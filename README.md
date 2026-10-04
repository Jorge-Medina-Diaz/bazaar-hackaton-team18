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

This repository also holds the trading harness of team 18. **Start with [docs/plan-domingo.md](docs/plan-domingo.md)** (Sunday plan, in Spanish) and [docs/knowledge.md](docs/knowledge.md) (verified facts), then [CLAUDE.md](CLAUDE.md) for the layout and the rules. [docs/LEEME-EQUIPO.md](docs/LEEME-EQUIPO.md) is the Saturday-morning team guide, kept for reference.

- One command runs everything: `python3 bazaar.py` (`selftest`, `clockcheck`, `run [--live] [--arm ...]`, `status`, `stop "reason"`). Without `--live` it is a dry run with zero writes.
- Every write to the game goes through one Gate (`agent/gate.py`) and one transport (`agent/transport.py`); everything else is read-only.
- Kill switch: `python3 bazaar.py stop "reason"`, or create a file named `STOP` in the repo root.
- The team key lives only in `.env` on the executor machine, never in Git. Never call `/api/admin/*`.
- Contract: [docs/harness-spec.md](docs/harness-spec.md) · facts: [docs/knowledge.md](docs/knowledge.md) · play book: [docs/strategy.md](docs/strategy.md) · official rules: [RULES.md](RULES.md), [docs/official/kickoff.pdf](docs/official/kickoff.pdf).
- Panels (read-only): `api/index.py` + `agent/dashboard.py` (Vercel), `website/` (hosted panel), `panel.py`, `live_monitor.py`, and the offline lab `laboratorio.py`. Read-only helpers: `bench_rec.py` (Market Test book recorder) and `egg_watch.py` (keyless easter-egg watcher). Do not run `observe_performance.py`: it sends the team key to an external host.
- The kit's `starter_agent.py` and `starter_broker.py` (sections 1 and 5 above) are in `archive/` and disabled (`SystemExit`); in this repo everything goes through `python3 bazaar.py`.
- Superseded scripts and notes are in [archive/](archive/README.md); none of them can run.

Tests: `python3 -m unittest discover -s tests -t .` (the panel website: `node --test website/worker.test.mjs`).
