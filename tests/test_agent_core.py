"""Kept-module cases of the old core suite (agent/offer_safety.py, agent/execution.py).

NOTES (M18): the original file is archived at docs/history/legacy-code/tests/test_agent_core.py (git history kept). Its Scorer
(agent/scorer.py) and haggle (agent/haggle.py) cases tested archived code and went with it; the cases below test
modules that stay in the harness, so they stay here until their owners (M4a test_guards, M5 test_gate) absorb them.
"""
import unittest

import tests  # noqa: F401  (test isolation)
from agent.execution import team_writer
from agent.offer_safety import executable_offer, offer_ok, settled_price


def listing(give, want, **extra):
    return {'id': 1, 'maker': 'peer', 'status': 'open', 'give': give, 'want': want, **extra}


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


class WriterLockTests(unittest.TestCase):
    def test_second_executor_is_rejected_then_lock_is_released(self):
        with team_writer('offline-lock-test'):
            with self.assertRaises(RuntimeError):
                with team_writer('offline-lock-test'):
                    self.fail('Concurrent writer entered')
        with team_writer('offline-lock-test'):
            pass


class ArchivedScriptsCannotRunTests(unittest.TestCase):
    """M18: every archived pre-harness script stops at import (SystemExit) before it can build a client."""

    def test_every_archived_python_file_is_guarded(self):
        import ast
        from pathlib import Path
        archive = Path(__file__).resolve().parents[1] / 'docs' / 'history' / 'legacy-code'
        files = [p for p in archive.rglob('*.py') if '__pycache__' not in p.parts
                 and not p.relative_to(archive).parts[0] == 'tests']
        self.assertTrue(files)
        unguarded = []
        for p in files:
            body = ast.parse(p.read_text(encoding='utf-8')).body
            head = [n for n in body if not (isinstance(n, ast.ImportFrom) and n.module == '__future__')
                    and not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))][:1]
            ok = head and isinstance(head[0], ast.Raise) and isinstance(head[0].exc, ast.Call) \
                and getattr(head[0].exc.func, 'id', '') == 'SystemExit'
            if not ok:
                unguarded.append(p.relative_to(archive).as_posix())
        self.assertEqual(unguarded, [])

    def test_no_legacy_writer_left_at_the_top_level(self):
        from pathlib import Path
        repo = Path(__file__).resolve().parents[1]
        legacy = ['run_loop.py', 'run_dealer.py', 'run_duels.py', 'run_broker.py', 'run_morning.py', 'market.py',
                  'starter_agent.py', 'starter_broker.py', 'collect_info.py', 'scout.py', 'probe.py',
                  'sim_bench.py', 'recheck.py', 'evaluacion.py', 'collector_mcp.py', 'bench_information.py',
                  'agent/scorer.py', 'agent/broker.py', 'agent/information.py', 'agent/haggle.py',
                  'agent/dealers.py', 'agent/duels.py']
        self.assertEqual([f for f in legacy if (repo / f).exists()], [])


if __name__ == '__main__':
    unittest.main()
