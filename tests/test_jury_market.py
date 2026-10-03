"""Public market evidence stays separate from private profit and judge points."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jury import report
from tests.test_market_harness import fixture, event


def market_fixture():
    s = fixture()
    s['catalog'] = {'sets': []}
    s['captured_at'] = '2026-10-03T13:40:00Z'
    s['leaderboard'].update(snapshot_tick=100, round=2)
    trade = event(1, 101, 'settlement', {'settlement': 50, 'kind': 'trade', 'venue': 'rastro',
                 'parties': ['t18','t02'], 'price': 27, 'fee': 3,
                 'items': [{'kind':'card','ref':'RET-08','frm':'t18','to':'t02','secret':'do-not-export'}]})
    s['feed']['events'] = [trade]
    return s


class JuryMarket(unittest.TestCase):
    def test_price_and_score_do_not_become_profit_or_judge_points(self):
        r = report.market_summary(market_fixture())
        self.assertEqual(r['own_settlements'][0]['price'], 27)
        for k in ('private_profit','causal_score_effect','fee_payer'):
            self.assertIsNone(r['own_settlements'][0][k])
        self.assertIsNone(r['judge_score'])
        self.assertNotIn('do-not-export', json.dumps(r))

    def test_duplicate_settlement_not_multiple_results(self):
        s = market_fixture(); s['feed']['events'] += deepcopy(s['feed']['events'])
        self.assertEqual(report.market_summary(s)['own_settlements_in_window'], 1)

    def test_private_or_future_event_not_public_result(self):
        for mutate in (lambda e: e.update(scope='private'), lambda e: e.update(tick=102)):
            s = market_fixture(); mutate(s['feed']['events'][0])
            self.assertEqual(report.market_summary(s)['own_settlements_in_window'], 0)

    def test_disappearance_not_settlement(self):
        s = market_fixture(); s['feed']['events'] = []
        s['books']['rastro']['offers'] = []
        self.assertEqual(report.market_summary(s)['own_settlements_in_window'], 0)

    def test_partial_snapshot_opportunities_indeterminate(self):
        s = market_fixture(); s['errors']['v19'] = 'BazaarError'
        self.assertIsNone(report.market_summary(s)['compatible_pairs'])

    def test_demo_offline_uses_capture_and_marker_age(self):
        s = market_fixture()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'public.json'; p.write_text(json.dumps(s))
            with patch.object(report,'public_get',side_effect=AssertionError('network')), patch('builtins.print'):
                report.main(['--market-snapshot',str(p),'--output',d])
            r = json.loads((Path(d)/'evidence.json').read_text())
            self.assertEqual(r['fetched_at'],s['captured_at'])
            self.assertEqual(r['snapshot_tick'],100)
            self.assertEqual(r['leaderboard_freshness']['age_ticks'],1)
            self.assertEqual(r['market']['own_settlements_in_window'],1)
            self.assertNotIn('do-not-export',(Path(d)/'evidence.json').read_text())
            self.assertIn('market-trades',(Path(d)/'demo.html').read_text())

    def test_report_legacy_tick_and_future_private_affinity(self):
        s = market_fixture(); s['leaderboard'].pop('snapshot_tick')
        s['feed']['events'][0]['scope'] = 'private'
        r = report.make_report(**{k:s[k] for k in ('leaderboard','clock','feed','catalog')})
        self.assertEqual(r['snapshot_tick'],101)
        self.assertEqual(r['affinity']['events'],0)

    def test_missing_catalog_stops_instead_of_inventing_model_input(self):
        s = market_fixture(); s.pop('catalog')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'public.json';p.write_text(json.dumps(s))
            with self.assertRaisesRegex(ValueError,'catalog'):
                report.main(['--market-snapshot',str(p),'--output',d])


if __name__ == '__main__': unittest.main()
