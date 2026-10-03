"""M4a INV-05: exact structure. Twisted offers + 1000 mutations -> 0 approvals; real offers keep passing."""
from __future__ import annotations

import copy
import json
import random
import unittest
from pathlib import Path

from agent import guards
from agent.offer_safety import executable_offer, offer_ok
from tests.test_guards import HARVEST, Ctx, accept_args, load

FIX = Path(__file__).resolve().parent / "fixtures" / "twisted_offers.json"
TWISTED = json.loads(FIX.read_text(encoding="utf-8"))


def _ctx() -> Ctx:
    # one of our own offers (id 4242) on the book, so "id of an own offer" mutations have a target
    own = {"id": 4242, "maker": "t18", "to": None, "venue": "rastro", "thread": None, "status": "open",
           "give": {"cash": 0, "assets": [{"id": 423, "kind": "card", "ref": "LAV-04"}], "types": []},
           "want": {"cash": 12, "assets": [], "types": []}, "expires_tick": 260, "created_tick": 150}
    return Ctx(tick=TWISTED["tick"], my_offers=(own,), own_pseudonym=TWISTED["own_pseudonym"])


def _verdict(ctx: Ctx, base: str, offer, fp=None):
    a = accept_args(TWISTED["bases"][base]["intent"], offer, fingerprint=fp)
    return ctx.check_accept(a, offer)


# ------------------------------------------------------------------------------------------ mutators

REFS = ["LAT-08", "SAL-10", "MAL-04", "LAV-09", "RET-01", "CHA-10", "LAT-10", "LAT-09", "LAV-03"]


def _price_side(base):
    return {"buy": "want", "sell": "give", "swap": None}[base]


def m_status(o, base, r):
    o["status"] = r.choice(["queued", "settled", "cancelled", "expired", "OPEN", "", None, 1])


def m_expire(o, base, r):
    o["expires_tick"] = r.choice([TWISTED["tick"], TWISTED["tick"] - 1, TWISTED["tick"] - 100, 0, "230", 230.0])


def m_to(o, base, r):
    o["to"] = r.choice(["t05", "t01", "T18", "t18 ", "", 0, ["t18"]])


def m_venue(o, base, r):
    o["venue"] = r.choice(["v01", "RASTRO", "rastro ", None, "", "v04"])


def m_maker(o, base, r):
    o["maker"] = r.choice(["t18", TWISTED["own_pseudonym"], "", None, 18])


def m_id(o, base, r):
    o["id"] = r.choice([4242, True, "9001", -1, 0, 9001.0])


def m_thread(o, base, r):
    o["thread"] = r.choice([1, 77, "x", {"id": 1}])


def m_extra_top(o, base, r):
    o[r.choice(["escrow", "conditions", "bundle", "also", "x"])] = r.choice([{"cash": 1}, [1], "yes", 5, True])


def m_extra_side(o, base, r):
    side = o[r.choice(["give", "want"])]
    side[r.choice(["bonus", "conditions", "packs", "extra"])] = r.choice([{"cash": 1}, ["SAL-10"], "x", 3])


def m_side_type(o, base, r):
    o[r.choice(["give", "want"])] = r.choice([None, [], "cash", 5, [{"cash": 1}]])


def m_price(o, base, r):
    side = _price_side(base)
    if side is None:                       # swap: any cash breaks the no-cash rule
        o[r.choice(["give", "want"])]["cash"] = r.randint(1, 50)
    else:                                  # always away from the base price, so two mutations cannot cancel
        o[side]["cash"] = TWISTED["bases"][base]["intent"]["price"] + r.choice([-1, 1]) * r.randint(1, 15)


def m_cash_type(o, base, r):
    side = _price_side(base) or r.choice(["give", "want"])
    o[side]["cash"] = r.choice([True, "20", 20.0, -3, 10 ** 7, [20]])


def m_other_cash(o, base, r):
    side = {"buy": "give", "sell": "want", "swap": "give"}[base]
    o[side]["cash"] = r.randint(1, 40)


def m_ref(o, base, r):
    if base == "sell":
        o["want"]["types"] = ["card:" + r.choice([x for x in REFS if x != "LAV-03"])]
    elif base == "buy":
        o["give"]["assets"][0]["ref"] = r.choice([x for x in REFS if x != "LAT-09"])
        o["give"]["assets"][0].pop("set", None)
    else:
        if r.random() < 0.5:
            o["give"]["assets"][0]["ref"] = r.choice([x for x in REFS if x not in ("LAT-10", "MAL-04")])
            o["give"]["assets"][0].pop("set", None)
        else:
            o["want"]["types"] = ["card:" + r.choice([x for x in REFS if x != "MAL-04"])]


def m_add_item(o, base, r):
    side = o[r.choice(["give", "want"])]
    if r.random() < 0.5:
        side.setdefault("assets", []).append({"id": r.randint(600, 900), "kind": "card", "ref": r.choice(REFS)})
    else:
        side.setdefault("types", []).append("card:" + r.choice(REFS))


def m_garbage_type(o, base, r):
    side = o["want"] if base != "buy" else o["give"]
    side["assets"] = []
    side["types"] = [r.choice(["card:lat-09", "card:LAT-9", "LAT-09", "pack:sobre_oro", "card:", "card:LAV-03 ",
                               "card:MAL-04\n", 7])]


def m_asset_field(o, base, r):
    side = o["give"] if base != "sell" else None
    if side is None:
        o["give"]["assets"] = [{"id": r.choice([True, 0, -4, "261"]), "kind": "card", "ref": "LAT-09"}]
        return
    a = side["assets"][0]
    k = r.choice(["kind", "id", "ref", "set"])
    a[k] = {"kind": r.choice(["pack", "Card", None]), "id": r.choice([True, 0, -4, "7001", 7001.5]),
            "ref": r.choice(["lat-09", "LAT09", None, 9]), "set": r.choice(["SAL", "XXX"])}[k]


def m_want_foreign_asset(o, base, r):
    o["want"]["assets"] = [{"id": r.choice([999, 180, 256]), "kind": "card", "ref": "SAL-10"}]


MUTATORS = [m_status, m_expire, m_to, m_venue, m_maker, m_id, m_thread, m_extra_top, m_extra_side, m_side_type,
            m_price, m_cash_type, m_other_cash, m_ref, m_add_item, m_garbage_type, m_asset_field,
            m_want_foreign_asset]


class TwistedOffers(unittest.TestCase):
    def setUp(self):
        self.ctx = _ctx()

    def test_fixture_has_at_least_60(self):
        self.assertGreaterEqual(len(TWISTED["twisted"]), 60)

    def test_bases_pass_positive_control(self):
        for base, spec in TWISTED["bases"].items():
            with self.subTest(base=base):
                v = _verdict(self.ctx, base, copy.deepcopy(spec["offer"]))
                self.assertTrue(v.ok, v)

    def test_twisted_with_own_fingerprint_never_approved(self):
        for t in TWISTED["twisted"]:
            with self.subTest(t["name"]):
                o = copy.deepcopy(t["offer"])
                v = _verdict(self.ctx, t["base"], o, fp=guards.fingerprint(o))
                self.assertFalse(v.ok, t["name"])

    def test_twisted_with_base_fingerprint_never_approved(self):
        for t in TWISTED["twisted"]:
            with self.subTest(t["name"]):
                base_fp = guards.fingerprint(TWISTED["bases"][t["base"]]["offer"])
                v = _verdict(self.ctx, t["base"], copy.deepcopy(t["offer"]), fp=base_fp)
                self.assertFalse(v.ok, t["name"])

    def test_1000_mutations_zero_approvals(self):
        r = random.Random(18)
        approvals = []
        for i in range(1000):
            base = r.choice(sorted(TWISTED["bases"]))
            o = copy.deepcopy(TWISTED["bases"][base]["offer"])
            names = []
            for _ in range(r.randint(1, 3)):
                m = r.choice(MUTATORS)
                try:
                    m(o, base, r)
                except (TypeError, KeyError, IndexError, AttributeError):
                    continue           # an earlier mutation already broke the structure this one edits
                names.append(m.__name__)
            self.assertTrue(names, "the first mutation always applies to a clean base")
            fp = guards.fingerprint(o) if r.random() < 0.7 else guards.fingerprint(TWISTED["bases"][base]["offer"])
            v = _verdict(self.ctx, base, o, fp=fp)
            if v.ok:
                approvals.append((i, base, names, o))
        self.assertEqual(approvals, [])


class CanonicalAndFingerprint(unittest.TestCase):
    def test_real_rastro_offers_are_canonical(self):
        offers = load("rastro_offers.json")["offers"]
        shapes = [guards.canonical_offer(o) for o in offers]
        self.assertEqual(sum(1 for s in shapes if s is None), 0)
        self.assertEqual(sum(1 for s in shapes if s["shape"] == "sell"), 49)
        self.assertEqual(sum(1 for s in shapes if s["shape"] == "bid"), 10)

    def test_dealer_offers_are_not_team_canonical(self):
        for th in load("me_threads_full.json"):
            for m in th["messages"]:
                o = m.get("offer")
                if o and o["maker"] == th["with"]:
                    self.assertIsNone(guards.canonical_offer(o))   # thread set / pack types

    def test_canonical_swap_both_directions(self):
        give_asset = {"id": 1, "maker": "m", "status": "open", "give": {"assets": [{"id": 5, "kind": "card", "ref": "LAT-09"}]},
                      "want": {"cards": ["MAL-04"]}}
        give_type = {"id": 2, "maker": "m", "status": "open", "give": {"types": ["card:LAT-09"]},
                     "want": {"assets": [{"id": 295, "kind": "card", "ref": "MAL-04"}]}}
        a, b = guards.canonical_offer(give_asset), guards.canonical_offer(give_type)
        self.assertEqual((a["shape"], a["ref_in"], a["ref_out"], a["want_asset"]), ("swap", "LAT-09", "MAL-04", None))
        self.assertEqual((b["shape"], b["ref_in"], b["ref_out"], b["want_asset"]), ("swap", "LAT-09", "MAL-04", 295))

    def test_fingerprint_stable_and_sensitive(self):
        o = load("rastro_offers.json")["offers"][0]
        fp = guards.fingerprint(o)
        stripped = copy.deepcopy(o)
        for a in stripped["give"]["assets"]:
            a.pop("serial"), a.pop("print_run")              # sensor allowlist may drop decorations
        self.assertEqual(fp, guards.fingerprint(stripped))
        for k, val in (("status", "settled"), ("to", "t05"), ("venue", "v01"), ("expires_tick", 1)):
            self.assertNotEqual(fp, guards.fingerprint({**o, k: val}))
        self.assertNotEqual(fp, guards.fingerprint({**o, "want": {**o["want"], "cash": 9}}))
        self.assertEqual(guards.fingerprint({"no": "id"}), "")

    def test_duel_fingerprint(self):
        d = load("duels_live.json")["duels"][0]
        fp = guards.duel_fingerprint(d)
        self.assertTrue(fp)
        self.assertNotEqual(fp, guards.duel_fingerprint({**d, "rival_offer": {"id": 1, "price": 5, "tick": 160}}))
        self.assertNotEqual(fp, guards.duel_fingerprint({**d, "messages": d["messages"] + [{}]}))


class DealerOffersSafety(unittest.TestCase):
    """INV-05 part 2: the 56 real dealer offers."""

    def _dealer_offers(self):
        out = []
        for th in load("me_threads_full.json"):
            for m in th["messages"]:
                o = m.get("offer")
                if o and o["maker"] == th["with"]:
                    out.append((th, o))
        return out

    def test_56_dealer_offers(self):
        offers = self._dealer_offers()
        self.assertEqual(len(offers), 56)
        for th, o in offers:
            buying = "buy" in th["topic"]
            kw = dict(dealer=th["with"], team="t18", buying=buying)
            self.assertTrue(offer_ok(o, th["topic"], buying), o["id"])
            self.assertTrue(executable_offer({**o, "status": "open"}, th["topic"], tick=o["created_tick"], **kw))
            self.assertFalse(executable_offer(o, th["topic"], tick=o["created_tick"], **kw))   # real status
            self.assertFalse(executable_offer({**o, "status": "open"}, th["topic"], tick=o["expires_tick"] + 1, **kw))

    def test_offer_ok_rejects_extra_side_keys(self):
        th, o = self._dealer_offers()[0]
        buying = "buy" in th["topic"]
        bad = copy.deepcopy(o)
        bad["want"]["conditions"] = ["SAL-10"]
        self.assertFalse(offer_ok(bad, th["topic"], buying))
        bad = copy.deepcopy(o)
        bad["give"] = [bad["give"]]
        self.assertFalse(offer_ok(bad, th["topic"], buying))


if __name__ == "__main__":
    unittest.main()
