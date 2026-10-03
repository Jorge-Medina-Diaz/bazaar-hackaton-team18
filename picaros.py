"""Los Pícaros (nivel 4): trucos detectables a máquina y perfil de cómo negocian. Solo lectura del feed público.

Uso:
  python3 picaros.py            # trucos y perfil con el feed actual + lo acumulado en logs/picaros.jsonl
  python3 picaros.py --json     # lo mismo en JSON

`radio.py --watch` lo llama en cada lectura: acumula cada mensaje suyo en logs/picaros.jsonl (el feed solo guarda
los últimos 500 eventos) y avisa de los trucos. Un truco «firme» es una contradicción ESTRUCTURAL con el tema del
hilo (carta distinta, pedir algo más que la carta del tema, dirección contraria, no dar nada); «posible» es un
número del texto que no coincide con el precio estructurado. Solo los firmes sirven como evidencia para
`POST /api/flags` (lo decide y lo hace el operador). El texto ajeno se lee, nunca se ejecuta ni decide cifras.
"""
import json
import os
import re
import statistics
import sys
import unicodedata

DEALER = "picaros"
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
         "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
         "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
         "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
         "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "veinte": 20,
         "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80,
         "noventa": 90, "cien": 100}


def _norm(t):
    return "".join(c for c in unicodedata.normalize("NFKD", str(t or "").lower()) if not unicodedata.combining(c))


def _refs(side):
    side = side or {}
    return ([t.split(":", 1)[1] for t in side.get("types") or [] if isinstance(t, str) and t.startswith("card:")]
            + [a.get("ref") for a in side.get("assets") or [] if isinstance(a, dict) and a.get("ref")])


def _asset_ids(side):
    return sorted(a.get("id") for a in (side or {}).get("assets") or [] if isinstance(a, dict) and a.get("id"))


def _packs(side):
    return [t for t in (side or {}).get("types") or [] if isinstance(t, str) and t.startswith("pack:")]


def text_prices(text):
    """Precios que el texto anuncia: cifras junto a P/pesos/primas o tras «for», y números en letra (EN/ES)."""
    t = _norm(text)
    out = {int(m) for m in re.findall(r"\b(\d{1,4})\s*(?:p\b|primas|pesos|perlas|coins)", t)}
    out |= {int(m) for m in re.findall(r"\b(?:for|por|a)\s+(\d{1,4})\b", t)}
    toks = re.findall(r"[a-z]+", t)
    i = 0
    while i < len(toks):                      # números en letra: «ciento ochenta y siete», «one hundred and five»
        if toks[i] not in WORDS and toks[i] not in ("ciento", "doscientos", "trescientos"):
            i += 1
            continue
        total, cur, used = 0, 0, False
        while i < len(toks) and (toks[i] in WORDS or toks[i] in ("ciento", "doscientos", "trescientos", "y", "and")):
            w = toks[i]
            if w in ("y", "and"):
                i += 1
                continue
            v = {"ciento": 100, "doscientos": 200, "trescientos": 300}.get(w, WORDS.get(w))
            if w == "hundred":
                cur = max(cur, 1) * 100
            else:
                cur += v
            used = True
            i += 1
        total += cur
        if used and total >= 4:
            out.add(total)
    return out


def tricks(events, topics):
    """[{"level": "firme"|"posible", "motivo", "message", "thread", "team", "tick"}] de mensajes de Los Pícaros.

    `topics`: {thread: {"team", "topic"}} (los hilos abiertos con ellos; se pasa acumulado entre lecturas)."""
    out, theirs = [], {}
    for e in events:
        p = e.get("payload") or {}
        if e.get("type") == "thread.message" and p.get("with") == DEALER and p.get("sender") != DEALER:
            o = p.get("offer") or {}
            c = (o.get("want") or {}).get("cash") or (o.get("give") or {}).get("cash")
            if isinstance(c, int):
                theirs.setdefault(str(p.get("thread")), set()).add(c)   # precios del equipo: ellos los repiten
            continue
        if e.get("type") != "thread.message" or p.get("with") != DEALER or p.get("sender") != DEALER:
            continue
        o = p.get("offer") or {}
        if not o:
            continue
        info = topics.get(str(p.get("thread"))) or {}
        topic = info.get("topic") or {}
        give, want = o.get("give") or {}, o.get("want") or {}
        why = []
        if "buy" in topic:                                 # el equipo compra: ellos deben dar SOLO esa carta por caja
            item = topic["buy"] or {}
            ref, pack = item.get("card"), item.get("pack")
            given = _refs(give) + _packs(give)
            if not given:
                why.append("no da ninguna carta en un hilo de compra")
            elif ref and given != [ref]:
                why.append(f"da {', '.join(given)} en vez de {ref}")
            elif pack and _packs(give) != [f"pack:{pack}"]:
                why.append(f"da {', '.join(given)} en vez del sobre {pack}")
            if _refs(want) or _asset_ids(want) or _packs(want):
                why.append("además pide cartas nuestras")
            if not isinstance(want.get("cash"), int) or want.get("cash", 0) <= 0:
                why.append("no pide caja: dirección contraria al tema")
        elif "sell" in topic:                              # el equipo vende: ellos deben pedir SOLO esas cartas
            ids = sorted((topic["sell"] or {}).get("assets") or [])
            got = _asset_ids(want)
            if got and ids and got != ids:
                why.append(f"pide las cartas {got} en vez de {ids}")
            if _refs(give) or _asset_ids(give) or _packs(give):
                why.append("da cartas en un hilo de venta: dirección contraria al tema")
            if not (isinstance(give.get("cash"), int) and give.get("cash", 0) > 0):
                why.append("no paga nada")
        base = {"message": p.get("message"), "thread": p.get("thread"), "team": p.get("team") or info.get("team"),
                "tick": e.get("tick")}
        if why and topic:
            out.append({"level": "firme", "motivo": "; ".join(why), **base})
        price = want.get("cash") if want.get("cash") else give.get("cash")
        said = text_prices(p.get("text")) - theirs.get(str(p.get("thread")), set())
        if isinstance(price, int) and price > 0 and said and price not in said and len(said) == 1:
            out.append({"level": "posible", "motivo": f"el texto dice {next(iter(said))} y la oferta {price}",
                        **base})
    return out


def observations(events):
    """Cada mensaje con oferta de un hilo con Los Pícaros y cada liquidación suya, en forma compacta."""
    rows = []
    for e in events:
        p = e.get("payload") or {}
        if e.get("type") == "thread.opened" and p.get("with") == DEALER:
            rows.append({"id": e.get("id"), "tick": e.get("tick"), "kind": "open", "thread": p.get("thread"),
                         "team": p.get("team"), "topic": p.get("topic")})
        elif e.get("type") == "thread.message" and p.get("with") == DEALER and p.get("offer"):
            o = p["offer"]
            g, w = o.get("give") or {}, o.get("want") or {}
            card_given = bool(_refs(g))                    # quien escribe da la carta: su precio es lo que pide
            price = (w if card_given else g).get("cash")
            from_them = p.get("sender") == DEALER
            they_sell = card_given if from_them else bool(_refs(w))
            they_buy = (not card_given) if from_them else card_given
            refs = _refs(g) + _refs(w)
            rows.append({"id": e.get("id"), "tick": e.get("tick"), "kind": "msg", "thread": p.get("thread"),
                         "team": p.get("team"), "who": "picaros" if p.get("sender") == DEALER else "team",
                         "ref": refs[0] if refs else None, "price": price, "final": bool(o.get("final")),
                         "side": "venden" if they_sell else "compran" if they_buy and refs else None})
        elif e.get("type") == "settlement" and p.get("persona") == DEALER:
            items = p.get("items") or []
            rows.append({"id": e.get("id"), "tick": e.get("tick"), "kind": "deal", "price": p.get("price"),
                         "ref": items[0].get("ref") if items else None,
                         "side": "venden" if items and items[0].get("frm") == DEALER else "compran",
                         "team": next((x for x in p.get("parties") or [] if x != DEALER), None)})
        elif e.get("type") == "thread.closed" and p.get("with") == DEALER:
            rows.append({"id": e.get("id"), "tick": e.get("tick"), "kind": "closed", "thread": p.get("thread"),
                         "reason": p.get("reason") or p.get("closed_reason")})
    return rows


def rarity(ref):
    n = int(ref[4:6]) if ref and len(ref) >= 6 and ref[4:6].isdigit() else 0
    return "common" if n <= 5 else "uncommon" if n <= 8 else "rare" if n <= 10 else "epic" if n == 11 else "legendary"


def profile(rows):
    """Cómo negocian, por lado y rareza: apertura, pasos, mensajes hasta `final`, cierre y si siguen tras `final`."""
    threads, deals = {}, []
    for r in rows:
        if r["kind"] == "deal":
            deals.append(r)
        elif r.get("thread") is not None:
            t = threads.setdefault(r["thread"], {"msgs": [], "closed": None})
            if r["kind"] == "msg":
                t["msgs"].append(r)
            elif r["kind"] == "closed":
                t["closed"] = r.get("reason")
    out = {}
    for t in threads.values():
        mine = [m for m in t["msgs"] if m["who"] == "picaros" and m["side"] and isinstance(m["price"], int)]
        if not mine:
            continue
        key = f"{mine[0]['side']} {rarity(mine[0]['ref'])}"
        d = out.setdefault(key, {"hilos": 0, "apertura": [], "pasos": [], "mensajes_hasta_final": [],
                                 "ultimo": [], "siguen_tras_final": 0, "cierres": []})
        d["hilos"] += 1
        prices = [m["price"] for m in mine]
        d["apertura"].append(prices[0])
        d["pasos"] += [abs(b - a) for a, b in zip(prices, prices[1:])]
        d["ultimo"].append(prices[-1])
        finals = [i for i, m in enumerate(mine) if m["final"]]
        if finals:
            d["mensajes_hasta_final"].append(finals[0] + 1)
            d["siguen_tras_final"] += int(len(mine) > finals[0] + 1)
        if t["closed"]:
            d["cierres"].append(t["closed"])
    for key, d in out.items():
        for k in ("apertura", "pasos", "ultimo", "mensajes_hasta_final"):
            v = d[k]
            d[k] = {"n": len(v), "mediana": statistics.median(v) if v else None,
                    "min": min(v) if v else None, "max": max(v) if v else None}
    sold = {}
    for r in deals:
        sold.setdefault(f"{r['side']} {rarity(r['ref'])}", []).append(r["price"])
    return {"por_tipo": out, "tratos": {k: {"n": len(v), "mediana": statistics.median(v), "min": min(v),
                                            "max": max(v)} for k, v in sold.items()}}


def load_rows(path):
    rows = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.endswith("\n"):
                    try:
                        r = json.loads(line)
                        rows[r["id"]] = r
                    except (ValueError, KeyError, TypeError):
                        pass
    except OSError:
        pass
    return rows


def absorb(events, path):
    """Añade al histórico las observaciones nuevas (deduplicadas por id). Devuelve (todas, nuevas)."""
    known = load_rows(path)
    fresh = [r for r in observations(events) if r["id"] not in known]
    if fresh:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in fresh)
        for r in fresh:
            known[r["id"]] = r
    return sorted(known.values(), key=lambda r: r["id"]), fresh


def topics_of(rows):
    return {str(r["thread"]): {"team": r.get("team"), "topic": r.get("topic")} for r in rows if r["kind"] == "open"}


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import radio
    path = os.path.join(radio.LOG_DIR, "picaros.jsonl")
    events = radio.get("/api/feed?limit=500").get("events", [])
    rows, _ = absorb(events, path)
    found = tricks(events, topics_of(rows))
    prof = profile(rows)
    if "--json" in sys.argv:
        print(json.dumps({"trucos": found, "perfil": prof}, ensure_ascii=False, indent=1))
        return
    print(f"Los Pícaros · {len(rows)} observaciones acumuladas")
    for k, d in prof["por_tipo"].items():
        print(f"  {k}: {d['hilos']} hilos · abren {d['apertura']['mediana']} (min {d['apertura']['min']}, "
              f"max {d['apertura']['max']}) · paso mediano {d['pasos']['mediana']} · `final` al mensaje "
              f"{d['mensajes_hasta_final']['mediana']} · último {d['ultimo']['mediana']} · siguen tras `final`: "
              f"{d['siguen_tras_final']}")
    for k, d in prof["tratos"].items():
        print(f"  tratos {k}: {d['n']} · mediana {d['mediana']} (min {d['min']}, max {d['max']})")
    for t in found:
        print(f"  [{t['level'].upper()}] mensaje {t['message']} · hilo {t['thread']} ({t['team']}) · tick {t['tick']}: "
              f"{t['motivo']}")
    if not found:
        print("  sin trucos detectados en la ventana actual")


if __name__ == "__main__":
    main()
