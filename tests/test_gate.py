"""M5 tests: Gate (INV-02, 03, 07, 08, 14, 15, 16, 22) with the real Journal, transport permit and valuation,
and small doubles for guards (M4a), talk (M4b), the transport's HTTP side and the valuer."""
from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import tempfile
import unittest
from dataclasses import dataclass, field, replace
from types import MappingProxyType, SimpleNamespace

import tests  # noqa: F401  (isolated environment)
from agent import gate as gate_mod
from agent import transport as tr
from agent import valuation as val
from agent.contracts import FRIDAY, TEAM, Book, Limits, Paths, Verdict, World, make_intent
from agent.execution import team_writer, writer_lock
from agent.journal import Journal

VALUES = {"LAT-09": 40.0, "LAT-10": 35.0, "RET-01": 30.0, "RET-02": 28.0, "SAL-01": 25.0,
          "MAL-04": 3.0, "LAV-03": 4.0, "CHA-01": 20.0}
TICK = 200


# --------------------------------------------------------------------------------------------- doubles

@dataclass(frozen=True)
class Counters:
    tick: int
    accepts: int = 0
    listings: int = 0
    threads_opened: int = 0
    offers_opened: int = 0
    msgs: set = field(default_factory=set)


def _fp(o):
    return hashlib.sha1(json.dumps({k: o.get(k) for k in ("id", "give", "want", "to", "venue", "expires_tick",
                                                         "status")}, sort_keys=True).encode()).hexdigest()


def _dfp(d):
    ro = d.get("rival_offer") or {}
    return hashlib.sha1(json.dumps([d.get("duel"), ro.get("id"), ro.get("price"), ro.get("tick"),
                                    len(d.get("messages") or [])]).encode()).hexdigest()


def _cost(it):
    a = it.args
    if it.kind == "list_offer" and a["side"] == "bid":
        return a["price"], a["ref"]
    if it.kind == "accept" and a["side"] == "buy":
        return a["price"] + val.fee(a["price"]), a["ref"]
    if it.kind == "open_thread" and a["side"] == "buy":
        return a["limit"], a["ref"]
    return 0, None


class FakeGuards:
    SOURCES = MappingProxyType({
        "cancel": frozenset({"clock", "me/offers"}), "close_thread": frozenset({"clock", "me/threads"}),
        "list_offer": frozenset({"clock", "me", "me/offers", "me/threads", "board"}),
        "accept": frozenset({"clock", "me", "me/offers", "me/threads", "board"}),
        "accept:dealer": frozenset({"clock", "me", "me/offers", "me/threads", "threads"}),
        "open_thread": frozenset({"clock", "me", "me/offers", "me/threads", "threads"}),
        "say": frozenset({"clock", "me", "me/offers", "me/threads", "threads"}),
        "open_pack": frozenset({"clock", "me", "me/threads"}),
        "duel_say": frozenset({"clock", "duels"}), "duel_accept": frozenset({"clock", "duels"})})
    Counters = Counters
    calls: list = []

    @staticmethod
    def build_book(world, journal, valuer, cfg, plan_cfg, frozen, baseline):
        held = {}
        for x in world.me.get("assets", []):
            held[x["ref"]] = held.get(x["ref"], 0) + 1
        cash = world.me["cash"]
        return Book(cash=cash, cash_free=cash - 10, held=held, listed={}, pending_out={}, pending_in={},
                    projected=dict(held), keep={}, listed_assets=frozenset(),
                    own_offer_ids=frozenset(o["id"] for o in world.my_offers), own_bids={}, bid_price={},
                    bid_band={}, paths={}, thread_limit={}, thread_prices={}, thread_ref={}, thread_by_dealer={},
                    dealer_block={}, dealer_deals_hour={}, packs=(), needs={}, frozen_closer={},
                    protect_sets=frozenset(), delivery_risk=False, recent_rastro={},
                    unknown_domains=frozenset(journal.unknown_domains()), valuation_ok=True)

    @staticmethod
    def apply(book, intent, outcome):
        if outcome.status not in ("sent", "would", "unknown"):
            return book
        cost, ref = _cost(intent)
        paths = dict(book.paths)
        if ref is not None:
            paths[ref] = paths.get(ref, 0) + 1
        return replace(book, cash_free=book.cash_free - cost, paths=paths)

    @staticmethod
    def check(intent, world, book, valuer, cfg, counters, *, fresh=None, now):
        FakeGuards.calls.append((intent.kind, fresh))
        cost, ref = _cost(intent)
        if cost > book.cash_free:
            return Verdict(False, "G16")
        if ref is not None and book.paths.get(ref, 0) > 0:
            return Verdict(False, "G15")
        if intent.kind == "accept" and intent.args["source"] == "team" and (fresh is None or fresh["offer"]["status"] != "open"
                                                                  or fresh["tick"] != world.tick):
            return Verdict(False, "G10")
        return Verdict(True, "ok")

    canonical_offer = staticmethod(lambda o: dict(o) if isinstance(o.get("give"), dict) else None)
    fingerprint = staticmethod(_fp)
    duel_fingerprint = staticmethod(_dfp)


class FakeTalk:
    @staticmethod
    def render(template, variant, price, days=None):
        return f"Te lo dejo en {price}" if days is None else f"Te lo dejo en {price} con {days} dias"

    @staticmethod
    def firewall(text, price, days):
        return Verdict(True, "ok")


class FakeValuer:
    def delta_add(self, counts, ref, packs=(), minted=None):
        return VALUES[ref]

    def delta_remove(self, counts, ref, packs=(), minted=None):
        return VALUES[ref]

    def closes_page(self, counts, ref):
        return False

    def self_check(self, me, server_values=None, tol=0.11):
        return True, 0.0, []


class FakeClock:
    def __init__(self, t=100.0):
        self.t = t

    def now(self):
        return self.t


class FakeTransport:
    """Records sends; checks that a matching one-use permit from agent.transport is active at send time."""
    mode = "live"

    def __init__(self, journal=None):
        self.sent, self.gets, self.journal = [], {}, journal
        self.reply = lambda m, p, b: tr.Response("ok", 200, None, {"id": 7000 + len(self.sent)})
        self.permit_seen = []

    def _call(self, method, path, body=None, query=None):
        assert method == "GET"
        v = self.gets.get(path)
        if v is None:
            raise tr.BazaarError("not_found", path, 404) if hasattr(tr, "BazaarError") else KeyError(path)
        return v() if callable(v) else v

    def send(self, method, path, body):
        p = tr._PERMIT.get()
        assert p is not None and not p.used, "no permit"
        assert (p.method, p.path, p.sha) == (method, path, tr._sha(body)), "permit mismatch"
        p.used = True
        if self.journal is not None:      # WAL: the intent row is on disk before the send
            rows = list(self.journal.rows({"intent"}))
            assert rows and rows[-1]["id"] == p.intent_id, "intent not journaled before send"
        self.sent.append((method, path, body))
        return self.reply(method, path, body)


# --------------------------------------------------------------------------------------------- builders

def offer(oid, ref="LAT-09", price=10, maker="m1", to=None, venue="rastro", status="open"):
    return {"id": oid, "maker": maker, "to": to, "venue": venue, "status": status, "thread": None,
            "give": {"cash": 0, "assets": [{"id": 900 + oid % 100, "kind": "card", "ref": ref}], "types": []},
            "want": {"cash": price, "assets": [], "types": []}, "expires_tick": TICK + 50,
            "created_tick": TICK - 5, "final": False}


ASSETS = [{"id": 101, "kind": "card", "ref": "MAL-04", "your_value": 3.0},
          {"id": 102, "kind": "card", "ref": "LAV-03", "your_value": 4.0},
          {"id": 103, "kind": "card", "ref": "RET-02", "your_value": 28.0}]
VENUES = ({"id": "rastro", "owner": None, "fee_bps": 500, "fee_per_card": 1, "status": "open"},
          {"id": "v01", "owner": "t06", "fee_bps": 50, "fee_per_card": 0, "status": "open"})
LEADERS = ("t13", "t06", "t01", "t02", "t03", "t04", "t05")


def world(tick=TICK, cash=200, board=(), my_offers=(), offers_to_us=(), clock=None, down=(), boards=None,
          leaderboard=LEADERS, threads=None, duels=(), deadline=1000.0, foreign_threads=()):
    clk = {"tick": tick, "paused": False, "doors": "open"}
    clk.update(clock or {})
    return World(tick=tick, t_hours=4.5, round=2, tick_seconds=30.0, tick_deadline=deadline, clock=clk,
                 limits=FRIDAY, reading="N", me={"cash": cash, "assets": list(ASSETS)}, my_offers=tuple(my_offers),
                 offers_to_us=tuple(offers_to_us), board=tuple(board), own_pseudonym="mself",
                 threads=threads or {}, foreign_threads=tuple(foreign_threads), duels=tuple(duels), catalog={},
                 schedule={}, released_sets=frozenset(), feed_new=(), server_values={}, down=frozenset(down),
                 boards=boards if boards is not None else {"rastro": tuple(board)}, venues=VENUES,
                 leaderboard=tuple(leaderboard))


def bid(ref, price, tactic="rastro", expires=60):
    pred = val.predict_team(VALUES[ref], price, "buy", False, 50.0)
    return make_intent("list_offer", tactic, {"side": "bid", "ref": ref, "asset_id": None, "price": price,
                                              "expires_ticks": expires, "closer": False, "want_ref": None},
                       "test", "bid", pred)


def sell(asset_id, ref, price, tactic="rastro"):
    pred = val.predict_team(VALUES[ref], price, "sell", False, 50.0)
    return make_intent("list_offer", tactic, {"side": "sell", "ref": ref, "asset_id": asset_id, "price": price,
                                              "expires_ticks": 20, "closer": False, "want_ref": None},
                       "test", "sell", pred)


def accept_buy(o, venue="rastro", tactic="rastro", fee_bps=500, per_card=1, pred=None):
    ref, price = o["give"]["assets"][0]["ref"], o["want"]["cash"]
    pred = pred or val.predict_team(VALUES[ref], price, "buy", True, 50.0, fee_bps=fee_bps, per_card=per_card)
    return make_intent("accept", tactic, {"offer_id": o["id"], "source": "team", "ref": ref, "side": "buy",
                                          "price": price, "thread_id": None, "give_asset": None,
                                          "fingerprint": _fp(o), "resupply": False, "venue": venue},
                       "test", "buy", pred)


def cancel(oid, tactic="hygiene"):
    return make_intent("cancel", tactic, {"offer_id": oid, "ref": None}, "t", "cancel", val.predict_none())


def open_thread(ref, limit, tactic="dealers"):
    return make_intent("open_thread", tactic, {"dealer": "abuela", "side": "buy", "ref": ref, "asset_ids": (),
                                               "limit": limit}, "t", "thread", val.predict_none())


# --------------------------------------------------------------------------------------------- base

class GateCase(unittest.TestCase):
    mode = "live"

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="t18-gate-")
        self.paths = Paths.at(self.root)
        self._lock = writer_lock(self.paths)
        self._lock.__enter__()
        self.journal = Journal(self.paths.journal, mode="test")
        self.transport = FakeTransport(self.journal)
        self.clock = FakeClock()
        self.armed = frozenset({"hygiene", "rastro", "dealers", "closer", "duels"})
        self.paused = set()
        self.gate = gate_mod.Gate(self.transport, self.journal, FakeValuer(), SimpleNamespace(NEG_CAP=50.0),
                                  {"baseline_bands": {}}, self.paths, mode=self.mode, armed=lambda: self.armed,
                                  paused=lambda t: t in self.paused, clock=self.clock, guards=FakeGuards,
                                  talk=FakeTalk, valuation=val)

    def tearDown(self):
        self._lock.__exit__(None, None, None)
        shutil.rmtree(self.root, ignore_errors=True)

    def start(self, w):
        self.gate.begin_tick(w)
        self.gate.reconcile(w)
        return w


# --------------------------------------------------------------------------------------------- tests

class TestDryAndArming(GateCase):
    mode = "dry"

    def test_dry_never_sends(self):
        rng = random.Random(7)
        for t in range(TICK, TICK + 20):
            w = self.start(world(tick=t, cash=10_000))
            for _ in range(10):
                it = bid(rng.choice(list(VALUES)), rng.randint(1, 30)) if rng.random() < .5 else cancel(rng.randint(1, 9))
                out = self.gate.execute(it, w)
                self.assertIn(out.status, ("would", "refused"))
        self.assertEqual(self.transport.sent, [])
        self.assertGreater(sum(1 for _ in self.journal.rows({"would"})), 0)
        self.assertEqual(list(self.journal.rows({"intent"})), [])


class TestLive(GateCase):
    def test_sent_with_wal_and_exact_request(self):
        w = self.start(world())
        out = self.gate.execute(bid("LAT-09", 20, expires=60), w)
        self.assertEqual(out.status, "sent", out)
        self.assertEqual(self.transport.sent, [("POST", "/api/offers", {
            "give": {"cash": 20}, "want": {"cards": ["LAT-09"]}, "venue": "rastro", "expires_in_ticks": 120})])
        kinds = [r["kind"] for r in self.journal.rows() if r["kind"] in ("intent", "result")]
        self.assertEqual(kinds, ["intent", "result"])

    def test_swap_listing_and_sell_body(self):
        w = self.start(world())
        pred = val.predict_swap(VALUES["LAT-10"], VALUES["MAL-04"], False, 50.0)
        it = make_intent("list_offer", "rastro", {"side": "swap", "ref": "MAL-04", "asset_id": 101, "price": 0,
                                                  "expires_ticks": 10, "closer": False, "want_ref": "LAT-10"},
                         "t", "swap", pred)
        self.assertEqual(self.gate.execute(it, w).status, "sent")
        self.assertEqual(self.transport.sent[-1][2]["give"], {"assets": [101]})
        self.assertEqual(self.transport.sent[-1][2]["want"], {"cards": ["LAT-10"]})
        # an asset that is not ours is never handed over
        it2 = make_intent("list_offer", "rastro", {"side": "sell", "ref": "MAL-04", "asset_id": 555, "price": 9,
                                                   "expires_ticks": 10, "closer": False, "want_ref": None},
                          "t", "sell", val.predict_team(3.0, 9, "sell", False, 50.0))
        self.assertEqual(self.gate.execute(it2, w).code, "G13.not_ours")

    def test_unarmed_and_paused_are_would(self):
        w = self.start(world())
        self.armed = frozenset()
        self.assertEqual(self.gate.execute(bid("LAT-09", 5), w).status, "would")
        self.armed = frozenset({"rastro"})
        self.paused.add("rastro")
        self.assertEqual(self.gate.execute(bid("LAT-10", 5), w).status, "would")
        self.assertEqual(self.transport.sent, [])

    def test_stop_file_refuses(self):
        w = self.start(world())
        open(os.path.join(self.root, "STOP.txt"), "w").close()
        out = self.gate.execute(cancel(5), w)
        self.assertEqual((out.status, out.code), ("refused", "G01.stop"))
        self.assertEqual(self.transport.sent, [])

    def test_not_reconciled_refuses(self):
        w = world()
        self.gate.begin_tick(w)
        self.assertEqual(self.gate.execute(cancel(5), w).code, "G05.not_reconciled")

    def test_doors_closed_only_cancel(self):
        o = offer(5001)
        w = self.start(world(board=[o], clock={"doors": "closed"}))
        self.assertEqual(self.gate.execute(accept_buy(o), w).code, "G03.closed")
        self.assertEqual(self.gate.execute(cancel(77), w).status, "sent")
        self.assertEqual(self.transport.sent, [("DELETE", "/api/offers/77", None)])

    def test_late_decision_is_deferred_except_cancel(self):
        w = self.start(world(deadline=50.0))
        out = self.gate.execute(bid("LAT-09", 5), w)
        self.assertEqual((out.status, out.code), ("deferred", "G03.late"))
        self.assertEqual(self.gate.execute(cancel(3), w).status, "sent")
        self.assertEqual(len(self.transport.sent), 1)

    def test_prediction_mismatch_trips(self):
        w = self.start(world())
        it = make_intent("list_offer", "rastro", {"side": "bid", "ref": "LAT-09", "asset_id": None, "price": 5,
                                                  "expires_ticks": 9, "closer": False, "want_ref": None},
                         "t", "bid", val.predict_team(99.0, 5, "buy", False, 50.0))
        self.assertEqual(self.gate.execute(it, w).code, "G07.trip")
        self.assertEqual(self.transport.sent, [])

    def test_source_down_refuses(self):
        w = self.start(world(down={"board"}))
        self.assertEqual(self.gate.execute(bid("LAT-09", 5), w).code, "G06.source:board")


class TestIdempotencyAndUnknown(GateCase):
    def test_same_intent_twice_is_one_send(self):
        w = self.start(world())
        it = bid("LAT-09", 5)
        self.assertEqual(self.gate.execute(it, w).status, "sent")
        self.assertTrue(self.gate.execute(it, w).code.startswith("G05"))
        self.assertEqual(len(self.transport.sent), 1)

    def test_unknown_freezes_domain_and_never_resends(self):
        w = self.start(world())
        self.transport.reply = lambda m, p, b: tr.Response("unknown", 0, "exception", None)
        out = self.gate.execute(bid("LAT-09", 5), w)
        self.assertEqual(out.status, "unknown")
        self.assertIn("ref:LAT-09", self.journal.unknown_domains())
        self.transport.reply = lambda m, p, b: tr.Response("ok", 200, None, {"id": 1})
        self.assertEqual(self.gate.execute(bid("LAT-09", 6), w).code, "G05.unknown")
        w2 = self.start(world(tick=TICK + 1))                    # still frozen next tick (no evidence yet)
        self.assertEqual(self.gate.execute(bid("LAT-09", 6), w2).code, "G05.unknown")
        self.assertEqual(len(self.transport.sent), 1)

    def test_duel_accept_unknown_resolves(self):
        # audit Sat: an unknown duel_accept must reconcile (duel ended / still live), never pause duels for good
        self.start(world())
        ev = self.gate._evidence
        a = {"duel_id": 5, "fingerprint": "x"}
        self.assertEqual(ev("duel_accept", a, world(duels=[{"duel": 5, "status": "deal"}]), TICK, 1)[0], True)
        self.assertEqual(ev("duel_accept", a, world(duels=[]), TICK, 1)[0], True)
        self.assertIsNone(ev("duel_accept", a, world(duels=[{"duel": 5, "status": "live"}]), TICK, 1)[0])
        self.assertEqual(ev("duel_accept", a, world(duels=[{"duel": 5, "status": "live"}]), TICK, 2)[0], False)

    def test_send_exception_is_unknown(self):
        w = self.start(world())

        def boom(m, p, b):
            raise ConnectionResetError("reset")
        self.transport.reply = boom
        self.assertEqual(self.gate.execute(bid("LAT-09", 5), w).status, "unknown")

    def test_reconcile_releases_landed_listing(self):
        w = self.start(world())
        self.transport.reply = lambda m, p, b: tr.Response("unknown", 0, "exception", None)
        self.gate.execute(bid("LAT-09", 5), w)
        mine = {"id": 8001, "maker": TEAM, "to": None, "venue": "rastro", "status": "open",
                "give": {"cash": 5, "assets": [], "types": []}, "want": {"cash": 0, "assets": [], "types": ["card:LAT-09"]},
                "expires_tick": TICK + 60, "created_tick": TICK}
        w2 = world(tick=TICK + 1, my_offers=[mine])
        self.gate.begin_tick(w2)
        self.assertIsNone(self.gate.stopped())                     # explained by our own intent: no STOP
        res = self.gate.reconcile(w2)
        self.assertTrue(any(r.get("landed") is True for r in res), res)
        self.assertNotIn("ref:LAT-09", self.journal.unknown_domains())

    def test_journal_failure_stops_before_send(self):
        w = self.start(world())
        real = self.journal.write

        def bad(kind, **f):
            if kind == "intent":
                raise OSError("disk full")
            return real(kind, **f)
        self.journal.write = bad
        with self.assertRaises(OSError):
            self.gate.execute(bid("LAT-09", 5), w)
        self.assertEqual(self.transport.sent, [])
        self.assertTrue(self.gate.stopped())

    def test_stop_active_from_transport_reraises(self):
        w = self.start(world())

        def stop(m, p, b):
            raise tr.StopActive("STOP")
        self.transport.reply = stop
        with self.assertRaises(tr.StopActive):
            self.gate.execute(bid("LAT-09", 5), w)


class TestInFlightThreadOffers(GateCase):
    def test_superseded_thread_offer_not_booked(self):
        # live Sat: our counter in a dealer thread cancels our previous offer; it must not leave cash_free
        def own(oid, cash, thread):
            return {"id": oid, "maker": TEAM, "to": "picaros", "venue": None, "thread": thread, "status": "open",
                    "give": {"cash": cash, "assets": [], "types": []},
                    "want": {"cash": 0, "assets": [], "types": ["card:SAL-11"]},
                    "expires_tick": TICK + 4, "created_tick": TICK}
        w1 = self.start(world(my_offers=[own(1, 130, 77)]))
        b1 = self.gate._in_flight(w1, FakeGuards.build_book(w1, self.journal, None, None, None, None, None))
        w2 = world(tick=TICK + 1, my_offers=[own(2, 133, 77)])
        b2 = self.gate._in_flight(w2, FakeGuards.build_book(w2, self.journal, None, None, None, None, None))
        self.assertEqual(b2.cash_free, 200 - 10)                 # 130 not booked: superseded, not accepted
        w3 = world(tick=TICK + 2, my_offers=[])
        b3 = self.gate._in_flight(w3, FakeGuards.build_book(w3, self.journal, None, None, None, None, None))
        self.assertEqual(b3.cash_free, 200 - 10 - 133)           # the last offer vanished: may be accepted


    def test_cooloff_without_until_blocks_to_next_game_hour_at_live_tick_rate(self):
        # t_hours 4.5, 30 s ticks = 120 per game hour: the rest of the hour is 60 ticks (was 30 with the constant 60)
        w = self.start(world())
        self.transport.reply = lambda m, p, b: tr.Response("refused", 409, "cooloff", {"error": "cooloff"})
        out = self.gate.execute(open_thread("RET-01", 20), w)
        self.assertEqual((out.status, out.code), ("refused", "cooloff"))
        self.assertEqual(self.gate.book.dealer_block.get("abuela"), TICK + 60)


class TestBudgetsAndBook(GateCase):
    def test_100_accepts_one_send(self):
        offers = [offer(5000 + i, ref="LAT-09", price=5) for i in range(100)]
        w = self.start(world(board=offers, cash=10_000))
        self.transport.gets["/api/venues/rastro/offers"] = {"offers": offers}
        self.transport.gets["/api/clock"] = {"tick": TICK}
        outs = [self.gate.execute(accept_buy(o), w) for o in offers]
        self.assertEqual(sum(o.status == "sent" for o in outs), 1)
        self.assertEqual(len(self.transport.sent), 1)
        self.assertTrue(all(o.code == "G04.accepts" for o in outs[1:]))

    def test_offers_to_us_do_not_block_listings(self):
        to_us = [offer(6000 + i, maker=f"t{i:02d}", to=TEAM) for i in range(30)]
        w = self.start(world(offers_to_us=to_us))
        self.assertEqual(self.gate.execute(sell(101, "MAL-04", 9), w).status, "sent")

    def test_listings_budget(self):
        w = self.start(world(cash=10_000))
        outs = [self.gate.execute(bid(r, 2), w) for r in ("LAT-09", "LAT-10", "RET-01", "RET-02", "SAL-01",
                                                         "CHA-01", "LAV-03")]
        self.assertEqual(sum(o.status == "sent" for o in outs), 6)
        self.assertEqual(outs[-1].code, "G04.listings")

    def test_two_bids_over_cash_second_refused(self):
        w = self.start(world(cash=100))                           # cash_free 90
        self.assertEqual(self.gate.execute(bid("LAT-09", 30), w).status, "sent")
        out = self.gate.execute(bid("RET-01", 25), w)
        self.assertEqual(out.status, "sent")
        out = self.gate.execute(bid("SAL-01", 24), w)             # 30 + 25 + 24 = 79 <= 90 ok
        self.assertEqual(out.status, "sent")
        out = self.gate.execute(bid("LAT-10", 20), w)             # 99 > 90
        self.assertEqual(out.status, "refused")
        self.assertTrue(out.code.startswith("G16"), out.code)

    def test_bid_then_thread_same_ref_g15(self):
        w = self.start(world(cash=1000))
        self.assertEqual(self.gate.execute(bid("LAT-09", 10), w).status, "sent")
        out = self.gate.execute(open_thread("LAT-09", 20), w)
        self.assertTrue(out.code.startswith("G15"), out.code)

    def test_running_book_50_random_pairs(self):
        rng = random.Random(18)
        refs = list(VALUES)
        for t in range(TICK, TICK + 50):
            w = self.start(world(tick=t, cash=rng.randint(20, 120)))
            pair = [bid(rng.choice(refs), rng.randint(1, 60)) if rng.random() < .5
                    else open_thread(rng.choice(refs), rng.randint(1, 60)) for _ in range(2)]
            for it in pair:
                self.gate.execute(it, w)
                b = self.gate.book
                self.assertGreaterEqual(b.cash_free, 0)
                self.assertTrue(all(v <= 1 for v in b.paths.values()), b.paths)


class TestFreshReread(GateCase):
    def setUp(self):
        super().setUp()
        self.o = offer(5001, price=10)
        self.w = self.start(world(board=[self.o]))
        self.transport.gets["/api/clock"] = {"tick": TICK}

    def test_ok_path(self):
        self.transport.gets["/api/venues/rastro/offers"] = {"offers": [self.o]}
        out = self.gate.execute(accept_buy(self.o), self.w)
        self.assertEqual(out.status, "sent", out)
        self.assertEqual(self.transport.sent, [("POST", "/api/offers/5001/accept", {})])
        self.assertEqual(sum(1 for _ in self.journal.rows({"accepted_unsettled"})), 1)

    def _odd(self, payload, code="G10.shape"):
        self.transport.gets["/api/venues/rastro/offers"] = payload
        out = self.gate.execute(accept_buy(self.o), self.w)
        self.assertEqual((out.status, out.code), ("refused", code))
        self.assertIsNone(self.gate.stopped())
        self.assertFalse(os.path.exists(os.path.join(self.root, "STOP")))
        self.assertEqual(self.transport.sent, [])
        return out

    def test_type_swap(self):
        self._odd({"offers": {"5001": self.o}})

    def test_missing_field(self):
        broken = dict(self.o)
        del broken["give"]
        self._odd({"offers": [broken]})

    def test_garbage_and_blocked_for_tick(self):
        self._odd("<html>")
        self.transport.gets["/api/venues/rastro/offers"] = {"offers": [self.o]}
        out = self.gate.execute(accept_buy(self.o, tactic="manual"), self.w)    # same domains, same tick
        self.assertEqual(out.code, "G10.blocked")
        w2 = self.start(world(tick=TICK + 1, board=[self.o]))
        self.transport.gets["/api/clock"] = {"tick": TICK + 1}
        self.assertEqual(self.gate.execute(accept_buy(self.o), w2).status, "sent")

    def test_changed_offer_fingerprint(self):
        moved = dict(self.o, want={"cash": 11, "assets": [], "types": []})
        self._odd({"offers": [moved]}, "G10.fingerprint")

    def test_stale_clock(self):
        self.transport.gets["/api/venues/rastro/offers"] = {"offers": [self.o]}
        self.transport.gets["/api/clock"] = {"tick": TICK + 1}
        self.assertEqual(self.gate.execute(accept_buy(self.o), self.w).code, "G10.stale")
        self.transport.gets["/api/clock"] = {"tick": str(TICK)}
        self.assertEqual(self.gate.execute(accept_buy(self.o, tactic="manual"), self.w).code, "G10.blocked")

    def test_read_error_refuses(self):
        def err():
            raise ValueError("bad json")
        self.transport.gets["/api/venues/rastro/offers"] = err
        out = self.gate.execute(accept_buy(self.o), self.w)
        self.assertEqual(out.status, "refused")
        self.assertIsNone(self.gate.stopped())

    def test_offer_to_us_reads_me_offers(self):
        o = offer(5002, to=TEAM, maker="t07")
        w = self.start(world(offers_to_us=[o]))
        self.transport.gets["/api/me/offers"] = {"offers": [o]}
        self.assertEqual(self.gate.execute(accept_buy(o), w).status, "sent")


class TestRivalVenue(GateCase):
    def setUp(self):
        super().setUp()
        self.o = offer(7001, ref="LAT-09", price=10, venue="v01")
        self.transport.gets["/api/venues/v01/offers"] = {"offers": [self.o]}
        self.transport.gets["/api/clock"] = {"tick": TICK}

    def _acc(self):
        return accept_buy(self.o, venue="v01", fee_bps=50, per_card=0)

    def test_owner_in_top_refused(self):
        w = self.start(world(boards={"rastro": (), "v01": (self.o,)}))
        self.assertEqual(self.gate.execute(self._acc(), w).code, "D2.top")

    def test_unknown_leaderboard_refused(self):
        w = self.start(world(boards={"v01": (self.o,)}, leaderboard=()))
        self.assertEqual(self.gate.execute(self._acc(), w).code, "D2.leaderboard_unknown")

    def test_ok_outside_top_with_gain(self):
        w = self.start(world(boards={"v01": (self.o,)}, leaderboard=("t13", "t01", "t02", "t03", "t04", "t06")))
        out = self.gate.execute(self._acc(), w)
        self.assertEqual(out.status, "sent", out)

    def test_small_gain_refused(self):
        o = offer(7002, ref="LAT-09", price=35, venue="v01")         # 40 - 35 - 1 = 4 < 10
        self.transport.gets["/api/venues/v01/offers"] = {"offers": [o]}
        w = self.start(world(boards={"v01": (o,)}, leaderboard=("t13", "t01", "t02", "t03", "t04", "t06"),
                             cash=1000))
        self.assertEqual(self.gate.execute(accept_buy(o, venue="v01", fee_bps=50, per_card=0), w).code, "D2.gain")


class TestForeignWriter(GateCase):
    def test_quiet_ticks_no_stop_and_rogue_offer_stops(self):
        inherited = offer(2463, maker=TEAM)
        for t in range(TICK, TICK + 5):
            self.start(world(tick=t, my_offers=[inherited], offers_to_us=[offer(9000 + t, maker="t03", to=TEAM)],
                             foreign_threads=(77,)))
            self.assertIsNone(self.gate.stopped())
        self.assertTrue(self.paths.baseline.exists())
        rogue = offer(9999, maker=TEAM, ref="SAL-01", price=3)
        msgs = self.gate.begin_tick(world(tick=TICK + 6, my_offers=[inherited, rogue]))
        self.assertTrue(any("foreign_writer:offer:9999" in m for m in msgs), msgs)
        self.assertTrue(self.gate.stopped())

    def test_rogue_duel_message_stops(self):
        d = {"duel": 149, "role": "buyer", "messages": [{"tick": 156, "from": "you", "price": 61, "days": None}]}
        self.start(world(duels=[d]))
        self.assertIsNone(self.gate.stopped())
        d2 = dict(d, messages=d["messages"] + [{"tick": TICK + 1, "from": "you", "price": 70, "days": None}])
        self.gate.begin_tick(world(tick=TICK + 1, duels=[d2]))
        self.assertTrue(self.gate.stopped())


try:
    from agent import guards as real_guards
except Exception:  # noqa: BLE001
    real_guards = None


@unittest.skipIf(real_guards is None, "agent.guards not built")
class TestWithRealGuards(GateCase):
    """Smoke: the Gate against the real M4a module (shapes of SOURCES, Counters, fresh, Book)."""

    def setUp(self):
        super().setUp()
        self.gate._guards = real_guards
        self.gate.cfg = real_guards.Cfg()

    def test_bid_then_duplicate_and_dry_counts(self):
        w = self.start(world(cash=200))
        out = self.gate.execute(bid("LAT-09", 20, expires=60), w)
        self.assertEqual(out.status, "sent", out)
        out2 = self.gate.execute(bid("LAT-09", 21, expires=60), w)
        self.assertEqual(out2.status, "refused")
        self.assertEqual(len(self.transport.sent), 1)
        self.assertEqual(self.gate.counters.listings, 1)

    def test_team_accept_with_fresh(self):
        o = offer(5001, price=10)
        o["give"]["assets"][0].update({"serial": 1, "rarity": "common", "set": "LAT", "print_run": 300})
        w = self.start(world(board=[o], cash=200))
        self.transport.gets["/api/venues/rastro/offers"] = {"offers": [o]}
        self.transport.gets["/api/clock"] = {"tick": TICK}
        it = accept_buy(o)
        it = make_intent("accept", "rastro", dict(it.args, fingerprint=real_guards.fingerprint(o)), "t", "buy",
                         it.prediction)
        out = self.gate.execute(it, w)
        self.assertEqual(out.status, "sent", out)
        self.assertEqual(self.transport.sent, [("POST", "/api/offers/5001/accept", {})])


class TestWriterLock(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="t18-lock-")
        self.paths = Paths.at(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_second_holder_refused_and_pid_readable(self):
        with writer_lock(self.paths) as p:
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["pid"], os.getpid())
            with self.assertRaises(RuntimeError):
                with writer_lock(self.paths):
                    pass
        with writer_lock(self.paths):                            # released -> can be taken again
            pass

    def test_team_writer_wraps_fixed_lock(self):
        with team_writer("t18"):
            with self.assertRaises(RuntimeError):
                with team_writer("other"):
                    pass
        with self.assertRaises(ValueError):
            with team_writer(""):
                pass


class TestRequestFor(unittest.TestCase):
    def test_shapes(self):
        R = gate_mod.REQUEST_FOR
        self.assertEqual(R["accept"]({"offer_id": 5, "give_asset": 9}, None), ("POST", "/api/offers/5/accept",
                                                                              {"assets": [9]}))
        self.assertEqual(R["cancel"]({"offer_id": 5}, None), ("DELETE", "/api/offers/5", None))
        self.assertEqual(R["duel_say"]({"duel_id": 3, "price": 40, "days": 2}, "x")[2],
                         {"text": "x", "price": 40, "days": 2, "offer": {"price": 40, "days": 2}})
        self.assertEqual(R["open_thread"]({"dealer": "chato", "side": "sell", "ref": "X", "asset_ids": (4,)}, None)[2],
                         {"with": "chato", "topic": {"sell": {"assets": [4]}}})
        with self.assertRaises(ValueError):
            R["say"]({"thread_id": 1, "price": 3}, None)


if __name__ == "__main__":
    unittest.main()
