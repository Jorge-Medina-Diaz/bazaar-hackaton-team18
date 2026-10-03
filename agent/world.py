"""M7 sensor: prioritised reads within the request budget -> immutable World (allowlisted fields, no foreign text)
plus Secrets (memory only). docs/harness-spec.md §1 (steps 4-5), §2.7, §8, INV-13, INV-18; late input D2.

NOTES (M7, night build)
- Every GET goes through the transport's public SDK methods (clock(), me(), my_offers(), ...); never `._call(`.
  Keyless polling (poll()) uses agent.transport.public_get with the public limiter.
- Foreign text never reaches the World. Each object is projected onto ALLOW[kind]; then split_untrusted() keeps a
  string only when its key is in SAFE_STR_KEYS and the value is a short token (TOKEN_RE). A dropped string under a
  token key, inside a list, or a dict key that is not a token is replaced by the constant UNTRUSTED, so an exact-shape
  check downstream (G11) sees "something odd was here" and fails closed instead of seeing a cleaned shape.
  Dropped text from rival-controlled sources goes base64 (redacted) to logs/run/untrusted.jsonl, deduplicated.
  Keys that look secret (key|token|secret|password) are dropped silently and never logged; starter_broker_key
  only goes to Secrets.
- Schema validation is strict per source: any malformed item in a source -> that source in World.down, a "shape"
  journal row, an "alarm" row after 3 consecutive failures; never an exception (except GateViolation, StopActive
  and JournalError, which must reach the runner: fail closed).
- Sources not read this tick (cadence, reduced mode with ticks < 10 s, fast path, time budget exhausted) keep the
  previous value; sources that the guards depend on (SOURCES table, §4) are then marked down. Other venues' boards
  and the venue list are read every 4 ticks unless tick_seconds >= 30 (D2); their stale copies are carried (the
  Gate re-reads before any accept).
- The World is deep-frozen: dicts -> MappingProxyType, lists -> tuples. CONSUMERS MUST NOT compare an inner list
  with a list literal (tuple != list): use tuple(x) == (...) or list(x) == [...]. MappingProxyType == dict works.
  thaw(world_part) gives plain JSON back (snapshots).
- World.threads = every thread with team == t18 (any status, keyed by id); World.foreign_threads = ids of OPEN
  threads that another team opened with us (closed ones are not actionable).
- tick_deadline = monotonic time taken BEFORE the clock GET + next_tick_in - TICK_MARGIN_S (conservative). Paused
  clock or doors not open -> deadline = that same instant (already expired: only cancel/close_thread pass G03).
- Venue fee: fee_bps/fee_per_card are the max of the current and an announced pending fee (conservative, D2).
- clock_reading: "?" with doors not open or no clock; "P" paused; round >= 2 and t >= 3.99 -> "N"; round >= 2 and
  t < 3.99 -> "M"; round 1 and t < 4 -> "C". After 10:21 a C morning reads as N (by then all timers run on game hours).
- Left out tonight (open issues): per-item tolerance on boards (one malformed offer downs the whole board); feed gap
  detection beyond an alarm row; value?card priority only from want_values() + visible offers + released catalog.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import time
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Optional

from agent.contracts import RASTRO, TEAM, VENUE_RE, Limits, Paths, Secrets, World
from agent.redact import redact


class SchemaError(Exception):
    """A response whose shape does not match what the sensor accepts. Message never carries response values."""


UNTRUSTED = "<untrusted>"
TOKEN_RE = re.compile(r"[A-Za-z0-9_:.+\-]{0,64}")
KEY_RE = re.compile(r"[A-Za-z0-9_\-]{1,40}")
SECRET_KEY_RE = re.compile(r"key|token|secret|password", re.IGNORECASE)
TICK_MARGIN_S = 2.0
FATAL = frozenset({"GateViolation", "StopActive", "JournalError"})

# Keys whose string values are server enumerations / ids (kept if they are short tokens).
SAFE_STR_KEYS = frozenset({
    "id", "ref", "set", "kind", "rarity", "status", "side", "role", "maker", "to", "venue", "owner", "team", "with",
    "sender", "from", "frm", "type", "scope", "actor", "persona", "dealer", "day", "today", "doors", "action",
    "pack", "packs", "issues", "unlocked", "types", "cards", "card", "release", "opens", "closes", "next_opens",
    "wall", "mechanism", "result", "closed_reason", "parties", "card_ref"})

# Field allowlists per object kind (top level of each object).
ALLOW: Mapping[str, frozenset] = MappingProxyType({
    "clock": frozenset({"tick", "t_hours", "tick_seconds", "paused", "next_tick_in", "round", "min_tick_seconds",
                        "max_tick_seconds", "limits", "calendar", "calendar_on", "doors", "today", "closes",
                        "next_opens", "days"}),
    "me": frozenset({"id", "cash", "level", "unlocked", "frozen", "affinity", "assets", "collection_value", "album",
                     "tick", "tick_seconds", "score", "venue", "open_threads"}),
    "asset": frozenset({"id", "kind", "ref", "serial", "rarity", "set", "print_run", "your_value", "pack", "type",
                        "locked"}),
    "offer": frozenset({"id", "maker", "to", "venue", "thread", "status", "give", "want", "expires_tick",
                        "created_tick", "final"}),
    "thread": frozenset({"id", "kind", "team", "with", "venue", "topic", "status", "created_tick", "messages",
                         "standing_offers", "closed_reason"}),
    "message": frozenset({"id", "tick", "sender", "offer", "final", "price"}),
    "duel": frozenset({"duel", "session", "status", "role", "issues", "your_days_weight", "your_limit",
                       "deadline_tick", "decay_per_round", "rounds", "your_offer", "rival_offer", "messages",
                       "result", "price", "days"}),
    "duel_offer": frozenset({"id", "price", "tick", "days"}),
    "duel_message": frozenset({"tick", "from", "price", "days"}),
    "venue": frozenset({"id", "owner", "status", "fee_bps", "fee_per_card", "house", "mechanism", "starter"}),
    "event": frozenset({"id", "tick", "t", "type", "scope", "actor", "payload"}),
    "schedule": frozenset({"now_hours", "upcoming"}),
    "upcoming": frozenset({"at_hours", "action", "params", "wall"}),
    "catalog": frozenset({"rarities", "sets", "packs", "values"}),
    "set": frozenset({"id", "released", "release", "cards"}),
    "card": frozenset({"id", "rarity", "book", "print_run", "minted", "hidden", "page"}),
    "pack": frozenset({"id", "slots", "expected_book"}),
})

# Sources whose dropped text is worth keeping in untrusted.jsonl (rival-controlled text).
LOG_UNTRUSTED = frozenset({"me/offers", "me/threads", "threads", "board", "boards", "venues", "duels", "feed",
                           "leaderboard"})
# Sources each kind depends on (§4 SOURCES): unread this tick -> down.
GUARDED_SOURCES = ("clock", "me", "me/offers", "me/threads", "threads", "board", "duels")
ALL_SOURCES = ("clock", "me", "me/offers", "me/threads", "threads", "board", "boards", "venues", "leaderboard",
               "duels", "feed", "values", "catalog", "schedule")


# ------------------------------------------------------------------------------------------ helpers

def _num(x: Any) -> bool:
    return type(x) in (int, float) and math.isfinite(x)


def _int(x: Any) -> bool:
    return type(x) is int


def _need(cond: bool, what: str) -> None:
    if not cond:
        raise SchemaError(what)


def _opt_int(d: Mapping, k: str) -> None:
    _need(d.get(k) is None or _int(d.get(k)), f"{k}: int or null")


def _opt_str(d: Mapping, k: str) -> None:
    _need(d.get(k) is None or isinstance(d.get(k), str), f"{k}: str or null")


def _project(d: Mapping, kind: str) -> dict:
    allow = ALLOW[kind]
    return {k: v for k, v in d.items() if k in allow}


def freeze(obj: Any) -> Any:
    """Deep freeze: dict -> MappingProxyType, list/tuple -> tuple."""
    if isinstance(obj, Mapping):
        return MappingProxyType({k: freeze(v) for k, v in obj.items()})
    if isinstance(obj, (list, tuple)):
        return tuple(freeze(v) for v in obj)
    return obj


def thaw(obj: Any) -> Any:
    """Plain JSON (dict/list) from a frozen World part (for snapshots and tests)."""
    if isinstance(obj, Mapping):
        return {k: thaw(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, frozenset, set)):
        return [thaw(v) for v in obj]
    return obj


_DROP = object()


def _split(obj: Any, path: str, key: Optional[str], out: list, depth: int) -> Any:
    if depth > 30:
        out.append((path, "<too deep>"))
        return UNTRUSTED
    if obj is None or type(obj) is bool or type(obj) is int:
        return obj
    if type(obj) is float:
        return obj if math.isfinite(obj) else None
    if isinstance(obj, str):
        if key in SAFE_STR_KEYS and TOKEN_RE.fullmatch(obj):
            return obj
        out.append((path, obj))
        return UNTRUSTED if key in SAFE_STR_KEYS or key == "[]" else _DROP
    if isinstance(obj, Mapping):
        res: dict = {}
        for k, v in obj.items():
            if not isinstance(k, str):
                res[UNTRUSTED] = True
                continue
            if SECRET_KEY_RE.search(k):
                continue                                   # silently: never logged, never kept
            if not KEY_RE.fullmatch(k):
                out.append((path + "{key}", k))
                res[UNTRUSTED] = True
                continue
            c = _split(v, f"{path}.{k}", k, out, depth + 1)
            if c is not _DROP:
                res[k] = c
        return res
    if isinstance(obj, (list, tuple)):
        res_l = []
        for i, v in enumerate(obj):
            c = _split(v, f"{path}[{i}]", key if key in SAFE_STR_KEYS else "[]", out, depth + 1)
            res_l.append(UNTRUSTED if c is _DROP else c)
        return res_l
    out.append((path, f"<{type(obj).__name__}>"))
    return _DROP if key not in SAFE_STR_KEYS else UNTRUSTED


def split_untrusted(obj: Any) -> tuple:
    """(clean, dropped): removes EVERY string outside SAFE_STR_KEYS/TOKEN_RE; dropped = [(json_path, text)].

    Inside lists and under token keys a dropped string becomes UNTRUSTED (shape preserved, fail closed);
    under other keys the key is removed. Secret-looking keys are removed and never reported.
    """
    out: list = []
    clean = _split(obj, "$", None, out, 0)
    if clean is _DROP:
        clean = None
    return clean, out


# ------------------------------------------------------------------------------------------ parsers
# Each _p_* returns (clean_plain_json, dropped). The public parse_* return only the clean mapping.

def _p_clock(d: Any) -> tuple:
    _need(isinstance(d, Mapping), "clock: object")
    _need(_int(d.get("tick")) and d["tick"] >= 0, "clock.tick: int")
    _need(_num(d.get("t_hours")), "clock.t_hours: number")
    _need(_num(d.get("tick_seconds")) and d["tick_seconds"] > 0, "clock.tick_seconds: positive number")
    _need(type(d.get("paused")) is bool, "clock.paused: bool")
    _need(_num(d.get("next_tick_in")) and d["next_tick_in"] >= 0, "clock.next_tick_in: number")
    _opt_int(d, "round")
    _opt_str(d, "doors")
    _need(d.get("limits") is None or isinstance(d.get("limits"), Mapping), "clock.limits: object")
    return split_untrusted(_project(d, "clock"))


def _p_asset(a: Any) -> dict:
    _need(isinstance(a, Mapping), "asset: object")
    _need(_int(a.get("id")) and a["id"] >= 0, "asset.id: int")
    _need(isinstance(a.get("kind"), str), "asset.kind: str")
    if a["kind"] == "card":
        _need(isinstance(a.get("ref"), str), "card asset.ref: str")
    return _project(a, "asset")


def _p_me(d: Any) -> tuple:
    _need(isinstance(d, Mapping), "me: object")
    _need(d.get("id") == TEAM, "me.id: our team")
    _need(_int(d.get("cash")), "me.cash: int")
    _need(isinstance(d.get("assets"), list), "me.assets: list")
    m = _project(d, "me")
    m["assets"] = [_p_asset(a) for a in d["assets"]]
    _need(d.get("affinity") is None or isinstance(d.get("affinity"), Mapping), "me.affinity: object")
    if isinstance(d.get("affinity"), Mapping):
        _need(all(_num(v) for v in d["affinity"].values()), "me.affinity: numbers")
    _need(d.get("unlocked") is None or isinstance(d.get("unlocked"), list), "me.unlocked: list")
    return split_untrusted(m)


def _bundle(b: Any, side: str) -> dict:
    _need(isinstance(b, Mapping), f"offer.{side}: object")
    _need(b.get("cash") is None or (_int(b["cash"]) and b["cash"] >= 0), f"offer.{side}.cash: int")
    out = dict(b)
    for k, v in b.items():
        if k not in ("cash", "assets", "types", "cards") and isinstance(v, str) and v:
            out[k] = [v]          # unknown text term: split_untrusted turns it into [UNTRUSTED], key kept (G11 sees it)
    if "assets" in b:
        _need(isinstance(b["assets"], list), f"offer.{side}.assets: list")
        out["assets"] = [_p_asset(a) for a in b["assets"]]
    for k in ("types", "cards"):
        if k in b:
            _need(isinstance(b[k], list) and all(isinstance(x, str) for x in b[k]), f"offer.{side}.{k}: list of str")
    return out


def _offer_plain(d: Any) -> dict:
    _need(isinstance(d, Mapping), "offer: object")
    _need(_int(d.get("id")) and d["id"] >= 0, "offer.id: int")
    _need(isinstance(d.get("maker"), str), "offer.maker: str")
    _need(isinstance(d.get("status"), str), "offer.status: str")
    _opt_str(d, "to")
    _opt_str(d, "venue")
    _opt_int(d, "thread")
    _opt_int(d, "expires_tick")
    _opt_int(d, "created_tick")
    _need(d.get("final") is None or type(d.get("final")) is bool, "offer.final: bool")
    o = _project(d, "offer")
    o["give"] = _bundle(d.get("give"), "give")
    o["want"] = _bundle(d.get("want"), "want")
    return o


def _p_offer(d: Any) -> tuple:
    return split_untrusted(_offer_plain(d))


def _message_plain(m: Any) -> dict:
    _need(isinstance(m, Mapping), "message: object")
    _need(_int(m.get("id")), "message.id: int")
    _need(_int(m.get("tick")), "message.tick: int")
    _need(isinstance(m.get("sender"), str), "message.sender: str")
    out = _project(m, "message")
    if m.get("offer") is not None:
        out["offer"] = _offer_plain(m["offer"])
    return out


def _p_thread(d: Any) -> tuple:
    if isinstance(d, Mapping) and isinstance(d.get("thread"), Mapping) and "id" not in d:
        d = d["thread"]
    _need(isinstance(d, Mapping), "thread: object")
    _need(_int(d.get("id")) and d["id"] >= 0, "thread.id: int")
    _need(isinstance(d.get("team"), str), "thread.team: str")
    _need(isinstance(d.get("status"), str), "thread.status: str")
    _need(isinstance(d.get("with"), str), "thread.with: str")
    _need(d.get("topic") is None or isinstance(d.get("topic"), Mapping), "thread.topic: object")
    _need(isinstance(d.get("messages", []), list), "thread.messages: list")
    _need(isinstance(d.get("standing_offers", []), list), "thread.standing_offers: list")
    t = _project(d, "thread")
    t["messages"] = [_message_plain(m) for m in d.get("messages", [])]
    t["standing_offers"] = [_offer_plain(o) for o in d.get("standing_offers", [])]
    return split_untrusted(t)


def _duel_offer(o: Any, what: str) -> Optional[dict]:
    if o is None:
        return None
    _need(isinstance(o, Mapping), f"{what}: object")
    _need(_int(o.get("price")), f"{what}.price: int")
    _need(_int(o.get("tick")), f"{what}.tick: int")
    _opt_int(o, "days")
    return _project(o, "duel_offer")


def _p_duel(d: Any) -> tuple:
    _need(isinstance(d, Mapping), "duel: object")
    _need(_int(d.get("duel")), "duel.duel: int")
    _need(isinstance(d.get("status"), str), "duel.status: str")
    _need(d.get("role") in ("buyer", "seller"), "duel.role")
    _need(_num(d.get("your_limit")), "duel.your_limit: number")
    _need(_int(d.get("deadline_tick")), "duel.deadline_tick: int")
    _need(_int(d.get("rounds")), "duel.rounds: int")
    _need(_num(d.get("decay_per_round")), "duel.decay_per_round: number")
    _need(isinstance(d.get("issues", []), list), "duel.issues: list")
    _need(isinstance(d.get("messages", []), list), "duel.messages: list")
    out = _project(d, "duel")
    out["your_offer"] = _duel_offer(d.get("your_offer"), "duel.your_offer")
    out["rival_offer"] = _duel_offer(d.get("rival_offer"), "duel.rival_offer")
    msgs = []
    for m in d.get("messages", []):
        _need(isinstance(m, Mapping) and _int(m.get("tick")) and isinstance(m.get("from"), str), "duel.message")
        _opt_int(m, "price")
        _opt_int(m, "days")
        msgs.append(_project(m, "duel_message"))
    out["messages"] = msgs
    return split_untrusted(out)


def _p_venue(v: Any, tick: int) -> tuple:
    _need(isinstance(v, Mapping), "venue: object")
    vid = v.get("venue", v.get("id"))
    _need(isinstance(vid, str) and re.fullmatch(VENUE_RE, vid) is not None, "venue.id")
    _need(isinstance(v.get("owner"), str), "venue.owner: str")
    _need(isinstance(v.get("status"), str), "venue.status: str")
    _need(_int(v.get("fee_bps")) and v["fee_bps"] >= 0, "venue.fee_bps: int")
    _need(_int(v.get("fee_per_card")) and v["fee_per_card"] >= 0, "venue.fee_per_card: int")
    fee_bps, per_card = v["fee_bps"], v["fee_per_card"]
    pend = v.get("pending_fee")
    if isinstance(pend, Mapping) and _int(pend.get("effective_tick")) and pend["effective_tick"] >= tick:
        if _int(pend.get("fee_bps")):
            fee_bps = max(fee_bps, pend["fee_bps"])
        if _int(pend.get("fee_per_card")):
            per_card = max(per_card, pend["fee_per_card"])
    rules = v.get("rules")
    out = {"id": vid, "owner": v["owner"], "status": v["status"], "fee_bps": fee_bps, "fee_per_card": per_card,
           "house": v.get("house") is True, "starter": v.get("starter") is True,
           "mechanism": rules.get("mechanism") if isinstance(rules, Mapping) else None}
    return split_untrusted(out)


def _p_event(e: Any) -> tuple:
    _need(isinstance(e, Mapping), "event: object")
    _need(_int(e.get("id")), "event.id: int")
    _need(_int(e.get("tick")), "event.tick: int")
    _need(isinstance(e.get("type"), str), "event.type: str")
    _need(e.get("payload") is None or isinstance(e.get("payload"), Mapping), "event.payload: object")
    return split_untrusted(_project(e, "event"))


def _p_schedule(d: Any) -> tuple:
    _need(isinstance(d, Mapping), "schedule: object")
    _need(_num(d.get("now_hours")), "schedule.now_hours: number")
    _need(isinstance(d.get("upcoming", []), list), "schedule.upcoming: list")
    ups = []
    for u in d.get("upcoming", []):
        _need(isinstance(u, Mapping) and _num(u.get("at_hours")) and isinstance(u.get("action"), str),
              "schedule.upcoming entry")
        _need(u.get("params") is None or isinstance(u.get("params"), Mapping), "schedule.params: object")
        ups.append(_project(u, "upcoming"))
    return split_untrusted({"now_hours": d["now_hours"], "upcoming": ups})


def _p_catalog(d: Any) -> tuple:
    _need(isinstance(d, Mapping), "catalog: object")
    _need(isinstance(d.get("sets"), list), "catalog.sets: list")
    sets = []
    for s in d["sets"]:
        _need(isinstance(s, Mapping) and isinstance(s.get("id"), str) and type(s.get("released")) is bool,
              "catalog.set")
        _need(isinstance(s.get("cards", []), list), "catalog.set.cards: list")
        ss = _project(s, "set")
        cards = []
        for c in s.get("cards", []):
            _need(isinstance(c, Mapping) and isinstance(c.get("id"), str) and isinstance(c.get("rarity"), str),
                  "catalog.card")
            cards.append(_project(c, "card"))
        ss["cards"] = cards
        sets.append(ss)
    _need(isinstance(d.get("packs", []), list), "catalog.packs: list")
    packs = []
    for p in d.get("packs", []):
        _need(isinstance(p, Mapping) and isinstance(p.get("id"), str), "catalog.pack")
        packs.append(_project(p, "pack"))
    out = _project(d, "catalog")
    out["sets"], out["packs"] = sets, packs
    return split_untrusted(out)


def _p_leaderboard(d: Any) -> tuple:
    _need(isinstance(d, Mapping) and isinstance(d.get("teams"), list), "leaderboard.teams: list")
    rows = []
    for t in d["teams"]:
        _need(isinstance(t, Mapping) and isinstance(t.get("team"), str) and _int(t.get("rank")), "leaderboard row")
        rows.append((t["rank"], t["team"]))
    rows.sort()
    teams, dropped = split_untrusted({"team": [r[1] for r in rows]})
    nxt = d.get("next_refresh_tick")
    return (tuple(teams["team"]), nxt if _int(nxt) else None), dropped


def _offers_list(d: Any, what: str) -> list:
    if isinstance(d, Mapping):
        rows: list = []
        found = False
        for k in ("offers", "open", "queued"):
            if k in d:
                found = True
                _need(isinstance(d[k], list), f"{what}.{k}: list")
                rows.extend(d[k])
        _need(found, f"{what}: no offers list")
        return rows
    _need(isinstance(d, list), f"{what}: list")
    return d


def _p_offers(d: Any, what: str) -> tuple:
    plain = [_offer_plain(o) for o in _offers_list(d, what)]
    seen: dict = {}
    for o in plain:                                       # dedupe by id (open + queued lists may overlap)
        seen.setdefault(o["id"], o)
    return split_untrusted(list(seen.values()))


def parse_clock(d: Any) -> Mapping:
    return freeze(_p_clock(d)[0])


def parse_me(d: Any) -> Mapping:
    return freeze(_p_me(d)[0])


def parse_offer(d: Any) -> Mapping:
    return freeze(_p_offer(d)[0])


def parse_thread(d: Any) -> Mapping:
    return freeze(_p_thread(d)[0])


def parse_duel(d: Any) -> Mapping:
    return freeze(_p_duel(d)[0])


def clock_reading(clock: Optional[Mapping], schedule: Optional[Mapping]) -> str:
    """'N' | 'M' | 'C' | 'P' | '?' (strategy §4). Uses schedule.now_hours only if the clock lacks t_hours."""
    if not isinstance(clock, Mapping) or not clock:
        return "?"
    doors = clock.get("doors")
    if doors is not None and doors != "open":
        return "?"
    if clock.get("paused") is True:
        return "P"
    rnd = clock.get("round")
    t = clock.get("t_hours")
    if not _num(t) and isinstance(schedule, Mapping):
        t = schedule.get("now_hours")
    if not _int(rnd) or not _num(t):
        return "?"
    if rnd >= 2:
        return "N" if t >= 3.99 else "M"
    if rnd == 1 and t < 4.0:
        return "C"
    return "?"


# -------------------------------------------------------------------------------------------- sensor

class _SysClock:
    @staticmethod
    def now() -> float:
        return time.monotonic()


class Sensor:
    FEED_LIMIT = 200
    VALUES_PER_TICK = 3
    OTHER_BOARDS_EVERY = 4            # ticks, unless tick_seconds >= SLOW_TICK_S (D2)
    SLOW_TICK_S = 30.0
    FAST_TICK_S = 10.0                # below: clock, me, me/offers, duels only (§14 S-M6)
    CATALOG_EVERY = 10
    LEADERBOARD_EVERY = 4
    MAX_OTHER_BOARDS = 8
    SHAPE_ALARM_AFTER = 3
    PAUSED_READ_BUDGET_S = 20.0
    UNTRUSTED_SEEN_MAX = 20000

    def __init__(self, transport: Any, base_url: Optional[str], journal: Any, paths: Paths, public_limiter: Any,
                 clock: Any, *, tick_margin_s: float = TICK_MARGIN_S):
        self.transport = transport
        self.base_url = base_url
        self.journal = journal
        self.paths = paths
        self.public_limiter = public_limiter
        self.clock = clock if clock is not None else _SysClock()
        self.tick_margin_s = float(tick_margin_s)
        self._streak: dict = {}
        self._seen_untrusted: set = set()
        self._feed_last: Optional[int] = None
        self._values: dict = {}
        self._values_version: Optional[str] = None
        self._wish: tuple = ()
        self._last_other_boards: Optional[int] = None
        self._last_catalog: Optional[int] = None
        self._last_leaderboard: Optional[int] = None
        self._leader_next: Optional[int] = None
        self._tick = 0

    # ------------------------------------------------------------------ public API

    def want_values(self, refs: Iterable[str]) -> None:
        """Refs whose value?card the next snapshots fetch first (e.g. the planner's needs)."""
        self._wish = tuple(r for r in refs if isinstance(r, str) and TOKEN_RE.fullmatch(r))

    def fast(self, prev: Optional[World]) -> World:
        """Fast path: clock + me/offers only. Every other guarded source is down."""
        down: set = set()
        clock, t0 = self._read_clock(down)
        offers = self._fetch("me/offers", lambda: self.transport.my_offers(), lambda d: _p_offers(d, "me/offers"),
                             down)
        parts = self._carry(prev)
        if offers is not None:
            parts["my_offers_raw"] = offers
        for s in ("me", "me/threads", "threads", "board", "duels", "boards", "venues", "leaderboard", "values"):
            down.add(s)
        return self._assemble(prev, clock, t0, parts, down)

    def poll(self, prev: Optional[World]) -> World:
        """Keyless clock + schedule (paused clock / closed doors). Everything else down."""
        down: set = set()
        try:
            from agent.transport import public_get
        except Exception:                                    # pragma: no cover - transport is M1
            public_get = None

        def get(path: str) -> Any:
            if public_get is None or not self.base_url or self.public_limiter is None:
                return getattr(self.transport, path.rsplit("/", 1)[-1])()
            return public_get(self.base_url, path, self.public_limiter)

        t0 = self.clock.now()
        clock = self._fetch("clock", lambda: get("/api/clock"), _p_clock, down)
        parts = self._carry(prev)
        sched = self._fetch("schedule", lambda: get("/api/schedule"), _p_schedule, down)
        if sched is not None:
            parts["schedule"] = sched
        down.update(s for s in ALL_SOURCES if s not in ("clock", "schedule"))
        return self._assemble(prev, clock, t0, parts, down)

    def snapshot(self, prev: Optional[World]) -> tuple:
        """Full prioritised read (§1 step 5). Returns (World, Secrets)."""
        down: set = set()
        clock, t0 = self._read_clock(down)
        tick = clock["tick"] if clock else (prev.tick if prev else 0)
        tick_s = clock["tick_seconds"] if clock else (prev.tick_seconds if prev else 60.0)
        deadline = self._deadline(clock, t0)
        if clock is not None and deadline <= t0:            # paused / doors closed: reads are not racing a tick
            deadline = t0 + self.PAUSED_READ_BUDGET_S
        reduced = tick_s < self.FAST_TICK_S
        parts = self._carry(prev)
        secrets = Secrets()
        read: set = {"clock"}

        def time_left() -> bool:
            return self.clock.now() < deadline

        # 1. me (+ Secrets)
        raw_me: dict = {}

        def get_me() -> Any:
            d = self.transport.me()
            if isinstance(d, Mapping):
                raw_me["key"] = d.get("starter_broker_key")
            return d
        me = self._fetch("me", get_me, _p_me, down)
        read.add("me")
        if me is not None:
            parts["me"] = me
            if isinstance(raw_me.get("key"), str) and raw_me["key"]:
                secrets = Secrets(starter_broker_key=raw_me["key"])
        # 2. me/offers
        offers = self._fetch("me/offers", lambda: self.transport.my_offers(), lambda d: _p_offers(d, "me/offers"),
                             down)
        read.add("me/offers")
        if offers is not None:
            parts["my_offers_raw"] = offers
        # 3. duels
        duels = self._fetch("duels", lambda: self.transport.duels(), self._p_duels, down)
        read.add("duels")
        if duels is not None:
            parts["duels"] = duels
        if not reduced:
            # 4. me/threads, then threads/{id} for our open dealer threads
            if time_left():
                ths = self._fetch("me/threads", lambda: self.transport.my_threads(), self._p_threads, down)
                read.add("me/threads")
                if ths is not None:
                    parts["threads_raw"] = ths
                    ok = True
                    fresh = {}
                    for t in ths:
                        if t["team"] == TEAM and t["status"] == "open":
                            tid = t["id"]
                            got = self._fetch("threads", lambda tid=tid: self.transport.thread(tid), _p_thread, down)
                            if got is None or got.get("id") != tid:
                                ok = False
                                down.add("threads")
                            else:
                                fresh[tid] = got
                    if ok:
                        read.add("threads")
                    parts["threads_raw"] = [fresh.get(t["id"], t) for t in ths]
                    parts["foreign_ids"] = None              # recomputed from this tick's threads
            # 5. El Rastro
            if time_left():
                b = self._fetch("board", lambda: self.transport.board(RASTRO), lambda d: _p_offers(d, "board"), down)
                read.add("board")
                if b is not None:
                    parts["boards"] = dict(parts["boards"])
                    parts["boards"][RASTRO] = [o for o in b if o.get("status") == "open"]
            # 6. venues + other boards (D2 cadence)
            every = 1 if tick_s >= self.SLOW_TICK_S else self.OTHER_BOARDS_EVERY
            due = self._last_other_boards is None or tick - self._last_other_boards >= every or tick < self._last_other_boards
            if due and time_left():
                self._read_venues(tick, parts, down, read, time_left)
            # 7. schedule (every tick), feed, leaderboard, catalog
            if time_left():
                s = self._fetch("schedule", lambda: self.transport.schedule(), _p_schedule, down)
                if s is not None:
                    parts["schedule"] = s
            if time_left():
                self._read_feed(tick, parts, down)
            lb_due = (self._last_leaderboard is None or tick - self._last_leaderboard >= self.LEADERBOARD_EVERY
                      or (self._leader_next is not None and tick >= self._leader_next) or tick < self._last_leaderboard)
            if lb_due and time_left():
                lb = self._fetch("leaderboard", lambda: self.transport.leaderboard(), _p_leaderboard, down)
                self._last_leaderboard = tick
                if lb is not None:
                    parts["leaderboard"], self._leader_next = lb[0], lb[1]
                else:
                    parts["leaderboard"] = ()             # D2 rule must fail closed
            cat_due = (self._last_catalog is None or not parts.get("catalog")
                       or tick - self._last_catalog >= self.CATALOG_EVERY or tick < self._last_catalog)
            if cat_due and time_left():
                c = self._fetch("catalog", lambda: self.transport.catalog(), _p_catalog, down)
                if c is not None:
                    parts["catalog"] = c
                    self._last_catalog = tick
        # 8. value?card (<= 3 per tick, cached per inventory version)
        self._read_values(parts, me, down, reduced or not time_left())
        for s in GUARDED_SOURCES:
            if s not in read:
                down.add(s)
        if not parts.get("catalog"):
            down.add("catalog")
        if not parts.get("schedule"):
            down.add("schedule")
        world = self._assemble(prev, clock, t0, parts, down)
        return world, secrets

    # ------------------------------------------------------------------ internals

    def _p_duels(self, d: Any) -> tuple:
        if isinstance(d, Mapping):
            _need(isinstance(d.get("duels"), list), "duels: list")
            d = d["duels"]
        _need(isinstance(d, list), "duels: list")
        out, dropped = [], []
        for x in d:
            c, dr = _p_duel(x)
            out.append(c)
            dropped.extend(dr)
        return out, dropped

    def _p_threads(self, d: Any) -> tuple:
        if isinstance(d, Mapping):
            _need(isinstance(d.get("threads"), list), "me/threads: list")
            d = d["threads"]
        _need(isinstance(d, list), "me/threads: list")
        out, dropped = [], []
        for x in d:
            c, dr = _p_thread(x)
            out.append(c)
            dropped.extend(dr)
        return out, dropped

    def _read_clock(self, down: set) -> tuple:
        t0 = self.clock.now()
        c = self._fetch("clock", lambda: self.transport.clock(), _p_clock, down)
        if c is not None:
            self._tick = c["tick"]
        return c, t0

    def _deadline(self, clock: Optional[Mapping], t0: float) -> float:
        if not clock or clock.get("paused") is True or (clock.get("doors") not in (None, "open")):
            return t0
        return t0 + float(clock["next_tick_in"]) - self.tick_margin_s

    def _carry(self, prev: Optional[World]) -> dict:
        if prev is None:
            return {"me": {}, "my_offers_raw": [], "threads_raw": [], "boards": {}, "duels": [], "schedule": {},
                    "catalog": {}, "venues": [], "leaderboard": (), "feed_new": [], "values": {}}
        return {"me": thaw(prev.me), "my_offers_raw": [thaw(o) for o in prev.my_offers] +
                [thaw(o) for o in prev.offers_to_us],
                "threads_raw": [thaw(t) for t in prev.threads.values()] + [],
                "foreign_ids": tuple(prev.foreign_threads),
                "boards": {k: [thaw(o) for o in v] for k, v in prev.boards.items()} or
                ({RASTRO: [thaw(o) for o in prev.board]} if prev.board else {}),
                "duels": [thaw(x) for x in prev.duels], "schedule": thaw(prev.schedule), "catalog": thaw(prev.catalog),
                "venues": [thaw(v) for v in prev.venues], "leaderboard": tuple(prev.leaderboard),
                "feed_new": [], "values": dict(prev.server_values), "pseudonym": prev.own_pseudonym}

    def _fetch(self, source: str, getter: Callable[[], Any], parser: Callable[[Any], tuple], down: set) -> Any:
        try:
            raw = getter()
        except Exception as e:
            if type(e).__name__ in FATAL:
                raise
            down.add(source)
            self._fail(source, "fetch", e)
            return None
        try:
            clean, dropped = parser(raw)
        except SchemaError as e:
            down.add(source)
            self._fail(source, "shape", e)
            return None
        except Exception as e:                              # parser bug or exotic payload: still fail closed
            if type(e).__name__ in FATAL:
                raise
            down.add(source)
            self._fail(source, "shape", e)
            return None
        self._streak[source] = 0
        if dropped and source in LOG_UNTRUSTED:
            self._log_untrusted(source, dropped)
        return clean

    def _fail(self, source: str, how: str, e: BaseException) -> None:
        n = self._streak.get(source, 0) + 1
        self._streak[source] = n
        code = getattr(e, "code", None)
        code = code if isinstance(code, str) and TOKEN_RE.fullmatch(code) else None
        detail = str(e) if isinstance(e, SchemaError) else type(e).__name__
        if self.journal is not None:
            if how == "shape":
                self.journal.write("shape", source=source, error=detail[:200])
            if n == self.SHAPE_ALARM_AFTER:
                self.journal.write("alarm", what="source_failing", source=source, how=how, code=code,
                                   consecutive=n)

    def _log_untrusted(self, source: str, dropped: list) -> None:
        lines = []
        for path, text in dropped:
            if not isinstance(text, str) or not text:
                continue
            h = hashlib.sha1(f"{source}|{path}|{text}".encode("utf-8", "replace")).hexdigest()
            if h in self._seen_untrusted:
                continue
            if len(self._seen_untrusted) >= self.UNTRUSTED_SEEN_MAX:
                self._seen_untrusted.clear()
            self._seen_untrusted.add(h)
            safe = redact(text)
            lines.append(json.dumps({"ts": time.time(), "tick": self._tick, "source": source, "path": path[:200],
                                     "b64": base64.b64encode(safe.encode("utf-8", "replace")).decode("ascii")}))
        if not lines:
            return
        try:
            p = self.paths.untrusted
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError:
            if self.journal is not None:
                self.journal.write("alarm", what="untrusted_log_failed", source=source)

    def _read_venues(self, tick: int, parts: dict, down: set, read: set, time_left: Callable[[], bool]) -> None:
        def parse(d: Any) -> tuple:
            rows = d.get("venues") if isinstance(d, Mapping) else d
            _need(isinstance(rows, list), "venues: list")
            out, dropped = [], []
            for v in rows:
                c, dr = _p_venue(v, tick)
                out.append(c)
                dropped.extend(dr)
            return out, dropped
        vs = self._fetch("venues", lambda: self.transport.venues(), parse, down)
        boards = {RASTRO: parts["boards"].get(RASTRO, [])}
        if vs is None:
            parts["boards"] = boards                        # fail closed: no stale rival boards without a venue list
            return
        self._last_other_boards = tick
        parts["venues"] = vs
        others = sorted((v for v in vs if v["status"] == "open" and v["id"] != RASTRO
                         and re.fullmatch(VENUE_RE, v["id"]) and v["owner"] != TEAM),
                        key=lambda v: v["id"])[: self.MAX_OTHER_BOARDS]
        for v in others:
            if not time_left():
                down.add("boards")
                break
            vid = v["id"]
            b = self._fetch("boards", lambda vid=vid: self.transport.board(vid), lambda d: _p_offers(d, "boards"),
                            down)
            if b is not None:
                boards[vid] = [o for o in b if o.get("status") == "open"]
        parts["boards"] = boards

    def _read_feed(self, tick: int, parts: dict, down: set) -> None:
        def parse(d: Any) -> tuple:
            rows = d.get("events") if isinstance(d, Mapping) else d
            _need(isinstance(rows, list), "feed.events: list")
            out, dropped = [], []
            for e in rows:
                c, dr = _p_event(e)
                out.append(c)
                dropped.extend(dr)
            return out, dropped
        ev = self._fetch("feed", lambda: self.transport.feed(limit=self.FEED_LIMIT), parse, down)
        if ev is None:
            parts["feed_new"] = []
            return
        if self._feed_last is None:
            new = [e for e in ev if e["tick"] >= tick]
        else:
            new = [e for e in ev if e["id"] > self._feed_last]
            if new and ev and min(e["id"] for e in ev) > self._feed_last + 1 and self.journal is not None:
                self.journal.write("alarm", what="feed_gap", since=self._feed_last)
        if ev:
            self._feed_last = max([e["id"] for e in ev] + ([self._feed_last] if self._feed_last is not None else []))
        parts["feed_new"] = sorted(new, key=lambda e: e["id"])

    def _read_values(self, parts: dict, me: Optional[Mapping], down: set, skip: bool) -> None:
        if me is None:
            if "me" in down:
                down.add("values")
            parts["values"] = dict(self._values)
            return
        version = hashlib.sha1(json.dumps(sorted((a.get("id"), a.get("kind"), a.get("ref"))
                                                 for a in me.get("assets", [])), default=str).encode()).hexdigest()
        if version != self._values_version:
            self._values, self._values_version = {}, version
        if not skip:
            order: list = []

            def add(r: Any) -> None:
                if isinstance(r, str) and TOKEN_RE.fullmatch(r) and r and r not in self._values and r not in order:
                    order.append(r)
            for r in self._wish:
                add(r)
            for o in parts.get("my_offers_raw", []):
                if o.get("to") == TEAM and o.get("maker") != TEAM:
                    for a in o["give"].get("assets", []) or []:
                        add(a.get("ref"))
                    for t in o["give"].get("types", []) or []:
                        add(t[5:] if isinstance(t, str) and t.startswith("card:") else None)
            for board in parts.get("boards", {}).values():
                for o in board:
                    for a in o["give"].get("assets", []) or []:
                        add(a.get("ref"))
            released = {s["id"] for s in parts.get("catalog", {}).get("sets", []) if s.get("released")}
            for s in parts.get("catalog", {}).get("sets", []):
                if s["id"] in released:
                    for c in s.get("cards", []):
                        add(c.get("id"))
            for ref in order[: self.VALUES_PER_TICK]:
                got = self._fetch("values", lambda ref=ref: self.transport.value(ref),
                                  lambda d, ref=ref: self._p_value(d, ref), down)
                if got is None:
                    break
                self._values[ref] = got
        parts["values"] = dict(self._values)

    @staticmethod
    def _p_value(d: Any, ref: str) -> tuple:
        _need(isinstance(d, Mapping), "value: object")
        _need(d.get("card") in (None, ref), "value.card: requested ref")
        v = d.get("your_value")
        _need(_num(v) and v >= 0, "value.your_value: number")
        return float(v), []

    def _assemble(self, prev: Optional[World], clock: Optional[Mapping], t0: float, parts: dict,
                  down: set) -> World:
        if clock is not None:
            tick, t_hours, tick_s, rnd = clock["tick"], float(clock["t_hours"]), float(clock["tick_seconds"]), \
                clock.get("round")
            clock_m = clock
        else:
            down.add("clock")
            tick = prev.tick if prev else 0
            t_hours = prev.t_hours if prev else 0.0
            tick_s = prev.tick_seconds if prev else 60.0
            rnd = prev.round if prev else None
            clock_m = thaw(prev.clock) if prev else {}
        self._tick = tick
        limits = Limits.from_clock(clock_m if clock is not None else {}, prev.limits if prev else None)
        offers = parts.get("my_offers_raw", [])
        my_offers = [o for o in offers if o.get("maker") == TEAM]
        to_us = [o for o in offers if o.get("to") == TEAM and o.get("maker") != TEAM]
        threads_raw = parts.get("threads_raw", [])
        ours = {t["id"]: t for t in threads_raw if t.get("team") == TEAM}
        foreign = parts.get("foreign_ids")
        if foreign is None:
            foreign = tuple(sorted(t["id"] for t in threads_raw if t.get("team") != TEAM and t.get("status") == "open"))
        boards = parts.get("boards", {})
        board = boards.get(RASTRO, [])
        pseudo = self._pseudonym(my_offers, boards, parts.get("pseudonym"))
        catalog = parts.get("catalog", {}) or {}
        released = frozenset(s["id"] for s in catalog.get("sets", []) if s.get("released") is True)
        if not catalog and prev is not None:
            released = prev.released_sets
        down_f = frozenset(s for s in down if s in ALL_SOURCES)
        schedule = parts.get("schedule", {}) or {}
        return World(
            tick=tick, t_hours=t_hours, round=rnd, tick_seconds=tick_s,
            tick_deadline=self._deadline(clock, t0),
            clock=freeze(clock_m), limits=limits, reading=clock_reading(clock, schedule),
            me=freeze(parts.get("me", {}) or {}),
            my_offers=freeze(my_offers), offers_to_us=freeze(to_us), board=freeze(board),
            own_pseudonym=pseudo, threads=MappingProxyType({k: freeze(v) for k, v in ours.items()}),
            foreign_threads=foreign, duels=freeze(parts.get("duels", [])),
            catalog=freeze(catalog), schedule=freeze(schedule), released_sets=released,
            feed_new=freeze(parts.get("feed_new", [])),
            server_values=MappingProxyType(dict(parts.get("values", {}))), down=down_f,
            boards=MappingProxyType({k: freeze(v) for k, v in boards.items()}),
            venues=freeze(parts.get("venues", [])), leaderboard=tuple(parts.get("leaderboard", ())))

    def _pseudonym(self, my_offers: list, boards: Mapping, prev: Optional[str]) -> Optional[str]:
        ids = {o["id"] for o in my_offers}
        found: dict = {}
        order = [RASTRO] + sorted(k for k in boards if k != RASTRO)
        for vid in order:
            for o in boards.get(vid, []):
                m = o.get("maker")
                if o.get("id") in ids and isinstance(m, str) and m not in (TEAM, UNTRUSTED):
                    found[m] = max(found.get(m, -1), o["id"])
            if found:
                break                                       # rastro first; other venues only if rastro shows none
        if not found:
            return prev
        if len(found) > 1 and self.journal is not None:
            self.journal.write("alarm", what="pseudonym_conflict", candidates=sorted(found))
        return max(found, key=lambda m: found[m])
