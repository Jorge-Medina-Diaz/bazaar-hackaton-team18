"""Práctica offline para la final; nunca negocia ni carga claves del equipo."""
from __future__ import annotations

import argparse
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

from harness.battle_data import load_evidence
from harness.mini_battle import run_experiment
from harness.battle_reference import crosscheck
from harness.battle_history import historical_states
from harness.battle_data import _read, FIXTURE


def source_identity() -> dict:
    root = Path(__file__).resolve().parent
    files = ("agent/tactics/duels.py", "agent/world.py", "config/plan.json", "harness/mini_battle.py",
             "harness/battle_reference.py", "harness/battle_history.py", "harness/battle_data.py",
             "run_duel_eval.py", "tests/test_duels.py", "battle_watch.py")
    digest = hashlib.sha256()
    for name in files:
        digest.update(name.encode())
        digest.update((root / name).read_bytes())
    return {"hash": digest.hexdigest(), "files": list(files)}


def pipeline_probe() -> dict:
    """Comprueba el camino World -> táctica con un duelo inventado, sin red."""
    from agent.world import parse_duel
    from agent.tactics import duels
    raw = dict(duel=1, status="live", role="buyer", your_limit=100,
               deadline_tick=116, decay_per_round=.1, issues=["price", "days"],
               messages=[], rival_offer=None, your_offer=None, your_days_weight=2.0,
               days_meaning="delivery days", rounds=0)
    parsed = parse_duel(raw)
    action = duels.decide(duels.view(parsed, 100), {"days_sign": -1})
    direct = duels.decide(duels.view(raw, 100), {"days_sign": -1})
    return {"synthetic_probe": True, "through_world": action[0],
            "direct_policy": direct[0], "blocked_by_projection": action[0] == "wait" and direct[0] == "say",
            "trace": [
                {"stage": "input", "issues": raw["issues"], "days_weight": raw["your_days_weight"],
                 "meaning_present": bool(raw["days_meaning"]), "tick": 100, "deadline": 116},
                {"stage": "world", "meaning_present": bool(parsed.get("days_meaning")),
                 "meaning_known": duels.view(parsed, 100).days_meaning_known},
                {"stage": "decision_after_world", "action": list(action)},
                {"stage": "direct_control", "action": list(direct)}],
            "runtime_of_operator_verified": False}


def markdown(report: dict) -> str:
    sim, data, probe = report["simulation"], report["evidence"], report["pipeline"]
    lines = ["# Mini campo de batalla · última práctica", "", f"Generado: {report['generated_at']}", "",
             "## Primero: que el agente pueda jugar", "",
             ("**El código de esta rama pierde `days_meaning` al construir World.** La prueba inventada "
              "propone una oferta al llamar a la táctica directamente, pero espera al pasar por World. "
              "Confirmar que el operador adoptó la corrección antes de cambiar estrategia."
              if probe["blocked_by_projection"] else
              "La prueba del camino World → táctica no reproduce el bloqueo de días en este checkout."),
             "No se ha inspeccionado ni modificado el proceso de Jorge.", "",
             "## Qué se ha practicado", "",
             "Compras y ventas en procesos paralelos. Selección con escenarios de entrenamiento; "
             "evaluación posterior con semillas distintas y los mismos casos para cada estrategia.", "",
             "Entrenamiento reforzado: los seis modelos iniciales más los tres de main. Compara ganancias "
             "normalizadas por límite propio, da igual peso a cada tipo y penaliza perder en un grupo de "
             "rivales o días. Siempre incluye el plan actual como alternativa segura. No demuestra "
             "que ningún rival real vaya a comportarse igual.", "",
             "La fórmula de precio es excedente firmado × (1 − decay)^min(mensajes nuestros, mensajes rivales). "
             "Sin acuerdo: 0. Esperar no añade decay. Para la final: 12 ticks, decay 0,10, precio y días.", "",
             "El efecto de los días se modela conservadoramente; su conversión exacta a puntos no está validada. "
             "Las respuestas de rivales son simuladas. Un resultado mejor aquí no garantiza puntos reales.", "",
             "## Resultados por lado", ""]
    roles = sim.get("roles", {})
    for role, title in (("buyer", "Compra"), ("seller", "Venta")):
        r = roles.get(role, {})
        b, c = r.get("validation_baseline", {}), r.get("validation_selected", {})
        lines.extend([f"### {title}", "",
                      f"Baseline: `{r.get('baseline_params')}`. Selección por entrenamiento: `{r.get('selected_params')}`.", "",
                      "| Validación simulada | Baseline | Selección |", "|---|---:|---:|"])
        for key, label in (("mean_score", "Excedente medio con modelo de días"),
                           ("mean_price_score", "Componente de precio medio"),
                           ("deals", "Acuerdos"), ("episodes", "Prácticas"),
                           ("failures", "Fallos de comprobación")):
            lines.append(f"| {label} | {b.get(key)} | {c.get(key)} |")
        lines.extend(["", f"Recomendación: `{r.get('recommendation')}`. Ganancia media pareada: "
                      f"{r.get('validation', {}).get('paired_mean_gain')}; error estándar: "
                      f"{r.get('validation', {}).get('paired_gain_standard_error')}.", "",
                      "| Rival simulado | Media baseline | Media selección |", "|---|---:|---:|"])
        groups = r.get("per_opponent", {})
        for name, stats in groups.get("baseline", {}).items():
            chosen = groups.get("chosen", {}).get(name, {})
            lines.append(f"| {name} | {stats.get('mean_score')} | {chosen.get('mean_score')} |")
        lines.append("")
    reference = report.get("reference")
    if reference:
        lines.extend(["## Plus de main: comprobación con tres rivales adicionales", "",
                      "Punto medio, concesiones Ackerman y paciencia hasta el final. Evaluación de precio "
                      "con el simulador upstream, sin cambiar la selección ni acceder a memoria del agente.", "",
                      "| Lado | Ganancia pareada adicional | Error estándar | Desacuerdo | Recomendación auxiliar |",
                      "|---|---:|---:|---|---|"])
        for role, label in (("buyer", "Compra"), ("seller", "Venta")):
            row = reference["roles"][role]
            lines.append(f"| {label} | {row['paired_gain']:.6f} | {row['paired_standard_error']:.6f} | "
                         f"{row['conflicts_with_main_validation']} | {row['recommendation']} |")
        lines.extend(["", f"Otros {reference['distinct_scenarios']} escenarios y {reference['evaluations']} "
                      "evaluaciones auxiliares en este lote, fuera de los contadores de entrenamiento. "
                      "No modelan días, memoria persistente ni el efecto del texto. "
                      "Un desacuerdo exige revisión antes de adoptar la propuesta.", ""])
    lines.extend(["## Evidencia real y límites", "",
                  f"Fórmula histórica: {data['formula_verified']['passed']}/{data['formula_verified']['tested']} "
                  f"acuerdos; rondas: {data['formula_verified']['rounds_min_messages_matches']}/"
                  f"{data['formula_verified']['rounds_min_messages_tested']}.", "",
                  f"Datos: `{data['counts']}`. Captura histórica de precio, no de la final.", ""])
    history = report.get("historical_states", {})
    market = data.get("market_history", {})
    lines.extend(["## Historiales: comprobaciones adicionales", "",
                  f"Estados de historiales probados a través de World y táctica: {history.get('states_tested')}; "
                  f"fallos: {history.get('failures')}. Patrones de ofertas observados: "
                  f"`{history.get('observed_quote_patterns')}`.", "",
                  "Los fixtures no identifican políticas actuales de los equipos enemigos. El replay prueba "
                  "decisiones sobre prefijos registrados; no inventa victorias ni respuestas a nuestras acciones nuevas.", "",
                  f"Liquidaciones públicas de una sola carta analizables: {market.get('eligible_single_card_settlements')}. "
                  f"Comparaciones propias con referencias anteriores: {len(market.get('own_comparisons',[]))}.", "",
                  "| Equipo observado | Tratos comparables | Mediana de ventaja frente a referencia anterior (P) |",
                  "|---|---:|---:|"])
    for team,row in market.get("team_observations",{}).items():
        lines.append(f"| {team} | {row['comparable_deals']} | {row['median_advantage_P']:.3f} |")
    lines.extend(["", "Cada referencia usa mismo dealer/lado/rareza/barrio, mínimo cinco tratos de otros "
                  "equipos y al menos dos equipos, únicamente ticks anteriores dentro de 240 ticks. "
                  "Es una comparación de precios con cobertura parcial, no beneficio ni puntuación. "
                  "El feed público de duelos no permite atribuir ofertas o cierres a cada enemigo.", ""])
    lines.extend(f"- {note}" for note in data.get("uncertainty", []))
    lines.extend(["", "## Registro del experimento", "",
                  f"Escenarios únicos: **{sim.get('distinct_scenarios')}**. Ejecuciones comparadas: "
                  f"**{sim.get('executed_episodes')}**. Fallos: **{sim.get('failures')}**.", "",
                  "Los escenarios se reutilizan para comparar candidatos; las ejecuciones no son "
                  "otros tantos datos reales independientes. Semillas y trazas completas: `resultados.json`.", "",
                  "## Para el operador antes de la final", "",
                  "1. Verificar código activo, etapa de duelos y ausencia de bloqueo al leer días.",
                  "2. Leer `your_days_weight` y el significado de días; no adivinar el signo.",
                  "3. Revisar por separado compra y venta; conservar el baseline si la validación no mejora.",
                  "4. Cualquier cambio va por el procedimiento actual del operador: selftest y única Gate.",
                  "5. No convertir resultados simulados en afirmaciones de ranking o puntos del servidor.", "",
                  "Este comando no modifica `agent/`, la configuración, el diario ni las tácticas armadas.", ""])
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--feed", type=Path, help="Archivo público JSON/JSONL, opcional")
    ap.add_argument("--duels", type=Path, help="Captura local de duelos, opcional")
    ap.add_argument("--practices", type=int, default=500, help="Escenarios por lado y partición")
    ap.add_argument("--seed", type=int, default=18)
    ap.add_argument("--output", type=Path, default=Path("runs/mini-campo-batalla"))
    args = ap.parse_args(argv)
    if not 10 <= args.practices <= 2000:
        ap.error("--practices debe estar entre 10 y 2000")
    source = source_identity()
    plan = json.loads((Path(__file__).resolve().parent / "config/plan.json").read_text(encoding="utf-8"))
    params = plan.get("duels", {})
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "source": source,
              "evidence": load_evidence(args.feed, args.duels), "pipeline": pipeline_probe(),
              "simulation": run_experiment(practices_per_role=args.practices, seed=args.seed, base_params=params)}
    report["reference"] = crosscheck(report["simulation"], args.seed)
    rows,_ = _read(args.duels if args.duels else FIXTURE, "duels")
    report["historical_states"] = historical_states(rows, params)
    if report["historical_states"]["failures"]:
        raise RuntimeError("Replay histórico con fallo; lote descartado")
    if report["reference"]["failures"]:
        raise RuntimeError("Comprobación upstream con fallo de seguridad; lote descartado")
    if source_identity() != source:
        raise RuntimeError("El código cambió durante el lote; resultados descartados")
    args.output.mkdir(parents=True, exist_ok=True)
    for name, content in (("resultados.json", json.dumps(report, ensure_ascii=False, indent=2)),
                          ("ULTIMO.md", markdown(report))):
        target = args.output / name
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(content + "\n", encoding="utf-8")
        temp.replace(target)
    print(json.dumps({"report": str(args.output / "ULTIMO.md"), "pipeline": report["pipeline"],
                      "simulation": {k: v for k, v in report["simulation"].items() if k != "roles"}},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
