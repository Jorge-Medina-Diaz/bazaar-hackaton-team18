"""One place to build the team's connection: a guarded transport, READ-ONLY by default (M1, spec §2.2).

client(mode="read") reads BAZAAR_URL / BAZAAR_KEY from the environment, or from the repo's .env unless
BAZAAR_NO_DOTENV is set. Read-only tools and the dashboard that call client() get a transport that can only
GET allowlisted routes: any write raises GateViolation (writes belong to the Gate alone).

_load_env(path) loads the repo's .env (KEY=VALUE lines) into os.environ without overriding variables already set.
"""
from __future__ import annotations

import os
from pathlib import Path

from agent.contracts import PROD_URL, Paths
from agent.transport import GuardedTransport, RateLimiter

REPO_ENV = Path(__file__).resolve().parents[1] / ".env"


def _load_env(path: "str | os.PathLike" = REPO_ENV) -> None:
    """KEY=value lines (never committed). Does not override variables already set."""
    if os.environ.get("BAZAAR_NO_DOTENV"):
        return
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                k, sep, v = line.strip().partition("=")
                if sep and not k.startswith("#"):
                    k = k.strip()
                    if k.startswith("export "):
                        k = k[len("export "):].strip()
                    os.environ.setdefault(k, v.strip().strip('"'))


PANEL_RATE = 1.0          # per process: each read-only tool or the dashboard gets 1 req/s; with the runner (RUNNER_RATE) keep the key <= 5/s


def client(mode: str = "read") -> GuardedTransport:
    _load_env()
    key = os.environ.get("BAZAAR_KEY")
    if not key:
        raise RuntimeError("BAZAAR_KEY is not set")
    url = os.environ.get("BAZAAR_URL") or PROD_URL
    return GuardedTransport(url, key, mode=mode, paths=Paths.at(), limiter=RateLimiter(rate=PANEL_RATE, burst=1,
                                                                                         reserve=0))
