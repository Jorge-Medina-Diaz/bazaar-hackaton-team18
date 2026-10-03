> Integración del 3 de octubre: el ejecutor actual es `bazaar.py` de harness-v2.
> Este documento describe una comparación histórica offline, no las tácticas actuales.
> El baseline y broker puro se conservaron en `harness/legacy_baseline.py` y
> `harness/legacy_broker.py`; los scripts de `archive/` no se importan ni ejecutan.

# Harness: medir antes de cambiar el agente

## Qué es y qué entrega esta versión

Un harness es el entorno que ejecuta el mismo agente frente a casos conocidos,
observa sus decisiones y compara resultados. Un test comprueba un requisito;
el harness reúne requisitos, escenarios, medidas y una referencia reproducible.

Esta versión funciona **offline, con datos inventados**. No necesita clave, no
arranca `run_loop.main()`, no negocia y bloquea llamadas al SDK, HTTP y sockets.
Ese bloqueo detecta errores accidentales: no es un sandbox para código ajeno.

Mide tres dimensiones por separado:

| Dimensión | Medida | Criterio |
|---|---|---|
| Economía | Ganancia neta simulada, ganancia por tick y pérdida frente a la mejor elección conocida | Contar solo elecciones admisibles; descontar comisiones. No equivale a puntuación oficial. |
| Seguridad | Selecciones no admisibles, oferta alterada, errores, decisiones tardías y conflictos | Ningún fallo admitido para el candidato en los casos cubiertos. |
| Rendimiento | GET simulados por ruta, presupuesto de consultas y p50/p95 local | Una consulta de valor por carta distinta y decisión; comparar lecturas y tiempo local por separado. |

No se oculta un fallo de seguridad dentro de una media económica. El `PASS`
corresponde al candidato experimental y sus casos conocidos; **no certifica el
agente completo ni autoriza una partida real**. Los defectos del selector histórico
se conservan en el informe como referencia y no impiden ejecutar la comparación.

## Ejecutar y abrir en VS Code

Desde la carpeta del repositorio:

```bash
python3 run_harness.py --output runs/harness-baseline.json
python3 run_harness.py --seed 23 --runs 100 --repeats 10 --output runs/harness-seed23.json
python3 -m unittest discover -s tests -p test_harness.py -v
```

El recorrido inicial tarda aproximadamente medio segundo en este equipo; no es
un compromiso de latencia en otros ordenadores. `--json` produce exclusivamente
el informe JSON en stdout. El código de salida es 0 si pasa el candidato y 1 si
falla. `runs/` está excluido de Git: no subir historiales privados del juego.

Para estudiar el código:

1. `harness/cases.py`: entradas, elecciones admisibles y elección óptima conocida.
2. `harness/runner.py`: cliente falso, métricas, oráculo y ejecución sin red.
3. `harness/market.py`: adaptador del selector histórico, candidato y arbitraje experimental.
4. `tests/test_harness.py`: verifica que el evaluador también detecta regresiones.
5. `runs/harness-baseline.json`: resultados de cada caso, sin ocultar fallos.

## Comparación justa y reproducible

Ambas políticas reciben las mismas ofertas, saldo, valores y reloj. No reciben
la elección esperada ni los límites ocultos de los traders. La semilla fija los
100 libros adicionales. Los 27 casos nombrados cubren compras y ventas, comisiones,
reserva, valores de página, varias ofertas de una carta, identidad, destinatario,
expiración, ofertas propias, cartas bloqueadas/publicadas, pausa, contexto antiguo,
cuota y liquidaciones pendientes o inciertas. Incluyen una alternativa válida
cuando la oferta aparentemente más rentable no está disponible.

El oráculo conoce de antemano las elecciones admisibles. Calcula la ganancia de
la elección con los datos de la fixture, mediante una expresión de comisión
independiente de `market.fee`. Una elección válida menos rentable recibe su
ganancia real y registra su pérdida frente al óptimo. Una elección no admisible
recibe cero ganancia y registra un fallo; no inventamos penalizaciones oficiales.
También comprobamos que un adaptador no falsifique los campos de una oferta
conservando su ID y su ganancia declarada.

Cada caso de mercado es una ventana independiente de **dos ticks**: elegir y
liquidar, o abstenerse. No se encadenan cambios de inventario entre casos. Por
tanto, la ganancia/tick permite comparar este conjunto de pruebas, no proyectar
ingresos de una jornada. Las consultas iniciales que producen los snapshots,
el POST de aceptación y las llamadas de conciliación no se incluyen en el coste
del selector. Las repeticiones de latencia no multiplican el total representativo
de consultas, que cuenta una decisión por caso.

Los informes registran commit, rama, estado sucio, versión de Python, semilla,
parámetros y hashes de fuentes y fixtures. El hash de fuentes incluye los archivos
ejecutados del experimento aunque aún no haya un commit. Para un adaptador externo,
se añade la identidad y hash de su archivo: sus dependencias deben versionarse también.

## Primer resultado: referencia, no promesa

Ejecutado sobre `origin/main` en `ae73a8a`, semilla 7, 100 libros adicionales,
10 repeticiones de tiempo por caso. **127 casos de mercado**, más 13 de arbitraje
y 100 simulaciones emparejadas del broker existente.

| Métrica de mercado | Selector histórico del viernes | Candidato experimental |
|---|---:|---:|
| Ganancia neta simulada | 6.578 | 6.599 |
| Ganancia por tick simulado | 25,898 | 25,980 |
| Selecciones no admisibles | 16 | 0 |
| Excepciones | 0 | 0 |
| Lecturas del selector | 948 | 357 |

Reducción de lecturas: **62,3 %**. En el caso de diez ofertas de una carta, las
consultas de valor pasan de diez a una y la ganancia se mantiene en 13. La mejora
económica de 21 en el conjunto viene de dos alternativas válidas que la referencia
no elige; no demuestra una mejora equivalente en partidas reales.

En la primera ejecución de esta versión el p95 local fue aproximadamente
0,081 ms para la referencia y 0,098 ms para el candidato. **El candidato hace más
validaciones locales**. Ahorrar GET puede reducir tiempo real y cuota, pero aún
no hemos medido la red. `--fake-api-ms 100` solo estima el coste secuencial si cada
lectura durase 100 ms; cambiar ese supuesto no cambia la ganancia ni las decisiones.
No representa una medición de la API.

El broker reutiliza `harness/broker_sim.py`, con los mismos traders para `greedy`, `broker`
y `wait`. Con semilla 7 sus eficiencias sintéticas fueron 91,22 %, 89,69 % y
89,50 %. Aquí el starter gana: es una señal para revisar las hipótesis del simulador
y comparar más situaciones, no para proclamar un ganador real. Se conserva cada
resultado emparejado para analizarlo sin volver a generar los datos.

## Qué código es experimental

**No se modificó el ejecutor del equipo.** `harness.market.candidate` es una
propuesta para comparar: cachea valores dentro de una decisión, filtra estructuras,
vigencia y recursos, y evita nuevas elecciones cuando hay operaciones pendientes.
Necesita `clock.ready` y `clock.accepts_used`, campos que prepara la fixture;
una integración real deberá obtener frescura y consumo de cuota del coordinador.
Por ahora solo admite cartas individuales por efectivo en `rastro`.

`DecisionGate` recibe una propuesta junto con una huella del snapshot. La rechaza
si cambia el tick, oferta, saldo, valor, pausa o cuota. Reserva la aceptación antes
del envío; un resultado incierto permanece pendiente hasta observar un estado
terminal. Los 13 casos verifican esa clase, **no una coordinación ya instalada**.
La huella de todo el snapshot es conservadora: un cambio inocuo también puede
obligar a evaluar otra vez.

El arbitraje presupone un único ejecutor que lo posee y lo llama secuencialmente.
No coordina ordenadores distintos ni garantiza exactly-once en el servidor. Antes
de usarlo en vivo faltan conciliación real, estados persistentes, política de
reintentos y pruebas del recorrido completo de `run_loop`.

## Añadir una estrategia, RAG o JEV

Un adaptador local de confianza expone esta función:

```python
def select(api, me, clock):
    # API falsa: my_offers(), board('rastro'), value(ref).
    # Solo leer. No recibe el oráculo de las fixtures.
    return (gain, 'BUY', offer, None)  # SELL: último campo = asset_id
    # Sin acción: (0, None, None, None)
```

```bash
python3 run_harness.py --candidate mi_modulo:select --output runs/mi-candidato.json
```

Las llamadas de red siguen bloqueadas. Para una estrategia con modelo, la primera
comparación debe usar respuestas grabadas/fixtures mediante un adaptador. Las
repeticiones actuales miden una política determinista: si el adaptador cambia de
elección con las mismas entradas, se registra fallo. Una evaluación posterior de
un modelo estocástico deberá puntuar cada respuesta y resumir su variabilidad.

Las medidas de llamadas, tokens y coste real del modelo requieren un recorrido
posterior instrumentado; en este informe son cero llamadas y coste/tokens
desconocidos, **no una estimación del precio de JEV**.

Orden de ampliación:

1. **Decisiones y ejecución:** integrar el candidato elegido en modo observación,
   comparar lo que propone con lo que ejecuta el agente y probar conciliación.
2. **Memoria:** guardar casos confirmados y fallidos, con dealer, lado, carta,
   fase, acción, respuesta y resultado. Separar casos usados para ajustar la
   estrategia de los reservados para evaluarla.
3. **Recuperación:** comparar sin memoria, SQL/FTS5 y recuperación semántica con
   las mismas preguntas. Medir relevancia de los casos recuperados, errores de
   dealer/lado, tokens y p95 total. La DB conserva el estado; RAG recupera recuerdos
   útiles para la decisión. No son alternativas excluyentes.
4. **JEV:** comparar la misma decisión con y sin su recomendación. Medir decisiones
   correctas, abstenciones, respuestas tardías, coste y beneficio. El código sigue
   verificando recursos, identidad, vigencia y cuota después de su respuesta.
5. **Piloto real controlado:** un ejecutor, parámetros registrados, estado fresco
   y límites comprobados. Confirmar liquidaciones y valor antes/después.

Esta versión no mide persuasión de Abuela/Chato, decisiones de duelos, errores HTTP,
planificación del rate limit, RAG ni JEV. `evaluacion.py`, los tests del haggler y
`harness/broker_sim.py` existentes siguen disponibles; no se presentan sus dealers inventados
como reproducciones del comportamiento real. Un `PASS` offline siempre necesita
el contraste posterior con el juego.
