"""M11 rastro / closer tactic tests (test doubles for the Valuer; World and Book from M0)."""
from __future__ import annotations

import unittest
from types import MappingProxyType

from agent.contracts import FRIDAY, Book, Need, World
from agent.tactics import rastro

CLOSER = "RET-05"


class FakeValuer:
    """delta_add / delta_remove from tables; closes_page for the closer ref only."""

    def __init__(self, add=None, rm=None, closers=(CLOSER,)):
        self.add = dict(add or {})
        self.rm = dict(rm or {})
        self.closers = set(closers)

    def delta_add(self, counts, ref, packs=(), minted=None):
        if ref not in self.add:
            raise KeyError(ref)
        return self.add[ref]

    def delta_remove(self, counts, ref, packs=(), minted=None):
        if ref not in self.rm:
            raise KeyError(ref)
        return self.rm[ref]

    def closes_page(self, counts, ref):
        return ref in self.closers


def card(aid, ref, rarity="common"):
    return {"id": aid, "kind": "card", "ref": ref, "serial": 1, "rarity": rarity, "set": ref.split("-")[0],
            "print_run": 300, "your_value": 0.0}


def sale(oid, ref, price, maker="mx", venue="rastro", to=None, exp=500, rarity="common"):
    return {"id": oid, "maker": maker, "to": to, "venue": venue, "thread": None, "status": "open",
            "give": {"cash": 0, "assets": [card(9000 + oid, ref, rarity)], "types": []},
            "want": {"cash": price, "assets": [], "types": []}, "expires_tick": exp, "created_tick": 1,
            "final": False}


def bid(oid, ref, price, maker="mx", venue="rastro", exp=500):
    return {"id": oid, "maker": maker, "to": None, "venue": venue, "thread": None, "status": "open",
            "give": {"cash": price, "assets": [], "types": []},
            "want": {"cash": 0, "assets": [], "types": ["card:" + ref]}, "expires_tick": exp, "created_tick": 1,
            "final": False}


def swap(oid, give_ref, want_ref=None, want_asset=None, maker="mx", venue="rastro", exp=500):
    want = {"cash": 0, "assets": [], "types": []}
    if want_ref:
        want["types"] = ["card:" + want_ref]
    if want_asset is not None:
        want["assets"] = [{"id": want_asset}]
    return {"id": oid, "maker": maker, "to": None, "venue": venue, "thread": None, "status": "open",
            "give": {"cash": 0, "assets": [card(9000 + oid, give_ref)], "types": []}, "want": want,
            "expires_tick": exp, "created_tick": 1, "final": False}


CATALOG = {"sets": [
    {"id": "RET", "cards": [{"id": f"RET-{i:02d}", "rarity": "common" if i <= 6 else "uncommon", "book": 10}
                            for i in range(1, 11)]},
    {"id": "MAL", "cards": [{"id": f"MAL-{i:02d}", "rarity": "common", "book": 10} for i in range(1, 11)]},
    {"id": "SAL", "cards": [{"id": f"SAL-{i:02d}", "rarity": "common", "book": 10} for i in range(1, 11)]},
    {"id": "LAT", "cards": [{"id": f"LAT-{i:02d}", "rarity": "rare" if i >= 9 else "common", "book": 70 if i >= 9 else 10}
                            for i in range(1, 11)]},
]}
AFF = {"RET": 1.3, "MAL": 0.5, "SAL": 1.1, "LAT": 0.9}


def world(tick=200, board=(), boards=None, my_offers=(), assets=(), offers_to_us=(), venues=(), leaderboard=(),
          reading="N", t_hours=10.0, down=frozenset()):
    me = {"id": "t18", "cash": 300, "assets": list(assets), "affinity": AFF}
    return World(tick=tick, t_hours=t_hours, round=2, tick_seconds=30.0, tick_deadline=1e12, clock={},
                 limits=FRIDAY, reading=reading, me=me, my_offers=tuple(my_offers),
                 offers_to_us=tuple(offers_to_us), board=tuple(board), own_pseudonym="mown",
                 threads={}, foreign_threads=(), duels=(), catalog=CATALOG, schedule={},
                 released_sets=frozenset({"RET", "MAL", "SAL", "LAT"}), feed_new=(), server_values={},
                 down=frozenset(down), boards=MappingProxyType(dict(boards or {})), venues=tuple(venues),
                 leaderboard=tuple(leaderboard))


def book(held=None, keep=None, cash_free=300, listed=None, paths=None, own_bids=None, bid_price=None,
         listed_assets=frozenset(), own_offer_ids=frozenset(), packs=(), delivery_risk=False, projected=None,
         frozen_closer=None, dealer_block=None, deals=None, recent=None):
    held = dict(held or {})
    return Book(cash=cash_free + 10, cash_free=cash_free, held=held, listed=dict(listed or {}), pending_out={},
                pending_in={}, projected=dict(projected if projected is not None else held),
                keep=dict(keep or {}), listed_assets=frozenset(listed_assets),
                own_offer_ids=frozenset(own_offer_ids), own_bids=dict(own_bids or {}),
                bid_price=dict(bid_price or {}), bid_band={}, paths=dict(paths or {}), thread_limit={},
                thread_prices={}, thread_ref={}, thread_by_dealer={}, dealer_block=dict(dealer_block or {}),
                dealer_deals_hour=dict(deals or {}), packs=tuple(packs), needs={},
                frozen_closer=dict(frozen_closer or {}), protect_sets=frozenset({"SAL", "RET"}),
                delivery_risk=delivery_risk, recent_rastro=dict(recent or {}), unknown_domains=frozenset(),
                valuation_ok=True)


PLAN = {"closer": {"accept_min": 20, "default_minus": 50, "compete_minus": 20, "endgame_hours": {"N": 12.0}},
        "resupply_min": 15, "dup_min_price": {"RET": 30, "CHA": 30}}
CLOSER_NEED = Need(set="RET", ref=CLOSER, source="team", max_price=99, closer=True)
VAL = dict(add={CLOSER: 99.1, "LAT-09": 63.0, "LAT-10": 63.0, "MAL-04": 2.0, "RET-03": 13.0, "RET-02": 13.0},
           rm={"MAL-04": 4.0, "MAL-05": 4.0, "RET-02": 13.0, "RET-03": 13.0, "SAL-04": 83.9, "LAT-01": 3.0})


def run(w, b, needs=(CLOSER_NEED,), state=None, valuer=None):
    return rastro.propose(w, b, valuer or FakeValuer(**VAL), None, PLAN, list(needs),
                          state if state is not None else {})


def kinds(out):
    return [(i.kind, i.tactic, dict(i.args)) for i in out]


def own_bid(oid, ref, price):
    o = bid(oid, ref, price, maker="t18")
    return o


class CloserTests(unittest.TestCase):
    def test_bid_49_on_the_spot(self):
        out = run(world(), book())
        bids = [i for i in out if i.kind == "list_offer" and i.args["ref"] == CLOSER]
        self.assertEqual(len(bids), 1)
        a = bids[0].args
        self.assertEqual((a["side"], a["price"], a["closer"], bids[0].tactic), ("bid", 49, True, "closer"))
        self.assertGreaterEqual(bids[0].prediction.neg_lo, 20)

    def test_bid_capped_by_cash_free(self):
        out = run(world(), book(cash_free=30))
        a = [i.args for i in out if i.kind == "list_offer" and i.args["ref"] == CLOSER][0]
        self.assertEqual(a["price"], 30)

    def test_accept_sale_with_neg_lo_20(self):
        # 99.1 - 70 - ceil(3.5 + 1) = 24.1 -> accept now
        out = run(world(board=[sale(1, CLOSER, 70)]), book())
        acc = [i for i in out if i.kind == "accept"]
        self.assertEqual(len(acc), 1)
        self.assertEqual((acc[0].args["offer_id"], acc[0].args["side"], acc[0].tactic), (1, "buy", "closer"))
        self.assertFalse([i for i in out if i.kind == "list_offer" and i.args["ref"] == CLOSER])

    def test_sale_below_20_not_accepted_bid_instead(self):
        out = run(world(board=[sale(1, CLOSER, 76)]), book())     # 99.1 - 76 - 5 = 18.1
        self.assertFalse([i for i in out if i.kind == "accept"])
        self.assertEqual([i.args["price"] for i in out if i.kind == "list_offer" and i.args["ref"] == CLOSER], [49])

    def test_raise_to_79_with_competition_two_steps(self):
        state = {}
        mine = own_bid(50, CLOSER, 49)
        w1 = world(board=[bid(60, CLOSER, 55)], my_offers=[mine])
        b1 = book(own_bids={CLOSER: 50}, bid_price={50: 49}, own_offer_ids={50}, paths={CLOSER: 1})
        out = run(w1, b1, state=state)
        self.assertEqual([(i.kind, i.args["offer_id"]) for i in out if i.kind == "cancel"], [("cancel", 50)])
        self.assertFalse([i for i in out if i.kind == "list_offer" and i.args["ref"] == CLOSER])
        # T+1: our bid is gone -> new bid at floor(99.1 - 20) = 79
        out2 = run(world(tick=201, board=[bid(60, CLOSER, 55)]), book(), state=state)
        bids = [i.args["price"] for i in out2 if i.kind == "list_offer" and i.args["ref"] == CLOSER]
        self.assertEqual(bids, [79])

    def test_raise_without_own_bid_goes_straight_to_79(self):
        out = run(world(board=[bid(60, CLOSER, 52)]), book())
        self.assertEqual([i.args["price"] for i in out if i.kind == "list_offer" and i.args["ref"] == CLOSER], [79])

    def test_endgame_raises(self):
        out = run(world(t_hours=12.5), book())
        self.assertEqual([i.args["price"] for i in out if i.kind == "list_offer" and i.args["ref"] == CLOSER], [79])

    def test_never_lowers(self):
        state = {}
        run(world(board=[bid(60, CLOSER, 52)]), book(), state=state)          # placed at 79
        # bid withdrawn (e.g. delivery risk), competition gone: re-place at 79, never 49
        out = run(world(tick=230), book(), state=state)
        self.assertEqual([i.args["price"] for i in out if i.kind == "list_offer" and i.args["ref"] == CLOSER], [79])
        # standing bid at 79 without competition: nothing (no cancel, no lower bid)
        mine = own_bid(70, CLOSER, 79)
        out = run(world(tick=231, my_offers=[mine]), book(own_bids={CLOSER: 70}, bid_price={70: 79},
                                                          own_offer_ids={70}, paths={CLOSER: 1}), state=state)
        self.assertFalse([i for i in out if i.args.get("ref") == CLOSER])
        # not enough cash for the floor: nothing rather than a lower bid
        out = run(world(tick=232), book(cash_free=60), state=state)
        self.assertFalse([i for i in out if i.args.get("ref") == CLOSER])

    def test_standing_bid_from_world_is_a_floor_even_without_state(self):
        mine = own_bid(70, CLOSER, 60)
        out = run(world(my_offers=[mine]), book(own_bids={CLOSER: 70}, bid_price={70: 60}, own_offer_ids={70},
                                                 paths={CLOSER: 1}))
        self.assertFalse([i for i in out if i.args.get("ref") == CLOSER])

    def test_cancel_verify_accept(self):
        state = {}
        mine = own_bid(50, CLOSER, 49)
        b1 = book(own_bids={CLOSER: 50}, bid_price={50: 49}, own_offer_ids={50}, paths={CLOSER: 1})
        out = run(world(board=[sale(1, CLOSER, 70)], my_offers=[mine]), b1, state=state)
        self.assertEqual([(i.kind, i.args["offer_id"]) for i in out], [("cancel", 50)])
        # T+1 still listed (cancel not seen): wait, no duplicate cancel, no accept
        out = run(world(tick=201, board=[sale(1, CLOSER, 70)], my_offers=[mine]), b1, state=state)
        self.assertFalse([i for i in out if i.args.get("ref") == CLOSER or i.args.get("offer_id") in (1, 50)])
        # T+2 the bid is gone -> accept
        out = run(world(tick=202, board=[sale(1, CLOSER, 70)]), book(), state=state)
        acc = [i for i in out if i.kind == "accept"]
        self.assertEqual([(i.args["offer_id"], i.tactic) for i in acc], [(1, "closer")])

    def test_no_closer_bid_with_delivery_risk_or_pack(self):
        self.assertFalse([i for i in run(world(), book(delivery_risk=True)) if i.args.get("ref") == CLOSER])
        self.assertEqual(run(world(), book(packs=(123,))), [])

    def test_one_route_per_ref(self):
        # a dealer thread already runs for the closer card: no bid, no accept
        out = run(world(board=[sale(1, CLOSER, 70)]), book(paths={CLOSER: 1}))
        self.assertFalse([i for i in out if i.args.get("ref") == CLOSER])


class SalesTests(unittest.TestCase):
    def test_ret_duplicates_never_below_30(self):
        assets = [card(1, "RET-02"), card(2, "RET-02")]
        state = {}
        out = run(world(assets=assets), book(held={"RET-02": 2}, keep={"RET-02": 1}), needs=(), state=state)
        sells = [i.args for i in out if i.kind == "list_offer" and i.args["side"] == "sell"]
        self.assertEqual(len(sells), 1)
        self.assertGreaterEqual(sells[0]["price"], 30)
        for _ in range(5):                                                     # relists decay to 30, never below
            out = run(world(assets=assets), book(held={"RET-02": 2}, keep={"RET-02": 1}), needs=(), state=state)
            p = [i.args["price"] for i in out if i.kind == "list_offer" and i.args["side"] == "sell"]
            self.assertTrue(p and p[0] >= 30)

    def test_single_protected_copy_never_listed(self):
        out = run(world(assets=[card(1, "RET-03")]), book(held={"RET-03": 1}, keep={"RET-03": 1}), needs=())
        self.assertFalse([i for i in out if i.args.get("asset_id") == 1 or i.args.get("give_asset") == 1])

    def test_spare_mal_listed_at_9(self):
        out = run(world(assets=[card(1, "MAL-04")]), book(held={"MAL-04": 1}), needs=())
        sells = [i.args for i in out if i.kind == "list_offer"]
        self.assertEqual([(s["ref"], s["price"], s["asset_id"]) for s in sells], [("MAL-04", 9, 1)])

    def test_sell_spare_into_rival_bid(self):
        out = run(world(assets=[card(1, "MAL-04")], board=[bid(5, "MAL-04", 12)]), book(held={"MAL-04": 1}),
                  needs=())
        acc = [i.args for i in out if i.kind == "accept"]   # 12 - ceil(0.6 + 1) - 4 = 6
        self.assertEqual([(a["side"], a["give_asset"], a["resupply"]) for a in acc], [("sell", 1, False)])

    def test_ret_duplicate_not_sold_into_bid_below_30(self):
        assets = [card(1, "RET-02"), card(2, "RET-02")]
        out = run(world(assets=assets, board=[bid(5, "RET-02", 25)]),
                  book(held={"RET-02": 2}, keep={"RET-02": 1}), needs=())
        self.assertFalse([i for i in out if i.kind == "accept"])


class J13Tests(unittest.TestCase):
    def base(self, **kw):
        held = {"RET-03": 1, "RET-01": 1}
        args = dict(held=held, keep={"RET-03": 1, "RET-01": 1})
        args.update(kw)
        return book(**args)

    def test_resupply_accepts_rival_closer_bid(self):
        # 35 - ceil(1.75 + 1) - 13 = 19 >= 15
        out = run(world(assets=[card(1, "RET-03")], board=[bid(5, "RET-03", 35)]), self.base(), needs=())
        acc = [i.args for i in out if i.kind == "accept"]
        self.assertEqual([(a["give_asset"], a["resupply"], a["side"]) for a in acc], [(1, True, "sell")])

    def test_resupply_conditions(self):
        w = world(assets=[card(1, "RET-03")], board=[bid(5, "RET-03", 35)])
        cases = {
            "low gain": (world(assets=[card(1, "RET-03")], board=[bid(5, "RET-03", 30)]), self.base()),
            "frozen closer": (w, self.base(frozen_closer={"RET": "RET-03"})),
            "page at 9": (w, self.base(projected={f"RET-{i:02d}": 1 for i in range(1, 10)})),
            "abuela blocked": (w, self.base(dealer_block={"abuela": 999})),
            "abuela quota": (w, self.base(deals={"abuela": 7})),
            "expires soon": (world(tick=200, assets=[card(1, "RET-03")], board=[bid(5, "RET-03", 35, exp=201)]),
                             self.base()),
        }
        for name, (ww, bb) in cases.items():
            with self.subTest(name):
                self.assertFalse([i for i in run(ww, bb, needs=()) if i.kind == "accept"])


class SwapTests(unittest.TestCase):
    def test_swap_accepted_with_spare(self):
        o = swap(7, "LAT-09", want_ref="MAL-04")
        out = run(world(assets=[card(1, "MAL-04")], board=[o]), book(held={"MAL-04": 1}), needs=())
        acc = [i for i in out if i.kind == "accept"]
        self.assertEqual(len(acc), 1)
        a = acc[0].args
        self.assertEqual((a["side"], a["ref"], a["give_asset"], a["price"]), ("swap", "LAT-09", 1, 0))
        self.assertEqual(acc[0].prediction.model, "D1")

    def test_swap_never_hands_over_protected_copy(self):
        for o in (swap(7, "LAT-09", want_ref="SAL-04"), swap(8, "LAT-09", want_asset=1)):
            with self.subTest(o["id"]):
                out = run(world(assets=[card(1, "SAL-04")], board=[o]),
                          book(held={"SAL-04": 1}, keep={"SAL-04": 1}), needs=())
                self.assertFalse([i for i in out if i.args.get("give_asset") == 1 or i.args.get("asset_id") == 1])

    def test_swap_listed_asset_not_handed(self):
        o = swap(7, "LAT-09", want_asset=1)
        out = run(world(assets=[card(1, "MAL-04")], board=[o]),
                  book(held={"MAL-04": 1}, listed={"MAL-04": 1}, listed_assets={1}), needs=())
        self.assertFalse([i for i in out if i.kind == "accept"])

    def test_publish_swap_for_team_need_without_cash(self):
        need = Need(set="LAT", ref="LAT-09", source="team", max_price=62, closer=False)
        out = run(world(assets=[card(1, "MAL-04")]), book(held={"MAL-04": 1}, cash_free=0), needs=(need,))
        sw = [i.args for i in out if i.kind == "list_offer" and i.args["side"] == "swap"]
        self.assertEqual([(s["ref"], s["asset_id"], s["want_ref"], s["price"]) for s in sw],
                         [("MAL-04", 1, "LAT-09", 0)])
        self.assertFalse([i for i in out if i.kind == "list_offer" and i.args["side"] == "sell"])

    def test_long_bid_for_team_need_one_route(self):
        need = Need(set="LAT", ref="LAT-09", source="team", max_price=62, closer=False)
        out = run(world(assets=[card(1, "MAL-04")]), book(held={"MAL-04": 1}), needs=(need,))
        routes = [i for i in out if i.args.get("ref") == "LAT-09" or i.args.get("want_ref") == "LAT-09"]
        self.assertEqual(len(routes), 1)
        self.assertEqual((routes[0].args["side"], routes[0].args["price"], routes[0].args["expires_ticks"]),
                         ("bid", 60, rastro.BID_TICKS))
        # standing own bid -> no second route
        out = run(world(my_offers=[own_bid(3, "LAT-09", 60)]),
                  book(own_bids={"LAT-09": 3}, bid_price={3: 60}, own_offer_ids={3}), needs=(need,))
        self.assertFalse([i for i in out if i.args.get("ref") == "LAT-09" or i.args.get("want_ref") == "LAT-09"])

    def test_swap_not_accepted_with_other_route(self):
        o = swap(7, "LAT-09", want_ref="MAL-04")
        cases = {"own bid": dict(own_bids={"LAT-09": 3}, bid_price={3: 60}, own_offer_ids={3}),
                 "dealer thread": dict(paths={"LAT-09": 1})}
        for name, extra in cases.items():
            with self.subTest(name):
                out = run(world(assets=[card(1, "MAL-04")], board=[o]), book(held={"MAL-04": 1}, **extra), needs=())
                self.assertFalse([i for i in out if i.kind == "accept"])

    def test_swap_below_gain_refused(self):
        # we would hand over a spare SAL-04 (dv_rm 83.9) for a MAL-04 (dv_add 2.0): losing swap
        out = run(world(assets=[card(1, "SAL-04"), card(2, "SAL-04")], board=[swap(8, "MAL-04", want_ref="SAL-04")]),
                  book(held={"SAL-04": 2}), needs=())
        self.assertFalse([i for i in out if i.kind == "accept"])

    def test_publish_swap_for_missing_ret(self):
        need = Need(set="RET", ref="RET-03", source="team", max_price=12, closer=False)
        out = run(world(assets=[card(1, "MAL-04")]), book(held={"MAL-04": 1}, cash_free=0), needs=(need,))
        sw = [i.args for i in out if i.kind == "list_offer" and i.args["side"] == "swap"]
        self.assertEqual([(s["asset_id"], s["want_ref"]) for s in sw], [(1, "RET-03")])

    def test_dealer_need_gets_no_bid(self):
        need = Need(set="RET", ref="RET-03", source="abuela", max_price=12, closer=False)
        out = run(world(), book(), needs=(need,))
        self.assertFalse([i for i in out if i.args.get("ref") == "RET-03"])


class VenueTests(unittest.TestCase):
    VEN = ({"id": "v01", "owner": "t06", "fee_bps": 0, "fee_per_card": 0, "status": "open"},
           {"id": "v02", "owner": "t12", "fee_bps": 0, "fee_per_card": 0, "status": "open"})
    LB = ("t13", "t06", "t02", "t05", "t08", "t12", "t18")
    NEED = Need(set="LAT", ref="LAT-09", source="chato", max_price=62, closer=False)

    def go(self, offer, leaderboard=LB, venues=VEN):
        return run(world(boards={offer["venue"]: [offer]}, venues=venues, leaderboard=leaderboard), book(),
                   needs=(self.NEED,))

    def test_rival_venue_outside_top5_with_gain_10(self):
        out = self.go(sale(1, "LAT-09", 50, venue="v02"))      # 63 - 50 - 0 = 13 >= 10
        acc = [i.args for i in out if i.kind == "accept"]
        self.assertEqual([(a["offer_id"], a["venue"]) for a in acc], [(1, "v02")])

    def test_rival_venue_small_gain_refused(self):
        self.assertFalse([i for i in self.go(sale(1, "LAT-09", 55, venue="v02")) if i.kind == "accept"])

    def test_rival_venue_top5_owner_refused(self):
        self.assertFalse([i for i in self.go(sale(1, "LAT-09", 40, venue="v01")) if i.kind == "accept"])

    def test_unknown_leaderboard_refused(self):
        self.assertFalse([i for i in self.go(sale(1, "LAT-09", 40, venue="v02"), leaderboard=())
                          if i.kind == "accept"])

    def test_venue_fee_included(self):
        ven = ({"id": "v02", "owner": "t12", "fee_bps": 1000, "fee_per_card": 2, "status": "open"},)
        # 63 - 50 - ceil(5 + 2) = 6 < 10 -> refused
        self.assertFalse([i for i in self.go(sale(1, "LAT-09", 50, venue="v02"), venues=ven) if i.kind == "accept"])

    def test_rastro_buy_with_gain_3(self):
        out = run(world(board=[sale(1, "LAT-09", 55)]), book(), needs=(self.NEED,))   # 63 - 55 - 4 = 4
        self.assertEqual([i.args["venue"] for i in out if i.kind == "accept"], ["rastro"])

    def test_own_and_foreign_targeted_offers_skipped(self):
        offers = [sale(1, "LAT-09", 40, maker="mown"), sale(2, "LAT-09", 40, to="t05")]
        self.assertFalse([i for i in run(world(board=offers), book(), needs=(self.NEED,)) if i.kind == "accept"])

    def test_unknown_card_fails_closed(self):
        out = run(world(board=[sale(1, "ZZZ-01", 1)]), book(),
                  needs=(Need(set="ZZZ", ref="ZZZ-01", source="team", max_price=50, closer=False),))
        self.assertFalse([i for i in out if i.args.get("ref") == "ZZZ-01"])

    def test_offer_addressed_to_us_is_read(self):
        o = sale(1, "LAT-09", 50, to="t18")
        out = run(world(offers_to_us=[o]), book(), needs=(self.NEED,))   # 63 - 50 - ceil(2.5 + 1) = 9.5 >= 3
        self.assertEqual([(i.args["offer_id"], i.args["venue"]) for i in out if i.kind == "accept"], [(1, "rastro")])

    def test_offer_to_us_without_venue_refused(self):
        o = sale(1, "LAT-09", 50, to="t18")
        o["venue"] = None
        self.assertFalse([i for i in run(world(offers_to_us=[o]), book(), needs=(self.NEED,)) if i.kind == "accept"])

    def test_no_sale_into_bid_on_top5_venue(self):
        o = bid(5, "MAL-04", 40, venue="v01")
        out = run(world(assets=[card(1, "MAL-04")], boards={"v01": [o]}, venues=self.VEN, leaderboard=self.LB),
                  book(held={"MAL-04": 1}), needs=())
        self.assertFalse([i for i in out if i.kind == "accept"])

    def test_closed_venue_refused(self):
        ven = ({"id": "v02", "owner": "t12", "fee_bps": 0, "fee_per_card": 0, "status": "closed"},)
        self.assertFalse([i for i in self.go(sale(1, "LAT-09", 30, venue="v02"), venues=ven) if i.kind == "accept"])

    def test_one_accept_per_ref_across_venues(self):
        boards = {"rastro": [sale(1, "LAT-09", 40)], "v02": [sale(2, "LAT-09", 30, venue="v02")]}
        out = run(world(boards=boards, venues=self.VEN, leaderboard=self.LB), book(), needs=(self.NEED,))
        self.assertEqual(len([i for i in out if i.kind == "accept" and i.args["ref"] == "LAT-09"]), 1)

    def test_down_sources_and_bad_valuation(self):
        self.assertEqual(run(world(down={"board"}), book()), [])
        b = book()
        object.__setattr__(b, "valuation_ok", False)
        self.assertEqual(run(world(), b), [])


if __name__ == "__main__":
    unittest.main()
