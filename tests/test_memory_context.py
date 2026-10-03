"""Regression cases: context boundaries and replay never borrow future evidence."""
from dataclasses import asdict, replace
import json
import unittest

from harness.dealer_history import summarize_public_history
from harness.jev_security import JevBlocked, secure_request
from harness.jev_plan import prepare_reranking
from harness.retrieval import MemoryCase, MemoryIndex, Scope, import_feed, in_scope


class ContextTests(unittest.TestCase):
    def case(self, oid='current', **kw):
        return replace(MemoryCase(oid, 'pilar', 'sell', 'SAL-01', 'negotiation', 'precio 12',
                                  'fixture', 'synthetic', 20, version='oct3-observations',
                                  round=2, regime='normal'), **kw)

    def test_round_regime_version_privacy_and_future_are_filtered_before_ranking(self):
        good = self.case()
        rows = [good, self.case('round', round=1), self.case('fever', regime='sal-fever'),
                self.case('future', tick=21), self.case('unknown-time', tick=None),
                self.case('unknown-round', round=None), self.case('private', visibility='t05'),
                self.case('old', version='oct2-observations')]
        index = MemoryIndex(rows)
        self.addCleanup(index.close)
        scope = Scope('pilar', 'sell', version='oct3-observations', round=2,
                      regime='normal', as_of_tick=20)
        for mode in ('recent_sql', 'scoped_fts', 'contextual_fts', 'fused_fts'):
            with self.subTest(mode=mode):
                selected, _ = index.retrieve('precio', scope, mode=mode, k=1)
                self.assertEqual([c['id'] for c in selected], ['current'])
        self.assertEqual([c.id for c in rows if in_scope(c, scope)], ['current'])

    def test_old_serialized_cases_and_scopes_remain_compatible(self):
        old = asdict(self.case(version='oct2-observations'))
        old.pop('round'); old.pop('regime')
        index = MemoryIndex([MemoryCase(**old)])
        self.addCleanup(index.close)
        self.assertEqual(len(index.retrieve('precio', Scope('pilar', 'sell'))[0]), 1)
        self.assertEqual(index.retrieve('precio', Scope('pilar', 'sell', round=2))[0], [])

    def test_secure_request_revalidates_new_context_and_old_packets(self):
        q = {'id': 'new', 'text': 'precio', 'scope': asdict(Scope('pilar', 'sell',
             version='oct3-observations', round=2, regime='normal', as_of_tick=20))}
        batch = prepare_reranking([self.case()], [q])[0]
        req = secure_request(batch)
        self.assertEqual(req['state']['candidates'][0]['round'], 2)
        batch['request']['state']['candidates'][0]['regime'] = 'sal-fever'
        with self.assertRaises(JevBlocked):
            secure_request(batch)
        oldq = {'id': 'old', 'text': 'precio', 'scope': {'dealer': 'pilar', 'side': 'sell'}}
        old = prepare_reranking([self.case(version='oct2-observations')], [oldq])[0]
        for key in ('round', 'regime'):
            old['request']['state']['candidates'][0].pop(key)
        self.assertEqual(len(secure_request(old)['state']['candidates']), 1)

    def test_unknown_round_and_replay_limits_are_rejected(self):
        for kw in ({'round': True}, {'round': 0}, {'as_of_tick': -1}, {'as_of_tick': True}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                Scope('pilar', 'sell', **kw)


def events(dealer='pilar'):
    return [
        {'id': 1, 'tick': 10, 'scope': 'public', 'type': 'thread.opened',
         'payload': {'thread': 1, 'with': dealer, 'topic': {'sell': {'assets': [2]}}}},
        {'id': 2, 'tick': 11, 'scope': 'public', 'type': 'thread.message',
         'payload': {'thread': 1, 'with': dealer, 'sender': dealer, 'text': 'precio',
                     'offer': {'give': {'cash': 12}, 'want': {'types': ['card:SAL-01']}}}},
        {'id': 3, 'tick': 12, 'scope': 'public', 'type': 'thread.message',
         'payload': {'thread': 1, 'with': dealer, 'sender': dealer, 'text': 'final',
                     'offer': {'give': {'cash': 14}, 'want': {'types': ['card:SAL-01']}, 'final': True}}},
        {'id': 4, 'tick': 13, 'scope': 'public', 'type': 'settlement',
         'payload': {'persona': dealer, 'settlement': 9, 'price': 14, 'parties': ['t18', dealer],
                     'items': [{'ref': 'SAL-01', 'frm': 't18', 'to': dealer}]}}]


class ImportTests(unittest.TestCase):
    def test_pilar_and_picaros_are_indexed_as_sales_with_explicit_context(self):
        for dealer in ('pilar', 'picaros'):
            with self.subTest(dealer=dealer):
                cases, report = import_feed(events(dealer), 'fixture', round=2, regime='normal')
                self.assertEqual(report['settlement_thread_joins'], 0)
                self.assertEqual([(c.dealer, c.side, c.item, c.version, c.round, c.regime) for c in cases],
                                 [(dealer, 'sell', 'SAL-01', 'oct3-observations', 2, 'normal')] * 2)
                self.assertEqual(summarize_public_history(events(dealer))['our_settlements'], 1)

    def test_replay_builds_only_prefix_no_final_no_settlement_no_future_price(self):
        cases, report = import_feed(events(), 'fixture', as_of_tick=11)
        self.assertEqual(report['settlements'], 0)
        self.assertEqual(len(cases), 1)
        body = json.loads(cases[0].body)
        self.assertEqual((cases[0].phase, cases[0].tick), ('negotiation', 11))
        self.assertEqual(body['dealer_prices'], [12])
        self.assertEqual(body['outcome'], 'unknown_in_feed_window')

    def test_zero_price_is_not_lost_and_unknown_regime_is_not_guessed(self):
        data = events()[:2]
        data[1]['payload']['offer']['give']['cash'] = 0
        cases, _ = import_feed(data, 'fixture')
        self.assertEqual(json.loads(cases[0].body)['dealer_prices'], [0])
        self.assertEqual((cases[0].round, cases[0].regime), (None, 'unknown'))


if __name__ == '__main__':
    unittest.main()
