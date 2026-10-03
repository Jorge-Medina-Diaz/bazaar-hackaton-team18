# Auditoría de cierre del viernes (tick 158, 23:00)

*Fuentes: leaderboard snapshot 155 (`logs/leaderboard_fri_close.json`), 175 settlements del feed (cobertura 64 %, `logs/settlements_fri.json`), nuestros logs de score antes y después de cada trato. Lo que no se puede medir va marcado ❓.*

## 1. Resultado
| # | Equipo | Puntos | Tratos | Páginas | Suerte (`luck`) |
|---|---|---|---|---|---|
| 1 | t13 | 30,00 | 24 | 1 | +19,5 |
| 2 | t12 | 27,87 | 21 | 1 | **+30,8** |
| 3 | t17 | 22,08 | 15 | 1 | −25,5 |
| 4 | t10 | 20,79 | 19 | 1 | 0 |
| 5 | t05 | 20,03 | 24 | 1 | −29,2 |
| 6 | t04 | 19,89 | 13 | 0 | −10,5 |
| **7** | **t18** | **19,19** | 17 | 1 | **−25,5** |
- **Nadie tiene puntos de mercado ni de duelos.** Todo el marcador de hoy es negociación (comercio con equipos y escalera). Viernes = ronda ×½ y al 65 % de su fase: **lo que se decide el sábado y el domingo pesa ~4 veces más que lo de hoy**.
- 7 equipos tienen página completa. **Completar una página ya no distingue a nadie.**

## 2. De dónde salen nuestros 74,5 `neg_points` (medido trato a trato)
| Bloque | Δ `neg_points` |
|---|---|
| Ventas a equipos de repetidos y cartas que valoramos poco (LAT-04, SAL-01 ×2, LAV-03, MAL-01, MAL-04, SAL-06) | **≈ +52** |
| Compra de la última carta de la página (SAL-10 a 80, valor 149,9) | **+50** (❓ tope por trato) |
| **Pérdidas con vendedores** por pagar por encima de nuestro valor (sobre −8,4 · LAT-01 −1 · LAT-06 −1,9 · LAT-08 a El Chato −11,8 · LAV-06 a El Chato −4,5) | **≈ −27,6** |
| Escalera: `ladder_points` 0,051, que solo subió con SAL-08 (+0,015). Los 2 tratos con El Chato no la movieron | ~0 |
**Sin las pérdidas con vendedores tendríamos ~102 `neg_points`** (+37 %). Ese es nuestro mayor error del día: 5 tratos, todos después de tener la regla E9 escrita.

## 3. t13: ¿suerte o estrategia? Las dos, pero sobre todo estrategia
Sus 22 tratos capturados muestran un plan coherente desde el **tick 4**:
1. **Colecciona su set fuerte desde el principio, a la Abuela y barato**: SAL-06 17, SAL-03 10, SAL-05 10, SAL-08 24 (ticks 4–44). Nosotros empezamos SAL en el tick 45.
2. **Compra las raras que le faltan a quien las valora menos**: SAL-09 a 74 (t04) y SAL-10 a 70 (t10). Completa SAL en el tick 98.
3. **Vende las raras de su set débil**: LAT-09 a 65 (t14) y otra LAT-09 a 46 (El Chato), LAT-01 + LAT-07 por 40 a t15.
4. **Compra comunes de su otro set fuerte a 6 P** a quien las vende barato (MAL-05, MAL-02 y MAL-01, a t14, t05 y t06).
5. **Se deshace de los sobrantes a los vendedores** (SAL-01 5, SAL-02 6, LAT-04 6, MAL-01 5): el poco valor que les queda, convertido en dinero.
- **Suerte:** `luck` +19,5. Tuvo más de una LAT-09, probablemente de sobres. Ayuda, pero sus mayores ganancias son compras y ventas cruzadas entre sets, no sobres.
- **Diferencia estructural ❓:** sus pujas por SAL (55 → 65 → 70 → 74) apuntan a que su affinity en SAL es alta (×1,3–1,6). **Su set fuerte estaba disponible el viernes y los nuestros (RET ×1,3, CHA ×1,6) no.** Hoy nuestro mejor set era SAL ×1,1. Mañana se invierte.

## 4. t12: el que más ha subido (21,5 → 27,9)
- **Vende raras y comunes de SAL a los coleccionistas de SAL**: SAL-10 a **nosotros por 80**, SAL-08 a t05 por 18 y a t17 por 35. Nuestra mejor compra fue también una gran venta para ellos: así funciona el juego.
- Colecciona MAL: MAL-06 27, MAL-05 10, MAL-08 y MAL-07 a 21 de la Abuela, MAL-09 a 90 de El Chato.
- **La mayor suerte del tablero, +30,8.** Parte de su subida son sobres buenos convertidos en ventas.

## 5. Qué hicieron los de arriba y nosotros no
| Hacen | Nosotros | Coste estimado |
|---|---|---|
| Empezar a coleccionar su set fuerte en el tick 4 | Tick 45 (horas de análisis y herramientas antes de jugar) | Ventaja de ~40 ticks |
| 4–5 tratos de raras cruzadas | 1 (SAL-10) | Las raras son donde están los +30–50 por trato |
| Vender sobrantes a vendedores cuando no hay comprador | Los retuvimos esperando a equipos | Pequeño |
| **No pagar de más a vendedores** | −27,6 en 5 tratos | **El mayor coste del día** |

## 6. Qué hicimos bien (y hay que mantener)
- La medición: `neg_points` = primas ganadas, el bonus de página y la fórmula de valor. Nadie más lo tiene documentado así.
- La táctica de la última carta (SAL-10 +50) y la de los repetidos a 9 P (+52 en total).
- El agente autónomo y la documentación de errores: material para los jueces (40 puntos).
- Llegar al nivel 2 entre los primeros y probar el formato de los duelos en la práctica.

---

# Auditoría crítica (vie 2 oct, tick 108, hora de juego 1,8)

## 1. Clasificación y de dónde salen los puntos
| # | Equipo | Puntos | Nivel | Tratos | Páginas | Tratos con equipos (compras/ventas) | Patrón |
|---|---|---|---|---|---|---|---|
| 1 | t13 | 27,83 | 2 | 17 | **1 (SAL)** | 6 / 4 | Vende LAT caro (LAT-09 a 65; LAT-01 y LAT-07 a 40), **compra MAL a 6** y **completó SAL comprando SAL-09 a 74 y SAL-10 a 70** |
| 2 | t08 | 23,2 | **1** | 9 | 0 | 4 / 2 | Pocos tratos y grandes: vendió LAV-10 a 70 y compró MAL-10 a 53 |
| **3** | **t18** | **22,16** | 2 | 11 | **1 (SAL)** | 1 / 5 | 5 repetidos a 9–10 y SAL-10 a 80 |
| 4 | t10 | 21,79 | 2 | 15 | 0 | 2 / 4 | Colecciona LAV (LAV-10 a 70); vendió SAL-10 a 70 a t13 |
| 5 | t12 | 21,49 | 2 | 13 | 0 | 2 / 3 | Nos vendió SAL-10 a 80 |
- Nadie tiene puntos de **mercado** ni de **duelos**: todo es negociación (comercio y escalera). **El 60 % del marcador (mercado y duelos) aún no se ha repartido.**
- Ronda 1 al 44 % de su fase y con peso ½: **lo de hoy pesa poco. El sábado (peso 1, 14 h) decide.**

## 2. Lo que hicimos bien
- **Táctica de la última carta** (SAL-10 a 80, valor 149,9): la jugada de más valor de la noche (+50).
- **Repetidos a 9 en lugar de 10–12**: 5 ventas rápidas, ~+33.
- **Medir antes de suponer**: fórmula de valor, bonus de página, `neg_points` = primas, regla E9 y caducidad /4.
- **Nivel 2 entre los primeros** (acceso anticipado a El Chato).
- **Agente autónomo** operando y documentación de errores y tácticas.

## 3. Lo que hicimos mal (con coste)
| Error | Coste estimado | Causa raíz |
|---|---|---|
| E9: sobre a 23 cuando valía ~14,6 | −8,4 `neg_points` | Suponer que los vendedores no tocaban `neg_points` |
| E2: rechazar SAL-08 a 23 (valor 27,5) | ~25 ticks de retraso en la página SAL | Límite basado en el suelo del vendedor y no en nuestro valor |
| E1: límite de 20 en el primer sobre | 5 ticks | No mirar el feed antes |
| **Ritmo:** 11 tratos frente a 15–17 de los líderes | Ventaja de t13 | Mucho tiempo en análisis manual; el bucle llegó en el tick 90 |
| **Dinero parado:** 281 P sin usar | Coste de oportunidad | El dinero no puntúa; solo vale si compra cartas por debajo de nuestro valor |
| t13 nos ganó en ser **coleccionista** de SAL (pagó 70–74 por las raras y completó antes) | — | Llegamos tarde a las raras de SAL |

## 4. Qué hace t13 que no hacemos (y deberíamos)
1. **Comprar a otros equipos en su set fuerte a precio de mercado bajo** (MAL a 6): miles de comunes baratas se venden por debajo de nuestro valor solo si nuestro set es fuerte → para nosotros **RET y CHA mañana**.
2. **Pagar caro por las raras que completan página** (74 y 70): lo hicimos con SAL-10, pero solo con una.
3. **Vender caro lo que valora poco a quien lo colecciona** (LAT a t14 y t15 a 40–65).

## 5. Opciones ahora (hasta las 23:00, ~50 ticks)
| Opción | Valor esperado | Riesgo/coste | Decisión |
|---|---|---|---|
| a) **Duelos de práctica** (tick ~120) | 0 puntos, pero aprender el protocolo antes de Duelos I | Ninguno | ✅ el bucle los juega |
| b) Ofertas dirigidas: LAV a t10 (LAV-03 y LAV-04 a 10; valor 7) | +3 cada una | Ninguno | ✅ ahora |
| c) LAT a t15 (ya enviadas) · MAL y SAL-01 públicas a 9 | +3 a +7 cada una | Ninguno | ✅ en curso |
| d) Comprar a la Abuela o a El Chato | ≤ 0 (E9) | Resta | ❌ |
| e) **No abrir el sobre de bienvenida hasta que salgan RET (sáb) o CHA (dom)**: su contenido sale de los sets publicados y nuestras affinities altas son RET y CHA | Mejores cartas para páginas y cambios | Ninguno | ✅ guardar |
| f) Escalera nivel 2 vendiendo a El Chato | Desconocido | Puede restar si vendemos por debajo del valor | ⏸ probar mañana con una carta que nos valga poco |

## 6. Plan para el sábado (orden de ejecución, desde las 09:00)
1. **09:00 (hora 4,0):** sale RET y llegan 150 P (dinero ~430). Al instante: `probe.py` y `market.py scan`. **Abrir nuestro mercado** (`board`, comisión 0, 270 P) antes del primer Market Test (hora 5,0).
2. **RET (×1,3):** con un sobre de barrio que incluya RET, mirar `your_value` del sobre. **Comprar sobres solo si `your_value` ≥ precio** (E9). Comprar comunes e infrecuentes de RET a equipos por debajo de nuestro valor (13 y 32,5), pujas públicas como con LAT, **y las raras (91) y la última carta de la página a ~2×**.
3. **Market Test (horas 5, 7, 9, 11, 13, 15, 16 difícil, 17):** primera sesión en **modo grabación** con el broker (emparejamiento simple, como el puesto) y guardar el libro de cada tick; recalibrar `sim_bench.py` con datos reales; a partir de la 2.ª sesión, la estrategia que gane en simulación.
4. **Duelos I (hora 6,5):** solo precio. Módulo ajustado con lo aprendido en la práctica.
5. **Bucle** todo el día; subir `MIN_GAIN` si hay ruido y ampliar con pujas automáticas por cartas de RET.
