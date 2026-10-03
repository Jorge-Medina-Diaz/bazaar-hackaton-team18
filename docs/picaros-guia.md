# Los Pícaros · guía medida (complementa docs/seguridad-picaros.md)

*Claude, sáb 3 oct ~17:00. Solo hilos públicos de Los Pícaros; nada de otros dealers. Parámetros vivos: `docs/dealer_params.md`.*

Medido (12 compras de raras, 7 tratos: 54, 54, 54, 58, 59, 59, 67; 10 trucos firmes):
- Abren a 73. **Bajan siempre que subimos**, con +1 igual que con +3 → subir **de 1 en 1**.
- **Perdonan a 2 P** de su oferta honesta (t05: 54 frente a su 56). Tras un truco han aceptado más lejos (t01: 58).
- Truco «gato por liebre»: la oferta da otra carta (más barata) que la del tema. `harness/picaros_guide.trick()` lo detecta por estructura.
- Venderles: comunes a 4 (no se mueven), infrecuentes 10 → 13.

`harness/picaros_guide.py`: `next_buy(ref, V-1, theirs, ours)` y `next_sell(rarity, V+1, theirs, ours)`; `theirs` = [(precio, final, trick(topic, offer))].
Reglas: ancla 45 · +1 · al llegar a su oferta honesta − 2, pedir eso · aceptar solo oferta honesta ≤ nuestro siguiente y ≤ V − 1 · nunca truco · su `final` no cierra nada.
