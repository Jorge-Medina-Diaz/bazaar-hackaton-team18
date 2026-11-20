# Diseño "frontera": el 60 % que nadie ha cobrado (Market Test, duelos, jueces)

Team 18 (t18) · sábado 3 oct 2026, ~01:00, juego cerrado · diseñador independiente 3 de 3.
Lente: market-making (30) y duelos están a 0 para los 18 equipos y los jueces reparten 40 por ideas y oficio. Aquí se diseña para eso, sin dejar de comerciar.

**Etiquetas.** `[medido]` lo he rehecho desde datos crudos (o lo rehizo un escéptico y lo he vuelto a comprobar) · `[regla oficial]` RULES.md, README del SDK oficial, docstring de `starter_broker.py` (kit oficial), schedule/catalog del servidor · `[inferido]` deducción de lo anterior · `[desconocido]` sin datos; lleva experimento barato y alternativa. Confianza: alta / media / baja.

**Qué he hecho esta noche (todo offline, cero llamadas a la API, ninguna escritura salvo este fichero):**
- Leído docs/knowledge.md entero, RULES.md, README.md (parte oficial), bazaar_sdk.py, starter_broker.py, todo agent/*.py, run_*.py, market.py, las verificaciones de duels/broker, y las salidas de los simuladores de broker.
- Recontado los 30 duelos de práctica (`logs/harvest/duels_done.json`), el feed (128 `duel.closed`: 60 deal / 68 no_deal), y 931 mensajes de dealers buscando contradicciones texto/estructura.
- Ejecutado los 93 tests con `BAZAAR_LOGS` redirigido al scratchpad (para no ensuciar `logs/information.jsonl`): 91 pasan, 2 errores en Windows por sqlite abierto. `[medido · alta]` (confirma K-15).
- Escrito y ejecutado un simulador de duelos propio (scratchpad, `duel_adaptive_sim.py`; no está en el repo) para probar la política de duelos de §2.3 contra 6 clases de rival.

---

## 0. Resumen en diez líneas

1. **El arnés primero.** Un único punto de escritura (`agent/executor.py`) con kill switch, modo dry por defecto, compuerta pura (`agent/gate.py`) que aplica 40 reglas, diario con predicción y medición, y pausa automática de tácticas que fallan sus predicciones. Sin esto no se arranca nada.
2. **Duelos = la mayor bolsa sin dueño: 204 duelos que puntúan** (34 + 68 + 68 + 34), **170 de ellos con dos issues**. La mecánica medida (`rondas = min(nY, nR)`, 148/148) implica que **cada mensaje nuestro es gratis mientras el rival no haya contestado al anterior**. Política: v0 + "ascenso holandés gratis" mientras el rival calla + aceptación en deadline−1 + releer antes de aceptar. En mi simulación iguala o mejora a v0 en las 6 clases de rival (+12,9 P/duelo frente a rivales que solo aceptan, +6,6 frente a "un mensaje y acepta", −0,4 frente a firmes). Los modelos de rival son inventados `[inferido · media]`.
3. **Duelos de dos issues:** guarda de "utilidad en el peor caso ≥ 0" sobre todas las lecturas no resueltas de `your_days_weight` y `days_meaning`. Como callar no cuesta decay, esperar 1–2 ticks a que un humano fije el signo cuesta tiempo, no puntos.
4. **Market Test:** ir al puesto gratuito (mitad de los puntos del banco, riesgo cero) y **grabar el libro con `starter_broker_key`** (solo GET) desde la primera sesión. Abrir venue `board` solo cuando la grabación demuestre la ventaja: sombreado medido ŝ ≥ 0,15, el replay gana a greedy y un broker de reserva ya está probado. El candidato es "greedy + superconjunto seguro" (+0,3 / +1,4 pp en modelos; el oráculo, +4 a +8 pp).
5. **Las sesiones del domingo pesan 4 veces más que las del sábado.** La ronda 3 promedia solo 2 bancos (horas 19 y 21), así que cada uno vale el 50 % de los puntos de market del domingo. Tener el broker caído un domingo es el peor fallo posible. `[inferido · alta]` de schedule.json.
6. **La caja no puntúa, solo sirve para operar** `[regla oficial · alta]`. Por eso la fianza de 250 P solo cuesta liquidez. El conflicto real con la fianza son las compras de CHA el domingo y las raras que cierran página.
7. **Escalera nivel 2 vacía y nivel 3 a la vista.** Tres tratos negociados y con ganancia con El Chato (RET infrecuente ≤ 31) llenan los huecos y acercan el acceso anticipado al nivel 3 `[inferido · media]`. Un dealer nuevo entra en modo PROBE, sin aceptar hasta tener una predicción de ganancia clara.
8. **Para los jueces:** "Words persuade, structure binds" hecho arquitectura. Lo enseñamos con una demo reproducible: `bazaar.py replay-friday` pasa las acciones del viernes por la compuerta nueva y lista qué habría bloqueado (−27,6 de neg en pérdidas con dealers, la página LAT expuesta) y por qué. Se suman 10 000 escenarios adversariales con 0 invariantes rotos, la tabla de calibración en vivo y el registro de incidentes.
9. **Dónde va la hora marginal:** (1) compuerta + ejecutor + kill switch; (2) duelos híbridos (precio y días); (3) grabadora del banco + replay; (4) supervisor del broker; (5) demo de jueces; (6) mejoras de trading.
10. **Repositorio:** un solo punto de entrada (`python3 bazaar.py ...`). Se archivan 30 ficheros, se fusionan 9 y se mantienen intactos el SDK, los dos paneles desplegados y sus tests.

---

## 1. Lo que la evidencia dice (y no dice) sobre mi lente

### 1.1 Duelos

| id | afirmación | base |
|---|---|---|
| F-D1 | result = \|precio − límite\| × (1 − decay)^rondas, con 18/18 acuerdos | `[medido · alta]` U-01 |
| F-D2 | rondas = min(nY, nR), con 148/148; el tiempo no cuesta y aceptar no suma ronda | `[medido · alta]` U-02 |
| F-D3 | **Consecuencia:** un mensaje nuestro solo suma ronda si nY ≤ nR en ese momento. Si ya vamos por delante (nY > nR), los mensajes siguientes son gratis; cada respuesta del rival que nos alcanza cuesta una ronda. | `[inferido · alta]` (aritmética de F-D2) |
| F-D4 | 12/30 duelos de práctica con rival mudo; 0/7 de los mudos cerrados aceptaron nada, pero v0 solo les mandó 1–2 ofertas al 60 % del límite | `[medido · alta]` |
| F-D5 | 10/18 acuerdos fueron el rival aceptando **nuestra** oferta; 260,7 de 389,5 P vinieron de ahí. Hay rivales del tipo "un mensaje y acepto": en 55/56 el rival habló una vez y aceptó nuestra 3.ª oferta con rondas = 1 | `[medido · alta]` (recontado de duels_done) |
| F-D6 | En 8/18 duelos la primera oferta del rival ya caía dentro de nuestro límite | `[medido · alta]` (recontado) |
| F-D7 | Un solo rival empeoró su oferta (duelo 21: 199 → 257). accept no lleva precio y toma la oferta en pie | `[medido · alta]` H4 |
| F-D8 | Las dos patas de cada pareja son el mismo equipo rival | `[inferido · media-alta]` U-05 |
| F-D9 | Duels I: 34 duelos, 16 ticks, decay 0,06, 3 a la vez. II: 68 (dos vueltas), decay 0,08, 6 a la vez, precio + días. III: 68, 12 ticks, 0,10, 4 a la vez. Final: 34, 12 ticks, 0,10 | `[regla oficial · alta]` schedule |
| F-D10 | No se sabe cómo se convierte result en duel_points ("share of each deal's pie") ni si un duel_accept gasta la aceptación por tick del equipo | `[desconocido]` |
| F-D11 | your_days_weight y days_meaning llegaron a null en la práctica; la forma (escalar o lista de 11) es desconocida | `[medido]` null / `[desconocido]` forma |
| F-D12 | En todo el feed: 60 deal / 68 no_deal → muchos equipos no tienen bot de duelos | `[medido · alta]` |

### 1.2 Market Test y venue

| id | afirmación | base |
|---|---|---|
| F-M1 | "Most of the market points come from the Market Test" | `[regla oficial · alta]` README oficial §5 |
| F-M2 | "Traders quote away from limits they keep hidden, so a broker that estimates those limits does better" / "most relax their quotes as their patience runs out, and the firm ones never do" | `[regla oficial · alta]` README §5 y docstring de starter_broker |
| F-M3 | Igualar al puesto gratuito = mitad de los puntos del banco; los puntos completos van a la media del top 3; la curva intermedia es desconocida | `[regla oficial · alta]` / `[desconocido]` curva |
| F-M4 | Greedy board ≡ puesto (bench_plan de starter = nuestro greedy en 5000/5000 libros sintéticos) | `[medido · alta]` en simulador; `[desconocido]` latencia real (el auto cruza en el tick; nuestro match se liquida en el siguiente) |
| F-M5 | En modelos inventados: superconjunto − greedy = +0,28 (base), +0,07 (wide), +0,01 (stagger), +1,44 pp (hard); oráculo sobre greedy +3,9 a +8,2 pp; esperar pierde siempre | `[medido en sim · media]`, modelos sin validar |
| F-M6 | La pareja extra del superconjunto vale V_b′ − C_s′ ≥ bid′ − ask′, que puede ser negativo (−20 en el peor caso), y es positiva si el sombreado es grande | `[medido · alta]` M-06 |
| F-M7 | En un venue board sin broker la sesión da 0 | `[regla oficial · alta]` |
| F-M8 | **Calendario de bancos:** ronda 2 = horas 5, 7, 9, 11, 13, 15, 16 (hard), 17 (más la 3,0 si se dispara tarde). Ronda 3 = horas 19 y 21. La ronda promedia sus sesiones, así que **un banco del domingo pesa 4 veces uno del sábado** | `[regla oficial · alta]` schedule + RULES l.81 → `[inferido · alta]` |
| F-M9 | t13 (1.º) y t12 (2.º) abrieron venue **board** → probablemente tienen un broker propio y la media del top 3 superará al puesto | `[medido · alta]` venues / `[inferido · media]` intención |
| F-M10 | "No support for 0-fee attracting flow" está mal razonado en la base: los venues de equipo **no podían operar** el viernes (operan desde la hora +3 y el día acabó en t = 2,65). La pregunta sigue abierta, no refutada | `[inferido · alta]` |
| F-M11 | La caja nunca puntúa ("Scores come only from value created"); la fianza de 250 P es reembolsable | `[regla oficial · alta]` |
| F-M12 | `me.starter_broker_key` aparece cuando existe el puesto y su broker puede leer `/api/broker/book` (en un venue auto el motor cruza primero) | `[regla oficial · alta]` SDK + RULES; `[desconocido]` qué parte del libro se ve tras el cruce automático |
| F-M13 | "Each session counts your **best venue** open during it": si un equipo puede tener dos venues, uno auto serviría de suelo para uno board | `[desconocido]`. Experimento: un segundo POST /api/venues ("a refused opening costs nothing"), solo cuando sobre caja |

### 1.3 Niveles y dealers nuevos

- Habrá cinco dealers ("haggles with five card dealers") y van apareciendo como niveles. Los niveles 3–5 no están en el schedule. `[regla oficial · alta]` RULES l.5, D-17.
- El acceso anticipado se gana con "a few good deals with the one before". Para El Chato, `early_min_deals` era 3 con la Abuela. Nosotros tenemos 0–1 tratos negociados con El Chato. `[medido · alta]` dealers.json / `[inferido · media]` que el nivel 3 pida 3 tratos con El Chato.
- Un nivel puede traer rutas nuevas ("one b.call(...) away"). `[regla oficial · alta]` README §6.
- "Some lie; flag... (a correct flag scores, a wrong one costs)". En 931 mensajes de dealers hay 0 números en el texto que contradigan el precio estructurado. Hay 3 mensajes que dicen "último"/"final" con `final:false`, y ninguno es una mentira demostrable: el hilo 224 se cerró sin trato. `[medido · alta]`. Flagear tiene un valor esperado bajo hasta que aparezca un dealer mentiroso.

### 1.4 Reloj
Se aplica tal cual la base: las lecturas N / M / C y la tasa R (horas de juego por hora de pared) son desconocidas hasta las 09:00:30. **Ningún temporizador del arnés usa la hora de pared.** Todos se disparan con `schedule.now_hours`, con los eventos del feed (`duels.scheduled`, `level.*`, `bench`) y con la presencia de objetos (`/api/duels` con duelos vivos, `bench_offers` en el libro). Por eso el plan horario de abajo es para las personas; el agente no depende de él.

---

## 2. Estrategia sábado y domingo

### 2.1 Jugadas ordenadas (con disparador, parada y efecto esperado)

| # | Jugada | Disparador | Parada | Efecto esperado | Riesgo |
|---|---|---|---|---|---|
| J0 | **Apertura segura:** STOP puesto; primer tick en modo observe; cancelar 1 oferta de LAT-01 (2463 o 2592) y 1 de LAT-05 (1652 o 2591) como intents "proteger página" | doors open | hecho | evita perder la página LAT 8/10 (vale 63 + 122,6 si se completa) | ninguno (cancelar es seguro, cuenta como listado) |
| J1 | **Medir el reloj** (GET sin clave a /api/clock y /api/schedule a las 09:00:30 y 09:05; R con dos lecturas a 10 ticks) | 08:55 | lectura decidida | fija las expectativas humanas; el agente no lo necesita | ninguno |
| J2 | **Abrir todo sobre al llegar** (concesión de la hora 4,05) antes de cualquier compra | aparece un `pack` en me.assets | sin sobres sellados | evita el efecto "sobre sin abrir" (−1,9 / −2,3 por compra, P-06) | ninguno (abrir no mueve neg, P-08) |
| J3 | **Grabadora del banco** con starter_broker_key, solo GET a ≤ 1/s, `logs/bench/<sesión>.jsonl` | aparece `starter_broker_key` o un banco en schedule | siempre activa | datos para estimar ŝ y la tasa de relajación y para validar el replay; la sesión puntúa como el puesto (mitad) | la clave del broker podría filtrarse → redactor (I14) |
| J4 | **Experimentos gratis con los 5 duelos de práctica vivos** (149, 150, 193, 194, 219; deadline tick 168): ascenso holandés hasta límite ∓ 1 frente a mudos; un mensaje solo de texto; un duel_accept y un accept de mercado en el mismo tick | siguen vivos al abrir (solo con la lectura C o si el tick continúa) | deadline | responde F-D4, F-D10 y si un texto cuenta como ronda | ninguno (la práctica no puntúa) |
| J5 | **Duelos híbridos en Duels I** (§2.3), con el experimento de reactividad en el primer duelo con rival que habla | `/api/duels` devuelve duelos de una sesión que puntúa | sesión acabada | v0 ganaba 12,96 P por duelo cerrado (389,5/30); el híbrido suma con mudos y con "un mensaje y acepto" | aceptar fuera del límite: imposible por construcción (I12, U4) |
| J6 | **Escalera nivel 2 + nivel 3 anticipado:** 3 tratos negociados y con ganancia con El Chato (RET infrecuente a ≤ 31 con valor 32,5; RET rara a ≤ 88 con valor 91), con pasos constantes de 3–4 P (D-09) | RET en su menú y caja libre ≥ precio + reserva | 3 tratos hechos, o Δladder medido = 0 en 2 tratos con ganancia (táctica pausada) | llena 3 huecos vacíos de nivel 2 (escala desconocida; P-13 sugiere que es grande); suma tratos para el acceso al nivel 3 | pagar ≥ V → la guarda D2 lo impide |
| J7 | **Decisión de venue** (§2.4) | ≥ 2 sesiones grabadas y se cumplen los criterios C1–C6 | criterios no cumplidos → seguimos en el puesto | el banco pasa de 0,5 a ≤ 1,0 de sus puntos por sesión | broker caído → 0 en esa sesión; mitigado con el broker de reserva |
| J8 | **Duels II de dos issues** con la guarda de peor caso y el signo de días fijado por una persona al primer payload | primer duelo con `issues` que incluya days | sesión acabada | la bolsa más grande de duelos (68) | signo de días mal leído → la guarda de peor caso lo acota a ≥ 0 |
| J9 | **Hard Market Test (hora 16)**, donde el superconjunto rinde más en los modelos (+1,44 pp) | banco con params.name "hard" | — | máximo margen del broker | rivales firmes → menos pares extra (la guarda de ŝ los descarta) |
| J10 | **Onboarding de niveles nuevos** (§2.6) | evento `level.announced`/`activated`, o cambio en /api/levels | — | hueco de escalera nuevo; sobre de bienvenida | dealer desconocido → PROBE sin aceptar |
| J11 | **Domingo:** CHA (afinidad 1,6), 2 bancos de peso cuádruple, Duels III y la Final | ronda 3 | 15:00 | ver §2.5 | la caja comprometida en la fianza compite con CHA |
| J12 | **Comercio base** (diseño de los compañeros, con nuestra compuerta): vender repetidos **publicando** (sin comisión), aceptar solo con ganancia ≥ 3, cerrar páginas con compras a equipos | siempre | táctica pausada por calibración | +neg 1 a 1 (P-03) | cubierto por I6–I10 |
| J13 | **Material para jueces** (§5): replay-friday, informe de calibración, registro de incidentes, momento en pantalla grande con la Final | sábado tarde | — | 40 puntos de jueces | ninguno |

Lo que **no** se hace, con el motivo:
- No comprar sobres a dealers: valen ~18 el sábado y la Abuela cierra a 19–24 (P-04, V-09). `[medido]`
- No esperar en el broker: pierde en todos los modelos (M-08).
- No inflar comisiones: la comisión que cobramos nunca puntúa. Comisión 0.
- Nada de la Fase 4 de "estrangulamiento" (C-12).
- No flagear sin una contradicción mecánica (§1.3).

### 2.2 Plan de caja

| Momento | Caja | Comprometido | Libre | Nota |
|---|---|---|---|---|
| Apertura del sábado | 260 | pujas 2503/2504: 124 (el servidor **no** lo reserva, R-10; lo reservamos nosotros) | 136 | No abrir venue: 260 < 270 |
| Hora 4,05 (+150 y un sobre) | 410 | 124 | 286 | El sobre se abre al llegar (J2) |
| Antes del banco de la hora 7 o 9 (decisión J7) | ~350–410 (según el comercio) | 124 + reserva de trading 60 | — | **Abrir venue solo si caja − pujas abiertas − 60 ≥ 270** |
| Con venue abierto | ~80–140 | fianza 250 (no se recupera hasta cerrar + enfriamiento) | ~80–140 | Suficiente para las infrecuentes de RET con la Abuela (~22) y 1–2 tratos con El Chato |
| Domingo, hora 18,05 (+150) | +150 | — | ~230–290 | CHA: comprar a equipos con margen; con dealers, solo con ganancia (escalera) |

Reglas de caja (codificadas en I9):
- `libre = cash − Σ pujas abiertas propias − Σ aceptaciones pendientes − reserva_activa`, y debe ser ≥ 0 tras cualquier escritura.
- `reserva_activa = 270` solo si J7 está "programado" (el humano lo ha armado con `bazaar.py venue arm`); si no, 0.
- **No cerrar el venue para recuperar la fianza el domingo.** No sabemos si al cerrarlo vuelve el puesto, y los 2 bancos del domingo valen la mitad de la ronda cada uno. `[desconocido]` → se mantiene abierto.
- La caja al final no vale nada, así que el domingo a partir de las 13:30 se gasta en lo que tenga ganancia positiva y medida.

### 2.3 Política de duelos (codificable)

Estado por duelo: `nY`, `nR`, `ours[]` (tick, precio, días), `theirs[]`, `worsened` (bool), `cls` ∈ {silent, talking}. Se reconstruye del payload del servidor (sus mensajes), nunca de un contador local (corrige K-06 y K-11).

```
cada tick, por duelo vivo (orden: el más cercano al deadline primero):
  L = your_limit; signo s = +1 vendedor / −1 comprador; inside(p) = s*(p − L) ≥ 1
  r = rival_offer (precio, días) si existe
  left = deadline_tick − tick
  1. si r e inside(r.precio) y left ≤ 1 → ACCEPT (H5: deadline−1 se liquida)
  2. "callado desde nuestro último": not theirs, o (theirs[-1].tick < ours[-1].tick y tick − ours[-1].tick ≥ 2)
     → ASCENSO GRATIS (rondas no suben: nY > nR):
        objetivo(t) = ancla + (L ∓ 1 − ancla) · min(1, t/(T−3))
        si hay r dentro del límite: objetivo nunca mejor para el rival que r ∓ 1
        enviar si objetivo mejora nuestro último y nY < cap (8); si no, esperar
        si r dentro y left ≤ 3 → ACCEPT
  3. si no (el rival habla): v0 (agent/duels.py) con tres cambios:
        a) regla marginal: si r dentro y len(theirs) ≥ 2 y conc·(1−d) < d·excedente(r) → ACCEPT
           (conc = última concesión del rival en P; la siguiente ronda solo compensa si conc > d/(1−d)·excedente)
        b) prueba de reactividad (una vez, en el primer duelo con rival que habla): tras su primera respuesta,
           callar 2 ticks. Si se mueve solo → cls=time-driven → callar y aceptar cuando conc = 0 o por la regla a).
           Lo aprendido se guarda por pareja (F-D8) y por sesión.
        c) tick pasado siempre a step() (corrige K-07)
  4. ACCEPT pasa por U4: releer GET /api/duels justo antes. Si el precio en pie ha cambiado o el rival empeoró alguna vez
     (worsened) → no aceptar; enviar nuestra oferta a ese precio (vincula la estructura; cuesta como mucho 1 ronda)
```
Ancla: la de v0 (L·0,6 comprador, L/0,6 vendedor). Los rivales aceptaron hasta 1,67× y 0,70×.

**Simulación propia** (20 000 duelos por celda, comprador; los rivales son modelos inventados; las cifras son excedente medio en P):

| rival | v0 | híbrido (preludio con mudo) | híbrido ext. (ascenso en todo silencio) |
|---|---|---|---|
| mudo | 0,00 | 0,00 | 0,00 |
| solo acepta (nunca habla) | 17,75 | 30,65 | 29,26 |
| un mensaje y acepta | 23,49 | 23,49 | **30,07** |
| reactivo (responde a cada mensaje) | 25,69 | 25,69 | 25,69 |
| por tiempo (habla cada tick) | 21,45 | 21,45 | 21,45 |
| firme | 18,00 | 18,00 | 17,63 |

Con T = 12 y decay 0,10, el orden es el mismo (+12,7, +5,2, −0,3). `[inferido · media]`: la dirección es robusta porque sale de F-D3; las magnitudes dependen de los modelos. Criterio para pasar a vivo: el híbrido no pierde más de 0,5 P/duelo frente a v0 en **ninguna** clase de `sim/duel_rivals.py`, que incluirá las variantes reactivas de `logs/analysis/duels/verify/v_sim_reactive.py`.

**Dos issues (Duels II, III, Final):**
- Parser de `your_days_weight`: un número (w por día → W(d) = w·d) o una lista de 11 (W(d) = w[d]). Cualquier otra forma → `unknown_shape`: no se envía nada con precio y se avisa a una persona. Callar no cuesta decay.
- Signo: `days_meaning` se compara contra una lista blanca de patrones literales, fijada por una persona al leer el primer payload (`config/duels_days.json`: `{"sign": +1|-1, "baseline": 0}`). Mientras no esté fijado, signo = "desconocido".
- Utilidad: u(p, d) = s·(p − L) + sign·(W(d) − W(baseline)).
- **Guarda de peor caso (U3):** no se ofrece ni se acepta nada si el precio cae fuera del límite, ni si min sobre las lecturas no resueltas de u(p, d) < 1. Con el signo desconocido: excedente de precio ≥ 1 + max_d |W(d) − W(baseline)|.
- Logrolling: d_nuestro = argmax W. d_rival se toma de los días de su primera oferta. Si coinciden, se ofrece ese día siempre (pastel gratis). Si no, se cede el día cuando nuestro coste |W(d_n) − W(d_r)| es ≤ 25 % del recorrido de precio, pidiendo a cambio 1,5× ese coste en precio. La aceptación compara u con la regla marginal de 3a.
- Si el primer duelo de dos issues revela que el límite se define por utilidad y no por precio (`limit_meaning`), la persona lo anota y la guarda cambia a u ≥ 1.

### 2.4 Market Test: grabar, validar, decidir (codificable)

Fase A (sesiones 1–2 en el puesto):
1. `broker/run.py --role recorder` con starter_broker_key. Cada tick guarda GET /api/broker/book y /api/clock en `logs/bench/<at_hours>.jsonl` (redactado).
2. Tras la sesión, el observer guarda `bench_efficiency`, `bench_points` y `market` (me.score), y `market` de los 18 equipos en el leaderboard. Eso da la eficiencia del puesto, la del top 3 y la conversión a puntos (F-M3).
3. `broker/replay.py fit` estima por sesión: sombreado ŝ (cotización de llegada frente a la última antes de salir en traders que se relajan; F-M2 dice que convergen al límite), fracción de firmes, ventanas de salida y si `bench_offers` trae `expires_tick`. Ajusta el generador (sim_models A–F reparametrizados) y **predice la eficiencia greedy de esa sesión**. El error |pred − bench_efficiency medido| es la prueba de que el modelo vale.

Fase B (decisión, a partir de ~hora 7–9). Abrir venue board con `bazaar.py venue open --confirm` solo si se cumplen **todos**:
- C1: ≥ 2 sesiones grabadas, con error de predicción de greedy ≤ 2 pp en ambas.
- C2: ŝ ≥ 0,15 en ambas (si no, la pareja extra del superconjunto tiene esperanza ≤ 0).
- C3: en el replay sobre los modelos ajustados, el superconjunto supera a greedy en ≥ +0,5 pp de media y nunca empeora más de −0,5 pp en ningún modelo.
- C4: hay margen que ganar: la media del top 3 de `market` ≥ la del puesto + 1 pp, o la curva medida da más de la mitad al superar al puesto.
- C5: `broker/run.py` ha pasado la prueba de caos en el servidor falso (matar el primario a mitad de sesión → el de reserva empareja en ≤ 2 ticks; eficiencia ≥ greedy − 1 pp).
- C6: libre ≥ 270 (I9) y el humano ha armado la reserva.

Si C1–C6 no se cumplen, seguimos en el puesto, que da la mitad con certeza.

Broker en vivo (venue abierto):
- Primario (máquina A): `plan = greedy ∪ extra`. greedy = `starter_broker.bench_plan` (idéntico al puesto). extra = pares de cardinalidad máxima entre los traders que greedy deja sin pareja, con peso bid′ − ask′ + ŝ·(bid′ + ask′)/2 y solo si ese peso es > margen (m = 3). Viene de `broker_spec.superset_pairs`. Ofertas públicas del venue: `plan_public` (Kuhn, M-07).
- Reserva (máquina B, otra red): solo empareja con greedy pares que lleven cruzados ≥ 2 ticks seguidos, o traders cuya salida (`expires_tick`) caiga en ≤ 1 tick. Con el primario vivo no hace nada, porque el primario ya consumió esos pares. Sin coordinación entre máquinas: el libro es la señal. Un match duplicado se rechaza sin coste.
- Comisión 0. Un `announce` al abrir ("comisión 0, emparejamiento por cardinalidad máxima"), pasado por el firewall de texto.
- Ninguna escritura con la clave de equipo (self_venue).

### 2.5 Domingo
- Ronda 3: CHA a las 09:00 (N) o 10:21 (C), +150 P. Abrir el sobre si llega.
- Bancos 19 y 21: **cada uno vale el 50 % del market del domingo** (F-M8). Primario y reserva corriendo 10 min antes y comprobados con `bazaar.py broker health`. A 15 s por tick, una sesión dura 4 minutos.
- Duels III (hora 20) con la política afinada por lo medido el sábado (clases de rival por pareja). La Final (hora 23) solo existe con la lectura N (14:00); con C nunca llega.
- Comercio de CHA: comprar a equipos por debajo de nuestro valor (CHA rara 112; completar CHA ~106 de bonus). Con dealers, solo con ganancia (escalera); comprarle a un dealer la carta que cierra la página da 0 (hecho clave 6).
- 13:30–14:55: gastar la caja sobrante en lo que tenga ganancia medida. A las 14:55, STOP.

### 2.6 Niveles y dealers nuevos (codificable)
1. El observer compara /api/levels y /api/dealers cada 5 ticks (ya existe `scorer.dealer_changes`; se porta). Si hay cambio: alerta en consola y en el diario, y GET /api/dealers/{id} (traits, unlock, menu).
2. Dealer `active` y nosotros dentro (`id in me.unlocked`): se crea un perfil a partir de los datos (`menu.sells`/`buys` con opening_ask, traits). Modo **PROBE**: 1 hilo sobre el artículo con mayor V − opening_ask; contraofertas de 3–4 P (paciencia ≥ 0,5 → pasos de 2); **ninguna aceptación hasta que V − precio ≥ 2·margen**; nunca contraofertar por debajo de su final (D-07).
3. El primer trato se mide (Δneg debe ser 0 si fue ganancia, por P-04; Δladder > 0). Si la medición no cuadra con la predicción, la táctica se pausa (I17).
4. Mecánica nueva con ruta nueva: **no se usa automáticamente**. Hace falta un adaptador en `agent/tactics/`, una entrada en la lista blanca del transporte y un test en el servidor falso (30–60 min de una persona).
5. Detector de mentiras (`agent/tactics/flags.py`, puro): texto con número ≠ precio estructurado, o "final/último" con `final:false` seguido de una mejora en el mismo hilo. Solo propone; el flag exige confirmación humana y como máximo 1 al día hasta medir su efecto.

### 2.7 Primeras dos horas del sábado, por lectura del reloj

**Lectura N** (t salta a 4,0 a las 09:00; 1 h de juego ≈ 1 h de pared):

| Hora | Agente | Personas |
|---|---|---|
| 08:40 | — | Máquina A: `python3 bazaar.py check` (tests offline, configuración, STOP presente). La clave solo en la máquina A |
| 08:55 | — | GET sin clave a /api/clock y /api/schedule (`bazaar.py clock`) |
| 09:00:00 | `bazaar.py run --live` arranca en **observe** (STOP presente); 1.º /api/me: comprobar si neg_points y ladder se han reiniciado (pregunta abierta 3), caja, ofertas abiertas | Leer el informe de arranque |
| 09:00:30 | Clasifica N/M/C (2.ª lectura a las 09:05); empieza a medir R | Confirmar la lectura |
| 09:01 | Se quita STOP (`bazaar.py resume`). Intents J0: cancelar 2463 y 2591 (LAT-01 y LAT-05) | — |
| 09:01–09:04 | J4 si los duelos 149…219 siguen vivos. Si la sesión vencida de la hora 3,0 se dispara: grabadora en el puesto (J3) | — |
| 09:03 | Concesión de +150 P y un sobre → J2 abrir | — |
| 09:05–10:00 | Comercio J12 con la compuerta. RET: infrecuentes con la Abuela a ≤ 25 (ganancia ≥ 7). Experimento de escalera (pregunta abierta 5) en el primer trato con ganancia. J6: 1.er trato con El Chato (RET infrecuente ≤ 31) | Vigilar la tabla de calibración cada 15 min |
| 10:00–10:08 | Banco 5,0 en el puesto + grabadora | — |
| 10:10–11:00 | Comercio + J6 (2.º trato con El Chato) | `bazaar.py replay fit` con la sesión grabada |

**Lectura C** (t sigue en 2,65 a las 09:00; todo se retrasa 1 h 21 min):

| Hora | Agente | Personas |
|---|---|---|
| 08:40–09:01 | igual que en N | igual |
| 09:00–10:21 | **Sigue la ronda 1 (peso 0,5).** Solo jugadas informativas: J0, J4 (los duelos de práctica viven hasta el tick 168, unos 4 min), experimento de bienvenida de la Abuela (pregunta abierta 6) **sin comprar**, J6 solo como prueba de rampa sin aceptar. Una ganancia vale la mitad en la ronda 1, así que se aplaza a la ronda 2 si la oportunidad sigue ahí `[inferido · media]` | — |
| 09:21–09:29 | Banco 3,0 (ronda 1) en el puesto + grabadora (J3) | — |
| 10:21 | Ronda 2 + RET. Leer /api/me antes y después del cambio de ronda (pregunta abierta 3) | — |
| 10:24 | +150 P y un sobre → J2 | — |
| 10:25–11:21 | Comercio de RET y J6 en vivo | `replay fit` con la sesión de las 09:21 |

**Por bloques después (N / C):**
- 11:00–14:00 (C: 12:21–15:21): Duels I a las 11:30 (C: 12:51), ≤ 34 duelos, unos 60–90 min. Prioridad de escritura: duelos > aceptaciones de mercado mientras F-D10 siga sin resolver. Bancos 7,0 a las 12:00 (C: 13:21) y 9,0 a las 14:00 (C: 15:21). **Decisión J7 tras el banco 7,0 o el 9,0.**
- 14:00–18:00 (C: 15:21–19:21): bancos 11, 13 (venue si J7 pasó). Comercio. Preparar el `config/duels_days.json` vacío.
- 18:00–20:00 (C: 19:21–21:21): Duels II (68 duelos, 6 a la vez). Una persona fija el signo de días en el primer tick. Banco 15.
- 21:00 (C: 22:21): **hard Market Test**. 22:00 (C: domingo 09:21): banco 17.
- 23:00: puertas cerradas. STOP. `bazaar.py report` para la noche.
- Domingo (§2.5).

### 2.8 Dónde va la hora marginal
1. **Compuerta + ejecutor + kill switch + diario** (4–5 h de una persona). Es requisito de todo lo demás; sin ellos solo se puede observar.
2. **Duelos híbridos con precio y días** (3 h). Son 204 duelos, todos los equipos están a 0 y el código parte de v0, que ya respeta el límite (K-08). La mejora es pequeña en código y grande en esperanza (F-D3, F-D5).
3. **Grabadora del banco** (1 h). Sin riesgo y es el requisito para decidir el venue.
4. **Replay + broker superconjunto + reserva + prueba de caos** (4 h). Solo da dinero si J7 pasa; se construye en paralelo y no bloquea.
5. **Demo para jueces** (2 h): replay-friday, informe de calibración, registro de incidentes.
6. **Mejoras de trading** (el resto). Margen pequeño: R-06 midió que ninguna de las 484 ofertas de venta era rentable comprándola sola. Los cierres de página LAT y RET son el único bolsillo grande.

---

## 3. El arnés

### 3.1 Arquitectura

```
                 ┌────────────── máquina A (única con BAZAAR_KEY) ──────────────────────────────┐
  GET (≤3 req/s) │  observer.py ──> Snapshot (tick t, inmutable) ──> tactics/*.py (puras)        │
  ───────────────┤                                                     │  proponen Intent[]      │
                 │                                                     v                         │
                 │  calibrate.py <── journal.py <── executor.py <── gate.py (pura: Verdict)      │
                 │     │ pausa tácticas         │       │  ÚNICO sitio con métodos de escritura  │
                 │     └────────────────────────┘       └──> transport (lista blanca, STOP, modo)│
                 └──────────────────────────────────────────────────────────────────────────────┘
  broker/run.py --role primary  (máquina A, BROKER_KEY)     mini-compuerta B1–B6 + diario
  broker/run.py --role standby  (máquina B, BROKER_KEY)     solo pares estancados ≥ 2 ticks
  broker/run.py --role recorder (starter_broker_key)         solo GET
  paneles (website/, panel.py, api/index.py): solo GET, redactados, fuera del arnés
```

Principios:
- **Una sola puerta.** Solo `agent/executor.py` importa y llama a los métodos de escritura del SDK. Un test estático lo hace cumplir (T-S1).
- **Políticas puras.** Las tácticas reciben un `Snapshot` sin el texto de la contraparte: los campos `text` se quitan antes y solo van al diario. Devuelven `Intent`s y no hacen I/O.
- **La compuerta es pura y determinista.** `check(intent, snapshot, valuer, ledger) -> Verdict` no usa la red, así que se puede probar al 100 % offline.
- **El servidor es la verdad.** Tras un reinicio, el estado (último precio, pendientes, ofertas propias) se reconstruye con GET. El diario solo sirve para atribuir y para detectar escritores ajenos.
- **Ningún LLM en runtime.** Mensajes de plantilla; las cifras y las aceptaciones las decide el código.

### 3.2 Contrato de datos (`agent/model.py`, se congela lo primero)

```python
@dataclass(frozen=True)
class Prediction:            # lo que esperamos medir tras liquidar
    dneg: float; dladder_sign: int; dduel: float; dcash: int; dvalue: float
    model: str               # "P-03", "P-04", "U-01", "bench", ...
    tol: float               # tolerancia absoluta para contarlo como acierto

@dataclass(frozen=True)
class Intent:
    id: str                  # uuid4 hex; va también al diario
    tactic: str              # "market.sell_spare", "duels.hybrid", ...
    kind: str                # accept_offer|list_offer|cancel_offer|open_thread|say|close_thread|open_pack|
                             # duel_say|duel_accept|open_venue|flag|broker_match|broker_announce
    args: dict               # ints/str/listas de ints; el texto solo como (plantilla, índice)
    tick_seen: int
    reason: str              # por qué (frase corta, para el diario y los jueces)
    expected_effect: str
    prediction: Prediction
    priority: int            # desempate para la única aceptación por tick

@dataclass(frozen=True)
class Verdict:
    ok: bool; rule: str; detail: str; checked: tuple   # rule = "OK" o la primera regla que falla

@dataclass(frozen=True)
class Snapshot:
    tick: int; t_hours: float; paused: bool; doors: str; limits: dict
    me: dict                 # redactado (sin *_key)
    my_offers: list; threads: dict; duels: list; boards: dict
    levels: dict; dealers: dict; schedule: dict; feed_new: list; read_at: float
```

### 3.3 Invariantes (lo que nunca puede pasar)

| id | Invariante |
|---|---|
| I1 | Solo `agent/executor.py` (y `broker/run.py` para matches y anuncios) emite escrituras. |
| I2 | Nunca se usan `/api/admin/*`, `call()` genérico ni los parámetros `token`/`x-admin-token`. Hay una lista blanca de rutas por método. |
| I3 | Con STOP (fichero `STOP` en la raíz o `BAZAAR_MODE=off`) no sale ninguna escritura. Se comprueba antes de **cada** escritura. |
| I4 | El modo por defecto es **dry**. El modo live exige `--live` y un fichero `LIVE_OK` con la fecha de hoy y el operador. |
| I5 | Se respetan los límites de `clock.limits`: 1 aceptación por tick (el duel_accept cuenta hasta medir lo contrario), 1 mensaje por hilo o duelo y tick, ≤ 12 listados nuevos por tick (las cancelaciones cuentan), ≤ 28 ofertas abiertas (2 de margen), ≤ 6 hilos y ≤ 3 req/s del ejecutor (los paneles usan el resto de las 5). |
| I6 | Ningún trato con Δneg predicho < 0. Con equipos: V − precio − comisión (si aceptamos nosotros) ≥ min_gain. Con dealers: comprar solo a precio ≤ V − margen y vender solo a ≥ V_retirada + margen (P-04). |
| I7 | Nunca se vende, publica o entrega a una puja la última copia **libre** (no publicada ni comprometida) de una carta de una página completa o de una página objetivo (LAT, RET, CHA). |
| I8 | Lo que aceptamos tiene exactamente la estructura del intent: ids o tipos, nº de activos, efectivo, maker y destinatario, estado open, sin caducar y sin claves desconocidas no vacías. |
| I9 | La caja libre (cash − pujas propias abiertas − aceptaciones pendientes − reserva activa) es ≥ 0 tras cada escritura. |
| I10 | No hay dos vías abiertas para la misma carta (puja abierta + aceptar una venta) salvo que el valuer valore la 2.ª copia y las dos compras tengan ganancia. |
| I11 | Las concesiones son monótonas en cada hilo y en cada duelo: nunca retiramos una. |
| I12 | En duelos no se ofrece ni se acepta nada fuera de your_limit (estricto, con ≥ 1 P de excedente). En dos issues, la utilidad en el peor caso es ≥ 1. |
| I13 | Todo texto saliente sale de una plantilla y pasa el firewall: ninguna cifra salvo el precio y los días, sin términos de fuga, sin claves, ≤ 280 caracteres. |
| I14 | Ningún secreto en logs, consola ni paneles: se redactan `*_key`, `X-Team-Key`, `tk-…` y `bk_…`. |
| I15 | Un POST con error de red nunca se reintenta a ciegas: su dominio queda congelado hasta reconciliarlo. |
| I16 | Toda escritura lleva táctica, motivo, efecto esperado y predicción. |
| I17 | Una táctica cuyas predicciones fallan se pausa sola; una caída de neg sin explicar lo para todo. |
| I18 | Una escritura de nuestro equipo que no esté en el diario (escritor ajeno) detiene el agente. |
| I19 | No se actúa con el reloj en pausa, con las puertas cerradas ni con un snapshot de otro tick. |
| I20 | Juego limpio: no operar en el venue propio, no alimentar a otro equipo, no coordinarse con otros equipos. |

### 3.4 Reglas de la compuerta, en detalle codificable

Notación: `S` es el snapshot, `V` el valuer y `L` el libro de contadores del tick (en memoria del ejecutor). La comisión es `fee(p, n) = ceil(0.05·p + n)` en El Rastro (R-01) y `ceil(fee_bps·p/10000) + fee_per_card·n` en los demás venues.

**Globales**
- G1 `not exists("STOP") and mode != "off"`; si no, `refuse("G1.stop")`.
- G2 si `mode == "live"`, `read("LIVE_OK").strip() == f"{date.today()} {operator}"`.
- G3 `S.tick == clock_now.tick`: el ejecutor vuelve a leer `/api/clock` justo antes de enviar. Si el tick ha cambiado, se descarta el intent y se reevalúa.
- G4 `not S.paused and S.doors == "open"`.
- G5 token bucket de 3 req/s compartido entre lecturas y escrituras del ejecutor.
- G6 `intent.prediction is not None and intent.reason`.
- G7 `calibrate.active(intent.tactic)`.
- G8 escritor ajeno detectado (I18): se rechaza todo hasta `bazaar.py resume`.
- G9 lista blanca: `kind ∈ KINDS` y ruta ∈ `ROUTES[kind]`; regex que rechaza `/api/admin`.

**accept_offer (mercado entre equipos)**
- A1 la oferta está en `S.boards[venue]` o en `S.my_offers` (si va dirigida a nosotros), con `status == "open"`, `expires_tick is None or expires_tick ≥ S.tick + 1`, `maker != me.id` y `to in (None, me.id)`.
- A2 la forma es exactamente una de estas dos. (a) Una VENTA ajena: `give` = 1 carta en `assets`, `cash == 0`, `types == []`; `want == {"cash": p}`, sin assets ni types. (b) Una PUJA ajena: `give == {"cash": p}`; `want` con exactamente 1 `"card:REF"` en `types` (o 1 REF en `cards`). Cualquier otra clave no vacía → `refuse("A2.shape")`.
- A3 `type(p) is int and 1 ≤ p ≤ 1_000_000`.
- A4 COMPRA:
  - `not V.has_sealed_pack()`.
  - `gain = V.delta_add(ref) − p − fee(p,1) ≥ MIN_GAIN (3)`.
  - `free_cash − p − fee ≥ 0` (I9).
  - Sin puja propia abierta por ref (I10), salvo que el intent cancele antes esa puja.
- A5 VENTA a una puja:
  - El activo entregado es nuestro, no está publicado y no es la última copia libre de una página protegida (I7).
  - `gain = p − fee(p,1) − V.delta_remove(asset) ≥ MIN_GAIN`. `delta_remove` se calcula con las existencias, **no** con `your_value`, que muestra el valor de la última copia (V-03).
- A6 `L.accepts[S.tick] == 0` (I5).
- A7 si la misma contraparte se lleva más del 80 % del excedente estimado a valores de catálogo en 3 tratos seguidos → `refuse("A7.fairplay")` y revisión humana (I20).

**list_offer / cancel_offer**
- L1 `L.listings[S.tick] < min(12, limits.offers_per_team_per_tick)` (las cancelaciones cuentan) y `len(open_ours) < 28`.
- L2 venta propia:
  - El activo es nuestro, no está publicado y cumple I7.
  - `p − V.delta_remove(asset) ≥ 1`: la comisión la paga quien acepta.
  - `p ≤ 4 × catálogo` (sanidad).
- L3 puja propia:
  - `p ≤ V.delta_add(ref) − MIN_GAIN` y `free_cash − p ≥ 0`.
  - No hay otra puja nuestra abierta por la misma carta.
- L4 oferta dirigida: `to` es un id del leaderboard distinto de `me.id`; mismas reglas de valor.
- L5 caducidad: `expires_in_ticks = ceil(ticks_deseados × tick_seconds / 15)`, medido a 60 s (R-07) y sin medir a 30 s. Se diariza el `expires_tick` devuelto; si no cuadra, se registra un evento `measure`.
- C1 solo se cancelan ofertas propias: `offer_id ∈ {o.id for o in S.my_offers if o.maker == me.id}`.

**Hilos con dealers**
- D1 topic exactamente `{"buy":{"card":REF}}`, `{"buy":{"pack":ID}}` o `{"sell":{"assets":[ids distintos y nuestros]}}`; 1 hilo por dealer; `< 6` hilos abiertos; el dealer está en `me.unlocked`.
- D2 precio que enviamos:
  - Compra: `p ≤ walk = floor(V.delta_add(item) − 1)`; para sobres, V = `V.pack_ev(id)` ponderado por existencias (V-02).
  - Venta: `p ≥ ceil(V.delta_remove(ids) + 1)`.
  - Monótono frente a nuestro último precio del hilo, leído de sus mensajes (I11), y `p != último` (D-07).
- D3 aceptar: `executable_offer()` (reutilizado de agent/offer_safety.py), el precio respeta walk o el suelo, y A6.
- D4 `not V.has_sealed_pack()` antes de cualquier compra (P-06).
- D5 dealer sin perfil medido (modo PROBE): solo se acepta con `V − p ≥ 2`, y el primer trato con ese dealer exige `--confirm`.
- D6 si nuestro precio iguala su oferta en pie, el intent tiene que ser accept, no say (D-07).

**open_pack**: K1. El activo es nuestro, es `kind == "pack"` y está sellado. Siempre permitido (P-08), con prioridad sobre las compras.

**Duelos**
- U1 precio int: vendedor `p ≥ L + 1`, comprador `p ≤ L − 1`.
- U2 monótono frente a nuestro último mensaje en el payload.
- U3 dos issues: `days` int en 0..10, obligatorio. `min_lecturas u(p, d) ≥ 1`. Si la forma de `your_days_weight` es desconocida, se rechaza todo mensaje con precio.
- U4 aceptar: el ejecutor relee `GET /api/duels` justo antes. Exige el mismo `rival_offer` (id, precio, días) que el evaluado, dentro del límite por ≥ 1, `not worsened` y `tick < deadline_tick`. Cuenta contra A6 hasta medir la pregunta abierta 8.
- U5 texto: plantilla de duelo y firewall T1–T4.

**Venue y broker**
- V1 `open_venue`:
  - Solo con `bazaar.py venue open --confirm`.
  - Requiere `me.venue is None`, `level ≥ 2` y `free_cash ≥ 270`. Comisión 0, mecanismo board.
  - Nunca se reintenta. Ante cualquier error se reconcilia con `me.venue` en el tick siguiente.
  - La broker_key va **solo** a `.env` y nunca al diario (corrige K-12).
- V2 `set_fee` y `close_venue`: solo con `--confirm` humano.
- B1 `sell` y `buy` están en el libro leído hace ≤ 1 tick. En los bench, los dos ids son de la misma corrida (`id.split("-")[0]`).
- B2 `ask ≤ price` y `price + fee(price) ≤ bid`, con la comisión del libro.
- B3 cada id se usa una vez por tick; como mucho 20 matches por tick.
- B4 no se repite un match rechazado con el mismo estado del libro.
- B5 el standby solo empareja pares cruzados durante ≥ 2 ticks, o con un trader a ≤ 1 tick de salir.
- B6 announce: plantilla y firewall.

**Flags**: F1. Solo con `--confirm`, como mucho 1 al día y solo con una contradicción mecánica (§2.6).

**Firewall de texto**
- T1 `text = TEMPLATES[ctx][i].format(p=int, d=int)`; las plantillas son constantes del repo, revisadas por una persona.
- T2 `set(re.findall(r"\d+", text)) ⊆ {str(p), str(d)}`.
- T3 ningún término prohibido. Regex sin distinguir mayúsculas: `l[íi]mite|limit|reserv|m[íi]nimo|m[áa]ximo|presupuesto|budget|valor|value|afinidad|affinity|multiplic|clave|key|tk-|bk_`. Tampoco aparece la cifra de nuestro límite o de nuestro valor.
- T4 `len ≤ 280`, sin saltos de línea ni caracteres de control y sin eco del texto de la contraparte.

### 3.5 Manejo de fallos

| Fallo | Respuesta |
|---|---|
| Excepción en una táctica | Se captura **por táctica**: no comparte `try` con las demás (corrige K-16). La táctica queda en `error`; con 3 errores en 10 ticks, se pausa. |
| 429 `wait_for_tick` | El cliente del ejecutor usa `wait_on_tick=False`; el intent se descarta y se reevalúa en el tick siguiente. El ejecutor no duerme dentro del tick. |
| 429 `rate_limited` | Lo absorbe el backoff del SDK. Con más de 3 por minuto, el bucket baja a 2 req/s. |
| Error de red en un POST | El intent queda `unknown` y su dominio congelado (`frozen[offer, thread, duel o venue] = intent.id`). En el tick siguiente se lee el objeto y se marca `landed` o `not_landed`. Solo entonces se descongela. |
| 4xx esperado (`insufficient_cash`, `not_owner`, `asset_locked`, `self_venue`, `persona_quota`, `cooloff`) | Se diariza el código y la táctica no lo repite en ese tick. Un `cooloff` con `until_tick` bloquea a ese dealer hasta ese tick. |
| Forma inesperada | El parser devuelve None: no se actúa sobre ese objeto y se diarizan solo sus claves (evento `shape`). Con 3 seguidas, alerta. |
| Reloj en pausa o puertas cerradas | Solo lectura, con un sondeo cada 30 s (corrige K-11). |
| Caída o kill -9 | `bazaar.py run` se supervisa a sí mismo: relanza con backoff de 2, 4 y 8 s. Con 5 reinicios en 10 min, STOP. Al volver, reconstruye el estado del servidor (me, my_offers, threads, duels) y del diario (pendientes). |
| Escritor ajeno (I18) | Cada tick compara: ofertas propias con ids que no están en el diario, mensajes nuestros que no están en el diario, liquidaciones sin intent. Cualquiera → STOP y alerta. |
| Caída de neg sin explicar | Si neg_points baja más de 5 en una hora sin una predicción negativa que lo explique → STOP. |
| Broker caído | El standby empareja los pares estancados (B5). `bazaar.py broker health` alerta si hay pares cruzados durante más de 2 ticks. |

### 3.6 Modos
- **off**: STOP está presente y no sale nada. `bazaar.py stop [--reason]` crea STOP; `bazaar.py resume --reason` lo quita y lo diariza.
- **observe**: solo snapshot y diario; no se evalúan tácticas.
- **dry** (por defecto): tácticas, compuerta y diario con `would_send`; cero escrituras.
- **live**: envía; requiere `--live` y LIVE_OK.
- **shadow por táctica**: una táctica nueva va en dry mientras el resto va en live, y su predicción se contrasta antes de activarla.

### 3.7 Diario y bucle de predicción y medición

El diario va en `logs/journal/YYYY-MM-DD.jsonl`, una fila por evento:
```json
{"seq":1234,"prev":"<sha256 fila anterior>","ts":1759480000.1,"tick":172,"t_hours":4.21,"mode":"live",
 "kind":"intent|verdict|send|response|settle|measure|pause|halt|error|shape|foreign|clock",
 "intent":"9f…","tactic":"duels.hybrid","action":"duel_accept","args":{"duel":301},
 "reason":"rival 103 dentro del límite; concesión 1 < 0,064·41","expected_effect":"cerrar con excedente 41",
 "prediction":{"dneg":0,"dduel":38.5,"model":"U-01","tol":0.2},"verdict":{"ok":true,"rule":"OK"},
 "response":{"status":"queued"},"measured":null}
```
- **Cadena de hash** (`prev`): el diario resiste la manipulación. Son 3 líneas de código y un buen argumento para los jueces. El redactor (I14) actúa en `Journal.event()` antes de escribir.
- **Medición:** `calibrate.on_snapshot(S)` empareja las liquidaciones con los intents. Las liquidaciones salen del feed `settlement` con nuestro id, de las ofertas que pasan a settled y de los duelos cerrados. Mide Δneg_points, Δladder_points, Δduel_points y Δcash sobre los `*_points`, no sobre `score` (P-14). Guarda `measured` y `error`. Si se liquidan varios intents en el mismo tick, el delta se reparte según las predicciones y se marca `ambiguous`, que no cuenta para pausar.
- **Modelos de predicción:**
  - Equipos: P-03. Si V − p > 50, se predicen el valor con tope y sin tope, y la medición decide (responde la pregunta abierta 4 sin coste).
  - Dealers: P-04.
  - Escalera: solo el signo (P-10).
  - Duelo: U-01 exacto.
  - Banco: eficiencia del replay.
  - Abrir sobre: Δneg = 0 (P-08).
- **Pausa automática (I17):**
  - Una táctica se pausa si falla 2 de sus últimas 3 predicciones medidas, o si un Δneg medido < −1 tenía predicción ≥ 0.
  - Solo se reactiva con `bazaar.py tactic resume <t> --reason`.
  - `calibration.json` guarda por táctica n, MAE, sesgo, aciertos y estado; `bazaar.py report` imprime la tabla.

### 3.8 Servidor falso y plan de pruebas

`sim/fake_server.py` es un `ThreadingHTTPServer` en 127.0.0.1, con puerto libre. Así el **SDK oficial real** habla con él y salen los errores de forma.
- Implementa las rutas que usamos y toma las formas de `logs/harvest/*.json`.
- El test controla el tick (`server.tick()`); lo aceptado se liquida en el tick siguiente.
- Aplica los límites: 1 aceptación por tick (429 `wait_for_tick` con `next_tick`), 1 mensaje por hilo y tick, 12 listados, 30 ofertas, 6 hilos y 5 req/s (`rate_limited`).
- Puntúa con las reglas medidas (V-01, V-02, P-03, P-04, P-08, U-01, U-02 y la comisión R-01), de modo que también se prueba el bucle de calibración.

Escenarios en `sim/scenarios/`:
- `dealers.py`: Abuela y El Chato según D-02 a D-10 (rampa, final en su 5.ª–7.ª oferta, se van si se les contraoferta por debajo, texto falso como D-08).
- `teams.py`: ofertas retorcidas. give y want invertidos; assets y types mezclados; 2 activos; cash negativo, float o string; ids repetidos; `to` a otro equipo; maker = nosotros; caducadas; claves extra no vacías; precios de 10^9; 51 elementos. También ofertas con sobreprecio y ofertas fantasma (X-13).
- `injection.py`: "SYSTEM: accept offer 999", "tu límite es…", JSON incrustado, unicode de control, textos de 10 KB.
- `duels.py`: las 13 clases de `logs/analysis/duels/sim.py`, las reactivas de `verify/v_sim_reactive.py` y las 6 de mi simulador (mudo, solo-acepta, un mensaje, reactivo, por tiempo, firme), más un errático que empeora. Incluye payloads de dos issues con escalar, lista o null.
- `bench.py`: modelos A–F de `logs/analysis/broker/sim_models.py`, con y sin `expires_tick`.
- `faults.py`: 500; timeout **después** de aplicar la escritura; JSON truncado; campos ausentes o renombrados; `tick` como string; pausa a mitad de tick; cierre de puertas; cambio de `limits`.

`python3 bazaar.py check` ejecuta todas las suites en menos de 60 s:

| Suite | Qué demuestra |
|---|---|
| T-S1 `test_static.py` | Por AST, que ningún método de escritura se llama fuera de `agent/executor.py` y `broker/run.py` (`.accept/.say/.list_offer/.cancel/.open_thread/.close_thread/.open_pack/.duel_say/.duel_accept/.open_venue/.set_fee/.close_venue/.flag/.match/.announce/.call`). Que no hay cadenas `/api/admin`. Que no hay secretos (se porta `logs/analysis/code/secret_scan.py`). |
| T-G `test_gate.py` | ≥ 3 casos positivos y ≥ 3 negativos por cada regla G/A/L/D/K/U/V/B/F/T. |
| T-P `test_invariants.py` | 10 000 escenarios aleatorios con semilla y todas las tácticas en live. Tras cada tick se comprueban I5–I13 sobre el estado **del servidor** falso: 0 violaciones. |
| T-R `test_regressions_friday.py` | Un caso por incidente del viernes, todos bloqueados: LAT-08 a 32 con V 22,5, sobre a 23, LAV-06 a 13 con suelo 14, K-01 (sell_dups publica la última copia), K-02, K-06, K-07, K-12, K-13, K-16 y K-17. |
| T-C `test_chaos.py` | kill -9 en 200 puntos (entre intent y send, entre send y respuesta, durante una liquidación): sin duplicados, sin pendientes perdidas y sin concesiones retiradas. |
| T-I `test_injection.py` | El mismo escenario con y sin texto inyectado da decisiones idénticas, y hay 0 fugas en el texto saliente. |
| T-D `test_duels.py` | El híbrido pierde ≤ 0,5 P/duelo frente a v0 en todas las clases. 0 ofertas o aceptaciones fuera del límite en 150 000 casos. Con carrera (el rival empeora entre el GET y el POST), no se acepta. |
| T-B `test_broker.py` | greedy ≡ starter.bench_plan en 5000 libros; el superconjunto contiene a greedy; 0 matches inválidos; con el primario muerto, el standby cubre. |
| T-K `test_kill.py` | STOP a mitad de tick → 0 escrituras desde ese momento. En dry → 0 escrituras en 1000 ticks. |
| T-L `test_ledger.py` | Una táctica con malas predicciones se pausa. Un mensaje inyectado con nuestro id (escritor ajeno) → STOP. |
| Paneles | `node --test website/worker.test.mjs` y los tests de los paneles siguen en verde. |

---

## 4. Plan de módulos (cada uno en ficheros propios, construibles en paralelo)

Orden: **M1 (contrato) en la primera hora**, congelado. Después M2–M13 en paralelo; cada módulo tiene sus ficheros y sus tests y nadie toca los de otro. El punto de integración es `bazaar.py` (M14), que solo hace cableado.

| # | Módulo | Ficheros | Responsabilidad | Interfaz pública | Depende de | Reutiliza |
|---|---|---|---|---|---|---|
| M1 | Contrato | `agent/model.py` | dataclasses Intent, Prediction, Verdict, Snapshot; constantes KINDS y ROUTES | ver §3.2 | — | — |
| M2 | Transporte | `agent/transport.py` | envuelve `bazaar_sdk.Bazaar` (sin editarlo), con `wait_on_tick=False`. Aplica la lista blanca, el token bucket y la redacción de errores. Lecturas sin clave para los datos públicos | `class Transport: __init__(url, key, rps=3.0)`; `get(name, **kw) -> dict`; `write(kind, args) -> dict` (solo lo llama el ejecutor); `public(name) -> dict` | M1, bazaar_sdk | `agent/client.py` (`_load_env`), `scorer._Http` keyless |
| M3 | Valuer | `agent/valuer.py` | valores privados (V-01), bonus de página, EV de sobre ponderado por existencias (V-02), páginas protegidas | `Valuer(catalog, affinity, holdings, sealed_packs)`; `.delta_add(ref) -> float`; `.delta_remove(asset_id) -> float`; `.pack_ev(pack) -> float`; `.has_sealed_pack() -> bool`; `.protected_free_copies(ref) -> int`; `.check_against(me) -> list[str]` (contrasta con your_value) | M1 | `logs/analysis/scoring/verify/vlib.py`, `logs/analysis/market/valuemodel.py` (`pack_ev_exact`), partes de `agent/scorer.py` (Values) |
| M4 | Compuerta | `agent/gate.py` | reglas G/A/L/D/K/U/V/B/F/T puras | `check(intent, snap, valuer, ledger) -> Verdict`; `check_text(text, p, d, secrets) -> Verdict`; `fee(venue_book_or_name, p, n) -> int` | M1, M3 | `agent/offer_safety.py` (offer_ok, executable_offer, settled_price) y `market.fee` |
| M5 | Ejecutor | `agent/executor.py` | punto único de escritura: STOP, modo, relectura del reloj, compuerta, diario, envío, reconciliación, contadores por tick, prioridad de la aceptación única | `Executor(transport, journal, calibrator, mode, operator)`; `.submit(intents: list[Intent], snap) -> list[Outcome]`; `.reconcile(snap) -> None`; `.halt(reason)` | M1, M2, M4, M6, M7 | `agent/execution.team_writer` (candado local) |
| M6 | Diario | `agent/journal.py` (se amplía) | `log()` se mantiene por compatibilidad. Se añaden `Journal.event(kind, **f)` con redacción y cadena de hash, y `redact(obj)` | `log(stream, **row)`; `class Journal(path)`; `.event(kind, **fields) -> int`; `redact(x) -> x` | — | el propio `journal.py` y `information.select` (lista blanca de Ruben) |
| M7 | Calibración | `agent/calibrate.py` | emparejar liquidaciones con intents, medir Δ*_points, guardar estadísticas por táctica y pausar | `Calibrator(journal, path)`; `.expect(intent)`; `.on_snapshot(snap) -> list[Measure]`; `.active(tactic) -> bool`; `.resume(tactic, reason)`; `.report() -> str` | M1, M6 | — |
| M8 | Observer | `agent/observer.py` | snapshot por tick con presupuesto, feed incremental (guarda en logs/feed.jsonl), lectura del reloj N/M/C y R, alertas de niveles y dealers, detección de escritor ajeno, redacción de `me` | `Observer(transport, journal)`; `.snapshot() -> Snapshot`; `.clock_reading() -> dict`; `.foreign_writes(snap, journal) -> list`; `.changes(prev, snap) -> list[str]` | M1, M2, M6 | `scout.py` (feed), `agent/dashboard.intel`, `scorer.dealer_changes`, `probe.shape` |
| M9 | Táctica mercado | `agent/tactics/market.py` | vender repetidos publicando, aceptar ventas o pujas con ganancia, cerrar páginas con equipos, proteger páginas, cancelar ofertas expuestas (J0) | `propose(snap, valuer, cfg) -> list[Intent]` | M1, M3 | `run_loop.best_trade` (con K-01, K-02 y K-11 corregidos), `market.sell_dups` y `market.expiry` |
| M10 | Táctica dealers | `agent/tactics/dealers.py` | máquina de estados **no bloqueante** por hilo (un paso por tick), perfiles por datos, modo PROBE para dealers nuevos, J6 | `propose(snap, valuer, state, profiles) -> list[Intent]`; `profile_from(dealer_json) -> dict` | M1, M3 | `agent/haggle.curve` y su lógica de pendientes, `agent/dealers.PROFILES` (frases), `negotiation_policy.decide_purchase` (para comparar) |
| M11 | Táctica duelos | `agent/tactics/duels.py` | política híbrida §2.3, dos issues con guarda de peor caso, prueba de reactividad y memoria por pareja | `propose(snap, state, days_cfg) -> list[Intent]`; `decide(view) -> ("accept"\|"say"\|"wait", price, days)` (pura); `utility(p, d, view, reading) -> float` | M1 | `agent/duels.step` (v0), `logs/analysis/duels/policy.py` |
| M12 | Sobres y flags | `agent/tactics/packs.py`, `agent/tactics/flags.py` | abrir todo sobre al llegar; detector de contradicciones que solo propone | `propose(snap) -> list[Intent]`; `contradictions(thread) -> list[dict]` | M1 | `run_dealer.py` (apertura de sobres) |
| M13 | Broker | `broker/plan.py`, `broker/run.py`, `broker/replay.py` | planes puros (greedy, superconjunto, público Kuhn); runner con roles primary, standby y recorder y su mini-compuerta B1–B6; ajuste y replay de sesiones grabadas | `greedy(book) -> list[tuple]`; `superset(book, state, s_hat, margin) -> list`; `public(book) -> list`; `run(role, key, journal)`; `fit(session_file) -> dict`; `replay(session_file, policy, model) -> float` | M6 (diario); **no** depende del ejecutor | `starter_broker.bench_plan/public_plan`, `logs/analysis/broker/broker_spec.py`, `sim_models.py`, `sim_superset.py` |
| M14 | CLI | `bazaar.py` | `check`, `clock`, `observe`, `run [--live]`, `stop`, `resume`, `tactic resume`, `report`, `venue arm\|open --confirm`, `broker --role`, `broker health`, `replay-friday`, `probe` | `main(argv)` | todos | `run_morning.py` (secuencia de apertura sin el reintento) |
| M15 | Servidor falso + escenarios | `sim/fake_server.py`, `sim/scenarios/*.py`, `sim/duel_rivals.py` | §3.8 | `FakeBazaar(scenario, seed).start() -> url`; `.tick()`; `.state()`; `.inject(fault)` | M1 (solo para las formas) | `logs/harvest/*.json` (formas), `logs/analysis/duels/sim.py`, `broker/sim_models.py` |
| M16 | Tests | `tests/test_static.py`, `test_gate.py`, `test_invariants.py`, `test_regressions_friday.py`, `test_chaos.py`, `test_injection.py`, `test_duels.py`, `test_broker.py`, `test_kill.py`, `test_ledger.py`, `test_valuer.py` | §3.8 | `unittest` | M15 y el módulo que prueba cada uno | `tests/test_agent_core.py` (casos de offer_ok y team_writer) |
| M17 | Panel y redacción | `agent/dashboard.py` (cambio mínimo: `me = redact(me)`) | cerrar K-13 antes de que exista el puesto | — | M6 | — |

Reparto sugerido para 3 personas (el sábado a las 09:00 basta con el núcleo):
- **Persona 1:** M1 → M5 + M6 + M14 + T-K, T-S1, T-C. El núcleo.
- **Persona 2:** M3 + M4 + M9 + M10 + M12 + T-G, T-R, T-P.
- **Persona 3:** M11 + M13 + M15 + T-D, T-B, T-I. M17 son 5 minutos de cualquiera.
- **Mínimo para las 09:00:** M1, M2, M4 (reglas G, A, L, K), M5, M6, M8, M12 (packs) y T-S1/T-K/T-R en verde. Hasta que lo demás pase sus tests, ese mínimo solo protege la página (J0), abre sobres y graba el banco (M13 recorder). M11 tiene que estar listo antes de Duels I; M13 primary/standby, antes de la decisión J7.

---

## 5. Lo que ven los jueces (40 puntos de ideas y oficio)

1. **Tesis:** "Words persuade, structure binds" convertido en arquitectura. Las políticas **no pueden** leer el texto de la contraparte (el campo se elimina del tipo que reciben), y toda estructura que aceptamos pasa una compuerta pura con 40 reglas probadas.
2. **Método científico en vivo:**
   - `docs/knowledge.md`: unos 110 hechos etiquetados, 72 afirmaciones nuestras refutadas con datos y 16 preguntas abiertas, cada una con su experimento.
   - En el juego, cada escritura lleva una predicción que se mide al liquidarse; la tabla de calibración pausa sola la táctica que falla.
   - Ejemplos: "el SAL-10 contó +50; la segunda puja de LAT decidirá entre tope y fórmula" y "¿ceden los rivales mientras callamos? Experimento en el primer duelo".
3. **Descubrimiento con datos:** `rondas = min(nY, nR)` en 148/148 instantáneas. De ahí sale que callar es gratis y que, mientras el rival no contesta, también lo son nuestros mensajes. Eso da el "ascenso holandés" frente a los rivales que solo aceptan.
4. **Demo reproducible (5 min):**
   1. `python3 bazaar.py replay-friday`: las 17 operaciones y los 30 duelos del viernes pasan por la compuerta. Bloquea los 5 tratos con pérdida (−27,6 de neg), la puesta a la venta de la última copia de LAT y el reintento de open_venue, cada uno con la regla que lo impide.
   2. `python3 bazaar.py check`: 10 000 escenarios adversariales (inyección, ofertas retorcidas, caídas, 429) con 0 invariantes rotos.
   3. El diario en vivo con su cadena de hash: intent → predicción → medición → error.
   4. El broker: la sesión grabada, el ŝ medido y la decisión numérica de abrir el venue o no.
5. **Registro de incidentes** (`docs/incidents.md`): cada error del viernes, su causa, la guarda que lo impide y el test que lo demuestra (K-01…K-17, hilo 296).
6. **Momento en pantalla grande:** la Final del domingo, "on the big screen". El diario de duelos se puede mostrar en directo con el motivo de cada movimiento.

---

## 6. Limpieza del repositorio

Una sola forma de hacer cada cosa: **`python3 bazaar.py <comando>`**. Todo lo archivado va con `git mv` a `archive/` con la misma ruta relativa (por ejemplo `archive/run_loop.py`), y `archive/README.md` dice por qué está ahí y qué lo sustituye. No se borra nada con historia útil; solo se borran artefactos generados.

| Fichero | Acción | Motivo |
|---|---|---|
| bazaar_sdk.py | keep | SDK oficial, sin editar |
| RULES.md | keep | Oficial |
| README.md | keep (reescribir la parte de equipo) | Se mantienen las §1–6 oficiales del SDK. Las secciones del equipo (recolector, laboratorio, "núcleo para Jorge", observación) se cambian por 15 líneas: cómo correr `bazaar.py` y dónde está el panel |
| CLAUDE.md | keep (reescribir) | Apunta a knowledge.md, a este diseño y a las reglas del arnés; quita las afirmaciones refutadas (offer_ok en toda aceptación, un solo ejecutor garantizado, todo queda en logs) |
| STRATEGY.md | archive | Superado por el diseño; contiene refutadas 3, 9, 10, 12, 18, 19, 36, 43, 48, 65 |
| santi/STRATEGY_v2.md | archive | Refutadas 10, 11, 12, 29, 30, 44, 57, 58 |
| santi/estrategia_el_estrangulamiento_de_rastro.md | archive | Estrategia refutada (X-04) y Fase 4 prohibida (C-12) |
| santi/The Bazaar - Kickoff.pdf | keep (git mv a docs/official/kickoff.pdf) | Material oficial; fuera de una carpeta personal |
| ANALISIS_RENDIMIENTO.md | archive | Refutada 48; sustituido por calibration report |
| RECHECK.md | archive | Refutada 11; histórico |
| INTEGRACION_JORGE.md | archive | Histórico de integración |
| HANDOFF.md | archive | Afirmaciones refutadas (66, 69); lo sustituye la sección de operación del README |
| PROPUESTA.md | archive | Refutada 55 |
| SHOWCASE.md | merge → docs/showcase.md (nuevo, con hechos medidos), y el viejo a archive | Contiene refutadas 3, 35, 39, 47, 60. La historia para los jueces se reescribe según §5 |
| docs/knowledge.md | keep | Única fuente de verdad |
| docs/openapi.json | keep | Referencia oficial |
| docs/research-context.md | keep (corregir la línea de §4 "esperar cuesta") | Fondo teórico; refutada 44 |
| docs/api.md | keep (corregir l.24, l.37, l.42) | Referencia de protocolo útil; refutadas 15, 16, 17 |
| docs/decisions.md | keep (añadir D-010+ y marcar D-006 y D-008 como superadas) | Registro de decisiones |
| docs/experiments.md | archive + uno nuevo que empiece en EXP-016 | Varias conclusiones refutadas (EXP-005b, 010, 011, 012) |
| docs/playbook.md | archive | Unas 25 refutadas; sustituido por knowledge.md + perfiles de dealers |
| docs/scoring.md | archive | Sustituido por knowledge §1 |
| docs/audit.md | archive | Histórico; refutadas 5, 13, 14, 37, 40, 42 |
| docs/broker-design.md | archive | Refutadas 50–54; sustituido por §2.4 y broker/ |
| docs/negotiation-design.md | archive | Sustituido por §2.3 y §3 |
| docs/README.md | merge → índice de 10 líneas en el README | Refutadas 13, 48, 49, 60, 63, 72 |
| docs/information.md | archive | Va con el recolector (ver abajo) |
| agent/__init__.py | keep | Paquete |
| agent/client.py | keep | Lo usa M2 |
| agent/journal.py | keep (se amplía, M6) | `log()` se mantiene por compatibilidad |
| agent/execution.py | keep | El candado local sigue sirviendo dentro de la máquina A |
| agent/offer_safety.py | merge → agent/gate.py, luego archive | Funciones reutilizadas tal cual |
| agent/haggle.py | merge → agent/tactics/dealers.py, luego archive | La curva y las pendientes se reutilizan; el bucle bloqueante y el límite sin valor (K-03) desaparecen |
| agent/dealers.py | merge → agent/tactics/dealers.py (datos), luego archive | Perfiles y frases |
| agent/duels.py | merge → agent/tactics/duels.py, luego archive | v0 queda como función base de la política híbrida |
| agent/broker.py | archive | v1 con espera, refutado (M-08); lo sustituye broker/plan.py |
| agent/scorer.py | merge (Values → agent/valuer.py; dealer_changes → agent/observer.py), luego archive | Evita dos valuadores; sus tests se portan |
| agent/information.py | archive | Lo sustituye el observer; causa los 2 errores en Windows; su lista blanca de campos se porta al redactor |
| agent/dashboard.py, agent/dashboard.html | keep (solo M17: `redact(me)`) | Panel desplegado de Santi; corrige K-13 |
| api/index.py, vercel.json, .vercelignore, run_dashboard.py | keep | Despliegue del panel de Santi |
| website/* (worker.mjs, panel.html, build.mjs, package.json, worker.test.mjs, .gitignore, .openai/hosting.json) | keep, sin tocar | Panel desplegado de Ruben; ya filtra campos por lista blanca |
| panel.py, panel.html, inventory_panel.py, live_monitor.py | keep | Panel local de Ruben (live_monitor ya filtra claves) |
| laboratorio.py, negotiation_policy.py | keep (congelados, fuera del arnés) | `inventory_panel.demo_states` y los tests del panel los importan |
| observe_performance.py | keep | Observador del panel desplegado; tiene test |
| evaluacion.py, tests/test_evaluation.py | archive | Los sustituye `bazaar.py check` |
| recheck.py | archive | Depende de otro repo y de ramas `origin/feat/jorge`; histórico |
| run_loop.py | archive | Sustituido por `bazaar.py run`; tiene K-01, K-02, K-09, K-11 y K-16 |
| run_dealer.py | archive | Sustituido por tactics/dealers; tiene K-03 y K-04 |
| run_duels.py | archive | Sustituido por tactics/duels; tiene K-07 |
| run_broker.py | archive | Sustituido por broker/run.py |
| run_morning.py | archive | Sustituido por `bazaar.py run` + `venue open`; tiene K-12 |
| market.py | merge (fee, expiry, sell_dups corregido → tactics/market.py y gate.py), luego archive | Tiene K-01 |
| scout.py | merge → observer (guardado del feed), luego archive | Dos formas de guardar el feed |
| probe.py | merge → `bazaar.py probe` (redactado), luego archive | K-13 |
| sim_bench.py | archive | Lo sustituyen broker/replay.py y los modelos A–F |
| collect_info.py, collector_mcp.py, bench_information.py, .mcp.json | archive | Recolector paralelo al observer; dos formas de leer el estado |
| starter_agent.py, starter_broker.py | keep (referencia oficial; no se ejecutan) | `bench_plan` es la referencia de equivalencia en T-B |
| tests/test_agent_core.py | merge (los casos de offer_safety y team_writer pasan a test_gate.py; los de haggle se archivan), luego archive | |
| tests/test_new_dealer.py | merge → tests/test_observer.py, luego archive | Va con scorer.dealer_changes |
| tests/test_information.py | archive | Va con information.py (los 2 errores en Windows) |
| tests/test_inventory_panel.py, test_live_monitor.py, test_negotiation.py, test_performance_observer.py | keep | Paneles |
| .gitignore | keep (+ `STOP`, `LIVE_OK`, `config/duels_days.json` local) | |
| logs/ (no versionado) | keep | Datos crudos y logs/analysis como evidencia. Los `__pycache__/` de logs/analysis se borran (son generados) |
| logs/information.jsonl | delete | Sus 112 filas vienen de los tests, no del juego (K-15) |

Ficheros nuevos: agent/model.py, transport.py, valuer.py, gate.py, executor.py, calibrate.py, observer.py, agent/tactics/{market,dealers,duels,packs,flags}.py, broker/{plan,run,replay}.py, sim/…, tests/…, bazaar.py, docs/incidents.md, docs/showcase.md, docs/official/, config/duels_days.example.json, archive/README.md.

---

## 7. Riesgos y preguntas abiertas que tocan este diseño

| Riesgo o pregunta | Probabilidad | Impacto | Mitigación o experimento | Si no se resuelve |
|---|---|---|---|---|
| Rivales mudos que nunca aceptan, de modo que el ascenso holandés no aporta | media | bajo (0 frente a 0) | J4 con los 5 duelos de práctica vivos; los primeros duelos de Duels I | Sin coste: el ascenso es gratis |
| duel_accept gasta la aceptación del equipo | desconocida | medio | Pregunta abierta 8 (J4); mientras tanto, prioridad a los duelos y el mercado espera 1 tick | Contarlo siempre como si la gastara |
| Interpretación de los días mal resuelta | media | alto (170 duelos) | Guarda de peor caso U3 y una persona fija el signo al primer payload (callar es gratis) | Jugar solo por precio con excedente ≥ 1 + max \|ΔW\| |
| Broker board caído | baja con standby | alto el domingo (50 % de la ronda 3 de market por sesión) | Standby en otra máquina, healthcheck, prueba de caos | No abrir el venue (seguimos en el puesto, mitad garantizada) |
| Latencia del board frente al auto (un tick de retraso) | desconocida | medio | Se mide en la 1.ª sesión del venue frente a la eficiencia del puesto en las sesiones grabadas | Cerrar o no abrir si sale peor que el puesto en 1 sesión |
| La grabación desde el puesto no ve el libro antes del cruce | media | medio (replay más pobre) | Usar los settlements del libro (precio medio) más bench_efficiency para validar | Abrir board con greedy puro en una sesión del sábado para obtener datos completos (riesgo: igual que el puesto si no hay latencia) |
| La curva de puntos del banco premia poco superar al puesto | desconocida | medio | Leer bench_points y market tras cada sesión (C4) | No abrir el venue |
| Dos venues por equipo (auto como suelo) | desconocida | positivo | POST de un segundo venue cuando sobre caja (rechazarlo no cuesta) | — |
| Escala de la escalera de nivel 2 | desconocida | medio | Medir Δladder en el 1.er trato con ganancia con El Chato (pregunta abierta 5) | J6 se pausa si Δladder = 0 en 2 tratos |
| Reinicio de neg/ladder al cambiar de ronda | desconocida | medio | Leer /api/me antes y después (pregunta abierta 3) | Planificar como si se reiniciara (lo hecho en la ronda 2 cuenta en la ronda 2) |
| Segundo escritor con la clave | media (pasó el viernes, K-05) | alto | La clave solo en la máquina A; detector I18 → STOP | Protocolo humano |
| Rate limit compartido con los paneles | media | bajo | Ejecutor a 3 req/s; paneles con sondeo ≥ 5 s | Bajar el ejecutor a 2 req/s |
| Una regla nueva de nivel cambia los límites a mitad de juego | media | medio | `clock.limits` se lee en cada tick; el feed avisa | La compuerta usa siempre el mínimo entre la configuración y el límite publicado |
| Modelos de rival del simulador de duelos inventados | alta | medio | Criterio de despliegue: no perder en ninguna clase; calibración en vivo con U-01 exacto | Volver a v0 (`duels.mode = v0`) |
