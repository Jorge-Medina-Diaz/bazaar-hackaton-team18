# Domingo 4 oct: registro de escrituras manuales y decisiones

Regla de CLAUDE.md: las escrituras fuera de la Gate necesitan el OK explícito de Jorge, se hacen una vez y quedan apuntadas aquí. Son las denuncias (`flag_one.py`) y los anuncios del puesto v18 (`announce_stall.py`); ninguno de los dos scripts mira STOP ni escribe en el diario. Las órdenes `bazaar.py do --live` (con `ladder_sell.py` y `egg_carrier.py`) ya quedan en `logs/run/journal.jsonl`, pero también conviene apuntarlas aquí con su motivo.

Plan del día: [../plan-domingo.md](../plan-domingo.md).

| Hora | Quién dio el OK | Qué (ruta o comando) | Id (mensaje, hilo, oferta) | Respuesta del servidor | Efecto medido (neg_points, insignia, venue.trades…) |
|---|---|---|---|---|---|
| | | | | | |

## Denuncias del domingo (ronda 3), con el OK de Jorge
- ~09:35, ticks ~1505–1510, `flag_one.py`, las tres de nivel A de `flag_candidates.py`:
  - 12965 (hilo 2250, tema CHA-10, la oferta da CHA-06): `{"flagged": true}`, neg_points 27 → 37.
  - 13095 (hilo 2277, tema RET-11, la oferta da RET-10): `{"flagged": true}`.
  - 13121 (hilo 2277, tema RET-11, la oferta da RET-09): `{"flagged": true}`. Con las dos, neg_points 37 → 57.
- Conclusión: el tope de 3 denuncias que puntúan es **por ronda** (el sábado ya se usaron 3).
