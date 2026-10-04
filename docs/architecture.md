# Architecture

This is the English map of the harness. The full build contract, with every signature, invariant and guard formula, is [harness-spec.md](harness-spec.md), in Spanish.

## Principles

1. **One write path.** Only `agent/gate.py` can cause a write, and only `agent/transport.py` can send one.
2. **Fail closed.** Unknown, missing or malformed means refuse. The bot never guesses.
3. **Code decides numbers, text never does.** Foreign text (dealers, rivals, LLMs) never enters the data the tactics read. Our own text is templated and firewalled.
4. **Measure, then act.** Every write carries a predicted score change, and the calibrator checks it against the measured change.
5. **Stdlib only, single process, no LLM at runtime.** Python ≥ 3.9, Windows and macOS.

## Modules

| Module | Role |
|---|---|
| `agent/contracts.py` (M0, frozen) | `World`, `Intent`, `Prediction`, `Paths`, `Secrets`, the argument schema of each write kind (`ARGS`, `KINDS`), the tactic names, `GET_ALLOWLIST` and `WRITE_ROUTES`. Every module codes against this file. |
| `agent/transport.py` (M1) | `GuardedTransport`: its own urllib opener (no redirects, no write retries). GETs go only to allowlisted routes. A write needs a one-use permit equal to `(method, exact path, sha256(body))`, live mode and no STOP. Installs a `sys.addaudithook` that rejects any other non-GET request. Classifies responses as `ok`, `deferred`, `refused` or `unknown`. |
| `agent/client.py` | `client("read")`: the same transport in read-only mode, for panels and operator tools. |
| `agent/journal.py` (M2) | One append-only, hash-chained JSONL write-ahead log for the whole event, with `fsync` before each send and tail recovery. |
| `agent/valuation.py` (M3) | The measured value model (copy factors, page bonus, master bonus, affinity), fees and score predictions per kind. |
| `agent/guards.py` (M4a) | The `Book` (commitments: held, listed, pending, paths, cash_free) and guards G01–G23, G33, G40, plus the dependency table between write kinds and data sources. |
| `agent/talk.py` (M4b) | Conversation guards G30–G32 (dealers), G50–G51 (duels), the text firewall G60, and the message templates. |
| `agent/gate.py` (M5) | `Gate.execute`, `begin_tick` (Book, baseline, foreign-writer detection) and `reconcile`. |
| `agent/execution.py` | The single-writer lock (`state/writer.lock`). |
| `agent/world.py` (M7) | The sensor. Prioritised GETs within the rate budget produce an immutable `World` of allowlisted fields. Foreign text goes to `untrusted.jsonl`. |
| `agent/tactics/pages.py` (M8) | Turns page targets into `Need`s (ref, source, cap), freezes the page-closing card at 8/10, and derives the day end and endgame times from the live clock and schedule. |
| `agent/tactics/hygiene.py` (M9) | Startup cancels, pack opening, the protected-copy watch (G19) and closing dealer threads at the end of the day. |
| `agent/tactics/dealers.py` (M10) | Non-blocking haggling with the five dealers, driven by numeric profiles (anchor, step, limit, fallback). |
| `agent/tactics/rastro.py` (M11) | The team market: the page closer bid, sales of duplicates, buys below value, swaps, and buy-anything-below-value in the endgame. |
| `agent/tactics/duels.py` (M12) | Two-issue duels (price and delivery day). The sign of the day weight comes from the server's own wording. Includes a slow ascent against a silent rival, and accepts timed to the tick the rival spoke. |
| `agent/calibrate.py` (M13) | Pairs settlements with intents, measures the score components, and pauses or stops on disagreement. |
| `agent/runner.py` (M15) | The per-tick loop, `choose` (budgets and priorities), the late window for duel accepts, the operator inbox. |
| `bazaar.py` (M16) | The CLI. Operator commands go through `state/inbox/`, and the CLI never writes the journal. |
| `sim/` (M6) | `FakeGame`: a fake Bazaar with its own oracle, dealer, team and duel bots, faults, and loopback or 127.0.0.1 HTTP. |

## Tick order

Each step runs in its own `try`.

1. Read the operator inbox (`arm`, `pause`, `do`, `stop`) and apply it, one journal row each.
2. If STOP is active, nothing is written.
3. Wait for a new tick. While the clock is paused or the doors are closed, poll the clock without the key; only `cancel` and `close_thread` may pass.
4. Fast path on start and on the first open tick: startup hygiene before the full read.
5. `sensor.snapshot` builds the World.
6. `gate.begin_tick`: build the Book, check for a foreign writer, reconcile pending intents.
7. `calibrator.on_tick` decides pauses or a STOP.
8. `pages.plan` gives the Needs.
9. The tactics propose Intents. An exception skips that tactic for this tick; three in 20 ticks pause it.
10. `runner.choose` orders the Intents within the per-tick budgets, and `Gate.execute` runs each one. Duel accepts wait for the late window of the tick, after a fresh re-read.
11. Write the `tick` row: cash, score components, outcomes.

## Gate.execute

`STOP → idempotency (≤ 1 send per intent id) → source health → fresh re-read (offer / thread / duel + clock tick) → guards → prediction recomputed with the same server values (±0.01, else refuse) → dry, unarmed or paused: journal "would" → tick deadline → WAL intent + fsync → one-use permit → send → WAL result → Book updated with the outcome`

A dry run walks the same path and the same per-tick budgets. It just stops before the permit.

## Invariants (summary)

| Id | Invariant |
|---|---|
| INV-01 | Single write point: no non-GET leaves the process except from `Gate.execute` with a matching one-use permit. |
| INV-02 | No write outside live mode, with an unarmed or paused tactic, with STOP, or after the tick deadline. |
| INV-03 | Per-tick budgets: accepts, messages per thread or duel, listings plus cancels, open offers, open threads. |
| INV-04 | No deal with a predicted loss, with a minimum gain per kind (team ≥ 3, page closer ≥ 20, dealer ≥ 1). |
| INV-05 | Exact structure: accept only a canonical offer whose fingerprint, re-read this tick, matches. |
| INV-06 | Protected copies: never hand over a card a target page needs. |
| INV-07 | Cash: `cash_free ≥ 0` after every decision, counting every standing commitment. |
| INV-08 | One buy path per card (a bid, a dealer thread or a pending accept). |
| INV-10 | A page-closing card is never bought from a dealer (that scores 0; from a team it scores up to +50). |
| INV-11 | Dealer threads: our price strictly monotone, the limit set at opening only goes down, never counter a final. |
| INV-12 | Duels: at least +1 surplus in every price, including the delivery-day term. Accept only on a fresh re-read of the same tick. |
| INV-13 | Text: templates only; digits ⊆ {price, days}; no forbidden terms; foreign text never in the World. |
| INV-14/15 | Idempotency and WAL: `unknown` freezes its domain; reconcile before writing again after a restart. |
| INV-16 | Foreign writer: an offer, thread or message of ours that the journal cannot explain causes a STOP. |
| INV-17 | Calibration: every write is predicted, and a hard failure pauses the tactic persistently. |
| INV-18 | Secrets never reach the journal, snapshots, dashboard or console (redaction by pattern and by value). |
| INV-20 | Fair play: never trade on our own venue, no wash trades, no round trips. |
| INV-21 | Tests never reach a host other than 127.0.0.1 or touch the real `logs/`, `state/` or `.env`. |
| INV-22 | Single writer: one lock for every run and every one-shot `do`. |

## Guard catalogue (summary)

| Group | Guards |
|---|---|
| Global | G01 STOP · G02 kind and schema · G03 clock, doors and tick deadline · G04 budgets · G05 idempotency · G06 source health · G07 prediction |
| Accept a team offer | G10 fresh identity · G11 exact shape · G12 value (gain ≥ 3, closer ≥ 20) · G13 protected copies · G14 unopened pack · G15 one path · G16 cash |
| Publish | G20 own sale · G21 own bid / closer bid · G22 expiry · G23 cancel ours only |
| Dealer threads | G30 open (unlocked, not blocked, limit ≤ value − margin) · G31 say (monotone, ≤ limit, never counter a final) · G32 accept (executable, ≤ limit) · G33 close · G40 open pack |
| Duels | G50 message (surplus ≥ 1 plus the days penalty, monotone) · G51 accept (live, rival spoke this tick, fingerprint, surplus) |
| Text | G60 firewall: template, digits, forbidden words (limit, value, budget, affinity, key, …), ≤ 280 characters |

Every refusal is a journal row with its code (`refused`, `G13.listed`, …). [data/journal-summary.txt](../data/journal-summary.txt) counts them for the live weekend.

## Operator surface

- `bazaar.py do <kind> --args '<json>' --why "..." --live`: one manual intent through the same Gate and guards. `ladder_sell.py` and `egg_carrier.py` drive sequences of these.
- `bazaar.py arm|pause|resume <tactic>`: tactics only act when armed, not paused, and their selftest stage is green for the current `code_hash`.
- Manual exceptions outside the Gate. The Gate has no write kind for flags or venue announcements, and `contracts.py` was frozen. These few writes were done by hand with the team lead's explicit approval, and each one was logged in [history/handoffs/HANDOFF-domingo.md](history/handoffs/HANDOFF-domingo.md).
