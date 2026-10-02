"""Haggle with a dealer from the command line.

    python3 run_dealer.py abuela                       # 3 packs (sobre_barrio), opened after each deal
    python3 run_dealer.py abuela -n 1                  # one pack
    python3 run_dealer.py abuela --card LAV-06 --anchor 15 --limit 22
    python3 run_dealer.py abuela --sell 123 --anchor 20 --limit 13   # sell asset 123, never below 13
"""
import argparse, os  # noqa: E401

from bazaar_sdk import Bazaar, BazaarError
from agent.dealers import PROFILES
from agent.haggle import haggle
from agent.journal import log

p = argparse.ArgumentParser()
p.add_argument("dealer")
p.add_argument("-n", type=int, default=3, help="how many deals in a row")
p.add_argument("--pack", default="sobre_barrio")
p.add_argument("--card", help="buy a card (e.g. LAV-06) instead of a pack")
p.add_argument("--sell", type=int, help="sell one of our assets (asset id) instead of buying")
p.add_argument("--anchor", type=int, help="first price (overrides the profile)")
p.add_argument("--limit", type=int, help="worst price we accept (overrides the profile)")
a = p.parse_args()

b = Bazaar(os.environ.get("BAZAAR_URL", "https://bazaar.causaprima.ai"), os.environ["BAZAAR_KEY"])
prof = PROFILES[a.dealer]
cfg = dict(prof.get("pack", {"anchor": 0.5, "limit": 0.8, "rounds": 6, "beta": 1.0}))
if a.sell:
    topic, buying = {"sell": {"assets": [a.sell]}}, False
elif a.card:
    topic, buying = {"buy": {"card": a.card}}, True
else:
    topic, buying = {"buy": {"pack": a.pack}}, True
    ask = next(s for s in b.dealer(a.dealer)["menu"]["sells"] if s.get("pack") == a.pack)["opening_ask"]
    cfg["anchor"], cfg["limit"] = round(ask * cfg["anchor"]), round(ask * cfg["limit"])
cfg["anchor"] = a.anchor or cfg["anchor"]
cfg["limit"] = a.limit or cfg["limit"]
if not isinstance(cfg["anchor"], int) or not isinstance(cfg["limit"], int):
    raise SystemExit("cards and sales need --anchor and --limit")

for i in range(1 if a.sell else a.n):
    print(f"\n== {i + 1}/{a.n} · cash {b.me()['cash']} P")
    try:
        r = haggle(b, a.dealer, topic, buying=buying, lines=prof["lines"], **cfg)
        if r["status"] == "deal" and not a.sell and not a.card:
            pack = next(x for x in b.me()["assets"] if x["kind"] == "pack" and x["ref"] == a.pack)
            cards = b.open_pack(pack["id"])["cards"]
            print("  pulled " + ", ".join(f"{c['name']} ({c['rarity']})" for c in cards))
    except BazaarError as e:  # persona_quota (hourly limit), cooloff, a thread already open, insufficient_cash...
        print(f"  stopped: {e.code} {e.message} {e.extra or ''}")
        log(a.dealer, event="error", code=e.code, message=e.message, extra=e.extra)
        break
