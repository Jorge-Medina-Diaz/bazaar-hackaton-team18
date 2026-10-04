# How we adapted: three days, measured

We kept one rule all weekend: **measure what the scorer pays, write it down as a numbered fact, then change the plan or the code**.
The facts live in [knowledge.md](knowledge.md) with ids (P- scoring, V- values, D- dealers, U- duels, M- market, S- Saturday live). knowledge.md stops before Sunday; Sunday's measurements are in `data/`. Each one carries its evidence and a confidence level. The plan ([strategy.md](strategy.md)) and the numbers in [config/plan.json](../config/plan.json) cite those ids.

## The loop

```
 live journal + public feed + /api/me before/after each action
        │
        ▼
 fact with an id and evidence (knowledge.md)  ──►  refuted claims are kept, with the evidence that refuted them
        │
        ▼
 a change in config/plan.json (numbers) or code + a regression test that fails on the old code
        │
        ▼
 selftest green for the new code_hash ──► redeploy between duels ──► the calibrator checks prediction vs measurement
```

Online, the calibrator compares every write's predicted score change with the measured one, pauses a tactic on a hard disagreement, and can learn the +50 cap per team deal. That detector never fired live; the cap was confirmed offline (knowledge P-07, S-05). Offline, the loop is human-driven but always data-first: no parameter changed without a fact behind it.

## Friday: from 13th to 2nd (round 1)

- **We measured the scorer before playing it.** A good dealer deal moved `ladder_points` by +0.014. Selling one duplicate to a team moved `neg_points` by +6.8, exactly price minus our value (P-03). So team trades, not dealer volume, pay.
- **Dealer gains score 0; only dealer losses count** (P-04, reproduced on 16 measurements). We stopped "winning" against dealers and used them only for album cards and ladder slots.
- **The page bonus is worth ~0.25 × the page.** The last SAL card was worth 149.9 to us, so we bid 80 for it while others bid 55, and completed the first full page of the game.
- The details and the climb are in [SHOWCASE.md](../SHOWCASE.md).

## Friday night: the harness v2, and a red team

The Friday scripts worked, but a review found too many ways to write around the rules. So we rebuilt it as a harness with one write path:
- **Red team first.** Three design proposals were scored, and a red team listed every shortcut to the wire: the SDK's own `_call`, a new `Bazaar(...)`, raw urllib, the broker. The result is the three-layer barrier (permit, audit hook, AST test) and fail-closed response classification.
- **A contract before code.** [harness-spec.md](harness-spec.md) fixed every signature at 03:30. Each file had one owner module (M0–M18), and each invariant names the test that proves it.
- 779 tests were green when the doors opened at 09:00 on Saturday.

## Saturday: from 7th to 2nd (round 2)

What we learned live and turned into code or plan:

| Signal | Fact | Change |
|---|---|---|
| The scorer gave **+10 per correct flag** on a Pícaros trick (first 3 per round) | S-28 | Read-only `flag_candidates.py` finds "level A" tricks: the text names the card, the structured offer gives another. Hand-flagged with the lead's OK: +30 on Saturday, +30 again on Sunday (the cap is per round) |
| Pícaros swap the card inside counter-offers and send fake finals | D- facts | G10/G11 fingerprint re-read; the dealer tactic closes on a trick final without countering |
| **Duels II: we sent 5 days in 318 of 318 messages** and demanded a worst-case margin of ~15 P | S-26, S-27: value = (s·(p − L) + sign·\|w\|·days) · (1 − decay)^rounds, matched on 95/95 deals | The sensor derives the day sign from the server's own `days_meaning` text: a buyer sends 0 days, a seller 10. A sign that contradicts the role falls back to the conservative side and raises an alarm |
| Market points: the free auto stall already scores half the bench; nobody beat it on Saturday | S-23, S-24, S-25 | We kept the stall and played organic market-making with announcements |
| The machine slept 48 min, and restarts cost 87 ticks | S-31 | Detached runner, power settings, "never restart during duels" rule |

## Saturday night: an audit workflow

With the game closed, we ran an orchestrated audit while the team slept:
- 11 parallel audits (the workflow's own report; the commits are `249808c..9070665`): incoming documents, our traces, rivals, duels, core harness, tactics, schedule, market, easter eggs, branches and repo hygiene.
- Each bug finding was then sent to independent agents asked to refute it.
- **47 bugs survived verification and were fixed, each with a regression test** that fails on the old code. Examples:
  - The days margin was too strict.
  - Duels with a silent rival could never close.
  - The 4-duel freeze blocked the whole dealer ladder.
  - A restart cancelled a manual listing.
- Then came four review lenses (duels, Gate safety, plan consistency, end-to-end simulation of Sunday in three clock scenarios), a fix-up round, a completeness critic and a gap fix.

The most important finding was about the clock:
- The schedule showed Sunday events at fixed game hours, but Saturday's data proved the organisers re-anchor them at opening.
- A harness with fixed hours would have closed every dealer thread at 11:38.
- `pages.effective_plan` now derives the day end and the endgame every tick from `clock.closes` (wall time) and the live schedule. The fixed hours stay only as a fallback.
- On Sunday it read scenario C correctly at 09:15.

## Sunday: round 3 (Chamberí)

- **09:15–09:35:**
  - 4 album pages complete: CHA bought from three dealer levels in parallel, with the closing card bought from a team.
  - SAL-11 sold to a team bid at 238 while Pilar offered 157: +27, settled at 09:27 (`data/score-timeline.csv`, tick 1494).
  - 3 more correct flags at 09:30 (+30), and the Castizo easter-egg badge.
- **A live bug, caught by our own safety net.** The calibrator's daily "negative surprise" threshold (−5) stopped the bot on a deal that *gained* +23 against a +50 prediction. Fail closed did its job. We raised the threshold to −60 (real losses stay with `LOSS_STOP`), added a test and redeployed in minutes.
- **The Market Test with our own venue.** We opened a board venue (v28) with a broker that matches like the stall, plus cross-run matches the stall never makes. It recorded the full synthetic book before matching, which the stall never shows. Result on the hard test: bench 0.5, the same score as the free stall, at **96.7 % efficiency** (`/api/me` `bench_efficiency` 0.967 at 10:20). The books are in [data/market-test/](../data/market-test/).
- **Duels III (11:00)** was played with the day-sign fix: **57 of 68 duels closed (84 %, field 75 %)** against 44 of 68 (65 %) in Duels II, and the summed result went from 791.6 to 1,187.6, with no deal below our limit ([data/duels-summary.txt](../data/duels-summary.txt)). After it, the tactic gained an ultimatum two ticks before the deadline (`4460a91`): three of the four Duels III no-deals had ended 8–11 P short of our limit. A pre-flight review had simulated 12-tick, decay-0.1 duels through the real Gate guards; every message and accept passed. The Grand Final (14:00) is after the end of these traces.

## What we would keep

- The Gate and the frozen contract made it safe to change strategy fast. 1,645 writes went through the Gate and the server refused none (one `unknown` froze its domain and was reconciled, as designed); our own guards refused 428 more first (most were redundant thread closes from a bug we then fixed).
- Numbered facts with evidence beat intuition. Several confident team claims were refuted with data, and the refutations are kept in knowledge.md.
- Process notes from the weekend are preserved in [history/](history/): handoffs, the Sunday plan, teammates' notes and the superseded scripts.
