"""Pure checks shared by the haggler, the guards (M4a, G32) and their offline tests.

Hardened (M4a): any non-empty key in give/want other than cash/assets/types fails (G11 rule),
asset ids must be positive ints (bool is not int), and a non-dict side fails closed.
"""

from collections.abc import Mapping

_SIDE_KEYS = frozenset({'cash', 'assets', 'types'})


def _cash(side):
    cash = side.get('cash', 0)
    if type(cash) is not int or not 0 <= cash <= 10_000_000:
        raise ValueError('Invalid cash')
    return cash


def _clean_side(side):
    """A side must be a dict whose only non-empty keys are cash/assets/types (lists for the last two)."""
    if not isinstance(side, Mapping):           # M17: the Sensor's World is deep-frozen (MappingProxyType)
        raise ValueError('side is not a dict')
    for k, v in side.items():
        if k not in _SIDE_KEYS and v not in (None, 0, '', [], {}):
            raise ValueError(f'unexpected key {k!r}')
        if v is False or v is True:
            raise ValueError('bool value')
    for k in ('assets', 'types'):
        if side.get(k) is not None and not isinstance(side.get(k), (list, tuple)):   # frozen World: tuples
            raise ValueError(f'{k} is not a list')
    return side


def offer_ok(offer, topic, buying=True):
    """Check exactly one requested item, or exactly the assets we chose to sell."""
    try:
        give, want = _clean_side(offer['give']), _clean_side(offer['want'])
        if buying:
            item = topic['buy']
            kind, ref = ('pack', item['pack']) if 'pack' in item else ('card', item['card'])
            for a in give.get('assets') or []:
                if type(a.get('id')) is not int or a['id'] <= 0:
                    return False
            got = list(give.get('types') or []) + [f"{a['kind']}:{a['ref']}" for a in give.get('assets') or []]
            return (not want.get('assets') and not want.get('types') and _cash(give) == 0
                    and _cash(want) >= 1 and len(got) == 1 and got[0] == f'{kind}:{ref}')
        expected = list(topic['sell']['assets'])
        ids = [a['id'] if isinstance(a, Mapping) else a for a in want.get('assets') or []]
        return (bool(expected) and all(type(i) is int and i > 0 for i in ids + expected)
                and len(ids) == len(set(ids)) and sorted(ids) == sorted(expected)
                and not want.get('types') and _cash(want) == 0 and _cash(give) >= 1
                and not give.get('assets') and not give.get('types'))
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def executable_offer(offer, topic, *, dealer, team, tick, buying=True):
    """`tick` is the first tick the offer must still be alive at (G32 passes w.tick + 1, the G10 rule)."""
    try:
        return (offer['maker'] == dealer and offer.get('to') == team
                and offer['status'] == 'open'
                and type(offer['id']) is int and offer['id'] > 0
                and (offer.get('expires_tick') is None
                     or (type(offer['expires_tick']) is int and offer['expires_tick'] >= tick))
                and offer_ok(offer, topic, buying))
    except (KeyError, TypeError):
        return False


def settled_price(thread, topic, *, team, dealer, buying=True):
    """The cash side depends on the maker, not only on whether we are buying."""
    for message in reversed(thread.get('messages', [])):
        offer = message.get('offer') or {}
        if offer.get('status') != 'settled' or offer.get('maker') not in (team, dealer):
            continue
        own = offer['maker'] == team
        normalized = {**offer, 'give': offer.get('want') if own else offer.get('give'),
                      'want': offer.get('give') if own else offer.get('want')}
        if offer_ok(normalized, topic, buying):
            return normalized['want' if buying else 'give']['cash']
    return None
