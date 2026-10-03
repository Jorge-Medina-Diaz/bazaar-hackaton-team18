"""Build a keyless, static jury demo. No game writes, model calls or credential reads.

python3 -m jury.report --refresh
python3 -m jury.report --refresh --journal logs/run/journal.jsonl
Outputs default to ignored runs/jury/. Journal export contains aggregate counts only.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.version_info < (3, 10):
    raise SystemExit("La demo requiere Python 3.10+ porque reutiliza agent.affinity de main.")

from agent import affinity
from agent.contracts import PROD_URL
from agent.transport import RateLimiter, public_get
from market_harness.core import TEAM, REF, analyze, events_at, integer, leaderboard_age

HERE = Path(__file__).resolve().parent
VERDICTS = frozenset({"pass", "soft_fail", "hard_fail", "surprise_up", "info",
                      "excluded", "unattributed"})


def journal_summary(path: Path | None) -> dict:
    """Verify one immutable byte snapshot; never repair or open a writer.

    A local hash chain detects inconsistency, not authenticity of who produced it.
    An incomplete final line is not silently treated as verified evidence.
    """
    if path is None or not path.is_file():
        return {"status": "missing", "live_measurements": 0, "verdicts": {}}
    raw = path.read_bytes()
    base = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    if not raw or not raw.endswith(b"\n"):
        return {**base, "status": "incomplete", "live_measurements": 0, "verdicts": {}}
    previous, verdicts, modes = "0" * 64, collections.Counter(), collections.Counter()
    try:
        for seq, line in enumerate(raw.splitlines(), 1):
            row = json.loads(line)
            if (type(row.get("seq")) is not int or row["seq"] != seq
                    or row.get("prev") != previous or row.get("mode") not in {"live", "dry", "test"}):
                raise ValueError("chain")
            previous = hashlib.sha256(line).hexdigest()
            modes[row["mode"]] += 1
            if row["mode"] == "live" and row.get("kind") == "measure":
                verdict = row.get("verdict")
                if verdict not in VERDICTS:
                    raise ValueError("verdict")
                verdicts[verdict] += 1
    except (ValueError, TypeError, AttributeError):
        return {**base, "status": "invalid", "live_measurements": 0, "verdicts": {}}
    return {**base, "status": "verified_chain", "rows": seq, "modes": dict(modes),
            "live_measurements": sum(verdicts.values()), "verdicts": dict(verdicts)}


def make_report(leaderboard: dict, clock: dict, feed: dict, catalog: dict,
                journal: Path | None = None, *, fetched_at: str | None = None,
                source: str = "public_api") -> dict:
    fields = ("team", "rank", "score", "negotiating", "market", "pages_complete", "album_filled", "album_slots")
    teams = [{k: t[k] for k in fields if k in t} for t in leaderboard.get("teams", [])
             if re.fullmatch(r"t\d{2}", str(t.get("team", "")))]
    rarity = {c["id"]: c["rarity"] for s in catalog.get("sets", []) for c in s.get("cards", [])}
    events, skipped = [], 0
    for event in feed.get("events", []):
        if (not isinstance(event, dict) or event.get("scope") == "private" or
                (integer(clock.get("tick")) and integer(event.get("tick")) and event["tick"] > clock["tick"])):
            skipped += 1
            continue
        try:
            # Skip unsupported shapes explicitly; never enrich an ID with invented offer fields.
            affinity.evidence([event], rarity)
            events.append(event)
        except (KeyError, TypeError, AttributeError, ValueError, ZeroDivisionError):
            skipped += 1
    inferred = []
    for team, post in sorted(affinity.estimate(events, rarity_of=rarity).items()):
        if not re.fullmatch(r"t\d{2}", str(team)):
            continue
        top = post.top_set()
        best = max(top, key=top.get)
        inferred.append({"team": team, "top_set": best, "probability": round(top[best], 4),
                         "evidence_rows": sum(post.n.values()),
                         "entropy_bits": round(post.entropy_bits(), 3),
                         "expected": {s: round(post.expected(s), 3) for s in affinity.SETS},
                         "credible80": {s: post.credible(s) for s in affinity.SETS}})
    ticks = [e["tick"] for e in events if type(e.get("tick")) is int]
    return {"schema": 1, "source": source,
            "fetched_at": fetched_at or datetime.now(timezone.utc).isoformat(),
            "snapshot_tick": leaderboard_age({"leaderboard": leaderboard, "clock": clock})["tick"],
            "leaderboard_freshness": leaderboard_age({"leaderboard": leaderboard, "clock": clock}),
            "round": leaderboard.get("round"),
            "clock": {k: clock.get(k) for k in ("tick", "paused", "doors")}, "teams": teams,
            "affinity": {"classification": "inferred", "model": "agent.affinity / 720 permutations",
                         "events": len(events), "skipped_events": skipped,
                         "tick_range": [min(ticks), max(ticks)] if ticks else [], "teams": inferred,
                         "exact_rival_profit": None},
            "coverage": {"complete": False, "selection": "browser_retained_settlements_and_bids"
                         if source == "analyst_browser_export" else "api_window"},
            "journal": journal_summary(journal)}


def market_summary(snapshot: dict) -> dict:
    """Public evidence for the pitch; a sale price never becomes private profit."""
    radar = analyze(snapshot)
    trades = {}
    for e in events_at(snapshot, radar["tick"]):
        p = e["payload"]
        parties = p.get("parties", [])
        if (e["type"] != "settlement" or not integer(p.get("settlement")) or not p.get("venue")
                or not isinstance(parties, list) or len(parties) != 2 or "t18" not in parties
                or not all(TEAM.fullmatch(str(t)) for t in parties)
                or not integer(p.get("price")) or not integer(p.get("fee"))):
            continue
        transfers = []
        if not isinstance(p.get("items"), list):
            continue
        for item in p["items"]:
            if (isinstance(item, dict) and item.get("kind") == "card" and REF.fullmatch(str(item.get("ref")))
                    and item.get("frm") in parties and item.get("to") in parties
                    and item["frm"] != item["to"]):
                transfers.append({k: item[k] for k in ("ref", "frm", "to")})
        if transfers:
            trades[p["settlement"]] = {"settlement": p["settlement"], "event_id": e["id"],
                                        "tick": e["tick"], "venue": p["venue"], "price": p["price"],
                                        "fee_observed": p["fee"], "fee_payer": None,
                                        "transfers": transfers, "private_profit": None, "causal_score_effect": None}
    own = [t for t in radar["teams"] if t["team"] == "t18"]
    return {"tick": radar["tick"], "books_scanned": radar["books_scanned"],
            "compatible_pairs": radar["compatible_count"], "blocks": radar["blocks"],
            "own_venues": own[0]["venues"] if own else [], "coverage": radar["feed_window"],
            "own_settlements_in_window": len(trades),
            "own_settlements": sorted(trades.values(), key=lambda t: t["tick"])[-5:],
            "judge_score": None, "rubric": "Only ideas and craft are official; detailed rubric pending.",
            "decision": "Prioritize a reproducible demo, sourced outcomes and measured limits; keep trading under the operator's controls."}


def render(report: dict, analyst_url: str = "../analista/index.html") -> str:
    # Prevent data from ending the inert JSON script block; DOM uses textContent only.
    data = json.dumps(report, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    return ((HERE / "template.html").read_text(encoding="utf-8").replace("__EVIDENCE__", data)
            .replace("__ANALYST_URL__", html.escape(analyst_url, quote=True)))


def write_team_assets(report: dict, output: Path) -> None:
    """Static analyst deployment bundle, generated from this repo's public plan."""
    plan_path = HERE.parent / "config" / "plan.json"
    raw = plan_path.read_bytes()
    caps = json.loads(raw).get("dealer_max", {})
    caps = {ref: price for ref, price in caps.items() if re.fullmatch(r"(RET|CHA)-\d{2}", ref)
            and type(price) in (int, float) and 0 < price < 10000000}
    output.mkdir(parents=True, exist_ok=True)
    (output / "jurado.html").write_text(render(report, "index.html"), encoding="utf-8")
    public_plan = {"source": "config/plan.json", "sha256": hashlib.sha256(raw).hexdigest(), "dealer_max": caps}
    (output / "plan-public.js").write_text("globalThis.T18PublicPlan = Object.freeze(" +
                                         json.dumps(public_plan, sort_keys=True) + ");\n", encoding="utf-8")


def analyst_input(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "t18.analyst.public.v1":
        raise ValueError("Formato de exportación del analista desconocido")
    datetime.fromisoformat(data["captured_at"].replace("Z", "+00:00"))
    for k in ("leaderboard", "clock", "feed", "catalog"):
        if not isinstance(data.get(k), dict):
            raise ValueError("Exportación incompleta: " + k)
    if not isinstance(data["feed"].get("events"), list) or len(data["feed"]["events"]) > 3000:
        raise ValueError("Feed exportado inválido o demasiado grande")
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--refresh", action="store_true", help="Four public GETs, once, without a key")
    mode.add_argument("--offline", type=Path, help="JSON: leaderboard, clock, feed, catalog; marked offline")
    mode.add_argument("--analyst-export", type=Path, help="Public JSON exported by analista/index.html; no network")
    mode.add_argument("--market-snapshot", type=Path, help="Frozen market radar snapshot with catalog; no network")
    ap.add_argument("--journal", type=Path, help="Optional local WAL; exports counts, never its content")
    ap.add_argument("--output", type=Path, default=Path("runs/jury"))
    ap.add_argument("--team-output", type=Path, help="Also generate jurado.html and plan-public.js for analyst bundle")
    args = ap.parse_args(argv)
    if args.refresh:
        limiter = RateLimiter(rate=1, burst=1, reserve=0)
        data = {name: public_get(PROD_URL, "/api/" + name, limiter,
                                {"limit": 1000} if name == "feed" else None)
                for name in ("leaderboard", "clock", "feed", "catalog")}
        source = "public_api"
    elif args.analyst_export:
        data = analyst_input(args.analyst_export)
        source = "analyst_browser_export"
    elif args.market_snapshot:
        data = json.loads(args.market_snapshot.read_text(encoding="utf-8"))
        for key in ("leaderboard", "clock", "feed", "catalog", "venues", "books"):
            if not isinstance(data.get(key), dict):
                raise ValueError("Market snapshot incomplete: " + key)
        source = "market_snapshot"
    else:
        data = json.loads(args.offline.read_text(encoding="utf-8"))
        source = "offline_input"
    report = make_report(**{k: data[k] for k in ("leaderboard", "clock", "feed", "catalog")},
                         journal=args.journal, source=source,
                         fetched_at=data.get("captured_at") if args.analyst_export or args.market_snapshot else None)
    if args.market_snapshot:
        report["market"] = market_summary(data)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    analyst_url = Path(os.path.relpath(HERE.parent / "analista" / "index.html", args.output)).as_posix()
    (args.output / "demo.html").write_text(render(report, analyst_url), encoding="utf-8")
    if args.team_output:
        write_team_assets(report, args.team_output)
    print(f"Demo: {args.output / 'demo.html'}; tick {report['snapshot_tick']}; journal {report['journal']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
