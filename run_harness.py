"""Fast offline harness. Never starts the agent, trades, or calls a model."""
import argparse
import importlib
import json
from pathlib import Path

from harness.runner import evaluate, offline
from harness.market import candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--runs', type=int, default=100, help='Paired synthetic market/broker cases')
    parser.add_argument('--repeats', type=int, default=10, help='Local latency samples per market case')
    parser.add_argument('--fake-api-ms', type=float, default=100, help='Illustrative sequential read latency, not measured API latency')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--output', type=Path, help='Optional local JSON report (use runs/, which is gitignored)')
    parser.add_argument('--candidate', help='Trusted local adapter module:function(api, me, clock); network remains blocked')
    args = parser.parse_args()
    try:
        policy = candidate
        if args.candidate:
            module, name = args.candidate.split(':')
            with offline():
                policy = getattr(importlib.import_module(module), name)
            if not callable(policy):
                raise ValueError('Candidate is not callable')
        report = evaluate(seed=args.seed, runs=args.runs, repeats=args.repeats, fake_api_ms=args.fake_api_ms,
                          candidate_policy=policy)
    except ValueError as exc:
        parser.error(str(exc))
    encoded = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + '\n')
    if args.json:
        print(encoded)
    else:
        print('OFFLINE · datos inventados · 0 API real · 0 modelos · no predice el leaderboard')
        print('política                  ganancia/tick   riesgos  excepc.  lecturas    p95 local ms')
        for name, data in report['market'].items():
            s = data['summary']
            print(f"{name:25} {s['simulated_gain_per_tick']:>12.3f} {s['unsafe_selections']:>8} "
                  f"{s['exceptions']:>8} {sum(s['calls'].values()):>9} {s['p95_ms']:>15.4f}")
        for name, data in report['market'].items():
            failures = [r['case'] for r in data['cases'] if r['oracle_mismatch'] or r['exception']
                        or r['read_budget_exceeded'] or r['gain_error'] or r['payload_error']]
            print(f"{name}: {data['summary']['cases']} casos; fallos: {', '.join(failures[:18]) or 'ninguno'}")
        print(f"Arbitraje experimental: {len(report['execution_gate']['cases'])} casos; "
              f"{'PASS' if report['execution_gate']['passed'] else 'FAIL'}")
        for name, s in report['broker']['policies'].items():
            print(f"Broker {name}: eficiencia simulada={s['efficiency']}; ganancia/tick={s['simulated_gain_per_tick']}")
        print(f"Candidato {'PASS' if report['passed'] else 'FAIL'} · {report['duration_seconds']:.3f} s")
        print('RAG/JEV se evalúan con run_rag_eval.py y run_jev_patterns.py. El candidato y el arbitraje no están conectados al ejecutor real.')
        if args.output:
            print(f'Informe: {args.output}')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
