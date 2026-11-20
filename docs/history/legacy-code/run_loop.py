"""The always-on agent: every tick, look for value and take the single best action. Ctrl+C to stop.

    python3 run_loop.py --dry     # print what it would do, touch nothing
    python3 run_loop.py           # act

Each tick, in order:
  1. alerts   a new or changed level (El Chato...) or new duels: printed and logged, never acted on blindly
  2. duels    live duels get one message each (agent/duels.py; never outside our limit)
  3. market   the best offer on El Rastro by value gained (neg_points) is accepted if gain >= MIN_GAIN:
              BUY  someone sells one card for cash: gain = value(one more copy) - price - fee
              SELL someone bids cash for a card we hold: gain = bid - fee - your_value of our copy
              your_value already includes page bonuses, so cards of a complete page are never worth selling
  4. relist   spare copies at 9 P every RELIST ticks (market.sell_dups skips what is already listed)
One accept per tick is the team limit; cash never drops below RESERVE (venue bond 270 P, El Chato, duels).
"""
raise SystemExit("ARCHIVED by M18: pre-harness script that could reach the game without the Gate. Use the harness: python3 bazaar.py (see CLAUDE.md).")  # M18 guard
import json, sys  # noqa: E401

from bazaar_sdk import BazaarError
from agent.client import client
from agent.duels import step as duel_step
from agent.journal import log
from market import fee, sell_dups

MIN_GAIN = 3      # primas of value; below this the fee/latency risk is not worth an accept
RESERVE = 150     # keep for the venue bond (250 + 20) once tomorrow's 150 P allowance lands
RELIST = 10       # ticks between relisting spares
PROTECT = {"LAT"}  # sets we are completing (D-009): only spare copies may be sold
DRY = "--dry" in sys.argv


def best_trade(b, me) -> tuple:
    """(gain, kind, offer, our_asset_id) of the best acceptable offer on El Rastro, or (0, None, None, None)."""
    mine = b.my_offers()["offers"]
    ours = {o["id"] for o in mine if o["maker"] == me["id"]}
    to_us = [o for o in mine if o.get("to") == me["id"]]  # offers addressed to us directly
    listed = {a["id"] for o in mine if o["maker"] == me["id"] for a in o["give"].get("assets") or []}
    held = {}
    for a in sorted(me["assets"], key=lambda a: a["id"] in listed):  # prefer a copy not locked in our own listing
        if a["kind"] == "card":
            held.setdefault(a["ref"], a)  # all copies carry the same your_value (the last copy's)
    best, values = (0, None, None, None), {}
    for o in b.board("rastro").get("offers", []) + to_us:
        if o["id"] in ours or o.get("status", "open") != "open":
            continue
        g, w = o["give"], o["want"]
        if (len(g.get("assets") or []) == 1 and not g.get("cash") and not g.get("types")
                and w.get("cash") and not w.get("assets") and not w.get("types")):  # a card for cash
            if g["assets"][0].get("kind", "card") != "card":  # packs: value() only knows cards (unknown_card, tick 141)
                continue
            ref, price = g["assets"][0]["ref"], w["cash"]
            if me["cash"] - price - fee(price) < RESERVE:
                continue
            values.setdefault(ref, b.value(ref)["your_value"])
            cand = (round(values[ref] - price - fee(price), 1), "BUY", o, None)
        elif (g.get("cash") and not g.get("assets") and not g.get("types") and len(w.get("types") or []) == 1
              and not w.get("assets") and not w.get("cash")):  # a bid for a card type
            kind, ref = w["types"][0].split(":", 1)
            if kind != "card":
                continue
            if ref not in held:
                continue
            if ref[:3] in PROTECT and sum(1 for a in me["assets"] if a["ref"] == ref) < 2:
                continue  # last copy of a page we are building
            cand = (round(g["cash"] - fee(g["cash"]) - held[ref]["your_value"], 1), "SELL", o, held[ref]["id"])
        else:
            continue
        if cand[0] > best[0]:
            best = cand
    return best


def main() -> None:
    b, duel_state, last_levels, last_tick = client(), {}, None, -1
    print(f"loop started ({'DRY' if DRY else 'LIVE'}): min gain {MIN_GAIN}, reserve {RESERVE}")
    while True:
        try:
            tick = b.clock()["tick"]
            if tick == last_tick:
                b.wait_tick()
                continue
            last_tick, me = tick, b.me()
            levels = json.dumps(b.levels(), sort_keys=True)
            if levels != last_levels:
                print(f"[{tick}] ALERT levels: {levels[:400]}")
                log("loop", event="levels", tick=tick, levels=json.loads(levels))
                last_levels = levels
            live = [d for d in b.duels().get("duels", []) if d.get("status") in ("open", "live", "active")]
            for d in live:
                log("loop", event="duel", tick=tick, duel=d)
                if not DRY:
                    duel_step(b, d, duel_state, tick)
            gain, kind, offer, asset = best_trade(b, me)
            if kind and gain >= MIN_GAIN:
                ref = (offer["give"]["assets"][0]["ref"] if kind == "BUY" else offer["want"]["types"][0])
                price = offer["want"]["cash"] if kind == "BUY" else offer["give"]["cash"]
                print(f"[{tick}] {kind} {ref} at {price}: gain {gain} (offer {offer['id']})")
                log("loop", event="trade", tick=tick, kind=kind, ref=ref, price=price, gain=gain, offer=offer["id"], dry=DRY)
                if not DRY:
                    b.accept(offer["id"], [asset] if asset else None)
            if tick % RELIST == 0 and not DRY:
                sell_dups(b, 9)
            s = me["score"]
            print(f"[{tick}] cash {me['cash']} · score {s['score']} · neg {s['neg_points']} · rank {s['rank']} · "
                  f"duels {len(live)} · best {kind or '-'} {gain}")
        except BazaarError as e:  # never die: log, wait for the next tick
            print(f"[{last_tick}] error {e.code}: {e.message}")
            log("loop", event="error", tick=last_tick, code=e.code, message=e.message, extra=e.extra)
        except Exception as e:  # a bug must not stop the agent (E11: a duel shape crash killed it at tick 120)
            print(f"[{last_tick}] error BUG {type(e).__name__}: {e}")
            log("loop", event="bug", tick=last_tick, error=repr(e))
        b.wait_tick()


if __name__ == "__main__":
    main()
