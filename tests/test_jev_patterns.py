from dataclasses import asdict
from pathlib import Path
import subprocess
import sys
import unittest

from harness.dealer_history import summarize_public_history
from harness.jev_patterns import LABELS, evaluate_patterns, pattern_batches
from harness.jev_security import JevBlocked, PATTERN_QUESTIONS, RequestBudget, secure_request
from harness.retrieval import MemoryCase


def fixtures():
    return [MemoryCase(oid, 'chato' if oid == 'note-chato188' else 'abuela', 'buy',
                       'SAL-02', 'negotiation', 'Observed historical price sequence.',
                       'synthetic', 'synthetic', 10) for oid in LABELS]


class PatternTests(unittest.TestCase):
    def test_cli_verifies_public_fixture_without_model_key_or_network(self):
        script = Path(__file__).resolve().parents[1] / 'run_jev_patterns.py'
        result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('9 solicitudes, 63 preguntas. Sin red.', result.stdout)

    def test_closed_plan_repeats_three_cases_without_sending_labels(self):
        batches = pattern_batches(fixtures())
        self.assertEqual(len(batches), 9)
        self.assertEqual(len({b['query_id'] for b in batches}), 9)
        for batch in batches:
            req = secure_request(batch)
            self.assertEqual(set(req['questions']), set(PATTERN_QUESTIONS))
            self.assertNotIn('expected', req['state'])
            self.assertNotIn('labels', req['state'])
        with self.assertRaises(JevBlocked):
            pattern_batches(fixtures(), 4)
        with self.assertRaises(JevBlocked):
            pattern_batches([])

    def test_evaluation_counts_distinct_cases_and_repetitions_separately(self):
        class FakeClient:
            budget = RequestBudget()
            def evaluate(self, batch):
                self.budget.reserve(100)
                return {'status': 'evaluated', 'scores': dict(zip(PATTERN_QUESTIONS,
                        [0.8 if x else 0.1 for x in LABELS[batch['case_id']]])),
                        'usage': {'input_tokens': 10, 'output_tokens': 1, 'cost_usd': 0}}
        r = evaluate_patterns(fixtures(), FakeClient())
        self.assertEqual((r['distinct_cases'], r['evaluated_questions'], r['correct_at_05']), (3, 63, 63))
        self.assertTrue(all(c['consistent_binary_decisions'] for c in r['per_case'].values()))

    def test_pattern_failure_stops_following_requests(self):
        class BrokenClient:
            budget = RequestBudget()
            def evaluate(self, batch):
                self.budget.reserve(100)
                raise JevBlocked('provider_unavailable')
        r = evaluate_patterns(fixtures(), BrokenClient())
        self.assertEqual(r['real_model_requests_attempted'], 1)
        self.assertEqual(r['evaluated_questions'], 0)
        self.assertFalse(r['completed'])

    def test_unknown_purpose_and_multiple_cases_are_blocked(self):
        b = pattern_batches(fixtures())[0]
        b['purpose'] = 'execute'
        with self.assertRaisesRegex(JevBlocked, 'unknown_purpose'):
            secure_request(b)
        b['purpose'] = 'pattern_check'
        b['request']['state']['candidates'] = []
        b['candidate_ids'] = []
        with self.assertRaisesRegex(JevBlocked, 'pattern_requires_one_case'):
            secure_request(b)

    def test_public_summary_does_not_join_similar_price_settlements_or_read_private_events(self):
        def event(oid, scope, team):
            return {'id': oid, 'tick': oid, 'scope': scope, 'type': 'settlement',
                    'payload': {'persona': 'abuela', 'settlement': oid, 'parties': ['abuela', team],
                                'price': 19, 'items': [{'ref': 'sobre_barrio', 'frm': 'abuela', 'to': team}]}}
        r = summarize_public_history([event(1, 'public', 't18'), event(2, 'public', 't7'), event(3, 'private', 't9')])
        self.assertEqual((r['our_settlements'], r['rival_settlements'], r['settlement_thread_joins']), (1, 1, 0))
        self.assertEqual(r['settlement_groups'][0]['count'], 2)
        self.assertFalse(r['opponent_private_values_available'])
