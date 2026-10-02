"""Bad-faith candidates: dealer messages whose words contradict their structured offer (EXP-014).

    python3 flags.py                     # list candidates from logs/feed.jsonl + the live feed (sends nothing)
    python3 flags.py --flag 882 "text says 14 P, offer is 16"   # flag one message (a wrong flag costs: be sure)

RULES: "Some lie; flag a message you believe is bad faith (a correct flag scores, a wrong one costs)."
Two checks, structure against words, nothing else:
  price  the text names prices ("14 P") and none of them is the offer's price
  final  the text says it is the last offer and the offer is not final (a final offer in soft words is not a lie)
"""
import json, os, re, sys  # noqa: E401

from agent.client import client
from agent.journal import log

PRICE = re.compile(r"(\d+)\s*P\b")
LAST = re.compile(r"last offer|final offer|last one|last word|can't go lower|cannot go lower|take it or leave|"
                  r"última palabra|mi última", re.I)


def events(b) -> list:
    seen, out = set(), []
    saved = [json.loads(line) for line in open("logs/feed.jsonl", encoding="utf-8")] if os.path.exists("logs/feed.jsonl") else []
    for e in saved + b.feed(500).get("events", []):
        if e["id"] not in seen:
            seen.add(e["id"])
            out.append(e)
    return out


def check(p: dict) -> list:
    """Reasons a dealer message contradicts its own offer, [] if none."""
    text, o = p.get("text") or "", p.get("offer") or {}
    price = (o.get("give") or {}).get("cash") or (o.get("want") or {}).get("cash")
    why = []
    named = [int(n) for n in PRICE.findall(text)]
    if named and price and price not in named:
        why.append(f"price: text says {named}, offer is {price}")
    if o and LAST.search(text) and not o.get("final"):  # claims a last offer that is not one: a bluff
        why.append("final: text says last offer, offer is not final")
    return why


def candidates(b, team: str) -> list:
    rows = []
    for e in events(b):
        p = e["payload"]
        if e["type"] != "thread.message" or str(p.get("sender", "")).startswith("t") or not p.get("offer"):
            continue
        for why in check(p):
            rows.append((p.get("team") == team, p["message"], p["sender"], p.get("team"), why, p.get("text") or ""))
    return rows


if __name__ == "__main__":
    b = client()
    if "--flag" in sys.argv:
        i = sys.argv.index("--flag")
        mid, reason = int(sys.argv[i + 1]), sys.argv[i + 2]
        r = b.flag(mid, reason)
        print(r)
        log("flags", event="flag", message=mid, reason=reason, result=r)
    else:
        me = b.me()
        team = me.get("team") or me.get("id") or me["score"]["team"]
        rows = candidates(b, team)
        for ours, mid, dealer, t, why, text in sorted(rows, key=lambda r: (not r[0], r[1])):
            print(f"{'OURS ' if ours else '     '}{mid:>6} {dealer:8} -> {t}: {why}\n         {text[:140]!r}")
        log("flags", event="scan", candidates=[r[:5] for r in rows])
        print(f"{len(rows)} candidates ({sum(r[0] for r in rows)} in our threads)")
