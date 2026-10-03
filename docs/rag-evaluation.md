# Evaluación de memoria para RAG y registros de dealers

## Resultado y alcance — 2026-10-03

Se evaluó **la recuperación de evidencia**, todavía sin un modelo generando
mensajes o decisiones. No se evaluaron embeddings semánticos ni JEV. El Python
local tiene SQLite/FTS5; no se encontraron paquetes/modelos locales de embeddings.
No instalamos uno ni presentamos vectores léxicos como comprensión semántica.

El piloto usa 81 registros: 48 hilos públicos de Abuela, 28 liquidaciones públicas
y cinco notas revisadas con fuente (dos de Chato y tres de criterios económicos).
Una nota antigua está marcada `superseded`; conservarla permite comprobar que
la búsqueda la excluye. Las otras notas no se consideran reglas oficiales.

Hay **12 consultas manuales**: nueve positivas y tres que deben abstenerse.
Una consulta tiene tres documentos relevantes; las demás positivas tienen uno.
Son consultas de desarrollo revisadas durante el piloto, no un conjunto intacto
de generalización. Los documentos relevantes sí están en el índice, como exige
una evaluación de recuperación; las consultas y sus etiquetas permanecen fuera.

| Método | Recall medio @3 | MRR | Resultados fuera del alcance | Abstenciones correctas | p95 local aproximado |
|---|---:|---:|---:|---:|---:|
| Sin memoria | 0 % | 0 | 0 | 3/3 | 0,002 ms |
| SQL: últimos casos filtrados | 77,8 % | 0,611 | 0 | 3/3 | 0,082 ms |
| FTS global, referencia sin filtros | 74,1 % | 0,667 | 18 | 1/3 | 0,155 ms |
| FTS con filtros | 85,2 % | 0,778 | 0 | 3/3 | 0,090 ms |
| FTS con contexto y filtros | **96,3 %** | **0,944** | **0** | **3/3** | **0,108 ms** |
| Fusión de FTS original/contextual mediante RRF | 96,3 % | 0,944 | 0 | 3/3 | 1,224 ms |

`Recall@3` es la fracción de documentos relevantes recuperados dentro del límite
de tres; se promedia por consulta positiva. MRR mide la posición del primer
documento relevante. Las 18 violaciones del método global mezclan dealer, lado,
fase o notas excluidas: **no son 18 incidentes de filtración de datos reales**.

**Elección para este piloto: FTS contextual con filtros.** La fusión no ganó
recuperación en estas consultas y añadió trabajo. No generalizar este resultado
a otros conjuntos o a una combinación con embeddings reales. El caso de compra
de sobre a 19 aún recupera solo dos de sus tres evidencias relevantes; queda
registrado, no se oculta tras la media.

La ejecución completa tarda aproximadamente 0,10 s; incluye 20 repeticiones por
consulta/método. El paquete contextual medio ocupa 1.231 bytes. El corpus completo
serializado ocupa 82.126 bytes. Son bytes medidos, **no tokens ni coste de modelo**.
Todas las llamadas reales a juego/modelos fueron cero. No se midió ganancia,
calidad de negociación, latencia del modelo ni puntuación oficial.

## Fuente real localizada en esta máquina

`/Users/ruben/projects/bazaar-hackaton-team18/runs/recheck-feed.json`

- 500 eventos públicos, ticks 30–56.
- 48 hilos de Abuela; 38 muestran apertura, diez comienzan truncados.
- 308 mensajes: 165 de Abuela con texto y 143 de equipos con texto `null`.
- 28 liquidaciones de Abuela; otras siete pertenecen al mercado y se excluyen.
- Ninguna conversación de Chato en ese feed.

Un chunk conserva un hilo completo **dentro de la ventana disponible**, con sus
precios, texto visible, tick y fuente. El cuerpo conserva referencias de las
ofertas y no se divide una secuencia de precios arbitrariamente. Si no cabe
en el presupuesto de contexto, se omite entero y se cuenta esa omisión.

Los eventos de liquidación no contienen ID de hilo/oferta. El importador los
mantiene como evidencia separada y realiza **cero asociaciones inferidas**.
Coincidir en precio, equipo y tick no acredita una relación explícita. Un hilo
sin liquidación visible se etiqueta `unknown_in_feed_window`, no como fracaso.

### Abuela: lo que podemos verificar

| Hilo | Observación |
|---|---|
| 68, SAL-02 | Peticiones 12 → 10 → 9; propuestas propias 5 → 7. HANDOFF documenta liquidación confirmada a 9. |
| 64, sobre | Peticiones 30 → 25 → 23 → 22 → 21; termina aceptando propuesta propia de 19. |
| 69, lote | Ofertas de compra 20 → 22 → 22 → 23 → 23 final. Hay una liquidación compatible a 23; el enlace al hilo es inferido. |
| 75, SAL-05 | Oferta de compra 5 repetida hasta final. |

Fuente complementaria: `/Users/ruben/projects/bazaar-hackaton-team18/HANDOFF.md:119`.
Los textos propios están ocultos en el feed: **no permite medir el efecto causal
de un halago** ni afirmar que toda conversación funciona con pasos de uno.

### Chato: evidencia documental, no transcripción cruda

- `/Users/ruben/projects/bazaar-hackaton-team18/ANALISIS_CHATO.md:24`: hilo 188,
  LAT-06, ticks 100–103. Nosotros 16 → 19 → 22; Chato 33 → 33 → 33 → 32.
  Cierre sin trato. Criticó un aumento de tres puntos; no demuestra que un salto
  mayor hubiera producido una oferta mejor.
- `/Users/ruben/projects/bazaar-hackaton-team18-collector/docs/playbook.md:102`:
  hilo 261. El script cerró durante intervención de otro operador, cuando Chato
  bajaba a 32. Es una evidencia documental de conflicto de coordinación.
- `docs/experiments.md`, EXP-013: tiene hipótesis y parámetros, **resultado vacío**.
  No se convierte en una negociación exitosa ni en evidencia indexada.

No se encontraron `logs/chato.jsonl`, `logs/abuela.jsonl`, `logs/feed.jsonl` ni
un archivo de hilos completo en los checkouts revisados. La documentación dice
dónde deberían estar; eso no garantiza que estén guardados en esta máquina.

## Contradicciones que el RAG debe respetar

`docs/decisions.md:21` contiene D-005: pagar por encima del valor no restaría y
el límite sería el suelo del vendedor. EXP-010 (`docs/experiments.md:21`) lo
contradice: sobre a 23, valor aproximado 14,6, `neg_points` 81,6 → 73,2 (−8,4).

EXP-012 (`docs/experiments.md:23`) agrega una incertidumbre: LAT-06 a 22, con
valor 22,5, coincidió con `neg_points` 73,2 → 71,3 (−1,9). No basta recuperar
la simplificación «precio ≤ valor = cero penalización» como garantía universal.
El motivo exacto de ese delta sigue pendiente.

Las notas se revisaron y marcaron **manualmente**. El código aplica la marca
`active/superseded`, versión y visibilidad; no detecta por sí solo contradicciones
ni inventa qué documento corrige a otro. `tick=null` indica que el tick exacto de
una nota no se verificó; el contexto lo muestra como desconocido.

## Procesos revisados

Se encontró `panel.py`, PID 94131, en el checkout `codex/plan-negociacion`.
No se encontraron procesos activos de `run_loop.py`, `run_dealer.py`,
`starter_agent.py`, collector ni scout en la revisión. No se iniciaron ni
detuvieron procesos ni se consultó el juego.

Los dos `logs/information.jsonl` encontrados tienen 112 registros de muestreo
cada uno, con fuente/fecha/error; **cero conversaciones**. No sirven para inferir
el comportamiento de un dealer. Los informes del harness anterior son sintéticos.

## Reproducir

Desde el worktree `/Users/ruben/projects/bazaar-hackaton-team18-harness`:

```bash
python3 run_rag_eval.py \
  --feed /Users/ruben/projects/bazaar-hackaton-team18/runs/recheck-feed.json \
  --notes runs/rag-notes.json \
  --queries runs/rag-queries.json \
  --corpus-output runs/rag-corpus.json \
  --output runs/rag-report.json
python3 -m unittest discover -s tests -p test_retrieval.py -v
```

Archivos locales en `runs/`, excluidos de Git:

- `rag-notes.json`: cinco notas revisadas con fuente y grado de evidencia.
- `rag-queries.json`: consultas, filtros y etiquetas esperadas.
- `rag-corpus.json`: corpus normalizado con procedencia.
- `rag-report.json`: resultados por consulta, hashes, límites y métricas.
- `jev-request-plan.json`: 12 lotes preparados para reordenar evidencia (nueve con
  candidatos, 17 preguntas Noul en total); no se enviaron al servicio.

En otra máquina hacen falta esos datos o un corpus propio: el código no descarga
el feed ni inventa registros. Una consulta tiene `id`, `text`, `scope` y `relevant`
(lista de IDs). `scope` define dealer, lado, carta opcional, fase opcional, equipo
y versión. Los filtros los prepara el llamador; su extracción automática desde
lenguaje natural tampoco está evaluada todavía.

## Antes de JEV

1. Conservar este piloto como referencia de recuperación; añadir consultas
   independientes, paráfrasis y registros de Chato cuando existan.
2. Comparar con/sin memoria sobre decisiones reservadas, separando por hilo y
   tiempo: no usar el desenlace futuro del mismo hilo para decidir un turno pasado.
   Esta separación es distinta de evaluar recuperación, donde el documento
   relevante necesariamente debe existir en el índice.
3. Para JEV, preparar una lista pequeña de evidencia y acciones válidas. Medir
   relevancia, decisiones correctas, abstención, coste y latencia. Un reranker no
   puede recuperar un documento omitido de su shortlist.
4. Mantener saldo, cuota, titularidad, valores marginales y ofertas vigentes en
   la DB/API actual; la memoria histórica aporta evidencia, no autorización.

`harness/jev_plan.py` prepara peticiones según la [API actual de TypeSafe](https://docs.typesafe.ai/api),
sin etiquetas esperadas dentro del estado del modelo. Las tres consultas sin
evidencia no necesitan llamar a JEV. Para ejecutar la evaluación real falta acceso:
no hay herramienta TypeSafe disponible ni `TYPESAFE_API_KEY` configurada en esta
sesión. Se solicitó a Rubén la ruta local de la clave; no reutilizar la del Bazaar.
Las peticiones preparadas no equivalen a una evaluación completada de JEV.

El código nuevo es experimental y no está conectado al ejecutor del equipo.
No se hicieron commits ni push.

## Referencias técnicas

- [SQLite FTS5](https://www.sqlite.org/fts5.html): búsqueda textual y ranking BM25.
- [Anthropic: Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval):
  contexto del chunk y complementar coincidencia lexical/semántica. Aquí el
  contexto lo prepara código, sin contextualizador LLM ni embeddings.
- [Microsoft: RRF](https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking):
  fusión de listas mediante rangos. En nuestro piloto se fusionan dos listas
  lexicales, no búsqueda vectorial.
