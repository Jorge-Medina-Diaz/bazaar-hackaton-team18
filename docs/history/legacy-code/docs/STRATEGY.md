# Team 18 strategy: The Bazaar · Cromos de Madrid

We are **t18**. Key goes in `.env` as `BAZAAR_KEY=tk-...` (gitignored). Never commit it.

## 1. How we are scored (and what that means)

| Bucket | Weight | What actually moves it | Our lever |
|---|---|---|---|
| Negotiating | 30 | Duels (share of pie) · dealer ladder (share of each dealer's price range, **best 3 deals per level only**) · value gained in team trades at *our private values* | A duel bot, a patient dealer haggler, a dupe-swapper |
| Market-making | 30 | **Market Test** efficiency (share of possible gains realised on the synthetic bench book) · value created between other teams on our venue | A board-venue broker that estimates hidden limits |
| Judges | 40 | Ideas and craft | Clean architecture, a learning loop, a good demo/write-up |

Never counts: number of trades, fees earned, pack luck. **Quality over activity, everywhere.**

Rounds are days, averaged. Friday counts half. Saturday (14 h) carries most of the game.

## 2. Core principles

1. **Read the structure, never the words.** Before every accept, check `give`/`want`, the counterparty and the price against our limits.
2. **Every action has a limit.** A deal is good only if it beats a computed reservation value: dealer floor estimate, duel limit or `your_value`.
3. **The feed is free intelligence.** `GET /api/feed` shows every team's haggles with dealers, including the dealer's counter-offers. We learn each dealer's concession curve from *everyone's* conversations, not just ours.
4. **One process, one tick loop.** Read state once per tick. Each tick we get one accept and one message per thread, so the scheduler decides which accept is worth the most.
5. **Log everything** (JSONL per tick). That data tunes the bots and is also our judges' story.

## 2b. What the leader is doing (t10, Fri tick 50, 28.1 pts, all negotiating)

Read from the public feed (it keeps only the last 500 events, so ticks 22-50):

- **They buy single cards for one set, never packs.** Abuela deals: LAV-06, LAV-07, LAV-04, LAV-05, MAL-07. They hold LAV-02/04/05/06/07/10, so they are building the LAV page.
- **They snipe El Rastro.** t08 listed LAV-10 (rare) at 70 on tick 46 and t10 took it on tick 49. They also bought t06's LAV-02 at 12.
- **Most likely score source: team trades at private values.** The top 4 (t10, t13, t08, t14) are exactly the 4 teams in Friday's only two rare trades (t08→t10 LAV-10 at 70, t13→t14 LAT-09 at 65). Both sides seem to gain, each at its own value.
- **Their Abuela haggling is mediocre.** Numbers only (`text: null`). Uncommons: 15/18 → +2-3 per step → close at 23-24. Commons: 7 → 9 → take 10. Others got 17 and 7. They take speed over price. **This is where we beat them.**
- They sell off-set spares on El Rastro (MAL commons at 11-12, MAL-06 at 25-35).

**Our takeaway:** copy the sniping and the one-set focus, and beat them on dealer price.

## 3. The four engines (priority order)

**Run order changed after the t10 read:** D (valuation and El Rastro trading) runs from now, alongside A. It is the cheapest lever and appears to be the biggest one.

### A. Dealer haggler (now: ladder points + unlock level 2)
Only the **best 3 deals per dealer** count, scored as share of the price range captured. So:
- Make a few *excellent* deals, not many. Cheapest way: haggle **cheap items** (commons, list ~10) to the floor. A full-share deal on a 7 P card scores like one on a pack.
- A deal at the opening price does not count toward unlocking the next level. Always negotiate.

What we saw of Abuela on Friday (about 40 threads in the feed):
- Pack: she opens at 30 and concedes 30 → 25-27 → 24 → 23 → 22 → 21. Best deals so far: **19** (t17), 21, 22. She accepts *our* price once it is at or above her secret limit for that conversation.
- Common: opens at 12, settles at 9-10, once at 7. Uncommon: opens at 29, settles at 21-25.
- When she buys from us she barely moves: 5-6 for a common, 12-16 for an uncommon. That is poor value for us, so mostly skip it.
- Her final offer comes about 5 rounds in (`final: true`). Small steps earn small steps: she mirrors the size of our increments.
- Two teams got a **17 opening** on a pack (t03, t08) by sending text with no price. Words seem to move her anchor ("Abuela likes kindness"). Worth testing.
- Quotas: 3 packs and 8 deals per team per hour.

- Lowest fills on Friday: **common 7, uncommon 17, pack 19**. Typical: 9 / 22-24 / 21. Our ceiling should be the typical fill, and our target the lowest one.
- **Buy single cards from our best set, not packs.** One deal then pays twice: ladder share now and album value (page bonus) later. Packs are luck, and luck never scores.

**Algorithm:** open low and kind, then raise in increments of 1-2. Stop at our walk-away. Accept her offer only if it is `final` and ≤ our ceiling, or if it is at or below our target. Keep a per-dealer model of the floors seen in the feed and target just above the lowest observed fill.

### B. Duel bot (practice Fri 21:00 · Duels I Sat 11:30 · II Sat 18:00 · III Sun 11:00 · Final Sun 14:00)
- Never cross our own limit (a deal outside it is negative).
- The pie decays 6-10 % per round, so a fast fair deal beats a slow perfect one.
- Price only: anchor at about 70-75 % of the zone we can infer, concede on a decaying schedule, and accept as soon as the rival's offer gives us at least what we would expect after one more round of decay.
- Price plus days: use `your_days_weight` to propose packages. Give the rival the days dimension we care less about and take price in exchange. Infer their weight from their counter-offers.
- Use the practice round to log rival behaviour.

### C. Broker for the Market Test (benches every 2 h from Sat 09:00; hard bench Sat 01:00 game-hour 16)
- Needs **level 2** to open our own `board` venue. Until then the free auto stall earns half the bench points.
- Beat the stall by matching on **estimated true limits**, not quotes:
  - Track each bench trader's quote path across ticks. Quotes relax towards the hidden limit; firm traders never move.
  - Maximise the total realised surplus (max-weight bipartite matching). Prioritise traders who are about to leave.
  - Do not cross early at the midpoint if waiting a tick reveals better pairings, but do not lose impatient ones.
- Set our venue fee as low as allowed during benches. Fees never score, and a fee stops pairs that should cross.

### D. Collector and swapper (team trades and album)
- Value only through `your_value` (`/api/me/value?card=`). Copy marginals are 1.0 / 0.25 / 0.10, and a complete page adds +25 %.
- Find our high-multiplier sets from `your_value`. Buy the cards that complete pages there. Sell duplicates and cards from low-multiplier sets to teams that are missing them.
- Post buy and sell offers on El Rastro (5 % + 1 P fee). Accept other teams' offers only when `your_value` gained minus cash paid is positive.
- **Rastro sniper (copied from t10, made faster):**
  1. At startup and every hour, call `value(ref)` for every card in the catalog. Cache it and rank our sets by multiplier. The top set is the page we build.
  2. Every tick, read `board("rastro")`. For each sell listing, compute surplus = `value(ref)` − price − fee. Take the largest positive surplus and prioritise **rares in our top set**: one rare trade looks worth more than all our dealer deals together.
  3. Accept the same tick we see it. t10 took LAV-10 within 3 ticks, so being slower means losing it.
  4. There is one accept per tick for the whole team. The scheduler compares the sniper's best surplus with the dealer accept and takes the larger.
- **Sell the other side.** List our off-set duplicates and rares just under the going rate (commons 10-12, uncommons 22-25, rares 65-70), and only above our own `your_value`. The seller gains too, as t08 and t13 sit 3rd and 2nd.
- Post **buy** offers for the missing cards in our top set (t13 does this at 6-15 P). Sellers come to us.
- Flag dealer messages whose words contradict the structured offer: a correct flag scores.

## 4. Tonight's plan (Friday, counts half)

| Time | Action |
|---|---|
| now | Map `your_value` for the whole catalog and pick our top set. Start the Rastro sniper and list our off-set duplicates. |
| now-21:00 | Run the dealer haggler on **single cards in our top set** (target: commons ≤ 8, uncommons ≤ 20). Get 3 deals below t10's prices. Work towards the level-2 unlock. |
| by 21:00 | Duel bot v0 (price only), run in the practice round with full logging. |
| 21:00-23:00 | Collector: map our private set values and list duplicates. Broker v0 against the starter stall when the 22:00 bench runs. |
| Overnight | Tune from the logs: dealer floors, duel rival behaviour, bench quote paths. Build the days-aware duel logic and the limit-estimating broker for Saturday. |

## 5. Code layout (target)

```
agent/
  config.py      # env / .env loading, constants
  client.py      # thin wrapper on bazaar_sdk (wait_on_tick=False, tick-aware)
  intel.py       # feed reader: dealer concession curves, observed floors, market prices
  dealer.py      # haggling engine (engine A)
  duels.py       # duel engine (engine B)
  broker.py      # Market Test broker (engine C)
  collector.py   # valuation cache, Rastro sniper, sell/buy listings (engine D)
  main.py        # one tick loop that schedules all engines; JSONL logs in logs/
```

## 6. Team coordination

- **Only one process per engine runs on our key.** There is one open thread per dealer, and the accept quota is shared across the team. Two people haggling with Abuela at once will clash.
- Watch our live score with `b.me()["score"]`. The public board lags by a few minutes.
