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

    def test_cha_rare_need_cap_allows_the_chato_fallback(self):
        # night audit: CHA:rare Pícaros (<= 60) falls back to El Chato (limit 90); the Need cap must let it open
        cfg = copy.deepcopy(self.cfg)
        cfg["page_sets"] = ["CHA"]
        cfg["profiles"]["CHA:rare"] = {"dealer": "picaros", "anchor": 45, "step": 3, "limit": 60, "fallback_after": 24}
        w = make_world(released=("LAV", "MAL", "LAT", "SAL", "RET", "CHA"), t_hours=14.0, today="sun")
        caps = lambda c: {n.ref: (n.source, n.max_price) for n in pages.plan(w, valuer_for(w), c, {})[0]  # noqa: E731
                          if n.ref in ("CHA-09", "CHA-10") and not n.closer}
        self.assertEqual(set(caps(cfg).values()), {("picaros", 60)})                     # no fallback profile
        cfg["profiles"]["CHA:rare"]["fallback_dealer"] = "chato"
        cfg["profiles"]["rare"] = {"dealer": "chato", "anchor": 70, "step": 4, "limit": 90, "fallback_after": None}
        self.assertEqual(set(caps(cfg).values()), {("picaros", 90)})
        self.assertEqual(pages.need_limit(cfg, "CHA-01", {"set": "CHA", "rarity": "common"}), 12)   # no fallback

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

    def test_extra_need_waits_for_release(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["profiles"]["CHA-10"] = {"dealer": "picaros", "anchor": 130, "step": 3, "limit": 170, "fallback_after": 24}
        cfg["page_sets"] = []
        cfg["extra_needs"] = [{"ref": "CHA-10", "max_price": 170}]
        w = make_world()                                                   # CHA not released yet
        self.assertEqual(pages.plan(w, valuer_for(w), cfg, {})[0], [])
        rel = make_world(released=("LAV", "MAL", "LAT", "SAL", "RET", "CHA"))
        needs = pages.plan(rel, valuer_for(rel), cfg, {})[0]
        self.assertEqual([(n.ref, n.source) for n in needs], [("CHA-10", "picaros")])

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
        self.assertAlmostEqual(pc["day_end_hours"]["sun"], 18.2837, places=3)      # stalls - 5 min
        self.assertAlmostEqual(pc["closer"]["endgame_hours"]["sun"], 18.7837, places=3)
        self.assertFalse(pages.past_day_end(_sun(18.2, 19.367, 18.367), pc))
        self.assertTrue(pages.past_day_end(_sun(18.29, 19.367, 18.367), pc))

    def test_clock_jump_to_16_65(self):
        # jump: CHA + round 3 at 09:00, stalls 21.65, close 22.65; the plan hours would fire at 09:00
        w = _sun(19.5, 22.65, 21.65)                                              # ~11:50 after a jump
        self.assertTrue(pages.past_day_end(w, self.PLAN))                         # the bug this fixes
        pc, _ = self.eff(w)
        self.assertFalse(pages.past_day_end(w, pc))
        self.assertFalse(pages.endgame(w, pc))
        self.assertAlmostEqual(pc["day_end_hours"]["sun"], 21.5667, places=3)
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
        self.assertAlmostEqual(pc["day_end_hours"]["sun"], 18.2837, places=3)
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



def _wall(h, m=0):
    """Epoch of Sunday 4 Oct 2026 hh:mm Madrid (+02:00)."""
    from datetime import datetime
    return datetime.fromisoformat(f"2026-10-04T{h:02d}:{m:02d}:00+02:00").timestamp()


def _sunw(t, upcoming, *, closes="2026-10-04T15:00:00+02:00", today="sun", paused=False, doors="open"):
    import dataclasses
    w = make_world(t_hours=t, today=today)
    return dataclasses.replace(w, clock={"today": today, "doors": doors, "paused": paused, "closes": closes},
                               schedule={"now_hours": t, "upcoming": list(upcoming)})


def _stalls(at):
    return [{"at_hours": at, "action": "persona", "params": {"id": p, "enabled": False}}
            for p in ("abuela", "chato", "pilar", "picaros", "banco")]


class WallCloseTest(unittest.TestCase):
    """Strategy M2 (night audit): day end / endgame from clock.closes (wall) and the live schedule, in the three
    Sunday clock scenarios. Expected: dealer day end 13:55 (C, B) or 14:55 (A), endgame 14:25 in all three."""
    PLAN = {"day_end_hours": {"sun": 19.283}, "day_end_min_before_close": 5,
            "closer": {"endgame_hours": {"sun": 18.783, "N": 18.783, "*": 18.783}, "endgame_min_before_close": 35}}

    def eff(self, w, now, seen=None):
        return pages.effective_plan(self.PLAN, w, seen, now=now)

    def test_scenario_c_resume_and_re_anchor(self):
        # t13.367 at 09:00, stalls re-anchored to 18.367 (14:00), the schedule's day_closes not re-projected yet
        w = _sunw(13.367, _stalls(18.367) + [{"at_hours": 22.65, "action": "day_closes", "params": {"day": "sun"}}])
        pc, _ = self.eff(w, _wall(9))
        self.assertAlmostEqual(pc["day_end_hours"]["sun"], 18.2837, places=3)
        self.assertAlmostEqual(pc["closer"]["endgame_hours"]["sun"], 18.7837, places=3)

    def test_scenario_a_resume_nothing_moves(self):
        w = _sunw(13.367, _stalls(21.65) + [{"at_hours": 22.65, "action": "day_closes", "params": {"day": "sun"}},
                                            {"at_hours": 22.65, "action": "end_round", "params": {}}])
        pc, _ = self.eff(w, _wall(9))
        self.assertAlmostEqual(pc["day_end_hours"]["sun"], 19.2837, places=3)     # 14:55
        self.assertAlmostEqual(pc["closer"]["endgame_hours"]["N"], 18.7837, places=3)
        self.assertTrue(pages.past_day_end(_sunw(19.29, ()), pc))

    def test_scenario_b_jump_to_16_65(self):
        w = _sunw(16.65, _stalls(21.65) + [{"at_hours": 22.65, "action": "day_closes", "params": {"day": "sun"}}])
        pc, _ = self.eff(w, _wall(9))
        self.assertAlmostEqual(pc["day_end_hours"]["sun"], 21.5667, places=3)     # 13:55
        self.assertAlmostEqual(pc["closer"]["endgame_hours"]["sun"], 22.0667, places=3)

    def test_a_pause_moves_both_earlier(self):
        up = _stalls(18.367)
        before, _ = self.eff(_sunw(15.0, up), _wall(10, 38))
        after, _ = self.eff(_sunw(15.0, up), _wall(10, 48))                         # 10 min paused: t did not move
        self.assertAlmostEqual(before["closer"]["endgame_hours"]["sun"] - after["closer"]["endgame_hours"]["sun"],
                               10 / 60, places=3)
        self.assertAlmostEqual(after["closer"]["endgame_hours"]["sun"], 15.0 + (4 + 12 / 60) - 35 / 60, places=3)

    def test_end_round_alone_is_a_close(self):
        w = _sunw(13.4, [{"at_hours": 19.367, "action": "end_round", "params": {}}], closes=None)
        pc, _ = self.eff(w, None)
        self.assertAlmostEqual(pc["closer"]["endgame_hours"]["sun"], 19.367 - 35 / 60, places=3)

    def test_doors_closed_or_no_closes_falls_back(self):
        pc, _ = self.eff(_sunw(13.367, [{"at_hours": 15.0, "action": "bench", "params": {}}], closes=None), _wall(9))
        self.assertEqual(pc["day_end_hours"]["sun"], 19.283)                       # schedule readable: plan hours
        closed = _sunw(13.367, (), doors="closed")
        pc, _ = self.eff(closed, _wall(8))
        self.assertFalse(pages.past_day_end(closed, pc))

    def test_stale_saturday_close_never_ends_sunday(self):
        # Sunday's first open tick still says today 'sat', closes Sat 23:00, and the fired 'day_closes sat' lingers
        w = _sunw(13.367, [{"at_hours": 13.367, "action": "day_closes", "params": {"day": "sat"}}],
                  closes="2026-10-03T23:00:00+02:00", today="sat")
        pc, _ = pages.effective_plan({"day_end_hours": {"sun": 19.283}, "closer": {}}, w, None, now=_wall(9))
        self.assertFalse(pages.past_day_end(w, pc))
        self.assertFalse(pages.endgame(w, pc))

    def test_stale_closed_door_saturday_entry_with_a_past_wall_is_skipped(self):
        # night review S2: scenario A on Sunday 09:00 with clock.today still 'sat'; the closed-door entry
        # 'day_closes sat' at 16.65 (wall Sat 23:00) lingers ahead of t. It used to be taken as today's close
        # (endgame 16.067 = 11:44, dealer day end 12:12); its wall has passed, so the Sunday close 19.367 wins.
        up = _stalls(21.65) + [
            {"at_hours": 16.65, "action": "day_closes", "params": {"day": "sat"}, "wall": "2026-10-03T23:00:00+02:00"},
            {"at_hours": 19.367, "action": "day_closes", "params": {"day": "sun"}, "wall": "2026-10-04T15:00:00+02:00"}]
        for closes in ("2026-10-04T15:00:00+02:00", "2026-10-03T23:00:00+02:00"):
            w = _sunw(13.367, up, closes=closes, today="sat")
            self.assertEqual(pages.live_times(w, _wall(9))[0], 19.367)
            pc, _ = self.eff(w, _wall(9))
            self.assertAlmostEqual(pc["day_end_hours"]["sat"], 19.2837, places=3, msg=closes)
            self.assertAlmostEqual(pc["closer"]["endgame_hours"]["sat"], 18.7837, places=3, msg=closes)
            self.assertFalse(pages.endgame(_sunw(16.1, up, closes=closes, today="sat"), pc))
        # without `now` the entry is still read by hour (old callers keep their behaviour)
        self.assertEqual(pages.live_times(_sunw(13.367, up, today="sat"))[0], 16.65)

    def test_stalls_latch_after_the_event_fires(self):
        _, seen = self.eff(_sunw(18.2, _stalls(18.367)), _wall(13, 50))
        w = _sunw(18.45, ())                                                       # 14:05, entries gone
        pc, _ = self.eff(w, _wall(14, 5), seen)
        self.assertAlmostEqual(pc["day_end_hours"]["sun"], 18.2837, places=3)
        self.assertTrue(pages.past_day_end(w, pc))

    def test_hygiene_and_rastro_agree_with_pages(self):
        from agent.tactics import hygiene, rastro
        w = _sunw(18.3, _stalls(18.367))
        pc, _ = self.eff(w, _wall(13, 56))
        self.assertTrue(pages.past_day_end(w, pc))
        self.assertTrue(hygiene._day_end(w, pc))
        late = _sunw(18.79, ())
        pc2, _ = self.eff(late, _wall(14, 26))
        self.assertTrue(pages.endgame(late, pc2))
        from types import SimpleNamespace
        self.assertTrue(rastro._Ctx.endgame(SimpleNamespace(endgame_hours=pc2["closer"]["endgame_hours"], w=late)))

    def test_load_plan_validates_minutes(self):
        import json, tempfile, os
        base = json.loads(PLAN.read_text(encoding="utf-8"))
        for bad in (-1, 241, "5"):
            raw = dict(base, day_end_min_before_close=bad)
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
                json.dump(raw, fh)
            try:
                with self.assertRaises(ValueError):
                    pages.load_plan(Path(fh.name))
            finally:
                os.unlink(fh.name)



class SundayPlanTest(unittest.TestCase):
    """The live config/plan.json for Sunday 4 Oct (strategy of the night audit): loads, and its keys do what the
    plan notes say."""

    def setUp(self):
        self.full = pages.load_plan(ROOT / "config" / "plan.json")
        # the CHA/RET extra-need semantics below ignore Sunday's LAV-07 egg carrier (Chato buy thread, cap 16)
        self.cfg = dict(self.full, extra_needs=[e for e in self.full["extra_needs"] if e["ref"] not in ("LAV-07", "CHA-12")])

    def test_sunday_keys(self):
        c = self.full
        self.assertNotIn("sat", c["day_end_hours"])               # a stale today='sat' must not close Sunday threads
        self.assertEqual(c["day_end_min_before_close"], 5)
        self.assertEqual(c["closer"]["endgame_min_before_close"], 35)
        self.assertNotIn("SAL", c["dup_min_price"])
        self.assertGreater(c["resupply_min"], 50)                  # > NEG_CAP: J13 resupply can never pass
        self.assertIs(c["endgame_buy_any"], True)
        self.assertIsNone(c["days_sign"])
        self.assertEqual(c["page_sets"], ["RET", "LAT", "CHA"])
        self.assertEqual({e["ref"]: e["max_price"] for e in c["extra_needs"]}, {"CHA-11": 225, "RET-11": 150, "CHA-12": 470})
        self.assertEqual(set(c["hand_sales"]), {"MAL-01", "MAL-02", "MAL-04", "MAL-05", "LAV-02", "LAV-03", "LAV-05",
                                                "LAT-06", "LAT-02"})   # night review P2: LAT-06 #1105 is the proven
                                                                       # Pilar / Chato carrier; J5 listed it at 18

    def test_cha_rare_need_cap_reaches_the_chato_fallback(self):
        card = {"set": "CHA", "rarity": "rare"}
        self.assertEqual(pages.profile_for(self.cfg, "CHA-09", card)["dealer"], "picaros")
        self.assertEqual(pages.need_limit(self.cfg, "CHA-09", card), 93)
        self.assertEqual(self.cfg["dealer_max"]["CHA-09"], 93)

    def test_extra_needs_only_after_the_cha_release(self):
        import dataclasses
        cfg = dict(self.cfg, page_sets=[])
        w = dataclasses.replace(make_world(t_hours=13.5, today="sun"), round=3)
        self.assertEqual([(n.ref, n.source) for n in pages.plan(w, valuer_for(w), cfg, {})[0]], [("RET-11", "picaros")])
        rel = dataclasses.replace(make_world(released=("LAV", "MAL", "LAT", "SAL", "RET", "CHA"), t_hours=13.5,
                                             today="sun"), round=3)
        needs = pages.plan(rel, valuer_for(rel), cfg, {})[0]
        self.assertEqual(sorted((n.ref, n.source) for n in needs), [("CHA-11", "picaros"), ("RET-11", "picaros")])
        self.assertTrue(all(n.max_price <= {"CHA-11": 225, "RET-11": 150}[n.ref] for n in needs))

    def test_extra_needs_wait_for_round_3(self):
        # night review P6/E2E-3: scenario A, Sunday 09:00 is still round 2 (L4 slots 3/3): no RET-11 Pícaros buy
        import dataclasses
        cfg = dict(self.cfg, page_sets=[])
        r2 = make_world(released=("LAV", "MAL", "LAT", "SAL", "RET", "CHA"), t_hours=13.5, today="sun")
        self.assertEqual(r2.round, 2)
        self.assertEqual(pages.plan(r2, valuer_for(r2), cfg, {})[0], [])
        r3 = dataclasses.replace(r2, round=3)
        self.assertEqual(sorted(n.ref for n in pages.plan(r3, valuer_for(r3), cfg, {})[0]), ["CHA-11", "RET-11"])
        self.assertEqual({e["ref"]: e.get("min_round") for e in self.cfg["extra_needs"]}, {"CHA-11": 3, "RET-11": 3})
        import json, tempfile, os
        raw = json.loads((ROOT / "config" / "plan.json").read_text(encoding="utf-8"))
        raw["extra_needs"] = [{"ref": "RET-11", "max_price": 150, "min_round": "3"}]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(raw, fh)
        try:
            with self.assertRaises(ValueError):
                pages.load_plan(Path(fh.name))
        finally:
            os.unlink(fh.name)

    def test_page_needs_come_before_extra_needs(self):
        # night review P1: dealers.propose opens one thread per dealer in Need order; CHA-11/RET-11 (Pícaros) used to
        # come first and take the Pícaros slot from the CHA rares the page (and its +50 closer) needs
        import dataclasses
        w = dataclasses.replace(make_world(released=("LAV", "MAL", "LAT", "SAL", "RET", "CHA"), t_hours=13.5,
                                           today="sun"), round=3)
        needs = [n for n in pages.plan(w, valuer_for(w), self.cfg, {})[0] if not n.closer]
        refs = [n.ref for n in needs]
        self.assertIn("CHA-11", refs)
        first_extra = min(refs.index(r) for r in ("CHA-11", "RET-11") if r in refs)
        self.assertTrue(all(n.set in ("RET", "LAT", "CHA") for n in needs[:first_extra]))
        self.assertGreater(first_extra, 0)
        self.assertEqual(set(refs[first_extra:]), {"CHA-11", "RET-11"} & set(refs))


if __name__ == "__main__":
    unittest.main()
