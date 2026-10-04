# Team 18 · The Bazaar: ideas, craft and evidence

**The Bazaar · Cromos de Madrid**, Causa Prima, 2–4 Oct 2026. Team 18 (t18): Jorge, Rubén and Santi.

We built an autonomous trading agent that cannot write to the game except through **one Gate**. We steered it with **numbered facts measured from the scorer**, not with intuition. This page is our memory of the weekend for the judges: the ideas, how we built them, what went wrong, and where to check every number.

| Round | What happened | Rank |
|---|---|---|
| Friday · El Rastro | Measured the scorer, then traded on it: first complete album page of the game | **13th → 2nd** at tick 75, closed 7th |
| Saturday · Gran Vía | New harness overnight (one Gate, ~30 guards, a write-ahead journal). El Retiro and La Latina pages closed with team deals at the +50 cap | **7th → 2nd** (31.26) |
| Sunday · Chamberí | Chamberí (our ×1.6 set) complete in about 12 minutes (09:21–09:33). Duels III closed **84 %** of duels (the field 75 %). 1st in negotiation by 10:20 | 3rd at 10:20, 0.88 from 1st · final: see the 15:00 freeze |

**Check it in two minutes:** `python3 -m unittest discover -s tests -t .` (911 tests, no key, no network) · `python3 -m sim.sunday C 120` (a Sunday against the fake server) · [data/](data/README.md) (the live journal, its hash chain verifies) · [docs/architecture.md](docs/architecture.md).

---

## Ideas

Each idea comes with what it changed, its evidence, and where it lives.

**1. Measure the scorer before playing it.**
- Before and after each early action we logged `/api/me`, and rebuilt the score deal by deal until it matched the board.
- Result: team trades score value gained at our private values, capped at +50 per deal (P-03, P-07). Dealer gains score 0 and only dealer losses count (P-04, 16/16 measurements). Packs are luck.
- That one finding set the whole strategy: buy from dealers only below our value and only to fill ladder slots, and close every album page with a **team** deal (+50), never a dealer.
- Where: [docs/knowledge.md](docs/knowledge.md) §1. Over 150 facts with ids, evidence and confidence, plus the claims we refuted with data (some were our own).

**2. One write path, enforced three times.**
- Every write is a typed `Intent`. The Gate re-reads the world in the same tick, runs the guards, recomputes the prediction, writes a WAL row with `fsync`, and only then hands the transport a **one-use permit** bound to `(method, exact path, sha256(body))`.
- A `sys.addaudithook` kills any other non-GET request, and an AST test fails the build if anything else touches the wire.
- Evidence: **1,645 writes through the Gate, 1,644 accepted by the server and 0 refused.** The one `unknown` (an exception) froze its domain and was reconciled as not landed two ticks later, exactly as designed. Our own guards refused 447 more first.
- Where: [agent/gate.py](agent/gate.py), [agent/transport.py](agent/transport.py), [data/journal-summary.txt](data/journal-summary.txt).

**3. Structure over words: the text never decides a number.**
- Dealer and rival text never enters the World. The sensor keeps only allowlisted structured fields and stores foreign text apart, base64-encoded, never read back.
- Our own messages come from templates behind a firewall (G60): no digit other than the price and days, and no word such as limit, budget, value or key.
- Payoff: Los Pícaros (level 4) swapped the card inside their counter-offers, and the Gate, which compares a fingerprint re-read in the same tick, never took one. Flagging those tricks scored **+60** (three correct flags per round, Saturday and Sunday).
- Where: [agent/world.py](agent/world.py), [agent/talk.py](agent/talk.py), [picaros.py](picaros.py) and [flag_candidates.py](flag_candidates.py).

**4. Prediction against measurement, in the loop.**
- Every write carries a predicted score change. The calibrator measures the real one and pauses the tactic when they disagree, or stops the bot.
- On Sunday it stopped us once, on a deal that *gained* less than predicted. Annoying, but it is the behaviour we asked for. We fixed the threshold with a test and redeployed in minutes.
- Where: [agent/calibrate.py](agent/calibrate.py), [data/report.txt](data/report.txt).

**5. Read the clock from the wall, not from the script.**
- Saturday's data showed the organisers re-anchor each day's events at its real opening. We predicted the Sunday schedule (scenario C) the night before.
- We made the harness derive the dealer day end and the endgame from `clock.closes` and the live schedule every tick.
- On Sunday the server did exactly that, and no one touched a config. A fixed-hours harness would have closed every dealer thread at 11:38.
- Where: `pages.effective_plan`, `python3 bazaar.py clockcheck`.

**6. Two-issue duels as a fitted model.**
- We fitted the duel value to `(s·(p − L) + sign·|w|·days)·(1 − decay)^rounds`, which matches **95/95 deals**.
- The day sign is read from the server's own `days_meaning` and kept in the World only as a derived `days_sign`, so no text leaks in. A buyer sends 0 days, a seller 10.
- Before the fix: Duels II, 44/68 deals. After: **Duels III, 57/68 (84 %)**, total result 791.6 → 1,187.6, none below our limit.
- Where: [agent/tactics/duels.py](agent/tactics/duels.py), [data/duels-summary.txt](data/duels-summary.txt), and [run_duel_eval.py](run_duel_eval.py), which plays the tactic against 10 rival archetypes with bootstrap confidence intervals.

**7. Ask the people you trade with, without asking.**
- Rival multipliers are secret, so Santi built a **Bayesian estimator** over the 720 possible assignments of multipliers to sets. It is fed only by public trades and score jumps.
- It ranks which teams are likely to pay for a given card, and which ones would compete with us for it.
- Where: [agent/affinity.py](agent/affinity.py), [affinity.py](affinity.py); [afinidad_propia.py](afinidad_propia.py) runs it blind on ourselves to measure how well it guesses.

**8. A market with its book on the table.**
- The free stall matches the Market Test blind. On Sunday we opened our own board venue with a broker that matches like the stall and adds cross-run pairs the stall never makes. It records the whole synthetic book **before** matching.
- Hard test: 96.7 % efficiency, the same 0.5 bench score as the stall, with no session lost. The books are in [data/market-test/](data/market-test/).
- We also ran matchmaking announcements naming real bids and holders.
- What we did not achieve: organic trades between other teams on our venue. We say so in [docs/limitations.md](docs/limitations.md).

**9. Red team first, then an overnight adversarial audit.**
- Friday night: three competing designs were scored ([docs/history/designs/](docs/history/designs/)), and a red team listed every shortcut to the wire before a line of the harness was written.
- Saturday night, with the game closed: an orchestrated multi-agent audit ran 11 independent audits. Each bug finding went to separate agents told to refute it. What survived was fixed with a regression test that fails on the old code: 74 commits overnight. Then came a simulated Sunday under three clock scenarios.
- Where: [docs/journey.md](docs/journey.md).

**10. Honest negatives are evidence too.**
- The broker we prototyped never beat greedy matching. A small RAG did not improve recall. Opening a venue on Saturday would have cost 270 P for no measured gain.
- We kept the baseline each time and wrote down why. Our limitations are listed, not hidden.

---

## Craft

| | |
|---|---|
| Architecture | Frozen contract (`agent/contracts.py`), one owner per module, pure tactics that only propose. A single-writer lock and an operator inbox: even manual orders go through the same Gate (`bazaar.py do`) |
| Safety | Fail closed everywhere. Any response that is not clean `ok` / `deferred` / `refused` is `unknown` and freezes its domain. Missing data refuses. A broken journal stops the bot. A STOP file halts writes within the tick |
| Evidence | A hash-chained write-ahead journal: every intent, result, refusal, prediction, measurement, pause and operator command. It verifies end to end ([data/](data/README.md)) |
| Tests | 911 tests, stdlib only, isolated from the key and the network: guards, Gate, transport fault injection, chaos (deaths mid-write), a fake server with dealer, team and duel bots, the Friday replay, and three Sunday clock scenarios. CI on Python 3.9 and 3.12 |
| Operations | `selftest` per stage, bound to the code hash: a tactic only arms if its stage is green for the exact code running. Dry mode with the same budgets. `clockcheck` and `status` with zero writes |
| Secrets | The key only in `.env` on one machine. Redaction by pattern and by value. Verified: no key in any shipped file |
| Docs | [Architecture](docs/architecture.md) · [journey](docs/journey.md) · [limitations](docs/limitations.md) · the full Spanish contract with invariants INV-01..23 and the test that proves each ([harness-spec](docs/harness-spec.md)) |

---

## The weekend, round by round

### Friday (round 1): from 13th to 2nd in one evening (closed 7th)

#### The climb

```
rank
  1 |
  2 |                                                    ● tick 75  27.39  SAL page complete
  3 |
  4 |
  5 |
  6 |                                      ● EXP-007  14.55  SAL-08 bought at 24
  7 |
  8 |
  9 |
 10 |                    ● EXP-005  10.46  first duplicate sold to a team
 11 |
 12 |
 13 | ● ─────────────────● welcome deal only (5.91), then SAL-02 at 9 (7.54)
    +------------------------------------------------------------ time
```

| When | What we did | Score | Rank |
|---|---|---|---|
| tick ~25 | Only the fixed-price welcome deal (pack at 17). Same score as four other teams. | 5.91 | bottom half |
| EXP-002 | Haggled a pack with a 20 P limit. Abuela's floor was 22-23, so we walked away with no deal. | — | — |
| tick 45 | Rubén's pilot: SAL-02 bought from Abuela at **9** (she asked 12). | 7.54 | 13th |
| tick 53 | **Pivot.** Listed our duplicates on El Rastro at 9 P. t14 bought LAT-04. | 10.46 | **10th** |
| ~tick 60 | Sold SAL-01 and LAV-03 at 9 as well. `neg_points` went from 6.8 to 20.9. | ~13 | — |
| ~tick 65 | **SAL-08 bought at 24.** Abuela accepted our price after 2 rounds. SAL page at 9/10. | 14.55 | **6th** |
| ~tick 68 | Measured the page bonus: SAL-10 was now worth **149.9** to us, up from 77. Posted a public bid of 80 P (t13 was bidding 55). | — | — |
| tick 75 | We hold SAL-10. The SAL page is complete, the first full page on the board (9 teams had one by Friday's close). | **27.39** | **2nd** |

---

#### What turned it around

##### 1. We measured the scorer instead of guessing
Before and after every action we logged `/api/me → score`. Two numbers changed our strategy:

| Action | Effect on score |
|---|---|
| A good dealer deal (SAL-02 at 9 with Abuela) | `ladder_points` **+0.014** |
| Selling one duplicate common to another team at 9 P | `neg_points` **+6.8**, exactly 9 − 2.2 (that card's value to us) |

That showed **`neg_points` is value gained in our private primas, 1 to 1.** A duplicate is worth 2 P to us and 9 P to a team missing it, and the 7 P difference goes straight into our score. Everyone else was still focused on haggling with Abuela. We moved our effort to trading with other teams.

##### 2. We used the public feed as free intel
`/api/feed` shows every team's dealer haggles and trades. From it we:
- **Mapped Abuela's concession curve** (pack 30 → 26 → 25 → 24 → final 22-24; commons 12 → 10 → 9; uncommons 29 → … → 21-24). This set our limits *before* opening a thread.
- **Reverse-engineered the leaders.** The top 4 at tick 50 were exactly the 4 teams in Friday's only two rare trades. Both sides gained because each priced the card at its own multiplier. That is where the big points were.
- **Built an affinity map of rivals** from what they buy and sell (t10 buys LAV, t13 buys SAL and MAL, t14 and t07 buy LAT). It told us who would pay for which duplicate, and that **t13 was our competitor for SAL-10**.

##### 3. We undercut the wall
El Rastro had a wall of commons listed at 10-12 P, probably from teams opening packs to resell. We listed ours at **9 P, the lowest price on the board**. The buyer pays the fee (5% + 1 P), so we kept the full 9. Three sold within about 15 ticks.

##### 4. We corrected our own buy rule after it cost us
In EXP-004 we walked away from SAL-08 at 23 P because it was above the seller's floor we had observed. That card was worth **27.5** to us, and t13 bought it at 24. We wrote it up as decision **D-007**: *for a card we want, the walk-away price is our `your_value`, not the seller's floor. Money does not score; card value does.* In the next attempt (EXP-007) we used steps of 3 P with the new limit. Abuela accepted our 24 in 2 rounds. Rank 6.

##### 5. We went for the page bonus while others bought packs
We tested whether the page bonus was real by checking `value("SAL-10")` once SAL reached 9/10. It jumped from **77 to 149.9** (+25% of the page). The last card of a page is worth almost double. We bid 80 for it in public, well under our 149.9 and well over t13's 55. At that moment it was the only complete page in the game. The +50 it scored turned out to be the per-deal cap (knowledge P-07, S-05).

---


### Saturday (round 2): from 7th to 2nd

Friday closed 7th (19.19). Saturday closed **2nd with 31.26** (negotiating 23.76, market 7.5), behind t10 (37.58). Every number below is rebuilt from our journal and the public feed (`docs/knowledge.md` S-17..S-33).

**A new harness overnight.** Friday's scripts had cost us points: a seller-side bug listed every copy of a card, and a second writer sold below our limit. So on Friday night we rebuilt the agent as a harness with one write path:
- every write is an `Intent` that passes the guards in one **Gate** and leaves through one transport;
- a dry mode, a per-stage `selftest` before going live, a STOP file and a single-writer lock;
- a hash-chained journal that pairs each write with its predicted and measured effect;
- dealer and rival text never enters the agent's view of the world.

On Saturday the server refused 0 of our 1,079 writes. All 372 refusals came from our own guards.

| When | What happened | Score | Rank |
|---|---|---|---|
| 09:30–10:45 | El Retiro (×1.3 for us) built to 9/10 from the two dealers, always below our value, so each buy filled a ladder slot at no cost. The last card came from another team on a public bid at 49 P: **+50 exactly**, which confirmed a per-deal cap | 30.58 | **1st** |
| 10:00–18:00 | Nothing in the agent aimed at empty ladder slots once the page was done, and the score drifted as other teams traded | 27.85 | 8th |
| 12:00–13:20 | Duels I: 30 of 34 duels closed, never outside our limit | | |
| 18:00–21:15 | Level 4 (Los Pícaros) tried 9 times to slip a different card into an offer. The Gate reads the structured offer, not the words, and accepted none. We bought SAL-11 at 139 from them and sold it to Pilar (level 3) at 199 | 30.01 | 4th |
| 21:18–22:55 | Duels II added a second issue, delivery days, and our deal rate fell to 65 %. The fix for the days sign never reached the tactic, because the sensor drops free text by design, so we sent a neutral 5 days with a worst-case margin. Found live, fixed in the sensor (`5ee5593`), redeployed mid-session | 28.20 | 7th |
| 22:00–22:40 | Last card of La Latina bought from another team (+50). We **flagged** the three clearest Pícaros tricks: +10 each | **31.26** | **2nd** |

**An unscheduled shock: the +400 P Payday** ([data/payday-analysis.txt](data/payday-analysis.txt)).
- At 20:58, with two hours of round 2 left, the organisers gave every team +400 P: "Only deals score, never cash you hold".
- It was not in the published schedule, which listed 150 P on Saturday morning and 150 P on Sunday.
- The same cash was worth very different amounts depending on each team's plan:
  - Teams that had sunk 270 P into their own venue were short of cash. They converted it at once: +4.8 deals each on average and +0.49 negotiating. t10 made +9 deals (+2.98) and t12 +6 (+2.43).
  - Teams on the free stall made +1.0 deals on average and lost 0.11 negotiating. The score is relative, so the field's new deals raised the bar for everyone else: t05, t15 and t02 dropped 1.4–2.0 points without trading.
- Our case:
  - We had 131 P before the grant and had budgeted our cash for Sunday's Chamberí (our ×1.6 set, released only in round 3).
  - We spent 72 P of the 400 on Saturday (LAT-10 from a team, +50) and kept the rest.
  - Our rank still improved, 4th → 2nd, but the gap to t10 widened from 4.59 to 6.32 in those two hours.
- **How the gainers used it** (public settlements):
  - **Epics from Los Pícaros, 137–155 P each.** The feed shows 11 bought after the grant against 1 before it.
  - **Epic resales between teams at 195–216 P.** Team trades score on both sides.
  - **Dealer-to-dealer loops**, which fill level 3 and 4 ladder slots.
  - t12 and t04 spent about the whole grant (net 405 and 380 P out) in those two hours. These were exactly the plays we had already made with our own cash before it: SAL-11 from Los Pícaros at 139, SAL-11 to Pilar at 199, ladder 0.214 → 0.366. Our level 3 and 4 slots were full.
  - **In short, the grant subsidised the late movers.**
- **Our estimate of the cost to us:**
  - About −0.5 to −1.1 negotiating points on Saturday's board, which is −0.3 to −0.7 on the final score. Three methods: the erosion of teams with no deals, our own point budget, and the leader's pace (details in the data file).
  - It did not change our Saturday rank, and t10's pace was the same before and after it.
  - The same 400 P paid for our Chamberí on Sunday.
- We did not change strategy in reaction. The cash went into Chamberí on Sunday, completed in about 12 minutes.

**What we measured on Saturday** (and the docs now use):
- A ladder slot is worth (share of the dealer's range) × level/45.
- Two-issue duels follow `(s·(p − L) + sign·w·days)·(1 − decay)^rounds`; this matches all 44 Duels II deals (95/95 with Duels I, knowledge S-26).
- The duel part of the score is a mean per duel, so a no-deal pulls it down.
- Market per round = 22.5 × bench + 7.5 × organic. Our free stall earns half the bench; t10's lead is trades between other teams on its venue.
- The calendar re-anchors each day at its real opening time.


### Sunday (round 3, Chamberí): the final day

Saturday closed 2nd. The night was spent on an orchestrated audit of the harness, with the game closed (see [docs/journey.md](docs/journey.md)):
- 11 parallel audits;
- an adversarial check of every bug finding;
- the confirmed bugs fixed, each with a regression test (commits `249808c..9070665`);
- a full Sunday rehearsed in the simulator under three clock scenarios.

| When | What happened |
|---|---|
| 09:15 | The organisers re-anchored the Sunday schedule, as our Saturday data predicted. The harness derived the dealer day end (13:55) and the endgame (14:25) from the live clock, so no config change was needed |
| 09:20–09:35 | Chamberí (×1.6 for us) completed from three dealer levels in parallel: Abuela for commons, El Chato for uncommons, Los Pícaros for rares and the epic. The closing card came from a team bid. **4 album pages complete** |
| 09:27 | A team bid 238 for our SAL-11 epic while the dealer offered 157. We spotted the bid because the Gate refused our own accept (`G13.listed`: the card was still offered to the dealer); we closed the dealer thread and sold to the team for **+27** |
| 09:32 | A live bug caught by our own safety net: the calibrator's daily-surprise threshold stopped the bot on a deal that *gained* less than predicted. We fixed it, added a test, redeployed and logged it |
| 09:30 | Three more "level A" Pícaros tricks flagged: **+30**. The cap of three scoring flags is per round |
| 10:09 | We opened our own board venue (v28) with a broker. On the hard Market Test it matched **96.7 % of the possible gains** (bench 0.5, the same as the stall, at zero risk) and recorded the full synthetic book for the first time |
| 10:20 | **1st in negotiation (24.89)**, 3rd overall, 0.88 behind the leader. All the gap was in organic market-making |
| 11:00 | Duels III with the day-sign fix: **57 of 68 duels closed (84 %, the field 75 %)**, up from 44 of 68 in Duels II, result 791.6 → 1,187.6, none below our limit |

**Final standings:** the organisers' leaderboard at the 15:00 freeze (Grand Final at 14:00 still to play when this was written).

---

## What went wrong, and what we changed

| When | What broke | What we changed |
|---|---|---|
| Fri | A seller-side bug listed every copy of a card, and a second writer sold below our limit | Rebuilt as a harness with one Gate, protected copies (INV-06) and a single-writer lock (INV-22) |
| Fri | We walked away from SAL-08 at 23 when it was worth 27.5 to us | Decision D-007: the walk-away price is our value, not the seller's floor |
| Sat 09:42 | Fail-closed went too far: `G04.threads` counted 16 old threads and blocked every new one | Count only open threads; the fix went live within minutes |
| Sat | After the RET page, nothing aimed at empty ladder slots, and the rank drifted 1st → 8th | The ladder plan became explicit: three deals per level, highest levels first |
| Sat 21:18 | Duels II sent a neutral 5 days on every message: the sign fix never reached the tactic, because the sensor drops free text by design | Derive `days_sign` in the sensor from the server's own wording. Duels III: 84 % deals |
| Sat 22:55 | The machine slept for 48 minutes and the bot missed the last ticks | Detached runner, power settings, `STALE?` warning in `status` |
| Sun 09:32 | The calibrator stopped the bot on a deal that gained less than predicted | Threshold −5 → −60, with a test; real losses still stop the bot |
| Weekend | 282 refusals were redundant thread closes (`G33.not_open`) | A walked-out thread counts as closed (`f9b4e2e`) |

## Decisions we would defend

| Question | Our answer | Evidence |
|---|---|---|
| Why not buy everything from dealers? | Dealer gains score 0 and dealer losses count in full. Dealers are for ladder slots, teams for page closers | P-03, P-04, P-07 |
| Why did you not open a venue on Saturday? | Saturday data showed nobody beat the free stall on the bench, and 270 P was Chamberí money. On Sunday, with the cards bought, we opened one to see the book | D1 in [bitácora](docs/history/team-notes/bitacora.md), S-23 |
| Do you use an LLM to negotiate? | No LLM at runtime. Code decides every number and accept, and text is only templated output | `agent/talk.py` G60, `tests/test_architecture.py` |
| Is a rise on the board your merit? | We only claim what a settlement shows, because the board is relative and lags | `data/score-timeline.csv` against the journal |
| What is still weak? | Organic market-making, and a two-issue duel can stall when the rival trades price for days | [docs/limitations.md](docs/limitations.md) |

## How we worked

| Who | Role |
|---|---|
| **Jorge** | Lead and operator. Architecture of the harness, the Gate and the live runs. Ran every manual action, each with an explicit OK and a log line |
| **Rubén** | The negotiation lab and evaluation. Cross-review that found 4 bugs on Friday, Radio Rastro (a news watcher that rates each event for t18), the Pícaros trick detector, and the jury evidence |
| **Santi** | Analyst. The scoring breakdown, rival tracking, the Bayesian affinity estimator, Doña Pilar's playbook, the Voss-style duel plan and the team logbook |

**Working with AI agents.** AI coding agents (Claude Code and Codex) wrote much of the code, under rules that kept them honest:
- a frozen contract;
- one owner per module;
- a test that fails before every fix;
- adversarial verification of every finding;
- "validate everything with data".

The overnight audit was a multi-agent workflow (finders, refuters, builders, reviewers and a completeness critic) that ran while the team slept. No agent had a path to the game except through the Gate.

**Habits:**
- a hypothesis before each run and the result after (Friday's EXP-001..008);
- decisions with dates and their evidence;
- a list of our own mistakes;
- one person with the key at a time;
- the memory of the event kept in [docs/history/](docs/history/README.md): handoffs, plans, teammates' notes and the superseded code.

---

*Every number on this page can be traced to [data/](data/README.md), [docs/knowledge.md](docs/knowledge.md) or a commit. If one cannot, it is a mistake: tell us.*
