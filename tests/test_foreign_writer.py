"""M17: INV-16 foreign writer, end to end (real runner, Gate, Sensor, Journal; fake game in process).

- The harvest as it is, 5 quiet ticks -> 0 STOP.
- Something writes with OUR key behind the harness's back (an offer, a dealer thread, a message in a thread that
  existed at baseline, a duel message) -> STOP within <= 1 tick, exit code 2, STOP file in the root.
- What others create (a rival opens a thread with us and sends us 30 offers) never triggers STOP.
The runner runs in dry, so every write in the game log comes from the "foreign" process.
"""
from __future__ import annotations

import unittest

import tests  # noqa: F401  (test isolation)
from agent import runner
from tests import m17_support as S

TEAM = "t18"


class ForeignWriter:
    """A second process holding our key: at tick `at` it performs `action(game)` as t18."""

    def __init__(self, at, action):
        self.at, self.action, self.done_at = at, action, None

    def on_tick(self, game):
        if self.done_at is None and game.tick >= self.at:
            status, _ = self.action(game)
            assert status == 200, status
            self.done_at = game.tick


class StallDealer:
    """A dealer at the stall that never answers (only so the fake accepts a thread with it)."""
    dealer_id = "abuela"

    def on_message(self, game, thread, msg):
        return None


class RivalSpammer:
    """Another team: opens a thread with us and sends us offers (30 in total)."""

    def __init__(self, team="t66", total=30):
        self.team, self.total, self.sent, self.thread = team, total, 0, None

    def attach(self, game):
        if self.team not in game.teams:
            game.add_team(self.team, cash=900, cards=["LAV-01", "LAV-02", "MAL-01", "MAL-02", "LAT-02"] * 2)

    def on_tick(self, game):
        if self.thread is None:
            s, t = game.handle("POST", "/api/threads", {"with": TEAM}, team=self.team)
            if s == 200:
                self.thread = t["id"]
        while self.sent < self.total:
            mine = [a for a, x in game.assets.items() if x["owner"] == self.team and x["kind"] == "card"]
            body = {"give": {"cash": 3 + self.sent % 5}, "want": {"cards": ["LAV-03"]}, "to": TEAM,
                    "expires_in_ticks": 40} if self.sent % 2 or not mine else \
                {"give": {"assets": [mine[0]]}, "want": {"cash": 50}, "to": TEAM, "expires_in_ticks": 40}
            s, _ = game.handle("POST", "/api/offers", body, team=self.team)
            self.sent += 1
            if self.sent % 10 == 0:
                break                                  # spread over a few ticks


def run_dry(game, ticks):
    p = S.paths("t18-m17-fw-")
    rc = S.run(game, p, mode="dry", armed=runner.TACTICS, ticks=ticks)
    return rc, p, S.rows(p)


def stopped(p) -> bool:
    return any(x.name.upper().startswith("STOP") for x in p.root.iterdir())


class TestForeignWriter(unittest.TestCase):
    def game(self):
        g = S.saturday(4, bots=(), dealers=False, duels=False)
        g.add_bot(StallDealer())
        return g

    def test_quiet_harvest_five_ticks_no_stop(self):
        g = self.game()
        rc, p, rows = run_dry(g, 5)
        self.assertEqual(rc, 0)
        self.assertFalse(stopped(p))
        self.assertEqual([r for r in rows if r["kind"] == "stop"], [])
        self.assertEqual(sum(1 for r in rows if r["kind"] == "tick"), 5)

    def _assert_stop_within_one_tick(self, g, fw, what):
        g.add_bot(fw)
        rc, p, rows = run_dry(g, 20)
        self.assertIsNotNone(fw.done_at, "the foreign write never happened")
        self.assertEqual(rc, 2, what)
        self.assertTrue(stopped(p), what)
        stops = [r for r in rows if r["kind"] == "stop" and "foreign_writer" in str(r.get("reason"))]
        self.assertTrue(stops, [r for r in rows if r["kind"] == "stop"])
        whats = (what,) if isinstance(what, str) else tuple(what)
        self.assertTrue(any(x in str(stops[0]["reason"]) for x in whats), (whats, stops[0]["reason"]))
        ticks = [r["tick"] for r in rows if r["kind"] == "tick"]
        last = max(ticks) if ticks else fw.done_at
        self.assertLessEqual(last - fw.done_at, 1, "STOP must come within one tick")
        self.assertEqual(S.writes(g, TEAM)[1:], [], "nothing else may be written after the foreign write")

    def test_offer_with_our_key(self):
        g = self.game()
        aid = sorted(a for a, x in g.assets.items() if x["owner"] == TEAM and x["kind"] == "card")[-1]
        fw = ForeignWriter(g.tick + 2, lambda gm: gm.handle("POST", "/api/offers",
                                                            {"give": {"assets": [aid]}, "want": {"cash": 99}},
                                                            team=TEAM))
        self._assert_stop_within_one_tick(g, fw, "offer:")

    def test_dealer_thread_with_our_key(self):
        g = self.game()
        fw = ForeignWriter(g.tick + 2, lambda gm: gm.handle("POST", "/api/threads",
                                                            {"with": "abuela", "topic": {"buy": {"card": "LAT-09"}}},
                                                            team=TEAM))
        self._assert_stop_within_one_tick(g, fw, "thread:")

    def test_message_as_t18_in_a_baseline_thread(self):
        g = self.game()
        s, t = g.handle("POST", "/api/threads", {"with": "abuela", "topic": {"buy": {"card": "LAT-09"}}}, team=TEAM)
        self.assertEqual(s, 200)
        g.requests.clear()                         # opened before the harness started: part of the baseline
        tid = t["id"]
        fw = ForeignWriter(g.tick + 2, lambda gm: gm.handle("POST", f"/api/threads/{tid}/messages",
                                                            {"text": "te doy 5", "price": 5}, team=TEAM))
        # the message carries a priced offer made by t18: caught as the offer or as the message, whichever first
        self._assert_stop_within_one_tick(g, fw, ("thread_msg:", "offer:"))

    def test_duel_message_as_t18(self):
        g = self.game()
        live = sorted(d for d, x in g.duels.items() if x["status"] == "live" and x["deadline_tick"] > g.tick + 4)
        self.assertTrue(live)
        did = live[0]
        fw = ForeignWriter(g.tick + 2, lambda gm: gm.handle("POST", f"/api/duels/{did}/messages",
                                                            {"text": "50", "price": 50}, team=TEAM))
        self._assert_stop_within_one_tick(g, fw, "duel_msg:")

    def test_rival_thread_and_thirty_offers_to_us_never_stop(self):
        g = self.game()
        spam = g.add_bot(RivalSpammer())
        rc, p, rows = run_dry(g, 8)
        self.assertEqual(spam.sent, 30)
        self.assertIsNotNone(spam.thread)
        self.assertEqual(rc, 0, [r for r in rows if r["kind"] in ("stop", "alarm")][:3])
        self.assertFalse(stopped(p))
        self.assertEqual(S.writes(g, TEAM), [])


if __name__ == "__main__":
    unittest.main()
