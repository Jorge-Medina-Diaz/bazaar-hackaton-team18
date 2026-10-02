"""Decisiones locales de compra; no hace peticiones ni usa credenciales."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    price: Optional[int] = None


def decide_purchase(ask: Optional[int], maximum: int,
                    last_sent: Optional[int] = None, increment: int = 2,
                    final: bool = False, pending: bool = False,
                    status: str = "open", paused: bool = False) -> Decision:
    """Precio máximo económico ya calculado; subida fija para comparar con el starter."""
    for name, value in (("maximum", maximum), ("increment", increment)):
        if type(value) is not int:
            raise ValueError(f"{name} debe ser un entero")
    if increment < 1 or maximum < 0 or maximum > 10_000_000:
        raise ValueError("Presupuesto o incremento inválido")
    if ask is not None and (type(ask) is not int or not 1 <= ask <= 10_000_000):
        raise ValueError("Precio del dealer inválido")
    if last_sent is not None and (type(last_sent) is not int or last_sent < 1):
        raise ValueError("Último precio enviado inválido")
    if status != "open":
        return Decision("done", f"Conversación terminada: {status}")
    if pending or paused:
        return Decision("wait", "Liquidación pendiente" if pending else "Reloj pausado")
    if maximum < 1:
        return Decision("close", "No queda presupuesto para una oferta válida")
    if ask is None:
        return Decision("wait", "Todavía no hay una oferta del dealer")
    if final:
        if ask <= maximum:
            return Decision("accept", "Oferta final dentro del límite", ask)
        return Decision("close", "Oferta final fuera del presupuesto")
    price = max(1, maximum * 3 // 5) if last_sent is None else min(maximum, last_sent + increment)
    if ask <= min(maximum, price + 1):
        return Decision("accept", "Oferta aceptable dentro del límite", ask)
    if last_sent is not None and price <= last_sent:
        return Decision("close", "Límite alcanzado; repetir precio no ayuda")
    return Decision("offer", "Primera propuesta" if last_sent is None else "Nueva concesión", price)


def polite_message(card: str, price: int, first: bool = True) -> str:
    if first:
        return (f"Hola, Abuela Carmen. Me gustaría comprar {card}. "
                f"¿Te vendría bien {price} primas? Gracias por considerarlo.")
    return (f"Gracias por tu propuesta, Abuela Carmen. Puedo subir a {price} primas "
            f"por {card}. ¿Te parece bien?")
