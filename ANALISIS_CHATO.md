# Abuela y Chato: evaluación de la negociación

Análisis del 2 de octubre de 2026. Datos históricos consultados por GET, sin nuevas ofertas. Fuente: [reglas del kit](RULES.md) y [ficha oficial de Chato](https://bazaar.causaprima.ai/api/dealers/chato).

## Diagnóstico breve

La amabilidad encaja con Abuela, pero no demuestra por sí sola que cause un descuento. Chato publica una personalidad menos generosa, más estricta y con poca paciencia. Nuestra negociación con él cedió mucho más de lo que conseguimos a cambio. Conviene adaptar las concesiones y proteger información estratégica antes de buscar trucos de conversación.

## Evidencia y límites

| Rasgo de Chato | Valor publicado |
|---|---:|
| Memoria | 0,90 |
| Astucia | 0,85 |
| Estrictez | 0,85 |
| Paciencia | 0,35 |
| Generosidad | 0,25 |
| Tendencia a conversar | 0,30 |

Estos números describen rasgos. No revelan tamaño de contexto, stacks, algoritmo de memoria ni un umbral concreto de concesión. Su biografía menciona que recuerda a quienes intentan pasarse de listos; las reglas generales contemplan memoria de trato y posibles periodos de rechazo para algunos dealers.

En el piloto con Abuela, SAL-02 se compró por 9 P frente a una petición inicial de 12 P, después de propuestas propias de 5 y 7 P. Se combinaron precio y tono: no hubo un experimento que aislara el efecto del halago. Tampoco fue un piloto de incrementos constantes de 1 P. Otros tratos pueden haber usado esa estrategia, pero no se verificaron aquí.

Conversación **188**, compra de LAT-06 a Chato:

| Tick | Oferta propia P | Oferta estructurada de Chato P |
|---|---:|---:|
| 100 | 16 | 33 |
| 101 | 19 | 33 |
| 102 | 22 | 33 |
| 103 | — | 32 |

Chato criticó expresamente una subida de tres puntos. Nosotros cedimos 6 P y él bajó 1 P; el hilo terminó sin trato. El registro contiene mensajes de ambos lados dentro del mismo tick: no inferimos su orden causal exacto del orden de la lista.

El valor privado de una copia adicional de LAT-06 observado anteriormente era 22,5 P. Pagar 32 P habría dado una pérdida económica de 9,5 P según ese valor, sin considerar un objetivo distinto de ladder. El límite debe volver a consultarse antes de otra negociación.

## Qué permite realmente el juego

Las reglas dicen que repetir un precio no provoca una concesión y que los pasos pequeños consiguen pasos pequeños. Cada conversación tiene un límite secreto. Cuando aparece una oferta estructurada final, se acepta dentro del límite propio o se abandona.

La inyección contra dealers está permitida, pero las reglas especifican que puede cambiar lo que dicen, no sus precios. Conseguir que Chato escriba una promesa no acredita una mejora: importan la oferta estructurada y la liquidación.

## Hipótesis de estrategia para probar

1. **No revelar el techo:** conservar en el planner el presupuesto, límite y valores privados. No indicar que pagaríamos más ni revelar qué carta completa una página salvo una decisión explícita con motivo medible.
2. **Ser breve y coherente:** precio concreto, mensaje corto y un motivo consistente. Evitar historias cambiantes, falsa autoridad y repetición de mensajes sin movimiento.
3. **Adaptar la concesión al margen:** comparar incrementos pequeños con una o dos concesiones mayores, siempre dentro del mismo techo. Una concesión mayor podría inducir más respuesta, pero también entregar beneficio innecesariamente; no se ha demostrado superior aquí.
4. **Medir reciprocidad:** registrar cuánto cedemos y cuánto cede él. Si no progresa, comparar continuar con otra oportunidad; no elevar automáticamente el límite para parecer serios.
5. **Elegir contraparte:** comprar a otro dealer o equipo si la ganancia esperada es mejor. Contra Chato, un trato puede interesar por ladder aunque no sea el mejor económicamente; declarar ese objetivo y presupuesto antes de empezar.

Ejemplo de mensaje a evaluar, con precio calculado por el planner: «Chato, por esta copia ofrezco {precio} P. Si te encaja, cerramos». El mensaje no revela el precio máximo ni garantiza aceptación.

## Evaluación propuesta antes de ejecutar

Comparar políticas con el mismo tipo de carta, rango de valor y techo; registrar dealer, tick, precio inicial, movimientos, oferta final, precio liquidado, motivo de cierre y datos revelados. Las cuotas, stock, memoria y límites ocultos pueden variar: no presentar conversaciones distintas como un experimento perfectamente controlado.

Métricas: ganancia económica confirmada, mejora de ladder cuando sea observable, ticks consumidos, reciprocidad de concesiones, cierres sin trato y señales de rechazo. Separar el texto del dealer de sus ofertas.

No se modificó `agent/haggle.py` ni se probó una nueva política en vivo en esta entrega. Las protecciones propuestas están en [SEGURIDAD_AGENTE.md](SEGURIDAD_AGENTE.md).
