"""Selling to Doña Pilar (level 3): a pure next-move function for the operator, outside agent/ (code_hash unchanged).

Not wired into the executor: dealers.py has no sell side (fail closed). The operator reads the advice and acts with
`bazaar.py do` under the Gate. Evidence: public feed only, 7 Pilar deals (ticks 559-630, Sat 3 Oct); see docs/pilar.md.
No behaviour measured on Abuela or Chato is assumed for Pilar.

Rules:
- Only `final: true` ends the thread (RULES). Accept a final >= floor, otherwise close.
- First ask = expected opening + 8 (scaled by catalog for other rarities). Observed: anchors of 40-51 closed no higher.
- Then -1 P per message (scaled), never repeating a price, never at or below her standing price.
- E1 (unmeasured on Pilar): when the next step reaches her price, ask her price + 1 once; if she does not take it,
  accept her standing offer when it covers the floor.
- floor = V + 1 of the copy sold. Only duplicates: a single SAL/RET copy carries the page bonus.
"""
from __future__ import annotations

FAV = frozenset({"SAL", "RET"})
CATALOG = {"uncommon": 25, "rare": 70, "epic": 180}
OPEN_FRAC = {True: 22 / 25, False: 16 / 25}    # observed openings on uncommons; other rarities are extrapolated
FEVER = 1.25                                    # schedule: Salamanca fever, 25 % over book (unmeasured on her offers)
ANCHOR_GAP = 8


def expected_open(ref: str, rarity: str, fever: bool = False) -> int:
    o = CATALOG.get(rarity, 25) * OPEN_FRAC[ref[:3] in FAV]
    if fever and ref.startswith("SAL"):
        o *= FEVER
    return round(o)


def next_move(ref: str, rarity: str, floor: int, her: list, ours: list, fever: bool = False) -> dict:
    """her: Pilar's offers [(price, final)], oldest first. ours: prices we sent. -> {"do": accept|say|close|wait, ...}"""
    if her and her[-1][1]:
        p = her[-1][0]
        return {"do": "accept", "why": f"final {p} >= floor {floor}"} if p >= floor else \
               {"do": "close", "why": f"final {p} < floor {floor}"}
    scale = CATALOG.get(rarity, 25) / 25
    if not ours:
        base = her[-1][0] if her else expected_open(ref, rarity, fever)
        return {"do": "say", "price": max(floor, base + round(ANCHOR_GAP * scale)), "why": "anchor = opening + 8"}
    if not her:
        return {"do": "wait", "why": "no reply yet"}
    cur, last = her[-1][0], ours[-1]
    if cur >= floor and last <= cur + 1:
        return {"do": "accept", "why": f"asked {last} (her price + 1), not taken; accept her {cur}"}
    nxt = last - max(1, round(scale))
    if nxt <= cur + 1:
        nxt = cur + 1
        if nxt >= last:
            return {"do": "accept", "why": f"no room; her {cur}"} if cur >= floor else {"do": "close", "why": "below floor"}
    if nxt < floor:
        return {"do": "accept", "why": f"her {cur} >= floor"} if cur >= floor else {"do": "close", "why": f"cannot reach floor {floor}"}
    return {"do": "say", "price": nxt, "why": "-1, never repeated; new polite text"}
