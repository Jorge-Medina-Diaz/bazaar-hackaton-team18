# Diseño "puntos esperados" — Team 18 (t18), sábado y domingo

Autor: diseñador independiente, lente **puntos esperados** (estratega cuantitativo). Escrito el sábado 3 oct 2026 hacia las 01:30, con el juego cerrado.
Fuentes: `docs/knowledge.md` (la base verificada; los ids P-xx, V-xx, D-xx, R-xx, X-xx, U-xx, M-xx, C-xx y K-xx son suyos), `logs/analysis/*/verify/verification.md`, `RULES.md`, el código de `agent/`, los `run_*.py`, `bazaar_sdk.py`, `starter_broker.py`, `docs/openapi.json` y los ficheros de `logs/harvest/`.
No he hecho ninguna petición a la red. No he ejecutado nada que actúe sobre el juego. Este fichero es el único que he creado.

**Etiquetas.** `[medido]` = lo rehice desde datos en bruto o lo leí en el código. `[regla]` = RULES.md, schedule, catalog o dealers.json del servidor. `[inferido]` = deducción. `[desconocido]` = no lo zanja nada en disco. Cada una lleva una confianza (alta, media o baja).
Cuando una decisión depende de algo abierto, lo digo y doy la alternativa ("fallback").

---

## 0. Resumen en diez líneas

1. **Nuestro hueco está en neg_points, no en la escalera.** Con el modelo de P-15, nuestros 19,19 puntos son 12,2 de escalera (0,051, el 97 % del techo) y 7,0 de comercio (74,5 frente a una referencia de ~186). Los equipos de arriba nos sacan unos 10 puntos ahí. `[inferido · media]`
2. **El cierre de página comprado a un equipo es la jugada más rentable que existe:** +50 de neg (SAL-10, P-07), unos 4,7 puntos de ronda. Nos tocan dos: RET el sábado y CHA el domingo.
3. **La escalera del nivel 2 (El Chato) está vacía** y la llenarán los de arriba. Si la referencia es la media del top 3, nuestra escalera puede caer del 97 % al ~35 %. Llenar los 3 huecos de El Chato con tratos que sean ganancia es la defensa. `[inferido · baja]` en el peso; `[medido · alta]` en la regla de que solo cuentan los tratos con ganancia (P-10).
4. **Las dos cosas se consiguen con el mismo plan:** montar 9/10 de RET con dealers (por debajo de nuestro valor: neg 0 y escalera elegible) y cerrar la página con una puja nuestra a un equipo (≤ 49 P). Coste ≈ 320 P; la caja del sábado es 410.
5. **No abrir venue** el sábado: con greedy rinde lo mismo que el puesto gratuito (M-04), bloquea 270 P y mata el plan RET. Se revisa el domingo solo si se cumplen unos disparadores concretos.
6. **Nunca sobres, nunca pagar a un dealer por encima de V efectiva, nunca cerrar una página con un dealer, abrir todo sobre en cuanto llegue.**
7. **Duelos:** política reactiva corregida (v0 sin K-06 ni K-07), aceptar releyendo y un experimento de reactividad gratis. No hay puntos que calcular hasta medir duel_points.
8. **El arnés** es un único proceso. Todas las escrituras pasan por un único punto de paso (`agent/gate.py`), que vuelve a comprobar cada invariante con funciones puras (`agent/rules.py`, `agent/values.py`). Tiene modos dry, live y kill, un diario con escritura anticipada (write-ahead), y compara lo predicho con lo medido en cada trato; la táctica que falla se pausa sola.
9. **El SDK es peligroso tal y como se construye hoy.** Con `wait_on_tick=True`, un `accept` rechazado con 429 se reenvía solo en el tick siguiente, sin volver a comprobar nada (bazaar_sdk.py:79-84). El gate debe usar un cliente de escritura con `wait_on_tick=False, retries=0`. `[medido · alta]` (lectura del código)
10. **Limpieza:** un comando (`python3 bazaar.py run`), un paquete (`agent/`), cuatro documentos vivos (knowledge, strategy, harness, runbook). El resto, a `archive/`. El panel y el dashboard desplegado no se tocan, salvo la redacción de claves en `agent/dashboard.py`.

---

## 1. Modelo de puntos que uso (solo lo verificado, y sus conversiones)

### 1.1 Lo medido o reglado
- **Pesos de ronda** 0,5 / 1 / 1: sábado y domingo valen lo mismo, el 40 % cada uno (P-16). `[regla · alta]`
- **Comercio con equipos:** Δneg = V − precio − comisión, y la comisión solo cuenta si aceptamos nosotros (P-03). Comisión de El Rastro = ceil(0,05·p + nº de cartas) (R-01). `[medido · alta]`
- **Con dealers:** comprar da min(0, V − p) y vender da min(0, p − V). V incluye los sobres sin abrir (P-04, P-06). `[medido · alta]`
- **El cierre de SAL-10 contó +50,0** en vez de +69,9 (P-07). La causa es desconocida: un tope de 50 por trato u otra fórmula. `[medido · alta]` el número; `[desconocido]` el mecanismo.
- **La escalera solo sube con tratos con dealer que son ganancia a nuestros valores** (P-10). Hasta t40 la negociación era solo escalera, con un máximo de 12,5 (P-13). `[medido · alta]`
- **Valores** (V-01, V-05, V-06): RET común 13, infrecuente 32,5, rara 91; bonus de página 86,1, así que la común que cierra RET vale 99,1. CHA común 16, infrecuente 40, rara 112; bonus 106, así que la común que cierra CHA vale 122. `[medido · alta]`
- **Precios de dealers** (D-01, D-05, D-09, D-10 y dealers.json):
  - Abuela: común abre en 12 y cierra con mediana 10; infrecuente abre en 29 y cierra entre 21 y 25. Tope de 8 tratos por equipo y hora.
  - El Chato: rara abre en 97 y cierra entre 90 y 93; con pasos constantes bajó a 82 y 87, en hilos que quedaron sin cerrar. Infrecuente abre en 33 y baja como mucho 1 P por ronda. Tope de 6 tratos por equipo y hora. `[medido/regla · alta-media]`

### 1.2 Conversión a puntos (lo que uso para ordenar las jugadas)
Modelo de P-15: negociación ≈ wL·min(1, L/refL) + wN·min(1, N/refN) (+ wD·duelos), con ref = media del top 3. `[inferido · media]`

Ajuste a nuestro cierre del viernes, con wL = 12,5, wN = 17,5 y refL = 0,0524 (P-13 y verify C10):
- La escalera da 12,5 × 0,051/0,0524 = **12,17**.
- El comercio da 19,19 − 12,17 = 7,02, así que **refN ≈ 186** (195 si refL fuera 0,0465). `[inferido · media-baja]`

| Unidad | Hipótesis A (12,5 / 17,5 / 0, la del viernes) | Hipótesis B (10 / 10 / 10, si los duelos entran a partes iguales) |
|---|---|---|
| 1 punto de neg | **0,094** puntos de ronda | 0,054 |
| +50 de cierre de página | **4,7** | 2,7 |
| Hueco de escalera de nivel 1 lleno (0,022), mientras no se llega al techo | **5,25** | 4,2 |
| Nuestra escalera hoy | al 97 % del techo: solo quedan **+0,33** salvo que suba refL | igual |

**Consecuencia para ordenar las jugadas** `[inferido · media]`:
- Hoy un punto de neg vale ≈ 0,094 y la escalera está saturada.
- Pero cuando el top 3 llene El Chato, refL subirá. Con un peso de nivel 2 de 1,5–2× (P-12 lo da como desconocido), refL pasaría de ~0,05 a ~0,12–0,15.
- Nuestro 0,051 bajaría entonces al 35–43 % del techo, una pérdida de 7–8 puntos que solo se recupera llenando los huecos del nivel 2.
- Si la ronda 2 reinicia la escalera (pregunta abierta 3), los 6 huecos (nivel 1 y nivel 2) vuelven a estar en juego.

**Las mismas jugadas valen en todos los casos.** Comprar a dealers por debajo de V (para la escalera, con neg 0) y cerrar páginas con equipos (para neg) es lo mejor con reinicio y sin él, y bajo A y bajo B. La incertidumbre cambia el tamaño del premio, no el orden de las jugadas. Por eso el plan no espera a resolverla.

---

## 2. Ranking de jugadas

E[pts] = puntos de negociación de la ronda (escala de 30), bajo la hipótesis A, con su rango. "Caja" = P comprometidas. Cuando la caja se convierte en cartas que valen al menos lo pagado, lo marco como "convertible": no se pierde valor, pero esa caja no está disponible para otra cosa.

| # | Jugada | Δneg | Escalera | Caja | E[pts] (rango) | pts/h | pts/100 P | Confianza |
|---|---|---|---|---|---|---|---|---|
| J1 | **Abrir cada sobre en cuanto llegue**, antes de comprar ninguna carta | evita ~−2,3 por carta comprada mientras se tiene el sobre (P-06): ~+20 en el plan RET | — | 0 | **+1,9** (1–2) | muy alto | ∞ | alta |
| J2 | **Reparar LAT**: cancelar 2463 (LAT-01 a 8) y 1652 (LAT-05 a 12 dirigida a t15); cancelar la puja 2503 (LAT-09, sin vendedor realista, X-06) | evita −1 y conserva la opción LAT; libera 62 P comprometidas | — | −62 comprometidas | +0,2 (0–0,5) | — | — | alta |
| J3 | **Huecos de nivel 2 (El Chato)**: 2 raras RET a ≤ 88 (valor 91) y 1 infrecuente RET a ≤ 30 (valor 32,5) | 0 (ganancia recortada a 0) | 3 tratos elegibles de nivel 2 | 206, convertible | **+4** (+2 a +8; defensivo) | ~6 | ~2 | baja en el peso, alta en la regla |
| J4 | **Cerrar RET con un equipo**: puja maker por la última común que falte, a ≤ 49 P | **+50** (+86 si no hay tope) | — | ≤ 49 | **+3,3** = 4,7 × P(0,7) | ~2–5 una vez en 9/10 | ~10 (solo el cierre) | media |
| J5 | **Nivel 1 (Abuela)**: 2 infrecuentes RET a ≤ 24 (objetivo 21–22) y 4 comunes RET a ≤ 11 (objetivo 9–10) | 0 | elegibles; mejoran el hueco de 0,014 | ~85, convertible | +0,5 sin reinicio (0–1,5) · **+6** con reinicio (4–12) | ~3 | ~3 | media |
| J6 | **Ventas maker de sobrantes** (dups de LAT-01 y LAT-05, LAV-03, LAV-04, MAL-04, MAL-05, dups de RET del sobre), a ≥ V + 2 y ≥ 9 | +2 a +7 cada una; +20 a +40 al día | — | entra caja | +2 a +4 | pasivo | ∞ (entra caja) | media |
| J7 | **Pujas maker por cartas RET que no cierran** (≤ V − 3: comunes ≤ 10, infrecuentes ≤ 26) en lugar de comprárselas a la Abuela | +3 a +10 cada una | — | sustituye caja de J5 | +1 a +2 | pasivo | ~4 | media |
| J8 | **Duelos I y II (sábado), III y Final (domingo)** con la política corregida | — | — | 0 | desconocido (duel_points sin mapear, U-13). Proteger: 0 acuerdos fuera de límite, menos rondas (el viernes se perdió un 15,7 %), cierre en deadline − 1 | — | — | alta en la mecánica |
| J9 | **CHA el domingo**: mismo patrón con más margen (rara 112 frente a 90–93 de El Chato) | +50 al cierre + pujas | nivel 1 y nivel 2 con más ganancia | ~320, convertible | **+8 a +14** (ronda del domingo) | ~6 | ~3 | media |
| J10 | **LAT condicional**: mantener 2504 (LAT-10 a 62). Si se cumple, LAT-09 a El Chato a ≤ 100 (neg 0, nivel 2 con ganancia ~22–40) | +1 | +1 elegible de nivel 2 | 62 + ~90 | +0,3 | — | <1 | baja |
| J11 | **Listado premium** de cartas que cierran páginas ajenas (SAL-09 ≥ 175) | +25 si se llena | — | 0 | +0,2 (probabilidad baja, R-03) | pasivo | ∞ | baja |
| — | **NO**: venue propio el sábado | 0 | — | 270 bloqueadas + 20 perdidas | −2 a +2, y bloquea J3, J4 y J9 (−5 a −10) | — | <0,7 | media |
| — | **NO**: sobres de barrio a la Abuela | −1 a −6 cada uno (VE ~18 frente a finales de 19–24) | 0 | 19–24 | −0,1 a −0,6 cada uno | — | negativo | alta |
| — | **NO**: sobre de plata | −70 (VE ~113 frente a 188) | 0 | 181–188 | −6,6 | — | negativo | alta |
| — | **NO**: primera rara de LAT a El Chato | −22 a −30 | 0 | 90 | −2,5 seguro; la segunda solo puntúa si viene de t03 | — | negativo | media |
| — | **NO**: aceptar ofertas de venta pagando comisión con ganancia < 3; vender a dealers por debajo de V; flags; directed como táctica principal (3/29) | — | — | — | negativo o desconocido | — | — | — |

### 2.1 Por qué este orden (el razonamiento que lo sostiene)
- **Las acciones por tick no son el recurso escaso.** El sábado tiene ~1.680 ticks y el mercado hizo 46 tratos entre equipos en todo el viernes (R-02). `[medido]`
- **Lo escaso es, por este orden:** (a) caja: 410 el sábado y 150 más el domingo; (b) huecos de escalera: 3 por nivel; (c) cierres de página: uno por set, cada uno de +50; (d) la cuota por hora de los dealers (8 la Abuela y 6 El Chato); (e) la atención del operador.
- **Por eso la caja va primero a lo que la convierte en cartas sin perder valor y a la vez llena escalera (J3, J5) y prepara un cierre (J4).** Las alternativas que la inmovilizan sin puntos medibles (venue) o la destruyen (sobres) quedan fuera.
- **Los pts/100 P solo cuentan la caja que no vuelve.** En J3 y J5 la caja se convierte en cartas que valen al menos lo pagado. En el venue, 250 P quedan bloqueadas y 20 se pierden.

### 2.2 Disparadores y paradas de cada jugada (codificables)

| Jugada | Se activa cuando | Se para cuando |
|---|---|---|
| J1 | Aparece un activo `kind=pack` en me.assets (subvención de las 4,05, o un regalo) | Nunca se para. Mientras haya un sobre sin abrir, el gate bloquea cualquier compra de carta que ese sobre pueda contener. |
| J2 | Primer tick en vivo. Condición: para algún set protegido, alguna carta tiene `copias_sin_listar == 0` | Cuando todas las cartas protegidas tienen al menos una copia sin listar |
| J3 | `released(RET)` y `chato ∈ unlocked` y `caja − comprometido ≥ precio + suelo` y no hay sobre sin abrir | Por rara: El Chato da `final` con precio > 88 → no aceptar, cerrar y reintentar como mucho una vez en otra hora (D-07 dice que reabrir en el mismo tick funciona; en El Chato no está medido, así que se espera 1 tick). Fin: 3 tratos de nivel 2 hechos, o RET completada hasta 9/10. |
| J4 | Exactamente 1 carta RET falta **y** las demás están en mano | Puja llena (se mide Δneg: experimento E5), o domingo 12:00 → bajar la puja a 30 y seguir |
| J5 | `released(RET)`, no hay sobre sin abrir, hilo de la Abuela libre | 7 tratos con la Abuela en la hora (cuota de 8), o RET 9/10, o `closed_reason ∈ {persona_quota, cooloff}` |
| J6 | Cada 10 ticks: carta con copia sobrante o set abandonado (LAV, MAL) | La venta no se llena en 60 ticks → bajar 1 P, nunca por debajo de V + 2 |
| J7 | RET publicada y el planner deja al menos 2 cartas sin fuente de dealer | La carta se obtiene por otra vía → cancelar la puja (evita E10, dos vías para la misma carta) |
| J8 | Aparecen duelos `live` en /api/duels | El duelo cierra. Duelos II/III: si `days_meaning` es null, se manda solo precio dentro de límite con margen ≥ 10·\|w\| |
| J9 | `released(CHA)` | Igual que J3, J4 y J5. Los dealers cierran en la hora 23 (14:00 con N). |
| J10 | 2504 se llena | Expira en el tick 205 → no repostear. Domingo: liquidar LAT si no ha avanzado. |

---

## 3. Qué NO hacer (lista cerrada; el gate lo impone)
1. No comprar sobres de ningún tipo. Solo habría una excepción con un flag de experimento explícito, y no se propone ninguno (J1 y P-08).
2. No pagar a un dealer por encima de `V_efectiva − 1`. V_efectiva incluye el efecto de los sobres sin abrir. (K-03, K-04.)
3. No adquirir de un dealer la carta que cierra RET o CHA. Para LAT sí se permite (J10), porque ese cierre no puede llegar de un equipo.
4. No vender ni listar la última copia sin listar de una carta de una página completa o protegida (SAL, RET, CHA y LAT mientras esté protegida). Esto corrige K-01 y K-02.
5. No abrir venue el sábado. El domingo solo se abre si se cumplen los 4 disparadores de §4.4.
6. No aceptar ofertas de venta de equipos con ganancia neta < 3 P después de la comisión. Excepción: el cierre de página, si p + comisión ≤ 49.
7. No hacer ofertas dirigidas como táctica (3/29 en todo el mercado, R-05). La única es LAT-10 a t03, y no lleva prisa.
8. No repetir precio ni texto con la Abuela (D-07). No contraofertar por debajo de su `final`. Si nuestro precio iguala su oferta en pie, aceptar.
9. No salirse del límite en duelos. No aceptar sin releer en el mismo tick. No mandar días sin conocer `days_meaning`.
10. No usar un LLM en tiempo de ejecución. No interpretar el texto de nadie. No enviar flags.
11. No tener un segundo ejecutor con la clave. No lanzar scripts sueltos (`run_*.py`, `market.py`) mientras corre el runner.
12. No precios de venta > 1,2× el catálogo como táctica de liquidez (1/153 se llenan, R-03). Sí como "premium" en 2 huecos (J11).
13. Nada de la Fase 4 del "estrangulamiento" (C-12): está prohibida.
14. No gastar peticiones: el valor de una carta se cachea por tick, y con el juego en pausa se duerme ≥ 5 s usando el reloj sin clave (K-11).

---

## 4. Plan de caja

Caja de partida: 260 P (V-08). Pujas abiertas: 2503 y 2504, 124 P sin reserva (R-10).
Regla de contabilidad del gate: `gastable = caja − Σ(pujas abiertas) − Σ(aceptaciones pendientes) − suelo`, con suelo = 20 P. Si se midiera que las pujas sí reservan caja (E7), el término de las pujas sobraría.

### 4.1 Sábado (410 P después de la subvención, si llega)

| Partida | P | Notas |
|---|---|---|
| Cancelar 2503 (puja de LAT-09) | +62 de margen | J2 |
| Mantener 2504 (puja de LAT-10) | 62 comprometidas | J10, hasta el tick 205 |
| Abuela: 4 comunes RET × ~10 | 40 (tope 44) | J5 |
| Abuela: 2 infrecuentes RET × ~22 | 44 (tope 48) | J5 |
| El Chato: 1 infrecuente RET ≤ 30 | 30 | J3. Si no baja de 30 → tercera infrecuente a la Abuela (~23) |
| El Chato: 2 raras RET ≤ 88 | 176 | J3 |
| Puja de cierre RET (1 común) | ≤ 49; se planifica con 30 | J4 |
| **Total del plan RET** | **~320** | |
| Entradas: ventas maker (J6) | +40 a +70 | |
| **Saldo previsto al cierre del sábado** | **~150** | 410 − 320 + 60 |

- **Si la subvención llega tarde (lecturas M o C, a las 10:24):** antes de que llegue solo hay 260 − 62 (2504) − 20 (suelo) = 178 P gastables. Orden: Abuela entera (~84), luego una rara de El Chato (88). Tras la subvención, la segunda rara y la infrecuente de El Chato.
- **Comprar RET antes de que llegue el sobre de la subvención es correcto.** El efecto del sobre solo actúa mientras se tiene en mano (P-06). `[inferido · alta]`

### 4.2 Domingo (~150 + 150 = ~300 P)
- **Plan CHA ≈ 320 P:**
  - 4 comunes de la Abuela × 10 = 40 (valor 16);
  - 2 infrecuentes de la Abuela × 22 = 44 (valor 40);
  - 1 infrecuente de El Chato ≤ 34 (valor 40);
  - 2 raras de El Chato ≤ 100 (valor 112): 200;
  - puja de cierre ≤ 49.
- **Lo que falta se cubre por este orden:**
  1. Ventas de dups de RET que salgan del sobre.
  2. Liquidar LAT a equipos si 2504 no se llenó: LAT-08 y LAT-03 a t14, y las raras que necesiten t04 y t07. Siempre como maker, a ≥ V + 5.
  3. Recortar el plan: una sola rara de CHA, y la otra rara como carta de cierre comprada a un equipo si aparece listada a ≤ 49 P.

### 4.3 Reserva para duelos y Market Test
- **Duelos:** no consumen caja. `[regla]`
- **Market Test con el puesto:** no consume caja. `[regla]` (M-02)

### 4.4 Disparadores para abrir venue (todos a la vez, nunca antes del domingo)
1. Se ha medido `bench_points` del puesto en al menos 2 sesiones. Queda una brecha frente al top 3 que vale ≥ 3 puntos de ronda.
2. Un broker distinto de greedy le gana ≥ 1,5 pp a greedy en libros de banco **reales**, grabados con la clave del puesto en modo solo lectura (E11). No vale con libros simulados.
3. `caja − comprometido ≥ 270 + plan CHA restante`.
4. Supervisión del broker con reinicio automático probada en el servidor falso: 0 sesiones perdidas en 50 sesiones simuladas con caídas inyectadas.

Si falta cualquiera de los cuatro, el puesto gratuito (la mitad de los puntos del banco, M-02) es la opción dominante.

---

## 5. Calendario

**Todos los disparadores salen de `schedule.now_hours`, de `/api/clock` y de los eventos del feed** (schedule.fired, set.released, duels, grant), nunca de la hora de pared (C-02, C-05).
Las horas de pared de estas tablas solo sirven para que las personas se organicen.
Equivalencias:
- Con ticks de 30 s y t acumulando tick_seconds (inferido, verify C1), 1 h de juego son 120 ticks.
- El tick 160 es el primero del sábado.

### 5.1 Antes de abrir (las tres lecturas)
| Hora | Acción | Quién |
|---|---|---|
| 08:45 | `python3 bazaar.py selftest`: los tests offline y el servidor falso deben salir en verde. Hasta entonces no se arranca nada. | operador |
| 08:55 | `bazaar.py clockcheck`: 1 GET sin clave a /api/clock | runner sin clave |
| 09:00:00 | `bazaar.py run --dry`: lecturas con clave, decide y escribe en el diario lo que haría, sin hacer POST | runner |
| 09:00:30 | `clockcheck` con /api/clock y /api/schedule (≤ 1/s). Clasifica la lectura N, M o C (E1). | runner |
| 09:01 | Si el modo dry muestra 2 ticks seguidos con el snapshot validado, 0 violaciones y las reparaciones J2 previstas → `run --live` | operador |

### 5.2 Sábado, las dos primeras horas, lectura N (t salta a 4,0; RET y la ronda 2 a las 09:00; subvención 09:03; banco 10:00; Duels I 11:30)

| Hora / tick | Acción | Disparador | Efecto esperado | Parada |
|---|---|---|---|---|
| 09:00 / 160 | Lectura completa. Diario del snapshot. **E2**: neg y escalera frente a 74,5 y 0,051 (¿reinicio?). | primer tick | — | — |
| 09:00–09:01 / 160–162 | **J2**: cancelar 2463, 1652 y 2503 (3 escrituras, ≤ 12 por tick) | copias sin listar = 0 | LAT protegida; +62 gastables | hecho |
| 09:00–09:04 / 160–168 | **Duelos de práctica vivos** (5, deadline 168, no puntúan). E10: acercarse al límite contra un mudo. E9: si hay oferta rival, aceptar duelo y mercado en el mismo tick. | duelos live | aprender gratis | deadline |
| 09:00–09:03 | **E3**: abrir hilo con la Abuela {buy: card RET-06}, leer su primer precio y no comprometer nada todavía | RET publicada | 17 → aceptar ya (ganancia 15,5; escalera casi completa). 29 → regateo normal | — |
| 09:03 / ~166 | Llega la subvención: **J1**, abrir el sobre en el tick siguiente | pack en assets | — | — |
| 09:04–09:40 / 168–240 | **J5**: la Abuela, en serie. Primero las infrecuentes (escalera), luego las comunes. **J3** en paralelo con El Chato: rara RET-09 con pasos constantes de +3 desde un ancla de 70. **E4**: escalera antes y después del primer trato con ganancia con cada dealer. | sin sobre; hilo libre | 6 tratos con la Abuela y 1–2 con El Chato; neg Δ = 0 ± 0,06 | §2.2 |
| 09:10 → | **J6**: reprecio de los sobrantes que expiren en 173 (LAV-04 a 14 por la demanda de t12 y t09; el resto a 9) | expiración | +2 a +7 cada una | §2.2 |
| 09:40–10:00 / 240–280 | **J3**: segunda rara y la infrecuente de El Chato. **J7**: pujas por las RET que falten si hay ≥ 2 sin fuente. | caja | — | — |
| 10:00 / 280 | **Banco #1 en el puesto** (automático). Si me trae starter_broker_key: E11, grabar el libro solo leyendo y con la clave redactada. | schedule.fired bench | mitad de los puntos del banco | — |
| 10:00–11:00 | RET a 9/10 → **J4**: puja por la común que falta a 30 (subir a 40 a los 60 ticks y a 49 a los 120). Seguir con J6. | falta 1 | +50 (E5 mide si hay tope) | lleno |

### 5.3 Sábado, las dos primeras horas, lectura C (t sigue en 2,65; banco de las 3,0 a las 09:21; ronda 2 y RET a las 10:21; subvención a las 10:24)

| Hora / tick | Acción | Notas |
|---|---|---|
| 09:00–09:04 / 160–168 | J2, duelos de práctica (E9, E10) y E2 (la ronda sigue siendo la 1) | Igual que con N |
| 09:00–09:21 | J6: vender sobrantes. **Todo lo que se haga cuenta para la ronda 1** (peso 0,5). No hay compras con ganancia: ningún dealer vende nada que nos sea ganancia antes de RET (§1.1). | — |
| 09:21 / 201 | Banco de las 3,0 en el puesto. E11 si hay clave del puesto. | — |
| 09:21–10:20 | J6 y J11. Leer el feed sin clave para E14 (multiplicadores de RET de los demás: aún nada). | Caja 260; 198 gastables tras J2 |
| 10:20 / 319 | **E2 bis**: leer /api/me en el tick 319 y en el 322, sin ningún trato entre las dos lecturas (¿se reinicia en el cambio de ronda?) | Es el experimento más limpio de reinicio |
| 10:21 / 321 | RET publicada → E3, y la Abuela (J5) con 178 gastables | — |
| 10:24 / 327 | Subvención → J1, luego El Chato (J3) | — |
| 10:24–11:00 | Igual que la tabla N de 09:04 a 10:00, desplazada 1 h 21 min | Banco 5,0 a las 11:21, Duels I a las 12:51 |

**Lectura M** (RET y ronda 2 a las 09:00; lo absoluto, incluida la subvención, desplazado): las compras empiezan como en N, pero con 178 P gastables hasta las 10:24. Orden: la Abuela entera y una rara de El Chato; después de la subvención, el resto.

### 5.4 Sábado por bloques (N; con C, sumar 1 h 21 min a lo que no esté anclado al día)

| Bloque | Jugadas | Disparadores, paradas y notas |
|---|---|---|
| 11:00–11:30 | Remate RET: cierre J4 y J7 | Si RET no está en 9/10, el planner reasigna fuentes |
| **11:30–~13:00 Duels I** | 34 duelos, hasta 3 a la vez, 16 ticks, decay 0,06 | **Durante la sesión el árbitro da la aceptación del tick a los duelos** si E9 no ha demostrado que van aparte. **E8** en el primer duelo con rival que hable: callar 2 ticks tras su primera respuesta. |
| 12:00 | Banco #2 | Medir bench_points (E11) |
| 13:00–18:00 | Mantenimiento: J6, J4 si sigue abierta, J10, J11. Ver el diario. | **Al menos una persona en SHOWCASE** (40 puntos de jueces) |
| 14:00 / 16:00 | Bancos | — |
| **18:00 Duels II** | Dos vueltas, 6 a la vez, precio y días, decay 0,08. Banco 13,0. | **E13**: leer `days_meaning` y `your_days_weight` antes de mandar nada |
| 20:00 / 21:00 / 22:00 | Bancos (el de las 21:00 es el difícil) | — |
| 22:30 | Revisar las pujas abiertas: nada se liquida de noche (R-08), pero se llenan al abrir | Cancelar las que no deban sobrevivir |

### 5.5 Domingo por bloques (ticks de 15 s: todo va el doble de rápido en la pared)

| Bloque | N | C |
|---|---|---|
| Apertura | 09:00: ronda 3 y CHA. E2 (¿reinicio?). Subvención de 150 a las 09:03 (solo caja). | 09:00: banco 17. CHA a las 10:21, subvención a las 10:24. |
| Montar CHA (J9) | 09:03–10:30. El mismo orden que RET: la Abuela, El Chato y luego la puja de cierre. | 10:24–11:50 |
| Bancos | 10:00 y 12:00 | 11:21 y 13:21 |
| Duels III | 11:00 (4 a la vez, 12 ticks, decay 0,10) | 12:21 |
| Liquidación | 12:00–13:30: LAT y sobrantes; bajar la puja de cierre a 30 si sigue abierta | 13:30–14:45 |
| Fin de los dealers | 14:00 (hora 23): la Abuela y El Chato cierran. **Último trato con dealer a las 13:45.** | Con C, la hora 23 nunca llega antes de las 15:00 |
| Final | 14:00 la Gran Final de duelos; 15:00 se congela | No hay Final (salvo que la organización reescriba el calendario) |

---

## 6. Experimentos (baratos, seguros y con fallback)

| Id | Pregunta (knowledge §preguntas) | Cómo (en el arnés) | Coste | Fallback mientras no se sepa |
|---|---|---|---|---|
| E1 | Lectura del reloj (1) | `clockcheck` sin clave; `calendar.reading()` | 0 | Disparar todo por eventos y now_hours |
| E2 | Reinicio de neg y escalera (3) | Leer me en el primer tick y en el cambio de ronda, sin tratos entre medias | 0 | Suponer reinicio para la escalera (J5 vale igual) |
| E3 | Bienvenida de la Abuela (6) | Abrir un hilo y mirar el primer precio | 0 | Regatear normal |
| E4 | Peso del nivel 2 (5) | Escalera antes y después del primer trato con ganancia de cada dealer | 0 | Hacer J3 igualmente |
| E5 | ¿Tope de 50? (4) | Δneg al llenarse el cierre de RET: +50 = tope, +86 = sin tope | 0 | Pujas de cierre a ≤ 49 |
| E6 | Δt por tick (2) | Dos lecturas del reloj | 0 | Caducidades calculadas sobre lo que devuelve el servidor (E12) |
| E7 | ¿Las pujas reservan caja? (10) | Comparar caja y pujas en me | 0 | Contarlas como comprometidas |
| E8 | Reactividad de los rivales de duelo (7) | Callar 2 ticks tras la primera respuesta del rival (callar no suma decay) | 0 | v0 reactivo |
| E9 | ¿El duel_accept consume la aceptación del tick? (8) | En la práctica, si hay oferta rival | 0 | El árbitro supone que sí |
| E10 | ¿Acepta un rival mudo? | Duelos de práctica vivos: acercarse a límite − 4 % | 0 | No acercarse en duelos que puntúan |
| E11 | Curva del banco y expires_tick (11) | Grabar el libro con la clave del puesto, solo GET y con la clave redactada | 0 | Puesto |
| E12 | Unidades de expires_in_ticks a 30 s | El primer listado: (expires_tick − created_tick) frente a lo pedido | 0 | Pedir ticks × tick_seconds / 15 y corregir |
| E13 | Días en Duels II (9) | Leer los campos antes del primer mensaje | 0 | Solo precio y margen ≥ 10·\|w\| |
| E14 | Multiplicadores de RET y CHA de los rivales (14) | Feed sin clave: pujas y ventas card:RET-xx | 0 | Precios de cierre fijos de §2 |

---

## 7. El arnés

### 7.1 Arquitectura

```
                       python3 bazaar.py run --dry | --live   (un proceso, un ejecutor)
 ┌───────────────────────────────────────────────────────────────────────────────────────┐
 │  Sensor (agent/state.py): lecturas con presupuesto de 3 req/s con clave, feed y reloj │
 │      sin clave; valida la forma y redacta claves → Snapshot (inmutable)               │
 │        │                                                                              │
 │  Calendar (agent/calendar.py): lectura N/M/C, fase, eventos del schedule y del feed   │
 │        │                                                                              │
 │  Tácticas PURAS (agent/tactics/*.py): pages, dealers, market, duels, bench            │
 │        │  → Intent{kind, target, bound, expected{dneg, dladder, dcash}, reason, tactic}│
 │  Árbitro (agent/arbiter.py): 1 aceptación por tick, 1 mensaje por hilo, ≤ 6 listados, │
 │        │  ≤ 5 hilos, ≤ 26 ofertas; prioridad = urgencia × pts esperados               │
 │        ▼                                                                              │
 │  GATE (agent/gate.py), EL ÚNICO que tiene un cliente de escritura                     │
 │    modo · STOP · lease · alarma de escritor ajeno · rutas permitidas · tokens         │
 │    relectura fresca → rules.py (puro) + values.py (puro) → WAL "intent" (fsync)       │
 │    → POST → WAL "result"                                                              │
 │        ▼                                                                              │
 │  Journal (agent/journal.py)  →  Ledger (agent/ledger.py): predicho frente a medido    │
 │                                  → breakers por táctica y globales                    │
 └───────────────────────────────────────────────────────────────────────────────────────┘
   Offline: sim/fake_server.py (HTTP local, el mismo SDK real) + sim/bots.py + tests/
```

**El bucle de cada tick**, en este orden:
1. Esperar un tick nuevo. Si el reloj está en pausa o las puertas cerradas: dormir ≥ 5 s y leer el reloj sin clave.
2. Hacer el snapshot.
3. Reconciliar las escrituras pendientes y las de resultado desconocido, y comprobar si hay un escritor ajeno.
4. El ledger mide los tratos liquidados.
5. Calendar.
6. Tácticas.
7. Árbitro.
8. Gate, que antes de cada aceptación vuelve a leer en ese mismo tick.
9. Resumen del tick en el diario.

### 7.2 Invariantes (lista completa; cada uno tiene su test)
- **I1 Punto único de escritura.** Solo `agent/gate.py` llama a `accept`, `say`, `list_offer`, `cancel`, `open_thread`, `close_thread`, `open_pack`, `duel_say`, `duel_accept`, `open_venue`, `set_fee`, `close_venue`, `flag` y `Broker.match`. Un test AST recorre el repo y falla si cualquier otro módulo los nombra. Excepción: `archive/`, `bazaar_sdk.py` y `starter_*.py`, que no se importan.
- **I2 Modo.** Sin `mode == "live"` no hay POST. En dry se ejecuta todo lo demás, se escribe "would" en el diario y se devuelve un resultado simulado.
- **I3 Kill switch.** Si existe el fichero `STOP` en la raíz o `BAZAAR_KILL=1`, ninguna escritura sale. Se comprueba justo antes de cada POST. `bazaar.py kill` lo crea; `bazaar.py resume` lo borra, y solo lo puede hacer una persona.
- **I4 Lease de un solo ejecutor.** Hay un candado local (`agent/execution.team_writer`) y además una alarma de escritor ajeno:
  - Cualquier oferta nuestra (`maker == t18`), mensaje nuestro en un hilo o mensaje nuestro en un duelo que no esté en el diario ni en la línea base heredada se trata como escritor ajeno. El gate se pone en STOP y lo anota en el diario.
  - Este es el caso del hilo 296 (K-05).
- **I5 Cliente de escritura seguro.** `Bazaar(url, key, wait_on_tick=False, retries=0)`:
  - Ningún POST se reintenta solo. Un 429 deja el intent "diferido"; el tick siguiente vuelve a decidir con datos frescos.
  - Un error de red en un POST deja el resultado "desconocido" y bloquea ese dominio (hilo, oferta o duelo) hasta que se reconcilia leyendo.
  - Base: bazaar_sdk.py:70-84. `[medido · alta]`
- **I6 Rutas permitidas.** El gate solo admite rutas de `ALLOWED_WRITES` (las de I1). Cualquier `/api/admin/*` o el parámetro `token` se rechazan antes de construir la petición (C-09).
- **I7 Presupuestos por tick, del servidor (C-07) y nuestros, más estrictos:**
  - aceptaciones: 1 por tick para todo el equipo, contando también duelos y dealers hasta que E9 diga otra cosa;
  - mensajes: 1 por hilo o duelo y tick;
  - listados nuevos y cancelaciones: ≤ 6 de los 12 por tick;
  - hilos abiertos: ≤ 5 de 6;
  - ofertas abiertas: ≤ 26 de 30;
  - todo leído de `clock.limits` en cada tick, nunca escrito en el código.
- **I8 Ritmo.**
  - Un token bucket de 3 req/s con ráfaga de 8 para la clave del equipo, dentro del proceso. Los otros 2 req/s quedan para el panel y el dashboard, con un único visor abierto.
  - Lecturas públicas sin clave a ≤ 2 req/s.
  - En pausa: ≤ 0,2 req/s.
- **I9 Relectura antes de aceptar.** La oferta que se acepta se ha leído en el tick actual (oferta de dealer: GET /api/threads/{tid}; oferta de equipo: /api/me/offers o /api/venues/rastro/offers; duelo: GET /api/duels). Su huella (id, give, want, status y expires_tick) tiene que ser idéntica a la que evaluó la táctica.
- **I10 Estructura exacta.** Para aceptar, la oferta debe pasar `rules.check_accept` (§7.3). Cualquier campo inesperado, tipo raro (bool, float, str numérica), lista con más de un elemento o lado de caja cambiado hace que se rechace.
- **I11 Banda de precio frente a valor.** Comprar: `p + comisión ≤ V_compra − margen`. Vender: `p − comisión ≥ V_conservar + margen`. Con dealers: `p ≤ V_efectiva − 1` al comprar y `p ≥ V_conservar + 1` al vender. V se calcula con `values.py`, que reproduce collection_value con error < 0,05, y se contrasta con `value?card` del servidor cuando el servidor la da.
- **I12 Activos protegidos.** Para cada carta de un set protegido o completo, `copias − copias_listadas − copias_a_vender ≥ 1`, contando los activos que hay en ofertas abiertas (K-01, K-02).
- **I13 Cierre de página.** Nunca se adquiere a un dealer la carta que deja una página RET o CHA en 10/10. LAT está en la lista `allow_dealer_close`.
- **I14 Sobres.** Comprar sobres está prohibido. Abrir es obligatorio (J1). Ninguna compra de carta mientras haya un sobre sin abrir que pueda contenerla.
- **I15 Caja.** `caja − comprometido − gasto ≥ suelo (20)`. Comprometido = pujas abiertas + aceptaciones pendientes + precio que proponemos en hilos abiertos. El venue además exige `≥ 270 + plan`.
- **I16 Concesiones monótonas.** En cada hilo y cada duelo, nuestro precio no retrocede nunca (comprando, no baja; vendiendo, no sube). El estado se reconstruye en cada arranque tomando el máximo entre el servidor y el diario.
- **I17 Duelos.** Nunca ofrecer ni aceptar fuera de `your_limit`. Excedente ≥ 1. Con días: utilidad ≥ límite + margen. Relectura y huella iguales (H4).
- **I18 Texto.** Solo plantillas de la lista, y el cortafuegos de salida de §7.3. El texto de la contraparte nunca se usa para decidir: se guarda en el diario truncado y escapado.
- **I19 Predicción obligatoria.** Todo intent lleva `expected.dneg`, `expected.dladder` (elegible o nada) y `expected.dcash`. El gate rechaza un intent con dneg previsto < −0,05, salvo que esté en un experimento con presupuesto.
- **I20 Breakers.** El ledger pausa una táctica tras 2 fallos de predicción en sus últimos 10 tratos. Cualquier Δneg medido ≤ −1 que no esté explicado pausa todas las compras. Un trato liquidado fuera de banda, detectado a posteriori, pone STOP.
- **I21 WAL.** Se escribe el "intent" con fsync antes del POST y el "result" después. Al arrancar, ningún intent sin resultado se reenvía: se reconcilia leyendo (§7.4).
- **I22 Forma desconocida.** Si una lectura no valida su esquema, ese dominio no recibe ninguna escritura en ese tick, y se anota en el diario.
- **I23 Secretos.** El diario, los snapshots y el dashboard pasan por `state.redact()`: lista blanca de campos, y se borran `*key*`, `token` y los patrones `tk-…` y `bk_…` (K-12, K-13). La clave del broker se guarda solo en `.env` y nunca se imprime.
- **I24 Juego limpio.** No operar en nuestro venue, no hacer órdenes complementarias, no "alimentar" a otro equipo. El gate rechaza `venue == nuestro_venue` y cualquier trato con el mismo equipo y la misma carta en ambos sentidos dentro de 60 ticks.
- **I25 Puertas.** Ninguna escritura con `paused` o con las puertas cerradas.

### 7.3 Reglas de guarda en detalle (pseudocódigo listo para codificar)

Funciones auxiliares de `values.py`: `fee(p, n=1) = ceil(0.05*p + n)`. `V_compra(ref)` es el cambio de collection_value al añadir una copia más, incluido el efecto sobre los sobres en mano. `V_conservar(asset)` es el cambio al quitar esa copia (incluye la pérdida del bonus si rompe una página). `cierra(ref)` es verdadero si la página queda en 10/10.

```
G0 global(intent): mode=="live" ∧ ¬STOP ∧ lease ∧ ¬foreign_alarm ∧ doors=="open" ∧ ¬paused
                   ∧ tokens>0 ∧ budgets[intent.kind]>0 ∧ ¬ledger.paused(intent.tactic)
                   ∧ ¬domain_unknown(intent.domain) ∧ journal.healthy ∧ intent.expected presente

G1 aceptar oferta de equipo (comprar carta):
   o = relectura(intent.offer_id)                     # I9, huella igual
   o.status=="open" ∧ o.venue=="rastro" ∧ o.maker∉{t18} ∧ o.to∈{None,t18}
   ∧ (o.expires_tick is None ∨ o.expires_tick ≥ tick)
   give: assets==[a] con a.kind=="card" ∧ a.ref==intent.ref; cash==0; types==[]
   want: assets==[] ∧ types==[] ∧ type(cash) is int ∧ 1 ≤ cash ≤ intent.max_price
   g = V_compra(ref) − cash − fee(cash);  si cierra(ref): g = min(g, 50)     # tope prudente
   g ≥ 3 (cierre: cash+fee ≤ 49) ∧ caja−comprometido−cash−fee ≥ 20 ∧ ¬pack_en_mano(ref)
   ∧ ¬puja_propia_abierta(ref) ∨ cancelarla_en_el_mismo_tick_no                 # E10: no dos vías

G2 aceptar puja de equipo (vender carta):
   give: type(cash) int ≥ intent.min_price ∧ assets==[] ∧ types==[]
   want: types==["card:"+ref] ∧ assets==[] ∧ cash==0 ;  elegir copia c no listada
   cash − fee(cash) − V_conservar(c) ≥ 3 ∧ protegido_ok(c)

G3 listar (maker venta):   give={"assets":[c]}, want={"cash":p}, venue=="rastro", to∈{None, equipo}
   p ≥ max(9, V_conservar(c)+2) ∧ protegido_ok(c) ∧ c∉listados ∧ ofertas_abiertas<26
   expires_in_ticks = round(ticks*tick_seconds/15) acotado a [4, 240]   # E12 corrige
G4 pujar (maker compra):   give={"cash":p}, want={"cards":[ref]}
   p ≤ V_compra(ref)−3 (cierre: p ≤ 49) ∧ 1 puja por ref ∧ ref∉objetivos_de_hilos_abiertos
   ∧ caja−comprometido−p ≥ 20

G5 mensaje a dealer (contraoferta comprando):
   p entero ∧ last < p ≤ min(intent.limit, floor(V_efectiva(ref))−1) ∧ p ≤ caja−comprometido−20
   ∧ p ≠ precio_en_pie_dealer (si igual → convertir en G6) ∧ ¬(dealer_final ∧ p < final)
   ∧ texto = plantilla[k].format(p) ∧ firewall(texto, p)
   (vendiendo: espejo, p ≥ V_conservar+1, p decreciente)
G6 aceptar oferta de dealer:
   executable_offer(o, topic, dealer, t18, tick) ∧ offer_ok(o, topic)          # reutiliza offer_safety
   ∧ precio ≤ intent.limit ≤ V_efectiva−1 ∧ ¬es_sobre ∧ ¬(cierra(ref) ∧ set∉allow_dealer_close)
   ∧ caja−comprometido ≥ precio
G7 abrir hilo con dealer: hilos<5 ∧ ningún hilo abierto con ese dealer ∧ topic exacto
   ({"buy":{"card":ref}} o {"sell":{"assets":[ids]}}) ∧ ¬pack_en_mano(ref)
G8 duelo, mensaje:  vendedor p ≥ L+1, comprador p ≤ L−1, monótono, entero ≥ 1;
   si "days"∈issues: days entero 0..10 y days_meaning conocido; si no, días = días del rival (o 5)
   y además |p−L| ≥ 1 + 10·|w| cuando w conocido
G9 duelo, aceptar:  d = relectura(duel) ∧ d.status=="live" ∧ huella(d.rival_offer)==decidida
   ∧ excedente(role, L, rival.price) ≥ 1 ∧ (días: utilidad ≥ L+1) ∧ tick ≤ deadline−1
G10 cancelar: o.maker==t18 ∧ o.status=="open"  (siempre permitido en modo live; cuenta como listado)
G11 abrir sobre: activo propio kind=="pack"  (siempre; neg no se mueve, P-08)
G12 venue: config.venue.enabled ∧ §4.4 ∧ me.venue is None ∧ once_key no usado
   (nunca reintentar; si red falla → leer /api/venues y /api/me antes de nada)
G13 broker.match (si hubiera venue board): (sell, buy) de la misma serie de banco o cruce real,
   ask ≤ price ∧ price+fee ≤ bid; nunca contra ofertas nuestras
G14 flag: deshabilitado

firewall(texto, p):  plantilla_id ∈ PERMITIDAS ∧ len ≤ 280 ∧ regex ^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ¿?¡!.,;:'"()\- 0-9]+$
   ∧ números(texto) == [p] (o [] si no hay precio) ∧ ninguna de {límite, limite, mínimo, minimo,
   máximo, maximo, reserva, valor, value, limit, clave, key, token, system, ignore, http, @}
   ∧ ningún número de V_*, límites o caja ∧ sin palabras de aceptación si la acción no es aceptar
```

Las plantillas se reaprovechan de `agent/dealers.py`, y hay que arreglar dos cosas:
- La plantilla de venta no puede decir "vengo a por esta carta" (verify de código, omisión 7).
- La plantilla de El Chato debe ser corta. Su ancla en el código es 0,70, no 0,60, y eso hay que corregirlo en la documentación.

### 7.4 Gestión de fallos
| Fallo | Respuesta |
|---|---|
| Excepción en una táctica | Esa táctica se salta en ese tick. Las demás siguen; se anota con traceback (K-16). Con 3 seguidas, la táctica se pausa. |
| Excepción en el gate o en el diario | STOP (fail closed) |
| 429 `wait_for_tick` o `rate_limited` | Intent diferido, se vuelve a decidir en el tick siguiente. Si llegan 3 seguidos, se baja el bucket a 2 req/s. |
| Error de red en un POST | Resultado desconocido. El dominio se bloquea y se reconcilia en el tick siguiente: aceptación → estado de la oferta y liquidación; mensaje → buscar nuestro precio en el hilo; listado → ofertas nuestras creadas después del tick del intent; venue → me.venue. |
| Error de red en un GET | Reintento (SDK, ≤ 2). Si sigue, se salta el tick sin escribir nada. |
| 4xx de negocio (insufficient_cash, cooloff, persona_quota, sold_out, missing_days…) | Se anota en el diario. La táctica recibe el código y aplica su parada (§2.2). |
| Forma inesperada | I22. Se guarda el payload crudo y redactado para depurar. |
| Reinicio o caída | Carga el diario, reconcilia los intents sin resultado, reconstruye la monotonía y los presupuestos del tick, y solo después escribe. Idempotencia: cada intent lleva `decision_id = hash(tick, táctica, objetivo, precio)`; no se manda dos veces el mismo id en el mismo tick. |
| Hora mal leída o calendario reescrito | Calendar solo dispara con eventos o now_hours. Si la lectura es "?", las tácticas que dependen de la hora se pausan y las demás siguen. |
| Escritor ajeno | STOP y alarma en `status` |

### 7.5 Modos
- `bazaar.py run --dry`: hace todas las lecturas con clave, todas las decisiones y escribe en el diario `would=true`. El ledger compara contra los efectos simulados. Es el modo por defecto: sin `--live` no se escribe nunca.
- `bazaar.py run --live`: además exige `config/live.json` con las tácticas habilitadas una a una y sus topes de caja por táctica.
- `bazaar.py kill` y `resume`: el STOP descrito en I3.
- `bazaar.py status`: lee el diario y el último snapshot, sin hacer ninguna llamada. Muestra el modo, las alarmas, los breakers y la caja comprometida.
- `bazaar.py flatten`: lo lanza una persona. Cancela todas nuestras ofertas abiertas, salvo los activos protegidos, que no se tocan. Sirve para dejar el juego desatendido.
- `bazaar.py selftest`: ejecuta los tests y una partida contra el servidor falso.

### 7.6 Diario y bucle de predicción frente a medición
- **Ficheros:** `logs/run/<fecha>/journal.jsonl` (append + fsync) y `logs/run/<fecha>/snap/<tick>.json`, redactado, con me, offers, threads y duels en cada tick (lo pide verify scoring, omisión 7).
- **Registro:** `{seq, ts, tick, kind: intent|sent|result|unknown|would|measure|breaker|alarm|tick, decision_id, tactic, action, args (redactados), reason, guards:[{id, ok, valor}], expected:{dneg, dladder, dcash, page}, mode}`.
- **Medición:**
  - En cada tick, el ledger empareja las liquidaciones nuevas con su decision_id: el estado de la oferta o del hilo y, si no, el evento settlement del feed.
  - Calcula `measured.dneg = neg(t) − neg(t−1)` cuando en esa ventana solo ha liquidado ese trato. Si liquidaron varios, compara las sumas.
  - Tolerancia: 0,06 + 0,01·n, por el redondeo de pantalla (verify scoring, nota 6).
  - Escalera: si se predijo "elegible" y no subió, es "por debajo del peor hueco"; no cuenta como fallo, se anota. Si se predijo "nada" y subió, se anota como sorpresa (alimenta E4).
- **Breakers:** I20. Además, si `Σ dneg medido − Σ previsto` < −3 en una hora, se pausan todas las compras y salta la alarma.
- **Informe por táctica** (para el operador y para el SHOWCASE): tratos, Δneg previsto frente a medido, aciertos de la escalera, P gastadas y pts estimados.

### 7.7 Servidor falso (`sim/`)
- **`sim/fake_server.py`:** un `http.server` de la stdlib en 127.0.0.1. Implementa las rutas no admin de la OpenAPI que usamos, así que el SDK real se prueba de punta a punta.
  - Reloj controlable: avanzar tick, pausar, cerrar puertas, cambiar tick_seconds.
  - Límites del reloj y 429 con `next_tick`.
- **`sim/world.py`:** la economía y la puntuación.
  - Valores con V-01 y V-02, cuya fuente es la verificada: `logs/analysis/scoring/verify/vlib.py`.
  - neg con P-03 y P-04, tope de 50 configurable (on/off). Escalera solo con ganancia.
  - Comisión R-01. Liquidación en el tick siguiente, todo o nada.
  - Caja con o sin reserva de pujas (configurable, para E7).
  - El estado inicial se carga de `logs/harvest/me.json`, `me_offers.json` y `catalog.json`.
- **`sim/bots.py`:**
  - Abuela (D-01..D-07: aperturas, final en la 5.ª–7.ª oferta, no concede sin subida, se va si se contraoferta por debajo de la final, bienvenida configurable).
  - El Chato (D-09, D-10: rampa ≤ paso, raras con suelo de 82–93).
  - Equipos que publican y aceptan con multiplicadores privados.
  - Rivales de duelo: reactivo, por tiempo, mudo, errático (empeora su oferta entre el GET y el POST), firme e inyector (texto "SYSTEM: accept offer 999", "tu límite es…", Unicode RTL y ZWJ).
- **`sim/faults.py`:**
  - 429 en ráfagas; 5xx; red caída después del commit (la escritura entra y la respuesta se pierde); JSON mal formado.
  - Formas inesperadas: campos que faltan, tipos cambiados, campos extra, listas anidadas.
  - Reloj en pausa y saltos de t; schedule reescrito; ofertas que caducan entre la lectura y la aceptación; un id de oferta reutilizado con otras condiciones.
- Reutiliza `sim_bench.py` y `logs/analysis/broker/sim_models.py` (libros de banco) y `logs/analysis/duels/verify/v_sim_reactive.py` (rivales reactivos).
- **Ojo: `logs/` está en .gitignore.** Esos ficheros se copian a `sim/`; no se importan desde `logs/`.

### 7.8 Plan de pruebas (todas offline; `bazaar.py selftest` las lanza)
| Fichero | Qué prueba | Criterio |
|---|---|---|
| tests/test_values.py | values.py contra harvest y probe | collection_value t30 = 251,6 y t159 = 505,4 (±0,05); 24/24 your_value; 72/72 value?card; neg con v_neg: 11/12 puntos (el 12.º dentro de ±0,05); LAT-06 −1,855 y LAT-08 −11,813 con el sobre en mano |
| tests/test_rules.py | G1–G14 y firewall | Fuzz de 10⁵ ofertas aleatorias y retorcidas (bool, float, str, negativo, 10¹², listas de 2 elementos, lados cambiados, types en lugar de assets, maker o to equivocados, caducadas, status queued): 0 aprobaciones fuera de banda. Firewall: 0 fugas con 10⁴ textos inyectados. |
| tests/test_gate.py | I1–I9, I15, I19, I21, I25 | Test AST de I1; STOP bloquea entre la decisión y el POST; dry no hace POST; los presupuestos por tick se respetan con 100 intents; el cliente de escritura tiene wait_on_tick=False y retries=0 |
| tests/test_replay_friday.py | Las decisiones reales del viernes pasadas por el gate (me_threads_full, duels_done) | Rechaza 5/5 tratos con pérdida (LAT-01 a 10, sobre a 23, LAT-06 con sobre en mano, LAT-08 a 32, venta de LAV-06 a 13); aprueba SAL-02 a 9 y SAL-08 a 24; 0/108 mensajes de duelo fuera de límite |
| tests/test_repairs.py | Estado de harvest (me.json, me_offers.json) | Al arrancar propone cancelar 2463 y 1652 (y 2503 por configuración) y nada más; nunca lista la segunda copia de LAT-01 o LAT-05 |
| tests/test_restart.py | Caída en cada punto (antes del intent, entre intent y POST, entre POST y result, con el commit hecho y la respuesta perdida) | 0 escrituras duplicadas; monotonía conservada; reconciliación correcta en 4/4 casos |
| tests/test_adversarial.py | Bots maliciosos e inyectores contra el servidor falso, 200 partidas de 200 ticks | 0 violaciones de I9–I18; 0 aceptaciones con precio cambiado; 0 textos de la contraparte en nuestros mensajes |
| tests/test_rate.py | Ráfagas de 429 y relojes de 5–60 s | ≤ 3 req/s medidos; ningún POST reintentado solo; ningún tick con 2 aceptaciones |
| tests/test_foreign_writer.py | Inyectar una oferta y un mensaje "nuestros" que no están en el diario | STOP en ≤ 1 tick |
| tests/test_calendar.py | Relojes y schedules N, M, C y reescrito | Fases y disparadores correctos; con "?", las tácticas dependientes de la hora quedan pausadas |
| tests/test_duels.py | El policy contra 6 tipos de rival × 2 papeles × decay 0,06/0,08/0,10 | 0 fuera de límite; acepta en deadline − 1 cuando hay excedente; contra rivales reactivos, igual o mejor que v0 |
| tests/test_e2e_fake.py | `bazaar.py run --live` contra el servidor falso, un sábado comprimido | Plan RET completado a 9/10 con neg Δ = 0 ± 0,06; cierre +50; ledger sin breakers; el diario reproduce cada decisión |
| (existentes) test_inventory_panel, test_live_monitor, test_performance_observer, test_negotiation | El panel | Siguen en verde. El fallo de sqlite en Windows (K-15) desaparece al archivar test_information. |

---

## 8. Plan de módulos (cada fichero lo puede construir una persona distinta)

Contrato común: `agent/types.py` es lo primero que se escribe; es corto y no cambia después. Lo demás depende solo de los tipos y de las interfaces de abajo.

| Módulo | Ficheros | Responsabilidad | Interfaz pública | Depende de | Reutiliza |
|---|---|---|---|---|---|
| types | agent/types.py | Dataclasses congeladas | `Intent(kind, tactic, domain, target, args, bound, expected: Expected, reason, experiment=None)`, `Expected(dneg: float, dladder: str, dcash: int, page: str\|None)`, `Snapshot(tick, clock, me, offers, board, threads, duels, feed, ok: dict[str,bool])`, `Result(status, decision_id, response, code)`, `Limits.from_clock(clock)` | — | — |
| values | agent/values.py | Modelo de valor y predicción de Δneg y de la escalera (puro) | `copy_value(ref, k, aff, cat)`, `collection_value(counts, packs, cat, aff, stock=None)`, `pack_ev(pack, counts, cat, aff, stock)`, `v_buy(snap, ref)`, `v_keep(snap, asset_id)`, `closes_page(snap, ref)`, `fee(p, n=1)`, `predict(intent, snap) -> Expected` | types | logs/analysis/scoring/verify/vlib.py y v_neg.py (copiados), market/verify/v_value.py |
| rules | agent/rules.py | Todas las guardas G0–G14 y el firewall (puro) | `check(intent, snap, fresh=None) -> list[Violation]`, `offer_ok`, `executable_offer`, `settled_price`, `protected_ok(snap, asset_ids)`, `firewall(text, price, secrets)` | types, values | agent/offer_safety.py (fusionado), validación de haggle.py:145-160 |
| state | agent/state.py | Lecturas con presupuesto, validación de esquema, redacción | `ReadClient(sdk_read, public, bucket)`, `snapshot(rc, prev) -> Snapshot`, `fresh_offer(rc, intent)`, `redact(obj)`, `TokenBucket(rate, burst)` | types, bazaar_sdk | information.clean/select (lista blanca), live_monitor.validate_payload |
| calendar | agent/calendar.py | Lectura N/M/C, fase y eventos | `reading(clock, schedule, first_clock) -> str`, `phase(snap) -> Phase`, `due(schedule, feed, last_seen) -> list[Event]` | types | logs/analysis/rules/verify/v_timeline.py |
| journal | agent/journal.py | WAL JSONL con fsync y lectura del diario | `Journal(path).write(kind, **row) -> int`, `.pending() -> list`, `.ours() -> set[ids]`, `log(stream, **row)` (compatible con lo actual) | — | agent/journal.py |
| gate | agent/gate.py | El único que escribe: modo, STOP, lease, alarma ajena, rutas, presupuestos, WAL, reconciliación | `Gate(write_sdk, rc, journal, mode, cfg)`, `.begin_tick(snap)`, `.execute(intent, snap) -> Result`, `.reconcile(snap) -> list[Result]`, `.foreign_check(snap) -> bool`, `make_write_client(url, key)` | types, rules, values, state, journal | agent/execution.team_writer |
| ledger | agent/ledger.py | Predicho frente a medido, breakers | `Ledger(journal)`, `.observe(snap_prev, snap) -> list[Measure]`, `.paused(tactic) -> bool`, `.report() -> dict` | types, journal | — |
| arbiter | agent/arbiter.py | Elige qué intents entran en cada tick | `choose(intents, limits, used) -> list[Intent]` (1 aceptación; prioridad: duelo en deadline−1 > final de dealer > cierre de página > resto, por expected/urgencia) | types | — |
| pages | agent/tactics/pages.py | Qué carta, de quién, a qué tope, y cuál es la de cierre | `plan(snap, cfg) -> PagePlan{set: [Need(ref, source, max_price, closer)]}` | types, values | — |
| dealers | agent/tactics/dealers.py | Máquina de regateo por tick (Abuela, El Chato) | `PROFILES` (datos), `HState.from_thread(thread, journal)`, `step(hstate, thread, snap, need) -> Intent\|None`, `open_intent(need) -> Intent` | types, values | agent/haggle.curve, agent/dealers.PROFILES (plantillas), D-03..D-10 |
| market | agent/tactics/market.py | Listados maker, pujas, aceptaciones de equipo, cancelaciones de reparación | `repairs(snap, cfg)`, `listings(snap, cfg)`, `bids(snap, plan, cfg)`, `accepts(snap, plan, cfg)`, todas `-> list[Intent]` | types, values, pages | run_loop.best_trade (corregido: copias sin listar, caché), market.fee/expiry/sell_dups (K-01 corregido) |
| duels | agent/tactics/duels.py | Policy de duelos (puro) con el experimento de reactividad | `DState`, `step(duel, dstate, tick, cfg) -> Intent\|None` | types | agent/duels.step (corregido K-06, K-07, H4), logs/analysis/duels/policy.py (fuzz con 0 violaciones) |
| bench | agent/tactics/bench.py | Grabar el libro del puesto (solo GET) y, si hubiera venue, el plan | `record(book, journal)`, `plan(book) -> list[(sell,buy,price)]` | types | starter_broker.bench_plan (= el puesto, 5000/5000), logs/analysis/broker/broker_spec.plan_public (Kuhn) |
| runner | agent/runner.py | El bucle por tick (§7.1) | `run(mode, cfg_path) -> None` | todos | run_loop.main (estructura) |
| cli | bazaar.py | Un comando | `run [--dry\|--live]`, `kill`, `resume`, `status`, `flatten`, `selftest`, `clockcheck` | runner, gate, journal | probe.py (snapshot redactado) |
| config | config/live.json, config/dry.json | Tácticas habilitadas, topes y márgenes | — | — | — |
| sim | sim/fake_server.py, sim/world.py, sim/bots.py, sim/faults.py, sim/bench.py | Servidor falso y bots | `serve(port, world, faults) -> thread`, `World.from_harvest(dir)`, `Bots.*` | values (solo para la puntuación), bazaar_sdk | sim_bench.py, broker/sim_models.py, duels/verify/v_sim_reactive.py |
| tests | tests/test_*.py (§7.8) | Las pruebas | — | sim | — |

**Orden de construcción:**
- Primero types.
- Después, en paralelo: values, rules, state, journal, calendar, sim/world y sim/bots, y las cuatro tácticas.
- Luego gate, ledger y arbiter.
- Al final runner, cli y la prueba e2e.

**Las tácticas no importan ni el gate ni el SDK.** Reciben un Snapshot y devuelven Intents, así que se prueban sin red.

---

## 9. Limpieza del repositorio

**Reglas:**
- Archivar es `git mv <f> archive/<f>`, conservando la ruta.
- Se borran los ficheros generados.
- Los documentos vivos son cuatro: `docs/knowledge.md` (hechos), `docs/strategy.md` (el plan elegido, de los tres diseños), `docs/harness.md` (§7) y `docs/runbook.md` (cómo arrancar a las 09:00).

| Ruta | Acción | Motivo |
|---|---|---|
| RULES.md | keep | Oficial |
| README.md | keep | Readme oficial del SDK. Las añadidas del equipo pasan a docs/runbook.md. |
| CLAUDE.md | keep (reescribir) | Instrucciones del proyecto. Quitar las afirmaciones refutadas 60, 63 y 67 y apuntar a knowledge y harness. |
| SHOWCASE.md | keep (reescribir el domingo) | Para los jueces (40). Hoy contiene refutadas (35, 39, 47, "Next steps"). Se regenera desde knowledge y el informe del ledger. |
| STRATEGY.md | archive | Refutadas 3, 9, 10, 18, 19, 36, 43, 48 y 65 |
| ANALISIS_RENDIMIENTO.md | archive | Refutada 48. Su aviso sobre keep_value queda resuelto al archivar scorer. |
| HANDOFF.md | archive | Refutadas 66 y 69 |
| INTEGRACION_JORGE.md | archive | Notas de integración ya superadas por el arnés |
| PROPUESTA.md | archive | Refutada 55 |
| RECHECK.md | archive | Refutada 11 |
| santi/STRATEGY_v2.md | archive | Refutadas 10, 11, 19, 29, 30 y 57–58 |
| santi/estrategia_el_estrangulamiento_de_rastro.md | archive | Refutada 31; Fase 4 prohibida (C-12) |
| santi/The Bazaar - Kickoff.pdf | keep (git mv a docs/official/kickoff.pdf) | Oficial |
| docs/knowledge.md | keep (añadirlo a git) | La fuente de verdad |
| docs/openapi.json | keep | Oficial |
| docs/research-context.md | keep (añadir una nota en §4) | Base de ideas para los jueces. §4 "esperar cuesta" está refutado (44). |
| docs/README.md | merge → docs/runbook.md, y archive | Refutadas 13, 48, 60 y 63 |
| docs/playbook.md | archive | Muchas refutadas (1, 4, 5, 7, 13, 14, 20–27, 33, 34, 39, 41, 45, 46, 56, 70, 71) |
| docs/scoring.md | archive | Refutadas 1–4, 8 y 56. El modelo correcto está en knowledge §1. |
| docs/audit.md | archive | Refutadas 5, 13, 14, 37, 40 y 42 |
| docs/experiments.md | archive | Refutadas 6, 27, 38 y 39. Los experimentos nuevos van en strategy.md (§6). |
| docs/decisions.md | archive | Refutadas 28, 32 y 41. Las decisiones nuevas van en strategy.md. |
| docs/api.md | merge (expiración, your_value) → knowledge §API, y archive | Refutadas 15, 16 y 17 |
| docs/broker-design.md | archive | Refutadas 50–54 |
| docs/negotiation-design.md | merge (plantillas) → agent/tactics/dealers.py, y archive | Solo una forma de negociar |
| docs/information.md | archive | Va con el colector archivado |
| bazaar_sdk.py | keep (no tocar) | Oficial |
| starter_broker.py | keep | Oficial. bench_plan se importa (= el puesto). |
| starter_agent.py | archive | Ejemplo oficial que compra un sobre: nunca se ejecuta |
| run_loop.py | archive | Lo sustituye agent/runner.py. best_trade pasa a tactics/market. |
| run_dealer.py | archive | K-04: 3 sobres a ≤ 23. Lo sustituye tactics/dealers. |
| run_duels.py | archive | K-07: sin tick. Lo sustituye tactics/duels. |
| run_broker.py | archive | Sin venue no hace falta. bench.record lo sustituye. |
| run_morning.py | archive | K-12: reintenta open_venue. Lo sustituyen bazaar.py y G12. |
| market.py | archive | K-01. Su lógica pasa a tactics/market, ya corregida. |
| scout.py | archive | Lecturas ad hoc. Las cubre state.snapshot. |
| probe.py | merge → bazaar.py (snapshot redactado), y archive | K-13 |
| sim_bench.py | merge → sim/bench.py, y archive | Un solo simulador |
| collect_info.py, collector_mcp.py, bench_information.py | archive | Colector paralelo con clave: gasta presupuesto de ritmo y es una segunda vía de lectura. Su `clean()` pasa a state.redact. |
| .mcp.json | delete | Solo registra collector_mcp |
| evaluacion.py, recheck.py | archive | Evaluación del laboratorio; no los usa el panel |
| negotiation_policy.py, laboratorio.py | keep (marcarlos como "laboratorio del panel, no los usa el arnés") | tests/test_inventory_panel.py importa laboratorio, que a su vez importa negotiation_policy. Hay que conservar el panel. |
| panel.py, panel.html, inventory_panel.py, live_monitor.py | keep | El panel del compañero. Nota en el runbook: un visor como mucho (I8). |
| observe_performance.py | keep | Observador del artefacto desplegado, solo lectura; cadencia ≥ 5 s |
| run_dashboard.py, api/index.py, vercel.json, .vercelignore | keep | Dashboard desplegado. En .vercelignore, añadir `archive/`, `sim/` y `config/`. |
| website/* (build.mjs, package.json, panel.html, worker.mjs, worker.test.mjs, .gitignore, .openai/hosting.json) | keep | Despliegue del compañero; no se toca |
| agent/__init__.py | keep | — |
| agent/client.py | keep | Lo usan el dashboard y el arnés. Añadir `make_write_client`, o hacerlo en gate. |
| agent/dashboard.py, agent/dashboard.html | keep (arreglar `snapshot` con una lista blanca de campos de /api/me) | K-13: no puede salir starter_broker_key |
| agent/journal.py | keep (ampliar: WAL y fsync) | — |
| agent/offer_safety.py | merge → agent/rules.py | Un solo módulo de guardas |
| agent/execution.py | merge → agent/gate.py (Lease) | — |
| agent/haggle.py | merge (curve) → agent/tactics/dealers.py, y archive | K-03. El bucle bloqueante se sustituye por step por tick. |
| agent/dealers.py | merge (PROFILES, plantillas) → agent/tactics/dealers.py | — |
| agent/duels.py | merge → agent/tactics/duels.py | K-06 y K-07 corregidos |
| agent/broker.py | archive | Refutadas 50 y 51; greedy = el puesto |
| agent/information.py | archive | Ver colector |
| agent/scorer.py | archive | Segundo modelo de valor. Riesgo de keep_value, y no está verificado contra harvest. values.py es la única valoración. |
| tests/test_agent_core.py | archive (lo sustituyen test_rules, test_gate y test_replay_friday) | Importa haggle y scorer, que se archivan |
| tests/test_new_dealer.py | archive | scorer |
| tests/test_information.py | archive | Colector. Además daba los 2 errores de Windows (K-15). |
| tests/test_evaluation.py | archive | evaluacion |
| tests/test_negotiation.py, tests/test_inventory_panel.py, tests/test_live_monitor.py, tests/test_performance_observer.py | keep | Panel y laboratorio |
| .gitignore | keep (añadir `STOP`, `config/local*.json`) | logs/ y runs/ ya están ignorados |
| __pycache__/, agent/__pycache__/, tests/__pycache__/ | delete | Generados |
| runs/ (ignorado) | delete en local tras archivar recheck | Salida de recheck |
| logs/ (ignorado) | keep en local | Datos. Lo que el arnés necesite de logs/analysis se copia a ficheros versionados. |

---

## 10. Riesgos (y qué los cubre)
1. **El peso de la escalera de nivel 2 y la fórmula de ref son inferencias.** Si el nivel 2 pesa poco, J3 sigue sin perder nada: las cartas valen ≥ lo pagado. Lo cubre E4.
2. **El tope de 50 puede ser otra cosa.** Con las pujas de cierre a ≤ 49 se gana en todas las hipótesis. Lo cubre E5.
3. **Que no aparezca vendedor de la carta de cierre de RET** (oferta escasa el sábado temprano). Fallback: la puja sube a 49; el domingo, cualquier carta RET que falte listada a ≤ 49 sirve de cierre. El plan elige como cierre la carta con más oferta en el feed.
4. **Lectura C:** el Final del domingo no llega y los dealers no cierran. Todo lo dispara el calendar, así que no depende de la hora.
5. **Un segundo escritor con la clave** (tres personas). Lo cubren el lease, la alarma de escritor ajeno y el STOP. La clave solo en una máquina.
6. **Reintentos ocultos del SDK.** Lo cubre I5. Tiene test.
7. **Ritmo compartido con el panel y el dashboard.** I8: un solo visor y ≤ 3 req/s para el runner.
8. **Cambio de reglas o límites en caliente.** Los límites se leen de `clock.limits` en cada tick y el feed se vigila en busca de anuncios.
9. **Caja sin reserva de pujas.** I15 las cuenta como comprometidas.
10. **Duelos: el mapeo a puntos es desconocido.** La policy minimiza el riesgo de perder (0 fuera de límite, aceptar en deadline − 1) y mide duel_points.
11. **Los jueces (40):** si el arnés no tiene un informe legible, se pierde lo que más pesa. El ledger produce el informe y el domingo se reescribe SHOWCASE.
