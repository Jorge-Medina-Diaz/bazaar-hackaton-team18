# Los Pícaros · guía medida (complementa docs/seguridad-picaros.md)

## PRIORIDAD · SAL-11 (épica) y su «final» falso — verificado en el feed (ticks 854–869)

- **SAL-11 acuñada:** hilo 1218, t16 pujó 69 → 150 → 151; Los Pícaros pidieron **187 → 174 → 167** (`final`, «Last offer, amigo! Then we are gone») y **t16 aceptó 167** (tick 858). La relistó en El Rastro a 315 (tick 858) y a 305 (tick 869). Bajaron 13 y 7: más que en raras.
- **Su `final` es falso:** hilo 1069, «59, the last word» con `final: true`, y aceptaron después la puja de 58 de t01 (que subía de 1 en 1, 55→58). t05 cerró 54 tras su final de 54. t02, que subió deprisa, pagó 67.
- **«Gato por liebre» sistemático:** 12 casos firmes; la oferta da una infrecuente del mismo barrio con el precio atractivo (mensajes 7124, 7130, 7160, 7201…).

**Jugada SAL-11 para t18** (V ≈ 198 + posible master bonus; confirmar con `GET /api/me/value?card=SAL-11`):
`topic {"buy":{"card":"SAL-11"}}` · ancla **115** (= 0,62 × su apertura 187, la misma proporción que dio el mejor cierre en raras; otra sesión propuso ~130, ambas válidas) · **+1 por tick** · ignorar `final` y prisas · al llegar a 2 P de su oferta honesta, pedir eso · **techo V − 1 (197)** · objetivo ≤ 160. Comprobar `trick()` en cada oferta.
Reventa en la fiebre de Salamanca (h 9,15–11,15): vender a Pilar a ≥ 199. **Sin medir** cuánto paga Pilar por una épica (el calendario dice «25 % sobre catálogo» → ~225): primero en seco.


*Claude, sáb 3 oct ~17:00. Solo hilos públicos de Los Pícaros; nada de otros dealers. Parámetros vivos: `docs/dealer_params.md`.*

Medido (12 compras de raras, 7 tratos: 54, 54, 54, 58, 59, 59, 67; 10 trucos firmes):
- Abren a 73. **Bajan siempre que subimos**, con +1 igual que con +3 → subir **de 1 en 1**.
- **Perdonan a 2 P** de su oferta honesta (t05: 54 frente a su 56). Tras un truco han aceptado más lejos (t01: 58).
- Truco «gato por liebre»: la oferta da otra carta (más barata) que la del tema. `harness/picaros_guide.trick()` lo detecta por estructura.
- Venderles: comunes a 4 (no se mueven), infrecuentes 10 → 13.

`harness/picaros_guide.py`: `next_buy(ref, V-1, theirs, ours)` y `next_sell(rarity, V+1, theirs, ours)`; `theirs` = [(precio, final, trick(topic, offer))].
Reglas: ancla 45 · +1 · al llegar a su oferta honesta − 2, pedir eso · aceptar solo oferta honesta ≤ nuestro siguiente y ≤ V − 1 · nunca truco · su `final` no cierra nada.
