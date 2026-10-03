"""Our venue's broker for the Market Test: match like the stall (greedy, proven in sim_bench) AND record the book.

    BROKER_KEY=bk_... python3 run_broker.py          # or the key saved by run_morning.py in .env (BROKER_KEY=...)

Every tick the full book is appended to logs/book.jsonl: that recording is what lets us replace greedy with a
limit-estimating broker (docs/broker-design.md, sim_bench.py) once we see how real bench traders behave.
"""
raise SystemExit("ARCHIVED by M18: pre-harness script that could reach the game without the Gate. Use the harness: python3 bazaar.py (see CLAUDE.md).")  # M18 guard
import os, time  # noqa: E401

from bazaar_sdk import BazaarError, Broker
from agent.client import _load_env
from agent.journal import log
from starter_broker import bench_plan, public_plan  # greedy: what the stall does; sim says it is near-optimal

_load_env()
broker = Broker(os.environ.get("BAZAAR_URL", "https://bazaar.causaprima.ai"), os.environ["BROKER_KEY"])
seen = None
while True:
    try:
        tick, book = broker.clock()["tick"], broker.book()
        now = (tick, [o["id"] for o in (book.get("bench_offers") or []) + (book.get("offers") or [])])
        if now != seen:
            seen = now
            log("book", tick=tick, book=book)  # raw data for the simulator
            for sell, buy, price in bench_plan(book) + public_plan(book):
                try:
                    r = broker.match(sell, buy, price)
                    log("broker", event="match", tick=tick, sell=sell, buy=buy, price=price, result=r)
                except BazaarError as e:
                    log("broker", event="refused", tick=tick, sell=sell, buy=buy, price=price, code=e.code)
    except BazaarError as e:
        print(f"cannot read the book ({e}), retrying")
    time.sleep(1.0)
