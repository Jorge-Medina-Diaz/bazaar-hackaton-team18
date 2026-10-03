# Puntuación: certezas, mediciones e hipótesis

Fuentes: [RULES.md](../RULES.md#scoring), [knowledge](knowledge.md),
[modelo Affinity](../agent/affinity.py). Las cifras de reconstrucción que aporta
Jorge se conservan como mediciones documentadas; aquí no se han repetido contra
su diario real.

| Tema | Fórmula / criterio | Evidencia y límite |
|---|---|---|
| Total | Negociación 30 + Mercado 30 + Jurado 40 | **Oficial**. El marcador público durante el juego no es una nota final del jurado. |
| Rondas | Pesos 0,5 · 1 · 1 → 20 % · 40 % · 40 % cuando terminan | **Oficial**. La ronda activa pesa por la fracción jugada. Sábado y domingo juntos pesan cuatro veces el viernes. |
| Copia | catálogo × multiplicador de barrio × factor de copia | **Medido/documentado**: común 10, infrecuente 25, rara 70, épica 180, legendaria 450; factores 1 / 0,25 / 0,1. El valor marginal depende también de páginas y sobres pendientes. |
| Página | 0,25 × suma de primeras copias de sus diez cartas | **Medido/documentado**. La carta que cierra página añade el bonus entero. Master 0,1 está publicado, no observado. |
| Equipo compra | V marginal recibido − precio − comisión si acepta | **Medido**, P-03. Para vender: precio − V marginal entregado − comisión si acepta; intercambio: V recibido − V entregado − comisión. |
| Rastro | ceil(0,05 × precio + número de cartas) | **Medido/documentado**, 44/44 comunicado por Jorge. Paga quien acepta. Otros mercados usan su propia comisión. |
| Dealer | comprar min(0,V−precio); vender min(0,precio−V) | **Medido**, P-04, 11/12 documentado. Las ganancias no elevan esta parte; la escalera es otra componente. |
| +50 | observado SAL-10; Jorge comunica RET-02 | **Observación**. No está identificada la causa exacta; el segundo caso requiere su diario. No afirmar una ley universal. |
| Escalera | tres mejores tratos por nivel; hueco vacío 0; altos pesan más | **Oficial**. Pesos exactos y transformación desconocidos. ≈0,022 por hueco completo del nivel 1 es **inferencia**. |
| Duelos I | distancia al límite × (1−decay)^rondas, con signo favorable dentro del límite | **Medido/documentado**, 148/148 comunicado; fuera de límite resta, sin trato 0. Rondas=min(mensajes propios,rival); aceptar no suma ronda. |
| Duelos II | precio + días; interpretar your_days_weight y days_meaning | **Pendiente**. No extrapolar solo la fórmula de precio ni fijar days_sign sin leer el primer duelo. |
| Decay | I: 0,06; II: 0,08; III y Final: 0,10 | **Calendario/documentado por Jorge**. Aceptar no añade ronda; callar no reduce el premio por sí solo. |
| Negociación normalizada | ≈12,5×min(1,escalera/ref)+17,5×min(1,neg/ref) | **Inferido**, confianza media. ref podría ser media top3 o máximo. Encaje de duelos desconocido. |
| Market Test | ganancias realizadas / posibles en libro sintético común | **Oficial**. Igualar puesto gratuito = mitad de puntos; puntos completos relativos a media top3. Curva intermedia desconocida. |
| Mercado | mejor mercado abierto por sesión; luego media de sesiones | **Oficial**. mm_points mide valor entre otros equipos, mezcla exacta desconocida. Coste mercado propio 20 P + 250 P fianza. |
| Jurado | ideas y calidad del trabajo | **Oficial**. No conocemos rúbrica detallada, duración ni formulario de entrega. |

No puntúan número de tratos, comisiones cobradas, suerte de sobres, regalos,
easter eggs ni concesiones. Penalizaciones restan un porcentaje de la ronda.

## Qué aporta Affinity y qué no permite concluir

El archivo en main es **affinity.py**, no infinity.py. Su módulo puro considera
las 720 permutaciones de seis multiplicadores privados. Las compras, ventas,
pujas y ofertas son señales con pesos distintos; los dealers pesan menos. El
modelo mantiene probabilidades, valores esperados y conjuntos creíbles del 80 %.

El demo reutiliza ese modelo sin clave, con la ventana pública que devuelve el
feed. No añade valores privados conocidos ni convierte cada variación del puesto
en beneficio. Tampoco usa score_jumps con una sola instantánea. La normalización
del marcador, duplicados, páginas, sobres y comisiones impiden deducir ganancias
exactas de todos los equipos desde esa vista.

X-15 documenta validación simulada y una prueba ciega parcial; las probabilidades
dependen de supuestos sobre intención, duplicados y cierre de páginas. No son una
garantía sobre el siguiente trato. Ejemplo de decisión para el analista: buscar
destinatarios probables de un duplicado y presentar la incertidumbre al operador,
que mantiene los límites económicos propios.
