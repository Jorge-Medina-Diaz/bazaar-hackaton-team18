"""Cómo ven los rivales nuestros multiplicadores: agent.affinity a ciegas sobre t18, contrastado con los reales.

Solo GET públicos sin clave (/api/feed, /api/leaderboard, /api/catalog), como rivals.py: nunca usa BAZAAR_KEY ni
escribe en el juego. Añade los eventos nuevos a logs/feed.jsonl y la foto del leaderboard a logs/leaderboard.jsonl
(mismo formato que affinity.py) y deja el resumen en logs/self_affinity.json.

    python3 afinidad_propia.py            # una pasada
    python3 afinidad_propia.py --offline  # solo logs/
"""
import argparse, json, os, time, urllib.request  # noqa: E401

from agent import affinity as af
from agent.journal import LOG_DIR, log

BASE = os.environ.get("BAZAAR_URL", "https://bazaar.causaprima.ai")
US = "t18"
TRUE = {"LAV": 0.7, "MAL": 0.5, "LAT": 0.9, "SAL": 1.1, "RET": 1.3, "CHA": 1.6}  # GET /api/me -> affinity (vie 2 oct)
FEED, LB, OUT = (os.path.join(LOG_DIR, f) for f in ("feed.jsonl", "leaderboard.jsonl", "self_affinity.json"))
CONF = 0.8


def get(path: str) -> dict:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "t18-analista"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def jsonl(path: str) -> list:
    return [json.loads(x) for x in open(path, encoding="utf-8")] if os.path.exists(path) else []


def collect(offline: bool):
    events, snaps, lb, rarity_of = {e["id"]: e for e in jsonl(FEED)}, jsonl(LB), None, {}
    if not offline:
        for e in sorted(get("/api/feed?limit=500")["events"], key=lambda e: e["id"]):
            if e["id"] not in events:
                log("feed", **e)
                events[e["id"]] = e
        lb = get("/api/leaderboard")
        rnd = next((r["round"] for r in lb.get("rounds", []) if r.get("status") == "active"), lb.get("round"))
        tick = lb.get("snapshot_tick", lb.get("tick"))
        if not snaps or snaps[-1]["tick"] != tick:
            row = {"tick": tick, "round": rnd, "teams": {t["team"]: t["negotiating"] for t in lb["teams"]},
                   "deals": {t["team"]: t["deals"] for t in lb["teams"]}}
            log("leaderboard", **row)
            snaps.append(row)
        rarity_of = {c["id"]: c["rarity"] for s in get("/api/catalog").get("sets", []) for c in s["cards"]}
    return [events[k] for k in sorted(events)], snaps, lb, rarity_of


def calib(p) -> dict:
    perm = tuple(TRUE[s] for s in af.SETS)
    best, pb = p.map()
    return {
        "sets": {s: {"e": round(p.expected(s), 3), "marg": {str(m): round(q, 4) for m, q in p.marginal(s).items()},
                     "cred": sorted(p.credible(s, CONF)), "true": TRUE[s], "hit": TRUE[s] in p.credible(s, CONF)}
                 for s in af.SETS},
        "map": best, "map_p": round(pb, 4), "p_true": round(p.p[af.PERMS.index(perm)], 5),
        "rank_true": sorted(p.p, reverse=True).index(p.p[af.PERMS.index(perm)]) + 1,
        "bits": round(p.entropy_bits(), 2), "n": dict(p.n),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--step", type=int, default=20, help="ticks entre cortes del histórico")
    a = ap.parse_args()
    events, snaps, lb, rarity_of = collect(a.offline)
    post = af.estimate(events, snaps, rarity_of)  # a ciegas: sin known, también para t18
    last = max(e["tick"] for e in events)
    hist = []
    for cut in list(range(events[0]["tick"] + a.step, last, a.step)) + [last]:
        p = af.estimate([e for e in events if e["tick"] <= cut], [s for s in snaps if s["tick"] <= cut],
                        rarity_of).get(US)
        if p:
            perm = tuple(TRUE[s] for s in af.SETS)
            hist.append({"tick": cut, "e": {s: round(p.expected(s), 3) for s in af.SETS},
                         "p_true": round(p.p[af.PERMS.index(perm)], 5), "bits": round(p.entropy_bits(), 2)})
    seen = [r for r in af.evidence(events, rarity_of) if r["team"] == US]
    out = {
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "tick": last, "events": len(events),
        "first_tick": events[0]["tick"], "snapshots": len(snaps), "conf": CONF, "true": TRUE,
        "us": calib(post[US]) if US in post else None, "history": hist,
        "evidence": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items() if k != "team"}
                     for r in sorted(seen, key=lambda r: -r["tick"])[:40]],
        "rivals": {t: {"top": max(p.top_set().items(), key=lambda kv: kv[1])[0],
                       "p16": round(max(p.top_set().values()), 3), "bits": round(p.entropy_bits(), 2),
                       "n": sum(p.n.values()), "e": {s: round(p.expected(s), 2) for s in af.SETS}}
                   for t, p in post.items() if t != US},
    }
    if lb:
        out["board"] = {"tick": lb.get("tick"), "rounds": lb.get("rounds"),
                        "teams": [{k: t.get(k) for k in ("team", "rank", "score", "negotiating", "market",
                                                          "deals", "pages_complete", "album_filled")}
                                  for t in lb["teams"]]}
    # ¿Quién más tiene CHA ×1,6? Sin señales de CHA, solo cuenta el residuo de los otros barrios (prior 1/6).
    rivals = sorted({t for t in post if t != US} | {t["team"] for t in (lb or {}).get("teams", []) if t["team"] != US})
    cha = {t: ({str(m): round(q, 4) for m, q in post[t].marginal("CHA").items()} if t in post
               else {str(m): round(1 / 6, 4) for m in af.MULTS}) for t in rivals}
    p_none = 1.0
    for m in cha.values():
        p_none *= 1 - m["1.6"]
    out["cha"] = {"teams": cha, "signals": sum(r["set"] == "CHA" for r in af.evidence(events, rarity_of)),
                  "expected_16": round(sum(m["1.6"] for m in cha.values()), 2),
                  "expected_13": round(sum(m["1.3"] for m in cha.values()), 2), "p_any_16": round(1 - p_none, 3),
                  "no_signals": [t for t in rivals if t not in post]}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    u = out["us"]
    print(f"tick {last} · {len(events)} eventos · t18 a ciegas: {u['bits'] if u else '-'} bits, "
          f"P(real)={u['p_true'] if u else '-'}, aciertos {sum(v['hit'] for v in u['sets'].values()) if u else 0}/6 "
          f"-> {OUT} ({os.path.getsize(OUT)} B)")


if __name__ == "__main__":
    main()
