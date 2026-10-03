"""M17: replay of Friday's real deals through today's guards (spec §10 test_replay_friday, `bazaar.py replay-friday`).

Each Friday deal is rebuilt at the tick it happened: our holdings just before it (tests/fixtures/harvest/
cards_all.json histories), Friday's released sets {LAV, MAL, LAT, SAL}, minted counts as they were then, the
dealer thread (for dealer deals) or our own bid (for SAL-10). The intent goes through the real guards.check
(M4a + M4b talk for dealer accepts). Criteria:
- REFUSED: the sobre at 23 (pack purchase: not even expressible), LAT-01 at 10, LAT-06 at 22 with the pack in hand,
  LAT-08 at 32, the sale of LAV-06 at 13 (the five Friday losses, P-05), and LAT-03 at 9.
- APPROVED: SAL-02 at 9, SAL-08 at 24 and SAL-10 at 80 as a closer bid (80 <= floor(149.875 - 20) = 129).
- Friday duels: none of our 108 messages... see TestFridayDuels (only messages whose limit is known are judged).

NOTES (M17): deals are rebuilt from cards_all + the price table of test_sim (feed settlements). Cash is set to 400
(cash was never the binding constraint on Friday). The dealer thread limit is set to the deal price, so a refusal
can only come from value/pack/protection guards, never from a limit we would not have set.
"""
from __future__ import annotations

import collections
import copy
import dataclasses
import json
import unittest
from pathlib import Path
from types import MappingProxyType

import tests  # noqa: F401  (test isolation)
from agent import guards
from agent.contracts import FRIDAY, Prediction, Verdict, World, make_intent
from agent.valuation import Valuer

HARVEST = Path(__file__).resolve().parent / "fixtures" / "harvest"


def _load(name):
    return json.loads((HARVEST / name).read_text(encoding="utf-8"))


CATALOG = _load("catalog.json")
ME = _load("me.json")
CARDS_ALL = _load("cards_all.json")
FRIDAY_RELEASED = frozenset({"LAV", "MAL", "LAT", "SAL"})
PLAN = {"protect_sets": ["SAL", "RET", "CHA", "LAT"], "grant_lookahead_ticks": 3}
PRED0 = Prediction(0.0, 0.0, "0", 0, None, "test")
TID = 77


def holdings_before(tick: int) -> list:
    out = []
    for a in CARDS_ALL.values():
        own = None
        for h in a["history"]:
            if h["tick"] < tick:
                own = h["to"]
        if own == "t18":
            out.append({"id": a["id"], "kind": a["kind"], "ref": a["ref"]})
    return sorted(out, key=lambda x: x["id"])


def minted_before(tick: int) -> collections.Counter:
    m = collections.Counter()
    for a in CARDS_ALL.values():
        if a["kind"] == "card" and a["history"][0]["tick"] < tick:
            m[a["ref"]] += 1
    return m


class FridayValuer(Valuer):
    """The real Valuer with minted counts as they were at the deal's tick (pack EV depends on them)."""

    def __init__(self, minted):
        super().__init__(CATALOG, ME["affinity"], FRIDAY_RELEASED)
        self._m = minted

    def delta_add(self, counts, ref, packs=(), minted=None):
        return super().delta_add(counts, ref, packs, self._m if minted is None else minted)

    def delta_remove(self, counts, ref, packs=(), minted=None):
        return super().delta_remove(counts, ref, packs, self._m if minted is None else minted)


def dealer_thread(dealer, ref, price, tick, side="buy", asset_id=None):
    oid = 9000 + tick
    if side == "buy":
        give = {"cash": 0, "assets": [{"id": 8000 + tick, "kind": "card", "ref": ref}], "types": []}
        want = {"cash": price, "assets": [], "types": []}
        topic = {"buy": {"card": ref}}
    else:
        give = {"cash": price, "assets": [], "types": []}
        want = {"cash": 0, "assets": [{"id": asset_id}], "types": []}
        topic = {"sell": {"assets": [asset_id]}}
    msg = {"id": oid, "tick": tick, "sender": dealer,
           "offer": {"id": oid, "maker": dealer, "to": "t18", "venue": None, "thread": TID, "status": "open",
                     "give": give, "want": want, "expires_tick": tick + 2, "created_tick": tick, "final": False}}
    return {"id": TID, "team": "t18", "with": dealer, "topic": topic, "status": "open", "messages": [msg],
            "standing_offers": []}, oid


class Friday:
    """World + Book + Valuer at a Friday tick (just before the deal)."""

    def __init__(self, tick, threads=None):
        self.tick = tick
        me = copy.deepcopy(ME)
        me["assets"] = holdings_before(tick)
        me["cash"] = 400
        me["unlocked"] = ["abuela", "chato"]
        self.valuer = FridayValuer(minted_before(tick))
        self.cfg = guards.Cfg()
        self.world = World(
            tick=tick, t_hours=tick * 60 / 3600.0, round=1, tick_seconds=60.0, tick_deadline=1e12,
            clock={"tick": tick, "paused": False, "doors": "open"}, limits=FRIDAY, reading="N", me=me,
            my_offers=(), offers_to_us=(), board=(), own_pseudonym="mcd38ffd5", threads=threads or {},
            foreign_threads=(), duels=(), catalog=CATALOG, schedule={"now_hours": tick / 60.0, "upcoming": []},
            released_sets=FRIDAY_RELEASED, feed_new=(), server_values={}, down=frozenset(), venues=(),
            leaderboard=())
        book = guards.build_book(self.world, None, self.valuer, self.cfg, PLAN, {}, {})
        self.book = dataclasses.replace(book, valuation_ok=True)     # hand-built me: no server collection_value

    def check(self, it, fresh=None) -> Verdict:
        return guards.check(it, self.world, self.book, self.valuer, self.cfg, guards.Counters(tick=self.tick),
                            fresh=fresh, now=0.0)

    def dealer_buy(self, dealer, ref, price) -> Verdict:
        th, oid = dealer_thread(dealer, ref, price, self.tick)
        f = Friday.__new__(Friday)
        f.__dict__.update(self.__dict__)
        f.world = dataclasses.replace(self.world, threads={TID: th})
        b = guards.build_book(f.world, None, self.valuer, self.cfg, PLAN, {}, {})
        f.book = dataclasses.replace(b, valuation_ok=True, thread_limit=MappingProxyType({TID: price}))
        it = make_intent("accept", "dealers", {"offer_id": oid, "source": "dealer", "ref": ref, "side": "buy",
                                               "price": price, "thread_id": TID, "give_asset": None,
                                               "fingerprint": "", "resupply": False, "venue": dealer}, "replay",
                         "replay", PRED0)
        return f.check(it, fresh=th)

    def dealer_sell(self, dealer, ref, asset_id, price) -> Verdict:
        th, oid = dealer_thread(dealer, ref, price, self.tick, side="sell", asset_id=asset_id)
        f = Friday.__new__(Friday)
        f.__dict__.update(self.__dict__)
        f.world = dataclasses.replace(self.world, threads={TID: th})
        b = guards.build_book(f.world, None, self.valuer, self.cfg, PLAN, {}, {})
        f.book = dataclasses.replace(b, valuation_ok=True, thread_limit=MappingProxyType({TID: price}))
        it = make_intent("accept", "dealers", {"offer_id": oid, "source": "dealer", "ref": ref, "side": "sell",
                                               "price": price, "thread_id": TID, "give_asset": None,
                                               "fingerprint": "", "resupply": False, "venue": dealer}, "replay",
                         "replay", PRED0)
        return f.check(it, fresh=th)

    def bid(self, ref, price, closer) -> Verdict:
        it = make_intent("list_offer", "closer" if closer else "rastro",
                         {"side": "bid", "ref": ref, "asset_id": None, "price": price, "expires_ticks": 60,
                          "closer": closer, "want_ref": None}, "replay", "replay", PRED0)
        return self.check(it)


def refused(v: Verdict) -> bool:
    return isinstance(v, Verdict) and not v.ok


class TestFridayLosses(unittest.TestCase):
    """The five Friday losses (P-05) and LAT-03 at 9: every one is refused today."""

    def test_sobre_at_23_is_not_even_expressible(self):
        f = Friday(97)
        for kind, args in (("open_thread", {"dealer": "abuela", "side": "buy", "ref": "sobre_barrio",
                                            "asset_ids": (), "limit": 23}),
                           ("accept", {"offer_id": 1424, "source": "dealer", "ref": "sobre_barrio", "side": "buy",
                                       "price": 23, "thread_id": TID, "give_asset": None, "fingerprint": "",
                                       "resupply": False, "venue": "abuela"})):
            try:
                it = make_intent(kind, "dealers", args, "replay", "replay", PRED0)
            except ValueError:
                continue                                   # refused at construction (ARGS)
            self.assertTrue(refused(f.check(it)), kind)

    def test_lat01_at_10(self):
        v = Friday(63).dealer_buy("abuela", "LAT-01", 10)
        self.assertTrue(refused(v), v)

    def test_lat06_at_22_with_the_pack_in_hand(self):
        f = Friday(115)
        self.assertIn("sobre_bienvenida", f.book.packs)            # asset 436 held from t98 to t145
        v = f.dealer_buy("chato", "LAT-06", 22)
        self.assertTrue(refused(v), v)
        self.assertEqual(v.code, "G14.pack")

    def test_lat08_at_32(self):
        v = Friday(140).dealer_buy("chato", "LAT-08", 32)
        self.assertTrue(refused(v), v)

    def test_lav06_sale_at_13(self):
        f = Friday(155)
        lav06 = [a["id"] for a in f.world.me["assets"] if a["ref"] == "LAV-06"]
        self.assertEqual(lav06, [509])
        v = f.dealer_sell("chato", "LAV-06", 509, 13)
        self.assertTrue(refused(v), v)
        self.assertIn(v.code, ("G32.limit", "G32.margin"), v)     # refused for price, not as "listed" (live 3 Oct)

    def test_dealer_sale_above_value_passes(self):
        v = Friday(155).dealer_sell("chato", "LAV-06", 509, 19)    # LAV uncommon 17.5 for us
        self.assertTrue(v.ok, v)

    def test_lat03_at_9(self):
        v = Friday(147).bid("LAT-03", 9, closer=False)
        self.assertTrue(refused(v), v)


class TestFridayGoodDeals(unittest.TestCase):
    def test_sal02_at_9(self):
        v = Friday(45).dealer_buy("abuela", "SAL-02", 9)
        self.assertTrue(v.ok, v)

    def test_sal08_at_24(self):
        v = Friday(67).dealer_buy("abuela", "SAL-08", 24)
        self.assertTrue(v.ok, v)

    def test_sal10_at_80_as_closer_bid(self):
        f = Friday(72)
        self.assertTrue(f.valuer.closes_page(f.book.projected, "SAL-10"))
        dv = guards.dv_add(f.world, f.book, f.valuer, "SAL-10")
        self.assertAlmostEqual(dv, 149.875, delta=0.05)
        v = f.bid("SAL-10", 80, closer=True)
        self.assertTrue(v.ok, v)
        self.assertFalse(f.bid("SAL-10", 130, closer=True).ok)        # above floor(dv - 20) = 129
        self.assertFalse(f.bid("SAL-10", 80, closer=False).ok)        # a closer must say so (G21.closer_flag)


if __name__ == "__main__":
    unittest.main()


# ------------------------------------------------------------------------------------------- duels (G50)

DUELS_DONE = _load("duels_done.json")["duels"]


def duel_before(d, k):
    """The duel as it stood just before our k-th message (messages before it; our and the rival's last offer)."""
    msgs = d["messages"][:k]
    m = d["messages"][k]
    you = [x for x in msgs if x["from"] == "you"]
    rival = [x for x in msgs if x["from"] != "you" and x.get("price") is not None]
    st = {key: d[key] for key in d if key not in ("messages", "your_offer", "rival_offer", "result", "price", "days")}
    st.update(status="live", messages=[{kk: x[kk] for kk in ("tick", "from", "price", "days")} for x in msgs],
              your_offer={"id": 1, "price": you[-1]["price"], "tick": you[-1]["tick"], "days": you[-1]["days"]}
              if you else None,
              rival_offer={"id": 2, "price": rival[-1]["price"], "tick": rival[-1]["tick"], "days": rival[-1]["days"]}
              if rival else None, result=None, price=None, days=None)
    return st, m


class TestFridayDuels(unittest.TestCase):
    """Every one of our 108 Friday duel messages, replayed through G50 at the state it was sent in."""

    def test_no_friday_message_outside_its_limit(self):
        from agent import talk
        codes = collections.Counter()
        n = 0
        for d in DUELS_DONE:
            for k, m in enumerate(d["messages"]):
                if m["from"] != "you" or m.get("price") is None:
                    continue
                n += 1
                st, m = duel_before(d, k)
                w = World(tick=m["tick"], t_hours=2.0, round=1, tick_seconds=60.0, tick_deadline=1e12,
                          clock={"tick": m["tick"], "paused": False, "doors": "open"}, limits=FRIDAY, reading="N",
                          me={"id": "t18"}, my_offers=(), offers_to_us=(), board=(), own_pseudonym=None, threads={},
                          foreign_threads=(), duels=(st,), catalog={}, schedule={}, released_sets=frozenset(),
                          feed_new=(), server_values={}, down=frozenset())
                two = "days" in d["issues"]
                it = make_intent("duel_say", "duels", {"duel_id": d["duel"], "price": m["price"],
                                                       "days": (m["days"] if m["days"] is not None else 5) if two
                                                       else None, "template": "duel", "variant": 0},
                                 "replay", "replay", PRED0)
                v = talk.check(it, w, None, None, guards.Cfg(), guards.Counters(tick=m["tick"]), now=0.0)
                codes[v.code if not v.ok else "ok"] += 1
                if k == 0 and not two:              # not vacuous: the same message AT the limit is refused
                    bad = make_intent("duel_say", "duels", {"duel_id": d["duel"], "price": d["your_limit"],
                                                            "days": None, "template": "duel", "variant": 0},
                                      "replay", "replay", PRED0)
                    vb = talk.check(bad, w, None, None, guards.Cfg(), guards.Counters(tick=m["tick"]), now=0.0)
                    self.assertEqual(vb.code, "G50.limit", d["duel"])
        self.assertEqual(n, 108)
        self.assertEqual(codes.get("G50.limit", 0), 0, codes)


# ------------------------------------------------------------------- INV-10 with a standing dealer offer (M17 fix)

class TestDealerNeverClosesRet(unittest.TestCase):
    """build_book counts a dealer thread's standing offer in Book.projected. Before the M17 fix, G32 asked
    closes_page(projected, ref) with the thread's own ref already counted -> always False: a dealer could close
    the RET page (INV-10 hole). Now the thread's own copy is left out, so the closer is refused."""

    def test_dealer_accept_of_the_ret_closer_is_refused(self):
        f = Friday(150)
        held = [a for a in f.world.me["assets"]]
        nxt = 7000
        for r in ("RET-01", "RET-02", "RET-03", "RET-04", "RET-06", "RET-07", "RET-08", "RET-09", "RET-10"):
            nxt += 1
            held.append({"id": nxt, "kind": "card", "ref": r})
        me = dict(f.world.me, assets=held)
        released = FRIDAY_RELEASED | {"RET"}
        f.world = dataclasses.replace(f.world, me=me, released_sets=released)
        f.valuer = Valuer(CATALOG, ME["affinity"], released)
        b = guards.build_book(f.world, None, f.valuer, f.cfg, PLAN, {}, {})
        f.book = dataclasses.replace(b, valuation_ok=True)
        self.assertTrue(f.valuer.closes_page(f.book.projected, "RET-05"))
        v = f.dealer_buy("abuela", "RET-05", 5)
        self.assertFalse(v.ok, v)
        self.assertIn("closes_page", v.code)
        # control: a non-closing RET card from the same dealer at a fair price is fine
        f2 = Friday(150)
        f2.world = dataclasses.replace(f2.world, released_sets=released)
        f2.valuer = Valuer(CATALOG, ME["affinity"], released)
        self.assertTrue(f2.dealer_buy("abuela", "RET-05", 5).ok)
