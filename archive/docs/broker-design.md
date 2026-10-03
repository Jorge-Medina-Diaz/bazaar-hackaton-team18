# Broker para el Market Test: diseño (vie 2 oct, tick 92)

Son 30 puntos de Mercado. Igualar al puesto gratuito da **la mitad** y los puntos completos van a la media del top 3 (📜 RULES). Este documento razona por qué un broker propio puede superar al puesto y qué hace falta para tenerlo.

## Requisitos
- Un mercado propio de tipo **`board`**. En uno `auto` (el puesto gratuito incluido), el motor cruza todo antes de que el broker lea el libro, así que el broker no aporta nada. Para abrirlo hace falta **nivel 2** y **270 P** (250 de fianza, reembolsable, + 20). Por eso `run_loop.py` mantiene una reserva de 150 P (más los 150 que se reparten el sábado).
- Cada sesión cuenta con nuestro mejor mercado abierto durante ella. **Si se cierra el mercado después de una buena sesión, no se conserva nada** → hay que tenerlo abierto todo el fin de semana.

## 1. Comisión = 0 en el mercado
📜 Las comisiones cobradas **no puntúan**, y una comisión **bloquea cruces**: un emparejamiento exige `price + fee ≤ bid`. Con comisión 0, todo par cuyas cotizaciones se cruzan se puede emparejar. Comisión > 0 solo nos quita eficiencia en el Market Test y atrae menos tráfico de equipos (el otro componente, `mm_points`). **Decisión: `fee_bps = 0`, `fee_per_card = 0`.** ❓ Comprobar que la API admite 0.

## 2. Por qué el puesto gratuito se queda en la mitad
La eficiencia es la suma de `(límite del comprador − límite del vendedor)` de los pares emparejados, dividida entre el máximo posible.
- El máximo lo da el **conjunto eficiente**: los k mejores compradores contra los k vendedores más baratos, con k el mayor tal que el k-ésimo comprador ≥ el k-ésimo vendedor (en límites reales). **Dentro de ese conjunto, cómo se emparejen da igual** (la suma es Σb − Σs).
- El puesto empareja **en cuanto las cotizaciones se cruzan**, a mitad de precio. Pierde por dos vías:
  1. **Desplazamiento:** empareja pronto a un trader *extramarginal* (fuera del conjunto eficiente) cuya cotización cruza antes, y ocupa al comprador que habría servido a un vendedor más barato que aún no había bajado su cotización.
  2. **Abandono:** los impacientes se van antes de que sus cotizaciones crucen. Su excedente se pierde.

## 3. Estrategia del broker propio
Por cada sesión, que viene en "runs": un id `"b12-7"` significa run b12, trader 7. Solo se emparejan ofertas del mismo run.
1. **Seguir a cada trader**: el historial de su cotización por tick. Pendiente de relajación `r` = cambio por tick. 📜 Los firmes nunca relajan; la mayoría relaja cuando se le acaba la paciencia.
2. **Estimar su límite**: `límite ≈ cotización actual − r × ticks que le quedan`. Si no hay datos, la cotización misma, que es una cota (el comprador puja ≤ su límite y el vendedor pide ≥ el suyo). Si la oferta trae `expires_tick`, esa es su paciencia.
3. **Calcular el conjunto eficiente estimado** con los límites estimados.
4. **Emparejar solo pares eficientes cuyas cotizaciones ya crucen**, y además:
   - **ahora** si a cualquiera de los dos le quedan ≤ 2 ticks, si ambos son firmes (esperar no aporta nada) o si quedan ≤ 2 ticks de sesión;
   - **esperar** en caso contrario, porque las relajaciones pueden hacer cruzar a otros pares eficientes;
   - **nunca** emparejar a un extramarginal estimado si eso deja sin pareja a un eficiente.
5. Precio: cualquiera que cumpla `ask ≤ price ≤ bid − fee`, por ejemplo el punto medio (con comisión 0, el precio no afecta a la eficiencia).
6. Respetar el máximo de 10 emparejamientos por tick (`starter_broker.public_plan`).

## 4. Qué falta para construirlo
- **Datos de una sesión real** (formato de `bench_offers`: ¿trae `expires_tick`?, ¿cuántos ticks dura?, ¿cómo relajan?). La primera sesión será con el puesto gratuito (no tenemos nivel 2): **grabar el libro de cada tick** con un broker en modo observación, sin emparejar nada, sobre la clave del puesto (`me().starter_broker_key`).
- **Nivel 2** (El Chato) y 270 P para el mercado `board`.
- Simulador local con los datos grabados para comparar el broker v1 con el emparejamiento por cotización antes de usarlo en vivo.

## 5. Simulación (vie, tick 108): `python3 sim_bench.py 500 [--no-expiry]`
Modelo inventado: 5 compradores y 5 vendedores por run, 16 ticks, cotizaciones alejadas un 10–40 % del límite, 25 % firmes, 60 % se van antes del final y el resto relaja hacia su límite.
| Estrategia | Con caducidad visible | Sin caducidad visible |
|---|---|---|
| greedy (puesto / starter: cruzar en cuanto se pueda) | 89,6 % | 89,6 % |
| v2: solo conjunto eficiente estimado, al momento | 89,0 % | 88,7 % |
| v1: esperar salvo urgencia | 89,1 % | **72,3 %** |
**Lecciones:** (1) **esperar es peligroso** si no sabemos cuándo se va cada trader; (2) con este modelo el desplazamiento cuesta poco y greedy ya está cerca del óptimo; (3) **el modelo no es la realidad**: las reglas dicen que el puesto solo saca la mitad de los puntos y que estimar límites y salidas lo supera. **Siguiente paso obligatorio: grabar el libro de una sesión real** (con `starter_broker_key` del puesto gratuito, en modo observación) y reajustar el simulador con esos datos antes de usar nada que no sea greedy.
