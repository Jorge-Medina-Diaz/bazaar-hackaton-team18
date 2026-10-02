import copy
from pathlib import Path
import tempfile
import threading
import time
import unittest

from bazaar_sdk import BazaarError
from live_monitor import LiveMonitor, POLL_SECONDS, read_key


class FakeReadOnlyAPI:
    def __init__(self):
        self.cash = 400
        self.assets = [{"id": 10, "ref": "SAL-02", "kind": "card", "your_value": 11}]
        self.failure = None
        self.reads = []
        self.offer_payload = {"offers": []}

    def me(self):
        self.reads.append(time.monotonic())
        return {"id": "t18", "cash": self.cash, "assets": copy.deepcopy(self.assets),
                "starter_broker_key": "MUST_NOT_REACH_BROWSER"}

    def clock(self):
        return {"tick": 45}

    def my_offers(self):
        if self.failure:
            raise BazaarError(self.failure)
        return self.offer_payload

    def my_threads(self):
        return {"threads": [{"id": 68, "status": "deal", "with": "abuela"}]}


class LiveMonitorTests(unittest.TestCase):
    def test_reads_all_sources_without_running_an_agent_or_exposing_keys(self):
        api = FakeReadOnlyAPI()
        monitor = LiveMonitor(api)
        monitor.poll()
        state = monitor.snapshot()
        self.assertEqual((state["cash"], state["assets"][0]["ref"], state["tick"]), (400, "SAL-02", 45))
        self.assertEqual(len(state["checks"]), 4)
        self.assertTrue(all(c["ok"] and c["verified_at"] for c in state["checks"].values()))
        self.assertNotIn("MUST_NOT_REACH_BROWSER", str(state))
        self.assertEqual(state["movements"], [])

    def test_failed_point_is_marked_and_does_not_block_other_updates(self):
        api = FakeReadOnlyAPI()
        api.offer_payload = {"offers": [{"id": 480, "status": "queued", "maker": "abuela"}]}
        monitor = LiveMonitor(api)
        monitor.poll()
        first = monitor.snapshot()["checks"]["ofertas"]["verified_at"]
        api.failure = "rate_limited"
        api.cash = 391
        api.assets.append({"id": 11, "ref": "LAV-03", "your_value": 20})
        monitor.poll()
        state = monitor.snapshot()
        check = state["checks"]["ofertas"]
        self.assertEqual((check["ok"], check["error"], check["verified_at"]), (False, "rate_limited", first))
        self.assertEqual(state["cash"], 391)
        self.assertEqual(state["offers"][0]["status"], "queued")
        self.assertEqual(state["movements"][0]["side"], "in")
        self.assertIsNone(state["movements"][0]["price"])
        monitor.poll()
        self.assertEqual(len(monitor.snapshot()["movements"]), 1)

    def test_bad_response_is_not_reported_as_verified_empty_offers(self):
        api = FakeReadOnlyAPI()
        api.offer_payload = {"unexpected": []}
        monitor = LiveMonitor(api)
        monitor.poll()
        self.assertEqual(monitor.snapshot()["checks"]["ofertas"]["error"], "invalid_response")

    def test_background_poll_runs_again_after_five_seconds_with_no_agent(self):
        api = FakeReadOnlyAPI()
        monitor = LiveMonitor(api)
        monitor.start()
        deadline = time.monotonic() + 7
        try:
            while len(api.reads) < 2 and time.monotonic() < deadline:
                threading.Event().wait(.05)
            self.assertGreaterEqual(len(api.reads), 2)
            self.assertAlmostEqual(api.reads[1] - api.reads[0], POLL_SECONDS, delta=.3)
        finally:
            monitor.close()

    def test_key_can_be_loaded_from_local_file_without_echoing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text('BAZAAR_URL=https://example.invalid\nBAZAAR_KEY="test-key"\n')
            self.assertEqual(read_key(path), "test-key")


if __name__ == "__main__":
    unittest.main()
