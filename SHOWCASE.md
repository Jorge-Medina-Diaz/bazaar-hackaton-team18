# Team 18: from 13th to 2nd in one evening

**The Bazaar · Cromos de Madrid**, Friday 2 Oct 2026 (round 1)
Team: Jorge, Rubén, Santi (t18)

| | Early Friday | Tick 75 |
|---|---|---|
| Rank | **13th of 18** (tied with the teams that had only the welcome deal) | **2nd of 18** |
| Negotiating score | 5.91 | **27.39** (0.44 behind 1st) |
| Deals | 1 | 8 (1st and 3rd place each have 11) |
| Complete album pages | 0 | **1, the only one in the game** |

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
| tick 75 | We hold SAL-10. The SAL page is complete, the only full page on the board. | **27.39** | **2nd** |

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
We tested whether the page bonus was real by checking `value("SAL-10")` once SAL reached 9/10. It jumped from **77 to 149.9** (+25% of the page). The last card of a page is worth almost double. We bid 80 for it in public, well under our 149.9 and well over t13's 55. We now own the only complete page in the game.

---

## How we worked

Three people, three tools (Claude Code, Codex, scripts), one key, and Friday ticks of 60 seconds.

| Who | Contribution |
|---|---|
| **Jorge** | The live engine: generic haggler (`agent/haggle.py`, concession curve + `AC_next` acceptance), dealer profiles as data, `market.py` (deal scanner + `sell-dups`), `scout.py` feed reader. Ran the experiments that produced the climb. Kept the playbook. |
| **Rubén** | Offline negotiation lab: `negotiation_policy.py`, a step-by-step simulator, **17 tests** and comparative evaluation. Ran the first real pilot (SAL-02 at 9). Ran a cross-review (`RECHECK.md`) that **found 4 bugs** in teammates' code before they cost anything. |
| **Santi** | Strategy v1 → v2: the scoring breakdown, the read on how t10 was leading, the corrected calendar (first Market Test is *tonight*, Sunday weighs as much as Saturday). Built `agent/scorer.py`, which prices every card, offer and pack in our private primas, plus the shared fill history. |

**Habits that made the difference:**
- **Hypothesis before the run, result after.** Every action against the game is a row in `docs/experiments.md` (EXP-001 to EXP-008), with parameters, outcome and the score change.
- **Decisions are dated and reversible.** `docs/decisions.md` records each decision with its evidence and a "revisit if…" condition. D-005 and D-006 were overturned by D-007 within an hour, based on data.
- **We keep a list of our mistakes.** The playbook keeps a table of errors (wrong limit source, rejecting a card we valued above its price, wrong status name, misread offer durations, price logged as 0). Each has its cost and the fix.
- **Structure over words.** The code sets every price and every accept, and `offer_ok()` checks the structured offer before any accept. Text never binds us.
- **One executor per key.** We share an accept quota and dealer threads, so only one person runs against the game at a time.

---

## Next steps (Saturday and Sunday, which weigh 2× Friday combined)

- **Market-making (30 points, we have 0 so far like everyone else):** reach level 2, open a near-zero-fee `board` venue, and run a broker that estimates traders' hidden limits instead of matching on quotes.
- **Duels:** a price-and-days bot that never crosses our limit and closes fast while the pie shrinks.
- **More pages:** El Retiro (Sat) and Chamberí (Sun) start at zero copies. If one is a high-multiplier set for us, the first hour of that day goes on its uncommons.
- **Rare-for-rare swaps** with teams whose high set is our low one. This is the biggest trade in the game where both sides gain.
