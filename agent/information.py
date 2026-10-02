"""Read-only information service. No model, game writes, or trading decisions.

The collector owns network IO; consumers read an atomic local snapshot. Confirmed
executor results form a separate, bounded SQLite memory that survives restarts.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time

from agent.execution import team_writer
from agent.journal import log


DEFAULT_STATE = Path(__file__).resolve().parents[1] / 'runs' / 'information.json'
SOURCES = ('me', 'clock', 'my_offers', 'my_threads')
SCORE_KEYS = ('score', 'negotiating', 'market', 'neg_points', 'mm_points',
              'duel_points', 'ladder_points', 'bench_points', 'deals', 'rank')


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def select(row, keys):
    return {key: row[key] for key in keys if key in row}


def rows(payload, *keys):
    if isinstance(payload, list):
        data = payload
    elif isinstance(payload, dict) and any(key in payload for key in keys):
        data = []
        for key in keys:
            part = payload.get(key, [])
            if not isinstance(part, list):
                raise ValueError('Expected a list')
            data.extend(part)
    else:
        raise ValueError('Missing list')
    if any(not isinstance(row, dict) for row in data):
        raise ValueError('Expected records')
    return data


def clean(name, payload):
    """Allowlist fields: /me may also contain a private starter_broker_key."""
    if name == 'me':
        if (not isinstance(payload, dict) or not number(payload.get('cash'))
                or not (payload.get('id') or payload.get('team'))):
            raise ValueError('Unverified team or cash')
        assets = rows(payload, 'assets')
        if any('id' not in a or 'ref' not in a for a in assets):
            raise ValueError('Unverified assets')
        result = select(payload, ('id', 'team', 'cash', 'level', 'tick', 'collection_value'))
        result['assets'] = [select(a, ('id', 'kind', 'ref', 'your_value', 'locked')) for a in assets]
        result['score'] = {k: v for k, v in payload.get('score', {}).items()
                           if k in SCORE_KEYS and number(v)}
        return result
    if name == 'clock':
        if not isinstance(payload, dict) or type(payload.get('tick')) is not int:
            raise ValueError('Unverified clock')
        return select(payload, ('tick', 'paused', 'tick_seconds', 'next_tick_in'))
    if name == 'my_offers':
        result = {}
        for offer in rows(payload, 'offers', 'open', 'queued'):
            if 'id' not in offer or 'status' not in offer:
                raise ValueError('Unverified offer')
            item = select(offer, ('id', 'maker', 'to', 'status', 'thread', 'thread_id',
                                  'expires_tick', 'final', 'venue'))
            for side in ('give', 'want'):
                bundle = offer.get(side, {})
                if not isinstance(bundle, dict):
                    raise ValueError('Unverified bundle')
                item[side] = select(bundle, ('cash', 'assets', 'types', 'cards'))
            result[str(offer['id'])] = item
        return list(result.values())
    if name == 'my_threads':
        result = rows(payload, 'threads')
        if any('id' not in t or 'status' not in t for t in result):
            raise ValueError('Unverified thread')
        return [select(t, ('id', 'status', 'with', 'closed_reason')) for t in result]
    raise ValueError('Unknown source')


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='information-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def memory_path(state_path):
    return Path(state_path).with_suffix('.sqlite3')


def record_result(state_path, *, team, dealer, item, buying, result):
    """Only called after the executor verified settlement; never infer a deal.

    Thread identity de-duplicates retries, including across process restarts.
    A caller failure must not cause a second trade or change a price limit.
    """
    if (result.get('status') != 'deal' or result.get('confirmed') is not True
            or not number(result.get('price')) or result['price'] <= 0
            or not result.get('thread') or not team or not dealer or not item):
        return False
    path = memory_path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=0.05) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('''CREATE TABLE IF NOT EXISTS deals (
            team TEXT, thread TEXT, dealer TEXT, item TEXT, side TEXT,
            price REAL, observed_at REAL, PRIMARY KEY(team, thread))''')
        cursor = db.execute('INSERT OR IGNORE INTO deals VALUES (?, ?, ?, ?, ?, ?, ?)',
                            (str(team), str(result['thread']), str(dealer), str(item),
                             'buy' if buying else 'sell', result['price'], time.time()))
        inserted = cursor.rowcount == 1
        db.execute('DELETE FROM deals WHERE rowid NOT IN '
                   '(SELECT rowid FROM deals ORDER BY observed_at DESC LIMIT 500)')
    return inserted


def learned(state_path, team):
    """Historical observations, not optimal prices or hidden dealer limits."""
    path = memory_path(state_path)
    if not team or not path.exists():
        return []
    try:
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=0.05) as db:
            groups = db.execute('''SELECT dealer, item, side, COUNT(*), AVG(price),
                MIN(price), MAX(price), MAX(observed_at) FROM deals WHERE team=?
                GROUP BY dealer, item, side ORDER BY MAX(observed_at) DESC LIMIT 12''',
                                (str(team),)).fetchall()
        return [dict(zip(('dealer', 'item', 'side', 'samples', 'mean_price',
                          'min_price', 'max_price', 'last_observed_at'), row),
                     evidence='executor_confirmed_settlement') for row in groups]
    except sqlite3.Error:
        return []


def get_context(state_path=DEFAULT_STATE, *, max_age=7.5, reserve_cash=0, now=None):
    """Cached read only; safe to call at every decision. Never waits for HTTP/LLM."""
    if not number(max_age) or max_age <= 0 or not number(reserve_cash) or reserve_cash < 0:
        raise ValueError('Invalid age or reserve')
    now = time.time() if now is None else now
    try:
        state = json.loads(Path(state_path).read_text(encoding='utf-8'))
        sources = state['sources']
        if state.get('schema') != 1 or not isinstance(sources, dict):
            raise ValueError('Unknown schema')
        fresh = {name: (number(sources.get(name, {}).get('verified_at'))
                       and 0 <= now - sources[name]['verified_at'] <= max_age
                       and not sources[name].get('error')) for name in SOURCES}
        me = sources.get('me', {}).get('data', {})
        clock = sources.get('clock', {}).get('data', {})
        offers = sources.get('my_offers', {}).get('data', [])
        threads = sources.get('my_threads', {}).get('data', [])
        assets = me.get('assets', [])
        groups = {}
        for asset in assets:
            group = groups.setdefault(asset['ref'], {'ref': asset['ref'], 'copies': 0,
                                                      'available': 0, 'your_value': asset.get('your_value')})
            group['copies'] += 1
            group['available'] += not asset.get('locked', False)
        pending = [o['id'] for o in offers if o.get('status') in ('queued', 'accepted')]
        open_threads = [t['id'] for t in threads if t.get('status') == 'open']
        cash = me.get('cash')
        ready = all(fresh.values())
        actions = []
        if not ready:
            actions.append({'priority': 0, 'action': 'refresh_required',
                            'sources': [k for k in SOURCES if not fresh[k]]})
        if clock.get('paused'):
            actions.append({'priority': 0, 'action': 'wait_clock'})
        if pending:
            actions.append({'priority': 0, 'action': 'wait_settlement', 'offers': pending[:16]})
        if ready and not pending and not clock.get('paused'):
            if open_threads:
                actions.append({'priority': 1, 'action': 'reconcile_existing_threads'})
            duplicates = [g['ref'] for g in groups.values() if g['copies'] > 1 and g['available'] > 0]
            if duplicates:
                actions.append({'priority': 2, 'action': 'evaluate_duplicate_sales', 'refs': duplicates[:12]})
        return {'schema': 1, 'ready': ready, 'generated_at': state.get('generated_at'),
                'poll_seconds': state.get('poll_seconds'), 'tick': clock.get('tick'),
                'sources': {name: {'fresh': fresh[name],
                                   'verified_at': sources.get(name, {}).get('verified_at'),
                                   'error': sources.get(name, {}).get('error')} for name in SOURCES},
                'cash': cash, 'spendable_cash': max(0, cash - reserve_cash) if number(cash) else None,
                'score': me.get('score', {}), 'collection_value': me.get('collection_value'),
                'inventory': list(groups.values())[:40], 'inventory_types': len(groups),
                'inventory_truncated': len(groups) > 40,
                'pending_count': len(pending), 'pending_offers': pending[:16],
                'open_thread_count': len(open_threads), 'open_threads': open_threads[:16],
                'actions': actions, 'learned': learned(state_path, me.get('id') or me.get('team')),
                'constraints': ['advisory_only', 'revalidate_before_accept', 'keep_explicit_limits',
                                'snapshots_are_not_atomic', 'observations_are_not_optimal_prices']}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {'schema': 1, 'ready': False, 'actions': [{'priority': 0, 'action': 'collector_unavailable'}]}


class InformationCollector:
    def __init__(self, client, state_path=DEFAULT_STATE, *, interval=5.0, spacing=0.3):
        if not number(interval) or interval < 5 or not number(spacing) or spacing < 0:
            raise ValueError('Poll interval must be at least 5 seconds')
        self.client, self.path, self.interval, self.spacing = client, Path(state_path), interval, spacing
        self.stop_event = threading.Event()
        self.state = {'schema': 1, 'poll_seconds': interval, 'sources': {}}

    def poll_once(self):
        """Independent source failures retain last verified data with an error flag."""
        def sample(name):
            try:
                data = clean(name, getattr(self.client, name)())
                return name, {'verified_at': time.time(), 'data': data}
            except Exception as error:
                # Exception text can contain keys, broker URLs, or private messages.
                return name, {'error': type(error).__name__, 'attempted_at': time.time()}

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = []
            for name in SOURCES:
                if self.stop_event.is_set():
                    break
                futures.append(pool.submit(sample, name))
                self.stop_event.wait(self.spacing)
            for future in futures:
                name, sample_result = future.result()
                log('information', event='sample', source=name,
                    verified_at=sample_result.get('verified_at'),
                    error=sample_result.get('error'))
                previous = self.state['sources'].get(name, {})
                if 'error' in sample_result:
                    self.state['sources'][name] = {**previous, **sample_result}
                else:
                    self.state['sources'][name] = sample_result
        self.state['generated_at'] = time.time()
        atomic_write(self.path, self.state)
        return get_context(self.path)

    def run(self):
        # Separate reader lock: never takes or interferes with the trading lock.
        # Scope by credential hash so parallel worktrees don't double-poll a key.
        import hashlib
        key = getattr(self.client, 'key', str(self.path.resolve()))
        identity = hashlib.sha256(key.encode()).hexdigest()
        with team_writer('collector:' + identity):
            deadline = time.monotonic()
            while not self.stop_event.is_set():
                self.poll_once()  # warm immediately; then independent wall-clock refresh
                deadline += self.interval
                if deadline < time.monotonic():
                    # Skip missed slots rather than accumulate a request backlog.
                    deadline = time.monotonic() + self.interval
                self.stop_event.wait(max(0, deadline - time.monotonic()))

    def stop(self):
        self.stop_event.set()
