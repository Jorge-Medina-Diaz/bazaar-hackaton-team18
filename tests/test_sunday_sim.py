"""Sunday 4 Oct in the simulator (night audit): the real runner, Gate and tactics with config/plan.json, LIVE against
sim.sunday (loopback, test key), from 13:30 to 14:10 wall: the derived dealer day end (13:55 in C and B), the stall
close latched after its entries leave the schedule, the Grand Final duels with days, and no new dealer thread after
the day end."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

import tests  # noqa: F401  (isolation: BAZAAR_TEST=1, no key)
from sim import sunday
from sim import world as SW


def _rows(p):
    return [json.loads(x) for x in Path(p.journal).read_text(encoding="utf-8").splitlines() if x.strip()]


class SundayAfternoonTest(unittest.TestCase):
    def day(self, scen):
        with mock.patch.object(SW, "DEALERS", SW.DEALERS + ("picaros",)):
            g = sunday.build(scen, start_min=270, released=("LAV", "MAL", "LAT", "SAL", "RET", "CHA"))
            rc, p = sunday.run(g, 40)
        return g, _rows(p), rc

    def check(self, scen, day_end):
        g, rows, rc = self.day(scen)
        self.assertEqual(rc, 0)
        params = [r for r in rows if r["kind"] == "param" and r.get("name") == "day_times"]
        self.assertTrue(params)
        self.assertTrue(all(abs(r["day_end"] - day_end) < 0.01 for r in params), params)   # latched after 14:00
        t_of = {r["tick"]: r for r in rows if r["kind"] == "tick"}
        end_tick = min(t for t in t_of if g.t_open + (t - min(t_of)) / 60.0 + 4.5 >= day_end - 1e-6)
        late_opens = [r for r in rows if r["kind"] == "intent" and r.get("intent_kind") == "open_thread"
                      and r["tick"] >= end_tick]
        self.assertEqual(late_opens, [])
        open_t18 = [t for t in g.threads.values() if t["team"] == "t18" and t["status"] == "open"]
        self.assertEqual(open_t18, [])
        final = [d for d in g.duels.values() if d["session"] >= end_tick]
        self.assertTrue(final)                                          # the Grand Final wave at 14:00
        says = [r for r in rows if r["kind"] == "intent" and r.get("intent_kind") == "duel_say"]
        self.assertTrue(says)
        self.assertTrue(all(type(r["args"].get("days")) is int for r in says))
        return g, rows

    def test_scenario_c(self):
        self.check("C", 18.284)

    def test_scenario_b(self):
        self.check("B", 21.567)
