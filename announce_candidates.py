"""Borradores de anuncio para nuestro puesto v18 (creación de mercado orgánica): SOLO LECTURA, sin clave.

Busca en los tableros públicos parejas reales entre dos equipos que NO son rivales directos (CONTENDERS fuera): una
venta de la carta X a `ask` del equipo A y una puja por X a `bid` del equipo B, las dos abiertas ahora, que se
cruzan (bid >= ask) o se quedan cerca (bid >= ask - max(2 P, 20 %); el sábado ninguna pareja abierta llegó a cruzarse). El dueño de cada oferta sale del feed público (offer.listed trae el equipo; los tableros
solo traen un seudónimo). Las cifras las pone el código; el texto solo las cita.
Imprime cada pareja (ids, precios, tableros) y un borrador en español. Jorge aprueba el texto y lo manda con
un POST /api/broker/announce manual fuera del repo (excepción manual, uno cada ~10 min; docs/history/plan-domingo.md §5.3). Nosotros nunca operamos en v18.

    python3 announce_candidates.py            # las 5 mejores parejas
    python3 announce_candidates.py 10
"""
from __future__ import annotations

import json
import math
import sys
import urllib.request
from typing import Iterable, Mapping, Optional

URL = "https://bazaar.causaprima.ai"
US = "t18"
OUR_VENUE = "v18"
CONTENDERS = frozenset({"t10", "t05", "t12", "t03", "t06", "t14"})   # sábado 23:55: 1.º y 3.º-7.º
FEED_LIMIT = 1000


def get(path: str):
    req = urllib.request.Request(URL + path, headers={"User-Agent": "t18-announce-candidates",
                                                      "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def _one_card(lst) -> Optional[str]:
    refs = [a.get("ref") for a in lst or () if isinstance(a, Mapping) and a.get("kind", "card") == "card"]
    return refs[0] if len(refs) == 1 and type(refs[0]) is str else None


def side_of(o: Mapping) -> Optional[tuple]:
    """("ask", ref, price) for a one-card sale for cash, ("bid", ref, price) for cash wanting one card type; else None."""
    g, w = o.get("give") or {}, o.get("want") or {}
    if o.get("to"):
        return None                                           # addressed: not for anyone else
    if _one_card(g.get("assets")) and not g.get("types") and not g.get("cash") and not w.get("assets") \
            and not w.get("types") and type(w.get("cash")) is int and w["cash"] > 0:
        return ("ask", _one_card(g.get("assets")), w["cash"])
    types = [t[5:] for t in w.get("types") or () if type(t) is str and t.startswith("card:")]
    if len(types) == 1 and not w.get("assets") and not w.get("cash") and not g.get("assets") \
            and type(g.get("cash")) is int and g["cash"] > 0:
        return ("bid", types[0], g["cash"])
    return None


def owners(feed: Iterable[Mapping]) -> dict:
    """offer id -> team, from the public offer.listed events."""
    out = {}
    for e in feed or ():
        if not isinstance(e, Mapping) or e.get("type") != "offer.listed":
            continue
        o = (e.get("payload") or {}).get("offer") or {}
        team = o.get("maker") or e.get("actor")
        if type(o.get("id")) is int and isinstance(team, str) and team.startswith("t"):
            out[o["id"]] = team
    return out


def max_gap(ask: int) -> int:
    """How far apart a pair may be to be worth a nudge: 2 P or 20 % of the ask (Sat: no open pair ever crossed;
    the near ones sat 1-2 P apart for 50 ticks)."""
    return max(2, int(ask * 0.2))


def pairs(open_offers: Iterable[Mapping], who: Mapping, exclude: frozenset = CONTENDERS | {US}) -> list:
    """Pairs between two different non-excluded teams with bid >= ask - max_gap(ask); crossing ones (gap 0) first,
    then the smallest gap: [{ref, ask_id, ask, ask_team, ask_venue, bid_id, bid, bid_team, bid_venue, gap}]."""
    asks, bids = [], []
    for o in open_offers or ():
        if not isinstance(o, Mapping) or o.get("status", "open") != "open" or type(o.get("id")) is not int:
            continue
        s, team = side_of(o), who.get(o["id"])
        if s is None or team is None or team in exclude:
            continue
        (asks if s[0] == "ask" else bids).append((s[1], s[2], team, o["id"], o.get("venue")))
    out, seen = [], set()
    for ref, ap, at, aid, av in asks:
        for bref, bp, bt, bid_id, bv in bids:
            if bref != ref or bt == at or bp < ap - max_gap(ap):
                continue
            key = (ref, at, bt)
            if key in seen:
                continue
            seen.add(key)
            out.append({"ref": ref, "ask_id": aid, "ask": ap, "ask_team": at, "ask_venue": av,
                        "bid_id": bid_id, "bid": bp, "bid_team": bt, "bid_venue": bv, "gap": max(0, ap - bp)})
    return sorted(out, key=lambda p: (p["gap"], -(p["bid"] - p["ask"]), p["ref"]))


def _team(t: str) -> str:
    return "Team " + str(int(t[1:])) if t[1:].isdigit() else t


def draft(p: Mapping) -> str:
    """Spanish announcement text for one pair; every number comes from the pair."""
    fee = math.ceil(p["ask"] * 0.05 + 1)
    near = f" Estáis a {p['gap']} P: con 0 de comisión, quedad a mitad de camino." if p.get("gap") else ""
    return (f"{_team(p['ask_team'])}: vendéis {p['ref']} a {p['ask']} P (oferta {p['ask_id']}, {p['ask_venue']}). "
            f"{_team(p['bid_team'])} puja {p['bid']} P por esa carta (oferta {p['bid_id']}, {p['bid_venue']}).{near} "
            f"En El Rastro quien acepta paga 5 % + 1 P (unos {fee} P aquí). En {OUR_VENUE}: 0 %, 0 P por carta, y "
            f"el puesto cruza solo la mejor puja con la mejor venta cada tick. Publicad las dos en {OUR_VENUE} "
            f"(o la venta dirigida a {_team(p['bid_team'])}).")


def main(argv) -> int:
    n = int(argv[0]) if argv else 5
    feed = get(f"/api/feed?limit={FEED_LIMIT}")
    events = feed.get("events", feed.get("feed", feed)) if isinstance(feed, dict) else feed
    who = owners(events)
    venues = get("/api/venues")
    vlist = venues.get("venues", venues) if isinstance(venues, dict) else venues
    offers = []
    for v in vlist or ():
        vid = v.get("venue") or v.get("id")
        if v.get("status") != "open" or not isinstance(vid, str):
            continue
        b = get(f"/api/venues/{vid}/offers")
        for o in (b.get("offers", b) if isinstance(b, dict) else b) or ():
            if isinstance(o, dict):
                offers.append(dict(o, venue=o.get("venue") or vid))
    found = pairs(offers, who)
    print(f"{len(offers)} open offers, {len(who)} owners from the feed, {len(found)} crossable pairs")
    for p in found[:n]:
        print(f"- {p['ref']}: ask {p['ask']} ({p['ask_team']}, {p['ask_id']}, {p['ask_venue']}) | "
              f"bid {p['bid']} ({p['bid_team']}, {p['bid_id']}, {p['bid_venue']})")
        print("  " + draft(p))
    return 0


if __name__ == "__main__":
    if {"-h", "--help"} & set(sys.argv[1:]):
        print(__doc__)
        sys.exit(0)
    sys.exit(main(sys.argv[1:]))
