"""Haggle with a dealer from the command line.

    python3 run_dealer.py abuela                       # 3 packs (sobre_barrio), opened after each deal
    python3 run_dealer.py abuela -n 1                  # one pack
    python3 run_dealer.py abuela --card LAV-06 --anchor 15 --limit 22
    python3 run_dealer.py abuela --sell 123 --anchor 20 --limit 13   # sell asset 123, never below 13
"""
raise SystemExit("ARCHIVED by M18: pre-harness script that could reach the game without the Gate. Use the harness: python3 bazaar.py (see CLAUDE.md).")  # M18 guard
import argparse
import sqlite3

from bazaar_sdk import BazaarError
from agent.client import client
from agent.dealers import PROFILES
from agent.haggle import haggle
from agent.journal import log
from agent.information import DEFAULT_STATE, get_context, record_result

p = argparse.ArgumentParser()
p.add_argument("dealer")
p.add_argument("-n", type=int, default=3, help="how many deals in a row")
p.add_argument("--pack", default="sobre_barrio")
p.add_argument("--card", help="buy a card (e.g. LAV-06) instead of a pack")
p.add_argument("--sell", type=int, help="sell one of our assets (asset id) instead of buying")
p.add_argument("--anchor", type=int, help="first price (overrides the profile)")
p.add_argument("--limit", type=int, help="worst price we accept (overrides the profile)")
p.add_argument("--rounds", type=int, help="rounds from anchor to limit (fewer = bigger steps)")
p.add_argument("--information", nargs="?", const=str(DEFAULT_STATE),
               help="read collector context and remember confirmed results (optional state path)")
a = p.parse_args()

b = client()
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
cfg["rounds"] = a.rounds or cfg["rounds"]
if not isinstance(cfg["anchor"], int) or not isinstance(cfg["limit"], int):
    raise SystemExit("cards and sales need --anchor and --limit")

SCORE_KEYS = ("score", "negotiating", "ladder_points", "duel_points", "neg_points", "deals", "rank")
for i in range(1 if a.sell else a.n):
    me = b.me()
    if a.information:
        context = get_context(a.information, reserve_cash=cfg.get('reserve_cash', 0))
        log(a.dealer, event='information_before', context=context)
        print(f"  collector ready={context['ready']} · actions={context['actions']}")
    before = {k: me["score"].get(k) for k in SCORE_KEYS}
    print(f"\n== {i + 1}/{a.n} · cash {me['cash']} P · score {before}")
    try:
        r = haggle(b, a.dealer, topic, buying=buying, lines=prof["lines"], **cfg)
        if a.information:
            item = (next((x['ref'] for x in me['assets'] if x['id'] == a.sell), None)
                    if a.sell else a.card or a.pack)
            try:
                record_result(a.information, team=me.get('id') or me.get('team'),
                              dealer=a.dealer, item=item, buying=buying, result=r)
            except (OSError, sqlite3.Error) as error:
                log(a.dealer, event='information_memory_error', error=type(error).__name__)
            log(a.dealer, event='information_after', context=get_context(a.information))
        b.wait_tick()  # the score updates once the deal has settled
        after = {k: b.me()["score"].get(k) for k in SCORE_KEYS}
        print(f"  score -> {after}")  # measure what each deal is worth: this is how we learn the ladder formula
        log(a.dealer, event="score", thread=r["thread"], status=r["status"], price=r["price"], before=before, after=after)
        if r["status"] == "deal" and not a.sell and not a.card:
            pack = next(x for x in b.me()["assets"] if x["kind"] == "pack" and x["ref"] == a.pack)
            cards = b.open_pack(pack["id"])["cards"]
            print("  pulled " + ", ".join(f"{c['name']} ({c['rarity']})" for c in cards))
    except BazaarError as e:  # persona_quota (hourly limit), cooloff, a thread already open, insufficient_cash...
        print(f"  stopped: {e.code} {e.message} {e.extra or ''}")
        log(a.dealer, event="error", code=e.code, message=e.message, extra=e.extra)
        break
