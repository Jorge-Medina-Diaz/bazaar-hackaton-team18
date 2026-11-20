"""M6a: FakeGame mechanics, oracle anchor (Friday: 11/12 neg points, the 5 losses P-05), faults, invariants."""
from __future__ import annotations

import collections
import http.client
import json
import unittest

from tests import HARVEST
from sim import faults, invariants
from sim.world import FakeGame, Model, VirtualClock, deal_delta, venue_fee

KEY = {"X-Team-Key": "tk-test"}


def call(g, method, path, body=None, key="tk-test"):
    data = None if body is None else json.dumps(body).encode()
    s, raw = g.http(method, "http://127.0.0.1" + path, data, {"X-Team-Key": key})
    return s, json.loads(raw) if raw else None


class Dealer:
    """Minimal dealer double: opens at `ask`, accepts any price >= floor."""
    def __init__(self, dealer_id="abuela", ask=20, floor=15):
        self.dealer_id, self.ask, self.floor = dealer_id, ask, floor

    def on_message(self, game, thread, msg):
        if msg is None:
            game.dealer_say(thread["id"], self.ask, "hola")
        elif msg["price"] is not None and msg["price"] >= self.floor:
            game.dealer_accept(thread["id"])
        else:
            game.dealer_say(thread["id"], self.ask, "no")


# ------------------------------------------------------------------------------ oracle anchor (P-04, P-05)

DEALS = [(6, 44, "dealer", 17, 0, True), (45, 480, "dealer", 9, 0, True), (53, 598, "team", 9, 2, False),
         (63, 806, "dealer", 10, 0, True), (64, 597, "team", 9, 2, False), (64, 593, "team", 9, 2, False),
         (67, 920, "dealer", 24, 0, True), (72, 980, "team", 80, 5, False), (90, 1311, "team", 9, 2, False),
         (92, 1334, "team", 10, 2, True), (97, 1424, "dealer", 23, 0, True), (115, 1791, "dealer", 22, 0, True),
         (118, 1199, "team", 9, 2, False), (140, 2334, "dealer", 32, 0, True), (146, 2422, "team", 23, 3, True),
         (147, 2505, "team", 9, 2, False), (155, 2662, "dealer", 13, 0, True)]
MEAS = {53: 6.8, 64: 20.9, 67: 20.9, 90: 74.9, 92: 81.6, 97: 73.2, 115: 71.3, 118: 77.6, 140: 65.8, 146: 79.0,
        147: 79.0, 155: 74.5}
LOSSES = {806: -1.0, 1424: -8.488, 1791: -1.855, 2334: -11.813, 2662: -4.5}
AFF = {"LAV": 0.7, "MAL": 0.5, "LAT": 0.9, "SAL": 1.1, "RET": 1.3, "CHA": 1.6}


def friday_ledger(cap=50.0):
    with open(HARVEST / "cards_all.json", encoding="utf-8") as fh:
        ca = json.load(fh)
    with open(HARVEST / "catalog.json", encoding="utf-8") as fh:
        model = Model(json.load(fh))

    def holdings(tick, inclusive):
        c, packs = collections.Counter(), []
        for a in ca.values():
            own = None
            for h in a["history"]:
                if (h["tick"] <= tick) if inclusive else (h["tick"] < tick):
                    own = h["to"]
            if own == "t18":
                if a["kind"] == "card":
                    c[a["ref"]] += 1
                else:
                    packs.append(a["ref"])
        return c, packs

    def minted_before(tick):
        m = collections.Counter()
        for a in ca.values():
            if a["kind"] == "card" and a["history"][0]["tick"] < tick:
                m[a["ref"]] += 1
        return m

    neg, rows = 0.0, []
    for tick, oid, kind, price, fee, we_acc in DEALS:
        moved = [(a, h) for a in ca.values() for h in a["history"]
                 if h["tick"] == tick and h["why"] == f"trade #{oid}" and "t18" in (h["from"], h["to"])]
        assert moved, oid
        hb, pb = holdings(tick, False)
        h2, p2 = hb.copy(), list(pb)
        for a, h in moved:
            sign = 1 if h["to"] == "t18" else -1
            if a["kind"] == "card":
                h2[a["ref"]] += sign
            elif sign > 0:
                p2.append(a["ref"])
            else:
                p2.remove(a["ref"])
        minted = minted_before(tick)
        dv = model.value(h2, p2, AFF, minted) - model.value(hb, pb, AFF, minted)
        buy = moved[0][1]["to"] == "t18"
        d = deal_delta(dv, -price if buy else price, dealer=kind == "dealer", fee=fee, we_accepted=we_acc, cap=cap)
        neg += d
        rows.append((tick, oid, d, neg))
    return rows


class TestOracleFriday(unittest.TestCase):
    def test_eleven_of_twelve_neg_points(self):
        rows = friday_ledger()
        last = {}
        for tick, oid, d, neg in rows:
            last[tick] = neg
        ok = sum(1 for t, m in MEAS.items() if abs(round(last[t] + 1e-9, 1) - m) < 0.051)
        self.assertEqual(ok, 11)
        self.assertAlmostEqual(rows[-1][3], 74.452, places=2)

    def test_five_friday_losses(self):
        got = {oid: d for _, oid, d, _ in friday_ledger() if d < -1e-9}
        self.assertEqual(set(got), set(LOSSES))
        for oid, v in LOSSES.items():
            self.assertAlmostEqual(got[oid], v, places=2, msg=oid)

    def test_cap_50_on_sal10(self):
        rows = {oid: d for _, oid, d, _ in friday_ledger()}
        self.assertAlmostEqual(rows[980], 50.0, places=6)
        rows_nocap = {oid: d for _, oid, d, _ in friday_ledger(cap=None)}
        self.assertAlmostEqual(rows_nocap[980], 69.875, places=3)

    def test_fixture_collection_value(self):
        g = FakeGame.from_fixtures(HARVEST)
        s, me = call(g, "GET", "/api/me")
        self.assertEqual(s, 200)
        self.assertAlmostEqual(me["collection_value"], 505.4, delta=0.05)

    def test_fee_rule(self):
        self.assertEqual(venue_fee(23, 1, 500, 1), 3)
        self.assertEqual(venue_fee(9, 1, 500, 1), 2)
        self.assertEqual(venue_fee(80, 1, 500, 1), 5)
        self.assertEqual(venue_fee(20, 1, 500, 1), 2)       # 1 + 1 exactly, no float drift
        self.assertEqual(venue_fee(50, 2, 100, 0), 1)


# ------------------------------------------------------------------------------ mechanics

class TestMarket(unittest.TestCase):
    def setUp(self):
        self.g = FakeGame(seed=1, tick_seconds=30.0)
        self.g.add_team("t05", cash=500, cards=["LAT-09", "LAV-01"], affinity=AFF)
        self.our = sorted(a for a, x in self.g.assets.items() if x["owner"] == "t18")

    def test_list_board_pseudonym_and_me_offers(self):
        aid = self.our[0]
        s, o = call(self.g, "POST", "/api/offers", {"give": {"assets": [aid]}, "want": {"cash": 9}, "venue": "rastro"})
        self.assertEqual(s, 200, o)
        self.assertEqual(o["maker"], "t18")
        _, board = call(self.g, "GET", "/api/venues/rastro/offers")
        b = [x for x in board["offers"] if x["id"] == o["id"]][0]
        self.assertNotEqual(b["maker"], "t18")
        self.assertEqual(b["maker"], self.g.pseudonym("t18"))
        _, mine = call(self.g, "GET", "/api/me/offers")
        self.assertEqual([x["maker"] for x in mine["offers"] if x["id"] == o["id"]], ["t18"])

    def test_directed_offer_visible_to_target_not_on_board(self):
        t05 = [a for a, x in self.g.assets.items() if x["owner"] == "t05" and x["ref"] == "LAV-01"][0]
        st, o = self.g.handle("POST", "/api/offers", {"give": {"assets": [t05]}, "want": {"cash": 5}, "to": "t18"},
                              team="t05")
        self.assertEqual(st, 200)
        _, board = call(self.g, "GET", "/api/venues/rastro/offers")
        self.assertNotIn(o["id"], [x["id"] for x in board["offers"]])
        _, mine = call(self.g, "GET", "/api/me/offers")
        self.assertIn(o["id"], [x["id"] for x in mine["offers"]])

    def test_expiry_in_15_second_units(self):
        aid = self.our[0]
        _, o = call(self.g, "POST", "/api/offers", {"give": {"assets": [aid]}, "want": {"cash": 9},
                                                    "expires_in_ticks": 40})
        self.assertEqual(o["expires_tick"] - o["created_tick"], 20)       # 40 * 15 / 30
        g60 = FakeGame(seed=1, tick_seconds=60.0)
        a2 = sorted(a for a, x in g60.assets.items() if x["owner"] == "t18")[0]
        _, o2 = call(g60, "POST", "/api/offers", {"give": {"assets": [a2]}, "want": {"cash": 9}, "expires_in_ticks": 40})
        self.assertEqual(o2["expires_tick"] - o2["created_tick"], 10)     # R-07

    def test_accept_settles_next_tick_with_fee_by_accepter_and_oracle(self):
        t05 = [a for a, x in self.g.assets.items() if x["owner"] == "t05" and x["ref"] == "LAT-09"][0]
        st, o = self.g.handle("POST", "/api/offers", {"give": {"assets": [t05]}, "want": {"cash": 60}}, team="t05")
        cash0 = self.g.teams["t18"]["cash"]
        s, r = call(self.g, "POST", f"/api/offers/{o['id']}/accept", {})
        self.assertEqual(s, 200, r)
        self.assertEqual(r["fee"], 4)                                     # ceil(3 + 1)
        self.assertEqual(self.g.assets[t05]["owner"], "t05")             # not before the next tick
        self.g.advance()
        self.assertEqual(self.g.assets[t05]["owner"], "t18")
        self.assertEqual(self.g.teams["t18"]["cash"], cash0 - 64)
        self.assertEqual(self.g.teams["t05"]["cash"], 560)
        row = self.g.oracle("t18")["rows"][-1]
        self.assertTrue(row["accepter"])
        self.assertAlmostEqual(row["dv"], 63.0, places=3)                 # rare LAT, first copy, 70 * 0.9
        self.assertAlmostEqual(row["delta"], 63.0 - 64, places=3)
        self.assertTrue(invariants.check(self.g))                         # a loss -> INV-04 reported

    def test_one_accept_per_tick(self):
        ids = []
        for ref in ("LAT-09", "LAV-01"):
            aid = [a for a, x in self.g.assets.items() if x["owner"] == "t05" and x["ref"] == ref][0]
            ids.append(self.g.handle("POST", "/api/offers", {"give": {"assets": [aid]}, "want": {"cash": 5}},
                                     team="t05")[1]["id"])
        self.assertEqual(call(self.g, "POST", f"/api/offers/{ids[0]}/accept", {})[0], 200)
        s, r = call(self.g, "POST", f"/api/offers/{ids[1]}/accept", {})
        self.assertEqual((s, r["error"]), (429, "wait_for_tick"))
        self.g.advance()
        self.assertEqual(call(self.g, "POST", f"/api/offers/{ids[1]}/accept", {})[0], 200)

    def test_swap_and_rival_venue_fee(self):
        self.g.add_venue("v03", "t05", fee_bps=100, fee_per_card=0)
        t05 = [a for a, x in self.g.assets.items() if x["owner"] == "t05" and x["ref"] == "LAT-09"][0]
        mine = self.our[0]
        ref = self.g.assets[mine]["ref"]
        st, o = self.g.handle("POST", "/api/offers", {"give": {"assets": [t05]}, "want": {"cards": [ref]},
                                                      "venue": "rastro"}, team="t05")
        self.assertEqual(st, 200, o)
        self.assertEqual(o["want"]["types"], [f"card:{ref}"])
        s, r = call(self.g, "POST", f"/api/offers/{o['id']}/accept", {"assets": [mine]})
        self.assertEqual(s, 200, r)
        self.assertEqual(r["fee"], 2)                                     # ceil(0 + 1 * 2 cards)
        self.g.advance()
        self.assertEqual(self.g.assets[mine]["owner"], "t05")
        self.assertEqual(self.g.assets[t05]["owner"], "t18")
        # the owner cannot trade on its own venue; others pay that venue's fee
        s, r = self.g.handle("POST", "/api/offers", {"give": {"cash": 10}, "want": {"cards": ["LAV-01"]},
                                                     "venue": "v03"}, team="t05")
        self.assertEqual((s, r["error"]), (403, "self_venue"))
        st, o = call(self.g, "POST", "/api/offers", {"give": {"cash": 50}, "want": {"cards": ["LAV-02"]}, "venue": "v03"})
        self.assertEqual(st, 200, o)
        self.assertEqual(self.g.fee_for(self.g.offers[o["id"]]), 1)       # ceil(0.5 + 0) on v03

    def test_phantom_offer_fails_at_settlement(self):
        aid = [a for a, x in self.g.assets.items() if x["owner"] == "t05" and x["ref"] == "LAV-01"][0]
        _, o = self.g.handle("POST", "/api/offers", {"give": {"assets": [aid]}, "want": {"cash": 5}}, team="t05")
        call(self.g, "POST", f"/api/offers/{o['id']}/accept", {})
        self.g.assets[aid]["owner"] = "abuela"                            # sold elsewhere meanwhile
        self.g.advance()
        self.assertEqual(self.g.offers[o["id"]]["status"], "failed")
        self.assertEqual(self.g.oracle()["deals"], 0)

    def test_bids_reserve_cash_flag(self):
        g = FakeGame(seed=2, team_cash=100, bids_reserve_cash=True)
        self.assertEqual(call(g, "POST", "/api/offers", {"give": {"cash": 60}, "want": {"cards": ["LAT-09"]}})[0], 200)
        s, r = call(g, "POST", "/api/offers", {"give": {"cash": 60}, "want": {"cards": ["LAT-10"]}})
        self.assertEqual((s, r["error"]), (409, "insufficient_cash"))
        g2 = FakeGame(seed=2, team_cash=100)
        self.assertEqual(call(g2, "POST", "/api/offers", {"give": {"cash": 60}, "want": {"cards": ["LAT-09"]}})[0], 200)
        self.assertEqual(call(g2, "POST", "/api/offers", {"give": {"cash": 60}, "want": {"cards": ["LAT-10"]}})[0], 200)

    def test_cancel_only_by_maker(self):
        _, o = call(self.g, "POST", "/api/offers", {"give": {"assets": [self.our[0]]}, "want": {"cash": 9}})
        s, r = self.g.handle("DELETE", f"/api/offers/{o['id']}", team="t05")
        self.assertEqual(s, 403)
        self.assertEqual(call(self.g, "DELETE", f"/api/offers/{o['id']}")[0], 200)
        self.assertEqual(self.g.offers[o["id"]]["status"], "cancelled")

    def test_dealer_offer_shape_and_deal(self):
        self.g.add_bot(Dealer(ask=20, floor=15))
        s, t = call(self.g, "POST", "/api/threads", {"with": "abuela", "topic": {"buy": {"card": "LAV-05"}}})
        self.assertEqual(s, 200, t)
        off = t["standing_offers"][0]
        self.assertEqual((off["venue"], off["to"], off["maker"]), (None, "t18", "abuela"))
        self.assertEqual(off["expires_tick"], off["created_tick"] + 2)
        _, mine = call(self.g, "GET", "/api/me/offers")
        self.assertIn(off["id"], [x["id"] for x in mine["offers"]])
        s, r = call(self.g, "POST", f"/api/threads/{t['id']}/messages", {"text": "16?", "price": 16})
        self.assertEqual(s, 200, r)
        self.assertEqual(r["thread"]["status"], "deal")
        s, r = call(self.g, "POST", f"/api/threads/{t['id']}/messages", {"text": "x", "price": 17})
        self.assertEqual(s, 409)
        self.g.advance()
        row = self.g.oracle()["rows"][-1]
        self.assertEqual(row["dealer"], "abuela")
        self.assertLessEqual(row["delta"], 0.0)                           # P-04: never positive

    def test_one_message_per_side_per_tick(self):
        self.g.add_bot(Dealer(ask=30, floor=29))
        _, t = call(self.g, "POST", "/api/threads", {"with": "abuela", "topic": {"buy": {"pack": "sobre_barrio"}}})
        self.assertEqual(call(self.g, "POST", f"/api/threads/{t['id']}/messages", {"text": "a", "price": 10})[0], 200)
        s, r = call(self.g, "POST", f"/api/threads/{t['id']}/messages", {"text": "b", "price": 11})
        self.assertEqual((s, r["error"]), (429, "wait_for_tick"))

    def test_pack_open_deterministic(self):
        def run():
            g = FakeGame(seed=7)
            aid = g.gift("t18", packs=["sobre_barrio"])[0]
            return [c["ref"] for c in call(g, "POST", f"/api/packs/{aid}/open")[1]["cards"]]
        self.assertEqual(run(), run())
        self.assertEqual(len(run()), 3)


class TestDuels(unittest.TestCase):
    def setUp(self):
        self.g = FakeGame(seed=3)

    def test_accept_takes_standing_offer_at_post_time(self):
        did = self.g.create_duel(limit=100, deadline_ticks=10, decay=0.1)
        self.assertEqual(call(self.g, "POST", f"/api/duels/{did}/accept")[1]["error"], "no_offer")
        call(self.g, "POST", f"/api/duels/{did}/messages", {"text": "", "price": 60})
        self.g.rival_say(did, 90)
        self.assertFalse(self.g.rival_say(did, 85))                       # one per tick
        self.g.advance()
        self.g.rival_say(did, 80)                                         # worsens/improves between read and POST
        s, r = call(self.g, "POST", f"/api/duels/{did}/accept")
        self.assertEqual(s, 200, r)
        self.g.advance()
        d = self.g.duels[did]
        self.assertEqual((d["status"], d["price"]), ("deal", 80))
        self.assertAlmostEqual(d["result"], round(20 * 0.9 ** 1, 1))      # rounds = min(1, 2)

    def test_days_top_level_or_in_offer(self):
        did = self.g.create_duel(issues=("price", "days"))
        s, r = call(self.g, "POST", f"/api/duels/{did}/messages", {"text": "", "price": 60})
        self.assertEqual((s, r["error"]), (400, "missing_days"))
        self.assertEqual(call(self.g, "POST", f"/api/duels/{did}/messages", {"text": "", "price": 60, "days": 3})[0], 200)
        self.g.advance()
        s, r = call(self.g, "POST", f"/api/duels/{did}/messages",
                    {"text": "", "price": 61, "offer": {"price": 61, "days": 4}})
        self.assertEqual(s, 200, r)
        self.assertEqual(r["duel"]["your_offer"]["days"], 4)

    def test_deadline_no_deal(self):
        did = self.g.create_duel(deadline_ticks=2)
        self.g.advance(3)
        self.assertEqual(self.g.duels[did]["status"], "no_deal")
        _, done = call(self.g, "GET", "/api/duels?done=true")
        self.assertEqual([d["duel"] for d in done["duels"]], [did])


class TestFaults(unittest.TestCase):
    def setUp(self):
        self.g = FakeGame(seed=4)
        self.aid = sorted(a for a, x in self.g.assets.items() if x["owner"] == "t18")[0]
        self.body = json.dumps({"give": {"assets": [self.aid]}, "want": {"cash": 9}}).encode()

    def post(self):
        return self.g.http("POST", "http://127.0.0.1/api/offers", self.body, KEY)

    def n_offers(self):
        return sum(1 for o in self.g.offers.values() if o["maker"] == "t18")

    def test_no_commit_faults(self):
        for do, status in (("429_wait", 429), ("429_rate", 429), ("500", 500), ("redirect_302", 302)):
            self.g.faults = faults.Plan([{"do": do, "method": "POST"}])
            s, raw = self.post()
            self.assertEqual(s, status, do)
            self.assertEqual(self.n_offers(), 0, do)

    def test_commit_then_garbled(self):
        cases = {"html_200": lambda s, raw: raw.startswith(b"<html"),
                 "truncated_body": lambda s, raw: raw.endswith(b"}") is False,
                 "bad_json": lambda s, raw: raw == b"{not json"}
        for i, (do, ok) in enumerate(cases.items()):
            self.g.faults = faults.Plan([{"do": do, "method": "POST"}])
            s, raw = self.post()
            self.assertTrue(ok(s, raw), do)
            self.assertEqual(self.n_offers(), i + 1, do)                  # it landed
            self.g.advance()

    def test_drop_and_incomplete_raise_after_commit(self):
        self.g.faults = faults.Plan([{"do": "drop_after_commit", "method": "POST"}])
        with self.assertRaises(ConnectionResetError):
            self.post()
        self.assertEqual(self.n_offers(), 1)
        self.g.advance()
        self.g.faults = faults.Plan([{"do": "incomplete_read", "method": "POST"}])
        with self.assertRaises(http.client.IncompleteRead):
            self.post()
        self.assertEqual(self.n_offers(), 2)

    def test_shape_faults_on_reads(self):
        self.g.faults = faults.Plan([{"do": "missing_field", "path": "/api/clock", "field": "tick"},
                                     {"do": "type_swap", "path": "/api/clock", "field": "tick"},
                                     {"do": "extra_field", "path": "/api/clock"}])
        c1 = json.loads(self.g.http("GET", "http://x/api/clock", None, KEY)[1])
        c2 = json.loads(self.g.http("GET", "http://x/api/clock", None, KEY)[1])
        c3 = json.loads(self.g.http("GET", "http://x/api/clock", None, KEY)[1])
        c4 = json.loads(self.g.http("GET", "http://x/api/clock", None, KEY)[1])
        self.assertNotIn("tick", c1)
        self.assertIsInstance(c2["tick"], str)
        self.assertIn("__extra__", c3)
        self.assertIsInstance(c4["tick"], int)                             # rules used up

    def test_game_faults(self):
        self.g.faults = faults.Plan([
            {"do": "limits_change", "tick": 1, "args": {"limits": {"accepts_per_team_per_tick": 2}}},
            {"do": "pack_grant", "tick": 2, "args": {"cash": 150}},
            {"do": "gift", "tick": 2, "args": {"cards": ["MAL-02"]}},
            {"do": "doors_closed", "tick": 3},
            {"do": "doors_closed", "tick": 4, "args": {"on": False}},
            {"do": "pause", "tick": 5}])
        cash0 = self.g.teams["t18"]["cash"]
        self.g.advance()
        self.assertEqual(call(self.g, "GET", "/api/clock")[1]["limits"]["accepts_per_team_per_tick"], 2)
        self.g.advance()
        self.assertEqual(self.g.teams["t18"]["cash"], cash0 + 150)
        self.assertIn("pack", [x["kind"] for x in call(self.g, "GET", "/api/me")[1]["assets"]])
        self.g.advance()
        s, o = self.g.http("POST", "http://x/api/offers", self.body, KEY)
        self.assertEqual(json.loads(o)["status"], "queued")
        self.g.advance()
        self.assertEqual(self.g.doors, "open")
        self.g.advance(3)
        self.assertTrue(self.g.paused)
        self.assertEqual(self.g.tick, 4)


class TestInvariants(unittest.TestCase):
    def test_clean_run_and_admin_violation(self):
        g = FakeGame(seed=5)
        call(g, "GET", "/api/me")
        g.advance(3)
        self.assertEqual(invariants.check(g), [])
        call(g, "GET", "/api//admin/teams")
        self.assertTrue(any(v.startswith("INV-01") for v in invariants.check(g)))

    def test_journal_matching(self):
        import hashlib
        import os
        import tempfile
        g = FakeGame(seed=6)
        aid = sorted(a for a, x in g.assets.items() if x["owner"] == "t18")[0]
        body = {"give": {"assets": [aid]}, "want": {"cash": 9}}
        call(g, "POST", "/api/offers", body)
        d = tempfile.mkdtemp()
        p = os.path.join(d, "journal.jsonl")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("")
        self.assertTrue(any(v.startswith("INV-15") for v in invariants.check(g, p)))
        sha = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": "intent", "id": "a1", "request": ["POST", "/api/offers", sha]}) + "\n")
        self.assertEqual(invariants.check(g, p), [])

    def test_virtual_clock(self):
        c = VirtualClock(0)
        g = FakeGame(seed=0, clock=c, tick_seconds=30)
        self.assertEqual(call(g, "GET", "/api/clock")[1]["next_tick_in"], 30.0)
        c.sleep(10)
        self.assertEqual(call(g, "GET", "/api/clock")[1]["next_tick_in"], 20.0)
        g.advance()
        self.assertEqual(c.now(), 30.0)


if __name__ == "__main__":
    unittest.main()


class HiddenCardTest(unittest.TestCase):
    """Sim fidelity (pre-Sunday audit): a hidden card is worth 0, like the live value?card for LAT-13 (prestige only).
    Without it a full-Sunday sim run failed the Valuer self_check (405 vs 0) and froze dealers and rastro."""

    def test_hidden_card_is_worth_zero(self):
        cat = {"sets": [{"id": "LAT", "released": True, "cards": [
            {"id": "LAT-12", "rarity": "legendary", "book": 450, "print_run": 3, "page": False},
            {"id": "LAT-13", "rarity": "legendary", "book": 450, "print_run": 1, "page": False, "hidden": True}]}]}
        m = Model(cat)
        self.assertEqual(m.base("LAT-13", {"LAT": 0.9}), 0.0)
        self.assertEqual(m.base("LAT-12", {"LAT": 0.9}), 405.0)


class MasterBonusTest(unittest.TestCase):
    """Sim fidelity (pre-Sunday audit): the master bonus the live server pays (Valuer V-13, SAL-12 593.45 with SAL-11
    held); without it the Sunday sim failed self_check after the RET-11 / CHA-11 buys and froze the tactics."""

    def test_model_matches_the_valuer(self):
        from agent.valuation import Valuer
        cat = {"values": {"copy_marginals": [1.0, 0.25, 0.1], "page_bonus": 0.25, "master_bonus": 0.1},
               "sets": [{"id": "SAL", "released": True, "cards":
                         [{"id": f"SAL-{i:02d}", "rarity": "common", "book": 10, "print_run": 300, "page": True}
                          for i in range(1, 11)]
                         + [{"id": "SAL-11", "rarity": "epic", "book": 180, "print_run": 9, "page": False},
                            {"id": "SAL-12", "rarity": "legendary", "book": 450, "print_run": 3, "page": False}]}]}
        aff = {"SAL": 1.1}
        held = collections.Counter({f"SAL-{i:02d}": 1 for i in range(1, 12)})
        m, v = Model(cat), Valuer(cat, aff, frozenset({"SAL"}))
        with_l = collections.Counter(held)
        with_l["SAL-12"] += 1
        self.assertAlmostEqual(m.total(with_l, aff) - m.total(held, aff), v.delta_add(held, "SAL-12"), places=6)
