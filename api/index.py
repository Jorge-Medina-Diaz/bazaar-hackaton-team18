"""Vercel entry point for the team dashboard: the same page as run_dashboard.py, online for the team.

Routes (vercel.json sends everything here):  /  -> the live page   /data.json -> the snapshot it polls.
Env vars (Vercel project settings): BAZAAR_KEY (team key, never sent to the browser), DASHBOARD_PASSWORD (basic
auth; any user name). Only GETs to the game; one snapshot per CACHE_S per warm instance, however many viewers.
Fail closed (M1, spec §2.2): with DASHBOARD_PASSWORD empty or unset every request gets 401; the game is read with
client("read") (writes impossible); error bodies are redacted.
"""
import base64, hmac, json, os, sys, time  # noqa: E401
from http.server import BaseHTTPRequestHandler

os.environ.setdefault("BAZAAR_LOGS", "/tmp/logs")  # the deploy is read-only except /tmp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.client import client  # noqa: E402
from agent.dashboard import page, snapshot  # noqa: E402
from agent.redact import redact  # noqa: E402

CACHE_S = 30
_state, _cache = {}, {"at": 0.0, "body": b""}


def _data() -> bytes:
    if time.time() - _cache["at"] >= CACHE_S or not _cache["body"]:
        _cache["body"] = json.dumps(snapshot(client("read"), _state), ensure_ascii=False).encode("utf-8")
        _cache["at"] = time.time()
    return _cache["body"]


class handler(BaseHTTPRequestHandler):
    def _authorized(self) -> bool:
        want = os.environ.get("DASHBOARD_PASSWORD", "")
        if not want:
            return False                       # fail closed: no password configured, nobody gets in
        got = self.headers.get("Authorization", "") or ""
        if not got.startswith("Basic "):
            return False
        try:
            pwd = base64.b64decode(got[len("Basic "):], validate=True).decode("utf-8").partition(":")[2]
        except Exception:
            return False
        return hmac.compare_digest(pwd.encode("utf-8"), want.encode("utf-8"))

    def _send(self, code: int, body: bytes, kind: str, extra: dict = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._authorized():
            self._send(401, b"Contrasena del equipo", "text/plain; charset=utf-8",
                       {"WWW-Authenticate": 'Basic realm="Team 18", charset="UTF-8"'})
            return
        path = self.path.split("?")[0]
        try:
            if path == "/data.json":
                self._send(200, _data(), "application/json")
            else:
                self._send(200, page(None).encode("utf-8"), "text/html; charset=utf-8")
        except Exception as e:  # e.g. the game is closed overnight: the page keeps the last data and shows it as stale
            self._send(502, json.dumps({"error": redact(repr(e))}).encode("utf-8"), "application/json")
