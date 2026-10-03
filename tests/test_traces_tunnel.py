import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import run_traces
import run_traces_tunnel


class TunnelSetupTests(unittest.TestCase):
    def test_secret_is_private_reused_and_unsafe_existing_file_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'password'
            secret = run_traces_tunnel.password_from_file(path)
            self.assertGreaterEqual(len(secret), 24)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(run_traces_tunnel.password_from_file(path), secret)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                run_traces_tunnel.password_from_file(path)

    def test_demo_is_isolated_reconciles_and_open_chato_is_not_in_memory(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run_traces_tunnel, 'ROOT', Path(directory)):
            logs = run_traces_tunnel.demo_logs()
            self.assertTrue(Path(logs).is_relative_to(Path(directory) / 'runs' / 'traces-demo'))
            state = run_traces.state(logs)
        self.assertTrue(state['reconcile']['ok'])
        self.assertEqual((state['reconcile']['open'], state['reconcile']['ended']), (1, 1))
        self.assertEqual((state['memory']['cases'], state['memory']['team_cases']), (1, 1))
        self.assertNotIn('FAKE_SECRET_MUST_NOT_REACH_VIEWER', json.dumps(state))


if __name__ == '__main__':
    unittest.main()
