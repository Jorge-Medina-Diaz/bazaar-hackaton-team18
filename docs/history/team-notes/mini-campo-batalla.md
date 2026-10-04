> **Revisión del equipo (dom 4 oct, 13:50):** laboratorio offline de Rubén (rama `codex/mini-campo-batalla`, commit `cac7793`), conservado como nota. No se integró en el arnés:
> - recomienda mantener los parámetros (ancla ≈ 0,60, `acc_late` 3), que son prácticamente los nuestros;
> - simula solo el precio con un modelo de «arrepentimiento» de los días, W(d) − máx W, y su oráculo de seguridad contradice la fórmula medida en 95/95 tratos (S-26). Con un vendedor de límite 54 que vende a 55 con 0 días, el laboratorio da −19 y la fórmula real +1;
> - además asigna el signo de los días al azar, sin relación con el rol, cuando en vivo comprador = −1 y vendedor = +1 (34/34 cada uno).
>
> Contra nuestra táctica, sus 2.740 «unsafe» bajan a 147 con el signo correcto, y esos 147 son todos de esa diferencia de modelo. Ninguno es un trato fuera de nuestro límite.

# Mini campo de batalla · propuesta para la final

Entrega local del 4 de octubre de 2026, 11:48 Madrid.
Rama `codex/mini-campo-batalla`, desde main `433b6d4`, actualizada después a `e0bd6d3`.

## Entrenamiento continuo y muestra congelada

**Estado de la entrega:** el corte programado se ejecutó a las13:30 Madrid;
el entrenador está detenido y el paquete final se preparó correctamente.
Total conservado: **89 lotes, 3.572.000 evaluaciones simuladas**, sin fallos
de comprobación en los lotes contabilizados. **27/27 tests pasan.**
Los contadores agrupan versiones distintas; no equivalen a esa cantidad de
partidas reales ni prueban mejora de puntuación. El acumulado favorece conservar
el plan actual. La rama se publica para revisión e integración por Jorge.

### Corte y acoplamiento programados

El domingo 4 de octubre se ha programado un corte **13:30 Madrid** exclusivamente
para nuestro entrenador offline. Servicio local `ai.ruben.bazaar.battle-cutoff`.
Al llegar la hora, solicita STOP_TRAINING, espera a que termine el lote, repite
las pruebas y prepara `runs/mini-campo-batalla/entrega-final/`:
`RESUMEN.md`, `PROMPT-JORGE.md`, `codigo-harness.zip`, `cambios.patch`,
`manifest.json` con hashes y `tests.log`. Si falla la comprobación de código,
tests o cierre del lote, deja estado `failed` en entrenamiento/cutoff.json;
no activa nada. El servicio no vuelve a disparar un corte completado al reloguear.

**13:30–13:45:** revisar/acoplar en worktree aislado, con el código actual de Jorge
y Santiago. **13:45:** congelar la versión candidata. **~14:00:** Final, según
reloj/calendario leídos a las13:09; confirmar cambios o pausas. No modificar el
runner ni hacer selftest vivo; cambios operativos requieren el procedimiento
del único operador. La primera entrega solo añade laboratorio y documentación.

La automatización genera una entrega local revisable; no hace commit, push,
merge, envío a terceros ni reinicio del agente. El Mac debe seguir disponible.
Hay una entrega previa comprobada en entrega-previa/ para revisión anticipada.
Prompt completo: `docs/prompt-integracion-jorge.md`.

El servicio local `ai.ruben.bazaar.mini-battle` practica compra y venta en paralelo.
Cada lote actual usa 4.600 escenarios nuevos y 43.000 ejecuciones comparadas, con semillas
reservadas antes de arrancar y selección separada de validación. Arranca un lote
cada 60 segundos sin solaparlos, con prioridad baja. No usa red ni modelos de pago.
Lee el feed público local que ya recopila el monitor de Claude; no modifica ese monitor.

Estado persistente: `runs/mini-campo-batalla/entrenamiento/status.json`.
Informe actualizado: `runs/mini-campo-batalla/ULTIMO.md`.
La configuración de prácticas se toma de `config/plan.json`: actualmente
`precise=true`, `punch=true`, `punch_mode=wait`. Un hash del código y plan separa
las estadísticas de distintas versiones; los totales globales cuentan ejecuciones,
pero no sirven para mezclar recomendaciones de políticas distintas.

### Plus del evaluador incorporado en main

Revisión del remoto a las 12:07 Madrid: `main` sigue en `e0bd6d3`, ya incorporado.
Ahora cada lote también reutiliza `run_duel_eval.py`, sin modificarlo, para
comprobar las dos propuestas con sus tres modelos adicionales: `splitter`,
`ackerman` y `patient`. Son 80 escenarios por tipo y lado: 480 casos y 960
ejecuciones auxiliares, contabilizadas aparte del entrenamiento.

La comprobación toma las candidatas ya elegidas por entrenamiento y las compara
con el plan actual en los mismos casos. No utiliza ese resultado para cambiar la
selección. Publica ganancia pareada, error estándar y desacuerdo con la validación
principal; un desacuerdo requiere revisión. Un fallo de seguridad descarta el lote.
Es una evaluación de precio, sin días, Gate, memoria persistente ni texto LLM.
Los modelos adicionales son supuestos, no réplicas aprendidas de equipos reales.

Primer lote con el plus: las selecciones `anchor=0.70` en compra y `0.75` en venta,
ambas con `acc_late=3`, mejoraron en la validación principal pero empeoraron en
la adicional: −1,057917 y −3,635833 por episodio, respectivamente. Son excedentes
simulados. **Conservar el baseline:** esas selecciones todavía no demuestran
robustez entre modelos. La recomendación auxiliar del informe mantiene el
baseline ante desacuerdo o evidencia insuficiente; no reelige parámetros.

### Mejora aprendida de ese desacuerdo

Los tres modelos de main también forman parte del entrenamiento, con semillas
distintas de las de comprobación. Se amplía a 15 combinaciones de ancla y
aceptación tardía, incluyendo ancla 0,55. El plan actual siempre está incluido.
Cada tipo de rival pesa igual y sus ganancias pareadas se normalizan por el
límite propio; así las cartas de precio alto no dominan la elección.

La selección prioriza seguridad y menos grupos con pérdida media observada,
antes de maximizar el promedio. Comprueba los nueve tipos de rival y los grupos
de días. El líder acumulado utiliza ese mismo criterio; no vuelve al promedio
antiguo. La comprobación posterior conserva 480 casos independientes y no elige
otra candidata tras verlos. Las ejecuciones de comprobación siguen fuera del
contador principal de 43.000.

Primer lote reforzado: cero fallos; compra y venta eligieron conservar
`anchor=0.60, acc_late=3` y los flags Voss actuales. El resultado correcto es
descartar las propuestas que parecían mejores bajo el conjunto anterior;
todavía no se ha demostrado una mejora de puntos. Ninguna restricción garantiza
rendimiento contra un rival real ni sustituye la prueba del runner/Gate.

### Historiales de batallas y comparación temporal

Cada lote también analiza los datos históricos disponibles:

- Los 30 duelos de los fixtures aportan 179 estados registrados. Se reconstruye
  cada prefijo, sin mensajes futuros, y se prueba World → táctica con el plan
  actual. La primera comprobación pasó sin fallos; el replay es una verificación
  sobre estados observados, no una victoria contrafactual ni 179 datos nuevos
  independientes en cada lote.
- Patrones descriptivos del fixture: cinco duelos con un mensaje rival, doce
  con concesiones, uno con cambios mixtos y doce sin mensajes rivales observados.
  Ausencia de mensajes no prueba una política de silencio; estos aliases no
  identifican equipos actuales. No se deduce una mezcla real de enemigos.
- El feed público aportó 519 liquidaciones analizables de una sola carta.
  La comparación usa mismo dealer/lado/rareza/barrio, cinco referencias de al
  menos dos equipos, en los 240 ticks anteriores. Excluye tratos del mismo tick,
  posteriores, lotes y duplicados. La mediana de medianas por equipo evita que
  un bot muy activo domine la referencia.
- Solo un trato propio tuvo cobertura para esa comparación temporal. No usar
  esa muestra para certificar nuestro rendimiento ni convertir ventaja de
  precio en beneficio o puntos. Las cartas de la misma rareza pueden diferir.

`harness/battle_history.py` conserva estas comprobaciones en el informe vivo.
`--duels /ruta/captura.json` permite sustituir el fixture por una captura local
del operador, sin trasladar su clave. El feed de duelos público no contiene
identidad del equipo, mensajes, precios ni límites; no podemos fabricar esa
traza. El diario real y la versión activa siguen siendo necesarios para atribuir
los fallos de la última batalla a nuestro agente.

La memoria y el aprendizaje del ejecutor permanecen en su propia máquina.
El laboratorio solo conserva sus estadísticas, semillas y versiones. No modifica
el estado del agente ni adopta automáticamente una política.

```bash
python3 battle_watch.py status
python3 -m unittest tests.test_battle_data tests.test_mini_battle tests.test_battle_watch tests.test_battle_reference tests.test_battle_history tests.test_training_cutoff tests.test_battle_delivery -v
# Solo si quieres detener nuestro entrenador, sin tocar el bot:
python3 battle_watch.py stop
```

LaunchAgent instalado en `~/Library/LaunchAgents/ai.ruben.bazaar.mini-battle.plist`.
Sigue tras cerrar esta conversación mientras el Mac esté disponible; no se promete
ejecución con el equipo apagado o la tapa cerrada. No cambia parámetros del ejecutor.

**La tabla siguiente es la primera foto histórica, anterior al ajuste Voss.**
Las propuestas actuales están en el informe vivo; el +18,8 % no es una medición
de la configuración actual ni una ganancia observada en el juego.

## Resultado inmediato

**14.000 ejecuciones simuladas, 2.000 escenarios únicos, compra y venta en
paralelo, cero fallos de las comprobaciones. Nueve tests pasan.**
La fórmula de precio se contrastó con 18 acuerdos registrados en fixtures (18/18), y las rondas
con 30 duelos (30/30). La captura pública usada contiene 23.435 eventos y
1.488 cierres de duelo; esos cierres no muestran ofertas ni límites rivales.

| Lado | Propuesta | Validación baseline → candidata | Acuerdos |
|---|---|---:|---:|
| Compra | Conservar `anchor=0.60`, `acc_late=3` | 3,597 → 3,582 al probar `acc_late=1`: no mejora | 140 → 138 de 500 |
| Venta | Revisar `anchor=0.75`, `acc_late=3` | 3,361 → 3,992: +18,8 % simulado | 148 → 164 de 500 |

Son medias de excedente bajo el modelo de simulación, **no puntos del marcador**.
La candidata de venta pierde ligeramente frente a rivales que solo aceptan y
mejora frente a varios de los otros modelos. No garantiza mejora en la final.
La selección se hizo con entrenamiento; la validación usa semillas diferentes.
No se escogió otra candidata después de ver la validación.

## Prioridad antes de la final

La prueba local reproduce el bloqueo de main: el Sensor descarta `days_meaning`
y la táctica espera en un duelo de precio y días. La misma táctica recibe la
entrada directa y propone una oferta. La rama `fix/domingo-urgente` contiene la
corrección y el ajuste de horario; no está incluida en el main de esta entrega.
Comprobar qué versión corre Jorge antes de pensar en cambiar anclas.

El schedule leído a las 11:43 publica la Gran Final en h18,367, con **12 ticks,
decay 0,10, 4 simultáneos, precio y días**. Aproximadamente 14:00 Madrid si no
hay nuevas pausas. El operador debe confirmar el calendario vigente.

## Cómo funciona

- `harness/battle_data.py`: lee archivos locales, valida la fórmula y agrega
  comportamientos observados de 15 compras y 15 ventas históricas.
- `harness/mini_battle.py`: utiliza las funciones reales `view` y `decide` de
  duelos; simula rivales reactivos, temporales, firmes, que solo aceptan, mudos y
  que empeoran. Varía zona de acuerdo, turno inicial y preferencias de días.
- Actualmente explora 15 combinaciones: anclas 0,55/0,60/0,65/0,70/0,75 y aceptación tardía
  1/3/5 ticks. Prioriza seguridad y no perder frente al baseline en grupos de entrenamiento.
- Procesos separados para comprador y vendedor. Cada lado utiliza 500 escenarios
  de entrenamiento y 500 de validación; se comparan los candidatos sobre los
  mismos escenarios. Las repeticiones de trazas no cuentan como prácticas nuevas.
- `mini_campo_batalla.py`: comprueba el camino World → táctica y genera
  `runs/mini-campo-batalla/ULTIMO.md` y `resultados.json`.

La fórmula conserva el signo: compra `límite − precio`, venta `precio − límite`,
ambas por `(1 − decay)^min(mensajes nuestros, mensajes rivales)`. Sin trato, cero.
Una pérdida no se transforma en premio con un valor absoluto. Callar no añade
rondas; aceptar no envía un mensaje.

## Lo que el entrenamiento puede y no puede demostrar

Se seleccionan parámetros de negociación offline; no se entrena un LLM.
Los datos reales validan el componente de precio y describen conversaciones
históricas. La mezcla de rivales y su reacción siguen siendo supuestos de
prueba: el feed no permite identificar su política ni sus límites.
La utilidad lineal de días es una hipótesis conservadora, sin fórmula oficial
calibrada. Se informa por separado del componente de precio.

La simulación representa la relectura en el mismo tick, pero no sustituye una
prueba del runner completo con cuatro duelos y un presupuesto de aceptaciones
compartido. Tampoco reproduce el efecto de las frases Voss en un modelo real.

## Repetir rápidamente

Desde este checkout, con Python 3.10 o posterior:

```bash
python3 mini_campo_batalla.py --practices 500 --seed 18
python3 mini_campo_batalla.py --feed /ruta/feed_publico.jsonl --practices 500 --seed 18
python3 -m unittest tests.test_battle_data tests.test_mini_battle -v
```

El comando admite una captura local con `--duels /ruta/duelos.json`.
No carga `.env`, no usa claves ni realiza peticiones de red. Se puede ejecutar
en la máquina del analista sin armar tácticas.

## Para combinar con el agente operativo

1. Confirmar versión activa y corrección del bloqueo de días; el simulador no
   accede al proceso de Jorge ni lo reinicia.
2. Leer peso y significado de días del duelo; mantener validaciones económicas.
3. Conservar compra. Tratar venta 0,75 como propuesta específica de vendedor:
   **no poner 0,75 globalmente para ambos lados**. Esta entrega no incorpora
   parámetros distintos por rol en el ejecutor.
4. Una adopción requiere revisión del operador, regresión y selftest del código
   combinado antes de reanudar. Ningún parámetro operativo se cambió aquí.

Último MD con resultados y desglose: `runs/mini-campo-batalla/ULTIMO.md`.
Cambios limitados al laboratorio, sus pruebas y documentación. La primera
entrega fue local; la publicación posterior de la rama permite revisar el código.
