import random
import unittest

from agent import affinity as af


def card(ref, rarity, frm, to):
    return {"id": random.randrange(10**6), "kind": "card", "ref": ref, "set": ref[:3], "rarity": rarity,
            "frm": frm, "to": to}


def settle(eid, tick, items, price, persona=None):
    parties = sorted({items[0]["frm"], items[0]["to"]})
    return {"id": eid, "tick": tick, "type": "settlement",
            "payload": {"kind": "trade", "items": items, "price": price, "persona": persona, "parties": parties}}


def bid(eid, tick, team, ref, rarity, price):
    return {"id": eid, "tick": tick, "type": "offer.listed",
            "payload": {"offer": {"maker": team, "thread": None, "give": {"cash": price, "assets": [], "types": []},
                                  "want": {"cash": 0, "assets": [], "types": [f"card:{ref}"]}}}}


class EvidenceTests(unittest.TestCase):
    def test_bundle_price_split_by_book_and_sides(self):
        ev = [settle(1, 5, [card("LAT-02", "common", "t04", "t15"), card("LAT-09", "rare", "t04", "t15")], 80)]
        rows = af.evidence(ev)
        buys = sorted((r["ref"], round(r["price"], 2)) for r in rows if r["kind"] == "trade_buy")
        self.assertEqual(buys, [("LAT-02", 10.0), ("LAT-09", 70.0)])
        self.assertEqual({r["team"] for r in rows if r["kind"] == "trade_sell"}, {"t04"})

    def test_dealer_trades_are_weaker_kinds_and_dealers_get_nothing(self):
        rows = af.evidence([settle(1, 5, [card("SAL-02", "common", "abuela", "t13")], 9, persona="abuela")])
        self.assertEqual([(r["team"], r["kind"]) for r in rows], [("t13", "dealer_buy")])

    def test_strongest_bid_per_card_only(self):
        rows = af.evidence([bid(1, 5, "t17", "MAL-09", "rare", 50), bid(2, 6, "t17", "MAL-09", "rare", 70)],
                           {"MAL-09": "rare"})
        self.assertEqual([r["price"] for r in rows], [70])

    def test_haggles_with_dealers_are_ignored(self):
        e = bid(1, 5, "t17", "MAL-09", "rare", 5)
        e["payload"]["offer"]["thread"] = 99
        self.assertEqual(af.evidence([e], {"MAL-09": "rare"}), [])


class PosteriorTests(unittest.TestCase):
    def test_uniform_prior(self):
        p = af.estimate([], known={})
        self.assertEqual(p, {})
        post = af.Posterior("t1", [0.0] * len(af.PERMS), {})
        self.assertAlmostEqual(post.marginal("SAL")[1.6], 1 / 6)
        self.assertAlmostEqual(post.entropy_bits(), 9.49, places=2)

    def test_expensive_rare_buy_points_at_high_multiplier_and_couples_sets(self):
        ev = [settle(i, i, [card("MAL-10", "rare", "t14", "t08")], 100) for i in range(3)]
        post = af.estimate(ev)
        self.assertGreater(post["t08"].p_at_least("MAL", 1.3), 0.6)
        self.assertLess(post["t08"].marginal("SAL")[1.6], 1 / 6)  # the 1.6 is probably taken by MAL

    def test_known_team_is_exact(self):
        aff = dict(zip(af.SETS, (0.7, 0.5, 0.9, 1.1, 1.3, 1.6)))
        post = af.estimate([], known={"t18": aff})
        self.assertAlmostEqual(post["t18"].expected("CHA"), 1.6)
        self.assertEqual(post["t18"].credible("CHA", 0.99), [1.6])

    def test_score_jump_sign_is_evidence(self):
        snaps = [{"tick": 10, "round": 2, "teams": {"t01": 5, "t02": 5, "t03": 5, "t04": 5, "t05": 5}},
                 {"tick": 15, "round": 2, "teams": {"t01": 7, "t02": 5, "t03": 5, "t04": 5, "t05": 5}}]
        ev = [settle(1, 12, [card("RET-09", "rare", "t02", "t01")], 80)]
        jumps = af.score_jumps(snaps, ev)
        self.assertEqual([(j["team"], j["sign"]) for j in jumps], [("t01", 1)])  # t02 fell 0: no jump
        with_jump = af.estimate(ev, snaps)["t01"].p_at_least("RET", 1.3)
        without = af.estimate(ev)["t01"].p_at_least("RET", 1.3)
        self.assertGreater(with_jump, without)


class CalibrationTest(unittest.TestCase):
    def test_simulated_market_is_calibrated(self):
        """Rational teams with known multipliers: the truth falls in the 80 % credible set about 80 % of the time."""
        rng = random.Random(7)
        teams = {f"t{i:02d}": dict(zip(af.SETS, rng.sample(af.MULTS, 6))) for i in range(12)}
        ev, eid = [], 0
        for _ in range(400):
            buyer, seller = rng.sample(sorted(teams), 2)
            st = rng.choice(af.SETS[:5])
            rar = rng.choice(["common"] * 5 + ["uncommon"] * 3 + ["rare"] * 2)
            b = af.BOOK[rar]
            v_buy = b * teams[buyer][st] * rng.choice([1, 1, 1.1, 1.5])
            v_sell = b * teams[seller][st] * rng.choice([0.25, 0.25, 0.25, 1])
            if v_buy > v_sell:
                eid += 1
                price = round(rng.uniform(v_sell, v_buy))
                ev.append(settle(eid, eid, [card(f"{st}-01", rar, seller, buyer)], max(price, 1)))
        post = af.estimate(ev)
        hits = total = 0
        for t, aff in teams.items():
            for st in af.SETS[:5]:
                total += 1
                hits += aff[st] in post[t].credible(st, 0.8)
        self.assertGreater(hits / total, 0.7)
        top_right = sum(max(post[t].top_set(), key=post[t].top_set().get) == max(aff, key=aff.get)
                        for t, aff in teams.items())
        self.assertGreater(top_right, 12 / 6)  # better than chance at naming each team's 1.6


if __name__ == "__main__":
    unittest.main()
