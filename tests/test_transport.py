"""M1 tests: INV-01 (single write point), INV-02 (transport side), INV-14 (fail-closed classification), INV-18,
INV-21 (hosts), dashboard redaction and api/index.py fail-closed auth. Only in-process fakes and 127.0.0.1."""
from __future__ import annotations

import base64
import hashlib
import http.client
import http.server
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock

import tests  # noqa: F401  (isolates the environment: BAZAAR_TEST=1, no key, no .env)
from agent import transport as T
from agent.contracts import PROD_URL, Paths

REPO = Path(__file__).resolve().parents[1]
HARVEST = REPO / "tests" / "fixtures" / "harvest"
LOOP = "http://127.0.0.1:9"          # discard port: never actually reached by the fakes


class FakeClock:
    def __init__(self, t: float = 1000.0, on_sleep=None):
        self.t, self.on_sleep, self.slept = t, on_sleep, 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s
        self.slept += s
        if self.on_sleep:
            self.on_sleep()


class FakeHttp:
    """http(method, url, data, headers, timeout) -> (status, bytes); records every call."""

    def __init__(self, *answers):
        self.answers = list(answers) or [(200, b'{"ok": true}')]
        self.calls = []

    def __call__(self, method, url, data, headers, timeout):
        self.calls.append((method, url, data, dict(headers)))
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, BaseException):
            raise a
        if callable(a):
            return a(method, url, data, headers)
        return a


def _transport(mode="live", http=None, root=None, key="tk-test", clock=None, **kw):
    root = root or tempfile.mkdtemp(prefix="t18-m1-")
    lim = T.RateLimiter(clock=clock or FakeClock())
    return T.GuardedTransport(LOOP, key, mode=mode, paths=Paths.at(root), limiter=lim, http=http or FakeHttp(), **kw)


def _canon(body) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


# ----------------------------------------------------------------------------------------------- INV-01

class WriteBarrier(unittest.TestCase):
    PATH, BODY = "/api/offers/7/accept", {"assets": [11]}

    def test_permitted_write_sends_exactly_once(self):
        h = FakeHttp((200, b'{"offer": {"id": 7, "status": "accepted"}}'))
        t = _transport(http=h)
        with T.write_permit("i1", "POST", self.PATH, self.BODY):
            r = t.send("POST", self.PATH, self.BODY)
        self.assertEqual(r.status, "ok")
        self.assertEqual(len(h.calls), 1)
        method, url, data, headers = h.calls[0]
        self.assertEqual((method, url, data), ("POST", LOOP + self.PATH, _canon(self.BODY)))
        self.assertEqual(headers["X-Team-Key"], "tk-test")

    def test_no_permit(self):
        h = FakeHttp()
        t = _transport(http=h)
        with self.assertRaises(T.GateViolation):
            t.send("POST", self.PATH, self.BODY)
        self.assertEqual(h.calls, [])

    def test_permit_for_other_route_body_or_method(self):
        h = FakeHttp()
        t = _transport(http=h)
        for m, p, b in (("POST", "/api/offers/8/accept", self.BODY), ("POST", self.PATH, {"assets": [12]}),
                        ("POST", self.PATH, None), ("DELETE", "/api/offers/7", None)):
            with T.write_permit("i", m, p, b):
                with self.assertRaises(T.GateViolation):
                    t.send("POST", self.PATH, self.BODY)
        self.assertEqual(h.calls, [])

    def test_permit_is_single_use(self):
        h = FakeHttp()
        t = _transport(http=h)
        with T.write_permit("i", "POST", self.PATH, self.BODY):
            t.send("POST", self.PATH, self.BODY)
            with self.assertRaises(T.GateViolation):
                t.send("POST", self.PATH, self.BODY)
        with self.assertRaises(T.GateViolation):                        # outside the with: gone
            t.send("POST", self.PATH, self.BODY)
        self.assertEqual(len(h.calls), 1)

    def test_nested_permit_refused(self):
        with T.write_permit("a", "POST", self.PATH, self.BODY):
            with self.assertRaises(T.GateViolation):
                with T.write_permit("b", "POST", self.PATH, self.BODY):
                    pass

    def test_twisted_paths_refused_with_zero_requests(self):
        h = FakeHttp()
        t = _transport(http=h)
        for p in ("/api//admin", "/API/admin", "/api/%61dmin", "/api/offers\n", "/api/admin", "/api/offers/7/accept/",
                  "/api/offers/7/accept?x=1", "/api/flags", "/api/broker/matches",
                  "/api/offers/../admin", " /api/offers", "/api/offers/7/accept\x00"):
            with T.write_permit("i", "POST", p, {}):
                with self.assertRaises(T.GateViolation, msg=p):
                    t.send("POST", p, {})
            with self.assertRaises(T.GateViolation, msg=p):
                t._call("GET", p)
        self.assertEqual(h.calls, [])

    def test_get_allowlist(self):
        h = FakeHttp((200, b'{"offers": []}'))
        t = _transport(mode="read", http=h)
        self.assertEqual(t.board("rastro"), {"offers": []})
        self.assertEqual(t.board("t07-shop"), {"offers": []})        # D2: every venue's board
        for p in ("/api/admin/flags", "/api/broker/book", "/api/dealers/abuela", "/api/health", "/api/venues/x/close",
                  "/api/me/value/x", "/api/cards/abc"):
            with self.assertRaises(T.GateViolation, msg=p):
                t._call("GET", p)
        with self.assertRaises(T.GateViolation):
            t._call("GET", "/api/me", query={"admin": 1})
        self.assertEqual(len(h.calls), 2)

    def test_sdk_write_methods_and_broker_cannot_write(self):
        h = FakeHttp()
        for mode in ("read", "dry", "live"):
            t = _transport(mode=mode, http=h)
            for f in (lambda: t.cancel(5), lambda: t.accept(7), lambda: t.open_venue("x"), lambda: t.flag(1),
                      lambda: t.close_thread(3), lambda: t.call("PATCH", "/api/venues/x", {}),
                      lambda: t.broker("bk_whatever"), lambda: t.list_offer({"cash": 1}, {"cards": ["LAT-09"]})):
                with self.assertRaises(T.GateViolation):
                    f()
        self.assertEqual(h.calls, [])

    def test_mode_is_read_only(self):
        t = _transport(mode="read")
        with self.assertRaises(AttributeError):
            t.mode = "live"
        for name in ("_mode", "url", "key", "_http_fn", "paths"):
            with self.assertRaises(T.GateViolation):
                setattr(t, name, "x")
        self.assertEqual(t.mode, "read")


# ------------------------------------------------------------------------------------- INV-02 (transport)

class NoWriteOutsideLive(unittest.TestCase):
    PATH, BODY = "/api/offers/9", None

    def test_dry_and_read_never_send(self):
        for mode in ("read", "dry"):
            h = FakeHttp()
            t = _transport(mode=mode, http=h)
            with T.write_permit("i", "DELETE", self.PATH, self.BODY):
                with self.assertRaises(T.GateViolation):
                    t.send("DELETE", self.PATH, self.BODY)
            self.assertEqual(h.calls, [])

    def test_stop_file_variants(self):
        for name in ("STOP", "STOP.txt", "stop", "stop.md", "Stop.json"):
            root = tempfile.mkdtemp()
            Path(root, name).write_text("fire", encoding="utf-8")
            self.assertIn(name, T.stop_active(Paths.at(root)))
            h = FakeHttp()
            t = _transport(http=h, root=root)
            with T.write_permit("i", "DELETE", self.PATH, None):
                with self.assertRaises(T.StopActive):
                    t.send("DELETE", self.PATH, None)
            self.assertEqual(h.calls, [])
        root = tempfile.mkdtemp()
        Path(root, "stopwatch.py").write_text("", encoding="utf-8")
        self.assertIsNone(T.stop_active(Paths.at(root)))

    def test_missing_root_fails_closed(self):
        self.assertTrue(T.stop_active(Paths.at(Path(tempfile.mkdtemp()) / "nope")))

    def test_stop_created_between_decision_and_send(self):
        root = tempfile.mkdtemp()
        clock = FakeClock(on_sleep=lambda: Path(root, "STOP.txt").write_text("late", encoding="utf-8"))
        h = FakeHttp()
        t = _transport(http=h, root=root, clock=clock)
        for _ in range(5):                       # drain the bucket so the send has to wait
            t.limiter.take(priority=True)
        with T.write_permit("i", "DELETE", self.PATH, None):
            with self.assertRaises(T.StopActive):
                t.send("DELETE", self.PATH, None)
        self.assertGreater(clock.slept, 0)
        self.assertEqual(h.calls, [])


# ---------------------------------------------------------------------------------------------- INV-14

class Classification(unittest.TestCase):
    def _send(self, answer):
        h = FakeHttp(answer)
        t = _transport(http=h)
        with T.write_permit("i", "POST", "/api/offers", {"a": 1}):
            r = t.send("POST", "/api/offers", {"a": 1})
        self.assertEqual(len(h.calls), 1)                              # never retried
        return r

    def test_unclean_answers_are_unknown(self):
        cases = {
            "html_200": (200, b"<html><body>ok</body></html>"),
            "truncated_body": (200, b'{"offer": {"id": 5, "sta'),
            "redirect_302": (302, b""),
            "redirect_302_json": (302, b'{"error": "moved", "message": "x"}'),
            "incomplete_read": http.client.IncompleteRead(b'{"of', 40),
            "timeout": TimeoutError("timed out"),
            "network": ConnectionResetError("reset"),
            "json_list_200": (200, b"[1, 2]"),
            "empty_200": (200, b""),
            "http_500": (500, b'{"error": "boom", "message": "x"}'),
            "http_502_html": (502, b"<html>bad gateway</html>"),
            "4xx_no_game_body": (404, b"Not Found"),
            "422_detail": (422, b'{"detail": [{"msg": "bad"}]}'),
            "429_other": (429, b'{"error": "slow", "message": "x"}'),
            "429_no_body": (429, b""),
            "bad_status": ("200", b"{}"),
        }
        for name, ans in cases.items():
            self.assertEqual(self._send(ans).status, "unknown", name)

    def test_clean_answers(self):
        r = self._send((201, b'{"offer": {"id": 5}}'))
        self.assertEqual((r.status, r.http, r.body), ("ok", 201, {"offer": {"id": 5}}))
        r = self._send((400, b'{"error": "insufficient_cash", "message": "no"}'))
        self.assertEqual((r.status, r.code), ("refused", "insufficient_cash"))
        for code in ("wait_for_tick", "rate_limited"):
            r = self._send((429, json.dumps({"error": code, "message": "later"}).encode()))
            self.assertEqual((r.status, r.code), ("deferred", code))

    def test_real_http_redirect_and_incomplete_read(self):
        """Over a real socket on 127.0.0.1 with the default urllib client (no redirects followed)."""
        hits = []

        class H(http.server.BaseHTTPRequestHandler):
            def _do(self):
                hits.append((self.command, self.path, self.headers.get("X-Team-Key")))
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(n)
                if self.path.startswith("/api/offers") or self.path == "/api/me":
                    self.send_response(302)
                    self.send_header("Location", "http://127.0.0.1:%d/landing" % self.server.server_port)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                elif self.path == "/api/clock":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", "100")
                    self.end_headers()
                    self.wfile.write(b'{"tick": 1')
                    self.wfile.flush()
                    self.close_connection = True
                else:
                    body = b'{"landed": true}'
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
            do_GET = do_POST = do_DELETE = _do

            def log_message(self, *a):
                pass

        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        try:
            url = "http://127.0.0.1:%d" % srv.server_port
            t = T.GuardedTransport(url, "tk-test", mode="live", paths=Paths.at(tempfile.mkdtemp()),
                                   limiter=T.RateLimiter(), get_retries=0, timeout=5)
            with T.write_permit("i", "POST", "/api/offers", {"x": 1}):
                r = t.send("POST", "/api/offers", {"x": 1})
            self.assertEqual((r.status, r.http), ("unknown", 302))
            with self.assertRaises(T.BazaarError):
                t.me()                                                    # GET redirect -> error, not followed
            with self.assertRaises(T.BazaarError):
                t.clock()                                                 # truncated body
            with T.write_permit("j", "POST", "/api/offers/3/accept", {}):
                pass
            self.assertNotIn("/landing", [p for _, p, _ in hits])
            self.assertEqual([p for _, p, _ in hits], ["/api/offers", "/api/me", "/api/clock"])
        finally:
            srv.shutdown()
            srv.server_close()


# ------------------------------------------------------------------------------------------ GET retries

class Reads(unittest.TestCase):
    def test_retries_only_network_and_rate_limited(self):
        h = FakeHttp(ConnectionError("x"), (429, b'{"error": "rate_limited", "message": "x"}'), (200, b'{"tick": 4}'))
        t = _transport(mode="read", http=h)
        self.assertEqual(t.clock(), {"tick": 4})
        self.assertEqual(len(h.calls), 3)
        h = FakeHttp(ConnectionError("x"))
        t = _transport(mode="read", http=h)
        with self.assertRaises(T.BazaarError):
            t.clock()
        self.assertEqual(len(h.calls), 3)                                 # 1 + get_retries(2)
        for ans in ((200, b"<html>"), (400, b'{"error": "bad", "message": "x"}'), (500, b"")):
            h = FakeHttp(ans)
            t = _transport(mode="read", http=h)
            with self.assertRaises(T.BazaarError):
                t.clock()
            self.assertEqual(len(h.calls), 1)

    def test_three_rate_limited_slow_the_limiter(self):
        rl = (429, b'{"error": "rate_limited", "message": "x"}')
        h = FakeHttp(rl, rl, rl, (200, b"{}"))
        t = _transport(mode="read", http=h, get_retries=3)
        t.clock()
        self.assertEqual(t.limiter.current_rate(), 1.5)

    def test_query_and_key_header(self):
        h = FakeHttp((200, b'{"your_value": 3.5}'))
        t = _transport(mode="read", http=h)
        t.value("LAT-09")
        self.assertEqual(h.calls[0][1], LOOP + "/api/me/value?card=LAT-09")


class Limiter(unittest.TestCase):
    def test_reserve_and_rate(self):
        c = FakeClock()
        lim = T.RateLimiter(rate=2.5, burst=5, reserve=1, clock=c)
        for _ in range(4):
            lim.take()
        self.assertEqual(c.slept, 0)
        lim.take(priority=True)                                           # the reserved token
        self.assertEqual(c.slept, 0)
        start = c.t
        for _ in range(10):
            lim.take()
        self.assertGreaterEqual(c.t - start, (10 + 1 - 0) / 2.5 - 1e-6)   # refills at 2.5/s, keeping 1 reserved
        lim.slow_down(1.0, 60)
        self.assertEqual(lim.current_rate(), 1.0)
        c.t += 61
        self.assertEqual(lim.current_rate(), 2.5)

    def test_bad_params(self):
        for kw in ({"rate": 0}, {"burst": 0}, {"reserve": 5}, {"reserve": -1}):
            with self.assertRaises(ValueError):
                T.RateLimiter(**kw)


# ----------------------------------------------------------------------------------- targets, INV-18/21

class Targets(unittest.TestCase):
    def test_test_mode_only_loopback(self):
        root = Paths.at(tempfile.mkdtemp())
        for url in (PROD_URL, "https://evil.example", "http://127.0.0.1.evil.example", "http://127.0.0.1:1/api"):
            for mode in ("read", "dry", "live"):
                with self.assertRaises(T.GateViolation, msg=url):
                    T.GuardedTransport(url, "tk-test", mode=mode, paths=root)
        with self.assertRaises(T.GateViolation):
            T.GuardedTransport(LOOP, "tk-real-abcdef-123456", mode="read", paths=root)
        with self.assertRaises(T.GateViolation):
            T.GuardedTransport(LOOP, "tk-test", mode="wild", paths=root)
        self.assertEqual(T.GuardedTransport(LOOP, "fake-key", mode="live", paths=root).mode, "live")

    def test_live_rules_outside_test_mode(self):
        root = Paths.at(tempfile.mkdtemp())
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BAZAAR_TEST")
            self.assertEqual(T.GuardedTransport(PROD_URL, "tk-x", mode="live", paths=root).mode, "live")   # no I/O
            with self.assertRaises(T.GateViolation):
                T.GuardedTransport(LOOP, "tk-test", mode="live", paths=root)
            with self.assertRaises(T.GateViolation):
                T.GuardedTransport("https://staging.example", "tk-x", mode="read", paths=root)
        self.assertEqual(os.environ.get("BAZAAR_TEST"), "1")

    def test_key_never_in_repr_or_errors(self):
        h = FakeHttp((500, b"oops"))
        t = _transport(mode="read", http=h, key="fake-key")
        self.assertNotIn("fake-key", repr(t))
        try:
            t.clock()
        except T.BazaarError as e:
            self.assertNotIn("fake-key", str(e) + repr(e))

    def test_audit_rule(self):
        T.audit_check("GET", LOOP + "/api/clock", test_mode=True)
        with self.assertRaises(T.GateViolation):
            T.audit_check("GET", PROD_URL + "/api/clock", test_mode=True)
        with self.assertRaises(T.GateViolation):
            T.audit_check("POST", PROD_URL + "/api/offers", test_mode=False)
        with self.assertRaises(T.GateViolation):
            T.audit_check("DELETE", "http://127.0.0.1:9/api/offers/1", test_mode=False)
        T.audit_check("GET", PROD_URL + "/api/clock", test_mode=False)
        url = PROD_URL + "/api/offers/3/accept"
        token = T._SENDING.set(("POST", url))                          # what send() sets around its one request
        try:
            T.audit_check("POST", url, test_mode=False)
            with self.assertRaises(T.GateViolation):
                T.audit_check("POST", PROD_URL + "/api/offers/4/accept", test_mode=False)
            with self.assertRaises(T.GateViolation):
                T.audit_check("DELETE", url, test_mode=False)
        finally:
            T._SENDING.reset(token)
        with self.assertRaises(T.GateViolation):
            T.audit_check("POST", url, test_mode=False)

    def test_audit_hook_live_in_process(self):
        with self.assertRaises(T.GateViolation):                         # raised before any DNS / connect
            urllib.request.urlopen("http://example.invalid/api/clock", timeout=0.5)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            with self.assertRaises(T.GateViolation):
                s.connect(("192.0.2.1", 80))                              # TEST-NET-1, never routable anyway
        finally:
            s.close()

    def test_audit_hook_blocks_raw_post_outside_test_mode(self):
        env = {k: v for k, v in os.environ.items() if k not in ("BAZAAR_TEST", "BAZAAR_KEY", "BAZAAR_URL")}
        env["PYTHONIOENCODING"] = "utf-8"
        code = ("import urllib.request, agent.transport\n"
                "try:\n"
                "    urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:9/api/offers', data=b'{}',"
                " method='POST'), timeout=1)\n"
                "except agent.transport.GateViolation:\n"
                "    print('BLOCKED')\n"
                "except Exception as e:\n"
                "    print('LEAKED', type(e).__name__)\n")
        out = subprocess.run([sys.executable, "-c", code], cwd=str(REPO), env=env, capture_output=True, text=True,
                             timeout=60)
        self.assertIn("BLOCKED", out.stdout, out.stderr)


# ----------------------------------------------------------------------------------------- public_get

class PublicGet(unittest.TestCase):
    def setUp(self):
        T._PUBLIC_LAST[0] = float("-inf")

    def test_keyless_allowlisted_one_per_second(self):
        h = FakeHttp((200, b'{"tick": 3}'))
        c = FakeClock()
        lim = T.RateLimiter(clock=c)
        self.assertEqual(T.public_get(LOOP, "/api/clock", lim, http=h), {"tick": 3})
        T.public_get(LOOP, "/api/schedule", lim, http=h)
        self.assertGreaterEqual(c.slept, 1.0 - 1e-9)
        self.assertNotIn("X-Team-Key", h.calls[0][3])
        with self.assertRaises(T.GateViolation):
            T.public_get(LOOP, "/api/admin", lim, http=h)
        with self.assertRaises(T.GateViolation):
            T.public_get(PROD_URL, "/api/clock", lim, http=h)
        with self.assertRaises(T.BazaarError):
            T.public_get(LOOP, "/api/clock", lim, http=FakeHttp((200, b"<html>")))


# ------------------------------------------------------------------------------- client / dashboard / api

def _harvest(name):
    return (HARVEST / f"{name}.json").read_bytes()


def _game_http(me_extra=None):
    me = json.loads(_harvest("me"))
    me.update(me_extra or {})
    values = json.loads(_harvest("me_values_all_cards"))
    routes = {"/api/me": json.dumps(me).encode(), "/api/clock": _harvest("clock"),
              "/api/catalog": _harvest("catalog"), "/api/leaderboard": _harvest("leaderboard"),
              "/api/feed": _harvest("feed_last500"), "/api/venues/rastro/offers": _harvest("rastro_offers")}

    def answer(method, url, data, headers):
        u = urllib.parse.urlsplit(url)
        if u.path == "/api/me/value":
            card = urllib.parse.parse_qs(u.query)["card"][0]
            return 200, json.dumps({"card": card, "your_value": values.get(card, 0.0)}).encode()
        return (200, routes[u.path]) if u.path in routes else (404, b'{"error": "not_found", "message": "x"}')
    return FakeHttp(answer)


class ClientAndDashboard(unittest.TestCase):
    def test_client_is_read_only_by_default(self):
        from agent.client import client
        with mock.patch.dict(os.environ, {"BAZAAR_KEY": "tk-test", "BAZAAR_URL": LOOP}):
            b = client()
            self.assertEqual(b.mode, "read")
            for f in (lambda: b.accept(1), lambda: b.cancel(1), lambda: b.open_pack(3),
                      lambda: b.say(1, "hola", price=5), lambda: b.duel_accept(2)):
                with self.assertRaises(T.GateViolation):
                    f()
        with self.assertRaises(RuntimeError):
            client()

    def test_dashboard_snapshot_redacts_me(self):
        from agent import dashboard
        secret = "tk-secretvalue-123456"
        h = _game_http({"api_key": secret, "note": "mine is " + secret, "broker_token": "bk_abcdefgh"})
        t = _transport(mode="read", http=h)
        tmp = tempfile.mkdtemp()
        with mock.patch.object(dashboard, "LOG_DIR", tmp), \
                mock.patch.object(dashboard, "FEED", os.path.join(tmp, "feed.jsonl")):
            data = dashboard.snapshot(t, {})
        blob = json.dumps(data)
        self.assertNotIn(secret, blob)
        self.assertNotIn("bk_abcdefgh", blob)
        self.assertNotIn("api_key", blob)
        self.assertEqual(data["me"]["id"], json.loads(_harvest("me"))["id"])
        self.assertTrue(all(c[0] == "GET" for c in h.calls))
        self.assertIn("<title", dashboard.page(data).lower())


class ApiIndex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved = dict(os.environ)
        try:
            os.environ["BAZAAR_LOGS"] = tempfile.mkdtemp()
            spec = importlib.util.spec_from_file_location("t18_api_index", REPO / "api" / "index.py")
            cls.mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.mod)
        finally:
            os.environ.clear()
            os.environ.update(saved)
        cls.mod.handler.log_message = lambda *a: None
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), cls.mod.handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _get(self, path="/", auth=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=10)
        headers = {"Authorization": "Basic " + base64.b64encode(auth.encode()).decode()} if auth else {}
        conn.request("GET", path, headers=headers)
        r = conn.getresponse()
        body = r.read()
        conn.close()
        return r.status, body

    def test_no_password_configured_is_401(self):
        with mock.patch.dict(os.environ, {"DASHBOARD_PASSWORD": ""}):
            self.assertEqual(self._get()[0], 401)
            self.assertEqual(self._get("/data.json", "x:anything")[0], 401)
        os.environ.pop("DASHBOARD_PASSWORD", None)
        self.assertEqual(self._get()[0], 401)

    def test_password(self):
        with mock.patch.dict(os.environ, {"DASHBOARD_PASSWORD": "s3cret"}):
            self.assertEqual(self._get()[0], 401)
            self.assertEqual(self._get("/", "team:wrong")[0], 401)
            status, body = self._get("/", "team:s3cret")
            self.assertEqual(status, 200)
            self.assertIn(b"<title", body.lower())

    def test_data_uses_read_client_and_redacts_errors(self):
        seen = []

        def fake_client(mode="read"):
            seen.append(mode)
            raise RuntimeError("boom tk-leakyvalue-999999")
        self.mod._cache["body"] = b""
        with mock.patch.dict(os.environ, {"DASHBOARD_PASSWORD": "s3cret"}), \
                mock.patch.object(self.mod, "client", fake_client):
            status, body = self._get("/data.json", "team:s3cret")
        self.assertEqual(status, 502)
        self.assertEqual(seen, ["read"])
        self.assertNotIn(b"tk-leakyvalue", body)


if __name__ == "__main__":
    unittest.main()
