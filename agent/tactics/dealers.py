"""M10 dealers: non-blocking haggling with la Abuela and El Chato (strategy J3/J12, knowledge D-01..D-10).

One step per tick and per thread: every call to `propose` looks at the World and the Book and emits at most one
intent per open dealer thread (say / accept / close_thread) plus at most one open_thread per dealer. Nothing here
waits, sleeps or talks to the network; the Gate (M5) checks and sends every intent (G30-G32, G60).

Rules implemented (acceptance of M10):
- Buy if the dealer's standing offer is <= our limit and either final or <= our next price; otherwise raise by the
  profile step. Never repeat a price (strictly monotone, never one already sent in the thread). Never counter a final:
  a final above the limit closes the thread without accepting. If we cannot raise any more (limit reached) -> close.
- Limit fixed at opening (min of profile limit, need.max_price, plan dealer_max, floor(dv_add - DEALER_MARGIN),
  cash_free) and it only goes down: every tick limit_t = min(opening limit, floor(dv_add - DEALER_MARGIN), need cap).
- No new threads while >= 4 live duels (E-M6), with an unopened pack (G14), with a dealer blocked (cooloff/quota),
  for the frozen closer card or a card that closes RET/CHA (INV-10), or more than one reopen per hour per (dealer, ref).
- PROBE mode (profile {"probe": true}, for new dealer levels): haggle with prices capped at the safe limit but never
  accept; close on a final or after `fallback_after` of our messages. Intents carry experiment "PROBE:<dealer>:<ref>".
- Fail closed: unknown opening limit, no profile, unreadable valuation or a missing helper module (agent.valuation /
  agent.guards not importable) -> no buy step (open threads are closed when the limit or value is unknown).

NOTES (night build, open issues for the lead)
- Sell threads (selling to dealers, J13 resupply rebuys are buys) are not handled: an open sell thread of ours is left
  alone (manual / hygiene).
- accept.venue for a dealer offer: the server gives venue null; the contract needs a VENUE_RE id, so we pass the dealer
  id ("abuela" / "chato"). The Gate must not apply the rival-venue rule (D2) or a fee to source == "dealer".
- dv_add follows §4 exactly (min(delta_add(book.projected, ref, packs), server_values[ref])) so the Gate's G07
  recomputation matches. If Book.projected already counts this thread's standing price (as §2.1 says), dv_add drops to
  a 2nd-copy value and the thread is closed/never accepted: M4a must exclude the thread's own ref from projected for
  G31/G32, and then this module should use the same counts. Flagged, not worked around.
- Journal rows: the intent-row field names are not frozen (M2 writes {iid, tactic, kind?, args}); rebuild() detects
  open_thread intents by their args shape (dealer, side, ref, asset_ids, limit). book.thread_limit wins when present.
- day_end_hours is not read here (its keys are not fixed); hygiene closes threads at day end, we only may open late.
- Grant lookahead (G30.grant_soon) is left to the Gate; this module does not read the schedule.
- Template for dealers other than abuela/chato/picaros (PROBE of level 3+): "chato_buy".
- Pícaros trick (live, Sat): their counter often gives another card at the asked price. Such an offer is never
  executable (offer_safety), so on a turn whose only dealer offer is a trick we counter with our next step and ignore
  its price; a trick marked final closes the thread (countering it made them walk: final_offer_refused). A correct
  offer expiring now is countered too unless it is final; fallback_after bounds the thread.
- A thread where the dealer spoke last with nothing executable (lapsed final, text only) closes after STALL_TICKS.
- fallback_after is checked after the accept branch: an executable offer at/under the limit is still taken.
- Profiles are looked up by ref, then "SET:rarity" (the keys config/plan.json uses), then bare rarity. RET-08/CHA-08
  "fallback_dealer" picks the next profile of that dealer after a walk/close within the hour (J3).
- "fallback_after" is read as ticks since the thread opened (J3 "10 ticks"), not "still at 32": the thread is closed
  at that age whatever the dealer's price.
- D1 swaps / D2 venues do not apply to dealers: dealer offers have venue null; no swaps are proposed to dealers.
- Sell threads to dealers and dealer swaps: not built (fail closed: never opened).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

from agent.contracts import TEAM, Intent, make_intent

TACTIC = "dealers"
PAGE_SETS_NO_DEALER_CLOSE = frozenset({"RET", "CHA"})
MAX_LIVE_DUELS_FOR_NEW_THREADS = 3          # >= 4 live duels -> no new threads
STALL_TICKS = 3                             # our message unanswered this long -> close
WALKS_PER_HOUR = 2                          # first thread + 1 reopen per hour per (dealer, ref)
REQUIRED_SOURCES = frozenset({"clock", "me", "me/offers", "me/threads", "threads"})
TEMPLATES = {"abuela": "abuela_buy", "chato": "chato_buy", "picaros": "picaros_buy"}
DEFAULT_TEMPLATE = "chato_buy"
PRIO_ACCEPT, PRIO_CLOSE, PRIO_SAY, PRIO_OPEN = 60, 50, 40, 10
_INF = float("inf")


# ------------------------------------------------------------------------------------------ pricing

def next_price(profile: Mapping, k: int, last: Optional[int], limit: int) -> int:
    """Our k-th price (k = number of prices we already sent): anchor + step*k, at least last+1, at most limit.

    The result may be <= last when the limit leaves no room: the caller then must not say it (close instead).
    """
    anchor, step = profile.get("anchor"), profile.get("step", 1)
    if type(anchor) is not int or type(step) is not int or anchor < 1 or step < 1:
        raise ValueError("profile needs int anchor >= 1 and int step >= 1")
    if type(k) is not int or k < 0 or type(limit) is not int:
        raise ValueError("k must be int >= 0 and limit int")
    if last is not None and type(last) is not int:
        raise ValueError("last must be int or None")
    p = anchor + step * k
    if last is not None:
        p = max(p, last + 1)
    return min(p, limit)


# -------------------------------------------------------------------------------------------- state

@dataclass
class DealerState:
    opened: dict = field(default_factory=dict)      # tid -> {"dealer", "ref", "limit", "tick", "probe"}
    walks: dict = field(default_factory=dict)       # (dealer, ref) -> [tick, ...] threads ended without a deal
    journal_ok: bool = True

    @staticmethod
    def rebuild(world: Any, journal: Any) -> "DealerState":
        st = DealerState()
        threads = _threads(world)
        for tid, t in threads.items():
            dealer, ref = t.get("with"), _topic_ref(t)
            if not isinstance(dealer, str) or ref is None:
                continue
            ct = t.get("created_tick") if type(t.get("created_tick")) is int else 0
            st.opened[tid] = {"dealer": dealer, "ref": ref, "limit": None, "tick": ct, "probe": False}
            status = t.get("status")
            if status not in ("open", "deal"):
                st.walks.setdefault((dealer, ref), []).append(_last_tick(t, ct))
        # opening limits from the journal: our open_thread intents, matched to the earliest later thread
        intents = []
        try:
            rows = journal.rows({"intent"}) if journal is not None else ()
            for row in rows:
                if row.get("tactic") != TACTIC:
                    continue
                a = row.get("args") or {}
                if not (isinstance(a, Mapping) and {"dealer", "side", "ref", "limit", "asset_ids"} <= set(a)):
                    continue
                if a.get("side") != "buy" or type(a.get("limit")) is not int:
                    continue
                tick = row.get("tick") if type(row.get("tick")) is int else -1
                probe = str(row.get("experiment") or "").startswith("PROBE")
                intents.append((tick, a["dealer"], a["ref"], a["limit"], probe))
        except Exception:
            st.journal_ok = False
            intents = []
        used = set()
        for tid in sorted(st.opened, key=lambda x: (st.opened[x]["tick"], x)):
            o = st.opened[tid]
            best = None
            for i, (tick, d, r, lim, probe) in enumerate(intents):
                if i in used or d != o["dealer"] or r != o["ref"] or tick > o["tick"]:
                    continue
                if best is None or tick > intents[best][0]:
                    best = i
            if best is not None:
                used.add(best)
                o["limit"], o["probe"] = intents[best][3], intents[best][4]
        return st

    def recent_walks(self, dealer: str, ref: str, tick: int, ticks_per_hour: int) -> int:
        return sum(1 for t in self.walks.get((dealer, ref), ()) if tick - t < ticks_per_hour)


# ------------------------------------------------------------------------------------------ helpers

def _threads(world) -> dict:
    out = {}
    for tid, t in dict(getattr(world, "threads", {}) or {}).items():
        if isinstance(t, Mapping):
            try:
                out[int(tid)] = t
            except (TypeError, ValueError):
                continue
    return out


def _topic_ref(t: Mapping) -> Optional[str]:
    try:
        ref = t["topic"]["buy"]["card"]
        return ref if isinstance(ref, str) and ref else None
    except (KeyError, TypeError):
        return None


def _last_tick(t: Mapping, default: int) -> int:
    ticks = [m.get("tick") for m in t.get("messages") or () if isinstance(m, Mapping) and type(m.get("tick")) is int]
    return max(ticks) if ticks else default


def _cash(side: Any) -> Optional[int]:
    if not isinstance(side, Mapping):
        return None
    c = side.get("cash")
    return c if type(c) is int else None


def _own_prices(t: Mapping) -> list:
    out = []
    for m in t.get("messages") or ():
        if not isinstance(m, Mapping) or m.get("sender") != TEAM:
            continue
        o = m.get("offer")
        if isinstance(o, Mapping) and o.get("maker") == TEAM:
            p = _cash(o.get("give"))
            if p is not None:
                out.append(p)
    return out


def _standing(t: Mapping, dealer: str, ref: str, tick: int) -> Optional[Mapping]:
    """Latest executable dealer sell offer of exactly `ref` (expires_tick >= tick + 1, same rule as G10/G32)."""
    try:
        from agent.offer_safety import executable_offer
    except Exception:
        return None
    topic = {"buy": {"card": ref}}
    cands = list(t.get("standing_offers") or ())
    cands += [m.get("offer") for m in t.get("messages") or () if isinstance(m, Mapping)]
    best = None
    for o in cands:
        if not isinstance(o, Mapping):
            continue
        if not executable_offer(o, topic, dealer=dealer, team=TEAM, tick=tick + 1, buying=True):
            continue
        key = (o.get("created_tick") if type(o.get("created_tick")) is int else -1, o["id"])
        if best is None or key > best[0]:
            best = (key, o)
    return best[1] if best else None


def _dealer_last_offer(t: Mapping, dealer: str) -> Optional[Mapping]:
    """The open offer of its own (of any shape) that the dealer's message carries when the dealer spoke last."""
    msgs = [m for m in t.get("messages") or () if isinstance(m, Mapping)]
    if not msgs or msgs[-1].get("sender") != dealer:
        return None
    o = msgs[-1].get("offer")
    return o if isinstance(o, Mapping) and o.get("maker") == dealer and o.get("status") == "open" else None


def _in_flight(t: Mapping) -> bool:
    for m in t.get("messages") or ():
        o = m.get("offer") if isinstance(m, Mapping) else None
        if isinstance(o, Mapping) and o.get("status") in ("queued", "accepted"):
            return True
    for o in t.get("standing_offers") or ():
        if isinstance(o, Mapping) and o.get("status") in ("queued", "accepted"):
            return True
    return False


def _last_sender(t: Mapping) -> tuple:
    msgs = [m for m in t.get("messages") or () if isinstance(m, Mapping)]
    if not msgs:
        return None, None
    m = msgs[-1]
    return m.get("sender"), (m.get("tick") if type(m.get("tick")) is int else None)


def _rarity(world, ref: str) -> Optional[str]:
    try:
        for s in world.catalog.get("sets") or ():
            for c in s.get("cards") or ():
                if c.get("id") == ref:
                    return c.get("rarity")
    except Exception:
        return None
    return None


def _set_of(ref: str) -> str:
    return ref.split("-", 1)[0]


def _profiles_for(plan_cfg: Mapping, world, ref: str) -> list:
    """Candidate profiles for ref, most specific first: by ref, then "SET:rarity" (config/plan.json), then rarity."""
    profs = (plan_cfg or {}).get("profiles") or {}
    rarity = _rarity(world, ref)
    keys = [ref] + ([f"{_set_of(ref)}:{rarity}", rarity] if rarity else [])
    out = []
    for key in keys:
        p = profs.get(key)
        if isinstance(p, Mapping) and isinstance(p.get("dealer"), str) and p not in out:
            out.append(p)
    return out


def _profile_for_thread(plan_cfg, world, ref: str, dealer: str) -> Optional[Mapping]:
    for p in _profiles_for(plan_cfg, world, ref):
        if p["dealer"] == dealer:
            return p
    return None


def _dv_add(world, book, valuer, ref: str) -> Optional[float]:
    try:
        counts = dict(book.projected or {})    # M17: without our own thread's standing copy (as agent.talk)
        if ref in set((book.thread_ref or {}).values()) and int(counts.get(ref, 0)) > int((book.held or {}).get(ref, 0)):
            counts[ref] = int(counts[ref]) - 1
        dv = float(valuer.delta_add(counts, ref, book.packs))
        sv = (world.server_values or {}).get(ref, _INF)
        dv = min(dv, float(sv))
        return dv if math.isfinite(dv) else None
    except Exception:
        return None


def _variant(template: str, k: int) -> int:
    """M17: cycle through the template's lines (talk.render refuses an index past the last line: the 5th say
    to Chato, who has 4 lines, was refused G60.render). Repeats are still impossible: every say has a new price."""
    try:
        from agent.talk import TEMPLATES as T, EGG_LINES
        n = len(T[template]) - int(EGG_LINES.get(template, 0))     # egg probe lines are hand-sent only
    except Exception:
        n = 1
    return k % max(1, n)


def _ticks_per_hour(world) -> int:
    ts = getattr(world, "tick_seconds", 0) or 0
    return max(1, int(round(3600.0 / ts))) if ts > 0 else 60


def _live_duels(world) -> int:
    return sum(1 for d in getattr(world, "duels", ()) or () if isinstance(d, Mapping) and d.get("status") == "live")


def _margin(cfg) -> float:
    m = getattr(cfg, "DEALER_MARGIN", 1.0)
    return float(m) if isinstance(m, (int, float)) and m >= 1.0 else 1.0


# ------------------------------------------------------------------------------------------ propose

def propose(world, book, valuer, cfg, plan_cfg, needs, state) -> list:
    """One step per open dealer thread + new buy threads for dealer needs. Pure: returns Intent[]."""
    try:
        from agent.offer_safety import offer_ok
        from agent.valuation import predict_dealer, predict_none
    except Exception:
        return []                                   # fail closed: no prediction model, no dealer step
    try:
        from agent.guards import fingerprint
    except Exception:
        fingerprint = None                          # accept impossible -> never accept (fail closed)

    if REQUIRED_SOURCES & set(getattr(world, "down", ()) or ()) or not book.valuation_ok:
        return []
    if state is None:
        state = DealerState()
    margin = _margin(cfg)
    needs_by_ref = {}
    for n in needs or ():
        if n.source != "team" and not n.closer:
            needs_by_ref.setdefault(n.ref, n)
    frozen = set((book.frozen_closer or {}).values())
    out: list = []
    tick = world.tick
    threads = _threads(world)

    def close(tid, ref, why):
        out.append(make_intent("close_thread", TACTIC, {"thread_id": tid, "ref": ref}, why,
                               "thread closed, no purchase", predict_none(), PRIO_CLOSE))

    # ---- step on our open buy threads
    open_dealers = set()
    for tid, t in sorted(threads.items()):
        if t.get("status") != "open":
            continue
        dealer = t.get("with")
        open_dealers.add(dealer)
        ref = _topic_ref(t)
        if ref is None or not isinstance(dealer, str):
            continue                                # sell thread or unknown topic: not ours to drive
        if book.packs or _in_flight(t):
            continue                                # G14 (hygiene closes) / acceptance pending
        info = state.opened.get(tid) or {}
        probe = bool(info.get("probe"))
        profile = _profile_for_thread(plan_cfg, world, ref, dealer)
        limit0 = book.thread_limit.get(tid) if type(book.thread_limit.get(tid)) is int else info.get("limit")
        if profile is None or type(limit0) is not int:
            close(tid, ref, "fail closed: no profile or unknown opening limit")
            continue
        probe = probe or bool(profile.get("probe"))
        dv = _dv_add(world, book, valuer, ref)
        if dv is None:
            close(tid, ref, "fail closed: value unknown")
            continue
        need = needs_by_ref.get(ref)
        if not probe and (need is None or ref in frozen):
            close(tid, ref, "need gone or frozen closer card")
            continue
        limit_t = min(limit0, math.floor(dv - margin))
        if need is not None:
            limit_t = min(limit_t, need.max_price)
        prices = sorted(set(_own_prices(t)) | set(book.thread_prices.get(tid, ()) or ()))
        last = prices[-1] if prices else None
        k = len(prices)
        opened_tick = info.get("tick", t.get("created_tick", tick))
        fb = profile.get("fallback_after")
        sender, sender_tick = _last_sender(t)
        standing = _standing(t, dealer, ref, tick)
        fb_due = not probe and type(fb) is int and fb > 0 and type(opened_tick) is int and tick - opened_tick >= fb
        # the dealer spoke last with an offer we cannot execute: a trick (fails offer_ok: another card, the Pícaros
        # trick) or our card at a price expiring now (lapsed). A lapsed final is the dealer's last word: wait/close.
        spoke = _dealer_last_offer(t, dealer) if standing is None else None
        trick = spoke is not None and not offer_ok(spoke, {"buy": {"card": ref}}, buying=True)
        lapsed = spoke is not None and not trick and spoke.get("final") is not True
        waiting = standing is None or (sender == TEAM and (standing.get("created_tick") or -1) < (sender_tick or 0))
        if fb_due and waiting:
            close(tid, ref, f"fallback_after {fb} ticks reached")
            continue
        if trick and spoke.get("final") is True:
            # countering a Pícaros "final" makes them walk (closed_reason final_offer_refused, a walk burnt): leave
            close(tid, ref, f"{dealer} offered a final that is not {ref}: close, never counter a final")
            continue
        if trick or lapsed:
            # counter with our next step, never accept it, never read its price
            nxt = next_price(profile, k, last, limit_t) if limit_t >= 1 and not probe else 0
            if nxt < 1 or (last is not None and nxt <= last) or nxt in prices:
                close(tid, ref, f"{'trick' if trick else 'lapsed'} offer and cannot raise (last {last}, limit {limit_t})")
                continue
            tpl = TEMPLATES.get(dealer, DEFAULT_TEMPLATE)
            what = f"an offer that is not {ref}" if trick else "an offer expiring now"
            out.append(make_intent(
                "say", TACTIC, {"thread_id": tid, "ref": ref, "price": nxt, "template": tpl, "variant": _variant(tpl, k)},
                f"{dealer} answered with {what}; our step {k} -> {nxt} (limit {limit_t})",
                f"standing bid {nxt} for {ref}", predict_dealer(dv, nxt, "buy"), PRIO_SAY))
            continue
        if waiting:
            if sender == TEAM:
                if sender_tick is not None and tick - sender_tick >= STALL_TICKS:
                    close(tid, ref, "dealer silent")
            else:
                # the dealer spoke last with nothing we can accept or counter (lapsed final, text only, nothing yet):
                # one conversation per dealer, so never wait forever
                quiet = sender_tick if sender_tick is not None else opened_tick
                if type(quiet) is int and tick - quiet >= STALL_TICKS:
                    close(tid, ref, "dealer spoke last with no executable offer")
            continue                                # wait for the dealer's answer
        s = standing["want"]["cash"]
        final = standing.get("final") is True
        exp = f"PROBE:{dealer}:{ref}" if probe else None
        if probe:
            if final or (type(fb) is int and k >= fb):
                close(tid, ref, "probe done")
                continue
        else:
            nxt0 = next_price(profile, k, last, limit_t) if limit_t >= 1 else 0
            accept_at = profile.get("accept_at")
            if s <= limit_t and (final or s <= nxt0 or (k == 0 and type(accept_at) is int and s <= accept_at)):
                if fingerprint is None:
                    continue                        # cannot fingerprint -> never accept
                out.append(make_intent(
                    "accept", TACTIC,
                    {"offer_id": standing["id"], "source": "dealer", "ref": ref, "side": "buy", "price": s,
                     "thread_id": tid, "give_asset": None, "fingerprint": fingerprint(standing),
                     "resupply": False, "venue": dealer},
                    f"{dealer} offers {ref} at {s} <= limit {limit_t} ({'final' if final else 'next ' + str(nxt0)})",
                    f"buy {ref} for {s}", predict_dealer(dv, s, "buy"), PRIO_ACCEPT))
                continue
            if fb_due:                              # after the accept: an offer at/under our limit is still taken
                close(tid, ref, f"fallback_after {fb} ticks reached")
                continue
            if final:
                close(tid, ref, f"final {s} above limit {limit_t}: never counter a final")
                continue
        nxt = next_price(profile, k, last, limit_t) if limit_t >= 1 else 0
        if nxt < 1 or (last is not None and nxt <= last) or nxt in prices or nxt >= s:
            close(tid, ref, f"cannot raise (last {last}, limit {limit_t}, standing {s})")
            continue
        out.append(make_intent(
            "say", TACTIC,
            {"thread_id": tid, "ref": ref, "price": nxt, "template": TEMPLATES.get(dealer, DEFAULT_TEMPLATE),
             "variant": _variant(TEMPLATES.get(dealer, DEFAULT_TEMPLATE), k)},
            f"{dealer} stands at {s}; our step {k} -> {nxt} (limit {limit_t})",
            f"standing bid {nxt} for {ref}", predict_dealer(dv, nxt, "buy"), PRIO_SAY, exp))

    # ---- open new buy threads
    if book.packs or _live_duels(world) > MAX_LIVE_DUELS_FOR_NEW_THREADS:
        return out
    open_count = sum(1 for t in threads.values() if t.get("status") == "open")
    max_threads = world.limits.threads - int(getattr(cfg, "THREADS_MARGIN", 1))
    unlocked = set((world.me or {}).get("unlocked") or ())
    tph = _ticks_per_hour(world)
    dealer_max = (plan_cfg or {}).get("dealer_max") or {}
    allow_close = frozenset(getattr(cfg, "ALLOW_DEALER_CLOSE", frozenset({"LAT"})))
    cash_free = book.cash_free
    candidates = [(n.ref, n) for n in needs_by_ref.values()]
    for ref, prof in _probe_targets(plan_cfg, needs_by_ref):
        candidates.append((ref, None))
    for ref, need in candidates:
        if open_count >= max_threads:
            break
        if ref in frozen or (book.paths or {}).get(ref, 0) != 0 or (book.projected or {}).get(ref, 0) > 0:
            continue
        set_id = _set_of(ref)
        try:
            closes = bool(valuer.closes_page(book.projected, ref))
        except Exception:
            continue
        if closes and (set_id in PAGE_SETS_NO_DEALER_CLOSE or set_id not in allow_close):
            continue
        profile = _pick_open_profile(plan_cfg, world, ref, state, tick, tph, need is None)
        if profile is None:
            continue
        dealer = profile["dealer"]
        if dealer in open_dealers or dealer not in unlocked or dealer in (book.thread_by_dealer or {}):
            continue
        if (book.dealer_block or {}).get(dealer, -1) >= tick:
            continue
        if state.recent_walks(dealer, ref, tick, tph) >= WALKS_PER_HOUR:
            continue
        dv = _dv_add(world, book, valuer, ref)
        if dv is None:
            continue
        caps = [profile.get("limit"), math.floor(dv - _margin(cfg)), cash_free]
        if need is not None:
            caps.append(need.max_price)
        if type(dealer_max.get(ref)) is int:
            caps.append(dealer_max[ref])
        if any(type(c) is not int for c in caps) or type(profile.get("anchor")) is not int:
            continue
        limit = min(caps)
        if limit < 1 or limit < profile["anchor"]:
            continue
        probe = bool(profile.get("probe"))
        out.append(make_intent(
            "open_thread", TACTIC,
            {"dealer": dealer, "side": "buy", "ref": ref, "asset_ids": (), "limit": limit},
            f"{'probe' if probe else 'need'} {ref} from {dealer}, limit {limit} (dv_add {dv:.1f})",
            f"thread with {dealer} for {ref}", predict_none(), PRIO_OPEN,
            f"PROBE:{dealer}:{ref}" if probe else None))
        open_dealers.add(dealer)
        open_count += 1
        cash_free -= limit
    return out


def _probe_targets(plan_cfg, needs_by_ref) -> Iterable:
    for key, p in ((plan_cfg or {}).get("profiles") or {}).items():
        if isinstance(p, Mapping) and p.get("probe") is True and "-" in str(key) and key not in needs_by_ref:
            yield key, p


def _pick_open_profile(plan_cfg, world, ref, state, tick, tph, probe_only) -> Optional[Mapping]:
    """Ref profile first; if its dealer walked away on this ref within the hour and it has fallback_after or
    fallback_dealer, use the next profile of the fallback dealer (J3: RET-08 from El Chato -> la Abuela)."""
    profs = _profiles_for(plan_cfg, world, ref)
    if probe_only:
        profs = [p for p in profs if p.get("probe") is True]
    if not profs:
        return None
    first = profs[0]
    has_fallback = first.get("fallback_after") or first.get("fallback_dealer")
    if not (has_fallback and state.recent_walks(first["dealer"], ref, tick, tph)):
        return first
    fb_dealer = first.get("fallback_dealer")
    for p in profs[1:]:
        if p["dealer"] != first["dealer"] and (not isinstance(fb_dealer, str) or p["dealer"] == fb_dealer):
            return p
    return first                    # no fallback profile: the same dealer again (WALKS_PER_HOUR still applies)
