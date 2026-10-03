# Estrategia de duelos v2

*vie 2 oct, tick 155. Fuente: los 24 duelos de práctica de t18 (`GET /api/duels?done=true`, transcripciones completas) y 194 `duel.closed` del feed. Etiquetas como en [scoring.md](scoring.md): ✅ medido · ❓ hipótesis.*

## En una frase
**Anclar alto, hablar poco y dejar que el rival cruce hacia nosotros:** cada mensaje que el rival no contesta es gratis, cada intercambio cuesta un 6–10 % del pastel, y casi dos tercios de nuestros tratos se cerraron porque el rival **aceptó nuestra oferta**.

## 1. Lo que hicimos y cómo fue
La práctica se jugó entera con **v0** (ancla límite/0,6 o límite×0,6, β = 1,6, cede hasta nuestro propio límite, acepta todo lo de dentro desde el 75 % del tiempo). La v1 (espejo + brazos de texto, cambios sin commit en `agent/duels.py`) aún no ha jugado.

| | Duelos | Trato | Sin trato | `result` medio con trato |
|---|---|---|---|---|
| t18 (v0) | 24 | 17 (71 %) | 7 | 20,2 |
| Todos (feed) | 194 | 85 (44 %) | 109 | — |

- Mejores resultados (~40): duelos 55, 56 y 224, **el rival aceptó nuestra primera o segunda oferta**, todavía cerca del ancla.
- Peores (2–9): 161/162 (10 rondas: el decay se comió el 46 %), 96 y 243 (7 rondas), 12 (aceptamos su apertura).
- **Los 7 sin trato tienen algo en común: el rival no habló nunca** y nosotros dejamos de mandar tras 1–2 mensajes (69, 70, 95, 87, 88, 129, 130). Hay que mirar en `logs/duels.jsonl` del ejecutor por qué paró el runner en esos duelos.

## 2. Mecánica descubierta
- ✅ **`rounds` = mín(mensajes nuestros, mensajes del rival).** Se cumple en los 17 tratos (21: 7 nuestros y 5 suyos → 5; 162: 11 y 10 → 10; 55: 3 y 1 → 1). Consecuencias:
  - Un mensaje nuestro solo cuesta decay si el rival manda (o acaba mandando) al menos tantos como nosotros.
  - **Contra un rival callado, ceder a pasitos cada tick es gratis.**
  - **Contra un rival que habla solo (concede por tiempo), callarse es gratis** y él sigue bajando.
- ✅ **11 de 17 tratos se cerraron a nuestro precio:** el rival acepta la primera oferta nuestra que entra en su zona. Dónde caemos depende de nuestro paso: un paso grande se mete muy dentro de su zona y regala pastel.
- ❓ **Espejo (EXP-010):** cada pareja (2k−1, 2k) es **el mismo equipo** (misma plantilla de texto en las dos, aunque el alias cambie). Con el espejo, los 5 equipos que respetan su límite caen dentro en sus 10 tratos. Los otros 2 lo cruzan **en ambos sentidos** (161/162 y la familia "thank you for meeting me" en 223/224 y 243/244). Eso encaja mejor con bots que ignoran su límite que con un espejo falso. **Confianza media:** usarlo para el ancla, no como suelo rígido (ver 4.4).

## 3. Lo que hacen los otros equipos (arquetipos)
La mayoría son **plantillas con números decididos por código**; el texto apenas influye. Se reconocen por la primera frase.

| Arquetipo | Huella de texto (duelos) | Comportamiento | Contra él |
|---|---|---|---|
| **Aceptador rápido** | "159 P?" (55/56) · "Thank you for meeting me. I can do 49 P" (223/224) | Abre una vez y acepta nuestra oferta en cuanto entra en su zona, aunque esté lejos de su apertura | Ancla alta y **pasitos gratis cada tick** (no contesta, no hay rondas) |
| **Concede por tiempo** | "That's a real step from me: 128 P" (Sol, 161/162) · "Propongo este precio…" (96) | Paso lineal de 6–7 por tick **hable o no hablemos**; acepta lo que haya al final | **Callarse** tras el ancla. Aceptar cuando su oferta llegue al objetivo o al final. En 161 aceptó nuestro 46 al final: con 30 habría aceptado igual y sin 10 rondas de decay |
| **Se planta** | "Hello, and thank you for meeting me… 95 P" → "My offer stays at 73 P" (243/244) | 3–4 concesiones decrecientes y después **repite precio** | Precio repetido dos veces = su suelo. Aceptar si está dentro de nuestro límite: cada ronda más cuesta un 6 % |
| **Va al punto medio** | "Hello! I can do 102" → "Meeting you halfway at 91" (155/156) | Pasos que se encogen hacia nuestra oferta; solo se mueve si nos movemos | Ceder poco y despacio: él recorre la mayor parte del camino |
| **Paso de 1** | "Es una pieza que merece su precio: 104 primas" (225/226) | Concede 1 por ronda, pero acepta nuestra oferta si entra en su zona | Igual que el aceptador: pasitos, y no aceptar su número |
| **LLM verboso** | "this card completes a strong album page…", "tight budget" (21/22) | Pasos de ~15, erráticos (199 → 257) | Paso tit-for-tat; el único donde el texto (brazos de EXP-012) puede mover algo |
| **Ausente** | nada | Nunca habla (3 de 12 equipos en sus dos duelos, otro en uno) | Seguir publicando pasitos: son gratis y quizá acepta al final |

## 4. Estrategia v2 (tick a tick)
Se construye sobre v1: mismas garantías (nunca fuera de `your_limit`, ofertas monótonas, nunca repetir precio) y mismo `log`.

### 4.1 Apertura
- **Ancla agresiva**, como v0 (vendedor límite/0,6; comprador límite×0,6). Fue la fuente de los mejores resultados. Con espejo y pastel ≥ 2: límite ± 90 % del pastel (v1).
- Si el rival ya ha abierto: nuestro ancla nunca es peor que su oferta (no ofrecer menos de lo que ya nos da).

### 4.2 Clasificar al rival (cada tick, por sus mensajes)
- `talks_alone`: ha mandado una oferta nueva y mejor sin que hayamos hablado desde su anterior → **concede por tiempo**.
- `holds`: la misma cifra dos veces seguidas → **se planta**.
- `silent`: no ha mandado nada desde nuestro último mensaje → aceptador, paso de 1 o ausente.
- si no, `responsive` (punto medio, LLM).
- Se hereda del duelo pareja (mismo equipo): si en 2k−1 se plantó en tal cifra, en 2k empezamos sabiendo cómo juega.

### 4.3 Qué hacer según el tipo
| Tipo | Acción | Por qué |
|---|---|---|
| `silent` | Bajar un **paso pequeño** (≈ 4 % de la distancia ancla–suelo) cada tick | Gratis: `rounds` no sube mientras él no hable. Caemos justo al entrar en su zona |
| `talks_alone` | **No hablar.** Aceptar en cuanto su oferta valga ≥ el objetivo actual de la curva, o al final | Él concede gratis; cada mensaje nuestro sería una ronda |
| `holds` | Aceptar si está dentro de nuestro límite y nos deja ≥ 25 % del pastel estimado (o hay espejo y está dentro); si no, un paso grande final | Ya no se va a mover; esperar solo quema decay |
| `responsive` | Paso = su última concesión (tit-for-tat), entre 3 % y 15 % de la distancia; hablar **como mucho una vez por cada mensaje suyo** | Cada intercambio cuesta; igualar su ritmo evita regalar |

### 4.4 Suelo y final
- No ceder nunca hasta nuestro límite exacto: el suelo es límite ± máx(1, 10 % de la distancia ancla–límite). Un trato en el límite vale 0, igual que no cerrar.
- Con espejo: suelo al 30 % del pastel (v1) **solo hasta 3 ticks del final**; después baja al suelo sin espejo. Si el espejo fallara, no nos quedamos sin trato.
- `left ≤ 1`: aceptar cualquier oferta dentro del límite (v1). Si no hay ninguna, publicar el suelo (el aceptador y el que concede por tiempo cierran ahí).
- Regla de aceptación general (v1): aceptar si su oferta ≥ nuestra siguiente × (1 − decay), o si el espejo dice que ha cruzado su límite.

### 4.5 Texto
Casi todos los rivales son código: el texto no mueve cifras. Mantener `plain` como base y dejar `info`/`inject` (EXP-012) solo como A/B contra el LLM verboso. Si los organizadores lo cuestionan, `--arms plain`.

## 5. Duelos II, III y final (precio + días)
- Mismo motor, más decay (0,08 → 0,10) y menos ticks (16 → 12): **callar y los pasos gratis valen aún más**.
- Mandar siempre `days` (sin él, `missing_days`). La forma de `your_days_weight` aún no la conocemos (en la práctica era `None`): **primer tick de Duelos II con `--watch`** y ajustar.
- Logrolling: el issue que el rival no mueve es el que le importa. Si apenas mueve los días y a nosotros nos dan igual, le damos sus días **a cambio de precio**: la misma utilidad para nosotros con más pastel. La regla actual (`0` si el peso es ≥ 0, si no `10`) es un marcador de posición.

## 6. Operativa
- **Duelos I: sáb 11:30 (hora 6,5).** 17 rivales × 2 = 34 duelos, 3 a la vez, 16 ticks de **60 s** (cambio del sáb 3 oct) → 16 min por duelo, ~3 h para los 34 (12 tandas de 3). Duelos II sáb 18:30 (2 rondas, 6 a la vez). Duelos III dom 11:00. Final dom 14:00.
- El runner tiene que estar vivo toda la sesión y relanzarse solo si cae (en la práctica 4 duelos se quedaron con un único mensaje nuestro).
- Respetar 5 req/s: con 3–6 duelos a la vez son 2 GET + hasta 6 POST por tick; cabe.

## 7. Cambios de código (pendientes de hacer sobre v1)
1. `classify(d, s)` con los 4 tipos y el `holds` heredado de la pareja.
2. En `step()`: `talks_alone` → no enviar; `silent` → paso pequeño; `responsive` → tit-for-tat; `holds` → aceptar o paso final.
3. Suelo = límite ± 10 % de la distancia; suelo del espejo solo hasta `left > 3`.
4. Tests nuevos en `tests/test_duels.py`: no habla con `talks_alone`; acepta con `holds` dentro del límite; con `silent`, paso ≤ 4 %; nunca baja del suelo antes de `left ≤ 3`.
5. Rejugar las 17 transcripciones de práctica como simulación (los rivales son deterministas) para comparar v1 con v2 antes del sábado.

Medición: EXP-017 en [experiments.md](experiments.md).
