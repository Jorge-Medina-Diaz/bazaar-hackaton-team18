# Rastro Intel: guion para diapositivas (t18)

Archivo pensado para que una persona o un Claude lo lea y monte diapositivas. Cada bloque es una diapositiva:
título, mensaje (una frase), cifra clave, imagen y notas para quien presenta. Las imágenes están en `img/`
y también por URL directa (el repo es público). Las cifras en estructurado están en `datos.json`.

> Nota para un artifact de Claude: los artifacts no cargan imágenes de otros dominios. Descarga las imágenes
> de las URL y súbelas como archivos o assets del propio artifact.

---

## 1. Rastro Intel
- **Mensaje:** Mientras nuestro agente negociaba, un segundo sistema miraba todo el mercado en directo, lo entendía y nos avisaba.
- **Cifras:** 2.º al cierre del sábado (31,26) · más de 30.000 eventos analizados · 0 de 12 trucos colados · +99 P en un arbitraje.
- **Imagen:** https://raw.githubusercontent.com/Jorge-Medina-Diaz/bazaar-hackaton-team18/main/docs/demo/rastro-intel/img/1-tablero.png
- **Notas:** Solo lectura sobre la API pública. Nada de esto actuaba en el juego.

## 2. Nuestra trayectoria
- **Mensaje:** La nota sube a saltos con cada trato bueno y cae sola cuando no negociamos.
- **Cifras:** mínimo 28,13 (sábado, sin tratos) · 2.º al cierre del sábado · máximo 33,44 (domingo).
- **Imagen:** https://raw.githubusercontent.com/Jorge-Medina-Diaz/bazaar-hackaton-team18/main/docs/demo/rastro-intel/img/0-trayectoria.png
- **Notas:** Un corte por minuto del leaderboard público durante todo el fin de semana.

## 3. Los Pícaros: el truco siempre es el mismo
- **Mensaje:** La oferta trae otra carta del mismo barrio con número menor; lo detectamos por la oferta, nunca por el texto.
- **Cifras:** 0 de 12 intentos colados a t18 · 1 colado en todo el mercado.
- **Imagen:** https://raw.githubusercontent.com/Jorge-Medina-Diaz/bazaar-hackaton-team18/main/docs/demo/rastro-intel/img/4-chats.png
- **Notas:** Ejemplos: SAL-10 en vez de SAL-11, LAT-06 en vez de LAT-09. En el chat se marca en rojo con un mini mono.

## 4. Huevos de pascua
- **Mensaje:** Los dealers esconden frases que desbloquean premios.
- **Cifras:** 3 de 3 insignias (Sharp ear, Trickster tricked, Castizo) + sobre gratis del Chato.
- **Contenido:** Banco «el oro de Moscú» → carta oculta · Pícaros «Lazarillo, Rinconete» → sin trucos ese día · Abuela «el chotis se baila en una baldosa» → Castizo · Chato «Plaza Mayor, con caña» → sobre gratis.
- **Notas:** Deducidos leyendo las respuestas de los dealers en el feed público.

## 5. Si no negocias, bajas solo
- **Mensaje:** La ronda en curso pesa más a medida que avanza el día; sin tratos la nota cae.
- **Cifras:** +1,92 por una sola compra a otro equipo · −0,85 en 10 minutos parados.
- **Imagen:** https://raw.githubusercontent.com/Jorge-Medina-Diaz/bazaar-hackaton-team18/main/docs/demo/rastro-intel/img/5-clasificacion.png

## 6. Sin venue, el 30 % está congelado
- **Mensaje:** La parte de mercado solo se mueve con un venue propio y los Market Test.
- **Cifras:** 5,91 → 8,33 con un solo Market Test tras abrir venue.

## 7. Arbitraje de épicas
- **Mensaje:** Comprar épicas a Los Pícaros y venderlas a equipos o a Pilar da beneficio; al Banco, pérdida.
- **Cifras:** compra 128–167 P · venta 195–238 P · Banco 113–120 P · nuestra SAL-11: 139 → 238.

## 8. Agente contra el mercado
- **Mensaje:** Cada trato del agente frente a la mediana del resto de equipos (mismo dealer, rareza y barrio).
- **Cifras:** fuerte comprando épicas a Los Pícaros (~7 P por debajo); flojo vendiendo infrecuentes de La Latina a Pilar.
- **Imagen:** https://raw.githubusercontent.com/Jorge-Medina-Diaz/bazaar-hackaton-team18/main/docs/demo/rastro-intel/img/3-batalla.png

## 9. Radio Rastro
- **Mensaje:** Una locutora elige lo relevante y lo cuenta en boletines con voz.
- **Ejemplo:** «Nos llevamos la copia 1 de Chamberí 11, Andén 0, comprada a Los Pícaros por 145 primas.»
- **Imagen:** https://raw.githubusercontent.com/Jorge-Medina-Diaz/bazaar-hackaton-team18/main/docs/demo/rastro-intel/img/2-radio.png

## 10. Inspector y directo de la final
- **Mensaje:** Cada acción del agente al segundo con el flujo en tiempo real, y la Gran Final en directo.
- **Cifras:** 306 duelos en la Gran Final, unos dos tercios con acuerdo.
- **Imágenes:** https://raw.githubusercontent.com/Jorge-Medina-Diaz/bazaar-hackaton-team18/main/docs/demo/rastro-intel/img/6-inspector.png · https://raw.githubusercontent.com/Jorge-Medina-Diaz/bazaar-hackaton-team18/main/docs/demo/rastro-intel/img/7-final.png

## 11. Estudio de los 18 equipos
- **Mensaje:** Comparación justa con la misma ventana de datos para todos.
- **Imagen:** https://raw.githubusercontent.com/Jorge-Medina-Diaz/bazaar-hackaton-team18/main/docs/demo/rastro-intel/img/8-estudio.png

## 12. Qué mejoraríamos
- Conectar el conocimiento por dealer al agente (se generaba en vivo, pero el agente no lo leía).
- Venue abierto todo el día (el mercado es el 30 %).
- Tratos buenos a ritmo constante, porque la nota cae sola.
- Medir el efecto de las denuncias con los datos privados del equipo.
