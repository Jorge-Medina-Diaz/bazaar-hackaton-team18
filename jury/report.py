"""Build a keyless, static jury demo. No game writes, model calls or credential reads.

python3 -m jury.report --refresh
python3 -m jury.report --refresh --journal logs/run/journal.jsonl
Outputs default to ignored runs/jury/. Journal export contains aggregate counts only.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.version_info < (3, 10):
    raise SystemExit("La demo requiere Python 3.10+ porque reutiliza agent.affinity de main.")

from agent import affinity
from agent.contracts import PROD_URL
from agent.transport import RateLimiter, public_get

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
            "snapshot_tick": leaderboard.get("snapshot_tick"), "round": leaderboard.get("round"),
            "clock": {k: clock.get(k) for k in ("tick", "paused", "doors")}, "teams": teams,
            "affinity": {"classification": "inferred", "model": "agent.affinity / 720 permutations",
                         "events": len(events), "skipped_events": skipped,
                         "tick_range": [min(ticks), max(ticks)] if ticks else [], "teams": inferred,
                         "exact_rival_profit": None},
            "journal": journal_summary(journal)}


def render(report: dict) -> str:
    # Prevent data from ending the inert JSON script block; DOM uses textContent only.
    data = json.dumps(report, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    return (HERE / "template.html").read_text(encoding="utf-8").replace("__EVIDENCE__", data)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--refresh", action="store_true", help="Four public GETs, once, without a key")
    mode.add_argument("--offline", type=Path, help="JSON: leaderboard, clock, feed, catalog; marked offline")
    ap.add_argument("--journal", type=Path, help="Optional local WAL; exports counts, never its content")
    ap.add_argument("--output", type=Path, default=Path("runs/jury"))
    args = ap.parse_args(argv)
    if args.refresh:
        limiter = RateLimiter(rate=1, burst=1, reserve=0)
        data = {name: public_get(PROD_URL, "/api/" + name, limiter,
                                {"limit": 1000} if name == "feed" else None)
                for name in ("leaderboard", "clock", "feed", "catalog")}
        source = "public_api"
    else:
        data = json.loads(args.offline.read_text(encoding="utf-8"))
        source = "offline_input"
    report = make_report(**{k: data[k] for k in ("leaderboard", "clock", "feed", "catalog")},
                         journal=args.journal, source=source)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "demo.html").write_text(render(report), encoding="utf-8")
    print(f"Demo: {args.output / 'demo.html'}; tick {report['snapshot_tick']}; journal {report['journal']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
