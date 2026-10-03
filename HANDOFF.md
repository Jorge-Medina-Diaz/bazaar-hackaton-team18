# Traspaso actual — 2026-10-03

## Radio Rastro y cambios para t18 (Claude) — sáb 3 oct, tick ~430

- Rubén pidió vigilar la radio, avisar en su máquina con lo relevante para t18 y subirlo a main. Añadidos `radio.py`, `tests/test_radio.py` y `docs/radio.md`. Solo lecturas públicas sin clave; `agent/` intacto (code_hash b96eb95d4edb5656).
- Investigado: las noticias solo las emiten los organizadores (rutas admin); los equipos no pueden publicar. Las ciertas mueven el mercado. El vigilante verifica con el feed (precios del dealer en los barrios citados frente al control de la misma rareza) y avisa de cambios exactos (puesto, adelantamientos, dealers, menús, barrios, acuñaciones, niveles, próximo evento).
- Pruebas: 19 tests del vigilante, 6 mutaciones detectadas, suite completa 816 OK (Python 3.14); notificación real probada en macOS con texto hostil sin ejecución.
- Siguiente paso: dejarlo corriendo (`python3 radio.py --watch`) en una máquina que no sea el ejecutor o junto a él, y actuar solo sobre noticias `confirmada` bajo el Gate.

## Integración autorizada por Rubén

- Repositorio: Jorge-Medina-Diaz/bazaar-hackaton-team18. Preparación aislada en
  `/Users/ruben/projects/bazaar-hackaton-team18-integration`, rama
  `codex/integrate-harnesses`, desde origin/main ae73a8a.
- Integradas `harness-v2` de Jorge (incluidas las correcciones en vivo hasta
  5dcbab1) y `codex/evaluation-harness` 562f312. Conservados los commits originales.
- Gate, transporte, contratos, tácticas, SDK y config/plan.json son idénticos a
  la rama de Jorge. JEV/RAG permanecen como evaluaciones independientes; no se
  conectan al World ni deciden cifras, permisos o aceptaciones.
- README resuelto conservando el arranque v2 y añadiendo las evaluaciones. Los
  imports del selector/broker antiguo se sustituyeron por copias puras offline
  en harness/legacy_baseline.py, legacy_broker.py y broker_sim.py, sin CLI/red ni
  escrituras. No se importa ni reactiva archive/.
- El visor lee el WAL logs/run/journal.jsonl, muestra modo/tick/tácticas/pendientes
  y comprueba la cadena sin reparar archivos. HTTP ok/queued no se convierte en
  liquidación ni en memoria de desenlace. No sirve snapshots ni untrusted.jsonl.
- La prueba de extremo a extremo usa ahora el runner v2 y servidor falso. Se
  añadieron regresiones para modo dry, lectura sin mutación, cadena/corte de línea
  y ausencia de falsas liquidaciones. Los fallos iniciales de imports y fixtures
  se corrigieron respetando el candado de escritor de Jorge.
- Detectado un fallo de aislamiento en tests/test_cli.py: el selftest ejecuta
  runner antes de clockcheck y la hora del reloj falso quedaba en _PUBLIC_LAST,
  provocando una espera enorme al cambiar a monotonic. Corregida solo la fixture
  de clockcheck mediante parche temporal del limitador; transporte/CLI de
  producción intactos. Regresión con _PUBLIC_LAST=10^12 pasa en 1,008 s.
- Pruebas/resultados finales se registran debajo antes del push. Ninguna operación
  real del juego ni llamada de pago a JEV durante esta integración. Claves,
  contraseñas, state/, logs/ y runs/ excluidos del contenido publicado.

## Próximo paso del único operador

Leer docs/integration-handoff.md. Jorge actualiza main cuando pueda detener el
runner entre operaciones, conservando archivos locales; repite selftest porque
cambia el hash del código. Comprueba status y abre run_traces_tunnel.py --logs logs
desde su máquina. Los demás observan por el visor y proponen cambios; no arrancan
un segundo ejecutor. Todavía falta validar el visor con sus logs reales y enlazar
desenlaces v2 con liquidaciones antes de alimentar RAG.

Las sesiones anteriores siguen en archive/docs/HANDOFF.md.

## Validación final

- Suite completa: 778 casos ejecutados en 90,176 s; 776 pasaron, dos omitidos,
  cero fallos/errores. Las salidas STOP/candado son casos deliberados de las
  pruebas contra el servidor falso, no operaciones del juego real.
- Panel web: 5/5 pruebas pasaron. Trazas v2: 16/16 pasaron, incluido runner real
  contra el servidor falso y archivo cortado sin reparación.
- Harness económico histórico PASS: 127 casos de mercado, 13 de arbitraje;
  preflight JEV: nueve solicitudes preparadas y 63 preguntas, sin red.
- `bazaar.py status` local: sin STOP, candado libre, sin tácticas armadas ni diario
  operativo. Escaneo de credenciales/archivos runtime y diff --check correctos.
- Selftest final: seis etapas GREEN: core 396, hygiene 27, dealers 155, rastro 42, closer 63 y duels 122. Exit 0. Las etapas comparten pruebas; no sumar esas cifras como casos independientes. El archivo de aprobación local no se publica y el operador debe repetir selftest tras actualizar.


## Entrega para jurado — 2026-10-03, Codex

- Pull de main 98bdfe0 antes de trabajar; rama codex/jury-evidence. El analizador se llama affinity.py, no infinity.py.
- SHOWCASE actualizado a arquitectura v2: corregidos pesos de rondas, fórmula simplificada de ganancias y referencias obsoletas. Tres fixes con commits; solo 5dcbab1 añade una regresión específica en ese commit.
- Demo de cuatro secciones en jury/demo.html, plantilla y CLI python3 -m jury.report --refresh. Cuatro GET públicos, una sola vez, sin clave, escritor ni modelo. Informe agregado en jury/evidence.json; no contiene feed ni diario bruto.
- Snapshot oficial 330, captura 2026-10-03T08:56:16Z: t18 primero, 28,32 puntos, dos páginas, 32/50 casillas. Reloj separado tick 332, abierto/activo. Feed: 500 eventos, ticks 311–332; probabilidades Affinity inferidas solo sobre esa ventana.
- Lectura opcional del diario: verifica snapshot de bytes y cadena sin reparar; cuenta ventanas live, nunca convierte HTTP ok ni dry en liquidación. Cadena consistente no demuestra autenticidad. No hay diario operativo en este ordenador; RET/40 minutos y 8.º→2.º siguen pendientes.
- docs/jury-runbook.md: guion provisional de tres minutos, rotación, mensaje para organización, instrucciones de integración. docs/scoring-evidence.md: fórmulas con etiquetas oficial/medido/inferido y huecos.
- Validación: 33/33 tests pasaron (11 jury, 10 Affinity, 12 arquitectura) con Python 3.14; diff --check correcto. Demo abierta en navegador; navegación, filtros y marcador comprobados. Affinity de main requiere Python 3.10+; Python 3.9 local falla en ese módulo. CLI nueva avisa claramente, no modifica el modelo.
- agent/, bazaar.py, SDK y config/plan.json idénticos a origin/main; code_hash operativo intacto. No se ejecutó el bot ni se reinició ningún operador.
- Rubén autoriza subir esta entrega. Publicación por fast-forward, sin force y conservando avances remotos. Próximo paso: abrir demo; obtener formato del jurado y reporte agregado del diario de Jorge para completar afirmaciones pendientes. Aviso running remote sin captura: origen sin identificar; acceso GitHub funciona.

- Antes del push main avanzó a adfd048 (merge de Santi: rivals.py, affinity --history y notas). Rebase limpio sobre ese commit, conservando todas sus modificaciones; 33/33 tests y diff --check repetidos correctamente. Ningún diff en agent/, bazaar.py, SDK ni plan frente a ese main actualizado.
