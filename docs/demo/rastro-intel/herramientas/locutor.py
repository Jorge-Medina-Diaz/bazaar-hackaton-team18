"""La locutora de Radio Rastro: convierte las alertas del tablero en boletines hablados con contexto.

- Selecciona: solo lo que importa a t18 (nuestro puesto, Pícaros contra nosotros, pausa o reanudación, épicas nuevas
  con quién y a cuánto, eventos a punto de empezar). El resto se queda en la página.
- Agrupa: todo lo nuevo de una vuelta del tablero (20 s) sale en un solo boletín, ordenado por importancia.
- Habla claro: equipos («el equipo doce»), cartas con barrio y nombre («Retiro once, el Palacio de Cristal»),
  puntos con coma decimal y pausas cortas entre noticias.
- Guarda: un .m4a por boletín en tablero_web/audios/ y su texto en tablero_web/audios/indice.jsonl.
"""
import datetime as dt, json, os, re, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed_all.jsonl")
BARRIO = {"LAV": "Lavapiés", "SAL": "Salamanca", "RET": "Retiro", "MAL": "Malasaña", "LAT": "La Latina", "CHA": "Chamberí"}
DEALER = {"picaros": "Los Pícaros", "pilar": "Doña Pilar", "chato": "El Chato", "abuela": "la Abuela Carmen", "banco": "Don Ernesto, el Banco"}
PAUSA = " [[slnc 450]] "
_names = {}


def names():
    if not _names:
        try:
            with urllib.request.urlopen("https://bazaar.causaprima.ai/api/catalog", timeout=10) as r:
                for s in json.load(r)["sets"]:
                    for c in s["cards"]: _names[c["id"]] = c["name"]
        except Exception:
            pass
    return _names


def carta(ref, con_nombre=True):
    m = re.match(r"([A-Z]{3})-(\d+)", ref or "")
    if not m: return ref or ""
    b = BARRIO.get(m.group(1), m.group(1)); n = int(m.group(2))
    nm = names().get(ref) if con_nombre else None
    return f"{b} {n}" + (f", {nm}," if nm else "")


def equipo(t):
    if t == "t18": return "nosotros"
    m = re.match(r"t(\d+)", t or "")
    return f"el equipo {int(m.group(1))}" if m else (DEALER.get(t, t) or "")


ORD = {1: "primeros", 2: "segundos", 3: "terceros", 4: "cuartos", 5: "quintos", 6: "sextos", 7: "séptimos", 8: "octavos", 9: "novenos", 10: "décimos"}
def puesto(n):
    return ORD.get(int(n), f"en el puesto {n}")

def de(t):
    e = equipo(t)
    return "del " + e[3:] if e.startswith("el ") else "de " + e

def num(x):
    return f"{x:.2f}".replace(".", ",") if isinstance(x, float) else str(x)


def quien_compro(ref, ventana=20000):
    """Busca en las últimas líneas del feed archivado el último trato con esa carta: (comprador, vendedor, precio)."""
    try:
        with open(FEED, "rb") as f:
            f.seek(0, 2); size = f.tell(); f.seek(max(0, size - 12_000_000))
            lines = f.read().decode("utf-8", "ignore").splitlines()[-ventana:]
    except OSError:
        return None
    for line in reversed(lines):
        if ref not in line or '"settlement"' not in line: continue
        try:
            p = json.loads(line)["payload"]
        except Exception:
            continue
        for i in p.get("items", []):
            if i.get("ref") == ref:
                return i.get("to"), i.get("frm"), p.get("price")
    return None


def frase(a, lb_rows):
    """Una noticia hablada para una alerta, o None si no merece voz. Devuelve (prioridad, texto)."""
    g, t = a["grupo"], a["titulo"]
    if g == "reloj":
        return 0, ("El juego está en pausa. No se liquida nada y el calendario se retrasa." if "PAUSA" in t
                   else "Arranca el juego. Volvemos a negociar.")
    if g == "picaros_nos":
        if a["nivel"] == "CRITICA":
            return 0, f"Atención. Los Pícaros nos han colado una carta cambiada. {a['que']} Hay que denunciarlo."
        m = re.search(r"(\d+) intentos? en el hilo (\d+)", a["que"])
        n = m.group(1) if m else "un"
        extra = " y cerró el trato limpio" if a.get("estado") == "bien" else ""
        return 2, f"Los Pícaros han intentado engañarnos, {n} {'veces' if n not in ('1', 'un') else 'vez'}. Nuestro agente lo ha pillado{extra}. Sin pérdidas."
    if g == "puesto":
        m = re.search(r"(Bajamos|Subimos) al (\d+)", t)
        if m:
            us = next((r for r in lb_rows if r["team"] == "t18"), None)
            pts = f" con {num(us['score'])} puntos" if us else ""
            if m.group(1) == "Subimos":
                return 1, f"Buenas noticias: ya vamos {puesto(m.group(2))}{pts}."
            return 1, f"Bajamos: ahora vamos {puesto(m.group(2))}{pts}. Solo los tratos nos devuelven arriba."
        m = re.search(r"Team (\d+) nos adelanta", t)
        if m: return 1, f"El equipo {m.group(1)} nos adelanta."
        m = re.search(r"Adelantamos a Team (\d+)", t)
        if m: return 2, f"Adelantamos al equipo {m.group(1)}."
        return None
    if g == "epica":
        m = re.search(r"([A-Z]{3}-\d+) \(copia (\d+)\)", t)
        if not m: return None
        ref, n = m.groups()
        q = quien_compro(ref)
        if q and q[0]:
            comp, vend, precio = q
            sujeto = "Nos llevamos" if comp == "t18" else f"{equipo(comp)[0].upper() + equipo(comp)[1:]} se lleva"
            return (1 if comp == "t18" else 3), f"{sujeto} la copia {n} de {carta(ref)} comprada a {equipo(vend)} por {precio} primas."
        return 3, f"Sale la copia {n} de {carta(ref)}."
    if g == "pronto":
        m = re.search(r"En ~(\d+) min: (.+)", t)
        if m: return 2, f"En unos {m.group(1)} minutos: {m.group(2)}."
        return None
    return None


def boletin(nuevas, lb_rows, clock):
    """Texto completo del boletín o None. Abre con la hora y nuestro puesto, ordena por prioridad, máximo 5 noticias."""
    # del puesto solo cuenta el estado final: la última noticia de ese grupo
    last_p = max((k for k, a in enumerate(nuevas) if a["grupo"] == "puesto" and re.search(r"(Bajamos|Subimos) al", a["titulo"])), default=None)
    if last_p is not None:
        nuevas = [a for k, a in enumerate(nuevas) if a["grupo"] != "puesto" or k == last_p]
    items = [x for x in (frase(a, lb_rows) for a in nuevas) if x]
    if not items: return None
    items.sort(key=lambda x: x[0])
    seen, cuerpo = set(), []
    for _, s in items:
        if s in seen: continue
        seen.add(s); cuerpo.append(s)
    cuerpo = cuerpo[:5]
    us = next((r for r in lb_rows if r["team"] == "t18"), None)
    cab = f"Radio Rastro, {dt.datetime.now():%H:%M}."
    pie = ""
    if us and not any(a["grupo"] == "puesto" for a in nuevas):
        pie = PAUSA + f"Seguimos {puesto(us['rank'])} con {num(us['score'])} puntos."
    return re.sub(r",\s*\.", ".", cab + PAUSA + PAUSA.join(cuerpo) + pie)


def resumen(lb_rows, proximos):
    """Resumen de media hora: puesto, distancias, fuerza y debilidad, y lo que viene."""
    i = next((k for k, r in enumerate(lb_rows) if r["team"] == "t18"), None)
    if i is None: return None
    us = lb_rows[i]; L = [f"Radio Rastro, resumen de las {dt.datetime.now():%H:%M}."]
    L.append(f"Vamos {puesto(us['rank'])} con {num(us['score'])} puntos y {us['deals']} tratos.")
    if i: L.append(f"Por delante, {equipo(lb_rows[i-1]['team'])} a {num(lb_rows[i-1]['score'] - us['score'])} puntos.")
    if i + 1 < len(lb_rows): L.append(f"Por detrás, {equipo(lb_rows[i+1]['team'])} a {num(us['score'] - lb_rows[i+1]['score'])}.")
    best_neg = max(lb_rows, key=lambda r: r["negotiating"])
    if best_neg["team"] == "t18": L.append(f"Tenemos la mejor negociación de todos: {num(us['negotiating'])}.")
    else: L.append(f"Negociación {num(us['negotiating'])}.")
    best_mk = max(lb_rows, key=lambda r: r["market"])
    if us["market"] < best_mk["market"] - 1:
        L.append(f"Nuestro punto débil es el mercado: {num(us['market'])}, frente a {num(best_mk['market'])} {de(best_mk['team'])}. Sin venue propio no sube.")
    if proximos:
        L.append("Lo próximo: " + "; ".join(f"en unos {m} minutos, {w}" for m, w in proximos[:2]) + ".")
    return re.sub(r",\s*\.", ".", PAUSA.join(L))
