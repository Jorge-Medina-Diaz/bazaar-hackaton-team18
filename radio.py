"""Radio Rastro para el equipo 18: noticias nuevas, su relevancia para t18 y un aviso en esta máquina.

Solo lecturas públicas sin clave (GET /api/news, /api/clock, /api/leaderboard, /api/dealers, /api/catalog,
/api/levels, /api/schedule). No escribe nada
en el juego, no toca agent/ (el code_hash del operador no cambia) y el texto de las noticias nunca decide cifras:
es una señal para el operador y el analista. La radio mezcla noticias ciertas, rumores y ruido.

Uso:
  python3 radio.py                 # lee una vez e imprime todas las noticias con su relevancia
  python3 radio.py --watch         # vigila con ritmo adaptativo y avisa (notificación de macOS) de lo nuevo
  python3 radio.py --watch --min-level MEDIA --no-notify

Ritmo: nunca más rápido que un tick. Tras una noticia nueva, vigila tick a tick un rato (suelen venir con
ventanas cortas: "una hora, no más"); después se ajusta a una fracción del intervalo medio entre noticias.
Con las puertas cerradas espera a la siguiente apertura. Graba en logs/radio.jsonl (gitignored) y recuerda las
ya vistas en logs/radio_state.json, así que al reiniciar no repite avisos.

Cambios para t18: en cada lectura se compara una foto pública con la anterior y se avisa con el cambio exacto
(antes → después): nuestro puesto y puntos (y quién nos adelanta), dealers nuevos o que se abren, precios y
compras de cada dealer, barrios publicados, épicas/legendarias acuñadas, niveles y el próximo evento del
calendario. Si cambia el menú de un dealer en la hora siguiente a una noticia sobre él, el aviso lo marca como
confirmación. El precio que paga hoy no es público: confirmarlo siempre en el hilo, bajo el Gate.
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request

import picaros

URL = os.environ.get("BAZAAR_URL", "https://bazaar.causaprima.ai").rstrip("/")
LOG_DIR = os.environ.get("BAZAAR_LOGS", "logs")
LEVELS = ("BAJA", "MEDIA", "ALTA")

# Nuestra situación (docs/knowledge.md, docs/operador-cartas-fuertes.md). Cambia poco; se pasa a mano si cambia.
MULT = {"CHA": 1.6, "RET": 1.3, "SAL": 1.1, "LAT": 0.9, "LAV": 0.7, "MAL": 0.5}
ROLE = {"CHA": "objetivo del domingo (×1,6)", "RET": "página completa (×1,3): proteger", "SAL":
        "página completa (×1,1): proteger", "LAT": "abandonada (×0,9): vender", "LAV": "valor bajo (×0,7): vender",
        "MAL": "valor bajo (×0,5): vender"}
SET_NAMES = {"CHA": ("chamberi",), "RET": ("retiro",), "SAL": ("salamanca",), "LAT": ("la latina", "latina"),
             "LAV": ("lavapies",), "MAL": ("malasana",)}
DEALERS = {"abuela": ("abuela", "carmen"), "chato": ("chato",), "pilar": ("pilar",)}
WORDS = {
    "demand": ("looking for", "buys", "buying", "pays above", "pays more", "wants", "collects", "busca", "compra",
               "paga mas", "paga por encima"),
    "supply": ("sells", "selling", "discount", "cheap", "sale", "offers", "vende", "rebaja", "barato", "oferta"),
    "scarce": ("sold out", "runs out", "closes", "closed", "shuts", "agotad", "cierra", "cerrad"),
    "urgent": ("hour", "minutes", "today", "tonight", "until", "now", "hora", "minutos", "hoy", "ahora"),
    "rarity_top": ("legendary", "epic", "gold pack", "legendaria", "epica", "sobre de oro"),
    "rare": ("rare", "rara"),
    "team": ("team 18", "equipo 18", "t18"),
    "duels": ("duel", "duelo"),
    "market": ("venue", "market", "fee", "mercado", "comision"),
    "hearsay": ("my cousin", "i swear", "rumour", "rumor", "someone said", "mi primo", "lo juro"),
}


def norm(text):
    return "".join(c for c in unicodedata.normalize("NFKD", str(text or "").lower()) if not unicodedata.combining(c))


_LAST_GET = [0.0]
GAP_S = 0.35          # separación mínima entre lecturas: nunca una ráfaga


class RateLimited(Exception):
    def __init__(self, wait):
        super().__init__(f"429: esperar {wait:.0f} s")
        self.wait = wait


def get(path, timeout=10):
    pause = GAP_S - (time.time() - _LAST_GET[0])
    if pause > 0:
        time.sleep(pause)
    _LAST_GET[0] = time.time()
    req = urllib.request.Request(URL + path, headers={"User-Agent": "t18-radio/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            try:
                wait = float(e.headers.get("Retry-After") or 60)
            except (TypeError, ValueError):
                wait = 60.0
            raise RateLimited(max(5.0, wait)) from None
        raise


def card_names(catalog):
    """{nombre normalizado: ref} para reconocer cartas citadas por su nombre."""
    out = {}
    for s in (catalog or {}).get("sets", []):
        for c in s.get("cards", []):
            if c.get("name") and c.get("id"):
                out[norm(c["name"])] = c["id"]
    return out


def _is_rare(ref):
    return ref[4:6] in ("09", "10")   # en cada barrio: 01-05 comunes, 06-08 infrecuentes, 09-10 raras


def classify(item, names=None, have=None):
    """Relevancia de una noticia para t18. Determinista; el texto solo se lee, nunca se ejecuta.

    `have` (opcional): refs que tenemos. Si se pasa y piden raras de un barrio del que no tenemos ninguna,
    la noticia baja un nivel: no podemos aprovecharla."""
    text = norm(f"{item.get('headline', '')} {item.get('body', '')}")
    has = {k: any(re.search(r"\b" + re.escape(w), text) for w in ws) for k, ws in WORDS.items()}
    sets = {s for s, ws in SET_NAMES.items() if any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in ws)}
    refs = set(re.findall(r"\b(?:cha|ret|sal|lat|lav|mal)-\d{2}\b", text))
    refs = {r.upper() for r in refs}
    for name, ref in (names or {}).items():
        if len(name) >= 6 and name in text:
            refs.add(ref)
    sets |= {r[:3] for r in refs}
    dealers = {d for d, ws in DEALERS.items() if any(re.search(r"\b" + w + r"\b", text) for w in ws)}
    score, why, todo = 0, [], []
    if has["team"]:
        score += 4
        why.append("menciona al equipo 18")
    for s in sorted(sets, key=lambda x: -MULT[x]):
        if s in ("CHA", "RET", "SAL"):
            score += 2
            why.append(f"{s}: {ROLE[s]}")
            if has["demand"]:
                todo.append(f"Demanda de {s}: vender solo repetidas a ≥ V + 1; nunca la copia única de una página.")
            if has["supply"]:
                todo.append(f"Oferta de {s}: comprar solo con ganancia (a un dealer, ≤ V − 1; a un equipo, ≤ V − 3)."
                            if s == "CHA" else f"Oferta de {s}: la página ya está completa; solo interesa a ≤ V − 50.")
        else:
            score += 2 if has["demand"] else 0
            why.append(f"{s}: {ROLE[s]}")
            if has["demand"]:
                ours = sorted(r for r in (have or ()) if r.startswith(s) and (_is_rare(r) or not has["rare"]))
                if have is not None and not ours:
                    score -= 2
                    why.append(f"no tenemos {'raras de ' if has['rare'] else ''}{s} (--have)")
                else:
                    todo.append(f"Demanda de {s}: oportunidad de venta" + (f" ({', '.join(ours)})" if ours else
                                f". Comprobar si tenemos {s} ({'raras' if has['rare'] else 'cartas'})")
                                + " y vender a ≥ V + 1.")
    for d in sorted(dealers):
        score += 2 if d == "pilar" else 1
        why.append({"abuela": "dealer Abuela (nivel 1)", "chato": "dealer El Chato (nivel 2)",
                    "pilar": "Doña Pilar (nivel 3): escalera que más pesa"}[d])
    if dealers and has["demand"]:
        todo.append("Venta a dealer: neg no baja si p ≥ V + 1 y el trato con ganancia llena escalera. "
                    "El ejecutor no vende a dealers: `bazaar.py do` primero en seco.")
    if has["rarity_top"]:
        score += 1
        why.append("épicas/legendarias o sobre de oro (no se persiguen: ver docs/operador-cartas-fuertes.md)")
    if has["scarce"]:
        score += 1
        why.append("escasez o cierre")
    if has["duels"]:
        score += 1
        why.append("duelos")
    if has["market"]:
        score += 1
        why.append("mercados o comisiones")
    if has["urgent"] and score:
        score += 1
        why.append("ventana corta")
    if item.get("source") == "boletin":
        why.append("fuente: Boletín del Bazar")
    rumour = item.get("source") == "tablon" or has["hearsay"]
    if rumour:
        why.append("probable rumor (El Tablón o «me dijeron»)")
        todo.insert(0, "No actuar sin evidencia: esperar el veredicto del feed o un cambio de menú.")
    level = "ALTA" if score >= 4 else "MEDIA" if score >= 2 else "BAJA"
    side = "compra" if has["demand"] else "vende" if has["supply"] else None   # lo que haría el dealer
    return {"level": level, "side": side, "rare": has["rare"], "rumour": rumour, "score": score, "sets": sorted(sets), "refs": sorted(refs), "dealers": sorted(dealers),
            "why": why or ["sin relación directa con t18"], "todo": todo}


def interval(ticks, tick_s, seen_new_recently):
    """Segundos hasta la próxima lectura: nunca menos de un tick; nunca más de 1 minuto."""
    tick_s = max(5.0, float(tick_s or 30.0))
    if seen_new_recently:
        return tick_s
    gaps = [b - a for a, b in zip(ticks, ticks[1:]) if b > a]
    if not gaps:
        return max(tick_s, 60.0)
    return max(tick_s, min(60.0, statistics.median(gaps) * tick_s / 8))


SOUNDS = {"ALTA": "/System/Library/Sounds/Hero.aiff", "MEDIA": "/System/Library/Sounds/Glass.aiff",
          "BAJA": "/System/Library/Sounds/Tink.aiff"}
LOUD = {"sound": True, "dialog": True}       # --no-sound / --no-dialog
_RANG = [0.0]


def notify_cmd(title, message):
    script = ["on run argv", "display notification (item 2 of argv) with title (item 1 of argv)", "end run"]
    return ["osascript"] + [x for line in script for x in ("-e", line)] + ["--", str(title)[:120], str(message)[:240]]


def dialog_cmd(title, message):
    """Alerta en pantalla que se queda hasta pulsar OK (o 2 minutos). Texto como argumento, sin inyección."""
    script = ["on run argv", "display alert (item 1 of argv) message (item 2 of argv) as critical "
              "giving up after 120", "end run"]
    return ["osascript"] + [x for line in script for x in ("-e", line)] + ["--", str(title)[:120], str(message)[:600]]


def ring_cmd(level):
    return ["afplay", SOUNDS.get(level, SOUNDS["MEDIA"])]


def notify(title, message, level="MEDIA"):
    """Aviso en esta máquina: notificación, sonido del sistema (sin voz: nunca se lee el contenido en voz alta)
    y, si es ALTA, una alerta en pantalla. Nada bloquea el bucle."""
    if sys.platform != "darwin":
        return False
    ok = False
    try:
        ok = subprocess.run(notify_cmd(title, message), capture_output=True, timeout=10).returncode == 0
        if LOUD["sound"] and time.time() - _RANG[0] >= 2:
            _RANG[0] = time.time()
            subprocess.Popen(ring_cmd(level), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if LOUD["dialog"] and level == "ALTA":
            subprocess.Popen(dialog_cmd(title, message), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return ok
    return ok


def load_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            s = json.load(f)
        if isinstance(s, dict):
            return {"seen": list(s.get("seen", [])), "ticks": list(s.get("ticks", [])), "watch": s.get("watch", {}),
                    "obs": s.get("obs"), "announced": list(s.get("announced", []))[-200:], "clock": s.get("clock"),
                    "tricks": list(s.get("tricks", []))[-500:]}
    except (OSError, ValueError):
        pass
    return {"seen": [], "ticks": [], "watch": {}, "obs": None, "announced": [], "clock": None, "tricks": []}


def save_state(path, state):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, path)


def record(row):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, "radio.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": round(time.time(), 2), **row}, ensure_ascii=False) + "\n")


TEAM = os.environ.get("BAZAAR_TEAM", "t18")
STRONG = ("SAL", "RET", "CHA")


def _sets(x):
    return "released" if x == "released" else ",".join(sorted(x)) if isinstance(x, list) else str(x)


def observe():
    """Foto pública de lo que afecta a t18. Cinco GET sin clave."""
    lb, dl, cat = get("/api/leaderboard"), get("/api/dealers"), get("/api/catalog")
    lv, sc = get("/api/levels"), get("/api/schedule")
    dealers = {}
    for p in dl.get("personas", []):
        m = p.get("menu") or {}
        sells = {}
        for it in m.get("sells", []):
            key = it.get("pack") or f"{it.get('rarity')}@{_sets(it.get('sets'))}"
            sells[key] = {"list": it.get("list_price"), "ask": it.get("opening_ask")}
        dealers[p["id"]] = {"name": p.get("name", p["id"]), "status": p.get("status"), "level": p.get("level"),
                            "open": p.get("open_to_all"), "sells": sells,
                            "buys": sorted(f"{b.get('rarity')}@{_sets(b.get('sets'))}" for b in m.get("buys", []))}
    top = {}
    for st in cat.get("sets", []):
        for c in st.get("cards", []):
            if c.get("rarity") in ("epic", "legendary") and c.get("minted"):
                top[c["id"]] = c["minted"]
    return {"snap": lb.get("snapshot_tick"), "tick": lb.get("tick"),
            "teams": {t["team"]: {"name": t.get("name", t["team"]), "rank": t.get("rank"), "score": t.get("score"),
                                  "neg": t.get("negotiating"), "market": t.get("market")} for t in lb.get("teams", [])},
            "dealers": dealers, "released": sorted(st["id"] for st in cat.get("sets", []) if st.get("released")),
            "minted_top": top, "levels": {x["id"]: x.get("state") for x in lv.get("levels", [])},
            "now_h": sc.get("now_hours"),
            "upcoming": [[u.get("at_hours"), u.get("action"), u.get("note")] for u in sc.get("upcoming", [])]}


def _f(x):
    return f"{x:.2f}".replace(".", ",") if isinstance(x, (int, float)) else str(x)


def diff(prev, now, team=TEAM, announced=()):
    """Cambios exactos (antes → después) que afectan a t18: [(nivel, texto, dealers implicados)]."""
    out = []
    if not prev:
        return out
    a, b = prev["teams"].get(team), now["teams"].get(team)
    if a and b and prev.get("snap") != now.get("snap"):
        if a["rank"] != b["rank"]:
            out.append(("ALTA", f"Puesto de {team}: {a['rank']}.º → {b['rank']}.º "
                                f"(puntos {_f(a['score'])} → {_f(b['score'])})", ()))
        ds = (b["score"] or 0) - (a["score"] or 0)
        if abs(ds) >= 0.01:
            out.append(("MEDIA" if abs(ds) >= 0.25 else "BAJA",
                        f"Puntos de {team}: {_f(a['score'])} → {_f(b['score'])} ({'+' if ds >= 0 else ''}{_f(ds)}): "
                        f"negociación {_f(a['neg'])} → {_f(b['neg'])}, mercado {_f(a['market'])} → {_f(b['market'])}", ()))
        for t, x in now["teams"].items():
            y = prev["teams"].get(t)
            if t == team or not y:
                continue
            if y["rank"] > a["rank"] and x["rank"] < b["rank"]:
                out.append(("ALTA", f"{x['name']} nos adelanta: {x['rank']}.º con {_f(x['score'])} "
                                    f"(nosotros {_f(b['score'])})", ()))
            elif y["rank"] < a["rank"] and x["rank"] > b["rank"]:
                out.append(("MEDIA", f"Adelantamos a {x['name']} ({_f(x['score'])} frente a {_f(b['score'])})", ()))
    for d, x in now["dealers"].items():
        y = prev["dealers"].get(d)
        if y is None:
            out.append(("ALTA", f"Nuevo dealer: {x['name']} (nivel {x['level']}, {x['status']})", (d,)))
            continue
        for k, label in (("status", "estado"), ("level", "nivel"), ("open", "abierto a todos")):
            if x[k] != y[k]:
                yes = {True: "sí", False: "no", None: "—"}
                out.append(("ALTA", f"{x['name']}: {label} {yes.get(y[k], y[k])} → {yes.get(x[k], x[k])}", (d,)))
        for item in sorted(set(x["sells"]) | set(y["sells"])):
            p, q = y["sells"].get(item), x["sells"].get(item)
            if p != q:
                out.append(("MEDIA", f"{x['name']} vende {item}: "
                                     f"{'—' if p is None else 'lista ' + str(p['list']) + ', pide ' + str(p['ask'])} → "
                                     f"{'—' if q is None else 'lista ' + str(q['list']) + ', pide ' + str(q['ask'])}", (d,)))
        for item in sorted(set(x["buys"]) ^ set(y["buys"])):
            added = item in x["buys"]
            sets = item.split("@", 1)[1]
            ours = sets != "released"
            out.append(("ALTA" if ours and added else "MEDIA",
                        f"{x['name']} {'ahora compra' if added else 'ya no compra'} {item.replace('@', ' de ')}",
                        (d, f"{'+' if added else '-'}buy:{sets}")))
    for st in sorted(set(now["released"]) - set(prev["released"])):
        out.append(("ALTA", f"Barrio publicado: {st} ({ROLE.get(st, 'sin rol')})", ()))
    for ref, n in sorted(now["minted_top"].items()):
        if n != prev["minted_top"].get(ref, 0):
            out.append(("ALTA" if ref[:3] in STRONG else "MEDIA",
                        f"{ref} acuñada: {prev['minted_top'].get(ref, 0)} → {n} copias (épica/legendaria en circulación)", ()))
    for lid, st in now["levels"].items():
        if prev["levels"].get(lid) != st:
            out.append(("ALTA", f"Nivel {lid}: {prev['levels'].get(lid, 'no anunciado')} → {st}", ()))
    before = {(u[1], u[2]) for u in prev.get("upcoming", [])}
    for at, action, note in now["upcoming"]:
        key = f"{action}@{at}"
        rel = classify({"headline": note or action})
        lvl = "ALTA" if action == "persona_patch" and rel["level"] != "BAJA" else rel["level"] \
            if rel["level"] != "BAJA" else "MEDIA"
        if (action, note) not in before and action not in ("bench",):
            out.append((lvl, f"Nuevo en el calendario (h {_f(at)}): {note or action}", ()))
        if key not in announced and isinstance(at, (int, float)) and isinstance(now.get("now_h"), (int, float)) \
                and 0 <= at - now["now_h"] <= 0.2:
            out.append((lvl, f"Próximo en {_f(at - now['now_h'])} h de juego: {note or action}", ("@" + key,)))
    return out


def rarity_of(ref):
    n = int(ref[4:6]) if len(ref) >= 6 and ref[4:6].isdigit() else 0
    return "common" if n <= 5 else "uncommon" if n <= 8 else "rare" if n <= 10 else "epic" if n == 11 else "legendary"


def _refs(side):
    out = [t.split(":", 1)[1] for t in (side or {}).get("types") or [] if isinstance(t, str) and t.startswith("card:")]
    return out + [a["ref"] for a in (side or {}).get("assets") or [] if isinstance(a, dict) and a.get("ref")]


def dealer_prices(events, dealer, since_tick):
    """Precios públicos de un dealer desde un tick: sus propias ofertas en hilos y sus liquidaciones."""
    out = []
    for e in events:
        p, t = e.get("payload") or {}, e.get("tick")
        if type(t) is not int or t < since_tick:
            continue
        if e.get("type") == "thread.message" and p.get("with") == dealer and p.get("sender") == dealer:
            o = p.get("offer") or {}
            gives, wants = _refs(o.get("give")), _refs(o.get("want"))
            if len(gives) + len(wants) != 1:
                continue
            buys = bool(wants)
            price = (o.get("give") if buys else o.get("want") or {}).get("cash")
            ref, kind = (wants or gives)[0], "oferta"
        elif e.get("type") == "settlement" and p.get("persona") == dealer:
            items = p.get("items") or []
            if len(items) != 1:
                continue
            ref, buys, price, kind = items[0].get("ref"), items[0].get("to") == dealer, p.get("price"), "trato"
        else:
            continue
        if ref and type(price) is int and price > 0:
            out.append({"id": e.get("id"), "tick": t, "ref": ref, "set": ref[:3], "rarity": rarity_of(ref),
                        "side": "compra" if buys else "vende", "price": price, "kind": kind})
    return out


def verdict(obs, sets, side, rarity=None):
    """Compara los precios del dealer en los barrios de la noticia con los de la misma rareza en otros barrios."""
    rows = [o for o in obs if o["side"] == side and (rarity is None or o["rarity"] == rarity)]
    target = [o["price"] for o in rows if o["set"] in sets]
    control = [o["price"] for o in rows if o["set"] not in sets]
    res = {"side": side, "rarity": rarity, "n_target": len(target), "n_control": len(control),
           "target": statistics.median(target) if target else None,
           "control": statistics.median(control) if control else None, "verdict": "sin datos"}
    if target and control:
        prem = res["target"] / res["control"] - 1
        res["premium"] = round(prem, 3)
        better = prem >= 0.10 if side == "compra" else prem <= -0.10
        res["verdict"] = ("confirmada" if better else "sin señal") if len(target) >= 2 and len(control) >= 2 \
            else ("indicio" if better else "sin señal")
    elif target:
        res["verdict"] = "solo barrio citado"
    return res


def hhmmss(ts=None):
    return time.strftime("%H:%M:%S", time.localtime(ts if ts is not None else time.time()))


def when(clock=None, ts=None):
    """«11:52:07 · tick 560 · h 5,12»: hora local, tick y hora de juego del momento del aviso."""
    parts = [hhmmss(ts)]
    if clock and clock.get("tick") is not None:
        parts.append(f"tick {clock['tick']}")
    if clock and isinstance(clock.get("t_hours"), (int, float)):
        parts.append(f"h {_f(clock['t_hours'])}")
    return " · ".join(parts)


def aired(item, clock=None, now=None):
    """Cuándo se emitió una noticia (tick, hora de juego, hora local estimada) y con qué retraso la vemos."""
    now = time.time() if now is None else now
    t, h = item.get("tick"), item.get("at_hours")
    txt = f"emitida tick {t}" + (f" (h {_f(h)})" if isinstance(h, (int, float)) else "")
    if clock and type(t) is int and type(clock.get("tick")) is int and clock.get("tick_seconds"):
        lag = max(0, clock["tick"] - t)
        secs = lag * float(clock["tick_seconds"]) + max(0.0, float(clock["tick_seconds"]) -
                                                       float(clock.get("next_tick_in") or 0))
        txt += f" ≈ {hhmmss(now - secs)} · detectada {hhmmss(now)} (+{lag} ticks, ~{secs / 60:.0f} min)"
    else:
        txt += f" · detectada {hhmmss(now)}"
    return txt


def show(item, c, clock=None):
    mark = {"ALTA": "‼️ ", "MEDIA": "⚠️ ", "BAJA": "   "}[c["level"]]
    lines = [f"{mark}[{c['level']}] tick {item.get('tick')} · {item.get('source_name')}: {item.get('headline')}",
             f"      🕒 {aired(item, clock)}",
             f"      {item.get('body', '')}", "      Por qué: " + "; ".join(c["why"])]
    lines += [f"      → {t}" for t in c["todo"]]
    return "\n".join(lines)


GRAVE, INFO, QUIET = "grave", "info", "silencio"
_RE = {
    "rank": re.compile(r"Puesto de (\w+): (\d+)\.º → (\d+)\.º \(puntos ([\d,]+) → ([\d,]+)\)"),
    "pts": re.compile(r"Puntos de \w+: ([\d,]+) → ([\d,]+) \(([+-]?[\d,]+)\)"),
    "active": re.compile(r"^(?:Nivel )?(.+?): (?:estado )?announced → active"),
    "open": re.compile(r"^(.+?): abierto a todos no → sí"),
    "announced": re.compile(r"^Nivel (\w+): no anunciado → announced"),
    "minted": re.compile(r"^(\w{3})-(\d+) acuñada: (\d+) → (\d+)"),
    "soon": re.compile(r"^Próximo en ([\d,]+) h de juego: (.+)"),
    "cal": re.compile(r"^Nuevo en el calendario \(h ([\d,]+)\): (.+)"),
    "swap": re.compile(r"da ([A-Z]{3}-\d+) en vez de ([A-Z]{3}-\d+)"),
}


def _num(x):
    return float(x.replace(",", "."))


def friendly(level, text):
    """(gravedad, frase corta y legible) para un cambio de diff(). Solo es GRAVE lo que exige actuar ya."""
    m = _RE["rank"].search(text)
    if m:
        a, b = int(m.group(2)), int(m.group(3))
        up = b < a
        return (GRAVE if b - a >= 2 else INFO,
                f"{'📈 Subimos' if up else '📉 Bajamos'} al {b}.º ({m.group(5)} puntos)")
    m = _RE["pts"].search(text)
    if m:
        d = _num(m.group(3))
        if abs(d) < 1.0:
            return QUIET, text
        return (GRAVE if d <= -1.0 else INFO), f"{'📈' if d > 0 else '📉'} {m.group(3)} puntos (ahora {m.group(2)})"
    if "nos adelanta" in text or text.startswith("Adelantamos"):
        return QUIET, text
    m = _RE["active"].search(text)
    if m and not text.startswith("Nivel"):
        return INFO, f"🆕 {m.group(1)} ya está activo"
    if m:
        return QUIET, text
    m = _RE["open"].search(text)
    if m:
        return INFO, f"🔓 {m.group(1)} ya está abierto a todos"
    m = _RE["announced"].search(text)
    if m:
        return INFO, f"📢 Anunciado un nivel nuevo: {m.group(1)}"
    if text.startswith("Nuevo dealer"):
        return INFO, "📢 " + text.split(" (")[0]
    if text.startswith("Barrio publicado"):
        return INFO, "🗺️ " + text
    m = _RE["minted"].search(text)
    if m:
        return (INFO if m.group(1) in STRONG else QUIET), f"✨ Primera {m.group(1)}-{m.group(2)} en circulación"
    m = _RE["soon"].search(text)
    if m:
        mins = round(_num(m.group(1)) * 60)
        return INFO, f"⏰ En ~{mins} min: {m.group(2)}"
    m = _RE["cal"].search(text)
    if m:
        return (INFO if level == "ALTA" else QUIET), f"📅 Programado (h {m.group(1)}): {m.group(2)}"
    if "confirma la noticia" in text:
        return INFO, "✅ " + text.replace(" — confirma", " · confirma")
    return QUIET, text


def collect(bucket, severity, line):
    if severity != QUIET:
        bucket.append((severity, line))


def deliver(bucket, clock, out=print, do_notify=True):
    """Imprime lo legible y avisa: cada GRAVE por separado (sonido fuerte y alerta); lo INFO agrupado y suave."""
    if not bucket:
        return
    stamp = when(clock)
    for sev, line in bucket:
        out(f"{'🚨 [GRAVE]' if sev == GRAVE else '🔔 [INFO]'} {stamp} · {line}")
    if not do_notify:
        return
    for sev, line in bucket:
        if sev == GRAVE:
            notify("🚨 t18 · importante", f"{line}\n🕒 {stamp}", level="ALTA")
    infos = [line for sev, line in bucket if sev == INFO]
    if infos:
        title = "🔔 t18" if len(infos) == 1 else f"🔔 t18 · {len(infos)} novedades"
        notify(title, "\n".join(infos[:4]) + f"\n🕒 {stamp}", level="MEDIA")


_hit = [None]


def attribute(tags, watches):
    """«confirma» solo si el dealer empieza a comprar justo los barrios de una noticia de demanda; «fin» si los
    deja de comprar. Cualquier otro cambio no se atribuye a ninguna noticia (un rumor sin barrios nunca se
    confirma por un cambio de menú)."""
    dealers = {t for t in tags if not t.startswith(("+", "-", "@"))}
    for t in tags:
        if t[:5] not in ("+buy:", "-buy:"):
            continue
        sets = set(t[5:].split(","))
        for w in sorted(watches, key=lambda w: -(w.get("news") or 0)):
            if dealers & set(w.get("dealers", ())) and sets & set(w.get("sets") or ()) and w.get("side") == "compra":
                _hit[0] = w
                return "confirma" if t[0] == "+" else "fin"
    return None


def step(state, names, *, min_level="MEDIA", do_notify=True, first=False, have=None, out=print, clock=None):
    """Una lectura: noticias nuevas, comprobación de menús y estado actualizado. Devuelve las noticias nuevas."""
    news = get("/api/news").get("news", [])
    fresh = sorted((n for n in news if n.get("id") not in state["seen"]), key=lambda n: n.get("id", 0))
    now = time.time()
    bucket = []
    for n in fresh:
        c = classify(n, names, have)
        state["seen"].append(n.get("id"))
        if type(n.get("tick")) is int and n["tick"] not in state["ticks"]:
            state["ticks"] = sorted(state["ticks"] + [n["tick"]])[-50:]
        record({"event": "news", "id": n.get("id"), "tick": n.get("tick"), "source": n.get("source"),
                "headline": n.get("headline"), "body": n.get("body"), **c})
        out(show(n, c, clock))
        if c["dealers"]:
            state["watch"][str(n.get("id"))] = {
                "until": now + 3 * 3600, "start": now, "news": n.get("id"), "headline": n.get("headline"), "tick": n.get("tick") or 0,
                "dealers": c["dealers"], "sets": c["sets"], "side": c["side"], "rarity": "rare" if c["rare"] else None,
                "obs": [], "verdict": None}
        if not first and c["level"] != "BAJA":   # ambiente (BAJA): solo consola
            hint = "rumor, no actuar" if c["rumour"] else (c["todo"][0] if c["todo"] else c["why"][0])
            collect(bucket, INFO, f"📻 «{n.get('headline')}» — {hint[:110]}")
    for key, w in list(state["watch"].items()):
        if now > w.get("until", 0) or "dealers" not in w:
            state["watch"].pop(key)
    live = [w for w in state["watch"].values() if w["sets"] and w["side"]
            and now - w.get("start", w["until"] - 3600) <= 3600]
    try:
        events = get("/api/feed?limit=500").get("events", [])
    except RateLimited:
        raise
    except Exception as e:  # noqa: BLE001
        events = []
        record({"event": "feed_error", "error": type(e).__name__})
    if events:
        rows, _ = picaros.absorb(events, os.path.join(LOG_DIR, "picaros.jsonl"))
        seen = set(state.setdefault("tricks", []))
        for t in picaros.tricks(events, picaros.topics_of(rows)):
            key = f"{t['message']}:{t['level']}"
            if key in seen:
                continue
            state["tricks"].append(key)
            ours = t["team"] == TEAM
            level = "ALTA" if t["level"] == "firme" or ours else "MEDIA"
            msg = (f"Truco {t['level'].upper()} de Los Pícaros{' CONTRA NOSOTROS' if ours else ''}: {t['motivo']} "
                   f"(mensaje {t['message']}, hilo {t['thread']}, {t['team']}, tick {t['tick']})")
            record({"event": "picaros_trick", **t})
            out(f"{'‼️' if level == 'ALTA' else '⚠️'} [{level}] [{when(clock)}] {msg}")
            if not first and ours and t["level"] == "firme":   # los ajenos: solo registro
                sw = _RE["swap"].search(t["motivo"])
                collect(bucket, INFO, (f"🃏 Los Pícaros intentaron colarnos {sw.group(1)} (pedimos {sw.group(2)}); "
                                       "el Gate no lo acepta") if sw else f"🃏 Truco de Los Pícaros: {t['motivo']}")
        state["tricks"] = state["tricks"][-500:]
    if live:
        for w in live:
            seen = {o["id"] for o in w["obs"]}
            for d in w["dealers"]:
                w["obs"] += [o for o in dealer_prices(events, d, w["tick"]) if o["id"] not in seen]
            v = verdict(w["obs"], set(w["sets"]), w["side"], w["rarity"])
            key = (v["verdict"], v["n_target"], v["n_control"])
            if w.get("verdict") != list(key):
                w["verdict"] = list(key)
                fmt = lambda x: "—" if x is None else _f(x)  # noqa: E731
                msg = (f"Evidencia «{w['headline']}»: {'/'.join(w['dealers'])} {v['side']} "
                       f"{v['rarity'] or 'cartas'} de {'/'.join(w['sets'])} a mediana {fmt(v['target'])} "
                       f"(n={v['n_target']}) frente a {fmt(v['control'])} en otros barrios (n={v['n_control']}) → "
                       f"{v['verdict'].upper()}" + (f" ({v['premium']:+.0%})" if "premium" in v else ""))
                record({"event": "evidence", "news": w["news"], **v})
                out(("‼️ " if v["verdict"] == "confirmada" else "   ") + f"[{when(clock)}] " + msg)
                if v["verdict"] == "confirmada":
                    collect(bucket, INFO, f"✅ Confirmada: «{w['headline']}» ({v['premium']:+.0%} frente a otros barrios)")
    try:
        obs = observe()
    except Exception as e:  # noqa: BLE001  la foto es un extra: las noticias ya se han procesado
        record({"event": "observe_error", "error": type(e).__name__})
        deliver(bucket, clock, out, do_notify)
        return fresh
    changes = []
    for level, text, tags in diff(state.get("obs"), obs, announced=state.setdefault("announced", [])):
        link = attribute(tags, state["watch"].values())
        if link == "confirma":
            level, text = "ALTA", text + f" — confirma la noticia «{_hit[0]['headline']}»"
        elif link == "fin":
            level, text = "MEDIA", text + f" — fin de la ventana de la noticia «{_hit[0]['headline']}»"
        state["announced"] += [t[1:] for t in tags if t.startswith("@")]
        changes.append((level, text))
    state["obs"] = obs
    if changes:
        changes.sort(key=lambda c: -LEVELS.index(c[0]))
        record({"event": "changes", "tick": obs.get("tick"), "changes": [list(c) for c in changes]})
        out(f"   Detalle de cambios · {when(clock or {'tick': obs.get('tick')})}:")
        for level, text in changes:
            out(f"      [{level}] {text}")
        for level, text in changes:
            collect(bucket, *friendly(level, text))
    deliver(bucket, clock or {"tick": (obs or {}).get("tick")}, out, do_notify)
    return fresh


def clock_change(prev, clock):
    """Aviso cuando el reloj se pausa o se reanuda (los organizadores lo hacen sin avisar): mueve todos los horarios."""
    if not prev or not clock or bool(prev.get("paused")) == bool(clock.get("paused")):
        return None
    if clock.get("paused"):
        return ("ALTA", f"Juego en PAUSA en el tick {clock.get('tick')} (h {_f(clock.get('t_hours'))}): "
                        "nada se liquida y el calendario se retrasa")
    return ("ALTA", f"Juego REANUDADO: tick {prev.get('tick')} → {clock.get('tick')} (h {_f(clock.get('t_hours'))})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--watch", action="store_true", help="vigilar con ritmo adaptativo")
    ap.add_argument("--min-level", choices=LEVELS, default="MEDIA", help="nivel mínimo para notificar")
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--no-sound", action="store_true", help="sin sonido (la notificación sigue)")
    ap.add_argument("--no-dialog", action="store_true", help="sin alerta en pantalla para ALTA")
    ap.add_argument("--have", default=None, help="refs que tenemos, separadas por comas (afina la relevancia)")
    ap.add_argument("--state", default=os.path.join(LOG_DIR, "radio_state.json"))
    a = ap.parse_args()
    state = load_state(a.state)
    LOUD.update(sound=not a.no_sound, dialog=not a.no_dialog)
    have = None if a.have is None else {r.strip().upper() for r in a.have.split(",") if r.strip()}
    try:
        names = card_names(get("/api/catalog"))
    except Exception:  # noqa: BLE001  sin catálogo solo se reconocen barrios y refs
        names = {}
    first = not state["seen"]
    if not a.watch:
        try:
            clock = get("/api/clock")
        except Exception:  # noqa: BLE001
            clock = None
        for n in sorted(get("/api/news").get("news", []), key=lambda n: n.get("id", 0)):
            print(show(n, classify(n, names, have), clock))
        return
    print(f"Radio Rastro: vigilando {URL}/api/news (avisos desde {a.min_level}; Ctrl+C para parar)", flush=True)
    burst, limited = 0, 0
    while True:
        tick_s, doors = 30.0, "open"
        try:
            clock = get("/api/clock")
            tick_s, doors = clock.get("tick_seconds") or 30.0, clock.get("doors", "open")
            change = clock_change(state.get("clock"), clock)
            state["clock"] = {k: clock.get(k) for k in ("tick", "t_hours", "paused")}
            if change:
                record({"event": "clock", "level": change[0], "text": change[1]})
                pause = "PAUSA" in change[1]
                deliver([(GRAVE, ("⏸️ Juego en pausa: nada se liquida y los horarios se retrasan" if pause
                                  else "▶️ El juego se ha reanudado"))], clock,
                        lambda x: print(x, flush=True), not a.no_notify)
            fresh = step(state, names, min_level=a.min_level, do_notify=not a.no_notify, first=first, clock=clock,
                         have=have)
            first, limited = False, 0
            burst = 10 if fresh else max(0, burst - 1)
            save_state(a.state, state)
            wait = interval(state["ticks"], tick_s, burst > 0)
            if doors != "open":
                wait = 600.0
            elif clock.get("paused"):
                wait = 60.0   # en pausa: leer cada minuto para avisar en cuanto se reanude
            record({"event": "poll", "tick": clock.get("tick"), "new": len(fresh), "next_s": round(wait, 1),
                    "doors": doors})
            print(f"   · {when(clock)}: {len(fresh)} nuevas; próxima lectura a las {hhmmss(time.time() + wait)} "
                  f"({wait:.0f} s)", flush=True)
        except RateLimited as e:   # el servidor pide calma: respetarlo y alargar si se repite
            limited = min(4, limited + 1)
            wait = min(600.0, max(e.wait, 60.0) * 2 ** (limited - 1))
            record({"event": "rate_limited", "wait": wait})
            print(f"   · {hhmmss()} · 429 del servidor: espero {wait:.0f} s", flush=True)
            time.sleep(wait)
            continue
        except Exception as e:  # noqa: BLE001  la red falla a veces: reintentar sin caerse
            wait = 60.0
            record({"event": "error", "error": type(e).__name__, "detail": str(e)[:200]})
            print(f"   · error de lectura ({type(e).__name__}); reintento en 60 s", flush=True)
        time.sleep(wait)


if __name__ == "__main__":
    main()
