"""Inspector del agente t18 en directo.

Escucha el flujo público en tiempo real (GET /api/events/stream?scope=public, SSE, sin clave), se queda con todo lo
que hace o le pasa a t18 (hilos, mensajes y ofertas, tratos, ofertas publicadas, venue, taller, huevos, sobres) y lo
escribe en tablero_web/inspector.json cada 2 s. La página tablero_web/inspector.html lo pinta en vivo.
Al arrancar rellena las últimas 2 h desde feed_all.jsonl. Solo lectura. Parar: touch practica/STOP_INSPECTOR
"""
import collections, datetime as dt, json, os, threading, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "tablero_web", "inspector.json")
LOG = os.path.join(HERE, "inspector_t18.jsonl")
URL = "https://bazaar.causaprima.ai/api/events/stream?scope=public"
US = "t18"
DN = {"picaros": "Los Pícaros", "pilar": "Doña Pilar", "chato": "El Chato", "abuela": "Abuela Carmen", "banco": "Don Ernesto"}
IC = {"picaros": "🃏", "pilar": "👒", "chato": "🧢", "abuela": "🧶", "banco": "🏦"}

DUEL = dict(session=None, name=None, total=None, closed=[], started=None, finished=False)
DOUT = os.path.join(HERE, "tablero_web", "duelos.json")

def duel_event(e):
    p, ty = e.get("payload", {}), e.get("type")
    if ty == "duels.scheduled":
        DUEL.update(session=p.get("session"), name=p.get("name"), total=p.get("duels"), closed=[], started=time.time(), finished=False)
    elif ty == "duels.finished" and p.get("session") == DUEL["session"]:
        DUEL["finished"] = True
    elif ty == "duel.closed" and (DUEL["session"] is None or p.get("session") == DUEL["session"]):
        DUEL["closed"].append(dict(ts=time.time(), status=p.get("status"), item=p.get("item"), tick=e.get("tick")))

def duel_backfill():
    try:
        with open(os.path.join(HERE, "feed_all.jsonl"), "rb") as f:
            f.seek(0, 2); f.seek(max(0, f.tell() - 6_000_000)); lines = f.read().decode("utf-8", "ignore").splitlines()[1:]
    except OSError:
        return
    evs = [json.loads(l) for l in lines if '"duel' in l]
    sch = [e for e in evs if e["type"] == "duels.scheduled"]
    if not sch: return
    last = sch[-1]; duel_event(last); t0 = last["tick"]
    for e in evs:
        if e["tick"] >= t0 and e["type"] != "duels.scheduled":
            duel_event(e)
            if e["type"] == "duel.closed": DUEL["closed"][-1]["ts"] = time.time() - 0   # hora aproximada

state = dict(connected=False, since=None, last_event=None, tick=None, t=None, events=collections.deque(maxlen=400),
             threads={}, my_venues=set(), deals_today=0, errors=0)
lock = threading.Lock()


def lado(x):
    x = x or {}
    parts = [a.get("ref", "?") for a in x.get("assets", [])] + [str(t).split(":", 1)[-1] for t in x.get("types", [])]
    if x.get("cash"): parts.append(f"{x['cash']} P")
    return " + ".join(parts) or "nada"


def mine(e):
    p = e.get("payload", {})
    if e.get("actor") == US or p.get("team") == US or p.get("sender") == US or US in (p.get("parties") or []):
        return True
    if p.get("venue") in state["my_venues"] or p.get("owner") == US:
        return True
    o = p.get("offer") if isinstance(p.get("offer"), dict) else {}
    return o.get("maker") == US or o.get("to") == US


def describe(e):
    """(icono, clase, texto) legible de un evento de t18, o None si no interesa."""
    ty, p = e.get("type"), e.get("payload", {})
    w = p.get("with")
    if ty == "thread.opened":
        top = p.get("topic") or {}
        if "buy" in top:
            b = top["buy"]; what = "comprar " + (b.get("card") or ("sobre " + str(b.get("pack")))) if isinstance(b, dict) else "comprar"
        elif "sell" in top: what = "vender"
        else: what = "hablar"
        state["threads"][p.get("thread")] = dict(with_=w, what=what, opened=e["tick"], last=e["tick"], n=0, closed=False)
        return IC.get(w, "🤝"), "open", f"Abre hilo con {DN.get(w, w)} para {what} · hilo {p.get('thread')}"
    if ty == "thread.message":
        th = state["threads"].get(p.get("thread"))
        if th: th["last"] = e["tick"]; th["n"] += 1
        o = p.get("offer") if isinstance(p.get("offer"), dict) else {}
        if p.get("sender") == US:
            return "🤖", "us", f"Nosotros a {DN.get(w, w)}: damos {lado(o.get('give'))} por {lado(o.get('want'))}" + (" · FINAL" if o.get("final") else "")
        txt = (p.get("text") or "").replace("\n", " ")
        txt = (txt[:150] + "…") if len(txt) > 150 else txt
        return IC.get(w, "💬"), "them", f"{DN.get(w, w)}: «{txt}» · da {lado(o.get('give'))} · pide {lado(o.get('want'))}" + (" · FINAL" if o.get("final") else "")
    if ty == "thread.closed":
        th = state["threads"].get(p.get("thread"))
        if th: th["closed"] = True
        return "🚪", "mut", f"Se cierra el hilo {p.get('thread')} con {DN.get(w, w)} ({p.get('reason', '')})"
    if ty == "settlement":
        other = next((x for x in p.get("parties", []) if x != US), "?")
        got = [i["ref"] for i in p.get("items", []) if i.get("to") == US]
        gave = [i["ref"] for i in p.get("items", []) if i.get("frm") == US]
        if US in p.get("parties", []):
            state["deals_today"] += 1
            for th in state["threads"].values():
                if th["with_"] == other and not th["closed"]: th["closed"] = True
            que = (f"recibimos {', '.join(got)}" if got else "") + (" y " if got and gave else "") + (f"entregamos {', '.join(gave)}" if gave else "")
            return "✅", "deal", f"TRATO con {DN.get(other, other)}{' en ' + p['venue'] if p.get('venue') else ''}: {que} por {p.get('price')} P"
        return "🏪", "mut", f"Trato en nuestro venue {p.get('venue')}: {', '.join(p.get('parties', []))} por {p.get('price')} P"
    if ty == "offer.listed":
        o = p.get("offer") if isinstance(p.get("offer"), dict) else {}
        return "📢", "list", f"Publica oferta en {p.get('venue')}: da {lado(o.get('give'))} · pide {lado(o.get('want'))}"
    if ty == "offer.cancelled":
        return None
    if ty == "venue.opened":
        state["my_venues"].add(p.get("venue"))
        return "🏪", "list", f"Abre venue {p.get('venue')} «{p.get('name')}»"
    if ty in ("venue.closing", "venue.closed"):
        return "🏪", "mut", f"Venue {p.get('venue')}: {'cerrando' if ty == 'venue.closing' else 'cerrado'}"
    if ty == "venue.announcement":
        return "📣", "mut", f"Anuncio en {p.get('venue')}: {(p.get('text') or '')[:140]}"
    if ty == "taller.crafted":
        return "🔨", "list", p.get("text") or "Taller"
    if ty in ("egg.found", "egg.given", "badge.awarded"):
        return "🥚", "deal", f"{ty}: {json.dumps({k: v for k, v in p.items() if k not in ('team', 'name')}, ensure_ascii=False)}"
    if ty == "pack.opened":
        return "📦", "mut", f"Abre un {p.get('pack')}"
    if ty == "gift.given":
        return "🎁", "mut", f"Regalo: {p.get('cards') or p.get('packs')}"
    return "•", "mut", ty


def add(e):
    d = describe(e)
    if not d: return
    ic, cls, txt = d
    item = dict(id=e.get("id"), tick=e.get("tick"), ts=time.time(), hora=dt.datetime.now().strftime("%H:%M:%S"), ic=ic, cls=cls, txt=txt, type=e.get("type"))
    state["events"].append(item)
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(json.dumps(dict(item, raw=e), ensure_ascii=False) + "\n")
    except OSError:
        pass


def backfill():
    """Últimas ~2 h de t18 desde el archivo, para no arrancar en blanco (hora estimada por tick)."""
    try:
        with open(os.path.join(HERE, "feed_all.jsonl"), "rb") as f:
            f.seek(0, 2); f.seek(max(0, f.tell() - 8_000_000)); lines = f.read().decode("utf-8", "ignore").splitlines()[1:]
    except OSError:
        return
    evs = []
    for line in lines:
        if '"t18"' not in line and '"v28"' not in line: continue
        try: evs.append(json.loads(line))
        except Exception: pass
    if not evs: return
    last_tick = max(e["tick"] for e in evs)
    for e in evs:
        if e["tick"] < last_tick - 480 or not mine(e): continue
        d = describe(e)
        if not d: continue
        ic, cls, txt = d
        ts = time.time() - (last_tick - e["tick"]) * 15
        state["events"].append(dict(id=e.get("id"), tick=e["tick"], ts=ts, hora=dt.datetime.fromtimestamp(ts).strftime("%H:%M:%S") + "≈",
                                    ic=ic, cls=cls, txt=txt, type=e.get("type")))
    state["deals_today"] = sum(1 for x in state["events"] if x["cls"] == "deal" and x["type"] == "settlement")


def reader():
    back = 2
    while not os.path.exists(os.path.join(HERE, "STOP_INSPECTOR")):
        try:
            req = urllib.request.Request(URL, headers={"Accept": "text/event-stream"})
            with urllib.request.urlopen(req, timeout=90) as r:
                with lock: state.update(connected=True, since=time.time())
                back = 2
                for raw in r:
                    line = raw.decode("utf-8", "ignore").strip()
                    if not line.startswith("data:"): continue
                    try: e = json.loads(line[5:].strip())
                    except Exception: continue
                    with lock:
                        state["last_event"] = time.time()
                        if e.get("type") == "tick" or "tick" in e:
                            state["tick"] = e.get("tick", state["tick"]); state["t"] = e.get("t", state["t"])
                        if str(e.get("type", "")).startswith("duel"): duel_event(e)
                        if e.get("type") not in ("tick", None) and mine(e): add(e)
        except Exception:
            with lock: state["connected"] = False; state["errors"] += 1
            time.sleep(back); back = min(60, back * 2)


def writer():
    while not os.path.exists(os.path.join(HERE, "STOP_INSPECTOR")):
        with lock:
            now = time.time(); ev = list(state["events"])
            acts = [x for x in ev if x["cls"] in ("us", "open", "list", "deal")]
            last_act = max((x["ts"] for x in acts), default=None)
            per_min = [0] * 30
            for x in acts:
                k = int((now - x["ts"]) // 60)
                if 0 <= k < 30: per_min[29 - k] += 1
            open_th = [dict(id=k, with_=DN.get(v["with_"], v["with_"]), ic=IC.get(v["with_"], "🤝"), what=v["what"], n=v["n"], last=v["last"])
                       for k, v in state["threads"].items() if not v["closed"] and state["tick"] and state["tick"] - v["last"] < 40]
            data = dict(now=dt.datetime.now().strftime("%H:%M:%S"), connected=state["connected"], tick=state["tick"], t=state["t"],
                        stream_age=(now - state["last_event"]) if state["last_event"] else None,
                        idle=(now - last_act) if last_act else None, per_min=per_min, deals=state["deals_today"],
                        open=open_th, events=ev[-120:][::-1])
            cl = list(DUEL["closed"]); deals = sum(1 for x in cl if x["status"] == "deal")
            per_min = [0] * 20
            for x in cl:
                k = int((now - x["ts"]) // 60)
                if 0 <= k < 20: per_min[19 - k] += 1
            items = collections.Counter(x["item"] for x in cl)
            us_row = None
            try:
                with open(os.path.join(HERE, "tablero_lb.jsonl"), "rb") as f:
                    f.seek(0, 2); f.seek(max(0, f.tell() - 20000)); last = f.read().decode("utf-8", "ignore").splitlines()[-1]
                lbh = json.loads(last); rows = sorted(lbh["teams"].items(), key=lambda kv: kv[1][0])
                us_row = dict(top=[dict(team=t, rank=v[0], score=v[1]) for t, v in rows[:5]], us=dict(rank=lbh["teams"]["t18"][0], score=lbh["teams"]["t18"][1]))
            except Exception:
                pass
            ddata = dict(now=dt.datetime.now().strftime("%H:%M:%S"), name=DUEL["name"], total=DUEL["total"], closed=len(cl), deals=deals,
                         nodeals=len(cl) - deals, finished=DUEL["finished"], per_min=per_min, top_items=items.most_common(6),
                         ticker=[dict(status=x["status"], item=x["item"]) for x in cl[-14:]][::-1], board=us_row, tick=state["tick"])
        try:
            tmp2 = DOUT + ".tmp"
            with open(tmp2, "w", encoding="utf-8") as f: json.dump(ddata, f, ensure_ascii=False)
            os.replace(tmp2, DOUT)
        except OSError:
            pass
        try:
            tmp = OUT + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, OUT)
        except OSError:
            pass
        time.sleep(2)


if __name__ == "__main__":
    backfill(); duel_backfill()
    threading.Thread(target=reader, daemon=True).start()
    print("Inspector t18 escuchando", URL, flush=True)
    writer()
