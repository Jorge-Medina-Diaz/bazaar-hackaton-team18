# Estrategia sábado y domingo — Team 18 (t18) · v2 (tras el equipo rojo)

> **English summary:** the playbook (J0–J13) that the tactics implement, in Spanish, written before Saturday. It includes how the design was chosen (three designs scored by a panel, then a red team), cash plans and the calendar. Sunday's revisions are in [history/plan-domingo.md](history/plan-domingo.md).

> **Escrito para el sábado (02:00–03:30).** El orden de jugadas J0–J13 es el que implementan las tácticas y sigue valiendo. **Superado:** la situación de §1 y §3, el calendario de §4 y las decisiones de venue (J11, D4). Lo vigente para el domingo, con el código publicado (`night-build` más los cambios del domingo, harness-spec §15), está en [plan-domingo.md](history/plan-domingo.md). Hechos del sábado: [knowledge.md](knowledge.md) S-17..S-33. Solo se ha corregido donde contradecía los datos o el código.

Escrito el sábado 3 oct 2026 entre las 02:00 y las 03:30, con el juego cerrado. Lo firma el arquitecto jefe. La v2 incorpora las críticas del equipo rojo (seguridad, escéptico de estrategia, jefe de ingeniería); la lista de cada problema y qué se hizo está en `docs/harness-spec.md` §14.
La fuente de verdad es `docs/knowledge.md` (ids P-, V-, D-, R-, X-, U-, M-, C-, K-). Cualquier otro documento del repo es una lista de afirmaciones.
El cómo se construye está en `docs/harness-spec.md`. Este documento dice **qué hacemos, en qué orden y por qué**.

**Etiquetas.** `[medido]` = rehecho desde datos crudos (esta noche, o por el escéptico de la KB con su id). `[regla]` = RULES.md, OpenAPI, schedule, catalog o dealers.json del servidor. `[inferido]` = deducción. `[desconocido]` = nada en disco lo zanja; lleva su experimento. La confianza va al lado (alta, media o baja).

---

## 0. Cómo se ha decidido este plan

### 0.1 Nota de cada diseño (1 a 10)

| Diseño | Puntos esperados | Seguridad | Construible antes de las 08:00 | Claridad |
|---|---|---|---|---|
| Cuantitativo ([`design_quant.md`](history/designs/design_quant.md)) | **8** | 7 | 6 | **8** |
| Seguridad ([`design_safety.md`](history/designs/design_safety.md)) | 7 | **9** | 5 | **8** |
| Frontera ([`design_frontier.md`](history/designs/design_frontier.md)) | 6 | 7 | 3 | 6 |

- **Cuantitativo.** Acierta en el orden de jugadas (lo escaso: caja, huecos de escalera, cierres de página, cuota de dealers), en el plan de caja y en el cliente sin reintentos (`bazaar_sdk.py:62-86`). Falla en P(fill) = 0,7 para el cierre (R-05: 9 %), en fiar la seguridad a una convención y en el tamaño.
- **Seguridad.** Acierta en la barrera física, la vigilancia de lo publicado, un camino de compra por carta, el límite que solo se endurece y el oráculo independiente. Falla en pujas de cierre de 20 a 30 (la caja no puntúa), en el venue automático (270 P que no hay) y en el tamaño.
- **Frontera.** Acierta en que callar no cuesta decay (rondas = min(nY, nR), 30/30 esta noche), en el peso de los bancos del domingo, en la caja que no puntúa, en el diario con cadena de hash y en `replay-friday`. Falla en dejar el comercio en segundo plano, en poner la clave del broker en otra máquina y en que no se construye esta noche.

### 0.2 El plan elegido
- **Estrategia:** la del diseño cuantitativo (RET con dealers por debajo del valor y cierre con un equipo), corregida por el escéptico: cierre a precio único inmediato, nunca bajar una puja de cierre, el plan de reabastecer las pujas de cierre de los rivales (J13) y un único modo de página el domingo.
- **Arnés:** el del diseño de seguridad, por etapas: lo que se usa a las 09:00 (higiene) está listo a las 08:00; duelos antes de Duels I; dealers y Rastro antes de que hagan falta (los dealers no son urgentes: la cuota es por hora e igual para todos).
- **Injertos del diseño frontera:** el ascenso gratis en duelos (ahora lento), la cadena de hash, `replay-friday`.

### 0.3 Desacuerdos y cómo se han resuelto

| Tema | Opciones | Decisión | Por qué |
|---|---|---|---|
| Precio de la puja de cierre | 30→40→49 (v1) / 20→30 (seg.) / floor(dv_add − 50) ya (escéptico) | **Primero aceptar una venta con neg_lo ≥ 20. Si no hay, pujar YA a min(floor(dv_add − 50), cash_free): 49 en una común de RET, 72 en una común de CHA. Subir hasta floor(dv_add − 20) si un rival puja igual o más por esa carta, o en el final del domingo. Nunca bajar.** | Con el tope (P-07, +50,0 frente a +69,9) toda p ≤ 49 da +50: escalar solo pierde 20–40 min frente a rivales que han pagado 70–110 por cartas de cierre `[medido esta noche · alta]` (feed: t13 pagó 74 y 70; t10 pujó 110, t05 100, t12 100). Sin tope, floor(dv_add − 50) da +50,1. Igual en las dos hipótesis. |
| Puja de cierre en las últimas horas | bajar a 30 (v1) / subir (escéptico) | **Subir a floor(dv_add − 20)** | La caja vale 0 a las 15:00 del domingo (RULES l.7, l.122). Bajar solo reduce la probabilidad del +50. |
| Venue | no / condiciones (v1) / `auto` según flujo (escéptico) | **No `board`. Un `auto` a comisión 0 solo si E15 mide ≥ 3 tratos/h en venues de equipo durante 2 h y cash_free − plan de páginas ≥ 270; siempre por el Gate (mejora L4).** | Greedy en board = puesto (M-04) y su caída da 0 (M-05). Un `auto` no tiene broker que caerse, y es nuestra única vía a mm_points (RULES l.119); pero el viernes no hubo flujo medido en venues de equipo (M-10) y bloquea 270 P que el plan de páginas necesita. |
| Duelos | v0 corregido / híbrido | **v0 corregido + ascenso lento con el rival callado + aceptar solo en el tick en que el rival ya habló** | rondas = min(nY, nR) `[medido 30/30]`; aceptar no lleva id (U-10, OpenAPI) y la única forma de que la oferta no cambie entre la lectura y el POST es que el rival ya haya gastado su mensaje del tick. |
| 2503 (puja de 62 por LAT-09) | cancelar (v1) / mantener | **Mantener 2503 y 2504 hasta t205** | Con N la caja libre es 276 tras la subvención y con M 126 basta para un hilo de rara y uno de infrecuente. Si se cumplen las dos, LAT se cierra con equipos (+1 y +50) y E5 se mide limpio (+60,6 sin tope frente a +50). |
| Modo del domingo | `page` / `ladder` | **Un solo modo:** comprar por orden rara → infrecuente → común, dejar el cierre al equipo | Comprar por debajo del valor nunca resta neg; la caja que sobra vale 0. Lo único que cambia entre los modos es el orden, así que se fija uno. |
| Bloqueo por sobre sin abrir | cartas posibles / toda compra | **Toda compra, y además se cierran los hilos de compra antes de abrirlo y antes de una subvención** | Un dealer puede aceptar nuestro último precio en cualquier momento (regla: "or let it accept yours"); con el sobre en mano ese precio pasa a ser pérdida (P-06). |
| LIVE_OK con fecha | sí / no | **No** | Armado por táctica + selftest por etapa + STOP + candado. |

---

## 1. Lo que sabemos y lo que no (lo que mueve el plan)

| # | Hecho | Etiqueta |
|---|---|---|
| 1 | Al cierre: caja 260, nivel 2, sin venue ni starter_broker_key, neg 74,5, ladder 0,051, 0 hilos abiertos. *(Desde el tick 201 hay puesto gratuito v18 con su starter_broker_key; cuenta en el Market Test con la mitad del banco, S-24)* | `[medido esta noche · alta]` me.json |
| 2 | Ofertas abiertas: 1652 (LAT-05#8 a 12, para t15, t167); 2460/2462/2465/2466 (LAV-03, MAL-04, MAL-05, LAV-04 a 8, t173); 2463 (LAT-01#16 a 8, t173); pujas 2503 (LAT-09) y 2504 (LAT-10) de 62 hasta t205; 2591 (LAT-05#16 a 9) y 2592 (LAT-01#17 a 9) hasta t210. Las 2 copias de LAT-01 y las 2 de LAT-05 están a la venta. LAV-04 es copia única (your_value 7,0), no repetida. | `[medido esta noche · alta]` me_offers, me.json |
| 3 | Valor de una copia más: RET 13 / 32,5 / 91; CHA 16 / 40 / 112; LAT-09 = LAT-10 = 63. La carta que cierra RET vale 99,1 (común) y la que cierra CHA 122 (común). | `[medido · alta]` V-05, V-06 |
| 4 | Con dealers, neg solo baja: min(0, V − p). Modelo ponderado con tope 50: 11/12 puntos. | `[medido · alta]` P-04 |
| 5 | Con equipos: V − p − comisión (solo si aceptamos); comisión = ceil(0,05·p + cartas) | `[medido · alta]` P-03, R-01 |
| 6 | SAL-10 contó +50,0 en vez de +69,9: tope o fórmula, causa desconocida | `[medido · alta]` P-07 / `[desconocido]` causa |
| 7 | La escalera solo sube con tratos con dealer que son ganancia; los 3 huecos de nivel 2 están vacíos; el peso de cada nivel no se conoce | `[medido · alta]` P-10 / `[inferido · baja]` peso |
| 8 | Un sobre sin abrir rebaja la V efectiva de cada compra (−1,9 / −2,3); abrirlo no mueve neg | `[medido · alta]` P-06, P-08 |
| 9 | La Abuela vende comunes e infrecuentes (8 tratos/h); El Chato infrecuentes y raras (6/h). Ninguno tiene RET ni CHA en stock: los acuñan al vender. | `[regla]` dealers.json; `[medido]` D-12 |
| 10 | Subvención de la hora 4,05: +150 y un sobre de barrio a cada equipo. El domingo, solo caja. | `[regla · alta]` schedule |
| 11 | Duelos: resultado = \|p − L\| × (1 − d)^rondas; rondas = min(nY, nR); la aceptación no lleva precio ni id y toma la oferta en pie | `[medido · alta]` U-01, U-02, U-10; `[regla]` OpenAPI `/api/duels/{did}/accept` sin cuerpo |
| 12 | El tablón muestra seudónimos: nuestras ofertas 2463/2503/2504/2591/2592 aparecen con maker `mcd38ffd5`, no `t18`; `/api/me/offers` sí muestra `t18` | `[medido esta noche · alta]` rastro_offers.json, me_offers.json |
| 13 | `clock.limits` = `accepts_per_team_per_tick` 1, `messages_per_side_per_tick` 1, `max_open_threads_per_team` 6, `max_open_offers_per_team` 30, `offers_per_team_per_tick` 12 | `[medido esta noche · alta]` clock.json |
| 14 | Los rivales pujan fuerte por cartas que cierran página: 59 pujas ≥ 35 P el viernes; se cumplieron SAL-09 a 74, SAL-10 a 70 y 80 (la nuestra), SAL-08 a 35 (t17, la vendió t12) | `[medido esta noche · alta]` feed.jsonl |
| 15 | No sabemos qué lectura del reloj rige el sábado (N, M, C) ni si seguirá en pausa (P) | `[desconocido]` C-05, C-03 → E1 |
| 16 | No sabemos si neg o escalera se reinician con la ronda | `[desconocido]` P-18 → E2 |
| 17 | La caja no puntúa: lo que quede el domingo a las 15:00 vale 0 | `[regla · alta]` RULES l.7, l.122 |

---

## 2. Jugadas por orden de prioridad

Cada jugada la ejecuta una táctica del arnés y pasa por el Gate. "Armar" pasa una táctica de sombra (decide y registra sin escribir) a escritura real; solo se puede armar si su etapa del `selftest` está en verde. Mientras una táctica no esté construida, una persona puede hacer la misma jugada con `bazaar.py do` (pasa por el mismo Gate y las mismas guardas).

| # | Jugada | Disparador | Efecto esperado | Parada | Evidencia | Guardas |
|---|---|---|---|---|---|---|
| **J0** | **Higiene de apertura:** cancelar 2463 (LAT-01#16) y 1652 (LAT-05#8). Se mantienen 2591/2592 a 9 y las pujas 2503/2504 hasta t205. Se intenta ya a las 08:55 (si el servidor la rechaza con puertas cerradas, no pasa nada) y otra vez en el primer tick abierto por la vía rápida (solo clock + me/offers, antes de la lectura completa). | Arranque del runner (08:55) | LAT no puede bajar de 8/10 aunque un rival acepte en el segundo 0 | Hecho; desde entonces la vigilancia de G19 | `[medido]` me_offers, R-09, K-01 | G23, G13 (en la vigilancia) |
| **J1** | **Abrir cada sobre al llegar**, después de cerrar los hilos de compra abiertos | `kind=pack` en `me.assets` | Evita −2 por compra (P-06) y que un dealer acepte un precio que el sobre ha vuelto pérdida | Nunca | P-06, P-08 | G14, G40, INV-23 |
| **J2** | **Medir sin coste:** cada tick, `*_points`, ronda, reloj y schedule al diario | Siempre | E1, E2, E4, E6 | — | P-14, P-18, C-05 | solo lectura |
| **J3** | **Página RET a 9/10 con dealers por debajo del valor.** <br>**El Chato, raras RET-09/10:** pasos constantes de +4 desde 70, límite 90 (valor 91); objetivo ≤ 87 (t07 le sacó 82 con +4, D-10). <br>**El Chato, RET-08 (infrecuente):** patrón de t03: ancla 13, pasos de +1, límite 31; si a los 10 ticks sigue en 32, se cierra el hilo y se compra a la Abuela. <br>**La Abuela:** RET-06/07 a ≤ 25 (desde 16, +2) y las comunes a ≤ 11 (desde 7, +1). Se descuenta lo que traiga el sobre. Primer hilo con la Abuela = sonda E3 (si abre en 17, se acepta). | RET publicado, sobre de la subvención abierto (N) o hilos cerrados antes de la subvención (M, C), etapa B verde | neg 0 garantizado; hasta 3 huecos de nivel 2. Coste ~290 P en cartas que valen ≥ lo pagado | 9/10 (la carta de cierre se congela en 8/10 y nunca se compra a un dealer). Final > límite → cerrar y reabrir ≤ 1 vez/h. Sin hilos nuevos de la táctica con más de 4 duelos vivos (una orden manual pasa siempre; `3dd3ed6`). | D-01..D-10, V-05, P-10 | G15, G16, G30, G31, G32, G60, INV-23 |
| **J4** | **Cierre de RET con un equipo.** 1) Venta en el tablón con `neg_lo ≥ 20` → aceptar (si hay puja nuestra abierta: cancelar en T, comprobar en T+1 que está `cancelled` y aceptar en T+1). 2) Si no, puja a `min(floor(dv_add − 50), cash_free)` = 49. 3) Si aparece una puja rival ≥ la nuestra por esa carta, o en el endgame (domingo: cierre − `closer.endgame_min_before_close` = 35 min, ≈ 14:25), subir hasta `floor(dv_add − 20)` = 79 (102 en CHA). Nunca bajar. 4) La puja se retira mientras haya riesgo de entrega (sobre pendiente o subvención a ≤ 3 ticks, hilo con la Abuela abierto, o hilo con dealer abierto con un nivel nuevo anunciado) y se repone al desaparecer. | RET en 9/10 (exactamente la carta congelada falta) | **+50** en las dos hipótesis de P-07 (unos 4,7 puntos de ronda, `[inferido · media]` P-15) | Cumplida | P-03, P-07, V-06, R-05, feed | G10–G12, G15, G16, G21, G19 (retirada) |
| **J13** | *(Domingo: apagada, `resupply_min` 999 en `config/plan.json` y nunca en el endgame, `a34e7c7`: vender la única común de CHA podía dejar la página bajo 9/10.)* **Reabastecer las pujas de cierre de los rivales** (nueva). Si un rival puja por una carta RET o CHA que tenemos y la página está por debajo de 9/10: aceptar su puja si `p − comisión − dv_rm ≥ 15`, la carta es común o infrecuente, no es nuestra carta de cierre congelada, la Abuela tiene cuota esta hora, la puja caduca a ≥ 2 ticks y no hay sobre pendiente. Después se recompra la carta a la Abuela (neg 0, y si es ganancia, hueco de escalera). | Puja rival por `card:RET-xx` / `card:CHA-xx` en el tablón | +19 a +32 de neg por ciclo (común de RET a 35–49) y +20 P de caja que financian CHA | La recompra falla dos veces seguidas → la táctica se pausa | feed (t12 hizo esto con SAL-08 a 35); P-03, P-04 | G12, G13 (excepción de reabastecimiento), G14 |
| **J5** | *(Domingo: solo segundas copias reales, con `dup_min_price` RET/CHA 30 y LAT 18; las épicas nunca son sobrantes; las cartas de `hand_sales` (MAL-01/02/04/05, LAV-02/03/05, LAT-06 #1105, LAT-02 #1103) quedan para las ventas a mano hasta el fin del día de dealers.)* **Ventas de sobrantes como autor** (sin comisión): LAT-01#17 y LAT-05#16 a 9; LAV-03, MAL-04, MAL-05 a 9 al caducar en t173; LAV-04 (copia única de un set que no montamos) a 12. **Duplicados de RET y CHA: nunca por debajo de 30**; mejor esperar pujas rivales. Si no se vende en 60 ticks, −1 P, nunca por debajo de V + 2. | Caducidad o carta sobrante | +2 a +7 por venta, +20 a +40 al día | No quedan sobrantes | R-01, R-03, R-04 | G13, G20, G22 |
| **J6** | **Comprar a equipos con ganancia ≥ 3** después de la comisión, solo cartas del plan. *(Domingo, `endgame_buy_any`: tras el fin del día de dealers o en el endgame, también cualquier primera copia fuera de las páginas por debajo de nuestro valor, guardando la caja que necesita la subida del closer.)* | Venta que pasa G12 | +3 a +10 por compra | — | P-03, R-06 | G10–G12, G15, G16 |
| **J7** | **Duelos** (Duels I: 11:30 N / 12:51 C): v0 corregido (K-06, K-07), estado desde el servidor; **ascenso lento** con el rival callado (lineal hasta L ± 1 en deadline − 2, guardando el último 25 % del excedente para los 3 últimos ticks); **aceptar solo cuando el rival ya ha hablado en el tick en curso**, releyendo a mitad de tick; si hace falta provocar su respuesta, mandar un mensaje (una ronda más de decay) y aceptar en la ventana tardía del mismo tick. Con varios duelos a punto de vencer, se reparte la única aceptación por orden de deadline. E8 en el primer rival que hable. | Duelos `live`; etapa C verde | 0 acuerdos fuera de límite; más acuerdos con rivales que solo aceptan (U-07) | Fin de la sesión | U-01, U-02, U-07, U-08, U-10 | G50, G51, G60, G04 |
| **J8** | **Market Test con el puesto gratuito**; grabadora solo-GET (L1) si aparece `starter_broker_key` | Sesión de banco | Mitad de los puntos del banco sin riesgo | — | M-02..M-05, P-19 | solo lectura; INV-18 |
| **J9** | **LAT condicional:** si se cumple 2503 o 2504, comprar la otra rara a El Chato a ≤ 100 (V = 122,6 con la primera en mano: neg 0, hueco de nivel 2), solo si no le quita caja a J3. Si se cumplen las dos, LAT se cierra con equipos (+1 y +50: mide E5). **Si en t205 no se ha cumplido ninguna, LAT se da por muerta:** sale de las páginas protegidas y sus cartas se venden como autor a ≥ V + 2 o a pujas con ganancia ≥ 3 (t14 necesita LAT-03 y LAT-08, X-12). | Puja cumplida / t205 | +1..+51 de neg, o caja para el domingo | t205 | X-02, X-06, X-12, V-07 | G32 (`ALLOW_DEALER_CLOSE`={LAT}), G16, G13 |
| **J10** | *(Superado por el código final, `55c25fd` y `70a487c`: valor = s·(p − L) + signo·\|w\|·d (S-26). El signo sale de cada duelo: `days_sign` del sensor, si no `days_meaning`, si no el papel (comprador −1, vendedor +1); un signo leído que contradice al papel da −1 y alarma. Comprador: 0 días y margen \|w\|·d; vendedor: 10 días y precio nunca fuera del límite. `plan.days_sign` ya no se usa. Lo de abajo es el plan del sábado.)* **Duels II de dos asuntos:** ningún mensaje con precio hasta leer `days_meaning` y `your_days_weight`; una persona fija el signo en `config/plan.json` (`days_sign`); mientras no esté, excedente ≥ 1 + max_d \|W(d) − W(base)\|. El mensaje lleva `days` arriba y dentro de `offer` (el SDK solo lo pone dentro; el esquema PostMessage admite los dos). | Primer duelo con `"days" ∈ issues` | 0 acuerdos con utilidad negativa en 68 duelos | Pausa si un resultado sale ≤ 0 | U-12, U-13, OpenAPI | G50 |
| **J11** | **Venue `auto` a comisión 0**, solo si E15 mide ≥ 3 tratos/h en venues de equipo durante 2 h y `cash_free − coste del plan de páginas ≥ 270`. Por el Gate (intent `open_venue` de la mejora L4), nunca a mano. Nunca operamos en él. | E15 | Acceso a mm_points por flujo ajeno | Una condición falla → puesto | M-02..M-09, RULES l.76, l.119 | Guarda propia de L4 |
| **J12** | **Domingo, CHA:** el mismo patrón que J3 + J4 en un solo modo: raras a El Chato (≤ 100, valor 112) → infrecuentes (Abuela ≤ 25, El Chato patrón t03 ≤ 31) → comunes (≤ 12) → cierre con equipo a min(floor(122 − 50), cash_free) = 72. Sin hilos nuevos durante Duels III. Último trato con dealer a las 13:45 (N). *(Plan vigente, `config/plan.json` de `night-build`: comunes CHA a la Abuela ≤ 12; CHA-06/07/08 a El Chato ≤ 31 con la Abuela de respaldo; raras CHA a los Pícaros ≤ 64 con El Chato de respaldo ≤ 93; después de la página, CHA-11 ≤ 170 y RET-11 ≤ 150 a los Pícaros, solo en la ronda 3; además (domingo en vivo) CHA-11 a equipos hasta 225 por J6 y CHA-12 a Don Ernesto (banco) ≤ 470 (ancla 380, paso 5), siempre topado por `cash_free` menos la reserva del closer. Hilos nuevos durante Duels III salvo con más de 4 duelos vivos. Fin de dealers y endgame derivados del reloj de pared y del calendario vivo (≈ 13:55 / 14:25). Detalle en [plan-domingo.md](history/plan-domingo.md) §5.1)* | CHA publicado | +50 si se llega a 9/10 y se cumple la puja; nada se pierde si la caja no llega | Igual que J3 y J4 | V-05, V-06, D-10 | igual que J3 y J4 |

### 2.1 Qué NO hacemos (lista cerrada; la impone el Gate)
1. **Comprar sobres.** No existe el intent.
2. **Pagar a un dealer más de V_lo − 1**, ni venderle por menos de V + 1.
3. **Cerrar RET o CHA comprando la carta de cierre a un dealer** (cuenta con lo que tenemos, lo aceptado sin liquidar, los hilos con precio en pie y nuestras pujas).
4. **Comprar la primera rara de LAT a El Chato** (−22 a −30).
5. **Publicar o dar la última copia libre** de una carta de una página protegida (SAL; RET y CHA; LAT mientras siga viva). La única excepción es J13, con sus condiciones.
6. **Tener una puja de cierre abierta con riesgo de entrega**, o un hilo de compra abierto al abrir un sobre o al llegar una subvención.
7. **Aceptar ofertas de equipos con ganancia < 3.** Ofertas dirigidas como táctica, tampoco (0/8, R-05).
8. **Bajar una puja de cierre.**
9. **Prompt injection** contra la infraestructura o los equipos. **Las denuncias (flags)** solo a mano, con el OK de Jorge y por trucos estructurales verificados (la oferta da otra carta que el tema del hilo y el texto nombra la pedida). El sábado puntuaron las 3 primeras, +10 cada una; las de nivel B dieron 0 (knowledge S-28). `flag` no es un KIND de la Gate.
10. **Ningún LLM decide cifras ni aceptaciones.** El texto ajeno es dato y no entra en el World.
11. **Ningún script antiguo** ni un segundo ejecutor. Con el arnés, `agent.client.client()` devuelve un transporte de solo lectura, así que los scripts antiguos que lo usan ya no pueden escribir; los que construyen su propio cliente llevan `SystemExit`.
12. **Nada de la Fase 4 del "estrangulamiento"** (C-12).
13. **No contraofertar por debajo de una final** de la Abuela, ni repetir precio o texto (D-07).
14. **No ida y vuelta** de la misma carta en El Rastro en 60 ticks.

---

## 3. Plan de caja

Regla del Gate (libro en marcha, se actualiza tras cada envío): `cash_free = cash − Σ pujas propias − Σ aceptaciones sin liquidar − Σ max(límite, precio en pie) de los hilos de compra − 10`. Las pujas no reservan caja en el servidor (R-10): las descontamos nosotros.

### 3.1 Sábado

| Momento | Caja | Comprometido | Libre | Uso |
|---|---|---|---|---|
| 09:00, tras J0 | 260 | 124 (2503, 2504) | 126 | Con M: un hilo de rara (90) + uno de infrecuente (31) caben |
| Subvención (hora 4,05) | 410 | 124, o 0 tras t205 | 276–400 | J3 |
| J3 completo | ~120 | 0–124 | ~0–110 | El Chato: 2 × ~87 + ~29. La Abuela: 2 × ~23 + 4 × ~10. Total ≈ 290 |
| J4 (cierre) | — | 49 en la puja (79 si hay competencia) | — | |
| J5 + J13 | +40 a +100 | — | — | Ventas y reabastecimiento |
| **Fin del sábado** | **~110–200** | puja de cierre si sigue abierta | — | Pasa al domingo |

- **Si se cumple 2503 o 2504 (−62):** J9 solo con lo que sobre de J3.
- **Si El Chato no baja de 90 en las raras:** RET se queda en 8/10 sin cierre; lo comprado vale ≥ lo pagado.

### 3.2 Domingo

> **Superado.** Caja de partida real: 555 + 150 = 705 P; gasto y topes en [plan-domingo.md](history/plan-domingo.md) §5.1 y §5.7 (la subida del closer es en el endgame, ≈ 14:25, no a las 12:00/13:00).

- **Caja prevista:** ~110–200 + 150 = **~260–350**, más J13 y la liquidación de LAT si murió.
- **Coste CHA calculado desde los Needs**, no fijo: 2 raras × ~87 + 3 infrecuentes × ~23–29 + 4 comunes × ~10 + cierre ≤ 72 ≈ **330–360**.
- **Un solo modo:** rara → infrecuentes → comunes → cierre con lo que haya (`min(72, cash_free)`; cualquier p ≤ 72 da ≥ +50 con o sin tope). Si la caja no llega a 9/10, no se pierde nada: lo comprado vale ≥ lo pagado y la caja sobrante valdría 0.
- **12:00 (N) / 13:00 (C):** las pujas de cierre abiertas suben a `floor(dv_add − 20)` si hay caja. Después, toda la caja restante a compras con ganancia ≥ 3.

---

## 4. Calendario

**El agente no usa la hora de pared.** Todo sale de `schedule.now_hours`, de la ronda, de los eventos del feed y de lo que aparece en las lecturas. Las horas de esta sección son para las personas.

**Lecturas del reloj (E1, a las 09:00:30):**
- **N:** `t_hours ≥ 4,0` y `round == 2`.
- **C:** `t_hours ≈ 2,65` y `round == 1`; todo +1 h 21 min.
- **M:** ronda 2 y RET a las 09:00, pero la subvención, los bancos y los duelos siguen +1 h 21 min en `upcoming`.
- **P (nueva):** puertas abiertas pero `paused: true` (el viernes el admin despausó a mano ~1 h 20 min tarde, C-03). Todo se desplaza lo que tarde en despausar; solo se pueden cancelar ofertas y cerrar hilos.

Con ticks de 30 s, el tick 160 cae a las 09:00:00 si el reloj no está en pausa. El runbook se ancla a ticks y eventos, no a horas.

### 4.1 Antes de abrir

| Hora | Acción | Quién |
|---|---|---|
| 07:50 | Revisión cruzada de las guardas | Dos personas |
| 08:00 | Congelar la etapa A. En la máquina A: `git pull`, `python3 bazaar.py selftest` (escribe el estado por etapa en `state/selftest.json`). Núcleo + higiene en verde = hay live. Núcleo en rojo = procedimiento de emergencia E0 (§13 del spec). | Operador |
| 08:30 | Custodia de la clave: `.env` solo en la máquina A; en Vercel, `DASHBOARD_PASSWORD` puesto o `BAZAAR_KEY` retirado; como mucho un visor de panel; nadie lanza `live_monitor.py` ni `panel.py` (retirados en la versión publicada) | Operador |
| 08:50 | `python3 bazaar.py clockcheck` (GET sin clave) | Operador |
| 08:55 | `python3 bazaar.py run --live --arm hygiene`: toma el candado, guarda la línea base e intenta las cancelaciones de J0 (si el servidor las rechaza con puertas cerradas, no pasa nada) | Operador |

### 4.2 Las primeras horas, lectura N (RET y ronda 2 a las 09:00; subvención 09:03; banco 5,0 a las 10:00; Duels I 11:30)

| Hora / tick | Acción | Control |
|---|---|---|
| 09:00:00 / 160 | Vía rápida: J0 si no se hizo a las 08:55. Diario: score del tick (E2). | `status`: 2463 y 1652 `cancelled` |
| 09:00:30 / 161 | `clockcheck` (E1) | N |
| 09:03 / ~166 | Subvención: +150 y un sobre. J1 lo abre en el tick siguiente (no hay hilos que cerrar). | Sobre abierto |
| 09:05 / 170 | `clockcheck` (E6) | — |
| 09:06:30 / 173 | Caducan 2460/2462/2465/2466. Si la etapa B no está: `bazaar.py do list_offer` a mano para LAV-03, MAL-04, MAL-05 a 9 y LAV-04 a 12 (E10). | ≤ 6 publicaciones por tick |
| 09:22:30 / 205 | Caducan 2503/2504 si no se cumplieron → J9 (LAT muerta: sale de las protegidas) | — |
| 09:25 / 210 | Caducan 2591/2592 → se republican a 9 (a mano o J5) | — |
| ~10:30 | Etapa B en verde → actualización en caliente (§13 del spec) → `arm dealers,rastro`. J3 en paralelo con los dos dealers. | Δneg = 0 ± 0,1 por trato |
| 10:00 / 280 | Banco 5,0 en el puesto | — |
| ≤ 11:00 | Etapa C en verde → actualización en caliente → `arm duels` | — |
| 11:30–~13:00 | Duels I (3 simultáneos: se permiten hilos con dealers; prioridad de la aceptación al duelo con menos ticks) | — |
| RET en 9/10 (~12:00–13:00) | `arm closer` → J4 a 49 en el acto | +50 al cumplirse |

### 4.3 Lectura C (todo +1 h 21 min: ronda 1 hasta las 10:21; banco 3,0 a las 09:21; RET a las 10:21; subvención a las 10:24)
- 09:00 J0 igual. Hasta las 10:21 no hay compras con ganancia (lo que se haga cuenta en la ronda 1, peso 0,5).
- 10:19–10:22: E2 bis (score tick a tick alrededor del cambio de ronda, sin tratos).
- 10:21 RET → `arm dealers` (etapa B ya en verde); 10:24 subvención: los hilos de compra se cierran 3 ticks antes y se reabren tras abrir el sobre.
- 12:51 Duels I.

**Lectura M:** compras desde las 09:00 con 126 de libre (2503/2504 abiertas); los hilos se cierran 3 ticks antes de la subvención de las 10:24 y se reabren después.
**Lectura P:** nada que hacer salvo cancelar; todo empieza al despausar, según la lectura que salga entonces.

### 4.4 Resto del sábado (N; con C, +1 h 21 min)

| Bloque | Qué |
|---|---|
| 12:00, 14:00, 16:00 | Bancos 7, 9 y 11 en el puesto; L1 si está |
| 13:00–18:00 | J4, J5, J6, J9, J13; E15 (flujo en venues de equipo); una persona prepara el informe para jueces (L3) |
| 18:00–~19:40 Duels II | 6 simultáneos: **sin hilos nuevos con dealers**; aceptaciones repartidas por deadline; J10 |
| 20:00, 21:00 (difícil), 22:00 | Bancos 15, 16 y 17 |
| 22:55 | La higiene cierra los hilos con dealers (regla `day_end` de `config/plan.json`) |
| 23:00 | `bazaar.py stop "cierre sábado"`. La puja de cierre se queda abierta de noche (no llegan sobres de noche; las ofertas se cumplen al abrir, R-08). |
| 23:15 | Una persona hace los `git mv` de la limpieza (M18 parte 2) y `selftest` |

### 4.5 Domingo (ticks de 15 s)

> **Superado.** Esta tabla supone las lecturas N/C del sábado. El sábado demostró que el reloj sigue y lo anclado al día se re-ancla (S-17). Calendario vigente: [plan-domingo.md](history/plan-domingo.md) §3 (probable: ronda 3 y CHA a las 09:00, Duels III ~11:00, cierre de puestos y Gran Final ~14:00, congelación a las 15:00).

| Bloque | N | C |
|---|---|---|
| Arranque | 08:40 selftest; 08:55 `run --live --arm hygiene,dealers,rastro,closer,duels` (las que estén en verde) con CHA en `page_sets` | igual |
| Ronda 3 y CHA | 09:00; subvención de caja a las 09:03; J12 | 10:21 / 10:24 |
| Banco 19 | 10:00 | 11:21 |
| Duels III | 11:00 (4 simultáneos, sin hilos nuevos con dealers) | 12:21 |
| Banco 21 | 12:00 | 13:21 |
| Final de caja | 12:00: las pujas de cierre suben a floor(dv_add − 20); la caja restante a compras con ganancia | 13:00 |
| Fin de dealers | Hora 23 = 14:00. **Último trato con dealer a las 13:45** | No llega antes de las 15:00 |
| Final | 14:00 Final de duelos; 15:00 se congela | Sin Final, salvo que la organización reescriba el calendario |

---

## 5. Experimentos (todos de coste 0 y con plan B)

| Id | Pregunta | Cómo | Plan B mientras no se sepa |
|---|---|---|---|
| E1 | ¿N, M, C o P? | `clockcheck` sin clave a las 08:50, 09:00:30 y 09:05 | Todo por eventos |
| E2 | ¿Se reinician neg o escalera con la ronda? | `*_points` y `round` cada tick; el calibrador excluye la ventana del cambio | Mismo plan |
| E3 | ¿Vuelve la bienvenida de la Abuela? | Primer precio del hilo RET-06 (17 o 29) | Regateo normal |
| E4 | ¿Cuánto vale un hueco de nivel 2? | ladder antes/después del primer trato con ganancia con El Chato | J3 igual |
| E5 | ¿El +50 es un tope por trato? | **Solo cuenta** si el trato tenía ganancia sin tope ≥ 55: el cierre de LAT con 2503+2504 (+60,6) o una venta de cierre aceptada a ≤ 44. Un cierre a 49 (sin tope: +50,1) no distingue nada. | Se trabaja con el tope |
| E6 | Horas de juego por tick de 30 s | Δt_hours en 10 ticks | Caducidades en ticks reales |
| E7 | ¿Las pujas reservan caja? | Caja frente a pujas en el primer `/api/me` | Se cuentan como comprometidas |
| E8 | ¿Los rivales de duelo ceden mientras callamos? | Callar 2 ticks tras la primera respuesta del primer rival que hable | v0 reactivo + ascenso lento |
| E9 | ¿Un duel_accept gasta la aceptación del tick? | Oportunista: la primera vez que coincidan una aceptación de duelo y una de mercado válidas | Se supone que la comparten |
| E10 | Unidades de `expires_in_ticks` a 30 s | `expires_tick − created_tick` de la primera publicación | Se pide 2× y se corrige |
| E11 | Libro del banco, curva y `expires_tick` | L1 solo GET | Puesto |
| E12 | Suelo de las raras de El Chato con +4 | Es J3 | RET en 8/10 |
| E13 | Días en Duels II | Leer los campos antes de mandar nada | Peor caso |
| E14 | Multiplicadores RET/CHA de rivales | Pujas `card:RET-xx` en el feed sin clave | Precios fijos |
| E15 | ¿Hay flujo en los venues de equipo? | Liquidaciones con `venue ∈ {v01..v04}` por hora en el feed sin clave (≤ 1 req/s) | Puesto |
| E16 | ¿El precio liquidado de un duel_accept es el que leímos? ¿Puede un rival mandar 2 mensajes en un tick? | Comparar en las 3 primeras aceptaciones; buscar en los mensajes de cada duelo dos del rival con el mismo tick | Si falla: se pausan las aceptaciones de duelo |
| E17 | ¿El servidor cuenta contra nuestros 6 hilos los que abre un rival con nosotros? | Si aparece uno, comparar el 4xx de `open_thread` | Se cierran |

---

## 6. Riesgos y qué los cubre

1. **El Chato no baja de 90 en las raras de RET** (finales 90–93, D-10). RET sin cierre; lo comprado vale lo pagado. E12.
2. **Nadie nos vende la carta de cierre** (pujas 9 %, R-05; ~11 cartas RET en el campo tras la subvención `[inferido · media]`). Cobertura: puja inmediata a 49, subida a 79 si hay competencia y en el final, congelar como cierre la común sin pujas rivales.
3. **Doble compra de la carta de cierre** (llega por sobre, regalo o dealer y a la vez se cumple la puja: −46 a −76). Cobertura: retirada de la puja con riesgo de entrega (INV-23), conteo proyectado (G15, G32), vigilancia G19. Residual: un regalo sin aviso en un hilo no abierto por nosotros; no se ha visto nunca (D-15: los regalos llegan en hilos negociados).
4. **El +50 no es un tope.** Pagar ≤ floor(dv_add − 50) gana igual en las dos hipótesis. E5 bien medido.
5. **La escalera de nivel 2 vale poco** (P-12). J3 no pierde neg.
6. **Lectura C o P:** todo por eventos.
7. **Un segundo escritor con la clave** (K-05). La clave solo la usan la máquina A y los paneles de solo GET; el Gate detecta lo que no explica y para en ≤ 1 tick.
8. **Caja corta el domingo.** Un solo modo y J13: nada se pierde si no se llega.
9. **Alimentar a un rival del top 3 con J13** sube la referencia relativa (P-15, `[inferido · media]`). Con ganancia ≥ 15 nos compensa siempre que la media del top 3 supere ~65 de neg, que es el caso.
10. **El arnés no llega entero.** Etapas con fecha; `bazaar.py do` permite hacer a mano cualquier jugada bajo el mismo Gate; E0 si falla el núcleo.
11. **Duelos:** la aceptación no lleva id (U-10); se acepta solo cuando el rival ya habló en el tick. Residual: que el POST llegue tras el cambio de tick (margen de 2 s). E16 lo mide.
12. **Jueces (40):** diario con cadena de hash, `report`, `replay-friday` y la tabla predicho/medido; el SHOWCASE se reescribe el domingo.
13. **Cambio de reglas en caliente:** `clock.limits` cada tick con las claves reales; una forma desconocida cierra solo su dominio.

---

## 7. Cambios tras información tardía

Sábado ~08:30. Entradas tardías (consejos de t13; énfasis del jefe en robustez, teoría de juegos y adaptación) adoptadas por el jefe como D1–D4. Ninguna cambia el orden de jugadas de §2 ni las cifras de cierre; solo amplían por dónde miramos y qué aceptamos. Resumen para el equipo en [LEEME-EQUIPO.md](history/LEEME-EQUIPO.md) §6.

| Id | Cambio | Dónde entra | Por qué y límite |
|---|---|---|---|
| D1 | **Swaps** carta por carta: se valoran V(recibida) − V(entregada) − comisión con el mínimo de una compra (≥ 3 aceptando); nunca se entrega una copia protegida (INV-06). Como autor solo en El Rastro, dando un sobrante (MAL, LAV, duplicados) por una carta del plan sin otra vía (nunca la carta de cierre: esa es J4) | J6 (aceptar) y J5 (publicar) | No hay medida de swaps del viernes: sin optimismo. Comisión calculada con 2 cartas. Forma inversa (el rival nombra lo que da) sin construir |
| D2 | **Todos los venues:** se leen los tableros de todos los venues abiertos y `/api/me/offers`. Publicamos solo en El Rastro. Aceptar en el venue de otro equipo solo con neg_lo ≥ `RIVAL_VENUE_MIN_GAIN` (10, comisión de ese venue incluida, ceil(fee_bps/10000 · p + fee_per_card · cartas)) y dueño fuera del top `RIVAL_TOP_N` (5) del leaderboard; leaderboard desconocido = no | J6, J13, E15 | El dueño gana puntos de mercado con nuestros tratos (RULES l.119). Con el snapshot del viernes, v03 (t13, 1.º) y v02 (t12, 2.º) quedan fuera; v01 (t06) y v04 (t02) pasan |
| D3 | **Pujas largas:** `expires_in_ticks` en unidades de 15 s: pedido = ticks deseados × segundos por tick / 15 (`contracts.expiry_units`) | J4, J5, J6 | Encaja con R-07 (a 60 s, lo pedido entre 4). No cambia la expectativa de cumplimiento (9 %, raras 4 %, R-05) |
| D4 | **Sin venue propio** en esta versión (`open_venue` fuera de `KINDS`). *Domingo: sigue siendo la opción por defecto; la decisión y la condición para cambiarla están en [plan-domingo.md](history/plan-domingo.md) §5.3 (no hay `bench.finished` público, S-23)* | J11 sigue condicionado | M-04, M-05: greedy en `board` = puesto, cuesta 270 P y una caída da 0. Condición de cambio en [LEEME-EQUIPO.md](history/LEEME-EQUIPO.md) §7, punto 1. *Domingo 10:09: se abrió a mano un venue board propio (v28) con un broker del operador, fuera de la Gate (excepción manual); en el banco difícil cruzó el 96,7 % de las ganancias posibles (bench 0,5, igual que el puesto). Traza: `data/market-test/v28-broker.jsonl`. L4/J11 no se construyó.* |
