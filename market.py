"""Team-to-team trading on El Rastro, where neg_points come from (1 point per prima of value gained, EXP-005).

    python3 market.py scan              # every open offer, ranked by our gain = our value - price - fee (buys)
                                        # or price - fee - our value (their bids for cards we hold)
    python3 market.py sell-dups 9       # list every spare copy (never the last one) at 9 P, if 9 > its value to us
    python3 market.py sell-high         # same spares, priced by supply: x1.6 collector's ceiling with no competing ask,
                                        # else 1 P under the cheapest one, never below the x1.1 collector's ceiling
    python3 market.py cross [--go]      # crossed books: an ask below someone's bid for the same card, on any venue
                                        # (EXP-011); --go buys the best one, then fills the bid once it settles
    python3 market.py bid-page RET 0.8  # standing bids at 80 % of our value for every card a page is missing (EXP-013)

The accepting side pays the venue fee (5 % + 1 P per card on El Rastro); a listing of ours is paid in full.
Expiry is asked in 15 s units (see expiry()); listings last 60 real ticks, then re-run sell-dups.
"""
import collections, json, math, os, sys  # noqa: E401

from agent.client import client
from agent.journal import log

VENUE = "rastro"
CATALOG = {"common": 10, "uncommon": 25, "rare": 70, "epic": 180, "legendary": 450}  # scoring.md §3
COLLECTOR = 1.1  # lowest affinity among the three teams that value a set above catalog (1.1, 1.3, 1.6)


def rarity(ref: str) -> str:
    n = int(ref.split("-")[1])  # per set: 01-05 commons, 06-08 uncommons, 09-10 rares, 11 epic, 12 legendary
    return "common" if n <= 5 else "uncommon" if n <= 8 else "rare" if n <= 10 else "epic" if n == 11 else "legendary"


def collector_price(ref: str, affinity: float = COLLECTOR) -> int:
    """Highest ask at which a collector at `affinity` still gains after paying the fee: common 9, uncommon 25, rare 72
    at 1.1; 14, 37, 105 at 1.6. The spread between our affinity and theirs is the value; both sides score."""
    return math.floor((CATALOG[rarity(ref)] * affinity - 1) / 1.05)


def supply_price(ref: str, asks: dict, bids: dict):
    """Scarcity moves where we sit between the x1.1 and x1.6 collectors' ceilings, never above x1.6: nobody's value is
    higher, so no rational buyer pays more. No competing ask: the x1.6 ceiling. Competing asks: 1 P under the cheapest,
    floored at x1.1. A standing bid that pays more than our ask: None (don't list, fill it from `scan`)."""
    lo, hi = collector_price(ref), collector_price(ref, 1.6)
    rivals = [o["want"]["cash"] for o in asks.get(ref, [])]
    price = max(lo, min(hi, min(rivals) - 1)) if rivals else hi
    best_bid = max((o["give"]["cash"] for o in bids.get(ref, [])), default=0)
    return None if best_bid - fee(best_bid) >= price else price


def fee(price: int, cards: int = 1, bps: int = 500, per_card: int = 1) -> int:
    return math.ceil(bps * price / 10000) + per_card * cards  # El Rastro: 500 bps + 1 P per card (fee 2 on a 9 P sale)


def venue_fees(b) -> dict:
    """{venue: (fee_bps, fee_per_card)} for every open venue, El Rastro and the teams' own."""
    return {v["venue"]: (v["fee_bps"], v["fee_per_card"]) for v in b.venues()["venues"] if v.get("status") == "open"}


def makers(b) -> dict:
    """{offer id: real team}: boards show pseudonyms, the feed's offer.listed carries the maker (docs/api.md)."""
    events = [json.loads(line) for line in open("logs/feed.jsonl", encoding="utf-8")] if os.path.exists("logs/feed.jsonl") else []
    return {e["payload"]["offer"]["id"]: e["payload"]["offer"]["maker"]
            for e in events + b.feed(500).get("events", []) if e.get("type") == "offer.listed"}


def others(b, fees: dict) -> list:
    """Every open offer on every open venue but ours, tagged with its venue."""
    ours = {o["id"] for o in b.my_offers()["offers"]}
    return [dict(o, venue=v) for v in fees for o in b.board(v).get("offers", []) if o["id"] not in ours]


def asks_bids(offers: list):
    """{ref: [asks]}, {ref: [bids]}: one card offered for cash, or cash offered for one card type."""
    asks, bids = collections.defaultdict(list), collections.defaultdict(list)
    for o in offers:
        g, w = o["give"], o["want"]
        if (len(g.get("assets") or []) == 1 and g["assets"][0].get("kind") == "card" and w.get("cash")
                and not w.get("assets") and not w.get("types")):
            asks[g["assets"][0]["ref"]].append(o)
        elif g.get("cash") and not g.get("assets") and len(w.get("types") or []) == 1 and w["types"][0].startswith("card:"):
            bids[w["types"][0].split(":", 1)[1]].append(o)
    return asks, bids


def expiry(b, ticks: int) -> int:
    """expires_in_ticks is counted in 15 s units: at 60 s ticks asking 240 gives 60 real ticks (measured, tick 69)."""
    return int(ticks * b.clock()["tick_seconds"] / 15)


def scan(b) -> None:
    """Every open venue: our gain from taking each offer (the accepting side pays that venue's fee)."""
    fees = venue_fees(b)
    held = {a["ref"]: a["your_value"] for a in b.me()["assets"] if a["kind"] == "card"}
    values, rows = {}, []
    asks, bids = asks_bids(others(b, fees))  # the boards show makers as pseudonyms, us included: others() drops ours
    for ref, offers in asks.items():
        values.setdefault(ref, b.value(ref)["your_value"])
        for o in offers:
            p = o["want"]["cash"]
            rows.append((values[ref] - p - fee(p, 1, *fees[o["venue"]]), "BUY", ref, p, values[ref], o["id"], o["venue"]))
    for ref, offers in bids.items():
        for o in offers if ref in held else []:
            p = o["give"]["cash"]
            rows.append((p - fee(p, 1, *fees[o["venue"]]) - held[ref], "SELL", ref, p, held[ref], o["id"], o["venue"]))
    for gain, side, ref, price, val, oid, venue in sorted(rows, reverse=True):
        print(f"{gain:>7.1f}  {side:4} {ref:7} at {price:>4} P  our value {val:>6}  offer {oid} on {venue}")
    log("market", event="scan", rows=rows)


def cross(b, go: bool = False) -> None:
    """Crossed books (EXP-011): someone asks less for a card than someone else bids for it, on any venues.
    Buying and refilling nets bid - ask - both fees in neg_points whatever the card is worth to us:
    (value - ask - fee) + (bid - fee - value). Risk: the bid leaves while our buy settles and we keep the card."""
    fees, who = venue_fees(b), makers(b)
    asks, bids = asks_bids(others(b, fees))
    rows = []
    for ref in asks.keys() & bids.keys():
        for a in asks[ref]:
            for d in bids[ref]:
                if who.get(a["id"], a["maker"]) == who.get(d["id"], d["maker"]):
                    continue  # the same team on both sides
                pa, pb = a["want"]["cash"], d["give"]["cash"]
                rows.append((pb - fee(pb, 1, *fees[d["venue"]]) - pa - fee(pa, 1, *fees[a["venue"]]), ref, a, d))
    rows.sort(key=lambda r: -r[0])
    for net, ref, a, d in rows[:15]:
        print(f"{net:>5}  {ref:7} ask {a['want']['cash']:>4} ({who.get(a['id'], a['maker'])} on {a['venue']}, offer {a['id']})"
              f"  ->  bid {d['give']['cash']:>4} ({who.get(d['id'], d['maker'])} on {d['venue']}, offer {d['id']})")
    log("market", event="cross", rows=[(n, r, a["id"], d["id"]) for n, r, a, d in rows])
    best = next((r for r in rows if r[0] > 0), None)
    if not go or not best:
        print("" if not go else "nothing positive to cross")
        return
    net, ref, a, d = best
    asset = a["give"]["assets"][0]["id"]
    b.accept(a["id"])  # one accept per tick: the sell leg waits for the settlement
    log("market", event="cross_buy", ref=ref, asset=asset, ask=a["id"], bid=d["id"], net=net)
    print(f"bought {ref} (asset {asset}) at {a['want']['cash']}; waiting for it to settle to fill bid {d['id']}")
    for _ in range(3):
        b.wait_tick()
        if any(x["id"] == asset for x in b.me()["assets"]):
            r = b.accept(d["id"], assets=[asset])
            log("market", event="cross_sell", ref=ref, asset=asset, bid=d["id"], result=r)
            print(f"filled bid {d['id']} with {ref}")
            return
    print(f"{ref} not in hand yet or the bid is gone: run `market.py scan` and relist it near {d['give']['cash']}")
    log("market", event="cross_stuck", ref=ref, asset=asset, bid=d["id"])


def bid_page(b, set_id: str, frac: float = 0.8) -> None:
    """Standing bids at frac x our value for every card a page is missing (EXP-013). Each fill is positive on its
    own and together they unlock the page bonus. Bids do not lock cash: one we cannot pay when taken is refused."""
    held = {a["ref"] for a in b.me()["assets"] if a["kind"] == "card"}
    bidding = {t.split(":", 1)[1] for o in b.my_offers()["offers"] if o["give"].get("cash")
               for t in o["want"].get("types") or []}
    for c in next(s["cards"] for s in b.catalog()["sets"] if s["id"] == set_id):
        ref = c["id"]
        if not c.get("page") or ref in held or ref in bidding:
            continue
        val = b.value(ref)["your_value"]
        price = max(1, math.floor(frac * val))
        r = b.list_offer({"cash": price}, {"cards": [ref]}, venue=VENUE, expires_in_ticks=expiry(b, 60))
        print(f"bid {price} P for {ref} (value {val}) -> offer {r.get('id')}")
        log("market", event="bid", ref=ref, price=price, our_value=val, offer=r.get("id"))


def sell_dups(b, price) -> None:
    """price: a flat int, or a function ref -> int (None: don't list that card)."""
    ask = price if callable(price) else (lambda ref: price)
    me = b.me()
    listed = {a["id"] for o in b.my_offers()["offers"] for a in o["give"].get("assets") or []}
    copies = collections.defaultdict(list)
    for a in me["assets"]:
        if a["kind"] == "card":
            copies[a["ref"]].append(a)
    for ref, cs in copies.items():
        for a in sorted(cs, key=lambda a: a["serial"])[1:]:  # keep one copy, always
            price = ask(ref)
            if price is None:
                print(f"{ref}: a standing bid beats our ask, fill it from `market.py scan` instead of listing")
                continue
            if a["id"] in listed or price <= a["your_value"]:
                continue
            r = b.list_offer({"assets": [a["id"]]}, {"cash": price}, venue=VENUE, expires_in_ticks=expiry(b, 60))
            print(f"listed {ref} (value {a['your_value']}) at {price} P -> offer {r.get('id')}")
            log("market", event="list", ref=ref, asset=a["id"], price=price, our_value=a["your_value"], offer=r.get("id"))


if __name__ == "__main__":
    b = client()
    if sys.argv[1:2] == ["sell-dups"]:
        sell_dups(b, int(sys.argv[2]) if len(sys.argv) > 2 else 9)
    elif sys.argv[1:2] == ["sell-high"]:
        asks, bids = asks_bids(others(b, venue_fees(b)))
        sell_dups(b, lambda ref: supply_price(ref, asks, bids))
    elif sys.argv[1:2] == ["cross"]:
        cross(b, go="--go" in sys.argv)
    elif sys.argv[1:2] == ["bid-page"]:
        bid_page(b, sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 0.8)
    else:
        scan(b)
