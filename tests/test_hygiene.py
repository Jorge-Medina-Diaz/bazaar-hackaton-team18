"""M9 hygiene tests: J0, J1, G19 watch, INV-06, INV-09, INV-23 (docs/harness-spec.md §4 Vigilancia, §10)."""
from __future__ import annotations

import collections
import copy
import json
import unittest
from dataclasses import replace
from types import MappingProxyType

from tests import HARVEST
from agent.contracts import FRIDAY, Book, World
from agent.tactics import hygiene

PROTECT = ("SAL", "RET", "CHA", "LAT")
PLAN = {
    "startup_cancels": [2463, 1652],
    "baseline_bands": {"2503": 0.0, "2504": 0.0},
    "protect_sets": list(PROTECT),
    "grant_lookahead_ticks": 3,
    "day_end_hours": {"sat": 17.9167, "sun": 23.9},
}


def _load(name):
    with open(HARVEST / name, encoding="utf-8") as f:
        return json.load(f)


class Cfg:                                     # test double of guards.Cfg (M4a); only the knobs hygiene reads
    DEALER_MARGIN = 1.0
    NEG_CAP = 50.0
    CLOSER_ACCEPT_MIN = 20.0


class FakeValuer:                              # test double of valuation.Valuer (M3)
    def __init__(self, values=None, fail=False):
        self.values = values or {}
        self.fail = fail

    def delta_add(self, counts, ref, packs=(), minted=None):
        if self.fail:
            raise RuntimeError("boom")
        k = counts.get(ref, 0)
        return self.values.get(ref, 10.0) * (1.0 if k == 0 else 0.25)

    def delta_remove(self, counts, ref, packs=(), minted=None):
        return self.values.get(ref, 10.0)

    def closes_page(self, counts, ref):
        s = ref.split("-")[0]
        have = {r for r, c in counts.items() if c > 0 and r.startswith(s + "-")} | {ref}
        return len(have) == 10


def _offer(oid, *, give_ref=None, asset_id=None, give_cash=0, want_cash=0, want_type=None, exp=200,
           status="open"):
    assets = [{"id": asset_id, "kind": "card", "ref": give_ref}] if give_ref else []
    types = [f"card:{want_type}"] if want_type else []
    return {"id": oid, "maker": "t18", "to": None, "venue": "rastro", "status": status,
            "give": {"cash": give_cash, "assets": assets, "types": []},
            "want": {"cash": want_cash, "assets": [], "types": types},
            "expires_tick": exp, "created_tick": 150}


def make_world(me=None, offers=None, threads=None, *, t_hours=2.65, today="fri", schedule=None, down=(),
               tick=159, tick_seconds=60.0, foreign=()):
    me = me if me is not None else _load("me.json")
    offers = offers if offers is not None else _load("me_offers.json")["offers"]
    clock = dict(_load("clock.json"))
    clock["today"] = today
    clock["t_hours"] = t_hours
    return World(tick=tick, t_hours=t_hours, round=1, tick_seconds=tick_seconds, tick_deadline=1e12,
                 clock=clock, limits=FRIDAY, reading="N", me=me, my_offers=tuple(offers), offers_to_us=(),
                 board=(), own_pseudonym=None, threads=MappingProxyType(dict(threads or {})),
                 foreign_threads=tuple(foreign), duels=(), catalog={},
                 schedule=schedule if schedule is not None else _load("schedule.json"),
                 released_sets=frozenset(), feed_new=(), server_values=MappingProxyType({}),
                 down=frozenset(down))


def make_book(world, *, cash_free=None, valuation_ok=True, delivery_risk=False, bid_band=None,
              thread_prices=None, frozen_closer=None):
    """Mimics guards.build_book (M4a) on the fields hygiene reads."""
    held = collections.Counter(a["ref"] for a in world.me["assets"] if a.get("kind") == "card")
    packs = tuple(a.get("type", "sobre") for a in world.me["assets"] if a.get("kind") == "pack")   # TYPES (M4a)
    listed, listed_assets, own_ids, own_bids, bid_price, reserved = collections.Counter(), set(), set(), {}, {}, 0
    for o in world.my_offers:
        if o["status"] not in ("open", "queued"):
            continue
        own_ids.add(o["id"])
        for a in o["give"]["assets"]:
            listed[a["ref"]] += 1
            listed_assets.add(a["id"])
        if o["give"]["cash"] > 0:
            ref = o["want"]["types"][0][5:]
            own_bids[ref] = o["id"]
            bid_price[o["id"]] = o["give"]["cash"]
            reserved += o["give"]["cash"]
    projected = collections.Counter(held)
    for ref in own_bids:
        projected[ref] += 1
    keep = {r: 1 for r in held if r.split("-")[0] in PROTECT}
    cash = world.me["cash"]
    band = {2503: 0.0, 2504: 0.0}
    band.update(bid_band or {})
    return Book(cash=cash, cash_free=cash - reserved if cash_free is None else cash_free, held=dict(held),
                listed=dict(listed), pending_out={}, pending_in={}, projected=dict(projected), keep=keep,
                listed_assets=frozenset(listed_assets), own_offer_ids=frozenset(own_ids), own_bids=own_bids,
                bid_price=bid_price, bid_band=band, paths={}, thread_limit={}, thread_prices=thread_prices or {},
                thread_ref={}, thread_by_dealer={}, dealer_block={}, dealer_deals_hour={}, packs=packs, needs={},
                frozen_closer=frozen_closer or {}, protect_sets=frozenset(PROTECT), delivery_risk=delivery_risk,
                recent_rastro={}, unknown_domains=frozenset(), valuation_ok=valuation_ok)


VALUES = {"LAT-09": 63.0, "LAT-10": 63.0, "RET-09": 91.0, "RET-03": 99.1, "LAT-06": 30.0}


def ids(intents, kind="cancel", key="offer_id"):
    return {it.args[key] for it in intents if it.kind == kind}


def buy_thread(dealer="chato", ref="RET-09", status="open", price=None):
    msgs = []
    if price is not None:
        msgs.append({"id": 1, "tick": 158, "sender": "t18",
                     "offer": {"give": {"cash": price, "assets": [], "types": []},
                               "want": {"cash": 0, "assets": [], "types": [f"card:{ref}"]}}})
    return {"id": 0, "with": dealer, "team": "t18", "topic": {"buy": {"card": ref}}, "status": status,
            "messages": msgs}


def current_offers():
    """The live state after the 01:30 cancels of the four unsafe LAT listings."""
    offers = copy.deepcopy(_load("me_offers.json")["offers"])
    for o in offers:
        if o["id"] in (2463, 2592, 1652, 2591):
            o["status"] = "cancelled"
    return offers


def with_pack(me):
    me = copy.deepcopy(me)
    me["assets"].append({"id": 900, "kind": "pack", "type": "sobre_barrio"})
    return me


class TestJ0AndProtection(unittest.TestCase):
    def test_harvest_watch_cancels_exactly_2463_and_1652(self):
        w = make_world()
        b = make_book(w)
        out = hygiene.watch(w, b, FakeValuer(VALUES), Cfg(), PLAN)
        self.assertEqual(ids(out), {2463, 1652})
        self.assertEqual(len(out), 2)

    def test_harvest_startup_cancels_configured_ids(self):
        w = make_world()
        out = hygiene.startup(w, make_book(w), PLAN)
        self.assertEqual(ids(out), {2463, 1652})

    def test_current_state_startup_finds_nothing(self):
        w = make_world(offers=current_offers())
        b = make_book(w)
        plan = dict(PLAN, startup_cancels=[2463, 2592, 1652, 2591])
        self.assertEqual(hygiene.startup(w, b, plan), [])
        self.assertEqual(hygiene.watch(w, b, FakeValuer(VALUES), Cfg(), plan), [])
        self.assertEqual(hygiene.propose(w, b, FakeValuer(VALUES), Cfg(), plan, {}), [])

    def test_startup_catches_new_unprotected_listing_generically(self):
        offers = current_offers() + [_offer(3001, give_ref="SAL-10", asset_id=180, want_cash=300)]
        w = make_world(offers=offers)
        out = hygiene.startup(w, make_book(w), dict(PLAN, startup_cancels=[]))
        self.assertEqual(ids(out), {3001})

    def test_protected_duplicate_is_kept_and_earliest_expiry_goes_first(self):
        offers = current_offers() + [_offer(3002, give_ref="LAT-01", asset_id=379, want_cash=9, exp=300),
                                     _offer(3003, give_ref="LAT-01", asset_id=424, want_cash=9, exp=250)]
        w = make_world(offers=offers)
        out = hygiene.watch(w, make_book(w), FakeValuer(VALUES), Cfg(), PLAN)
        self.assertEqual(ids(out), {3003})          # one copy may go (2 held, keep 1); the earliest is cancelled

    def test_unprotected_swap_is_cancelled(self):
        offers = current_offers() + [{**_offer(3004, give_ref="SAL-03", asset_id=258, exp=300),
                                      "want": {"cash": 0, "assets": [], "types": ["card:RET-09"]}}]
        w = make_world(offers=offers)
        out = hygiene.startup(w, make_book(w), dict(PLAN, startup_cancels=[]))
        self.assertEqual(ids(out), {3004})

    def test_only_safe_kinds_and_tactic(self):
        w = make_world(me=with_pack(_load("me.json")), threads={7: buy_thread(price=95)})
        b = make_book(w, cash_free=-500, valuation_ok=False, delivery_risk=True)
        out = hygiene.propose(w, b, FakeValuer(VALUES), Cfg(), PLAN, {})
        self.assertTrue(out)
        for it in out:
            self.assertIn(it.kind, {"cancel", "close_thread", "open_pack"})
            self.assertEqual(it.tactic, "hygiene")
            self.assertEqual(it.prediction.model, "none")


class TestBids(unittest.TestCase):
    def _w(self, extra, **kw):
        return make_world(offers=current_offers() + extra, **kw)

    def test_inherited_bids_kept_with_band_zero(self):
        w = self._w([])
        self.assertEqual(hygiene.watch(w, make_book(w), FakeValuer(VALUES), Cfg(), PLAN), [])

    def test_inherited_bid_cancelled_when_below_its_band(self):
        w = self._w([])
        out = hygiene.watch(w, make_book(w), FakeValuer(dict(VALUES, **{"LAT-09": 60.0})), Cfg(), PLAN)
        self.assertEqual(ids(out), {2503})

    def test_normal_bid_out_of_band(self):
        w = self._w([_offer(3010, give_cash=90, want_type="RET-09"), _offer(3011, give_cash=80, want_type="LAT-06",
                                                                             exp=210)])
        b = make_book(w, bid_band={3010: 2.0, 3011: 2.0})
        out = hygiene.watch(w, b, FakeValuer(VALUES), Cfg(), PLAN)
        self.assertEqual(ids(out), {3010, 3011})       # 91-90=1 < 2 ; 30-80 < 2
        w2 = self._w([_offer(3010, give_cash=85, want_type="RET-09")])
        self.assertEqual(hygiene.watch(w2, make_book(w2, bid_band={3010: 2.0}), FakeValuer(VALUES), Cfg(), PLAN), [])

    def test_bids_without_cash_most_expensive_first(self):
        w = self._w([_offer(3020, give_cash=40, want_type="RET-09"), _offer(3021, give_cash=70, want_type="RET-03")])
        b = make_book(w, cash_free=-30, bid_band={3020: 2.0, 3021: 2.0})
        out = hygiene.watch(w, b, FakeValuer(VALUES), Cfg(), PLAN)
        self.assertEqual(ids(out), {3021})

    def test_valuation_down_skips_value_cancels_but_not_cash(self):
        w = self._w([_offer(3020, give_cash=90, want_type="RET-09")])
        b = make_book(w, valuation_ok=False, cash_free=-10, bid_band={3020: 2.0})
        out = hygiene.watch(w, b, FakeValuer(VALUES), Cfg(), PLAN)
        self.assertEqual(ids(out), {3020})              # cash rule still applies (most expensive bid)

    def test_closer_bid_withdrawn_with_delivery_risk_and_back_after(self):
        """Acceptance: the closer bid is withdrawn under delivery risk and re-posted afterwards."""
        closer = _offer(3030, give_cash=49, want_type="RET-03", exp=400)
        w = self._w([closer])
        state = {}
        b = make_book(w, delivery_risk=True, bid_band={3030: 20.0})
        out = hygiene.propose(w, b, FakeValuer(VALUES), Cfg(), PLAN, state)
        self.assertEqual(ids(out), {3030})
        self.assertEqual(state["retired_closers"]["RET-03"]["price"], 49)
        # Next tick: the bid is cancelled (gone from the board); the risk persists -> nothing more to do.
        w_gone = self._w([dict(closer, status="cancelled")])
        self.assertEqual(hygiene.propose(w_gone, make_book(w_gone, delivery_risk=True), FakeValuer(VALUES), Cfg(),
                                         PLAN, state), [])
        # Risk gone: the closer tactic re-posts at the remembered price; hygiene leaves the new bid alone.
        reposted = _offer(3031, give_cash=state["retired_closers"]["RET-03"]["price"], want_type="RET-03", exp=500)
        w2 = self._w([reposted])
        b2 = make_book(w2, delivery_risk=False, bid_band={3031: 20.0})
        self.assertEqual(hygiene.propose(w2, b2, FakeValuer(VALUES), Cfg(), PLAN, state), [])

    def test_closer_bid_withdrawn_when_pack_in_hand_even_if_book_says_no_risk(self):
        w = make_world(me=with_pack(_load("me.json")),
                       offers=current_offers() + [_offer(3032, give_cash=49, want_type="RET-03")])
        b = make_book(w, delivery_risk=False, bid_band={3032: 20.0})
        self.assertIn(3032, ids(hygiene.watch(w, b, FakeValuer(VALUES), Cfg(), PLAN)))

    def test_closer_bid_out_of_closer_band(self):
        w = self._w([_offer(3033, give_cash=85, want_type="RET-03")])
        out = hygiene.watch(w, make_book(w, bid_band={3033: 20.0}), FakeValuer(VALUES), Cfg(), PLAN)
        self.assertEqual(ids(out), {3033})              # 99.1 - 85 = 14.1 < 20

    def test_closer_detected_by_closes_page(self):
        me = copy.deepcopy(_load("me.json"))
        me["assets"].append({"id": 901, "kind": "card", "ref": "LAT-10"})
        w = make_world(me=me, offers=current_offers())
        w = replace(w, my_offers=tuple(o for o in w.my_offers if o["id"] != 2504) +
                    (_offer(3034, give_cash=62, want_type="LAT-09"),))
        b = make_book(w, delivery_risk=True)              # 3034 is not inherited; LAT-09 now closes LAT
        out = hygiene.watch(w, b, FakeValuer(VALUES), Cfg(), PLAN)
        self.assertIn(3034, ids(out))
        self.assertNotIn(2503, ids(out))                   # inherited bid: band only (strategy: keep to t205)


class TestThreadsAndPacks(unittest.TestCase):
    def test_pack_opened_after_buy_threads_closed(self):
        """Acceptance: the pack opens after the threads are closed (J1, G40, INV-23)."""
        me = with_pack(_load("me.json"))
        w1 = make_world(me=me, offers=current_offers(), threads={7: buy_thread(price=80), 8: buy_thread("abuela",
                                                                                                          "RET-03")})
        out1 = hygiene.propose(w1, make_book(w1), FakeValuer(VALUES), Cfg(), PLAN, {})
        self.assertEqual(ids(out1, "close_thread", "thread_id"), {7, 8})
        self.assertEqual(ids(out1, "open_pack", "asset_id"), set())
        w2 = make_world(me=me, offers=current_offers(), threads={7: buy_thread(status="closed", price=80)})
        out2 = hygiene.propose(w2, make_book(w2), FakeValuer(VALUES), Cfg(), PLAN, {})
        self.assertEqual(ids(out2, "open_pack", "asset_id"), {900})
        self.assertEqual(ids(out2, "close_thread", "thread_id"), set())

    def test_book_pack_types_alone_close_buy_threads(self):
        w = make_world(offers=current_offers(), threads={7: buy_thread(price=10)})
        b = replace(make_book(w), packs=("sobre_barrio",))
        out = hygiene.propose(w, b, FakeValuer(VALUES), Cfg(), PLAN, {})
        self.assertEqual(ids(out, "close_thread", "thread_id"), {7})
        self.assertEqual(ids(out, "open_pack", "asset_id"), set())   # no pack asset id in me -> nothing to open

    def test_pack_with_sell_thread_only_opens(self):
        me = with_pack(_load("me.json"))
        sell = {"with": "chato", "topic": {"sell": {"assets": [261]}}, "status": "open", "messages": []}
        w = make_world(me=me, offers=current_offers(), threads={9: sell})
        out = hygiene.propose(w, make_book(w), FakeValuer(VALUES), Cfg(), PLAN, {})
        self.assertEqual(ids(out, "open_pack", "asset_id"), {900})
        self.assertEqual(ids(out, "close_thread", "thread_id"), set())

    def test_grant_soon_closes_buy_threads(self):
        sched = {"upcoming": [{"at_hours": 4.05, "action": "grant_all", "params": {"packs": ["sobre_barrio"],
                                                                                    "cash": 150}}]}
        th = {7: buy_thread(price=80)}
        near = make_world(offers=current_offers(), threads=th, schedule=sched, t_hours=4.04, today="sat",
                          tick_seconds=30.0)
        self.assertEqual(ids(hygiene.watch(near, make_book(near), FakeValuer(VALUES), Cfg(), PLAN), "close_thread",
                             "thread_id"), {7})
        far = make_world(offers=current_offers(), threads=th, schedule=sched, t_hours=4.0, today="sat",
                         tick_seconds=30.0)                   # 0.05 h = 6 ticks of 30 s > 3
        self.assertEqual(hygiene.watch(far, make_book(far), FakeValuer(VALUES), Cfg(), PLAN), [])
        cash_only = {"upcoming": [{"at_hours": 4.05, "action": "grant_all", "params": {"cash": 150}}]}
        w = make_world(offers=current_offers(), threads=th, schedule=cash_only, t_hours=4.04, today="sat",
                       tick_seconds=30.0)
        self.assertEqual(hygiene.watch(w, make_book(w), FakeValuer(VALUES), Cfg(), PLAN), [])

    def test_schedule_down_fails_closed(self):
        w = make_world(offers=current_offers(), threads={7: buy_thread(price=80)}, down=("schedule",))
        self.assertEqual(ids(hygiene.watch(w, make_book(w), FakeValuer(VALUES), Cfg(), PLAN), "close_thread",
                             "thread_id"), {7})

    def test_standing_price_out_of_value(self):
        hi = make_world(offers=current_offers(), threads={7: buy_thread(price=91)})
        self.assertEqual(ids(hygiene.watch(hi, make_book(hi), FakeValuer(VALUES), Cfg(), PLAN), "close_thread",
                             "thread_id"), {7})               # 91 > 91 - 1
        ok = make_world(offers=current_offers(), threads={7: buy_thread(price=90)})
        self.assertEqual(hygiene.watch(ok, make_book(ok), FakeValuer(VALUES), Cfg(), PLAN), [])
        via_book = make_world(offers=current_offers(), threads={7: buy_thread()})
        b = make_book(via_book, thread_prices={7: (70, 95)})
        self.assertEqual(ids(hygiene.watch(via_book, b, FakeValuer(VALUES), Cfg(), PLAN), "close_thread",
                             "thread_id"), {7})

    def test_standing_price_without_valuation_closes(self):
        w = make_world(offers=current_offers(), threads={7: buy_thread(price=50)})
        for b, v in ((make_book(w, valuation_ok=False), FakeValuer(VALUES)), (make_book(w), FakeValuer(fail=True))):
            self.assertEqual(ids(hygiene.watch(w, b, v, Cfg(), PLAN), "close_thread", "thread_id"), {7})

    def test_pack_buy_thread_always_closed(self):
        t = {"with": "abuela", "topic": {"buy": {"pack": "sobre_barrio"}}, "status": "open", "messages": []}
        w = make_world(offers=current_offers(), threads={5: t})
        self.assertEqual(ids(hygiene.watch(w, make_book(w), FakeValuer(VALUES), Cfg(), PLAN), "close_thread",
                             "thread_id"), {5})

    def test_day_end_closes_all_dealer_threads(self):
        sell = {"with": "chato", "topic": {"sell": {"assets": [261]}}, "status": "open", "messages": []}
        th = {7: buy_thread(price=60), 9: sell}
        sched = {"upcoming": []}
        late = make_world(offers=current_offers(), threads=th, t_hours=17.92, today="sat", schedule=sched)
        self.assertEqual(ids(hygiene.watch(late, make_book(late), FakeValuer(VALUES), Cfg(), PLAN), "close_thread",
                             "thread_id"), {7, 9})
        early = make_world(offers=current_offers(), threads=th, t_hours=17.9, today="sat", schedule=sched)
        self.assertEqual(hygiene.watch(early, make_book(early), FakeValuer(VALUES), Cfg(), PLAN), [])

    def test_foreign_threads_recorded_and_closed_only_with_e17(self):
        w = make_world(offers=current_offers(), foreign=(141,))
        state = {}
        self.assertEqual(hygiene.propose(w, make_book(w), FakeValuer(VALUES), Cfg(), PLAN, state), [])
        self.assertEqual(state["foreign_threads"], {141})
        out = hygiene.propose(w, make_book(w), FakeValuer(VALUES), Cfg(), dict(PLAN, close_foreign_threads=True), {})
        self.assertEqual(ids(out, "close_thread", "thread_id"), {141})

    def test_no_duplicates_between_startup_and_watch(self):
        w = make_world()
        out = hygiene.propose(w, make_book(w), FakeValuer(VALUES), Cfg(), PLAN, {})
        keys = [(it.kind, it.args.get("offer_id")) for it in out]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(ids(out), {2463, 1652})


if __name__ == "__main__":
    unittest.main()
