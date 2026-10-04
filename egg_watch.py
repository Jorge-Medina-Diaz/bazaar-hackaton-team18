"""Vigía de easter eggs: solo GET públicos, SIN clave (no lee .env, no puede escribir).

Avisa (consola + logs/eggs.jsonl) de:
- cartas nuevas u ocultas en /api/catalog (LAT-13 salió así: "hidden": true al acuñarse);
- egg.found / egg.given / badge.awarded en /api/feed, e insignias nuevas en /api/leaderboard;
- pistas sembradas: una frase de dealer que se repite a >= 2 equipos (la de Pilar se repitió 18 veces)
  o que contiene "ask her/him about", "only one ... printed", etc.;
- noticias nuevas en /api/news.

    python3 egg_watch.py            # bucle cada 30 s
    python3 egg_watch.py --once     # una pasada
    python3 egg_watch.py --check    # comprobación offline, sin red
"""
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

URL = "https://bazaar.causaprima.ai"
POLL = 30
LOG = Path(__file__).resolve().parent / "logs" / "eggs.jsonl"
DEALERS = {"abuela", "chato", "pilar", "picaros", "banco"}
EGG_TYPES = {"egg.found", "egg.given", "badge.awarded"}
HINT = re.compile(r"ask (her|him|them|carmen|don \w+|el chato|pilar|paco|nando)\b.{0,40}\babout|they say only|"
                  r"only one .{0,30}(printed|ever)|knows (the story|where)|\bpassword\b|\briddle\b", re.I)
# ponytail: frases ya conocidas, para no avisar en cada arranque; añadir aquí las que se vayan resolviendo
KNOWN = {"they say only one golden chulapa was ever printed.",
         "carmen at el rastro knows the story; ask her about the golden chulapa."}
NOISE = re.compile(r"full page|duplicates|eaten|eat something|hungry|final|take it|my price|my terms|haggle|"
                   r"hurry|opens? (for everyone|at)|trade straight|meet in the middle|kind face|"
                   r"i swear|quick|we leave|next door|we like you|nando|paco", re.I)   # Pícaros' patter


def get(path):
    req = urllib.request.Request(URL + path, headers={"User-Agent": "t18-egg-watch"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def sentences(text):
    for s in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        s = s.strip()
        if len(s) >= 35:
            yield re.sub(r"\d+", "#", s.lower())


class Watch:
    def __init__(self):
        self.cards = None          # card ids seen in the first catalog read
        self.events = set()
        self.badges = set()
        self.news = set()
        self.said = defaultdict(set)   # sentence -> teams it was said to
        self.flagged = set(KNOWN)
        self.archive = None            # an open file: every new feed event is appended (logs/feed_all.jsonl)

    def catalog(self, cat):
        out = []
        cards = {c["id"]: c for s in cat.get("sets", []) for c in s.get("cards", [])}
        for cid, c in cards.items():
            first, new = self.cards is None, self.cards is not None and cid not in self.cards
            if new or (first and c.get("hidden")):
                out.append(("card", f"{cid} {c.get('name')} {c.get('rarity')} hidden={c.get('hidden')} "
                                    f"minted={c.get('minted')}/{c.get('print_run')} — {c.get('flavour')}"))
        self.cards = set(cards)
        return out

    def feed(self, events):
        out = []
        for e in events:
            if e.get("id") in self.events:
                continue
            self.events.add(e.get("id"))
            if self.archive is not None:   # ponytail: the feed only serves its last 500 events, so keep them all
                self.archive.write(json.dumps(e, ensure_ascii=False) + "\n")
            p = e.get("payload") or {}
            if e.get("type") in EGG_TYPES or e.get("type") == "bench.finished":
                out.append((e["type"], f"tick {e.get('tick')}: {json.dumps(p, ensure_ascii=False)}"))
            if e.get("type") == "thread.message" and p.get("sender") in DEALERS and p.get("text"):
                for s in sentences(p["text"]):
                    self.said[s].add(p.get("team"))
                    hit = HINT.search(s) or (len(self.said[s]) >= 2 and not NOISE.search(s))
                    if hit and s not in self.flagged:
                        self.flagged.add(s)
                        out.append(("hint", f"tick {e.get('tick')} {p['sender']}->{p.get('team')}: {s}"))
        return out

    def leaderboard(self, lb):
        out = []
        for t in lb.get("teams", []):
            for b in t.get("badges") or []:
                if b not in self.badges:
                    self.badges.add(b)
                    out.append(("badge", f"{b} (primero visto en {t.get('team')})"))
        return out

    def newsfeed(self, news):
        out = []
        for n in news.get("news", []):
            if n.get("id") not in self.news:
                self.news.add(n.get("id"))
                out.append(("news", f"{n.get('source_name')}: {n.get('headline')} {n.get('body') or ''}".strip()))
        return out


def once(w):
    alerts = []
    for name, path, fn in (("catalog", "/api/catalog", w.catalog), ("feed", "/api/feed?limit=500",
                           lambda d: w.feed(d.get("events", []))), ("leaderboard", "/api/leaderboard", w.leaderboard),
                           ("news", "/api/news", w.newsfeed)):
        try:
            alerts += fn(get(path))
        except Exception as e:  # noqa: BLE001 - un GET fallido no para el vigía
            alerts.append(("error", f"{name}: {e.__class__.__name__}: {e}"))
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        for kind, msg in alerts:
            f.write(json.dumps({"ts": ts, "kind": kind, "msg": msg}, ensure_ascii=False) + "\n")
            bell = "\a" if kind in ("card", "egg.found", "egg.given", "hint") else ""
            print(f"{bell}[{ts}] {kind:13s} {msg}", flush=True)


def check():
    w = Watch()
    cat = {"sets": [{"cards": [{"id": "LAT-12", "hidden": False}]}]}
    assert w.catalog(cat) == []
    cat["sets"][0]["cards"].append({"id": "LAT-13", "hidden": True, "name": "X"})
    assert [k for k, _ in w.catalog(cat)] == ["card"]
    assert w.catalog(cat) == []                                  # once only
    msg = lambda i, team, text: {"id": i, "tick": 1, "type": "thread.message",  # noqa: E731
                                 "payload": {"sender": "pilar", "team": team, "text": text}}
    planted = "Nobody has seen the ghost train since the station closed at midnight."
    assert w.feed([msg(1, "t01", "Fifty P. " + planted)]) == []
    assert [k for k, _ in w.feed([msg(2, "t02", "Sixty P. " + planted)])] == ["hint"]   # 2nd team -> planted
    assert w.feed([msg(3, "t03", planted)]) == []                                     # once only
    assert w.feed([msg(4, "t04", "They say only one golden chulapa was ever printed.")]) == []   # KNOWN
    assert [k for k, _ in w.feed([msg(5, "t05", "Ask him about the ghost platform, señor.")])] == ["hint"]
    egg = {"id": 6, "tick": 9, "type": "egg.found", "payload": {"persona": "chato", "team": "t07"}}
    assert [k for k, _ in w.feed([egg, egg])] == ["egg.found"]
    bench = {"id": 7, "tick": 9, "type": "bench.finished", "payload": {"venue": "v07", "efficiency": 0.95}}
    assert [k for k, _ in w.feed([bench])] == ["bench.finished"]
    assert [k for k, _ in w.leaderboard({"teams": [{"team": "t1", "badges": ["Sharp ear", "Night owl"]}]})] \
        == ["badge", "badge"]
    print("egg_watch: check OK")


if __name__ == "__main__":
    if {"-h", "--help"} & set(sys.argv[1:]):
        print(__doc__)
        sys.exit(0)
    if "--check" in sys.argv:
        check()
    else:
        w = Watch()
        LOG.parent.mkdir(exist_ok=True)
        w.archive = (LOG.parent / "feed_all.jsonl").open("a", encoding="utf-8", buffering=1)
        while True:
            once(w)
            if "--once" in sys.argv:
                break
            time.sleep(POLL)
