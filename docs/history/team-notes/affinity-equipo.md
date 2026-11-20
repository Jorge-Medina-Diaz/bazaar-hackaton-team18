# Estimador de multiplicadores de los rivales: resumen para el equipo

*Sáb 3 oct, tick ~279. Código: `agent/affinity.py` + `affinity.py` (en `main`). Panel en vivo: [Radar de barrios](https://claude.ai/artifact/Mc5Xzjj4uUMWTgP6z9vZ2C).*

## Qué hemos hecho
Todos los equipos tienen los mismos 6 multiplicadores (×0,5 · 0,7 · 0,9 · 1,1 · 1,3 · 1,6), uno por barrio, en un orden secreto. El estimador calcula, para cada rival, **qué probabilidad tiene cada barrio de valer cada multiplicador**.

- Para cada equipo prueba los 720 repartos posibles. Al principio todos valen lo mismo y cada dato público los va ajustando.
- Cada multiplicador se usa una sola vez, así que un dato sobre un barrio mueve también los demás: si MAL es casi seguro el ×1,6 de un equipo, ningún otro barrio suyo puede serlo.

**Qué datos usa y cuánto pesa cada uno**
| Dato | Qué nos dice | Peso |
|---|---|---|
| Compra a otro equipo a precio P | Probablemente valora la carta por encima de P | 1 |
| Venta a otro equipo | Poco: casi siempre es un repetido (vale el 25 %) | 0,7 |
| Pujas y ventas publicadas en cualquier mercado | Lo mismo, más débil (aún no se han cerrado) | 0,5 / 0,25 |
| Tratos con la Abuela o El Chato | Casi nada: todos les pagan de más (X-10) | 0,15 / 0,1 |
| Subida o bajada de `negotiating` en el leaderboard tras un trato entre equipos | Si ganó puntos, el trato le salió con ganancia a sus valores | 1 |

También tiene en cuenta que pagar muy por encima del libro suele ser por **cerrar una página** (bonus del 25 %), no porque el multiplicador sea altísimo.

## Qué tal acierta
- **En simulación** (equipos con multiplicadores conocidos): el intervalo del 80 % contiene el valor real el **92–97 %** de las veces. Es prudente, y para negociar es mejor así. Acierta el barrio ×1,6 en **6–9 de 12 equipos** (al azar serían 2).
- **Sobre nosotros, a ciegas:** el intervalo del 80 % acierta en **5 de 6 barrios**. Falla en SAL porque nuestras compras de SAL son anteriores al tick 76 y no las tenemos grabadas.
- **Cuánto queda por saber:** «bits» mide la incertidumbre. 9,5 = no se sabe nada y 0 = el reparto es seguro. Los mejor estimados van por 7,8–8,0. Con un equipo que no comercia, no hay forma de saber nada.

## Lo que dice ahora (tick 279; probabilidades modestas, usar como orientación)
| Equipo | Su ×1,6 más probable | Barrio que menos valora | Seguridad |
|---|---|---|---|
| t17 | **SAL** (42 %) | LAT | la más alta |
| t15 | LAT alto (×1,30 esperado); RET 34 % de ser su ×1,6 | LAV | alta |
| t05 | **RET** (39 %) | LAT | media |
| t04 | **LAV** (38 %) | MAL | media |
| t12 | **MAL** (38 %) | LAT | media |
| t06 | **SAL** (37 %) | LAT | media |
| t07 | LAV (31 %) | MAL | baja |
| t13 | SAL (30 %) | LAT | baja |
| t01, t09, t16 | sin datos suficientes | — | ninguna |

## Cómo usarlo al negociar
```
python3 affinity.py --card RET-09 --price 80   # a quién venderle (COMPRADOR) y a quién comprarle (VENDEDOR) a ese precio
python3 affinity.py --set SAL                  # quién valora más un barrio
python3 affinity.py --team t13                 # detalle de un equipo
python3 affinity.py --watch 60                 # dejarlo grabando en la máquina A (el leaderboard solo cuenta desde que se graba)
python3 affinity.py --history 5                # historia tick a tick -> logs/affinity_history.json (la que pinta el panel)
```
- Sirve para **elegir contraparte y dónde anclar** (mercado, duelos, trades entre equipos). **Las cifras de cada oferta siguen saliendo de nuestro valor y de las guardas**, nunca de esto.
- Regla práctica: vender solo a quien sale COMPRADOR con ≥ 80 % y buscar carta en quien sale VENDEDOR.

## El panel
[Radar de barrios](https://claude.ai/artifact/Mc5Xzjj4uUMWTgP6z9vZ2C): matriz equipo × barrio con el multiplicador esperado y la ★ en el ×1,6 más probable, y la evolución tick a tick del equipo que se elija. La franja gris marca el hueco del feed (ticks 159–203). Sustituido por la página [Barrios](https://t18-analista.vercel.app/barrios) de la Mesa del Analista, que se recalcula en cada tick en el navegador (semilla grabada + feed en vivo).
