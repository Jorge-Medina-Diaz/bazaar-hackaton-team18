import unittest

from harness.pilar_guide import expected_open, next_move
from harness.retrieval import import_feed

# Price paths observed in the public feed (Pilar's offers, the selling team's asks), no team ids.
OBSERVED = [
    ("SAL-07", [22, 22, 22, 23, (24, True)], [40, 37, 34, 32, 30]),
    ("LAV-08", [16, 16, 17, (17, True)], [25, 22, 20, 19]),
    ("SAL-06", [22, 22, 23, (24, True)], [40, 39, 38]),
    ("LAV-06", [16, 16, 16, 17, 17, 18, 19, (19, True)], [30, 28, 27, 26, 25, 24, 23, 22]),
]


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
        self.assertGreater(n, 200)

    def test_final_decides(self):
        self.assertEqual(next_move("SAL-07", "uncommon", 30, [(24, True)], [30])["do"], "close")
        self.assertEqual(next_move("SAL-07", "uncommon", 5, [(24, True)], [30])["do"], "accept")

    def test_anchor_and_e1(self):
        self.assertEqual(next_move("SAL-07", "uncommon", 5, [], []), {"do": "say", "price": 30, "why": "anchor = opening + 8"})
        self.assertEqual(next_move("SAL-07", "uncommon", 5, [(22, False)], [30, 29, 28, 27, 26, 25, 24])["price"], 23)
        self.assertEqual(next_move("SAL-07", "uncommon", 5, [(23, False)], [24])["do"], "accept")
        self.assertEqual(expected_open("LAV-06", "uncommon"), 16)

    def test_harness_sees_pilar(self):
        ev = [{"id": 1, "tick": 1, "scope": "public", "type": "thread.opened",
               "payload": {"thread": 9, "kind": "persona", "team": "t09", "with": "pilar", "topic": {"sell": {"assets": [1]}}}}]
        cases, _ = import_feed(ev, "t")
        self.assertTrue(any(c.dealer == "pilar" for c in cases))


if __name__ == "__main__":
    unittest.main()
