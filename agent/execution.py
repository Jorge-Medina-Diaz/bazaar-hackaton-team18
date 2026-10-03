"""M5 execution: the single-writer lock (INV-22). The lock holds no credentials.

writer_lock(paths): fixed path state/writer.lock for every `run` (dry included) and every one-shot `do`.
The file holds {"pid", "argv", "since"} so `status` (and agent.journal's writer check) can read who holds it.
The OS lock is non-blocking: a second holder (another process, or a nested call in this process) gets
RuntimeError immediately (the runner turns it into exit code 3).
On Windows the region locked is one byte far past the JSON text (offset LOCK_OFFSET), so other processes can
still read the PID; with fcntl the whole file is flock'ed.

team_writer(team) is kept for the old code (agent/haggle.py, agent/information.py, tests/test_agent_core.py):
it is now a wrapper of writer_lock(Paths.at()), so the old per-name %TEMP% locks are gone (S-M11).
"""
from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager

from agent.contracts import Paths

LOCK_OFFSET = 1 << 20

try:
    import fcntl

    def _lock(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
except ImportError:  # Windows
    import msvcrt

    def _lock(f):
        f.seek(LOCK_OFFSET)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(f):
        f.seek(LOCK_OFFSET)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def writer_lock(paths: Paths):
    path = paths.lock
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    stream = os.fdopen(fd, "r+b")
    try:
        try:
            _lock(stream)
        except OSError:  # BlockingIOError (fcntl) and PermissionError (msvcrt) are both OSError
            raise RuntimeError(f"Another local executor already owns the writer lock ({path})") from None
        try:
            info = json.dumps({"pid": os.getpid(), "argv": list(sys.argv)[:20], "since": round(time.time(), 3)})
            stream.seek(0)
            stream.truncate(0)
            stream.write(info.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
            yield path
        finally:
            try:
                stream.seek(0)
                stream.truncate(0)
                stream.flush()
            except OSError:
                pass
            _unlock(stream)
    finally:
        stream.close()


@contextmanager
def team_writer(team):
    if not team:
        raise ValueError('Team identity required')
    with writer_lock(Paths.at()):
        yield
