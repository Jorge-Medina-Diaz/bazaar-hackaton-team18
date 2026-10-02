"""Dealer-agnostic haggling: code decides every price (docs/negotiation-design.md, invariants 2-4).

One function for buying and selling. Buying, our price climbs from `anchor` up to `limit`; selling, it falls from
`anchor` down to `limit`. Our offers are monotonic and never repeat (a repeated price earns no concession).
"""
from bazaar_sdk import Bazaar

from agent.journal import log


def curve(k: int, anchor: int, limit: int, rounds: int, beta: float) -> int:
    """Faratin time-dependent concession: round k of `rounds`, beta < 1 holds out, beta > 1 concedes early."""
    return round(anchor + (limit - anchor) * min(1.0, k / rounds) ** (1 / beta))


def offer_ok(o: dict, topic: dict, buying: bool) -> bool:
    """Structure binds: before accepting, check the offer moves exactly what the thread is about.
    Buying: she gives one item of the kind we asked for and wants only cash. Selling: she wants exactly the assets we
    put up and gives only cash. Anything else (extra assets asked from us, a different item) is refused."""
    give, want = o.get("give") or {}, o.get("want") or {}
    if buying:
        item = topic["buy"]
        kind, ref = ("pack", item["pack"]) if "pack" in item else ("card", item.get("card"))
        got = list(give.get("types") or []) + [f"{a['kind']}:{a['ref']}" for a in give.get("assets") or []]
        return (not want.get("assets") and not want.get("types") and not give.get("cash") and len(got) == 1
                and got[0].startswith(kind + ":") and (ref is None or got[0] == f"{kind}:{ref}"))
    ours = sorted(topic["sell"]["assets"])
    asked = sorted(a["id"] if isinstance(a, dict) else a for a in want.get("assets") or [])
    return asked == ours and not want.get("cash") and not give.get("assets") and not give.get("types")


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
            offers = [m["offer"] for m in t.get("messages", []) if m.get("offer")]  # a deal ends as status "settled"
            price = next((o[side]["cash"] for o in reversed(offers) if o["status"] == "settled"), None)
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
        ok = her is not None and better(her, limit) and offer_ok(hers[-1], topic, buying)
        if her is not None and not offer_ok(hers[-1], topic, buying):  # words may lie; never accept a twisted offer
            print(f"  her offer does not match the topic, not accepting: {hers[-1]}")
            log(dealer, event="bad_structure", thread=tid, offer=hers[-1])
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
