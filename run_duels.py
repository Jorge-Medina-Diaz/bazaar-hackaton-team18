"""Play every live duel, one message per duel per tick, until none are left for a while.

    python3 run_duels.py          # play
    python3 run_duels.py --watch  # only print and log the raw duels (learn the protocol, send nothing)
"""
import json, sys  # noqa: E401

from agent.client import client
from agent.duels import step
from agent.journal import log

b, state, idle = client(), {}, 0
watch = "--watch" in sys.argv
while idle < 30:  # stop after 30 ticks without any live duel
    live = [d for d in b.duels().get("duels", []) if d.get("status", "open") in ("open", "live", "active")]
    idle = 0 if live else idle + 1
    for d in live:
        if watch:
            print(json.dumps(d, ensure_ascii=False)[:600])
            log("duels", event="watch", duel=d)
        else:
            step(b, d, state)
    b.wait_tick()
