# Decisiones

Entradas cortas y fechadas: qué decidimos, por qué, y qué haría cambiarlo. Las más recientes arriba.

## D-004 · vie 2 oct · Estudiar a los vendedores con el feed público
`/api/feed` muestra los regateos de todos los equipos con los vendedores (precios, ofertas finales, tratos). Estudiarlos no cuesta dinero ni ticks. `scout.py` lo automatiza.
**Revisar si** el feed deja de ser público o empieza a ocultar precios.

## D-003 · vie 2 oct · Vendedores como datos y regateo genérico
Habrá más vendedores con el tiempo. El regateo (`agent/haggle.py`) es el mismo para todos y lo propio de cada uno (precios y frases) va en `agent/dealers.py`.
**Revisar si** un vendedor necesita una lógica distinta (por ejemplo, uno que miente): entonces se crea una función específica para él.

## D-002 · vie 2 oct · El código decide las cifras
Seguimos las invariantes de [negotiation-design.md](negotiation-design.md): el código fija cada precio y cada aceptación, las ofertas son monótonas y todo se registra en un JSONL. Los mensajes por ahora son plantillas; un LLM solo redactaría el texto.

## D-001 · vie 2 oct · Repositorio privado, clave fuera del código
Compiten otros equipos, así que la estrategia no se publica. La clave va en `BAZAAR_KEY` y `.env`/`logs/` están en el `.gitignore`.
