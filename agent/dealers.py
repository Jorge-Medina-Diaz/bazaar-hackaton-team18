"""What we know about each dealer, as data. A new dealer = a new entry here (and a section in docs/playbook.md).

Pack prices are fractions of the dealer's `opening_ask` (GET /api/dealers/{id} -> menu.sells).
Numbers come from docs/playbook.md; change them there and here together.
"""

PROFILES = {
    "abuela": {
        "pack": {"anchor": 0.50, "limit": 0.77, "rounds": 6, "beta": 1.0},  # 30 -> 23 final; a pack at 24 seems to score 0
        "lines": [  # she likes kindness; the same words twice are spam, so rotate
            "¡Buenas, Carmen! Qué puesto tan bonito. ¿Me lo dejaría en {p} P?",
            "Usted conoce los cromos mejor que nadie. ¿Qué tal {p} P, señora?",
            "Me hace mucha ilusión este sobre. ¿Podríamos dejarlo en {p} P?",
            "Gracias por su paciencia, Carmen. Subo a {p} P, ¿le parece?",
            "Mi abuela también tenía un puesto así. ¿Le vendría bien {p} P?",
            "Hago un esfuerzo: {p} P. ¡Y vuelvo el domingo que viene!",
            "Es usted un encanto. ¿{p} P y cerramos con una sonrisa?",
        ],
    },
    # PROVISIONAL until he opens: only the teaser is known ("Better packs, friendly prices. If I like you.").
    # His price depends on how he feels about us, so open less hard than with Abuela, never trick or inject,
    # never repeat a line without a new price. Re-tune from his traits and `python3 scout.py chato` once active.
    "chato": {
        "pack": {"anchor": 0.60, "limit": 0.80, "rounds": 6, "beta": 1.0},
        "lines": [
            "¡Buenas, Chato! Me han dicho que eres el más majo del Rastro. ¿Lo dejamos en {p} P?",
            "Vengo recomendado por la Abuela Carmen. ¿Te parece bien {p} P?",
            "Qué buen material tienes, de verdad. Te ofrezco {p} P.",
            "Me gusta tratar contigo. Subo a {p} P, ¿hay trato?",
            "Volveré a comprarte, palabra. ¿{p} P y amigos?",
            "Hago un esfuerzo por ti: {p} P.",
            "Venga, Chato, que somos de confianza: {p} P y cerramos.",
        ],
    },
}
