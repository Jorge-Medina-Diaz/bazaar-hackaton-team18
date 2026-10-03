# Compatibilidad con harness-v2 — 3 de octubre

El visor lee también `logs/run/journal.jsonl`: decisiones, resultados, rechazos,
alertas, pausas y ticks. Muestra modo dry/live, último evento, tácticas, pendientes,
cadena válida y STOP. Es un lector: no modifica ni repara el diario y no ejecuta
operaciones. `--check` devuelve fallo si la cadena v2 está corrupta o cortada;
una línea aún en escritura puede aparecer cortada hasta la siguiente lectura.

En la máquina de Jorge, desde el checkout actualizado de main:

```bash
python3 bazaar.py status
python3 run_traces.py --logs logs --check
python3 run_traces_tunnel.py --logs logs
```

El túnel exige contraseña local privada (usuario `equipo`). Las respuestas HTTP
`ok` o `queued` no demuestran liquidación. La memoria histórica y el lector antiguo
se conservan separados. `untrusted.jsonl` y snapshots privados no se sirven.

### Desenlaces v2 para el RAG (`harness/outcomes.py`)

El único desenlace aceptado es la fila `measure` del calibrador: una liquidación
detectada en el estado del juego, unida al `intent` que la causó y juzgada contra
su predicción por el cambio real de nuestros puntos. Entra en memoria como caso
privado (`local-team`, fase `settled`) solo si:

- la cadena del diario es válida (si no, no se indexa nada);
- la medida es de un solo trato (`ambiguous` falso) y su origen es solo el arnés;
- el veredicto no es `excluded`, `unattributed`, `info` ni `out_of_band`;
- el `intent` es `accept`, `list_offer` o `say` y consta como enviado.

Los tratos con dealers usan el id `thread-<id>` y se fusionan con el hilo público
del feed; los tratos con equipos usan `outcome-<intent>`. El visor y `--check`
muestran `outcomes` (medidas, indexadas, omitidas por motivo). Está fuera de
`agent/`: no cambia el `code_hash` del operador.

Verificación: con el runner v2 real contra el servidor falso (semillas 11, 3, 7 y 23)
se indexaron 5 desenlaces y los 5 coinciden con el libro de liquidaciones del
juego en carta, lado, contraparte, precio y efecto en puntos. Es conservador:
en la semilla 11 hubo 8 liquidaciones y se indexaron 2; el resto quedó fuera por
ambigüedad o veredicto. Falta validarlo con el diario real de Jorge.

Lo siguiente describe el formato anterior, que sigue admitido por compatibilidad:

# Trazas del equipo y memoria RAG

`run_traces.py` muestra en directo qué hacen los agentes: conversaciones, ofertas propias y del dealer, aceptaciones, cierres y errores. Lee `logs/*.jsonl` (lo que ya escriben `haggle`, `run_dealer`, `run_loop` y `duels` vía `agent/journal.py`). No llama al juego ni a modelos y no tiene coste.

```bash
python3 run_traces.py                                     # solo esta máquina: http://127.0.0.1:8019
TRACES_PASSWORD=... python3 run_traces.py --host 0.0.0.0  # el equipo en la misma red: http://<IP>:8019
python3 run_traces.py --check                             # informe de conciliación; sale con 1 si hay descuadre
```

- Se arranca en la máquina del **único ejecutor**, junto a sus logs. La página se actualiza cada 3 s.
- Abrirlo a la red sin `TRACES_PASSWORD` se rechaza: los logs contienen nuestros límites de precio. Los campos con nombre de clave, token o contraseña se redactan.
- Para compartir por Internet, usar el arranque protegido de abajo. La contraseña se mantiene; el visor escucha solo en `127.0.0.1` y el enlace público usa HTTPS. El modo de red local con HTTP no cifra la contraseña.

## Túnel protegido y demostración

`cloudflared` 2026.9.1 está instalado en esta máquina mediante Homebrew. No se ha configurado un servicio al iniciar sesión ni creado una cuenta Cloudflare. Si falta en otra máquina:

```bash
HOMEBREW_NO_AUTO_UPDATE=1 brew install cloudflared
```

Para probar con **datos inventados**, sin juego ni modelos:

```bash
python3 run_traces_tunnel.py --demo
```

Genera únicamente `runs/traces-demo/logs/`: una compra simulada con Abuela, una conversación abierta con Chato y un error simulado. Construye la memoria con esos mismos datos. No sirve para medir persuasión ni rendimiento real.

El comando crea una contraseña aleatoria en `runs/traces.password` con permisos `0600`, fuera de Git, y muestra su **ruta**, nunca su contenido. Abre el archivo localmente para consultar la contraseña; en el navegador usa usuario `equipo`. El comando imprime la URL temporal. No compartas la clave del Bazaar o de OpenRouter como contraseña del visor.

Para logs reales del ejecutor, en la máquina que los produce:

```bash
python3 run_traces_tunnel.py --logs logs
```

Esto comparte información privada de estrategias con quien tenga la contraseña: úsalo solo cuando el equipo decida abrir el visor. El túnel sirve la página y `/state.json`; no sirve archivos arbitrarios, no expone una terminal y no ejecuta compras ni decisiones de JEV. Ctrl+C y SIGTERM cierran tanto el visor como el proceso de túnel. No se inicia ningún servicio permanente.

El túnel rápido no requiere cuenta o dominio; su URL cambia cada vez y no ofrece garantía de disponibilidad. [Documentación oficial de Cloudflare](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).

## Una sola fuente de verdad

`agent/trace.py` construye un único modelo de lectura que usan **el visor y la memoria**, de modo que no pueden contradecirse:

- `read()`: eventos con id estable `<stream>:<línea>`. Las líneas a medio escribir se cuentan y se leen completas en la siguiente pasada. Se ignoran los muestreos (`information`, `dashboard`, `feed`).
- `threads()`: una conversación por dealer e hilo.
- `team_cases()`: solo conversaciones **terminadas** entran en la memoria, con visibilidad `local-team`.
- `merge()`: si el hilo también está en el feed público, se fusiona en **un único caso** (`thread-<id>`) en vez de duplicarlo. Si el dealer no coincide, no se fusiona.
- `reconcile()`: comprueba dealer, lado y que el precio liquidado aparezca en el feed. El visor y `--check` lo muestran.

`harness/retrieval.py` no se ha modificado.

## Pruebas

`python3 -m unittest tests.test_trace`: el haggler real con el dealer falso escribe el journal, y a partir de ahí se comprueban las conversaciones, el caso privado, la conciliación con el feed y la recuperación. También se prueban líneas cortadas, la redacción de secretos, las conversaciones abiertas, el descuadre de precio o dealer, el determinismo, la autenticación y `--check`.

Carga medida en local con datos sintéticos (1.000 conversaciones, 13.680 eventos y 20.000 muestreos ignorados): unos 110 ms por reconstrucción, en caché 2 s, y 325 KiB por respuesta. Con un escritor y un lector concurrentes, 5.000 filas sin errores, pérdidas ni duplicados. No se ha probado todavía con logs reales del ejecutor.

Comprobación del 3 de octubre con fixture aislado: 15/15 tests de trazas y arranque pasan (cinco añadidos). Verificados por HTTPS: `/` y `/state.json` sin contraseña devuelven 401; estado autenticado devuelve 200, un caso RAG privado sin duplicados, conversación abierta excluida y secreto ficticio redactado. `--check` devuelve 0 y conciliación correcta. El visor y el túnel de prueba quedaron detenidos. No hubo llamadas al juego ni a modelos.

Corregidos dos fallos con regresiones: credenciales Unicode/malformadas ya fallan de forma segura; la caché distingue carpetas de logs para no mezclar dos visores en el mismo proceso. La página incluye políticas del navegador para impedir framing y recursos externos; el texto del dealer se dibuja como texto, sin ejecutar HTML.
