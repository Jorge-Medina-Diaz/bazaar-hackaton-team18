"""Pure checks shared by the haggler and its offline tests."""


def _cash(side):
    cash = side.get('cash', 0)
    if type(cash) is not int or not 0 <= cash <= 10_000_000:
        raise ValueError('Invalid cash')
    return cash


def offer_ok(offer, topic, buying=True):
    """Check exactly one requested item, or exactly the assets we chose to sell."""
    try:
        give, want = offer['give'], offer['want']
        if buying:
            item = topic['buy']
            kind, ref = ('pack', item['pack']) if 'pack' in item else ('card', item['card'])
            got = list(give.get('types') or []) + [f"{a['kind']}:{a['ref']}" for a in give.get('assets') or []]
            return (not want.get('assets') and not want.get('types') and _cash(give) == 0
                    and _cash(want) >= 1 and len(got) == 1 and got[0] == f'{kind}:{ref}')
        expected = topic['sell']['assets']
        ids = [a['id'] if isinstance(a, dict) else a for a in want.get('assets') or []]
        return (bool(expected) and all(type(i) is int and i > 0 for i in ids + expected)
                and len(ids) == len(set(ids)) and sorted(ids) == sorted(expected)
                and not want.get('types') and _cash(want) == 0 and _cash(give) >= 1
                and not give.get('assets') and not give.get('types'))
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def executable_offer(offer, topic, *, dealer, team, tick, buying=True):
    try:
        return (offer['maker'] == dealer and offer.get('to') == team
                and offer['status'] == 'open'
                and type(offer['id']) is int and offer['id'] > 0
                and (offer.get('expires_tick') is None or offer['expires_tick'] >= tick)
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
