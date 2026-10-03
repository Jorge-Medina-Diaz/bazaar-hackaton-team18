"""M0: exact types, Intent indexed by id, Limits from the harvest, redaction, isolation, fixtures without keys."""
from __future__ import annotations

import ast
import dataclasses
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from tests import HARVEST, PROBE
from agent import contracts as C
from agent.contracts import (ARGS, FRIDAY, KINDS, TACTICS, Intent, Limits, Paths, Prediction, Secrets, World,
                             domains_of, expiry_units, intent_id, make_intent)
from agent.redact import REDACTED, redact

ROOT = Path(__file__).resolve().parents[1]
P0 = Prediction(0.0, 0.0, "0", 0, None, "none")
PB = Prediction(5.0, 7.5, ">=0", -20, None, "P-03")

VALID = {
    "accept": {"offer_id": 2460, "source": "team", "ref": "LAV-03", "side": "buy", "price": 8,
               "thread_id": None, "give_asset": None, "fingerprint": "abc", "resupply": False, "venue": "rastro"},
    "list_offer": {"side": "bid", "ref": "RET-01", "asset_id": None, "price": 49, "expires_ticks": 20,
                   "closer": True, "want_ref": None},
    "cancel": {"offer_id": 2463, "ref": None},
    "open_thread": {"dealer": "chato", "side": "buy", "ref": "RET-02", "asset_ids": (), "limit": 30},
    "say": {"thread_id": 7, "ref": "RET-02", "price": 20, "template": "chato_buy", "variant": 0},
    "close_thread": {"thread_id": 7, "ref": "RET-02"},
    "open_pack": {"asset_id": 999},
    "duel_say": {"duel_id": 3, "price": 40, "days": None, "template": "duel", "variant": 1},
    "duel_accept": {"duel_id": 3, "fingerprint": "f00"},
}


def mk(kind, tactic="manual", pred=P0, **over):
    a = dict(VALID[kind])
    a.update(over)
    return make_intent(kind, tactic, a, "why", "effect", pred)


def load(name, base=HARVEST):
    return json.loads((base / name).read_text(encoding="utf-8"))


class TestEnvironment(unittest.TestCase):
    def test_tests_package_isolates_env(self):
        self.assertEqual(os.environ.get("BAZAAR_TEST"), "1")
        self.assertEqual(os.environ.get("BAZAAR_NO_DOTENV"), "1")
        self.assertNotIn("BAZAAR_KEY", os.environ)
        self.assertNotIn("BAZAAR_URL", os.environ)

    def test_default_paths_never_repo_in_tests(self):
        p = Paths.at()
        self.assertNotEqual(p.root, ROOT)
        self.assertFalse(str(p.journal).startswith(str(ROOT)))
        self.assertEqual(Paths.at(), p)               # stable within the process

    def test_contracts_parse_as_python39(self):
        for f in ("agent/contracts.py", "agent/redact.py", "tests/__init__.py"):
            src = (ROOT / f).read_text(encoding="utf-8")
            ast.parse(src, filename=f, feature_version=(3, 9))
            self.assertIn("from __future__ import annotations", src)


class TestPaths(unittest.TestCase):
    def test_layout(self):
        tmp = tempfile.mkdtemp()
        p = Paths.at(tmp)
        r = Path(tmp).resolve()
        self.assertEqual(p.root, r)
        self.assertEqual(p.journal, r / "logs/run/journal.jsonl")
        self.assertEqual(p.untrusted, r / "logs/run/untrusted.jsonl")
        self.assertEqual(p.snaps, r / "logs/run/snap")
        self.assertEqual(p.state, r / "state")
        self.assertEqual(p.inbox, r / "state/inbox")
        self.assertEqual(p.lock, r / "state/writer.lock")
        self.assertEqual(p.baseline, r / "state/baseline.json")
        self.assertEqual(p.armed, r / "state/armed.json")
        self.assertEqual(p.pauses, r / "state/pauses.json")
        self.assertEqual(p.frozen, r / "state/frozen.json")
        self.assertEqual(p.selftest, r / "state/selftest.json")
        self.assertEqual(p.stop_names, ("STOP", "stop"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            p.root = Path(".")  # type: ignore[misc]

    def test_default_root_outside_tests_is_repo(self):
        old = os.environ.pop("BAZAAR_TEST")
        try:
            self.assertEqual(Paths.at().root, ROOT)
        finally:
            os.environ["BAZAAR_TEST"] = old


class TestVocab(unittest.TestCase):
    def test_kinds_and_tactics(self):
        self.assertEqual(KINDS, ("accept", "list_offer", "cancel", "open_thread", "say", "close_thread",
                                 "open_pack", "duel_say", "duel_accept"))
        self.assertNotIn("open_venue", KINDS)
        self.assertIn("manual", TACTICS)
        self.assertEqual(C.BUY_TACTICS, frozenset({"dealers", "rastro", "closer"}))
        self.assertEqual(C.TALK_KINDS, frozenset({"open_thread", "say", "duel_say", "duel_accept"}))
        self.assertEqual(set(ARGS), set(KINDS))
        self.assertEqual(C.RIVAL_VENUE_MIN_GAIN, 10.0)
        self.assertEqual(C.RIVAL_TOP_N, 5)

    def test_late_input_args(self):
        self.assertIs(ARGS["accept"]["venue"], str)
        self.assertEqual(ARGS["list_offer"]["want_ref"], (str, C.NONE))
        self.assertEqual(ARGS["accept"]["give_asset"], (int, C.NONE))
        with self.assertRaises(TypeError):
            ARGS["accept"]["x"] = int  # type: ignore[index]

    def test_get_allowlist(self):
        ok = ["/api/clock", "/api/venues", "/api/venues/rastro/offers", "/api/venues/v01/offers",
              "/api/me/offers", "/api/threads/12", "/api/leaderboard", "/api/cards/5"]
        bad = ["/api/admin", "/api//admin", "/API/clock", "/api/venues/../admin/offers", "/api/venues/V01/offers",
               "/api/venues/v01/offers/1", "/api/clock\n", "/api/%61dmin", "/api/venues/v01"]
        for p in ok:
            self.assertTrue(re.fullmatch(C.GET_ALLOWLIST, p), p)
        for p in bad:
            self.assertIsNone(re.fullmatch(C.GET_ALLOWLIST, p), p)


class TestMakeIntent(unittest.TestCase):
    def test_every_kind_valid(self):
        for kind in KINDS:
            it = mk(kind)
            self.assertEqual(it.kind, kind)
            self.assertIsInstance(it.args, MappingProxyType)
            with self.assertRaises(TypeError):
                it.args["x"] = 1  # type: ignore[index]

    def test_exact_keys(self):
        for kind in KINDS:
            a = dict(VALID[kind])
            k = next(iter(a))
            a.pop(k)
            with self.assertRaises(ValueError, msg=kind):
                make_intent(kind, "manual", a, "r", "e", P0)
            a = dict(VALID[kind], extra=1)
            with self.assertRaises(ValueError, msg=kind):
                make_intent(kind, "manual", a, "r", "e", P0)

    def test_bool_is_not_int_and_int_is_not_bool(self):
        with self.assertRaises(ValueError):
            mk("accept", price=True)
        with self.assertRaises(ValueError):
            mk("cancel", offer_id=False)
        with self.assertRaises(ValueError):
            mk("accept", resupply=0)
        with self.assertRaises(ValueError):
            mk("list_offer", closer=1)
        with self.assertRaises(ValueError):
            mk("accept", give_asset=True, side="sell")
        with self.assertRaises(ValueError):
            mk("accept", price=8.0)
        with self.assertRaises(ValueError):
            mk("accept", offer_id="2460")

    def test_optional_types(self):
        mk("cancel", ref="LAT-01")
        mk("cancel", ref=None)
        mk("duel_say", days=3)
        mk("duel_say", days=-2)                       # days may be signed
        with self.assertRaises(ValueError):
            mk("duel_say", days="3")
        with self.assertRaises(ValueError):
            mk("open_thread", asset_ids=[1, 2])        # tuple only
        with self.assertRaises(ValueError):
            mk("open_thread", asset_ids=(1, True))
        mk("open_thread", side="sell", asset_ids=(1, 2))

    def test_enums_and_meta(self):
        with self.assertRaises(ValueError):
            mk("accept", source="broker")
        with self.assertRaises(ValueError):
            mk("accept", side="bid")
        with self.assertRaises(ValueError):
            mk("list_offer", side="buy")
        with self.assertRaises(ValueError):
            mk("accept", venue="V01/../admin")
        with self.assertRaises(ValueError):
            make_intent("open_venue", "manual", {}, "r", "e", P0)
        with self.assertRaises(ValueError):
            mk("cancel", tactic="broker")
        with self.assertRaises(ValueError):
            make_intent("cancel", "manual", VALID["cancel"], "r", "e", P0, priority=True)
        with self.assertRaises(ValueError):
            make_intent("cancel", "manual", VALID["cancel"], "r", "e", "pred")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            mk("cancel", pred=Prediction(float("nan"), 0.0, "0", 0))
        with self.assertRaises(ValueError):
            mk("cancel", pred=Prediction(0.0, 0.0, "up", 0))
        with self.assertRaises(ValueError):
            mk("cancel", pred=Prediction(0.0, 0.0, "0", 1.5))  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            mk("accept", price=-1)

    def test_swaps_d1(self):
        it = mk("list_offer", tactic="rastro", side="swap", ref="MAL-02", asset_id=301, price=0, want_ref="LAT-09",
                closer=False)
        self.assertEqual(domains_of(it), frozenset({"asset:301", "ref:MAL-02", "ref:LAT-09"}))
        with self.assertRaises(ValueError):
            mk("list_offer", side="swap", ref="MAL-02", asset_id=301, price=5, want_ref="LAT-09")
        with self.assertRaises(ValueError):
            mk("list_offer", side="swap", ref="MAL-02", asset_id=None, price=0, want_ref="LAT-09")
        with self.assertRaises(ValueError):
            mk("list_offer", side="swap", ref="MAL-02", asset_id=301, price=0, want_ref=None)
        with self.assertRaises(ValueError):
            mk("list_offer", side="bid", want_ref="LAT-09")
        with self.assertRaises(ValueError):
            mk("list_offer", side="sell", asset_id=None)
        with self.assertRaises(ValueError):
            mk("list_offer", side="bid", asset_id=5)
        with self.assertRaises(ValueError):
            mk("list_offer", expires_ticks=0)
        a = mk("accept", side="swap", price=0, give_asset=262, ref="LAT-09", venue="v02")
        self.assertIn("asset:262", domains_of(a))
        with self.assertRaises(ValueError):
            mk("accept", side="swap", price=0, give_asset=None)
        with self.assertRaises(ValueError):
            mk("accept", side="swap", price=3, give_asset=262)
        with self.assertRaises(ValueError):
            mk("accept", side="buy", give_asset=262)


class TestIdentity(unittest.TestCase):
    def test_intent_eq_false_and_indexable_by_id(self):
        a, b = mk("cancel"), mk("cancel")
        self.assertNotEqual(a, b)                     # eq=False: identity, never by value
        self.assertEqual(len({a, b}), 2)              # hashable
        self.assertEqual(intent_id(10, a), intent_id(10, b))
        idx = {intent_id(10, it): it for it in (a, b, mk("cancel", offer_id=1652))}
        self.assertEqual(len(idx), 2)
        self.assertIs(idx[intent_id(10, a)], b)

    def test_intent_id_formula(self):
        import hashlib
        it = mk("accept")
        raw = f"7|manual|accept|{json.dumps(dict(it.args), sort_keys=True)}"
        self.assertEqual(intent_id(7, it), hashlib.sha1(raw.encode()).hexdigest()[:16])
        self.assertRegex(intent_id(7, it), r"^[0-9a-f]{16}$")
        self.assertNotEqual(intent_id(7, it), intent_id(8, it))
        self.assertNotEqual(intent_id(7, it), intent_id(7, mk("accept", tactic="rastro")))
        rev = dict(reversed(list(VALID["accept"].items())))
        self.assertEqual(intent_id(7, it), intent_id(7, make_intent("accept", "manual", rev, "x", "y", PB)))
        it2 = mk("open_thread", asset_ids=(3, 4), side="sell")
        self.assertRegex(intent_id(1, it2), r"^[0-9a-f]{16}$")

    def test_direct_intent_args_are_frozen(self):
        it = Intent("cancel", "manual", {"offer_id": 1, "ref": None}, "r", "e", P0)
        self.assertIsInstance(it.args, MappingProxyType)

    def test_domains(self):
        self.assertEqual(domains_of(mk("accept", thread_id=4, source="dealer")),
                         frozenset({"offer:2460", "thread:4", "ref:LAV-03"}))
        self.assertEqual(domains_of(mk("open_thread", side="sell", asset_ids=(1, 2))),
                         frozenset({"dealer:chato", "ref:RET-02", "asset:1", "asset:2"}))
        self.assertEqual(domains_of(mk("duel_accept")), frozenset({"duel:3"}))
        self.assertEqual(domains_of(mk("open_pack")), frozenset({"asset:999"}))
        self.assertEqual(domains_of(mk("cancel")), frozenset({"offer:2463"}))
        self.assertIsInstance(domains_of(mk("cancel")), frozenset)


class TestLimits(unittest.TestCase):
    def test_harvest_clock(self):
        self.assertEqual(Limits.from_clock(load("clock.json"), None), Limits(1, 1, 6, 30, 12))
        self.assertEqual(FRIDAY, Limits(1, 1, 6, 30, 12))

    def test_missing_or_bad_values(self):
        self.assertEqual(Limits.from_clock({}, None), FRIDAY)
        prev = Limits(3, 2, 10, 50, 20)
        self.assertEqual(Limits.from_clock({}, prev), FRIDAY)               # min(prev, FRIDAY)
        low = Limits(1, 1, 4, 20, 8)
        self.assertEqual(Limits.from_clock({"limits": None}, low), low)
        clock = {"limits": {"accepts_per_team_per_tick": True, "messages_per_side_per_tick": "2",
                            "max_open_threads_per_team": 9, "max_open_offers_per_team": -1,
                            "offers_per_team_per_tick": 15}}
        self.assertEqual(Limits.from_clock(clock, low), Limits(1, 1, 9, 20, 15))


class TestWorldAndTypes(unittest.TestCase):
    BASE = dict(tick=159, t_hours=2.65, round=1, tick_seconds=60.0, tick_deadline=0.0, clock={},
                limits=FRIDAY, reading="?", me={}, my_offers=(), offers_to_us=(), board=(), own_pseudonym=None,
                threads={}, foreign_threads=(), duels=(), catalog={}, schedule={}, released_sets=frozenset(),
                feed_new=(), server_values={}, down=frozenset())

    def test_world_late_fields(self):
        w = World(**self.BASE)
        self.assertEqual(dict(w.boards), {})
        self.assertEqual(w.venues, ())
        self.assertEqual(w.leaderboard, ())
        w2 = World(**self.BASE, boards={"rastro": (), "v01": ({"id": 1},)},
                   venues=({"id": "v01", "owner": "t06", "fee_bps": 50, "fee_per_card": 0, "status": "open"},),
                   leaderboard=("t13", "t12"))
        self.assertEqual(w2.boards["v01"][0]["id"], 1)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            w2.tick = 1  # type: ignore[misc]
        names = [f.name for f in dataclasses.fields(World)]
        self.assertEqual(names[:22], list(self.BASE))

    def test_secrets_repr(self):
        s = Secrets("bk_supersecret123")
        self.assertNotIn("supersecret", repr(s))
        self.assertNotIn("supersecret", str(s))
        self.assertEqual(s.starter_broker_key, "bk_supersecret123")

    def test_misc_types(self):
        self.assertEqual(C.Verdict(True, "ok").detail, "")
        o = C.Outcome("abc", "would")
        self.assertIsNone(o.code)
        self.assertIn(o.status, C.OUTCOME_STATUSES)
        n = C.Need("RET", "RET-01", "team", 49, True)
        self.assertTrue(n.closer)
        book_fields = {f.name for f in dataclasses.fields(C.Book)}
        for k in ("cash_free", "projected", "own_bids", "bid_band", "frozen_closer", "delivery_risk",
                  "recent_rastro", "unknown_domains", "valuation_ok"):
            self.assertIn(k, book_fields)
        self.assertIn("grant_lookahead_ticks", C.PlanCfg.__annotations__)

    def test_expiry_units_d3(self):
        self.assertEqual(expiry_units(10, 30.0), 20)
        self.assertEqual(expiry_units(10, 15.0), 10)
        self.assertEqual(expiry_units(10, 60.0), 40)
        self.assertEqual(expiry_units(1, 5.0), 1)
        self.assertEqual(expiry_units(3, 10.0), 2)     # ceil(2.0)
        self.assertEqual(expiry_units(4, 10.0), 3)     # ceil(2.67)
        for bad in ((0, 30.0), (True, 30.0), (5, 0), (5, float("inf"))):
            with self.assertRaises(ValueError):
                expiry_units(*bad)


class TestRedact(unittest.TestCase):
    def test_keys_patterns_and_equality(self):
        os.environ["BAZAAR_KEY"] = "weird-format-key-value"
        try:
            obj = {"api_key": "x", "Token": "y", "starter_broker_key": "z", "PASSWORD": "p", "secretive": 1,
                   "msg": "use tk-abcdef123 now", "b": ("bk_9999999", ["fine", "LAT-09"]),
                   "env": "weird-format-key-value", "inner": "Bearer weird-format-key-value",
                   "mine": "s3cr3t-value", "n": 5, "f": 1.5, "none": None, "flag": True,
                   "ids": frozenset({1, 2}), "pred": PB}
            r = redact(obj, secrets=("s3cr3t-value",))
        finally:
            os.environ.pop("BAZAAR_KEY", None)
        for k in ("api_key", "Token", "starter_broker_key", "PASSWORD", "secretive"):
            self.assertNotIn(k, r)
        self.assertEqual(r["msg"], f"use {REDACTED} now")
        self.assertEqual(r["b"], (REDACTED, ["fine", "LAT-09"]))
        self.assertEqual(r["env"], REDACTED)
        self.assertEqual(r["inner"], f"Bearer {REDACTED}")
        self.assertEqual(r["mine"], REDACTED)
        self.assertEqual((r["n"], r["f"], r["none"], r["flag"]), (5, 1.5, None, True))
        self.assertEqual(r["ids"], frozenset({1, 2}))
        self.assertEqual(r["pred"]["neg_lo"], 5.0)
        self.assertEqual(obj["api_key"], "x")          # input untouched

    def test_short_codes_survive(self):
        self.assertEqual(redact({"ref": "tk-12", "x": "bk-ab"}), {"ref": "tk-12", "x": "bk-ab"})
        self.assertEqual(redact(MappingProxyType({"a": [1, {"key": 2}]})), {"a": [1, {}]})


class TestFixtures(unittest.TestCase):
    def test_present(self):
        for name in ("clock.json", "me.json", "me_offers.json", "rastro_offers.json", "catalog.json",
                     "venues.json", "leaderboard.json", "me_threads_full.json", "duels_live.json"):
            self.assertTrue((HARVEST / name).is_file(), name)
        for name in ("clock.json", "me.json", "venues_rastro_offers.json", "venues.json"):
            self.assertTrue((PROBE / name).is_file(), name)

    def test_no_keys_anywhere(self):
        pat = re.compile(r"(tk|bk)[-_][A-Za-z0-9-]{6,}|tk-|bk_")
        files = list(HARVEST.rglob("*"))
        self.assertGreater(len(files), 20)
        for f in files:
            if f.is_file():
                text = f.read_text(encoding="utf-8")
                self.assertIsNone(pat.search(text), f.name)
                if f.suffix == ".json":
                    data = json.loads(text)
                    self.assertEqual(redact(data), data, f.name)


if __name__ == "__main__":
    unittest.main()
