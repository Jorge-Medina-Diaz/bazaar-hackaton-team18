"""Frozen Friday selectors for offline comparisons only; no SDK, writer or CLI.
Source: origin/main ae73a8a, run_loop.py best_trade and market.py fee.
These historical assumptions are not the current harness-v2 operating policy.
"""
import math

MIN_GAIN = 3
RESERVE = 150

def fee(price: int, cards: int = 1) -> int:
    return math.ceil(0.05 * price) + cards  # El Rastro: 500 bps + 1 P per card, rounded up (fee 2 on a 9 P sale)


def best_trade(b, me) -> tuple:
    """(gain, kind, offer, our_asset_id) of the best acceptable offer on El Rastro, or (0, None, None, None)."""
    mine = b.my_offers()["offers"]
    ours = {o["id"] for o in mine if o["maker"] == me["id"]}
    to_us = [o for o in mine if o.get("to") == me["id"]]  # offers addressed to us directly
    listed = {a["id"] for o in mine if o["maker"] == me["id"] for a in o["give"].get("assets") or []}
    held = {}
    for a in sorted(me["assets"], key=lambda a: a["id"] in listed):  # prefer a copy not locked in our own listing
        if a["kind"] == "card":
            held.setdefault(a["ref"], a)  # all copies carry the same your_value (the last copy's)
    best, values = (0, None, None, None), {}
    for o in b.board("rastro").get("offers", []) + to_us:
        if o["id"] in ours or o.get("status", "open") != "open":
            continue
        g, w = o["give"], o["want"]
        if (len(g.get("assets") or []) == 1 and not g.get("cash") and not g.get("types")
                and w.get("cash") and not w.get("assets") and not w.get("types")):  # a card for cash
            ref, price = g["assets"][0]["ref"], w["cash"]
            if me["cash"] - price - fee(price) < RESERVE:
                continue
            values.setdefault(ref, b.value(ref)["your_value"])
            cand = (round(values[ref] - price - fee(price), 1), "BUY", o, None)
        elif (g.get("cash") and not g.get("assets") and not g.get("types") and len(w.get("types") or []) == 1
              and not w.get("assets") and not w.get("cash")):  # a bid for a card type
            ref = w["types"][0].split(":", 1)[1]
            if ref not in held:
                continue
            cand = (round(g["cash"] - fee(g["cash"]) - held[ref]["your_value"], 1), "SELL", o, held[ref]["id"])
        else:
            continue
        if cand[0] > best[0]:
            best = cand
    return best
