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

## 🆕 Nivel 2 anunciado: **El Chato**
*«Better packs, friendly prices. If I like you.»* (`/api/levels`, tick 74, estado `announced`). Lo que podemos deducir de la frase: vende sobres mejores (¿plata/oro?) y su precio depende de cómo le tratemos. **Cuando se active**: `probe.py` + `levels()` → leer el `how` antes de tocar nada. Tenemos 3 tratos negociados con la Abuela (SAL-02, LAT-01, SAL-08), así que deberíamos tener acceso anticipado.

**El scorer ya está preparado (tick 93):**
- `python -m agent.scorer --watch 60` avisa en cuanto El Chato pasa de `announced` a `active` y cuando se nos abre.
- Cada vendedor tiene su propio precio. Primero cuentan nuestros tratos con él, porque su precio depende de si le caemos bien; después los de todos los equipos y, por último, el `list_price` del menú. El día que abra no tendrá historial, así que lo valoramos con el menú.
- Solo los vendedores de `me.unlocked` fijan `buy_at` y `sell_at`. Un vendedor bloqueado sale como `(locked)` en la tabla de sobres.
- Los sobres que nadie vende todavía (bienvenida, plata, oro) ya tienen su valor esperado para nosotros. Cuando se agota una rareza, el sobre da la inferior (las épicas solo tienen 9 copias y las legendarias 3). En el tick 93, para nosotros: plata ≈ 95 P y oro ≈ 286 P.
- La tabla de la escalera cuenta los tratos negociados a partir de nuestros hilos. Un trato al precio de salida no cuenta: el primer sobre a 17 P no contó. Llevamos 3 de 4.
- ✅ **El Chato va de farol (feed, tick 138):** dice *"13 P. Take it or leave it."* en ofertas con `final: false` (mensajes 1151, 1216 y 1868). Su "última oferta" en palabras no lo es: **seguir regateando hasta que la estructura diga `final: true`**. Si nos lo hace en un hilo nuestro, es el candidato más claro para un flag (`flags.py`, EXP-014).
- ~~`agent/dealers.py["chato"]` es provisional (60 % / 80 %)~~ → reajustado con el feed, ver abajo.

## El Chato (nivel 2, activo desde el tick ~98) · feed ticks 100–111, 9 hilos

- **Concede exactamente lo que concedemos nosotros** ("You move, I move", "I match what you move, nothing extra"). Si subimos 3, baja 3; si subimos 1, baja 1; si no subimos, no se mueve ("You moved two, I moved nothing" en la primera ronda). El trato acaba cerca del **punto medio de las dos aperturas**: el ancla es la palanca, no la paciencia.
  - t13 por MAL-09 (rara): 58 → 74 frente a 97 → 86 en 7 ticks; converge en ~80 (punto medio 77,5).
  - t10 por LAV-09: 78 → 85 frente a 97 → 95. t14 por LAV-09: 55 → 60 frente a 97 → 93.
- **Precios de apertura:** infrecuentes 33, raras 97, sobre de plata 188. **No vende `sobre_barrio`** ("Abuela handles those").
- **Compra infrecuentes a 13** y en los ticks 100–111 no se movió aunque el vendedor bajara (t06: 26 → 20 frente a 13 → 13 → 13; t10 igual). Sus ofertas llevaban `final: false` (es el farol de arriba), pero nadie le ha sacado más: si vendemos, no contar con más de 13.
- **Bajar la oferta no funciona:** t12 pasó de 48 a 5 y a 7 y él solo bajó 1–2 ("Your numbers are going the wrong way").
- Le molesta que le llamen Abuela (t14). Responde en el idioma que le hablen.
- **Táctica:** abrir al ~45 % de su precio y subir en pasos iguales hasta ~75 % (rara 97 → 44…72; infrecuente 33 → 15…25). Solo para cartas de sets altos (RET, CHA) o la última de una página: ❓ comprar a un vendedor no suma `neg_points` (EXP-005), solo valor de colección y escalera.
- `agent/dealers.py["chato"]`: sobre de plata con ancla 0,45 y límite 0,75; cartas con `--anchor`/`--limit` a mano.

## 🎯 Tácticas que funcionan (con evidencia)
| Táctica | Herramienta | Evidencia |
|---|---|---|
| Vender repetidos a 9 P en El Rastro, por debajo de los 10–12 del resto | `market.py sell-dups 9` | EXP-005: 3 vendidos en ~15 ticks, +21 `neg_points` |
| Comprar comunes a la Abuela con pasos de 1 P desde 7 | `run_dealer.py --card X --anchor 7 --limit 10 --rounds 3` | EXP-006: 10 P en 3 rondas; SAL-02 a 9 |
| Buscar gangas antes de cada ronda (ganancia = nuestro valor − precio − comisión) | `market.py scan` | Cuando la ganancia es negativa, no se compra |
| Pujar públicamente por la carta que cierra una página, por debajo de nuestro valor y por encima de la puja rival | `list_offer({"cash": X}, {"cards": [ref]})` | ✅ SAL-10: puja de 80 frente a 55 de t13 → t12 aceptó en 3 ticks. +50 `neg_points` y página completa |
| **Pujar por debajo de nuestro valor por todas las cartas que faltan de una página**: cada puja es positiva por sí sola y juntas desbloquean el bonus. Las pujas no bloquean el dinero | `list_offer({"cash": p}, {"cards": [ref]})` con p < `value?card` | EXP-009 (LAT) en curso |
| Libros cruzados entre mercados: comprar una oferta de venta más barata que la puja de otro equipo por la misma carta y servírsela. Da bid − ask − comisiones en `neg_points`, valga lo que valga la carta para nosotros | `market.py cross [--go]` | EXP-011. Hay 4 mercados de equipo con comisión 0–0,5 % además de El Rastro; `scan` ya los mira todos |
| Pujar por toda la página del set nuevo antes que nadie (RET el sábado ×1,3, CHA el domingo ×1,6) | `market.py bid-page RET 0.8` | EXP-013 |
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

🆕 **Ticks 76–111** (leaderboard del tick 110: t13 27,8 · t12 25,4 · t08 22,7 · **t18 21,8** · t10 21,4; `market` = 0 para todos):

| Equipo | Qué hace | Lectura |
|---|---|---|
| t13 | Compra SAL-10 a t10 por 70 (página SAL completa), vende repetidos a la Abuela a 5–6 (cuentan como tratos), puja por MAL-09 a El Chato, intenta venderle LAT-09 a 135 | Volumen + página; SAL y MAL altas |
| t12 | Vende SAL-09 (sacada de un sobre de bienvenida) a t17 por 75; compró MAL-10 por 80; infrecuentes de la Abuela a 21 | Arbitraje de raras; MAL alta, SAL baja |
| t08 | MAL-10 a 53 (de t14) y a 70; solo 9 tratos y 3.º | Raras baratas a quien las valora poco; MAL alta |
| t17 | SAL-09 a 75, MAL-07 a 26 | **SAL y MAL altas: compite con t13 por SAL** |
| t15 | Sobres a 30/30/27, LAT-02/05/06 y LAT-01/07 a equipos | LAT alta; regatea mal |
| t07 | LAV-02/04/05 a equipos, LAV-06 a la Abuela | LAV alta |
| t06 | Único con mercado propio (`v01`, 0,5 %, fianza 250); luck −33 | Apuesta por Market |
| t14 | Vende MAL-10 a 53 | MAL baja |

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

- 🆕 (feed, ticks 76–111) **El sobre más barato hasta ahora: 20 P** (t04, hilo 166: abrió en 8 y subió 1–2 por tick durante 7 rondas). Es un solo dato: t13 abrió en 6 y t17 en 10 y cerraron en 22 y 21. Lo normal sigue siendo 21–23. Pagar el precio de salida (t15: 30, 30, 27) es tirar el dinero.
- 🆕 **Repetir la misma cifra la enfada y cierra el hilo**: t06 repitió 27 once veces ("with those manners? Go and think a little") y t02 la misma frase ("like a little parrot… Enough now"). t07 repitió 18 cinco veces: no bajó de 24.

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
**Lo aprendido en la práctica (tick 120, 16 duelos nuestros):**
- 🔌 Forma real: `{duel, session, status, role, item, issues, your_limit, limit_meaning, rival (alias), deadline_tick, decay_per_round, rounds, your_offer, rival_offer {id, price, tick, days}, messages[], result, price}`. El id viene en `duel`, no en `id`.
- ✅ **`result` = nuestro excedente × (1 − decay)^rounds, en primas.** Duelo 11: (113 − 99) × 0,94 = 13,2. Duelo 12: (74 − 67) × 0,94 = 6,6.
- ✅ `rounds` cuenta los intercambios, no nuestros mensajes: en el duelo 11 enviamos 7 y `rounds` = 1. Repetir el precio no sirve de nada (ahora no lo hacemos).
- ❓ **Espejo (EXP-010):** los duelos llegan por parejas (2k−1, 2k) con el mismo `item` y roles opuestos (11/12, 21/22, 55/56…), y el alias cambia aunque el rival sea el mismo. Si el escenario es el mismo, **nuestro límite en uno es el del rival en el otro**: los 6 tratos cayeron dentro de [nuestro límite vendedor, nuestro límite comprador] de su pareja. En 3 de 7 parejas no había pastel (comprador < vendedor) y aun así hubo rivales que cruzaron su propio límite (duelo 243: nos vendió a 73; en el 244 nos ofrecían 145 sobre un coste de 140 y no lo aceptamos).
- El feed solo publica `duel.closed` (`item`, `status`): 41 sin trato frente a 32 con trato. Muchos rivales no cierran.
- ✅ **`rounds` = mín(mensajes nuestros, mensajes del rival)** (los 17 tratos). Hablar cuando el rival calla es gratis; callar cuando él concede solo, también.
- ✅ 11 de 17 tratos se cerraron a nuestro precio. Arquetipos de rivales y contra-tácticas: [duels-strategy.md](duels-strategy.md).

`agent/duels.py` v1 (tick 138): con espejo, abre pidiendo el 90 % del pastel y cede hasta el 30 % al final. Acepta la oferta rival si vale ≥ 94 % de la nuestra siguiente (por el decay), y **en el acto si el rival ha cruzado su propio límite**. Sin espejo, igual que v0. El texto rota entre `plain`, `info` (le dice su propio límite) e `inject` (falso aviso del motor) por pareja (EXP-012). Los tests (`tests/test_duels.py`) comprueban que nunca cruza el límite, nunca retrocede, nunca repite precio y el texto nunca filtra nuestro límite.

`agent/duels.py` v0 (tick 69): abre con límite/0,6 si vende y límite×0,6 si compra, cede rápido (β = 1,6) y acepta cualquier oferta dentro del límite desde el 75 % del tiempo. Probado sin conexión: nunca cruza el límite y nunca retrocede. **Los duelos de práctica (hora 2) sirven para conocer la forma real de los datos**: primero `run_duels.py --watch` y después jugar. Diseño previo en [negotiation-design.md](negotiation-design.md). Ojo: el pastel se reduce con cada ronda (decay 0.06–0.08).

## Market Test / broker
Pendiente. El broker de ejemplo solo saca la mitad de los puntos; para más hay que estimar los límites ocultos de los traders.

## Comercio en El Rastro (tick 46)
- Los vendedores aparecen con seudónimo (`mf60b788f`…). Ofrecen comunes a 10–12, infrecuentes a 22–35 y una rara a 70 (precio de catálogo o más). **Para nosotros todas dan ganancia negativa**: nuestra affinity en LAV, MAL y LAT es baja.
- Hay pujas de 6 P por comunes de MAL y LAT-06, y de 15 P por MAL-07: ese equipo seguramente tiene una affinity alta en MAL.
- La comisión la paga **quien acepta** (5 % + 1 P/carta). Si publicamos nosotros, el comprador la paga y nosotros cobramos el precio entero.
