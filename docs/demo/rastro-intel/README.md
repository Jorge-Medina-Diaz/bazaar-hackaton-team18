# Rastro Intel (t18)

Material de apoyo para la demo: lo que aprendimos mirando el mercado del Bazaar en directo y las herramientas que lo hicieron posible.

- **Para diapositivas:** `PARA_DIAPOSITIVAS.md` (guion diapositiva a diapositiva) y `datos.json` (cifras).
- **Página:** `index.html` (se abre en el navegador; las capturas están en `img/`). Versión publicada: https://claude.ai/artifact/Xnhk2r11zVdee8ggcG3QGQ (privada, compartir desde su menú).
- **Secciones enlazables:** `#trayectoria`, `#hallazgos`, `#herramientas`, `#final`, `#mejoras`.

## Grandes descubrimientos
1. **Los Pícaros** siempre hacen el mismo truco: la oferta trae otra carta del mismo barrio con número menor. Al agente de t18 no le colaron ninguna de 12.
2. **Huevos de pascua** por dealer: «el oro de Moscú» (Banco), «Lazarillo, Rinconete» (Pícaros), el chotis (Abuela), «Plaza Mayor, con caña» (Chato).
3. **La nota cae sola** si no negocias: la ronda en curso pesa más a medida que avanza el día. Un trato bueno la levanta (+1,92).
4. **Sin venue, el mercado (30 %) no se mueve.** Con venue y un Market Test: 5,91 → 8,33.
5. **Arbitraje de épicas:** comprar a Los Pícaros (128–167 P) y vender a equipos o a Pilar (195–238 P); nunca al Banco.
6. **Agente frente al mercado:** fuerte comprando épicas a Los Pícaros (~7 P por debajo), flojo vendiendo infrecuentes de La Latina a Pilar.
7. **Denuncias:** ningún equipo tiene ajustes; preparamos 12 con prueba estructural, sin efecto visible en la clasificación pública.

## Herramientas (`herramientas/`)
Solo lectura, sobre la API pública del Bazaar. Escritas para correr en un Mac (rutas locales de Rubén; ajustar `HERE`/rutas).

| Archivo | Qué hace |
|---|---|
| `pilar_watch.py` | Lee el feed público, archiva todo y regenera el conocimiento por dealer |
| `tablero.py` | Tablero local (http://127.0.0.1:8030): alertas en lenguaje claro, Radio Rastro, clasificación, chats |
| `locutor.py` | La locutora de Radio Rastro: elige lo relevante y lo convierte en boletines con voz (`say` + `afconvert`) |
| `envivo.py` | Negociaciones del agente como chats, con avatares y trucos marcados |
| `batalla.py` | Campo de batalla: cada trato del agente contra la mediana del mercado (mismo dealer, rareza y barrio) |
| `inspector.py` + `inspector.html` | Inspector en tiempo real con el flujo SSE público (`/api/events/stream?scope=public`) |
| `duelos.html` | Directo de la Gran Final (lo alimenta `inspector.py`) |
| `estudio.py` | Estudio justo de los 18 equipos (misma ventana de datos para todos) |
