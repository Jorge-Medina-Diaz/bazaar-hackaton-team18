"""Independent collector: python3 collect_info.py; cached read: --context."""
raise SystemExit("ARCHIVED by M18: pre-harness script that could reach the game without the Gate. Use the harness: python3 bazaar.py (see CLAUDE.md).")  # M18 guard
import argparse
import json
import os
import signal

from agent.client import _load_env
from agent.information import DEFAULT_STATE, InformationCollector, get_context
from bazaar_sdk import Bazaar
from live_monitor import read_key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', default=str(DEFAULT_STATE))
    parser.add_argument('--context', action='store_true', help='read cached JSON, no network or key')
    parser.add_argument('--once', action='store_true', help='prime once before starting the agent')
    parser.add_argument('--key-file', help='local key file; never stored in the snapshot')
    parser.add_argument('--interval', type=float, default=5)
    parser.add_argument('--timeout', type=float, default=1.5, help='socket timeout per GET; no retries')
    args = parser.parse_args()
    if args.context:
        print(json.dumps(get_context(args.state), ensure_ascii=False))
        return
    if not 0 < args.timeout <= 3:
        parser.error('timeout must be between 0 and 3 seconds')
    _load_env()
    try:
        key = read_key(args.key_file)
        client = Bazaar(os.environ.get('BAZAAR_URL', 'https://bazaar.causaprima.ai'), key,
                        timeout=args.timeout, retries=0, wait_on_tick=False)
        collector = InformationCollector(client, args.state, interval=args.interval)
    except ValueError as error:
        parser.error(str(error))
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: collector.stop())
    if args.once:
        print(json.dumps(collector.poll_once(), ensure_ascii=False))
    else:
        print(f'Collector -> {args.state}, every {args.interval:g}s; GET only', flush=True)
        collector.run()


if __name__ == '__main__':
    main()
