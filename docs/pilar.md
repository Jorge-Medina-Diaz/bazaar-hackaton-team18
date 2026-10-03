# Doña Pilar · cómo venderle (guía medida, sáb 3 oct)

*Claude, a petición de Rubén. Fuente: feed público sin clave (ticks 559–630) acumulado por un vigilante de solo lectura.
Nada de Abuela o Chato se da por válido para Pilar: lo no medido en ella está marcado como experimento.*

## Lo observado (7 tratos, 15 hilos de venta)

| Infrecuentes | Abre | Cierres | Mejor | Respuestas hasta trato | ¿Aceptó el precio del equipo? |
|---|---|---|---|---|---|
| SAL / RET | 22 | 24, 24 | 24 | 4–5 | 0/2 |
| Resto | 16 | 17, 17, 17, 18, 19 | 19 | 3–8 | 0/5 |

- Anclas de 40–51 cerraron a 17–24; un ancla de 30 cerró a 19 (el mejor de su grupo). Descriptivo, n pequeño.
- Su texto dice "última palabra" y sigue subiendo: solo vale `final: true`.
- Raras, épicas y fiebre de SAL: **sin datos**.

## Reglas (`harness/pilar_guide.py`, `next_move`, con parámetros de `docs/dealer_params.json`)

Aprendido solo de Pilar (`python3 -m harness.dealer_tuner`), sáb ~17:00:
- Sube más cuando bajamos **1 P** (infrecuentes SAL/RET 78 % frente a 64 % con 2–3; resto 54/44/31 %; raras SAL 100 %).
- Su 1.er `final` llega en su respuesta **4** (raras: 5). **Perdona a 1 P** (4 de 5 a 0–1 P; 0 de 6 a 2 P, con `final` en la mitad).
- Se ha movido como mucho +4 en infrecuentes y +10 en raras SAL (cierres 69–70).

1. Solo **repetidas**; suelo = **V + 1**. Nunca una copia única de SAL/RET.
2. Ancla = su precio + lo máximo que se ha movido + 1 (SAL/RET infrecuente ≈ 27; rara SAL ≈ 72).
3. **−1 P por mensaje**, uno por tick, texto nuevo y cortés; nunca repetir precio.
4. En el mensaje nº `final_min` (4; raras 5): pedir **su precio + 1**. Si no lo toma, aceptar el suyo si ≥ suelo.
5. `final` ≥ suelo → aceptar; `final` < suelo → cerrar. `cooloff` → no reabrir hasta `until_tick`. Máx. 6 tratos/hora.

## Uso (operador, máquina A, bajo el Gate; primero en seco)

El ejecutor no vende a dealers (`agent/tactics/dealers.py`, fail closed). Este módulo está fuera de `agent/`: **no cambia `code_hash`**.

```bash
python3 -c 'from harness.pilar_guide import next_move; print(next_move("SAL-07","uncommon",FLOOR,[(22,False)],[]))'
python3 bazaar.py do open_thread --args '{"dealer":"pilar","side":"sell","ref":"<REF>","asset_ids":[<id repetida>],"limit":<V+1>}' --why "Pilar: guía docs/pilar.md"
```
Sin `--live` primero. Si el Gate rechaza (puede no conocer a Pilar ni los hilos de venta), parar y anotar el código.

## Métricas por hilo (para "ganar siempre")

- **Tasa de trato** = tratos / hilos abiertos.
- **Sin pérdidas**: 100 % de tratos con precio ≥ V + 1.
- **Captura** = (precio − su apertura) / (mejor cierre observado − su apertura). Proxy: el rango del servidor no es público.
- **Mensajes hasta trato** (cuota de 6/hora).
- **Cero penalizaciones**: `cooloff`, precios repetidos, contraofertas ≤ su precio.

## Experimentos pendientes (uno por venta propia)

- **E1**: ¿acepta su precio + 1? · **E2**: ancla apertura + 8 frente a 40: ¿mismo cierre? · **E3**: primera rara, en seco.

## Harness

`harness/retrieval.py` y `harness/dealer_history.py` filtraban solo `abuela`/`chato`: los hilos de Pilar se descartaban. Ahora usan `DEALERS` con `pilar`.
