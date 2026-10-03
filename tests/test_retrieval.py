from dataclasses import asdict, replace
import json
from unittest import TestCase

from harness.rag_eval import evaluate_retrieval
from harness.jev_plan import prepare_reranking
from harness.retrieval import MemoryCase, MemoryIndex, Scope, contextual, import_feed, in_scope


def case(oid='good', **changes):
    c = MemoryCase(oid, 'chato', 'buy', 'LAT-06', 'repeated', 'offer 33 33 32',
                   'fixture#thread=1', 'synthetic', 10)
    return replace(c, **changes)


class RetrievalTests(TestCase):
    def test_filters_apply_before_top_k_even_if_other_records_have_better_terms(self):
        rows = [case(), case('dealer', dealer='abuela', body='offer offer offer'),
                case('side', side='sell'), case('private', visibility='another-team'),
                case('old', status='superseded'), case('version', version='unknown')]
        index = MemoryIndex(rows)
        self.addCleanup(index.close)
        for mode in ('recent_sql', 'scoped_fts', 'contextual_fts', 'fused_fts'):
            selected, _ = index.retrieve('offer', Scope('chato', 'buy', 'LAT-06'), mode=mode)
            self.assertEqual([c['id'] for c in selected], ['good'])
        selected, _ = index.retrieve('offer', Scope('chato', 'buy', 'LAT-06'), mode='global_fts', k=6)
        self.assertTrue(any(not in_scope(next(c for c in rows if c.id == p['id']), Scope('chato', 'buy', 'LAT-06')) for p in selected))

    def test_contextual_tags_help_spanish_query_without_claiming_semantic_embeddings(self):
        self.assertIn('Tick desconocido', contextual(case(tick=None)))
        index = MemoryIndex([case()])
        self.addCleanup(index.close)
        q, scope = 'estancamiento', Scope('chato', 'buy')
        self.assertEqual(index.retrieve(q, scope, mode='scoped_fts')[0], [])
        self.assertEqual(index.retrieve(q, scope, mode='contextual_fts')[0][0]['id'], 'good')

    def test_budget_omits_whole_evidence_and_keeps_source_when_it_fits(self):
        index = MemoryIndex([case(body='price 33 -> 32. ' * 100)])
        self.addCleanup(index.close)
        selected, skipped = index.retrieve('price', Scope('chato', 'buy'), byte_budget=80)
        self.assertEqual((selected, skipped), ([], 1))
        selected, _ = index.retrieve('price', Scope('chato', 'buy'), byte_budget=4000)
        self.assertEqual(selected[0]['source'], 'fixture#thread=1')
        self.assertEqual(selected[0]['body'], 'price 33 -> 32. ' * 100)
        self.assertEqual(selected[0]['authority'], 'historical_evidence_only')

    def test_query_operators_and_sql_are_not_executed(self):
        index = MemoryIndex([case()])
        self.addCleanup(index.close)
        index.retrieve('" OR 1=1; DROP TABLE cases; --', Scope('chato', 'buy'))
        selected, _ = index.retrieve('offer', Scope("chato' OR 1=1 --", 'buy'))
        self.assertEqual(selected, [])
        self.assertEqual(index.db.execute('SELECT count(*) FROM cases').fetchone()[0], 1)

    def test_import_does_not_join_settlement_to_thread_or_treat_missing_outcome_as_failure(self):
        events = [
            {'id':1,'tick':1,'scope':'public','type':'thread.opened','payload':{'thread':9,'with':'abuela','topic':{'buy':{'card':'SAL-02'}}}},
            {'id':2,'tick':2,'scope':'public','type':'thread.message','payload':{'thread':9,'with':'abuela','sender':'abuela','text':'offer','offer':{'give':{'types':['card:SAL-02']},'want':{'cash':9}}}},
            {'id':3,'tick':2,'scope':'public','type':'thread.message','payload':{'thread':9,'with':'abuela','sender':'t18','text':'fixture-secret','offer':{'give':{'cash':9},'want':{'types':['card:SAL-02']}}}},
            {'id':4,'tick':3,'scope':'public','type':'settlement','payload':{'persona':'abuela','settlement':10,'price':9,'items':[{'ref':'SAL-02','frm':'abuela','to':'t18'}]}},
            {'id':5,'tick':4,'scope':'private','type':'thread.message','payload':{'thread':99,'with':'abuela','text':'private'}}]
        rows, coverage = import_feed(events, 'fixture-feed')
        self.assertEqual(len(rows), 2)
        self.assertEqual(coverage['settlement_thread_joins'], 0)
        self.assertNotIn('fixture-secret', json.dumps([asdict(r) for r in rows]))
        thread = next(c for c in rows if c.id == 'thread-9')
        self.assertEqual(json.loads(thread.body)['outcome'], 'unknown_in_feed_window')
        self.assertEqual(next(c for c in rows if c.id == 'settlement-10').phase, 'settled')

    def test_labels_remain_outside_index_and_metrics_show_missing_evidence(self):
        rows = [case()]
        queries = [{'id':'q1','text':'estancamiento','scope':asdict(Scope('chato','buy')), 'relevant':['good']},
                   {'id':'q2','text':'offer','scope':asdict(Scope('abuela','buy')), 'relevant':[]}]
        report = evaluate_retrieval(rows, queries, repeats=2)
        self.assertEqual(report['results']['scoped_fts']['summary']['mean_recall_at_k'], 0)
        self.assertEqual(report['results']['contextual_fts']['summary']['mean_recall_at_k'], 1)
        self.assertGreater(report['results']['global_fts']['summary']['scope_violations'], 0)
        self.assertFalse(report['generation_evaluated'])
        self.assertFalse(report['embeddings_evaluated'])
        self.assertEqual(report['real_model_calls'], 0)
        queries[0]['relevant']=['missing']
        with self.assertRaises(ValueError):
            evaluate_retrieval(rows, queries)

    def test_jev_request_is_bounded_excludes_labels_and_has_no_execution_capability(self):
        q = {'id':'q1', 'text':'estancamiento', 'scope':asdict(Scope('chato','buy')), 'relevant':['good']}
        batches = prepare_reranking([case()], [q], shortlist=2)
        request = batches[0]['request']
        self.assertEqual(set(request), {'model','state','questions'})
        self.assertNotIn('relevant', request['state']['query'])
        self.assertEqual(request['questions']['evidence_0']['type'], 'noul')
        self.assertNotIn('api_key', json.dumps(request))
        self.assertEqual(len(request['state']['candidates']), 1)
