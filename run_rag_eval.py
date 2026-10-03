"""Evaluate local RAG retrieval on a public feed and labelled local questions."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from harness.rag_eval import evaluate_retrieval
from harness.retrieval import MemoryCase, VERSIONS, import_feed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feed', required=True, type=Path)
    parser.add_argument('--queries', required=True, type=Path, help='JSON array: id, text, scope, relevant IDs')
    parser.add_argument('--notes', type=Path, help='Optional JSON array of curated MemoryCase records with provenance')
    parser.add_argument('--output', type=Path, default=Path('runs/rag-report.json'))
    parser.add_argument('--corpus-output', type=Path, help='Optional sanitized local corpus, use runs/')
    parser.add_argument('--k', type=int, default=3)
    parser.add_argument('--byte-budget', type=int, default=8000)
    parser.add_argument('--repeats', type=int, default=20)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--evidence-version', choices=sorted(VERSIONS))
    parser.add_argument('--round', type=int, help='Verified round for the entire supplied feed window')
    parser.add_argument('--regime', default='unknown', help='Verified regime, e.g. normal or sal-fever')
    parser.add_argument('--as-of-tick', type=int, help='Import only events visible by this tick')
    args = parser.parse_args()
    raw = args.feed.read_bytes()
    payload = json.loads(raw)
    try:
        cases, coverage = import_feed(payload['events'], str(args.feed), version=args.evidence_version,
                                      round=args.round, regime=args.regime, as_of_tick=args.as_of_tick)
    except ValueError as exc:
        parser.error(str(exc))
    if args.notes:
        cases += [MemoryCase(**row) for row in json.loads(args.notes.read_text())]
    queries = json.loads(args.queries.read_text())
    try:
        report = evaluate_retrieval(cases, queries, k=args.k, byte_budget=args.byte_budget, repeats=args.repeats)
    except ValueError as exc:
        parser.error(str(exc))
    report['import'] = {**coverage, 'feed': str(args.feed), 'feed_sha256': hashlib.sha256(raw).hexdigest()}
    report['import']['context'] = {'version': args.evidence_version, 'round': args.round,
                                    'regime': args.regime, 'as_of_tick': args.as_of_tick}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    if args.corpus_output:
        args.corpus_output.parent.mkdir(parents=True, exist_ok=True)
        args.corpus_output.write_text(json.dumps([asdict(c) for c in cases], indent=2, ensure_ascii=False) + '\n')
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"RAG · recuperación local · {len(cases)} casos · {len(queries)} consultas · {report['duration_seconds']:.3f}s")
        print('método             recall@k   MRR    fugas   abstenciones   bytes/contexto  p95 ms')
        for mode, result in report['results'].items():
            s = result['summary']
            print(f"{mode:18} {s['mean_recall_at_k']:>8.1%} {s['mrr']:>6.3f} {s['scope_violations']:>7} "
                  f"{s['correct_abstentions']:>5}/{s['negative_queries']:<7} {s['mean_context_bytes']:>14} {s['p95_ms']:>8.3f}")
        print('0 API/modelos. Sin embeddings ni generación; no mide ganancias del agente.')
        print(f'Informe: {args.output}')
    return 0 if report['results']['fused_fts']['summary']['safety_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
