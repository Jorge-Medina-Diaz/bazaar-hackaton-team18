"""M8 pages: Needs, frozen closer, protect_sets, plan.json (docs/harness-spec.md §10: test_pages.py)."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from tests import HARVEST
from agent.contracts import FRIDAY, World, Need
from agent.tactics import pages
from agent.valuation import Valuer

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "tests" / "fixtures" / "plan_night.json"   # frozen: config/plan.json changes during the game


def _load(name):
    with open(HARVEST / name, encoding="utf-8") as fh:
        return json.load(fh)


def _catalog(released=("LAV", "MAL", "LAT", "SAL", "RET")):
    cat = copy.deepcopy(_load("catalog.json"))
    for s in cat["sets"]:
        s["released"] = s["id"] in released
    return cat


def make_world(*, released=("LAV", "MAL", "LAT", "SAL", "RET"), add_refs=(), my_offers=None, board=None,
               tick=200, t_hours=6.0, today="sat", down=(), threads=None, feed=(), boards=None):
    me = copy.deepcopy(_load("me.json"))
    nid = 9000
    for ref in add_refs:
        nid += 1
        me["assets"].append({"id": nid, "kind": "card", "ref": ref, "set": ref[:3], "rarity": "common"})
    offers = _load("me_offers.json")["offers"] if my_offers is None else my_offers
    brd = tuple(_load("rastro_offers.json")["offers"]) if board is None else tuple(board)
    cat = _catalog(released)
    return World(tick=tick, t_hours=t_hours, round=2, tick_seconds=30.0, tick_deadline=0.0,
                 clock={"today": today}, limits=FRIDAY, reading="N", me=me, my_offers=tuple(offers),
                 offers_to_us=(), board=brd, own_pseudonym="mcd38ffd5", threads=threads or {},
                 foreign_threads=(), duels=(), catalog=cat, schedule={}, released_sets=frozenset(released),
                 feed_new=tuple(feed), server_values={}, down=frozenset(down),
                 boards=MappingProxyType(boards if boards is not None else {"rastro": brd}))


def valuer_for(world):
    return Valuer(world.catalog, world.me["affinity"], world.released_sets)


class PlanFileTest(unittest.TestCase):
    def test_load_real_plan(self):
        cfg = pages.load_plan(PLAN)
        self.assertEqual(cfg["page_sets"], ["RET"])
        self.assertEqual(cfg["closer"]["default_minus"], 50)
        self.assertEqual(cfg["baseline_bands"], {"2503": 0.0, "2504": 0.0})
        self.assertNotIn("_notes", cfg)
        for k in ("startup_cancels", "protect_sets", "grant_lookahead_ticks", "day_end_hours", "days_sign",
                  "dup_min_price", "resupply_min", "profiles", "dealer_max"):
            self.assertIn(k, cfg)
        self.assertIsNone(cfg["days_sign"])
        self.assertTrue({2463, 1652} <= set(cfg["startup_cancels"]))

    def _bad(self, mutate):
        raw = json.loads(PLAN.read_text(encoding="utf-8"))
        mutate(raw)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "plan.json"
            p.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ValueError):
                pages.load_plan(p)

    def test_load_rejects_malformed(self):
        self._bad(lambda r: r.pop("page_sets"))
        self._bad(lambda r: r.__setitem__("startup_cancels", ["2463"]))
        self._bad(lambda r: r["closer"].__setitem__("compete_minus", 10))      # below accept_min
        self._bad(lambda r: r["profiles"]["RET:rare"].__setitem__("dealer", "t05"))
        self._bad(lambda r: r["profiles"]["RET:rare"].__setitem__("anchor", 95))  # anchor above limit
        self._bad(lambda r: r.__setitem__("days_sign", 2))


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.cfg = pages.load_plan(PLAN)

    def test_ret_published_9_dealer_needs_and_1_closer(self):
        w = make_world()
        needs, frozen = pages.plan(w, valuer_for(w), self.cfg, {})
        self.assertTrue(all(isinstance(n, Need) for n in needs))
        dealer = [n for n in needs if not n.closer]
        closer = [n for n in needs if n.closer]
        self.assertEqual(len(dealer), 9)
        self.assertEqual(len(closer), 1)
        self.assertEqual(closer[0].source, "team")
        self.assertEqual(closer[0].ref, "RET-01")        # common, no rival bids, lowest number
        self.assertEqual(closer[0].max_price, 49)        # floor(99.1 - 50)
        self.assertNotIn(closer[0].ref, {n.ref for n in dealer})
        self.assertEqual(frozen, {})                     # 0/10: not frozen yet
        by = {n.ref: n for n in dealer}
        self.assertEqual((by["RET-09"].source, by["RET-09"].max_price), ("chato", 90))
        self.assertEqual((by["RET-08"].source, by["RET-08"].max_price), ("chato", 31))
        self.assertEqual((by["RET-06"].source, by["RET-06"].max_price), ("abuela", 25))
        self.assertEqual((by["RET-02"].source, by["RET-02"].max_price), ("abuela", 11))
        self.assertEqual([n.ref for n in dealer][:2], ["RET-09", "RET-10"])   # rare first

    def test_closer_frozen_at_8_of_10_and_kept(self):
        w = make_world(add_refs=["RET-02", "RET-03", "RET-04", "RET-05", "RET-06", "RET-07", "RET-08", "RET-09"])
        v = valuer_for(w)
        needs, frozen = pages.plan(w, v, self.cfg, {})
        self.assertEqual(frozen, {"RET": "RET-01"})
        self.assertEqual([(n.ref, n.closer) for n in needs], [("RET-10", False), ("RET-01", True)])
        # next tick a rival bids for RET-01: the frozen closer does not move
        bid = {"id": 7001, "maker": "mzz", "status": "open", "venue": "rastro",
               "give": {"cash": 60, "assets": [], "types": []}, "want": {"cash": 0, "assets": [], "types": ["card:RET-01"]}}
        w2 = make_world(add_refs=["RET-02", "RET-03", "RET-04", "RET-05", "RET-06", "RET-07", "RET-08", "RET-09"],
                        board=[bid])
        needs2, frozen2 = pages.plan(w2, v, self.cfg, frozen)
        self.assertEqual(frozen2, {"RET": "RET-01"})
        cl = [n for n in needs2 if n.closer][0]
        self.assertEqual(cl.max_price, 79)               # rival bid >= our cap: compete_minus

    def test_before_8_closer_avoids_rival_bid(self):
        bid = {"id": 7001, "maker": "mzz", "status": "open", "venue": "rastro",
               "give": {"cash": 40, "assets": [], "types": []}, "want": {"cash": 0, "assets": [], "types": ["card:RET-01"]}}
        w = make_world(board=[bid])
        needs, frozen = pages.plan(w, valuer_for(w), self.cfg, {})
        self.assertEqual([n.ref for n in needs if n.closer], ["RET-02"])
        self.assertEqual(frozen, {})

    def test_frozen_closer_acquired_refreezes(self):
        refs = ["RET-01", "RET-02", "RET-03", "RET-04", "RET-05", "RET-06", "RET-07", "RET-08"]
        w = make_world(add_refs=refs)                    # the frozen RET-01 arrived (pack, gift)
        needs, frozen = pages.plan(w, valuer_for(w), self.cfg, {"RET": "RET-01"})
        self.assertEqual(frozen["RET"], [n.ref for n in needs if n.closer][0])
        self.assertIn(frozen["RET"], {"RET-09", "RET-10"})
        self.assertEqual(len([n for n in needs if not n.closer]), 1)

    def test_page_complete_no_needs(self):
        refs = [f"RET-{i:02d}" for i in range(1, 11)]
        w = make_world(add_refs=refs)
        needs, frozen = pages.plan(w, valuer_for(w), self.cfg, {"RET": "RET-01", "LAT": "LAT-09"})
        self.assertEqual(needs, [])
        self.assertEqual(frozen, {"LAT": "LAT-09"})      # other sets pass through

    def test_sunday_add_cha_is_enough(self):
        cfg = dict(self.cfg)
        cfg["page_sets"] = ["RET", "CHA"]
        w = make_world(released=("LAV", "MAL", "LAT", "SAL", "RET", "CHA"), t_hours=19.0, today="sun")
        needs, _ = pages.plan(w, valuer_for(w), cfg, {})
        cha = [n for n in needs if n.set == "CHA"]
        self.assertEqual(len([n for n in cha if not n.closer]), 9)
        cl = [n for n in cha if n.closer]
        self.assertEqual(len(cl), 1)
        self.assertEqual(cl[0].max_price, 72)            # floor(122 - 50)
        self.assertEqual({n.max_price for n in cha if n.ref in ("CHA-09", "CHA-10")}, {100})

    def test_unreleased_set_no_needs(self):
        w = make_world(released=("LAV", "MAL", "LAT", "SAL"))
        self.assertEqual(pages.plan(w, valuer_for(w), self.cfg, {})[0], [])

    def test_endgame_raises_closer_cap(self):
        cfg = dict(self.cfg)
        cfg["page_sets"] = ["CHA"]
        w = make_world(released=("LAV", "MAL", "LAT", "SAL", "RET", "CHA"), t_hours=21.5, today="sun")
        needs, _ = pages.plan(w, valuer_for(w), cfg, {})
        self.assertEqual([n.max_price for n in needs if n.closer], [102])   # floor(122 - 20)

    def test_extra_need_from_profile_dealer(self):
        # Sat: a non-page card (here RET-09 stands in for the SAL-11 epic) bought from its profile dealer, capped
        cfg = copy.deepcopy(self.cfg)
        cfg["profiles"]["RET-09"] = {"dealer": "picaros", "anchor": 30, "step": 3, "limit": 160, "fallback_after": 20}
        cfg["page_sets"] = []
        cfg["extra_needs"] = [{"ref": "RET-09", "max_price": 40}]
        w = make_world()
        needs, _ = pages.plan(w, valuer_for(w), cfg, {})
        self.assertEqual([(n.ref, n.source, n.max_price, n.closer) for n in needs], [("RET-09", "picaros", 40, False)])
        held = make_world(add_refs=["RET-09"])
        self.assertEqual(pages.plan(held, valuer_for(held), cfg, {})[0], [])          # held -> no Need
        late = make_world(t_hours=17.95, today="sat")
        self.assertEqual(pages.plan(late, valuer_for(late), cfg, {})[0], [])         # day end -> no dealer Need

    def test_day_end_drops_dealer_needs(self):
        w = make_world(t_hours=17.95, today="sat")
        needs, _ = pages.plan(w, valuer_for(w), self.cfg, {})
        self.assertEqual([n.closer for n in needs], [True])

    def test_fail_closed(self):
        w = make_world(down=("me",))
        self.assertEqual(pages.plan(w, valuer_for(w), self.cfg, {"RET": "RET-03"}), ([], {"RET": "RET-03"}))

        class Broken:
            @staticmethod
            def holdings(me):
                return Valuer.holdings(me)

            def delta_add(self, *a, **k):
                raise RuntimeError("valuation down")
        w = make_world()
        self.assertEqual(pages.plan(w, Broken(), self.cfg, {})[0], [])

    def test_rival_bid_on_other_venue_counts(self):
        """D2: boards of every venue are read; a rival bid on another team's venue also moves the closer."""
        bid = {"id": 7002, "maker": "t05", "status": "open", "venue": "t05_shop",
               "give": {"cash": 40, "assets": [], "types": []}, "want": {"cash": 0, "assets": [], "types": ["card:RET-01"]}}
        w = make_world(board=[], boards={"rastro": (), "t05_shop": (bid,)})
        needs, _ = pages.plan(w, valuer_for(w), self.cfg, {})
        self.assertEqual([n.ref for n in needs if n.closer], ["RET-02"])

    def test_startup_cancels_only_if_open_in_fixtures(self):
        open_ids = {o["id"] for o in _load("me_offers.json")["offers"] if o.get("status") == "open"}
        self.assertTrue(set(self.cfg["startup_cancels"]) <= open_ids)

    def test_never_lowers_standing_bid(self):
        refs = ["RET-02", "RET-03", "RET-04", "RET-05", "RET-06", "RET-07", "RET-08", "RET-09", "RET-10"]
        bid = {"id": 8001, "maker": "t18", "status": "open", "venue": "rastro",
               "give": {"cash": 79, "assets": [], "types": []}, "want": {"cash": 0, "assets": [], "types": ["card:RET-01"]}}
        w = make_world(add_refs=refs, my_offers=[bid], board=[])
        needs, frozen = pages.plan(w, valuer_for(w), self.cfg, {"RET": "RET-01"})
        self.assertEqual([(n.ref, n.max_price) for n in needs], [("RET-01", 79)])
        self.assertEqual(frozen, {"RET": "RET-01"})


class ProtectTest(unittest.TestCase):
    def setUp(self):
        self.cfg = pages.load_plan(PLAN)

    def test_lat_protected_before_205(self):
        w = make_world(tick=180)
        self.assertEqual(pages.protect_sets(w, self.cfg, None), frozenset({"SAL", "RET", "CHA", "LAT"}))

    def test_lat_given_up_at_205(self):
        w = make_world(tick=205, my_offers=[])
        self.assertEqual(pages.protect_sets(w, self.cfg, None), frozenset({"SAL", "RET", "CHA"}))

    def test_lat_alive_if_bid_filled_or_held(self):
        w = make_world(tick=210, my_offers=[])
        self.assertIn("LAT", pages.protect_sets(w, self.cfg, {"filled_offers": [2503]}))
        self.assertIn("LAT", pages.protect_sets(w, self.cfg, {"pending_in": {"LAT-10": 1}}))
        w2 = make_world(tick=210, my_offers=[], add_refs=["LAT-09"])
        self.assertIn("LAT", pages.protect_sets(w2, self.cfg, None))

    def test_lat_kept_when_unknown(self):
        w = make_world(tick=300, my_offers=[], down=("me",))
        self.assertIn("LAT", pages.protect_sets(w, self.cfg, None))

    def test_page_sets_always_protected(self):
        cfg = dict(self.cfg)
        cfg["protect_sets"] = ["SAL"]
        self.assertEqual(pages.protect_sets(make_world(), cfg, None), frozenset({"SAL", "RET"}))

    def test_spare_assets_keep_last_protected_copy(self):
        w = make_world(my_offers=[])
        spares = pages.spare_assets(w, {"SAL", "RET", "CHA", "LAT"})
        refs = [r for _, r in spares]
        self.assertFalse(any(r.startswith("SAL") for r in refs))      # single copies of SAL stay
        self.assertEqual(refs.count("LAT-01"), 1)                     # LAT-01 x2: one spare
        self.assertIn("LAV-03", refs)                                 # unprotected set
        listed = make_world()                                         # harvest: LAV-03 listed in 2460
        self.assertNotIn("LAV-03", [r for _, r in pages.spare_assets(listed, {"SAL", "LAT"})])


def _sun(t, close, stalls=None, *, doors="open", paused=False, today="sun", upcoming=None):
    """A Sunday World for the live-schedule day end: today's day_closes at `close`, stalls closing at `stalls`."""
    up = [] if upcoming is None else list(upcoming)
    if upcoming is None:
        up.append({"at_hours": close + 0.0, "action": "day_closes", "params": {"day": "sun"},
                   "wall": "2026-10-04T15:00:00+02:00"})
        if stalls is not None:
            up += [{"at_hours": stalls, "action": "persona", "params": {"id": p, "enabled": False}}
                   for p in ("abuela", "chato", "pilar", "picaros", "banco")]
    w = make_world(t_hours=t, today=today)
    import dataclasses
    return dataclasses.replace(w, clock={"today": today, "doors": doors, "paused": paused},
                               schedule={"now_hours": t, "upcoming": up})


class LiveDayEndTest(unittest.TestCase):
    """Night audit (Sun 4 Oct): day end / endgame follow the live schedule, not plan hours (sun 19.283 / 18.783)."""
    PLAN = {"day_end_hours": {"sun": 19.283}, "closer": {"endgame_hours": {"sun": 18.783, "N": 18.783, "*": 18.783}}}

    def eff(self, w, seen=None):
        return pages.effective_plan(self.PLAN, w, seen)

    def test_resume_at_13_367(self):
        # no jump: Sunday 09:00-15:00 = t 13.367-19.367; the re-based stalls close one hour earlier (18.367)
        pc, _ = self.eff(_sun(13.4, 19.367))
        self.assertAlmostEqual(pc["day_end_hours"]["sun"], 19.367 - 5 / 60, places=3)
        self.assertAlmostEqual(pc["closer"]["endgame_hours"]["N"], 19.367 - 35 / 60, places=3)
        pc, _ = self.eff(_sun(13.4, 19.367, 18.367))
        self.assertAlmostEqual(pc["day_end_hours"]["sun"], 18.267, places=3)       # stalls - 6 min
        self.assertAlmostEqual(pc["closer"]["endgame_hours"]["sun"], 18.7837, places=3)
        self.assertFalse(pages.past_day_end(_sun(18.2, 19.367, 18.367), pc))
        self.assertTrue(pages.past_day_end(_sun(18.27, 19.367, 18.367), pc))

    def test_clock_jump_to_16_65(self):
        # jump: CHA + round 3 at 09:00, stalls 21.65, close 22.65; the plan hours would fire at 09:00
        w = _sun(19.5, 22.65, 21.65)                                              # ~11:50 after a jump
        self.assertTrue(pages.past_day_end(w, self.PLAN))                         # the bug this fixes
        pc, _ = self.eff(w)
        self.assertFalse(pages.past_day_end(w, pc))
        self.assertFalse(pages.endgame(w, pc))
        self.assertAlmostEqual(pc["day_end_hours"]["sun"], 21.55, places=3)
        self.assertTrue(pages.endgame(_sun(22.07, 22.65), self.eff(_sun(22.07, 22.65))[0]))

    def test_a_pause_moves_the_triggers(self):
        # the server re-projects day_closes after a pause (Sat: 14.086 -> 13.367): the triggers follow
        late = self.eff(_sun(17.0, 19.367))[0]
        early = self.eff(_sun(17.0, 18.9))[0]
        self.assertLess(early["closer"]["endgame_hours"]["sun"], late["closer"]["endgame_hours"]["sun"])
        self.assertTrue(pages.endgame(_sun(18.4, 18.9), early))
        self.assertFalse(pages.endgame(_sun(18.4, 19.367), late))

    def test_stalls_hour_is_kept_after_the_entries_fire(self):
        _, seen = self.eff(_sun(18.0, 19.367, 18.367))
        pc, seen = self.eff(_sun(18.4, 19.367), seen)                             # persona entries gone
        self.assertAlmostEqual(pc["day_end_hours"]["sun"], 18.267, places=3)
        self.assertTrue(pages.past_day_end(_sun(18.4, 19.367), pc))

    def test_one_dealer_off_is_not_the_stalls_closing(self):
        up = [{"at_hours": 19.367, "action": "day_closes", "params": {"day": "sun"}},
              {"at_hours": 15.0, "action": "persona", "params": {"id": "pilar", "enabled": False}}]
        pc, _ = self.eff(_sun(14.0, 0, upcoming=up))
        self.assertAlmostEqual(pc["day_end_hours"]["sun"], 19.367 - 5 / 60, places=3)

    def test_no_live_schedule(self):
        # cold start (schedule unread) or paused with nothing seen: no trigger at all (never the stale plan hour)
        cold = _sun(20.0, 0, upcoming=[])
        pc, _ = self.eff(cold)
        self.assertFalse(pages.past_day_end(cold, pc))
        self.assertFalse(pages.endgame(cold, pc))
        # paused after a live read: the last live close stays
        _, seen = self.eff(_sun(17.0, 19.367))
        paused = _sun(17.0, 22.65, paused=True)
        pc, _ = self.eff(paused, seen)
        self.assertAlmostEqual(pc["day_end_hours"]["sun"], 19.367 - 5 / 60, places=3)
        # schedule read but no close entry: the plan's hours
        pc, _ = self.eff(_sun(14.0, 0, upcoming=[{"at_hours": 15.0, "action": "bench", "params": {}}]))
        self.assertEqual(pc["day_end_hours"]["sun"], 19.283)

    def test_stale_today_uses_the_next_close(self):
        up = [{"at_hours": 19.367, "action": "day_closes", "params": {"day": "sun"}}]
        w = _sun(13.4, 0, today="sat", upcoming=up)
        pc, _ = self.eff(w)
        self.assertAlmostEqual(pc["day_end_hours"]["sat"], 19.367 - 5 / 60, places=3)
        self.assertFalse(pages.past_day_end(w, pc))

    def test_today_missing_is_not_guessed(self):
        import dataclasses
        w = dataclasses.replace(make_world(t_hours=15.0), clock={})
        self.assertEqual(pages.today(w), "default")
        self.assertFalse(pages.past_day_end(w, self.PLAN))


if __name__ == "__main__":
    unittest.main()
