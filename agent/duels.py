"""Duels: 1v1 price (and later price + delivery days) negotiations against other teams' agents.

Code decides every number (docs/negotiation-design.md). Hard rule: never offer or accept outside our limit
(a deal outside it loses points; no deal scores 0). The pie shrinks every round (decay), so we concede faster
than with dealers and close early. Field names follow the SDK docstring (role, your_limit, rival_offer, deadline);
unknown shapes are logged raw so the practice session teaches us the protocol.
"""
from bazaar_sdk import Bazaar, BazaarError

from agent.haggle import curve
from agent.journal import log

ANCHOR = 0.6   # seller opens at limit / ANCHOR, buyer at limit * ANCHOR
BETA = 1.6     # > 1: concede early, the pie decays every round
CLOSE = 0.75   # from this fraction of the duel, accept any offer inside our limit


def _num(x):
    return x.get("price") if isinstance(x, dict) else x


def step(b: Bazaar, d: dict, state: dict) -> None:
    """One tick of one duel. `state` keeps our last price per duel id (monotonic offers)."""
    did, role, limit = d["id"], d.get("role"), d.get("your_limit")
    if limit is None or role not in ("seller", "buyer"):
        log("duels", event="unknown_shape", duel=d)
        return
    seller = role == "seller"
    rival = _num(d.get("rival_offer"))
    total = d.get("duel_ticks") or 12
    k = state.setdefault(did, {"k": 0, "last": None})["k"]
    anchor = round(limit / ANCHOR) if seller else max(1, round(limit * ANCHOR))
    nxt = curve(k, anchor, limit, total, BETA)
    last = state[did]["last"]
    if last is not None:
        nxt = min(last - 1, nxt) if seller else max(last + 1, nxt)
    nxt = max(nxt, limit) if seller else min(nxt, limit)  # never cross our own limit
    inside = rival is not None and (rival >= limit if seller else rival <= limit)
    good = rival is not None and (rival >= nxt if seller else rival <= nxt)
    log("duels", event="round", duel=did, role=role, limit=limit, rival=rival, k=k, our_next=nxt, raw=d)
    try:
        if inside and (good or k >= CLOSE * total):
            print(f"  duel {did} ({role}, limit {limit}): accept {rival}")
            b.duel_accept(did)
            log("duels", event="accept", duel=did, price=rival)
        else:
            days = None
            if "days" in (d.get("issues") or []):  # trade days we care little about; refine after practice
                w = d.get("your_days_weight")
                days = 0 if (w or 0) >= 0 else 10
            print(f"  duel {did} ({role}, limit {limit}): rival {rival}, we offer {nxt}" + (f", {days} days" if days is not None else ""))
            b.duel_say(did, "Propuesta justa para cerrar pronto y que ganemos los dos.", price=nxt, days=days)
            state[did].update(k=k + 1, last=nxt)
    except BazaarError as e:
        print(f"  duel {did}: {e.code} {e.message}")
        log("duels", event="error", duel=did, code=e.code, message=e.message, extra=e.extra)
