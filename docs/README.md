# Síntesis: dónde estamos y qué sabemos

*Última actualización: sáb 3 oct, tick 279 (hora de juego 3,65, ronda 2 «Gran Vía»). Mantener al día: es lo primero que hay que leer.*

> **Ahora mismo:** 116 P · **puesto 1** (29,29) · `neg_points` 53,4 · `market` 6,5 (Market Test: eficiencia 0,90 con el puesto starter `v18`) · `ladder_points` 0,078 · 27 tratos · nivel 2 (Abuela + El Chato). **Doña Pilar** (nivel 3, coleccionista: paga por encima de catálogo y vende sobres de oro) ya la tiene t13; abre para todos en la hora 5,5. Radio Rastro anunciada. Álbum 32/50: **SAL 10/10 y RET 10/10**, LAT 8/10, LAV 2/10, MAL 2/10. Faltan: LAT-09/10 · LAV-01/02/05/06/07/08/09/10 · MAL-01/02/03/06/07/08/09/10. En El Rastro hay 12 cartas nuestras a la venta, entre ellas las copias únicas LAT-02/03/04/06/07/08, MAL-04, LAV-03 y LAV-04. Próximo: Market Test (hora 5,0), **Duelos I (5,15)** y Pilar abierta a todos (5,5).

| Documento | Para qué |
|---|---|
| [scoring.md](scoring.md) | Cómo se puntúa, penalizaciones y prioridades |
| [api.md](api.md) | Todo lo verificado de la API (rutas, formas, errores) |
| [playbook.md](playbook.md) | Conocimiento confirmado por vendedor y mecánica |
| [experiments.md](experiments.md) | Cada ejecución: hipótesis → resultado |
| [decisions.md](decisions.md) | Decisiones fechadas y qué haría revisarlas |
| [duels-strategy.md](duels-strategy.md) | **Estrategia de duelos v2**: arquetipos de los rivales y qué hacer contra cada uno |
| [negotiation-design.md](negotiation-design.md) | Diseño del negociador (para los duelos) |

## Estado del Team 18
- 247 P · nivel 2 · 16 tratos · `neg_points` 79,0 · `ladder_points` 0,051 · `duel_points` 0 · `mm_points` 0 · puesto 7 (tick 150). La puntuación baja sola mientras otros comercian (27,4 en el tick 75 → 19,4).
- **Affinity: CHA 1,6 · RET 1,3 · SAL 1,1 · LAT 0,9 · LAV 0,7 · MAL 0,5.** Los dos sets que más valoramos llegan el sábado (RET) y el domingo (CHA).
- **Álbum (tick 150):** **SAL 10/10 (completa: no vender ninguna)**, LAT 8/10, LAV 3/10, MAL 2/10.
  - A LAT solo le faltan sus dos raras, **LAT-09** y **LAT-10** (pujas de EXP-009 a 55). La última cierra la página: táctica de la última carta (playbook) y prueba del posible tope de 50 por trato (decisions.md, pendiente 1).
- **Repetidos:** LAT-01 ×2 y LAT-05 ×2. Compradores de LAT: t15, t14, t07 (playbook, mapa de affinity).

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
- Respetar los límites: 1 aceptación por tick, 1 mensaje por hilo y tick, 12 ofertas nuevas por tick (las canceladas cuentan), 5 req/s, 6 hilos, 30 ofertas abiertas, 3 sobres por hora y 8 tratos por hora con la Abuela. Los números vigentes están en `GET /api/clock` → `limits`.
- **Ritmo: 1 tick cada 60 s** (cambio del sáb 3 oct; el domingo está anunciado a 15 s). Nunca fijar segundos en el código: leer `tick_seconds` del reloj (`market.expiry()` ya lo hace). Con 60 s hay tiempo para decidir cada oferta, pero cada tick perdido cuesta el doble de reloj: en duelos, 16 ticks = 16 min.
- Cada vez que se abra un nivel: `python3 probe.py` y leer `GET /api/levels` antes de tocar nada.

## Preguntas abiertas (por orden)
1. ¿Cómo se calcula exactamente la parte capturada en la escalera? → medir con EXP-003.
2. ¿La oferta final de la Abuela es su suelo o se puede bajar más con pasos grandes?
3. ¿Vender a la Abuela (comunes a 5, infrecuentes a 13 fijo) puntúa en la escalera?
4. ¿Cuándo se anuncia el nivel 2 y qué es? → `GET /api/levels`.
