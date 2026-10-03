"""M6a: the fake answers with the same keys and types as the real server (harvest), and the real SDK works on it.

Shape rule: for every route with a harvest sample, the key set of every object equals the harvest's (recursively,
merging all list items), and every value type the fake produces was seen in the harvest for that key (int/float are
one "number"; null is accepted only where the harvest had null). Empty harvest lists are not descended.
The SDK runs in a clean subprocess (no agent.transport audit hook there) against serve() on 127.0.0.1.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import unittest

from tests import HARVEST, PROBE
from sim.fake_server import serve
from sim.world import FakeGame

KEY = {"X-Team-Key": "tk-test"}
REPO = HARVEST.parents[2]


def _t(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    return "dict"


def shape(v):
    """dict -> {"__keys__": frozenset, key: shape}, list -> {"__item__": merged shape}; leaves -> set of type names."""
    if isinstance(v, dict):
        return {"__type__": {"dict"}, "__keys__": {frozenset(v)},
                "__fields__": {k: shape(x) for k, x in v.items()}}
    if isinstance(v, list):
        s = {"__type__": {"list"}, "__item__": None}
        for x in v:
            s["__item__"] = merge(s["__item__"], shape(x))
        return s
    return {"__type__": {_t(v)}}


def merge(a, b):
    if a is None:
        return b
    if b is None:
        return a
    out = {"__type__": a["__type__"] | b["__type__"]}
    if "__keys__" in a or "__keys__" in b:
        out["__keys__"] = a.get("__keys__", set()) | b.get("__keys__", set())
        fa, fb = a.get("__fields__", {}), b.get("__fields__", {})
        out["__fields__"] = {k: merge(fa.get(k), fb.get(k)) for k in set(fa) | set(fb)}
    if "__item__" in a or "__item__" in b:
        out["__item__"] = merge(a.get("__item__"), b.get("__item__"))
    return out


def diff(real, fake, where="$"):
    """List of differences (fake vs real)."""
    out = []
    if real is None or fake is None:
        return out
    extra_types = fake["__type__"] - real["__type__"]
    if extra_types:
        out.append(f"{where}: types {sorted(extra_types)} not in harvest {sorted(real['__type__'])}")
    if "__keys__" in real and "__keys__" in fake:
        rk = set().union(*real["__keys__"])
        for ks in fake["__keys__"]:
            if ks not in real["__keys__"]:      # every fake key set must be a variant the harvest showed
                near = min(real["__keys__"], key=lambda r: len(set(r) ^ set(ks)))
                out.append(f"{where}: keys missing={sorted(set(near) - set(ks))} extra={sorted(set(ks) - set(near))}")
                break
        for k in rk & set(fake["__fields__"]):
            out += diff(real["__fields__"].get(k), fake["__fields__"].get(k), f"{where}.{k}")
    if real.get("__item__") is not None and fake.get("__item__") is not None:
        out += diff(real["__item__"], fake["__item__"], f"{where}[]")
    return out


def load(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


class Dealer:
    dealer_id = "abuela"

    def on_message(self, game, thread, msg):
        if msg is None:
            game.dealer_say(thread["id"], 20, "hola")
        elif msg["price"] is not None and msg["price"] >= 19:
            game.dealer_accept(thread["id"])
        else:
            game.dealer_say(thread["id"], 19, "casi", final=True)


def busy_game() -> FakeGame:
    """A fixture game with every kind of object: our offers, rival offers, a dealer thread, live and done duels,
    a settlement, a cancelled offer and an opened pack in the feed."""
    g = FakeGame.from_fixtures(HARVEST)
    g.add_bot(Dealer())
    s, t = g.handle("POST", "/api/threads", {"with": "abuela", "topic": {"buy": {"card": "LAV-05"}}}, team="t18")
    assert s == 200, t
    g.handle("POST", f"/api/threads/{t['id']}/messages", {"text": "15", "price": 15}, team="t18")
    g.advance()
    g.handle("POST", f"/api/threads/{t['id']}/messages", {"text": "19", "price": 19}, team="t18")
    rival = [o for o in g.offers.values() if o["maker"] != "t18" and o["status"] == "open" and o["to"] is None
             and o["give"]["assets"]][0]
    g.advance()
    g.handle("POST", f"/api/offers/{rival['id']}/accept", {}, team="t18")
    mine = [o for o in g.offers.values() if o["maker"] == "t18" and o["status"] == "open"]
    g.handle("DELETE", f"/api/offers/{mine[0]['id']}", team="t18")
    s, o = g.handle("POST", "/api/offers", {"give": {"assets": mine[0]["give"]["assets"]}, "want": {"cash": 9}},
                    team="t18")
    assert s == 200, o
    did = g.create_duel(limit=100, deadline_ticks=8)
    g.handle("POST", f"/api/duels/{did}/messages", {"text": "x", "price": 60}, team="t18")
    g.rival_say(did, 90, text="opening")
    done = g.create_duel(limit=100, deadline_ticks=8)
    g.handle("POST", f"/api/duels/{done}/messages", {"text": "x", "price": 70}, team="t18")
    g.rival_accept(done)
    pack = g.gift("t18", packs=["sobre_barrio"])[0]
    g.advance()
    g.handle("POST", f"/api/packs/{pack}/open", team="t18")
    return g


ROUTES = [("/api/clock", PROBE / "clock.json"), ("/api/me", PROBE / "me.json"),
          ("/api/me/offers", PROBE / "me_offers.json"), ("/api/venues", PROBE / "venues.json"),
          ("/api/venues/rastro/offers", PROBE / "venues_rastro_offers.json"), ("/api/duels", PROBE / "duels.json"),
          ("/api/duels?done=true", PROBE / "duels_done-true.json"), ("/api/me/threads", PROBE / "me_threads.json"),
          ("/api/leaderboard", PROBE / "leaderboard.json"), ("/api/schedule", PROBE / "schedule.json"),
          ("/api/catalog", PROBE / "catalog.json"), ("/api/health", PROBE / "health.json"),
          ("/api/levels", PROBE / "levels.json"), ("/api/dealers", PROBE / "dealers.json"),
          ("/api/me/value?card=LAV-01", PROBE / "me_value_card-LAV-01.json")]


class TestShapes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = busy_game()

    def get(self, path):
        s, raw = self.g.http("GET", "http://127.0.0.1" + path, None, KEY)
        self.assertEqual(s, 200, (path, raw[:200]))
        return json.loads(raw)

    def test_routes_match_harvest(self):
        problems = []
        for path, fixture in ROUTES:
            problems += [f"{path} {d}" for d in diff(shape(load(fixture)), shape(self.get(path)))]
        self.maxDiff = None
        self.assertEqual(problems, [])

    def test_thread_and_card(self):
        threads = load(PROBE / "me_threads.json")["threads"]
        tid = self.get("/api/me/threads")["threads"][0]["id"]
        real = None
        for t in threads:
            real = merge(real, shape(t))
        self.assertEqual(diff(real, shape(self.get(f"/api/threads/{tid}"))), [])
        cards = load(HARVEST / "cards_all.json")
        aid = next(a for a, x in self.g.assets.items() if x["kind"] == "card")
        real = shape(next(c for c in cards.values() if c["kind"] == "card"))
        self.assertEqual(diff(real, shape(self.get(f"/api/cards/{aid}"))), [])

    def test_feed_events_match_harvest(self):
        real = {}
        for e in load(PROBE / "feed_limit-1000.json")["events"]:
            real[e["type"]] = merge(real.get(e["type"]), shape(e))
        fake = {}
        for e in self.get("/api/feed?limit=500")["events"]:
            fake[e["type"]] = merge(fake.get(e["type"]), shape(e))
        for typ in ("offer.listed", "offer.cancelled", "settlement", "thread.opened", "pack.opened"):
            self.assertIn(typ, fake)
        problems = []
        for typ, s in fake.items():
            if typ in real:
                problems += [f"{typ} {d}" for d in diff(real[typ], s)]
        self.assertEqual(problems, [])

    def test_fidelity_points(self):
        clock = self.get("/api/clock")
        self.assertEqual(set(clock["limits"]), {"accepts_per_team_per_tick", "messages_per_side_per_tick",
                                                "max_open_threads_per_team", "max_open_offers_per_team",
                                                "offers_per_team_per_tick"})
        board = self.get("/api/venues/rastro/offers")["offers"]
        self.assertNotIn("t18", {o["maker"] for o in board})
        self.assertIn("mcd38ffd5", {o["maker"] for o in board})          # our pseudonym from the harvest
        self.assertEqual({o["maker"] for o in self.get("/api/me/offers")["offers"] if o["maker"].startswith("t")},
                         {"t18"})

    def test_openapi_postmessage_admits_days(self):
        props = load(REPO / "docs" / "openapi.json")["components"]["schemas"]["PostMessage"]["properties"]
        self.assertIn("days", props)
        self.assertIn("offer", props)


SDK_SCRIPT = textwrap.dedent("""
    import json, sys
    sys.path.insert(0, sys.argv[2])
    from bazaar_sdk import Bazaar, BazaarError
    b = Bazaar(sys.argv[1], "tk-test", wait_on_tick=False, retries=0, timeout=5)
    out = {}
    out["cash"] = b.me()["cash"]
    out["tick"] = b.clock()["tick"]
    out["board"] = len(b.board()["offers"])
    out["value"] = b.value("LAT-09")["your_value"]
    aid = [a["id"] for a in b.me()["assets"] if a["kind"] == "card"][0]
    o = b.list_offer({"assets": [aid]}, {"cash": 99}, venue="rastro", expires_in_ticks=4)
    out["listed"] = o["status"]
    out["cancel"] = b.cancel(o["id"])["ok"]
    try:
        b.accept(o["id"])
    except BazaarError as e:
        out["accept_err"] = [e.code, e.status]
    d = [x for x in b.duels()["duels"] if "days" in x["issues"]][0]
    try:
        b.duel_say(d["duel"], "hola", price=50)
    except BazaarError as e:
        out["missing_days"] = e.code
    out["duel_days"] = b.duel_say(d["duel"], "hola", price=50, days=3)["duel"]["your_offer"]["days"]
    try:
        b.call("GET", "/api/admin/teams")
    except BazaarError as e:
        out["admin"] = e.status
    print(json.dumps(out))
""")


class TestRealSdk(unittest.TestCase):
    def test_sdk_round_trip_over_http(self):
        g = FakeGame.from_fixtures(HARVEST)
        g.create_duel(issues=("price", "days"))
        url, stop = serve(g)
        try:
            env = {k: v for k, v in os.environ.items() if k not in ("BAZAAR_KEY", "BAZAAR_URL")}
            env["PYTHONIOENCODING"] = "utf-8"
            r = subprocess.run([sys.executable, "-c", SDK_SCRIPT, url, str(REPO)], capture_output=True, text=True,
                               timeout=60, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout.strip().splitlines()[-1])
        finally:
            stop()
        self.assertEqual(out["cash"], 260)
        self.assertEqual(out["tick"], 159)
        self.assertGreater(out["board"], 10)
        self.assertEqual((out["listed"], out["cancel"]), ("open", True))
        self.assertEqual(out["accept_err"], ["not_open", 409])
        self.assertEqual(out["missing_days"], "missing_days")
        self.assertEqual(out["duel_days"], 3)
        self.assertEqual(out["admin"], 404)
        self.assertEqual([v["kind"] for v in g.violations], ["admin"])
        self.assertTrue(all(r["team"] == "t18" for r in g.requests))


if __name__ == "__main__":
    unittest.main()
