"""Tablero de alarmas y evaluación del Payday (t18). Solo lectura: feed archivado, logs de la radio y GET públicos.
Sirve http://127.0.0.1:8030 (solo este Mac) y se regenera cada 20 s. Avisos del sistema solo para lo importante:
  CRÍTICA (nos afecta a t18, pausa/reanudación, bajamos de puesto) -> alerta en pantalla + sonido Sosumi
  AVISO   (nos adelantan, épica nueva, evento en < 10 min)          -> notificación + sonido Glass
Parar: touch practica/STOP_TABLERO
"""
import collections, datetime as dt, html, json, os, re, subprocess, threading, time, urllib.request
from http.server import HTTPServer, SimpleHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
RADIO = os.environ.get("T18_RADIO_DIR", ".")
CONSOLE, RJSON, RSTATE = (os.path.join(RADIO, p) for p in ("logs-radio-console.txt", "logs/radio.jsonl", "logs/radio_state.json"))
FEED, OUT = os.path.join(HERE, "feed_all.jsonl"), os.path.join(HERE, "tablero_web")
BASE, LBHIST = os.path.join(HERE, "tablero_base.json"), os.path.join(HERE, "tablero_lb.jsonl")
API, US, PAYDAY, PORT = "https://bazaar.causaprima.ai", "t18", 1201, 8030
STARTED = time.time()

def get(path):
    with urllib.request.urlopen(API + path, timeout=15) as r:
        return json.load(r)

def esc(x):
    return html.escape(str(x))

def fnum(x, d=2):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ---------- alarmas: de la línea seca de la radio a lenguaje claro ----------
TS = re.compile(r"(\d{2}:\d{2}:\d{2})")
R_TRICK = re.compile(r"Truco FIRME de Los Pícaros: da (\S+) en vez de (\S+) \(mensaje (\d+), hilo (\d+), (t\d+), tick (\d+)\)")
R_POSS = re.compile(r"Truco POSIBLE de Los Pícaros: el texto dice (\d+) y la oferta (\d+) \(mensaje (\d+), hilo (\d+), (t\d+), tick (\d+)\)")
R_RANK = re.compile(r"Puesto de t18: (\d+)\.º → (\d+)\.º \(puntos ([\d,]+) → ([\d,]+)\)")
R_PASS = re.compile(r"Team (\d+) nos adelanta: (\d+)\.º con ([\d,]+) \(nosotros ([\d,]+)\)")
R_OVER = re.compile(r"[Aa]delantamos a (.+)")
R_PTS = re.compile(r"Puntos de t18: ([\d,]+) → ([\d,]+) \(([-+][\d,]+)\)")
R_MINT = re.compile(r"(\S+) acuñada: (\d+) → (\d+) copias")
R_NEXT = re.compile(r"Próximo en ([\d,]+) h de juego: (.+)")
R_SOON = re.compile(r"En ~(\d+) min: (.+)")

def classify(line, when):
    """-> dict(nivel, grupo, icono, titulo, que, hacer, team) o None. nivel: CRITICA > AVISO > INFO."""
    s = line.strip()
    m = R_TRICK.search(s)
    if m:
        got, want, msg, th, team, tick = m.groups()
        if team == US:
            return dict(nivel="PICAROS", grupo="picaros_nos", icono="🃏", team=team, th=int(th), tick=int(tick), kind="carta",
                        got=got, want=want, titulo=f"Pícaros intentó colarnos {got} en vez de {want}", que="", hacer="")
        return dict(nivel="INFO", grupo="picaros_otros", icono="🃏", team=team,
                    titulo=f"Pícaros engañan a {team}: {got} en vez de {want}", que=f"hilo {th}, tick {tick}", hacer="")
    m = R_POSS.search(s)
    if m:
        txt, off, msg, th, team, tick = m.groups()
        if team == US:
            return dict(nivel="PICAROS", grupo="picaros_nos", icono="🃏", team=team, th=int(th), tick=int(tick), kind="precio",
                        txt=int(txt), off=int(off), titulo=f"Pícaros: el texto dice {txt} P y la oferta {off} P", que="", hacer="")
        return dict(nivel="INFO", grupo="picaros_otros", icono="🃏", team=team,
                    titulo=f"Pícaros a {team}: texto {txt} P, oferta {off} P", que=f"hilo {th}, tick {tick}", hacer="")
    m = R_RANK.search(s)
    if m:
        a, b, pa, pb = m.groups()
        worse = int(b) > int(a)
        return dict(nivel="CRITICA" if worse else "AVISO", grupo="puesto", icono="📉" if worse else "📈", team=US,
                    titulo=f"{'Bajamos' if worse else 'Subimos'} al {b}.º puesto",
                    que=f"Antes {a}.º con {pa}; ahora {b}.º con {pb} puntos.",
                    hacer="Solo cuentan los tratos: un buen trato recupera puestos (el dinero guardado no puntúa)." if worse else "")
    m = R_PASS.search(s)
    if m:
        n, pos, sc, ours = m.groups()
        return dict(nivel="AVISO", grupo="puesto", icono="🏃", team=f"t{int(n):02d}",
                    titulo=f"Team {n} nos adelanta", que=f"Ellos {pos}.º con {sc}; nosotros {ours}.", hacer="")
    m = R_OVER.search(s)
    if m:
        return dict(nivel="AVISO", grupo="puesto", icono="🏆", team=US, titulo=f"Adelantamos a {m.group(1)}", que="", hacer="")
    m = R_PTS.search(s)
    if m:
        a, b, d = m.groups()
        return dict(nivel="INFO", grupo="puntos", icono="📊", team=US, titulo=f"Nuestros puntos: {a} → {b} ({d})",
                    que="La nota de negociación se recalcula con el mercado aunque no hagamos tratos; si hubo trato nuestro, sale en «Payday».", hacer="")
    m = R_MINT.search(s)
    if m:
        ref, a, b = m.groups()
        return dict(nivel="AVISO", grupo="epica", icono="💎", team="",
                    titulo=f"Nueva épica en circulación: {ref} (copia {b})",
                    que="Alguien acaba de conseguirla (Pícaros o Banco venden épicas desde el Payday).",
                    hacer="Mira en «Payday» quién la compró y a qué precio.")
    m = R_SOON.search(s)
    if m:
        mins, what = m.groups()
        return dict(nivel="AVISO", grupo="pronto", icono="⏰", team="", titulo=f"En ~{mins} min: {traduce_evento(what)}",
                    que=what, hacer="")
    m = R_NEXT.search(s)
    if m:
        h, what = m.groups()
        return dict(nivel="INFO", grupo="pronto", icono="🗓️", team="", titulo=f"Se acerca: {traduce_evento(what)}",
                    que=f"dentro de {h} h de juego · {what}", hacer="")
    if "pausa" in s.lower():
        return dict(nivel="CRITICA", grupo="reloj", icono="⏸️", team="", titulo="JUEGO EN PAUSA",
                    que="No se liquida nada y el calendario se retrasa.", hacer="Esperar; no hace falta tocar nada.")
    if "reanud" in s.lower():
        return dict(nivel="CRITICA", grupo="reloj", icono="▶️", team="", titulo="EL JUEGO SE HA REANUDADO",
                    que="Vuelven los tratos y el reloj.", hacer="Comprobar que el agente del operador está corriendo.")
    if "Pilar" in s or "Chato" in s or "Abuela" in s or "Ernesto" in s or "Pícaros" in s:
        return dict(nivel="INFO", grupo="dealer", icono="🏪", team="", titulo=s.split("] ", 1)[-1][:140],
                    que="Cambia lo que compra o vende un dealer.", hacer="")
    return dict(nivel="INFO", grupo="otro", icono="📻", team="", titulo=s.split("] ", 1)[-1][:160], que="", hacer="")

def traduce_evento(w):
    w2 = w.lower()
    if w2.startswith("duels"): return "Duelos (" + w.split(":")[0] + "): negociación precio + día de entrega"
    if "market test" in w2: return "Market Test (" + ("difícil" if "hard" in w2 else "normal") + ")"
    if "fever breaks" in w2: return "Se acaba la fiebre de Salamanca"
    return w

def read_alerts():
    out, last_ts = [], None
    try:
        lines = open(CONSOLE, encoding="utf-8", errors="replace").read().splitlines()[-4000:]
    except OSError:
        return out
    today = dt.date.today()
    for ln in lines:
        m = TS.search(ln)
        if m: last_ts = m.group(1)
        if not re.search(r"\[(GRAVE|ALTA|MEDIA)\]", ln): continue
        a = classify(ln, last_ts)
        if not a: continue
        a["hora"] = last_ts or "—"; a["raw"] = ln.strip(); a["key"] = ln.strip()
        try:
            a["ts"] = dt.datetime.combine(today, dt.time.fromisoformat(last_ts)).timestamp()
            if a["ts"] > time.time() + 120: a["ts"] -= 86400   # hora de ayer (el log no guarda la fecha)
        except Exception:
            a["ts"] = 0
        out.append(a)
    seen, uniq = set(), []
    for a in out:
        k = re.sub(r"\[\d{2}:\d{2}:\d{2} · ", "[", a["key"])
        if k in seen: continue
        seen.add(k); uniq.append(a)
    return uniq

def picaros_nuestros(alerts):
    """Agrupa los trucos de Pícaros contra t18 por hilo y mira en el feed cómo acabó: pillado, trato bien o colado."""
    sets = []
    try:
        for line in open(FEED, encoding="utf-8"):
            if '"settlement"' not in line or '"picaros"' not in line or '"t18"' not in line: continue
            e = json.loads(line); p = e["payload"]
            if p.get("persona") == "picaros" and US in p.get("parties", []): sets.append((e["tick"], p))
    except OSError:
        pass
    byth = collections.OrderedDict()
    for a in alerts:
        if a["grupo"] != "picaros_nos": continue
        g = byth.setdefault(a["th"], dict(first=a, last=a, n=0)); g["last"] = a; g["n"] += 1
    out = []
    for th, g in byth.items():
        a, f = dict(g["last"]), g["first"]
        st = next(((t, p) for t, p in sets if t >= f["tick"] and t <= f["tick"] + 60), None)
        intent = f"{g['n']} intento{'s' if g['n'] > 1 else ''} en el hilo {th}"
        if st:
            t, p = st
            got = [i["ref"] for i in p.get("items", []) if i.get("to") == US]
            gave = [i["ref"] for i in p.get("items", []) if i.get("frm") == US]
            if a.get("kind") == "carta" and a["got"] in got:
                a.update(nivel="CRITICA", icono="❌", titulo=f"¡Nos han colado {a['got']} en vez de {a['want']}!",
                         que=f"Trato cerrado en tick {t} por {p.get('price')} P ({intent}).", hacer="Denunciar el truco (POST /api/flags).")
            else:
                lo = f"recibimos {', '.join(got)}" if got else f"vendimos {', '.join(gave)}"
                a.update(estado="bien", icono="✅", titulo="Pícaros: lo ha pillado y cerró el trato sin perder",
                         que=f"{intent}; trato limpio en tick {t}: {lo} por {p.get('price')} P.")
        else:
            a.update(estado="pillado", icono="✅", titulo="Pícaros: lo ha pillado",
                     que=f"{intent} ({a['titulo'].replace('Pícaros ', '')}); el agente no lo aceptó y sigue negociando.")
        a["key"] = f"picaros-{th}-{a.get('estado', a['nivel'])}"
        out.append(a)
    return sorted([x for x in alerts if x["grupo"] != "picaros_nos"] + out, key=lambda x: x["ts"])

# ---------- avisos del sistema (solo lo importante, una vez) ----------
_notified = set()
def osa(script, *args):
    try:
        subprocess.Popen(["osascript", "-e", "on run argv", "-e", script, "-e", "end run", "--", *args],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass

def ring(name):
    try:
        subprocess.Popen(["afplay", f"/System/Library/Sounds/{name}.aiff"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass

def push_system(alerts):
    for a in alerts:
        if a["key"] in _notified or a["ts"] < STARTED - 5: _notified.add(a["key"]); continue
        _notified.add(a["key"])
        msg = (a["que"] + ("  →  " + a["hacer"] if a["hacer"] else ""))[:500]
        if a["nivel"] == "CRITICA":
            ring("Sosumi")
            osa("display alert (item 1 of argv) message (item 2 of argv) as critical giving up after 300", a["icono"] + " " + a["titulo"], msg)
        elif a["nivel"] == "PICAROS":
            osa("display notification (item 2 of argv) with title (item 1 of argv)", a["icono"] + " " + a["titulo"], a["que"][:200])
        elif a["nivel"] == "AVISO":
            ring("Glass")
            osa("display notification (item 2 of argv) with title (item 1 of argv)", a["icono"] + " " + a["titulo"], msg)

# ---------- copia en audio (para escuchar después; no suena en directo) ----------
AUD = os.path.join(OUT, "audios"); AUDLOG = os.path.join(HERE, "AVISOS_GRABADOS.md")
_said = set()
import queue, itertools
_Q = queue.Queue(); _N = itertools.count(1)
def _worker():
    while True:
        texto, etiqueta = _Q.get()
        try: _grabar(texto, etiqueta)
        finally: _Q.task_done()
threading.Thread(target=_worker, daemon=True).start()

def grabar(texto, etiqueta):
    _Q.put((texto, etiqueta))

def _plain(t):
    t = re.sub(r"[^\w\s.,:;¿?¡!()%+\-–—/·ºª'\"\[\]]", " ", t)
    return re.sub(r"[ \t]+", " ", t.replace("·", ",").replace("→", " a ")).strip()

def _grabar(texto, etiqueta):
    """Genera un .m4a con voz española en tablero_web/audios, su texto en audios/indice.jsonl y en AVISOS_GRABADOS.md."""
    try:
        os.makedirs(AUD, exist_ok=True)
        now = dt.datetime.now(); name = f"{now:%H%M%S}-{etiqueta}-{next(_N)}"; base = os.path.join(AUD, name)
        subprocess.run(["say", "-v", "Mónica", "-r", "178", "-o", base + ".aiff", _plain(texto)], timeout=90, check=True)
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", base + ".aiff", base + ".m4a"], timeout=60, check=True)
        os.remove(base + ".aiff")
        limpio = re.sub(r"\s*\[\[[^\]]*\]\]\s*", " · ", texto).strip(" ·")
        with open(os.path.join(AUD, "indice.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"file": name + ".m4a", "hora": f"{now:%H:%M:%S}", "tipo": etiqueta, "texto": limpio}, ensure_ascii=False) + "\n")
        with open(AUDLOG, "a", encoding="utf-8") as f:
            f.write(f"- **{now:%H:%M:%S}** · {etiqueta} · {limpio}  \n  🎧 `tablero_web/audios/{name}.m4a`\n")
    except Exception as ex:  # noqa: BLE001
        print(f"{dt.datetime.now():%H:%M:%S} ERROR audio: {ex!r}", flush=True)

import locutor
def grabar_alertas(alerts, lb):
    """Todo lo nuevo de esta vuelta, en un solo boletín de Radio Rastro (la locutora decide qué merece voz)."""
    nuevas = []
    for a in alerts:
        if a["key"] in _said: continue
        _said.add(a["key"])
        if a["ts"] >= STARTED - 5: nuevas.append(a)
    if not nuevas: return
    txt = locutor.boletin(nuevas, (lb or {}).get("teams", []), None)
    if txt:
        urgente = any(x["nivel"] == "CRITICA" for x in nuevas)
        grabar(txt, "urgente" if urgente else "boletin")

_clk = []   # (segundos reales, horas de juego) para medir cuántos minutos reales dura una hora de juego
def min_por_hora(clock):
    if clock and not clock.get("paused") and clock.get("t_hours") is not None:
        _clk.append((time.time(), clock["t_hours"])); del _clk[:-30]
    if len(_clk) >= 2 and _clk[-1][1] > _clk[0][1]:
        return (_clk[-1][0] - _clk[0][0]) / 60 / (_clk[-1][1] - _clk[0][1])
    return 60.0

_last_recap = [0.0]
def resumen_periodico(lb, clock, rstate=None):
    """Cada 30 min de juego activo, un resumen hablado con puesto, distancias, fuerza, debilidad y lo próximo."""
    if not lb or not clock or clock.get("paused") or time.time() - _last_recap[0] < 1800: return
    _last_recap[0] = time.time()
    tick_s = clock.get("tick_seconds") or 15.0; now_h = clock.get("t_hours") or 0
    up = (rstate or {}).get("obs", {}).get("upcoming", [])
    mph = min_por_hora(None)
    prox = [(max(1, round((h - now_h) * mph)), traduce_evento(w)) for h, k, w in up if h > now_h][:2]
    txt = locutor.resumen(lb.get("teams", []), prox)
    if txt: grabar(txt, "resumen")

# ---------- evaluación desde el Payday ----------
def payday_eval():
    teams = collections.defaultdict(lambda: dict(buys=[], sells=[], swaps=[], spent=0, earned=0, threads=collections.Counter(),
                                                 offers=collections.Counter(), taller=[], tricks=0, duels=0, packs=0))
    log = []
    try:
        f = open(FEED, encoding="utf-8")
    except OSError:
        return teams, log
    for line in f:
        try: e = json.loads(line)
        except Exception: continue
        if e.get("tick", 0) < PAYDAY: continue
        p, ty = e.get("payload", {}), e.get("type")
        if ty == "settlement":
            cards = [i for i in p.get("items", []) if i.get("kind") == "card"]
            price, parties = p.get("price") or 0, p.get("parties", [])
            who = p.get("persona") or p.get("venue") or "?"
            for t in parties:
                if not t.startswith("t"): continue
                got = [c for c in cards if c.get("to") == t]; gave = [c for c in cards if c.get("frm") == t]
                other = next((x for x in parties if x != t), "?")
                row = dict(tick=e["tick"], got=got, gave=gave, price=price, other=other, where=who)
                if got and not gave: teams[t]["buys"].append(row); teams[t]["spent"] += price
                elif gave and not got: teams[t]["sells"].append(row); teams[t]["earned"] += price
                else: teams[t]["swaps"].append(row)
            log.append((e["tick"], p))
        elif ty == "thread.opened" and str(p.get("team", "")).startswith("t"):
            top = p.get("topic") or {}
            k = f"{p.get('with')}: " + ("compra " + top["buy"].get("card", "?") if "buy" in top else "vende" if "sell" in top else "charla")
            teams[p["team"]]["threads"][k] += 1
        elif ty == "offer.listed" and str(e.get("actor", "")).startswith("t"):
            teams[e["actor"]]["offers"][str(p.get("venue"))] += 1
        elif ty == "taller.crafted":
            teams[p.get("team")]["taller"].append(f"{p.get('from')}→{p.get('to')}: {p.get('card')}")
        elif ty == "duel.closed":
            for t in re.findall(r'"(t\d\d)"', json.dumps(p)): teams[t]["duels"] += 1
        elif ty == "pack.opened" and str(p.get("team", "")).startswith("t"):
            teams[p["team"]]["packs"] += 1
    seen = set()
    try:
        for line in open(RJSON, encoding="utf-8"):
            r = json.loads(line)
            if r.get("event") == "picaros_trick" and r.get("tick", 0) >= PAYDAY and r.get("message") not in seen:
                seen.add(r.get("message")); teams[r["team"]]["tricks"] += 1
    except OSError:
        pass
    return teams, log

def card_txt(cs):
    return ", ".join(f"{c['ref']} <small>({esc(c.get('rarity','')[:3])} #{c.get('serial')})</small>" for c in cs)

# ---------- clasificación ----------
def load_base():
    try: return json.load(open(BASE))
    except Exception: return {}

def save_lb(lb):
    try:
        with open(LBHIST, "a") as f:
            f.write(json.dumps({"ts": time.time(), "tick": lb.get("tick"),
                                "teams": {r["team"]: [r["rank"], r["score"], r["negotiating"], r["market"], r["deals"]] for r in lb["teams"]}}) + "\n")
    except Exception:
        pass

# ---------- página ----------
CSS = """
:root{--bg:#f5f3ee;--card:#fff;--ink:#1d1d1f;--mut:#6b6b70;--line:#e3e0d8;--red:#c62828;--redbg:#fde8e8;--org:#b85c00;--orgbg:#fff1dc;
--grn:#1b7a3a;--grnbg:#e3f5e8;--blu:#1f5fbf;--blubg:#e6effc;--gry:#8a8a8f}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141416;--card:#1f1f23;--ink:#f2f2f4;--mut:#a0a0a8;--line:#33333a;
--red:#ff6b6b;--redbg:#3a1618;--org:#ffb25c;--orgbg:#3a2810;--grn:#5fd38a;--grnbg:#123222;--blu:#7fb0ff;--blubg:#16243d;--gry:#77777e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,system-ui,sans-serif}
.wrap{max-width:1200px;margin:0 auto;padding:16px}
.top{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;margin-bottom:14px}
.pill{padding:6px 12px;border-radius:999px;font-weight:700;background:var(--card);border:1px solid var(--line)}
.live{background:var(--grnbg);color:var(--grn)}.paused{background:var(--redbg);color:var(--red);animation:pulse 1.2s infinite}
@keyframes pulse{50%{opacity:.45}}
.hero{border-radius:16px;padding:20px 22px;margin-bottom:14px;border:3px solid var(--red);background:var(--redbg)}
.hero.AVISO{border-color:var(--org);background:var(--orgbg)}.hero.calm{border-color:var(--line);background:var(--card)}
.hero h1{margin:0 0 6px;font-size:30px;line-height:1.15}.hero .new{animation:pulse 1s infinite}
.hero p{margin:4px 0;font-size:17px}.hero .do{font-weight:700}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-bottom:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.big{font-size:40px;font-weight:800;line-height:1}.mut{color:var(--mut)}.small{font-size:13px}
h2{font-size:20px;margin:22px 0 10px}
.al{display:flex;gap:12px;align-items:flex-start;background:var(--card);border:1px solid var(--line);border-left:8px solid var(--gry);
border-radius:12px;padding:10px 14px;margin-bottom:8px}
.al.CRITICA{border-left-color:var(--red);background:var(--redbg)}.al.AVISO{border-left-color:var(--org)}
.al .ic{font-size:26px;line-height:1}.al .t{font-weight:700;font-size:16px}.al .h{color:var(--mut);font-size:13px;white-space:nowrap}
.al .do{font-weight:700;color:var(--red)}
.tag{display:inline-block;font-size:11px;font-weight:800;padding:2px 7px;border-radius:6px;margin-right:6px;vertical-align:2px}
.tag.CRITICA{background:var(--red);color:#fff}.tag.AVISO{background:var(--org);color:#fff}.tag.INFO{background:var(--line);color:var(--mut)}
.tag.PICAROS{background:var(--grn);color:#fff}.al.PICAROS{border-left-color:var(--grn);padding:6px 12px;font-size:13px}.al.PICAROS .t{font-size:14px}.al.PICAROS .ic{font-size:18px}
table{width:100%;border-collapse:collapse;background:var(--card);border-radius:12px;overflow:hidden}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{font-size:12px;color:var(--mut);text-transform:uppercase}
tr.us td{background:var(--blubg);font-weight:600}.up{color:var(--grn);font-weight:700}.down{color:var(--red);font-weight:700}
.scroll{overflow-x:auto}details{margin:6px 0}summary{cursor:pointer;font-weight:600}
.legend span{margin-right:14px}

.lb2{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.lb2 .lh,.lb2 .lr{display:grid;grid-template-columns:44px minmax(110px,150px) 1fr 70px 110px 56px;gap:14px;align-items:center;padding:0 16px}
.lb2 .lh{height:34px;font:600 11px system-ui;color:var(--mut);text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid var(--line)}
.lb2 .lh .lg{display:inline-block;width:9px;height:9px;border-radius:2px;margin:0 4px 0 10px;vertical-align:-1px}
.lb2 .lg.neg,.lb2 .sb .neg{background:#4c7dff}.lb2 .lg.mkt,.lb2 .sb .mkt{background:#f0a83a}
.lb2 .lr{height:48px;border-bottom:1px solid var(--line);position:relative}.lb2 .lr:last-child{border-bottom:0}
.lb2 .lr.us{background:var(--blubg)}.lb2 .lr.us::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:#1f5fbf}
.lb2 .lr.dim{opacity:.55}.lb2 .r{text-align:right}
.lb2 .rk{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;font:800 13px system-ui;background:var(--line);color:var(--ink)}
.lb2 .rk.r1{background:#e9b949;color:#3d2c00}.lb2 .rk.r2{background:#c7ccd6;color:#2a2f38}.lb2 .rk.r3{background:#d29563;color:#3a1f08}
.lb2 .tn{display:flex;flex-direction:column;line-height:1.15}.lb2 .tn b{font-size:15px}.lb2 .tn em{font-style:normal;font-size:11px;color:#1f5fbf;font-weight:700}
.lb2 .tn small{font-size:11px;color:var(--mut)}
.lb2 .sb{display:flex;height:16px;border-radius:5px;overflow:hidden;background:var(--line)}
.lb2 .sb i{display:flex;align-items:center;justify-content:flex-end;padding-right:5px;min-width:0}
.lb2 .sb i b{font:700 10px system-ui;color:#fff;white-space:nowrap}
.lb2 .pt{font:800 17px system-ui;font-variant-numeric:tabular-nums}
.lb2 .dc{display:inline-block;font:700 12px system-ui;padding:3px 8px;border-radius:999px;font-variant-numeric:tabular-nums}
.lb2 .dc.pos{background:rgba(31,157,85,.14);color:#1b7a3a}.lb2 .dc.neg{background:rgba(198,40,40,.12);color:#c62828}.lb2 .dc.eq{color:var(--mut)}
@media (prefers-color-scheme:dark){.lb2 .dc.pos{color:#5fd38a}.lb2 .dc.neg{color:#ff7b7b}.lb2 .tn em{color:#7fb0ff}}
.lb2 .ep2{font-size:12px;color:var(--mut)}.movs{margin:8px 0}.movs summary{font-size:12px;color:var(--mut)}
@media (max-width:760px){.lb2 .lh,.lb2 .lr{grid-template-columns:32px 1fr 64px 80px}.lb2 .sb,.lb2 .ep2,.lb2 .lh span:nth-child(3),.lb2 .lh span:nth-child(6){display:none}}

.lbx{display:flex;flex-direction:column;gap:6px}
.lbr{display:grid;grid-template-columns:44px 150px minmax(140px,1fr) 150px 110px minmax(0,180px);gap:12px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 14px}
.lbr.us{border:2px solid var(--blu);background:var(--blubg)}
.lbr .rk{font:800 20px system-ui;text-align:center}.lbr .bar{flex:1;height:10px;border-radius:6px;background:var(--line);overflow:hidden}
.lbr .bar i{display:block;height:100%;border-radius:6px;background:linear-gradient(90deg,#7b61ff,#1f5fbf)}
.lbr.us .bar i{background:linear-gradient(90deg,#1f9d55,#1f5fbf)}
.lbr .sc{display:flex;align-items:center;gap:10px}.lbr .scn{font:800 18px system-ui;min-width:52px;text-align:right}
.lbr .sub{font-size:12px;color:var(--mut);display:flex;flex-direction:column;gap:3px}
.mini{display:inline-block;width:60px;height:6px;border-radius:4px;background:linear-gradient(90deg,var(--blu) var(--w),var(--line) var(--w));vertical-align:middle}
.lbr .dl{font:700 14px system-ui;text-align:right}.ep{display:inline-block;font:700 11px system-ui;padding:2px 6px;border-radius:6px;background:rgba(176,97,255,.15);color:#8a4fd8;margin:2px}
.lbd{margin:-4px 0 2px 60px}.lbd summary{font-size:11px;color:var(--mut);font-weight:500;opacity:.7;list-style:none;cursor:pointer}.lbd summary::before{content:'▸ '}.lbd[open] summary::before{content:'▾ '}
@media (max-width:820px){.lbr{grid-template-columns:36px 1fr 90px}.lbr .sub,.lbr .eps{display:none}.lbr .sc{grid-column:2/4}}

.radio{background:linear-gradient(135deg,#1d1b2e,#2b1f3d);color:#f4efff;border-radius:16px;padding:16px 18px;margin-bottom:14px;border:1px solid #3d3355}
.radio .onair{font:800 12px system-ui;letter-spacing:.12em;color:#ff8a8a;display:flex;align-items:center;gap:8px;margin-bottom:8px}
.radio .dot{width:10px;height:10px;border-radius:50%;background:#ff4d4d;box-shadow:0 0 0 0 #ff4d4d;animation:onair 1.6s infinite}
@keyframes onair{0%{box-shadow:0 0 0 0 rgba(255,77,77,.7)}70%{box-shadow:0 0 0 10px rgba(255,77,77,0)}100%{box-shadow:0 0 0 0 rgba(255,77,77,0)}}
.radio .rtop{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}.radio .rbig{font:800 20px system-ui}
.radio .rtxt{font-size:18px;line-height:1.4;margin:0 0 10px}.radio audio{width:100%;max-width:520px;height:34px}
.radio .mut{color:#b9aed6}.radio details{margin-top:10px}.radio summary{color:#d9ccff}
.radio .ritem{display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-top:1px solid #3d3355}

.mono{position:fixed;inset:0;background:rgba(0,0,0,.72);display:flex;align-items:center;justify-content:center;z-index:99;padding:16px}
.mono .box{background:var(--card);border:4px solid var(--red);border-radius:22px;max-width:560px;width:100%;padding:18px 20px;text-align:center;
box-shadow:0 20px 60px rgba(0,0,0,.5);animation:shake .5s 6}
@keyframes shake{25%{transform:rotate(-1.5deg)}75%{transform:rotate(1.5deg)}}
.mono h1{margin:6px 0;font-size:26px;color:var(--red)}.mono p{margin:6px 0;font-size:17px}
.mono button{margin-top:10px;font:700 18px system-ui;padding:12px 26px;border-radius:12px;border:0;background:var(--red);color:#fff;cursor:pointer}
.mono svg{width:230px;height:230px;overflow:visible}
.mono .armL{animation:clapL .32s ease-in-out infinite alternate;transform-origin:78px 120px}
.mono .armR{animation:clapR .32s ease-in-out infinite alternate;transform-origin:122px 120px}
@keyframes clapL{from{transform:rotate(28deg)}to{transform:rotate(-6deg)}}
@keyframes clapR{from{transform:rotate(-28deg)}to{transform:rotate(6deg)}}
.mono .body{animation:bob .32s ease-in-out infinite alternate;transform-origin:100px 190px}
@keyframes bob{to{transform:translateY(-4px)}}
.mono .clang{animation:clang .64s steps(1) infinite;font:900 22px system-ui;fill:#e0a800}
@keyframes clang{0%{opacity:0}50%{opacity:1}}
.mono .eye{animation:blink 3s infinite;transform-origin:center;transform-box:fill-box}
@keyframes blink{0%,92%,100%{transform:scaleY(1)}95%{transform:scaleY(.1)}}
"""


MONO_SVG = """<svg viewBox="0 0 200 230" aria-label="mono de cuerda tocando platillos">
<g class=body>
 <rect x="62" y="118" width="76" height="80" rx="30" fill="#8b5a2b"/>
 <rect x="72" y="122" width="56" height="60" rx="12" fill="#c62828"/>
 <circle cx="100" cy="140" r="4" fill="#ffd54f"/><circle cx="100" cy="158" r="4" fill="#ffd54f"/>
 <ellipse cx="80" cy="204" rx="16" ry="9" fill="#5d3a1a"/><ellipse cx="120" cy="204" rx="16" ry="9" fill="#5d3a1a"/>
 <rect x="160" y="150" width="14" height="6" rx="3" fill="#9e9e9e"/><circle cx="178" cy="153" r="7" fill="none" stroke="#9e9e9e" stroke-width="4"/>
 <circle cx="56" cy="78" r="16" fill="#8b5a2b"/><circle cx="56" cy="78" r="9" fill="#e8b98a"/>
 <circle cx="144" cy="78" r="16" fill="#8b5a2b"/><circle cx="144" cy="78" r="9" fill="#e8b98a"/>
 <circle cx="100" cy="80" r="42" fill="#8b5a2b"/>
 <ellipse cx="100" cy="92" rx="30" ry="26" fill="#e8b98a"/>
 <ellipse class=eye cx="86" cy="76" rx="7" ry="9" fill="#fff"/><ellipse class=eye cx="114" cy="76" rx="7" ry="9" fill="#fff"/>
 <circle cx="87" cy="78" r="4" fill="#111"/><circle cx="113" cy="78" r="4" fill="#111"/>
 <path d="M80 100 Q100 122 120 100 Q100 110 80 100Z" fill="#7a1010"/><path d="M84 101 Q100 108 116 101" stroke="#fff" stroke-width="4" fill="none"/>
 <rect x="84" y="30" width="32" height="18" rx="4" fill="#c62828"/><rect x="80" y="44" width="40" height="6" rx="3" fill="#8e1b1b"/>
 <line x1="110" y1="30" x2="120" y2="20" stroke="#222" stroke-width="2"/><circle cx="121" cy="19" r="3" fill="#ffd54f"/>
</g>
<g class=armL><rect x="34" y="114" width="48" height="13" rx="6" fill="#8b5a2b"/><ellipse cx="30" cy="120" rx="8" ry="28" fill="#f2c230" stroke="#b8860b" stroke-width="3"/><circle cx="30" cy="120" r="3" fill="#b8860b"/></g>
<g class=armR><rect x="118" y="114" width="48" height="13" rx="6" fill="#8b5a2b"/><ellipse cx="170" cy="120" rx="8" ry="28" fill="#f2c230" stroke="#b8860b" stroke-width="3"/><circle cx="170" cy="120" r="3" fill="#b8860b"/></g>
<text class=clang x="100" y="14" text-anchor="middle">¡CLANG! ¡CLANG!</text>
</svg>"""

def mono_overlay(a):
    import hashlib
    k = hashlib.md5(a["key"].encode()).hexdigest()[:12]
    return (f"<div class=mono id=mono data-k='{k}'><div class=box>{MONO_SVG}<h1>{a['icono']} {esc(a['titulo'])}</h1>"
            f"<p>{esc(a['que'])}</p>" + (f"<p><b>👉 {esc(a['hacer'])}</b></p>" if a["hacer"] else "")
            + f"<div class='small mut'>{esc(a['hora'])}</div><button id=monok>Entendido</button></div></div>")

try:
    import envivo as _ev, batalla as _bt; ENVIVO_CSS = _ev.CSS + _bt.CSS
except Exception:
    ENVIVO_CSS = ""
JS_REFRESH = """<script>
function initMono(){var m=document.getElementById('mono');if(!m)return;var k='mono-'+m.dataset.k;
 try{if(localStorage.getItem(k)){m.remove();return}}catch(e){}
 var b=document.getElementById('monok');if(b)b.onclick=function(){try{localStorage.setItem(k,'1')}catch(e){}m.remove()}}
async function refresca(){
 if([...document.querySelectorAll('audio')].some(function(a){return !a.paused}))return;
 try{var r=await fetch(location.href,{cache:'no-store'});if(!r.ok)return;var d=new DOMParser().parseFromString(await r.text(),'text/html');
  var nw=d.querySelector('.wrap');if(!nw)return;
  var abiertos=[...document.querySelectorAll('details')].map(function(x){return x.open});
  var y=window.scrollY,chats=[...document.querySelectorAll('.chat')].map(function(c){return c.scrollTop});
  document.querySelector('.wrap').replaceWith(nw);document.title=d.title;
  document.querySelectorAll('details').forEach(function(x,i){if(abiertos[i])x.open=true});
  document.querySelectorAll('.chat').forEach(function(c,i){c.scrollTop=(chats[i]!==undefined)?chats[i]:c.scrollHeight});
  window.scrollTo(0,y);initMono();
 }catch(e){}}
document.addEventListener('DOMContentLoaded',function(){initMono();document.querySelectorAll('.chat').forEach(function(c){c.scrollTop=c.scrollHeight});setInterval(refresca,15000)});
</script>"""

def page(lb, clock, alerts, teams, log, base, rstate):
    now = time.time()
    tick = (clock or {}).get("tick", "?"); paused = (clock or {}).get("paused")
    tick_s = (clock or {}).get("tick_seconds") or 30.0
    rows = (lb or {}).get("teams", []); byteam = {r["team"]: r for r in rows}
    us = byteam.get(US, {}); i_us = next((i for i, r in enumerate(rows) if r["team"] == US), None)
    imp = [a for a in alerts if a["nivel"] in ("CRITICA", "AVISO") and a["grupo"] != "pronto"]
    hero = next((a for a in reversed(imp) if now - a["ts"] < 900), None)
    H = []
    H.append(f"<!doctype html><html lang=es><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
             f"{JS_REFRESH}<title>{'🚨 ' if hero and hero['nivel']=='CRITICA' else ''}Tablero t18 · tick {tick}</title><style>{CSS}{ENVIVO_CSS}</style></head><body><div class=wrap>")
    H.append("<div class=top><div><b style='font-size:20px'>Tablero t18</b> <a href='/inspector.html' style='margin-left:10px;font-weight:800;color:#ff6b6b'>🔎 Inspector EN VIVO</a> <a href='/estudio.html' style='margin-left:10px;font-weight:700'>📚 Estudio de equipos</a> <span class='mut small'>se actualiza sola cada 15 s, sin recargar · "
             f"{dt.datetime.now():%H:%M:%S}</span></div><div>"
             f"<span class='pill {'paused' if paused else 'live'}'>{'⏸ EN PAUSA' if paused else '● EN JUEGO'}</span> "
             f"<span class=pill>tick {tick} · h {fnum((clock or {}).get('t_hours',0))}</span></div></div>")
    # héroe
    if hero:
        age = int((now - hero["ts"]) // 60)
        H.append(f"<div class='hero {hero['nivel']}'><div class='mut small'>ÚLTIMA ALERTA IMPORTANTE · {esc(hero['hora'])} · hace {age} min</div>"
                 f"<h1 class={'new' if age < 2 else ''}>{hero['icono']} {esc(hero['titulo'])}</h1><p>{esc(hero['que'])}</p>"
                 + (f"<p class=do>👉 {esc(hero['hacer'])}</p>" if hero["hacer"] else "") + "</div>")
    else:
        H.append("<div class='hero calm'><h1>✅ Sin alertas importantes en los últimos 15 min</h1>"
                 "<p class=mut>Si algo nos afecta (Pícaros contra t18, pausa, bajamos de puesto), aparece aquí en grande y salta una alerta en pantalla con sonido.</p></div>")
    # Radio Rastro: el último boletín en grande y el archivo
    idx = []
    try:
        for line in open(os.path.join(OUT, "audios", "indice.jsonl"), encoding="utf-8"):
            try: idx.append(json.loads(line))
            except Exception: pass
    except OSError:
        pass
    idx = [x for x in idx if os.path.exists(os.path.join(OUT, "audios", x["file"]))][::-1]
    if idx:
        top, rest = idx[0], idx[1:12]
        TIPO = {"urgente": ("🔴", "URGENTE"), "boletin": ("📻", "BOLETÍN"), "resumen": ("🗞️", "RESUMEN"), "prueba": ("🎙️", "PRUEBA")}
        ic, lab = TIPO.get(top["tipo"], ("📻", top["tipo"].upper()))
        H.append(f"<div class='radio'><div class='onair'><span class=dot></span>EN ANTENA · RADIO RASTRO</div>"
                 f"<div class=rtop><div class=rmeta><div class=rbig>{ic} {lab}</div><div class='mut small'>{esc(top['hora'])}</div></div>"
                 f"<div style='flex:1;min-width:240px'><p class=rtxt>«{esc(top['texto'])}»</p><audio controls preload=none src='audios/{esc(top['file'])}'></audio></div></div>")
        if rest:
            H.append("<details><summary>Boletines anteriores</summary>" + "".join(
                f"<div class=ritem><div class='small mut' style='width:120px'>{TIPO.get(x['tipo'],('📻',''))[0]} {esc(x['hora'])}</div>"
                f"<div style='flex:1'><div class=small>{esc(x['texto'])}</div><audio controls preload=none src='audios/{esc(x['file'])}'></audio></div></div>" for x in rest) + "</details>")
        H.append("</div>")
    crit = next((a for a in reversed(alerts) if a["nivel"] == "CRITICA" and now - a["ts"] < 600), None)
    if crit and any(b["grupo"] == crit["grupo"] and b["ts"] > crit["ts"] for b in alerts):
        crit = None   # superada: ya hay una noticia posterior del mismo tipo (p. ej. volvimos a subir)
    if crit: H.append(mono_overlay(crit))
    # tarjetas
    H.append("<div class=grid>")
    if us:
        above = rows[i_us - 1] if i_us else None; below = rows[i_us + 1] if i_us is not None and i_us + 1 < len(rows) else None
        b = base.get("teams", {}).get(US)
        d = f" <span class={'up' if us['score']>=b['score'] else 'down'}>{us['score']-b['score']:+.2f} desde el Payday</span>" if b else ""
        H.append(f"<div class=card><div class='mut small'>NUESTRA POSICIÓN</div><div class=big>{us['rank']}.º</div>"
                 f"<div>{fnum(us['score'])} puntos{d}</div><div class='small mut'>negociación {fnum(us['negotiating'])} · mercado {fnum(us['market'])} · {us['deals']} tratos</div>"
                 + (f"<div class=small>⬆ a {fnum(above['score']-us['score'])} de {above['team']} ({above['rank']}.º)</div>" if above else "")
                 + (f"<div class=small>⬇ {below['team']} a {fnum(us['score']-below['score'])} por detrás</div>" if below else "") + "</div>")
    up = (rstate or {}).get("obs", {}).get("upcoming", []); now_h = (clock or {}).get("t_hours") or 0
    nxt = [(h, w) for h, k, w in up if h >= now_h][:4]
    if nxt:
        mph = min_por_hora(None)
        lis = "".join(f"<div><b>~{max(0,round((h-now_h)*mph))} min</b> · {esc(traduce_evento(w))}</div>" for h, w in nxt)
        H.append(f"<div class=card><div class='mut small'>LO PRÓXIMO (si no hay pausa)</div>{lis}<div class='small mut'>cierre del día: {esc(str((clock or {}).get('closes',''))[11:16])}</div></div>")
    po = [a for a in alerts if a["grupo"] == "picaros_otros" and now - a["ts"] < 3600]
    vict = collections.Counter(a["team"] for a in po)
    H.append(f"<div class=card><div class='mut small'>LOS PÍCAROS · ÚLTIMA HORA</div><div class=big>{len(po)}</div><div>trucos a otros equipos</div>"
             f"<div class='small mut'>{', '.join(f'{t}×{n}' for t,n in vict.most_common(8)) or '—'}</div>"
             f"<div class=small>Patrón: entregan otra carta del mismo barrio con número menor, o el texto dice el doble que la oferta.</div></div>")
    H.append("</div>")
    # campo de batalla: agente vs entrenamiento
    try:
        import importlib, batalla; importlib.reload(batalla)
        H.append(batalla.render())
    except Exception as ex:  # noqa: BLE001
        H.append(f"<div class='card mut'>Campo de batalla no disponible: {esc(repr(ex))}</div>")
    # negociaciones en directo
    try:
        import importlib, envivo; importlib.reload(envivo)
        H.append(envivo.render(tick if isinstance(tick, int) else None))
    except Exception as ex:  # noqa: BLE001
        H.append(f"<div class='card mut'>Negociaciones en directo no disponibles: {esc(repr(ex))}</div>")
    # historial de la radio (solo texto, sin voz)
    hist = [x for x in idx][:40] if idx else []
    imp_hist = [a for a in alerts if a["nivel"] in ("CRITICA", "AVISO", "PICAROS") and a["grupo"] != "pronto"][-40:]
    if hist or imp_hist:
        H.append("<h2>📜 Historial de la radio</h2><details><summary>Boletines y noticias importantes (texto)</summary><div class=card>"
                 + "".join(f"<div class=small style='padding:4px 0;border-bottom:1px solid var(--line)'><b>{esc(x['hora'])}</b> · {esc(x['texto'])}</div>" for x in hist)
                 + "<div class='mut small' style='margin-top:8px'>Noticias</div>"
                 + "".join(f"<div class=small>{esc(a['hora'])} · {a['icono']} {esc(a['titulo'])}</div>" for a in reversed(imp_hist))
                 + "</div></details>")
    # alertas
    H.append("<h2>🔔 Alertas</h2><div class='legend small mut'><span><span class='tag CRITICA'>CRÍTICA</span>nos afecta · alerta en pantalla</span>"
             "<span><span class='tag AVISO'>AVISO</span>conviene saberlo · notificación</span><span><span class='tag INFO'>INFO</span>contexto · solo aquí</span></div><br>")
    shown = [a for a in alerts if a["grupo"] != "picaros_otros"][-30:]
    for a in reversed(shown):
        H.append(f"<div class='al {a['nivel']}'><div class=ic>{a['icono']}</div><div style='flex:1'><div><span class='tag {a['nivel']}'>{a['nivel'].replace('CRITICA','CRÍTICA').replace('PICAROS','PÍCAROS')}</span>"
                 f"<span class=t>{esc(a['titulo'])}</span></div>" + (f"<div>{esc(a['que'])}</div>" if a['que'] else "")
                 + (f"<div class=do>👉 {esc(a['hacer'])}</div>" if a['hacer'] else "") + f"</div><div class=h>{esc(a['hora'])}</div></div>")
    if po:
        H.append("<details><summary>Ver los trucos de Los Pícaros a otros equipos (última hora)</summary>"
                 + "".join(f"<div class=small>{esc(a['hora'])} · {esc(a['titulo'])} · {esc(a['que'])}</div>" for a in reversed(po)) + "</details>")
    # payday
    H.append(f"<h2>💰 Desde el Payday (400 P a cada equipo, sábado 20:57)</h2>")
    tot_spent = sum(t["spent"] for t in teams.values()); n_set = len(log)
    epics = [(t, r) for t, v in teams.items() for r in v["buys"] for c in r["got"] if c.get("rarity") in ("epic", "legendary")]
    H.append(f"<div class=grid><div class=card><div class='mut small'>TRATOS CERRADOS</div><div class=big>{n_set}</div><div class=small>en {max(0,(tick if isinstance(tick,int) else PAYDAY)-PAYDAY)} ticks</div></div>"
             f"<div class=card><div class='mut small'>GASTADO EN COMPRAS (todos)</div><div class=big>{tot_spent} P</div><div class=small>de {len(rows)*400} P repartidos</div></div>"
             f"<div class=card><div class='mut small'>ÉPICAS COMPRADAS</div><div class=big>{len(epics)}</div><div class=small>"
             + "<br>".join(f"{t}: {', '.join(c['ref'] for c in r['got'])} a {esc(r['other'])} por {r['price']} P" for t, r in epics) + "</div></div></div>")
    # clasificación limpia: barras, cambio desde el cierre del sábado y detalle plegado
    try:
        sab = {r["team"]: r for r in json.load(open(os.path.join(HERE, "leaderboard_sabado_final.json")))["teams"]}
    except Exception:
        sab = {}
    top = max((r["score"] for r in rows), default=1) or 1
    mk_top = max((r["market"] for r in rows), default=1) or 1; ng_top = max((r["negotiating"] for r in rows), default=1) or 1
    tot_top = max((r["negotiating"] + r["market"] for r in rows), default=1) or 1
    H.append("<h2>🏆 Clasificación en vivo</h2><div class=lb2>"
             "<div class='lh'><span>#</span><span>Equipo</span><span>De dónde salen los puntos "
             "<i class='lg neg'></i>negociación <i class='lg mkt'></i>mercado</span><span class=r>Puntos</span><span class=r>Desde ayer</span><span class=r>Épicas</span></div>")
    movs = []
    for r in rows:
        t = r["team"]; v = teams.get(t) or teams[t]; s0 = sab.get(t)
        d = r["score"] - s0["score"] if s0 else None
        mv = (s0["rank"] - r["rank"]) if s0 else 0
        ep = [c["ref"] for x in v["buys"] for c in x["got"] if c.get("rarity") in ("epic", "legendary")]
        dcls = "pos" if d and d > 0.005 else "neg" if d and d < -0.005 else "eq"
        dtxt = (f"{d:+.2f}".replace(".", ",") if d is not None else "—") + (f" · {'▲' if mv > 0 else '▼'}{abs(mv)}" if mv else "")
        rk = f"<span class='rk r{r['rank']}'>{r['rank']}</span>"
        H.append(f"<div class='lr{' us' if t == US else ''}{' dim' if r['rank'] > 8 else ''}'>{rk}"
                 f"<span class=tn><b>{t}</b>{'<em>nosotros</em>' if t == US else ''}<small>{r['deals']} tratos</small></span>"
                 f"<span class=sb title='negociación {fnum(r['negotiating'])} · mercado {fnum(r['market'])}'>"
                 f"<i class=neg style='width:{r['negotiating']/tot_top*100:.1f}%'><b>{fnum(r['negotiating'],1)}</b></i>"
                 f"<i class=mkt style='width:{r['market']/tot_top*100:.1f}%'><b>{fnum(r['market'],1)}</b></i></span>"
                 f"<span class='pt r'>{fnum(r['score'])}</span><span class='r'><span class='dc {dcls}'>{dtxt}</span></span>"
                 f"<span class='r ep2'>{('💎 ' + str(len(ep))) if ep else ''}</span></div>")
        det = []
        if v["buys"]: det.append("compró " + ", ".join(f"{', '.join(c['ref'] for c in x['got'])} ({x['price']} P)" for x in v["buys"][-4:]))
        if v["sells"]: det.append("vendió " + ", ".join(f"{', '.join(c['ref'] for c in x['gave'])} ({x['price']} P)" for x in v["sells"][-4:]))
        if det and r["rank"] <= 6: movs.append(f"<div class=small><b>{t}</b>: {esc('; '.join(det))}</div>")
    H.append("</div>")
    if movs:
        H.append("<details class=movs><summary>Últimos movimientos de los 6 primeros</summary>" + "".join(movs) + "</details>")
    H.append("<p class='small mut'>Barra: negociación (azul) y mercado (ámbar) frente al máximo del momento. «Desde ayer» compara con el cierre del sábado. Solo puntúan los tratos, nunca el dinero guardado.</p>")
    H.append("</div></body></html>")
    return "".join(H)

def loop():
    rstate = None; n = 0; lb = clock = None
    while not os.path.exists(os.path.join(HERE, "STOP_TABLERO")):
        try:
            if n % 3 == 0 or lb is None:      # leaderboard cada ~60 s (el público se refresca cada pocos minutos)
                try: lb = get("/api/leaderboard"); save_lb(lb)
                except Exception: pass
            if n % 2 == 0 or clock is None:   # reloj cada ~40 s
                try: clock = get("/api/clock"); min_por_hora(clock)
                except Exception: pass
            try: rstate = json.load(open(RSTATE))
            except Exception: pass
            alerts = picaros_nuestros(read_alerts()); push_system(alerts); grabar_alertas(alerts, lb); resumen_periodico(lb, clock, rstate)
            teams, log = payday_eval()
            htmltxt = page(lb, clock, alerts, teams, log, load_base(), rstate)
            os.makedirs(OUT, exist_ok=True)
            tmp = os.path.join(OUT, "index.tmp")
            open(tmp, "w", encoding="utf-8").write(htmltxt); os.replace(tmp, os.path.join(OUT, "index.html"))
            if n % 30 == 0:   # estudio cada ~10 min
                try:
                    import estudio; estudio.build()
                except Exception as ex:  # noqa: BLE001
                    print(f"{dt.datetime.now():%H:%M:%S} ERROR estudio: {ex!r}", flush=True)
            n += 1
            print(f"{dt.datetime.now():%H:%M:%S} tablero ok · {len(alerts)} alertas · {len(log)} tratos desde Payday", flush=True)
        except Exception as ex:  # noqa: BLE001
            print(f"{dt.datetime.now():%H:%M:%S} ERROR tablero: {ex!r}", flush=True)
        time.sleep(20)
    print("STOP_TABLERO", flush=True)

class Quiet(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=OUT, **k)
    def log_message(self, *a): pass

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    srv = HTTPServer(("127.0.0.1", PORT), Quiet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"Tablero en http://127.0.0.1:{PORT}", flush=True)
    loop()
