"""Live bounded pattern checks for Abuela, Chato and a public pack negotiation."""
import argparse
import json
import os
from pathlib import Path
import tempfile

from harness.jev_patterns import evaluate_patterns, pattern_batches
from harness.jev_security import JevBlocked, JevClient, RequestBudget, secure_request, _encoded
from harness.retrieval import MemoryCase
from run_jev_eval import load_key


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus', type=Path, default=Path(__file__).resolve().parent / 'tests/fixtures/jev-history.json')
    p.add_argument('--key-file', type=Path)
    p.add_argument('--live', action='store_true', help='Required to send any request')
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--output', type=Path, default=Path('runs/jev-patterns-live.json'))
    args = p.parse_args()
    try:
        cases = [MemoryCase(**r) for r in json.loads(args.corpus.read_text())]
        requests = [secure_request(b) for b in pattern_batches(cases, args.repeats)]
        budget = RequestBudget()
        if sum(len(_encoded(r)) for r in requests) > budget.max_total_bytes:
            raise JevBlocked('plan_exceeds_byte_limit')
        if not args.live:
            print(f'Plan verificado: {len(requests)} solicitudes, {sum(len(r["questions"]) for r in requests)} preguntas. Sin red.')
            return 0
        if not args.output.resolve().is_relative_to(Path(__file__).resolve().parent / 'runs'):
            raise JevBlocked('report_location')
        report = evaluate_patterns(cases, JevClient(load_key(args.key_file), budget=budget), args.repeats)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=args.output.parent, prefix='.jev-patterns-')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)
                f.write('\n')
            os.replace(tmp, args.output)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        print({k: report[k] for k in ('completed', 'real_model_requests_attempted', 'evaluated_questions',
                                     'correct_at_05', 'incorrect_at_05', 'successful_cost_usd')})
        return 0 if report['completed'] else 1
    except JevBlocked as exc:
        p.error(str(exc))
    except (OSError, ValueError, TypeError, KeyError):
        p.error('invalid_local_input')


if __name__ == '__main__':
    raise SystemExit(main())
