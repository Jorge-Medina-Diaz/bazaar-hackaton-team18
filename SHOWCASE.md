# Team 18 · Negociar, medir y corregir

The Bazaar · Cromos de Madrid · Jorge, Rubén y Santi · Actualizado 3 de octubre de 2026.

**Idea:** un agente que decide con valor marginal, opera por una única Gate y
compara sus predicciones con resultados. El equipo separa operación, análisis y
preparación del jurado; los roles rotan, la clave permanece con el operador.

**Abrir la demo:** [jury/demo.html](jury/demo.html). Cuatro secciones con datos
públicos fechados. [Guion y actualización](docs/jury-runbook.md). Actualizar los
datos requiere Python 3.10+; abrir la demo ya generada no requiere Python.

## 1. Qué problema resolvemos

Una misma carta vale distinto para cada equipo. La primera copia, los duplicados,
el cierre de una página, las comisiones y los sobres pendientes cambian el valor
marginal. Regatear requiere también respetar cuotas, paciencia y reloj.

Según [RULES.md](RULES.md#scoring), negociación aporta 30 puntos, mercado 30 y
jurado 40. El número de tratos no puntúa. El marcador es relativo y se actualiza
por instantáneas: subir de puesto no demuestra por sí solo una mejora del código.

## 2. Cómo controlamos la ejecución

```text
Sensor → World → tácticas → Intent → Gate/guardas → transporte → diario
                                   ↑                     ↓
                           límites económicos     calibrador
```

- [Gate](agent/gate.py): única vía de escritura; valida estructura, cuotas,
  frescura, caja, valor y permiso antes del transporte.
- [World](agent/world.py): las decisiones usan campos estructurados. El texto
  ajeno no fija precios ni aceptaciones.
- [Ejecución](agent/execution.py): candado local de escritor; un solo operador
  conserva la clave. Dry permite revisar propuestas sin escrituras al juego.
- [Runner](agent/runner.py): selftest y etapas aprobadas con el mismo hash antes
  de operar. STOP y pausas por táctica.
- [Diario](agent/journal.py) y [calibrador](agent/calibrate.py): predicción frente
  a medida, ambigüedad y sorpresas. HTTP ok/queued no equivale a liquidación.
- [Visor](docs/traces.md): solo lectura del diario, sin reparar archivos.

Límite conocido: stop --flatten no garantiza retirar todas las pujas. El operador
las comprueba. El candado es local, no coordina automáticamente dos máquinas.
No afirmamos seguridad absoluta.

## 3. Qué aprendimos y qué estamos probando

### Medición económica

El [registro de conocimiento](docs/knowledge.md) distingue hechos medidos e
inferencias. Reconstruimos valor marginal y comisiones, y observamos diferencias
entre trades con equipos y dealers. Las fórmulas y sus huecos están en
[scoring-evidence.md](docs/scoring-evidence.md).

Los pesos completos de las rondas son 20 % / 40 % / 40 %; la ronda activa cuenta
por su fracción jugada. Sábado y domingo juntos pesan cuatro veces el viernes.
No conocemos toda la fórmula de normalización, la causa del +50 ni la mezcla
exacta de las componentes de mercado.

### Lectura de rivales: Affinity

[affinity.py](affinity.py) y [agent/affinity.py](agent/affinity.py) consideran las
720 asignaciones posibles de seis multiplicadores. Compras, ventas y ofertas
actualizan probabilidades de preferencia por barrio. No revelan beneficios
privados exactos. X-15 documenta validación simulada y una comprobación parcial;
la demo presenta estas salidas como inferencias condicionadas al modelo.

### RAG y JEV

Las [evaluaciones](docs/jev-real-testing.md) permanecen separadas del ejecutor.
JEV no fija límites, arma tácticas ni acepta operaciones. Ensayo real previo:
18 solicitudes, 90 juicios; coste declarado 0,001343286 USD. Los patrones fueron
21 juicios sobre tres casos, repetidos tres veces; no 63 casos independientes.
Recall@3 del RAG: 88,9 %, igual que el orden original. No demostramos mejora de
beneficios ni generalización con este ensayo pequeño.

## 4. Correcciones reales y evidencia de ingeniería

Tres fixes de Jorge, inspeccionados en el historial:

| Commit | Fallo corregido | Evidencia disponible |
|---|---|---|
| [eb863bc](https://github.com/Jorge-Medina-Diaz/bazaar-hackaton-team18/commit/eb863bc) | Peticiones sin cuerpo enviaban JSON null | Cambio de transporte. El commit no añade un test específico. |
| [986bc69](https://github.com/Jorge-Medina-Diaz/bazaar-hackaton-team18/commit/986bc69) | Hilos cerrados agotaban la cuota de apertura | Cambio G04; el commit no añade un test específico. |
| [5dcbab1](https://github.com/Jorge-Medina-Diaz/bazaar-hackaton-team18/commit/5dcbab1) | Oferta de dealer contada dos veces; RET-09 parecía segunda copia | Guardas/higiene y regresión explícita en tests/test_guards.py. |

Integración publicada dca0b63: **778 casos, 776 pasaron, dos omitidos y cero
fallos**, seis etapas selftest GREEN. Sus grupos solapan; no se suman como casos
independientes. [Resultados y limitaciones](docs/integration-handoff.md).
Es una ejecución registrada de la integración, no un resultado nuevo de la demo.

## 5. Resultado del juego: lo verificado y lo pendiente

La demo guarda fecha UTC, ronda y snapshot_tick del marcador público, con una
consulta separada del reloj. Muestra puesto, negociación, mercado y páginas de
t18 sin atribuir causalidad a una táctica. Se puede actualizar sin clave:

```bash
python3 -m jury.report --refresh
# Abrir runs/jury/demo.html
```

La mejora del viernes y la página SAL están documentadas en
[experimentos históricos](archive/docs/experiments.md). Son historia, no estado
actual. Los scripts antiguos están archivados; la arquitectura operativa es v2.

**Pendiente del diario de Jorge:** «8.º a 2.º en una hora», «RET completa en 40
minutos», cada compra RET frente a su predicción y el segundo +50. Una cantidad
de páginas en el marcador no identifica cuáles son ni cuánto tardaron.
El informe opcional del WAL verifica consistencia de cadena y cuenta ventanas
live; no certifica autoría, cada compra individual ni ausencia de ambigüedad.

## 6. Qué mostrar al jurado

1. El problema económico y los roles del equipo.
2. La Gate, dry, candado y parada; límites explícitos de recuperación.
3. Predicción/medición, Affinity y evaluación separada de RAG/JEV.
4. Instantánea fechada, fixes reales, pruebas y próximos experimentos.

Formato, duración y formulario de entrega aún por confirmar con la organización.
[Mensaje preparado y guion provisional](docs/jury-runbook.md).
