# Bazaar · Cromos de Madrid: Team 18 (t18) harness

Guidance for anyone, human or AI agent, working in this repository. Overview: [README.md](README.md). Architecture: [docs/architecture.md](docs/architecture.md). Contract: [docs/harness-spec.md](docs/harness-spec.md). Facts: [docs/knowledge.md](docs/knowledge.md). Official rules: [RULES.md](RULES.md).

## Commands
```
python3 bazaar.py selftest                     tests per stage -> state/selftest.json (required before any live run)
python3 bazaar.py clockcheck                   live clock, schedule and derived day end / endgame; no key
python3 bazaar.py run [--live] [--arm a,b]     the runner; without --live it is a dry run with zero writes
python3 bazaar.py status                       journal, STOP, lock, pauses, pending; zero API calls
python3 bazaar.py arm|pause <tactic> --why "..."
python3 bazaar.py resume [tactic] --why "..."  without a tactic it removes STOP; with one it un-pauses it
python3 bazaar.py do <kind> --args '<json>' --why "..." [--live]   one manual intent, through the same Gate
python3 bazaar.py stop "reason" [--flatten]    kill switch (or create a STOP file in the repo root)
python3 bazaar.py report                       calibration report from the journal
python3 -m unittest discover -s tests -t .     the full suite (stdlib, no key, no network)
python3 -m sim.sunday C 120                    rehearse a Sunday against the fake server
```

## Layout
```
bazaar.py              the CLI and the only entry point
bazaar_sdk.py          the organisers' SDK: do not edit (the harness never imports it)
config/plan.json       every tunable number: page targets, dealer profiles, caps, duel parameters, day times
agent/
  contracts.py         M0, FROZEN: World, Intent, Prediction, Paths, ARGS, KINDS, TACTICS, GET_ALLOWLIST
  transport.py         the only connection: GET by allowlist; writes only with a one-use permit from the Gate
  gate.py              the only executor of writes (guards -> permit -> transport.send -> journal)
  guards.py, talk.py   rules G01–G60 and the Book; talk.py also holds the message templates and the text firewall
  offer_safety.py      structure-before-words checks on offers
  valuation.py         marginal value model and predictions (no I/O)
  world.py             the sensor: builds the World (structured fields only, never foreign text)
  journal.py           hash-chained write-ahead journal in logs/run/; calibrate.py: prediction vs measurement
  runner.py            the per-tick loop; execution.py: the single-writer lock
  tactics/             pages, hygiene, dealers, rastro, duels, bench: they propose Intents and never write
  client.py            client("read"): read-only transport for panels and tools
  dashboard.py, dashboard.html, redact.py   read-only dashboard (api/index.py on Vercel, run_dashboard.py locally)
sim/                   fake server, bots, faults and invariant checks for the tests
tests/                 the full suite (tests/__init__.py isolates: BAZAAR_TEST=1, no key, loopback only)
ladder_sell.py, egg_carrier.py          operator sales to a dealer; they write only through `bazaar.py do`
flag_candidates.py, announce_candidates.py, egg_watch.py, bench_rec.py   read-only operator tools
data/                  curated live traces (see data/README.md)
docs/                  architecture, journey, limitations, spec, knowledge, strategy; docs/history/ is the event log
state/, logs/, runs/   local runtime, never in Git
```

## Rules
- **Never write outside the Gate.** Every write to the game is an `Intent` that passes `agent/gate.py` and leaves through `agent/transport.py`. Nothing else in `agent/` or in the root scripts imports `bazaar_sdk`, `urllib` or `http.client` for writing; `tests/test_architecture.py` checks this.
- **Never call `/api/admin/*`.**
- **The team key lives only in `.env` on the machine that runs the bot**, never in Git, logs, snapshots or the dashboard (`agent/redact.py`). Tests never use a key.
- **Code decides numbers and accepts; text never does** (ours, a rival's or an LLM's). Foreign text never enters the World.
- **Fail closed.** If a function, a data source or a value is missing, refuse. Never act without checking.
- **Before `--live`:** `selftest` must be green, and every armed tactic needs its stage green for the current `code_hash`.
- **Kill switch:** `python3 bazaar.py stop "reason"` or a `STOP` file. After a crash, relaunch the same `run`; it reconciles before writing.
- **Manual exceptions** are actions the Gate has no kind for: flags, and venue fee, announcements or broker. They need the team lead's explicit approval each time, and each is logged in `docs/history/handoffs/HANDOFF-domingo.md`.
- **Keep it simple:** stdlib only, functions, no frameworks. Do not edit `agent/contracts.py` (frozen) or `bazaar_sdk.py` (official). Every behaviour change needs a test that fails on the old code.
