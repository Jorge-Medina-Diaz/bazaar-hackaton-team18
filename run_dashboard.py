"""Live team dashboard: polls the game every 30 s (GETs only) and serves it on localhost.

    python3 run_dashboard.py                    # http://127.0.0.1:8018 , refreshes every 30 s
    python3 run_dashboard.py --every 60 --port 9000
    python3 run_dashboard.py --once out.html    # one static snapshot (the file we publish as the shared artifact)

Each poll is ~6 GET requests (plus /api/me/value for missing cards when our holdings change), well under the
5 req/s limit. It logs one row to logs/dashboard.jsonl and appends new feed events to logs/feed.jsonl.
"""
import argparse, http.server, json, os, threading, time  # noqa: E401

from agent.client import client
from agent.dashboard import page, snapshot
from agent.journal import log

OUT = os.path.join("logs", "dashboard")


def poll(b, every: int) -> None:
    state = {}  # feed history and value cache, kept across polls
    while True:
        try:
            d = snapshot(b, state)
            tmp = os.path.join(OUT, "data.json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            os.replace(tmp, os.path.join(OUT, "data.json"))
            sc = d["me"]["score"]
            log("dashboard", tick=d["me"]["tick"], cash=d["me"]["cash"], score=sc["score"], rank=sc["rank"],
                board=len(d["board"]), moves=len(d["moves"]))
            print(f"tick {d['me']['tick']}: cash {d['me']['cash']} · score {sc['score']} · puesto {sc['rank']}", flush=True)
        except Exception as e:  # keep serving the last good data.json; the page shows it as stale after 90 s
            log("dashboard", error=repr(e))
            print("error:", e, flush=True)
        time.sleep(every)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            body, kind = page(None).encode("utf-8"), "text/html; charset=utf-8"
        elif path == "/data.json" and os.path.exists(os.path.join(OUT, "data.json")):
            body, kind = open(os.path.join(OUT, "data.json"), "rb").read(), "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # quiet: one line per poll is enough
        pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=int, default=30, help="seconds between polls")
    ap.add_argument("--port", type=int, default=8018)
    ap.add_argument("--once", metavar="FILE", help="write one static snapshot page and exit")
    a = ap.parse_args()
    b = client()
    if a.once:
        with open(a.once, "w", encoding="utf-8") as f:
            f.write(page(snapshot(b, {})))
        print("escrito", a.once)
        return
    os.makedirs(OUT, exist_ok=True)
    threading.Thread(target=poll, args=(b, a.every), daemon=True).start()
    print(f"Dashboard en http://127.0.0.1:{a.port} (refresco cada {a.every} s; Ctrl+C para parar)", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
