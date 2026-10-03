"""Observe the existing artifact, log compact changes, never trade or call an LLM."""
import argparse
from datetime import datetime, timezone
import http.cookiejar
import json
import math
from pathlib import Path
import time
import urllib.request

from live_monitor import read_client, read_key

ARTIFACT = 'https://bazaar-equipo18-cartas.rubenwork1009.chatgpt.site'
SCORE_FIELDS = ('score', 'rank', 'negotiating', 'market', 'neg_points', 'ladder_points',
                'duel_points', 'mm_points', 'bench_points', 'deals', 'level', 'pages_complete')
COMPONENTS = ('neg_points', 'ladder_points', 'duel_points', 'mm_points')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def metrics(me):
    score = me.get('score') or {}
    point = {k: score.get(k) if number(score.get(k)) else None for k in SCORE_FIELDS}
    point.update(tick=me.get('tick'), cash=me.get('cash'),
                 collection_value=me.get('collection_value'),
                 open_threads=len(me.get('open_threads') or []))
    return point


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class ArtifactClient:
    """Cookie stays in memory; the only POST authenticates to our own artifact."""
    def __init__(self, key):
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect())
        body = json.dumps({'key': key}).encode()
        self._request('/api/login', body)

    def _request(self, path, body=None):
        headers = {'Accept': 'application/json', 'User-Agent': 'BazaarPerformanceObserver/1.0'}
        if body is not None:
            headers.update({'Origin': ARTIFACT, 'Content-Type': 'application/json'})
        request = urllib.request.Request(ARTIFACT + path, data=body, headers=headers)
        with self.opener.open(request, timeout=10) as response:
            blob = response.read(2_000_001)
        if len(blob) > 2_000_000:
            raise ValueError('Oversized artifact response')
        return json.loads(blob)

    def snapshot(self):
        return self._request('/api/state')


class Sampler:
    """Reuses artifact snapshots; supplements missing scores once per artifact tick."""
    def __init__(self, panel_read, me_read):
        self.panel_read, self.me_read = panel_read, me_read
        self.cached, self.last_tick, self.extra_reads = None, None, 0

    def read(self):
        state = self.panel_read()
        if state.get('mode') != 'live':
            raise ValueError('Artifact is not in live mode')
        tick = state.get('tick')
        check = state.get('checks', {}).get('reloj', {})
        if type(tick) is not int or not check.get('ok'):
            raise ValueError('Artifact clock is unverified')
        embedded = state.get('performance')
        if isinstance(embedded, dict) and number(embedded.get('score')):
            inventory_check = state.get('checks', {}).get('inventario y saldo', {})
            if not inventory_check.get('ok'):
                raise ValueError('Artifact metrics are unverified')
            point, source = dict(embedded), 'artifact'
        else:
            # Current deployed panel omits score. One GET /api/me per new tick
            # fills that gap; it does not introduce another five-second API loop.
            if self.cached is None or tick != self.last_tick:
                self.cached = metrics(self.me_read())
                self.last_tick = tick
                self.extra_reads += 1
            point, source = dict(self.cached), 'artifact+me_once_per_tick'
        if not number(point.get('score')):
            raise ValueError('Score unavailable')
        point.update(observed_at=stamp(), source=source, artifact_tick=tick,
                     artifact_checks={k: bool(v.get('ok')) for k, v in state.get('checks', {}).items()})
        return point


class ChangeLog:
    def __init__(self, path, reserve_cash=0):
        self.path, self.reserve = Path(path), reserve_cash
        self.previous, self.first, self.count = None, None, 0

    def observe(self, point):
        signature = {k: v for k, v in point.items() if k != 'observed_at'}
        old = self.previous
        if old and signature == {k: v for k, v in old.items() if k != 'observed_at'}:
            return None
        delta = {k: round(point[k] - old[k], 4) for k in point if old
                 and number(point[k]) and number(old.get(k)) and k not in ('tick', 'artifact_tick')}
        flags = []
        if old:
            measured = [k for k in COMPONENTS if number(point.get(k)) and number(old.get(k))]
            if (delta.get('score', 0) != 0 and len(measured) >= 2
                and all(point[k] == old[k] for k in measured)
                and delta.get('cash') == 0 and delta.get('collection_value') == 0):
                flags.append('score_changed_without_measured_component_or_resource_change')
            if delta.get('score', 0) > 0 and delta.get('rank', 0) > 0:
                flags.append('score_improved_but_relative_position_worsened')
        if number(point.get('cash')) and point['cash'] < self.reserve:
            flags.append('cash_below_planned_reserve')
        event = {'kind': 'baseline' if old is None else 'change', 'metrics': point,
                 'delta': delta, 'flags': flags,
                 'scope': 'Observed differences; no automatic attribution to trades or scoring formula.'}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Keep the active log and one rotated file bounded. Private metrics only;
        # never serialize the client, headers, key, cookie or full API response.
        line = json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n'
        if self.path.exists() and self.path.stat().st_size + len(line.encode()) > 1_000_000:
            self.path.replace(self.path.with_suffix('.previous.jsonl'))
        with self.path.open('a', encoding='utf-8') as stream:
            self.path.chmod(0o600)
            stream.write(line)
        self.previous = dict(point)
        if self.first is None:
            self.first = dict(point)
        self.count += 1
        return event

    def summary(self):
        return {'records': self.count, 'first': self.first, 'latest': self.previous}


def observe(sampler, log, cycles=12, interval=5):
    errors = 0
    for cycle in range(cycles) if cycles else iter(int, 1):
        started = time.monotonic()
        try:
            event = log.observe(sampler.read())
            errors = 0
            if event:
                p = event['metrics']
                print(json.dumps({'tick': p['tick'], 'score': p['score'], 'rank': p['rank'],
                                  'delta': event['delta'], 'flags': event['flags']}, ensure_ascii=False), flush=True)
        except Exception as error:
            errors += 1
            print(json.dumps({'observation_error': type(error).__name__, 'consecutive': errors}), flush=True)
        if cycles and cycle + 1 >= cycles:
            break
        delay = min(60, interval * 2 ** min(errors, 4))
        time.sleep(max(0, delay - (time.monotonic() - started)))
    return {**log.summary(), 'supplementary_me_reads': sampler.extra_reads}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key-file', type=Path)
    parser.add_argument('--cycles', type=int, default=12, help='0 observes until interrupted')
    parser.add_argument('--interval', type=int, default=5)
    parser.add_argument('--reserve-cash', type=int, default=0)
    parser.add_argument('--log', type=Path, default=Path(__file__).resolve().parent / 'runs/performance-observations.jsonl')
    args = parser.parse_args()
    if args.cycles < 0 or args.interval < 5 or args.reserve_cash < 0:
        parser.error('cycles/reserve must be nonnegative; interval must be at least 5 seconds')
    key = read_key(args.key_file)
    panel = ArtifactClient(key)
    b = read_client('https://bazaar.causaprima.ai', key)  # M18: read-only transport
    sampler = Sampler(panel.snapshot, b.me)
    result = observe(sampler, ChangeLog(args.log, args.reserve_cash), args.cycles, args.interval)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result['records'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
