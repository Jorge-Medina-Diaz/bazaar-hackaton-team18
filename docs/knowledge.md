# Base de conocimiento verificada — Team 18 (t18)

Estado: sábado 3 oct 2026, ~00:45, juego cerrado. Datos hasta el cierre del viernes (tick 159).
Única fuente de verdad sobre **lo que sabemos**. Todo lo demás en el repo (playbook, scoring, audit, STRATEGY*, SHOWCASE, RECHECK, HANDOFF...) es una lista de afirmaciones; si contradice esto, manda esto.

**Cómo se ha construido.** Ocho analistas estudiaron el viernes y ocho escépticos independientes rehicieron sus cuentas desde los datos crudos. Aquí solo entra lo que el escéptico confirmó (con su redacción corregida) o lo que está escrito en RULES.md. Lo incierto va a "Preguntas abiertas", con el experimento seguro más barato. Lo refutado va a "Refutado", con los documentos que aún lo dicen.

**Etiquetas.** `[medido]` = rehecho desde logs/harvest, feed o logs propios. `[regla oficial]` = RULES.md, kickoff o schedule/catalog del servidor. `[inferido]` = deducción razonable sin medida directa. Confianza: alta / media / baja.

**Fuentes de detalle:** `logs/analysis/<dimensión>/` (scripts del analista) y `logs/analysis/<dimensión>/verify/` (scripts y notas del escéptico).

---

## Los diez hechos que más cambian el sábado

1. **No sabemos a qué hora pasa nada el sábado hasta las 09:00:30.** El viernes se paró en la hora de juego 2,65, no en la 4,0. El Market Test de la hora 3,0 sigue pendiente y el reloj está en `paused: true` (el viernes lo despausó un admin a mano hacia las 20:20). Caben al menos tres lecturas: N (t salta a 4,0 y todo va a su hora nominal), M (lo anclado al día va a su hora y lo absoluto se desplaza +1 h 21 min) y C (t sigue desde 2,65 y todo se desplaza +1 h 21 min). Se decide con un GET sin clave a /api/clock y /api/schedule a las 09:00:30 y otro a las 09:05. Todos los temporizadores deben salir de `schedule.now_hours` y de los eventos del feed, nunca de la hora de pared. `[medido · alta]` lo de las 2,65 y la pausa; `[inferido · media]` las lecturas.
2. **Con los dealers, neg_points solo puede bajar.** Comprar suma min(0, V − precio) y vender min(0, precio − V), donde V es el cambio del valor total de la colección (sobres sin abrir incluidos). Las ganancias con un dealer no suman nada a neg; solo pueden llenar la escalera. Encaja en los 8 tratos con dealers y en 11 de 12 puntos medidos de neg (el que falla es redondeo de pantalla); lo he vuelto a ejecutar (`logs/analysis/scoring/verify/v_neg.py`, modelo ponderado con tope 50). Consecuencia: no comprar sobres (vale ~18 el sábado y la Abuela cierra a 19–24) ni pagar a un dealer por encima de nuestro valor. `[medido · alta]`
3. **La escalera pesa mucho más de lo que dicen nuestros documentos.** Hasta el tick 40 no hubo tratos entre equipos y la puntuación de negociación era solo escalera: el máximo era 12,5 y nuestro 0,022 valía 5,25–5,91 puntos de 30. La escalera solo subió con tratos que eran ganancia a nuestros valores (+0,022, +0,014, +0,015); los 5 tratos con pérdida dieron 0, aunque quedara un hueco libre. Los 3 huecos del nivel 2 (El Chato) están vacíos. `[medido · alta]` la mecánica; `[inferido · baja]` la escala exacta y el peso de cada nivel.
4. **Abrir todo sobre en cuanto llegue (el del sábado incluido) y antes de comprar nada.** Un sobre sin abrir cuenta a su valor esperado, y cada carta que compramos y que ese sobre podría haber traído baja ese valor esperado. Por eso LAT-06 (pagada a 22 con valor de 22,5) restó −1,855 y LAT-08 restó −11,8 en vez de −9,5. Abrir un sobre no mueve neg_points. `[medido · alta]`
5. **Con equipos, neg_points cuenta 1 a 1 a nuestros valores, menos la comisión si somos quien acepta.** La comisión de El Rastro es ceil(0,05 × precio + 1 por carta) y la paga quien acepta (44/44 liquidaciones; caja reconstruida 10/10). Por tanto, mejor publicar que aceptar. La compra de SAL-10 contó exactamente +50,0 en vez de +69,9: hay un tope o una fórmula distinta, sin identificar. `[medido · alta]` regla y comisión; `[medido · alta]` el +50; causa desconocida.
6. **El bonus de página solo llega a neg_points si la carta que cierra la página se compra a otro equipo.** Comprársela a un dealer da 0 por la regla del punto 2. Para LAT: la primera rara vale 63 y El Chato cobra 90–93, así que comprársela a él resta unos −27; la segunda (que cierra la página, valor 122,6) comprada a El Chato daría 0. Las dos raras de LAT tienen que venir de equipos. Para RET: montar la página con dealers por debajo de nuestro valor (llena escalera y no resta) y cerrarla con una compra a un equipo. `[inferido · media]`, derivado de reglas medidas.
7. **Nuestra página LAT está expuesta en cuanto se abran las puertas.** Están a la venta todas las copias de LAT-01 (ofertas 2463 a 8 y 2592 a 9) y de LAT-05 (1652 a 12 dirigida a t15 y 2591 a 9), con la página en 8/10. La regla oficial dice que las ofertas siguen abiertas de noche. La causa es un fallo de `market.sell_dups`. Antes de arrancar nada, el equipo (con la clave) tiene que cancelar una oferta de LAT-01 y una de LAT-05. `[medido · alta]`
8. **El Market Test vale 30 puntos, igual que la negociación, y todos estamos a 0.** Un venue `board` con el broker greedy rinde exactamente lo mismo que el puesto gratuito (3000/3000 y 5000/5000 libros idénticos), cuesta 20 P, bloquea 250 P y da 0 en cualquier sesión en que el broker se caiga. El puesto gratuito saca la mitad de los puntos del banco (regla oficial). Abrir venue solo compensa con un broker mejor que greedy y con supervisor que garantice que no se cae. `[medido · alta]` / `[regla oficial · alta]`
9. **Los dealers son predecibles.** La Abuela no concede nada si no subimos (31/31) y luego cede ~1 P por ronda sea cual sea nuestro paso. Sus finales: sobre 19–24, infrecuente 21–25. Contraofertar por debajo de su final hace que se vaya (4/4), pero se puede reabrir en el mismo tick sin coste. El Chato nunca cede más que nuestro último paso (rara: abre en 97 y cierra a 90–93). Con nuestros valores de RET (13 / 32,5 / 91), las infrecuentes de RET a la Abuela (~22–23) son la mejor compra a dealer del sábado. `[medido · alta/media]`
10. **En los duelos, lo que cuesta son los intercambios, no el tiempo.** Resultado = |precio − límite| × (1 − decay)^rondas, con rondas = min(mensajes nuestros, mensajes del rival) (148/148). Callar no cuesta decay. No sabemos si los rivales ceden mientras callamos (64 de 71 mensajes rivales llegaron justo después de uno nuestro): eso decide si la política "ancla y espera" gana o pierde frente a v0. Lo zanja un experimento gratuito en el primer duelo de Duels I. `[medido · alta]` la fórmula; `[inferido · baja]` la reactividad.

---

## 1. Puntuación

- **P-01** `[regla oficial · alta]` Negociar vale 30 puntos: parte de los duelos, escalera de dealers ("tus 3 mejores tratos por nivel, uno que falte cuenta cero, los niveles altos pesan más") y valor ganado con otros equipos a nuestros valores privados (RULES l.118).
- **P-02** `[regla oficial · alta]` Nunca cuentan: el número de tratos, las comisiones cobradas, lo que sale de un sobre (luck), los regalos, los easter eggs ni las concesiones de los organizadores (RULES l.122).
- **P-03** `[medido · alta]` Con equipos: comprar suma V − precio − comisión (si aceptamos); vender suma precio − comisión − V. V = cambio del valor total, sobres sin abrir incluidos. Rehecho trato a trato: los 9 tratos con equipos y el total 74,452 frente a 74,5 medido.
- **P-04** `[medido · alta]` Con dealers (Abuela, El Chato): comprar suma min(0, V − precio) y vender min(0, precio − V). Lo he rehecho ejecutando `scoring/verify/v_neg.py`: el modelo ponderado con tope 50 cuadra 11/12 puntos medidos; el 12.º (t92: 81,65 frente a 81,6) es redondeo de pantalla. Tratar las ganancias con dealers como ganancias cuadra 0/16, y tratar los tratos con dealers como 0 cuadra 3/16.
- **P-05** `[medido · alta]` Pérdidas con dealers el viernes: LAT-01 a 10 (−1,0), sobre a 23 (−8,488), LAT-06 a 22 (−1,855), LAT-08 a 32 (−11,813), venta de LAV-06 a 13 (−4,5). Total −27,6. Ganancias que contaron 0: sobre a 17, SAL-02 a 9, SAL-08 a 24.
- **P-06** `[medido · alta]` Los "−2,3 de más" de LAT-06 y LAT-08 son el efecto del sobre de bienvenida sin abrir (del t98 al t145): con el valor esperado ponderado por existencias restantes, la V efectiva fue 20,145 y 20,187. Esto resuelve el desacuerdo entre las dimensiones: dealers (C16) y market (C4) daban la regla por fallida o con un residuo sin explicar; con el efecto del sobre cuadra.
- **P-07** `[medido · alta]` La compra de SAL-10 (V 149,875, precio 80, sin comisión porque éramos los autores de la puja) contó +50,0 ± 0,01. La causa no está identificada: puede ser un tope de 50 por trato o una fórmula del bonus de página. Un tope del 62,5 % del precio queda descartado (LAT-04 dio el 75 %).
- **P-08** `[medido · alta]` Abrir sobres, regalos y concesiones no mueven neg_points (aperturas en t98 y t145, regalo de LAT-05, sobre de bienvenida). Comprar un sobre sí: cuenta como trato con dealer a su valor esperado.
- **P-09** `[medido · alta]` luck = Σ(valor de catálogo de lo sacado − valor esperado del sobre), 18/18 equipos con ±0,2. luck_private es lo mismo a nuestros valores (−6,7 en t30, −17,5 al cierre). No puntúa.
- **P-10** `[medido · alta]` La escalera subió solo en tratos con dealers que eran ganancia a nuestros valores: +0,022 (sobre a 17, t6), +0,014 (SAL-02 a 9, t45), +0,015 (SAL-08 a 24, t67). Se quedó igual en los 5 tratos con pérdida. Nuestro total: 0,051.
- **P-11** `[medido · alta]` Pruebas más fuertes de que la escalera no mide solo el rango del dealer: el sobre a 17 era la apertura de la Abuela y aun así dio casi la parte completa, y el sobre a 24 de t07 no sumó nada en t25 teniendo un hueco libre.
- **P-12** `[inferido · media]` Un hueco del nivel 1 con la parte completa vale ≈ 0,022 (siete equipos con un único trato completo tenían exactamente 5,91 en t25). Los pesos de los niveles 2 en adelante y la fórmula de la "parte" están sin medir.
- **P-13** `[medido · alta]` Hasta el tick 40 la puntuación de negociación era solo escalera y relativa a los demás equipos: el máximo era 12,5 (t06 en t25; t05 y t06 empatados en t30), y entre t25 y t30 todos los equipos sin tratos nuevos se reescalaron por el mismo factor (~0,888).
- **P-14** `[medido · alta]` La puntuación pública solo se actualiza cada 5 ticks y se mueve aunque nuestros componentes no cambien (es relativa a los demás). El efecto de un trato se lee en `*_points`, no en `score`.
- **P-15** `[medido · alta]` El líder (t13) tenía exactamente 30,00 en t155. `[inferido · media]` Encaja negociar ≈ 12,5 × min(1, escalera/ref) + 17,5 × min(1, neg/ref), con ref = media del top 3, pero normalizar contra el máximo no queda descartado.
- **P-16** `[regla oficial · alta]` Cada día es una ronda; el viernes cuenta la mitad. Pesos 0,5 / 1 / 1, es decir, 20 % / 40 % / 40 % del total. Una ronda en curso cuenta por la parte de su día ya jugada y cuenta entera cuando el día termina (RULES l.124-125).
- **P-17** `[medido · alta]` phase = t/4 en la ronda 1 (0,104, 0,125 y 0,646 en t = 0,417, 0,5 y 2,583). Al cierre el snapshot aún decía `active` con phase 0,646; no está confirmado que pase a 1.
- **P-18** `[regla oficial · alta]` schedule.json: "Round 2 starts (holdings carry over)". Dice que las cartas se mantienen; no dice si neg_points y la escalera se reinician.
- **P-19** `[regla oficial · alta]` En el Market Test, igualar al puesto automático gratuito da la mitad de los puntos del banco y los puntos completos van a la media del top 3 (RULES l.82). La curva intermedia no se conoce.

## 2. Valores y páginas

- **V-01** `[medido · alta]` Valor de cada copia = libro(rareza) × affinity(set) × [1; 0,25; 0,1] para la 1.ª, 2.ª y 3.ª copia. Una página completa suma 0,25 × la suma de los valores de primera copia de sus 10 cartas. Reproduce collection_value en t30 (251,6) y t159 (505,4), 24/24 your_value y 72/72 value?card.
- **V-02** `[medido · alta]` collection_value incluye los sobres sin abrir a su valor esperado, sumando hueco a hueco y ponderando cada carta por las copias que quedan en su tirada.
- **V-03** `[medido · alta]` En GET /api/me, todas las copias de una carta repetida muestran el mismo your_value (el de la última copia): LAT-01 ×2 → 2,2 y 2,2. value?card es el valor de una copia más.
- **V-04** `[medido · alta]` Nuestra affinity: CHA 1,6 · RET 1,3 · SAL 1,1 · LAT 0,9 · LAV 0,7 · MAL 0,5 (me.json).
- **V-05** `[medido · alta]` Valor de una copia más de RET para nosotros: común 13, infrecuente 32,5, rara 91. De CHA, la rara vale 112.
- **V-06** `[medido · alta]` Bonus de la página SAL: +72,9 = 0,25 × 291,5. Completar RET supondría ~86,1 de bonus (la última común valdría 99,1) y CHA ~106 (la última común valdría 122).
- **V-07** `[medido · alta]` LAT: la primera rara que falta vale 63 y la segunda, la que cierra la página, 122,6.
- **V-08** `[medido · alta]` Álbum al cierre: SAL 10/10 (completa), LAT 8/10 (faltan LAT-09 y LAT-10), LAV 2/10, MAL 2/10. Caja 260 P, nivel 2, sin venue.
- **V-09** `[inferido · media]` Valor esperado de un sobre de barrio a nuestros valores: ~11,5 sin RET y ~18 con RET el sábado (17,97–18,3 según el modelo), ~24 el domingo con CHA. Sobre de plata: ~112–114 el sábado. Las dos dimensiones coinciden dentro de ±0,4.
- **V-10** `[medido · media]` catalog.json publica master_bonus 0,1. Nunca se ha observado, igual que el valor de la 4.ª copia.

## 3. Dealers

- **D-01** `[medido · alta]` Las aperturas son fijas, iguales para todos los equipos y a todas horas. La Abuela vende el sobre a 30, la infrecuente a 29 y la común a 12, y compra la común a 5 y la infrecuente a 12. El Chato vende la rara a 97, la infrecuente a 33 y el sobre de plata a 188, y compra la infrecuente a 13. Solo hay datos del viernes.
- **D-02** `[medido · alta]` Hasta el primer trato de un equipo con la Abuela, todos sus hilos tienen precio fijo de bienvenida: sobre o infrecuente a 17, común a 7, y ella compra la común a 13. Lo tuvieron 17 equipos; el nuestro (hilo #25, sobre a 17) ya está gastado.
- **D-03** `[medido · alta]` La Abuela no concede nada si el equipo no ha subido desde su última oferta. Los mensajes sin precio tampoco consiguen nada.
- **D-04** `[medido · media]` Tras un primer recorte de 3–4 P, la Abuela concede ~1 P por ronda siempre que subamos al menos 1 P, sea cual sea nuestro paso (pendiente ≈ 0,09–0,16). En las comunes concede ~0,5 P por ronda. Que los pasos pequeños cierren más barato no es significativo.
- **D-05** `[medido · alta]` La final de la Abuela llega en su 5.ª–7.ª oferta, como mucho 1 P por debajo de la anterior. Finales de sobre de 19 a 24 (n=20, mediana 22,5; hubo 3 tratos a 19), de infrecuente de 21 a 25.
- **D-06** `[medido · media]` Con 1 P de diferencia sobre su precio, la Abuela acepta casi siempre; con 2 P, ~1 de cada 3 veces. Encaja con un suelo oculto distinto en cada conversación.
- **D-07** `[medido · media]` Contraofertar por debajo de su final la hace irse ("not today", 4/4), pero el mismo equipo reabrió en el mismo tick y fue atendido normalmente. También se va cuando se le agota la paciencia (en #109 una contraoferta igual a su precio recibió "not today"): si nuestro precio iguala el suyo, hay que aceptar, no contraofertar. Repetir precio o texto provoca "with those manners".
- **D-08** `[medido · alta]` El texto del dealer no es señal fiable ("Es mi último, de verdad" con final:false en #224). Hay que fiarse solo del campo `final`.
- **D-09** `[medido · media]` El Chato nunca concede más que el último paso del equipo (18/18 en hilos completos). En raras sigue una rampa que se parece a min(paso, k − 1) en ~80 % de las rondas, pero no es una regla exacta. En infrecuentes concede como mucho 1 P por ronda, empezando en su 4.ª oferta.
- **D-10** `[medido · media]` Las raras de El Chato cerraron a 90, 90, 91 y 93. Con pasos de 2–4 P su precio bajó a 87 (t04) y 82 (t07, LAT-10, tick 157), pero esos hilos quedaron sin final cuando cerró el juego.
- **D-11** `[medido · media]` "If I like you" no se tradujo en mejores precios: los que desbloquearon pronto recibieron un sobre de bienvenida gratis y 1 h de acceso anticipado, nada más.
- **D-12** `[medido · alta]` Los dealers crean cartas nuevas al vender. La Abuela vende de su stock solo si ya tiene esa carta (10/10) y si no, la crea (52/52); El Chato creó las 8 raras que vendió. Stock al cierre: Abuela 22 cartas (18 comunes, 4 infrecuentes); El Chato 4 (LAT-08, LAT-09 #4, LAV-06, MAL-06). Ninguno tiene RET ni CHA.
- **D-13** `[medido · media]` La cuota de 3 sobres por equipo y hora se aplica y parece ir por franjas horarias fijas; el sobre de bienvenida cuenta. La de 8 tratos por hora nunca se vio aplicarse. No hubo ningún sold_out.
- **D-14** `[medido · media]` Venderle a un dealer paga poco: la Abuela paga 5–6 por común (lotes ~5,5 por carta) y 13–16 por infrecuente. El Chato se queda en 13 por infrecuente y solo llega a 15 cuando da su final. A t13 le compró una rara por 46.
- **D-15** `[medido · media]` Los regalos de la Abuela llegan en el primer hilo negociado tras el primer trato (15 de 17 equipos) y son casi siempre comunes. No hay ninguna prueba de que dependan de ser amables (el texto de los equipos no se ve en el feed).
- **D-16** `[regla oficial · alta]` Para desbloquear un dealer cuentan los tratos negociados; uno a su precio de apertura no cuenta (RULES l.35).
- **D-17** `[medido · alta]` El nivel 2 lo anunció un admin en t=1,183, lo activó en t=1,633 y lo abrió a todos exactamente 1,0 h después. Lo desbloquearon 18 equipos y todos recibieron un sobre de bienvenida gratis (no figura en RULES). Los niveles 3–5 no están en el schedule.
- **D-18** `[medido · media]` El recuento de tratos que hace el servidor para desbloquear es más estricto que "no a precio de apertura": a nosotros nos contó 3 de 4, y t15, con al menos 4 liquidaciones con la Abuela, no entró pronto. La regla exacta no se ha podido reproducir.
- **D-19** `[inferido · media]` Para entrar pronto en el nivel 3 tenemos 0 o 1 tratos con El Chato que cuenten (LAT-08 a 32 frente a 33; la venta a 13 fue a su precio de apertura). La regla del nivel 3 se desconoce.

## 4. El Rastro (mercado entre equipos)

- **R-01** `[medido · alta]` Comisión = ceil(0,05 × precio + 1 P por carta), 44/44 liquidaciones. La paga quien acepta, no quien publica (caja reconstruida 10/10). Los tratos con dealers no tienen comisión (131/131).
- **R-02** `[medido · alta]` Mercado pequeño: 46 tratos entre equipos en todo el viernes (9 nuestros), 484 ofertas de venta y 161 pujas; se cumplieron 26 ventas y 15 pujas. Medianas: común 9, infrecuente 24,5, rara 70.
- **R-03** `[medido · alta]` Las ventas por encima del catálogo casi nunca se llenan: comunes a ≥ 1,2× catálogo, 1/153; infrecuentes, 0/26. El mercado es poco líquido incluso a precio de catálogo o por debajo.
- **R-04** `[medido · media]` A 9, las comunes se vendían más que a 10–12 (1,39 frente a 0,51 ventas por cada 100 ticks de oferta), pero no antes: nuestras ventas a 9 tardaron una mediana de 13 ticks. A 8 no se vendió ninguna (evidencia débil).
- **R-05** `[medido · alta]` Pujas públicas: se cumplió el 9 % (14/154); en raras, el 4 % (3/69). Ofertas dirigidas: 3/29 en todo el mercado; las nuestras, 0/8.
- **R-06** `[medido · alta]` Ninguna oferta de venta del viernes era una compra rentable para nosotros mirándolas de una en una. La única excepción posible eran las raras de LAT dentro de un plan para cerrar la página (LAT-09 a 65 en t42–102, LAT-10 a 84 en t117–138).
- **R-07** `[medido · alta]` Con ticks de 60 s, una oferta duró lo pedido entre 4: el valor por defecto (40) dio 10 ticks y el máximo visto fue 60 ticks. A 30 s no está medido.
- **R-08** `[regla oficial · alta]` Fuera de horario no pasa nada: las ofertas siguen abiertas y no se liquida nada hasta que se abran las puertas (RULES l.107).
- **R-09** `[medido · alta]` Nuestras ofertas abiertas caducan en los ticks 167 (1652), 173 (2460, 2462, 2463, 2465, 2466), 205 (las pujas 2503 y 2504 de 62 P por LAT-09 y LAT-10) y 210 (2591, 2592). Si el tick 160 cae a las 09:00 con ticks de 30 s, eso es entre las 09:03:30 y las 09:25.
- **R-10** `[medido · media]` La caja que vemos no descuenta las pujas: se publicaron dos pujas de 62 P en el tick 145 y la caja pasó de 236 a 256 en el 146 (venta de SAL-06), sin restar 124. No se sabe si una aceptación puede fallar por insufficient_cash si se cumplen varias pujas a la vez.
- **R-11** `[medido · alta]` Nuestro libro: 17 tratos (8 con dealers y 9 con equipos), caja 400 → 260, 5 P de comisiones pagadas (MAL-04 y SAL-06, en las que aceptamos nosotros).
- **R-12** `[medido · alta]` El contenido del sobre comprado a 23 en t97 (MAL-05, LAV-04, LAT-01) sigue sin vender: resultado neto −8,4.
- **R-13** `[medido · media]` venues.json (45 tratos, 1.088 de volumen, 125 de comisiones en El Rastro) es un snapshot de ~t155 y no cuadra exactamente con los 46 tratos que da la procedencia de las cartas. Para comisiones y tratos, fiarse del feed y de cards_all.

## 5. Rivales

- **X-01** `[medido · alta]` Se conoce el dueño final de 535 de los 538 activos (los 3 abiertos son LAV-09#3, LAT-06#6 y SAL-08#10) y las dos partes de los 46 tratos entre equipos. 45 de los 46 tienen precio; falta el de LAT-10 de t06 a t15 (tick 142, en un hueco del feed).
- **X-02** `[medido · alta]` De LAT-10 solo hay 2 copias: la #1 de t03 (de su mano inicial, nunca movida) y la #2 de t15 (que con ella completó LAT). De LAT-09 hay 4: t01 #1, t14 #2, t15 #3 y El Chato #4 (se la compró a t13 por 46 en t120, trato #1897).
- **X-03** `[medido · alta]` Hay pocas raras acuñadas: entre 2 y 5 por rara (la tirada es 30). No hay ninguna épica ni legendaria acuñada.
- **X-04** `[medido · alta]` Ningún equipo ha tenido nunca 2 copias de la misma rara, y El Chato acuña raras nuevas a 90–93 (8 el viernes). La estrategia del cuello de botella no es viable.
- **X-05** `[medido · alta]` t07 y t04 tienen LAT en 8/10 y les faltan 09 y 10; a t14 le faltan 03, 08 y 10. `[inferido · media]` t07 y t14 valoran LAT a ≥ 0,93–1,0, con márgenes estrechos. Compiten con nosotros por las raras de LAT.
- **X-06** `[inferido · media]` El único equipo que podría vender LAT-10 es t03; si no, queda El Chato (82–93). LAT-09 la tienen t01 (inactivo desde t103), t14, t15 y El Chato. Nuestras pujas de 62 en El Rastro no tienen ningún vendedor realista.
- **X-07** `[medido · alta]` Inactivos: t11 no ha hecho nada; t01 está parado desde t103 y t16 desde ~t132. Guardan raras clave: MAL-09#1 (t11), LAT-09#1 (t01) y SAL-09#2 (t16).
- **X-08** `[medido · alta]` t17 es 3.º con la misma mala suerte en sobres que nosotros (luck −25,5), comprando a equipos: 6 compras por 200 P y 0 ventas. Nosotros: 2 compras por 89 P y 7 ventas por 78 P. No hay un único perfil ganador: t12 (2.º) es vendedor neto (6 ventas por 227 P).
- **X-09** `[medido · alta]` Hubo 8 ventas de raras entre equipos, las 7 con precio entre 53 y 80 P. 5 de los 6 primeros (todos menos t05) hicieron alguna.
- **X-10** `[medido · media]` Las cotas de multiplicador sacadas de precios entre equipos aciertan en nuestro caso; las sacadas de tratos con dealers fallan (todos pagan de más a los dealers). Cotas robustas: t10 tiene LAV ∈ {1,3; 1,6} y SAL ≤ 0,9; t17, MAL ∈ {1,3; 1,6} y SAL ≥ 1,1. El resto, solo con tratos entre equipos, es más ancho.
- **X-11** `[medido · alta]` Al cierre hay 9 páginas completas (t18, t13, t10, t17, t12, t07, t15, t05, t08). t15 ya tiene LAT completa y no compra más LAT.
- **X-12** `[medido · media]` Contrapartes para el sábado. SAL: t02 (le falta SAL-09), t08 y t06 compran. MAL: t17 y t10 (les faltan las raras), t13 y t15. LAV: t14 (le falta LAV-07), t12 y t09 (les falta LAV-04, que tenemos repetida). LAT: t14 necesita LAT-03 y LAT-08, que tenemos.
- **X-13** `[medido · alta]` Los listados no prueban la propiedad: t09 publicó MAL-08 después de vendérsela a la Abuela (puede haber ofertas fantasma en el tablero).
- **X-14** `[inferido · baja]` Los multiplicadores de RET y CHA de los rivales no se pueden saber desde disco. La única pista débil es la regla de valor inicial igual, que da 0 soluciones para t07, t08, t12 y t13.

## 6. Duelos

- **U-01** `[medido · alta]` Resultado de un duelo con acuerdo = |precio − your_limit| × (1 − decay)^rondas, redondeado a 0,1 (18/18, error máximo 0,049). Sin acuerdo = 0. Solo se ha medido con excedente positivo.
- **U-02** `[medido · alta]` Una ronda = min(nº de mensajes nuestros, nº de mensajes del rival) (148/148 instantáneas). El tiempo no cuesta nada y aceptar no suma ronda.
- **U-03** `[regla oficial · alta]` Solo vemos nuestro límite; un acuerdo fuera de él resta puntos, no llegar a acuerdo da cero, y el valor se reduce con cada ronda de conversación (RULES l.90). Los duelos puntúan por "la parte del pastel de cada trato que capturaste" (RULES l.118).
- **U-04** `[medido · alta]` La hipótesis de que el límite del rival es el nuestro en la otra pata no encaja con 4 de 15 parejas (36 eventos incompatibles), suponiendo que los rivales no salen de su propio límite. Lo único que comparten las dos patas es el objeto (15/15 y 54/54).
- **U-05** `[inferido · media-alta]` Las dos patas de cada pareja son contra el mismo equipo rival: hay plantillas de texto idénticas en 7 parejas, y 306 = 2 × C(18,2). El alias cambia en cada duelo y no identifica a nadie. Lo aprendido de un rival en una pata sirve para la otra.
- **U-06** `[medido · alta]` Los límites no dependen del valor de catálogo del objeto.
- **U-07** `[medido · alta]` Práctica: 18 acuerdos, 7 sin acuerdo (los 7 con el rival mudo) y 5 vivos (149, 150, 193, 194 y 219, con deadline en el tick 168). Hemos empezado 30 de nuestros 34 duelos de práctica. En todo el feed: 60 acuerdos y 68 sin acuerdo, así que muchos equipos no tienen bot.
- **U-08** `[medido · alta]` El bot v0 perdió 72,5 P (15,7 %) del excedente bruto por decay, con 3,83 rondas de media. Aceptar antes habría sumado como mucho +3,7. 260,7 de los 389,5 vinieron de que el rival aceptara nuestra oferta.
- **U-09** `[medido · alta]` La reactividad de los rivales no se puede identificar con la práctica: v0 escribía casi cada tick y 64 de 71 mensajes rivales llegaron justo después de uno nuestro. Contra rivales que solo responden, la política "ancla y espera" pierde 0,5–4,3 P por duelo frente a v0; contra rivales que ceden con el tiempo, gana 16–18 P.
- **U-10** `[medido · alta]` Aceptar en deadline − 1 se liquida (duelo 12). La aceptación no lleva precio: toma la oferta que esté en pie en ese momento, así que hay que releer justo antes de aceptar.
- **U-11** `[medido · alta]` En la práctica hubo como mucho 6 duelos a la vez y los huecos se rellenaban en el acto (el reparto es continuo, no por tandas fijas).
- **U-12** `[regla oficial · alta]` Duels I: hora 6,5, 16 ticks, decay 0,06, 3 simultáneos, una vuelta (34 duelos). Duels II: hora 13,0, dos vueltas, decay 0,08, 6 simultáneos, precio y días. Duels III: hora 20,0, y Final: hora 23,0, ambos con 12 ticks, decay 0,10 y 4 simultáneos. La hora de pared depende de la lectura del reloj.
- **U-13** `[medido · alta]` En la práctica, your_days_weight y days_meaning llegaron a null. La conversión de result a duel_points no se conoce.

## 7. Market Test y venues

- **M-01** `[medido · alta]` No se ha jugado ningún Market Test: market = 0 en los 18 equipos y bench_points y bench_efficiency son null. La sesión de la hora 3,0 sigue en "upcoming".
- **M-02** `[regla oficial · alta]` Un venue cuesta una fianza reembolsable de 250 P más 20 P, y exige nivel 2. Los venues de equipo empiezan a operar en la hora +3; desde entonces, quien no tenga venue recibe un puesto gratuito, y abrir uno propio lo sustituye en el acto. No se puede operar en el propio venue con la clave del equipo.
- **M-03** `[regla oficial · alta]` Cada sesión cuenta el mejor venue que tengas abierto durante ella (ninguno cuenta 0) y la ronda promedia sus sesiones, así que cerrar después de una buena sesión no conserva nada (RULES l.81).
- **M-04** `[medido · alta]` Con greedy, un venue board da exactamente lo mismo que el puesto (bench_plan del starter = nuestro greedy en 5000/5000 libros). run_broker.py usa literalmente starter_broker.bench_plan.
- **M-05** `[regla oficial · alta]` En un venue board, si el broker no está corriendo no se empareja nada: esa sesión da 0, peor que el puesto.
- **M-06** `[medido · alta]` Emparejar más allá del final de sesión por encima de greedy nunca hace nada (greedy ya consume todos los pares que se cruzan). Maximizar la cardinalidad a ciegas en el banco puede ser peor que greedy (el segundo par vale B′ − S′, que puede ser −20 P).
- **M-07** `[medido · alta]` Para ofertas públicas reales, el emparejamiento de cardinalidad máxima (Kuhn, broker_spec.plan_public) nunca hace menos matches válidos que public_plan y hace más en el 12–16 % de los libros (según el generador).
- **M-08** `[inferido · media]` En simulación, esperar es peligroso: con la caducidad oculta, agent v1 pierde frente a greedy (10–28 pp en los modelos del escéptico). Las cifras de ganancia de las políticas "superset" y del oráculo (+4 a +11 pp) dependen de modelos de traders inventados y no están validadas con libros reales.
- **M-09** `[medido · alta]` Hay 4 venues rivales: v01 (t06, board, comisión 0 desde t156), v02 (t12, board, 0), v03 (t13, board, 100 bps) y v04 (t02, auto, 0). La API admite comisión 0. Los avisos de cambio de comisión entraron en vigor 2 ticks después (n=2, a 60 s).
- **M-10** `[medido · alta]` Flujo real del viernes: todo en El Rastro (641+ listados de 15 makers); 0 tratos en venues de equipo, como manda la regla, porque aún no podían operar.
- **M-11** `[medido · alta]` me.json no tiene starter_broker_key y venue es null: el puesto gratuito aún no existe para nosotros.
- **M-12** `[medido · alta]` Para abrir venue nos faltan 10 P (tenemos 260 y hacen falta 270). `[regla oficial · alta]` A la hora 4,05 llegan 150 P y un sobre de barrio para todos (schedule). Una o dos ventas de nuestras ofertas abiertas también nos llevarían a 270.

## 8. Reglas y calendario

- **C-01** `[medido · alta]` El viernes hizo ticks de ~20:20 a 22:59:46 (ticks 0–159, ~60 s) y t_hours = tick/60 en 3.136/3.136 eventos. Terminó en t = 2,65, 81 min antes de la hora nominal 4,0.
- **C-02** `[medido · alta]` Las acciones del schedule se disparan en el primer tick con t_hours ≥ at_hours (los duelos de práctica, a la hora 2,0, salieron a las 22:20:46, no a las 21:00). Las puertas siguen la hora de pared (cierre a las 23:00 con t = 2,65). Nunca se ha visto disparar una entrada vencida.
- **C-03** `[medido · alta]` El reloj está en paused:true. El viernes, un admin lo despausó a mano hacia las 20:20 (clock.changed, id 71), y t empezó en 0 sin saltar a la hora de pared.
- **C-04** `[medido · alta]` El catálogo ancla RET a "sat+0h" y CHA a "sun+0h", junto a anclas absolutas ("+0h" para los sets del viernes, "+2.63h" para que El Chato abra a todos). `[regla oficial · media]` Según la OpenAPI (PUT /api/admin/calendar): "Days that have already opened keep the live hour they opened at, so everything anchored to them stays where it is."
- **C-05** `[inferido · media]` Lecturas del sábado. N: ronda 2 y RET a las 09:00, +150 P a las 09:03, bancos a las 10, 12, 14, 16, 18, 20, 21 (difícil) y 22, Duels I a las 11:30, Duels II a las 18:00. C: todo +1 h 21 min, el sábado de 09:00 a 10:21 sigue siendo ronda 1 y la final del domingo nunca llega antes de las 15:00. M: mezcla de ambas. Los organizadores pueden reescribir el calendario.
- **C-06** `[inferido · media]` Probablemente haya un Market Test al principio del sábado (la sesión vencida de la hora 3,0, a las 09:00 o a las 09:21), aunque no está garantizado que se dispare.
- **C-07** `[medido · alta]` Límites del servidor: 1 aceptación por equipo y tick, 1 mensaje por lado y tick, 6 hilos abiertos, 30 ofertas abiertas, 12 listados nuevos por tick; el tick dura entre 5 y 60 s. `[regla oficial · alta]` 5 peticiones por segundo por clave (ráfagas de 20); sin clave, 60 por segundo por dirección.
- **C-08** `[regla oficial · alta]` Duración de los ticks: el sábado 30 s (09:00–23:00) y el domingo 15 s (09:00–15:00). Una sesión de 16 ticks dura 8 min el sábado y 4 el domingo.
- **C-09** `[medido · alta]` La OpenAPI expone 46 operaciones /api/admin/* (24 de escritura) y parámetros token/x-admin-token en /api/events/stream: no tocarlos nunca. El feed lleva el maker real en offer.listed aunque el tablero muestre seudónimos: no publicarlo ni depender de ello.
- **C-10** `[regla oficial · alta]` Las fuentes oficiales se contradicen sobre los anillos de colusión. RULES l.132 dice que esos tratos "count for nothing until the organisers have looked"; la OpenAPI de /api/admin/integrity dice "counts as an even split".
- **C-11** `[medido · alta]` Hay huecos en el feed (ticks 108–112 y 130–143) y el `ts` del feed es la hora de descarga, no la del evento. leaderboard.json y venues.json son snapshots de ~t155.
- **C-12** `[regla oficial · alta]` Juego limpio: la Fase 4 de santi/estrategia_el_estrangulamiento_de_rastro.md (órdenes complementarias en nuestro propio venue) está prohibida por RULES l.76, y hacerlo a través de otro equipo cae en "alimentar a otro equipo a propósito". No implementarla.

## 9. Nuestro código

- **K-01** `[medido · alta]` market.sell_dups se queda con la copia de serial más bajo aunque ya esté a la venta, así que puede llegar a poner a la venta todas las copias. Así acabó LAT-05 entera a la venta (t150). El LAT-01 #16 lo publicó en t143 código ad hoc que no está en el repo.
- **K-02** `[inferido · alta]` La guarda PROTECT de run_loop.best_trade cuenta las copias que tenemos, no las que quedan sin publicar: con las dos LAT-01 a la venta, todavía dejaría pasar una puja por LAT-01.
- **K-03** `[medido · alta]` haggle() nunca compara el límite con nuestro valor. Ya pasó: LAT-08 aceptada a 32 con valor 22,5; el sobre a 23; un intento de vender LAT-07 (de la página que estamos montando) con suelo de 14.
- **K-04** `[medido · alta]` `run_dealer.py abuela` sin argumentos compra 3 sobres hasta 23 P cada uno sin comprobar el valor (−5 por sobre o más).
- **K-05** `[medido · alta]` El candado de un solo ejecutor solo cubre haggle() y solo en una máquina (es un fichero temporal local). En el hilo 296, un segundo escritor que no está en el repo vendió LAV-06 a 13, por debajo del límite declarado de 14.
- **K-06** `[medido · alta]` En duels.py:37, `and rival is None` hace que sigamos cediendo después de la primera oferta del rival aunque calle (15 de 72 concesiones). En la práctica costó 0 P de resultado. Tras un reinicio, el estado se reconstruye mal (k = nº de mensajes nuestros); en la práctica tampoco cambió el resultado.
- **K-07** `[medido · alta]` run_duels.py llama a step() sin tick: el cierre en el deadline nunca se dispara y puede quedarse sin aceptar una oferta rival que está dentro de nuestro límite.
- **K-08** `[medido · alta]` El límite de precio de los duelos sí está garantizado en el código: 0 de 108 mensajes y 0 acuerdos fuera de your_limit, y nunca volvimos atrás en una oferta.
- **K-09** `[medido · alta]` offer_ok acepta las 56 ofertas reales de dealers. Pero run_loop (aceptación de mercado) y duels (duel_accept) aceptan sin llamar a offer_ok.
- **K-10** `[medido · alta]` Ningún script del repo cancela ofertas de forma automática, pero cancel() existe en el SDK y el viernes se usó a mano (al menos 8 cancelaciones). best_trade compra sin mirar nuestras pujas abiertas, así que E10 (dos vías para la misma carta) no está protegido.
- **K-11** `[medido · alta]` best_trade hace 42 llamadas a value() en un tick (setdefault evalúa b.value() siempre) y ningún código lee clock.limits. Mientras el juego está en pausa, run_loop sondea el reloj a ~3 peticiones por segundo (entre 2,3 y 5,4).
- **K-12** `[inferido · alta]` run_morning.py manda un segundo open_venue ante cualquier BazaarError, también ante un error de red en el que el primero quizá sí llegó, y escribe la respuesta (con broker_key) en logs/venue.jsonl.
- **K-13** `[inferido · media]` agent/dashboard.snapshot y probe.py vuelcan /api/me entero: en cuanto exista el puesto, starter_broker_key llegará a los logs y al navegador.
- **K-14** `[medido · alta]` Hoy no hay claves en ficheros versionados, ni en el historial de git ni en logs (solo fixtures de test).
- **K-15** `[medido · alta]` 93 tests: 91 pasan y 2 dan error en Windows porque una conexión sqlite queda abierta (`with sqlite3.connect` no cierra). No hay ningún test para run_loop, market, duels, broker, run_morning ni run_broker. Los tests escriben en el logs/information.jsonl real: sus 112 filas son de tests.
- **K-16** `[medido · alta]` Una excepción en un duelo hace que run_loop se salte el paso de mercado de ese tick (comparten el mismo try).
- **K-17** `[medido · alta]` El campo `locked` que usan haggle e information no existe en la respuesta real de /api/me.

---

## Refutado

Cada línea: la afirmación falsa → lo que sale de los datos o de las reglas → documentos que aún la dicen.

1. "La escalera pesa poco / los puntos salen de equipos, no de la escalera" → hasta t40 la puntuación era 100 % escalera y nuestro 0,022 valía 5,25–5,91 puntos de 30 (P-13). Lo dicen: docs/playbook.md:22, docs/scoring.md §4.2.
2. "El viernes es entrenamiento que puntúa poco" → el viernes pesa el 20 % del total (P-16). Lo dice: docs/scoring.md:24.
3. "El sábado es la ronda decisiva / lleva la mayor parte del juego" → el sábado y el domingo pesan lo mismo (40 % cada uno). Lo dicen: docs/scoring.md:24, STRATEGY.md §1. SHOWCASE.md ("Saturday and Sunday ... weigh 2× Friday combined") también se equivoca: juntos pesan 4× el viernes.
4. "neg_points = primas de valor 1 a 1" → hay que restar la comisión cuando aceptamos, incluir los sobres sin abrir en V, aplicar el +50 de SAL-10, y con dealers solo cuentan las pérdidas (P-03, P-04, P-07). Lo dicen: docs/scoring.md §4.1 y :61, docs/playbook.md:22, STRATEGY.md.
5. "Las pérdidas con vendedores fueron por pagar por encima de nuestro valor" → LAT-06 se pagó por debajo de su valor (22 frente a 22,5) y LAV-06 fue una venta, no una compra; LAT-06 y LAT-08 restaron por el sobre sin abrir (P-06). Lo dicen: docs/audit.md §2 (l.23), docs/playbook.md:4 y regla 1, docs/playbook.md E13.
6. "Comprar a ≤ valor da 0 neg_points" → LAT-06 a 22 ≤ 22,5 restó −1,86 (efecto del sobre sin abrir). Lo dice: docs/experiments.md EXP-012.
7. "Con LAT-08 la escalera solo puntúa la parte del rango capturada" → la escalera dio 0 porque el trato era una pérdida; LAT-06, 7 P por debajo de la apertura, también dio 0 (P-10). Lo dice: docs/playbook.md E13.
8. "Comisión = 5 % + 1 P por carta" → se redondea hacia arriba: ceil(5 % × precio + cartas) (R-01). Lo dice: docs/scoring.md §4.1 (acierta en que la paga quien acepta).
9. "Packs are luck, and luck never scores" → comprar un sobre puntúa como trato con dealer a su valor esperado (sobre a 23: −8,49). Lo que no puntúa es el resultado de abrirlo (P-08). Lo dice: STRATEGY.md:55.
10. "A full-share deal on a 7 P card scores like one on a pack" → solo si el precio queda por debajo de nuestro valor (LAT-01 a 10 dio 0). Lo dicen: STRATEGY.md:43, santi/STRATEGY_v2.md:55.
11. "El primer Market Test es el viernes a las 22:00 (hora 3)" → el viernes se paró en la hora 2,65 y no hubo ningún banco (M-01, C-01). Lo dicen: santi/STRATEGY_v2.md:10, :51 y :82, RECHECK.md:68, SHOWCASE.md (fila de Santi), STRATEGY.md:94 (§3.B/§4).
12. "Hard bench Sat 01:00 / benches every 2 h from Sat 09:00" → la hora de juego 16 es a las 21:00 (N) o a las 22:21 (C), y a la 01:00 las puertas están cerradas. Lo dice: STRATEGY.md:66. santi/STRATEGY_v2.md (calendario) da como seguras las horas de la lectura N.
13. "Market Test seguro a las ~09:20 (hora 3,0)" y "hora 5,0 a las ~10:00" → depende de la lectura del reloj, que no se conoce (C-05). Lo dicen: docs/README.md:7 y :28, docs/audit.md:104, docs/playbook.md:80.
14. "Tenemos 281 P" / "dinero ~430 a las 09:00" → al cierre hay 260; con la concesión del sábado, 410 (V-08). Lo dicen: docs/playbook.md:80, docs/audit.md:104.
15. "at_hours: viernes de 0 a 4" → el viernes fue de 0 a 2,65. Lo dice: docs/api.md:42.
16. "Las ofertas caducan a los 40 ticks (en la práctica 30)" → el valor por defecto (40) dio 10 ticks a 60 s/tick (R-07). Lo dice: docs/api.md:37.
17. "your_value es el valor marginal de cada copia (la 1.ª al 100 %, la 2.ª al 25 %)" → todas las copias muestran el valor de la última (V-03). Lo dice: docs/api.md:24.
18. "La Abuela imita el tamaño de nuestros pasos" → su concesión apenas depende de nuestro paso (pendiente ≤ 0,16). Esto sí vale para El Chato. Lo dice: STRATEGY.md:50.
19. "Las palabras mueven su ancla (17 por texto sin precio)" → 17 es el precio fijo de bienvenida antes del primer trato (D-02). Lo dicen: STRATEGY.md:51, santi/STRATEGY_v2.md:55.
20. "Solo el primer hilo de cada equipo recibe el precio fijo" → son todos los hilos hasta el primer trato, y además ella compra la común a 13. Lo dice: docs/playbook.md:145.
21. "Cooloff tras 'Come back after lunch'" → no se midió ninguno: hubo reaperturas en el mismo tick atendidas con normalidad. Lo dice: docs/playbook.md:154.
22. "La final llega antes con pasos pequeños" → llega en su 5.ª–7.ª oferta; con pasos pequeños hubo más ofertas, no menos. Lo dice: docs/playbook.md:155.
23. "Suelo secreto de 22, 23 o 24 en sobres" → las finales van de 19 a 24. Lo dice: docs/playbook.md:156.
24. "La Abuela compra la infrecuente a 13 fijo y la común a 5 fijo" → la infrecuente abre a 12 y cierra a 13–16; la común, 5 o 6. Lo dice: docs/playbook.md:163.
25. "Los regalos son por ser amables" → llegan en el primer hilo negociado tras el primer trato; no hay ninguna prueba de que influya la amabilidad. Lo dice: docs/playbook.md:167.
26. "El inventario de la Abuela son las cartas que le venden los equipos" → crea cartas nuevas cuando no tiene la que le piden (D-12). Lo dice: docs/playbook.md:27.
27. "El Chato cambia rápido a la oferta final" y "con él, pocos pasos y grandes" → sus finales llegan en su 5.ª–7.ª oferta, y un salto de 22 consiguió 1 P. El patrón eficiente es un paso constante de ~3–4 P. Lo dicen: docs/playbook.md:70 y :75, docs/experiments.md EXP-011.
28. "Límites de compra: sobre ≤ 23, común ≤ 10, infrecuente ≤ 22" → las finales de infrecuente van de 21 a 25: con un tope de 22 se abandonan la mayoría. Lo dice: docs/decisions.md D-006 (l.19).
29. "Solo hay 18 raras / 30 copias de cada rara en circulación" → hay 29 raras acuñadas y entre 2 y 5 por rara; El Chato acuña bajo demanda (X-03). Lo dicen: santi/STRATEGY_v2.md:16, santi/estrategia_el_estrangulamiento_de_rastro.md §2.
30. "La Abuela no vende raras; las raras solo se mueven entre equipos" → El Chato vende raras sueltas, el sobre de plata tiene un hueco de rara (86 %) y el de bienvenida un 40 %. Lo dice: santi/STRATEGY_v2.md §1 #7.
31. Estrategia del estrangulamiento (acumular raras con el sobre de barrio, controlar páginas con 3–4 copias, "24 P para él frente a 6 P para ti") → el sobre de barrio no trae raras, nadie ha tenido 2 copias de una rara y El Chato acuña copias nuevas. Lo dice: santi/estrategia_el_estrangulamiento_de_rastro.md §2 y Fase 2.
32. "Para LAT nos faltan 2 raras que nadie vende" → t13 publicó LAT-09 a 65, t06 publicó LAT-10 a 84, y El Chato tiene LAT-09 #4 y bajó LAT-10 a 82. Lo dice: docs/decisions.md D-008.
33. "Vender LAT a t15 cuando esté cerca de completar" → t15 completó LAT en t142. Lo dice: docs/playbook.md:51.
34. "Compradores de SAL = t13; de LAT = t14 y t07" → t13 ya completó SAL; ahora compran SAL t02, t08 y t06, y en LAT falta t04. Lo dice: docs/playbook.md:136.
35. "Tenemos la única página completa del juego" → al cierre hay 9 páginas completas. Lo dice: SHOWCASE.md:75.
36. "Los 4 primeros son los 4 de los únicos tratos de raras" → caducado: al cierre hay 8 ventas de raras entre equipos. Lo dice: STRATEGY.md:31.
37. "Cobertura de settlements del 64 %" → es el 64 % de los ids, pero el 91 % de los tratos que mueven cartas. Lo dice: docs/audit.md:3.
38. "Revender el contenido del sobre da +12–15" → las 3 cartas siguen sin vender (−8,4 neto). Lo dice: docs/experiments.md EXP-010.
39. "Los repetidos a 9 se venden en ~10–20 ticks / nuestros 9 P se venden" → se vendieron 5 de 9 y la limitación era la demanda. Lo dicen: docs/experiments.md EXP-005b, docs/playbook.md:122, SHOWCASE.md:69.
40. "El dinero parado tiene coste de oportunidad" → ni una de las 484 ofertas de venta era rentable comprándolas de una en una. Lo dice: docs/audit.md §3.
41. "Las ofertas dirigidas ganan los dos" → nuestras dirigidas se cumplieron 0 de 8; en todo el mercado, 3 de 29. Lo dicen: docs/playbook.md:101, docs/decisions.md D-008.
42. "Guardar el sobre de bienvenida hasta RET" → se abrió en t145, y guardarlo abarataba las cartas que comprábamos (P-06). Lo dice: docs/audit.md §5 opción e.
43. "Mínimos del viernes: común 7, infrecuente 17, sobre 19" → la común más barata entre equipos se vendió a 5, la infrecuente a 12 y el sobre más barato fue de 17. Lo dice: STRATEGY.md:54.
44. "En los duelos esperar cuesta" → el decay es por intercambio, no por tiempo (U-02). Lo dicen: docs/research-context.md §4, el docstring y el comentario BETA de agent/duels.py, santi/STRATEGY_v2.md:19 y §3.5.
45. "En duelos solo cedemos cuando el rival se mueve" → el código cede tras la primera oferta rival aunque el rival calle (K-06). Lo dicen: docs/playbook.md:171, el comentario de agent/duels.py.
46. "6 duelos por sesión en la práctica" → fueron 30 duelos en la sesión, con hasta 6 simultáneos. Lo dice: docs/playbook.md:170.
47. "El bot de duelos cierra rápido" → 3,83 rondas de media y un 15,7 % perdido; los días se fijan sin leer days_meaning. Lo dice: SHOWCASE.md:101.
48. "result = parte del pastel" → result es el excedente absoluto por el decay; cómo se convierte en duel_points no se conoce. Lo dicen: STRATEGY.md:9, ANALISIS_RENDIMIENTO.md:17, docs/README.md:38, docs/scoring.md §4.3.
49. "El límite del rival es nuestro límite en la otra pata" → no encaja con 4 de 15 parejas (U-04). Puede ser la "regla de rival fijo" de docs/README.md:7; si es eso, está refutada.
50. "Greedy ya está cerca del óptimo" → un oráculo lo supera por 4–11 pp según el modelo; solo es casi óptimo entre las políticas que no conocen los límites. Lo dice: docs/broker-design.md §5.
51. "Esperar en el broker mejora" → esperar pierde frente a greedy en todos los modelos (M-08). Lo dicen: docs/broker-design.md §3.4, el docstring de agent/broker.py.
52. "Tope oficial de 10 emparejamientos por tick" → es un recorte del public_plan del starter, no una regla. Lo dice: docs/broker-design.md §3.6.
53. "Comprobar si la API admite comisión 0" → ya está comprobado: v02 y v04 abrieron con 0. Lo dice: docs/broker-design.md §1.
54. "La primera sesión será con el puesto porque no tenemos nivel 2" → tenemos nivel 2. Lo dice: docs/broker-design.md §4.
55. "Max-card arregla la elección voraz en el banco" → solo vale para ofertas públicas; en el banco puede perder −20 P. Lo dice: PROPUESTA.md:54.
56. "30 puntos enteros de broker propio y el puesto saca la mitad" → la mitad se aplica a los puntos del banco, y el reparto entre bench_points y mm_points no se conoce. Lo dicen: docs/playbook.md:48, docs/scoring.md:118, santi/estrategia_el_estrangulamiento_de_rastro.md:8 y :57.
57. "Atraer el flujo de El Rastro con comisión cercana a 0" → sin respaldo: tres venues rivales ya tienen comisión 0 y no han hecho ningún trato. Lo dice: santi/STRATEGY_v2.md fila 9 / §3.2.
58. "+150 P a las 09:00" y "~240 aceptaciones esta noche" → la concesión llega a la hora 4,05 (09:03 con N, 10:24 con C), y el viernes hubo 160 ticks. Lo dice: santi/STRATEGY_v2.md §1 #10 y #11.
59. "Aceptar órdenes segundos antes del cierre del tick" → ninguna regla lo premia y se arriesga a perder el tick. Lo dice: santi/estrategia_el_estrangulamiento_de_rastro.md §4.
60. "offer_ok() antes de cualquier aceptación" → run_loop y duels aceptan sin offer_ok (K-09). Lo dicen: CLAUDE.md, docs/README.md:53, SHOWCASE.md:93.
61. "sell-dups nunca vende la última copia" → ha puesto a la venta todas las copias de LAT-05 (K-01). Lo dice: el docstring de market.py.
62. "La caja nunca baja de RESERVE (270)" → RESERVE = 150 y solo se aplica a compras. Lo dice: el docstring de run_loop.py.
63. "Un solo ejecutor" garantizado → el candado es local, de una sola máquina. Lo dicen: CLAUDE.md, docs/README.md:23.
64. "El mismo código corre en vivo y en el simulador" → run_broker usa starter_broker. Lo dice: el docstring de agent/broker.py.
65. "client.py usa wait_on_tick=False" → usa el valor por defecto, True. Lo dice: STRATEGY.md:102.
66. "Pasan las 93 pruebas" → 2 dan error en Windows. Lo dice: HANDOFF.md.
67. "Todo lo que toca la API deja rastro en logs/" → open_pack y el escritor del hilo 296 no dejaron log. Lo dice: CLAUDE.md.
68. "run_morning es seguro de relanzar" → reintenta open_venue ante errores de red. Lo dice: el docstring de run_morning.py.
69. "Las claves del broker nunca llegan al navegador" → agent/dashboard.snapshot manda /api/me entero. Lo dicen: HANDOFF.md (panel), el docstring de api/index.py.
70. "agent/dealers.py['chato'] abre al 60 %" → el código tiene un ancla de 0,70. Lo dice: docs/playbook.md (El Chato).
71. "El bucle captura cualquier excepción y sigue" → sigue, pero pierde el paso de mercado de ese tick (K-16). Lo dice: docs/playbook.md E11.
72. "Los puntos son la parte del rango capturada a los vendedores" → la escalera solo cuenta tratos que son ganancia a nuestros valores (P-10). Lo dice: docs/README.md:38.

Afirmaciones de los propios analistas refutadas por su escéptico (no deben citarse): finales de sobre "20–24" (son 19–24; dealers C5); los 3 activos anónimos que daba rivals C1 eran otros; "los seis primeros hicieron todos trato de rara" (t05 no; rivals C9); "El Chato acuñó 6 raras" (fueron 8); "17 equipos con nivel 2" (fueron 18); "nada en el repo puede cancelar" (el SDK sí puede; code C11); "4,7 req/s en pausa" (son ~3; code C13); "tandas de duelos sincronizadas cada 12 ticks" (el reparto es continuo; rules C17); "8 duelos sin acuerdo" (fueron 7, más 5 vivos); v0 "perdió 72,9 / 15,8 %" (fueron 72,5 / 15,7 %).

---

## Preguntas abiertas (con el experimento seguro más barato)

1. **¿Qué lectura del reloj rige el sábado (N, M o C)? ¿Se dispara la sesión vencida de la hora 3,0? ¿Sigue en pausa a las 09:00?** Decide la hora de todo. → GET sin clave a /api/clock a las 08:55 y a /api/clock + /api/schedule a las 09:00:30 y a las 09:05 (≤ 1/s). Mirar t_hours, round, paused y las entradas que siguen en "upcoming".
2. **¿Cuánta hora de juego avanza cada tick de 30 s?** Decide cuánto dura una "hora" de cuota y cuándo caducan las ofertas. → Comparar t_hours entre dos GET de /api/clock separados 10 ticks.
3. **¿Se reinician neg_points, escalera y duel_points al empezar la ronda 2?** Decide si lo hecho el viernes vuelve a contar. → Leer /api/me (lo hace el equipo con la clave) justo antes y justo después del cambio de ronda, sin operar entre las dos lecturas.
4. **¿El +50 de SAL-10 es un tope por trato (¿y hay un suelo de −50?) o una fórmula del bonus?** Decide hasta cuánto pujar por la carta que cierra una página. → Cuando se cumpla la segunda puja de LAT: +50 = tope; +54 = bonus al 0,2 del libro; +60,6 = sin tope. Coste 0 (la puja ya está puesta).
5. **¿Qué fórmula da la "parte" de la escalera y cuánto pesa cada nivel?** Decide si vale la pena llenar los 3 huecos de El Chato. → Un trato pequeño con ganancia segura (una común de RET a la Abuela a ≤ 8 si ofrece bienvenida, o a ≤ 10) leyendo ladder_points antes y después; después, el primer trato con ganancia con El Chato.
6. **¿Se reinicia con la ronda el precio de bienvenida de la Abuela (17/17/7)?** → Abrir un hilo de una infrecuente de RET y mirar su primer precio (17 o 29) sin comprometerse.
7. **¿Ceden los rivales de duelo mientras callamos?** Decide entre "ancla y espera" y v0. → En el primer duelo de Duels I con un rival que hable, callar 2 ticks tras su primera respuesta (callar no cuesta decay) y ver si se mueve.
8. **¿Cómo se convierte result en duel_points? ¿Gasta un duel_accept la aceptación por tick del equipo? ¿Cuenta como ronda un mensaje solo de texto?** → Registrar duel_points antes y después de cada acuerdo. Usar los 5 duelos de práctica aún vivos (no puntúan): un mensaje solo de texto, y una aceptación de duelo seguida de una de mercado en el mismo tick.
9. **Qué significan los días en Duels II (signo de your_days_weight, days_meaning).** → Leer GET /api/duels antes de jugar el primer duelo de dos issues; no enviar nada hasta tener days_meaning.
10. **¿Las pujas abiertas pueden hacer fallar una aceptación por insufficient_cash?** Decide si abrir el venue deja las pujas sin cubrir. → Comparar caja y pujas abiertas en el primer /api/me del sábado; no abrir el venue si caja − pujas < 270 hasta saberlo.
11. **¿Trae bench_offers el campo expires_tick? ¿Cuál es la curva de puntos entre la mitad y el top 3? ¿Cómo se reparten bench_points y mm_points?** → Grabar el libro completo del primer banco sin hacer nada distinto de greedy (o con el puesto) y leer bench_points y market al acabar.
12. **¿Cuál es el precio mínimo real de El Chato para una rara con pasos constantes de 3–4 P?** → Regatear sin aceptar (un hilo sin aceptar no cuesta puntos). Nunca contraofertar por debajo de su final.
13. **¿Venden t03 (LAT-10 #1) o t01 (LAT-09 #1)?** → Oferta dirigida con caducidad corta a ≤ valor − margen; si no responden en 30 ticks, abandonar.
14. **Multiplicadores de RET y CHA de los rivales.** → Leer en el feed (sin clave, ≤ 1/s) las pujas y ventas `card:RET-xx` entre las 09:00 y las 10:00.
15. **¿Cuánto dura el aviso de cambio de comisión con ticks de 30 s (2 ticks o 2 minutos)?** → Mirar effective_tick en el primer venue.fee_announced del sábado.
16. **¿Qué regla de tratos da acceso anticipado al nivel 3?** → Esperar a level.announced y leer GET /api/levels.

---

## Para el sábado: qué hacer con esto (resumen operativo)

- 08:55–09:05: solo lecturas sin clave para decidir la lectura del reloj (pregunta 1). No arrancar run_loop hasta corregir sell_dups/PROTECT y cancelar una oferta de LAT-01 y una de LAT-05 (lo hace el equipo con la clave).
- Abrir el sobre del sábado en cuanto llegue, antes de comprar nada (hecho clave 4).
- Con dealers, solo tratos que sean ganancia a valor total; nunca sobres; infrecuentes de RET a la Abuela a ≤ 25; raras de RET a El Chato solo por debajo de 91.
- La carta que cierra una página (LAT y RET) se compra a un equipo, nunca a un dealer.
- Vender repetidos publicando (sin comisión), no aceptando.
- Venue: solo con broker supervisado y caja suficiente; si no, el puesto gratuito.
- Duelos: no salirse nunca del límite, releer antes de aceptar, pasar el tick a step() y hacer el experimento de reactividad.
