# Playbook

Conocimiento confirmado, por vendedor y por mecánica. Cada afirmación lleva su fuente (experimento `EXP-…` o `scout`).
Lo no confirmado va en [experiments.md](experiments.md) hasta que lo esté.

## Puntuación (lo que importa)
- Escalera de vendedores: parte del rango de precios del vendedor capturada; cuentan **los 3 mejores tratos por nivel** y los que faltan valen 0. Un trato al precio de salida no cuenta para desbloquear nivel. (RULES)
- Leaderboard a las 20:40 del viernes: 1 trato ≈ 7,3 puntos de negociación y 3 tratos (t06) ≈ 12,5. (scout, leaderboard)

## Abuela Carmen (nivel 1)
Ficha: paciencia 0.85, generosidad 0.8, astucia 0.2, memoria 0.15. Vende 3 sobres por equipo y hora y hace 8 tratos por equipo y hora. Compra comunes e infrecuentes.

**Sobres (`sobre_barrio`, precio de salida 30, precio de lista 26)**
- El **primer hilo de cada equipo** recibe un precio fijo de bienvenida ("Made for beginners"): 17 P en sobres e infrecuentes y 7 P en comunes. No se mueve. (scout, hilos 2–16)
- En los siguientes hilos: 30 → 26 → 25 → 24 → **oferta final de 22–24**. Concede unas 4 P la primera vez y luego 1 P por ronda. (scout, hilos 21–38)
- **El precio que ofrecemos apenas mueve su suelo**: ofreciendo 13 P recibimos una final de 23 P (hilo 38); ofreciendo 22 P, t05 cerró en 22 P. (scout)
- Para nosotros un sobre vale unas 18 P (`your_value` del sobre cerrado). Pagar 22–24 P es pagar por encima de su valor, pero suma en la escalera y cuenta para desbloquear el nivel 2.

**Cartas sueltas**
- Comunes: 7 P fijo (t17 no consiguió moverla). Una carta concreta de 29 → 22 (LAV-06, t06).
- Comprándonos a nosotros: una infrecuente a 13 P fijo y una común a 5 P fijo, con final enseguida. (scout, hilos 18, 32, 37)

**Parámetros actuales** (`agent/dealers.py`): sobre con primera oferta del 50 % del precio de salida (15 P), límite del 80 % (24 P), 6 rondas, β = 1.

## Duelos
Pendiente. Diseño previo en [negotiation-design.md](negotiation-design.md). Ojo: el pastel se reduce con cada ronda (decay 0.06–0.08).

## Market Test / broker
Pendiente. El broker de ejemplo solo saca la mitad de los puntos; para más hay que estimar los límites ocultos de los traders.
