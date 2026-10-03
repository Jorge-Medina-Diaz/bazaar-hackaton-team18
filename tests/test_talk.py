"""M4b: G30-G32 (dealer threads), G50-G51 (duels), INV-10, INV-11, INV-12. Doubles for Valuer / Cfg / Counters."""
from __future__ import annotations

import hashlib
import sys
import types
import unittest
from types import MappingProxyType, SimpleNamespace

from agent import talk
from agent.contracts import Book, Limits, Need, World, make_intent
from agent.valuation import predict_none



def _dfp(d):
    """Test double of guards.duel_fingerprint (spec §2.5), used only while M4a is not importable."""
    r = d.get("rival_offer") or {}
    raw = f"{d.get('duel')}|{r.get('id')}|{r.get('price')}|{r.get('days')}|{r.get('tick')}|{len(d.get('messages') or ())}"
    return hashlib.sha1(raw.encode()).hexdigest()


_SAVED = {}


def setUpModule():
    """Install the fake agent.guards only for this module's tests, and only if the real one cannot import."""
    try:
        import agent.guards  # noqa: F401
    except Exception:  # noqa: BLE001
        _SAVED["agent.guards"] = sys.modules.get("agent.guards")
        mod = types.ModuleType("agent.guards")
        mod.duel_fingerprint = _dfp
        sys.modules["agent.guards"] = mod


def tearDownModule():
    if "agent.guards" in _SAVED:
        prev = _SAVED.pop("agent.guards")
        if prev is None:
            sys.modules.pop("agent.guards", None)
        else:
            sys.modules["agent.guards"] = prev


PRED = predict_none()
TICK = 200


class FakeValuer:
    def __init__(self, add=None, rm=None, closes=()):
        self.add, self.rm, self.closes = add or {}, rm or {}, set(closes)

    def delta_add(self, counts, ref, packs=(), minted=None):
        return self.add[ref]

    def delta_remove(self, counts, ref, packs=(), minted=None):
        return self.rm[ref]

    def closes_page(self, counts, ref):
        return ref in self.closes


CFG = SimpleNamespace(DEALER_MARGIN=1.0, TICK_MARGIN_S=2.0, ALLOW_DEALER_CLOSE=frozenset({"LAT"}))


def counters(**kw):
    return SimpleNamespace(**{"tick": TICK, "accepts": 0, "msgs": set(), **kw})


def book(**kw):
    base = dict(cash=300, cash_free=200, held={"LAT-07": 2, "MAL-03": 1, "SAL-02": 1}, listed={}, pending_out={},
                pending_in={}, projected={"LAT-07": 2}, keep={"SAL-02": 1, "LAT-07": 1}, listed_assets=frozenset(),
                own_offer_ids=frozenset(), own_bids={}, bid_price={}, bid_band={}, paths={}, thread_limit={},
                thread_prices={}, thread_ref={}, thread_by_dealer={}, dealer_block={}, dealer_deals_hour={},
                packs=(), needs={"LAT-09": Need("LAT", "LAT-09", "chato", 90, False),
                                 "RET-04": Need("RET", "RET-04", "abuela", 25, False)},
                frozen_closer={"RET": "RET-07"}, protect_sets=frozenset({"SAL", "RET", "CHA", "LAT"}),
                delivery_risk=False, recent_rastro={}, unknown_domains=frozenset(), valuation_ok=True)
    base.update(kw)
    return Book(**base)


ASSETS = [{"id": 267, "kind": "card", "ref": "LAT-07"}, {"id": 268, "kind": "card", "ref": "LAT-07"},
          {"id": 300, "kind": "card", "ref": "MAL-03"}, {"id": 256, "kind": "card", "ref": "SAL-02"},
          {"id": 900, "kind": "pack", "ref": "sobre_barrio"}]
SCHEDULE = {"upcoming": [{"at_hours": 9.0, "action": "bench", "params": {}},
                         {"at_hours": 12.0, "action": "grant_all", "params": {"packs": ["sobre_barrio"], "cash": 150}}]}


def world(**kw):
    base = dict(tick=TICK, t_hours=4.5, round=2, tick_seconds=30.0, tick_deadline=1000.0, clock={},
                limits=Limits(1, 1, 6, 30, 12), reading="N",
                me={"id": "t18", "unlocked": ["abuela", "chato"], "assets": ASSETS},
                my_offers=(), offers_to_us=(), board=(), own_pseudonym=None, threads={}, foreign_threads=(),
                duels=(), catalog={}, schedule=SCHEDULE, released_sets=frozenset(), feed_new=(),
                server_values={}, down=frozenset())
    base.update(kw)
    return World(**base)


def run(intent, w=None, b=None, v=None, c=None, *, fresh=None, now=990.0):
    return talk.check(intent, w or world(), b or book(), v or FakeValuer(add={"LAT-09": 100.0, "RET-04": 30.0},
                      rm={"LAT-07": 12.0, "MAL-03": 4.0, "SAL-02": 9.0}),
                      CFG, c or counters(), fresh=fresh, now=now)


def open_thread(dealer="chato", side="buy", ref="LAT-09", asset_ids=(), limit=80):
    return make_intent("open_thread", "dealers", {"dealer": dealer, "side": side, "ref": ref,
                                                  "asset_ids": tuple(asset_ids), "limit": limit}, "t", "t", PRED)


# ---------------------------------------------------------------------------------------- G30


class G30Open(unittest.TestCase):
    def test_buy_ok(self):
        self.assertTrue(run(open_thread()).ok)

    def test_limit_equal_to_cap_ok(self):
        # cap = min(floor(100 - 1), 90) = 90
        self.assertTrue(run(open_thread(limit=90)).ok)

    def test_sell_ok(self):
        v = run(open_thread(dealer="abuela", side="sell", ref="MAL-03", asset_ids=(300,), limit=5))
        self.assertTrue(v.ok, v)

    def test_sell_one_of_two_lat_ok(self):
        v = run(open_thread(side="sell", ref="LAT-07", asset_ids=(267,), limit=13), b=book(keep={"LAT-07": 1}))
        self.assertTrue(v.ok, v)

    def test_limit_over_need(self):
        self.assertEqual(run(open_thread(limit=91)).code, "G30.limit")

    def test_limit_over_value(self):
        v = FakeValuer(add={"LAT-09": 60.0})
        self.assertEqual(run(open_thread(limit=60), v=v).code, "G30.limit")

    def test_locked_dealer(self):
        self.assertEqual(run(open_thread(dealer="nuevo")).code, "G30.locked")

    def test_thread_already_open(self):
        self.assertEqual(run(open_thread(), b=book(thread_by_dealer={"chato": 5})).code, "G30.thread_open")
        w = world(threads={5: {"id": 5, "with": "chato", "status": "open", "topic": {"buy": {"card": "X"}}}})
        self.assertEqual(run(open_thread(), w=w).code, "G30.thread_open")

    def test_blocked(self):
        self.assertEqual(run(open_thread(), b=book(dealer_block={"chato": TICK + 3})).code, "G30.blocked")
        self.assertTrue(run(open_thread(), b=book(dealer_block={"chato": TICK})).ok)

    def test_no_need(self):
        self.assertEqual(run(open_thread(ref="LAT-02")).code, "G30.no_need")

    def test_closes_ret_page_refused_inv10(self):
        v = FakeValuer(add={"RET-04": 30.0}, closes={"RET-04"})
        self.assertEqual(run(open_thread(dealer="abuela", ref="RET-04", limit=20), v=v).code, "G30.closes_page")

    def test_closes_lat_page_allowed(self):
        v = FakeValuer(add={"LAT-09": 100.0}, closes={"LAT-09"})
        self.assertTrue(run(open_thread(), v=v).ok)

    def test_frozen_closer(self):
        b = book(needs={"RET-07": Need("RET", "RET-07", "abuela", 25, True)})
        v = FakeValuer(add={"RET-07": 40.0})
        self.assertEqual(run(open_thread(dealer="abuela", ref="RET-07", limit=20), b=b, v=v).code,
                         "G30.frozen_closer")

    def test_grant_soon(self):
        # 3 ticks * 30 s = 0.025 h; grant at 12.0
        self.assertEqual(run(open_thread(), w=world(t_hours=11.98)).code, "G30.grant_soon")
        self.assertTrue(run(open_thread(), w=world(t_hours=11.9)).ok)

    def test_grant_unknown_schedule(self):
        self.assertEqual(run(open_thread(), w=world(schedule={})).code, "G30.grant_unknown")

    def test_pack_in_hand(self):
        self.assertEqual(run(open_thread(), b=book(packs=(900,))).code, "G14.pack")

    def test_second_path(self):
        self.assertEqual(run(open_thread(), b=book(paths={"LAT-09": 1})).code, "G15.path")

    def test_cash(self):
        self.assertEqual(run(open_thread(), b=book(cash_free=50)).code, "G16.cash")

    def test_sell_protected(self):
        v = run(open_thread(dealer="abuela", side="sell", ref="SAL-02", asset_ids=(256,), limit=20))
        self.assertEqual(v.code, "G13.protected")

    def test_sell_below_value(self):
        # ceil(12 + 1) = 13
        self.assertEqual(run(open_thread(side="sell", ref="LAT-07", asset_ids=(267,), limit=12)).code, "G30.limit")

    def test_sell_not_ours_or_listed(self):
        self.assertEqual(run(open_thread(side="sell", ref="LAT-07", asset_ids=(999,), limit=20)).code,
                         "G30.not_ours")
        b = book(listed_assets=frozenset({267}))
        self.assertEqual(run(open_thread(side="sell", ref="LAT-07", asset_ids=(267,), limit=20), b=b).code,
                         "G30.listed")
        self.assertEqual(run(open_thread(side="sell", ref="LAT-07", asset_ids=(300,), limit=20)).code,
                         "G30.asset_ref")

    def test_valuation_down(self):
        self.assertEqual(run(open_thread(), b=book(valuation_ok=False)).code, "G06.valuation")

    def test_valuer_exception_fails_closed(self):
        self.assertFalse(run(open_thread(), v=FakeValuer(add={})).ok)


# ---------------------------------------------------------------------------------------- G31


def thread(tid=7, dealer="chato", ref="LAT-09", side="buy", ours=(), theirs=((95, False),), status="open"):
    msgs = []
    oid = 1000
    for p in ours:
        oid += 1
        give, want = ({"cash": p, "assets": [], "types": []}, {"cash": 0, "assets": [], "types": [f"card:{ref}"]}) \
            if side == "buy" else ({"cash": 0, "assets": [{"id": 267, "kind": "card", "ref": ref}], "types": []},
                                   {"cash": p, "assets": [], "types": []})
        msgs.append({"id": oid, "tick": TICK - 1, "sender": "t18",
                     "offer": {"id": oid, "maker": "t18", "to": dealer, "status": "cancelled", "give": give,
                               "want": want, "expires_tick": TICK + 1, "created_tick": TICK - 1, "final": False}})
    for p, final in theirs:
        oid += 1
        if side == "buy":
            give, want = {"cash": 0, "assets": [], "types": [f"card:{ref}"]}, {"cash": p, "assets": [], "types": []}
        else:
            give, want = {"cash": p, "assets": [], "types": []}, {"cash": 0, "assets": [{"id": 267}], "types": []}
        msgs.append({"id": oid, "tick": TICK, "sender": dealer,
                     "offer": {"id": oid, "maker": dealer, "to": "t18", "venue": None, "thread": tid, "status": "open",
                               "give": give, "want": want, "expires_tick": TICK + 2, "created_tick": TICK,
                               "final": final}})
    topic = {"buy": {"card": ref}} if side == "buy" else {"sell": {"assets": [267]}}
    return {"id": tid, "team": "t18", "with": dealer, "topic": topic, "status": status, "messages": msgs,
            "standing_offers": []}


def say(price, tid=7, ref="LAT-09", template="chato_buy", variant=0):
    return make_intent("say", "dealers", {"thread_id": tid, "ref": ref, "price": price, "template": template,
                                          "variant": variant}, "t", "t", PRED)


def tb(**kw):
    base = dict(thread_limit={7: 88}, thread_prices={7: (70,)}, thread_ref={7: "LAT-09"},
                thread_by_dealer={"chato": 7}, paths={"LAT-09": 1})
    base.update(kw)
    return book(**base)


class G31Say(unittest.TestCase):
    def w(self, **kw):
        return world(threads={7: thread(**kw)})

    def test_ok(self):
        self.assertTrue(run(say(75), w=self.w(ours=(70,)), b=tb()).ok)

    def test_price_equal_limit_ok(self):
        self.assertTrue(run(say(88), w=self.w(ours=(70,)), b=tb()).ok)

    def test_all_variants_ok(self):
        for i in range(len(talk.TEMPLATES["chato_buy"])):
            self.assertTrue(run(say(75, variant=i), w=self.w(ours=(70,)), b=tb()).ok)

    def test_first_message_ok(self):
        self.assertTrue(run(say(60), w=self.w(), b=tb(thread_prices={})).ok)

    def test_over_limit(self):
        self.assertEqual(run(say(89), w=self.w(ours=(70,)), b=tb()).code, "G31.limit")

    def test_limit_lowered_by_value(self):
        v = FakeValuer(add={"LAT-09": 80.0})            # floor(80 - 1) = 79 < 88
        self.assertEqual(run(say(80), w=self.w(ours=(70,)), b=tb(), v=v).code, "G31.limit")
        self.assertTrue(run(say(79), w=self.w(ours=(70,)), b=tb(), v=v).ok)

    def test_not_monotone(self):
        self.assertEqual(run(say(69), w=self.w(ours=(70,)), b=tb()).code, "G31.limit")

    def test_repeat_price_from_journal_or_server(self):
        self.assertEqual(run(say(70), w=self.w(ours=(70,)), b=tb()).code, "G31.repeat")
        # server knows a higher price of ours than the journal (restart): monotone vs the server too
        self.assertEqual(run(say(72), w=self.w(ours=(70, 74)), b=tb()).code, "G31.limit")

    def test_final_never_countered(self):
        self.assertEqual(run(say(75), w=self.w(ours=(70,), theirs=((90, True),)), b=tb()).code, "G31.final")

    def test_trick_offer_does_not_bind(self):
        # Pícaros trick: their "final" at 60 gives LAT-06, not the thread's LAT-09 -> it never blocks our next step
        w = self.w(ours=(70,), theirs=((60, True),))
        w.threads[7]["messages"][-1]["offer"]["give"]["types"] = ["card:LAT-06"]
        self.assertTrue(run(say(75), w=w, b=tb()).ok)
        self.assertEqual(run(say(75), w=self.w(ours=(70,), theirs=((60, True),)), b=tb()).code, "G31.final")

    def test_should_accept(self):
        self.assertEqual(run(say(85), w=self.w(ours=(70,), theirs=((84, False),)), b=tb()).code,
                         "G31.should_accept")

    def test_wrong_template(self):
        self.assertEqual(run(say(75, template="abuela_buy"), w=self.w(ours=(70,)), b=tb()).code, "G60.template")
        self.assertEqual(run(say(75, variant=99), w=self.w(ours=(70,)), b=tb()).code, "G60.render")

    def test_unknown_dealer_has_no_template(self):
        w = world(threads={7: thread(dealer="nuevo", ours=(70,))})
        self.assertEqual(run(say(75, template="chato_buy"), w=w, b=tb()).code, "G60.template")

    def test_one_message_per_tick(self):
        c = counters(msgs={"thread:7"})
        self.assertEqual(run(say(75), w=self.w(ours=(70,)), b=tb(), c=c).code, "G04.msg")

    def test_thread_closed_or_missing(self):
        self.assertEqual(run(say(75), w=self.w(status="closed"), b=tb()).code, "G31.not_open")
        self.assertEqual(run(say(75), w=world(), b=tb()).code, "G31.no_thread")

    def test_pack_in_hand(self):
        self.assertEqual(run(say(75), w=self.w(ours=(70,)), b=tb(packs=(900,))).code, "G14.pack")

    def test_sell_thread(self):
        b = tb(thread_limit={7: 14}, thread_prices={7: (20,)}, thread_ref={7: "LAT-07"})
        w = world(threads={7: thread(ref="LAT-07", side="sell", ours=(20,), theirs=((12, False),))})
        self.assertTrue(run(say(18, ref="LAT-07", template="chato_sell"), w=w, b=b).ok)
        self.assertEqual(run(say(21, ref="LAT-07", template="chato_sell"), w=w, b=b).code, "G31.limit")
        self.assertEqual(run(say(13, ref="LAT-07", template="chato_sell"), w=w, b=b).code, "G31.limit")
        w2 = world(threads={7: thread(ref="LAT-07", side="sell", ours=(20,), theirs=((19, False),))})
        self.assertEqual(run(say(18, ref="LAT-07", template="chato_sell"), w=w2, b=b).code, "G31.should_accept")

    def test_monotone_random_walk_inv11(self):
        """A sequence of approved says is strictly increasing and never above the limit."""
        import random
        rnd = random.Random(11)
        for _ in range(200):
            ours = []
            lim = rnd.randint(20, 95)
            for _step in range(12):
                p = rnd.randint(1, 100)
                b = tb(thread_limit={7: lim}, thread_prices={7: tuple(ours)})
                v = run(say(p, variant=rnd.randrange(4)), w=world(threads={7: thread(ours=tuple(ours),
                                                                                    theirs=((99, False),))}), b=b)
                if v.ok:
                    self.assertTrue(p <= lim and all(p > q for q in ours))
                    ours.append(p)


# ---------------------------------------------------------------------------------------- G32


def dealer_accept(offer_id, price, tid=7, ref="LAT-09", side="buy"):
    return make_intent("accept", "dealers", {"offer_id": offer_id, "source": "dealer", "ref": ref, "side": side,
                                             "price": price, "thread_id": tid, "give_asset": None,
                                             "fingerprint": "", "resupply": False, "venue": "rastro"},
                       "t", "t", PRED)


class G32Accept(unittest.TestCase):
    def setUp(self):
        self.t = thread(ours=(70,), theirs=((84, False),))
        self.oid = self.t["messages"][-1]["offer"]["id"]
        self.w = world(threads={7: self.t})

    def test_ok(self):
        self.assertTrue(run(dealer_accept(self.oid, 84), w=self.w, b=tb(), fresh=self.t).ok)

    def test_ok_final_at_limit(self):
        t = thread(ours=(70,), theirs=((88, True),))
        oid = t["messages"][-1]["offer"]["id"]
        self.assertTrue(run(dealer_accept(oid, 88), w=world(threads={7: t}), b=tb(), fresh=t).ok)

    def test_ok_wrapped_fresh(self):
        self.assertTrue(run(dealer_accept(self.oid, 84), w=self.w, b=tb(), fresh={"thread": self.t}).ok)

    def test_ok_sell(self):
        t = thread(ref="LAT-07", side="sell", ours=(20,), theirs=((15, False),))
        t["messages"][-1]["offer"]["want"] = {"cash": 0, "assets": [{"id": 267}], "types": []}
        oid = t["messages"][-1]["offer"]["id"]
        b = tb(thread_limit={7: 14}, thread_prices={7: (20,)}, thread_ref={7: "LAT-07"})
        v = run(dealer_accept(oid, 15, ref="LAT-07", side="sell"), w=world(threads={7: t}), b=b, fresh=t)
        self.assertTrue(v.ok, v)

    def test_over_limit(self):
        t = thread(ours=(70,), theirs=((89, False),))
        oid = t["messages"][-1]["offer"]["id"]
        self.assertEqual(run(dealer_accept(oid, 89), w=world(threads={7: t}), b=tb(), fresh=t).code, "G32.limit")

    def test_price_mismatch(self):
        self.assertEqual(run(dealer_accept(self.oid, 83), w=self.w, b=tb(), fresh=self.t).code, "G32.price")

    def test_expiring_offer(self):
        import copy
        t = copy.deepcopy(self.t)
        t["messages"][-1]["offer"]["expires_tick"] = TICK      # must be >= tick + 1
        self.assertEqual(run(dealer_accept(self.oid, 84), w=self.w, b=tb(), fresh=t).code, "G32.not_executable")

    def test_twisted_shape(self):
        import copy
        t = copy.deepcopy(self.t)
        t["messages"][-1]["offer"]["give"]["types"] = ["card:LAT-09", "card:LAT-10"]
        self.assertEqual(run(dealer_accept(self.oid, 84), w=self.w, b=tb(), fresh=t).code, "G32.not_executable")

    def test_no_fresh_or_missing_offer(self):
        self.assertFalse(run(dealer_accept(self.oid, 84), w=self.w, b=tb(), fresh=None).ok)
        self.assertEqual(run(dealer_accept(4242, 84), w=self.w, b=tb(), fresh=self.t).code, "G32.no_offer")

    def test_closes_ret_page_inv10(self):
        t = thread(dealer="abuela", ref="RET-04", ours=(15,), theirs=((20, False),))
        oid = t["messages"][-1]["offer"]["id"]
        b = tb(thread_limit={7: 25}, thread_prices={7: (15,)}, thread_ref={7: "RET-04"})
        v = FakeValuer(add={"RET-04": 30.0}, closes={"RET-04"})
        self.assertEqual(run(dealer_accept(oid, 20, ref="RET-04"), w=world(threads={7: t}), b=b, v=v, fresh=t).code,
                         "G32.closes_page")

    def test_margin_and_cash(self):
        v = FakeValuer(add={"LAT-09": 84.5})
        self.assertFalse(run(dealer_accept(self.oid, 84), w=self.w, b=tb(), v=v, fresh=self.t).ok)
        # the Book's cash_free already excludes this thread's reserve (its standing 84): add-back, live Sat SAL-11
        self.assertTrue(run(dealer_accept(self.oid, 84), w=self.w, b=tb(cash_free=0), fresh=self.t).ok)
        self.assertEqual(run(dealer_accept(self.oid, 84), w=self.w, b=tb(cash_free=-10), fresh=self.t).code,
                         "G16.cash")

    def test_pack_in_hand(self):
        self.assertEqual(run(dealer_accept(self.oid, 84), w=self.w, b=tb(packs=(900,)), fresh=self.t).code,
                         "G14.pack")

    def test_team_accept_not_judged_here(self):
        it = make_intent("accept", "rastro", {"offer_id": 1, "source": "team", "ref": "LAT-09", "side": "buy",
                                              "price": 5, "thread_id": None, "give_asset": None, "fingerprint": "x",
                                              "resupply": False, "venue": "rastro"}, "t", "t", PRED)
        self.assertEqual(run(it).code, "G02.kind")


# ---------------------------------------------------------------------------------------- G50


def duel(did=301, role="seller", limit=50, issues=("price",), w=None, mine=None, rival=None, deadline=TICK + 8,
         status="live", msgs=()):
    return {"duel": did, "status": status, "role": role, "issues": list(issues), "your_days_weight": w,
            "your_limit": limit, "deadline_tick": deadline, "decay_per_round": 0.06, "rounds": 1,
            "your_offer": mine, "rival_offer": rival, "messages": list(msgs)}


def dsay(price, days=None, did=301, template=None, variant=0):
    template = template or ("duel_days" if days is not None else "duel")
    return make_intent("duel_say", "duels", {"duel_id": did, "price": price, "days": days, "template": template,
                                             "variant": variant}, "t", "t", PRED)


class G50DuelSay(unittest.TestCase):
    def test_seller_ok(self):
        self.assertTrue(run(dsay(70), w=world(duels=(duel(),))).ok)

    def test_seller_limit_plus_one_ok(self):
        self.assertTrue(run(dsay(51), w=world(duels=(duel(),))).ok)

    def test_buyer_ok(self):
        self.assertTrue(run(dsay(100), w=world(duels=(duel(role="buyer", limit=101),))).ok)

    def test_concession_ok(self):
        d = duel(mine={"id": 1, "price": 70, "tick": TICK - 1, "days": 0})
        self.assertTrue(run(dsay(65), w=world(duels=(d,))).ok)

    def test_at_limit_refused(self):
        self.assertEqual(run(dsay(50), w=world(duels=(duel(),))).code, "G50.limit")
        self.assertEqual(run(dsay(101), w=world(duels=(duel(role="buyer", limit=101),))).code, "G50.limit")

    def test_not_monotone(self):
        d = duel(mine={"id": 1, "price": 70, "tick": TICK - 1, "days": 0})
        self.assertEqual(run(dsay(71), w=world(duels=(d,))).code, "G50.monotone")
        d2 = duel(msgs=({"tick": TICK - 2, "from": "you", "price": 60, "days": None},))
        self.assertEqual(run(dsay(61), w=world(duels=(d2,))).code, "G50.monotone")

    def test_repeat(self):
        d = duel(mine={"id": 1, "price": 70, "tick": TICK - 1, "days": 0})
        self.assertEqual(run(dsay(70), w=world(duels=(d,))).code, "G50.repeat")

    def test_worse_than_rival(self):
        d = duel(rival={"id": 9, "price": 66, "tick": TICK - 1, "days": 0})
        self.assertEqual(run(dsay(60), w=world(duels=(d,))).code, "G50.worse_than_rival")
        self.assertTrue(run(dsay(66), w=world(duels=(d,))).ok)

    def test_not_live_or_missing(self):
        self.assertEqual(run(dsay(70), w=world(duels=(duel(status="done"),))).code, "G50.not_live")
        self.assertEqual(run(dsay(70), w=world()).code, "G50.no_duel")

    def test_message_budget(self):
        self.assertEqual(run(dsay(70), w=world(duels=(duel(),)), c=counters(msgs={"duel:301"})).code, "G04.msg")

    def test_two_issue_needs_days_and_weight(self):
        d = duel(issues=("price", "days"), w=None)
        self.assertEqual(run(dsay(70), w=world(duels=(d,))).code, "G50.missing_days")
        self.assertEqual(run(dsay(70, days=3), w=world(duels=(d,))).code, "G50.days_unknown")

    def test_two_issue_null_weight_fallback(self):
        # cfg.DAYS_WEIGHT_FALLBACK (plan duels.days_weight_fallback) replaces a null weight: day 5 -> penalty 5 -> p >= 56
        d = duel(issues=("price", "days"), w=None)
        cfg = SimpleNamespace(**vars(CFG), DAYS_WEIGHT_FALLBACK=1.0)
        chk = lambda p, days: talk.check(dsay(p, days=days), world(duels=(d,)), book(), FakeValuer(), cfg, counters(),  # noqa: E731
                                         fresh=None, now=990.0)
        self.assertEqual(chk(55, 5).code, "G50.limit")
        self.assertTrue(chk(56, 5).ok)

    def test_two_issue_with_weight(self):
        d = duel(issues=("price", "days"), w=0.5)      # penalty at days 0 = 0.5 * 10 = 5 -> p >= 56
        self.assertTrue(run(dsay(56, days=0), w=world(duels=(d,))).ok)
        self.assertEqual(run(dsay(55, days=0), w=world(duels=(d,))).code, "G50.limit")
        self.assertTrue(run(dsay(54, days=5), w=world(duels=(d,))).ok)   # penalty 2.5 -> p >= 53.5
        self.assertEqual(run(dsay(70, days=11), w=world(duels=(d,))).code, "G50.missing_days")

    def test_days_on_price_only_duel(self):
        self.assertEqual(run(dsay(70, days=3), w=world(duels=(duel(),))).code, "G50.days_not_issue")

    def test_template_context(self):
        self.assertEqual(run(dsay(70, template="chato_buy"), w=world(duels=(duel(),))).code, "G60.template")

    def test_fuzz_never_outside_limit_inv12(self):
        import random
        rnd = random.Random(12)
        for _ in range(2000):
            role = rnd.choice(("seller", "buyer"))
            lim = rnd.randint(10, 150)
            two = rnd.random() < 0.3
            w = rnd.choice((None, 0.3, -1.2)) if two else None
            last = rnd.choice((None, rnd.randint(1, 200)))
            mine = {"id": 1, "price": last, "tick": TICK - 1, "days": 0} if last is not None else None
            d = duel(role=role, limit=lim, issues=("price", "days") if two else ("price",), w=w, mine=mine)
            p = rnd.randint(1, 200)
            days = rnd.randint(0, 10) if two else None
            v = run(dsay(p, days=days, variant=rnd.randrange(3)), w=world(duels=(d,)))
            if v.ok:
                s = 1 if role == "seller" else -1
                pen = abs(w) * max(days, 10 - days) if two else 0
                self.assertGreaterEqual(s * (p - lim), 1 + pen)
                if last is not None:
                    self.assertGreaterEqual(s * (last - p), 0)


# ---------------------------------------------------------------------------------------- G51


class G51DuelAccept(unittest.TestCase):
    def fresh(self, **kw):
        base = dict(rival={"id": 9, "price": 60, "tick": TICK, "days": 0})
        base.update(kw)
        return duel(**base)

    def acc(self, d, did=301):
        return make_intent("duel_accept", "duels", {"duel_id": did, "fingerprint": talk._duel_fp(d)}, "t", "t", PRED)

    def test_ok(self):
        d = self.fresh()
        self.assertTrue(run(self.acc(d), w=world(duels=(d,)), fresh=d).ok)

    def test_ok_payload_shapes(self):
        d = self.fresh()
        self.assertTrue(run(self.acc(d), fresh={"duels": [duel(did=5), d]}).ok)
        self.assertTrue(run(self.acc(d), fresh=[d]).ok)

    def test_ok_buyer(self):
        d = self.fresh(role="buyer", limit=101, rival={"id": 9, "price": 100, "tick": TICK, "days": 0})
        self.assertTrue(run(self.acc(d), fresh=d).ok)

    def test_ok_at_deadline_minus_one(self):
        d = self.fresh(deadline=TICK + 1)
        self.assertTrue(run(self.acc(d), fresh=d).ok)

    def test_rival_spoke_earlier_tick(self):
        d = self.fresh(rival={"id": 9, "price": 60, "tick": TICK - 1, "days": 0})
        self.assertEqual(run(self.acc(d), fresh=d).code, "G51.rival_tick")

    def test_fingerprint_changed(self):
        d = self.fresh()
        it = self.acc(d)
        d2 = self.fresh(rival={"id": 10, "price": 55, "tick": TICK, "days": 0})
        self.assertEqual(run(it, fresh=d2).code, "G51.fingerprint")

    def test_outside_limit(self):
        d = self.fresh(rival={"id": 9, "price": 50, "tick": TICK, "days": 0})
        self.assertEqual(run(self.acc(d), fresh=d).code, "G51.limit")

    def test_deadline(self):
        d = self.fresh(deadline=TICK)
        self.assertEqual(run(self.acc(d), fresh=d).code, "G51.deadline")

    def test_time_margin(self):
        d = self.fresh()
        self.assertEqual(run(self.acc(d), fresh=d, now=999.0).code, "G51.late")
        self.assertTrue(run(self.acc(d), fresh=d, now=998.0).ok)

    def test_no_fresh_or_no_rival(self):
        d = self.fresh()
        self.assertEqual(run(self.acc(d), fresh=None).code, "G51.no_fresh")
        d2 = self.fresh(rival=None)
        self.assertEqual(run(self.acc(d), fresh=d2).code, "G51.no_rival")

    def test_accept_budget(self):
        d = self.fresh()
        self.assertEqual(run(self.acc(d), fresh=d, c=counters(accepts=1)).code, "G04.accepts")

    def test_two_issue_worst_case_days(self):
        d = self.fresh(issues=("price", "days"), w=None, rival={"id": 9, "price": 60, "tick": TICK, "days": 2})
        self.assertEqual(run(self.acc(d), fresh=d).code, "G50.days_unknown")
        d2 = self.fresh(issues=("price", "days"), w=1.0, rival={"id": 9, "price": 60, "tick": TICK, "days": 0})
        self.assertEqual(run(self.acc(d2), fresh=d2).code, "G51.limit")   # 10 < 1 + 10
        d3 = self.fresh(issues=("price", "days"), w=1.0, rival={"id": 9, "price": 60, "tick": TICK, "days": 5})
        self.assertTrue(run(self.acc(d3), fresh=d3).ok)                    # 10 >= 1 + 5

    def test_without_guards_fails_closed(self):
        d = self.fresh()
        it = self.acc(d)
        saved = sys.modules.get("agent.guards")
        sys.modules["agent.guards"] = None
        try:
            self.assertEqual(run(it, fresh=d).code, "G51.no_fingerprint")
        finally:
            if saved is not None:
                sys.modules["agent.guards"] = saved
            else:
                sys.modules.pop("agent.guards", None)


class Misc(unittest.TestCase):
    def test_other_kinds_refused(self):
        it = make_intent("cancel", "hygiene", {"offer_id": 1, "ref": None}, "t", "t", PRED)
        self.assertEqual(run(it).code, "G02.kind")

    def test_templates_cover_spec_names(self):
        self.assertEqual(set(talk.TEMPLATES), {"abuela_buy", "chato_buy", "abuela_sell", "chato_sell", "pilar_sell",
                                               "picaros_buy", "banco_sell", "duel", "duel_days"})


if __name__ == "__main__":
    unittest.main()
