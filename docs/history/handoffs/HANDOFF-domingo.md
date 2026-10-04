# Domingo 4 oct: registro de escrituras manuales y decisiones

Regla de CLAUDE.md: las escrituras fuera de la Gate necesitan el OK explícito de Jorge, se hacen una vez y quedan apuntadas aquí. Son las denuncias (`flag_one.py`) y los anuncios del puesto v18 (`announce_stall.py`); ninguno de los dos scripts mira STOP ni escribe en el diario. Las órdenes `bazaar.py do --live` (con `ladder_sell.py` y `egg_carrier.py`) ya quedan en `logs/run/journal.jsonl`, pero también conviene apuntarlas aquí con su motivo.

Plan del día: [../plan-domingo.md](../plan-domingo.md). Trazas: [data/](../../../data/README.md).

| Hora | Quién dio el OK | Qué (ruta o comando) | Id (mensaje, hilo, oferta) | Respuesta del servidor | Efecto medido (neg_points, insignia, venue.trades…) |
|---|---|---|---|---|---|
| ~09:23 | Jorge (en el chat) | `announce_stall.py`: «Chamberí is out! … v18: 0 % fee…» (`POST /api/broker/announce`, clave del puesto) | v18 | 200 `{"ok":true}` | ninguno medible |
| ~09:31 | Jorge | `announce_stall.py`: repetidas de CHA a v18 | v18 | 200 | ninguno medible |
| 09:30 | Jorge | `flag_one.py` ×3 (`POST /api/flags`) | 12965, 13095, 13121 | `{"flagged": true}` ×3 | neg_points 27 → 57 (ver abajo) |
| 09:46–12:02 | Jorge («sigamos incentivando la venue») | anunciador cada 10 min (`POST /api/broker/announce`): demanda real de El Rastro con parejas | v18, después v28 | 12 × 200, 3 × 429 «one announcement per venue every 20 ticks» | `data/market-test/announcements.txt`; 0 tratos de otros equipos en nuestro venue |
| 10:09 | Jorge («HAZLO») | `venue_broker.py open`: `POST /api/venues` (board, 0 %, 0 P/carta), fianza 250 + 20 | venue v28 | ok, clave de broker guardada fuera de Git | caja 357 → 87; bench_venue v28 |
| 10:09–… | Jorge | `venue_broker.py run`: `GET /api/broker/book` por tick + `POST /api/broker/matches` | v28 | 11 cruces aceptados (10:16–10:40), 2 errores `BazaarError` (11:37, 11:54) | test difícil: bench_points 0,5, bench_efficiency 0,967 (`/api/me`, 10:20); `data/market-test/v28-broker.jsonl` |
| ~10:24 | Jorge | anuncio dirigido de parejas CHA (t16 y t09 pujan; t1, t15, t8, t2 tienen repetidas) | v28 | 200 | ninguno medible |

## Denuncias del domingo (ronda 3), con el OK de Jorge
- ~09:35, ticks ~1505–1510, `flag_one.py`, las tres de nivel A de `flag_candidates.py`:
  - 12965 (hilo 2250, tema CHA-10, la oferta da CHA-06): `{"flagged": true}`, neg_points 27 → 37.
  - 13095 (hilo 2277, tema RET-11, la oferta da RET-10): `{"flagged": true}`.
  - 13121 (hilo 2277, tema RET-11, la oferta da RET-09): `{"flagged": true}`. Con las dos, neg_points 37 → 57.
- Conclusión: el tope de 3 denuncias que puntúan es **por ronda** (el sábado ya se usaron 3).

## Notas
- Los scripts `flag_one.py`, `announce_stall.py`, el anunciador y `venue_broker.py` corrieron desde el scratchpad de la sesión del operador: no están en el repo, no miran STOP ni escriben en el diario. Por eso se apuntan aquí; sus salidas están en `data/market-test/`.
- La venta de SAL-11 (09:27, +27), las de LAT-06 a Pilar y las pruebas de huevos fueron órdenes `bazaar.py do --live` (`ladder_sell.py`, `egg_carrier.py`): pasan por la Gate y están en `data/journal.jsonl`.
