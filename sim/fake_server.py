"""M6a: real HTTP front for FakeGame on 127.0.0.1 (stdlib ThreadingHTTPServer), plus the in-process loopback.

serve(game, port=0, faults=None) -> (url, stop). Only binds 127.0.0.1. Every request goes through
FakeGame.respond (same code path as the in-process transport game.http), so faults behave the same way:
drop_after_commit closes the socket without a response, incomplete_read announces a longer body than it sends.
Any /api/admin/* route answers 404 and is recorded in game.violations.

NOTES: no auto-ticking thread (tests call game.advance()); a lock serialises the game between handler threads.
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Tuple

ADMIN_PREFIX = "/api/admin"


def serve(game, port: int = 0, faults=None) -> Tuple[str, Callable[[], None]]:
    if faults is not None:
        game.faults = faults
    lock = getattr(game, "_server_lock", None) or threading.RLock()
    game._server_lock = lock

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a, **k):      # quiet
            return

        def _do(self):
            n = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(n) if n > 0 else None
            # ADMIN_PREFIX routes are answered 404 and recorded as a violation by FakeGame._route
            with lock:
                status, raw, action = game.respond(self.command, "http://127.0.0.1" + self.path, data,
                                                   dict(self.headers.items()))
            if action == "drop":
                self.close_connection = True
                try:
                    self.connection.shutdown(2)
                except OSError:
                    pass
                return
            ctype = "text/html" if raw[:1] == b"<" else "application/json"
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            if status == 302:
                self.send_header("Location", "http://127.0.0.1:1/elsewhere")
            if action == "incomplete":
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw[: len(raw) // 2])
                self.wfile.flush()
                self.close_connection = True
                try:
                    self.connection.shutdown(2)
                except OSError:
                    pass
                return
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_GET = do_POST = do_DELETE = do_PATCH = do_PUT = _do

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    th = threading.Thread(target=srv.serve_forever, name="fake-bazaar", daemon=True)
    th.start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"

    def stop() -> None:
        srv.shutdown()
        srv.server_close()
        th.join(timeout=5)

    return url, stop
