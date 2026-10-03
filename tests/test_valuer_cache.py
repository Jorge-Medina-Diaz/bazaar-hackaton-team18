"""runner.Runner.build_valuer follows the catalog CONTENT (Sunday CHA release mid-run), not the catalog object's
id() (taken from integrate/main-into-harness-v2, tests/test_pack_policy.py::ValuerFollowsCatalog)."""
from __future__ import annotations

import copy
import unittest
from types import MappingProxyType, SimpleNamespace

import tests  # noqa: F401  (test isolation: BAZAAR_TEST=1)
from agent import runner
from tests.test_guards import CATALOG, ME


class ValuerFollowsCatalog(unittest.TestCase):
    """Rebuild on any catalog change (CHA released, minted), reuse on equal content."""

    def _self(self):
        return SimpleNamespace(valuer=None, _valuer_key=None, alarm=lambda *a, **k: None)

    def _world(self, catalog):
        cat = MappingProxyType(copy.deepcopy(catalog))
        released = frozenset(s["id"] for s in catalog["sets"] if s.get("released") is True)
        return SimpleNamespace(catalog=cat, me=MappingProxyType({"affinity": dict(ME["affinity"])}),
                               released_sets=released)

    def test_cha_release_and_minted_rebuild(self):
        me = self._self()
        sat = copy.deepcopy(CATALOG)
        for s in sat["sets"]:
            if s["id"] == "CHA":
                s["released"] = False
        v1 = runner.Runner.build_valuer(me, self._world(sat))
        self.assertNotIn("CHA", v1.released_sets)
        self.assertIs(runner.Runner.build_valuer(me, self._world(sat)), v1)     # same content, new object
        sun = copy.deepcopy(sat)
        for s in sun["sets"]:
            if s["id"] == "CHA":
                s["released"] = True
        v2 = runner.Runner.build_valuer(me, self._world(sun))
        self.assertIsNot(v2, v1)
        self.assertIn("CHA", v2.released_sets)
        minted = copy.deepcopy(sun)
        card = next(c for s in minted["sets"] for c in s.get("cards") or () if "minted" in c)
        card["minted"] = int(card["minted"] or 0) + 1
        v3 = runner.Runner.build_valuer(me, self._world(minted))
        self.assertIsNot(v3, v2)
        self.assertEqual(v3.cards[card["id"]]["minted"], card["minted"])


if __name__ == "__main__":
    unittest.main()
