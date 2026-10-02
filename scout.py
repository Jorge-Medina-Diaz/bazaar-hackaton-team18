"""Learn a dealer's behaviour from everyone's public haggles (GET /api/feed needs no key).

    python3 scout.py abuela            # every thread with her: topic, price sequence, outcome
    python3 scout.py abuela --save     # also append the raw events to logs/feed.jsonl

Reading: "t05:16 abu:30 abu:26F" = team t05 offered 16, she asked 30, then 26 as her final word (F).
"""
import argparse, collections, json, urllib.request  # noqa: E401

from agent.journal import log

p = argparse.ArgumentParser()
p.add_argument("dealer")
p.add_argument("--save", action="store_true")
p.add_argument("--url", default="https://bazaar.causaprima.ai")
a = p.parse_args()

events = json.load(urllib.request.urlopen(f"{a.url}/api/feed?limit=1000"))["events"]
topics, msgs, deals = {}, collections.defaultdict(list), {}
for e in sorted(events, key=lambda e: e["id"]):
    pl = e["payload"]
    if a.save:
        log("feed", **e)
    if pl.get("with") != a.dealer and pl.get("persona") != a.dealer:
        continue
    if e["type"] == "thread.opened":
        topics[pl["thread"]] = (pl["team"], json.dumps(pl.get("topic"), ensure_ascii=False))
    elif e["type"] == "thread.message":
        o = pl.get("offer") or {}
        price = (o.get("want") or {}).get("cash") or (o.get("give") or {}).get("cash")
        msgs[pl["thread"]].append(f"{pl['sender'][:3]}:{price}{'F' if o.get('final') else ''}")
    elif e["type"] == "settlement":
        deals[e["tick"], tuple(pl["parties"])] = pl

for tid in sorted(msgs):
    team, topic = topics.get(tid, ("?", "?"))
    print(f"{tid:>4} {team} {topic}\n      {' '.join(msgs[tid])}")
print(f"\n{len(msgs)} threads, {len(deals)} settlements with {a.dealer} in the last {len(events)} public events")
