import unittest
from copy import deepcopy

from harness.battle_reference import crosscheck, robustness


class ReferenceTests(unittest.TestCase):
    def simulation(self):
        row = {"baseline_params": {"precise": True, "punch": True, "punch_mode": "wait"},
               "selected_params": {"precise": True, "punch": True, "punch_mode": "wait"},
               "validation": {"paired_mean_gain": 0}}
        return {"ticks": 12, "decay": .1, "roles": {"buyer": deepcopy(row), "seller": deepcopy(row)}}

    def test_paired_controls_do_not_select_or_mutate_and_counts_are_separate(self):
        sim = self.simulation()
        before = deepcopy(sim)
        r = crosscheck(sim, 18, per_kind_role=8)
        self.assertEqual(sim, before)
        self.assertEqual(r["distinct_scenarios"], 48)
        self.assertEqual(r["evaluations"], 96)
        self.assertEqual(r["failures"], 0)
        self.assertFalse(r["selection_changed"])
        for role in r["roles"].values():
            self.assertEqual(role["paired_gain"], 0)
            self.assertEqual(set(role["per_opponent"]), {"splitter", "ackerman", "patient"})
            self.assertFalse(role["conflicts_with_main_validation"])
            self.assertEqual(role["recommendation"], "retain_baseline")

    def test_reference_is_deterministic_and_validates_sample_size(self):
        self.assertEqual(crosscheck(self.simulation(), 77, 3), crosscheck(self.simulation(), 77, 3))
        with self.assertRaises(ValueError):
            crosscheck(self.simulation(), 18, 0)

    def test_high_average_does_not_hide_losses_against_a_rival(self):
        result = robustness({"reactive": .4, "patient": -.01, "silent": 0})
        self.assertGreater(result["selection_score"], 0)
        self.assertEqual(result["robust_rejections"], 1)
        self.assertEqual(robustness({"reactive": 0, "patient": 0})["robust_rejections"], 0)
