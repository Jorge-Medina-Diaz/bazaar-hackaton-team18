# Síntesis: dónde estamos y qué sabemos

*Última actualización: vie 2 oct, tick 74 (≈22:05). Mantener al día: es lo primero que hay que leer.*

> **Ahora mismo (tick 99):** 281 P · **nivel 2 (El Chato, acceso anticipado)** · página SAL completa · `neg_points` 73,2 · puesto 2 · `run_loop.py` operando. **Regla E9:** nunca pagar a un vendedor por encima de nuestro valor.

| Documento | Para qué |
|---|---|
| [harness.md](harness.md) | Evaluación offline: ganancia, seguridad, consumo, comparación de candidatos y límites |
| [rag-evaluation.md](rag-evaluation.md) | Recuperación de evidencia: comparación de métodos e historial local de Abuela/Chato |
| [jev-security.md](jev-security.md) | Cliente JEV acotado, validación, credenciales y límites de seguridad |
| [jev-real-testing.md](jev-real-testing.md) | Prueba real, repeticiones, patrones de dealers y límites de datos de rivales |
| [integration-handoff.md](integration-handoff.md) | Instrucciones para integrar la rama en main y resumen para el equipo |
| [scoring.md](scoring.md) | Cómo se puntúa, penalizaciones y prioridades |
| [api.md](api.md) | Todo lo verificado de la API (rutas, formas, errores) |
| [playbook.md](playbook.md) | Conocimiento confirmado por vendedor y mecánica |
| [experiments.md](experiments.md) | Cada ejecución: hipótesis → resultado |
| [decisions.md](decisions.md) | Decisiones fechadas y qué haría revisarlas |
| [negotiation-design.md](negotiation-design.md) | Diseño del negociador (para los duelos) |
| [audit.md](audit.md) | Auditoría crítica, opciones y plan del sábado |
| [broker-design.md](broker-design.md) | Broker para el Market Test |

## Estado del Team 18
- 383 P · nivel 1 · 1 trato (el de bienvenida, a 17 P) · `ladder_points` 0,022 · negociación 5,25 · puesto 8.
- **Affinity: CHA 1,6 · RET 1,3 · SAL 1,1 · LAT 0,9 · LAV 0,7 · MAL 0,5.** Los dos sets que más valoramos llegan el sábado (RET) y el domingo (CHA).
- **Álbum:** SAL 7/10, LAT 4/10, MAL 2/10, LAV 1/10.
  - A SAL solo le faltan **SAL-02** (común, 11), **SAL-08** (infrecuente, 27,5) y **SAL-10** (rara, 77). Completar la página suma un 25 % sobre ≈ 291 P de página, unos +73 P.
- **Repetidos** (valen el 25 % o el 10 % para nosotros): SAL-01 ×3, LAV-03 ×2, LAT-04 ×2, MAL-04 ×2.

## Las 10 cosas que más importan
1. **El dinero no puntúa.** Puntúan la parte del rango capturada a los vendedores, el pastel de los duelos, el valor ganado con otros equipos (a nuestros valores) y el mercado.
2. **Con los vendedores no hay penalización por no cerrar trato**, pero los tratos al precio de salida no desbloquean nivel. Los 3 mejores tratos por nivel cuentan y los que faltan valen 0.
3. **En los duelos, un trato fuera de nuestro límite resta** y el pastel se reduce con cada ronda (decay de 0,06 a 0,10).
4. **La Abuela es predecible.** Sobres: 30 → 26 → 25 → 24 → final 22–23 en unos 5 ticks, empecemos donde empecemos. Comunes: 12 → 10. Infrecuentes: 29 → 21–22.
5. **Las cartas sueltas son la forma barata de llenar la escalera** (t13: 11,73 puntos con 37 P). Mejor aún si son las que nos faltan (SAL-02, SAL-08).
6. **El valor de una carta para nosotros cambia con lo que ya tenemos.** Cuando tengamos SAL-02 y SAL-08, SAL-10 valdrá unos 77 + 73: comprarla a otro equipo será una ganancia de valor enorme.
7. **Los repetidos casi no valen nada para nosotros** y sí para quien no los tiene: hay que venderlos a otros equipos (en El Rastro: 5 % + 1 P de comisión).
8. **Estructura antes que palabras.** `offer_ok()` impide aceptar una oferta que no corresponda al tema del hilo.
9. **El feed público muestra los regateos de todos** con los vendedores y solo guarda 500 eventos: hay que grabarlo (`scout.py --save`).
10. **Oferta final = sin segunda oportunidad.** Se decide en ese mismo tick contra un límite fijado de antemano (D-006). Un trato con un vendedor nunca resta en la escalera.
11. **Fórmula de valor verificada:** catálogo × affinity × [1; 0,25; 0,1] por copia. El bonus de página está pendiente de verificar.
12. **Medir y no suponer.** El desglose de `score` en `/api/me` se guarda antes y después de cada trato. La fórmula exacta de la escalera aún no la conocemos.

## Guardarraíles (para no cagarla)
- Nunca llamar a `/api/admin/*`. Una sola clave y un solo ejecutor a la vez.
- Nunca aceptar una oferta sin `offer_ok()`. Nunca aceptar en un duelo fuera de `your_limit`.
- Antes de un experimento, apuntar la hipótesis en experiments.md. Después, el resultado y el `score` antes y después.
- Respetar los límites: 1 aceptación por tick, 1 mensaje por hilo y tick, 5 req/s, 6 hilos, 30 ofertas, 3 sobres por hora y 8 tratos por hora con la Abuela.
- Cada vez que se abra un nivel: `python3 probe.py` y leer `GET /api/levels` antes de tocar nada.

## Preguntas abiertas (por orden)
1. ¿Cómo se calcula exactamente la parte capturada en la escalera? → medir con EXP-003.
2. ¿La oferta final de la Abuela es su suelo o se puede bajar más con pasos grandes?
3. ¿Vender a la Abuela (comunes a 5, infrecuentes a 13 fijo) puntúa en la escalera?
4. ¿Cuándo se anuncia el nivel 2 y qué es? → `GET /api/levels`.
