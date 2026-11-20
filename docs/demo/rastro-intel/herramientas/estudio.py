"""Estudio de todos los equipos con todos los datos públicos: qué ha hecho cada uno, con quién, a qué precio y cómo ha
ido aprendiendo (precios frente a referencia por mitades, trucos de Pícaros que le colaron frente a los que esquivó).
Solo lectura: almacén de eventos del worktree pilar (data/feeds, todos los autores), feed_all.jsonl, logs de la radio
y GET públicos. Escribe tablero_web/estudio.html y estudio_equipos.json. Lo regenera tablero.py cada ~2 min.
Uso suelto: python3 estudio.py
"""
import collections, datetime as dt, html, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PILAR = os.environ.get("T18_PILAR_DIR", "../pilar")
RJSON = os.environ.get("T18_RADIO_LOG", "logs/radio.jsonl")
API, US = "https://bazaar.causaprima.ai", "t18"
FAIR_FROM = 559   # desde aquí el archivo público está completo: mismo tramo para todos los equipos
SAT_CLOSE_H = 13.362
DEALERS = ["abuela", "chato", "pilar", "picaros", "banco"]
DNAME = {"abuela": "Abuela (1)", "chato": "Chato (2)", "pilar": "Pilar (3)", "picaros": "Pícaros (4)", "banco": "Banco (5)"}
RAR = ["common", "uncommon", "rare", "epic", "legendary"]


def get(path):
    with urllib.request.urlopen(API + path, timeout=15) as r:
        return json.load(r)


def esc(x):
    return html.escape(str(x))


def load_events():
    """Une el almacén compartido (todos los autores) y nuestro archivo local; deduplica por id."""
    seen, ev = set(), []
    try:
        sys.path.insert(0, PILAR)
        from harness import feed_store as F  # noqa: E402
        cwd = os.getcwd(); os.chdir(PILAR)
        try:
            for e in F.load_all():
                if e.get("id") not in seen: seen.add(e.get("id")); ev.append(e)
        finally:
            os.chdir(cwd)
    except Exception:
        pass
    try:
        for line in open(os.path.join(HERE, "feed_all.jsonl"), encoding="utf-8"):
            try: e = json.loads(line)
            except Exception: continue
            if e.get("id") not in seen: seen.add(e.get("id")); ev.append(e)
    except OSError:
        pass
    ev.sort(key=lambda e: (e.get("tick", 0), e.get("id", 0)))
    return [e for e in ev if e.get("tick", 0) >= FAIR_FROM]


_REFS = []
def refs():
    if _REFS: return _REFS[0]
    _REFS.append(_refs()); return _REFS[0]

def _refs():
    """Precio de lista de cada dealer por rareza (lo que vende) y libro del catálogo."""
    book = {r: v["book"] for r, v in get("/api/catalog")["rarities"].items()}
    lists = collections.defaultdict(dict)
    for p in get("/api/dealers")["personas"]:
        for s in (p.get("menu") or {}).get("sells", []):
            if "rarity" in s: lists[p["id"]][s["rarity"]] = s["list_price"]
            if "pack" in s: lists[p["id"]]["pack:" + s["pack"]] = s["list_price"]
    return book, lists


def tricks_by_team():
    out = collections.defaultdict(list); seen = set()
    try:
        for line in open(RJSON, encoding="utf-8"):
            r = json.loads(line)
            if r.get("event") == "picaros_trick" and r.get("level") == "firme" and r.get("message") not in seen:
                seen.add(r.get("message")); out[r["team"]].append(r)
    except OSError:
        pass
    return out


def analyse(lb=None):
    ev = load_events(); book, lists = refs()
    lb = lb or get("/api/leaderboard"); now_tick = lb.get("tick")
    tmax = max((e.get("t", 0) for e in ev), default=0)
    T = collections.defaultdict(lambda: dict(
        deals=0, by=collections.Counter(), dealer=collections.defaultdict(lambda: dict(buy=[], sell=[])),
        team_buy=[], team_sell=[], swaps=0, epics=[], pic_threads=[], pic_settles=[], colados=[], limpios=[],
        packs=0, taller=0, offers=0, venue=None, venue_deals=0, hours=collections.Counter(), first_tick=None, last_tick=None,
        eggs=0, badges=[]))
    venue_owner = {}
    last_pic_topic = {}
    for e in ev:
        ty, p, tk, th = e.get("type"), e.get("payload", {}), e.get("tick", 0), e.get("t", 0)
        if ty == "venue.opened" and p.get("owner"):
            venue_owner[p["venue"]] = p["owner"]; T[p["owner"]]["venue"] = f"{p['venue']} · {p.get('name','')}"
        elif ty == "offer.listed" and str(e.get("actor", "")).startswith("t"):
            T[e["actor"]]["offers"] += 1
        elif ty == "pack.opened" and str(p.get("team", "")).startswith("t"):
            T[p["team"]]["packs"] += 1
        elif ty == "taller.crafted":
            T[p.get("team")]["taller"] += 1
        elif ty == "egg.found":
            T[p.get("team")]["eggs"] += 1
        elif ty == "badge.awarded":
            T[p.get("team")]["badges"].append(p.get("badge"))
        elif ty == "thread.opened" and p.get("with") == "picaros" and str(p.get("team", "")).startswith("t"):
            top = (p.get("topic") or {}).get("buy") or {}
            last_pic_topic[p["team"]] = (tk, top.get("card"))
            T[p["team"]]["pic_threads"].append(tk)
        elif ty == "settlement":
            items = p.get("items", []); cards = [i for i in items if i.get("kind") == "card"]
            price = p.get("price") or 0; parties = p.get("parties", []); per = p.get("persona"); ven = p.get("venue")
            if ven in venue_owner:
                own = venue_owner[ven]
                if own not in parties: T[own]["venue_deals"] += 1
            for t in parties:
                if not str(t).startswith("t"): continue
                d = T[t]; d["deals"] += 1; d["hours"][int(th)] += 1
                d["first_tick"] = d["first_tick"] or tk; d["last_tick"] = tk
                got = [c for c in cards if c.get("to") == t]; gave = [c for c in cards if c.get("frm") == t]
                packs_got = [i for i in items if i.get("kind") == "pack" and i.get("to") == t]
                for c in got:
                    if c.get("rarity") in ("epic", "legendary"):
                        d["epics"].append(dict(tick=tk, ref=c["ref"], src=per or ven or "?", price=price, dir="compra"))
                for c in gave:
                    if c.get("rarity") in ("epic", "legendary"):
                        d["epics"].append(dict(tick=tk, ref=c["ref"], src=per or ven or "?", price=price, dir="venta"))
                if per in DEALERS:
                    d["by"][per] += 1
                    if (got or packs_got) and not gave:
                        rar = got[0]["rarity"] if got else None
                        ref = lists[per].get(rar) if rar else (lists[per].get("pack:" + packs_got[0].get("pack", "")) if packs_got else None)
                        d["dealer"][per]["buy"].append(dict(tick=tk, t=th, price=price, ref=ref, what=(got[0]["ref"] if got else "sobre"), rar=rar))
                    elif gave and not got:
                        rar = gave[0]["rarity"]; ref = book.get(rar) * len(gave) if rar in book else None
                        d["dealer"][per]["sell"].append(dict(tick=tk, t=th, price=price, ref=ref, what=",".join(c["ref"] for c in gave), rar=rar))
                    if per == "picaros" and got:
                        lt = last_pic_topic.get(t); want = lt[1] if lt else None
                        row = dict(tick=tk, got=got[0]["ref"], want=want, price=price)
                        d["pic_settles"].append(row)
                        if want and got[0]["ref"] != want: d["colados"].append(row)
                        else: d["limpios"].append(row)
                else:
                    d["by"]["equipos/mercado"] += 1
                    if got and not gave:
                        d["team_buy"].append(dict(tick=tk, t=th, price=price, ref=sum(book.get(c["rarity"], 0) for c in got), what=",".join(c["ref"] for c in got)))
                    elif gave and not got:
                        d["team_sell"].append(dict(tick=tk, t=th, price=price, ref=sum(book.get(c["rarity"], 0) for c in gave), what=",".join(c["ref"] for c in gave)))
                    else:
                        d["swaps"] += 1
    tricks = tricks_by_team()
    rows = {r["team"]: r for r in lb["teams"]}
    hist = collections.defaultdict(list)
    for fn in ("leaderboard.jsonl", "tablero_lb.jsonl"):
        try:
            for line in open(os.path.join(HERE, fn)):
                h = json.loads(line)
                for t, v in h["teams"].items():
                    sc = v["score"] if isinstance(v, dict) else v[1]
                    hist[t].append((h.get("tick"), sc))
        except OSError:
            pass
    return dict(T=T, rows=rows, lb=lb, tricks=tricks, hist=hist, book=book, lists=lists, now_tick=now_tick, tmax=tmax, n_events=len(ev),
                tick_range=(ev[0]["tick"], ev[-1]["tick"]) if ev else (0, 0))


def ratio(L):
    xs = [x["price"] / x["ref"] for x in L if x.get("ref")]
    return sum(xs) / len(xs) if xs else None


def halves(L, tsplit):
    a = [x for x in L if x["t"] < tsplit]; b = [x for x in L if x["t"] >= tsplit]
    return ratio(a), ratio(b), len(a), len(b)


def pct(x):
    return "—" if x is None else f"{x*100:.0f} %"


def spark(points, w=140, h=30):
    pts = [p for p in points if p[0] is not None]
    if len(pts) < 2: return ""
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if x1 == x0: return ""
    sy = (y1 - y0) or 1
    d = " ".join(f"{(x-x0)/(x1-x0)*w:.1f},{h-(y-y0)/sy*h:.1f}" for x, y in pts)
    return f"<svg width={w} height={h} viewBox='0 0 {w} {h}' style='overflow:visible'><polyline points='{d}' fill=none stroke='currentColor' stroke-width=1.8/></svg>"


def team_story(t, d, rows, tricks, tsplit):
    """Frases cortas de cómo ha jugado y cómo ha cambiado (solo hechos medidos)."""
    S = []
    top = d["by"].most_common(2)
    if top: S.append("Juega sobre todo con " + " y ".join(f"{DNAME.get(k, k)} ({n})" for k, n in top) + ".")
    lv = [k for k in DEALERS if d["by"].get(k)]
    miss = [DNAME[k] for k in DEALERS if not d["by"].get(k)]
    if miss: S.append("En esta ventana sin tratos con " + ", ".join(miss) + " (en la escalera un nivel vacío cuenta cero).")
    for k in ("chato", "picaros", "abuela"):
        a, b, na, nb = halves(d["dealer"][k]["buy"], tsplit)
        if a is not None and b is not None and na >= 2 and nb >= 2:
            trend = "paga menos" if b < a - 0.03 else "paga más" if b > a + 0.03 else "paga igual"
            S.append(f"Comprando a {DNAME[k]}: {pct(a)} de lista antes → {pct(b)} después ({trend}).")
    tr = len(tricks.get(t, [])); col = len(d["colados"]); lim = len(d["limpios"])
    if tr or col or lim:
        S.append(f"Pícaros: {tr} trucos detectados en sus hilos; le colaron {col}, cerró limpias {lim}.")
    if d["epics"]:
        S.append("Épicas: " + "; ".join(f"{x['dir']} {x['ref']} ({x['src']}, {x['price']} P)" for x in d["epics"][-4:]) + ".")
    if d["team_buy"] or d["team_sell"]:
        S.append(f"Con otros equipos: compró {len(d['team_buy'])} (a {pct(ratio(d['team_buy']))} del libro), vendió {len(d['team_sell'])} (a {pct(ratio(d['team_sell']))}).")
    if d["venue"]:
        S.append(f"Tiene mercado {d['venue']}: {d['venue_deals']} tratos entre otros equipos allí.")
    return S


CSS = """
:root{--bg:#f5f3ee;--card:#fff;--ink:#1d1d1f;--mut:#6b6b70;--line:#e3e0d8;--red:#c62828;--grn:#1b7a3a;--blu:#1f5fbf;--blubg:#e6effc;--hi:#fff6d6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141416;--card:#1f1f23;--ink:#f2f2f4;--mut:#a0a0a8;--line:#33333a;--red:#ff6b6b;--grn:#5fd38a;--blu:#7fb0ff;--blubg:#16243d;--hi:#3a3216}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,system-ui,sans-serif}
.wrap{max-width:1300px;margin:0 auto;padding:16px}h1{font-size:24px;margin:4px 0}h2{font-size:18px;margin:24px 0 8px}
.mut{color:var(--mut)}.small{font-size:12px}a{color:var(--blu)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:10px}
table{width:100%;border-collapse:collapse;background:var(--card)}th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-size:11px;color:var(--mut);text-transform:uppercase}tr.us td{background:var(--blubg);font-weight:600}
.scroll{overflow-x:auto;border-radius:12px;border:1px solid var(--line)}.good{color:var(--grn);font-weight:700}.bad{color:var(--red);font-weight:700}
.best{background:var(--hi)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:10px}
.card h3{margin:0 0 6px;font-size:16px}.card ul{margin:4px 0 0;padding-left:18px}
"""


def build(final=False, lb=None):
    A = analyse(lb); T, rows, tricks = A["T"], A["rows"], A["tricks"]
    t0 = 6.0  # h de juego del tick FAIR_FROM
    tsplit = (t0 + A["tmax"]) / 2 if A["tmax"] else 0
    order = sorted(rows, key=lambda t: rows[t]["rank"])
    H = [f"<!doctype html><html lang=es><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
         f"<meta http-equiv=refresh content=120><title>{'Estudio final del sábado' if final else 'Estudio de equipos'}</title><style>{CSS}</style></head><body><div class=wrap>"
         f"<div class=small><a href='/'>← volver al tablero</a></div><h1>📚 {'Estudio FINAL del sábado (cerrado)' if final else 'Estudio de todos los equipos (provisional: el día sigue abierto)'}</h1>"
         f"<div class='mut small'><b>Ventana justa:</b> ticks {A['tick_range'][0]}–{A['tick_range'][1]} (h 6,0 → h {A['tmax']:.2f}), el mismo tramo para los 18 equipos: desde el tick {FAIR_FROM} el archivo público está completo; antes hay huecos que la API pública no deja recuperar (solo da los últimos 500 eventos). "
         f"«Tratos» cuenta solo esta ventana; el contador oficial del leaderboard incluye viernes y mañana. Puntos = leaderboard {'final tras el cierre' if final else 'en este momento'}. {A['n_events']} eventos · "
         f"actualizado {dt.datetime.now():%H:%M} · se regenera cada ~2 min · «antes/después» = primera/segunda mitad del juego (h {tsplit:.1f})</div>"]
    # tabla resumen
    H.append("<h2>Resumen</h2><div class=scroll><table><tr><th>#</th><th>Equipo</th><th>Puntos</th><th>Evolución</th><th>Tratos</th>"
             + "".join(f"<th>{DNAME[k]}</th>" for k in DEALERS) + "<th>Con equipos</th><th>Pícaros: colados / limpios / trucos</th><th>Épicas</th><th>Ofertas</th><th>Mercado propio</th></tr>")
    for t in order:
        r, d = rows[t], T[t]
        H.append(f"<tr class={'us' if t==US else ''}><td>{r['rank']}</td><td><b>{t}</b></td><td>{r['score']:.2f}<div class='small mut'>neg {r['negotiating']:.1f} · mer {r['market']:.1f}</div></td>"
                 f"<td>{spark(A['hist'].get(t, []))}</td><td>{d['deals']}</td>"
                 + "".join(f"<td>{d['by'].get(k) or '<span class=bad>0</span>'}</td>" for k in DEALERS)
                 + f"<td>{d['by'].get('equipos/mercado', 0)}</td>"
                 f"<td><span class={'bad' if d['colados'] else ''}>{len(d['colados'])}</span> / {len(d['limpios'])} / {len(tricks.get(t, []))}</td>"
                 f"<td>{len([x for x in d['epics'] if x['dir']=='compra'])}↓ {len([x for x in d['epics'] if x['dir']=='venta'])}↑</td>"
                 f"<td>{d['offers']}</td><td>{d['venue_deals'] if d['venue'] else '—'}</td></tr>")
    H.append("</table></div><p class='small mut'>Dealers: número de tratos con cada uno (0 en rojo = nivel vacío; según RULES cuentan los 3 mejores tratos por nivel y un hueco vale cero). "
             "Pícaros: colados = trato cerrado con otra carta que la del tema del hilo; trucos = ofertas trucadas detectadas por la radio (desde que corre). "
             "Épicas: ↓ compradas, ↑ vendidas. Mercado propio: tratos entre otros equipos en su venue.</p>")
    # quién negocia mejor con cada dealer
    H.append("<h2>¿Quién negocia mejor con cada dealer?</h2><div class=scroll><table><tr><th>Dealer</th><th>Compras: precio medio frente a lista (menos es mejor)</th><th>Ventas: precio medio frente a libro (más es mejor)</th></tr>")
    for k in DEALERS:
        b = sorted(((ratio(T[t]["dealer"][k]["buy"]), t, len(T[t]["dealer"][k]["buy"])) for t in T if ratio(T[t]["dealer"][k]["buy"]) is not None))
        s = sorted(((ratio(T[t]["dealer"][k]["sell"]), t, len(T[t]["dealer"][k]["sell"])) for t in T if ratio(T[t]["dealer"][k]["sell"]) is not None), reverse=True)
        fmt = lambda L: " · ".join(f"<span class={'us' if t==US else ''}>{'<b>' if t==US else ''}{t} {pct(x)} <small class=mut>(n={n})</small>{'</b>' if t==US else ''}</span>" for x, t, n in L[:8]) or "—"
        H.append(f"<tr><td><b>{DNAME[k]}</b></td><td>{fmt(b)}</td><td>{fmt(s)}</td></tr>")
    H.append("</table></div>")
    # fichas por equipo
    H.append("<h2>Ficha de cada equipo: cómo ha jugado y cómo ha cambiado</h2><div class=grid>")
    for t in order:
        d, r = T[t], rows[t]
        hrs = " ".join(f"h{h}:{n}" for h, n in sorted(d["hours"].items()))
        H.append(f"<div class=card style=\"{'border:2px solid var(--blu)' if t==US else ''}\"><h3>{r['rank']}.º {t}{' (nosotros)' if t==US else ''} · {r['score']:.2f}</h3><ul>"
                 + "".join(f"<li>{esc(x)}</li>" for x in team_story(t, d, rows, tricks, tsplit))
                 + f"</ul><div class='small mut'>tratos por hora de juego: {hrs or '—'} · sobres abiertos {d['packs']} · taller {d['taller']} · huevos {d['eggs']}"
                 + (f" · insignias {esc(', '.join(d['badges']))}" if d["badges"] else "") + "</div></div>")
    H.append("</div></div></body></html>")
    out = os.path.join(HERE, "tablero_web"); os.makedirs(out, exist_ok=True)
    name = "estudio_sabado_final" if final else "estudio"
    tmp = os.path.join(out, name + ".tmp"); open(tmp, "w", encoding="utf-8").write("".join(H)); os.replace(tmp, os.path.join(out, name + ".html"))
    dump = {t: dict(rank=rows[t]["rank"], score=rows[t]["score"], deals=T[t]["deals"], by=dict(T[t]["by"]),
                    dealer={k: dict(buy=T[t]["dealer"][k]["buy"], sell=T[t]["dealer"][k]["sell"]) for k in DEALERS},
                    team_buy=T[t]["team_buy"], team_sell=T[t]["team_sell"], epics=T[t]["epics"], colados=T[t]["colados"],
                    limpios=T[t]["limpios"], tricks=len(tricks.get(t, [])), venue=T[t]["venue"], venue_deals=T[t]["venue_deals"],
                    story=team_story(t, T[t], rows, tricks, tsplit)) for t in order}
    json.dump(dict(generated=dt.datetime.now().isoformat(timespec="seconds"), tick=A["now_tick"], teams=dump),
              open(os.path.join(HERE, "estudio_sabado_final.json" if final else "estudio_equipos.json"), "w"), ensure_ascii=False, indent=1)
    return A


if __name__ == "__main__":
    final = "--final" in sys.argv
    lb = None
    if final:
        lb = get("/api/leaderboard")
        json.dump(lb, open(os.path.join(HERE, "leaderboard_sabado_final.json"), "w"), ensure_ascii=False, indent=1)
    A = build(final=final, lb=lb)
    print("estudio ok ·", A["n_events"], "eventos")
