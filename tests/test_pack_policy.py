"""Strategy §2.1.1 / INV-09: t18 never buys packs. G61.pack_buy refuses every write that names, threads for or
receives a pack (manual `do` included); releases (cancel, close_thread, open_pack) stay allowed. Also: the
runner's Valuer follows the catalog CONTENT (Sunday CHA release mid-run), not the catalog object's id()."""
from __future__ import annotations

import copy
import unittest
from types import MappingProxyType, SimpleNamespace

import tests  # noqa: F401  (test isolation: BAZAAR_TEST=1)
from agent import runner
from agent.contracts import make_intent
from tests.test_guards import CATALOG, ME, Ctx, accept_args, buy_spec, pred, team_offer

PACKS = ("pack:sobre_oro", "pack:sobre_plata", "pack:sobre_barrio", "sobre_oro")
G61 = "G61.pack_buy"


def pack_asset(aid=8001, ptype="sobre_oro"):
    return {"id": aid, "kind": "pack", "ref": ptype}


def pack_thread(tid=7, dealer="pilar", ptype="sobre_oro"):
    return {"id": tid, "with": dealer, "team": "t18", "status": "open", "topic": {"buy": {"pack": ptype}},
            "messages": [{"from": dealer, "offer": {"id": 61, "maker": dealer, "status": "open",
                                                    "give": {"cash": 0, "assets": [pack_asset()], "types": []},
                                                    "want": {"cash": 420, "assets": [], "types": []}}}],
            "standing_offers": []}


def unlocked_me(*dealers):
    me = copy.deepcopy(ME)
    me["unlocked"] = list(dict.fromkeys(list(me.get("unlocked") or []) + list(dealers)))
    return me


class ManualDealerPackBuy(unittest.TestCase):
    """`bazaar.py do open_thread` with a pack want, at every dealer that sells packs, even when unlocked."""

    def test_open_thread_pack_refused(self):
        c = Ctx(me=unlocked_me("abuela", "chato", "pilar"))
        for dealer, price in (("abuela", 22), ("chato", 188), ("pilar", 420)):
            for ref in PACKS:
                args = runner.manual_args("open_thread", {"dealer": dealer, "side": "buy", "ref": ref,
                                                          "asset_ids": [], "limit": price})
                it = make_intent("open_thread", "manual", args, "test", "test", pred())
                v = c.check(it)
                self.assertFalse(v.ok, (dealer, ref))
                self.assertEqual(v.code, G61, (dealer, ref, v))

    def test_say_in_pack_thread_refused(self):
        c = Ctx(me=unlocked_me("pilar"), threads={7: pack_thread()})
        v = c.check(c.intent("say", thread_id=7, ref="LAT-09", price=400, template="pilar_buy", variant=0))
        self.assertEqual(v.code, G61, v)

    def test_dealer_accept_of_pack_refused(self):
        t = pack_thread()
        c = Ctx(me=unlocked_me("pilar"), threads={7: t})
        for ref in ("pack:sobre_oro", "LAT-09"):
            it = c.intent("accept", offer_id=61, source="dealer", ref=ref, side="buy", price=420, thread_id=7,
                          give_asset=None, fingerprint="x", resupply=False, venue="rastro")
            v = c.check(it, {"tick": 200, "thread": t})
            self.assertEqual(v.code, G61, (ref, v))

    def test_closing_a_pack_thread_still_allowed(self):
        c = Ctx(threads={7: pack_thread()})
        v = c.check(c.intent("close_thread", thread_id=7, ref="pack:sobre_oro"))
        self.assertNotEqual(v.code, G61, v)


class TeamPackBuy(unittest.TestCase):
    """El Rastro / rival venues: a team listing or swap that hands us a pack is never accepted."""

    def test_accept_listing_selling_a_pack(self):
        c = Ctx()
        o = team_offer(5001, {"cash": 0, "assets": [pack_asset()], "types": []},
                       {"cash": 100, "assets": [], "types": []})
        for ref in ("pack:sobre_oro", "LAT-09"):
            for venue in ("rastro", "t07"):
                v = c.check_accept(accept_args(buy_spec(ref, 100), o, venue=venue), o)
                self.assertEqual(v.code, G61, (ref, venue, v))

    def test_accept_listing_with_pack_type(self):
        c = Ctx()
        o = team_offer(5003, {"cash": 0, "assets": [], "types": ["pack:sobre_plata"]},
                       {"cash": 150, "assets": [], "types": []})
        v = c.check_accept(accept_args(buy_spec("LAT-09", 150), o), o)
        self.assertEqual(v.code, G61, v)

    def test_accept_swap_receiving_a_pack(self):
        c = Ctx()
        o = team_offer(5002, {"cash": 0, "assets": [pack_asset()], "types": []},
                       {"cash": 0, "assets": [], "types": ["card:MAL-04"]})
        v = c.check_accept(accept_args({"side": "swap", "ref": "LAT-09", "price": 0, "give_asset": 295}, o), o)
        self.assertEqual(v.code, G61, v)

    def test_bid_or_swap_listing_wanting_a_pack(self):
        c = Ctx()
        for ref in PACKS:
            self.assertEqual(c.check(c.bid(ref, 50)).code, G61, ref)
            self.assertEqual(c.check(c.swap("MAL-04", 295, ref)).code, G61, ref)

    def test_card_bid_not_touched_by_g61(self):
        c = Ctx()
        v = c.check(c.bid("LAT-09", 5))
        self.assertNotEqual(v.code, G61, v)


class ValuerFollowsCatalog(unittest.TestCase):
    """runner.Runner.build_valuer: rebuild on any catalog change (CHA released, minted), reuse on equal content."""

    def _self(self):
        return SimpleNamespace(valuer=None, _valuer_key=None, alarm=lambda *a, **k: None)

    def _world(self, catalog):
        cat = MappingProxyType(copy.deepcopy(catalog))
        released = frozenset(s["id"] for s in catalog["sets"] if s.get("released") is True)
        return SimpleNamespace(catalog=cat, me=MappingProxyType({"affinity": dict(ME["affinity"])}),
                               released_sets=released)

    def test_cha_release_and_minted_rebuild(self):
        me = self._self()
        sat = copy.deepcopy(CATALOG)
        for s in sat["sets"]:
            if s["id"] == "CHA":
                s["released"] = False
        v1 = runner.Runner.build_valuer(me, self._world(sat))
        self.assertNotIn("CHA", v1.released_sets)
        self.assertIs(runner.Runner.build_valuer(me, self._world(sat)), v1)     # same content, new object
        sun = copy.deepcopy(sat)
        for s in sun["sets"]:
            if s["id"] == "CHA":
                s["released"] = True
        v2 = runner.Runner.build_valuer(me, self._world(sun))
        self.assertIsNot(v2, v1)
        self.assertIn("CHA", v2.released_sets)
        minted = copy.deepcopy(sun)
        card = next(c for s in minted["sets"] for c in s.get("cards") or () if "minted" in c)
        card["minted"] = int(card["minted"] or 0) + 1
        v3 = runner.Runner.build_valuer(me, self._world(minted))
        self.assertIsNot(v3, v2)
        self.assertEqual(v3.cards[card["id"]]["minted"], card["minted"])


if __name__ == "__main__":
    unittest.main()
