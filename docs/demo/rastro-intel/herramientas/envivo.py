"""Negociaciones de t18 en directo, leídas del feed público archivado (feed_all.jsonl): cada hilo con un dealer como
un chat (lo que dice y ofrece el dealer, lo que ofrecemos nosotros, si hay truco y cómo acaba), más nuestros tratos con
otros equipos. Solo lectura. Lo pinta tablero.py en su página."""
import html, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed_all.jsonl")
US = "t18"
DEALER = {"picaros": ("🃏", "Los Pícaros"), "pilar": ("👒", "Doña Pilar"), "chato": ("🧢", "El Chato"),
          "abuela": ("🧶", "Abuela Carmen"), "banco": ("🏦", "Don Ernesto (Banco)")}

SKIN, HAIR = "#f1c9a5", "#5b3a29"
AVATAR = {
 "abuela": f"""<svg viewBox='0 0 40 40' class=av><circle cx=20 cy=20 r=19 fill='#E07A5F'/><circle cx=20 cy=10 r=7 fill='#cfcfcf'/><circle cx=20 cy=22 r=11 fill='{SKIN}'/>
<circle cx=16 cy=21 r=3 fill=none stroke='#333' stroke-width=1.4/><circle cx=24 cy=21 r=3 fill=none stroke='#333' stroke-width=1.4/><line x1=19 y1=21 x2=21 y2=21 stroke='#333' stroke-width=1.4/>
<path d='M16 27 Q20 30 24 27' stroke='#a0522d' stroke-width=1.5 fill=none/></svg>""",
 "chato": f"""<svg viewBox='0 0 40 40' class=av><circle cx=20 cy=20 r=19 fill='#5C6B73'/><circle cx=20 cy=23 r=11 fill='{SKIN}'/>
<path d='M8 18 Q20 6 32 18 L34 19 L8 19Z' fill='#2f3a40'/><rect x=24 y=17 width=10 height=3 rx=1.5 fill='#2f3a40'/>
<circle cx=16 cy=23 r=1.4 fill='#222'/><circle cx=24 cy=23 r=1.4 fill='#222'/><line x1=16 y1=29 x2=24 y2=29 stroke='#7a3b2e' stroke-width=1.6/></svg>""",
 "pilar": f"""<svg viewBox='0 0 40 40' class=av><circle cx=20 cy=20 r=19 fill='#8E6C8A'/><circle cx=20 cy=23 r=10 fill='{SKIN}'/>
<ellipse cx=20 cy=15 rx=16 ry=4 fill='#2b2b45'/><rect x=13 y=8 width=14 height=8 rx=3 fill='#2b2b45'/><circle cx=27 cy=12 r=2.6 fill='#e85d75'/>
<circle cx=16.5 cy=23 r=1.3 fill='#222'/><circle cx=23.5 cy=23 r=1.3 fill='#222'/><path d='M17 28 Q20 30 23 28' stroke='#b0303a' stroke-width=1.5 fill=none/></svg>""",
 "picaros": f"""<svg viewBox='0 0 40 40' class=av><circle cx=20 cy=20 r=19 fill='#c62828'/>
<circle cx=13 cy=22 r=8 fill='{SKIN}'/><circle cx=27 cy=22 r=8 fill='{SKIN}'/><path d='M5 18 Q13 9 21 18Z' fill='#222'/><path d='M19 18 Q27 9 35 18Z' fill='#222'/>
<circle cx=11 cy=21 r=1.2 fill='#222'/><circle cx=15 cy=21 r=1.2 fill='#222'/><circle cx=25 cy=21 r=1.2 fill='#222'/><circle cx=29 cy=21 r=1.2 fill='#222'/>
<path d='M9 25 Q13 23 17 25' stroke='#222' stroke-width=1.6 fill=none/><path d='M23 25 Q27 23 31 25' stroke='#222' stroke-width=1.6 fill=none/></svg>""",
 "banco": f"""<svg viewBox='0 0 40 40' class=av><circle cx=20 cy=20 r=19 fill='#b8860b'/><circle cx=20 cy=24 r=10 fill='{SKIN}'/>
<rect x=12 y=5 width=16 height=11 rx=1 fill='#1a1a1a'/><rect x=8 y=15 width=24 height=3 rx=1.5 fill='#1a1a1a'/>
<circle cx=24 cy=23 r=3 fill=none stroke='#d4af37' stroke-width=1.4/><circle cx=16 cy=23 r=1.3 fill='#222'/><path d='M15 29 L25 29' stroke='#555' stroke-width=1.6/></svg>""",
}
AV_US = "<svg viewBox='0 0 40 40' class=av><circle cx=20 cy=20 r=19 fill='#1f5fbf'/><text x=20 y=26 text-anchor=middle font-size=15 font-weight=800 fill='#fff' font-family=system-ui>18</text></svg>"
MINI_MONO = """<span class=minimono><svg viewBox='0 0 120 70' width=78 height=46>
<g class=mmbody><circle cx=60 cy=30 r=16 fill='#8b5a2b'/><ellipse cx=60 cy=35 rx=11 ry=9 fill='#e8b98a'/><circle cx=55 cy=28 r=2.4 fill='#111'/><circle cx=65 cy=28 r=2.4 fill='#111'/>
<path d='M53 37 Q60 45 67 37Z' fill='#7a1010'/><rect x=51 y=10 width=18 height=7 rx=2 fill='#c62828'/><rect x=48 y=46 width=24 height=20 rx=8 fill='#c62828'/></g>
<g class=mmL><rect x=24 y=44 width=26 height=6 rx=3 fill='#8b5a2b'/><ellipse cx=22 cy=47 rx=4 ry=13 fill='#f2c230' stroke='#b8860b' stroke-width=2/></g>
<g class=mmR><rect x=70 y=44 width=26 height=6 rx=3 fill='#8b5a2b'/><ellipse cx=98 cy=47 rx=4 ry=13 fill='#f2c230' stroke='#b8860b' stroke-width=2/></g></svg>
<b>¡Nos la intentan colar!</b></span>"""


def esc(x):
    return html.escape(str(x))


def tail_events(nbytes=6_000_000):
    try:
        with open(FEED, "rb") as f:
            f.seek(0, 2); size = f.tell(); f.seek(max(0, size - nbytes))
            lines = f.read().decode("utf-8", "ignore").splitlines()[1:]
    except OSError:
        return []
    out = []
    for line in lines:
        if '"t18"' not in line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out


def cartas(x):
    x = x or {}
    return [a.get("ref", "?") for a in x.get("assets", [])] + [str(t).split(":", 1)[-1] for t in x.get("types", [])]


def lado(x):
    """Texto corto de un lado de una oferta: cartas (refs o tipos) y/o dinero."""
    x = x or {}
    parts = [a.get("ref", "?") for a in x.get("assets", [])]
    parts += [str(t).split(":", 1)[-1] for t in x.get("types", [])]
    if x.get("cash"): parts.append(f"{x['cash']} P")
    return " + ".join(parts) or "nada"


def topic_txt(top):
    top = top or {}
    if "buy" in top:
        b = top["buy"]; return "compramos " + (b.get("card") or ("sobre " + b.get("pack", "")) if isinstance(b, dict) else str(b))
    if "sell" in top:
        return "vendemos"
    return "charla"


def threads(n=6):
    ev = tail_events()
    T = {}
    for e in ev:
        p, ty = e.get("payload", {}), e.get("type")
        if ty == "thread.opened" and p.get("team") == US:
            T[p["thread"]] = dict(id=p["thread"], with_=p.get("with"), topic=p.get("topic") or {}, opened=e["tick"], msgs=[],
                                  last=e["tick"], closed=None, deal=None, sell_ref=None)
        elif ty == "thread.message" and p.get("thread") in T:
            th = T[p["thread"]]; o = p.get("offer") or {}
            th["msgs"].append(dict(tick=e["tick"], who=p.get("sender"), text=p.get("text"), give=o.get("give"), want=o.get("want"),
                                   final=o.get("final"), mid=p.get("message")))
            th["last"] = e["tick"]
            if th["topic"].get("sell") and not th["sell_ref"]:
                w = (o.get("want") if p.get("sender") != US else o.get("give")) or {}
                th["sell_ref"] = next((a.get("ref") for a in w.get("assets", [])), None)
        elif ty == "thread.closed" and p.get("thread") in T:
            T[p["thread"]]["closed"] = p.get("reason") or "cerrado"; T[p["thread"]]["last"] = e["tick"]
        elif ty == "settlement" and US in p.get("parties", []):
            other = next((x for x in p["parties"] if x != US), None)
            cand = [th for th in T.values() if th["with_"] == other and th["deal"] is None and th["opened"] <= e["tick"] <= th["last"] + 3]
            if cand:
                th = max(cand, key=lambda t: t["last"])
                got = [i["ref"] for i in p.get("items", []) if i.get("to") == US]
                gave = [i["ref"] for i in p.get("items", []) if i.get("frm") == US]
                th["deal"] = dict(tick=e["tick"], price=p.get("price"), got=got, gave=gave); th["last"] = e["tick"]
    order = sorted(T.values(), key=lambda t: t["last"], reverse=True)[:n]
    order.sort(key=lambda t: t["with_"] != "picaros")   # Los Pícaros, anclados arriba
    return order


def mercado(n=6):
    """Nuestros tratos con otros equipos (venues) más recientes."""
    out = []
    for e in tail_events():
        p = e.get("payload", {})
        if e.get("type") == "settlement" and US in p.get("parties", []) and not p.get("persona"):
            other = next((x for x in p["parties"] if x != US), "?")
            got = [i["ref"] for i in p.get("items", []) if i.get("to") == US]
            gave = [i["ref"] for i in p.get("items", []) if i.get("frm") == US]
            out.append(dict(tick=e["tick"], other=other, venue=p.get("venue"), price=p.get("price"), got=got, gave=gave))
    return out[-n:][::-1]


CSS = """

.av{width:28px;height:28px;flex:none}.row{display:flex;gap:6px;align-items:flex-end}.row.us{justify-content:flex-end}
.row .b{max-width:82%}
.th.pic{border:2px solid #c62828;box-shadow:0 0 0 3px rgba(198,40,40,.12)}
.th.pic .hd{background:linear-gradient(90deg,rgba(198,40,40,.18),transparent)}.th.pic .who{color:#c62828}
@media (prefers-color-scheme:dark){.th.pic .who{color:#ff6b6b}}
.minimono{display:flex;align-items:center;gap:6px;margin-top:6px;font-size:12px;color:#c62828}
@media (prefers-color-scheme:dark){.minimono{color:#ff8a8a}}
.minimono .mmL{animation:mmL .3s ease-in-out infinite alternate;transform-origin:50px 47px}
.minimono .mmR{animation:mmR .3s ease-in-out infinite alternate;transform-origin:70px 47px}
.minimono .mmbody{animation:mmB .3s ease-in-out infinite alternate}
@keyframes mmL{from{transform:rotate(22deg)}to{transform:rotate(-4deg)}}
@keyframes mmR{from{transform:rotate(-22deg)}to{transform:rotate(4deg)}}
@keyframes mmB{to{transform:translateY(-2px)}}
.vivo{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px;margin-bottom:14px}
.th{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;display:flex;flex-direction:column}
.th .hd{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--line)}
.th .hd .who{font-weight:800}.th .hd .tp{color:var(--mut);font-size:12px;flex:1}
.st{font:800 11px system-ui;padding:3px 8px;border-radius:999px;white-space:nowrap}
.st.on{background:#e8f0ff;color:#1f5fbf}.st.ok{background:#e3f5e8;color:#1b7a3a}.st.no{background:#eee;color:#666}
@media (prefers-color-scheme:dark){.st.on{background:#16243d;color:#7fb0ff}.st.ok{background:#123222;color:#5fd38a}.st.no{background:#333;color:#aaa}}
.st.on::before{content:"● ";animation:pulse 1.2s infinite}
.chat{padding:10px 12px;display:flex;flex-direction:column;gap:6px;max-height:340px;overflow-y:auto}
.b{max-width:88%;padding:7px 10px;border-radius:12px;font-size:13px;line-height:1.35}
.b.them{align-self:flex-start;background:var(--bg);border:1px solid var(--line);border-bottom-left-radius:4px}
.b.us{align-self:flex-end;background:#1f5fbf;color:#fff;border-bottom-right-radius:4px}
.b .chip{display:inline-block;margin-top:4px;font:700 11px system-ui;padding:2px 7px;border-radius:6px;background:rgba(127,127,127,.18)}
.b .trk{display:inline-block;margin-top:4px;font:800 11px system-ui;padding:2px 7px;border-radius:6px;background:#c62828;color:#fff}
.b .tk{font-size:10px;opacity:.6;margin-left:6px}
.deal{margin:4px 12px 12px;padding:8px 10px;border-radius:10px;background:#e3f5e8;color:#1b7a3a;font-weight:700;font-size:13px}
@media (prefers-color-scheme:dark){.deal{background:#123222;color:#5fd38a}}
"""


def render(now_tick=None):
    ths = threads()
    H = ["<h2>🤝 Nuestro agente negociando, en directo</h2>",
         "<div class='small mut' style='margin:-4px 0 8px'>Del feed público (se actualiza cada 45 s). Nuestros mensajes salen sin texto en el feed: se ve la oferta.</div>",
         "<div class=vivo>"]
    if not ths:
        H.append("<div class='card mut'>Sin hilos recientes de t18 en el archivo.</div>")
    for th in ths:
        ic, name = DEALER.get(th["with_"], ("🤝", th["with_"]))
        want_card = (th["topic"].get("buy") or {}).get("card") if isinstance(th["topic"].get("buy"), dict) else None
        tp = topic_txt(th["topic"]) + (f" {th['sell_ref']}" if th["sell_ref"] else "")
        if th["deal"]:
            st = f"<span class='st ok'>TRATO {th['deal']['price']} P</span>"
        elif th["closed"] or (now_tick and now_tick - th["last"] > 30):
            st = "<span class='st no'>SIN TRATO</span>"
        else:
            st = "<span class='st on'>EN CURSO</span>"
        pic = th["with_"] == "picaros"
        H.append(f"<div class='th{' pic' if pic else ''}'><div class=hd>{AVATAR.get(th['with_'], '')}<span class=who>{esc(name)}</span>"
                 f"<span class=tp>{esc(tp)} · hilo {th['id']}</span>{st}</div><div class=chat>")
        for m in th["msgs"][-8:]:
            if m["who"] == US:
                H.append(f"<div class='row us'><div class='b us'>Nosotros ofrecemos <b>{esc(lado(m['give']))}</b> por <b>{esc(lado(m['want']))}</b>"
                         f"{' · <b>FINAL</b>' if m['final'] else ''}<span class=tk>t{m['tick']}</span></div>{AV_US}</div>")
            else:
                txt = (m["text"] or "").replace("\n", " ")
                txt = (txt[:200] + "…") if len(txt) > 200 else txt
                gives = lado(m["give"])
                dc = cartas(m["give"])
                trick = bool(want_card and dc and want_card not in dc)
                H.append(f"<div class='row them'>{AVATAR.get(th['with_'], '')}<div class='b them'>{esc(txt) or '<i>(sin texto)</i>'}<br>"
                         f"<span class=chip>da {esc(gives)} · pide {esc(lado(m['want']))}{' · FINAL' if m['final'] else ''}</span>"
                         + (f" <span class=trk>⚠️ truco: {esc(gives)} ≠ {esc(want_card)}</span>" if trick else "")
                         + f"<span class=tk>t{m['tick']}</span>" + (MINI_MONO if trick else "") + "</div></div>")
        H.append("</div>")
        if th["deal"]:
            d = th["deal"]
            H.append(f"<div class=deal>✅ Trato en el tick {d['tick']}: "
                     + (f"recibimos {esc(', '.join(d['got']))}" if d["got"] else f"entregamos {esc(', '.join(d['gave']))}")
                     + f" por {d['price']} P</div>")
        H.append("</div>")
    H.append("</div>")
    mk = mercado()
    if mk:
        H.append("<div class=card><div class='mut small'>TRATOS CON OTROS EQUIPOS</div>" + "".join(
            f"<div class=small>t{x['tick']} · {esc(x['other'])} en {esc(x['venue'] or '?')}: "
            + (f"recibimos {esc(', '.join(x['got']))}" if x["got"] else f"entregamos {esc(', '.join(x['gave']))}")
            + f" · {x['price']} P</div>" for x in mk) + "</div>")
    return "".join(H)
