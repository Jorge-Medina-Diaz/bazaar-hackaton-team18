# Team 18: from 13th to 2nd in one evening

**The Bazaar · Cromos de Madrid**, Friday 2 Oct 2026 (round 1)
Team: Jorge, Rubén, Santi (t18)

| | Early Friday | Tick 75 |
|---|---|---|
| Rank | **13th of 18** (tied with the teams that had only the welcome deal) | **2nd of 18** |
| Negotiating score | 5.91 | **27.39** (0.44 behind 1st) |
| Deals | 1 | 8 (1st and 3rd place each have 11) |
| Complete album pages | 0 | **1**, the first in the game at that moment |

*Friday story below; Saturday (round 2: 7th → 2nd) is in the [last section](#saturday-round-2-from-7th-to-2nd).*

We made fewer deals than the teams around us and still passed them. The change was not about doing more. We measured what the scorer actually pays for, and then we did that.

---

## The climb

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

## What turned it around

### 1. We measured the scorer instead of guessing
Before and after every action we logged `/api/me → score`. Two numbers changed our strategy:

| Action | Effect on score |
|---|---|
| A good dealer deal (SAL-02 at 9 with Abuela) | `ladder_points` **+0.014** |
| Selling one duplicate common to another team at 9 P | `neg_points` **+6.8**, exactly 9 − 2.2 (that card's value to us) |

That showed **`neg_points` is value gained in our private primas, 1 to 1.** A duplicate is worth 2 P to us and 9 P to a team missing it, and the 7 P difference goes straight into our score. Everyone else was still focused on haggling with Abuela. We moved our effort to trading with other teams.

### 2. We used the public feed as free intel
`/api/feed` shows every team's dealer haggles and trades. From it we:
- **Mapped Abuela's concession curve** (pack 30 → 26 → 25 → 24 → final 22-24; commons 12 → 10 → 9; uncommons 29 → … → 21-24). This set our limits *before* opening a thread.
- **Reverse-engineered the leaders.** The top 4 at tick 50 were exactly the 4 teams in Friday's only two rare trades. Both sides gained because each priced the card at its own multiplier. That is where the big points were.
- **Built an affinity map of rivals** from what they buy and sell (t10 buys LAV, t13 buys SAL and MAL, t14 and t07 buy LAT). It told us who would pay for which duplicate, and that **t13 was our competitor for SAL-10**.

### 3. We undercut the wall
El Rastro had a wall of commons listed at 10-12 P, probably from teams opening packs to resell. We listed ours at **9 P, the lowest price on the board**. The buyer pays the fee (5% + 1 P), so we kept the full 9. Three sold within about 15 ticks.

### 4. We corrected our own buy rule after it cost us
In EXP-004 we walked away from SAL-08 at 23 P because it was above the seller's floor we had observed. That card was worth **27.5** to us, and t13 bought it at 24. We wrote it up as decision **D-007**: *for a card we want, the walk-away price is our `your_value`, not the seller's floor. Money does not score; card value does.* In the next attempt (EXP-007) we used steps of 3 P with the new limit. Abuela accepted our 24 in 2 rounds. Rank 6.

### 5. We went for the page bonus while others bought packs
We tested whether the page bonus was real by checking `value("SAL-10")` once SAL reached 9/10. It jumped from **77 to 149.9** (+25% of the page). The last card of a page is worth almost double. We bid 80 for it in public, well under our 149.9 and well over t13's 55. At that moment it was the only complete page in the game. The +50 it scored turned out to be the per-deal cap (knowledge P-07, S-05).

---

## How we worked

Three people, three tools (Claude Code, Codex, scripts), one key, and Friday ticks of 60 seconds.

| Who | Contribution |
|---|---|
| **Jorge** | The live engine: generic haggler (`agent/haggle.py`, concession curve + `AC_next` acceptance), dealer profiles as data, `market.py` (deal scanner + `sell-dups`), `scout.py` feed reader. Ran the experiments that produced the climb. Kept the playbook. *(Friday code, now in `archive/`; replaced on Saturday by the v2 harness.)* |
| **Rubén** | Offline negotiation lab: `negotiation_policy.py`, a step-by-step simulator, **17 tests** and comparative evaluation. Ran the first real pilot (SAL-02 at 9). Ran a cross-review (`archive/docs/RECHECK.md`) that **found 4 bugs** in teammates' code before they cost anything. |
| **Santi** | Strategy v1 → v2: the scoring breakdown, the read on how t10 was leading, the corrected calendar (first Market Test is *tonight*, Sunday weighs as much as Saturday). Built `agent/scorer.py` (now `archive/agent/scorer.py`), which prices every card, offer and pack in our private primas, plus the shared fill history. |

**Habits that made the difference:**
- **Hypothesis before the run, result after.** Every action against the game is a row in `archive/docs/experiments.md` (EXP-001 to EXP-008), with parameters, outcome and the score change.
- **Decisions are dated and reversible.** `archive/docs/decisions.md` records each decision with its evidence and a "revisit if…" condition. D-005 and D-006 were overturned by D-007 within an hour, based on data.
- **We keep a list of our mistakes.** The playbook keeps a table of errors (wrong limit source, rejecting a card we valued above its price, wrong status name, misread offer durations, price logged as 0). Each has its cost and the fix.
- **Structure over words.** The code sets every price and every accept, and `offer_ok()` checks the structured offer before any accept. Text never binds us.
- **One executor per key.** We share an accept quota and dealer threads, so only one person runs against the game at a time.

---

## Next steps as written on Friday (Saturday and Sunday each weigh 2× Friday, so together 4×)

- **Market-making (30 points, we have 0 so far like everyone else):** reach level 2, open a near-zero-fee `board` venue, and run a broker that estimates traders' hidden limits instead of matching on quotes.
- **Duels:** a price-and-days bot that never crosses our limit and closes fast while the pie shrinks.
- **More pages:** El Retiro (Sat) and Chamberí (Sun) start at zero copies. If one is a high-multiplier set for us, the first hour of that day goes on its uncommons.
- **Rare-for-rare swaps** with teams whose high set is our low one. This is the biggest trade in the game where both sides gain.

---

## Saturday (round 2): from 7th to 2nd

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

**What we measured on Saturday** (and the docs now use):
- A ladder slot is worth (share of the dealer's range) × level/45.
- Two-issue duels follow `(s·(p − L) + sign·w·days)·(1 − decay)^rounds`; this matches all 44 deals.
- The duel part of the score is a mean per duel, so a no-deal pulls it down.
- Market per round = 22.5 × bench + 7.5 × organic. Our free stall earns half the bench; t10's lead is trades between other teams on its venue.
- The calendar re-anchors each day at its real opening time.

## Sunday (round 3): Chamberí in 40 minutes, the duels fixed, a venue of our own

**The night before** we ran an overnight audit with independent reviewers that tried to refute each other's findings. It produced about 60 fixes, each with its regression test, and the playbook `docs/plan-domingo.md`. Two of the fixes decided the morning:
- **The clock.** The Sunday schedule was scripted for t = 16.65 while the clock stood at 13.37. The harness now derives the dealer-day end and the endgame from the server's wall-clock close and the live schedule, not from fixed hours. The server re-anchored the day exactly as predicted (scenario C), and nothing had to be touched by hand.
- **The duel days.** A buyer now sends day 0 and a seller day 10. The Gate and the tactic share one sign rule, read from the server's own `days_meaning`. On Saturday we had sent a neutral 5 days on every message.

| When | What happened |
|---|---|
| 09:15 | Clock starts. Round 3 opens, Chamberí (×1.6 for us) is released, and +150 P arrives. Dealers stay paused so that teams' first Chamberí sales reach our El Rastro buyer first |
| 09:23 | Abuela egg sent through the Gate as a template line: **Castizo** badge. We now hold all three badges |
| 09:24 | SAL-11 sold to another team's bid at 238 (**+27**) instead of the dealer's 199. We spotted the bid because the Gate refused our own accept (`G13.listed`) while the card was still offered to the dealer |
| 09:21–09:33 | **Chamberí complete in about 40 minutes.** Rares came from Los Pícaros (58, ~60), uncommons from El Chato (31), commons from the Abuela (9–10), and the closing card from a team's sale into our standing bid at 72 |
| 09:35 | Three firm Pícaros tricks flagged: **+30**. This confirmed that the cap of three scoring flags resets each round |
| 09:32 | The calibrator stopped the bot. A closing-card buy that gained +23 had been predicted at +50, and the daily surprise limit was −5. We redeployed with a −60 limit within minutes; real losses stay with `LOSS_STOP` |
| 10:09 | We opened our own **board venue v28** with a broker (0 % fee), so that we see the Market Test book *before* the cross, which the free stall never showed us. Hard Market Test: **0.967 efficiency**, the same 0.5 bench points as the stall, and no session lost |
| 11:00–11:52 | Duels III: **57 of 68 duels closed with a deal (84 %)**, against 73.5 % for the rest of the field (Saturday's Duels II: 65 % against 77.6 %). Duel points went from 0 to 22.6. No accept and no offer outside our limit |
| 11:55 | El Chato egg, copied from the public feed in two minutes: Team 2 had opened a *buy* thread and asked about the calamares sandwich, so we did the same through the Gate (`chato_buy` template). Free neighbourhood pack |
| 12:28 | **El Taller:** three spare commons worth about 2 P each became an uncommon (LAT-06), sold to Doña Pilar at 16. That filled her third ladder slot |
| 12:53 | Our venue v28 closed after the last Market Test with its bond refunded. It ran at 0.967 efficiency and hosted one trade between two other teams (t01 → t13), brought in by our matchmaking announcements |
| 13:00–13:15 | Before the Grand Final, four independent reviewers attacked the deployed code, the Duels III data, the tick timing and the operations. 110k random duel states went through the real Gate with 0 refusals. Two changes came out of it: silent-rival sellers now go to L+1 at the end (5 of 12 such sellers had ended with no deal), and the 15 s ticks read only clock, account, offers and duels (32 of 33 late refusals came from the full snapshot overrunning) |

We kept a rule all day: **dealer gains score only on the ladder, and a loss counts in full**. With every page complete, no listing anywhere below our value and Don Ernesto's legendaries above what we could pay, we did not spend the remaining cash to "use it": a gold pack would have cost about −175 negotiation points. It went into standing bids below our value instead, which can only add.

### Final standing (Sunday 15:00, doors closed at t 19.34)

**5th of 18 with 32.27** (negotiation 23.27, the 3rd best of the field; market 9.00). Ahead: t05 37.73, t10 35.76, t12 34.51, t03 34.19. The gap to the podium was market making: trades between *other* teams on one's own venue. The leaders earned it with dozens of targeted matchmaking announcements and seller incentives. Our venue hosted one such trade.
Grand Final duels: duel points rose from 22.63 to 27.97. Sixty-eight messages and two accepts were refused as late, because server ticks arrived unevenly (5–25 s). The Gate refused them rather than act on stale data.
What we would keep: the single-write-path harness, the predicted-versus-measured journal, the knowledge base of measured rules, and the adversarial audits. What we would do earlier: market making from Friday evening, with a cadence and a go/no-go metric.
