"""Observed movement, public history integrity and offline CLI regressions."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_harness.__main__ import main
from market_harness.timeline import archive_snapshot, read_archive, timeline, transition
from tests.test_market_harness import fixture, event


def frame(tick=101, hours=1, capture="2026-10-03T10:00:00Z", paused=False):
    s = fixture()
    s.update(captured_at=capture)
    s["clock"].update(tick=tick, t_hours=hours, round=2, paused=paused)
    s["clock_start"]["tick"] = tick
    s["leaderboard"].update(snapshot_tick=tick, round=2)
    s["venues"]["venues"][0]["trades"] = 1
    return s


def pair():
    a = frame()
    b = frame(102, 1.1, "2026-10-03T10:05:00Z")
    return a, b


class Movement(unittest.TestCase):
    def test_paused_wall_time_never_creates_rate(self):
        a = frame(paused=True); b = deepcopy(a); b["captured_at"] = "2026-10-03T18:00:00Z"
        b["venues"]["venues"][0]["trades"] = 2
        r = transition(a, b)
        self.assertEqual(r["venues"][0]["trades_delta"], 1)
        self.assertIsNone(r["venues"][0]["trades_per_game_hour"])
        self.assertIsNone(r["elapsed_game_hours"])

    def test_valid_game_hour_rate(self):
        a, b = pair(); b["venues"]["venues"][0]["trades"] = 2
        self.assertAlmostEqual(transition(a, b)["venues"][0]["trades_per_game_hour"], 10)

    def test_stale_leaderboard_explicit_and_separate_from_clock(self):
        a, b = pair(); b["leaderboard"]["snapshot_tick"] = 101
        r = transition(a, b)
        self.assertTrue(r["leaderboard"]["after"]["stale"])
        self.assertEqual(r["leaderboard"]["after"]["lag_ticks"], 1)
        self.assertTrue(r["leaderboard"]["comparable"])

    def test_leaderboard_round_or_tick_reset_nullifies_score_delta(self):
        for mutation in ({"snapshot_tick": 100}, {"round": 3}, {"snapshot_tick": 110}):
            a, b = pair(); b["leaderboard"].update(mutation)
            self.assertIsNone(transition(a, b)["teams"][0]["score_delta"])

    def test_clock_round_change_nullifies_rate_and_venue_delta(self):
        a, b = pair(); b["clock"]["round"] = 3
        r = transition(a, b)
        self.assertIn("round_changed", r["rate_blocks"])
        self.assertIsNone(r["venues"][0]["trades_delta"])

    def test_chronological_reset_not_hidden_by_tick_sort(self):
        a, b = pair(); b["clock"]["tick"] = 99; b["clock_start"]["tick"] = 99
        b["books"]["rastro"]["offers"] = []
        r = timeline([a, b])
        self.assertTrue(r["chronological_clock_reset_detected"])
        self.assertTrue(all(v["trades_per_game_hour"] is None for v in r["transitions"][0]["venues"]))

    def test_disappearance_never_is_settlement(self):
        a, b = pair(); b["books"]["rastro"]["offers"] = []
        r = transition(a, b)
        self.assertEqual(len(r["quotes"]["disappeared"]), 2)
        self.assertFalse(r["quotes"]["disappeared"][0]["settlement_inferred"])
        self.assertEqual(r["confirmed_newly_observed_settlements"], [])

    def test_cancellation_and_expiry_separated(self):
        a, b = pair(); offers = a["books"]["rastro"]["offers"]
        offers[1]["expires_tick"] = 102
        b["books"]["rastro"]["offers"] = []
        b["feed"]["events"] = [event(1, 102, "offer.cancelled", {"venue": "rastro", "offer": offers[0]["id"]})]
        reasons = {o["reason"] for o in transition(a, b)["quotes"]["disappeared"]}
        self.assertEqual(reasons, {"confirmed_cancelled", "expired_by_final_tick"})

    def test_failed_book_not_disappeared_quotes(self):
        a, b = pair(); b["books"]["rastro"]["offers"] = []; b["errors"]["rastro"] = "TimeoutError"
        self.assertEqual(transition(a, b)["quotes"]["disappeared"], [])

    def test_nonoverlap_flag_does_not_claim_id_gaps_missing(self):
        a, b = pair()
        a["feed"]["events"] = [event(1, 101, "clock.changed", {})]
        b["feed"]["events"] = [event(999, 102, "clock.changed", {})]
        r = transition(a, b)["feed"]
        self.assertTrue(r["non_overlapping_windows"])
        self.assertIsNone(r["coverage_complete"])

    def test_repeated_snapshot_settlement_unique(self):
        a, b = pair()
        b["feed"]["events"] = [event(1, 102, "settlement", {"settlement": 5, "price": 13, "venue": "v18",
            "parties": ["t01", "t02"], "items": [{"ref": "RET-01", "frm": "t01", "to": "t02"}]})]
        r = timeline([b, a, b])
        self.assertEqual(r["frames_used"], 2)
        self.assertEqual(len(r["confirmed_settlements_in_observed_history"]), 1)
        self.assertEqual(r["confirmed_settlements_in_observed_history"][0]["classification"], "cash_trade")

    def test_swap_is_not_cash_volume(self):
        a, b = pair()
        b["feed"]["events"] = [event(1, 102, "settlement", {"settlement": 5, "price": 0, "venue": "v18",
            "items": [{"frm": "t01", "to": "t02"}, {"frm": "t02", "to": "t01"}]})]
        self.assertEqual(transition(a, b)["confirmed_newly_observed_settlements"][0]["classification"], "swap")

    def test_same_settlement_new_envelope_not_counted_twice(self):
        a, b = pair()
        payload = {"settlement": 5, "price": 13, "venue": "v18", "items": [{"frm": "t01", "to": "t02"}]}
        a["feed"]["events"] = [event(1, 101, "settlement", payload)]
        b["feed"]["events"] = [event(2, 101, "settlement", payload)]
        self.assertEqual(transition(a, b)["confirmed_newly_observed_settlements"], [])

    def test_expired_still_visible_book_explicit(self):
        a, b = pair(); oid = b["books"]["rastro"]["offers"][0]["id"]
        b["books"]["rastro"]["offers"][0]["expires_tick"] = 102
        self.assertEqual(transition(a, b)["quotes"]["expired_by_final_tick"], [{"venue": "rastro", "offer": oid}])

    def test_asof_excludes_future_complete_frame(self):
        a, b = pair(); self.assertEqual(timeline([a, b], as_of=101)["frames_used"], 1)

    def test_incomplete_scan_does_not_infer_opportunity_disappearance(self):
        a, b = pair(); b["errors"]["rastro"] = "TimeoutError"
        r = transition(a, b)["opportunities"]
        self.assertFalse(r["comparison_available"])
        self.assertIsNone(r["removed"])

    def test_paused_new_observation_timing_cautious(self):
        a = frame(paused=True); b = deepcopy(a); b["captured_at"] = "2026-10-03T11:00:00Z"
        b["feed"]["events"] = [event(1, 101, "offer.listed", {})]
        self.assertTrue(transition(a, b)["newly_observed_activity_without_clock_progress"])


class Archive(unittest.TestCase):
    def test_dedup_immutable_merge(self):
        a, b = pair(); a["feed"]["events"] = [event(1, 101, "clock.changed", {})]
        b["feed"]["events"] = a["feed"]["events"] + [event(2, 102, "clock.changed", {})]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "events.json"
            archive_snapshot(p, a); archive_snapshot(p, b); archive_snapshot(p, b)
            self.assertEqual(len(read_archive(p)["events"]), 2)

    def test_conflict_preserves_existing_archive(self):
        a, b = pair(); a["feed"]["events"] = [event(1, 101, "clock.changed", {})]
        b["feed"]["events"] = [event(1, 101, "clock.changed", {"altered": True})]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "events.json"; archive_snapshot(p, a); old = p.read_bytes()
            with self.assertRaises(ValueError): archive_snapshot(p, b)
            self.assertEqual(p.read_bytes(), old)

    def test_private_and_future_records_rejected(self):
        for e in (dict(event(1, 101, "clock.changed", {}), scope="private"), event(1, 102, "clock.changed", {})):
            a = frame(); a["feed"]["events"] = [e]
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "events.json"
                with self.assertRaises(ValueError): archive_snapshot(p, a)
                self.assertFalse(p.exists())

    def test_corruption_fails_closed_preserves_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "events.json"; p.write_text("{broken")
            with self.assertRaises(ValueError): archive_snapshot(p, frame())
            self.assertEqual(p.read_text(), "{broken")

    def test_archive_future_relative_to_refresh_reset_rejected(self):
        a, b = pair()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "events.json"; archive_snapshot(p, b)
            with self.assertRaises(ValueError): archive_snapshot(p, a)

    def test_archive_not_retroactive_into_historical_opportunities(self):
        a, b = pair()
        archive = {"schema": 1, "max_tick": 200, "events": [event(1, 200, "clock.changed", {})]}
        r = timeline([a, b], archive=archive)
        self.assertEqual(r["unique_public_events"], 0)


class CLI(unittest.TestCase):
    def test_timeline_cli_no_network_or_archive_mutation(self):
        a, b = pair()
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for i, s in enumerate((a, b)):
                p = Path(d) / f"s{i}.json"; p.write_text(json.dumps(s)); paths += ["--snapshot", str(p)]
            with patch("market_harness.__main__.collect", side_effect=AssertionError("network")), patch("builtins.print"):
                main(["timeline", *paths, "--out", d])
            self.assertTrue((Path(d) / "movement.md").exists())
            self.assertFalse((Path(d) / "public-events.json").exists())

    def test_refresh_archives_and_previous_loaded_before_overwrite(self):
        a, b = pair()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "snapshot.json"; p.write_text(json.dumps(a))
            with patch("market_harness.__main__.collect", return_value=b), patch("builtins.print"):
                main(["refresh", "--previous", str(p), "--out", d])
            self.assertTrue((Path(d) / "public-events.json").exists())
            result = json.loads((Path(d) / "timeline.json").read_text())
            self.assertEqual(result["transitions"][0]["from_tick"], 101)


if __name__ == "__main__":
    unittest.main()
