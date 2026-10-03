# Domingo 4 oct: gastar toda la caja en tratos que puntúan, y market-making

*Analista (Persona 2), sáb 3 oct 22:30, tick ~1378. Fuentes: deck oficial «The Bazaar · Payday»
(sáb noche), [RULES.md](../RULES.md), [knowledge.md](knowledge.md), `state/equipo.json` (tick 1374),
GET públicos sin clave (`/api/clock`, `/api/schedule`, `/api/dealers`, `/api/catalog`, `/api/leaderboard`,
`/api/venues`, `/api/feed`) y `logs/feed.jsonl`. Etiquetas: `[oficial]`, `[medido]`, `[inferido]`.
Lo aplica el operador; nada de esto se arma solo.*

**Resumen (seis líneas):**
1. 09:00, bloqueante: re-anclar `day_end_hours.sun` y `closer.endgame_hours.sun` al reloj real (hoy apuntan a t = 21,x y el domingo acaba en t ≈ 19,37).
2. Repetidas a Pilar por encima de V: SAL-10 #2 ≥ 60, RET-07 #2 y LAT-06 #2 → +≈120 P y 3 huecos del nivel 3.
3. CHA: raras a los Pícaros (48–64) en vez de a El Chato (tope 100), y la carta de cierre a un equipo (≤ 72 → +50). ≈ 290 P.
4. Resto (≈ 440 P): primero compras a equipos con +50 (RET-11 ≤ 180 a t05/t06, raras CHA de sobre ≤ 62); luego una épica a los Pícaros y una legendaria a Don Ernesto (CHA-12 o SAL-12, ≤ 480). Nunca sobres. A las 14:00–14:50, vaciar la caja solo en tratos con ganancia.
5. Market-making: v18 auto 0/0 abierto todo el día, sin board (ningún board supera al auto en el banco). Los puntos extra salen de **tratos que cierran página entre otros dos equipos en v18**: emparejar como t10, vía la Lonja si la organización autoriza v18.
6. Duelos III y Final: cerrar siempre; sin trato = 0.

---

## 0. La regla que lo decide todo `[oficial, deck p. 7]`

> **ONLY DEALS SCORE.** Un trato = valor que añade a tu colección − precio pagado + precio recibido.

| Con quién | Si ganas | Si pierdes |
|---|---|---|
| **Equipo** | cuenta **hasta 50** por trato | cuenta entera |
| **Dealer** | cuenta **solo en la escalera** (3 mejores por dealer; los altos pesan más) | cuenta entera |
| Dealer → dealer (comprar a uno, vender a otro) | comprar no da nada | vender por debajo de V resta (un equipo perdió 189 con una épica Pícaros → Pilar) |
| **Lo que tienes** (caja, cartas, álbum) | **0** por sí solo | — |

La última carta de una página: **comprarla a un equipo = +50**. Revenderla rompe la página: +50 − 130 = **−80**.

Consecuencias para mañana:
1. **La caja a las 15:00 vale 0**, y una carta en el álbum tampoco puntúa por sí sola. Solo puntúa *el trato* que la trajo.
2. Con dealers, la ganancia **no** suma a negociación: solo llena un hueco de escalera. Por eso no importa *cuánto* ganas con un dealer, sino **qué parte de su rango de precio capturas** y **en qué nivel** (Ernesto 5 > Pícaros 4 > Pilar 3 > Chato 2 > Abuela 1).
3. Con equipos, cada trato vale como mucho +50 → el mejor uso de P es **muchas compras a equipos con ganancia ≈ 50**, no una gran compra.
4. Nunca vender por debajo de V; nunca vender una copia única de página.

---

## 1. Caja disponible

| Concepto | P | Etiqueta |
|---|---:|---|
| Caja tick 1374 (tras +400 primas) | 459 | `[medido]` equipo.json |
| +150 del domingo | 150 | `[oficial]` deck p. 4 |
| Repetidas vendidas a Pilar por encima de V (§3, paso 1) | ≈ +120 | `[inferido]` precios de Pilar del sábado |
| **Total** | **≈ 730** | |

## 2. Lo que dicen los precios reales `[medido]`, feed t1083–t1379

| Dealer | Qué | Precios cerrados |
|---|---|---|
| Los Pícaros (nivel 4) | raras | **48–64** (mediana ≈ 56) |
| Los Pícaros | épicas | **128–155** (SAL-11 nuestra a 139; RET-11 a 128 y 137) |
| Doña Pilar (nivel 3) | compra SAL-09/10 | **67–86** |
| Doña Pilar | compra SAL-11 | 179–195 (con fiebre) |
| Don Ernesto (nivel 5) | compra épicas | **116–120** (por debajo de catálogo: no venderle) |
| Don Ernesto | vende | sobre de oro (lista 420, deck: ≈ 380), legendaria (lista 585, deck: **≈ 470** «para el negociador paciente»). **0 legendarias acuñadas** en todo el juego |

Valor para nosotros (1.ª copia, ×CHA 1,6 · RET 1,3 · SAL 1,1 · LAT 0,9 · LAV 0,7 · MAL 0,5):
rara CHA 112 · épica CHA 288 · **legendaria CHA 720** · épica RET 234 · legendaria SAL 495 (+ master ≈ 0,1 × set, porque ya tenemos página SAL y SAL-11) · épica LAT 162.

---

## 3. Plan del domingo, en orden

### 3.0 · 08:50 — antes de nada (bloqueante)

- **El reloj se ha movido.** `/api/schedule` (22:25) dice: Saturday cierra en **t = 13,367**, el domingo abre en t = 13,367 y cierra en **t = 19,367** (15:00). Pero el calendario aún pone «Round 3 / CHA / +150» en t = 16,65–16,7 y los dealers cierran en t = 21,65, *después* del cierre. Los organizadores probablemente lo re-anclen al abrir (CHA está anclada a «sun+0h»); el deck dice 09:00 para +150 y ronda nueva.
- `config/plan.json` usa el reloj viejo: `day_end_hours.sun = 21.5667` y `closer.endgame_hours.sun = 21.0`. **Con el reloj nuevo nunca se alcanzarían**: el cierre de CHA no subiría la puja y la higiene no cerraría hilos (`agent/tactics/pages.py:256-261`, `hygiene.py:268`).
  → Con `python3 bazaar.py clockcheck` a las 09:00: `day_end_hours.sun = t(14:55)` y `closer.endgame_hours.sun = t(13:20)` del reloj real (si abre en t = 13,367 a 09:00: **19,283** y **17,7**).
- Si CHA no sale hasta las ~12:17 (calendario sin re-anclar), la ventana de CHA es 12:17–14:55: §3.1 y las compras de §3.3 A sin CHA van primero, por la mañana.
- Leer `/api/me` **antes del primer trato**: `ladder_points` y los huecos por dealer. Si se reiniciaron con la ronda 3, todos los huecos del domingo están vacíos y cada trato con ganancia con cada dealer cuenta. Si no, un trato nuevo solo ayuda si supera al peor de sus 3 huecos.

### 3.1 · 09:00–09:30 — vender repetidas a Doña Pilar (nivel 3, caja + escalera)

| Repetida | V para nosotros | Pilar pagó | Suelo |
|---|---:|---:|---:|
| SAL-10 #2 (rara) | 19,2 | 75–80 por SAL-10 | **≥ 60** |
| RET-07 #2 (infrecuente) | 8,1 | — | ≥ 20 |
| LAT-06 #2 (infrecuente) | 5,6 | — | ≥ 18 |

Tres tratos con ganancia a nivel 3 = sus 3 huecos y ≈ +120 P. Comunes repetidas (LAT-02, SAL-05): a Pícaros o Abuela solo si llenan un hueco vacío. **Nunca** copias únicas de página ni SAL-11 por debajo de 199. Manual, por la Gate, como en [pilar.md](pilar.md).

### 3.2 · Al publicarse CHA — completar CHA con dealers baratos, cerrar con un equipo

- **Raras CHA-09/10 a Los Pícaros, no a El Chato.** Pícaros cierran raras a 48–64; el perfil actual `CHA:rare` va a El Chato con tope 100. Cambio propuesto en `profiles`:
  `"CHA:rare": {"dealer": "picaros", "anchor": 45, "step": 3, "limit": 66, "fallback_after": 12, "fallback_dealer": "chato"}`
  (respaldo El Chato con su perfil actual si los Pícaros no venden CHA). Ahorra ≈ 70 P y llena huecos del nivel 4 en vez del 2.
- Infrecuentes y comunes a la Abuela con los topes actuales (nivel 1, sin pérdida).
- **La carta que cierra la página, a un equipo** (vale ≈ 122): puja en El Rastro a ≤ 72 → **+50**. Comprada a un dealer daría 0.
- Coste estimado: 2 × 56 + 3 × 22 + 4 × 10 + 72 ≈ **290 P**. Quedan ≈ **440 P**.

### 3.3 · Después de CHA — el resto de la caja, por puntos por P

**A. Compras a equipos con ganancia ≈ +50 (lo mejor por P).** Pujas en pie en El Rastro, siempre `V − precio − comisión ≥ 50` (o ≥ 3 en la última hora):

| Qué | V | Pujar hasta | Quién la tiene |
|---|---:|---:|---|
| Cualquier rara CHA que un equipo saque de sobre (nos falte o no) | 112 / 28 repetida | 62 si nos falta | quien tenga CHA ×0,5–0,9 |
| RET-11 (épica, solo 2 acuñadas) | 234 | **≤ 180** (ya en `dealer_needs`) | t05 (pagó 128), t06 (137) |
| CHA-11 si un equipo la saca | 288 | ≤ 235 | — |
| LAT-11 | 162 | ≤ 110 | — |

Un mensaje en hilo (¡no promesas de texto!) a t05 y t06 por RET-11: a 150–180 ganan ellos (si su RET es ≤ ×1,0) y ganamos +50. Es el tipo de trato que suma a los dos.

**B. Escalera de nivel 4 y 5 (lo que el deck señala con las +400).**
1. **Pícaros:** CHA-09 + CHA-10 + **una épica** (RET-11 a ≤ 180 si no llega de un equipo; o CHA-11 a ≈ 140–150, V 288) = 3 huecos del nivel 4.
2. **Don Ernesto, una legendaria (nivel 5, el que más pesa).** Solo una de: **CHA-12 (V 720)** si la vende tras publicarse CHA, o **SAL-12 (V ≈ 495 + master)**. Paciencia: abrir bajo (≈ 400), pasos pequeños y nunca repetir precio (paciencia 0,95, generosidad 0,1, memoria 1,0, rigor 1,0: **ningún truco**, y no abrir hilos que vayamos a abandonar). Tope **≤ 480**. Una legendaria por equipo y hora.
   **No** comprar el sobre de oro: lo que sale es suerte (no puntúa) y su valor esperado para nosotros, con tantas repetidas, queda por debajo de 380 → pérdida entera.
3. Si la caja no da para A + B: **primero A** (+50 seguros por trato), luego B.1, luego B.2.

**C. 14:00–14:50 — vaciar la caja.** Comprar a equipos toda oferta con `V − precio − comisión ≥ 3`, de mayor a menor ganancia. A dealers, solo si es ganancia y llena o mejora un hueco. **Nunca** comprar por debajo de cero «para gastar»: una pérdida cuenta entera; la caja sobrante solo vale 0.

### 3.4 · Duelos III (11:00) y Gran Final (14:00)

El deck: «4 de cada 10 duelos acabaron sin trato. Sin trato = 0. Una parte pequeña gana a nada». Cerrar siempre dentro del límite antes del último tick; ceder el día que nos importa poco a cambio de precio.

---

## 4. Market-making (30 puntos)

### 4.1 Cómo se reparte `[oficial, deck p. 5 y 9]`

- **Market Test ≈ 22,5:** todos los venues reciben el mismo libro sintético; puntúa la parte de las ganancias posibles que realizas. Igualar al puesto auto gratuito = mitad; puntos completos = media del top 3.
- **Tratos reales ≈ 7,5:** «el valor que **dos otros equipos** crean en tu mercado». Volumen, comisiones y «amigos» = 0.
- Pistas del deck para dueños de mercado: **encontrar la carta que falta** (cruzar listas de deseos con quien tiene repetidas), **trueque sin caja** (comisión 0; El Rastro cobra 5 % + 1 P/carta) y **terminar páginas** (la última carta de una página es el mejor trato del juego).

### 4.2 Quién lidera y cómo `[medido, GET públicos, 22:25–22:51, sesión 6 en vivo]`

| Equipo | Venue | Tratos | Mercado | Cómo |
|---|---|---:|---:|---|
| t10 | v07 board, 0/0 | 11 | **12,50** | ~48 anuncios de emparejamiento **con nombre**: «t18, publica MAL-05 aquí a 3… t06 puja 2»; «t09 vende a 8 en El Rastro (el comprador paga 9,4): publícalo en v07». t06 es parte en 6 de 10 |
| t06 | v01 board, 0/0 | 3 | 11,87 | SAL-10 (rara) t12→t08 a 76: carta de página |
| t09 | v21 board | 6 | 10,89 | — |
| **t16** | **v16 puesto auto gratuito** | **2** | **10,16** | LAT-08 y **SAL-09 (rara, 70 P) t12→t09**: compras que cierran página. Subió de 7,50 a 10,16 **sin broker ni anuncios** |
| t14, t17 | puestos auto | 1 | 9,30 / 8,64 | una venta de página cada uno |
| t18 y otros 7 | sin tratos | 0 | **7,50** | — |
| t12 | v02 board | 11 | 12,50 → **7,25** | Volcados de comunes de página a 6–11 P «destruyeron valor» (su propio aviso, t938); subió comisión a 5 P/carta y cayó más |
| t13, t03 | boards | 0 | 6,77 / 6,08 | **peor que el puesto auto** |

`[inferido, encaja con todos los números]` Marcador ≈ (0,5 × viernes 0 + 1 × sábado) / 1,5. Sábado base = 11,25 (mitad del banco) → 7,50 en pantalla. 12,50 en pantalla = 18,75 = 11,25 + **7,5 de tratos reales (tope)**.

**Conclusiones:**
1. **Nadie gana al puesto auto en el Market Test.** Los boards empatan (7,50) o pierden (t13, t03, t12 con comisión). Las ganancias del banco son Σ(límite comprador − límite vendedor) de los pares casados. El auto ya casa la mejor puja con la mejor oferta en cada tick, y eso es óptimo en cada tick. El libro del banco no es público (`bench_offers` solo con la clave del broker).
2. **Toda la ventaja viene de los tratos reales entre otros dos equipos**, medidos a *sus* valores. Dos tratos que cierran página bastaron a t16 (+2,66 en pantalla ≈ +4 en la ronda).
3. **El valor puede ser negativo:** volcar cartas de página baratas en tu venue resta (t12).

### 4.3 Qué hacemos

| # | Jugada | Coste | Ganancia esperada |
|---|---|---|---|
| M1 | **Mantener v18 tal cual:** auto, 0 bps, 0 P/carta, abierto todo el domingo. **No abrir un board** (270 P de fianza+alta que hacen falta para tratos; ningún board supera al auto en el banco) | 0 | Mitad del banco asegurada en cada sesión (≈ 11,25 de ronda) |
| M2 | **Emparejamiento hacia v18, como t10:** cruzar pujas `want card:X` de El Rastro con quien tiene repetidas de X. Prioridad: **cartas que cierran página** y CHA (el domingo todos buscan CHA y quien tenga CHA ×0,5 sacará repetidas de sobres). Mensaje tipo: «t09 busca SAL-09; tú tienes una repetida. Publícala en v18 a P, comisión 0: el comprador se ahorra 5 % + 1 P» | 0 P | Hasta los 7,5 de tratos reales de la ronda (≈ +3 en el total, porque el domingo pesa 40 %) |
| M3 | **La Lonja como canal de M2.** `foro-agentes.md` excluye v18 del ruteo por neutralidad (R-05) salvo autorización escrita. **Pedirla a la organización a las 09:00**, con el algoritmo público: v18 entraría en el ruteo neutral como cualquier venue auto con 0/0. t10 ya enruta a su venue a la vista de todos, y el deck lo recomienda («Take want-lists and match them…») | 0 | Multiplica M2 sin trabajo manual |
| M4 | **No dar flujo a venues rivales:** nuestras compras de equipo, en El Rastro o en venues de equipos por detrás. D2 ya lo hace (`RIVAL_TOP_N`) | — | No regalar puntos a t10/t06 |

**Límites de M2** (no se rompen):
- La Gate no tiene `announce` ni mensajes a equipos (`KINDS` en `agent/contracts.py:120`, congelado), y `POST /api/broker/announce` necesita la clave del broker. Antes de nada, el operador mira si `/api/me` trae `starter_broker_key`. **Escribir anuncios fuera de la Gate es decisión del lead**: si no hay luz verde, M2 va solo por la Lonja (M3), que es fuera del juego y sin claves.
- Nunca proponer tratos que vuelquen cartas de página por debajo de su valor (t12). Solo pares en los que ganan los dos: el comprador cierra página o completa una carta que le falta, y el vendedor suelta una repetida.
- Nunca proponer a otro equipo una carta CHA que nos falte a nosotros.

### 4.4 Sesiones del Market Test que quedan `[calendario público, 22:25]`

Si no se re-ancla: ~10:17 (**difícil**, 12 traders), ~10:38, ~12:38, ~14:38; ronda 3, CHA y +150 en t = 16,65 ≈ **12:17**. En ese caso las dos sesiones de la mañana y todo lo anterior a las 12:17 cuentan para la ronda del sábado. El deck dice 09:00: **lo decide `/api/schedule` a las 09:00** (§3.0). En ambos casos basta con tener v18 abierto en cada sesión, y cada trato real en v18 suma a la ronda en curso.

---

## 5. No hacer

- Vender una copia única de página (−80 la que cierra), ni SAL-11 por debajo de V.
- Comprar a un dealer para revender a otro dealer.
- Comprar sobres (plata/oro/barrio): suerte = 0, el precio por encima de su valor esperado resta.
- Gastar en épicas solo porque «suben la colección»: la colección no puntúa, solo el trato.
- Dejar caja a las 15:00, o gastarla con pérdida.
