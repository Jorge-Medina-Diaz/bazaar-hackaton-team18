# Traspaso del equipo — 2026-10-02

## Repositorio y autorización

- Repositorio: `https://github.com/Jorge-Medina-Diaz/bazaar-hackaton-team18.git`.
- Carpeta: `/Users/ruben/projects/bazaar-hackaton-team18`.
- Rama: `codex/plan-negociacion`, creada desde `main` en `ca4228b`.
- Rubén autorizó pruebas incrementales, después juego real y finalmente commit y push de nuestros cambios a esta rama. Claude quedó al margen por su indicación.
- Se revisaron README y reglas oficiales. No se reutilizó código de negotiation-lab. Los starters y el SDK originales conservan su código.
- No se incluyen credenciales ni respuestas privadas completas de la API. Los archivos locales del panel aparecidos durante la sesión pertenecen a otro trabajo y quedan fuera de este commit.

## Implementación y evaluación

- `negotiation_policy.py`: decisiones sin red para ofrecer, aceptar, esperar o cerrar. Respeta máximo, ofertas finales y liquidación pendiente; evita repetir precio al llegar al límite.
- `laboratorio.py`: simulación local paso a paso sin API. Escenarios de compra, límite, oferta final y varias cartas con duplicados.
- `evaluacion.py`: pruebas y comparación de dos políticas en cuatro escenarios. `require_passed` bloquea la siguiente etapa cuando falla la evaluación.
- Pasaron 17 pruebas y ocho simulaciones. La evaluación previa tardó aproximadamente 0,002 segundos dentro de Python; no incluye arranque del proceso ni red.
- En `limite`, el starter simulado necesita 13 decisiones y repite seis precios; la mejora cierra en ocho decisiones sin repetir. En los otros escenarios no se observó mejora del precio pagado.
- Estas simulaciones verifican decisiones, presupuesto y liquidación; no miden persuasión real ni predicen puntuación.

## Piloto real terminado

La clave corregida funcionó. Otro proceso había abierto una conversación para comprar un sobre. Rubén indicó que ese proceso ya estaba detenido; se cerró aquella conversación sin comprar y se inició el piloto de carta individual.

Objetivo: El Portero (`SAL-02`), que faltaba en la colección. Se consultó su valor marginal y se fijó un máximo antes de negociar. Conversación 68, oferta aceptada 480.

| Tick | Acción |
|---|---|
| 37 | Apertura de conversación para SAL-02. |
| 38 | Abuela pide 12 P. |
| 39 | Propuesta propia de 5 P, con saludo amable y referencia a la colección. |
| 40 | Abuela baja a 10 P. |
| 41 | Propuesta propia de 7 P, agradeciendo su respuesta. |
| 42 | Abuela baja a 9 P. |
| 44 | Se valida la oferta estructurada y se acepta por 9 P. |
| 45 | Oferta settled, conversación deal y carta presente en el inventario. |

Resultado: una carta adquirida, descuento de 3 P (25 %) respecto a la petición inicial y ganancia neta de 2 P según el valor marginal consultado antes de comprar. No se abrieron sobres durante el piloto.

La compra está confirmada por saldo, nuevo activo y estado de liquidación. Una negociación no demuestra que el tono amable causara el descuento ni que 9 P fuera el mejor precio posible. Recalcular el valor marginal antes de comprar otra copia.

## Rapidez y siguiente paso

Los ticks del viernes duran 60 segundos. También hubo demora evitable entre turnos al preparar el evaluador mientras la negociación estaba abierta; Rubén pidió mayor rapidez y actualizaciones frecuentes.

Siguiente mejora: un ejecutor que evalúe antes de abrir la conversación y actúe al recibir cada respuesta, registrando acción, precio y motivo. Debe confirmar la liquidación, consultar el valor de cada nueva copia y evitar dos procesos actuando a la vez para el equipo. La integración autónoma sigue pendiente; el piloto se ejecutó mediante llamadas controladas de Codex.

Evaluación: `python3 evaluacion.py`. Recorrido: `python3 laboratorio.py --scenario compra --step`.
