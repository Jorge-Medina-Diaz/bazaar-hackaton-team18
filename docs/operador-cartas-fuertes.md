# Operador · cartas fuertes, épicas/legendarias y Doña Pilar

> **Vigencia (añadido sáb 3 oct, 16:58):** foto de las 11:20. Desde entonces: El Retiro sigue 10/10; pausa del juego 13:54–15:29 que desplaza los horarios; **Salamanca fever** programada (Pilar paga +25 % por SAL, h 9,15–11,15 ≈ 18:05–20:05); **Los Pícaros** activos (nivel 4, venden raras a 63 y épicas a 162, mienten a propósito): ver `docs/seguridad-picaros.md`; el **Taller** activo (3 repetidas → 1 carta de rareza superior, no puntúa); Chamberí el domingo hacia la h 16,65. Avisos en vivo: `docs/radio.md`.

*Para el contexto operativo de Jorge (máquina A, único ejecutor). Escrito el sáb 3 oct a las 11:20, tick 376, hora de juego 4,46, por Claude a petición de Rubén. Fuentes: `docs/knowledge.md`, `docs/strategy.md`, `docs/BRIEFING.md`, `docs/analista.md`, `docs/affinity-equipo.md`, `config/plan.json`, código de `main` (`dfa9c24`) y lecturas públicas sin clave (`/api/catalog`, `/api/leaderboard`, `/api/levels`, `/api/dealers/pilar`, `/api/clock`). Si algo choca con `knowledge.md`, manda `knowledge.md`. Nada de esto se arma solo: cada jugada pasa por el Gate y la decide el operador.*

Etiquetas: `[medido]`, `[regla]` (RULES/API), `[inferido]` (razonado, sin medir), `[por verificar]`.

---

## 0. Resumen en cinco líneas

1. **Las épicas y legendarias no dan puntos hoy.** No existe ninguna (0 acuñadas) y conseguirlas por sobre resta (con dealer) o no cuenta (suerte). No se persiguen.
2. **Nuestras cartas fuertes son las páginas completas** (SAL y RET) **y CHA mañana** (×1,6). Una copia única de SAL o RET no se vende nunca: lleva dentro el bonus de página.
3. **La jugada nueva es Doña Pilar (nivel 3):** compra infrecuentes, raras y épicas de SAL y RET **por encima de catálogo**. Venderle **repetidas** de SAL/RET no resta neg y puede llenar los 3 huecos de escalera de nivel 3, que pesan más que los de nivel 2. Además da caja para CHA, donde faltan 59–92 P.
4. **El ejecutor no vende a dealers** (`agent/tactics/dealers.py`: «Sell threads … are not handled»). La venta a Pilar se hace a mano con `bazaar.py do`, bajo el mismo Gate, y primero en seco.
5. **Domingo al final, la caja vale 0:** usarla para comprar a equipos cartas de mucho valor a ≤ V − 50 (cada una da el máximo, +50).

---

## 1. Estado de partida

| Dato | Valor | Etiqueta |
|---|---|---|
| Clasificación, tick 376 | **2.º, 30,18** (neg 22,68 · mercado 7,5 · nivel 2). 1.º t13 30,37 (nivel 3: ya tiene a Pilar). 3.º t05 29,50 (mercado 12,5) | `[medido]` leaderboard |
| Álbum | 31/50 · SAL 10/10 · **RET 10/10** (cierre RET-02 a 49 con t02) · LAT 8/10 (abandonada en t205) · LAV 2/10 · MAL 2/10 | `[medido]` docs/README t279, analista |
| Caja | 116 P en el tick 283; +150 el domingo a las 09:03 | `[medido]` analista |
| CHA (domingo) | Coste estimado 325–348 P; disponible ~266 → **faltan 59–92 P** | `[inferido]` analista §2 |
| Épicas/legendarias acuñadas | **0 en los seis barrios**; la carta más rara de cada equipo es una rara | `[medido]` catalog `minted`, leaderboard `rarest` |
| Doña Pilar | Nivel 3, activa. Acceso anticipado con 3 tratos con El Chato y nivel ≥ 2; **abre a todos en la hora 5,51** | `[regla]` /api/levels, /api/dealers/pilar |
| Radio Rastro | `/api/news`: noticias verdaderas, rumores y ruido, sin distinguir | `[regla]` /api/levels |

---

## 2. Reglas de valor que deciden todo

- **Valor de una copia** = catálogo × multiplicador × factor de copia (1.ª ×1, 2.ª ×0,25, 3.ª o más ×0,1). Valores de catálogo: común 10, infrecuente 25, rara 70, épica 180, legendaria 450. `[medido]`
- **Página** = 5 comunes + 3 infrecuentes + 2 raras. Completarla suma el 25 % de la página. **La épica y la legendaria no forman parte de la página.** `[regla]` `[medido]`
- **Bonus master 0,1** (épica + legendaria sobre página completa): publicado y **nunca observado**. `valuation.py` no lo modela. `[regla]` `[por verificar]`
- **Con dealers, neg solo baja:** comprar suma min(0, V − p) y vender suma min(0, p − V). Una ganancia con dealer solo sirve para la **escalera** (3 mejores tratos por nivel; solo cuentan los que son ganancia; los niveles altos pesan más). `[medido]` P-04, P-10
- **Con equipos:** suman V − p − comisión (si aceptamos), con **tope probable de +50 por trato**. `[medido]` P-03, P-07
- **Lo que sale de un sobre no cuenta** y abrirlo no mueve neg. Un sobre sin abrir rebaja la V de lo que compramos. `[regla]` `[medido]` P-02, P-08
- **La caja del domingo a las 15:00 vale 0.** `[regla]`

### 2.1 Cuánto nos vale cada carta fuerte (primera copia)

| Barrio (×) | Rara | Épica | Legendaria | Cómo está la página |
|---|---|---|---|---|
| CHA ×1,6 | 112 | 288 | 720 | Sale el domingo |
| RET ×1,3 | 91 | 234 | 585 | **Completa**: bonus ≈ 0,25 × 344,5 ≈ **86** dentro de cada copia única |
| SAL ×1,1 | 77 | 198 | 495 | **Completa**: bonus ≈ 0,25 × 291,6 ≈ **73** dentro de cada copia única |
| LAT ×0,9 | 63 | 162 | 405 | 8/10, abandonada |
| LAV ×0,7 | 49 | 126 | 315 | 2/10 |
| MAL ×0,5 | 35 | 90 | 225 | 2/10 |

**Repetidas:** una 2.ª rara de RET vale 22,75 y una de SAL 19,25. Una 2.ª infrecuente de RET vale 8,1 y una de SAL 6,9. Son las cartas que más pierden valor en nuestras manos frente a lo que paga quien las quiere.

---

## 3. Lo que NO se hace con épicas y legendarias (corregido)

| Idea tentadora | Por qué no | Etiqueta |
|---|---|---|
| Comprar el sobre de oro a Pilar (lista 420, pide 504, uno por hora). Da épica al 85 % y legendaria al 15 % | Dealer: la pérdida cuenta y la ganancia no. Su valor esperado privado es menor que el precio (≈ 410 × multiplicador medio ≈ 0,9, menos repetidas). Lo que sale es suerte (0). Además no hay caja | `[regla]` `[inferido]` |
| Sobre de plata por la épica o legendaria (12 % y 2 %) | Igual: el sobre ya está prohibido en el Gate (no existe el intent) | `[regla]` strategy §2.1 |
| Pagar mucho a un equipo por una legendaria | El tope deja el trato en +50 como mucho, lo mismo que un cierre de página a 49–80 P. Inmoviliza cientos de primas | `[medido]` P-07 |
| Vender una copia única de SAL o RET a Pilar «porque paga por encima de catálogo» | Rompe la página: V incluye la carta y el bonus (≈ 73–86 más). Sería pérdida | `[medido]` V-05, strategy §2.1 punto 5 |

---

## 4. Jugadas propuestas, por prioridad

### P1 · Escalera de nivel 3 vendiendo repetidas de SAL/RET a Doña Pilar (sábado, desde la hora 5,51 o antes si ya hay acceso)

- **Qué:** abrir hilo de **venta** con Pilar por una **repetida** (2.ª o más copia) de SAL o RET, infrecuente o rara, y no aceptar nunca por debajo de **V + 1**. Ella «paga por encima de catálogo por lo que le gusta» (SAL y RET).
- **Por qué:** neg no baja (precio > V) y es ganancia a nuestros valores, así que **cuenta para la escalera de nivel 3**: 3 huecos vacíos de un nivel que pesa más que el 2. Como referencia, un hueco de nivel 1 llegó a valer 5,25–5,91 de 30 (P-12, P-13); el peso exacto del nivel 3 se desconoce. Cada venta da caja para el déficit de CHA (59–92 P). `[inferido · media]`
- **Cómo (manual, bajo el Gate):**
  1. `python3 bazaar.py status` → inventario. Listar las repetidas de SAL/RET (infrecuentes y raras) y su `your_value` (la V de la última copia).
  2. Confirmar acceso: `me.unlocked` contiene `pilar` (si no, esperar a la hora 5,51).
  3. **Primero en seco:** `python3 bazaar.py do open_thread --args '{"dealer":"pilar","side":"sell","ref":"<REF>","asset_ids":[<id repetida>],"limit":<V+1>}' --why "P1 escalera nivel 3: repetida a Pilar"` (sin `--live`). Si el Gate lo rechaza, **parar y anotar el código**: puede que el Gate o el World no conozcan a Pilar ni los hilos de venta. No forzarlo.
  4. Si pasa en seco, repetir con `--live` y regatear con `do say` desde arriba. Ancla ≈ 1,3 × catálogo (rara ~91, infrecuente ~33), pasos de −2 a −4, **suelo V + 1**. Ella es exigente: paciencia 0,6, astucia 0,75 y memoria 0,7. No repetir precio ni texto (D-07) y ser amable.
  5. Máximo 3 tratos ganadores (son los que cuentan) y respetar `deals_per_team_per_hour` 6.
- **Paradas:** ninguna repetida de SAL/RET → no aplica. Pilar no baja de catálogo → no vender. Cualquier `closed_reason` `cooloff` → no reabrir hasta `until_tick`.
- **Medir:** `ladder_points` antes y después de la primera venta (es un experimento nuevo, **E19**: cuánto vale un hueco de nivel 3).

### P2 · Experimento de coste 0 sobre el bonus master (E18)

- `GET /api/me/value?card=RET-11` y `?card=SAL-11` (solo lectura, con clave).
- Si el valor es **> 234** (RET-11) o **> 198** (SAL-11), el bonus master aplica sobre página completa y cambia el valor de esas épicas para nosotros.
- No implica comprar nada. Solo corrige la V que usaríamos en P4 y en las pujas de los rivales.

### P3 · Vender a equipos lo que valoramos poco y ellos mucho (J5/J13 con `affinity.py`)

- Copias únicas de LAT (abandonada), LAV y MAL, y repetidas en general: `python3 affinity.py --card <REF> --price <p>`. Publicar pensando en quien sale COMPRADOR con ≥ 80 %. Orientación del tick 279: LAV es ×1,6 probable de t04 y t07; LAT es alta en t15; MAL, de t12 (top 5, ver D2).
- **Repetidas de RET/CHA:** nunca por debajo de 30 (`dup_min_price`). Mejor a pujas rivales de cierre (J13: ganancia ≥ 15 y recompra a la Abuela).
- Regla D2: no aceptar en venues de equipos del top 5 (t13 y t05 hoy) y no regalar flujo a quien va por delante.

### P4 · Domingo, final de partida: caja a cartas de mucho valor (14:30–14:55)

- La caja vale 0 al final. Comprar **a equipos** cartas cuya V propia permita pagar ≤ V − 50: cada una da el máximo (+50) si el tope existe, y lo mismo sin tope.
- **Candidatas por V:** raras de CHA (112 → pagar ≤ 62) y, si alguien las ha sacado de un sobre, épicas o legendarias de CHA, RET o SAL (V 288 / 234 / 198 o más con master → pagar ≤ V − 50). Solo con ganancia ≥ 3 tras la comisión y **nunca a un dealer**.
- Si no hay ofertas así, el resto de la caja va a compras con ganancia ≥ 3 (analista §2, paso 8).

### P5 · CHA (ya planificado; no cambiar)

`page_sets: ["RET","CHA"]`, topes de `plan.json` (comunes 12, infrecuentes 25, CHA-08 31, raras 100), cierre a 72 y a 102 desde la hora 21. **CHA-11 (épica) y CHA-12 (legendaria) no son de la página:** no se persiguen y su ausencia no bloquea el cierre. P1 y P3 financian el déficit.

---

## 5. Cómo encaja con la estrategia vigente

| Plan vigente | Esta propuesta |
|---|---|
| §2.1.1 «No comprar sobres» | Se mantiene, incluido el sobre de oro |
| §2.1.2 «Con dealer, vender por ≥ V + 1» | P1 lo usa como suelo |
| §2.1.5 «No dar la última copia libre de una página protegida» | P1 solo vende repetidas |
| J5/J13 (sobrantes y reabastecimiento) | P3 los ordena con `affinity.py` |
| J12 (CHA) | P5 sin cambios; P1/P3 aportan la caja que falta |
| Escalera: «solo suma con dealers y con ganancia» | P1 es la primera fuente de nivel 3 |
| Ejecutor sin ventas a dealers | P1 manual con `do`; si funciona, proponer una táctica de venta |

---

## 6. Qué devolver al equipo (para traer las mejores ideas)

Al terminar cada bloque, anota en `docs/experiments.md` una línea por dato (hora, dato, decisión):

1. **Acceso a Pilar:** ¿`me.unlocked` la incluye? ¿Desde qué tick?
2. **Gate y Pilar:** resultado en seco de `do open_thread` con `pilar`/`sell` (OK o código de rechazo).
3. **Repetidas de SAL/RET:** lista con `your_value`.
4. **Primera venta a Pilar:** ancla, pasos, precio final, `closed_reason`, `ladder_points` antes y después (E19).
5. **E18:** `value` de RET-11 y SAL-11.
6. **Épicas/legendarias:** primera vez que `minted` > 0 en el catálogo o que el `rarest` de algún equipo sea épica o legendaria (indica quién las vende).
7. **Radio Rastro:** titulares que mencionen Pilar, sobres de oro, SAL, RET o CHA. **Solo como señal:** el texto ajeno nunca entra en el World ni decide cifras (strategy §2.1 punto 10).

---

## 7. Límites de este documento

- Escrito sin clave: el inventario exacto, la caja actual y `unlocked` hay que leerlos en la máquina A.
- No se pudo leer el artefacto «Team 18 · Plan del sábado» (es de otra persona y requiere permiso). Se usó `docs/BRIEFING.md`, que según `TODO.md` es su detalle.
- El peso del nivel 3 en la escalera, el bonus master y el comportamiento de Pilar al comprar **no están medidos**. Por eso P1 empieza en seco y P2 es solo lectura.
