import base64
from dataclasses import asdict
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from agent import journal, trace
from agent.haggle import haggle
from harness.retrieval import MemoryIndex, Scope, import_feed
import run_traces
from tests.test_agent_core import FakeDealer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write(log_dir, stream, rows, tail=''):
    with open(os.path.join(log_dir, stream + '.jsonl'), 'a', encoding='utf-8') as f:
        f.writelines(json.dumps(r) + '\n' for r in rows)
        f.write(tail)


def feed_thread(tid=1, dealer='abuela', prices=(12, 9), card='SAL-01'):
    events = [{'id': 1, 'tick': 0, 'scope': 'public', 'type': 'thread.opened',
               'payload': {'thread': tid, 'with': dealer, 'topic': {'buy': {'card': card}}}}]
    for n, p in enumerate(prices, 2):
        events.append({'id': n, 'tick': n, 'scope': 'public', 'type': 'thread.message',
                       'payload': {'thread': tid, 'with': dealer, 'sender': dealer, 'text': 'precio',
                                   'offer': {'give': {'types': ['card:' + card]}, 'want': {'cash': p}}}})
    events.append({'id': 99, 'tick': 9, 'scope': 'public', 'type': 'thread.closed',
                   'payload': {'thread': tid, 'with': dealer}})
    return events


def deal(tid='1', dealer='abuela', price=9, status='deal'):
    return [{'ts': 1, 'event': 'open', 'thread': tid, 'topic': {'buy': {'card': 'SAL-01'}}, 'anchor': 5, 'limit': 9},
            {'ts': 2, 'event': 'offer_sent', 'thread': tid, 'price': 5, 'tick': 1},
            {'ts': 3, 'event': 'accept_intent', 'thread': tid, 'price': price, 'tick': 2},
            {'ts': 4, 'event': 'end', 'thread': tid, 'status': status, 'price': price, 'reason': None}]


class TraceReadTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_torn_and_malformed_lines_are_counted_and_ids_stay_stable_on_append(self):
        write(self.dir, 'abuela', deal()[:2], tail='{"ts": 9, "event": "off')
        with open(os.path.join(self.dir, 'abuela.jsonl'), 'a') as f:
            f.write('\n[1,2]\n')  # completes the torn line as garbage, plus a non-object row
        events, bad = trace.read(self.dir)
        self.assertEqual(([e['id'] for e in events], bad), (['abuela:1', 'abuela:2'], 2))
        write(self.dir, 'abuela', deal()[2:])
        again, _ = trace.read(self.dir)
        self.assertEqual([e['id'] for e in again][:2], ['abuela:1', 'abuela:2'])
        self.assertEqual(len(again), 4)

    def test_polling_noise_and_secret_fields_never_reach_the_viewer(self):
        write(self.dir, 'information', [{'ts': 1, 'event': 'sample', 'source': 'me'}])
        write(self.dir, 'loop', [{'ts': 1, 'event': 'error', 'extra': {'X-Team-Key': 'tk-1', 'api_token': 't'}}])
        events, _ = trace.read(self.dir)
        self.assertEqual([e['stream'] for e in events], ['loop'])
        self.assertNotIn('tk-1', json.dumps(events))
        self.assertNotIn('"t"', json.dumps(events))

    def test_open_conversation_never_enters_the_memory(self):
        write(self.dir, 'abuela', deal()[:3])
        summaries = trace.threads(trace.read(self.dir)[0])
        self.assertEqual(summaries[0]['status'], 'open')
        self.assertEqual(trace.team_cases(summaries), [])


class EndToEndTests(unittest.TestCase):
    """The real haggler writes the journal; viewer, memory and reconciliation read the same rows."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        p = patch.object(journal, 'LOG_DIR', self.dir)
        p.start()
        self.addCleanup(p.stop)

    def test_haggler_journal_becomes_one_private_memory_case_consistent_with_the_feed(self):
        b = FakeDealer()
        result = haggle(b, 'abuela', {'buy': {'card': 'SAL-01'}}, anchor=5, limit=9, rounds=6, beta=1,
                        lines=['Oferta {p}'])
        self.assertTrue(result['confirmed'])
        summaries = trace.threads(trace.read(self.dir)[0])
        self.assertEqual(len(summaries), 1)
        t = summaries[0]
        self.assertEqual((t['dealer'], t['side'], t['item'], t['status'], t['price']),
                         ('abuela', 'buy', 'SAL-01', 'deal', result['price']))
        self.assertEqual(t['ours'], [w[1] for w in b.writes if w[0] == 'say'])

        feed, _ = import_feed(feed_thread(prices=(12, 10, result['price'])), 'feed')
        report = trace.reconcile(summaries, feed)
        self.assertTrue(report['ok'], report)
        self.assertEqual(report['in_feed'], 1)

        memory = trace.merge(feed, trace.team_cases(summaries))
        self.assertEqual([c.id for c in memory], ['thread-1'])
        self.assertEqual(memory[0].visibility, 'local-team')
        self.assertEqual(memory[0].phase, 'settled')
        body = json.loads(memory[0].body)
        self.assertEqual(body['team']['price'], result['price'])
        self.assertEqual(body['feed']['dealer_prices'], [12, 10, result['price']])

        index = MemoryIndex(memory)
        self.addCleanup(index.close)
        mine, _ = index.retrieve('compra SAL-01', Scope('abuela', 'buy', 'SAL-01'), k=3)
        self.assertEqual([c['id'] for c in mine], ['thread-1'])
        other, _ = index.retrieve('compra SAL-01', Scope('abuela', 'buy', 'SAL-01', team='another-team'), k=3)
        self.assertEqual(other, [])


class ConsistencyTests(unittest.TestCase):
    def test_price_not_seen_in_the_feed_is_reported_as_descuadre(self):
        summaries = trace.threads([{**e, 'id': f'abuela:{n}', 'stream': 'abuela'} for n, e in enumerate(deal(price=11), 1)])
        report = trace.reconcile(summaries, import_feed(feed_thread(prices=(12, 9)), 'feed')[0])
        self.assertEqual((report['ok'], report['price_not_in_feed']), (False, ['1']))

    def test_two_dealers_are_never_fused_and_ids_stay_unique(self):
        summaries = trace.threads([{**e, 'id': f'chato:{n}', 'stream': 'chato'} for n, e in enumerate(deal(), 1)])
        feed = import_feed(feed_thread(), 'feed')[0]
        self.assertEqual(trace.reconcile(summaries, feed)['dealer_mismatch'], ['1'])
        memory = trace.merge(feed, trace.team_cases(summaries))
        self.assertEqual(sorted(c.id for c in memory), ['thread-1', 'thread-1-team'])
        self.assertEqual(next(c for c in memory if c.id == 'thread-1').visibility, 'public')

    def test_feed_cases_without_our_trace_are_untouched_and_merge_is_deterministic(self):
        feed = import_feed(feed_thread(tid=7) + [dict(e, id=e['id'] + 100) for e in feed_thread(tid=8)], 'feed')[0]
        ours = trace.team_cases(trace.threads(
            [{**e, 'id': f'abuela:{n}', 'stream': 'abuela'} for n, e in enumerate(deal(tid='8'), 1)]))
        once, twice = trace.merge(feed, ours), trace.merge(feed, ours)
        self.assertEqual([asdict(c) for c in once], [asdict(c) for c in twice])
        self.assertEqual(asdict(next(c for c in once if c.id == 'thread-7')),
                         asdict(next(c for c in feed if c.id == 'thread-7')))
        self.assertEqual(len(once), len(feed))


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        write(self.dir, 'abuela', deal())
        with open(os.path.join(self.dir, 'feed.jsonl'), 'w') as f:
            f.writelines(json.dumps(e) + '\n' for e in feed_thread())
        run_traces._cache.update(at=0.0, body=b'')

    def start(self, password):
        server = run_traces.serve('127.0.0.1', 0, self.dir, password)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f'http://127.0.0.1:{server.server_address[1]}'

    def get(self, url, password=None):
        req = urllib.request.Request(url)
        if password:
            req.add_header('Authorization', 'Basic ' + base64.b64encode(b'equipo:' + password.encode()).decode())
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()

    def test_opening_to_the_network_without_password_is_refused(self):
        with self.assertRaises(SystemExit):
            run_traces.serve('0.0.0.0', 0, self.dir, '')

    def test_password_protects_page_and_state_and_state_is_consistent(self):
        base = self.start('s3creto')
        for path in ('/', '/state.json'):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.get(base + path, 'mala')
            self.assertEqual(ctx.exception.code, 401)
        self.assertEqual(self.get(base + '/', 's3creto')[0], 200)
        s = json.loads(self.get(base + '/state.json', 's3creto')[1])
        self.assertTrue(s['reconcile']['ok'])
        self.assertEqual(s['threads'][0]['status'], 'deal')
        self.assertEqual((s['memory']['cases'], s['memory']['team_cases'], s['memory']['ids_unique']), (1, 1, True))

    def test_malformed_and_unicode_credentials_fail_closed_without_crashing(self):
        base = self.start('válida-contraseña')
        for value in ('Bearer anything', 'Basic !!!', 'Basic ' + base64.b64encode('team:incorrectá'.encode()).decode()):
            req = urllib.request.Request(base + '/state.json', headers={'Authorization': value})
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(ctx.exception.code, 401)
        self.assertEqual(self.get(base + '/', 'válida-contraseña')[0], 200)

    def test_no_auth_cannot_read_arbitrary_routes_or_files(self):
        base = self.start('secret')
        for path in ('/', '/state.json', '/index.html', '/../../.env', '/logs/abuela.jsonl', '/unknown'):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.get(base + path)
            self.assertEqual(ctx.exception.code, 401)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get(base + '/logs/abuela.jsonl', 'secret')
        self.assertEqual(ctx.exception.code, 404)

    def test_cache_never_reuses_a_different_log_directory(self):
        first = json.loads(run_traces._body(self.dir))
        with tempfile.TemporaryDirectory() as empty_dir:
            second = json.loads(run_traces._body(empty_dir))
        self.assertEqual(first['events_total'], 4)
        self.assertEqual(second['events_total'], 0)

    def test_check_command_fails_on_descuadre(self):
        def check():
            return subprocess.run([sys.executable, 'run_traces.py', '--check', '--logs', self.dir], cwd=ROOT,
                                  capture_output=True, text=True).returncode
        self.assertEqual(check(), 0)
        write(self.dir, 'abuela', [dict(e, thread='1') for e in deal(price=11)[3:]])  # a later, contradicting end
        self.assertEqual(check(), 1)


if __name__ == '__main__':
    unittest.main()
