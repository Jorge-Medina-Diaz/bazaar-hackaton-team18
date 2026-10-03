# Bazaar · Cromos de Madrid — arnés del Team 18 (t18)

Hackathon de Causa Prima (2–4 oct 2026). Guía del equipo: [docs/LEEME-EQUIPO.md](docs/LEEME-EQUIPO.md). Reglas oficiales: [RULES.md](RULES.md) y [docs/official/kickoff.pdf](docs/official/kickoff.pdf).

## Un solo comando
```
python3 bazaar.py selftest                     tests por etapa -> state/selftest.json (antes de cualquier live)
python3 bazaar.py clockcheck                   reloj y calendario sin clave
python3 bazaar.py run [--live] [--arm a,b]     el runner; sin --live es dry: 0 escrituras
python3 bazaar.py status                       0 llamadas a la API: diario, STOP, candado, pendientes
python3 bazaar.py arm|pause <táctica> --why "..."
python3 bazaar.py do <kind> --args '<json>' --why "..." [--live]   un intent manual, por las mismas guardas
python3 bazaar.py stop "motivo" [--flatten]    kill switch (o crear un fichero STOP en la raíz del repo)
```
Tests: `python3 -m unittest discover -s tests -t .` (Python 3.9+, stdlib). Panel alojado: `node --test website/worker.test.mjs`.

## Evaluación y observabilidad integradas

`harness/` y `run_harness.py` son experimentos offline con selectores históricos
puros; no sustituyen las tácticas v2. `run_rag_eval.py`, `run_jev_eval.py` y
`run_jev_patterns.py` son evaluaciones independientes. JEV no entra en el World,
decide límites ni arma tácticas. `agent/trace.py` y `run_traces.py` leen el diario
v2 sin modificarlo; `run_traces_tunnel.py` comparte el visor con contraseña.
Ver `docs/integration-handoff.md` y `docs/traces.md`. No importar scripts de
`archive/` para ejecutar estas herramientas.

## Qué es cada fichero
```
bazaar.py              CLI: el único punto de entrada
bazaar_sdk.py          SDK oficial: NO editar
config/plan.json       páginas objetivo, cancelaciones de arranque, bandas, perfiles numéricos de dealers
agent/
  contracts.py         M0 CONGELADO: World, Intent, Prediction, Paths, ARGS, KINDS, TACTICS, GET_ALLOWLIST
  transport.py         la única conexión: GET por allowlist; escribe solo send() con permiso de la Gate
  gate.py              la Gate: única vía de escritura (guardas -> permiso -> transport.send -> diario)
  guards.py            reglas G-xx y Cfg (límites); offer_safety.py: estructura de ofertas antes que palabras
  valuation.py         valor marginal y predicciones (sin E/S)
  world.py             Sensor: construye el World (solo campos estructurados, nunca texto ajeno)
  journal.py           diario encadenado en logs/run/ ; calibrate.py: predicción vs medida, pausas
  runner.py            bucle por tick: tácticas -> intents -> Gate; STOP, candado (execution.py)
  talk.py              plantillas de texto (el texto nunca decide cifras)
  tactics/             hygiene, dealers, rastro, duels, pages, bench: proponen intents, no escriben
  client.py            client("read"): transporte de solo lectura para paneles
  dashboard.py, dashboard.html, redact.py   panel (Vercel vía api/index.py)
sim/                   servidor falso y bots para los tests (127.0.0.1 o en proceso)
tests/                 suite completa (tests/__init__.py aísla: BAZAAR_TEST=1, sin clave)
api/index.py, vercel.json, website/, panel.py, panel.html, run_dashboard.py,
live_monitor.py, observe_performance.py, inventory_panel.py, laboratorio.py, negotiation_policy.py
                       paneles y laboratorio: solo lectura (GuardedTransport en modo "read") o fuera de línea
docs/harness-spec.md   el contrato (arquitectura, firmas, invariantes INV-xx, guardas, runbook §13)
docs/knowledge.md      hechos verificados (P-xx puntuación, D-xx dealers, U-xx duelos)
docs/strategy.md       el libro de jugadas que implementan las tácticas
docs/research-context.md  ideas y bibliografía (para jueces)
docs/openapi.json      API oficial
SHOWCASE.md            para jueces
archive/               scripts y notas superados (con SystemExit al importar: no se ejecutan)
state/, logs/, runs/   locales, fuera de Git
```

## Reglas
- **Nunca** llamar a `/api/admin/*`.
- **Nunca escribir fuera de la Gate.** Toda escritura al juego es un `Intent` que pasa por `agent/gate.py` y sale por `agent/transport.py`. Nada más importa `bazaar_sdk`, `urllib` o `http` en `agent/` (lo comprueba `tests/test_architecture.py`). Paneles y scripts usan `client("read")`.
- **La clave solo en la máquina ejecutora** (máquina A, en `.env`, fuera de Git). Ninguna otra máquina ejecuta código con la clave del equipo; los tests corren sin clave.
- No ejecutar nada de `archive/` ni rescatar de ahí código que escriba al juego.
- El código decide cifras y aceptaciones; el texto (nuestro, de un rival o de un LLM) nunca. Lo ajeno no entra en el World.
- Antes de `--live`: `selftest` en verde; las tácticas armadas deben tener su etapa en verde con el mismo `code_hash`.
- Kill: `python3 bazaar.py stop "motivo"` o un fichero `STOP` en la raíz. Tras una caída, relanzar el mismo `run`.
- Si falta una función, falla cerrado (rechazar), nunca actuar sin comprobar.
- Simple: stdlib, funciones, sin frameworks. No editar `agent/contracts.py` (congelado) ni `bazaar_sdk.py`.
