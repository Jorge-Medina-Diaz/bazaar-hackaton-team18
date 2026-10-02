# Experimentos

Una fila por ejecución contra el juego. **Hipótesis y parámetros antes de ejecutar; resultado y conclusión después.**
Los datos crudos están en `logs/<dealer>.jsonl` (número de hilo para cruzar).

| ID | Fecha y hora | Qué | Hipótesis | Parámetros | Resultado | Conclusión |
|---|---|---|---|---|---|---|
| EXP-001 | vie 20:25 | `starter_agent.py`, 1 sobre a la Abuela | Primera toma de contacto | Starter: 60 % del presupuesto, +2 por ronda | Trato a 17 P (sobre valorado en 18,1 P para nosotros). Puntuación 7,29 | 17 P era su precio de bienvenida fijo, no fruto del regateo |
| EXP-002 | vie 20:35 | `abuela.py` v0, hilo 38 | El precio de la Abuela baja con un ancla baja | Ancla 9, límite 20, 10 rondas, β = 0,6 | Su final fue 23 P con nuestra oferta en 13 P. Con límite 20 nos íbamos a retirar | El límite de 20 P es demasiado bajo: su suelo está en 22–24 P. Se sube a 24 |
| EXP-003 | | `run_dealer.py abuela`, 3 sobres | Ofrecer más arriba (15 P) y con pasos más grandes cierra en 22–23 P en menos rondas | Ancla 15, límite 24, 6 rondas, β = 1 | | |
