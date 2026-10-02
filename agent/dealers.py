"""What we know about each dealer, as data. A new dealer = a new entry here (and a section in docs/playbook.md).

Pack prices are fractions of the dealer's `opening_ask` (GET /api/dealers/{id} -> menu.sells).
Numbers come from docs/playbook.md; change them there and here together.
"""

PROFILES = {
    "abuela": {
        "pack": {"anchor": 0.50, "limit": 0.80, "rounds": 6, "beta": 1.0},  # observed: 30 -> ~22-24 final
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
}
