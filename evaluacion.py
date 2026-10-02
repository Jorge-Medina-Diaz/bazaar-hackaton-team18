"""Evaluación rápida de la política local antes de una partida real."""
import argparse
import io
import json
from pathlib import Path
from time import perf_counter
import unittest

from laboratorio import SCENARIOS, Simulation


def repeated_prices(events):
    """No confundir precios iguales en compras distintas con repetir una oferta."""
    prices, repeats = set(), 0
    for event in events:
        if event["action"] == "offer":
            repeats += event["price"] in prices
            prices.add(event["price"])
        if event["action"] in ("settled", "close", "refused"):
            prices.clear()
    return repeats


def evaluate():
    started = perf_counter()
    root = Path(__file__).resolve().parent
    suite = unittest.defaultTestLoader.discover(str(root / "tests"), top_level_dir=str(root / "tests"))
    output = io.StringIO()
    tests = unittest.TextTestRunner(stream=output).run(suite)
    rows, violations = [], []
    for name, scenario in SCENARIOS.items():
        for policy in ("base", "mejorada"):
            simulation = Simulation(scenario, policy)
            list(simulation.steps())
            row = {"scenario": name, **simulation.summary(),
                   "repeated_prices": repeated_prices(simulation.events),
                   "simulated_net_value": round(sum(a["value"] - a["paid"] for a in simulation.assets), 2)}
            rows.append(row)
            if policy == "mejorada":
                if simulation.cash < 0 or simulation.pending or row["repeated_prices"]:
                    violations.append(f"{name}: saldo, liquidación o precios repetidos")
                if any(a["paid"] > min(scenario.maximum, a["value"]) for a in simulation.assets):
                    violations.append(f"{name}: compra fuera del límite económico")
    return {"passed": tests.wasSuccessful() and not violations,
            "duration_seconds": round(perf_counter() - started, 6),
            "tests_run": tests.testsRun, "test_failures": len(tests.failures),
            "test_errors": len(tests.errors), "violations": violations,
            "results": rows, "test_output": output.getvalue(),
            "scope": "Verifica la política y un dealer inventado; no mide persuasión real ni predice la puntuación."}


def require_passed(report):
    if not report.get("passed"):
        raise RuntimeError("Evaluación fallida: detenerse antes de operaciones reales")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = evaluate()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Evaluación {'APROBADA' if report['passed'] else 'FALLIDA'} · "
              f"{report['tests_run']} pruebas · {report['duration_seconds']:.4f} s")
        for row in report["results"]:
            print(f"{row['scenario']:7} {row['policy']:8} cartas={row['cards']} "
                  f"saldo={row['cash']} decisiones={row['decisions']} "
                  f"repeticiones={row['repeated_prices']}")
        print(report["scope"])
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
