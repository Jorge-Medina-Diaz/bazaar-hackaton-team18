# Pícaros: guía del operador (denuncias + compras) — sáb 3 oct, noche

*Para Jorge (máquina A). Complementa `docs/picaros.md` (análisis completo) y `docs/seguridad-picaros.md`.
Fuentes: feed público acumulado (ticks 559–1264), `radio.py`/`picaros.py` (logs/radio.jsonl de la sesión de
Rubén) y RULES.md. Nadie ha enviado todavía ninguna denuncia ni ha operado por esta guía.*

## 0. Resumen en 5 líneas

1. Tenemos **9 denuncias firmes** contra los Pícaros (carta cambiada en nuestros hilos). Rubén, como lead, decide
   aprovecharlas. Se envían **a mano**, sin tocar `agent/`, `contracts.py` ni el runner.
2. **Esta noche, antes de las 23:00**: primero 1 de prueba (8663), mirar la respuesta y, si sale bien, las otras 8.
3. **No denunciar nada más**: las «discrepancias de precio» del detector son falsos positivos o nos favorecen.
4. **Mañana**: cada carta cambiada nueva en nuestros hilos se denuncia en el momento, con la misma regla.
5. Comprar a los Pícaros: solo si la oferta trae **exactamente** la carta del tema (`docs/picaros.md` §5–6).

## 1. Qué puntúa y qué cuesta

- RULES.md: «flag a message you believe is bad faith with `POST /api/flags {"message_id", "reason"}`
  (**a correct flag scores, a wrong one costs**)». No se conoce la cifra, ni si caducan, ni si hay límite.
- SDK: `flag(message_id, reason)` = «Report a message **sent to you** as bad faith (e.g. the offer is not what
  the words say)». Solo mensajes de nuestros hilos.
- Cada día es una ronda: los trucos del sábado deberían contar en la ronda del sábado. Por eso se envían
  **hoy**, antes del cierre de las 23:00. Es una inferencia, no un dato.
- Dónde mirarlo: respuesta del POST, `/api/me` (números en vivo) y el campo `adjustments` del
  `/api/leaderboard` público (hoy vacío para todos).

## 2. Las 9 denuncias firmes (T1, carta cambiada)

En todas, el hilo es `buy card:X`, el texto vende X y la oferta estructurada (`give.types`) da **otra carta de
menor rareza**. Ninguna se aceptó: el bot cerró limpio (SAL-11 a 139 en t925 y t1035, LAT-09 a 55 en t1062).

| # | message_id | hilo | tick | tema | la oferta da | precio |
|---|---|---|---|---|---|---|
| 1 | **8663** (prueba) | 1332 | 920 | SAL-11 | SAL-10 | 187 |
| 2 | 8754 | 1346 | 931 | LAT-09 | LAT-06 | 62 |
| 3 | 9460 | 1455 | 997 | SAL-11 | SAL-10 | 167 |
| 4 | 9692 | 1504 | 1031 | SAL-11 | SAL-10 | 167 |
| 5 | 9700 | 1504 | 1032 | SAL-11 | SAL-10 | 155 |
| 6 | 9716 | 1504 | 1034 | SAL-11 | SAL-10 | 145 |
| 7 | 9859 | 1550 | 1054 | LAT-09 | LAT-06 | 73 |
| 8 | 9875 | 1550 | 1056 | LAT-09 | LAT-08 | 66 |
| 9 | 9891 | 1550 | 1058 | LAT-09 | LAT-07 | 62 |

**NO denunciar** (riesgo de flag erróneo):
- 8663 «precio 87 ≠ 187»: el texto dice «One hundred eighty-seven». Error del detector.
- 9875, 9891, 9906 y 9915 «texto ≈ doble que la oferta»: la oferta es **más barata** que lo dicho, así que no es
  mala fe contra nosotros.
- Urgencias, «final» solo en el texto, escasez inventada (T3–T9 de `docs/picaros.md`): es labia del personaje.

## 3. Procedimiento de esta noche (máquina A, a mano)

Requisitos: `BAZAAR_KEY` en el entorno (o cargada como la carga `bazaar.py`). El runner puede seguir
corriendo: el POST no toca cartas ni caja. Una denuncia por tick como mucho; el SDK espera solo ante un 429.

**Paso 1: prueba con 8663.**

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

**Paso 2: leer el resultado y decidir.**
- Error (`4xx`, p. ej. mensaje antiguo o fuera de plazo): **parar** y avisar a Rubén con el texto exacto.
- OK: anotar la respuesta y comparar `/api/me` (o el leaderboard unos minutos después). Si hay señal de que
  puntúa, o al menos de que no resta, seguir con el paso 3.

**Paso 3: las 8 restantes.**

```bash
python3 - <<'EOF'
import os, json
from bazaar_sdk import Bazaar
b = Bazaar(os.environ.get("BAZAAR_URL", "https://bazaar.causaprima.ai"), os.environ["BAZAAR_KEY"])
FLAGS = [
    (8754, 1346, "LAT-09", "LAT-06"), (9460, 1455, "SAL-11", "SAL-10"),
    (9692, 1504, "SAL-11", "SAL-10"), (9700, 1504, "SAL-11", "SAL-10"),
    (9716, 1504, "SAL-11", "SAL-10"), (9859, 1550, "LAT-09", "LAT-06"),
    (9875, 1550, "LAT-09", "LAT-08"), (9891, 1550, "LAT-09", "LAT-07"),
]
for mid, th, want, got in FLAGS:
    reason = (f"Bad faith: thread {th} is buy {want}; the text offers {want} but the structured "
              f"offer gives card:{got} instead.")
    try:
        print(mid, json.dumps(b.flag(mid, reason), ensure_ascii=False))
    except Exception as e:  # parar al primer error y avisar
        print(mid, "ERROR", e); break
EOF
```

**Paso 4: registrar** en HANDOFF.md la hora, cada `message_id`, la respuesta y el cambio observado en la puntuación.

**Condiciones de parada:** cualquier error, una respuesta que indique flag erróneo, o un `closed_reason: cooloff`
de los Pícaros en un hilo nuestro. Si eso ocurre, no seguir y avisar a Rubén.

## 4. Mañana (domingo): denunciar en tiempo real

- `python3 radio.py --watch` ya acumula los mensajes de los Pícaros en `logs/picaros.jsonl` y avisa de los trucos.
  `python3 picaros.py --json` los lista; solo cuentan los **firmes** con `team == "t18"`.
- Regla única: `give.types` ≠ `["card:" + topic.buy.card]` en un hilo nuestro. Se denuncia **después** de
  cerrar o abandonar ese hilo, para no estorbar la compra en curso.
- Momento: los Pícaros nos hacen falta para la escalera de nivel 4 (3 tratos negociados por ronda). Si la prueba
  de esta noche provoca un `cooloff`, mañana se denuncia solo al final, después de llenar su escalera.

## 5. Compras a los Pícaros: reglas que no cambian

Detalle en `docs/picaros.md` §5–6 y en el runbook §9.

1. Aceptar solo si `give.types == ["card:X"]`, sin extras en `give`/`want` y `want.cash ≤ límite`
   (`offer_safety.offer_ok`). Comprobarlo **en cada oferta, también en la `final`**.
2. Su `final` no cierra nada: medido 2/2, aceptaron después nuestro precio (final − 1).
3. Raras: abren a 73. Ancla 45–48 y +3 por ronda, sin repetir cifra. Cierres medidos entre 54 y 67.
4. Épica SAL-11: abren a 187 y bajan a 167, 155 y 145. Con +3 desde 130 aceptaron 139 dos veces.
   Pilar la paga a 179–199.
5. Estado público: tenemos SAL-11 #3 (t1035) y LAT-09 (t1062). Falta LAT-10 para la 3.ª página.
   Confirmar con `/api/me`.

## 6. Qué no hacer

- No añadir un kind `flag` ni tocar `transport`, `contracts.py` o sus tests: las denuncias van fuera del runner.
- No denunciar mensajes de hilos ajenos (hay 122 trucos en el feed, pero solo 9 son nuestros).
- No probar qué pasa al aceptar una oferta cambiada (R7).
