# TO-DO domingo 4 oct (último día)

Plan completo, comandos y razones: [docs/plan-domingo.md](docs/plan-domingo.md). Hechos: [docs/knowledge.md](docs/knowledge.md). Escrituras manuales: [docs/handoffs/HANDOFF-domingo.md](docs/handoffs/HANDOFF-domingo.md).

## 08:30–08:50 (Jorge, máquina A)
- [ ] Energía: tapa = "no hacer nada" (powercfg, plan §4.1), enchufada.
- [ ] Desplegar: `stop` → `lock free` → apartar los no versionados → `merge --ff-only night-build` → `merge night-docs` → `selftest` en verde → `resume --why` → `run --live --arm hygiene,dealers,rastro,closer,duels` desacoplado (plan §4.2).
- [ ] `status`: 5 armadas, `paused ['dealers', 'rastro']`, etapas en verde con el `code_hash` actual, oferta 20117 sin cancelar (plan §4.3).

## 09:00–09:10
- [ ] `clockcheck` a las 09:00:30 y a las 09:05 → escenario A, B o C (plan §3.3).
- [ ] Huevos de la Abuela con `dealers` aún en pausa; `resume rastro` (plan §4.4).
- [ ] `resume dealers` al terminar los huevos, o a las 09:10 como tarde.

## Durante el día (cada uno, a mano y con el OK de Jorge; plan §6)
- [ ] Pilar (nivel 3): SAL-11 si la oferta 20117 caduca sin venderse, LAT-06 #1105 y LAV-03 #788 como prueba.
- [ ] Denuncias de nivel A, ≤ 3, una a una (plan §5.5).
- [ ] Anuncios en v18, uno cada ~10 min de 09:15 a 14:30, con go / no-go a las 11:00 (plan §5.3).
- [ ] Primer duelo de Duels III (~11:00): mirar las alarmas de `days_meaning`. Si las hay, el bot sigue por papel: **no pausar** (plan §5.2).
- [ ] Cada hora, `python3 bazaar.py status`. Nada de reiniciar con duelos vivos. Después de las 13:55, relanzar sin `dealers`.

## Después de las 15:00
- [ ] `python3 bazaar.py stop "fin del juego"`.
- [ ] SHOWCASE.md: sección del domingo.
- [ ] Decidir la visibilidad del repo y si `harness-v2` se fusiona en `main`. Hasta las 15:00, ningún `push`.
- [ ] Limpiar worktrees y ramas ya fusionadas (`audit-fixes`, `night-build`, `night-docs`…).

## Pendiente técnico (no urge; no afecta al juego)
- [ ] `tests/test_architecture.py`: revisar también los `.py` de la raíz con una lista explícita (`bench_rec.py` y `ladder_sell.py` solo GET + `bazaar.py do`, `egg_watch.py` y `announce_candidates.py` sin clave, `observe_performance.py` prohibido).
- [ ] Archivar `observe_performance.py` y su test (envía la clave a un host externo).
- [ ] Pasar `flag_one.py` y `announce_stall.py` del scratchpad al repo, con comprobación de STOP y una fila en el diario.
- [ ] Una prueba de que `panel.html` y `website/panel.html` son idénticos.
- [ ] Código sin conectar: `pages.protect_sets`, `Calibrator.recheck`, `duels.e16_settled` y el grabador L1 dentro del runner (hoy lo hace `bench_rec.py`).
- [ ] Ideas no desplegadas: compras a Ernesto (nivel 5), días como vendedor por debajo del límite, `logroll_w` en duelos, `STALE` en `live_monitor.py` y más pistas en `egg_watch.py` (plan §1.3).
