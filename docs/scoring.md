# Puntuación: qué cuenta y qué priorizar

Fuentes: [RULES.md](../RULES.md), la presentación del kickoff (diapositivas 8 y 9), `/api/catalog`, `/api/schedule`, `/api/leaderboard` y el feed (vie 2 oct, tick 25).

## El marcador (100 puntos)
| Bloque | Peso | Qué lo compone |
|---|---|---|
| Negociación | 30 | **Duelos** (parte del pastel capturada) · **escalera de vendedores** (parte del rango de precios capturada; tus **3 mejores tratos por nivel**, los que faltan valen 0, los niveles altos pesan más) · **valor ganado comerciando con otros equipos**, a tus valores privados |
| Mercado | 30 | **Eficiencia en el Market Test** (la mitad de los puntos por igualar al puesto gratuito; los puntos completos van a la media del top 3) · valor creado entre otros equipos en tu mercado |
| Jueces | 40 | Ideas y calidad del trabajo |

**No cuenta nunca:** el número de operaciones, las comisiones cobradas, la suerte con los sobres (`luck`), los regalos, los easter eggs ni las concesiones de los organizadores. **El dinero (cash) no puntúa por sí mismo**: solo es un medio.

**Rondas:** cada día es una ronda (viernes ×½, sábado y domingo ×1) y se promedian. Una ronda en curso cuenta según la parte del día ya jugada (`rounds[].phase`), así que la puntuación pública **baja o sube sola** con el tiempo. Ejemplo: 1 trato daba 7,29 en el tick 15 y 5,91 en el tick 25.

## Desglose medible (`GET /api/me → score`)
`ladder_points`, `duel_points`, `neg_points` (comercio entre equipos), `mm_points`, `bench_efficiency`/`bench_points`, `negotiating`, `market`. Con solo el trato de bienvenida tenemos `ladder_points` 0,022 y negociación 5,25 (tick 30). **Cómo pasa `*_points` a los 30 puntos aún no lo sabemos**: se mide antes y después de cada trato (`run_dealer.py` lo registra).

## Dónde está el valor entre equipos
El valor de una carta para nosotros depende de lo que ya tenemos. Cuando falte una sola carta de una página, esa carta vale su catálogo × affinity **más el bonus de página** (25 % de la página). Comprarla a otro equipo por menos es la mayor ganancia de `neg_points` posible. Al revés, nuestros repetidos (25 % o 10 %) valen mucho para quien los necesita: hay que venderlos.

## ¿Penaliza no cerrar trato?
| Dónde | No cerrar trato | Cerrar un trato malo |
|---|---|---|
| Vendedores | **Sin penalización directa**: ese hueco vale 0 hasta que lo llenes. Lo que se pierde es tiempo y posiblemente cupo (`persona_quota` cuenta conversaciones **o** tratos por hora). La Abuela tiene memoria 0,15 y perdona | Un trato a su precio de salida **no cuenta para desbloquear nivel** |
| Duelos | **0 puntos** | **Resta** si el trato queda fuera de tu límite. El pastel se reduce con cada ronda (decay de 0,06 a 0,10) |
| Comercio entre equipos | 0 | Resta valor si vendes por debajo de tu `your_value` o compras por encima |
| Etiquetar mensajes (`flags`) | — | Un flag acertado puntúa y uno erróneo resta |

## Valor de las cartas: fórmula verificada (tick 33)
`valor de la copia k de una carta = catálogo(rareza) × affinity(set) × copy_marginals[k]`, con k = 0, 1, 2+ → 1,0 · 0,25 · 0,1.
- Comprobada contra la API: la suma da exactamente `collection_value` (251,6), y `GET /api/me/value?card=` coincide en 5 de 5 casos.
- **`your_value` de cada copia que tenemos = valor de la última copia**, que es lo que perdemos si vendemos una. `value?card=` = lo que ganamos con una copia más.
- **Bonus de página (sin verificar aún):** se supone un +25 % de la página (sus 10 cartas, 1.ª copia) al completarla, y un +10 % más con la épica y la legendaria. Se verificará con `value?card=SAL-10` cuando solo falte esa.
- **Valor para otros equipos:** los mismos 6 multiplicadores {0,5 · 0,7 · 0,9 · 1,1 · 1,3 · 1,6} repartidos de otra forma (media 1,017). Una común vale para otro entre 5 y 16 P (7,5 de media); la 1.ª copia de una rara, entre 35 y 112. Qué multiplicador tiene cada uno se puede **inferir** de lo que compra, guarda o vende (feed).

## Valor de las cartas (`/api/catalog → values`)
- `copy_marginals [1.0, 0.25, 0.1]`: la 1.ª copia vale el 100 %, la 2.ª el 25 % y la 3.ª el 10 %. **Los repetidos valen muy poco para ti** y por eso conviene venderlos.
- `page_bonus 0.25`: una página completa (comunes, infrecuentes y raras de un set) suma un 25 %. `master_bonus 0.1`: la épica y la legendaria encima suman un 10 % más.
- Valor de catálogo por rareza: común 10, infrecuente 25, rara 70, épica 180, legendaria 450. Cada equipo lo multiplica por su multiplicador privado de set.
- Valor esperado de catálogo por sobre: barrio 33,8 · bienvenida 78 · plata 160,8 · oro 410,5. La Abuela solo vende el de barrio.

## Lo que muestra el leaderboard (tick 25, todos en nivel 1)
| Equipo | Tratos con la Abuela (precio) | Negociación |
|---|---|---|
| t06 | sobre 17 (bienvenida), infrecuente 21, infrecuente 22, sobre 24 | 12,5 |
| t13 | infrecuente 17 (bienvenida), común 10, común 10 | 11,73 |
| t05 | sobre 17 (bienvenida), sobre 22, sobre 22, común 9 | 9,7 |
| t10 | infrecuente 17 (bienvenida), infrecuente 24 | 9,66 |
| t07 | sobre 17 (bienvenida), sobre 24 | 5,91 |
| t12 | vende una común a 13, sobre 24, vende una común a 5 | 5,91 |
| t18 (nosotros) y otros 4 | solo el de bienvenida a 17 (o una común a 7) | 5,91 |

Lecturas (hipótesis, pendientes de confirmar con el desglose de `/api/me`):
- **H1.** Un sobre a 24 P (su penúltimo o último precio) **no añade nada** (t07, t12). Uno a 22 P sí (t05). En los sobres solo puntúa capturar rango por debajo de unas 24 P.
- **H2.** Las **cartas sueltas** sí puntúan: infrecuentes a 21–24 (t06, t10) y comunes a 10 tras pedir 12 (t13). t13 hizo 11,73 gastando solo 37 P. **Llenar los 3 huecos con comunes o infrecuentes es mucho más barato que con sobres.**
- **H3.** El trato de bienvenida a 17 P (precio fijo) da el valor base de 5,91 (tanto t18 como t17, con una común a 7).

## Prioridades (por puntos por esfuerzo)
1. **Llenar los 3 huecos del nivel 1 con buenos tratos** (H2: cartas baratas que nos falten, empujando hasta su suelo). Además desbloquean el nivel 2 antes que al resto.
2. **Duelos**: los de práctica son en la hora 2 de juego; Duelos I (precio) en la 6,5; II en la 13; III en la 20; la final en la 23. Hay que tener el módulo listo antes de Duelos I.
3. **Market Test** desde la hora 3 y cada 2 horas: necesitamos nivel 2 para abrir un mercado de tipo `board` con broker propio. Sin él, el puesto gratuito saca la mitad de los puntos.
4. **Comercio entre equipos**: vender repetidos (valen el 25 % para nosotros) a quien le falten y completar páginas.
5. **Jueces (40 %)**: la trazabilidad de `docs/` y los logs es nuestra historia.
