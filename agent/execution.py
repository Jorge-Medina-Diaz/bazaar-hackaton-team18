"""One writer per team on this computer. The lock holds no credentials."""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import tempfile

try:
    import fcntl

    def _lock(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
except ImportError:  # Windows
    import msvcrt

    def _lock(f):
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(f):
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def team_writer(team):
    if not team:
        raise ValueError('Team identity required')
    name = hashlib.sha256(str(team).encode()).hexdigest()[:20]
    path = Path(tempfile.gettempdir()) / ('bazaar-writer-' + name + '.lock')
    with path.open('a+') as stream:
        try:
            _lock(stream)
        except OSError:  # BlockingIOError (fcntl) and PermissionError (msvcrt) are both OSError
            raise RuntimeError('Another local executor already owns this team') from None
        try:
            yield
        finally:
            _unlock(stream)
