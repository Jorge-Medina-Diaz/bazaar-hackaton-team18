"""Explicit hypothetical bot policies and observational conversion accounting."""
from __future__ import annotations

from collections import Counter
from market_harness.core import REF, TEAM, analyze, events_at, integer

PROFILES = ("rastro_only", "fee_comparator", "feed_reader", "conservative")


def decision(opportunity, report, profile, message="specific"):
    """Consideration under assumed policies, NOT predictions of real rivals/LLMs."""
    if profile not in PROFILES or message not in ("generic", "specific"):
        raise ValueError("unknown profile/message")
    if report["blocks"] or opportunity["status"] != "compatible_quotes":
        return {"considers": False, "reason": "blocked_or_price_gap"}
    if not opportunity["draft"]:
        return {"considers": False, "reason": "no_fresh_migration_draft"}
    if profile == "rastro_only":
        return {"considers": opportunity["target"] == "rastro", "reason": "venue_allowlist"}
    saving = opportunity["buyer_fee_saving_if_accepting_same_ask"]
    if profile == "fee_comparator":
        return {"considers": saving is not None and saving > 0, "reason": "buyer_fee_improvement"}
    if profile == "feed_reader":
        return {"considers": message == "specific", "reason": "needs_verified_offer_facts"}
    return {"considers": (message == "specific" and opportunity["remaining_ticks"] >= 4
                          and report["scan_start_tick"] == report["tick"]
                          and saving is not None and saving > 0), "reason": "fresh_facts_and_fee_improvement"}


def evaluate(snapshots, target="v18", as_of=None):
    """Replay COMPLETE historical frames only. Never rewind a future order book."""
    frames = sorted((s for s in snapshots if as_of is None or s["clock"]["tick"] <= as_of),
                    key=lambda s: (s["clock"]["tick"], s.get("captured_at", "")))
    totals = {p: {m: {"considered": 0, "examined": 0} for m in ("generic", "specific")} for p in PROFILES}
    reasons = Counter()
    seen = set()
    for s in frames:
        report = analyze(s, target)
        for o in report["opportunities"]:
            # Same quotes observed repeatedly are one exposure, not more successful campaigns.
            if o["id"] in seen:
                continue
            seen.add(o["id"])
            for p in PROFILES:
                for m in ("generic", "specific"):
                    d = decision(o, report, p, m)
                    totals[p][m]["examined"] += 1
                    totals[p][m]["considered"] += int(d["considers"])
                    reasons[f"{p}:{m}:{d['reason']}"] += 1
    return {"frames_used": len(frames), "unique_pairs": len(seen), "as_of": as_of,
            "profiles": totals, "reasons": dict(reasons), "real_trades_sent": 0,
            "interpretation": "Hypothetical consideration only; not real replies, closure probability, private surplus or score.",
            "assumptions": {"rastro_only": "Only Rastro allowed: text cannot change this.",
                            "fee_comparator": "Both enumerate venues; buyer needs a strictly lower fee, seller keeps ask.",
                            "feed_reader": "Both enumerate venues and require explicit current quote facts; heuristic, no LLM call.",
                            "conservative": "Both require facts, same-tick scan, >=4 ticks left and lower buyer fee."}}


def conversions(snapshot, campaigns, window=30):
    """Count verified published campaigns and exact public events, never missing offers.

    No explicit offer id in normal settlements: direction/card/parties/venue gives
    association only. A settlement is attributed at most once, to the latest campaign.
    """
    tick = snapshot["clock"]["tick"]
    events = events_at(snapshot, tick)
    by_id = {e["id"]: e for e in events}
    rows, used_ids = [], set()
    for c in campaigns:
        cid = c.get("id")
        if not isinstance(cid, str) or not cid or cid in used_ids:
            continue
        used_ids.add(cid)
        row = {"id": cid, "published": False, "listed_sides": [], "settlements": [],
               "association_only": True}
        ann = by_id.get(c.get("announcement_event_id"))
        if (not ann or ann["type"] != "venue.announcement" or ann["payload"].get("venue") != c.get("target")
                or ann["tick"] != c.get("tick") or c.get("seller") == c.get("buyer")
                or not TEAM.fullmatch(str(c.get("seller"))) or not TEAM.fullmatch(str(c.get("buyer")))
                or not REF.fullmatch(str(c.get("ref")))
                or not all(token in str(ann["payload"].get("text", ""))
                           for token in (str(c.get("seller")), str(c.get("buyer")), str(c.get("ref"))))):
            row["reason"] = "publication_not_verified_in_available_feed"
            rows.append(row)
            continue
        row.update({"published": True, "tick": c["tick"], "campaign": c,
                    "observation_end_tick": min(tick, c["tick"] + window),
                    "window_complete": tick >= c["tick"] + window})
        sides = set()
        for e in events:
            if not c["tick"] < e["tick"] <= c["tick"] + window:
                continue
            p = e["payload"]
            if e["type"] != "offer.listed" or p.get("venue") != c["target"]:
                continue
            o = p.get("offer", {})
            if not isinstance(o, dict):
                continue
            g, w = o.get("give", {}), o.get("want", {})
            if not isinstance(g, dict) or not isinstance(w, dict):
                continue
            assets = g.get("assets", [])
            if not isinstance(assets, list):
                continue
            if (o.get("maker") == c["seller"] and len(assets) == 1
                    and isinstance(assets[0], dict) and assets[0].get("ref") == c["ref"]
                    and not g.get("cash") and not g.get("types") and not w.get("assets")
                    and not w.get("types") and integer(w.get("cash"), 1)):
                sides.add("seller")
            if (o.get("maker") == c["buyer"] and w.get("types") == ["card:" + c["ref"]]
                    and not g.get("assets") and not g.get("types") and not w.get("assets")
                    and not w.get("cash") and integer(g.get("cash"), 1)):
                sides.add("buyer")
        row["listed_sides"] = sorted(sides)
        rows.append(row)
    settlement_ids = set()
    for e in events:
        p = e["payload"]
        if e["type"] != "settlement" or not integer(p.get("settlement")) or p["settlement"] in settlement_ids:
            continue
        items = p.get("items", [])
        matches = []
        for row in rows:
            if not row["published"]:
                continue
            c = row["campaign"]
            if (c["tick"] < e["tick"] <= c["tick"] + window and p.get("venue") == c["target"]
                    and set(p.get("parties", [])) == {c["seller"], c["buyer"]}
                    and len(items) == 1 and isinstance(items[0], dict)
                    and integer(p.get("price"), 1)
                    and items[0].get("ref") == c["ref"] and items[0].get("frm") == c["seller"]
                    and items[0].get("to") == c["buyer"]):
                matches.append(row)
        if matches:
            latest = max(matches, key=lambda r: (r["tick"], r["id"]))
            latest["settlements"].append({"settlement": p["settlement"], "tick": e["tick"], "price": p.get("price")})
            settlement_ids.add(p["settlement"])
    for r in rows:
        r.pop("campaign", None)
    counterparties = {party for r in rows if r["settlements"] for c in campaigns
                      if c.get("id") == r["id"] for party in (c["seller"], c["buyer"])}
    return {"campaigns": rows, "published": sum(r["published"] for r in rows),
            "associated_settlements": len(settlement_ids), "causal_effect": None,
            "distinct_counterparties": sorted(counterparties), "extra_market_points": None,
            "limitations": "Bounded feed; no response or missing offer proves nothing. Settlement associations are not causal uplift."}


def synthetic_frames(count=100):
    """Repeatable scenarios, deliberately including gaps, stale quotes and missing data."""
    frames = []
    for i in range(count):
        tick = 100 + i
        expiry = tick + (1 if i % 5 == 0 else 12)
        ask_price = 12 + i % 4
        bid_price = ask_price + (3 if i % 3 else -2)
        def offer(oid, maker, side, price):
            asset = {"id": oid, "kind": "card", "ref": "RET-01"}
            g = {"cash": 0, "assets": [asset], "types": []} if side == "ask" else {"cash": price, "assets": [], "types": []}
            w = {"cash": price, "assets": [], "types": []} if side == "ask" else {"cash": 0, "assets": [], "types": ["card:RET-01"]}
            return {"id": oid, "maker": maker, "to": None, "venue": "rastro", "status": "open",
                    "give": g, "want": w, "created_tick": tick, "expires_tick": expiry}
        frames.append({"clock": {"tick": tick, "paused": False}, "clock_start": {"tick": tick},
                       "captured_at": f"synthetic-{i:04}", "errors": {"v02": "missing"} if i % 11 == 0 else {},
                       "leaderboard": {"teams": []}, "feed": {"events": []},
                       "venues": {"venues": [
                           {"venue": "rastro", "owner": "world", "status": "open", "fee_bps": 500, "fee_per_card": 1},
                           {"venue": "v18", "owner": "t18", "status": "open", "fee_bps": 0, "fee_per_card": 0}]},
                       "books": {"v18": {"offers": []}, "rastro": {"offers": [
                           offer(i * 2 + 1, "t01", "ask", ask_price), offer(i * 2 + 2, "t02", "bid", bid_price)]}}})
    return frames
