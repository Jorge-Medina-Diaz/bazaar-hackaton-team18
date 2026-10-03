"""Manual helper scripts at the repo root (night audit, Sun 4 Oct): their decision functions are pure and tested here.
ladder_sell / egg_carrier write only through `bazaar.py do --live` (the Gate); flag_candidates and
announce_candidates are read-only. No network here."""
from __future__ import annotations

import unittest

import announce_candidates as A
import egg_carrier
import flag_candidates as F
import ladder_sell as L
from agent import talk


def _offer(oid, maker="pilar", cash=200, asset=1063, exp=500, final=False, status="open", give_types=()):
    return {"id": oid, "maker": maker, "status": status, "final": final, "expires_tick": exp, "created_tick": 1,
            "give": {"cash": cash, "assets": [], "types": list(give_types)},
            "want": {"cash": 0, "assets": [{"id": asset}], "types": []}}


class LadderSellTest(unittest.TestCase):
    ASKS = [260, 250, 242, 235]

    def test_first_ask_then_down_the_ladder(self):
        self.assertEqual(L.decide(150, False, [], self.ASKS, 200), ("say", 260))
        self.assertEqual(L.decide(180, False, [260], self.ASKS, 200), ("say", 250))

    def test_accept_when_the_bid_reaches_our_next_ask(self):
        self.assertEqual(L.decide(245, False, [260, 250], self.ASKS, 200), ("accept", 245))

    def test_final_at_or_above_floor_is_accepted(self):
        self.assertEqual(L.decide(205, True, [260], self.ASKS, 200), ("accept", 205))

    def test_final_below_floor_closes(self):
        self.assertEqual(L.decide(190, True, [260], self.ASKS, 200)[0], "close")

    def test_ladder_exhausted_below_floor_closes(self):
        self.assertEqual(L.decide(190, False, self.ASKS, self.ASKS, 200)[0], "close")

    def test_bid_above_every_ask_is_taken(self):
        self.assertEqual(L.decide(9, False, [], [9, 8, 7, 6], 6), ("accept", 9))
        self.assertEqual(L.decide(5, False, [], [9, 8, 7, 6], 6), ("say", 9))
        self.assertEqual(L.decide(7, False, [9], [9, 8, 7, 6], 6), ("say", 8))

    def test_variants_eggs_then_ordinary(self):
        normal = L.normal_variants("abuela")
        self.assertEqual(normal, len(talk.TEMPLATES["abuela_sell"]) - talk.EGG_LINES["abuela_sell"])
        got = [L.variant_for(i, [5, 6], normal) for i in range(6)]
        self.assertEqual(got[:2], [5, 6])
        self.assertTrue(all(v < normal for v in got[2:]))

    def test_check_args_fail_closed(self):
        self.assertEqual(L.check_args("pilar", 200, self.ASKS, [], 198.0), [])
        self.assertTrue(L.check_args("pilar", 198, self.ASKS, [], 198.0))          # floor < value + 1
        self.assertTrue(L.check_args("pilar", 200, self.ASKS, [], None))           # value unknown
        self.assertTrue(L.check_args("pilar", 200, [250, 260], [], 198.0))         # not descending
        self.assertTrue(L.check_args("pilar", 240, self.ASKS, [], 198.0))          # an ask below the floor
        self.assertTrue(L.check_args("abuela", 6, [9, 8, 7, 6], [1], 5.0))         # ordinary variant as an egg
        self.assertEqual(L.check_args("abuela", 6, [9, 8, 7, 6], [5, 6], 5.0), [])
        self.assertTrue(L.check_args("ernesto", 6, [9], [], 5.0))

    def test_dealer_bids_structure_only(self):
        t = {"messages": [{"offer": _offer(1)}, {"offer": _offer(2, give_types=["card:SAL-10"])},
                          {"offer": _offer(3, asset=999)}, {"offer": _offer(4, exp=10)},
                          {"offer": _offer(5, maker="t18")}, {"offer": _offer(6, status="expired")}]}
        self.assertEqual([o["id"] for o in L.dealer_bids(t, "pilar", 1063, 100)], [1])

    def test_egg_carrier_needs_eggs(self):
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(egg_carrier.main(["abuela", "940", "MAL-01", "6", "9,8,7,6"]), 2)
            self.assertEqual(egg_carrier.main(["abuela", "940", "MAL-01", "6", "9,8,7,6", "-"]), 2)


class FlagCandidatesTest(unittest.TestCase):
    def thread(self, mid, give, text, item="La Puerta de Alcalá", topic="SAL-11", with_="picaros"):
        return {"id": 77, "with": with_, "item": item, "topic": {"buy": {"card": topic}},
                "messages": [{"id": mid, "tick": 10, "sender": with_, "text": text,
                              "offer": {"give": {"cash": 0, "assets": [], "types": [f"card:{give}"]},
                                        "want": {"cash": 100}}}]}

    def test_level_a_swap_named_in_the_text(self):
        got = F.candidates([self.thread(1, "SAL-10", "aquí tienes la Puerta, recién sacada")], frozenset())
        self.assertEqual(got, [(1, 77, 10, "SAL-11", ["SAL-10"])])

    def test_level_b_not_named_is_left_out(self):
        self.assertEqual(F.candidates([self.thread(2, "SAL-10", "ciento sesenta, última palabra")], frozenset()), [])

    def test_same_card_or_other_dealer_or_already_flagged(self):
        self.assertEqual(F.candidates([self.thread(3, "SAL-11", "la Puerta")], frozenset()), [])
        self.assertEqual(F.candidates([self.thread(4, "SAL-10", "la Puerta", with_="chato")], frozenset()), [])
        self.assertEqual(F.candidates([self.thread(8663, "SAL-10", "la Puerta")]), [])


class AnnounceCandidatesTest(unittest.TestCase):
    def ask(self, oid, ref, price, venue="rastro"):
        return {"id": oid, "status": "open", "venue": venue, "to": None,
                "give": {"cash": 0, "assets": [{"kind": "card", "ref": ref}], "types": []},
                "want": {"cash": price, "assets": [], "types": []}}

    def bid(self, oid, ref, price, venue="v21"):
        return {"id": oid, "status": "open", "venue": venue, "to": None,
                "give": {"cash": price, "assets": [], "types": []},
                "want": {"cash": 0, "assets": [], "types": [f"card:{ref}"]}}

    def test_owners_from_the_feed(self):
        ev = [{"type": "offer.listed", "actor": "t09", "payload": {"offer": {"id": 5, "maker": "t09"}}},
              {"type": "offer.cancelled", "payload": {"offer": 6}}]
        self.assertEqual(A.owners(ev), {5: "t09"})

    def test_pairs_cross_or_near_and_contenders_out(self):
        offers = [self.ask(1, "RET-01", 6), self.bid(2, "RET-01", 6), self.bid(3, "RET-01", 5),
                  self.ask(4, "MAL-07", 20), self.bid(5, "MAL-07", 9), self.bid(6, "RET-01", 7)]
        who = {1: "t09", 2: "t08", 3: "t13", 4: "t15", 5: "t16", 6: "t10"}
        got = A.pairs(offers, who)
        self.assertEqual([(p["ask_id"], p["bid_id"], p["gap"]) for p in got], [(1, 2, 0), (1, 3, 1)])
        self.assertTrue(all(p["bid_team"] != "t10" for p in got))       # contender out
        self.assertEqual(A.pairs(offers, {1: "t09", 2: "t09"}), [])       # same team

    def test_addressed_and_multi_card_offers_are_skipped(self):
        a = self.ask(1, "RET-01", 6)
        a["to"] = "t08"
        self.assertIsNone(A.side_of(a))
        m = self.ask(2, "RET-01", 6)
        m["give"]["assets"].append({"kind": "card", "ref": "RET-02"})
        self.assertIsNone(A.side_of(m))

    def test_draft_quotes_only_the_pair_numbers(self):
        p = {"ref": "RET-01", "ask_id": 11, "ask": 6, "ask_team": "t09", "ask_venue": "rastro", "bid_id": 12,
             "bid": 5, "bid_team": "t08", "bid_venue": "v21", "gap": 1}
        text = A.draft(p)
        self.assertIn("Team 9", text)
        self.assertIn("Team 8", text)
        self.assertIn("v18", text)
        import re
        self.assertTrue(set(re.findall(r"\d+", text)) <= {"9", "8", "01", "6", "11", "5", "12", "21", "1", "2", "18", "0"})


if __name__ == "__main__":
    unittest.main()
