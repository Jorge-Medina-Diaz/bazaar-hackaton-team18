"""M3 valuation tests: anchored on measured Friday data (tests/fixtures/harvest)."""
from __future__ import annotations

import ast
import collections
import json
import math
import unittest
from pathlib import Path

from agent.contracts import Prediction
from agent.valuation import (UnknownCard, UnknownPack, Valuer, fee, predict_dealer, predict_duel, predict_none,
                             predict_swap, predict_team, venue_fee, verdict)

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "harvest"


def _load(name):
    with open(FIX / name, encoding="utf-8") as f:
        return json.load(f)


CATALOG = _load("catalog.json")
ME159 = _load("me.json")
VALUES_ALL = _load("me_values_all_cards.json")
CARDS_ALL = _load("cards_all.json")
AFF = ME159["affinity"]
FRIDAY_RELEASED = frozenset({"LAV", "MAL", "LAT", "SAL"})


def valuer(released=FRIDAY_RELEASED):
    return Valuer(CATALOG, AFF, released)


def holdings_at(tick, inclusive=True, team="t18"):
    c = collections.Counter()
    packs = []
    for a in CARDS_ALL.values():
        own = None
        for h in a["history"]:
            if (h["tick"] <= tick) if inclusive else (h["tick"] < tick):
                own = h["to"]
        if own == team:
            if a["kind"] == "card":
                c[a["ref"]] += 1
            else:
                packs.append(a["ref"])
    return c, packs


def minted_before(tick):
    m = collections.Counter()
    for a in CARDS_ALL.values():
        if a["kind"] == "card" and a["history"][0]["tick"] < tick:
            m[a["ref"]] += 1
    return m


class TestValueModel(unittest.TestCase):
    def test_released_from_catalog(self):
        self.assertEqual(Valuer.released_from_catalog(CATALOG), FRIDAY_RELEASED)

    def test_collection_value_t30(self):
        c, packs = holdings_at(30)
        self.assertEqual(packs, [])
        self.assertAlmostEqual(valuer().collection_value(c), 251.6, delta=0.05)
        p30 = ROOT / "logs" / "probe" / "30" / "me.json"       # cross-check with the raw t30 read if present
        if p30.exists():
            with open(p30, encoding="utf-8") as f:
                me30 = json.load(f)
            self.assertEqual(Valuer.holdings(me30)[0], +c)
            ok, err, mism = valuer().self_check(me30)
            self.assertTrue(ok, mism)

    def test_collection_value_t159(self):
        c, packs = Valuer.holdings(ME159)
        self.assertEqual(packs, ())
        self.assertAlmostEqual(valuer().collection_value(c), 505.4, delta=0.05)
        self.assertEqual(c, holdings_at(159)[0])

    def test_your_value_24_of_24(self):
        v = valuer()
        c, packs = Valuer.holdings(ME159)
        cards = [a for a in ME159["assets"] if a["kind"] == "card"]
        ok = sum(abs(v.delta_remove(c, a["ref"], packs) - a["your_value"]) < 0.051 for a in cards)
        self.assertEqual((ok, len(cards)), (24, 24))

    def test_value_card_72_of_72(self):
        v = valuer()
        c, packs = Valuer.holdings(ME159)
        ok = sum(abs(v.delta_add(c, ref, packs) - val) < 0.051 for ref, val in VALUES_ALL.items())
        self.assertEqual((ok, len(VALUES_ALL)), (72, 72))

    def test_self_check_harvest(self):
        ok, err, mism = valuer().self_check(ME159, VALUES_ALL)
        self.assertTrue(ok, mism)
        self.assertLess(err, 0.06)

    def test_packs_weighted_t110_t122(self):
        # V-02: welcome pack unopened, stock-weighted EV (second-hand 493.7 / 511.2, C2)
        v = valuer()
        for tick, meas in ((110, 493.7), (122, 511.2)):
            c, packs = holdings_at(tick)
            self.assertEqual(packs, ["sobre_bienvenida"])
            self.assertAlmostEqual(v.collection_value(c, packs, minted_before(tick)), meas, delta=0.05)

    def test_copy_value(self):
        v = valuer()
        self.assertAlmostEqual(v.copy_value("SAL-01", 1, side="buy"), 11.0)
        self.assertAlmostEqual(v.copy_value("SAL-01", 2, side="buy"), 2.75)
        self.assertAlmostEqual(v.copy_value("SAL-01", 3, side="sell"), 1.1)
        self.assertEqual(v.copy_value("SAL-01", 4, side="buy"), 0.0)
        self.assertAlmostEqual(v.copy_value("SAL-01", 4, side="sell"), 1.1)
        with self.assertRaises(ValueError):
            v.copy_value("SAL-01", 0, side="buy")

    def test_fourth_copy_conservative(self):
        v = valuer()
        c = collections.Counter({"LAV-01": 3})
        self.assertEqual(v.delta_add(c, "LAV-01"), 0.0)
        c4 = collections.Counter({"LAV-01": 4})
        self.assertAlmostEqual(v.delta_remove(c4, "LAV-01"), 0.7)

    def test_page_card_and_closes_page(self):
        v = valuer()
        self.assertTrue(v.page_card("LAT-09"))
        self.assertFalse(v.page_card("LAT-11"))
        self.assertFalse(v.page_card("XXX-01"))
        c, _ = Valuer.holdings(ME159)                     # LAT 8/10: LAT-09 and LAT-10 missing
        self.assertFalse(v.closes_page(c, "LAT-09"))
        c2 = collections.Counter(c)
        c2["LAT-10"] += 1                                 # projected with the other bid landing
        self.assertTrue(v.closes_page(c2, "LAT-09"))
        self.assertFalse(v.closes_page(c2, "LAT-10"))    # already held
        self.assertFalse(v.closes_page(c2, "LAT-11"))    # not a page card
        # E-M3: the card that closes LAT is worth 122.625 to us (uncapped gain 122.625 - p as bid maker)
        self.assertAlmostEqual(v.delta_add(c2, "LAT-09"), 122.625, delta=0.001)

    def test_unknown_pack_sobre_nuevo(self):
        v = valuer()
        c, _ = Valuer.holdings(ME159)
        with self.assertRaises(UnknownPack):
            v.pack_ev("sobre_nuevo", c)
        with self.assertRaises(UnknownPack):
            v.collection_value(c, ["sobre_nuevo"])
        with self.assertRaises(UnknownPack):
            v.delta_add(c, "LAT-09", ["sobre_nuevo"])
        me = dict(ME159)
        me["assets"] = list(ME159["assets"]) + [{"id": 9999, "kind": "pack", "ref": "sobre_nuevo"}]
        ok, err, mism = v.self_check(me)                  # never raises; valuation_ok -> False
        self.assertFalse(ok)
        self.assertEqual(mism[-1][0], "error")

    def test_unknown_card_fails_closed(self):
        v = valuer()
        with self.assertRaises(UnknownCard):
            v.delta_add({}, "ZZZ-01")
        with self.assertRaises(UnknownCard):
            v.delta_remove({"ZZZ-01": 1}, "ZZZ-01")
        with self.assertRaises(ValueError):
            v.delta_remove({}, "LAV-01")                  # not held
        no_aff = Valuer(CATALOG, {"LAV": 0.7}, FRIDAY_RELEASED)
        with self.assertRaises(UnknownCard):
            no_aff.delta_add({}, "RET-01")
        with self.assertRaises(ValueError):
            Valuer({"sets": []}, AFF, FRIDAY_RELEASED)   # no values block

    def test_released_sets_drive_packs(self):
        c, _ = Valuer.holdings(ME159)
        ev4 = valuer().pack_ev("sobre_barrio", c)
        ev6 = valuer(frozenset(FRIDAY_RELEASED | {"RET", "CHA"})).pack_ev("sobre_barrio", c)
        self.assertNotAlmostEqual(ev4, ev6, places=3)
        with self.assertRaises(UnknownPack):            # no released set -> no candidates
            valuer(frozenset()).pack_ev("sobre_barrio", c)

    def test_pack_lowers_effective_value_P06(self):
        # LAT-06 at t115 with the welcome pack unopened: effective V 20.145 (P-06), not 22.5
        v = valuer()
        hb, pb = holdings_at(115, inclusive=False)
        self.assertIn("sobre_bienvenida", pb)
        dv = v.delta_add(hb, "LAT-06", pb, minted_before(115))
        self.assertAlmostEqual(dv, 20.145, delta=0.002)
        self.assertAlmostEqual(v.delta_add(hb, "LAT-06"), 22.5, delta=0.001)

    def test_swap_delta(self):
        v = valuer()
        c, _ = Valuer.holdings(ME159)
        give = "LAT-01"                                   # a duplicate
        self.assertGreaterEqual(c[give], 2)
        d = v.delta_swap(c, give, "LAT-09")
        self.assertAlmostEqual(d, v.delta_add(c, "LAT-09") - v.delta_remove(c, give), delta=1e-9)
        # same-set swap that would break the page: giving away the only copy of a page card
        sal = "SAL-02"
        self.assertEqual(c[sal], 1)
        d2 = v.delta_swap(c, sal, "LAV-01")
        self.assertLess(d2, -50)                          # loses the SAL page bonus


def _catalog(values=None, minted=None):
    """A deep copy of the harvest catalog with optional values overrides and per-ref minted overrides."""
    cat = json.loads(json.dumps(CATALOG))
    if values is not None:
        cat["values"] = values
    for s in cat["sets"]:
        for c in s["cards"]:
            if minted and c["id"] in minted:
                c["minted"] = minted[c["id"]]
    return cat


def _rarity_refs(rarity, released=FRIDAY_RELEASED):
    return [c["id"] for s in CATALOG["sets"] if s["id"] in released for c in s["cards"] if c["rarity"] == rarity]


class TestRarityFallback(unittest.TestCase):
    """Official rule: an exhausted rarity draws from the next rarity down."""

    # pack EVs with the harvest catalog before the fallback / master change (nothing exhausted)
    EV159 = {"sobre_barrio": 11.466143228045496, "sobre_bienvenida": 36.74830225251024,
             "sobre_plata": 87.8241835684799, "sobre_oro": 280.82401909644597}
    EV0 = {"sobre_barrio": 27.0353716254703, "sobre_bienvenida": 62.42841695318094,
           "sobre_plata": 128.64683718514817, "sobre_oro": 328.2743231293531}

    def test_ev_regression_nothing_exhausted(self):
        v = valuer()
        c, _ = Valuer.holdings(ME159)
        for p in self.EV159:
            self.assertAlmostEqual(v.pack_ev(p, c), self.EV159[p], places=9)
            self.assertAlmostEqual(v.pack_ev(p, {}), self.EV0[p], places=9)

    def test_exhausted_legendary_uses_epic(self):
        leg = {r: 3 for r in _rarity_refs("legendary")}
        v = Valuer(_catalog(minted=leg), AFF, FRIDAY_RELEASED)
        plain = valuer()
        dist = v._slot_dist("legendary", None)
        self.assertEqual({r for r, _ in dist}, set(_rarity_refs("epic")))
        self.assertAlmostEqual(sum(q for _, q in dist), 1.0)
        self.assertEqual(dist, plain._slot_dist("epic", None))
        # sobre_oro last slot {epic .85, legendary .15} -> all epic: EV equals a pure-epic slot
        oro = dict(next(p for p in CATALOG["packs"] if p["id"] == "sobre_oro"))
        oro["slots"] = oro["slots"][:4] + [{"epic": 1.0}]
        cat = _catalog(minted=leg)
        cat["packs"] = [oro]
        ref_v = Valuer(cat, AFF, FRIDAY_RELEASED)
        self.assertAlmostEqual(v.pack_ev("sobre_oro", {}), ref_v.pack_ev("sobre_oro", {}), places=9)
        # the same through the minted argument (Sensor counts: replaces the catalog field for every ref)
        full = {c["id"]: c["minted"] for s in CATALOG["sets"] for c in s["cards"]}
        full.update(leg)
        self.assertAlmostEqual(valuer().pack_ev("sobre_oro", {}, full),
                               ref_v.pack_ev("sobre_oro", {}), places=9)

    def test_partially_mixed_slot_merges_mass(self):
        # plata last slot {rare .86, epic .12, legendary .02}; epic + legendary out -> all rare
        out = {r: 9 for r in _rarity_refs("epic")}
        out.update({r: 3 for r in _rarity_refs("legendary")})
        v = Valuer(_catalog(minted=out), AFF, FRIDAY_RELEASED)
        plata = dict(next(p for p in CATALOG["packs"] if p["id"] == "sobre_plata"))
        plata["slots"] = plata["slots"][:4] + [{"rare": 1.0}]
        cat = _catalog(minted=out)
        cat["packs"] = [plata]
        self.assertAlmostEqual(v.pack_ev("sobre_plata", {}), Valuer(cat, AFF, FRIDAY_RELEASED)
                               .pack_ev("sobre_plata", {}), places=9)
        # only legendary out: its .02 lands on the epics, i.e. {rare .86, epic .14}
        leg = {r: 3 for r in _rarity_refs("legendary")}
        v2 = Valuer(_catalog(minted=leg), AFF, FRIDAY_RELEASED)
        plata["slots"] = plata["slots"][:4] + [{"rare": 0.86, "epic": 0.14}]
        cat2 = _catalog(minted=leg)
        cat2["packs"] = [plata]
        self.assertAlmostEqual(v2.pack_ev("sobre_plata", {}), Valuer(cat2, AFF, FRIDAY_RELEASED)
                               .pack_ev("sobre_plata", {}), places=9)
        self.assertLess(v2.pack_ev("sobre_plata", {}), valuer().pack_ev("sobre_plata", {}))

    def test_everything_exhausted_fails_closed(self):
        out = {}
        for rar, n in (("common", 300), ("uncommon", 90), ("rare", 30), ("epic", 9), ("legendary", 3)):
            out.update({r: n for r in _rarity_refs(rar)})
        v = Valuer(_catalog(minted=out), AFF, FRIDAY_RELEASED)
        for p in ("sobre_barrio", "sobre_plata", "sobre_oro"):
            with self.assertRaises(UnknownPack):
                v.pack_ev(p, {})
        # rare and below out: a legendary-only slot still has the epics, a rare slot has nothing
        low = {r: n for r, n in out.items() if r in set(_rarity_refs("common") + _rarity_refs("uncommon")
                                                       + _rarity_refs("rare"))}
        v2 = Valuer(_catalog(minted=low), AFF, FRIDAY_RELEASED)
        self.assertTrue(v2._slot_dist("legendary", None))
        with self.assertRaises(UnknownPack):
            v2._slot_dist("rare", None)

    def test_malformed_slot_fails_closed(self):
        for slot in ({"mythic": 1.0}, {"rare": float("nan")}, {"rare": -0.1}, {"rare": "1"}):
            cat = _catalog()
            cat["packs"] = [{"id": "sobre_x", "slots": [slot]}]
            with self.assertRaises(UnknownPack):
                Valuer(cat, AFF, FRIDAY_RELEASED).pack_ev("sobre_x", {})

    def test_missing_rarity_is_not_a_stock_out(self):
        # legendary entries absent (or with a non-finite book) -> bad data, never the epic fallback
        for how in ("drop", "book", "one_set"):
            cat = _catalog()
            for s in cat["sets"]:
                if how == "one_set" and s["id"] != "LAV":
                    continue
                if how == "book":
                    for c in s["cards"]:
                        if c["rarity"] == "legendary":
                            c["book"] = None
                else:
                    s["cards"] = [c for c in s["cards"] if c["rarity"] != "legendary"]
            v = Valuer(cat, AFF, FRIDAY_RELEASED)
            with self.assertRaises(UnknownPack):
                v._slot_dist("legendary", None)
            with self.assertRaises(UnknownPack):
                v.pack_ev("sobre_oro", {})
            self.assertTrue(v._slot_dist("epic", None))


class TestMasterBonus(unittest.TestCase):
    """master_bonus (V-13): INFERRED base = page cards + epic + legendary of the set, all held."""

    @staticmethod
    def _full(sid="LAV"):
        return collections.Counter({c["id"]: 1 for s in CATALOG["sets"] if s["id"] == sid for c in s["cards"]})

    def test_fires_only_with_all_twelve(self):
        v = valuer()
        full = self._full()
        self.assertEqual(len(full), 12)
        no_mb = Valuer(_catalog(values={"copy_marginals": [1.0, 0.25, 0.1], "page_bonus": 0.25}), AFF,
                       FRIDAY_RELEASED)
        master_base = sum(v.base(r) for r in full)
        self.assertAlmostEqual(v.collection_value(full) - no_mb.collection_value(full), 0.1 * master_base)
        for missing in ("LAV-01", "LAV-11", "LAV-12"):
            c = collections.Counter(full)
            del c[missing]
            self.assertAlmostEqual(v.collection_value(c), no_mb.collection_value(c))
        # the 12th card is worth its first copy + the master bonus
        c = collections.Counter(full)
        del c["LAV-12"]
        self.assertAlmostEqual(v.delta_add(c, "LAV-12"), v.base("LAV-12") + 0.1 * master_base)
        self.assertEqual(v.masters["LAV"], tuple(sorted(full)))

    def test_absent_master_bonus_no_effect(self):
        no_mb = Valuer(_catalog(values={"copy_marginals": [1.0, 0.25, 0.1], "page_bonus": 0.25}), AFF,
                       FRIDAY_RELEASED)
        self.assertEqual(no_mb.master_bonus, 0.0)
        full = self._full()
        expected = sum(no_mb.base(r) for r in full) + 0.25 * sum(no_mb.base(r) for r in no_mb.pages["LAV"])
        self.assertAlmostEqual(no_mb.collection_value(full), expected)

    def test_malformed_master_bonus(self):
        for bad in (float("nan"), float("inf"), "0.1", None):
            with self.assertRaises(ValueError):
                Valuer(_catalog(values={"copy_marginals": [1.0, 0.25, 0.1], "page_bonus": 0.25,
                                        "master_bonus": bad}), AFF, FRIDAY_RELEASED)


class TestNegLedger(unittest.TestCase):
    """11/12 measured neg points on Friday, from cards_all moves + feed prices (P-03, P-04, cap 50)."""
    # offer id -> (price, dealer, we_accepted)  [feed settlements; #2334 price from chato thread 268]
    DEALS = {44: (17, True, True), 480: (9, True, True), 598: (9, False, False), 806: (10, True, True),
             597: (9, False, False), 593: (9, False, False), 920: (24, True, True), 980: (80, False, False),
             1311: (9, False, False), 1334: (10, False, True), 1424: (23, True, True), 1791: (22, True, True),
             1199: (9, False, False), 2334: (32, True, True), 2422: (23, False, True), 2505: (9, False, False),
             2662: (13, True, True)}
    MEAS = {53: 6.8, 64: 20.9, 67: 20.9, 90: 74.9, 92: 81.6, 97: 73.2, 115: 71.3, 118: 77.6, 140: 65.8,
            146: 79.0, 147: 79.0, 155: 74.5}

    def test_neg_11_of_12(self):
        v = valuer()
        moves = collections.defaultdict(list)
        for a in CARDS_ALL.values():
            for h in a["history"]:
                if "t18" in (h["from"], h["to"]):
                    moves[h["tick"]].append((a, h))
        neg = 0.0
        at_tick = {}
        seen = set()
        for t in sorted(moves):
            hb, pb = holdings_at(t, inclusive=False)
            minted = minted_before(t)
            by_why = collections.defaultdict(list)
            for a, h in moves[t]:
                by_why[h["why"]].append((a, h))
            for why, lst in by_why.items():
                if not why.startswith("trade #"):
                    continue
                oid = int(why.split("#")[1])
                price, dealer, we_acc = self.DEALS[oid]
                seen.add(oid)
                h2, p2 = collections.Counter(hb), list(pb)
                for a, h in lst:
                    sign = 1 if h["to"] == "t18" else -1
                    if a["kind"] == "card":
                        h2[a["ref"]] += sign
                    elif sign > 0:
                        p2.append(a["ref"])
                    else:
                        p2.remove(a["ref"])
                dv = v.collection_value(h2, p2, minted) - v.collection_value(hb, pb, minted)
                buy = lst[0][1]["to"] == "t18"
                if dealer:
                    pred = predict_dealer(dv if buy else -dv, price, "buy" if buy else "sell")
                else:
                    pred = predict_team(dv if buy else -dv, price, "buy" if buy else "sell", we_acc)
                neg += pred.neg_lo
            at_tick[t] = neg
        self.assertEqual(seen, set(self.DEALS))
        ok = sum(abs(round(at_tick[t] + 1e-9, 1) - m) < 0.001 for t, m in self.MEAS.items())   # as displayed
        self.assertEqual(ok, 11)
        self.assertTrue(all(abs(at_tick[t] - m) < 0.051 for t, m in self.MEAS.items()))      # 12/12 within ±0.05
        self.assertAlmostEqual(at_tick[92], 81.65, delta=0.01)     # the 12th is display rounding (P-04)
        self.assertAlmostEqual(at_tick[155], 74.452, delta=0.01)


class TestFeeAndPredictions(unittest.TestCase):
    def test_fee_R01(self):
        self.assertEqual(fee(5), 2)
        self.assertEqual(fee(9), 2)
        self.assertEqual(fee(20), 2)
        self.assertEqual(fee(23), 3)
        self.assertEqual(fee(80), 5)
        self.assertEqual(fee(18, 2), 3)
        self.assertEqual(fee(40, 2), 4)
        self.assertEqual(fee(100, 1, 0, 0), 0)
        self.assertEqual(fee(100, 1, 250, 2), 5)          # another venue's parameters (D2)
        self.assertEqual(fee(0, 2), 2)
        for bad in ((-1,), (5, -1), (5, 1, -1), (5, 1, 500, -1), (float("nan"),), (True,)):
            with self.assertRaises(ValueError):
                fee(*bad)

    def test_venue_fee(self):
        self.assertEqual(venue_fee({"id": "v1", "fee_bps": 1000, "fee_per_card": 0}, 37), 4)
        for bad in ({}, {"fee_bps": "500", "fee_per_card": 1}, {"fee_bps": 500}, None):
            with self.assertRaises(ValueError):
                venue_fee(bad, 10)

    def test_predict_team(self):
        p = predict_team(149.875, 80, "buy", False)       # SAL-10, we were the bid maker
        self.assertEqual((p.neg_lo, p.neg_hi, p.cash, p.ladder, p.model), (50.0, 69.875, -80, "0", "P-03"))
        p = predict_team(17.5, 23, "buy", True)            # generic buy as accepter: fee(23) = 3
        self.assertAlmostEqual(p.neg_hi, 17.5 - 23 - 3)
        self.assertEqual(p.cash, -26)
        p = predict_team(1.25, 10, "sell", True)           # MAL-04 sold into a bid: +6.75
        self.assertAlmostEqual(p.neg_lo, 6.75)
        self.assertEqual(p.cash, 8)
        p = predict_team(10.0, 30, "buy", True, fee_bps=1000, per_card=0)   # rival venue fee
        self.assertAlmostEqual(p.neg_hi, 10 - 30 - 3)
        with self.assertRaises(ValueError):
            predict_team(float("inf"), 10, "buy", True)
        with self.assertRaises(ValueError):
            predict_team(1.0, 10, "swap", True)
        self.assertIsInstance(p, Prediction)

    def test_predict_swap(self):
        p = predict_swap(31.5, 9.0, True)
        self.assertAlmostEqual(p.neg_hi, 31.5 - 9 - 2)
        self.assertEqual((p.cash, p.model), (-2, "D1"))
        p = predict_swap(100.0, 1.0, False)
        self.assertEqual((p.neg_lo, p.neg_hi, p.cash), (50.0, 99.0, 0))

    def test_predict_dealer(self):
        p = predict_dealer(9.0, 10, "buy")                  # LAT-01 at 10: -1.0
        self.assertEqual((p.neg_lo, p.neg_hi, p.ladder, p.cash, p.model), (-1.0, -1.0, "0", -10, "P-04"))
        p = predict_dealer(11.0, 9, "buy")                  # SAL-02 at 9: gain counts 0, ladder may rise
        self.assertEqual((p.neg_lo, p.ladder), (0.0, ">=0"))
        p = predict_dealer(17.5, 13, "sell")                # LAV-06 sale: -4.5
        self.assertAlmostEqual(p.neg_lo, -4.5)
        self.assertEqual(p.cash, 13)

    def test_predict_duel_and_none(self):
        p = predict_duel(50, 40, 0.06, 2, "buy")
        self.assertAlmostEqual(p.duel, 10 * 0.94 ** 2)
        self.assertEqual((p.neg_lo, p.cash, p.model), (0.0, 0, "U-01"))
        self.assertLess(predict_duel(50, 60, 0.06, 1, "buy").duel, 0)   # beyond the limit: negative
        self.assertAlmostEqual(predict_duel(30, 40, 0.0, 3, "sell").duel, 10.0)
        with self.assertRaises(ValueError):
            predict_duel(50, 40, 1.5, 1, "buy")
        n = predict_none()
        self.assertEqual((n.neg_lo, n.neg_hi, n.ladder, n.cash, n.model), (0.0, 0.0, "0", 0, "none"))

    def test_verdict(self):
        team = predict_team(149.875, 80, "buy", False)      # 50 .. 69.875
        self.assertEqual(verdict(team, 50.0, 0.0), "pass")
        self.assertEqual(verdict(team, 69.9, 0.0), "pass")
        self.assertEqual(verdict(team, 75.0, 0.0), "surprise_up")
        self.assertEqual(verdict(team, 49.5, 0.0), "soft_fail")
        self.assertEqual(verdict(team, 40.0, 0.0), "hard_fail")
        self.assertEqual(verdict(team, -1.0, 0.0), "hard_fail")
        small = predict_team(9.0, 2, "buy", False)
        self.assertEqual(verdict(small, -0.5, 0.0), "hard_fail")    # predicted gain, measured a loss
        self.assertEqual(verdict(team, 50.0, -0.01), "hard_fail")    # ladder going down
        self.assertEqual(verdict(team, 50.0, 0.02), "surprise_up")   # ladder rose on a team deal
        dealer = predict_dealer(11.0, 9, "buy")
        self.assertEqual(verdict(dealer, 0.0, 0.014), "pass")
        self.assertEqual(verdict(dealer, float("nan"), 0.0), "hard_fail")


class TestNoIO(unittest.TestCase):
    def test_module_has_no_file_or_network_io(self):
        src = (ROOT / "agent" / "valuation.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        banned_names = {"open", "exec", "eval", "__import__", "input"}
        banned_mods = {"io", "os", "pathlib", "json", "urllib", "http", "socket", "shutil", "subprocess",
                       "tempfile", "time", "bazaar_sdk"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                self.assertNotIn(node.id, banned_names, f"line {node.lineno}")
            if isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, {"read_text", "write_text", "open", "load", "dump"},
                                 f"line {node.lineno}")
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertNotIn(a.name.split(".")[0], banned_mods)
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], banned_mods)


if __name__ == "__main__":
    unittest.main()
