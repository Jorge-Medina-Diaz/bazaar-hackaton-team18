# Bazaar SDK for Python

## Recolector de información para el agente y Claude

Python estándar, cuatro GET cada **5 segundos**, memoria persistente de tratos confirmados y contexto local sin llamadas a modelos. Arranque en una terminal del equipo, con `BAZAAR_KEY` ya configurada:

```bash
python3 collect_info.py
```

Consulta instantánea: `python3 collect_info.py --context`. Claude Code detecta el servidor compartido `.mcp.json`; al habilitar `bazaar-info`, la herramienta `bazaar_context` lee ese mismo contexto. Para registrar resultados del negociador, añadir `--information` a su comando habitual. [Uso, tiempos y límites](docs/information.md).

## Panel de cartas con consultas cada 5 segundos

**URL para el equipo:** [Mesa de cartas](https://bazaar-equipo18-cartas.rubenwork1009.chatgpt.site).

Abrir la URL e introducir la clave del Bazaar del equipo. La página pública no contiene datos del juego; el servidor valida la clave y conserva el acceso en una cookie cifrada, Secure y HttpOnly, de ocho horas. No hace falta ejecutar el agente ni tener abierto el ordenador de Rubén. Mientras la página esté abierta consulta cada cinco segundos. El botón **Salir** elimina la sesión.

La versión alojada está en `website/`: `node --test website/worker.test.mjs` comprueba autenticación, privacidad, consulta de las cuatro fuentes y refresco de cinco segundos. Las respuestas recientes se reutilizan entre peticiones con la misma clave en el mismo punto de presencia. El caché es temporal; los movimientos observados no constituyen un historial contable permanente.

La publicación y sus pruebas con respuestas simuladas están verificadas. En la comprobación posterior del 2 de octubre, el login con la clave real devolvió HTTP 503 `connection_error`; el recorrido completo del panel sigue pendiente. La API directa del juego sí funcionó.

El observador consulta saldo e inventario, ofertas, conversaciones y reloj cada **5 segundos**, independientemente del agente y de sus pruebas. Cada fuente muestra la hora de la última verificación; si falla, se conserva el dato anterior y se señala como no verificado. Todas las consultas al juego son GET. Para usar la versión local:

```bash
python3 panel.py --live --key-file /ruta/local/a/la/clave
```

Abrir `http://127.0.0.1:8766/`. También admite `BAZAAR_KEY` en el entorno en lugar de `--key-file`. El archivo puede contener la clave sola o una línea `BAZAAR_KEY=...`; no se debe guardar en Git. La clave permanece en el servidor local y no se envía al navegador.

El panel muestra las cartas y sus valores privados actuales, duplicados, ofertas estructuradas y su estado. Las entradas y salidas se registran desde el inicio del observador; no se atribuyen precios ni compras históricas a partir de un simple cambio de inventario. Las consultas de varias rutas no constituyen una instantánea atómica del servidor.

Sin `--live`, `python3 panel.py` observa el archivo local que escribe `laboratorio.py`. El ejemplo de compraventa es independiente y no altera ese archivo. Para pruebas simultáneas, elegir archivos distintos con `--state-file` en ambos scripts. El ejemplo y la simulación usan precios inventados y no sirven como información actual del juego.


The Bazaar · Cromos de Madrid, a hackathon game hosted by Causa Prima.
Welcome!

One file, standard library only: `bazaar_sdk.py`.
Copy it next to your agent, or run from this folder.

## Laboratorio del equipo: primera prueba paso a paso

Para empezar sin gastar primas ni contactar al servidor:

```bash
cd /Users/ruben/projects/bazaar-hackaton-team18
python3 laboratorio.py --scenario compra --step
```

Enter avanza al siguiente evento y `q` detiene la simulación. El laboratorio muestra el precio solicitado, el mensaje amable, la contraoferta, el saldo y el inventario. Sus precios y su vendedora son inventados: permite verificar decisiones, pero no medir la persuasión real de Abuela.

La primera prueba ejecutada ofreció 7 P por `LAV-03`, recibió una contraoferta de 12 P y subió a 9 P. La vendedora simulada aceptó; la carta entró al inventario en el siguiente tick y el saldo pasó de 40 a 31 P.

Archivos para inspeccionar:

- [laboratorio.py](laboratorio.py): simulación local y recorrido paso a paso.
- [negotiation_policy.py](negotiation_policy.py): decisiones de ofrecer, aceptar, cerrar o esperar; mensajes amables.
- [evaluacion.py](evaluacion.py): evaluación rápida con 17 pruebas y ocho simulaciones comparativas.
- [tests/test_negotiation.py](tests/test_negotiation.py): 13 comprobaciones de presupuesto, ofertas finales, liquidación e inventario.
- [PROPUESTA.md](PROPUESTA.md): alcance de la mejora y pasos posteriores.

Escenarios disponibles: `compra`, `limite`, `final` y `varias`. Para comparar la lógica de precios del starter con la política mejorada, usar `--compare` en lugar de `--step`. Para variar el tamaño de concesión, usar `--increment 1` o un entero positivo. La política nueva está conectada al laboratorio; todavía no sustituye el bucle del starter real.

```bash
python3 -m unittest discover -s tests -v
```

**Qué inicia cada script:** `starter_agent.py` habla con Abuela, compra un sobre, lo abre y publica duplicados. `starter_broker.py` empareja compradores y vendedores en un mercado y requiere una clave de broker. Para avanzar con control ahora, usar el laboratorio. La prueba real y la apertura de sobres requieren una clave válida del equipo; el laboratorio no realiza ninguna de esas operaciones.

**Varias cartas:** el inventario contiene varios activos con identificadores distintos y admite copias de un mismo tipo. El escenario `varias` comprueba tres compras, incluida una copia repetida con menor valor simulado. En el juego real, las compras de carta concreta al dealer se documentan por tema individual, los sobres entregan varias cartas y las ofertas entre equipos pueden incluir varias cartas. El límite de 50 elementos por lado corresponde a una oferta; las reglas no indican que sea un límite del inventario.

Para evaluar todo de una vez, ejecutar `python3 evaluacion.py` o `python3 evaluacion.py --json`. La evaluación usa un dealer inventado; no mide persuasión real. En el escenario `limite`, la política mejorada reduce las decisiones de 13 a ocho y evita seis repeticiones de precio.

**Piloto real completado:** compra de El Portero (`SAL-02`) a Abuela por 9 P, frente a una petición inicial de 12 P, tras propuestas propias de 5 y 7 P. La liquidación y la entrada al inventario están confirmadas. La política se aplicó mediante llamadas controladas de Codex; falta integrarla en un ejecutor autónomo. El relato está en [HANDOFF.md](HANDOFF.md).

 Según la instrucción de Rubén, abrir sobres del juego únicamente después de probar y analizar. Las cartas sueltas ya están abiertas; `open_pack` se aplica a sobres sellados.

## 1. Start in five minutes

```bash
export BAZAAR_URL=https://bazaar.causaprima.ai
export BAZAAR_KEY=tk-xxxx-xxxx      # the key on your team's slip; keep it to your team
curl -s -H "X-Team-Key: $BAZAAR_KEY" $BAZAAR_URL/api/me   # shows your team: the key works (401 = check it)
python3 starter_agent.py            # or: uv run starter_agent.py
```

The starter says hello to Abuela Carmen, haggles for a neighbourhood pack, opens it and prints what you pulled.
Copy it, then make it yours.

The game is open Fri 19:00–23:00, Sat 09:00–23:00 and Sun 09:00–15:00 (Madrid).
Outside those hours nothing ticks.
Big screen: https://bazaar.causaprima.ai

## 2. The calls you use most

```python
from bazaar_sdk import Bazaar, BazaarError
b = Bazaar("https://bazaar.causaprima.ai", "tk-xxxx-xxxx")

me = b.me()                        # cash, level, unlocked dealers, your cards (each with your_value), score
b.value("LAV-09")                  # what one more copy of a card is worth to you (private)
th = b.open_thread("abuela", topic={"buy": {"pack": "sobre_barrio"}})
b.say(th["id"], "Hello! 18 primas?", price=18)   # words plus a structured price
b.accept(offer_id)                 # take a standing offer; it settles on the next tick
```

Everything else: `dealers()`, `dealer(id)`, `catalog()`, `thread(id)`, `close_thread(id)`, `my_threads()`, `list_offer(give, want, venue)`, `cancel(id)`, `my_offers()`, `board(venue)`, `venues()`, `open_pack(id)`, `flag(message_id, reason)`, `duels()`, `duel_say(id, text, price, days)`, `duel_accept(id)`, `open_venue(...)`, `set_fee(...)`, `close_venue(...)`, `broker(key)`, `leaderboard()`, `clock()`, `schedule()`, `levels()`, `feed()`.
Each method is one HTTP route; the docstrings in `bazaar_sdk.py` show the payloads.

## 3. Rules that shape your agent

| Rule | What it means for your code |
|---|---|
| Words persuade, structure binds | Only a structured offer that its counterparty accepts moves cards or cash. Read the offer, not the words. |
| One heartbeat | Per tick your team may accept one offer and send one message per conversation; everything accepted settles on the next tick. `clock()` has the tick length and `next_tick_in`. |
| Dealers move when you move | A dealer concedes only after you do. The same price twice is not a new offer. When its patience runs out it names a final offer (`"final": true`): take it or it walks. |
| Private values | Your set multipliers are secret, and so are everyone else's. `your_value` is what the scorer counts for you. Duplicates are worth little to you and a lot to someone missing them. |
| Value, not activity | You score the value you create: good dealer deals, gains in trades with other teams, your share in duels, and what your market makes possible. The number of trades never counts. |

The full rules are in `RULES.md`, next to this file.

## 4. Errors you will meet

`BazaarError` carries the server's `code`, `message` and HTTP `status`.
A refused request costs nothing.

| code | why | what to do |
|---|---|---|
| `wait_for_tick` | a second message or accept in the same tick | the SDK waits for the next tick and retries |
| `rate_limited` | more than 5 requests per second | the SDK pauses and retries |
| `locked` / `cooloff` | dealer not unlocked yet / cooling off after tricks | `dealers()` shows how each one unlocks |
| `persona_quota` | too many conversations or deals with a dealer this hour | come back next game hour |
| `insufficient_cash`, `not_owner`, `asset_locked` | the deal would fail | re-read `me()` |
| `self_venue` | your team key on your own market | trade elsewhere; your broker runs your market |
| `venue_not_live` | team markets open later (see `schedule()`) | trade on El Rastro meanwhile |
| `bad_key` | wrong or rotated key | ask the organisers at the desk |

## 5. Your own market

From level 2 you can open a market (a refundable bond of 250 primas plus 20).
You get a broker key for it:

```bash
python3 -c 'from bazaar_sdk import Bazaar; import os; print(Bazaar(os.environ["BAZAAR_URL"], os.environ["BAZAAR_KEY"]).open_venue("My market", fee_bps=150, rules={"mechanism": "board"})["broker_key"])'
BROKER_KEY=bk_... python3 starter_broker.py     # keep it running all game
```

Most of the market points come from *the Market Test*: every venue regularly gets the same synthetic book of buyers and sellers, and your broker scores the share of the possible gains it realises.
The starter broker matches by quoted prices, as the free stall does.
Traders quote away from limits they keep hidden, so a broker that estimates those limits does better.

## 6. New things during the weekend

New dealers and mechanics appear as levels.
`b.levels()` lists what is announced and what is active, with a line on how to use it.
A route a level brings is one `b.call("POST", "/api/...", {...})` away.
For live updates instead of polling: `GET /api/events/stream?scope=team` with your `X-Team-Key` header.

## Núcleo para integrar con Jorge

La entrega está en [INTEGRACION_JORGE.md](INTEGRACION_JORGE.md): módulos corregidos, fortalezas y limitaciones, compatibilidad y pasos para combinar en un agente. `agent/haggle.py` no se inicia al importarlo; requiere un cliente y límites explícitos. La clave no forma parte de los archivos.

```bash
python3 evaluacion.py
python3 recheck.py --candidate
```

La entrega incluye 50 pruebas propias (17 anteriores y 33 del núcleo). El recheck del candidato verifica los cuatro fallos originales contra los módulos corregidos. Los logs quedan en `runs/` y `logs/`, fuera de Git.

## Observación de puntuación sin negociar

El análisis de reglas, métricas observadas y estrategia de venta está en [ANALISIS_RENDIMIENTO.md](ANALISIS_RENDIMIENTO.md).

`observe_performance.py` consume el estado del artefacto cada cinco segundos y registra solo cambios. Como el panel desplegado aún omite puntuación, consulta `/api/me` una vez por nuevo tick del panel; las métricas pueden retrasarse dentro del tick. No llama a modelos ni envía órdenes al juego. La autenticación al propio panel es su único POST.

```bash
python3 observe_performance.py --key-file /ruta/local/clave --cycles 12
```

El log compacto está en `runs/performance-observations.jsonl`, ignorado por Git, con rotación y permisos privados. `--cycles 0` observa hasta interrumpir; `--reserve-cash` configura una reserva opcional. Distingue cambios de puntos sin cambios económicos medidos y mejoras de puntos acompañadas de peor puesto, sin atribuir automáticamente causas.

Estado verificado el 2 de octubre: seis pruebas locales pasan; el acceso real al panel devuelve HTTP 503 `connection_error` al validar la sesión. La API directa del juego funciona. El recorrido completo por el artefacto sigue pendiente.
