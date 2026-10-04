"""Entrenamiento continuo con Doña Pilar desde el feed PÚBLICO (sin clave, solo GET; cada 90 s en vivo, cada 5 min en pausa).
Guarda eventos de Pilar en pilar_events.jsonl (dedupe por id) y regenera pilar_knowledge.md tras cada lectura.
Parar: crear el archivo STOP en esta carpeta. No escribe nada en el juego ni fuera de esta carpeta.
"""
import json, os, time, urllib.request, statistics as st, collections, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, "pilar_events.jsonl"); KB = os.path.join(HERE, "pilar_knowledge.md")
URL = "https://bazaar.causaprima.ai/api/feed?limit=500"; CLOCK = "https://bazaar.causaprima.ai/api/clock"
EVERY_PAUSED, EVERY_LIVE = 90, 60   # en pausa basta cada 5 min; en vivo cada 90 s (domingo, tick 15 s: el feed cubre ~6 min)
FAV = {"SAL", "RET"}

def load_seen():
    seen, rows = set(), []
    if os.path.exists(EV):
        for line in open(EV):
            e = json.loads(line); seen.add(e["id"]); rows.append(e)
    return seen, rows

ALL = os.path.join(HERE, "feed_all.jsonl")   # TODO el feed público (historia de equipos), misma lectura, sin GET extra
_all_seen = None

def archive_all(events):
    global _all_seen
    if _all_seen is None:
        _all_seen = set()
        if os.path.exists(ALL):
            for line in open(ALL):
                try: _all_seen.add(json.loads(line)["id"])
                except Exception: pass
    n = 0
    with open(ALL, "a") as f:
        for e in events:
            if e.get("id") not in _all_seen:
                _all_seen.add(e["id"]); f.write(json.dumps(e, ensure_ascii=False) + "\n"); n += 1
    return n

def ingest(events, seen, rows, pil_threads):
    new = 0
    archive_all(events)
    for e in events:
        p = e.get("payload", {})
        if e["type"] == "thread.opened" and p.get("with") == "pilar": pil_threads.add(p["thread"])
    with open(EV, "a") as f:
        for e in events:
            p = e.get("payload", {})
            rel = (p.get("with") == "pilar" or p.get("persona") == "pilar" or p.get("thread") in pil_threads
                   or (e["type"] == "settlement" and "pilar" in (p.get("parties") or [])))
            if rel and e["id"] not in seen:
                seen.add(e["id"]); rows.append(e); f.write(json.dumps(e, ensure_ascii=False) + "\n"); new += 1
    return new

def analyse(rows):
    th = collections.defaultdict(lambda: {"pilar": [], "team": [], "meta": None, "settle": None, "closed": None})
    for e in sorted(rows, key=lambda e: e["id"]):
        p = e["payload"]; t = p.get("thread")
        if e["type"] == "thread.opened" and t: th[t]["meta"] = dict(p, tick=e["tick"], t=e.get("t"))
        elif e["type"] == "thread.message" and t:
            o = p.get("offer") or {}
            if p.get("sender") == "pilar":
                th[t]["pilar"].append((e["tick"], (o.get("give") or {}).get("cash"), bool(o.get("final")), (p.get("text") or "")[:90]))
            else:
                a = ((o.get("give") or {}).get("assets") or [{}])[0]
                th[t]["team"].append((e["tick"], (o.get("want") or {}).get("cash"), a.get("ref"), a.get("rarity")))
        elif e["type"] == "thread.closed" and t: th[t]["closed"] = p.get("reason")
    settles = [e for e in rows if e["type"] == "settlement" and "pilar" in (e["payload"].get("parties") or [])]
    # enlaza liquidación -> hilo por equipo + ref
    for s in settles:
        p = s["payload"]; team = [x for x in p["parties"] if x != "pilar"][0]; it = p["items"][0]
        cands = []
        for t, d in th.items():
            m = d["meta"] or {}
            ticks = [x[0] for x in d["pilar"] + d["team"] if x[0] <= s["tick"]]
            if m.get("team") == team and d["settle"] is None and ticks and any(r == it.get("ref") for _, _, r, _ in d["team"]):
                cands.append((max(ticks), t))
        if cands:
            d = th[max(cands)[1]]
            d["settle"] = dict(price=p.get("price"), ref=it.get("ref"), rarity=it.get("rarity"), set=it.get("set"), tick=s["tick"], t=s.get("t"))
    out = []
    for t, d in th.items():
        m = d["meta"] or {}
        if "sell" not in (m.get("topic") or {}): continue
        ref = next((r for _, _, r, _ in d["team"] if r), None) or (d["settle"] or {}).get("ref")
        rar = next((r for _, _, _, r in d["team"] if r), None) or (d["settle"] or {}).get("rarity")
        if not ref or not d["pilar"]: continue
        ps = [x[1] for x in d["pilar"] if x[1]]; asks = [x[1] for x in d["team"] if x[1]]
        s = d["settle"]; who = None
        if s:
            last_her = ps[-1] if ps else None
            who = ("aceptan_el_suyo" if s["price"] in ps else
                   "ella_acepta_nuestro" if s["price"] in asks else "sin_mensaje_visto")
        fever = (m.get("t") or 0) >= 9.15 and (m.get("t") or 0) < 11.15 and ref.startswith("SAL")
        out.append(dict(thread=t, team=m.get("team"), ref=ref, set=ref[:3], rarity=rar, open=ps[0] if ps else None,
                        top=max(ps) if ps else None, final=any(x[2] for x in d["pilar"]), replies=len(ps),
                        raises=sum(1 for a, b in zip(ps, ps[1:]) if b > a), asks=asks, min_ask=min(asks) if asks else None,
                        price=s["price"] if s else None, who=who, closed=d["closed"], fever=fever,
                        gap_end=(min(asks) - ps[-1]) if asks and ps else None))
    return out

def med(xs): xs = [x for x in xs if x is not None]; return st.median(xs) if xs else None

def write_kb(out):
    groups = collections.defaultdict(list)
    for r in out: groups[("SAL/RET" if r["set"] in FAV else "otros") + " · " + str(r["rarity"]) + (" · FIEBRE" if r["fever"] else "")].append(r)
    L = [f"# Doña Pilar · conocimiento acumulado", "",
         f"Actualizado {datetime.datetime.now():%H:%M:%S}. Fuente: feed público (sin clave). {len(out)} hilos de venta con respuesta; "
         f"{sum(1 for r in out if r['price'])} con trato.", "",
         "| Grupo | n | tratos | apertura (mediana) | cierre (mediana) | cierre máx | subidas (mediana) | respuestas hasta final | ¿aceptó precio nuestro? |",
         "|---|---|---|---|---|---|---|---|---|"]
    for g, rs in sorted(groups.items()):
        deals = [r for r in rs if r["price"]]
        L.append(f"| {g} | {len(rs)} | {len(deals)} | {med([r['open'] for r in rs])} | {med([r['price'] for r in deals])} | "
                 f"{max([r['price'] for r in deals], default='—')} | {med([r['raises'] for r in rs])} | {med([r['replies'] for r in deals])} | "
                 f"{sum(r['who']=='ella_acepta_nuestro' for r in deals)}/{len(deals)} |")
    acc = [r for r in out if r["who"] == "ella_acepta_nuestro"]
    L += ["", "## Experimento clave: ¿acepta Pilar un precio nuestro?", "",
          (f"**SÍ, {len(acc)} vez/veces**: " + "; ".join(f"{r['ref']} a {r['price']} (su tope ofrecido {r['top']})" for r in acc)) if acc
          else "Aún ningún caso observado: todos los tratos son a la oferta de Pilar. La estrategia 'converger' sigue sin confirmar.",
          "", "## Sin trato", ""]
    nd = [r for r in out if not r["price"] and r["closed"]]
    L += [f"- {r['ref']} ({r['team']}): cerrado `{r['closed']}`, su tope {r['top']}, nuestro mínimo {r['min_ask']}" for r in nd] or ["- ninguno cerrado sin trato"]
    L += ["", "## Hilos (más recientes al final)", "", "| hilo | equipo | carta | rareza | apertura | tope | precio | quién acepta | respuestas | asks |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(out, key=lambda r: r["thread"])[-40:]:
        L.append(f"| {r['thread']} | {r['team']} | {r['ref']} | {r['rarity']} | {r['open']} | {r['top']} | {r['price'] or '—'} | {r['who'] or r['closed'] or 'abierto'} | {r['replies']} | {r['asks'][:8]} |")
    L += ["", "_Hipótesis, no reglas del servidor. El texto de Pilar no es señal: solo `final`._"]
    open(KB, "w").write("\n".join(L) + "\n")

def main():
    seen, rows = load_seen(); pil = {e["payload"]["thread"] for e in rows if e["type"] == "thread.opened"}
    seed = os.path.join(HERE, "feed_seed.json")
    if os.path.exists(seed):
        d = json.load(open(seed)); ingest(d.get("events", d) if isinstance(d, dict) else d, seen, rows, pil)
    while not os.path.exists(os.path.join(HERE, "STOP")):
        try:
            req = urllib.request.Request(URL, headers={"User-Agent": "t18-pilar-watch"})
            d = json.load(urllib.request.urlopen(req, timeout=20)); evs = d.get("events", d) if isinstance(d, dict) else d
            n = ingest(evs, seen, rows, pil); out = analyse(rows); write_kb(out)
            try:
                import importlib, picaros_estudio; importlib.reload(picaros_estudio); pk = picaros_estudio.write()
                print(f"   pícaros: {pk[0]} hilos · {pk[1]} violaciones", flush=True)
            except Exception as ex:
                print(f"   pícaros error {type(ex).__name__}: {ex}", flush=True)
            print(f"{datetime.datetime.now():%H:%M:%S} +{n} eventos · {len(out)} hilos", flush=True)
        except Exception as ex:
            print(f"{datetime.datetime.now():%H:%M:%S} error {type(ex).__name__}: {ex}", flush=True)
        every = EVERY_PAUSED
        try:
            c = json.load(urllib.request.urlopen(urllib.request.Request(CLOCK, headers={"User-Agent": "t18-pilar-watch"}), timeout=15))
            every = EVERY_PAUSED if c.get("paused") else EVERY_LIVE
            print(f"   reloj tick {c.get('tick')} paused={c.get('paused')} -> siguiente lectura en {every}s", flush=True)
        except Exception as ex:
            print(f"   reloj error {type(ex).__name__}", flush=True)
        for _ in range(every):
            if os.path.exists(os.path.join(HERE, "STOP")): break
            time.sleep(1)
    print("STOP", flush=True)

if __name__ == "__main__": main()
