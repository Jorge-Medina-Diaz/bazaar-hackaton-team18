# Strategy v2 (proposal): price everything in our private primas

Team t18 · written Fri 2 Oct, about 19:50 (tick 50), from `RULES.md`, the kickoff deck, and the live `/api/catalog`, `/api/schedule`, `/api/dealers`, `/api/feed` and `/api/leaderboard`.
It keeps the four engines of `STRATEGY.md`. It fixes the dates that are wrong there, fills the gaps, and adds one shared currency for every decision: **edge in our private primas**, computed by `agent/scorer.py`.

## 1. Gaps in v1

| # | v1 says | What the data says | Change |
|---|---|---|---|
| 1 | Benches every 2 h from Sat 09:00; hard bench Sat 01:00 | `/api/schedule`: the **first Market Test is tonight at 22:00** (game hour 3). Saturday has benches at 10, 12, 14, 16, 18, 20 and 22, plus the **hard test at 21:00** (hour 16, not 01:00). Sunday has 10:00 and 12:00. | The broker must be live by 21:45 tonight. |
| 2 | "Saturday carries most of the game" | Rounds are averaged: Fri ×0.5, Sat ×1, **Sun ×1**. Sunday's 6 h weigh as much as Saturday's 14 h, so a Sunday hour is worth about 2.3 Saturday hours. Sunday has only 2 benches, so each one weighs more. | Do not run down cash or the bot on Saturday. Plan Sunday 09:00–14:00 as a peak. |
| 3 | "Work towards the level-2 unlock" | `/api/dealers`: `early_min_deals: 3` negotiated deals with Abuela. We have **2** (leaderboard). Level 2 is not even announced yet (`/api/levels` is empty). | One more negotiated Abuela deal now. That opens our venue tonight and gives us the head start on L2. |
| 4 | Selling to Abuela "is poor value, mostly skip it" | Copy marginals are 1.0, 0.25 and 0.10. A third copy of a common in a 0.5× set is worth **0.5 P** to us; Abuela pays 5–6 (t08 sold 4 commons in **one** deal for 23). | Dump duplicates in bundles. The scorer flags them as `SELL to abuela`. |
| 5 | "Find our high-multiplier sets from `your_value`" (no method) | The multipliers are fixed for the game. `value()` on an unheld card gives book × multiplier, so 3 calls per set measure them (the scorer does 18 calls once and caches them). | Calibrate before anything else. Every engine reads `logs/multipliers.json`. |
| 6 | Haggle **cheap commons** to the floor for ladder points | Only the best 3 deals per dealer count for the ladder. Beyond those, what a deal is worth depends on the set: an uncommon at about 23 P is worth 50 P to us in a 2× set and 12 P in a 0.5× set. | Use deal slots (8 per hour) on our top-multiplier sets. Rank each slot by `buy_edge`. |
| 7 | Chokepoint doc: accumulate rares "from dealers" | Abuela sells **no rares**, and `sobre_barrio` never contains one. Only **18 rares exist** across the 8 rare cards (1–4 copies each), one per team from the starting hands. A page needs both rares of its set. | Rares are the page bottleneck, and they only move team to team. See §3.3. |
| 8 | Price rares at book | Two rare team trades filled at about 68 (book is 70). To a team with that set's top multiplier and a nearly complete page, a rare is worth 70 × mult **plus** the page bonus (25% of the page, about 66 × mult). | Never sell a rare at book. List it near the top peer's value and buy rares at book from teams for whom that set is low. |
| 9 | Market-making is the bench only | "Value created between other teams on your venue" also scores. El Rastro charges 5% + 1 P per card; fees never score. | Open a **near-zero-fee** venue and pull Rastro flow onto it. The broker matches team want-lists all day, not just during benches. |
| 10 | Scheduler decides "which accept is worth the most" | One accept per tick for the whole team (about 240 tonight). Until now there was no shared unit to compare a duel accept, a dealer deal and a board offer. | Edge in P from the scorer is that unit. Duel accepts come first (the pie decays 6–10% a round). |
| 11 | No cash plan | 400 now, +150 and a pack Sat 09:00, +150 Sun 09:00. A venue locks a 250 P bond plus a 20 P fee. | Keep ≥ 270 P liquid until the venue is open. |
| 12 | We guess the scoring function | t10 has 28 negotiating points from 5 deals, t08 has 25 from 4, and we have 7.5 from 2. The ladder share seems to dominate early. | After every deal, log the change in `me()["score"]`. Fit what scores (opening vs fill, buy vs sell), and correct the haggler from it. |
| 13 | New sets not planned | El Retiro opens Sat 09:00 and Chamberí Sun 09:00, both with 0 minted. Abuela will sell their commons and uncommons from the first tick. | If RET or CHA is one of our high sets, the first hour of that day goes on its uncommons, before rivals' want-lists form. |

## 2. The scorer (`python -m agent.scorer`)

It shows one view of every card, in our private primas:

- **Our cards**: copies held, `keep` (what giving one away costs us, including a page bonus we would break), `next` (one more copy), market value, the best exit (board bid net of fee, or Abuela's typical bid), `sell_edge`, a suggested ask, and an action (`SELL`, `LIST @x` or `KEEP`).
- **What to buy**: `buy_edge = next − buy_at` for every released card, where `buy_at` is the cheaper of the board (ask + fee) and Abuela (median of recent fills, all teams). It also shows how many teams asked for that card.
- **Pages**: per set, the multiplier, cards held out of 10, missing cards, which ones have no seller, completion cost, gain (including the 25% bonus) and net.
- **Board offers**: every open offer on every venue, scored as if we accepted it now.
- **Packs**: the expected value of a pack *to us* (our duplicates count at 0.25 and 0.10) against its typical price.
- **Price levels**: Abuela's opening asks, lowest final asks, best final bids and fill medians by rarity, from every team's threads. This is the haggler's floor model.
- **Rivals**: album fill, completed pages and deal counts from the public leaderboard.

How it works:

- Public data goes through a keyless client, so the scorer never uses up the team key's 5 requests per second. With the key it calls `me()` and `my_offers()` once per refresh, and `value()` only at calibration.
- Fills are appended to `logs/fills.jsonl`, so the price history outlives the feed's ~500-event window.
- Peer value: every team has the same six multipliers, shuffled. Once we know ours, we know how much the best-placed rival values any card (book × our top multiplier). That sets our asks. For commons and uncommons the ask is capped at Abuela's all-in price, because nobody pays a team more than she charges.
- `--watch 60 --html logs/market.html` keeps a live local page. It holds our private values, so **never publish or commit it** (`logs/` is gitignored).
- `--json` is the feed for the other engines: the haggler reads `buy_edge`, the swapper reads `ask` and `sell_edge`, and the scheduler ranks accepts by edge.

## 3. The strategy

### 3.1 Tonight (Friday counts half): unlock, calibrate, get the broker live
1. **Now:** run the scorer with the key to calibrate the multipliers. Note our top two and bottom two sets.
2. **Third negotiated Abuela deal** for the level-2 unlock. Pick a card with a high `buy_edge` (an uncommon in our top set), open low and kind, and step up 1–2 P.
3. **Bundle-sell duplicates** to Abuela from our lowest set (one deal, several cards).
4. **21:00** practice duels: log everything.
5. **By 21:45** open a `board` venue at the lowest fee. If L2 has not unlocked yet, the free stall still earns half the bench points. Run the broker at the **22:00 bench**.

### 3.2 Dealer ladder: three excellent deals per dealer, per round
- Assume the ladder is scored per round (to verify with fact 12), so get three excellent deals again on Saturday and Sunday mornings.
- The best observed shares: pack at **17** (opening 30), commons at **7** (opening 12), uncommons at **21** (opening 29). Abuela's lowest final asks are in the scorer's price table.
- After the best three, every further slot goes to the highest `buy_edge` in our top sets, or to duplicate bundles out.

### 3.3 Pages: rares decide everything
- Choose **one target page**: the highest-multiplier released set whose two rares we can realistically get. The Pages table ranks by net.
- Buy its commons and uncommons from Abuela (about 9 and 23 P). Post `want card:XXX-09/10` bids on El Rastro **and** open direct threads with the teams that hold them. Ownership history is on `/api/cards/{id}`, and the feed shows who pulled what.
- Our own rare: if it is in a low set, do not sell it at book. Ask about 85% of the top peer value and offer it in a swap for a rare in our target set. Two rares crossing between teams that each value the other's set is the biggest single value-created trade in the game, and it scores for both sides.

### 3.4 Market-making: two sources of points
- **Bench:** the limit-estimating broker from v1. The hard test (Sat 21:00) has firmer, more impatient traders, so cross early rather than wait.
- **Real flow:** fee 0–1%, a clear venue name and description, and a broker that pairs crossing team offers every tick. The value other teams create on our venue scores, and Rastro's 5% + 1 P is a bad deal for a 10 P common.
- Never trade on our own venue (`self_venue`). Our own team trades stay on El Rastro.

### 3.5 Duels
v1 plan unchanged. Additions:
- Duel accepts outrank everything in the per-tick accept budget.
- In two-issue duels (Sat 18:00 clashes with a bench), the broker and the duel bot run in one process, so they share the rate limit.

### 3.6 Flags
For any dealer after level 1, compare the price in a dealer's words with the structured offer. A mismatch is a flag candidate, but flag only clear contradictions: a wrong flag costs.

## 4. Times (Madrid)

| When | What |
|---|---|
| Fri now–21:00 | Calibrate, third Abuela deal (L2), dump duplicates, scorer on `--watch` |
| Fri 21:00 | Practice duels (not scored) |
| Fri 22:00 | **Market Test #1**; team venues go live |
| Sat 09:00 | El Retiro released; +150 P and a pack for everyone; Saturday's three ladder deals |
| Sat 10, 12, 14, 16, 18, 20, 22 | Market Tests |
| Sat 11:30 | Duels I (price only, 16 ticks, decay 6%) |
| Sat 18:00 | Duels II (price + days, 2 rounds, decay 8%), at the same time as a bench |
| **Sat 21:00** | **Hard Market Test** (12 firmer, impatient traders) |
| Sun 09:00 | Chamberí released; +150 P; Sunday's three ladder deals |
| Sun 10:00, 12:00 | Market Tests (only two, so each weighs more) |
| Sun 11:00 | Duels III (two issues, 12 ticks, decay 10%) |
| Sun 14:00 | Abuela closes; Grand Final duels |

## 5. Open questions to settle with data
1. What exactly is the ladder's "price range": opening to floor, or list to opening? Is it reset per round? (Log the score change after each deal.)
2. Does a duel accept use up the team's one accept per tick?
3. Does `value()` answer for unreleased sets (RET, CHA)? The scorer's calibration tries it.
4. Is the page bonus 25% of the page's first-copy value? Check `next` against `value()` on our last missing page card (`--recalibrate` stores the checks).
