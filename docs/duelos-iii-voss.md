# Duelos III y Gran Final con *Never Split the Difference* (Voss)

Dom 4 oct. Duelos III a las 11:00 (hora 18,65) y Gran Final a las 14:00: 12 ticks, decay 0,10, 4 duelos a la vez.
Asuntos: `price` y, según `analista.md`, `days`. **Comprobarlo en el primer duelo** (`issues`, `days_meaning`); U-12 solo lo confirma para Duelos II.
Fuente: skill `never-split-the-difference` (`.claude/skills/`). Hechos del juego: `docs/knowledge.md` U-01…U-13.
Revisado por tres revisores independientes (seguridad, afirmaciones y operación) antes de publicarlo.

## Lo que cambia respecto al libro

Voss negocia contra personas, con tiempo y sin coste por mensaje. Aquí:

- **Cada intercambio cuesta el 10 % del pastel** (U-01, U-02: ronda = min(nuestros, suyos)). Cuatro rondas se comen el 34 %. Hablar es caro; **callar es gratis**.
- **Sin trato = 0** y cualquier trato dentro del límite es ≥ 0. «Mejor ningún trato que uno malo» solo vale en el límite, y eso ya lo garantiza la Gate.
- **El texto nunca decide nuestras cifras** (regla del repo). Sí puede mover las del rival, si es un LLM que lee nuestro mensaje.

## 8 ideas aplicables

| # | Voss (cap.) | En los duelos | Estado |
|---|---|---|---|
| 1 | **Ackerman** (9): 65 → 85 → 95 → 100 % del objetivo, en concesiones decrecientes | La curva (`curve`, exponente 1/BETA = 0,625) da concesiones decrecientes desde un ancla de 0,60 del límite. **No** hay tope de 3–4 ofertas: concede un paso por cada respuesta del rival. Ackerman pide 4 ofertas; con decay 0,10, más rondas salen caras | parcial: concesiones decrecientes sí, tope de ofertas no |
| 2 | **Número preciso y no redondo** en la oferta final (9) | La oferta final (`final_frac`) debería acabar en una cifra no redonda (137, no 140). Un LLM rival suele leerla como límite | no implementado; mejora pequeña |
| 3 | **Girar hacia lo no monetario** (6) | **Los días son el término no monetario**: dar al rival los días que a nosotros nos cuestan poco a cambio de precio (logrolling, `analista.md` §5). En Ackerman (9) el extra final es algo que el rival «probablemente no quiere», solo como señal de límite | no implementado: depende de `days_sign` y de la Gate (D7) |
| 4 | **Nunca partir la diferencia** (6) | La curva depende del número de respuestas del rival, no de su precio: no salta al punto medio | ya implementado |
| 5 | **Los plazos cortan en los dos sentidos** (6) | El rival también se queda en 0. En la ventana `acc_late` (3 últimos ticks) aceptamos una oferta dentro del límite **si el rival habló en ese tick**; si no, lo provocamos con un mensaje. Hay una oferta final (`final_frac` 0,6) en deadline − 4. No regalar pasos por miedo al tick 12 | ya implementado |
| 6 | **El silencio y las pausas** (2, 3) | Con el rival callado, la subida lenta no cuesta rondas (U-02) | ya implementado |
| 7 | **No usar «justo» a la defensiva** (6) | Las plantillas antiguas abrían con «Propuesta **justa**…», que insinúa que el rival es injusto si dice que no. Las nuevas abren con una auditoría de acusaciones y una pregunta orientada al **no** (4): «Sé que vas a pensar que abro fuerte. ¿Sería una locura cerrar en {p} P?» | en `main`, para la Gran Final |
| 8 | **«¿Cómo se supone que hago eso?»** (pregunta calibrada, 7) | El tercer mensaje es «Yo ya me he movido. ¿Cómo se supone que hago más?» (sustituye a «¿Qué puedes hacer tú?») | en `main`, para la Gran Final |

**Plantillas nuevas** (`agent/talk.py`; la variante es el nº de mensaje módulo 4, así que el ciclo se repite en duelos largos):
1. «Sé que vas a pensar que abro fuerte. ¿Sería una locura cerrar en {p} P?»: auditoría de acusaciones + pregunta orientada al no.
2. «Parece que aún estamos lejos. ¿Cómo podemos acercarnos? Me muevo a {p} P.»: etiqueta + pregunta calibrada.
3. «Yo ya me he movido. ¿Cómo se supone que hago más? Propongo {p} P.»: la pregunta calibrada de Voss.
4. «Esto ya me cuesta: {p} P. ¿Te parece mal cerrar así?»: pregunta orientada al no.

`duel_days` usa los mismos cuatro textos con «y {d} días» (antes tenía 3 variantes). Solo cambia el texto: las cifras, la Gate y el firewall G60 no cambian. `selftest` en verde en todas las etapas (core 405, duels 133).

## Leer al rival en el primer tick (cap. 9, tipos de negociador)

| Tipo | Señal en el duelo | Respuesta |
|---|---|---|
| **Analista** | Callado, mueve poco, cifras precisas | Su silencio es que está pensando, no un no. Subida lenta (gratis), paciencia |
| **Complaciente** | Mensajes largos y amables, concede pronto | Si su oferta ya está dentro del límite, cerrar ya: cada mensaje más cuesta un 10 % |
| **Asertivo** | Ancla extrema y rápida, se repite | Mantener el paso, con pregunta calibrada; oferta final cerca del deadline |

**Las dos patas son contra el mismo equipo** (U-05): lo aprendido de su tipo en la primera pata vale para la segunda (el «cisne negro» del cap. 10).

## Instrucciones para el operador (máquina A)

### Duelos III (11:00): Plan B, sin cambios

No parar el runner ni hacer `git pull`. Con `duels` armado ya aplica las ideas 4, 5 y 6 y, en parte, la 1. El `selftest` tarda unos 4,5 minutos con el runner parado, así que no cabe antes de las 11:00.

### Gran Final (14:00): Plan A, plantillas Voss

Hacerlo después de que acabe el último duelo de Duelos III y antes de las 13:45, **sin ningún duelo vivo** y no justo después de una aceptación:

1. `python3 bazaar.py status`. Mirar el titular del candado y STOP, y buscar en el diario una alarma **E16** o `duel_accepts_paused`. **Si hubo E16, no armar `duels` al relanzar**: el reinicio reactiva las aceptaciones en silencio (ese estado vive solo en memoria).
2. `python3 bazaar.py stop "plantillas Voss para la Final"`, **sin `--flatten`**: flatten cancela las pujas de Rastro y cierra los hilos de compra con dealers.
3. Esperar a que `python3 bazaar.py status` muestre el candado libre. Si sigue ocupado, el relanzamiento sale con código 3.
4. `git pull origin main` y `git log -3`: el único cambio de código debe ser `agent/talk.py`.
5. `python3 bazaar.py selftest`, **con el runner parado**: si `logs/run` o `state/` cambian durante el selftest, todas las etapas salen en rojo. Todas deben salir en verde.
6. `python3 bazaar.py resume --why "plantillas Voss, selftest verde"`. STOP **no** se borra solo: si sigue ahí, el runner sale con código 2 al arrancar.
7. Relanzar **el mismo** run: `python3 bazaar.py run --live --arm hygiene,dealers,rastro,closer,duels`, solo con las tácticas que estaban armadas. En las primeras líneas no debe salir `run: X not armed`.
8. Si algo sale en rojo: `git checkout c825858 -- agent/talk.py`, `selftest` de nuevo y relanzar. No improvisar.

### Durante cualquier duelo

- **No aceptar a mano el punto medio** ni subir la oferta para «desbloquear». Callar no cuesta rondas.
- **No pausar `duels` porque un rival esté callado**: la subida lenta es gratis.
- Pausar `duels` solo con rechazos de la Gate en cadena (`G50`/`G51`) o con E16.
- Apuntar el tipo de cada rival (analista, complaciente o asertivo): la segunda pata es contra el mismo equipo.
- **`days_sign` sigue en `null`**: fijarlo sin cambiar `_days_penalty` en la Gate provoca rechazos `G50.limit` en cadena (bitácora D7).
