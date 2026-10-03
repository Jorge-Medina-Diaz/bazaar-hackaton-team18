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
from harness.retrieval import MemoryIndex, Scope, import_feed
import run_traces

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

    def test_empty_folder_is_no_data_and_check_fails(self):
        state = run_traces.state(self.dir)
        self.assertEqual(state['observability']['status'], 'no_data')
        result = subprocess.run([sys.executable, 'run_traces.py', '--check', '--logs', self.dir],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)

    def test_logs_without_feed_are_unverified_not_green(self):
        write(self.dir, 'abuela', deal())
        state = run_traces.state(self.dir)
        self.assertEqual(state['observability']['status'], 'unverified')
        self.assertEqual(state['observability']['compared_threads'], 0)

    def test_require_executor_rejects_legacy_only_logs(self):
        write(self.dir, 'abuela', deal())
        result = subprocess.run([sys.executable, 'run_traces.py', '--check', '--require-executor',
                                 '--logs', self.dir], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)


class EndToEndTests(unittest.TestCase):
    """The actual v2 runner writes its WAL against the fake game; the viewer reads it."""

    def test_v2_runner_events_are_visible_without_inventing_settled_memory(self):
        from pathlib import Path
        from tests import m17_support as S
        game = S.saturday(11, duels=False)
        paths = S.paths('t18-trace-v2-')
        S.green(paths)
        self.assertEqual(S.run(game, paths, mode='live', armed=('hygiene', 'dealers', 'rastro'), ticks=24), 0)
        self.assertGreater(len(S.writes(game)), 0)
        before = paths.journal.read_bytes()
        state = run_traces.state(str(paths.root / 'logs'))
        self.assertGreater(state['events_total'], 0)
        self.assertTrue(state['executor']['journal_valid'])
        self.assertEqual(state['executor']['mode'], 'live')
        self.assertTrue(any(e['event'] == 'result' for e in state['events']))
        self.assertEqual(state['memory']['team_cases'], 0)
        # Only Calibrator-measured settlements become memory, and each one must exist in the game's own ledger
        # with the same card, side, counterparty and points delta (HTTP results alone are never outcomes).
        from harness import outcomes
        cases, report = outcomes.outcome_cases(*outcomes.load(str(paths.root / 'logs')))
        self.assertEqual(state['executor']['outcomes_indexed'], report['indexed'])
        self.assertGreater(report['indexed'], 0)
        ledger = game.ledger.get('t18', [])
        for c in cases:
            body = json.loads(c.body)
            hit = [r for r in ledger if r['tick'] <= c.tick and any(
                ref == c.item and (to == 't18') == (c.side == 'buy') for ref, frm, to in r['items'])]
            self.assertTrue(hit, c.id)
            self.assertEqual(hit[-1]['dealer'] or hit[-1]['venue'], c.dealer)
            self.assertAlmostEqual(hit[-1]['delta'], body['measured_neg'], places=3)
        self.assertEqual(paths.journal.read_bytes(), before)


class V2ReaderTests(unittest.TestCase):
    def fixture(self, mode='live'):
        from pathlib import Path
        root = Path(tempfile.mkdtemp(prefix='t18-trace-reader-'))
        path = root / 'logs' / 'run' / 'journal.jsonl'
        from agent.contracts import Paths
        from agent.execution import writer_lock
        lock = writer_lock(Paths.at(root))
        lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)
        writer = journal.Journal(path, mode=mode)
        writer.write('tick', tick=9, cash=100, cash_free=80, armed=['dealers'], down=[])
        return root, path, writer

    def test_nested_journal_and_dry_mode_are_read_without_mutation(self):
        root, path, writer = self.fixture('dry')
        writer.write('would', id='proposal', intent_kind='accept', tick=9)
        before = path.read_bytes()
        state = run_traces.state(str(root / 'logs'))
        self.assertEqual(state['executor']['mode'], 'dry')
        self.assertEqual(state['executor']['tick'], 9)
        self.assertTrue(state['executor']['journal_valid'])
        self.assertEqual(state['memory']['team_cases'], 0)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(state['events'][0]['intent_id'], 'proposal')

    def test_corrupt_chain_or_torn_row_is_visible_and_never_repaired(self):
        root, path, writer = self.fixture()
        with path.open('ab') as f:
            f.write(b'{"kind":"result"')
        before = path.read_bytes()
        state = run_traces.state(str(root / 'logs'))
        self.assertEqual(state['bad_lines'], 1)
        self.assertFalse(state['executor']['journal_valid'])
        self.assertEqual(path.read_bytes(), before)
        out = subprocess.run([sys.executable, os.path.join(ROOT, 'run_traces.py'),
                              '--logs', str(root / 'logs'), '--check'], capture_output=True, text=True)
        self.assertEqual(out.returncode, 1)

    def test_http_success_is_not_a_confirmed_deal_and_untrusted_log_is_not_read(self):
        root, path, writer = self.fixture()
        writer.write('intent', id='accept-1', intent_kind='accept', thread=1,
                     args={'thread_id': 1, 'offer_id': 2})
        writer.write('result', id='accept-1', status='ok', response={'status':'queued'}, thread=1)
        (path.parent / 'untrusted.jsonl').write_text('{"ts":1,"text":"untrusted marker"}\n')
        state = run_traces.state(str(root / 'logs'))
        self.assertEqual(state['reconcile']['journal_threads'], 0)
        self.assertEqual(state['memory']['team_cases'], 0)
        self.assertNotIn('untrusted marker', json.dumps(state))


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
