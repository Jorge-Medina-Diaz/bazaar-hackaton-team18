"""M17: INV-02 end to end. 1,000 ticks in dry against the fake game (adversarial bots, dealers, duels) -> 0 writes.

The runner, Gate, Sensor, Journal and GuardedTransport are the real ones; only the server is fake (in process,
no sockets). Dry must still decide (the Gate journals `would` rows), but nothing non-GET reaches the server.
"""
from __future__ import annotations

import collections
import unittest

import tests  # noqa: F401  (test isolation)
from agent import runner
from tests import m17_support as S


class TestDryThousandTicks(unittest.TestCase):
    TICKS = 1000

    @classmethod
    def setUpClass(cls):
        cls.g = S.saturday(7, bots=("twisted", "opener", "injector"), duels=False)   # light: speed (selftest)
        cls.p = S.paths("t18-m17-dry-")
        S.green(cls.p)                                    # green selftest must not matter: dry never writes
        cls.rc = S.run(cls.g, cls.p, mode="dry", armed=runner.TACTICS, ticks=cls.TICKS)
        cls.rows = S.rows(cls.p)

    def test_runs_to_the_end(self):
        self.assertEqual(self.rc, 0)
        self.assertEqual(sum(1 for r in self.rows if r["kind"] == "tick"), self.TICKS)

    def test_zero_writes_reach_the_server(self):
        self.assertEqual(S.writes(self.g), [])

    def test_no_intent_rows_and_decisions_are_would(self):
        kinds = collections.Counter(r["kind"] for r in self.rows)
        self.assertEqual(kinds.get("intent", 0), 0)
        self.assertEqual(kinds.get("result", 0), 0)
        self.assertEqual(kinds.get("unknown", 0), 0)
        self.assertGreater(kinds.get("would", 0), 0, "dry must still decide (Gate `would` rows)")
        self.assertTrue(all(r.get("mode") == "dry" for r in self.rows if "mode" in r))

    def test_no_stop_written(self):
        self.assertFalse(any(p.name.upper().startswith("STOP") for p in self.p.root.iterdir()))
        self.assertFalse([r for r in self.rows if r["kind"] == "stop"])


if __name__ == "__main__":
    unittest.main()
