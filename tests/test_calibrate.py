"""M13 calibrate tests (INV-17, harness-spec §7)."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from types import MappingProxyType

from tests import HARVEST
from agent.calibrate import Calibrator, fallback_verdict, points_of
from agent.contracts import BUY_TACTICS, FRIDAY, Paths, Prediction, World

ME = json.loads((HARVEST / "me.json").read_text(encoding="utf-8"))


class FakeJournal:
    """Test double for agent.journal.Journal (M2): write + rows."""

    def __init__(self):
        self.data = []

    def write(self, kind, **fields):
        self.data.append({"seq": len(self.data) + 1, "kind": kind, **json.loads(json.dumps(fields))})
        return len(self.data)

    def rows(self, kinds=None):
        return iter([r for r in self.data if kinds is None or r["kind"] in kinds])

    def of(self, kind):
        return [r for r in self.data if r["kind"] == kind]


def me_with(neg=74.5, ladder=0.051, duel=0.0, cash=260, assets=None):
    me = copy.deepcopy(ME)
    me["cash"] = cash
    me["score"].update({"neg_points": neg, "ladder_points": ladder, "duel_points": duel})
    if assets is not None:
        me["assets"] = assets
    return me


def world(tick, me, *, rnd=1, offers=(), threads=None, duels=(), down=frozenset()):
    return World(tick=tick, t_hours=tick / 60.0, round=rnd, tick_seconds=30.0, tick_deadline=0.0,
                 clock=MappingProxyType({"today": "sat", "round": rnd}), limits=FRIDAY, reading="N", me=me,
                 my_offers=tuple(offers), offers_to_us=(), board=(), own_pseudonym=None,
                 threads=MappingProxyType(threads or {}), foreign_threads=(), duels=tuple(duels),
                 catalog={}, schedule={}, released_sets=frozenset(), feed_new=(), server_values={},
                 down=frozenset(down))


def bid(oid, ref="LAT-10", price=62, status="open", created=145, expires=205):
    return {"id": oid, "maker": "t18", "to": None, "venue": "rastro", "status": status,
            "give": {"cash": price, "assets": [], "types": []},
            "want": {"cash": 0, "assets": [], "types": [f"card:{ref}"]},
            "created_tick": created, "expires_tick": expires}


def sell(oid, ref="MAL-04", asset=900, price=12, status="open", created=170, expires=230):
    return {"id": oid, "maker": "t18", "to": None, "venue": "rastro", "status": status,
            "give": {"cash": 0, "assets": [{"id": asset, "ref": ref}], "types": []},
            "want": {"cash": price, "assets": [], "types": []},
            "created_tick": created, "expires_tick": expires}


def pred(lo, hi=None, ladder="0"):
    return {"neg_lo": lo, "neg_hi": lo if hi is None else hi, "ladder": ladder, "cash": 0, "duel": None,
            "model": "P-03"}


class Base(unittest.TestCase):
    def setUp(self):
        self.paths = Paths.at(tempfile.mkdtemp(prefix="t18-calib-"))
        self.j = FakeJournal()

    def cal(self, **kw):
        kw.setdefault("verdict_fn", fallback_verdict)
        return Calibrator(self.j, self.paths, **kw)

    def harness_list(self, iid, offer_id, lo, tactic="rastro", tick=170, hi=None):
        self.j.write("intent", id=iid, tactic=tactic, intent_kind="list_offer", tick=tick,
                     args={"side": "sell", "ref": "MAL-04", "asset_id": 900, "price": 12, "expires_ticks": 20,
                           "closer": False, "want_ref": None},
                     prediction=pred(lo, hi))
        self.j.write("result", id=iid, status="ok", code=None, response={"offer": {"id": offer_id}})

    def no_pauses(self, c):
        for t in ("hygiene", "dealers", "rastro", "closer", "duels", "manual"):
            self.assertFalse(c.paused(t), t)


class TestINV17(Base):
    def test_inherited_2504_filled_at_t170_is_pass_without_stop(self):
        self.paths.state.mkdir(parents=True, exist_ok=True)
        self.paths.baseline.write_text(json.dumps({"offers": {"2503": 0.0, "2504": 0.0}}), encoding="utf-8")
        c = self.cal()
        prev = world(169, me_with(neg=74.5), offers=[bid(2503, "LAT-09"), bid(2504)])
        c.on_tick(None, prev)
        got = [{"id": 5000, "ref": "LAT-10"}] + ME["assets"]
        now = world(170, me_with(neg=75.6, cash=198, assets=got),
                    offers=[bid(2503, "LAT-09"), bid(2504, status="settled")])
        ev = c.on_tick(prev, now)
        m = self.j.of("measure")
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["verdict"], "pass")
        self.assertEqual(m[0]["ids"], ["baseline:2504"])
        self.assertEqual(c.stop_reasons(), [])
        self.assertFalse(any(e["kind"] in ("stop", "pause") for e in ev))
        self.no_pauses(c)

    def test_round_change_reset_gives_no_pause(self):
        c = self.cal()
        prev = world(200, me_with(neg=74.5), rnd=1)
        c.on_tick(None, prev)
        now = world(201, me_with(neg=0.0), rnd=2)
        ev = c.on_tick(prev, now)
        self.assertEqual(len(self.j.of("round_reset")), 1)
        rr = self.j.of("round_reset")[0]
        self.assertEqual((rr["from_round"], rr["to_round"]), (1, 2))
        self.assertEqual(rr["before"]["neg_points"], 74.5)
        self.assertEqual(c.stop_reasons(), [])
        self.assertFalse(any(e["kind"] == "pause" for e in ev))
        self.no_pauses(c)
        # new base: a quiet next tick at 0 changes nothing
        c.on_tick(now, world(202, me_with(neg=0.0), rnd=2))
        self.no_pauses(c)

    def test_same_drop_mid_round_pauses_buys_persistently(self):
        c = self.cal()
        prev = world(200, me_with(neg=74.5), rnd=1)
        c.on_tick(None, prev)
        c.on_tick(prev, world(201, me_with(neg=0.0), rnd=1))
        for t in BUY_TACTICS:
            self.assertTrue(c.paused(t), t)
        self.assertEqual(self.j.of("round_reset"), [])
        # persistent: a new calibrator (restart) still sees the pauses
        c2 = self.cal()
        for t in BUY_TACTICS:
            self.assertTrue(c2.paused(t), t)
        self.assertFalse(c2.paused("hygiene"))

    def test_all_points_drop_without_settlement_is_reset(self):
        c = self.cal()
        prev = world(200, me_with(neg=74.5, ladder=0.051), rnd=None)
        c.on_tick(None, prev)
        c.on_tick(prev, world(201, me_with(neg=0.0, ladder=0.0), rnd=None))
        self.assertEqual(len(self.j.of("round_reset")), 1)
        self.no_pauses(c)

    def test_window_crossing_round_change_is_excluded(self):
        self.harness_list("i1", 3000, lo=3.0)
        c = self.cal()
        prev = world(200, me_with(neg=74.5), offers=[sell(3000)])
        c.on_tick(None, prev)
        mid = world(201, me_with(neg=74.5, cash=272, assets=ME["assets"][1:]),
                    offers=[sell(3000, status="settled")])
        c.on_tick(prev, mid)                      # settlement, no change yet: window open
        self.assertEqual(self.j.of("measure"), [])
        c.on_tick(mid, world(202, me_with(neg=0.0, cash=272, assets=ME["assets"][1:]), rnd=2))
        m = self.j.of("measure")
        self.assertEqual([x["verdict"] for x in m], ["excluded"])
        self.no_pauses(c)
        self.assertEqual(c.stop_reasons(), [])


class TestHarnessSettlements(Base):
    def _settle(self, c, tick, oid, neg0, neg1, cash1=272):
        prev = world(tick, me_with(neg=neg0), offers=[sell(oid)])
        c.on_tick(None, prev) if c._base is None else None
        now = world(tick + 1, me_with(neg=neg1, cash=cash1, assets=ME["assets"][1:]),
                    offers=[sell(oid, status="settled")])
        return c.on_tick(prev, now)

    def test_pass(self):
        self.harness_list("i1", 3000, lo=3.0, hi=3.5)
        c = self.cal()
        self._settle(c, 200, 3000, 74.5, 77.7)
        m = self.j.of("measure")[0]
        self.assertEqual((m["verdict"], m["ids"], m["tactics"]), ("pass", ["i1"], ["rastro"]))
        self.no_pauses(c)

    def test_hard_fail_pauses_and_stops(self):
        self.harness_list("i1", 3000, lo=3.0)
        c = self.cal()
        ev = self._settle(c, 200, 3000, 74.5, 70.0)
        self.assertEqual(self.j.of("measure")[0]["verdict"], "hard_fail")
        self.assertTrue(c.paused("rastro"))
        self.assertTrue(any(r.startswith("calib:harness_settlement_out_of_band") for r in c.stop_reasons()))
        self.assertTrue(any(e["kind"] == "stop" for e in ev))
        saved = json.loads(self.paths.pauses.read_text(encoding="utf-8"))
        self.assertIn("rastro", saved)

    def test_two_soft_fails_in_five_pause(self):
        self.harness_list("i1", 3000, lo=3.0)
        self.harness_list("i2", 3001, lo=3.0)
        c = self.cal()
        self._settle(c, 200, 3000, 74.5, 76.5)        # +2 vs +3 -> soft
        self.assertFalse(c.paused("rastro"))
        self._settle(c, 210, 3001, 76.5, 78.5)
        self.assertEqual([m["verdict"] for m in self.j.of("measure")], ["soft_fail", "soft_fail"])
        self.assertTrue(c.paused("rastro"))
        self.assertEqual(c.stop_reasons(), [])

    def test_window_waits_then_measures_zero(self):
        self.harness_list("i1", 3000, lo=3.0)
        c = self.cal()
        prev = world(200, me_with(neg=74.5), offers=[sell(3000)])
        c.on_tick(None, prev)
        w = world(201, me_with(neg=74.5, cash=272), offers=[sell(3000, status="settled")])
        c.on_tick(prev, w)
        for t in (202, 203):
            nxt = world(t, me_with(neg=74.5, cash=272), offers=[sell(3000, status="settled")])
            c.on_tick(w, nxt)
            w = nxt
        self.assertEqual(self.j.of("measure"), [])
        c.on_tick(w, world(204, me_with(neg=74.5, cash=272), offers=[sell(3000, status="settled")]))
        m = self.j.of("measure")
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["meas"]["neg"], 0.0)

    def test_window_measures_first_change(self):
        self.harness_list("i1", 3000, lo=3.0)
        c = self.cal()
        prev = world(200, me_with(neg=74.5), offers=[sell(3000)])
        c.on_tick(None, prev)
        w = world(201, me_with(neg=74.5, cash=272), offers=[sell(3000, status="settled")])
        c.on_tick(prev, w)
        c.on_tick(w, world(202, me_with(neg=77.5, cash=272), offers=[sell(3000, status="settled")]))
        m = self.j.of("measure")
        self.assertEqual((m[0]["verdict"], m[0]["meas"]["neg"]), ("pass", 3.0))

    def test_inherited_out_of_band_alarms_without_stop(self):
        c = self.cal(baseline={"offers": {"2504": 0.0}})
        prev = world(169, me_with(neg=74.5), offers=[bid(2504)])
        c.on_tick(None, prev)
        c.on_tick(prev, world(170, me_with(neg=72.0, cash=198), offers=[bid(2504, status="settled")]))
        self.assertEqual(self.j.of("measure")[0]["verdict"], "out_of_band")
        self.assertTrue(any(a["what"] == "inherited_out_of_band" for a in self.j.of("alarm")))
        self.assertEqual(c.stop_reasons(), [])

    def test_ladder_down_pauses_dealers(self):
        c = self.cal()
        prev = world(200, me_with(neg=74.5, ladder=0.051))
        c.on_tick(None, prev)
        c.on_tick(prev, world(201, me_with(neg=74.5, ladder=0.02)))
        self.assertTrue(c.paused("dealers"))
        self.assertFalse(c.paused("rastro"))

    def test_daily_negative_surprise_stop(self):
        for i in range(3):
            self.harness_list(f"i{i}", 3000 + i, lo=30.0)
        c = self.cal(verdict_fn=lambda p, n, l: "pass")   # verdicts aside, surprises accumulate
        neg = 74.5
        for i in range(3):
            self._settle(c, 200 + 10 * i, 3000 + i, neg, neg + 1.0)   # surprise -29 each (-87 < -60)
            neg += 1.0
        self.assertTrue(any(r.startswith("calib:daily_negative_surprise") for r in c.stop_reasons()))

    def test_neg_cap_confirmed_param(self):
        self.harness_list("i1", 3000, lo=50.0, hi=60.6)
        c = self.cal()
        self._settle(c, 200, 3000, 74.5, 124.5)
        self.assertTrue(any(r.get("name") == "NEG_CAP_CONFIRMED" for r in self.j.of("param")))

    def test_dealer_thread_deal_attributed(self):
        self.j.write("intent", id="d1", tactic="dealers", tick=200,
                     args={"thread_id": 77, "ref": "RET-02", "price": 8, "template": "t", "variant": 0},
                     prediction=pred(0.0, 0.0, ">=0"))
        self.j.write("result", id="d1", status="ok", code=None, response={})
        c = self.cal()
        prev = world(200, me_with(neg=74.5, ladder=0.051), threads={77: {"id": 77, "with": "abuela",
                                                                        "status": "open"}})
        c.on_tick(None, prev)
        c.on_tick(prev, world(201, me_with(neg=74.5, ladder=0.08, cash=252),
                              threads={77: {"id": 77, "with": "abuela", "status": "deal"}}))
        m = self.j.of("measure")[0]
        self.assertEqual((m["verdict"], m["ids"], m["dealers"]), ("pass", ["d1"], ["abuela"]))
        self.no_pauses(c)


class TestFailClosedAndApi(Base):
    def test_me_down_does_nothing(self):
        c = self.cal()
        prev = world(200, me_with(neg=74.5))
        c.on_tick(None, prev)
        self.assertEqual(c.on_tick(prev, world(201, me_with(neg=0.0), down={"me"})), [])
        self.no_pauses(c)
        self.assertEqual(self.j.data, [])

    def test_broken_pauses_json_fails_closed(self):
        self.paths.state.mkdir(parents=True, exist_ok=True)
        self.paths.pauses.write_text("{broken", encoding="utf-8")
        c = self.cal()
        for t in BUY_TACTICS | {"duels"}:
            self.assertTrue(c.paused(t))
        self.assertFalse(c.paused("hygiene"))
        self.assertEqual(self.j.of("alarm")[0]["what"], "pauses_unreadable")

    def test_pause_resume_persist_and_journal(self):
        c = self.cal()
        c.pause("duels", "manual test", 5)
        self.assertTrue(self.cal().paused("duels"))
        c.resume("duels", "ok again")
        self.assertFalse(self.cal().paused("duels"))
        self.assertEqual([r["kind"] for r in self.j.data if r["kind"] in ("pause", "resume")],
                         ["pause", "resume"])

    def test_verdict_exception_is_hard(self):
        self.harness_list("i1", 3000, lo=3.0)

        def boom(*a):
            raise RuntimeError("x")
        c = self.cal(verdict_fn=boom)
        prev = world(200, me_with(neg=74.5), offers=[sell(3000)])
        c.on_tick(None, prev)
        c.on_tick(prev, world(201, me_with(neg=77.5, cash=272), offers=[sell(3000, status="settled")]))
        self.assertEqual(self.j.of("measure")[0]["verdict"], "hard_fail")
        self.assertTrue(c.paused("rastro"))

    def test_report_and_points(self):
        self.assertEqual(points_of(ME)["neg_points"], 74.5)
        self.assertIsNone(points_of({"score": {}}))
        c = self.cal()
        prev = world(200, me_with(neg=74.5), rnd=1)
        c.on_tick(None, prev)
        c.on_tick(prev, world(201, me_with(neg=0.0), rnd=2))
        rep = c.report()
        self.assertIn("round_resets: 1", rep)
        self.assertIn("stop reasons: none", rep)

    def test_fallback_verdict(self):
        P = Prediction
        self.assertEqual(fallback_verdict(P(3, 4, "0", 0), 3.5, 0.0), "pass")
        self.assertEqual(fallback_verdict(P(3, 4, "0", 0), 2.0, 0.0), "soft_fail")
        self.assertEqual(fallback_verdict(P(3, 4, "0", 0), -1.5, 0.0), "hard_fail")
        self.assertEqual(fallback_verdict(P(3, 4, "0", 0), 9.0, 0.0), "surprise_up")
        self.assertEqual(fallback_verdict(P(3, 4, ">=0", 0), 3.0, -0.01), "hard_fail")


def swap(oid, give_ref="MAL-04", asset=900, want_ref="LAT-09", status="open", created=170, expires=230):
    return {"id": oid, "maker": "t18", "to": None, "venue": "rastro", "status": status,
            "give": {"cash": 0, "assets": [{"id": asset, "ref": give_ref}], "types": []},
            "want": {"assets": [], "types": [f"card:{want_ref}"]},
            "created_tick": created, "expires_tick": expires}


class TestLateInputs(Base):
    def test_swap_settlement_matched_by_shape_without_offer_id(self):
        # D1: swap published as maker; the result carries no offer id -> shape match (price None == 0)
        self.j.write("intent", id="s1", tactic="rastro", intent_kind="list_offer", tick=170,
                     args={"side": "swap", "ref": "MAL-04", "asset_id": 900, "price": 0, "expires_ticks": 20,
                           "closer": False, "want_ref": "LAT-09"},
                     prediction=pred(4.0, 6.0))
        self.j.write("result", id="s1", status="ok", code=None, response={})
        c = self.cal()
        prev = world(200, me_with(neg=74.5), offers=[swap(3100)])
        c.on_tick(None, prev)
        assets = [{"id": 901, "ref": "LAT-09"}] + list(ME["assets"][1:])
        c.on_tick(prev, world(201, me_with(neg=79.5, cash=260, assets=assets),
                              offers=[swap(3100, status="settled")]))
        m = self.j.of("measure")[0]
        self.assertEqual((m["verdict"], m["ids"], m["tactics"]), ("pass", ["s1"], ["rastro"]))
        self.no_pauses(c)
        self.assertEqual(c.stop_reasons(), [])

    def test_accept_on_rival_venue_measured_and_hard_fail_pauses(self):
        # D2: accept on another team's venue; asset/cash change within the accepted_unsettled window
        args = {"offer_id": 4000, "source": "team", "ref": "LAT-10", "side": "buy", "price": 40,
                "thread_id": None, "give_asset": None, "fingerprint": "f", "resupply": False, "venue": "t07"}
        self.j.write("intent", id="a1", tactic="closer", intent_kind="accept", tick=200, args=args,
                     prediction=pred(12.0, 14.0))
        self.j.write("result", id="a1", status="ok", code=None, response={})
        self.j.write("accepted_unsettled", id="a1", offer_id=4000, ref="LAT-10", price=40, until_tick=202)
        c = self.cal()
        prev = world(200, me_with(neg=74.5))
        c.on_tick(None, prev)
        c.on_tick(prev, world(201, me_with(neg=72.0, cash=220)))
        m = self.j.of("measure")[0]
        self.assertEqual((m["verdict"], m["ids"], m["kinds"]), ("hard_fail", ["a1"], ["accept"]))
        self.assertTrue(c.paused("closer"))
        self.assertTrue(c.stop_reasons())

    def test_late_accept_change_is_not_attributed(self):
        args = {"offer_id": 4000, "source": "team", "ref": "LAT-10", "side": "buy", "price": 40,
                "thread_id": None, "give_asset": None, "fingerprint": "f", "resupply": False, "venue": "rastro"}
        self.j.write("intent", id="a1", tactic="closer", intent_kind="accept", tick=100, args=args,
                     prediction=pred(12.0, 14.0))
        self.j.write("result", id="a1", status="ok", code=None, response={})
        self.j.write("accepted_unsettled", id="a1", offer_id=4000, ref="LAT-10", price=40, until_tick=102)
        c = self.cal()
        prev = world(200, me_with(neg=74.5))
        c.on_tick(None, prev)
        c.on_tick(prev, world(201, me_with(neg=74.5, cash=250)))
        self.assertEqual(self.j.of("measure"), [])
        self.no_pauses(c)


class TestRealJournal(Base):
    def test_round_reset_and_mid_round_drop_with_m2_journal(self):
        import os
        from agent.journal import Journal
        self.paths.state.mkdir(parents=True, exist_ok=True)
        (self.paths.state / "writer.lock").write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        j = Journal(self.paths.journal, mode="test", lock_path=self.paths.state / "writer.lock")
        c = Calibrator(j, self.paths, verdict_fn=fallback_verdict)
        prev = world(200, me_with(neg=74.5), rnd=1)
        c.on_tick(None, prev)
        c.on_tick(prev, world(201, me_with(neg=0.0, ladder=0.0), rnd=2))
        self.no_pauses(c)
        self.assertEqual(len(list(j.rows({"round_reset"}))), 1)
        p2 = world(201, me_with(neg=74.5), rnd=2)
        c2 = Calibrator(j, self.paths, verdict_fn=fallback_verdict)
        c2.on_tick(None, p2)
        c2.on_tick(p2, world(202, me_with(neg=0.0), rnd=2))
        self.assertTrue(c2.paused("rastro"))
        self.assertTrue(Calibrator(j, self.paths, verdict_fn=fallback_verdict).paused("rastro"))


if __name__ == "__main__":
    unittest.main()
