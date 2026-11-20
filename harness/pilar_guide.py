"""Guía de venta a Doña Pilar: una función pura que decide el siguiente movimiento.

No habla con la red ni con el ejecutor: recibe el estado del hilo y devuelve qué hacer. Pensada para que el
operador (o el agente, tras revisión) la consulte en cada tick. Reglas de origen:
- Feed público de hoy (practica/pilar_knowledge.md): SAL/RET infrecuente abre 22 y cierra 24; resto abre 16 y cierra 17-19.
- Reglas de seguridad de RULES.md (repetir precio no da concesión; `final` es la última oferta).
- NO se trasladan comportamientos medidos con Abuela o Chato: lo que Pilar haga se mide solo con sus hilos.
"""
from __future__ import annotations

FAV = {"SAL", "RET"}
CATALOG = {"uncommon": 25, "rare": 70, "epic": 180}
# Apertura de Pilar como fracción del catálogo (medido en infrecuentes; en raras es una extrapolación)
OPEN_FRAC = {True: 22 / 25, False: 16 / 25}
FEVER = 1.25            # 16:00-18:00 SAL: «25 % por encima del catálogo» (hipótesis sobre su apertura)
ANCHOR_GAP = 8          # en infrecuentes; en raras se escala con el catálogo


def expected_open(ref: str, rarity: str, fever: bool = False) -> int:
    fav = ref[:3] in FAV
    o = CATALOG.get(rarity, 25) * OPEN_FRAC[fav]
    if fever and ref.startswith("SAL"):
        o *= FEVER
    return round(o)


def next_move(ref: str, rarity: str, floor: int, her: list, ours: list, fever: bool = False) -> dict:
    """her: ofertas de Pilar [(precio, final)]; ours: precios enviados. floor = V+1. Usa params.json (afinador) si existe.
    Política aprendida solo de Pilar: bajar de 1 en 1 (es cuando más sube), y en el mensaje nº final_min pedir su precio + 1
    (la distancia a la que perdona). Su `final` se acepta si cubre el suelo."""
    try:
        from harness import dealer_tuner as afinador; P = afinador.get("pilar", "venta", ref, rarity) or {}
    except Exception:
        P = {}
    deadline = P.get("final_min") or 4
    lift = P.get("mejora_max") or 4
    forgive = max(1, min(1, P.get("perdona_max") or 1))   # medido: acepta a 1, nunca a 2
    if her and her[-1][1]:
        p = her[-1][0]
        return {"do": "accept", "why": f"final {p} >= suelo {floor}"} if p >= floor else {"do": "close", "why": f"final {p} < suelo {floor}"}
    if not ours:
        base = her[-1][0] if her else expected_open(ref, rarity, fever)
        return {"do": "say", "price": max(floor, base + lift + forgive), "why": f"ancla = su precio + techo visto {lift} + {forgive}"}
    if not her:
        return {"do": "wait", "why": "aún no ha respondido"}
    cur, last, k = her[-1][0], ours[-1], len(ours) + 1
    target = cur + forgive
    if last <= target:                                   # ya pedimos su precio + 1 y no lo tomó
        return {"do": "accept", "why": f"pedido {last} (su precio + {forgive}) sin aceptar; tomar su {cur}"} if cur >= floor else {"do": "close", "why": "bajo suelo"}
    nxt = target if k >= deadline else last - 1          # antes del plazo: -1 (máxima subida suya); en el plazo: su precio + 1
    nxt = max(nxt, target)
    if nxt >= last:
        nxt = last - 1
    if nxt < max(floor, cur + 1):
        return {"do": "accept", "why": f"su {cur} >= suelo"} if cur >= floor else {"do": "close", "why": f"no llega a suelo {floor}"}
    return {"do": "say", "price": nxt, "why": ("plazo: su precio + 1" if nxt == target else "-1 (le hace subir más)") + f" · mensaje {k}/{deadline}"}


if __name__ == "__main__":
    # Sin simulador a propósito: las reglas se validan contra hilos REALES en pilar_replay.py.
    print(next_move("SAL-07", "uncommon", 5, [], []))
