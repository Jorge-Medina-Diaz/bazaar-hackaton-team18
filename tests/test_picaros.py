import json
import os
import tempfile
import unittest
from unittest.mock import patch

import picaros
import radio


def opened(tid, team, topic, eid):
    return {"id": eid, "tick": 760, "type": "thread.opened",
            "payload": {"thread": tid, "team": team, "with": "picaros", "topic": topic}}


def msg(eid, tid, team, give, want, sender="picaros", text="", final=False, mid=None):
    return {"id": eid, "tick": 761 + eid % 10, "type": "thread.message",
            "payload": {"thread": tid, "team": team, "with": "picaros", "sender": sender, "message": mid or eid,
                        "text": text, "offer": {"give": give, "want": want, "final": final}}}


BUY = {"buy": {"card": "SAL-09"}}
SELL = {"sell": {"assets": [233]}}
CARD = {"cash": 0, "types": ["card:SAL-09"]}


class TrickTests(unittest.TestCase):
    def topics(self, events):
        return picaros.topics_of(picaros.observations(events))

    def test_real_threads_without_structural_contradiction_are_clean(self):
        ev = [opened(1060, "t08", SELL, 1), opened(1061, "t02", BUY, 2),
              msg(3, 1060, "t08", {"cash": 4}, {"cash": 0, "assets": [{"id": 233, "ref": "LAV-05"}]},
                  text="¡Eh, amigo! Paco, enséñale la Bici de Reparto… cuatro perlas"),
              msg(4, 1061, "t02", CARD, {"cash": 73}, text="Seventy-three pesos, for you only. They stopped printing"),
              msg(5, 1061, "t02", {"cash": 55}, CARD, sender="t02"),
              msg(6, 1061, "t02", CARD, {"cash": 67}, text="Fifty-five, he says! Sixty-seven, amigo")]
        self.assertEqual(picaros.tricks(ev, self.topics(ev)), [])

    def test_structural_tricks_against_the_topic_are_firm(self):
        ev = [opened(1, "t02", BUY, 1), opened(2, "t18", SELL, 2),
              msg(3, 1, "t02", {"cash": 0, "types": ["card:SAL-01"]}, {"cash": 70}),          # otra carta
              msg(4, 1, "t02", CARD, {"cash": 60, "assets": [{"id": 9, "ref": "RET-01"}]}),   # pide algo más
              msg(5, 2, "t18", {"cash": 10}, {"cash": 0, "assets": [{"id": 233}, {"id": 234}]}),  # más cartas
              msg(6, 2, "t18", {"cash": 0, "types": ["card:MAL-01"]}, {"cash": 5}),           # dirección contraria
              msg(7, 1, "t02", {"cash": 0}, {"cash": 50})]                                    # no da nada
        got = {t["message"]: t["motivo"] for t in picaros.tricks(ev, self.topics(ev)) if t["level"] == "firme"}
        self.assertIn("da SAL-01 en vez de SAL-09", got[3])
        self.assertIn("además pide cartas nuestras", got[4])
        self.assertIn("pide las cartas [233, 234] en vez de [233]", got[5])
        self.assertIn("dirección contraria", got[6])
        self.assertIn("no da ninguna carta", got[7])

    def test_text_price_mismatch_is_only_possible_and_echoes_are_ignored(self):
        ev = [opened(1, "t02", BUY, 1), msg(2, 1, "t02", {"cash": 50}, CARD, sender="t02"),
              msg(3, 1, "t02", CARD, {"cash": 80}, text="Only 60 P for you, amigo!"),
              msg(4, 1, "t02", CARD, {"cash": 70}, text="Fifty, he says! Ha!"),          # repite el 50 del equipo
              msg(5, 1, "t02", CARD, {"cash": 80}, text="Not 60 P, not 65 P, amigo")]   # dos cifras: ambiguo
        got = picaros.tricks(ev, self.topics(ev))
        self.assertEqual([(t["message"], t["level"]) for t in got], [(3, "posible")])
        self.assertIn("el texto dice 60 y la oferta 80", got[0]["motivo"])

    def test_number_words_in_english_and_spanish(self):
        self.assertEqual(picaros.text_prices("Seventy-three pesos"), {73})
        self.assertEqual(picaros.text_prices("trece perlas, amigo"), {13})
        self.assertEqual(picaros.text_prices("Fine, 13 P. Last offer"), {13})
        self.assertEqual(picaros.text_prices("ciento ochenta y siete primas"), {187})   # caso real, mensaje 8663
        self.assertEqual(picaros.text_prices("one hundred and fifty-five"), {155})
        self.assertEqual(picaros.text_prices("¡Ciento treinta y nueve! Hecho"), {139})


class ProfileTests(unittest.TestCase):
    def test_profile_and_history_accumulate_without_duplicates(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "p.jsonl")
        ev = [opened(1, "t05", {"sell": {"assets": [872]}}, 1),
              msg(2, 1, "t05", {"cash": 10}, {"cash": 0, "assets": [{"id": 872, "ref": "MAL-06"}]}),
              msg(3, 1, "t05", {"cash": 11}, {"cash": 0, "assets": [{"id": 872, "ref": "MAL-06"}]}),
              msg(4, 1, "t05", {"cash": 13}, {"cash": 0, "assets": [{"id": 872, "ref": "MAL-06"}]}, final=True),
              {"id": 5, "tick": 766, "type": "settlement", "payload": {"persona": "picaros", "price": 67,
               "parties": ["picaros", "t02"], "items": [{"ref": "SAL-09", "frm": "picaros", "to": "t02"}]}}]
        rows, fresh = picaros.absorb(ev, path)
        self.assertEqual(len(fresh), 5)
        rows, fresh = picaros.absorb(ev, path)
        self.assertEqual((len(rows), fresh), (5, []))
        p = picaros.profile(rows)
        d = p["por_tipo"]["compran uncommon"]
        self.assertEqual((d["apertura"]["mediana"], d["pasos"]["max"], d["mensajes_hasta_final"]["mediana"]),
                         (10, 2, 3))
        self.assertEqual(p["tratos"]["venden rare"]["mediana"], 67)


class WatcherTests(unittest.TestCase):
    def test_watcher_alerts_each_trick_once_and_high_when_it_targets_us(self):
        d, sent, lines = tempfile.mkdtemp(), [], []
        ev = [opened(2, "t18", SELL, 2),
              msg(6, 2, "t18", {"cash": 0, "types": ["card:MAL-01"]}, {"cash": 5})]

        def fake_get(path, timeout=10):
            if path == "/api/news":
                return {"news": []}
            if path.startswith("/api/feed"):
                return {"events": ev}
            raise AssertionError(path)
        with patch.object(radio, "LOG_DIR", d), patch.object(radio, "get", fake_get), \
                patch.object(radio, "observe", lambda: None), \
                patch.object(radio, "notify", lambda *a, **k: sent.append((a, k)) or True):
            state = radio.load_state(os.path.join(d, "s.json"))
            radio.step(state, {}, out=lines.append)
            radio.step(state, {}, out=lines.append)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][1]["level"], "MEDIA")          # el Gate lo bloquea: informativo, no alarma
        self.assertIn("🃏 Truco de Los Pícaros", sent[0][0][1])
        self.assertTrue(any("CONTRA NOSOTROS" in x for x in lines))
        with open(os.path.join(d, "picaros.jsonl")) as f:
            self.assertEqual(len(f.readlines()), 2)


class QuietPossibleTests(unittest.TestCase):
    def test_possible_tricks_on_other_teams_are_logged_but_silent(self):
        d, sent, lines = tempfile.mkdtemp(), [], []
        ev = [opened(1, "t04", BUY, 1), msg(2, 1, "t04", CARD, {"cash": 80}, text="Only 60 P for you!")]

        def fake_get(path, timeout=10):
            return {"news": []} if path == "/api/news" else {"events": ev}
        with patch.object(radio, "LOG_DIR", d), patch.object(radio, "get", fake_get), \
                patch.object(radio, "observe", lambda: None), \
                patch.object(radio, "notify", lambda *a, **k: sent.append(a) or True):
            radio.step(radio.load_state(os.path.join(d, "s.json")), {}, out=lines.append)
        self.assertEqual(sent, [])
        self.assertTrue(any("POSIBLE" in x for x in lines))


class ContextTests(unittest.TestCase):
    def test_real_lat09_thread_explains_how_the_bait_is_placed(self):
        lat = {"buy": {"card": "LAT-09"}}
        ev = [opened(1346, "t18", lat, 1),
              msg(2, 1346, "t18", {"cash": 0, "types": ["card:LAT-09"]}, {"cash": 73}),
              msg(3, 1346, "t18", {"cash": 45}, {"types": ["card:LAT-09"]}, sender="t18"),
              msg(4, 1346, "t18", {"cash": 0, "types": ["card:LAT-09"]}, {"cash": 66}),
              msg(5, 1346, "t18", {"cash": 48}, {"types": ["card:LAT-09"]}, sender="t18"),
              msg(6, 1346, "t18", {"cash": 0, "types": ["card:LAT-06"]}, {"cash": 62}, final=True,
                  text="Mira, amigo, the Corrala, la de verdad, sixty-two")]
        trick = {"thread": 1346, "message": 6, "motivo": "da LAT-06 en vez de LAT-09"}
        cx = picaros.trick_context(ev, trick, names={"la corrala": "LAT-09", "la tabacalera": "LAT-06"})
        self.assertEqual((cx["asked"], cx["bait"], cx["price"], cx["last_real"], cx["our_bid"], cx["final"],
                          cx["attempts"], cx["text_names_good"]),
                         ("LAT-09", "LAT-06", 62, 66, 48, True, 1, True))
        line = radio.explain_trick(cx, trick)
        self.assertEqual(line, "🃏 Pedimos LAT-09 (rara) y ofrecen LAT-06 (infrecuente) a 62 · su última oferta real "
                               "de LAT-09 fue 66 · nuestra puja va en 48 · el texto habla de LAT-09 · lo marcan "
                               "«final» (suele ser falso). El Gate no lo acepta.")


if __name__ == "__main__":
    unittest.main()
