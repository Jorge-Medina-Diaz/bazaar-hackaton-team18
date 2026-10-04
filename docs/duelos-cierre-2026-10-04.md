# Cierre de Duelos III: evidencia y fallo prioritario

Revisión de lectura del 4 de octubre de 2026, aproximadamente 11:59 Madrid.
No se ha detenido el entrenamiento, cambiado el bot ni enviado operaciones del juego.

## Lo confirmado

- **Duelos III terminó:** evento público **95250**, tick **2074**, sesión **4**.
- Inicio anunciado: evento **83085**, tick **1862**, hora de juego **15,3667**: **612 duelos**, dos vueltas, 12 ticks por duelo, decay 0,10. Evento **83086** confirma el disparo del calendario.
- Unión del archivo público y lectura fresca: **612 IDs de duelo distintos**, **457 acuerdos (74,67 %)** y **155 sin acuerdo (25,33 %)**. Coincide el total observado con el anunciado.
- IDs de duelo de esta sesión: **11078–11689**. Primer cierre observado: evento **83287**, duelo **11100**, tick **1865**, acuerdo. Último: evento **95247**, duelo **11687**, tick **2074**, sin acuerdo. Estos ejemplos son globales, no atribuidos a t18.

Comparación pública completa de las dos sesiones recientes:

| Sesión | Acuerdos | Sin acuerdo | Total | Tasa de acuerdo |
|---|---:|---:|---:|---:|
| 3: Duelos II | 475 | 137 | 612 | 77,61 % |
| 4: Duelos III | 457 | 155 | 612 | 74,67 % |

Son tasas de cierre globales. Un acuerdo puede crear poco valor; no equivalen a puntuación ni permiten evaluar la calidad de nuestra política.

## Resultado propio: qué vemos y qué falta

**No podemos contar los acuerdos propios con estos eventos.** Los 612 eventos llevan `actor: ""`; su payload expone únicamente duelo, sesión, estado e ítem, sin equipo, precio, mensajes ni límite. Por tanto, acuerdos, fallos e IDs propios de t18 quedan **desconocidos**, no cero. No se ha encontrado `logs/run/journal.jsonl` en este checkout. Los fixtures de práctica no son la traza de este cierre.

La clasificación sí permite medir el cambio visible:

| Lectura | Puesto t18 | Total | Negociación | Mercado | Tratos |
|---|---:|---:|---:|---:|---:|
| Tick 1842, antes del inicio | 2 | 33,38 | 24,83 | 8,55 | 56 |
| Tick 1862, inicio de la sesión | 2 | 33,44 | 24,86 | 8,58 | 56 |
| Lectura fresca después del cierre | 3 | 33,08 | 24,19 | 8,89 | 56 |

Desde el punto anterior al inicio: **−0,30 total, −0,64 negociación, +0,34 mercado**. El contador de tratos sigue en 56. No identifica qué duelos jugamos, ni demuestra que los duelos causaran toda la caída: la normalización relativa, la actividad de otros equipos y el paso de la ronda también mueven el marcador. Del tick 1882 al 2002 la negociación bajó a 24,28 y después volvió a 24,62, mostrando movimiento durante la sesión.

Lectura fresca: t12 **34,40**, t10 **33,49**, t18 **33,08**, t05 **32,93**. Distancias: **0,41** al segundo y **1,32** al primero. No tenemos sus límites ni resultados privados para atribuir la diferencia a una estrategia concreta.

## Fallo comprobado en código: los duelos con días pueden quedarse esperando

El `fetch` de `main` avanzó de **433b6d4** a **e0bd6d3**, que incorpora fases Voss y opciones de conducta. **El bloqueo de los días sigue presente en ese main.**

Cadena comprobada en el código de `origin/main@e0bd6d3`:

1. `agent/world.py:81`: la proyección de `duel` admite `your_days_weight`, pero omite `days_meaning`.
2. `agent/world.py:331`: `_p_duel` proyecta el dato y no conserva tampoco un booleano de presencia.
3. `agent/tactics/duels.py:232`: `view()` exige `duel.get("days_meaning")` para marcar la explicación como conocida.
4. `agent/tactics/duels.py:244`: `_days_model()` devuelve ilegible si falta esa señal; la decisión termina en espera para el caso de dos asuntos.

Así, una entrada válida de dos asuntos puede perder la señal al pasar por World. Es un defecto reproducible de la ruta de datos; **no demuestra por sí solo cuántos duelos perdió el ejecutor**: falta su revisión de código activa y su diario. El arreglo de proyección tampoco sustituye la confirmación de que la táctica estaba armada o de que `your_days_weight` llegó numérico.

La rama remota **`fix/domingo-urgente@dd0d909`** contiene la reparación concreta: World deriva `days_meaning_known` de una cadena no vacía y la táctica acepta ese booleano. No conserva el texto como dato de decisión. También cambia configuración y tests.

### Traza mínima reproducida, sin llamadas al juego

Duelo inventado: comprador, límite 100, tick 100, deadline 116, peso de días 2,
asuntos precio y días, significado presente y signo de días −1.

```text
Entrada válida → days_meaning presente
parse_duel / World → days_meaning eliminado
view → days_meaning_known = False
_days_model → readable = False
_decide → ("wait", None, None)
Control con entrada directa → ("say", 60, 0)
```

Se conserva esta traza estructurada en el campo `pipeline.trace` de cada nuevo
`runs/mini-campo-batalla/resultados.json`. Es una reproducción del defecto,
no la conversación privada de un duelo cerrado.

### Mejoras por orden de impacto

1. **Restaurar la señal de días conservando Voss.** Probar entrada válida,
   ausencia de significado y peso ausente; los dos últimos deben seguir seguros.
   Confirmar versión activa en el operador antes de atribuirle el fallo.
2. **Distinguir motivos de espera en el diario.** Separar dato faltante,
   oferta no rentable, espera Voss deliberada, mensaje ya enviado en ese tick,
   aceptación pausada y deadline. Un único `wait` oculta causas distintas.
3. **Comprobar cuatro duelos simultáneos en el runner.** Una política individual
   segura no verifica el presupuesto compartido de aceptaciones ni los rechazos
   de Gate. Esta cobertura no existe en la simulación nueva.
4. **Comparar compra y venta por separado con el plan actual.** El laboratorio
   mantiene los flags Voss comunes y semillas de validación independientes.
   Elegir más acuerdos sin medir excedente y decay puede empeorar el resultado.

Estas son propuestas para revisión; no se ha aplicado ningún cambio al ejecutor.

**Integración pendiente para el operador:** esa rama y el main nuevo divergen. Copiar toda su táctica sobre main eliminaría las adiciones Voss de e0bd6d3. Debe conservarse el comportamiento nuevo e integrar el parche de presencia con revisión y prueba de la ruta World → táctica. Este informe no aplica el parche operativo.

## La Final: calendario fresco y condición mínima

Las lecturas públicas frescas muestran reloj **tick 2092**, hora de juego **16,325**, abierto y sin pausa. El calendario anuncia:

- Final a **18,367 horas de juego**: una vuelta, **12 ticks**, **decay 0,10**, **4 simultáneos**, asuntos **`price` y `days`**.
- Cierre de vendedores en esa misma hora de juego.
- Congelación en **19,367**; cierre de puertas explícito **15:00 Madrid**.

No usar el horario antiguo escrito en documentos para programar el cambio. El operador debe leer el reloj y calendario actuales. Antes de aplicar recomendaciones del simulador, la prueba indispensable es que una entrada válida de precio y días llegue a la táctica y pueda producir una propuesta segura tras la proyección. Después se comparan políticas con esa ruta comprobada; entrenar una política sobre campos que World descarta no arregla el bot.

## Qué necesita el siguiente análisis del diario

En la máquina del operador, sin otra copia de su clave, recoger por cada duelo propio: ID, sesión, lado, `issues`, límite propio ya disponible, peso y señal conocida de días, deadline, mensajes estructurados, decisión, motivo de espera, rechazo de Gate, precio/días liquidados y resultado. Confirmar asimismo commit/code_hash activo, tácticas armadas y pausas de aceptación. Así se podrá distinguir bloqueo de datos, silencio del rival, falta de excedente, espera deliberada, Gate y expiración.

No inferir límites rivales ni tratar una aceptación enviada como liquidación. La traza privada permanecerá local; el resumen compartido puede publicar métricas e IDs con autorización.

## Fuentes y conservación

- Archivo público local: `/Users/ruben/projects/hackathon/practica/feed_all.jsonl`.
- Histórico de clasificación: `/Users/ruben/projects/hackathon/practica/leaderboard.jsonl`.
- Lecturas sin clave: [reloj](https://bazaar.causaprima.ai/api/clock), [calendario](https://bazaar.causaprima.ai/api/schedule), [clasificación](https://bazaar.causaprima.ai/api/leaderboard), [feed](https://bazaar.causaprima.ai/api/feed?limit=500).
- Snapshots y detalle de los 612 cierres: `runs/mini-campo-batalla/duelos-cierre/`, ignorado por Git; `resumen.json` identifica cada evento y duelo sin inventar pertenencia.
- Código contrastado mediante `git fetch` y `git show`. Después se incorporó `origin/main@e0bd6d3` por fast-forward al checkout aislado de prácticas para entrenar con su configuración; no se modificó la máquina del operador. La rama local sigue siendo `codex/mini-campo-batalla`.

Comprobación realizada: deduplicación por ID de evento y por ID de duelo; 612/612 cierres respecto al anuncio; cierre de sesión explícito; comparación de dos snapshots y lectura directa del defecto en main y del parche remoto. No se ejecutaron pruebas del bot vivo ni operaciones del juego.
