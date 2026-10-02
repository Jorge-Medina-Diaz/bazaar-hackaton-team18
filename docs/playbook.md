# Playbook

Conocimiento confirmado, por vendedor y por mecánica. Cada afirmación lleva su fuente (experimento `EXP-…` o `scout`).
Lo no confirmado va en [experiments.md](experiments.md) hasta que lo esté.

## Puntuación
Todo el detalle está en [scoring.md](scoring.md). Resumen: no cerrar trato con un vendedor no penaliza (el hueco vale 0); en los duelos, un trato fuera de tu límite resta; el dinero no puntúa por sí mismo.

## Abuela Carmen (nivel 1)
Ficha: paciencia 0.85, generosidad 0.8, astucia 0.2, memoria 0.15. Vende 3 sobres por equipo y hora y hace 8 tratos por equipo y hora. Compra comunes e infrecuentes.

**Sobres (`sobre_barrio`, precio de salida 30, precio de lista 26)**
- "Welcome, hijo! … Made for beginners" sale también en hilos que empiezan en 30 (hilo 65): **la frase no indica el precio**. Al principio de la partida, el **primer hilo de cada equipo** recibía un precio fijo ("Made for beginners"): 17 P en sobres e infrecuentes y 7 P en comunes. No se mueve. (scout, hilos 2–16)
- En los siguientes hilos: 30 → 26 → 25 → 24 → **oferta final de 22–24**. Concede unas 4 P la primera vez y luego 1 P por ronda. (scout, hilos 21–38)
- **El precio que ofrecemos apenas mueve su suelo**: ofreciendo 13 P recibimos una final de 23 P (hilo 38); ofreciendo 22 P, t05 cerró en 22 P. (scout)
- Para nosotros un sobre vale unas 18 P (`your_value` del sobre cerrado), pero el dinero no puntúa: lo que importa es la parte del rango capturada.
- **Los sobres a 24 P parecen no puntuar nada (t07, t12); a 22 P sí (t05).** Si compramos sobres, solo a ≤ 23. (scoring.md, H1)
- Su ritmo es de 5 ticks desde 30 hasta la final, empecemos alto o bajo (EXP-002 y scout). Abrir bajo no acelera ni mejora la final.

**Oferta final (`"final": true`): no hay segunda oportunidad** (feed, 11 hilos con final)
- La final **nunca baja**: repite su último precio o lo baja 1 P, y después no vuelve a moverse.
- Si no se acepta, se va: hilo 12, "Oh no, hijo, not today. Come back after lunch" al tick siguiente, con pinta de `cooloff`. Excepción: hilo 11, donde t08 igualó la final 3 ticks después y ella cerró ("Venga, 17 P"). **No contar con eso.**
- La final llega antes si contraofertamos lejos o con pasos pequeños: t12 a 21 → final 24, t06 a 22 → final 24, nosotros a 13 → final 23. t05 subiendo 16 → 18 → 20 → 22 cerró en 22 **antes** de la final.
- Cada conversación tiene su propio suelo secreto (RULES): 22, 23 o 24 en sobres.
- **Regla:** ante una final, decidir en ese mismo tick: aceptar si está dentro del límite y, si no, retirarse (D-006).

**Cartas sueltas**
- Comunes: 12 → 10 → **9** (nuestro hilo 68: SAL-02 a 9); 12 → 11 → 10 (t13); en el hilo de bienvenida, 7 P fijo (t17).
- Infrecuentes: 29 → 26 → 24 → 23 → 21–22 (t06 LAV-06 a 21, LAV-07 a 22; t10 a 24).
- **Las cartas sueltas son la forma barata de llenar los 3 huecos de la escalera** (t13: 11,73 puntos con 37 P). (scoring.md, H2)
- Comprándonos a nosotros: una infrecuente a 13 P fijo y una común a 5 P fijo, con final enseguida. (scout, hilos 18, 32, 37)

**Parámetros actuales** (`agent/dealers.py`): sobre con primera oferta del 50 % del precio de salida (15 P), límite del 77 % (23 P, por H1), 6 rondas, β = 1.

**Regalos:** a algunos equipos la Abuela les regala una carta ("gift from Abuela Carmen"), a nosotros LAT-05. Probablemente por ser amables. No puntúa, pero es una carta.

## Duelos
Pendiente. Diseño previo en [negotiation-design.md](negotiation-design.md). Ojo: el pastel se reduce con cada ronda (decay 0.06–0.08).

## Market Test / broker
Pendiente. El broker de ejemplo solo saca la mitad de los puntos; para más hay que estimar los límites ocultos de los traders.

## Comercio en El Rastro (tick 46)
- Los vendedores aparecen con seudónimo (`mf60b788f`…). Ofrecen comunes a 10–12, infrecuentes a 22–35 y una rara a 70 (precio de catálogo o más). **Para nosotros todas dan ganancia negativa**: nuestra affinity en LAV, MAL y LAT es baja.
- Hay pujas de 6 P por comunes de MAL y LAT-06, y de 15 P por MAL-07: ese equipo seguramente tiene una affinity alta en MAL.
- La comisión la paga **quien acepta** (5 % + 1 P/carta). Si publicamos nosotros, el comprador la paga y nosotros cobramos el precio entero.
