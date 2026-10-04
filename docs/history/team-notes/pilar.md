# Doña Pilar (nivel 3): estrategia y runbook

*Sáb 3 oct, tick ~300 (t = 3,78). Abre para todos en **t = 5,51** (≈ tick 500 con ticks de 30 s). Antes: Market Test (5,0) y Duelos I (5,15).*
*Etiquetas como en [knowledge.md](../../knowledge.md): `[medido]`, `[API]`, `[regla oficial]`, `[inferido]`. Hechos: D-20 a D-24.*

## 1. Lo que sabemos
| Dato | Fuente |
|---|---|
| Coleccionista de Salamanca. **Compra** infrecuentes, raras y épicas: **SAL y RET** listadas aparte (sus favoritas) y las de cualquier set publicado. **No compra comunes.** | `[API]` `GET /api/dealers/pilar` → `menu.buys` |
| **Vende solo `sobre_oro`**: apertura 504, lista 420, 1 por equipo y hora. 6 tratos por equipo y hora. | `[API]` `menu.sells` |
| *"Pays over book for the cards she loves … looks down on everything else."* | `[API]` `levels.how`, `bio` |
| Rasgos: paciencia 0,6 · generosidad 0,5 · **astucia 0,75** · **memoria 0,7** · rigor 0,6 · charla 0,55. Mucho más dura que la Abuela (astucia 0,2, memoria 0,15). | `[API]` `traits` |
| La Abuela la anuncia: *"If you find doubles, Doña Pilar … pays very well for her favourites."* | feed, hilo 442 |
| **Único precio visto:** t13 le pidió 49 por LAV-08 (infrecuente, set no favorito). Ella respondió: *"I know precisely what that card is — forty-nine it is not … I offer sixteen."* Eso es **0,64 × libro**. t13 abandonó el hilo, abrió otro y subió a 51. | `[medido]` feed, hilos 455–457 (ticks 292–295) |
| Desbloqueo anticipado: 3 tratos negociados con El Chato. t13 lo tiene desde el tick 262; nosotros no (D-18, D-19). No merece la pena forzarlo por 1,7 h. | `[API]` `unlock`, feed |

## 2. Para qué nos sirve (por orden)
Tenemos SAL y RET completas (protegidas) y **ningún repetido de SAL ni RET**. Lo único que le podemos vender hoy son **LAT-06, LAT-07 y LAT-08**: infrecuentes, copia única, LAT abandonada en t205. Cada una nos vale 22,5.

1. **Los 3 huecos de escalera del nivel 3.** Los niveles altos pesan más (`[regla oficial]`) y hoy los tres valen 0. Comprarle no es opción: el sobre de oro cuesta ~420 y vale mucho menos para nosotros. **La única forma de llenarlos es venderle.**
2. **Caja para CHA.** El plan del domingo va corto de 59–92 P ([analista.md](analista.md) §2).
3. **Precio de referencia de SAL/RET.** Lo que pague por sus favoritas es un suelo para los repetidos de RET (J5, J13) y para las pujas de los rivales.

## 3. La restricción de la Gate (lo que decide los números)
**La Gate no vende a un dealer por debajo de nuestro valor + `DEALER_MARGIN`.** El suelo es `ceil(dv_rm + 1)`, comprobado en G30 (al abrir), G31 (cada mensaje) y G32 (al aceptar). Para una LAT infrecuente es **24**. Los tests están en `tests/test_talk.py` (`PilarSell`).

- Con su apertura de ~16 para sets no favoritos, el punto medio con un ancla de 32 da ~24, justo en el suelo. **Lo más probable es que solo cerremos si concede como El Chato.** No cerrar no cuesta nada (D-14: venderle a un dealer paga poco).
- Para bajar de 24 habría que cambiar G30–G32 en las ventas a dealers. Solo tendría sentido si se demuestra que vender a un dealer no mueve `neg_points`, y eso hoy no se puede medir por debajo de 24. **No se toca sin decisión del lead.**
- La Gate también impide venderle cualquier carta de SAL o RET (`G13.protected`), y abrir el hilo antes del desbloqueo (`G30.locked`).

## 4. Lecciones que aplicamos (nuestras y de otros equipos)
| Lección | De dónde | Qué hacemos con Pilar |
|---|---|---|
| Pedir el doble de libro no ancla a un dealer astuto: contesta con su cifra baja | t13, hilo 456 | Ancla creíble: **32** (~1,3 × libro), no 49 |
| El trato acaba cerca del punto medio de las dos aperturas | D-09 (El Chato) | Con su 16 y nuestro 32, el medio es 24 = nuestro suelo |
| No concede si no nos movemos; repetir cifra enfada | D-03, D-07 | Bajar en cada mensaje (G31 ya prohíbe repetir) |
| El texto del dealer no es señal; solo cuenta `final` | D-08 | Decidir con la estructura. Si el texto contradice la oferta, es candidato a flag (solo a mano) |
| Memoria alta: abrir, abandonar y reabrir se recuerda | rasgo 0,7; t13 lo está haciendo (455→457) | Un hilo por carta, sin abandonarlo. **Vigilar si su segunda oferta a t13 empeora** |
| La inyección cambia palabras, no precios, y algunos dejan de hablarte | RULES, Fair play | Nada de inyección con Pilar: necesitamos 3 tratos |
| Ante una final, decidir en el mismo tick | D-07 | ≥ 24 → `accept`; < 24 → `close_thread` |

## 5. Afinidad de los rivales: qué cambia
Datos de `python3 affinity.py` (tick 300). Solo sirven para elegir contraparte: las cifras salen de nuestro valor y de la Gate.

- **Para LAT-06/07/08 hay compradores entre los equipos.** A 24: t15 (82 %, valor esperado 31, COMPRADOR) y t14 (76 %, 30,6). Venderles a ≥ 26 da +3,5 o más de `neg_points`, que es mejor que Pilar en puntos y en caja. **Orden: El Rastro primero (J5, hacia t15/t14); Pilar para lo que no se venda y para los huecos de escalera.**
- **Pilar compite con los equipos de SAL y RET altos** por los repetidos de sus favoritas. SAL: t17 (41 % de ser su ×1,6), t06 (37 %) y t13. RET: t05 (54 %) y t15 (41 %). Un repetido nuestro de SAL/RET da puntos si se vende a esos equipos (un RET-07 repetido nos vale 8,1, así que a 30 son +21,9). A Pilar solo da caja y escalera.
- **Los equipos con SAL/RET bajos** (SAL: t15 0,83, t12 0,88; RET: t17 0,86, t08 0,87) le venderán a ella. Habrá menos oferta de esas cartas en El Rastro. No nos afecta: nuestras páginas están completas.
- **CHA mañana:** compra cualquier set publicado, pero CHA no es favorita. No debería encarecer nuestra carta de cierre (puja a 72). Hay que comprobarlo en el feed a las 09:00.

## 6. Runbook
### Fase A: ahora → t = 5,51 (sin clave)
- `python3 rivals.py` / feed público: seguir los hilos de t13 con `pilar`. El feed solo guarda 500 eventos: hay que grabarlo.
- Contestar antes de abrir y apuntar en [knowledge.md](../../knowledge.md) (D-xx) o en el diario:
  - P1. Su apertura por rareza y set, y cuánto paga sobre libro en SAL/RET.
  - P2. Su patrón de concesión: espejo (El Chato), decreciente (Abuela) o rígido.
  - P3. Cuándo da la final y cuánto la mueve.
  - P4. Si su oferta en el hilo 457 de t13 sale peor que en el 456 (memoria).
- **Si P1–P3 dicen que no pasa de ~20 en no favoritas: no abrir hilos.** Las LAT siguen en El Rastro para t15/t14.

### Fase B: t ≥ 5,51, venta manual por la Gate (solo el operador, máquina A)
**La táctica `dealers` no abre hilos de venta.** Cada paso es un intent manual con `bazaar.py do`. Con el runner vivo, la orden va a su buzón; si no, hay que añadir `--live`. Un hilo con Pilar cada vez (G30.thread_open). Fuera de las sesiones de duelo.

1. **Retirar la carta de El Rastro** (si no, `G30.listed`): `status` da el id de la oferta.
   ```
   python3 bazaar.py do cancel --args '{"offer_id": <id>, "ref": "LAT-07"}' --why "Pilar: retirar LAT-07 de El Rastro"
   ```
2. **Abrir el hilo** en el tick siguiente, cuando la oferta salga `cancelled`. El `limit` es el suelo: 24 (lo exige G30).
   ```
   python3 bazaar.py do open_thread --args '{"dealer": "pilar", "side": "sell", "ref": "LAT-07", "asset_ids": [<asset_id>], "limit": 24}' --why "Pilar EXP-P1"
   ```
3. **Pedir** con la plantilla `pilar_sell` (variantes 0–3, una distinta cada vez). Escalera: **32 → 29 → 27 → 26 → 25 → 24**, un mensaje por tick y solo después de que ella conteste.
   ```
   python3 bazaar.py do say --args '{"thread_id": <tid>, "ref": "LAT-07", "price": 32, "template": "pilar_sell", "variant": 0}' --why "Pilar ancla"
   ```
   Si su oferta ya es ≥ la nuestra siguiente, G31 rechaza el `say` (`should_accept`): hay que aceptar.
4. **Aceptar** su oferta si es ≥ 24 (G32 lo vuelve a comprobar contra el hilo releído):
   ```
   python3 bazaar.py do accept --args '{"offer_id": <oid>, "source": "dealer", "ref": "LAT-07", "side": "sell", "price": <p>, "thread_id": <tid>, "give_asset": null, "fingerprint": "", "resupply": false, "venue": "pilar"}' --why "Pilar: venta"
   ```
5. **Final por debajo de 24, o 6 ticks sin moverse:** `do close_thread --args '{"thread_id": <tid>, "ref": "LAT-07"}'` y volver a publicar la carta en El Rastro (J5).
6. **Medir (EXP-P1):** `score` antes y después en el diario: Δ`neg_points` (se espera 0), Δ`ladder_points`, `negotiating` en el snapshot siguiente. Con eso se decide si las otras dos van a Pilar o a t15/t14.

### Fase C: condicional, puente de favoritas (bloqueado por diseño)
Si P1 muestra que paga **≥ 28** por una infrecuente de SAL/RET, habría ciclo: comprarla a la Abuela a ≤ 22 y vendérsela a Pilar. **Hoy la Gate no lo permite:** comprar un repetido no es una `need` del plan (`G30.no_need`) y su valor de segunda copia queda por debajo del precio. Hacerlo requiere un cambio de código y de plan aprobado por el lead. Aun así, el repetido se ofrecería antes a t05/t15 (RET) o t17/t06 (SAL), que dan puntos.

### Lo que NO hacemos
- **No comprar sobres de oro.** 420 de lista frente a un valor esperado de ~286 (tick 93), y hoy menor porque salen repetidos de SAL y RET. No hay plantilla `pilar_buy`: G60 rechaza cualquier compra.
- No venderle cartas de SAL ni RET (G13 lo impide).
- No abrir y abandonar hilos, no inyectar, no repetir cifras.
- No forzar el desbloqueo anticipado con un trato con El Chato.

## 7. Experimentos
| Id | Hipótesis | Parámetros | Medir |
|---|---|---|---|
| EXP-P0 | Pilar abre a ~0,64 × libro en sets no favoritos y por encima de libro en SAL/RET | Solo el feed | Aperturas y finales por rareza y set |
| EXP-P1 | Vender a un dealer no cambia `neg_points` y llena un hueco de escalera del nivel 3 | LAT-07, ancla 32, suelo 24 | Δ`neg_points`, Δ`ladder_points`, `negotiating`, precio y rondas |
| EXP-P2 | Su memoria castiga reabrir: la segunda apertura a t13 por LAV-08 sale ≤ 16 | Solo el feed | Su oferta en los hilos 457 y siguientes |

## 8. Qué se ha añadido al código
- `agent/talk.py`: plantilla `pilar_sell` (4 variantes formales que pasan G60). No hay `pilar_buy`.
- `tests/test_talk.py`: `PilarSell`. Cubre el desbloqueo (G30.locked), el suelo de 24 al abrir, mensajes y aceptación, la protección de SAL (G13), la plantilla por dealer y lado (G60) y que no existe `pilar_buy`.
- Sin cambios en `config/plan.json` ni en la táctica `dealers`: las ventas son manuales.
