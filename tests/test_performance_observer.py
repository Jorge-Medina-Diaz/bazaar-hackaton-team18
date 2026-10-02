import json
from pathlib import Path
import tempfile
import unittest

from observe_performance import ChangeLog, Sampler, metrics


def state():
    return {'mode': 'live', 'tick': 109, 'checks': {'reloj': {'ok': True}}}


def me():
    return {'tick': 109, 'cash': 281, 'collection_value': 493.7, 'open_threads': [],
            'score': {'score': 22.16, 'rank': 3, 'neg_points': 73.2, 'ladder_points': 0.051},
            'key': 'MUST_NOT_BE_LOGGED'}


class ObservationTests(unittest.TestCase):
    def test_one_supplementary_read_per_tick_and_no_credentials_in_metrics(self):
        panel = state()
        reads = []
        def read_me():
            reads.append(1)
            return me()
        sampler = Sampler(lambda: panel, read_me)
        sampler.read(); sampler.read()
        self.assertEqual(len(reads), 1)
        panel['tick'] += 1
        sampler.read()
        self.assertEqual(len(reads), 2)
        self.assertNotIn('MUST_NOT_BE_LOGGED', str(sampler.cached))

    def test_embedded_metrics_use_no_extra_game_read(self):
        panel = {**state(), 'performance': metrics(me()),
                 'checks': {'reloj': {'ok': True}, 'inventario y saldo': {'ok': True}}}
        sampler = Sampler(lambda: panel, lambda: self.fail('Extra API read'))
        self.assertEqual(sampler.read()['source'], 'artifact')

    def test_failed_clock_prevents_supplementary_poll(self):
        panel = {**state(), 'checks': {'reloj': {'ok': False}}}
        with self.assertRaises(ValueError):
            Sampler(lambda: panel, lambda: self.fail('Unnecessary API read')).read()

    def test_unchanged_snapshot_emits_no_new_log(self):
        with tempfile.TemporaryDirectory() as directory:
            log = ChangeLog(Path(directory) / 'observations.jsonl')
            p = metrics(me())
            log.observe(p)
            self.assertIsNone(log.observe({**p, 'observed_at': 'later'}))
            self.assertEqual(log.count, 1)

    def test_score_drop_without_resource_or_component_loss_is_distinguished(self):
        with tempfile.TemporaryDirectory() as directory:
            log = ChangeLog(Path(directory) / 'observations.jsonl')
            p = metrics(me()); log.observe(p)
            event = log.observe({**p, 'score': 21.77, 'rank': 4, 'tick': 110})
            self.assertIn('score_changed_without_measured_component_or_resource_change', event['flags'])
            self.assertEqual(event['delta']['cash'], 0)

    def test_rebound_can_coincide_with_worse_rank(self):
        with tempfile.TemporaryDirectory() as directory:
            log = ChangeLog(Path(directory) / 'observations.jsonl', reserve_cash=270)
            p = metrics(me()); log.observe(p)
            event = log.observe({**p, 'score': 22.2, 'rank': 5, 'cash': 268})
            self.assertIn('score_improved_but_relative_position_worsened', event['flags'])
            self.assertIn('cash_below_planned_reserve', event['flags'])
            saved = json.loads(log.path.read_text().splitlines()[-1])
            self.assertNotIn('MUST_NOT_BE_LOGGED', json.dumps(saved))
