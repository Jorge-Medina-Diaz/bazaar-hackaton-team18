"""Estado del panel local. No usa red ni credenciales del juego."""
import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile


DEFAULT_STATE = Path(__file__).resolve().parent / "runs" / "panel-state.json"


class InventoryJournal:
    def __init__(self, scenario, policy="mejorada"):
        self.scenario = scenario
        self.policy = policy
        self.movements = []
        self.events = []
        self.seen = set()

    def observe(self, *, cash, assets, tick, event=None, pending=None, finished=False):
        """Recibe el estado confirmado; registrar un acuerdo no mueve activos."""
        if event is not None:
            identity = (event["tick"], event["action"], event.get("asset_id"), event.get("card"))
            if identity not in self.seen:
                if event["action"] == "settled":
                    side = event.get("side", "buy")
                    if side not in ("buy", "sell"):
                        raise ValueError("Dirección de movimiento inválida")
                    if side == "buy":
                        asset = next(a for a in assets if a["id"] == event["asset_id"])
                        cost = asset["paid"]
                    else:
                        cost = event.get("paid")
                    self.movements.append({"id": len(self.movements) + 1, "tick": tick,
                                           "side": side, "card": event["card"],
                                           "asset_id": event["asset_id"], "price": event["price"],
                                           "paid": cost, "counterparty": "Abuela simulada"})
                self.events.append(copy.deepcopy(event))
                self.seen.add(identity)
        return {"schema_version": 1, "mode": "simulation", "scenario": self.scenario,
                "policy": self.policy, "updated_at": datetime.now(timezone.utc).isoformat(),
                "tick": tick, "cash": cash, "assets": copy.deepcopy(assets),
                "pending": copy.deepcopy(pending), "movements": copy.deepcopy(self.movements),
                "events": copy.deepcopy(self.events), "finished": finished}

    def simulation_state(self, simulation, event=None, finished=False):
        event = copy.deepcopy(event)
        if event and event["action"] == "settled":
            event.update(side="buy", asset_id=simulation.assets[-1]["id"])
        pending = copy.deepcopy(simulation.pending)
        if pending:
            pending["side"] = "buy"
        return self.observe(cash=simulation.cash, assets=simulation.assets,
                            tick=event["tick"] if event else simulation.tick,
                            event=event, pending=pending, finished=finished)


def write_state(path, state):
    """Reemplazo atómico: el navegador nunca lee un JSON a medio escribir."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".panel-", suffix=".tmp", delete=False) as stream:
            temporary = stream.name
            json.dump(state, stream, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def demo_states():
    """Compras del laboratorio y venta INVENTADA de una copia repetida."""
    from laboratorio import SCENARIOS, Simulation

    simulation = Simulation(SCENARIOS["varias"])
    journal = InventoryJournal("compraventa de ejemplo")
    states = [journal.simulation_state(simulation)]
    for event in simulation.steps():
        states.append(journal.simulation_state(simulation, event))
    asset = simulation.assets[-1]
    tick = simulation.tick
    pending = {"side": "sell", "asset_id": asset["id"], "ref": asset["ref"], "price": 8}
    states.append(journal.observe(cash=simulation.cash, assets=simulation.assets, tick=tick,
                                 pending=pending,
                                 event={"tick": tick, "action": "accept", "side": "sell",
                                        "asset_id": asset["id"], "card": asset["ref"], "price": 8,
                                        "reason": "Venta simulada acordada; pendiente del siguiente tick"}))
    states.append(journal.observe(cash=simulation.cash + 8, assets=simulation.assets[:-1],
                                 tick=tick + 1, finished=True,
                                 event={"tick": tick + 1, "action": "settled", "side": "sell",
                                        "asset_id": asset["id"], "card": asset["ref"], "price": 8,
                                        "paid": asset["paid"], "reason": "Duplicado vendido en el ejemplo"}))
    return states
