import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import radio

CHATO = {"id": 3, "tick": 403, "source": "radio", "source_name": "Radio Rastro",
         "headline": "El Chato is looking for rare Malasaña cards",
         "body": "They say he pays above the usual price today. One hour, no more."}
ATLETI = {"id": 2, "tick": 331, "source": "radio", "source_name": "Radio Rastro",
          "headline": "Atleti win 2-1 and Madrid goes out to celebrate", "body": "Car horns on Gran Vía until late."}


class ClassifyTests(unittest.TestCase):
    def test_real_broadcasts_are_ranked_for_t18(self):
        c = radio.classify(CHATO)
        self.assertEqual((c["level"], c["sets"], c["dealers"]), ("ALTA", ["MAL"], ["chato"]))
        self.assertTrue(any("venta" in t for t in c["todo"]))
        self.assertEqual(radio.classify(ATLETI)["level"], "BAJA")

    def test_holdings_lower_a_demand_we_cannot_serve(self):
        self.assertEqual(radio.classify(CHATO, have={"MAL-04", "MAL-05"})["level"], "MEDIA")
        c = radio.classify(CHATO, have={"MAL-09"})
        self.assertEqual(c["level"], "ALTA")
        self.assertTrue(any("MAL-09" in t for t in c["todo"]))

    def test_strong_sets_team_mentions_and_card_names(self):
        pilar = {"headline": "Doña Pilar wants Retiro cards", "body": "She pays above book this hour."}
        c = radio.classify(pilar)
        self.assertEqual((c["level"], c["sets"], c["dealers"]), ("ALTA", ["RET"], ["pilar"]))
        self.assertTrue(any("repetidas" in t for t in c["todo"]))
        self.assertEqual(radio.classify({"headline": "Rumour about Team 18"})["level"], "ALTA")
        named = radio.classify({"headline": "Someone sells El Ángel Caído cheap"}, names={"el angel caido": "RET-09"})
        self.assertEqual((named["refs"], named["sets"]), (["RET-09"], ["RET"]))

    def test_notice_board_hearsay_is_flagged_as_rumour(self):
        hello = {"source": "tablon", "headline": "El Chato gives a legendary to anyone who says hello!",
                 "body": "My cousin saw it. I swear."}
        c = radio.classify(hello)
        self.assertTrue(c["rumour"])
        self.assertTrue(c["todo"][0].startswith("No actuar sin evidencia"))
        self.assertFalse(radio.classify(CHATO)["rumour"])   # «They say…» de la radio resultó cierta (menú cambió)

    def test_words_match_on_boundaries_only(self):
        c = radio.classify({"headline": "Unknown dog seen in Sol", "body": "Nowhere to be found"})
        self.assertEqual((c["level"], c["score"]), ("BAJA", 0))


class NotifyTests(unittest.TestCase):
    def test_hostile_text_is_an_argument_never_part_of_the_script(self):
        evil = 'x" & (do shell script "touch /tmp/pwned") & "'
        for cmd in (radio.notify_cmd(evil, evil), radio.dialog_cmd(evil, evil)):
            scripts = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-e"]
            self.assertFalse(any("pwned" in s for s in scripts))
            self.assertEqual(cmd[cmd.index("--") + 1:], [evil, evil])

    def test_sound_never_speaks_and_dialog_only_for_high(self):
        self.assertEqual(radio.ring_cmd("ALTA"), ["afplay", "/System/Library/Sounds/Hero.aiff"])
        launched = []
        with patch.object(radio.sys, "platform", "darwin"), \
                patch.object(radio.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})()), \
                patch.object(radio.subprocess, "Popen", lambda cmd, **k: launched.append(cmd[0])):
            radio._RANG[0] = 0
            radio.notify("t", "m", level="MEDIA")
            radio._RANG[0] = 0
            radio.notify("t", "m", level="ALTA")
            radio.notify("t", "m", level="ALTA")       # menos de 2 s: no repite el sonido
        self.assertEqual(launched, ["afplay", "afplay", "osascript", "osascript"])
        self.assertNotIn("say", launched)


class PacingTests(unittest.TestCase):
    def test_never_faster_than_a_tick_and_never_slower_than_five_minutes(self):
        self.assertEqual(radio.interval([], 30, False), 60.0)
        self.assertEqual(radio.interval([283, 331, 403], 30, True), 30.0)
        self.assertEqual(radio.interval([283, 331, 403], 30, False), 225.0)  # mediana 60 ticks × 30 s / 8
        self.assertEqual(radio.interval([0, 1000], 30, False), 300.0)
        self.assertEqual(radio.interval([1, 2], 1, False), 5.0)


def obs(**over):
    base = {"snap": 400, "tick": 405,
            "teams": {"t18": {"name": "Team 18", "rank": 2, "score": 30.18, "neg": 22.68, "market": 7.5},
                      "t13": {"name": "Team 13", "rank": 1, "score": 30.37, "neg": 27.04, "market": 3.33},
                      "t05": {"name": "Team 5", "rank": 3, "score": 29.5, "neg": 17.0, "market": 12.5}},
            "dealers": {"chato": {"name": "El Chato", "status": "active", "level": 2, "open": True,
                                  "sells": {"rare@released": {"list": 77, "ask": None}},
                                  "buys": ["rare@released"]},
                        "pilar": {"name": "Doña Pilar", "status": "active", "level": 3, "open": False,
                                  "sells": {"sobre_oro": {"list": 420, "ask": 504}}, "buys": ["rare@RET,SAL"]}},
            "released": ["LAT", "LAV", "MAL", "RET", "SAL"], "minted_top": {},
            "levels": {"chato": "active", "pilar": "active"}, "now_h": 4.6,
            "upcoming": [[5.15, "duels", "Duels I"], [5.508, "persona_opens", "Doña Pilar opens for everyone"]]}
    base.update(over)
    return base


class DiffTests(unittest.TestCase):
    def test_no_baseline_no_report_and_identical_photos_report_nothing(self):
        self.assertEqual(radio.diff(None, obs()), [])
        self.assertEqual(radio.diff(obs(), obs()), [])

    def test_rank_overtake_and_points_are_reported_with_before_and_after(self):
        after = obs(snap=410, teams={
            "t18": {"name": "Team 18", "rank": 3, "score": 26.66, "neg": 19.16, "market": 7.5},
            "t13": {"name": "Team 13", "rank": 1, "score": 30.5, "neg": 27.2, "market": 3.33},
            "t05": {"name": "Team 5", "rank": 2, "score": 29.6, "neg": 17.1, "market": 12.5}})
        texts = {t: lvl for lvl, t, _ in radio.diff(obs(), after)}
        self.assertEqual(texts["Puesto de t18: 2.º → 3.º (puntos 30,18 → 26,66)"], "ALTA")
        self.assertIn("Team 5 nos adelanta: 2.º con 29,60 (nosotros 26,66)", texts)
        self.assertTrue(any(t.startswith("Puntos de t18: 30,18 → 26,66 (-3,52): negociación 22,68 → 19,16")
                            for t in texts))

    def test_leaderboard_is_only_compared_when_its_snapshot_refreshes(self):
        moved = obs(teams=dict(obs()["teams"], t18={"name": "Team 18", "rank": 3, "score": 1, "neg": 1, "market": 1}))
        self.assertEqual(radio.diff(obs(), moved), [])

    def test_dealer_opening_prices_buys_sets_and_minting(self):
        d = obs()["dealers"]
        after = obs(dealers={"chato": dict(d["chato"], sells={"rare@released": {"list": 85, "ask": None}},
                                           buys=["rare@MAL", "rare@released"]),
                             "pilar": dict(d["pilar"], open=True),
                             "vault": {"name": "La Cámara", "status": "active", "level": 4, "open": False,
                                       "sells": {}, "buys": []}},
                    released=["CHA", "LAT", "LAV", "MAL", "RET", "SAL"], minted_top={"RET-12": 1})
        got = {t: (lvl, tags) for lvl, t, tags in radio.diff(obs(), after)}
        self.assertEqual(got["El Chato vende rare@released: lista 77, pide None → lista 85, pide None"][0], "MEDIA")
        self.assertEqual(got["El Chato ahora compra rare de MAL"], ("ALTA", ("chato", "+buy:MAL")))
        self.assertEqual(got["Doña Pilar: abierto a todos no → sí"][0], "ALTA")
        self.assertIn("Nuevo dealer: La Cámara (nivel 4, active)", got)
        self.assertEqual(got["Barrio publicado: CHA (objetivo del domingo (×1,6))"][0], "ALTA")
        self.assertEqual(got["RET-12 acuñada: 0 → 1 copias (épica/legendaria en circulación)"][0], "ALTA")

    def test_upcoming_event_is_announced_once_inside_the_window(self):
        soon = obs(now_h=5.0)
        first = [t for _, t, _ in radio.diff(obs(), soon)]
        self.assertEqual(first, ["Próximo en 0,15 h de juego: Duels I"])
        self.assertEqual(radio.diff(obs(), soon, announced=["duels@5.15"]), [])


class StepTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        p = patch.object(radio, "LOG_DIR", self.dir)
        p.start()
        self.addCleanup(p.stop)
        self.news, self.photo, self.sent = [ATLETI], obs(), []
        for target, fake in (("get", self.fake_get), ("observe", lambda: self.photo),
                             ("notify", lambda *a, **k: self.sent.append(a) or True)):
            q = patch.object(radio, target, fake)
            q.start()
            self.addCleanup(q.stop)
        self.state, self.lines = radio.load_state(os.path.join(self.dir, "state.json")), []

    def fake_get(self, path, timeout=10):
        if path == "/api/news":
            return {"news": list(reversed(self.news))}
        raise AssertionError(path)

    def step(self, **kw):
        return radio.step(self.state, {}, out=self.lines.append, **kw)

    def test_first_read_is_silent_then_only_new_relevant_items_notify_once(self):
        self.assertEqual(len(self.step(first=True)), 1)
        self.assertEqual(self.sent, [])
        self.news.append(CHATO)
        self.assertEqual([n["id"] for n in self.step()], [3])
        self.assertEqual(len(self.sent), 1)
        self.assertIn("ALTA", self.sent[0][0])
        self.assertEqual(self.step(), [])
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.state["ticks"], [331, 403])

    def test_existing_items_on_the_first_read_never_notify_even_if_high(self):
        self.news.append(CHATO)
        self.assertEqual(len(self.step(first=True)), 2)
        self.assertEqual(self.sent, [])

    def test_every_new_item_rings_even_low_ones(self):
        self.step(first=True)
        self.news.append(dict(ATLETI, id=9, tick=500))
        self.step()
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][0], "📻 Radio Rastro · BAJA para t18")
        with open(os.path.join(self.dir, "radio.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(line) for line in f]
        self.assertEqual([r["id"] for r in rows if r["event"] == "news"], [2, 9])

    def test_menu_change_after_a_broadcast_confirms_it_and_notifies(self):
        self.step(first=True)
        self.news.append(CHATO)
        self.step()
        d = self.photo["dealers"]
        self.photo = obs(dealers=dict(d, chato=dict(d["chato"], buys=["rare@MAL", "rare@released"])))
        self.step()
        line = next(x for x in self.lines if "ahora compra rare de MAL" in x)
        self.assertIn("confirma la noticia «El Chato is looking for rare Malasaña cards»", line)
        self.assertTrue(any(s[0].startswith("🔔 t18 · ALTA") for s in self.sent))

    def test_state_survives_restart_and_a_corrupt_file(self):
        path = os.path.join(self.dir, "state.json")
        self.step(first=True)
        radio.save_state(path, self.state)
        restored = radio.load_state(path)
        self.assertEqual((restored["seen"], restored["obs"]["tick"]), ([2], 405))
        with open(path, "w") as f:
            f.write("{broken")
        self.assertEqual(radio.load_state(path)["seen"], [])


def offer(eid, tick, ref, price, buys=True, dealer="chato"):
    card, cash = {"cash": 0, "types": ["card:" + ref]}, {"cash": price}
    return {"id": eid, "tick": tick, "type": "thread.message",
            "payload": {"with": dealer, "sender": dealer, "offer": {"give": cash if buys else card,
                                                                    "want": card if buys else cash}}}


class EvidenceTests(unittest.TestCase):
    def test_dealer_prices_read_offers_and_deals_after_the_news_only(self):
        ev = [offer(1, 399, "MAL-09", 60), offer(2, 404, "MAL-09", 85), offer(3, 405, "LAV-10", 62, buys=False),
              {"id": 4, "tick": 406, "type": "settlement", "payload": {"persona": "chato", "price": 88,
               "items": [{"ref": "MAL-10", "frm": "t07", "to": "chato"}]}},
              offer(5, 407, "MAL-09", 90, dealer="abuela"),
              {"id": 6, "tick": 407, "type": "thread.message", "payload": {"with": "chato", "sender": "t05",
               "offer": {"give": {"types": ["card:MAL-09"]}, "want": {"cash": 200}}}}]
        got = radio.dealer_prices(ev, "chato", 403)
        self.assertEqual([(o["id"], o["side"], o["price"], o["kind"]) for o in got],
                         [(2, "compra", 85, "oferta"), (3, "vende", 62, "oferta"), (4, "compra", 88, "trato")])

    def test_verdict_needs_a_premium_against_the_same_rarity_elsewhere(self):
        obs = [{"id": i, "set": s, "rarity": "rare", "side": "compra", "price": p}
               for i, (s, p) in enumerate([("MAL", 85), ("MAL", 88), ("LAV", 60), ("SAL", 64)])]
        v = radio.verdict(obs, {"MAL"}, "compra", "rare")
        self.assertEqual((v["verdict"], v["target"], v["control"]), ("confirmada", 86.5, 62.0))
        self.assertEqual(radio.verdict(obs[:1] + obs[2:3], {"MAL"}, "compra", "rare")["verdict"], "indicio")
        flat = [dict(o, price=60) for o in obs]
        self.assertEqual(radio.verdict(flat, {"MAL"}, "compra", "rare")["verdict"], "sin señal")
        self.assertEqual(radio.verdict(obs[:2], {"MAL"}, "compra", "rare")["verdict"], "solo barrio citado")
        cheap = [dict(o, side="vende", price=50 if o["set"] == "MAL" else 80) for o in obs]
        self.assertEqual(radio.verdict(cheap, {"MAL"}, "vende", "rare")["verdict"], "confirmada")

    def test_step_accumulates_evidence_across_reads_and_notifies_confirmation_once(self):
        d = tempfile.mkdtemp()
        feeds = [[], [offer(1, 404, "MAL-09", 85), offer(2, 404, "LAV-09", 60)],
                 [offer(2, 404, "LAV-09", 60), offer(3, 406, "MAL-10", 88), offer(4, 406, "SAL-09", 63)],
                 [offer(4, 406, "SAL-09", 63)]]
        news, sent, lines = [ATLETI], [], []

        def fake_get(path, timeout=10):
            if path == "/api/news":
                return {"news": list(reversed(news))}
            if path.startswith("/api/feed"):
                return {"events": feeds.pop(0) if feeds else []}
            raise AssertionError(path)
        with patch.object(radio, "LOG_DIR", d), patch.object(radio, "get", fake_get), \
                patch.object(radio, "observe", lambda: obs()), \
                patch.object(radio, "notify", lambda *a, **k: sent.append(a) or True):
            state = radio.load_state(os.path.join(d, "s.json"))
            radio.step(state, {}, first=True, out=lines.append)
            news.append(CHATO)
            radio.step(state, {}, out=lines.append)
            radio.step(state, {}, out=lines.append)
            radio.step(state, {}, out=lines.append)
        w = state["watch"]["3"]
        self.assertEqual(sorted(o["id"] for o in w["obs"]), [1, 2, 3, 4])
        self.assertEqual(w["verdict"][0], "confirmada")
        self.assertEqual(sum("CONFIRMADA" in s[0] for s in sent), 1)
        self.assertTrue(any("mediana 86,50 (n=2) frente a 61,50" in x for x in lines))


class AttributionTests(unittest.TestCase):
    MAL = {"news": 3, "headline": "El Chato is looking for rare Malasaña cards", "dealers": ["chato"],
           "sets": ["MAL"], "side": "compra"}
    HELLO = {"news": 4, "headline": "El Chato gives a legendary to anyone who says hello!", "dealers": ["chato"],
             "sets": [], "side": None}

    def test_only_matching_sets_confirm_and_a_removal_is_the_end_of_the_window(self):
        both = [self.MAL, self.HELLO]
        self.assertEqual(radio.attribute(("chato", "+buy:MAL"), both), "confirma")
        self.assertEqual(radio._hit[0]["news"], 3)
        self.assertEqual(radio.attribute(("chato", "-buy:MAL"), both), "fin")
        self.assertEqual(radio._hit[0]["news"], 3)

    def test_rumour_without_sets_or_other_sets_or_dealers_is_never_confirmed(self):
        self.assertIsNone(radio.attribute(("chato", "-buy:MAL"), [self.HELLO]))
        self.assertIsNone(radio.attribute(("chato", "+buy:LAV"), [self.MAL]))
        self.assertIsNone(radio.attribute(("abuela", "+buy:MAL"), [self.MAL]))
        self.assertIsNone(radio.attribute(("chato",), [self.MAL]))      # cambio de precio: sin atribución

    def test_the_real_13_03_case_reads_as_end_of_window(self):
        d, sent, lines = tempfile.mkdtemp(), [], []
        base = obs()
        ch = base["dealers"]["chato"]
        photos = [obs(dealers=dict(base["dealers"], chato=dict(ch, buys=["rare@MAL", "rare@released"]))), base]
        with patch.object(radio, "LOG_DIR", d), \
                patch.object(radio, "get", lambda p, timeout=10: {"news": [], "events": []}), \
                patch.object(radio, "observe", lambda: photos.pop(0) if len(photos) > 1 else photos[0]), \
                patch.object(radio, "notify", lambda *a, **k: sent.append(k.get("level")) or True):
            state = radio.load_state(os.path.join(d, "s.json"))
            state["watch"] = {"3": dict(self.MAL, until=time.time() + 9000, start=time.time() - 4000, obs=[]),
                              "4": dict(self.HELLO, until=time.time() + 9000, start=time.time() - 300, obs=[])}
            radio.step(state, {}, out=lines.append)
            radio.step(state, {}, out=lines.append)
        line = next(x for x in lines if "ya no compra rare de MAL" in x)
        self.assertIn("fin de la ventana de la noticia «El Chato is looking for rare Malasaña cards»", line)
        self.assertNotIn("hello", line)
        self.assertNotIn("ALTA", sent)


class TimeTests(unittest.TestCase):
    def test_aired_reports_tick_game_hour_estimated_wall_time_and_delay(self):
        clock = {"tick": 410, "tick_seconds": 30.0, "next_tick_in": 10.0, "t_hours": 4.75}
        now = 1_000_000.0
        txt = radio.aired(CHATO | {"at_hours": 4.6833} if hasattr(dict, "__or__") else dict(CHATO, at_hours=4.6833),
                          clock, now)
        lag_s = 7 * 30 + 20   # 7 ticks y 20 s del tick en curso
        self.assertIn("emitida tick 403 (h 4,68)", txt)
        self.assertIn(f"≈ {radio.hhmmss(now - lag_s)} · detectada {radio.hhmmss(now)} (+7 ticks, ~4 min)", txt)
        self.assertIn("detectada", radio.aired(CHATO))

    def test_when_has_local_time_tick_and_game_hour(self):
        self.assertRegex(radio.when({"tick": 560, "t_hours": 5.12}), r"^\d\d:\d\d:\d\d · tick 560 · h 5,12$")
        self.assertRegex(radio.when(), r"^\d\d:\d\d:\d\d$")

    def test_notifications_and_report_carry_the_time(self):
        d, sent, lines = tempfile.mkdtemp(), [], []
        news = [ATLETI]
        clock = {"tick": 405, "tick_seconds": 30.0, "next_tick_in": 5.0, "t_hours": 4.7}
        photos = [obs(), obs(released=["CHA", "LAT", "LAV", "MAL", "RET", "SAL"])]
        with patch.object(radio, "LOG_DIR", d), \
                patch.object(radio, "get", lambda p, timeout=10: {"news": list(reversed(news)), "events": []}), \
                patch.object(radio, "observe", lambda: photos.pop(0) if len(photos) > 1 else photos[0]), \
                patch.object(radio, "notify", lambda *a, **k: sent.append(a) or True):
            state = radio.load_state(os.path.join(d, "s.json"))
            radio.step(state, {}, first=True, out=lines.append, clock=clock)
            news.append(CHATO)
            radio.step(state, {}, out=lines.append, clock=clock)
        self.assertTrue(all(m.startswith("🕒 ") for _, m in sent), sent)
        self.assertIn("emitida tick 403", sent[0][1])
        self.assertIn("detectada", sent[0][1])
        self.assertIn("tick 405 · h 4,70", sent[1][1])
        self.assertTrue(any(x.startswith("🔔 Cambios para t18 · 🕒 ") and "tick 405 · h 4,70" in x for x in lines))
        self.assertTrue(any("🕒 emitida tick 403" in x for x in lines))


class ScheduleTests(unittest.TestCase):
    FEVER = [9.15, "persona_patch", "Salamanca fever: Doña Pilar pays 25 % over book for Salamanca until 17:30"]

    def test_a_scheduled_dealer_patch_on_our_sets_is_high_when_it_appears_and_when_it_starts(self):
        new = obs(upcoming=obs()["upcoming"] + [self.FEVER])
        got = radio.diff(obs(), new)
        self.assertIn(("ALTA", "Nuevo en el calendario (h 9,15): " + self.FEVER[2], ()), got)
        soon = dict(new, now_h=9.0)
        self.assertIn("ALTA", [lvl for lvl, t, _ in radio.diff(new, soon) if t.startswith("Próximo en 0,15")])

    def test_benches_are_not_reannounced_as_new(self):
        new = obs(upcoming=obs()["upcoming"] + [[7.0, "bench", "The Market Test"]])
        self.assertEqual(radio.diff(obs(), new), [])


class RateLimitTests(unittest.TestCase):
    def test_429_becomes_rate_limited_with_server_wait_and_reads_are_spaced(self):
        import io
        import urllib.error

        def boom(req, timeout=10):
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {"Retry-After": "90"}, io.BytesIO(b""))
        with patch.object(radio.urllib.request, "urlopen", boom):
            with self.assertRaises(radio.RateLimited) as ctx:
                radio.get("/api/news")
        self.assertEqual(ctx.exception.wait, 90.0)
        stamps = []

        class Ok:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b"{}"
        with patch.object(radio.urllib.request, "urlopen", lambda req, timeout=10: stamps.append(time.time()) or Ok()):
            radio.get("/a")
            radio.get("/b")
        self.assertGreaterEqual(stamps[1] - stamps[0], radio.GAP_S - 0.01)


class ClockTests(unittest.TestCase):
    def test_pause_and_resume_are_reported_once_with_ticks(self):
        run, stop = {"tick": 630, "t_hours": 6.575, "paused": False}, {"tick": 630, "t_hours": 6.575, "paused": True}
        self.assertEqual(radio.clock_change(run, stop)[0], "ALTA")
        self.assertIn("PAUSA en el tick 630 (h 6,58)", radio.clock_change(run, stop)[1])
        self.assertIn("REANUDADO: tick 630 → 631", radio.clock_change(stop, dict(run, tick=631))[1])
        self.assertIsNone(radio.clock_change(stop, stop))
        self.assertIsNone(radio.clock_change(None, stop))


if __name__ == "__main__":
    unittest.main()
