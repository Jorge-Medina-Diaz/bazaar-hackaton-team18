"""Shared run traces: one read model over logs/*.jsonl for the team viewer and the RAG memory.

Read-only. The journal stays the single source of truth: the viewer and the memory both derive from it,
so what the team sees and what the RAG retrieves cannot drift apart. Event ids are `<stream>:<line>`,
stable because the journal is append-only.
"""
import glob
import json
import os
from dataclasses import replace

from agent.journal import Journal
from agent.redact import redact

from harness.retrieval import MemoryCase

NOISE = frozenset({'information', 'dashboard', 'feed', 'untrusted'})  # samples/text, not decisions
SECRET = ('key', 'token', 'password', 'secret', 'authorization')
ENDED = frozenset({'deal', 'closed', 'expired', 'cancelled', 'failed', 'walked'})


def _clean(value):
    if isinstance(value, dict):
        return {k: '[redacted]' if any(s in str(k).lower() for s in SECRET) else _clean(v)
                for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def read(log_dir, skip=NOISE):
    """All journal rows as events, oldest first. Torn or malformed lines are counted, never fatal."""
    events, bad = [], 0
    paths = sorted(glob.glob(os.path.join(log_dir, '*.jsonl')))
    nested = os.path.join(log_dir, 'run', 'journal.jsonl')
    if os.path.isfile(nested):
        paths.append(nested)
    for path in paths:
        stream = os.path.basename(path)[:-len('.jsonl')]
        v2 = stream == 'journal'
        if v2:
            stream = 'run'
        if stream in skip:
            continue
        with open(path, encoding='utf-8', errors='replace') as f:
            for n, line in enumerate(f, 1):
                if not line.endswith('\n'):
                    bad += 1  # the writer is mid-append; it will be read complete next time
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    bad += 1
                    continue
                if not isinstance(row, dict):
                    bad += 1
                    continue
                clean = _clean(redact(row))
                if v2:
                    clean['intent_id'] = clean.pop('id', None)
                    clean['event'] = clean.get('kind')
                events.append({**clean, 'id': f'{stream}:{n}', 'stream': stream})
    events.sort(key=lambda e: (e.get('ts') or 0, e['stream'], int(e['id'].rsplit(':', 1)[1])))
    return events, bad


def executor_status(log_dir, events):
    """Read the v2 WAL and status files; never repair, arm, stop or write anything.

    An HTTP result is not a settled trade. V2 rows remain operational events,
    not outcome labels for the RAG until an explicit outcome adapter exists.
    """
    path = os.path.join(log_dir, 'run', 'journal.jsonl')
    if not os.path.isfile(path):
        path = os.path.join(log_dir, 'journal.jsonl')
    if not os.path.isfile(path):
        return None
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(path))))
    rows = [e for e in events if e['stream'] == 'run']
    tick = next((e for e in reversed(rows) if e.get('event') == 'tick'), {})
    try:
        reader = Journal(path, mode='dry', writer=False)
        valid = reader.verify_chain()
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            if f.tell():
                f.seek(-1, os.SEEK_END)
                valid = valid and f.read(1) == b'\n'
        pending = len(reader.pending())
        unknown = sorted(reader.unknown_domains())
    except Exception:
        valid, pending, unknown = False, None, []
    try:
        with open(os.path.join(root, 'state', 'writer.lock'), encoding='utf-8') as f:
            lock = json.load(f)
        pid = lock.get('pid') if isinstance(lock, dict) else None
    except (OSError, ValueError):
        pid = None
    return {'mode': rows[-1].get('mode') if rows else None,
            'tick': tick.get('tick'), 'cash': tick.get('cash'), 'cash_free': tick.get('cash_free'),
            'armed': tick.get('armed', []), 'down': tick.get('down', []),
            'last_ts': rows[-1].get('ts') if rows else None, 'writer_pid': pid,
            'journal_valid': valid, 'pending': pending, 'unknown_domains': unknown,
            'stop': bool(glob.glob(os.path.join(root, 'STOP*')) or glob.glob(os.path.join(root, 'stop*'))),
            'outcomes_indexed': False}


def threads(events):
    """One summary per (dealer, thread), in the order the conversations were opened."""
    out = {}
    for e in events:
        if e['stream'] == 'run':
            continue  # v2 HTTP outcomes are not settlement evidence
        if e.get('thread') is None:
            continue
        t = out.setdefault((e['stream'], str(e['thread'])), {
            'dealer': e['stream'], 'thread': str(e['thread']), 'side': 'unknown', 'item': 'unknown',
            'anchor': None, 'limit': None, 'ours': [], 'hers': [], 'steps': [], 'status': 'open',
            'price': None, 'reason': None, 'score': None, 'first': e['id'], 'last_ts': e.get('ts')})
        t['last_ts'] = e.get('ts')
        kind = e.get('event')
        t['steps'].append({'id': e['id'], 'ts': e.get('ts'), 'tick': e.get('tick'), 'event': kind,
                           'price': e.get('price')})
        if kind == 'open':
            topic = e.get('topic') or {}
            t['side'] = 'buy' if 'buy' in topic else 'sell' if 'sell' in topic else 'unknown'
            buy = topic.get('buy') or {}
            t['item'] = buy.get('card') or buy.get('pack') or ('assets' if t['side'] == 'sell' else 'unknown')
            t['anchor'], t['limit'] = e.get('anchor'), e.get('limit')
        elif kind == 'offer_sent':
            t['ours'].append(e.get('price'))
        elif kind in ('accept_intent', 'walk'):
            t['hers'].append(e.get('price'))
        elif kind == 'end':
            t['status'], t['price'], t['reason'] = e.get('status') or 'closed', e.get('price'), e.get('reason')
        elif kind == 'score':
            t['score'] = {'before': e.get('before'), 'after': e.get('after')}
            if t['status'] == 'open' and e.get('status'):
                t['status'], t['price'] = e['status'], e.get('price')
    return list(out.values())


def team_cases(summaries, source='journal'):
    """Memory cases from our own finished conversations only; private, so never visible as public evidence."""
    cases = []
    for t in summaries:
        if t['status'] not in ENDED:
            continue  # an open conversation has no outcome yet: indexing it would teach a wrong result
        body = json.dumps({'anchor': t['anchor'], 'limit': t['limit'], 'our_prices': t['ours'],
                           'dealer_prices_seen': t['hers'], 'status': t['status'], 'price': t['price'],
                           'reason': t['reason'], 'score': t['score']}, ensure_ascii=False)
        ticks = [s['tick'] for s in t['steps'] if type(s.get('tick')) is int]
        cases.append(MemoryCase(f"thread-{t['thread']}", t['dealer'], t['side'], t['item'],
                                'settled' if t['status'] == 'deal' and t['price'] is not None else 'closed',
                                body, f"{source}#{t['first']}", 'team_journal', max(ticks) if ticks else None,
                                visibility='local-team'))
    return cases


def merge(feed_cases, ours):
    """One case per conversation: our trace enriches the public thread instead of duplicating it."""
    mine = {c.id: c for c in ours}
    merged = []
    for c in feed_cases:
        o = mine.pop(c.id, None)
        if o is None or o.dealer != c.dealer:
            merged.append(c)
            if o is not None:
                mine[c.id + '-team'] = replace(o, id=c.id + '-team')  # never fuse two dealers' threads
            continue
        body = json.dumps({'feed': json.loads(c.body), 'team': json.loads(o.body)}, ensure_ascii=False)
        ticks = [t for t in (c.tick, o.tick) if t is not None]
        merged.append(replace(c, side=o.side if c.side == 'unknown' else c.side,
                              item=o.item if c.item in ('unknown', 'bundle') else c.item, phase=o.phase,
                              body=body, source=c.source + ' + ' + o.source, evidence='public_thread+team_journal',
                              tick=max(ticks) if ticks else None, visibility='local-team'))
    return merged + list(mine.values())


def reconcile(summaries, feed_cases):
    """Where the journal and the public feed disagree. Empty lists mean the memory is consistent."""
    feed = {c.id: c for c in feed_cases if c.id.startswith('thread-')}
    report = {'journal_threads': len(summaries), 'ended': 0, 'open': 0, 'in_feed': 0,
              'missing_in_feed': [], 'dealer_mismatch': [], 'price_not_in_feed': [], 'side_mismatch': []}
    for t in summaries:
        report['ended' if t['status'] in ENDED else 'open'] += 1
        c = feed.get(f"thread-{t['thread']}")
        if c is None:
            report['missing_in_feed'].append(t['thread'])
            continue
        report['in_feed'] += 1
        if c.dealer != t['dealer']:
            report['dealer_mismatch'].append(t['thread'])
            continue
        if c.side not in ('unknown', t['side']) and t['side'] != 'unknown':
            report['side_mismatch'].append(t['thread'])
        if t['status'] == 'deal' and t['price'] is not None:
            seen = {m.get('price') for m in json.loads(c.body).get('messages', [])}
            if t['price'] not in seen:
                report['price_not_in_feed'].append(t['thread'])
    report['ok'] = not (report['dealer_mismatch'] or report['price_not_in_feed'] or report['side_mismatch'])
    return report


def read_feed(path):
    """Raw feed events saved by scout.py --save / run_dashboard.py; same torn-line tolerance as read()."""
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.endswith('\n'):
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    return list({r['id']: r for r in rows if isinstance(r, dict) and 'id' in r}.values())
