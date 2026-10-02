# Sistema de puntuación: guía completa

*Para todo el equipo. Actualizado el vie 2 oct, tick 71. Etiquetas: ✅ medido con nuestras propias jugadas · 📜 dicho en las reglas o el kickoff · 🔌 dato de la API · ❓ hipótesis/inferencia.*

**Fuentes:** [RULES.md](../RULES.md) (sección *Scoring* y demás) · presentación del kickoff (diapositivas 6, 8 y 9) · API (`/api/catalog → values`, `/api/me → affinity, score`, `/api/schedule`, `/api/leaderboard`) · nuestras mediciones ([experiments.md](experiments.md): EXP-005, EXP-007 y la verificación de la fórmula en el tick 33).

---

## 1. El marcador: 100 puntos
| Bloque | Peso | De dónde sale | Campo en `/api/me → score` |
|---|---|---|---|
| **Negociación** | 30 | Comercio con otros equipos · escalera de vendedores · duelos 📜 | ❓ `negotiating` combina `neg_points`, `ladder_points` y `duel_points` (deducido de los nombres; la fórmula no se conoce) |
| **Mercado** | 30 | Market Test · valor creado entre otros equipos en nuestro mercado 📜 | ❓ `market` combina `bench_points` y `mm_points` (deducido de los nombres) |
| **Jueces** | 40 | Ideas y calidad del trabajo | — (fuera de la API) |

📜 **No puntúa nunca:** el número de tratos, las comisiones cobradas, la suerte con los sobres (`luck`), los regalos, los easter eggs ni las concesiones de los organizadores. **El dinero no puntúa por sí mismo**: solo sirve para comprar lo que sí puntúa.

📜 **Penalizaciones:** un porcentaje de la ronda por saltarse las reglas: compartir clave, varios equipos o regalar valor a otro equipo a propósito. ❓ Probablemente aparecen en `score.adjustments`.

## 2. Rondas: el tiempo también cuenta
- 📜 Cada día es una ronda: **viernes ×½**, sábado ×1 y domingo ×1. Las rondas se **promedian**.
- 📜 La ronda en curso pesa en proporción a la parte del día ya jugada (`leaderboard.rounds[].phase`). Por eso **la puntuación pública sube o baja sola** aunque no hagamos nada.
- 🔌 El leaderboard se refresca cada 5 ticks (`next_refresh_tick`). ✅/❓ El `score` de `/api/me` parece ir igual: `neg_points` subió a 20,9 y `negotiating` siguió en 10,3 hasta el snapshot siguiente. **Para medir un trato, hay que comparar `*_points`, no `negotiating`.**
- Consecuencia: **el sábado (14 h, peso completo) es la ronda decisiva**. Lo de hoy es entrenamiento que puntúa poco.

---

## 3. El valor de las cartas: la fórmula (✅ verificada)
```
valor de la copia k = catálogo(rareza) × affinity(set) × marginal[k]        marginal = [1.0, 0.25, 0.1]
```
| Rareza | Catálogo | Copias | Para nosotros en SAL (×1,1) | En CHA (×1,6) |
|---|---|---|---|---|
| Común | 10 | 300 | 11 | 16 |
| Infrecuente | 25 | 90 | 27,5 | 40 |
| Rara | 70 | 30 | 77 | 112 |
| Épica | 180 | 9 | 198 | 288 |
| Legendaria | 450 | 3 | 495 | 720 |

### Los multiplicadores (`affinity`)
- 📜 Todos los equipos tienen **los mismos 6 multiplicadores {0,5 · 0,7 · 0,9 · 1,1 · 1,3 · 1,6}**, repartidos entre los 6 sets de forma distinta. Son privados.
- ✅ **Los nuestros (t18): CHA 1,6 · RET 1,3 · SAL 1,1 · LAT 0,9 · LAV 0,7 · MAL 0,5.** Salen en `GET /api/me → affinity`.
- Una misma carta vale entre ×0,5 y ×1,6 según quién la tenga: **hasta 3,2 veces más para un equipo que para otro**. Ese desfase es la fuente de todo el valor comerciable.
- Los multiplicadores de los rivales se **deducen** de lo que compran y venden (mapa en [playbook.md](playbook.md)).

### Copias repetidas
- 🔌✅ La 2.ª copia vale el 25 % y la 3.ª el 10 % (`copy_marginals`; verificado contra `collection_value`). **Un repetido casi no vale nada para nosotros** y vale la copia entera para quien no la tiene.
- ✅ `your_value` de una carta que tenemos = **valor de la última copia** (lo que perdemos si vendemos una). `GET /api/me/value?card=X` = lo que **ganamos** con una copia más.

### Páginas
- Una **página** = las 10 cartas de un set: 5 comunes, 3 infrecuentes y 2 raras. La épica y la legendaria no forman parte de ella.
- ✅ **Completarla suma un 25 % del valor de la página.** Medido: con SAL en 9/10, SAL-10 pasó de valer 77 a **149,9** (77 + 0,25 × 291,6).
- 🔌 `catalog.values.master_bonus = 0.1`; las reglas dicen *"the epic and legendary on top add a little more"*. ❓ Aplicación exacta sin medir.
- **La última carta de una página vale casi el doble que cualquier otra.**

---

## 4. Las fuentes de puntos, de más a menos rentable

### 4.1 Comercio con otros equipos → `neg_points` ✅ (la más rentable hoy)
- **`neg_points` = primas de valor ganadas, 1 a 1**, a nuestros valores privados.
  - Vender: precio cobrado − nuestro valor de esa copia.
  - Comprar: nuestro valor − precio pagado.
- ✅ Evidencia: vendimos LAT-04 (valor 2,2) a 9 → **+6,8** exactos. Con tres repetidos vendidos: **+20,9**.
- Lo hacen los líderes: t08 llegó a 4.º con 4 tratos vendiendo una **rara** a 70; t13 es 1.º comprando MAL barato y vendiendo una rara de LAT.
- 📜 Los dos lados pueden ganar a la vez (cada uno a sus valores), y eso es lo que el juego premia.
- 📜 En El Rastro, **quien acepta paga la comisión** (5 % + 1 P por carta). Si publicamos y otro acepta, cobramos el precio entero.
- 📜 Regalar valor a otro equipo a propósito no cuenta y se revisa.

### 4.2 Escalera de vendedores → `ladder_points` ✅📜
- 📜 Puntúa la **parte del rango de precios del vendedor que capturamos**. Cuentan los **3 mejores tratos por nivel**, los que faltan valen 0 y los niveles altos pesan más.
- ✅ Cada trato con la Abuela ha movido `ladder_points` entre +0,000 y +0,015: **poco**. ❓ Cómo pesa `ladder_points` dentro de los 30 puntos no se conoce. (Corrección: la subida de 10,3 a 14,55 del tick 68 fue casi seguro el snapshot atrasado de los `neg_points` de las ventas, no el trato de SAL-08.)
- 📜 **Desbloquea niveles**: unos cuantos tratos *negociados* (no al precio de salida) dan acceso anticipado al siguiente vendedor y al nivel 2, que permite tener mercado propio.
- ✅ No cerrar trato no resta, y un trato malo tampoco (un hueco vacío vale 0).

### 4.3 Duelos → `duel_points` 📜
- 1 contra 1 con cada equipo, dos veces: una como vendedor y otra como comprador. Solo vemos nuestro límite.
- 📜 Puntúa la **parte del pastel capturada** en cada trato (*"share of each deal's pie you captured"*). El pastel es el margen entre el límite del vendedor y el del comprador; nosotros solo vemos el nuestro.
- **No cerrar trato = 0. Un trato fuera de nuestro límite RESTA.**
- El pastel **se reduce cada ronda** (decay de 0,06 a 0,10): conviene cerrar pronto.
- En Duelos II y III se negocian también los **días de entrega** (0–10). Cada lado tiene un peso privado por día, y el pastel crece si se cambia aquello que al otro le importa más.
- Calendario (horas de juego): práctica en la 2 (no puntúa) · I en la 6,5 · II en la 13 · III en la 20 · final en la 23.

### 4.4 Mercado propio → `bench_points` y `mm_points` (30 puntos enteros) 📜
- **Market Test**, cada 2 horas: todos los mercados reciben el mismo libro sintético. Puntúa el porcentaje de las ganancias posibles que realizamos.
  - Igualar al puesto gratuito da **la mitad** de los puntos; los puntos completos van a la media del top 3.
  - Para superarlo, el broker tiene que **estimar los límites ocultos** de los traders (cotizan lejos de su límite) y saber quién está a punto de irse.
  - Cada sesión cuenta con nuestro mejor mercado abierto durante ella; sin mercado abierto, cuenta 0.
- **Valor creado entre otros equipos en nuestro mercado.** Nosotros no podemos comerciar en él.
- Requisitos: **nivel 2** (fianza de 250 P, reembolsable, + 20 P). Los mercados de equipo abren a partir de la hora 3; sin mercado propio, tenemos un puesto gratuito de tipo `auto`.

### 4.5 Jueces (40 puntos) 📜
"Ideas y calidad del trabajo". Lo que tenemos para enseñar: la arquitectura (el código decide y el texto solo acompaña), el proceso de experimentos medidos, el playbook con errores y lecciones, y las herramientas (`scout`, `probe`, `market`).

### 4.6 Flags 📜
`POST /api/flags` sobre un mensaje de mala fe de un vendedor: un flag acertado puntúa y uno erróneo resta. Solo con evidencia clara: por ejemplo, que la oferta estructurada no coincida con lo que dice el texto.

---

## 5. Estrategias para ganar puntos (ordenadas por valor esperado)
1. **Llevar las páginas a 9/10 con cartas baratas y comprar la última a otro equipo.** La última carta vale ~2× (SAL-10: 149,9 para nosotros, frente a 35–112 para un poseedor cualquiera). Con una puja pública por debajo de nuestro valor ganan los dos. *En curso: puja de 80 P por SAL-10.*
2. **Vender lo que valoramos poco a quien lo valora mucho.** Repetidos (+7 cada uno), y cartas de MAL (×0,5) y LAV (×0,7) a los equipos que coleccionan esos sets. `market.py sell-dups 9`.
3. **Comprar lo que valoramos mucho por debajo de nuestro valor:** CHA (×1,6) y RET (×1,3) cuando salgan. Una común de CHA vale 16 para nosotros y se vende a unas 10; una rara, 112 frente a ~70.
4. **Raras cruzadas:** vender raras de sets bajos a sus coleccionistas y comprar raras de sets altos. Es el mayor salto de valor por trato.
5. **Duelos:** cerrar pronto, dentro del límite y nunca fuera. En Duelos II y III, ceder en los días que nos importan poco.
6. **Nivel 2 y broker propio** para el Market Test: son 30 puntos enteros y el puesto gratuito solo saca la mitad.
7. **Escalera:** 3 buenos tratos por nivel, sobre todo para desbloquear niveles.

## 6. Lo que NO hay que hacer
- Comprar a otros equipos por encima de nuestro valor o venderles por debajo: resta `neg_points`.
- Aceptar en un duelo fuera de nuestro límite: resta.
- Vender la **última copia** de una carta que forma parte de una página que podemos completar.
- Fijar los límites con el dinero en vez de con el valor (error E2: perdimos SAL-08 a 23 cuando valía 27,5).
- Llamar a `/api/admin/*`, compartir la clave o regalar valor: sanción.

## 7. Dónde mirar cada número
| Pregunta | Llamada |
|---|---|
| ¿Cuánto llevamos y de dónde viene? | `GET /api/me → score` (`neg_points`, `ladder_points`, `duel_points`, `bench_*`) |
| ¿Cuánto nos vale una carta más? | `GET /api/me/value?card=SAL-10` |
| ¿Cuáles son nuestros multiplicadores? | `GET /api/me → affinity` |
| ¿Quién tiene una carta? | `GET /api/leaderboard → teams[].rarest`, el feed (`pack.opened`, `settlement`) |
| ¿Hay gangas? | `python3 market.py scan` |
| ¿Cuándo hay duelos o Market Test? | `GET /api/schedule` |
