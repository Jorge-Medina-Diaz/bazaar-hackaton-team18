"""M0 redaction of secrets (INV-18).

redact(obj, secrets=()) returns a redacted deep copy:
- mapping keys containing key|token|secret|password (case-insensitive) are dropped;
- substrings matching (tk|bk)[-_][A-Za-z0-9-]{6,} become "<redacted>";
- strings equal to a value of `secrets` or of os.environ["BAZAAR_KEY"] become "<redacted>"
  (and, stricter than the spec, any occurrence of such a value of length >= 8 inside a longer string).
Mappings come back as dict, lists as list, tuples as tuple, sets as set/frozenset, dataclasses as dict.
bytes are decoded leniently and treated as strings. Other scalars are returned unchanged.
"""
from __future__ import annotations

import dataclasses
import os
import re
from typing import Any, Iterable, Mapping

REDACTED = "<redacted>"
SECRET_KEY_RE = re.compile(r"key|token|secret|password", re.IGNORECASE)
SECRET_VALUE_RE = re.compile(r"(tk|bk)[-_][A-Za-z0-9-]{6,}")
_MIN_EMBEDDED = 8


def _secret_values(secrets: Iterable[str]) -> list:
    vals = [s for s in (secrets or ()) if isinstance(s, str) and s]
    env = os.environ.get("BAZAAR_KEY")
    if env:
        vals.append(env)
    # longest first so an embedded long secret is replaced before a shorter prefix of it
    return sorted(set(vals), key=len, reverse=True)


def _redact_str(s: str, vals: list) -> str:
    if s in vals:
        return REDACTED
    for v in vals:
        if len(v) >= _MIN_EMBEDDED and v in s:
            s = s.replace(v, REDACTED)
    return SECRET_VALUE_RE.sub(REDACTED, s)


def _walk(obj: Any, vals: list, depth: int) -> Any:
    if depth > 200:
        return REDACTED                       # fail closed on absurd nesting
    if isinstance(obj, str):
        return _redact_str(obj, vals)
    if isinstance(obj, (bytes, bytearray)):
        return _redact_str(bytes(obj).decode("utf-8", "replace"), vals)
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        obj = {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}
    if isinstance(obj, Mapping):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and SECRET_KEY_RE.search(k):
                continue
            nk = _redact_str(k, vals) if isinstance(k, str) else k
            out[nk] = _walk(v, vals, depth + 1)
        return out
    if isinstance(obj, tuple):
        return tuple(_walk(x, vals, depth + 1) for x in obj)
    if isinstance(obj, list):
        return [_walk(x, vals, depth + 1) for x in obj]
    if isinstance(obj, frozenset):
        return frozenset(_walk(x, vals, depth + 1) for x in obj)
    if isinstance(obj, set):
        return {_walk(x, vals, depth + 1) for x in obj}
    # unknown object: its repr could carry a secret, so redact the repr text
    return _redact_str(repr(obj), vals)


def redact(obj: Any, secrets: Iterable[str] = ()) -> Any:
    return _walk(obj, _secret_values(secrets), 0)
