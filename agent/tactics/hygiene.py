"""M9 hygiene: J0 (startup cancels), J1 (close buy threads, then open packs) and the G19 watch.

docs/harness-spec.md §2.7 (signatures), §4 "Vigilancia", INV-06, INV-09, INV-23; docs/strategy.md J0, J1.
Pure: reads World / Book / Valuer / Cfg / PlanCfg, returns Intents. The Gate re-checks every one (G23, G33, G40).
Every intent here only REDUCES exposure (cancel, close_thread) or opens a pack (G40), so a missing input makes the
watch do more closing, never less checking.

Design notes
- J0: `startup_cancels` from plan_cfg are cancelled only if still live in world.my_offers (the four LAT listings
  2463/2592/1652/2591 were cancelled at 01:30, so against the current state J0 finds nothing). startup() also runs
  the generic unprotected-sale check (G19, INV-06) when a Book is given, so any new unprotected listing is caught.
- Unprotected sales: free(ref) = held - listed - pending_out; while free < keep, cancel the ref's live sale/swap
  offer that expires first, recalculating (+1 per cancel). Own swaps (D1) hand over an asset, so they count as sales.
- Bids: own bids are in Book.projected, so dv_add is computed with that bid's own copy removed. A buy thread with a
  standing price is valued as the copy after held (_counts_for_thread: never a 2nd copy of a ref we hold 0 of). Inherited bids (id in plan_cfg.baseline_bands or Book.bid_band from the baseline)
  only use their band (2503/2504 -> 0) and are not treated as closer bids, per strategy (keep until t205).
  Harness closer bid = bid_band >= 20, frozen closer ref, or closes_page(counts, ref) (valuer error -> closer).
  With valuation unavailable the value checks on bids/swaps are skipped (they only cancel); buy threads with a
  standing price are closed instead (fail closed).
- Book.packs holds pack TYPES (guards M4a deviation from the contract comment): any entry counts as a pack in
  hand; pack asset ids to open come only from world.me assets (kind "pack").
- Delivery risk = Book.delivery_risk OR (local) pack in hand / grant with pack within grant_lookahead_ticks /
  schedule down or unreadable / Abuela thread open. Closer bids are cancelled and remembered in
  state["retired_closers"] (ref -> {offer_id, price, tick}); re-posting is the `closer` tactic's job (M11), hygiene
  never posts a bid (it is not a buy tactic).
- J1: packs are opened only when no buy thread is open (this tick closes them, the next tick opens: G40).
- Day end: plan_cfg["day_end_hours"][world.clock["today"]] (or key "default"); unknown day -> rule skipped.
- Foreign threads: recorded in state["foreign_threads"]; closed only if plan_cfg.get("close_foreign_threads") is
  True (E17 not measured yet; G33 decides whether we may close it at all).
- Not done: own sale price vs dv_rm (not in the G19 list), rival-venue boards (we never hold offers there).
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Optional

from agent.contracts import Intent, Prediction, make_intent

TACTIC = "hygiene"
LIVE_OFFER = frozenset({"open", "queued"})
TERMINAL_THREAD = frozenset({"deal", "closed", "expired", "cancelled", "canceled", "settled", "rejected", "done",
                             "walked"})        # live Sat: a dealer walk-out is status "walked" (G33 refused each tick)
DEFAULT_BAND = 2.0
CLOSER_BAND = 20.0
GRANT_ACTIONS = frozenset({"grant", "grant_all", "grant_team"})

P_UNPROTECTED = 100
P_RISK = 95
P_CASH = 90
P_THREAD_VALUE = 85
P_BAND = 80
P_DAY_END = 75
P_PACK = 70
P_FOREIGN = 10


# ------------------------------------------------------------------------------------------ helpers

def _pred_none() -> Prediction:
    try:
        from agent.valuation import predict_none  # M3; the Gate recomputes with the same function
        return predict_none()
    except Exception:
        return Prediction(0.0, 0.0, "0", 0, None, "none")


def _int(x: Any) -> Optional[int]:
    return x if type(x) is int else None


def _m(x: Any) -> Mapping:
    return x if isinstance(x, Mapping) else {}


def _seq(x: Any) -> tuple:
    return tuple(x) if isinstance(x, (list, tuple)) else ()


def _num(x: Any, default: float) -> float:
    return float(x) if type(x) in (int, float) and math.isfinite(x) else default


def _cfg(cfg: Any, name: str, default: float) -> float:
    return _num(getattr(cfg, name, default), default)


def _want_refs(want: Mapping) -> list:
    refs = [c for c in _seq(want.get("cards")) if isinstance(c, str)]
    for t in _seq(want.get("types")):
        if isinstance(t, str) and t.startswith("card:"):
            refs.append(t[5:])
    for a in _seq(want.get("assets")):
        if isinstance(a, Mapping) and isinstance(a.get("ref"), str):
            refs.append(a["ref"])
    return refs


def offer_view(o: Mapping) -> Optional[dict]:
    """{id, side, ref, asset_id, want_ref, price, expires} of one of OUR offers, or None if not understood.

    side: "sell" (asset for cash), "swap" (asset for card), "bid" (cash for card)."""
    oid = _int(o.get("id"))
    if oid is None:
        return None
    give, want = _m(o.get("give")), _m(o.get("want"))
    g_assets = [a for a in _seq(give.get("assets")) if isinstance(a, Mapping)]
    w_refs = _want_refs(want)
    g_cash = _int(give.get("cash")) or 0
    w_cash = _int(want.get("cash")) or 0
    exp = _int(o.get("expires_tick"))
    base = {"id": oid, "expires": exp, "status": o.get("status")}
    if g_assets:
        a = g_assets[0]
        ref = a.get("ref") if isinstance(a.get("ref"), str) else None
        if w_refs:
            return {**base, "side": "swap", "ref": ref, "asset_id": _int(a.get("id")), "want_ref": w_refs[0],
                    "price": 0}
        return {**base, "side": "sell", "ref": ref, "asset_id": _int(a.get("id")), "want_ref": None,
                "price": w_cash}
    if g_cash > 0 and w_refs:
        return {**base, "side": "bid", "ref": w_refs[0], "asset_id": None, "want_ref": w_refs[0], "price": g_cash}
    return {**base, "side": "other", "ref": None, "asset_id": None, "want_ref": None, "price": 0}


def _live_own(world) -> list:
    out = []
    for o in _seq(getattr(world, "my_offers", ())):
        if isinstance(o, Mapping) and o.get("status") in LIVE_OFFER:
            v = offer_view(o)
            if v is not None:
                out.append(v)
    return out


def _cancel(oid: int, ref: Optional[str], reason: str, priority: int) -> Intent:
    return make_intent("cancel", TACTIC, {"offer_id": oid, "ref": ref}, reason,
                       f"offer {oid} cancelled", _pred_none(), priority)


def _close(tid: int, ref: Optional[str], reason: str, priority: int) -> Intent:
    return make_intent("close_thread", TACTIC, {"thread_id": tid, "ref": ref}, reason,
                       f"thread {tid} closed", _pred_none(), priority)


def _open_pack(aid: int) -> Intent:
    return make_intent("open_pack", TACTIC, {"asset_id": aid}, "J1: open pack on arrival (no buy thread open)",
                       f"pack {aid} opened", _pred_none(), P_PACK)


def _key(it: Intent) -> tuple:
    a = it.args
    return (it.kind, a.get("offer_id"), a.get("thread_id"), a.get("asset_id"))


def _dedupe(intents: Iterable[Intent]) -> list:
    seen, out = set(), []
    for it in intents:
        k = _key(it)
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def _counts_without(book, ref: str) -> dict:
    """Book.projected with one copy of `ref` removed (our own bid / standing buy price), never below held."""
    c = {k: v for k, v in _m(book.projected).items()}
    held = int(_m(book.held).get(ref, 0) or 0)
    c[ref] = max(int(c.get(ref, 0) or 0) - 1, held)
    return c


def _counts_for_thread(book, ref: str) -> dict:
    """Book.projected with `ref` at held: our open buy thread stands for the next copy after the ones we hold.
    G15 allows one buy path per ref, so anything projected above held for `ref` is this thread. Removing only one
    copy (_counts_without) valued it as a 2nd copy whenever `ref` was projected twice (live t191: the thread offer
    also counted from my_offers, RET-09 91 -> 22.8; still possible with two open threads for one ref) and G19
    closed every dealer thread."""
    c = {k: v for k, v in _m(book.projected).items()}
    c[ref] = int(_m(book.held).get(ref, 0) or 0)
    return c


def _dv_add(world, book, valuer, ref: str, counts: Mapping) -> float:
    v = float(valuer.delta_add(counts, ref, book.packs))
    sv = _m(world.server_values).get(ref)
    if type(sv) in (int, float) and math.isfinite(sv):
        v = min(v, float(sv))
    if not math.isfinite(v):
        raise ValueError("non-finite value")
    return v


def _your_value(world, ref: str) -> float:
    best = 0.0
    for a in _seq(_m(world.me).get("assets")):
        if isinstance(a, Mapping) and a.get("ref") == ref:
            best = max(best, _num(a.get("your_value"), 0.0))
    return best


def _packs(world, book) -> list:
    ids = [p for p in _seq(getattr(book, "packs", ())) if type(p) is int] if book is not None else []
    for a in _seq(_m(world.me).get("assets")):
        if isinstance(a, Mapping) and a.get("kind") == "pack" and type(a.get("id")) is int and a["id"] not in ids:
            ids.append(a["id"])
    return ids


def _pack_in_hand(world, book) -> bool:
    """A pack asset in me.assets, or pack TYPES in Book.packs (guards.build_book keeps types, not ids)."""
    return bool(_packs(world, book)) or (book is not None and bool(getattr(book, "packs", ())))


def grant_soon(world, lookahead_ticks: int) -> bool:
    """A grant carrying a pack within `lookahead_ticks` (or already due). Unreadable schedule -> True (fail closed)."""
    if "schedule" in world.down:
        return True
    sched = world.schedule
    if not isinstance(sched, Mapping) or not isinstance(sched.get("upcoming"), (list, tuple)):
        return True
    ts = _num(world.tick_seconds, 60.0) or 60.0
    horizon = max(0, lookahead_ticks) * ts / 3600.0
    now = _num(world.t_hours, float("nan"))
    if not math.isfinite(now):
        return True
    for ev in sched["upcoming"]:
        if not isinstance(ev, Mapping) or ev.get("action") not in GRANT_ACTIONS:
            continue
        params = _m(ev.get("params"))
        if not _seq(params.get("packs")) and not params.get("pack"):
            continue
        at = _num(ev.get("at_hours"), float("nan"))
        if not math.isfinite(at) or at - now <= horizon + 1e-9:
            return True
    return False


def _thread_open(t: Mapping) -> bool:
    # Only "open" is open: G33 refuses close_thread on anything else, so a server-ended thread ("walked",
    # closed_reason final_offer_refused / persona_budget, ...) was re-proposed every tick (G33.not_open, t1455).
    return t.get("status") == "open"


def _thread_side(t: Mapping) -> tuple:
    """("buy"|"sell"|"?", ref or None, is_pack)."""
    topic = _m(t.get("topic"))
    if "buy" in topic:
        b = _m(topic.get("buy"))
        ref = b.get("card") if isinstance(b.get("card"), str) else None
        return "buy", ref, "pack" in b
    if "sell" in topic:
        return "sell", None, False
    return "?", None, False


def _our_standing_price(tid: int, t: Mapping, book) -> Optional[int]:
    prices = [p for p in _seq(_m(book.thread_prices).get(tid)) if type(p) is int] if book is not None else []
    if prices:
        return max(prices)
    last = None
    for msg in _seq(t.get("messages")):
        if not isinstance(msg, Mapping) or msg.get("sender") != "t18":
            continue
        p = _int(msg.get("price"))
        if p is None:
            p = _int(_m(_m(msg.get("offer")).get("give")).get("cash"))
        if p is not None and p > 0:
            last = p
    return last


def _open_threads(world) -> list:
    out = []
    for tid, t in _m(world.threads).items():
        if type(tid) is int and isinstance(t, Mapping) and _thread_open(t):
            out.append((tid, t))
    return out


def _day_end(world, plan_cfg) -> bool:
    ends = _m(plan_cfg.get("day_end_hours"))
    today = _m(world.clock).get("today")
    h = ends.get(today) if isinstance(today, str) else None
    if h is None:
        h = ends.get("default")
    h = _num(h, float("nan"))
    t = _num(world.t_hours, float("nan"))
    return math.isfinite(h) and math.isfinite(t) and t >= h


def delivery_risk(world, book, plan_cfg) -> bool:
    if book is not None and bool(getattr(book, "delivery_risk", False)):
        return True
    if _pack_in_hand(world, book):
        return True
    if grant_soon(world, int(plan_cfg.get("grant_lookahead_ticks", 3) or 3)):
        return True
    return any(t.get("with") == "abuela" for _, t in _open_threads(world))


# --------------------------------------------------------------------------------------------- watch

def unprotected_sales(world, book) -> list:
    """G19 / INV-06: cancel own sales (and swaps) of refs with free(ref) < keep(ref), earliest expiry first.
    Not on degraded data: with the catalog down build_book has no valuer and keeps every held ref (fail-closed
    keep=1), so the manual sole-copy SAL-11 listing was cancelled on the first tick after two Saturday restarts."""
    if book is None or "catalog" in (getattr(world, "down", None) or ()):
        return []
    by_ref: dict = {}
    for v in _live_own(world):
        if v["side"] in ("sell", "swap") and v["ref"]:
            by_ref.setdefault(v["ref"], []).append(v)
    out = []
    held, listed, pend, keep = _m(book.held), _m(book.listed), _m(book.pending_out), _m(book.keep)
    for ref in sorted(by_ref):
        free = int(held.get(ref, 0) or 0) - int(listed.get(ref, 0) or 0) - int(pend.get(ref, 0) or 0)
        k = int(keep.get(ref, 0) or 0)
        offers = sorted(by_ref[ref], key=lambda v: (v["expires"] if v["expires"] is not None else 10**9, v["id"]))
        for v in offers:
            if free >= k:
                break
            out.append(_cancel(v["id"], ref, f"G19: unprotected {v['side']} of {ref} (free {free} < keep {k})",
                               P_UNPROTECTED))
            free += 1
    return out


def _band(book, plan_cfg, oid: int) -> tuple:
    """(band, inherited)."""
    base = _m(plan_cfg.get("baseline_bands"))
    if str(oid) in base:
        return _num(base[str(oid)], DEFAULT_BAND), True
    b = _m(book.bid_band).get(oid)
    if type(b) in (int, float):
        return float(b), False
    return DEFAULT_BAND, False


def _is_closer(world, book, valuer, plan_cfg, v: dict, counts: Mapping) -> bool:
    band, inherited = _band(book, plan_cfg, v["id"])
    if inherited:
        return False
    if band >= CLOSER_BAND or v["ref"] in set(_m(book.frozen_closer).values()):
        return True
    try:
        return bool(valuer.closes_page(counts, v["ref"]))
    except Exception:
        return True


def bid_watch(world, book, valuer, cfg, plan_cfg, state: Optional[dict] = None) -> list:
    if book is None:
        return []
    in_thread = {o.get("id") for o in _seq(getattr(world, "my_offers", ())) if isinstance(o, Mapping)
                 and o.get("thread") is not None}               # dealer-thread prices: thread_watch owns them
    bids = [v for v in _live_own(world) if v["side"] == "bid" and v["id"] not in in_thread]
    out, cancelled = [], set()
    risk = delivery_risk(world, book, plan_cfg)
    cap = _cfg(cfg, "NEG_CAP", 50.0)
    closer_min = _cfg(cfg, "CLOSER_ACCEPT_MIN", CLOSER_BAND)
    val_ok = bool(getattr(book, "valuation_ok", False)) and valuer is not None
    retired = state.setdefault("retired_closers", {}) if state is not None else {}
    for v in bids:
        counts = _counts_without(book, v["ref"])
        closer = _is_closer(world, book, valuer, plan_cfg, v, counts) if valuer is not None else True
        if closer and risk:
            out.append(_cancel(v["id"], v["ref"], f"INV-23: closer bid on {v['ref']} withdrawn (delivery risk)",
                               P_RISK))
            cancelled.add(v["id"])
            retired[v["ref"]] = {"offer_id": v["id"], "price": v["price"], "tick": world.tick}
            continue
        if not val_ok:
            continue
        try:
            g = _dv_add(world, book, valuer, v["ref"], counts) - v["price"]
        except Exception:
            continue
        if closer:
            if min(g, cap) < closer_min:
                out.append(_cancel(v["id"], v["ref"], f"G19: closer bid on {v['ref']} out of band (gain {g:.1f})",
                                   P_BAND))
                cancelled.add(v["id"])
        else:
            band, _ = _band(book, plan_cfg, v["id"])
            if g < band:
                out.append(_cancel(v["id"], v["ref"], f"G19: bid on {v['ref']} out of band (gain {g:.1f} < {band})",
                                   P_BAND))
                cancelled.add(v["id"])
    cash_free = _num(getattr(book, "cash_free", 0), 0.0) + sum(v["price"] for v in bids if v["id"] in cancelled)
    for v in sorted(bids, key=lambda v: (-v["price"], v["id"])):
        if cash_free >= 0:
            break
        if v["id"] in cancelled:
            continue
        out.append(_cancel(v["id"], v["ref"], f"G19: bid on {v['ref']} without cash (cash_free {cash_free:.0f})",
                           P_CASH))
        cancelled.add(v["id"])
        cash_free += v["price"]
    return out


def swap_watch(world, book, valuer, cfg, plan_cfg) -> list:
    """D1: own swap whose value V(received) - V(given) fell below the default band -> cancel."""
    if book is None or valuer is None or not bool(getattr(book, "valuation_ok", False)):
        return []
    out = []
    for v in _live_own(world):
        if v["side"] != "swap" or not v["ref"] or not v["want_ref"]:
            continue
        try:
            # build_book already counts this swap's wanted copy in projected: value it as if not yet received
            gain = _dv_add(world, book, valuer, v["want_ref"], _counts_without(book, v["want_ref"]))
            lose = max(float(valuer.delta_remove(book.held, v["ref"], book.packs)), _your_value(world, v["ref"]))
            g = gain - lose
        except Exception:
            continue
        if not math.isfinite(g) or g < DEFAULT_BAND:
            out.append(_cancel(v["id"], v["ref"], f"G19: swap {v['ref']}->{v['want_ref']} out of value ({g:.1f})",
                               P_BAND))
    return out


def thread_watch(world, book, valuer, cfg, plan_cfg) -> list:
    """INV-23 / S-B1: buy threads closed with a pack in hand or a grant near, out of value, or at day end."""
    out = []
    pack_risk = _pack_in_hand(world, book) or grant_soon(world, int(plan_cfg.get("grant_lookahead_ticks", 3) or 3))
    day_end = _day_end(world, plan_cfg)
    margin = _cfg(cfg, "DEALER_MARGIN", 1.0)
    val_ok = book is not None and bool(getattr(book, "valuation_ok", False)) and valuer is not None
    for tid, t in _open_threads(world):
        side, ref, is_pack = _thread_side(t)
        if book is not None and ref is None:
            r = _m(book.thread_ref).get(tid)
            ref = r if isinstance(r, str) else None
        if side == "buy" or side == "?":
            if is_pack:
                out.append(_close(tid, ref, "INV-09: packs are never bought", P_RISK))
                continue
            if pack_risk:
                out.append(_close(tid, ref, "INV-23: buy thread closed (pack in hand or grant with pack near)",
                                  P_RISK))
                continue
        if day_end:
            out.append(_close(tid, ref, "day end: dealer threads closed", P_DAY_END))
            continue
        if side == "buy":
            p = _our_standing_price(tid, t, book)
            if p is None:
                continue
            if not val_ok or ref is None:
                out.append(_close(tid, ref, "fail closed: standing buy price with no valuation", P_THREAD_VALUE))
                continue
            try:
                dv = _dv_add(world, book, valuer, ref, _counts_for_thread(book, ref))
            except Exception:
                out.append(_close(tid, ref, "fail closed: valuation error on a standing buy price", P_THREAD_VALUE))
                continue
            if p > dv - margin:
                out.append(_close(tid, ref, f"G19: standing price {p} > dv_add {dv:.1f} - {margin}", P_THREAD_VALUE))
    return out


# ------------------------------------------------------------------------------------ public surface

def startup(world, book, plan_cfg) -> list:
    """J0: the configured startup cancels still live in my_offers, plus any unprotected sale (G19)."""
    out = []
    live = {v["id"]: v for v in _live_own(world)}
    for oid in _seq(plan_cfg.get("startup_cancels")):
        if type(oid) is int and oid in live:
            v = live[oid]
            out.append(_cancel(oid, v["ref"], "J0: startup cancel (plan_cfg.startup_cancels)", P_UNPROTECTED))
    out.extend(unprotected_sales(world, book))
    return _dedupe(out)


def watch(world, book, valuer, cfg, plan_cfg, state: Optional[dict] = None) -> list:
    """G19 + INV-23 + day-end thread closing."""
    out = []
    if valuer is not None:            # keep was computed without values otherwise (see unprotected_sales)
        out.extend(unprotected_sales(world, book))
    out.extend(bid_watch(world, book, valuer, cfg, plan_cfg, state))
    out.extend(swap_watch(world, book, valuer, cfg, plan_cfg))
    out.extend(thread_watch(world, book, valuer, cfg, plan_cfg))
    return _dedupe(out)


def propose(world, book, valuer, cfg, plan_cfg, state) -> list:
    """startup + watch + J1 (open packs once no buy thread is open) + foreign threads."""
    if state is None:
        state = {}
    out = startup(world, book, plan_cfg) + watch(world, book, valuer, cfg, plan_cfg, state)
    buy_open = any(_thread_side(t)[0] in ("buy", "?") for _, t in _open_threads(world))
    if not buy_open:
        listed = set(getattr(book, "listed_assets", ()) or ()) if book is not None else set()
        for aid in _packs(world, book):
            if aid not in listed:
                out.append(_open_pack(aid))
    seen = state.setdefault("foreign_threads", set())
    for tid in _seq(world.foreign_threads):
        if type(tid) is not int:
            continue
        seen.add(tid)
        if plan_cfg.get("close_foreign_threads") is True:
            out.append(_close(tid, None, "E17: foreign thread counts against our limit", P_FOREIGN))
    return _dedupe(out)
