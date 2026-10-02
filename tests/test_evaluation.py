import unittest

from evaluacion import repeated_prices, require_passed


class EvaluationGateTests(unittest.TestCase):
    def test_failed_gate_blocks_real_play(self):
        with self.assertRaises(RuntimeError):
            require_passed({"passed": False})
        with self.assertRaises(RuntimeError):
            require_passed({})

    def test_successful_gate_allows_next_stage(self):
        require_passed({"passed": True})

    def test_same_price_in_separate_purchases_is_valid(self):
        events = [{"action": "offer", "price": 7}, {"action": "settled", "price": 7},
                  {"action": "offer", "price": 7}, {"action": "settled", "price": 7}]
        self.assertEqual(repeated_prices(events), 0)

    def test_same_price_inside_one_purchase_is_a_repetition(self):
        events = [{"action": "offer", "price": 7}, {"action": "offer", "price": 7}]
        self.assertEqual(repeated_prices(events), 1)
