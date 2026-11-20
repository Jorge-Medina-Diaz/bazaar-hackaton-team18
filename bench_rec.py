"""Grabadora del Market Test: SOLO LECTURA del libro de nuestro puesto (GET /api/broker/book), cada 3 s.

Usa agent/tactics/bench.BenchRecorder: la clave del puesto (starter_broker_key de /api/me) vive solo en memoria y cada
línea se redacta y se comprueba antes de escribirse (SecretLeak si se colara). Nada de match ni announce.

    python3 bench_rec.py        # graba en logs/bench_book.jsonl una línea por tick con el libro
"""
import sys
import json
import os
import time
import urllib.request
from pathlib import Path

from agent.client import _load_env
from agent.contracts import PROD_URL, Secrets
from agent.tactics.bench import BenchRecorder

OUT = Path(__file__).resolve().parent / "logs" / "bench_book.jsonl"


def _get(url, path, headers):
    req = urllib.request.Request(url + path, headers={"User-Agent": "t18-bench-rec", **headers})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    _load_env()
    url = os.environ.get("BAZAAR_URL") or PROD_URL
    me = _get(url, "/api/me", {"X-Team-Key": os.environ["BAZAAR_KEY"]})
    secrets = Secrets(starter_broker_key=me.get("starter_broker_key"))
    if not secrets.starter_broker_key:
        raise SystemExit("bench_rec: /api/me has no starter_broker_key")
    rec = BenchRecorder(lambda path, headers: _get(url, path, headers), secrets, OUT)
    while True:
        try:
            tick = _get(url, "/api/clock", {}).get("tick")
            if rec.poll(tick):
                print(f"tick {tick}: recorded ({rec.recorded})", flush=True)
        except Exception as e:  # noqa: BLE001 - a failed read never stops the recorder
            print(f"read failed: {e.__class__.__name__}", flush=True)
        time.sleep(3)


if __name__ == "__main__":
    if {"-h", "--help"} & set(sys.argv[1:]):
        print(__doc__)
        sys.exit(0)
    main()
