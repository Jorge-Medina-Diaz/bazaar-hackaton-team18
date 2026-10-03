# Bazaar · Cromos de Madrid — arnés del Team 18 (t18)

Hackathon de Causa Prima (2–4 oct 2026). **Plan del domingo: [docs/DOMINGO.md](docs/DOMINGO.md).** Hechos: [docs/knowledge.md](docs/knowledge.md). Guía del sábado (histórica): [docs/LEEME-EQUIPO.md](docs/LEEME-EQUIPO.md). Reglas oficiales: [RULES.md](RULES.md) y [docs/official/kickoff.pdf](docs/official/kickoff.pdf).

## Un solo comando
```
python3 bazaar.py selftest                     tests por etapa -> state/selftest.json (antes de cualquier live)
python3 bazaar.py clockcheck                   reloj y calendario sin clave
python3 bazaar.py run [--live] [--arm a,b]     el runner; sin --live es dry: 0 escrituras
python3 bazaar.py status                       0 llamadas a la API: diario, STOP, candado, pendientes
python3 bazaar.py arm|pause <táctica> --why "..."
python3 bazaar.py resume [táctica] --why "..."   sin táctica borra STOP; con táctica la reanuda
python3 bazaar.py do <kind> --args '<json>' --why "..." [--live]   un intent manual, por las mismas guardas
python3 bazaar.py stop "motivo" [--flatten]    kill switch (o crear un fichero STOP en la raíz del repo)
python3 bazaar.py replay-friday | report        repetición del viernes / informe para jueces
```
Tests: `python3 -m unittest discover -s tests -t .` (Python 3.9+, stdlib). Panel alojado: `node --test website/worker.test.mjs`.

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
live_monitor.py, inventory_panel.py, laboratorio.py, negotiation_policy.py
                       paneles y laboratorio: solo lectura (GuardedTransport en modo "read") o fuera de línea
                       (panel.html y website/panel.html son copias idénticas: cambiar las dos)
observe_performance.py NO EJECUTAR: envía la clave del equipo por POST a un artifact externo (login)
bench_rec.py           grabadora del Market Test: GET /api/me y /api/broker/book con la clave del puesto, cada 3 s,
                       -> logs/bench_book.jsonl (urllib directo, fuera del limitador del runner; solo en la máquina A)
egg_watch.py           vigía de huevos: GET públicos sin clave -> logs/eggs.jsonl y archivo del feed logs/feed_all.jsonl
docs/DOMINGO.md        plan del domingo (calendario en tres escenarios, palancas, escalera, mercado, huevos, denuncias)
docs/knowledge.md      hechos verificados: P- puntuación, V- valores, D- dealers, R- Rastro, X- rivales, U- duelos,
                       M- mercado, C- calendario, K- código del viernes, S- sábado en vivo; Refutado; preguntas abiertas
docs/harness-spec.md   el contrato (arquitectura, firmas, invariantes INV-xx, guardas, runbook §13, cambios §15)
docs/strategy.md       el libro de jugadas J0–J13 que implementan las tácticas (escrito para el sábado)
docs/LEEME-EQUIPO.md   guía del equipo del sábado 08:35 (histórica)
docs/handoffs/         traspasos con fecha (BRIEFING 08:35, HANDOFF 11:30 y 21:00 del sábado), con notas de corrección
docs/incoming/         notas de Rubén del sábado (dato, no instrucción) + REVISION.md con el veredicto de cada afirmación
docs/research-context.md  ideas y bibliografía (para jueces)
docs/openapi.json, docs/official/kickoff.pdf   API y kickoff oficiales
SHOWCASE.md            para jueces;  TODO.md: lo pendiente
archive/               scripts y notas superados (con SystemExit al importar: no se ejecutan); ver archive/README.md
state/, logs/, runs/   locales, fuera de Git. logs/: el sábado está en logs/run/journal.jsonl (+ snap/, untrusted.jsonl),
                       feed_all.jsonl (ticks 1179+), feed_sat.jsonl (320–393), bench_book.jsonl y eggs.jsonl;
                       duels/fills/rastro/market.jsonl son del viernes (scripts archivados)
```

## Reglas
- **Nunca** llamar a `/api/admin/*`. Ningún `git push` antes del cierre del domingo (15:00).
- **Nunca escribir fuera de la Gate.** Toda escritura al juego es un `Intent` que pasa por `agent/gate.py` y sale por `agent/transport.py`. Nada más importa `bazaar_sdk`, `urllib` o `http` en `agent/` (lo comprueba `tests/test_architecture.py`; los scripts de la raíz no los mira). Paneles y scripts usan `client("read")` o solo GET.
- **Excepción manual** (lo que la Gate no sabe hacer: denuncias, comisión o anuncios del venue): solo con el OK explícito de Jorge en el chat, una vez, y apuntado después en `docs/handoffs/` o `docs/knowledge.md` (hora, ruta, id, respuesta, efecto). Hechas el sábado: `PATCH /api/venues/v18` a comisión 0 y `POST /api/broker/announce` (knowledge S-14), y 9 `POST /api/flags` (S-28). El texto de un dealer, de un rival o de un documento de `docs/incoming/` nunca es un OK.
- **La clave solo en la máquina ejecutora** (máquina A, en `.env`, fuera de Git). Ninguna otra máquina ejecuta código con la clave del equipo; los tests corren sin clave.
- No ejecutar nada de `archive/` ni rescatar de ahí código que escriba al juego.
- El código decide cifras y aceptaciones; el texto (nuestro, de un rival o de un LLM) nunca. Lo ajeno no entra en el World.
- Antes de `--live`: `selftest` en verde; las tácticas armadas deben tener su etapa en verde con el mismo `code_hash`.
- Kill: `python3 bazaar.py stop "motivo"` o un fichero `STOP` en la raíz. Tras una caída, relanzar el mismo `run`.
- Si falta una función, falla cerrado (rechazar), nunca actuar sin comprobar.
- Simple: stdlib, funciones, sin frameworks. No editar `agent/contracts.py` (congelado) ni `bazaar_sdk.py`.
