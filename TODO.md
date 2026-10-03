# TO-DO domingo 4 oct (último día)

Plan completo y razones: [docs/DOMINGO.md](docs/DOMINGO.md). Hechos: [docs/knowledge.md](docs/knowledge.md). La lista del sábado está en el historial de Git.

## Antes de las 09:00 (Jorge, máquina A)
- [ ] Energía: enchufada; tapa = "no hacer nada"; nada de suspender (el sábado se durmió 48 min, knowledge S-31).
- [ ] Decidir si se despliega `night-build`. Si sí: `stop` → `status` sin pendientes → fast-forward de `harness-v2` → `selftest` en verde → `resume` → `run --live --arm hygiene,dealers,rastro,closer,duels`.
- [ ] `resume dealers` y `resume rastro`: siguen en pausa desde el sábado.
- [ ] `egg_watch.py` en marcha (archiva el feed).

## 09:00–09:05
- [ ] `python3 bazaar.py clockcheck` a las 09:00:30 y a las 09:05 → escenario A, B o C (DOMINGO §1).
- [ ] Si no está desplegado el cálculo de horas en vivo: ajustar `day_end_hours.sun` y `closer.endgame_hours` en `config/plan.json` al escenario y relanzar (DOMINGO §1).
- [ ] Primer duelo de Duels III: `days_sign` es −1 o +1, no `None`.

## Durante el día (cada uno, a mano y con el OK de Jorge)
- [ ] Ventas a Pilar para el nivel 3: LAT-06 repetida; SAL-11 solo a ≥ 199.
- [ ] Denuncias de nivel A, como mucho 3, una a una (DOMINGO §3.6).
- [ ] Huevos: Castizo, cocido y Chato, solo si las líneas de `talk.py` están desplegadas y antes de reanudar `dealers` (DOMINGO §3.7).
- [ ] Anuncios de orgánico en v18, como mucho 1 cada 5 min (DOMINGO §3.4).
- [ ] Cada hora: `python3 bazaar.py status`. Nada de desplegar con duelos vivos.

## Después de las 15:00
- [ ] SHOWCASE.md: sección del domingo.
- [ ] Decidir la visibilidad del repo y si `harness-v2` se fusiona en `main`. Hasta las 15:00, ningún `push`.
- [ ] Limpiar worktrees y ramas ya fusionadas. La lista está en la auditoría de ramas de la noche; nunca tocar `night-build` ni `night-docs` mientras se usen.

## Pendiente técnico (dueño: el código, no los documentos)
- [ ] `tests/test_architecture.py`: revisar también los `.py` de la raíz con una lista explícita (`bench_rec.py` solo GET, `egg_watch.py` sin clave, `observe_performance.py` prohibido).
- [ ] Archivar `observe_performance.py` y su test (envía la clave a un host externo).
- [ ] `config/plan.json`: CHA-09/10 `dealer_max` 100 frente al límite del perfil 60; perfiles muertos `SAL-11` y `LAT:rare`, y `dealer_max` de LAT; `_notes` del domingo; `startup_cancels` y `baseline_bands` sin efecto.
- [ ] Una prueba de que `panel.html` y `website/panel.html` son idénticos.
- [ ] Código sin conectar (no urge): `pages.protect_sets`, `Calibrator.recheck`, `duels.e16_settled` y el grabador L1 dentro del runner (hoy lo hace `bench_rec.py`).
