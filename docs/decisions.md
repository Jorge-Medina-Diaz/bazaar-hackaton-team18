# Decisiones

Entradas cortas y fechadas: qué decidimos, por qué, y qué haría cambiarlo. Las más recientes arriba.

## Pendiente de decidir (vie 2 oct, tick ~111)
1. **¿Tope de 50 `neg_points` por trato?** EXP-008 dio +50,0 donde esperábamos +69,9. Si hay tope, tres compras de +50 valen más que una de +150, y eso cambia cómo pujamos por raras y por las cartas de RET y CHA. Probar con el próximo trato de ganancia > 50.
2. **Nuestra puntuación baja sin hacer tratos:** 27,4 (tick 75, 2.º) → 21,8 (tick 110, 4.º) → 19,7 (tick 138, 6.º). ❓ Probablemente es relativa a los demás y ponderada por la fase de la ronda. Si es así, quedarse quieto hace perder puestos.
3. ~~**Espejo de duelos**~~ → revisado en D-010: cada pareja es el mismo equipo (misma plantilla de texto con alias distinto); 5 equipos consistentes con el espejo y 2 que cruzan su límite en ambos sentidos.
4. **Mercado:** ¿abrimos el mercado (fianza de 250 + 20 P) antes del próximo Market Test o seguimos con el puesto gratuito? Con `starter_broker.py` sacamos lo mismo que el puesto (la mitad de los puntos). La ventaja real es cobrar poca comisión para atraer el comercio entre equipos (`market` = 0 para todos; solo t06 tiene mercado, al 0,5 %).

## D-011 · sáb 3 oct · Multiplicadores de los rivales: estimación bayesiana, no tablas a ojo
`agent/affinity.py` + `affinity.py`. Por equipo, las 720 permutaciones de {0,5…1,6} con prior uniforme; cada trade entre equipos, compra/venta a un vendedor, puja/oferta publicada y salto de `negotiating` en el leaderboard es una verosimilitud suave del multiplicador del barrio de la carta (mezclas para repetidos y bonus de página, suelo EPS para jugadas irracionales). Sustituye al "mapa de affinity" a ojo del playbook.
- Para decidir: `--card X --price P` da P(el equipo valora X ≥ P). Vender solo a quien sale COMPRADOR al nivel de confianza fijado (80 % por defecto); comprar a quien sale VENDEDOR. Las cifras de la oferta siguen saliendo de nuestro valor (D-002, D-007); esto solo elige contraparte y ancla.
- Calibración: en simulación el intervalo del 80 % contiene el valor real el 92–97 % de las veces (conservador) y nombra bien el ×1,6 en 6–9 de 12 equipos. Sobre nosotros (t18, a ciegas) acierta 5/6 barrios al 80 %; falla SAL porque nuestras compras de SAL son anteriores al tick 76 y no están grabadas.
- La evolución de la puntuación solo cuenta para los intervalos grabados: `python3 affinity.py --watch 60` siempre en marcha (2 GET públicos por minuto).
**Revisar si** `--calibrate` deja de contener nuestra affinity real en su intervalo del 80 %, o si los organizadores confirman que los multiplicadores no son una permutación.

## D-010 · vie 2 oct · Duelos v2: anclar alto, hablar poco, que el rival cruce
Detalle en [duels-strategy.md](duels-strategy.md). De la práctica (24 duelos, transcripciones completas):
- `rounds` = mín(mensajes nuestros, del rival): contra un rival callado ceder a pasitos es gratis; contra uno que concede solo, callarse es gratis.
- 11 de 17 tratos se cerraron a **nuestro** precio (el rival acepta la primera oferta que entra en su zona): ancla alta y pasos pequeños.
- Los rivales son casi todos plantillas deterministas, en 6 arquetipos reconocibles por el texto. El texto no mueve cifras.
- Espejo: confianza media (5 equipos consistentes; 2 lo cruzan en ambos sentidos). Se usa para el ancla y el suelo solo hasta 3 ticks del final.
**Revisar si** en Duelos I la tasa de trato baja del 71 % de la práctica o el `result` medio no supera 20,2.

## D-009 · vie 2 oct · Vendedores: solo para cartas de página y niveles. El Chato, con ancla baja
- La escalera casi no puntúa: +0,014 por trato con la Abuela, `ladder_points` 0,051 frente a `neg_points` 73,2. Matiza D-005: los tratos con vendedores sirven para conseguir las cartas baratas de una página (que después cerramos comprando a otro equipo) y para desbloquear niveles, no para perseguir la escalera.
- El Chato concede exactamente lo que concedemos nosotros y el trato cae en el punto medio de las aperturas (playbook, "El Chato"). Por eso: ancla al ~45 %, pasos iguales y nunca bajar la oferta. `dealers.py["chato"]` reajustado (0,45 / 0,75).
- Los líderes (t12, t08) puntúan con arbitraje de raras entre equipos: comprar a quien la valora poco y vender a quien la valora mucho. Hacemos lo mismo con nuestras cartas fuera de SAL.
**Revisar si** el Δ de `ladder_points` de un trato con El Chato (nivel 2, "higher levels weigh more") resulta grande.

## D-008 · vie 2 oct · Ventajas de información y manipulación: dónde sí y dónde no
- **Sí:** usar todo lo público (feed, tablones de todos los mercados, nuestros duelos) para adelantarnos: espejo de duelos (EXP-010), libros cruzados (EXP-011), pujas por páginas (EXP-013), faroles de vendedores (EXP-014) y libros del Market Test (EXP-015).
- **Sí, solo en el texto:** inyección de prompt y persuasión contra los agentes de otros equipos en los duelos (EXP-012). RULES: *"your agent may say anything"*. Las cifras las sigue decidiendo el código, así que el peor caso es igual que no inyectar. Se mide con A/B (`--arms`).
- **No:** inyección contra los vendedores (no cambia sus precios y alguno deja de hablarnos; El Chato fija el precio según "if I like you"), colusión o regalos entre equipos (penalización), más de una clave, `/api/admin/*`, ni saturar la API.
- **Flags:** solo a mano y con la contradicción entre texto y estructura a la vista (`flags.py`). Uno erróneo resta.
**Revisar si** los organizadores dicen que la inyección entre equipos no está permitida (entonces `--arms plain`) o si el A/B muestra que `inject` provoca más impasses.

## D-007 · vie 2 oct · El límite de compra de una carta que queremos es nuestro `your_value`
Corrige a D-006 y D-005 para las cartas que queremos: si el precio es ≤ `value?card=` (y el gasto cabe en la reserva de dinero), aceptar. El dinero no puntúa y el valor de la carta sí entra en futuros cambios y páginas. El suelo del vendedor solo sirve para **regatear** (hasta dónde empujar), no para **retirarse**.
Evidencia: EXP-004 rechazó SAL-08 a 23 con un valor de 27,5. t13 lo compró a 24.

## D-006 · vie 2 oct · Cómo decidir ante una oferta final
Una final no se repite (playbook). Para la escalera, un trato **nunca resta** (puntúa ≥ 0; los huecos vacíos valen 0) y solo cuentan los 3 mejores por nivel. Por tanto, ante una final:
- **Aceptar** si el precio está dentro del límite. El límite lo marca su suelo observado (sobre ≤ 23, común ≤ 10, infrecuente ≤ 22) **y** que el gasto no nos deje sin dinero para lo que sí puntúa: comprar a equipos cartas que nos faltan, la fianza del mercado (270 P) y los duelos.
- **Retirarse** si no: no se pierden puntos, solo el cupo y el tiempo.
- El límite se fija **antes** de abrir el hilo, nunca en caliente.
**Revisar si** el Δ de `ladder_points` muestra que un trato malo puede restar.

## D-005 · vie 2 oct · Con los vendedores, maximizar el rango capturado, no el valor del objeto
El dinero no puntúa. En la escalera puntúa la parte del rango de precios del vendedor que capturamos, y lo que se pague por encima del valor del objeto no resta. Por eso el límite de compra lo marca el suelo del vendedor (lo que vemos en el feed), no nuestro `your_value`. El límite de 20 P de EXP-002 salía de `your_value` y fue un error.
**Revisar si** el desglose de `/api/me` muestra que el valor del objeto también cuenta.

## D-004 · vie 2 oct · Estudiar a los vendedores con el feed público
`/api/feed` muestra los regateos de todos los equipos con los vendedores (precios, ofertas finales, tratos). Estudiarlos no cuesta dinero ni ticks. `scout.py` lo automatiza.
**Revisar si** el feed deja de ser público o empieza a ocultar precios.

## D-003 · vie 2 oct · Vendedores como datos y regateo genérico
Habrá más vendedores con el tiempo. El regateo (`agent/haggle.py`) es el mismo para todos y lo propio de cada uno (precios y frases) va en `agent/dealers.py`.
**Revisar si** un vendedor necesita una lógica distinta (por ejemplo, uno que miente): entonces se crea una función específica para él.

## D-002 · vie 2 oct · El código decide las cifras
Seguimos las invariantes de [negotiation-design.md](negotiation-design.md): el código fija cada precio y cada aceptación, las ofertas son monótonas y todo se registra en un JSONL. Los mensajes por ahora son plantillas; un LLM solo redactaría el texto.

## D-001 · vie 2 oct · Repositorio privado, clave fuera del código
Compiten otros equipos, así que la estrategia no se publica. La clave va en `BAZAAR_KEY` y `.env`/`logs/` están en el `.gitignore`.
