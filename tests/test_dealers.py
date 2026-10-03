"""M10 dealers: next_price, DealerState.rebuild and propose against in-file AbuelaBot / ChatoBot (D-02..D-10).

agent.valuation (M3) and agent.guards (M4a) are replaced by small in-file doubles via sys.modules for determinism.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
import types
import unittest
from types import MappingProxyType
from unittest import mock

from agent.contracts import FRIDAY, TEAM, Book, Need, Prediction, World
from agent.tactics import dealers as D


# ------------------------------------------------------------------------------------- module doubles

def _fake_valuation():
    m = types.ModuleType("agent.valuation")

    def predict_dealer(dv, price, side):
        g = (dv - price) if side == "buy" else (price - dv)
        return Prediction(min(0.0, g), min(0.0, g), ">=0" if g > 0 else "0", -price if side == "buy" else price,
                          model="P-04")

    def predict_none(model="none"):
        return Prediction(0.0, 0.0, "0", 0, model=model)
    m.predict_dealer, m.predict_none = predict_dealer, predict_none
    return m


def _fake_guards():
    m = types.ModuleType("agent.guards")
    m.fingerprint = lambda o: hashlib.sha1(json.dumps(dict(o), sort_keys=True, default=str).encode()).hexdigest()
    return m


class FakeValuer:
    def __init__(self, values, closers=()):
        self.values, self.closers = values, set(closers)

    def delta_add(self, counts, ref, packs=(), minted=None):
        return self.values[ref]

    def closes_page(self, counts, ref):
        return ref in self.closers


class Cfg:
    DEALER_MARGIN = 1.0
    THREADS_MARGIN = 1
    ALLOW_DEALER_CLOSE = frozenset({"LAT"})


CATALOG = {"sets": [{"id": "RET", "cards": [
    {"id": "RET-02", "rarity": "common"}, {"id": "RET-06", "rarity": "uncommon"},
    {"id": "RET-08", "rarity": "uncommon"}, {"id": "RET-09", "rarity": "rare"}, {"id": "RET-10", "rarity": "rare"}]},
    {"id": "LAT", "cards": [{"id": "LAT-09", "rarity": "rare"}]}]}

PLAN = {"profiles": {
    "RET-09": {"dealer": "chato", "anchor": 70, "step": 4, "limit": 90},
    "RET-08": {"dealer": "chato", "anchor": 13, "step": 1, "limit": 31, "fallback_after": 10},
    "uncommon": {"dealer": "abuela", "anchor": 16, "step": 2, "limit": 25},
    "common": {"dealer": "abuela", "anchor": 7, "step": 1, "limit": 11}},
    "dealer_max": {}}

VALUES = {"RET-02": 13.0, "RET-06": 32.5, "RET-08": 32.5, "RET-09": 91.0, "RET-10": 91.0, "LAT-09": 63.0}


def make_world(tick=10, threads=None, duels=(), down=frozenset(), unlocked=("abuela", "chato")):
    return World(tick=tick, t_hours=10.0, round=1, tick_seconds=60.0, tick_deadline=1e12, clock={}, limits=FRIDAY,
                 reading="N", me={"unlocked": list(unlocked), "cash": 400}, my_offers=(), offers_to_us=(), board=(),
                 own_pseudonym=None, threads=threads or {}, foreign_threads=(), duels=tuple(duels), catalog=CATALOG,
                 schedule={}, released_sets=frozenset({"RET"}), feed_new=(), server_values={}, down=down)


def make_book(**kw):
    base = dict(cash=400, cash_free=400, held={}, listed={}, pending_out={}, pending_in={}, projected={}, keep={},
                listed_assets=frozenset(), own_offer_ids=frozenset(), own_bids={}, bid_price={}, bid_band={},
                paths={}, thread_limit={}, thread_prices={}, thread_ref={}, thread_by_dealer={}, dealer_block={},
                dealer_deals_hour={}, packs=(), needs={}, frozen_closer={}, protect_sets=frozenset({"RET"}),
                delivery_risk=False, recent_rastro={}, unknown_domains=frozenset(), valuation_ok=True)
    base.update(kw)
    return Book(**base)


def need(ref, source, max_price=100, closer=False):
    return Need(set=ref.split("-")[0], ref=ref, source=source, max_price=max_price, closer=closer)


def dealer_offer(oid, dealer, ref, price, tick, final=False, status="open"):
    return {"id": oid, "maker": dealer, "to": TEAM, "venue": None, "status": status, "final": final,
            "give": {"cash": 0, "assets": [], "types": [f"card:{ref}"]}, "want": {"cash": price, "assets": [], "types": []},
            "created_tick": tick, "expires_tick": tick + 2}


def own_offer(oid, dealer, ref, price, tick, status="open"):
    return {"id": oid, "maker": TEAM, "to": dealer, "venue": None, "status": status, "final": False,
            "give": {"cash": price, "assets": [], "types": []}, "want": {"cash": 0, "assets": [], "types": [f"card:{ref}"]},
            "created_tick": tick, "expires_tick": tick + 2}


# --------------------------------------------------------------------------------------------- bots

class AbuelaBot:
    """D-02..D-07: no concession unless we raised; first cut 3-4 then ~1 per round; final in her 5th-7th offer,
    at most 1 below the previous; accepts ours within 1 P of hers if >= floor; leaves on a counter below a final."""

    def __init__(self, opening, floor, rng):
        self.price, self.floor, self.n = opening, floor, 1
        self.final_at, self.first_cut = rng.randint(5, 7), rng.randint(3, 4)
        self.final, self.last_team = False, None

    def on_team(self, p):
        if self.last_team is not None and p == self.last_team:
            return ("leave", "manners")
        if self.final and p < self.price:
            return ("leave", "not today")
        if p >= self.floor and self.price - p <= 1:
            return ("deal", p)
        raised = self.last_team is None or p > self.last_team
        self.last_team = p
        if raised:
            cut = self.first_cut if self.n == 1 else 1
            self.price = max(self.floor, self.price - cut)
            self.n += 1
            if self.n >= self.final_at or self.price == self.floor:
                self.final = True
        return ("offer", self.price, self.final)


class ChatoBot:
    """D-09/D-10: never concedes more than our last step; ramp min(step, k-1); finals 90-93 for rares."""

    def __init__(self, opening, floor, rng):
        self.price, self.floor, self.n = opening, floor, 1
        self.final_at = rng.randint(5, 7)
        self.final, self.last_team = False, None

    def on_team(self, p):
        if self.last_team is not None and p == self.last_team:
            return ("leave", "manners")
        if self.final and p < self.price:
            return ("leave", "not today")
        if p >= self.floor and p >= self.price:
            return ("deal", p)
        step = 0 if self.last_team is None else max(0, p - self.last_team)
        self.last_team = p
        self.price = max(self.floor, self.price - min(step, self.n - 1))
        self.n += 1
        if self.n >= self.final_at or self.price == self.floor:
            self.final = True
        return ("offer", self.price, self.final)


class Sim:
    """Applies dealer intents as the server would (one tick at a time) and rebuilds World + Book."""

    def __init__(self, bot_factory, needs, values=VALUES, plan=PLAN, duels=()):
        self.tick, self.threads, self.bots, self.next_id = 10, {}, {}, 1000
        self.bot_factory, self.needs, self.plan, self.duels = bot_factory, needs, plan, duels
        self.valuer = FakeValuer(values)
        self.limits, self.prices, self.deals, self.intents, self.journal_rows = {}, {}, [], [], []

    def _oid(self):
        self.next_id += 1
        return self.next_id

    def world(self):
        return make_world(self.tick, {tid: json.loads(json.dumps(t)) for tid, t in self.threads.items()},
                          duels=self.duels)

    def book(self):
        open_by = {t["with"]: tid for tid, t in self.threads.items() if t["status"] == "open"}
        return make_book(thread_limit=dict(self.limits), thread_prices={k: tuple(v) for k, v in self.prices.items()},
                         thread_by_dealer=open_by)

    def _expire_open(self, t):
        for m in t["messages"]:
            if m["offer"]["status"] == "open":
                m["offer"]["status"] = "expired"
        t["standing_offers"] = []

    def apply(self, it):
        a = it.args
        self.intents.append(it)
        if it.kind == "open_thread":
            tid = len(self.threads) + 1
            bot = self.bot_factory(a["dealer"], a["ref"])
            t = {"id": tid, "with": a["dealer"], "team": TEAM, "topic": {"buy": {"card": a["ref"]}}, "status": "open",
                 "created_tick": self.tick, "messages": [], "standing_offers": []}
            o = dealer_offer(self._oid(), a["dealer"], a["ref"], bot.price, self.tick)
            t["messages"].append({"id": self._oid(), "tick": self.tick, "sender": a["dealer"], "offer": o})
            t["standing_offers"] = [o]
            self.threads[tid], self.bots[tid], self.limits[tid] = t, bot, a["limit"]
            self.journal_rows.append({"kind": "intent", "tick": self.tick, "tactic": "dealers", "args": dict(a),
                                      "experiment": it.experiment})
        elif it.kind == "say":
            t, bot = self.threads[a["thread_id"]], self.bots[a["thread_id"]]
            self.prices.setdefault(a["thread_id"], []).append(a["price"])
            self._expire_open(t)
            mine = own_offer(self._oid(), t["with"], a["ref"], a["price"], self.tick)
            t["messages"].append({"id": self._oid(), "tick": self.tick, "sender": TEAM, "offer": mine})
            r = bot.on_team(a["price"])
            if r[0] == "deal":
                mine["status"] = "settled"
                t["status"] = "deal"
                self.deals.append((a["ref"], r[1], t["with"]))
            elif r[0] == "leave":
                mine["status"] = "cancelled"
                t["status"] = "closed"
            else:
                o = dealer_offer(self._oid(), t["with"], a["ref"], r[1], self.tick, final=r[2])
                t["messages"].append({"id": self._oid(), "tick": self.tick, "sender": t["with"], "offer": o})
                t["standing_offers"] = [o]
        elif it.kind == "accept":
            t = self.threads[a["thread_id"]]
            st = t["standing_offers"]
            assert st and st[0]["id"] == a["offer_id"] and st[0]["want"]["cash"] == a["price"], "accepted a stale offer"
            st[0]["status"] = "settled"
            t["status"] = "deal"
            self.deals.append((a["ref"], a["price"], t["with"]))
        elif it.kind == "close_thread":
            self.threads[a["thread_id"]]["status"] = "closed"
            self._expire_open(self.threads[a["thread_id"]])

    def run(self, ticks=40):
        for _ in range(ticks):
            w, b = self.world(), self.book()
            st = D.DealerState.rebuild(w, FakeJournal(self.journal_rows))
            its = D.propose(w, b, self.valuer, Cfg(), self.plan, self.needs, st)
            per_thread = {}
            for it in its:
                tid = it.args.get("thread_id")
                if tid is not None:
                    per_thread[tid] = per_thread.get(tid, 0) + 1
            assert all(v == 1 for v in per_thread.values()), "more than one step per thread and tick"
            for it in its:
                self.apply(it)
            self.tick += 1
            if not any(t["status"] == "open" for t in self.threads.values()) and self.threads:
                break
        return self


class FakeJournal:
    def __init__(self, rows):
        self._rows = rows

    def rows(self, kinds=None):
        return iter([r for r in self._rows if kinds is None or r["kind"] in kinds])


class Base(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(sys.modules, {"agent.valuation": _fake_valuation(), "agent.guards": _fake_guards()})
        p.start()
        self.addCleanup(p.stop)


# -------------------------------------------------------------------------------------------- tests

class NextPriceTest(unittest.TestCase):
    PROF = {"anchor": 16, "step": 2}

    def test_linear_from_anchor(self):
        self.assertEqual([D.next_price(self.PROF, k, None, 25) for k in range(3)], [16, 18, 20])

    def test_at_least_last_plus_one_and_capped(self):
        self.assertEqual(D.next_price(self.PROF, 1, 30, 40), 31)
        self.assertEqual(D.next_price(self.PROF, 10, 24, 25), 25)
        self.assertLessEqual(D.next_price(self.PROF, 10, 25, 25), 25)     # no room: caller must close

    def test_rejects_bad_profiles(self):
        for bad in ({"anchor": 0}, {"anchor": "16"}, {"anchor": 16, "step": 0}, {"anchor": True}, {}):
            with self.assertRaises(ValueError):
                D.next_price(bad, 0, None, 25)


class BotsTest(Base):
    def _abuela(self, floor, limit, seed):
        rng = random.Random(seed)
        plan = json.loads(json.dumps(PLAN))
        plan["profiles"]["uncommon"]["limit"] = limit
        return Sim(lambda d, r: AbuelaBot(29, floor, rng), [need("RET-06", "abuela")], plan=plan).run()

    def _assert_monotone(self, sim):
        for tid, ps in sim.prices.items():
            self.assertEqual(ps, sorted(set(ps)), f"thread {tid}: prices repeated or not strictly rising {ps}")
            self.assertTrue(all(p <= sim.limits[tid] for p in ps))

    def test_abuela_buys_when_final_within_limit(self):
        for seed in range(30):
            floor = random.Random(seed).randint(21, 25)
            sim = self._abuela(floor, 25, seed)
            self.assertEqual(len(sim.deals), 1, f"seed {seed} floor {floor}: {sim.deals}")
            self.assertLessEqual(sim.deals[0][1], 25)
            self._assert_monotone(sim)

    def test_abuela_final_above_limit_closes_without_accepting(self):
        for seed in range(30):
            sim = self._abuela(random.Random(seed).randint(23, 25), 22 - (seed % 3), seed)
            self.assertEqual(sim.deals, [], f"seed {seed}")
            self.assertFalse(any(it.kind == "accept" for it in sim.intents))
            self.assertTrue(all(t["status"] == "closed" for t in sim.threads.values()))
            self._assert_monotone(sim)

    def test_chato_rare(self):
        finals_in_reach = 0
        for seed in range(40):
            rng = random.Random(seed)
            floor = rng.randint(88, 93)
            sim = Sim(lambda d, r: ChatoBot(97, floor, rng), [need("RET-09", "chato")]).run(60)
            self._assert_monotone(sim)
            accepts = [it for it in sim.intents if it.kind == "accept"]
            self.assertTrue(all(it.args["price"] <= 90 for it in accepts))
            bot = sim.bots[1]
            if floor > 90 or (bot.final and bot.price > 90):
                self.assertEqual(sim.deals, [], f"seed {seed} floor {floor}")
                self.assertTrue(all(t["status"] == "closed" for t in sim.threads.values()))
            if bot.final and bot.price <= 90:
                self.assertEqual(len(sim.deals), 1, f"seed {seed} floor {floor}")
            for _, price, _ in sim.deals:
                self.assertLessEqual(price, 90)
            finals_in_reach += bool(sim.deals)
        self.assertGreater(finals_in_reach, 0)

    def test_never_repeats_price_across_reopen(self):
        rng = random.Random(7)
        sim = Sim(lambda d, r: AbuelaBot(29, 25, rng), [need("RET-06", "abuela", max_price=22)]).run(80)
        self.assertEqual(sim.deals, [])
        self._assert_monotone(sim)
        self.assertLessEqual(len(sim.threads), D.WALKS_PER_HOUR)          # reopen at most once per hour


class ProposeUnitTest(Base):
    def _thread(self, dealer, ref, msgs, standing, status="open", created=5):
        return {"id": 7, "with": dealer, "team": TEAM, "topic": {"buy": {"card": ref}}, "status": status,
                "created_tick": created, "messages": msgs, "standing_offers": standing}

    def _step(self, thread, needs, book=None, **wkw):
        w = make_world(threads={7: thread}, **wkw)
        b = book or make_book(thread_limit={7: 25}, thread_by_dealer={thread["with"]: 7})
        return D.propose(w, b, FakeValuer(VALUES), Cfg(), PLAN, needs, D.DealerState.rebuild(w, None))

    def _haggled(self, her_price, final=False):
        msgs = [{"id": 1, "tick": 6, "sender": "abuela", "offer": dealer_offer(1, "abuela", "RET-06", 29, 6, status="expired")},
                {"id": 2, "tick": 7, "sender": TEAM, "offer": own_offer(2, "abuela", "RET-06", 16, 7, "cancelled")},
                {"id": 3, "tick": 7, "sender": "abuela", "offer": dealer_offer(3, "abuela", "RET-06", 25, 7, status="expired")},
                {"id": 4, "tick": 8, "sender": TEAM, "offer": own_offer(4, "abuela", "RET-06", 18, 8, "cancelled")}]
        o = dealer_offer(5, "abuela", "RET-06", her_price, 9, final=final)
        msgs.append({"id": 5, "tick": 9, "sender": "abuela", "offer": o})
        return self._thread("abuela", "RET-06", msgs, [o])

    def test_accepts_when_standing_le_next_price(self):
        its = self._step(self._haggled(20), [need("RET-06", "abuela")])
        self.assertEqual([(i.kind, i.args["price"]) for i in its], [("accept", 20)])
        a = its[0].args
        self.assertEqual((a["source"], a["side"], a["thread_id"], a["offer_id"], a["give_asset"]), ("dealer", "buy", 7, 5, None))

    def test_raises_when_standing_above_next(self):
        its = self._step(self._haggled(23), [need("RET-06", "abuela")])
        self.assertEqual([(i.kind, i.args["price"], i.args["template"]) for i in its], [("say", 20, "abuela_buy")])

    def test_final_above_limit_closes(self):
        its = self._step(self._haggled(24, final=True),
                         [need("RET-06", "abuela")], make_book(thread_limit={7: 22}, thread_by_dealer={"abuela": 7}))
        self.assertEqual([i.kind for i in its], ["close_thread"])

    def test_final_within_limit_accepts(self):
        its = self._step(self._haggled(23, final=True), [need("RET-06", "abuela")])
        self.assertEqual([(i.kind, i.args["price"]) for i in its], [("accept", 23)])

    def test_limit_only_goes_down_with_value(self):
        sim_values = dict(VALUES, **{"RET-06": 20.0})                       # dv_add - 1 = 19 < standing 20
        w = make_world(threads={7: self._haggled(20)})
        its = D.propose(w, make_book(thread_limit={7: 25}), FakeValuer(sim_values), Cfg(), PLAN,
                        [need("RET-06", "abuela")], D.DealerState())
        self.assertEqual([i.kind for i in its], ["say"])
        self.assertEqual(its[0].args["price"], 19)

    def test_unknown_limit_closes(self):
        its = self._step(self._haggled(20), [need("RET-06", "abuela")], make_book())
        self.assertEqual([i.kind for i in its], ["close_thread"])

    def test_need_gone_closes(self):
        self.assertEqual([i.kind for i in self._step(self._haggled(20), [])], ["close_thread"])

    def test_waits_for_dealer_answer(self):
        t = self._haggled(23)
        t["messages"].append({"id": 6, "tick": 10, "sender": TEAM, "offer": own_offer(6, "abuela", "RET-06", 20, 10)})
        self.assertEqual(self._step(t, [need("RET-06", "abuela")]), [])

    def test_pending_acceptance_waits(self):
        t = self._haggled(20)
        t["standing_offers"][0]["status"] = "queued"
        t["messages"][-1]["offer"]["status"] = "queued"
        self.assertEqual(self._step(t, [need("RET-06", "abuela")]), [])

    def test_no_accept_without_fingerprint_module(self):
        with mock.patch.dict(sys.modules, {"agent.guards": None}):
            its = self._step(self._haggled(20), [need("RET-06", "abuela")])
        self.assertFalse(any(i.kind == "accept" for i in its))

    def test_no_valuation_module_no_intents(self):
        with mock.patch.dict(sys.modules, {"agent.valuation": None}):
            self.assertEqual(self._step(self._haggled(20), [need("RET-06", "abuela")]), [])

    def test_pack_in_hand_no_step_no_open(self):
        its = self._step(self._haggled(20), [need("RET-06", "abuela"), need("RET-09", "chato")],
                         make_book(thread_limit={7: 25}, packs=(99,)))
        self.assertEqual(its, [])


class OpenTest(Base):
    def _open(self, needs, book=None, world=None, plan=PLAN, values=VALUES, closers=()):
        w = world or make_world()
        return D.propose(w, book or make_book(), FakeValuer(values, closers), Cfg(), plan, needs, D.DealerState())

    def test_opens_with_limit_from_profile_need_value_and_cash(self):
        its = self._open([need("RET-06", "abuela", max_price=24), need("RET-09", "chato")])
        got = {(i.args["dealer"], i.args["ref"]): i.args["limit"] for i in its}
        self.assertEqual(got, {("abuela", "RET-06"): 24, ("chato", "RET-09"): 90})
        self.assertTrue(all(i.kind == "open_thread" and i.args["side"] == "buy" for i in its))

    def test_one_thread_per_dealer(self):
        its = self._open([need("RET-06", "abuela"), need("RET-02", "abuela")])
        self.assertEqual(len(its), 1)

    def test_no_new_threads_with_four_live_duels(self):
        w = make_world(duels=[{"status": "live"}] * 4)
        self.assertEqual(self._open([need("RET-06", "abuela")], world=w), [])
        w3 = make_world(duels=[{"status": "live"}] * 3)
        self.assertEqual(len(self._open([need("RET-06", "abuela")], world=w3)), 1)

    def test_skips_closer_frozen_and_page_closing(self):
        self.assertEqual(self._open([need("RET-06", "abuela", closer=True)]), [])
        self.assertEqual(self._open([need("RET-06", "abuela")], book=make_book(frozen_closer={"RET": "RET-06"})), [])
        self.assertEqual(self._open([need("RET-06", "abuela")], closers={"RET-06"}), [])

    def test_skips_blocked_locked_busy_and_team_needs(self):
        self.assertEqual(self._open([need("RET-06", "abuela")], book=make_book(dealer_block={"abuela": 12})), [])
        self.assertEqual(self._open([need("RET-09", "chato")], world=make_world(unlocked=("abuela",))), [])
        self.assertEqual(self._open([need("RET-06", "abuela")], book=make_book(paths={"RET-06": 1})), [])
        self.assertEqual(self._open([need("RET-06", "team")]), [])
        self.assertEqual(self._open([need("RET-06", "abuela")], world=make_world(down=frozenset({"threads"}))), [])
        self.assertEqual(self._open([need("RET-06", "abuela")], book=make_book(valuation_ok=False)), [])

    def test_limit_below_anchor_or_no_cash_skips(self):
        self.assertEqual(self._open([need("RET-06", "abuela", max_price=15)]), [])
        self.assertEqual(self._open([need("RET-06", "abuela")], book=make_book(cash_free=10)), [])

    def test_fallback_to_rarity_profile_after_walk(self):
        w = make_world(tick=30, threads={3: {"id": 3, "with": "chato", "topic": {"buy": {"card": "RET-08"}},
                                              "status": "closed", "created_tick": 15, "messages": [], "standing_offers": []}})
        its = D.propose(w, make_book(), FakeValuer(VALUES), Cfg(), PLAN, [need("RET-08", "chato")],
                        D.DealerState.rebuild(w, None))
        self.assertEqual([(i.args["dealer"], i.args["limit"]) for i in its], [("abuela", 25)])

    def test_fallback_after_closes_slow_thread(self):
        o = dealer_offer(1, "chato", "RET-08", 32, 21)
        t = {"id": 7, "with": "chato", "topic": {"buy": {"card": "RET-08"}}, "status": "open", "created_tick": 15,
             "messages": [{"id": 1, "tick": 21, "sender": "chato", "offer": o}], "standing_offers": [o]}
        w = make_world(tick=25, threads={7: t})
        its = D.propose(w, make_book(thread_limit={7: 31}), FakeValuer(VALUES), Cfg(), PLAN,
                        [need("RET-08", "chato")], D.DealerState.rebuild(w, None))
        self.assertEqual([i.kind for i in its], ["close_thread"])


class ProbeTest(Base):
    def test_probe_never_accepts(self):
        plan = json.loads(json.dumps(PLAN))
        plan["profiles"]["LAT-09"] = {"dealer": "chato", "anchor": 40, "step": 4, "limit": 60, "probe": True,
                                      "fallback_after": 4}
        rng = random.Random(3)
        sim = Sim(lambda d, r: ChatoBot(97, 50, rng), [], plan=plan).run(30)
        self.assertEqual(sim.deals, [])
        self.assertFalse(any(it.kind == "accept" for it in sim.intents))
        self.assertTrue(sim.intents and all(it.experiment == "PROBE:chato:LAT-09"
                                            for it in sim.intents if it.kind in ("open_thread", "say")))
        self.assertTrue(all(t["status"] == "closed" for t in sim.threads.values()))
        self.assertLessEqual(len(sim.prices.get(1, [])), 4)


class RebuildTest(unittest.TestCase):
    def test_limits_and_walks_from_world_and_journal(self):
        threads = {
            4: {"id": 4, "with": "abuela", "topic": {"buy": {"card": "RET-06"}}, "status": "closed", "created_tick": 5,
                "messages": [{"id": 1, "tick": 8, "sender": "abuela"}]},
            9: {"id": 9, "with": "abuela", "topic": {"buy": {"card": "RET-06"}}, "status": "open", "created_tick": 12,
                "messages": []}}
        rows = [{"kind": "intent", "tick": 5, "tactic": "dealers", "args": {"dealer": "abuela", "side": "buy",
                 "ref": "RET-06", "asset_ids": [], "limit": 25}},
                {"kind": "intent", "tick": 12, "tactic": "dealers", "args": {"dealer": "abuela", "side": "buy",
                 "ref": "RET-06", "asset_ids": [], "limit": 23}, "experiment": "PROBE:abuela:RET-06"},
                {"kind": "intent", "tick": 12, "tactic": "rastro", "args": {"dealer": "abuela", "side": "buy",
                 "ref": "RET-06", "asset_ids": [], "limit": 99}}]
        st = D.DealerState.rebuild(make_world(tick=13, threads=threads), FakeJournal(rows))
        self.assertEqual((st.opened[4]["limit"], st.opened[9]["limit"]), (25, 23))
        self.assertTrue(st.opened[9]["probe"])
        self.assertEqual(st.walks, {("abuela", "RET-06"): [8]})
        self.assertEqual(st.recent_walks("abuela", "RET-06", 13, 60), 1)

    def test_broken_journal_fails_closed(self):
        class Broken:
            def rows(self, kinds=None):
                raise OSError("boom")
        st = D.DealerState.rebuild(make_world(), Broken())
        self.assertFalse(st.journal_ok)


# ------------------------------------------------------------- real config/plan.json and sim/bots.py dealers

def _real_plan():
    from pathlib import Path
    return json.loads((Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "plan_night.json").read_text(encoding="utf-8"))


class RealPlanTest(Base):
    """config/plan.json keys profiles by ref and by "SET:rarity" (M8); RET-08 falls back via fallback_dealer."""

    def setUp(self):
        super().setUp()
        try:
            self.plan = _real_plan()
        except Exception as e:                                      # pragma: no cover
            self.skipTest(f"config/plan.json unreadable: {e}")

    def _open(self, needs, world=None):
        w = world or make_world()
        return D.propose(w, make_book(), FakeValuer(VALUES), Cfg(), self.plan, needs, D.DealerState.rebuild(w, None))

    def test_set_rarity_profiles_resolve(self):
        got = {}
        for n in (need("RET-06", "abuela"), need("RET-09", "chato"), need("RET-02", "abuela")):
            its = self._open([n])
            got[n.ref] = [(i.kind, i.args["dealer"], i.args["limit"]) for i in its]
        self.assertEqual(got, {"RET-06": [("open_thread", "abuela", 25)], "RET-09": [("open_thread", "chato", 90)],
                               "RET-02": [("open_thread", "abuela", 11)]})

    def test_ret08_chato_first_then_fallback_dealer(self):
        self.assertEqual([(i.args["dealer"], i.args["limit"]) for i in self._open([need("RET-08", "chato")])],
                         [("chato", 31)])
        w = make_world(tick=30, threads={3: {"id": 3, "with": "chato", "topic": {"buy": {"card": "RET-08"}},
                                              "status": "closed", "created_tick": 15, "messages": [], "standing_offers": []}})
        self.assertEqual([(i.args["dealer"], i.args["limit"]) for i in self._open([need("RET-08", "chato")], w)],
                         [("abuela", 25)])

    def test_unknown_ref_without_profile_opens_nothing(self):
        self.assertEqual(self._open([need("LAT-09", "chato")]), [])


class _Model:
    def __init__(self):
        self.packs = set()
        self.cards = {c["id"]: c for s in CATALOG["sets"] for c in s["cards"]}

    def slot_cards(self, rarity):
        return [r for r, c in self.cards.items() if c["rarity"] == rarity]


class _GameAdapter:
    """The FakeGame hooks sim/bots.py dealers call, writing into a Sim's thread dicts."""

    def __init__(self, sim):
        self.sim, self.model, self.walk_reasons, self.gifts = sim, _Model(), [], []

    @property
    def threads(self):
        return self.sim.threads

    def dealer_say(self, tid, price, text="", final=False):
        t, sim = self.sim.threads[tid], self.sim
        for m in t["messages"]:
            if m["sender"] != TEAM and m["offer"]["status"] == "open":
                m["offer"]["status"] = "expired"
        o = dealer_offer(sim._oid(), t["with"], t["item"], price, sim.tick, final=final)
        t["messages"].append({"id": sim._oid(), "tick": sim.tick, "sender": t["with"], "offer": o})
        t["standing_offers"] = [o]

    def dealer_accept(self, tid):
        t = self.sim.threads[tid]
        mine = [m["offer"] for m in t["messages"] if m["sender"] == TEAM][-1]
        mine["status"] = "settled"
        t["status"] = "deal"
        self.sim.deals.append((t["item"], mine["give"]["cash"], t["with"]))
        return True

    def dealer_walk(self, tid, text="not today", reason="walked"):
        self.walk_reasons.append(text)
        self.sim.threads[tid]["status"] = "closed"
        self.sim._expire_open(self.sim.threads[tid])

    def gift(self, team, cards=(), reason=""):
        self.gifts.append(tuple(cards))


class RealBotSim(Sim):
    def __init__(self, bots, needs, plan=PLAN, values=VALUES):
        super().__init__(None, needs, values=values, plan=plan)
        self.real_bots, self.game = bots, _GameAdapter(self)

    def apply(self, it):
        a = it.args
        if it.kind == "open_thread":
            self.intents.append(it)
            tid = len(self.threads) + 1
            t = {"id": tid, "with": a["dealer"], "team": TEAM, "topic": {"buy": {"card": a["ref"]}}, "status": "open",
                 "created_tick": self.tick, "messages": [], "standing_offers": [], "item": a["ref"], "side": "buy"}
            self.threads[tid], self.limits[tid] = t, a["limit"]
            self.journal_rows.append({"kind": "intent", "tick": self.tick, "tactic": "dealers", "args": dict(a),
                                      "experiment": it.experiment})
            self.real_bots[a["dealer"]].on_message(self.game, t, None)
        elif it.kind == "say":
            self.intents.append(it)
            tid = a["thread_id"]
            t = self.threads[tid]
            self.prices.setdefault(tid, []).append(a["price"])
            self._expire_open(t)
            mine = own_offer(self._oid(), t["with"], a["ref"], a["price"], self.tick)
            t["messages"].append({"id": self._oid(), "tick": self.tick, "sender": TEAM, "offer": mine})
            text = "%s:%d:%d" % (a["template"], a["variant"], a["price"])
            self.real_bots[t["with"]].on_message(self.game, t, {"price": a["price"], "text": text})
        else:
            super().apply(it)

    def run(self, ticks=40):
        for _ in range(ticks):
            for b in self.real_bots.values():
                b.on_tick(self.game)
            super().run(1)
            if self.threads and not any(t["status"] == "open" for t in self.threads.values()):
                break
        return self


class SimBotsTest(Base):
    """Against sim/bots.py AbuelaBot and ChatoBot (M6b, D-01..D-10)."""

    def setUp(self):
        super().setUp()
        try:
            import sim.bots as B
        except Exception as e:                                      # pragma: no cover
            self.skipTest(f"sim/bots.py not importable: {e}")
        self.B = B

    def _check(self, sim, limit):
        for tid, ps in sim.prices.items():
            self.assertEqual(ps, sorted(set(ps)), f"prices repeated or not rising: {ps}")
            self.assertTrue(all(p <= limit for p in ps), ps)
        for _, price, _ in sim.deals:
            self.assertLessEqual(price, limit)
        self.assertNotIn("with those manners", sim.game.walk_reasons)     # D-07: never repeated a price or text
        for t in sim.threads.values():
            self.assertIn(t["status"], ("deal", "closed"))

    def test_abuela_uncommon_buys_within_limit_or_closes(self):
        deals = 0
        for seed in range(40):
            sim = RealBotSim({"abuela": self.B.AbuelaBot(seed=seed)}, [need("RET-06", "abuela")]).run(60)
            self._check(sim, 25)
            deals += len(sim.deals)
            if not sim.deals:
                self.assertFalse(any(i.kind == "accept" for i in sim.intents))
        self.assertGreater(deals, 20)

    def test_abuela_floor_above_limit_never_buys(self):
        for seed in range(30):
            sim = RealBotSim({"abuela": self.B.AbuelaBot(seed=seed)}, [need("RET-06", "abuela", max_price=20)]).run(60)
            self._check(sim, 20)
            self.assertEqual(sim.deals, [], "seed %d" % seed)              # her floor is 21-25 (D-05)

    def test_abuela_welcome_price_is_taken(self):
        sim = RealBotSim({"abuela": self.B.AbuelaBot(welcome=True)}, [need("RET-06", "abuela")]).run(10)
        self.assertEqual(sim.deals, [("RET-06", 17, "abuela")])           # E3: opens at 17 (final) -> accept
        sim = RealBotSim({"abuela": self.B.AbuelaBot(welcome=True)}, [need("RET-02", "abuela")]).run(10)
        self.assertEqual(sim.deals, [("RET-02", 7, "abuela")])

    def test_chato_rare_only_at_or_below_90(self):
        deals = 0
        for seed in range(40):
            sim = RealBotSim({"chato": self.B.ChatoBot(seed=seed)}, [need("RET-09", "chato")]).run(80)
            self._check(sim, 90)
            deals += len(sim.deals)
        self.assertGreater(deals, 0)

if __name__ == "__main__":
    unittest.main()
