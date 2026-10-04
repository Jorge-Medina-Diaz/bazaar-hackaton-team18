"""Entrenamiento continuo offline; lotes aislados y progreso conservado al reiniciar."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / "runs/mini-campo-batalla"


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def read_state(out):
    path = out / "entrenamiento/status.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"version": 1, "next_batch": 1, "completed_batches": 0, "scenarios": 0,
            "evaluations": 0, "failures": 0, "roles": {}, "phase": "not_started"}


def seeds(batch, base_seed):
    # Cada lote ocupa un bloque separado: test +50k, seller +100k.
    return base_seed + batch * 1000000


def accumulate(state, report):
    sim = report["simulation"]
    source = report.get("source", {}).get("hash", "legacy")
    if state.get("source_hash") != source:
        if state.get("roles"):
            prior = state.setdefault("prior_versions", {})
            prior[state.get("source_hash", "legacy")] = state["roles"]
            while len(prior) > 8:
                del prior[next(iter(prior))]
        state.update(source_hash=source, roles={}, version_scenarios=0, version_evaluations=0)
    state["completed_batches"] += 1
    state["scenarios"] += sim["distinct_scenarios"]
    state["evaluations"] += sim["executed_episodes"]
    state["failures"] += sim["failures"]
    state["version_scenarios"] += sim["distinct_scenarios"]
    state["version_evaluations"] += sim["executed_episodes"]
    for role, row in sim["roles"].items():
        stats = state["roles"].setdefault(role, {"training": {}, "validation": {}})
        for candidate in row["train_ranking"]:
            key = json.dumps(candidate["params"], sort_keys=True)
            acc = stats["training"].setdefault(key, {"params": candidate["params"], "n": 0,
                                                     "sum_score": 0, "failures": 0, "group_sums": {}})
            n = candidate["episodes"]
            acc["n"] += n
            acc["sum_score"] += candidate.get("selection_score", candidate["mean_score"]) * n
            acc["failures"] += candidate["failures"]
            acc.setdefault("group_sums", {})
            for group, gain in candidate.get("training_group_gains", {}).items():
                acc["group_sums"][group] = acc["group_sums"].get(group, 0) + gain*n
        chosen = json.dumps(row["selected_params"], sort_keys=True)
        acc = stats["validation"].setdefault(chosen, {"n": 0, "sum_gain": 0, "failures": 0})
        n = row["validation_selected"]["episodes"]
        acc["n"] += n
        acc["sum_gain"] += row["validation"]["paired_mean_gain"] * n
        acc["failures"] += row["validation_selected"]["failures"]
        # Solo entrenamiento elige el líder acumulado; validación no lo cambia.
        leader = min(stats["training"].items(), key=lambda item:
                     (item[1]["failures"],
                      sum(value/item[1]["n"] < -1e-12 for value in item[1].get("group_sums",{}).values()),
                      -item[1]["sum_score"] / item[1]["n"]))
        stats["leader_from_training"] = leader[1]["params"]
        validation = stats["validation"].get(leader[0])
        stats["leader_validation"] = ({"n": validation["n"], "mean_paired_gain":
                                        validation["sum_gain"] / validation["n"],
                                        "failures": validation["failures"]} if validation else None)
    return state


def prefix(state):
    lines = ["# Entrenamiento continuo · Mini campo de batalla", "",
             f"Último lote completado: {state.get('last_completed_at')}", "",
             f"**{state['completed_batches']} lotes · {state['scenarios']} escenarios nuevos · "
             f"{state['evaluations']} evaluaciones · {state['failures']} fallos.**", "",
             f"Compra y venta se practican en paralelo; un lote cada {state.get('interval_seconds',60)} s, sin solaparlos.",
             "Estado vivo y PID: `entrenamiento/status.json`. Son simulaciones locales, no tratos reales.", "",
             f"Versión actual: `{state.get('source_hash','sin identificar')[:16]}` · "
             f"{state.get('version_scenarios',0)} escenarios / {state.get('version_evaluations',0)} evaluaciones. "
             "Los resultados de versiones distintas se conservan separados.", "",
             "| Lado | Líder por entrenamiento acumulado | Ganancia en validaciones disponibles |",
             "|---|---|---:|"]
    for role, label in (("buyer", "Compra"), ("seller", "Venta")):
        r = state["roles"].get(role, {})
        v = r.get("leader_validation") or {}
        lines.append(f"| {label} | `{r.get('leader_from_training')}` | {v.get('mean_paired_gain', 'sin validación')} |")
    lines.extend(["", "La validación agregada solo incluye lotes donde ese parámetro fue elegido con "
                  "entrenamiento. No compara retrospectivamente todos los candidatos con el test. "
                  "No se modifica la configuración del agente operativo.", "", "---", ""])
    return "\n".join(lines)


@contextmanager
def single_writer(out):
    path = out / "entrenamiento/writer.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Ya hay un entrenador activo") from None
        yield


def run(out, feed, practices, every, base_seed):
    out.mkdir(parents=True, exist_ok=True)
    stop = out / "STOP_TRAINING"
    status = out / "entrenamiento/status.json"
    workspace = out / "entrenamiento/lote"
    interrupted = False
    def shutdown(*_):
        nonlocal interrupted
        interrupted = True
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    with single_writer(out):
        state = read_state(out)
        print("Entrenador offline iniciado; progreso en " + str(status), flush=True)
        while not interrupted and not stop.exists():
            started = time.monotonic()
            batch = state["next_batch"]
            seed = seeds(batch, base_seed)
            state.update(next_batch=batch + 1, active_batch=batch, active_seed=seed,
                         pid=os.getpid(), phase="training", last_error=None,
                         interval_seconds=every, practices_per_role_split=practices)
            atomic(status, state)  # Reserva semilla antes del proceso: nunca reutilizar un lote tras caída.
            cmd = [sys.executable, str(ROOT / "mini_campo_batalla.py"), "--practices", str(practices),
                   "--seed", str(seed), "--output", str(workspace)]
            if feed and feed.is_file():
                cmd.extend(["--feed", str(feed)])
            child = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                     text=True, start_new_session=True,
                                     env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", BAZAAR_NO_DOTENV="1"))
            try:
                _, error = child.communicate(timeout=45)
                if child.returncode:
                    raise RuntimeError("Lote fallido; no se cuentan ni publican resultados")
                report = json.loads((workspace / "resultados.json").read_text(encoding="utf-8"))
                if report["simulation"]["failures"]:
                    raise RuntimeError("Lote con fallos de seguridad/comprobación; conserva informe anterior")
                accumulate(state, report)
                state.update(phase="waiting", last_completed_at=datetime.now(timezone.utc).isoformat(),
                             last_completed_batch=batch)
                atomic(out / "resultados.json", report)
                atomic(out / "ULTIMO.md", prefix(state) + (workspace / "ULTIMO.md").read_text(encoding="utf-8"))
            except Exception as exc:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.communicate(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.communicate()
                state.update(phase="retry_wait", last_error=str(exc)[:180])
            atomic(status, state)
            while not interrupted and not stop.exists() and time.monotonic() - started < every:
                time.sleep(1)
        state.update(phase="stopped", pid=None)
        atomic(status, state)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "status", "stop"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--feed", type=Path)
    parser.add_argument("--practices", type=int, default=1000)
    parser.add_argument("--every", type=int, default=60)
    parser.add_argument("--seed", type=int, default=18)
    args = parser.parse_args(argv)
    if args.command == "status":
        state = read_state(args.output)
        pid = state.get("pid")
        try:
            os.kill(pid, 0) if pid else None
            state["process_alive"] = bool(pid)
        except (OSError, TypeError):
            state["process_alive"] = False
        print(json.dumps(state, ensure_ascii=False, indent=2))
    elif args.command == "stop":
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "STOP_TRAINING").touch()
        print("Parada solicitada solo al entrenador offline")
    else:
        if not 10 <= args.practices <= 2000 or args.every < 15:
            parser.error("practices 10..2000; every >=15")
        run(args.output, args.feed, args.practices, args.every, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
