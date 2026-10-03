import unittest

import bitacora


class TestBitacora(unittest.TestCase):
    def test_trailers_pair_why_with_previous_entry(self):
        body = "texto libre\nDecisión: no abrimos mercado\nPor qué: 270 P inmovilizados\nLección: el marcador va atrasado"
        self.assertEqual(bitacora.trailers(body), [
            {"tipo": "decisión", "texto": "no abrimos mercado", "por_que": "270 P inmovilizados"},
            {"tipo": "lección", "texto": "el marcador va atrasado", "por_que": ""}])

    def test_wall_estimator_interpolates_and_jumps_the_night(self):
        events = [{"at_hours": 14.0, "wall": "2026-10-03T23:00:00+02:00"},
                  {"at_hours": 14.0, "wall": "2026-10-04T09:00:00+02:00"},
                  {"at_hours": 20.0, "wall": "2026-10-04T15:00:00+02:00"}]
        sat_17 = bitacora.parse_wall("2026-10-03T17:00:00+02:00")
        est = bitacora.wall_estimator(8.0, sat_17, events)
        self.assertEqual(est(11.0), bitacora.parse_wall("2026-10-03T20:00:00+02:00"))
        self.assertEqual(est(16.0), bitacora.parse_wall("2026-10-04T11:00:00+02:00"))
        self.assertEqual(est(21.0), bitacora.parse_wall("2026-10-04T16:00:00+02:00"))   # extrapolado

    def test_replace_blocks_keeps_manual_text_and_ignores_timestamp_only(self):
        doc = "a mano\n<!-- AUTO:x -->\n_t1_ <!-- ts -->\nX\n<!-- /AUTO:x -->\nfin\n<!-- AUTO:y -->\n<!-- /AUTO:y -->\n"
        new, changed = bitacora.replace_blocks(doc, {"x": "_t2_ <!-- ts -->\nX"})
        self.assertFalse(changed)
        self.assertIn("_t2_", new)
        new, changed = bitacora.replace_blocks(new, {"y": "Y"})
        self.assertTrue(changed)
        self.assertTrue(new.startswith("a mano\n") and "fin\n<!-- AUTO:y -->\nY\n<!-- /AUTO:y -->" in new)

    def test_market_block_compares_own_venue_with_starter_stall(self):
        snap = {"ts": 0, "leaderboard": {"teams": [
            {"team": "t18", "market": 7.5}, {"team": "t10", "market": 12.5}, {"team": "t03", "market": 4.75}]},
            "venues": {"venues": [
                {"owner": "t18", "starter": True, "status": "open", "trades": 0},
                {"owner": "t10", "starter": False, "status": "open", "trades": 8},
                {"owner": "t03", "starter": False, "status": "open", "trades": 0},
                {"owner": "t03", "starter": False, "status": "closed", "trades": 0}]}}
        out = bitacora.block_mercado(snap)
        self.assertIn("| Con mercado propio | 2 | 8,62 |", out)
        self.assertIn("| Con el puesto gratuito | 1 | 7,50 |", out)
        self.assertIn("t03 (4,75)", out)
        self.assertIn("t03 2 mercados, 0 tratos", out)

    def test_rank_series_are_kept_per_metric(self):
        d = {"ranking": []}
        bitacora.note_rank(d, {"metric": "neg", "ts": 0, "tick": 1, "round": 2, "rank": 1, "score": 20})
        bitacora.note_rank(d, {"metric": "total", "ts": 1, "tick": 1, "round": 2, "rank": 8, "score": 27})
        bitacora.note_rank(d, {"metric": "neg", "ts": 2, "tick": 2, "round": 2, "rank": 1, "score": 21})
        self.assertEqual([(r["metric"], r["rank"]) for r in d["ranking"]], [("neg", 1), ("total", 8)])


if __name__ == "__main__":
    unittest.main()
