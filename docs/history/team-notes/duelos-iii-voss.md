# Duelos con *Never Split the Difference* (Voss): estrategia para la Gran Final

Dom 4 oct. Gran Final a las 14:00: 12 ticks, decay 0,10, 4 duelos a la vez.
Asuntos: `price` y quizá `days`. **Comprobarlo en el primer duelo** (`issues`, `days_meaning`).
Skill: `.claude/skills/never-split-the-difference`. Hechos del juego: `docs/knowledge.md` U-01…U-13.
Medido con `run_duel_eval.py` y revisado por seis revisores independientes en dos rondas (seguridad, afirmaciones y operación; luego invariantes, Gate y G60, y código).

## Lo que cambia respecto al libro

Voss negocia contra personas, con tiempo y sin coste por mensaje. Aquí:

- **Cada intercambio cuesta el 10 % del pastel** (U-01, U-02: ronda = min(nuestros, suyos)). Cuatro rondas se comen el 34 %. Hablar es caro; **callar es gratis**.
- **Sin trato = 0** y cualquier trato dentro del límite es ≥ 0. «Mejor ningún trato que uno malo» solo vale en el límite, y eso ya lo garantiza la Gate.
- **El texto nunca decide nuestras cifras** (regla del repo) y **el texto ajeno no entra en el World**: no podemos hacer espejo ni etiquetar lo que dice el rival. Solo leemos sus cifras y sus ticks. Nuestro texto sí puede mover a un rival LLM.

## Lo que hace ahora el agente

Hay cuatro opciones en `agent/tactics/duels.py`. Todas pasan por la Gate y el firewall G60 sin cambios. Se encienden en `config/plan.json` → `"duels"`, sin cambiar el `code_hash`.

| Opción | Voss (cap.) | Comportamiento | Medido (Final, Δ por episodio, IC 95 %) | Estado |
|---|---|---|---|---|
| **V1 `voss_text`** | 3, 4, 7, 9 | El mensaje se elige por **fase** de la negociación, no por turno (tabla siguiente) | idéntico en puntos (los rivales simulados no leen texto) | **ON** (por defecto en el código) |
| **V2 `precise`** | 6, 9 (cifras impares, paso 5 de Ackerman) | Ningún precio múltiplo de 5: se mueve 1 P hacia nuestro lado si sigue siendo una concesión (137, no 140) | +0,01 [0,00, +0,02] | **ON** (plan.json) |
| **V4 `punch`** con `punch_mode: "wait"` | 8, 9 (encajar el golpe; que pujen contra sí mismos) | Si el rival no se movió desde su oferta anterior, o abrió con un ancla extrema (≥ 1,5·L o ≤ L/1,5), **no cedemos: callamos** ese tick. Es gratis y no suma ronda | +0,01 [+0,01, +0,01] | **ON** (plan.json) |
| V2 + V4 juntos | | | **+0,02 [+0,01, +0,03]**, ningún tipo de rival peor; también a decay 0,08 y con 16 ticks | **configuración elegida** |
| V3 `ackerman` | 9 (65 → 85 → 95 → 100 %) | Tres concesiones decrecientes hasta el objetivo y luego mantener | −0,03 [−0,08, +0,03]; **−1,2 a −3 P contra rivales reactivos** | **OFF** |

Las fases del texto (V1, `agent/talk.py`, iguales en `duel_days` con «y {d} días»):

| Fase | Cuándo | Texto | Voss |
|---|---|---|---|
| open | primer mensaje | «Sé que vas a pensar que abro fuerte. ¿Sería una locura cerrar en {p} P?» | auditoría de acusaciones + pregunta orientada al no (3, 4) |
| move | concesión normal tras su respuesta | «Parece que aún estamos lejos. ¿Cómo podemos acercarnos? Me muevo a {p} P.» | etiqueta + pregunta calibrada (3, 7) |
| how | rival quieto o con ancla extrema | «¿Cómo se supone que hago eso? Lo más que puedo ahora: {p} P.» | «How am I supposed to do that?» (7, 8) |
| final | oferta final en deadline − 4 | «Esto ya me cuesta: {p} P. ¿Te parece mal cerrar así?» | último número de Ackerman (9) |
| close | rival ya dentro del límite, ventana final | «¿Sería mala idea cerrarlo ya en {p} P?» | orientada al no (4) |
| ghost | el rival nunca ha hablado | «¿Has dejado de lado este trato? Sigo aquí: {p} P.» | el email de 9 palabras (4) |

**Lo que ya hacía el agente y coincide con Voss:** concesiones decrecientes (`curve`, exponente 0,625); nunca saltar al punto medio (la curva depende del número de respuestas del rival, no de su precio); usar el plazo, que corta en los dos sentidos (oferta final en deadline − 4 y aceptación en los 3 últimos ticks si el rival habla en ese tick); y callar cuando el rival calla.

**Errores corregidos de paso:**
- La provocación final repetía nuestro precio cuando el rival estaba más allá de nuestra oferta. La Gate lo rechazaba (`G50.repeat` / `worse_than_rival`); ahora espera.
- V2 + V3 juntos gastaban una ronda en un movimiento de 1 P.

## Lo que el simulador no puede decir

- **Los rivales son modelos supuestos** (8 de `tests/test_duels.py` y 3 nuevos: «parte la diferencia», «Ackerman» y «paciente»). Ninguno está ajustado a rivales reales (U-09).
- **El efecto del texto no se mide**: los rivales simulados solo leen cifras. V1 se juega a que los bots rivales sean LLM.
- La ganancia medida es pequeña (+0,02 P por episodio, ≈ 0,25 %). **La palanca grande sigue siendo `days`** (logrolling: ceder días que nos importan poco a cambio de precio). Está bloqueada porque `_days_penalty` en la Gate ignora `days_sign` (bitácora D7). **`days_sign` sigue en `null`**: fijarlo hoy haría que la Gate rechazara casi todas las ofertas con días.

## Leer al rival (cap. 9, tipos de negociador)

| Tipo | Señal | Qué hace ya el agente |
|---|---|---|
| **Analista** | callado, cifras precisas | subida lenta gratis y fase «ghost» |
| **Complaciente** | concede pronto | acepta en cuanto su oferta es buena; cada mensaje más cuesta un 10 % |
| **Asertivo** | ancla extrema, repite | V4: callamos en vez de ceder y usamos la fase «how» |

Las dos patas son contra el mismo equipo (U-05).

## Instrucciones para el operador (máquina A), antes de la Gran Final

Entre el final del último duelo vivo y las 13:45, **sin ningún duelo vivo**:

1. `python3 bazaar.py status`. Mirar el titular del candado y STOP, y buscar en el diario una alarma **E16** o `duel_accepts_paused`. **Si hubo E16, no armar `duels` al relanzar**: el reinicio reactiva las aceptaciones en silencio.
2. `python3 bazaar.py stop "Voss para la Final"`, **sin `--flatten`** (flatten cancela las pujas de Rastro y cierra los hilos con dealers).
3. Esperar a que `python3 bazaar.py status` muestre el candado libre. Si sigue ocupado, el relanzamiento sale con código 3.
4. `git pull origin main`. Comprobar con `git log -3` que llegan `agent/tactics/duels.py`, `agent/talk.py`, `config/plan.json` y `run_duel_eval.py`.
5. `python3 bazaar.py selftest`, **con el runner parado**. Todas las etapas deben salir en verde.
6. `python3 bazaar.py resume --why "Voss, selftest verde"`. STOP no se borra solo.
7. Relanzar el mismo run: `python3 bazaar.py run --live --arm hygiene,dealers,rastro,closer,duels`, solo con las tácticas que estaban armadas. En las primeras líneas no debe salir `run: X not armed`.

**Interruptores sin selftest** (solo `config/plan.json` + relanzar; no cambian el `code_hash`):
- Si en la Final hay demasiados rivales que no responden, quitar `"punch": true`.
- Para volver a los precios de antes: `"duels": {}`.
- `"voss_text": false` hace que el texto rote por turno, pero sigue usando los textos nuevos. Los textos antiguos solo vuelven con la vuelta atrás completa.

**Vuelta atrás completa:** `git checkout 1e79485 -- agent/tactics/duels.py agent/talk.py config/plan.json`, luego `selftest` y relanzar.

### Durante el duelo

- **No aceptar a mano el punto medio** ni subir la oferta para «desbloquear».
- **No pausar `duels` porque un rival calle** (con V4 a veces somos nosotros los que callamos, a propósito).
- Pausar `duels` solo con rechazos de la Gate en cadena (`G50`/`G51`) o con E16.
- **`days_sign` sigue en `null`.**

## Reproducir la medida

```
BAZAAR_TEST=1 py run_duel_eval.py --primary-only --n 2000 --seed 18 \
  --compare '{"base":{"voss_text":false},"final":{"precise":true,"punch":true,"punch_mode":"wait"}}'
```
