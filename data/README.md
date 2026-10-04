# Traces from the live weekend

Real data that the harness and its tools recorded from Sat 3 Oct 09:21 to Sun 4 Oct 12:06 (first and last journal rows). Friday's traces are not included. Secrets were removed at write time by `agent/redact.py`, and we checked that neither the team key nor the broker key appears anywhere in this folder.

| File | What it is | Produced by |
|---|---|---|
| `journal.jsonl` | The harness's hash-chained write-ahead journal, Saturday and Sunday. One JSON object per row with `seq`, `ts`, `tick`, `day`, `mode`, `kind` and `prev` (the hash of the previous row). Row kinds: `intent`, `result`, `refused`, `would`, `tick`, `measure`, `pause`, `alarm`, `cmd`, `arm`, `resume`, `stop`, `reconciled`, `param`… | `agent/journal.py` via the Gate, runner and calibrator |
| `journal-summary.txt` | Counts by row kind, write status, guard refusal code, and intent kind per day | a one-off script over `journal.jsonl` |
| `score-timeline.csv` | One line per journal `tick` row (ticks while the runner was stopped are absent): cash, `cash_free` and the raw score inputs from `/api/me` (`neg_points`, `ladder_points`, `duel_points`, `mm_points`). These are not the normalised leaderboard score; market points come from `bench_points`, which is not recorded here, so `mm_points` stays 0. Join on `seq` with `journal.jsonl` for wall time | the `tick` rows of the journal |
| `report.txt` | The calibration report: predicted vs measured per tactic, and ladder deltas per dealer. Its last two lines show only what the report process itself decided; the live pauses and STOP are the `pause` / `stop` rows of `journal.jsonl` (tick 1513) | `python3 bazaar.py report` |
| `feed_public.jsonl` | The public game feed from tick 1179 onwards (settlements, listings, thread messages, duels, eggs). It is public data from the organisers' API | `egg_watch.py` |
| `market-test/v18-stall-saturday.jsonl` | The book of our free stall during Saturday's 6th Market Test (after the stall's auto-matching) | `bench_rec.py` |
| `market-test/v28-broker.jsonl` | Our board venue on Sunday: the full synthetic book each tick, **before** matching, plus every match we sent and its result | the operator's broker script (manual exception, see [docs/journey.md](../docs/journey.md); not shipped: it ran from a session scratchpad, outside the repo). The hard-test score (`bench_efficiency` 0.967, bench 0.5) was read from `/api/me` at 10:20 |
| `market-test/announcements.txt` | The matchmaking announcements we posted to promote our venue | the operator's announcer script (not shipped, same reason). 3 of 15 were rate-limited (429) |

Not included: the per-tick World snapshots (`logs/run/snap/`), which are large, and `logs/run/untrusted.jsonl` (dealer and rival text, kept out of the World by design).

## Quick analyses

```bash
# guard refusals by code
python3 -c "import json,collections; rows=[json.loads(l) for l in open('data/journal.jsonl', encoding='utf-8')]; print(collections.Counter(r['code'] for r in rows if r['kind']=='refused').most_common(10))"
# verify the hash chain (prev = sha256 of the previous line)
python3 -c "from pathlib import Path; from agent.journal import Journal; print(Journal(Path('data/journal.jsonl'), mode='dry', writer=False).verify_chain())"
```
