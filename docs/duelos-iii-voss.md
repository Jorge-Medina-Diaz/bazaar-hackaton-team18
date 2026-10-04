# Duelos III con *Never Split the Difference* (Voss)

Dom 4 oct, 11:00 (hora 18,65). 12 ticks, decay 0,10, 4 duelos a la vez, asuntos `price` y `days`.
Fuente: skill `never-split-the-difference` (`.agents/skills/`). Hechos del juego: `docs/knowledge.md` U-01…U-13.

## Lo que cambia respecto al libro

Voss negocia contra personas, con tiempo y sin coste por mensaje. Aquí:

- **Cada intercambio cuesta el 10 % del pastel** (U-01, U-02: ronda = min(nuestros, suyos)). Hablar es caro; **callar es gratis**.
- **Sin trato = 0** y cualquier trato dentro del límite es ≥ 0. «Mejor ningún trato que uno malo» solo vale en el límite, y eso ya lo garantiza la Gate.
- **El texto nunca decide nuestras cifras** (regla del repo). Sí puede mover las del rival, si es un LLM que lee nuestro mensaje.

## 8 ideas aplicables

| # | Voss (cap.) | En Duelos III | Estado |
|---|---|---|---|
| 1 | **Ackerman** (9): 65 → 85 → 95 → 100 % del objetivo, con concesiones decrecientes | Nuestra curva ya lo hace: ancla 0,60 y BETA 1,6 dan concesiones decrecientes. Con decay 0,10, **3–4 ofertas como máximo**; cuatro rondas ya se comen el 34 % del pastel | ya implementado; no tocar |
| 2 | **Número preciso y no redondo** en la oferta final (9) | La oferta final (`final_frac`) debería acabar en una cifra no redonda (p. ej. 137, no 140). Es una señal de límite que un LLM rival suele creerse | mejora pequeña, opcional |
| 3 | **Un término no monetario en la última oferta** (9) y **girar hacia lo no monetario** (6) | **Los días son ese término.** En la oferta final, dar al rival el día que a nosotros nos cuesta poco (\|w\| pequeño) a cambio de precio. Es el logrolling de `analista.md` §5 | depende de `days_sign` (propuesta A) |
| 4 | **Nunca partir la diferencia** (6) | Si el rival propone el punto medio, no saltar ahí. Seguir con el siguiente paso de la curva | ya implementado: la curva no reacciona al punto medio |
| 5 | **Los plazos cortan en los dos sentidos** (6): cuando acaba para uno, acaba para el otro | El rival también se queda en 0. Los bots aceptan tarde: esperar es gratis y la ventana `acc_late` acepta cualquier oferta dentro del límite. **No regalar concesiones antes de tiempo** por miedo al tick 12 | ya implementado |
| 6 | **El silencio y las pausas** (2, 3) | Si el rival está callado, la subida lenta no cuesta rondas (U-02). No escribir solo por romper el silencio | ya implementado |
| 7 | **No usar «justo» a la defensiva** (6: «fair» es la palabra más poderosa y pone al otro a la defensiva) | Las plantillas `duel` y `duel_days` empiezan con «Propuesta **justa**…». Insinúa que el rival es injusto si dice que no. Mejor: «¿Sería una locura cerrar en {p} P?» (pregunta orientada al **no**, cap. 4) | aplicado en `main`; se adopta para la Gran Final |
| 8 | **«¿Cómo se supone que hago eso?»** (pregunta calibrada, 7) ante un ancla agresiva | Contra un rival que abre fuera de nuestro límite: mantener el precio con un «¿cómo…?» en el texto, **sin ceder un paso**. Ya existe «¿Qué puedes hacer tú?» | ya existe parcialmente |

## Leer al rival en el primer tick (cap. 9, tipos de negociador)

| Tipo | Señal en el duelo | Respuesta |
|---|---|---|
| **Analista** | Callado, mueve poco, cifras precisas | Su silencio es que está pensando, no un no. Subida lenta (gratis), paciencia, nada de prisas |
| **Complaciente** | Mensajes largos y amables, concede pronto | Si su oferta ya está dentro del límite, cerrar ya: cada mensaje más cuesta un 10 % |
| **Asertivo** | Ancla extrema y rápida, se repite | Mantener el paso, pregunta calibrada, oferta final con cifra precisa cerca del deadline |

**Las dos patas son contra el mismo equipo** (U-05): lo aprendido de su tipo en la primera pata vale para la segunda (el «cisne negro» del cap. 10).

## Recomendación para las 11:00

1. **La lógica no se toca.** Las ideas 1, 4, 5 y 6 ya están en `agent/tactics/duels.py`.
2. **Idea 7 aplicada en `main`**: las plantillas `duel` y `duel_days` de `agent/talk.py` ya no dicen «justa». Ahora usan, en orden de mensaje: auditoría de acusaciones con pregunta orientada al no, luego etiqueta con pregunta calibrada, luego «¿Cómo se supone que hago más?» y por último «me queda muy poco margen» con pregunta orientada al no. Solo cambia el texto: las cifras, la Gate y el firewall G60 no cambian. El `selftest` completo tarda unos 4,5 minutos en esta máquina, así que **no da tiempo antes de Duelos III**: se adopta en la pausa antes de la Gran Final (14:00).
3. **`days_sign` sigue en `null`.** Fijarlo sin cambiar `_days_penalty` en la Gate provoca rechazos `G50.limit` en cadena (bitácora D7). El logrolling con días (idea 3) queda para después de Duelos III.

## Instrucciones para el operador (máquina A)

**Duelos III (11:00): Plan B, sin cambios (riesgo cero).** No parar el runner. Con `duels` armado ya aplica las ideas 1, 4, 5 y 6.

**Gran Final (14:00): Plan A, plantillas Voss.** Hacerlo entre el final de Duelos III y las 13:45, sin ningún duelo vivo:

1. `python3 bazaar.py stop "plantillas Voss para Duelos III"` y esperar a que el runner salga (`python3 bazaar.py status`: sin candado).
2. `git pull origin main`
3. `python3 bazaar.py selftest`, **con el runner parado**: si `logs/run` o `state/` cambian durante el selftest, todas las etapas salen en rojo. Hace falta `core` y `duels` en verde.
4. `python3 bazaar.py resume --why "plantillas Voss"` (borra STOP).
5. Relanzar **el mismo** run de antes, por ejemplo `python3 bazaar.py run --live --arm hygiene,dealers,rastro,closer,duels`, con solo las tácticas que estaban armadas y en verde.
6. Si algo sale rojo o falla: `git checkout c825858 -- agent/talk.py`, volver a pasar el selftest y relanzar. No improvisar.

Durante el duelo, en cualquiera de los dos planes:
- **No aceptar a mano el punto medio** ni subir la oferta para «desbloquear». Callar no cuesta rondas.
- **No pausar `duels` porque un rival esté callado**: la subida lenta es gratis y la ventana final acepta cualquier oferta dentro del límite.
- Pausar `duels` solo con rechazos de la Gate en cadena (`G50`/`G51`) o con E16.
- Apuntar el tipo de cada rival (analista / complaciente / asertivo): la segunda pata es contra el mismo equipo.
