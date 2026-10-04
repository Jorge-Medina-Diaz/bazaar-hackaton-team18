"""Prepare a reviewable local delivery; never commits, pushes, or operates the bot."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

from battle_watch import atomic, DEFAULT_OUT

ROOT = Path(__file__).resolve().parent
FILES = (
    "mini_campo_batalla.py", "battle_watch.py", "schedule_training_cutoff.py", "prepare_battle_delivery.py",
    "harness/battle_data.py", "harness/battle_history.py", "harness/battle_reference.py", "harness/mini_battle.py",
    "tests/test_battle_data.py", "tests/test_battle_history.py", "tests/test_battle_reference.py",
    "tests/test_battle_watch.py", "tests/test_mini_battle.py", "tests/test_training_cutoff.py",
    "tests/test_battle_delivery.py", "docs/mini-campo-batalla.md", "docs/duelos-cierre-2026-10-04.md",
    "docs/prompt-integracion-jorge.md",
)
TESTS = ("tests.test_battle_data", "tests.test_battle_history", "tests.test_battle_reference",
         "tests.test_battle_watch", "tests.test_mini_battle", "tests.test_training_cutoff", "tests.test_battle_delivery")


def summary(state, report):
    lines = ["# Entrega congelada · Mini campo de batalla", "",
             f"Último lote: {state.get('last_completed_at')}",
             f"Lotes: {state.get('completed_batches')} · Escenarios: {state.get('scenarios')} · "
             f"Evaluaciones simuladas: {state.get('evaluations')} · Fallos: {state.get('failures')}", "",
             "## Recomendación", "",
             "La integración inicial añade evaluación offline. No activa estrategias ni modifica memoria.", ""]
    for role in ("buyer", "seller"):
        row = report["simulation"]["roles"][role]
        params = {k:v for k,v in row["selected_params"].items()
                  if k in {"anchor","acc_late","precise","punch","punch_mode"}}
        lines.append(f"- {role}: última selección `{params}`; validación auxiliar: "
                     f"`{report['reference']['roles'][role]['recommendation']}`.")
    lines.extend(["", "La última selección no implica mejora consistente ni autoriza activación.",
                  "Historiales: fixtures y prefijos observados; rivales simulados, sin políticas reales identificadas.",
                  "Consultar prompt-integracion-jorge.md y manifest.json antes de aplicar el parche.",
                  "Los registros privados, claves, bases de datos, resultados JSON crudos y estado del bot no se empaquetan."])
    return "\n".join(lines)+"\n"


def package_files(root, dest, files=FILES):
    if any(name not in FILES for name in files):
        raise ValueError("Archivo fuera de la entrega permitida")
    dest.mkdir(parents=True, exist_ok=True)
    patch, hashes = [], {}
    with zipfile.ZipFile(dest / "codigo-harness.zip", "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name in files:
            path = root / name
            if not path.is_file() or path.is_symlink():
                raise ValueError("Archivo ausente o enlace: "+name)
            data = path.read_bytes()
            hashes[name] = hashlib.sha256(data).hexdigest()
            z.writestr(name, data)
            diff = subprocess.run(["git","diff","--no-index","--","/dev/null",name],
                                  cwd=root,capture_output=True,timeout=10)
            if diff.returncode not in (0,1):
                raise RuntimeError("No se pudo construir el parche")
            patch.append(diff.stdout.decode())
    atomic(dest / "cambios.patch", "".join(patch))
    return hashes


def prepare(out=DEFAULT_OUT, root=ROOT, dest=None):
    from mini_campo_batalla import source_identity
    dest = dest or out / "entrega-final"
    state = json.loads((out/"entrenamiento/status.json").read_text())
    report = json.loads((out/"resultados.json").read_text())
    if state.get("last_error") or report["source"] != source_identity():
        raise RuntimeError("La última práctica no corresponde al código vigente o tiene error")
    verification = subprocess.run([sys.executable,"-m","unittest",*TESTS,"-v"],
                                  cwd=root,capture_output=True,text=True,timeout=45)
    dest.mkdir(parents=True,exist_ok=True)
    atomic(dest/"tests.log",verification.stdout+verification.stderr)
    if verification.returncode:
        raise RuntimeError("Tests fallidos: entrega detenida")
    if subprocess.run(["git","diff","--quiet","HEAD","--","agent","config","bazaar.py","bazaar_sdk.py"],cwd=root).returncode:
        raise RuntimeError("Cambios operativos presentes: requieren revisión separada")
    hashes = package_files(root,dest)
    atomic(dest/"RESUMEN.md",summary(state,report))
    atomic(dest/"PROMPT-JORGE.md",(root/"docs/prompt-integracion-jorge.md").read_text())
    base = subprocess.check_output(["git","merge-base","HEAD","origin/main"],cwd=root,text=True).strip()
    commit = subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()
    atomic(dest/"manifest.json",{"base_commit":base,"source_hash":report["source"]["hash"],
                                 "delivery_commit":commit,
                                 "files_sha256":hashes,"automatic_activation":False,
                                 "kind":"local additive harness delivery; no commit or push"})
    # Check patch syntax and additions in a disposable empty worktree, never in the runner.
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        subprocess.run(["git","init","--quiet",temp],check=True,capture_output=True)
        subprocess.run(["git","-C",temp,"apply","--check",str((dest/"cambios.patch").resolve())],check=True,capture_output=True)
    return dest


if __name__ == "__main__":
    print(prepare())
