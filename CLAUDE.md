# Bazaar · Cromos de Madrid — agente del Team 18

Hackathon de Causa Prima (2–4 oct 2026). **Empieza por [docs/README.md](docs/README.md)** (estado, claves, guardarraíles). Reglas: [RULES.md](RULES.md) · **puntuación y prioridades: [docs/scoring.md](docs/scoring.md)** · SDK: [README.md](README.md) · notas de API: [docs/api.md](docs/api.md).

## Estructura
```
bazaar_sdk.py       SDK oficial: no editar (se puede actualizar)
agent/
  haggle.py         regateo genérico con vendedores (curva de concesión + AC_next), compra y venta
  dealers.py        PROFILES: lo que sabemos de cada vendedor, como datos (precios, frases)
  duels.py          duelos: step() por tick, curva con decay, nunca fuera de your_limit
  affinity.py       posterior por equipo sobre las 720 permutaciones de multiplicadores; p_worth, buyers, sellers, load()
  journal.py        log(stream, **row) -> logs/<stream>.jsonl
  client.py         client(): Bazaar con BAZAAR_KEY del entorno o de .env
run_duels.py        CLI: jugar los duelos activos (--watch = solo observar y registrar)
run_dealer.py       CLI: regatear con un vendedor (sobres, cartas, ventas)
market.py           Todos los mercados: scan (gangas), sell-dups, cross (libros cruzados), bid-page (pujar por una página)
affinity.py         multiplicador probable de cada rival por barrio (bayes sobre trades y saltos de puntuación), --watch graba
rivals.py           rol analista, sin clave: clasificación, mercados de equipo y pujas grandes de El Rastro (--watch 3600); ver docs/analista.md
flags.py            candidatos a flag: mensajes de vendedor cuyo texto contradice su oferta (flaggear solo a mano)
bench.py            grabar los libros del Market Test (necesita BROKER_KEY de nuestro mercado)
probe.py            snapshot de todos los GET en logs/probe/<tick>/ (formas de respuesta, cambios)
scout.py            estudiar a un vendedor con el feed público (los regateos de todos los equipos)
docs/               conocimiento: playbook, experimentos, decisiones, diseño
logs/               JSONL de cada ejecución (gitignored, cada uno tiene los suyos)
```
Un vendedor nuevo = una entrada en `agent/dealers.py` + una sección en `docs/playbook.md`. Módulos futuros (duelos, broker, comercio) van como `agent/<modulo>.py` + `run_<modulo>.py`.

## Proceso (exploratorio, converger al diseño óptimo)
1. **Observar gratis antes de gastar**: `python3 scout.py <dealer>` muestra cómo negocia con todos.
2. **Hipótesis → experimento**: anota en [docs/experiments.md](docs/experiments.md) la hipótesis y los parámetros *antes* de ejecutar.
3. **Ejecutar** y anotar el resultado (precio, rondas, puntuación de `/api/me`) en la misma fila.
4. **Destilar**: lo que se confirma pasa a [docs/playbook.md](docs/playbook.md) y a `agent/dealers.py`.
5. **Decisiones** de diseño o de estrategia: una entrada fechada en [docs/decisions.md](docs/decisions.md).

## Reglas de código
- **Nunca** llamar a `/api/admin/*`.
- Antes de aceptar cualquier oferta: `agent.haggle.offer_ok()` (estructura antes que palabras).
- El código decide cifras y aceptaciones; el texto (nuestro o de LLM) nunca. Ofertas monótonas. Ver [docs/negotiation-design.md](docs/negotiation-design.md).
- Todo lo que toca la API deja rastro en `logs/` vía `agent.journal.log`.
- Una sola persona ejecuta contra el juego con la clave del equipo (límite: 1 accept y 1 mensaje por hilo por tick, 5 req/s).
- Clave en variable de entorno `BAZAAR_KEY`, nunca en el código.
- Simple: stdlib, funciones, sin frameworks.
