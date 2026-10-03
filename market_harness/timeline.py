"""Offline observations across public frames; no inferred fills or wall-time rates."""
from __future__ import annotations

from collections import Counter
import json
import math
import os
from pathlib import Path
import tempfile

from market_harness.core import analyze, integer


def public_events(events, max_tick):
    """Fail closed on private, malformed, future or conflicting event records."""
    if not integer(max_tick) or not isinstance(events, list):
        raise ValueError("invalid public archive")
    found = {}
    for event in events:
        if (not isinstance(event, dict) or event.get("scope") != "public"
                or not integer(event.get("id")) or not integer(event.get("tick"))
                or event["tick"] > max_tick or not isinstance(event.get("type"), str)
                or not isinstance(event.get("payload"), dict)):
            raise ValueError("invalid/private/future public event")
        json.dumps(event, allow_nan=False)
        eid = event["id"]
        if eid in found and found[eid] != event:
            raise ValueError(f"conflicting public event id {eid}")
        found[eid] = event
    return sorted(found.values(), key=lambda e: (e["tick"], e["id"]))


def read_archive(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or type(data.get("schema")) is not int or data.get("schema") != 1:
        raise ValueError("invalid archive schema")
    data["events"] = public_events(data.get("events"), data.get("max_tick"))
    return data


def archive_snapshot(path, snapshot):
    """Merge immutable public IDs under a lock, replace atomically, preserve on error."""
    import fcntl
    path = Path(path)
    tick = snapshot.get("clock", {}).get("tick")
    incoming = public_events(snapshot.get("feed", {}).get("events", []), tick)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        existing = read_archive(path) if path.exists() else {"schema": 1, "max_tick": tick, "events": []}
        if existing["max_tick"] > tick:
            raise ValueError("clock reset or archive later than refresh")
        merged = public_events(existing["events"] + incoming, tick)
        data = {"schema": 1, "max_tick": tick, "events": merged}
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=".public-events-", delete=False) as tmp:
                name = tmp.name
                json.dump(data, tmp, ensure_ascii=False, indent=2, allow_nan=False)
                tmp.write("\n"); tmp.flush(); os.fsync(tmp.fileno())
            os.replace(name, path)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)
    return data


def with_archive(snapshot, archive):
    """Enrich observation history, retaining the original feed window separately."""
    tick = snapshot["clock"]["tick"]
    events = [e for e in archive["events"] if e["tick"] <= tick]
    events = public_events(events + snapshot.get("feed", {}).get("events", []), tick)
    return dict(snapshot, feed={"events": events})


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _book(snapshot):
    return {(venue, offer["id"]): offer
            for venue, book in snapshot.get("books", {}).items()
            if venue not in snapshot.get("errors", {})
            for offer in book.get("offers", [])
            if isinstance(offer, dict) and integer(offer.get("id"))}


def _settlements(events, before_tick):
    found = {}
    for event in events:
        p = event["payload"]
        if event["type"] != "settlement" or not integer(p.get("settlement")):
            continue
        sid = p["settlement"]
        if sid in found:
            # Different public envelopes for one settlement may exist, but its facts must agree.
            if found[sid]["payload"] != p:
                raise ValueError(f"conflicting settlement {sid}")
            continue
        found[sid] = event
    result = []
    for sid, event in sorted(found.items()):
        p = event["payload"]
        price = p.get("price")
        items = p.get("items", [])
        # A public price and card transfer distinguish a cash trade from a barter.
        directions = {(i.get("frm"), i.get("to")) for i in items if isinstance(i, dict)}
        classification = "cash_trade" if integer(price, 1) and len(directions) == 1 else (
            "swap" if integer(price) and price == 0 and len(directions) > 1 else "other_or_unknown")
        result.append({"settlement": sid, "event_id": event["id"], "tick": event["tick"],
                       "venue": p.get("venue"), "price": price, "classification": classification,
                       "parties": p.get("parties", []),
                       "timing": "after_previous_tick" if event["tick"] > before_tick else (
                           "same_tick_order_unknown" if event["tick"] == before_tick else "older_new_observation")})
    return result


def transition(before, after, target="v18"):
    a, b = before["clock"], after["clock"]
    ta, tb = a["tick"], b["tick"]
    reasons = []
    if tb < ta:
        reasons.append("clock_reset")
    if a.get("round") != b.get("round"):
        reasons.append("round_changed")
    elapsed = b.get("t_hours", 0) - a.get("t_hours", 0) if (
        number(a.get("t_hours")) and number(b.get("t_hours"))) else None
    if elapsed is None or elapsed <= 0 or tb <= ta:
        reasons.append("no_valid_game_time_progress")
    valid_rate = not reasons
    events_a = public_events(before.get("feed", {}).get("events", []), ta)
    events_b = public_events(after.get("feed", {}).get("events", []), tb)
    public_events(events_a + events_b, max(ta, tb))
    ids_a = {e["id"] for e in events_a}
    ids_b = {e["id"] for e in events_b}
    observed = [e for e in events_b if e["id"] not in ids_a]
    prior_settlement_ids = {e["payload"].get("settlement") for e in events_a if e["type"] == "settlement"}
    newly_observed_settlements = [e for e in observed if e["type"] == "settlement"
                                and e["payload"].get("settlement") not in prior_settlement_ids]
    window_non_overlap = bool(events_a and events_b and not ids_a.intersection(ids_b))
    ba, bb = _book(before), _book(after)
    comparable_books = set(before.get("books", {})).intersection(after.get("books", {}))
    comparable_books -= set(before.get("errors", {})) | set(after.get("errors", {}))
    missing = sorted(k for k in ba.keys() - bb.keys() if k[0] in comparable_books)
    cancelled = {(e["payload"].get("venue"), e["payload"].get("offer")) for e in events_b
                 if e["type"] == "offer.cancelled"}
    disappeared = [{"venue": v, "offer": oid, "reason": "confirmed_cancelled" if (v, oid) in cancelled
                    else "expired_by_final_tick" if integer(ba[(v, oid)].get("expires_tick"))
                    and ba[(v, oid)]["expires_tick"] <= tb else "unknown_disappearance",
                    "settlement_inferred": False} for v, oid in missing]
    def lb_clock(s):
        lb = s.get("leaderboard", {})
        tick = lb.get("snapshot_tick", lb.get("tick"))
        return {"snapshot_tick": tick, "clock_tick": s["clock"]["tick"],
                "lag_ticks": s["clock"]["tick"] - tick if integer(tick) else None,
                "stale": tick != s["clock"]["tick"], "round": lb.get("round")}
    lba, lbb = lb_clock(before), lb_clock(after)
    lb_comparable = (integer(lba["snapshot_tick"]) and integer(lbb["snapshot_tick"])
                     and lbb["snapshot_tick"] >= lba["snapshot_tick"]
                     and lba["round"] is not None and lba["round"] == lbb["round"]
                     and lba["snapshot_tick"] <= ta and lbb["snapshot_tick"] <= tb)
    teams_a = {t["team"]: t for t in before.get("leaderboard", {}).get("teams", [])}
    teams_b = {t["team"]: t for t in after.get("leaderboard", {}).get("teams", [])}
    round_comparable = a.get("round") == b.get("round") and tb >= ta
    teams = []
    for tid, team in sorted(teams_b.items()):
        old = teams_a.get(tid, {})
        delta = {key + "_delta": team[key] - old[key] if lb_comparable
                 and number(team.get(key)) and number(old.get(key)) else None
                 for key in ("rank", "score", "market")}
        teams.append(dict(team=tid, rank=team.get("rank"), score=team.get("score"), market=team.get("market"), **delta))
    va = {v["venue"]: v for v in before.get("venues", {}).get("venues", [])}
    venues = []
    for v in after.get("venues", {}).get("venues", []):
        old = va.get(v["venue"], {})
        trades = v.get("trades")
        diff = trades - old["trades"] if round_comparable and integer(trades) and integer(old.get("trades")) else None
        venues.append({"venue": v["venue"], "owner": v.get("owner"), "trades": trades,
                       "trades_delta": diff,
                       "trades_per_game_hour": diff / elapsed if valid_rate and diff is not None and diff >= 0 else None,
                       "counter_reset": diff is not None and diff < 0})
    ra, rb = analyze(before, target), analyze(after, target)
    oa = {o["id"] for o in ra["opportunities"]}; ob = {o["id"] for o in rb["opportunities"]}
    opportunities_comparable = not ra["blocks"] and not rb["blocks"]
    return {"from_tick": ta, "to_tick": tb, "from_capture": before.get("captured_at"),
            "to_capture": after.get("captured_at"), "paused_before": a.get("paused"), "paused_after": b.get("paused"),
            "elapsed_game_hours": elapsed if valid_rate else None, "rate_blocks": reasons,
            "newly_observed_activity_without_clock_progress": tb == ta and bool(observed),
            "leaderboard": {"before": lba, "after": lbb, "comparable": lb_comparable,
                            "snapshot_advanced": lba["snapshot_tick"] != lbb["snapshot_tick"],
                            "deltas_are_observed_snapshots": True},
            "teams": teams, "venues": venues,
            "quotes": {"new_book_ids": [{"venue": v, "offer": oid} for v, oid in sorted(bb.keys() - ba.keys())
                                         if v in comparable_books], "disappeared": disappeared,
                       "cancelled_in_new_feed": [{"venue": e["payload"].get("venue"), "offer": e["payload"].get("offer")}
                                                 for e in observed if e["type"] == "offer.cancelled"],
                       "expired_by_final_tick": [{"venue": v, "offer": oid} for (v, oid), offer in sorted({**ba, **bb}.items())
                                                 if integer(offer.get("expires_tick")) and ta < offer["expires_tick"] <= tb]},
            "new_observed_event_counts": dict(Counter(e["type"] for e in observed)),
            "confirmed_newly_observed_settlements": _settlements(newly_observed_settlements, ta),
            "feed": {"non_overlapping_windows": window_non_overlap, "overlap_event_count": len(ids_a & ids_b),
                     "coverage_complete": None, "event_id_gaps_are_not_missing_event_proof": True},
            "opportunities": {"entered": sorted(ob - oa) if opportunities_comparable else None,
                              "removed": sorted(oa - ob) if opportunities_comparable else None,
                              "comparison_available": opportunities_comparable,
                              "before_blocks": ra["blocks"], "after_blocks": rb["blocks"],
                              "removed_does_not_mean_executed": True}}


def timeline(snapshots, target="v18", previous=None, as_of=None, archive=None):
    frames = list(snapshots) + ([previous] if previous is not None else [])
    frames = [s for s in frames if as_of is None or s["clock"]["tick"] <= as_of]
    # Detect chronological resets before tick sorting would hide them.
    chronological = sorted(frames, key=lambda s: s.get("captured_at", ""))
    reset = any(b["clock"]["tick"] < a["clock"]["tick"] for a, b in zip(chronological, chronological[1:]))
    unique = {}
    for s in frames:
        # A tick/capture label is not a server snapshot identity. Only exact
        # repeated bodies are duplicate observations (same-tick changes can be real).
        key = json.dumps(s, sort_keys=True, ensure_ascii=False, allow_nan=False)
        unique[key] = s
    frames = sorted(unique.values(), key=lambda s: (s["clock"]["tick"], s.get("captured_at", "")))
    transitions = [transition(a, b, target) for a, b in zip(frames, frames[1:])]
    all_events = public_events([e for s in frames for e in s.get("feed", {}).get("events", [])],
                              max((s["clock"]["tick"] for s in frames), default=0))
    for s in frames:
        public_events(s.get("feed", {}).get("events", []), s["clock"]["tick"])
    if archive is not None:
        archived = public_events(archive.get("events"), archive.get("max_tick"))
        final_tick = max((s["clock"]["tick"] for s in frames), default=0)
        all_events = public_events(all_events + [e for e in archived if e["tick"] <= final_tick], final_tick)
    if reset:
        for row in transitions:
            row["rate_blocks"].append("chronological_clock_reset_detected")
            row["elapsed_game_hours"] = None
            for v in row["venues"]:
                v["trades_per_game_hour"] = None
    return {"schema": 1, "frames_used": len(frames), "target": target, "as_of": as_of,
            "chronological_clock_reset_detected": reset, "unique_public_events": len(all_events),
            "confirmed_settlements_in_observed_history": _settlements(all_events, -1), "transitions": transitions,
            "limitations": ["Feed windows are bounded; overlapping windows do not establish full coverage.",
                            "New observation does not establish when an action occurred within a paused tick.",
                            "Missing quotes are never interpreted as settlements.",
                            "Rates use game time only; score deltas compare cached leaderboard snapshots.",
                            "No inferred inventories, private profits, model behavior or causal market uplift."]}


def movement_brief(report):
    lines = ["# Movimiento observado del mercado", "", f"Fotos únicas: {report['frames_used']} · "
             f"eventos públicos únicos: {report['unique_public_events']}", ""]
    for t in report["transitions"]:
        lb = t["leaderboard"]
        fmt = lambda value: f"{value:.4f}" if number(value) else str(value)
        lines += [f"## Tick {t['from_tick']} → {t['to_tick']}", "",
                  f"Horas de juego comparables: {fmt(t['elapsed_game_hours'])}. "
                  f"Bloqueos de tasas: {', '.join(t['rate_blocks']) or 'ninguno'}.",
                  f"Clasificación: foto {lb['before']['snapshot_tick']} → {lb['after']['snapshot_tick']}; "
                  f"retraso final {lb['after']['lag_ticks']} ticks. Foto avanzó: {lb['snapshot_advanced']}; "
                  f"deltas comparables: {lb['comparable']}.",
                  f"Liquidaciones recién observadas: {len(t['confirmed_newly_observed_settlements'])}; "
                  f"ofertas desaparecidas: {len(t['quotes']['disappeared'])} (no se infieren tratos).",
                  f"Ventanas del feed sin solapamiento: {t['feed']['non_overlapping_windows']}.", "",
                  "| Equipo | Puesto | Δ puesto | Δ total | Δ mercado |", "|---|---:|---:|---:|---:|"]
        for team in t["teams"]:
            lines.append(f"| {team['team']} | {team['rank']} | {team['rank_delta']} | {fmt(team['score_delta'])} | {fmt(team['market_delta'])} |")
        lines += ["", "| Mercado | Δ tratos | Tratos/hora de juego |", "|---|---:|---:|"]
        for venue in t["venues"]:
            lines.append(f"| {venue['venue']} | {venue['trades_delta']} | {fmt(venue['trades_per_game_hour'])} |")
        lines.append("")
    lines += ["## Límites", ""] + [f"- {line}" for line in report["limitations"]]
    return "\n".join(lines) + "\n"
