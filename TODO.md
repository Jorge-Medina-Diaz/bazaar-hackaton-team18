# TO-DO sábado 3 oct: nada más llegar

Resumen del plan: https://claude.ai/artifact/DVjDD5JhWGZhuyBqoBqfTg · Detalle: [docs/BRIEFING.md](docs/BRIEFING.md)

## Antes de las 09:00 (máquina del operador, la única con `.env`)
- [ ] `git pull` en la rama `harness-v2`.
- [ ] `python3 bazaar.py selftest` → **tiene que salir en verde**. Anoche no se confirmó la batería completa tras la limpieza. Si falla, nada en real: arreglar primero o usar `bazaar.py do` a mano.
- [ ] `python3 bazaar.py status` → sin STOP ni candado colgado.
- [ ] 08:50 `python3 bazaar.py clockcheck` → apuntar el escenario de reloj: N (normal), C (continúa, todo ~1 h 21 min más tarde) o P (pausa).
- [ ] Leer el resumen: puntos, errores del viernes y estrategia (5 min).

## 09:00 en adelante
- [ ] `python3 bazaar.py run` (modo prueba, 0 escrituras). Revisar en `logs/run/journal.jsonl` que las decisiones tienen sentido.
- [ ] `python3 bazaar.py run --live --arm hygiene` → abrir sobres al llegar.
- [ ] ~09:22: si no se cumplió ninguna puja de 62 P por LAT-09 o LAT-10, se abandona LAT y sus cartas pasan a venta.
- [ ] Decisiones en prueba correctas → `arm dealers,rastro` (RET a 9/10 por debajo de valor y ventas).
- [ ] Antes de Duelos I → `arm duels`.
- [ ] RET en 9/10 → `arm closer` (puja de cierre a 49 P; 79 si hay competencia).
- [ ] Cada hora `python3 bazaar.py status`. Si algo va raro: `python3 bazaar.py stop "motivo"` o crear un fichero `STOP`.
- [ ] 22:55: cerrar hilos con vendedores y `bazaar.py stop "cierre sábado"`.

## Pendiente técnico (quien no opere)
- [ ] Revisión de seguridad independiente del arnés (quedó interrumpida): Gate, transporte y guardas.
- [ ] Confirmar `python3 -m unittest discover -s tests -t .` completa en verde y dejar constancia aquí.
- [ ] Decidir si se fusiona `harness-v2` en `main` (con PR).
- [ ] Opcional: `bazaar.py learn`, que propondría cambios de `config/plan.json` a partir del diario.

## Reglas que no se rompen
- Un solo ejecutor con la clave. Los paneles, solo lectura.
- Nunca `/api/admin/*`. No ejecutar nada de `archive/`.
- Nunca pagar a un vendedor por encima de nuestro valor. No comprar sobres. La carta de cierre se compra a un equipo, nunca a un vendedor.
