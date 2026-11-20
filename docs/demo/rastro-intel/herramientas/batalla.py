"""Campo de batalla: nuestro agente contra «el entrenamiento» (lo que aprendimos del mercado).

Cada trato de t18 con un dealer es una ronda. La referencia del entrenamiento es la mediana de lo que pagaron (al
comprar) o cobraron (al vender) los demás equipos a ese mismo dealer por esa misma rareza, medida en el feed público
(tramo completo desde el tick 559). Si compramos más barato o vendimos más caro que esa mediana, gana el agente; si no,
gana el entrenamiento; a menos de 1 P es empate. La «ventaja» es cuántas primas mejor (o peor) que la referencia.
Solo lectura. Lo pinta tablero.py.
"""
import collections, html, json, os, statistics as st, time

HERE = os.path.dirname(os.path.abspath(__file__))
US = "t18"
DEALERS = ("abuela", "chato", "pilar", "picaros", "banco")
DN = {"abuela": "Abuela", "chato": "Chato", "pilar": "Pilar", "picaros": "Pícaros", "banco": "Banco"}
_cache = {"t": 0, "data": None}


def esc(x):
    return html.escape(str(x))


def _deals():
    import estudio  # reutiliza el almacén unido (data/feeds + feed_all), tramo justo
    out = []
    for e in estudio.load_events():
        if e.get("type") != "settlement": continue
        p = e["payload"]; per = p.get("persona")
        if per not in DEALERS: continue
        items = [i for i in p.get("items", []) if i.get("kind") == "card"]
        for t in p.get("parties", []):
            if not str(t).startswith("t"): continue
            got = [i for i in items if i.get("to") == t]; gave = [i for i in items if i.get("frm") == t]
            if got and not gave: side, c = "compra", got[0]
            elif gave and not got: side, c = "venta", gave[0]
            else: continue
            out.append(dict(team=t, dealer=per, side=side, rar=c.get("rarity"), ref=c.get("ref"), n=len(got or gave),
                            price=(p.get("price") or 0) / max(1, len(got or gave)), tick=e["tick"], t=e.get("t", 0)))
    return out


def datos(max_age=120):
    if _cache["data"] and time.time() - _cache["t"] < max_age:
        return _cache["data"]
    D = _deals()
    # referencia justa: mismo dealer, mismo lado, misma rareza Y mismo barrio (Pilar paga más por SAL/RET, por ejemplo);
    # solo con 5 tratos o más de los demás equipos; si no hay suficientes, la ronda no cuenta.
    ref = collections.defaultdict(list)
    for d in D:
        if d["team"] != US: ref[(d["dealer"], d["side"], d["rar"], (d["ref"] or "")[:3])].append(d["price"])
    rondas = []
    for d in D:
        if d["team"] != US: continue
        xs = ref.get((d["dealer"], d["side"], d["rar"], (d["ref"] or "")[:3]))
        if not xs or len(xs) < 5: continue
        base = st.median(xs)
        adv = (base - d["price"]) if d["side"] == "compra" else (d["price"] - base)
        res = "agente" if adv >= 1 else "entreno" if adv <= -1 else "empate"
        rondas.append(dict(d, base=base, adv=adv, res=res, nref=len(xs)))
    rondas.sort(key=lambda r: r["tick"])
    _cache.update(t=time.time(), data=rondas)
    return rondas


AGENTE = """<svg viewBox='0 0 80 80' class=fighter><circle cx=40 cy=40 r=38 fill='#1f5fbf'/><rect x=20 y=22 width=40 height=30 rx=9 fill='#dfe9ff'/>
<circle cx=31 cy=36 r=5 fill='#1f5fbf'/><circle cx=49 cy=36 r=5 fill='#1f5fbf'/><rect x=30 y=45 width=20 height=3 rx=1.5 fill='#1f5fbf'/>
<line x1=40 y1=22 x2=40 y2=12 stroke='#dfe9ff' stroke-width=3/><circle cx=40 cy=10 r=4 fill='#ffd54f'/>
<text x=40 y=68 text-anchor=middle font-size=13 font-weight=800 fill='#fff' font-family=system-ui>T18</text></svg>"""
ENTRENO = """<svg viewBox='0 0 80 80' class=fighter><circle cx=40 cy=40 r=38 fill='#6b4fd8'/>
<path d='M18 34 Q40 14 62 34 L62 40 L18 40Z' fill='#2b1f5c'/><rect x=24 y=40 width=32 height=6 fill='#2b1f5c'/>
<circle cx=40 cy=52 r=12 fill='#efe7ff'/><path d='M33 52 L38 57 L48 47' stroke='#6b4fd8' stroke-width=3.5 fill=none stroke-linecap=round/>
<line x1=60 y1=36 x2=66 y2=50 stroke='#ffd54f' stroke-width=2.5/><circle cx=66 cy=52 r=3 fill='#ffd54f'/></svg>"""

CSS = """
.bt{background:linear-gradient(135deg,#0f1b33,#24164a);color:#eef2ff;border-radius:16px;padding:16px 18px;margin-bottom:14px;border:1px solid #2e2a5a}
.bt h2{margin:0 0 2px;color:#fff}.bt .sub{color:#aab3d6;font-size:12px;margin-bottom:12px}
.bt .arena{display:grid;grid-template-columns:1fr 120px 1fr;gap:12px;align-items:center}
.bt .side{display:flex;align-items:center;gap:12px}.bt .side.r{flex-direction:row-reverse;text-align:right}
.bt .fighter{width:64px;height:64px;flex:none}.bt .side.win .fighter{animation:bob 1s ease-in-out infinite alternate}
@keyframes bob{to{transform:translateY(-5px) rotate(-3deg)}}
.bt .nm{font:800 15px system-ui}.bt .wins{font:900 40px system-ui;line-height:1}.bt .lbl{font-size:11px;color:#aab3d6;text-transform:uppercase;letter-spacing:.06em}
.bt .hp{height:8px;border-radius:5px;background:#2b2f55;overflow:hidden;margin-top:6px;width:180px;max-width:100%}
.bt .side.r .hp{margin-left:auto}.bt .hp i{display:block;height:100%}
.bt .vs{text-align:center;font:900 26px system-ui;color:#ffd54f;text-shadow:0 0 12px rgba(255,213,79,.5)}
.bt .vs small{display:block;font:600 11px system-ui;color:#aab3d6;text-shadow:none}
.bt .chart{margin-top:14px;background:rgba(255,255,255,.04);border-radius:10px;padding:8px}
.bt .rounds{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.bt .rd{font:700 11px system-ui;padding:4px 8px;border-radius:8px;background:rgba(255,255,255,.07)}
.bt .rd.agente{background:rgba(79,140,255,.25);color:#cfe0ff}.bt .rd.entreno{background:rgba(176,97,255,.25);color:#e6d4ff}
.bt .kpi{display:flex;gap:18px;flex-wrap:wrap;margin-top:10px;font-size:13px;color:#cfd6f5}.bt .kpi b{color:#fff;font-size:16px}
@media (max-width:720px){.bt .arena{grid-template-columns:1fr}.bt .vs{order:-1}.bt .side.r{flex-direction:row;text-align:left}.bt .side.r .hp{margin-left:0}}
"""


def chart(rondas, w=900, h=150):
    if len(rondas) < 2: return ""
    acc, pts = 0.0, []
    for r in rondas:
        acc += r["adv"]; pts.append((r["tick"], acc))
    x0, x1 = pts[0][0], pts[-1][0]; ys = [y for _, y in pts] + [0]; y0, y1 = min(ys), max(ys)
    sx = lambda x: 30 + (x - x0) / max(1, x1 - x0) * (w - 40)
    sy = lambda y: 10 + (y1 - y) / max(1e-9, y1 - y0) * (h - 30)
    line = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in pts)
    area = f"{sx(pts[0][0]):.1f},{sy(0):.1f} " + line + f" {sx(pts[-1][0]):.1f},{sy(0):.1f}"
    dots = "".join(f"<circle cx='{sx(r['tick']):.1f}' cy='{sy(y):.1f}' r=3.2 fill='{'#4f8cff' if r['res']=='agente' else '#b061ff' if r['res']=='entreno' else '#9aa4b8'}'/>"
                   for r, (_, y) in zip(rondas, pts))
    return (f"<svg viewBox='0 0 {w} {h}' width='100%' height='{h}' preserveAspectRatio='none'>"
            f"<defs><linearGradient id=gA x1=0 y1=0 x2=0 y2=1><stop offset=0 stop-color='#4f8cff' stop-opacity=.45/><stop offset=1 stop-color='#4f8cff' stop-opacity=0/></linearGradient></defs>"
            f"<line x1=30 x2={w-10} y1='{sy(0):.1f}' y2='{sy(0):.1f}' stroke='#5a6290' stroke-dasharray='4 4'/>"
            f"<text x=4 y='{sy(0)+4:.1f}' font-size=11 fill='#aab3d6' font-family=system-ui>0</text>"
            f"<text x=4 y=16 font-size=11 fill='#aab3d6' font-family=system-ui>{y1:+.0f}</text>"
            f"<polygon points='{area}' fill='#4f8cff' fill-opacity='.16'/><polyline points='{line}' fill=none stroke='#4f8cff' stroke-width=2.5/>{dots}</svg>")


def render():
    try:
        R = datos()
    except Exception as ex:  # noqa: BLE001
        return f"<div class='card mut'>Campo de batalla no disponible: {esc(repr(ex))}</div>"
    if not R:
        return ""
    wa = sum(r["res"] == "agente" for r in R); we = sum(r["res"] == "entreno" for r in R); dr = len(R) - wa - we
    adv = sum(r["adv"] for r in R)
    hoy = [r for r in R if r["tick"] >= 1446]; adv_hoy = sum(r["adv"] for r in hoy)
    lead = "agente" if wa > we else "entreno" if we > wa else ""
    tot = max(1, wa + we)
    by = collections.defaultdict(lambda: [0, 0])
    for r in R:
        if r["res"] == "agente": by[r["dealer"]][0] += 1
        elif r["res"] == "entreno": by[r["dealer"]][1] += 1
    best = max(by.items(), key=lambda kv: kv[1][0] - kv[1][1], default=None)
    H = [f"<div class=bt><h2>⚔️ Campo de batalla: nuestro agente vs el entrenamiento</h2>"
         f"<div class=sub>Cada trato con un dealer es una ronda. El entrenamiento = la mediana que consiguen los demás equipos con ese dealer, esa rareza y ese barrio (mínimo 5 tratos de referencia). "
         f"Gana el agente si compra más barato o vende más caro.</div><div class=arena>"
         f"<div class='side{' win' if lead=='agente' else ''}'>{AGENTE}<div><div class=nm>Nuestro agente</div><div class=wins>{wa}</div>"
         f"<div class=lbl>rondas ganadas</div><div class=hp><i style='width:{wa/tot*100:.0f}%;background:linear-gradient(90deg,#4f8cff,#7fb0ff)'></i></div></div></div>"
         f"<div class=vs>VS<small>{len(R)} rondas · {dr} empates</small></div>"
         f"<div class='side r{' win' if lead=='entreno' else ''}'>{ENTRENO}<div><div class=nm>El entrenamiento</div><div class=wins>{we}</div>"
         f"<div class=lbl>rondas ganadas</div><div class=hp><i style='width:{we/tot*100:.0f}%;background:linear-gradient(90deg,#b061ff,#d6a8ff)'></i></div></div></div></div>"
         f"<div class=kpi><span>Ventaja acumulada: <b>{adv:+.0f} P</b></span><span>Hoy: <b>{adv_hoy:+.0f} P</b> en {len(hoy)} rondas</span>"
         + (f"<span>Donde más gana: <b>{DN.get(best[0], best[0])}</b> ({best[1][0]}–{best[1][1]})</span>" if best else "") + "</div>"
         f"<div class=chart><div class=lbl style='margin:0 0 4px 4px'>Primas de ventaja acumuladas frente al entrenamiento</div>{chart(R)}</div><div class=rounds>"]
    for r in R[-10:][::-1]:
        verb = "compra" if r["side"] == "compra" else "vende"
        H.append(f"<span class='rd {r['res']}' title='referencia {r['base']:.0f} P (n={r['nref']})'>{'🔵' if r['res']=='agente' else '🟣' if r['res']=='entreno' else '⚪'} "
                 f"{DN.get(r['dealer'], r['dealer'])}: {verb} {esc(r['ref'])} a {r['price']:.0f} (ref {r['base']:.0f}) {r['adv']:+.0f}</span>")
    H.append("</div></div>")
    return "".join(H)
