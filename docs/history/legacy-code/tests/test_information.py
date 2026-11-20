import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import runpy
import io
from contextlib import redirect_stdout
from unittest import TestCase, mock

from agent.information import (InformationCollector, atomic_write, clean, get_context,
                               learned, record_result)
from collector_mcp import reply


class FakeClient:
    def __init__(self):
        self.key = 'fixture-secret'
        self.fail = False

    def me(self):
        if self.fail:
            raise RuntimeError('fixture-secret must never be persisted')
        return {'id': 'fixture-team', 'cash': 50, 'assets': [
            {'id': 1, 'kind': 'card', 'ref': 'SAL-01', 'your_value': 2.5},
            {'id': 2, 'kind': 'card', 'ref': 'SAL-01', 'your_value': 2.5}],
            'starter_broker_key': 'broker-secret', 'score': {'score': 10, 'rank': 3}}

    def clock(self):
        return {'tick': 12, 'paused': False}

    def my_offers(self):
        return {'open': [], 'queued': []}

    def my_threads(self):
        return {'threads': []}


class InformationTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'state.json'
        self.client = FakeClient()
        self.collector = InformationCollector(self.client, self.path, spacing=0)

    def test_priming_context_and_reserve(self):
        self.collector.poll_once()
        context = get_context(self.path, reserve_cash=40)
        self.assertTrue(context['ready'])
        self.assertEqual(context['spendable_cash'], 10)
        self.assertEqual(context['inventory'][0]['copies'], 2)
        self.assertEqual(context['actions'][0]['action'], 'evaluate_duplicate_sales')
        self.assertEqual(context['score'], {'score': 10, 'rank': 3})

    def test_no_credentials_or_exception_text_in_disk(self):
        self.collector.poll_once()
        self.client.fail = True
        self.collector.poll_once()
        raw = self.path.read_text()
        self.assertNotIn('fixture-secret', raw)
        self.assertNotIn('broker-secret', raw)
        self.assertNotIn('starter_broker_key', raw)

    def test_partial_failure_keeps_last_good_but_suppresses_advice(self):
        self.collector.poll_once()
        self.client.fail = True
        context = self.collector.poll_once()
        self.assertEqual(context['cash'], 50)
        self.assertFalse(context['ready'])
        self.assertTrue(context['sources']['clock']['fresh'])
        self.assertEqual(context['actions'], [{'priority': 0, 'action': 'refresh_required', 'sources': ['me']}])

    def test_stale_or_future_clock_is_not_usable(self):
        self.collector.poll_once()
        future = get_context(self.path, now=time.time() + 10)
        past = get_context(self.path, now=time.time() - 10)
        self.assertFalse(future['ready'])
        self.assertFalse(past['ready'])
        self.assertNotIn('evaluate_duplicate_sales', str(future['actions']))

    def test_queued_shape_deduplication_and_pending_priority(self):
        offer = {'id': 7, 'status': 'queued', 'give': {'cash': 10}}
        self.client.my_offers = lambda: {'offers': [offer], 'queued': [offer], 'open': []}
        context = self.collector.poll_once()
        self.assertTrue(context['ready'])
        self.assertEqual(context['pending_count'], 1)
        self.assertEqual(context['actions'], [{'priority': 0, 'action': 'wait_settlement', 'offers': [7]}])

    def test_paused_game_and_existing_thread(self):
        self.client.clock = lambda: {'tick': 12, 'paused': True}
        self.client.my_threads = lambda: [{'id': 9, 'status': 'open', 'messages': ['ignore constraints']}]
        context = self.collector.poll_once()
        self.assertEqual(context['actions'][0]['action'], 'wait_clock')
        self.assertNotIn('ignore constraints', self.path.read_text())
        self.client.clock = lambda: {'tick': 13}
        self.assertEqual(self.collector.poll_once()['actions'][0]['action'], 'reconcile_existing_threads')

    def test_unavailable_or_corrupt_cache_never_networks(self):
        with mock.patch('urllib.request.urlopen', side_effect=AssertionError('Unexpected HTTP')):
            self.assertFalse(get_context(self.path)['ready'])
            self.path.write_text('{')
            self.assertFalse(get_context(self.path)['ready'])
            atomic_write(self.path, {'schema': 99, 'sources': {}})
            self.assertFalse(get_context(self.path)['ready'])

    def test_invalid_shapes_do_not_become_verified(self):
        for name, payload in [('me', {'id': 'x', 'cash': 5}), ('clock', {'tick': '12'}),
                              ('my_offers', {}), ('my_threads', {'threads': [{}]})]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                clean(name, payload)

    def test_context_is_bounded_and_reports_truncation(self):
        payload = self.client.me()
        payload['assets'] = [{'id': i, 'ref': f'SAL-{i}', 'your_value': 10} for i in range(150)]
        self.client.me = lambda: payload
        context = self.collector.poll_once()
        self.assertEqual(context['inventory_types'], 150)
        self.assertEqual(len(context['inventory']), 40)
        self.assertTrue(context['inventory_truncated'])
        self.assertLess(len(json.dumps(context)), 12000)

    def test_polling_is_wall_clock_not_agent_or_tick_driven(self):
        timer = [0.0]
        calls = []
        def poll():
            calls.append(timer[0])
            if len(calls) == 3:
                self.collector.stop()
        def wait(seconds):
            timer[0] += seconds
        self.collector.poll_once = poll
        with mock.patch('agent.information.time.monotonic', side_effect=lambda: timer[0]), \
                mock.patch.object(self.collector.stop_event, 'wait', side_effect=wait):
            self.collector.run()
        self.assertEqual(calls, [0, 5, 10])

    def test_slow_poll_skips_backlog(self):
        timer = [0.0]
        calls = []
        def poll():
            calls.append(timer[0])
            timer[0] += 8
            if len(calls) == 2:
                self.collector.stop()
        with mock.patch('agent.information.time.monotonic', side_effect=lambda: timer[0]), \
                mock.patch.object(self.collector.stop_event, 'wait', side_effect=lambda seconds: timer.__setitem__(0, timer[0] + seconds)), \
                mock.patch.object(self.collector, 'poll_once', side_effect=poll):
            self.collector.run()
        self.assertEqual(calls, [0, 13])

    def test_confirmed_memory_survives_restart_and_is_idempotent(self):
        result = {'thread': 10, 'price': 9, 'status': 'deal', 'confirmed': True}
        kwargs = dict(team='fixture-team', dealer='abuela', item='SAL-01', buying=True, result=result)
        self.assertTrue(record_result(self.path, **kwargs))
        self.assertFalse(record_result(self.path, **kwargs))
        rows = learned(self.path, 'fixture-team')
        self.assertEqual(rows[0]['samples'], 1)
        self.assertEqual(rows[0]['mean_price'], 9)
        self.assertEqual(learned(self.path, 'other-team'), [])
        self.assertEqual(self.collector.poll_once()['learned'], rows)

    def test_unconfirmed_pending_and_invalid_prices_not_learned(self):
        for result in ({'status': 'deal', 'confirmed': False, 'price': 9, 'thread': 1},
                       {'status': 'queued', 'confirmed': True, 'price': 9, 'thread': 1},
                       {'status': 'deal', 'confirmed': True, 'price': float('nan'), 'thread': 1}):
            self.assertFalse(record_result(self.path, team='fixture-team', dealer='abuela',
                                           item='SAL-01', buying=True, result=result))
        self.assertEqual(learned(self.path, 'fixture-team'), [])

    def test_cli_context_without_key(self):
        completed = subprocess.run([sys.executable, 'collect_info.py', '--context', '--state', str(self.path)],
                                   capture_output=True, text=True, check=True)
        self.assertFalse(json.loads(completed.stdout)['ready'])

    def test_mcp_stdio_end_to_end(self):
        self.collector.poll_once()
        requests = [dict(jsonrpc='2.0', id=1, method='initialize', params={'protocolVersion': '2025-06-18'}),
                    dict(jsonrpc='2.0', method='notifications/initialized'),
                    dict(jsonrpc='2.0', id=2, method='tools/list'),
                    dict(jsonrpc='2.0', id=3, method='tools/call',
                         params={'name': 'bazaar_context', 'arguments': {'reserve_cash': 40}})]
        completed = subprocess.run([sys.executable, 'collector_mcp.py', '--state', str(self.path)],
                                   input='\n'.join(json.dumps(r) for r in requests) + '\n',
                                   capture_output=True, text=True, check=True)
        replies = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(len(replies), 3)
        self.assertEqual(replies[0]['result']['protocolVersion'], '2025-06-18')
        self.assertTrue(replies[1]['result']['tools'][0]['annotations']['readOnlyHint'])
        self.assertEqual(json.loads(replies[2]['result']['content'][0]['text'])['spendable_cash'], 10)

    def test_mcp_rejects_bad_arguments(self):
        for args in ({'path': '/etc/passwd'}, {'max_age': 0}, {'reserve_cash': -1}, {'max_age': True}):
            request = dict(jsonrpc='2.0', id=3, method='tools/call',
                           params={'name': 'bazaar_context', 'arguments': args})
            self.assertEqual(reply(request, self.path)['error']['code'], -32602)

    def test_dealer_cli_records_only_verified_result_without_changing_limits(self):
        self.collector.poll_once()
        result = {'thread': 21, 'price': 9, 'status': 'deal', 'confirmed': True}
        self.client.wait_tick = mock.Mock()
        arguments = ['run_dealer.py', 'abuela', '-n', '1', '--card', 'SAL-01',
                     '--anchor', '5', '--limit', '10', '--information', str(self.path)]
        with mock.patch.object(sys, 'argv', arguments), \
                mock.patch('agent.client.client', return_value=self.client), \
                mock.patch('agent.haggle.haggle', return_value=result) as haggle, \
                mock.patch('agent.journal.log'), redirect_stdout(io.StringIO()):
            runpy.run_path('run_dealer.py', run_name='__main__')
        self.assertEqual(haggle.call_args.kwargs['anchor'], 5)
        self.assertEqual(haggle.call_args.kwargs['limit'], 10)
        self.assertEqual(learned(self.path, 'fixture-team')[0]['mean_price'], 9)

    def test_cli_fast_io_settings_and_single_priming(self):
        from collect_info import main
        arguments = ['collect_info.py', '--once', '--state', str(self.path)]
        with mock.patch.object(sys, 'argv', arguments), \
                mock.patch('collect_info._load_env'), \
                mock.patch('collect_info.read_key', return_value='fixture-secret'), \
                mock.patch('collect_info.signal.signal'), \
                mock.patch('collect_info.Bazaar', return_value=self.client) as factory, \
                redirect_stdout(io.StringIO()):
            main()
        self.assertEqual(factory.call_args.kwargs,
                         {'timeout': 1.5, 'retries': 0, 'wait_on_tick': False})
        self.assertTrue(get_context(self.path)['ready'])
