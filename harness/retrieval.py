"""Experimental retrieval for RAG: provenance, structured scope and local BM25.

No generation, model, API, or execution. Historical evidence is not current state.
"""
from dataclasses import asdict, dataclass
import json
import re
import sqlite3
import unicodedata
from typing import Optional


@dataclass(frozen=True)
class MemoryCase:
    id: str
    dealer: str
    side: str
    item: str
    phase: str
    body: str
    source: str
    evidence: str
    tick: Optional[int]
    visibility: str = 'public'
    version: str = 'oct2-observations'
    status: str = 'active'


@dataclass(frozen=True)
class Scope:
    dealer: str
    side: str
    item: str = ''
    phase: str = ''
    team: str = 'local-team'
    version: str = 'oct2-observations'


def in_scope(case, scope):
    return (case.dealer == scope.dealer and case.side == scope.side
            and (not scope.item or case.item == scope.item)
            and (not scope.phase or case.phase == scope.phase)
            and case.visibility in ('public', scope.team)
            and case.version == scope.version and case.status == 'active')


def contextual(case):
    role = {'buy': 'compra', 'sell': 'venta', 'unknown': 'lado desconocido'}.get(case.side, case.side)
    stage = {'final': 'oferta final última propuesta', 'repeated': 'precio repetido estancamiento',
             'closed': 'conversación cerrada', 'settled': 'liquidación confirmada',
             'negotiation': 'negociación', 'policy': 'criterio económico',
             'coordination': 'conflicto entre operadores'}.get(case.phase, case.phase)
    tick = case.tick if case.tick is not None else 'desconocido'
    return f'Dealer {case.dealer}. {role} {case.item}. {stage}. Tick {tick}.\n{case.body}'


def tokens(text):
    normal = ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))
    stop = {'de', 'del', 'la', 'el', 'los', 'las', 'un', 'una', 'en', 'a', 'y', 'o', 'con', 'por', 'para',
            'que', 'se', 'si', 'como', 'cuando', 'al', 'lo', 'su', 'me', 'nos', 'the', 'of', 'to', 'and', 'is'}
    return list(dict.fromkeys(t for t in re.findall(r'[a-z0-9_]+', normal) if t not in stop))[:32]


class MemoryIndex:
    def __init__(self, cases):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.cases = list(cases)
        if len({c.id for c in self.cases}) != len(self.cases):
            raise ValueError('Duplicate evidence IDs')
        self.db.execute('CREATE TABLE cases (id TEXT PRIMARY KEY, dealer TEXT, side TEXT, item TEXT, '
                        'phase TEXT, body TEXT, source TEXT, evidence TEXT, tick INTEGER, '
                        'visibility TEXT, version TEXT, status TEXT)')
        for table in ('raw_fts', 'context_fts'):
            self.db.execute(f"CREATE VIRTUAL TABLE {table} USING fts5(body, tokenize='unicode61 remove_diacritics 2')")
        for rowid, c in enumerate(self.cases, 1):
            self.db.execute('INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', tuple(asdict(c).values()))
            self.db.execute('INSERT INTO raw_fts(rowid,body) VALUES (?,?)', (rowid, c.body))
            self.db.execute('INSERT INTO context_fts(rowid,body) VALUES (?,?)', (rowid, contextual(c)))
        self.db.commit()

    def close(self):
        self.db.close()

    def retrieve(self, question, scope, *, mode='contextual_fts', k=3, byte_budget=8000):
        if k < 1 or byte_budget < 2:
            raise ValueError('Invalid retrieval limits')
        if mode not in ('none', 'recent_sql', 'global_fts', 'scoped_fts', 'contextual_fts', 'fused_fts'):
            raise ValueError('Unknown retrieval mode')
        if mode == 'none':
            return [], 0
        where = "c.dealer=? AND c.side=? AND c.visibility IN ('public',?) AND c.version=? AND c.status='active'"
        args = [scope.dealer, scope.side, scope.team, scope.version]
        if scope.item:
            where += ' AND c.item=?'
            args.append(scope.item)
        if scope.phase:
            where += ' AND c.phase=?'
            args.append(scope.phase)
        if mode == 'fused_fts':
            ranks, packets = {}, {}
            for component in ('scoped_fts', 'contextual_fts'):
                shortlist, _ = self.retrieve(question, scope, mode=component, k=k * 8, byte_budget=1_000_000)
                for rank, packet in enumerate(shortlist, 1):
                    oid = packet['id']
                    ranks[oid] = ranks.get(oid, 0) + 1 / (60 + rank)
                    packets[oid] = packet
            rows = [packets[oid] for oid in sorted(ranks, key=lambda oid: (-ranks[oid], oid))]
        elif mode == 'recent_sql':
            rows = self.db.execute('SELECT c.* FROM cases c WHERE ' + where + ' ORDER BY tick DESC,id LIMIT ?',
                                   [*args, k * 8]).fetchall()
        else:
            terms = tokens(question)
            if not terms:
                return [], 0
            expression = ' OR '.join('"' + t + '"' for t in terms)  # no user FTS operators or SQL interpolation
            table = 'context_fts' if mode == 'contextual_fts' else 'raw_fts'
            restriction = '' if mode == 'global_fts' else ' AND ' + where
            params = [expression] + ([] if mode == 'global_fts' else args) + [k * 8]
            rows = self.db.execute(f'SELECT c.* FROM {table} JOIN cases c ON c.rowid={table}.rowid '
                                   f'WHERE {table} MATCH ?{restriction} ORDER BY bm25({table}),c.id LIMIT ?', params).fetchall()
        selected, omitted = [], 0
        for row in rows:
            packet = dict(row)
            packet['authority'] = 'historical_evidence_only'
            attempt = json.dumps([*selected, packet], ensure_ascii=False, separators=(',', ':')).encode()
            if len(attempt) > byte_budget:
                omitted += 1  # never cut a price sequence or detach a statement from its source
                continue
            selected.append(packet)
            if len(selected) == k:
                break
        return selected, omitted


def _refs(side):
    result = []
    for a in side.get('assets') or []:
        if isinstance(a, dict) and a.get('ref'):
            result.append(a['ref'])
    result += [t.split(':', 1)[1] for t in side.get('types') or [] if isinstance(t, str) and ':' in t]
    return result


def import_feed(events, source):
    """One chunk per thread; no inferred settlement-to-thread join."""
    groups, settlements = {}, []
    for event in sorted(events, key=lambda e: e['id']):
        if event.get('scope') != 'public':
            continue
        p = event.get('payload', {})
        dealer = p.get('with') or p.get('persona')
        if dealer not in ('abuela', 'chato'):
            continue
        tid = p.get('thread')
        if tid is not None:
            group = groups.setdefault(tid, {'dealer': dealer, 'rows': []})
            group['rows'].append(event)
        elif event['type'] == 'settlement':
            items = p.get('items', [])
            refs = sorted({a['ref'] for a in items if isinstance(a, dict) and a.get('ref')})
            direction = 'buy' if items and all(a.get('frm') == dealer for a in items) else 'sell' if items and all(a.get('to') == dealer for a in items) else 'unknown'
            body = json.dumps({'price': p.get('price'), 'items': refs, 'fee': p.get('fee'),
                               'settlement': p.get('settlement'), 'thread_association': 'unavailable'}, ensure_ascii=False)
            settlements.append(MemoryCase(f'settlement-{p["settlement"]}', dealer, direction,
                                          refs[0] if len(refs) == 1 else 'bundle', 'settled', body,
                                          source + f'#event={event["id"]}', 'public_settlement', event['tick']))
    cases, complete = [], 0
    for tid, group in groups.items():
        rows = group['rows']
        opened = next((e['payload'] for e in rows if e['type'] == 'thread.opened'), {})
        topic = opened.get('topic') or {}
        side = 'buy' if 'buy' in topic else 'sell' if 'sell' in topic else 'unknown'
        item = next(iter((topic.get('buy') or {}).values()), '') if side == 'buy' else ''
        refs, dealer_prices, messages = [], [], []
        final, closed = False, False
        for e in rows:
            p = e['payload']
            o = p.get('offer') or {}
            g, w = o.get('give') or {}, o.get('want') or {}
            refs += _refs(g) + _refs(w)
            is_dealer = p.get('sender') == group['dealer']
            if side == 'unknown' and o and bool(_refs(g)) != bool(_refs(w)):
                card_side = g if _refs(g) else w
                side = 'buy' if (card_side is g) == is_dealer else 'sell'
            if e['type'] == 'thread.message':
                price = w.get('cash') or g.get('cash')
                messages.append({'tick': e['tick'], 'role': 'dealer' if is_dealer else 'team',
                                 'price': price, 'final': bool(o.get('final')),
                                 'refs': _refs(g) + _refs(w),
                                 'text': p.get('text') if is_dealer else None})
                if is_dealer and type(price) is int:
                    dealer_prices.append(price)
                    final |= bool(o.get('final'))
            closed |= e['type'] == 'thread.closed'
        refs = sorted(set(refs))
        item = item or (refs[0] if len(refs) == 1 else 'bundle' if refs else 'unknown')
        phase = 'closed' if closed else 'final' if final else 'repeated' if any(a == b for a, b in zip(dealer_prices, dealer_prices[1:])) else 'negotiation'
        body = json.dumps({'opening_visible': bool(opened), 'dealer_prices': dealer_prices,
                           'outcome': 'closed' if closed else 'unknown_in_feed_window', 'messages': messages}, ensure_ascii=False)
        complete += bool(opened)
        cases.append(MemoryCase(f'thread-{tid}', group['dealer'], side, item, phase, body,
                                source + f'#thread={tid}', 'public_partial_thread', max(e['tick'] for e in rows)))
    return cases + settlements, {'threads': len(cases), 'threads_with_opening': complete,
                                'settlements': len(settlements), 'settlement_thread_joins': 0,
                                'dealer_texts_only': True}
