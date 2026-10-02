# Bazaar · Cromos de Madrid — agente del Team 18

Hackathon de Causa Prima (2–4 oct 2026). Reglas: [RULES.md](RULES.md) · SDK: [README.md](README.md) · notas de API: [docs/api.md](docs/api.md).

## Estructura
```
bazaar_sdk.py       SDK oficial: no editar (se puede actualizar)
agent/
  haggle.py         regateo genérico con vendedores (curva de concesión + AC_next), compra y venta
  dealers.py        PROFILES: lo que sabemos de cada vendedor, como datos (precios, frases)
  journal.py        log(stream, **row) -> logs/<stream>.jsonl
run_dealer.py       CLI: regatear con un vendedor (sobres, cartas, ventas)
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
- El código decide cifras y aceptaciones; el texto (nuestro o de LLM) nunca. Ofertas monótonas. Ver [docs/negotiation-design.md](docs/negotiation-design.md).
- Todo lo que toca la API deja rastro en `logs/` vía `agent.journal.log`.
- Una sola persona ejecuta contra el juego con la clave del equipo (límite: 1 accept y 1 mensaje por hilo por tick, 5 req/s).
- Clave en variable de entorno `BAZAAR_KEY`, nunca en el código.
- Simple: stdlib, funciones, sin frameworks.
