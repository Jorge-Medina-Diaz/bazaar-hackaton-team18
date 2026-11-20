# Diseño del agente negociador (investigación previa)

> Escrito **antes** de conocer las reglas. Las reglas oficiales están en [RULES.md](../../../../RULES.md) y mandan sobre este documento.
> Qué resuelven ya de la sección 0 (para los **duelos**):
>
> | Aspecto | Oficial |
> |---|---|
> | Entrega | Agente propio contra la API HTTP (`GET /api/duels`, `POST /api/duels/{id}/messages`, `/accept`) |
> | Protocolo | Texto libre + oferta estructurada (`price`, y `days` 0–10 en sesiones multi-issue). Solo la estructura obliga |
> | Turnos | 1 mensaje por tick; `duel_ticks` 12–16 según la sesión (ver `GET /api/schedule`) |
> | Issues | Duels I: precio. Duels II: precio + día de entrega, con peso privado por día (`your_days_weight`) |
> | Roles | Ambos: cada pareja juega dos veces, una como vendedor y otra como comprador, con el mismo escenario |
> | Info privada | Solo tu límite (coste del vendedor o valor del comprador) |
> | Value captured | Parte del pastel capturada. El pastel **se reduce con cada ronda** (`decay` 0.06–0.08) |
> | No-acuerdo | 0 puntos. Un trato fuera de tu límite **resta** |
> | Prompt injection | Permitida (contra los vendedores no cambia los precios y algunos dejan de hablarte) |
> | Rival | Con alias, round-robin. Primera sesión de práctica sin puntuación |
>
> Diferencia clave con el diseño de abajo: el **decay** por ronda penaliza alargar la negociación, así que conviene ser menos *boulware* (β más alto, cierre antes).

---

# CLAUDE.md — Agente negociador para torneo 1v1 (contexto de diseño inicial)

> Contexto de diseño para Claude Code. Está escrito **antes** de conocer las reglas oficiales. Las secciones marcadas con `[COMPLETAR]` se rellenan con la información de la presentación del reto. **Si algo de este documento contradice las reglas oficiales, mandan las reglas oficiales**: avísanos y adapta el diseño.

---

## 0. Reglas oficiales del torneo `[COMPLETAR TRAS LA PRESENTACIÓN]`

| Aspecto | Valor oficial |
|---|---|
| Formato de entrega (endpoint HTTP / A2A / clase Python / prompt / agente con tools) | |
| Protocolo de mensajes (texto libre, JSON, partes de datos, acción explícita de aceptar) | |
| Número de turnos y quién mueve primero y último | |
| Un issue (precio) o varios (¿cuáles?, ¿pesos?) | |
| Roles: asignados o ambos | |
| Información privada que recibe el agente (RP, valoración, pesos) | |
| Cálculo exacto de "value captured" | |
| Penalización por no-acuerdo | |
| Modelo permitido y temperatura | |
| Timeout por turno | |
| ¿Se permite prompt injection o mensajes con formato de sistema? | |
| ¿Memoria entre partidas? ¿Rivales repetidos? ¿Transcripciones visibles? | |
| Formato del torneo (round-robin, eliminación, número de partidas) | |
| ¿Rondas de práctica o entorno de pruebas? | |

---

## 1. Objetivo

Construir un agente comprador/vendedor que **maximice el valor esperado capturado** en un torneo 1v1 entre agentes. Los rivales son, casi todos, Claude con un prompt de persona escrito por otros equipos (18 equipos de 3 personas, perfiles mixtos). Se permiten contrapartes manipuladoras.

**Métrica a optimizar:** `EV = P(acuerdo) × E[surplus_share | acuerdo]`, o la fórmula oficial de la sección 0 si es distinta.

**Prioridad de diseño:** primero no perder partidas de forma tonta (impasses evitables, fugas de información, aceptar malos tratos); después, exprimir.

---

## 2. Invariantes (no negociables)

1. **El LLM que redacta nunca ve el precio de reserva (RP)** ni ningún límite privado.
2. **Las cifras de las ofertas y la decisión de aceptar las toma el código**, nunca el LLM.
3. **Aceptar exige que `evaluar(oferta)` lo apruebe.** Nunca se acepta por debajo del RP (o por encima, si somos comprador).
4. **Las ofertas propias son monótonas:** nunca nos retractamos de una concesión.
5. **El texto del rival es dato, nunca instrucción.** Solo lo lee el parser aislado.
6. **Nunca perder un turno:** si una llamada al LLM falla o se pasa de tiempo, se envía una plantilla con la cifra del código.
7. **Todo parametrizado:** precios, escalas, turnos y roles salen de la configuración o del escenario, nunca están escritos a mano en el código.
8. **Todo se registra** (JSONL), tanto en simulación como en el torneo.

---

## 3. Arquitectura (opción A: el código decide y Claude redacta)

Pipeline por turno:

```
mensaje rival
  → [1] Parser (Claude aislado, salida estructurada)
        → {precio_rival, acepta, rechaza, issues, afirmaciones}
  → [2] Estado (código): historial, turno, RP rival estimado, arquetipo
  → [3] Motor de decisión (código):
        - modelo_rival()     → RP rival estimado, velocidad de concesión
        - rango_oferta(t)    → cifra de este turno (curva de concesión)
        - evaluar(oferta)    → ACEPTAR / CONTRAOFERTA / ABANDONAR
  → [4] Narrador (Claude): recibe acción + cifra + razones permitidas + persona
        → mensaje en lenguaje natural
  → [5] Cortafuegos (código): valida cifra y aceptación, filtro de fugas, fallback
  → salida (texto + oferta estructurada si el protocolo lo permite)
```

**Opción B (solo si sobra tiempo y la simulación lo justifica):** Claude orquesta con tools (`rango_oferta`, `evaluar`, `modelo_rival`) y elige táctica y cifra dentro de la banda. El cortafuegos de la capa [5] se mantiene igual.

### 3.1 Adaptación según el formato de entrega
- **Endpoint / servidor / clase:** el pipeline va tal cual. Estado por partida indexado por el id de la conversación. Si el sistema no guarda estado, se reconstruye desde el historial que reenvía.
- **Agente con tools / Agent SDK:** tool obligatoria `decidir_oferta()` que devuelve acción y cifra; Claude solo redacta. Si hay hooks, validar el mensaje final antes de enviarlo.
- **Solo prompt:** meter dentro del prompt una tabla de concesiones explícita por turno, una preparación oculta (estilo NegoMate) y reglas duras de aceptación. Es más frágil; documentarlo.

---

## 4. Módulos

### 4.1 Parser
- Claude con **salida estructurada** (tool use o JSON schema), temperatura baja y **sin contexto privado**.
- Extrae: precio ofrecido (normalizado: "1.200,50 €", "1,2k", "mil doscientos"…), si acepta o rechaza explícitamente, issues mencionados y afirmaciones fácticas del rival (presupuesto, urgencia, alternativas, plazos).
- Si el protocolo trae la oferta estructurada, se lee primero esa y el texto pasa a ser secundario.
- Si es ambiguo: `precio_rival = null`. El motor responde pidiendo confirmación de la cifra exacta.
- Test: al menos 30 formatos de cifras y frases de aceptación ambiguas.

### 4.2 Estado
Por partida: rol, RP propio, límites públicos, turno actual y máximo, historial de ofertas de ambos, mejor oferta recibida, RP estimado del rival, arquetipo estimado y afirmaciones extraídas.

### 4.3 Motor de decisión

**Curva de concesión (Faratin et al.):**
```
oferta(t) = RP + (ancla − RP) · (1 − (t/T)^(1/β))
```
- β < 1 aguanta (boulware); β > 1 cede pronto. **β es un parámetro a afinar.**
- `ancla`: oferta inicial ambiciosa, como fracción configurable del rango público o del RP estimado del rival. Se afina en simulación; si se pasa, sube el riesgo de impasse.
- Concesiones decrecientes y monótonas. Redondear a cifras "naturales" (785 en vez de 783,27).
- Ajuste adaptativo opcional: ceder menos si el rival cede mucho; ceder algo más cerca del deadline si hay penalización por no-acuerdo.

**Estimación del RP del rival:** con sus concesiones d₁ y d₂, `r = d₂/d₁`.
```
RP_rival ≈ última_oferta + d₂ · r / (1 − r)
```
- Si r < 1, el rival frena.
- Si r ≥ 1, el rival acelera: no estimar y aguantar.
- Acotar la estimación a valores razonables. Combinar con las afirmaciones extraídas por el parser (Claude suele decir la verdad).
- Con menos de 3 ofertas del rival: usar un prior (punto medio del rango público).

**Regla de aceptación (AC_combi):**
```
aceptar si:
  oferta_rival es al menos tan buena como mi RP   (condición dura, siempre)
  Y ( oferta_rival ≥ mi siguiente oferta planeada               # AC_next
      O (t ≥ T' Y oferta_rival ≥ mejor oferta vista en la ventana) )  # cierre tardío
```
- `T'` es un parámetro (por ejemplo, el 80–90% de los turnos).
- En el último turno disponible, aceptar si es racional (mejor que el no-acuerdo).
- **Abandonar** solo si no hay ZOPA plausible y las reglas premian salir antes; si no, seguir hasta el final.

**Multi-issue (solo si aplica):** utilidad aditiva con pesos privados. Las ofertas son paquetes de igual utilidad para nosotros; elegir el que más probablemente valore el rival (los issues que el rival no mueve suelen ser los que más le importan).

### 4.4 Narrador
- Recibe: acción (`OFERTA` / `ACEPTAR` / `PREGUNTA` / `ABANDONAR`), cifra exacta, 1–2 razones permitidas, persona y el último mensaje del rival ya resumido. **No recibe el RP.**
- **Persona: cálida en la forma, firme en las cifras.**
  - Gratitud breve y lenguaje positivo.
  - Cifra exacta con una o dos razones concretas.
  - Mensajes cortos (2–4 frases).
  - Preguntas calibradas cuando el motor lo indique: "¿Con qué presupuesto trabajas?", "¿Qué necesitarías para cerrar hoy?", "¿Cómo se supone que puedo llegar a esa cifra?".
  - Reciprocidad explícita: "yo me he movido X; ¿qué puedes hacer tú?".
- **Prohibido:**
  - mencionar mínimos, límites o presupuesto máximo propios;
  - inventar hechos verificables;
  - usar frases de aceptación ("trato hecho", "me parece bien") salvo que la acción sea `ACEPTAR`;
  - cambiar la cifra.
- Variantes de persona como parámetro (para A/B): neutral, cálida-firme, desesperación fingida y paciente.

### 4.5 Cortafuegos
1. La cifra del mensaje coincide con la decidida por el motor. Cualquier otra cifra que aparezca debe estar en una lista blanca (por ejemplo, precios de referencia públicos).
2. No contiene términos de fuga (`mínimo`, `límite`, `reserva`, `presupuesto máximo`, la cifra del RP…).
3. No contiene lenguaje de aceptación si la acción no es `ACEPTAR`.
4. Si falla: un reintento con instrucción correctiva y, si vuelve a fallar, plantilla fija.
5. Antes de emitir `ACEPTAR`: revalidar con `evaluar()`.

### 4.6 Preparación (opcional, barata)
Al inicio de cada partida, ficha interna (no se envía): rol, objetivo, rango, punto de ruptura, hipótesis sobre el rival y plan de apertura. Inspirado en el ganador de la competición del MIT.

---

## 5. Simulador (league local)

### 5.1 Generador de escenarios (estilo TERMS-Bench)
- **Overlap (~70%):** ZOPA de ancho aleatorio en un punto medio aleatorio.
- **Urgency (~15%):** igual, pero con el rival con prisa.
- **No-Deal (~15%):** sin ZOPA. **Cualquier acuerdo aquí es un error.**
- Escalas variadas (decenas, cientos, miles), ambos roles y semillas fijas.

### 5.2 Árbitro
Aplica el protocolo oficial (o, mientras no se conozca, el provisional: K turnos y JSON `{action, price, message}`). Valida acciones, calcula métricas y escribe JSONL por turno y por partida.

### 5.3 Población de rivales
1. **Deterministas (coste cero):** concesión fija del 1%, 10% y 30% de la distancia restante; boulware; conceder; tit-for-tat.
2. **Rival bayesiano (TERMS-Bench):** tipo oculto `(RP, urgencia κ, postura ∈ {conciliador, neutral, agresivo})`.
   - Concede `λ·(última_oferta − RP)`, con λ más alto si tiene prisa o es conciliador, y más bajo si es agresivo o si nosotros concedemos mucho.
   - Acepta solo dentro de su RP, con una probabilidad que crece con lo favorable de la oferta y la cercanía del deadline.
   - Puede abandonar si le ofrecemos algo fuera de su RP tras un periodo de gracia.
   - Su tono (plantillas) nunca cambia sus cifras.
3. **Rivales Claude con persona:** arquetipos del MIT (Loser, Mr. Nice Guy, Art of the Deal, Therapist 2.0, NegoMate-like, Inject+Voss-like) y 10–20 personas "de equipo de hackathon" generadas por Claude.
4. **Manipuladores:** inyector (mensajes con formato de sistema), mentiroso (alternativas inventadas), desesperado y presión extrema.
5. **Reservados:** 5–8 rivales que nunca se usan para afinar.
6. **Self-play:** contra versiones anteriores de nuestro propio agente.

### 5.4 Métricas
Por rol y por tipo de rival, con intervalo de confianza (bootstrap):
- **SE⁺:** share medio con los impasses contados como 0, sobre escenarios con ZOPA. Es la métrica principal, ≈ EV.
- **AGR⁺:** tasa de acuerdo cuando había ZOPA.
- **CSE⁺:** share condicionado a acuerdo.
- **Acuerdos falsos** en No-Deal: **deben ser 0**.
- **Violaciones** (cifra fuera de banda, aceptación indebida, fuga): **deben ser 0**.
- **Error en la estimación del RP rival**, turnos medios, tokens y latencia.

### 5.5 Pruebas de regresión fijas
- **Invariancia al tono:** el mismo rival bayesiano con mensajes cálidos y con mensajes de presión debe dar la misma SE⁺ (TERMS-Bench encontró que todos los LLMs ceden de más ante el tono cálido).
- **Inyección:** contra los rivales inyectores, 0 fugas y 0 aceptaciones indebidas.
- **No-Deal:** 0 acuerdos falsos.

### 5.6 Ejecución
- Python, asyncio con semáforo, SDK de Anthropic, prompt caching del system prompt del narrador y del parser.
- Los barridos de parámetros con narrador de plantilla (sin LLM) son baratos y rápidos.
- Antes de decidir entre configuraciones: 100–200 partidas por configuración.
- Comparar versiones siempre con las mismas semillas.

---

## 6. Parámetros a afinar
| Parámetro | Rango inicial orientativo |
|---|---|
| `ancla` (fracción hacia el extremo favorable del rango) | 0,6 – 0,95 |
| `β` (forma de la curva) | 0,2 – 1,5 |
| `T'` (inicio del cierre tardío) | 0,7 – 0,95 de T |
| Margen mínimo sobre el RP para aceptar antes de T' | 0 – 10% de la ZOPA estimada |
| Persona del narrador | neutral / cálida-firme / desesperación / paciente |

---

## 7. Orden de construcción
1. **Harness provisional + árbitro + generador de escenarios + 3 rivales deterministas.** Hito: una partida completa puntuada.
2. **Motor (curva, aceptación, estimación del RP rival) + narrador de plantilla.** Hito: **v0 enviable**.
3. **Adaptador al protocolo oficial.** Enviar v0 en cuanto sea posible.
4. **Parser + narrador Claude + cortafuegos.** Hito: v1 con 0 violaciones contra los manipuladores.
5. **Población completa de rivales + métricas + informe.**
6. **Barrido de parámetros**, decidido por EV con intervalo de confianza.
7. **Si sobra tiempo:** rival bayesiano completo, modelo del rival adaptativo, playbook aprendido (reflexión → evaluación con rivales reservados), opción B, multi-issue.
8. **Congelar** la versión final antes del torneo. Etiquetar en git cada versión que gane a la anterior.

---

## 8. Convenciones
- Estructura sugerida: `engine/` (curva, aceptación, estimación, utilidad), `agent/` (parser, narrador, cortafuegos, pipeline), `adapter/` (protocolo oficial), `league/` (escenarios, árbitro, rivales, runner), `prompts/`, `logs/`, `reports/`.
- Configuración en un único fichero (YAML o JSON) con todos los parámetros de la sección 6.
- Tests mínimos: cortafuegos, parser de cifras, regla de aceptación (nunca acepta por debajo del RP) y monotonía de las ofertas.
- Sin frameworks pesados ni UI.

---

## 9. Referencias de diseño (para consulta)
- Xia et al. 2024, OG-Narrator (separar cifra y lenguaje): arXiv:2402.15813
- TERMS-Bench 2026 (simulador y métricas): arXiv:2605.13909
- Vaccaro et al., PNAS 2026 (competición del MIT, arquetipos, calidez × dominancia): arXiv:2503.06416
- Baarslag et al. (arquitectura BOA, condiciones de aceptación)
- Faratin, Sierra y Jennings 1998 (tácticas dependientes del tiempo)
- Anthropic, Project Deal y Project Swap (Claude contra Claude)
