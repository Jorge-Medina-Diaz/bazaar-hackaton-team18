# Persona 3 · Jurado

El trabajo rota entre miembros. La demo y el análisis público no necesitan clave.
Actualizar requiere **Python 3.10+**, como el nuevo módulo Affinity de main.
Abrir el HTML ya generado no requiere Python.

## Abrir y actualizar

1. Abrir `jury/demo.html` en el navegador: cuatro secciones, navegación con botones o flechas. Es una instantánea fechada, no un panel en directo.
2. Para datos nuevos: `python3 -m jury.report --refresh`. Hace cuatro GET públicos una sola vez, limitados a una petición por segundo; guarda `runs/jury/demo.html` y `evidence.json` fuera de Git. Abrir ese HTML.
3. Solo en la máquina de Jorge, opcionalmente: `python3 -m jury.report --refresh --journal logs/run/journal.jsonl`. Lee una copia de bytes, verifica la cadena y exporta contadores. No exporta mensajes, claves, precios, límites ni contenido del diario. No repara el archivo.

El informe no adquiere candado, arma tácticas ni envía operaciones. Tampoco
requiere JEV, OpenRouter, un túnel o servidor remoto. El visor operativo sigue
siendo `run_traces.py` en la máquina del operador.

## Guion provisional de tres minutos

Duración propuesta hasta que la organización confirme su formato.

- **0:00–0:35 · Idea.** «Cada carta vale distinto para cada equipo. Diseñamos un agente que decide con valor marginal, comisiones y límites; repartimos operación, análisis y evidencia entre tres personas».
- **0:35–1:20 · Control.** Mostrar la Gate, el candado de escritor, dry y STOP. «Los mensajes persuaden, pero los campos estructurados y las guardas deciden». Explicar el límite de flatten si preguntan por recuperación.
- **1:20–2:10 · Aprendizaje.** Mostrar predicción frente a medición y Affinity. «Inferimos preferencias con 720 hipótesis, y expresamos incertidumbre. JEV y RAG se prueban fuera del ejecutor; el ensayo pequeño no mostró mejora de Recall».
- **2:10–3:00 · Evidencia.** Mostrar fecha y tick, los tres fixes de Jorge y las pruebas de la integración. Contar RET/tiempos solo con el diario confirmado. Cerrar con los huecos de la fórmula y el siguiente experimento.

## Mensaje para la organización

> Hola, somos el equipo 18. ¿Cuándo se presenta ante el jurado, cuánto dura y en qué formato? ¿Hay formulario o enlace de entrega y fecha límite? ¿Podemos mostrar una demo local y qué criterios concretos usaréis para los 40 puntos?

No se ha enviado: falta canal o contacto. El «formulario» es ese enlace/documento
de entrega; no se pide ninguna clave.

## Rotación y siguiente paso

- Leer SHOWCASE, comprobar tick y refrescar antes de presentar.
- Apuntar última actualización, responsable y evidencia pendiente.
- Pedir a Jorge el diario o el informe agregado generado por él. No copiar su clave.
- Verificar identidad de las páginas, tiempo real de completar RET y compras frente al calibrador. Un pass de ventana con varias liquidaciones no prueba cada compra individual.
- Mantener «oficial / medido / inferido» en cada afirmación. No asociar subir de puesto únicamente con nuestro código: el marcador es relativo.
- Incorporar preguntas del formulario cuando llegue. La demo se puede imprimir como cuatro páginas desde el navegador.

## Cómo incorporar esta rama

Trae documentación y `jury/`; no sustituye `agent/`, el runner ni `config/plan.json`.
El snapshot publicado es público y agregado. Revisa el diff y conserva cambios
locales antes de fusionar. No actualizar ni reiniciar el ejecutor en caliente
solo para abrir la demo. Ante cualquier actualización del código operativo,
el único operador decide cuándo parar y repetir selftest.

El main actualizado también incluye `rivals.py` (rol analista) y
`affinity.py --history` (evolución de inferencias). Sus notas complementan el
relato del jurado. La demo pública usa directamente el modelo puro y
`public_get`, y no necesita configurar el cliente ni una clave.


## Recibir el trabajo del analista

La misma carpeta `analista/` incluye `jurado.html` y un enlace entre ambos roles.
En el panel, **Exportar para jurado** produce `analista-publico.json` con datos
públicos seleccionados; los ajustes de caja e inventario no salen del navegador.
Después ejecutar `python3 -m jury.report --analyst-export analista-publico.json`
y abrir `runs/jury/demo.html`. No consulta la API ni llama a modelos.
La fecha es la de la captura; el feed acumulado sigue siendo parcial y no
sustituye el diario privado. Las estimaciones Affinity quedan etiquetadas como
inferencias del modelo sobre esa selección.

Para reconstruir los archivos del paquete del equipo, usar
`python3 -m jury.report --refresh --output jury --team-output analista`.
Los topes se generan desde `config/plan.json`; no se copia ni modifica el estado
operativo de Jorge. Las propuestas de Duelos II y CHA están en
[analista.md](analista.md); el cambio A de días sigue pendiente de su revisión.

## Recibir el radar y preparar la siguiente decisión

`python3 -m market_harness refresh` guarda una foto pública con catálogo. Reutilizar
esa misma foto, sin red: `python3 -m jury.report --market-snapshot runs/market-harness/snapshot.json`.
Abrir `runs/jury/demo.html`: separa marcador/reloj y muestra liquidaciones propias
confirmadas, sin inventar beneficio o puntos de jueces. Para el bundle estático,
añadir `--output jury --team-output analista` y revisar antes de desplegar.

[Prioridades del jurado](jury-priorities.md) y [investigación para Santiago](market-research-santiago.md).
