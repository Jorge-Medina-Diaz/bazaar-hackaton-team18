# Estudio de dealers en equipo (Rubén/Claude + Santi): cómo aportar sin pisarse

Rama: `claude/pilar-guia` (PR #3). Todo fuera de `agent/` → no cambia `code_hash`.

## Quién escribe dónde

| Qué | Dónde | Quién |
|---|---|---|
| Feed público capturado (datos crudos) | `data/feeds/<autor>/chunk-*.jsonl` | cada uno **solo en su carpeta** (`ruben`, `santi`) |
| Notas y hallazgos propios | `docs/estudio/<autor>.md` | cada uno en el suyo |
| Parámetros aprendidos | `docs/dealer_params.json` / `.md` | **nadie a mano**: se regeneran |
| Guías | `harness/pilar_guide.py`, `harness/picaros_guide.py` | proponer cambios por PR/comentario |

## Aportar datos (Santi)

```bash
git checkout claude/pilar-guia && git pull --rebase
python3 -m harness.feed_store add santi logs/feed.jsonl     # o cualquier JSONL/JSON del feed público
python3 -m harness.feed_store verify                        # debe salir "conflicts": []
python3 -m harness.dealer_tuner                             # regenera docs/dealer_params.* con TODOS los autores
python3 -m unittest tests.test_pilar_guide
git add data/feeds/santi docs/dealer_params.* docs/estudio/santi.md
git commit -m "estudio: datos de santi" && git pull --rebase && git push
```

Si `git pull --rebase` choca en `docs/dealer_params.*`: `git checkout --theirs docs/dealer_params.*`, volver a ejecutar `python3 -m harness.dealer_tuner`, `git add` y `git rebase --continue`. Son derivados: regenerarlos nunca pierde datos.

## Por qué no se pierde nada
- Cada aportación crea un fichero **nuevo e inmutable**; nunca se reescribe uno existente.
- Los eventos se unen por su `id` del servidor; los repetidos entre autores se cuentan una vez.
- Si un mismo `id` llega con contenido distinto, `verify` lo marca como conflicto (sale con código 1).
- Solo datos públicos del feed: **nunca** claves, `/api/me`, `equipo.json` ni valores privados.
