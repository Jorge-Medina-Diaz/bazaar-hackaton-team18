"""Offline Market Test simulator: compare the stall's quote-crossing with agent/broker.py on synthetic books.

    python3 sim_bench.py [runs] [--no-expiry]

Model (a guess until we record a real session; RULES: traders shade quotes away from hidden limits, some are
patient, some leave soon, most relax as patience runs out, the firm never do): 10 traders per run (5 buyers,
5 sellers), 16 ticks. Efficiency = realised surplus between TRUE limits / max possible surplus.
"""
raise SystemExit("ARCHIVED by M18: pre-harness script that could reach the game without the Gate. Use the harness: python3 bazaar.py (see CLAUDE.md).")  # M18 guard
import random, sys  # noqa: E401

from agent.broker import Tracker, plan


def make_run(rng, rid, ticks=16, n=5):
    traders = []
    for side in ("s", "b"):
        for i in range(n):
            limit = rng.randint(40, 100)
            shade = rng.uniform(0.1, 0.4)
            leave = rng.randint(4, ticks) if rng.random() < 0.6 else ticks  # 60% may leave early
            firm = rng.random() < 0.25
            traders.append(dict(id=f"{rid}-{side}{i}", side=side, limit=limit, shade=shade, leave=leave, firm=firm))
    return traders


def quote(t, tick):
    prog = 0 if t["firm"] else min(1.0, tick / max(1, t["leave"] - 1))
    sh = t["shade"] * (1 - 0.9 * prog)  # relaxers move 90% of the way to their limit before leaving
    return round(t["limit"] * (1 + sh)) if t["side"] == "s" else max(1, round(t["limit"] * (1 - sh)))


def max_surplus(traders):
    s = sorted(t["limit"] for t in traders if t["side"] == "s")
    b = sorted((t["limit"] for t in traders if t["side"] == "b"), reverse=True)
    return sum(max(0, bb - ss) for bb, ss in zip(b, s))


def greedy(book):  # the stall / starter broker: best bid vs best ask while crossing, every tick
    out = []
    asks = sorted((o for o in book if o["want"]["cash"]), key=lambda o: o["want"]["cash"])
    bids = sorted((o for o in book if o["give"]["cash"]), key=lambda o: -o["give"]["cash"])
    for a, b in zip(asks, bids):
        if b["give"]["cash"] < a["want"]["cash"]:
            break
        out.append((a["id"], b["id"], 0))
    return out


def simulate(traders, strategy, show_expiry, ticks=16):
    alive, tracker, got = {t["id"]: t for t in traders}, Tracker(), 0
    for tick in range(ticks):
        for tid in [k for k, t in alive.items() if t["leave"] <= tick]:
            del alive[tid]
        book = []
        for t in alive.values():
            q = quote(t, tick)
            o = {"id": t["id"], "give": {"cash": q if t["side"] == "b" else 0}, "want": {"cash": q if t["side"] == "s" else 0}}
            if show_expiry:
                o["expires_tick"] = t["leave"]
            book.append(o)
        tracker.see(tick, book)
        if strategy == "greedy":
            matches = greedy(book)
        else:
            matches = plan({"bench_offers": book}, tracker, tick, end_tick=ticks - 1, wait=strategy == "wait")
        for s, b, _ in matches:
            if s in alive and b in alive:
                got += alive[b]["limit"] - alive[s]["limit"]
                del alive[s], alive[b]
    return got


if __name__ == "__main__":
    runs = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 300
    show = "--no-expiry" not in sys.argv
    rng, tot = random.Random(7), {"greedy": 0, "broker": 0, "wait": 0, "max": 0}
    for r in range(runs):
        tr = make_run(rng, f"b{r}")
        tot["max"] += max_surplus(tr)
        for strat in ("greedy", "broker", "wait"):
            tot[strat] += simulate(tr, strat, show)
    print(f"{runs} runs, expiry visible: {show}")
    for strat in ("greedy", "broker", "wait"):
        print(f"  {strat:7} efficiency {tot[strat] / tot['max']:.1%}")
