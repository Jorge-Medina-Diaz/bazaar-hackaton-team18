import copy
import json
from pathlib import Path
import tempfile
import unittest

from battle_watch import accumulate, atomic, read_state, seeds, single_writer


class ContinuousBattleTests(unittest.TestCase):
    def test_persistence_and_seed_blocks_survive_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            s = read_state(out)
            s["next_batch"] = 3
            atomic(out / "entrenamiento/status.json", s)
            restored = read_state(out)
            self.assertEqual(restored["next_batch"], 3)
            self.assertGreater(seeds(3, 18), seeds(2, 18) + 150000)

    def test_only_one_coordinator_can_write(self):
        with tempfile.TemporaryDirectory() as temp:
            with single_writer(Path(temp)):
                with self.assertRaises(RuntimeError):
                    with single_writer(Path(temp)):
                        pass

    def test_validation_cannot_select_cumulative_training_leader(self):
        baseline = {"anchor": .6, "acc_late": 3}
        alternative = {"anchor": .75, "acc_late": 3}
        row = {"train_ranking": [
            {"params": baseline, "episodes": 10, "mean_score": 5, "failures": 0},
            {"params": alternative, "episodes": 10, "mean_score": 4, "failures": 0}],
            "selected_params": alternative, "validation_selected": {"episodes": 10, "failures": 0},
            "validation": {"paired_mean_gain": 100}}
        report = {"simulation": {"distinct_scenarios": 40, "executed_episodes": 280, "failures": 0,
                                  "roles": {"buyer": row, "seller": copy.deepcopy(row)}}}
        with tempfile.TemporaryDirectory() as temp:
            s = accumulate(read_state(Path(temp)), report)
            self.assertEqual(s["completed_batches"], 1)
            self.assertEqual(s["scenarios"], 40)
            self.assertEqual(s["roles"]["buyer"]["leader_from_training"], baseline)
            self.assertIsNone(s["roles"]["buyer"]["leader_validation"])
            self.assertEqual(s["roles"]["buyer"]["validation"][json.dumps(alternative, sort_keys=True)]["n"], 10)

    def test_new_policy_version_does_not_mix_training_rankings(self):
        row = {"train_ranking": [{"params": {"anchor": .6}, "episodes": 10, "mean_score": 5, "failures": 0}],
               "selected_params": {"anchor": .6}, "validation_selected": {"episodes": 10, "failures": 0},
               "validation": {"paired_mean_gain": 1}}
        r = {"source": {"hash": "old"}, "simulation": {"distinct_scenarios": 40,
             "executed_episodes": 280, "failures": 0, "roles": {"buyer": row}}}
        with tempfile.TemporaryDirectory() as temp:
            s = accumulate(read_state(Path(temp)), r)
            r["source"]["hash"] = "new"
            s = accumulate(s, r)
            self.assertEqual(s["evaluations"], 560)
            self.assertEqual(s["version_evaluations"], 280)
            self.assertIn("old", s["prior_versions"])
            self.assertEqual(next(iter(s["roles"]["buyer"]["training"].values()))["n"], 10)

    def test_cumulative_leader_rejects_average_gain_with_losing_group(self):
        baseline, alternative = {"anchor": .6}, {"anchor": .75}
        row = {"train_ranking": [
            {"params": baseline, "episodes": 10, "mean_score": 5, "selection_score": 0,
             "failures": 0, "training_group_gains": {"reactive": 0, "patient": 0}},
            {"params": alternative, "episodes": 10, "mean_score": 8, "selection_score": .2,
             "failures": 0, "training_group_gains": {"reactive": .5, "patient": -.1}}],
            "selected_params": baseline, "validation_selected": {"episodes": 10, "failures": 0},
            "validation": {"paired_mean_gain": 0}}
        report = {"simulation": {"distinct_scenarios": 40, "executed_episodes": 280,
                                  "failures": 0, "roles": {"buyer": row}}}
        with tempfile.TemporaryDirectory() as temp:
            state = accumulate(read_state(Path(temp)), report)
            self.assertEqual(state["roles"]["buyer"]["leader_from_training"], baseline)


if __name__ == "__main__":
    unittest.main()
