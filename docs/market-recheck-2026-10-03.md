# Reevaluación de mercado · 3 octubre 2026

Consulta sin clave de todos los mercados abiertos y los 18 equipos, antes de
implementar el radar y repetida después con su propio collector. Foto de las
14:13–14:14 de Madrid; reloj final 630, t=6,575, ronda 2, **pausado**.
Clasificación tick 630. La foto previa de las 13:25 también tenía tick 630:
no interpretar el tiempo de pausa como pérdida de rendimiento del bot.
Los listados pueden cambiar durante la pausa, por lo que se releen los libros.

Fuentes: API oficial `/api/clock`, `/api/leaderboard`, `/api/venues`,
`/api/venues/<id>/offers`, `/api/schedule` y `/api/feed?limit=500`.
La API respondió por el transporte público del repo; el visor de búsqueda web
no pudo abrirla. Se guardaron las fotos y salidas completas en `runs/`, ignorado
por Git. Este documento contiene solo un resumen público.

## Decisión

Mantener el puesto auto gratuito v18 y dirigir la investigación a parejas
concretas. No hay prueba para pagar por sustituirlo por un board: el broker local
pierde contra greedy en la simulación de Claude (500 libros sintéticos, seed 11,
0,8987 frente a 0,9053); tampoco hay ruta de broker activa en GuardedTransport.
La simulación no demuestra cómo iría en un libro real.

El Rastro concentra 39 de 56 tratos registrados (69,6 %); v18 sigue con 0.
El atasco no es únicamente la comisión: **cero parejas de caja/carta identificadas
son compatibles en v18**, excluyendo al dueño t18. Hay cuatro candidatos que
requieren mover límites. No generar mensajes que prometan cierre inmediato.

## Qué observamos de los demás

- t12 y t10: mejores puntuaciones de mercado (12,50 y 12,07), boards con 7 y 3
  tratos acumulados y 15 ofertas cada uno. Eso acredita actividad, no identifica
  qué parte del marcador viene de bench o de valor creado.
- t14: lidera; puesto auto con un trato y 9,72 en mercado. Un board propio no es
  requisito para tener un resultado superior al nuestro.
- t05: dos tratos, 7,50 de mercado. El número de operaciones no permite predecir
  los puntos. t17: un trato, 8,90; tampoco es una relación lineal.
- t13 y t17: 27 listados públicos cada uno en la ventana. t13 anuncia tres veces
  y su v03 acumula cero tratos. Anuncios y republicación no prueban conversión.
- t08: tres anuncios, cero tratos en su v06. Ya ofrece cartas/precios concretos;
  nuestra idea compite con tácticas que otros están usando.
- t06: publica compras en v07 y ventas en Rastro; es un candidato a contraparte,
  pero los precios observados no cruzan. RET-06: pide 30 frente a 26 de t04.
- t07/t15: tres trueques entre ambos en la ventana, además de tratos de t13 con
  t04/t07. Todos esos cinco tratos de equipo están en Rastro; tres son carta por
  carta. El radar inicial no evalúa trueques, una extensión especialmente útil.
- t11: sin listados ni liquidaciones en esta ventana. Esto no prueba que no esté
  jugando: el feed conserva solo los últimos 500 eventos.

El resto se compara en la tabla. No identificamos la configuración, el modelo,
los valores privados, inventario o margen de beneficio de ningún rival.

## Todos los equipos (ventana pública limitada)

| Equipo | Puesto | Mercado | Listados | Tratos equipo | Anuncios | Mercados abiertos: tratos/libro |
|---|---:|---:|---:|---:|---:|---|
| t14 | 1 | 9.72 | 22 | 0 | 0 | v14 auto: 1/0 |
| t12 | 2 | 12.50 | 2 | 0 | 0 | v02 board: 7/15 |
| t10 | 3 | 12.07 | 11 | 0 | 1 | v07 board: 3/15 |
| t18 | 4 | 7.50 | 5 | 0 | 0 | v18 auto: 0/0 |
| t05 | 5 | 7.50 | 15 | 0 | 0 | v10 auto: 2/1 |
| t17 | 6 | 8.90 | 27 | 0 | 1 | v17 auto: 1/0 |
| t13 | 7 | 5.49 | 27 | 2 | 3 | v03 board: 0/0 |
| t01 | 8 | 7.50 | 4 | 0 | 2 | v19 board: 0/0 |
| t06 | 9 | 11.64 | 20 | 0 | 0 | v01 board: 2/0 |
| t04 | 10 | 7.50 | 8 | 1 | 1 | v05 board: 0/0 |
| t02 | 11 | 7.50 | 11 | 0 | 0 | v04 auto: 0/0 |
| t16 | 12 | 7.50 | 7 | 0 | 0 | v16 auto: 0/0 |
| t08 | 13 | 7.46 | 0 | 0 | 3 | v06 board: 0/0 |
| t15 | 14 | 7.50 | 7 | 3 | 0 | v15 auto: 0/0 |
| t09 | 15 | 8.98 | 0 | 0 | 1 | v21 board: 1/5 |
| t03 | 16 | 3.61 | 8 | 0 | 0 | v20 board: 0/0 |
| t07 | 17 | 7.50 | 5 | 4 | 0 | v11 auto: 0/0 |
| t11 | 18 | 7.50 | 0 | 0 | 0 | v13 auto: 0/0 |

## Próximas parejas a revisar

- MAL-05: t17 pide 6 P / t06 ofrece 2 P. renegotiation_required; cambio mínimo 4 P; quedan 26 ticks.
- RET-06: t06 pide 30 P / t04 ofrece 26 P. renegotiation_required; cambio mínimo 4 P; quedan 19 ticks.
- MAL-05: t07 pide 6 P / t06 ofrece 2 P. renegotiation_required; cambio mínimo 4 P; quedan 7 ticks.
- RET-01: t06 pide 12 P / t13 ofrece 2 P. renegotiation_required; cambio mínimo 10 P; quedan 11 ticks.

## Cobertura y cautelas

Se consultaron 19 libros (18 mercados de equipo abiertos y Rastro), 95 ofertas
brutas. Se identificaron 73 cotizaciones simples vigentes; descartes: 10 lotes o
trueques, 11 caducadas/tiempo desconocido y una identidad no resuelta. El feed
público tiene 500 eventos, ticks 604–630, una ventana limitada y no un diario
completo. Los contadores de tratos en la tabla son del venue acumulado; los
"tratos equipo" son participaciones dentro de esa ventana, no totales.

El ahorro de comisión beneficia a quien acepta. La comparación RET-06 no
justifica bajar automáticamente el precio de t06 ni subir el de t04: hacen falta
sus decisiones y lecturas actuales. RET-08 está ofrecida por t18 y queda excluida
como oportunidad para nuestro propio mercado. Los anuncios rivales que atribuyen
una comisión a un vendedor que publica una venta confunden quién acepta; nuestro
borrador indica explícitamente el caso comprador-aceptante.

**Siguiente acción útil:** al reanudarse, refrescar el radar y revisar primero
MAL-05/RET-06 si los precios cambian. Si surge una pareja compatible, el operador
revalida límites y capacidad de publicación y propone la migración. Registrar id
de anuncio, listados y liquidaciones permite medir asociaciones; no causa probada
ni aumento garantizado de puntuación. Mientras no exista pareja compatible,
conservar caja, puesto y atención del operador.

Guía y entrega: [market-harness.md](market-harness.md).
