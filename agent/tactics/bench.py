"""L1 bench recorder: a read-only recording of the free stall's book during the Market Test (strategy J8, E11).

What it does: with the starter_broker_key held in memory by `Secrets` (never in the World, journal or disk), it reads
GET /api/broker/book once per state of the book and appends a redacted copy plus a small summary (offer counts,
whether bench offers carry `expires_tick`, what the greedy stall would cross and the surplus it would realise) to a
JSONL file. That data answers knowledge.md Q11 and feeds the own-venue decision (strategy J11, D4).

Hard properties (acceptance "0 writes; key never on disk"):
- This module never writes to the game. It holds no HTTP client: the caller injects `get(path, headers) -> Mapping`,
  a GET-only reader, and this module only ever calls it with BOOK_PATH. No match, no announce, no other route.
- The key only lives in the header dict built inside `read_book` for the duration of the call. Every recorded line is
  passed through `redact` with the key as a secret and is then scanned: if the key (or a bk_/tk- pattern) is still in
  the serialized line, nothing is written and `SecretLeak` is raised (fail closed).
- `plan_greedy` is a copy of starter_broker.bench_plan (archived by M18), made tolerant of malformed offers: an offer
  whose shape is not understood is skipped, never guessed.

NOTES (night build, open issues for the lead)
- Wiring: M1's GuardedTransport forbids broker routes (INV-01, `broker()` raises) and GET_ALLOWLIST has no
  /api/broker/book, so there is no GET-only reader with the X-Broker-Key header yet. Until M1 (or the runner) supplies
  one, nobody can call `read_book` against the server: L1 is inert, which is the fail-closed state.
- The journal (M2) is not used: the recording goes to its own file (suggested: Paths.run_dir / "bench.jsonl"), which
  never feeds the World. Book strings (pseudonyms) are recorded as data, not shown to tactics.
- Not done: public_plan (own venue public offers; we have no venue, D4), a Recorder loop/thread (the runner decides
  when to poll), analysis of the recording after the session.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from agent.contracts import Secrets
from agent.redact import SECRET_VALUE_RE, redact

BOOK_PATH = "/api/broker/book"          # the only route this module ever reads
KEY_HEADER = "X-Broker-Key"

Getter = Callable[[str, Mapping[str, str]], Any]


class SecretLeak(Exception):
    """A secret would have reached the disk: nothing was written."""


# ------------------------------------------------------------------------------------------- planning

def _int(x: Any) -> Optional[int]:
    return x if type(x) is int and x >= 0 else None


def _bench_quote(o: Any) -> Optional[tuple]:
    """(run, side, quote, id) for a well-formed bench offer, else None. side: "ask" (wants cash) | "bid" (gives cash)."""
    if not isinstance(o, Mapping):
        return None
    oid = o.get("id")
    if not isinstance(oid, str) or not oid or "-" not in oid:
        return None
    give, want = o.get("give"), o.get("want")
    if not isinstance(give, Mapping) or not isinstance(want, Mapping):
        return None
    w, g = _int(want.get("cash") or 0), _int(give.get("cash") or 0)
    if w is None or g is None:
        return None
    if w and not g:
        return oid.split("-")[0], "ask", w, oid
    if g and not w:
        return oid.split("-")[0], "bid", g, oid
    return None                          # both or neither: not a shape the stall crosses


def plan_greedy(book: Any) -> list:
    """[(sell id, buy id, price)] exactly as the free stall crosses: in each bench run (the "b12" of "b12-7"), the
    highest bid against the lowest ask while the bid covers it, at the integer midpoint. Stable sort keeps the
    book's order among equal quotes. Malformed offers are skipped."""
    if not isinstance(book, Mapping):
        return []
    offers = book.get("bench_offers") or []
    if not isinstance(offers, (list, tuple)):
        return []
    runs: dict = {}
    for o in offers:
        q = _bench_quote(o)
        if q is None:
            continue
        run, side, quote, oid = q
        asks, bids = runs.setdefault(run, ([], []))
        (asks if side == "ask" else bids).append((quote, oid))
    plan = []
    for asks, bids in runs.values():
        for (ask, sell), (bid, buy) in zip(sorted(asks, key=lambda a: a[0]), sorted(bids, key=lambda b: -b[0])):
            if bid < ask:
                break
            plan.append((sell, buy, (ask + bid) // 2))
    return plan


def summarize(book: Any) -> dict:
    """Small structured summary of a book for the recording (no strings from the book except offer ids)."""
    offers = book.get("bench_offers") if isinstance(book, Mapping) else None
    offers = offers if isinstance(offers, (list, tuple)) else []
    quotes = [q for q in (_bench_quote(o) for o in offers) if q is not None]
    plan = plan_greedy(book)
    by_id = {q[3]: q[2] for q in quotes}
    surplus = sum(by_id[b] - by_id[s] for s, b, _ in plan)
    public = book.get("offers") if isinstance(book, Mapping) else None
    return {
        "bench_offers": len(offers),
        "malformed": len(offers) - len(quotes),
        "asks": sum(1 for q in quotes if q[1] == "ask"),
        "bids": sum(1 for q in quotes if q[1] == "bid"),
        "runs": len({q[0] for q in quotes}),
        "has_expires_tick": sum(1 for o in offers if isinstance(o, Mapping) and "expires_tick" in o),
        "public_offers": len(public) if isinstance(public, (list, tuple)) else 0,
        "greedy_matches": len(plan),
        "greedy_quote_surplus": surplus,      # sum(bid - ask) over greedy pairs, by quote (not by hidden limit)
    }


# ------------------------------------------------------------------------------------------- recording

def _secret_values(secrets: Optional[Secrets]) -> list:
    vals = []
    if secrets is not None and isinstance(secrets.starter_broker_key, str) and secrets.starter_broker_key:
        vals.append(secrets.starter_broker_key)
    env = os.environ.get("BAZAAR_KEY")
    if env:
        vals.append(env)
    return vals


def record(book: Any, path: "str | Path", *, secrets: Optional[Secrets] = None, tick: Optional[int] = None) -> None:
    """Append one line {ts, tick, summary, book} to `path` (JSONL). The book is redacted with the key as a secret;
    if the serialized line still contains a secret, nothing is written and SecretLeak is raised."""
    if not isinstance(book, Mapping):
        raise ValueError("record: book must be a mapping")
    if tick is not None and type(tick) is not int:
        raise ValueError("record: tick must be int or None")
    vals = _secret_values(secrets)
    clean = redact(dict(book), vals)
    row = {"ts": round(time.time(), 3), "tick": tick, "summary": summarize(clean), "book": clean}
    line = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
    if any(v in line for v in vals) or SECRET_VALUE_RE.search(line) or re.search(KEY_HEADER, line, re.I):
        raise SecretLeak("record: a secret survived redaction; nothing written")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_book(get: Getter, secrets: Optional[Secrets]) -> Optional[Mapping]:
    """One GET of BOOK_PATH with the stall key. Fail closed: no key, no reader, an exception or a non-mapping answer
    -> None. The key is only placed in the header of this one call."""
    key = secrets.starter_broker_key if isinstance(secrets, Secrets) else None
    if not isinstance(key, str) or not key or not callable(get):
        return None
    try:
        body = get(BOOK_PATH, {KEY_HEADER: key})
    except Exception:
        return None
    return body if isinstance(body, Mapping) else None


def _state(book: Mapping) -> tuple:
    offers = book.get("bench_offers") or []
    public = book.get("offers") or []
    ids = []
    for o in list(offers if isinstance(offers, (list, tuple)) else []) + \
            list(public if isinstance(public, (list, tuple)) else []):
        if isinstance(o, Mapping):
            ids.append(str(o.get("id")))
    return tuple(ids)


class BenchRecorder:
    """Polls once per call, records only when the book state (tick + offer ids) changed. Read-only by construction."""

    def __init__(self, get: Getter, secrets: Optional[Secrets], path: "str | Path"):
        self._get = get
        self._secrets = secrets
        self.path = Path(path)
        self._seen: Optional[tuple] = None
        self.recorded = 0

    def poll(self, tick: Optional[int] = None) -> bool:
        """True if a new line was recorded. Never raises on a bad read (returns False); SecretLeak propagates."""
        book = read_book(self._get, self._secrets)
        if book is None:
            return False
        state = (tick, _state(book))
        if state == self._seen:
            return False
        record(book, self.path, secrets=self._secrets, tick=tick)
        self._seen = state
        self.recorded += 1
        return True
