"""Evidence checks: scored historical fixtures, not mirrored implementation."""
import json
from pathlib import Path
import tempfile
import unittest

from harness.battle_data import load_evidence


class BattleDataTests(unittest.TestCase):
    def test_historical_scores_and_rounds_match(self):
        evidence = load_evidence()
        formula = evidence["formula_verified"]
        self.assertEqual((formula["tested"], formula["passed"], formula["failed"]), (18, 18, 0))
        self.assertEqual((formula["rounds_min_messages_tested"], formula["rounds_min_messages_matches"]), (30, 30))
        self.assertLessEqual(formula["max_abs_error"], 0.05)
        self.assertEqual(evidence["profiles"]["buyer"]["duels"], 15)
        self.assertEqual(evidence["profiles"]["seller"]["duels"], 15)
        self.assertIsNone(evidence["simulation_profile_weights"])
        json.dumps(evidence, allow_nan=False)

    def test_jsonl_deduplicates_and_counts_malformed_without_text(self):
        event = {"id": 42, "tick": 1, "type": "duel.closed",
                 "payload": {"session": 4, "status": "deal", "text": "PRIVATE-MARKER"}}
        with tempfile.TemporaryDirectory() as directory:
            feed = Path(directory) / "feed.jsonl"
            feed.write_text(json.dumps(event) + "\n" + json.dumps(event) + "\nBROKEN\n[]\n", encoding="utf-8")
            evidence = load_evidence(feed)
        self.assertEqual(evidence["counts"]["feed_events"], 1)
        self.assertEqual(evidence["counts"]["public_duel_closed"], 1)
        self.assertEqual(evidence["sources"]["malformed_feed_rows"], 2)
        self.assertEqual(evidence["public_duel_summary"]["by_session"], {"4": {"deal": 1}})
        self.assertNotIn("PRIVATE-MARKER", json.dumps(evidence))

    def test_private_text_prices_and_limits_not_exported(self):
        row = {"duel": 999, "session": 8, "role": "buyer", "status": "deal",
               "issues": ["price"], "your_limit": 187654321, "price": 176543210,
               "rounds": 1, "decay_per_round": 0.1, "result": 9999999.9,
               "messages": [{"from": "you", "tick": 3, "price": 176543210, "text": "PRIVATE-MARKER"},
                            {"from": "Rival", "tick": 4, "price": 176543210, "text": "RIVAL-PRIVATE"}]}
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "duels.json"
            fixture.write_text(json.dumps({"duels": [row]}), encoding="utf-8")
            evidence = load_evidence(duels_path=fixture)
        encoded = json.dumps(evidence)
        for marker in ("PRIVATE-MARKER", "RIVAL-PRIVATE", "187654321", "176543210"):
            self.assertNotIn(marker, encoded)
        self.assertFalse(evidence["sources"]["network_used"])
        self.assertEqual(evidence["formula_verified"]["passed"], 1)


if __name__ == "__main__":
    unittest.main()
