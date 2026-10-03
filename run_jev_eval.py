"""Bounded Jev reranking pilot. Simulated by default, never trades."""
import argparse
import json
import os
from pathlib import Path
import stat
import tempfile
from time import perf_counter

from harness.jev_plan import prepare_reranking
from harness.jev_security import JevBlocked, JevClient, RequestBudget, _encoded, secure_request, validate_response
from harness.retrieval import MemoryCase


def load_key(path):
    if path is None:
        value = os.environ.get('OPENROUTER_API_KEY', '')
        if not value:
            raise JevBlocked('missing_key')
        return value
    # Keys must live outside the checkout, in a regular owner-only local file.
    root = Path(__file__).resolve().parent
    resolved = path.resolve()
    if resolved.is_relative_to(root) or path.is_symlink():
        raise JevBlocked('key_location')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise JevBlocked('key_permissions')
    if info.st_size > 256:
        raise JevBlocked('invalid_key')
    return path.read_text().strip()


def evaluate(batches, queries, *, client=None):
    """Caller is an evaluator, not an executor. Labels are local only."""
    labels = {q['id']: set(q['relevant']) for q in queries}
    rows, stopped = [], False
    for batch in batches:
        t0 = perf_counter()
        ids = batch['candidate_ids']
        row = {'query_id': batch['query_id'], 'baseline_selected': ids[:3],
               'selected': [], 'scores': {}, 'error': None}
        try:
            request = secure_request(batch)
            if not ids:
                row['status'] = 'no_evidence'
            elif stopped:
                row['status'] = 'not_attempted_after_failure'
            elif client is None:
                # Neutral canned probabilities; never use expected labels as model input.
                result = validate_response({'model': request['model'], 'answers': {
                    qid: {'type': 'noul', 'noul': 0.5} for qid in request['questions']},
                    'usage': {'input_tokens': 0, 'output_tokens': 0}}, request)
                row.update(status='simulated', **result)
            else:
                result = client.evaluate(batch)
                row.update(result)
                scores = result['scores']
                # Rank only IDs already filtered; no model-created IDs or actions.
                row['selected'] = sorted(ids, key=lambda oid: (
                    -scores[f'evidence_{ids.index(oid)}'], ids.index(oid)))[:3]
            if client is not None and row['status'] in ('evaluated', 'no_evidence'):
                expected = labels[batch['query_id']]
                row['baseline_recall_at_3'] = len(set(ids[:3]) & expected) / len(expected) if expected else None
                row['recall_at_3'] = len(set(row['selected']) & expected) / len(expected) if expected else None
        except JevBlocked as exc:
            row['status'], row['error'], stopped = 'blocked', str(exc), True
        row['elapsed_ms'] = round((perf_counter() - t0) * 1000, 3)
        rows.append(row)
    evaluated = [r for r in rows if r['status'] == 'evaluated']
    quality = [r for r in rows if r.get('recall_at_3') is not None]
    costs = [r['usage']['cost_usd'] for r in evaluated]
    return {'schema_version': 1, 'mode': 'live' if client else 'simulated',
            'scope': 'Relevance reranking only; manually labelled development pilot, never execution',
            'real_model_requests_attempted': client.budget.calls if client else 0,
            'evaluated_questions': sum(len(r['scores']) for r in evaluated),
            'real_game_operations': 0, 'requests_bytes_reserved': client.budget.sent_bytes if client else 0,
            'quality_evaluated': bool(evaluated), 'simulation_proves_model_accuracy': False,
            'mean_recall_at_3': sum(r['recall_at_3'] for r in quality) / len(quality) if quality else None,
            'mean_baseline_recall_at_3': sum(r['baseline_recall_at_3'] for r in quality) / len(quality) if quality else None,
            'known_successful_cost_usd': sum(costs) if costs and all(c is not None for c in costs) else None,
            'failed_request_cost_unknown': any(r['status'] == 'blocked' for r in rows) and client is not None,
            'completed': not stopped, 'queries': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=Path('runs/rag-corpus.json'))
    parser.add_argument('--queries', type=Path, default=Path('runs/rag-queries.json'))
    parser.add_argument('--output', type=Path, default=Path('runs/jev-evaluation.json'))
    parser.add_argument('--live', action='store_true', help='Send at most 9 bounded requests to OpenRouter')
    parser.add_argument('--key-file', type=Path, help='Owner-only secret file outside checkout; alternatively env')
    parser.add_argument('--max-calls', type=int, default=9)
    args = parser.parse_args()
    try:
        cases = [MemoryCase(**row) for row in json.loads(args.corpus.read_text())]
        queries = json.loads(args.queries.read_text())
        batches = prepare_reranking(cases, queries)
        budget = RequestBudget(max_calls=args.max_calls)
        # Check every request before the first real call.
        requests = [secure_request(b) for b in batches]
        if sum(bool(r['questions']) for r in requests) > budget.max_calls:
            raise JevBlocked('plan_exceeds_call_limit')
        if sum(len(_encoded(r)) for r in requests if r['questions']) > budget.max_total_bytes:
            raise JevBlocked('plan_exceeds_byte_limit')
        root = Path(__file__).resolve().parent / 'runs'
        if not args.output.resolve().is_relative_to(root):
            raise JevBlocked('report_location')
        client = JevClient(load_key(args.key_file), budget=budget) if args.live else None
        report = evaluate(batches, queries, client=client)
        # Reports contain identifiers/probabilities only, no request bodies or keys.
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=args.output.parent, prefix='.jev-report-')
        try:
            with os.fdopen(fd, 'w') as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write('\n')
            os.replace(tmp, args.output)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    except JevBlocked as exc:
        parser.error(str(exc))
    except (OSError, ValueError, TypeError, KeyError):
        parser.error('invalid_local_input')
    print(f"JEV · {report['mode']} · solicitudes reales: {report['real_model_requests_attempted']} · "
          f"preguntas reales evaluadas: {report['evaluated_questions']} · operaciones del juego: 0")
    print(f"Informe local: {args.output}")
    return 0 if report['completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
