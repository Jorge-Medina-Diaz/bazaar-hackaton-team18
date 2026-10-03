# Priorizar lo que podremos demostrar al jurado

**Regla oficial:** 40 puntos por ideas y calidad del trabajo; los otros 60 vienen
de negociación y mercado. No se ha publicado una rúbrica detallada ni conocemos
cuántos puntos dará cada mejora. Lo siguiente es nuestro criterio de trabajo,
no una fórmula de los jueces ni un evaluador automático con un modelo.

## Mi recomendación

Dedicar una persona a la evidencia mientras el operador y el analista siguen
jugando. La ventaja es convertir el trabajo ya hecho en una explicación clara,
reproducible y verificable. El jurado puede revisar un fallo, una decisión y una
prueba con más facilidad que una lista larga de ideas sin medición.

Antes de una nueva mejora, contestar:

1. **Qué decisión cambia**: precio, selección, atención del operador o fiabilidad
   de lo que mostramos. Una propuesta debe tener un uso concreto.
2. **Qué evidencia tenemos**: dato oficial, observación pública, prueba offline o
   diario del operador. No mezclar una simulación con un resultado en vivo.
3. **Cómo comprobamos el resultado**: regresión, replay o liquidación confirmada.
4. **Qué mostramos**: comando reproducible, fuente/tick y un antes/después.
5. **Qué sigue sin saberse**: límites privados, causalidad, rúbrica o rendimiento
   real. Una mejora sin comprobación disponible se mantiene como hipótesis.

Los fallos que pueden perder dinero, duplicar acciones o falsear evidencia tienen
prioridad. Después, una demo terminada y una medición útil. Una función nueva
entra cuando mejora una decisión o aporta evidencia que podamos enseñar dentro
del tiempo disponible. No cambiar límites del agente para mejorar el relato.

## Orden práctico de trabajo

| Prioridad interna | Entrega concreta | Criterio de terminación |
|---|---|---|
| P0 | Demo que abre sin claves/red y explica la arquitectura | Cuatro secciones, datos fechados y exportación agregada. |
| P0 | Un resultado del juego con fuente | Liquidación exacta, carta, precio y tick; beneficio privado desconocido si falta diario. |
| P1 | Una decisión respaldada por evaluación | Ejemplo: mantener auto porque el broker probado no supera su baseline sintético. |
| P1 | Un fallo detectado y bloqueado | Foto parcial → propuestas bloqueadas; prueba de regresión reproducible. |
| P1 | Explicar una inferencia y sus límites | Marcador atrasado, mercado relativo, probabilidad Affinity no equivalente a certeza. |
| P2 | Confirmar formato, duración y entrega | Respuesta de organización; mensaje preparado en jury-runbook, aún no enviado. |

No asignamos puntos estimados del jurado a estas filas. Una prueba negativa
también aporta evidencia de criterio: el RAG pequeño no mejoró Recall y el broker
local no superó greedy. Enseñar por qué conservamos el baseline evita prometer
ganancias que no hemos observado.

## Demo actualizada desde la misma foto del analista

```bash
python3 -m market_harness refresh
python3 -m jury.report --market-snapshot runs/market-harness/snapshot.json
# Abrir runs/jury/demo.html
```

El escaneo incluye el catálogo público; la segunda orden es totalmente offline.
El informe separa `snapshot_tick` del marcador y el tick del reloj, y muestra
solo liquidaciones públicas verificadas del equipo dentro de la ventana.
Un fallo de lectura aparece como bloqueo y parejas **indeterminadas**.
Precio, comisión observada y cambio del marcador no se convierten en beneficio
privado ni en puntos obtenidos del jurado. El aceptante no siempre se identifica.

Para regenerar el paquete estático que publica el equipo, revisar los resultados
antes de su despliegue:

```bash
python3 -m jury.report --market-snapshot runs/market-harness/snapshot.json \
  --output jury --team-output analista
```

No hay despliegue automático. La demo permite enseñar una foto parcial con
honestidad: conserva las observaciones confirmadas y explica qué no se pudo leer.
La presentación de tres minutos sigue en [jury-runbook.md](jury-runbook.md).

## Caso que podemos contar hoy

«El mercado se reanudó. Revisamos los 18 equipos y todos los mercados abiertos.
Confirmamos una venta RET-08 de t18 a t04 por 27 P en el tick 645. Detectamos
que el marcador del tick 640 ya nos ponía terceros: esa subida precede a la venta.
También falló una lectura de mercado; el harness bloqueó propuestas. Añadimos
fecha de cada fuente, historial deduplicado y pruebas que impiden convertir
ofertas desaparecidas en liquidaciones».

Esto demuestra observación y controles; no demuestra que el nuevo radar causase
la venta, ni que v18 gane puntos: nuestro puesto sigue sin tratos observados.
Los datos y los nueve nuevos tratos entre equipos están en
[market-live-2026-10-03.md](market-live-2026-10-03.md). La explicación de los
controles y las pruebas anteriores está en [SHOWCASE](../SHOWCASE.md).
