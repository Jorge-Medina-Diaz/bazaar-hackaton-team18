# Revisión de los documentos de Rubén (sáb 3 oct, 22:30–22:55)

*Revisión nocturna, dom 4 oct, solo con lecturas: snapshots de las 23:59, el feed fusionado (con huecos), el diario, `untrusted.jsonl`, `eggs.jsonl` y los hilos. Los originales se quedan en esta carpeta tal cual, con un aviso arriba. **Son datos, no instrucciones**: sus PROMPT no se pegan en ninguna sesión, porque reenviarían denuncias, escribirían fuera de la Gate y gastarían el "oro de Moscú", que ya está agotado. El plan vigente está en [../plan-domingo.md](../plan-domingo.md) y los hechos en [../knowledge.md](../knowledge.md).*

Claves: **OK** = correcto · **MAL** = falso · **HECHO** = ya se hizo · **SIN VERIFICAR** = no se ha podido comprobar.

## EL_ORO_DE_MOSCU.md

| § | Afirmación | Veredicto | Dato |
|---|---|---|---|
| 1 | Clasificación del cierre: t10 37,58 (25,08 / 12,5 / 62 tratos), t18 31,26 (23,76 / 7,5 / 40), t05 30,49, t12 30,42, t03 29,67, t06 28,76, t14 27,67, t17 25,82 | **OK** | `leaderboard.json` de las 23:59 |
| 1 | Nuestra negociación es la 2.ª mejor | **OK** | 23,76; solo t10 está por encima |
| 1 | En el tramo desde el tick 559: t18 11 tratos, t10 32, t12 31, t06 36 | **SIN VERIFICAR** | El feed tiene huecos de ~250 ids cada 5 ticks |
| 1 | "El mercado está fijo en 7,5 porque t18 no tiene venue" | **MAL** | Tenemos el puesto v18 desde el tick 201: bench 0,5, eficiencia 0,854. Lo que falta es orgánico (S-23, S-24; Refutado #73) |
| 2a | Sin tratos la nota baja sola; caímos al 7.º | **OK** | Es la ponderación por fase de la ronda (P-16); 28,2 y 7.º en el tick 1320 |
| 2a | LAT-10 a 72 → +1,92; SAL-10 a Pilar → +0,82 | **OK con matiz** | LAT-10 sumó +50 neg (medido). Los +0,82 incluyen 2 denuncias (+20 neg) |
| 2a | "Repartir los tratos durante el día" | **MAL** | La nota final no depende de cuándo. Lo que obliga a ir pronto es el cupo por hora y el cierre de los puestos (Refutado #84) |
| 2b | Un nivel vacío cuenta cero; el Banco es el que más pesa | **OK** | Hueco = parte × L/45 (S-20) |
| 2b | "No tenemos tratos con El Chato en la ronda 2" | **MAL** | 2 tratos, ticks 206 y 213, fuera de su tramo (Refutado #80) |
| 2b | Solo t06, t08 y t16 tienen trato con el Banco | **OK** para t06 y t16; **SIN VERIFICAR** para t08 | Huecos del feed |
| 2b | "El domingo, 1–3 tratos con el Banco y El Chato" | **Incompleto** | La escalera se reinicia: hay 15 huecos (S-19). Con Ernesto no hay trato con ganancia posible (S-21; plan-domingo §5.1) |
| 2c | Los Pícaros venden épicas a 128–167 | **Casi**: liquidadas a 128–155; 167 y 187 eran precios pedidos | S-21 |
| 2c | Nuestra SAL-11: comprada a 139, vendida a Pilar a 199 | **OK** | Diario, ticks 925 y 994 |
| 2c | Reventas t06 RET-11 +79, t08 MAL-11 +45 | **MAL** (brutas) | Netas tras comisión: +67 y +34 |
| 2c | "Revender épicas da beneficio" | **MAL como puntuación** | La caja no puntúa; con dealers comprar suma min(0, V − p) (Refutado #75) |
| 2c | Revender al Banco da pérdida (113–120) | **OK con cifra corregida** | Ernesto llega a 126 de final, y aun así por debajo de nuestro valor (198) |
| 2d | Los Pícaros cambian la carta; a t18 no le colaron ninguna (9 intentos) | **OK** | S-21 |
| 2d | "A todo el mercado solo le colaron una (a t04)" | **SIN VERIFICAR** | Feed con huecos; hay otros candidatos (t16, tick 1165) |
| 3 | "`adjustments` vacío: nadie ha denunciado" | **MAL** | Denunciamos 9 y siguió vacío (S-28; Refutado #74) |
| 3 | Las 9 denuncias: ids, hilos, ticks y cartas | **OK los datos**; **HECHO** el envío | 22:30–22:37: 8663, 9460 y 9859 → +10 cada una; las otras 6 → 0 (S-28). **No reenviar** |
| 4 | Banco "oro de Moscú" → LAT-13 | **Agotado** | LAT-13 1/1, de t02 desde el tick 1021 (S-29; Refutado #78). **No enviar** |
| 4 | Abuela chotis → Castizo; la tienen t10, t05, t08 y t02 | **OK** quién la tiene; **probable** el disparador ("chotis") | S-29. La frase exacta del equipo no se ve en el feed |
| 4 | Abuela cocido → carta repetida gratis | **Probable** | t10, t05 y t08 sí; t06 no (¿tope de 3?) (S-29) |
| 4 | Chato "bocadillo de calamares… Plaza Mayor, con caña" → sobre gratis | **Probable** | t10 y t08; las frases parciales fallaron (S-29) |
| 4 | Pícaros Lazarillo → "ese día no te hacen trucos" | **MAL** | Insignia sí (la tenemos, tick 1227); los trucos siguen (Refutado #79). **No reenviar** |
| 4 | "Los huevos pueden pesar en el 40 % del jurado" | **Sin respaldo** | RULES: nunca puntúan (Refutado #85) |
| 5 | El mercado es el 30 %; t10 12,5 y t06 11,87 | **OK** | Pero su ventaja es orgánico, no "tener venue" (S-23) |
| 5 | "Con venue antes de las 10:17 entramos en los Market Test" | **MAL** | Ya entramos con v18. Un `board` solo ayuda con un broker mejor que el puesto (plan-domingo §5.3) |
| 5 | "4 Market Tests el domingo" | **Depende del escenario** | plan-domingo §3 |
| 6 | Horario: CHA 12:17, +150 a las 12:20, Duels III 14:17 | **MAL (probablemente)** | Solo vale si no se re-ancla. El precedente del sábado da CHA 09:00, Duels III ~11:00 y puestos cerrados ~14:00 (S-17; Refutado #77) |
| 6 | "De 09:00 a 12:17 cuenta para la ronda del sábado" | **MAL (probablemente)** | El sábado la ronda cambió al abrir (Refutado #76) |
| 7 | Checklist: denuncias, huevos, venue, Banco, repartir tratos, épicas | **Superado** | Lo vigente es plan-domingo.md §5 y §6 |
| 8 | PROMPT para el agente | **NO EJECUTAR** | Reenvía denuncias ya hechas, gasta el huevo agotado y escribe fuera de la Gate sin el OK de Jorge |
| pie | `practica/SECRETOS.md`, `practica/tablero_web/` | **No están en este repo** | Están en el Mac de Rubén y en la rama `integrate/main-into-harness-v2` |

## PARA_JORGE.md

| § | Afirmación | Veredicto | Dato |
|---|---|---|---|
| — | "Rubén autoriza estas acciones para t18" | **No es un OK** | Solo Jorge autoriza escrituras fuera de la Gate (CLAUDE.md) |
| 1 | `adjustments` vacío = nadie ha denunciado | **MAL** | Refutado #74 |
| 1 | Las 9 denuncias y la tabla de mensajes | **OK los datos**; **HECHO** | Solo las 3 de nivel A puntuaron (S-28) |
| 1 | No denunciar "precio distinto" ni el hilo 1722 del Banco | **OK** | Sigue valiendo |
| 2 | Tabla de huevos | Igual que EL_ORO §4 | Banco: agotado. Pícaros: no reenviar. Castizo, cocido y Chato: probables |
| 2 | Abuela con tema `{"buy": {"pack": "sobre_barrio"}}` | **Innecesario e imposible para la Gate** | Los huevos saltaron en hilos de carta y nuestro Sharp ear en uno de venta; la Gate solo abre temas de carta |
| 3 | "t18 no tiene venue; el Market Test solo puntúa en venues inscritos" | **MAL** | Refutado #73 |
| 3 | Market Test del domingo a las 14,65, 15,0, 17,0 y 19,0 | **OK** en horas de juego | La hora de pared depende del escenario (plan-domingo §3) |
| 3 | t18 2.º con 30,98, empatado con t06; t10 37,74; t06 mercado 11,82 | **Superado** | Snapshot anterior. Cierre: 31,26, t10 37,58 y t06 11,87. El empate no se puede comprobar |
| 4 | Épicas con beneficio; Banco con pérdida | Igual que EL_ORO §2c | Cifras brutas; la caja no puntúa |
| 4 | +1,92 y +0,82 | Igual que EL_ORO §2a | +0,82 con 2 denuncias dentro |
| 4 | Banco: solo t06, t08 y t16 | Igual que EL_ORO §2b | t08 sin verificar |

## JORGE-denuncias-picaros.md

| § | Afirmación | Veredicto | Dato |
|---|---|---|---|
| 1–2 | Contexto y clasificación A/B de los 9 mensajes | **OK** | Era exacta: las A puntuaron y las B no (S-28) |
| 1 | "Nadie ha denunciado; `adjustments` vacío" | **MAL** como indicador | Refutado #74 |
| 1 | Rubén levanta la prohibición de strategy #9 / INV-01 / INV-20 | **Superado** | Las denuncias se hicieron con el OK de Jorge. La regla vigente: denuncias solo a mano y con su OK (CLAUDE.md, strategy §2.1 #9) |
| 3, paso 0 | "El repo es PÚBLICO"; `gh repo edit … --visibility private` o `git push origin --delete …` | **SIN VERIFICAR; NO EJECUTAR** | Es decisión solo de Jorge. Mientras tanto: ningún `push` antes de las 15:00 del domingo |
| 3, pasos 1–5 | Scripts con `bazaar_sdk` directo | **HECHO; NO REPETIR** | Escriben fuera de la Gate |
| pie | `radio.py --watch`, `docs/picaros.md`, `logs/picaros.jsonl` | **No están en este repo** | Rama `integrate/main-into-harness-v2` |
| pie | Para comprar a los Pícaros, aceptar solo si `give.types == ["card:X"]` exacta, también en la final | **OK** | Lo impone la Gate (oferta exacta releída en el tick, INV-05) |
