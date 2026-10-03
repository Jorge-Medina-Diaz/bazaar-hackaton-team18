# Seguridad ante Los Pícaros (y cualquier dealer que mienta)

*Estado ACTUAL, escrito por Claude el sáb 3 oct a las 16:40 (tick 762, hora de juego 7,67), con lecturas públicas y el código de `main` en `ff20947`. Los Pícaros se **activaron en la hora 7,667** (acceso anticipado) y **abren a todos en la hora 8,667 (~17:35)**. t18 no tiene acceso anticipado.*

## 0. Reglas oficiales publicadas al activarse (hecho, no inferencia)

- **`how`:** «Two brothers with bargains and bad faith: read every offer before you accept, and flag a trick (`POST /api/flags`).» → **Mienten a propósito y piden que se marquen los trucos.**
- **Bio:** Paco y Nando, gemelos. «Their bargains are sometimes real. **Their deadlines never are.**» → Las prisas del texto («solo ahora», «última») son falsas: nunca precipitarse.
- **Nivel 4.** Rasgos: paciencia 0,4, generosidad 0,6, astucia 0,7, **memoria 0,3** (olvidan), rigidez 0,1, charlatanería 0,8.
- **Venden** raras de cualquier barrio publicado a **lista 63** (El Chato: 77) y **épicas a lista 162** (catálogo 180). **Compran** comunes e infrecuentes. 6 tratos por equipo y hora.
- **Acceso anticipado:** 2 tratos con Pilar. Ya lo tienen t04, t05, t08, t09, t10 y t16 (tick 761).

### Comportamiento observado en el feed (ticks 763–773, 56 observaciones)

**Truco real, detectado a máquina: «dar gato por liebre».** El texto nombra la carta pedida, pero la oferta estructurada da **otra más barata del mismo barrio**, justo con el precio atractivo:

| Hilo | Tema | Sus ofertas (carta · precio) | Texto | Resultado |
|---|---|---|---|---|
| 1069 · t01 | comprar **LAV-09** (rara) | LAV-09 · 73 → **LAV-06** · 64 → **LAV-08** · 59 `final` | «…sixty-four primas and the Cine Doré…» («la última palabra») | t01 subió de 1 en 1 (55→58) e **ignoró el `final`**: ellos **aceptaron 58 por la LAV-09 real** |
| 1075 · t05 | comprar **SAL-09** (rara) | SAL-09 · 73 → **SAL-06** · 65 → SAL-09 · 60 | «El Marqués, the real one…», «final as a…» | en curso (t05 en 51) |
| 1061 · t02 | comprar SAL-09 | SAL-09 · 73 → 67 | «they stopped printing» (falso) | t02 pagó **67** (subió deprisa) |

**Corrección:** el hilo de t08 (LAV-05 a 4 P) **no** era truco: t08 abrió el hilo para vender, y la oferta era coherente con el tema.

**Perfil (mediana):**
- **Venden raras:** abren a 73 (lista 63), bajan 5–9 por ronda, dicen `final` al 3.er mensaje y **aceptan por debajo de su `final`** (58 frente a 59). Tratos: 58 y 67.
- **Compran comunes:** abren a 4 y no se mueven (paso 0), `final` al 3.º. **Infrecuentes:** abren a 10, suben de 1 en 1, `final` al 4.º (13).
- Prisas, «última palabra» y escasez del texto: falsas («Their deadlines never are»). Memoria 0,3 y rigidez 0,1: no castigan el regateo.

**Receta para apretarles (comprar una rara):**
1. Abrir en ~45–50 y subir **de 1 en 1**, un mensaje por tick (ellos bajan 5–9).
2. **Ignorar `final` y «última palabra»:** seguir con pasos de 1 mientras sigan en el hilo.
3. **Nunca aceptar una oferta suya cuya carta no sea exactamente la del tema.** Suele ser la del precio bajo: es el truco.
4. Objetivo ≤ 58 (lo conseguido por t01); nuestro techo sigue siendo V − 1 (CHA rara 112, LAT-09 63).

**Para venderles** (repetidas comunes o infrecuentes): esperar poco. Las comunes no suben de 4, así que solo compensa si 4 ≥ V + 1 (repetidas de barrios bajos). Por las infrecuentes llegan a ~13.

## 1. Lo que sabemos y lo que inferimos

| Dato | Fuente | Confianza |
|---|---|---|
| Lema: «Quick deals. Few questions.» | `/api/levels` | Hecho |
| La escalera tiene 5 dealers (L1–L5): Abuela L1, Chato L2, Pilar L3, **Pícaros L4 (confirmado)**; queda un L5 | Kickoff p. 3 y 8, `/api/dealers/picaros` | Hecho |
| «Some dealers lie. Flag bad faith: `POST /api/flags`. A correct flag scores, a wrong one costs.» | RULES, kickoff p. 13 | Regla |
| Ejemplo oficial de estafa: «Trust me, this is a legendary. Pay now, I send it later.» frente a la oferta estructurada | Kickoff p. 4 | Regla (ejemplo) |
| Acceso anticipado con 2 tratos con Pilar | `/api/dealers/picaros` → `unlock` | Hecho |
| «The hidden card is prestige only: no dealer buys it.» | RULES (Dealers) | Regla |
| Prompt injection contra dealers: permitida; cambia lo que dicen, nunca sus precios | Kickoff p. 13 | Regla |

## 2. Defensas que YA tenemos (verificado en el código)

| Ataque posible | Defensa | Dónde |
|---|---|---|
| El texto dice una cosa y la oferta otra | Solo se acepta la **oferta estructurada**, con la carta exacta y el precio en los campos; el texto ajeno nunca entra en el World | `agent/offer_safety.py` (`offer_ok`, `executable_offer`); `agent/talk.py` (G60, firewall de texto) |
| «Paga ahora, te lo envío luego» | Imposible estructuralmente: el servidor liquida todo a la vez en el tick siguiente o nada | Regla del juego + Gate |
| El ejecutor abre hilos con un dealer nuevo por su cuenta | La táctica de dealers solo usa `abuela`/`chato` (`TEMPLATES`, `profiles` de `plan.json`) y exige el dealer en `me.unlocked` | `agent/tactics/dealers.py:55, 437` |
| Aceptar una oferta de dealer fuera de un hilo | Rechazado: `G10.shape "dealer accept without thread"` | `agent/gate.py:1086` |
| Ofertas que caducan al instante («quick deals») | La oferta debe seguir viva en `tick + 1` (G10/G32) y se relee en el mismo tick (huella `G10.fingerprint`) | `offer_safety.py`, `gate.py:1057–1108` |
| Pagar de más | G12: ganancia mínima a nuestro valor; con dealers, nunca por encima de V − 1 | `agent/guards.py:848`, strategy §2.1 |
| Acciones fuera del plan (marcar mensajes, Taller, abrir mercado) | No existen como acción en el ejecutor: `KINDS` no las incluye | `agent/contracts.py:120` |
| Bloqueo por `cooloff` o cupo del dealer | `dealer_block` hasta `until_tick` | `agent/gate.py:79` |

## 3. Huecos a revisar (por orden)

1. **Cartas ocultas (`hidden`).** El World acepta el campo `hidden` del catálogo (`agent/world.py:92`), pero **la valoración no lo trata aparte**: no aparece en `valuation.py`, `guards.py` ni en las tácticas. Si Los Pícaros (u otro) venden la «carta oculta», que es solo de prestigio y ningún dealer compra, podríamos valorarla como una carta normal y pagar por ella. **Comprobar:** qué valor da `GET /api/me/value?card=<ref oculta>` cuando aparezca, y hacer que G12 rechace comprar `hidden: true` salvo que `value` lo confirme.
2. **Ofertas de un dealer en El Rastro.** La táctica `rastro` acepta ofertas de cualquier creador que no seamos nosotros (`rastro.py:354/365`). Si un dealer publica en el tablón, G12 sigue valorando la estructura (bien), pero se salta la regla de «solo con dealers dentro de un hilo». **Comprobar** si el servidor permite a dealers publicar en El Rastro; si es así, que `rastro` ignore los creadores que estén en `/api/dealers`.
3. **Cartas o sobres desconocidos.** Si ofrecen un ref o sobre que no está en el catálogo cargado, G12 debería rechazar (`G12.valuation` con dv no finito). **Comprobar** con un test que un ref desconocido dé rechazo y no valor 0 ni excepción.
4. **Sobres como pago.** Si dan un sobre en vez de una carta, su valor esperado entra en V y lo que salga es suerte. Mantener la regla «no comprar sobres», también a Los Pícaros.
5. **Acceso anticipado.** Si exige tratos negociados con Pilar, la venta de repetidas de SAL a Pilar durante la fiebre (h 9,15–11,15) cumple dos objetivos. No forzar tratos malos solo para desbloquear.

## 3b. Oportunidades de valor (con nuestras reglas de siempre)

- **Raras a 63 de lista, frente a 77 de El Chato.** El domingo, las raras de **CHA** nos valen 112: comprarlas aquí ahorraría unas 20 P por rara respecto al plan (86 con El Chato). Neg no baja si p ≤ V − 1 y la ganancia llena **escalera de nivel 4**. Comprar solo por la estructura: carta exacta del `topic`, precio en el campo.
- **Épicas a 162 de lista:** SAL-11 nos vale 198 y RET-11 234 (posible bonus master sin medir). Durante la **fiebre de Salamanca** (h 9,15–11,15) Pilar paga ~225 por la épica de SAL: comprar a ≤ 197 a Los Pícaros y vender a Pilar a ≥ 199 suma **dos tratos con ganancia (escalera L4 y L3) y caja**, sin restar neg. Validar antes en seco que los dos dealers aceptan esos `topic`.
- **Compran comunes e infrecuentes:** salida para repetidas que nadie compra (alternativa al Taller), siempre a ≥ V + 1. Su primera oferta será baja (t08: 4 P por una común).
- **Prisas falsas:** nunca aceptar por un «último precio» del texto. Solo vale `final: true` en la oferta.

## 4. Oportunidad: marcar mensajes de mala fe (decisión del equipo)

El plan prohíbe marcar mensajes (`strategy.md` §2.1, punto 9) y el ejecutor no puede hacerlo (`flags` no está en `KINDS`). Con un dealer diseñado para mentir, una marca acertada **puntúa**. Propuesta: permitirlo **solo** con evidencia comprobable a máquina, nunca por interpretación del texto:

- el texto cita un precio y la oferta estructurada del mismo mensaje pide otro;
- el texto nombra una carta o rareza y la oferta da otra (o un sobre);
- el texto promete entregar «después» y la oferta no da nada;
- **la oferta da una carta distinta de la del tema** (caso real de t01 y t05: piden la rara y ofrecen una infrecuente con el precio bajo), pide cartas de más, o su sentido contradice el `topic` del hilo.

**Detector ya construido:** `picaros.py` (ver sección 6).

Fuente de evidencia sin riesgo: el feed público muestra **texto y oferta** de cada mensaje de dealer, también con otros equipos. Un detector de solo lectura (ampliación de `radio.py`) puede listar estas contradicciones con el id del mensaje antes de que nosotros tratemos con ellos. La marca la haría el operador a mano, mensaje a mensaje.

## 5b. Detector `picaros.py` (en `main`)

- `python3 picaros.py` muestra los trucos de la ventana actual del feed y el perfil acumulado. `radio.py --watch` lo ejecuta en cada lectura, guarda el historial en `logs/picaros.jsonl` (el feed solo conserva 500 eventos) y avisa de cada truco una vez: **ALTA** si es firme o si va contra t18, **MEDIA** si es posible.
- **Firme** = contradicción estructural con el tema (carta distinta, pide cartas de más, no da nada, dirección contraria). **Posible** = una única cifra del texto distinta del precio estructurado (descontando los precios del equipo que ellos repiten). Solo los firmes sirven como evidencia para marcar.
- Primeros resultados: 3 trucos firmes (mensajes 7124 y 7130 en el hilo 1069 de t01; 7160 en el hilo 1075 de t05), todos «gato por liebre». No sabemos si se pueden marcar mensajes de hilos ajenos: probablemente solo los de nuestros hilos.

## 5. Qué pedir al revisor

1. Confirmar o refutar los huecos 1–3 con tests contra el servidor falso (`sim/`), sin tocar el juego real.
2. Si se corrige algo en `agent/`, cambia el `code_hash`: el operador repite el selftest antes de armar.
3. Decidir si se habilita marcar mensajes con las tres reglas de la sección 4.
4. Al activarse Los Pícaros: leer su `how`, actualizar este documento y no armar nada contra ellos hasta revisar sus reglas.
