import unittest
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from market_harness.core import analyze, brief, leaderboard_age
from market_harness.__main__ import main
from tests.test_market_harness import fixture


class MarketFreshness(unittest.TestCase):
    def test_scoreboard_tick_not_clock_tick(self):
        s = fixture(); s['leaderboard'].update(snapshot_tick=95, tick=101, round=2)
        self.assertEqual(leaderboard_age(s), {'tick': 95, 'age_ticks': 6, 'status': 'lagged', 'round': 2})
        self.assertIn('Marcador tick 95', brief(analyze(s)))

    def test_legacy_tick_fallback(self):
        s = fixture(); s['leaderboard']['tick'] = 100
        self.assertEqual(leaderboard_age(s)['age_ticks'], 1)

    def test_missing_future_and_boolean_ticks(self):
        s = fixture()
        s['leaderboard'].pop('tick')
        self.assertEqual(leaderboard_age(s)['status'], 'unknown')
        s['leaderboard']['snapshot_tick'] = 102
        self.assertEqual(leaderboard_age(s)['status'], 'future_inconsistent')
        s['leaderboard']['snapshot_tick'] = True
        self.assertEqual(leaderboard_age(s)['status'], 'unknown')

    def test_new_round_or_reverse_scoreboard_not_comparable(self):
        old, new = fixture(), fixture()
        old['leaderboard'].update(snapshot_tick=100, round=2)
        new['leaderboard'].update(snapshot_tick=101, round=3)
        self.assertIsNone(analyze(new, previous=old)['teams'][0]['score_delta'])
        new['leaderboard'].update(snapshot_tick=99, round=2)
        self.assertIsNone(analyze(new, previous=old)['teams'][0]['score_delta'])

    def test_alternative_quotes_group_without_losing_ids(self):
        s = fixture(); alt = deepcopy(s['books']['rastro']['offers'][0]); alt['id'] = 55
        s['books']['rastro']['offers'].append(alt)
        r = analyze(s)
        self.assertEqual(len(r['opportunities']), 2)
        self.assertEqual(len(r['opportunity_groups']), 1)
        self.assertEqual({p['ask_id'] for p in r['opportunity_groups'][0]['equivalent_pairs']}, {3,55})

    def test_incomplete_scan_not_zero_compatible(self):
        s = fixture(); s['errors'] = {'v19':'BazaarError'}
        r = analyze(s)
        self.assertIsNone(r['compatible_count'])
        self.assertIn('indeterminado', brief(r))

    def test_failed_archive_preserves_new_capture_and_previous_latest(self):
        old, current = fixture(), fixture()
        current['clock'] = {}  # Failed final clock cannot become a valid archive frame.
        with tempfile.TemporaryDirectory() as d:
            latest = Path(d)/'snapshot.json'; latest.write_text(json.dumps(old))
            with patch('market_harness.__main__.collect',return_value=current), self.assertRaises(ValueError):
                main(['refresh','--out',d])
            self.assertEqual(json.loads(latest.read_text()),old)
            captures = list(Path(d).glob('snapshot-*.json'))
            self.assertEqual(len(captures),1)
            self.assertEqual(json.loads(captures[0].read_text()),current)


if __name__ == '__main__': unittest.main()
