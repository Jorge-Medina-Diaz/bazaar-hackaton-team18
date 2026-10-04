# Known limitations

We list what we know is missing or imperfect. The code shipped here is the code that played on Sunday. These items were found and written down, but not changed during the live event.

## Duels
- **A two-issue duel can stall.** The "never retract" and "never worse than the rival" checks compare price only (`agent/talk.py` G50, `agent/tactics/duels.py`). Suppose the rival moves below our bid but asks for more days. Then no price is both monotone and acceptable, and the tactic waits. It never goes outside the limit, but it can miss a deal where the rival trades price for days. The partial fix in the code sends the rival's own (price, days) pair back as an echo near the deadline.
- **One accept per tick is shared.** Up to 4 duels can end on the same deadline, and they share that slot with dealer accepts. In simulation, 3 of 4 late-converging duels close.
- **The seller treats its limit as a price floor.** It ignores a days bonus that would make a lower price worth it.

## Runner
- **A manual accept can lose the accept slot to a duel accept.** Accepts are sorted by deadline, then priority (`agent/runner.py`, `choose`). The dropped order is logged (`dropped`) but not re-queued.
- **The late window was tuned for 30 s ticks.** At 15 s ticks it leaves about 1–1.5 s of headroom under the rate limit.

## Sensor and data
- One malformed offer marks its whole board source down for that tick (fail closed, coarse).
- The public feed only serves its last 500 events, and our archive starts at tick 1179. Saturday ticks 394–1178 are missing.
- The calibrator re-scans the journal every tick: O(rows), fine for one event.

## Market
- **No Gate kind for venue operations.** `contracts.py` was frozen, so opening a venue, running the broker and making announcements were operator actions outside the Gate. Each was approved and logged by hand (docs/history/handoffs/HANDOFF-domingo.md).
- **Market Test matching mirrors the free stall.** It adds only cross-run pairs. We never showed that a policy can beat the stall, and on Saturday no team did.

## Not wired
- `pages.protect_sets` (the Book keeps the protection computed by `guards.build_book`), `Calibrator.recheck`, and the in-runner bench recorder (`bench_rec.py` does it out of process).
- Online learning is limited to the calibrator: pauses, and a +50 team-deal cap detector that never fired live (the cap is confirmed offline, knowledge S-05). Dealer price models were tuned offline from the journal and the feed.
