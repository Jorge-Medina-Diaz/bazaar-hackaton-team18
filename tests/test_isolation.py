"""M17: INV-21 test isolation (and INV-18 for the environment).

- Importing `tests` puts the process in test mode and strips any key / URL / .env (BAZAAR_TEST, BAZAAR_NO_DOTENV).
- A realistic-looking .env never reaches a test: _load_env ignores it, client() has no key.
- A real key / production URL exported in the shell does not survive into the test process.
- In a subprocess with a production-looking key and URL in its environment, a sample of the integration tests
  (real HTTP on 127.0.0.1 included) makes 0 connections to any host other than 127.0.0.1 (audit hook on
  socket.connect / socket.getaddrinfo / urllib.Request), and logs/run/ and state/ of the repo do not change.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import tests  # noqa: F401  (the import under test)

REPO = Path(__file__).resolve().parents[1]
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
SAMPLE = ["tests.test_e2e_fake.TestOverRealHttp", "tests.test_cli", "tests.test_sim",
          "tests.test_foreign_writer.TestForeignWriter.test_quiet_harvest_five_ticks_no_stop"]

PROBE = r"""
import json, sys
hosts = []
def hook(ev, args):
    try:
        if ev == "socket.connect":
            a = args[1]
            hosts.append(str(a[0]) if isinstance(a, tuple) else str(a))
        elif ev == "socket.getaddrinfo":
            hosts.append(str(args[0]))
        elif ev == "urllib.Request":
            hosts.append(str(args[0]))
    except Exception:
        hosts.append("<unparsed>")
sys.addaudithook(hook)
import unittest
suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
res = unittest.TextTestRunner(stream=open(__import__("os").devnull, "w"), verbosity=0).run(suite)
print("RESULT " + json.dumps({"hosts": hosts, "ok": res.wasSuccessful(), "ran": res.testsRun,
                              "errors": [str(e[0]) for e in res.errors + res.failures]}))
"""


def tree_hash(*dirs: Path) -> str:
    h = hashlib.sha256()
    for d in dirs:
        if not d.exists():
            h.update(b"<none>" + str(d).encode())
            continue
        for p in sorted(x for x in d.rglob("*") if x.is_file()):
            if p.name == "selftest.json":           # written by `bazaar.py selftest` itself
                continue
            h.update(p.relative_to(d).as_posix().encode() + b"\0")
            try:
                h.update(p.read_bytes())
            except OSError:
                h.update(b"<locked>")
    return h.hexdigest()


def host_of(x: str) -> str:
    if "://" in x:
        x = x.split("://", 1)[1].split("/", 1)[0]
        if x.startswith("["):
            return x[1:].split("]")[0]
        return x.rsplit(":", 1)[0] if x.count(":") == 1 else x
    return x


class TestEnvironment(unittest.TestCase):
    def test_test_mode_and_no_credentials(self):
        self.assertEqual(os.environ.get("BAZAAR_TEST"), "1")
        self.assertTrue(os.environ.get("BAZAAR_NO_DOTENV"))
        self.assertNotIn("BAZAAR_KEY", os.environ)
        self.assertNotIn("BAZAAR_URL", os.environ)

    def test_realistic_dotenv_is_ignored(self):
        from agent import client
        d = Path(tempfile.mkdtemp(prefix="t18-m17-env-"))
        env = d / ".env"
        env.write_text("BAZAAR_KEY=tk-" + "a1b2c3d4" * 4 + "\nBAZAAR_URL=https://bazaar.causaprima.ai\n",
                       encoding="utf-8")
        client._load_env(env)
        self.assertNotIn("BAZAAR_KEY", os.environ)
        self.assertNotIn("BAZAAR_URL", os.environ)
        with self.assertRaises(RuntimeError):
            client.client()

    def test_test_paths_never_point_into_the_repo(self):
        from tests import m17_support as S
        p = S.paths()
        self.assertNotEqual(Path(p.root).resolve(), REPO.resolve())
        self.assertFalse(str(Path(p.journal).resolve()).startswith(str((REPO / "logs").resolve())))


class TestNoNetworkOutsideLoopback(unittest.TestCase):
    def test_sample_makes_zero_external_connections_and_leaves_repo_state(self):
        before = tree_hash(REPO / "logs" / "run", REPO / "state")
        env = dict(os.environ)
        env.pop("BAZAAR_TEST", None)
        env.pop("BAZAAR_NO_DOTENV", None)
        env.update({"BAZAAR_KEY": "tk-" + "f00dfeed" * 4, "BAZAAR_URL": "https://bazaar.causaprima.ai",
                    "PYTHONIOENCODING": "utf-8"})
        p = subprocess.run([sys.executable, "-c", PROBE] + SAMPLE, cwd=str(REPO), env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=600)
        line = [x for x in (p.stdout or "").splitlines() if x.startswith("RESULT ")]
        self.assertTrue(line, (p.stdout or "")[-1500:] + (p.stderr or "")[-1500:])
        res = json.loads(line[-1][7:])
        self.assertTrue(res["ok"], res["errors"])
        self.assertGreater(res["ran"], 20)
        hosts = {host_of(h) for h in res["hosts"]}
        self.assertTrue(hosts, "the sample must have used real sockets (HTTP on 127.0.0.1)")
        self.assertEqual(hosts - LOOPBACK, set())
        self.assertEqual(tree_hash(REPO / "logs" / "run", REPO / "state"), before)

    def test_host_parser(self):
        self.assertEqual(host_of("http://127.0.0.1:5555/api/clock"), "127.0.0.1")
        self.assertEqual(host_of("https://bazaar.causaprima.ai/api/me"), "bazaar.causaprima.ai")
        self.assertEqual(host_of("127.0.0.1"), "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
