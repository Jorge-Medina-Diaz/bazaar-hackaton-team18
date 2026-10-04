"""Market value scorer: what every card is worth to us, what it trades for, and where the edge is.

    python -m agent.scorer                          # tables in the terminal
    python -m agent.scorer --html logs/market.html  # the same as a local page (private values: never publish it)
    python -m agent.scorer --watch 60 --html logs/market.html
    python -m agent.scorer --json                   # machine-readable, for the other engines
    python -m agent.scorer --recalibrate            # re-measure our set multipliers (a dozen value() calls)

Private numbers need BAZAAR_KEY (env or .env). Without it the scorer still prices the market, as a
neutral team (every multiplier 1.0).

Three prices per card, all in primas:
  ours    what one more copy is worth to us (next) and what giving one away costs us (keep)
  market  buy_at: the cheapest way to get one now (board ask + fee, or the cheapest open dealer's typical fill)
          sell_at: the best way to cash one now (board bid - fee, or the best-paying open dealer's typical bid)
          mv: the clearing estimate (team fills > board mid > dealer fills > book)
  dealers each priced on its own: our fills with it > every team's > its menu list price (a dealer that just
          opened, like El Chato, has no fills yet). Only dealers in /api/me `unlocked` set buy_at and sell_at.
  peers   what the card is worth to another team missing it: the six multipliers are the same for
          everyone, shuffled, so once we know ours we know the whole distribution of theirs

Edges: buy_edge = next - buy_at, sell_edge = sell_at - keep. Both score at our private values.
Public reads go through a keyless client so they never spend the team key's 5 requests per second.
"""
from __future__ import annotations
raise SystemExit("ARCHIVED by M18: pre-harness script that could reach the game without the Gate. Use the harness: python3 bazaar.py (see CLAUDE.md).")  # M18 guard

import argparse
import html
import json
import math
import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bazaar_sdk import Bazaar, BazaarError, _Http  # noqa: E402

LOGS = ROOT / "logs"
MULT_CACHE = LOGS / "multipliers.json"
FILLS_LOG = LOGS / "fills.jsonl"
PAGE_RARITIES = ("common", "uncommon", "rare")
RARITY_ORDER = ("common", "uncommon", "rare", "epic", "legendary")
RECENT = 8  # fills that count towards a median


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def median(xs, default=None):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else default


def menu_covers(item: dict, card: dict, released: bool) -> bool:
    """A menu line covers a card when the rarity matches and the card's set is on it ("released" or a list)."""
    if item.get("rarity") != card["rarity"] or not released:
        return False
    sets = item.get("sets", "released")
    return card["set"] in sets if isinstance(sets, list) else True


def venue_fee(venue: dict | None, price: int, cards: int = 1) -> int:
    """The accepting side pays ceil(price * bps + per_card * cards): a 12 P sale on El Rastro paid 2 P."""
    if not venue:
        return 0
    return math.ceil(price * venue.get("fee_bps", 0) / 10000 + venue.get("fee_per_card", 0) * cards)


# --------------------------------------------------------------------------- reading the world

class Snapshot:
    """Everything the scorer reads in one pass: public data keyless, private data with the team key."""

    def __init__(self, url: str, key: str | None):
        self.public = _Http(url, {}, 15.0, False, 3)
        self.team = Bazaar(url, key, wait_on_tick=False) if key else None
        self.catalog: dict = {}
        self.cards: dict[str, dict] = {}      # ref -> catalog card (+ "set")
        self.sets: dict[str, dict] = {}
        self.me: dict | None = None
        self.my_offer_ids: set[int] = set()
        self.my_threads: list[dict] | None = None  # ours, complete (the public feed forgets old deals)

    def get(self, path: str, query: dict | None = None):
        return self.public._call("GET", path, query=query)

    def refresh(self) -> None:
        if not self.catalog:
            self.catalog = self.get("/api/catalog")
        else:  # minted counts and releases move
            self.catalog = self.get("/api/catalog")
        self.cards, self.sets = {}, {}
        for s in self.catalog["sets"]:
            self.sets[s["id"]] = s
            for c in s["cards"]:
                self.cards[c["id"]] = {**c, "set": s["id"]}
        self.clock = self.get("/api/clock")
        self.events = self.get("/api/feed", {"limit": 1000}).get("events", [])
        self.venues = {v["venue"]: v for v in self.get("/api/venues").get("venues", []) if v.get("status") == "open"}
        self.boards = {}
        for vid in self.venues:
            try:
                self.boards[vid] = self.get(f"/api/venues/{vid}/offers").get("offers", [])
            except BazaarError:
                self.boards[vid] = []
        self.leaderboard = self.get("/api/leaderboard")
        self.dealers = self.get("/api/dealers").get("personas", [])
        if self.team:
            self.me = self.team.me()
            try:
                mine = self.team.my_offers()
                self.my_offer_ids = {o["id"] for k in ("open", "queued", "offers") for o in mine.get(k, []) or []
                                     if isinstance(o, dict) and o.get("maker") == self.me.get("team", self.me.get("id"))}
            except BazaarError:
                pass
            try:
                self.my_threads = self.team.my_threads().get("threads", [])
            except BazaarError:
                self.my_threads = None

    def released(self, ref: str) -> bool:
        return bool(self.sets[self.cards[ref]["set"]].get("released"))


# --------------------------------------------------------------------------- market history

def fills_from(events: list, cards: dict, packs: dict) -> list[dict]:
    """One row per item in each settlement; bundle prices split by book value."""
    out = []
    for e in events:
        if e.get("type") != "settlement":
            continue
        p = e["payload"]
        items, price = p.get("items") or [], p.get("price") or 0
        if not items or price <= 0 or len({(i["frm"], i["to"]) for i in items}) != 1:
            continue  # swaps and gifts carry no price
        books = [cards.get(i["ref"], {}).get("book") or packs.get(i["ref"], {}).get("expected_book") or 10 for i in items]
        dealer = p.get("persona")
        for i, bk in zip(items, books):
            out.append({
                "event": e["id"], "tick": p.get("tick", e.get("tick")), "ref": i["ref"], "kind": i.get("kind"),
                "rarity": i.get("rarity") or ("pack" if i.get("kind") == "pack" else None),
                "price": price * bk / sum(books), "venue": p.get("venue"), "dealer": dealer,
                "side": ("dealer_sells" if i["frm"] == dealer else "dealer_buys") if dealer else "team",
                "seller": i["frm"], "buyer": i["to"], "bundle": len(items),
            })
    return out


def merge_history(new: list[dict]) -> list[dict]:
    """The feed only reaches back ~500 events; keep every fill we ever saw in logs/fills.jsonl."""
    LOGS.mkdir(exist_ok=True)
    seen, rows = set(), []
    if FILLS_LOG.exists():
        for line in FILLS_LOG.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            seen.add((r["event"], r["ref"]))
            rows.append(r)
    fresh = [r for r in new if (r["event"], r["ref"]) not in seen]
    if fresh:
        with FILLS_LOG.open("a", encoding="utf-8") as f:
            for r in fresh:
                f.write(json.dumps(r) + "\n")
    return sorted(rows + fresh, key=lambda r: (r["tick"], r["event"]))


def dealer_quotes(events: list, cards: dict) -> dict:
    """Dealer asks and bids from every team's haggling, keyed (dealer, rarity) for cards and (dealer, pack id)
    for packs, with the opening and the final (walk-away) ones apart. Dealers price differently: never pool them."""
    q = defaultdict(lambda: {"open_ask": [], "final_ask": [], "open_bid": [], "final_bid": []})
    first = set()
    for e in events:
        if e.get("type") != "thread.message":
            continue
        p = e["payload"]
        o = p.get("offer") or {}
        if p.get("kind") != "persona" or p.get("sender") != p.get("with") or not o:
            continue
        dealer, opening = p["with"], p["thread"] not in first
        first.add(p["thread"])
        give, want = o.get("give") or {}, o.get("want") or {}
        if want.get("cash"):      # the dealer sells: "card:LAV-06" or "pack:sobre_barrio" in give.types
            t = ((give.get("types") or []) + [""])[0]
            key = t.removeprefix("pack:") if t.startswith("pack:") else cards.get(t.removeprefix("card:"), {}).get("rarity")
            if key:
                if opening:
                    q[(dealer, key)]["open_ask"].append(want["cash"])
                if o.get("final"):
                    q[(dealer, key)]["final_ask"].append(want["cash"])
        elif give.get("cash"):    # the dealer buys
            assets = want.get("assets") or []
            rarity = (assets or [{}])[0].get("rarity")
            if rarity:
                each = give["cash"] / len(assets)
                if opening:
                    q[(dealer, rarity)]["open_bid"].append(each)
                if o.get("final"):
                    q[(dealer, rarity)]["final_bid"].append(each)
    return q


def thread_deal(t: dict, cards: dict) -> dict | None:
    """One of our dealer threads that ended in a deal: side, item key (rarity, or pack id), the dealer's first
    price and the settled one. Negotiated = settled away from that first price (the unlock rule: a deal at
    the dealer's opening price does not count)."""
    if t.get("kind") != "persona" or t.get("status") != "deal":
        return None
    dealer, topic = t["with"], t.get("topic") or {}
    buy = topic.get("buy") or {}
    side = "dealer_sells" if buy else "dealer_buys"
    key = buy.get("pack") or cards.get(buy.get("card"), {}).get("rarity")
    first = settled = None
    for m in t.get("messages", []):
        o = m.get("offer") or {}
        cash = (o.get("want") or {}).get("cash") or (o.get("give") or {}).get("cash")
        if not cash:
            continue
        if first is None and o.get("maker") == dealer:
            first = cash
        if o.get("status") == "settled":
            settled = cash
            if key is None:  # a sale: the card is in the offer
                assets = (o.get("give") or {}).get("assets", []) + (o.get("want") or {}).get("assets", [])
                key = next((a.get("rarity") for a in assets if a.get("rarity")), None)
    if settled is None:
        return None
    return {"dealer": dealer, "side": side, "key": key, "first": first, "price": settled,
            "negotiated": first is None or settled != first}


def demand_from(events: list) -> dict[str, set]:
    """Who has asked for which card: dealer threads with a card topic, and want-lists on venues."""
    d = defaultdict(set)
    for e in events:
        p = e.get("payload") or {}
        if e.get("type") == "thread.opened":
            ref = ((p.get("topic") or {}).get("buy") or {}).get("card")
            if ref:
                d[ref].add(p.get("team"))
        elif e.get("type") == "offer.listed":
            for t in ((p.get("offer") or {}).get("want") or {}).get("types") or []:
                if t.startswith("card:"):
                    d[t[5:]].add(e.get("actor"))
    return d


# --------------------------------------------------------------------------- our private values

class Values:
    """Our value model. Multipliers are measured once with value() and cached; marginals and the
    page bonus follow the catalog's rules, so pricing a card never costs a request."""

    def __init__(self, snap: Snapshot, recalibrate: bool = False):
        rules = snap.catalog.get("values", {})
        self.marginals = rules.get("copy_marginals", [1.0, 0.25, 0.1])
        self.page_bonus = rules.get("page_bonus", 0.25)
        self.master_bonus = rules.get("master_bonus", 0.1)
        self.snap = snap
        self.counts: dict[str, int] = defaultdict(int)
        self.copy_values: dict[str, list[float]] = defaultdict(list)
        self.assets: dict[str, list[dict]] = defaultdict(list)
        if snap.me:
            for a in snap.me.get("assets", []):
                if a.get("kind") == "card":
                    self.counts[a["ref"]] += 1
                    self.copy_values[a["ref"]].append(float(a.get("your_value") or 0))
                    self.assets[a["ref"]].append(a)
        self.mult, self.calibration = self._multipliers(recalibrate)

    def _multipliers(self, recalibrate: bool):
        sets = list(self.snap.sets)
        if not self.snap.team:
            return {s: 1.0 for s in sets}, {"source": "neutral (no key)"}
        affinity = self.snap.me.get("affinity", {})
        if all(type(affinity.get(s)) in (int, float) and math.isfinite(affinity[s])
               and affinity[s] > 0 for s in sets):
            return {s: float(affinity[s]) for s in sets}, {"source": "me.affinity"}
        team = self.snap.me.get("team") or self.snap.me.get("id") or self.snap.me.get("name")
        if MULT_CACHE.exists() and not recalibrate:
            cache = json.loads(MULT_CACHE.read_text(encoding="utf-8"))
            if cache.get("team") == team and all(s in cache["mult"] for s in sets if self.snap.sets[s].get("released")):
                return {s: cache["mult"].get(s, 1.0) for s in sets}, cache
        mult, checks = {}, []
        for s in sets:
            ests = []
            refs = sorted((r for r, c in self.snap.cards.items() if c["set"] == s),
                          key=lambda r: (self.counts[r] > 0, self.snap.cards[r]["book"]))
            for ref in refs[:3]:  # unheld cards first: their value is book * mult, no marginal to undo
                try:
                    v = float(self.snap.team.value(ref)["your_value"])
                except BazaarError:
                    continue
                k = self.counts[ref]
                factor = self.marginals[min(k, len(self.marginals) - 1)]
                ests.append(v / (self.snap.cards[ref]["book"] * factor))
                checks.append({"ref": ref, "held": k, "api": v})
                time.sleep(0.25)
            if ests:
                mult[s] = round(median(ests), 4)
        cache = {"team": team, "mult": mult, "checks": checks, "tick": self.snap.clock.get("tick"),
                 "source": "measured with value()"}
        LOGS.mkdir(exist_ok=True)
        MULT_CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
        return {s: mult.get(s, 1.0) for s in sets}, cache

    def m(self, ref: str) -> float:
        return self.mult.get(self.snap.cards[ref]["set"], 1.0)

    def base(self, ref: str) -> float:
        return self.snap.cards[ref]["book"] * self.m(ref)

    def page_refs(self, set_id: str) -> list[str]:
        return [c["id"] for c in self.snap.sets[set_id]["cards"] if c["rarity"] in PAGE_RARITIES]

    def page_value(self, set_id: str) -> float:
        return sum(self.base(r) for r in self.page_refs(set_id))

    def missing(self, set_id: str) -> list[str]:
        return [r for r in self.page_refs(set_id) if self.counts[r] == 0]

    def next_value(self, ref: str) -> float:
        """One more copy: its marginal, plus the page bonus if it is the last card the page lacks."""
        k = self.counts[ref]
        v = self.base(ref) * self.marginals[min(k, len(self.marginals) - 1)]
        s = self.snap.cards[ref]["set"]
        if k == 0 and self.missing(s) == [ref]:
            v += self.page_bonus * self.page_value(s)
        return v

    def keep_value(self, ref: str) -> float:
        """What giving one copy away costs us: the least valuable copy, plus a broken page bonus."""
        k = self.counts[ref]
        if k == 0:
            return 0.0
        v = min(self.copy_values[ref]) if self.copy_values[ref] else self.base(ref) * self.marginals[min(k - 1, 2)]
        s = self.snap.cards[ref]["set"]
        if k == 1 and self.snap.cards[ref]["rarity"] in PAGE_RARITIES and not self.missing(s):
            v += self.page_bonus * self.page_value(s)
        return v

    def peer(self, ref: str) -> dict:
        """Value of a first copy to another team: the same multipliers, shuffled."""
        ms = sorted(self.mult.values())
        if not self.snap.team:
            return {"top": None, "mean": None}
        bk = self.snap.cards[ref]["book"]
        return {"top": bk * ms[-1], "mean": bk * statistics.mean(ms)}

    def bundle_delta(self, received: list[str], given: list[str]) -> float:
        """Atomic collection change: quantities and page bonuses evaluated together.

        Master-page transitions need API confirmation; do not guess their formula.
        """
        before = dict(self.counts)
        after = defaultdict(int, before)
        for ref in given:
            if ref not in self.snap.cards or after[ref] < 1:
                raise ValueError("Missing card or insufficient copies")
            after[ref] -= 1
        for ref in received:
            if ref not in self.snap.cards:
                raise ValueError("Unknown card")
            after[ref] += 1
        changed = set(received + given)
        total = 0.0
        for ref in changed:
            old, new = before.get(ref, 0), after[ref]
            lo, hi = sorted((old, new))
            delta = self.base(ref) * sum(self.marginals[min(k, len(self.marginals) - 1)]
                                        for k in range(lo, hi))
            total += delta if new >= old else -delta
        for s in {self.snap.cards[r]["set"] for r in changed}:
            refs = self.page_refs(s)
            was = bool(refs) and all(before.get(r, 0) > 0 for r in refs)
            now = bool(refs) and all(after[r] > 0 for r in refs)
            masters = [c["id"] for c in self.snap.sets[s]["cards"]
                       if c["rarity"] in ("epic", "legendary")]
            old_master = was and bool(masters) and all(before.get(r, 0) > 0 for r in masters)
            new_master = now and bool(masters) and all(after[r] > 0 for r in masters)
            if old_master != new_master:
                raise ValueError("Master bonus transition requires API validation")
            total += (int(now) - int(was)) * self.page_bonus * self.page_value(s)
        return total


# --------------------------------------------------------------------------- scoring

class Scorer:
    def __init__(self, snap: Snapshot, values: Values, history: list[dict]):
        self.snap, self.v, self.hist = snap, values, history
        self.rastro = snap.venues.get("rastro")
        self.quotes = dealer_quotes(snap.events, snap.cards)
        self.demand = demand_from(snap.events)
        self.by_ref = defaultdict(lambda: defaultdict(list))
        self.by_rarity = defaultdict(lambda: defaultdict(list))
        me = snap.me or {}
        self.team_id = me.get("id") or me.get("team")
        # Dealers in play, and the ones we may trade with now (a new dealer opens to the teams that earned it
        # first, to everyone after a head start). Without a key we price as if every dealer were open.
        self.active = {d["id"]: d for d in snap.dealers if d.get("status") == "active" and d.get("enabled", True)}
        self.can_trade = set(self.active) & set(me["unlocked"]) if "unlocked" in me else set(self.active)
        # Fills per dealer, keyed (dealer, side, ref) and (dealer, side, rarity); ours apart, because some
        # dealers price by how much they like you (El Chato: "friendly prices. If I like you.").
        self.dfills, self.dfills_ours = defaultdict(list), defaultdict(list)
        for f in history:
            self.by_ref[f["ref"]][f["side"]].append(f["price"])
            self.by_rarity[f["rarity"]][f["side"]].append(f["price"])
            if f.get("dealer"):
                mine = self.team_id is not None and self.team_id in (f["buyer"], f["seller"])
                for k in {f["ref"], f["rarity"]}:
                    self.dfills[(f["dealer"], f["side"], k)].append(f["price"])
                    if mine:
                        self.dfills_ours[(f["dealer"], f["side"], k)].append(f["price"])
        self.asks, self.bids = defaultdict(list), defaultdict(list)
        for vid, offers in snap.boards.items():
            for o in offers:
                if o["id"] in snap.my_offer_ids or o.get("status") != "open":
                    continue
                give, want = o["give"], o["want"]
                if len(give.get("assets") or []) == 1 and not give.get("cash") and want.get("cash") and not want.get("types") and not want.get("assets"):
                    a = give["assets"][0]
                    self.asks[a["ref"]].append({"offer": o["id"], "venue": vid, "price": want["cash"],
                                                "cost": want["cash"] + venue_fee(snap.venues.get(vid), want["cash"])})
                elif give.get("cash") and len(want.get("types") or []) == 1 and not want.get("cash") and not give.get("assets"):
                    ref = want["types"][0].removeprefix("card:")
                    self.bids[ref].append({"offer": o["id"], "venue": vid, "price": give["cash"],
                                           "net": give["cash"] - venue_fee(snap.venues.get(vid), give["cash"])})

    def recent(self, xs):
        return median(xs[-RECENT:])

    def menu_item(self, dealer: str, side: str, ref: str) -> dict | None:
        """The line of a dealer's menu under which it sells ("dealer_sells") or buys this card or pack."""
        menu = self.active[dealer].get("menu", {}).get("sells" if side == "dealer_sells" else "buys", [])
        if ref in self.snap.cards:
            c = self.snap.cards[ref]
            return next((i for i in menu if menu_covers(i, c, self.snap.released(ref))), None)
        return next((i for i in menu if i.get("pack") == ref), None)

    def dealer_estimate(self, dealer: str, side: str, ref: str):
        """What a deal with one dealer for this card or pack typically settles at, and where the number
        comes from: our own fills, then every team's for the card, then for its rarity, then the menu's
        list price (a dealer that just opened has no fills yet). Packs never fall back to a rarity."""
        if self.menu_item(dealer, side, ref) is None:
            return None, None
        rarity = self.snap.cards[ref]["rarity"] if ref in self.snap.cards else None
        for pool, label, need_ref in ((self.dfills_ours, "our fills", 1), (self.dfills, "fills", 2)):
            for k, need in ((ref, need_ref), (rarity, 1)):
                xs = pool.get((dealer, side, k), []) if k else []
                if len(xs) >= need:
                    return self.recent(xs), f"{dealer} {label}"
        price = self.menu_item(dealer, side, ref).get("list_price")
        return (price, f"{dealer} list") if price else (None, None)

    def dealer_price(self, ref: str, side: str):
        """The best dealer we can trade with now for this card: (price, dealer, source), or None."""
        quotes = [(p, d, src) for d in sorted(self.can_trade) for p, src in [self.dealer_estimate(d, side, ref)]
                  if p is not None]
        if not quotes:
            return None
        return min(quotes) if side == "dealer_sells" else max(quotes, key=lambda q: q[0])

    def card(self, ref: str) -> dict:
        c, v = self.snap.cards[ref], self.v
        ask = min(self.asks[ref], key=lambda a: a["cost"], default=None)
        bid = max(self.bids[ref], key=lambda b: b["net"], default=None)
        d_sell, d_buy = self.dealer_price(ref, "dealer_sells"), self.dealer_price(ref, "dealer_buys")
        buy_opts = [(ask["cost"], f"board #{ask['offer']}")] if ask else []
        if d_sell:
            buy_opts.append(d_sell[:2])
        sell_opts = [(bid["net"], f"bid #{bid['offer']}")] if bid else []
        if d_buy:
            sell_opts.append(d_buy[:2])
        buy_at, buy_via = min(buy_opts, default=(None, "no seller"))
        sell_at, sell_via = max(sell_opts, default=(None, "no buyer"))
        team = self.by_ref[ref]["team"]
        if team:
            mv, src = self.recent(team), f"teams ({len(team)})"
        elif ask and bid:
            mv, src = (ask["price"] + bid["price"]) / 2, "board mid"
        elif d_sell:
            mv, src = d_sell[0], d_sell[2]
        else:
            mv, src = c["book"], "book"
        nxt, keep, peer = v.next_value(ref), v.keep_value(ref), v.peer(ref)
        row = {
            "ref": ref, "name": c["name"], "set": c["set"], "rarity": c["rarity"], "book": c["book"],
            "minted": c.get("minted"), "print_run": c.get("print_run"), "held": v.counts[ref],
            "mult": v.m(ref), "next": nxt, "keep": keep, "peer_top": peer["top"], "peer_mean": peer["mean"],
            "mv": mv, "mv_src": src, "buy_at": buy_at, "buy_via": buy_via, "sell_at": sell_at, "sell_via": sell_via,
            "buy_edge": None if buy_at is None else nxt - buy_at,
            "sell_edge": None if (sell_at is None or not v.counts[ref]) else sell_at - keep,
            "demand": sorted(t for t in self.demand.get(ref, ()) if t), "released": self.snap.released(ref),
        }
        row["ask"] = self.suggest_ask(row, d_sell[0] if d_sell else None)
        row["action"] = self.action(row)
        return row

    def suggest_ask(self, row: dict, dealer_price):
        """Where to list a copy: near what the best-placed peer would pay, never above what the cheapest
        dealer charges all-in (nobody pays a team more), never below what the copy is worth to us."""
        if not row["held"]:
            return None
        target = 0.85 * row["peer_top"] if row["peer_top"] else row["mv"]
        if dealer_price and self.rastro:
            cap = (dealer_price - self.rastro.get("fee_per_card", 0)) / (1 + self.rastro.get("fee_bps", 0) / 10000)
            target = min(target, cap)
        return max(math.floor(target), math.ceil(row["keep"] + 1))

    def action(self, r: dict) -> str:
        if r["held"]:
            if r["sell_edge"] is not None and r["sell_edge"] >= 1:
                return f"SELL to {r['sell_via']} (+{r['sell_edge']:.0f})"
            if r["ask"] is not None and r["ask"] > r["keep"] + 1 and (r["held"] > 1 or r["mult"] < 1):
                return f"LIST @{r['ask']}"
            return "KEEP"
        if r["buy_edge"] is not None and r["buy_edge"] >= 2:
            return f"BUY via {r['buy_via']} (+{r['buy_edge']:.0f})"
        return ""

    def pull_values(self) -> dict:
        """What one pull of each rarity is worth to us: the mean next-copy value over released cards with
        copies left to mint. A sold-out rarity gives the next one down (the rules), so epic and legendary
        slots in the better packs lose value as their 9 and 3 copies per card get minted."""
        left = {}
        for rar in RARITY_ORDER:
            vals = [self.v.next_value(r) for r, c in self.snap.cards.items()
                    if c["rarity"] == rar and self.snap.released(r)
                    and (c.get("minted") is None or c.get("print_run") is None or c["minted"] < c["print_run"])]
            left[rar] = statistics.mean(vals) if vals else None
        out, below = {}, 0.0
        for rar in RARITY_ORDER:
            below = left[rar] if left[rar] is not None else below
            out[rar] = below
        return out

    def pack_ev(self) -> list[dict]:
        """One row per pack and seller (every active dealer that sells it, and teams), priced from the
        dealer's fills or its list price. A pack with no seller yet is still scored, so the day a new dealer
        brings it we already know what it is worth to us."""
        out = []
        pull = self.pull_values()
        team_fills = defaultdict(list)
        for f in self.hist:
            if f["kind"] == "pack" and not f.get("dealer"):
                team_fills[f["ref"]].append(f["price"])
        for p in self.snap.catalog.get("packs", []):
            ev = sum(prob * pull.get(rar, 0.0) for slot in p["slots"] for rar, prob in slot.items())
            base = {"pack": p["id"], "name": p["name"], "expected_book": p["expected_book"], "ev_to_us": ev}
            sellers = [(d, self.menu_item(d, "dealer_sells", p["id"])) for d in sorted(self.active)]
            for d, item in sellers:
                if item is None:
                    continue
                price, src = self.dealer_estimate(d, "dealer_sells", p["id"])
                out.append({**base, "seller": d, "can_trade": d in self.can_trade, "opening_ask": item.get("opening_ask"),
                            "per_hour": item.get("per_team_per_hour"), "typical_price": price, "price_src": src,
                            "edge": None if price is None else ev - price})
            if team_fills[p["id"]]:
                price = self.recent(team_fills[p["id"]])
                out.append({**base, "seller": "teams", "can_trade": True, "opening_ask": None, "per_hour": None,
                            "typical_price": price, "price_src": f"teams ({len(team_fills[p['id']])})", "edge": ev - price})
            if not any(r["pack"] == p["id"] for r in out):
                out.append({**base, "seller": None, "can_trade": False, "opening_ask": None, "per_hour": None,
                            "typical_price": None, "price_src": "nobody sells it yet", "edge": None})
        return out

    def ladder(self) -> list[dict]:
        """Every dealer, announced or in play: our deals with it, an estimate of the share of its price range
        each deal captured (the ladder counts the best three per level, a missing one as zero, higher levels
        weigh more), and how it unlocks. The capture is an estimate: we see the range other teams reached,
        not the dealer's secret limits."""
        threads = getattr(self.snap, "my_threads", None)
        if threads is not None:  # exact: our own threads, the dealer's first price included
            ours = [x for x in (thread_deal(t, self.snap.cards) for t in threads) if x]
        else:  # no key: what the feed still shows, with the median opening quote as the first price
            ours = []
            for f in self.hist:
                if f.get("dealer") and self.team_id in (f["buyer"], f["seller"]):
                    key = f["ref"] if f["kind"] == "pack" else f["rarity"]
                    q = self.quotes.get((f["dealer"], key)) or {}
                    first = median(q.get("open_ask" if f["side"] == "dealer_sells" else "open_bid", []))
                    ours.append({"dealer": f["dealer"], "side": f["side"], "key": key, "first": first,
                                 "price": f["price"], "negotiated": first is None or f["price"] != first})
        out = []
        for d in sorted(self.snap.dealers, key=lambda d: (d.get("level") or 99, d["id"])):
            did, unlock = d["id"], d.get("unlock") or {}
            deals = [x for x in ours if x["dealer"] == did]
            caps = []
            for x in deals:
                xs = self.dfills.get((did, x["side"], x["key"]), [])
                q = self.quotes.get((did, x["key"])) or {}
                if x["side"] == "dealer_sells":
                    hi, lo = max(xs + q.get("open_ask", []) + [x["first"] or 0]), min(xs + [x["price"]])
                    cap = (hi - x["price"]) / (hi - lo) if hi > lo else None
                else:
                    lo, hi = min(xs + q.get("open_bid", []) + [x["first"] or x["price"]]), max(xs + [x["price"]])
                    cap = (x["price"] - lo) / (hi - lo) if hi > lo else None
                if cap is not None:
                    caps.append(max(0.0, min(1.0, cap)))
            negotiated = sum(x["negotiated"] for x in deals)
            prev = unlock.get("early_deals_with")
            out.append({
                "dealer": did, "name": d.get("name"), "status": d.get("status"), "level": d.get("level"),
                "teaser": d.get("teaser"), "traits": d.get("traits"), "can_trade": did in self.can_trade,
                "deals": len(deals), "negotiated": negotiated, "best3": sorted(caps, reverse=True)[:3],
                "open_slots": max(0, 3 - len(deals)), "unlock_after": prev,
                "unlock_need": unlock.get("early_min_deals"), "open_to_all": d.get("open_to_all"),
                "deals_per_hour": (d.get("menu") or {}).get("deals_per_team_per_hour"),
            })
        return out

    def pages(self, rows: dict) -> list[dict]:
        out = []
        for s, meta in self.snap.sets.items():
            refs = self.v.page_refs(s)
            missing = self.v.missing(s)
            unsourced = [r for r in missing if rows[r]["buy_at"] is None]
            # no seller (rares, at level 1): price them at their market value, and say so
            cost = sum(rows[r]["buy_at"] if rows[r]["buy_at"] is not None else rows[r]["mv"] for r in missing)
            gain = (sum(self.v.base(r) for r in missing) + self.v.page_bonus * self.v.page_value(s)) if missing else 0
            out.append({"set": s, "name": meta["name"], "released": meta.get("released"), "mult": self.v.mult.get(s),
                        "have": len(refs) - len(missing), "of": len(refs), "missing": missing, "unsourced": unsourced,
                        "bonus": self.v.page_bonus * self.v.page_value(s), "cost": cost, "gain": gain,
                        "net": gain - cost})
        return sorted(out, key=lambda p: -(p["mult"] or 0))

    def board_offers(self) -> list[dict]:
        """Every open offer on every venue, scored as if we accepted it now, at our values."""
        out = []
        me = self.snap.me or {}
        team = me.get("id") or me.get("team")
        owned = {a["id"]: a for a in me.get("assets", []) if a.get("kind") == "card"}
        own_venue = me.get("venue")
        if isinstance(own_venue, dict):
            own_venue = own_venue.get("venue") or own_venue.get("id")
        for vid, offers in self.snap.boards.items():
            if own_venue and vid == own_venue:
                continue
            for o in offers:
                if (o["id"] in self.snap.my_offer_ids or o.get("status") != "open"
                    or (team and o.get("maker") == team)
                    or (o.get("to") and team and o["to"] != team)
                    or (o.get("expires_tick") is not None and o["expires_tick"] < self.snap.clock["tick"])):
                    continue
                give, want = o["give"], o["want"]
                incoming = give.get("assets") or []
                requested = want.get("assets") or []
                types = want.get("types") or []
                if (give.get("types") or any(a.get("kind") != "card" or type(a.get("id")) is not int
                                             or a["id"] <= 0 for a in incoming)
                    or any(not t.startswith("card:") for t in types)):
                    continue  # Scoring is for known, concrete incoming cards.
                ids = [a["id"] if isinstance(a, dict) else a for a in requested]
                if len(ids) != len(set(ids)) or any(i not in owned or owned[i].get("locked") for i in ids):
                    continue
                get_refs = [a["ref"] for a in incoming]
                pay_refs = [owned[i]["ref"] for i in ids]
                selected = list(ids)
                for kind in types:
                    ref = kind.removeprefix("card:")
                    candidates = [i for i, a in owned.items() if a["ref"] == ref
                                  and i not in selected and not a.get("locked")]
                    if not candidates:
                        break
                    selected.append(min(candidates))
                    pay_refs.append(ref)
                else:
                    if len(incoming) != len({a.get("id") for a in incoming}):
                        continue
                    cash = want.get("cash") or give.get("cash") or 0
                    fee = venue_fee(self.snap.venues.get(vid), cash, len(get_refs) + len(pay_refs))
                    cash_out, cash_in = want.get("cash") or 0, give.get("cash") or 0
                    if me.get("cash") is not None and me["cash"] + cash_in < cash_out + fee:
                        continue
                    try:
                        delta = self.v.bundle_delta(get_refs, pay_refs)
                    except ValueError:
                        continue
                    out.append({"offer": o["id"], "venue": vid, "gets": get_refs, "gives": pay_refs,
                                "payment_assets": selected, "cash_in": cash_in, "cash_out": cash_out,
                                "fee": fee, "surplus": delta + cash_in - cash_out - fee,
                                "expires": o.get("expires_tick")})
        return sorted(out, key=lambda x: -x["surplus"])

    def run(self) -> dict:
        rows = {r: self.card(r) for r in self.snap.cards}
        dealer = []  # price levels per dealer and item (rarity, or pack id): dealers price differently
        packs = [p["id"] for p in self.snap.catalog.get("packs", [])]
        for d in sorted(self.active):
            menu = self.active[d].get("menu", {})
            for key in (*RARITY_ORDER, *packs):
                sells = next((i for i in menu.get("sells", []) if key in (i.get("rarity"), i.get("pack"))), None)
                buys = next((i for i in menu.get("buys", []) if i.get("rarity") == key), None)
                q = self.quotes.get((d, key)) or {}
                s_all, b_all = self.dfills.get((d, "dealer_sells", key), []), self.dfills.get((d, "dealer_buys", key), [])
                if not (sells or buys or s_all or b_all or q):
                    continue
                dealer.append({
                    "dealer": d, "item": key, "list": (sells or {}).get("list_price"),
                    "opening_ask": (sells or {}).get("opening_ask") or median(q.get("open_ask", [])),
                    "final_ask_min": min(q.get("final_ask", []), default=None),
                    "sells_median": self.recent(s_all), "sells_ours": self.recent(self.dfills_ours.get((d, "dealer_sells", key), [])),
                    "buys_median": self.recent(b_all), "final_bid_max": max(q.get("final_bid", []), default=None),
                    "team_median": self.recent(self.by_rarity[key]["team"]) if key in RARITY_ORDER else None,
                    "fills": len(s_all) + len(b_all)})
        me = self.snap.me or {}
        held_value = me.get("collection_value", sum(sum(v) for v in self.v.copy_values.values()))
        return {
            "tick": self.snap.clock.get("tick"), "t_hours": self.snap.clock.get("t_hours"),
            "team": me.get("team") or me.get("name"), "cash": me.get("cash"), "level": me.get("level"),
            "score": me.get("score"), "held_value": held_value, "mult": self.v.mult, "calibration": self.v.calibration,
            "cards": rows, "dealer": dealer, "dealers": self.ladder(), "packs": self.pack_ev(), "pages": self.pages(rows),
            "offers": self.board_offers(),
            "rivals": [{k: t.get(k) for k in ("team", "rank", "score", "negotiating", "market", "album_filled",
                                               "album_slots", "pages_complete", "deals", "venue")}
                       for t in self.snap.leaderboard.get("teams", [])],
        }


# --------------------------------------------------------------------------- rendering

def f0(x, signed=False):
    if x is None:
        return "-"
    return f"{x:+.0f}" if signed else f"{x:.0f}"


def short(refs: list[str]) -> str:
    """LAV-03 LAV-09 -> #03 #09 (the set is in its own column)."""
    return " ".join("#" + r.split("-")[1] for r in refs)


def table(rows: list[list], head: list[str]) -> str:
    cells = [head] + [[str(c) for c in r] for r in rows]
    w = [max(len(r[i]) for r in cells) for i in range(len(head))]
    line = lambda r: "  ".join(c.ljust(w[i]) if i < 3 else c.rjust(w[i]) for i, c in enumerate(r))
    return "\n".join([line(head), "  ".join("-" * x for x in w)] + [line(r) for r in cells[1:]])


def sections(rep: dict) -> list[tuple[str, list[str], list[list]]]:
    cards = rep["cards"].values()
    held = sorted((c for c in cards if c["held"]), key=lambda c: -(c["sell_edge"] or -99))
    buys = sorted((c for c in cards if not c["held"] and c["released"] and c["buy_edge"] is not None),
                  key=lambda c: -c["buy_edge"])[:15]
    out = [
        ("Our cards: keep, sell or list", ["card", "name", "rarity", "held", "x", "keep", "next", "mv", "sell_at", "via", "edge", "ask", "action"],
         [[c["ref"], c["name"][:22], c["rarity"], c["held"], f"{c['mult']:.2f}", f0(c["keep"]), f0(c["next"]), f0(c["mv"]),
           f0(c["sell_at"]), c["sell_via"], f0(c["sell_edge"], True), f0(c["ask"]), c["action"]] for c in held]),
        ("What to buy: next copy's value minus what it costs now", ["card", "name", "rarity", "x", "next", "buy_at", "via", "edge", "minted", "asked by"],
         [[c["ref"], c["name"][:22], c["rarity"], f"{c['mult']:.2f}", f0(c["next"]), f0(c["buy_at"]), c["buy_via"],
           f0(c["buy_edge"], True), f"{c['minted']}/{c['print_run']}", len(c["demand"])] for c in buys]),
        ("Pages: what completing each one costs and earns (no seller: priced at mv, must come from a team)",
         ["set", "name", "mult", "have", "missing", "no seller", "cost", "gain", "net"],
         [[p["set"], p["name"], f"{p['mult']:.2f}", f"{p['have']}/{p['of']}", short(p["missing"]) or "complete",
           short(p["unsourced"]) or "-", f0(p["cost"]), f0(p["gain"]), f0(p["net"], True)] if p["released"] else
          [p["set"], p["name"], f"{p['mult']:.2f}", "-", "not released yet", "-", "-", f0(p["gain"]), "-"] for p in rep["pages"]]),
        ("Board offers, scored as if we accepted now", ["offer", "venue", "gets", "gives", "cash in", "cash out", "fee", "surplus", "expires"],
         [[o["offer"], o["venue"], " ".join(o["gets"]) or "-", " ".join(o["gives"]) or "-", o["cash_in"], o["cash_out"],
           o["fee"], f0(o["surplus"], True), o["expires"]] for o in rep["offers"][:15]]),
        ("Dealers: ladder (best 3 deals per level count, higher levels weigh more) and unlocks",
         ["dealer", "status", "level", "trade", "deals", "negotiated", "best 3 capture (est.)", "open slots", "unlock / teaser"],
         [[d["dealer"], d["status"], d["level"] or "-", "yes" if d["can_trade"] else "no", d["deals"], d["negotiated"],
           " ".join(f"{c:.0%}" for c in d["best3"]) or "-", d["open_slots"], unlock_note(d, rep["dealers"])] for d in rep["dealers"]]),
        ("Packs: EV to us vs price, per seller (no seller yet: scored anyway, for the next dealer)",
         ["pack", "name", "seller", "book EV", "EV to us", "open ask", "price", "from", "edge", "/hour"],
         [[p["pack"], p["name"], (p["seller"] or "-") + ("" if p["can_trade"] or not p["seller"] else " (locked)"),
           f0(p["expected_book"]), f0(p["ev_to_us"]), f0(p["opening_ask"]), f0(p["typical_price"]), p["price_src"],
           f0(p["edge"], True), p["per_hour"] or "-"] for p in sorted(rep["packs"], key=lambda p: -(p["edge"] if p["edge"] is not None else -1e9))]),
        ("Price levels per dealer (all teams' haggles; ours apart: some dealers price by how they like you)",
         ["dealer", "item", "", "list", "open ask", "final ask min", "sells", "sells us", "buys", "final bid max", "teams", "fills"],
         [[d["dealer"], d["item"], "", f0(d["list"]), f0(d["opening_ask"]), f0(d["final_ask_min"]), f0(d["sells_median"]),
           f0(d["sells_ours"]), f0(d["buys_median"]), f0(d["final_bid_max"]), f0(d["team_median"]), d["fills"]] for d in rep["dealer"]]),
        ("Rivals (public board)", ["team", "rank", "score", "neg", "mkt", "album", "pages", "deals"],
         [[t["team"], t["rank"], t["score"], t["negotiating"], t["market"], f"{t['album_filled']}/{t['album_slots']}",
           t["pages_complete"], t["deals"]] for t in rep["rivals"]]),
    ]
    return out


def unlock_note(d: dict, dealers: list[dict]) -> str:
    """How a dealer opens for us. An announced one shows only its teaser; the rules say a dealer opens early
    to teams with a few negotiated deals with the one before, so show our count with the top dealer in play."""
    if d["status"] == "announced":
        prev = max((x for x in dealers if x["status"] == "active"), key=lambda x: x["level"] or 0, default=None)
        need = (prev or {}).get("unlock_need") or 3
        mine = f" · likely needs {need} negotiated with {prev['dealer']}: we have {prev['negotiated']}" if prev else ""
        return f"{d['teaser'] or ''}{mine}"
    if d["can_trade"]:
        return f"open to us · {d['deals_per_hour'] or '?'} deals/team/hour"
    if d["unlock_after"]:
        prev = next((x for x in dealers if x["dealer"] == d["unlock_after"]), {})
        return (f"locked: {d['unlock_need']} negotiated with {d['unlock_after']} (we have {prev.get('negotiated', 0)})"
                + ("; open to all now" if d["open_to_all"] else "; opens to all after the head start"))
    return "locked"


def header(rep: dict) -> str:
    s = rep.get("score") or {}
    mult = "  ".join(f"{k} {v:.2f}" for k, v in sorted(rep["mult"].items(), key=lambda kv: -kv[1]))
    who = f"{rep['team']}: {rep['cash']} P, level {rep['level']}, cards worth {rep['held_value']:.0f} P, score {s.get('score', '-')} (rank {s.get('rank', '-')})" \
        if rep["team"] else "No BAZAAR_KEY: market view as a neutral team (every multiplier 1.0)"
    dealers = "  ".join(f"{d['dealer']} " + (f"L{d['level']} {'open' if d['can_trade'] else 'LOCKED'}" if d["status"] == "active"
                                             else d["status"]) for d in rep.get("dealers", []))
    return (f"tick {rep['tick']} (game hour {rep['t_hours']})  |  {who}\nmultipliers: {mult}  [{rep['calibration'].get('source')}]"
            f"\ndealers: {dealers}")


def dealer_changes(before: dict, rep: dict) -> list[str]:
    """What changed among the dealers since the last pass: a new one announced, activated, opened to us."""
    out, first_pass = [], not before
    for d in rep.get("dealers", []):
        now = (d["status"], d["can_trade"])
        if first_pass:
            pass
        elif d["dealer"] in before and before[d["dealer"]] != now:
            out.append(f"DEALER {d['name'] or d['dealer']}: {before[d['dealer']][0]} -> {d['status']}"
                       + (f", level {d['level']}" if d["level"] else "") + (", OPEN TO US" if d["can_trade"] else ", locked for us")
                       + f". New prices from the menu until fills arrive; check /api/levels and agent/dealers.py.")
        elif d["dealer"] not in before:
            out.append(f"DEALER announced: {d['name'] or d['dealer']} {d['teaser'] or ''}")
        before[d["dealer"]] = now
    return out


def render_text(rep: dict) -> str:
    parts = [header(rep)]
    for title, head, rows in sections(rep):
        parts.append(f"\n== {title}\n" + (table(rows, head) if rows else "(none)"))
    return "\n".join(parts)


CSS = """
:root{--bg:#f7f5f0;--fg:#1d1b18;--mut:#6b665d;--line:#e2ddd2;--card:#fff;--pos:#1a7f4b;--neg:#b3261e;--acc:#c2410c}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#15140f;--fg:#ece8df;--mut:#9a948a;--line:#2e2b25;--card:#1d1c17;--pos:#4ade80;--neg:#f87171;--acc:#fb923c}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 ui-sans-serif,system-ui,sans-serif;margin:0;padding:24px 16px}
main{max-width:1200px;margin:auto}h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:28px 0 8px;color:var(--acc)}
.meta{color:var(--mut);font-size:13px;white-space:pre-wrap}.wrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:5px 9px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th{color:var(--mut);font-weight:600;font-size:12px}th:nth-child(-n+3),td:nth-child(-n+3){text-align:left}tr:last-child td{border-bottom:0}
.pos{color:var(--pos);font-weight:600}.neg{color:var(--neg)}
"""


def render_html(rep: dict, refresh: int | None) -> str:
    def cell(v):
        s = html.escape(str(v))
        cls = "pos" if s.startswith("+") or s.startswith(("SELL", "BUY", "LIST")) else "neg" if s.startswith("-") and len(s) > 1 else ""
        return f'<td class="{cls}">{s}</td>'
    body = [f"<h1>Team 18 · market value</h1><div class='meta'>{html.escape(header(rep))}</div>"]
    for title, head, rows in sections(rep):
        body.append(f"<h2>{html.escape(title)}</h2>")
        if not rows:
            body.append("<p class='meta'>(none)</p>")
            continue
        body.append("<div class='wrap'><table><tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in head) + "</tr>"
                    + "".join("<tr>" + "".join(cell(v) for v in r) + "</tr>" for r in rows) + "</table></div>")
    meta = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    return (f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"{meta}<title>Market value</title><style>{CSS}</style></head><body><main>{''.join(body)}</main></body></html>")


# --------------------------------------------------------------------------- main

def score_once(snap: Snapshot, recalibrate: bool) -> dict:
    snap.refresh()
    history = merge_history(fills_from(snap.events, snap.cards, {p["id"]: p for p in snap.catalog.get("packs", [])}))
    return Scorer(snap, Values(snap, recalibrate), history).run()


def main() -> None:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html", help="also write a local HTML page (it holds private values: keep it local)")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--watch", type=int, help="refresh every N seconds (min 30)")
    ap.add_argument("--recalibrate", action="store_true", help="re-measure set multipliers with value()")
    ap.add_argument("--public", action="store_true", help="ignore BAZAAR_KEY: neutral market view")
    args = ap.parse_args()
    key = None if args.public else os.environ.get("BAZAAR_KEY")
    snap = Snapshot(os.environ.get("BAZAAR_URL", "https://bazaar.causaprima.ai"), key)
    recal = args.recalibrate
    seen = {}  # dealer -> (status, can_trade), to shout when one opens
    while True:
        try:
            rep = score_once(snap, recal)
            recal = False
            for line in dealer_changes(seen, rep):
                print(f"\a[scorer] *** {line}", file=sys.stderr)
            if args.json:
                print(json.dumps(rep, default=str))
            else:
                print(render_text(rep))
            if args.html:
                Path(args.html).parent.mkdir(parents=True, exist_ok=True)
                Path(args.html).write_text(render_html(rep, max(30, args.watch) if args.watch else None), encoding="utf-8")
        except BazaarError as e:
            print(f"[scorer] {e}", file=sys.stderr)
        if not args.watch:
            break
        time.sleep(max(30, args.watch))


if __name__ == "__main__":
    main()
