"""Which barrio (set) gives each rival team the biggest multiplier: a Bayesian estimate from public evidence.

Every team holds the same six multipliers {0.5, 0.7, 0.9, 1.1, 1.3, 1.6}, one per set, in a private order. So the
hypothesis space per team is the 720 permutations, with a uniform prior. Coupling matters: evidence that LAT is high
for t14 also lowers the odds that any other set of t14 is the 1.6.

Evidence (each one is a soft likelihood L(a) of the multiplier `a` of the card's set, raised to a weight):
  * trade between teams (settlement, no persona): the buyer paid p for book value b, so b*a >= p is likely
    (sigmoid((b*a - p)/tau)), plus the share of the page bonus that card brings (none, ordinary, closer: mixture, PAGE_SHARE); the
    seller took p, so its copy was worth <= p, but that copy is usually a repeat (25 %): mixture, P_REPEAT.
  * buying a single card from a dealer: same as a buyer, weaker (teams also buy to unlock levels and ladder points).
    Selling to a dealer: same as a seller, weaker. Packs carry no set information.
  * bids and asks posted on any market (offer.listed): the strongest bid / ask per (team, card), weaker than a fill.
  * score evolution: between two leaderboard snapshots, a team whose only activity was team trades and whose
    `negotiating` jumped (after removing the drift of inactive teams) gained value on those trades, so
    sum(gain) > 0 under the true multipliers. That is a measurement, not a rationality assumption.
Every likelihood is floored by EPS (irrational or arbitrage moves happen), so one odd trade cannot zero a hypothesis.

estimate(events, snapshots) -> {team: Posterior}. A Posterior answers what negotiation code needs: marginals per set,
expected multiplier, P(card worth >= price to that team), a credible set at any confidence level.
"""
import collections, itertools, math, statistics  # noqa: E401

MULTS = (0.5, 0.7, 0.9, 1.1, 1.3, 1.6)
SETS = ("LAV", "MAL", "LAT", "SAL", "RET", "CHA")
BOOK = {"common": 10, "uncommon": 25, "rare": 70, "epic": 180, "legendary": 450}
PERMS = list(itertools.permutations(MULTS))  # PERMS[i][j] = multiplier of SETS[j]
EPS = 0.05
P_REPEAT = 0.75  # chance a seller's copy is a repeat (worth 25 %): teams mostly sell repeats
# A buyer filling a page also gets part of the page bonus (25 % of the page): nothing (not collecting that page),
# a tenth of it (an ordinary card of the page) or all of it (the card that closes the page). Mixture weights:
PAGE_SHARE = ((0.0, 0.35), (0.1, 0.5), (1.0, 0.15))
PAGE_BOOK = 5 * 10 + 3 * 25 + 2 * 70  # book value of a page: 265
# Dealer trades weigh little: everyone overpays dealers, so their prices bound multipliers badly (knowledge X-10).
WEIGHT = {"trade_buy": 1.0, "trade_sell": 0.7, "dealer_buy": 0.15, "dealer_sell": 0.1,
          "bid": 0.5, "ask": 0.25, "score": 1.0}
DEALERS = {"abuela", "chato"}


def _sig(x: float) -> float:
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, x))))


def _tau(p: float) -> float:
    return max(3.0, 0.25 * p)


def lik_buy(b: float, p: float, a: float) -> float:
    mix = sum(w * _sig(((b + share * 0.25 * PAGE_BOOK) * a - p) / _tau(p)) for share, w in PAGE_SHARE)
    return EPS + (1 - 2 * EPS) * mix


def lik_sell(b: float, p: float, a: float) -> float:
    first = _sig((p - b * a) / _tau(p))
    repeat = _sig((p - 0.25 * b * a) / _tau(p))
    return EPS + (1 - 2 * EPS) * ((1 - P_REPEAT) * first + P_REPEAT * repeat)


# ---------------------------------------------------------------- evidence extraction (pure, from feed events)

def _card_of(o: dict):
    """(side, set, rarity, ref) of a one-card offer: 'ask' gives a card for cash, 'bid' gives cash for a card."""
    g, w = o.get("give") or {}, o.get("want") or {}
    side, pool = ("ask", g) if (g.get("assets") or g.get("types")) else ("bid", w)
    if pool.get("assets"):
        a = pool["assets"][0]
        return side, a.get("set"), a.get("rarity"), a.get("ref")
    for t in pool.get("types") or []:
        kind, _, ref = t.partition(":")
        if kind == "card":
            return side, ref.split("-")[0], None, ref
    return side, None, None, None


def evidence(events: list, rarity_of: dict | None = None) -> list:
    """One row per piece of evidence: {team, kind, set, book, price, tick, ref}. rarity_of maps card ref -> rarity."""
    rarity_of = rarity_of or {}
    rows, quotes = [], {}
    for e in sorted(events, key=lambda e: e["id"]):
        p = e.get("payload") or {}
        if e["type"] == "settlement" and p.get("kind") == "trade":
            cards = [i for i in p.get("items") or [] if i.get("kind") == "card" and i.get("rarity") in BOOK]
            total = sum(BOOK[i["rarity"]] for i in cards)
            if not cards or not p.get("price"):
                continue
            for i in cards:
                share = p["price"] * BOOK[i["rarity"]] / total  # a bundle's price split by book value
                base = {"set": i["set"], "book": BOOK[i["rarity"]], "price": share, "tick": e["tick"], "ref": i["ref"]}
                dealer = p.get("persona") in DEALERS or i["frm"] in DEALERS or i["to"] in DEALERS
                if i["to"] not in DEALERS:
                    rows.append({**base, "team": i["to"], "kind": "dealer_buy" if dealer else "trade_buy"})
                if i["frm"] not in DEALERS:
                    rows.append({**base, "team": i["frm"], "kind": "dealer_sell" if dealer else "trade_sell"})
        elif e["type"] == "offer.listed":
            o = p.get("offer") or {}
            if o.get("thread") is not None or o.get("maker") in DEALERS:
                continue  # haggles with dealers are lowballs, not value signals
            side, st, rar, ref = _card_of(o)
            rar = rar or rarity_of.get(ref)
            price = (o.get("give") or {}).get("cash") if side == "bid" else (o.get("want") or {}).get("cash")
            if not st or rar not in BOOK or not price:
                continue
            k = (o["maker"], side, ref)
            best = quotes.get(k)
            if best is None or (price > best["price"] if side == "bid" else price < best["price"]):
                quotes[k] = {"team": o["maker"], "kind": side, "set": st, "book": BOOK[rar], "price": price,
                             "tick": e["tick"], "ref": ref}
    return rows + list(quotes.values())


def score_jumps(snapshots: list, events: list, min_jump: float = 0.05) -> list:
    """Intervals between leaderboard snapshots where a team's only activity was team trades.

    snapshots: [{tick, round, teams: {team: negotiating}}] oldest first. Returns
    [{team, sign, trades: [{set, book, price, side}], t0, t1, jump}] with drift of inactive teams removed.
    """
    sett = [e for e in events if e["type"] == "settlement" and (e.get("payload") or {}).get("kind") == "trade"]
    duel_ticks = {e["tick"] for e in events if e["type"] == "duel.closed"}
    out = []
    for s0, s1 in zip(snapshots, snapshots[1:]):
        if s0.get("round") != s1.get("round") or any(s0["tick"] < t <= s1["tick"] for t in duel_ticks):
            continue  # a new round restarts the score; duels move negotiating invisibly
        acts = collections.defaultdict(lambda: {"team": [], "dealer": 0})
        for e in sett:
            if not s0["tick"] < e["tick"] <= s1["tick"]:
                continue
            p = e["payload"]
            cards = [i for i in p.get("items") or [] if i.get("kind") == "card" and i.get("rarity") in BOOK]
            dealer = p.get("persona") in DEALERS
            for party in p.get("parties") or []:
                if dealer or not cards:
                    acts[party]["dealer"] += 1
                    continue
                total = sum(BOOK[i["rarity"]] for i in cards)
                for i in cards:
                    side = "buy" if i["to"] == party else "sell" if i["frm"] == party else None
                    if side:
                        acts[party]["team"].append({"set": i["set"], "book": BOOK[i["rarity"]], "side": side,
                                                    "price": p["price"] * BOOK[i["rarity"]] / total, "ref": i["ref"]})
        n0, n1 = s0["teams"], s1["teams"]
        idle = [n1[t] / n0[t] for t in n0 if t in n1 and t not in acts and n0[t] > 0.5]
        if len(idle) < 3:
            continue
        drift = statistics.median(idle)
        for t, a in acts.items():
            if a["dealer"] or not a["team"] or t not in n0 or t not in n1:
                continue
            jump = n1[t] - drift * n0[t]
            if abs(jump) >= min_jump:
                out.append({"team": t, "sign": 1 if jump > 0 else -1, "trades": a["team"],
                            "t0": s0["tick"], "t1": s1["tick"], "jump": round(jump, 3)})
    return out


# ---------------------------------------------------------------- inference

class Posterior:
    def __init__(self, team: str, logp: list, n: collections.Counter):
        m = max(logp)
        w = [math.exp(x - m) for x in logp]
        z = sum(w)
        self.team, self.p, self.n = team, [x / z for x in w], n  # p[i] = P(PERMS[i])

    def marginal(self, st: str) -> dict:
        j, out = SETS.index(st), dict.fromkeys(MULTS, 0.0)
        for perm, p in zip(PERMS, self.p):
            out[perm[j]] += p
        return out

    def expected(self, st: str) -> float:
        return sum(m * p for m, p in self.marginal(st).items())

    def p_at_least(self, st: str, mult: float) -> float:
        return sum(p for m, p in self.marginal(st).items() if m >= mult - 1e-9)

    def top_set(self) -> dict:
        """P(set is this team's 1.6) for every set."""
        return {s: self.marginal(s)[1.6] for s in SETS}

    def credible(self, st: str, conf: float = 0.8) -> list:
        """Smallest list of multipliers whose probability adds up to >= conf, most likely first."""
        out, acc = [], 0.0
        for m, p in sorted(self.marginal(st).items(), key=lambda kv: -kv[1]):
            out.append(m)
            acc += p
            if acc >= conf:
                break
        return out

    def p_worth(self, st: str, book: float, price: float, copy: float = 1.0) -> float:
        """P(the team values this copy at >= price): would it rationally buy at price (or refuse to sell below)?"""
        return sum(p for m, p in self.marginal(st).items() if book * m * copy >= price)

    def value(self, st: str, book: float, copy: float = 1.0) -> dict:
        mg = self.marginal(st)
        ev = sum(book * m * copy * p for m, p in mg.items())
        return {"expected": round(ev, 1), "low": round(book * min(self.credible(st)) * copy, 1),
                "high": round(book * max(self.credible(st)) * copy, 1)}

    def map(self) -> tuple:
        i = max(range(len(PERMS)), key=self.p.__getitem__)
        return dict(zip(SETS, PERMS[i])), self.p[i]

    def entropy_bits(self) -> float:
        return -sum(p * math.log2(p) for p in self.p if p > 0)  # 9.49 bits = knows nothing


def estimate(events: list, snapshots: list | None = None, rarity_of: dict | None = None,
             known: dict | None = None) -> dict:
    """{team: Posterior} from feed events (and leaderboard snapshots). known = {team: affinity} fixes a team."""
    ll = collections.defaultdict(lambda: [0.0] * len(PERMS))
    n = collections.defaultdict(collections.Counter)
    for r in evidence(events, rarity_of):
        if r["set"] not in SETS:
            continue
        j, w = SETS.index(r["set"]), WEIGHT[r["kind"]]
        f = lik_buy if r["kind"] in ("trade_buy", "dealer_buy", "bid") else lik_sell
        per_m = {m: w * math.log(f(r["book"], r["price"], m)) for m in MULTS}
        acc = ll[r["team"]]
        for i, perm in enumerate(PERMS):
            acc[i] += per_m[perm[j]]
        n[r["team"]][r["kind"]] += 1
    for jmp in score_jumps(snapshots or [], events):
        acc, w = ll[jmp["team"]], WEIGHT["score"]
        for i, perm in enumerate(PERMS):
            a = dict(zip(SETS, perm))
            gain = 0.0
            for t in jmp["trades"]:
                if t["set"] not in a:
                    continue
                v = t["book"] * a[t["set"]]
                gain += v - t["price"] if t["side"] == "buy" else t["price"] - v * (1 - 0.75 * P_REPEAT)
            scale = _tau(sum(t["price"] for t in jmp["trades"]))
            acc[i] += w * math.log(EPS + (1 - 2 * EPS) * _sig(jmp["sign"] * gain / scale))
        n[jmp["team"]]["score"] += 1
    out = {t: Posterior(t, ll[t], n[t]) for t in ll}
    for t, aff in (known or {}).items():
        exact = [0.0 if all(abs(aff.get(s, 0) - m) < 1e-9 for s, m in zip(SETS, perm)) else -1e9 for perm in PERMS]
        out[t] = Posterior(t, exact, collections.Counter(known=1))
    return out


def buyers(post: dict, st: str, book: float, price: float, conf: float = 0.7, exclude=()) -> list:
    """Teams that value a first copy of (set, book) at >= price with probability >= conf, best first."""
    rows = [(t, p.p_worth(st, book, price)) for t, p in post.items() if t not in exclude]
    return sorted([r for r in rows if r[1] >= conf], key=lambda r: -r[1])


def sellers(post: dict, st: str, book: float, price: float, conf: float = 0.7, exclude=()) -> list:
    """Teams that value their (first) copy below price with probability >= conf: likely to sell at that price."""
    rows = [(t, 1 - p.p_worth(st, book, price)) for t, p in post.items() if t not in exclude]
    return sorted([r for r in rows if r[1] >= conf], key=lambda r: -r[1])


def load(log_dir: str = "logs", known: dict | None = None) -> dict:
    """estimate() from what is already recorded (logs/feed.jsonl, logs/leaderboard.jsonl): no network, for agents."""
    import json, os  # noqa: E401
    rows = lambda f: [json.loads(x) for x in open(f, encoding="utf-8")] if os.path.exists(f) else []  # noqa: E731
    return estimate(rows(os.path.join(log_dir, "feed.jsonl")), rows(os.path.join(log_dir, "leaderboard.jsonl")),
                    known=known)
