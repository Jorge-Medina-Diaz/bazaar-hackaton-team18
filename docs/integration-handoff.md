# Entrega para el agente de main y el equipo

## Mensaje para el equipo

Ya tenemos harness offline, memoria RAG con filtros, visor compartido y cliente
JEV con controles. Se preservó el trabajo de Claude sobre trazas y se completó
la instalación/prueba de cloudflared con una demo aislada. Los túneles quedaron
cerrados; no se abrió el visor con datos reales del ejecutor.

JEV real: **18 solicitudes, 90 juicios Noul**, coste declarado total
**0,001343286 USD**, cero operaciones del juego. En patrones acertó 63/63 juicios
(21 distintos sobre tres casos repetidos tres veces); en reranking no mejoró
recall. No se entrenaron pesos ni se probó una nueva negociación en vivo.

Los datos públicos permiten estudiar 27 liquidaciones de otros equipos con
Abuela, pero no sus mensajes ocultos, valores privados ni beneficios.
No tenemos conversaciones crudas de Chato en la máquina: usamos una nota con
fuente. Informe: [jev-real-testing.md](jev-real-testing.md).

## Destino y orden de integración

Repositorio correcto: `Jorge-Medina-Diaz/bazaar-hackaton-team18`.
Rama de entrega: **`codex/evaluation-harness`**, basada en `origin/main` `ae73a8a`.
La carpeta `/Users/ruben/projects/hackathon` es el punto de entrada compartido,
no el checkout del repositorio de Jorge. Código local de esta entrega:
`/Users/ruben/projects/bazaar-hackaton-team18-harness`.

1. En el repositorio correcto, ejecutar `git fetch origin`, comprobar rama y
   cambios locales. Conservar cambios de otros; no usar reset/clean ni push forzado.
2. Leer esta entrega y revisar `origin/main...origin/codex/evaluation-harness`.
   Integrar la rama completa mediante su PR; no copiar archivos sueltos perdiendo
   tests o contratos. Esta entrega no modifica el bucle real del juego.
3. Ejecutar los comandos offline de abajo en la versión integrada. El baseline
   puede mostrar fallos deliberadamente: se exige que el candidato pase, no que
   se borren los fallos del agente original de las métricas.
4. En la máquina del ejecutor, verificar el visor con logs reales y `--check`.
   La memoria solo admite conversaciones terminadas y distingue origen/alcance.
   No enlazar acuerdos y liquidaciones por precio/tick sin identificador explícito.
5. Añadir JEV primero como observador: registrar señales, contraste humano y
   resultados reales. Mantener búsqueda contextual como referencia; no activar
   automáticamente reranking como reemplazo porque no ganó recall en el piloto.
6. Antes de consumir recomendaciones, mantener un único ejecutor y volver a
   validar oferta estructurada, saldo, comisiones, inventario, tick, cuotas,
   máximo/mínimo y liquidaciones pendientes. `DecisionGate` es experimental/local,
   no un bloqueo distribuido. JEV nunca modifica límites ni autoriza una operación.
7. Para nuevas evaluaciones, separar entrenamiento/ajuste de evaluación por hilo
   y tiempo; no usar el desenlace futuro de un caso para decidir un tick anterior.

## Comprobaciones reproducibles

```bash
python3 -m unittest discover -s tests
python3 run_harness.py --output runs/harness-baseline.json
python3 run_jev_patterns.py
```

El último valida los tres casos históricos minimizados publicados en
`tests/fixtures/jev-history.json` sin red. Para probar inferencia real:

```bash
python3 run_jev_patterns.py --live --key-file /ruta/privada/openrouter.key
```

La clave se mantiene fuera del repo, archivo 0600, o en `OPENROUTER_API_KEY`.
No usar la clave del Bazaar ni poner secretos en el visor. Cada evaluación está
limitada a nueve solicitudes, sin reintentos; configurar también límite económico
por clave en OpenRouter. Los límites/retención de la cuenta no se cambiaron aquí.

En la máquina que produce los logs:

```bash
python3 run_traces.py --logs logs --check
python3 run_traces_tunnel.py --demo
```

La demo abre un túnel temporal **con datos inventados**. Contraseña fuerte en
`runs/traces.password`, fuera de Git; usuario `equipo`. Ctrl+C cierra visor y
túnel. `--logs logs` en el arranque del túnel comparte logs reales con quienes
reciban enlace y contraseña, así que elegir explícitamente ese modo cuando toque.

## Archivos y responsabilidades

| Componente | Archivos | Estado |
|---|---|---|
| Harness económico/selector | `run_harness.py`, `harness/market.py`, `cases.py`, `runner.py` | Offline; no conectado al ejecutor |
| Recuperación RAG | `harness/retrieval.py`, `rag_eval.py`, `jev_plan.py`, `run_rag_eval.py` | FTS contextual, filtros y fuentes; no embeddings |
| JEV protegido | `harness/jev_security.py`, `run_jev_eval.py` | Inferencia de relevancia, sin permisos de trading |
| Patrones históricos | `harness/jev_patterns.py`, `run_jev_patterns.py`, fixture pública | Tres casos × tres repeticiones; no entrenamiento |
| Historial de rivales | `harness/dealer_history.py` | Estadísticas públicas, sin joins inventados |
| Trazas compartidas | `agent/trace.py`, `run_traces.py` | Trabajo de Claude preservado, auth/caché reforzadas |
| Túnel | `run_traces_tunnel.py` | cloudflared instalado en esta máquina; demo HTTPS probada |
| Resultados/seguridad | `docs/harness.md`, `rag-evaluation.md`, `jev-security.md`, `jev-real-testing.md`, `evaluations/` | Fuentes, límites y métricas |

No se publican claves, contraseñas, feed completo, bases privadas ni informes
con cuerpos de mensajes. `runs/` y `logs/` siguen ignorados por Git. La fixture
histórica publicada está minimizada y separada de las simulaciones inventadas.

## Lo pendiente

- Validar visor y conciliación con los logs reales del ejecutor.
- Evaluar casos nuevos y ataques semánticos; los tests del código no certifican
  inmunidad del modelo a instrucciones adversarias.
- Medir ganancia/ticks en una prueba real controlada, después de observación.
- Integrar el arbiter en el único ejecutor si se decide consumir recomendaciones.
- Confirmar presupuesto y preferencias de privacidad/retención de OpenRouter.
