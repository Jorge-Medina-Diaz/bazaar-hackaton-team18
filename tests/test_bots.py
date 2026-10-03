"""M6b: every bot follows its profile (docs/knowledge.md D-02..D-10, U-01/U-02; harness-spec §9)."""
from __future__ import annotations

import json
import unittest

from sim.bots import INJECTION, AbuelaBot, ChatoBot, DuelRival, TeamBot
from sim.world import FakeGame

AFF = {"LAV": 0.7, "MAL": 0.5, "LAT": 0.9, "SAL": 1.1, "RET": 1.3, "CHA": 1.6}


def call(g, method, path, body=None):
    s, raw = g.http(method, "http://127.0.0.1" + path, None if body is None else json.dumps(body).encode(),
                    {"X-Team-Key": "tk-test"})
    return s, json.loads(raw) if raw else None


def our_assets(g):
    return sorted(a for a, x in g.assets.items() if x["owner"] == "t18" and x["kind"] == "card")


# =========================================================================== team bots

class TestTeamBots(unittest.TestCase):
    def game(self, kind, seed=0, **kw):
        g = FakeGame(seed=seed)
        bot = g.add_bot(TeamBot(kind, seed, **kw))
        return g, bot

    def test_honest_lists_bids_and_buys_cheap(self):
        g, bot = self.game("honest")
        aid = our_assets(g)[0]
        _, o = call(g, "POST", "/api/offers", {"give": {"assets": [aid]}, "want": {"cash": 1}})
        g.advance()
        kinds = {("sell" if g.offers[i]["give"]["assets"] else "bid") for i in bot.posted}
        self.assertEqual(kinds, {"sell", "bid"})
        self.assertIn(o["id"], bot.accepted)                      # 1 + fee 2 <= its value of a common
        g.advance()
        self.assertEqual(g.assets[aid]["owner"], bot.team)

    def test_overpriced_lists_at_three_times_book(self):
        g, bot = self.game("overpriced")
        g.advance()
        self.assertTrue(bot.posted)
        for oid in bot.posted:
            o = g.offers[oid]
            ref = g.assets[o["give"]["assets"][0]]["ref"]
            self.assertEqual(o["want"]["cash"], 3 * g.model.cards[ref]["book"])

    def test_phantom_offer_fails_when_accepted(self):
        g, bot = self.game("phantom")
        g.advance()
        oid = bot.posted[0]
        self.assertEqual(call(g, "POST", f"/api/offers/{oid}/accept", {})[0], 200)
        g.advance()
        self.assertEqual(g.offers[oid]["status"], "failed")
        self.assertEqual(g.failures[-1]["code"], "missing_assets")

    def test_opener_accepts_our_cheapest_sell_on_its_first_tick(self):
        g = FakeGame(seed=1)
        a, b = our_assets(g)[:2]
        _, o1 = call(g, "POST", "/api/offers", {"give": {"assets": [a]}, "want": {"cash": 30}})
        _, o2 = call(g, "POST", "/api/offers", {"give": {"assets": [b]}, "want": {"cash": 12}})
        bot = g.add_bot(TeamBot("opener", 1))
        g.advance()
        self.assertEqual(bot.accepted, [o2["id"]])
        _, o3 = call(g, "POST", "/api/offers", {"give": {"assets": [a]}, "want": {"cash": 2}})
        g.advance(2)
        self.assertEqual(bot.accepted, [o2["id"]])                 # only on tick 0

    def test_closer_bidder_outbids_our_bid(self):
        g, bot = self.game("closer_bidder", step=3, cap=70)
        call(g, "POST", "/api/offers", {"give": {"cash": 49}, "want": {"cards": ["LAT-09"]}})
        g.advance()
        bids = [g.offers[i] for i in bot.posted if g.offers[i]["status"] == "open"]
        self.assertEqual([(b["give"]["cash"], b["want"]["types"]) for b in bids], [(52, ["card:LAT-09"])])
        call(g, "POST", "/api/offers", {"give": {"cash": 69}, "want": {"cards": ["LAT-09"]}})
        g.advance()
        open_bids = [g.offers[i]["give"]["cash"] for i in bot.posted if g.offers[i]["status"] == "open"]
        self.assertEqual(open_bids, [70])                          # capped, its older bid cancelled

    def test_swapper_posts_and_takes_swaps(self):
        g = FakeGame(seed=2, starting_cards=None)
        g.add_team("t18", cash=100, keys=("tk-test",), affinity=AFF, cards=["LAV-01", "LAV-01", "MAL-02"])
        bot = g.add_bot(TeamBot("swapper", 2, cards=["LAT-03", "MAL-02"]))
        g.advance()
        swap = g.offers[bot.posted[0]]
        self.assertEqual((swap["give"]["cash"], swap["want"]["cash"], swap["want"]["types"]), (0, 0, ["card:LAV-01"]))
        mal = [a for a in our_assets(g) if g.assets[a]["ref"] == "LAV-01"][0]
        _, o = call(g, "POST", "/api/offers", {"give": {"assets": [mal]}, "want": {"cards": ["MAL-02"]}})
        g.advance()
        self.assertIn(o["id"], bot.accepted)

    def test_twisted_posts_non_canonical_shapes(self):
        g, bot = self.game("twisted")
        g.advance()
        self.assertGreaterEqual(len(bot.posted), 3)
        odd = 0
        for oid in bot.posted:
            o = g.offers[oid]
            n_give = len(o["give"]["assets"]) + (1 if o["give"]["cash"] else 0)
            n_want = len(o["want"]["types"]) + (1 if o["want"]["cash"] else 0)
            odd += n_give > 1 or n_want > 1 or o["to"] == "t18"
        self.assertEqual(odd, len(bot.posted))

    def test_injector_text_reaches_us_only_as_thread_text(self):
        g, bot = self.game("injector")
        g.advance(2)
        _, th = call(g, "GET", "/api/me/threads")
        texts = [m["text"] for t in th["threads"] for m in t["messages"]]
        self.assertIn(INJECTION, texts)
        _, mine = call(g, "GET", "/api/me/offers")
        self.assertTrue(any(o["to"] == "t18" for o in mine["offers"]))


# =========================================================================== dealers

def talk(g, tid, price, text=None):
    s, r = call(g, "POST", f"/api/threads/{tid}/messages", {"text": text or f"p{price}", "price": price})
    assert s == 200, r
    th = r["thread"]
    dealer = [m for m in th["messages"] if m["sender"] != "t18"]
    return th, dealer[-1] if dealer else None


class TestAbuela(unittest.TestCase):
    def open(self, seed=0, topic=None, welcome=False):
        g = FakeGame(seed=seed)
        g.add_bot(AbuelaBot(welcome=welcome, seed=seed))
        s, t = call(g, "POST", "/api/threads", {"with": "abuela", "topic": topic or {"buy": {"pack": "sobre_barrio"}}})
        self.assertEqual(s, 200, t)
        return g, t

    def test_opening_and_no_concession_without_raise(self):
        g, t = self.open()
        self.assertEqual(t["standing_offers"][0]["give"]["assets"][0]["ref"], "sobre_barrio")
        self.assertEqual(t["messages"][0]["offer"]["want"]["cash"], 30)              # D-01
        th, m = talk(g, t["id"], 10)
        first_cut = 30 - m["offer"]["want"]["cash"]
        self.assertIn(first_cut, (3, 4))                                            # D-04
        g.advance()
        th, m2 = talk(g, t["id"], 9)                                                # lower: no concession (D-03)
        self.assertEqual(m2["offer"]["want"]["cash"], m["offer"]["want"]["cash"])

    def test_final_in_5th_to_7th_offer_within_19_24_and_walk_below_final(self):
        for seed in range(12):
            g, t = self.open(seed=seed)
            price, asks, final = 10, [30], None
            for _ in range(10):
                g.advance()
                th, m = talk(g, t["id"], price)
                if th["status"] != "open":
                    break
                asks.append(m["offer"]["want"]["cash"])
                if m["offer"]["final"]:
                    final = asks[-1]
                    break
                price += 1
            self.assertIsNotNone(final, seed)
            self.assertTrue(19 <= final <= 26, (seed, asks))
            self.assertIn(len(asks), (5, 6, 7), (seed, asks))                       # D-05
            self.assertTrue(all(a >= b for a, b in zip(asks, asks[1:])))
            g.advance()
            th, _ = talk(g, t["id"], final - 3)                                     # below her final: she walks
            self.assertEqual(th["status"], "walked")

    def test_accepts_at_her_price_and_deal_counts_zero_or_less(self):
        g, t = self.open(seed=3)
        th, _ = talk(g, t["id"], 30)
        self.assertEqual(th["status"], "deal")
        g.advance()
        self.assertLessEqual(g.oracle()["rows"][-1]["delta"], 0.0)                   # P-04

    def test_repeat_price_walks(self):
        g, t = self.open(seed=4)
        talk(g, t["id"], 15)
        g.advance()
        th, m = talk(g, t["id"], 15, text="other words")
        self.assertEqual(th["status"], "walked")
        self.assertEqual(m["text"], "with those manners")

    def test_welcome_fixed_price(self):
        g, t = self.open(seed=5, welcome=True)
        self.assertEqual(t["messages"][0]["offer"]["want"]["cash"], 17)              # D-02
        th, m = talk(g, t["id"], 12)
        self.assertEqual(m["offer"]["want"]["cash"], 17)
        g.advance()
        th, _ = talk(g, t["id"], 17)
        self.assertEqual(th["status"], "deal")

    def test_buys_uncommon_from_us_between_12_and_16(self):
        g = FakeGame(seed=6, starting_cards=None)
        g.add_team("t18", cash=100, keys=("tk-test",), affinity=AFF, cards=["LAV-07"])
        g.add_bot(AbuelaBot(seed=6))
        aid = our_assets(g)[0]
        _, t = call(g, "POST", "/api/threads", {"with": "abuela", "topic": {"sell": {"assets": [aid]}}})
        self.assertEqual(t["messages"][0]["offer"]["give"]["cash"], 12)              # D-01
        price, bids = 30, []
        for _ in range(8):
            g.advance()
            th, m = talk(g, t["id"], price)
            if th["status"] != "open":
                break
            bids.append(m["offer"]["give"]["cash"])
            if m["offer"]["final"]:
                break
            price -= 1
        self.assertTrue(all(12 <= b <= 16 for b in bids), bids)
        self.assertTrue(all(a <= b for a, b in zip(bids, bids[1:])), bids)

    def test_conditional_buy_profile(self):
        """Accepts if her final <= our limit; otherwise we close without a deal."""
        for seed in range(8):
            g, t = self.open(seed=seed)
            limit, price, status = 22, 12, None
            for _ in range(12):
                g.advance()
                th, m = talk(g, t["id"], min(price, limit))
                status = th["status"]
                if status != "open":
                    break
                ask = m["offer"]["want"]["cash"]
                if ask <= limit:
                    g.advance()
                    th, _ = talk(g, t["id"], ask)
                    status = th["status"]
                    break
                if m["offer"]["final"]:
                    call(g, "POST", f"/api/threads/{t['id']}/close")
                    status = "closed"
                    break
                price += 1
            self.assertIn(status, ("deal", "closed", "walked"), seed)
            if status == "deal":
                g.advance()
                paid = -g.oracle()["rows"][-1]["cash"]
                self.assertLessEqual(paid, limit)


class TestChato(unittest.TestCase):
    def test_rare_never_concedes_more_than_our_step_and_final_90_93(self):
        for seed in range(10):
            g = FakeGame(seed=seed)
            g.add_bot(ChatoBot(seed=seed))
            _, t = call(g, "POST", "/api/threads", {"with": "chato", "topic": {"buy": {"card": "LAT-10"}}})
            self.assertEqual(t["messages"][0]["offer"]["want"]["cash"], 97)          # D-01
            ours, asks, final = [60], [97], None
            talk(g, t["id"], 60)
            for _ in range(10):
                g.advance()
                p = ours[-1] + 3
                th, m = talk(g, t["id"], p)
                if th["status"] != "open":
                    break
                ours.append(p)
                asks.append(m["offer"]["want"]["cash"])
                self.assertLessEqual(asks[-2] - asks[-1], ours[-1] - ours[-2])        # D-09
                if m["offer"]["final"]:
                    final = asks[-1]
                    break
            self.assertIsNotNone(final, (seed, asks))
            self.assertTrue(90 <= final <= 97, (seed, asks))

    def test_buys_uncommon_at_13_final_15(self):
        g = FakeGame(seed=1, starting_cards=None)
        g.add_team("t18", cash=100, keys=("tk-test",), affinity=AFF, cards=["LAV-07"], unlocked=["abuela", "chato"])
        g.add_bot(ChatoBot(seed=1))
        aid = our_assets(g)[0]
        _, t = call(g, "POST", "/api/threads", {"with": "chato", "topic": {"sell": {"assets": [aid]}}})
        bids, price = [t["messages"][0]["offer"]["give"]["cash"]], 25
        for _ in range(8):
            g.advance()
            th, m = talk(g, t["id"], price)
            if th["status"] != "open":
                break
            bids.append(m["offer"]["give"]["cash"])
            if m["offer"]["final"]:
                break
            price -= 1
        self.assertEqual(bids[0], 13)
        self.assertEqual(bids[-1], 15)
        self.assertEqual(set(bids[:-1]), {13})


# =========================================================================== duel rivals

class TestDuelRivals(unittest.TestCase):
    def duel(self, kind, *, role="buyer", limit=100, rival_limit=80, issues=("price",), ticks=10, seed=0):
        g = FakeGame(seed=seed)
        bot = DuelRival(kind, seed)
        did = g.create_duel(role=role, limit=limit, rival_limit=rival_limit, deadline_ticks=ticks, decay=0.1,
                            issues=issues, rival=bot)
        return g, did

    def say(self, g, did, price, days=None):
        body = {"text": "", "price": price}
        if days is not None:
            body["days"] = days
        s, r = call(g, "POST", f"/api/duels/{did}/messages", body)
        assert s == 200, r
        return r["duel"]

    def test_mute(self):
        g, did = self.duel("mute")
        self.say(g, did, 90)
        g.advance(12)
        d = g.duels[did]
        self.assertEqual((d["status"], d["rival_msgs"]), ("no_deal", 0))

    def test_accept_only(self):
        g, did = self.duel("accept_only")
        self.say(g, did, 70)
        self.assertEqual(g.duels[did]["status"], "live")
        g.advance()
        self.say(g, did, 85)
        g.advance()
        d = g.duels[did]
        self.assertEqual((d["status"], d["price"], d["rival_msgs"]), ("deal", 85, 0))
        self.assertEqual(d["result"], 15.0)                              # 0 rounds: no decay

    def test_one_and_accept(self):
        g, did = self.duel("one_and_accept")
        g.advance()
        self.assertEqual(g.duels[did]["rival_offer"]["price"], 112)       # 80 * 1.4
        g.advance()
        self.assertEqual(g.duels[did]["rival_msgs"], 1)
        self.say(g, did, 81)
        g.advance()
        self.assertEqual(g.duels[did]["price"], 81)

    def test_reactive_answers_only_after_us_and_converges(self):
        g, did = self.duel("reactive", ticks=30)
        g.advance(3)
        self.assertEqual(g.duels[did]["rival_msgs"], 0)
        price, offers = 60, []
        for _ in range(10):
            d = self.say(g, did, price)
            if g.duels[did]["status"] != "live":
                break
            offers.append(d["rival_offer"]["price"])
            g.advance()
            price += 3
        self.assertTrue(all(a >= b for a, b in zip(offers, offers[1:])), offers)
        self.assertTrue(all(o >= 80 for o in offers))                    # never past its limit
        g.advance()
        self.assertEqual(g.duels[did]["status"], "deal")
        self.assertGreaterEqual(g.duels[did]["price"], 80)

    def test_time_driven_concedes_every_tick(self):
        g, did = self.duel("time_driven")
        g.advance(5)
        prices = [m["price"] for m in g.duels[did]["messages"]]
        self.assertEqual(len(prices), 5)
        self.assertTrue(all(a > b for a, b in zip(prices, prices[1:])), prices)

    def test_firm_never_moves(self):
        g, did = self.duel("firm")
        for p in (60, 70, 80, 90):
            self.say(g, did, p)
            g.advance()
        prices = {m["price"] for m in g.duels[did]["messages"] if m["from"] != "you"}
        self.assertEqual(prices, {112})
        self.say(g, did, 112)
        g.advance()
        self.assertEqual(g.duels[did]["price"], 112)
        self.assertLess(g.duels[did]["result"], 0)                        # outside OUR limit: the oracle shows it

    def test_worsening_speaks_every_tick_and_never_accepts(self):
        g, did = self.duel("worsening")
        g.advance(4)
        prices = [m["price"] for m in g.duels[did]["messages"]]
        self.assertTrue(all(b > a for a, b in zip(prices, prices[1:])), prices)
        self.say(g, did, 99)
        g.advance()
        self.assertEqual(g.duels[did]["status"], "live")

    def test_injector_text_and_days(self):
        g, did = self.duel("injector", issues=("price", "days"))
        d = self.say(g, did, 60, days=2)
        self.assertEqual(d["messages"][-1]["text"], INJECTION)
        self.assertEqual(d["rival_offer"]["days"], 5)

    def test_seller_role_mirrors(self):
        g, did = self.duel("reactive", role="seller", limit=50, rival_limit=90, ticks=30)
        d = self.say(g, did, 120)
        self.assertEqual(d["rival_offer"]["price"], 54)                   # 90 * 0.6
        offers, price = [54], 120
        for _ in range(12):
            g.advance()
            price -= 5
            d = self.say(g, did, price)
            if g.duels[did]["status"] != "live":
                break
            offers.append(d["rival_offer"]["price"])
        self.assertTrue(all(a <= b for a, b in zip(offers, offers[1:])), offers)   # it climbs toward its limit
        self.assertTrue(all(o <= 90 for o in offers), offers)                     # never past its limit
        g.advance()
        self.assertEqual(g.duels[did]["status"], "deal")
        self.assertLessEqual(g.duels[did]["price"], 90)
        self.assertEqual(g.duels[did]["price"], price)                   # it took our crossing price


if __name__ == "__main__":
    unittest.main()
