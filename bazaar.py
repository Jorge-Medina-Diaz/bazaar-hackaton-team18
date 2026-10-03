"""M16 cli: the single entry point of the t18 harness (docs/harness-spec.md §5, §10, §13; INV-02, INV-21, INV-22).

    python3 bazaar.py selftest                       per-stage unittest runs -> state/selftest.json {stage: {green, code_hash}}
    python3 bazaar.py clockcheck                     keyless GET clock + schedule: N/M/C/P/?, round, t_hours, paused, upcoming
    python3 bazaar.py run [--live] [--arm a,b]       the runner (takes state/writer.lock; without --live: dry, 0 writes)
    python3 bazaar.py arm <tactic> --why "..."       order to the running runner (refused if the stage is red)
    python3 bazaar.py pause <tactic> --why "..."     order to the running runner
    python3 bazaar.py do <kind> --args '<json>' --why "..." [--live]
                                                     one manual intent through the Gate (inbox if the runner is alive,
                                                     else a one-tick run of our own; without --live it is a dry "would")
    python3 bazaar.py stop "reason" [--flatten]      STOP in the repo root (Paths.root, not the cwd)
    python3 bazaar.py resume [tactic] --why "..."    no tactic: delete STOP; with a tactic: order to resume that tactic
    python3 bazaar.py status                         0 API calls: journal (reader), state files, STOP, lock holder
    python3 bazaar.py replay-friday | report

NOTES (M16, night build)
- The CLI never writes the journal, armed.json or pauses.json (INV-22): orders go to state/inbox/<ns>-<cmd>.json
  (temp file + os.replace) and the runner applies and journals them. Orders are only written while a runner holds the
  writer lock (probe: try to take the lock; busy = alive); otherwise `arm`/`pause` refuse (exit 1) because a later run
  ignores stale orders anyway. `stop --flatten` with no runner alive writes STOP at once and says flatten did not run.
- `do` orders carry "live": a.live and the runner sends one for real only if it says live. `do` without --live is
  refused while a live runner holds the lock (mode read from the lock's argv; unreadable counts as live).
- `--root DIR` (first argument) relocates Paths for tests; production never passes it. Default Paths.at() is anchored
  on the package location, so `stop` from any folder writes <repo>/STOP.
- selftest: one unittest subprocess per stage (env: BAZAAR_TEST=1, BAZAAR_NO_DOTENV=1, no key/url), green = exit 0
  and at least STAGE_MIN tests ran (0 tests -> red). Test files that do not exist yet (M17) are listed as missing but
  do not turn the stage red; tests/test_bots.py is not in any stage (known failures, informational). If logs/run or
  state/ (except selftest.json and writer.lock) change during the selftest, every stage is red.
- replay-friday runs tests/test_replay_friday.py when it exists (M17); otherwise exits 1 ("not built").
- Exit codes: 0 ok, 1 refused / usage / red, 2 STOP from run, 3 writer lock busy (run).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

REPO = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from agent.contracts import KINDS, PROD_URL, TACTICS, Paths, make_intent  # noqa: E402

STAGES = ("core", "hygiene", "dealers", "rastro", "closer", "duels")
STAGE_FILES = {
    "core": ("test_contracts", "test_transport", "test_journal", "test_valuation", "test_guards", "test_shapes",
             "test_gate", "test_sim", "test_fake_contract", "test_world", "test_calibrate", "test_runner",
             "test_cli", "test_architecture", "test_isolation", "test_e2e_fake", "test_chaos",
             "test_foreign_writer", "test_dry", "test_replay_friday"),
    "hygiene": ("test_hygiene",),
    "dealers": ("test_talk", "test_firewall", "test_pages", "test_dealers"),
    "rastro": ("test_rastro",),
    "closer": ("test_rastro", "test_pages"),
    "duels": ("test_talk", "test_firewall", "test_duels"),
}
STAGE_MIN = {"core": 150, "hygiene": 5, "dealers": 20, "rastro": 5, "closer": 10, "duels": 10}
WATCH_EXCLUDE = frozenset({"selftest.json", "writer.lock"})


def _out(msg: str = "") -> None:
    print(msg, flush=True)


# ------------------------------------------------------------------------------------------ helpers

def _paths(root: Optional[str]) -> Paths:
    return Paths.at(root) if root else Paths.at()


def runner_alive(paths: Paths) -> bool:
    """True if some process holds state/writer.lock (probe by trying to take it)."""
    from agent.execution import writer_lock
    try:
        with writer_lock(paths):
            return False
    except RuntimeError:
        return True


def runner_mode(paths: Paths) -> Optional[str]:
    """"live" / "dry" from the argv the lock holder wrote in state/writer.lock; None if it cannot be read."""
    try:
        txt = Path(paths.lock).read_text(encoding="utf-8", errors="replace").split("\x00")[0].strip()
        argv = json.loads(txt).get("argv")
    except Exception:                                                    # noqa: BLE001
        return None
    if not isinstance(argv, list):
        return None
    return "live" if "--live" in argv else "dry"


def write_order(paths: Paths, cmd: str, **fields: Any) -> Path:
    box = Path(paths.inbox)
    box.mkdir(parents=True, exist_ok=True)
    order = dict(fields, cmd=cmd, ts=time.time())
    name = f"{time.time_ns()}-{cmd}.json"
    tmp = box / f".{name}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(order, f, ensure_ascii=False, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, box / name)
    return box / name


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:                                                    # noqa: BLE001
        return default


def _tree_hash(*dirs: Path) -> str:
    h = hashlib.sha256()
    for d in dirs:
        d = Path(d)
        if not d.exists():
            h.update(b"<none>" + str(d).encode())
            continue
        for p in sorted(x for x in d.rglob("*") if x.is_file()):
            if p.name in WATCH_EXCLUDE:
                continue
            h.update(p.relative_to(d).as_posix().encode() + b"\0")
            try:
                h.update(p.read_bytes())
            except OSError:
                h.update(b"<locked>")
    return h.hexdigest()


# ------------------------------------------------------------------------------------------ selftest

def _test_env() -> dict:
    env = dict(os.environ)
    env.update({"BAZAAR_TEST": "1", "BAZAAR_NO_DOTENV": "1", "PYTHONIOENCODING": "utf-8"})
    env.pop("BAZAAR_KEY", None)
    env.pop("BAZAAR_URL", None)
    return env


def run_tests(modules: Sequence[str], *, pattern: Optional[str] = None, timeout: float = 900.0) -> tuple:
    """(returncode, tests_ran, tail of output). modules: dotted test modules; pattern: discover -p instead."""
    if pattern is not None:
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", pattern]
    else:
        cmd = [sys.executable, "-m", "unittest"] + list(modules)
    try:
        p = subprocess.run(cmd, cwd=str(REPO), env=_test_env(), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, 0, "timeout"
    text = (p.stdout or "") + (p.stderr or "")
    m = re.findall(r"Ran (\d+) tests?", text)
    ran = int(m[-1]) if m else 0
    return p.returncode, ran, text[-1500:]


def selftest(paths: Paths, *, stages: Sequence[str] = STAGES, runner_fn: Callable = run_tests,
             watch_root: Optional[Path] = None) -> int:
    from agent import runner
    if sys.version_info < (3, 9):
        _out("selftest: Python >= 3.9 required")
        return 1
    watch = Path(watch_root) if watch_root is not None else Path(paths.root)
    before = _tree_hash(watch / "logs" / "run", watch / "state")
    chash = runner.code_hash()
    result = {}
    for st in stages:
        files = STAGE_FILES.get(st, ())
        present = [f for f in files if (REPO / "tests" / f"{f}.py").exists()]
        missing = [f for f in files if f not in present]
        if present:
            rc, ran, tail = runner_fn([f"tests.{f}" for f in present])
        else:
            rc, ran, tail = 5, 0, "no test files"
        green = rc == 0 and ran >= STAGE_MIN.get(st, 1) and ran > 0
        result[st] = {"green": green, "code_hash": chash, "tests": ran, "rc": rc, "missing": missing,
                      "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        _out(f"{st:8s} {'GREEN' if green else 'RED  '}  ran={ran} rc={rc}"
             + (f"  missing={','.join(missing)}" if missing else ""))
        if not green:
            _out("   " + tail.strip().replace("\n", "\n   ")[-800:])
    after = _tree_hash(watch / "logs" / "run", watch / "state")
    if after != before:
        _out("selftest: logs/run or state/ changed during the tests -> every stage RED (INV-21)")
        for st in result:
            result[st]["green"] = False
    runner._write_json(Path(paths.selftest), result)
    return 0 if result.get("core", {}).get("green") else 1


# ------------------------------------------------------------------------------------------ status

def status(paths: Paths) -> int:
    """0 API calls: reads files only."""
    from agent.transport import stop_active
    _out(f"root     {paths.root}")
    s = stop_active(paths)
    _out(f"STOP     {s or '-'}")
    lock = Path(paths.lock)
    holder = None
    if lock.exists():
        try:
            txt = lock.read_text(encoding="utf-8", errors="replace").split("\x00")[0].strip()
            holder = json.loads(txt) if txt else None
        except Exception:                                                # noqa: BLE001
            holder = None
    _out(f"lock     {('pid ' + str(holder.get('pid')) + ' ' + ' '.join(holder.get('argv') or [])) if isinstance(holder, dict) else 'free'}")
    _out(f"armed    {_read_json(paths.armed, '-')}")
    _out(f"paused   {sorted((_read_json(paths.pauses, {}) or {}).keys()) if isinstance(_read_json(paths.pauses, {}), dict) else _read_json(paths.pauses, '-')}")
    st = _read_json(paths.selftest, {}) or {}
    _out("stages   " + (" ".join(f"{k}:{'G' if isinstance(v, dict) and v.get('green') else 'R'}" for k, v in st.items())
                       if isinstance(st, dict) and st else "-"))
    if not Path(paths.journal).exists():
        _out("journal  -")
        return 0
    from agent.journal import Journal
    try:
        j = Journal(paths.journal, mode="dry", writer=False)
        rows = list(j.rows())
        pend = j.pending()
        unk = sorted(j.unknown_domains())
    except Exception as e:                                               # noqa: BLE001
        _out(f"journal  unreadable: {e.__class__.__name__}: {e}")
        return 1
    last_tick = next((r for r in reversed(rows) if r.get("kind") == "tick"), None)
    _out(f"journal  {len(rows)} rows, mode {rows[-1].get('mode') if rows else '-'}")
    if last_tick:
        _out(f"tick     {last_tick.get('tick')} cash {last_tick.get('cash')} cash_free {last_tick.get('cash_free')} "
             f"reading {last_tick.get('reading')} down {last_tick.get('down')}")
    _out(f"pending  {len(pend)} {[p.get('id') for p in pend][:10]}")
    _out(f"unknowns {unk[:20]}")
    for kind, n in (("measure", 5), ("alarm", 5), ("stop", 3), ("pause", 5)):
        sel = [r for r in rows if r.get("kind") == kind][-n:]
        for r in sel:
            _out(f"{kind:8s} t{r.get('tick')} " + json.dumps({k: v for k, v in r.items()
                                                             if k not in ("prev", "seq", "ts", "day", "mode", "kind")},
                                                            ensure_ascii=False, default=str)[:240])
    return 0


# ------------------------------------------------------------------------------------------ commands

def cmd_clockcheck(base_url: Optional[str] = None, http: Optional[Callable] = None) -> int:
    from agent.transport import RateLimiter, public_get
    from agent.world import clock_reading, parse_clock
    url = base_url or os.environ.get("BAZAAR_URL") or PROD_URL
    lim = RateLimiter(rate=1.0, burst=1, reserve=0)
    try:
        clock = public_get(url, "/api/clock", lim, http=http)
        sched = public_get(url, "/api/schedule", lim, http=http)
    except Exception as e:                                               # noqa: BLE001
        _out(f"clockcheck: {e.__class__.__name__}: {e}")
        return 1
    try:
        c = parse_clock(clock)
    except Exception:                                                    # noqa: BLE001
        c = None
    reading = clock_reading(c, sched if isinstance(sched, dict) else None)
    up = (sched or {}).get("upcoming") if isinstance(sched, dict) else None
    _out(f"reading {reading}  round {clock.get('round')}  tick {clock.get('tick')}  t_hours {clock.get('t_hours')}  "
         f"paused {clock.get('paused')}  doors {clock.get('doors')}  next_tick_in {clock.get('next_tick_in')}")
    for u in (up or [])[:8]:
        if isinstance(u, dict):
            _out(f"  upcoming {u.get('at_hours')} {u.get('action')} {json.dumps(u.get('params'), default=str)[:120]}")
    return 0


def _arm_ok(paths: Paths, tactic: str) -> Optional[str]:
    from agent import runner
    if tactic not in TACTICS:
        return f"unknown tactic {tactic!r} (one of {', '.join(TACTICS)})"
    if not runner.tactic_green(tactic, paths):
        return f"stage of {tactic} is not green with this code (run selftest)"
    return None


def cmd_run(paths: Paths, a) -> int:
    from agent import runner
    armed = [t for t in (a.arm or "").split(",") if t.strip()]
    armed = [t.strip() for t in armed]
    bad = [t for t in armed if t not in TACTICS]
    if bad:
        _out(f"run: unknown tactics {bad}")
        return 1
    if a.live:
        for t in armed:
            why = _arm_ok(paths, t)
            if why:
                _out(f"run: {t} not armed: {why}")
        armed = [t for t in armed if _arm_ok(paths, t) is None]
    plan = Path(a.plan) if a.plan else REPO / "config" / "plan.json"
    return runner.run("live" if a.live else "dry", armed, paths=paths, plan_path=plan, max_ticks=a.max_ticks)


def cmd_do(paths: Paths, a) -> int:
    from agent import runner
    if a.kind not in KINDS:
        _out(f"do: unknown kind {a.kind!r}")
        return 1
    try:
        args = json.loads(a.args)
        if not isinstance(args, dict):
            raise ValueError("args must be a JSON object")
        make_intent(a.kind, "manual", runner.manual_args(a.kind, args), a.why, "manual order", runner._none_pred())
    except Exception as e:                                               # noqa: BLE001
        _out(f"do: refused: {e}")
        return 1
    order = {"kind": a.kind, "args": args, "why": a.why, "live": bool(a.live)}
    if runner_alive(paths):
        # the runner sends a `do` for real only if the order says live; a dry `do` next to a live runner is refused
        # here so nobody believes a rehearsal is safe (or a real order was rehearsed). Unknown runner mode = live.
        if not a.live and runner_mode(paths) != "dry":
            _out("do: refused: the runner is live; repeat with --live to send it for real (a dry `do` needs a dry "
                 "runner or no runner)")
            return 1
        p = write_order(paths, "do", **order)
        _out(f"do: order left for the runner ({p.name}, {'live' if a.live else 'dry: would only'})")
        return 0
    plan = Path(a.plan) if a.plan else REPO / "config" / "plan.json"
    return runner.run("live" if a.live else "dry", [], paths=paths, plan_path=plan, max_ticks=1,
                      manual=[dict(order, cmd="do")])


def cmd_stop(paths: Paths, a) -> int:
    from agent.gate import write_stop
    reason = " ".join(a.reason).strip() or "manual stop"
    if a.flatten and runner_alive(paths):
        p = write_order(paths, "flatten", why=reason)
        _out(f"stop: flatten order left ({p.name}); the runner cancels bids, closes buy threads, then writes STOP")
        return 0
    write_stop(reason, paths)
    _out(f"stop: STOP written at {Path(paths.root) / 'STOP'}" + (" (no runner alive: flatten not done)" if a.flatten else ""))
    return 0


def cmd_resume(paths: Paths, a) -> int:
    if a.tactic:
        if a.tactic not in TACTICS:
            _out(f"resume: unknown tactic {a.tactic!r}")
            return 1
        if not runner_alive(paths):
            _out("resume: no runner alive (start one; pauses persist in state/pauses.json)")
            return 1
        write_order(paths, "resume", tactic=a.tactic, why=a.why)
        _out(f"resume: order left for {a.tactic}")
        return 0
    removed = []
    for p in Path(paths.root).iterdir():
        low = p.name.lower()
        if p.is_file() and (low == "stop" or low.startswith("stop.")):
            p.unlink()
            removed.append(p.name)
    write_order(paths, "resume", why=a.why)
    _out(f"resume: removed {removed or 'nothing'}")
    return 0


def cmd_order(paths: Paths, cmd: str, a) -> int:
    if cmd == "arm":
        why = _arm_ok(paths, a.tactic)
        if why:
            _out(f"arm: refused: {why}")
            return 1
    elif a.tactic not in TACTICS:
        _out(f"{cmd}: unknown tactic {a.tactic!r}")
        return 1
    if not runner_alive(paths):
        _out(f"{cmd}: no runner alive; use `run --live --arm ...` (orders are only read by a running runner)")
        return 1
    p = write_order(paths, cmd, tactic=a.tactic, why=a.why)
    _out(f"{cmd}: order left for the runner ({p.name})")
    return 0


def cmd_report(paths: Paths) -> int:
    from agent.calibrate import Calibrator
    from agent.journal import Journal
    if not Path(paths.journal).exists():
        _out("report: no journal")
        return 1
    try:
        cal = Calibrator(Journal(paths.journal, mode="dry", writer=False), paths)
        _out(cal.report())
    except Exception as e:                                               # noqa: BLE001
        _out(f"report: {e.__class__.__name__}: {e}")
        return 1
    return 0


def cmd_replay(paths: Paths) -> int:
    if not (REPO / "tests" / "test_replay_friday.py").exists():
        _out("replay-friday: not built (tests/test_replay_friday.py, M17)")
        return 1
    rc, ran, tail = run_tests(["tests.test_replay_friday"])
    _out(tail)
    return 0 if rc == 0 and ran > 0 else 1


# ------------------------------------------------------------------------------------------ main

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="bazaar.py", description="t18 harness")
    ap.add_argument("--root", default=None, help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    sub.add_parser("clockcheck")
    r = sub.add_parser("run")
    r.add_argument("--live", action="store_true")
    r.add_argument("--arm", default="")
    r.add_argument("--max-ticks", type=int, default=None)
    r.add_argument("--plan", default=None)
    for c in ("arm", "pause"):
        p = sub.add_parser(c)
        p.add_argument("tactic")
        p.add_argument("--why", required=True)
    d = sub.add_parser("do")
    d.add_argument("kind")
    d.add_argument("--args", required=True)
    d.add_argument("--why", required=True)
    d.add_argument("--live", action="store_true")
    d.add_argument("--plan", default=None)
    s = sub.add_parser("stop")
    s.add_argument("reason", nargs="*")
    s.add_argument("--flatten", action="store_true")
    rs = sub.add_parser("resume")
    rs.add_argument("tactic", nargs="?", default=None)
    rs.add_argument("--why", required=True)
    sub.add_parser("status")
    sub.add_parser("replay-friday")
    sub.add_parser("report")
    return ap


def main(argv: Sequence[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")      # cp1252 console
    except Exception:                                                    # noqa: BLE001
        pass
    try:
        a = build_parser().parse_args(list(argv))
    except SystemExit as e:
        return int(e.code or 0) if isinstance(e.code, int) else 1
    paths = _paths(a.root)
    c = a.cmd
    if c == "selftest":
        return selftest(paths)
    if c == "clockcheck":
        return cmd_clockcheck()
    if c == "run":
        return cmd_run(paths, a)
    if c in ("arm", "pause"):
        return cmd_order(paths, c, a)
    if c == "do":
        return cmd_do(paths, a)
    if c == "stop":
        return cmd_stop(paths, a)
    if c == "resume":
        return cmd_resume(paths, a)
    if c == "status":
        return status(paths)
    if c == "replay-friday":
        return cmd_replay(paths)
    if c == "report":
        return cmd_report(paths)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
