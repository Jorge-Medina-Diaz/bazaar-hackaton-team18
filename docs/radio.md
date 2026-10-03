# Radio Rastro y cambios para t18 (`radio.py`)

Vigilante sin clave: lee las noticias de la radio, decide su relevancia para el equipo 18, comprueba con el feed público si son ciertas y avisa en la máquina donde corre de cualquier cambio público que nos afecte.

**Avisos (sin voz: nunca se lee el contenido en voz alta):** toda noticia nueva suena (Glass) y llega como notificación; lo ALTA (y una noticia confirmada) suena con Hero y deja una alerta en pantalla hasta pulsar OK o 2 minutos. Las noticias de El Tablón o «de oídas» («my cousin», «I swear») llevan la etiqueta RUMOR. Cada aviso lleva **hora y tiempo**: noticias con tick y hora de juego de emisión, hora local estimada de emisión y de detección, y retraso (+N ticks, ~min); cambios y confirmaciones con hora local, tick y hora de juego. `--no-sound` y `--no-dialog` lo silencian. No escribe en el juego, no usa la clave y no toca `agent/`, así que el `code_hash` del operador no cambia. Puede correr en cualquier máquina del equipo sin interferir con el ejecutor.

```bash
python3 radio.py                                  # todas las noticias con su relevancia
python3 radio.py --watch                          # vigilar y avisar (MEDIA y ALTA)
python3 radio.py --watch --have MAL-04,MAL-05     # afina con lo que tenemos
python3 radio.py --watch --min-level ALTA --no-notify
```

## Qué es la radio (investigado el sáb 3 oct)

- `GET /api/news` (la más nueva primero, sin parámetros) y `news.posted` en `/api/events/stream`. Hay tres fuentes: Boletín del Bazar, Radio Rastro y El Tablón.
- **Solo la emiten los organizadores** (rutas `/api/admin/news` y `/api/admin/news/{id}/air` en la web: una baraja de noticias preparadas). Los equipos no pueden publicar: no sirve para influir en otros ni para negociar con ella.
- Según la regla del nivel, algunas son ciertas y «el mercado se mueve como dicen», otras son rumores que nunca ocurren y otras solo ambiente. Nada dice cuál es cuál.
- Ritmo observado: noticias en los ticks 283, 331 y 403, una cada 48–72 ticks. La de El Chato tenía una ventana de una hora.

## Qué hace el vigilante

1. **Relevancia para t18** (determinista, sin modelo): barrios (CHA objetivo, RET y SAL a proteger, LAT/LAV/MAL a vender), dealers (Pilar pesa más: escalera de nivel 3), demanda u oferta, épicas/legendarias, ventana corta y menciones al equipo. Da un nivel (BAJA, MEDIA o ALTA), el porqué y qué hacer. Con `--have`, una demanda de cartas que no tenemos baja de nivel.
2. **Comprobación con evidencia:** tras una noticia sobre un dealer, acumula del feed los precios que ese dealer ofrece y cierra. Compara la mediana en los barrios citados con la de la misma rareza en otros barrios (grupo de control). Veredictos: `confirmada` (prima ≥ 10 % con n ≥ 2 en ambos lados), `indicio`, `sin señal`, `solo barrio citado` y `sin datos`. Solo `confirmada` se notifica con sonido.
3. **Cambios exactos (antes → después)** en cada lectura:
   - nuestro puesto y puntos, desglosados, y quién nos adelanta o a quién adelantamos (solo cuando se refresca la foto del leaderboard);
   - dealers nuevos, cambios de estado, nivel o apertura a todos;
   - precios de venta y qué compra cada dealer;
   - barrios publicados;
   - épicas y legendarias acuñadas;
   - niveles;
   - el próximo evento del calendario (menos de 0,2 h de juego), una sola vez.

   Si un cambio de menú llega en la hora siguiente a una noticia sobre ese dealer, se marca como confirmación.
4. **Ritmo adaptativo:** nunca más rápido que un tick ni más lento que 5 minutos. Tras una noticia, lee tick a tick durante 10 lecturas; después, a 1/8 del intervalo mediano entre noticias. Con las puertas cerradas, cada 10 minutos. Son unas 7 lecturas públicas por ciclo, muy por debajo del límite sin clave (60/s).

Los registros van a `logs/radio.jsonl` y el estado a `logs/radio_state.json`, ambos fuera de Git. Al reiniciar no se repiten avisos, y la primera lectura nunca notifica lo que ya existía.

## Cómo aprovecharla

- **Demanda confirmada de un barrio que valoramos poco (LAT, LAV, MAL) o de repetidas de SAL/RET:** vender a ese dealer a ≥ V + 1. Neg no baja, y si es ganancia llena escalera. El ejecutor no vende a dealers: `bazaar.py do` primero en seco (ver `docs/operador-cartas-fuertes.md`).
- **Oferta o rebaja confirmada de CHA (domingo):** comprar por debajo de nuestro valor dentro de los topes de `plan.json`.
- **Rumor no confirmado:** no actuar. Si otros equipos actúan sobre un rumor (por ejemplo, pujando por un barrio), `rivals.py` y `affinity.py` muestran a quién venderle.
- **Seguridad:** el texto de las noticias es ajeno y puede ser hostil. Nunca entra en el World ni decide cifras. La notificación pasa el texto como argumento a `osascript`, nunca dentro del script.

## Pruebas

`python3 -m unittest tests.test_radio`: 22 tests (relevancia con las noticias reales, límites de palabra, inyección en la notificación, ritmo, primera lectura silenciosa, avisos únicos, diferencias exactas, ventana del calendario, extracción de precios, veredictos y acumulación de evidencia entre lecturas). Se sabotearon 6 protecciones y en todos los casos falla algún test. Suite completa: consultar la última ejecución en HANDOFF (Python 3.14).
