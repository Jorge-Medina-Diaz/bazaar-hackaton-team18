"""Dealer tuner (afinador): aprende de los hilos REALES de cada dealer (solo de ese dealer) los parámetros para apretar al máximo.

Por dealer, lado y grupo (barrio favorito o no · rareza) mide:
- p_sube[tam]: probabilidad de que el dealer mejore su oferta tras una concesión nuestra de ese tamaño (1, 2-3, 4+);
- final_min / final_med: en qué respuesta suya llega el primer `final`;
- perdona_max: la mayor distancia a la que ha aceptado nuestro precio;
- mejora_max: lo máximo que su oferta se ha movido desde su apertura (techo visto).
Escribe params.json y afinador_knowledge.md. Las guías leen params.json; si falta un grupo, usan sus valores por defecto.
"""
import json, os, collections, datetime, statistics as st
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALL = os.path.join(REPO, "logs", "feed.jsonl")               # feed público acumulado (affinity.py --watch / radio.py)
PARAMS = os.path.join(REPO, "docs", "dealer_params.json"); KB = os.path.join(REPO, "docs", "dealer_params.md")
FAV = {"pilar": {"SAL", "RET"}}


def rarity_of(ref):
    """Rareza por el número de la carta (catálogo: 01-05 común, 06-08 infrecuente, 09-10 rara, 11 épica, 12 legendaria)."""
    try:
        n = int(str(ref).split("-")[1])
    except (IndexError, ValueError):
        return None
    return "common" if n <= 5 else "uncommon" if n <= 8 else "rare" if n <= 10 else "epic" if n == 11 else "legendary"


def tam(x): return "1" if x <= 1 else "2-3" if x <= 3 else "4+"


def _load(paths):
    seen, ev = set(), []
    for path in paths:
        if not os.path.exists(path): continue
        with open(path) as f:
            for line in f:
                try: e = json.loads(line)
                except ValueError: continue
                if isinstance(e, dict) and "id" in e and "payload" in e and e["id"] not in seen:
                    seen.add(e["id"]); ev.append(e)
    return sorted(ev, key=lambda e: e["id"])


def learn(paths=(ALL,)):
    ev = _load(paths)
    th = {}
    for e in ev:
        p = e["payload"]
        if e["type"] == "thread.opened" and p.get("with") in ("pilar", "picaros"):
            th[p["thread"]] = dict(dealer=p["with"], team=p.get("team"), topic=p.get("topic") or {}, seq=[], ref=None, rar=None)
    for e in ev:
        p = e["payload"]; t = p.get("thread")
        if t not in th or e["type"] != "thread.message": continue
        d = th[t]; o = p.get("offer") if isinstance(p.get("offer"), dict) else {}
        buy = "buy" in d["topic"]; give, want = o.get("give") or {}, o.get("want") or {}
        if p.get("sender") == d["dealer"]:
            if buy:   # honesto solo si da la carta del tema
                ref = (d["topic"]["buy"] or {}).get("card"); refs = [a.get("ref") for a in give.get("assets") or []] + [x.split(":", 1)[1] for x in give.get("types") or [] if isinstance(x, str) and x.startswith("card:")]
                d["seq"].append(("dl", want.get("cash"), bool(o.get("final")), refs == [ref]))
                d["ref"] = ref
            else:
                d["seq"].append(("dl", give.get("cash"), bool(o.get("final")), True))
        else:
            if buy:
                d["seq"].append(("us", give.get("cash"), False, True))
            else:
                a = (give.get("assets") or [{}])[0]; d["ref"] = d["ref"] or a.get("ref"); d["rar"] = d["rar"] or a.get("rarity")
                d["seq"].append(("us", want.get("cash"), False, True))
    settle = collections.defaultdict(list)
    for e in ev:
        p = e["payload"]
        if e["type"] == "settlement" and p.get("persona") in ("pilar", "picaros"):
            team = [x for x in p["parties"] if x != p["persona"]][0]
            for i in p["items"]:
                settle[(p["persona"], team, i.get("ref"))].append((p.get("price"), i.get("rarity")))
    G = collections.defaultdict(lambda: dict(sube=collections.Counter(), tot=collections.Counter(), finals=[], perdona=[], mejora=[], cierres=[], n=0))
    for t, d in th.items():
        buy = "buy" in d["topic"]
        s = settle.get((d["dealer"], d["team"], d["ref"]), [])
        rar = d["rar"] or (s[0][1] if s else None) or rarity_of(d["ref"])
        fav = (d["ref"] or "")[:3] in FAV.get(d["dealer"], set())
        g = G[(d["dealer"], "compra" if buy else "venta", ("fav" if fav else "resto") + "·" + str(rar))]
        g["n"] += 1
        dl = [(p, f) for k, p, f, h in d["seq"] if k == "dl" and h and p]
        if not dl: continue
        g["finals"] += [i + 1 for i, (p, f) in enumerate(dl) if f][:1]
        g["mejora"].append(abs(max(p for p, _ in dl) - dl[0][0]) if not buy else abs(dl[0][0] - min(p for p, _ in dl)))
        last_us = last_dl = None; conc = None
        for k, p, f, h in d["seq"]:
            if not p: continue
            if k == "us":
                conc = None if last_us is None else (last_us - p if not buy else p - last_us)
                last_us = p
            elif k == "dl" and h:
                if conc is not None and conc > 0 and last_dl is not None:
                    g["tot"][tam(conc)] += 1
                    g["sube"][tam(conc)] += (p > last_dl) if not buy else (p < last_dl)
                if last_dl is not None and last_us is not None:
                    pass
                last_dl = p
        for price, _ in s:
            us = [p for k, p, f, h in d["seq"] if k == "us" and p]
            if price in us and dl:
                stand = [p for k, p, f, h in d["seq"] if k == "dl" and h and p]
                g["perdona"].append((stand[-1] - price) if buy else (price - stand[-1]))
            g["cierres"].append(price)
    out = {}
    for (dealer, side, grp), g in G.items():
        out[f"{dealer}|{side}|{grp}"] = dict(
            hilos=g["n"], cierres=sorted(g["cierres"]),
            p_sube={k: round(g["sube"][k] / g["tot"][k], 2) for k in g["tot"]}, n_sube=dict(g["tot"]),
            final_min=min(g["finals"]) if g["finals"] else None, final_med=st.median(g["finals"]) if g["finals"] else None,
            perdona_max=max(g["perdona"]) if g["perdona"] else None, mejora_max=max(g["mejora"]) if g["mejora"] else None)
    return out


def write(paths=(ALL,)):
    out = learn(paths)
    with open(PARAMS, "w") as f:
        json.dump(dict(updated=datetime.datetime.now().isoformat(timespec="seconds"), groups=out), f, ensure_ascii=False, indent=1)
    L = ["# Afinador · parámetros aprendidos por dealer (solo sus hilos)", "", f"Actualizado {datetime.datetime.now():%H:%M:%S}.", "",
         "| dealer · lado · grupo | hilos | cierres | P(mejora tras nuestra concesión: 1 / 2-3 / 4+) | 1.er final en su respuesta | perdona hasta | se movió hasta |",
         "|---|---|---|---|---|---|---|"]
    for k, v in sorted(out.items()):
        ps = " / ".join(f"{v['p_sube'].get(b, '—')} (n={v['n_sube'].get(b, 0)})" for b in ("1", "2-3", "4+"))
        L.append(f"| {k.replace('|', ' · ')} | {v['hilos']} | {v['cierres'][:10]} | {ps} | mín {v['final_min']} · med {v['final_med']} | {v['perdona_max']} | {v['mejora_max']} |")
    with open(KB, "w") as f:
        f.write("\n".join(L) + "\n")
    return out


def get(dealer, side, ref, rarity, fav_sets=None):
    try:
        with open(PARAMS) as f:
            g = json.load(f)["groups"]
    except Exception:
        return None
    fav = ref[:3] in (fav_sets if fav_sets is not None else FAV.get(dealer, set()))
    return g.get(f"{dealer}|{side}|{'fav' if fav else 'resto'}·{rarity}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Recalcula docs/dealer_params.json con el feed público acumulado (solo lectura).")
    ap.add_argument("feeds", nargs="*", help="ficheros JSONL de eventos; por defecto data/feeds/*/chunk-*.jsonl (todos los autores) + logs/feed.jsonl")
    a = ap.parse_args()
    from harness.feed_store import chunk_files
    write(a.feeds or chunk_files() + [ALL]); print(open(KB).read())
