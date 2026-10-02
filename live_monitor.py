"""Observador del Bazaar: únicamente GET, cada cinco segundos, sin agente."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
import threading
import time

from bazaar_sdk import Bazaar


POLL_SECONDS = 5


def now():
    return datetime.now(timezone.utc).isoformat()


def read_key(path=None):
    if path is None:
        key = os.environ.get("BAZAAR_KEY", "").strip()
    else:
        content = Path(path).read_text(encoding="utf-8").strip()
        if "=" in content:
            entries = [line.split("=", 1)[1].strip().strip("\"'")
                       for line in content.splitlines()
                       if line.strip().startswith("BAZAAR_KEY=")]
            key = entries[0] if entries else ""
        else:
            key = content
    if not key or any(char.isspace() for char in key):
        raise ValueError("Falta BAZAAR_KEY en el entorno o en el archivo local indicado")
    return key


def rows(payload, field):
    data = payload if isinstance(payload, list) else payload.get(field, [])
    if not isinstance(data, list):
        raise ValueError("Formato de respuesta inesperado")
    return data


def asset_view(asset):
    return {"id": asset["id"], "ref": asset["ref"], "kind": asset.get("kind", "card"),
            "name": asset.get("name", asset["ref"]), "paid": None,
            "value": asset.get("your_value"), "serial": asset.get("serial")}


def offer_view(offer):
    # Solo campos que necesita el panel; nunca devuelve claves del equipo o del broker.
    return {field: copy.deepcopy(offer[field]) for field in
            ("id", "maker", "to", "status", "give", "want", "final", "venue", "thread_id")
            if field in offer}


def validate_payload(name, payload):
    if name == "inventario y saldo":
        if not isinstance(payload, dict) or type(payload.get("cash")) not in (int, float):
            raise ValueError("Saldo sin verificar")
        for asset in rows(payload, "assets"):
            asset_view(asset)
        if "assets" not in payload:
            raise ValueError("Inventario ausente")
    elif name == "reloj":
        if not isinstance(payload, dict) or type(payload.get("tick")) is not int:
            raise ValueError("Reloj sin verificar")
    else:
        field = "offers" if name == "ofertas" else "threads"
        if isinstance(payload, dict) and field not in payload:
            raise ValueError("Lista ausente")
        for item in rows(payload, field):
            if not isinstance(item, dict) or "id" not in item or "status" not in item:
                raise ValueError("Registro sin verificar")
    return payload


class LiveMonitor:
    def __init__(self, client):
        self.client = client
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.worker = None
        self.state = {"mode": "live", "scenario": "Bazaar real", "cash": None,
                      "assets": [], "pending": None, "movements": [], "events": [],
                      "offers": [], "threads": [], "tick": None, "checks": {},
                      "poll_seconds": POLL_SECONDS, "updated_at": None, "finished": False}
        self.previous_assets = None

    def poll(self):
        started = now()
        calls = {"inventario y saldo": self.client.me, "reloj": self.client.clock,
                 "ofertas": self.client.my_offers, "conversaciones": self.client.my_threads}
        values, failures = {}, {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {name: pool.submit(call) for name, call in calls.items()}
            for name, future in futures.items():
                try:
                    values[name] = validate_payload(name, future.result())
                except (ValueError, KeyError, TypeError, AttributeError):
                    failures[name] = "invalid_response"
                except Exception as error:
                    failures[name] = getattr(error, "code", "connection_error")
        with self.lock:
            self.state.pop("monitor_error", None)
            for name in calls:
                previous = self.state["checks"].get(name, {})
                self.state["checks"][name] = {"attempted_at": started,
                    "verified_at": now() if name in values else previous.get("verified_at"),
                    "ok": name in values, "error": failures.get(name)}
            if "inventario y saldo" in values:
                me = values["inventario y saldo"]
                assets = [asset_view(a) for a in me["assets"]]
                current = {a["id"]: a for a in assets}
                if self.previous_assets is not None:
                    for direction, ids, source in (
                        ("in", current.keys() - self.previous_assets.keys(), current),
                        ("out", self.previous_assets.keys() - current.keys(), self.previous_assets)):
                        for identity in sorted(ids):
                            self.state["movements"].append({"id": len(self.state["movements"]) + 1,
                                "side": direction, "card": source[identity]["ref"], "asset_id": identity,
                                "price": None, "paid": None, "tick": None,
                                "observed_at": now(), "counterparty": "Cambio confirmado de inventario"})
                self.previous_assets = current
                self.state.update(cash=me["cash"], assets=assets, team_id=me.get("id"),
                                  team_name=me.get("name"), updated_at=now())
            if "reloj" in values:
                clock = values["reloj"]
                self.state.update(tick=clock["tick"], paused=clock.get("paused"))
            if "ofertas" in values:
                self.state["offers"] = [offer_view(o) for o in rows(values["ofertas"], "offers")]
            if "conversaciones" in values:
                self.state["threads"] = [{k: t[k] for k in ("id", "with", "status", "closed_reason")
                                          if k in t} for t in rows(values["conversaciones"], "threads")]
            self.state["last_attempt_at"] = started

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.state)

    def run(self):
        while not self.stop_event.is_set():
            deadline = time.monotonic() + POLL_SECONDS
            try:
                self.poll()
            except (ValueError, KeyError, TypeError):
                with self.lock:
                    self.state["monitor_error"] = "Formato de respuesta inesperado; datos sin verificar"
            self.stop_event.wait(max(0, deadline - time.monotonic()))

    def start(self):
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def close(self):
        self.stop_event.set()
        if self.worker:
            self.worker.join(timeout=4)


def make_monitor(url, key_file=None):
    return LiveMonitor(Bazaar(url, read_key(key_file), timeout=3, retries=0, wait_on_tick=False))
