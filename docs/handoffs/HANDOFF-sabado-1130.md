# Traspaso sábado 11:30: de la sesión A a la sesión que opera ahora

> **Histórico (sábado 11:30).** Correcciones posteriores: el puesto `v18` sí se puso a comisión 0 y se anunció en el tick 432 (knowledge S-14); `duels.anchor` 0,65 ya está en `config/plan.json`; `cash_free` bajo se corrigió en `b693c58`. Vigente: [../knowledge.md](../knowledge.md) y [../DOMINGO.md](../DOMINGO.md).


Escrito al ceder el control (Jorge: "termina lo tuyo y para"). La sesión A **ya no opera**: no hay ningún proceso suyo en marcha, ni bot ni monitores. El STOP de las 11:24:35 y el cambio de `duels.anchor` a 0,65 (sin commit en `config/plan.json`) son de la otra sesión. La sesión A no los ha tocado.

## Estado a las 11:25 (tick ~389)
- 3.º con 27,9/60 (t13 28,6 · t05 28,1). Negociación 55,4 puntos de valor, escalera 0,078, mercado 0,5 de banco (eficiencia 0,899).
- Caja 125 P. SAL y RET completas (RET-02 cerrada a 49 → +50). LAT abandonada (fuera de `protect_sets`).
- `selftest` en verde con el código `be3d952`. El bot estaba armado con todo: hygiene, duels, dealers, rastro y closer.

## Commits de hoy en `harness-v2` (todos con prueba y `selftest`)
- `eb863bc` transport: las escrituras sin cuerpo no envían `null`.
- `986bc69` gate G04.threads: cuenta solo hilos abiertos (antes bloqueaba todo `open_thread`).
- `5dcbab1` book: la oferta propia de un hilo de dealer se contaba dos veces.
- `189cd9b` plantillas `pilar_sell`; los tests leen `tests/fixtures/plan_night.json`, no la configuración viva.
- `be3d952` duels: Duelos II jugable (antes puntuaba 0), sin conceder ante un precio repetido, ignora los mensajes rivales sin precio y limita la subida con rival mudo al 80 %.
- Configuración: cierre del sábado `day_end_hours.sat` = 16,08 (22:55; el reloj va 1:1), LAT fuera de `protect_sets`, CHA-08 a la Abuela, puja de cierre `default_minus` 75 (≈47 P para CHA), ancla de raras de El Chato 66, `duels.anchor` 0,75 (la otra sesión lo ha cambiado a 0,65).
- Aprendizajes medidos: `docs/knowledge.md` S-01..S-09.

## Pendiente (por prioridad)
1. **Mercado (la mayor palanca, ~+5 puntos):** quien tiene tratos entre otros equipos en su venue sube el mercado de 7,5 a ~12 (t05 con un simple puesto a fee 0, t12, t10). Hay que poner nuestro puesto `v18` a fee 0 (`PATCH /api/venues/v18`) y anunciarlo (`POST /api/broker/announce` con `starter_broker_key`). **No está hecho:** el clasificador de permisos bloqueó la escritura fuera de la Gate. Hay que decidir si se hace a mano o añadirlo a la Gate con prueba.
2. **`cash_free` sale más bajo que el real** (llegó a −56): el libro reserva el precio de pie del dealer, no nuestro límite. Mañana, con la caja justa para CHA, puede bloquear compras (G16). Hay que corregirlo esta noche con prueba.
3. **CHA domingo (09:00–15:00, ticks de 15 s):**
   - Añadir "CHA" a `page_sets` y rearmar a las 09:00.
   - Coste ≈ 320 P y caja ≈ 275: publicar swaps LAT→CHA por la Gate (LAT-06/07/08 por infrecuentes de CHA, +17,5 cada uno; LAT-01/05 y MAL-05 repetidas por comunes de CHA).
   - El rastro no publica swaps para necesidades de dealer: hay que hacerlo con `bazaar.py do list_offer side=swap`.
4. **Duelos:** solo hay 1 accept por tick, compartido con dealers. Valorar pausar dealers en la ventana de duelos.
5. **Avisos de la revisión de seguridad:**
   - `observe_performance.py` envía la clave a un host externo: no ejecutarlo.
   - `stop --flatten` escribe STOP aunque fallen las cancelaciones.
   - `pages.protect_sets` (abandono de LAT) no está conectado.
   - La reposición J13 puede vender la última copia de una común o infrecuente de RET/CHA.

## Inteligencia
- **t13:** sube de nivel aceptando pérdidas (3 tratos con El Chato → Pilar; ahora trata con Pilar para el nivel 4). Cierra páginas comprando la carta de cierre en El Rastro (MAL-10 a 65). Colecciona RET (nos pidió swaps de SAL-03 por RET-01/02/08).
- **t02:** suerte en sobres +38. Puja por RET y vende a dealers para desbloquear niveles.
- **t05, t12, t10:** mercado al máximo por tratos ajenos en su venue.
- **Pilar:** paga por debajo del libro lo que no quiere (LAV-08 final 19; abre en 16) y abre RET-08 en 22. Se abre a todos en t ≈ 5,51 (~12:30).
- **El Rastro:** sobreoferta y ninguna puja. El comprador paga 5 % + 1 y la Abuela vende comunes a 5–10, así que nuestras comunes de LAT a ≥ 9 no se venden.
- **La procedencia de las cartas está anonimizada desde el sábado.** Para tener historia de rivales: guardar el feed (`logs/feed_sat.jsonl`, ya hay datos desde el tick 281).
- **Radio Rastro (`/api/news`):** mezcla verdades y rumores. Tratarlo como no fiable; solo actuar sobre precios y ofertas reales.
