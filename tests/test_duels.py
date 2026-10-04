"""M12 duels: INV-12 (0 prices outside the limit, monotone, accept only on the tick the rival spoke), J7, J10, E8, E16.

Uses an in-file DuelRival double (8 behaviours) instead of sim/bots.py, which belongs to M6b.
"""
from __future__ import annotations

import copy
import json
import random
import unittest

from tests import HARVEST
from agent.contracts import Limits, World
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


def run_episode(kind, role, decay, rng, cases, checker):
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
            act = D.decide(v, {})
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
        rng = random.Random(18)
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
                        r = run_episode(kind, role, decay, rng, cases, checker)
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
        # buyer L=100, start 100, deadline 116: anchor 60; the walk stops at slow_cap 0.8 of the way (60+0.8*39=91)
        d = duel(L=100, deadline=116)
        prices = {}
        for t in range(100, 116):
            kind, p, _ = D.decide(D.view(d, t), {})
            if kind == "say":
                d["messages"].append(msg("you", t, p))
                prices[t] = p
        self.assertEqual(prices[100], 60)
        self.assertEqual(max(prices.values()), 60 + round(0.8 * 39))
        self.assertEqual(prices[max(prices)], 60 + round(0.8 * 39))     # stays at the cap until the deadline
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
        # days_meaning is free text the Sensor never passes: the weight alone makes the duel playable
        self.assertEqual(D.decide(D.view(self.two(w=2.0, meaning=None), 100), {})[0], "say")

    def test_null_weight_uses_plan_fallback(self):
        # server sends your_days_weight null: silent unless plan duels.days_weight_fallback is set; buyer -> day 0
        d = self.two(L=100, w=None, meaning=None)
        self.assertEqual(D.decide(D.view(d, 100), {})[0], "wait")
        kind, p, days = D.decide(D.view(d, 100), {"days_weight_fallback": 1.0})
        self.assertEqual((kind, days), ("say", 0))
        self.assertLessEqual(p, 99)
        # a real server weight wins over the fallback
        ro = {"price": 80, "days": 5, "tick": 114, "id": 4}
        d3 = self.two(L=100, w=3.0, meaning=None, msgs=[msg("you", 100, 60, 5), msg("R", 114, 80, 5)], rival_offer=ro)
        self.assertEqual(D.decide(D.view(d3, 114), {"days_weight_fallback": 5.0})[0], "accept")   # 20 >= 1+15 (w=3)

    def test_server_meaning_gives_the_sign(self):
        # Duels II live: buyer "each delivery day costs you this much cash" -> day 0; seller "...adds ... to your side" -> 10
        from agent import talk
        cost = "each delivery day costs you this much cash"
        add = "each delivery day adds this much cash to your side"
        kind, p, days = D.decide(D.view(self.two(L=100, w=3.4, meaning=cost), 100), {})
        self.assertEqual((kind, days), ("say", 0))
        kind, p, days = D.decide(D.view(self.two(role="seller", L=79, w=1.98, meaning=add), 100), {})
        self.assertEqual((kind, days), ("say", 10))
        # the Gate uses the same rule: buyer at day 0 needs only the base margin, at day 10 it needs 1 + 34;
        # seller: days only add (value s*(p-L) + |w|*d, 44/44 Duels II deals) -> no days margin at any day
        self.assertEqual(talk._days_penalty({"your_days_weight": 3.4, "days_meaning": cost}, 0), 0.0)
        self.assertAlmostEqual(talk._days_penalty({"your_days_weight": 3.4, "days_meaning": cost}, 10), 34.0)
        self.assertEqual(talk._days_penalty({"your_days_weight": 2.0, "days_meaning": add}, 0), 0.0)
        self.assertEqual(talk._days_penalty({"your_days_weight": 2.0, "days_meaning": add}, 10), 0.0)
        self.assertAlmostEqual(talk._days_penalty({"your_days_weight": 2.0, "days_meaning": "?"}, 5), 10.0)

    def test_reworded_meaning_against_the_role_is_worst_case(self):
        # pre-Sunday review D1/S1: buyer L100 w6 with 'adds ... the price you pay' (parsed +1) used to give penalty 0:
        # accept 95@10 (true value 5 - 60 = -55) and say day 10 (Saturday's bug). The conflict now gives -1.
        m = "each delivery day adds this much to the price you pay"
        ro = {"price": 95, "days": 10, "tick": 114, "id": 3}
        d = self.two(L=100, w=6.0, meaning=m, msgs=[msg("you", 100, 60, 0), msg("R", 114, 95, 10)], rival_offer=ro)
        self.assertNotEqual(D.decide(D.view(d, 114), {})[0], "accept")
        kind, p, days = D.decide(D.view(self.two(L=100, w=5.0, meaning=m), 100), {})
        self.assertEqual((kind, days), ("say", 0))
        # a seller's reworded 'reduces' reading -1 also goes to the safe side: day 0 and |w|*d (not penalty 0)
        s = self.two(role="seller", L=60, w=2.0, meaning="each delivery day reduces the cash you receive")
        self.assertEqual(D.decide(D.view(s, 100), {})[2], 0)

    P3 = {"anchor": 0.62, "slow_cap": 0.85, "acc_late": 2, "e8_ticks": 0, "days_weight_fallback": 1.0}   # plan duels

    def test_silent_rival_with_other_days_gets_its_own_pair_back(self):
        # pre-Sunday review E2E-2 (sim drive3, duels 901/905): buyer L125 w5 (sign -1), ours 97/d0, the rival offers
        # 94/d5 (+6 for us) and goes silent. We used to wait to the deadline (no deal). Now by deadline-2 we send
        # (94, 5) back, the Gate passes it, and when the rival answers with it we accept.
        from agent import talk
        cost = "each delivery day costs you this much cash"
        dl = 116
        ro = {"price": 94, "days": 5, "tick": 105, "id": 3}
        d = self.two(L=125, w=5.0, meaning=cost, msgs=[msg("you", 104, 97, 0), msg("R", 105, 94, 5)],
                     rival_offer=ro)
        d.update(deadline_tick=dl, decay_per_round=0.10)
        got = None
        for t in range(106, dl):
            kind, p, days = D.decide(D.view(d, t), self.P3)
            if kind == "say":
                got = (t, p, days)
                break
        self.assertIsNotNone(got)
        self.assertLessEqual(got[0], dl - 2)
        self.assertEqual(got[1:], (94, 5))
        self.assertGreaterEqual(125 - 94, 1 + talk._days_penalty(d, 5))           # the Gate's margin: 31 >= 26
        d["messages"].append(msg("you", got[0], 94, 5))
        d["your_offer"] = {"price": 94, "days": 5, "tick": got[0], "id": 9}
        self.assertEqual(D.decide(D.view(d, got[0] + 1), self.P3)[0], "wait")          # no second echo
        d["messages"].append(msg("R", got[0] + 1, 94, 5))
        d["rival_offer"] = {"price": 94, "days": 5, "tick": got[0] + 1, "id": 4}
        self.assertEqual(D.decide(D.view(d, got[0] + 1), self.P3), ("accept", 94, 5))

    def test_unknown_text_falls_back_by_role(self):
        # pre-Sunday audit: an unrecognised days_meaning no longer means "day 5 + worst case" (0/7 deals in Duels II):
        # the sign comes from the role (buyer -1, seller +1), the same in tactic and Gate (talk.days_sign_of)
        d = self.two(L=100, w=3.0, meaning="delivery days", msgs=[msg("you", 100, 60, 0)])
        for t in range(101, 116):
            kind, p, days = D.decide(D.view(d, t), {})
            if kind == "say":
                self.assertEqual(days, 0)
                self.assertLessEqual(p, 99)
                d["messages"].append(msg("you", t, p, days))
                d["your_offer"] = {"price": p, "days": days, "tick": t, "id": 9}
        for rd, want in ((0, True), (5, True), (10, False)):                 # 20 >= 1 + 3*rd ?
            ro = {"price": 80, "days": rd, "tick": 114, "id": 3}
            d2 = self.two(L=100, w=3.0, meaning="m", msgs=[msg("you", 100, 60, 0), msg("R", 114, 80, rd)],
                          rival_offer=ro)
            self.assertEqual(D.decide(D.view(d2, 114), {})[0] == "accept", want, rd)
        s = self.two(role="seller", L=60, w=2.0, meaning="zzz")
        self.assertEqual(D.decide(D.view(s, 100), {})[2], 10)

    def test_default_T_by_decay(self):
        self.assertEqual(D._default_T(0.06), 16)
        self.assertEqual(D._default_T(0.08), 16)     # Duels II: duel_ticks 16
        self.assertEqual(D._default_T(0.10), 12)     # Sunday: duel_ticks 12

    def test_accept_when_rival_retreats_inside_limit(self):
        # D2304: rival came to 135 (inside L=167), we countered, it moved back up to 140: accept, do not chase
        d = duel(L=167, msgs=[msg("you", 100, 108), msg("R", 100, 187), msg("you", 102, 124), msg("R", 103, 135),
                              msg("you", 104, 132), msg("R", 105, 140)],
                 rival_offer={"price": 140, "days": 0, "tick": 105, "id": 9})
        self.assertEqual(D.decide(D.view(d, 105), {"anchor": 0.65}), ("accept", 140, 0))
        ro = {"price": 69, "days": 5, "tick": 114, "id": 3}
        d3 = self.two(L=100, w=3.0, meaning="m", msgs=[msg("you", 100, 60, 0), msg("R", 114, 69, 5)], rival_offer=ro)
        self.assertEqual(D.decide(D.view(d3, 114), {})[0], "accept")

    def test_sign_known_best_days(self):
        kind, p, days = D.decide(D.view(self.two(role="seller", L=60, w=2.0, meaning="m"), 100), {})
        self.assertEqual((kind, days), ("say", 10))
        kind, p, days = D.decide(D.view(self.two(L=100, w=2.0, meaning="m"), 100), {})
        self.assertEqual((kind, days), ("say", 0))
        # buyer, rival 85 with 10 days, w 2: each day costs 2 -> 15 < 1 + 20 -> no accept
        ro = {"price": 85, "days": 10, "tick": 114, "id": 3}
        d = self.two(L=100, w=2.0, meaning="m", msgs=[msg("you", 100, 60, 0), msg("R", 114, 85, 10)], rival_offer=ro)
        self.assertNotEqual(D.decide(D.view(d, 114), {})[0], "accept")
        ro = {"price": 75, "days": 10, "tick": 114, "id": 4}
        d = self.two(L=100, w=2.0, meaning="m", msgs=[msg("you", 100, 60, 0), msg("R", 114, 75, 10)], rival_offer=ro)
        self.assertEqual(D.decide(D.view(d, 114), {})[0], "accept")          # 25 >= 1 + 20

    def test_seller_days_credit_replays(self):
        # Duels II misses (pre-Sunday audit, recon/duels_done.json): seller 6173 L60 w6.35 rival 89 P at 0 days on
        # deadline-1 was worth 29 but needed 1 + 63.5; buyer 5730 L117 rival 89/0 (surplus 28) needed 53.3.
        ro = {"price": 89, "days": 0, "tick": 115, "id": 3}
        d = self.two(role="seller", L=60, w=6.35, meaning="each delivery day adds this much cash to your side",
                     msgs=[msg("you", 100, 100, 10), msg("R", 115, 89, 0)], rival_offer=ro)
        self.assertEqual(D.decide(D.view(d, 115), {}), ("accept", 89, 0))
        b = self.two(L=117, w=5.33, meaning=None, msgs=[msg("you", 100, 70, 0), msg("R", 115, 89, 0)],
                     rival_offer={"price": 89, "days": 0, "tick": 115, "id": 4})
        self.assertEqual(D.decide(D.view(b, 115), {}), ("accept", 89, 0))
        # a seller never goes below its limit, whatever the days pay (price floor)
        lo = self.two(role="seller", L=60, w=6.35, meaning=None,
                      msgs=[msg("you", 100, 100, 10), msg("R", 115, 59, 10)],
                      rival_offer={"price": 59, "days": 10, "tick": 115, "id": 5})
        self.assertNotEqual(D.decide(D.view(lo, 115), {})[0], "accept")

    def test_accept_ranks_offers_with_days(self):
        # buyer L120 w3, our standing 80@0 (value 40); rival 79@10 is cheaper but worth 41 - 30 = 11: not "good"
        ro = {"price": 79, "days": 10, "tick": 102, "id": 3}
        d = self.two(L=120, w=3.0, msgs=[msg("you", 100, 72, 0), msg("you", 101, 80, 0), msg("R", 102, 79, 10)],
                     rival_offer=ro)
        self.assertNotEqual(D.decide(D.view(d, 102), {})[0], "accept")
        # the same price at 0 days is worth 41 >= 40: accepted
        ro0 = {"price": 79, "days": 0, "tick": 102, "id": 4}
        d0 = self.two(L=120, w=3.0, msgs=[msg("you", 100, 72, 0), msg("you", 101, 80, 0), msg("R", 102, 79, 0)],
                      rival_offer=ro0)
        self.assertEqual(D.decide(D.view(d0, 102), {})[0], "accept")

    def test_fuzz_two_issue_value_never_below_one(self):
        # every say and accept has true value s*(p-L) + sign*|w|*d >= 1 and a price inside the limit
        import random
        rnd = random.Random(44)
        n = 0
        for _ in range(3000):
            role = rnd.choice(("buyer", "seller"))
            L, w = rnd.randint(20, 160), round(rnd.uniform(0.2, 7.0), 2)
            s, sign = (1, 1) if role == "seller" else (-1, -1)
            t0, dl = 100, 112
            rp, rd = rnd.randint(1, 250), rnd.randint(0, 10)
            tick = rnd.randint(t0 + 1, dl - 1)
            msgs = [msg("you", t0, L + s * rnd.randint(5, 60), 10 if sign > 0 else 0), msg("R", tick, rp, rd)]
            d = self.two(role=role, L=L, w=w, deadline=dl, decay=0.1, msgs=msgs,
                         rival_offer={"price": rp, "days": rd, "tick": tick, "id": 1})
            kind, p, days = D.decide(D.view(d, tick), {})
            if kind in ("accept", "say"):
                n += 1
                self.assertGreaterEqual(s * (p - L), 1, (role, L, w, kind, p, days))
                self.assertGreaterEqual(s * (p - L) + sign * w * days, 1, (role, L, w, kind, p, days))
        self.assertGreater(n, 500)

    def test_missing_rival_days_not_accepted(self):
        ro = {"price": 50, "days": None, "tick": 114, "id": 3}
        d = self.two(L=100, w=2.0, meaning="m", msgs=[msg("you", 100, 40, 0), msg("R", 114, 50)], rival_offer=ro)
        self.assertNotEqual(D.decide(D.view(d, 114), {})[0], "accept")


class TestPropose(unittest.TestCase):
    def test_accept_budget_by_deadline(self):
        ds = []
        for did, dl in ((1, 120), (2, 116), (3, 118)):
            ds.append(dict(duel(did=did, L=100, deadline=dl, msgs=[msg("you", 104, 60), msg("R", 115, 70)],
                                rival_offer={"price": 70, "days": None, "tick": 115, "id": did}), rounds=1))
        st = {}
        out = D.propose(make_world(ds, 115), None, {"days_sign": None}, {}, st)
        acc = [i for i in out if i.kind == "duel_accept"]
        self.assertEqual([i.args["duel_id"] for i in acc], [2])
        self.assertEqual(acc[0].args["fingerprint"], D.view(ds[1], 115).fingerprint)
        # pre-Sunday review D3: the accept beyond the budget (duel 3) gets the rival's price back as a say (it uses no
        # accept); duel 1 is held by E8 and says nothing
        self.assertEqual(sorted((i.args["duel_id"], i.args["price"]) for i in out if i.kind == "duel_say"),
                         [(3, 70)])
        self.assertFalse(any(i.kind == "duel_say" and i.args["duel_id"] == 2 for i in out))
        self.assertEqual(st["duel_accepts"][2]["price"], 70)
        self.assertAlmostEqual(acc[0].prediction.duel, 30 * 0.94 ** 1, places=1)
        self.assertEqual(acc[0].prediction.model, "U-01")
        # zero accept budget -> no duel_accept
        out0 = D.propose(make_world(ds, 115, accepts=0), None, {}, {}, {})
        self.assertFalse(any(i.kind == "duel_accept" for i in out0))

    def test_skipped_two_issue_accept_echoes_the_rival_pair(self):
        # four duels on one deadline (Sunday max_concurrent 4) and one accept per tick: the three skipped ones send
        # the rival's (price, days) back; each passes the Gate's margin with its days
        from agent import talk
        cost = "each delivery day costs you this much cash"
        ds = []
        for did in (1, 2, 3, 4):
            ds.append(dict(duel(did=did, L=100, deadline=118, decay=0.1, issues=("price", "days"), w=2.0,
                                meaning=cost, msgs=[msg("you", 108, 60, 0), msg("R", 115, 80, 3)],
                                rival_offer={"price": 80, "days": 3, "tick": 115, "id": did}), rounds=1))
        out = D.propose(make_world(ds, 115), None, {}, {}, {})
        self.assertEqual([i.args["duel_id"] for i in out if i.kind == "duel_accept"], [1])
        says = [i for i in out if i.kind == "duel_say"]
        self.assertEqual(sorted((i.args["duel_id"], i.args["price"], i.args["days"]) for i in says),
                         [(2, 80, 3), (3, 80, 3), (4, 80, 3)])
        for i in says:
            self.assertGreaterEqual(100 - i.args["price"], 1 + talk._days_penalty(ds[0], i.args["days"]))

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
        # audit Sat: the pause is per duel (G51 re-reads + fingerprints before any accept); other duels still accept
        self.assertNotIn("duel_accepts_paused", st)
        d2 = duel(did=6, L=100, deadline=116, msgs=[msg("you", 104, 60), msg("R", 114, 70)],
                  rival_offer={"price": 70, "days": None, "tick": 114, "id": 3})
        self.assertTrue(any(i.kind == "duel_accept" for i in D.propose(make_world([d2], 114), None, {}, {}, st)))

    def test_opening_never_worse_than_rival(self):
        # audit Sat: rival already asks 55 (buyer, L=100, anchor 60): we open at 55, not at the anchor (G50 refused)
        d = duel(did=7, L=100, deadline=116, msgs=[msg("R", 103, 55)],
                 rival_offer={"price": 55, "days": None, "tick": 103, "id": 4})
        act = D.decide(D.view(d, 105), {})
        self.assertEqual(act[0], "say")
        self.assertLessEqual(act[1], 55)

    def test_e16_settled_price(self):
        st = {"duel_accepts": {8: {"tick": 114, "price": 70, "days": None}}}
        self.assertIsNone(D.e16_settled(st, [{"duel": 8, "status": "deal", "price": 70, "your_offer": {"price": 66}}]))
        st = {"duel_accepts": {8: {"tick": 114, "price": 70, "days": None}}}
        self.assertTrue(D.e16_settled(st, [{"duel": 8, "status": "deal", "price": 75, "your_offer": {"price": 66}}]))


class TestCrossModule(unittest.TestCase):
    def test_fingerprint_matches_guards(self):
        from agent.guards import duel_fingerprint
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


if __name__ == "__main__":
    unittest.main()


class TestLiveReviewFixes(unittest.TestCase):
    """Sat 3 Oct review before Duels I: text-only rival messages, repeated rival prices."""

    def test_text_only_rival_message_does_not_freeze(self):
        d = duel(L=100, deadline=116, msgs=[msg("you", 100, 75), {"tick": 101, "from": "R", "text": "hola", "price": None,
                                                                   "days": None}])
        v = D.view(d, 102)
        self.assertTrue(v.ok, v.why)

    def test_no_concession_to_a_repeated_price(self):
        d = duel(L=100, deadline=116, msgs=[msg("you", 100, 75), msg("R", 101, 150), msg("you", 102, 80),
                                            msg("R", 103, 150)],
                 rival_offer={"price": 150, "days": None, "tick": 103, "id": 9})
        self.assertEqual(D.decide(D.view(d, 104), {})[0], "wait")


class TestGateConsistency(unittest.TestCase):
    """Sat review (Duels II): the tactic sends only what the Gate (talk G50/G51, gate G07) lets through."""

    def test_days_margin_is_the_gates_with_sign_known(self):
        from agent.talk import _days_penalty
        n = 0
        for sign in (1, -1):
            for t in range(101, 115):
                d = duel(issues=("price", "days"), L=100, w=2.0, meaning="m",
                         msgs=[msg("you", 100, 60, 10 if sign > 0 else 0)])
                kind, p, days = D.decide(D.view(d, t), {"days_sign": sign})
                if kind == "say":
                    n += 1
                    self.assertGreaterEqual(100 - p, 1 + _days_penalty(d, days), (sign, t, p, days))
        self.assertGreater(n, 0)
        # accept: the rival's days are charged the Gate's worst case too (talk G51)
        ro = {"price": 85, "days": 10, "tick": 114, "id": 3}
        d = duel(issues=("price", "days"), L=100, w=2.0, meaning="m", msgs=[msg("you", 100, 60, 10),
                                                                             msg("R", 114, 85, 10)], rival_offer=ro)
        self.assertNotEqual(D.decide(D.view(d, 114), {"days_sign": 1})[0], "accept")    # 15 < 1 + 20

    def test_server_sign_margin_is_the_gates(self):
        # merged build: with the SERVER's sign (days_meaning, or the sensor's days_sign) tactic and Gate both
        # charge the loss vs our best days, not the worst case; the plan sign alone keeps the worst case
        from agent.talk import _days_penalty
        cost = "each delivery day costs you this much cash"
        for srv in ({"meaning": cost}, {"meaning": None}):
            def two(msgs, ro=None):
                d = duel(issues=("price", "days"), L=100, w=2.0, msgs=msgs, rival_offer=ro, **srv)
                if srv["meaning"] is None:
                    d["days_sign"] = -1                                   # World shape: only the derived sign
                return d
            for t in range(101, 115):
                d = two([msg("you", 100, 60, 0)])
                kind, p, days = D.decide(D.view(d, t), {})
                if kind == "say":
                    self.assertEqual(days, 0)
                    self.assertGreaterEqual(100 - p, 1 + _days_penalty(d, days), (srv, t, p))
            ro = {"price": 85, "days": 0, "tick": 114, "id": 3}
            d = two([msg("you", 100, 60, 0), msg("R", 114, 85, 0)], ro)
            self.assertEqual(_days_penalty(d, 0), 0.0)
            self.assertEqual(D.decide(D.view(d, 114), {})[0], "accept")               # 15 >= 1 + 0
            ro = {"price": 85, "days": 10, "tick": 114, "id": 4}
            d = two([msg("you", 100, 60, 0), msg("R", 114, 85, 10)], ro)
            self.assertNotEqual(D.decide(D.view(d, 114), {})[0], "accept")            # 15 < 1 + 20
        # server silent: the role gives the sign (buyer -1) in both tactic and Gate -> day 0 costs nothing
        ro = {"price": 85, "days": 0, "tick": 114, "id": 5}
        d = duel(issues=("price", "days"), L=100, w=2.0, meaning="m",
                 msgs=[msg("you", 100, 60, 0), msg("R", 114, 85, 0)], rival_offer=ro)
        self.assertEqual(_days_penalty(d, 0), 0.0)
        self.assertEqual(D.decide(D.view(d, 114), {})[0], "accept")

    def test_float_limit_is_read_inside(self):
        b = D.view(duel(role="buyer", L=100.0), 100)
        self.assertTrue(b.ok, b.why)
        self.assertEqual(b.limit, 100)
        self.assertEqual(D.view(duel(role="buyer", L=100.7), 100).limit, 100)       # floor for a buyer
        self.assertEqual(D.view(duel(role="seller", L=100.2), 100).limit, 101)      # ceil for a seller
        # the prediction uses the raw limit, as the Gate's G07 recompute does
        d = duel(L=100.5, msgs=[msg("you", 104, 60), msg("R", 115, 70)],
                 rival_offer={"price": 70, "days": None, "tick": 115, "id": 1})
        acc = [i for i in D.propose(make_world([d], 115), None, {}, {}, {}) if i.kind == "duel_accept"]
        self.assertEqual(len(acc), 1)
        self.assertAlmostEqual(acc[0].prediction.duel, 30.5, places=6)               # server rounds 0

    def test_never_resends_our_own_price(self):
        d = duel(L=100, deadline=116, msgs=[msg("you", 104, 60), msg("R", 110, 80), msg("you", 112, 80)],
                 rival_offer={"price": 80, "days": None, "tick": 110, "id": 5})
        v = D.view(d, 114)
        self.assertEqual(D._final_guard(v, dict(D.DEFAULTS), ("say", 80, None)), ("wait", None, None))
        self.assertEqual(D.decide(v, {}), ("wait", None, None))
        two = duel(issues=("price", "days"), L=100, w=1.0, meaning="m", msgs=[msg("you", 104, 60, 5)])
        v2 = D.view(two, 106)
        self.assertEqual(D._final_guard(v2, dict(D.DEFAULTS), ("say", 60, 5))[0], "wait")
        self.assertEqual(D._final_guard(v2, dict(D.DEFAULTS), ("say", 60, 4))[0], "say")   # other days: not a repeat

    def test_rounds_from_server(self):
        d = dict(duel(L=100, msgs=[msg("you", 104, 60), msg("R", 115, 70)],
                      rival_offer={"price": 70, "days": None, "tick": 115, "id": 1}), rounds=3)
        self.assertEqual(D.view(d, 115).rounds, 3)
        acc = [i for i in D.propose(make_world([d], 115), None, {}, {}, {}) if i.kind == "duel_accept"]
        self.assertAlmostEqual(acc[0].prediction.duel, 30 * 0.94 ** 3, places=6)
        self.assertEqual(D.view(dict(d, rounds=None), 115).rounds, 1)                 # fallback: min(ours, rivals)
