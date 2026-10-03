"""Paired offline evaluation. Fixtures are synthetic; gains are not game scores."""
from collections import Counter
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import asdict
import hashlib
import inspect
import json
import math
from pathlib import Path
import platform
import random
import statistics
import subprocess
from time import perf_counter
from unittest.mock import patch

from bazaar_sdk import Bazaar
from harness.cases import fixtures
from harness.market import DecisionGate, baseline, candidate, propose
from harness.broker_sim import make_run, max_surplus, simulate

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def offline():
    """Catch accidental SDK/HTTP/socket calls. Not a sandbox for untrusted code."""
    with ExitStack() as stack:
        for target in ('urllib.request.urlopen', 'socket.create_connection',
                       'socket.socket.connect', 'socket.socket.connect_ex'):
            stack.enter_context(patch(target, side_effect=RuntimeError('Harness: network forbidden')))
        stack.enter_context(patch.object(Bazaar, '_call', side_effect=RuntimeError('Harness: SDK forbidden')))
        yield


class FakeMarket:
    def __init__(self, case):
        self.case = deepcopy(case)
        self.calls = Counter()

    def my_offers(self):
        self.calls['my_offers'] += 1
        return {'offers': deepcopy(self.case.mine)}

    def board(self, venue):
        if venue != 'rastro':
            raise AssertionError('Unexpected venue')
        self.calls['board'] += 1
        return {'offers': deepcopy(self.case.board)}

    def value(self, ref):
        self.calls['value'] += 1
        return {'your_value': self.case.values[ref]}

    def accept(self, *args, **kwargs):
        raise AssertionError('A selector must not write, even to the fake API')


def percentiles(samples):
    ordered = sorted(samples)
    return {'p50_ms': round(statistics.median(ordered), 4),
            'p95_ms': round(ordered[math.ceil(len(ordered) * .95) - 1], 4)}


def trial(policy, case):
    api = FakeMarket(case)
    me, clock = deepcopy(case.me), deepcopy(case.clock)
    error, choice = None, (0, None, None, None)
    started = perf_counter()
    try:
        choice = policy(api, me, clock)
        if not isinstance(choice, tuple) or len(choice) != 4:
            raise ValueError('Policy must return (gain, kind, offer, asset)')
        gain, kind, selected_offer, asset = choice
        if (type(gain) not in (int, float) or not math.isfinite(gain)
                or (kind is None and choice != (0, None, None, None))
                or (kind is not None and (kind not in ('BUY', 'SELL') or not isinstance(selected_offer, dict)
                                         or type(selected_offer.get('id')) is not int))):
            raise ValueError('Invalid choice contract')
        if (me, clock) != (case.me, case.clock):
            raise ValueError('Policy mutated input state')
    except Exception as exc:
        error = type(exc).__name__  # never include arbitrary exception text/secrets
        choice = (0, None, None, None)
    elapsed = (perf_counter() - started) * 1000
    selected = choice[2].get('id') if isinstance(choice[2], dict) else None
    payload_error = False
    if selected is not None:
        original = next((o for o in case.board + case.mine if o['id'] == selected), None)
        kind = 'BUY' if original and original.get('give', {}).get('assets') else 'SELL'
        sale_assets = [a['id'] for a in case.me['assets']
                       if original and 'card:' + a['ref'] in original.get('want', {}).get('types', [])]
        payload_error = (choice[2] != original or choice[1] != kind
                         or (kind == 'BUY' and choice[3] is not None)
                         or (kind == 'SELL' and choice[3] not in sale_assets))
    mismatch = selected != case.expected
    allowed = case.allowed_ids if case.allowed_ids is not None else (() if case.expected is None else (case.expected,))
    unsafe = selected is not None and (selected not in allowed or payload_error)
    gross_gain = 0
    if selected in allowed and not payload_error:
        price = original['want']['cash'] if kind == 'BUY' else original['give']['cash']
        charge = (price + 19) // 20 + 1  # oracle does not call the production fee function
        if kind == 'BUY':
            gross_gain = case.values[original['give']['assets'][0]['ref']] - price - charge
        else:
            asset = next(a for a in case.me['assets'] if a['id'] == choice[3])
            gross_gain = price - charge - asset['your_value']
    gain_error = selected in allowed and not payload_error and choice[0] != round(gross_gain, 1)
    gain = gross_gain if not error and not gain_error and not unsafe else 0
    # Every fixture is an independent two-tick window: decide, then settle (or abstain).
    return dict(case=case.name, selected=selected, expected=case.expected, simulated_net_gain=gain,
                simulated_ticks=2, unsafe_selection=unsafe, oracle_mismatch=mismatch,
                gain_error=gain_error, payload_error=payload_error, oracle_regret=max(0, case.expected_gain - gain),
                exception=error, calls=dict(api.calls), local_ms=elapsed,
                max_value_calls=case.max_value_calls)


def evaluate_policy(policy, cases, repeats, fake_api_ms):
    rows, latencies, call_totals = [], [], Counter()
    for case in cases:
        row = trial(policy, case)
        samples = [row['local_ms']]
        for _ in range(repeats - 1):
            replay = trial(policy, case)
            if {k: v for k, v in replay.items() if k != 'local_ms'} != {k: v for k, v in row.items() if k != 'local_ms'}:
                row['exception'] = 'NonDeterministicPolicy'
            samples.append(replay['local_ms'])
        row.pop('local_ms')
        if row['exception'] == 'NonDeterministicPolicy':
            row['simulated_net_gain'] = 0
            row['oracle_regret'] = case.expected_gain
        row.update(percentiles(samples))
        row['simulated_sequential_read_ms'] = sum(row['calls'].values()) * fake_api_ms
        row['read_budget_exceeded'] = row['calls'].get('value', 0) > case.max_value_calls
        call_totals.update(row['calls'])
        latencies.extend(samples)
        rows.append(row)
    gain, ticks = sum(r['simulated_net_gain'] for r in rows), sum(r['simulated_ticks'] for r in rows)
    summary = dict(cases=len(rows), simulated_net_gain=round(gain, 2), simulated_ticks=ticks,
                   simulated_gain_per_tick=round(gain / ticks, 4), calls=dict(call_totals),
                   unsafe_selections=sum(r['unsafe_selection'] for r in rows),
                   oracle_mismatches=sum(r['oracle_mismatch'] for r in rows),
                   gain_errors=sum(r['gain_error'] for r in rows),
                   oracle_regret=round(sum(r['oracle_regret'] for r in rows), 2),
                   payload_errors=sum(r['payload_error'] for r in rows),
                   exceptions=sum(r['exception'] is not None for r in rows),
                   read_budget_failures=sum(r['read_budget_exceeded'] for r in rows),
                   simulated_read_ms_per_decision=round(sum(call_totals.values()) * fake_api_ms / len(rows), 3),
                   **percentiles(latencies))
    summary['passed'] = not any(summary[k] for k in ('unsafe_selections', 'oracle_mismatches',
                                                     'gain_errors', 'payload_errors', 'exceptions', 'read_budget_failures'))
    return {'summary': summary, 'cases': rows}


def gate_checks():
    c = fixtures(runs=0)[0]
    choice = candidate(FakeMarket(c), c.me, c.clock)
    p = propose(choice, c.me, c.clock, c.mine, c.board, c.values)
    results = []

    def check(name, got, expected):
        results.append(dict(case=name, passed=got == expected, actual=got, expected=expected))

    def authorize(gate, proposal=p, case=c):
        return gate.authorize(proposal, case.me, case.clock, case.mine, case.board, case.values)

    gate = DecisionGate()
    check('first_intent_reserved', authorize(gate), (True, 'reserved'))
    check('second_teammate_same_state', authorize(gate), (False, 'pending_reconciliation'))
    # This also represents an unknown POST timeout: do not retry without a terminal observation.
    check('unknown_post_no_retry', authorize(gate), (False, 'pending_reconciliation'))
    gate.reconcile(1, 'settled')
    check('quota_after_settlement', authorize(gate), (False, 'accept_quota'))
    for name, mutate, reason in [
        ('late_model_response', lambda x: x.clock.update(tick=11), 'late_tick'),
        ('offer_price_changed', lambda x: x.board[0]['want'].update(cash=30), 'state_changed'),
        ('cash_spent_by_teammate', lambda x: x.me.update(cash=150), 'state_changed'),
        ('private_value_changed', lambda x: x.values.update({'SAL-01': 1}), 'state_changed'),
        ('offer_cancelled', lambda x: x.board[0].update(status='cancelled'), 'state_changed'),
        ('clock_paused', lambda x: x.clock.update(paused=True), 'state_changed'),
        ('quota_changed', lambda x: x.clock['limits'].update(accepts_per_team_per_tick=0), 'state_changed')]:
        changed = deepcopy(c)
        mutate(changed)
        check(name, authorize(DecisionGate(), case=changed), (False, reason))
    bad = propose((99, 'BUY', c.board[0], None), c.me, c.clock, c.mine, c.board, c.values)
    check('model_invents_gain', authorize(DecisionGate(), proposal=bad), (False, 'invalid_choice'))
    changed = deepcopy(c)
    changed.clock['tick'] = 11
    fresh = propose(choice, changed.me, changed.clock, changed.mine, changed.board, changed.values)
    check('fresh_tick_after_reconciliation', authorize(gate, fresh, changed), (True, 'reserved'))
    return {'passed': all(r['passed'] for r in results), 'cases': results,
            'scope': 'Experimental gate only; run_loop does not yet use this arbiter. No distributed coordination.'}


def broker_checks(seed, runs):
    rng = random.Random(seed)
    gains, pairs = Counter(), []
    for r in range(runs):
        traders = make_run(rng, f'b{r}')
        possible = max_surplus(traders)
        row = {'run': r, 'max_possible': possible}
        for policy in ('greedy', 'broker', 'wait'):
            row[policy] = simulate(deepcopy(traders), policy, True)
            gains[policy] += row[policy]
        gains['max_possible'] += possible
        pairs.append(row)
    denominator = gains['max_possible']
    return {'runs': runs, 'seed': seed,
            'policies': {k: {'simulated_surplus': gains[k],
                            'simulated_gain_per_tick': round(gains[k] / (16 * runs), 4),
                            'efficiency': round(gains[k] / denominator, 4) if denominator else None}
                         for k in ('greedy', 'broker', 'wait')},
            'paired_runs': pairs,
            'scope': 'Existing sim_bench assumptions; synthetic hidden limits never passed to broker.plan. Not a promotion gate.'}


def revision():
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()
    # Includes uncommitted harness sources; a Git SHA alone would not identify this experiment.
    paths = [ROOT / 'run_harness.py', *sorted((ROOT / 'harness').glob('*.py'))]
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return dict(commit=commit, branch=branch, dirty=bool(dirty), source_sha256=digest.hexdigest())


def evaluate(*, seed=7, runs=100, repeats=10, fake_api_ms=100, candidate_policy=candidate):
    if type(runs) is not int or runs < 1 or type(repeats) is not int or repeats < 1:
        raise ValueError('runs and repeats must be positive integers')
    if type(seed) is not int or type(fake_api_ms) not in (int, float) or not math.isfinite(fake_api_ms) or fake_api_ms < 0:
        raise ValueError('Invalid seed or synthetic API latency')
    started = perf_counter()
    cases = fixtures(seed, runs)
    fixture_hash = hashlib.sha256(json.dumps([asdict(c) for c in cases], sort_keys=True).encode()).hexdigest()
    with offline():
        policies = {name: evaluate_policy(fn, cases, repeats, fake_api_ms)
                    for name, fn in [('current_run_loop', baseline), ('experimental_candidate', candidate_policy)]}
        gates = gate_checks()
        broker = broker_checks(seed, runs)
    return {'schema_version': 1, 'passed': policies['experimental_candidate']['summary']['passed'] and gates['passed'],
            'metadata': {**revision(), 'python': platform.python_version(), 'platform': platform.platform(),
                         'seed': seed, 'runs': runs, 'repeats': repeats, 'fixtures_sha256': fixture_hash,
                         'fake_api_read_ms': fake_api_ms,
                         'candidate': candidate_policy.__module__ + ':' + candidate_policy.__name__,
                         'candidate_source_sha256': hashlib.sha256(Path(inspect.getsourcefile(candidate_policy)).read_bytes()).hexdigest()},
            'scope': {'data': 'synthetic', 'real_api_calls': 0, 'real_model_calls': 0,
                      'model_tokens': None, 'model_cost': None, 'rag_evaluated': False, 'jev_evaluated': False,
                      'gain_unit': 'synthetic private value net of fees',
                      'latency': 'local fake-client time; simulated read latency reported separately',
                      'coverage': 'market selector, experimental arbiter, existing broker simulator',
                      'not_covered': ['dealer persuasion', 'full run_loop orchestration', 'multi-machine execution',
                                      'HTTP failures/rate-limit scheduling', 'real settlement', 'leaderboard score']},
            'market': policies, 'execution_gate': gates, 'broker': broker,
            'comparison': {'paired_cases': len(cases),
                           'simulated_gain_delta': round(policies['experimental_candidate']['summary']['simulated_net_gain']
                                                       - policies['current_run_loop']['summary']['simulated_net_gain'], 2),
                           'read_reduction_fraction': round(1 - sum(policies['experimental_candidate']['summary']['calls'].values())
                                                            / sum(policies['current_run_loop']['summary']['calls'].values()), 4)},
            'duration_seconds': round(perf_counter() - started, 4)}
