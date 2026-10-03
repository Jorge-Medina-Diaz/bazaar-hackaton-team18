"""Public observations, not inferred causal effects or private opponent values."""
from collections import Counter, defaultdict
import json
from statistics import median

from harness.retrieval import import_feed


def summarize_public_history(events, own_team='t18'):
    cases, coverage = import_feed(events, 'public-feed')
    threads = [c for c in cases if c.evidence == 'public_partial_thread']
    settlements = [e for e in events if e.get('scope') == 'public' and e['type'] == 'settlement'
                   and e.get('payload', {}).get('persona') in ('abuela', 'chato')]
    groups, teams = defaultdict(list), set()
    own, rival = 0, 0
    for e in settlements:
        p = e['payload']
        dealer, items = p['persona'], p.get('items', [])
        counterparties = {t for t in p.get('parties', []) if t != dealer}
        teams.update(counterparties)
        if counterparties == {own_team}:
            own += 1
        elif counterparties and own_team not in counterparties:
            rival += 1
        direction = ('buy' if items and all(i.get('frm') == dealer for i in items)
                     else 'sell' if items and all(i.get('to') == dealer for i in items) else 'unknown')
        refs = tuple(sorted(i['ref'] for i in items if i.get('ref')))
        if type(p.get('price')) is int:
            groups[(dealer, direction, refs)].append(p['price'])
    thread_rows = []
    for c in threads:
        body = json.loads(c.body)
        prices = body['dealer_prices']
        thread_rows.append({'id': c.id, 'dealer': c.dealer, 'side': c.side, 'item': c.item,
                            'opening_visible': body['opening_visible'], 'observed_prices': prices,
                            'asks_repeated': any(a == b for a, b in zip(prices, prices[1:])),
                            'ask_reduction': prices[0] - prices[-1] if c.side == 'buy' and prices else None,
                            'outcome': body['outcome']})
    return {'schema_version': 1, 'scope': 'public feed window only, descriptive not causal',
            'events': len(events), 'tick_range': [min(e['tick'] for e in events), max(e['tick'] for e in events)] if events else [],
            'coverage': coverage, 'teams_with_settlements': len(teams),
            'our_settlements': own, 'rival_settlements': rival,
            'unassigned_settlements': len(settlements) - own - rival,
            'settlement_thread_joins': 0, 'opponent_private_values_available': False,
            'dealer_threads': dict(Counter(c.dealer for c in threads)),
            'repeated_ask_threads': sum(r['asks_repeated'] for r in thread_rows),
            'settlement_groups': [{'dealer': d, 'side': side, 'items': list(refs), 'count': len(prices),
                                  'min_price': min(prices), 'median_price': median(prices), 'max_price': max(prices)}
                                 for (d, side, refs), prices in sorted(groups.items())],
            'threads': thread_rows}
