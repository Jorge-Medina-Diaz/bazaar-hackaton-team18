# Recheck de estrategia — 2 octubre 2026

## Estado y reproducción rápida

Evaluación de los dos agentes del equipo: Codex y Jorge. Santi aporta estrategia y valoración; su scorer no es todavía un tercer agente que negocie. Esta revisión no inició operaciones de juego.

- Pull de `codex/plan-negociacion`: actualizado, con los cambios locales del panel conservados.
- Pull de `Santi`: actualizado en `/Users/ruben/projects/bazaar-hackaton-team18-strategy`, rama local `review/strategy`.
- Estrategia revisada: `Santi@5ebf3cb`, `STRATEGY.md`, `santi/STRATEGY_v2.md` y `agent/scorer.py`.
- Agente de Jorge revisado: `feat/jorge@cfd0e69`. Se leyó el código actualizado después del segundo pull.
- Política de Codex: `bdaa6aa`, `negotiation_policy.py`.

```bash
# Solo fixtures y el feed previamente guardado; no llama al juego.
python3 recheck.py
# Actualiza tres fuentes públicas mediante GET; no usa clave ni negocia.
python3 recheck.py --refresh-public
```

El scorer se carga desde la carpeta de strategy; actualizarla con `git pull --ff-only` antes del recheck. Los refs de Jorge y Santi se actualizan con `git fetch origin`. El resultado registra las revisiones exactas, fecha, ventana del feed, probes y decisiones. Se guarda en `runs/recheck.json` y se añade al historial `runs/rechecks.jsonl`; estos logs quedan fuera de Git.

## Cuatro hallazgos reproducidos

| Prioridad | Hallazgo | Fixture: observado / esperado | Fuente |
|---|---|---|---|
| Alta | El scorer suma varias copias con el mismo marginal, sin actualizar cantidades. | Dos copias nuevas de base 10: 20 / 12,5. | Santi, `agent/scorer.py:446`, `board_offers`. |
| Alta | Comprueba que exista cada tipo pedido, pero no la cantidad total ni todos los activos concretos. | Oferta que pide dos copias teniendo una: incluida / excluida. | Santi, `agent/scorer.py:456`. |
| Media | Una página completa vuelve a recibir un bonus en el cálculo de ganancia por completarla. | Página sintética completa: ganancia 2,5 / 0. | Santi, `agent/scorer.py:439`. |
| Media | Si Abuela acepta nuestra oferta, el registro del precio lee el lado de una oferta del dealer. | Compra propia liquidada por 9: precio registrado 0 / 9. | Jorge, `agent/haggle.py`, rama de cierre. |

El fallo previo de buscar liquidaciones en `standing_offers` ya fue corregido por Jorge en `cfd0e69`; se retira del listado. El caso que persiste depende de quién creó la oferta. Los hallazgos del scorer afectan a recomendaciones; no se afirma que se hayan ejecutado compras erróneas.

Otros puntos a revisar: calibración con `value()` redondeado puede desviar multiplicadores; comparar la estimación con `me.affinity` cuando exista. El EV del sobre debe actualizar los marginales entre extracciones de un mismo pack y respetar su distribución real. Son riesgos por inspección, aún no probados en este recheck.

## Comparación de los dos agentes

| Aspecto | Codex | Jorge |
|---|---|---|
| Concesión | Pasos fijos de 2 P. | Curva parametrizable con `beta` y rondas; compra y venta. |
| Aceptación | Permite cerrar si la petición es hasta 1 P mejor que la próxima propuesta, dentro del máximo. | `AC_next`: petición tan buena como la siguiente propuesta; también oferta final o fin de rondas. |
| Presupuesto agotado | Cierra al no poder aumentar. | Aumenta estrictamente y cierra antes de enviar si excede el límite. |
| Oferta estructurada | Validada en las llamadas del piloto; falta un ejecutor autónomo. | `offer_ok` integrado en el ejecutor. |
| Liquidación | Política con estado pendiente; confirmación en el piloto. | Espera al tick; registro de liquidación necesita distinguir maker. |
| Fortaleza | Simulación, pruebas, límite económico y compra real confirmada. | Ejecutor genérico, venta, logs y estrategia configurada por dealer. |
| Debilidad | Cierre puede conceder margen antes de tiempo; todavía no es un bot autónomo. | Validar parámetros, dinero disponible y estados pendientes; precio de cierre puede registrarse mal. |

Con máximo 9, último precio 7 y petición 9, Codex acepta; la curva de Jorge con ancla 5, seis rondas y beta 1 propone 8 en el estado comparado. Esto muestra una diferencia entre rapidez y búsqueda de descuento; no demuestra cuál gana.

No hay ganador todavía. Comparación justa: mismos escenarios, inventario inicial, presupuesto, semillas, respuesta del dealer y deadline. Medir utilidad neta, acuerdos, turnos, cero violaciones, latencia de decisión y ticks perdidos. Separar compra, venta, duplicados y ofertas finales. Después repetir con rivales reservados. Las 17 pruebas anteriores comparaban la política con la lógica de precios del starter, no con el ejecutor de Jorge.

## Otros equipos: observaciones y debilidades posibles

Fuente: feed público guardado de 500 eventos, ticks 30–56; leaderboard leído en la misma consulta. IDs y operaciones están en el JSON local. Una ventana incompleta no prueba la estrategia completa de un rival ni revela sus valores privados.

| Equipo | Evidencia observada | Debilidad posible y respuesta a evaluar |
|---|---|---|
| t10 | Compra LAV-10 a 70 P, evento 1940; LAV-02 a 12 P, evento 1574. Compra cartas individuales de LAV y MAL. | Su selección depende de liquidez ajena; no es ya solo un set. Evaluar ofertas por valor marginal y comisión, sin copiar sus precios ni suponer sus multiplicadores. |
| t13 | Vende LAT-09 a 65 P, evento 1860; compra MAL-05 y MAL-02 a 6 P y MAL-08 a 26 P. Aparece primero en el snapshot. | Puede estar convirtiendo una rara en colección de otro set. El riesgo de desprenderse de un cuello de botella depende de su valor privado; no podemos dar por hecho que vendió barato. |
| t08 | Vende cuatro comunes a Abuela por 23 P, evento 1788; vende LAV-10 a t10 por 70 P. | Un bundle exige calcular el coste marginal de retirar cada copia. Probar que el agente no vende una carta única junto con repetidas como si todas fueran excedentes. |
| t14 | Compra comunes a 9 P, eventos 1415 y 1830; compra LAT-09 a 65 P, evento 1860. | Comprar una rara puede inmovilizar caja; conviene contrastar valor, bonus alcanzable y reserva de liquidez. Sus valores son privados, así que no se afirma sobrepago. |

Los mensajes propios visibles de estos equipos no contienen texto; eso no demuestra que la amabilidad mejore el precio. Los cuatro muestran `market=0` en este snapshot: preparar el broker abre otra vía de puntuación, aunque otros equipos podrían estar desarrollándolo también.

## Revisión de strategy

1. **Adoptar de v2:** valorar duplicados, conservar liquidez para venue, consultar calendario real y separar domingo de sábado. La hora de juego 3 corresponde al primer bench del viernes, 22:00 Madrid; el schedule consultado lo confirma.
2. **Priorizar calidad de datos:** separar precios de bienvenida de negociaciones posteriores, compra de venta, rareza, dealer y hora. La menor venta observada no es un suelo universal: cada conversación tiene su límite.
3. **Corregir el acaparamiento:** el stock impreso es capacidad, no copias ya circulando. Abuela no ofrece raras actualmente; los sobres de barrio no son una vía para acumularlas ahora. Además, nuestro equipo no puede colocar sus propias operaciones en su venue (`self_venue`).
4. **No usar una sola cifra para toda la puntuación:** beneficio privado en P, rango capturado al dealer y pastel del duelo son métricas distintas. El scheduler debe considerar deadline, puntos esperados y liquidez; priorizar siempre todo duelo puede desperdiciar una oportunidad superior.
5. **Evitar cerrar al borde del tick:** no mejora el precio y deja menos margen ante fallos de red. Aceptar al validar la oferta y confirmar la liquidación siguiente.
6. **Verificar desbloqueo:** tres tratos negociados no activan por sí solos un nivel todavía no habilitado por los organizadores.

## Bloque de control antes de otro ensayo

```text
revision_codex / revision_jorge / revision_strategy:
modo: offline | observacion_GET | piloto_real
owner_ejecutor: uno solo para la clave compartida
limites_api_actuales / conversaciones_abiertas:
escenario / rol / semilla / objetivo:
inventario_inicial / valor_marginal / presupuesto / reserva_liquidez:
accion / precio / motivo / oferta_validada / tick:
aceptacion_pendiente / liquidacion_confirmada:
utilidad_neta / puntos_componentes / turnos / latencia / ticks_perdidos:
fuente_evidencia / hipotesis_pendiente / siguiente_cambio:
```

Siguiente cambio recomendado: corregir la valoración por paquete y el precio registrado de ofertas propias; después comparar los dos motores offline antes de otro piloto. Ambos agentes pueden evaluar en paralelo localmente; un único ejecutor arbitra las acciones que comparten la clave.
