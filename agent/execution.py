"""One writer per team on this computer. The lock holds no credentials."""
from contextlib import contextmanager
import fcntl
import hashlib
from pathlib import Path
import tempfile


@contextmanager
def team_writer(team):
    if not team:
        raise ValueError('Team identity required')
    name = hashlib.sha256(str(team).encode()).hexdigest()[:20]
    path = Path(tempfile.gettempdir()) / ('bazaar-writer-' + name + '.lock')
    with path.open('a') as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another local executor already owns this team') from None
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
