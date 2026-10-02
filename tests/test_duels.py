import contextlib
import io
import random
import unittest

from agent import duels
from agent.duels import arm, mirror, plan, say_text

duels.log = lambda *a, **k: None  # keep tests out of logs/


def step(*a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        duels.step(*a, **k)


class FakeBazaar:
    def __init__(self):
        self.sent, self.accepted = [], []

    def duel_say(self, did, text="", price=None, days=None):
        self.sent.append((did, text, price, days))

    def duel_accept(self, did):
        self.accepted.append(did)


def duel(did, role, limit, item="Plaza de Olavide", rival=None, deadline=136, session=1):
    return {"duel": did, "session": session, "status": "live", "role": role, "item": item, "issues": ["price"],
            "your_limit": limit, "deadline_tick": deadline, "decay_per_round": 0.06,
            "rival_offer": {"price": rival} if rival is not None else None}


class MirrorTests(unittest.TestCase):
    def test_practice_pairs(self):  # shapes and numbers from the practice session (tick 120)
        ds = [duel(11, "buyer", 113), duel(12, "seller", 67), duel(21, "buyer", 204, "Mercado"),
              duel(22, "seller", 125, "Mercado"), duel(95, "buyer", 164, "Mercado"), duel(155, "buyer", 115, "Taxi")]
        self.assertEqual(mirror(ds), {11: 67, 12: 113, 21: 125, 22: 204})

    def test_no_pair_across_items_sessions_or_same_role(self):
        ds = [duel(11, "buyer", 113), duel(12, "seller", 67, "Other"), duel(13, "buyer", 1), duel(14, "buyer", 2),
              duel(15, "buyer", 1), duel(16, "seller", 2, session=2)]
        self.assertEqual(mirror(ds), {})

    def test_pairs_share_an_arm(self):
        for k in range(1, 50, 2):
            self.assertEqual(arm(k), arm(k + 1))
        self.assertEqual({arm(k) for k in range(1, 7)}, set(duels.ARMS))


class PlanTests(unittest.TestCase):
    def test_plan_sits_inside_the_pie(self):
        self.assertEqual(plan("buyer", 113, 67, 0, 16), (113 - 42, 113 - 14))
        self.assertEqual(plan("seller", 67, 113, 0, 16), (67 + 42, 67 + 14))

    def test_no_pie_falls_back_to_default(self):
        self.assertEqual(plan("buyer", 50, 102, 0, 16), (30, 50))
        self.assertEqual(plan("seller", 100, None, 0, 16), (167, 100))


class StepTests(unittest.TestCase):
    def test_never_crosses_limit_and_is_monotonic(self):
        rng = random.Random(7)
        for _ in range(400):
            role = rng.choice(["buyer", "seller"])
            limit = rng.randint(20, 300)
            rl = rng.choice([None, rng.randint(10, 400)])
            b, state, did = FakeBazaar(), {}, rng.randint(1, 300)
            for now in range(120, 136):
                rival = rng.choice([None, rng.randint(1, 450)])
                step(b, duel(did, role, limit, rival=rival), state, rival_limit=rl, now=now, arms=("plain",))
                if b.accepted:
                    self.assertTrue(rival <= limit if role == "buyer" else rival >= limit)
                    break
            prices = [p for _, _, p, _ in b.sent]
            for p in prices:
                self.assertTrue(p <= limit if role == "buyer" else p >= limit)
            self.assertEqual(prices, sorted(prices, reverse=role == "seller"))
            self.assertEqual(len(prices), len(set(prices)))

    def test_accepts_a_rival_that_crosses_its_own_limit(self):  # duel 244: rival bid 145 over our cost 140
        b = FakeBazaar()
        step(b, duel(244, "seller", 140, rival=145), {}, rival_limit=87, now=125)
        self.assertEqual(b.accepted, [244])

    def test_text_never_leaks_limit(self):
        for name in duels.ARMS:
            for role in ("buyer", "seller"):
                self.assertNotIn("113", say_text(name, role, 90, 67, 113))
        self.assertEqual(say_text("info", "buyer", 90, None, 113), duels.TEXTS["plain"])
        self.assertTrue(all(len(say_text(n, "buyer", 90, 67, 113)) <= 1200 for n in duels.ARMS))


if __name__ == "__main__":
    unittest.main()
