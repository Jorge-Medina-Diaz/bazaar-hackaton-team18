"""Three manually checked historical cases; not model training or held-out data."""
from dataclasses import asdict
import hashlib
import json
from statistics import median

from harness.jev_security import JevBlocked, PATTERN_QUESTIONS
from harness.retrieval import Scope

# Derived from visible price sequences/text and explicit absence of linked settlement.
# Never included in requests: these are local evaluation labels, not model inputs.
LABELS = {
    'thread-68': (True, False, False, False, False, False, False),
    'note-chato188': (True, True, False, False, False, False, False),
    'thread-64': (True, False, True, False, False, False, False)}


def pattern_batches(cases, repeats=3):
    if type(repeats) is not int or not 1 <= repeats <= 3:
        raise JevBlocked('invalid_repeats')
    by_id = {c.id: c for c in cases}
    batches = []
    for repetition in range(1, repeats + 1):
        for oid in LABELS:
            if oid not in by_id:
                raise JevBlocked('missing_pattern_case')
            case = by_id[oid]
            scope = Scope(case.dealer, case.side, item=case.item, phase=case.phase)
            batches.append({'query_id': oid + '-rep' + str(repetition), 'case_id': oid,
                'purpose': 'pattern_check', 'repetition': repetition, 'candidate_ids': [oid],
                'request': {'state': {'query': {'text': 'Comprobar patrones y límites de evidencia de la negociación.',
                                              'scope': asdict(scope)}, 'candidates': [asdict(case)]}}})
    return batches


def evaluate_patterns(cases, client, repeats=3):
    from time import perf_counter
    batches = pattern_batches(cases, repeats)
    rows, stopped = [], False
    for batch in batches:
        t0 = perf_counter()
        row = {k: batch[k] for k in ('query_id', 'case_id', 'repetition')}
        if stopped:
            row.update(status='not_attempted_after_failure', error=None)
        else:
            try:
                row.update(client.evaluate(batch))
                expected = dict(zip(PATTERN_QUESTIONS, LABELS[batch['case_id']]))
                row['expected'] = expected
                row['correct_at_05'] = {k: (row['scores'][k] >= 0.5) == value for k, value in expected.items()}
                row['brier'] = sum((row['scores'][k] - int(value)) ** 2 for k, value in expected.items()) / len(expected)
            except JevBlocked as exc:
                row.update(status='blocked', error=str(exc))
                stopped = True
        row['elapsed_ms'] = round((perf_counter() - t0) * 1000, 3)
        rows.append(row)
    valid = [r for r in rows if r['status'] == 'evaluated']
    per_case = {}
    for oid in LABELS:
        group = [r for r in valid if r['case_id'] == oid]
        per_case[oid] = {'completed_repeats': len(group), 'score_ranges': {
            k: [min(r['scores'][k] for r in group), max(r['scores'][k] for r in group)]
            for k in PATTERN_QUESTIONS} if group else {},
            'consistent_binary_decisions': all(len({r['scores'][k] >= 0.5 for r in group}) == 1
                                               for k in PATTERN_QUESTIONS) if group else None}
    costs = [r['usage']['cost_usd'] for r in valid]
    correct = sum(sum(r['correct_at_05'].values()) for r in valid)
    total = len(valid) * len(PATTERN_QUESTIONS)
    return {'schema_version': 1, 'mode': 'live', 'scope': 'Three development cases, repeated; not training or generalization',
            'repeats': repeats, 'distinct_cases': len(LABELS), 'questions_per_case': len(PATTERN_QUESTIONS),
            'real_model_requests_attempted': client.budget.calls, 'evaluated_questions': total,
            'correct_at_05': correct, 'incorrect_at_05': total - correct,
            'mean_brier': sum(r['brier'] for r in valid) / len(valid) if valid else None,
            'median_request_ms': median(r['elapsed_ms'] for r in valid) if valid else None,
            'successful_cost_usd': sum(costs) if costs and all(c is not None for c in costs) else None,
            'completed': not stopped, 'real_game_operations': 0, 'per_case': per_case, 'rows': rows,
            'cases_sha256': hashlib.sha256(json.dumps([asdict(c) for c in cases if c.id in LABELS],
                                                     sort_keys=True).encode()).hexdigest()}
