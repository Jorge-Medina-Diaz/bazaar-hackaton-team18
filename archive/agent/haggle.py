"""Jorge's concession curve with Codex validation and settlement controls.

Nothing runs on import. The caller supplies a client and explicit limits.
"""
raise SystemExit("ARCHIVED by M18: pre-harness script that could reach the game without the Gate. Use the harness: python3 bazaar.py (see CLAUDE.md).")  # M18 guard
import math

from agent.execution import team_writer
from agent.journal import log
from agent.offer_safety import executable_offer, offer_ok, settled_price


def curve(k, anchor, limit, rounds, beta):
    return round(anchor + (limit - anchor) * min(1.0, k / rounds) ** (1 / beta))


def haggle(b, dealer, topic, *, anchor, limit, rounds, beta, lines,
           buying=True, reserve_cash=0):
    """Same interface as Jorge's engine; adds an optional liquidity reserve."""
    if (any(type(x) is not int for x in (anchor, limit, rounds, reserve_cash))
        or not 1 <= anchor <= 10_000_000 or not 1 <= limit <= 10_000_000
        or rounds < 1 or reserve_cash < 0 or not lines
        or type(beta) not in (float, int) or not math.isfinite(beta) or beta <= 0
        or (buying and anchor > limit) or (not buying and anchor < limit)):
        raise ValueError('Invalid negotiation configuration')
    if buying:
        item = topic.get('buy', {})
        if len(item) != 1 or not any(isinstance(item.get(key), str) and item[key]
                                     for key in ('card', 'pack')):
            raise ValueError('An exact card or pack topic is required')
    else:
        ids = topic.get('sell', {}).get('assets', [])
        if (not ids or any(type(i) is not int or i < 1 for i in ids)
            or len(ids) != len(set(ids))):
            raise ValueError('Distinct asset IDs required')
    me = b.me()
    team = me.get('id') or me.get('team')
    with team_writer(team):
        # Refresh after obtaining the lock; do not take over another conversation.
        me = b.me()
        if me.get('open_threads'):
            raise RuntimeError('Existing conversation: reconcile before opening another')
        if buying and me['cash'] - reserve_cash < anchor:
            raise ValueError('Insufficient unreserved cash for the opening offer')
        if not buying:
            owned = {a['id'] for a in me.get('assets', []) if not a.get('locked')}
            if not set(ids) <= owned:
                raise ValueError('Sale assets unavailable')
        return _run(b, dealer, topic, team=team, anchor=anchor, limit=limit,
                    rounds=rounds, beta=beta, lines=lines, buying=buying,
                    reserve_cash=reserve_cash)


def _run(b, dealer, topic, *, team, anchor, limit, rounds, beta, lines, buying, reserve_cash):
    tid = b.open_thread(dealer, topic=topic)['id']
    k, last, pending = 0, None, None
    better = (lambda a, x: a <= x) if buying else (lambda a, x: a >= x)
    side = 'want' if buying else 'give'
    log(dealer, event='open', thread=tid, topic=topic, anchor=anchor, limit=limit)
    while True:
        t, clock = b.thread(tid), b.clock()
        if t['status'] != 'open':
            price = settled_price(t, topic, team=team, dealer=dealer, buying=buying)
            log(dealer, event='end', thread=tid, status=t['status'], price=price,
                reason=t.get('closed_reason'))
            return {'status': t['status'], 'price': price, 'thread': tid,
                    'confirmed': t['status'] == 'deal' and price is not None}
        if pending is None:
            queued = [m['offer']['id'] for m in t.get('messages', [])
                      if (m.get('offer') or {}).get('status') in ('queued', 'accepted')
                      and m['offer'].get('maker') in (team, dealer)]
            if queued:
                pending = queued[-1]
        if pending is not None:
            statuses = [m['offer']['status'] for m in t.get('messages', [])
                        if (m.get('offer') or {}).get('id') == pending]
            if statuses and statuses[-1] in ('cancelled', 'expired', 'failed'):
                pending = None
            else:
                log(dealer, event='pending', thread=tid, offer=pending, tick=clock['tick'])
                b.wait_tick()
                continue
        if clock.get('paused'):
            b.wait_tick()
            continue
        hers = [o for o in t.get('standing_offers', [])
                if executable_offer(o, topic, dealer=dealer, team=team,
                                    tick=clock['tick'], buying=buying)]
        if not hers:
            b.wait_tick()
            continue
        offer = hers[-1]
        her, final = offer[side]['cash'], bool(offer.get('final'))
        available = max(0, b.me()['cash'] - reserve_cash) if buying else limit
        effective = min(limit, available) if buying else limit
        nxt = curve(k, anchor, limit, rounds, beta)
        if last is not None:
            nxt = max(last + 1, nxt) if buying else min(last - 1, nxt)
        if buying:
            nxt = min(nxt, effective)
        improving = last is None or (nxt > last if buying else nxt < last)
        valid = 1 <= nxt <= 10_000_000 and better(nxt, effective)
        if better(her, effective) and (better(her, nxt) or final or k >= rounds):
            log(dealer, event='accept_intent', thread=tid, price=her, tick=clock['tick'])
            result = b.accept(offer['id'])
            pending = offer['id']
            log(dealer, event='accept_queued', thread=tid, offer=pending, response=result)
        elif final or not valid or not improving:
            log(dealer, event='walk', thread=tid, price=her, tick=clock['tick'])
            b.close_thread(tid)
        else:
            text = lines[k % len(lines)].format(p=nxt)
            log(dealer, event='offer_intent', thread=tid, price=nxt, tick=clock['tick'])
            result = b.say(tid, text, price=nxt)
            log(dealer, event='offer_sent', thread=tid, price=nxt, response=result)
            last, k = nxt, k + 1
        b.wait_tick()
