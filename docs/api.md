# API: lo que sabemos (verificado con llamadas reales, vie 2 oct, tick 30)

Spec completa: **`GET /openapi.json`** (copia en [openapi.json](openapi.json)). UI interactiva en `/docs` y `/redoc`.
Los métodos del SDK están documentados en las docstrings de `bazaar_sdk.py`. Aquí va lo que **no** está en el README.

## ⛔ Prohibido
Las rutas `/api/admin/*` (X-Admin-Token) son de los organizadores. **No se llaman nunca**, ni para probar: sería juego sucio y motivo de sanción.

## Rutas de equipo (todas las que existen)
| Lectura | Escritura |
|---|---|
| `GET /api/me` · `/api/me/value?card=` · `/api/me/threads?status=` · `/api/me/offers` | `POST /api/threads` · `/api/threads/{id}/messages` · `/api/threads/{id}/close` |
| `GET /api/threads/{id}` (solo los nuestros: `403 not_your_thread`) | `POST /api/offers` · `DELETE /api/offers/{id}` · `POST /api/offers/{id}/accept` |
| `GET /api/cards/{asset_id}` (procedencia de cualquier carta o sobre) | `POST /api/packs/{id}/open` · `POST /api/flags` |
| `GET /api/duels?done=` | `POST /api/duels/{id}/messages` · `/api/duels/{id}/accept` |
| `GET /api/events/stream?scope=team` (SSE, máx. 6 por clave) | `POST /api/venues` · `PATCH /api/venues/{id}` · `POST /api/venues/{id}/close` |
| Broker (X-Broker-Key): `GET /api/broker/book` | `POST /api/broker/matches` · `/api/broker/announce` |

Cuerpos (OpenAPI): `PostMessage {text, price?, days?, offer?, topic?}` (vale para hilos y duelos) · `NewOffer {venue?, to?, give, want, expires_in_ticks=40}` · `OpenThread {with, topic?, venue?}` · `NewVenue {name, fee_bps=300, fee_per_card=0, rules, description}`.

## `GET /api/me`: el centro de todo
- `cash`, `level`, `unlocked`, `venue`, `open_threads`, `tick`, `tick_seconds`.
- **`affinity`: nuestros multiplicadores privados por set.** Para t18: **CHA 1,6 · RET 1,3 · SAL 1,1 · LAT 0,9 · LAV 0,7 · MAL 0,5**.
- `assets[]`: `{id, kind, ref, serial, rarity, set, print_run, name, your_value}`. **`your_value` es el valor marginal de *esa* copia**: la 1.ª copia vale catálogo × affinity, la 2.ª el 25 % y la 3.ª el 10 %.
- `album.pages[]`: `{set, have, of: 10, complete, master}`. `collection_value` es el valor total de lo que tenemos.
- **`score`**: `score, negotiating, market, neg_points, mm_points, duel_points, ladder_points, bench_efficiency, bench_points, bench_venue, deals, luck, luck_private, rank, adjustments, frozen`. Es el **único sitio con el desglose**. `run_dealer.py` lo guarda antes y después de cada trato.
- `GET /api/me/value?card=X` = valor de **una copia más** (por ejemplo SAL-02 = 11, SAL-10 = 77, SAL-12 = 495, CHA-01 = 16).

## Hilos y ofertas
- Hilo: `{id, kind: "persona", team, with, venue, topic, status, created_tick, messages[], standing_offers[], item, closed_reason}`.
- `status`: open → deal | closed | walked | cooloff. **Al cerrar, `standing_offers` queda vacío**: las ofertas viven en `messages[].offer`.
- Estados de una oferta: `open`, **`settled`** (trato cerrado), `cancelled`. Caducan en 2 ticks (`expires_tick`).
- Forma de una oferta: `{id, maker, to, venue, thread, status, give: {cash, assets[], types[]}, want: {...}, expires_tick, created_tick, final}`.
  - La Abuela vendiendo: `give.types = ["pack:sobre_barrio"]` o `["card:SAL-02"]` y `want.cash` = su precio.
  - La Abuela comprando: `give.cash` = lo que paga y `want.assets = [{id, kind, ref, ...}]`.
  - `agent/haggle.offer_ok()` comprueba esta estructura antes de aceptar; todas las ofertas reales del feed la pasan.
- **`expires_in_ticks` se cuenta en unidades de 15 s**: con ticks de 60 s, pedir 120 da 30 ticks reales, 60 da 15 y 240 da 60 (medido, ticks 51, 68 y 69). Con ticks de 30 s se divide entre 2; **desde el sáb 3 oct el tick vuelve a 60 s** (pedido 240 → 60 ticks reales). `market.expiry()` lo compensa. Las ofertas en El Rastro caducan a los 40 ticks si no se dice otra cosa (en la práctica, 30): las 5 del starter ya no están (`/api/me/offers` vacío).
- Topics con vendedores: `{"buy": {"pack"|"card": id}}`, `{"buy": {"rarity", "set"}}`, `{"sell": {"assets": [ids]}}`.

## Públicas (sin clave)
- `catalog.values`: `copy_marginals [1.0, 0.25, 0.1]`, `page_bonus 0.25`, `master_bonus 0.1`. `packs[].slots` con probabilidades. `sets[].cards[]` con `page` (comunes, infrecuentes y raras) y `hidden`. La épica (-11) y la legendaria (-12) no forman parte de la página.
- `schedule.upcoming[]`: `at_hours` cuenta **horas de juego** (ticks × tick_seconds). Viernes de 0 a 4, sábado de 4 a 18, domingo de 18 a 24.
- `leaderboard`: equipos con `score, negotiating, market, level, album_filled, pages_complete, luck, deals`. Se refresca cada 5 ticks.
- `dealers`: `traits`, `unlock {always, early_deals_with, early_min_deals: 3, ...}`, `menu.sells/buys`, `deals_per_team_per_hour`.
- **`feed`: tope de 500 eventos** (`limit` mayor no da más). Para conservar el historial: `python3 scout.py abuela --save` → `logs/feed.jsonl`, que solo añade los eventos nuevos.
- `cards/{id}`: `history[{tick, from, to, why}]`. Por ejemplo, un sobre abierto pasa a `owner: "burned"`.

## Seudónimos
El tablón (`/api/venues/rastro/offers`) muestra a quien publica con un seudónimo (`mf60b788f`), **pero el evento `offer.listed` del feed lleva el id real** (`maker: "t13"`). Para desanonimizar: cruzar el id de la oferta con el feed. Así supimos que `mf60b788f` = t13.

## Quién tiene qué
`leaderboard.teams[].rarest` = la carta más rara de cada equipo (`ref`, `serial`). `catalog...cards[].minted` = cuántas copias existen. Ejemplo: SAL-10 tiene 4 copias; t17 (n.º 4), t12 (n.º 3) y t02 (n.º 1) la muestran.

## Errores vistos
`{"error": code, "message"}`: `not_your_thread` (403), `wait_for_tick`, `rate_limited`, `persona_quota` ("you bought enough of these this hour; come back later"), `insufficient_cash`, `cooloff`, `locked`, `self_venue`, `venue_not_live`, `bad_key`, `too_many_failures`.

## Herramientas nuestras
- `python3 probe.py [--public]`: foto de todos los GET (nunca los de admin) en `logs/probe/<tick>/`, con su forma.
- `python3 scout.py <dealer> [--save]`: regateos públicos con un vendedor, y opcionalmente graba el feed.
- `agent/client.py`: `client()` lee `.env` (`BAZAAR_KEY`, `BAZAAR_URL`).
