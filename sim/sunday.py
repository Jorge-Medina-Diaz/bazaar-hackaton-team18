"""A Sunday 4 Oct in the simulator (night audit): FakeGame with Sunday's clock (closes 15:00), the live schedule of one
clock scenario, schedule events that fire (CHA release, round 3, grant, duel waves with days, stalls closing), the
Pícaros as a third dealer bot, and a run clock that also gives the wall time (runner.wall). Never the real server:
loopback transport with the test key.

Scenarios (docs/DOMINGO.md): C = resume at 13.367 and Sunday events re-anchored by -3.283 (stalls 14:00 = t18.367);
A = resume at 13.367, nothing moved (CHA 12:17, stalls 21.65 never reached); B = clock jumped to 16.65.

    python3 -m sim.sunday C [ticks] [fixtures_dir]     # a dry rehearsal of the day in LIVE mode against the sim
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from sim import world as SW
from sim.bots import AbuelaBot, ChatoBot, DuelRival, TeamBot
from sim.world import FakeGame, Model

REPO = Path(__file__).resolve().parents[1]
HARVEST = REPO / "tests" / "fixtures" / "harvest"
T0 = {"C": 13.367, "A": 13.367, "B": 16.65}
SHIFT = {"C": -3.283, "A": 0.0, "B": 0.0}
W09 = datetime.fromisoformat("2026-10-04T09:00:00+02:00").timestamp()
CLOSES = "2026-10-04T15:00:00+02:00"
STAGES = ("core", "hygiene", "dealers", "rastro", "closer", "duels")


class PicarosBot(ChatoBot):
    """Honest stand-in for the Pícaros (no card swaps): El Chato's prices."""
    dealer_id = "picaros"


def schedule(scen: str) -> list:
    """/api/schedule entries of Sunday as Saturday 23:59 showed them, shifted for scenario C."""
    s = lambda h: round(h + SHIFT[scen], 3)                               # noqa: E731
    days = {"name": "", "rounds": 2, "duel_ticks": 12, "decay": 0.1, "max_concurrent": 4, "issues": ["price", "days"]}
    up = [{"at_hours": s(16.65), "action": "set_release", "params": {"set": "CHA"}},
          {"at_hours": s(16.65), "action": "round", "params": {"name": "Sunday · Chamberí", "weight": 1}},
          {"at_hours": s(16.7), "action": "grant_all", "params": {"cash": 150}},
          {"at_hours": s(18.65), "action": "duels", "params": dict(days, name="Duels III")},
          {"at_hours": s(21.45), "action": "announce", "params": {}}]
    up += [{"at_hours": s(21.65), "action": "persona", "params": {"id": p, "enabled": False}}
           for p in ("abuela", "chato", "pilar", "picaros", "banco")]
    up += [{"at_hours": s(21.65), "action": "duels", "params": dict(days, name="Final duels", rounds=1)},
           {"at_hours": s(22.65), "action": "end_round", "params": {}},
           {"at_hours": s(22.65), "action": "day_closes", "params": {"day": "sun"}, "wall": CLOSES}]
    return up


class SundayGame(FakeGame):
    scen = "C"
    t_open = 13.367                     # game hour at 09:00 wall

    def clock_view(self) -> dict:
        v = super().clock_view()
        v.update({"today": "sun", "today_name": "Sunday", "closes": CLOSES, "next_opens": None, "next_name": None})
        return v

    def wall(self) -> float:
        """Wall epoch of the current game instant (one game hour per wall hour while open)."""
        return W09 + (self.t_hours - self.t_open) * 3600.0 + (self.clock.now() - self.tick_started)

    def fire(self) -> None:
        self.log = getattr(self, "log", [])
        for e in self.schedule_upcoming:
            if e.get("_done") or e["at_hours"] > self.t_hours + 1e-9:
                continue
            e["_done"] = True
            a, p = e["action"], e.get("params") or {}
            if a == "set_release":
                for st in self.catalog["sets"]:
                    if st["id"] == p["set"]:
                        st["released"] = True
                self.model = Model(self.catalog)
            elif a == "round":
                self.round, self.round_name = 3, p["name"]
            elif a == "grant_all":
                for t in self.teams.values():
                    t["cash"] += p["cash"]
            elif a == "persona":
                self.dealers.pop(p["id"], None)
            elif a == "duels":
                self.duel_wave = {"left": p["rounds"], "ticks": p["duel_ticks"], "next": self.tick, "decay": p["decay"]}
            self.log.append((self.tick, round(self.t_hours, 3), a, p.get("id") or p.get("set") or p.get("name")))
        if self.t_hours >= self.t_open + 6.0 - 1e-9 and self.doors == "open":
            self.doors = "closed"                                         # 15:00 wall, whatever the schedule says
            self.log.append((self.tick, round(self.t_hours, 3), "doors_closed", None))
        w = getattr(self, "duel_wave", None)
        if w and w["left"] > 0 and self.tick >= w["next"]:
            w["left"] -= 1
            w["next"] = self.tick + w["ticks"] + 1
            for i, kind in enumerate(("reactive", "time_driven", "firm", "one_and_accept")):
                buyer = i % 2 == 0
                did = self.create_duel(role="buyer" if buyer else "seller", limit=100 if buyer else 60,
                                       rival_limit=80 if buyer else 85, deadline_ticks=w["ticks"], decay=w["decay"],
                                       issues=("price", "days"), rival=DuelRival(kind, self.tick + i), session=self.tick)
                self.duels[did]["your_days_weight"] = 5.0 if buyer else 6.0
                self.duels[did]["days_meaning"] = ("each delivery day costs you" if buyer
                                                   else "each delivery day adds cash to your side")
            self.log.append((self.tick, round(self.t_hours, 3), "duel_wave", w["left"]))

    def advance(self, n: int = 1) -> int:
        for _ in range(n):
            super().advance(1)
            self.fire()
        return self.tick


class SundayClock:
    """The run clock: virtual time that advances the game at tick boundaries, and the wall epoch for runner.wall."""

    def __init__(self, game: SundayGame):
        self.g, self.v = game, game.clock

    def now(self) -> float:
        return self.v.now()

    def sleep(self, s: float) -> None:
        self.v.sleep(s)
        while self.v.now() >= self.g.tick_started + self.g.tick_seconds:
            self.g.advance()

    def wall(self) -> float:
        return self.g.wall()


def build(scen: str = "C", *, fixtures: Path = HARVEST, start_min: int = 0, tick_seconds: float = 60.0,
          seed: int = 4, released=("LAV", "MAL", "LAT", "SAL", "RET")) -> SundayGame:
    """A SundayGame at 09:00 + start_min (wall); one tick = tick_seconds of game and of wall time. The Pícaros bot
    needs "picaros" in sim.world.DEALERS (main() sets it; tests patch it)."""
    d = Path(tempfile.mkdtemp(prefix="t18-sunday-fx-"))
    shutil.copytree(fixtures, d, dirs_exist_ok=True)
    shutil.rmtree(d / "probe", ignore_errors=True)
    t_open = T0[scen]
    clk = json.loads((d / "clock.json").read_text(encoding="utf-8")) if (d / "clock.json").exists() else {}
    clk.update({"t_hours": round(t_open + start_min / 60.0, 4), "tick_seconds": tick_seconds,
                "round": 3 if scen == "B" else 2, "days": []})
    (d / "clock.json").write_text(json.dumps(clk), encoding="utf-8")
    (d / "schedule.json").write_text(json.dumps({"upcoming": schedule(scen)}), encoding="utf-8")
    (d / "duels_live.json").write_text(json.dumps({"duels": []}), encoding="utf-8")
    (d / "me_offers.json").write_text(json.dumps({"offers": []}), encoding="utf-8")
    cat = json.loads((d / "catalog.json").read_text(encoding="utf-8"))
    for st in cat["sets"]:
        st["released"] = st["id"] in released
    (d / "catalog.json").write_text(json.dumps(cat), encoding="utf-8")
    g = SundayGame.from_fixtures(d, seed=seed, tick_seconds=tick_seconds)
    g.scen, g.t_open, g.log = scen, t_open, []
    for e in g.schedule_upcoming:                                       # a late start: past duel waves are over
        if e["action"] == "duels" and e["at_hours"] < g.t_hours - 0.2:
            e["_done"] = True
    g.teams["t18"]["unlocked"] = ["abuela", "chato", "pilar", "picaros", "banco"]
    for i, kind in enumerate(("honest", "honest", "overpriced", "twisted", "closer_bidder", "swapper")):
        g.add_bot(TeamBot(kind, 10 + i))
    for b in (AbuelaBot(seed=1), ChatoBot(seed=2), PicarosBot(seed=3)):
        g.add_bot(b)
    g.fire()
    return g


def run(g: SundayGame, ticks: int, *, plan: Path = REPO / "config" / "plan.json",
        armed=("hygiene", "dealers", "rastro", "closer", "duels")):
    """-> (rc, Paths). Live mode against the sim (loopback, test key), every stage marked green for this code."""
    from agent import runner
    from agent import transport as T
    from agent.contracts import Paths
    p = Paths.at(tempfile.mkdtemp(prefix="t18-sunday-"))
    p.state.mkdir(parents=True, exist_ok=True)
    ch = runner.code_hash()
    p.selftest.write_text(json.dumps({s: {"green": True, "code_hash": ch} for s in STAGES}), encoding="utf-8")
    clock = SundayClock(g)
    tr = T.GuardedTransport("http://127.0.0.1:9", "tk-test", mode="live", paths=p,
                            limiter=T.RateLimiter(rate=1000, burst=100, clock=clock), http=g.http)
    rc = runner.run("live", list(armed), paths=p, plan_path=plan, max_ticks=ticks, transport=tr, clock=clock)
    return rc, p


def main(argv) -> int:
    import os
    os.environ.setdefault("BAZAAR_TEST", "1")
    os.environ.setdefault("BAZAAR_NO_DOTENV", "1")
    SW.DEALERS = tuple(dict.fromkeys(SW.DEALERS + ("picaros",)))
    scen = argv[0] if argv else "C"
    ticks = int(argv[1]) if len(argv) > 1 else 359
    fx = Path(argv[2]) if len(argv) > 2 else HARVEST
    g = build(scen, fixtures=fx)
    rc, p = run(g, ticks)
    print(json.dumps({"rc": rc, "journal": str(p.journal), "events": g.log,
                      "threads": [(t["id"], t["with"], t["item"], t["status"], t["created_tick"])
                                  for t in g.threads.values() if t["team"] == "t18"],
                      "cash": g.teams["t18"]["cash"]}, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
