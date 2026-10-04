"""M4a guards-core: >= 4 positive and >= 4 negative cases per guard (G02-G07, G10-G16, G20-G23, G33, G40),
D1 swaps, D2 rival venues, build_book on the harvest (INV-06/07) and apply (running book)."""
from __future__ import annotations

import copy
import json
import math
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from agent import guards
from agent.contracts import FRIDAY, Intent, Outcome, Prediction, Verdict, World, make_intent
from agent.valuation import Valuer, fee

HARVEST = Path(__file__).resolve().parent / "fixtures" / "harvest"


def load(name: str):
    return json.loads((HARVEST / name).read_text(encoding="utf-8"))


ME = load("me.json")
CATALOG = load("catalog.json")
MY_OFFERS = tuple(load("me_offers.json")["offers"])
SELLS = tuple(o for o in MY_OFFERS if o["id"] not in (2503, 2504))
DEFAULT = tuple(o for o in SELLS if o["id"] != 2462)          # MAL-04 (asset 295) left unlisted
PLAN = {"protect_sets": ["SAL", "RET", "CHA", "LAT"], "baseline_bands": {"2503": 0.0, "2504": 0.0},
        "grant_lookahead_ticks": 3}
PSEUDO = "mcd38ffd5"


def pred(neg: float = 0.0) -> Prediction:
    return Prediction(neg_lo=neg, neg_hi=neg, ladder="0", cash=0, model="test")


class Ctx:
    """A World + Book + Valuer + Counters around the harvest `me`, tick 200, clock open."""

    def __init__(self, *, tick=200, me=None, my_offers=DEFAULT, threads=None, clock=None, down=frozenset(),
                 own_pseudonym=PSEUDO, venues=(), leaderboard=(), schedule=None, t_hours=5.0, journal=None,
                 frozen=None, plan=None, cfg=None):
        self.cfg = cfg or guards.Cfg()
        synthetic_me = me is not None
        me = copy.deepcopy(me or ME)
        self.world = World(
            tick=tick, t_hours=t_hours, round=2, tick_seconds=30.0, tick_deadline=100.0,
            clock=clock or {"tick": tick, "paused": False, "doors": "open"}, limits=FRIDAY, reading="N",
            me=me, my_offers=tuple(my_offers), offers_to_us=(), board=(), own_pseudonym=own_pseudonym,
            threads=threads or {}, foreign_threads=(), duels=(), catalog=CATALOG,
            schedule=schedule if schedule is not None else {"now_hours": t_hours, "upcoming": []},
            released_sets=Valuer.released_from_catalog(CATALOG), feed_new=(), server_values={}, down=frozenset(down),
            venues=tuple(venues), leaderboard=tuple(leaderboard))
        self.valuer = Valuer(CATALOG, me["affinity"], self.world.released_sets)
        self.book = guards.build_book(self.world, journal, self.valuer, self.cfg, plan or PLAN, frozen or {}, {})
        if synthetic_me:     # hand-edited `me`: collection_value was not recomputed, so self_check cannot pass
            self.book = replace(self.book, valuation_ok=True)
        self.counters = guards.Counters(tick=tick)
        self.now = 10.0

    def intent(self, kind, neg=0.0, tactic="manual", **args) -> Intent:
        return make_intent(kind, tactic, args, "test", "test", pred(neg))

    def check(self, it, fresh=None, **kw) -> Verdict:
        return guards.check(it, kw.get("world", self.world), kw.get("book", self.book), self.valuer, self.cfg,
                            kw.get("counters", self.counters), fresh=fresh, now=kw.get("now", self.now))

    def check_accept(self, args, offer, *, tick=None, neg=0.0, **kw) -> Verdict:
        try:
            it = self.intent("accept", neg=neg, **args)
        except ValueError as e:
            return Verdict(False, "make_intent", str(e))
        fresh = {"tick": self.world.tick if tick is None else tick, "offer": offer}
        return self.check(it, fresh, **kw)

    # convenient intents
    def sell(self, ref, asset_id, price, expires=60, neg=0.0):
        return self.intent("list_offer", neg=neg, side="sell", ref=ref, asset_id=asset_id, price=price,
                           expires_ticks=expires, closer=False, want_ref=None)

    def bid(self, ref, price, closer=False, expires=60, neg=0.0):
        return self.intent("list_offer", neg=neg, side="bid", ref=ref, asset_id=None, price=price,
                           expires_ticks=expires, closer=closer, want_ref=None)

    def swap(self, ref, asset_id, want_ref, closer=False, neg=0.0):
        return self.intent("list_offer", neg=neg, side="swap", ref=ref, asset_id=asset_id, price=0,
                           expires_ticks=60, closer=closer, want_ref=want_ref)


def accept_args(spec, offer, fingerprint=None, venue="rastro", resupply=False):
    oid = offer.get("id") if isinstance(offer, dict) else None
    return {"offer_id": oid if type(oid) is int and oid >= 0 else 999999, "source": "team", "ref": spec["ref"],
            "side": spec["side"], "price": spec["price"], "thread_id": None, "give_asset": spec["give_asset"],
            "fingerprint": guards.fingerprint(offer) if fingerprint is None else fingerprint,
            "resupply": resupply, "venue": venue}


def team_offer(oid, give, want, **kw):
    o = {"id": oid, "maker": "m7f3a9c21", "to": None, "venue": "rastro", "thread": None, "status": "open",
         "give": give, "want": want, "expires_tick": 230, "created_tick": 190, "final": False}
    o.update(kw)
    return o


def sell_offer(oid, ref, price, asset_id=7001, **kw):
    return team_offer(oid, {"cash": 0, "assets": [{"id": asset_id, "kind": "card", "ref": ref}], "types": []},
                      {"cash": price, "assets": [], "types": []}, **kw)


def bid_offer(oid, ref, price, **kw):
    return team_offer(oid, {"cash": price, "assets": [], "types": []},
                      {"cash": 0, "assets": [], "types": ["card:" + ref]}, **kw)


def swap_offer(oid, ref_in, ref_out, **kw):
    return team_offer(oid, {"cash": 0, "assets": [{"id": 7002, "kind": "card", "ref": ref_in}], "types": []},
                      {"cash": 0, "assets": [], "types": ["card:" + ref_out]}, **kw)


def buy_spec(ref, price):
    return {"side": "buy", "ref": ref, "price": price, "give_asset": None}


def max_buy_price(ctx, ref, min_gain=3.0, cards=1, bps=500, pc=1):
    dv = guards.dv_add(ctx.world, ctx.book, ctx.valuer, ref)
    best = 0
    for p in range(1, 400):
        if min(dv - p - fee(p, cards, bps, pc), 50.0) >= min_gain:
            best = p
    return best


# --------------------------------------------------------------------------------------------- tests

class G02Type(unittest.TestCase):
    def test_positive(self):
        c = Ctx()
        for it in (c.intent("cancel", offer_id=2463, ref="LAT-01"), c.sell("MAL-04", 295, 9),
                   c.bid("LAT-09", 30), c.intent("cancel", offer_id=1652, ref=None)):
            self.assertTrue(c.check(it).ok, it)

    def test_negative(self):
        c = Ctx()
        good = c.sell("MAL-04", 295, 9)
        bad_args = Intent("list_offer", "manual", {**good.args, "price": True}, "r", "e", pred())
        extra = Intent("list_offer", "manual", {**good.args, "venue": "v01"}, "r", "e", pred())
        bad_kind = Intent("open_venue", "manual", {}, "r", "e", pred())
        for it, code in ((bad_args, "G02.args"), (extra, "G02.args"), (bad_kind, "G02.kind"),
                         (object(), "G02.kind")):
            v = c.check(it)
            self.assertFalse(v.ok)
            self.assertEqual(v.code, code)

    def test_talk_kinds_fail_closed_without_talk(self):
        c = Ctx()
        it = c.intent("duel_accept", duel_id=149, fingerprint="x")
        with mock.patch.dict(sys.modules, {"agent.talk": None}):
            v = c.check(it)
        self.assertEqual((v.ok, v.code), (False, "G02.not_built"))


class G03Clock(unittest.TestCase):
    def test_positive_exempt_and_open(self):
        for clock in ({"paused": True, "doors": "open"}, {"paused": False, "doors": "closed"}, {}):
            c = Ctx(clock=clock)
            self.assertTrue(c.check(c.intent("cancel", offer_id=2463, ref=None)).ok)
        c = Ctx()
        self.assertTrue(c.check(c.intent("cancel", offer_id=2463, ref=None), now=1e9).ok)   # late but exempt
        self.assertTrue(c.check(c.sell("MAL-04", 295, 9), now=100.0).ok)                   # exactly at deadline

    def test_negative(self):
        for clock, code in (({"paused": True, "doors": "open"}, "G03.paused"),
                            ({"paused": False, "doors": "closed"}, "G03.doors"),
                            ({"doors": "open"}, "G03.paused"), ({"paused": False}, "G03.doors")):
            c = Ctx(clock=clock)
            v = c.check(c.sell("MAL-04", 295, 9))
            self.assertEqual((v.ok, v.code), (False, code))
        c = Ctx()
        self.assertEqual(c.check(c.sell("MAL-04", 295, 9), now=100.01).code, "G03.late")
        o = sell_offer(9001, "LAT-09", 20)
        self.assertEqual(c.check_accept(accept_args(buy_spec("LAT-09", 20), o), o, tick=199).code, "G03.stale")
        bare = c.check(c.intent("accept", **accept_args(buy_spec("LAT-09", 20), o)), fresh=o)
        self.assertFalse(bare.ok)


class G04Budgets(unittest.TestCase):
    def test_positive(self):
        c = Ctx()
        o = sell_offer(9001, "LAT-09", 20)
        self.assertTrue(c.check_accept(accept_args(buy_spec("LAT-09", 20), o), o).ok)
        for n in (0, 3, 5):
            cn = guards.Counters(tick=200, listings=n)
            self.assertTrue(c.check(c.sell("MAL-04", 295, 9), counters=cn).ok, n)

    def test_negative(self):
        c = Ctx()
        o = sell_offer(9001, "LAT-09", 20)
        v = c.check_accept(accept_args(buy_spec("LAT-09", 20), o), o, counters=guards.Counters(tick=200, accepts=1))
        self.assertEqual(v.code, "G04.accepts")
        self.assertEqual(c.check(c.sell("MAL-04", 295, 9), counters=guards.Counters(tick=200, listings=6)).code,
                         "G04.listings")
        self.assertEqual(c.check(c.sell("MAL-04", 295, 9), counters=guards.Counters(tick=199)).code, "G04.counters")
        many = guards.Counters(tick=200, offers_opened=30 - 4 - len(DEFAULT))
        self.assertEqual(c.check(c.sell("MAL-04", 295, 9), counters=many).code, "G04.open_offers")
        say = c.intent("say", thread_id=5, ref="RET-01", price=5, template="abuela_buy", variant=0)
        self.assertEqual(c.check(say, counters=guards.Counters(tick=200, msgs={"thread:5"})).code, "G04.msg")

    def test_offers_to_us_do_not_count(self):
        c = Ctx()
        flood = tuple(bid_offer(5000 + i, "SAL-01", 5, to="t18", maker="t07") for i in range(30))
        w = replace(c.world, offers_to_us=flood)
        self.assertTrue(c.check(c.sell("MAL-04", 295, 9), world=w).ok)


class G05Unknown(unittest.TestCase):
    def test_positive(self):
        for dom in ("offer:1", "asset:1", "ref:SAL-01", "thread:3"):
            c = Ctx()
            b = replace(c.book, unknown_domains=frozenset({dom}))
            self.assertTrue(c.check(c.sell("MAL-04", 295, 9), book=b).ok, dom)

    def test_negative(self):
        for dom in ("asset:295", "ref:MAL-04", "offer:2463"):
            c = Ctx()
            b = replace(c.book, unknown_domains=frozenset({dom}))
            it = c.intent("cancel", offer_id=2463, ref=None) if dom.startswith("offer") else c.sell("MAL-04", 295, 9)
            self.assertEqual(c.check(it, book=b).code, "G05.unknown", dom)
        c = Ctx()
        o = sell_offer(9001, "LAT-09", 20)
        b = replace(c.book, unknown_domains=frozenset({"offer:9001"}))
        self.assertEqual(c.check_accept(accept_args(buy_spec("LAT-09", 20), o), o, book=b).code, "G05.unknown")


class G06Sources(unittest.TestCase):
    def test_positive(self):
        for down, kind in (({"duels"}, "sell"), ({"board"}, "cancel"), ({"feed", "values"}, "cancel"),
                           ({"threads"}, "sell")):
            c = Ctx(down=down)
            it = c.intent("cancel", offer_id=2463, ref=None) if kind == "cancel" else c.sell("MAL-04", 295, 9)
            self.assertTrue(c.check(it).ok, (down, kind))

    def test_negative(self):
        for down, kind in (({"board"}, "sell"), ({"me/offers"}, "cancel"), ({"clock"}, "sell"), ({"me"}, "sell")):
            c = Ctx(down=down)
            it = c.intent("cancel", offer_id=2463, ref=None) if kind == "cancel" else c.sell("MAL-04", 295, 9)
            self.assertEqual(c.check(it).code, "G06.source", (down, kind))
        c = Ctx()
        b = replace(c.book, valuation_ok=False)
        self.assertEqual(c.check(c.sell("MAL-04", 295, 9), book=b).code, "G06.valuation")
        self.assertTrue(c.check(c.intent("cancel", offer_id=2463, ref=None), book=b).ok)   # cancel needs no value

    def test_rival_venue_needs_venues_and_leaderboard(self):
        for down in ({"venues"}, {"leaderboard"}, {"boards"}):
            c = Ctx(down=down, venues=[_venue("v02", "t12")], leaderboard=("t13", "t01", "t02", "t03", "t04", "t12"))
            o = sell_offer(9001, "LAT-09", 20, venue="v02")
            self.assertEqual(c.check_accept(accept_args(buy_spec("LAT-09", 20), o, venue="v02"), o).code,
                             "G06.source")


class G07Prediction(unittest.TestCase):
    def test_positive_and_negative(self):
        c = Ctx()
        dv = guards.dv_rm(c.world, c.book, c.valuer, "MAL-04", 295)
        honest = min(12 - dv, 50.0)
        for neg in (honest, honest - 1, 0.0, -5.0):
            self.assertTrue(c.check(c.sell("MAL-04", 295, 12, neg=neg)).ok, neg)
        for neg in (honest + 0.02, honest + 1, 50.0, 1e6):
            self.assertEqual(c.check(c.sell("MAL-04", 295, 12, neg=neg)).code, "G07.trip", neg)


class G10Identity(unittest.TestCase):
    def test_positive(self):
        c = Ctx()
        for kw in ({}, {"to": "t18"}, {"expires_tick": None}, {"expires_tick": 201}):
            o = sell_offer(9001, "LAT-09", 20, **kw)
            self.assertTrue(c.check_accept(accept_args(buy_spec("LAT-09", 20), o), o).ok, kw)

    def test_negative(self):
        c = Ctx()
        own_id = SELLS[0]["id"]
        cases = (({"expires_tick": 200}, "G10.expired"), ({"maker": PSEUDO}, "G10.own_maker"),
                 ({"maker": "t18"}, "G10.own_maker"), ({"to": "t07"}, "G10.to"), ({"venue": "v01"}, "G10.venue"),
                 ({"status": "queued"}, "G10.status"), ({"id": own_id}, "G10.own_offer"))
        for kw, code in cases:
            o = sell_offer(9001, "LAT-09", 20, **kw)
            self.assertEqual(c.check_accept(accept_args(buy_spec("LAT-09", 20), o), o).code, code, kw)
        o = sell_offer(9001, "LAT-09", 20)
        self.assertEqual(c.check_accept(accept_args(buy_spec("LAT-09", 20), o, fingerprint="abc"), o).code,
                         "G10.fingerprint")
        self.assertEqual(c.check(c.intent("accept", **accept_args(buy_spec("LAT-09", 20), o))).code, "G10.no_fresh")


class G11Shape(unittest.TestCase):
    def test_positive(self):
        c = Ctx(my_offers=())
        o = sell_offer(9001, "LAT-09", 20)
        self.assertTrue(c.check_accept(accept_args(buy_spec("LAT-09", 20), o), o).ok)
        o = bid_offer(9002, "LAV-03", 30)
        self.assertTrue(c.check_accept(accept_args({"side": "sell", "ref": "LAV-03", "price": 30, "give_asset": 261}, o), o).ok)
        o = swap_offer(9003, "LAT-10", "MAL-04")
        self.assertTrue(c.check_accept(accept_args({"side": "swap", "ref": "LAT-10", "price": 0, "give_asset": 295}, o), o).ok)
        o = team_offer(9004, {"cash": 0, "types": ["card:LAT-10"]}, {"assets": [{"id": 295, "kind": "card", "ref": "MAL-04"}]})
        self.assertTrue(c.check_accept(accept_args({"side": "swap", "ref": "LAT-10", "price": 0, "give_asset": 295}, o), o).ok)

    def test_negative(self):
        c = Ctx(my_offers=())
        o = sell_offer(9001, "LAT-09", 20)
        self.assertEqual(c.check_accept(accept_args(buy_spec("LAT-09", 19), o), o).code, "G11.buy_shape")
        self.assertEqual(c.check_accept(accept_args(buy_spec("LAT-10", 20), o), o).code, "G11.buy_shape")
        b = bid_offer(9002, "LAV-03", 30)
        self.assertEqual(c.check_accept(accept_args(buy_spec("LAV-03", 30), b), b).code, "G11.buy_shape")
        s = team_offer(9004, {"types": ["card:LAT-10"]}, {"assets": [{"id": 422, "kind": "card", "ref": "MAL-04"}]})
        self.assertEqual(c.check_accept(accept_args({"side": "swap", "ref": "LAT-10", "price": 0, "give_asset": 295}, s), s).code,
                         "G11.swap_want_asset")
        s = swap_offer(9003, "LAT-10", "MAL-04")
        self.assertEqual(c.check_accept(accept_args({"side": "swap", "ref": "LAT-10", "price": 0, "give_asset": 422}, s), s).code,
                         "G11.swap_give_ref")   # 422 is MAL-05


class G12Value(unittest.TestCase):
    def test_buy_threshold(self):
        c = Ctx(my_offers=())
        pmax = max_buy_price(c, "LAT-09")
        self.assertGreater(pmax, 10)
        for p in (1, 10, pmax - 1, pmax):
            o = sell_offer(9001, "LAT-09", p)
            self.assertTrue(c.check_accept(accept_args(buy_spec("LAT-09", p), o), o).ok, p)
        for p in (pmax + 1, pmax + 5, 100, 1000):
            o = sell_offer(9001, "LAT-09", p)
            v = c.check_accept(accept_args(buy_spec("LAT-09", p), o), o)
            self.assertFalse(v.ok, p)
            self.assertIn(v.code, ("G12.gain", "G16.cash"))

    def test_sell_into_bid_threshold(self):
        c = Ctx(my_offers=())
        dv = guards.dv_rm(c.world, c.book, c.valuer, "LAV-03", 261)
        pmin = next(p for p in range(1, 200) if p - fee(p) - dv >= 3)
        for p in (pmin, pmin + 1, pmin + 10, 100):
            o = bid_offer(9002, "LAV-03", p)
            self.assertTrue(c.check_accept(accept_args({"side": "sell", "ref": "LAV-03", "price": p, "give_asset": 261}, o), o).ok, p)
        for p in (1, 5, pmin - 2, pmin - 1):
            o = bid_offer(9002, "LAV-03", p)
            self.assertEqual(c.check_accept(accept_args({"side": "sell", "ref": "LAV-03", "price": p, "give_asset": 261}, o), o).code,
                             "G12.gain", p)

    def test_round_trip_and_closer(self):
        c = Ctx(my_offers=())
        o = sell_offer(9001, "LAT-09", 20)
        for prev, ok in ((("sell", 150), False), (("sell", 140), True), (("buy", 199), True), (("sell", 199), False)):
            b = replace(c.book, recent_rastro={"LAT-09": prev})
            self.assertEqual(c.check_accept(accept_args(buy_spec("LAT-09", 20), o), o, book=b).ok, ok, prev)
        # with LAT-09 projected (own bid), LAT-10 closes the page: needs neg >= 20
        c = Ctx(my_offers=tuple(x for x in MY_OFFERS if x["id"] != 2504))
        self.assertTrue(c.valuer.closes_page(c.book.projected, "LAT-10"))
        p20 = max_buy_price(c, "LAT-10", min_gain=20.0)
        o = sell_offer(9005, "LAT-10", p20)
        self.assertTrue(c.check_accept(accept_args(buy_spec("LAT-10", p20), o), o).ok)
        o = sell_offer(9005, "LAT-10", p20 + 1)
        self.assertEqual(c.check_accept(accept_args(buy_spec("LAT-10", p20 + 1), o), o).code, "G12.closer_gain")


def _venue(vid, owner, bps=0, pc=0, status="open"):
    return {"id": vid, "owner": owner, "fee_bps": bps, "fee_per_card": pc, "status": status}


class D2RivalVenues(unittest.TestCase):
    LB = ("t13", "t01", "t02", "t03", "t04", "t12", "t18")

    def ctx(self, **kw):
        kw.setdefault("venues", [_venue("v02", "t12"), _venue("v03", "t13", 100, 0), _venue("v09", "t18"),
                                 _venue("v05", "t07", 0, 0, "closed"), {"venue": "v06", "owner": "t08", "fee_bps": 500,
                                                                         "fee_per_card": 1, "status": "open"}])
        kw.setdefault("leaderboard", self.LB)
        return Ctx(my_offers=(), **kw)

    def test_positive(self):
        c = self.ctx()
        pmax = max_buy_price(c, "LAT-09", min_gain=10.0, bps=0, pc=0)
        for p in (1, 20, pmax):
            o = sell_offer(9001, "LAT-09", p, venue="v02")
            self.assertTrue(c.check_accept(accept_args(buy_spec("LAT-09", p), o, venue="v02"), o).ok, p)
        o = sell_offer(9001, "LAT-09", 20, venue="v06")       # harvest-style "venue" key
        self.assertTrue(c.check_accept(accept_args(buy_spec("LAT-09", 20), o, venue="v06"), o).ok)

    def test_negative(self):
        c = self.ctx()
        pmax = max_buy_price(c, "LAT-09", min_gain=10.0, bps=0, pc=0)
        cases = (("v02", pmax + 1, "G12.gain"), ("v03", 20, "G12.rival_top"), ("v09", 20, "G12.own_venue"),
                 ("v05", 20, "G12.venue_closed"), ("v77", 20, "G12.venue_closed"))
        for vid, p, code in cases:
            o = sell_offer(9001, "LAT-09", p, venue=vid)
            self.assertEqual(c.check_accept(accept_args(buy_spec("LAT-09", p), o, venue=vid), o).code, code, vid)
        c = self.ctx(leaderboard=())
        o = sell_offer(9001, "LAT-09", 20, venue="v02")
        self.assertEqual(c.check_accept(accept_args(buy_spec("LAT-09", 20), o, venue="v02"), o).code, "G12.rank_unknown")

    def test_venue_fee_is_charged(self):
        c = self.ctx(venues=[_venue("v02", "t12", 2000, 5)])
        p = max_buy_price(c, "LAT-09", min_gain=10.0, bps=2000, pc=5)
        o = sell_offer(9001, "LAT-09", p + 1, venue="v02")
        self.assertEqual(c.check_accept(accept_args(buy_spec("LAT-09", p + 1), o, venue="v02"), o).code, "G12.gain")
        o = sell_offer(9001, "LAT-09", p, venue="v02")
        self.assertTrue(c.check_accept(accept_args(buy_spec("LAT-09", p), o, venue="v02"), o).ok)


class G13Protected(unittest.TestCase):
    def test_harvest_watch_targets(self):
        """INV-06 on the harvest: the only protected refs over-committed are LAT-01 and LAT-05, and the
        first-expiring offers for them are exactly {2463, 1652}."""
        c = Ctx(my_offers=MY_OFFERS)
        over = {r for r in c.book.held if guards.free(c.book, r, c.world) < c.book.keep.get(r, 0)}
        self.assertEqual(over, {"LAT-01", "LAT-05"})
        first = set()
        for ref in over:
            mine = [o for o in MY_OFFERS if o["give"]["assets"] and o["give"]["assets"][0]["ref"] == ref]
            first.add(min(mine, key=lambda o: o["expires_tick"])["id"])
        self.assertEqual(first, {2463, 1652})

    def test_positive(self):
        c = Ctx(my_offers=())
        for ref, aid, p in (("MAL-04", 295, 9), ("LAV-03", 261, 9), ("LAT-01", 424, 9), ("LAT-05", 508, 9)):
            self.assertTrue(c.check(c.sell(ref, aid, p)).ok, ref)

    def test_negative(self):
        c = Ctx(my_offers=MY_OFFERS)
        for ref, aid, code in (("SAL-04", 256, "G13.protected"), ("LAT-03", 313, "G13.protected"),
                               ("LAV-03", 261, "G13.listed"), ("LAT-01", 424, "G13.listed"),
                               ("MAL-04", 999, "G13.not_ours"), ("MAL-05", 295, "G13.asset_ref")):
            self.assertEqual(c.check(c.sell(ref, aid, 300 if ref.startswith("SAL") else 9)).code, code, ref)

    def test_running_book_blocks_second_copy(self):
        c = Ctx(my_offers=())
        first = c.sell("LAT-01", 379, 9)
        self.assertTrue(c.check(first).ok)
        b = guards.apply(c.book, first, Outcome("x", "would"))
        self.assertEqual(c.check(c.sell("LAT-01", 424, 9), book=b).code, "G13.protected")

    def test_swap_respects_protection(self):
        c = Ctx(my_offers=())
        self.assertEqual(c.check(c.swap("SAL-04", 256, "LAT-09")).code, "G13.protected")
        s = swap_offer(9003, "LAT-10", "LAT-03")
        v = c.check_accept(accept_args({"side": "swap", "ref": "LAT-10", "price": 0, "give_asset": 313}, s), s)
        self.assertEqual(v.code, "G13.protected")


def _ret_ctx(**kw):
    me = copy.deepcopy(ME)
    me["assets"].append({"id": 901, "kind": "card", "ref": "RET-03", "rarity": "common", "set": "RET",
                         "your_value": 13.0})
    me["assets"].append({"id": 902, "kind": "card", "ref": "RET-09", "rarity": "rare", "set": "RET",
                         "your_value": 13.0})
    return Ctx(me=me, my_offers=(), **kw)


class J13Resupply(unittest.TestCase):
    def args(self, ref="RET-03", aid=901, p=60, offer=None):
        return accept_args({"side": "sell", "ref": ref, "price": p, "give_asset": aid},
                           offer or bid_offer(9010, ref, p), resupply=True)

    def test_positive(self):
        for p in (40, 60, 80, 99):
            c = _ret_ctx()
            o = bid_offer(9010, "RET-03", p)
            self.assertTrue(c.check_accept(self.args(p=p), o).ok, (p, c.check_accept(self.args(p=p), o)))

    def test_negative(self):
        c = _ret_ctx(frozen={"RET": "RET-03"})
        o = bid_offer(9010, "RET-03", 60)
        self.assertEqual(c.check_accept(self.args(), o).code, "G13.j13_closer")
        c = _ret_ctx()
        o9 = bid_offer(9010, "RET-09", 60)
        self.assertEqual(c.check_accept(self.args("RET-09", 902), o9).code, "G13.j13_rarity")
        b = replace(c.book, dealer_block={"abuela": 500})
        self.assertEqual(c.check_accept(self.args(), o, book=b).code, "G13.j13_abuela_blocked")
        o1 = bid_offer(9010, "RET-03", 60, expires_tick=201)
        self.assertEqual(c.check_accept(self.args(offer=o1), o1).code, "G13.j13_expiry")
        o = bid_offer(9010, "RET-03", 20)
        self.assertEqual(c.check_accept(accept_args({"side": "sell", "ref": "RET-03", "price": 20, "give_asset": 901}, o,
                                                    resupply=True), o).code, "G12.gain")      # < RESUPPLY_MIN
        o = bid_offer(9010, "SAL-04", 300)
        self.assertEqual(c.check_accept(accept_args({"side": "sell", "ref": "SAL-04", "price": 300, "give_asset": 256}, o,
                                                    resupply=True), o).code, "G13.j13_set")
        o = bid_offer(9010, "RET-03", 60)
        self.assertEqual(c.check_accept(accept_args({"side": "sell", "ref": "RET-03", "price": 60, "give_asset": 901}, o), o).code,
                         "G13.protected")                                                   # no resupply flag


def _pack_me():
    me = copy.deepcopy(ME)
    me["assets"].append({"id": 950, "kind": "pack", "ref": "sobre_barrio"})
    return me


class G14Pack(unittest.TestCase):
    def test_positive(self):
        c = Ctx(me=_pack_me())
        self.assertEqual(c.book.packs, ("sobre_barrio",))
        self.assertTrue(c.book.delivery_risk)
        for it in (c.intent("cancel", offer_id=2463, ref=None), c.intent("open_pack", asset_id=950),
                   c.intent("cancel", offer_id=1652, ref="LAT-05"), c.intent("cancel", offer_id=2592, ref=None)):
            self.assertTrue(c.check(it).ok, it.kind)

    def test_negative(self):
        c = Ctx(me=_pack_me(), my_offers=())
        o = sell_offer(9001, "LAT-09", 20)
        self.assertEqual(c.check_accept(accept_args(buy_spec("LAT-09", 20), o), o).code, "G14.pack")
        for it in (c.sell("MAL-04", 295, 9), c.bid("LAT-09", 20),
                   c.intent("open_thread", dealer="abuela", side="buy", ref="RET-01", asset_ids=(), limit=10)):
            self.assertEqual(c.check(it).code, "G14.pack", it.kind)


class G15OnePath(unittest.TestCase):
    def test_negative(self):
        c = Ctx(my_offers=MY_OFFERS)                       # own bids 2503 (LAT-09), 2504 (LAT-10)
        o = sell_offer(9001, "LAT-09", 20)
        self.assertEqual(c.check_accept(accept_args(buy_spec("LAT-09", 20), o), o).code, "G15.path")
        self.assertEqual(c.check(c.bid("LAT-09", 20)).code, "G21.dup")
        c = Ctx(my_offers=())
        first = c.bid("LAT-09", 20)
        b = guards.apply(c.book, first, Outcome("x", "sent"))
        self.assertEqual(c.check(c.bid("LAT-09", 25), book=b).code, "G21.dup")
        b = guards.apply(c.book, c.intent("open_thread", dealer="chato", side="buy", ref="LAT-09", asset_ids=(),
                                          limit=40), Outcome("x", "unknown"))
        self.assertEqual(c.check(c.bid("LAT-09", 20), book=b).code, "G15.path")

    def test_positive(self):
        c = Ctx(my_offers=())
        b = guards.apply(c.book, c.bid("LAT-09", 20), Outcome("x", "would"))
        for it in (c.bid("LAV-05", 3), c.bid("LAV-06", 2), c.bid("MAL-07", 1)):
            self.assertTrue(c.check(it, book=b).ok, it.args)
        b2 = guards.apply(c.book, c.bid("LAT-09", 20), Outcome("x", "refused"))
        self.assertTrue(c.check(c.bid("LAT-09", 20), book=b2).ok)


class G16Cash(unittest.TestCase):
    def test_positive(self):
        c = Ctx(my_offers=())
        free_cash = c.book.cash_free
        self.assertEqual(free_cash, 250)
        for ref, p in (("LAT-09", 30), ("LAT-10", 30)):
            self.assertTrue(c.check(c.bid(ref, p)).ok)
        b = replace(c.book, cash_free=30)
        self.assertTrue(c.check(c.bid("LAT-09", 30), book=b).ok)
        o = sell_offer(9001, "LAT-09", 20)
        self.assertTrue(c.check_accept(accept_args(buy_spec("LAT-09", 20), o), o, book=replace(c.book, cash_free=22)).ok)

    def test_negative(self):
        c = Ctx(my_offers=())
        b = replace(c.book, cash_free=29)
        self.assertEqual(c.check(c.bid("LAT-09", 30), book=b).code, "G16.cash")
        o = sell_offer(9001, "LAT-09", 20)
        self.assertEqual(c.check_accept(accept_args(buy_spec("LAT-09", 20), o), o, book=replace(c.book, cash_free=21)).code,
                         "G16.cash")                         # 20 + fee 2
        b = replace(c.book, cash_free=50)
        b = guards.apply(b, c.bid("LAT-09", 30), Outcome("x", "sent"))
        self.assertEqual(c.check(c.bid("LAT-10", 30, closer=True), book=b).code, "G16.cash")   # INV-07: two bids > cash_free
        b = replace(c.book, cash_free=-1)
        self.assertEqual(c.check(c.bid("LAT-09", 1), book=b).code, "G16.cash")


class G20OwnSale(unittest.TestCase):
    def test_positive_and_negative(self):
        c = Ctx(my_offers=())
        dv = guards.dv_rm(c.world, c.book, c.valuer, "LAV-03", 261)
        lo = math.ceil(dv + 2)
        hi = math.floor(4 * 10 * ME["affinity"]["LAV"])
        for p in (lo, lo + 1, (lo + hi) // 2, hi):
            self.assertTrue(c.check(c.sell("LAV-03", 261, p)).ok, p)
        for p in (1, lo - 1, hi + 1, 1000):
            v = c.check(c.sell("LAV-03", 261, p))
            self.assertIn(v.code, ("G20.low", "G20.high"), p)

    def test_round_trip_sale(self):
        c = Ctx(my_offers=())
        b = replace(c.book, recent_rastro={"LAV-03": ("buy", 190)})
        self.assertEqual(c.check(c.sell("LAV-03", 261, 12), book=b).code, "G12.round_trip")


class G21OwnBid(unittest.TestCase):
    def test_normal(self):
        c = Ctx(my_offers=())
        dv = guards.dv_add(c.world, c.book, c.valuer, "LAT-09")
        top = math.floor(dv - 3)
        for p in (1, 30, top - 1, top):
            self.assertTrue(c.check(c.bid("LAT-09", p)).ok, p)
        for p in (top + 1, top + 2, 200, 10 ** 6):
            self.assertFalse(c.check(c.bid("LAT-09", p)).ok, p)

    def test_closer(self):
        c = Ctx(my_offers=tuple(x for x in MY_OFFERS if x["id"] != 2504))
        dv = guards.dv_add(c.world, c.book, c.valuer, "LAT-10")
        top = math.floor(dv - 20)
        for p in (1, 20, top - 1, top):
            self.assertTrue(c.check(c.bid("LAT-10", p, closer=True)).ok, p)
        self.assertEqual(c.check(c.bid("LAT-10", top + 1, closer=True)).code, "G21.closer_high")
        self.assertEqual(c.check(c.bid("LAT-10", 10, closer=False)).code, "G21.closer_flag")
        risky = replace(c.book, delivery_risk=True)
        self.assertEqual(c.check(c.bid("LAT-10", 10, closer=True), book=risky).code, "G21.delivery_risk")
        grant = {"now_hours": 5.0, "upcoming": [{"at_hours": 5.02, "action": "grant_all", "params": {"packs": ["sobre_barrio"]}}]}
        c2 = Ctx(my_offers=tuple(x for x in MY_OFFERS if x["id"] != 2504), schedule=grant)
        self.assertTrue(c2.book.delivery_risk)                          # INV-23
        self.assertEqual(c2.check(c2.bid("LAT-10", 10, closer=True)).code, "G21.delivery_risk")


class G22Expiry(unittest.TestCase):
    def test_positive_and_negative(self):
        c = Ctx(my_offers=())
        for e in (4, 60, 120, 240):
            self.assertTrue(c.check(c.sell("MAL-04", 295, 9, expires=e)).ok, e)
        for e in (1, 3, 241, 10 ** 4):
            self.assertEqual(c.check(c.sell("MAL-04", 295, 9, expires=e)).code, "G22.expiry", e)


class G23Cancel(unittest.TestCase):
    def test_positive(self):
        c = Ctx(my_offers=MY_OFFERS)
        for oid in (2463, 1652, 2503, 2592):
            self.assertTrue(c.check(c.intent("cancel", offer_id=oid, ref=None)).ok, oid)

    def test_negative(self):
        gone = dict(MY_OFFERS[0], status="cancelled")
        c = Ctx(my_offers=(gone,) + MY_OFFERS[1:])
        self.assertEqual(c.check(c.intent("cancel", offer_id=gone["id"], ref=None)).code, "G23.not_open")
        for oid in (9999, 2470, 1, 0):
            self.assertEqual(c.check(c.intent("cancel", offer_id=oid, ref=None)).code, "G23.not_ours", oid)


def _thread(tid, status="open", team="t18", with_="abuela", topic=None):
    return {"id": tid, "team": team, "with": with_, "status": status, "topic": topic or {"buy": {"card": "RET-01"}},
            "messages": [], "standing_offers": [], "created_tick": 190}


class G33CloseThread(unittest.TestCase):
    def test_positive(self):
        c = Ctx(threads={5: _thread(5), 6: _thread(6, with_="chato"), 7: _thread(7, topic={"sell": {"assets": [295]}}),
                         8: _thread(8, team=None)})
        for tid in (5, 6, 7, 8):
            self.assertTrue(c.check(c.intent("close_thread", thread_id=tid, ref=None)).ok, tid)

    def test_negative(self):
        c = Ctx(threads={5: _thread(5, status="deal"), 6: _thread(6, status="closed"), 7: _thread(7, team="t07")})
        for tid, code in ((5, "G33.not_open"), (6, "G33.not_open"), (7, "G33.not_open"), (99, "G33.not_ours")):
            self.assertEqual(c.check(c.intent("close_thread", thread_id=tid, ref=None)).code, code, tid)


class G40OpenPack(unittest.TestCase):
    def test_positive(self):
        for threads in ({}, {5: _thread(5, status="closed")}, {6: _thread(6, topic={"sell": {"assets": [295]}})},
                        {7: _thread(7, status="deal")}):
            c = Ctx(me=_pack_me(), threads=threads)
            self.assertTrue(c.check(c.intent("open_pack", asset_id=950)).ok, threads)

    def test_negative(self):
        c = Ctx(me=_pack_me(), threads={5: _thread(5)})
        self.assertEqual(c.check(c.intent("open_pack", asset_id=950)).code, "G40.threads_open")
        c = Ctx(me=_pack_me())
        for aid in (295, 12345):
            self.assertEqual(c.check(c.intent("open_pack", asset_id=aid)).code, "G40.not_pack", aid)
        b = guards.apply(c.book, c.intent("open_thread", dealer="abuela", side="buy", ref="RET-01", asset_ids=(),
                                          limit=10), Outcome("x", "unknown"))
        self.assertEqual(c.check(c.intent("open_pack", asset_id=950), book=b).code, "G40.threads_open")


class D1SwapMaker(unittest.TestCase):
    def test_positive(self):
        c = Ctx(my_offers=())
        for ref, aid, want in (("MAL-04", 295, "LAT-09"), ("LAV-03", 261, "LAT-10"), ("LAT-01", 424, "LAT-09"),
                               ("MAL-05", 422, "LAT-10")):
            self.assertTrue(c.check(c.swap(ref, aid, want)).ok, ref)

    def test_negative(self):
        c = Ctx(my_offers=())
        self.assertEqual(c.check(c.swap("SAL-10", 180, "LAT-09")).code, "G13.protected")
        self.assertEqual(c.check(c.swap("LAT-07", 267, "LAV-05")).code, "G13.protected")
        self.assertEqual(c.check(c.swap("LAV-04", 423, "MAL-01")).code, "G12.swap_gain")     # 7 for 5: loss
        c2 = Ctx(my_offers=MY_OFFERS)
        self.assertEqual(c2.check(c2.swap("MAL-04", 295, "LAT-09")).code, "G13.listed")
        c3 = Ctx(my_offers=DEFAULT + tuple(o for o in MY_OFFERS if o["id"] == 2503))   # own bid on LAT-09
        self.assertEqual(c3.check(c3.swap("MAL-04", 295, "LAT-09")).code, "G15.path")


class BookAndApply(unittest.TestCase):
    def test_build_from_harvest(self):
        c = Ctx(my_offers=MY_OFFERS, t_hours=2.65)
        b = c.book
        self.assertEqual((b.cash, b.cash_free), (260, 260 - 62 - 62 - 10))
        self.assertEqual(dict(b.own_bids), {"LAT-09": 2503, "LAT-10": 2504})
        self.assertEqual(dict(b.bid_band), {2503: 0.0, 2504: 0.0})
        self.assertEqual(b.listed["LAT-01"], 2)
        self.assertEqual(b.keep.get("LAV-03", 0), 0)
        self.assertEqual(b.keep["SAL-04"], 1)
        self.assertEqual(b.projected["LAT-09"], 1)
        self.assertTrue(b.valuation_ok)
        self.assertFalse(b.delivery_risk)

    def test_apply_effects(self):
        c = Ctx(my_offers=())
        b0 = c.book
        b = guards.apply(b0, c.bid("LAT-09", 30), Outcome("x", "sent"))
        self.assertEqual((b.cash_free, b.paths["LAT-09"], b.projected["LAT-09"]), (b0.cash_free - 30, 1, 1))
        b = guards.apply(b, c.sell("MAL-04", 295, 9), Outcome("y", "would"))
        self.assertIn(295, b.listed_assets)
        self.assertEqual(b.listed["MAL-04"], 1)
        o = sell_offer(9001, "LAT-10", 20)
        acc = c.intent("accept", **accept_args(buy_spec("LAT-10", 20), o))
        b = guards.apply(b, acc, Outcome("z", "unknown"))
        self.assertEqual((b.pending_in["LAT-10"], b.cash_free), (1, b0.cash_free - 30 - 22))
        for st in ("refused", "deferred"):
            self.assertIs(guards.apply(b, c.bid("RET-01", 3), Outcome("w", st)), b)
        same = guards.apply(b, c.intent("cancel", offer_id=2463, ref=None), Outcome("c", "sent"))
        self.assertEqual(same.cash_free, b.cash_free)          # releases wait for the server

    def test_journal_pending_and_unknown(self):
        class J:
            def rows(self, kinds):
                return iter([{"kind": "intent", "intent_kind": "accept", "id": "i1", "tick": 199,
                              "args": accept_args(buy_spec("LAT-09", 20), sell_offer(9001, "LAT-09", 20))}])

            def pending(self):
                return [{"kind": "intent", "intent_kind": "accept", "id": "i1", "tick": 199, "pending": "unknown",
                         "args": accept_args(buy_spec("LAT-09", 20), sell_offer(9001, "LAT-09", 20))}]

            def unknown_domains(self):
                return {"offer:9001"}
        c = Ctx(my_offers=(), journal=J())
        self.assertIn("offer:9001", c.book.unknown_domains)
        self.assertEqual((c.book.pending_in["LAT-09"], c.book.paths["LAT-09"]), (1, 1))
        self.assertEqual(c.book.cash_free, 260 - 10 - 22)


class SourcesTable(unittest.TestCase):
    def test_table_matches_spec(self):
        S = guards.SOURCES
        self.assertEqual(S["cancel"], {"clock", "me/offers"})
        self.assertEqual(S["close_thread"], {"clock", "me/threads"})
        self.assertEqual(S["list_offer"], {"clock", "me", "me/offers", "me/threads", "board"})
        self.assertEqual(S["accept"], S["list_offer"])
        self.assertEqual(S["accept_dealer"], {"clock", "me", "me/offers", "me/threads", "threads"})
        self.assertEqual(S["open_pack"], {"clock", "me", "me/threads"})
        self.assertEqual(S["duel_accept"], {"clock", "duels"})
        self.assertTrue({"boards", "venues", "leaderboard"} <= S["accept_venue"])


if __name__ == "__main__":
    unittest.main()


class ThreadOfferCountedOnce(unittest.TestCase):
    """Live 3 Oct t191: our standing offer in a dealer thread is also in my_offers (thread=360). Counting it twice
    valued RET-09 as a 2nd copy (91 -> 22.8), doubled the commitment and made hygiene cancel every dealer thread."""

    def test_projected_and_commit_once(self):
        offer = {"id": 3238, "maker": "t18", "to": "chato", "venue": None, "thread": 360, "status": "open",
                 "give": {"cash": 70, "assets": [], "types": []},
                 "want": {"cash": 0, "assets": [], "types": ["card:RET-09"]}, "expires_tick": None}
        th = {"id": 360, "team": "t18", "with": "chato", "status": "open", "topic": {"buy": {"card": "RET-09"}},
              "messages": [{"tick": 190, "sender": "t18", "price": 70, "offer": offer}], "standing_offers": [],
              "created_tick": 189}
        base = Ctx(my_offers=())
        c = Ctx(my_offers=(offer,), threads={360: th})
        self.assertEqual(c.book.projected.get("RET-09", 0), base.book.projected.get("RET-09", 0) + 1)
        self.assertEqual(base.book.cash_free - c.book.cash_free, 70)
        from agent.tactics import hygiene
        self.assertEqual(hygiene.bid_watch(c.world, c.book, c.valuer, c.cfg, PLAN), [])


class ServerClosedDealerThreads(unittest.TestCase):
    """closed_reason cooloff / sold_out / persona_budget (server-ended threads) block reopening that dealer."""
    PLAN = dict(PLAN, day_end_hours={"sat": 13.28, "sun": 20.0})

    @staticmethod
    def th(tid, dealer, reason, last, until=None):
        t = {"id": tid, "kind": "persona", "team": "t18", "with": dealer, "topic": {"buy": {"card": "SAL-11"}},
             "status": "walked", "created_tick": last - 2, "standing_offers": [], "closed_reason": reason,
             "messages": [{"id": tid * 10, "tick": last, "sender": dealer}]}
        if until is not None:
            t["until_tick"] = until
        return t

    def test_blocks(self):
        ths = {1: self.th(1, "pilar", "persona_budget", 190), 2: self.th(2, "picaros", "cooloff", 150, until=260),
               3: self.th(3, "chato", "sold_out", 150), 4: self.th(4, "abuela", "sold_out", 50),
               5: self.th(5, "abuela", "final_offer_refused", 199)}
        b = Ctx(threads=ths, plan=self.PLAN, t_hours=5.5).book    # tick 200, 30 s ticks: this hour = ticks 140..260
        self.assertEqual(dict(b.dealer_block), {"pilar": 260, "picaros": 260, "chato": 260})   # until the hour ends

    def test_persona_budget_resets_with_the_game_hour(self):
        # RULES: "never offers more than it can still pay this hour" -> a budget walk-out blocks to the end of
        # that game hour; at t 14.0 a new hour began at tick 200, so threads ended at 150 and 60 block nothing
        ths = {1: self.th(1, "pilar", "persona_budget", 150), 2: self.th(2, "chato", "persona_budget", 60)}
        b = Ctx(threads=ths, plan=self.PLAN, t_hours=14.0).book    # tick 200
        self.assertEqual(dict(b.dealer_block), {})
        b = Ctx(threads=ths, plan=self.PLAN, t_hours=14.5).book    # this hour began at tick 140: pilar (150) blocked to 260
        self.assertEqual(dict(b.dealer_block), {"pilar": 260})


class TicksPerHour(unittest.TestCase):
    """Live Sat ticks are 30 s (120 per game hour), Sun 15 s (240): never the Friday constant 60."""

    def test_derived_from_tick_seconds(self):
        from types import SimpleNamespace as NS
        cfg = guards.Cfg()
        self.assertEqual([guards.ticks_per_hour(NS(tick_seconds=s), cfg) for s in (60.0, 30.0, 15.0)], [60, 120, 240])
        self.assertEqual(guards.ticks_per_hour(NS(tick_seconds=None), cfg), cfg.TICKS_PER_GAME_HOUR)
        self.assertEqual(guards.ticks_per_hour(NS(tick_seconds=0), cfg), cfg.TICKS_PER_GAME_HOUR)
        # grant 0.04 h ahead, lookahead 3 ticks: 3/120 = 0.025 h (Sat) -> not soon; 3/60 = 0.05 h (Fri) -> soon
        sched = {"upcoming": [{"action": "grant", "at_hours": 10.04, "params": {"packs": ["sobre"]}}]}
        sat = NS(tick_seconds=30.0, t_hours=10.0, schedule=sched)
        fri = NS(tick_seconds=60.0, t_hours=10.0, schedule=sched)
        self.assertFalse(guards._grant_soon(sat, 3, cfg))
        self.assertTrue(guards._grant_soon(fri, 3, cfg))


class _OpenedJournal:
    """Journal with one open_thread intent (limit) answered ok with thread `tid`; extra rows appended."""

    def __init__(self, tid, limit, dealer="chato", ref="RET-10", extra=()):
        self._rows = [{"kind": "intent", "id": "o1", "intent_kind": "open_thread", "tick": 207,
                       "args": {"dealer": dealer, "side": "buy", "ref": ref, "asset_ids": [], "limit": limit}},
                      {"kind": "result", "id": "o1", "status": "ok", "code": None, "response": {"id": tid},
                       "tick": 207}] + list(extra)

    def rows(self, kinds):
        return iter([r for r in self._rows if r["kind"] in kinds])

    def pending(self):
        return []

    def unknown_domains(self):
        return set()


class _UnsettledJournal:
    """A dealer buy of RET-01 at 9 accepted at tick 210 (result ok), its accepted_unsettled row still pending."""

    def __init__(self):
        self._rows = [{"kind": "intent", "id": "a1", "intent_kind": "accept", "tick": 210,
                       "args": {"source": "dealer", "side": "buy", "ref": "RET-01", "price": 9, "thread_id": 5,
                                "offer_id": 77}},
                      {"kind": "result", "id": "a1", "status": "ok", "code": None, "response": {"queued": True},
                       "tick": 210}]

    def rows(self, kinds):
        return iter([r for r in self._rows if r["kind"] in kinds])

    def pending(self):
        return [{"kind": "accepted_unsettled", "id": "a1", "offer_id": 77, "ref": "RET-01", "price": 9,
                 "until_tick": 212, "tick": 210, "pending": "accepted_unsettled"}]

    def unknown_domains(self):
        return set()


class RefusalBlocksFromTheJournal(unittest.TestCase):
    def test_gate_end_of_hour_block_is_rebuilt(self):
        # the Gate journals {dealer: end of the game hour} on a persona_budget / sold_out / cooloff refusal;
        # build_book must rebuild that block, not a rolling hour from the refusal tick
        extra = [{"kind": "intent", "id": "o2", "intent_kind": "open_thread", "tick": 205,
                  "args": {"dealer": "picaros", "side": "buy", "ref": "CHA-09", "asset_ids": [], "limit": 60}},
                 {"kind": "result", "id": "o2", "status": "refused", "code": "persona_budget", "response": {},
                  "tick": 205, "dealer_block": {"picaros": 230}}]
        b = Ctx(my_offers=(), journal=_OpenedJournal(392, 90, extra=extra)).book
        self.assertEqual(b.dealer_block.get("picaros"), 230)


class AcceptedUnsettledCountedOnce(unittest.TestCase):
    """Pre-Sunday audit: the server settles an accept at T+1 (settles_at_tick); from then on the World shows the card and
    the cash, so the pending row must not add price / projected / paths again (Sat ticks 212-213: cash_free < 0)."""

    def test_after_settlement_tick_counted_once(self):
        plain = Ctx(tick=211, my_offers=()).book
        b = Ctx(tick=211, my_offers=(), journal=_UnsettledJournal()).book
        self.assertEqual(b.cash_free, plain.cash_free)
        self.assertEqual(b.projected.get("RET-01", 0), plain.projected.get("RET-01", 0))
        self.assertEqual(b.paths.get("RET-01", 0), plain.paths.get("RET-01", 0))

    def test_same_tick_still_pending(self):
        plain = Ctx(tick=210, my_offers=()).book
        b = Ctx(tick=210, my_offers=(), journal=_UnsettledJournal()).book
        self.assertEqual(b.cash_free, plain.cash_free - 9)
        self.assertEqual(b.projected.get("RET-01", 0), plain.projected.get("RET-01", 0) + 1)

    def test_me_down_keeps_the_reservation(self):
        plain = Ctx(tick=211, my_offers=(), down={"me"}).book
        b = Ctx(tick=211, my_offers=(), down={"me"}, journal=_UnsettledJournal()).book
        self.assertEqual(b.paths.get("RET-01", 0), plain.paths.get("RET-01", 0) + 1)


def _live_thread(tid=392, ref="RET-10", ask=95, ask_types=None, dealer="chato"):
    """Live 3 Oct t210 shape: messages carry only id/offer/sender/tick (no top-level price)."""
    def offer(oid, maker, cash_give, cash_want, types_give, types_want, status, tick):
        return {"id": oid, "maker": maker, "to": "t18" if maker != "t18" else dealer, "venue": None, "thread": tid,
                "status": status, "final": False, "created_tick": tick, "expires_tick": tick + 4,
                "give": {"cash": cash_give, "assets": [], "types": types_give},
                "want": {"cash": cash_want, "assets": [], "types": types_want}}
    mine0 = offer(3506, "t18", 70, 0, [], [f"card:{ref}"], "cancelled", 208)
    mine1 = offer(3515, "t18", 74, 0, [], [f"card:{ref}"], "open", 209)
    hers = offer(3519, dealer, 0, ask, ask_types or [f"card:{ref}"], [], "open", 210)
    msgs = [{"id": 1, "offer": mine0, "sender": "t18", "tick": 208}, {"id": 2, "offer": mine1, "sender": "t18", "tick": 209},
            {"id": 3, "offer": hers, "sender": dealer, "tick": 210}]
    return {"id": tid, "team": "t18", "with": dealer, "status": "open", "topic": {"buy": {"card": ref}},
            "created_tick": 207, "messages": msgs, "standing_offers": [mine1, hers]}, mine1


class ThreadPricesAndReserve(unittest.TestCase):
    def test_prices_read_from_the_message_offer(self):
        th, mine = _live_thread()
        c = Ctx(my_offers=(mine,), threads={392: th})
        self.assertEqual(c.book.thread_prices[392], (70, 74))

    def test_reserve_capped_at_thread_limit(self):
        base = Ctx(my_offers=())
        th, mine = _live_thread(ask=95)                       # chato asks 95 on a limit-90 thread
        c = Ctx(my_offers=(mine,), threads={392: th}, journal=_OpenedJournal(392, 90))
        self.assertEqual(base.book.cash_free - c.book.cash_free, 90)
        unknown = Ctx(my_offers=(mine,), threads={392: th})   # no opening limit in the journal: full max (fail closed)
        self.assertEqual(base.book.cash_free - unknown.book.cash_free, 95)

    def test_trick_offer_not_reserved(self):
        base = Ctx(my_offers=())
        th, mine = _live_thread(ask=130, ask_types=["card:LAT-06"], dealer="picaros")   # another card: never ours
        c = Ctx(my_offers=(mine,), threads={392: th}, journal=_OpenedJournal(392, 160, "picaros"))
        self.assertEqual(base.book.cash_free - c.book.cash_free, 74)
        self.assertEqual(guards._thread_standing(th), 74)


class ClosedThreadBlocks(unittest.TestCase):
    """closed_reason / until_tick of our closed dealer threads -> dealer_block (the tactic must not reopen them)."""

    @staticmethod
    def _closed(tid, dealer, reason, last_tick, **kw):
        return {"id": tid, "team": "t18", "with": dealer, "status": "walked", "closed_reason": reason,
                "topic": {"buy": {"card": "RET-06"}}, "created_tick": last_tick - 3, "standing_offers": [],
                "messages": [{"id": 1, "tick": last_tick, "sender": dealer}], **kw}

    def test_blocks_from_closed_reason(self):
        # tick 200 at t_hours 5.5 with 30 s ticks: this hour began at tick 140 and ends at 260
        th = {1: self._closed(1, "abuela", "persona_budget", 190),
              2: self._closed(2, "chato", "cooloff", 195, until_tick=230),
              3: self._closed(3, "picaros", "final_offer_refused", 198),
              4: self._closed(4, "pilar", "persona_quota", 130),           # previous hour: quota reset
              5: self._closed(5, "ernesto", "cooloff", 150, until_tick=170)}
        b = Ctx(tick=200, t_hours=5.5, threads=th).book
        self.assertEqual(dict(b.dealer_block), {"abuela": 260, "chato": 230})

    def test_world_keeps_until_tick(self):
        from agent import world as W
        t, _ = W._p_thread(self._closed(2, "chato", "cooloff", 195, until_tick=230))
        self.assertEqual((t["closed_reason"], t["until_tick"]), ("cooloff", 230))


class PackTypesOnlyPacks(unittest.TestCase):
    def test_unknown_asset_kind_is_not_a_pack(self):
        me = copy.deepcopy(ME)
        me["assets"].append({"id": 990, "kind": "badge", "ref": "egg"})
        c = Ctx(me=me)
        self.assertEqual(c.book.packs, ())
        self.assertTrue(c.check(c.bid("RET-01", 3)).code != "G14.pack")
        me["assets"].append({"id": 991, "kind": "pack", "ref": "sobre_barrio"})
        self.assertEqual(Ctx(me=me).book.packs, ("sobre_barrio",))


class TicksPerGameHour(unittest.TestCase):
    """A game hour is a wall hour: 3600 / tick_seconds ticks (60 hard-coded made Saturday's 30 s hour 30 min)."""

    def test_derived_from_tick_seconds(self):
        from agent import gate
        for ts, tph in ((60.0, 60), (30.0, 120), (15.0, 240)):
            w = replace(Ctx().world, tick_seconds=ts)
            self.assertEqual(guards.ticks_per_hour(w), tph)
            self.assertEqual(gate._ticks_per_hour(w), tph)
        self.assertEqual(guards.ticks_per_hour(replace(Ctx().world, tick_seconds=0)), 60)
        self.assertEqual(gate._ticks_per_hour(replace(Ctx().world, tick_seconds=float("nan"))), 60)

    def test_deals_hour_window_at_30s_ticks(self):
        deal = {"id": 5, "team": "t18", "with": "abuela", "status": "deal", "topic": {"buy": {"card": "RET-06"}},
                "created_tick": 120, "messages": [], "standing_offers": []}
        self.assertEqual(Ctx(tick=200, threads={5: deal}).book.dealer_deals_hour.get("abuela"), 1)   # 80 < 120
        self.assertIsNone(Ctx(tick=241, threads={5: deal}).book.dealer_deals_hour.get("abuela"))
