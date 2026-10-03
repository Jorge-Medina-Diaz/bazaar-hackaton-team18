"""equipo.json para la pestaña Equipo de la Mesa del Analista (analista/equipo.html).

Solo lectura: client("read") y un GET /api/me por vuelta, redactado y recortado a lo que pinta la página
(caja, tick, cartas, sobres, valor de colección, álbum). Corre solo en la máquina A, la que tiene la clave.
Escribe de forma atómica (tmp + replace) para que el navegador nunca lea un fichero a medias.

  python3 equipo_json.py                    una vez -> state/equipo.json
  python3 equipo_json.py --every 60         cada 60 s, hasta Ctrl+C

En la página: «Elegir equipo.json» (Chrome/Edge) y la página relee el fichero sola cada 15 s.
No dejar el fichero dentro de analista/: esa carpeta se publica en Vercel.
"""
import argparse
import json
import os
import time

from agent.client import client
from agent.redact import redact

ASSET_KEYS = ("id", "kind", "ref", "rarity", "set", "your_value")   # id: la página ajusta con el feed copia a copia


def snapshot(c) -> dict:
    me = redact(c._get("/api/me"))
    return {"id": me.get("id"), "cash": me["cash"], "tick": me.get("tick"), "collection_value": me.get("collection_value"),
            "album": me.get("album"), "assets": [{k: a.get(k) for k in ASSET_KEYS} for a in me.get("assets", [])],
            "written_at": round(time.time(), 1)}


def write(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=os.path.join("state", "equipo.json"))
    ap.add_argument("--every", type=float, default=0, help="segundos entre lecturas (0 = una sola vez); mínimo 20")
    a = ap.parse_args()
    if os.path.abspath(a.out).startswith(os.path.abspath("analista") + os.sep):
        raise SystemExit("--out dentro de analista/ se publicaría en Vercel: elige otra ruta")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    c = client("read")
    while True:
        try:
            d = snapshot(c)
            write(a.out, d)
            print(f"{time.strftime('%H:%M:%S')} tick {d['tick']} caja {d['cash']} cartas "
                  f"{sum(1 for x in d['assets'] if x['kind'] == 'card')} -> {a.out}", flush=True)
        except Exception as e:                     # una lectura fallida no tumba el bucle; el fichero anterior sigue
            print(f"{time.strftime('%H:%M:%S')} error: {str(redact(str(e)))[:200]}", flush=True)
            if not a.every:
                raise SystemExit(1)
        if not a.every:
            return
        time.sleep(max(20.0, a.every))


if __name__ == "__main__":
    main()
