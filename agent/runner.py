"""M15 runner: the per-tick loop (docs/harness-spec.md §1 "Orden de cada tick", §2.7, §5, §8, INV-02/03/19/22).

One process, one thread, one writer (state/writer.lock). Each tick:
inbox -> STOP -> wait / paused-doors poll -> fast path (startup, first open-doors tick) -> sensor.snapshot ->
gate.begin_tick + reconcile -> calibrator.on_tick -> pages.plan (Book.needs) -> tactics (each isolated) ->
choose (order, budgets, accepts by deadline) -> gate.execute -> late window for duel_accept -> journal "tick".

NOTES (M15, night build)
- Exit codes: 0 = max_ticks reached / interrupted, 1 = cannot start (no key, plan unreadable, bad mode),
  2 = STOP (STOP file present or written, GateViolation, StopActive, JournalError, AssertionError), 3 = writer lock busy.
  A STOP file at start or during the run makes the runner journal it and exit 2 (so a hot update can relaunch `run`).
- Tactics are plugged by name (TACTIC_MODULES) and imported lazily; a missing module is skipped (journal "alarm"
  once). Each propose runs in its own try: an exception skips only that tactic this tick; 3 exceptions in 20 ticks
  pause it (rastro pauses both "rastro" and "closer", it proposes both).
- Arming: run() arms exactly `armed` (state/armed.json rewritten). In live, a tactic is armed only if its selftest
  stage AND "core" are green with the current code_hash (state/selftest.json); "manual" needs only "core" (stricter
  than the spec, where manual is always armed in live: fail closed if the core is red). Red -> "alarm" row, not armed.
- Inbox (state/inbox/*.json, written by bazaar.py): arm / pause / resume / do / flatten. Each applied order is
  journaled ("cmd") then deleted. Orders older than the runner's start are not applied (journaled as stale and
  removed): a stale `arm` must never arm a new run. `do` from a one-shot CLI call comes in through run(manual=...).
- Manual intents (`do`, `flatten`): the prediction is the Gate's own recomputation (Gate._predict), so G07 never
  trips on a human order; every other guard applies unchanged. A failure there leaves predict_none -> the Gate refuses.
  A `do` order is sent for real only if it says "live": true (`do --live`); otherwise armed_now() drops "manual"
  while the Gate executes it, so it ends as a "would" even in a live run. Flatten intents follow the run's mode.
- Fast path (§1 step 4) only runs when a baseline already exists and nothing is pending reconciliation: the Gate
  takes its baseline from the World it is given and reconcile reads evidence from it, and the fast World has most
  sources down. It only executes the configured startup cancels (J0). First start without baseline: the full
  snapshot must have me/offers, me/threads, threads and duels up before begin_tick (else the tick is skipped).
- Late window: duel_accept intents are held back; from 50 % of the tick the runner re-reads (sensor.snapshot),
  re-proposes duels on the fresh World and executes the fresh duel_accepts (accept budget left this tick, the Gate
  re-checks G51 and the deadline). If the re-read fails or the tick moved, the early ones are dropped.
- Not done tonight (open issues): Book.protect_sets is left as guards.build_book made it (pages.protect_sets would
  drop LAT at t205 but Book.keep would not follow); Calibrator recheck= (guards-based) is not wired; duels.e16_settled
  is not called (World has no done duels); L1 bench recorder is not polled; snapshots every 5 ticks only (not on
  every write tick); no req_rate in the tick row.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import math
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Optional, Sequence

from agent.contracts import (PROD_URL, TACTICS, TEAM, Intent, Paths, Prediction, World, intent_id, make_intent)

REPO = Path(__file__).resolve().parents[1]

TACTIC_MODULES = (("hygiene", "agent.tactics.hygiene"), ("dealers", "agent.tactics.dealers"),
                  ("rastro", "agent.tactics.rastro"), ("duels", "agent.tactics.duels"))
MODULE_TACTICS = {"hygiene": ("hygiene",), "dealers": ("dealers",), "rastro": ("rastro", "closer"),
                  "duels": ("duels",)}
TACTIC_STAGE = {"hygiene": "hygiene", "dealers": "dealers", "rastro": "rastro", "closer": "closer",
                "duels": "duels", "manual": "core"}
EXPOSURE = {"cancel": 0, "close_thread": 1, "open_pack": 2}
TACTIC_ORDER = {t: i for i, t in enumerate(("manual", "hygiene", "duels", "dealers", "closer", "rastro"))}
ACCEPT_KINDS = frozenset({"accept", "duel_accept"})
OWN_OPEN = frozenset({"open", "queued"})
FATAL_NAMES = frozenset({"GateViolation", "StopActive", "JournalError"})
BASELINE_SOURCES = frozenset({"me/offers", "me/threads", "threads", "duels"})
EXC_LIMIT, EXC_WINDOW = 3, 20
SNAP_EVERY = 5
# Keyed request budget (RULES: 5 requests/s per key, bursts of 20). The runner takes 3.5/s, burst 8 (2 kept for the
# Gate's fresh re-reads and sends); read-only panels on the same key take agent.client.PANEL_RATE (1/s) -> 4.5/s.
# At 2.5/s a 15 s Sunday tick left only a few seconds after the snapshot (Sat: 14 G03.late at 30 s ticks).
RUNNER_RATE, RUNNER_BURST, RUNNER_RESERVE = 3.5, 8, 2
MAX_SLEEP_S = 60.0
WAKE_PAD_S = 1.0
INBOX_CMDS = frozenset({"arm", "pause", "resume", "do", "flatten"})
FLATTEN_MAX_TICKS = 10           # stop --flatten: STOP anyway after this many flatten ticks (a cancel that never lands)


class Fatal(Exception):
    """Internal: stop the run with exit code 2 after writing STOP."""


# ------------------------------------------------------------------------------------- stages / hash

def code_hash(root: Path = REPO) -> str:
    """sha256 over agent/**/*.py and bazaar.py (sorted by path). Selftest and arming compare it."""
    h = hashlib.sha256()
    files = sorted(p for p in (Path(root) / "agent").rglob("*.py") if "__pycache__" not in p.parts)
    b = Path(root) / "bazaar.py"
    if b.exists():
        files.append(b)
    for p in files:
        h.update(p.relative_to(root).as_posix().encode("utf-8") + b"\0")
        try:
            h.update(p.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return h.hexdigest()[:16]


def read_selftest(paths: Paths) -> dict:
    try:
        d = json.loads(Path(paths.selftest).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:                                                    # noqa: BLE001
        return {}


def stage_green(stage: str, paths: Paths, *, chash: Optional[str] = None, selftest: Optional[dict] = None) -> bool:
    st = selftest if selftest is not None else read_selftest(paths)
    e = st.get(stage)
    ch = chash if chash is not None else code_hash()
    return isinstance(e, dict) and e.get("green") is True and e.get("code_hash") == ch


def tactic_green(tactic: str, paths: Paths, *, chash: Optional[str] = None, selftest: Optional[dict] = None) -> bool:
    """Live arming rule: core green and the tactic's own stage green, both with the current code hash."""
    stage = TACTIC_STAGE.get(tactic)
    if stage is None:
        return False
    st = selftest if selftest is not None else read_selftest(paths)
    ch = chash if chash is not None else code_hash()
    return stage_green("core", paths, chash=ch, selftest=st) and stage_green(stage, paths, chash=ch, selftest=st)


# ------------------------------------------------------------------------------------------- choose

def _g(m: Any, k: str, default: Any = None) -> Any:
    try:
        return m.get(k, default)
    except Exception:                                                    # noqa: BLE001
        return default


def _num(x: Any) -> Optional[float]:
    return float(x) if type(x) in (int, float) and math.isfinite(x) else None


def _offer_deadline(world: World, oid: Any) -> float:
    pools: list = [world.offers_to_us or (), world.board or ()]
    pools.extend((world.boards or {}).values())
    for t in (world.threads or {}).values():
        pools.append(_g(t, "standing_offers", ()) or ())
    for pool in pools:
        for o in pool or ():
            if _g(o, "id") == oid:
                e = _num(_g(o, "expires_tick"))
                return e if e is not None else math.inf
    return math.inf


def _duel_deadline(world: World, did: Any) -> float:
    for d in world.duels or ():
        if _g(d, "duel", _g(d, "id")) == did:
            e = _num(_g(d, "deadline_tick"))
            return e if e is not None else math.inf
    return math.inf


def accept_deadline(it: Intent, world: World) -> float:
    if it.kind == "duel_accept":
        return _duel_deadline(world, it.args.get("duel_id"))
    if it.kind == "accept":
        return _offer_deadline(world, it.args.get("offer_id"))
    return math.inf


def _cfg(cfg: Any, name: str, default: Any) -> Any:
    v = getattr(cfg, name, default)
    return default if v is None else v


def choose(intents: Sequence[Intent], world: World, cfg: Any, drops: Optional[list] = None) -> list:
    """Order and per-tick budgets (INV-03). Pure.

    Order: exposure reducers first (cancel, close_thread, open_pack), then priority (high first), then tactic order.
    Budgets: accepts (team/dealer + duel when DUEL_ACCEPT_SHARED) <= limits.accepts, given to the EARLIEST deadline
    (ties: higher priority); list_offer + cancel <= min(LISTINGS_PER_TICK, L, max(1, L - 2)), L = limits.listings;
    new list_offer <= room in open offers (limits.open_offers - OPEN_OFFERS_MARGIN - own open); open_thread <= max(1, limits.threads -
    THREADS_MARGIN) - own open threads, none from a tactic while more than MAX_LIVE_DUELS_FOR_THREADS (4: Sunday's
    max_concurrent) duels are live (a manual order still goes); <= 1 message per thread / duel (a duel being accepted
    gets no message); duplicates (same intent id, or same cancel/close/pack target) dropped.
    The Gate re-checks every budget (G04); this only decides WHO gets the scarce slots. `drops`, when given, gets
    (intent, code) for every intent left out (R04.*), so the runner can journal why an order did nothing.
    """
    def drop(it, code):
        if drops is not None:
            drops.append((it, code))

    tick = world.tick
    seen_ids, seen_targets = set(), set()
    items = []
    for i, it in enumerate(intents or ()):
        if not isinstance(it, Intent):
            continue
        try:
            iid = intent_id(tick, it)
        except Exception:                                                # noqa: BLE001
            continue
        if iid in seen_ids:
            drop(it, "R04.dup")
            continue
        seen_ids.add(iid)
        items.append((EXPOSURE.get(it.kind, 3), -int(it.priority), TACTIC_ORDER.get(it.tactic, 9), i, it))
    items.sort(key=lambda x: x[:4])
    ordered = [x[-1] for x in items]

    L = world.limits
    shared = bool(_cfg(cfg, "DUEL_ACCEPT_SHARED", True))
    acc_budget = max(0, int(getattr(L, "accepts", 0) or 0))
    accepts = [it for it in ordered if it.kind in ACCEPT_KINDS]
    accepts.sort(key=lambda it: (accept_deadline(it, world), -int(it.priority)))
    chosen_acc: set = set()
    if shared:
        chosen_acc = {id(it) for it in accepts[:acc_budget]}
    else:
        team = [it for it in accepts if it.kind == "accept"]
        duel = [it for it in accepts if it.kind == "duel_accept"]
        chosen_acc = {id(it) for it in team[:acc_budget] + duel[:acc_budget]}
    accepted_duels = {it.args.get("duel_id") for it in accepts if id(it) in chosen_acc and it.kind == "duel_accept"}

    lim = int(getattr(L, "listings", 0) or 0)          # min(L, max(1, L - 2)): limit 2 or 3 keeps one slot (Gate G04)
    listings = max(0, min(int(_cfg(cfg, "LISTINGS_PER_TICK", 6)), lim, max(1, lim - 2)))
    own_open = sum(1 for o in world.my_offers or () if _g(o, "maker") == TEAM and _g(o, "status") in OWN_OPEN)
    offer_room = max(0, int(getattr(L, "open_offers", 0) or 0) - int(_cfg(cfg, "OPEN_OFFERS_MARGIN", 4)) - own_open)
    own_threads = sum(1 for t in (world.threads or {}).values()
                      if _g(t, "status") == "open" and _g(t, "team", TEAM) == TEAM)
    tlim = int(getattr(L, "threads", 0) or 0)
    thread_room = max(0, min(tlim, max(1, tlim - int(_cfg(cfg, "THREADS_MARGIN", 1)))) - own_threads)
    live_duels = sum(1 for d in world.duels or () if _g(d, "status", "live") == "live")
    duel_freeze = live_duels > int(_cfg(cfg, "MAX_LIVE_DUELS_FOR_THREADS", 4))
    msgs: set = set()

    out = []
    for it in ordered:
        k, a = it.kind, it.args
        if k in ACCEPT_KINDS:
            if id(it) in chosen_acc:
                out.append(it)
            else:
                drop(it, "R04.accept_budget")
            continue
        if k in ("cancel", "close_thread", "open_pack"):
            target = (k, a.get("offer_id", a.get("thread_id", a.get("asset_id"))))
            if target in seen_targets:
                drop(it, "R04.dup")
                continue
            seen_targets.add(target)
        if k in ("cancel", "list_offer"):
            if listings <= 0:
                drop(it, "R04.listings")
                continue
            if k == "list_offer":
                if offer_room <= 0:
                    drop(it, "R04.offer_room")
                    continue
                offer_room -= 1
            listings -= 1
        elif k == "open_thread":
            if thread_room <= 0 or (duel_freeze and it.tactic != "manual"):
                drop(it, "R04.thread_room" if thread_room <= 0 else "R04.duel_freeze")
                continue
            thread_room -= 1
        elif k == "say":
            key = f"thread:{a.get('thread_id')}"
            if key in msgs:
                drop(it, "R04.msg")
                continue
            msgs.add(key)
        elif k == "duel_say":
            key = f"duel:{a.get('duel_id')}"
            if key in msgs or a.get("duel_id") in accepted_duels:
                drop(it, "R04.msg")
                continue
            msgs.add(key)
        out.append(it)
    return out


# ------------------------------------------------------------------------------------------- helpers

DAY_TIMES_MAX_AGE_S = 6 * 3600      # state/day_times.json older than this is another day's: ignored at start


def _seen_moved(a: Mapping, b: Mapping) -> bool:
    """effective_plan memory changed by more than a minute (the live close is re-projected every read)."""
    for day in set(a or {}) | set(b or {}):
        ra, rb = (a or {}).get(day) or {}, (b or {}).get(day) or {}
        for k in ("close", "stalls"):
            x, y = ra.get(k), rb.get(k)
            if (x is None) != (y is None) or (x is not None and abs(x - y) > 1 / 60):
                return True
    return False


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:                                                    # noqa: BLE001
        return default


def _write_json(path: Path, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, sort_keys=True, ensure_ascii=False, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _is_fatal(e: BaseException) -> bool:
    return isinstance(e, (AssertionError, Fatal)) or e.__class__.__name__ in FATAL_NAMES


def _plain(x: Any) -> Any:
    try:
        from agent.world import thaw
        return thaw(x)
    except Exception:                                                    # noqa: BLE001
        return json.loads(json.dumps(x, default=lambda o: dict(o) if isinstance(o, Mapping) else list(o)))


def manual_args(kind: str, args: Mapping) -> dict:
    """JSON args -> ARGS types (lists become tuples for asset_ids)."""
    a = dict(args)
    if kind == "open_thread" and isinstance(a.get("asset_ids"), list):
        a["asset_ids"] = tuple(a["asset_ids"])
    return a


def _none_pred() -> Prediction:
    try:
        from agent.valuation import predict_none
        return predict_none()
    except Exception:                                                    # noqa: BLE001
        return Prediction(0.0, 0.0, "0", 0, None, "none")


def is_open_world(world: World) -> bool:
    c = world.clock if isinstance(world.clock, Mapping) else {}
    return c.get("paused") is False and c.get("doors") == "open" and "clock" not in (world.down or ())


# --------------------------------------------------------------------------------------------- Runner

class Runner:
    """Holds the per-run state; run() below builds it. Tests drive it with fakes through run()."""

    def __init__(self, *, mode: str, armed: Iterable[str], paths: Paths, plan_cfg: Mapping, transport: Any,
                 journal: Any, gate: Any, sensor: Any, calibrator: Any, cfg: Any, clock: Any,
                 manual: Sequence[Mapping] = (), started: Optional[float] = None, chash: Optional[str] = None):
        self.mode, self.paths, self.plan_cfg = mode, paths, plan_cfg
        self.plan_now: Mapping = plan_cfg          # plan_cfg with today's day end / endgame from the live schedule
        self._sched_seen: dict = {}                # pages.effective_plan memory (last live close, stalls hour)
        self._drop_counts: dict = {}               # choose() drops of this tick, by R04 code (tick row)
        self._sign_noted: set = set()              # duel ids already alarmed for an unreadable days_meaning
        self.late_read_s: Optional[float] = None   # seconds the late-window re-read took (tick row)
        self.transport, self.journal, self.gate, self.sensor = transport, journal, gate, sensor
        self.calibrator, self.cfg, self.clock = calibrator, cfg, clock
        self.started = time.time() if started is None else started
        self.chash = chash
        self.armed: set = set()
        self.state: dict = {"hygiene": {}, "rastro": {}, "duels": {}}
        self.exc: dict = defaultdict(lambda: deque(maxlen=EXC_LIMIT))
        self.missing_noted: set = set()
        self.pending_manual: list = list(manual or ())
        self.dry_manual: set = set()               # intent ids of this tick's `do` orders sent without --live
        self._manual_dry = False                   # True while the Gate executes one of them (armed_now drops manual)
        self.flatten: Optional[str] = None
        self.flatten_ticks = 0
        self.prev: Optional[World] = None          # last World read (any kind): the sensor carries from it
        self.prev_full: Optional[World] = None     # last fully processed World: the calibrator's "before"
        self.last_tick: Optional[int] = None
        self.valuer = None
        self._valuer_key = None
        self.frozen: dict = dict(_read_json(paths.frozen, {}) or {}) if isinstance(_read_json(paths.frozen, {}), dict) else {}
        self.ticks_done = 0
        self.wall = getattr(clock, "wall", None) or time.time   # epoch for the wall close (a sim clock gives its own)
        self._sched_seen = self._load_day_times()
        for t in armed or ():
            self._arm(t, "run --arm", at_start=True)
        self._save_armed()

    # ------------------------------------------------------------ journal
    def j(self, kind: str, **fields) -> None:
        self.journal.write(kind, **fields)        # JournalError propagates: fatal

    def alarm(self, why: str, **fields) -> None:
        try:
            self.j("alarm", why=why, **fields)
        except Exception as e:                                           # noqa: BLE001
            if _is_fatal(e):
                raise

    # ------------------------------------------------------------ arming
    def _arm(self, tactic: str, why: str, at_start: bool = False) -> bool:
        if tactic not in TACTICS:
            self.alarm(f"arm refused: unknown tactic {tactic!r}")
            return False
        if self.mode == "live" and not tactic_green(tactic, self.paths, chash=self.chash):
            self.alarm(f"arm refused: stage of {tactic} not green with this code", tactic=tactic)
            return False
        self.armed.add(tactic)
        self.j("arm", tactic=tactic, why=str(why)[:300], at_start=at_start)
        return True

    def _save_armed(self) -> None:
        try:
            _write_json(self.paths.armed, sorted(self.armed))
        except OSError as e:
            self.alarm(f"armed.json not written: {e.__class__.__name__}")

    def armed_now(self) -> frozenset:
        s = set(self.armed)
        if self.mode == "live" and tactic_green("manual", self.paths, chash=self.chash):
            s.add("manual")
        if self._manual_dry:                       # a `do` without --live is only a "would", even in a live run
            s.discard("manual")
        return frozenset(s)

    def paused(self, tactic: str) -> bool:
        try:
            return bool(self.calibrator.paused(tactic))
        except Exception:                                                # noqa: BLE001
            return True                                                  # fail closed: unknown = paused

    # ------------------------------------------------------------ inbox
    def read_inbox(self) -> None:
        box = Path(self.paths.inbox)
        if not box.is_dir():
            return
        for p in sorted(box.glob("*.json")):
            cmd = _read_json(p, None)
            try:
                if not isinstance(cmd, dict) or cmd.get("cmd") not in INBOX_CMDS:
                    self.alarm("inbox: unreadable or unknown order", file=p.name)
                elif cmd.get("cmd") == "resume" and not cmd.get("tactic"):
                    self.apply_cmd(cmd, p.name)              # only a note (STOP was removed by a person)
                elif _num(cmd.get("ts")) is None or cmd["ts"] < self.started:
                    self.j("cmd", cmd=cmd.get("cmd"), applied=False, why="stale (older than this run)", file=p.name)
                else:
                    self.apply_cmd(cmd, p.name)
            finally:
                try:
                    p.unlink()
                except OSError:
                    pass

    def apply_cmd(self, cmd: Mapping, name: str = "") -> None:
        c, why = cmd.get("cmd"), str(cmd.get("why") or "")[:300]
        self.j("cmd", cmd=c, applied=True, why=why, file=name,
               tactic=cmd.get("tactic"), intent_kind=cmd.get("kind"), args=cmd.get("args"), live=cmd.get("live"))
        if c == "arm":
            if self._arm(str(cmd.get("tactic")), why):
                self._save_armed()
        elif c == "pause":
            self.calibrator.pause(str(cmd.get("tactic")), why or "manual pause")
        elif c == "resume":
            t = cmd.get("tactic")
            if isinstance(t, str) and t:
                self.calibrator.resume(t, why or "manual resume")
            else:
                self.j("resume", what="STOP removed by an operator", why=why)
        elif c == "do":
            self.pending_manual.append(dict(cmd))
        elif c == "flatten":
            self.flatten = why or "flatten"

    # ------------------------------------------------------------ STOP
    def stop_reason(self) -> Optional[str]:
        try:
            return self.gate.stopped()
        except Exception as e:                                           # noqa: BLE001
            return f"stop check failed ({e.__class__.__name__})"

    def write_stop(self, reason: str) -> None:
        try:
            from agent.gate import write_stop
            write_stop(reason, self.paths)
        except Exception:                                                # noqa: BLE001
            p = Path(self.paths.root) / "STOP"
            p.write_text(str(reason)[:500] + "\n", encoding="utf-8")

    # ------------------------------------------------------------ valuer
    def build_valuer(self, world: World) -> Any:
        # Keyed by catalog CONTENT, not id(): the Sensor re-freezes the catalog each tick and CPython reuses the
        # ids of freed objects, so an id key could keep a Valuer with stale released sets / minted counts
        # (Sunday: CHA flips released:true while the runner keeps going).
        cat = hashlib.sha256(json.dumps(_plain(world.catalog), sort_keys=True, default=str).encode()).hexdigest()
        key = (cat, json.dumps(_plain(_g(world.me, "affinity", {})), sort_keys=True),
               tuple(sorted(world.released_sets or ())))
        if key == self._valuer_key and self.valuer is not None:
            return self.valuer
        try:
            from agent.valuation import Valuer
            self.valuer = Valuer(world.catalog, _g(world.me, "affinity", {}) or {}, world.released_sets)
        except Exception as e:                                           # noqa: BLE001 - fail closed: no valuer
            if self.valuer is None:
                self.alarm(f"valuer not built: {e.__class__.__name__}")
            self.valuer = None
        self._valuer_key = key
        return self.valuer

    # ------------------------------------------------------------ execute
    def execute(self, intents: Sequence[Intent], world: World, *, late: bool = False) -> list:
        outs = []
        for it in intents:
            self._manual_dry = it.tactic == "manual" and intent_id(world.tick, it) in self.dry_manual
            try:
                o = self.gate.execute(it, world)
            except Exception as e:                                       # noqa: BLE001
                if _is_fatal(e):
                    raise
                self.alarm(f"execute error {e.__class__.__name__}: {str(e)[:200]}", tactic=it.tactic,
                           intent_kind=it.kind)
                continue
            finally:
                self._manual_dry = False
            outs.append((it, o))
        return outs

    def manual_intent(self, cmd: Mapping, world: World) -> Optional[Intent]:
        kind = cmd.get("kind")
        try:
            args = manual_args(str(kind), cmd.get("args") or {})
            why = str(cmd.get("why") or "manual")[:300]
            it = make_intent(kind, "manual", args, why, "manual order", _none_pred(), priority=10_000)
            pred = None
            fn = getattr(self.gate, "_predict", None)
            if callable(fn):
                try:
                    pred = fn(it, world)
                except Exception:                                        # noqa: BLE001 - Gate will refuse (G07)
                    pred = None
            if isinstance(pred, Prediction):
                it = make_intent(kind, "manual", args, why, "manual order", pred, priority=10_000)
            return it
        except Exception as e:                                           # noqa: BLE001
            self.alarm(f"manual order rejected: {e.__class__.__name__}: {str(e)[:200]}")
            return None

    def flatten_intents(self, world: World) -> list:
        """Cancel our open bids/swaps (want a card) and close our open buy threads."""
        cmds = []
        for o in world.my_offers or ():
            if _g(o, "maker") != TEAM or _g(o, "status") not in OWN_OPEN or type(_g(o, "id")) is not int:
                continue
            want = _g(o, "want", {}) or {}
            if _g(want, "cards") or _g(want, "types"):
                cmds.append({"kind": "cancel", "args": {"offer_id": o["id"], "ref": None}, "why": "flatten"})
        for tid, t in (world.threads or {}).items():
            if _g(t, "status") != "open" or _g(t, "team", TEAM) != TEAM or type(tid) is not int:
                continue
            topic = _g(t, "topic", {}) or {}
            if _g(topic, "buy") is not None:
                cmds.append({"kind": "close_thread", "args": {"thread_id": tid, "ref": None}, "why": "flatten"})
        return [x for x in (self.manual_intent(c, world) for c in cmds) if x is not None]

    # ------------------------------------------------------------ tactics
    def _tactic_failed(self, module: str, world: World, e: BaseException) -> None:
        self.alarm(f"tactic {module} raised {e.__class__.__name__}: {str(e)[:200]}", tactic=module, tick=world.tick)
        q = self.exc[module]
        q.append(world.tick)
        if len(q) >= EXC_LIMIT and world.tick - q[0] < EXC_WINDOW:
            for t in MODULE_TACTICS.get(module, (module,)):
                self.calibrator.pause(t, f"{EXC_LIMIT} exceptions in {EXC_WINDOW} ticks")

    def _module(self, name: str, modpath: str) -> Any:
        try:
            return importlib.import_module(modpath)
        except Exception as e:                                           # noqa: BLE001
            if name not in self.missing_noted:
                self.missing_noted.add(name)
                self.alarm(f"tactic {name} not available: {e.__class__.__name__}")
            return None

    def propose_all(self, world: World, book: Any, needs: list) -> list:
        intents: list = []
        v, cfg, pc = self.valuer, self.cfg, self.plan_now
        for name, modpath in TACTIC_MODULES:
            mod = self._module(name, modpath)
            if mod is None:
                continue
            try:
                if name == "hygiene":
                    got = mod.propose(world, book, v, cfg, pc, self.state["hygiene"])
                elif name == "dealers":
                    got = mod.propose(world, book, v, cfg, pc, needs, mod.DealerState.rebuild(world, self.journal))
                elif name == "rastro":
                    got = mod.propose(world, book, v, cfg, pc, needs, self.state["rastro"])
                else:
                    got = mod.propose(world, cfg, pc, dict(pc.get("duels") or {}), self.state["duels"])
                intents.extend(x for x in (got or ()) if isinstance(x, Intent))
            except Exception as e:                                       # noqa: BLE001 - INV-19: only this tactic
                if _is_fatal(e):
                    raise
                self._tactic_failed(name, world, e)
        return intents

    # ------------------------------------------------------------ one tick
    def fast_path(self) -> None:
        """Startup / first open-doors tick: clock + me/offers -> J0 startup cancels only."""
        if not Path(self.paths.baseline).exists():
            return
        try:
            if self.journal.pending():
                return                    # reconcile needs the full World first
        except Exception as e:                                           # noqa: BLE001
            if _is_fatal(e):
                raise
            return
        try:
            world = self.sensor.fast(self.prev)
        except Exception as e:                                           # noqa: BLE001
            if _is_fatal(e):
                raise
            self.alarm(f"fast path read failed: {e.__class__.__name__}")
            return
        if "me/offers" in (world.down or ()) or "clock" in (world.down or ()):
            return
        self.gate.valuer = None
        self.gate.begin_tick(world)
        self.gate.reconcile(world)
        if self.stop_reason():
            raise Fatal(self.stop_reason() or "STOP")
        try:
            from agent.tactics import hygiene
            wanted = {x for x in (self.plan_cfg.get("startup_cancels") or ()) if type(x) is int}
            its = [it for it in hygiene.startup(world, None, self.plan_cfg)
                   if it.kind == "cancel" and it.args.get("offer_id") in wanted]
        except Exception as e:                                           # noqa: BLE001
            if _is_fatal(e):
                raise
            self._tactic_failed("hygiene", world, e)
            return
        self.execute(choose(its, world, self.cfg), world)

    def tick_once(self) -> bool:
        """One full tick. Returns True if a new tick was processed."""
        if self.prev is not None and not is_open_world(self.prev):
            w = self.sensor.poll(self.prev)              # keyless clock + schedule while paused / doors closed
            if not is_open_world(w):
                self.prev = w
                self.wait(w)
                return False
            self.fast_path()                             # first tick with open doors
        world, _secrets = self.sensor.snapshot(self.prev)
        if self.last_tick is not None and world.tick == self.last_tick:
            self.wait(world)
            return False
        if not is_open_world(world):
            self.prev = world
            self.wait(world)
            return False
        if not Path(self.paths.baseline).exists() and BASELINE_SOURCES & set(world.down or ()):
            self.alarm("no baseline yet and a baseline source is down: tick skipped",
                       down=sorted(BASELINE_SOURCES & set(world.down)))
            self.prev = world
            self.wait(world)
            return False

        valuer = self.build_valuer(world)
        self.gate.valuer = valuer
        msgs = self.gate.begin_tick(world)
        for m in msgs or ():
            if str(m).startswith("STOP") or "failed" in str(m) or "not built" in str(m):
                self.alarm(f"begin_tick: {m}", tick=world.tick)
        for r in self.gate.reconcile(world) or ():
            if isinstance(r, Mapping) and r.get("action") == "pause" and r.get("tactic") in TACTICS:
                self.calibrator.pause(r["tactic"], f"unreconciled intent {r.get('id')}")
            elif isinstance(r, Mapping) and r.get("action") == "alarm":
                self.alarm(f"reconcile: {r.get('why')}", id=r.get("id"))
        if self.stop_reason():
            raise Fatal(self.stop_reason() or "STOP")

        try:
            self.calibrator.on_tick(self.prev_full, world)
        except Exception as e:                                           # noqa: BLE001
            if _is_fatal(e):
                raise
            self.alarm(f"calibrator error {e.__class__.__name__}: {str(e)[:200]}")
        reasons = list(self.calibrator.stop_reasons() or ())
        if reasons:
            raise Fatal("calibrator: " + "; ".join(map(str, reasons))[:400])

        self.update_plan(world)
        self.note_days_sign(world)
        needs = self.plan_needs(world, valuer)
        book = self.gate.book

        intents = []
        if self.flatten is None and book is not None:
            intents = self.propose_all(world, book, needs)
        self.dry_manual = set()
        for cmd in self.pending_manual:
            it = self.manual_intent(cmd, world)
            if it is not None:
                intents.append(it)
                if cmd.get("live") is not True:          # only an order that says live is sent for real
                    self.dry_manual.add(intent_id(world.tick, it))
        self.pending_manual = []
        flat: list = []
        if self.flatten is not None:
            flat = self.flatten_intents(world)
            intents = [it for it in intents if it.tactic == "manual"] + flat

        intents, shadow = self.split_would(intents)
        drops: list = []
        chosen = choose(intents, world, self.cfg, drops)
        self.journal_drops(world, drops)
        early = [it for it in chosen if it.kind != "duel_accept"]
        held = [it for it in chosen if it.kind == "duel_accept"]
        outs = self.execute(early, world)
        if self.flatten is not None:
            # one tick cancels at most the listings budget: keep flattening tick after tick until no own bid / buy
            # thread is left, then STOP (dry: nothing changes, so one pass; FLATTEN_MAX_TICKS bounds a stuck cancel)
            self.flatten_ticks += 1
            if not flat or self.mode != "live" or self.flatten_ticks >= FLATTEN_MAX_TICKS:
                why = self.flatten if not flat else f"{self.flatten} ({len(flat)} left after {self.flatten_ticks} ticks)"
                self.write_stop(f"flatten: {why}")
                self.j("stop", reason=f"flatten: {why}", tick=world.tick)
                raise Fatal(f"flatten: {why}")
        if self.flatten is None and (held or world.duels):     # no late duel accepts while flattening
            outs += self.late_window(world, held, outs)
        if shadow:
            outs += self.execute(choose(shadow, world, self.cfg), world)   # "would" rows only (Gate step 7)

        self.tick_row(world, outs)
        self.prev = world
        self.prev_full = world
        self.last_tick = world.tick
        self.ticks_done += 1
        if world.tick % SNAP_EVERY == 0:
            self.snap(world)
        return True

    def split_would(self, intents: list) -> tuple:
        """Live: (intents that may act, intents of paused / unarmed tactics). The second only journal "would" and run
        after everything else, so they never take the accept slot or the listing budget (Sat: a paused rastro took
        4 of 6 listing slots every tick). Dry: everything is a "would" anyway -> (intents, [])."""
        if self.mode != "live":
            return list(intents), []
        armed = self.armed_now()
        act, shadow = [], []
        for it in intents:
            ok = it.tactic == "manual" or (it.tactic in armed and not self.paused(it.tactic))
            (act if ok else shadow).append(it)
        return act, shadow

    def journal_drops(self, world: World, drops: list) -> None:
        """A manual order left out by choose() gets its own 'dropped' row (operators must see why it did nothing);
        tactic drops only count, in the tick row."""
        counts: dict = defaultdict(int)
        for it, code in drops:
            counts[code] += 1
            if it.tactic == "manual":
                try:
                    iid = intent_id(world.tick, it)
                except Exception:                                        # noqa: BLE001
                    iid = None
                self.j("dropped", id=iid, tactic=it.tactic, intent_kind=it.kind, code=code, tick=world.tick)
        self._drop_counts = dict(counts)

    def note_days_sign(self, world: World) -> None:
        """One alarm per two-issue duel whose days_meaning the sensor could not read (days_sign None: tactic and Gate
        fall back to the role's sign) or read against the role (days_sign_conflict: both use -1, |w|*d and day 0;
        talk.checked_sign). Either way the operator should know the wording changed."""
        for d in world.duels or ():
            did, issues = _g(d, "duel", _g(d, "id")), _g(d, "issues") or ()
            if "days" not in issues or did in self._sign_noted:
                continue
            if _g(d, "days_sign_conflict"):
                why = "duel days_meaning contradicts the role: days sign -1 (each day costs us)"
            elif _g(d, "days_sign") not in (1, -1):
                why = "duel days_meaning not recognised: days sign taken from the role"
            else:
                continue
            self._sign_noted.add(did)
            self.alarm(why, duel=did, role=_g(d, "role"), tick=world.tick)

    def _day_times_path(self) -> Path:
        return Path(self.paths.state) / "day_times.json"

    def _load_day_times(self) -> dict:
        """The effective_plan memory a previous process of today left (night review E2E-1/S4: the stalls close at
        14:00 leaves 'upcoming' once fired, so a cold restart after it brought back a 14:55 dealer day end and a
        stream of refused open_threads). Older than DAY_TIMES_MAX_AGE_S (another day) or unreadable -> {}."""
        raw = _read_json(self._day_times_path(), {})
        try:
            if not isinstance(raw, dict) or not (0 <= float(self.wall()) - float(raw["saved"]) <= DAY_TIMES_MAX_AGE_S):
                return {}
            out = {}
            for day, rec in (raw.get("seen") or {}).items():
                if isinstance(day, str) and isinstance(rec, dict):
                    out[day] = {k: (float(rec[k]) if type(rec.get(k)) in (int, float) and math.isfinite(rec[k])
                                    else None) for k in ("close", "stalls")}
            return out
        except Exception:                                                # noqa: BLE001 - fail closed: no memory
            return {}

    def _save_day_times(self) -> None:
        try:
            _write_json(self._day_times_path(), {"saved": float(self.wall()), "seen": self._sched_seen})
        except Exception as e:                                           # noqa: BLE001
            self.alarm(f"day_times.json not written: {e.__class__.__name__}")

    def update_plan(self, world: World) -> None:
        """Today's day end / endgame from the live schedule (pages.effective_plan); journal a 'param' row on change."""
        try:
            from agent.tactics import pages
            before = self._sched_seen
            pc, self._sched_seen = pages.effective_plan(self.plan_cfg, world, self._sched_seen, now=self.wall())
            if self.mode == "live" and _seen_moved(before, self._sched_seen):
                self._save_day_times()
        except Exception as e:                                           # noqa: BLE001 - keep the last plan
            if _is_fatal(e):
                raise
            self.alarm(f"effective_plan failed: {e.__class__.__name__}: {str(e)[:200]}")
            return
        day = pages.today(world)
        def hours(p):
            de = (p.get("day_end_hours") or {}).get(day)
            eg = ((p.get("closer") or {}).get("endgame_hours") or {}).get(day)
            return tuple(round(x, 3) if type(x) in (int, float) and math.isfinite(x) else None for x in (de, eg))
        old, new = hours(self.plan_now), hours(pc)
        self.plan_now = pc
        moved = any((a is None) != (b is None) or (a is not None and abs(a - b) > 1 / 60) for a, b in zip(old, new))
        if moved:
            seen = self._sched_seen.get(day) or {}
            self.j("param", name="day_times", game_day=day, day_end=new[0], endgame=new[1], close=seen.get("close"),
                   stalls=seen.get("stalls"), tick=world.tick)

    def plan_needs(self, world: World, valuer: Any) -> list:
        if valuer is None:
            return []
        try:
            from agent.tactics import pages
            needs, frozen = pages.plan(world, valuer, self.plan_now, self.frozen)
        except Exception as e:                                           # noqa: BLE001
            if _is_fatal(e):
                raise
            self.alarm(f"pages.plan failed: {e.__class__.__name__}: {str(e)[:200]}")
            return []
        if frozen != self.frozen:
            self.frozen = dict(frozen)
            try:
                _write_json(self.paths.frozen, self.frozen)
            except OSError as e:
                self.alarm(f"frozen.json not written: {e.__class__.__name__}")
        try:
            self.sensor.want_values([n.ref for n in needs])
        except Exception:                                                # noqa: BLE001
            pass
        if self.gate.book is not None:
            try:
                self.gate.book = dataclasses.replace(self.gate.book,
                                                     needs=MappingProxyType({n.ref: n for n in needs}))
            except Exception as e:                                       # noqa: BLE001
                self.alarm(f"book needs not set: {e.__class__.__name__}")
        return list(needs)

    def late_window(self, world: World, held: list, early_outs: list) -> list:
        used = sum(1 for it, o in early_outs if it.kind in ACCEPT_KINDS and o.status in ("sent", "would", "unknown"))
        budget = max(0, int(getattr(world.limits, "accepts", 0) or 0) - (used if _cfg(self.cfg, "DUEL_ACCEPT_SHARED", True) else 0))
        if budget <= 0:
            return []
        margin = float(_cfg(self.cfg, "TICK_MARGIN_S", 2.0))
        mid = world.tick_deadline + margin - float(world.tick_seconds) / 2.0
        now = self.clock.now()
        if now < mid:
            self.clock.sleep(mid - now)
        try:
            t_read = self.clock.now()
            try:
                fresh, _ = self.sensor.snapshot(world, late=True)   # reduced read: duel_accept needs clock + duels
            except TypeError:                                        # a sensor without the keyword (test fakes)
                fresh, _ = self.sensor.snapshot(world)
            self.late_read_s = round(self.clock.now() - t_read, 3)
            self.prev = fresh
        except Exception as e:                                           # noqa: BLE001
            if _is_fatal(e):
                raise
            self.alarm(f"late window re-read failed: {e.__class__.__name__}")
            return []
        if fresh.tick != world.tick or "duels" in (fresh.down or ()) or not is_open_world(fresh):
            return []
        mod = self._module("duels", "agent.tactics.duels")
        if mod is None:
            return []
        try:
            got = mod.propose(fresh, self.cfg, self.plan_now, dict(self.plan_now.get("duels") or {}),
                              self.state["duels"])
        except Exception as e:                                           # noqa: BLE001
            if _is_fatal(e):
                raise
            self._tactic_failed("duels", fresh, e)
            return []
        acc = [it for it in got or () if isinstance(it, Intent) and it.kind == "duel_accept"]
        acc.sort(key=lambda it: (accept_deadline(it, fresh), -int(it.priority)))
        return self.execute(acc[:budget], fresh, late=True)

    def tick_row(self, world: World, outs: list) -> None:
        b = self.gate.book
        try:
            from agent.calibrate import points_of
            pts = points_of(world.me)
        except Exception:                                                # noqa: BLE001
            pts = None
        counts: dict = defaultdict(int)
        for _, o in outs:
            counts[o.status] += 1
        extra = {"dropped": self._drop_counts} if getattr(self, "_drop_counts", None) else {}
        self._drop_counts = {}
        if getattr(self, "late_read_s", None) is not None:
            extra["late_read_s"] = self.late_read_s
            self.late_read_s = None
        self.j("tick", tick=world.tick, cash=_g(world.me, "cash"), cash_free=getattr(b, "cash_free", None),
               points=pts, round=world.round, reading=world.reading, down=sorted(world.down or ()),
               outcomes=dict(counts), armed=sorted(self.armed_now()), **extra)

    def snap(self, world: World) -> None:
        try:
            from agent.redact import redact
            d = {f.name: _plain(getattr(world, f.name)) for f in dataclasses.fields(world)
                 if f.name not in ("catalog",)}
            d["down"] = sorted(world.down or ())
            d["released_sets"] = sorted(world.released_sets or ())
            _write_json(Path(self.paths.snaps) / f"{world.tick}.json", redact(d))
        except Exception as e:                                           # noqa: BLE001
            self.alarm(f"snapshot not written: {e.__class__.__name__}")

    # ------------------------------------------------------------ waiting
    def wait(self, world: Optional[World]) -> None:
        now = self.clock.now()
        if world is None:
            s = 5.0
        elif not is_open_world(world):
            nti = _num(_g(world.clock, "next_tick_in")) or 0.0
            s = max(5.0, nti)
        else:
            # tick_deadline is taken before the clock GET (conservative); the GET itself may wait on the limiter,
            # so wake up WAKE_PAD_S after the estimated tick end, not 0.3 s (M17: avoids a stale extra snapshot)
            s = world.tick_deadline + float(_cfg(self.cfg, "TICK_MARGIN_S", 2.0)) - now + WAKE_PAD_S
        self.clock.sleep(min(MAX_SLEEP_S, max(0.5, s)))

    def loop(self, max_ticks: Optional[int]) -> int:
        iterations = 0
        cap = None if max_ticks is None else max(1, max_ticks) * 6 + 6
        s = self.stop_reason()
        if s:
            self.j("stop", reason=f"STOP present at start: {s}")
            return 2
        self.read_inbox()
        self.fast_path()
        while max_ticks is None or self.ticks_done < max_ticks:
            iterations += 1
            if cap is not None and iterations > cap:
                break
            self.read_inbox()
            s = self.stop_reason()
            if s:
                self.j("stop", reason=s)
                return 2
            try:
                processed = self.tick_once()
                if processed is True and (max_ticks is None or self.ticks_done < max_ticks):
                    self.wait(self.prev)     # M17: sleep to the next tick instead of re-reading the same tick
            except Exception as e:                                       # noqa: BLE001
                if _is_fatal(e):
                    raise
                self.alarm(f"tick error {e.__class__.__name__}: {str(e)[:200]}")
                self.wait(self.prev)
        return 0


# ------------------------------------------------------------------------------------------------ run

class _SysClock:
    @staticmethod
    def now() -> float:
        return time.monotonic()

    @staticmethod
    def sleep(seconds: float) -> None:
        time.sleep(max(0.0, seconds))


def _make_cfg(plan_cfg: Mapping) -> Any:
    from agent.guards import Cfg
    cfg = Cfg()
    upd = {}
    # plan days_sign is not copied: one sign for both duel roles is wrong by construction (talk.days_sign_of reads
    # the duel: sensor days_sign, server days_meaning, then role)
    if type(plan_cfg.get("grant_lookahead_ticks")) is int:
        upd["GRANT_LOOKAHEAD_TICKS"] = plan_cfg["grant_lookahead_ticks"]
    fb = (plan_cfg.get("duels") or {}).get("days_weight_fallback") if isinstance(plan_cfg.get("duels"), Mapping) else None
    if type(fb) in (int, float) and fb > 0:
        upd["DAYS_WEIGHT_FALLBACK"] = float(fb)
    if type(plan_cfg.get("resupply_min")) in (int, float):
        upd["RESUPPLY_MIN"] = float(plan_cfg["resupply_min"])
    return dataclasses.replace(cfg, **upd) if upd else cfg


def run(mode: str, armed: Iterable[str], *, paths: Paths, plan_path: Path, max_ticks: Optional[int] = None,
        base_url: Optional[str] = None, transport: Any = None, clock: Any = None,
        manual: Sequence[Mapping] = ()) -> int:
    """The runner. mode in {"live","dry"}. See module NOTES for exit codes. `manual`: one-shot `do` orders."""
    if mode not in ("live", "dry"):
        print(f"run: bad mode {mode!r}")
        return 1
    clock = clock or _SysClock()
    from agent.execution import writer_lock
    try:
        with writer_lock(paths):
            return _run_locked(mode, armed, paths=paths, plan_path=plan_path, max_ticks=max_ticks,
                               base_url=base_url, transport=transport, clock=clock, manual=manual)
    except RuntimeError as e:
        if "writer lock" in str(e):
            print(f"run: {e}")
            return 3
        raise


def _run_locked(mode, armed, *, paths, plan_path, max_ticks, base_url, transport, clock, manual) -> int:
    from agent import transport as T
    from agent.calibrate import Calibrator
    from agent.gate import Gate, write_stop
    from agent.journal import Journal
    from agent.tactics import pages
    from agent.world import Sensor

    started = time.time()
    try:
        plan_cfg = pages.load_plan(Path(plan_path))
    except Exception as e:                                               # noqa: BLE001 - fail closed
        print(f"run: plan unreadable ({e.__class__.__name__}: {e})")
        return 1
    cfg = _make_cfg(plan_cfg)
    if transport is None:
        try:
            from agent.client import _load_env
            _load_env()
        except Exception:                                                # noqa: BLE001
            pass
        key = os.environ.get("BAZAAR_KEY")
        if not key:
            print("run: BAZAAR_KEY is not set")
            return 1
        url = base_url or os.environ.get("BAZAAR_URL") or PROD_URL
        transport = T.GuardedTransport(url, key, mode=("live" if mode == "live" else "dry"), paths=paths,
                                       limiter=T.RateLimiter(rate=RUNNER_RATE, burst=RUNNER_BURST,
                                                             reserve=RUNNER_RESERVE, clock=clock))
    if mode == "live" and getattr(transport, "mode", None) != "live":
        print("run: --live needs a live transport")
        return 1
    url = base_url or getattr(transport, "url", None)
    journal = None
    try:
        journal = Journal(paths.journal, mode=mode, writer=True, lock_path=paths.lock)
        public = T.RateLimiter(rate=1.0, burst=1, reserve=0, clock=clock)
        sensor = Sensor(transport, url, journal, paths, public, clock)
        calibrator = Calibrator(journal, paths)
        holder: dict = {}
        gate = Gate(transport, journal, None, cfg, plan_cfg, paths, mode=mode,
                    armed=lambda: holder["r"].armed_now(), paused=lambda t: holder["r"].paused(t), clock=clock)
        journal.write("cmd", cmd="run", applied=True, mode=mode, armed=sorted(set(armed or ())),
                      max_ticks=max_ticks)
        r = Runner(mode=mode, armed=armed, paths=paths, plan_cfg=plan_cfg, transport=transport, journal=journal,
                   gate=gate, sensor=sensor, calibrator=calibrator, cfg=cfg, clock=clock, manual=manual,
                   started=started, chash=code_hash())
        holder["r"] = r
        return r.loop(max_ticks)
    except KeyboardInterrupt:
        return 0
    except Exception as e:                                               # noqa: BLE001
        if not _is_fatal(e):
            raise
        reason = f"{e.__class__.__name__}: {str(e)[:300]}"
        try:
            write_stop(reason, paths)
        except Exception:                                                # noqa: BLE001
            pass
        if journal is not None:
            try:
                journal.write("stop", reason=reason)
            except Exception:                                            # noqa: BLE001
                pass
        print(f"run: STOP ({reason})")
        return 2
