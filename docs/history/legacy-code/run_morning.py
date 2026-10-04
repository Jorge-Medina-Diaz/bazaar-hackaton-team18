"""Saturday 09:00 opening, one command. Safe to re-run: every step checks before acting.

    python3 run_morning.py            # does everything below
    python3 run_morning.py --dry      # only reports what it would do

1. snapshot every endpoint (probe) and print levels, dealers, schedule, cash
2. open our venue: board mechanism, fee 0 (fees never score and block crossings; docs/broker-design.md),
   as soon as cash >= 270 (bond 250 + 20); saves the broker key to .env as BROKER_KEY
3. tells you the two long-running commands to start: run_broker.py (Market Test, records the book) and run_loop.py
"""
raise SystemExit("ARCHIVED by M18: pre-harness script that could reach the game without the Gate. Use the harness: python3 bazaar.py (see CLAUDE.md).")  # M18 guard
import json, os, subprocess, sys  # noqa: E401

from bazaar_sdk import BazaarError
from agent.client import client
from agent.journal import log

DRY = "--dry" in sys.argv
b = client()
subprocess.run([sys.executable, "probe.py"], stdout=subprocess.DEVNULL)
me, c = b.me(), b.clock()
print(f"tick {c['tick']} · hour {c['t_hours']:.2f} · doors {c['doors']} · cash {me['cash']} · level {me['level']} · venue {me.get('venue')}")
print("levels:", json.dumps(b.levels(), ensure_ascii=False)[:600])
print("dealers:", [(d["id"], d["status"]) for d in b.dealers()["personas"]])
print("next:", [(u["at_hours"], u["note"]) for u in b.schedule()["upcoming"][:5]])

if me.get("venue"):
    print(f"venue already open: {me['venue']}")
elif me["level"] < 2:
    print("level < 2: cannot open a venue yet")
elif me["cash"] < 270:
    print(f"cash {me['cash']} < 270: wait for the Saturday allowance (150 P at hour 4.05), then re-run")
elif DRY:
    print("DRY: would open venue 'Mercado 18' (board, fee 0)")
else:
    try:
        v = b.open_venue("Mercado 18", fee_bps=0, fee_per_card=0, rules={"mechanism": "board"},
                         description="Fee 0. Fair matching for everyone.")
    except BazaarError as e:  # if 0 is refused, the smallest fee keeps crossings almost intact
        print(f"fee 0 refused ({e.code}: {e.message}); trying 1 bps")
        v = b.open_venue("Mercado 18", fee_bps=1, fee_per_card=0, rules={"mechanism": "board"},
                         description="Lowest fee. Fair matching for everyone.")
    log("venue", event="open", venue=v)
    key = v.get("broker_key")
    print(f"venue opened: {v.get('venue') or v.get('id')} · broker key received: {bool(key)}")
    if key:
        with open(".env", "a", encoding="utf-8") as f:
            f.write(f"\nBROKER_KEY={key}\n")
        print("BROKER_KEY saved to .env (gitignored)")

print("\nNow start, each in its own terminal (or background):")
print("  python3 run_broker.py   # Market Test: greedy matching + records logs/book.jsonl")
print("  python3 run_loop.py     # autonomous trading, duels, alerts")
