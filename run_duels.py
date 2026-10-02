"""Play every live duel, one message per duel per tick, until none are left for a while.

    python3 run_duels.py                    # play, all text arms (plain / info / inject, EXP-012)
    python3 run_duels.py --arms plain       # play with one arm only (no injection)
    python3 run_duels.py --no-mirror        # ignore the partner duel's limit (EXP-010 off)
    python3 run_duels.py --watch            # only print and log the raw duels (learn the protocol, send nothing)
"""
import json, sys  # noqa: E401

from agent.client import client
from agent.duels import ARMS, duel_id, mirror, step
from agent.journal import log

b, state, idle = client(), {}, 0
watch = "--watch" in sys.argv
arms = tuple(sys.argv[sys.argv.index("--arms") + 1].split(",")) if "--arms" in sys.argv else ARMS
use_mirror = "--no-mirror" not in sys.argv
while idle < 30:  # stop after 30 ticks without any live duel
    now = b.clock()["tick"]
    every = list({duel_id(d): d for d in b.duels(done=True).get("duels", []) + b.duels().get("duels", [])}.values())
    live = [d for d in every if d.get("status", "open") in ("open", "live", "active")]
    idle = 0 if live else idle + 1
    rivals = mirror(every) if use_mirror else {}
    for d in live:
        if watch:
            print(json.dumps(d, ensure_ascii=False)[:600])
            log("duels", event="watch", duel=d, rival_limit=rivals.get(duel_id(d)))
        else:
            step(b, d, state, rival_limit=rivals.get(duel_id(d)), now=now, arms=arms)
    b.wait_tick()
