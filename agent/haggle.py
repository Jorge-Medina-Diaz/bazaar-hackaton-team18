"""Dealer-agnostic haggling: code decides every price (docs/negotiation-design.md, invariants 2-4).

One function for buying and selling. Buying, our price climbs from `anchor` up to `limit`; selling, it falls from
`anchor` down to `limit`. Our offers are monotonic and never repeat (a repeated price earns no concession).
"""
from bazaar_sdk import Bazaar

from agent.journal import log


def curve(k: int, anchor: int, limit: int, rounds: int, beta: float) -> int:
    """Faratin time-dependent concession: round k of `rounds`, beta < 1 holds out, beta > 1 concedes early."""
    return round(anchor + (limit - anchor) * min(1.0, k / rounds) ** (1 / beta))


def haggle(b: Bazaar, dealer: str, topic: dict, *, anchor: int, limit: int, rounds: int, beta: float,
           lines: list, buying: bool = True) -> dict:
    """Run one thread to its end. Returns {"status", "price", "thread"}; every round goes to logs/<dealer>.jsonl."""
    th = b.open_thread(dealer, topic=topic)
    tid, k, last = th["id"], 0, None
    better = (lambda a, x: a <= x) if buying else (lambda a, x: a >= x)  # is price a at least as good for us as x
    side = "want" if buying else "give"  # her offer wants our cash when we buy, gives cash when we sell
    print(f"{dealer} thread {tid} {topic}: anchor {anchor}, limit {limit}")
    log(dealer, event="open", thread=tid, topic=topic, anchor=anchor, limit=limit, rounds=rounds, beta=beta)
    while True:
        t = b.thread(tid)
        if t["status"] != "open":
            price = next((o[side]["cash"] for o in reversed(t["standing_offers"]) if o["status"] == "accepted"), None)
            print(f"  {t['status']} ({t.get('closed_reason')}) price {price}")
            log(dealer, event="end", thread=tid, status=t["status"], reason=t.get("closed_reason"), price=price,
                our_last=last, snapshot=t)  # full thread kept: her words are data for the playbook
            return {"status": t["status"], "price": price, "thread": tid}
        hers = [o for o in t["standing_offers"] if o["maker"] == dealer and o["status"] == "open"]
        her = hers[-1][side]["cash"] if hers else None
        final = bool(hers and hers[-1].get("final"))
        nxt = curve(k, anchor, limit, rounds, beta)
        if last is not None:  # strictly monotonic towards the limit
            nxt = max(last + 1, nxt) if buying else min(last - 1, nxt)
        log(dealer, event="round", thread=tid, k=k, her=her, final=final, our_next=nxt, our_last=last)
        ok = her is not None and better(her, limit)
        if ok and (better(her, nxt) or final or k >= rounds):  # AC_next, her final word, or out of rounds
            print(f"  accept {her}{' (final)' if final else ''}")
            log(dealer, event="accept", thread=tid, price=her, final=final, k=k)
            b.accept(hers[-1]["id"])
        elif final or not better(nxt, limit):
            print(f"  her {her} beyond our limit {limit}: walk away")
            log(dealer, event="walk", thread=tid, her=her)
            b.close_thread(tid)
        else:
            print(f"  round {k}: she {her}, we {nxt}")
            b.say(tid, lines[k % len(lines)].format(p=nxt), price=nxt)
            last, k = nxt, k + 1
        b.wait_tick()
