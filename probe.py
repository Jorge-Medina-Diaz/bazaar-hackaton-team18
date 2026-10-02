"""Snapshot every readable endpoint to logs/probe/<tick>/ and print each one's shape. Safe: GETs only.

    python3 probe.py            # public + keyed (needs BAZAAR_KEY or .env)
    python3 probe.py --public   # no key needed

Use it when a level opens or something looks odd: diff two snapshots to see what changed.
"""
import json, os, sys  # noqa: E401

from bazaar_sdk import Bazaar, BazaarError

PUBLIC = ["/api/health", "/api/clock", "/api/schedule", "/api/levels", "/api/dealers", "/api/catalog",
          "/api/leaderboard", "/api/venues", "/api/venues/rastro/offers", "/api/feed?limit=1000"]
KEYED = ["/api/me", "/api/me/value?card=LAV-01", "/api/me/threads", "/api/me/offers", "/api/duels",
         "/api/duels?done=true"]


def shape(x, depth=0):
    """Keys and types, two levels deep: enough to read an unknown response."""
    if isinstance(x, dict) and depth < 2:
        return {k: shape(v, depth + 1) for k, v in x.items()}
    if isinstance(x, list):
        return [shape(x[0], depth + 1)] if x else []
    return type(x).__name__ if isinstance(x, (dict, list)) else x


if __name__ == "__main__":
    if "--public" in sys.argv:
        b, paths = Bazaar(os.environ.get("BAZAAR_URL", "https://bazaar.causaprima.ai"), "none"), PUBLIC
    else:
        from agent.client import client
        b, paths = client(), PUBLIC + KEYED
    out = os.path.join("logs", "probe", str(b.clock()["tick"]))
    os.makedirs(out, exist_ok=True)
    for path in paths:
        try:
            data = b.call("GET", path)
        except BazaarError as e:
            data = {"error": e.code, "message": e.message}
        name = path.removeprefix("/api/").replace("/", "_").replace("?", "_").replace("=", "-")
        with open(os.path.join(out, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        print(f"\n### {path}\n{json.dumps(shape(data), ensure_ascii=False)[:1500]}")
    print(f"\nsaved to {out}/")
