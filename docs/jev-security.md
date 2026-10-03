# JEV: seguridad y evaluación acotada

## Qué está implementado

`harness/jev_security.py` proporciona un cliente de evaluación de relevancia.
No importa el cliente del Bazaar ni posee herramientas para comprar/vender.
Las probabilidades sirven para ordenar **los documentos ya admitidos**; no
autorizan operaciones ni modifican reglas económicas.
También admite el propósito fijo `pattern_check`: siete preguntas Noul definidas
por código sobre un único caso. No admite preguntas arbitrarias de un plan.

1. **Credenciales:** clave en variable de entorno o archivo regular fuera del
   checkout, propiedad del usuario y permisos `0600`. No se guarda en informes.
   El archivo solo contiene la clave. El proveedor recibe la clave en la cabecera
   de autenticación; nunca dentro del estado enviado al modelo.
2. **Salida de datos:** endpoint HTTPS fijo de OpenRouter, modelo Jev 1.13,
   sin proxies del entorno ni redirecciones que puedan reenviar Authorization.
   Solo consulta/alcance y evidencia mínima. Etiquetas de evaluación, rutas
   locales y campos extra de los planes quedan fuera de la petición.
3. **Memoria:** se vuelve a comprobar dealer, compra/venta, carta/fase cuando
   están especificadas, versión, estado activo y visibilidad pública/propia.
   Los metadatos deben proceder de nuestro importador: la comprobación no
   autentica un archivo que alguien haya podido manipular en el disco.
4. **Instrucciones:** preguntas reconstruidas por código. Ni el dealer ni un
   plan JSON pueden cambiar modelo, endpoint o instrucciones. El texto de la
   evidencia sigue siendo entrada no confiable; un modelo puede malinterpretarlo.
5. **Respuesta:** solo Noul entre 0 y 1, valores finitos, IDs exactos de las
   preguntas y modelo/proveedor esperados. Datos inválidos no se aplican.
6. **Consumo:** máximo nueve solicitudes por evaluación, seis documentos por
   consulta, 20.000 bytes por petición y 128.000 bytes acumulados. Sin reintentos.
   Timeout de socket de 15 s, no un límite absoluto de duración ante un servidor
   que envíe fragmentos continuamente. Primera evaluación fallida detiene las
   solicitudes posteriores. Los fallos consumen el cupo reservado.
7. **Informes:** JSON local en `runs/`, creación privada y reemplazo atómico.
   Guarda IDs, probabilidades, modelo, uso/coste declarado y código de error;
   no cuerpos de mensajes ni excepciones del proveedor.

El filtro rechaza patrones de claves OpenRouter/Bazaar y campos explícitos de
credenciales, incluso JSON dentro del cuerpo. **No detecta cualquier secreto o
dato personal posible.** Revisar y minimizar las fuentes antes de enviarlas.

## Ejecutar

Modo predeterminado: respuestas ficticias neutrales. Comprueba el recorrido;
no mide precisión, latencia ni coste de JEV real.

La primera prueba real posterior está documentada en [jev-real-testing.md](jev-real-testing.md):
18 solicitudes,90 juicios y cero operaciones del juego. No cambia los límites de
seguridad ni convierte las pruebas repetidas en casos independientes.

```bash
python3 run_jev_eval.py
python3 -m unittest tests.test_jev_security tests.test_retrieval -v
```

Con una clave propia guardada fuera del repo y `chmod 600` aplicado al archivo:

```bash
python3 run_jev_eval.py --live --key-file /ruta/privada/openrouter.key
```

También admite `OPENROUTER_API_KEY`; nunca pasar la clave como argumento literal.
El corpus y consultas predeterminados son los archivos locales del piloto RAG.
Las nueve consultas con candidatos y las tres sin evidencia producen como máximo
nueve solicitudes; las tres vacías no consumen llamada. Se prepara y comprueba
el plan antes de iniciar la primera solicitud. Las etiquetas solo se usan localmente
para comparar recall@3 con el orden original. No es una evaluación independiente
ni una prueba de mejora en negociación o beneficios.

## Controles de cuenta y límites pendientes

Los cupos locales se reinician al arrancar otra evaluación: **no constituyen un
tope económico de la cuenta**. Configurar en OpenRouter un límite pequeño por
clave sin reinicio, desactivar recargas automáticas si no se desean y revisar
las opciones de registro/retención. Estos ajustes no se han cambiado ni verificado
en la cuenta de Rubén. Reemplazar una clave compartida en texto reduce exposición.

Antes de conectar recomendaciones al agente, el ejecutor debe comprobar de nuevo
oferta estructurada, saldo, precio máximo/mínimo, comisiones, inventario, tick,
cuotas, permisos y operaciones pendientes. `harness/market.py:DecisionGate` ya
ofrece una puerta experimental local, aún no integrada en el ejecutor real.
No sirve de bloqueo distribuido entre operadores. Mantener un solo ejecutor.

No se garantiza inmunidad a prompt injection, exactitud de JEV ni protección
total. Las pruebas verifican controles del programa; no miden robustez semántica
del modelo ni la seguridad de la infraestructura del proveedor.

## Fuentes oficiales comprobadas

- [Decisions API de OpenRouter](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request).
- [API y tipos de TypeSafe](https://docs.typesafe.ai/api).
- [Límites de claves](https://openrouter.ai/docs/api/api-reference/api-keys/create-a-new-api-key).
- [Privacidad de OpenRouter](https://openrouter.ai/docs/guides/privacy/data-collection).
