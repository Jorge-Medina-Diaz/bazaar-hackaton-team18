# Rendimiento: puntuación, ventas y clasificación

Fecha de observación: 2 de octubre de 2026. Los datos siguientes son históricos; no describen necesariamente el estado actual del juego.

## Conclusión

Una buena operación puede mejorar nuestra ganancia sin mejorar el puesto si otros equipos avanzan más. Además, la puntuación visible puede cambiar mientras nuestros componentes medidos y recursos siguen iguales. No debemos interpretar cada descenso como una venta fallida ni prometer un rebote automático.

## Qué puntúa

Fuente: [reglas oficiales incluidas en el kit](../../../../RULES.md), apartado Scoring.

| Vía | Criterio | Consecuencia para el agente |
|---|---|---|
| Dealers | Porción de su rango de precios capturada; cuentan los tres mejores tratos por nivel, los ausentes como cero y los niveles altos pesan más. | Evaluar si el próximo trato mejora nuestros tres mejores, además de su rentabilidad económica. |
| Otros equipos | Valor ganado según nuestros valores privados. | Comparar el dinero y cartas recibidos con el valor de lo entregado y las comisiones. |
| Duelos | Porción del beneficio capturada; el beneficio disponible se reduce con las rondas de conversación. | Buscar acuerdos rentables sin consumir rondas innecesarias. |
| Mercado propio | Eficiencia en el Market Test y valor creado entre otros equipos. | Evaluar el broker por beneficio realizado; cobrar más comisiones no puntúa por sí mismo. |
| Jueces | Ideas y ejecución, 40 puntos. | Documentar decisiones y pruebas; la clasificación automática no representa toda la evaluación final. |

Negociación y mercado aportan hasta 30 puntos cada uno. No puntúan el número de tratos, las comisiones cobradas, la suerte al abrir sobres ni los regalos. Completar páginas modifica la valoración de las cartas mediante bonus; no es una métrica independiente de puntuación indicada en estas reglas.

Cada día constituye una ronda; el viernes pesa la mitad. Una nueva ronda entra gradualmente según la parte del día jugada. La tabla pública es un snapshot que se refresca cada pocos minutos; `/api/me` muestra los números propios en vivo. No reconstruimos aquí la fórmula exacta de conversión entre componentes y puntuación visible.

## Evidencia observada

| Tick de `/api/me` | Puntos | Puesto | `neg_points` | `ladder_points` | Caja P | Valor colección |
|---|---:|---:|---:|---:|---:|---:|
| 109 | 22,16 | 3 | 73,2 | 0,051 | 281 | 493,7 |
| 110 | 21,77 | 4 | 73,2 | 0,051 | 281 | 493,7 |
| 122 | 22,02 | 5 | 77,6 | 0,051 | 268 | 511,2 |
| 129 | 21,42 | 6 | 77,6 | 0,051 | 268 | 511,2 |
| 130 | 20,15 | 6 | 77,6 | 0,051 | 268 | 511,2 |

- Entre 110 y 122 subieron los puntos y la ganancia registrada, pero empeoró el puesto.
- Entre 122 y 130 bajaron los puntos visibles sin cambiar los componentes mostrados, caja o valor de colección. Esto no demuestra una pérdida económica en una operación ni identifica por sí solo la causa del cambio de puntuación.
- En el snapshot público **130**, el tercero era t08 con **23,93**, frente a nuestros **20,15**: una diferencia de **3,78 puntos**. Ambos datos proceden de la misma tabla. Esa diferencia es histórica, no una meta fija de beneficio en P.
- t08 tenía cero páginas completas y estaba tercero. Por tanto, completar páginas no explica por sí solo el orden de la clasificación.

## Cómo evaluar una venta

Para una venta a otro equipo:

**Ganancia económica = dinero neto recibido − pérdida marginal de valor al entregar las cartas.**

Para intercambios mixtos, añadir el valor marginal de las cartas recibidas y evaluar el paquete completo. Recalcular con inventario actual: vender la última copia de una página completa puede perder también su bonus. Una ganancia de 10 P no equivale automáticamente a 10 puntos de clasificación.

Una copia duplicada de `LAT-01` tenía valor privado de **2,2 P** en la lectura observada. Es una candidata para evaluar y buscar un comprador al que le falte. No se publicó una oferta ni se negoció esa venta durante este análisis. Antes de actuar deben revalidarse propiedad, marginal, comisión y estado de ofertas.

Secuencia propuesta para el único ejecutor:

1. Leer inventario y ofertas actuales; distinguir duplicados de últimas copias.
2. Estimar ganancia, probabilidad de aceptación y ticks necesarios. Priorizar ganancia esperada por tick; para dealers considerar además la mejora de los tres mejores tratos.
3. Fijar un precio mínimo y negociar respetándolo.
4. Tras aceptar, esperar la liquidación del siguiente tick; no registrar beneficio como realizado antes de confirmar.
5. Registrar oferta, precio liquidado, comisión y cambios económicos verificados.
6. Comparar los componentes propios y luego la clasificación de un mismo snapshot. Ajustar la siguiente decisión sin atribuir automáticamente todo cambio de puntos al último trato.

Esta secuencia es una propuesta; el observador no está conectado a un ejecutor que lance operaciones.

## Observación sin saturar el agente

Implementación: observe_performance.py (removed).

- Consume el estado del artefacto cada cinco segundos, sin llamadas a modelos ni órdenes al juego.
- El panel desplegado omite puntuación: el observador la complementa con un GET `/api/me` por nuevo tick del artefacto. Las métricas pueden retrasarse dentro del tick; se registran tick propio y tick del panel.
- Guarda solo cambios en JSONL, con rotación y permisos privados. No guarda clave, cookie ni respuesta completa de la API.
- Señala cambios de puntos sin cambios económicos medidos y mejoras de puntos con peor puesto. Las señales son observaciones, no diagnósticos causales.
- Aplica espera creciente cuando fallan las lecturas. El único POST autentica al propio panel.

```bash
python3 observe_performance.py --key-file /ruta/local/clave --cycles 12
```

`--cycles 0` mantiene la observación hasta interrumpirla. `--reserve-cash` establece una reserva opcional. Logs en `runs/performance-observations.jsonl`, fuera de Git; el baseline real guardado durante el diagnóstico procede de la API directa y está identificado como tal.

## Verificación y pendientes

- Seis pruebas locales del observador pasaron: consultas por tick, métricas integradas, reloj fallido, ausencia de cambios, caída de puntos sin pérdida medida y mejora de puntos con peor puesto.
- La API directa funcionó. El login del artefacto devolvió HTTP 503 `connection_error` con el cliente identificado como `BazaarPerformanceObserver/1.0`. El recorrido completo por el artefacto sigue pendiente; no se afirma validación real de su sesión.
- Se observó un riesgo adicional en `agent/scorer.py`, `keep_value`: puede sumar de nuevo un bonus de página ya incluido en `your_value`. No se corrigió en este análisis y no está demostrado que causara la bajada de clasificación. Revisarlo antes de basar ventas de últimas copias en esa función.
- Próximo paso: diagnosticar la conexión del Worker, verificar login y dos ciclos reales, y después integrar un resumen compacto de cambios con un único ejecutor.
