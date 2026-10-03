"""Bitácora del Team 18: línea de tiempo, decisiones y lecciones para el relato ante el jurado.

Reescribe solo los bloques <!-- AUTO:x --> ... <!-- /AUTO:x --> de docs/bitacora.md; lo escrito a mano fuera
de ellos no se toca. Fuentes:
  - lecturas públicas sin clave (GET /api/clock, /api/schedule, /api/leaderboard, /api/venues), como rivals.py;
  - git log (commits, y las líneas «Decisión: / Por qué: / Lección: / Hito:» del cuerpo de un commit);
  - logs/leaderboard.jsonl si existe (historial de clasificación de esta máquina);
  - docs/bitacora-hitos.json: memoria compartida (calendario visto, cambios de puesto, entradas a mano).
No escribe nada en el juego ni toca agent/ (el code_hash del operador no cambia).

Uso:
  python3 bitacora.py                         refresca todo (3-4 GET públicos, 1 por segundo)
  python3 bitacora.py --no-net                solo git y ficheros locales
  python3 bitacora.py --max-age 15            red solo si la última lectura tiene más de 15 min (para hooks)
  python3 bitacora.py --watch 10              refresca cada 10 min
  python3 bitacora.py decision "No abrimos mercado propio" --why "..." [--evidencia "..."]
  python3 bitacora.py leccion "El marcador va atrasado" --why "..."
  python3 bitacora.py hito "RET 10/10"
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(ROOT, "docs", "bitacora.md")
DATA = os.path.join(ROOT, "docs", "bitacora-hitos.json")
LB_LOG = os.path.join(ROOT, "logs", "leaderboard.jsonl")
TEAM = "t18"
MADRID = timezone(timedelta(hours=2))          # CEST durante todo el hackathon (2-4 oct 2026)
AUTHORS = {"zetazeta50": "Santi", "rubenuni1009": "Rubén", "Jorge Medina": "Jorge"}
DAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
TRAILER = re.compile(r"^\s*(decisi[oó]n|lecci[oó]n|hito|por qu[eé]|porque|why)\s*:\s*(.+)$", re.I)
KIND = {"decision": "decisión", "leccion": "lección", "hito": "hito"}


# ------------------------------------------------------------------------------------------------ util

def fmt_ts(ts, approx=False):
    d = datetime.fromtimestamp(ts, MADRID)
    return f"{'≈ ' if approx else ''}{DAYS[d.weekday()]} {d:%H:%M}"


def num(x, nd=2):
    return f"{x:.{nd}f}".replace(".", ",") if isinstance(x, (int, float)) else "?"


def cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def load_data():
    try:
        with open(DATA, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    for k in ("calendario", "ranking", "entradas", "hitos"):
        d.setdefault(k, [])
    d.setdefault("ultima_red", 0)
    return d


def save_data(d):
    tmp = DATA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, DATA)


# ------------------------------------------------------------------------------------------- lecturas

def fetch_public():
    """Lecturas públicas sin clave por el transporte del arnés (allowlist, 1 GET/s). None si falla."""
    sys.path.insert(0, ROOT)
    from agent.contracts import PROD_URL
    from agent.transport import RateLimiter, public_get
    lim = RateLimiter(rate=1, burst=1, reserve=0)
    out = {}
    try:
        for name in ("clock", "schedule", "leaderboard", "venues"):
            out[name] = public_get(PROD_URL, "/api/" + name, lim)
    except Exception as e:                                   # red caída o 429: se queda lo de la última vez
        print(f"bitacora: lectura pública fallida ({e.__class__.__name__}); se conservan los bloques en vivo",
              file=sys.stderr)
        return None
    out["ts"] = time.time()
    return out


def git_commits():
    try:
        raw = subprocess.run(["git", "log", "--no-merges", "--date=unix", "--pretty=%H%x1f%ad%x1f%an%x1f%s%x1f%b%x1e"],
                             cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for rec in raw.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) < 5:
            continue
        h, ts, author, subject, body = parts
        out.append({"hash": h[:7], "ts": int(ts), "autor": AUTHORS.get(author, author), "asunto": subject,
                    "trailers": trailers(body)})
    return out


def trailers(body):
    """«Decisión: X» + «Por qué: Y» del cuerpo de un commit → [{tipo, texto, por_que}]."""
    out = []
    for line in body.splitlines():
        m = TRAILER.match(line)
        if not m:
            continue
        key = m.group(1).lower()
        if key.startswith(("por", "why")):
            if out:
                out[-1]["por_que"] = m.group(2).strip()
            continue
        tipo = "decisión" if key.startswith("decisi") else "lección" if key.startswith("lecci") else "hito"
        out.append({"tipo": tipo, "texto": m.group(2).strip(), "por_que": ""})
    return out


def git_user():
    try:
        name = subprocess.run(["git", "config", "user.name"], cwd=ROOT, capture_output=True, text=True,
                              timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        name = ""
    return AUTHORS.get(name, name or "?")


# ---------------------------------------------------------------------------------------- calendario

def parse_wall(s):
    try:
        return datetime.fromisoformat(s).timestamp()
    except (TypeError, ValueError):
        return None


def wall_estimator(now_h, now_ts, events):
    """Hora de juego → hora real, interpolando entre anclas conocidas (ahora y las aperturas/cierres con hora).
    Entre el cierre del sábado y la apertura del domingo la hora de juego no avanza, así que con la misma hora
    se toma el ancla más tardía. Fuera de las anclas, se extrapola con el ritmo del último tramo."""
    anchors = [(now_h, now_ts)] + [(e["at_hours"], w) for e in events if (w := parse_wall(e.get("wall")))]
    anchors.sort()

    def est(h):
        before = [a for a in anchors if a[0] <= h]
        after = [a for a in anchors if a[0] > h]
        if before and after:
            (h0, t0), (h1, t1) = before[-1], after[0]
            return t0 + (h - h0) * (t1 - t0) / (h1 - h0)
        segs = [(a, b) for a, b in zip(anchors, anchors[1:]) if b[0] > a[0]]
        rate = (segs[-1][1][1] - segs[-1][0][1]) / (segs[-1][1][0] - segs[-1][0][0]) if segs else 3600.0
        h0, t0 = (before[-1] if before else after[0])
        return t0 + (h - h0) * rate
    return est


def merge_calendar(d, snap):
    """Guarda cada evento del calendario oficial; los ya pasados se conservan con su última hora estimada."""
    clock, upcoming = snap["clock"], snap["schedule"].get("upcoming", [])
    now_h = snap["schedule"].get("now_hours", clock.get("t_hours"))
    est = wall_estimator(now_h, snap["ts"], upcoming)
    for e in upcoming:
        h = e.get("at_hours")
        if not isinstance(h, (int, float)):
            continue
        w = parse_wall(e.get("wall"))
        row = {"at_hours": round(h, 3), "accion": e.get("action"), "nota": e.get("note"),
               "ts": round(w or est(h)), "exacta": bool(w)}
        same = [c for c in d["calendario"] if c["accion"] == row["accion"] and c["nota"] == row["nota"]
                and abs(c["at_hours"] - row["at_hours"]) < 0.5 and not c.get("pasado")]
        if same:
            same[0].update(row)
        else:
            d["calendario"].append(row)
    for c in d["calendario"]:
        if c["at_hours"] <= now_h:
            c["pasado"] = True
    d["calendario"].sort(key=lambda c: (c["ts"], c["at_hours"]))


# ---------------------------------------------------------------------------------------- clasificación

def ranks(teams):
    order = sorted(teams.items(), key=lambda kv: -kv[1])
    return {t: i + 1 for i, (t, _) in enumerate(order)}


METRICS = {"total": "total", "neg": "negociación"}


def note_rank(d, row):
    """Apunta la fila de t18 por métrica si cambia el puesto o la ronda, o cada hora como mínimo."""
    same = [r for r in d["ranking"] if r.get("metric", "total") == row["metric"]]
    last = same[-1] if same else None
    if last and row["tick"] is not None and last.get("tick") is not None and row["tick"] <= last["tick"]:
        return
    if last and last["rank"] == row["rank"] and last.get("round") == row.get("round") and row["ts"] - last["ts"] < 3600:
        return
    d["ranking"].append(row)


def seed_ranking_from_log(d):
    """logs/leaderboard.jsonl (affinity.py --watch) guarda la puntuación de negociación de cada equipo."""
    if any(r.get("metric") == "neg" for r in d["ranking"]) or not os.path.exists(LB_LOG):
        return
    with open(LB_LOG, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            teams = r.get("teams") or {}
            if TEAM in teams:
                note_rank(d, {"metric": "neg", "ts": round(r["ts"]), "tick": r.get("tick"), "round": r.get("round"),
                              "rank": ranks(teams)[TEAM], "score": teams[TEAM]})


def lb_rows(snap):
    lb = snap["leaderboard"]
    teams = lb.get("teams", [])
    me = next((t for t in teams if t["team"] == TEAM), None)
    if not me:
        return []
    base = {"ts": round(snap["ts"]), "tick": lb.get("tick"), "round": lb.get("round")}
    neg = {t["team"]: t.get("negotiating") or 0 for t in teams}
    return [{**base, "metric": "total", "rank": me["rank"], "score": me["score"], "neg": me.get("negotiating"),
             "market": me.get("market")},
            {**base, "metric": "neg", "rank": ranks(neg)[TEAM], "score": me.get("negotiating")}]


# ------------------------------------------------------------------------------------------- bloques

def block_estado(snap, d):
    clock, lb = snap["clock"], snap["leaderboard"]
    teams = lb.get("teams", [])
    me = next((t for t in teams if t["team"] == TEAM), {})
    lead = teams[0] if teams else {}
    pages = me.get("pages_complete")
    lines = [f"_Actualizado {fmt_ts(snap['ts'])} (Madrid) · tick {clock.get('tick')} · hora de juego "
             f"{num(clock.get('t_hours'))} · {clock.get('round_name', '')}"
             f"{' · **reloj en pausa**' if clock.get('paused') else ''}_ <!-- ts -->", "",
             "| Puesto | Total | Negociación | Mercado | Nivel | Páginas | Álbum | Tratos |",
             "|---|---|---|---|---|---|---|---|",
             f"| **{me.get('rank', '?')}.º** de {len(teams)} | {num(me.get('score'))} | {num(me.get('negotiating'))} | "
             f"{num(me.get('market'))} | {me.get('level', '?')} | {pages} | {me.get('album_filled')}/"
             f"{me.get('album_slots')} | {me.get('deals')} |", ""]
    if lead and lead.get("team") != TEAM:
        lines.append(f"Líder: {lead['team']} con {num(lead['score'])} (a {num(lead['score'] - me.get('score', 0))} "
                     f"de nosotros). Marcador relativo y con retraso (snapshot tick {lb.get('tick')}): una subida no "
                     "prueba por sí sola una mejora nuestra.")
    nxt = [c for c in d["calendario"] if not c.get("pasado")][:4]
    if nxt:
        lines += ["", "Próximos eventos oficiales: " + " · ".join(
            f"{fmt_ts(c['ts'], not c['exacta'])} {cell(c['nota'])}" for c in nxt)]
    return "\n".join(lines)


def block_mercado(snap):
    """Evidencia viva para D1: puntos de mercado con mercado propio frente al puesto gratuito."""
    lb = {t["team"]: t for t in snap["leaderboard"].get("teams", [])}
    own, starter, opened = {}, {}, {}
    for v in snap["venues"].get("venues", []):
        o = v.get("owner")
        if o not in lb:
            continue
        if not v.get("starter"):
            opened.setdefault(o, []).append(v)               # cada apertura cuesta 20 P aunque se cierre
        if v.get("status") in ("open", "closing"):
            (starter if v.get("starter") else own).setdefault(o, []).append(v)
    starter = {t: vs for t, vs in starter.items() if t not in own}
    rows = []

    def stats(group):
        m = sorted((lb[t]["market"] for t in group), reverse=True)
        return (sum(m) / len(m), m[0], m[-1]) if m else (None, None, None)
    for label, group in (("Con mercado propio", own), ("Con el puesto gratuito", starter)):
        avg, best, worst = stats(group)
        rows.append(f"| {label} | {len(group)} | {num(avg)} | {num(best)} | {num(worst)} |")
    a_own, a_st = stats(own)[0], stats(starter)[0]
    below = sorted((t for t in own if lb[t]["market"] < lb.get(TEAM, {}).get("market", 0)), key=lambda t: lb[t]["market"])
    detail = ", ".join(f"{t} {num(lb[t]['market'])} ({sum(v.get('trades', 0) for v in own[t])} tratos)"
                       for t in sorted(own, key=lambda t: -lb[t]["market"]))
    lines = [f"_Actualizado {fmt_ts(snap['ts'])} · /api/leaderboard + /api/venues_ <!-- ts -->", "",
             "| Grupo | Equipos | Mercado medio | Mejor | Peor |", "|---|---|---|---|---|", *rows, "",
             f"Nosotros: **{num(lb.get(TEAM, {}).get('market'))}** con el puesto gratuito y 0 P invertidos."]
    if a_own is not None and a_st is not None:
        lines.append(f"Diferencia media de abrir: **{num(a_own - a_st)}** puntos de mercado, a cambio de 250 P "
                     "bloqueados + 20 P perdidos.")
    if below:
        lines.append("Abrieron y hoy puntúan **menos** que nuestro puesto gratuito: " + ", ".join(
            f"{t} ({num(lb[t]['market'])})" for t in below) + ".")
    serial = sorted(((t, vs) for t, vs in opened.items() if len(vs) > 1), key=lambda kv: -len(kv[1]))
    if serial:
        lines.append("Abrieron más de un mercado (20 P perdidos por apertura): " + ", ".join(
            f"{t} {len(vs)} mercados, {sum(v.get('trades', 0) for v in vs)} tratos" for t, vs in serial) + ".")
    lines += ["", f"<details><summary>Detalle por equipo con mercado propio</summary>\n\n{detail}\n\n</details>"]
    return "\n".join(lines)


def block_timeline(d, commits):
    ev = []
    for h in d["hitos"]:
        ev.append((h["ts"], fmt_ts(h["ts"], h.get("aprox")), h.get("tipo", "equipo"), h["texto"]))
    for c in d["calendario"]:
        if c.get("pasado"):
            ev.append((c["ts"], fmt_ts(c["ts"], not c["exacta"]), "oficial", f"{c['nota']} (h {num(c['at_hours'])})"))
    prev = {}
    for r in d["ranking"]:
        m = r.get("metric", "total")
        p = prev.get(m)
        if p is None or r["rank"] != p["rank"]:
            arrow = "" if p is None else (" ↑" if r["rank"] < p["rank"] else " ↓")
            extra = f", mercado {num(r['market'])}" if r.get("market") is not None else ""
            ev.append((r["ts"], fmt_ts(r["ts"]), "clasificación",
                       f"t18 {r['rank']}.º{arrow} en {METRICS[m]} ({num(r['score'])}{extra}; tick {r.get('tick')})"))
        prev[m] = r
    for e in d["entradas"]:
        why = f" — _por qué:_ {e['por_que']}" if e.get("por_que") else ""
        ev.append((e["ts"], fmt_ts(e["ts"]), e["tipo"], f"**{e['texto']}**{why} ({e.get('autor', '?')})"))
    for c in commits:
        for t in c["trailers"]:
            why = f" — _por qué:_ {t['por_que']}" if t["por_que"] else ""
            ev.append((c["ts"], fmt_ts(c["ts"]), t["tipo"], f"**{t['texto']}**{why} ({c['autor']}, {c['hash']})"))
    ev.sort(key=lambda e: e[0])
    lines = ["| Cuándo | Tipo | Hito |", "|---|---|---|"]
    lines += [f"| {when} | {tipo} | {cell(text)} |" for _, when, tipo, text in ev]
    upcoming = [c for c in d["calendario"] if not c.get("pasado")]
    if upcoming:
        lines += ["", "**Por venir (calendario oficial; ≈ = hora estimada, los organizadores pueden moverla):**", ""]
        lines += [f"- {fmt_ts(c['ts'], not c['exacta'])} · h {num(c['at_hours'])} · {cell(c['nota'])}" for c in upcoming]
    return "\n".join(lines)


def block_registro(d, commits):
    items = [(e["ts"], e["tipo"], e["texto"], e.get("por_que", ""), e.get("evidencia", ""), e.get("autor", "?"))
             for e in d["entradas"]]
    items += [(c["ts"], t["tipo"], t["texto"], t["por_que"], "", f"{c['autor']}, {c['hash']}")
              for c in commits for t in c["trailers"]]
    items = [i for i in items if i[1] in ("decisión", "lección")]
    if not items:
        return ("_Aún no hay entradas. `python3 bitacora.py decision \"...\" --why \"...\"` o una línea "
                "«Decisión: …» / «Por qué: …» en el cuerpo de un commit._")
    lines = []
    for ts, tipo, texto, why, evid, autor in sorted(items, reverse=True):
        lines.append(f"- **{fmt_ts(ts)} · {tipo}: {texto}** ({autor})")
        if why:
            lines.append(f"  - Por qué: {why}")
        if evid:
            lines.append(f"  - Evidencia: {evid}")
    return "\n".join(lines)


def block_commits(commits):
    by_day = {}
    for c in sorted(commits, key=lambda c: c["ts"]):
        by_day.setdefault(fmt_ts(c["ts"]).split()[0], []).append(c)
    out = [f"{len(commits)} commits sin merges."]
    for day, cs in by_day.items():
        out += ["", f"<details><summary>{day}: {len(cs)} commits</summary>", ""]
        out += [f"- {fmt_ts(c['ts']).split()[1]} · {c['autor']} · {cell(c['asunto'])} (`{c['hash']}`)" for c in cs]
        out += ["", "</details>"]
    return "\n".join(out)


# ------------------------------------------------------------------------------------------ documento

def replace_blocks(text, blocks):
    """Sustituye el interior de cada <!-- AUTO:x --> ... <!-- /AUTO:x -->. Devuelve (texto, cambió_algo_real)."""
    changed = False
    for name, body in blocks.items():
        m = re.search(rf"<!-- AUTO:{name} -->\n?(.*?)\n?<!-- /AUTO:{name} -->", text, re.S)
        if not m:
            continue
        strip = lambda s: re.sub(r"^.*<!-- ts -->.*$", "", s, flags=re.M)   # la marca de hora sola no es cambio
        if strip(m.group(1)) != strip(body):
            changed = True
        text = text[:m.start()] + f"<!-- AUTO:{name} -->\n{body}\n<!-- /AUTO:{name} -->" + text[m.end():]
    return text, changed


def refresh(net=True, max_age=None, quiet=False):
    d = load_data()
    seed_ranking_from_log(d)
    snap = None
    if net and (max_age is None or time.time() - d["ultima_red"] > max_age * 60):
        snap = fetch_public()
    commits = git_commits()
    blocks = {"timeline": None, "registro": block_registro(d, commits), "commits": block_commits(commits)}
    if snap:
        d["ultima_red"] = round(snap["ts"])
        merge_calendar(d, snap)
        for row in lb_rows(snap):
            note_rank(d, row)
        blocks["estado"] = block_estado(snap, d)
        blocks["mercado"] = block_mercado(snap)
    blocks["timeline"] = block_timeline(d, commits)
    save_data(d)
    with open(DOC, encoding="utf-8") as f:
        old = f.read()
    new, changed = replace_blocks(old, blocks)
    if changed:
        with open(DOC + ".tmp", "w", encoding="utf-8", newline="\n") as f:
            f.write(new)
        os.replace(DOC + ".tmp", DOC)
    if not quiet:
        print(f"bitacora: {'actualizada' if changed else 'sin cambios'} · {'con' if snap else 'sin'} lectura pública "
              f"· {len(commits)} commits · {len(d['entradas'])} entradas a mano")
    return changed


def add_entry(tipo, texto, why="", evidencia=""):
    d = load_data()
    e = {"ts": round(time.time()), "tipo": tipo, "texto": texto, "autor": git_user()}
    if why:
        e["por_que"] = why
    if evidencia:
        e["evidencia"] = evidencia
    if tipo == "hito":
        d["hitos"].append({"ts": e["ts"], "tipo": "equipo", "texto": texto})
    else:
        d["entradas"].append(e)
    save_data(d)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("cmd", nargs="?", choices=("decision", "leccion", "hito"))
    p.add_argument("texto", nargs="?")
    p.add_argument("--why", default="")
    p.add_argument("--evidencia", default="")
    p.add_argument("--no-net", action="store_true")
    p.add_argument("--max-age", type=float, help="minutos: sin red si la última lectura es más reciente")
    p.add_argument("--watch", type=float, metavar="MIN")
    p.add_argument("--quiet", action="store_true")
    a = p.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if a.cmd:
        if not a.texto:
            p.error(f"{a.cmd} necesita un texto")
        add_entry(KIND[a.cmd], a.texto, a.why, a.evidencia)
        refresh(net=False, quiet=a.quiet)
        return 0
    while True:
        refresh(net=not a.no_net, max_age=a.max_age, quiet=a.quiet)
        if not a.watch:
            return 0
        time.sleep(max(1.0, a.watch) * 60)


if __name__ == "__main__":
    sys.exit(main())
