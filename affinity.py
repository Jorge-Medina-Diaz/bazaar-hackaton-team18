"""Estimate every rival's multiplier per barrio (set) from public trades and score evolution. Read-only: GETs through
client("read") (allowlisted, rate-limited); never writes to the game.

    python3 affinity.py                       # table: E[multiplier] per team and set, and P(set is its 1.6)
    python3 affinity.py --conf 0.9            # credible sets at 90 % (default 80 %)
    python3 affinity.py --set SAL             # who values SAL most (buyers) / least (sellers)
    python3 affinity.py --card SAL-10 --price 80   # P(each team values SAL-10 >= 80): to whom to sell, from whom to buy
    python3 affinity.py --team t13            # one team in detail, with its evidence counts
    python3 affinity.py --calibrate           # run blind on us (t18) and compare with our real affinity
    python3 affinity.py --watch 60            # keep recording feed + leaderboard snapshots (the score evolution)
    python3 affinity.py --history 5           # replay the estimate every 5 ticks -> logs/affinity_history.json
    python3 affinity.py --offline             # only logs/, no network

Each run appends new feed events to logs/feed.jsonl, a new leaderboard snapshot to logs/leaderboard.jsonl, a summary
to logs/affinity.jsonl and the full table to logs/affinity.json (other modules: agent.affinity.load(), offline).
Score evolution only works for intervals we recorded: leave --watch running (it is cheap: 2 GETs per call).
"""
import argparse, json, os, sys, time  # noqa: E401

from agent import affinity as af
from agent.journal import LOG_DIR, log

FEED, LB = os.path.join(LOG_DIR, "feed.jsonl"), os.path.join(LOG_DIR, "leaderboard.jsonl")


_T = None


def get(path: str, query: dict | None = None) -> dict:
    global _T
    if _T is None:
        from agent.client import client
        _T = client("read")
    return _T._get(path, query)


def jsonl(path: str) -> list:
    return [json.loads(line) for line in open(path, encoding="utf-8")] if os.path.exists(path) else []


def collect(offline: bool) -> tuple:
    events = {e["id"]: e for e in jsonl(FEED)}
    snaps = jsonl(LB)
    cat = None
    if not offline:
        new = [e for e in get("/api/feed", {"limit": 500})["events"] if e["id"] not in events]
        for e in sorted(new, key=lambda e: e["id"]):
            log("feed", **e)
            events[e["id"]] = e
        lb = get("/api/leaderboard")
        rnd = next((r["round"] for r in lb.get("rounds", []) if r.get("status") == "active"), lb.get("round"))
        if not snaps or snaps[-1]["tick"] != lb["snapshot_tick"]:
            row = {"tick": lb["snapshot_tick"], "round": rnd,
                   "teams": {t["team"]: t["negotiating"] for t in lb["teams"]},
                   "deals": {t["team"]: t["deals"] for t in lb["teams"]}}
            log("leaderboard", **row)
            snaps.append(row)
        cat = get("/api/catalog")
    rarity_of = {c["id"]: c["rarity"] for s in (cat or {}).get("sets", []) for c in s["cards"]}
    return [events[k] for k in sorted(events)], snaps, rarity_of


def ours(offline: bool):
    """Our real affinity from /api/me (needs BAZAAR_KEY); None if not available."""
    if offline:
        return None
    try:
        me = get("/api/me")
        return me["id"], me["affinity"]
    except Exception:  # no key or no network: the estimate still works, just without the self-anchor
        return None


def fmt(x: float) -> str:
    return f"{x:.2f}"


def table(post: dict, conf: float, us: str | None) -> None:
    print(f"E[multiplicador] por barrio · ★ = barrio más probable de ser su 1,6 (prob.) · creíble al {conf:.0%}")
    print(f"{'equipo':<6} " + " ".join(f"{s:>5}" for s in af.SETS) + "   ★ top        datos  bits")
    for t in sorted(post, key=lambda t: (t == us, t)):
        p = post[t]
        top = max(p.top_set().items(), key=lambda kv: kv[1])
        print(f"{t:<6} " + " ".join(f"{p.expected(s):>5.2f}" for s in af.SETS)
              + f"   {top[0]} {top[1]:>4.0%}   {sum(p.n.values()):>5}  {p.entropy_bits():>4.1f}")
    print("\nbits: incertidumbre que queda (9,5 = nada sabido; 0 = permutación segura).")


def detail(p, conf: float) -> None:
    print(f"{p.team} · evidencia: {dict(p.n)} · incertidumbre {p.entropy_bits():.1f} bits")
    best, pb = p.map()
    print(f"permutación más probable ({pb:.1%}): " + " ".join(f"{s}×{m}" for s, m in best.items()))
    for s in af.SETS:
        mg = p.marginal(s)
        bars = " ".join(f"{m}:{mg[m]:>4.0%}" for m in af.MULTS)
        print(f"  {s}  E={p.expected(s):.2f}  P(≥1,3)={p.p_at_least(s, 1.3):>4.0%}  "
              f"{conf:.0%} → {sorted(p.credible(s, conf))}   {bars}")


def card(post: dict, ref: str, price: float, rarity_of: dict, conf: float, us: str | None) -> None:
    st, rar = ref.split("-")[0], rarity_of.get(ref) or {"11": "epic", "12": "legendary"}.get(ref.split("-")[1])
    if not rar:
        n = int(ref.split("-")[1])
        rar = "common" if n <= 5 else "uncommon" if n <= 8 else "rare"
    book = af.BOOK[rar]
    print(f"{ref} ({rar}, libro {book}) a {price}: P(le vale ≥ {price}) por equipo (1.ª copia)")
    rows = sorted(((t, p.p_worth(st, book, price), p.value(st, book)) for t, p in post.items() if t != us),
                  key=lambda r: -r[1])
    for t, pw, v in rows:
        tag = "COMPRADOR" if pw >= conf else "VENDEDOR" if 1 - pw >= conf else ""
        print(f"  {t:<5} {pw:>4.0%}   valor esperado {v['expected']:>6}  [{v['low']}–{v['high']}]  {tag}")
    print(f"COMPRADOR: P ≥ {conf:.0%} de que lo valore por encima (venderle a {price}). "
          f"VENDEDOR: P ≥ {conf:.0%} de que lo valore por debajo (comprarle a {price}).")


def summary(p) -> dict:
    return {"e": {s: round(p.expected(s), 3) for s in af.SETS}, "p16": {s: round(q, 3) for s, q in p.top_set().items()},
            "bits": round(p.entropy_bits(), 2), "n": sum(p.n.values())}


def history(events: list, snaps: list, rarity_of: dict, known: dict, step: int) -> list:
    """The estimate as it would have been at every `step` ticks: how each team's multipliers came into focus."""
    ticks = [e["tick"] for e in events]
    out = []
    for cut in list(range(min(ticks) + step, max(ticks), step)) + [max(ticks)]:
        post = af.estimate([e for e in events if e["tick"] <= cut], [s for s in snaps if s["tick"] <= cut],
                           rarity_of, known)
        out.append({"tick": cut, "teams": {t: summary(p) for t, p in post.items() if t not in known}})
    with open(os.path.join(LOG_DIR, "affinity_history.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return out


def save(post: dict, tick: int) -> None:
    rows = {t: {"expected": {s: round(p.expected(s), 3) for s in af.SETS},
                "marginal": {s: {str(m): round(q, 4) for m, q in p.marginal(s).items()} for s in af.SETS},
                "top": {s: round(q, 4) for s, q in p.top_set().items()},
                "evidence": dict(p.n), "bits": round(p.entropy_bits(), 2)} for t, p in post.items()}
    with open(os.path.join(LOG_DIR, "affinity.json"), "w", encoding="utf-8") as f:
        json.dump({"tick": tick, "teams": rows}, f, ensure_ascii=False, indent=1)
    log("affinity", tick=tick, top={t: max(r["top"], key=r["top"].get) for t, r in rows.items()},
        bits={t: r["bits"] for t, r in rows.items()})


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    ap = argparse.ArgumentParser()
    ap.add_argument("--conf", type=float, default=0.8)
    ap.add_argument("--set")
    ap.add_argument("--card")
    ap.add_argument("--price", type=float)
    ap.add_argument("--team")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--watch", type=int, metavar="SECONDS")
    ap.add_argument("--history", type=int, metavar="TICKS")
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()

    if a.watch:
        while True:
            events, snaps, _ = collect(False)
            print(f"tick {snaps[-1]['tick'] if snaps else '?'}: {len(events)} eventos, {len(snaps)} snapshots")
            time.sleep(a.watch)

    events, snaps, rarity_of = collect(a.offline)
    me = ours(a.offline)
    us, known = (me[0], {me[0]: me[1]}) if me else ("t18", {})
    if a.calibrate:
        post = af.estimate(events, snaps, rarity_of)
        if us not in post:
            print(f"sin evidencia pública de {us}")
            return
        detail(post[us], a.conf)
        if known:
            truth = known[us]
            print("real:      " + " ".join(f"{s}×{truth.get(s)}" for s in af.SETS))
            hits = sum(truth.get(s) in post[us].credible(s, a.conf) for s in af.SETS)
            p_true = post[us].p[af.PERMS.index(tuple(truth[s] for s in af.SETS))]
            print(f"el valor real cae en el intervalo al {a.conf:.0%} en {hits}/6 barrios · "
                  f"P(permutación real) = {p_true:.2%} (a priori {1 / 720:.2%})")
        return
    if a.history:
        h = history(events, snaps, rarity_of, known, a.history)
        print(f"{len(h)} cortes (ticks {h[0]['tick']}–{h[-1]['tick']}) -> logs/affinity_history.json")
        return
    post = af.estimate(events, snaps, rarity_of, known)
    tick = max((e["tick"] for e in events), default=0)
    save(post, tick)
    print(f"{len(events)} eventos (ticks {events[0]['tick'] if events else '-'}–{tick}), "
          f"{len(snaps)} snapshots del leaderboard, {len(af.score_jumps(snaps, events))} saltos de puntuación usados\n")
    if a.team:
        detail(post[a.team], a.conf)
    elif a.card:
        card(post, a.card.upper(), a.price or 0, rarity_of, a.conf, us)
    elif a.set:
        st = a.set.upper()
        print(f"{st}: quién lo valora más (P de que {st} sea su 1,6 · P(≥1,3) · E)")
        for t, p in sorted(post.items(), key=lambda kv: -kv[1].expected(st)):
            print(f"  {t:<5} {p.marginal(st)[1.6]:>4.0%}  {p.p_at_least(st, 1.3):>4.0%}  {p.expected(st):.2f}"
                  f"   {a.conf:.0%} → {sorted(p.credible(st, a.conf))}")
    else:
        table(post, a.conf, us)


if __name__ == "__main__":
    main()
