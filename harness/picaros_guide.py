"""Los Pícaros (nivel 4, 'trickster'): guía de decisión + detector de trucos. Funciones puras, sin red.

Reglas SOLO de lo observado en sus hilos (feed público, ticks 763-778) y de su ficha oficial:
- Venden raras (lista 63, abren a 73) y épicas (lista 162). Compran comunes (pagan 4, a veces 5) e infrecuentes (10 -> 13).
- Truco medido: la oferta estructurada da OTRA carta (más barata) que la del tema, con un precio atractivo
  (LAV-09 -> LAV-06/LAV-08; SAL-09 -> SAL-06; LAV-10 -> LAV-08). Bio oficial: «Their deadlines never are».
- Aceptan el precio del equipo: t01 58 (pasos +1 desde 55), t05 54 (pasos +3 desde 45). t02 aceptó su 67.
- Nada de otros dealers se da por válido aquí.
"""
from __future__ import annotations

BUY_ANCHOR, BUY_STEP = 45, 3        # lo que hizo t05 (54, el mejor cierre visto); E-P1 compara con +1
OPEN = {"rare": 73, "epic": 187}    # su primera oferta medida (rara n>10; épica n=1, SAL-11 t16)
ANCHOR_FRAC = 45 / 73               # ancla del mejor cierre en raras, como fracción de su apertura (épica: extrapolado)
COMMON_PAY, UNCOMMON_TOP = 4, 13     # lo que pagan por comunes / tope visto en infrecuentes


def offered_refs(give: dict) -> list:
    return [a.get("ref") for a in (give.get("assets") or [])] + \
           [t.split(":", 1)[1] for t in (give.get("types") or []) if isinstance(t, str) and t.startswith("card:")]


def trick(topic: dict, offer: dict) -> str | None:
    """Motivo firme si la oferta estructurada contradice el tema; None si es coherente. Solo estructura, nunca texto."""
    if not offer:
        return None
    give, want = offer.get("give") or {}, offer.get("want") or {}
    if "buy" in topic:                                   # nosotros compramos: ellos deben dar la carta del tema
        ref = (topic["buy"] or {}).get("card")
        refs = offered_refs(give)
        if any(isinstance(t, str) and t.startswith("pack:") for t in give.get("types") or []):
            return "da un sobre en vez de la carta"
        if not refs:
            return "no da ninguna carta"
        if ref and refs != [ref]:
            return f"da {refs} en vez de {ref}"
        if offered_refs(want) or (want.get("assets") or []):
            return "pide cartas además de dinero"
    if "sell" in topic:                                  # nosotros vendemos: ellos deben dar dinero y pedir nuestra carta
        if offered_refs(give) or (give.get("assets") or []):
            return "da cartas cuando debería pagar"
        if not give.get("cash"):
            return "no paga nada"
    return None


def _rarity(ref):
    try:
        n = int(ref.split("-")[1])
    except (AttributeError, IndexError, ValueError):
        return "rare"
    return "epic" if n == 11 else "legendary" if n == 12 else "rare"


def next_buy(ref_topic: str, ceiling: int, theirs: list, ours: list) -> dict:
    """Comprar una rara. theirs: [(price, final, trick|None)]; ours: precios enviados; ceiling = V - 1.
    Aprendido solo de Los Pícaros (params.json): paso = el menor con la misma probabilidad de que bajen; perdonan a
    `perdona` P de su oferta honesta (medido: 2). Nunca aceptar una oferta con truco; su `final` no cierra nada."""
    try:
        from harness import dealer_tuner as afinador; P = afinador.get("picaros", "compra", ref_topic or "XXX", _rarity(ref_topic), fav_sets=set()) or {}
    except Exception:
        P = {}
    ps = P.get("p_sube") or {}
    step = 1 if ps.get("1", 0) >= ps.get("2-3", 0) else BUY_STEP
    forgive = 2 if (P.get("perdona_max") or 0) >= 2 else 1
    honest = theirs[-1][0] if theirs and theirs[-1][2] is None else None
    if not ours:
        first = next((p for p, _, t in theirs if t is None), None) or OPEN.get(_rarity(ref_topic), 73)
        anchor = min(round(first * ANCHOR_FRAC), ceiling)
        if honest is not None and honest <= anchor:
            return {"do": "accept", "why": f"oferta honesta {honest} ya bajo el ancla"}
        return {"do": "say", "price": anchor, "why": f"ancla {anchor} = {ANCHOR_FRAC:.2f} × su apertura {first}"}
    last = ours[-1]
    if honest is not None and honest <= ceiling and honest <= last + step:
        return {"do": "accept", "why": f"su oferta honesta {honest} <= nuestro siguiente"}
    nxt = min(last + step, ceiling)
    if honest is not None:
        target = honest - forgive                       # zona de perdón medida
        if nxt >= target:
            nxt = max(target, last + 1) if target > last else last + 1
        nxt = min(nxt, honest - 1, ceiling)
    if nxt <= last:
        return {"do": "close", "why": f"sin hueco bajo el techo {ceiling}"}
    why = f"+{nxt - last}" + (" (zona de perdón)" if honest is not None and nxt == honest - forgive else "") + \
          ("; su última oferta era truco: ignorada" if theirs and theirs[-1][2] else "")
    return {"do": "say", "price": nxt, "why": why}


def next_sell(rarity: str, floor: int, theirs: list, ours: list) -> dict:
    """Vender una común/infrecuente. theirs: [(price, final, trick)]. floor = V + 1."""
    if theirs and theirs[-1][2] is not None:
        return {"do": "say", "price": ours[-1] if ours else floor, "why": f"truco: {theirs[-1][2]}; no aceptar"} if not ours \
            else {"do": "close", "why": f"truco: {theirs[-1][2]}"}
    cur = theirs[-1][0] if theirs else None
    if cur is not None and cur < floor and theirs[-1][1]:
        return {"do": "close", "why": f"final {cur} < suelo {floor}"}
    if cur is not None and cur >= floor and (theirs[-1][1] or (ours and ours[-1] <= cur + 1)):
        return {"do": "accept", "why": f"{cur} >= suelo {floor}"}
    top = COMMON_PAY + 1 if rarity == "common" else UNCOMMON_TOP
    if not ours:
        return {"do": "say", "price": max(floor, top + 3), "why": "ancla cerca de su tope observado"}
    nxt = ours[-1] - 1
    if cur is not None and nxt <= cur:
        return {"do": "accept", "why": f"sin hueco; su {cur}"} if cur >= floor else {"do": "close", "why": "bajo suelo"}
    if nxt < floor:
        return {"do": "close", "why": f"no llega a suelo {floor}"}
    return {"do": "say", "price": nxt, "why": "-1"}
