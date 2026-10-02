"""Team-to-team trading on El Rastro, where neg_points come from (1 point per prima of value gained, EXP-005).

    python3 market.py scan              # every open offer, ranked by our gain = our value - price - fee (buys)
                                        # or price - fee - our value (their bids for cards we hold)
    python3 market.py sell-low 9 LAT    # list every card worth < 9-3 to us, except sets we complete (LAT)
    python3 market.py sell-dups 9       # list every spare copy (never the last one) at 9 P, if 9 > its value to us

The accepting side pays the venue fee (5 % + 1 P per card on El Rastro); a listing of ours is paid in full.
Expiry is asked in 15 s units (see expiry()); listings last 60 real ticks, then re-run sell-dups.
"""
import collections, math, sys  # noqa: E401

from agent.client import client
from agent.journal import log

VENUE = "rastro"


def fee(price: int, cards: int = 1) -> int:
    return math.ceil(0.05 * price) + cards  # El Rastro: 500 bps + 1 P per card, rounded up (fee 2 on a 9 P sale)


def expiry(b, ticks: int) -> int:
    """expires_in_ticks is counted in 15 s units: at 60 s ticks asking 240 gives 60 real ticks (measured, tick 69)."""
    return int(ticks * b.clock()["tick_seconds"] / 15)


def scan(b) -> None:
    me = b.me()
    held = {a["ref"]: a["your_value"] for a in me["assets"] if a["kind"] == "card"}
    values, rows = {}, []
    ours = {o["id"] for o in b.my_offers()["offers"]}  # the board shows makers as pseudonyms, us included
    for o in b.board(VENUE).get("offers", []):
        if o["id"] in ours:
            continue
        g, w = o["give"], o["want"]
        if len(g.get("assets") or []) == 1 and w.get("cash") and not w.get("assets"):  # someone sells a card
            ref = g["assets"][0]["ref"]
            values.setdefault(ref, b.value(ref)["your_value"])
            rows.append((values[ref] - w["cash"] - fee(w["cash"]), "BUY", ref, w["cash"], values[ref], o["id"]))
        elif g.get("cash") and len(w.get("types") or []) == 1:  # someone bids for a card type
            ref = w["types"][0].split(":")[1]
            if ref in held:
                rows.append((g["cash"] - fee(g["cash"]) - held[ref], "SELL", ref, g["cash"], held[ref], o["id"]))
    for gain, side, ref, price, val, oid in sorted(rows, reverse=True):
        print(f"{gain:>7.1f}  {side:4} {ref:7} at {price:>4} P  our value {val:>6}  offer {oid}")
    log("market", event="scan", rows=rows)


def sell_dups(b, price: int) -> None:
    me = b.me()
    listed = {a["id"] for o in b.my_offers()["offers"] for a in o["give"].get("assets") or []}
    copies = collections.defaultdict(list)
    for a in me["assets"]:
        if a["kind"] == "card":
            copies[a["ref"]].append(a)
    for ref, cs in copies.items():
        for a in sorted(cs, key=lambda a: a["serial"])[1:]:  # keep one copy, always
            if a["id"] in listed or price <= a["your_value"]:
                continue
            r = b.list_offer({"assets": [a["id"]]}, {"cash": price}, venue=VENUE, expires_in_ticks=expiry(b, 60))
            print(f"listed {ref} (value {a['your_value']}) at {price} P -> offer {r.get('id')}")
            log("market", event="list", ref=ref, asset=a["id"], price=price, our_value=a["your_value"], offer=r.get("id"))


def sell_low(b, price: int, keep_sets: set) -> None:
    """List every card worth less than `price` to us (first copies too), except sets we are completing.
    your_value includes page bonuses, so cards of a complete page never qualify."""
    me = b.me()
    listed = {a["id"] for o in b.my_offers()["offers"] for a in o["give"].get("assets") or []}
    for a in me["assets"]:
        if a["kind"] != "card" or a["id"] in listed or a["set"] in keep_sets or price - a["your_value"] < 3:
            continue
        r = b.list_offer({"assets": [a["id"]]}, {"cash": price}, venue=VENUE, expires_in_ticks=expiry(b, 60))
        print(f"listed {a['ref']} (value {a['your_value']}) at {price} P -> offer {r.get('id')}")
        log("market", event="list", ref=a["ref"], asset=a["id"], price=price, our_value=a["your_value"], offer=r.get("id"))
        listed.add(a["id"])


if __name__ == "__main__":
    b = client()
    if sys.argv[1:2] == ["sell-low"]:  # python3 market.py sell-low 9 LAT,RET,CHA
        sell_low(b, int(sys.argv[2]), set(sys.argv[3].split(",")) if len(sys.argv) > 3 else set())
    elif sys.argv[1:2] == ["sell-dups"]:
        sell_dups(b, int(sys.argv[2]) if len(sys.argv) > 2 else 9)
    else:
        scan(b)
