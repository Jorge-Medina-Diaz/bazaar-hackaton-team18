"""M17: chaos (INV-14, INV-15, INV-19; spec §8 and §10 test_chaos).

1. Process death at 4 points of a write (while writing the intent row, after the intent row and before the wire,
   after the server committed and before the result row, while writing the result row), several times each,
   each followed by a restart of the same `run` on the same root -> 0 duplicate sends (every write of ours has its
   own intent row written before it, no intent written twice), nothing sent before the restart reconciled.
2. Transport faults on writes (drop_after_commit, 500, html_200, truncated_body, redirect_302, incomplete_read,
   429 wait/rate) -> never re-sent, the run goes on, 0 invariant violations.
3. Unexpected shapes on reads (type_swap, missing_field, extra_field) -> the source goes down / refused, no STOP.

A "death" is a BaseException raised inside the runner: it unwinds through every `except Exception`, the writer
lock is released (as the OS would) and nothing after the crash point runs. NOTES (M17): the spec's 5 real
subprocess kills are not staged (the fake game lives in this process); the in-process death covers the same
WAL/idempotency paths but not a torn half-written journal line (test_journal covers the torn tail).
"""
from __future__ import annotations

import collections
import contextlib
import unittest
from unittest import mock

import tests  # noqa: F401  (test isolation)
from agent import runner
from agent.journal import Journal
from sim import faults, invariants
from tests import m17_support as S


class Crash(BaseException):
    """Process death: not an Exception, so no handler in the harness catches it."""


POINTS = ("intent_write", "before_wire", "after_wire", "result_write")
DEATHS_PER_POINT = 4


@contextlib.contextmanager
def crash_at(point: str, nth: int, game, hits: list):
    """Kill the process at the nth write that reaches `point`."""
    seen = {"n": 0}

    def due() -> bool:
        seen["n"] += 1
        return seen["n"] == nth

    if point in ("intent_write", "result_write"):
        orig = Journal.write
        kind_at = "intent" if point == "intent_write" else "result"

        def write(self, kind, **fields):
            if kind == kind_at and due():
                hits.append((point, fields.get("id"), game.tick))
                raise Crash(point)
            return orig(self, kind, **fields)

        with mock.patch.object(Journal, "write", write):
            yield
        return
    orig_http = game.http

    def http(method, url, data=None, headers=None, timeout=None):
        if method != "GET" and due():
            hits.append((point, f"{method} {url}", game.tick))
            if point == "before_wire":
                raise Crash(point)
            out = orig_http(method, url, data, headers, timeout)       # the server commits ...
            raise Crash(point)                                         # ... and we die before reading the reply
        return orig_http(method, url, data, headers, timeout)

    game.http = http
    try:
        yield
    finally:
        game.http = orig_http


def run_once(g, p, ticks):
    clock = S.GameClock(g)
    tr = S.loop_transport(g, p, clock, "live")      # built per run: the transport captures game.http
    return S.run(g, p, mode="live", armed=runner.TACTICS, ticks=ticks, transport=tr, clock=clock)


class TestDeathsAndRestarts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = S.saturday(21)
        cls.p = S.paths("t18-m17-chaos-")
        S.green(cls.p)
        cls.hits, cls.rcs = [], []
        for point in POINTS:
            for i in range(DEATHS_PER_POINT):
                try:
                    with crash_at(point, 1 + i % 3, cls.g, cls.hits):
                        cls.rcs.append(run_once(cls.g, cls.p, 6))
                except Crash:
                    cls.rcs.append("crash")
        cls.final_rc = run_once(cls.g, cls.p, 6)                          # clean restart at the end
        cls.rows = S.rows(cls.p)

    def test_deaths_happened_at_every_point(self):
        got = collections.Counter(h[0] for h in self.hits)
        for point in POINTS:
            self.assertGreaterEqual(got[point], 2, (point, got))

    def test_restarts_run_clean(self):
        self.assertEqual(self.final_rc, 0, [r for r in self.rows if r["kind"] in ("stop", "alarm")][-5:])
        self.assertFalse([r for r in self.rows if r["kind"] == "stop"])

    def test_zero_duplicate_sends(self):
        bad = [v for v in invariants.check(self.g, self.p.journal) if v.startswith(("INV-14", "INV-15"))]
        self.assertEqual(bad, [])
        ids = collections.Counter(r["id"] for r in self.rows if r["kind"] == "intent")
        self.assertEqual([i for i, n in ids.items() if n > 1], [])
        # the same request (method, path, body) never reaches the server twice from one intent
        writes = collections.Counter((q["method"], q["path"], str(q["body"])) for q in S.writes(self.g))
        intents = collections.Counter(tuple(r["request"][:2]) for r in self.rows if r["kind"] == "intent")
        for (m, path, _b), n in writes.items():
            self.assertLessEqual(n, max(1, intents[(m, path)]), (m, path))

    def test_no_loss_and_no_other_violation(self):
        v = invariants.check(self.g, self.p.journal)
        self.assertEqual([x for x in v if x.startswith(("INV-04", "INV-07", "INV-01", "INV-02"))], [])
        self.assertEqual(self.g.oracle()["losses"], [])

    def test_crashed_intents_never_resent(self):
        rows_by_id = collections.defaultdict(list)
        for r in self.rows:
            if r.get("id"):
                rows_by_id[r["id"]].append(r["kind"])
        for point, ident, _tick in self.hits:
            if point == "result_write":
                self.assertEqual(rows_by_id[ident].count("intent"), 1, ident)


class StopWriter:
    """A person creating STOP in the root at a given tick (from inside the game loop: mid-tick for the runner)."""

    def __init__(self, root, at):
        self.root, self.at, self.done_at = root, at, None

    def on_tick(self, game):
        if self.done_at is None and game.tick >= self.at:
            (self.root / "STOP").write_text("manual stop (test)", encoding="utf-8")
            self.done_at = game.tick


class TestStopFile(unittest.TestCase):
    def test_stop_halts_within_one_tick_and_nothing_is_written_after_it(self):
        g = S.saturday(25)
        p = S.paths("t18-m17-stop-")
        S.green(p)
        sw = g.add_bot(StopWriter(p.root, g.tick + 6))
        rc = run_once(g, p, 40)
        self.assertEqual(rc, 2)
        self.assertIsNotNone(sw.done_at)
        rows = S.rows(p)
        ticks = [r["tick"] for r in rows if r["kind"] == "tick"]
        self.assertLessEqual(max(ticks) - sw.done_at, 1, "the runner must stop within one tick")
        late = [q for q in S.writes(g) if q["tick"] >= sw.done_at]
        self.assertEqual(late, [], "no write may reach the server once STOP exists")
        self.assertGreater(len(S.writes(g)), 0, "the run wrote before STOP (not vacuous)")


class TestTransportFaults(unittest.TestCase):
    WRITE_FAULTS = ("drop_after_commit", "500", "html_200", "truncated_body", "redirect_302", "incomplete_read",
                    "429_wait", "429_rate")

    def test_every_write_fault_is_unknown_or_deferred_never_resent(self):
        g = S.saturday(22)
        g.faults = faults.Plan([{"do": d, "method": m, "times": 2, "skip": 2 * i}
                                for i, d in enumerate(self.WRITE_FAULTS) for m in ("POST",)])
        p = S.paths("t18-m17-faults-")
        S.green(p)
        rc = run_once(g, p, 40)
        rows = S.rows(p)
        fired = {f["do"] for f in g.faults.fired}
        self.assertGreaterEqual(len(fired), 4, fired)
        self.assertEqual(rc, 0, [r for r in rows if r["kind"] in ("stop",)])
        v = invariants.check(g, p.journal)
        self.assertEqual([x for x in v if not x.startswith("INV-03 429")], [])   # 429s here are injected
        ids = collections.Counter(r["id"] for r in rows if r["kind"] == "intent")
        self.assertEqual([i for i, n in ids.items() if n > 1], [])
        unknown = [r for r in rows if r["kind"] == "unknown"]
        self.assertTrue(unknown, "drop/500/html/truncated/redirect must be classified unknown")

    def test_odd_shapes_on_reads_do_not_stop(self):
        g = S.saturday(23)
        g.faults = faults.Plan([{"do": d, "method": "GET", "path": path, "times": 3, "field": fld}
                                for d, path, fld in (("type_swap", r"/api/me/offers", "offers"),
                                                     ("missing_field", r"/api/venues/rastro/offers", "offers"),
                                                     ("extra_field", r"/api/me", "cash"),
                                                     ("bad_json", r"/api/duels", None))])
        p = S.paths("t18-m17-shapes-")
        S.green(p)
        rc = run_once(g, p, 20)
        rows = S.rows(p)
        self.assertTrue(g.faults.fired)
        self.assertEqual(rc, 0, [r for r in rows if r["kind"] == "stop"])
        self.assertEqual([x for x in invariants.check(g, p.journal) if not x.startswith("INV-03")], [])

    def test_rate_limited_server_never_sees_more_than_our_budget(self):
        g = S.saturday(24)
        g.rate = (5.0, 20)                                # the real server's limit (measured)
        p = S.paths("t18-m17-rate-")
        S.green(p)
        rc = run_once(g, p, 30)
        self.assertEqual(rc, 0)
        ours = [q for q in g.requests if q["team"] == "t18"]
        self.assertEqual([q for q in ours if q["status"] == 429], [])
        self.assertEqual(invariants.check(g, p.journal), [])


if __name__ == "__main__":
    unittest.main()
