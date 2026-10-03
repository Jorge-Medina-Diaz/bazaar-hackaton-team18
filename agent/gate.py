"""M5 gate: the ONLY executor of writes (docs/harness-spec.md §2.6, §0, INV-02/03/07/08/14/15/16/22).

Gate.execute order: STOP -> idempotency -> sources -> fresh re-read -> guards.check -> prediction recompute
-> (dry / unarmed / paused: would) -> tick deadline -> WAL intent (fsync) -> exact one-use permit -> send
-> WAL result/unknown -> running Book = guards.apply(book, intent, outcome).

NOTES (M5, night build)
- Dependencies are resolved lazily and are injectable (extra keyword-only args with defaults, so the §2.6
  signature still works): guards=, talk=, valuation=. A missing module FAILS CLOSED: guards missing ->
  every execute is refused "G02.not_built:guards"; talk missing -> say/duel_say refused; valuation missing ->
  "G07.not_built". agent.transport missing -> nothing is ever sent ("G02.not_built:transport").
- Defence in depth: besides guards.check the Gate itself enforces STOP (own scan + transport.stop_active),
  doors/pause (G03a), tick deadline (G03b), the fresh clock tick (G03c), per-tick budgets (G04: accepts,
  listings+cancels, own open offers, own threads, 1 message per thread/duel), one buy path per ref (G15, new
  paths only), cash (G16, buys and bids), D2 rival-venue rule (venue known and open, owner not ours, owner not in
  the leaderboard top RIVAL_TOP_N, leaderboard known, predicted neg_lo >= RIVAL_VENUE_MIN_GAIN) and the swap
  hand-over asset being ours. These duplicate guards on purpose; a disagreement can only refuse more.
- Prediction recompute (G07, exact +-0.01 on neg_lo, neg_hi, cash, duel; ladder equal): guards.predict() if it
  ever exists; otherwise valuation.predict_* fed with guards.dv_add / guards.dv_rm (the SAME dv as G12, with the
  asset id for sells/swaps and projected-minus-the-given-card for swaps) and the venue's fee_bps/fee_per_card
  from World.venues (El Rastro defaults 500/1). Swaps: predict_swap (cards=2). A tactic that computes
  differently is refused with G07.trip: fail closed, fix the tactic or share the formula.
- Integration with the real M4a (checked by TestWithRealGuards): SOURCES key via guards.source_key()
  ("accept_venue", "accept_dealer"); guards.Counters is frozen, so the Gate replaces it; Book.packs holds pack
  TYPES (ints are mapped through me.assets); `fresh` for a team accept is {"tick": re-read clock tick,
  "offer": re-read offer}; for a dealer accept the thread, for duel_accept the duel (agent.talk shapes).
- Architecture test conflict to resolve in M17: REQUEST_FOR (spec'd in gate.py) must put the literal "text"
  key in the say/duel_say bodies, while INV-13's AST rule bans the literal "text" in gate.py. The Gate never
  READS a text field; the AST rule should allow it inside REQUEST_FOR.
- list_offer: the Gate converts args.expires_ticks (game ticks) to server units with contracts.expiry_units
  (D3) and REQUEST_FOR["list_offer"] reads the ALREADY CONVERTED value. Venue is always "rastro" (D2).
- Fresh re-read (step 4): team accept -> /api/me/offers when the offer is in World.offers_to_us, otherwise
  /api/venues/{args.venue}/offers (late input D2); dealer accept -> /api/threads/{tid}; duel_accept -> /api/duels;
  then /api/clock (tick must equal World.tick). The re-read uses transport._call("GET") (the transport has no
  priority-GET entry point yet: the reserved limiter token is not used; open issue).
- Counters are incremented on ok, unknown AND would (so a dry run respects the same per-tick budgets).
  Messages are recorded in Counters.msgs as "thread:<id>" / "duel:<id>".
- dealer_block on cooloff/persona_quota: until_tick from the response body when present, else the next game hour
  assuming 60 ticks per game hour (measured Friday: t159 = 2.65 h). Written in the result row as dealer_block.
- Foreign writer (begin_tick): explained = journal.own_objects(baseline) ∪ baseline ∪ any journal intent row
  whose shape matches (list_offer: give/want signature; open_thread: dealer; say: thread+price; duel_say:
  duel+price). Unexplained cash/asset changes (alarm + pause of buy tactics) and "an accept of ours" are NOT
  checked tonight (need settlement accounting from the feed / cards): open issue.
- reconcile: evidence from the World for list_offer/cancel/open_thread/say/duel_say/close_thread/open_pack;
  accept/duel_accept only "not landed" when the offer is still open >= 2 ticks later, otherwise left frozen and
  reported {"action": "pause", "tactic": ...} after 3 ticks. accepted_unsettled released at until_tick with
  landed=False/evidence "timeout" (no /api/cards check tonight: open issue). execute refuses until reconcile ran
  once in this process (INV-15: reconcile before writing).
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import math
import os
from contextlib import contextmanager
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional

from agent.contracts import (BUY_TACTICS, RASTRO, RIVAL_TOP_N, RIVAL_VENUE_MIN_GAIN, TEAM, Intent, Outcome,
                             Paths, Prediction, Verdict, World, domains_of, expiry_units, intent_id)
from agent.redact import redact

try:                                                    # M1; missing -> nothing is ever sent
    from agent import transport as _transport
except Exception:                                       # noqa: BLE001
    _transport = None

write_permit = getattr(_transport, "write_permit", None)
_FATAL: tuple = tuple(c for c in (getattr(_transport, "GateViolation", None), getattr(_transport, "StopActive", None))
                      if isinstance(c, type))

NO_DEADLINE_KINDS = frozenset({"cancel", "close_thread"})
FRESH_KINDS = frozenset({"accept", "duel_accept"})
TEXT_KINDS = frozenset({"say", "duel_say"})
DEALER_BLOCK_CODES = frozenset({"cooloff", "persona_quota"})
TICKS_PER_GAME_HOUR = 60
RESPONSE_MAX = 2048
PRED_TOL = 0.01
IN_FLIGHT_TICKS = 2              # M17: an own offer gone from me/offers stays booked this many ticks


# ------------------------------------------------------------------------------------------- requests

def _req_accept(a: Mapping, text: Optional[str]) -> tuple:
    body = {"assets": [a["give_asset"]]} if a.get("give_asset") is not None else {}
    return "POST", f"/api/offers/{int(a['offer_id'])}/accept", body


def _req_list_offer(a: Mapping, text: Optional[str]) -> tuple:
    side = a["side"]
    if side == "sell":
        give, want = {"assets": [int(a["asset_id"])]}, {"cash": int(a["price"])}
    elif side == "bid":
        give, want = {"cash": int(a["price"])}, {"cards": [str(a["ref"])]}
    elif side == "swap":
        give, want = {"assets": [int(a["asset_id"])]}, {"cards": [str(a["want_ref"])]}
    else:
        raise ValueError(f"list_offer side {side!r}")
    # expires_ticks here is ALREADY in server units (the Gate converts with expiry_units, D3)
    return "POST", "/api/offers", {"give": give, "want": want, "venue": RASTRO,
                                   "expires_in_ticks": int(a["expires_ticks"])}


def _req_cancel(a: Mapping, text: Optional[str]) -> tuple:
    return "DELETE", f"/api/offers/{int(a['offer_id'])}", None


def _req_open_thread(a: Mapping, text: Optional[str]) -> tuple:
    if a["side"] == "buy":
        topic = {"buy": {"card": str(a["ref"])}}
    else:
        topic = {"sell": {"assets": [int(x) for x in a["asset_ids"]]}}
    return "POST", "/api/threads", {"with": str(a["dealer"]), "topic": topic}


def _req_say(a: Mapping, text: Optional[str]) -> tuple:
    if type(text) is not str or not text:
        raise ValueError("say needs a rendered text")
    return "POST", f"/api/threads/{int(a['thread_id'])}/messages", {"text": text, "price": int(a["price"])}


def _req_close_thread(a: Mapping, text: Optional[str]) -> tuple:
    return "POST", f"/api/threads/{int(a['thread_id'])}/close", None


def _req_open_pack(a: Mapping, text: Optional[str]) -> tuple:
    return "POST", f"/api/packs/{int(a['asset_id'])}/open", None


def _req_duel_say(a: Mapping, text: Optional[str]) -> tuple:
    if type(text) is not str or not text:
        raise ValueError("duel_say needs a rendered text")
    p, d = int(a["price"]), a.get("days")
    if d is None:
        return "POST", f"/api/duels/{int(a['duel_id'])}/messages", {"text": text, "price": p}
    return "POST", f"/api/duels/{int(a['duel_id'])}/messages", {"text": text, "price": p, "days": int(d),
                                                                 "offer": {"price": p, "days": int(d)}}


def _req_duel_accept(a: Mapping, text: Optional[str]) -> tuple:
    return "POST", f"/api/duels/{int(a['duel_id'])}/accept", None


REQUEST_FOR: Mapping[str, Callable[[Mapping, Optional[str]], tuple]] = MappingProxyType({
    "accept": _req_accept, "list_offer": _req_list_offer, "cancel": _req_cancel,
    "open_thread": _req_open_thread, "say": _req_say, "close_thread": _req_close_thread,
    "open_pack": _req_open_pack, "duel_say": _req_duel_say, "duel_accept": _req_duel_accept})


def body_sha(body: Optional[Mapping]) -> str:
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


# ------------------------------------------------------------------------------------------- STOP

def _own_stop_scan(paths: Paths) -> Optional[str]:
    try:
        names = os.listdir(Path(paths.root))
    except OSError as e:
        return f"stop check failed ({e.__class__.__name__})"          # fail closed
    for n in sorted(names):
        low = n.lower()
        if low == "stop" or low.startswith("stop."):
            return n
    return None


def stop_reason(paths: Paths) -> Optional[str]:
    """STOP if either the transport's check or our own scan says so (belt and braces)."""
    fn = getattr(_transport, "stop_active", None)
    if fn is not None:
        try:
            r = fn(paths)
        except Exception as e:                                          # noqa: BLE001
            r = f"stop check failed ({e.__class__.__name__})"
        if r:
            return r
    return _own_stop_scan(paths)


def write_stop(reason: str, paths: Paths) -> None:
    """Create STOP in the repo root (Paths.root). An existing STOP keeps its text and gets the reason appended."""
    root = Path(paths.root)
    root.mkdir(parents=True, exist_ok=True)
    p = root / "STOP"
    line = (str(reason).replace("\n", " ")[:500] + "\n")
    if p.exists():
        with open(p, "a", encoding="utf-8") as f:
            f.write(line)
        return
    tmp = root / f".STOP.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


# ------------------------------------------------------------------------------------------- helpers

class _Refuse(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code, self.detail = code, detail


def _get(m: Any, k: str, default: Any = None) -> Any:
    return m.get(k, default) if isinstance(m, Mapping) else default


def _int(x: Any) -> Optional[int]:
    return x if type(x) is int else None


def _small(body: Any) -> Any:
    r = redact(body)
    try:
        raw = json.dumps(r, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return {"unserializable": True}
    if len(raw) <= RESPONSE_MAX:
        return r
    keep = {k: r[k] for k in ("id", "status", "error", "code", "offer_id", "thread_id") if isinstance(r, Mapping) and k in r}
    keep["truncated"] = len(raw)
    return keep


def _pred_dict(p: Prediction) -> dict:
    return dataclasses.asdict(p)


def _pred_close(a: Prediction, b: Prediction) -> bool:
    def near(x, y):
        return abs(float(x) - float(y)) <= PRED_TOL
    if a.ladder != b.ladder or not near(a.neg_lo, b.neg_lo) or not near(a.neg_hi, b.neg_hi) or not near(a.cash, b.cash):
        return False
    if (a.duel is None) != (b.duel is None):
        return False
    return a.duel is None or near(a.duel, b.duel)


def _assets(world: World) -> list:
    a = _get(world.me, "assets", ())
    return [x for x in a if isinstance(x, Mapping)] if isinstance(a, (list, tuple)) else []


def _asset(world: World, aid: Any) -> Optional[Mapping]:
    for x in _assets(world):
        if x.get("id") == aid:
            return x
    return None


def _offer_sig(o: Mapping) -> Optional[tuple]:
    """(refs given, cash given, refs wanted, cash wanted) of an offer as the server shows it."""
    try:
        give, want = o.get("give") or {}, o.get("want") or {}
        g_refs = sorted(str(a.get("ref")) for a in give.get("assets") or [])
        w_refs = sorted([str(c) for c in want.get("cards") or []] +
                        [str(t).split(":", 1)[-1] for t in want.get("types") or []] +
                        [str(a.get("ref")) for a in want.get("assets") or [] if isinstance(a, Mapping)])
        return (tuple(g_refs), int(give.get("cash") or 0), tuple(w_refs), int(want.get("cash") or 0))
    except Exception:                                                    # noqa: BLE001
        return None


def _intent_sig(args: Mapping) -> Optional[tuple]:
    side = args.get("side")
    if side == "sell":
        return ((str(args.get("ref")),), 0, (), int(args.get("price") or 0))
    if side == "bid":
        return ((), int(args.get("price") or 0), (str(args.get("ref")),), 0)
    if side == "swap":
        return ((str(args.get("ref")),), 0, (str(args.get("want_ref")),), 0)
    return None


def _read_json(path: Path, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        return default


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _import(name: str) -> Any:
    try:
        return importlib.import_module(name)
    except Exception:                                                    # noqa: BLE001
        return None


# ------------------------------------------------------------------------------------------- the Gate

class Gate:
    def __init__(self, transport, journal, valuer, cfg, plan_cfg, paths: Paths, *, mode: str,
                 armed: Callable[[], frozenset], paused: Callable[[str], bool], clock,
                 guards: Any = None, talk: Any = None, valuation: Any = None):
        if mode not in ("live", "dry", "test"):
            raise ValueError(f"bad mode {mode!r}")
        self.transport, self.journal, self.valuer = transport, journal, valuer
        self.cfg, self.plan_cfg, self.paths = cfg, plan_cfg, paths
        self.mode, self._armed, self._paused, self.clock = mode, armed, paused, clock
        self._guards = guards if guards is not None else _import("agent.guards")
        self._talk = talk if talk is not None else _import("agent.talk")
        self._valuation = valuation if valuation is not None else _import("agent.valuation")
        self.book = None
        self.counters = None
        self._tick: Optional[int] = None
        self._blocked: set = set()            # domains blocked for this tick (odd fresh re-read)
        self._seen: dict = {}                 # iid -> status (this process)
        self._frozen_unknown: set = set()     # domains frozen by unknown outcomes in this process
        self._reconciled = False
        self._stop: Optional[str] = None
        self._frozen: Mapping = {}

    # ---------------------------------------------------------------- small utilities
    def _cfg(self, name: str, default: Any) -> Any:
        return getattr(self.cfg, name, default)

    def _j(self, kind: str, **fields) -> int:
        """Journal write; any failure -> STOP + re-raise (INV-15: a journal we cannot write means stop)."""
        try:
            return self.journal.write(kind, **fields)
        except Exception as e:
            self._fatal(f"journal:{e.__class__.__name__}:{e}")
            raise

    def _fatal(self, reason: str) -> None:
        self._stop = self._stop or reason
        try:
            write_stop(reason, self.paths)
        except Exception:                                                # noqa: BLE001
            pass

    def stopped(self) -> Optional[str]:
        return stop_reason(self.paths) or self._stop

    # ---------------------------------------------------------------- begin_tick
    def begin_tick(self, world: World) -> list:
        msgs: list = []
        self._tick = world.tick
        self._blocked = set()
        self.book = None
        g = self._guards
        if g is None:
            msgs.append("guards not built: every write refused")
            self.counters = None
            return msgs
        self.counters = g.Counters(tick=world.tick)
        baseline = self._baseline(world, msgs)
        if baseline is None:
            return msgs
        fr = _read_json(self.paths.frozen, None)
        if isinstance(fr, Mapping):
            self._frozen = dict(fr)
        try:
            self.book = g.build_book(world, self.journal, self.valuer, self.cfg, self.plan_cfg, self._frozen, baseline)
        except Exception as e:                                           # noqa: BLE001 - fail closed: no book
            self.book = None
            msgs.append(f"book failed: {e.__class__.__name__}: {e}")
        try:
            self.book = self._in_flight(world, self.book)
        except Exception as e:                                           # noqa: BLE001 - fail closed: no book
            self.book = None
            msgs.append(f"in-flight booking failed: {e.__class__.__name__}: {e}")
        foreign = self._foreign_writer(world, baseline)
        if foreign:
            reason = f"foreign_writer:{foreign}"
            self._fatal(reason)
            try:
                self.journal.write("stop", reason=reason, tick=world.tick)
            except Exception:                                            # noqa: BLE001
                pass
            msgs.append("STOP " + reason)
        return msgs

    def _in_flight(self, world: World, book: Any) -> Any:
        """M17 integration fix. An own offer that leaves /api/me/offers before its expiry may have been accepted
        and not settled yet (the server settles on the next tick; the fake hides accepted offers from me/offers).
        For IN_FLIGHT_TICKS keep it booked: a sale keeps its asset in listed_assets/listed (never re-listed while
        it is still ours), a bid keeps its cash out of cash_free and its buy path in paths. Only refuses more."""
        now_open = {}
        for o in world.my_offers or ():
            if isinstance(o, Mapping) and _get(o, "maker") == TEAM and _get(o, "status") in ("open", "queued")                     and _int(_get(o, "id")) is not None:
                now_open[o["id"]] = o
        flight = getattr(self, "_flight", {})
        prev = dict(getattr(self, "_prev_open", {}))
        sent = getattr(self, "_sent_offers", {})
        open_assets = {_int(_get(a, "id")) for o in now_open.values()
                       for a in (_get(_get(o, "give", {}) or {}, "assets", ()) or ())}
        for key, o in sent.items():             # sent since the last snapshot: may already be accepted
            aids = [_int(_get(a, "id")) for a in (_get(o["give"], "assets", ()) or ())]
            if key in now_open or (aids and all(x in open_assets for x in aids)):
                continue
            if not aids and any(_get(x, "give", {}).get("cash") == o["give"]["cash"] and
                                tuple(_get(x, "want", {}).get("types") or ()) == tuple(o["want"]["types"])
                                for x in now_open.values()):
                continue
            prev[key] = dict(o, _unseen=True)
        self._sent_offers = {}
        # a thread offer of ours that left me/offers while a newer own offer is open in the SAME thread was
        # superseded by our counter (the server cancels it), not accepted: never book it (live Sat: each step of
        # a Pícaros haggle took its price out of cash_free, 303 cash -> cash_free 4, so G16 refused the accept)
        open_threads = {_get(o, "thread") for o in now_open.values() if _get(o, "thread") is not None}
        for oid, o in prev.items():
            exp = _int(_get(o, "expires_tick"))
            if _get(o, "thread") is not None and _get(o, "thread") in open_threads:
                continue
            if oid not in now_open and (exp is None or exp >= world.tick):
                flight[oid] = (o, world.tick + IN_FLIGHT_TICKS)
        flight = {k: v for k, v in flight.items() if v[1] >= world.tick and k not in now_open
                  and not (_get(v[0], "thread") is not None and _get(v[0], "thread") in open_threads)}
        self._flight, self._prev_open = flight, now_open
        if book is None or not flight:
            return book
        held_ids = {a.get("id") for a in _assets(world) if isinstance(a, Mapping)}
        listed, la = dict(book.listed), set(book.listed_assets)
        paths, cash_free = dict(book.paths), book.cash_free
        for o, _until in flight.values():
            give, want = _get(o, "give", {}) or {}, _get(o, "want", {}) or {}
            for a in _get(give, "assets", ()) or ():
                aid = _int(_get(a, "id"))
                if aid is not None and aid in held_ids and aid not in la:
                    la.add(aid)
                    ref = _get(a, "ref")
                    if isinstance(ref, str):
                        listed[ref] = int(listed.get(ref, 0)) + 1
            cash = _int(_get(give, "cash"))
            types = [t for t in (_get(want, "types", ()) or ()) if isinstance(t, str) and t.startswith("card:")]
            cards = [c for c in (_get(want, "cards", ()) or ()) if isinstance(c, str)]
            if cash and (types or cards):
                ref = types[0][5:] if types else cards[0]
                paths[ref] = int(paths.get(ref, 0)) + 1
                # cash only for a bid we SAW open and then vanish (likely accepted, settling now); a bid sent
                # and never seen keeps only its buy path (no double count against a cash_free never debited)
                if isinstance(cash_free, (int, float)) and not _get(o, "_unseen", False):
                    cash_free = cash_free - cash
        return dataclasses.replace(book, listed=MappingProxyType(listed), listed_assets=frozenset(la),
                                   paths=MappingProxyType(paths), cash_free=cash_free)

    def _note_sent_offer(self, intent: Intent, world: World, out: Outcome) -> None:
        """M17: remember a listing sent this tick (shape from its args) for the in-flight booking above."""
        a = intent.args
        side, ref = a.get("side"), a.get("ref")
        exp = world.tick + int(a.get("expires_ticks") or 0)
        if side in ("sell", "swap") and _int(a.get("asset_id")) is not None:
            give = {"cash": 0, "assets": [{"id": a["asset_id"], "ref": ref}], "types": []}
            want = {"cash": a.get("price") or 0, "assets": [], "types": []}
        elif side == "bid":
            give = {"cash": int(a.get("price") or 0), "assets": [], "types": []}
            want = {"cash": 0, "assets": [], "types": [f"card:{ref}"]}
        else:
            return
        resp = out.response if isinstance(getattr(out, "response", None), Mapping) else {}
        oid = None
        for cand in (resp.get("offer_id"), resp.get("id"),
                     (resp.get("offer") or {}).get("id") if isinstance(resp.get("offer"), Mapping) else None):
            if _int(cand) is not None:
                oid = cand
                break
        key = oid if oid is not None else f"iid:{out.intent_id}"
        if not hasattr(self, "_sent_offers"):
            self._sent_offers = {}
        self._sent_offers[key] = {"id": key, "give": give, "want": want, "expires_tick": exp}

    def _baseline(self, world: World, msgs: list) -> Optional[Mapping]:
        p = self.paths.baseline
        if p.exists():
            b = _read_json(p, None)
            if not isinstance(b, Mapping):
                self._fatal("baseline unreadable")
                msgs.append("STOP baseline unreadable")
                return None
            return b
        try:
            had_intents = any(True for _ in self.journal.rows({"intent"}))
        except Exception:                                                # noqa: BLE001
            had_intents = True
        if had_intents:                    # a baseline is only taken before any write
            self._fatal("baseline missing after writes")
            msgs.append("STOP baseline missing after writes")
            return None
        bands = dict(_get(self.plan_cfg, "baseline_bands", {}) or {})
        offers = {str(o.get("id")): float(bands.get(str(o.get("id")), 2.0))
                  for o in world.my_offers if isinstance(o, Mapping) and _int(o.get("id")) is not None}
        threads, tmsgs, dmsgs = [], [], []
        for tid, th in (world.threads or {}).items():
            threads.append(int(tid))
            for m in _get(th, "messages", ()) or ():
                if _get(m, "sender") == TEAM and _int(_get(m, "id")) is not None:
                    tmsgs.append(m["id"])
        for d in world.duels:
            did = _get(d, "duel", _get(d, "id"))
            for m in _get(d, "messages", ()) or ():
                if _get(m, "from") == "you":
                    dmsgs.append([did, _get(m, "tick"), _get(m, "price"), _get(m, "days")])
        b = {"tick": world.tick, "offers": offers, "dealer_threads": threads, "thread_msgs": tmsgs,
             "duel_msgs": dmsgs, "accepts": []}
        _write_json(p, b)
        self._j("baseline", tick=world.tick, offers=sorted(offers), dealer_threads=threads,
                thread_msgs=len(tmsgs), duel_msgs=len(dmsgs))
        msgs.append("baseline written")
        return b

    def _foreign_writer(self, world: World, baseline: Mapping) -> Optional[str]:
        try:
            own = self.journal.own_objects(baseline)
        except Exception as e:                                           # noqa: BLE001
            return f"own_objects failed ({e.__class__.__name__})"
        offers = set(own.get("offers") or ()) | {int(k) for k in (baseline.get("offers") or {}) if str(k).isdigit()}
        threads = set(own.get("dealer_threads") or ()) | {int(x) for x in baseline.get("dealer_threads") or ()}
        tmsgs = set(own.get("thread_msgs") or ()) | {int(x) for x in baseline.get("thread_msgs") or ()}
        dmsgs = set(tuple(x) for x in own.get("duel_msgs") or ())
        dmsgs |= {tuple(x[:3]) for x in baseline.get("duel_msgs") or () if isinstance(x, (list, tuple))}
        try:
            intents = [r for r in self.journal.rows({"intent"})]
        except Exception as e:                                           # noqa: BLE001
            return f"journal unreadable ({e.__class__.__name__})"
        sigs, dealers, says, dsays = set(), set(), set(), set()
        for r in intents:
            ik, a = r.get("intent_kind"), r.get("args") or {}
            if ik == "list_offer":
                s = _intent_sig(a)
                if s:
                    sigs.add(s)
            elif ik == "open_thread":
                dealers.add(a.get("dealer"))
            elif ik == "say":
                says.add((a.get("thread_id"), a.get("price")))
            elif ik == "duel_say":
                dsays.add((a.get("duel_id"), a.get("price")))
        for o in world.my_offers:
            if _get(o, "maker") != TEAM:
                continue
            oid = _get(o, "id")
            if oid in offers or _offer_sig(o) in sigs:
                continue
            tho = _get(o, "thread")             # M17: the offer a `say` of ours creates inside a dealer thread
            if tho is not None:
                give, want = _get(o, "give", {}) or {}, _get(o, "want", {}) or {}
                price = _get(give, "cash") or _get(want, "cash")
                if (tho, price) in says or (_int(tho), price) in says:
                    continue
            return f"offer:{oid}"
        for tid, th in (world.threads or {}).items():
            if _get(th, "team", TEAM) != TEAM:
                continue
            if tid not in threads and _get(th, "with") not in dealers:
                return f"thread:{tid}"
            for m in _get(th, "messages", ()) or ():
                if _get(m, "sender") != TEAM or _get(m, "id") in tmsgs:
                    continue
                # M17: the real message has no top-level price (harvest): it is the cash of the offer it carries
                mo = _get(m, "offer", {}) or {}
                prices = {_get(m, "price"), _get(_get(mo, "give", {}) or {}, "cash"),
                          _get(_get(mo, "want", {}) or {}, "cash")} - {None, 0}
                if not any((tid, pr) in says for pr in prices):
                    return f"thread_msg:{tid}:{_get(m, 'id')}"
        for d in world.duels:
            did = _get(d, "duel", _get(d, "id"))
            for m in _get(d, "messages", ()) or ():
                if _get(m, "from") != "you":
                    continue
                key = (did, _get(m, "tick"), _get(m, "price"))
                if key not in dmsgs and (did, _get(m, "price")) not in dsays:
                    return f"duel_msg:{did}:{_get(m, 'tick')}"
        return None

    # ---------------------------------------------------------------- reconcile
    def reconcile(self, world: World) -> list:
        out: list = []
        try:
            pend = self.journal.pending()
        except Exception as e:                                           # noqa: BLE001
            self._fatal(f"journal pending failed: {e}")
            raise
        for row in pend:
            iid = row.get("id")
            if row.get("pending") == "accepted_unsettled":
                until = _int(row.get("until_tick"))
                if until is None or world.tick >= until:
                    self._j("reconciled", id=iid, landed=False, evidence="accepted_unsettled timeout",
                            tick=world.tick)
                    out.append({"id": iid, "landed": False, "evidence": "timeout"})
                continue
            if row.get("kind") != "intent":
                out.append({"id": iid, "action": "alarm", "why": f"pending {row.get('pending')}"})
                continue
            ik, a, t0 = row.get("intent_kind"), row.get("args") or {}, _int(row.get("tick"))
            age = world.tick - t0 if t0 is not None else 99
            try:
                landed, ev = self._evidence(ik, a, world, t0, age)
            except Exception as e:                                       # noqa: BLE001
                landed, ev = None, f"evidence error {e.__class__.__name__}"
            if landed is not None:
                self._j("reconciled", id=iid, landed=landed, evidence=ev, tick=world.tick)
                out.append({"id": iid, "landed": landed, "evidence": ev})
            elif age >= 3:
                out.append({"id": iid, "action": "pause", "tactic": row.get("tactic"), "why": ev})
        self._reconciled = True
        try:
            jd = set(self.journal.unknown_domains())
        except Exception:                                                # noqa: BLE001
            jd = None
        if jd is not None:
            self._frozen_unknown = set(jd)
            if self.book is not None:
                try:
                    self.book = dataclasses.replace(self.book, unknown_domains=frozenset(jd))
                except Exception:                                        # noqa: BLE001
                    pass
        return out

    def _evidence(self, ik: str, a: Mapping, world: World, t0: Optional[int], age: int) -> tuple:
        t0 = t0 if t0 is not None else -1
        if ik == "list_offer":
            want = _intent_sig(a)
            for o in world.my_offers:
                if _offer_sig(o) == want and (_int(_get(o, "created_tick")) or 0) >= t0:
                    return True, {"offer_id": _get(o, "id"), "own": {"offers": [_get(o, "id")]}}
            return (False, "no matching own offer") if age >= 2 else (None, "waiting")
        if ik == "cancel":
            oid = a.get("offer_id")
            live = [o for o in world.my_offers if _get(o, "id") == oid and _get(o, "status") in ("open", "queued")]
            if not live:
                return True, "offer no longer open"
            return (False, "offer still open") if age >= 2 else (None, "waiting")
        if ik == "open_thread":
            for tid, th in (world.threads or {}).items():
                if _get(th, "with") == a.get("dealer") and (_int(_get(th, "created_tick")) or 0) >= t0:
                    return True, {"thread_id": tid}
            return (False, "no thread") if age >= 2 else (None, "waiting")
        if ik == "say":
            th = (world.threads or {}).get(a.get("thread_id"))
            for m in _get(th, "messages", ()) or ():
                if _get(m, "sender") == TEAM and _get(m, "price") == a.get("price") and (_int(_get(m, "tick")) or 0) >= t0:
                    return True, {"msg_id": _get(m, "id")}
            return (False, "no message") if age >= 2 else (None, "waiting")
        if ik == "duel_say":
            for d in world.duels:
                if _get(d, "duel", _get(d, "id")) != a.get("duel_id"):
                    continue
                for m in _get(d, "messages", ()) or ():
                    if _get(m, "from") == "you" and _get(m, "price") == a.get("price") and (_int(_get(m, "tick")) or 0) >= t0:
                        return True, "duel message seen"
            return (False, "no duel message") if age >= 2 else (None, "waiting")
        if ik == "duel_accept":                 # audit Sat: without a rule an unknown accept paused duels for good
            for d in world.duels:
                if _get(d, "duel", _get(d, "id")) == a.get("duel_id"):
                    if _get(d, "status") != "live":
                        return True, f"duel {_get(d, 'status')}"
                    return (False, "duel still live") if age >= 2 else (None, "waiting")
            return True, "duel gone"
        if ik == "close_thread":
            if a.get("thread_id") not in (world.threads or {}):
                return True, "thread gone"
            return (False, "thread still open") if age >= 2 else (None, "waiting")
        if ik == "open_pack":
            if _asset(world, a.get("asset_id")) is None:
                return True, "pack gone"
            return (False, "pack still held") if age >= 2 else (None, "waiting")
        if ik == "accept":
            oid = a.get("offer_id")
            still = any(_get(o, "id") == oid for o in world.offers_to_us) or any(
                _get(o, "id") == oid for b in (world.boards or {}).values() for o in b) or any(
                _get(o, "id") == oid for o in world.board)
            if still and age >= 2:
                return False, "offer still open"
            return None, "accept outcome unverifiable from the World"
        return None, f"no evidence rule for {ik}"

    # ---------------------------------------------------------------- execute
    def execute(self, intent: Intent, world: World) -> Outcome:
        iid = intent_id(world.tick, intent)
        try:
            return self._execute(intent, world, iid)
        except _Refuse as r:
            return self._refused(intent, world, iid, r.code, r.detail)
        except _FATAL as e:                                              # GateViolation / StopActive: STOP, exit 2
            if e.__class__.__name__ != "StopActive":
                self._fatal(f"{e.__class__.__name__}: {e}")
            raise

    def _refused(self, intent: Intent, world: World, iid: str, code: str, detail: str = "",
                 status: str = "refused") -> Outcome:
        self._seen[iid] = status
        self._j("refused" if status == "refused" else "deferred", id=iid, tactic=intent.tactic,
                intent_kind=intent.kind, code=code, detail=str(detail)[:300],
                prediction=_pred_dict(intent.prediction), tick=world.tick)
        return Outcome(iid, status, code)

    def _execute(self, intent: Intent, world: World, iid: str) -> Outcome:
        k, a = intent.kind, intent.args
        g = self._guards
        # 1. STOP
        s = self.stopped()
        if s:
            raise _Refuse("G01.stop", s)
        if g is None:
            raise _Refuse("G02.not_built", "guards")
        if self.book is None or self.counters is None or self._tick != world.tick:
            raise _Refuse("G06.book", "begin_tick not run for this tick or book failed")
        if not self._reconciled:
            raise _Refuse("G05.not_reconciled")
        # 2. idempotency
        doms = domains_of(intent)
        if iid in self._seen:
            raise _Refuse("G05.repeat", self._seen[iid])
        try:
            prev = self.journal.result_for(iid)
        except Exception as e:                                           # noqa: BLE001
            self._fatal(f"journal result_for failed: {e}")
            raise
        if prev is not None:
            raise _Refuse("G05.done", str(prev.get("kind")))
        unk = doms & (frozenset(self.book.unknown_domains) | self._frozen_unknown)
        if unk:
            raise _Refuse("G05.unknown", ",".join(sorted(unk)))
        blk = doms & self._blocked
        if blk:
            raise _Refuse("G10.blocked", ",".join(sorted(blk)))
        # 3. sources
        src = getattr(g, "SOURCES", None)
        sk = getattr(g, "source_key", None)
        cands = ([sk(intent)] if callable(sk) else []) + [f"{k}:{a.get('source')}", k]
        skey = next((x for x in cands if isinstance(src, Mapping) and x in src), None)
        if skey is None:
            raise _Refuse("G06.source", "no SOURCES entry")
        down = frozenset(src[skey]) & frozenset(world.down)
        if k == "accept" and a.get("source") == "team" and a.get("venue") != RASTRO:
            down |= frozenset({"boards", "venues", "leaderboard"}) & frozenset(world.down)
        if down:
            raise _Refuse("G06.source:" + sorted(down)[0])
        # gate-level checks (defence in depth)
        self._gate_checks(intent, world)
        # text (say / duel_say)
        text = self._text(intent)
        # 4. fresh re-read
        fresh = None
        if k in FRESH_KINDS:
            fresh = self._fresh(intent, world, doms)
        # 5. guards + prediction
        now = self.clock.now()
        try:
            v = g.check(intent, world, self.book, self.valuer, self.cfg, self.counters, fresh=fresh, now=now)
        except Exception as e:                                           # noqa: BLE001 - fail closed
            v = Verdict(False, "G02.check_error", e.__class__.__name__)
        if not isinstance(v, Verdict) or not v.ok:
            raise _Refuse(getattr(v, "code", "G02.verdict"), getattr(v, "detail", ""))
        pred = self._predict(intent, world)
        if not _pred_close(pred, intent.prediction):
            self._j("trip", id=iid, tactic=intent.tactic, intent_kind=k, mine=_pred_dict(pred),
                    theirs=_pred_dict(intent.prediction), tick=world.tick)
            raise _Refuse("G07.trip", f"recomputed {pred.neg_lo:.3f}/{pred.cash} vs {intent.prediction.neg_lo:.3f}/"
                                      f"{intent.prediction.cash}")
        if k == "accept" and a.get("source") == "team" and a.get("venue") != RASTRO:
            gain = float(self._cfg("RIVAL_VENUE_MIN_GAIN", RIVAL_VENUE_MIN_GAIN))
            if pred.neg_lo < gain:
                raise _Refuse("D2.gain", f"{pred.neg_lo:.2f} < {gain}")
        # request (built before any WAL row so a bad request is a clean refusal)
        a2 = dict(a)
        if k == "list_offer":
            try:
                a2["expires_ticks"] = expiry_units(int(a["expires_ticks"]), world.tick_seconds)
            except ValueError as e:
                raise _Refuse("G22.expiry", str(e))
        try:
            method, path, body = REQUEST_FOR[k](a2, text)
            sha = body_sha(body)
        except Exception as e:                                           # noqa: BLE001
            raise _Refuse("G02.request", f"{e.__class__.__name__}: {e}")
        # 7. dry / unarmed / paused -> would
        # manual is armed like any tactic: the runner's armed_now() adds it only with "core" green in live and
        # leaves it out for a `do` order sent without --live (it was always armed here: a dry `do` went out live)
        armed = intent.tactic in frozenset(self._armed() or ())
        if self.mode != "live" or not armed or self._paused(intent.tactic):
            why = "mode" if self.mode != "live" else ("unarmed" if not armed else "paused")
            out = Outcome(iid, "would", why)
            self._seen[iid] = "would"
            self._j("would", id=iid, tactic=intent.tactic, intent_kind=k, code=why, detail="",
                    prediction=_pred_dict(intent.prediction), request=[method, path, sha], tick=world.tick)
            self._after(intent, world, out, doms)
            return out
        # 8. deadline
        if self.clock.now() > world.tick_deadline and k not in NO_DEADLINE_KINDS:
            return self._refused(intent, world, iid, "G03.late", "", status="deferred")
        if write_permit is None:
            raise _Refuse("G02.not_built", "transport")
        tmode = getattr(self.transport, "mode", "live")
        if tmode != "live":
            raise _Refuse("G02.mode_mismatch", str(tmode))
        s = self.stopped()
        if s:
            raise _Refuse("G01.stop", s)
        # 9. WAL intent (fsync)
        self._seen[iid] = "intent"
        self._j("intent", id=iid, tactic=intent.tactic, intent_kind=k, args=dict(a), reason=intent.reason,
                expected_effect=intent.expected_effect, prediction=_pred_dict(intent.prediction),
                guards=v.code, gate_mode=self.mode, request=[method, path, sha], tick=world.tick)
        # 10. exact permit + one send
        try:
            with write_permit(iid, method, path, body):
                r = self.transport.send(method, path, body)
        except _FATAL as e:                                              # GateViolation / StopActive
            name = e.__class__.__name__
            self._j("result", id=iid, status="refused", code=name, response={"error": str(e)[:200]},
                    tick=world.tick)
            self._seen[iid] = "refused"
            if name == "StopActive":
                raise
            self._fatal(f"{name}: {e}")
            raise
        except Exception as e:                                           # noqa: BLE001 - may have been sent
            r = None
            err = f"{e.__class__.__name__}: {e}"
        # 11. classify
        return self._classify(intent, world, iid, r, doms, err if r is None else None)

    def _classify(self, intent: Intent, world: World, iid: str, r: Any, doms: frozenset,
                  err: Optional[str]) -> Outcome:
        k, a = intent.kind, intent.args
        status = getattr(r, "status", None) if r is not None else None
        code = getattr(r, "code", None) if r is not None else None
        body = getattr(r, "body", None) if r is not None else None
        if status == "ok" and isinstance(body, Mapping):
            resp = _small(body)
            self._j("result", id=iid, status="ok", code=None, response=resp, tick=world.tick)
            if k == "accept":
                self._j("accepted_unsettled", id=iid, offer_id=a["offer_id"], ref=a["ref"], price=a["price"],
                        until_tick=world.tick + 2, tick=world.tick)
            out = Outcome(iid, "sent", None, resp)
            self._seen[iid] = "sent"
            self._after(intent, world, out, doms)
            return out
        if status == "deferred":
            self._j("result", id=iid, status="deferred", code=code, response=_small(body), tick=world.tick)
            self._seen[iid] = "deferred"
            return Outcome(iid, "deferred", code, _small(body))
        if status == "refused" and isinstance(code, str) and code:
            extra = {}
            if code in DEALER_BLOCK_CODES:
                dealer = self._dealer_of(intent, world)
                if dealer:
                    until = _int(_get(body, "until_tick"))
                    if until is None:
                        frac = world.t_hours - math.floor(world.t_hours)
                        until = world.tick + max(1, math.ceil((1.0 - frac) * TICKS_PER_GAME_HOUR))
                    extra["dealer_block"] = {dealer: until}
                    try:
                        db = dict(self.book.dealer_block)
                        db[dealer] = max(until, db.get(dealer, until))
                        self.book = dataclasses.replace(self.book, dealer_block=db)
                    except Exception:                                    # noqa: BLE001
                        pass
            self._j("result", id=iid, status="refused", code=code, response=_small(body), tick=world.tick, **extra)
            self._seen[iid] = "refused"
            return Outcome(iid, "refused", code, _small(body))
        # everything else is unknown: freeze its domains, never resend (INV-14)
        error = err or f"status={status} code={code}"
        self._j("unknown", id=iid, domains=sorted(doms), error=str(error)[:300], tick=world.tick)
        self._frozen_unknown |= set(doms)
        out = Outcome(iid, "unknown", code or "unknown", _small(body) if body is not None else None)
        self._seen[iid] = "unknown"
        self._after(intent, world, out, doms)
        return out

    def _after(self, intent: Intent, world: World, out: Outcome, doms: frozenset) -> None:
        """Counters and the running Book after would / sent / unknown (S-B2)."""
        c, a, k = self.counters, intent.args, intent.kind
        upd: dict = {}
        if k in ("accept", "duel_accept"):
            upd["accepts"] = c.accepts + 1
        elif k == "list_offer":
            upd["listings"], upd["offers_opened"] = c.listings + 1, c.offers_opened + 1
        elif k == "cancel":
            upd["listings"] = c.listings + 1
        elif k == "open_thread":
            upd["threads_opened"] = c.threads_opened + 1
        elif k == "say":
            upd["msgs"] = set(c.msgs) | {f"thread:{a['thread_id']}"}
        elif k == "duel_say":
            upd["msgs"] = set(c.msgs) | {f"duel:{a['duel_id']}"}
        if upd:                                    # guards.Counters is frozen: always replace
            self.counters = dataclasses.replace(c, **upd)
        if k == "list_offer" and out.status in ("ok", "sent", "unknown"):
            self._note_sent_offer(intent, world, out)
        try:
            nb = self._guards.apply(self.book, intent, out)
        except Exception as e:                                           # noqa: BLE001 - no trustworthy book
            self.book = None
            self._fatal_soft(f"apply failed: {e.__class__.__name__}")
            return
        if out.status == "unknown":
            try:
                nb = dataclasses.replace(nb, unknown_domains=frozenset(nb.unknown_domains) | doms)
            except Exception:                                            # noqa: BLE001
                pass
        self.book = nb

    def _fatal_soft(self, why: str) -> None:
        """Book lost mid-tick: refuse the rest of the tick (execute sees book None), journal an alarm."""
        try:
            self.journal.write("alarm", why=why, tick=self._tick)
        except Exception:                                                # noqa: BLE001
            pass

    # ---------------------------------------------------------------- pieces
    def _gate_checks(self, intent: Intent, world: World) -> None:
        k, a, b, c, L = intent.kind, intent.args, self.book, self.counters, world.limits
        clock = world.clock if isinstance(world.clock, Mapping) else {}
        if k not in NO_DEADLINE_KINDS:
            if clock.get("paused") is not False or clock.get("doors") != "open":
                raise _Refuse("G03.closed", f"paused={clock.get('paused')} doors={clock.get('doors')}")
        # G04 budgets (only our own objects count)
        if k in ("accept", "duel_accept") and c.accepts >= L.accepts:
            raise _Refuse("G04.accepts", f"{c.accepts}/{L.accepts}")
        if k in ("list_offer", "cancel"):
            cap = min(int(self._cfg("LISTINGS_PER_TICK", 6)), L.listings - 2)
            if c.listings >= cap:
                raise _Refuse("G04.listings", f"{c.listings}/{cap}")
        if k == "list_offer":
            mine = sum(1 for o in world.my_offers if _get(o, "maker") == TEAM and _get(o, "status") in ("open", "queued"))
            cap = L.open_offers - int(self._cfg("OPEN_OFFERS_MARGIN", 4))
            if mine + c.offers_opened >= cap:
                raise _Refuse("G04.open_offers", f"{mine}+{c.offers_opened}/{cap}")
        if k == "open_thread":
            mine = sum(1 for th in (world.threads or {}).values()
                       if _get(th, "team", TEAM) == TEAM and _get(th, "status") == "open")   # World.threads keeps every status
            cap = L.threads - int(self._cfg("THREADS_MARGIN", 1))
            if mine + c.threads_opened >= cap:
                raise _Refuse("G04.threads", f"{mine}+{c.threads_opened}/{cap}")
        if k == "say" and f"thread:{a['thread_id']}" in c.msgs:
            raise _Refuse("G04.messages")
        if k == "duel_say" and f"duel:{a['duel_id']}" in c.msgs:
            raise _Refuse("G04.messages")
        # G15: a NEW acquisition path for a ref needs paths[ref] == 0
        new_ref = None
        if k == "list_offer" and a["side"] == "bid":
            new_ref = a["ref"]
        elif k == "list_offer" and a["side"] == "swap":
            new_ref = a["want_ref"]
        elif k == "open_thread" and a["side"] == "buy":
            new_ref = a["ref"]
        elif k == "accept" and a["source"] == "team" and a["side"] in ("buy", "swap"):
            new_ref = a["ref"]
        if new_ref is not None and int((b.paths or {}).get(new_ref, 0)) > 0:
            raise _Refuse("G15.path", new_ref)
        # G16: cash for buys and bids (fee only when we accept)
        cost = None
        if k == "list_offer" and a["side"] == "bid":
            cost = a["price"]
        elif k == "accept" and a["side"] == "buy" and a["source"] == "team":
            cost = a["price"] + self._fee(world, a.get("venue", RASTRO), a["price"], 1)
        # (audit Sat) a dealer accept's cash is checked by talk G32 with its own thread reserve added back; here
        # cash_free already excludes that reserve, so it demanded 2x the price (SAL-11 at 159 refused, cash 303)
        elif k == "open_thread" and a["side"] == "buy":
            cost = a["limit"]
        if cost is not None and cost > b.cash_free:
            raise _Refuse("G16.cash", f"{cost} > {b.cash_free}")
        # swaps / sells: the asset handed over must be ours
        give = a.get("give_asset") if k == "accept" else (a.get("asset_id") if k == "list_offer" else None)
        if give is not None:
            asset = _asset(world, give)
            if asset is None:
                raise _Refuse("G13.not_ours", str(give))
            if k == "list_offer" and asset.get("ref") != a["ref"]:
                raise _Refuse("G13.ref", str(give))
        # D2: another team's venue
        if k == "accept" and a.get("source") == "team" and a.get("venue") != RASTRO:
            self._rival_venue_ok(a["venue"], world)   # M17: not for dealer accepts (venue = dealer id, M10)

    def _venue_row(self, world: World, vid: str) -> Optional[Mapping]:
        for v in world.venues:
            if _get(v, "id", _get(v, "venue")) == vid:
                return v
        return None

    def _rival_venue_ok(self, vid: str, world: World) -> None:
        row = self._venue_row(world, vid)
        if row is None or _get(row, "status") != "open":
            raise _Refuse("D2.venue", vid)
        owner = _get(row, "owner")
        if not isinstance(owner, str) or owner == TEAM:
            raise _Refuse("D2.owner", str(owner))
        lb = tuple(world.leaderboard or ())
        if not lb:
            raise _Refuse("D2.leaderboard_unknown")
        top = int(self._cfg("RIVAL_TOP_N", RIVAL_TOP_N))
        if owner in lb[:top]:
            raise _Refuse("D2.top", owner)

    def _fee(self, world: World, vid: str, price: int, cards: int) -> int:
        val = self._valuation
        row = self._venue_row(world, vid)
        if row is not None:
            bps, pc = _get(row, "fee_bps"), _get(row, "fee_per_card")
            if type(bps) is int and type(pc) is int:
                return val.fee(price, cards, bps, pc) if val else -(-(bps * price + 10000 * pc * cards) // 10000)
            raise _Refuse("D2.venue_fee", vid)
        if vid != RASTRO:
            raise _Refuse("D2.venue", vid)
        return val.fee(price, cards) if val else -(-(500 * price + 10000 * cards) // 10000)

    def _fee_params(self, world: World, vid: str) -> tuple:
        row = self._venue_row(world, vid)
        if row is not None:
            bps, pc = _get(row, "fee_bps"), _get(row, "fee_per_card")
            if type(bps) is int and type(pc) is int:
                return bps, pc
            raise _Refuse("D2.venue_fee", vid)
        if vid != RASTRO:
            raise _Refuse("D2.venue", vid)
        return 500, 1

    def _dealer_of(self, intent: Intent, world: World) -> Optional[str]:
        a = intent.args
        if intent.kind == "open_thread":
            return a["dealer"]
        tid = a.get("thread_id")
        if tid is not None:
            return _get((world.threads or {}).get(tid), "with")
        return None

    def _text(self, intent: Intent) -> Optional[str]:
        if intent.kind not in TEXT_KINDS:
            return None
        t = self._talk
        if t is None:
            raise _Refuse("G02.not_built", "talk")
        a = intent.args
        days = a.get("days") if intent.kind == "duel_say" else None
        try:
            text = t.render(a["template"], a["variant"], a["price"], days)
        except Exception as e:                                           # noqa: BLE001
            raise _Refuse("G60.render", e.__class__.__name__)
        try:
            v = t.firewall(text, a["price"], days)
        except Exception as e:                                           # noqa: BLE001
            v = Verdict(False, "G60.error", e.__class__.__name__)
        if not getattr(v, "ok", False):
            raise _Refuse(getattr(v, "code", "G60"), getattr(v, "detail", ""))
        return text

    def _block(self, doms: frozenset, code: str, detail: str = "") -> None:
        self._blocked |= set(doms)
        raise _Refuse(code, detail)

    def _read(self, path: str) -> Any:
        try:
            return self.transport._call("GET", path)
        except _FATAL:
            raise
        except Exception as e:                                           # noqa: BLE001
            raise _Refuse("G10.read", f"{path}: {e.__class__.__name__}")

    def _fresh(self, intent: Intent, world: World, doms: frozenset) -> Any:
        """Step 4: same-tick re-read. Any odd shape -> refused G10.shape and the domains blocked this tick."""
        k, a = intent.kind, intent.args
        try:
            if k == "accept" and a["source"] == "team":
                to_us = any(_get(o, "id") == a["offer_id"] for o in world.offers_to_us)
                path = "/api/me/offers" if to_us else f"/api/venues/{a['venue']}/offers"
                data = self._read(path)
                offers = _get(data, "offers")
                if not isinstance(offers, list):
                    self._block(doms, "G10.shape", f"{path}: offers not a list")
                found = [o for o in offers if isinstance(o, Mapping) and type(o.get("id")) is int
                         and o.get("id") == a["offer_id"]]
                if not found:
                    self._block(doms, "G10.gone", str(a["offer_id"]))
                fresh = found[0]
                if not isinstance(fresh.get("give"), Mapping) or not isinstance(fresh.get("want"), Mapping) \
                        or not isinstance(fresh.get("status"), str):
                    self._block(doms, "G10.shape", "offer fields")
                canon = getattr(self._guards, "canonical_offer", None)
                if canon is not None and canon(fresh) is None:
                    self._block(doms, "G10.shape", "not canonical")
                fp = getattr(self._guards, "fingerprint", None)
                if fp is None or fp(fresh) != a["fingerprint"]:
                    self._block(doms, "G10.fingerprint")
                if not to_us and fresh.get("venue") != a["venue"]:
                    self._block(doms, "G10.venue", str(fresh.get("venue")))
            elif k == "accept":                                          # dealer
                tid = a.get("thread_id")
                if tid is None:
                    self._block(doms, "G10.shape", "dealer accept without thread")
                fresh = self._read(f"/api/threads/{int(tid)}")
                if not isinstance(fresh, Mapping) or not isinstance(fresh.get("messages"), list):
                    self._block(doms, "G10.shape", "thread")
            else:                                                        # duel_accept
                data = self._read("/api/duels")
                duels = _get(data, "duels")
                if not isinstance(duels, list):
                    self._block(doms, "G10.shape", "duels not a list")
                found = [d for d in duels if isinstance(d, Mapping) and type(d.get("duel")) is int
                         and d.get("duel") == a["duel_id"]]
                if not found:
                    self._block(doms, "G10.gone", str(a["duel_id"]))
                fresh = found[0]
                dfp = getattr(self._guards, "duel_fingerprint", None)
                if dfp is None or dfp(fresh) != a["fingerprint"]:
                    self._block(doms, "G10.fingerprint")
            clock = self._read("/api/clock")
            t = _get(clock, "tick")
            if type(t) is not int:
                self._block(doms, "G10.shape", "clock")
            if t != world.tick:
                self._block(doms, "G10.stale", f"{t} != {world.tick}")
            if k == "accept" and a["source"] == "team":
                return {"tick": t, "offer": fresh}      # M4a shape: re-read clock tick + re-read offer
            return fresh
        except _Refuse:
            raise
        except _FATAL:
            raise
        except Exception as e:                                           # noqa: BLE001 - odd shape: refuse, no STOP
            self._blocked |= set(doms)
            raise _Refuse("G10.shape", e.__class__.__name__)

    # ---------------------------------------------------------------- prediction (G07)
    def _packs(self, world: World) -> tuple:
        """Book.packs as pack TYPES (M4a stores types; ids are mapped through me.assets)."""
        out = []
        for pid in self.book.packs or ():
            if isinstance(pid, str):
                out.append(pid)
                continue
            asset = _asset(world, pid)
            ref = _get(asset, "ref") or _get(asset, "type")
            if not isinstance(ref, str):
                raise _Refuse("G07.pack", str(pid))
            out.append(ref)
        return tuple(out)

    def _own_counts(self, ref: str) -> dict:
        """projected without our own dealer thread's standing copy of `ref` (same rule as agent.talk; M17)."""
        b = self.book
        c = dict(b.projected or {})
        if ref in set((b.thread_ref or {}).values()) and int(c.get(ref, 0)) > int((b.held or {}).get(ref, 0)):
            c[ref] = int(c[ref]) - 1
        return c

    def _dv_add(self, world: World, ref: str, counts: Optional[Mapping] = None) -> float:
        shared = getattr(self._guards, "dv_add", None)
        if callable(shared):                       # the same formula as G12 (one valuation, no false trips)
            return float(shared(world, self.book, self.valuer, ref, counts))
        d = self.valuer.delta_add(self.book.projected if counts is None else counts, ref, self._packs(world))
        sv = (world.server_values or {}).get(ref)
        return min(d, float(sv)) if isinstance(sv, (int, float)) and not isinstance(sv, bool) else d

    def _dv_rm(self, world: World, ref: str, asset_id: Optional[int] = None) -> float:
        shared = getattr(self._guards, "dv_rm", None)
        if callable(shared):
            return float(shared(world, self.book, self.valuer, ref, asset_id))
        d = self.valuer.delta_remove(self.book.held, ref, self._packs(world))
        yv = [x.get("your_value") for x in _assets(world) if x.get("ref") == ref
              and isinstance(x.get("your_value"), (int, float)) and not isinstance(x.get("your_value"), bool)]
        return max([d] + [float(y) for y in yv])

    def _duel(self, world: World, did: int) -> Mapping:
        for d in world.duels:
            if _get(d, "duel", _get(d, "id")) == did:
                return d
        raise _Refuse("G07.duel", str(did))

    def _predict(self, intent: Intent, world: World) -> Prediction:
        shared = getattr(self._guards, "predict", None)
        try:
            if callable(shared):
                return shared(intent, world, self.book, self.valuer, self.cfg)
            return self._predict_local(intent, world)
        except _Refuse:
            raise
        except Exception as e:                                           # noqa: BLE001
            raise _Refuse("G07.error", f"{e.__class__.__name__}: {e}")

    def _predict_local(self, intent: Intent, world: World) -> Prediction:
        val = self._valuation
        if val is None:
            raise _Refuse("G07.not_built", "valuation")
        k, a = intent.kind, intent.args
        cap = float(self._cfg("NEG_CAP", 50.0))
        if k in ("cancel", "close_thread", "open_thread", "open_pack"):
            return val.predict_none(intent.prediction.model if intent.prediction.model else "none")
        if k == "accept" and a["source"] == "team":
            bps, pc = self._fee_params(world, a["venue"])
            if a["side"] == "buy":
                return val.predict_team(self._dv_add(world, a["ref"]), a["price"], "buy", True, cap,
                                        fee_bps=bps, per_card=pc)
            if a["side"] == "sell":
                return val.predict_team(self._dv_rm(world, a["ref"], a["give_asset"]), a["price"], "sell", True,
                                        cap, fee_bps=bps, per_card=pc)
            give = _asset(world, a["give_asset"])
            counts = dict(self.book.projected)
            counts[give["ref"]] = counts.get(give["ref"], 0) - 1
            return val.predict_swap(self._dv_add(world, a["ref"], counts), self._dv_rm(world, give["ref"], give["id"]),
                                    True, cap, fee_bps=bps, per_card=pc)
        if k == "accept":                                                # dealer
            side = a["side"] if a["side"] in ("buy", "sell") else None
            if side is None:
                raise _Refuse("G07.side")
            dv = self._dv_add(world, a["ref"], self._own_counts(a["ref"])) if side == "buy"                 else self._dv_rm(world, a["ref"])
            return val.predict_dealer(dv, a["price"], side)
        if k == "list_offer":
            if a["side"] == "sell":
                return val.predict_team(self._dv_rm(world, a["ref"], a["asset_id"]), a["price"], "sell", False, cap)
            if a["side"] == "bid":
                return val.predict_team(self._dv_add(world, a["ref"]), a["price"], "buy", False, cap)
            counts = dict(self.book.projected)
            counts[a["ref"]] = counts.get(a["ref"], 0) - 1
            return val.predict_swap(self._dv_add(world, a["want_ref"], counts),
                                    self._dv_rm(world, a["ref"], a["asset_id"]), False, cap)
        if k == "say":
            th = (world.threads or {}).get(a["thread_id"])
            topic = _get(th, "topic", {})
            side = "buy" if isinstance(topic, Mapping) and "buy" in topic else "sell"
            dv = self._dv_add(world, a["ref"], self._own_counts(a["ref"])) if side == "buy"                 else self._dv_rm(world, a["ref"])
            return val.predict_dealer(dv, a["price"], side)
        if k in ("duel_say", "duel_accept"):
            d = self._duel(world, a["duel_id"])
            side = "buy" if _get(d, "role") == "buyer" else "sell"
            rounds = int(_get(d, "rounds", 0))
            if k == "duel_say":
                return val.predict_duel(_get(d, "your_limit"), a["price"], _get(d, "decay_per_round"),
                                        rounds + 1, side)
            ro = _get(d, "rival_offer")
            return val.predict_duel(_get(d, "your_limit"), _get(ro, "price"), _get(d, "decay_per_round"),
                                    rounds, side)
        raise _Refuse("G07.kind", k)
