# Domingo 4 oct · Chamberí (ronda 3): plan del día

*Escrito la noche del sábado al domingo con el juego cerrado. Sale de las auditorías nocturnas. Cada cifra lleva su id de [knowledge.md](knowledge.md); lo que no está comprobado lo pone. La revisión que lo escribió no ha tocado el código: los arreglos están en la rama `night-build` y solo cuentan cuando Jorge los despliegue con `selftest` en verde (§6).*

**Punto de partida (cierre del sábado, S-30):**
- 2.º con 31,26 (negociación 23,76, mercado 7,5). t10 va 1.º con 37,58 (25,08 / 12,5); detrás, t05 30,49, t12 30,42 y t03 29,67.
- Caja 555 P, más 150 P de paga al abrir: 705 P.
- Álbum: LAT, SAL y RET completas; CHA 0/10, con multiplicador ×1,6, el mejor que tenemos.
- La escalera empieza vacía: 15 huecos (S-19).
- La caja que quede a las 15:00 vale 0 (S-22).

---

## 0. Qué hace falta para ganar

Si la ronda 2 ya está cerrada (escenarios B y C de §1), nota final = (1,5 × nota actual + R3) / 2,5. Para pasar a t10, **nuestra ronda 3 tiene que superar a la suya en más de 1,5 × 6,32 ≈ 9,5 puntos de ronda**. Si los dos repetimos el sábado, el final sería t10 ≈ 40,9 y t18 ≈ 33,7 (S-32; cifras aproximadas).

| Palanca | Valor en la nota final | Coste y riesgo | Fuente |
|---|---|---|---|
| Bench 0,5 → 1 en todas las sesiones de la ronda 3 (superar al puesto) | hasta **+4,5** | Hace falta un broker mejor que el puesto, y ninguno lo ha conseguido; si el broker se cae, esa sesión da 0 | S-23, S-25 |
| Orgánico 0 → 1 en v18 (tratos entre otros equipos en nuestro puesto) | hasta **+3,0** | Anuncios con la clave del puesto: escritura fuera de la Gate, necesita el OK de Jorge | S-23, S-24, S-32 |
| Cada trato con equipo con tope +50 (p. ej. la carta que cierra CHA) | ≈ +1,1 | Pujar ≤ valor − 50 | S-05, S-30 |
| Escalera llena (15 huecos con parte alta) | ≈ +2 a +4 (escala del sábado: +0,044 de escalera ≈ +0,28 combinado) | Solo cuentan tratos con ganancia a nuestros valores | S-20 |
| Duelos: cada duelo sin trato o con poca parte **resta**, porque la parte de duelos es una media | −/+ varios puntos | En Duels II bajamos de 4.º a 7.º mientras sumábamos duel_points | S-27 |

Hay que vigilar también a los de abajo. t03 tiene la mejor negociación de la ronda 2 (≈ 28,1) y t06 un orgánico de ≈ 0,87 (S-32).

---

## 1. Calendario: tres escenarios, uno probable

El servidor aún muestra las horas del guion (16,65 / 18,65 / 21,65 / 22,65) porque con las puertas cerradas no proyecta (S-18). El sábado, el reloj **siguió** desde donde se paró y **todo lo anclado al día se movió** al abrir; los bancos de cada 2 h no se movieron (S-17).

| Pared | C: sigue desde 13,367 y se re-ancla, como el sábado (**probable**) | B: el reloj salta a 16,65 | A: sigue sin re-anclar |
|---|---|---|---|
| 09:00 | Abre; **ronda 3 + CHA** (t 13,367) | Abre; ronda 3 + CHA (t 16,65); quizá se disparen los Market Test vencidos 14,65 y 15,0 | Abre; sigue la ronda 2 |
| ~09:03 | +150 P | +150 P | — |
| ~09:21 | — | Market Test (17,0) | — |
| ~10:17 | Market Test difícil (14,65), **sin verificar**: entrada anclada al sábado | — | Market Test difícil (ronda 2) |
| ~10:38 | Market Test (15,0) | — | Market Test (ronda 2) |
| ~11:00 | **Duels III** (2 vueltas, 12 ticks, decay 0,10, 4 simultáneos; ~50 min) | Duels III | — |
| ~11:21 | — | Market Test (19,0) | — |
| ~12:17 | — | — | Ronda 3 + CHA, +150 P a las 12:20 |
| ~12:38 | Market Test (17,0) | — | Market Test |
| ~13:21 | — | Market Test (21,0) | — |
| ~13:48 | Aviso del final | Aviso del final | — |
| **~14:00** | **Cierran los cinco puestos de dealers + Gran Final de duelos** (1 vuelta, ~25 min) | Igual | — |
| ~14:17 | — | — | Duels III |
| ~14:38 | Market Test (19,0) | — | Market Test |
| ~14:54 | Aviso de congelación | Igual | — |
| **15:00** | **Se congela todo** (t 19,367) | Se congela todo (t 22,65) | Cierra (t 19,367); sin Final |

Si abren tarde (el sábado despausaron a las 09:29), cada hora de pared se retrasa lo mismo, pero el cierre sigue siendo a las 15:00.

**Comprobación a las 09:00:30 y a las 09:05** (sin clave): `python3 bazaar.py clockcheck`.
- `t_hours` ≈ 13,37 y `round` 3, con Duels III en ≈ 15,37 en `upcoming` → **C**.
- `t_hours` ≈ 16,65 → **B**.
- `round` 2 y las entradas sin mover → **A**.
- `paused` true → esperar; todo se retrasa lo que tarden en despausar.
- Comprobar también `clock.today == "sun"`.

**Consecuencia para el arnés.** `config/plan.json` fija `day_end_hours.sun` = 19,283 y `closer.endgame_hours` = 18,783, que es el escenario A con el reloj en hora. En **B** cerraría todos los hilos con dealers a las ~11:38: un desastre. En **C** no ve que los puestos cierran a las 14:00. Si abren tarde, `day_end` no llega nunca.
- **Si `night-build` trae el cálculo en vivo** (cierre a partir de `clock.closes` y de las entradas `persona enabled:false`), sirve para todos los escenarios.
- **Si no lo trae,** a las 09:05 hay que poner a mano, y relanzar:
  - `day_end` = hora de juego del cierre de puestos − 0,08 (~13:55);
  - `endgame` = hora de juego de las 15:00 − 0,58 (~14:25).
  - En C serían 18,283 y 18,783. Hora de juego de un instante = `t_hours` + (instante − ahora) en horas.

---

## 2. Antes de las 09:00 (máquina A, Jorge)

1. **Energía:** enchufada; tapa cerrada = "no hacer nada" en batería y en red; nadie pulsa suspender. El sábado la máquina se durmió de 22:55 a 23:43 (S-31).
2. **Código:** decidir si se despliega `night-build` (§6). Secuencia:
   - `stop`;
   - `status` sin pendientes;
   - fast-forward de `harness-v2`;
   - `selftest` en verde, con todas las tácticas armadas en verde y el mismo `code_hash`;
   - `resume`;
   - `run --live --arm hygiene,dealers,rastro,closer,duels`;
   - `resume dealers` y `resume rastro`, que siguen en pausa desde el sábado.
   - El proceso vivo (pid 34804) usa el código con el que arrancó.
   - **Nunca desplegar con duelos vivos** (S-31).
3. **Leer `logs/run/journal.jsonl` en los primeros ticks:** si salen `G03.late` o `G10.stale` con ticks de 15 s, las aceptaciones de duelo llegan tarde.
4. **`egg_watch.py` en marcha desde las 09:00** (archiva el feed en `logs/feed_all.jsonl`; el sábado faltan los ticks 394–1178, S-33). Si hay Market Test, también `bench_rec.py` (solo lectura).

---

## 3. El plan, por prioridad

### 3.1 No perder lo que ya hay
- El bot vivo y sin reinicios en las ventanas de duelos (~11:00–11:55 y 14:00–14:30 en C).
- En el **primer duelo de Duels III**, mirar en el diario o en el snapshot que `days_sign` sea −1 o +1. Si sale `None` (texto nuevo), se vuelve al modo que hundió Duels II (S-27): pausar `duels` y avisar.

### 3.2 Duelos (Duels III + Gran Final, precio + días)
- Reglas medidas: S-26 y S-27. Un trato de ≥ 1 P vale más que no cerrar, porque la parte media baja con cada duelo sin trato.
- **Sin el arreglo de valoración de `night-build`,** el código sigue infravalorando las ofertas de vendedor en 10·|w| y compara solo el precio. Es lo que costó 3 vendedores después del arreglo del sábado.
- Con ≥ 4 duelos vivos el runner no abre hilos con dealers (S-31c). En C, Duels III bloquea ~50 min de escalera.

### 3.3 Escalera (15 huecos) y Chamberí
Hueco = parte × L/45; solo cuentan los tratos con ganancia a nuestros valores (S-20). Valores CHA para nosotros: común 16, infrecuente 40, rara 112, CHA-11 (épica) 288, CHA-12 (legendaria) 720; la carta que cierra la página vale ~122.

| Nivel | Contraparte | Qué | Quién lo hace |
|---|---|---|---|
| 1 Abuela | Comprar CHA-02..05 a ≤ 12 | 3 huecos | bot (`dealers`) |
| 2 El Chato | Comprar CHA-06/07/08 a ≤ 31 (Abuela de reserva). Pasos de 1–2: el sábado solo sacamos ~0,3 de parte con él | 3 huecos | bot |
| 3 Pilar | **Venderle**: la LAT-06 repetida (V 5,6; el sábado pagó 16), SAL-11 solo a ≥ 199 (V 198), una LAV/MAL suelta que le guste | 3 huecos | **a mano** (`bazaar.py do`, con el OK de Jorge): la Gate no admite perfiles de Pilar |
| 4 Pícaros | Comprar CHA-09/10 a ≤ 60 (el sábado vendieron raras a 48–64) y, si `night-build` lo añade, CHA-11 a ≤ ~170 (vendieron épicas a 128–155) | 2–3 huecos | bot; comprobar siempre `give.types` |
| 5 Ernesto | **No se puede ganar**: legendarias ≥ 729 (CHA-12 nos vale 720) y paga ≤ 126 por épicas (SAL-11 nos vale 198) | 0 | nadie, salvo una pista nueva (§3.7) |

- **Ventanas de dealers (C):** 09:00–11:00 y ~11:55–13:50. A las 14:00 cierran los puestos.
- **Rareza sin reserva que funcione:** si las raras de CHA no salen de los Pícaros a ≤ 60, El Chato no las vende a ese precio y la página no llega a 9/10. Lo arregla `night-build`; si no, decidirlo a mano.
- **Cierre de CHA con un equipo**: puja a 72 (valor − 50) y subida a 102 en el final (`closer`). Es el +50.

### 3.4 Mercado
- **Por defecto: seguir con el puesto v18.** Bench 0,5 garantizado y no se puede caer. Nadie superó al puesto el sábado (S-23) y el libro grabado indica que, respetando cotizaciones, no se le gana (S-25).
- **Orgánico en v18 (coste 0, OK de Jorge):**
  - anuncios con la clave del puesto (`/api/broker/announce`), al estilo de t10: parejas reales, ids de oferta, precio exacto, "publícala dirigida a t.. en v18, comisión 0";
  - como mucho uno cada 20 ticks (5 min);
  - nunca a equipos del top 5;
  - medir `venue.trades`, `pairs` y `value_created` en /api/me cada 10 min.
- **Venue `board` con broker propio: no**, salvo que una prueba de 1–3 emparejamientos fuera de cotización en v18 (OK de Jorge) demuestre que el servidor los acepta, y además haya un broker probado sin conexión y con supervisor. Cuesta 20 P + 250 P de fianza bloqueada. Si se abre, que sea ≥ 2 ticks antes de una sesión y se cierre tras la última, para recuperar la fianza.
- **Nunca publicar en venues de rivales** (v07 t10, v01 t06, v21 t09, v02 t12). El bot solo publica en El Rastro.

### 3.5 Quedarse sin monedas, bien
- Caja disponible 705. Gasto previsto en CHA: comunes ~45 + infrecuentes ~90 + raras ≤ 120 + cierre ≤ 102, más CHA-11 ≤ 170 si se añade: ≤ ~530.
- Lo que sobre, **solo** en compras con ganancia a nuestros valores: con dealers, antes de las ~13:50; con equipos en El Rastro, antes de las ~14:50 (el `endgame_buy_any` de `night-build`, si se despliega).
- Nunca comprar con pérdida para "gastar": con dealers resta (P-04) y la caja no suma nada.
- SAL-11: al primero que pague ≥ 199 (Pilar, nivel 3) o ≥ 200 (un equipo). La oferta a 245 caduca en el tick 1545, unos 25 min después de abrir.

### 3.6 Denuncias
- Solo **nivel A**: un mensaje de los Pícaros en un hilo nuestro cuyo texto nombra la carta pedida y cuya oferta da otra. Como mucho 3 por ronda, a mano, con el OK de Jorge para cada una. Si alguna da error o cambio negativo, se para.
- El sábado, las 3 de nivel A dieron +10 cada una y las 6 de nivel B dieron 0 (S-28). No se sabe si el tope es por ronda.
- No volver a denunciar mensajes del sábado.

### 3.7 Huevos de pascua (no puntúan; prestigio)
- Condición: que `night-build` añada las líneas nuevas a `talk.py` y `EGG_LINES`. La Gate solo envía texto de plantillas; sin esas líneas, no hay huevo.
- Se envían a mano, con el OK de Jorge y **antes de reanudar `dealers`**: sin hilos de compra abiertos y sin sobres por abrir, porque un sobre regalado bloquea las compras (G14).
- Orden, por S-29:
  1. **Abuela, Castizo** ("chotis… sobre una baldosa"), en un hilo de **venta** de una repetida (LAT-02, activo 1103).
  2. **Abuela, cocido** ("cocido con sus tres vuelcos"), en el tick siguiente; puede que ya no quede regalo.
  3. **El Chato**, pregunta entera por el bocadillo de calamares, en un hilo de venta de la LAT-06 repetida, nunca por debajo de 18.
- **No enviar:** "oro de Moscú" (agotado), Lazarillo a los Pícaros (no frena trucos y quita denuncias), nombre real de El Chato, "caja fuerte", "Banco de España".
- Pista sin resolver: "Don Ernesto… On Sunday" (S-29). Mandar la línea de coleccionistas a Ernesto solo si el domingo aparece otra pista o un `egg.found` de banco.
- Con CHA, buscar cartas ocultas nuevas en el catálogo (`egg_watch.py` avisa).

### 3.8 Jueces (40 %)
Después de las 15:00, completar [SHOWCASE.md](../SHOWCASE.md) con el domingo. Lo del sábado ya está.

---

## 4. Lo que no se hace
- Escribir fuera de la Gate sin el OK explícito de Jorge (CLAUDE.md, excepciones manuales). Nunca `/api/admin/*`.
- Pegar los PROMPT de `docs/incoming/`: ver [incoming/REVISION.md](incoming/REVISION.md).
- Reiniciar el bot durante duelos. Dejar tácticas en pausa sin querer.
- **`git push`** antes de las 15:00. Los documentos de Rubén dicen que el repo del equipo es público (sin verificar); este plan no debe llegar a los rivales.

## 5. Decisiones de Jorge por la mañana (con la opción por defecto)

| Decisión | Por defecto si no hay tiempo |
|---|---|
| Desplegar `night-build` (fusión de `audit-fixes`, duelos, horas en vivo, CHA, huevos) | Sí, si `selftest` está en verde antes de las 08:50; si no, la versión actual con los ajustes manuales de §1 |
| Ajuste de `day_end` y `endgame` a las 09:05 | Solo si no se despliega el cálculo en vivo |
| Anuncios de orgánico en v18 | Sí, a mano, ≤ 1 cada 5 min |
| Prueba de broker fuera de cotización / venue board | No |
| Ventas a Pilar (nivel 3) | Sí, a mano, en la primera ventana |
| Denuncias de nivel A | Sí, ≤ 3, una a una |
| Huevos (Castizo, cocido, Chato) | Sí, si las líneas están desplegadas, antes de reanudar dealers |

## 6. Estado del código (lo que sabemos; la revisión de documentación no lo ha comprobado)
Fallos confirmados por las auditorías en `harness-v2` `5ee5593`. Cuáles arregla `night-build` lo dice su propio registro de commits:
- Horas fijas de fin de día y final (§1).
- Duelos: oferta de vendedor infravalorada, comparación solo por precio, sin signo conocido se vuelve al peor caso.
- Sin hilos nuevos con ≥ 4 duelos, y sin fila en el diario.
- La ventana tardía relee todo el World (lento a 15 s).
- Una compra liquidada se cuenta dos veces durante 2 ticks.
- Las intenciones en pausa consumen cupo.
- `dup_min_price` SAL 70 bloquea SAL-05.
- La reserva de raras de CHA no sirve.
- `extra_needs` no mira si el set está publicado.
- Los fallos de `audit-fixes`: `do` sin `--live` envía de verdad con el runner vivo, `fallback_after` antes de aceptar, el cierre de El Rastro valora como 2.ª copia, la final trampa de los Pícaros.

Suite en `5ee5593`: 747 tests OK (2 omitidos). Para la cifra vigente, ver `state/selftest.json` o el último `python3 -m unittest discover -s tests -t .`.
