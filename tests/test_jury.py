"""Evidence boundaries: no fabricated settlements, no secret export, safe HTML."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jury import report


def wal(rows):
    prev, lines = "0" * 64, []
    for seq, row in enumerate(rows, 1):
        line = json.dumps({**row, "seq": seq, "prev": prev}).encode()
        lines.append(line)
        prev = hashlib.sha256(line).hexdigest()
    return b"\n".join(lines) + b"\n"


def snapshot():
    return {"leaderboard": {"snapshot_tick": 10, "round": 2, "teams": [
        {"team": "t18", "rank": 2, "score": 20, "secret": "do-not-export"}]},
        "clock": {"tick": 11, "paused": False, "doors": "open", "secret": "do-not-export"},
        "feed": {"events": []}, "catalog": {"sets": []}}


class JuryEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "journal.jsonl"

    def test_missing_does_not_claim_live_results(self):
        result = report.make_report(**snapshot())
        self.assertEqual(result["journal"]["status"], "missing")
        self.assertEqual(result["journal"]["live_measurements"], 0)
        self.assertNotIn("do-not-export", json.dumps(result))

    def test_http_ok_and_dry_pass_are_not_live_measurements(self):
        self.path.write_bytes(wal([{"mode": "live", "kind": "result", "status": "ok"},
                                   {"mode": "dry", "kind": "measure", "verdict": "pass"}]))
        result = report.journal_summary(self.path)
        self.assertEqual(result["status"], "verified_chain")
        self.assertEqual(result["live_measurements"], 0)

    def test_live_windows_count_without_exporting_private_fields(self):
        data = wal([{"mode": "live", "kind": "measure", "verdict": "pass", "ambiguous": True,
                     "args": {"ref": "RET-01", "key": "private-value"}, "pred": {"cash": 91}},
                    {"mode": "live", "kind": "measure", "verdict": "surprise_up"}])
        self.path.write_bytes(data)
        result = report.journal_summary(self.path)
        self.assertEqual(result["verdicts"], {"pass": 1, "surprise_up": 1})
        self.assertEqual(result["live_measurements"], 2)
        self.assertNotIn("private-value", json.dumps(result))
        self.assertNotIn("RET-01", json.dumps(result))
        self.assertEqual(self.path.read_bytes(), data)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_tampered_chain_rejects_all_measurements(self):
        data = wal([{"mode": "live", "kind": "measure", "verdict": "pass"},
                    {"mode": "live", "kind": "measure", "verdict": "pass"}])
        self.path.write_bytes(data.replace(b'"verdict": "pass"', b'"verdict": "info"', 1))
        result = report.journal_summary(self.path)
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["live_measurements"], 0)

    def test_torn_tail_rejects_even_valid_prefix(self):
        self.path.write_bytes(wal([{"mode": "live", "kind": "measure", "verdict": "pass"}]) + b'{"kind":')
        result = report.journal_summary(self.path)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["live_measurements"], 0)

    def test_unknown_mode_or_verdict_rejected(self):
        for row in ({"mode": "maybe", "kind": "result"},
                    {"mode": "live", "kind": "measure", "verdict": "excellent"}):
            self.path.write_bytes(wal([row]))
            self.assertEqual(report.journal_summary(self.path)["status"], "invalid")

    def test_unsupported_offer_id_skipped_not_invented(self):
        data = snapshot()
        data["feed"]["events"] = [{"id": 1, "tick": 10, "type": "offer.listed", "payload": {"offer": 44}}]
        result = report.make_report(**data)
        self.assertEqual(result["affinity"]["skipped_events"], 1)
        self.assertEqual(result["affinity"]["teams"], [])

    def test_public_trade_is_inference_not_exact_profit(self):
        data = snapshot()
        data["feed"]["events"] = [{"id": 1, "tick": 10, "type": "settlement", "payload": {
            "kind": "trade", "price": 14, "items": [{"kind": "card", "rarity": "common", "set": "RET",
            "ref": "RET-01", "frm": "t02", "to": "t03"}]}}]
        result = report.make_report(**data)
        self.assertEqual(result["affinity"]["classification"], "inferred")
        self.assertIsNone(result["affinity"]["exact_rival_profit"])
        self.assertEqual(len(result["affinity"]["teams"]), 2)
        self.assertEqual(result["journal"]["live_measurements"], 0)

    def test_script_closing_string_cannot_escape_json_block(self):
        result = report.make_report(**snapshot(), fetched_at='</script><script>alert(1)</script>')
        html = report.render(result)
        self.assertNotIn('</script><script>alert(1)', html)
        self.assertIn('\\u003c/script>', html)

    def test_refresh_only_public_fixed_endpoints(self):
        data = snapshot()
        with patch.object(report, "public_get", side_effect=[data[k] for k in
                         ("leaderboard", "clock", "feed", "catalog")]) as get:
            report.main(["--refresh", "--output", self.tmp.name])
        self.assertEqual([c.args[1] for c in get.call_args_list],
                         ['/api/leaderboard', '/api/clock', '/api/feed', '/api/catalog'])
        self.assertTrue(all(c.args[0] == report.PROD_URL for c in get.call_args_list))
        self.assertEqual(json.loads((Path(self.tmp.name)/"evidence.json").read_text())["source"], "public_api")

    def test_offline_input_is_explicit_and_never_calls_network(self):
        fixture = Path(self.tmp.name) / "input.json"
        fixture.write_text(json.dumps(snapshot()))
        with patch.object(report, "public_get", side_effect=AssertionError("network")):
            report.main(["--offline", str(fixture), "--output", self.tmp.name])
        result = json.loads((Path(self.tmp.name)/"evidence.json").read_text())
        self.assertEqual(result["source"], "offline_input")

    def test_analyst_export_uses_capture_date_without_network_or_false_settlements(self):
        fixture = Path(self.tmp.name) / "analyst.json"
        fixture.write_text(json.dumps({**snapshot(), "schema": "t18.analyst.public.v1",
                                      "captured_at": "2026-10-03T09:00:00Z", "settings": {"key": "private-value"}}))
        with patch.object(report, "public_get", side_effect=AssertionError("network")):
            report.main(["--analyst-export", str(fixture), "--output", self.tmp.name])
        result = json.loads((Path(self.tmp.name)/"evidence.json").read_text())
        self.assertEqual(result["source"], "analyst_browser_export")
        self.assertEqual(result["fetched_at"], "2026-10-03T09:00:00Z")
        self.assertEqual(result["journal"]["live_measurements"], 0)
        self.assertFalse(result["coverage"]["complete"])
        self.assertNotIn("private-value", json.dumps(result))

    def test_unknown_export_schema_rejected(self):
        fixture = Path(self.tmp.name) / "input.json"
        fixture.write_text(json.dumps({**snapshot(), "schema": "unknown"}))
        with self.assertRaises(ValueError):
            report.analyst_input(fixture)

    def test_static_analyst_bundle_regenerates_plan_limits(self):
        out = Path(self.tmp.name)
        report.write_team_assets(report.make_report(**snapshot()), out)
        self.assertIn('href="index.html"', (out/"jurado.html").read_text())
        self.assertIn('"CHA-09": 100', (out/"plan-public.js").read_text())


if __name__ == "__main__":
    unittest.main()
