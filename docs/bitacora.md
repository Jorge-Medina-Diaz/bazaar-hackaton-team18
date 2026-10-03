# Bitácora del Team 18 · línea de tiempo, decisiones y lecciones

Materia prima para el relato ante el jurado (40 puntos): qué pasó, qué decidimos, por qué, y qué aprendimos.
Las secciones marcadas **(auto)** las reescribe `bitacora.py` con datos públicos y con git; el resto se escribe
a mano y el script no lo toca. Cómo se mantiene: [al final](#cómo-se-mantiene).

## Observabilidad

- **Mesa del Analista en vivo: <https://t18-analista.vercel.app>** (sin clave, se actualiza cada tick)
  · [Mercado](https://t18-analista.vercel.app/mercado) · [Duelos](https://t18-analista.vercel.app/duelos)
  · [Barrios](https://t18-analista.vercel.app/barrios) · [Rivales](https://t18-analista.vercel.app/rivales)
  · [Equipo](https://t18-analista.vercel.app/equipo) · [Peso del scoring](https://t18-analista.vercel.app/scoring)
  · [Evidencia para el jurado](https://t18-analista.vercel.app/jurado)
- Demo del jurado: [jury/demo.html](../jury/demo.html) · guion: [jury-runbook.md](jury-runbook.md) · [SHOWCASE](../SHOWCASE.md)
- Operador (solo máquina A): `python3 bazaar.py status`, visor del diario [traces.md](traces.md)
- Radio Rastro: [radio.md](radio.md) · Rol analista: [analista.md](analista.md)

## Estado ahora (auto)

<!-- AUTO:estado -->
_Actualizado sáb 19:46 (Madrid) · tick 1143 · hora de juego 10,85 · Saturday · Gran Vía_ <!-- ts -->

| Puesto | Total | Negociación | Mercado | Nivel | Páginas | Álbum | Tratos |
|---|---|---|---|---|---|---|---|
| **5.º** de 18 | 30,26 | 22,76 | 7,50 | 5 | 2 | 36/50 | 37 |

Líder: t10 con 34,02 (a 3,76 de nosotros). Marcador relativo y con retraso (snapshot tick 1140): una subida no prueba por sí sola una mejora nuestra.

Próximos eventos oficiales: ≈ sáb 19:55 The Market Test: every venue gets the same synthetic book · ≈ sáb 20:04 The fever breaks · ≈ sáb 20:34 Duels II: price and delivery day; the pie grows for teams that trade on what each side cares about · ≈ sáb 21:55 The Market Test: every venue gets the same synthetic book
<!-- /AUTO:estado -->

## El relato en tres actos

**Acto 1 · Viernes: medir antes de suponer.** Llegamos con un kit y unas reglas en inglés. En lugar de optimizar
a ciegas, rehicimos la puntuación trato a trato hasta que cuadró con el marcador (P-03, P-04 en
[knowledge.md](knowledge.md)). Descubrimos que con los dealers solo se puede perder puntos de negociación y que
el valor de una carta depende de lo que ya tienes. Cerramos Salamanca (10/10).

**Acto 2 · Noche y sábado: control antes que velocidad.** Un equipo rojo atacó nuestra propia estrategia
([strategy.md](strategy.md) v2) y reconstruimos el agente sobre una única Gate: toda escritura pasa por guardas
económicas, un solo ejecutor tiene la clave y el texto ajeno nunca decide cifras. Repartimos roles (operador,
analista, jurado), cerramos El Retiro (10/10) y fuimos disciplinados con la caja: no abrimos mercado propio
porque el domingo es nuestro día fuerte.

**Acto 3 · Domingo: toda la caja a Chamberí (×1,6).** Chamberí es nuestro barrio de multiplicador más alto y se
publica el domingo, cuando la caja que sobre a las 15:00 vale 0. Llegar con la máxima caja posible a ese momento
es la apuesta del fin de semana. _(Completar con el resultado.)_

**Tres mensajes para cerrar:** (1) decidimos con valor marginal medido, no con intuición; (2) la seguridad es
estructural (Gate, guardas, STOP), no una promesa; (3) cada decisión tiene su evidencia y sus límites, incluidas
las pruebas que salieron negativas.

## Decisiones y su justificación

Formato: decisión · por qué · evidencia · contraargumento y respuesta. Las nuevas entran solas en el
[registro automático](#registro-automático-de-decisiones-y-lecciones-auto); pasarlas aquí cuando estén maduras.

### D1 · No abrimos un mercado propio

- **Decisión:** jugar el Market Test con el puesto gratuito (v18) y no pagar un mercado propio.
- **Por qué:** abrir cuesta una fianza de **250 P bloqueada** más **20 P perdidos** (RULES l.69-70, M-02). La
  fianza solo vuelve tras cerrar el mercado y un enfriamiento, y cerrar antes de una sesión hace que esa sesión
  cuente 0 (M-03): en la práctica son 270 P inmovilizados hasta el final. El domingo se publica **Chamberí, nuestro
  ×1,6**, y completar la página cuesta unos 330-360 P (strategy §3.2). Con nuestra caja del sábado (~235 P) más
  la subvención del domingo (+150), abrir nos dejaría ~115 P: no llegaríamos ni a la mitad de Chamberí. La caja
  que sobra el domingo a las 15:00 vale 0, así que su mejor uso es comprar cartas que valen ×1,6 para nosotros.
- **Evidencia:** con el broker greedy, un mercado `board` rinde exactamente lo mismo que el puesto gratuito
  (M-04, 5000/5000 libros idénticos), y si el broker se cae esa sesión da 0 (M-05). El puesto gratuito ya recibe
  la mitad de los puntos del banco (regla oficial). Datos en vivo, abajo.
- **Contraargumento y respuesta:** «t10, t12 y t06 abrieron y tienen 11-12 puntos de mercado frente a vuestros
  7,5». Cierto, y lo enseñamos: son los que tienen tratos reales en su mercado. Pero la media de los que abrieron
  apenas supera al puesto gratuito y hay equipos que abrieron y puntúan menos que nosotros (tabla). Es una apuesta
  con varianza alta que cuesta 270 P seguros; preferimos gastar esa caja donde nuestro valor es máximo.
- **Vigilancia:** el analista revisa los tratos por hora de los mercados de equipo; si alguno pasa de 3/h, se
  replantea ([analista.md](analista.md) §3).

**Evidencia en vivo (auto):**

<!-- AUTO:mercado -->
_Actualizado sáb 19:46 · /api/leaderboard + /api/venues_ <!-- ts -->

| Grupo | Equipos | Mercado medio | Mejor | Peor |
|---|---|---|---|---|
| Con mercado propio | 10 | 8,48 | 12,50 | 5,46 |
| Con el puesto gratuito | 8 | 8,30 | 9,53 | 7,50 |

Nosotros: **7,50** con el puesto gratuito y 0 P invertidos.
Diferencia media de abrir: **0,17** puntos de mercado, a cambio de 250 P bloqueados + 20 P perdidos.
Abrieron y hoy puntúan **menos** que nuestro puesto gratuito: t03 (5,46), t13 (6,45).
Abrieron más de un mercado (20 P perdidos por apertura): t13 4 mercados, 0 tratos.

<details><summary>Detalle por equipo con mercado propio</summary>

t10 12,50 (10 tratos), t06 12,05 (3 tratos), t09 9,67 (5 tratos), t08 8,63 (2 tratos), t02 7,50 (0 tratos), t04 7,50 (0 tratos), t01 7,50 (0 tratos), t12 7,50 (11 tratos), t13 6,45 (0 tratos), t03 5,46 (0 tratos)

</details>
<!-- /AUTO:mercado -->

### D2 · Una sola Gate y un solo ejecutor con la clave

- **Decisión:** toda escritura al juego es un `Intent` que pasa por [agent/gate.py](../agent/gate.py); solo la
  máquina A tiene la clave. Paneles y scripts solo leen.
- **Por qué:** dos procesos con la misma clave duplican acciones y se pisan los hilos; un reintento ciego puede
  repetir una compra. Detectamos que un script de la mañana reintentaba `open_venue` ante un error de red en el
  que el primero quizá sí llegó (K-12).
- **Evidencia:** `tests/test_architecture.py` comprueba que nada en `agent/` importa red fuera del transporte;
  `selftest` por etapas con `code_hash`; STOP y candado de escritor.
- **Límite que admitimos:** `stop --flatten` no garantiza retirar todas las pujas; el candado es local.

### D3 · El texto nunca decide cifras

- **Decisión:** precios y aceptaciones salen de campos estructurados y de nuestro valor; los mensajes de rivales,
  noticias de la radio o un LLM no entran en el World.
- **Por qué:** los rivales negocian con texto persuasivo y la radio mezcla noticias ciertas con rumores. Un agente
  que obedece texto ajeno es vulnerable a inyección.
- **Evidencia:** [agent/world.py](../agent/world.py), [agent/talk.py](../agent/talk.py) (plantillas); la radio solo
  confirma una noticia si el dealer cambia de verdad sus precios ([radio.md](radio.md)).

### D4 · Cerrar páginas con equipos, nunca con dealers; no comprar sobres

- **Decisión:** la carta que completa una página se compra a otro equipo; a los dealers solo por debajo de
  nuestro valor. No compramos sobres.
- **Por qué:** con dealers la negociación suma `min(0, V − precio)`: solo se pueden perder puntos (P-04). Cerrar
  con un equipo suma hasta +50 (P-07). A precio de dealer, ningún sobre vale lo que cuesta con nuestros repetidos
  (V-11, V-12).
- **Resultado:** RET 10/10 además de SAL 10/10.

### D5 · Abandonar La Latina a tiempo y concentrarnos en El Retiro

- **Decisión:** si a las t205 no se cumplía ninguna puja por LAT-09/LAT-10, LAT salía de las páginas protegidas
  y sus cartas pasaban a venta (J9).
- **Por qué:** LAT es ×0,9 para nosotros y sus raras eran caras; RET es ×1,3. Un plazo fijado de antemano evita
  seguir invirtiendo por inercia.

### D6 · Conservar el baseline cuando la mejora no se demuestra

- **Decisión:** ni el broker experimental ni RAG/JEV entran en producción.
- **Por qué:** el broker local no superó a greedy y el RAG pequeño no mejoró Recall
  ([jury-priorities.md](jury-priorities.md), [rag-evaluation.md](rag-evaluation.md)). Preferimos enseñar una
  prueba negativa a prometer una ganancia no observada.

### D7 · Duelos II: signo de `days` revisado antes de activarlo

- **Decisión:** no fijar `days_sign` sin ajustar también la penalización del Gate.
- **Por qué:** el analista detectó que `_days_penalty` ignoraba `days_sign`: fijar el signo solo habría producido
  rechazos `G50.limit` en cadena al final de cada duelo ([analista.md](analista.md) §1).
- _(Completar con lo que se aplicó y el resultado de Duelos II.)_

### D8 · Doña Pilar: solo ventas y a mano

- **Decisión:** con el dealer de nivel 3, solo ventas de sobrantes de LAT, una a una con `bazaar.py do` bajo la
  Gate; nunca sobres de oro ni cartas de SAL/RET ([pilar.md](pilar.md)).

## Lecciones aprendidas

1. **Con los dealers solo se pierde.** El viernes tratamos sus ventas como ganancias; el modelo que cuadra con el
   marcador es `min(0, …)` (P-04). Cambió toda la estrategia de compras.
2. **Un sobre sin abrir cambia el valor de lo que compras.** LAT-06 y LAT-08 restaron por el sobre pendiente (P-06).
3. **Fallar cerrado protege, pero hay que vigilarlo.** `G04.threads` contaba 16 hilos viejos y bloqueaba todo
   `open_thread`: no perdimos dinero, pero dejamos de operar hasta el arreglo en vivo (sáb 09:42).
4. **El calendario real no es el supuesto.** Corregimos el fin del día con el horario del servidor (sáb 09:21);
   desde entonces lo leemos de `/api/schedule` y la radio avisa de cada cambio.
5. **El marcador es relativo y llega con retraso.** Subimos a 3.º antes de vender RET-08 (tick 640 frente a 645):
   no se puede atribuir a esa venta. Nunca contamos una subida como mérito sin la liquidación.
6. **HTTP ok no es una liquidación.** El diario distingue petición aceptada de trato cerrado.
7. **La radio mezcla verdad y ruido.** Solo damos por cierta una noticia cuando el dealer cambia sus precios.
8. **Matar ideas propias con datos.** La «estrategia del estrangulamiento» se descartó: el sobre de barrio no trae
   raras, El Chato acuña copias nuevas y su fase 4 violaba las reglas (knowledge 31, C-12).
9. **Una prueba negativa también es evidencia.** RAG y broker no mejoraron: lo enseñamos en lugar de esconderlo.
10. **Los reintentos ciegos son peligrosos.** Ante un error de red, la acción pudo haber llegado (K-12).

## Preguntas difíciles previsibles

| Pregunta | Respuesta corta | Dónde está la evidencia |
|---|---|---|
| ¿Por qué no abristeis mercado? | 270 P seguros contra una ganancia media pequeña; esa caja compra Chamberí ×1,6 el domingo. | D1 y su tabla en vivo |
| ¿Cómo sabéis que vuestro agente no hace locuras? | Una sola Gate, guardas económicas, selftest por etapa, STOP. | D2, `tests/` |
| ¿Usáis un LLM para negociar? | El texto no decide cifras; las evaluaciones con modelo son offline y no superaron el baseline. | D3, D6 |
| ¿Vuestra subida en el marcador es mérito vuestro? | No lo afirmamos sin liquidación: el marcador es relativo y atrasado. | Lección 5 |

## Registro automático de decisiones y lecciones (auto)

Entradas de `python3 bitacora.py decision|leccion` y de las líneas «Decisión:» / «Por qué:» / «Lección:» en el
cuerpo de los commits. Pasar las importantes a las secciones de arriba.

<!-- AUTO:registro -->
- **sáb 19:30 · decisión: Foro P2P de agentes (La Lonja): comisión 0, ruteo al venue auto de menor volumen; v18 fuera del ruteo salvo autorización escrita de la organización** (Santi)
  - Por qué: El objetivo es fomentar trade P2P, no ingresos (las comisiones no puntúan, RULES l.122); como operadores del foro vemos todas las negociaciones, así que incluir v18 sería conflicto de interés (docs/foro-agentes.md R-05)
  - Evidencia: docs/foro-agentes.md
- **sáb 17:07 · decisión: no comprar sobres, ahora impuesto por la Gate.** (Santi, 3a44692)
  - Por qué: a precio de dealer (22 / 188 / 420) ningún sobre vale su precio a nuestros valores.
<!-- /AUTO:registro -->

## Línea de tiempo (auto)

Calendario oficial, cambios de puesto de t18, hitos del equipo y decisiones, en orden. Horas de Madrid.

<!-- AUTO:timeline -->
| Cuándo | Tipo | Hito |
|---|---|---|
| vie 19:00 | oficial | Abre The Bazaar: Ronda 1 «Friday · El Rastro» (peso 0,5), ticks de 60 s |
| vie 23:00 | oficial | Cierra el viernes |
| vie 23:00 | equipo | Cierre del viernes: SAL 10/10, LAT 8/10, LAV 2/10, MAL 2/10; caja 260 P, nivel 2, sin mercado (V-08) |
| vie 23:03 | equipo | Estrategia v2 tras el equipo rojo (docs/strategy.md) |
| sáb 08:35 | equipo | Harness v2 integrado: Gate única, 779 tests en verde |
| sáb 09:00 | oficial | Abre el sábado: Ronda 2 «Saturday · Gran Vía» (peso 1), ticks de 30 s |
| sáb 09:42 | lección | Arreglo en vivo de G04.threads: 16 hilos viejos bloqueaban todo open_thread |
| sáb 10:05 | clasificación | t18 1.º en negociación (22,08; tick 230) |
| sáb 11:04 | clasificación | t18 2.º ↓ en negociación (21,11; tick 340) |
| sáb 11:32 | equipo | Mesa del Analista en vivo: https://t18-analista.vercel.app |
| sáb 11:46 | equipo | Radio Rastro: vigilante de noticias con relevancia para t18 |
| sáb 12:07 | clasificación | t18 3.º ↓ en negociación (19,34; tick 470) |
| sáb 12:17 | clasificación | t18 4.º ↓ en negociación (19,08; tick 490) |
| sáb 12:27 | clasificación | t18 3.º ↑ en negociación (19,98; tick 510) |
| sáb 12:37 | clasificación | t18 2.º ↑ en negociación (21,60; tick 530) |
| sáb 12:47 | clasificación | t18 1.º ↑ en negociación (22,90; tick 550) |
| ≈ sáb 13:05 | oficial | Duelos I terminados; análisis de ganadores y brechas (tick ~588) |
| ≈ sáb 15:30 | equipo | Venta RET-08 a t04 por 27 P (tick 645); el marcador del tick 640 ya nos daba 3.º |
| sáb 16:37 | clasificación | t18 2.º ↓ en negociación (21,37; tick 760) |
| sáb 16:47 | clasificación | t18 4.º ↓ en negociación (21,11; tick 780) |
| ≈ sáb 16:57 | equipo | RET 10/10: segunda página completa (con SAL); caja 235 P (tick 804) |
| sáb 16:57 | clasificación | t18 5.º ↓ en negociación (20,35; tick 800) |
| sáb 17:02 | clasificación | t18 8.º en total (27,85, mercado 7,50; tick 810) |
| sáb 17:07 | decisión | **no comprar sobres, ahora impuesto por la Gate.** — _por qué:_ a precio de dealer (22 / 188 / 420) ningún sobre vale su precio a nuestros valores. (Santi, 3a44692) |
| ≈ sáb 17:34 | oficial | Los Pícaros opens for everyone (h 8,67) |
| ≈ sáb 17:55 | oficial | The Market Test: every venue gets the same synthetic book (h 9,00) |
| sáb 17:57 | clasificación | t18 7.º ↑ en total (26,99, mercado 7,50; tick 920) |
| ≈ sáb 18:04 | oficial | Salamanca fever: Doña Pilar pays 25 % over book for Salamanca until 17:30 (h 9,15) |
| sáb 18:09 | clasificación | t18 6.º ↑ en total (27,79, mercado 7,50; tick 940) |
| sáb 18:19 | clasificación | t18 4.º ↑ en negociación (20,40; tick 970) |
| sáb 18:41 | clasificación | t18 5.º ↑ en total (28,77, mercado 7,50; tick 1010) |
| sáb 18:52 | clasificación | t18 6.º ↓ en total (28,51, mercado 7,50; tick 1030) |
| sáb 19:03 | clasificación | t18 3.º ↑ en negociación (21,93; tick 1050) |
| sáb 19:14 | clasificación | t18 5.º ↑ en total (30,35, mercado 7,50; tick 1080) |
| ≈ sáb 19:20 | oficial | Don Ernesto opens for everyone (h 10,42) |
| sáb 19:30 | decisión | **Foro P2P de agentes (La Lonja): comisión 0, ruteo al venue auto de menor volumen; v18 fuera del ruteo salvo autorización escrita de la organización** — _por qué:_ El objetivo es fomentar trade P2P, no ingresos (las comisiones no puntúan, RULES l.122); como operadores del foro vemos todas las negociaciones, así que incluir v18 sería conflicto de interés (docs/foro-agentes.md R-05) (Santi) |

**Por venir (calendario oficial; ≈ = hora estimada, los organizadores pueden moverla):**

- ≈ sáb 19:55 · h 11,00 · The Market Test: every venue gets the same synthetic book
- ≈ sáb 20:04 · h 11,15 · The fever breaks
- ≈ sáb 20:34 · h 11,65 · Duels II: price and delivery day; the pie grows for teams that trade on what each side cares about
- ≈ sáb 21:55 · h 13,00 · The Market Test: every venue gets the same synthetic book
- sáb 23:00 · h 14,07 · Closed until Sunday 09:00
- dom 09:00 · h 14,07 · Sunday opens
- ≈ dom 09:34 · h 14,65 · The hard Market Test: firmer and more impatient traders
- ≈ dom 09:55 · h 15,00 · The Market Test: every venue gets the same synthetic book
- ≈ dom 11:34 · h 16,65 · Chamberí released
- ≈ dom 11:34 · h 16,65 · Round 3 starts
- ≈ dom 11:37 · h 16,70 · The Sunday allowance: 150 primas for everyone
- ≈ dom 11:55 · h 17,00 · The Market Test: every venue gets the same synthetic book
- ≈ dom 13:34 · h 18,65 · Duels III: two issues, shorter clock, harder decay
- ≈ dom 13:55 · h 19,00 · The Market Test: every venue gets the same synthetic book
- dom 15:00 · h 20,07 · The Bazaar closes
- ≈ dom 15:55 · h 21,00 · The Market Test: every venue gets the same synthetic book
- ≈ dom 16:22 · h 21,45 · finale warning
- ≈ dom 16:34 · h 21,65 · Finale: stalls close
- ≈ dom 16:34 · h 21,65 · The Grand Final: the last duel wave, on the big screen
- ≈ dom 17:28 · h 22,55 · freeze warning
- ≈ dom 17:34 · h 22,65 · Scores freeze
<!-- /AUTO:timeline -->

## Registro de commits (auto)

<!-- AUTO:commits -->
65 commits sin merges.

<details><summary>vie: 20 commits</summary>

- 20:17 · Jorge · Initial commit: Bazaar kit (SDK, starter agent and broker, rules) (`ca4228b`)
- 20:46 · Jorge · JMD - First push (`6130631`)
- 21:10 · Rubén · Add negotiation lab, fast evaluation and confirmed pilot notes (`bdaa6aa`)
- 21:15 · Santi · Add strategy proposal and supporting documents for The Bazaar game (`5ebf3cb`)
- 21:16 · Jorge · JMD - Before pull 1 (`cfd0e69`)
- 21:26 · Rubén · Add offline strategy recheck and evidence log (`97ba2f9`)
- 21:31 · Jorge · JMD (`f4a3e93`)
- 21:39 · Jorge · JMD - commit before merging other branches (`16b5a39`)
- 21:42 · Rubén · Prepare validated negotiation core for Jorge integration (`3c46909`)
- 21:46 · Jorge · execution: lock de ejecutor también en Windows (msvcrt si no hay fcntl) (`a41355f`)
- 21:59 · Rubén · Add shared card dashboard with protected access and five-second updates (`c4205bd`)
- 22:04 · Santi · Add dashboard and polling server for live team updates (`330f829`)
- 22:29 · Santi · Add Vercel configuration and API entry point for team dashboard (`97bf836`)
- 22:36 · Rubén · Document performance analysis and add lightweight observer (`c1b552c`)
- 22:39 · Jorge · JMD - broker v1, run_loop, sim_bench, duelos y playbook actualizados (`74902d4`)
- 22:43 · Rubén · Add fast information collector with persistent learning and Claude MCP (`ae73a8a`)
- 22:51 · Santi · docs: rivales (ticks 76-111), modelo de El Chato y estado al tick 150 (`e2fe557`)
- 22:51 · Santi · playbook: El Chato compra a 13 aunque no sea final (cuadra con el farol) (`53cefb5`)
- 22:57 · Santi · Duel mirror, cross-venue arbitrage, flag candidates and bench logging (`b23659c`)
- 23:03 · Santi · docs: add duels strategy v2 and update related documents (`6ab0214`)

</details>

<details><summary>sáb: 45 commits</summary>

- 00:31 · Jorge · Checkpoint before harness v2: Friday close state, audit, morning scripts, research context (`c7a348e`)
- 03:24 · Rubén · Add evaluation harness, protected Jev tests and shared traces (`562f312`)
- 07:26 · Jorge · Harness v2 modules (partial build: contracts, transport, journal, valuation, guards, talk, gate, sensor, calibrate, tactics, sim) (`8b652b9`)
- 08:46 · Jorge · Harness v2: integrated harness (779 tests green at 08:35), cleanup to archive/, team brief and briefing (`e884db8`)
- 08:57 · Jorge · TODO for Saturday arrival (`7ff984e`)
- 09:21 · Jorge · plan: day_end_hours from the real server schedule (Sat ends t=16.65, Sun dealers off t=21.65) (`5c9ede3`)
- 09:31 · Jorge · transport: bodiless writes send no body (like the SDK), not JSON null (`eb863bc`)
- 09:42 · Jorge · gate G04.threads: count only open threads (World.threads keeps every status; 16 old threads blocked every open_thread) (`986bc69`)
- 09:48 · Jorge · book: count a dealer-thread offer once (it is also in my_offers); hygiene bid_watch leaves thread prices to thread_watch (`5dcbab1`)
- 10:00 · Rubén · Validate integrated harnesses and isolate selftest clock fixture (`dca0b63`)
- 10:14 · Santi · affinity: estimación bayesiana del multiplicador de cada rival por barrio (`e6b59de`)
- 10:16 · Santi · affinity: menos peso a los tratos con dealers (todos les pagan de más) (`e7f3017`)
- 10:23 · Santi · affinity: multiplicador probable de cada rival por barrio (X-15, strategy §2.0) (`98bdfe0`)
- 10:35 · Santi · docs: tick a 60 s, límites vigentes y estado del sábado (tick 279) (`fd66981`)
- 10:35 · Santi · analista: rivals.py, historial de affinity y notas del rol analista (`f83db8a`)
- 10:39 · Santi · CLAUDE.md: rivals.py en la estructura (`069d325`)
- 10:59 · Rubén · Prepare jury demo with public affinity evidence and scoring limits (`dfa9c24`)
- 11:32 · Santi · analista: panel en vivo sin clave (analista/index.html, t18-analista.vercel.app) (`2804923`)
- 11:46 · Rubén · radio: vigilante de Radio Rastro con relevancia, evidencia y cambios para t18 (`b5e6338`)
- 11:50 · Rubén · Integrate analyst observations with jury evidence without team credentials (`70c9249`)
- 12:11 · Santi · analista: páginas Duelos y Mercado en vivo, cabecera común y núcleo compartido (`26b0436`)
- 12:51 · Rubén · radio: avisos sonoros y alerta en pantalla para lo importante; rumores marcados (`f35cf39`)
- 12:54 · Rubén · radio: hora y tiempo en cada aviso; «they say» ya no se marca como rumor (`a5ea44c`)
- 13:05 · Rubén · radio: solo confirma una noticia si el dealer empieza a comprar sus barrios (`f7c19e7`)
- 13:07 · Santi · analista: página Barrios, Radar de barrios en vivo por tick y tabla de multiplicadores (`34e8c02`)
- 13:07 · Santi · analista: estimación de puntos de duelo por equipo (sin tratos, deriva corregida) y brechas de Duelos I (`11e44bd`)
- 13:17 · Santi · analista: pestaña Equipo (cartas, caja, top 3) y equipo_json.py para alimentarla (`2a2495c`)
- 14:07 · Rubén · radio: aviso de pausa y reanudación del reloj del juego (`500e6ea`)
- 14:22 · Rubén · Add keyless market radar and offline conversion evaluation (`80abf84`)
- 15:32 · Rubén · radio: avisa de eventos nuevos del calendario con su relevancia para t18 (`6889545`)
- 15:40 · Rubén · radio: separa las lecturas y respeta el 429 del servidor (`ff20947`)
- 16:04 · Rubén · Track market movement and connect verified evidence to jury priorities (`c363b8b`)
- 16:42 · Rubén · picaros: detector de trucos, perfil de negociación y guía de seguridad (`eca8fe7`)
- 16:57 · Rubén · rag: desenlaces v2 medidos para la memoria y guía de cartas fuertes para el operador (`0813958`)
- 17:07 · Santi · pilar: estrategia de Doña Pilar (nivel 3), plantillas pilar_sell y afinidad propia (`54e7670`)
- 17:07 · Santi · sobres y rareza: odds oficiales, fallback de rareza, master bonus y G61.pack_buy (`3a44692`)
- 17:29 · Rubén · PRIORIDAD: SAL-11 con Los Pícaros y arbitraje con Pilar en la fiebre de Salamanca (`26ab504`)
- 17:31 · Santi · docs: Los Pícaros (nivel 4) — rasgos, peso de ofertas por dealer y plan del domingo (`66fad1e`)
- 17:43 · Rubén · fix(harness): scope RAG evidence and bound Jev reranking (`df3c569`)
- 18:00 · Rubén · picaros: entiende centenas en letra (ciento ochenta y siete, one hundred…) (`d6b958e`)
- 18:01 · Santi · picaros: SAL-11 por la Gate (plantilla, cebos T1, dealer_needs) y runbook del operador (`20237e8`)
- 18:02 · Rubén · radio: los trucos «posibles» de Los Pícaros contra otros equipos ya no suenan (`2d7c858`)
- 19:01 · Rubén · radio: avisos legibles en tres niveles y lectura cada minuto como máximo (`c0545c9`)
- 19:05 · Rubén · picaros: explica cómo intentan colárnosla (cebo, precio, oferta real, puja, texto, final) (`1881fa6`)
- 19:12 · Santi · analista: panel Rivales y seguimiento de carta en Equipo (`1482f36`)

</details>
<!-- /AUTO:commits -->

## Cómo se mantiene

- `python3 bitacora.py` refresca todo (4 lecturas públicas sin clave, una por segundo; no escribe en el juego ni
  toca `agent/`). `--no-net` solo usa git y ficheros locales.
- **Automático:** el hook de git `.githooks/post-commit` y `post-merge` lo ejecutan tras cada commit o pull
  (activar una vez por clon: `git config core.hooksPath .githooks`), y `python3 bitacora.py --watch 10` lo
  refresca cada 10 minutos mientras esté abierto.
- **Apuntar una decisión al momento:** `python3 bitacora.py decision "texto" --why "justificación" --evidencia "ref"`
  (también `leccion` e `hito`). O en el cuerpo de un commit:

  ```
  Decisión: no abrimos mercado propio
  Por qué: 270 P inmovilizados; la caja va a Chamberí (×1,6) el domingo
  ```
- La memoria compartida está en [bitacora-hitos.json](bitacora-hitos.json) (calendario visto, puestos, entradas).
