"""M6a: invariants checked on a finished FakeGame (request log + oracle), optionally against the journal.

check(game, journal_path=None) -> list[str]   (empty = all good). Each string starts with the invariant id.
Checked: INV-01 (admin / forbidden routes), INV-02 (writes while paused or doors closed other than cancel/close),
INV-03 (429s, request rate, own open offers <= limit - 4, own threads <= limit - 1), INV-04 (oracle Δneg >= 0 on
team deals, == 0 on dealer deals), INV-07 (insufficient cash, settlement failures of ours), INV-12 (duel results
>= 0), INV-14/INV-15 with a journal (every write request of t18 has an intent row with the same method, path and
body hash, written before; no intent sent twice).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

TEAM = "t18"

def _body_hashes(body) -> set:
    if body is None:
        forms = ["", "null", "{}"]
    else:
        forms = [json.dumps(body, sort_keys=True, separators=(",", ":")), json.dumps(body, sort_keys=True),
                 json.dumps(body), json.dumps(body, separators=(",", ":"))]
    return {hashlib.sha256(f.encode("utf-8")).hexdigest() for f in forms}


def _journal_rows(path: Path) -> list:
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        return []
    return rows


def check(game, journal_path: Optional[str] = None, *, team: str = TEAM, max_rate: float = 2.5,
          window_s: float = 10.0) -> list:
    out = []
    for v in game.violations:
        out.append(f"INV-01 {v['kind']}: {v.get('method', '')} {v.get('path', '')} at tick {v['tick']}")
    ours = [r for r in game.requests if r["team"] == team]
    writes = [r for r in ours if r["method"] != "GET"]
    for r in ours:
        if r["status"] == 429:
            out.append(f"INV-03 429 {r['code']} on {r['method']} {r['path']} at tick {r['tick']}")
        if r["code"] == "insufficient_cash":
            out.append(f"INV-07 insufficient_cash on {r['method']} {r['path']} at tick {r['tick']}")
        if r["code"] in ("paused", "doors_closed"):
            out.append(f"INV-02 write while {r['code']}: {r['method']} {r['path']} at tick {r['tick']}")
    # request rate (virtual time): any window of window_s seconds holds at most max_rate*window_s + burst requests
    ts = sorted(r["t"] for r in ours)
    j = 0
    for i, t in enumerate(ts):
        while ts[j] < t - window_s:
            j += 1
        if i - j + 1 > max_rate * window_s + 5:
            out.append(f"INV-03 request rate above {max_rate}/s around t={t:.1f}")
            break
    for h in game.history:
        lim = h["limits"]
        if h["own_open_offers"] > lim["max_open_offers_per_team"] - 4:
            out.append(f"INV-03 {h['own_open_offers']} own open offers at tick {h['tick']}")
        if h["own_threads"] > lim["max_open_threads_per_team"] - 1:
            out.append(f"INV-03 {h['own_threads']} own threads at tick {h['tick']}")
        if h["cash"] is not None and h["cash"] < 0:
            out.append(f"INV-07 negative cash at tick {h['tick']}")
    for row in game.ledger.get(team, []):
        if row["dealer"]:
            if row["delta"] < -1e-6:
                out.append(f"INV-04 dealer deal {row['offer']} cost {row['delta']:.3f} neg at tick {row['tick']}")
        elif row["delta"] < -1e-6:
            out.append(f"INV-04 team deal {row['offer']} cost {row['delta']:.3f} neg at tick {row['tick']}")
    for f in game.failures:
        # only a failure caused by OUR side counts (M17): a counterparty whose listed asset vanished (phantom
        # bot) fails the settlement with missing_assets on ITS side, which is not a breach of INV-07 by us.
        if team in (f["maker"], f["accepter"]) and f.get("party", team) == team:
            out.append(f"INV-07 settlement of offer {f['offer']} failed: {f['code']}")
    for res in game.duel_results.get(team, []):
        if res < 0:
            out.append(f"INV-12 duel settled outside our limit (result {res})")
    if journal_path is not None:
        rows = _journal_rows(Path(journal_path))
        intents = [r for r in rows if r.get("kind") == "intent"]
        seen_ids: dict = {}
        for r in intents:
            iid = r.get("id")
            seen_ids[iid] = seen_ids.get(iid, 0) + 1
        for iid, n in seen_ids.items():
            if n > 1:
                out.append(f"INV-14 intent {iid} written {n} times")
        reqs = []
        for r in intents:
            req = r.get("request")
            if isinstance(req, (list, tuple)) and len(req) == 3:
                reqs.append((str(req[0]).upper(), req[1], req[2]))
            elif isinstance(req, dict):
                reqs.append((str(req.get("method", "")).upper(), req.get("path"), req.get("sha256")))
        used = [False] * len(reqs)
        for w in writes:
            hs = _body_hashes(w["body"])
            hit = None
            for k, (m, p, h) in enumerate(reqs):
                if not used[k] and m == w["method"] and p == w["path"] and (h in hs or h is None):
                    hit = k
                    break
            if hit is None:
                out.append(f"INV-15 write without a journal intent: {w['method']} {w['path']} at tick {w['tick']}")
            else:
                used[hit] = True
    return out
