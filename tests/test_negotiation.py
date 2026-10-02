import unittest
from dataclasses import replace

from laboratorio import SCENARIOS, Simulation
from negotiation_policy import decide_purchase


class PurchasePolicyTests(unittest.TestCase):
    def test_budget_boundary_closes_without_repeating_price(self):
        decision = decide_purchase(28, 26, last_sent=26)
        self.assertEqual(decision.action, "close")
        self.assertIsNone(decision.price)

    def test_new_offer_increases_and_stays_within_limit(self):
        decision = decide_purchase(30, 26, last_sent=25)
        self.assertEqual((decision.action, decision.price), ("offer", 26))

    def test_final_offer_within_limit_is_accepted(self):
        self.assertEqual(decide_purchase(26, 26, final=True).action, "accept")

    def test_final_offer_outside_limit_is_closed(self):
        self.assertEqual(decide_purchase(27, 26, final=True).action, "close")

    def test_pending_or_paused_never_creates_another_offer(self):
        for flags in ({"pending": True}, {"paused": True}):
            self.assertEqual(decide_purchase(10, 26, **flags).action, "wait")

    def test_settled_conversation_finishes_even_if_marked_pending(self):
        self.assertEqual(decide_purchase(10, 26, status="deal", pending=True).action, "done")

    def test_no_cash_means_no_zero_price_offer(self):
        self.assertEqual(decide_purchase(10, 0).action, "close")
        self.assertEqual(decide_purchase(10, 1).price, 1)

    def test_malformed_prices_are_rejected(self):
        for ask in (0, -1, True, 1.5, 10_000_001):
            with self.subTest(ask=ask), self.assertRaises(ValueError):
                decide_purchase(ask, 26)


class SimulationTests(unittest.TestCase):
    def test_card_and_cash_change_only_at_next_tick(self):
        simulation = Simulation(SCENARIOS["final"])
        steps = simulation.steps()
        acceptance = next(steps)
        self.assertEqual(acceptance["action"], "accept")
        self.assertEqual(simulation.cash, 40)
        self.assertEqual(simulation.assets, [])
        self.assertIsNotNone(simulation.pending)
        settlement = next(steps)
        self.assertEqual(settlement["tick"], acceptance["tick"] + 1)
        self.assertEqual((simulation.cash, len(simulation.assets)), (29, 1))
        self.assertIsNone(simulation.pending)
        with self.assertRaises(StopIteration):
            next(steps)
        self.assertEqual(len(simulation.assets), 1)

    def test_multiple_cards_and_duplicates_have_distinct_assets(self):
        simulation = Simulation(SCENARIOS["varias"])
        list(simulation.steps())
        self.assertEqual(simulation.summary()["copies"], {"LAV-03": 2, "MAL-01": 1})
        self.assertEqual(len({a["id"] for a in simulation.assets}), 3)
        self.assertEqual(simulation.assets[-1]["value"], 5)
        self.assertEqual(simulation.cash, 23)

    def test_insufficient_cash_prevents_later_purchases(self):
        simulation = Simulation(replace(SCENARIOS["varias"], cash=3))
        list(simulation.steps())
        self.assertEqual((simulation.cash, len(simulation.assets)), (0, 1))

    def test_improved_policy_avoids_baseline_repetition(self):
        base, improved = (Simulation(SCENARIOS["limite"], name) for name in ("base", "mejorada"))
        list(base.steps())
        list(improved.steps())
        base_prices = [e["price"] for e in base.events if e["action"] == "offer"]
        improved_prices = [e["price"] for e in improved.events if e["action"] == "offer"]
        self.assertGreater(len(base_prices), len(set(base_prices)))
        self.assertEqual(len(improved_prices), len(set(improved_prices)))
        self.assertLess(improved.summary()["decisions"], base.summary()["decisions"])
        self.assertEqual((base.cash, improved.cash), (40, 40))

    def test_all_scenarios_preserve_economic_bounds(self):
        for name, scenario in SCENARIOS.items():
            with self.subTest(scenario=name):
                simulation = Simulation(scenario)
                list(simulation.steps())
                self.assertGreaterEqual(simulation.cash, 0)
                for asset in simulation.assets:
                    self.assertLessEqual(asset["paid"], min(scenario.maximum, asset["value"]))


if __name__ == "__main__":
    unittest.main()
