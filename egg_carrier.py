"""Huevos de pascua del domingo (solo prestigio, nunca puntúan): ladder_sell.py con las variantes de huevo primero.

Abre un hilo de VENTA con el dealer para una carta suelta, manda las variantes de huevo (talk.EGG_LINES: abuela_sell
5 = Castizo/chotis, 6 = cocido; chato_sell 3 = calamares; banco_sell 5 = Casa Prima, solo con pruebas), una por
tick y con precios descendentes, y después regatea con las variantes normales hasta >= FLOOR. Mismas lecturas
(solo GET) y escrituras (`bazaar.py do ... --live`, por la Gate) que ladder_sell.py. Cada uso necesita el OK de Jorge.

    python3 egg_carrier.py abuela 940 MAL-01 6 9,8,7,6 5,6           # Castizo y luego cocido
    python3 egg_carrier.py chato 938 LAV-02 8 14,12,11,10,9,8 3      # calamares (solo con CHA-06/07/08 ya en mano)
Nunca: "oro de Moscú" (LAT-13 es de t02) ni la línea del Lazarillo a los Pícaros.
"""
from __future__ import annotations

import sys

from ladder_sell import main as _ladder


def main(argv) -> int:
    if len(argv) < 6 or argv[5] in ("", "-"):
        print(__doc__)
        return 2
    return _ladder(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
