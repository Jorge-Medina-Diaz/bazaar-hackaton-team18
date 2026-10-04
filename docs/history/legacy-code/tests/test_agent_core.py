import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent.execution import team_writer
from agent.haggle import haggle
from agent.offer_safety import executable_offer, offer_ok, settled_price
from agent.scorer import Scorer, Values


def snapshot(held=(), cash=100):
    cards = {ref: {'id': ref, 'set': 'SAL', 'name': ref, 'book': book, 'rarity': rarity}
             for ref, book, rarity in [('SAL-01', 10, 'common'), ('SAL-02', 25, 'uncommon'),
                                      ('SAL-03', 70, 'rare'), ('SAL-11', 180, 'epic'),
                                      ('SAL-12', 450, 'legendary')]}
    assets = [{'id': i + 1, 'kind': 'card', 'ref': ref, 'your_value': cards[ref]['book']}
              for i, ref in enumerate(held)]
    return SimpleNamespace(cards=cards, sets={'SAL': {'name': 'Fixture', 'released': True,
        'cards': list(cards.values())}}, catalog={'values': {}}, team=None,
        me={'id': 'fixture-team', 'assets': assets, 'cash': cash}, clock={'tick': 5},
        events=[], dealers=[], boards={}, my_offer_ids=set(), venues={}, released=lambda r: True)


def listing(give, want, **extra):
    return {'id': 1, 'maker': 'peer', 'status': 'open', 'give': give, 'want': want, **extra}


class ValuationTests(unittest.TestCase):
    def test_two_incoming_copies_use_distinct_marginals(self):
        values = Values(snapshot())
        self.assertEqual(values.bundle_delta(['SAL-01', 'SAL-01'], []), 12.5)

    def test_two_outgoing_copies_use_distinct_marginals(self):
        values = Values(snapshot(['SAL-01', 'SAL-01']))
        self.assertEqual(values.bundle_delta([], ['SAL-01', 'SAL-01']), -12.5)

    def test_bundle_completes_page_and_adds_bonus_once(self):
        values = Values(snapshot(['SAL-01']))
        self.assertEqual(values.bundle_delta(['SAL-02', 'SAL-03'], []), 121.25)

    def test_breaking_page_removes_bonus_once(self):
        values = Values(snapshot(['SAL-01', 'SAL-02', 'SAL-03']))
        self.assertEqual(values.bundle_delta([], ['SAL-03']), -96.25)

    def test_atomic_swap_of_same_type_preserves_page_and_value(self):
        values = Values(snapshot(['SAL-01', 'SAL-02', 'SAL-03']))
        self.assertEqual(values.bundle_delta(['SAL-03'], ['SAL-03']), 0)

    def test_cannot_give_more_copies_than_held(self):
        with self.assertRaises(ValueError):
            Values(snapshot(['SAL-01'])).bundle_delta([], ['SAL-01', 'SAL-01'])

    def test_unknown_cards_are_rejected(self):
        with self.assertRaises(ValueError):
            Values(snapshot()).bundle_delta(['UNKNOWN'], [])

    def test_complete_page_has_no_further_completion_gain(self):
        snap = snapshot(['SAL-01', 'SAL-02', 'SAL-03'])
        scorer = Scorer(snap, Values(snap), [])
        rows = {r: {'buy_at': 10, 'mv': 10} for r in snap.cards}
        page = scorer.pages(rows)[0]
        self.assertEqual((page['gain'], page['cost'], page['net']), (0, 0, 0))

    def test_master_transition_is_not_guessed(self):
        values = Values(snapshot(['SAL-01', 'SAL-02', 'SAL-03', 'SAL-11']))
        with self.assertRaises(ValueError):
            values.bundle_delta(['SAL-12'], [])

    def test_exact_affinity_avoids_calibration_calls(self):
        snap = snapshot()
        snap.team = SimpleNamespace(value=lambda r: self.fail('API calibration should not run'))
        snap.me['affinity'] = {'SAL': 1.1}
        values = Values(snap)
        self.assertEqual(values.mult, {'SAL': 1.1})
        self.assertEqual(values.calibration['source'], 'me.affinity')


class BoardSafetyTests(unittest.TestCase):
    def score(self, give, want, held=(), cash=100, **extra):
        snap = snapshot(held, cash)
        snap.boards = {'rastro': [listing(give, want, **extra)]}
        snap.venues = {'rastro': {'fee_bps': 500, 'fee_per_card': 1}}
        return Scorer(snap, Values(snap), []).board_offers()

    def test_requested_quantity_is_enforced(self):
        self.assertEqual(self.score({'cash': 30}, {'types': ['card:SAL-01'] * 2}, ['SAL-01']), [])

    def test_specific_asset_must_be_owned(self):
        self.assertEqual(self.score({'cash': 20}, {'assets': [99]}, ['SAL-01']), [])

    def test_asset_and_type_cannot_spend_same_copy_twice(self):
        self.assertEqual(self.score({'cash': 20}, {'assets': [1], 'types': ['card:SAL-01']}, ['SAL-01']), [])

    def test_returns_distinct_payment_asset_selection(self):
        rows = self.score({'cash': 30}, {'types': ['card:SAL-01'] * 2}, ['SAL-01', 'SAL-01'])
        self.assertEqual(rows[0]['payment_assets'], [1, 2])

    def test_duplicate_incoming_asset_is_rejected(self):
        asset = {'id': 12, 'ref': 'SAL-01', 'kind': 'card'}
        self.assertEqual(self.score({'assets': [asset, asset]}, {'cash': 5}), [])

    def test_fee_is_included_in_net_surplus(self):
        row = self.score({'assets': [{'id': 12, 'ref': 'SAL-01', 'kind': 'card'}]}, {'cash': 9})[0]
        self.assertEqual((row['fee'], row['surplus']), (2, -1))

    def test_insufficient_cash_including_fee_is_rejected(self):
        self.assertEqual(self.score({'assets': [{'id': 12, 'ref': 'SAL-01', 'kind': 'card'}]}, {'cash': 9}, cash=10), [])

    def test_expired_or_other_recipient_is_rejected(self):
        for extra in ({'expires_tick': 4}, {'to': 'other-team'}):
            self.assertEqual(self.score({'cash': 20}, {'assets': [1]}, ['SAL-01'], **extra), [])

    def test_own_venue_is_excluded(self):
        snap = snapshot(['SAL-01'])
        snap.me['venue'] = 'rastro'
        snap.boards = {'rastro': [listing({'cash': 20}, {'assets': [1]})]}
        self.assertEqual(Scorer(snap, Values(snap), []).board_offers(), [])


class OfferSafetyTests(unittest.TestCase):
    def test_wrong_card_extra_asset_and_invalid_cash_are_rejected(self):
        topic = {'buy': {'card': 'SAL-01'}}
        for give, want in [({'types': ['card:SAL-02']}, {'cash': 9}),
                           ({'types': ['card:SAL-01']}, {'cash': 9, 'assets': [1]}),
                           ({'types': ['card:SAL-01']}, {'cash': True}),
                           ({'types': ['card:SAL-01']}, {'cash': 0})]:
            self.assertFalse(offer_ok(listing(give, want), topic))

    def test_sale_rejects_extra_typed_assets(self):
        offer = listing({'cash': 15}, {'assets': [1], 'types': ['card:SAL-02']})
        self.assertFalse(offer_ok(offer, {'sell': {'assets': [1]}}, False))

    def test_identity_recipient_and_expiry_checked(self):
        offer = listing({'types': ['card:SAL-01']}, {'cash': 9}, to='t18', expires_tick=5)
        args = dict(topic={'buy': {'card': 'SAL-01'}}, dealer='peer', team='t18', tick=5)
        self.assertTrue(executable_offer(offer, **args))
        self.assertFalse(executable_offer(offer, **{**args, 'tick': 6}))
        self.assertFalse(executable_offer(offer, **{**args, 'team': 't19'}))

    def test_settlement_price_for_both_makers_and_roles(self):
        for buying in (True, False):
            for own in (True, False):
                topic = {'buy': {'card': 'SAL-01'}} if buying else {'sell': {'assets': [1]}}
                give = {'types': ['card:SAL-01']} if buying else {'cash': 9}
                want = {'cash': 9} if buying else {'assets': [1]}
                if own:
                    give, want = want, give
                offer = listing(give, want, maker='t18' if own else 'abuela', status='settled')
                thread = {'messages': [{'offer': offer}]}
                self.assertEqual(settled_price(thread, topic, team='t18', dealer='abuela', buying=buying), 9)


class FakeDealer:
    """In-memory API with next-tick settlement; never calls the SDK."""
    def __init__(self, *, buying=True, quote=12, floor=9, final=False, delay=1, late=False):
        self.buying, self.quote, self.floor, self.final = buying, quote, floor, final
        self.delay, self.late = delay, late
        self.tick, self.accepts, self.writes = 0, 0, []
        self.status, self.messages, self.pending = 'open', [], None
        self._dealer_offer()

    def _dealer_offer(self):
        give = {'types': ['card:SAL-01']} if self.buying else {'cash': self.quote}
        want = {'cash': self.quote} if self.buying else {'assets': [1]}
        self.offer = listing(give, want, maker='abuela', to='test-haggle', final=self.final,
                             expires_tick=100)
        self.messages.append({'offer': self.offer})

    def me(self):
        return {'id': 'test-haggle', 'cash': 100, 'open_threads': [],
                'assets': [{'id': 1, 'kind': 'card', 'ref': 'SAL-01'}]}

    def clock(self):
        return {'tick': self.tick, 'paused': False}

    def open_thread(self, *args, **kwargs):
        self.writes.append('open')
        return {'id': 1}

    def thread(self, tid):
        visible = not self.late or self.tick > 0
        return {'status': self.status, 'messages': self.messages if visible else [],
                'standing_offers': [self.offer] if visible and self.offer['status'] == 'open' else []}

    def say(self, tid, text, price):
        self.writes.append(('say', price, self.tick))
        if (price >= self.floor if self.buying else price <= self.floor):
            own = listing({'cash': price} if self.buying else {'assets': [1]},
                          {'types': ['card:SAL-01']} if self.buying else {'cash': price},
                          maker='test-haggle', status='queued')
            self.messages.append({'offer': own})
            self.pending = [own, self.delay]
        else:
            self.offer['status'] = 'cancelled'
            self.quote = max(self.floor, self.quote - 2) if self.buying else min(self.floor, self.quote + 2)
            self._dealer_offer()
        return {'message': len(self.messages)}

    def accept(self, oid):
        self.accepts += 1
        self.offer['status'] = 'queued'
        self.pending = [self.offer, self.delay]
        return {'queued': True}

    def close_thread(self, tid):
        self.status = 'closed'

    def wait_tick(self):
        self.tick += 1
        if self.tick > 30:
            raise AssertionError('Engine did not terminate')
        if self.pending:
            self.pending[1] -= 1
            if self.pending[1] == 0:
                self.pending[0]['status'] = 'settled'
                self.status = 'deal'


class HagglerTests(unittest.TestCase):
    def setUp(self):
        self.logger = patch('agent.haggle.log')
        self.logger.start()
        self.addCleanup(self.logger.stop)

    def run_engine(self, b, **kwargs):
        cfg = dict(anchor=5, limit=9, rounds=6, beta=1, lines=['Oferta {p}'])
        cfg.update(kwargs)
        topic = {'buy': {'card': 'SAL-01'}} if b.buying else {'sell': {'assets': [1]}}
        return haggle(b, 'abuela', topic, buying=b.buying, **cfg)

    def test_own_offer_settles_with_correct_price(self):
        b = FakeDealer()
        result = self.run_engine(b, anchor=9, limit=11)
        self.assertEqual((result['price'], result['confirmed']), (9, True))

    def test_delayed_settlement_does_not_accept_twice(self):
        b = FakeDealer(quote=8, delay=3)
        result = self.run_engine(b, anchor=9)
        self.assertEqual((b.accepts, result['price'], b.tick), (1, 8, 3))

    def test_dealer_accepts_own_offer_with_delayed_settlement(self):
        b = FakeDealer(delay=3)
        result = self.run_engine(b, anchor=9, limit=11)
        sent = [w for w in b.writes if isinstance(w, tuple)]
        self.assertEqual((len(sent), b.accepts, result['price']), (1, 0, 9))

    def test_waits_for_initial_dealer_offer(self):
        b = FakeDealer(late=True)
        self.run_engine(b, anchor=9, limit=11)
        self.assertTrue(all(w[2] >= 1 for w in b.writes if isinstance(w, tuple)))

    def test_final_above_limit_closes_without_acceptance(self):
        b = FakeDealer(final=True)
        result = self.run_engine(b)
        self.assertEqual((result['status'], b.accepts), ('closed', 0))

    def test_reserve_blocks_before_opening_conversation(self):
        b = FakeDealer()
        with self.assertRaises(ValueError):
            self.run_engine(b, reserve_cash=99)
        self.assertEqual(b.writes, [])

    def test_existing_thread_is_not_taken_over(self):
        b = FakeDealer()
        me = b.me()
        me['open_threads'] = [99]
        b.me = lambda: me
        with self.assertRaises(RuntimeError):
            self.run_engine(b)
        self.assertEqual(b.writes, [])

    def test_sale_own_offer_price_is_recorded(self):
        b = FakeDealer(buying=False, quote=5, floor=13)
        result = self.run_engine(b, anchor=13, limit=10)
        self.assertEqual((result['price'], result['confirmed']), (13, True))

    def test_invalid_curve_configuration_causes_no_api_calls(self):
        for kwargs in ({'beta': 0}, {'rounds': 0}, {'anchor': True}, {'limit': 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                haggle(object(), 'abuela', {'buy': {'card': 'SAL-01'}},
                       **{**dict(anchor=5, limit=9, rounds=6, beta=1, lines=['{p}']), **kwargs})


class WriterLockTests(unittest.TestCase):
    def test_second_executor_is_rejected_then_lock_is_released(self):
        with team_writer('offline-lock-test'):
            with self.assertRaises(RuntimeError):
                with team_writer('offline-lock-test'):
                    self.fail('Concurrent writer entered')
        with team_writer('offline-lock-test'):
            pass
