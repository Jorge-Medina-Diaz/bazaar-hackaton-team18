# Memoria RAG y JEV: integración compatible — 3 de octubre

Cambios en `harness/` y herramientas de evaluación/visor. El runner, la Gate,
el SDK y `config/plan.json` no cambian. No se activa JEV para negociar.
Usar Python 3.10 o superior, con el mismo intérprete en evaluación y tests.

## Memoria que corresponde al hilo correcto

`outcomes` une `open_thread` con su respuesta exitosa o reconciliación, usando el
ID exacto del hilo. La carta por sí sola no identifica una negociación. Hilos
intercalados de compra/venta ya no heredan el lado del último abierto. Identidades
ausentes, contradictorias o ambiguas se omiten; un diario parcial/roto no alimenta
la memoria. El adaptador sigue leyendo el diario sin modificarlo.

Un `measure` del calibrador es un desenlace atribuido, no un asiento enlazado del
libro de liquidaciones. Su precio procede del intent. El cuerpo conserva
`price_source=intent_not_settlement_ledger` y
`outcome_verification=calibrator_attributed`. Un HTTP `ok` por sí solo no crea
un caso. La fase `settled` se conserva por compatibilidad; consultar también la
procedencia. No usar estos casos como etiquetas de liquidación verificada.

## Dealer, ronda, régimen y tiempo

El importador público incluye Abuela, Chato, Pilar y Pícaros. Por defecto mantiene
`oct2-observations` para Abuela/Chato y usa `oct3-observations` para Pilar/Pícaros.
Se puede declarar una versión común explícita para una ventana revisada.

`MemoryCase` añade `round` y `regime`, y `Scope` permite esos filtros más
`as_of_tick`. Campos nuevos opcionales: corpus, scopes y planes antiguos siguen
leyéndose. Una ronda/régimen desconocidos no satisfacen un filtro explícito.
El corte temporal excluye también casos sin tick; todos los filtros se aplican
antes de seleccionar top-k. `global_fts` sigue siendo únicamente el control
experimental deliberadamente sin filtros, y no pasa la validación de JEV si
contiene evidencia fuera de alcance.

Para replay, importar el prefijo con `as_of_tick` antes de construir casos:
filtrar después un resumen que contiene mensajes futuros no reconstruye el pasado.
No asignar la misma ronda/fiebre a un archivo que cruza varios regímenes.

```python
from harness.retrieval import MemoryIndex, Scope, import_feed

cases, coverage = import_feed(events, 'feed-revisado', version='oct3-observations',
                               round=2, regime='normal', as_of_tick=840)
index = MemoryIndex(cases)
try:
    evidence, omitted = index.retrieve('precios de venta',
        Scope('pilar', 'sell', version='oct3-observations', round=2,
              regime='normal', as_of_tick=840))
finally:
    index.close()
```

`run_rag_eval.py` admite `--evidence-version`, `--round`, `--regime` y
`--as-of-tick`. Las consultas etiquetadas deben tener el mismo alcance.
El RAG recupera evidencia; no entrena pesos ni decide precios del ejecutor.

## JEV: consultas acotadas y caché

`run_jev_eval.py` usa por defecto FTS cuando toda la lista cabe en tres posiciones;
no hay selección adicional que hacer. Más de tres candidatos o evidencia omitida
por tamaño requieren evaluación semántica. Cero evidencia produce abstención.
Esto conserva el baseline: no demuestra que cada documento sea relevante.
`--all-candidates` conserva la comparación de desarrollo anterior.

El cliente revalida el alcance antes de consultar su caché. La clave de caché es
SHA-256 de la petición reconstruida: modelo, preguntas, consulta, contexto y
evidencia. Una modificación de cualquiera invalida el resultado anterior.
Hasta 64 entradas, 300 segundos, solo en memoria del cliente; se almacenan scores
validados y uso, sin mensajes ni credenciales. Errores nunca se almacenan.
Los aciertos de caché no consumen una llamada ni un nuevo coste de proveedor.
`pattern_check` no usa caché, para conservar las repeticiones explícitas del piloto.

Los límites de llamadas/bytes siguen siendo por evaluación, no un tope económico
compartido entre procesos. Esta actualización no envía consultas de pago.
Las pruebas usan proveedor simulado; no demuestran mayor precisión de JEV real.

Fuentes de diseño: [API de TypeSafe](https://docs.typesafe.ai/api) y
[reranking](https://docs.typesafe.ai/cookbooks/rerank_typesafe). Se conserva la
ruta OpenRouter ya usada por el proyecto; no se migra de proveedor ni modelo.

## Visor y comprobación

El visor distingue `no_data`, `unverified`, `consistent` y `contradictory`.
No muestra verde porque una carpeta vacía carezca de contradicciones.
Consistencia entre fuentes no demuestra liquidación ni que el proceso esté vivo.

```bash
python3 run_traces.py --check --require-executor --logs logs
```

Una carpeta vacía falla `--check`. `--require-executor` exige además diario v2
válido con tick. Sin ese flag, registros antiguos conservan su comprobación.
Un diario válido con tick tampoco prueba actualidad: revisar su última fecha.

## Adopción por el equipo

1. Traer el commit en la máquina del visor/evaluador. El proceso del visor debe
   recargarse para leer el código nuevo; esto no reinicia el bot.
2. Usar un intérprete Python 3.10+ y revisar el estado del diario con el comando anterior.
3. Añadir contexto verificado al corpus de Pilar/Pícaros; conservar `unknown`
   cuando falte. No convertir guías o ejemplos sintéticos en tratos observados.
4. Comparar recuperación y decisiones sobre hilos nuevos, separados de los usados
   para ajustar las consultas. Mantener las mismas reglas y el mismo prefijo temporal.
5. JEV/RAG siguen fuera del ejecutor. Una recomendación futura deberá pasar por
   las mismas guardas económicas y operativas del bot.
