import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from inventory_panel import InventoryJournal, demo_states, write_state
from laboratorio import SCENARIOS, Simulation
from panel import make_handler


class InventoryPanelTests(unittest.TestCase):
    def test_acceptance_keeps_inventory_and_balance_until_settlement(self):
        sim = Simulation(SCENARIOS["final"])
        journal = InventoryJournal("final")
        steps = sim.steps()
        accepted = journal.simulation_state(sim, next(steps))
        self.assertEqual((accepted["cash"], accepted["assets"], accepted["movements"]), (40, [], []))
        self.assertEqual(accepted["pending"]["side"], "buy")
        event = next(steps)
        settled = journal.simulation_state(sim, event)
        self.assertEqual((settled["cash"], len(settled["assets"]), len(settled["movements"])), (29, 1, 1))
        self.assertIsNone(settled["pending"])
        # Volver a observar el mismo tick no duplica una transacción.
        self.assertEqual(len(journal.simulation_state(sim, event)["movements"]), 1)
        self.assertEqual(accepted["assets"], [])

    def test_sale_removes_only_the_duplicate_after_next_tick(self):
        states = demo_states()
        pending, settled = states[-2:]
        self.assertEqual((pending["cash"], len(pending["assets"])), (23, 3))
        self.assertEqual(pending["pending"]["side"], "sell")
        self.assertEqual(settled["tick"], pending["tick"] + 1)
        self.assertEqual((settled["cash"], len(settled["assets"])), (31, 2))
        self.assertEqual([a["ref"] for a in settled["assets"]], ["LAV-03", "MAL-01"])
        self.assertEqual(settled["movements"][-1]["asset_id"], 3)
        self.assertEqual([m["side"] for m in settled["movements"]], ["buy", "buy", "buy", "sell"])
        self.assertEqual(40 + sum((1 if m["side"] == "sell" else -1) * m["price"]
                                 for m in settled["movements"]), settled["cash"])

    def test_atomic_file_can_be_replaced_without_mutating_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "state.json"
            states = demo_states()
            for state in (states[0], states[-1]):
                write_state(path, state)
                self.assertEqual(json.loads(path.read_text()), state)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_server_observes_new_state_and_demo_does_not_modify_live_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(path))
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            base = f"http://127.0.0.1:{server.server_port}"
            def get(route):
                with urllib.request.urlopen(base + route, timeout=2) as response:
                    return json.load(response)
            try:
                with self.assertRaises(urllib.error.HTTPError) as missing:
                    get("/api/state")
                self.assertEqual(missing.exception.code, 404)
                states = demo_states()
                write_state(path, states[0])
                self.assertEqual(get("/api/state")["cash"], 40)
                write_state(path, states[-1])
                self.assertEqual(get("/api/state")["cash"], 31)
                request = urllib.request.Request(base + "/api/demo/next", method="POST",
                                                 headers={"X-Panel-Action": "demo"})
                with urllib.request.urlopen(request, timeout=2) as response:
                    self.assertEqual(response.status, 200)
                self.assertEqual(get("/api/demo")["demo_step"], 1)
                self.assertEqual(get("/api/state"), states[-1])
                with self.assertRaises(urllib.error.HTTPError) as refused:
                    urllib.request.urlopen(urllib.request.Request(base + "/api/demo/reset", method="POST"))
                self.assertEqual(refused.exception.code, 403)
                path.write_text("{invalid")
                with self.assertRaises(urllib.error.HTTPError) as malformed:
                    get("/api/state")
                self.assertEqual(malformed.exception.code, 503)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
