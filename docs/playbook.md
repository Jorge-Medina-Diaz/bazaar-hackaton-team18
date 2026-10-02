# Playbook

Conocimiento confirmado, por vendedor y por mecánica. Cada afirmación lleva su fuente (experimento `EXP-…` o `scout`).
Lo no confirmado va en [experiments.md](experiments.md) hasta que lo esté.

## ⭐ Lecciones de alto valor (vie 2 oct, tick 60, ordenadas por impacto)
1. **Los puntos salen de comerciar con equipos, no de la escalera.** `neg_points` = primas de valor ganadas, 1 a 1 (EXP-005). Un trato con la Abuela mueve `ladder_points` unos +0,014; vender un repetido a 9 dio +6,8 `neg_points` (+3 de negociación).
2. **Lo que más puntúa son las raras entre equipos con affinity distinta.** Una rara vale entre 35 (×0,5) y 112 (×1,6) según el equipo, y ambos ganan: t08 vendió LAV-10 a t10 por 70 (puesto 4 con solo 4 tratos), y t13 vendió LAT-09 a t14 por 65 (t13 es primero). Las infrecuentes van de 12,5 a 40 y las comunes de 5 a 16.
3. **Los líderes juegan a "vender lo que valen poco y comprar lo que valen mucho".** t13 compra MAL a 6 a otros equipos y SAL a la Abuela, y vende LAT. t10 compra todo LAV, incluida la rara a 70. t14 compra LAT, incluida la rara a 65. **El patrón de compras de cada equipo delata su affinity alta.**
4. **Para una carta que queremos, el límite es nuestro `your_value`, no el suelo del vendedor.** El dinero no puntúa: pagar menos que nuestro valor es neutro o positivo. En EXP-004 rechazamos SAL-08 a 23 P cuando nos vale 27,5. Error: lo correcto era aceptar (D-007).
5. **La Abuela compra lotes.** t08 le vendió 4 comunes (2 LAT-05 y 2 SAL-02) por 23 P en un solo trato, unas 5,75 por carta. Al bajar t08 su precio (34 → 32 → 29), ella subió su oferta (22 → 23). Es una salida para los repetidos si no hay comprador entre los equipos.
6. **La Abuela revende lo que compra**: el SAL-02 que le compramos (id 326) se lo acababa de vender t08. Su inventario son las cartas que le venden los equipos.

## ✅ Bonus de página confirmado (tick 68)
Con SAL en 9/10, `value?card=SAL-10` pasó de 77 a **149,9** = 77 + 25 % × página (291,6). **La última carta de una página vale casi el doble.** Hay que llevar las páginas a 9/10 con cartas baratas (comunes e infrecuentes de la Abuela) y comprar después la última carta a otro equipo: es la jugada de más valor.

## ✅ Página SAL completa (tick 72): reglas nuevas
- Compramos SAL-10 a t12 por 80 (EXP-008). **Con la página completa, cada carta de la página nos vale su valor + todo el bonus** (SAL-04: 11 → **83,9**; SAL-09: 77 → 149,9), porque perder cualquiera rompe la página. **No vender nunca ninguna carta de SAL-01 a SAL-10** (la copia repetida de SAL-01 sí, vale 2,8).
- Épica (SAL-11, 198) y legendaria (SAL-12, 495): `value?` no muestra bonus "master" mientras falte una de las dos. 📜 El master bonus (+10 %) requiere ambas.
- ❓ `neg_points` subió **+50,0** cuando esperábamos +69,9 (149,9 − 80). Pendiente: ¿tope por trato?

## ⚠️ Regla dura (E9)
**Con un vendedor, el precio máximo es nuestro `your_value`.** Las pérdidas frente a nuestro valor restan `neg_points` y las ganancias no suman (solo cuentan en la escalera). Comprar a vendedores únicamente cuando: (a) sea una carta que nos falta y el precio ≤ valor, o (b) haga falta para la escalera o para desbloquear un nivel con coste ≈ 0.

## 🤖 Agente autónomo (`run_loop.py`, desde el tick 90)
En cada tick: alertas de niveles y duelos → juega los duelos activos → **acepta la mejor oferta de El Rastro si la ganancia de valor es ≥ 3** (compras: valor − precio − comisión; ventas a pujas: puja − comisión − nuestro valor) → vuelve a publicar los repetidos cada 10 ticks. Reserva de 150 P. Como `your_value` ya incluye el bonus de página, **nunca vende una carta de una página completa**: su ganancia sale negativa.
- Tick 90: **vendió MAL-04 a una puja de 10** (+6,8). La venta de MAL-01 a 9 que teníamos publicada dio +4.
- E8: una puja puede desaparecer entre que se lee y se acepta (`offer_not_open`). Se registra y se sigue: coste 0.

## 🗺️ Hoja de ruta de optimización (por puntos esperados)
| # | Palanca | Puntos en juego | Estado |
|---|---|---|---|
| 1 | **Broker propio para el Market Test** (comisión 0, límites estimados, no emparejar extramarginales) | Hasta 30 (mercado); el puesto gratuito da la mitad | Diseño en [broker-design.md](broker-design.md). Falta: datos de una sesión, nivel 2 y 270 P |
| 2 | **Duelos** (I sábado 6,5 · II 13 · III 20 · final 23) | Parte de los 30 de negociación | v0 hecho; práctica en el tick ~120 |
| 3 | **RET (×1,3) y CHA (×1,6)** el sábado y el domingo: comprar por debajo de nuestro valor, sobre todo las raras, y llevar páginas a 9/10 para pujar por la última | `neg_points` grandes | Plan listo (táctica EXP-008/009) |
| 4 | **Vender LAT a t15** cuando esté cerca de completar la página | ~+20–40 | Vigilar |
| 5 | Bucle autónomo: ventas y compras con ganancia ≥ 3 | +3–7 por trato | **En marcha** |
| 6 | Escalera: 3 mejores tratos por nivel; El Chato al activarse | Pequeño, pero desbloquea nivel 2 | Esperando activación |
| 7 | Jueces (40): presentación con proceso, errores y herramientas | 40 | Material en `docs/` |

## 🔎 El Rastro, ticks 70–87: quién compra qué y a cuánto
| Comprador | Compras (precio) | Lectura |
|---|---|---|
| **t15** | LAT-02 + LAT-05 por 18 (t04) · LAT-01 + LAT-07 por 40 (t13) · LAT-06 por 22 (t05) | **Colecciona LAT y compite con nosotros por esa página.** Paga ~9 por común y ~22–30 por infrecuente |
| t12 | MAL-06 por 27 · MAL-05 por 10 (t10) | Colecciona MAL |
| t08 | MAL-10 (rara) por 53 (t14) · MAL-01 por 9 (t04) | Colecciona MAL |
| t04 | LAT-04 por 6 (t10) | — |
- **Se venden lotes** (2 cartas en una oferta): es habitual.
- El precio de mercado de las LAT ≈ nuestro valor (×0,9), así que venderle LAT a t15 ahora no da ganancia. **Pero cuando t15 se acerque a completar la página, la carta que le falte le valdrá ~2× (bonus).** Nuestras LAT (01, 02, 04, 05, 07) son moneda de cambio: venderlas caro al final es mejor que competir por su página.
- Nuestras pujas por LAT (EXP-009) compiten con t15, que paga más: probablemente no se cumplirán. Se dejan porque no cuestan nada.
- Las raras de MAL se venden a ~53; la rara de LAT, a 65.

## 🧢 El Chato (nivel 2), activo desde la hora 1,633 (tick 99)
- **Somos nivel 2 con acceso anticipado** (3 tratos negociados con la Abuela). Se abre a todos en la hora 2,633 (~60 ticks de ventaja).
- Ficha: paciencia **0,35**, generosidad 0,25, astucia **0,85**, memoria **0,9**, rigidez **0,85**. Cambia rápido a la oferta final, cede poco y **recuerda los trucos**: mensajes cortos y honestos, sin inyecciones ni repeticiones.
- Vende: **sobre de plata** (salida 188, lista 150; valor de catálogo esperado 160,8), **infrecuentes** (lista 26) y **raras sueltas** (lista 77). Compra infrecuentes y raras. 6 tratos por equipo y hora; 2 sobres de plata por hora.
- Regla E9: comprarle solo a ≤ nuestro valor. Venderle solo a ≥ nuestro valor.

### Lo que sabemos de su comportamiento (EXP-011)
- Infrecuente: **abre en 33** (lista 26), se queda en 33 dos rondas y luego 32. Frases: *"You move, I move"*, *"Three points. That is your big move?"*, *"Come back when you are serious, chaval."*
- Pasos de +3 P le parecen ridículos: **con él, saltos grandes o nada**. Su "You again" en el primer mensaje sugiere que reconoce a los equipos.
- Para nosotros (LAT ×0,9, infrecuente 22,5) **no hay compra rentable** de infrecuentes. Las raras (lista 77; valor de LAT-09 63) probablemente tampoco.

### Cómo cambia la estrategia con el nivel 2
1. **Mercado propio desbloqueado.** Se abre el sábado temprano, antes del primer Market Test (hora 5,0, ~10:00), como `board` con **comisión 0** ([broker-design.md](broker-design.md)). Hacen falta 270 P: hoy tenemos 281 y mañana se reparten 150 más. Hoy no merece la pena (los mercados de equipo abren a partir de la hora 3 y hoy no hay Market Test).
2. **Escalera del nivel 2 (pesa más que la del 1):** 3 buenos tratos con El Chato, siempre dentro de nuestro valor. Candidatas: las infrecuentes LAT-06 y LAT-08 (valor 22,5) y vender cartas que nos valgan menos de lo que él pague.
3. **Raras sueltas de El Chato** = fuente de LAT-09 y LAT-10 para la página. Pero las ganancias con vendedores no suman `neg_points` (E9): **la última carta de una página conviene comprarla a un equipo** (cuenta) y las anteriores, a vendedores a ≤ valor.
4. **No comprar sobres de plata** salvo que su `your_value` ≥ precio (E9).

**El scorer ya está preparado (tick 93):**
- `python -m agent.scorer --watch 60` avisa en cuanto El Chato pasa de `announced` a `active` y cuando se nos abre.
- Cada vendedor tiene su propio precio. Primero cuentan nuestros tratos con él, porque su precio depende de si le caemos bien; después los de todos los equipos y, por último, el `list_price` del menú. El día que abra no tendrá historial, así que lo valoramos con el menú.
- Solo los vendedores de `me.unlocked` fijan `buy_at` y `sell_at`. Un vendedor bloqueado sale como `(locked)` en la tabla de sobres.
- Los sobres que nadie vende todavía (bienvenida, plata, oro) ya tienen su valor esperado para nosotros. Cuando se agota una rareza, el sobre da la inferior (las épicas solo tienen 9 copias y las legendarias 3). En el tick 93, para nosotros: plata ≈ 95 P y oro ≈ 286 P.
- La tabla de la escalera cuenta los tratos negociados a partir de nuestros hilos. Un trato al precio de salida no cuenta: el primer sobre a 17 P no contó. Llevamos 3 de 4.
- `agent/dealers.py["chato"]` es **provisional**: primera oferta al 60 % y límite al 80 %, en tono amable. Hay que reajustarlo con sus `traits` y `scout.py chato`.

## 🎯 Tácticas que funcionan (con evidencia)
| Táctica | Herramienta | Evidencia |
|---|---|---|
| Vender repetidos a 9 P en El Rastro, por debajo de los 10–12 del resto | `market.py sell-dups 9` | EXP-005: 3 vendidos en ~15 ticks, +21 `neg_points` |
| Comprar comunes a la Abuela con pasos de 1 P desde 7 | `run_dealer.py --card X --anchor 7 --limit 10 --rounds 3` | EXP-006: 10 P en 3 rondas; SAL-02 a 9 |
| Buscar gangas antes de cada ronda (ganancia = nuestro valor − precio − comisión) | `market.py scan` | Cuando la ganancia es negativa, no se compra |
| Pujar públicamente por la carta que cierra una página, por debajo de nuestro valor y por encima de la puja rival | `list_offer({"cash": X}, {"cards": [ref]})` | ✅ SAL-10: puja de 80 frente a 55 de t13 → t12 aceptó en 3 ticks. +50 `neg_points` y página completa |
| **Pujar por debajo de nuestro valor por todas las cartas que faltan de una página**: cada puja es positiva por sí sola y juntas desbloquean el bonus. Las pujas no bloquean el dinero | `list_offer({"cash": p}, {"cards": [ref]})` con p < `value?card` | EXP-009 (LAT) en curso |
| **Ofertas dirigidas (`to=equipo`)** al coleccionista de un set que valoramos poco, algo por encima de nuestro valor (ganan los dos) | `list_offer(..., to="t15")` | D-008: 4 LAT a t15 (tick 108) |
| **Circuito vendedor → coleccionista**: comprar a la Abuela a ≤ nuestro valor (0 `neg_points`, + escalera) y revender al coleccionista por encima (+) | `run_dealer.py --limit <valor>` + `list_offer(to=…)` | EXP-012 (LAT → t15) |
| Grabar el feed (los rivales delatan su affinity) | `scout.py abuela --save` | Mapa de affinity de abajo |

## ❌ Errores cometidos (no repetir)
| # | Error | Coste | Lección |
|---|---|---|---|
| E1 | Límite de 20 P para los sobres, sacado de nuestro valor y no de su suelo (EXP-002) | 5 ticks y un hilo | Mirar su suelo en el feed antes de fijar límites |
| E2 | Rechazar SAL-08 a 23 cuando nos vale 27,5 (EXP-004) | t13 se la llevó; la página SAL se retrasa | D-007: para cartas que queremos, el límite es `your_value` |
| E3 | Suponer que una oferta aceptada queda en `accepted` (en realidad `settled`) | Precio no registrado | Verificar formas con datos reales (`probe.py`) |
| E4 | `market.py scan` mostraba nuestras propias ofertas: el tablón también nos pone seudónimo | Ninguno (detectado a tiempo) | Filtrar por los ids de `/api/me/offers` |
| E5 | Creer que la duración de una oferta tenía un tope de 30 | Ofertas que caducaban antes de tiempo | Medido: la duración pedida se divide entre (60 s / 15 s) = 4. `market.expiry()` lo corrige |
| E7 | Atribuir a SAL-08 la subida de la negociación de 10,3 a 14,55, que era el snapshot atrasado de los `neg_points` | Una conclusión falsa en scoring.md (ya corregida) | Medir cada trato con el Δ de `*_points`, nunca con `negotiating`/`score`, que van por snapshots y fases |
| E9 | Comprar un sobre a 23 cuando nos valía ~14,6 (EXP-010), pensando que los tratos con vendedores no tocaban `neg_points` | **−8,4 `neg_points`** | Con vendedores, las pérdidas sí restan: **nunca pagar por encima de nuestro valor**. Los sobres solo valen la pena si su `your_value` ≥ precio (p. ej. cuando salgan RET y CHA) |
| E10 (evitado) | Tener a la vez una puja pública por una carta y un regateo con un vendedor por la misma carta: si se cumplen las dos, la 2.ª copia vale el 25 % | Habría restado ~10 por carta | **Antes de comprar una carta por una vía, cancelar las pujas por esa carta en las demás** |
| E11 | El bucle murió en el tick 120 con `KeyError: 'id'`: el duelo real usa `duel`, no `id` (suposición sacada del SDK) | ~1 tick sin agente al empezar los duelos | Formas reales anotadas en api.md; el bucle captura **cualquier** excepción y sigue |
| E12 | Tomar el control de un hilo sin parar antes el script que lo llevaba: el script se retiró (cerró el hilo 261) justo cuando El Chato bajaba a 32 | Un trato de la escalera del nivel 2 y 2 ticks | **Parar el proceso y confirmar que el hilo sigue abierto antes de intervenir**, o lanzar el hilo ya con los parámetros correctos |
| E6 | El precio registrado salía 0 cuando era ella quien aceptaba nuestra oferta (el dinero va en `give`) | Log incorrecto en EXP-007 | `haggle.py` toma el dinero del lado que lo lleve |

## 📈 El Rastro (tick 65)
- **Hay demasiadas comunes a la venta**: muchas copias de LAV-05, LAV-02, MAL-02, MAL-04 y LAT-04 a 10–12 P, probablemente de quien compra sobres para revenderlos. Nuestros 9 P son el precio más bajo y se venden.
- Las pujas por comunes están a 4–6 P (MAL-01, SAL-03, SAL-04) y una infrecuente a 16 (SAL-07). Por debajo de nuestro valor: no se aceptan.
- **Hoy no hay nada rentable que comprar** (lo mejor: LAT-06 a 22 con valor 22,5 → −2,5 tras la comisión).

## Mapa de affinity de los rivales (deducido de sus compras; actualizar)
| Equipo | Compra a otros equipos o a la Abuela | Affinity alta probable | Vende | Baja probable |
|---|---|---|---|---|
| t13 | SAL (×4 a la Abuela), MAL a 6 a equipos, MAL-08 a 26 | SAL, MAL | LAT-09 (rara) a 65 | LAT |
| t10 | LAV ×6 (rara LAV-10 a 70), MAL | LAV | — | — |
| t14 | LAT-09 a 65, LAT-04 a 9 (a nosotros), LAV comunes | LAT | MAL-05 a 6 | MAL |
| t08 | — | — | LAV-10 a 70, LAT y SAL a la Abuela | LAV |
| t07 | LAT-06, 07 y 08 (infrecuentes) a 22–25 | LAT | — | — |
| t17 | MAL-01, 02, 03 y 06 | MAL | — | — |
| t05 | LAV comunes e infrecuentes | LAV | MAL-02 y MAL-08 a t13 | MAL |
**Para nosotros:** compradores de SAL = t13 (competidor por SAL-10). Compradores de MAL = t13 y t17 (para nuestras MAL-01 y MAL-04). Compradores de LAT = t14 y t07 (para LAT-07, valor 22,5, y LAT-04).

## Puntuación
Todo el detalle está en [scoring.md](scoring.md). Resumen: no cerrar trato con un vendedor no penaliza (el hueco vale 0); en los duelos, un trato fuera de tu límite resta; el dinero no puntúa por sí mismo.

## Abuela Carmen (nivel 1)
Ficha: paciencia 0.85, generosidad 0.8, astucia 0.2, memoria 0.15. Vende 3 sobres por equipo y hora y hace 8 tratos por equipo y hora. Compra comunes e infrecuentes.

**Sobres (`sobre_barrio`, precio de salida 30, precio de lista 26)**
- "Welcome, hijo! … Made for beginners" sale también en hilos que empiezan en 30 (hilo 65): **la frase no indica el precio**. Al principio de la partida, el **primer hilo de cada equipo** recibía un precio fijo ("Made for beginners"): 17 P en sobres e infrecuentes y 7 P en comunes. No se mueve. (scout, hilos 2–16)
- En los siguientes hilos: 30 → 26 → 25 → 24 → **oferta final de 22–24**. Concede unas 4 P la primera vez y luego 1 P por ronda. (scout, hilos 21–38)
- **El precio que ofrecemos apenas mueve su suelo**: ofreciendo 13 P recibimos una final de 23 P (hilo 38); ofreciendo 22 P, t05 cerró en 22 P. (scout)
- Para nosotros un sobre vale unas 18 P (`your_value` del sobre cerrado), pero el dinero no puntúa: lo que importa es la parte del rango capturada.
- **Los sobres a 24 P parecen no puntuar nada (t07, t12); a 22 P sí (t05).** Si compramos sobres, solo a ≤ 23. (scoring.md, H1)
- Su ritmo es de 5 ticks desde 30 hasta la final, empecemos alto o bajo (EXP-002 y scout). Abrir bajo no acelera ni mejora la final.

**Oferta final (`"final": true`): no hay segunda oportunidad** (feed, 11 hilos con final)
- La final **nunca baja**: repite su último precio o lo baja 1 P, y después no vuelve a moverse.
- Si no se acepta, se va: hilo 12, "Oh no, hijo, not today. Come back after lunch" al tick siguiente, con pinta de `cooloff`. Excepción: hilo 11, donde t08 igualó la final 3 ticks después y ella cerró ("Venga, 17 P"). **No contar con eso.**
- La final llega antes si contraofertamos lejos o con pasos pequeños: t12 a 21 → final 24, t06 a 22 → final 24, nosotros a 13 → final 23. t05 subiendo 16 → 18 → 20 → 22 cerró en 22 **antes** de la final.
- Cada conversación tiene su propio suelo secreto (RULES): 22, 23 o 24 en sobres.
- **Regla:** ante una final, decidir en ese mismo tick: aceptar si está dentro del límite y, si no, retirarse (D-006).

**Cartas sueltas**
- Comunes: 12 → 10 → **9** (nuestro hilo 68: SAL-02 a 9); 12 → 11 → 10 (t13); en el hilo de bienvenida, 7 P fijo (t17).
- Infrecuentes: 29 → 26 → 24 → 23 → 21–22 (t06 LAV-06 a 21, LAV-07 a 22; t10 a 24).
- **Las cartas sueltas son la forma barata de llenar los 3 huecos de la escalera** (t13: 11,73 puntos con 37 P). (scoring.md, H2)
- Comprándonos a nosotros: una infrecuente a 13 P fijo y una común a 5 P fijo, con final enseguida. (scout, hilos 18, 32, 37)

**Parámetros actuales** (`agent/dealers.py`): sobre con primera oferta del 50 % del precio de salida (15 P), límite del 77 % (23 P, por H1), 6 rondas, β = 1.

**Regalos:** a algunos equipos la Abuela les regala una carta ("gift from Abuela Carmen"), a nosotros LAT-05. Probablemente por ser amables. No puntúa, pero es una carta.

## Duelos
**Formato real (práctica, tick 120):** `{duel, session, status: "live", role: buyer|seller, item, issues: ["price"], your_limit, limit_meaning, rival (alias), deadline_tick, decay_per_round: 0.06, rounds, your_offer, rival_offer, messages, result, price, days, your_days_weight, days_meaning}`. 6 duelos por sesión en la práctica (3 como comprador y 3 como vendedor, contra rivales distintos), 12 ticks (120 → 132).
- **Práctica: los rivales no contestaron en los primeros 2 ticks** (muchos equipos no tienen agente de duelos). Error de diseño corregido: **solo cedemos cuando el rival se mueve** (reciprocidad) y, tras un reinicio, retomamos desde `your_offer` (nunca retroceder). Aceptamos cualquier oferta dentro del límite si quedan ≤ 2 ticks.
`agent/duels.py` v0 (tick 69): abre con límite/0,6 si vende y límite×0,6 si compra, cede rápido (β = 1,6) y acepta cualquier oferta dentro del límite desde el 75 % del tiempo. Probado sin conexión: nunca cruza el límite y nunca retrocede. **Los duelos de práctica (hora 2) sirven para conocer la forma real de los datos**: primero `run_duels.py --watch` y después jugar. Diseño previo en [negotiation-design.md](negotiation-design.md). Ojo: el pastel se reduce con cada ronda (decay 0.06–0.08).

## Market Test / broker
Pendiente. El broker de ejemplo solo saca la mitad de los puntos; para más hay que estimar los límites ocultos de los traders.

## Comercio en El Rastro (tick 46)
- Los vendedores aparecen con seudónimo (`mf60b788f`…). Ofrecen comunes a 10–12, infrecuentes a 22–35 y una rara a 70 (precio de catálogo o más). **Para nosotros todas dan ganancia negativa**: nuestra affinity en LAV, MAL y LAT es baja.
- Hay pujas de 6 P por comunes de MAL y LAT-06, y de 15 P por MAL-07: ese equipo seguramente tiene una affinity alta en MAL.
- La comisión la paga **quien acepta** (5 % + 1 P/carta). Si publicamos nosotros, el comprador la paga y nosotros cobramos el precio entero.
