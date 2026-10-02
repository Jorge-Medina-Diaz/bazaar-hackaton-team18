"""Laboratorio SIN red: precios inventados, no reproduce la IA real de Abuela."""
import argparse
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from negotiation_policy import Decision, decide_purchase, polite_message
from inventory_panel import DEFAULT_STATE, InventoryJournal, write_state


@dataclass(frozen=True)
class Scenario:
    cards: tuple
    maximum: int
    opening: int
    floor: int
    concession: int = 2
    patience: int = 6
    cash: int = 40
    values: tuple = (20, 5, 2)
    final: bool = False


SCENARIOS = {
    "compra": Scenario(("LAV-03",), 12, 14, 9),
    "limite": Scenario(("LAV-06",), 26, 30, 28, 1, 12, values=(40, 10, 4)),
    "final": Scenario(("LAV-03",), 12, 11, 11, final=True),
    "varias": Scenario(("LAV-03", "MAL-01", "LAV-03"), 12, 14, 3),
}


def baseline_decision(ask: int, maximum: int, last_sent: Optional[int],
                      increment: int, final: bool) -> Decision:
    """Solo la lógica de precios del starter; no ejecuta el script oficial."""
    if maximum < 1:
        return Decision("close", "Sin presupuesto")
    price = maximum * 3 // 5 if last_sent is None else min(maximum, last_sent + increment)
    if ask <= min(maximum, price + 1) or (final and ask <= maximum):
        return Decision("accept", "Criterio de aceptación del starter", ask)
    return Decision("offer", "Contraoferta del starter", price)


class Simulation:
    def __init__(self, scenario: Scenario, policy: str = "mejorada", increment: int = 2):
        if policy not in ("base", "mejorada") or type(increment) is not int or increment < 1:
            raise ValueError("Política o incremento inválido")
        numbers = (scenario.maximum, scenario.opening, scenario.floor, scenario.concession,
                   scenario.patience, scenario.cash, *scenario.values)
        if any(type(n) is not int or n < 0 for n in numbers):
            raise ValueError("Los valores del escenario deben ser enteros no negativos")
        if not (1 <= scenario.floor <= scenario.opening <= 10_000_000):
            raise ValueError("Precios de la vendedora inválidos")
        if scenario.maximum > 10_000_000 or scenario.concession < 1 or scenario.patience < 1:
            raise ValueError("Presupuesto, concesión o paciencia inválidos")
        if not scenario.cards or not scenario.values:
            raise ValueError("Faltan cartas o valores")
        self.scenario, self.policy, self.increment = scenario, policy, increment
        self.cash, self.tick = scenario.cash, 0
        self.assets, self.events = [], []
        self.pending = None

    def event(self, card, action, reason, price=None, message=None):
        result = {"tick": self.tick, "card": card, "action": action, "reason": reason,
                  "price": price, "message": message, "cash": self.cash,
                  "cards": len(self.assets)}
        self.events.append(result)
        return result

    def steps(self):
        """Una decisión por tick; una aceptación no cambia el inventario hasta el siguiente."""
        for card in self.scenario.cards:
            copies = Counter(a["ref"] for a in self.assets)[card]
            value = self.scenario.values[min(copies, len(self.scenario.values) - 1)]
            maximum = min(self.scenario.maximum, self.cash, value)
            ask, final, last = self.scenario.opening, self.scenario.final, None
            sent = 0
            for _ in range(100):
                if self.policy == "base":
                    decision = baseline_decision(ask, maximum, last, self.increment, final)
                else:
                    decision = decide_purchase(ask, maximum, last, self.increment, final)
                if decision.action == "close":
                    yield self.event(card, "close", decision.reason,
                                     message="Gracias por tu tiempo, Abuela. Se sale de mi presupuesto.")
                    self.tick += 1
                    break
                price = decision.price
                if price is None or not 1 <= price <= maximum:
                    yield self.event(card, "refused", "Precio inválido; no se transfiere nada", price)
                    self.tick += 1
                    break
                message = polite_message(card, price, last is None) if decision.action == "offer" else None
                event = self.event(card, decision.action, decision.reason, price, message)
                event["dealer_ask"] = ask
                # El umbral es inventado y SOLO lo conoce el dealer simulado.
                accepted = decision.action == "accept" or price >= self.scenario.floor
                if accepted:
                    self.pending = {"ref": card, "price": price, "value": value}
                    event["reply"] = "Acepta; la carta todavía no se ha liquidado"
                elif final:
                    event["reply"] = "Era su oferta final; termina la conversación"
                else:
                    if last is None or price > last:
                        ask = max(self.scenario.floor, ask - self.scenario.concession)
                    sent += 1
                    final = sent >= self.scenario.patience
                    event["reply"] = f"Contraoferta: {ask} P" + (" (final)" if final else "")
                yield event
                self.tick += 1
                if accepted:
                    # Liquidación de una sola operación en el siguiente tick.
                    self.cash -= price
                    self.assets.append({"id": len(self.assets) + 1, "ref": card,
                                        "paid": price, "value": value})
                    self.pending = None
                    yield self.event(card, "settled", "Carta incorporada al inventario", price)
                    self.tick += 1
                    break
                if final and event["reply"].startswith("Era su oferta"):
                    break
                last = price
            else:
                yield self.event(card, "close", "Límite de seguridad del simulador")
                self.tick += 1

    def summary(self):
        return {"policy": self.policy, "cash": self.cash, "cards": len(self.assets),
                "copies": dict(Counter(a["ref"] for a in self.assets)),
                "decisions": len([e for e in self.events if e["action"] != "settled"]),
                "pending": self.pending}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="compra")
    parser.add_argument("--policy", choices=("base", "mejorada"), default="mejorada")
    parser.add_argument("--increment", type=int, default=2)
    parser.add_argument("--step", action="store_true", help="Enter avanza, q detiene")
    parser.add_argument("--compare", action="store_true", help="Compara ambas políticas en el mismo escenario")
    parser.add_argument("--state-file", default=str(DEFAULT_STATE), help="Estado que lee el panel local")
    args = parser.parse_args()
    if args.increment < 1 or (args.step and args.compare):
        parser.error("increment debe ser positivo; step y compare se usan por separado")
    print("SIMULACIÓN LOCAL · SIN API · Precios inventados; no mide persuasión real.")
    for policy in ("base", "mejorada") if args.compare else (args.policy,):
        simulation = Simulation(SCENARIOS[args.scenario], policy, args.increment)
        journal = InventoryJournal(args.scenario, policy)
        write_state(args.state_file, journal.simulation_state(simulation))
        print(f"\nEscenario: {args.scenario} · Política: {policy}")
        finished = False
        for event in simulation.steps():
            write_state(args.state_file, journal.simulation_state(simulation, event))
            print(f"Tick {event['tick']}: {event['action']} · {event['card']} · "
                  f"precio={event['price']} · saldo={event['cash']} · cartas={event['cards']}")
            if "dealer_ask" in event:
                print(f"  La vendedora pide: {event['dealer_ask']} P")
            if event["message"]:
                print(f"  Agente: {event['message']}")
            print(f"  {event.get('reply', event['reason'])}")
            if args.step:
                try:
                    if input("Enter para avanzar / q para salir: ").strip().lower() == "q":
                        break
                except EOFError:
                    break
        else:
            finished = True
        write_state(args.state_file, journal.simulation_state(simulation, finished=finished))
        print(f"Resultado: {simulation.summary()}")


if __name__ == "__main__":
    main()
