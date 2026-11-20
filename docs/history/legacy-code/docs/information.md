# Recolector: contexto en segundos, consumo en milisegundos

`agent/information.py` mantiene una memoria de apoyo al negociador. Usa Python y su biblioteca estándar, como el resto del equipo. La recogida funciona en un proceso independiente; leer el contexto no consulta al juego ni a un modelo.

## Antes y durante una negociación

Con `BAZAAR_KEY` en el entorno o en `.env`, desde la raíz del repositorio:

```bash
# Terminal de observación: primer refresco inmediato, después cada cinco segundos.
python3 collect_info.py

# Otra terminal: leer el contexto ya preparado, sin clave ni red.
python3 collect_info.py --context
```

También acepta `--key-file /ruta/local/a/la/clave`. Para preparar una sola instantánea, usar `--once`; para mantener la información actualizada dejar el proceso normal abierto. `--state /ruta/state.json` permite elegir el archivo que deberán compartir todos los consumidores. El archivo por defecto es `runs/information.json`, junto al código instalado.

Cada ciclo verifica por separado `me`, `clock`, `my_offers` y `my_threads`. Conserva saldo, cartas, valores privados, puntuación, pendientes y conversaciones abiertas. Admite ofertas en lista, en `offers` o repartidas entre `open` y `queued`, sin contar dos veces una misma oferta.

El ritmo depende del reloj local, independientemente de ticks, pruebas o acciones del agente. Los cuatro GET se lanzan separados por 0,3 segundos: 0,8 peticiones/segundo de media. La CLI configura timeout de socket de 1,5 segundos, cero reintentos y ninguna espera por tick. La latencia de Internet y DNS no permite garantizar una respuesta cada cinco segundos cuando el servidor falla; se marcan los errores y se saltan ciclos atrasados sin acumular peticiones.

Solo ejecutar un recolector por clave: el bloqueo local también cubre otros worktrees. Todos los procesos y ordenadores comparten el límite del juego de 5 peticiones/segundo. Coordinarlo con el único ejecutor del equipo y evitar observadores redundantes. El panel alojado es un consumidor independiente; este recolector usa la API directa y no depende de que funcione el login del panel.

## Memoria después de la operación

Añadir `--information` al comando habitual del negociador para leer el contexto antes y después y guardar el resultado verificado:

```bash
# Ejemplo de sintaxis; ejecutar solo al decidir esta operación y estos límites.
python3 run_dealer.py abuela -n 1 --card SAL-01 --anchor 5 --limit 10 --information
```

Se conservan hasta 500 tratos en `runs/information.sqlite3`, con deduplicación por equipo e hilo. Solo entra un resultado con `status=deal`, `confirmed=True` y precio válido; una aceptación pendiente o un cambio de inventario no se consideran una compra confirmada. La memoria vuelve a leerse al arrancar y entrega cantidad de muestras, media, mínimo, máximo y fecha por vendedor, carta/sobre y lado. No mezcla compras con ventas ni tipos de sobres. No atribuye cambios de puntuación global a una operación.

Las prioridades se recalculan con cada consulta: actualizar información caducada, esperar al reloj o a una liquidación, reconciliar conversaciones y evaluar repetidos. Las estadísticas describen precios observados; no demuestran un precio óptimo ni un límite oculto. `run_dealer.py` conserva los límites explícitos y la validación del motor; los consejos no generan operaciones por sí solos. Otros ejecutores pueden usar `get_context()` en cada decisión y llamar a `record_result()` después de verificar su liquidación.

## Claude Code y otros consumidores

El repositorio comparte `.mcp.json`. Claude Code lo detecta como `bazaar-info`; en el primer uso se habilita desde `/mcp`, según el consentimiento de configuración del propio Claude. La herramienta `bazaar_context` devuelve JSON compacto y admite `reserve_cash` y `max_age`. El servidor stdio solo lee archivos locales: no necesita la clave ni hace llamadas a Bazaar o a modelos. Arrancar previamente el recolector; sin él la herramienta responde `ready=false`.

El transporte MCP usa JSON-RPC por líneas y el ciclo `initialize` de las revisiones 2024-11-05 a 2025-11-25. Las pruebas cubren handshake, listado y llamada real a través de un subproceso. La CLI local de Claude detectó la configuración; la sesión completa con un modelo requiere habilitar el servidor en Claude. Referencias: [configuración oficial de Claude](https://code.claude.com/docs/en/mcp), [ciclo MCP](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle).

Uso desde cualquier agente Python:

```python
from agent.information import get_context

context = get_context(reserve_cash=150)
# Tratar ready=false como contexto no verificado.
# Antes de aceptar, revalidar la oferta y su valor con el motor de negociación.
```

La lectura devuelve como máximo 40 tipos de inventario y 12 grupos de precios. Informa de truncación. Cada fuente lleva fecha de verificación y estado; al superar 7,5 segundos, fallar la consulta o detectar fechas futuras, `ready` pasa a falso y se suprimen consejos comerciales. Los datos anteriores siguen visibles con ese estado. Las rutas no forman una instantánea atómica: siempre revalidar antes de aceptar.

## Pruebas y medición

```bash
python3 -m unittest discover -s tests -v
python3 bench_information.py
```

Medición local inicial: 2.000 lecturas y serializaciones con 48 activos sintéticos y un trato confirmado; mediana **0,311 ms**, percentil 95 **0,442 ms**, contexto **2.017 bytes**. Es tiempo de consumo de caché, no latencia de Bazaar ni de Claude. El benchmark es reproducible con datos sintéticos y no requiere clave.

El recolector no consume tokens ni crea un servicio de pago. Las consultas a un modelo que haga el usuario desde Claude mantienen el coste de su cuenta. Los archivos de ejecución están excluidos de Git; las claves del equipo/broker y el texto de errores no se persisten. El journal registra verificación/error por fuente sin guardar credenciales.
