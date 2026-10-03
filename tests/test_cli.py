"""M16 cli tests: arm/pause/stop/resume/status/do without API calls; arm refuses red stages and leaves the journal
alone with a runner alive; two runs -> exit 3; `stop` from another folder writes STOP in the root; selftest is red
with 0 tests; run without --live never writes."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import tests  # noqa: F401  (BAZAAR_TEST=1)
import bazaar
from agent import runner
from agent.contracts import Paths
from agent.execution import writer_lock

REPO = Path(__file__).resolve().parents[1]


def cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = bazaar.main(list(argv))
    return rc, buf.getvalue()


class NoNetwork:
    """Any HTTP attempt fails the test."""

    def __enter__(self):
        def boom(*a, **k):
            raise AssertionError("network call from the CLI")
        self.ps = [mock.patch("urllib.request.urlopen", boom),
                   mock.patch("agent.transport._urllib_http", boom),
                   mock.patch("agent.transport.GuardedTransport.__init__", boom)]
        for p in self.ps:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self.ps:
            p.stop()


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="t18-cli-"))
        self.paths = Paths.at(self.root)
        self.paths.state.mkdir(parents=True, exist_ok=True)

    def green(self, stages=("core", "hygiene")):
        ch = runner.code_hash()
        self.paths.selftest.write_text(json.dumps({s: {"green": True, "code_hash": ch} for s in stages}),
                                       encoding="utf-8")

    def inbox(self):
        return sorted(p.name for p in self.paths.inbox.glob("*.json")) if self.paths.inbox.exists() else []


class TestOrders(Base):
    def test_arm_with_runner_alive_writes_inbox_not_journal(self):
        self.green()
        with NoNetwork(), writer_lock(self.paths):
            rc, out = cli("--root", str(self.root), "arm", "hygiene", "--why", "J0")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(self.inbox()), 1)
        order = json.loads(next(self.paths.inbox.glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual((order["cmd"], order["tactic"], order["why"]), ("arm", "hygiene", "J0"))
        self.assertFalse(self.paths.journal.exists())
        self.assertFalse(self.paths.armed.exists())

    def test_arm_refuses_red_stage_and_unknown(self):
        self.green(stages=("core",))
        with NoNetwork(), writer_lock(self.paths):
            rc, out = cli("--root", str(self.root), "arm", "dealers", "--why", "x")
            self.assertEqual(rc, 1)
            self.assertIn("not green", out)
            rc, _ = cli("--root", str(self.root), "arm", "bogus", "--why", "x")
            self.assertEqual(rc, 1)
        self.assertEqual(self.inbox(), [])

    def test_arm_stale_hash_is_red(self):
        self.paths.selftest.write_text(json.dumps({"core": {"green": True, "code_hash": "old"},
                                                   "hygiene": {"green": True, "code_hash": "old"}}), encoding="utf-8")
        with writer_lock(self.paths):
            rc, _ = cli("--root", str(self.root), "arm", "hygiene", "--why", "x")
        self.assertEqual(rc, 1)

    def test_orders_need_a_runner(self):
        self.green()
        rc, out = cli("--root", str(self.root), "pause", "rastro", "--why", "x")
        self.assertEqual(rc, 1)
        self.assertEqual(self.inbox(), [])
        with writer_lock(self.paths):
            rc, _ = cli("--root", str(self.root), "pause", "rastro", "--why", "x")
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.inbox()), 1)

    def test_do_validates_and_goes_to_inbox_when_runner_alive(self):
        with NoNetwork(), writer_lock(self.paths):
            rc, out = cli("--root", str(self.root), "do", "cancel", "--args", '{"offer_id": 5}', "--why", "x")
            self.assertEqual(rc, 1)                                  # missing "ref"
            rc, out = cli("--root", str(self.root), "do", "cancel", "--args", '{"offer_id": 5, "ref": null}',
                          "--why", "J0")
            self.assertEqual(rc, 0, out)
            rc, _ = cli("--root", str(self.root), "do", "open_venue", "--args", "{}", "--why", "x")
            self.assertEqual(rc, 1)
        names = self.inbox()
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].endswith("-do.json"))
        self.assertFalse(self.paths.journal.exists())

    def test_stop_flatten_with_runner_leaves_order(self):
        with writer_lock(self.paths):
            rc, _ = cli("--root", str(self.root), "stop", "x", "--flatten")
        self.assertEqual(rc, 0)
        self.assertTrue(self.inbox()[0].endswith("-flatten.json"))
        self.assertFalse((self.root / "STOP").exists())
        rc, out = cli("--root", str(self.root), "stop", "y", "--flatten")       # no runner: STOP at once
        self.assertTrue((self.root / "STOP").exists())
        self.assertIn("flatten not done", out)


class TestStopResumeStatus(Base):
    def test_stop_from_another_folder_writes_root_stop(self):
        other = Path(tempfile.mkdtemp(prefix="t18-cwd-"))
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, str(REPO / "bazaar.py"), "--root", str(self.root), "stop", "kill",
                            "now"], cwd=str(other), env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.root / "STOP").read_text(encoding="utf-8").strip(), "kill now")
        self.assertEqual(list(other.iterdir()), [])

    def test_default_root_is_the_repo_not_the_cwd(self):
        with mock.patch.dict(os.environ, {"BAZAAR_TEST": ""}):
            self.assertEqual(bazaar._paths(None).root, REPO)

    def test_resume_removes_every_stop_variant(self):
        for n in ("STOP", "stop.txt", "STOP.md"):
            (self.root / n).write_text("x", encoding="utf-8")
        (self.root / "stopwatch.py").write_text("x", encoding="utf-8")
        rc, out = cli("--root", str(self.root), "resume", "--why", "ok")
        self.assertEqual(rc, 0)
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.is_file()), ["stopwatch.py"])

    def test_status_makes_no_calls(self):
        with NoNetwork():
            rc, out = cli("--root", str(self.root), "status")
        self.assertEqual(rc, 0, out)
        self.assertIn("journal  -", out)
        (self.root / "STOP").write_text("why", encoding="utf-8")
        with NoNetwork():
            rc, out = cli("--root", str(self.root), "status")
        self.assertIn("STOP     STOP", out)


class TestRunAndSelftest(Base):
    def test_two_runs_second_exits_3(self):
        with writer_lock(self.paths):
            rc, out = cli("--root", str(self.root), "run", "--max-ticks", "1")
        self.assertEqual(rc, 3, out)

    def test_run_without_live_is_dry(self):
        calls = {}

        def fake_run(mode, armed, **kw):
            calls.update(mode=mode, armed=list(armed))
            return 0
        self.green(stages=("core",))
        with mock.patch.object(runner, "run", fake_run):
            rc, _ = cli("--root", str(self.root), "run", "--arm", "hygiene,rastro")
            self.assertEqual((rc, calls["mode"], calls["armed"]), (0, "dry", ["hygiene", "rastro"]))
            rc, out = cli("--root", str(self.root), "run", "--live", "--arm", "hygiene,rastro")
            self.assertEqual((calls["mode"], calls["armed"]), ("live", []))   # stages red -> nothing armed
            self.green(stages=("core", "hygiene"))
            cli("--root", str(self.root), "run", "--live", "--arm", "hygiene")
            self.assertEqual(calls["armed"], ["hygiene"])
            rc, _ = cli("--root", str(self.root), "run", "--arm", "nope")
            self.assertEqual(rc, 1)

    def test_selftest_red_with_zero_tests(self):
        rc, ran, _ = bazaar.run_tests([], pattern="no_such_test_zz*.py")
        self.assertEqual(ran, 0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = bazaar.selftest(self.paths, stages=("core", "hygiene"), runner_fn=lambda mods: (0, 0, "Ran 0 tests"))
        self.assertEqual(code, 1)
        st = json.loads(self.paths.selftest.read_text(encoding="utf-8"))
        self.assertFalse(st["core"]["green"])
        self.assertFalse(st["hygiene"]["green"])

    def test_selftest_green_and_watch(self):
        def ok(mods):
            return 0, 500, "OK"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(bazaar.selftest(self.paths, stages=("core",), runner_fn=ok), 0)
        st = json.loads(self.paths.selftest.read_text(encoding="utf-8"))
        self.assertEqual(st["core"]["code_hash"], runner.code_hash())
        self.assertTrue(runner.tactic_green("manual", self.paths))

        def dirty(mods):
            (self.paths.state / "armed.json").write_text("[]", encoding="utf-8")
            return 0, 500, "OK"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(bazaar.selftest(self.paths, stages=("core",), runner_fn=dirty), 1)
        self.assertFalse(json.loads(self.paths.selftest.read_text(encoding="utf-8"))["core"]["green"])

    def test_clockcheck_against_fake(self):
        from sim.world import FakeGame
        from agent import transport
        g = FakeGame(seed=1)
        buf = io.StringIO()
        # Runner tests use an epoch-based fake clock; clockcheck uses monotonic.
        # Isolate the process-wide limiter so stage order cannot cause a huge sleep.
        previous = transport._PUBLIC_LAST[0]
        with redirect_stdout(buf), mock.patch.object(transport, '_PUBLIC_LAST', [float('-inf')]):
            rc = bazaar.cmd_clockcheck("http://127.0.0.1:9", http=g.http)
        self.assertEqual(transport._PUBLIC_LAST[0], previous)
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertIn("reading", buf.getvalue())

    def test_replay_not_built_is_red(self):
        if (REPO / "tests" / "test_replay_friday.py").exists():
            self.skipTest("replay built")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli("--root", str(self.root), "replay-friday")[0], 1)


if __name__ == "__main__":
    unittest.main()
