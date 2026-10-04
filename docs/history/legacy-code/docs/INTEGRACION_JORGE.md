# Entrega para combinar en un solo agente

## Qué aporta esta rama

Origen: política y laboratorio de Codex, scorer de `Santi@5ebf3cb` y curva/interfaz de Jorge en `feat/jorge@cfd0e69`. Se conservan los starters y el SDK oficiales. Estos módulos no arrancan operaciones al importarse.

| Archivo | Aporte para el agente único |
|---|---|
| `agent/scorer.py` | Scorer de Santi corregido: valoración atómica de bundles, selección de activos disponibles, cantidades, comisiones, saldo, caducidad, destinatario y exclusión del venue propio. Usa `me.affinity` cuando existe. |
| `agent/offer_safety.py` | Validación pura de estructura e identidad; precio liquidado correcto para ofertas nuestras o del dealer, comprando o vendiendo. |
| `agent/haggle.py` | Curva e interfaz compatibles con Jorge, con reserva de caja, configuración validada, espera de primera oferta, protección de liquidaciones pendientes y confirmación explícita. |
| `agent/execution.py` | Bloqueo de un ejecutor por equipo en el mismo ordenador; se libera incluso al fallar. |
| `agent/journal.py` | JSONL de Jorge. Se distinguen intención de escritura y respuesta confirmada. `logs/` queda fuera de Git. |
| `negotiation_policy.py` | Política simple, sin red, como referencia para comparar concesiones. |
| `laboratorio.py`, `evaluacion.py` | Simulaciones y pruebas antes de autorizar el ejecutor. |
| `recheck.py --candidate` | Reproduce los cuatro fallos originales contra los módulos corregidos; salida no cero si reaparecen. |

## Lo mejor de Codex que conservaría

- Decisiones comprobables sin gastar primas y fixtures reproducibles.
- Presupuesto, ofertas finales, cantidades y liquidación como controles del código.
- Valoración de toda la oferta como un cambio de inventario: duplicados y bonus se recalculan conjuntamente.
- Trazabilidad del piloto real: SAL-02 comprado por 9 P, confirmado; no se atribuye el descuento a la amabilidad sin comparación.

## Lo peor y qué sustituir

- La concesión fija de 2 P es una referencia; no ha demostrado superar la curva de Jorge. Conservar ambas para comparar, usar una sola en el ejecutor final.
- El piloto original dependió de llamadas manuales de Codex y perdió ticks. Usar el ejecutor de Jorge con estas protecciones y preparar la evaluación antes de abrir un hilo.
- Las simulaciones inventan el dealer y no evalúan un LLM real. No presentar sus resultados como prueba de persuasión.
- No hay todavía scheduler completo de dealer, duelos y broker. No lanzar dos bucles con la misma clave para suplirlo.

## Cómo integrarlo en feat/jorge

Aplicar los módulos anteriores y `tests/test_agent_core.py`, conservar sus CLI, perfiles, scouting y documentación. `agent.haggle.haggle` mantiene los argumentos de Jorge y añade `reserve_cash=0`; devuelve además `confirmed`. El caller debe usar el precio registrado solo cuando `confirmed` sea verdadero.

```python
from agent.haggle import haggle
result = haggle(b, dealer, topic, anchor=anchor, limit=limit,
                rounds=6, beta=1, lines=lines, reserve_cash=reserve_cash)
```

Para ofertas de mercado, consumir `Scorer.board_offers()` y pasar `payment_assets` a `b.accept(..., assets=...)` cuando se pidan tipos. Revalidar saldo, propiedad, valor y estado inmediatamente antes de aceptar; la recomendación del scorer no reserva activos. Definir el límite económico en el planner: el haggler respeta el límite recibido y la caja, pero no decide por sí mismo el objetivo de puntuación.

Un único scheduler debe poseer la ejecución real. El bloqueo funciona entre procesos locales; no coordina ordenadores distintos. El haggler rechaza abrir otra conversación si el equipo ya tiene una: la recuperación de una conversación existente corresponde al scheduler.

## Verificación y límites

Ejecutar `python3 evaluacion.py` y `python3 recheck.py --candidate`. Las pruebas nuevas incluyen compras y ventas con ambos makers, aceptación propia pendiente durante varios ticks, precio correcto, reserva de caja, bloqueo de dos ejecutores, estructura incorrecta, bundles, bonus de página y comisiones.

Las transiciones del bonus master se excluyen de las recomendaciones de bundles hasta confirmar su fórmula con la API. El EV de sobres sigue siendo una estimación de la versión de Santi; no se usa como garantía para comprar. Los nuevos módulos se verificaron offline; el piloto real anterior no equivale a una prueba real de esta nueva versión.

Siguiente paso conjunto: integrar estas piezas, comparar ambas políticas con iguales escenarios y escoger una sola configuración antes del siguiente piloto.
