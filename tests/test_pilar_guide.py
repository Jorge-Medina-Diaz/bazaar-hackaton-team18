import json
import os
import tempfile
import unittest

from harness import dealer_tuner
from harness.picaros_guide import next_buy, next_sell, trick
from harness.pilar_guide import expected_open, next_move
from harness.retrieval import import_feed

# Price paths observed in the public feed (Pilar's offers, the selling team's asks), no team ids.
OBSERVED = [
    ("SAL-07", [22, 22, 22, 23, (24, True)], [40, 37, 34, 32, 30]),
    ("LAV-08", [16, 16, 17, (17, True)], [25, 22, 20, 19]),
    ("SAL-06", [22, 22, 23, (24, True)], [40, 39, 38]),
    ("LAV-06", [16, 16, 16, 17, 17, 18, 19, (19, True)], [30, 28, 27, 26, 25, 24, 23, 22]),
]
# Los Pícaros, real buy thread 1075 (t05, SAL-09): their offers (price, final, trick?) and the team's bids.
PICAROS_1075 = ([(73, False, None), (65, False, "da ['SAL-06'] en vez de SAL-09"), (60, False, None), (56, False, None)], [45, 48, 51, 54])


def _her(seq):
    return [x if isinstance(x, tuple) else (x, False) for x in seq]


class PilarGuideTest(unittest.TestCase):
    def test_invariants_on_observed_states(self):
        n = 0
        for ref, her_all, ours_all in OBSERVED:
            her_all = _her(her_all)
            for i in range(1, len(her_all) + 1):
                for j in range(0, len(ours_all) + 1):
                    her, ours = her_all[:i], ours_all[:j]
                    for floor in (1, her[-1][0], her[-1][0] + 1):
                        m = next_move(ref, "uncommon", floor, her, ours); n += 1
                        if m["do"] == "accept":
                            self.assertGreaterEqual(her[-1][0], floor)
                        if m["do"] == "say":
                            self.assertNotIn(m["price"], ours)
                            self.assertGreater(m["price"], her[-1][0])
                            self.assertGreaterEqual(m["price"], floor)
                            self.assertFalse(her[-1][1])
                            if ours:
                                self.assertLess(m["price"], ours[-1])
        self.assertGreater(n, 200)

    def test_final_decides(self):
        self.assertEqual(next_move("SAL-07", "uncommon", 30, [(24, True)], [30])["do"], "close")
        self.assertEqual(next_move("SAL-07", "uncommon", 5, [(24, True)], [30])["do"], "accept")

    def test_asks_her_price_plus_one_then_takes_hers(self):
        self.assertEqual(next_move("SAL-07", "uncommon", 5, [(23, False)], [24])["do"], "accept")
        self.assertEqual(expected_open("LAV-06", "uncommon"), 16)

    def test_harness_sees_pilar(self):
        ev = [{"id": 1, "tick": 1, "scope": "public", "type": "thread.opened",
               "payload": {"thread": 9, "kind": "persona", "team": "t09", "with": "pilar", "topic": {"sell": {"assets": [1]}}}}]
        cases, _ = import_feed(ev, "t")
        self.assertTrue(any(c.dealer == "pilar" for c in cases))


class PicarosGuideTest(unittest.TestCase):
    def test_trick_is_structural(self):
        topic = {"buy": {"card": "SAL-09"}}
        self.assertIsNotNone(trick(topic, {"give": {"types": ["card:SAL-06"]}, "want": {"cash": 65}}))
        self.assertIsNotNone(trick(topic, {"give": {"types": ["pack:sobre_oro"]}, "want": {"cash": 50}}))
        self.assertIsNone(trick(topic, {"give": {"types": ["card:SAL-09"]}, "want": {"cash": 60}}))
        self.assertIsNotNone(trick({"sell": {"assets": [1]}}, {"give": {"cash": 0}, "want": {"assets": [{"ref": "LAV-05"}]}}))

    def test_never_accepts_trick_nor_above_ceiling(self):
        theirs_all, ours_all = PICAROS_1075
        for i in range(1, len(theirs_all) + 1):
            for j in range(0, len(ours_all) + 1):
                theirs, ours = theirs_all[:i], ours_all[:j]
                for ceiling in (40, 55, 60, 112):
                    m = next_buy("SAL-09", ceiling, theirs, ours)
                    if m["do"] == "accept":
                        self.assertIsNone(theirs[-1][2])
                        self.assertLessEqual(theirs[-1][0], ceiling)
                    if m["do"] == "say":
                        self.assertLessEqual(m["price"], ceiling)
                        if ours:
                            self.assertGreater(m["price"], ours[-1])
                        if theirs[-1][2] is None:
                            self.assertLess(m["price"], theirs[-1][0])

    def test_sell_respects_floor(self):
        self.assertEqual(next_sell("common", 6, [(4, True, None)], [8])["do"], "close")
        self.assertEqual(next_sell("uncommon", 5, [(13, True, None)], [16])["do"], "accept")


class DealerTunerTest(unittest.TestCase):
    def test_learns_from_feed_file(self):
        ev = [
            {"id": 1, "tick": 1, "payload": {"thread": 5, "team": "t09", "with": "pilar", "topic": {"sell": {"assets": [7]}}}, "type": "thread.opened"},
            {"id": 2, "tick": 1, "type": "thread.message", "payload": {"thread": 5, "sender": "t09", "offer": {"give": {"assets": [{"ref": "SAL-07", "rarity": "uncommon"}]}, "want": {"cash": 30}}}},
            {"id": 3, "tick": 2, "type": "thread.message", "payload": {"thread": 5, "sender": "pilar", "offer": {"give": {"cash": 22}, "want": {}}}},
            {"id": 4, "tick": 2, "type": "thread.message", "payload": {"thread": 5, "sender": "t09", "offer": {"give": {"assets": [{"ref": "SAL-07", "rarity": "uncommon"}]}, "want": {"cash": 29}}}},
            {"id": 5, "tick": 3, "type": "thread.message", "payload": {"thread": 5, "sender": "pilar", "offer": {"give": {"cash": 23}, "want": {}, "final": True}}},
        ]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "feed.jsonl")
            with open(path, "w") as f:
                f.write("\n".join(json.dumps(e) for e in ev))
            out = dealer_tuner.learn([path])
        g = out["pilar|venta|fav·uncommon"]
        self.assertEqual(g["final_min"], 2)
        self.assertEqual(g["p_sube"]["1"], 1.0)


if __name__ == "__main__":
    unittest.main()
