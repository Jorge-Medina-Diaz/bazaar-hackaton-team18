# Team 18 · a fail-closed trading harness for *The Bazaar · Cromos de Madrid*

Team 18 (t18) built this harness for Causa Prima's hackathon (2–4 Oct 2026).
It is an autonomous agent that collects Madrid cards, haggles with five dealer personas, trades with 17 other teams, plays negotiation duels and runs its own market. The harness played Saturday and Sunday live, with a human operator; Friday was played with the earlier scripts now in [docs/history/legacy-code/](docs/history/legacy-code/README.md).

**The design idea:** every write to the game is a typed `Intent` that passes **one Gate**. The Gate re-reads the world, checks it against about thirty guards, logs a write-ahead journal and then sends it through **one transport**. That transport physically refuses anything else.
**The method:** we measured what the scorer pays for, wrote it down as numbered facts, and changed the plan and the code only from those facts.

| | Result |
|---|---|
| Friday (round 1) | **13th → 2nd** by tick 75 (first complete album page of the game); closed 7th |
| Saturday (round 2) | **7th → 2nd** (2nd-best negotiation score of the field at the close) |
| Sunday (round 3) | 4 album pages complete by 09:35. 1st in negotiation by 10:20. Our own board venue matched 96.7 % of the hard Market Test's possible gains (bench score 0.5, the same as the free stall) |
| Duels | Duels II (Sat): 44/68 deals, 65 %. After the day-sign fix, **Duels III (Sun): 57/68 deals, 84 % (field 75 %)**, total result 791.6 → 1,187.6, no deal below our limit. Grand Final: 24/34 (71 %, field 68 %) |
| Writes through the Gate (Sat 09:21 – Sun 14:55) | **1,850: 1,849 accepted by the server, 0 refused, 1 `unknown`** (an exception: its domain froze and it was reconciled as not landed 2 ticks later, as designed). Our own guards refused 531 more before they left the process: 282 were redundant thread closes from a bug fixed in `f9b4e2e`, 143 missed the tick deadline (81 of them in the Grand Final's 15 s ticks), the rest were value, cash and protection checks. Manual writes outside the Gate (flags, venue, broker, announcements) are logged separately |
| Tests | 912 unit, property, chaos and end-to-end tests (stdlib only, no network, no key) |

---

## How a tick works

```
            ┌──────────────────────────── python3 bazaar.py run --live --arm <tactics> ────────────────────────────┐
            │                                                                                                  │
 GET only   │  Sensor (agent/world.py) ──► World (immutable, allowlisted fields, NO foreign text)                │
 ─────────► │        │                         foreign text ──► logs/run/untrusted.jsonl (never read back)     │
            │        ▼                                                                                         │
            │  Calibrator: predicted vs measured score of last tick's writes ──► pause a tactic / STOP           │
            │        ▼                                                                                         │
            │  pages.plan ──► Needs  ──►  pure tactics: hygiene · dealers · rastro · closer · duels · manual     │
            │                                   │  (propose Intents, never write)                              │
            │                                   ▼                                                              │
            │  runner.choose: per-tick budgets, priorities, duel accepts in the late window                      │
            │                                   ▼                                                              │
            │  Gate.execute:  STOP → idempotency → source health → fresh re-read → guards G01–G60                │
            │                 → recompute prediction → WAL intent (fsync) → one-use permit → send → WAL result   │
            │                                   ▼                                                              │
 POST/...   │  GuardedTransport: sends only with a permit matching (method, exact path, sha256(body))            │
 ◄───────── │  + sys.addaudithook: any non-GET urllib request without a permit raises                            │
            └──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Read [docs/architecture.md](docs/architecture.md) for the module map, the invariants and the guard catalogue.

## What makes it robust

- **One write path, enforced three times.** The transport only sends with a one-use permit. An audit hook kills any other non-GET request. An AST test (`tests/test_architecture.py`) fails the build if any file in `agent/` other than `transport.py` and `gate.py` touches the wire, or if an operator script imports the SDK, contains an HTTP write verb, or combines raw urllib with the team key (`bench_rec.py` excepted: GET only).
- **Fail closed everywhere.** A response that is not clean `ok` / `deferred` / `refused` is `unknown`. That freezes its domain and is never resent. A missing module, data source or value refuses the action. A broken journal stops the bot.
- **Structure over words.** The code reads only the structured offer, never the text. Dealers lie: Los Pícaros swap the card inside a counter-offer. Guards G10/G11 compare a fingerprint re-read in the same tick, and flagging those tricks scored +60 (six correct flags). Our own messages come from templates, behind a text firewall (G60) that blocks any number or word that could leak our limits.
- **A hash-chained write-ahead journal.** Every intent, result, refusal, measurement, pause and operator command is in one append-only file, with `fsync` before each send. After a crash the bot reconciles before writing again. An excerpt is in [data/](data/README.md).
- **Prediction vs measurement.** Every write carries a predicted score change. The calibrator measures the real one and pauses the tactic when they disagree.
- **A single writer and a kill switch.** A lock file allows one writer process. `python3 bazaar.py stop "reason"` or a `STOP` file halts every write within the tick. Operator commands go through an inbox and the same Gate (`bazaar.py do`).
- **No LLM at runtime.** Every number and every accept decision comes from code.

## Run it

Python ≥ 3.9, standard library only.

```bash
python3 -m unittest discover -s tests -t .      # the full suite: no key, no network (tests/__init__.py isolates)
python3 -m sim.sunday C 120                      # rehearse a Sunday against the in-process fake server
python3 bazaar.py selftest                       # tests per stage -> state/selftest.json (arms only green stages)
python3 bazaar.py clockcheck                     # live clock and schedule, no key
python3 bazaar.py run                            # dry run against the real game (needs BAZAAR_KEY=tk-... in .env): reads, decides, writes nothing
python3 bazaar.py run --live --arm hygiene,dealers,rastro,closer,duels    # the real thing (needs BAZAAR_KEY in .env)
python3 bazaar.py status                         # journal, STOP, lock, pauses; zero API calls
python3 bazaar.py report                         # calibration report from the journal
python3 bazaar.py replay-friday                  # replay Friday against the fake server (tests/test_replay_friday.py)
```

## Repository map

| Path | What it is |
|---|---|
| `bazaar.py` | The CLI and the only entry point (`selftest`, `run`, `do`, `stop`, `status`, `report`…) |
| `agent/` | The harness: `contracts` (frozen types) · `transport` (the write barrier) · `gate` · `guards` + `talk` (rules G01–G60) · `world` (sensor) · `valuation` · `journal` · `calibrate` · `runner` |
| `agent/tactics/` | Pure strategy: `hygiene`, `dealers`, `rastro` (team market + page closer) and `duels` propose Intents; `pages` turns targets into Needs; `bench` is a read-only Market Test recorder used by `bench_rec.py` |
| `config/plan.json` | Every tunable number: target pages, dealer profiles (anchor/step/limit), caps, duel parameters, day times |
| `sim/` | Fake Bazaar server with dealer, team and duel bots, fault injection and invariant checks |
| `tests/` | 912 tests, including real captured server responses (`tests/fixtures/`), the Friday replay and chaos tests |
| `ladder_sell.py`, `egg_carrier.py` | Operator tools: a manual dealer sale with a price ladder. They write only through `bazaar.py do` (the Gate) |
| `flag_candidates.py`, `announce_candidates.py`, `egg_watch.py`, `bench_rec.py` | Read-only operator tools (trick finder, market matchmaking drafts, feed archiver, Market Test recorder) |
| `picaros.py`, `radio.py`, `rivals.py`, `affinity.py` (+ `agent/affinity.py`), `afinidad_propia.py` | Read-only analysis tools by the team's analysts (all keyless except `affinity.py` online, which reads `/api/me`): Pícaros trick detector, a feed watcher that rates news for t18, rival tracking, and a Bayesian estimate of each rival's per-set multiplier from public trades |
| `run_duel_eval.py` | Offline duel evaluator: plays the real duel tactic against 10 rival archetypes, with bootstrap confidence intervals; it reports points, deal rate, missed deals and any deal outside our limit |
| `api/`, `run_dashboard.py`, `agent/dashboard.py` | Read-only team dashboard (local or Vercel) |
| `data/` | Curated traces from the live weekend: journal, score timeline, Market Test books, public feed |
| `docs/` | Architecture, journey, limitations, the full spec, verified facts, playbook. [Index](docs/README.md) |
| `bazaar_sdk.py`, `RULES.md`, [docs/sdk.md](docs/sdk.md) | The organisers' SDK, rules and kit README, unmodified (only `agent/transport.py` imports the SDK: `GuardedTransport` subclasses `Bazaar` and replaces its `_call`) |
| `.github/workflows/tests.yml` | CI: the full suite on Python 3.9 and 3.12, plus the Sunday rehearsal |
| `vercel.json`, `.vercelignore` | Deploy of the optional hosted dashboard (only `api/`, `agent/` and the SDK) |

## Read next

1. [docs/journey.md](docs/journey.md): how we adapted over three days. What we measured, what broke live, how we fixed it.
2. [docs/architecture.md](docs/architecture.md): modules, tick order, invariants, guards.
3. [SHOWCASE.md](SHOWCASE.md): the memory for the judges: ten ideas, the craft, the three rounds, what went wrong and what we changed.
4. [docs/limitations.md](docs/limitations.md): what we know is missing or imperfect.
5. Deeper, in Spanish: the build contract [docs/harness-spec.md](docs/harness-spec.md) and the verified facts [docs/knowledge.md](docs/knowledge.md) (P-, V-, D-, U-, M-, S- ids).

Team: Jorge, Rubén and Santi. The team key lives only in `.env` on the machine that runs the bot (and, for the optional hosted dashboard, in a Vercel environment variable read by a read-only client), never in Git. No code here calls `/api/admin/*`.
