# Integración de harness-v2 y evaluación — 2026-10-03

Rubén autorizó integrar la rama `harness-v2` de Jorge y
`codex/evaluation-harness` en main. Se conserva la arquitectura de Jorge:
`bazaar.py` → tácticas → Gate → transporte. Contratos, SDK y cifras de las tácticas
no se alteran. Ningún comando de evaluación arma tácticas ni escribe al juego.

## Qué se adaptó

- README mantiene el arranque de harness-v2 y enlaza las evaluaciones.
- Los selectores y broker históricos puros se aislaron en `harness/legacy_*` y
  `harness/broker_sim.py`. No se reactivan scripts archivados ni otro ejecutor.
- RAG y JEV mantienen sus controles y resultados medidos. JEV sigue como evaluación
  independiente; no se inserta en la decisión numérica ni en el World.
- El visor admite el diario v2 `logs/run/journal.jsonl` además del formato anterior.
  Distingue dry/live y verifica la cadena sin repararla. `ok` HTTP no se indexa
  como trato confirmado. Los logs de texto ajeno no se sirven.
- La prueba del visor usa el runner v2 real con el servidor falso, reemplazando
  el haggler archivado. Se conservan pruebas de autenticación y reconciliación.

## Instrucciones para Jorge, único operador

1. Comprobar commit y estado local. Actualizar código cuando el proceso pueda
   detenerse entre operaciones; evitar modificar módulos debajo de un runner activo.
   Conservar `.env`, `state/`, `logs/` y `runs/`; no usar reset/clean ni borrar candados.
2. Leer `docs/LEEME-EQUIPO.md`, `CLAUDE.md` y este archivo. Tras actualizar, volver a
   ejecutar `python3 bazaar.py selftest`: el código nuevo cambia el hash de aprobación.
3. Ejecutar `python3 bazaar.py status` y revisar STOP, candado, pausas y pendientes.
   Solo el ordenador de Jorge opera; Rubén/Codex/Claude observan y proponen cambios.
4. Abrir observabilidad desde esa máquina:

```bash
python3 run_traces.py --logs logs --check
python3 run_traces_tunnel.py --logs logs
```

Compartir enlace y contraseña con el equipo por su canal privado. La contraseña
está en `runs/traces.password`, usuario `equipo`; no usar claves del juego/modelo.
5. Mantener las tácticas que el operador haya decidido armar. Esta integración no
   cambia sus permisos, no arranca el agente y no autoriza otra máquina ejecutora.

## Validación offline

```bash
python3 -m unittest discover -s tests -t .
node --test website/worker.test.mjs
python3 run_harness.py --output runs/integration-harness.json
python3 run_jev_patterns.py
python3 bazaar.py status
```

## Métricas históricas y límites

JEV: 18 solicitudes reales, 90 juicios, coste declarado 0,001343286 USD.
Patrones: 63/63 coincidencias sobre 21 juicios distintos de tres casos repetidos
(Abuela y nota documental de Chato). Reranking: recall@3 88,9 %, igual al baseline.
No se entrenaron pesos ni se hicieron negociaciones reales durante la evaluación.
Informe: `docs/jev-real-testing.md`. El feed público permite estudiar 27
liquidaciones de rivales, no sus valores privados o beneficios.

Pendiente: medir mejora en casos nuevos, enlazar desenlaces v2 a liquidaciones
antes de alimentar memoria y validar el visor con logs del ejecutor de Jorge.
