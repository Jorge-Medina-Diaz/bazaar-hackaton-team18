"""Record every Market Test book we can see (EXP-015): every venue gets "the same synthetic book" every two hours.
If the books repeat, or the traders' quotes move by a rule we can fit, a broker can estimate the hidden limits and
beat the free stall (half the bench points). Needs our own venue's broker key; reads only, matches nothing.

    BROKER_KEY=bk_... python3 bench.py      # one line per tick with bench offers in logs/bench.jsonl
"""
import os, time  # noqa: E401

from bazaar_sdk import BazaarError, Broker

from agent.journal import log

if __name__ == "__main__":
    broker = Broker(os.environ.get("BAZAAR_URL", "https://bazaar.causaprima.ai"), os.environ["BROKER_KEY"])
    last = None
    while True:
        try:
            tick, book = broker.clock()["tick"], broker.book()
            bench = book.get("bench_offers") or []
            if bench and tick != last:
                last = tick
                log("bench", tick=tick, bench_offers=bench)
                print(f"tick {tick}: {len(bench)} bench offers logged")
        except BazaarError as e:
            print(f"cannot read the book ({e}), trying again")
        time.sleep(2.0)
