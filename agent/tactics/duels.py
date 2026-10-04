"""M12 duels tactic: v0 corrected + slow ascent with a silent rival + accept only on the tick the rival spoke.

Strategy J7/J10 (docs/strategy.md), INV-12 (docs/harness-spec.md), facts U-01, U-02, U-07, U-10, U-12, U-13, K-06, K-07.
Pure: no network, no files, no clock. `view` reads one duel as the sensor gives it, `decide` picks one action for it,
`propose` turns the decisions of every live duel into Intents (the Gate re-checks everything with G50/G51).

Policy (decide):
- Never a price with less than `min_margin` (1 P) of surplus, plus the days worst case in two-issue duels; offers are
  monotone with our last offer read from the server; at most one message per duel per tick; nothing after deadline-1.
- Opening: anchor at L*anchor (buyer) / L/anchor (seller).
- Rival never spoke: slow ascent, free because rounds = min(nY, nR) = 0 (U-02): linear from the anchor to L-+margin at
  deadline-2, keeping the last 25 % of the way for the last 3 ticks (deadline-4..deadline-2).
- Rival spoke: v0 corrected. We concede one curve step (k = rival messages, BETA 1.6) only when the rival answered our
  last message (K-06 fix: never concede against silence); state is rebuilt from the server every tick (K-06, K-07).
  Near the deadline: one final offer toward the limit if the rival is outside it, and "provoke" messages if the rival
  is inside our limit but did not speak this tick (accept in the late window once it answers).
- Accept only if rival_offer.tick == tick (it already spent its message of the tick, U-10), tick <= deadline-1, the
  surplus holds with the days worst case, and the offer is good (>= our next step), firm (repeated) or late.
- Two issues (J10): nothing until your_days_weight is a number and days_meaning is present. days_sign (plan_cfg) known:
  we send our best days and value the rival's days as W(d) - max W. Unknown: surplus >= 1 + 10*|w| on every price.
- E8: on the first duel whose rival speaks, stay silent 2 ticks after its first message (accepts still allowed).
- E16: two rival messages in one tick, or a settled price different from the one read -> duel accepts paused.
- Accept budget: at most world.limits.accepts duel_accept intents per tick, nearest deadline first.

NOTES (M12, night build) / open issues
- duel_fingerprint and predict_duel come from agent.guards (M4a) and agent.valuation (M3) (both present; a test checks
  the fingerprint matches the local copy). predict_duel takes side "buy"/"sell", mapped from the duel role.
- Duel length T is not in the duel object: inferred from decay (0.06 -> 16 ticks, else 12, U-12) and the first message
  tick; params["T"] overrides.
- W(d) = days_sign * |your_days_weight| * d is an assumption (U-13: the weight was null in practice); the unit of
  your_days_weight is unknown. No logrolling on days yet (we always send our best days when the sign is known).
- E16 settled-price check needs the done duels (World.duels holds live ones only): `e16_settled(state, done)` is
  provided for the runner/calibrator to call; it is not wired here.
- The late-window second pass (re-read mid-tick, then accept) is the runner's job (M15): calling propose again with the
  fresh world gives the accept, since decide sees rival_offer.tick == tick.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from agent.contracts import Prediction, make_intent

DAYS_MAX = 10
BETA = 1.6

DEFAULTS: Mapping[str, Any] = {
    "anchor": 0.60,        # buyer opens at L*anchor, seller at L/anchor (v0)
    "min_margin": 1,       # P of surplus on every price we send or accept (INV-12)
    "acc_late": 3,         # from deadline - acc_late accept any offer inside our limit
    "close_frac": 0.75,    # ... or once this fraction of the duel has elapsed (v0 CLOSE)
    "final": 4,            # at deadline - final: one final offer toward the limit if the rival is outside it
    "final_frac": 0.6,     # final offer goes this fraction of the way from our offer to the limit
    "slow_keep": 0.25,     # slow ascent keeps this share of the way for the tail
    "slow_tail": 3,        # ... spent over the last slow_tail ticks before deadline - 2
    "e8_ticks": 2,         # E8: silence after the first answer of the first rival that speaks
    "T": None,             # duel length override (ticks)
    "days_sign": None,     # +1: more days is better for us; -1: fewer; None: unknown (worst case)
    "accept_paused": False,
    "e8_hold_until": None,
}


# ------------------------------------------------------------------------------------------ helpers

def _int(x: Any) -> Optional[int]:
    return x if type(x) is int else None


def _num(x: Any) -> Optional[float]:
    return float(x) if type(x) in (int, float) and math.isfinite(x) else None


def _local_duel_fingerprint(d: Mapping) -> str:
    """Spec §2.5: sha1(duel_id, rival_offer.id, .price, .days, .tick, len(messages))."""
    ro = d.get("rival_offer") if isinstance(d.get("rival_offer"), Mapping) else {}
    did = d.get("duel", d.get("id"))
    raw = json.dumps([did, ro.get("id"), ro.get("price"), ro.get("days"), ro.get("tick"),
                      len(d.get("messages") or ())], separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def duel_fingerprint(d: Mapping) -> str:
    try:
        from agent.guards import duel_fingerprint as fp   # M4a owns the canonical one
        return fp(d)
    except Exception:
        return _local_duel_fingerprint(d)


def _predict(limit: int, price: int, decay: float, rounds: int, role: str) -> Prediction:
    try:
        from agent.valuation import predict_duel          # M3: side is "buy" | "sell"
        p = predict_duel(limit, price, decay, rounds, "buy" if role == "buyer" else "sell")
        if type(p) is Prediction:
            return p
    except Exception:
        pass
    return Prediction(0.0, 0.0, "0", 0, duel=round(abs(price - limit) * (1 - decay) ** rounds, 1), model="U-01")


def _template_variants(name: str) -> int:
    try:
        from agent.talk import TEMPLATES
        return max(1, len(TEMPLATES[name]))
    except Exception:
        return 1


def curve(k: int, anchor: float, limit: float, total: int, beta: float = BETA) -> int:
    return round(anchor + (limit - anchor) * min(1.0, k / max(1, total)) ** (1 / beta))


# --------------------------------------------------------------------------------------------- view

@dataclass(frozen=True)
class DuelView:
    duel_id: int
    ok: bool
    why: str
    role: str = ""
    limit: int = 0
    s: int = 0                     # +1 seller, -1 buyer: surplus = s * (price - limit)
    tick: int = 0
    deadline: int = 0
    start: int = 0
    T: int = 0
    decay: float = 0.0
    two_issue: bool = False
    days_weight: Optional[float] = None
    days_meaning_known: bool = False
    ours: tuple = ()               # ((tick, price, days, index), ...) our messages, server order
    rivals: tuple = ()             # same for the rival
    rival_offer: Optional[tuple] = None   # (price, days, tick, id)
    mine: Optional[int] = None     # our standing price (last message, else your_offer)
    rounds: int = 0
    rival_spoke_now: bool = False
    rival_double: bool = False     # E16: two rival messages in one tick
    fingerprint: str = ""


def _default_T(decay: float) -> int:
    return 16 if abs(decay - 0.06) < 1e-9 else 12   # U-12


def view(duel: Mapping, tick: int) -> DuelView:
    """Read one live duel. Any shape we do not understand gives ok=False (decide then waits)."""
    did = _int(duel.get("duel", duel.get("id"))) if isinstance(duel, Mapping) else None
    if did is None or type(tick) is not int:
        return DuelView(duel_id=did if did is not None else -1, ok=False, why="shape.id")
    bad = lambda why: DuelView(duel_id=did, ok=False, why=why)   # noqa: E731
    if duel.get("status") != "live":
        return bad("status")
    role = duel.get("role")
    limit = _int(duel.get("your_limit"))
    deadline = _int(duel.get("deadline_tick"))
    decay = _num(duel.get("decay_per_round"))
    if role not in ("buyer", "seller") or limit is None or limit < 1 or deadline is None:
        return bad("shape.core")
    if decay is None or not 0 <= decay < 1:
        return bad("shape.decay")
    issues = duel.get("issues")
    if not isinstance(issues, (list, tuple)) or not all(isinstance(i, str) for i in issues):
        return bad("shape.issues")
    two = "days" in issues
    msgs = duel.get("messages") or []
    if not isinstance(msgs, (list, tuple)):
        return bad("shape.messages")
    ours, rivals = [], []
    for i, m in enumerate(msgs):
        if not isinstance(m, Mapping):
            return bad("shape.message")
        t, p, dd = _int(m.get("tick")), _int(m.get("price")), m.get("days")
        if t is None or p is None or (dd is not None and _int(dd) is None):
            return bad("shape.message")
        (ours if m.get("from") == "you" else rivals).append((t, p, dd, i))
    ro = duel.get("rival_offer")
    rival_offer = None
    if ro is not None:
        if not isinstance(ro, Mapping) or _int(ro.get("price")) is None or _int(ro.get("tick")) is None:
            return bad("shape.rival_offer")
        rd = ro.get("days")
        if rd is not None and _int(rd) is None:
            return bad("shape.rival_offer")
        rival_offer = (ro["price"], rd, ro["tick"], ro.get("id"))
    yo = duel.get("your_offer")
    mine = ours[-1][1] if ours else (_int(yo.get("price")) if isinstance(yo, Mapping) else None)
    T = _default_T(decay)
    first = min([m[0] for m in ours + rivals], default=deadline - T)
    start = min(deadline - T, first)
    per_tick: dict = {}
    for m in rivals:
        per_tick[m[0]] = per_tick.get(m[0], 0) + 1
    spoke_now = (rival_offer is not None and rival_offer[2] == tick
                 and bool(rivals) and rivals[-1][0] == tick and rivals[-1][1] == rival_offer[0])
    w = _num(duel.get("your_days_weight"))
    return DuelView(
        duel_id=did, ok=True, why="", role=role, limit=limit, s=1 if role == "seller" else -1, tick=tick,
        deadline=deadline, start=start, T=deadline - start, decay=decay, two_issue=two, days_weight=w,
        days_meaning_known=(duel.get("days_meaning_known") is True
                            or duel.get("days_meaning") not in (None, "")), ours=tuple(ours), rivals=tuple(rivals),
        rival_offer=rival_offer, mine=mine, rounds=min(len(ours), len(rivals)), rival_spoke_now=spoke_now,
        rival_double=any(c > 1 for c in per_tick.values()), fingerprint=duel_fingerprint(duel))


# ------------------------------------------------------------------------------------------- decide

def _days_model(v: DuelView, P: Mapping):
    """-> (readable, our_days, extra(d)) for the days issue. extra(d) = P lost to days in the worst case."""
    if not v.two_issue:
        return True, None, (lambda d: 0.0)
    w = v.days_weight
    if w is None or not v.days_meaning_known:
        return False, None, None
    sign = P.get("days_sign")
    aw = abs(w)
    if sign not in (1, -1):
        return True, None, (lambda d: aw * DAYS_MAX)          # max_d |W(d) - W(base)|
    best = DAYS_MAX if sign > 0 else 0
    W = lambda d: sign * aw * d                                 # noqa: E731
    top = W(best)
    return True, best, (lambda d: top - W(d))


def surplus(v: DuelView, p: int) -> int:
    return v.s * (p - v.limit)


def decide(v: DuelView, params: Optional[Mapping] = None) -> tuple:
    """("say"|"accept"|"wait", price, days). Final guard: anything outside the limits becomes a wait."""
    P = dict(DEFAULTS, **(params or {}))
    try:
        if v.ok and P["T"]:
            v = _with_T(v, int(P["T"]))
        act = _decide(v, P)
    except Exception:
        return ("wait", None, None)
    return _final_guard(v, P, act)


def _need(v: DuelView, P: Mapping, extra, d) -> float:
    if v.two_issue and d is None:
        return math.inf
    return P["min_margin"] + extra(d if d is not None else 0)


def _final_guard(v: DuelView, P: Mapping, act: tuple) -> tuple:
    kind, price, days = act
    wait = ("wait", None, None)
    if kind == "wait" or not v.ok:
        return wait
    readable, _, extra = _days_model(v, P)
    if not readable or v.tick > v.deadline - 1:
        return wait
    if kind == "say":
        if type(price) is not int or price < 1:
            return wait
        if v.ours and v.ours[-1][0] >= v.tick:                          # one message per duel per tick
            return wait
        if v.two_issue:
            if type(days) is not int or not 0 <= days <= DAYS_MAX:
                return wait
        elif days is not None:
            return wait
        if surplus(v, price) < _need(v, P, extra, days):
            return wait
        if v.mine is not None and v.s * (price - v.mine) > 0:            # monotone: never retract a concession
            return wait
        return ("say", price, days)
    if kind == "accept":
        if P["accept_paused"] or v.rival_double or not v.rival_spoke_now or v.rival_offer is None:
            return wait
        rp, rd = v.rival_offer[0], v.rival_offer[1]
        if v.two_issue and rd is None:
            return wait
        if surplus(v, rp) < _need(v, P, extra, rd):
            return wait
        return ("accept", rp, rd)
    return wait


def _clamp(v: DuelView, p: float, need: float) -> int:
    """Clamp a price so that our surplus is at least `need`."""
    p = int(round(p))
    if v.s < 0:
        return min(p, v.limit - math.ceil(need))
    return max(p, v.limit + math.ceil(need))


def _decide(v: DuelView, P: Mapping) -> tuple:
    wait = ("wait", None, None)
    if not v.ok or v.tick > v.deadline - 1:
        return wait
    readable, our_days, extra = _days_model(v, P)
    if not readable:
        return wait                                                     # J10: nothing before reading the days
    buyer = v.s < 0
    L = v.limit
    ro = v.rival_offer
    r = ro[0] if ro else None
    rd = ro[1] if ro else None
    say_days = our_days
    if v.two_issue and say_days is None:                                # sign unknown: margin covers any days
        say_days = rd if type(rd) is int and 0 <= rd <= DAYS_MAX else 0
    need_say = _need(v, P, extra, say_days)
    Lm = L - need_say if buyer else L + need_say                        # closest price we may offer
    ok_r = r is not None and surplus(v, r) >= _need(v, P, extra, rd)
    anchor = int(L * P["anchor"]) if buyer else math.ceil(L / P["anchor"] - 1e-9)
    anchor = _clamp(v, anchor, need_say)
    mine = v.mine
    spoke_this_tick = bool(v.ours) and v.ours[-1][0] >= v.tick
    late = v.tick >= v.deadline - P["acc_late"]
    total = max(2, v.deadline - v.start)
    k = len(v.rivals)
    nxt = curve(k, anchor, Lm, total)
    if mine is not None:
        nxt = max(nxt, mine + 1) if buyer else min(nxt, mine - 1)
    nxt = _clamp(v, nxt, need_say)

    # 1. acceptance (only when the rival spoke this tick: its standing offer cannot change before our POST)
    if ok_r and v.rival_spoke_now and not P["accept_paused"]:
        firm = len(v.rivals) >= 2 and v.rivals[-1][1] == v.rivals[-2][1]
        good = surplus(v, r) >= surplus(v, nxt) or (mine is not None and surplus(v, r) >= surplus(v, mine))
        opening = mine is None and surplus(v, r) >= surplus(v, anchor)
        elapsed = (v.tick - v.start) >= P["close_frac"] * total
        if good or firm or late or opening or elapsed:
            return ("accept", r, rd)

    if spoke_this_tick:
        return wait

    # 2. opening
    if mine is None:
        return ("say", anchor, say_days)

    # 3. rival never spoke: slow ascent (free: rounds stay 0)
    if not v.rivals:
        end = v.deadline - 2
        tail_start = end - P["slow_tail"]
        t0 = v.start
        if v.tick >= end:
            frac = 1.0
        elif v.tick <= tail_start:
            frac = (1 - P["slow_keep"]) * max(0, v.tick - t0) / max(1, tail_start - t0)
        else:
            frac = (1 - P["slow_keep"]) + P["slow_keep"] * (v.tick - tail_start) / max(1, P["slow_tail"])
        p = _clamp(v, anchor + (Lm - anchor) * min(1.0, frac), need_say)
        p = max(p, mine) if buyer else min(p, mine)
        return ("say", p, say_days) if p != mine else wait

    # 4. E8: silence after the first answer of the first rival that speaks
    hold = P.get("e8_hold_until")
    if type(hold) is int and v.tick < hold and not late:
        return wait

    rival_after_ours = not v.ours or v.rivals[-1][3] > v.ours[-1][3]

    # 5. late: provoke an inside-limit rival that did not speak this tick; final offer toward the limit otherwise
    if late and ok_r and not v.rival_spoke_now:
        p = r if (r >= mine if buyer else r <= mine) else mine
        return ("say", _clamp(v, p, need_say), say_days)
    last_our_tick = v.ours[-1][0] if v.ours else -1
    if v.tick >= v.deadline - P["final"] and not ok_r and last_our_tick < v.deadline - P["final"]:
        p = _clamp(v, mine + P["final_frac"] * (Lm - mine), need_say)
        p = max(p, mine) if buyer else min(p, mine)
        return ("say", p, say_days) if p != mine else wait

    # 6. v0 corrected: concede one step only when the rival answered our last message (K-06)
    if rival_after_ours:
        p = nxt
        if ok_r:                                                         # never offer more than the rival asks
            p = min(p, r) if buyer else max(p, r)
            p = max(p, mine) if buyer else min(p, mine)
        return ("say", p, say_days) if p != mine else wait
    return wait


# ------------------------------------------------------------------------------------------ propose

def e16_settled(state: dict, done_duels) -> Optional[str]:
    """Compare settled prices of duels we accepted with the price we read (E16). Mismatch -> accepts paused."""
    pend = state.setdefault("duel_accepts", {})
    for d in done_duels or ():
        if not isinstance(d, Mapping):
            continue
        did = d.get("duel", d.get("id"))
        rec = pend.get(did)
        if rec is None or d.get("status") != "deal":
            continue
        yo = d.get("your_offer") if isinstance(d.get("your_offer"), Mapping) else {}
        price = d.get("price")
        if price != rec["price"] and price != yo.get("price"):
            state["duel_accepts_paused"] = f"E16.price:{did}:{rec['price']}->{price}"
        pend.pop(did, None)
    return state.get("duel_accepts_paused")


def propose(world, cfg, plan_cfg, params, state) -> list:
    """Intents for every live duel. state: a dict the runner keeps between ticks (E8, E16)."""
    if state is None:
        state = {}
    if "duels" in (getattr(world, "down", None) or ()):
        return []
    P = dict(DEFAULTS, **(params or {}))
    sign = (plan_cfg or {}).get("days_sign") if isinstance(plan_cfg, Mapping) else None
    P["days_sign"] = sign if sign in (1, -1) and type(sign) is int else None
    tick = world.tick
    accepts, says = [], []
    for d in world.duels or ():
        try:
            v = view(d, tick)
            if not v.ok:
                continue
            if v.rival_double and not state.get("duel_accepts_paused"):
                state["duel_accepts_paused"] = f"E16.two_msgs:{v.duel_id}"
            p = dict(P, accept_paused=bool(P["accept_paused"] or state.get("duel_accepts_paused")))
            e8 = state.get("e8")
            if e8 is None and v.rivals:
                e8 = state["e8"] = {"duel": v.duel_id, "until": v.rivals[0][0] + P["e8_ticks"]}
            exp = None
            if e8 and e8.get("duel") == v.duel_id:
                p["e8_hold_until"] = e8["until"]
                exp = "E8"
            act, price, days = decide(v, p)
            if act == "accept":
                pred = _predict(v.limit, price, v.decay, v.rounds, v.role)
                it = make_intent("duel_accept", "duels", {"duel_id": v.duel_id, "fingerprint": v.fingerprint},
                                 f"duel {v.duel_id} {v.role} L={v.limit}: rival {price} spoke at t{tick}",
                                 f"deal at {price}, surplus {surplus(v, price)}, rounds {v.rounds}", pred,
                                 priority=1000 - (v.deadline - tick), experiment=exp)
                accepts.append((v.deadline, -surplus(v, price), v.duel_id, it, price, days))
            elif act == "say":
                tpl = "duel_days" if v.two_issue else "duel"
                pred = _predict(v.limit, price, v.decay, v.rounds + 1, v.role)
                says.append(make_intent(
                    "duel_say", "duels",
                    {"duel_id": v.duel_id, "price": price, "days": days, "template": tpl,
                     "variant": len(v.ours) % _template_variants(tpl)},
                    f"duel {v.duel_id} {v.role} L={v.limit}: offer {price}" + (f" d{days}" if days is not None else ""),
                    f"if accepted: surplus {surplus(v, price)}", pred,
                    priority=500 - (v.deadline - tick), experiment=exp))
        except Exception:
            continue                                                    # fail closed: nothing for this duel
    budget = getattr(getattr(world, "limits", None), "accepts", 0)
    budget = budget if type(budget) is int and budget > 0 else 0
    accepts.sort(key=lambda a: (a[0], a[1], a[2]))
    out = []
    rec = state.setdefault("duel_accepts", {})
    for dl, _, did, it, price, days in accepts[:budget]:
        rec[did] = {"tick": tick, "price": price, "days": days}
        out.append(it)
    chosen = {a[2] for a in accepts[:budget]}
    skipped = {a[2] for a in accepts[budget:]}
    out.extend(s for s in says if s.args["duel_id"] not in chosen | skipped)
    return out


def _with_T(v: DuelView, T: int) -> DuelView:
    from dataclasses import replace
    start = min(v.deadline - T, min([m[0] for m in v.ours + v.rivals], default=v.deadline - T))
    return replace(v, start=start, T=v.deadline - start)
