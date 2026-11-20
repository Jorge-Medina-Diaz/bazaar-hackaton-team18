"""Dashboard data: one snapshot of us (/api/me) plus everything public about the other teams.

snapshot(b, state) only does GETs (me, clock, catalog, leaderboard, feed, El Rastro board, /api/me/value): no writes,
no admin routes. New feed events are appended to logs/feed.jsonl (same format as affinity.py / afinidad_propia.py read), so what we know
about rivals grows past the feed's 500-event window.

Rivals' cash and holdings are private (/api/cards/{id} shows their owner as "a team"). intel() works only from
public evidence: settlements in the feed (who received which card, who paid what) and El Rastro listings
(selling a card = holds it, bidding for a card = wants it).
page(data) fills agent/dashboard.html; data=None gives the live page that polls data.json.

M1 (K-13, INV-18): /api/me is redacted (agent.redact) before it is used or served, and the error text is too.
LOG_DIR comes from BAZAAR_LOGS (default logs/), so the dashboard never imports the runner's journal.
"""
import collections, json, os, time  # noqa: E401

from agent.redact import redact

LOG_DIR = os.environ.get("BAZAAR_LOGS", "logs")

TEMPLATE = os.path.join(os.path.dirname(__file__), "dashboard.html")
FEED = os.path.join(LOG_DIR, "feed.jsonl")


def _side(o: dict):
    """(side, ref, price, asset_id) of a one-card listing: 'vende' gives a card for cash, 'compra' gives cash."""
    g, w = o["give"], o["want"]
    if g.get("assets") or g.get("types"):
        a = (g.get("assets") or [None])[0]
        return "vende", a["ref"] if a else g["types"][0].split(":", 1)[1], w.get("cash", 0), a and a["id"]
    a = (w.get("assets") or [None])[0]
    ref = a["ref"] if a else (w["types"][0].split(":", 1)[1] if w.get("types") else "?")
    return "compra", ref, g.get("cash", 0), a and a["id"]


def _board(offers: list, makers: dict, teams: set) -> list:
    """Open offers on El Rastro, one row per card; the maker's pseudonym is resolved through the feed when we can."""
    rows = []
    for o in offers:
        side, ref, price, asset = _side(o)
        team = makers.get(o["id"]) or o["maker"]
        rows.append({"id": o["id"], "maker": o["maker"], "team": team if team in teams else None,
                     "side": side, "ref": ref, "price": price, "asset": asset, "expires": o["expires_tick"]})
    return sorted(rows, key=lambda r: (r["side"], r["ref"], r["price"]))


def _moves(events: list) -> list:
    rows = []
    for e in events:
        if e["type"] != "settlement":
            continue
        p = e["payload"]
        items = p.get("items") or []
        rows.append({"id": p["settlement"], "tick": p["tick"], "parties": p["parties"],
                     "from": items[0]["frm"] if items else p["parties"][0],
                     "to": items[0]["to"] if items else p["parties"][-1],
                     "cards": [i["ref"] for i in items if i["kind"] == "card"],
                     "assets": [[i["id"], i["ref"], i["frm"], i["to"]] for i in items if i["kind"] == "card"],
                     "price": p.get("price"), "venue": p.get("venue"), "persona": p.get("persona")})
    return rows


def _history(state: dict, events: list) -> list:
    """All feed events we have ever seen, oldest first; new ones are appended to logs/feed.jsonl."""
    seen = state.setdefault("events", {})
    if not seen and os.path.exists(FEED):
        for line in open(FEED, encoding="utf-8"):
            e = json.loads(line)
            seen[e["id"]] = e
    new = [e for e in events if e["id"] not in seen]
    if new:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(FEED, "a", encoding="utf-8") as f:
            for e in sorted(new, key=lambda e: e["id"]):
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
                seen[e["id"]] = e
    return [seen[k] for k in sorted(seen)]


def _value(b, state: dict, me: dict, ref: str) -> float:
    """Value of one more copy to us (/api/me/value), cached until our holdings change."""
    key = tuple(sorted(a["id"] for a in me["assets"]))
    if state.get("value_key") != key:
        state["value_key"], state["values"] = key, {}
    if ref not in state["values"]:
        state["values"][ref] = b.value(ref)["your_value"]
    return state["values"][ref]


def intel(b, state: dict, me: dict, lb: dict, cat: dict, board: list, moves: list, events: list) -> dict:
    us, tick = me["id"], me["tick"]
    teams = {t["team"]: t for t in lb["teams"]}

    # Last known holder of every card we have seen move; our own assets are the authority for us.
    owner, flow = {}, collections.defaultdict(lambda: {"in": 0, "out": 0, "n": 0})
    for m in moves:
        for aid, ref, _frm, to in m["assets"]:
            owner[aid] = {"team": to, "ref": ref, "tick": m["tick"], "how": "trato"}
        if m["price"]:
            flow[m["to"]]["out"] += m["price"]
            flow[m["from"]]["in"] += m["price"]
        flow[m["to"]]["n"] += 1
        flow[m["from"]]["n"] += 1
    for r in board:
        if r["side"] == "vende" and r["team"] and r["asset"]:
            owner[r["asset"]] = {"team": r["team"], "ref": r["ref"], "tick": tick, "how": f"lo vende a {r['price']}"}
    mine = {a["id"] for a in me["assets"]}
    for aid in [a for a, o in owner.items() if o["team"] == us and a not in mine]:
        del owner[aid]
    holds = collections.defaultdict(dict)  # team -> ref -> evidence
    for aid, o in owner.items():
        if o["team"] in teams and o["team"] != us:
            holds[o["team"]][o["ref"]] = o

    # What each team wants: bids on the board now, and bids it posted earlier (still a hint).
    wants = collections.defaultdict(dict)  # team -> ref -> {price, now}
    for e in events:
        if e["type"] == "offer.listed":
            o = e["payload"]["offer"]
            side, ref, price, _ = _side(o)
            if side == "compra" and o["maker"] in teams:
                wants[o["maker"]][ref] = {"price": price, "now": False, "tick": e["tick"]}
    for r in board:
        if r["side"] == "compra" and r["team"]:
            wants[r["team"]][r["ref"]] = {"price": r["price"], "now": True, "tick": tick, "expires": r["expires"]}

    # Cards of ours someone wants: compare their bid with what our cheapest copy is worth to us.
    ours = collections.defaultdict(list)
    for a in me["assets"]:
        if a["kind"] == "card":
            ours[a["ref"]].append(a)
    pages = {p["set"]: p for p in me["album"]["pages"]}
    sell_to = []
    for t, refs in wants.items():
        if t == us:
            continue
        for ref, w in refs.items():
            if ref in ours:
                copies = ours[ref]
                cheapest = min(a["your_value"] for a in copies)
                st = ref.split("-")[0]
                breaks = len(copies) == 1 and pages.get(st, {}).get("complete", False)
                sell_to.append({"team": t, "ref": ref, "price": w["price"], "now": w["now"], "tick": w["tick"],
                                "copies": len(copies), "our_value": cheapest, "breaks_page": breaks,
                                "gain": round(w["price"] - cheapest, 1)})
    sell_to.sort(key=lambda r: (not r["now"], r["breaks_page"], -r["gain"]))

    # Cards we miss: who sells them now and who we know holds one.
    missing = []
    for s in cat["sets"]:
        if not s["released"] or pages.get(s["id"], {}).get("complete"):
            continue
        have = pages.get(s["id"], {}).get("have", 0)
        for c in s["cards"]:
            if c["id"] in ours or not c["page"]:
                continue
            sources = [{"team": r["team"], "maker": r["maker"], "kind": "vende", "price": r["price"], "expires": r["expires"]}
                       for r in board if r["side"] == "vende" and r["ref"] == c["id"]]
            sellers = {x["team"] for x in sources}
            sources += [{"team": t, "kind": "tiene", "tick": h[c["id"]]["tick"], "how": h[c["id"]]["how"]}
                        for t, h in holds.items() if c["id"] in h and t not in sellers]
            missing.append({"ref": c["id"], "set": s["id"], "set_have": have, "rarity": c["rarity"],
                            "minted": c["minted"], "value": _value(b, state, me, c["id"]), "sources": sources})
    missing.sort(key=lambda m: (not m["sources"], -m["set_have"], -m["value"]))

    sc = me["score"]
    compare = []
    for t in lb["teams"]:
        f = flow[t["team"]]
        compare.append({"team": t["team"], "name": t["name"], "rank": t["rank"],
                        "score": t["score"], "d_score": round(t["score"] - sc["score"], 2),
                        "deals": t["deals"], "d_deals": t["deals"] - sc["deals"],
                        "album": t["album_filled"], "d_album": t["album_filled"] - sc["album_filled"],
                        "pages": t["pages_complete"], "d_pages": t["pages_complete"] - sc["pages_complete"],
                        "luck": t["luck"], "cash_in": f["in"], "cash_out": f["out"], "trades": f["n"],
                        "known": sorted(holds.get(t["team"], {})), "wants": sorted(wants.get(t["team"], {}))})
    return {"compare": compare, "sell_to": sell_to, "missing": missing,
            "since_tick": events[0]["tick"] if events else tick, "events": len(events)}


def snapshot(b, state: dict) -> dict:
    """state persists between calls (feed history, value cache)."""
    me, clock, cat, lb = redact(b.me()), b.clock(), b.catalog(), b.leaderboard()
    events = _history(state, b.feed(500).get("events", []))
    makers = {e["payload"]["offer"]["id"]: e["payload"]["offer"]["maker"] for e in events if e["type"] == "offer.listed"}
    teams = {t["team"] for t in lb["teams"]}
    for s in cat["sets"]:
        for c in s["cards"]:
            c.pop("flavour", None)
    board = _board(b.board("rastro").get("offers", []), makers, teams)
    moves = _moves(events)
    cat = {k: cat[k] for k in ("rarities", "sets", "currency", "currency_symbol", "values") if k in cat}
    return {
        "fetched_at": round(time.time(), 1),
        "me": me, "clock": clock, "cat": cat,
        "lb": {"tick": lb["tick"], "teams": lb["teams"]},
        "board": board,
        "moves": moves[-150:],
        "feedFrom": events[0]["tick"] if events else me["tick"], "feedTo": events[-1]["tick"] if events else me["tick"],
        "intel": intel(b, state, me, lb, cat, board, moves, events),
    }


def page(data=None) -> str:
    blob = "null" if data is None else json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    with open(TEMPLATE, encoding="utf-8") as f:
        return f.read().replace("__DATA__", blob, 1)
