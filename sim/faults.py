"""M6a: fault plans for the fake server (docs/harness-spec.md §9).

A rule is a dict:
  {"do": <kind>, "method": "POST"|None, "path": <regex fullmatch>|None, "tick": int|None, "team": str|None,
   "times": int (default 1, 0 = forever), "skip": int (matching calls to let through first), "field": str|None,
   "args": dict (game-level faults)}
Transport faults (matched per request in FakeGame.respond): 429_wait, 429_rate, 500, drop_after_commit, html_200,
truncated_body, redirect_302, incomplete_read, bad_json, missing_field, type_swap, extra_field.
Game faults (applied by on_tick at the start of FakeGame.advance when tick == rule["tick"], or every tick if None):
pause, doors_closed, schedule_rewrite, limits_change, pack_grant, gift.
Commit semantics: 429_*, 500 and redirect_302 do NOT reach the game; every other transport fault is applied to the
response of a request the game already processed (so a write may have landed: the client must treat it as unknown).
"""
from __future__ import annotations

import re
from typing import Iterable, Mapping, Optional

TRANSPORT = frozenset({"429_wait", "429_rate", "500", "drop_after_commit", "html_200", "truncated_body",
                       "redirect_302", "incomplete_read", "bad_json", "missing_field", "type_swap", "extra_field"})
GAME = frozenset({"pause", "doors_closed", "schedule_rewrite", "limits_change", "pack_grant", "gift"})
KINDS = TRANSPORT | GAME


class Plan:
    def __init__(self, rules: Iterable[Mapping] = ()):
        self.rules = []
        for r in rules:
            r = dict(r)
            if r.get("do") not in KINDS:
                raise ValueError(f"unknown fault {r.get('do')!r}")
            r.setdefault("times", 1)
            r.setdefault("skip", 0)
            r["_left"] = r["times"]
            r["_seen"] = 0
            self.rules.append(r)
        self.fired: list = []

    def _live(self, r) -> bool:
        return r["times"] == 0 or r["_left"] > 0

    def _use(self, r, game, where: str) -> None:
        if r["times"]:
            r["_left"] -= 1
        self.fired.append({"tick": game.tick, "do": r["do"], "where": where})

    def match(self, game, method: str, path: str, team: Optional[str] = None) -> Optional[dict]:
        """The first live transport rule that matches this request (and consumes one use)."""
        for r in self.rules:
            if r["do"] not in TRANSPORT or not self._live(r):
                continue
            if r.get("method") and r["method"].upper() != method.upper():
                continue
            if r.get("path") and not re.fullmatch(r["path"], path):
                continue
            if r.get("tick") is not None and r["tick"] != game.tick:
                continue
            if r.get("team") and r["team"] != team:
                continue
            r["_seen"] += 1
            if r["_seen"] <= r["skip"]:
                continue
            self._use(r, game, f"{method} {path}")
            return r
        return None

    def on_tick(self, game) -> None:
        """Game-level faults due before tick game.tick + 1 is produced."""
        upcoming = game.tick + 1
        for r in self.rules:
            if r["do"] not in GAME or not self._live(r):
                continue
            if r.get("tick") is not None and r["tick"] != upcoming:
                continue
            apply_game_fault(game, r["do"], r.get("args") or {})
            self._use(r, game, "tick")


def apply_game_fault(game, do: str, args: Mapping) -> None:
    team = args.get("team", "t18")
    if do == "pause":
        game.paused = bool(args.get("on", True))
    elif do == "doors_closed":
        game.doors = "closed" if args.get("on", True) else "open"
    elif do == "schedule_rewrite":
        game.schedule_upcoming = [dict(u) for u in args.get("upcoming", [])]
        game.emit("announcement", {"text": "calendar rewritten"}, actor="calendar")
    elif do == "limits_change":
        game.limits.update(args.get("limits", {}))
    elif do == "pack_grant":
        game.gift(team, packs=[args.get("pack", "sobre_barrio")], cash=int(args.get("cash", 0)), reason="grant")
    elif do == "gift":
        game.gift(team, cards=list(args.get("cards", [])), cash=int(args.get("cash", 0)), reason="gift from Abuela")
