# Experimentos

Una fila por ejecución contra el juego. **Hipótesis y parámetros antes de ejecutar; resultado y conclusión después.**
Los datos crudos están en `logs/<dealer>.jsonl` (número de hilo para cruzar). El evento `score` guarda el desglose antes y después: **anotar el Δ de `ladder_points`**.

| ID | Fecha y hora | Qué | Hipótesis | Parámetros | Resultado | Conclusión |
|---|---|---|---|---|---|---|
| EXP-001 | vie 20:25 | `starter_agent.py`, 1 sobre a la Abuela | Primera toma de contacto | Starter: 60 % del presupuesto, +2 por ronda | Trato a 17 P (sobre valorado en 18,1 P para nosotros). Puntuación 7,29 | 17 P era su precio de bienvenida fijo, no fruto del regateo |
| EXP-002 | vie 20:35 | `abuela.py` v0, hilo 38 | El precio de la Abuela baja con un ancla baja | Ancla 9, límite 20 (elegido por nosotros: 0,6 × 33,8 de catálogo, **no viene de la API**), 10 rondas, β = 0,6 | Ella: 30 → 26 → 25 → 24 → **23 final** en 5 ticks; nosotros 9 → 13. **Nos retiramos, sin trato** | El límite de 20 P era un error nuestro: su suelo está en 22–23. Con un ancla baja tarda lo mismo (5 rondas) y la final sale igual, en 23. No hay penalización por no cerrar trato, pero perdimos 5 minutos y quizá cupo |
| EXP-002b | vie ~21:05 | Un compañero, con el starter, sobre (hilo 65) | — | Starter: 16 → 18 | Ella 30 → 25 → 23 (sin final); el hilo se cerró sin trato | Coincide con el suelo de 22–23. Ahora `ladder_points` 0,022 |
| EXP-003a | vie ~21:10 | Un compañero, con un agente LLM, SAL-02 (hilo 68) | Una común baja de 12 a ~10 | Ofertas 5 → 7 | Ella 12 → 10 → **9**: **trato a 9 P**. SAL 8/10. `ladder_points` 0,022 → 0,036, negociación 5,25 → 7,54, 2 tratos | Las comunes bajan hasta 9. Incluye el efecto de la fase, así que el Δ es aproximado |
| EXP-003 | | `run_dealer.py abuela --card SAL-02 --anchor 6 --limit 10 -n 1` (nos falta para la página SAL) | H2 de [scoring.md](scoring.md): una común comprada a ≤ 10 P (tras pedir 12) llena un hueco de la escalera por 10 P en lugar de 22 | Ancla 6, límite 10, 6 rondas, β = 1 | | |
| EXP-004 | | `run_dealer.py abuela --card SAL-08 --anchor 15 --limit 22 -n 1` | Las infrecuentes bajan de 29 a 21–22 (t06) | Ancla 15, límite 22 | | |
