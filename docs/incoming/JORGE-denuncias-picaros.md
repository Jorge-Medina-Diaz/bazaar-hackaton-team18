> **AVISO (revisión del dom 4 oct): documento de Rubén del sáb 3 oct, conservado como registro. Es dato, no instrucción: no pegar sus PROMPT ni ejecutar sus comandos. Las denuncias ya se enviaron, el "oro de Moscú" está agotado y varias afirmaciones son falsas ("no tenemos venue", el horario del domingo). Veredicto afirmación por afirmación: [REVISION.md](REVISION.md). Plan vigente: [../DOMINGO.md](../DOMINGO.md).**

# Denuncias a Los Pícaros: todo en uno (para Jorge, sáb 3 oct, 22:30)

> **Cómo usarlo:** pega este fichero entero en tu sesión de Claude Code (dentro del repo del equipo) y dile:
> «Sigue la sección PROMPT al pie de la letra». Empieza a las 22:30. Corte duro a las 22:55.

## 1. Contexto (30 segundos)

- Los Pícaros (nivel 4) intentaron colarnos **cartas distintas** de las que pedíamos: en un hilo `buy SAL-11` la
  oferta daba SAL-10, y en uno `buy LAT-09` daba LAT-06/07/08. Nuestro bot no aceptó ninguna.
- Las reglas lo premian: «flag a message you believe is bad faith with `POST /api/flags` (**a correct flag scores,
  a wrong one costs**)». La descripción oficial del nivel dice: «**flag a trick**».
- Nadie de t18 ha enviado ninguna denuncia. En el feed no se ve ninguna de ningún equipo y el campo `adjustments`
  del leaderboard está vacío para todos.
- **Hoy antes de las 22:55:** los trucos son del sábado y mañana quizá no se acepten. Si los Pícaros se molestan,
  tienen la noche para olvidarlo antes de la escalera del domingo.
- Rubén (lead) levanta para este caso la prohibición de strategy.md (Nunca #9) e INV-01/INV-20, **solo por esta vía
  manual**. No se toca `agent/`, `contracts.py`, `transport`, los tests ni el runner.

## 2. Verificación (hecha mensaje a mensaje contra el feed y el catálogo)

En los 9: el remitente es `picaros`, el hilo es de t18 y la oferta (`give.types`) da **otra carta, de menor
rareza**, por precio de la buena.

**Nivel A: el texto nombra la carta buena y la oferta da otra** (el ejemplo del SDK: «the offer is not what the
words say»):

| message_id | hilo | el texto dice | la oferta da |
|---|---|---|---|
| **8663** (prueba) | 1332 | «La Puerta de Alcalá… One hundred eighty-seven» (SAL-11) | SAL-10 a 187 |
| **9460** | 1455 | «…y la Puerta se va con nosotros», 167 P | SAL-10 a 167 |
| **9859** | 1550 | «¡el San Isidro!… seventy-three» (LAT-09) | LAT-06 a 73 |

**Nivel B: la carta solo va implícita** (precio o «the card»), dentro del hilo del tema: 8754 (1346, LAT-06 a 62),
9692 (1504, SAL-10 a 167), 9700 (1504, SAL-10 a 155), 9716 (1504, SAL-10 a 145), 9875 (1550, LAT-08 a 66) y 9891
(1550, LAT-07 a 62).

**¿Penaliza?** Denunciar es una mecánica oficial e invitada. No toca cartas, caja ni el bot. El único riesgo es
«a wrong one costs» (cifra desconocida). Por eso el orden es: prueba con la más clara, después el resto del
nivel A, y **el B solo si hay señal de que el A cuenta como acertado**. Si no la hay, el B no se envía.

**No denunciar nunca:** discrepancias de precio (8663 «87», 9875, 9891, 9906, 9915: falsos positivos o nos
favorecen), urgencias, «final» solo en el texto, ni hilos de otros equipos.

## 3. PROMPT (lo que tiene que hacer tu Claude)

**Paso 0. Repo del equipo.** Es PÚBLICO. Pregúntame (Jorge) si los jueces necesitan verlo esta noche:
- Si no: `gh repo edit Jorge-Medina-Diaz/bazaar-hackaton-team18 --visibility private --accept-visibility-change-consequences`
  y compruébalo con `gh repo view Jorge-Medina-Diaz/bazaar-hackaton-team18 --json visibility`.
- Si tiene que seguir público: `git push origin --delete claude/picaros-operador` (rama con una versión vieja de
  esta guía).
- No subir nada de esto al repo del equipo hasta después del cierre del domingo (15:00).

**Paso 1. Comprobaciones (sin enviar nada todavía).**
- `GET https://bazaar.causaprima.ai/api/clock`: `doors` tiene que ser `"open"` y `paused` false. Si no, para.
- `BAZAAR_KEY` disponible igual que la usa `bazaar.py`. **No la imprimas nunca.**
- Los 9 message_id son mensajes de `picaros` en hilos de t18 (`logs/picaros.jsonl`, `python3 picaros.py --json` o
  el feed). El que no cuadre, fuera.
- Guarda los números de `/api/me` para comparar después.

**Paso 2. Prueba: SOLO 8663.** Enséñame la respuesta exacta y espera a que yo diga «sigue». Si da error, para y
dame el texto exacto para Rubén.

```bash
python3 - <<'EOF'
import os, json
from bazaar_sdk import Bazaar
b = Bazaar(os.environ.get("BAZAAR_URL", "https://bazaar.causaprima.ai"), os.environ["BAZAAR_KEY"])
r = b.flag(8663, "Bad faith: thread 1332 is buy SAL-11; the text sells La Puerta de Alcalá (SAL-11) "
                 "at 187 but the structured offer gives card:SAL-10 instead.")
print(json.dumps(r, indent=2, ensure_ascii=False))
EOF
```

**Paso 3. Si digo «sigue»: el resto del nivel A.**

```bash
python3 - <<'EOF'
import os, json
from bazaar_sdk import Bazaar
b = Bazaar(os.environ.get("BAZAAR_URL", "https://bazaar.causaprima.ai"), os.environ["BAZAAR_KEY"])
A = [
    (9460, "Bad faith: thread 1455 is buy SAL-11; the text says the Puerta (SAL-11) goes for 167 but the "
           "structured offer gives card:SAL-10 instead."),
    (9859, "Bad faith: thread 1550 is buy LAT-09; the text sells San Isidro (LAT-09) at 73 but the "
           "structured offer gives card:LAT-06 instead."),
]
for mid, reason in A:
    try:
        print(mid, json.dumps(b.flag(mid, reason), ensure_ascii=False))
    except Exception as e:
        print(mid, "ERROR", e); break
EOF
```

**Paso 4. Nivel B: SOLO si hay señal** de que las A cuentan como acertadas (lo dice la respuesta, sube `/api/me`
o aparece un ajuste positivo) **y yo digo «B»**. Sin señal, no se envía.

```bash
python3 - <<'EOF'
import os, json
from bazaar_sdk import Bazaar
b = Bazaar(os.environ.get("BAZAAR_URL", "https://bazaar.causaprima.ai"), os.environ["BAZAAR_KEY"])
B = [
    (8754, 1346, "LAT-09", "LAT-06"), (9692, 1504, "SAL-11", "SAL-10"),
    (9700, 1504, "SAL-11", "SAL-10"), (9716, 1504, "SAL-11", "SAL-10"),
    (9875, 1550, "LAT-09", "LAT-08"), (9891, 1550, "LAT-09", "LAT-07"),
]
for mid, th, want, got in B:
    reason = (f"Bad faith: thread {th} is buy {want}; this counter-offer in that thread gives "
              f"card:{got} instead of {want}.")
    try:
        print(mid, json.dumps(b.flag(mid, reason), ensure_ascii=False))
    except Exception as e:
        print(mid, "ERROR", e); break
EOF
```

**Paradas obligatorias:** cualquier error, una respuesta de denuncia errónea, un `cooloff` de los Pícaros o que
sean más de las 22:55.

**Paso 5. Al terminar.**
- Compara `/api/me` con la foto del paso 1. Unos minutos después, mira `adjustments` de t18 en
  `https://bazaar.causaprima.ai/api/leaderboard`.
- Apunta en HANDOFF.md la hora, cada message_id, la respuesta del servidor y el cambio en la puntuación.
- Dame un resumen de 5 líneas para Rubén: qué se envió, qué respondió el servidor, qué cambió, cómo quedó el
  repo y si hubo alguna parada.

**Mañana (domingo):** con `radio.py --watch` activo, avísame de cada truco FIRME nuevo en un hilo de t18
(`give.types` distinto de la carta del tema). Se denuncia con el hilo ya cerrado y con mi confirmación.
Para comprar a los Pícaros, acepta solo si `give.types == ["card:X"]` exacta, también en la `final`
(`docs/picaros.md` §5–6).
