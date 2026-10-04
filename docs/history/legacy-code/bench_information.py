"""Reproducible cache-read benchmark. Synthetic inputs; no game or model calls."""
raise SystemExit("ARCHIVED by M18: pre-harness script that could reach the game without the Gate. Use the harness: python3 bazaar.py (see CLAUDE.md).")  # M18 guard
import argparse
import json
import math
from pathlib import Path
import statistics
import tempfile
import time
from unittest.mock import patch

from agent.information import InformationCollector, get_context, record_result


class Fixture:
    def me(self):
        return {'id': 'fixture-team', 'cash': 400, 'score': {'rank': 3},
                'assets': [{'id': i, 'kind': 'card', 'ref': f'SAL-{i % 12:02}',
                            'your_value': 10} for i in range(48)]}

    def clock(self):
        return {'tick': 100, 'paused': False}

    def my_offers(self):
        return {'open': [], 'queued': []}

    def my_threads(self):
        return {'threads': []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reads', type=int, default=2000)
    args = parser.parse_args()
    if args.reads < 1:
        parser.error('reads must be positive')
    with tempfile.TemporaryDirectory() as directory, patch('agent.information.log'):
        path = Path(directory) / 'state.json'
        InformationCollector(Fixture(), path, spacing=0).poll_once()
        record_result(path, team='fixture-team', dealer='abuela', item='SAL-01', buying=True,
                      result={'status': 'deal', 'confirmed': True, 'thread': 1, 'price': 9})
        measurements = []
        for _ in range(args.reads):
            start = time.perf_counter()
            context = get_context(path)
            serialized = json.dumps(context).encode()
            measurements.append((time.perf_counter() - start) * 1000)
        print(json.dumps({'reads': args.reads,
                          'median_ms': round(statistics.median(measurements), 3),
                          'p95_ms': round(sorted(measurements)[math.ceil(args.reads * 0.95) - 1], 3),
                          'context_bytes': len(serialized), 'api_calls_per_read': 0,
                          'model_calls_per_read': 0}))


if __name__ == '__main__':
    main()
