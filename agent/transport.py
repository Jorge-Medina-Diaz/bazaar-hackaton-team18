"""M1 transport: the physical write barrier of the harness (docs/harness-spec.md §0, §2.2, INV-01/02/14/18/21).

Three layers keep every non-GET request inside the Gate:
  1. GuardedTransport re-implements the SDK's _call (it never calls the SDK one). GET goes only to GET_ALLOWLIST
     (re.fullmatch). Any other method goes through send(), which needs a one-use permit whose
     (method, exact path, sha256 of the canonical JSON body) matches with ==, a WRITE_ROUTES fullmatch,
     mode "live" and no STOP file. Everything else raises GateViolation before a single byte leaves.
  2. An audit hook (installed when this module is imported) rejects any urllib request that is not a GET unless
     send() is sending exactly that request. Under BAZAAR_TEST=1 it also rejects any host / socket that is not
     loopback (INV-21).
  3. The AST test of M17 (forbidden names outside transport.py / gate.py).

Responses are classified fail-closed: ok (2xx + JSON object), deferred (429 wait_for_tick / rate_limited),
refused (4xx with the game's {error, message} body). Everything else (3xx, 2xx not JSON or truncated, 4xx without
the game's body, 5xx, network, timeout, any exception) is "unknown" and the caller freezes the domain.

Design notes
- Test mode exception in the audit hook: with BAZAAR_TEST=1 a non-GET urllib request to a LOOPBACK host is let
  through without a permit, so the sim tests can drive the fake server with the real SDK (§10 test_sim). Outside
  test mode the hook is strict. GuardedTransport itself never relaxes in test mode (the permit is always required).
- GateViolation raised by the audit hook inside send() propagates (it is a barrier breach, not an "unknown").
- public_get() has an extra keyword-only `http=` (test double); signature otherwise as in §2.2.
- GET query keys are restricted to {card, limit, status, done} (the ones the SDK reads use).
- Against loopback the key must be "", "tk-test" or "fake-key"; any other key -> GateViolation (stricter than §2.2).
- Non-test processes may only target PROD_URL or loopback (read/dry); live only PROD_URL (or loopback in test mode).
- stop_active() is case-insensitive (Stop.md also stops) and fails closed if the root cannot be listed.
- Not done: http.client / raw socket writes in production are only covered by the AST test (M17), not the hook.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional

from agent.contracts import GET_ALLOWLIST, PROD_URL, Paths
from bazaar_sdk import Bazaar, BazaarError

__all__ = ["WRITE_ROUTES", "GET_ALLOWLIST", "GateViolation", "StopActive", "Response", "RateLimiter",
           "stop_active", "write_permit", "install_audit_hook", "GuardedTransport", "public_get", "classify",
           "BazaarError", "TEST_KEYS", "LOOPBACK_HOSTS"]

WRITE_ROUTES: Mapping[str, tuple] = MappingProxyType({        # re.fullmatch, never re.match
    "accept": ("POST", r"/api/offers/\d+/accept"),
    "list_offer": ("POST", r"/api/offers"),
    "cancel": ("DELETE", r"/api/offers/\d+"),
    "open_thread": ("POST", r"/api/threads"),
    "say": ("POST", r"/api/threads/\d+/messages"),
    "close_thread": ("POST", r"/api/threads/\d+/close"),
    "open_pack": ("POST", r"/api/packs/\d+/open"),
    "duel_say": ("POST", r"/api/duels/\d+/messages"),
    "duel_accept": ("POST", r"/api/duels/\d+/accept"),
})

TEST_KEYS = frozenset({"tk-test", "fake-key"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
QUERY_KEYS = frozenset({"card", "limit", "status", "done"})
MODES = frozenset({"read", "dry", "live"})
_PATH_OK = re.compile(r"/api/[A-Za-z0-9_/-]*")          # no %, no ., no whitespace, no control chars, no ?


class GateViolation(Exception):
    """A request tried to leave the band. Never caught by the agent except to write STOP and exit 2."""


class StopActive(Exception):
    """A STOP file exists in the root: nothing is written."""


@dataclass(frozen=True)
class Response:
    status: str                  # "ok" | "deferred" | "refused" | "unknown"
    http: int
    code: Optional[str]
    body: Optional[Mapping]


def _test_mode() -> bool:
    return os.environ.get("BAZAAR_TEST") == "1"


# --------------------------------------------------------------------------------------------- limiter

class _SysClock:
    @staticmethod
    def now() -> float:
        return time.monotonic()

    @staticmethod
    def sleep(seconds: float) -> None:
        time.sleep(seconds)


class RateLimiter:
    """Token bucket. take() without priority leaves `reserve` tokens for the Gate's fresh re-reads and sends."""

    def __init__(self, rate: float = 2.5, burst: int = 5, reserve: int = 1, clock=None):
        if not (isinstance(rate, (int, float)) and rate > 0):
            raise ValueError("rate must be > 0")
        if type(burst) is not int or burst < 1 or type(reserve) is not int or not 0 <= reserve < burst:
            raise ValueError("need int burst >= 1 and 0 <= reserve < burst")
        self.rate, self.burst, self.reserve = float(rate), burst, reserve
        self.clock = clock or _SysClock()
        self._tokens = float(burst)
        self._t = self.clock.now()
        self._slow_rate: Optional[float] = None
        self._slow_until = 0.0
        self._lock = threading.Lock()

    def current_rate(self, now: Optional[float] = None) -> float:
        now = self.clock.now() if now is None else now
        if self._slow_rate is not None and now < self._slow_until:
            return self._slow_rate
        return self.rate

    def _refill(self, now: float) -> None:
        if now > self._t:
            self._tokens = min(float(self.burst), self._tokens + (now - self._t) * self.current_rate(now))
        self._t = max(self._t, now)

    def take(self, priority: bool = False) -> None:
        need = 1.0 if priority else 1.0 + self.reserve
        while True:
            with self._lock:
                now = self.clock.now()
                self._refill(now)
                if self._tokens >= need:
                    self._tokens -= 1.0
                    return
                wait = (need - self._tokens) / self.current_rate(now)
            self.clock.sleep(max(wait, 0.001))

    def slow_down(self, rate: float, seconds: float) -> None:
        with self._lock:
            now = self.clock.now()
            self._refill(now)
            self._slow_rate = min(float(rate), self.rate)
            self._slow_until = now + float(seconds)


# ------------------------------------------------------------------------------------------------ STOP

def stop_active(paths: Paths) -> Optional[str]:
    """Reason if the root holds STOP, STOP.*, stop or stop.* (any case). Fails closed if the root can't be listed."""
    root = Path(paths.root)
    try:
        names = os.listdir(root)
    except OSError as e:
        return f"stop check failed ({e.__class__.__name__})"
    for n in sorted(names):
        low = n.lower()
        if low == "stop" or low.startswith("stop."):
            p = root / n
            text = ""
            try:
                if p.is_file():
                    text = p.read_text(encoding="utf-8", errors="replace")[:200].strip()
            except OSError:
                pass
            return f"{n}: {text}" if text else n
    return None


# ---------------------------------------------------------------------------------------------- permit

@dataclass
class _Permit:
    intent_id: str
    method: str
    path: str
    sha: str
    used: bool = False


_PERMIT: ContextVar[Optional[_Permit]] = ContextVar("t18_write_permit", default=None)
_SENDING: ContextVar[Optional[tuple]] = ContextVar("t18_sending", default=None)   # (METHOD, full url)


def _plain(o: Any) -> Any:
    if isinstance(o, Mapping):
        return dict(o)
    if isinstance(o, (tuple, set, frozenset)):
        return list(o)
    raise TypeError(f"not JSON: {type(o).__name__}")


def _canonical(body: Optional[Mapping]) -> bytes:
    if body is not None and not isinstance(body, Mapping):
        raise GateViolation("body must be a mapping or None")
    try:
        return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
                          default=_plain).encode("ascii")
    except (TypeError, ValueError) as e:
        raise GateViolation(f"body not canonical JSON: {e}") from None


def _sha(body: Optional[Mapping]) -> str:
    return hashlib.sha256(_canonical(body)).hexdigest()


@contextmanager
def write_permit(intent_id: str, method: str, path: str, body: Optional[Mapping]):
    """One-use permit for exactly (method, path, sha256(canonical body)). Only agent/gate.py may use it."""
    if type(intent_id) is not str or not intent_id or type(method) is not str or type(path) is not str:
        raise GateViolation("permit: intent_id, method and path must be non-empty str")
    if _PERMIT.get() is not None:
        raise GateViolation("permit: nested permits are not allowed")
    p = _Permit(intent_id, method, path, _sha(body))
    token = _PERMIT.set(p)
    try:
        yield
    finally:
        p.used = True
        _PERMIT.reset(token)


# ------------------------------------------------------------------------------------------ audit hook

_HOOK_INSTALLED = False


def _host(url: str) -> Optional[str]:
    try:
        return urllib.parse.urlsplit(url).hostname
    except ValueError:
        return None


def audit_check(method: Any, url: Any, test_mode: Optional[bool] = None) -> None:
    """The urllib.Request rule of the audit hook (pure; raises GateViolation)."""
    test_mode = _test_mode() if test_mode is None else test_mode
    m = str(method or "GET").upper()
    host = _host(str(url))
    if test_mode and host not in LOOPBACK_HOSTS:
        raise GateViolation("test mode: only loopback hosts")
    if m == "GET":
        return
    if _SENDING.get() == (m, str(url)):
        return
    if test_mode and host in LOOPBACK_HOSTS:
        return                                   # fake server driven by the real SDK in tests (see NOTES)
    raise GateViolation(f"audit: {m} without a write permit")


def _audit(event: str, args: tuple) -> None:
    if event == "urllib.Request":
        audit_check(args[3] if len(args) > 3 else None, args[0])
    elif event == "socket.connect":
        if _test_mode():
            addr = args[1] if len(args) > 1 else None
            if isinstance(addr, tuple) and addr and addr[0] not in LOOPBACK_HOSTS:
                raise GateViolation("test mode: socket to a non-loopback address")


def install_audit_hook() -> None:
    """Idempotent; called when this module is imported. Audit hooks cannot be removed."""
    global _HOOK_INSTALLED
    if not _HOOK_INSTALLED:
        sys.addaudithook(_audit)
        _HOOK_INSTALLED = True


install_audit_hook()


# ------------------------------------------------------------------------------------------- http/classify

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):     # never follow: 3xx -> HTTPError
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _urllib_http(method: str, url: str, data: Optional[bytes], headers: Mapping, timeout: float):
    req = urllib.request.Request(url, data=data, method=method, headers=dict(headers))
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        try:
            raw = e.read()
        finally:
            e.close()
        return e.code, raw


def _json_obj(raw: Any) -> Optional[dict]:
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        return None
    try:
        obj = json.loads(bytes(raw).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return obj if isinstance(obj, dict) else None


def classify(http: Any, raw: Any) -> Response:
    """Fail-closed classification of one HTTP answer (status, body bytes)."""
    if type(http) is not int:
        return Response("unknown", 0, "bad_status", None)
    body = _json_obj(raw)
    if 200 <= http < 300:
        return Response("ok", http, None, body) if body is not None else Response("unknown", http, "bad_body", None)
    if body is not None and isinstance(body.get("error"), str) and isinstance(body.get("message"), str):
        if http == 429:
            if body["error"] in ("wait_for_tick", "rate_limited"):
                return Response("deferred", http, body["error"], body)
            return Response("unknown", http, f"http_{http}", body)
        if 400 <= http < 500:
            return Response("refused", http, body["error"], body)
    return Response("unknown", http, f"http_{http}", body)


def _check_path(path: Any) -> str:
    if type(path) is not str or not _PATH_OK.fullmatch(path) or "//" in path:
        raise GateViolation("path rejected")
    return path


def _check_target(url: Any, key: Any) -> tuple:
    """(normalized url, is_loopback). GateViolation on any target the process may not talk to."""
    if type(url) is not str or type(key) is not str:
        raise GateViolation("url and key must be str")
    u = url.rstrip("/")
    try:
        parts = urllib.parse.urlsplit(u)
    except ValueError:
        raise GateViolation("bad url") from None
    if parts.path or parts.query or parts.fragment or parts.username or parts.password:
        raise GateViolation("url must be scheme://host[:port] only")
    host = parts.hostname
    loop = host in LOOPBACK_HOSTS and parts.scheme == "http"
    if _test_mode() and not loop:
        raise GateViolation("BAZAAR_TEST=1: only http://127.0.0.1")
    if not loop and u != PROD_URL:
        raise GateViolation("unknown host")
    if loop and key not in TEST_KEYS and key != "":
        raise GateViolation("a real key against loopback")
    return u, loop


# --------------------------------------------------------------------------------------------- transport

_FROZEN_ATTRS = frozenset({"_mode", "url", "key", "_headers", "_http_fn", "paths", "_loopback"})


class GuardedTransport(Bazaar):
    """The team's only connection. Reads by allowlist; writes only through send() with a Gate permit."""

    def __init__(self, url: str, key: str, *, mode: str = "read", paths: Paths,
                 limiter: Optional[RateLimiter] = None, get_retries: int = 2, timeout: float = 10.0,
                 http: Optional[Callable] = None):
        if mode not in MODES:
            raise GateViolation(f"mode must be one of {sorted(MODES)}")
        u, loop = _check_target(url, key)
        if mode == "live" and not ((u == PROD_URL and not _test_mode())
                                   or (_test_mode() and loop and key in TEST_KEYS)):
            raise GateViolation("live needs PROD_URL outside tests, or 127.0.0.1 + test key in tests")
        if not isinstance(paths, Paths):
            raise GateViolation("paths must be a Paths")
        super().__init__(u, key, timeout=float(timeout), wait_on_tick=False, retries=0)
        object.__setattr__(self, "_mode", mode)
        object.__setattr__(self, "_loopback", loop)
        object.__setattr__(self, "paths", paths)
        object.__setattr__(self, "_http_fn", http or _urllib_http)
        self.limiter = limiter or RateLimiter()
        self.get_retries = max(0, int(get_retries))
        self._rate_hits: list = []

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _FROZEN_ATTRS and name in self.__dict__:
            raise GateViolation(f"{name} is read-only")
        object.__setattr__(self, name, value)

    def __repr__(self) -> str:
        return f"GuardedTransport(url={self.url!r}, mode={self._mode!r})"

    @property
    def mode(self) -> str:
        return self._mode

    # ---- reads
    def _query(self, query: Optional[Mapping]) -> str:
        if not query:
            return ""
        q = {}
        for k, v in query.items():
            if k not in QUERY_KEYS:
                raise GateViolation(f"query key {k!r} not allowed")
            if v is None:
                continue
            q[k] = "true" if v is True else "false" if v is False else v
        return ("?" + urllib.parse.urlencode(q)) if q else ""

    def _note_rate_limited(self) -> None:
        now = self.limiter.clock.now()
        self._rate_hits = [t for t in self._rate_hits if now - t < 60.0] + [now]
        if len(self._rate_hits) >= 3:
            self.limiter.slow_down(1.5, 60.0)
            self._rate_hits = []

    def _get(self, path: str, query: Optional[Mapping] = None) -> dict:
        _check_path(path)
        if not re.fullmatch(GET_ALLOWLIST, path):
            raise GateViolation("GET outside the allowlist")
        url = self.url + path + self._query(query)
        headers = {"X-Team-Key": self.key, "Accept": "application/json"}
        attempt = 0
        while True:
            self.limiter.take()
            try:
                status, raw = self._http_fn("GET", url, None, headers, self.timeout)
                r = classify(status, raw)
            except GateViolation:
                raise
            except Exception as e:                                       # network, timeout, IncompleteRead...
                r = Response("unknown", 0, "network", {"exc": e.__class__.__name__})
            if r.status == "ok":
                return r.body
            if r.code == "rate_limited":
                self._note_rate_limited()
            if r.code in ("network", "rate_limited") and attempt < self.get_retries:
                attempt += 1
                self.limiter.clock.sleep(0.25 * attempt)
                continue
            msg = (r.body or {}).get("message") if isinstance(r.body, Mapping) else None
            raise BazaarError(r.code or r.status, f"GET {path}: {msg or r.status}", r.http)

    def _call(self, method: str, path: str, body: Any = None, query: Optional[dict] = None) -> Any:
        if method == "GET":
            return self._get(path, query)
        if query:
            raise GateViolation("writes take no query")
        r = self.send(method, path, body)
        if r.status == "ok":
            return r.body
        raise BazaarError(r.code or r.status, f"{method} {path}: {r.status}", r.http)

    def _sleep_until_next_tick(self) -> None:
        raise GateViolation("wait_on_tick is disabled")

    def broker(self, broker_key: str):
        raise GateViolation("broker desactivado")

    # ---- the one write path
    def send(self, method: str, path: str, body: Optional[Mapping]) -> Response:
        if type(method) is not str:
            raise GateViolation("method must be str")
        _check_path(path)
        if not any(m == method and re.fullmatch(rx, path) for m, rx in WRITE_ROUTES.values()):
            raise GateViolation("not a write route")
        data = _canonical(body)
        permit = _PERMIT.get()
        if permit is None or permit.used:
            raise GateViolation("no unused write permit")
        if (permit.method, permit.path, permit.sha) != (method, path, hashlib.sha256(data).hexdigest()):
            permit.used = True
            raise GateViolation("permit does not match (method, path, body)")
        permit.used = True                                               # one use, whatever happens next
        if self._mode != "live":
            raise GateViolation(f"mode {self._mode}: no writes")
        reason = stop_active(self.paths)
        if reason:
            raise StopActive(reason)
        self.limiter.take(priority=True)
        reason = stop_active(self.paths)                                 # STOP created while we waited
        if reason:
            raise StopActive(reason)
        url = self.url + path
        headers = {"X-Team-Key": self.key, "Accept": "application/json"}
        payload = None if body is None else data                        # like the SDK: bodiless writes send no body
        if payload is not None:
            headers["Content-Type"] = "application/json"
        token = _SENDING.set((method, url))
        try:
            status, raw = self._http_fn(method, url, payload, headers, self.timeout)
            r = classify(status, raw)
        except GateViolation:
            raise
        except Exception as e:                                           # incl. IncompleteRead, timeouts
            r = Response("unknown", 0, "exception", {"exc": e.__class__.__name__})
        finally:
            _SENDING.reset(token)
        if r.code == "rate_limited":
            self._note_rate_limited()
        return r


# ------------------------------------------------------------------------------------------- public reads

_PUBLIC_LOCK = threading.Lock()
_PUBLIC_LAST = [float("-inf")]


def public_get(base_url: str, path: str, limiter: RateLimiter, query: Optional[dict] = None, *,
               http: Optional[Callable] = None) -> dict:
    """Keyless GET (clock, schedule...), allowlisted, at most 1 request per second per process."""
    u, _loop = _check_target(base_url, "")
    _check_path(path)
    if not re.fullmatch(GET_ALLOWLIST, path):
        raise GateViolation("GET outside the allowlist")
    q = ""
    if query:
        if any(k not in QUERY_KEYS for k in query):
            raise GateViolation("query key not allowed")
        q = "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    clock = limiter.clock
    with _PUBLIC_LOCK:
        wait = _PUBLIC_LAST[0] + 1.0 - clock.now()
        if wait > 0:
            clock.sleep(wait)
        limiter.take()
        _PUBLIC_LAST[0] = clock.now()
    try:
        status, raw = (http or _urllib_http)("GET", u + path + q, None, {"Accept": "application/json"}, 10.0)
        r = classify(status, raw)
    except GateViolation:
        raise
    except Exception as e:
        r = Response("unknown", 0, "network", {"exc": e.__class__.__name__})
    if r.status != "ok":
        raise BazaarError(r.code or r.status, f"GET {path}: {r.status}", r.http)
    return r.body
