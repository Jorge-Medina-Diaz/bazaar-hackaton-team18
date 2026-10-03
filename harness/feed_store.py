"""Almacén compartido del feed público para el estudio de dealers: varios autores, sin pisarse ni perder datos.

Reglas que lo hacen seguro con git:
- Cada autor escribe SOLO en data/feeds/<autor>/. Nadie edita la carpeta de otro.
- Cada aportación es un fichero NUEVO e inmutable (chunk-<tick_desde>-<tick_hasta>-<huella>.jsonl): nunca se reescribe
  uno existente, así que dos personas nunca tocan el mismo fichero y git no puede generar conflictos de contenido.
- Al leer, los eventos se unen por su `id` del servidor (único). Si dos copias del mismo id difieren, `verify` lo
  reporta como conflicto en vez de quedarse con una en silencio.
- Los ficheros derivados (docs/dealer_params.*) se regeneran desde la unión: si chocan en git, se vuelven a generar.

    python3 -m harness.feed_store add santi logs/feed.jsonl     # aporta lo nuevo de un JSONL (o JSON con "events")
    python3 -m harness.feed_store verify                        # duplicados, conflictos y cobertura por autor
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(REPO, "data", "feeds")
AUTHOR_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


def _events_from(path):
    with open(path) as f:
        text = f.read()
    try:
        d = json.loads(text)
        items = d.get("events", d) if isinstance(d, dict) else d
        rows = items if isinstance(items, list) else []
    except ValueError:
        rows = []
        for line in text.splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return [e for e in rows if isinstance(e, dict) and isinstance(e.get("id"), int) and "payload" in e and "tick" in e]


def chunk_files(author=None):
    pattern = os.path.join(ROOT, author or "*", "chunk-*.jsonl")
    return sorted(glob.glob(pattern))


def load_all():
    """Unión de todos los autores, deduplicada por id, ordenada."""
    seen = {}
    for path in chunk_files():
        with open(path) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                seen.setdefault(e["id"], e)
    return [seen[k] for k in sorted(seen)]


def add(author, sources):
    if not AUTHOR_RE.match(author):
        raise SystemExit(f"autor inválido: {author!r} (minúsculas, números, - o _)")
    known = {e["id"] for e in load_all()}
    new = {}
    for src in sources:
        for e in _events_from(src):
            if e["id"] not in known:
                new[e["id"]] = e
    if not new:
        return None
    rows = [new[k] for k in sorted(new)]
    body = "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in rows)
    digest = hashlib.sha256(body.encode()).hexdigest()[:10]
    ticks = [e["tick"] for e in rows]
    d = os.path.join(ROOT, author)
    os.makedirs(d, exist_ok=True)
    final = os.path.join(d, f"chunk-{min(ticks):05d}-{max(ticks):05d}-{digest}.jsonl")
    if os.path.exists(final):
        return final
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")         # escritura atómica: nunca un chunk a medias
    with os.fdopen(fd, "w") as f:
        f.write(body)
    os.replace(tmp, final)
    return final


def verify():
    by_id, conflicts, per_author = {}, [], {}
    for path in chunk_files():
        author = os.path.basename(os.path.dirname(path))
        with open(path) as f:
            for line in f:
                e = json.loads(line)
                per_author.setdefault(author, set()).add(e["id"])
                prev = by_id.get(e["id"])
                if prev is None:
                    by_id[e["id"]] = (author, e)
                elif json.dumps(prev[1], sort_keys=True) != json.dumps(e, sort_keys=True):
                    conflicts.append((e["id"], prev[0], author))
    ticks = sorted({e["tick"] for _, e in by_id.values()})
    gaps = [(a, b) for a, b in zip(ticks, ticks[1:]) if b - a > 5]
    return dict(events=len(by_id), chunks=len(chunk_files()), authors={a: len(s) for a, s in per_author.items()},
                conflicts=conflicts, tick_range=[ticks[0], ticks[-1]] if ticks else [], gaps=gaps)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "add":
        p = add(sys.argv[2], sys.argv[3:])
        print(p or "nada nuevo")
    elif len(sys.argv) == 2 and sys.argv[1] == "verify":
        r = verify()
        print(json.dumps(r, ensure_ascii=False, indent=1))
        sys.exit(1 if r["conflicts"] else 0)
    else:
        print(__doc__)
