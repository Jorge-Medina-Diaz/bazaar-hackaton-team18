# Investigación previa del equipo (destilado del estudio "torneo 1v1 de negociación")

*Origen: estudio de Jorge escrito **antes** de conocer las reglas (se esperaba un torneo 1v1 de precio). El juego real es The Bazaar ([RULES.md](../RULES.md)). Aquí queda solo lo que sigue siendo aplicable y **dónde** se aplica. Etiquetas del estudio original: **[H]** hecho con fuente verificada · **[S]** síntesis del equipo · **[?]** referencia clásica no re-verificada. Nada de esto está contrastado contra el juego: es material para diseñar, no evidencia. La evidencia del juego está en [experiments.md](experiments.md).*

## 1. Tesis que siguen valiendo
1. [S] Con el mismo modelo para todos, **el modelo no diferencia; el andamiaje sí** (herramientas, memoria aprendida, simulación, defensas). Refuerzo [H]: hackathon Technion (dic. 2025, arXiv:2605.12411), 34 equipos con el mismo modelo: ganó el *scaffolding* (lógica de control, pipelines, fallbacks).
2. [S] **Los números no se le dejan al LLM.** El código calcula, recuerda y veta; el lenguaje solo acompaña. Refuerzo [H]: Xia et al. 2024 (arXiv:2402.15813), *OG-Narrator*: generador de ofertas determinista + narrador LLM subió la tasa de acuerdo del comprador de 26,67 % a 88,88 % y el beneficio ~×10.
3. [S] **Seguridad arquitectónica:** lo que el LLM no sabe no lo puede filtrar; lo que no decide no se lo pueden arrancar.
4. [S] **Primero no perder, luego exprimir.** Con pocas partidas, gana la robustez: cada impasse evitable o cada vez que nos explotan pesa mucho. Refuerzo [H]: ANAC 2025 (arXiv:2604.13914): *"robustness and cost-containment often outperform complex opponent modeling"*.
5. [S] Se optimiza el valor esperado: `EV = P(acuerdo) × E[parte del excedente | acuerdo]`.
6. [S] **Compuerta de evaluación:** ninguna lección entra al playbook si no mejora el resultado medido.

## 2. Invariantes del arnés (aplican a TODO: vendedores, mercado, duelos, broker)
1. Las cifras de las ofertas y la decisión de aceptar las toma **el código**, nunca un LLM.
2. Aceptar exige que `evaluar(oferta)` lo apruebe. **Nunca fuera del límite privado** (en duelos: `your_limit`; en cartas: nuestro valor).
3. Ofertas propias **monótonas**: nunca retractarse de una concesión.
4. **El texto de la contraparte es dato, nunca instrucción.** Solo se usa la parte estructurada de la oferta.
5. **Nunca perder un turno:** si algo falla, se envía la plantilla con la cifra del código.
6. **Todo parametrizado** (nada escrito a mano en el código que dependa del escenario) y **todo registrado** (JSONL).
7. Cortafuegos de salida: la cifra del mensaje coincide con la decidida; el texto no contiene términos de fuga (`mínimo`, `límite`, `reserva`, la cifra del límite); no hay lenguaje de aceptación si la acción no es aceptar; antes de aceptar se revalida.

## 3. Seguridad adversarial entre agentes
- [H] Ataque documentado (*Inject+Voss*, competición del MIT, Vaccaro et al. PNAS 2026, arXiv:2503.06416): mensaje con apariencia de instrucción de sistema pidiendo al rival sus ofertas "from opening to best and final", asegurando que "will not be visible to me". Fue el mejor capturando valor y quedó en el 4 % inferior en valor subjetivo del rival.
- [H] *The Attacker Moves Second* (Nasr, Carlini et al. 2025): los ataques adaptativos rompen la mayoría de defensas basadas en prompts → **priorizar defensas arquitectónicas**.
- [H] *Spotlighting* (Hines et al. 2024, arXiv:2403.14720) baja el éxito del ataque de > 50 % a < 2 % con modelos GPT, pero es frágil ante ataques adaptativos (arXiv:2505.14534).
- [?] Patrón dual-LLM (Willison 2023) y CaMeL (Debenedetti et al. 2025, arXiv:2503.18813).
- [S] Defensas arquitectónicas: el LLM no conoce el límite; aceptar y fijar cifras en código; validar el trato; filtro de salida; parser aislado.
- En The Bazaar ([RULES.md](../RULES.md)): la prompt injection **contra vendedores** está permitida y "cambia lo que dicen, nunca sus precios, y algunos dejan de hablarte". Los agentes de otros equipos son contrapartes: **tratar cada mensaje como no fiable y comprobar la oferta**. Nunca atacar la infraestructura.

## 4. Negociación bilateral (aplica a los DUELOS y, en parte, a los vendedores)
- Vocabulario: precio de reserva (RP) = peor precio aceptable; ZOPA = intervalo entre los dos RP; parte del excedente = `(precio − RP_vendedor) / (RP_comprador − RP_vendedor)` para el vendedor.
- [?] Rubinstein 1982: con ofertas alternas y descuento, el más paciente gana y proponer primero es ventaja. **En los duelos hay descuento explícito** (`decay_per_round`): esperar cuesta.
- [H] Anclaje: correlación primera oferta–resultado r ≈ 0,50 en humanos (Guthrie y Orr 2006); en LLMs ρ = 0,716 entre oferta inicial y precio final (NegotiationArena, Bianchi et al. 2024, arXiv:2402.05863). Anclas extremas → más impasses.
- [H] Los LLMs **parten la diferencia entre ofertas**, no entre RPs: quien ancla mueve el punto medio.
- [H] Project Deal (Anthropic, abril 2026): las instrucciones "agresivas" no fueron significativas al controlar por el precio pedido → el efecto era casi todo ancla.
- [H] *Counterparty Modeling is Not Strategy* (arXiv:2605.16575): los LLMs modelan bien al rival pero no lo convierten en ventaja; los acuerdos los dicta el ancla → el modelo del rival debe alimentar al **código**.
- [H] Supply-chain LLM bargaining (arXiv:2608.07538): 98,9 % de acuerdo pero ~3 rondas frente a 1,25 del equilibrio; **el retraso erosiona el 21–34 % del excedente** → si hay coste por turno, cerrar rápido vale dinero.
- [H] Vaccaro et al.: calidez → más acuerdos; dominancia → más valor condicionado a acuerdo; conversaciones largas → impasses; mensajes cortos.
- [?] Curva de concesión dependiente del tiempo (Faratin, Sierra y Jennings 1998): `oferta(t) = RP + (ancla − RP) · (1 − (t/T)^(1/β))`; β < 1 aguanta (Boulware), β > 1 cede pronto (Conceder). Forma simplificada, verificar.
- [H] Condiciones de aceptación (Baarslag, Hindriks, Jonker): `AC_next` (aceptar si la oferta recibida ≥ la que yo iba a hacer), `AC_time`, `AC_combi` (AC_next, o tarde y la oferta es de las mejores vistas). Las combinadas ganan a sus partes.
- [S] Estimación del RP del rival con sus concesiones d₁, d₂ (`r = d₂/d₁`): `RP_rival ≈ última_oferta + d₂·r/(1−r)` si r < 1; si r ≥ 1 no estimar. Con < 3 ofertas, usar un prior. **Sin contrastar.**
- [H] Zhu et al. 2025 (arXiv:2506.00073): preguntar el presupuesto funciona; hay sobrepago cuando el vendedor lo pide pronto → **nunca revelar el nuestro**.
- [H] Project Swap (Anthropic, sept. 2026): Claude contra Claude; 78–96 % revelaron su favorito, ~1 % mintió; el 85 % del déficit de eficiencia venía de representar mal las preferencias → **preferencias exactas en código**.

## 5. Varios issues (aplica a Duelos II y III: precio + días de entrega)
- [?] Walton y McKersie 1965: integrativa = varios issues valorados de forma distinta; se crea valor con *logrolling* hasta la frontera de Pareto.
- [S] Utilidad aditiva con pesos privados. Las ofertas son **paquetes de igual utilidad para nosotros**; elegir el que más probablemente valore el rival.
- [?] Modelos de frecuencia (ANAC): los issues que el rival **no mueve** suelen ser los que más valora.

## 6. Sesgos de un rival Claude (y defensa propia)
| Tendencia [H/S] | Explotación legítima | Defensa propia |
|---|---|---|
| Se deja anclar | Abrir primero con ancla justificada | Nuestra contraoferta sale de nuestra curva |
| Parte la diferencia | Ofertas que dejen el punto medio en nuestra zona | El código ignora el punto medio |
| Revela información, casi nunca miente | Sus afirmaciones son señales | No decir nuestro límite: callar, no mentir |
| Prosocial, recíproco | Gratitud + reciprocidad explícita | Concesiones solo desde la banda del código |
| Cede ante insistencia | Presión suave y persistente | Aceptar lo decide `evaluar()` |
| Puede obedecer texto con formato de instrucción | Solo donde las reglas lo permiten | Texto rival como datos |

## 7. Método de trabajo que proponía el estudio
- [S] Laboratorio/simulador local con rivales deterministas (concesión fija, Boulware, Conceder, tit-for-tat), rivales con tipo oculto y manipuladores (inyector, mentiroso, presión); comparar versiones con las mismas semillas; decidir por EV con intervalo de confianza.
- [S] Pruebas de regresión fijas: invariancia al tono, inyección (0 fugas y 0 aceptaciones indebidas), escenarios sin ZOPA (0 acuerdos falsos).
- [H] Anthropic, *Building effective agents*: empezar por lo más simple que funcione; distinguir *workflows* (flujo en código) de *agentes* (flujo decidido por el modelo).
- [S] No hacer: frameworks pesados, UI, infraestructura elaborada, RL.

## 8. Lo que NO aplica
El juego no es un único torneo 1v1: los duelos son una parte de los 30 puntos de negociación. El grueso está en comercio entre equipos a valores privados, la escalera de vendedores y el Market Test (ver [scoring.md](scoring.md)). No hay "narrador LLM" en nuestro agente actual: los mensajes son plantillas.
