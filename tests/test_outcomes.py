from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from agent import journal, trace
from agent.contracts import Paths
from agent.execution import writer_lock
from harness import outcomes
from harness.retrieval import MemoryIndex, Scope, import_feed
import run_traces

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRED = {'neg_lo': 0.0, 'neg_hi': 0.0, 'ladder': '>=0', 'cash': -9}


def measure(ids, **over):
    row = {'ids': ids, 'pred': PRED, 'meas': {'neg': 0.0, 'ladder': 0.012, 'duel': 0.0}, 'verdict': 'pass',
           'tick': 30, 'opened': 29, 'tactics': ['dealers'], 'kinds': ['dealer'], 'sources': {'harness': 1},
           'ambiguous': False, 'dealers': ['abuela'], 'day': 'sat', 'surprise': 0.0}
    row.update(over)
    return row


class OutcomeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='t18-outcomes-'))
        self.logs = self.root / 'logs'
        lock = writer_lock(Paths.at(self.root))
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)
        self.j = journal.Journal(self.logs / 'run' / 'journal.jsonl', mode='live')
        self.j.write('tick', tick=20, cash=300, cash_free=200, armed=['dealers'], down=[])

    def dealer_deal(self, tid=41, ref='RET-01', price=9, sent=True, **meas):
        self.j.write('intent', id='open-1', tactic='dealers', intent_kind='open_thread', tick=20,
                     args={'dealer': 'abuela', 'side': 'buy', 'ref': ref, 'asset_ids': [], 'limit': 11},
                     reason='RET a 9/10', prediction=PRED)
        self.j.write('result', id='open-1', status='ok', response={'id': tid})
        self.j.write('intent', id='say-1', tactic='dealers', intent_kind='say', tick=28,
                     args={'thread_id': tid, 'ref': ref, 'price': price, 'template': 'a', 'variant': 0},
                     reason='paso +1', prediction=PRED)
        if sent:
            self.j.write('result', id='say-1', status='ok', response={'status': 'queued'})
        self.j.write('measure', **measure(['say-1'], **meas))

    def cases(self):
        return outcomes.outcome_cases(*outcomes.load(str(self.logs)))

    def test_http_ok_without_a_measured_settlement_is_never_an_outcome(self):
        self.j.write('intent', id='acc-1', tactic='rastro', intent_kind='accept', tick=21,
                     args={'offer_id': 7, 'source': 'team', 'ref': 'MAL-01', 'side': 'sell', 'price': 9,
                           'thread_id': None, 'give_asset': 3, 'fingerprint': 'f', 'resupply': False,
                           'venue': 'rastro'}, reason='venta', prediction=PRED)
        self.j.write('result', id='acc-1', status='ok', response={'status': 'queued'})
        cases, report = self.cases()
        self.assertEqual((cases, report['measures'], report['indexed']), ([], 0, 0))

    def test_measured_dealer_deal_becomes_one_private_case_merged_with_the_public_thread(self):
        self.dealer_deal()
        cases, report = self.cases()
        self.assertEqual((report['chain_valid'], report['indexed']), (True, 1))
        c = cases[0]
        self.assertEqual((c.id, c.dealer, c.side, c.item, c.phase, c.visibility),
                         ('thread-41', 'abuela', 'buy', 'RET-01', 'settled', 'local-team'))
        body = json.loads(c.body)
        self.assertEqual((body['price'], body['measured_ladder'], body['verdict']), (9, 0.012, 'pass'))

        feed = [{'id': 1, 'tick': 25, 'scope': 'public', 'type': 'thread.opened',
                 'payload': {'thread': 41, 'with': 'abuela', 'topic': {'buy': {'card': 'RET-01'}}}},
                {'id': 2, 'tick': 28, 'scope': 'public', 'type': 'thread.message',
                 'payload': {'thread': 41, 'with': 'abuela', 'sender': 'abuela', 'text': 'vale',
                             'offer': {'give': {'types': ['card:RET-01']}, 'want': {'cash': 9}}}}]
        memory = trace.merge(import_feed(feed, 'feed')[0], cases)
        self.assertEqual([m.id for m in memory], ['thread-41'])
        index = MemoryIndex(memory)
        self.addCleanup(index.close)
        found, _ = index.retrieve('compra RET-01', Scope('abuela', 'buy', 'RET-01'))
        self.assertEqual([f['id'] for f in found], ['thread-41'])
        self.assertEqual(index.retrieve('compra RET-01', Scope('abuela', 'buy', 'RET-01', team='t05'))[0], [])

    def test_team_trade_is_keyed_by_intent_and_venue(self):
        self.j.write('intent', id='acc-2', tactic='rastro', intent_kind='accept', tick=21,
                     args={'offer_id': 8, 'source': 'team', 'ref': 'MAL-01', 'side': 'sell', 'price': 12,
                           'thread_id': None, 'give_asset': 3, 'fingerprint': 'f', 'resupply': False,
                           'venue': 'rastro'}, reason='venta', prediction=PRED)
        self.j.write('result', id='acc-2', status='ok', response={'status': 'queued'})
        self.j.write('measure', **measure(['acc-2'], dealers=[], kinds=['accept'], tactics=['rastro']))
        cases, _ = self.cases()
        self.assertEqual([(c.id, c.dealer, c.side, c.item) for c in cases],
                         [('outcome-acc-2', 'rastro', 'sell', 'MAL-01')])

    def test_ambiguous_inherited_unattributed_excluded_and_unsent_are_left_out(self):
        self.dealer_deal(ambiguous=True)
        self.j.write('measure', **measure(['say-1', 'x'], ambiguous=True))
        self.j.write('measure', **measure(['say-1'], sources={'harness': 1, 'inherited': 1}))
        self.j.write('measure', **measure(['say-1'], verdict='unattributed'))
        self.j.write('measure', **measure(['say-1'], verdict='excluded', pred=None, meas=None))
        _, report = self.cases()
        self.assertEqual(report['indexed'], 0)
        self.assertEqual(report['skipped'], {'ambiguous': 2, 'not_harness': 1, 'verdict:unattributed': 1,
                                             'verdict:excluded': 1})

    def test_intent_never_sent_is_not_labelled(self):
        self.dealer_deal(sent=False)
        cases, report = self.cases()
        self.assertEqual((cases, report['skipped']), ([], {'intent_not_sent': 1}))

    def test_broken_chain_indexes_nothing_and_check_fails(self):
        self.dealer_deal()
        with open(self.logs / 'run' / 'journal.jsonl', 'ab') as f:
            f.write(b'{"kind":"measure"}\n')  # a complete line that breaks seq/prev
        cases, report = self.cases()
        self.assertEqual((cases, report['chain_valid']), ([], False))
        self.assertIn('refused', report)
        out = subprocess.run([sys.executable, 'run_traces.py', '--check', '--logs', str(self.logs)], cwd=ROOT,
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 1)

    def test_viewer_state_reports_measured_cases_and_is_deterministic(self):
        self.dealer_deal()
        a, b = run_traces.state(str(self.logs)), run_traces.state(str(self.logs))
        self.assertEqual((a['memory']['measured_cases'], a['executor']['outcomes_indexed']), (1, 1))
        self.assertTrue(a['memory']['ids_unique'])
        self.assertEqual(a['outcomes'], b['outcomes'])
        self.assertEqual([asdict(c) for c in self.cases()[0]], [asdict(c) for c in self.cases()[0]])


if __name__ == '__main__':
    unittest.main()
