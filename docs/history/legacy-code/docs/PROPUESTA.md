# Primera mejora: negociar con un límite claro

Estado: Rubén autorizó empezar con pruebas incrementales. Implementados la política local y el laboratorio; la integración en el starter real sigue pendiente. Rubén autorizó el commit y el push a `codex/plan-negociacion`.

- Repositorio: `Jorge-Medina-Diaz/bazaar-hackaton-team18`.
- Rama local: `codex/plan-negociacion`, creada desde `main` en `ca4228b`.
- Carpeta local: `/Users/ruben/projects/bazaar-hackaton-team18`.
- Los cinco archivos del kit coinciden con el kit oficial que ya revisamos.

## La idea

Empezar con una mejora pequeña del negociador: que cada turno produzca una decisión explícita de ofrecer, aceptar, esperar la liquidación o cerrar. Distinguir el último precio enviado, el próximo precio y el presupuesto máximo.

El beneficio esperado es conservar turnos y paciencia, respetar el presupuesto y poder comprobar las decisiones antes de usar dinero del juego. Esta mejora por sí sola no garantiza mejores descuentos ni una posición en la clasificación.

## Problema concreto del código actual

En `starter_agent.py:29`, el próximo precio se calcula con `min(budget, offer + 2)`. Al alcanzar el presupuesto, el precio deja de cambiar. El bucle puede volver a enviarlo si el dealer todavía pide más, aunque `RULES.md:45` indica que repetir precio no obtiene concesiones.

Ejemplo: presupuesto 26 P, último precio enviado 26 P y dealer pidiendo 28 P. El siguiente precio calculado vuelve a ser 26 P. La decisión propuesta es cerrar con un motivo claro si no hay una oferta aceptable.

También hay que resolver expresamente una oferta `final`: aceptarla si cumple el presupuesto y el criterio de compra, o cerrar si queda fuera. Después de enviar una aceptación, esperar a confirmar la liquidación en vez de tratarla como una compra ya terminada.

## Cambios que planteo

| Archivo | Cambio previsto |
|---|---|
| `negotiation_policy.py` (nuevo) | Función de decisión sin red: recibe estado, oferta del dealer, presupuesto y último precio enviado; devuelve acción, precio si corresponde y motivo. |
| `starter_agent.py` | Usar esa decisión en el bucle y controlar la espera tras una aceptación. Guardar el precio como enviado solo cuando la petición haya tenido éxito. |
| `tests/test_negotiation_policy.py` (nuevo) | Casos locales con `unittest`; no requieren credenciales ni operaciones reales. |

Mantendríamos para esta primera mejora la subida de 2 P como referencia comparable. La elección de cartas, los valores privados y las concesiones adaptativas se abordarían después de comprobar que el flujo básico funciona.

Si falla una escritura de forma ambigua, consultar el estado antes de repetirla: el SDK ya evita reintentar ciegamente errores de red en escrituras. La forma exacta de confirmar la liquidación deberá ajustarse a las respuestas documentadas o reales de la API; no inventar campos.

## Casos de prueba y criterios de aceptación

| Caso | Resultado esperado |
|---|---|
| Última oferta propia 26, máximo 26, dealer pide 28 | Cerrar; no repetir 26 ni ofrecer más de 26. |
| Queda margen para subir | Enviar un precio nuevo dentro del presupuesto. |
| Oferta final aceptable | Aceptar una vez y pasar a espera de liquidación. |
| Oferta final fuera del presupuesto | Cerrar con motivo explícito. |
| Aceptación pendiente | Esperar; no emitir otra oferta o aceptación desde esa conversación. |
| Conversación terminada | Salir del bucle conservando el motivo y el resultado. |
| Presupuesto insuficiente para un precio válido | Detenerse antes de crear una oferta de precio cero. |

Las pruebas verificarán decisiones y transiciones, sin llamadas al servidor. Más adelante se podrá contrastar una negociación real, una vez verificada la clave del equipo y acordado el ensayo.

## Lo siguiente que revisaría

1. Comprar cartas según su valor privado y faltantes de colección, en vez de elegir siempre un sobre.
2. Ajustar concesiones usando la respuesta del dealer y medirlas contra la subida fija.
3. Mejorar el broker: ya encontramos un libro pequeño donde su elección voraz pierde una segunda operación válida.

## Estado de esta entrega

Se añadieron la política, el laboratorio, el evaluador y 17 pruebas locales. Se ejecutaron ocho simulaciones y una compra real de El Portero por 9 P, confirmada en el inventario. El starter y el broker originales conservan su código. La política se aplicó mediante llamadas controladas de Codex; la integración en un ejecutor autónomo sigue pendiente.

Rubén indicó dejar a Claude de momento y avanzar con las pruebas. Este trabajo es de Codex, no una revisión conjunta atribuida a Claude.
