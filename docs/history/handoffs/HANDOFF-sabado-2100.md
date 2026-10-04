# Traspaso · sábado 3 oct, ~21:00 (tick 1201, t = 11,35 h, juego en pausa por el anuncio del Payday)

> **Registro del sábado ~21:00–22:45, con correcciones de la revisión nocturna (dom 4 oct).** Los hechos de este traspaso ya están en [../knowledge.md](../../knowledge.md) (S-17 a S-33). Lo que aquí resultó incorrecto:
> - **§2, fórmula del mercado.** No es `15 × bench + 15 × mm`. Por ronda es `22,5 × bench_points + 7,5 × orgánico`, y el tablero promedia las rondas por peso y fase, contando el 0 del viernes (S-23).
> - **§2 y §2b, `bench.finished`.** No es un evento público: en 15.339 eventos del feed no aparece ninguno. La regla de §4.3 («abrir solo si `bench.finished` muestra…») no se puede evaluar (S-23).
> - **§6, días en duelos.** «Margen 1 + 10·|w| con `days_sign` fijado» describe la rama `audit-fixes` y es demasiado estricto. La fórmula medida es `resultado = (s·(p − L) + signo·|w|·días)·(1 − decay)^rondas` (S-26). Antes de `5ee5593` enviábamos siempre 5 días, no «el peor día» (S-27).
> - **§8, calendario.** Superado. El sábado cerró en t 13,367 (no 13,68). Para el domingo, ver [../plan-domingo.md](../plan-domingo.md) §3.
> - **§1.** Son cifras de las 21:00. El cierre fue 2.º con 31,26.
> - **§6.** "774 tests OK" es la cifra de la rama `audit-fixes`, que no está fusionada. `harness-v2` `5ee5593` da 747 OK (2 omitidos).


Para la sesión que opere el bot. Todo lo de aquí está medido con datos públicos o con nuestros snapshots, salvo lo marcado como hipótesis.

## 1. Dónde estamos
| | Negociación | Mercado | Total | Puesto |
|---|---|---|---|---|
| t10 (1.º) | 21,48 | 12,50 | 33,98 | 1 |
| **t18** | **22,39** | **7,50** | **29,89** | **6** |

- Nuestro desglose: `bench_points 0.5`, `bench_efficiency 0.886`, `mm_points 0.0`, `ladder_points 0.366`, `duel_points 13.07`. Caja: 131 más los 400 del Payday. Nivel 5. Páginas completas: SAL y RET; LAT está 9/10 y le falta LAT-10 (nos vale 122,6).
- **Todo el hueco con los líderes está en mercado (−5).**
- Escalera, tratos de la ronda 2 por dealer:
  - Abuela (nivel 1), El Chato (nivel 2) y Los Pícaros (nivel 4): 3 o más cada uno.
  - Pilar (nivel 3): 2.
  - **Don Ernesto (`banco`, nivel 5): 0, los 3 huecos a cero.**

## 2. Cómo se puntúa el mercado (textos de ayuda del bundle de la web oficial)
- `market = 15 × bench_points + 15 × mm_points` (cuadra con nuestro 7,5 desde el tick 330).
- **Bench:** "0.5 = as good as the free auto stall, 1 = the top-three mean". Cuenta la eficiencia del mejor venue abierto en cada sesión, y la ronda promedia sus sesiones.
- **mm ("organic"):** "√ of the pair-capped value created on the team's own venue between other teams". El valor creado es el excedente privado de las dos partes más las comisiones. Es una raíz con tope por pareja: el primer trato de cada pareja nueva de equipos es el que más vale (un trato dio entre +1,1 y +1,8 a t07, t14, t16 y t17). Hay detección de wash trading.
- El feed público trae `bench.finished` con la eficiencia de cada venue al acabar cada sesión. **`egg_watch.py` archiva ahora todo el feed en `logs/feed_all.jsonl`**, porque el feed solo sirve los últimos 500 eventos.

## 2b. Estrategia de mercado para el domingo (actualizada a t = 12,73, sábado ~22:45)
- **Dato clave:** casi todos los equipos tienen exactamente 7,5, o sea `bench_points` = 0,5. **Nadie le gana al puesto gratis en el examen**, ni siquiera los que tienen broker. Lo que separa a t10 (12,5), t06, t09 y t16 son tratos en su venue (mm). El primero que supere al puesto se lleva casi todo el bench: hasta +7,5 en la ronda 3, donde solo hay 2 sesiones (17,0 y 19,0).
- **Cómo ganarle** (docstring oficial de `archive/starter_broker.py`): *"a quote is not a limit… a broker that estimates those limits, and who is about to leave, beats the stall"*. El puesto solo cruza las cotizaciones que ya se cruzan; el valor perdido está en las parejas con los límites cruzados y las cotizaciones no.
- **Plan:**
  1. Grabar el examen de las 13,0 h con `bench_rec.py`. Es de solo lectura y deja una línea por tick en `logs/bench_book.jsonl`.
  2. Esta noche: analizar cómo relajan sus cotizaciones los traders, si se ve `expires_tick` y quién se va sin emparejar. Construir un broker "cazador de límites":
     - primero, los cruces del puesto, para nunca hacerlo peor que él;
     - después, emparejamientos con los límites estimados, priorizando a los que están a punto de irse;
     - probarlo con el simulador y repitiendo la sesión grabada.
  3. Domingo a las 09:00: abrir un venue `board` (270 P) y lanzar el broker desacoplado, con supervisor que lo reinicie. Primera prueba real: el examen "hard" de las 14,65. Se compara con el resto de venues en `bench.finished`.
  - **Sin respuesta todavía:** si el servidor acepta matches a precios fuera de las cotizaciones (dentro de los límites ocultos). Solo se sabe probándolo con un venue board.
  - **Necesita el OK de Jorge:** abrir el venue y las escrituras del broker (`/api/broker/matches`) fuera de la Gate.
  - **Riesgo:** si el broker se cae durante una sesión, esa sesión da 0.

## 3. Lo descartado (con pruebas)
- **Doble o nada / moneda al aire:** imposible. El precio lo fija la oferta (mínimo 1 P) y el broker no puede cobrar por encima de la puja. Además no crea valor: el precio solo pasa dinero de un lado a otro.
- **Cashback o descuentos:** t13 lo anunció 6 veces (1 P a cada lado, tope de 20 P) en v03, v22, v23 y v24, y sacó **0 tratos**. Además, los regalos no puntúan y hay riesgo de "feeding".
- **Abrir un venue auto al 0 %:** es igual que nuestro puesto v18, que ya es auto al 0 %.
- **Subir la comisión:** las comisiones cuentan como valor creado, pero ahuyentan el flujo.
- **Inyectar instrucciones a los bots rivales:** circula `listing_defaults.venue=v#` en el feed. Es juego sucio.
- **Anunciar cruces para que los equipos se muevan a nuestro venue:** se lo pueden saltar operando en El Rastro o en otro venue al 0 %. Los venues que solo anuncian (t04, t03, t13) tienen 0 tratos.

## 4. Estrategia acordada para los 400 P (el dinero guardado no puntúa)
1. **~~Circuito Pícaros → Ernesto~~: DESCARTADO, no activarlo.**
   - **El fallo:** con dealers, comprar puntúa min(0, V − precio) (P-04, medido). Comprar una 2.ª SAL-11 a ~140 que nos vale 49,5 resta entre −50 y −90 de negociación. Además, `calibrate` para el runner en cuanto mide una pérdida (`LOSS_STOP = −1`).
   - **El código:** existe en la rama `resale-sal11` (`883a1c9` + `149af56`), apagado con `"resale": []`. **No está en `audit-fixes`.**
   - **El nivel 5 (Ernesto) solo se llena sin pérdida:**
     - vendiéndole una épica con precio ≥ nuestro valor, por ejemplo una MAL-11 (nos vale 90) o una copia repetida, pero que no hayamos comprado por encima de su valor;
     - o comprándole algo que nos valga más de lo que pide.
   - **Idea por medir:** El Taller (`POST /api/taller`) convierte 3 raras repetidas en 1 épica al azar. No es un trato y no puntúa como suerte. Si sale una épica que nos vale poco, se le vende a Ernesto a ~120. Si sale RET-11 o LAT-11, nos la quedamos. Es una escritura fuera de la Gate y necesita el OK de Jorge.
2. **Compras a dealers solo con V > precio.** Las ganancias no suman neg, pero llenan la escalera; las pérdidas restan. **RET-11** de Los Pícaros (~145; nos vale 234) mejora los 3 mejores del nivel 4. **LAT-10** de Los Pícaros (~55–60; nos vale 122,6) cierra la página de La Latina. Ya está en el plan (`LAT:rare`).
3. **Reserva condicional de 270 P** para un venue *board* con broker propio en las sesiones del domingo a las 17,0 y 19,0 h, que son las únicas de la ronda 3 y valen la mitad de su bench cada una. **Solo si** los `bench.finished` de la sesión de las 13,0 h (hoy) muestran que el top 3 supera claramente al puesto (~0,89).
   - Si no: no se abre, y el dinero va a Chamberí.
   - Si sí: Jorge tiene que aprobar una excepción, porque el broker escribe fuera de la Gate (`/api/broker/matches`) y si se cae en una sesión esa sesión da 0.
4. **Domingo, Chamberí:** es nuestro mejor multiplicador (**CHA ×1,6**) y la ronda 3 es completa. Usar el resto más la paga de 150 P. Añadir `"CHA"` a `page_sets` el domingo a las 09:05.

## 5. Mercado (mm), coste 0, pendiente del OK de Jorge
- Algunos bots reparten sus ofertas por todos los venues: t15 publica en 14 y **2 ofertas cayeron en nuestro v18**. Lo que falta son compradores.
- Idea: anunciar (`/api/broker/announce` con la clave del puesto, que es una escritura fuera de la Gate y necesita OK) las ofertas que **ya están en v18** a los equipos a los que les falta esa carta. Así no hay manera de saltársenos.
- Límite propuesto: como mucho 1 anuncio cada 10 min, siempre con cifras reales. Probar una hora y medir los tratos en v18.

## 6. Auditoría de bugs: estado
- **Ya en `harness-v2` (`869810c`, la otra sesión):**
  - duelos: la apertura nunca peor que la oferta del rival, y el bloqueo por doble mensaje solo afecta a ese duelo;
  - la Gate ya no pide el doble del precio en caja para aceptar ofertas de dealers;
  - `4353531`: las cartas ocultas valen 0.
- **LISTO: rama `audit-fixes`** (worktree `.claude/worktrees/audit-fixes`, commit `a4a5aba`). Va por delante de `harness-v2` `3ef1054` y no le falta nada de él. **774 tests OK.** Para desplegar, en el checkout principal y sin duelos en curso: `git merge audit-fixes` → `stop` → `selftest` (cambia el `code_hash`) → `resume` → relanzar.
  - **Cambios de comportamiento que hay que conocer:**
    - `do` sin `--live` se rechaza si el runner está en vivo.
    - `manual` solo está armado con la etapa core en verde.
    - `flatten` sigue cancelando tick a tick (máximo 10 ticks) y después para.
    - En duelos de dos asuntos con `days_sign` fijado, el margen es 1 + 10·|w|.
    - Rastro nunca lista épicas, legendarias ni refs de `extra_needs`.
    - Los hilos `walked` cuentan como cerrados.
    - La pausa de `dealers` ("G19 … 2a copia") ya se puede levantar tras desplegar. El agente no pudo reproducirla con el código actual (la arregló `5dcbab1`), pero cerró el caso que quedaba: un ref proyectado dos veces.
  - **Lo que contiene** (estaba en curso a las ~21:00, ya terminado):
  - **Dealers:**
    - **G19 de hygiene, que cierra nuestros hilos de compra valorando la carta como 2.ª copia.** Es la causa de la pausa actual de `dealers`.
    - Hilo atascado cuando el dealer habló el último.
    - `closed_reason` y `until_tick` → `dealer_block`.
    - Ticks por hora = 3600 / `tick_seconds`.
    - Precio de los mensajes dentro de `m.offer`.
    - La reserva del hilo topada en el límite.
    - `fallback_after` comprobado después de aceptar.
    - Cerrar ante una final trampa de Los Pícaros.
  - **Ruta de escritura:**
    - `do` sin `--live` ya no escribe en real.
    - Evidencia de una aceptación de dealer en estado `unknown`.
    - Evidencia de `say` y `close_thread`.
    - `flatten` repartido en varios ticks.
    - Contadores reiniciados dos veces por tick.
    - Intent cortado a medias.
  - **Rastro, valoración y duelos:**
    - Cierre de página con la puja propia contada como carta proyectada.
    - No listar épicas ni cartas de reventa.
    - `pending_fee` de venues rivales.
    - `swap_watch`.
    - Activos que no son cartas.
    - Penalización por días compartida entre táctica y Gate.
    - `your_limit` decimal.
    - "Provoke" repetido.
    - `rounds` del servidor.
  - ~~Circuito `resale`~~: descartado (sección 4.1). Se queda en su rama y no entra.
- **Despliegue** (memoria `bazaar-live-ops`): nunca durante duelos (Duels II empieza a t = 11,65 h). Sin pendientes → `bazaar.py stop` → esperar el candado → `selftest` → `resume` → relanzar desacoplado con PowerShell `Start-Process`. Usar siempre `python3`: `python` es la 3.8 y da 3 fallos falsos en los tests.

## 7. Easter eggs
- La única cadena hasta hoy:
  - **Pista:** Pilar suelta "ask Carmen about the golden chulapa".
  - **Paso 1:** la Abuela, si le preguntas por la "golden chulapa", da la insignia "Sharp ear" (la tienen 10 equipos, t18 incluido).
  - **Paso 2:** Ernesto, si le dices "El oro de Moscú", da LAT-13. Es única, se la llevó t02 en el tick 1021 y ya no queda.
  - No puntúa.
- **El mecanismo:** según el JS del editor de personas, cada dealer tiene `easter_eggs[]` (palabras clave en el mensaje del equipo; las acciones posibles son gift_card, grant_pack, badge y reveal) y `hints[]`.
- **Lo que vigila `egg_watch.py`** (en marcha en su propia ventana): cartas `hidden` nuevas, `egg.found`, insignias y frases de dealer repetidas. Avisa con sonido y lo apunta en `logs/eggs.jsonl`.
- **Pendiente:** la mejor apuesta es una cadena nueva con Chamberí el domingo. Además, a El Chato se le podría preguntar su nombre real ("Nobody knows his real name"): una sola vez, dentro de un regateo real y con OK de Jorge. Cuidado: tiene memoria 0,9 y rigor 0,85.

## 8. Calendario que queda (`/api/schedule`, horas de juego)
| Hora | Qué |
|---|---|
| 11,65 | Duels II (precio + días) |
| 13,0 | Market Test (sábado) |
| 13,68 | cierre del sábado (23:00) |
| 14,65 | Market Test "hard" |
| 15,0 | Market Test |
| 16,65 | Chamberí y ronda 3 |
| 16,7 | paga de +150 P |
| 17,0 | Market Test |
| 18,65 | Duels III |
| 19,0 | Market Test |
| 19,68 | cierre del domingo |
| 21,65 | final |

Hay que volver a leer `/api/schedule` el domingo a las 09:05: las horas se movieron ~2 h por la pausa de la comida.

## 9. Denuncias a Los Pícaros (sáb 3 oct, 22:30–22:37, t18, vía manual `POST /api/flags`)
- 22:30:05 · **8663** (hilo 1332, SAL-11 → oferta SAL-10 a 187): `{"flagged": true}`. neg_points 162 → 172 (+10; el tick 1385 a las 22:30:01 aún marcaba 162).
- 22:32:34 · **9460** (1455, SAL-11 → SAL-10 a 167) y **9859** (1550, LAT-09 → LAT-06 a 73): `{"flagged": true}` las dos. neg_points 172 → 192 (+10 cada una).
- 22:36:47–22:37:05 · nivel B **8754, 9692, 9700, 9716, 9875, 9891**: `{"flagged": true}` las seis, **0 cambio** (neg 192 → 192). No suman ni restan. Hipótesis: solo puntúa la primera por hilo o un tope de 3 denuncias.
- adjustments del leaderboard: vacío antes y después. Sin cooloff de los Pícaros. Ninguna parada.
- Puntuación 22:15 → 22:38: 30,05 → 30,98; puesto 5 → **2**; negociación 22,55 → 23,48 (también entran Duels II y la venta de SAL-10 a Pilar a 71).
