"""M15 runner tests: choose (order, budgets, accepts by deadline), tactic isolation (INV-19), pluggable tactics,
late window for duel_accept, single writer (exit 3), STOP (exit 2), dry = 0 writes, inbox orders, manual `do`,
flatten. End-to-end cases drive the real Gate/Sensor/Journal against sim.FakeGame in process (no sockets)."""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest import mock

import tests  # noqa: F401  (test isolation: BAZAAR_TEST=1)
from agent import runner
from agent import transport as T
from agent.contracts import FRIDAY, TEAM, Limits, Outcome, Paths, Prediction, World, intent_id, make_intent
from agent.execution import writer_lock
from sim.world import FakeGame

REPO = Path(__file__).resolve().parents[1]
PLAN = REPO / "tests" / "fixtures" / "plan_night.json"   # frozen: config/plan.json changes during the game
NONE_P = Prediction(0.0, 0.0, "0", 0, None, "none")
STAGES = ("core", "hygiene", "dealers", "rastro", "closer", "duels")


def make_world(**kw) -> World:
    base = dict(tick=100, t_hours=5.0, round=2, tick_seconds=30.0, tick_deadline=1e12,
                clock=MappingProxyType({"paused": False, "doors": "open", "next_tick_in": 30}), limits=FRIDAY,
                reading="N", me=MappingProxyType({}), my_offers=(), offers_to_us=(), board=(), own_pseudonym=None,
                threads=MappingProxyType({}), foreign_threads=(), duels=(), catalog=MappingProxyType({}),
                schedule=MappingProxyType({}), released_sets=frozenset(), feed_new=(),
                server_values=MappingProxyType({}), down=frozenset())
    base.update(kw)
    return World(**base)


def cancel(oid, tactic="hygiene", prio=0):
    return make_intent("cancel", tactic, {"offer_id": oid, "ref": None}, "r", "e", NONE_P, priority=prio)


def listing(i, tactic="rastro", prio=0):
    return make_intent("list_offer", tactic, {"side": "sell", "ref": f"LAV-0{i % 9 + 1}", "asset_id": 100 + i,
                                              "price": 10 + i, "expires_ticks": 60, "closer": False,
                                              "want_ref": None}, "r", "e", NONE_P, priority=prio)


def accept(oid, prio=0):
    return make_intent("accept", "rastro", {"offer_id": oid, "source": "team", "ref": "SAL-02", "side": "buy",
                                            "price": 9, "thread_id": None, "give_asset": None, "fingerprint": "f",
                                            "resupply": False, "venue": "rastro"}, "r", "e", NONE_P, priority=prio)


def duel_accept(did, prio=0):
    return make_intent("duel_accept", "duels", {"duel_id": did, "fingerprint": "x"}, "r", "e", NONE_P, priority=prio)


def duel_say(did, price=50):
    return make_intent("duel_say", "duels", {"duel_id": did, "price": price, "days": None, "template": "duel",
                                             "variant": 0}, "r", "e", NONE_P)


def open_thread(ref="RET-01"):
    return make_intent("open_thread", "dealers", {"dealer": "abuela", "side": "buy", "ref": ref, "asset_ids": (),
                                                  "limit": 20}, "r", "e", NONE_P)


def say(tid, price):
    return make_intent("say", "dealers", {"thread_id": tid, "ref": "RET-01", "price": price, "template": "abuela_buy",
                                          "variant": 0}, "r", "e", NONE_P)


class Cfg:
    DUEL_ACCEPT_SHARED = True
    LISTINGS_PER_TICK = 6
    OPEN_OFFERS_MARGIN = 4
    THREADS_MARGIN = 1
    TICK_MARGIN_S = 2.0


# ------------------------------------------------------------------------------------------- choose

class TestChoose(unittest.TestCase):
    def test_one_accept_per_tick_earliest_deadline_wins(self):
        w = make_world(board=({"id": 7, "expires_tick": 300}, {"id": 8, "expires_tick": 120}),
                       duels=({"duel": 5, "deadline_tick": 110},))
        out = runner.choose([accept(7, prio=99), accept(8), duel_accept(5)], w, Cfg())
        acc = [it for it in out if it.kind in ("accept", "duel_accept")]
        self.assertEqual(len(acc), 1)
        self.assertEqual(acc[0].kind, "duel_accept")          # deadline 110 < 120 < 300, priority does not matter
        out = runner.choose([accept(7, prio=99), accept(8)], w, Cfg())
        self.assertEqual([it.args["offer_id"] for it in out], [8])

    def test_accept_budget_follows_limits_and_unshared_duels(self):
        w = make_world(limits=Limits(2, 1, 6, 30, 12), board=({"id": 7, "expires_tick": 300},
                                                              {"id": 8, "expires_tick": 120}))
        self.assertEqual(len(runner.choose([accept(7), accept(8), duel_accept(5)], w, Cfg())), 2)
        c = Cfg()
        c.DUEL_ACCEPT_SHARED = False
        w1 = make_world(board=({"id": 7, "expires_tick": 300},))
        kinds = sorted(it.kind for it in runner.choose([accept(7), duel_accept(5)], w1, c))
        self.assertEqual(kinds, ["accept", "duel_accept"])
        self.assertEqual(runner.choose([accept(7)], make_world(limits=Limits(0, 1, 6, 30, 12)), Cfg()), [])

    def test_listing_budget_and_exposure_first(self):
        its = [listing(i, prio=50) for i in range(10)] + [cancel(900 + i) for i in range(3)]
        out = runner.choose(its, make_world(), Cfg())
        self.assertEqual(len(out), 6)                         # min(6, 12 - 2)
        self.assertEqual([it.kind for it in out[:3]], ["cancel"] * 3)
        w = make_world(limits=Limits(1, 1, 6, 30, 5))         # min(6, 5 - 2) = 3
        self.assertEqual(len(runner.choose(its, w, Cfg())), 3)
        for lim, n in ((2, 1), (3, 1), (1, 1), (0, 0)):         # small limits keep one slot (was 0 at 2)
            self.assertEqual(len(runner.choose(its, make_world(limits=Limits(1, 1, 6, 30, lim)), Cfg())), n, lim)
        self.assertEqual(len(runner.choose([open_thread()], make_world(limits=Limits(1, 1, 1, 30, 12)), Cfg())), 1)

    def test_open_offer_room(self):
        mine = tuple({"id": i, "maker": TEAM, "status": "open"} for i in range(25))
        out = runner.choose([listing(i) for i in range(5)], make_world(my_offers=mine), Cfg())
        self.assertEqual(len(out), 1)                         # 30 - 4 - 25

    def test_threads_messages_and_duplicates(self):
        out = runner.choose([open_thread("RET-01"), open_thread("RET-02")], make_world(), Cfg())
        self.assertEqual(len(out), 2)
        four = tuple({"duel": i, "deadline_tick": 200} for i in range(4))
        self.assertEqual(runner.choose([open_thread()], make_world(duels=four), Cfg()), [])
        threads = MappingProxyType({i: {"status": "open", "team": TEAM} for i in range(5)})
        self.assertEqual(runner.choose([open_thread()], make_world(threads=threads), Cfg()), [])
        out = runner.choose([say(3, 10), say(3, 11), say(4, 10)], make_world(), Cfg())
        self.assertEqual(sorted((it.args["thread_id"], it.args["price"]) for it in out), [(3, 10), (4, 10)])
        out = runner.choose([duel_say(5), duel_accept(5), duel_say(6)], make_world(), Cfg())
        self.assertEqual(sorted((it.kind, it.args["duel_id"]) for it in out), [("duel_accept", 5), ("duel_say", 6)])
        out = runner.choose([cancel(1, "hygiene"), cancel(1, "rastro"), cancel(1, "hygiene")], make_world(), Cfg())
        self.assertEqual(len(out), 1)

    def test_garbage_is_ignored(self):
        self.assertEqual(runner.choose([None, "x", 3], make_world(), Cfg()), [])


# ------------------------------------------------------------------------------------------ late window

class FakeClock:
    def __init__(self, t=0.0):
        self.t = t
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


class FakeGate:
    def __init__(self, clock):
        self.clock, self.calls, self.book = clock, [], None

    def execute(self, it, world):
        self.calls.append((it.kind, world.tick, self.clock.now()))
        return Outcome(intent_id(world.tick, it), "would")


class FakeSensor:
    def __init__(self, world):
        self.world, self.reads = world, 0

    def snapshot(self, prev):
        self.reads += 1
        return self.world, None


class FakeCal:
    def __init__(self):
        self.p = {}

    def paused(self, t):
        return t in self.p

    def pause(self, t, why, tick=None):
        self.p[t] = why

    def resume(self, t, why):
        self.p.pop(t, None)


class FakeJournal:
    def __init__(self):
        self.rows = []

    def write(self, kind, **f):
        self.rows.append(dict(f, kind=kind))
        return len(self.rows)


def bare_runner(world, clock, gate=None, **kw):
    tmp = Paths.at(tempfile.mkdtemp(prefix="t18-runner-"))
    gate = gate or FakeGate(clock)
    r = runner.Runner(mode="dry", armed=(), paths=tmp, plan_cfg={}, transport=None, journal=FakeJournal(),
                      gate=gate, sensor=FakeSensor(world), calibrator=FakeCal(), cfg=Cfg(), clock=clock, **kw)
    return r, gate


class TestLateWindow(unittest.TestCase):
    def test_duel_accept_waits_for_mid_tick_and_uses_fresh_read(self):
        clk = FakeClock(0.0)
        # tick ends at deadline + margin = 28 + 2 = 30; mid = 15
        w = make_world(tick_deadline=28.0, tick_seconds=30.0, duels=({"duel": 5, "deadline_tick": 110},))
        r, gate = bare_runner(w, clk)
        fresh = duel_accept(5)
        with mock.patch("agent.tactics.duels.propose", return_value=[fresh, duel_say(6)]):
            outs = r.late_window(w, [duel_accept(5)], [])
        self.assertEqual([c[0] for c in gate.calls], ["duel_accept"])
        self.assertGreaterEqual(gate.calls[0][2], 15.0)
        self.assertEqual(r.sensor.reads, 1)
        self.assertEqual(len(outs), 1)

    def test_no_late_accept_when_budget_used_or_tick_moved(self):
        clk = FakeClock(20.0)
        w = make_world(tick_deadline=28.0, duels=({"duel": 5, "deadline_tick": 110},))
        r, gate = bare_runner(w, clk)
        used = [(accept(7), Outcome("x", "sent"))]
        with mock.patch("agent.tactics.duels.propose", return_value=[duel_accept(5)]):
            self.assertEqual(r.late_window(w, [], used), [])
            r.sensor.world = make_world(tick=101, duels=w.duels)
            self.assertEqual(r.late_window(w, [], []), [])
        self.assertEqual(gate.calls, [])

    def test_tactic_exceptions_isolated_and_paused_after_three(self):
        clk = FakeClock()
        r, _ = bare_runner(make_world(), clk)
        r.valuer = object()

        def boom(*a, **k):
            raise ZeroDivisionError("x")
        good = cancel(1, "rastro")
        with mock.patch("agent.tactics.hygiene.propose", side_effect=boom), \
                mock.patch("agent.tactics.dealers.propose", return_value=[]), \
                mock.patch("agent.tactics.dealers.DealerState.rebuild", return_value=None), \
                mock.patch("agent.tactics.rastro.propose", return_value=[good]), \
                mock.patch("agent.tactics.duels.propose", return_value=[]):
            for t in (100, 101):
                got = r.propose_all(make_world(tick=t), object(), [])
                self.assertEqual(got, [good])                    # hygiene raising does not stop rastro
            self.assertFalse(r.calibrator.paused("hygiene"))
            r.propose_all(make_world(tick=102), object(), [])
        self.assertTrue(r.calibrator.paused("hygiene"))
        self.assertFalse(r.calibrator.paused("rastro"))

    def test_missing_tactic_module_is_skipped(self):
        r, _ = bare_runner(make_world(), FakeClock())
        mods = (("hygiene", "agent.tactics.no_such_module"), ("rastro", "agent.tactics.rastro"))
        with mock.patch.object(runner, "TACTIC_MODULES", mods), \
                mock.patch("agent.tactics.rastro.propose", return_value=[cancel(2, "rastro")]):
            self.assertEqual(len(r.propose_all(make_world(), object(), [])), 1)
            r.propose_all(make_world(), object(), [])
        alarms = [x for x in r.journal.rows if x["kind"] == "alarm" and "not available" in x.get("why", "")]
        self.assertEqual(len(alarms), 1)


# ----------------------------------------------------------------------------------------- end to end

class GameClock:
    """Virtual clock whose sleep advances the fake game when a tick boundary is crossed."""

    def __init__(self, game):
        self.g, self.v = game, game.clock

    def now(self):
        return self.v.now()

    def sleep(self, s):
        self.v.sleep(s)
        while self.v.now() >= self.g.tick_started + self.g.tick_seconds:
            self.g.advance()


class E2E(unittest.TestCase):
    def setUp(self):
        self.g = FakeGame(seed=3, tick_seconds=30.0)
        self.clk = GameClock(self.g)
        self.paths = Paths.at(tempfile.mkdtemp(prefix="t18-runner-e2e-"))
        self.paths.state.mkdir(parents=True, exist_ok=True)

    def transport(self, mode):
        return T.GuardedTransport("http://127.0.0.1:9", "tk-test", mode=mode, paths=self.paths,
                                  limiter=T.RateLimiter(rate=1000, burst=100, clock=self.clk), http=self.g.http)

    def green(self, stages=STAGES):
        ch = runner.code_hash()
        self.paths.selftest.write_text(json.dumps({s: {"green": True, "code_hash": ch} for s in stages}),
                                       encoding="utf-8")

    def run_(self, mode="dry", armed=("hygiene",), ticks=4, **kw):
        return runner.run(mode, list(armed), paths=self.paths, plan_path=PLAN, max_ticks=ticks,
                          transport=self.transport(mode), clock=self.clk, **kw)

    def writes(self):
        return [q for q in self.g.requests if (q.get("method") if isinstance(q, dict) else q[0]) != "GET"]

    def rows(self):
        return [json.loads(x) for x in self.paths.journal.read_text(encoding="utf-8").splitlines()]

    def test_dry_never_writes(self):
        self.assertEqual(self.run_("dry", armed=runner.TACTICS, ticks=6), 0)
        self.assertEqual(self.writes(), [])
        kinds = [r["kind"] for r in self.rows()]
        self.assertEqual(kinds.count("tick"), 6)
        self.assertNotIn("intent", kinds)

    def test_live_writes_only_armed_green(self):
        self.green()
        self.assertEqual(self.run_("live", armed=("hygiene", "rastro", "closer"), ticks=6), 0)
        rows = self.rows()
        sent = [r for r in rows if r["kind"] == "intent"]
        self.assertTrue(sent)
        self.assertTrue(all(r["tactic"] in ("hygiene", "rastro", "closer") for r in sent))
        self.assertEqual(len(self.writes()), len(sent))
        per_tick = {}
        for r in sent:
            if r["intent_kind"] in ("accept", "duel_accept"):
                per_tick[r["tick"]] = per_tick.get(r["tick"], 0) + 1
        self.assertTrue(all(v <= 1 for v in per_tick.values()))

    def test_live_red_stage_is_not_armed(self):
        self.green(stages=("core",))                         # rastro stage missing -> red
        self.assertEqual(self.run_("live", armed=("rastro",), ticks=3), 0)
        rows = self.rows()
        self.assertTrue(any(r["kind"] == "alarm" and "arm refused" in r.get("why", "") for r in rows))
        self.assertEqual(self.writes(), [])
        self.assertEqual(json.loads(self.paths.armed.read_text(encoding="utf-8")), [])

    def test_code_change_turns_stage_red(self):
        ch = runner.code_hash()
        st = {"core": {"green": True, "code_hash": ch}, "hygiene": {"green": True, "code_hash": "old"}}
        self.assertFalse(runner.tactic_green("hygiene", self.paths, chash=ch, selftest=st))
        st["hygiene"]["code_hash"] = ch
        self.assertTrue(runner.tactic_green("hygiene", self.paths, chash=ch, selftest=st))
        self.assertFalse(runner.tactic_green("nope", self.paths, chash=ch, selftest=st))

    def test_second_runner_exits_3(self):
        with writer_lock(self.paths):
            self.assertEqual(self.run_("dry"), 3)
        self.assertFalse(self.paths.journal.exists())

    def test_stop_file_exits_2_without_writes(self):
        self.green()
        (self.paths.root / "STOP.txt").write_text("manual", encoding="utf-8")
        self.assertEqual(self.run_("live", armed=runner.TACTICS), 2)
        self.assertEqual(self.writes(), [])

    def test_stop_mid_run(self):
        self.green()
        orig = self.clk.sleep
        calls = {"n": 0}

        def sleep(s):
            calls["n"] += 1
            if calls["n"] == 3:
                (self.paths.root / "stop").write_text("x", encoding="utf-8")
            orig(s)
        self.clk.sleep = sleep
        rc = self.run_("live", armed=runner.TACTICS, ticks=50)
        self.assertEqual(rc, 2)
        n = len(self.writes())
        self.assertLess(self.g.tick, 10)
        self.assertEqual(n, len([r for r in self.rows() if r["kind"] == "intent"]))

    def _own_bid(self):
        ref = sorted(r for r in self.g.model.cards if r.startswith("LAV"))[0]
        o = self.g.post_offer(TEAM, {"give": {"cash": 3}, "want": {"cards": [ref]}, "venue": "rastro",
                                     "expires_in_ticks": 200})
        return o.get("id", o.get("offer", {}).get("id") if isinstance(o.get("offer"), dict) else None)

    def test_manual_do_and_stale_inbox(self):
        oid = self._own_bid()
        self.assertIsInstance(oid, int)
        self.paths.inbox.mkdir(parents=True, exist_ok=True)
        (self.paths.inbox / "0-arm.json").write_text(json.dumps({"cmd": "arm", "tactic": "rastro", "why": "old",
                                                                 "ts": time.time() - 3600}), encoding="utf-8")
        self.green(stages=("core",))
        rc = self.run_("live", armed=(), ticks=2,
                       manual=[{"cmd": "do", "kind": "cancel", "args": {"offer_id": oid, "ref": None}, "why": "t",
                                "live": True}])
        self.assertEqual(rc, 0)
        rows = self.rows()
        sent = [r for r in rows if r["kind"] == "intent"]
        self.assertEqual([(r["tactic"], r["intent_kind"], r["args"]["offer_id"]) for r in sent],
                         [("manual", "cancel", oid)])
        self.assertTrue(any(r["kind"] == "cmd" and r.get("applied") is False for r in rows))
        self.assertEqual(json.loads(self.paths.armed.read_text(encoding="utf-8")), [])
        self.assertEqual(list(self.paths.inbox.glob("*.json")), [])

    def test_manual_do_without_live_is_only_would_in_a_live_run(self):
        # the order did not say live (no --live): a live runner must not send it, even with core green / manual armed
        oid = self._own_bid()
        self.green(stages=("core",))
        self.paths.inbox.mkdir(parents=True, exist_ok=True)
        (self.paths.inbox / "5-do.json").write_text(json.dumps({"cmd": "do", "kind": "cancel", "why": "t",
                                                                "args": {"offer_id": oid, "ref": None}, "live": False,
                                                                "ts": time.time() + 3600}), encoding="utf-8")
        self.assertEqual(self.run_("live", armed=("manual",), ticks=2), 0)
        rows = self.rows()
        self.assertEqual(self.writes(), [])
        self.assertEqual([r for r in rows if r["kind"] == "intent"], [])
        self.assertTrue(any(r["kind"] == "would" and r["tactic"] == "manual" for r in rows))

    def test_flatten_cancels_bids_then_stops(self):
        oid = self._own_bid()
        self.green(stages=("core",))
        self.paths.inbox.mkdir(parents=True, exist_ok=True)
        (self.paths.inbox / "9-flatten.json").write_text(json.dumps({"cmd": "flatten", "why": "test",
                                                                     "ts": time.time() + 3600}), encoding="utf-8")
        self.assertEqual(self.run_("live", armed=(), ticks=5), 2)
        self.assertTrue(any(p.name.upper().startswith("STOP") for p in self.paths.root.iterdir()))
        sent = [r for r in self.rows() if r["kind"] == "intent"]
        self.assertEqual([(r["intent_kind"], r["args"]["offer_id"]) for r in sent], [("cancel", oid)])

    def test_flatten_keeps_going_past_one_tick_budget(self):
        # one tick cancels at most min(6, listings - 2); STOP used to come after that first tick with bids left
        oids = [self._own_bid() for _ in range(8)]
        self.green(stages=("core",))
        self.paths.inbox.mkdir(parents=True, exist_ok=True)
        (self.paths.inbox / "9-flatten.json").write_text(json.dumps({"cmd": "flatten", "why": "test",
                                                                     "ts": time.time() + 3600}), encoding="utf-8")
        self.assertEqual(self.run_("live", armed=(), ticks=10), 2)
        sent = [r for r in self.rows() if r["kind"] == "intent"]
        self.assertEqual(sorted(r["args"]["offer_id"] for r in sent), sorted(oids))
        self.assertGreater(len({r["tick"] for r in sent}), 1)
        self.assertEqual([o for o in self.g.offers.values() if o["maker"] == TEAM and o["status"] == "open"], [])

    def test_inbox_pause_applied(self):
        self.paths.inbox.mkdir(parents=True, exist_ok=True)
        (self.paths.inbox / "1-pause.json").write_text(json.dumps({"cmd": "pause", "tactic": "rastro", "why": "p",
                                                                   "ts": time.time() + 3600}), encoding="utf-8")
        self.assertEqual(self.run_("dry", ticks=2), 0)
        self.assertIn("rastro", json.loads(self.paths.pauses.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
