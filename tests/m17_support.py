"""M17 shared helpers for the integration tests (not a test module: the name does not match test_*.py).

A compressed Saturday on sim.FakeGame (harvest-seeded, adversarial bots, dealer bots, duel rivals), the real
GuardedTransport (in-process loopback or real HTTP on 127.0.0.1), and the real runner/Gate/Sensor/Journal.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import tests  # noqa: F401  (test isolation: BAZAAR_TEST=1, no key, no .env)
from agent import runner
from agent import transport as T
from agent.contracts import Paths
from sim.bots import AbuelaBot, ChatoBot, DuelRival, TeamBot
from sim.world import FakeGame, Model

REPO = Path(__file__).resolve().parents[1]
PLAN = REPO / "tests" / "fixtures" / "plan_night.json"   # frozen: config/plan.json changes during the game
HARVEST = REPO / "tests" / "fixtures" / "harvest"
STAGES = ("core", "hygiene", "dealers", "rastro", "closer", "duels")
ADVERSARIES = ("honest", "twisted", "overpriced", "phantom", "injector", "opener", "closer_bidder", "swapper")
RIVALS = ("mute", "accept_only", "one_and_accept", "reactive", "time_driven", "firm", "worsening", "injector")


class GameClock:
    """Virtual clock whose sleep advances the fake game when a tick boundary is crossed."""

    def __init__(self, game):
        self.g, self.v = game, game.clock

    def now(self):
        return self.v.now()

    def sleep(self, s):
        self.v.sleep(s)
        while self.v.now() >= self.g.tick_started + self.g.tick_seconds:
            self.g.advance()


def saturday(seed: int = 1, *, bots=ADVERSARIES, dealers: bool = True, duels: bool = True,
             injection: bool = True, fixtures: bool = True, release=("RET",), **kw) -> FakeGame:
    """A harvest-seeded game with the adversarial team bots, Abuela + Chato and a few duels."""
    g = FakeGame.from_fixtures(HARVEST, seed=seed, **kw) if fixtures else FakeGame(seed=seed, **kw)
    if release:                                   # Saturday: RET is released (schedule), the page tactic starts
        for st in g.catalog["sets"]:
            if st["id"] in release:
                st["released"] = True
        g.model = Model(g.catalog)
    for i, kind in enumerate(bots):
        if kind == "injector" and not injection:
            continue
        g.add_bot(TeamBot(kind, seed + i))
    if dealers:
        g.add_bot(AbuelaBot(seed=seed))
        g.add_bot(ChatoBot(seed=seed))
    if duels:
        for i, kind in enumerate(RIVALS[:4] if injection else ("mute", "accept_only", "one_and_accept", "reactive")):
            g.create_duel(role="buyer" if i % 2 == 0 else "seller", limit=100, rival_limit=80 if i % 2 == 0 else 120,
                          deadline_ticks=12 + 4 * (i % 2), decay=0.06, rival=DuelRival(kind, seed + i))
    return g


def paths(prefix: str = "t18-m17-") -> Paths:
    p = Paths.at(tempfile.mkdtemp(prefix=prefix))
    p.state.mkdir(parents=True, exist_ok=True)
    return p


def loop_transport(game, p: Paths, clock, mode: str) -> T.GuardedTransport:
    return T.GuardedTransport("http://127.0.0.1:9", "tk-test", mode=mode, paths=p,
                              limiter=T.RateLimiter(rate=2.5, burst=5, clock=clock), http=game.http)


def http_transport(url: str, p: Paths, clock, mode: str) -> T.GuardedTransport:
    return T.GuardedTransport(url, "tk-test", mode=mode, paths=p, limiter=T.RateLimiter(rate=2.5, burst=5, clock=clock))


def green(p: Paths, stages=STAGES) -> None:
    ch = runner.code_hash()
    p.selftest.write_text(json.dumps({s: {"green": True, "code_hash": ch} for s in stages}), encoding="utf-8")


def run(game, p: Paths, *, mode: str = "dry", armed=runner.TACTICS, ticks: int = 10, transport=None, clock=None,
        **kw) -> int:
    clock = clock or GameClock(game)
    transport = transport or loop_transport(game, p, clock, mode)
    return runner.run(mode, list(armed), paths=p, plan_path=PLAN, max_ticks=ticks, transport=transport,
                      clock=clock, **kw)


def writes(game, team: str = "t18") -> list:
    return [q for q in game.requests if q["team"] == team and q["method"] != "GET"]


def rows(p: Paths) -> list:
    if not Path(p.journal).exists():
        return []
    out = []
    for line in Path(p.journal).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out
