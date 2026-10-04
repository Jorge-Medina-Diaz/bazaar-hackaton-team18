"""Scoring, safe action and held-out selection checks for offline battle practice."""
import unittest

from harness.mini_battle import signed_score, make_scenarios, simulate_episode, run_experiment
from mini_campo_batalla import pipeline_probe


class MiniBattleTests(unittest.TestCase):
    def test_losses_are_not_rewarded_for_either_role(self):
        self.assertLess(signed_score("buyer", 100, 120, .1, 2, 3), 0)
        self.assertLess(signed_score("seller", 100, 80, .1, 2, 3), 0)
        self.assertEqual(signed_score("buyer", 100, None, .1, 2, 3), 0)

    def test_only_matched_messages_decay_and_days_are_separate_assumption(self):
        self.assertAlmostEqual(signed_score("buyer", 100, 70, .1, 10, 2), 24.3)
        self.assertAlmostEqual(signed_score("seller", 100, 130, .1, 2, 10), 24.3)
        self.assertEqual(signed_score("buyer", 100, 70, .1, 10, 0), 30)
        self.assertAlmostEqual(signed_score("buyer", 100, 70, .1, 10, 2, days_loss=10), 16.2)

    def test_determinism_and_no_trade_with_truly_silent_rival(self):
        a = make_scenarios(24, 18)
        self.assertEqual(a, make_scenarios(24, 18))
        self.assertNotEqual(a, make_scenarios(24, 19))
        silent = next(s for s in a if s["profile"] == "silent")
        for role in ("buyer", "seller"):
            result = simulate_episode(role, silent, trace=True)
            self.assertFalse(result["deal"])
            self.assertEqual(result["score"], 0)
            self.assertEqual(result["rival_messages"], 0)

    def test_stress_checks_both_roles_and_unknown_delivery_preferences(self):
        scenarios = make_scenarios(96, 71)
        self.assertEqual({s["day_case"] for s in scenarios}, {"price_only", "same", "opposite", "unknown"})
        for role in ("buyer", "seller"):
            for scenario in scenarios:
                r = simulate_episode(role, scenario, {"anchor": .75, "acc_late": 5})
                self.assertEqual(r["failures"], [], (role, scenario, r))
                self.assertGreaterEqual(r["score"], 0)

    def test_parallel_experiment_has_separate_train_and_validation(self):
        r = run_experiment(practices_per_role=12, seed=7)
        self.assertEqual(set(r["roles"]), {"buyer", "seller"})
        self.assertEqual(r["distinct_scenarios"], 60)
        self.assertEqual(r["executed_episodes"], 588)
        self.assertEqual(r["failures"], 0)
        for role in r["roles"].values():
            self.assertNotEqual(role["train_seed"], role["test_seed"])
            self.assertEqual(role["validation_baseline"]["episodes"], 12)
            self.assertEqual(role["validation_selected"]["episodes"], 12)
            self.assertEqual(role["selected_params"], role["train_ranking"][0]["params"])
            self.assertEqual(role["train_ranking"][0]["robust_rejections"], 0)
            self.assertEqual(set(role["additional_training_profiles"]), {"splitter", "ackerman", "patient"})

    def test_pipeline_probe_explicitly_does_not_claim_runtime_access(self):
        result = pipeline_probe()
        self.assertTrue(result["synthetic_probe"])
        self.assertFalse(result["runtime_of_operator_verified"])
        self.assertEqual(result["direct_policy"], "say")

    def test_experiment_preserves_actual_policy_flags_and_baseline(self):
        params = {"anchor": .65, "acc_late": 5, "precise": True,
                  "punch": True, "punch_mode": "wait"}
        r = run_experiment(practices_per_role=12, seed=17, base_params=params)
        self.assertEqual(r["failures"], 0)
        for role in r["roles"].values():
            self.assertEqual(role["baseline_params"]["anchor"], .65)
            self.assertEqual(role["baseline_params"]["acc_late"], 5)
            for candidate in role["train_ranking"]:
                for key in ("precise", "punch", "punch_mode"):
                    self.assertEqual(candidate["params"][key], params[key])
        self.assertEqual(params["anchor"], .65)


if __name__ == "__main__":
    unittest.main()
