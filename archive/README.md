# archive/ — superseded by the t18 harness (M18, docs/harness-spec.md §12)

Moved here with `git mv`, so `git log --follow archive/<path>` shows each file's history.

- `*.py`, `agent/*.py`: pre-harness scripts and modules. Every one starts with
  `raise SystemExit(...)  # M18 guard` (after any `from __future__` import): they cannot run or be imported,
  because they could reach the game without the Gate. `tests/test_agent_core.py` checks the guard.
  Do not remove the guard; port what you need into the harness owner module instead.
- `tests/`: suites that tested the archived code (not discovered by `python3 -m unittest discover -s tests`).
  The cases of the old `test_agent_core.py` that test kept modules (offer_safety, execution) stay in
  `tests/test_agent_core.py`.
- `bench.py`, `flags.py` and `docs/duels-strategy.md` came from the Santi branch (merged Sat 3 Oct); the duel
  archetypes in `docs/duels-strategy.md` are still worth reading for the duels tactic.
- `docs/`: old notes, plans and designs (refuted or replaced by docs/knowledge.md, docs/strategy.md and
  docs/harness-spec.md). `docs/README.md` was the old docs index; `docs/santi/` holds the refuted strategies.
- `.mcp.json`: the old information-collector MCP server (`collector_mcp.py`), now disabled.
- The old team sections of the top-level README.md (collector, panel URL, lab, Jorge integration, performance
  observer) are in the git history of README.md before the M18 commit.
