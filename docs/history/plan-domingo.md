# Plan del domingo 4 oct · Chamberí (último día)

*Escrito la noche del sábado al domingo, con el juego cerrado. Cada cifra sale de los datos o de los ids de [knowledge.md](knowledge.md). Lo que no se pudo comprobar dice **sin verificar**. Este documento sustituye a `DOMINGO.md` (que ahora solo remite aquí).*

**Lo esencial en 6 líneas**
1. El código bueno está en la rama `night-build` (último commit comprobado `0daffe5`, 883 tests OK). El bot vivo (pid 34804) **todavía lleva el código del sábado**: hay que desplegar antes de las 09:00 (§4) y, si se llega tarde, en cuanto no haya un duelo vivo y nunca después de las 10:55 (§4.2).
2. Escenario más probable (C): a las 09:00 empiezan la ronda 3 y CHA; Duels III a las ~11:00; cierran los puestos y empieza la Gran Final a las ~14:00; todo se congela a las 15:00.
3. El arnés calcula solo el fin del día de dealers (13:55) y el endgame (14:25) a partir del reloj de pared y del calendario vivo. Funciona en los tres escenarios y no hay que tocar `config/plan.json`.
4. A las 09:00:30, `python3 bazaar.py clockcheck` dice el escenario.
5. Nada de venue `board`. El mercado se juega con el puesto v18 y con anuncios a mano.
6. Lo manual (huevos, ventas a Pilar, denuncias, anuncios) va **con tu OK, uno a uno**, con los comandos de §6.

---

## 1. Resumen de la noche

### 1.1 Qué se auditó
- **El código** (`harness-v2` `5ee5593`) pasó por cinco revisiones: duelos, seguridad de la Gate, plan y tácticas, simulación del domingo entero (escenarios A, B y C, con ticks de 15 s y el estado real del sábado) y documentación.
- **Los datos del sábado:** diario (`logs/run/journal.jsonl` y `snap/`), feed archivado, `untrusted.jsonl`, `bench_book.jsonl`, `eggs.jsonl` y los snapshots de las 23:59 (`me`, `leaderboard`, `schedule`, `clock`…). Los hechos nuevos están en knowledge S-17..S-33.
- **Los documentos de Rubén:** cada afirmación tiene veredicto en [incoming/REVISION.md](incoming/REVISION.md). Lo más importante: **sí tenemos venue** (el puesto v18, con la mitad de los puntos del banco); **las denuncias ya se hicieron** (3 de 9 puntuaron); **el huevo de los Pícaros ya lo tenemos**; **"oro de Moscú" está agotado** (LAT-13 es de t02). Que "el domingo de 09:00 a 12:17 cuenta para la ronda del sábado" solo vale en el escenario A, el menos probable.
- **El calendario:** con el horario del viernes (`logs/harvest/schedule.json`), el snapshot del tick 170 del sábado y el schedule de las 23:59 (§3).

### 1.2 Fallos encontrados y arreglados (rama `night-build`)
Cada arreglo lleva su test de regresión, y se comprobó que el test falla con el código anterior.

| Tema | Qué fallaba | Arreglo |
|---|---|---|
| **Fin del día (crítico)** | `day_end` y `endgame` eran horas de juego fijas (19,283 / 18,783). Si el reloj saltaba, los hilos con dealers se cerraban a las ~11:38. Si había pausas o se abría tarde, el cierre no llegaba nunca. Un `day_closes sat` rancio podía cerrar el domingo | `4e68562`, `ae488b3`, `db9f3bd`, `f4a2871`: fin de dealers = mín(cierre, cierre de puestos) − 5 min; endgame = cierre − 35 min. El cierre sale de `clock.closes` (pared) y del calendario vivo. `5be0384`: la hora de cierre de puestos se guarda en `state/day_times.json` para que sobreviva a un reinicio. `176b840`: fila `param` al arrancar. `c171798`: `clockcheck` imprime todo |
| **Duelos: días** | El sábado mandábamos siempre 5 días y exigíamos un margen de peor caso de ~15 P (S-27). Un `days_meaning` redactado de otra forma podía volver a dar el signo al revés sin avisar | `55c25fd`: valor = s·(p − L) + signo·\|w\|·d; vendedor sin penalización (con suelo en el límite), comprador \|w\|·d. `70a487c`: si el signo leído contradice al papel, se usa −1 (conservador) y salta una alarma. `9d47e85`: alarma si el texto no se entiende (entonces decide el papel) |
| **Duelos: cierres perdidos** | Con un rival callado en otros días, ningún precio era a la vez monótono y no peor: esperábamos hasta el no_deal. La única aceptación del tick se la podía comer un dealer. Los duelos sin cupo de aceptación no recibían ni mensaje | `19ce06c` (devolver al rival su propio par precio/días), `b0e128b` + `8789d3f` (retener un tick una aceptación de dealer si hay un duelo a punto de vencer), `916ed53` (mensaje en vez de nada) |
| **Duelos y escalera** | Con ≥ 4 duelos vivos no se abrían hilos con dealers. El domingo hay justo 4, así que la escalera se paraba ~1 h. Los descartes no dejaban rastro (así se perdieron 12 órdenes manuales el sábado) | `3dd3ed6`: solo con **más de 4**; una orden manual nunca se bloquea; cada descarte deja fila `dropped` |
| **Velocidad a 15 s** | La relectura de mitad de tick lo releía todo; 2,5 req/s se quedaba corto | `688b385` (relectura reducida), `3f4bd4b` (3,5 req/s con ráfaga de 8; paneles a 1 req/s) |
| **Caja y cupos** | Una compra liquidada se contaba dos veces durante 2 ticks. Las tácticas en pausa gastaban la aceptación y los cupos | `77ff224`, `414da2e` |
| **SAL-11 a la venta** | Tras un reinicio sin catálogo, la higiene cancelaba la oferta de SAL-11 (19:44 y 22:12) | `d839634` |
| **CHA** | Las raras CHA no tenían un respaldo que funcionara; los extra_needs se abrían antes que las cartas de página y en la ronda 2 | `b5d2f96`, `e2269d1` (Pícaros ≤ 64, El Chato ≤ 93), `d9401d8`, `5cb6082` (extra_needs detrás de la página y `min_round` 3) |
| **El Rastro** | J13 podía vender la única común de CHA. La compra de cualquier carta del final podía gastar la caja de la subida del closer. Un intercambio podía llevarse una carta reservada | `a34e7c7`, `2bfcb16` (`resupply_min` 999), `40bd4de`, `3a95137`, `e9ea3bf` |
| **Caja del closer frente a las épicas** | Con los topes, CHA-11 (≤ 170) y RET-11 (≤ 150) podían dejar ~61 P de 705, menos que la puja del closer (72 a 9/10, 102 en el endgame). Un +50 con un equipo vale más que un 4.º candidato a L4 (solo cuentan 3) | `0daffe5`: el hilo de un `extra_needs` se topa en `cash_free` − reserva del closer (su Need + 30 antes del endgame, menos nuestra puja ya puesta). Las cartas de la página no se topan |
| **Ventas a mano** | J5 listaba las sueltas que hacen falta para las ventas a mano (escalera y huevos) | `49eb183`, `f0352eb` (`hand_sales`, también LAT-06 #1105 y LAT-02 #1103) |
| **Bloqueos de dealer** | `persona_budget` y `sold_out` no bloqueaban al dealer | `2512ce4`: hasta el final de la hora de juego |
| **Fusión de `audit-fixes`** | Fallos ya arreglados en otra rama: `do` sin `--live` que enviaba de verdad junto al runner, la final trampa de los Pícaros, el closer que valoraba su puja como 2.ª copia, bucle de pausa al conciliar, flatten | `249808c` (fusión), `ede86fe` (caché del Valuer por contenido del catálogo) |
| **Herramientas** | — | `ad3b0a7`, `c9170ea`, `b7c1359`: `ladder_sell.py`, `egg_carrier.py`, `flag_candidates.py`, `announce_candidates.py`. `a199fc5`: líneas de huevo del domingo. `e2269d1`: `sim/sunday.py`. `bf7d02c`: `status` avisa `STALE?` |

### 1.3 Lo que quedó fuera, y por qué
- **Compras a Ernesto (nivel 5).** Nadie ha visto su precio de una épica. Una legendaria cuesta ≥ 729 y CHA-12 nos vale 720, y sus pujas por épicas (113–126) quedan por debajo de nuestros valores. Sin trato con ganancia posible, el nivel 5 se queda en 0.
- **Días por debajo del límite como vendedor:** no se adoptó. RULES dice que un trato fuera del límite pierde puntos, y ningún trato observado salió de él.
- **Mejoras de `egg_watch.py`** (más pistas) y `STALE` en `live_monitor.py`. No urgen: `status` ya avisa.
- **Volver a elegir el closer** tras un reinicio muy temprano (E2E-6). Es raro y solo cambia una compra barata por una puja.
- **Sin respaldo de dealer para la carta de cierre** (E2E-7): por diseño, el cierre con un equipo es el +50.
- **`flag_one.py` y `announce_stall.py`** (en el scratchpad, fuera del repo) no miran STOP ni escriben en el diario. Por eso cada uso se apunta a mano en [handoffs/HANDOFF-domingo.md](handoffs/HANDOFF-domingo.md).
- **Limpieza de código sin conectar** (`pages.protect_sets`, `Calibrator.recheck`, `duels.e16_settled`), un test de arquitectura para los scripts de la raíz y archivar `observe_performance.py`. Nada de eso afecta al juego. Está en [TODO.md](../TODO.md).

### 1.4 Tests
- `night-build` `0daffe5`: **883 tests OK, 2 omitidos** (129 s, repetido esta noche). El commit siguiente, `37e3e7e`, solo cambia un docstring de `announce_candidates.py`.
- `selftest` en verde en todas las etapas en el worktree de `night-build`. **En la máquina A hay que repetirlo** tras la fusión, porque cambia el `code_hash` (§4).
- La fusión de `night-docs` sobre `night-build` es limpia y no toca código (comprobado en un clon aparte).

---

## 2. Situación y qué hace falta para ganar

**Clasificación al cierre del sábado** (leaderboard 23:55; negociación / mercado):

| Puesto | Equipo | Total | Neg. | Merc. | Venue | Notas |
|---|---|---|---|---|---|---|
| 1 | t10 | 37,58 | 25,08 | 12,5 | v07 board + broker | 62 tratos, 3 insignias, orgánico al tope |
| **2** | **t18** | **31,26** | **23,76** | **7,5** | **v18 puesto** | 40 tratos, bench 0,5, mm 0 |
| 3 | t05 | 30,49 | 22,99 | 7,5 | v10 puesto | |
| 4 | t12 | 30,42 | 23,17 | 7,25 | v02 board | |
| 5 | t03 | 29,67 | 23,59 | 6,08 | v20 | la mejor negociación de la ronda 2 (≈ 28,1, S-32) |
| 6 | t06 | 28,76 | 16,90 | 11,87 | v01 board | orgánico ≈ 0,87 |
| 7 | t14 | 27,67 | 18,37 | 9,30 | v25 | |

**La cuenta (S-23):**
- Nota final = (0,5 · R1 + R2 + R3) / 2,5 = **(1,5 × nota actual + R3) / 2,5**, donde R3 es la nota de la ronda 3 (máximo 30 + 30).
- **Para pasar a t10**, nuestra R3 tiene que superar a la suya en más de 1,5 × 6,32 = **9,5 puntos de ronda**.
- Si los dos repetimos la ronda 2 (t10 ≈ 27,2 + 18,75; nosotros ≈ 26,1 + 11,25), acabaríamos con t10 ≈ 40,9 y t18 ≈ 33,7.
- **Ojo a los de atrás.** Para pasarnos les basta con superar nuestra R3 por poco: t05 por 1,2 puntos de ronda, t12 por 1,3, t03 por 2,4, t06 por 3,8 y t14 por 5,4. **El 2.º no está asegurado.**

**Palancas en la ronda 3.** Escala aproximada del sábado: 1 punto de tablero el sábado ≈ 1,5 de ronda; 1 de ronda ≈ 0,4 de nota final.

| Palanca | Puntos de ronda | Cómo | Riesgo |
|---|---|---|---|
| Trato con equipo al tope (+50) | ≈ +2,9 cada uno (LAT-10 a 72 dio ≈ +1,9 de tablero, S-30) | El closer de CHA (común que nos vale 122, a ≤ 72, y luego ≤ 102). CHA comprada a equipos muy por debajo del valor: una rara CHA (V 112) a ≤ 62 da +50 | Que nadie venda. Es la mejor palanca que depende de nosotros |
| **Orgánico en v18** | **+7,5 × m, la palanca más grande.** El orgánico va con la raíz cuadrada, así que los primeros tratos pesan mucho: t16 sacó m ≈ 0,53 (+4,0 de ronda) con 2 tratos dirigidos en su puesto (80 P), y t09 m ≈ 0,68 con 6 tratos en v21 (si su banco fue 0,5) | Anuncios cada ~10 min con parejas reales o con el reclamo de comisión 0 (§5.3) | El sábado v18 hizo 0 tratos y casi no hubo parejas entre no rivales |
| SAL-11 (V 198) | **≈ 0 a 245.** Lleva publicada desde el tick 1125 (renovada en 1192, 1327 y 1425, oferta 20117) y nadie la compró en ~300 ticks. Los equipos pagaron 195–216 por épicas: RET-11 a 216 (t1245), MAL-11 a 195 (t1264), SAL-11 a 207 (t1296). A 210–215, +12..+17 neg ≈ +0,7..+1,0 | Decides tú (§6 #3): republicar a 210–215 para equipos, o Pilar con suelo 199 | Pilar nunca ha pagado más de 199 por una épica |
| Denuncias de nivel A | ≈ +0,6 cada una (+10 neg) | ≤ 3, a mano (§5.5) | Sin verificar si el tope de 3 es por ronda |
| Escalera | +0,044 de escalera ≈ +0,4 de ronda | 12 huecos alcanzables (niveles 1–4) | Ernesto (nivel 5) no da trato |
| Sobrantes a equipos | +2..+19 neg cada uno (precio − V; quien acepta paga la comisión): SAL-05 #1104 (V 2,8), LAT-02 #1103 (V 2,2), LAT-06 #1105 (V 5,6) | J5 los publica sola: SAL-05 en cuanto se reanuda `rastro`; LAT-02 y LAT-06 están en `hand_sales` (reservadas para Pilar y El Chato) hasta el fin de dealers | El sábado LAT-02 a 11 y LAT-06 a 25 se publicaron 11 veces cada una y nadie las compró |
| Duelos | La parte media de duelos **baja con cada duelo sin trato** (S-27) | Código nuevo (§5.2) | Duels II nos costó puestos |

Escala de la tabla: +50 neg ≈ +2,9 de ronda, así que 1 neg ≈ 0,058 de ronda.

**Camino a la victoria, con números:**
- Ronda 2 aproximada (S-32): t10 ≈ 27,2 + 18,75 = **45,95**; nosotros ≈ 26,1 + 11,25 = **37,35**. Si los dos repetimos, la distancia final crece.
- **Nuestro techo en la ronda 3:** negociación ≤ 30 (la mejor de la ronda 2 fue 28,1, t03) + mercado ≤ 18,75 (puesto: banco 0,5 = 11,25, más orgánico al tope 7,5) = **48,75**. Aun en el techo, t10 tendría que bajar de 39,3 (48,75 − 9,48).
- **Ronda realista buena:** negociación ≈ 27–28 (el +50 del closer, una rara CHA barata, denuncias, escalera) + mercado ≈ 15,2 (m ≈ 0,53, como t16) ≈ **42–43**. Con eso, t10 tendría que quedarse por debajo de ~33, unos 12–13 puntos menos que en la ronda 2 (por ejemplo, sin orgánico y con 4–5 puntos menos de negociación).
- **Conclusión:** ganar depende también de que t10 falle. Lo que sí está en nuestra mano es subir la R3 todo lo posible y no regalar el 2.º. El orgánico es lo que más mueve (+4 de ronda con dos tratos), así que tiene un ritmo y una métrica de go/no-go en §5.3.

**Qué hace t10 (S-32)** y cómo nos afecta:
- **Mercado orgánico:** lo saca de anuncios en su venue v07 cada ~20 ticks, con parejas concretas entre otros equipos (11 tratos, 8 parejas). Lo más probable es que repita el tope.
- **Dealers:** abrió 106 hilos en la ronda 2, frente a nuestros 16.
- **Huevos:** tiene los tres (Castizo, cocido y El Chato).
- **Lo que no podemos tocar:** sus duelos y sus tratos.
- **Lo que sí:** nuestras palancas de la tabla de arriba.

**En resumen: ganar exige una ronda 3 nuestra muy buena (el orgánico en v18 y los +50 con equipos son lo que más mueve) y que t10 no repita la suya. Lo que controlamos es maximizar la R3 y no regalar el 2.º.**

---

## 3. Calendario del domingo

### 3.1 Qué dicen los datos
- **El sábado el reloj no saltó.** Siguió en 2,65, donde paró el viernes (tick 170 = t 2,7417). Todo lo anclado al día se movió exactamente −1,35 h: Duels I 6,5 → 5,15, Duels II 13,0 → 11,65, ronda 3 18,0 → 16,65, puestos 23,0 → 21,65 (S-17). Coincide con la OpenAPI: "Days that have already opened keep the live hour they opened at".
- **Los bancos de cada 2 h no se mueven** (3, 5, …, 21: horas absolutas).
- **El sábado cerró en t 13,367** (23:00) por 3,28 h de pausas (S-18). El schedule de las 23:59 muestra 16,65 / 18,65 / 21,65 / 22,65 porque con las puertas cerradas enseña las cifras del guion; el viernes por la noche pasaba lo mismo con 4,0.
- **El domingo empieza a las 09:00 y cierra a las 15:00** (`clock.days`), con ticks de 15 s. Mientras corre, el juego va 1:1 con la pared.

### 3.2 Los tres escenarios (hora de Madrid)

| Hora de pared | **C: sigue en 13,367 y se re-ancla −3,283 (probable, como el sábado)** | B: el reloj salta a 16,65 | A: sigue en 13,367 sin re-anclar |
|---|---|---|---|
| 09:00 | Abre. **Ronda 3 + CHA** | Abre. Ronda 3 + CHA. Puede que los Market Test vencidos (14,65 y 15,0) salten de golpe | Abre. **Sigue la ronda 2** |
| 09:03 | +150 P | +150 P | — |
| 09:21 | — | Market Test (17,0) | — |
| 09:25 | Caduca SAL-11 a 245 (tick 1545) | Igual | Igual |
| 10:17 | Market Test difícil (14,65), **sin verificar** que se dispare | — | Market Test difícil (ronda 2) |
| 10:38 | Market Test (15,0) | — | Market Test (ronda 2) |
| **11:00** | **Duels III** (2 vueltas, 12 ticks, decay 0,10, 4 a la vez; ~1 h, sin verificar) | Duels III | — |
| 11:21 | — | Market Test (19,0) | — |
| 12:17 | — | — | **Ronda 3 + CHA**; +150 P a las 12:20 |
| 12:38 | Market Test (17,0) | — | Market Test (17,0, ronda 3) |
| 13:21 | — | Market Test (21,0) | — |
| 13:48 | Aviso del final | Aviso del final | — |
| **13:55** | **El arnés cierra los hilos con dealers** | Igual | — |
| **14:00** | **Cierran los 5 puestos + Gran Final** (1 vuelta, 12 ticks, ~25 min) | Igual | — |
| 14:17 | — | — | Duels III (no acaba antes del cierre) |
| **14:25** | **Endgame:** el closer sube y se gasta la caja | Igual | Igual |
| 14:38 | Market Test (19,0) | — | Market Test (19,0) |
| 14:54 | Aviso de congelación | Igual | — |
| 14:55 | — | — | Fin de dealers (el cierre de puestos, 21,65, no llega) |
| **15:00** | **Se congela todo** (t 19,367) | Se congela todo (t 22,65) | Cierra (t 19,367); sin Gran Final |

Si abren tarde o pausan, todo se retrasa lo mismo, pero el cierre sigue a las 15:00 (`clock.closes`). El arnés adelanta el fin de dealers y el endgame en la misma medida.

### 3.3 Cómo saber a las 09:00 cuál aplica
A las **09:00:30** y a las **09:05** (GET sin clave a `/api/clock` y `/api/schedule`):
```
cd C:/Users/jorge/Desktop/hackaton-claude/bazaar-kit
python3 bazaar.py clockcheck
```
Imprime `reading`, `round`, `t_hours`, `paused`, `doors`, el cierre (schedule y pared), el cierre de puestos, el `day_end` / `endgame` derivados y una línea `scenario`:
- **C:** `t_hours` ≈ 13,37, `round 3`, `stalls close` ≈ 18,367 → `derived day_end 18.284 endgame 18.784` (13:55 / 14:25).
- **B:** `t_hours` ≈ 16,65 → `21.567 / 22.067` (13:55 / 14:25).
- **A:** `t_hours` ≈ 13,37, `round 2`, puestos en 21,65 → `19.284 / 18.784` (14:55 / 14:25).
- `paused True` o `doors closed`: esperar y repetir. Todo se mueve lo que tarden.

Sin herramientas: `curl -s https://bazaar.causaprima.ai/api/clock` y `curl -s https://bazaar.causaprima.ai/api/schedule`.

### 3.4 Qué hace el arnés en cada caso
- **Cada tick** (`pages.effective_plan`), cierre = lo primero entre `clock.closes` (pared), el `day_closes` de hoy y un `end_round` del calendario vivo. Un cierre ya pasado no cuenta.
- **Cierre de puestos** = la primera hora en la que ≥ 3 dealers pasan a `enabled:false`. Se recuerda (también en `state/day_times.json`) aunque la entrada desaparezca al dispararse.
- **Fin de dealers** = mín(cierre, puestos) − 5 min. A esa hora la higiene cierra **todos** los hilos con dealers, también los manuales.
- **Endgame** = cierre − 35 min. El closer sube a valor − 20, J6 compra cualquier primera copia por debajo de nuestro valor (`endgame_buy_any`) y J13 está apagado.
- Cada cambio de más de 1 min deja una fila `param day_times` en el diario. `status` enseña las 3 últimas.
- **Las horas de `config/plan.json`** (`day_end_hours.sun` 19,283 y `endgame_hours` 18,783) solo se usan si el calendario se lee pero no trae cierre y no hay `clock.closes`.
- **En A:** CHA-11 y RET-11 esperan a la ronda 3 (`min_round` 3) y CHA no existe hasta las 12:17. Antes de eso, el bot solo hace higiene y duelos.

---

## 4. Runbook 08:30–09:05 (máquina A)

Todo desde `C:/Users/jorge/Desktop/hackaton-claude/bazaar-kit`, en Git Bash salvo donde pone PowerShell. **Un solo operador y una sola sesión de Claude** con el bot.

### 4.1 08:30 Energía (PowerShell)
El sábado la máquina se durmió de 22:55 a 23:43 (S-31).
```
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setdcvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setactive SCHEME_CURRENT
```
Enchufada a la corriente; no pulsar suspender.

### 4.2 08:32 Desplegar (si nadie lo ha hecho ya)
Comprobar primero: si `git log -1 --oneline` en `harness-v2` ya enseña la fusión de `night-docs` y `status` muestra un pid nuevo, saltar a §4.3.

**Si se llega tarde (después de las 09:00):** desplegar en cuanto no haya ningún duelo vivo, y **nunca más tarde de las 10:55**, antes de Duels III (~11:00 en C y en B). Antes de Duels III no hay duelos el domingo. Si ya empezó, esperar a un hueco: `grep -E "duel_(say|accept)" logs/run/journal.jsonl | tail -2` (si la última fila tiene más de 2 min, no hay duelo vivo). El código viejo tiene las horas fijas: en B (el reloj salta a 16,65) dispararía el endgame a 18,783 (≈ 11:08) y el fin de dealers a 19,283 (≈ 11:38); en C no cierra los hilos antes de que cierren los puestos (14:00), y en los duelos usa el margen de días del sábado (S-27). Mientras tanto, `dealers` y `rastro` siguen en pausa (lo están desde el sábado) y no hay que tocar nada más. Con un duelo vivo, esperar a que acabe: un `stop` en mitad de un duelo lo pierde.
1. **Parar el bot viejo** (las puertas están cerradas y no hay duelos):
   ```
   python3 bazaar.py stop "deploy domingo"
   python3 bazaar.py status        # repetir hasta: lock free
   ```
2. **Apartar los no versionados** que traen las ramas (git se niega a sobrescribirlos; son copias iguales o superadas):
   ```
   mkdir -p C:/tmp/sat-untracked && mv bench_rec.py egg_watch.py docs/HANDOFF-sabado-1130.md docs/HANDOFF-sabado-2100.md C:/tmp/sat-untracked/
   ```
   `egg_watch.py` (pid 18236) sigue corriendo con su código ya cargado: no hace falta tocarlo.
3. **Fusionar:**
   ```
   git status --short              # solo debe quedar .claude/
   git merge-base --is-ancestor harness-v2 night-build && git merge --ff-only night-build
   git merge --no-edit night-docs
   git log --oneline -3
   ```
4. **Verificar** (con el bot parado):
   ```
   python3 bazaar.py selftest      # todas las etapas en verde
   python3 -m unittest discover -s tests -t .   # opcional si hay tiempo (~2,5 min): 883+ OK
   ```
5. **Quitar el STOP y lanzar** (PowerShell, desacoplado como el sábado):
   ```
   python3 bazaar.py resume --why "deploy domingo"
   Start-Process -FilePath python3 -ArgumentList 'bazaar.py','run','--live','--arm','hygiene,dealers,rastro,closer,duels' -WorkingDirectory 'C:\Users\jorge\Desktop\hackaton-claude\bazaar-kit' -RedirectStandardOutput 'C:\Users\jorge\Desktop\hackaton-claude\bazaar-kit\logs\run\stdout-dom.txt' -RedirectStandardError 'C:\Users\jorge\Desktop\hackaton-claude\bazaar-kit\logs\run\stderr-dom.txt' -WindowStyle Minimized
   ```
   `dealers` y `rastro` arrancan **en pausa** (`state/pauses.json`, desde el sábado). Así debe ser hasta las 09:00.

### 4.3 08:45 Comprobar que todo está bien
```
python3 bazaar.py status
cat logs/run/stdout-dom.txt
python3 -c "import json; from agent.runner import code_hash; s=json.load(open('state/selftest.json')); print(code_hash(), {k: (v['green'], v['code_hash']) for k, v in s.items()})"
```
- `lock pid <nuevo> ... run --live --arm hygiene,dealers,rastro,closer,duels`, `STOP -`.
- `armed` con las 5 tácticas; `paused ['dealers', 'rastro']`; `stages core:G hygiene:G dealers:G rastro:G closer:G duels:G`.
- El `code_hash` actual es igual al de cada etapa. Si no, la táctica no se arma: repetir `selftest` con el bot parado.
- En `stdout-dom.txt` no aparece ningún `not armed`.
- `pending 0`. Las filas `alarm` / `stop` de antes del despliegue no importan.
- Proceso vivo (PowerShell): `Get-CimInstance Win32_Process -Filter "Name='python3.exe'" | Select ProcessId,CommandLine`.
- La oferta de SAL-11 sigue viva: `grep 20117 logs/run/journal.jsonl | tail -2`. No debe haber un `cancel` nuevo.

### 4.4 09:00–09:05 Apertura
| Hora | Qué | Comando |
|---|---|---|
| 09:00:30 | Escenario (§3.3) | `python3 bazaar.py clockcheck` |
| 09:01 | Primer tick abierto sano: `down` sin `catalog` (si sale, esperar un tick) y fila `param day_times` | `python3 bazaar.py status` |
| 09:01 | **Huevos de la Abuela** con los dealers aún en pausa (§5.6) | `python3 egg_carrier.py abuela 940 MAL-01 6 9,8,7,6 5,6` |
| 09:01 | Reanudar El Rastro (J6 compras de CHA a equipos, closer; J5 solo repetidas reales) | `python3 bazaar.py resume rastro --why "domingo: J6 CHA, closer, repes"` |
| 09:02 | **SAL-11: decides (a) equipos a 212 o (b) Pilar con suelo 199** (§5.4). Cancelar la 20117 y lanzar lo elegido | §6 #3 |
| 09:03 | Paga: caja ≈ 705 (`tick ... cash`) | `python3 bazaar.py status` |
| 09:05 | Escenario confirmado | `python3 bazaar.py clockcheck` |
| ~09:08 (al terminar los huevos, o a las 09:10 como tarde) | **Reanudar dealers**: escalera y CHA | `python3 bazaar.py resume dealers --why "domingo ronda 3: escalera + CHA"` |

**En A** (ronda 2 hasta las 12:17), se reanudan igual: antes de CHA no hay Needs de dealer y CHA-11 / RET-11 esperan a la ronda 3.
- El único hueco libre de la ronda 2 es uno de El Chato (nivel 2, 2/3 el sábado). Se puede llenar antes de las 12:17 con el huevo de El Chato en el mismo hilo: `python3 egg_carrier.py chato 1105 LAT-06 8 18,16,14,12,10,9,8 3`.
- El coste: Pilar pierde LAT-06 en la ronda 3, y un hueco de Pilar (3/45) vale más que uno de El Chato (2/45). Por defecto, no hacerlo.
- Las ventas a Pilar (§6) esperan a las 12:17.

---

## 5. Plan por bloques

### 5.1 Escalera (ronda 3) y Chamberí
Un hueco vale parte capturada × L/45. Solo cuentan los tratos con ganancia a nuestros valores, y aceptar la apertura del dealer da 0. Cuentan los 3 mejores por nivel, y todo vuelve a 0 en cada ronda (S-19, S-20).

**Valores CHA para nosotros** (afinidad ×1,6): común 16, infrecuente 40, rara 112, CHA-11 (épica) 288, CHA-12 (legendaria) 720. La carta que cierra la página vale ~122.

| Nivel | Dealer | Qué hace el bot (`config/plan.json`) | Qué hago yo a mano |
|---|---|---|---|
| 1 | Abuela | CHA comunes, ancla 7, paso +1, ≤ 12 | MAL-01 #940 con los huevos, a ≥ 6 (V 5) |
| 2 | El Chato | CHA-06/07/08, ancla 27, paso +1, ≤ 31 (Abuela de respaldo a los 24 ticks). Respaldo de las raras CHA: ancla 70, paso +2, ≤ 93 | — |
| 3 | Pilar | Nada (la Gate no admite perfiles de Pilar) | Tres ventas: **SAL-11** #1063 (solo si eliges la opción (b) de §5.4, suelo 199), **LAT-06** #1105 (el sábado pagó 16) y **LAV-03** #788 como prueba (no se sabe si compra comunes) |
| 4 | Pícaros | CHA-09/10 ≤ 64 (ancla 45, paso +3; El Chato tras un abandono). Después de la página: CHA-11 ≤ 170 (ancla 130) y RET-11 ≤ 150 (ancla 115), solo en la ronda 3. Sus finales trampa se cierran sin contraoferta | Denunciar trucos de nivel A (§5.5) |
| 5 | Ernesto | Nada | Nada, salvo la línea de huevo si hay pruebas (§5.6) |

- **Orden:** primero las cartas de la página CHA, y luego los extra_needs (CHA-11, RET-11).
- **El closer:** en cuanto CHA llega a 8/10 se congela la carta de cierre (una común). A 9/10 se puja a equipos a 72 (V − 50) y en el endgame se sube a 102 (V − 20). La carta de cierre nunca se compra a un dealer.
- **Compras a equipos (J6):** cualquier carta CHA del plan con ganancia ≥ 3 tras la comisión. Una rara CHA a ≤ 62 da el tope de +50: vigilar El Rastro cuando los equipos abran sobres de CHA.
- **Durante Duels III** el bot sigue abriendo hilos (bloqueo solo con > 4 duelos) y los hilos abiertos siguen negociando.
- **Caja prevista** (705): comunes ~40, infrecuentes ~90, raras ~120, CHA-11 ~140, RET-11 ~135, cierre 72–102. Total ≈ 600–630, con topes de hasta ~750. Lo que no llegue se queda sin comprar y no resta. **CHA-11 y RET-11 nunca se comen la caja del closer** (`0daffe5`): su hilo se topa en `cash_free` menos la puja del closer a su precio de endgame (≈ 102, o lo que le falte a nuestra puja ya puesta). Si no cabe ni el ancla (130 / 115), el hilo no se abre: es lo esperado, no un fallo. Comprobación a mano a 8/10 de CHA: `python3 bazaar.py status` (`cash_free` ≥ ~110).

### 5.2 Duels III (≈ 11:00) y Gran Final (≈ 14:00)
- **Formato:** precio + días (0–10), 12 ticks, decay 0,10, 4 a la vez. Duels III tiene 2 vueltas y la Final 1.
- **Valor medido** (S-26, 95/95 tratos): `s·(p − L) + signo·|w|·días`, con signo −1 como comprador ("each delivery day costs you") y +1 como vendedor.
- **Qué manda el código nuevo:**
  - como **comprador**, 0 días y margen \|w\|·d;
  - como **vendedor**, 10 días y precio nunca por debajo del límite;
  - si el texto no se entiende, el signo sale del papel y salta una alarma;
  - si contradice al papel, −1 (conservador) y alarma.
- **Parámetros** (`plan.duels`): `anchor 0,62`, `slow_cap 0,85`, `acc_late 2`, `e8_ticks 0`, `days_weight_fallback 1,0`.
- **Expectativa:** parte ≈ 0,16 en el modelo, no 0,214. Son modelos con rivales sintéticos, **sin verificar**. Con los duelos del sábado, el código nuevo habría aceptado en 17 puntos, ninguno con valor < 1 (incluidos 5730 y 6173, que el sábado acabaron sin trato).
- **Qué mirar en el primer duelo:**
  - `python3 bazaar.py status`: una fila `alarm` sobre `days_meaning` significa texto nuevo; el bot sigue por papel y **no hay que pausar**;
  - `G51.late` / `G03.late` repetidos significan que la aceptación llega tarde.
- **Reglas de manos:** nada de reiniciar con duelos vivos. Pausar duelos solo si `duel_points` baja tras un trato (`python3 bazaar.py pause duels --why "resultado negativo"`), cosa que el código no debería permitir.

### 5.3 Mercado y venue
**Decisión: NO abrir venue `board` ni broker.** Seguimos con el puesto gratuito v18.
- **Por qué:**
  - Ningún equipo superó al puesto en las 6 sesiones del sábado: t10 sacó exactamente 0,5 de banco y los `board` de t04, t01 y t02 dan 7,5 exactos (S-23).
  - Un broker que respete las cotizaciones no gana al cruce automático (S-25).
  - Si el broker se cae, esa sesión da 0.
  - Cuesta 20 P + 250 P de fianza bloqueada.
- **Cuánto vale:** mercado por ronda = 22,5 × bench + 7,5 × orgánico. Quedándonos quietos sacamos 11,25 por ronda.
- **Lo que sí: orgánico en v18 con anuncios a mano** (excepción manual, tu OK para cada envío). Es la palanca más grande de la ronda (§2):
  - **Cuánto vale:** el orgánico es la raíz cuadrada del valor creado entre otros equipos en nuestro venue, normalizado al top 3 y con tope 1 (S-23). Con dos tratos dirigidos, t16 sacó m ≈ 0,53 (+4,0 de ronda); t09 sacó m ≈ 0,68 con 6 (si su banco fue 0,5). Ojo: los `trades` del leaderboard son acumulados desde el viernes. v02 de t12 enseña 11 tratos y t12 marca 7,25 de mercado, así que en la ronda 2 apenas le dieron orgánico. Lo que cuenta son los tratos de hoy.
  - **Por qué funciona:** t10 publica cada ~20 ticks parejas concretas ("Team 6 bids 6 P for RET-03 (offer 17714)… post it publicly on v07…; El Rastro costs 5 % + 1 P") y sacó 11 tratos y 8 parejas. t16 llegó a m ≈ 0,53 con dos tratos dirigidos en su puesto.
  - **El sábado v18 hizo 0 tratos** y `announce_candidates.py` solo encontró una pareja cercana entre no rivales en todo el día. Hay que provocar las parejas, no solo esperar a encontrarlas.
  - **Ritmo:** de 09:15 a 14:30, un anuncio cada ~10 min (≈ 40 ticks de 15 s; es el ritmo de t10 el sábado, ~20 ticks de 30 s).
    - Si `announce_candidates.py` da una pareja, el anuncio la cita: ids, precios y que en v18 no hay comisión, frente al 5 % + 1 P de El Rastro.
    - Si no hay pareja, va el reclamo fijo: "Team 18 stall v18: 0 % fee, 0 P per card, auto-matched every tick. Post your sale or your bid on v18 and skip El Rastro's 5 % + 1 P." Puedes aprobar el reclamo una vez; cada envío sigue necesitando tu sí.
  - **Go / no-go a las 11:00:** si v18 tiene `trades` ≥ 1 en el leaderboard (o `mm_points` > 0 en `/api/me`), seguir al mismo ritmo hasta las 14:30. Si sigue en 0, bajar a uno cada 30 min y solo con pareja concreta. A las 12:30, la misma revisión.
  - **Procedimiento:**
    ```
    python3 announce_candidates.py                # solo lectura, sin clave: parejas y borrador
    python3 C:/Users/jorge/AppData/Local/Temp/claude/c--Users-jorge-Desktop-hackaton-claude-bazaar-kit/27e13914-d038-4ac9-be22-314fc951d24e/scratchpad/announce_stall.py "<texto aprobado>"
    ```
  - **Reglas:**
    - nunca nombrar a contendientes (t10, t05, t12, t03, t06, t14);
    - nunca operamos en v18 nosotros;
    - el bot nunca publica en venues rivales: solo El Rastro;
    - cada envío se apunta en [handoffs/HANDOFF-domingo.md](handoffs/HANDOFF-domingo.md).
  - **Medir (sin clave):** `curl -s https://bazaar.causaprima.ai/api/leaderboard | python3 -c "import json,sys; d=json.load(sys.stdin); [print(v['venue'], v['owner'], v['trades'], v['pairs']) for v in d['venues'] if v['venue'] in ('v18','v07','v01','v16')]"`
  - **`mm_points` (GET con clave, no la imprime):** `cd C:/Users/jorge/AppData/Local/Temp/claude/c--Users-jorge-Desktop-hackaton-claude-bazaar-kit/27e13914-d038-4ac9-be22-314fc951d24e/scratchpad && MSYS_NO_PATHCONV=1 python3 peekfull.py /api/me | python3 -c "import json,sys; s=json.load(sys.stdin)['score']; print(s['mm_points'], s['market'])"`
- **Reabrir la decisión** solo si un rival pasa de 12,5 + 0,5 de mercado (prueba de que se puede superar al puesto). Aun así, solo con tu OK y un broker probado abierto ≥ 2 ticks antes de una sesión.

### 5.4 Épicas: qué sí y qué no
- **No hay arbitraje que puntúe.** Comprar a un dealer por encima de nuestro valor resta (min(0, V − p), P-04), y la caja final vale 0 (S-22). Revender a un equipo solo suma si el precio supera *nuestro* valor de la carta. Lo de Rubén ("revender épicas da beneficio") está refutado (knowledge, refutación 75).
- **Sí:**
  - comprar a los Pícaros por debajo de nuestro valor para la escalera L4: CHA-11 (V 288) a ≤ 170 y RET-11 (V 234) a ≤ 150. Los Pícaros vendieron épicas a 128–155;
  - **SAL-11** (V 198, asset 1063). A 245 nadie la ha comprado en ~300 ticks (oferta 20117, caduca a las 09:25), mientras los equipos pagaban 195–216 por épicas. **Decides tú a las 09:00** (§6 #3):
    - **(a) Equipos a 210–215:** +12..+17 neg si alguien compra (publicamos; la comisión la paga quien acepta). Es lo que mejor paga si sale.
    - **(b) Pilar con suelo 199** (V + 1, lo mínimo que admite `ladder_sell`): +1 neg y un hueco de escalera L3. Pilar nunca ha cerrado una épica por encima de 199: la nuestra a 199 (S-21, en la "fiebre SAL" sin verificar) y LAV-11 de t08 a 140 (tick 550, feed). Rubén cita además 179 y 195 (sin verificar). **Sin fiebre, lo más probable es que no haya trato.**
    - En los dos casos hay que cancelar antes la 20117: la Gate no deja volver a publicar ni vender en un hilo una carta que ya está publicada (`G13.listed`).
    - En el escenario A, (b) espera a las 12:17: los huecos de Pilar de la ronda 2 ya están 3/3.
    - A Ernesto no (113–126).
- No vender CHA-11 ni RET-11 una vez compradas: cualquier venta por debajo de su valor resta.

### 5.5 Denuncias (Pícaros)
- **Solo nivel A:** un mensaje de los Pícaros en un hilo **nuestro** cuya oferta estructurada da otra carta que la del tema **y** cuyo texto nombra la carta del tema. Las tres que puntuaron el sábado eran así (8663, 9460, 9859: +10 cada una). Las 6 de nivel B dieron 0 (S-28).
- **Como mucho 3.** No se sabe si el tope es por ronda o del fin de semana: si la primera da 0, parar.
- **Cuándo:** a las ~10:00, ~12:00 y ~13:30, preferiblemente con el hilo ya cerrado.
- **Procedimiento** (excepción manual):
  ```
  python3 flag_candidates.py          # solo lectura; ya excluye las 9 del sábado
  ```
  Para cada candidata que apruebes, apuntar `neg_points` antes, enviar, y comprobar después:
  ```
  python3 C:/Users/jorge/AppData/Local/Temp/claude/c--Users-jorge-Desktop-hackaton-claude-bazaar-kit/27e13914-d038-4ac9-be22-314fc951d24e/scratchpad/flag_one.py <message_id> "Los Pícaros ofrecen <carta dada> en un hilo sobre <carta del tema> y el texto nombra <carta del tema>"
  ```
  Para leer `neg_points` (GET de solo lectura; no imprime la clave):
  ```
  cd C:/Users/jorge/AppData/Local/Temp/claude/c--Users-jorge-Desktop-hackaton-claude-bazaar-kit/27e13914-d038-4ac9-be22-314fc951d24e/scratchpad && MSYS_NO_PATHCONV=1 python3 peekfull.py /api/me | python3 -c "import json,sys; print(json.load(sys.stdin)['score']['neg_points'])"
  ```
  Si da error o el cambio es ≤ 0, parar. Apuntar cada una en HANDOFF-domingo.

### 5.6 Huevos de pascua (no puntúan: prestigio y jueces)
Nuestras insignias: Sharp ear y Trickster tricked. **Falta Castizo** (la tienen t10, t05 y t08). Las líneas están en `talk.py` y `EGG_LINES` las saca de la rotación: solo salen a mano.

| Orden | Dealer | Frase (plantilla, variante) | Portadora | Cuándo | Riesgo |
|---|---|---|---|---|---|
| 1 | Abuela | "¡Buenas, Carmen! Usted que es tan castiza: ¿es verdad que el chotis se baila sobre una baldosa? Le dejo esta carta en {p} P." (`abuela_sell` 5) | MAL-01 #940, hilo de venta | 09:01, **con `dealers` en pausa** (G30.thread_open rechaza un 2.º hilo con la Abuela) | Ninguno. Las 4 Castizo del sábado llegaron con la respuesta sobre el chotis |
| 2 | Abuela | "¿Ha comido ya, Carmen? Yo hoy, cocido madrileño con sus tres vuelcos, como lo hacía mi abuela. Le dejo esta carta en {p} P." (`abuela_sell` 6) | El mismo hilo, cuando la Abuela haya contestado | Justo después | Quizá ya no quede regalo (t06 no lo recibió, sin verificar) |
| 3 (opcional) | El Chato | "Buenas, Chato. ¿Dónde se come el mejor bocadillo de calamares de Madrid? Yo digo que en la Plaza Mayor, con una caña. Te la dejo en {p} P." (`chato_sell` 3) | Una suelta que El Chato compre (infrecuente o rara). La única es LAT-06 #1105, reservada para Pilar: usarla aquí solo si Pilar ya la rechazó | Con CHA-06/07/08 ya compradas y sin hilo de compra con El Chato abierto | El regalo es un **sobre**: G14 bloquea compras y la higiene cierra los hilos de compra hasta abrirlo |
| — | Ernesto | `banco_sell` 5 ("…los domingos usted recibe en Casa Prima a los coleccionistas más consumados. Traigo tres páginas completas…") | — | **Solo** si aparece una pista nueva o un `egg.found` de banco | Strictness 1,0 y memoria 1,0: castiga insistir. Una vez como mucho |

- **Comando** (orden 1 y 2 juntos): `python3 egg_carrier.py abuela 940 MAL-01 6 9,8,7,6 5,6`. Manda la variante 5, espera respuesta, manda la 6 y luego regatea 9 → 6.
- **Al terminar:** mirar las insignias en el leaderboard y reanudar `dealers`.
- **Chato (opcional):** `python3 egg_carrier.py chato 1105 LAT-06 8 18,16,14,12,10,9,8 3`.
- **Nunca:** "oro de Moscú" (LAT-13 es de t02), la línea del Lazarillo a los Pícaros, "caja fuerte", "Banco de España" ni el nombre real de El Chato (todo probado sin efecto o agotado, S-29).
- **Vigilar:** `egg_watch.py` (si sigue vivo; si no, `Start-Process -FilePath python3 -ArgumentList 'egg_watch.py' -WorkingDirectory 'C:\Users\jorge\Desktop\hackaton-claude\bazaar-kit'`) avisa de `egg.found`, `badge.awarded` y cartas ocultas nuevas de CHA.

### 5.7 Gastar la caja y congelación
- La caja a las 15:00 vale 0 (S-22). **Nunca comprar con pérdida para gastar**: con dealers resta.
- **Hasta las 13:55**, dealers: lo de §5.1.
- **Desde el fin de dealers (13:55) o el endgame (14:25)**, `endgame_buy_any`: J6 compra en El Rastro cualquier primera copia de fuera de las páginas que un equipo venda por debajo de nuestro valor (ganancia ≥ 3 tras la comisión). Guarda lo que necesita la subida del closer.
- **14:25:** el closer sube a 102.
- **14:50:** `python3 bazaar.py status` (`cash`, `cash_free`). Si sobra caja y no hay compras con ganancia, es lo esperado. No hace falta `stop --flatten`.
- **15:00:** congelación. Después: `python3 bazaar.py stop "fin del juego"`.

---

## 6. Acciones manuales que necesitan tu OK
Cada una, una vez y apuntada en [handoffs/HANDOFF-domingo.md](handoffs/HANDOFF-domingo.md). Todos los `ladder_sell` / `egg_carrier` escriben solo con `bazaar.py do ... --live` y pasan por la Gate (G30/G31/G32/G60). Necesitan el runner vivo y `core` en verde. Solo hay un hilo por dealer a la vez.

| # | Acción | Condición | Comando |
|---|---|---|---|
| 1 | Desplegar `night-build` + `night-docs` | 08:30–08:50, sin duelos | §4.2 |
| 2 | Huevos Castizo + cocido | 09:01, `dealers` aún en pausa | `python3 egg_carrier.py abuela 940 MAL-01 6 9,8,7,6 5,6` |
| 3 | SAL-11: eliges (a) o (b) (§5.4) | 09:00–09:10. Primero, si la 20117 sigue abierta, cancelarla: `python3 bazaar.py do cancel --args '{"offer_id": 20117, "ref": "SAL-11"}' --why "Jorge: SAL-11 a 245 sin comprador" --live` | (a) Equipos: `python3 bazaar.py do list_offer --args '{"side": "sell", "ref": "SAL-11", "asset_id": 1063, "price": 212, "expires_ticks": 240, "closer": false, "want_ref": null}' --why "Jorge: SAL-11 a equipos a 212" --live` (renovar si caduca sin venderse; a las ~12:00 sin comprador, pasar a (b)). (b) Pilar: `python3 ladder_sell.py pilar 1063 SAL-11 199 260,250,242,235,228,222,216,211,207,203,201,199` |
| 4 | Pilar, LAT-06 (L3) | Al terminar la 3 (si en la 3 elegiste (a), ya: Pilar está libre) | `python3 ladder_sell.py pilar 1105 LAT-06 7 18,16,14,12,10,9,8,7` |
| 5 | Pilar, LAV-03 (L3, prueba) | Al terminar la 4. Abortar si no puja ≥ 8 | `python3 ladder_sell.py pilar 788 LAV-03 8 16,14,12,11,10,9,8` |
| 6 | Denuncia de nivel A (≤ 3) | `flag_candidates.py` la lista y la has leído | §5.5 |
| 7 | Anuncio en v18 | De 09:15 a 14:30, uno cada ~10 min; a las 11:00 go / no-go (si v18 sigue en 0 tratos, uno cada 30 min y solo con pareja). Texto aprobado | §5.3 |
| 8 | Huevo de El Chato (opcional) | CHA-06/07/08 en mano, sin hilo con El Chato, LAT-06 sin vender a Pilar | `python3 egg_carrier.py chato 1105 LAT-06 8 18,16,14,12,10,9,8 3` |
| 9 | Escalera Abuela si L1 < 3 tratos a las ~12:30 | Sin hilo con la Abuela abierto. Antes de que haya una puja del closer, porque un hilo con la Abuela la retira | `python3 ladder_sell.py abuela 789 MAL-02 6 9,8,7,6` (también 583 MAL-04 y 582 MAL-05) |
| 10 | Huevo de Ernesto | Solo con una pista nueva o un `egg.found` de banco | `python3 ladder_sell.py banco <id> <ref> <suelo ≥ V+1> <precios> 5` (una pieza que le interese; con cuidado) |
| 11 | Respaldo de horas a mano | Solo si `clockcheck` no da `derived day_end` (sale `-`) con las puertas abiertas | §7, fila "Reloj distinto" |

Antes de cualquier venta a un dealer: si la oferta final es menor que tu suelo, `ladder_sell` no acepta. Si la Gate rechaza el `open_thread`, el motivo está en la última fila `refused` del diario: `grep refused logs/run/journal.jsonl | tail -3`. `G30.thread_open` significa que ya hay un hilo con ese dealer: espera a que se cierre.

---

## 7. Riesgos y planes B

| Riesgo | Señal | Qué hacer |
|---|---|---|
| **Despliegue tarde** | Son más de las 09:00 y `status` enseña todavía el pid 34804 (código del sábado) | Desplegar (§4.2) en cuanto no haya un duelo vivo, como muy tarde a las 10:55 (antes de Duels III). Hasta entonces `dealers` y `rastro` siguen en pausa. En B, el código viejo dispararía el endgame a las ≈ 11:08 y el fin de dealers a las ≈ 11:38 |
| **Se cae el bot** | `status` → `lock free` o `STALE?` con las puertas abiertas | Relanzar el mismo `Start-Process` de §4.2 (sin `selftest` si el código no ha cambiado). Las pausas siguen en `state/pauses.json`; el cierre de puestos, en `state/day_times.json`. **Después de las 13:55** relanzar sin dealers: `--arm hygiene,rastro,closer,duels` |
| **Reloj distinto** (tarde, en pausa, otra hora de cierre) | `clockcheck`: `paused True`, otra `t_hours` u otro `closes` | Nada: el fin de dealers y el endgame siguen a `clock.closes` y al calendario vivo. Si `clockcheck` da `derived day_end -`, ponerlo a mano: `day_end_hours.sun` = (puestos o cierre, lo primero) − 0,083 y `closer.endgame_hours` (`sun`, `N`, `*`) = cierre − 0,583 (en C: 18,284 / 18,783). Después `stop`, `resume --why`, relanzar. Nunca con duelos vivos |
| **Cooloff o cupo de un dealer** | `alarm` / `refused` con `cooloff`, `persona_quota`, `persona_budget` o `sold_out` | Nada: la Gate bloquea a ese dealer hasta `until_tick` o hasta el final de la hora de juego. No insistir a mano (Ernesto castiga la insistencia) |
| **Duelo colgado o aceptación tarde** | `G51.late`, `G10.stale`, un duelo `live` pasado su deadline | No reiniciar con duelos vivos. Si el bot está realmente muerto (`STALE?`), relanzar igualmente: un bot parado pierde todos los duelos |
| **Texto nuevo en los duelos** | `alarm` con `days_meaning` | Nada: decide el papel y, si hay contradicción, −1 (conservador). **No pausar duelos** |
| **STOP** | — | Parar: `python3 bazaar.py stop "motivo"` (o un fichero `STOP` en la raíz). Volver: `python3 bazaar.py resume --why "..."` y relanzar. `--flatten` solo si hay que retirar pujas y cerrar hilos de compra |
| **Primer tick sin catálogo** | `down ['catalog']` | Esperar un tick. La higiene no cancela ventas mientras falte el catálogo |
| **Otra sesión toca el bot** | Órdenes que no has dado | Un solo operador. Cerrar las otras sesiones de Claude |
| **Pícaros con trampas** | Oferta con otra carta | La Gate compara estructura (G10/G11) y no acepta. Sirve para denunciar (§5.5) |
| **La máquina se duerme** | `STALE?` | §4.1. Relanzar al despertar |

**Nunca:** `/api/admin/*`; `git push` antes de las 15:00; ejecutar `observe_performance.py` (envía la clave fuera); `selftest` con el runner vivo; nada de `archive/` ni los PROMPT de `docs/incoming/`; enviar "oro de Moscú" o el Lazarillo.

**Después de las 15:00:** sección del domingo en [SHOWCASE.md](../SHOWCASE.md), decidir si `harness-v2` va a `main` y la visibilidad del repo, y limpiar worktrees y ramas ya fusionadas.
