"""Broker v1 for the Market Test (docs/broker-design.md).

The score is the share of the possible gains realised, measured between the traders' TRUE limits. Within the
efficient set (top-k buyers vs bottom-k sellers) the pairing does not matter; what loses gains is
(1) matching extramarginal traders early, displacing efficient ones, and (2) letting traders leave unmatched.
So: track every bench trader's quote, estimate its limit, match only estimated-efficient pairs whose quotes
already cross, and match them early only when someone is about to leave (or nobody is still moving).

plan(book, tracker, tick) is pure, so the same code runs live (run_broker.py) and in the simulator (sim_bench.py).
"""
raise SystemExit("ARCHIVED by M18: pre-harness script that could reach the game without the Gate. Use the harness: python3 bazaar.py (see CLAUDE.md).")  # M18 guard
from collections import defaultdict


class Tracker:
    """Quote history per bench offer id: {id: [(tick, quote), ...]}."""

    def __init__(self):
        self.hist = defaultdict(list)

    def see(self, tick: int, offers: list) -> None:
        for o in offers:
            q = _quote(o)
            h = self.hist[o["id"]]
            if not h or h[-1] != (tick, q):
                h.append((tick, q))

    def rate(self, oid: str) -> float:
        """Quote change per tick (asks fall, bids rise when a trader relaxes); 0 for firm or unseen traders."""
        h = self.hist.get(oid) or []
        if len(h) < 2 or h[-1][0] == h[0][0]:
            return 0.0
        return (h[-1][1] - h[0][1]) / (h[-1][0] - h[0][0])


def _quote(o: dict) -> int:
    return o["want"]["cash"] if o["want"].get("cash") else o["give"]["cash"]  # seller asks, buyer bids


def plan(book: dict, tracker: Tracker, tick: int, *, fee=lambda p: 0, horizon: int = 3, end_tick=None,
         wait: bool = False) -> list:
    """[(sell_id, buy_id, price)] to send this tick."""
    runs = defaultdict(lambda: ([], []))  # run -> (asks, bids); a match pairs two offers of one run
    for o in book.get("bench_offers") or []:
        asks, bids = runs[o["id"].split("-")[0]]
        (asks if o["want"].get("cash") else bids).append(o)
    out = []
    for asks, bids in runs.values():
        def left(o):  # ticks before this trader may leave; unknown -> assume plenty
            return (o.get("expires_tick") or 10 ** 9) - tick

        def est(o, sign):  # projected quote when it leaves: our limit estimate (a quote bounds the limit)
            return _quote(o) + sign * abs(tracker.rate(o["id"])) * max(0, min(left(o), 20))

        sellers = sorted(asks, key=lambda o: est(o, -1))   # cheapest estimated limit first
        buyers = sorted(bids, key=lambda o: -est(o, +1))   # highest estimated limit first
        k = 0                                              # size of the estimated efficient set
        while k < min(len(sellers), len(buyers)) and est(buyers[k], +1) >= est(sellers[k], -1):
            k += 1
        eff_s, eff_b = sellers[:k], buyers[:k]
        closing = end_tick is not None and end_tick - tick <= horizon
        used = set()
        for b in sorted(eff_b, key=lambda o: -_quote(o)):  # crossing pairs among efficient traders only
            for s in sorted(eff_s, key=_quote):
                if s["id"] in used:
                    continue
                ask, bid = _quote(s), _quote(b)
                price = (ask + bid) // 2
                while price > ask and price + fee(price) > bid:
                    price -= 1
                if price < ask or price + fee(price) > bid:
                    continue
                urgent = (not wait or closing or left(s) <= horizon or left(b) <= horizon
                          or (tracker.rate(s["id"]) == 0 and tracker.rate(b["id"]) == 0))
                if urgent:
                    out.append((s["id"], b["id"], price))
                    used.add(s["id"])
                    break
                break  # this buyer's best crossing seller is not urgent: wait, quotes may still move
    return out[:10]
