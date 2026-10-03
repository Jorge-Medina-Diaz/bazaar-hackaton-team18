# Bazaar SDK for Python

The Bazaar · Cromos de Madrid, a hackathon game hosted by Causa Prima.
Welcome!

One file, standard library only: `bazaar_sdk.py`.
Copy it next to your agent, or run from this folder.

## 1. Start in five minutes

```bash
export BAZAAR_URL=https://bazaar.causaprima.ai
export BAZAAR_KEY=tk-xxxx-xxxx      # the key on your team's slip; keep it to your team
curl -s -H "X-Team-Key: $BAZAAR_KEY" $BAZAAR_URL/api/me   # shows your team: the key works (401 = check it)
python3 starter_agent.py            # or: uv run starter_agent.py
```

The starter says hello to Abuela Carmen, haggles for a neighbourhood pack, opens it and prints what you pulled.
Copy it, then make it yours.

The game is open Fri 19:00–23:00, Sat 09:00–23:00 and Sun 09:00–15:00 (Madrid).
Outside those hours nothing ticks.
Big screen: https://bazaar.causaprima.ai

## 2. The calls you use most

```python
from bazaar_sdk import Bazaar, BazaarError
b = Bazaar("https://bazaar.causaprima.ai", "tk-xxxx-xxxx")

me = b.me()                        # cash, level, unlocked dealers, your cards (each with your_value), score
b.value("LAV-09")                  # what one more copy of a card is worth to you (private)
th = b.open_thread("abuela", topic={"buy": {"pack": "sobre_barrio"}})
b.say(th["id"], "Hello! 18 primas?", price=18)   # words plus a structured price
b.accept(offer_id)                 # take a standing offer; it settles on the next tick
```

Everything else: `dealers()`, `dealer(id)`, `catalog()`, `thread(id)`, `close_thread(id)`, `my_threads()`, `list_offer(give, want, venue)`, `cancel(id)`, `my_offers()`, `board(venue)`, `venues()`, `open_pack(id)`, `flag(message_id, reason)`, `duels()`, `duel_say(id, text, price, days)`, `duel_accept(id)`, `open_venue(...)`, `set_fee(...)`, `close_venue(...)`, `broker(key)`, `leaderboard()`, `clock()`, `schedule()`, `levels()`, `feed()`.
Each method is one HTTP route; the docstrings in `bazaar_sdk.py` show the payloads.

## 3. Rules that shape your agent

| Rule | What it means for your code |
|---|---|
| Words persuade, structure binds | Only a structured offer that its counterparty accepts moves cards or cash. Read the offer, not the words. |
| One heartbeat | Per tick your team may accept one offer and send one message per conversation; everything accepted settles on the next tick. `clock()` has the tick length and `next_tick_in`. |
| Dealers move when you move | A dealer concedes only after you do. The same price twice is not a new offer. When its patience runs out it names a final offer (`"final": true`): take it or it walks. |
| Private values | Your set multipliers are secret, and so are everyone else's. `your_value` is what the scorer counts for you. Duplicates are worth little to you and a lot to someone missing them. |
| Value, not activity | You score the value you create: good dealer deals, gains in trades with other teams, your share in duels, and what your market makes possible. The number of trades never counts. |

The full rules are in `RULES.md`, next to this file.

## 4. Errors you will meet

`BazaarError` carries the server's `code`, `message` and HTTP `status`.
A refused request costs nothing.

| code | why | what to do |
|---|---|---|
| `wait_for_tick` | a second message or accept in the same tick | the SDK waits for the next tick and retries |
| `rate_limited` | more than 5 requests per second | the SDK pauses and retries |
| `locked` / `cooloff` | dealer not unlocked yet / cooling off after tricks | `dealers()` shows how each one unlocks |
| `persona_quota` | too many conversations or deals with a dealer this hour | come back next game hour |
| `insufficient_cash`, `not_owner`, `asset_locked` | the deal would fail | re-read `me()` |
| `self_venue` | your team key on your own market | trade elsewhere; your broker runs your market |
| `venue_not_live` | team markets open later (see `schedule()`) | trade on El Rastro meanwhile |
| `bad_key` | wrong or rotated key | ask the organisers at the desk |

## 5. Your own market

From level 2 you can open a market (a refundable bond of 250 primas plus 20).
You get a broker key for it:

```bash
python3 -c 'from bazaar_sdk import Bazaar; import os; print(Bazaar(os.environ["BAZAAR_URL"], os.environ["BAZAAR_KEY"]).open_venue("My market", fee_bps=150, rules={"mechanism": "board"})["broker_key"])'
BROKER_KEY=bk_... python3 starter_broker.py     # keep it running all game
```

Most of the market points come from *the Market Test*: every venue regularly gets the same synthetic book of buyers and sellers, and your broker scores the share of the possible gains it realises.
The starter broker matches by quoted prices, as the free stall does.
Traders quote away from limits they keep hidden, so a broker that estimates those limits does better.

## 6. New things during the weekend

New dealers and mechanics appear as levels.
`b.levels()` lists what is announced and what is active, with a line on how to use it.
A route a level brings is one `b.call("POST", "/api/...", {...})` away.
For live updates instead of polling: `GET /api/events/stream?scope=team` with your `X-Team-Key` header.


## Team 18 (t18)

This repository also holds the trading harness of team 18. **Start with [docs/LEEME-EQUIPO.md](docs/LEEME-EQUIPO.md)** (team guide, in Spanish), then [CLAUDE.md](CLAUDE.md) for the layout and the rules.

- One command runs everything: `python3 bazaar.py` (`selftest`, `clockcheck`, `run [--live] [--arm ...]`, `status`, `stop "reason"`). Without `--live` it is a dry run with zero writes.
- Every write to the game goes through one Gate (`agent/gate.py`) and one transport (`agent/transport.py`); everything else is read-only.
- Kill switch: `python3 bazaar.py stop "reason"`, or create a file named `STOP` in the repo root.
- The team key lives only in `.env` on the executor machine, never in Git. Never call `/api/admin/*`.
- Contract: [docs/harness-spec.md](docs/harness-spec.md) · facts: [docs/knowledge.md](docs/knowledge.md) · play book: [docs/strategy.md](docs/strategy.md) · official rules: [RULES.md](RULES.md), [docs/official/kickoff.pdf](docs/official/kickoff.pdf).
- Panels (read-only): `api/index.py` + `agent/dashboard.py` (Vercel), `website/` (hosted panel), `panel.py`, `live_monitor.py`, `observe_performance.py`, and the offline lab `laboratorio.py`.
- Superseded scripts and notes are in [archive/](archive/README.md); none of them can run.

Tests: `python3 -m unittest discover -s tests -t .` (the panel website: `node --test website/worker.test.mjs`).

## Evaluation and shared traces

Offline evaluation remains separate from the live Gate:

- [Integration guide](docs/integration-handoff.md): merged architecture and operator steps.
- [Offline harness](docs/harness.md) and [RAG evaluation](docs/rag-evaluation.md).
- [JEV measured results](docs/jev-real-testing.md) and [security controls](docs/jev-security.md).
- [Shared trace viewer](docs/traces.md): read-only, including the harness-v2 journal.

`python3 run_harness.py` compares frozen Friday selectors on synthetic cases, not live v2 tactics. `python3 run_jev_patterns.py` validates the historical plan without network. Neither command arms tactics.

## Jury evidence (no team key)

Open [jury/demo.html](jury/demo.html) locally: four sections with a dated public
snapshot, Affinity probabilities and engineering evidence. Story:
[SHOWCASE.md](SHOWCASE.md); script and rotation:
[docs/jury-runbook.md](docs/jury-runbook.md); formula certainty:
[docs/scoring-evidence.md](docs/scoring-evidence.md).

With Python 3.10+: `python3 -m jury.report --refresh` builds a fresh static demo in
`runs/jury/` using four public GETs. It does not read credentials, trade or call a
model. Optional local `--journal logs/run/journal.jsonl` exports aggregate verified
chain counts, never raw journal contents. It is independent of the runner.


## Shared analyst and jury workflow

[Analyst panel](analista/index.html) → **Exportar para jurado** →
`python3 -m jury.report --analyst-export analista-publico.json` → `runs/jury/demo.html`.
No network or model call during import. The static analyst bundle includes
[jury demo](analista/jurado.html), generated alongside dealer limits with
`python3 -m jury.report --refresh --output jury --team-output analista`.
[Analyst guide](docs/analista.md) describes the partial public history and operator decisions.
