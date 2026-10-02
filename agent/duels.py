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


def step(b: Bazaar, d: dict, state: dict, tick: int = 0) -> None:
    """One tick of one duel. Real shape (practice, tick 120): {duel, status: live, role, your_limit, rival_offer,
    your_offer, deadline_tick, decay_per_round, rounds, issues, your_days_weight, ...}."""
    did, role, limit = d.get("duel", d.get("id")), d.get("role"), d.get("your_limit")
    if did is None or limit is None or role not in ("seller", "buyer"):
        log("duels", event="unknown_shape", duel=d)
        return
    seller = role == "seller"
    rival = _num(d.get("rival_offer"))
    if did not in state:  # after a restart, resume from our standing offer: never retract a concession
        mine = d.get("your_offer") or {}
        ours = [m for m in d.get("messages") or [] if m.get("from") == "you"]
        state[did] = {"k": len(ours), "last": mine.get("price"), "start": tick - len(ours), "rival_msgs": 0}
    st = state[did]
    rival_msgs = sum(1 for m in d.get("messages") or [] if m.get("from") != "you")
    if st["last"] is not None and rival_msgs == st["rival_msgs"] and rival is None:
        return  # reciprocity: never concede against silence (practice: most rivals never answered)
    moved = rival_msgs > st["rival_msgs"]
    st["rival_msgs"] = rival_msgs
    total = max(2, (d.get("deadline_tick") or tick + 12) - st["start"])
    left = (d.get("deadline_tick") or tick + 12) - tick
    k = st["k"]
    anchor = round(limit / ANCHOR) if seller else max(1, round(limit * ANCHOR))
    nxt = curve(k, anchor, limit, total, BETA)
    last = st["last"]
    if last is not None:
        nxt = min(last - 1, nxt) if seller else max(last + 1, nxt)
    nxt = max(nxt, limit) if seller else min(nxt, limit)  # never cross our own limit
    inside = rival is not None and (rival >= limit if seller else rival <= limit)
    hist = st.setdefault("rival_hist", [])
    if moved and rival is not None:
        hist.append(rival)
    firm = len(hist) >= 2 and hist[-1] == hist[-2]  # rival stopped moving: waiting only shrinks the pie (decay)
    good = rival is not None and (rival >= nxt if seller else rival <= nxt)
    log("duels", event="round", duel=did, role=role, limit=limit, rival=rival, k=k, left=left, our_next=nxt, raw=d)
    try:
        if inside and (good or firm or k >= CLOSE * total or left <= 2):
            print(f"  duel {did} ({role}, limit {limit}): accept {rival}")
            b.duel_accept(did)
            log("duels", event="accept", duel=did, price=rival)
        else:
            days = None
            if "days" in (d.get("issues") or []):  # trade days we care little about; refine with real weights
                w = d.get("your_days_weight")
                days = 0 if (w or 0) >= 0 else 10
            print(f"  duel {did} ({role}, limit {limit}): rival {rival}, we offer {nxt}" + (f", {days} days" if days is not None else ""))
            b.duel_say(did, "Propuesta justa para cerrar pronto y que ganemos los dos.", price=nxt, days=days)
            st.update(k=k + 1 if (moved or st["last"] is None) else k, last=nxt)
    except BazaarError as e:
        print(f"  duel {did}: {e.code} {e.message}")
        log("duels", event="error", duel=did, code=e.code, message=e.message, extra=e.extra)
