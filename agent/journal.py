"""M2 journal: one append-only JSONL write-ahead log for the whole event (docs/harness-spec.md §2.3, §6, INV-15).

Also keeps the old helpers: LOG_DIR and log(stream, **row) (used by the dashboard and the old scripts).

NOTES (M2, night build)
- Row: {seq, ts, tick?, day, mode, kind, prev, **redact(fields)}; prev = sha256 hex of the previous line's bytes
  (without the newline); the first row has prev = GENESIS ("0" * 64). fsync on every kind in FSYNC.
- Extra keyword arguments beyond §2.3 (all with defaults): lock_path (default <root>/state/writer.lock, where
  root = path.parents[2], i.e. the Paths layout logs/run/journal.jsonl) and clock (epoch seconds, for tests).
- writer=True requires the writer lock to be held already (INV-22): the lock file must exist and either name our
  PID (JSON {"pid": n} or text whose first integer is the PID) or, when no PID can be read (Windows region lock),
  be held by someone (we try a non-blocking lock; if we get it, nobody holds it -> JournalError). Tests that open
  a writer journal must write {"pid": os.getpid()} into the lock file (or take execution.writer_lock).
- Modes: "live" on a journal with "test" rows -> JournalError; "test" on a journal with "live" rows ->
  JournalError too (stricter than the spec: a test can never write into the event journal).
- Broken tail: only the LAST line may be broken (unparseable, or a chain/seq mismatch). It is appended (base64)
  to journal.corrupt, the journal is truncated to the last valid line and a "truncated" row is written with
  prev = hash of the last valid line. If the broken bytes look like an intent, its id (if readable) and the
  domains readable from its args are recorded and stay pending / frozen until a "reconciled" row with that id
  (or with truncated=<seq of the truncated row>) resolves them; the Gate writes `reconciled truncated=<seq>
  landed=False` at its first reconcile (a torn intent was never sent, see below). Any earlier broken line ->
  JournalError.
  Known gap: a crash between the truncation and the "truncated" row loses that pending marker (the bytes are
  still in journal.corrupt). A writer intent row is fsynced before the send, so a torn intent was never sent.
- Intent rows: the intent's own kind cannot be passed as kind= (it is write()'s first parameter), so the Gate
  writes it as intent_kind=<kind> (e.g. write("intent", id=iid, intent_kind="accept", args=..., tick=...));
  own_objects() and the torn-intent recovery depend on it.
- result_for(iid): the last resolution row (result | unknown | reconciled | refused | would | deferred); if there
  is none but an intent row exists (sent, outcome not journaled) it returns that intent row (kind "intent"),
  so the Gate's G05 never re-sends after a crash (INV-14).
- own_objects(): ids come from intent args (accept -> offer_id; duel_say -> (duel_id, intent tick, price)) and
  from result.response / reconciled.evidence (tolerant: offer_id | thread_id | msg_id | message_id | id, or a
  nested {"offer"|"thread"|"message": {"id"}}). Any row may also carry an explicit
  own = {"offers": [...], "dealer_threads": [...], "thread_msgs": [...], "duel_msgs": [[did, tick, price]],
  "accepts": [...]}. Responses of the real server for POST were not measured (openapi gives no schema).
- Not done tonight: no rotation / size cap; readers re-scan only the new bytes (incremental), verify_chain()
  re-reads the whole file.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator, Mapping

from agent.contracts import domains_of
from agent.redact import redact

LOG_DIR = os.environ.get("BAZAAR_LOGS", "logs")


def log(stream: str, **row) -> None:
    """Old append-only JSONL logs under logs/<stream>.jsonl (kept for the dashboard and old scripts)."""
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, f"{stream}.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": round(time.time(), 2), **row}, ensure_ascii=False) + "\n")


class JournalError(Exception):
    """The journal cannot be trusted or written: the runner must STOP (exit 2)."""


GENESIS = "0" * 64
MODES = frozenset({"live", "dry", "test"})
RESOLUTION_KINDS = frozenset({"result", "unknown", "reconciled", "refused", "would", "deferred"})
_HEADER = ("seq", "ts", "tick", "day", "mode", "kind", "prev")
_KIND_RE = re.compile(r"[a-z][a-z0-9_]{0,31}")
_TORN_KIND_RE = re.compile(rb'"kind"\s*:\s*"intent"')
_TORN_ID_RE = re.compile(rb'"id"\s*:\s*"([0-9A-Za-z_-]{1,64})"')
_TORN_ARG_RE = re.compile(rb'"(offer_id|thread_id|dealer|duel_id|asset_id|give_asset|ref|want_ref)"\s*:\s*'
                          rb'("([A-Za-z0-9_-]{1,32})"|(\d{1,12}))')


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _json_default(o: Any) -> Any:
    if isinstance(o, (set, frozenset)):
        try:
            return sorted(o)
        except TypeError:
            return sorted(o, key=repr)
    if isinstance(o, Path):
        return str(o)
    return repr(o)


def _int(x: Any) -> int | None:
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, str) and x.isdigit():
        return int(x)
    return None


def _ids_from(resp: Any, keys: tuple, nested: str) -> set:
    out = set()
    if not isinstance(resp, Mapping):
        return out
    for k in keys:
        v = _int(resp.get(k))
        if v is not None:
            out.add(v)
            return out
    sub = resp.get(nested)
    if isinstance(sub, Mapping):
        v = _int(sub.get("id"))
        if v is not None:
            out.add(v)
    return out


def _duel_key(x: Any) -> tuple | None:
    if isinstance(x, Mapping):
        x = (x.get("did", x.get("duel_id")), x.get("tick"), x.get("price"))
    if isinstance(x, (list, tuple)) and len(x) >= 3:
        k = tuple(_int(v) if not isinstance(v, int) else v for v in x[:3])
        if all(isinstance(v, int) and not isinstance(v, bool) for v in k):
            return k
    return None


def _lock_pid(text: str) -> int | None:
    try:
        d = json.loads(text)
        if isinstance(d, Mapping):
            return _int(d.get("pid"))
        if isinstance(d, int) and not isinstance(d, bool):
            return d
    except ValueError:
        pass
    m = re.search(r"\d+", text)
    return int(m.group(0)) if m else None


def _lock_is_free(lock: Path) -> bool:
    """True if we can take the lock ourselves right now (then nobody holds it). Released immediately."""
    try:
        with lock.open("a+") as f:
            try:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except ImportError:
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            return True
    except OSError:
        return False


class Journal:
    FSYNC = frozenset({"intent", "result", "unknown", "reconciled", "accepted_unsettled", "stop", "pause",
                       "resume", "arm", "param", "baseline", "round_reset", "cmd"})

    def __init__(self, path: Path, *, mode: str, writer: bool = True, lock_path: Path | None = None,
                 clock: Callable[[], float] = time.time):
        if mode not in MODES:
            raise JournalError(f"bad mode {mode!r}")
        self.path = Path(path)
        self.mode = mode
        self.writer = bool(writer)
        self.clock = clock
        self.corrupt_path = self.path.with_name(self.path.stem + ".corrupt")
        self._failed: str | None = None
        self._reset_index()
        if self.writer:
            self._check_lock(Path(lock_path) if lock_path is not None
                             else self.path.parent.parent.parent / "state" / "writer.lock")
            self._open_writer()
        else:
            self._refresh()
        self._check_mode()

    # ------------------------------------------------------------------ index

    def _reset_index(self) -> None:
        self._offset = 0                 # bytes of the file already ingested (complete lines only)
        self._last_seq = 0
        self._last_hash = GENESIS
        self._chain_ok = True
        self._has = {"live": False, "dry": False, "test": False}
        self._intents: dict[str, dict] = {}          # id -> {id, kind, args, tick, seq}
        self._resolved: dict[str, dict] = {}          # id -> last resolution row (compact for would/refused)
        self._closed: set[str] = set()                # ids with result or reconciled
        self._unknown: dict[str, frozenset] = {}      # id -> domains of an unknown outcome
        self._reconciled: set[str] = set()
        self._unsettled: dict[str, dict] = {}         # id -> accepted_unsettled row
        self._settled: set[str] = set()
        self._torn: list[dict] = []                   # truncated rows that may hide an intent
        self._torn_done: set[int] = set()             # seq of truncated rows resolved by reconciled
        self._own = {"offers": set(), "dealer_threads": set(), "thread_msgs": set(), "duel_msgs": set(),
                     "accepts": set()}

    def _ingest(self, row: Mapping) -> None:
        mode = row.get("mode")
        if mode in self._has:
            self._has[mode] = True
        kind = row.get("kind")
        iid = row.get("id")
        iid = iid if isinstance(iid, str) else None
        if kind == "intent" and iid:
            args = row.get("args") if isinstance(row.get("args"), Mapping) else {}
            ik = row.get("intent_kind") if isinstance(row.get("intent_kind"), str) else None
            self._intents[iid] = {"id": iid, "kind": ik, "args": dict(args), "tick": row.get("tick"),
                                  "seq": row.get("seq"), "row": dict(row)}
            if ik == "accept" and _int(args.get("offer_id")) is not None:
                self._own["accepts"].add(_int(args.get("offer_id")))
            if ik == "duel_say":
                k = _duel_key((args.get("duel_id"), row.get("tick"), args.get("price")))
                if k:
                    self._own["duel_msgs"].add(k)
        elif kind in RESOLUTION_KINDS and iid:
            if kind in ("result", "unknown", "reconciled"):
                self._resolved[iid] = dict(row)
            else:
                self._resolved[iid] = {"seq": row.get("seq"), "kind": kind, "id": iid, "code": row.get("code")}
            if kind in ("result", "reconciled"):
                self._closed.add(iid)
            if kind == "unknown":
                doms = row.get("domains")
                if isinstance(doms, (list, tuple, set, frozenset)):
                    self._unknown[iid] = frozenset(str(d) for d in doms)
                else:
                    self._unknown[iid] = frozenset()
            if kind == "reconciled":
                self._reconciled.add(iid)
                self._settled.add(iid)
            if kind in ("result", "reconciled"):
                self._own_from_response(iid, row.get("response") if kind == "result" else row.get("evidence"))
        elif kind == "accepted_unsettled" and iid:
            self._unsettled[iid] = dict(row)
        elif kind == "settlement":
            ids = row.get("ids")
            if isinstance(ids, (list, tuple)):
                self._settled.update(str(i) for i in ids)
        elif kind == "truncated" and (row.get("maybe_intent") or row.get("domains")):
            self._torn.append(dict(row))
        if kind == "reconciled" and _int(row.get("truncated")) is not None:
            self._torn_done.add(_int(row.get("truncated")))
        own = row.get("own")
        if isinstance(own, Mapping):
            for key in ("offers", "dealer_threads", "thread_msgs", "accepts"):
                for v in own.get(key) or ():
                    if _int(v) is not None:
                        self._own[key].add(_int(v))
            for v in own.get("duel_msgs") or ():
                k = _duel_key(v)
                if k:
                    self._own["duel_msgs"].add(k)

    def _own_from_response(self, iid: str, resp: Any) -> None:
        it = self._intents.get(iid)
        ik = it["kind"] if it else None
        if ik == "list_offer":
            self._own["offers"] |= _ids_from(resp, ("offer_id", "id"), "offer")
        elif ik == "open_thread":
            self._own["dealer_threads"] |= _ids_from(resp, ("thread_id", "id"), "thread")
        elif ik == "say":
            self._own["thread_msgs"] |= _ids_from(resp, ("msg_id", "message_id", "id"), "message")

    # ------------------------------------------------------------------ open / recover

    def _check_lock(self, lock: Path) -> None:
        if not lock.exists():
            raise JournalError(f"writer lock not held: {lock} missing")
        try:
            text = lock.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""                   # region-locked by its holder (Windows): fall through
        pid = _lock_pid(text) if text.strip() else None
        if pid is not None:
            if pid != os.getpid():
                raise JournalError(f"writer lock held by pid {pid}, not {os.getpid()}")
            return
        if _lock_is_free(lock):
            raise JournalError(f"writer lock not held: {lock} is free")

    def _open_writer(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = self.path.read_bytes() if self.path.exists() else b""
        except OSError as e:
            raise JournalError(f"cannot read journal: {e}") from e
        lines = data.split(b"\n")
        tail = lines.pop()                 # b"" when the file ends with a newline
        complete = lines
        if tail:                           # no newline at the end: the last line is the candidate
            complete = lines + [tail]
        good_end = 0                       # byte offset just after the last valid line (incl. newline)
        broken: bytes | None = None
        prev, last_seq = GENESIS, 0
        rows = []
        for i, raw in enumerate(complete):
            is_last = i == len(complete) - 1
            row = self._parse_link(raw, prev, last_seq)
            if row is None:
                if not is_last:
                    raise JournalError(f"journal chain broken at line {i + 1} (not the tail)")
                broken = data[good_end:]
                break
            rows.append(row)
            prev, last_seq = _sha(raw), row["seq"]
            good_end += len(raw) + 1
        need_newline = broken is None and bool(tail)
        for row in rows:
            self._ingest(row)
        self._last_seq, self._last_hash = last_seq, prev
        if need_newline:                   # a valid last line whose newline did not reach the disk
            try:
                with open(self.path, "ab") as f:
                    f.write(b"\n")
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                raise JournalError(f"cannot complete last line: {e}") from e
        elif broken is not None:
            self._recover(broken, good_end)
        self._offset = self.path.stat().st_size if self.path.exists() else 0

    @staticmethod
    def _parse_link(raw: bytes, prev: str, last_seq: int) -> dict | None:
        try:
            row = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(row, dict) or row.get("prev") != prev:
            return None
        seq = row.get("seq")
        if type(seq) is not int or seq != last_seq + 1:
            return None
        return row

    def _recover(self, broken: bytes, good_end: int) -> None:
        maybe = None
        doms: list[str] = []
        if _TORN_KIND_RE.search(broken):
            m = _TORN_ID_RE.search(broken)
            maybe = m.group(1).decode() if m else "?"
            for k, _, s, n in _TORN_ARG_RE.findall(broken):
                prefix = dict((("offer_id", "offer"), ("thread_id", "thread"), ("dealer", "dealer"),
                               ("duel_id", "duel"), ("asset_id", "asset"), ("give_asset", "asset"),
                               ("ref", "ref"), ("want_ref", "ref")))[k.decode()]
                doms.append(f"{prefix}:{(s or n).decode()}")
        try:
            rec = json.dumps({"ts": round(self.clock(), 3), "journal": str(self.path), "offset": good_end,
                              "bytes": len(broken), "sha256": _sha(broken),
                              "b64": base64.b64encode(broken).decode("ascii")}) + "\n"
            with open(self.corrupt_path, "ab") as f:
                f.write(rec.encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
            with open(self.path, "r+b") as f:
                f.truncate(good_end)
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            raise JournalError(f"cannot recover broken tail: {e}") from e
        self.write("truncated", offset=good_end, bytes=len(broken), sha256=_sha(broken),
                   corrupt=str(self.corrupt_path), maybe_intent=maybe, domains=sorted(set(doms)))

    def _check_mode(self) -> None:
        if self.mode == "live" and self._has["test"]:
            raise JournalError("journal has test rows: refusing live mode")
        if self.mode == "test" and self._has["live"]:
            raise JournalError("journal has live rows: refusing test mode")

    def _refresh(self) -> None:
        """Reader: ingest complete lines appended since the last call; a partial last line is left for later."""
        if self.writer:
            return
        try:
            with open(self.path, "rb") as f:
                f.seek(self._offset)
                data = f.read()
        except FileNotFoundError:
            return
        except OSError as e:
            raise JournalError(f"cannot read journal: {e}") from e
        end = data.rfind(b"\n")
        if end < 0:
            return
        for raw in data[:end].split(b"\n"):
            row = self._parse_link(raw, self._last_hash, self._last_seq)
            if row is None:
                self._chain_ok = False
                try:
                    row = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    row = None
                if not isinstance(row, dict):
                    self._last_hash = _sha(raw)
                    continue
            self._ingest(row)
            self._last_hash = _sha(raw)
            if type(row.get("seq")) is int:
                self._last_seq = row["seq"]
        self._offset += end + 1

    # ------------------------------------------------------------------ write

    def write(self, kind: str, **fields) -> int:
        if not self.writer:
            raise JournalError("read-only journal")
        if self._failed:
            raise JournalError(f"journal failed earlier: {self._failed}")
        if not isinstance(kind, str) or not _KIND_RE.fullmatch(kind):
            raise JournalError(f"bad row kind {kind!r}")
        for k in ("seq", "ts", "prev"):
            if k in fields:
                raise JournalError(f"reserved field {k!r}")
        if "mode" in fields and fields.pop("mode") != self.mode:
            raise JournalError("row mode differs from the journal mode")
        now = self.clock()
        tick = fields.pop("tick", None)
        day = fields.pop("day", None) or time.strftime("%Y-%m-%d", time.localtime(now))
        seq = self._last_seq + 1
        row: dict = {"seq": seq, "ts": round(now, 3)}
        if tick is not None:
            row["tick"] = tick
        row.update({"day": day, "mode": self.mode, "kind": kind, "prev": self._last_hash})
        body = redact(fields)
        for k, v in body.items():
            if k not in row:
                row[k] = v
        try:
            line = json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=_json_default).encode("utf-8")
        except (TypeError, ValueError) as e:
            raise JournalError(f"row not serializable: {e}") from e
        try:
            with open(self.path, "ab") as f:
                f.write(line + b"\n")
                f.flush()
                if kind in self.FSYNC:
                    os.fsync(f.fileno())
        except OSError as e:
            self._failed = str(e)
            raise JournalError(f"journal write failed: {e}") from e
        self._last_seq, self._last_hash = seq, _sha(line)
        self._offset += len(line) + 1
        self._has[self.mode] = True
        self._ingest(json.loads(line.decode("utf-8")))
        return seq

    # ------------------------------------------------------------------ read

    def rows(self, kinds: set[str] | None = None) -> Iterator[dict]:
        """Every parseable complete row in file order (a partial last line is skipped)."""
        try:
            with open(self.path, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            return
        except OSError as e:
            raise JournalError(f"cannot read journal: {e}") from e
        end = data.rfind(b"\n")
        if end < 0:
            return
        # M17 speed-up (the runner reads the journal several times per tick): an index (kind, raw line) of the
        # complete lines already seen is kept while the file only grows; only the new tail is parsed. Matching
        # rows are parsed again from their bytes, so callers always get fresh dicts (no shared mutable state).
        head = data[:end + 1]
        cached = getattr(self, "_rows_bytes", b"")
        if cached and len(head) >= len(cached) and head[:len(cached)] == cached:
            index = list(self._rows_index)
            new = head[len(cached):]
        else:
            index = []
            new = head
        for raw in new[:-1].split(b"\n") if new else ():
            try:
                row = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(row, dict):
                index.append((row.get("kind"), raw))
        self._rows_bytes, self._rows_index = head, index
        for k, raw in index:
            if kinds is None or k in kinds:
                try:
                    yield json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue

    def result_for(self, intent_id: str) -> dict | None:
        self._refresh()
        r = self._resolved.get(intent_id)
        if r is not None:
            return dict(r)
        it = self._intents.get(intent_id)
        if it is not None:
            return dict(it["row"])         # sent (or about to be), outcome never journaled: never re-send
        for t in self._torn:
            if t.get("maybe_intent") == intent_id:
                return dict(t)
        return None

    def pending(self) -> list[dict]:
        self._refresh()
        out = []
        for iid, it in self._intents.items():
            if iid not in self._closed:
                row = dict(it["row"])
                row["pending"] = "unknown" if iid in self._unknown else "no_result"
                out.append(row)
        for iid, row in self._unsettled.items():
            if iid not in self._settled:
                r = dict(row)
                r["pending"] = "accepted_unsettled"
                out.append(r)
        for t in self._torn:
            if not self._torn_resolved(t):
                r = dict(t)
                r["pending"] = "truncated"
                out.append(r)
        return out

    def _torn_resolved(self, t: Mapping) -> bool:
        return t.get("seq") in self._torn_done or t.get("maybe_intent") in self._reconciled

    def unknown_domains(self) -> set[str]:
        self._refresh()
        out: set[str] = set()
        for iid, doms in self._unknown.items():
            if iid in self._reconciled:
                continue
            out |= set(doms) or self._domains_of_intent(iid)
        for iid, it in self._intents.items():            # intent with no outcome at all (crash mid-send)
            if iid not in self._resolved:
                out |= self._domains_of_intent(iid)
        for t in self._torn:
            if not self._torn_resolved(t):
                out |= {str(d) for d in t.get("domains") or ()}
        return out

    def _domains_of_intent(self, iid: str) -> set[str]:
        it = self._intents.get(iid)
        if not it:
            return set()
        try:
            return set(domains_of(SimpleNamespace(args=it["args"])))
        except Exception:                  # noqa: BLE001 - odd args must not hide the freeze
            return {f"intent:{iid}"}

    def own_objects(self, baseline: Mapping) -> dict[str, set]:
        self._refresh()
        out = {k: set(v) for k, v in self._own.items()}
        base = baseline if isinstance(baseline, Mapping) else {}
        for key in ("offers", "dealer_threads", "thread_msgs", "accepts"):
            for v in base.get(key) or ():         # a dict {id: band} iterates its ids
                if _int(v) is not None:
                    out[key].add(_int(v))
        for v in base.get("duel_msgs") or ():
            k = _duel_key(v)
            if k:
                out["duel_msgs"].add(k)
        return out

    def verify_chain(self) -> bool:
        """Re-read the whole file: every complete line parses, seq is 1,2,3,... and prev links to the line before.

        A writer's file must end with a newline; a reader tolerates one partial last line (a write in flight).
        """
        try:
            data = self.path.read_bytes() if self.path.exists() else b""
        except OSError:
            return False
        lines = data.split(b"\n")
        tail = lines.pop()
        if tail and self.writer:
            return False
        prev, seq = GENESIS, 0
        for raw in lines:
            row = self._parse_link(raw, prev, seq)
            if row is None:
                return False
            prev, seq = _sha(raw), row["seq"]
        return True
