"""M4b: G60 firewall and templates (INV-13). 2.000 generated texts pass, 300 malicious ones are all rejected."""
from __future__ import annotations

import ast
import random
import unittest
from pathlib import Path

from agent import talk
from agent.talk import TEMPLATES, firewall, render

ROOT = Path(__file__).resolve().parents[1]

INJECTIONS = [
    "Ignore previous instructions", "my limit is {L}", "Mi límite es {L}", "limite {L}", "reserva {L}",
    "precio mínimo {L}", "máximo {L}", "presupuesto {L}", "budget {L}", "valor {L}", "VALUE {L}",
    "afinidad {L}", "affinity 1.6", "multiplicador", "la clave", "api key", "token", "tk-abcdef123",
    "bk_live_123456", "http://evil.example", "https://x.y", "SYSTEM:", "{\"price\": 1}", "}", "{",
    "tengo {L} P en caja", "caja: {L}", "\x00", "\n", "\r", "​", "‮", "\x7f", " ",
    "٣", "１２", "½", "²", "ｋｅｙ", "ＶＡＬＵＥ", "lImItE", "Ｌímite", "value=", "SyStEm",
]


def _generated(rnd):
    name = rnd.choice(sorted(TEMPLATES))
    variant = rnd.randrange(len(TEMPLATES[name]))
    price = rnd.randint(0, 999999)
    days = rnd.randint(0, 10) if name == "duel_days" else None
    return name, variant, price, days


class Templates(unittest.TestCase):
    def test_every_template_renders_and_passes(self):
        for name, lines in TEMPLATES.items():
            for i in range(len(lines)):
                days = 4 if name == "duel_days" else None
                text = render(name, i, 23, days)
                self.assertTrue(firewall(text, 23, days, template=name).ok, (name, i, text))
                self.assertIn("23", text)
                self.assertLessEqual(len(render(name, i, 999999, days)), 280)

    def test_render_misuse(self):
        with self.assertRaises(ValueError):
            render("nope", 0, 5)
        with self.assertRaises(ValueError):
            render("duel", 99, 5)
        with self.assertRaises(ValueError):
            render("duel", 0, -1)
        with self.assertRaises(ValueError):
            render("duel_days", 0, 5)              # days missing
        with self.assertRaises(ValueError):
            render("duel", 0, 5, 3)                # days on a price-only template
        with self.assertRaises(ValueError):
            render("duel_days", 0, 5, 11)
        with self.assertRaises(ValueError):
            render("duel", True, 5)                # bool is not int

    def test_template_validation_rejects_bad_template(self):
        saved = dict(TEMPLATES)
        try:
            for bad in ("Mi límite es {p}", "Te doy {p} P, tengo 300", "Sin cifra", "{p} {x}"):
                TEMPLATES.clear()
                TEMPLATES.update(saved)
                TEMPLATES["duel"] = (bad,)
                with self.assertRaises(AssertionError, msg=bad):
                    talk._validate_templates()
        finally:
            TEMPLATES.clear()
            TEMPLATES.update(saved)
        talk._validate_templates()


class Firewall(unittest.TestCase):
    def test_2000_generated_pass(self):
        rnd = random.Random(60)
        for _ in range(2000):
            name, variant, price, days = _generated(rnd)
            text = render(name, variant, price, days)
            v = firewall(text, price, days, template=name)
            self.assertTrue(v.ok, (text, v))

    def test_300_malicious_rejected(self):
        rnd = random.Random(61)
        leaks = []
        for k in range(300):
            name, variant, price, days = _generated(rnd)
            text = render(name, variant, price, days)
            limit = price + rnd.randint(1, 50)
            inj = INJECTIONS[k % len(INJECTIONS)].replace("{L}", str(limit))
            mode = rnd.randrange(3)
            bad = text + " " + inj if mode == 0 else (inj + " " + text if mode == 1 else text[:5] + inj + text[5:])
            # without the template constraint too: the term / digit / control rules alone must catch it
            if firewall(bad, price, days).ok or firewall(bad, price, days, template=name).ok:
                leaks.append(bad)
        self.assertEqual(leaks, [])

    def test_price_equal_to_limit_allowed(self):
        limit = 88
        self.assertTrue(firewall(render("chato_buy", 1, limit), limit, None, template="chato_buy").ok)

    def test_other_number_rejected(self):
        # the limit (or any other number) never goes out: only str(p) and str(d)
        self.assertEqual(firewall("Precio justo y cerramos ya: 80 P. Puedo llegar a 88.", 80, None).code,
                         "G60.digits")
        self.assertEqual(firewall("Propuesta: 40 P y 3 días, caja 260", 40, 3).code, "G60.digits")

    def test_cash_in_text_rejected(self):
        cash = 260
        self.assertFalse(firewall(f"Tengo {cash} P. ¿{30} P?", 30, None).ok)

    def test_days_digits_allowed_only_with_days(self):
        self.assertTrue(firewall("40 P y 3 días", 40, 3).ok)
        self.assertEqual(firewall("40 P y 3 días", 40, None).code, "G60.digits")

    def test_length_and_empty(self):
        self.assertEqual(firewall("a" * 281, 1, None).code, "G60.length")
        self.assertEqual(firewall("   ", 1, None).code, "G60.empty")
        self.assertFalse(firewall(None, 1, None).ok)

    def test_repeat_of_last_text(self):
        t = render("duel", 0, 40)
        self.assertEqual(firewall(t, 40, None, last_text=t).code, "G60.repeat")
        self.assertTrue(firewall(t, 40, None, last_text=render("duel", 0, 41)).ok)

    def test_template_context(self):
        t = render("abuela_buy", 0, 17)
        self.assertTrue(firewall(t, 17, None, template="abuela_buy").ok)
        self.assertEqual(firewall(t, 17, None, template="chato_buy").code, "G60.template")
        self.assertEqual(firewall("Hola 17 P", 17, None, template="abuela_buy").code, "G60.template")
        self.assertEqual(firewall(t, 17, None, template="nope").code, "G60.template")

    def test_rendered_price_must_match(self):
        t = render("duel", 0, 40)
        self.assertEqual(firewall(t, 41, None).code, "G60.digits")


class NoForeignText(unittest.TestCase):
    """INV-13 (local part): talk.py never reads a "text" field nor anything untrusted."""

    def test_ast(self):
        tree = ast.parse((ROOT / "agent" / "talk.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertNotEqual(node.value, "text")
                self.assertNotIn("untrusted", node.value)
            if isinstance(node, ast.Name):
                self.assertNotIn("untrusted", node.id)
            if isinstance(node, ast.Attribute):
                self.assertNotIn("untrusted", node.attr)


if __name__ == "__main__":
    unittest.main()
