"""M3 valuation tests: anchored on measured Friday data (tests/fixtures/harvest)."""
from __future__ import annotations

import ast
import collections
import json
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


class TestSelfCheckRobust(unittest.TestCase):
    """Sat review: nothing unmeasured may fail self_check (valuation_ok False blocks every value write)."""

    def test_unknown_asset_kind_is_not_a_pack(self):
        me = dict(ME159)
        me["assets"] = list(ME159["assets"]) + [{"id": 9998, "kind": "ticket", "ref": "golden_ticket"}]
        self.assertEqual(Valuer.holdings(me), Valuer.holdings(ME159))
        ok, err, mism = valuer().self_check(me, VALUES_ALL)
        self.assertTrue(ok, mism)
        me["assets"].append({"id": 9999, "kind": "pack", "ref": "sobre_nuevo"})   # a real unknown pack still fails
        self.assertFalse(valuer().self_check(me, VALUES_ALL)[0])

    def test_fourth_copy_not_compared(self):
        v = valuer()
        me = dict(ME159)
        extra = [dict(a, id=8000 + i, your_value=0.0) for i, a in
                 enumerate(a for a in ME159["assets"] if a.get("ref") == "LAT-01")]
        me["assets"] = list(ME159["assets"]) + extra                        # LAT-01 x4
        c, packs = Valuer.holdings(me)
        self.assertEqual(c["LAT-01"], 4)
        me["collection_value"] = v._total(c, packs, None, "buy")            # server prices the 4th copy at 0
        ok, err, mism = v.self_check(me, VALUES_ALL)
        self.assertTrue(ok, mism)
        me["collection_value"] = v.collection_value(c, packs)               # ... or at MARG[-1]
        self.assertTrue(v.self_check(me, VALUES_ALL)[0])
        me["collection_value"] = v.collection_value(c, packs) + 5.0         # anything else is still a mismatch
        self.assertFalse(v.self_check(me, VALUES_ALL)[0])


class TestMasterBonus(unittest.TestCase):
    def test_master_bonus_fires_with_page_epic_legendary(self):
        # Sat t950: the server valued SAL-12 at 593.5 with our page + SAL-11 held = page/master model (495 without)
        import copy
        cat = copy.deepcopy(CATALOG)
        cat["values"]["master_bonus"] = 0.1
        v = Valuer(cat, {"SAL": 1.1}, frozenset({"SAL"}))
        refs = v.masters.get("SAL")
        self.assertTrue(refs and len(refs) == len(v.pages["SAL"]) + 2)
        held = {r: 1 for r in refs if r != refs[-1]}
        base = sum(v.base(r) for r in refs)
        self.assertAlmostEqual(v.delta_add(held, refs[-1], ()) - v.base(refs[-1]), 0.1 * base, places=6)
        self.assertEqual(Valuer(CATALOG, {"SAL": 1.1}, frozenset({"SAL"})).master_bonus,
                         float(CATALOG["values"].get("master_bonus", 0.0)))


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
