# Los Pícaros (nivel 4): análisis y plan para el domingo

*Sáb 3 oct, ~17:00 (t ≈ 7,75 h). Abren a todos a **t = 8,67 h** (hoy, ≈17:40–18:00; comprobarlo con `clockcheck`). Mañana abren a las 09:00 (t = 14,08) con ticks de 15 s. CHA se publica a t = 16,65 (≈11:34) y las +150 primas llegan a 16,7. El Bazar cierra a las 15:00 (t = 20,08).*
*Etiquetas: `[medido]` (feed público, ticks 76–779), `[código]` (lectura del repo), `[regla oficial]`, `[inferido]` y `[hipótesis]`. Los datos de los Pícaros salen de **unos 17 ticks (762–778), 9 equipos, 18 hilos, 37 ofertas y 3 tratos**. Muestra pequeña: todo lo que pase de n ≈ 5 es provisional.*

## 1. Resumen
1. Son dos hermanos, Paco y Nando, un dealer «trickster» de nivel 4. **Venden** raras (lista 63) y épicas (lista 162) de sets publicados y **compran** comunes e infrecuentes, con un tope de 6 tratos por equipo y hora `[API]`.
2. **Son la fuente de raras más barata que hemos medido.** Abren siempre a 73, la rara se cerró a 67, 58 y 54 (n = 3, media 59,7), y El Chato la vende con mediana de 89,5 (n = 26) `[medido]`.
3. **Como compradores son los peores del juego.** Pagan 4 por una común y entre 10 y 13 por una infrecuente. Ningún equipo les ha vendido nada (0 tratos) `[medido]`.
4. **Su trampa está en la estructura de la oferta, no en el texto.** En 4 de 11 ofertas de venta, `give.types` trae una **infrecuente del mismo set** al precio de una rara, mientras el texto nombra la rara. Una de esas 4 era su `final` `[medido]`.
5. **Por qué importan mañana:**
   - Pueden abaratar las dos raras de CHA (unos 30 P menos que con El Chato, `[inferido]`).
   - Son el nivel más alto de la escalera, que solo cuenta tratos con ganancia a nuestros valores (P-10).
   - Hoy **el arnés no puede negociar con ellos**: no hay plantilla, perfil ni filtro de ofertas trucadas (§7).

## 2. Rasgos y lo que significan en la práctica

| rasgo | Abuela | Chato | Pilar | **Pícaros** | Qué se ve en los Pícaros |
|---|---|---|---|---|---|
| paciencia | 0,85 | 0,35 | 0,60 | **0,40** | Dan la `final` en su 3.ª–4.ª oferta (6 de 6 hilos con final). Los demás la dan en la ronda 5–6 (abajo) `[medido]` |
| generosidad | 0,80 | 0,25 | 0,50 | **0,60** | En raras, la concesión total es del 20,5 % (n = 3, rango −8 a 26 %). El ajuste con los otros 3 dealers predecía un 16,3 % (`[hipótesis]`, 3 puntos) |
| astucia | 0,20 | 0,85 | 0,75 | **0,70** | Comprando son rígidos: común fija a 4, infrecuente de 10 a 13. Vendiendo bajan más que nuestro paso (n = 2 válidos) |
| memoria | 0,15 | 0,90 | 0,70 | **0,30** | `[inferido]` Reabrir un hilo sale barato. La apertura es una constante por categoría en todos los dealers |
| rigor | 0,10 | 0,85 | 0,60 | **0,10** | Ninguno de sus 18 hilos acabó con ellos marchándose. Aceptaron 58 por la rara justo después de una «final» de 59 que traía otra carta (n = 1) |
| charla | 0,75 | 0,30 | 0,55 | **0,80** | Textos con una mediana de 258 caracteres (Chato 79, Pilar 178, Abuela 222), con urgencias y escaseces inventadas |

**Métricas medidas por dealer** `[medido]` (cifras del verificador donde corrigió):

| métrica | Abuela | Chato | Pilar | Pícaros |
|---|---|---|---|---|
| apertura / lista | 1,15–1,20 | 1,26–1,27 | — (compra a 16 en LAT/LAV/MAL y a 22 en SAL/RET) | **1,16** (73/63) |
| concesión total mediana | 20–26,7 % | 6,1–7,7 % | 12,5 % (infrecuente, n = 36) y 10,6 % (rara, n = 2) | rara 20,5 % (n = 3); común 0 %; infrecuente +30 % (n = 1) |
| ronda mediana de la `final` | 5 (n = 82) | 6 (n = 42) | 5 (n = 27) | **3–4** (n = 6) |
| trato al precio de la final | 37/38 | 23/23 | 18/18 | 0/1: cerró 1 P por debajo de una final que traía la carta cambiada |
| concede más que nuestro paso | sobre 19 %, infrecuente 14 %, venta de común 1 %, compra de común 0 % | 0 de ≈620 | 0 de ≈204 | 4/4, aunque solo 2 son de la rara real (73→60→56 con pasos de +3) |
| hilos en los que se van (por hilo) | 4,5 % | 1,8 % | 1,1 % | 0 de 18 |
| longitud del texto | 222 | 79 | 178 | 258 |

**Predicción para los Pícaros:**

| situación | predicción | intervalo | medido (n) |
|---|---|---|---|
| apertura de una rara | 73 | fija | 73 en todas las aperturas (5–6) |
| cierre de una rara negociando | ≈57 `[inferido]` | 54–67 | 54, 58, 67 (3) |
| ronda de la final | 3.ª–4.ª oferta | — | 3,3,3,3,4,4 (6) |
| probabilidad de carta cambiada en una oferta de venta | ≈36 % | muy incierta | 4/11; 3 de 6 contraofertas |
| épica (lista 162) | apertura ≈188, cierre ≈140–148 | **sin datos** | 0 |
| que nos compren una común | 4, y no se mueven | 4–5 | 17 de 19 ofertas a 4 (8 hilos) |
| que nos compren una infrecuente | 10 → 13 final | — | 1 hilo completo |

## 3. Cuánto pesan nuestras ofertas según el dealer

| dealer | elasticidad (concesión según nuestro paso, solo compras) | 1.ª rebaja sin que nos movamos | si repetimos o retrocedemos | hueco que acepta | ronda de la final | etiqueta |
|---|---|---|---|---|---|---|
| **Abuela** | casi plana: paso 1 → 1,33 (n = 210), 2 → 1,23 (138), 3 → 1,41 (27), 4 → 1,56 (16). En sobres el paso pesa algo (pendiente 0,17) | **3 P** (mediana, n = 197) | 0 de concesión (65/65 en todos los dealers). Se va con texto un 11 % de las veces | 1 P: 42 % (35/83; infrecuente 14/17, común 19/67). 2 P: 7 % (5/74) | 5 | medido |
| **Chato** | **umbral en 4**: paso 1 → 0,69 (139), 2 → 0,76 (74), 3 → 0,80 (59), 4 → 1,83 (46), ≥6 → 1,87 (52) | 0 (112 de 139 hilos) | 0 | 1 P: 9/15 (rara 4/4). 2 P: 2/16. 3–5 P: 2/73 | 6 | medido |
| **Pilar** (nos compra) | +1 por ronda desde su 2.ª oferta, sea cual sea nuestro paso. Nunca concede más que nuestro paso. En rara la pendiente es 0,24 (n = 28) | 0 (abre a 16 o 22) | 0 | 1 P: 6/6. 2 P: 0/10. 3–5 P: 0/45 | 5 | medido |
| **Pícaros vendiendo raras** | con la carta real: 73→60→56 tras pasos de +3 (n = 1 hilo) y 73→67 tras nuestro 55 | 6 (1061). Las rebajas de −8/−9 eran ofertas con la carta cambiada | sin datos | aceptaron 58 frente a su 59 (de otra carta) y 54 frente a 56 (n = 2) | 3–4 | medido n ≤ 3 |
| **Pícaros comprando comunes** | 0 (subieron a 5 en 1 de 7 hilos) | 0 | — | **rechazan incluso 1–2 P** (0/4) | 3–4 (final a 4) | medido |

**Lectura** `[inferido]`:
- En los grupos grandes, lo que cuenta es moverse o no moverse. El tamaño del paso apenas importa, salvo en tres casos:
  - El Chato, que reacciona a pasos de 4 o más.
  - Los sobres de la Abuela.
  - Las raras de Pilar.
- Repetir cifra nunca saca concesión.
- Con los Pícaros, la diferencia entre subir de 1 en 1 (t01 cerró a 58) y de 3 en 3 (t05 cerró a 54) es un caso por lado. No es una regla.

## 4. Nuestro historial: lecciones
Feed `[medido]`: **21 hilos y 13 tratos** (Abuela 8, Chato 4, Pilar 1); en 1 hilo el dealer se fue.

| | t18 | resto | lectura |
|---|---|---|---|
| Abuela, tasa de cierre | **8/10** | 87/227 (38 %) | Nuestra fuerza: cerrar |
| 1.ª contraoferta / apertura | 0,58 común · 0,59 infrecuente · 0,50 sobre | 0,42 · 0,41 · 0,33 | Abrimos alto: cerramos rápido y pagamos un poco más |
| Raras del Chato | 86, 86 (pasos de 70→74→78→82→86) | mediana 89,5 (n = 26) | **El paso constante de 4 funcionó** (percentil ~25) |
| Infrecuente del Chato | 32 | 30,5 | Caro (percentil 88) |
| Venta al Chato | 13 (su apertura) | 14 | Concedimos 9 P y él 0 |
| Venta a Pilar | 16 (LAT-06, tick 741) | mediana 19 (n = 38, rango 16–25) | Precio mínimo empatado (2 de 43 tratos a 16). Era **un repetido**: a nuestros valores fue ganancia `[inferido]` |

**Bien:**
- Tasa de cierre alta.
- Paso constante de 4 con El Chato.
- Cambiar de dealer cuando uno se planta: RET-08 con final de 31 del Chato, comprada a la Abuela a 22; LAT-06 del Chato a 32, comprada a la Abuela a 22.

**Mal:**
- Subir de 1 en 1 con El Chato (hilo 398: burla y final a 31).
- Repetir nuestra cifra con la Abuela (hilo 224: se fue).
- Aceptar la apertura de un dealer cuando le vendemos.
- **Llegar 1,2 h tarde a Pilar.** Solo tuvimos 1 trato visible con ella, así que no desbloqueamos a los Pícaros pronto (entraron 9 equipos). La regla real de recuento del servidor no se reproduce (D-18). Descarto la hipótesis de las «anclas abusivas», que es inconsistente.

**Aplicado a los Pícaros:**
- Estar el primer tick que abran.
- No subir de 1 en 1.
- No repetir cifra.
- No aceptar a ciegas: comprobar la carta en cada oferta.

## 5. Catálogo de trucos y detección

| id | truco | n `[medido]` | ejemplos (oferta/mensaje) | qué hacemos |
|---|---|---|---|---|
| **T1** | **Carta cambiada**: `give.types` lleva una infrecuente del mismo set (libro 25) y el texto nombra la rara (libro 70). **Va más barata que la oferta legítima**: es un cebo | 4 de 11 ofertas de venta; 3 de 6 contraofertas; también en la apertura de un hilo reabierto y en una `final` | 11718/7124 LAV-09→LAV-06 a 64 · **11730/7130 LAV-09→LAV-08 a 59, final = true** · 11777/7160 SAL-09→SAL-06 a 65 · 11834/7201 LAV-10→LAV-08 a 73 | Rechazar por estructura. **Es el único candidato a flag** |
| T3 | Inversión de rol: en hilos donde nos compran, el texto suena a que nos venden («Para ti… cuatro perlas») | 9 de 9 aperturas de compra | 11597, 11687, 11858 | Ignorar |
| T4 | Rareza o escasez falsa («rare», «la última de Madrid», «dejaron de imprimirla»). Vendieron **dos** SAL-09 (series 9 y 11); los dealers acuñan (D-12) | 1 + 4 + 4 | 11687, 11644, 11598… | Ignorar |
| T6 | «Final» o «última» en el texto con `final = false` | 4 | 11774, 11798, 11814, 11845 | Ignorar; solo cuenta el campo |
| T7 | Concesión fingida («Fine, 4 P» repitiendo precio) | 2 | 11746, 11816 | No contarla como movimiento |
| T8 | Urgencias (taxi, tren, policía, «otro equipo paga más») | 29 de 37 | casi todas | El plazo real es `expires_tick` = creación + 4 (37/37). **Es el estándar de todos los dealers**: el domingo son 60 s |
| T9 | Unidades inventadas (perlas, pesos) | 19 | 11597, 11598 | Cosmético: la cifra coincide con el cash (37/37). Ojo: el texto incluye otras cifras |
| T2/T5 | Extras en `give`/`want` o cifra del texto ≠ cash | **0** | — | Ya lo cubre `offer_safety` |

**Hechos clave** `[medido]`:
- Los 3 tratos entregaron la rara correcta: en 2, el dealer aceptó **nuestra** oferta (`want.types = [card:X]`); en 1, el equipo aceptó una oferta suya que era correcta.
- Nadie ha aceptado nunca una oferta cambiada. Que entregaría la infrecuente es `[inferido]`, y no hay que comprobarlo.

**Reglas estructurales** (hilo `buy card:X`):
1. Aceptar solo si `give.types == ["card:X"]`, sin cash ni assets en `give`, sin types ni assets en `want`, y `want.cash ≤ límite`. Esto ya lo exige `offer_safety.offer_ok` `[código]`. **Comprobarlo en cada oferta, también en la `final`.**
2. Preferir que el trato salga de **nuestra** oferta: contraofertar 1–2 P por debajo de su último precio legítimo.
3. Una oferta con la carta cambiada **no es precio**: no cuenta como su posición, no bloquea y no se acepta.
4. La comparación es `give.types` frente a `topic.buy.card`. **Nunca contra el texto**: el texto siempre nombra la carta buena.

**Flags** `[regla oficial]`:
- «A correct flag scores, a wrong one costs». No se conoce la cifra.
- Solo se pueden marcar mensajes de nuestros hilos.
- Hoy no se puede enviar ninguno: no hay kind `flag`, `contracts.py` está congelado, `transport` no tiene la ruta y los tests prohíben `/api/flags`. Además lo prohíben strategy.md (Nunca #9), INV-01 e INV-20.
- **Decisión del lead.** Mientras no la haya, registrar a mano los `message_id` T1 de nuestros hilos.
- Si se habilitara, marcar **solo T1**. T6 y T8 son labia de personaje y el riesgo de un flag erróneo es alto.

## 6. Estrategia

### Qué comprarles y a qué tope
Valores de la 1.ª copia de una rara (V-05 y V-07): CHA 112, RET 91, SAL 77, LAT 63 (la que cierra LAT vale 122,6), LAV 49, MAL 35. Caja: 235.

| # | Qué | Cuándo | Tope | Por qué |
|---|---|---|---|---|
| 1 | **CHA-09** (rara) | dom, en cuanto se publique CHA (t = 16,65) | **60** `[hipótesis]` | Ganancia a nuestros valores, así que entra en la escalera de nivel 4 (P-10). Ahorra unos 30 de caja frente al Chato para cerrar CHA |
| 2 | **CHA-10** | justo después (un hilo por dealer) | 60 | 2.º hueco de nivel 4. Respaldo: El Chato (`CHA:rare`) |
| 3 | LAT-09, opcional | solo si la caja lo permite después de CHA | 58 | V 63: margen muy justo |

`[inferido]` Plan CHA con raras de los Pícaros: unos 300 de caja, frente a 330–360 con El Chato. Hay 385 disponibles (235 + 150). LAT-09 cabría (≈355); LAT-10 a 72 ya no. **CHA primero.**

**No comprar:**
- **Épicas.** No hay ningún dato de precio y cuestan unos 140–190 de una caja que hace falta para CHA. El valor de colección no puntúa.
- **Raras repetidas** (2.ª copia de SAL o RET ≈ 19–23). Con un dealer, comprar suma min(0, V − precio) (P-04): una SAL-09 a 57 serían unos −38 de `neg_points`.
- **Arbitraje con Pilar.** Comprar una SAL a los Pícaros y vendérsela a Pilar, aunque la fiebre de Salamanca le suba el precio, da caja pero pierde unos 38 de `neg_points` en la compra. **No.**

### Qué venderles y a qué suelo
- **Solo LAT-01 #2** (nuestro único repetido, your_value 2,2). Hay que aceptar su 4. El suelo de G30 es ceil(2,25 + 1) = 4 `[código]`.
  - Da +1,75 y llena un hueco de escalera.
  - Si el servidor da a `dv_rm` un valor mayor de 3, el suelo sube a 5 y la Gate no deja vender: no pasa nada.
- Nada más: nuestras comunes e infrecuentes quedan por debajo del suelo, y Pilar o la Abuela pagan más.

### Secuencia de puja de una rara `[hipótesis sobre n = 3]`
1. `open_thread` buy `card:X` con `limit` = min(60, floor(dv_add − 1)).
2. Su apertura será 73. **Ancla 45–48** (t05 abrió a 45 y cerró a 54; t01 abrió a 55 y cerró a 58).
3. **+3 por ronda**, sin repetir nunca cifra: 45 → 48 → 51 → 54 → 57 → 60.
4. Si su oferta **legítima** es ≤ nuestra puja siguiente, aceptarla por la Gate (G31 lo exige y G32/`offer_ok` comprueban la carta).
5. Si su oferta trae la carta cambiada: no es precio. Seguir pujando nuestra cifra siguiente y apuntar el `message_id`.
6. Ante una `final` legítima por encima del tope: una contraoferta a final − 1 o − 2 si cabe en el tope. Con el rigor de 0,1 no se castiga (n = 1, `[inferido]`). Si no cabe, cerrar.
7. **Irse:** 5–6 rondas sin llegar al tope, o `fallback_after` (unos 12 ticks = 3 min el domingo). Entonces pasar a El Chato con paso constante de 4.
8. **Velocidad:** cada oferta caduca en 4 ticks (60 s). El runner tiene que contestar en cada tick.

### Interacción con Pilar y El Chato
- **Pilar:** no le compramos (solo vende sobre_oro). Fiebre de Salamanca hoy: no tenemos repetidos de SAL ni RET, y las tenemos protegidas (G13), así que **no nos afecta**. No usar a los Pícaros como proveedor para revender (ver arriba). Desconozco el detalle de la fiebre `[pregunta abierta]`.
- **El Chato:** respaldo de CHA-09 y CHA-10. Memoria 0,9: no abrir hilos que vayamos a abandonar. Su v3 cerró 4 de 21 hilos de rara (77, 81, 90, 96).

### Plan para hoy (desde t = 8,67)
1. **Antes:** en la máquina A, `status` o `/api/me` para confirmar que `picaros` aparece en `me.unlocked`. Si no, G30.locked: no se hace nada.
2. **Vender LAT-01 #2 a 4**, con 4 intents manuales y sin cambiar código:
   - `cancel` en El Rastro si está publicada;
   - `open_thread {"dealer":"picaros","side":"sell","ref":"LAT-01","asset_ids":[<id #2>],"limit":4}`;
   - esperar su oferta;
   - `accept {"source":"dealer","side":"sell","price":4,"venue":"picaros",...}` si `offer_ok` pasa.
   - Medir Δ`ladder_points` y Δ`neg_points`: es el experimento barato de la escalera de nivel 4.
3. **No comprar raras hoy.** La caja es para CHA y todavía falta la plantilla.
4. Grabar el feed esta noche (precios de épicas, raras de LAT, nuevas cartas cambiadas).

### Domingo
| hora (t) | acción |
|---|---|
| 09:00 (14,08) | `selftest` en verde. Leer `/api/me`: ¿se reinició la escalera (P-18)? ¿`picaros` sigue en `unlocked`? Si LAT-01 #2 no se vendió el sábado, venderla ahora |
| 09:00–11:30 | Feed: ¿alguien compra épicas o raras de LAT? Ajustar el tope con los cierres nuevos. No gastar caja |
| 11:34 (16,65) | **Abrir buy CHA-09 con los Pícaros.** Si no responden con `card:CHA-09` (no venden CHA), pasar directamente al Chato |
| 11:37 (16,7) | +150 de caja. Al cerrar CHA-09, abrir CHA-10 |
| hasta 15:00 | Cerrar CHA (comunes, infrecuentes y la carta de cierre a 72 vía equipos). LAT-09 solo si queda caja |

## 7. Cambios en el arnés (por prioridad, mínimos)
Respetan las reglas: `contracts.py` y `bazaar_sdk.py` no se tocan, toda escritura pasa por la Gate y el texto nunca decide cifras.

1. **`agent/talk.py`: plantilla `picaros_buy`** (3–4 variantes con `{p}`, sin cifras ni términos de FORBIDDEN). Sin ella, cualquier `say` a los Pícaros da G60.template, también en modo manual. Añadir tests en `tests/test_talk.py`, clase `Picaros` (G30.locked, G60, que no existe `picaros_sell`).
2. **`agent/tactics/dealers.py:55`**: `TEMPLATES["picaros"] = "picaros_buy"`. **`config/plan.json` → `profiles`** (solo datos):
   `"CHA-09": {"dealer":"picaros","anchor":45,"step":3,"limit":60,"fallback_after":12,"fallback_dealer":"chato"}`, y lo mismo para `CHA-10`.
   - Sin perfil, la táctica **cierra** un hilo de compra («fail closed: no profile»).
3. **`agent/talk.py:392-397` (G31)**: filtrar las ofertas de `_dealer_standing` con `offer_safety.offer_ok(o, topic, buying=...)` antes de comprobar `final`, `should_accept` y `shape`.
   - Sin el filtro, una oferta con la carta cambiada y `final = true` (caso 7130) bloquea el hilo `[código, inferido]`.
   - La guarda queda más precisa, no más laxa.
   - Test con el caso real.
4. **`agent/tactics/dealers.py:365-372`**: si el último mensaje es del dealer y no hay ninguna oferta legítima en pie, tratarlo como respuesta. Pujar `next_price` si cabe en el límite y apuntar `reason = "bait <msg id>"`.
5. **Tests de `offer_safety` con las formas reales:**
   - types cambiados (G32.shape);
   - cash distinto (G32.price);
   - extras en `want`/`give`;
   - `expires_tick` vencido;
   - venta con otro asset id;
   - en la táctica: ante una oferta cambiada, emitir `say` y nunca `accept`.
6. **`agent/affinity.py:37`**: `DEALERS = {"abuela","chato","pilar","picaros"}`. Hoy 42–43 tratos con Pilar y 3 con los Pícaros cuentan como tratos entre equipos con peso 1,0, y crean filas falsas con `team = 'pilar'` o `'picaros'`. `radio.py` solo necesita añadir `picaros` a su lista de detección de texto.
7. **Detector offline de T1** (script fuera de `agent/`, solo lectura): lista los `message_id` candidatos de nuestros hilos. No envía nada.
8. **Opcional, que no recomiendo hoy**: `Cfg.SOFT_FINAL_DEALERS = {"picaros"}` en `guards.py`. La evidencia es n = 1 y la final de ese caso era de otra carta.
9. **Fuera de alcance sin decisión del lead:** un kind `flag`, porque exige descongelar M0 y cambiar `transport` y sus tests.

## 8. Riesgos y preguntas abiertas
| # | Pregunta o riesgo | Impacto | Experimento más barato |
|---|---|---|---|
| R1 | ¿Venden raras de CHA? (D-12: los dealers acuñan; sin medir en los Pícaros) | Decide todo el plan del domingo | Abrir buy CHA-09 a t = 16,65 y mirar `give.types` de su apertura. Cerrar si no es CHA-09 (memoria 0,3) |
| R2 | ¿`picaros` en `me.unlocked` tras t = 8,67? | Sin eso, G30.locked | Leer `/api/me` (máquina A) a las 17:45 |
| R3 | ¿Se reinicia la escalera por ronda? (P-18) | ¿Hace falta repetir los tratos el domingo? | Leer `/api/me` antes y después del cambio de ronda |
| R4 | Suelo real de una rara por debajo de 54 | Hasta ~6 P por rara | Nuestras propias pujas de +3: registrar dónde acepta |
| R5 | El cierre a ~57 no está garantizado: t01 abandonó LAV-10 dos veces con 55, y MAL-09 a 54 sigue pendiente | Fallback al Chato (unos +30 de caja) | `fallback_after` corto; vigilar el feed |
| R6 | Épicas: n = 0 | Ninguno (no compramos) | Solo observar el feed |
| R7 | Qué entrega aceptar una oferta cambiada | Alto si ocurre | **No probarlo.** Se cubre con `offer_ok` |
| R8 | Si la Gate no tiene el arreglo de G31, cada oferta cambiada (≈36 %) para el hilo hasta `fallback_after` | Tiempo, nunca una compra mala | Aplicar los cambios 3 y 4 con su test |
| R9 | Latencia del runner con ticks de 15 s y expiración en 60 s | Perder ofertas | Ensayo en `sim/` con expires = +4 ticks |
| R10 | Tope de 6 tratos por hora y stock de raras: sin medir | Bajo (necesitamos 2–3 tratos) | Solo observar |
| R11 | Valor de un flag acertado y de uno erróneo: desconocido | Decisión de política | Preguntar a la organización o leer RULES; no enviar ninguno |
| R12 | Detalle de la fiebre de Salamanca | Bajo (sin repetidos de SAL) | `/api/schedule` |

**Fuentes:** scripts en el scratchpad: `picaros_tricks.py`, `weight/dealer_weight.py`, `weight/dealer_metrics.py`, `threads.py`, `analyze.py`, `pic_tricks.py` y `verify_*.py`. No hice escrituras al juego ni toqué el repo.
## 9. Runbook del operador: SAL-11 (Pícaros → Pilar) — sáb 3 oct, 18:00

**Estado:** t18 **compró SAL-11 a los Pícaros por 139** (hilo 1332, tick 925, liquidación 855, asset **992**, serie 2/9). La abrieron con la carta cambiada a 187 (T1) y bajaron por 167, 155 y 145. Con nuestros +3 (130→139), aceptaron 139. Para nosotros vale unos 198, así que la compra da unos +59 y llena un hueco de la escalera de nivel 4.

### Qué cambió en el código (commit «picaros: SAL-11…»)
| fichero | cambio |
|---|---|
| `agent/talk.py` | Nueva plantilla `picaros_buy` (solo compra). G31 ignora las ofertas del dealer que no pasan `offer_safety.offer_ok`: un cebo con otra carta, aunque sea `final`, ni bloquea ni obliga a aceptar |
| `agent/tactics/dealers.py` | `TEMPLATES["picaros"]`. Si la última oferta de los Pícaros es un cebo (no hay oferta válida de la carta), la táctica **sigue subiendo** en vez de quedarse esperando (`BAIT_DEALERS`) |
| `agent/tactics/pages.py` | Clave opcional `dealer_needs`: cartas sueltas fuera de `page_sets` que la táctica `dealers` compra con su perfil. Nunca es una carta de cierre. Tope = min(perfil, `dealer_max`, V − 1) |
| `agent/guards.py` | Clave opcional `protect_except`: refs que G13 no guarda, para poder revender SAL-11 |
| `config/plan.json` | `dealer_needs: ["SAL-11"]`, perfil `SAL-11` (picaros, ancla 130, paso 4, límite 197, `fallback_after` 40), `dealer_max.SAL-11 = 197`, `protect_except: ["SAL-11"]` |

Como ya **tenemos** SAL-11, `dealer_needs` no genera nada: el bot no compra una segunda copia. Queda preparado para la siguiente épica que añadáis (cada ref necesita su perfil propio).

### Pasos (máquina A)
1. `git pull` → `python3 bazaar.py selftest` (verde en analista: core, hygiene, dealers, rastro, closer, duels) → relanzar el mismo `run --live` (cambió el `code_hash`).
2. **Revender a Pilar durante la fiebre de Salamanca** (t = 9,15–11,15, ≈ 18:05–20:05). Es **opcional**. El suelo de la Gate es `ceil(dv_rm + 1)` ≈ **199**: por debajo no deja vender, y entonces nos la quedamos (sigue valiendo unos 198 en el álbum). Un hilo con Pilar cada vez y solo a mano:
   ```
   python3 bazaar.py do open_thread --args '{"dealer": "pilar", "side": "sell", "ref": "SAL-11", "asset_ids": [992], "limit": 199}' --why "SAL-11 a Pilar, fiebre"
   python3 bazaar.py do say --args '{"thread_id": <tid>, "ref": "SAL-11", "price": 240, "template": "pilar_sell", "variant": 0}' --why "ancla"
   # bajar de 5 en 5 con variant 1..3 (240, 235, 230, 225, …); nunca repetir cifra; nunca por debajo de 199
   python3 bazaar.py do accept --args '{"offer_id": <oid>, "source": "dealer", "ref": "SAL-11", "side": "sell", "price": <p>, "thread_id": <tid>, "give_asset": null, "fingerprint": "", "resupply": false, "venue": "pilar"}' --why "SAL-11 vendida a Pilar"
   ```
   - Aceptar su oferta si es ≥ 199 **y** su `want.assets` es exactamente `[992]` (lo comprueba G32).
   - **Riesgo:** Pilar abre bajo (0,64 × libro en D-23) y sube unos +1 por ronda. Con la fiebre (+25 % sobre un libro de 180, unos 225) puede no llegar a 199 a tiempo. Si su `final` queda por debajo de 199, **cerrar el hilo y quedárnosla**.
   - **¿Vender o guardar?** Vender a ≥ 199 da caja y un trato de nivel 3, pero solo +1 sobre su valor. Guardarla no pierde nada. Vended solo si hace falta caja: mañana llegan +150 y las raras de CHA cuestan unos 300.
3. **Más compras a los Pícaros** (LAT-09 ya está en curso a mano): mismo patrón, pasos de +3 y aceptar solo una oferta con la carta exacta. Para que el bot compre otra épica (p. ej. RET-11, que vale unos 234), añadid su perfil propio. Pero RET está en `page_sets`, así que pasa por el bucle de páginas, no por `dealer_needs`: hace falta un perfil `RET-11`. Antes, validadlo en seco con `run` sin `--live`.
4. **Parar:** quitad `SAL-11` de `dealer_needs` y de `protect_except`, o `python3 bazaar.py pause dealers --why "..."`.

**Vigía de solo lectura (analista):** avisa de cada oferta de SAL-11/RET-11 de los Pícaros y de Pilar, de las liquidaciones, de las reventas en El Rastro por debajo del techo y de nuestros hilos con los dos dealers.
