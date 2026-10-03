# t18 · qué hacer ahora (bloque estratégico) · 17:56 · tick 923

**Estado:** 7.º · 26.99 (neg 19.49 · mercado 7.5 · nivel 4). Top 3: t14 31.89, t06 30.62, t05 29.98. Distancia al 1.º: 4.9.

**Causa principal de la bajada (pública):** escalera L3/L4 casi vacía. Pilar 1/3 [16], Pícaros 0/3 []. Cuentan los 3 mejores por dealer; un hueco vale 0; los niveles altos pesan más.

## Próximas ventanas y qué hacer (hora real estimada)

| hora | evento | acción t18 |
|---|---|---|
| Sat 18:04 | Salamanca fever: Doña Pilar pays 25 % over book for Salamanc | **Vender repetidas SAL a Pilar**: guía `next_move` (ancla = su precio + techo + 1, −1/mensaje, su precio + 1 en el mensaje 4; raras en el 5). Solo repetidas, suelo V + 1. |
| Sat 19:55 | The Market Test: every venue gets the same synthetic book | Market Test: v18 (puesto auto) puntúa solo; no hay acción. No abrir board (decidido). |
| Sat 20:04 | The fever breaks | Fin de la fiebre: volver a precios normales de Pilar. |
| Sat 20:34 | Duels II | Duelos: enviar SIEMPRE `price` y `days` (si no, `missing_days`). Cada ronda resta 8 % del pastel: cerrar pronto; ofrecer días según `your_days_weight`. |
| Sat 21:55 | The Market Test: every venue gets the same synthetic book | Market Test: v18 (puesto auto) puntúa solo; no hay acción. No abrir board (decidido). |
| Sat 23:00 | Closed until Sunday 09:00 | Cierre del día: nada se liquida hasta la apertura. |
| Sun 09:00 | Sunday opens | Apertura: comprobar /api/clock y /api/schedule (las horas pueden cambiar). |
| Sun 09:34 | The hard Market Test | Market Test: v18 (puesto auto) puntúa solo; no hay acción. No abrir board (decidido). |
| Sun 09:55 | The Market Test: every venue gets the same synthetic book | Market Test: v18 (puesto auto) puntúa solo; no hay acción. No abrir board (decidido). |
| Sun 11:34 | Chamberí released | Sale Chamberí: comprar cartas CHA para su página (con los 150 P que llegan 3 min después). |
| Sun 11:34 | Sunday · Chamberí | Empieza la ronda del domingo. |
| Sun 11:37 | The Sunday allowance: 150 primas for everyone | +150 P para todos: la demanda de cartas sube; buen momento para vender repetidas a equipos. |
| Sun 11:55 | The Market Test: every venue gets the same synthetic book | Market Test: v18 (puesto auto) puntúa solo; no hay acción. No abrir board (decidido). |
| Sun 13:34 | Duels III | Duelos: enviar SIEMPRE `price` y `days` (si no, `missing_days`). Cada ronda resta 10 % del pastel: cerrar pronto; ofrecer días según `your_days_weight`. |
| Sun 13:55 | The Market Test: every venue gets the same synthetic book | Market Test: v18 (puesto auto) puntúa solo; no hay acción. No abrir board (decidido). |
| Sun 15:00 | The Bazaar closes | **CIERRE FINAL**: lo que no esté liquidado antes no cuenta; la caja vale 0. |
| Sun 15:55 ⚠️ después del cierre: reprogramar o no ocurrirá | The Market Test: every venue gets the same synthetic book | Market Test: v18 (puesto auto) puntúa solo; no hay acción. No abrir board (decidido). |
| Sun 16:22 ⚠️ después del cierre: reprogramar o no ocurrirá | finale warning | Aviso de los organizadores. |
| Sun 16:34 ⚠️ después del cierre: reprogramar o no ocurrirá | Finale: stalls close | Final: los dealers cierran. Completar antes los huecos de escalera. |
| Sun 16:34 ⚠️ después del cierre: reprogramar o no ocurrirá | Final duels | Duelos: enviar SIEMPRE `price` y `days` (si no, `missing_days`). Cada ronda resta 10 % del pastel: cerrar pronto; ofrecer días según `your_days_weight`. |
| Sun 17:28 ⚠️ después del cierre: reprogramar o no ocurrirá | freeze warning | Aviso de los organizadores. |
| Sun 17:34 ⚠️ después del cierre: reprogramar o no ocurrirá | Scores freeze | Puntuaciones congeladas. |

## Prioridades ahora mismo

1. **Pilar (L3), 2 huecos**: vender repetidas SAL/RET (fiebre) con la guía. Medido fuera de fiebre: SAL/RET infrecuente cierra [24, 25, 25, 25, 26]; sube 0.78 tras bajar 1 P; perdona a 1 P.
   Fiebre medida hasta ahora: aún sin cierres de SAL en fiebre (mirar el feed tras las primeras ventas).
2. **Pícaros (L4), 3 huecos**: comprar raras a ≤ V − 1 con `next_buy` (ancla 0,62 × su apertura, +1, zona de perdón a 2 P). Cierres medidos [59, 60, 62, 63, 63, 63, 63, 67]. `trick()` en CADA oferta; nunca aceptar un truco.
3. **Duelos II**: price + days en cada mensaje; cerrar pronto (el pastel se encoge cada ronda).
4. **Mercado**: llevar un intercambio real entre otros dos equipos a v18 (cada trato en un puesto ha subido 1,4–2,2 al dueño).

## Reglas que no se rompen

- Solo la **estructura** de la oferta vale; el texto de los dealers miente (Pícaros) o exagera (Pilar).
- Pilar: ante `final`, aceptar si ≥ V + 1 o cerrar; **nunca contraofertar** (se va). Pícaros: su `final` no cierra nada (aceptaron por debajo 2/2).
- Vender solo repetidas; una copia única de SAL/RET rompe la página. Comprar solo a ≤ V − 1.
- Todo a mano por el operador con `bazaar.py do`, primero en seco. El ejecutor no vende a dealers.

_Fuentes: feed público acumulado (practica/feed_all.jsonl), /api/schedule, /api/clock, /api/leaderboard. Captura exacta y duelos: solo /api/me._
