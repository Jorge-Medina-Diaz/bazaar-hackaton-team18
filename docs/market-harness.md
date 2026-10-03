# Radar y evaluación de conversión del mercado

Entrega en `codex/market-opportunity-harness`, integrada con avances de main.
Objetivo: encontrar contrapartes concretas para el puesto gratuito v18 y medir
qué ocurre después de una propuesta, antes de gastar caja o sustituir el puesto.

Siguiente investigación: [guía para Santiago](market-research-santiago.md).
Datos de la reanudación: [escaneo en vivo](market-live-2026-10-03.md).

## Uso inmediato del analista

Desde la raíz del repo, con Python 3.10+ (sin dependencias nuevas):

```bash
python3 -m market_harness refresh
```

Una consulta acotada a clasificación, reloj, calendario, feed público y libros de
**todos los mercados abiertos**. Usa `public_get` y su limitador de una petición
por segundo. Normalmente tarda unos 25 segundos; no deja un proceso permanente.
No lee `.env`, estado privado, clave de equipo ni clave de broker.

Resultados locales, excluidos de Git:

- `runs/market-harness/brief.md`: los 18 equipos y cinco parejas prioritarias.
- `radar.json`: cotizaciones, bloqueos, descartes y todos los candidatos.
- `snapshot.json` y `snapshot-<fecha>.json`: fotos para repetir evaluaciones.
- `public-events.json`: eventos públicos únicos, validados y guardados atómicamente.
- `movement.md` / `timeline.json`: movimiento observado cuando se pasa `--previous`.

Repetir el análisis sin red o comparar con otra foto:

```bash
python3 -m market_harness offline --snapshot runs/market-harness/snapshot.json
python3 -m market_harness refresh --previous runs/market-harness/snapshot.json
```

`--previous` se carga antes de recoger y guardar la nueva foto.
Las métricas distinguen contadores acumulados del venue de eventos en una ventana
limitada; no convierten un feed de 500 eventos en un historial completo.

El marcador muestra su propio tick y retraso frente al reloj. Los grupos conservan
ids alternativos sin repetir propuestas equivalentes en el brief. Foto bloqueada:
`compatible_count=null` significa indeterminado, no ausencia de cruces.

```bash
python3 -m market_harness timeline \
  --snapshot foto-nueva.json --previous foto-anterior.json
```

Repetir `--snapshot` para historial. `--archive` recupera eventos observados sin
convertir su unión en una ventana completa. Tasas por horas de juego comparables;
no tiempo de pared durante pausas. Desaparición de oferta no equivale a liquidación.
La recogida incluye catálogo para generar la demo sin otra consulta:
`python3 -m jury.report --market-snapshot runs/market-harness/snapshot.json`.

## Qué decide y qué no sabe

1. Solo precios estructurados, carta individual, estado abierto, contraparte
   pública y caducidad conocida. Ofertas privadas, lotes y trueques quedan fuera.
2. Identifica un pseudónimo únicamente enlazando el mismo id de oferta y venue
   con un listado público; nunca adivina quién es por su estilo de escritura.
3. Excluye al propietario del mercado destino y pares del mismo equipo.
4. Calcula el coste con comisión y distingue `compatible_quotes` de
   `renegotiation_required`. El segundo **no genera un anuncio de cierre**.
5. Un borrador exige al menos dos ticks de margen. Una foto incompleta, demasiado
   lenta (>2 ticks), un destino cerrado o tarifas pendientes bloquean los borradores.
6. Ordena por margen entre cotizaciones, después por tiempo restante. Las parejas
   que comparten oferta son alternativas, no tratos que puedan sumarse.

La comisión se atribuye correctamente: el ahorro mostrado corresponde al
**comprador si acepta la misma venta**, no al vendedor que la publicó. El
excedente privado y la probabilidad de cierre son `null`: no conocemos caja,
inventario libre, valores marginales ni política de los rivales. Una cotización
compatible tampoco asegura que ambos quieran mudarla de mercado.

Los borradores contienen únicamente hechos estructurados: equipos, carta, ids,
venues, precios, comisión y caducidad. Texto de anuncios/dealers no modifica esos
datos ni entra en ellos. No prometen descuentos secretos, ganancias privadas o
saltarse las reglas del otro agente.

## Evaluación rápida y replay

```bash
python3 -m market_harness evaluate --synthetic 100 --out runs/market-harness/synthetic
python3 -m market_harness evaluate --snapshot runs/market-harness/snapshot.json
python3 -m market_harness evaluate --snapshot runs/market-harness/snapshot.json --as-of 630
```

Se puede repetir `--snapshot` para varias fotos históricas. Replay excluye fotos
enteras posteriores a `--as-of`: no reconstruye un libro pasado con información
futura. La misma pareja repetida no suma más exposiciones.

Cuatro políticas **hipotéticas**, ninguna asignada a un rival real:

| Política | Qué permite considerar una propuesta |
|---|---|
| `rastro_only` | Solo Rastro; ningún mensaje cambia su allowlist. |
| `fee_comparator` | Enumera venues; exige ahorro de comisión para el comprador. |
| `feed_reader` | Enumera venues; necesita datos explícitos de ofertas vigentes. |
| `conservative` | Lo anterior, foto del mismo tick, cuatro ticks restantes y ahorro. |

Compara anuncios genéricos y propuestas específicas. Es una simulación de
**consideración**, no de respuestas reales, aceptación ni negociación completa.
No llama a un LLM/JEV ni inventa una probabilidad calibrada. En los 100 escenarios
incluidos, 90 parejas son analizables y 48 cumplen los requisitos de migración.
Los bots limitados a Rastro consideran 0; los que leen propuestas específicas
consideran 48. Esto comprueba las políticas declaradas, **no demuestra una mejora
de 48 tratos en el juego**. Los tests ejercitan además listados y liquidaciones
sintéticas por separado.

## Medir lo publicado por el operador

Después de una publicación real, el analista registra un manifiesto local. Ejemplo
de formato con ids ficticios, no para enviarlo al juego:

```json
[
  {
    "id": "campana-001", "target": "v18", "tick": 700,
    "seller": "t01", "buyer": "t02", "ref": "RET-01",
    "announcement_event_id": 40000
  }
]
```

```bash
python3 -m market_harness conversions \
  --snapshot runs/market-harness/snapshot.json \
  --campaigns runs/market-harness/campaigns.json
```

Comprueba el anuncio público exacto (id, tick, venue y nombres de ambas partes y
carta en el texto), separa listados posteriores de liquidaciones y cuenta una
liquidación una sola vez. Exige venue, partes, carta y dirección del intercambio;
no considera una oferta desaparecida como un trato. Una campaña posterior recibe
la asociación cuando se solapan varias para la misma pareja. Ventana: 30 ticks.
Si el anuncio ha salido del feed, la publicación queda sin verificar: conservar
fotos/exportaciones públicas para ampliar el historial es trabajo posterior.

El resultado señala ventana incompleta, contrapartes distintas y asociaciones.
No mide descubrimiento/lectura del anuncio por el otro bot (dato no público), no
prueba causalidad y no asigna puntos extra. Mercado sigue midiéndose con el
leaderboard; tratos/volumen y comisión recaudada no son la fórmula del marcador.

## Integración para quien trabaja en main

- Incorporar esta rama cuando el equipo decida revisarla. Los cambios están en
  `market_harness/`, su test, documentación y HANDOFF; `agent/`, Gate, SDK,
  `bazaar.py`, configuración y panel analista no cambian.
- Ejecutar `python3 -m unittest tests.test_market_harness tests.test_architecture`.
- El analista puede refrescar y entregar un brief de cinco propuestas al operador.
  No es necesario cargar el feed entero al agente: consultar `radar.json` cuando
  haya cambios y usar sus campos tipados; RAG sirve para precedentes, no para
  reemplazar una lectura actual del libro.
- Este módulo no publica, acepta, cancela, abre mercados ni reinicia al ejecutor.
  Toda acción posterior conserva el único escritor y su Gate. El transporte actual
  tiene broker desactivado: publicar requiere una capacidad revisada del operador,
  no usar este radar como bypass del SDK.
- Antes de publicar, releer las dos ofertas, tarifas vigentes, margen de tiempo y
  límites autorizados. Las partes deben cancelar/republicar sus propias ofertas;
  nunca pueden trasladarse ofertas ajenas desde el radar.
- Conservar v18 auto por ahora: la prueba local de Claude (500 libros, semilla 11)
  da eficiencia ponderada 0,9053 al greedy frente a 0,8987 del broker existente.
  Abrir un board sustituye el puesto gratuito y no tiene un broker operativo hoy.

Siguiente extensión prioritaria: trueques 1:1, observados en tres de cinco tratos
entre equipos de la ventana real. Antes hay que verificar su ejecución y comisión
con los contratos de Gate y pruebas propias; no asumir que el motor auto de cruces
de caja/carta los resuelve. Otra prioridad es guardar continuamente el feed sin
duplicar el poller del panel, para medir campañas que salgan de los últimos 500
eventos. Esta entrega hace fotos acotadas y replay local.

Fuentes: [reglas del repo](../RULES.md), [conocimiento medido](knowledge.md),
[venues oficiales](https://bazaar.causaprima.ai/api/venues),
[clasificación oficial](https://bazaar.causaprima.ai/api/leaderboard),
[reevaluación de los 18 equipos](market-recheck-2026-10-03.md).
