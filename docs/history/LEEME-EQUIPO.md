# LÉEME — Team 18 (t18), sábado 3 oct 2026

> **Histórico: guía del sábado a las 08:35.** Las reglas de puntuación (§1) y el arnés (§5) siguen valiendo. La situación, el calendario y las decisiones del sábado están superados. **Domingo: [plan-domingo.md](plan-domingo.md).** Hechos al día: [knowledge.md](../knowledge.md) S-17..S-33. Este documento solo se ha corregido donde contradecía los datos.

Para quien estaba dormido: diez minutos. Si algo choca con `docs/knowledge.md` (ids P-, V-, D-, R-, X-, U-, M-, C-, K-), manda `knowledge.md`. Plan completo: `docs/strategy.md`. Arnés: `docs/harness-spec.md`.

---

## 1. El juego en 1 minuto y cómo se puntúa de verdad

Coleccionamos cromos de Madrid (página = 5 comunes + 3 infrecuentes + 2 raras de un barrio). Compramos y vendemos a dos dealers (Abuela, El Chato), a 17 equipos en El Rastro, y jugamos duelos. Cada carta tiene un **valor privado** nuestro; la 2.ª copia vale el 25 % y la 3.ª el 10 % (V-01). Una página completa suma un bonus del 25 % de sus cartas.

**Reparto:** Negociar 30 · Market Test 30 · Jueces 40. Rondas: viernes 0,5, sábado 1, domingo 1 = **20 / 40 / 40 %** (P-16).

| Pieza | Cómo puntúa (medido) |
|---|---|
| neg con equipos | Comprar: V − precio − comisión si aceptamos. Vender: precio − comisión − V. V = cambio del valor total de la colección (P-03) |
| neg con dealers | **Solo baja:** min(0, V − p) al comprar, min(0, p − V) al vender. La ganancia suma 0 (P-04) |
| Escalera | 3 mejores tratos con dealer por nivel; solo cuentan los que son **ganancia** (P-10). Pesa mucho: hasta el tick 40 era toda la nota, y un hueco de nivel 1 (≈ 0,022) valía 5,25–5,91 de 30 (P-12, P-13). Los 3 huecos del nivel 2 están vacíos |
| Duelos | \|precio − límite\| × (1 − decay)^rondas; rondas = min(mensajes nuestros, del rival). Callar no cuesta (U-01, U-02). Fuera del límite resta. Con días: S-26; la parte de duelos es una media por duelo (S-27) |
| Market Test | Cuenta el mejor venue abierto en cada sesión (ninguno = 0). Igualar al puesto gratuito = mitad de los puntos del banco; completos = media del top 3 (P-19). El sábado hubo 6 sesiones; por ronda, mercado = 22,5 × bench + 7,5 × orgánico (S-23) |
| Jueces | Ideas y oficio: diario con cadena de hash, `report`, `replay-friday`, SHOWCASE |

**Nunca cuenta:** número de tratos, comisiones cobradas, lo que sale de un sobre, regalos, easter eggs, concesiones (P-02). La caja que quede el domingo a las 15:00 vale 0.

**Cinco reglas que cambian decisiones:**
1. **Regla del dealer:** con un dealer solo se pierde neg. Se le compra solo por debajo de nuestro valor, para llenar escalera.
2. **Sobre sin abrir:** cuenta a su valor esperado, y cada carta que compramos y que ese sobre podría traer baja ese valor. LAT-06, pagada por debajo de su valor (22 frente a 22,5), restó −1,855 (P-06). **Abrir cada sobre al llegar, antes de comprar.** Abrir no mueve neg (P-08).
3. **Comisión de El Rastro:** ceil(0,05 × precio + 1 por carta), la paga **quien acepta** (R-01). Publicar sale gratis.
4. **Posible tope de +50:** SAL-10 (V 149,875, precio 80) contó +50,0 y no +69,9 (P-07). Causa desconocida; se juega como si hubiera tope.
5. **El bonus de página solo llega a neg si la carta que la cierra se compra a un equipo** (a un dealer da 0).

---

## 2. Nuestra situación

- **Caja 260**, nivel 2, sin venue propio; **410** tras la subvención de la hora 4,05 (V-08, M-12). *(Corrección: desde el tick 201 tenemos el puesto gratuito v18, automático y a comisión 0 desde t 432, que cuenta en el Market Test con la mitad del banco, S-24. Cierre del sábado: S-30.)*
- **Álbum:** SAL 10/10, LAT 8/10 (faltan las raras LAT-09 y LAT-10), LAV 2/10, MAL 2/10.
- **Multiplicadores:** CHA 1,6 · RET 1,3 · SAL 1,1 · LAT 0,9 · LAV 0,7 · MAL 0,5. RET sale hoy, CHA mañana: nuestros dos mejores sets. Una copia más de RET vale 13 / 32,5 / 91; la carta que cierra RET vale 99,1 y la de CHA 122 (V-05, V-06).
- **neg 74,5, escalera 0,051, 17 tratos, puesto 7.º** (19,19) en el snapshot del cierre; líder t13 con 30,00.
- Pujas heredadas 2503/2504 (LAT-09/10 a 62) hasta el tick 205. Las cuatro ventas de LAT que exponían la página las canceló el jefe a la 01:30.

**Lo que enseñó el viernes:** las ganancias con dealers no suman y las pérdidas sí; el mercado es pequeño (46 tratos entre equipos, pujas cumplidas 9 %, raras 4 %, R-02, R-05); el reloj se paró en la hora 2,65 y estuvo en pausa (C-01, C-03); y nuestro código nos hizo daño: `sell_dups` puso a la venta todas las copias de LAT-05 (K-01), `haggle()` no comparaba con nuestro valor (K-03) y un segundo escritor vendió por debajo del límite (K-05).

**Los cinco tratos con pérdida (todos con dealers, −27,6, P-05):** LAT-01 a 10 (−1,0, pagado por encima del valor); sobre a 23 (−8,488, vale ~18 y su contenido sigue sin vender); LAT-06 a 22 (−1,855, efecto del sobre sin abrir); LAT-08 a 32 (−11,813, valor 22,5: `haggle()` sin comprobación más el sobre); venta de LAV-06 a 13 (−4,5, segundo escritor).

---

## 3. Teoría de juegos

17 equipos que aprenden, dos dealers de reglas fijas, el calendario de los organizadores y los jueces. La nota es **relativa** (P-13, P-14): lo que hacen los demás mueve la nuestra.

| Contraparte | Incentivo | Aprovechable | Trampa |
|---|---|---|---|
| Abuela | Vender caro con suelo oculto | No cede si no subimos; luego ~1 P por ronda. Finales: sobre 19–24, infrecuente 21–25. Si se va, se reabre en el mismo tick (D-03..D-07) | Contraofertar bajo su final; repetir precio; creer su texto (solo vale `final`) |
| El Chato | Igual | Nunca cede más que nuestro paso: +4 constante (t07 sacó 82 en una rara, D-10) | Raras a 90–93: por encima de 91 resta |
| Equipos vendedores | Precio alto | Casi nada: ninguna venta del viernes era rentable sola (R-06) | Listados fantasma (X-13), seudónimos; las palabras no obligan, solo la estructura |
| Equipos que cierran página | Pagan 70–110 (59 pujas ≥ 35 el viernes) | Venderles un duplicado de RET/CHA y recomprarlo a la Abuela (J13) | Vender duplicados baratos les cierra la página |
| Dueños de venue (t13 v03, t12 v02, t06 v01, t02 v04) | Ganan puntos de mercado con lo que otros crean en su venue (RULES l.119). t13 lo promocionó en un chat de grupo por eso | Comisión baja | Cada trato nuestro allí sube la nota de un rival |
| Rivales de duelo | Su límite oculto | Callar no cuesta; las dos patas son contra el mismo equipo (U-05); muchos no tienen bot (68 sin acuerdo de 128) | La aceptación toma la oferta en pie en ese instante (U-10) |
| Organizadores | Que el juego fluya | Niveles y concesiones, anunciados en el feed | Pausa, calendario y límites cambian en caliente |

**Por qué observar, predecir, medir y adaptar:** varias reglas solo se conocen midiendo (el +50, el peso del nivel 2, si los rivales ceden callando, si la ronda reinicia neg); los rivales reaccionan (las pujas de cierre llegaron a 70–110 en una tarde); el calendario puede moverse 1 h 21 min. Por eso toda escritura lleva una predicción, el calibrador la compara con lo medido y pausa la táctica que falla, los temporizadores salen de eventos y no de la hora de pared, y cada duda tiene un experimento de coste 0 (E1–E17). Ningún LLM decide cifras.

---

## 4. La estrategia del sábado y el domingo

| # | Jugada | Efecto | Parada |
|---|---|---|---|
| J1 | Abrir cada sobre al llegar, tras cerrar los hilos de compra | Evita −2 por compra | Nunca |
| J2 | Medir cada tick: puntos, ronda, reloj | E1, E2, E4, E6 | — |
| J3 | **RET a 9/10 con dealers bajo valor.** Raras a El Chato desde 70, +4, límite 90; RET-08 a El Chato (13, +1, límite 31; a los 10 ticks, Abuela); Abuela: infrecuentes ≤ 25, comunes ≤ 11 | neg 0 + hasta 3 huecos de nivel 2; ~290 P | La carta de cierre se congela en 8/10 y nunca va a un dealer |
| J4 | **Cierre de RET con un equipo:** aceptar venta con ganancia ≥ 20; si no, pujar ya **49**; con un rival que puja igual o más, o en el final del domingo, **79**. Nunca bajar | **+50** (≈ 4,7 puntos de ronda, inferido) | Cumplida |
| J13 | Duplicado de RET/CHA a una puja rival con ganancia ≥ 15 y recompra a la Abuela | +19 a +32 por ciclo | 2 recompras fallidas |
| J5 | Sobrantes **publicando**; RET/CHA nunca bajo 30 | +2 a +7 por venta | — |
| J6 | Comprar a equipos con ganancia ≥ 3, solo cartas del plan | +3 a +10 | — |
| J7 | Duelos dentro del límite, ascenso lento, aceptar solo si el rival ya habló en el tick | 0 fuera de límite | — |
| J8 | Market Test con el puesto gratuito | Mitad del banco sin riesgo | — |
| J9 | LAT: si se cumple 2503 o 2504, la otra rara a El Chato ≤ 100; si no, LAT muerta en el tick 205 y se vende | +1 a +51, o caja | Tick 205 |
| J10 | Duels II: nada con precio hasta leer `days_meaning` | — | Resultado ≤ 0 |
| J12 | **Domingo, CHA:** J3 + J4; cierre a 72, subida a 102 | +50 | Los puestos cierran ~14:00 si el calendario se re-ancla (plan-domingo §3) |

**Nunca:** comprar sobres; pagar a un dealer más que nuestro valor; cerrar página con un dealer; publicar la última copia libre de una página protegida; aceptar con ganancia < 3; bajar una puja de cierre; prompt injection; scripts antiguos. Las denuncias (flags) solo a mano y con el OK de Jorge: el sábado puntuaron las 3 primeras de nivel A (S-28).

**Primeras dos horas:** 08:50 `clockcheck`; 08:55 `run --live --arm hygiene`; 09:00:30 y 09:05 `clockcheck` para la lectura del reloj (E1).
- **N** (ronda 2 y RET 09:00, subvención 09:03, banco 10:00, Duels I 11:30): sobre abierto al tick siguiente; 09:06 caducan las ventas de LAV/MAL (J5 republica a 9); 09:22 tick 205 decide LAT; `arm dealers` y `arm rastro`; antes de las 11:00, `arm duels`.
- **C** (todo +1 h 21 min: ronda 1 hasta 10:21, RET 10:21, subvención 10:24, Duels I 12:51): nada de compras con ganancia antes de 10:21 (contaría en la ronda de peso 0,5); hilos de compra cerrados 3 ticks antes de la subvención.
- **M** (mezcla) y **P** (puertas abiertas en pausa: solo cancelar y cerrar hilos): `strategy.md` §4.

---

## 5. El arnés en una página

**Qué lo hace seguro:** un único punto de escritura, el **Gate**. Nada que no sea GET sale sin un permiso de un uso atado a método, ruta y hash del cuerpo (más audit hook y test AST). Respuesta dudosa = **fallo cerrado**: se congela ese dominio y nunca se reenvía. Selftest de las 08:30 en verde en todas las etapas (núcleo 394 tests, higiene 27, dealers 155, rastro 42, cierre 63, duelos 122); repetirlo antes de arrancar.

**Invariantes:** 01 solo el Gate escribe, nunca a admin/venues/flags/broker (las excepciones manuales con el OK de Jorge están en CLAUDE.md) · 02 sin `--live`, táctica armada o con STOP no se escribe · 03 por tick: 1 aceptación, 1 mensaje por hilo, ≤ 6 publicaciones, ≤ 2,5 req/s · 04 ningún trato con pérdida predicha (equipos ≥ 3, cierre ≥ 20, J13 ≥ 15, dealers ≥ 1) · 05 solo ofertas de forma exacta releídas en el tick · 06 nunca se entrega una copia protegida · 07 caja libre ≥ 0 contando pujas e hilos · 08 un camino de compra por carta · 09 sobres: no se compran, se abren al llegar · 10 cierre nunca a un dealer · 11 con dealers, precio al alza y límite que solo baja · 12 duelos: dentro del límite, aceptar solo la oferta del rival de este tick · 13 texto de plantillas; el texto ajeno no decide · 14 un envío por intent · 15 diario WAL con hash · 16 escritura t18 sin explicar → STOP · 17 toda escritura con predicción; fuera de banda → pausa · 18 claves fuera de logs y panel · 19 un fallo de táctica solo la salta · 20 juego limpio · 21 tests solo en 127.0.0.1 · 22 un solo escritor (`state/writer.lock`) · 23 nada de pujas de cierre ni hilos de compra con riesgo de entrega.

**Comandos (solo en la máquina A):**
```
python3 bazaar.py selftest                          # etapas verde/rojo
python3 bazaar.py clockcheck                        # N/M/C/P, ronda, t_hours (sin clave)
python3 bazaar.py run --live --arm hygiene          # sin --live = simulacro
python3 bazaar.py arm dealers --why "RET publicado" # con el runner vivo; rechaza etapas en rojo
python3 bazaar.py pause rastro --why "..."
python3 bazaar.py do list_offer --args '{...}' --why "J5"   # a mano por el Gate (sin runner vivo: añadir --live)
python3 bazaar.py status                            # 0 llamadas: armadas, pausas, STOP, unknowns, cash_free
python3 bazaar.py stop "motivo" [--flatten]         # kill; --flatten retira antes pujas e hilos
python3 bazaar.py resume --why "..."
```
Tácticas: `hygiene`, `dealers`, `rastro`, `closer`, `duels`. **Parar:** `bazaar.py stop` o crear `STOP` (o `STOP.txt`) en la raíz del repo. **Código nuevo:** `stop "hot update"` → `status` sin pendientes → `git pull` → `selftest` → relanzar `run`.

**Cada hora:** `status` (alarmas, pausas, unknowns, `cash_free`); en el panel, Δneg = 0 ± 0,1 en cada trato con dealer, ningún 429, solo las ofertas esperadas.

**Si se para solo** (salida 2): no relanzar a ciegas. `status` da el motivo. `foreign_writer` = alguien más escribe con la clave: pararlo primero. `unknown` = mirar en el panel si el envío llegó. Con la causa clara, `resume --why` y el mismo `run` (concilia antes de escribir). Salida 3 = ya hay otro runner. Táctica pausada sola: leer sus filas `measure` y `pause` antes de rearmar.

---

## 6. Qué cambiamos y qué no tras la información tardía

| Entrada | Decisión | Evidencia |
|---|---|---|
| t13: pujas largas por cartas que faltan | **Adoptado con cambio (D3):** caducidad en unidades de 15 s (×2 el sábado, ×1 el domingo); solo para cartas de equipo que no son la de cierre | Encaja con R-07 (a 60 s duró lo pedido entre 4). No sube la expectativa: 9 % de pujas cumplidas, 4 % en raras (R-05). No reservan caja (R-10): el Gate las descuenta |
| t13: swaps | **Adoptado con cambio (D1):** V(recibida) − V(entregada) − comisión con el mínimo de una compra; nunca una copia protegida; como autor solo damos un sobrante (MAL, LAV, duplicados) | Sin ninguna medida de swaps del viernes: se tratan como una compra más. Falta la forma inversa |
| t13: mirar todos los venues | **Adoptado:** se leen todos los tableros y las ofertas dirigidas; publicamos solo en El Rastro | Solo GET. El viernes, 0 tratos en venues de equipo porque no podían operar (M-10); E15 mide el flujo |
| t13: operar en v03 | **No, mientras t13 esté en el top 5 (D2):** en un venue rival solo con ganancia ≥ 10 y dueño fuera del top 5 | t13 es 1.º y gana puntos con nuestros tratos; el consejo viene del beneficiario. Ahorro pequeño: en 60 P, 1 P de comisión en v03 frente a 4 en El Rastro. Hoy solo pasan v01 (t06, 11.º) y v04 (t02, 17.º) |
| Jefe: robustez | **Ya cubierto** | Gate, 23 invariantes, fallo cerrado, selftest en verde |
| Jefe: teoría de juegos y adaptación | **Cubierto; se añade D2** | Calibrador, J4 sube ante competencia, J13 responde a pujas rivales. No se modelan multiplicadores rivales de RET/CHA: no se pueden saber (X-14) |
| Venue propio (D4) | **No en esta versión** | §7.1 |

---

## 7. Decisiones abiertas

1. **Venue propio o puesto gratuito → puesto.** Un `board` con greedy rinde igual que el puesto (5000/5000 libros, M-04), cuesta 20 P, bloquea 250 P que necesitan las páginas, y si el broker se cae esa sesión da 0 (M-05). *Cambia si* un broker supera a greedy en el libro grabado del primer Market Test real: grabar con solo GET el libro del banco con sus caducidades, repetirlo sin conexión con greedy y con el candidato, y comparar la fracción de ganancia realizada en ese libro y en el siguiente (los +4 a +11 pp de los modelos no están validados, M-08); además caja libre ≥ 270 y un supervisor contra caídas. Hoy la grabadora L1 está inerte (no hay lector con la clave del broker).
2. **Venues rivales → regla D2.** Leaderboard desconocido = no. *Cambia si* E15 mide flujo real y el dueño sale del top 5.
3. **LAT → mantener 2503/2504 hasta el tick 205; después vender** a ≥ V + 2 o a pujas con ganancia ≥ 3 (t14 necesita LAT-03 y LAT-08). *Cambia si* aparece LAT-09/10 con ganancia ≥ 20 en algún tablero, o se cumple una puja (la otra rara a El Chato ≤ 100).
4. **Puja de cierre → 49 (RET) / 72 (CHA) ya; 79 / 102 con competencia o en el final; nunca bajar.** Con tope, todo ≤ 49 da +50; sin tope, 49 da +50,1. *Cambia si* E5 prueba que no hay tope y nadie compite; aun así, bajar reduce el 9 % de cumplimiento.
5. **Duelos (E8) → v0 corregido + ascenso lento.** En el primer rival de Duels I que hable, callar 2 ticks. *Si cede callando*, "ancla y espera" (+16–18 P por duelo); si solo responde, v0 (ancla perdería 0,5–4,3, U-09).
6. **Cuándo armar:** `hygiene` 08:55; `dealers` y `rastro` con RET publicado y el sobre abierto; `duels` antes de Duels I; `closer` con RET en 9/10. Domingo: "CHA" en `page_sets` de `config/plan.json` y todas las que estén en verde a las 08:55.
7. **Días en Duels II:** una persona fija `days_sign` en `config/plan.json`; mientras no, se exige excedente para el peor caso. *(Superado: desde `5ee5593` el sensor deriva `days_sign` de `days_meaning`, con comprador −1 y vendedor +1. El margen de peor caso fue lo que hundió Duels II, S-26 y S-27.)*
8. **Venue `auto` (J11) → no**, salvo ≥ 3 tratos/h en venues de equipo durante 2 h (E15) y caja libre − plan de páginas ≥ 270. Hoy no hay acción para abrirlo.
9. **J13 alimenta al top 3 → hacerlo** con ganancia ≥ 15, mientras la media de neg del top 3 supere ~65 (P-15, inferido).
10. **Abierto en el arnés:** 2 mensajes del rival en un tick o POST tras el cambio de tick (E16; si falla, se pausan las aceptaciones de duelo); hilos que nos abren contra nuestros 6 (E17); regalos de la Abuela en la ronda 2 (riesgo de entrega); si la aceptación de duelo gasta la del tick (E9; se supone que sí).

---

## 8. Quién hace qué mañana

| Papel | Quién | Qué hace |
|---|---|---|
| Operador | (nombre) | Única máquina con la clave (A). Lanza todos los comandos y pasa `status` cada hora al chat |
| Vigía del panel | (nombre) | **Un solo** visor del panel (≤ 1 req/s entre todos); nada de `live_monitor.py` ni `panel.py`. Avisa si ve una oferta inesperada |
| Duelos | (nombre) | Lee los días de Duels II y propone `days_sign`; anota E8 |
| Jueces | (nombre) | `report`, `replay-friday`, tabla predicho/medido; SHOWCASE el domingo |

Cualquiera puede pedir un `stop`. Nadie más escribe con la clave, ni a mano ni con scripts antiguos.

**Glosario.** **V / dv_add / dv_rm:** cambio del valor total al añadir / quitar una carta. **neg_lo:** ganancia predicha en el peor caso, con tope 50. **Carta de cierre:** la que completa la página; congelada desde 8/10. **Riesgo de entrega:** la carta podría llegar por otra vía (sobre, subvención, dealer). **Gate:** único punto de escritura (guardas G01–G60). **Intent:** acción propuesta. **Armar:** pasar una táctica de sombra a escritura real. **cash_free:** caja − pujas − aceptaciones sin liquidar − límites de hilos − 10. **N/M/C/P:** a su hora / mezcla / +1 h 21 min / en pausa. **Puesto:** venue automático gratuito. **Board / auto:** venue con broker propio / que cruza solo. **Seudónimo:** alias con que el tablón muestra a cada equipo. **Tick:** 30 s el sábado, 15 s el domingo.
