"""L1 bench recorder tests: greedy plan equals the stall, 0 writes, key never on disk."""
from __future__ import annotations

import ast
import json
import random
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import tests  # noqa: F401  (isolates the environment)
from agent.contracts import Secrets
from agent.tactics import bench
from agent.tactics.bench import (BOOK_PATH, BenchRecorder, SecretLeak, plan_greedy, read_book, record,
                                 summarize)

KEY = "bk_TESTstall-0123456789abcdef"
BENCH_SRC = Path(bench.__file__).read_text(encoding="utf-8")


def ask(oid, q, **extra):
    return {"id": oid, "give": {"cash": 0, "assets": [{"kind": "x", "ref": "Y"}]}, "want": {"cash": q}, **extra}


def bid(oid, q, **extra):
    return {"id": oid, "give": {"cash": q}, "want": {"cash": 0, "types": ["x:Y"]}, **extra}


BOOK = {"bench_offers": [ask("b1-1", 50), ask("b1-2", 40), bid("b1-3", 60), bid("b1-4", 55), bid("b1-5", 30),
                         ask("b2-1", 100), bid("b2-2", 90),
                         ask("b3-1", 10), bid("b3-2", 10)],
        "offers": [], "settlements": []}
EXPECTED = [("b1-2", "b1-3", 50), ("b1-1", "b1-4", 52), ("b3-1", "b3-2", 10)]



class TestPlanGreedy(unittest.TestCase):
    def test_fixed_book(self):
        self.assertEqual(plan_greedy(BOOK), EXPECTED)


    def test_malformed_fails_closed(self):
        self.assertEqual(plan_greedy(None), [])
        self.assertEqual(plan_greedy({"bench_offers": "nope"}), [])
        bad = {"bench_offers": [ask("b1-1", 10), bid("b1-2", 20), {"id": 5}, "x", {"id": "b1-9"},
                                {"id": "b1-8", "give": {"cash": -3}, "want": {"cash": 0}},
                                {"id": "b1-7", "give": {"cash": True}, "want": {"cash": 0}},
                                {"id": "b1-6", "give": {"cash": 5}, "want": {"cash": 5}},
                                {"id": "nodash", "give": {"cash": 99}, "want": {"cash": 0}}]}
        self.assertEqual(plan_greedy(bad), [("b1-1", "b1-2", 15)])
        s = summarize(bad)
        self.assertEqual(s["malformed"], 7)
        self.assertEqual(s["greedy_matches"], 1)

    def test_summary(self):
        b = dict(BOOK)
        b["bench_offers"] = BOOK["bench_offers"] + [ask("b4-1", 5, expires_tick=210)]
        s = summarize(b)
        self.assertEqual((s["bench_offers"], s["asks"], s["bids"], s["runs"]), (10, 5, 5, 4))
        self.assertEqual(s["has_expires_tick"], 1)
        self.assertEqual(s["greedy_matches"], 3)
        self.assertEqual(s["greedy_quote_surplus"], (60 - 40) + (55 - 50) + 0)


def scan_for_key(root: Path) -> list:
    hits = []
    for p in root.rglob("*"):
        if p.is_file():
            data = p.read_bytes()
            if KEY.encode() in data or b"bk_" in data:
                hits.append(str(p))
    return hits


class TestRecord(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t18-bench-"))
        self.path = self.tmp / "logs" / "run" / "bench.jsonl"
        self.sec = Secrets(KEY)

    def test_record_appends_redacted_line(self):
        book = dict(BOOK, broker_key=KEY, note=KEY, nested={"a": [KEY, "ok"]})
        record(book, self.path, secrets=self.sec, tick=150)
        record(BOOK, self.path, secrets=self.sec, tick=151)
        rows = [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["tick"] for r in rows], [150, 151])
        self.assertNotIn("broker_key", rows[0]["book"])
        self.assertEqual(rows[0]["book"]["note"], "<redacted>")
        self.assertEqual(rows[0]["summary"]["greedy_matches"], 3)
        self.assertEqual(scan_for_key(self.tmp), [])

    def test_short_embedded_secret_refused_nothing_written(self):
        sec = Secrets("abc12")             # too short for redact's embedded rule
        with self.assertRaises(SecretLeak):
            record({"bench_offers": [], "x": "zzabc12zz"}, self.path, secrets=sec)
        self.assertFalse(self.path.exists())

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            record([1, 2], self.path)
        with self.assertRaises(ValueError):
            record({}, self.path, tick="7")
        self.assertFalse(self.path.exists())

    def test_secrets_repr_hides_key(self):
        self.assertNotIn(KEY, repr(self.sec))
        self.assertNotIn(KEY, str(self.sec))


class FakeGetter:
    def __init__(self, books):
        self.books = list(books)
        self.calls = []

    def __call__(self, path, headers):
        self.calls.append((path, dict(headers)))
        b = self.books.pop(0) if len(self.books) > 1 else self.books[0]
        if isinstance(b, Exception):
            raise b
        return b


class TestReadAndRecorder(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t18-bench-"))
        self.path = self.tmp / "bench.jsonl"

    def test_no_key_no_call(self):
        g = FakeGetter([BOOK])
        self.assertIsNone(read_book(g, Secrets(None)))
        self.assertIsNone(read_book(g, None))
        self.assertIsNone(read_book(g, "bk_notasecretsobject"))
        self.assertEqual(g.calls, [])
        self.assertIsNone(read_book(None, Secrets(KEY)))

    def test_only_book_path_with_header(self):
        g = FakeGetter([BOOK])
        self.assertEqual(read_book(g, Secrets(KEY)), BOOK)
        self.assertEqual(g.calls, [(BOOK_PATH, {"X-Broker-Key": KEY})])

    def test_errors_fail_closed(self):
        self.assertIsNone(read_book(FakeGetter([RuntimeError("down")]), Secrets(KEY)))
        self.assertIsNone(read_book(FakeGetter([[1, 2]]), Secrets(KEY)))
        rec = BenchRecorder(FakeGetter([RuntimeError("down")]), Secrets(KEY), self.path)
        self.assertFalse(rec.poll(1))
        self.assertFalse(self.path.exists())

    def test_recorder_dedupes_by_state(self):
        b2 = {"bench_offers": BOOK["bench_offers"][:3]}
        g = FakeGetter([BOOK, BOOK, b2, b2])
        rec = BenchRecorder(g, Secrets(KEY), self.path)
        self.assertEqual([rec.poll(10), rec.poll(10), rec.poll(10), rec.poll(11)], [True, False, True, True])
        self.assertEqual(rec.recorded, 3)
        self.assertEqual({c[0] for c in g.calls}, {BOOK_PATH})
        self.assertEqual(scan_for_key(self.tmp), [])


class _Handler(BaseHTTPRequestHandler):
    seen: list = []

    def _count(self):
        type(self).seen.append((self.command, self.path, self.headers.get("X-Broker-Key")))

    def do_GET(self):
        self._count()
        body = json.dumps(BOOK).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _no(self):
        self._count()
        self.send_response(405)
        self.end_headers()

    do_POST = do_PUT = do_DELETE = do_PATCH = _no

    def log_message(self, *a):
        pass


class TestZeroWritesLoopback(unittest.TestCase):
    """End to end against 127.0.0.1: the server sees only GET /api/broker/book."""

    def test_zero_writes(self):
        _Handler.seen = []
        srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"

        def get(path, headers):          # a GET-only reader, as M1 would supply it
            req = urllib.request.Request(base + path, headers=dict(headers), method="GET")
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read())

        tmp = Path(tempfile.mkdtemp(prefix="t18-bench-"))
        try:
            rec = BenchRecorder(get, Secrets(KEY), tmp / "bench.jsonl")
            for t in range(5):
                rec.poll(t)
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual(len(_Handler.seen), 5)
        self.assertTrue(all(m == "GET" and p == BOOK_PATH for m, p, _ in _Handler.seen))
        self.assertEqual(rec.recorded, 5)
        self.assertEqual(scan_for_key(tmp), [])


class TestSourceIsReadOnly(unittest.TestCase):
    FORBIDDEN_TEXT = ("urllib", "http.client", "socket", "bazaar_sdk", "Bazaar(", "Broker(", "._call(", ".send(",
                      "write_permit", "requests", "subprocess")

    def test_no_network_or_write_primitives(self):
        for s in self.FORBIDDEN_TEXT:
            self.assertNotIn(s, BENCH_SRC, s)

    def test_no_write_routes_or_methods_in_literals(self):
        tree = ast.parse(BENCH_SRC)
        consts = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        doc = ast.get_docstring(tree)
        for c in consts:
            if c == doc:
                continue
            for bad in ("POST", "DELETE", "PUT", "PATCH", "/matches", "/announce", "/api/offers", "/api/threads"):
                self.assertNotIn(bad, c)
        api = [c for c in consts if c.startswith("/api/")]
        self.assertEqual(api, [BOOK_PATH])

    def test_imports_only_stdlib_and_m0(self):
        tree = ast.parse(BENCH_SRC)
        mods = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                mods.update(a.name for a in n.names)
            elif isinstance(n, ast.ImportFrom):
                mods.add(n.module)
        self.assertLessEqual(mods, {"__future__", "json", "os", "re", "time", "pathlib", "typing",
                                    "agent.contracts", "agent.redact"})


if __name__ == "__main__":
    unittest.main()
