# Persona 2 · Analista (sábado 3 y domingo 4 oct)

Sin clave, desde cualquier máquina. Solo lecturas públicas y análisis; **nunca** se toca el juego ni `config/plan.json` en la máquina del operador: se le pasa la propuesta y la aplica él.
El código del bot y ambos trabajos están integrados en `main`: `bazaar.py`, `config/plan.json`, `agent/tactics/`, `analista/` y `jury/`.

Tres trabajos:
1. **Duelos II** (hoy, hora de juego 11,65 ≈ **18:29**): proponer `days_sign`.
2. **CHA** (mañana, 09:00): dinero, precios máximos, horario y lista de cambios de configuración.
3. **Rivales**, cada hora: `python3 rivals.py --watch 3600`.

Estado al empezar (10:31, tick 283, t = 3,68): **t18 1.º con 29,66** (neg 22,93 · mercado 6,73). t12 va 2.º con 27,07 gracias al mercado (11,22). t02 va 3.º con 26,69.
**11:09 (tick 359):** t18 30,47 · **t13 30,24, a 0,23** (neg 26,91, 43 tratos) · t05 28,95 · t12 26,52. Mercado: t05 y t12 12,50 frente a nuestros 7,50. La propuesta A (Gate con signo) sigue sin aplicar.

---

## 1. Duelos II: propuesta para `days_sign`

**Datos** (calendario público, RULES, knowledge U-01/U-02/U-12/U-13):
- Hora 11,65, 16 ticks por duelo, decay 0,08, dos vueltas, 6 duelos a la vez, asuntos `price` y `days` (0–10). Mensaje sin `days` → `missing_days`.
- Resultado medido en un asunto: |precio − límite| × (1 − decay)^rondas, con rondas = min(mensajes nuestros, del rival). No se sabe cómo entran los días: en la práctica `your_days_weight` y `days_meaning` llegaron a null.
- "The pie grows for teams that trade on what each side cares about" (calendario). Es una negociación integrativa: cada lado tiene su peso por día.

**Lo que hace hoy el código** (`origin/main`):

| Pieza | `days_sign = null` | `days_sign = ±1` |
|---|---|---|
| Táctica (`agent/tactics/duels.py` `_days_model`) | Exige excedente ≥ 1 + 10·\|w\| en cada precio y envía los días del rival (o 0) | Envía nuestro mejor día (10 o 0) y exige excedente ≥ 1 + (W(mejor) − W(d)), es decir, 1 en nuestro mejor día |
| Gate G50/G51 (`agent/talk.py` `_days_penalty`) | Exige ≥ 1 + \|w\|·max(d, 10 − d) | **Lo mismo: no mira el signo.** En d = 10 o d = 0 exige 1 + 10·\|w\| |

**Hallazgo.** Si se fija el signo sin tocar el Gate, la táctica cree que puede acercarse a L ± 1, pero el Gate exige L ± (1 + 10·\|w\|). Al final de cada duelo saldrán rechazos `G50.limit` en cadena. No hay riesgo de perder puntos: el Gate falla cerrado. Pero el operador tiene la instrucción de pausar los duelos si ve rechazos en cadena. Y si \|w\| es grande frente al pastel, cerraremos pocos duelos con o sin signo. Como referencia, en la práctica el excedente medio por acuerdo fue de unos 21,6 P (389,5 / 18). Con 10·\|w\| ≥ 20, casi nada cumpliría el margen.

Hay otro riesgo: el signo puede depender del papel. Lo normal en una entrega es que el comprador la quiera pronto y el vendedor tarde. Un `days_sign` global acertaría en la mitad de los duelos y en la otra mitad enviaría nuestro peor día. El Gate conservador evita la pérdida, pero se pierde pastel.

**Propuesta.**

A. **Cambio de código antes de las 18:00** (lo hace quien toca código, con test y con el OK del operador). El Gate usa el signo cuando se conoce, igual que la táctica:
```python
# agent/talk.py
def _days_penalty(d, days, sign=None):
    w = d.get("your_days_weight"); _need(_num(w), "G50.days_unknown")
    if sign in (1, -1):                      # peor caso sobre la referencia desconocida, con W monótona conocida
        return abs(float(w)) * ((10 - days) if sign > 0 else days)
    return abs(float(w)) * max(days, 10 - days)
# llamadas en _g50_say / _g51_accept: _days_penalty(d, days, getattr(cfg, "DAYS_SIGN", None))
```
Tests: signo +1 y d = 10 → 0; signo +1 y d = 0 → 10·\|w\|; signo −1 y d = 0 → 0; null → como ahora.
Es seguro: con W monótona y referencia desconocida en [0, 10], W(d) − W(ref) ≥ −\|w\|·distancia(d, mejor extremo).
Opcional, si el signo depende del papel: aceptar `days_sign` como `{"buyer": -1, "seller": 1}` (validación en `agent/tactics/pages.py:103`, lectura en `duels.propose` y en `runner.py:816`).

B. **En el primer duelo de Duelos II** (~18:29). El operador copia de `GET /api/duels`, para 3–6 duelos: `role`, `your_limit`, `your_days_weight` y `days_meaning`. El analista decide:

| Lo que se lee | `days_sign` |
|---|---|
| `days_meaning` dice que más días valen más (o un peso positivo es "valor por día") y el signo es igual en todos nuestros duelos | `1` |
| Lo contrario ("coste por día", entrega tarde peor), igual en todos | `-1` |
| El signo cambia con el papel (comprador frente a vendedor) | `null` + cambio opcional por papel; si no está, se queda en `null` |
| `days_meaning` null, vacío o ambiguo | `null` (J10: la táctica no envía nada sin leerlo) |

Y la regla de margen: si **10·\|w\| > mitad del excedente típico** (\|L − ancla\|) y el cambio A no está, se deja `null`. No se gana nada fijando el signo y solo se añaden rechazos.

C. **Aviso al operador**: con `days_sign` fijado y sin el cambio A, pueden aparecer `G50.limit` cerca del deadline. Avisar y revisar el desajuste antes de aplicar cambios; ante rechazos en cadena, seguir el protocolo de pausa del operador. Un acuerdo con resultado ≤ 0, `E16` o un `G51` que no sea `rival_tick` también requiere revisión. La integración del panel no aplica la propuesta A ni cambia `days_sign`.

La misma decisión vale para **Duelos III** (domingo, hora 18,65 ≈ 11:00, 12 ticks, decay 0,10), salvo que `days_meaning` cambie.

---

## 2. Plan de CHA (domingo)

**Horario** (calendario público; 1 h de juego = 1 h de pared desde las 09:00 si abre a su hora):

| Hora | t | Qué |
|---|---|---|
| 09:00 | 16,65 | Abre el domingo, ronda 3, CHA publicado. Ticks de 15 s |
| 09:03 | 16,70 | +150 P para todos (solo caja) |
| 11:00 | 18,65 | Duelos III (dos asuntos) |
| 13:21 | 21,00 | `closer.endgame_hours.sun`: la puja de cierre sube a 102 |
| 13:45 | — | Último trato con vendedor (J12) |
| 14:00 | 21,65 | Vendedores cerrados y final de duelos |
| 15:00 | 22,65 | Fin: **la caja que quede vale 0** |

**Coste real de RET hoy** (feed público, settlements t205–t230): raras 86 + 86 (El Chato), infrecuentes 22 + 22 (Abuela; RET-07 ya la teníamos), comunes 9, 9, 10, 9, cierre RET-02 a **49** con t02.
Si CHA cuesta lo mismo: 2 × 86 + 3 × 22 + 4 × 9,5 + cierre = 276 + cierre, es decir, **325 con cierre a 49** y **348 con la puja de cierre del plan a 72**. Y el Gate guarda 10 P de reserva (`cash_free`).

**Dinero**: 116 + 150 = 266. **Faltan 69–92 P incluyendo reserva** (325 + 10 − 266 = 69 como objetivo central). Hay que sacarlos hoy:
- Vender LAT (abandonada en t205) como autor a ≥ V + 2 o a pujas con ganancia ≥ 3 (J9/J5). Confirmar el inventario con `bazaar.py status` del operador.
- J13: duplicados de RET a pujas rivales de cierre con ganancia ≥ 15 y recompra a la Abuela (+19 a +32 por ciclo). `rivals.py` avisa de pujas ≥ 30.
- Si a las 22:55 no llega: no hace falta cambiar nada. El orden rara → infrecuente → común compra primero lo escaso, y el cierre usa `min(72, cash_free)`.

**Precios máximos** (`config/plan.json` → `dealer_max` y `profiles`): **no cambiar**.

| Rareza | Tope CHA | Pagado en RET | Valor CHA para nosotros | Margen |
|---|---|---|---|---|
| común | 12 | 9–10 | 16 | ≥ 4 |
| infrecuente | 25 (CHA-08: 31 con El Chato y respaldo de la Abuela) | 22 | 40 | ≥ 9 |
| rara | 100 | 86 | 112 | ≥ 12 |

Los topes solo se alcanzan si el vendedor no baja. El regateo llegó a 86 desde un ancla de 70 con paso 4. Bajar el tope de las raras a 90 ahorraría caja, pero pone en riesgo la página: no lo propongo.

**Lista para las 09:00** (en este orden; lo aplica el operador):
1. 08:40 `git pull` · `python3 bazaar.py selftest` en verde · `status` sin STOP ni candado.
2. 08:50 `python3 bazaar.py clockcheck`: si abre tarde (T0 ≠ 09:00), `day_end_hours.sun = 16,65 + horas(13:55 − T0)`.
3. `config/plan.json`:
   - `"page_sets": ["RET", "CHA"]` (el único cambio obligatorio).
   - `"days_sign"`: el valor decidido en Duelos II (o `null`).
   - Revisar `closer.endgame_hours.sun = 21.0` y `dup_min_price.CHA = 30` (ya están).
4. 08:55 `python3 bazaar.py run --live --arm hygiene,dealers,rastro,closer,duels`, solo las que estén en verde.
5. 09:03 comprobar en `status` que han entrado los +150.
6. 09:05–10:45 compras de CHA: raras primero. El analista comprueba en el feed que cada precio queda ≤ tope. Objetivo: 9/10 antes de Duelos III.
7. Con 9/10: puja de cierre a 72 (J12), y a 102 desde las 13:21 o si un rival puja igual o más.
8. 14:30: gastar la caja sobrante en lo que tenga ganancia (la caja no puntúa).

---

## 3. Vigilancia de rivales

**Panel en vivo: https://t18-analista.vercel.app** (código en `analista/index.html`). Es un HTML estático sin dependencias que lee la API pública desde el navegador (la API envía CORS `*`); no usa clave ni servidor.
- Uso local: `cd analista && python3 -m http.server 8765` y abrir http://localhost:8765 (o abrir el fichero directamente).
- Publicado en Vercel (proyecto `t18-analista`, aparte del panel del equipo). Republicar tras un cambio: `cd analista && npx vercel deploy --prod --yes`.
- Ritmo: clock y feed cada 15 s; clasificación, mercados y El Rastro cada 30 s; calendario cada 5 min (≈ 0,2 lecturas/s).
- Contenido: cuentas atrás del calendario, clasificación con Δ 1 h y tendencia, gráfico de evolución, mercados con tratos/h y alerta, pujas y ventas de El Rastro filtrables con nuestros sobrantes, nuestros tratos comparados con `dealer_max`, pujas de cierre rivales por RET/CHA (J13), calculadora de `days_sign` y de caja para CHA.
- El feed público devuelve como mucho 500 eventos; los minutos cubiertos dependen de la actividad. El panel acumula una selección de hasta 3.000 eventos en el navegador (localStorage), así que conviene dejarlo abierto. No garantiza un historial completo.

### Registro horario


`python3 rivals.py --watch 3600 [--have LAT-01,LAT-05,...]` graba en `logs/rivals.jsonl` y saca un informe:
- **t12 en mercado** (`--team`): ahora 11,22 frente a nuestros 6,73. Es el puesto automático gratuito (casi todos tienen 6,73). t12 tiene mercado propio (`v02`, `board`, 0 % de comisión).
- **Mercados de equipo con tratos por hora**: ALERTA si alguno pasa de 3/h → se replantea abrir mercado propio. Ahora solo `v02` (t12) tiene tratos: 2, 17 P.
- **Pujas grandes en El Rastro** (≥ 30 P, `--min-bid`). Con `--have` marca las de cartas que tenemos de sobra → avisar al operador.

Cada informe relevante se apunta en este documento con hora, tick, dato y decisión. Los experimentos históricos están en `archive/docs/experiments.md`.


## Integración con Persona 3 y el harness

- El panel enlaza **Demo del jurado** (`analista/jurado.html`), incluida en la misma carpeta para servirla en el despliegue estático.
- **Exportar para jurado** descarga `analista-publico.json`: clasificación, reloj, catálogo y eventos públicos retenidos. Hace una lectura pública de catálogo; no exporta caja, sobrantes, ajustes, mensajes ni claves. El almacenamiento local es modificable: esta exportación es evidencia observada por el navegador, no un diario autenticado.
- Sin red, con Python 3.10+: `python3 -m jury.report --analyst-export analista-publico.json`. El informe en `runs/jury/` reutiliza `agent.affinity` y conserva fecha de captura y cobertura parcial. El RAG no recibe desenlaces ni liquidaciones inventadas a partir de un HTTP ok o una puja ausente.
- Para renovar el paquete estático desde datos oficiales: `python3 -m jury.report --refresh --output jury --team-output analista`. Genera la demo en ambos lugares y `analista/plan-public.js` con topes y hash de `config/plan.json`. Son los límites del repo, no la configuración que Jorge tenga cargada en ese momento.
- `rivals.py` ahora usa `public_get` sin leer `.env` ni necesitar clave. No se modifican la Gate, la táctica de duelos ni el plan operativo.
- Estados de pujas: desaparecer de El Rastro significa **sin confirmar**, no liquidada. Cancelaciones numéricas se conservan; ofertas en otros mercados no se declaran abiertas por mirar solo El Rastro. El tope de una carta no se compara con el precio total de un lote. Δ 1 h espera una hora completa de historial de la misma ronda.
- Verificación: `node --test analista/evidence.test.cjs`; Python: `python3 -m unittest tests.test_jury tests.test_rivals_public tests.test_affinity tests.test_architecture`. La publicación en Git no republica por sí misma un despliegue manual de Vercel; para actualizar el enlace alojado seguir el comando de despliegue de arriba.
