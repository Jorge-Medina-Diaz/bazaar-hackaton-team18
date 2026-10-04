"""One-shot local cutoff; requests only our offline trainer to stop after its batch."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import time

from battle_watch import atomic, DEFAULT_OUT


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("La hora debe incluir zona, por ejemplo +02:00")
    return result


def request_if_due(out, deadline, now):
    if now < deadline:
        return False
    # This sentinel belongs exclusively to battle_watch; no game STOP or state files.
    (out / "STOP_TRAINING").touch()
    return True


def run(out, deadline, prepare_delivery=False):
    folder = out / "entrenamiento"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "cutoff.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous = folder / "cutoff.json"
        if previous.exists():
            saved = json.loads(previous.read_text())
            if saved.get("deadline") == deadline.isoformat() and saved.get("requested_at") and saved.get("phase") in {"prepared","failed","stop_requested"}:
                return  # A subsequent login cannot fire this one-shot against a new trainer.
        state = {"deadline": deadline.isoformat(), "pid": os.getpid(), "phase": "scheduled"}
        atomic(folder / "cutoff.json", state)
        while not request_if_due(out, deadline, datetime.now(timezone.utc)):
            time.sleep(1)
        state.update(phase="stop_requested", requested_at=datetime.now(timezone.utc).isoformat())
        atomic(folder / "cutoff.json", state)
        if prepare_delivery:
            end = time.monotonic()+50
            while time.monotonic()<end:
                trainer=json.loads((folder/"status.json").read_text())
                if trainer.get("phase")=="stopped":break
                time.sleep(1)
            try:
                if trainer.get("phase")!="stopped":
                    raise RuntimeError("El entrenador aún no terminó: no congelar una muestra incompleta")
                state["phase"]="preparing"
                atomic(folder / "cutoff.json",state)
                from prepare_battle_delivery import prepare
                dest=prepare(out)
                state.update(phase="prepared",delivery=str(dest))
            except Exception as exc:
                state.update(phase="failed",error=type(exc).__name__+": "+str(exc)[:200])
        state["pid"]=None
        atomic(folder / "cutoff.json",state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--at", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--prepare", action="store_true", help="Verifica y empaqueta entrega local tras detener nuestro entrenador")
    args = parser.parse_args()
    try:
        deadline = timestamp(args.at)
    except ValueError as exc:
        parser.error(str(exc))
    run(args.output, deadline, args.prepare)


if __name__ == "__main__":
    main()
