"""The scorer when a new dealer (El Chato) opens: no fills yet, better packs, prices that depend on us."""
import unittest

from agent.scorer import Scorer, Values, dealer_changes
from test_agent_core import snapshot

ABUELA = {'id': 'abuela', 'name': 'Abuela Carmen', 'status': 'active', 'level': 1,
          'unlock': {'always': True, 'early_min_deals': 3},
          'menu': {'sells': [{'pack': 'sobre_barrio', 'list_price': 26, 'opening_ask': 30, 'per_team_per_hour': 3},
                             {'rarity': 'common', 'sets': 'released', 'list_price': 10},
                             {'rarity': 'uncommon', 'sets': 'released', 'list_price': 25}],
                   'buys': [{'rarity': 'common', 'sets': 'released'}], 'deals_per_team_per_hour': 8}}
CHATO = {'id': 'chato', 'name': 'El Chato', 'status': 'active', 'level': 2,
         'unlock': {'early_deals_with': 'abuela', 'early_min_deals': 3}, 'open_to_all': False,
         'menu': {'sells': [{'pack': 'sobre_plata', 'list_price': 120, 'opening_ask': 150, 'per_team_per_hour': 2},
                            {'rarity': 'uncommon', 'sets': 'released', 'list_price': 20},
                            {'rarity': 'rare', 'sets': 'released', 'list_price': 60}],
                  'buys': [{'rarity': 'rare', 'sets': 'released'}], 'deals_per_team_per_hour': 6}}
ANNOUNCED = {'id': 'chato', 'name': 'El Chato', 'status': 'announced', 'level': None,
             'teaser': '«Better packs, friendly prices. If I like you.»'}
PACKS = [{'id': 'sobre_barrio', 'name': 'Neighbourhood pack', 'expected_book': 33.8,
          'slots': [{'common': 1.0}, {'common': 1.0}, {'common': 0.75, 'uncommon': 0.25}]},
         {'id': 'sobre_plata', 'name': 'Silver pack', 'expected_book': 160.8,
          'slots': [{'common': 1.0}, {'common': 1.0}, {'uncommon': 1.0}, {'uncommon': 1.0},
                    {'rare': 0.86, 'epic': 0.12, 'legendary': 0.02}]}]


def fill(ref, rarity, price, dealer, side, buyer, seller, kind='card', event=1):
    return {'event': event, 'tick': event, 'ref': ref, 'kind': kind, 'rarity': rarity, 'price': price,
            'venue': None, 'dealer': dealer, 'side': side, 'seller': seller, 'buyer': buyer, 'bundle': 1}


def world(dealers, unlocked=None, history=(), held=()):
    snap = snapshot(held)
    snap.dealers = dealers
    snap.catalog = {'values': {}, 'packs': PACKS}
    for c in snap.cards.values():
        c.setdefault('minted', 1)
        c.setdefault('print_run', 300)
    if unlocked is not None:
        snap.me['unlocked'] = unlocked
    return snap, Scorer(snap, Values(snap), list(history))


class NewDealerTests(unittest.TestCase):
    def test_announced_dealer_does_not_price_anything(self):
        _, s = world([ABUELA, ANNOUNCED], unlocked=['abuela'])
        self.assertEqual(s.card('SAL-02')['buy_via'], 'abuela')
        self.assertIsNone(s.card('SAL-03')['buy_at'])  # nobody sells rares yet

    def test_fresh_dealer_is_priced_from_its_menu(self):
        _, s = world([ABUELA, CHATO], unlocked=['abuela', 'chato'])
        row = s.card('SAL-02')
        self.assertEqual((row['buy_at'], row['buy_via']), (20, 'chato'))  # cheaper than Abuela's 25
        self.assertEqual(s.card('SAL-03')['buy_at'], 60)                  # a new source of rares

    def test_locked_dealer_does_not_set_buy_at(self):
        _, s = world([ABUELA, CHATO], unlocked=['abuela'])
        self.assertEqual(s.card('SAL-02')['buy_via'], 'abuela')
        self.assertIsNone(s.card('SAL-03')['buy_at'])
        plata = next(p for p in s.pack_ev() if p['pack'] == 'sobre_plata')
        self.assertEqual((plata['seller'], plata['can_trade'], plata['typical_price']), ('chato', False, 120))

    def test_our_fills_outrank_other_teams(self):
        others = [fill('SAL-03', 'rare', 80, 'chato', 'dealer_sells', 't01', 'chato', event=i) for i in range(4)]
        ours = [fill('SAL-03', 'rare', 55, 'chato', 'dealer_sells', 'fixture-team', 'chato', event=9)]
        _, s = world([CHATO], unlocked=['chato'], history=others + ours)
        self.assertEqual(s.dealer_estimate('chato', 'dealer_sells', 'SAL-03'), (55, 'chato our fills'))
        _, s = world([CHATO], unlocked=['chato'], history=others)
        self.assertEqual(s.dealer_estimate('chato', 'dealer_sells', 'SAL-03'), (80, 'chato fills'))

    def test_pack_prices_never_pool_across_pack_types(self):
        barrio = [fill('sobre_barrio', 'pack', 23, 'abuela', 'dealer_sells', 't01', 'abuela', kind='pack', event=i)
                  for i in range(3)]
        _, s = world([ABUELA, CHATO], unlocked=['abuela', 'chato'], history=barrio)
        self.assertEqual(s.dealer_estimate('chato', 'dealer_sells', 'sobre_plata'), (120, 'chato list'))

    def test_unsold_pack_is_still_scored(self):
        _, s = world([ABUELA, ANNOUNCED], unlocked=['abuela'])
        plata = next(p for p in s.pack_ev() if p['pack'] == 'sobre_plata')
        self.assertIsNone(plata['seller'])
        self.assertGreater(plata['ev_to_us'], 0)

    def test_sold_out_rarity_falls_to_the_next_one_down(self):
        snap, s = world([CHATO], unlocked=['chato'])
        before = s.pull_values()
        snap.cards['SAL-11']['minted'] = snap.cards['SAL-11']['print_run']  # every epic minted
        after = Scorer(snap, Values(snap), []).pull_values()
        self.assertEqual(after['epic'], before['rare'])
        self.assertEqual(after['legendary'], before['legendary'])

    def test_ladder_and_unlock_progress(self):
        quotes_free = [fill('SAL-02', 'uncommon', p, 'abuela', 'dealer_sells', 'fixture-team', 'abuela', event=i)
                       for i, p in enumerate((22, 24, 23))]
        _, s = world([ABUELA, CHATO], unlocked=['abuela'], history=quotes_free)
        lad = {d['dealer']: d for d in s.ladder()}
        self.assertEqual((lad['abuela']['deals'], lad['abuela']['open_slots']), (3, 0))
        self.assertEqual((lad['chato']['deals'], lad['chato']['open_slots'], lad['chato']['unlock_after']), (0, 3, 'abuela'))
        self.assertFalse(lad['chato']['can_trade'])

    def test_unlock_counts_only_deals_away_from_the_opening_price(self):
        def thread(prices, settled_at):
            msgs = [{'offer': {'maker': maker, 'status': 'settled' if i == settled_at else 'open',
                               'give': {'types': ['pack:sobre_barrio']} if maker == 'abuela' else {'cash': p},
                               'want': {'cash': p} if maker == 'abuela' else {'types': ['pack:sobre_barrio']}}}
                    for i, (maker, p) in enumerate(prices)]
            return {'kind': 'persona', 'with': 'abuela', 'status': 'deal',
                    'topic': {'buy': {'pack': 'sobre_barrio'}}, 'messages': msgs}
        snap, _ = world([ABUELA, CHATO], unlocked=['abuela'])
        snap.my_threads = [thread([('abuela', 17)], 0),                                  # took her opening ask
                           thread([('abuela', 30), ('fixture-team', 18), ('abuela', 24)], 2),
                           {'kind': 'persona', 'with': 'abuela', 'status': 'closed', 'messages': []}]
        lad = {d['dealer']: d for d in Scorer(snap, Values(snap), []).ladder()}
        self.assertEqual((lad['abuela']['deals'], lad['abuela']['negotiated']), (2, 1))

    def test_alert_when_a_dealer_opens(self):
        seen = {}
        rep = lambda status, trade: {'dealers': [{'dealer': 'chato', 'name': 'El Chato', 'status': status,
                                                   'level': 2 if status == 'active' else None,
                                                   'can_trade': trade, 'teaser': None}]}
        self.assertEqual(dealer_changes(seen, rep('announced', False)), [])
        self.assertEqual(dealer_changes(seen, rep('announced', False)), [])
        self.assertIn('OPEN TO US', dealer_changes(seen, rep('active', True))[0])


if __name__ == '__main__':
    unittest.main()
