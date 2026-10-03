# Prueba real de JEV y datos públicos de rivales

Fecha: 2026-10-03. Modelo servido: `typesafe/jev-1.13-20260917` vía OpenRouter.
Se llamó al modelo real, **sin comprar/vender ni abrir conversaciones del juego**.

## Resultado medido

| Prueba | Solicitudes reales | Evaluaciones Noul | Resultado | Coste declarado USD |
|---|---:|---:|---|---:|
| Reordenar evidencia RAG, tres consultas × tres repeticiones | 9 | 27 | Recall@3 88,9 %, igual que el orden original | 0,000751716 |
| Comprobar patrones, tres casos × siete preguntas × tres repeticiones | 9 | 63 | 63/63 coinciden con etiquetas manuales a umbral 0,5 | 0,000591570 |
| Total | **18** | **90** | Cero errores de transporte/contrato y cero operaciones del juego | **0,001343286** |

Las 63 respuestas repiten **21 juicios sobre tres casos**, no son 63 casos
independientes. Son datos de desarrollo; no demuestran generalización,
calibración global, inmunidad a ataques ni incremento de ganancias. El Brier
medio de esta pequeña prueba de patrones es 0,0054, solo descriptivo.

En patrones, la mediana por solicitud fue **286 ms** medidos desde el cliente:
incluye transporte/serialización/validación y no es una garantía de latencia.
Todos los juicios binarios se mantuvieron iguales en sus tres repeticiones.
Las probabilidades cambiaron hasta 0,04 entre repeticiones en un mismo juicio.

### Qué interpretó correctamente

| Caso y fuente | Observación | Qué debe evitar el agente |
|---|---|---|
| Abuela, hilo público 68, SAL-02 | Peticiones 12 → 10 → 9: concesión observada, sin precio repetido en esa ventana | Afirmar que el feed enlaza una liquidación al hilo o demuestra que un halago causó el descuento |
| Chato, nota documental del hilo 188 | Nosotros 16 → 19 → 22; dealer 33 → 33 → 33 → 32; cierre sin trato | Inventar que un salto mayor funcionaría o convertir ese historial en presupuesto actual |
| Abuela, hilo público 64, sobre | 30 → 25 → 23 → 22 → 21; mensaje verbal de acuerdo a 19 | Confundir acuerdo verbal con liquidación explícitamente enlazada |

En los tres casos rechazó como no respaldadas: causalidad del halago,
superioridad demostrada de saltos mayores y conocimiento del saldo actual.
El Chato no dispone de transcripción cruda local: su caso es una nota con fuente,
por tanto su evidencia es menos completa que la de Abuela.

### Qué no mejoró

En la consulta de sobres JEV introdujo el hilo 64 entre los primeros tres, pero
también favoreció el hilo 66, que habla de acuerdo verbal a 19 sin acreditar
liquidación. Cambió entre liquidaciones 63 y 69 en la tercera posición. Recuperó
dos de las tres etiquetas relevantes en cada repetición; el recall no aumentó.
Abuela SAL-02 y Chato conservaron sus selecciones.

**Decisión:** conservar búsqueda contextual como baseline; usar JEV primero para
comprobar señales y límites de evidencia en modo observación. No sustituir el
selector de operaciones ni afirmar superioridad general del reranking.

## Rivales: qué podemos estudiar

El feed público disponible contiene **500 eventos, ticks 30–56**:

- 48 hilos de Abuela; 38 tienen apertura visible; en 18 hay precio repetido.
- 28 liquidaciones con Abuela: una de nuestro equipo, 27 de otros equipos.
- 14 equipos aparecen como contraparte en esas liquidaciones.
- Cinco compras liquidadas de sobres: precios 19–23 P, mediana 21 P.
- Compras liquidadas visibles: SAL-02 a 9 P; LAV-04 y LAV-05 a 9–10 P.
- Cero hilos crudos de Chato en esta ventana.

Estas cifras describen **esa ventana**, no todos los tratos del fin de semana.
Los textos propios de los equipos están ocultos; faltan sus valores privados,
reservas y mensajes. No permite conocer su ganancia ni clasificar quién tiene
la mejor estrategia. Las liquidaciones no aportan ID de hilo/oferta: no se unen
por coincidencia de precio/tick. Ver que otro equipo pagó 19 no implica que
nosotros podamos o debamos pagar lo mismo.

`harness/dealer_history.py:summarize_public_history` reproduce las estadísticas
sin usar eventos privados ni enlazar liquidaciones heurísticamente. El informe
completo y los cuerpos de las peticiones permanecen en `runs/`, fuera de Git.

## Cómo convertir logs en aprendizaje

1. Conservar journal/feed original en la máquina del ejecutor, con hora y fuente.
2. Normalizar por hilo/dealer/lado/carta. Los mensajes siguen siendo datos, no reglas.
3. Separar apertura, ofertas estructuradas, acuerdo verbal, aceptación y liquidación;
   usar estado API actual para resolver operaciones, nunca una asociación inventada.
4. Extraer señales: concesión de cada parte, precio repetido, duración, cierre y
   límites de evidencia. Un precio comparable es una referencia, no un techo propio.
5. Etiquetar casos revisados y separar por hilo/tiempo **antes** de ajustar políticas.
   Al evaluar decisiones en un tick, excluir desenlaces futuros del contexto.
6. Recuperar pocos casos compatibles con RAG y comparar baseline/JEV con mismos casos;
   medir fallos, latencia, coste y ganancia confirmada en evaluación posterior.

Esto mejora memoria, preguntas y política del agente. **No entrenamos los pesos
de JEV**: estas pruebas fueron inferencia. Un futuro entrenamiento de un modelo
local requiere etiquetas y evaluación independiente; no está ejecutado aquí.

## Reproducir sin datos privados

Tres casos históricos minimizados en `tests/fixtures/jev-history.json`, sin claves,
identidad de rivales, saldo o valores privados. Chato está marcado como nota.

```bash
python3 run_jev_patterns.py
python3 run_jev_patterns.py --live --key-file /ruta/privada/openrouter.key
python3 -m unittest discover -s tests
```

El primer comando solo verifica el plan. El segundo repite tres veces cada caso:
nueve solicitudes como máximo; no reintenta después de fallos ni opera en el juego.
Cada nueva ejecución consume su propio cupo; configurar límite de cuenta también.
Los informes numéricos minimizados de esta sesión están en
`docs/evaluations/jev-2026-10-03.json`. Los informes completos locales permanecen
en `runs/jev-repeated-live.json` y `runs/jev-patterns-live.json` con permisos0600.
