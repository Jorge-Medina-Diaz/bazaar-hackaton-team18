"""Experimental market policy and local decision gate, NOT wired into run_loop.

The gate must be owned by one executor. It is not a distributed lock or an API
idempotency guarantee. Uncertain writes remain pending until reconciliation.
"""
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
import math

from market import fee
from run_loop import MIN_GAIN, RESERVE, best_trade

NONE = (0, None, None, None)


def baseline(api, me, clock):
    choice = best_trade(api, me)
    return choice if choice[0] >= MIN_GAIN else NONE


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def available(me, clock, offers):
    """Conservative policy: resolve outstanding writes before choosing again."""
    return (clock.get('ready') is True and not clock.get('paused', True)
            and type(clock.get('tick')) is int and clock['tick'] >= 0
            and type(clock.get('accepts_used')) is int
            and type(clock.get('limits', {}).get('accepts_per_team_per_tick')) is int
            and 0 <= clock['accepts_used'] < clock['limits']['accepts_per_team_per_tick']
            and type(me.get('cash')) is int and me['cash'] >= 0
            and not any(o.get('status') in ('queued', 'accepted', 'unknown') for o in offers))


def candidates(me, clock, mine, board, values, *, reserve=RESERVE):
    """Enumerate valid single-card cash trades using supplied marginal values.

    No page bonus is added: API your_value already contains it. One call site's
    snapshot is not authorization; DecisionGate checks the refreshed state.
    """
    if not available(me, clock, mine):
        return []
    own = {o['id'] for o in mine if o.get('maker') == me['id']}
    listed = {a['id'] for o in mine if o.get('maker') == me['id']
              and o.get('status') in ('open', 'queued', 'accepted')
              for a in o.get('give', {}).get('assets', [])}
    held = {}
    for a in me.get('assets', []):
        if (a.get('kind') == 'card' and not a.get('locked') and a['id'] not in listed
                and _number(a.get('your_value'))):
            held.setdefault(a['ref'], a)
    out, seen = [], set()
    for o in board + [o for o in mine if o.get('to') == me['id']]:
        oid = o.get('id')
        if (type(oid) is not int or oid <= 0 or oid in seen or oid in own
                or o.get('maker') == me['id'] or not o.get('maker')
                or o.get('status') != 'open' or o.get('to') not in (None, me['id'])
                or o.get('venue') != 'rastro'):
            continue
        seen.add(oid)
        expiry = o.get('expires_tick')
        if expiry is not None and (type(expiry) is not int or expiry < clock['tick']):
            continue
        g, w = o.get('give', {}), o.get('want', {})
        if not isinstance(g, dict) or not isinstance(w, dict):
            continue
        buy = (len(g.get('assets') or []) == 1 and not g.get('cash') and not g.get('types')
               and not w.get('assets') and not w.get('types'))
        sell = (not g.get('assets') and not g.get('types') and not w.get('assets')
                and not w.get('cash') and len(w.get('types') or []) == 1)
        price = w.get('cash') if buy else g.get('cash') if sell else None
        if type(price) is not int or not 1 <= price <= 10_000_000:
            continue
        charge = fee(price)
        if buy:
            asset = g['assets'][0]
            if not isinstance(asset, dict) or asset.get('kind') != 'card':
                continue
            if me['cash'] - price - charge < reserve:
                continue
            value = values.get(asset.get('ref'))
            if not _number(value):
                continue
            choice = (round(value - price - charge, 1), 'BUY', o, None)
        else:
            typ = w['types'][0]
            if not isinstance(typ, str) or not typ.startswith('card:'):
                continue
            asset = held.get(typ[5:])
            # Fees are paid at acceptance; do not assume unsettled proceeds can fund them.
            if asset is None or me['cash'] - charge < reserve:
                continue
            choice = (round(price - charge - asset['your_value'], 1), 'SELL', o, asset['id'])
        if choice[0] >= MIN_GAIN:
            out.append(choice)
    return out


def candidate(api, me, clock):
    """A benchmark candidate, not a deployed replacement for the current agent."""
    mine = api.my_offers()['offers']
    if not available(me, clock, mine):
        return NONE
    board = api.board('rastro').get('offers', [])
    class Values(dict):
        def get(self, ref, default=None):
            if not isinstance(ref, str):
                return default
            if ref not in self:
                self[ref] = api.value(ref)['your_value']
            return self[ref]

    values = Values()  # scoped to this decision; never reuse stale marginal values
    return max(candidates(me, clock, mine, board, values), key=lambda c: c[0], default=NONE)


def signature(me, clock, mine, board, values):
    data = dict(me=me, clock=clock, mine=mine, board=board, values=values)
    return hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Proposal:
    choice: tuple
    state: str
    tick: int


def propose(choice, me, clock, mine, board, values):
    return Proposal(deepcopy(choice), signature(me, clock, mine, board, values), clock['tick'])


@dataclass
class DecisionGate:
    """An experimental single-executor arbiter. No network calls or game writes."""
    used: dict = field(default_factory=dict)
    pending: set = field(default_factory=set)

    def authorize(self, proposal, me, clock, mine, board, values):
        if self.pending:
            return False, 'pending_reconciliation'
        if proposal.tick != clock['tick']:
            return False, 'late_tick'
        if proposal.state != signature(me, clock, mine, board, values):
            return False, 'state_changed'
        limit = clock['limits']['accepts_per_team_per_tick']
        if self.used.get(clock['tick'], 0) >= limit:
            return False, 'accept_quota'
        valid = candidates(me, clock, mine, board, values)
        if not any(proposal.choice == c for c in valid):
            return False, 'invalid_choice'
        oid = proposal.choice[2]['id']
        self.used = {clock['tick']: self.used.get(clock['tick'], 0) + 1}
        self.pending.add(oid)  # reserve before POST; timeout must not release it
        return True, 'reserved'

    def reconcile(self, oid, status):
        if status not in ('settled', 'cancelled', 'expired', 'failed'):
            raise ValueError('A known terminal status is required')
        self.pending.discard(oid)
