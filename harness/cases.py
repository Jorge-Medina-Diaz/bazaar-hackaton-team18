"""Synthetic fixtures with independent expected choices, not game snapshots."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import random


def offer(oid=1, price=5, *, ref='SAL-01', buying=True, **changes):
    row = dict(id=oid, maker='fixture-rival', status='open', venue='rastro',
               to=None, expires_tick=20,
               give={'assets': [{'id': 900 + oid, 'kind': 'card', 'ref': ref}]} if buying else {'cash': price},
               want={'cash': price} if buying else {'types': ['card:' + ref]})
    row.update(changes)
    return row


@dataclass
class Case:
    name: str
    board: list = field(default_factory=lambda: [offer()])
    mine: list = field(default_factory=list)
    me: dict = field(default_factory=lambda: dict(id='fixture-team', cash=400, assets=[]))
    clock: dict = field(default_factory=lambda: dict(tick=10, ready=True, paused=False, accepts_used=0,
                          limits={'accepts_per_team_per_tick': 1}))
    values: dict = field(default_factory=lambda: {'SAL-01': 20})
    expected: int | None = 1
    expected_gain: float = 13
    max_value_calls: int = 1
    allowed_ids: tuple | None = None  # admissible choices; expected is the optimal one


def fixtures(seed=7, runs=100):
    cases = [Case('buy_valid'), Case('same_card_ten_offers', board=[offer(i) for i in range(1, 11)],
                                  allowed_ids=tuple(range(1, 11))),
             Case('choose_cheapest', board=[offer(1, 10), offer(2, 5)], expected=2, allowed_ids=(1, 2)),
             Case('two_card_values', board=[offer(), offer(2, 10, ref='LAT-02')],
                  values={'SAL-01': 20, 'LAT-02': 35}, expected=2, expected_gain=23, max_value_calls=2,
                  allowed_ids=(1, 2)),
             Case('valid_alternative_to_expired', board=[offer(expires_tick=9), offer(2, 10)],
                  expected=2, expected_gain=8)]
    for name, change in [('expired', {'expires_tick': 9}), ('wrong_recipient', {'to': 'another-team'}),
                         ('cancelled', {'status': 'cancelled'}), ('wrong_venue', {'venue': 'unknown'}),
                         ('own_offer', {'maker': 'fixture-team'})]:
        cases.append(Case(name, board=[offer(**change)], expected=None, expected_gain=0, max_value_calls=0))
    for name, change in [('paused', {'paused': True}), ('stale_context', {'ready': False}),
                         ('accept_already_used', {'accepts_used': 1}),
                         ('live_quota_zero', {'limits': {'accepts_per_team_per_tick': 0}})]:
        c = Case(name, expected=None, expected_gain=0, max_value_calls=0)
        c.clock.update(change)
        cases.append(c)
    cases.append(Case('insufficient_reserve', me={'id': 'fixture-team', 'cash': 155, 'assets': []},
                      expected=None, expected_gain=0, max_value_calls=0))
    for status in ('queued', 'unknown'):
        cases.append(Case('write_' + status, mine=[offer(40, status=status, maker='fixture-team')],
                          expected=None, expected_gain=0, max_value_calls=0))
    for name, give, want in [('pack_instead_of_card', {'assets': [{'id': 1, 'kind': 'pack', 'ref': 'SAL-01'}]}, {'cash': 5}),
                              ('extra_cash', {'assets': [{'id': 1, 'kind': 'card', 'ref': 'SAL-01'}], 'cash': 1}, {'cash': 5}),
                              ('boolean_price', {'assets': [{'id': 1, 'kind': 'card', 'ref': 'SAL-01'}]}, {'cash': True})]:
        cases.append(Case(name, board=[offer(give=give, want=want)], expected=None, expected_gain=0,
                          max_value_calls=0))
    held = {'id': 7, 'kind': 'card', 'ref': 'SAL-01', 'your_value': 2}
    sale_me = {'id': 'fixture-team', 'cash': 400, 'assets': [held]}
    cases.append(Case('sell_duplicate', board=[offer(price=20, buying=False)], me=deepcopy(sale_me),
                      expected_gain=16, max_value_calls=0))
    locked = deepcopy(sale_me)
    locked['assets'][0]['locked'] = True
    cases.append(Case('locked_card', board=[offer(price=20, buying=False)], me=locked,
                      expected=None, expected_gain=0, max_value_calls=0))
    cases.append(Case('valid_alternative_to_locked', board=[offer(price=20, buying=False), offer(2)],
                      me=deepcopy(locked), expected=2))
    listing = offer(50, maker='fixture-team', give={'assets': [held]})
    cases.append(Case('listed_card', board=[offer(price=20, buying=False)], me=deepcopy(sale_me),
                      mine=[listing], expected=None, expected_gain=0, max_value_calls=0))
    high_value = deepcopy(sale_me)
    high_value['assets'][0]['your_value'] = 40
    cases.append(Case('protect_page_value', board=[offer(price=25, buying=False)], me=high_value,
                      expected=None, expected_gain=0, max_value_calls=0))
    cases.append(Case('expiry_equal_tick', board=[offer(expires_tick=10)]))
    cases.append(Case('direct_offer_only', board=[], mine=[offer(to='fixture-team')]))
    # Known optimum derives from the generated lowest price. No selector is used as oracle.
    rng = random.Random(seed)
    for i in range(runs):
        prices = rng.sample(range(2, 45), rng.randint(2, 12))
        cheapest = min(prices)
        value = rng.randint(55, 95)
        charge = (cheapest + 19) // 20 + 1  # independent integer expression for 5% rounded up +1
        cases.append(Case(f'seeded-{i:03}', board=[offer(j + 1, p) for j, p in enumerate(prices)],
                          values={'SAL-01': value}, expected=prices.index(cheapest) + 1,
                          expected_gain=value - cheapest - charge, allowed_ids=tuple(range(1, len(prices) + 1))))
    return cases
