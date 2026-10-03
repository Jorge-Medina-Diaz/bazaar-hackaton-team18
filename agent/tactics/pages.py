"""M8 pages: page plan (Needs per source with a cap), closer card frozen at 8/10, dynamic protect_sets, plan data.

Contract: docs/harness-spec.md §2.7 (signatures), §4 (G13, G21, G30, G32 read what this module produces),
docs/strategy.md J3, J4, J9, J12, J13. Pure: no I/O except load_plan reading config/plan.json.

NOTES (M8, night build)
- plan(): for each set of plan_cfg.page_sets that is released: every page card we do not hold is a Need. One of them
  is the closer (source "team", closer=True, never bought from a dealer); the others are dealer Needs with the
  profile's dealer and cap = min(profile.limit, dealer_max[ref], floor(dv_add - 1)). The closer is re-chosen each
  tick with closer_ref until the page reaches closer.freeze_at (8) cards held or in flight; from then on it is frozen
  (returned in the frozen dict, persisted by the runner) until we hold it.
- "In flight" here = own open bids on El Rastro (my_offers) and open dealer buy threads with a standing offer.
  Accepted-but-unsettled trades are not visible to plan() (no journal argument); guards use Book.projected, which
  has them, so G30/G32 still block a dealer buy that would close the page.
- Fail closed: "me" or "catalog" down, or a valuation error on a set -> no Needs for that set (frozen kept).
  A page card without a dealer profile gets no dealer Need. After the day's day_end_hours no dealer Needs.
- Closer cap: floor(dv_close - default_minus) where dv_close is the closer's value once the other page cards are
  held (99.1 -> 49 for a RET common); floor(dv_close - compete_minus) (79) when a rival bid for that ref on any
  board reaches our cap, or in the endgame (closer.endgame_hours). Never below our own standing bid (never lower).
- protect_sets: plan_cfg.protect_sets + page_sets; LAT leaves at lat_give_up.tick when neither LAT-09 nor LAT-10 is
  held, pending in (journal_view["pending_in"]) or filled (journal_view["filled_offers"]). Unknown -> keep (safe side).
- spare_assets(): helper for M11 (J5 sales and D1 swaps): card assets that can be handed over without touching the
  last copy of a protected page card; it does not price anything.
- Open: RET-08/CHA-08 fallback to the Abuela after fallback_after ticks is data only (profile.fallback_dealer); the
  switch is M10's. "Sales seen" in closer_ref uses only feed_new of this tick and the boards (no history).
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from agent.contracts import TEAM, Need, PlanCfg

DEALERS = frozenset({"abuela", "chato", "picaros"})
RARITY_RANK = {"common": 0, "uncommon": 1, "rare": 2, "epic": 3, "legendary": 4}
OPEN_STATUSES = frozenset({"open", "queued"})
CLOSED_THREAD = frozenset({"closed", "deal", "expired", "cancelled", "settled"})

_REQUIRED = {
    "page_sets": list, "protect_sets": list, "startup_cancels": list, "baseline_bands": dict, "dealer_max": dict,
    "profiles": dict, "closer": dict, "resupply_min": (int, float), "dup_min_price": dict,
    "days_sign": (int, type(None)), "day_end_hours": dict, "grant_lookahead_ticks": int,
}


# ------------------------------------------------------------------------------------------ load_plan

def _num(x: Any) -> bool:
    return type(x) in (int, float) and math.isfinite(x)


def load_plan(path: Path) -> PlanCfg:
    """Read and validate config/plan.json. ValueError on anything missing or malformed (fail closed)."""
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        raise ValueError("plan: top level must be an object")
    cfg = {k: v for k, v in raw.items() if not k.startswith("_")}
    for k, t in _REQUIRED.items():
        if k not in cfg:
            raise ValueError(f"plan: missing key {k!r}")
        allowed = t if isinstance(t, tuple) else (t,)
        if type(cfg[k]) not in allowed:
            raise ValueError(f"plan.{k}: bad type {type(cfg[k]).__name__}")
    for k in ("page_sets", "protect_sets"):
        if not all(type(s) is str and s for s in cfg[k]):
            raise ValueError(f"plan.{k}: list of set ids")
    for e in cfg.get("extra_needs", []):
        if not (isinstance(e, dict) and type(e.get("ref")) is str and type(e.get("max_price")) is int
                and e["max_price"] >= 1 and e["ref"] in (cfg.get("profiles") or {})):
            raise ValueError("plan.extra_needs: [{ref, max_price}] with a profile for ref")
    if not all(type(x) is int and x >= 0 for x in cfg["startup_cancels"]):
        raise ValueError("plan.startup_cancels: list of offer ids")
    if not all(type(k) is str and _num(v) for k, v in cfg["baseline_bands"].items()):
        raise ValueError("plan.baseline_bands: offer id -> number")
    if not all(type(v) is int and v >= 0 for v in cfg["dealer_max"].values()):
        raise ValueError("plan.dealer_max: ref -> int >= 0")
    for key, p in cfg["profiles"].items():
        if not isinstance(p, dict) or p.get("dealer") not in DEALERS:
            raise ValueError(f"plan.profiles.{key}: dealer must be one of {sorted(DEALERS)}")
        a, s, lim = p.get("anchor"), p.get("step"), p.get("limit")
        if not (type(a) is int and type(s) is int and type(lim) is int and 0 < a <= lim and s >= 1):
            raise ValueError(f"plan.profiles.{key}: need int 0 < anchor <= limit and step >= 1")
        fa = p.get("fallback_after")
        if fa is not None and not (type(fa) is int and fa >= 1):
            raise ValueError(f"plan.profiles.{key}: fallback_after int >= 1 or null")
        if p.get("fallback_dealer") is not None and p["fallback_dealer"] not in DEALERS:
            raise ValueError(f"plan.profiles.{key}: bad fallback_dealer")
    c = cfg["closer"]
    for k in ("accept_min", "default_minus", "compete_minus"):
        if not _num(c.get(k)):
            raise ValueError(f"plan.closer.{k}: number required")
    if not (c["default_minus"] >= c["compete_minus"] >= c["accept_min"] >= 20):
        raise ValueError("plan.closer: need default_minus >= compete_minus >= accept_min >= 20")
    fz = c.get("freeze_at", 8)
    if not (type(fz) is int and 1 <= fz <= 9):
        raise ValueError("plan.closer.freeze_at: int 1..9")
    if not isinstance(c.get("endgame_hours", {}), dict) or not all(_num(v) for v in c.get("endgame_hours", {}).values()):
        raise ValueError("plan.closer.endgame_hours: day -> hours")
    for k, v in (("day_end_min_before_close", cfg.get("day_end_min_before_close")),
                 ("closer.endgame_min_before_close", c.get("endgame_min_before_close"))):
        if v is not None and not (_num(v) and 0 <= v <= 240):
            raise ValueError(f"plan.{k}: minutes 0..240 or absent")
    if type(cfg.get("endgame_buy_any", False)) is not bool:
        raise ValueError("plan.endgame_buy_any: true / false")
    if not _num(cfg["resupply_min"]) or cfg["resupply_min"] < 0:
        raise ValueError("plan.resupply_min: number >= 0")
    if not all(type(v) is int and v >= 0 for v in cfg["dup_min_price"].values()):
        raise ValueError("plan.dup_min_price: set -> int")
    if cfg["days_sign"] not in (None, 1, -1):
        raise ValueError("plan.days_sign: null, 1 or -1")
    if not all(_num(v) for v in cfg["day_end_hours"].values()):
        raise ValueError("plan.day_end_hours: day -> hours")
    if cfg["grant_lookahead_ticks"] < 0:
        raise ValueError("plan.grant_lookahead_ticks: >= 0")
    lg = cfg.get("lat_give_up")
    if lg is not None:
        if not (isinstance(lg, dict) and type(lg.get("set")) is str and type(lg.get("tick")) is int
                and isinstance(lg.get("refs"), list) and isinstance(lg.get("bids", []), list)):
            raise ValueError("plan.lat_give_up: {set, tick, refs, bids}")
    return cfg  # type: ignore[return-value]


# -------------------------------------------------------------------------------------- world readers

def _cards(catalog: Mapping) -> dict:
    """ref -> card mapping (with "set" added) from catalog.sets[].cards[]."""
    out = {}
    for s in (catalog or {}).get("sets") or ():
        if not isinstance(s, Mapping):
            continue
        for c in s.get("cards") or ():
            if isinstance(c, Mapping) and type(c.get("id")) is str:
                d = dict(c)
                d["set"] = s.get("id")
                out[c["id"]] = d
    return out


def page_refs(world, set_id: str) -> list:
    """Page cards of a set (catalog page == True), in catalog order."""
    return [r for r, c in _cards(world.catalog).items() if c.get("set") == set_id and c.get("page") is True]


def held_counts(me: Mapping) -> Counter:
    cnt: Counter = Counter()
    for a in (me or {}).get("assets") or ():
        if isinstance(a, Mapping) and a.get("kind") == "card" and type(a.get("ref")) is str:
            cnt[a["ref"]] += 1
    return cnt


def _want_ref(o: Mapping) -> Optional[str]:
    w = o.get("want") or {}
    if not isinstance(w, Mapping):
        return None
    refs = [c for c in (w.get("cards") or ()) if type(c) is str]
    refs += [t[5:] for t in (w.get("types") or ()) if type(t) is str and t.startswith("card:")]
    return refs[0] if len(refs) == 1 else None


def _give_cash(o: Mapping) -> int:
    g = o.get("give") or {}
    c = g.get("cash") if isinstance(g, Mapping) else None
    return c if type(c) is int else 0


def _give_refs(o: Mapping) -> list:
    g = o.get("give") or {}
    if not isinstance(g, Mapping):
        return []
    return [a.get("ref") for a in (g.get("assets") or ()) if isinstance(a, Mapping) and type(a.get("ref")) is str]


def own_bids(world) -> dict:
    """ref -> highest price of our open bids (maker t18, give cash, want one card)."""
    out: dict = {}
    for o in world.my_offers or ():
        if not isinstance(o, Mapping) or o.get("status") not in OPEN_STATUSES:
            continue
        ref = _want_ref(o)
        p = _give_cash(o)
        if ref and p > 0 and not _give_refs(o):
            out[ref] = max(out.get(ref, 0), p)
    return out


def buy_threads(world) -> set:
    """refs with an open dealer buy thread that has a standing offer."""
    out = set()
    for t in (world.threads or {}).values():
        if not isinstance(t, Mapping) or t.get("status") in CLOSED_THREAD:
            continue
        topic = t.get("topic") or {}
        buy = topic.get("buy") if isinstance(topic, Mapping) else None
        ref = buy.get("card") if isinstance(buy, Mapping) else None
        if type(ref) is str and t.get("standing_offers"):
            out.add(ref)
    return out


def _all_board_offers(world) -> list:
    seen, out = set(), []
    boards = list((world.boards or {}).values()) + [world.board or ()]
    for b in boards:
        for o in b or ():
            if isinstance(o, Mapping) and o.get("id") not in seen:
                seen.add(o.get("id"))
                out.append(o)
    return out


def _is_ours(world, o: Mapping) -> bool:
    mine = {x.get("id") for x in world.my_offers or () if isinstance(x, Mapping)}
    return o.get("id") in mine or o.get("maker") in {TEAM, world.own_pseudonym} - {None}


def rival_bids(world) -> dict:
    """ref -> highest rival bid price on any board (open, not ours)."""
    out: dict = {}
    for o in _all_board_offers(world):
        if o.get("status", "open") not in OPEN_STATUSES or _is_ours(world, o):
            continue
        ref, p = _want_ref(o), _give_cash(o)
        if ref and p > 0 and not _give_refs(o):
            out[ref] = max(out.get(ref, 0), p)
    return out


def _sales_seen(world) -> Counter:
    cnt: Counter = Counter()
    for o in _all_board_offers(world):
        if _is_ours(world, o):
            continue
        for r in _give_refs(o):
            cnt[r] += 1
    for e in world.feed_new or ():
        if not isinstance(e, Mapping) or e.get("type") != "settlement":
            continue
        pl = e.get("payload") or {}
        if not isinstance(pl, Mapping) or pl.get("persona"):
            continue
        for it in pl.get("items") or ():
            if isinstance(it, Mapping) and type(it.get("ref")) is str:
                cnt[it["ref"]] += 1
    return cnt


def today(world) -> str:
    """clock.today; missing -> "default" (never guessed from t_hours: Sunday spans t 13.37-19.37 or 16.65-22.65)."""
    d = (world.clock or {}).get("today") if isinstance(world.clock, Mapping) else None
    if type(d) is str and d:
        return d
    return "default"


# Day end / endgame from the server's live schedule and the wall clock (night audit, Sun 4 Oct). While the clock runs
# the server re-projects the wall-anchored "day_closes" entry onto game hours every read (Sat snaps 170-1435:
# day_closes sun = t + wall hours to 15:00), so the triggers follow a late start, a clock jump (16.65 at 09:00) or a
# pause. clock.closes (wall) is the second source of the same close: t + (closes - now) / 3600 (1 game hour per wall
# hour while the clock runs); the earlier of the two wins. Fixed plan hours are only a fallback.
DAY_END_BEFORE_CLOSE_H = 5 / 60        # default day_end_min_before_close: dealer threads close 5 min before close
ENDGAME_BEFORE_CLOSE_H = 35 / 60       # default closer.endgame_min_before_close: closer endgame 35 min before close
STALLS_MIN_PERSONAS = 3                # a stall close = >= 3 personas disabled at the same hour (not one dealer's break)
NEVER = math.inf


def _live_schedule(world) -> Optional[Sequence]:
    """world.schedule["upcoming"] when the doors are open, the clock runs and the list is not empty; else None."""
    c = world.clock if isinstance(world.clock, Mapping) else {}
    sched = world.schedule if isinstance(world.schedule, Mapping) else {}
    up = sched.get("upcoming")
    if c.get("doors") != "open" or c.get("paused") is True or not isinstance(up, (list, tuple)) or not up:
        return None
    return up


def live_times(world) -> tuple:
    """-> (close_h, stalls_h) from the live schedule; None for what is not there.
    close_h: the earliest day_closes for today still ahead of t (else the next one, if clock.today is stale), capped
    by an end_round still ahead; a day_closes already behind t is a fired entry that lingers (Sat 09:29: "fri 4.0"
    still listed) and is ignored. stalls_h: earliest hour at which >= STALLS_MIN_PERSONAS persona entries say
    enabled: false (kept even when behind t: the stalls are then closed)."""
    up = _live_schedule(world)
    if up is None:
        return None, None
    day, t = today(world), world.t_hours if _num(world.t_hours) else 0.0
    mine, nxt, ends, off = [], [], [], Counter()
    for e in up:
        if not isinstance(e, Mapping) or not _num(e.get("at_hours")):
            continue
        at, pr = float(e["at_hours"]), e.get("params") if isinstance(e.get("params"), Mapping) else {}
        if e.get("action") == "day_closes" and at > t:
            (mine if pr.get("day") == day else nxt).append(at)
        elif e.get("action") == "end_round" and at > t:
            ends.append(at)
        elif e.get("action") == "persona" and pr.get("enabled") is False:
            off[at] += 1
    close = min(mine) if mine else min(nxt, default=None)
    if ends:
        close = min(ends) if close is None else min(close, min(ends))
    stalls = min([a for a, n in off.items() if n >= STALLS_MIN_PERSONAS], default=None)
    return close, stalls


def wall_close(world, now: Optional[float]) -> Optional[float]:
    """Game hour of today's close from clock.closes (wall, ISO with offset): t + (closes - now) / 3600. None when the
    doors are not open, the clock is paused, there is no `now`, or the close is not ahead (a past clock.closes while
    the doors are open is stale: Saturday's 23:00 on Sunday's first tick must never end the day)."""
    c = world.clock if isinstance(world.clock, Mapping) else {}
    s = c.get("closes")
    if not _num(now) or c.get("doors") != "open" or c.get("paused") is True or not isinstance(s, str)             or not _num(world.t_hours):
        return None
    try:
        end = datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None
    left = (end - float(now)) / 3600.0
    if not (0.0 < left <= 24.0):
        return None
    return float(world.t_hours) + left


def _minutes(x: Any, default_h: float) -> float:
    return x / 60.0 if _num(x) and 0 <= x <= 240 else default_h


def effective_plan(plan_cfg: Mapping, world, seen: Optional[Mapping] = None, now: Optional[float] = None) -> tuple:
    """-> (plan_cfg for this tick, seen). Today's day_end_hours / closer.endgame_hours derived every tick:
    close = min(live day_closes / end_round, wall close from clock.closes and `now`), stalls = the finale's stall close;
    day end = min(close, stalls) - day_end_min_before_close (5), endgame = close - closer.endgame_min_before_close (35).
    `seen` (held by the runner, per day) keeps the last close and the stalls hour once their entries have fired and
    left "upcoming" (the stalls close at 14:00 must keep the dealer day ended after 14:00).
    No close and nothing seen: schedule readable -> the plan's hours; cold start / paused -> no trigger (a stale
    plan hour after a clock jump would close every dealer thread at 11:38)."""
    seen = dict(seen or {})
    day = today(world)
    close, stalls = live_times(world)
    wc = wall_close(world, now)
    if wc is not None:
        close = wc if close is None else min(close, wc)
    prev = seen.get(day) or {}
    close = close if close is not None else prev.get("close")
    stalls = stalls if stalls is not None else prev.get("stalls")
    seen[day] = {"close": close, "stalls": stalls}
    de_h = _minutes(plan_cfg.get("day_end_min_before_close"), DAY_END_BEFORE_CLOSE_H)
    eg_h = _minutes((plan_cfg.get("closer") or {}).get("endgame_min_before_close"), ENDGAME_BEFORE_CLOSE_H)
    if close is None and stalls is None:
        if _live_schedule(world) is not None:
            return plan_cfg, seen                       # schedule read, no close in it: plan hours
        day_end = endgame = NEVER
    else:
        day_end = round(min(x for x in (close, stalls) if x is not None) - de_h, 4)
        eh0 = ((plan_cfg.get("closer") or {}).get("endgame_hours") or {}).get(day)
        endgame = round(close - eg_h, 4) if close is not None else (eh0 if _num(eh0) else NEVER)
    pc = dict(plan_cfg)
    pc["day_end_hours"] = dict(pc.get("day_end_hours") or {}, **{day: day_end})
    cl = dict(pc.get("closer") or {})
    keys = set(cl.get("endgame_hours") or {}) | {day, "*"} | ({world.reading} if isinstance(world.reading, str) else set())
    cl["endgame_hours"] = {k: endgame for k in keys}
    pc["closer"] = cl
    return pc, seen


def past_day_end(world, plan_cfg) -> bool:
    h = (plan_cfg.get("day_end_hours") or {}).get(today(world))
    return _num(h) and world.t_hours >= h


def endgame(world, plan_cfg) -> bool:
    eh = ((plan_cfg.get("closer") or {}).get("endgame_hours") or {}).get(today(world))
    return _num(eh) and world.t_hours >= eh


def profile_for(plan_cfg, ref: str, card: Mapping) -> Optional[Mapping]:
    prof = plan_cfg.get("profiles") or {}
    rar = card.get("rarity")
    for key in (ref, f"{card.get('set')}:{rar}", rar):
        if key in prof:
            return prof[key]
    return None


def need_limit(plan_cfg, ref: str, card: Mapping) -> Optional[int]:
    """Need cap from the profiles: the first profile's limit, raised to its fallback profile's limit (the next
    profile with another dealer, the fallback_dealer if set; same choice as dealers._pick_open_profile) when the
    first has a fallback. Each thread stays capped by its own profile's limit. Night audit: CHA rares from the
    Pícaros (<= 60) fall back to El Chato (finals 86-93): a 60 Need cap kept the Chato thread from ever opening."""
    first = profile_for(plan_cfg, ref, card)
    if not first:
        return None
    lim = int(first["limit"])
    if not (first.get("fallback_after") or first.get("fallback_dealer")):
        return lim
    prof = plan_cfg.get("profiles") or {}
    fb = first.get("fallback_dealer")
    for key in (ref, f"{card.get('set')}:{card.get('rarity')}", card.get("rarity")):
        p = prof.get(key)
        if isinstance(p, Mapping) and p is not first and p.get("dealer") != first.get("dealer")                 and (not isinstance(fb, str) or p.get("dealer") == fb) and _num(p.get("limit")):
            return max(lim, int(p["limit"]))
    return lim


# ------------------------------------------------------------------------------------------ closer_ref

def closer_ref(world, missing: Sequence[str], plan_cfg) -> str:
    """Closer choice: common without rival bids > more sales seen > more minted copies not ours > lowest number."""
    if not missing:
        raise ValueError("closer_ref: nothing missing")
    cards = _cards(world.catalog)
    bids = rival_bids(world)
    sales = _sales_seen(world)
    held = held_counts(world.me)

    def key(ref: str):
        c = cards.get(ref, {})
        rank = RARITY_RANK.get(c.get("rarity"), 9)
        minted = c.get("minted") if type(c.get("minted")) is int else 0
        try:
            num = int(ref.rsplit("-", 1)[1])
        except (IndexError, ValueError):
            num = 999
        return (rank, ref in bids, -sales[ref], -(minted - held[ref]), num, ref)

    return min(missing, key=key)


# ---------------------------------------------------------------------------------------------- plan

def _floor(x: float) -> int:
    return int(math.floor(x + 1e-9))


def _dv_add(valuer, counts: Mapping, ref: str, packs) -> float:
    v = float(valuer.delta_add(counts, ref, packs))
    if not math.isfinite(v):
        raise ValueError(f"valuation of {ref} not finite")
    return v


def plan(world, valuer, plan_cfg, frozen: Mapping[str, str]) -> "tuple[list[Need], dict[str, str]]":
    """Needs for every released page set in plan_cfg.page_sets, and the updated frozen closers (set -> ref)."""
    new_frozen = dict(frozen or {})
    if {"me", "catalog"} & set(world.down or ()):
        return [], new_frozen
    try:
        held, packs = valuer.holdings(world.me)
        held = Counter(held)
    except Exception:
        return [], new_frozen
    cards = _cards(world.catalog)
    bids_own = own_bids(world)
    in_thread = buy_threads(world)
    rivals = rival_bids(world)
    sv = world.server_values or {}
    c_cfg = plan_cfg.get("closer") or {}
    freeze_at = c_cfg.get("freeze_at", 8)
    no_dealers = past_day_end(world, plan_cfg)
    needs: list = []

    # extra_needs: a card outside the pages bought from the dealer of its ref profile (Sat: SAL-11 epic from the
    # Pícaros, resold to Pilar in the Salamanca fever). Cap = min(max_price, floor(value - 1)); never if held.
    for e in plan_cfg.get("extra_needs") or ():
        try:
            ref = e["ref"]
            dealer = ((plan_cfg.get("profiles") or {}).get(ref) or {}).get("dealer")
            if no_dealers or held[ref] >= 1 or dealer not in DEALERS                     or ref.split("-", 1)[0] not in (world.released_sets or ()):
                continue                            # unreleased set: the card cannot be bought yet (CHA before 16.65)
            dv = min(_dv_add(valuer, held, ref, packs), float(sv.get(ref, math.inf)))
            cap = min(int(e["max_price"]), math.floor(dv - 1))
            if cap >= 1:
                needs.append(Need(set=ref.split("-", 1)[0], ref=ref, source=dealer, max_price=cap, closer=False))
        except Exception:
            continue                                # fail closed: no Need

    for set_id in plan_cfg.get("page_sets") or ():
        if set_id not in (world.released_sets or ()):
            continue
        refs = page_refs(world, set_id)
        if len(refs) < 2:
            continue
        unheld = [r for r in refs if held[r] < 1]
        if not unheld:
            new_frozen.pop(set_id, None)            # page complete
            continue
        try:
            closer = new_frozen.get(set_id)
            if closer not in unheld:                # never frozen, or we now hold it: choose again
                closer = None
                new_frozen.pop(set_id, None)
            if closer is None:
                free = [r for r in unheld if r not in bids_own and r not in in_thread] or unheld
                closer = closer_ref(world, free, plan_cfg)
            have = sum(1 for r in refs if r != closer and (held[r] >= 1 or r in bids_own or r in in_thread))
            if have >= freeze_at:
                new_frozen[set_id] = closer
            set_needs = []
            # dealer Needs: every unheld page card but the closer (they can never close the page: the closer is missing)
            if not no_dealers:
                for ref in unheld:
                    if ref == closer:
                        continue
                    card = cards.get(ref, {})
                    prof = profile_for(plan_cfg, ref, card)
                    if not prof:
                        continue
                    dv = min(_dv_add(valuer, held, ref, packs), float(sv.get(ref, math.inf)))
                    nl = need_limit(plan_cfg, ref, card)
                    cap = min(nl, int((plan_cfg.get("dealer_max") or {}).get(ref, nl)), _floor(dv - 1.0))
                    if cap >= 1:
                        set_needs.append(Need(set=set_id, ref=ref, source=prof["dealer"], max_price=cap, closer=False))
            # closer Need: valued as the card that completes the page
            hypo = Counter(held)
            for r in unheld:
                if r != closer:
                    hypo[r] += 1
            dv_close = _dv_add(valuer, hypo, closer, packs)
            if len(unheld) == 1:
                dv_close = min(dv_close, float(sv.get(closer, math.inf)))
            cap = _floor(dv_close - float(c_cfg["default_minus"]))
            compete = endgame(world, plan_cfg) or rivals.get(closer, 0) >= max(cap, bids_own.get(closer, 0), 1)
            if compete:
                cap = _floor(dv_close - float(c_cfg["compete_minus"]))
            ceiling = _floor(dv_close - float(c_cfg["accept_min"]))
            cap = min(max(cap, bids_own.get(closer, 0)), ceiling)   # never lower a standing bid; never past the ceiling
            set_needs.sort(key=lambda n: (-RARITY_RANK.get(cards.get(n.ref, {}).get("rarity"), 0), n.ref))
            if cap >= 1:
                set_needs.append(Need(set=set_id, ref=closer, source="team", max_price=cap, closer=True))
            needs.extend(set_needs)
        except Exception:
            continue                                # fail closed for this set: no Needs
    return needs, new_frozen


# ------------------------------------------------------------------------------------------ protection

def protect_sets(world, plan_cfg, journal_view) -> frozenset:
    """Protected page sets: plan_cfg.protect_sets + page_sets, minus LAT once given up (strategy J9, t205)."""
    out = set(plan_cfg.get("protect_sets") or ()) | set(plan_cfg.get("page_sets") or ())
    lg = plan_cfg.get("lat_give_up")
    if not lg or lg.get("set") not in out:
        return frozenset(out)
    if "me" in (world.down or ()) or "me/offers" in (world.down or ()) or type(world.tick) is not int:
        return frozenset(out)                       # unknown -> keep protected
    if world.tick < lg["tick"]:
        return frozenset(out)
    held = held_counts(world.me)
    jv = journal_view if isinstance(journal_view, Mapping) else {}
    pending = jv.get("pending_in") or {}
    filled = set(jv.get("filled_offers") or ())
    alive = any(held[r] >= 1 or (pending.get(r, 0) if isinstance(pending, Mapping) else 0) >= 1
                for r in lg.get("refs") or ())
    alive = alive or bool(filled & set(lg.get("bids") or ()))
    open_ids = {o.get("id") for o in world.my_offers or () if isinstance(o, Mapping)
                and o.get("status") in OPEN_STATUSES}
    alive = alive or bool(open_ids & set(lg.get("bids") or ()))   # our bid still open: not dead yet
    if not alive:
        out.discard(lg["set"])
    return frozenset(out)


def spare_assets(world, protected: Iterable[str]) -> list:
    """(asset_id, ref) of card assets we can hand over (J5 sales, D1 swaps) without the last copy of a protected
    page card. Assets already listed in an open offer of ours are excluded. Pricing is the caller's job."""
    protected = set(protected)
    cards = _cards(world.catalog)
    listed = set()
    for o in world.my_offers or ():
        if isinstance(o, Mapping) and o.get("status") in OPEN_STATUSES:
            g = o.get("give") or {}
            for a in (g.get("assets") or ()) if isinstance(g, Mapping) else ():
                if isinstance(a, Mapping):
                    listed.add(a.get("id"))
    by_ref: dict = {}
    for a in (world.me or {}).get("assets") or ():
        if isinstance(a, Mapping) and a.get("kind") == "card" and type(a.get("ref")) is str and type(a.get("id")) is int:
            by_ref.setdefault(a["ref"], []).append(a["id"])
    out = []
    for ref, ids in sorted(by_ref.items()):
        c = cards.get(ref, {})
        keep = 1 if (c.get("set") in protected and c.get("page") is True) else 0
        free_ids = [i for i in sorted(ids) if i not in listed]
        for i in free_ids[keep:]:                   # strict: the kept copy must be an unlisted one
            out.append((i, ref))
    return out
