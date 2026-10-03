"""Candidatas a denuncia (POST /api/flags) contra los Pícaros: SOLO LECTURA, no denuncia nada.

Nivel A (las únicas que sumaron el sábado, knowledge S-28: 8663, 9460, 9859 = +10 neg_points cada una): un mensaje
de los Pícaros en NUESTRO hilo cuya oferta estructurada da otra carta que la del tema del hilo Y cuyo texto nombra
la carta del tema (por su ref o por una palabra de >= 5 letras del nombre del hilo, `item`; con los hilos del
sábado da justo 8663, 9460 y 9859 y ninguna de las seis de nivel B). El texto ajeno solo se busca, nunca se imprime.
Imprime id del mensaje, hilo, tick, carta del tema y carta dada. Jorge envía como mucho 3, con su OK, con
scratchpad/flag_one.py (excepción manual: `flag` no es un KIND de la Gate).

    python3 flag_candidates.py
"""
from __future__ import annotations

import re
import sys
from typing import Iterable, Mapping

# ya denunciadas el sábado 22:30-22:37 (S-28): A = 8663, 9460, 9859; B (0 puntos) = el resto
FLAGGED = frozenset({8663, 9460, 9859, 8754, 9692, 9700, 9716, 9875, 9891})


def _topic_ref(t: Mapping):
    topic = t.get("topic") or {}
    for side in ("buy", "sell"):
        s = topic.get(side) if isinstance(topic, Mapping) else None
        if isinstance(s, Mapping) and type(s.get("card")) is str:
            return s["card"]
    return None


def _given_refs(o: Mapping) -> set:
    g = o.get("give") or {}
    refs = {x[5:] for x in g.get("types") or () if type(x) is str and x.startswith("card:")}
    refs |= {a.get("ref") for a in g.get("assets") or () if isinstance(a, Mapping) and type(a.get("ref")) is str}
    return refs


def _words(item) -> list:
    """Significant words of the card name (>= 5 letters: 9460 said only "la Puerta" for La Puerta de Alcalá)."""
    if not isinstance(item, str):
        return []
    return [w for w in re.findall(r"\w+", item.lower()) if len(w) >= 5]


def candidates(threads: Iterable[Mapping], done: frozenset = FLAGGED) -> list:
    """-> [(message_id, thread_id, tick, topic_ref, given_refs)] Level A, oldest first, not flagged yet."""
    out = []
    for t in threads or ():
        if not isinstance(t, Mapping) or t.get("with") != "picaros":
            continue
        ref, item = _topic_ref(t), t.get("item")
        if ref is None:
            continue
        names = [ref.lower()] + _words(item)
        for m in t.get("messages") or ():
            o = m.get("offer") if isinstance(m, Mapping) else None
            if m.get("sender") != "picaros" or not isinstance(o, Mapping) or m.get("id") in done:
                continue
            given = _given_refs(o)
            if not given or ref in given:
                continue
            text = m.get("text") if isinstance(m.get("text"), str) else ""
            if any(n in text.lower() for n in names):
                out.append((m.get("id"), t.get("id"), m.get("tick"), ref, sorted(given)))
    return sorted(out, key=lambda c: (c[2] or 0, c[0] or 0))


def main() -> int:
    from agent.client import client
    c = client("read")
    th = c._call("GET", "/api/me/threads")
    threads = th.get("threads", th) if isinstance(th, dict) else th
    full = []
    for t in threads or ():
        if t.get("with") == "picaros" and "messages" not in t and type(t.get("id")) is int:
            r = c._call("GET", f"/api/threads/{t['id']}")
            t = r.get("thread", r)
        full.append(t)
    cands = candidates(full)
    if not cands:
        print("no Level-A candidates")
    for mid, tid, tick, ref, given in cands:
        print(f"message {mid}  thread {tid}  tick {tick}  topic {ref}  offer gives {','.join(given)}")
    print("send at most 3, each with Jorge's OK: python3 <scratchpad>/flag_one.py <message_id> \"<motivo>\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
