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
  market  buy_at: the cheapest way to get one now (board ask + fee, or Abuela's typical fill)
          sell_at: the best way to cash one now (board bid - fee, or Abuela's typical bid)
          mv: the clearing estimate (team fills > board mid > dealer fills > book)
  peers   what the card is worth to another team missing it: the six multipliers are the same for
          everyone, shuffled, so once we know ours we know the whole distribution of theirs

Edges: buy_edge = next - buy_at, sell_edge = sell_at - keep. Both score at our private values.
Public reads go through a keyless client so they never spend the team key's 5 requests per second.
"""
from __future__ import annotations

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
    """Dealer asks and bids by rarity from every team's haggling, with the final (walk-away) ones apart."""
    q = defaultdict(lambda: {"open_ask": [], "final_ask": [], "final_bid": []})
    first = set()
    for e in events:
        if e.get("type") != "thread.message":
            continue
        p = e["payload"]
        o = p.get("offer") or {}
        if p.get("kind") != "persona" or p.get("sender") != p.get("with") or not o:
            continue
        give, want = o.get("give") or {}, o.get("want") or {}
        if want.get("cash"):      # the dealer sells: "card:LAV-06" or "pack:sobre_barrio" in give.types
            t = ((give.get("types") or []) + [""])[0]
            key = "pack" if t.startswith("pack:") else cards.get(t.removeprefix("card:"), {}).get("rarity")
            if key:
                if p["thread"] not in first:
                    q[key]["open_ask"].append(want["cash"])
                    first.add(p["thread"])
                if o.get("final"):
                    q[key]["final_ask"].append(want["cash"])
        elif give.get("cash"):    # the dealer buys
            item = (want.get("assets") or [{}])[0]
            if item.get("rarity") and o.get("final"):
                q[item["rarity"]]["final_bid"].append(give["cash"] / max(1, len(want.get("assets") or [1])))
    return q


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


# --------------------------------------------------------------------------- scoring

class Scorer:
    def __init__(self, snap: Snapshot, values: Values, history: list[dict]):
        self.snap, self.v, self.hist = snap, values, history
        self.rastro = snap.venues.get("rastro")
        self.quotes = dealer_quotes(snap.events, snap.cards)
        self.demand = demand_from(snap.events)
        self.by_ref = defaultdict(lambda: defaultdict(list))
        self.by_rarity = defaultdict(lambda: defaultdict(list))
        for f in history:
            self.by_ref[f["ref"]][f["side"]].append(f["price"])
            self.by_rarity[f["rarity"]][f["side"]].append(f["price"])
        self.dealer_sells = {r for d in snap.dealers if d.get("status") == "active"
                             for item in d.get("menu", {}).get("sells", []) for r in [item.get("rarity")] if r}
        self.dealer_buys = {r for d in snap.dealers if d.get("status") == "active"
                            for item in d.get("menu", {}).get("buys", []) for r in [item.get("rarity")] if r}
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

    def dealer_price(self, ref: str, side: str):
        rarity = self.snap.cards[ref]["rarity"]
        menu = self.dealer_sells if side == "dealer_sells" else self.dealer_buys
        if rarity not in menu or not self.snap.released(ref):
            return None
        own = self.by_ref[ref][side]
        return self.recent(own) if len(own) >= 2 else self.recent(self.by_rarity[rarity][side])

    def card(self, ref: str) -> dict:
        c, v = self.snap.cards[ref], self.v
        ask = min(self.asks[ref], key=lambda a: a["cost"], default=None)
        bid = max(self.bids[ref], key=lambda b: b["net"], default=None)
        d_sell, d_buy = self.dealer_price(ref, "dealer_sells"), self.dealer_price(ref, "dealer_buys")
        buy_opts = [(ask["cost"], f"board #{ask['offer']}")] if ask else []
        if d_sell:
            buy_opts.append((d_sell, "abuela"))
        sell_opts = [(bid["net"], f"bid #{bid['offer']}")] if bid else []
        if d_buy:
            sell_opts.append((d_buy, "abuela"))
        buy_at, buy_via = min(buy_opts, default=(None, "no seller"))
        sell_at, sell_via = max(sell_opts, default=(None, "no buyer"))
        team = self.by_ref[ref]["team"]
        if team:
            mv, src = self.recent(team), f"teams ({len(team)})"
        elif ask and bid:
            mv, src = (ask["price"] + bid["price"]) / 2, "board mid"
        elif d_sell:
            mv, src = d_sell, "abuela fills"
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
        row["ask"] = self.suggest_ask(row, d_sell)
        row["action"] = self.action(row)
        return row

    def suggest_ask(self, row: dict, dealer_price):
        """Where to list a copy: near what the best-placed peer would pay, never above what the dealer
        charges all-in (nobody pays a team more than Abuela), never below what the copy is worth to us."""
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

    def pack_ev(self) -> list[dict]:
        out = []
        released = [r for r in self.snap.cards if self.snap.released(r)]
        by_rarity = defaultdict(list)
        for r in released:
            by_rarity[self.snap.cards[r]["rarity"]].append(self.v.next_value(r))
        fills = defaultdict(list)
        for f in self.hist:
            if f["kind"] == "pack":
                fills[f["ref"]].append(f["price"])
        on_sale = {item.get("pack") for d in self.snap.dealers if d.get("status") == "active"
                   for item in d.get("menu", {}).get("sells", [])}
        for p in self.snap.catalog.get("packs", []):
            if p["id"] not in on_sale and not fills[p["id"]]:
                continue  # nobody sells it yet
            ev = sum(prob * statistics.mean(by_rarity[rar]) for slot in p["slots"] for rar, prob in slot.items()
                     if by_rarity.get(rar))
            paid = self.recent(fills[p["id"]])
            out.append({"pack": p["id"], "name": p["name"], "expected_book": p["expected_book"], "ev_to_us": ev,
                        "typical_price": paid, "edge": None if paid is None else ev - paid})
        return out

    def pages(self, rows: dict) -> list[dict]:
        out = []
        for s, meta in self.snap.sets.items():
            refs = self.v.page_refs(s)
            missing = self.v.missing(s)
            unsourced = [r for r in missing if rows[r]["buy_at"] is None]
            # no seller (rares, at level 1): price them at their market value, and say so
            cost = sum(rows[r]["buy_at"] if rows[r]["buy_at"] is not None else rows[r]["mv"] for r in missing)
            gain = sum(self.v.base(r) for r in missing) + self.v.page_bonus * self.v.page_value(s)
            out.append({"set": s, "name": meta["name"], "released": meta.get("released"), "mult": self.v.mult.get(s),
                        "have": len(refs) - len(missing), "of": len(refs), "missing": missing, "unsourced": unsourced,
                        "bonus": self.v.page_bonus * self.v.page_value(s), "cost": cost, "gain": gain,
                        "net": gain - cost})
        return sorted(out, key=lambda p: -(p["mult"] or 0))

    def board_offers(self) -> list[dict]:
        """Every open offer on every venue, scored as if we accepted it now, at our values."""
        out = []
        for vid, offers in self.snap.boards.items():
            for o in offers:
                if o["id"] in self.snap.my_offer_ids or o.get("status") != "open":
                    continue
                give, want = o["give"], o["want"]
                get_refs = [a["ref"] for a in give.get("assets") or []]
                pay_refs = [a["ref"] for a in want.get("assets") or []] + [t.removeprefix("card:") for t in want.get("types") or []]
                if any(self.v.counts[r] == 0 for r in pay_refs):
                    continue  # we do not hold what it wants
                cash = want.get("cash") or give.get("cash") or 0
                fee = venue_fee(self.snap.venues.get(vid), cash, len(get_refs) + len(pay_refs))
                got = sum(self.v.next_value(r) for r in get_refs) + (give.get("cash") or 0)
                paid = sum(self.v.keep_value(r) for r in pay_refs) + (want.get("cash") or 0) + fee
                out.append({"offer": o["id"], "venue": vid, "gets": get_refs, "gives": pay_refs,
                            "cash_in": give.get("cash") or 0, "cash_out": want.get("cash") or 0, "fee": fee,
                            "surplus": got - paid, "expires": o.get("expires_tick")})
        return sorted(out, key=lambda x: -x["surplus"])

    def run(self) -> dict:
        rows = {r: self.card(r) for r in self.snap.cards}
        q = self.quotes
        dealer = {rar: {"sells_median": self.recent(self.by_rarity[rar]["dealer_sells"]),
                        "sells_min": min(self.by_rarity[rar]["dealer_sells"], default=None),
                        "buys_median": self.recent(self.by_rarity[rar]["dealer_buys"]),
                        "open_ask": median(q[rar]["open_ask"]), "final_ask_min": min(q[rar]["final_ask"], default=None),
                        "final_bid_max": max(q[rar]["final_bid"], default=None),
                        "team_median": self.recent(self.by_rarity[rar]["team"]), "fills": sum(len(x) for x in self.by_rarity[rar].values())}
                  for rar in ("common", "uncommon", "rare", "epic", "legendary", "pack")}
        me = self.snap.me or {}
        held_value = sum(sum(v) for v in self.v.copy_values.values())
        return {
            "tick": self.snap.clock.get("tick"), "t_hours": self.snap.clock.get("t_hours"),
            "team": me.get("team") or me.get("name"), "cash": me.get("cash"), "level": me.get("level"),
            "score": me.get("score"), "held_value": held_value, "mult": self.v.mult, "calibration": self.v.calibration,
            "cards": rows, "dealer": dealer, "packs": self.pack_ev(), "pages": self.pages(rows),
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
        ("Packs", ["pack", "name", "", "book EV", "EV to us", "typical price", "edge"],
         [[p["pack"], p["name"], "", f0(p["expected_book"]), f0(p["ev_to_us"]), f0(p["typical_price"]), f0(p["edge"], True)] for p in rep["packs"]]),
        ("Price levels by rarity (all teams' fills)", ["rarity", "abuela sells", "min", "abuela buys", "open ask", "final ask min", "final bid max", "teams", "fills"],
         [[r, f0(d["sells_median"]), f0(d["sells_min"]), f0(d["buys_median"]), f0(d["open_ask"]), f0(d["final_ask_min"]),
           f0(d["final_bid_max"]), f0(d["team_median"]), d["fills"]] for r, d in rep["dealer"].items()]),
        ("Rivals (public board)", ["team", "rank", "score", "neg", "mkt", "album", "pages", "deals"],
         [[t["team"], t["rank"], t["score"], t["negotiating"], t["market"], f"{t['album_filled']}/{t['album_slots']}",
           t["pages_complete"], t["deals"]] for t in rep["rivals"]]),
    ]
    return out


def header(rep: dict) -> str:
    s = rep.get("score") or {}
    mult = "  ".join(f"{k} {v:.2f}" for k, v in sorted(rep["mult"].items(), key=lambda kv: -kv[1]))
    who = f"{rep['team']}: {rep['cash']} P, level {rep['level']}, cards worth {rep['held_value']:.0f} P, score {s.get('score', '-')} (rank {s.get('rank', '-')})" \
        if rep["team"] else "No BAZAAR_KEY: market view as a neutral team (every multiplier 1.0)"
    return f"tick {rep['tick']} (game hour {rep['t_hours']})  |  {who}\nmultipliers: {mult}  [{rep['calibration'].get('source')}]"


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
    while True:
        try:
            rep = score_once(snap, recal)
            recal = False
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
