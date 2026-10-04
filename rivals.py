"""Vigilancia de rivales sin clave (rol analista): clasificación, mercados de equipo y pujas grandes en El Rastro.

Solo lecturas públicas (GET /api/leaderboard, /api/venues, /api/venues/rastro/offers) por public_get, con
allowlist y límite de ritmo: no escribe nada en el juego. Cada foto se graba en logs/rivals.jsonl y se compara con la anterior:
  - t12 (o --watch-team): su puntuación de mercado y cuánto ha cambiado;
  - mercados de equipo con tratos: tratos por hora desde la foto anterior; ALERTA si alguno pasa de 3/h
    (umbral para replantear abrir mercado propio);
  - pujas en El Rastro (dar caja, pedir carta) de al menos --min-bid P, marcando las de cartas que tenemos
    de sobra si se pasan con --have.

Uso:
  python3 rivals.py                       # una foto y el informe
  python3 rivals.py --watch 3600          # una foto cada hora
  python3 rivals.py --have LAT-01,LAT-05  # marca pujas por nuestros sobrantes
"""
import argparse
import json
import os
import sys
import time

from agent.journal import LOG_DIR, log

STREAM = "rivals"
VENUE_ALERT_PER_H = 3.0
_LIMITER = None


def get(path: str):
    global _LIMITER
    from agent.contracts import PROD_URL
    from agent.transport import RateLimiter, public_get
    if path not in ("/api/leaderboard", "/api/venues", "/api/venues/rastro/offers"):
        raise ValueError("Ruta no pública del analista")
    if _LIMITER is None:
        _LIMITER = RateLimiter(rate=1, burst=1, reserve=0)
    return public_get(PROD_URL, path, _LIMITER)


def snapshot() -> dict:
    lb = get("/api/leaderboard")
    venues = get("/api/venues").get("venues", [])
    offers = get("/api/venues/rastro/offers").get("offers", [])
    bids = []
    for o in offers:
        cash = (o.get("give") or {}).get("cash") or 0
        cards = [t.split(":", 1)[1] for t in (o.get("want") or {}).get("types") or [] if t.startswith("card:")]
        if cash > 0 and cards:
            bids.append({"id": o["id"], "maker": o.get("maker"), "cash": cash, "cards": cards,
                         "expires": o.get("expires_tick")})
    return {
        "tick": lb.get("tick"), "t": lb.get("t"), "round": lb.get("round"),
        "teams": {t["team"]: {"rank": t["rank"], "score": t["score"], "neg": t["negotiating"],
                              "market": t["market"], "deals": t["deals"], "pages": t["pages_complete"]}
                  for t in lb.get("teams", [])},
        "venues": {v["venue"]: {"owner": v["owner"], "trades": v["trades"], "volume": v["volume"],
                                "mechanism": (v.get("rules") or {}).get("mechanism"), "starter": v.get("starter"),
                                "status": v.get("status")}
                   for v in venues},
        "bids": bids,
    }


def last_snapshot():
    path = os.path.join(LOG_DIR, f"{STREAM}.jsonl")
    if not os.path.exists(path):
        return None
    last = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                last = line
    return json.loads(last) if last else None


def report(now: dict, prev, watch_team: str, min_bid: int, have: set) -> list:
    out, alerts = [], []
    hours = (now["ts"] - prev["ts"]) / 3600 if prev else None
    out.append(f"tick {now['tick']} · t={now['t']} · ronda {now['round']}"
               + (f" · {hours * 60:.0f} min desde la foto anterior" if hours else " · primera foto"))

    out.append("\n  #  equipo  total   neg   mkt  tratos  Δtotal")
    for team, s in sorted(now["teams"].items(), key=lambda kv: kv[1]["rank"])[:8]:
        p = (prev or {}).get("teams", {}).get(team)
        d = f"{s['score'] - p['score']:+6.2f}" if p else "      "
        mark = " <" if team in ("t18", watch_team) else ""
        out.append(f" {s['rank']:2}  {team:6} {s['score']:6.2f} {s['neg']:5.2f} {s['market']:5.2f}  {s['deals']:5}  {d}{mark}")

    us, them = now["teams"].get("t18"), now["teams"].get(watch_team)
    if us and them:
        p = (prev or {}).get("teams", {}).get(watch_team)
        delta = f" ({them['market'] - p['market']:+.2f} desde la anterior)" if p else ""
        out.append(f"\n{watch_team} mercado {them['market']:.2f}{delta} frente a t18 {us['market']:.2f}")

    out.append("\nMercados de equipo con tratos:")
    any_venue = False
    for vid, v in sorted(now["venues"].items()):
        if v["owner"] == "world" or not v["trades"]:
            continue
        any_venue = True
        pv = (prev or {}).get("venues", {}).get(vid)
        rate = (v["trades"] - pv["trades"]) / hours if (pv and hours) else None
        r = f"{rate:.1f}/h" if rate is not None else "¿/h"
        out.append(f"  {vid} ({v['owner']}, {v['mechanism']}{', puesto' if v['starter'] else ''}): "
                   f"{v['trades']} tratos, {v['volume']} P · {r}")
        if rate is not None and rate > VENUE_ALERT_PER_H:
            alerts.append(f"ALERTA: {vid} de {v['owner']} va a {rate:.1f} tratos/h (> {VENUE_ALERT_PER_H:g}): "
                          "replantear mercado propio")
    if not any_venue:
        out.append("  ninguno")

    big = sorted((b for b in now["bids"] if b["cash"] >= min_bid), key=lambda b: -b["cash"])
    out.append(f"\nPujas en El Rastro de al menos {min_bid} P:")
    for b in big:
        ours = [c for c in b["cards"] if c in have]
        tag = "  <- TENEMOS DE SOBRA" if ours else ""
        out.append(f"  #{b['id']} {b['maker']}: {b['cash']} P por {','.join(b['cards'])} (caduca t{b['expires']}){tag}")
        if ours:
            alerts.append(f"Puja de {b['cash']} P por {','.join(ours)} (#{b['id']}): avisar al operador")
    if not big:
        out.append("  ninguna")
    return out + ([""] + alerts if alerts else [])


def once(watch_team: str, min_bid: int, have: set) -> None:
    prev = last_snapshot()
    snap = snapshot()
    log(STREAM, **snap)
    snap["ts"] = time.time()
    print("\n".join(report(snap, prev, watch_team, min_bid, have)), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--watch", type=int, default=0, help="segundos entre fotos (0 = una sola)")
    ap.add_argument("--team", default="t12", help="rival a seguir en mercado (por defecto t12)")
    ap.add_argument("--min-bid", type=int, default=30, help="pujas de El Rastro a partir de estos P")
    ap.add_argument("--have", default="", help="refs que tenemos de sobra, separadas por comas")
    a = ap.parse_args()
    have = {r.strip().upper() for r in a.have.split(",") if r.strip()}
    while True:
        try:
            once(a.team, a.min_bid, have)
        except Exception as e:  # una foto fallida no para la vigilancia
            print(f"error: {e}", file=sys.stderr, flush=True)
            log(STREAM + "_errors", error=str(e))
        if not a.watch:
            break
        time.sleep(a.watch)


if __name__ == "__main__":
    main()
