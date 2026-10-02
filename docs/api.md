# Notas de API

Lo que el README del SDK no dice y hemos visto en respuestas reales. La referencia de métodos está en las docstrings de `bazaar_sdk.py`.

## Sin clave (lectura pública, 60 req/s)
| Método SDK | Ruta | Útil para |
|---|---|---|
| `clock()` | `/api/clock` | tick, `next_tick_in`, `doors`, `limits` en vigor, calendario |
| `schedule()` | `/api/schedule` | próximos duelos y Market Tests (`at_hours` en horas de juego) |
| `dealers()` / `dealer(id)` | `/api/dealers` | `traits`, `unlock`, `menu.sells[]` (`opening_ask`, `list_price`, `per_team_per_hour`), `menu.buys` |
| `levels()` | `/api/levels` | niveles anunciados o activos (vacío al empezar) |
| `catalog()` | `/api/catalog` | rarezas (valor de catálogo), sets y cartas, `packs[].expected_book` |
| `feed(limit)` | `/api/feed` | **los regateos públicos de todos** (ver `scout.py`) |
| `leaderboard()` | `/api/leaderboard` | puntuación, nivel, tratos y álbum por equipo |
| `venues()` / `board(v)` | `/api/venues` | mercados y ofertas publicadas |

## Formas observadas
- **Oferta** (en un hilo o en el feed): `{id, maker, to, venue, thread, status, give: {cash, assets, types}, want: {cash, assets, types}, expires_tick, created_tick, final}`.
  - Cuando el vendedor vende: `want.cash` es su precio.
  - Cuando nos compra: `give.cash` es lo que paga.
- **Hilo** (`thread(id)`): `status` ∈ open/deal/walked/closed/cooloff, `closed_reason`, `standing_offers[]`, mensajes.
- **Evento del feed**: `{id, tick, t, type, scope, actor, payload}`. Tipos: `thread.opened` (payload `team, with, topic, thread`), `thread.message` (`sender, text, offer`), `settlement` (`parties, persona, items, fee`), `offer.listed`, `pack.opened`, `gift.given`, `clock.changed`, `announcement`, `schedule.fired`.
- **Leaderboard**: `teams[]` con `score, negotiating, market, level, album_filled, pages_complete, luck, deals, rank`.

## Pendiente de verificar con clave
- La forma completa de `me()` (`score`, `album`, `starter_broker_key`).
- El `status` de una oferta aceptada dentro de `thread().standing_offers`. `haggle.py` asume `"accepted"` y, si no coincide, el precio queda como `None`.
