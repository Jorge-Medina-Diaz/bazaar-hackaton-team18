"""M12 duels: INV-12 (0 prices outside the limit, monotone, accept only on the tick the rival spoke), J7, J10, E8, E16.

Uses an in-file DuelRival double (8 behaviours) instead of sim/bots.py, which belongs to M6b.
"""
from __future__ import annotations

import copy
import json
import random
import unittest
from types import MappingProxyType

from tests import HARVEST
from agent.contracts import FRIDAY, Limits, World
from agent.tactics import duels as D

ROLES = ("buyer", "seller")
DECAYS = (0.06, 0.08, 0.10)
RIVALS = ("mute", "accept_only", "one_and_accept", "reactive", "time_driven", "firm", "worsening", "injector")


def surplus(role, L, p):
    return (L - p) if role == "buyer" else (p - L)


def make_world(duels, tick, accepts=1, down=frozenset()):
    lim = Limits(accepts, 1, 6, 30, 12)
    return World(tick=tick, t_hours=10.0, round=2, tick_seconds=30.0, tick_deadline=1e12, clock={}, limits=lim,
                 reading="N", me={}, my_offers=(), offers_to_us=(), board=(), own_pseudonym=None, threads={},
                 foreign_threads=(), duels=tuple(duels), catalog={}, schedule={}, released_sets=frozenset(),
                 feed_new=(), server_values={}, down=frozenset(down))


def duel(did=1, role="buyer", L=100, deadline=116, decay=0.06, msgs=(), rival_offer=None, issues=("price",),
         w=None, meaning=None):
    ours = [m for m in msgs if m["from"] == "you"]
    yo = {"price": ours[-1]["price"], "days": ours[-1].get("days"), "tick": ours[-1]["tick"], "id": 9} if ours else None
    return {"duel": did, "status": "live", "role": role, "your_limit": L, "deadline_tick": deadline,
            "decay_per_round": decay, "issues": list(issues), "messages": [dict(m) for m in msgs],
            "rival_offer": rival_offer, "your_offer": yo, "your_days_weight": w, "days_meaning": meaning,
            "rounds": 0}


def msg(frm, tick, price, days=None):
    return {"from": frm, "tick": tick, "price": price, "days": days}


# ------------------------------------------------------------------------------------- rival double

class DuelRival:
    """Rival bot. Speaks at most once per tick (messages_per_side_per_tick = 1, measured)."""

    def __init__(self, kind, role, L, T, rng):
        self.kind, self.rng = kind, rng
        self.role = "seller" if role == "buyer" else "buyer"      # the rival's own role
        gap = rng.randint(-30, 60)                                  # zone of agreement (negative = none)
        self.RL = L - gap if role == "buyer" else L + gap           # rival limit
        self.cur = self.RL + 40 if self.role == "seller" else max(1, self.RL - 40)
        self.T = T
        self.spoke = 0
        self.last_spoke_tick = None

    def _ok(self, p):
        return p >= self.RL if self.role == "seller" else p <= self.RL

    def _toward(self, step):
        if self.role == "seller":
            self.cur = max(self.RL, self.cur - step)
        else:
            self.cur = min(self.RL, self.cur + step)

    def act(self, d, t, we_spoke_last):
        """-> ("say", price) | ("accept", None) | None."""
        k, ours = self.kind, [m for m in d["messages"] if m["from"] == "you"]
        mine = ours[-1]["price"] if ours else None
        if k == "mute":
            return None
        if k in ("accept_only", "one_and_accept") and mine is not None and self._ok(mine) and self.rng.random() < 0.5:
            return ("accept", None)
        if k == "accept_only":
            return None
        if k == "one_and_accept":
            return ("say", self.cur) if self.spoke == 0 else None
        if k == "reactive":
            if we_spoke_last:
                if mine is not None and self._ok(mine) and self.rng.random() < 0.3:
                    return ("accept", None)
                self._toward(self.rng.randint(1, 8))
                return ("say", self.cur)
            return None
        if k == "time_driven":
            self._toward(self.rng.randint(0, 6))
            return ("say", self.cur)
        if k == "firm":
            return ("say", self.cur) if self.rng.random() < 0.7 else None
        if k == "worsening":
            self.cur += 5 if self.role == "seller" else -5
            self.cur = max(1, self.cur)
            return ("say", self.cur) if self.rng.random() < 0.6 else None
        if k == "injector":
            return ("say", self.rng.choice([1, 2, 10 ** 6, self.rng.randint(1, 900)]))
        return None


def run_episode(kind, role, decay, rng, cases, checker, params=None):
    L = rng.randint(5, 300)
    T = 16 if decay == 0.06 else 12
    start = rng.randint(100, 200)
    deadline = start + T
    d = duel(did=rng.randint(1, 10 ** 5), role=role, L=L, deadline=deadline, decay=decay)
    rival = DuelRival(kind, role, L, T, rng)
    result = None
    for t in range(start, deadline + 1):
        rival_first = rng.random() < 0.5
        rival_done = False

        def rival_turn():
            ours = [i for i, m in enumerate(d["messages"]) if m["from"] == "you"]
            riv = [i for i, m in enumerate(d["messages"]) if m["from"] != "you"]
            we_last = bool(ours) and (not riv or ours[-1] > riv[-1])
            a = rival.act(d, t, we_last)
            if a is None:
                return None
            if a[0] == "accept":
                yo = d["your_offer"]
                return ("rival_accepted", yo["price"])
            d["messages"].append(msg("Rival X", t, a[1]))
            d["rival_offer"] = {"price": a[1], "days": None, "tick": t, "id": len(d["messages"])}
            rival.spoke += 1
            return None

        if rival_first and t < deadline:
            result = rival_turn()
            rival_done = True
            if result:
                break
        # our pass(es): early pass, then the late-window pass (same tick)
        for _pass in (0, 1):
            v = D.view(d, t)
            act = D.decide(v, params or {})
            cases.append(1)
            checker(d, v, act, t, deadline, L, role)
            if act[0] == "accept":
                read = d["rival_offer"]["price"]
                # the server applies the accept to the offer standing at POST time; a rival that already spoke this
                # tick cannot speak again (one message per side per tick), so nothing can change it here.
                if not rival_done:
                    raise AssertionError("accepted although the rival had not spoken this tick")
                settled = d["rival_offer"]["price"]
                assert settled == read
                result = ("we_accepted", settled)
                break
            if act[0] == "say":
                d["messages"].append(msg("you", t, act[1], act[2]))
                d["your_offer"] = {"price": act[1], "days": act[2], "tick": t, "id": 1}
            if not rival_done and t < deadline:
                result = rival_turn()
                rival_done = True
                if result:
                    break
        if result:
            break
    return result


class TestInvariant12Fuzz(unittest.TestCase):
    def test_8_rivals_2_roles_3_decays_2000_cases(self):
        self._fuzz({}, 18)

    def test_fuzz_voss_options_on(self):
        # V2 precise + V3 ackerman + V4 punch (both modes), V1 off and on: INV-12 holds the same way
        self._fuzz({"precise": True, "ackerman": True, "punch": True}, 19)
        self._fuzz({"precise": True, "ackerman": True, "punch": True, "punch_mode": "wait", "voss_text": False}, 20)
        self._fuzz({"precise": True, "punch": True, "ack_target": 1.0}, 21)

    def _fuzz(self, params, seed):
        rng = random.Random(seed)
        cases, bad = [], []
        last_our = {}

        def checker(d, v, act, t, deadline, L, role):
            kind, price, days = act
            if kind == "say":
                if type(price) is not int or surplus(role, L, price) < 1:
                    bad.append(("outside", d["duel"], t, price, L, role))
                ours = [m for m in d["messages"] if m["from"] == "you"]
                if ours and ours[-1]["tick"] == t:
                    bad.append(("two_msgs_tick", d["duel"], t))
                if ours and (price - ours[-1]["price"]) * (1 if role == "buyer" else -1) < 0:
                    bad.append(("retract", d["duel"], t, ours[-1]["price"], price))
                if t > deadline - 1:
                    bad.append(("after_deadline", d["duel"], t))
            elif kind == "accept":
                ro = d["rival_offer"]
                if ro is None or ro["tick"] != t:
                    bad.append(("accept_not_now", d["duel"], t))
                elif surplus(role, L, ro["price"]) < 1:
                    bad.append(("accept_outside", d["duel"], t, ro["price"], L))
                if t > deadline - 1:
                    bad.append(("accept_late", d["duel"], t))

        outcomes = {}
        while len(cases) < 2000 or len(outcomes) < 48:
            for kind in RIVALS:
                for role in ROLES:
                    for decay in DECAYS:
                        r = run_episode(kind, role, decay, rng, cases, checker, params)
                        outcomes.setdefault((kind, role, decay), []).append(r)
        self.assertGreaterEqual(len(cases), 2000)
        self.assertEqual(bad, [], bad[:5])
        # some deals do happen against rivals that move (the policy is not just "never act")
        deals = sum(1 for rs in outcomes.values() for r in rs if r)
        self.assertGreater(deals, 0)

    def test_random_views_never_outside(self):
        rng = random.Random(7)
        for _ in range(3000):
            role = rng.choice(ROLES)
            L = rng.randint(1, 400)
            deadline = 200
            t = rng.randint(185, 205)
            msgs = []
            for tt in sorted(rng.randint(184, min(t, 199)) for _ in range(rng.randint(0, 8))):
                frm = rng.choice(["you", "R"])
                if frm == "you":
                    p = rng.randint(1, 900)
                    p = min(p, L - 1) if role == "buyer" else max(p, L + 1)
                    if p < 1:
                        continue
                    if any(m["from"] == "you" and m["tick"] == tt for m in msgs):
                        continue
                    msgs.append(msg("you", tt, p))
                else:
                    msgs.append(msg("R", tt, rng.randint(1, 900)))
            # our history is monotone in reality
            ours = [m for m in msgs if m["from"] == "you"]
            prices = sorted(m["price"] for m in ours)
            if role == "seller":
                prices.reverse()
            for m, p in zip(ours, prices):
                m["price"] = p
            riv = [m for m in msgs if m["from"] != "you"]
            ro = {"price": riv[-1]["price"], "days": None, "tick": riv[-1]["tick"], "id": 1} if riv else None
            d = duel(role=role, L=L, deadline=deadline, decay=rng.choice(DECAYS), msgs=msgs, rival_offer=ro)
            v = D.view(d, t)
            prm = {"anchor": rng.uniform(0.3, 0.95), "final_frac": rng.uniform(0, 1)}
            kind, price, _ = D.decide(v, prm)
            if kind == "say":
                self.assertGreaterEqual(surplus(role, L, price), 1)
                if ours:
                    self.assertLessEqual((ours[-1]["price"] - price) * (1 if role == "buyer" else -1), 0)
                    self.assertLess(ours[-1]["tick"], t)
                self.assertLessEqual(t, deadline - 1)
            if kind == "accept":
                self.assertEqual(ro["tick"], t)
                self.assertGreaterEqual(surplus(role, L, ro["price"]), 1)
                self.assertLessEqual(t, deadline - 1)


class TestAcceptOnlyWhenRivalSpoke(unittest.TestCase):
    def test_worsening_rival_speaking_another_tick_not_accepted(self):
        # rival offered 80 (inside our buyer limit 100) at t110; it is now t113, late, and it has not spoken
        d = duel(L=100, deadline=116, msgs=[msg("you", 104, 60), msg("R", 110, 80)],
                 rival_offer={"price": 80, "days": None, "tick": 110, "id": 5})
        kind, price, _ = D.decide(D.view(d, 114), {})
        self.assertNotEqual(kind, "accept")
        # instead it provokes: a message at the rival's price (monotone, inside the limit)
        self.assertEqual(kind, "say")
        self.assertEqual(price, 80)

    def test_rival_spoke_this_tick_accept_and_settles_at_read(self):
        d = duel(L=100, deadline=116, msgs=[msg("you", 104, 60), msg("R", 113, 80)],
                 rival_offer={"price": 80, "days": None, "tick": 113, "id": 5})
        self.assertEqual(D.decide(D.view(d, 113), {}), ("accept", 80, None))

    def test_no_accept_at_deadline(self):
        d = duel(L=100, deadline=116, msgs=[msg("you", 104, 60), msg("R", 116, 80)],
                 rival_offer={"price": 80, "days": None, "tick": 116, "id": 5})
        self.assertEqual(D.decide(D.view(d, 116), {})[0], "wait")

    def test_outside_limit_never_accepted(self):
        d = duel(L=100, deadline=116, msgs=[msg("you", 104, 60), msg("R", 114, 100)],
                 rival_offer={"price": 100, "days": None, "tick": 114, "id": 5})
        self.assertNotEqual(D.decide(D.view(d, 114), {})[0], "accept")


class TestPolicy(unittest.TestCase):
    def test_opening_anchor(self):
        self.assertEqual(D.decide(D.view(duel(L=100, deadline=116), 100), {}), ("say", 60, None))
        self.assertEqual(D.decide(D.view(duel(role="seller", L=60, deadline=116), 100), {}), ("say", 100, None))

    def test_slow_ascent_silent_rival(self):
        # buyer L=100, start 100, deadline 116: anchor 60 -> 99 at deadline-2, 75 % of the way by deadline-5
        d = duel(L=100, deadline=116)
        prices = {}
        for t in range(100, 116):
            kind, p, _ = D.decide(D.view(d, t), {})
            if kind == "say":
                d["messages"].append(msg("you", t, p))
                prices[t] = p
        self.assertEqual(prices[100], 60)
        self.assertEqual(max(prices.values()), 99)
        self.assertEqual(prices[114], 99)
        at_tail = max(p for t, p in prices.items() if t <= 111)
        self.assertLessEqual(at_tail, 60 + round(0.75 * 39) + 1)
        seq = [prices[t] for t in sorted(prices)]
        self.assertEqual(seq, sorted(seq))

    def test_no_concession_against_silence_after_first_offer(self):
        # K-06: the rival answered once at t103; we answered at t104; it stays silent -> we wait
        d = duel(L=100, deadline=116, msgs=[msg("you", 100, 60), msg("R", 103, 130), msg("you", 104, 66)],
                 rival_offer={"price": 130, "days": None, "tick": 103, "id": 2})
        for t in (105, 106, 107, 108, 109, 110):
            self.assertEqual(D.decide(D.view(d, t), {})[0], "wait", t)

    def test_concede_when_rival_answers(self):
        d = duel(L=100, deadline=116, msgs=[msg("you", 100, 60), msg("R", 103, 130)],
                 rival_offer={"price": 130, "days": None, "tick": 103, "id": 2})
        kind, p, _ = D.decide(D.view(d, 104), {})
        self.assertEqual(kind, "say")
        self.assertGreater(p, 60)
        self.assertLessEqual(p, 99)

    def test_one_message_per_tick(self):
        d = duel(L=100, deadline=116, msgs=[msg("you", 100, 60), msg("R", 101, 130), msg("you", 101, 66)])
        self.assertEqual(D.decide(D.view(d, 101), {})[0], "wait")

    def test_bad_shape_waits(self):
        for bad in ({"duel": 1}, {"duel": 1, "status": "live", "role": "x"}, {}, {"duel": "1"},
                    duel(decay=1.5), dict(duel(), messages=[{"from": "R", "tick": "x", "price": 3}])):
            self.assertEqual(D.decide(D.view(bad, 105), {}), ("wait", None, None))


class TestTwoIssues(unittest.TestCase):
    def two(self, **kw):
        return duel(issues=("price", "days"), **kw)

    def test_unreadable_days_no_message(self):
        self.assertEqual(D.decide(D.view(self.two(w=None, meaning="x"), 100), {})[0], "wait")
        self.assertEqual(D.decide(D.view(self.two(w=2.0, meaning=None), 100), {})[0], "wait")

    def test_sign_unknown_worst_case_margin(self):
        # w = 3 -> every price needs surplus >= 1 + 30
        d = self.two(L=100, w=3.0, meaning="delivery days", msgs=[msg("you", 100, 60, 0)])
        for t in range(101, 116):
            kind, p, days = D.decide(D.view(d, t), {})
            if kind == "say":
                self.assertLessEqual(p, 69)
                self.assertIsInstance(days, int)
                d["messages"].append(msg("you", t, p, days))
        ro = {"price": 75, "days": 5, "tick": 114, "id": 3}
        d2 = self.two(L=100, w=3.0, meaning="m", msgs=[msg("you", 100, 60, 0), msg("R", 114, 75, 5)], rival_offer=ro)
        self.assertNotEqual(D.decide(D.view(d2, 114), {})[0], "accept")       # 25 < 31
        ro = {"price": 69, "days": 5, "tick": 114, "id": 3}
        d3 = self.two(L=100, w=3.0, meaning="m", msgs=[msg("you", 100, 60, 0), msg("R", 114, 69, 5)], rival_offer=ro)
        self.assertEqual(D.decide(D.view(d3, 114), {})[0], "accept")

    def test_sign_known_best_days(self):
        kind, p, days = D.decide(D.view(self.two(L=100, w=2.0, meaning="m"), 100), {"days_sign": 1})
        self.assertEqual((kind, days), ("say", 10))
        kind, p, days = D.decide(D.view(self.two(L=100, w=2.0, meaning="m"), 100), {"days_sign": -1})
        self.assertEqual((kind, days), ("say", 0))
        # rival offers 85 with 10 days, sign -1, w 2: worst case loses 20 -> 15 - 20 < 1 -> no accept
        ro = {"price": 85, "days": 10, "tick": 114, "id": 3}
        d = self.two(L=100, w=2.0, meaning="m", msgs=[msg("you", 100, 60, 0), msg("R", 114, 85, 10)], rival_offer=ro)
        self.assertNotEqual(D.decide(D.view(d, 114), {"days_sign": -1})[0], "accept")
        self.assertEqual(D.decide(D.view(d, 114), {"days_sign": 1})[0], "accept")

    def test_missing_rival_days_not_accepted(self):
        ro = {"price": 50, "days": None, "tick": 114, "id": 3}
        d = self.two(L=100, w=2.0, meaning="m", msgs=[msg("you", 100, 40, 0), msg("R", 114, 50)], rival_offer=ro)
        self.assertNotEqual(D.decide(D.view(d, 114), {"days_sign": 1})[0], "accept")


class TestPropose(unittest.TestCase):
    def test_accept_budget_by_deadline(self):
        ds = []
        for did, dl in ((1, 120), (2, 116), (3, 118)):
            ds.append(duel(did=did, L=100, deadline=dl, msgs=[msg("you", 104, 60), msg("R", 115, 70)],
                           rival_offer={"price": 70, "days": None, "tick": 115, "id": did}))
        st = {}
        out = D.propose(make_world(ds, 115), None, {"days_sign": None}, {}, st)
        acc = [i for i in out if i.kind == "duel_accept"]
        self.assertEqual([i.args["duel_id"] for i in acc], [2])
        self.assertEqual(acc[0].args["fingerprint"], D.view(ds[1], 115).fingerprint)
        self.assertFalse(any(i.kind == "duel_say" and i.args["duel_id"] in (1, 3) for i in out))
        self.assertEqual(st["duel_accepts"][2]["price"], 70)
        self.assertAlmostEqual(acc[0].prediction.duel, 30 * 0.94 ** 1, places=1)
        self.assertEqual(acc[0].prediction.model, "U-01")
        # zero accept budget -> no duel_accept
        out0 = D.propose(make_world(ds, 115, accepts=0), None, {}, {}, {})
        self.assertFalse(any(i.kind == "duel_accept" for i in out0))

    def test_duels_down_nothing(self):
        self.assertEqual(D.propose(make_world([duel()], 100, down={"duels"}), None, {}, {}, {}), [])

    def test_say_intent_shape(self):
        out = D.propose(make_world([duel(did=7)], 100), None, {}, {}, {})
        self.assertEqual(len(out), 1)
        a = out[0].args
        self.assertEqual((out[0].kind, a["duel_id"], a["price"], a["days"], a["template"]), ("duel_say", 7, 60, None, "duel"))

    def test_e8_hold_first_rival(self):
        d = duel(did=4, L=100, deadline=116, msgs=[msg("you", 100, 60), msg("R", 103, 130)],
                 rival_offer={"price": 130, "days": None, "tick": 103, "id": 2})
        st = {}
        self.assertEqual(D.propose(make_world([d], 103), None, {}, {}, st), [])
        self.assertEqual(st["e8"], {"duel": 4, "until": 105})
        self.assertEqual(D.propose(make_world([d], 104), None, {}, {}, st), [])
        out = D.propose(make_world([d], 105), None, {}, {}, st)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].experiment, "E8")

    def test_e16_two_rival_msgs_pauses_accepts(self):
        d = duel(did=5, L=100, deadline=116, msgs=[msg("you", 104, 60), msg("R", 114, 90), msg("R", 114, 70)],
                 rival_offer={"price": 70, "days": None, "tick": 114, "id": 2})
        st = {}
        out = D.propose(make_world([d], 114), None, {}, {}, st)
        self.assertFalse(any(i.kind == "duel_accept" for i in out))
        self.assertTrue(st["duel_accepts_paused"].startswith("E16.two_msgs"))
        # and the pause holds for other duels too
        d2 = duel(did=6, L=100, deadline=116, msgs=[msg("you", 104, 60), msg("R", 114, 70)],
                  rival_offer={"price": 70, "days": None, "tick": 114, "id": 3})
        self.assertFalse(any(i.kind == "duel_accept" for i in D.propose(make_world([d2], 114), None, {}, {}, st)))

    def test_e16_settled_price(self):
        st = {"duel_accepts": {8: {"tick": 114, "price": 70, "days": None}}}
        self.assertIsNone(D.e16_settled(st, [{"duel": 8, "status": "deal", "price": 70, "your_offer": {"price": 66}}]))
        st = {"duel_accepts": {8: {"tick": 114, "price": 70, "days": None}}}
        self.assertTrue(D.e16_settled(st, [{"duel": 8, "status": "deal", "price": 75, "your_offer": {"price": 66}}]))


class TestCrossModule(unittest.TestCase):
    def test_fingerprint_matches_guards(self):
        try:
            from agent.guards import duel_fingerprint
        except Exception:                                   # M4a absent: local copy is used
            self.skipTest("agent.guards not importable")
        d = duel(did=11, msgs=[msg("you", 100, 60), msg("R", 101, 130)],
                 rival_offer={"price": 130, "days": None, "tick": 101, "id": 2})
        self.assertEqual(D._local_duel_fingerprint(d), duel_fingerprint(d))
        self.assertEqual(D.view(d, 101).fingerprint, duel_fingerprint(d))


class TestHarvest(unittest.TestCase):
    def test_live_practice_duels(self):
        data = json.loads((HARVEST / "duels_live.json").read_text(encoding="utf-8"))["duels"]
        for d in data:
            v = D.view(d, 160)
            self.assertTrue(v.ok, v.why)
            kind, p, _ = D.decide(v, {})
            if kind == "say":
                self.assertGreaterEqual(surplus(v.role, v.limit, p), 1)
        self.assertEqual(D.view(data[0], 160).fingerprint, D.view(copy.deepcopy(data[0]), 160).fingerprint)

    def test_friday_done_duels_messages_inside_limit(self):
        # replay: at every tick where we spoke on Friday, the policy's own say would stay inside the limit
        data = json.loads((HARVEST / "duels_done.json").read_text(encoding="utf-8"))["duels"]
        n = 0
        for d in data:
            msgs = d.get("messages") or []
            for i, m in enumerate(msgs):
                partial = dict(d, status="live", messages=msgs[:i])
                riv = [x for x in msgs[:i] if x["from"] != "you"]
                partial["rival_offer"] = ({"price": riv[-1]["price"], "days": riv[-1].get("days"),
                                           "tick": riv[-1]["tick"], "id": 1} if riv else None)
                kind, p, _ = D.decide(D.view(partial, m["tick"]), {})
                n += 1
                if kind == "say":
                    self.assertGreaterEqual(surplus(d["role"], d["your_limit"], p), 1)
        self.assertGreater(n, 100)


# ------------------------------------------------------------------------------- Voss options (V1-V4)

def _rival(t, price):
    return {"price": price, "days": None, "tick": t, "id": t}


class TestVossDefaults(unittest.TestCase):
    def test_defaults_off_except_text(self):
        # Code defaults stay conservative; config/plan.json "duels" turns on what run_duel_eval.py measured.
        self.assertTrue(D.DEFAULTS["voss_text"])
        for k in ("precise", "ackerman", "punch"):
            self.assertIs(D.DEFAULTS[k], False, k)
        self.assertEqual((D.DEFAULTS["ack_target"], D.DEFAULTS["punch_mode"], D.DEFAULTS["punch_x"]),
                         (0.8, "min", 0.5))

    def test_plan_turns_on_measured_options(self):
        import json
        from pathlib import Path
        plan = json.loads((Path(__file__).resolve().parents[1] / "config" / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan.get("duels"), {"precise": True, "punch": True, "punch_mode": "wait"})

    def test_decide_equals_decide_ex(self):
        rng = random.Random(55)
        opts = ({}, {"precise": True}, {"ackerman": True}, {"punch": True}, {"punch": True, "punch_mode": "wait"},
                {"precise": True, "ackerman": True, "punch": True}, {"voss_text": False})
        for _ in range(1500):
            role = rng.choice(ROLES)
            L = rng.randint(2, 300)
            t = rng.randint(100, 117)
            msgs, cur = [], None
            last = min(t, 115)
            for tt in sorted(rng.sample(range(100, last + 1), rng.randint(0, min(6, last - 99)))):
                if rng.random() < 0.5:
                    step = rng.randint(0, 12)
                    if cur is None:
                        cur = rng.randint(1, L - 1) if role == "buyer" else rng.randint(L + 1, 3 * L + 2)
                    cur = min(L - 1, cur + step) if role == "buyer" else max(L + 1, cur - step)
                    msgs.append(msg("you", tt, cur))
                else:
                    msgs.append(msg("R", tt, rng.randint(1, 3 * L + 2)))
            riv = [m for m in msgs if m["from"] != "you"]
            ro = _rival(riv[-1]["tick"], riv[-1]["price"]) if riv else None
            v = D.view(duel(role=role, L=L, deadline=116, msgs=msgs, rival_offer=ro), t)
            prm = dict(rng.choice(opts), anchor=rng.uniform(0.3, 0.95))
            act, phase = D.decide_ex(v, prm)
            self.assertEqual(D.decide(v, prm), act)
            if act[0] == "say":
                self.assertIn(phase, D.PHASE_VARIANT)
                self.assertGreaterEqual(surplus(role, L, act[1]), 1)
                if v.mine is not None:
                    self.assertLessEqual(surplus(role, L, act[1]), surplus(role, L, v.mine), phase)
                    if phase != "close":                 # close may repeat mine (pre-existing; G50.repeat)
                        self.assertLess(surplus(role, L, act[1]), surplus(role, L, v.mine), (phase, prm))
                    self.assertLess(v.ours[-1][0], t)
                self.assertLessEqual(t, 115)
            elif act[0] == "accept":
                self.assertEqual(phase, "accept")
            else:
                self.assertIsNone(phase)


class TestVossText(unittest.TestCase):
    """V1: the template variant follows the negotiation phase."""

    def test_templates_match_phases(self):
        from agent import talk
        for name in ("duel", "duel_days"):
            self.assertEqual(len(talk.TEMPLATES[name]), len(D.PHASE_VARIANT))
            for ph, i in D.PHASE_VARIANT.items():
                days = 3 if name == "duel_days" else None
                text = talk.render(name, i, 37, days)
                self.assertTrue(talk.firewall(text, 37, days, template=name).ok, (name, ph))
        self.assertIn("locura", talk.TEMPLATES["duel"][D.PHASE_VARIANT["open"]])
        self.assertIn("Cómo se supone", talk.TEMPLATES["duel"][D.PHASE_VARIANT["how"]])
        self.assertIn("dejado de lado", talk.TEMPLATES["duel"][D.PHASE_VARIANT["ghost"]])

    def phase(self, d, t, prm=None):
        return D.decide_ex(D.view(d, t), prm or {})

    def test_phases(self):
        self.assertEqual(self.phase(duel(L=100), 100), (("say", 60, None), "open"))
        self.assertEqual(self.phase(duel(L=100, msgs=[msg("you", 100, 60)]), 104)[1], "ghost")
        d = duel(L=100, msgs=[msg("you", 100, 60), msg("R", 103, 130)], rival_offer=_rival(103, 130))
        self.assertEqual(self.phase(d, 104)[1], "move")
        d = duel(L=100, msgs=[msg("you", 100, 60), msg("R", 103, 160)], rival_offer=_rival(103, 160))
        self.assertEqual(self.phase(d, 104)[1], "how")                     # extreme first offer (>= 1.5 L)
        d = duel(L=100, msgs=[msg("you", 100, 60), msg("R", 101, 130), msg("you", 102, 67), msg("R", 103, 130)],
                 rival_offer=_rival(103, 130))
        self.assertEqual(self.phase(d, 104)[1], "how")                     # rival did not move
        d = duel(L=100, msgs=[msg("you", 100, 60), msg("R", 103, 130), msg("you", 104, 70)],
                 rival_offer=_rival(103, 130))
        self.assertEqual(self.phase(d, 112)[1], "final")                   # deadline - final
        d = duel(L=100, msgs=[msg("you", 104, 60), msg("R", 110, 80)], rival_offer=_rival(110, 80))
        self.assertEqual(self.phase(d, 114), (("say", 80, None), "close"))  # late provoke
        d = duel(L=100, msgs=[msg("you", 104, 60), msg("R", 113, 80)], rival_offer=_rival(113, 80))
        self.assertEqual(self.phase(d, 113), (("accept", 80, None), "accept"))
        self.assertEqual(self.phase(duel(L=100, msgs=[msg("you", 100, 60)]), 100), (("wait", None, None), None))

    def test_seller_phases(self):
        d = duel(role="seller", L=60, msgs=[msg("you", 100, 100), msg("R", 103, 30)], rival_offer=_rival(103, 30))
        self.assertEqual(self.phase(d, 104)[1], "how")                     # 30 <= 60 / 1.5
        d = duel(role="seller", L=60, msgs=[msg("you", 100, 100), msg("R", 103, 50)], rival_offer=_rival(103, 50))
        self.assertEqual(self.phase(d, 104)[1], "move")

    def test_propose_variant_by_phase(self):
        from agent import talk
        d = duel(did=3, L=100, msgs=[msg("you", 100, 60)])                  # silent rival: ghost
        on = D.propose(make_world([d], 104), None, {}, {}, {})[0].args
        off = D.propose(make_world([d], 104), None, {}, {"voss_text": False}, {})[0].args
        self.assertEqual(on["variant"], D.PHASE_VARIANT["ghost"])
        self.assertEqual(off["variant"], 1 % len(talk.TEMPLATES["duel"]))   # legacy len(ours) % n
        self.assertEqual((on["price"], on["days"]), (off["price"], off["days"]))   # V1 is text only
        d2 = duel(did=4, L=100, issues=("price", "days"), w=2.0, meaning="m")
        out = D.propose(make_world([d2], 100), None, {"days_sign": 1}, {}, {})
        self.assertEqual((out[0].args["template"], out[0].args["variant"]), ("duel_days", D.PHASE_VARIANT["open"]))


class TestVossPrecise(unittest.TestCase):
    """V2: no multiples of 5 on our say prices when it costs nothing (ch6 / ch9)."""

    def test_off_keeps_round_anchor(self):
        self.assertEqual(D.decide(D.view(duel(L=100), 100), {}), ("say", 60, None))

    def test_on_shifts_anchor_toward_us(self):
        self.assertEqual(D.decide(D.view(duel(L=100), 100), {"precise": True}), ("say", 59, None))
        self.assertEqual(D.decide(D.view(duel(role="seller", L=60), 100), {"precise": True}), ("say", 101, None))

    def test_only_if_still_strict_concession(self):
        v = D.view(duel(L=100, msgs=[msg("you", 100, 59)]), 104)
        P = dict(D.DEFAULTS, precise=True)
        self.assertEqual(D._precise(v, P, ("say", 60, None)), ("say", 60, None))     # 59 would repeat
        self.assertEqual(D._precise(v, P, ("say", 65, None)), ("say", 64, None))
        self.assertEqual(D._precise(v, P, ("say", 66, None)), ("say", 66, None))     # not round: untouched

    def test_never_touches_accepts(self):
        d = duel(L=100, msgs=[msg("you", 104, 60), msg("R", 113, 80)], rival_offer=_rival(113, 80))
        self.assertEqual(D.decide(D.view(d, 113), {"precise": True}), ("accept", 80, None))

    def test_late_provoke_is_shifted_but_inside(self):
        d = duel(L=100, msgs=[msg("you", 104, 60), msg("R", 110, 80)], rival_offer=_rival(110, 80))
        self.assertEqual(D.decide(D.view(d, 114), {"precise": True}), ("say", 79, None))


class TestVossAckerman(unittest.TestCase):
    """V3: 65/85/95/100 % of the target (anchor 0.6 L, target 0.8 of the way to L-1 -> ~0.92 L), then hold."""

    def test_off_uses_curve(self):
        d = duel(L=100, msgs=[msg("you", 100, 60), msg("R", 103, 130)], rival_offer=_rival(103, 130))
        self.assertEqual(D.decide(D.view(d, 104), {}), ("say", 67, None))

    def test_schedule_then_hold_then_final(self):
        P = {"ackerman": True}
        msgs = [msg("you", 100, 60)]
        got = []
        for t_r, rp, t_us in ((103, 130, 104), (105, 125, 106), (107, 120, 108)):
            msgs.append(msg("R", t_r, rp))
            d = duel(L=100, msgs=msgs, rival_offer=_rival(t_r, rp))
            act, phase = D.decide_ex(D.view(d, t_us), P)
            self.assertEqual((act[0], phase), ("say", "move"))
            got.append(act[1])
            msgs.append(msg("you", t_us, act[1]))
        self.assertEqual(got, [77, 86, 91])                                 # raises 17, 9, 5: shrinking
        msgs.append(msg("R", 109, 118))
        d = duel(L=100, msgs=msgs, rival_offer=_rival(109, 118))
        for t in (110, 111):
            self.assertEqual(D.decide(D.view(d, t), P)[0], "wait", t)        # hold: silence is free
        act, phase = D.decide_ex(D.view(d, 112), P)                          # deadline - final: unchanged rule
        self.assertEqual((act, phase), (("say", 96, None), "final"))

    def test_seller_schedule(self):
        # seller L=60: anchor 100, Lm 61; first step ceil(100 - 0.8 * 20/35 * 39) = 83
        d = duel(role="seller", L=60, msgs=[msg("you", 100, 100), msg("R", 103, 50)], rival_offer=_rival(103, 50))
        self.assertEqual(D.decide(D.view(d, 104), {"ackerman": True}), ("say", 83, None))

    def test_skips_steps_already_reached(self):
        # the slow ascent already took us to 80 before the rival spoke: the next step is 86, not 77
        d = duel(L=100, msgs=[msg("you", 100, 60), msg("you", 104, 80), msg("R", 105, 130)],
                 rival_offer=_rival(105, 130))
        self.assertEqual(D.decide(D.view(d, 106), {"ackerman": True}), ("say", 86, None))

    def test_never_above_rival_ask(self):
        d = duel(L=100, msgs=[msg("you", 100, 60), msg("R", 103, 70)], rival_offer=_rival(103, 70))
        kind, p, _ = D.decide(D.view(d, 105), {"ackerman": True})
        self.assertEqual(kind, "say")
        self.assertLessEqual(p, 70)

    def test_with_precise_no_round_numbers(self):
        d = duel(L=200, msgs=[msg("you", 100, 120), msg("R", 103, 260)], rival_offer=_rival(103, 260))
        kind, p, _ = D.decide(D.view(d, 104), {"ackerman": True, "precise": True})
        self.assertEqual(kind, "say")
        self.assertNotEqual(p % 5, 0)


class TestVossPunch(unittest.TestCase):
    """V4: an unmoved or extreme rival gets 1 P (min) or silence (wait), never a full step."""

    @staticmethod
    def unmoved():
        return duel(L=100, msgs=[msg("you", 100, 60), msg("R", 101, 130), msg("you", 102, 67), msg("R", 103, 130)],
                    rival_offer=_rival(103, 130))

    @staticmethod
    def extreme():
        return duel(L=100, msgs=[msg("you", 100, 60), msg("R", 103, 160)], rival_offer=_rival(103, 160))

    def test_off_full_step(self):
        self.assertEqual(D.decide_ex(D.view(self.unmoved(), 104), {}), (("say", 71, None), "how"))
        self.assertEqual(D.decide_ex(D.view(self.extreme(), 104), {}), (("say", 67, None), "how"))

    def test_min(self):
        self.assertEqual(D.decide_ex(D.view(self.unmoved(), 104), {"punch": True}), (("say", 68, None), "how"))
        self.assertEqual(D.decide_ex(D.view(self.extreme(), 104), {"punch": True}), (("say", 61, None), "how"))

    def test_wait(self):
        P = {"punch": True, "punch_mode": "wait"}
        self.assertEqual(D.decide_ex(D.view(self.unmoved(), 104), P), (("wait", None, None), None))
        self.assertEqual(D.decide_ex(D.view(self.extreme(), 104), P), (("wait", None, None), None))

    def test_moving_rival_unaffected(self):
        d = duel(L=100, msgs=[msg("you", 100, 60), msg("R", 101, 130), msg("you", 102, 67), msg("R", 103, 125)],
                 rival_offer=_rival(103, 125))
        self.assertEqual(D.decide_ex(D.view(d, 104), {"punch": True}), D.decide_ex(D.view(d, 104), {}))
        self.assertEqual(D.decide_ex(D.view(d, 104), {})[1], "move")

    def test_seller_and_punch_x(self):
        d = duel(role="seller", L=60, msgs=[msg("you", 100, 100), msg("R", 103, 30)], rival_offer=_rival(103, 30))
        self.assertEqual(D.decide(D.view(d, 104), {"punch": True}), ("say", 99, None))
        # punch_x 1.0 -> threshold 30: still extreme; punch_x 2.0 -> threshold 20: not extreme -> full step
        self.assertEqual(D.decide(D.view(d, 104), {"punch": True, "punch_x": 1.0}), ("say", 99, None))
        self.assertEqual(D.decide(D.view(d, 104), {"punch": True, "punch_x": 2.0}), D.decide(D.view(d, 104), {}))
        self.assertNotEqual(D.decide(D.view(d, 104), {})[1], 99)

    def test_at_limit_no_message(self):
        d = duel(L=100, msgs=[msg("you", 100, 60), msg("R", 101, 130), msg("you", 102, 99), msg("R", 103, 130)],
                 rival_offer=_rival(103, 130))
        self.assertEqual(D.decide(D.view(d, 104), {"punch": True}), ("wait", None, None))

    def test_late_rules_unchanged(self):
        d = duel(L=100, msgs=[msg("you", 104, 60), msg("R", 110, 80)], rival_offer=_rival(110, 80))
        for P in ({"punch": True}, {"punch": True, "punch_mode": "wait"}, {"ackerman": True}):
            self.assertEqual(D.decide(D.view(d, 114), P), ("say", 80, None))


if __name__ == "__main__":
    unittest.main()
