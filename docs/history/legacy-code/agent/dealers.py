"""What we know about each dealer, as data. A new dealer = a new entry here (and a section in docs/playbook.md).

Pack prices are fractions of the dealer's `opening_ask` (GET /api/dealers/{id} -> menu.sells).
Numbers come from docs/playbook.md; change them there and here together.
"""
raise SystemExit("ARCHIVED by M18: pre-harness script that could reach the game without the Gate. Use the harness: python3 bazaar.py (see CLAUDE.md).")  # M18 guard

PROFILES = {
    "abuela": {
        "pack": {"anchor": 0.50, "limit": 0.77, "rounds": 6, "beta": 1.0},  # 30 -> 23 final. E9: only buy if the pack's your_value >= price, overpaying costs neg_points
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
    "chato": {  # level 2: shrewd 0.85, patience 0.35, memory 0.9, strict 0.85 -> short, honest, few rounds, no tricks
        "pack": {"anchor": 0.70, "limit": 0.80, "rounds": 2, "beta": 1.0},  # silver pack: only if its your_value >= price (E9)
        "lines": [
            "Buenas, Chato. Vengo a por esta carta para completar mi página. ¿{p} P?",
            "Precio justo y cerramos ya: {p} P.",
            "Mi última cifra, sin rodeos: {p} P.",
        ],
    },
}
