"""Evaluate retrieval with separately labelled questions. No generative model."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
from time import perf_counter

from harness.retrieval import MemoryCase, MemoryIndex, Scope, in_scope
from harness.runner import offline, percentiles

MODES = ('none', 'recent_sql', 'global_fts', 'scoped_fts', 'contextual_fts', 'fused_fts')


def evaluate_retrieval(cases, queries, *, k=3, byte_budget=8000, repeats=20):
    if not cases or not queries or repeats < 1 or k < 1 or byte_budget < 2:
        raise ValueError('Corpus, queries and positive limits required')
    ids = {c.id for c in cases}
    by_id = {c.id: c for c in cases}
    for q in queries:
        scope = Scope(**q['scope'])
        if not set(q['relevant']) <= ids:
            raise ValueError('Relevant evidence missing from corpus: ' + q['id'])
        if any(not in_scope(by_id[oid], scope) for oid in q['relevant']):
            raise ValueError('Labels violate query scope: ' + q['id'])
    started = perf_counter()
    with offline():
        index = MemoryIndex(cases)
        build_ms = (perf_counter() - started) * 1000
        results = {}
        try:
            for mode in MODES:
                rows, timings = [], []
                for q in queries:
                    scope = Scope(**q['scope'])
                    samples = []
                    for _ in range(repeats):
                        t0 = perf_counter()
                        packets, omitted = index.retrieve(q['text'], scope, mode=mode, k=k, byte_budget=byte_budget)
                        serialized = json.dumps(packets, ensure_ascii=False, separators=(',', ':')).encode()
                        samples.append((perf_counter() - t0) * 1000)
                    selected = [p['id'] for p in packets]
                    relevant = set(q['relevant'])
                    hits = len(set(selected) & relevant)
                    leaks = [oid for oid in selected if not in_scope(by_id[oid], scope)]
                    ranks = [i + 1 for i, oid in enumerate(selected) if oid in relevant]
                    rows.append({'query': q['id'], 'selected': selected, 'relevant': sorted(relevant),
                                 'recall_at_k': hits / len(relevant) if relevant else None,
                                 'precision_at_k': hits / len(selected) if selected else 0,
                                 'reciprocal_rank': 1 / min(ranks) if ranks else 0,
                                 'correct_abstention': not selected if not relevant else None,
                                 'scope_violations': leaks, 'context_bytes': len(serialized),
                                 'oversize_cases_skipped': omitted, **percentiles(samples)})
                    timings.extend(samples)
                positives = [r for r in rows if r['recall_at_k'] is not None]
                negatives = [r for r in rows if r['correct_abstention'] is not None]
                summary = {'positive_queries': len(positives), 'negative_queries': len(negatives),
                           'mean_recall_at_k': round(sum(r['recall_at_k'] for r in positives) / len(positives), 4) if positives else None,
                           'mrr': round(sum(r['reciprocal_rank'] for r in positives) / len(positives), 4) if positives else None,
                           'mean_precision_at_k': round(sum(r['precision_at_k'] for r in positives) / len(positives), 4) if positives else None,
                           'scope_violations': sum(len(r['scope_violations']) for r in rows),
                           'correct_abstentions': sum(r['correct_abstention'] for r in negatives),
                           'mean_context_bytes': round(sum(r['context_bytes'] for r in rows) / len(rows)),
                           **percentiles(timings)}
                summary['safety_passed'] = not summary['scope_violations'] and summary['correct_abstentions'] == len(negatives)
                results[mode] = {'summary': summary, 'queries': rows}
        finally:
            index.close()
    normalized = [asdict(c) for c in cases]
    sources = [Path(__file__), Path(__file__).with_name('retrieval.py'), Path(__file__).resolve().parents[1] / 'run_rag_eval.py']
    source_hash = hashlib.sha256(b''.join(p.name.encode() + p.read_bytes() for p in sources)).hexdigest()
    return {'schema_version': 1, 'scope': 'RAG retrieval stage only; manually labelled pilot, not held-out decision performance',
            'metadata': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version, 'source_sha256': source_hash},
            'corpus_cases': len(cases), 'queries': len(queries), 'k': k, 'byte_budget': byte_budget, 'repeats': repeats,
            'build_ms': round(build_ms, 3), 'corpus_sha256': hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest(),
            'queries_sha256': hashlib.sha256(json.dumps(queries, sort_keys=True).encode()).hexdigest(),
            'real_api_calls': 0, 'real_model_calls': 0, 'embeddings_evaluated': False,
            'generation_evaluated': False, 'jev_evaluated': False, 'tokens_measured': None, 'model_cost': None,
            'evidence_kinds': {kind: sum(c.evidence == kind for c in cases) for kind in sorted({c.evidence for c in cases})},
            'results': results, 'duration_seconds': round(perf_counter() - started, 4)}
