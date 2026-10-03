from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from unittest import TestCase
import urllib.request

from bazaar_sdk import Bazaar
from harness.cases import Case, fixtures
from harness.market import DecisionGate, baseline, candidate, propose
from harness.runner import FakeMarket, evaluate, gate_checks, offline, trial


def forged_payload(api, me, clock):
    choice = candidate(api, me, clock)
    if choice[2]:
        choice[2]['want']['cash'] = 999  # same ID and claimed gain; actual cash field is wrong
    return choice


def wrong_shape(api, me, clock):
    return ()


class HarnessTests(TestCase):
    def test_current_cache_defect_is_measured_without_changing_gain(self):
        case = next(c for c in fixtures(runs=0) if c.name == 'same_card_ten_offers')
        old, new = trial(baseline, case), trial(candidate, case)
        self.assertEqual((old['calls']['value'], new['calls']['value']), (10, 1))
        self.assertEqual((old['simulated_net_gain'], new['simulated_net_gain']), (13, 13))

    def test_valid_alternative_is_selected_instead_of_unsafe_high_gain(self):
        case = next(c for c in fixtures(runs=0) if c.name == 'valid_alternative_to_expired')
        old, new = trial(baseline, case), trial(candidate, case)
        self.assertTrue(old['unsafe_selection'])
        self.assertEqual((old['simulated_net_gain'], new['simulated_net_gain']), (0, 8))

    def test_safe_but_suboptimal_choice_is_credited_with_its_actual_gain(self):
        case = next(c for c in fixtures(runs=0) if c.name == 'choose_cheapest')
        def choose_expensive(api, me, clock):
            return 8, 'BUY', api.board('rastro')['offers'][0], None
        result = trial(choose_expensive, case)
        self.assertFalse(result['unsafe_selection'])
        self.assertTrue(result['oracle_mismatch'])
        self.assertEqual((result['simulated_net_gain'], result['oracle_regret']), (8, 5))

    def test_oracle_does_not_credit_a_forged_offer_with_correct_id(self):
        result = trial(forged_payload, Case('forged'))
        self.assertTrue(result['payload_error'])
        self.assertEqual(result['simulated_net_gain'], 0)

    def test_malformed_adapter_is_a_failure_in_report_not_a_runner_crash(self):
        result = trial(wrong_shape, Case('wrong_shape'))
        self.assertEqual(result['exception'], 'ValueError')
        self.assertEqual(result['simulated_net_gain'], 0)
        result = trial(lambda api, me, clock: (13, 'BUY', None, None), Case('missing_offer'))
        self.assertEqual(result['exception'], 'ValueError')

    def test_live_sdk_and_http_calls_are_blocked(self):
        with offline():
            with self.assertRaisesRegex(RuntimeError, 'SDK forbidden'):
                Bazaar('https://invalid.example', 'fixture-key').me()
            with self.assertRaisesRegex(RuntimeError, 'network forbidden'):
                urllib.request.urlopen('https://invalid.example')

    def test_seed_reproduces_fixtures_and_changes_prices_for_other_seed(self):
        a, b, c = fixtures(7, 8), fixtures(7, 8), fixtures(8, 8)
        self.assertEqual(a, b)
        self.assertNotEqual(a[-8:], c[-8:])

    def test_all_named_edge_cases_and_seeded_choices_have_known_answers(self):
        for case in fixtures(23, 20):
            with self.subTest(case=case.name):
                result = trial(candidate, case)
                self.assertIsNone(result['exception'])
                self.assertFalse(result['oracle_mismatch'])
                self.assertFalse(result['payload_error'])
                self.assertLessEqual(result['calls'].get('value', 0), case.max_value_calls)

    def test_uncertain_write_reserves_asset_until_reconciled_even_next_tick(self):
        c = next(x for x in fixtures(runs=0) if x.name == 'sell_duplicate')
        trade = candidate(FakeMarket(c), c.me, c.clock)
        gate = DecisionGate()
        def submit(case):
            p = propose(trade, case.me, case.clock, case.mine, case.board, case.values)
            return gate.authorize(p, case.me, case.clock, case.mine, case.board, case.values)
        self.assertEqual(submit(c), (True, 'reserved'))
        following = deepcopy(c)
        following.clock['tick'] += 1
        self.assertEqual(submit(following), (False, 'pending_reconciliation'))
        with self.assertRaises(ValueError):
            gate.reconcile(1, 'unknown')
        self.assertEqual(submit(following), (False, 'pending_reconciliation'))
        gate.reconcile(1, 'failed')
        self.assertEqual(submit(following), (True, 'reserved'))

    def test_gate_rejects_late_verdicts_resource_changes_and_teammate_conflicts(self):
        report = gate_checks()
        self.assertTrue(report['passed'], report['cases'])
        self.assertEqual(len(report['cases']), 13)

    def test_regressed_adapter_cannot_receive_pass_even_if_runner_itself_works(self):
        report = evaluate(runs=2, repeats=1, candidate_policy=baseline)
        self.assertFalse(report['passed'])
        self.assertGreater(report['market']['experimental_candidate']['summary']['unsafe_selections'], 0)

    def test_report_keeps_economics_safety_calls_and_timing_separate(self):
        report = evaluate(runs=3, repeats=2)
        self.assertTrue(report['passed'])
        self.assertEqual(report['comparison']['simulated_gain_delta'], 21)
        self.assertGreater(report['comparison']['read_reduction_fraction'], 0)
        self.assertEqual(report['scope']['real_model_calls'], 0)
        self.assertIsNone(report['scope']['model_cost'])
        self.assertFalse(report['scope']['jev_evaluated'])
        summary = report['market']['experimental_candidate']['summary']
        self.assertEqual(summary['simulated_ticks'], 2 * summary['cases'])
        self.assertEqual(len(report['metadata']['source_sha256']), 64)
        self.assertEqual(len(report['metadata']['fixtures_sha256']), 64)

    def test_cli_json_can_be_consumed_as_one_report_without_extra_stdout(self):
        root = Path(__file__).resolve().parents[1]
        process = subprocess.run([sys.executable, str(root / 'run_harness.py'), '--runs', '2', '--repeats', '1', '--json'],
                                 cwd=root, text=True, capture_output=True, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        report = json.loads(process.stdout)
        self.assertTrue(report['passed'])
