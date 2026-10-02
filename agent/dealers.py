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
    # From the feed, ticks 100-111 (9 threads, docs/playbook.md "El Chato"): he concedes exactly what we concede
    # ("You move, I move"), so the deal lands near the midpoint of both openings: the anchor is the lever.
    # Equal steps (beta 1), never lower a bid (t12 tried, he barely moved). He sells silver packs (188) and
    # singles (uncommon 33, rare 97), not sobre_barrio; he buys uncommons at a flat 13.
    # Cards via run_dealer.py: --anchor ~45 % and --limit ~75 % of his opening (rare 97 -> 44/72, uncommon 33 -> 15/25).
    "chato": {
        "pack": {"anchor": 0.45, "limit": 0.75, "rounds": 6, "beta": 1.0},
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
