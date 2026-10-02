# Decisiones

Entradas cortas y fechadas: qué decidimos, por qué, y qué haría cambiarlo. Las más recientes arriba.

## D-008 · vie 2 oct, tick 108 · Abandonar la página LAT y vender LAT a t15
t15 colecciona LAT (5 compras en 8 ticks) y casi seguro tiene una affinity mayor que nuestro ×0,9. Para completar LAT nos faltan 2 raras que nadie vende, t15 compite por ellas y las ganancias con vendedores no suman (E9). **Crear valor = mover las LAT a quien más las valora.** Ofertas dirigidas a t15: comunes a 12 (valor 9) y LAT-07 a 28 (valor 22,5). Las pujas por LAT por debajo de nuestro valor se mantienen: si se cumplen, son reventa.
**Revisar si** t15 no acepta en ~30 ticks (bajar a 10–11 / 25) o si aparecen raras de LAT a ≤ 63.

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
