"""One bounded keyless scan, or fully offline radar/replay. Outputs stay in runs/."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from market_harness.core import analyze, brief
from market_harness.evaluation import conversions, evaluate, synthetic_frames
from market_harness.timeline import archive_snapshot, movement_brief, read_archive, timeline, with_archive


def collect(get=None):
    if get is None:
        from agent.contracts import PROD_URL
        from agent.transport import RateLimiter, public_get
        limiter = RateLimiter(rate=1, burst=1, reserve=0)
        def get(path, query=None):
            return public_get(PROD_URL, path, limiter, query)
    s = {"captured_at": datetime.now(timezone.utc).isoformat(), "errors": {}, "books": {}}
    def read(key, path, query=None):
        try:
            return get(path, query)
        except Exception as e:
            s["errors"][key] = type(e).__name__
            return {}
    for key, path in (("clock_start", "/api/clock"), ("leaderboard", "/api/leaderboard"),
                      ("venues", "/api/venues"), ("schedule", "/api/schedule"),
                      ("catalog", "/api/catalog")):
        s[key] = read(key, path)
    for v in s["venues"].get("venues", []):
        vid = v.get("venue", "")
        if v.get("status") == "open" and re.fullmatch(r"(?:v\d+|rastro)", vid):
            s["books"][vid] = read(vid, f"/api/venues/{vid}/offers")
    s["feed"] = read("feed", "/api/feed", {"limit": 500})
    s["clock"] = read("clock", "/api/clock")
    s["finished_at"] = datetime.now(timezone.utc).isoformat()
    return s


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("refresh", "offline", "evaluate", "conversions", "timeline"))
    p.add_argument("--snapshot", action="append", default=[], help="Frozen public snapshot; repeat for replay")
    p.add_argument("--previous", help="Previous snapshot, for score/venue deltas")
    p.add_argument("--target", default="v18")
    p.add_argument("--out", default="runs/market-harness")
    p.add_argument("--as-of", type=int, help="Replay ignores COMPLETE frames later than this tick")
    p.add_argument("--synthetic", type=int, default=0, help="Number of hypothetical scenarios, not real data")
    p.add_argument("--campaigns", help="JSON list with verified announcement ids; never sends them")
    p.add_argument("--archive", help="Existing public event archive for offline history; refresh defaults to out/public-events.json")
    args = p.parse_args(argv)
    if args.synthetic < 0 or args.synthetic > 10000:
        p.error("--synthetic must be in 0..10000")
    if args.synthetic and args.snapshot:
        p.error("evaluate synthetic scenarios and real snapshots separately")
    if args.mode != "refresh" and not args.snapshot and not (args.mode == "evaluate" and args.synthetic):
        p.error("offline modes need --snapshot (evaluate can use --synthetic)")
    if args.mode == "conversions" and not args.campaigns:
        p.error("conversions needs --campaigns")
    out = Path(args.out)
    if args.mode == "timeline":
        result = timeline([load(s) for s in args.snapshot], args.target,
                          load(args.previous) if args.previous else None, args.as_of,
                          read_archive(args.archive) if args.archive else None)
        save(out / "timeline.json", result)
        (out / "movement.md").write_text(movement_brief(result), encoding="utf-8")
        print(movement_brief(result))
    elif args.mode == "evaluate":
        snapshots = [load(s) for s in args.snapshot] + synthetic_frames(args.synthetic)
        result = evaluate(snapshots, args.target, args.as_of)
        result["synthetic_frames_requested"] = args.synthetic
        save(out / "evaluation.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.mode == "conversions":
        s = load(args.snapshot[-1])
        if args.archive:
            s = with_archive(s, read_archive(args.archive))
        result = conversions(s, load(args.campaigns))
        save(out / "conversions.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        previous = load(args.previous) if args.previous else None
        s = collect() if args.mode == "refresh" else load(args.snapshot[-1])
        if args.mode == "refresh":
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            save(out / f"snapshot-{stamp}.json", s)
            # Preserve the failed observation, but never replace the previous
            # latest snapshot if the archive cannot validate/merge this frame.
            archive_snapshot(args.archive or out / "public-events.json", s)
            save(out / "snapshot.json", s)
            observed = s
        else:
            observed = with_archive(s, read_archive(args.archive)) if args.archive else s
        result = analyze(observed, args.target, previous)
        if observed is not s:
            result["feed_window"]["source"] = "public_archive_union_not_current_feed_window"
            result["feed_window"]["coverage_complete"] = None
            result["feed_window"]["bounded"] = False
        save(out / "radar.json", result)
        if previous:
            movement = timeline([s], args.target, previous)
            save(out / "timeline.json", movement)
            (out / "movement.md").write_text(movement_brief(movement), encoding="utf-8")
        out.mkdir(parents=True, exist_ok=True)
        (out / "brief.md").write_text(brief(result), encoding="utf-8")
        print(brief(result))


if __name__ == "__main__":
    main()
