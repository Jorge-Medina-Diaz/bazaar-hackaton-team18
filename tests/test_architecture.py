"""M17: architecture rules checked on the source (INV-01 AST layer 3, INV-13 AST, INV-18 secrets in source).

Design notes
- The scan is AST-based, so docstrings and comments that *mention* a forbidden name do not count; only code does.
- LEGACY lists the Friday modules (now in docs/history/legacy-code/, guarded by SystemExit). They must never come
  back into agent/: no harness module may import those names (checked on the static import graph).
- agent/dashboard.py and agent/client.py are read-only (the dashboard and client("read")).
- INV-13: the literal "text" is allowed in agent/gate.py only inside the REQUEST_FOR body builders (_req_*), which
  must put the "text" key in say/duel_say bodies (by design). The Gate never reads a text field.
"""
from __future__ import annotations

import ast
import os
import re
import unittest
from pathlib import Path

import tests  # noqa: F401  (test isolation)

REPO = Path(__file__).resolve().parents[1]
AGENT = REPO / "agent"

WRITE_OK = {"agent/transport.py", "agent/gate.py"}          # the only files allowed to touch the wire
LEGACY = {"agent/duels.py", "agent/scorer.py", "agent/haggle.py", "agent/information.py", "agent/broker.py",
          "agent/dealers.py"}
HARNESS = {"agent/contracts.py", "agent/redact.py", "agent/transport.py", "agent/client.py", "agent/journal.py",
           "agent/valuation.py", "agent/guards.py", "agent/offer_safety.py", "agent/talk.py", "agent/gate.py",
           "agent/execution.py", "agent/world.py", "agent/calibrate.py", "agent/runner.py"}
FORBIDDEN_MODULES = re.compile(r"^(bazaar_sdk|urllib(\..*)?|http(\.client)?|socket|ssl|requests|httpx|aiohttp)$")
FORBIDDEN_CALLS = {"Bazaar", "Broker"}
FORBIDDEN_ATTR_CALLS = {"_call", "send"}
TEXT_FREE = ["agent/guards.py", "agent/talk.py", "agent/gate.py"]


def rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


def harness_files() -> list:
    files = sorted(AGENT.glob("*.py")) + sorted((AGENT / "tactics").glob("*.py")) + [REPO / "bazaar.py"]
    return [p for p in files if rel(p) not in LEGACY]


def tree(p: Path) -> ast.AST:
    return ast.parse(p.read_text(encoding="utf-8"), filename=str(p))


def violations(p: Path) -> list:
    out = []
    for node in ast.walk(tree(p)):
        if isinstance(node, ast.Import):
            for a in node.names:
                if FORBIDDEN_MODULES.match(a.name):
                    out.append(f"import {a.name} (line {node.lineno})")
        elif isinstance(node, ast.ImportFrom):
            if node.module and FORBIDDEN_MODULES.match(node.module):
                out.append(f"from {node.module} import (line {node.lineno})")
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in FORBIDDEN_CALLS:
                out.append(f"{f.id}( (line {node.lineno})")
            if isinstance(f, ast.Attribute) and (f.attr in FORBIDDEN_CALLS or f.attr in FORBIDDEN_ATTR_CALLS):
                out.append(f".{f.attr}( (line {node.lineno})")
            if isinstance(f, (ast.Name, ast.Attribute)) and getattr(f, "id", getattr(f, "attr", "")) in (
                    "import_module", "__import__"):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                            and FORBIDDEN_MODULES.match(arg.value):
                        out.append(f"dynamic import {arg.value} (line {node.lineno})")
        elif isinstance(node, ast.Name) and node.id == "write_permit":
            out.append(f"write_permit (line {node.lineno})")
        elif isinstance(node, ast.Attribute) and node.attr == "write_permit":
            out.append(f".write_permit (line {node.lineno})")
        elif isinstance(node, ast.Constant) and node.value == "write_permit":
            out.append(f"'write_permit' (line {node.lineno})")
    return out


def imported_agent_modules(p: Path) -> set:
    out = set()
    for node in ast.walk(tree(p)):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names if a.name.startswith("agent")}
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "agent":
                out |= {f"agent.{a.name}" for a in node.names}
            elif node.module.startswith("agent"):
                out.add(node.module)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and re.fullmatch(r"agent(\.\w+)+",
                                                                                            node.value):
            out.add(node.value)                                   # importlib.import_module("agent.x") / lazy names
    return out


class TestSingleWritePath(unittest.TestCase):
    """INV-01 layer 3: no SDK, urllib, http.client, socket, Bazaar(, Broker(, ._call(, .send(, write_permit
    in agent/ or bazaar.py outside agent/transport.py and agent/gate.py."""

    def test_harness_files_exist(self):
        for f in HARNESS | {"agent/tactics/hygiene.py", "agent/tactics/rastro.py", "bazaar.py"}:
            self.assertTrue((REPO / f).exists(), f)

    def test_no_forbidden_names_outside_transport_and_gate(self):
        bad = {}
        for p in harness_files():
            if rel(p) in WRITE_OK:
                continue
            v = violations(p)
            if v:
                bad[rel(p)] = v
        self.assertEqual(bad, {})

    def test_detector_catches_shortcuts(self):
        """The scanner itself must see the red-team shortcuts (otherwise the test above proves nothing)."""
        samples = ["import urllib.request", "from bazaar_sdk import Bazaar", "import http.client", "import socket",
                   "Bazaar('u', 'k')", "x.Broker()", "t._call('POST', '/api/offers')", "t.send(1)",
                   "write_permit(1)", "importlib.import_module('bazaar_sdk')", "__import__('socket')"]
        tmp = Path(os.environ.get("TEMP", "/tmp")) / f"t18_arch_{os.getpid()}.py"
        try:
            for s in samples:
                tmp.write_text(s + "\n", encoding="utf-8")
                self.assertTrue(violations(tmp), s)
            tmp.write_text('"""mentions ._call( and bazaar_sdk in a docstring only"""\nx = 1\n', encoding="utf-8")
            self.assertEqual(violations(tmp), [])
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass

    def test_harness_never_imports_legacy_modules(self):
        legacy_mods = {f[:-3].replace("/", ".") for f in LEGACY}
        bad = {}
        for p in harness_files():
            hit = imported_agent_modules(p) & legacy_mods
            if hit:
                bad[rel(p)] = sorted(hit)
        self.assertEqual(bad, {})

    def test_only_transport_and_gate_import_the_sdk_or_urllib(self):
        users = set()
        for p in harness_files():
            for node in ast.walk(tree(p)):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                if any(FORBIDDEN_MODULES.match(n) for n in names):
                    users.add(rel(p))
        self.assertTrue(users <= WRITE_OK, users)
        self.assertIn("agent/transport.py", users)                   # the transport really owns the wire

    def test_admin_route_literal_only_in_transport_and_fake_server(self):
        allowed = {"agent/transport.py", "sim/fake_server.py"}
        files = harness_files() + sorted((REPO / "sim").glob("*.py")) + sorted(LEGACY_PATHS())
        bad = []
        for p in files:
            for node in ast.walk(tree(p)):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and "/api/admin" in node.value.lower():
                    if rel(p) not in allowed:
                        bad.append(f"{rel(p)}:{getattr(node, 'lineno', '?')}")
        self.assertEqual(bad, [])

    def test_open_venue_not_a_kind(self):
        from agent.contracts import KINDS
        self.assertNotIn("open_venue", KINDS)                        # D4: no own venue in this build


def LEGACY_PATHS():
    return [REPO / f for f in LEGACY if (REPO / f).exists()]


class TestNoForeignText(unittest.TestCase):
    """INV-13 (AST): `untrusted` and the literal "text" do not appear in tactics, guards, talk or gate
    (gate: allowed only inside the REQUEST_FOR body builders _req_*)."""

    def _hits(self, p: Path) -> list:
        t = tree(p)
        allowed_ranges = []
        if rel(p) == "agent/gate.py":
            for node in ast.walk(t):
                if isinstance(node, ast.FunctionDef) and node.name.startswith("_req_"):
                    allowed_ranges.append((node.lineno, node.end_lineno))
        docstrings = set()
        for node in ast.walk(t):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", [])
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                    docstrings.add(id(body[0].value))
        out = []
        for node in ast.walk(t):
            ln = getattr(node, "lineno", 0)
            if isinstance(node, ast.Constant) and node.value == "text" and id(node) not in docstrings:
                if not any(a <= ln <= b for a, b in allowed_ranges):
                    out.append(f"'text' line {ln}")
            if isinstance(node, ast.Name) and "untrusted" in node.id.lower():
                out.append(f"name {node.id} line {ln}")
            if isinstance(node, ast.Attribute) and "untrusted" in node.attr.lower():
                out.append(f"attr {node.attr} line {ln}")
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and "untrusted" in node.value \
                    and id(node) not in docstrings:
                out.append(f"'untrusted' line {ln}")
        return out

    def test_no_text_in_decision_code(self):
        files = [REPO / f for f in TEXT_FREE] + sorted((AGENT / "tactics").glob("*.py"))
        bad = {rel(p): h for p in files if (h := self._hits(p))}
        self.assertEqual(bad, {})

    def test_gate_text_only_in_request_builders(self):
        src = (AGENT / "gate.py").read_text(encoding="utf-8")
        self.assertIn("REQUEST_FOR", src)
        self.assertEqual(self._hits(AGENT / "gate.py"), [])

    def test_world_has_no_text_field(self):
        import dataclasses

        from agent.contracts import World
        names = {f.name for f in dataclasses.fields(World)}
        self.assertFalse({n for n in names if "text" in n or "untrusted" in n})


class TestNoSecretsInSource(unittest.TestCase):
    """INV-18 in the source tree: no real key in code, config or fixtures."""
    SCAN = ("agent", "sim", "config", "tests", "api")

    def _source_files(self):
        out = [REPO / "bazaar.py"]
        for d in self.SCAN:
            base = REPO / d
            if base.exists():
                out += [p for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                        and p.suffix in (".py", ".json", ".jsonl", ".txt", ".md", ".js", ".html", "")]
        return out

    def _env_secrets(self) -> list:
        vals = []
        for name in (".env", ".env.night", ".env.local"):
            p = REPO / name
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    v = v.strip().strip("'\"")
                    if k.strip().upper().endswith(("KEY", "TOKEN", "SECRET", "PASSWORD")) and len(v) >= 8:
                        vals.append(v)
        return vals

    def test_real_key_values_never_in_source(self):
        secrets = self._env_secrets()
        leaks = []
        for p in self._source_files():
            try:
                data = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for s in secrets:
                if s in data:
                    leaks.append(rel(p))                              # never print the value itself
        self.assertEqual(leaks, [])

    def test_no_key_literals_in_harness_code(self):
        pat = re.compile(r"(tk-[A-Za-z0-9_]{6,}|bk_[A-Za-z0-9]{6,})")
        bad = []
        for p in harness_files() + sorted((REPO / "sim").glob("*.py")) + [REPO / "config" / "plan.json"]:
            for m in pat.findall(p.read_text(encoding="utf-8")):
                bad.append(f"{rel(p)}:{m[:5]}...")
        self.assertEqual(bad, [])

    def test_fixtures_carry_no_key_headers(self):
        bad = []
        for p in (REPO / "tests" / "fixtures").rglob("*.json"):
            s = p.read_text(encoding="utf-8", errors="replace")
            if re.search(r"(?i)x-(team|broker)-key", s) or re.search(r"tk-[A-Za-z0-9]{12,}", s):
                bad.append(rel(p))
        self.assertEqual(bad, [])


class TestRootScriptsAreReadOnly(unittest.TestCase):
    """The operator tools next to bazaar.py never write to the game on their own: they GET, and any write they need
    goes through `python3 bazaar.py do ... --live` (so through the Gate). Checked on the AST of every top-level .py
    and api/*.py, except bazaar_sdk.py (the official SDK, never imported by them) and bazaar.py (the CLI)."""

    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    KEYED_RAW_READERS = {"bench_rec.py"}   # GETs /api/broker/book with the stall's key via urllib (no write route)

    def scripts(self):
        files = sorted(REPO.glob("*.py")) + sorted((REPO / "api").glob("*.py"))
        return [p for p in files if p.name not in ("bazaar_sdk.py", "bazaar.py")]

    def test_scripts_exist(self):
        self.assertTrue({"ladder_sell.py", "egg_watch.py", "run_dashboard.py"} <= {p.name for p in self.scripts()})

    def test_no_sdk_and_no_write_verbs(self):
        bad = []
        for p in self.scripts():
            for node in ast.walk(tree(p)):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in node.names] + ([node.module] if isinstance(node, ast.ImportFrom) else [])
                    if any(n and n.split(".")[0] == "bazaar_sdk" for n in names):
                        bad.append(f"{rel(p)}: imports bazaar_sdk (line {node.lineno})")
                elif isinstance(node, ast.Constant) and node.value in self.WRITE_METHODS:
                    bad.append(f"{rel(p)}: HTTP write verb {node.value!r} (line {node.lineno})")
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                    bad.append(f"{rel(p)}: {node.func.id}() (line {node.lineno})")
        self.assertEqual(bad, [])

    def test_raw_http_scripts_do_not_hold_the_team_key(self):
        """A script that speaks raw urllib must not load the team key (except the listed GET-only recorder):
        keyed reads go through agent.client.client("read"), whose transport refuses every write."""
        bad = []
        for p in self.scripts():
            t = tree(p)
            docs = {id(n.body[0].value) for n in ast.walk(t)
                    if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body
                    and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
            keyed = any((isinstance(n, ast.Constant) and n.value == "BAZAAR_KEY" and id(n) not in docs)
                        or (isinstance(n, ast.Name) and n.id == "_load_env")
                        or (isinstance(n, ast.alias) and n.name == "_load_env") for n in ast.walk(t))
            raw = any(isinstance(n, (ast.Import, ast.ImportFrom)) and any(
                (a.name if isinstance(n, ast.Import) else (n.module or "")).startswith(("urllib", "http.client", "requests", "httpx"))
                for a in n.names) for n in ast.walk(tree(p)))
            if raw and keyed and p.name not in self.KEYED_RAW_READERS:
                bad.append(rel(p))
        self.assertEqual(bad, [])

    def test_no_write_mode_client(self):
        bad = [rel(p) for p in self.scripts() if re.search(r"client\(\s*(mode\s*=\s*)?[\"']write", p.read_text(encoding="utf-8"))]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
