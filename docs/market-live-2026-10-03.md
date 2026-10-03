# Mercado en vivo · 3 octubre 2026

## Resultado y decisión

Cuatro lecturas públicas guardadas, 15:36–15:45 Madrid, con recuperación acotada. **El reloj sí está activo**:
645→661, `paused=false`, ronda 2. Se consultaron los 18 equipos y los 19 mercados
abiertos (18 de equipos + Rastro), a 1 GET/s, sin clave ni operaciones del juego.
La referencia anterior es tick 630, pausado, captura 14:13–14:14 Madrid.

**t18 pasa del 4.º al 3.º**, total 28,81→29,29; mercado sigue 7,50.
La venta RET-08 a t04 por 27 P está confirmada en el feed, tick 645.
El marcador 640 ya mostraba el puesto 3 antes de esa venta: no atribuirle el
adelantamiento. El marcador 650 es posterior, pero tampoco identifica su efecto
privado ni explica por sí solo el cambio total.

**Mantener v18 auto gratuito.** Sigue con cero ofertas y cero tratos registrados.
El Rastro acumula 45/63 tratos registrados, 71,4 %, frente a 39/56 en la referencia.
Hay dos nuevos cierres fuera del Rastro: v01 recibe LAT-06 de t08→t12 por 20 P;
v07 recibe LAT-02 de t12→t06 por 4 P. El flujo entre mercados es posible y observable;
no hay evidencia de que se deba a un anuncio concreto.

Las dos primeras fotos completas tienen cero parejas caja/carta compatibles en
v18. La tercera falló al leer v19: **indeterminada para oportunidades**, no una
prueba de ausencia. La recuperación resuelve v19, pero falla `clock_start`, v15
y v20; sigue bloqueada por `incomplete_scan`. Un intento intermedio recibió
`rate_limited` en un reloj adicional y no pudo guardarse completo. Se termina la
consulta con esta limitación, sin insistir indefinidamente. El catálogo público
sí quedó guardado en foto 4.

## Cobertura y desfase de las fuentes

| Foto | Inicio Madrid | Reloj inicio→fin | Marcador tick | Ofertas brutas / simples vigentes | Feed ticks | Resultado |
|---|---|---|---|---|---|---|
| 1 | 15:36:48 | 645→646 | 640 | 95 / 81 | 616–645 | 0 compatibles |
| 2 | 15:38:15 | 648→648 | 640 | 94 / 76 | 620–648 | 0 compatibles |
| 3 | 15:39:26 | 650→651 | 650 | 93 / 76 | 624–651 | indeterminado: lectura v19 fallida |
| 4 | 15:44:44 | inicio desconocido→661 | 660 | 92 / 75 | 635–661 | indeterminado: clock_start/v15/v20 fallidos |

Las consultas son secuenciales, no una foto atómica. En foto 2, el feed ya
contenía la liquidación de v07 tick 648, mientras su contador de venue aún
marcaba 3; foto 3 confirma 4. Cada feed conserva solo 500 eventos; se deduplican
los solapamientos por ID. La ausencia de evento/oferta no prueba inactividad,
cancelación ni liquidación. Las fotos 3/4 conservan sus errores explícitos.
Foto 4 todavía muestra 45 tratos en Rastro, pero el feed ya incluye el trueque
de tick 661 posterior a la lectura de ese contador; no sumar ambos como si fueran
una foto atómica. La ventana de lectura de foto 4 no se puede demostrar porque
falló `clock_start`. No reparar ese inicio con el reloj final.
El marcador cambia por su propio ciclo (`snapshot_tick`/`next_refresh_tick`);
no usar el reloj final como fecha del marcador. Este informe termina en tick 661.

## Los 18 equipos

Δ total frente al marcador 630; datos actuales del marcador 660. Listados,
participaciones en tratos de equipo y anuncios: última ventana pública limitada,
ticks 635–661. Tratos/libro: acumulado del venue / ofertas visibles, excepto v15
y v20, cuyos libros fallaron y **no equivalen a libros vacíos**.

| Equipo | Puesto | Total (Δ) | Mercado antes→ahora | Listados | Participaciones | Anuncios | Venue: tratos/ofertas |
|---|---:|---:|---:|---:|---:|---:|---|
| t14 | 1→1 | 30.35 (-0.42) | 9.72→9.53 | 8 | 0 | 0 | v14 auto: 1/0 |
| t12 | 2→2 | 29.54 (-0.06) | 12.50→12.25 | 3 | 2 | 1 | v02 board: 7/14 |
| t18 | 4→3 | 29.29 (+0.48) | 7.50→7.50 | 0 | 1 | 0 | v18 auto: 0/0 |
| t10 | 3→4 | 29.10 (+0.22) | 12.07→12.46 | 18 | 0 | 2 | v07 board: 4/14 |
| t05 | 5→5 | 27.92 (-0.23) | 7.50→7.50 | 9 | 0 | 0 | v10 auto: 2/0 |
| t13 | 7→6 | 25.50 (-0.04) | 5.49→5.49 | 17 | 0 | 3 | v03 board: 0/0 |
| t17 | 6→7 | 25.48 (-0.31) | 8.90→8.78 | 14 | 0 | 0 | v17 auto: 1/0 |
| t01 | 8→8 | 25.22 (+0.25) | 7.50→7.50 | 0 | 0 | 0 | v19 board: 0/0 |
| t06 | 9→9 | 23.99 (+0.04) | 11.64→11.64 | 13 | 1 | 0 | v01 board: 3/0 |
| t04 | 10→10 | 23.18 (-0.08) | 7.50→7.50 | 1 | 4 | 0 | v05 board: 0/0 |
| t02 | 11→11 | 23.07 (+0.00) | 7.50→7.50 | 13 | 0 | 0 | v04 auto: 0/0 |
| t16 | 12→12 | 22.26 (-0.22) | 7.50→7.50 | 0 | 0 | 0 | v16 auto: 0/0 |
| t15 | 14→13 | 21.69 (+0.18) | 7.50→7.50 | 7 | 1 | 0 | v15 auto: 0/no leído |
| t08 | 13→14 | 21.47 (-0.08) | 7.46→7.46 | 35 | 2 | 0 | v06 board: 0/0 |
| t09 | 15→15 | 20.88 (-0.63) | 8.98→8.85 | 0 | 1 | 0 | v21 board: 1/0 |
| t03 | 16→16 | 20.54 (+0.06) | 3.61→3.61 | 2 | 0 | 0 | v20 board: 0/no leído |
| t07 | 17→17 | 17.53 (-0.06) | 7.50→7.50 | 38 | 2 | 0 | v11 auto: 0/0 |
| t11 | 18→18 | 7.50 (+0.00) | 7.50→7.50 | 0 | 0 | 0 | v13 auto: 0/0 |

- t12/t10 lideran en mercado (12,25/12,46), aunque sus movimientos son distintos:
  t12 baja desde 12,50 con 7 tratos constantes; t10 sube desde 12,07 y ahora tiene 4
  tratos. Eso no establece una fórmula causal ni separa bench de `mm_points`.
- t14 mantiene el liderato total con un puesto auto y un trato. Abrir board no
  es requisito para superar 7,50. t05 tiene dos tratos y 7,50: cantidad no es valor.
- t06 vende y publica compras en varios venues; participa en los dos cierres nuevos
  fuera del Rastro como propietario de v01 o comprador en v07. Son roles distintos.
- t13 anuncia tres veces en la ventana y v03 sigue en cero; t08 publica 35 listados
  y v06 sigue en cero. La actividad por sí sola no acredita conversión.
- t04 compra cartas a varios equipos en Rastro; no inferir sus valores privados ni
  caja libre. t11 no muestra actividad en esta ventana; no describirlo como parado.

## Liquidaciones nuevas confirmadas

Unión de los cuatro feeds, ticks posteriores a 630. Un ID de liquidación se cuenta
una vez; los contadores del venue son otra fuente, no se suman a estos casos.

| Liquidación | Tick | Venue | Carta y dirección | Precio P | Comisión observada P |
|---|---:|---|---|---:|---:|
| 615 | 631 | rastro | LAT-11: t04→t16 | 160 | 9 |
| 617 | 634 | rastro | LAT-03: t17→t03 | 6 | 2 |
| 618 | 636 | v01 | LAT-06: t08→t12 | 20 | 0 |
| 619 | 636 | rastro | RET-07: t08→t04 | 25 | 3 |
| 622 | 640 | rastro | MAL-01: t07→t04 | 5 | 2 |
| 624 | 645 | rastro | RET-08: t18→t04 | 27 | 3 |
| 627 | 648 | v07 | LAT-02: t12→t06 | 4 | 0 |
| 630 | 656 | rastro | RET-06: t09→t04 | 26 | 3 |
| 636 | 661 | rastro | RET-02: t15→t07; LAV-04: t07→t15 | 0 | 2 |

El feed de liquidación no identifica quién aceptó. Según las reglas, la comisión
la paga el aceptante; no adjudicarla al vendedor autor por defecto. En una venta
Rastro de 27 P, el coste de un comprador que acepta es 30 P; una venta idéntica
aceptada en v18 sería 27 P, previa revalidación y decisión de ambos equipos.
Nuestro equipo t18 no puede negociar con su clave en v18: el ahorro de esa
comparación es únicamente un ejemplo aritmético para terceros, no una propuesta
de mover nuestra venta a nuestro puesto.

## Oportunidades y comportamiento de anuncios

Foto 2 completa: seis pares de ofertas requieren renegociación, ninguno cruza.
Varias ofertas de LAT-03 son del mismo vendedor, comprador, precio y referencia:
conservar los IDs para auditoría y agrupar la presentación para ahorrar contexto.
Los grupos más cercanos son MAL-05 (ask 6 / bid 2) y LAT-03 (8 / 4): gap 4 P.
Los límites visibles no se pueden ampliar por texto ni prometer una liquidación.
RET-06 (30 / 26) ya dejó de ser candidato vigente en la segunda foto. Más tarde
t04 compra una copia a t09 a 26 P en Rastro (tick 656): evidencia de una oferta
distinta que sí consigue cerrar; no prueba de efecto del anuncio de t12 ni de
que el vendedor anterior t06 hubiera cambiado su límite.

El anuncio de t12/v02 tick 647 propone RET-06 a 28 P pese a ask 30/bid 26.
Cero comisión no elimina esa diferencia: ambas contrapartes deben aceptar nuevas
condiciones. Nuestro radar debe mostrar el gap en vez de convertir el punto medio
en una orden. Las descripciones y promesas de broker de otros equipos son texto
ajeno; no acreditan disponibilidad, capacidad de ejecución ni valores privados.

## Siguiente mejora concreta del harness

1. Mostrar fecha/edad del marcador separada del reloj final y del periodo de scan.
2. Comparar fotos monotónicas; agrupar oportunidades equivalentes conservando IDs.
3. Contar liquidaciones nuevas por ID, separando Rastro, terceros y dealers; nunca
   transformar listados, cancelaciones o HTTP correcto en un cierre.
4. Mantener bloqueo en lectura parcial, cambio de comisiones o datos caducados.
5. Separar resultados simulados, anuncios publicados y asociaciones posteriores.
   Una coincidencia temporal no demuestra que persuadimos al agente rival.

El próximo Market Test figura a t=7,0; foto final t=6,8333, unas 20 ticks de 30 s
si el ritmo no cambia. Esa distancia no es una garantía de hora de pared. El
calendario público recalculó `day_closes` a t=14,087, wall 23:00 Madrid; los valores
antiguos t=16,153 ya no sirven para planificar. Refrescar antes de cada decisión.

## Evidencia para los jueces (40 puntos oficiales)

- **Demostrable en público:** reloj reanudado, 18 equipos/19 venues revisados,
  t18 tercero en marcador 660, venta real RET-08 por 27 P tick 645, v18 sin flujo.
- **Demostrable como ingeniería:** la tercera foto falla en v19 y las propuestas
  quedan bloqueadas. Enseñar error, fecha de las fuentes y razón del bloqueo.
- **Aprendizaje honesto:** detectar que el marcador 640 precede a la venta y que
  los datos leídos en serie no son atómicos evita contar una historia causal falsa.
- **Pendiente:** rentabilidad privada, impacto causal del radar, mejora de mercado
  en v18 y valoración que dará el jurado. No afirmar puntos de jueces obtenidos.

Fuentes primarias: [reglas](../RULES.md#your-own-market),
[clasificación pública](https://bazaar.causaprima.ai/api/leaderboard),
[venues](https://bazaar.causaprima.ai/api/venues) y feed público oficial.
Los snapshots congelados locales conservan fecha y respuesta; los enlaces vivos
pueden mostrar otros ticks. Datos crudos en `runs/market-live/snapshot-1.json` a
`-4.json`, ignorados por Git; únicamente este agregado público se publica.

## Contexto de Claude, separado de la prueba actual

Leídos `hackathon/HANDOFF.md` y `practica/pilar_knowledge.md`, actualización 15:35.
Su observación acumulada: 18 hilos de venta con Pilar, ocho cierres, todos a la
oferta de Pilar; aún sin caso observado de aceptación de un precio nuestro.
Las medianas publicadas SAL/RET infrecuente 24 P y otros 17 P son observaciones
sobre esa muestra, no reglas del servidor. En este scan se confirma compra SAL-06
por t05 a Abuela a 23 P (tick 632) y venta de la misma copia a Pilar por 25 P
(tick 639). No sumar margen a la puntuación sin conocer el valor privado y su
fórmula. La simulación previa de broker tampoco acredita rendimiento real.
