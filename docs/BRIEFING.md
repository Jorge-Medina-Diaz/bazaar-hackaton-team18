# BRIEFING sábado — Team 18 (léelo en 5 minutos)

*Escrito el sáb 3 oct a las 08:35. Base: `docs/knowledge.md` (hechos verificados por 8 analistas + 8 escépticos sobre los datos del viernes) y `docs/strategy.md` (plan completo). Si algo aquí contradice esos dos, mandan ellos.*

---

## 1. Cómo se consiguen puntos (lo medido, no lo supuesto)

| Bloque | Peso | Cómo se gana **de verdad** | Lo que NO sirve |
|---|---|---|---|
| **Negociación** | 30 | **a) Comercio con equipos:** cada trato suma `valor recibido − valor entregado − comisión (solo si aceptamos)`, a NUESTROS valores privados. Medido trato a trato. **b) Escalera de vendedores:** solo suman los tratos que son **ganancia** a nuestro valor (3 mejores por nivel). **c) Duelos:** `|precio − nuestro límite| × (1 − decay)^rondas`; las rondas son mensajes **intercambiados** (callar no cuesta). | Pagar a un vendedor más de lo que vale la carta **resta** (el viernes, −27,6 en 5 tratos). Las ganancias con vendedores **no suman** a neg_points. Comprar sobres resta. Nº de tratos, comisiones, suerte, regalos: 0. |
| **Mercado** | 30 | **Market Test** cada ~2 h: el puesto gratuito saca la **mitad** de los puntos sin riesgo. Un mercado propio solo da más si su broker supera al emparejamiento simple. | Abrir mercado "por tenerlo": cuesta 20 P + 250 P bloqueados y si el broker cae, esa sesión vale 0. |
| **Jueces** | 40 | Ideas y ejecución: arnés seguro, aprendizaje medido (predicho vs medido), diario, documentación. | — |

**Reglas de valor clave:**
- Valor de una carta = catálogo × nuestro multiplicador × [1 / 0,25 / 0,1] por copia (1.ª, 2.ª, 3.ª+).
- **Bonus de página:** completar las 10 cartas de un set suma un 25 % de la página → **la última carta vale casi el doble** (SAL-10 pasó de 77 a 149,9).
- La compra de SAL-10 a 80 sumó **+50 exactos** (no +69,9): probable **tope de +50 por trato**. Consecuencia: pagar por la carta de cierre hasta `valor − 50` da el máximo; no hace falta regatear barato.
- **Comisión** = `ceil(0,05 × precio + 1 por carta)` en El Rastro, la paga **quien acepta** → mejor publicar que aceptar.
- **Sobre sin abrir = pérdida en cada compra** (rebaja el valor de lo que compras) → abrir todo sobre al llegar.

## 2. Nuestra situación y nuestras cartas

- **Caja 260** (+150 al empezar la ronda 2) · nivel 2 (Abuela + El Chato) · puesto 7/18 · negociación 19,19.
- **Multiplicadores:** **CHA 1,6 · RET 1,3** · SAL 1,1 · LAT 0,9 · LAV 0,7 · MAL 0,5. **RET sale hoy a las 09:00 y CHA mañana: son nuestros sets fuertes.** El viernes el líder (t13) ganó porque su set fuerte (SAL) estaba disponible y lo coleccionó desde el minuto 1; hoy nos toca a nosotros con RET.
- **Páginas:** SAL completa (10/10). **LAT 8/10** (faltan las raras LAT-09 y LAT-10; tenemos pujas de 62 P abiertas por cada una hasta el tick 205).
- **Valores RET para nosotros:** común 13, infrecuente 32,5, rara 91; **la carta que cierre RET vale ~99**. CHA: 16 / 40 / 112, cierre ~122.

## 3. El juego es teoría de juegos: con quién jugamos

| Contraparte | Qué es | Cómo la tratamos |
|---|---|---|
| **Abuela Carmen** | Reglas fijas y predecibles: no cede si no subes; cede ~1 P por ronda; final de sobre 19–24, infrecuente 21–25, común ~9–10. | Explotable: le compramos **por debajo de nuestro valor** (RET común ≤ 11, infrecuente ≤ 25). Nunca contraofertar por debajo de su final. |
| **El Chato** | Duro: nunca cede más que tu último paso. Raras abren en 97 y cierran 90–93 (t07 sacó 82 con pasos de +4). | Pasos constantes de +4 en raras RET (valor 91): límite 90. Infrecuentes: patrón lento. Nunca por encima del valor. |
| **17 equipos rivales** | Adaptativos, cada uno con sus multiplicadores. Pagan **35–110 P** por la carta que les cierra una página (59 pujas ≥ 35 el viernes). | Les **vendemos** lo que valoramos poco y ellos mucho; les **compramos** la carta que nos cierra página. Sus mensajes son "cheap talk": solo cuenta la oferta estructurada. |
| **Dueños de mercados** (t06, t12, t13, t02) | Ganan puntos de mercado cuando otros comercian en su mercado. t13 lo promociona por eso. | Publicamos solo en El Rastro. Aceptamos en el de un rival solo si la ganancia ≥ 10 y no es un top-5. |
| **Organizadores** | Calendario que puede moverse; el viernes el reloj se despausó tarde. | El agente se guía por **eventos y el reloj del servidor**, no por la hora de pared. |

**Principio:** observar → predecir el efecto en puntos → actuar solo si es positivo → medir → si la predicción falla, pausar esa táctica. Nada de guiones fijos.

## 4. La estrategia, por prioridad (y por qué)

1. **Higiene (desde el minuto 1):** abrir cada sobre al llegar, no exponer nunca la última copia de una carta de página, medir. *Por qué:* el viernes perdimos −8,4 por un sobre y −2 por compra con un sobre sin abrir.
2. **RET a 9/10 comprando a los vendedores por debajo de nuestro valor** (Abuela comunes ≤ 11 e infrecuentes ≤ 25; El Chato raras ≤ 90). *Por qué:* coste ~290 P en cartas que valen más de lo pagado → no resta nada y llena huecos de escalera.
3. **Cerrar RET comprando la última carta a OTRO EQUIPO** (nunca a un vendedor): puja inmediata a 49 P (valor 99 − 50); subir a 79 si hay competencia. *Por qué:* es el **+50**, la jugada más rentable del juego (así ganamos la mitad de nuestros puntos el viernes).
4. **Vender a las pujas de cierre de los rivales** cartas RET/CHA que la Abuela nos repone barato (+19 a +32 por ciclo). *Por qué:* es lo que hizo t12 (2.º) el viernes.
5. **Vender sobrantes como autor** (sin comisión): MAL, LAV y copias repetidas a ~9–12 P.
6. **Duelos (Duels I hoy):** nunca fuera del límite; ceder despacio si el rival calla; aceptar solo cuando el rival ya ha hablado en el tick.
7. **Market Test con el puesto gratuito** (mitad de puntos sin riesgo). Mercado propio **solo si** un broker supera al emparejamiento simple con el libro real grabado.
8. **LAT:** si se cumple una de las pujas de 62 P, la otra rara pasa a valer ~122 → comprarla. Si a las ~09:22 no se ha cumplido ninguna, LAT se da por muerta y sus cartas se venden.
9. **Domingo:** lo mismo con CHA (nuestro multiplicador más alto).

**Lo que NO hacemos:** comprar sobres; pagar a un vendedor más de lo que vale; comprar la carta de cierre a un vendedor; aceptar tratos con ganancia < 3; bajar una puja de cierre; flags o prompt injection; un segundo ejecutor con la clave.

## 5. Planning concreto de hoy

**El reloj es la gran incógnita:** el viernes se paró en la hora de juego 2,65, no en 4,0. A las 09:00:30 se sabe cuál de estos casos rige:
- **N (normal):** RET y ronda 2 a las 09:00, +150 P a las ~09:03, Market Test ~10:00, **Duelos I ~11:30**.
- **C (continuación):** todo +1 h 21 min → Market Test 09:21, RET y +150 P ~10:21, Duelos I ~12:51.
- **P (en pausa):** solo se puede cancelar hasta que despausen.

| Hora | Acción | Quién |
|---|---|---|
| 08:50 | `python3 bazaar.py clockcheck` (solo lectura) | Operador (máquina con la clave) |
| 09:00 | `python3 bazaar.py run` **en modo prueba (sin `--live`)**: lee el juego real, decide y registra, **no envía nada**. Valida el arnés contra datos reales. | Operador |
| 09:00–09:30 | Al terminar la integración (suite en verde) → `run --live --arm hygiene` (abrir sobres, vigilar) | Operador |
| ~09:30–10:30 | Revisar el diario de decisiones en prueba; si son correctas → `arm dealers,rastro` (RET a 9/10 y ventas) | Operador + 1 revisor |
| Antes de Duelos I | `arm duels` | Operador |
| RET en 9/10 | `arm closer` → puja de cierre a 49 | Operador |
| Cada hora | `python3 bazaar.py status` · si algo raro: `python3 bazaar.py stop "motivo"` o crear un fichero `STOP` en la raíz | Cualquiera |
| 22:55–23:00 | Cerrar hilos con vendedores; `bazaar.py stop "cierre sábado"` | Operador |

**Seguridad operativa:** la clave solo en la máquina del operador; los paneles son solo lectura; todo lo que escribe pasa por un único punto de control (Gate) con reglas que no se pueden saltar, modo prueba y botón de parada.

## 6. Estado del arnés a las 08:35

- ✅ Construidos e integrados: punto de control (Gate), reglas de seguridad, modelo de valor, diario, sensor, tácticas (higiene, páginas, vendedores, mercado + intercambios + varios mercados, duelos), simulador con bots adversarios, bucle principal y `bazaar.py`.
- ✅ **Batería completa: 779 pruebas en verde** (08:35). Incluye: 1.000 ticks en modo prueba con 0 escrituras; sábado simulado con bots adversarios (4 semillas × 300 ticks) con 0 violaciones; repetición del viernes que **rechaza las 5 pérdidas y aprueba SAL-02, SAL-08 y SAL-10 a 80**; 16 caídas en mitad de una escritura con reinicio; STOP efectivo en ≤ 1 tick; ningún test sale de 127.0.0.1.
- ⏳ En curso: revisión de seguridad independiente, limpieza del repo y el resumen largo `docs/LEEME-EQUIPO.md`.
- **Regla:** ninguna táctica se arma en real hasta que su autoprueba esté en verde. Si algo no llega, se hace a mano con `bazaar.py do` (pasa por el mismo Gate).

## 7. Dónde mirar

- Hechos verificados: `docs/knowledge.md` · Plan completo y razones: `docs/strategy.md` · Cómo está construido: `docs/harness-spec.md`
- Lo que decide y hace el agente: `logs/run/journal.jsonl` (y `python3 bazaar.py status`)
