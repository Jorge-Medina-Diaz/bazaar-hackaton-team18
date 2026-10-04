# Especificación del arnés — Team 18 (t18) · v2 (tras el equipo rojo)

> **English summary:** this is the build contract of the harness, written in Spanish during the event. It covers architecture decisions (§0), the tick loop (§1), module signatures (§2), invariants INV-01..23 with the test that proves each (§3), guard formulas (§4), modes and CLI (§5), the journal (§6), calibration (§7), failure handling (§8), the fake server (§9), the test plan (§10) and module ownership (§11). The English overview is [architecture.md](architecture.md). For the release, the offline lab and the extra panels it mentions (`website/`, `panel.py`, `live_monitor.py`, `observe_performance.py`, `laboratorio.py`, …) were removed, and `archive/` moved to `docs/history/legacy-code/`. Sections 12–14 are the cleanup table, the Saturday runbook and the red-team decisions. §15 lists how the shipped code differs from the frozen contract, and it wins on any conflict. A few test criteria in §3 and §10 were not staged as written (see the note under §10).

Sábado 3 oct 2026, ~03:30. La firma el arquitecto jefe. El plan de juego está en `docs/strategy.md`; los hechos, en `docs/knowledge.md`. Los cambios frente a la v1 y su motivo están en §14.
Este documento es el contrato de construcción: cada fichero tiene un único módulo dueño, las firmas de M0 son fijas desde las 03:30 y cada invariante dice cómo se impone y qué test lo prueba.

Reglas de la casa:
- Solo la biblioteca estándar de Python ≥ 3.9 (`from __future__ import annotations` en cada módulo nuevo), en Windows y macOS.
- `bazaar_sdk.py` no se edita.
- `website/` y los paneles siguen funcionando (regla del evento; en la versión publicada solo queda el panel de solo lectura `api/index.py` + `agent/dashboard.py` + `run_dashboard.py`).
- Ningún LLM decide en tiempo de ejecución.
- Todo camino de fichero sale de un único `Paths(root)`; los tests siempre usan una carpeta temporal.

---

## 0. Decisiones de arquitectura

| Tema | Decisión | Motivo |
|---|---|---|
| Punto único de escritura | **Barrera física en tres capas.** (1) `GuardedTransport` reimplementa `_call` (sin llamar al `_call` del SDK) y solo envía un método distinto de GET con un permiso de un solo uso cuyo `(método, ruta exacta, sha256 del cuerpo)` coincide con `==`. (2) Un `sys.addaudithook` instalado al importar `agent.transport` rechaza cualquier `urllib.Request` no-GET sin ese permiso. (3) Test AST: `bazaar_sdk`, `urllib`, `http.client`, `socket`, `Bazaar(`, `Broker(`, `._call(`, `.send(` y `write_permit` no aparecen en `agent/` ni en `bazaar.py` fuera de `agent/transport.py` y `agent/gate.py`. | El agente **no puede** salirse de la banda aunque haya un bug. El equipo rojo mostró los atajos (`broker()`, `_Http._call`, `Bazaar(...)` nuevo, urllib directo). |
| Cliente HTTP | Nuestro `_call`: abridor de urllib **sin redirecciones**, `timeout=10`, sin reintentos en escrituras; GET con ≤ 2 reintentos solo por `network`/`rate_limited`. `wait_on_tick=False`, `retries=0`. | `bazaar_sdk.py:62-86` `[medido]`: reenvía POST tras `wait_for_tick` y `rate_limited`; un 302 sobre POST se convierte en GET con "ok"; un 2xx truncado da `bad_response` y `IncompleteRead` escapa. |
| Clasificación de respuestas | **Fallo cerrado.** Solo hay `ok` (2xx con cuerpo JSON objeto), `deferred` (429 `wait_for_tick`/`rate_limited`) y `refused` (4xx con cuerpo `{error, message}` del juego). Todo lo demás (3xx, 2xx no-JSON o truncado, 4xx sin cuerpo del juego, 5xx, red, timeout, cualquier excepción) es **`unknown`** y congela su dominio. | Equipo rojo, bloqueante S-B4. |
| Predicción | La táctica la propone; el Gate la recalcula con los **mismos** `server_values` del World y rechaza si difiere > 0,01 (`trip`). | Una sola valoración, sin falsos `trip`. |
| Libro de compromisos | `Book` (tipo en M0) se construye al empezar el tick y **se actualiza tras cada intent** enviado, `would` o `unknown` con `guards.apply`. | Bloqueante S-B2: dos intents del mismo tick no pueden ver el mismo libro. |
| Escritor único | Un solo proceso escritor: el runner. Candado `state/writer.lock` de ruta fija para todo `run` (dry incluido) y todo `do` de un disparo. El CLI nunca escribe el diario: deja órdenes en `state/inbox/`. | Dos procesos rompían la cadena de hash y el candado dependía del nombre que pasara cada uno (5 ficheros distintos en %TEMP%, medido). |
| Diario | Un solo fichero para todo el evento, `logs/run/journal.jsonl`, WAL con `fsync` y cadena de hash; recuperación de cola rota. | Con un fichero por día, el domingo olvidaba el sábado (bloqueante B-B2). |
| Texto ajeno | Nunca entra en el World. El sensor lo escribe en `logs/run/untrusted.jsonl` (base64) y lo descarta. | El World llega a todas las tácticas. |
| Etapas | El arnés se construye por etapas según cuándo se usa cada pieza (§11). Cada táctica se arma solo si su etapa del `selftest` está en verde. `bazaar.py do` permite hacer a mano cualquier jugada por el Gate. | Una noche no da para todo; las 09:00 solo necesitan higiene. |
| Broker y venue | Fuera de las 09:00. `open_venue` no está en `KINDS`; llega con L4 y su propia guarda. | strategy J11. |

---

## 1. Arquitectura

```
 python3 bazaar.py run [--live] [--arm a,b]       (un proceso, un hilo, máquina A; candado state/writer.lock)
 ┌────────────────────────────────────────────────────────────────────────────────────────────────┐
 │ Inbox (state/inbox/*.json, órdenes del CLI) → diario → armed/pauses/do/flatten                   │
 │ Sensor (agent/world.py): GET priorizados, limitador 3,5 req/s con 2 fichas reservadas            │
 │   → World inmutable (campos de lista blanca, sin texto) + Secrets (solo memoria)                 │
 │   → texto ajeno a logs/run/untrusted.jsonl                                                       │
 │ Gate.begin_tick: Book.build + línea base + escritor ajeno · Gate.reconcile                       │
 │ Calibrator.on_tick: predicho vs medido (excluye cambios de ronda) → pausas, STOP                 │
 │ pages.plan → Need[] (+ carta de cierre congelada)                                                │
 │ Tácticas puras (cada una en su try): hygiene, dealers, rastro, closer, duels, manual → Intent[]  │
 │ runner.choose → orden y presupuestos; duel_accept a la ventana tardía del tick                   │
 │ Gate.execute: STOP → idempotencia → fuentes → relectura fresca → guards.check → predicción      │
 │   → (dry/sombra: would) → plazo del tick → WAL intent+fsync → permiso exacto → send → WAL result │
 │   → Book = apply(Book, intent, outcome)                                                          │
 │ GuardedTransport: permiso (método, ruta, sha256 cuerpo) de un uso ∧ modo live ∧ sin STOP         │
 │ Audit hook: cualquier urllib no-GET sin permiso → excepción                                      │
 └────────────────────────────────────────────────────────────────────────────────────────────────┘
 Paneles: solo GET; agent.client.client() devuelve el transporte en modo "read" (y los scripts antiguos que lo usan quedan sin escritura).
 Offline: sim/ (FakeGame con oráculo propio, LoopbackTransport en proceso, HTTP real en 127.0.0.1), reloj virtual inyectable.
```

**Orden de cada tick** (cada paso en su `try`):
1. Leer el inbox y aplicar las órdenes (cada una queda en el diario).
2. STOP (`stop_active`) → no se escribe nada; con `flatten` pendiente, ver §5.
3. Esperar tick nuevo. Con `paused` o puertas cerradas: sondeo sin clave cada `max(5 s, next_tick_in)` (corrige K-11); solo pasan `cancel` y `close_thread`.
4. **Vía rápida** en el arranque y en el primer tick con puertas abiertas: `clock` + `me/offers` → `hygiene.startup` → Gate. Antes de la lectura completa.
5. `world, secrets = sensor.snapshot(prev)` (orden: clock, me, me/offers, duels si hay sesión, me/threads, threads/{id} abiertos, rastro, feed, value?card ≤ 3 por tick).
6. `gate.begin_tick(world)` (Book, línea base en el primer arranque, escritor ajeno) y `gate.reconcile(world)`.
7. `calibrator.on_tick(prev, world)` → pausas o razón de STOP.
8. `needs, frozen = pages.plan(world, valuer, plan_cfg, frozen)`.
9. `intents = hygiene + dealers + rastro(+closer) + duels + manual(inbox)`, cada una en su `try`; 3 excepciones en 20 ticks → pausa.
10. `for it in choose(intents, world, cfg): gate.execute(it, world)`; los `duel_accept` se ejecutan en la ventana tardía: desde el 50 % del tick hasta `world.tick_deadline`.
11. Diario: fila `tick`.

**Fallo cerrado:**
- `GateViolation`, `StopActive`, `JournalError` o una aserción interna → `write_stop()` y salida con código 2.
- Un error al interpretar una relectura fresca dentro del Gate → `refused:G10.shape` y dominio bloqueado ese tick (no es STOP).
- Una excepción en una táctica → solo esa táctica en ese tick.

---

## 2. Contratos

### 2.1 `agent/contracts.py` y `agent/redact.py` (M0, congelado a las 03:30)
```python
from __future__ import annotations
PROD_URL = "https://bazaar.causaprima.ai"
TEAM = "t18"

@dataclass(frozen=True)
class Paths:
    root: Path                       # por defecto Path(__file__).resolve().parents[1]
    @classmethod
    def at(cls, root: str | Path | None = None) -> "Paths"
    # propiedades: journal = root/logs/run/journal.jsonl; untrusted = root/logs/run/untrusted.jsonl;
    # snaps = root/logs/run/snap; state = root/state; inbox = state/inbox; lock = state/writer.lock;
    # baseline = state/baseline.json; armed = state/armed.json; pauses = state/pauses.json;
    # frozen = state/frozen.json; selftest = state/selftest.json; stop_names = ("STOP","stop") (+ cualquier extensión)

KINDS = ("accept", "list_offer", "cancel", "open_thread", "say", "close_thread",
         "open_pack", "duel_say", "duel_accept")
TACTICS = ("hygiene", "dealers", "rastro", "closer", "duels", "manual")
BUY_TACTICS = frozenset({"dealers", "rastro", "closer"})
TALK_KINDS = frozenset({"open_thread", "say", "duel_say", "duel_accept"})   # + accept con source == "dealer"

@dataclass(frozen=True)
class Prediction:            # efecto SI esta escritura acaba en liquidación
    neg_lo: float            # Δneg con el tope de 50
    neg_hi: float            # Δneg sin tope
    ladder: str              # "0" | ">=0"
    cash: int                # Δcaja al liquidar (con signo)
    duel: float | None = None
    model: str = ""          # "P-03" | "P-04" | "P-08" | "U-01" | "none"
# Semántica por kind: accept/list_offer → predict_team (list_offer con we_accept=False);
# say y accept de dealer → predict_dealer(dv, p); duel_say → predict_duel con rondas+1;
# duel_accept → predict_duel con las rondas actuales; cancel/close_thread/open_thread/open_pack → predict_none.

@dataclass(frozen=True, eq=False)       # se compara e indexa por intent_id, nunca por valor
class Intent:
    kind: str; tactic: str
    args: Mapping[str, Any]             # MappingProxyType, esquema ARGS[kind]
    reason: str; expected_effect: str
    prediction: Prediction
    priority: int = 0
    experiment: str | None = None

NONE = type(None)
ARGS: Mapping[str, Mapping[str, type | tuple]] = {
  "accept":      {"offer_id": int, "source": str, "ref": str, "side": str, "price": int,
                  "thread_id": (int, NONE), "give_asset": (int, NONE), "fingerprint": str,
                  "resupply": bool},
  "list_offer":  {"side": str, "ref": str, "asset_id": (int, NONE), "price": int,
                  "expires_ticks": int, "closer": bool},
  "cancel":      {"offer_id": int, "ref": (str, NONE)},
  "open_thread": {"dealer": str, "side": str, "ref": str, "asset_ids": tuple, "limit": int},
  "say":         {"thread_id": int, "ref": str, "price": int, "template": str, "variant": int},
  "close_thread":{"thread_id": int, "ref": (str, NONE)},
  "open_pack":   {"asset_id": int},
  "duel_say":    {"duel_id": int, "price": int, "days": (int, NONE), "template": str, "variant": int},
  "duel_accept": {"duel_id": int, "fingerprint": str},
}
# source ∈ {"team","dealer"}; side ∈ {"buy","sell"} (list_offer: {"sell","bid"}); bool NO cuenta como int
# (salvo en los campos declarados bool). El venue siempre es "rastro" y lo pone el Gate.

def make_intent(kind, tactic, args, reason, expected_effect, prediction, priority=0, experiment=None) -> Intent
    # valida claves exactas y tipos exactos; ValueError si no cuadra
def intent_id(tick: int, it: Intent) -> str
    # sha1(f"{tick}|{it.tactic}|{it.kind}|{json.dumps(dict(it.args), sort_keys=True)}")[:16]
def domains_of(it: Intent) -> frozenset[str]
    # {"offer:<id>", "thread:<id>", "dealer:<id>", "duel:<id>", "asset:<id>", "ref:<REF>"} según args

LIMIT_KEYS = {"accepts": "accepts_per_team_per_tick", "messages": "messages_per_side_per_tick",
              "threads": "max_open_threads_per_team", "open_offers": "max_open_offers_per_team",
              "listings": "offers_per_team_per_tick"}                          # [medido] clock.json
@dataclass(frozen=True)
class Limits:
    accepts: int; messages: int; threads: int; open_offers: int; listings: int
    @staticmethod
    def from_clock(clock: Mapping, prev: Limits | None) -> Limits
        # lee clock["limits"][LIMIT_KEYS[k]]; si falta o no es int: min(prev, FRIDAY); FRIDAY = Limits(1,1,6,30,12)

@dataclass(frozen=True)
class World:
    tick: int; t_hours: float; round: int | None; tick_seconds: float
    tick_deadline: float              # monotonic de la lectura de clock + next_tick_in − TICK_MARGIN_S
    clock: Mapping; limits: Limits; reading: str                 # "N" | "M" | "C" | "P" | "?"
    me: Mapping                       # campos de lista blanca; sin claves ni texto
    my_offers: tuple[Mapping, ...]    # maker == "t18" (incluye "queued")
    offers_to_us: tuple[Mapping, ...] # to == "t18", maker != "t18"
    board: tuple[Mapping, ...]        # El Rastro, abiertas, campos estructurados
    own_pseudonym: str | None         # maker del tablón de cualquier oferta cuyo id está en my_offers
    threads: Mapping[int, Mapping]    # hilos con dealer abiertos por nosotros (team == t18); mensajes sin text
    foreign_threads: tuple[int, ...]  # hilos abiertos por otros con nosotros
    duels: tuple[Mapping, ...]        # duelos live; mensajes sin text
    catalog: Mapping; schedule: Mapping
    released_sets: frozenset[str]
    feed_new: tuple[Mapping, ...]     # sin texto
    server_values: Mapping[str, float]   # value?card en caché por versión de inventario
    down: frozenset[str]              # fuentes caídas o con forma inválida: "clock","me","me/offers",
                                      # "me/threads","threads","board","duels","feed","values","catalog","schedule"

@dataclass(frozen=True)
class Secrets:                        # nunca en World, diario, snapshots ni consola
    starter_broker_key: str | None = None

@dataclass(frozen=True)
class Need:
    set: str; ref: str; source: str   # "abuela" | "chato" | "team"
    max_price: int; closer: bool

@dataclass(frozen=True)
class Book:                           # lo construye guards.build_book; lo actualiza guards.apply
    cash: int; cash_free: int
    held: Mapping[str, int]; listed: Mapping[str, int]
    pending_out: Mapping[str, int]; pending_in: Mapping[str, int]
    projected: Mapping[str, int]      # held + pending_in + hilos de compra con precio en pie + pujas propias
    keep: Mapping[str, int]
    listed_assets: frozenset[int]; own_offer_ids: frozenset[int]
    own_bids: Mapping[str, int]       # ref → offer_id
    bid_price: Mapping[int, int]; bid_band: Mapping[int, float]   # banda de G19 por oferta (línea base o 2/20)
    paths: Mapping[str, int]
    thread_limit: Mapping[int, int]; thread_prices: Mapping[int, tuple[int, ...]]
    thread_ref: Mapping[int, str]; thread_by_dealer: Mapping[str, int]
    dealer_block: Mapping[str, int]   # dealer → until_tick (cooloff, persona_quota)
    dealer_deals_hour: Mapping[str, int]
    packs: tuple[int, ...]
    needs: Mapping[str, Need]; frozen_closer: Mapping[str, str]   # set → ref
    protect_sets: frozenset[str]
    delivery_risk: bool               # INV-23
    recent_rastro: Mapping[str, tuple[str, int]]   # ref → (lado, tick) de nuestras liquidaciones en El Rastro
    unknown_domains: frozenset[str]; valuation_ok: bool

@dataclass(frozen=True)
class Verdict:
    ok: bool; code: str; detail: str = ""
@dataclass(frozen=True)
class Outcome:
    intent_id: str
    status: str                       # "sent" | "would" | "refused" | "deferred" | "unknown"
    code: str | None = None
    response: Mapping | None = None   # redactada, ≤ 2 KB

class PlanCfg(TypedDict):
    page_sets: list[str]              # ["RET"] el sábado; ["RET","CHA"] el domingo
    protect_sets: list[str]           # ["SAL","RET","CHA","LAT"]; LAT sale al darse por muerta (t205)
    startup_cancels: list[int]        # [2463, 1652]
    baseline_bands: dict[str, float]  # {"2503": 0.0, "2504": 0.0}
    dealer_max: dict[str, int]        # ref → tope
    profiles: dict[str, dict]         # ref/rareza → {dealer, anchor, step, limit, fallback_after}
    closer: dict                      # {"accept_min": 20, "default_minus": 50, "compete_minus": 20, "endgame_hours": {...}}
    resupply_min: float               # 15
    dup_min_price: dict[str, int]     # {"RET": 30, "CHA": 30}
    days_sign: int | None
    day_end_hours: dict[str, float]   # cierre de hilos con dealer (22:55 sábado)
    grant_lookahead_ticks: int        # 3

# agent/redact.py
def redact(obj: Any, secrets: Iterable[str] = ()) -> Any
    # quita claves que contengan key|token|secret|password (sin mayúsculas); sustituye por "<redacted>"
    # las cadenas que encajen con (tk|bk)[-_][A-Za-z0-9-]{6,} y las que sean IGUALES a un valor de
    # `secrets` o de os.environ["BAZAAR_KEY"]
```
También son de M0: `tests/__init__.py` (al importarse: `BAZAAR_TEST=1`, `BAZAAR_NO_DOTENV=1`, borra `BAZAAR_KEY` y `BAZAAR_URL`) y `tests/fixtures/harvest/**` (copia sin claves de `logs/harvest` y `logs/probe`).

### 2.2 `agent/transport.py` y `agent/client.py` (M1)
```python
WRITE_ROUTES: Mapping[str, tuple[str, str]] = {      # re.fullmatch, nunca re.match
  "accept": ("POST", r"/api/offers/\d+/accept"),   "list_offer": ("POST", r"/api/offers"),
  "cancel": ("DELETE", r"/api/offers/\d+"),        "open_thread": ("POST", r"/api/threads"),
  "say": ("POST", r"/api/threads/\d+/messages"),   "close_thread": ("POST", r"/api/threads/\d+/close"),
  "open_pack": ("POST", r"/api/packs/\d+/open"),   "duel_say": ("POST", r"/api/duels/\d+/messages"),
  "duel_accept": ("POST", r"/api/duels/\d+/accept")}
GET_ALLOWLIST = r"/api/(clock|schedule|catalog|me|me/value|me/offers|me/threads|threads/\d+|venues|venues/rastro/offers|duels|feed|dealers|levels|cards/\d+|leaderboard)"
class GateViolation(Exception): ...
class StopActive(Exception): ...
@dataclass(frozen=True)
class Response:
    status: str                  # "ok" | "deferred" | "refused" | "unknown"
    http: int; code: str | None; body: Mapping | None
class RateLimiter:
    def __init__(self, rate: float = 2.5, burst: int = 5, reserve: int = 1, clock=None)  # clock: now()/sleep()
    def take(self, priority: bool = False) -> None   # sin priority deja `reserve` fichas para relecturas de aceptación
    def slow_down(self, rate: float, seconds: float) -> None
def stop_active(paths: Paths) -> str | None          # motivo si existe en root un fichero STOP, STOP.*, stop o stop.*
@contextmanager
def write_permit(intent_id: str, method: str, path: str, body: Mapping | None): ...
    # ContextVar; de un solo uso; SOLO agent/gate.py lo usa (test AST)
def install_audit_hook() -> None    # idempotente; se llama al importar el módulo
class GuardedTransport(Bazaar):
    def __init__(self, url: str, key: str, *, mode: str = "read", paths: Paths,
                 limiter: RateLimiter | None = None, get_retries: int = 2, timeout: float = 10.0,
                 http: Callable | None = None)   # http(method, url, data, headers, timeout) -> (status, bytes); None = urllib sin redirecciones
        # mode ∈ {"read","dry","live"} es una propiedad de solo lectura.
        # "live" exige: url == PROD_URL y BAZAAR_TEST sin poner; o BAZAAR_TEST=1, url en 127.0.0.1 y key ∈ {"tk-test","fake-key"}.
        # Con BAZAAR_TEST=1 rechaza cualquier host que no sea 127.0.0.1. Una clave "tk-…" real contra 127.0.0.1 → GateViolation.
    def _call(self, method, path, body=None, query=None):
        # GET: re.fullmatch(GET_ALLOWLIST, path) o GateViolation; limiter.take(); reintentos ≤ get_retries por network/rate_limited.
        # Otro método: delega en send(); fuera de gate.py nadie tiene permiso → GateViolation.
    def send(self, method: str, path: str, body: Mapping | None) -> Response
        # permiso activo y sin usar ∧ (method, path, sha256(json canónico del cuerpo)) == permiso ∧ fullmatch de WRITE_ROUTES
        # ∧ mode == "live" ∧ stop_active() is None (StopActive) ∧ limiter.take(priority=True) → UN envío.
        # Clasificación de fallo cerrado (§0). Toda excepción dentro del envío → Response("unknown").
    def broker(self, broker_key: str): raise GateViolation("broker desactivado")
def public_get(base_url: str, path: str, limiter: RateLimiter, query: dict | None = None) -> dict   # sin clave, ≤ 1 req/s
# agent/client.py
def client(mode: str = "read") -> GuardedTransport    # .env solo si BAZAAR_NO_DOTENV no está puesto
```
`agent/dashboard.py`: `me = redact(me)` antes de servir (K-13). `api/index.py`: si `DASHBOARD_PASSWORD` está vacío, 401 (fallo cerrado) y usa `client("read")`.

### 2.3 `agent/journal.py` (M2)
```python
LOG_DIR = os.environ.get("BAZAAR_LOGS", "logs")      # se mantiene (dashboard)
def log(stream: str, **row) -> None                   # se mantiene
class JournalError(Exception): ...
class Journal:
    FSYNC = frozenset({"intent","result","unknown","reconciled","accepted_unsettled","stop","pause",
                       "resume","arm","param","baseline","round_reset","cmd"})
    def __init__(self, path: Path, *, mode: str, writer: bool = True)
        # writer=True: exige el candado ya tomado; recupera la cola: una última línea rota se mueve a
        # journal.corrupt con una fila "truncated" (prev = hash de la última línea válida); el intent que
        # pudiera ser queda como pendiente. writer=False: solo lectura (status, report).
        # mode ∈ {"live","dry","test"}; en un diario con filas "test", mode "live" → JournalError.
    def write(self, kind: str, **fields) -> int
        # {seq, ts, tick?, day, mode, kind, prev: sha256(línea anterior), **redact(fields)}; fsync si kind ∈ FSYNC
    def rows(self, kinds: set[str] | None = None) -> Iterator[dict]
    def result_for(self, intent_id: str) -> dict | None
    def pending(self) -> list[dict]       # intent sin result ni reconciled + accepted_unsettled sin resolver
    def unknown_domains(self) -> set[str]
    def own_objects(self, baseline: Mapping) -> dict[str, set]
        # {"offers": ids, "dealer_threads": ids, "thread_msgs": {msg_id},
        #  "duel_msgs": {(did, tick, price)}, "accepts": {offer_id}} ∪ línea base
    def verify_chain(self) -> bool
```

### 2.4 `agent/valuation.py` (M3)
```python
class UnknownPack(Exception): ...
class Valuer:                              # sin E/S de ficheros
    def __init__(self, catalog: Mapping, affinity: Mapping[str, float], released_sets: frozenset[str])
    @staticmethod
    def holdings(me: Mapping) -> tuple[Counter, tuple[str, ...]]
    def copy_value(self, ref: str, k: int, *, side: str) -> float   # [1, .25, .1]; 4.ª copia: 0 al comprar, MARG[-1] al vender
    def page_card(self, ref: str) -> bool
    def collection_value(self, counts, packs=(), minted=None) -> float   # V-01 + V-02
    def delta_add(self, counts, ref, packs=(), minted=None) -> float
    def delta_remove(self, counts, ref, packs=(), minted=None) -> float
    def pack_ev(self, pack_type: str, counts, minted=None) -> float      # UnknownPack si el tipo no está en el catálogo
    def closes_page(self, counts: Mapping[str, int], ref: str) -> bool  # se llama con Book.projected
    def self_check(self, me, server_values=None, tol=0.11) -> tuple[bool, float, list]
def fee(price: int, cards: int = 1, fee_bps: int = 500, per_card: int = 1) -> int
def predict_team(dv: float, price: int, side: str, we_accept: bool, cap: float = 50.0) -> Prediction
def predict_dealer(dv: float, price: int, side: str) -> Prediction
def predict_duel(limit: int, price: int, decay: float, rounds: int, side: str) -> Prediction
def predict_none(model: str = "none") -> Prediction
def verdict(pred: Prediction, measured_neg: float, ladder_delta: float) -> str   # pass|soft_fail|hard_fail|surprise_up
```
Origen: se reescribe desde `logs/analysis/scoring/verify/vlib.py` (que tiene la ruta `C:/Users/jorge/...` y `RELEASED` fijos, medido). `released_sets` sale de `catalog.sets[].released` en cada tick.

### 2.5 `agent/guards.py` (M4a) y `agent/talk.py` (M4b)
```python
# agent/guards.py
@dataclass(frozen=True)
class Cfg:
    MIN_GAIN_TEAM: float = 3.0;  MIN_GAIN_MAKER: float = 2.0;  DEALER_MARGIN: float = 1.0
    VAL_TOL: float = 0.11;       RESERVE: int = 10;            NEG_CAP: float = 50.0
    CLOSER_ACCEPT_MIN: float = 20.0;  RESUPPLY_MIN: float = 15.0
    LISTINGS_PER_TICK: int = 6;  OPEN_OFFERS_MARGIN: int = 4;  THREADS_MARGIN: int = 1
    DUEL_ACCEPT_SHARED: bool = True;  TICK_MARGIN_S: float = 2.0
    ALLOW_DEALER_CLOSE: frozenset = frozenset({"LAT"})
    MAX_PRICE_X_BOOK: float = 4.0;   ROUND_TRIP_TICKS: int = 60
    EXPIRY_FACTOR: float | None = None
@dataclass
class Counters:
    tick: int; accepts: int = 0; listings: int = 0; threads_opened: int = 0; offers_opened: int = 0
    msgs: set = field(default_factory=set)
SOURCES: Mapping[str, frozenset[str]]       # tabla de §4 (dependencia de fuentes)
def build_book(world, journal, valuer, cfg, plan_cfg, frozen, baseline) -> Book
def apply(book: Book, intent: Intent, outcome: Outcome) -> Book    # puro; sent/would/unknown → efecto inmediato
def canonical_offer(o: Mapping) -> dict | None
def fingerprint(o: Mapping) -> str           # sha1(id, give, want, to, venue, expires_tick, status)
def duel_fingerprint(d: Mapping) -> str      # sha1(duel_id, rival_offer.id, .price, .days, .tick, len(messages))
def check(intent, world, book, valuer, cfg, counters, *, fresh=None, now: float) -> Verdict
    # PURA. Globales G01–G07 y luego: kinds de equipo/publicación/sobres aquí (G10–G23, G33, G40);
    # TALK_KINDS y accept de dealer → agent.talk.check; si agent.talk no se puede importar → Verdict(False, "G02.not_built")

# agent/talk.py
def check(intent, world, book, valuer, cfg, counters, *, fresh=None, now: float) -> Verdict   # G30–G32, G50, G51
TEMPLATES: Mapping[str, tuple[str, ...]]     # "abuela_buy","chato_buy","abuela_sell","chato_sell","duel","duel_days"
def render(template: str, variant: int, price: int, days: int | None = None) -> str
def firewall(text: str, price: int, days: int | None) -> Verdict   # G60
```

### 2.6 `agent/gate.py` (M5) y `agent/execution.py`
```python
REQUEST_FOR: Mapping[str, Callable[[Mapping, str | None], tuple[str, str, dict | None]]]
  # accept      → ("POST", f"/api/offers/{offer_id}/accept", {"assets": [give_asset]} si give_asset, si no {})
  # list_offer  → ("POST", "/api/offers", {"give": {"assets":[asset_id]} | {"cash": price},
  #                 "want": {"cash": price} | {"cards": [ref]}, "venue": "rastro", "expires_in_ticks": E})
  # cancel      → ("DELETE", f"/api/offers/{offer_id}", None)
  # open_thread → ("POST", "/api/threads", {"with": dealer, "topic": {"buy": {"card": ref}} | {"sell": {"assets": ids}}})
  # say         → ("POST", f"/api/threads/{tid}/messages", {"text": text, "price": price})
  # close_thread→ ("POST", f"/api/threads/{tid}/close", None)
  # open_pack   → ("POST", f"/api/packs/{asset_id}/open", None)
  # duel_say    → ("POST", f"/api/duels/{did}/messages", {"text": text, "price": p, "days": d, "offer": {"price": p, "days": d}})
  #               (sin días: {"text": text, "price": p}); el esquema PostMessage admite days arriba [regla, OpenAPI]
  # duel_accept → ("POST", f"/api/duels/{did}/accept", None)
  # La forma del cuerpo de open_thread y say se congela tras un viaje de ida y vuelta contra el servidor falso
  # copiado del harvest (me_threads_full); el texto lo pone el Gate con talk.render.
class Gate:
    def __init__(self, transport, journal, valuer, cfg, plan_cfg, paths, *, mode: str,
                 armed: Callable[[], frozenset[str]], paused: Callable[[str], bool], clock)
    book: Book
    def begin_tick(self, world: World) -> list[str]
    def reconcile(self, world: World) -> list[dict]
    def execute(self, intent: Intent, world: World) -> Outcome
    def stopped(self) -> str | None
def write_stop(reason: str, paths: Paths) -> None
# agent/execution.py
@contextmanager
def writer_lock(paths: Paths): ...   # state/writer.lock fijo; guarda PID y línea de órdenes para `status`
def team_writer(team): ...           # se mantiene como envoltorio de writer_lock(Paths.at()) para el código antiguo
```
**`execute`, paso a paso:**
1. `stop_active()` → diario `refused`, `refused:G01.stop`.
2. `iid = intent_id(world.tick, intent)`; resultado previo para `iid`, o `domains_of(intent) ∩ book.unknown_domains` → `refused:G05`.
3. Fuentes: `SOURCES[kind] ∩ world.down` → `refused:G06.source:<fuente>`.
4. Relectura fresca (solo accept y duel_accept, con `limiter.take(priority=True)`): equipo → `/api/venues/rastro/offers` u `/api/me/offers` si va a nosotros; dealer → `/api/threads/{tid}`; duelo → `/api/duels`; y `/api/clock` (debe dar `tick == world.tick`). La interpretación va en `try`: error → `refused:G10.shape`/`G10.stale`, dominio bloqueado este tick.
5. `v = guards.check(..., now=clock.now())`; se recalcula la predicción con `world.server_values` y se compara (±0,01) → `trip`.
6. `not v.ok` → diario `refused`.
7. `mode != "live"` o táctica no armada o en pausa → diario `would`; `book = apply(book, intent, would)`.
8. Plazo: `clock.now() > world.tick_deadline` y `kind ∉ {cancel, close_thread}` → `deferred:G03.late` (no se envía).
9. Diario `intent` (fsync) con `{iid, tactic, kind, args, reason, expected_effect, prediction, guards, mode, request:(method, path, sha256)}`.
10. `method, path, body = REQUEST_FOR[kind](args, text)`; `with write_permit(iid, method, path, body): r = transport.send(method, path, body)`.
11. Según `r.status`: `ok` → `result ok` (para accept: además `accepted_unsettled`); `deferred` → `result deferred`; `refused` → `result refused:<code>` (cooloff/persona_quota → `dealer_block`); `unknown` → diario `unknown` y el dominio se congela. Contadores += 1 en ok y unknown. `book = apply(book, intent, outcome)` en ok y unknown.

### 2.7 Sensor y tácticas (firmas)
```python
# agent/world.py (M7)
class SchemaError(Exception): ...
class Sensor:
    def __init__(self, transport, base_url, journal, paths, public_limiter, clock)
    def fast(self, prev: World | None) -> World            # solo clock + me/offers (vía rápida)
    def snapshot(self, prev: World | None) -> tuple[World, Secrets]
ALLOW: Mapping[str, frozenset[str]]                         # campos que se conservan por tipo de objeto
def parse_clock(d) / parse_me(d) / parse_offer(d) / parse_thread(d) / parse_duel(d) -> Mapping   # SchemaError
def split_untrusted(obj) -> tuple[Any, list[tuple[str, str]]]   # quita TODA cadena fuera de ALLOW
def clock_reading(clock: Mapping, schedule: Mapping) -> str      # "N" | "M" | "C" | "P" | "?"

# agent/tactics/pages.py (M8)
def load_plan(path: Path) -> PlanCfg
def plan(world, valuer, plan_cfg, frozen: Mapping[str, str]) -> tuple[list[Need], dict[str, str]]
def protect_sets(world, plan_cfg, journal_view) -> frozenset[str]
def closer_ref(world, missing: Sequence[str], plan_cfg) -> str
    # común sin pujas rivales en el tablón > más ventas vistas > más `minted` libres > número más bajo
# agent/tactics/hygiene.py (M9)
def startup(world, book, plan_cfg) -> list[Intent]                # J0
def watch(world, book, valuer, cfg, plan_cfg) -> list[Intent]     # G19 + INV-23 + cierre de hilos al final del día
def propose(world, book, valuer, cfg, plan_cfg, state) -> list[Intent]   # startup + watch + J1 + hilos ajenos
# agent/tactics/dealers.py (M10)
def next_price(profile: Mapping, k: int, last: int | None, limit: int) -> int
class DealerState:
    @staticmethod
    def rebuild(world, journal) -> "DealerState"
def propose(world, book, valuer, cfg, plan_cfg, needs, state) -> list[Intent]
# agent/tactics/rastro.py (M11)
def propose(world, book, valuer, cfg, plan_cfg, needs, state) -> list[Intent]   # J4 (tactic "closer"), J5, J6, J9, J13
# agent/tactics/duels.py (M12)
@dataclass(frozen=True)
class DuelView: ...
def view(duel: Mapping, tick: int) -> DuelView
def decide(view: DuelView, params: Mapping) -> tuple[str, int | None, int | None]   # ("say"|"accept"|"wait", price, days)
def propose(world, cfg, plan_cfg, params, state) -> list[Intent]
# agent/calibrate.py (M13)
class Calibrator:
    def __init__(self, journal, paths)
    def on_tick(self, prev: World | None, world: World) -> list[dict]
    def paused(self, tactic: str) -> bool
    def pause(self, tactic: str, why: str) -> None; def resume(self, tactic: str, why: str) -> None
    def stop_reasons(self) -> list[str]
    def report(self) -> str
# agent/runner.py (M15)
def choose(intents: Sequence[Intent], world: World, cfg: Cfg) -> list[Intent]
def run(mode: str, armed: Iterable[str], *, paths: Paths, plan_path: Path, max_ticks: int | None = None,
        base_url: str | None = None, transport: GuardedTransport | None = None, clock=None) -> int
# bazaar.py (M16)
def main(argv: Sequence[str]) -> int
```

---

## 3. Invariantes

| Id | Invariante | Lo impone | Test (criterio) |
|---|---|---|---|
| INV-01 | **Punto único.** Ningún método distinto de GET sale del proceso salvo desde `Gate.execute`, con un permiso de un uso que coincide en (método, ruta, sha256 del cuerpo) y ruta de `WRITE_ROUTES`. GET solo a `GET_ALLOWLIST` con `fullmatch`. Nunca admin, venues, flags ni broker (las excepciones manuales con el OK de Jorge quedan fuera del arnés: §15). | `GuardedTransport.send`/`_call`; audit hook; `broker()` desactivado; test AST | `test_transport.py`: POST sin permiso, con permiso de otra ruta/cuerpo, reutilizado, `/api//admin`, `/API/admin`, `/api/%61dmin`, ruta con `\n` → `GateViolation` y 0 peticiones. `test_architecture.py`: los nombres prohibidos de §0 no aparecen en `agent/` ni `bazaar.py` fuera de `transport.py`/`gate.py`; `/api/admin` solo como literal en `transport.py` y `sim/fake_server.py`. |
| INV-02 | **Ninguna escritura** fuera de `live`, con la táctica sin armar o pausada, con STOP, o pasado `tick_deadline`; con reloj en pausa o puertas cerradas solo `cancel` y `close_thread`. | Transport (modo, STOP en cada envío); Gate G01, G03 | `test_dry.py`: 1.000 ticks en dry → 0 escrituras. `test_transport.py`: `STOP.txt` creado entre la decisión y el envío → 0 POST. `test_gate.py`: pausa, puertas cerradas (cancel sí, accept no), decisión tardía. |
| INV-03 | **Presupuestos por tick:** aceptaciones ≤ `limits.accepts` (los duel_accept cuentan); ≤ 1 mensaje por hilo o duelo; publicaciones + cancelaciones ≤ min(6, `limits.listings` − 2); ofertas propias (maker t18) ≤ `limits.open_offers` − 4; hilos propios ≤ `limits.threads` − 1; ≤ 3,5 req/s (ráfaga 8) con 2 fichas reservadas (dom 4 oct: era 2,5). | Gate G04; `RateLimiter`; `Limits.from_clock` con `LIMIT_KEYS` | `test_contracts.py`: `clock.json` del harvest → `Limits(1,1,6,30,12)`. `test_gate.py`: 100 intents → 1 aceptación; 30 ofertas dirigidas a nosotros no bloquean publicaciones. `test_e2e_fake.py`: 0 429 y tasa ≤ 2,5 req/s. |
| INV-04 | **Ningún trato con pérdida predicha.** Equipos: neg_lo ≥ 3 al aceptar y ≥ 2 al publicar; cierre ≥ 20; reabastecimiento ≥ 15. Dealers: ΔV_lo − p ≥ 1 al comprar, p − ΔV_hi ≥ 1 al vender. | G12, G20, G21, G31, G32 | `sim/invariants.py` + `test_e2e_fake.py`: Δneg ≥ 0 del oráculo en cada liquidación nuestra (dealers: == 0). `test_replay_friday.py`: rechaza los 5 tratos con pérdida. |
| INV-05 | **Estructura exacta:** solo se acepta una forma canónica cuya huella, releída en el mismo tick, coincide con la del intent. | G10, G11 (`canonical_offer`, `offer_safety`) | `test_shapes.py`: `tests/fixtures/twisted_offers.json` (60) + 1.000 mutaciones → 0 aprobaciones. Las 56 ofertas reales de dealer: 56/56 pasan `offer_ok` tal cual; 56/56 pasan `executable_offer` con `status="open"` y `tick=created_tick`; 56/56 se rechazan con su estado real o con `tick=expires_tick+1`. |
| INV-06 | **Copias protegidas:** `free(ref) = held − listed − pending_out`; nada entrega un activo si `free(ref) − 1 < keep(ref)`, salvo el reabastecimiento J13 con todas sus condiciones. | G13; vigilancia G19 | `test_guards.py` / `test_hygiene.py`: con el harvest, la vigilancia propone exactamente {2463, 1652}; nunca hay más de `held − keep` copias publicadas o comprometidas. |
| INV-07 | **Caja:** `cash_free ≥ 0` tras cada decisión, con el libro en marcha (pujas, aceptaciones sin liquidar, max(límite, precio en pie) de los hilos de compra, reserva 10). | G16 + `guards.apply` | `test_gate.py`: dos pujas cuya suma supera `cash_free` en el mismo tick → la segunda `G16`. `test_e2e_fake.py`: 0 `insufficient_cash`. |
| INV-08 | **Un solo camino de compra por ref** (puja, hilo con dealer, aceptación sin liquidar), con el libro en marcha. | G15 | `test_gate.py`: puja y `open_thread` por la misma ref en un tick → el segundo `G15`. |
| INV-09 | **Sobres:** nunca se compran; con uno sin abrir, ninguna compra; se abren al llegar, después de cerrar los hilos de compra. | `ARGS`; G14; G40 (`threads_open`); hygiene | `test_hygiene.py`; `test_replay_friday.py` (LAT-06 con el sobre en mano → rechazada). |
| INV-10 | **El cierre de RET o CHA nunca se compra a un dealer**, contando `Book.projected` y la carta de cierre congelada. | G30, G32 | `test_e2e_fake.py`: los dos dealer-bots aceptan en el mismo tick con RET a 8/10 → la página no se cierra por dealers. |
| INV-11 | **Hilos con dealer:** precio propio estrictamente monótono; límite fijado al abrir que solo baja; nunca se contraoferta una final; nunca se repite precio ni texto. | G30, G31 (M4b); `thread_limit` del diario y del servidor | `test_dealers.py`; `test_chaos.py` (monotonía tras reiniciar). |
| INV-12 | **Duelos:** ≥ 1 P de excedente en todo precio; ofertas monótonas (con días, devolver al rival su par en pie no cuenta como retroceso); `duel_accept` solo si la relectura del mismo tick muestra `rival_offer.tick == tick actual`, la misma huella de duelo, `tick ≤ deadline − 1` y tiempo restante ≥ margen; en dos asuntos, ningún precio sin la guarda de días. | G50, G51 (M4b) | `test_duels.py`: 8 rivales × 2 papeles × 3 decays, 2.000 casos → 0 fuera de límite. El servidor falso aplica el accept a la oferta en pie en el momento del POST (sin id); un rival `worsening` que habla en un tick distinto → no se acepta; uno que ya habló en el tick → la diferencia entre lo leído y lo liquidado es 0. |
| INV-13 | **Texto:** solo plantillas; dígitos ⊆ {str(p), str(d)}; sin términos prohibidos; ≤ 280 caracteres. El texto ajeno nunca está en el World ni lo lee una táctica. | G60; sensor con lista blanca; test AST (`untrusted`, `"text"` no aparecen en `agent/tactics/*`, `guards.py`, `talk.py`, `gate.py`) | `test_firewall.py`: 2.000 generados + 300 maliciosos → 0 fugas; `p == límite` se permite; la caja en el texto se rechaza. `test_e2e_fake.py`: misma partida con y sin inyección → mismas decisiones. |
| INV-14 | **Idempotencia y fallo cerrado:** ≤ 1 envío por `intent_id`; todo lo que no es `ok`/`deferred`/`refused` limpio es `unknown`, congela su dominio y nunca se reenvía. | G05; `Response`; `Gate.reconcile` | `test_chaos.py`: 4 puntos × 25 excepciones + 5 muertes reales del subproceso → 0 envíos duplicados. `test_transport.py` con `html_200`, `truncated_body`, `redirect_302`, `incomplete_read` → `unknown`. |
| INV-15 | **WAL:** intent con fsync antes del envío y result/unknown después; un solo fichero para todo el evento; cola rota recuperada; si el diario falla → STOP; al reiniciar se concilia antes de escribir. | Gate + Journal | `test_journal.py`: cambio de día simulado → `own_objects()` conserva lo del día anterior; línea final rota → `journal.corrupt` y cadena válida. |
| INV-16 | **Escritor ajeno:** una oferta con maker t18, un hilo con dealer abierto por t18, un mensaje con `sender`/`from` nuestro o una aceptación nuestra que ni el diario ni la línea base explican → STOP en ≤ 1 tick. Lo que crean otros (hilos que nos abren, ofertas dirigidas a nosotros) nunca dispara STOP. | `Gate.begin_tick` | `test_foreign_writer.py`: desde el harvest sin cambios, 5 ticks tranquilos → 0 STOP; un mensaje "como t18" → STOP; un rival abre un hilo con nosotros y nos manda 30 ofertas → 0 STOP. |
| INV-17 | **Calibración:** toda escritura lleva predicción. `hard_fail` → pausa persistente. El STOP por liquidación fuera de banda solo aplica a ofertas creadas por el arnés (por `intent_id`); las heredadas usan su banda de `state/baseline.json`. Las ventanas que cruzan un cambio de ronda se excluyen. | Calibrator | `test_calibrate.py`: 2504 cumplida en t170 → `pass`, sin STOP; neg 74,5 → 0 al cambiar de ronda → 0 pausas; la misma caída a mitad de ronda → pausa. |
| INV-18 | **Secretos:** ni en diario, snapshots, dashboard ni consola; redacción por patrón y por igualdad con el valor real; sin redirecciones; `Secrets` fuera del World. | `redact`; abridor sin redirecciones; sensor | `test_transport.py`; escaneo de `logs/run/**` tras e2e: 0 `tk-`, `bk_`, `*_key` ni el valor de la clave de test. |
| INV-19 | **Aislamiento:** una excepción en una táctica solo la salta; una forma rara en una relectura del Gate → `refused`, no STOP; un tipo de sobre desconocido → `valuation_ok = false`. | runner; Gate paso 4; Valuer | `test_runner.py`; `test_gate.py` con `type_swap`/`missing_field` en la relectura; `test_valuation.py` con `sobre_nuevo`. |
| INV-20 | **Juego limpio:** nunca operar en un venue propio, sin órdenes complementarias, sin ida y vuelta de una ref en El Rastro en 60 ticks (según nuestras liquidaciones del diario), sin flags desde la Gate (las denuncias manuales con OK: §15). | `ARGS` (venue fijo); G12 | `test_guards.py`. |
| INV-21 | **Aislamiento de los tests:** ningún test alcanza un host distinto de 127.0.0.1 ni toca `logs/run`, `state/` o `.env` del repo. | `tests/__init__.py`; `Paths` temporal; `GuardedTransport` con `BAZAAR_TEST` | `test_isolation.py`: con un `.env` de aspecto real presente, `selftest` hace 0 conexiones fuera de 127.0.0.1 (audit hook) y el hash de `logs/run/` y `state/` no cambia. |
| INV-22 | **Escritor único:** todo `run` (dry incluido) y todo `do` de un disparo toman `state/writer.lock`; el CLI nunca escribe el diario ni `armed/pauses`. | `writer_lock`; inbox | `test_cli.py`: `arm` con el runner vivo no toca el diario; dos `run` → el segundo sale con código 3. |
| INV-23 | **Compromisos en pie:** ningún hilo de compra abierto al abrir un sobre ni a ≤ `grant_lookahead_ticks` de una subvención con sobre; ninguna puja de cierre abierta mientras `delivery_risk` (sobre pendiente o subvención cercana, hilo con la Abuela abierto, o hilo con dealer abierto con un nivel nuevo anunciado). | G40, G30, G21; `hygiene.watch` | `test_e2e_fake.py`: el servidor da un sobre con un hilo con precio en pie y el bot acepta ese mismo tick → 0 liquidaciones con Δneg < 0. |

---

## 4. Guardas

Notación: `w` World, `b` Book, `v` Valuer, `c` Cfg, `n` Counters, `it` Intent, `a = it.args`.
- `dv_add(ref) = min(v.delta_add(b.projected, ref, b.packs), w.server_values.get(ref, +inf))`.
- `dv_rm(ref) = max(v.delta_remove(b.held, ref, b.packs), your_value(ref))`.
- `free(ref) = b.held[ref] − b.listed[ref] − b.pending_out[ref]`.

**Dependencia de fuentes (`SOURCES`, G06):**

| Kind | Fuentes que deben estar bien |
|---|---|
| cancel | clock, me/offers |
| close_thread | clock, me/threads |
| list_offer | clock, me, me/offers, me/threads, board |
| accept (equipo) | clock, me, me/offers, me/threads, board |
| open_thread, say, accept (dealer) | clock, me, me/offers, me/threads, threads |
| open_pack | clock, me, me/threads |
| duel_say, duel_accept | clock, duels |

Además, todo kind que dependa del valor (todos salvo cancel, close_thread, open_pack y duelos) exige `b.valuation_ok`.

**Globales**
- **G01 STOP.** `stop_active()` → `refused:G01.stop` (en el Gate y en el transporte). Sin armar o en pausa → `would` (no es rechazo).
- **G02 Tipo.** `kind ∈ KINDS`; `make_intent` validó `ARGS`; kinds de M4b sin `agent/talk.py` → `G02.not_built`.
- **G03 Reloj.** (a) `paused is False` y `doors == "open"`, salvo cancel y close_thread. (b) `now ≤ w.tick_deadline`, salvo cancel y close_thread. (c) accept y duel_accept: el reloj releído da `tick == w.tick`.
- **G04 Presupuestos.** Contadores de §3 INV-03; solo cuentan las ofertas con maker t18 y los hilos abiertos por nosotros.
- **G05 Idempotencia.** Sin resultado para `iid`; `domains_of(it) ∩ b.unknown_domains = ∅`.
- **G06 Salud.** `SOURCES[kind] ∩ w.down = ∅`; `valuation_ok` si aplica; diario sano.
- **G07 Predicción.** Recalculada con `w.server_values` = la del intent (±0,01) → si no, `trip`.

**Aceptar oferta de equipo**
- **G10 Identidad fresca.** `fresh.status == "open"`; `fresh.expires_tick is None or ≥ w.tick + 1`; `fresh.id ∉ b.own_offer_ids`; `fresh.maker ∉ {"t18", w.own_pseudonym}`; `fresh.to ∈ {None, "t18"}`; `fresh.venue == "rastro"`; `fingerprint(fresh) == a.fingerprint`. (La comparación de maker con `t18` sola no sirve: el tablón muestra seudónimos, medido.)
- **G11 Forma exacta.** (a) venta ajena: 1 activo `card` de `a.ref`, `want == {cash: p}` con p int 1..10⁶; (b) puja ajena: `give == {cash: p}`, `want.types == ["card:"+ref]` o `want.cards == [ref]`, `a.give_asset` es nuestro y de esa ref. Cualquier otra clave no vacía → falla.
- **G12 Valor.** Compra: `g = dv_add − p − fee(p)`, `neg_lo = min(g, 50) ≥ 3`; si `closes_page(b.projected, ref)`, `neg_lo ≥ 20`. Venta a puja: `g = p − fee(p) − dv_rm ≥ 3` (`≥ RESUPPLY_MIN` si `a.resupply`). Ida y vuelta: `b.recent_rastro[ref]` no tiene el lado contrario en los últimos 60 ticks.
- **G13 Protegidas.** Todo intent que entrega un activo de `ref`: `free(ref) − 1 ≥ b.keep[ref]` (keep = 1 si página de un set de `b.protect_sets`), y el activo no está en `b.listed_assets`. **Excepción J13** (`a.resupply`): set ∈ {RET, CHA}; `b.projected` del set < 9; ref ≠ `b.frozen_closer[set]`; rareza común o infrecuente; la Abuela no bloqueada y con `dealer_deals_hour["abuela"] ≤ 6`; `fresh.expires_tick ≥ w.tick + 2`; sin sobre pendiente; G12 con `RESUPPLY_MIN`.
- **G14 Sobre sin abrir.** Con `b.packs`: solo open_pack, cancel, close_thread, duel_say y duel_accept.
- **G15 Un camino.** Para adquirir `ref`: `b.paths[ref] == 0` (con el libro en marcha), o continúa el mismo camino. Cambiar de la puja a una venta del tablón: cancelar en T, ver `cancelled` en T+1, aceptar en T+1.
- **G16 Caja.** Compra o puja: `p + fee·[aceptamos] ≤ b.cash_free`; `open_thread` de compra: `a.limit ≤ b.cash_free`.

**Publicar (autor)**
- **G20 Venta propia.** Activo nuestro, `card`, no publicado; G13; `p ≥ ceil(dv_rm + 2)`; `p ≤ 4 × libro × afinidad`.
- **G21 Puja propia.** Normal: `p ≤ floor(dv_add − 3)`. De cierre (`closes_page(b.projected, ref)`): `p ≤ floor(dv_add − CLOSER_ACCEPT_MIN)`, `not b.delivery_risk`, `a.closer`. Una puja por ref; G14, G15, G16.
- **G22 Caducidad.** `expires_ticks = clamp(round(deseados × (EXPIRY_FACTOR or 2.0)), 4, 240)`.
- **G23 Cancelar.** `a.offer_id ∈ b.own_offer_ids` y abierta.

**Hilos con dealer (M4b)**
- **G30 Abrir.** `a.dealer ∈ w.me.unlocked`, sin hilo abierto con él, no bloqueado; compra: `a.limit ≤ min(floor(dv_add − DEALER_MARGIN), need.max_price)`, no es la carta de cierre congelada ni cierra RET/CHA con `projected`, sin subvención con sobre a ≤ `grant_lookahead_ticks` (`G30.grant_soon`), G14, G15, G16; venta: G13 y `a.limit ≥ ceil(dv_rm + DEALER_MARGIN)`.
- **G31 Decir.** `último_nuestro < p ≤ limit_t` (`limit_t = min(límite al abrir, floor(dv_add − DEALER_MARGIN))`); `p ∉ thread_prices`; la oferta en pie no es `final`; si la oferta en pie ≤ p → `G31.should_accept`; texto → G60.
- **G32 Aceptar de dealer.** `offer_safety.executable_offer` (con `expires_tick ≥ w.tick + 1`, la misma regla que G10) y `offer_ok`; `precio ≤ limit_t`; `dv_add − precio ≥ DEALER_MARGIN`; no cierra RET/CHA con `projected`; G14, G16.
- **G33 Cerrar hilo.** Siempre, si es nuestro (M4a).
- **G40 Abrir sobre.** Activo nuestro `pack`; sin hilos de compra abiertos (`G40.threads_open`) (M4a).

**Duelos (M4b)**
- **G50 Mensaje.** `s = +1` vendedor / `−1` comprador; sin días `s·(p − L) ≥ 1`; con días `days` int 0..10 y `s·(p − L) ≥ 1 + pen(d)`, con pen(d) = `|w|·d` si cada día nos cuesta (signo −1) y 0 si los días suman (signo +1; el valor medido es `s·(p − L) + signo·|w|·d`, 44/44 tratos de Duels II). El signo sale del `days_sign` del sensor, si no del `days_meaning` del servidor, si no del papel (comprador −1, vendedor +1); un signo leído que contradice al papel da −1 (`talk.checked_sign`) y el runner avisa. `w` nulo → `duels.days_weight_fallback` del plan, si no `G50.days_unknown`. Monótono respecto de todas nuestras ofertas que muestra el servidor (`G50.monotone`), salvo, con días, devolver al rival su propio par (precio, días) en pie; nunca repetir nuestra oferta en pie (`G50.repeat`) ni un precio peor que el del rival (`G50.worse_than_rival`); texto → G60.
- **G51 Aceptar.** Relectura: `status == "live"`; `rival_offer` no nulo; `rival_offer.tick == tick releído`; `duel_fingerprint(fresh) == a.fingerprint`; `s·(rival.price − L) ≥ 1`; con días, `s·(rival.price − L) ≥ 1 + |w|·d` si cada día nos cuesta (signo −1: comprador, o un signo leído que contradice al papel) y solo `≥ 1` si los días suman (signo +1: vendedor; el precio nunca sale del límite); `tick ≤ deadline − 1`; `w.tick_deadline − now ≥ TICK_MARGIN_S`; G04.

**Texto (M4b)**
- **G60 Firewall.** Plantilla del contexto; `set(re.findall(r"\d+", text)) ⊆ {str(p), str(d)}`; sin `(?i)l[íi]mite|limit|reserv|m[íi]nimo|m[áa]ximo|presupuesto|budget|valor|value|afinidad|affinity|multiplic|clave|key|token|tk-|bk_|http|system|ignore|\{|\}`; ≤ 280; sin control; distinto del último texto del hilo. Las plantillas se validan al importar.

**Vigilancia (`hygiene.watch`, propone; el Gate comprueba con G23/G33)**
- Venta propia con `free(ref) < keep(ref)` → `cancel`, de una en una recalculando, primero la que caduca antes (desde el harvest: 2463 y 1652).
- Puja propia con `dv_add − p < b.bid_band[id]` (2 para pujas normales del arnés; para cierres, `min(dv_add − p, 50) < 20`; heredadas, su banda de la línea base: 2503/2504 → 0) → `cancel`.
- Puja que deja `cash_free < 0` → `cancel` (la más cara primero).
- Puja de cierre con `b.delivery_risk` → `cancel` (la táctica `closer` la repone cuando desaparece).
- Hilo de compra con precio en pie > `dv_add − DEALER_MARGIN` → `close_thread`.
- Sobre en `me.assets` o subvención con sobre a ≤ `grant_lookahead_ticks` → `close_thread` de todos los hilos de compra; el sobre se abre al tick siguiente.
- `t_hours ≥ day_end_hours` → `close_thread` de todos los hilos con dealer. Desde el dom 4 oct el runner fija cada tick la hora de hoy (`pages.effective_plan`): cierre = el antes de `day_closes` / `end_round` del calendario vivo y de `clock.closes` (pared: t + (closes − ahora)/3600; un cierre ya pasado no cuenta); fin de dealers = mín(cierre, cierre de puestos) − `day_end_min_before_close` (5 min); endgame del closer = cierre − `closer.endgame_min_before_close` (35 min); tras el fin de dealers o en el endgame J6 compra también cualquier primera copia fuera de las páginas por debajo de nuestro valor (`endgame_buy_any`); las horas de `config/plan.json` solo valen si el calendario se lee pero no trae cierre y no hay `clock.closes`.
- Hilo abierto por otro equipo con nosotros → diario `untrusted`; `close_thread` si E17 muestra que cuenta contra nuestros 6.

**Escritor ajeno (`Gate.begin_tick`)**
- **Línea base** (primer arranque, antes de cualquier escritura): ids de las ofertas con maker t18 y su banda; ids de todos los hilos con dealer (abiertos y cerrados) y de todos nuestros mensajes; en duelos, `(did, tick, price, days)` de cada mensaje nuestro, incluidos los `done` y los 5 de práctica vivos (149, 150, 193, 194, 219). Se guarda en `state/baseline.json`.
- STOP `foreign_writer:<detalle>` si aparece una oferta con maker t18, un hilo con dealer de team t18, un mensaje con `sender == "t18"` (hilo, por `msg_id`) o `from == "you"` (duelo, por `(did, tick, price)`) que no explican el diario ni la línea base.
- Cambio de caja o activos sin explicar (ni liquidaciones, ni subvenciones del calendario, ni intents) → `alarm` + pausa de las tácticas de compra.

---

## 5. Modos, CLI y kill switch

| Comando | Qué hace |
|---|---|
| `python3 bazaar.py selftest` | Corre por etapa las listas de módulos de `bazaar.STAGE_FILES` (no la suite completa); falla si corre 0 tests o menos del mínimo por etapa; agrupa por etapa (core, hygiene, dealers, rastro, closer, duels) y escribe `state/selftest.json` `{etapa: {green, code_hash}}`; comprueba que `logs/run/` y `state/` (salvo `selftest.json`) no cambian. Comprueba Python ≥ 3.9. |
| `python3 bazaar.py clockcheck` | GET sin clave a clock y schedule; imprime N/M/C/P/?, ronda, `t_hours`, `paused`, `upcoming`. |
| `python3 bazaar.py run [--live] [--arm a,b]` | Toma el candado (dry incluido). Sin `--live`: dry, 0 escrituras. Con `--live`: escriben solo las tácticas armadas cuya etapa está en verde con el mismo `code_hash`; `armed.json` = exactamente `--arm`. |
| `python3 bazaar.py arm/pause <táctica> --why "..."` | Deja `state/inbox/<ts>-arm.json` (temporal + `os.replace`); el runner lo aplica y lo anota. `arm` rechaza una táctica con su etapa en rojo. |
| `python3 bazaar.py do <kind> --args '<json>' --why "..." [--live]` | Un intent humano, táctica `manual` (siempre armada en live). Sin `--live` es un ensayo (`would`) y, con un runner vivo en live, se rechaza. Con el runner vivo va por el inbox; sin runner toma el candado y ejecuta un solo tick. Las mismas guardas. |
| `python3 bazaar.py stop "motivo" [--flatten]` | Crea `STOP` en la raíz del repo (`Paths.root`, no el directorio actual). Con `--flatten`, primero deja una orden: el runner cancela nuestras pujas y cierra los hilos de compra en un tick y después escribe STOP. Crear a mano `STOP`, `STOP.txt`, `stop`… en la raíz también vale. (Se retira la afirmación de `BAZAAR_KILL`: no llega a un proceso en marcha.) |
| `python3 bazaar.py resume [táctica] --why "..."` | Sin táctica: borra STOP (STOP, STOP.*, stop, stop.*); el runner lo anota. Con táctica: deja una orden para reanudarla (exige runner vivo). Solo una persona. |
| `python3 bazaar.py status` | 0 llamadas a la API; lee el diario con `writer=False`: modo, armadas, pausadas, STOP, pendientes, unknowns, `cash_free`, últimos veredictos, alarmas, quién tiene el candado (PID y orden). |
| `python3 bazaar.py replay-friday` | Pasa los tratos y los 108 mensajes de duelo del viernes por las guardas. |
| `python3 bazaar.py report` (L3) | Calibración por táctica. |

`main()` llama a `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` (consola cp1252).

---

## 6. Diario

- `logs/run/journal.jsonl`: un solo fichero para todo el evento, solo añadir, cada fila con `day` y `mode`.
- `logs/run/untrusted.jsonl`: texto ajeno en base64; no lo leen `status` ni `report`.
- `logs/run/snap/<tick>.json`: World redactado (1 de cada 5 ticks y en cada tick con escritura).
- `state/`: `armed.json`, `pauses.json`, `frozen.json`, `baseline.json`, `selftest.json`, `writer.lock`, `inbox/`. El runner es el único que escribe `armed/pauses/frozen/baseline`. Lectores: JSON roto = "conservar el valor anterior"; `armed.json` roto al arrancar = nada armado + `alarm`.
```
tick              {cash, cash_free, points:{neg, ladder, duel, mm, bench}, round, reading, req_rate, alarms}
intent            {id, tactic, kind, args, reason, expected_effect, prediction, guards, mode, request}   (fsync)
would | refused   {id, tactic, kind, code, detail, prediction}
result            {id, status, code, response}                                                         (fsync)
unknown           {id, domains, error}                                                                 (fsync)
accepted_unsettled{id, offer_id, ref, price, until_tick}                                               (fsync)
reconciled        {id, landed, evidence}                                                               (fsync)
settlement        {ids, tick, cash_delta, assets_in, assets_out}
measure           {ids, pred, meas:{neg, ladder}, verdict}
round_reset       {from_round, to_round, before, after}                                                (fsync)
baseline | cmd | pause | resume | arm | param | stop | alarm | trip | error | shape | clock | truncated
```

---

## 7. Bucle de predicción y medida (`agent/calibrate.py`)

1. **Liquidación:** una oferta nuestra deja de estar abierta, un hilo pasa a `deal`, un duelo se cierra o cambian activos/caja. Se empareja con su `intent_id`; para las heredadas, con la línea base.
2. **Ventana:** antes = `*_points` del tick previo; después = la primera lectura con cambio (≤ 3 ticks). Nunca `score` (P-14).
3. **Cambio de ronda:** si `round` cambia entre los dos ticks, o todos los `*_points` caen a la vez sin liquidación nuestra → fila `round_reset`, nueva base, y esa ventana no da veredicto ni pausa (E2 queda como medida pura).
4. **Atribución:** una liquidación → todo; varias → suma; ventana ambigua no cuenta para pausas blandas, pero un `hard_fail` de la suma pausa a todas las implicadas.
5. **Acciones automáticas:** `hard_fail` → pausa persistente; 2 `soft_fail` en las últimas 5 → pausa; escalera que baja → pausa `dealers`; Δneg ≤ −1 sin atribuir → pausa de compras; liquidación de una oferta **creada por el arnés** que hoy fallaría G12/G20/G21/G32 → STOP; una heredada fuera de su banda de línea base → `alarm` (no STOP); suma diaria de sorpresas negativas < −60 → STOP (era −5: el domingo a las 09:32 paró el bot un cierre que ganó +23 frente a +50 predicho; `9a871e2`). Sin `recheck` conectado, «fallaría hoy» se aproxima con Δneg medido ≤ −1 (`LOSS_STOP`).
6. **Aprendizaje:** `NEG_CAP_CONFIRMED` solo si la ganancia sin tope predicha era ≥ 55 y lo medido es 50,0 ± 0,1 (E5); tabla de escalera por dealer (E4); `param DUEL_ACCEPT_SHARED=false` lo aplica una persona (E9). Ningún límite de precio se cambia solo.

---

## 8. Fallos y conciliación

| Fallo | Respuesta |
|---|---|
| Red o 429 en un GET | ≤ 2 reintentos; si sigue, fuente en `down` y G06 bloquea lo que depende de ella |
| Cualquier envío no limpio (red, 5xx, 3xx, 2xx no-JSON/truncado, 4xx sin cuerpo del juego, excepción) | `unknown`; dominio congelado; `reconcile` en ≤ 3 ticks; si no, pausa de la táctica |
| 429 `wait_for_tick`/`rate_limited` | `deferred`; 3 `rate_limited` en un minuto → limitador a 1,5 req/s durante 60 s |
| 4xx de negocio | `refused:<code>`; `cooloff`/`persona_quota` → `dealer_block` hasta `until_tick` o la siguiente hora de juego |
| Forma inesperada en una lectura del sensor | Fuente `down`, fila `shape`; 3 seguidas → `alarm` |
| Forma inesperada en una relectura del Gate | `refused:G10.shape`, dominio bloqueado ese tick |
| Tipo de sobre desconocido | `valuation_ok = false`; la higiene lo abre igual (G40 no depende del valor) |
| Aceptación `ok` | `accepted_unsettled` (cuenta en `cash_free`) hasta que `/api/cards/{asset_id}` muestre la fila `to = t18`/`from = t18` con `why = "trade #<offer_id>"`; sin ella en T+2 → `reconciled{landed:false}` y se libera |
| Salto de tick > 1 | Conciliación completa antes de decidir |
| `clock.limits` cambia | Presupuestos recalculados; fila `param` |
| Excepción en táctica | Se salta en ese tick; 3 en 20 ticks → pausa |
| GateViolation, StopActive, JournalError | STOP y salida 2 |
| Caída del proceso | Se relanza el mismo `run`: recupera la cola, concilia pendientes (incluidos los `accepted_unsettled`), reconstruye límites y monotonía (máx. servidor/diario) y solo después escribe; primera escritura ≤ 1 tick tras conciliar |

**Conciliación por kind:** accept → `/api/me/offers` o el hilo, y `/api/cards/{id}`; list_offer → oferta nuestra de la misma forma con `created_tick ≥` tick del intent; cancel → `cancelled`; say/duel_say → nuestro mensaje con ese precio (se anota su `msg_id`); open_thread → `/api/me/threads` y el tema; open_pack → el activo ya no está; duel_accept → estado del duelo y precio liquidado (E16).

---

## 9. Servidor falso (`sim/`)

- **`sim/world.py` — `FakeGame`**, determinista con semilla y reloj virtual. Oráculo de puntuación propio (copiado del modelo medido, no importado de `agent/`), con tope configurable, sobres ponderados, escalera que solo sube con ganancia, comisión R-01 y pujas que reservan caja o no. Lo aceptado se liquida en el tick siguiente.
- **Fidelidad obligatoria con el servidor real** (comprobada por `tests/test_fake_contract.py`, que compara claves y tipos de cada respuesta con `tests/fixtures/harvest/*` y `docs/openapi.json`):
  - el tablón muestra makers con seudónimo; `/api/me/offers` muestra `t18` e incluye ofertas dirigidas a nosotros y `queued`;
  - `POST /api/duels/{did}/accept` sin cuerpo: toma la oferta en pie **en el momento del POST**; un rival puede hablar una vez por tick;
  - `clock.limits` con las claves reales de `LIMIT_KEYS`;
  - ofertas de dealer con `venue: null`, `to: "t18"`, `expires_tick = created_tick + 2`;
  - `PostMessage` acepta `days` arriba y en `offer`; sin días en un duelo de dos asuntos → `missing_days`;
  - regalos de la Abuela, sobres de bienvenida al desbloquear, tipos `sobre_barrio`, `sobre_bienvenida`, `sobre_plata`, `sobre_oro`, hilos que abren otros equipos, ventana de 500 eventos del feed.
- **Ancla medida del oráculo:** `test_sim.py` reproduce los 11/12 puntos de neg del viernes y los 5 tratos con pérdida (P-04, P-05). El oráculo comparte el modelo con la valoración a propósito: es el modelo medido; lo que se prueba contra él son las guardas, no el modelo.
- **`sim/fake_server.py`:** `serve(game, port=0, faults=None) -> (url, stop)` con `ThreadingHTTPServer`; y `game.http` para `LoopbackTransport` (el mismo `GuardedTransport` con `http=` inyectado: mismo permiso, sin sockets). `/api/admin/*` → 404 y violación.
- **`sim/faults.py`:** `Plan(rules)`; `do` ∈ 429_wait, 429_rate, 500, drop_after_commit, html_200, truncated_body, redirect_302, incomplete_read, bad_json, missing_field, type_swap, extra_field, pause, doors_closed, schedule_rewrite, limits_change, pack_grant, gift.
- **`sim/bots.py`:** TeamBot (`honest`, `twisted` desde `tests/fixtures/twisted_offers.json`, `overpriced`, `phantom`, `injector`, `opener` que acepta nuestra venta más barata en el tick 0, `closer_bidder`); AbuelaBot y ChatoBot (perfiles D-02..D-10, finales aleatorios); DuelRival (`mute`, `accept_only`, `one_and_accept`, `reactive`, `time_driven`, `firm`, `worsening`, `injector`).
- **`sim/invariants.py`:** `check(game, journal_path=None) -> list[str]` sobre el registro de peticiones y el oráculo.

---

## 10. Plan de pruebas

`python3 -m unittest discover -s tests -t .` corre la suite completa (< 180 s con reloj virtual; la lanza la CI de `.github/workflows/tests.yml`). `selftest` no la lanza: corre por etapa las listas de `bazaar.STAGE_FILES` con un mínimo de tests (`STAGE_MIN`); test_bots, test_agent_core, test_bench, test_valuer_cache, test_manual_scripts, test_sunday_sim, test_affinity, test_picaros, test_radio y test_rivals_public no están en ninguna etapa. Los tests usan `Paths.at(tempfile.mkdtemp())`, `BAZAAR_URL=http://127.0.0.1:<puerto>` y `BAZAAR_KEY=tk-test`.

| Fichero | Dueño | Etapa | Criterio |
|---|---|---|---|
| test_contracts.py | M0 | core | Tipos exactos; `Intent` indexable por id; `Limits` del harvest = (1,1,6,30,12); importa en 3.9 |
| test_transport.py | M1 | core | INV-01, INV-02 (transporte), INV-14 (clasificación), INV-18; `api/index.py` 401 sin contraseña |
| test_journal.py | M2 | core | INV-15; un fichero a través del cambio de día; cola rota |
| test_valuation.py | M3 | core | 251,6 / 505,4 ± 0,05; 24/24 your_value; 72/72 value?card; 11/12 neg; `UnknownPack`; sin `open()` |
| test_guards.py, test_shapes.py | M4a | core | ≥ 4+/4− por guarda de M4a; INV-04..10, 20, 23; G13 sobre el harvest |
| test_gate.py | M5 | core | Libro en marcha (50 pares aleatorios en un tick con los invariantes tras cada `execute`); 0 envíos en dry; relectura rara → `refused` sin STOP |
| test_sim.py, test_fake_contract.py | M6a | core | El SDK real funciona contra él; diferencias de forma con el harvest = 0 |
| test_bots.py | M6b | por bot | Cada bot sigue su perfil; criterios condicionales (p. ej. "acepta si su final ≤ límite; si no, cierra") |
| test_world.py | M7 | core | World sin texto (lista blanca); forma mutada → `down`; `tick_deadline`; seudónimo propio |
| test_calibrate.py | M13 | core | INV-17 |
| test_hygiene.py | M9 | hygiene | Desde el harvest: J0 cancela {2463, 1652} y nada más; abre el sobre tras cerrar hilos; retira la puja de cierre con riesgo de entrega |
| test_talk.py, test_firewall.py | M4b | dealers, duels | G30–G33, G50, G51, G60 |
| test_pages.py | M8 | dealers | Con RET publicado en la fixture: 9 Needs de dealer + 1 de cierre; carta de cierre congelada en 8/10 |
| test_dealers.py | M10 | dealers | Compra si la final del bot ≤ límite y si no cierra sin aceptar; nunca repite precio |
| test_rastro.py | M11 | rastro, closer | Cierre a 49 inmediato; sube a 79 con competencia; nunca baja; cancel → verificar → aceptar; J13 con sus condiciones |
| test_duels.py | M12 | duels | INV-12; 0 mensajes fuera de límite; aceptaciones solo en ticks en que el rival habló |
| test_runner.py | M15 | core | `choose`; aislamiento; ventana tardía de duelos |
| test_cli.py | M16 | core | arm/pause/stop/resume/status/do sin llamadas a la API; dos `run` → código 3; `stop` desde otra carpeta crea `STOP` en la raíz |
| test_architecture.py, test_isolation.py | M17 | core | INV-01 (AST), INV-13 (AST), INV-18, INV-21 |
| test_e2e_fake.py | M17 | por etapa | 5 semillas × 300 ticks en proceso + 1 por HTTP; 0 violaciones de `sim/invariants` |
| test_chaos.py | M17 | core | 4 puntos × 25 + 5 muertes reales → 0 duplicados, 0 escrituras antes de conciliar |
| test_foreign_writer.py | M17 | core | INV-16 |
| test_dry.py | M17 | core | 1.000 ticks → 0 escrituras |
| test_replay_friday.py | M17 | core | Rechaza el sobre a 23, LAT-01 a 10, LAT-06 con el sobre en mano, LAT-08 a 32, la venta de LAV-06 a 13 y LAT-03 a 9; aprueba SAL-02 a 9, SAL-08 a 24 y **SAL-10 a 80** (cierre: 80 ≤ floor(149,875 − 20) = 129 y min(69,9, 50) ≥ 20; con el tope fijo de 49 de la v1 se habría rechazado, que era la contradicción); 0/108 mensajes de duelo fuera de límite |
| Paneles (retirados en la versión publicada junto con `website/`, `panel.py`, `live_monitor.py`, `observe_performance.py`, `laboratorio.py`…) | — | — | — |

Además, sin etapa: test_agent_core, test_bench (L1), test_valuer_cache, test_manual_scripts (scripts de la raíz), test_sunday_sim y los de las herramientas de análisis (test_affinity, test_picaros, test_radio, test_rivals_public).

**Nota (versión publicada):** cuatro criterios no se cumplen al pie de la letra, como dicen los NOTES de cada test:
- e2e usa 4 semillas, no 5;
- las muertes de proceso de test_chaos son en proceso (`BaseException`), no de un subproceso;
- INV-10 (dos dealer-bots en el mismo tick) no está montado;
- INV-03 no tiene test de tasa (solo comprueba ≤ 1 aceptación por tick).

Las comparaciones de rendimiento (p. ej. "frente a v0") van a `bazaar.py report`, fuera del `selftest`.

---

## 11. Plan de módulos (cada fichero tiene un solo dueño)

**Olas** = orden de integración: un módulo solo importa módulos de olas anteriores o de su misma ola a través de las firmas congeladas de §2.
**Etapas** = cuándo se necesita: **A** (08:00, must-have), **C** (duelos: antes de Duels I, 11:00 N / 12:20 C), **B** (dealers y Rastro: ~10:30 N, antes de que RET esté publicado con C), **L** (después).

| Ola | Módulo | Ficheros | Etapa | Depende de |
|---|---|---|---|---|
| 0 | M0 contracts | agent/contracts.py, agent/redact.py, tests/__init__.py, tests/test_contracts.py, tests/fixtures/harvest/** | A | — |
| 1 | M1 transport | agent/transport.py, agent/client.py, agent/dashboard.py, api/index.py, tests/test_transport.py | A | M0 |
| 1 | M2 journal | agent/journal.py, tests/test_journal.py | A | M0 |
| 1 | M3 valuation | agent/valuation.py, tests/test_valuation.py | A | M0 |
| 1 | M4a guards-core | agent/guards.py, agent/offer_safety.py, tests/test_guards.py, tests/test_shapes.py, tests/fixtures/twisted_offers.json | A | M0, M2, M3 |
| 1 | M5 gate | agent/gate.py, agent/execution.py, tests/test_gate.py | A | M0, M1, M2, M3, M4a |
| 1 | M6a sim-core | sim/__init__.py, sim/world.py, sim/fake_server.py, sim/faults.py, sim/invariants.py, tests/test_sim.py, tests/test_fake_contract.py | A | M0 |
| 1 | M7 sensor | agent/world.py, tests/test_world.py | A | M0, M1, M2 |
| 1 | M13 calibrate | agent/calibrate.py, tests/test_calibrate.py | A | M0, M2, M3 |
| 2 | M6b sim-actors | sim/bots.py, tests/test_bots.py | A (TeamBot), C (DuelRival), B (dealer-bots) | M6a |
| 2 | M9 hygiene | agent/tactics/__init__.py, agent/tactics/hygiene.py, tests/test_hygiene.py | A | M0, M3 |
| 2 | M4b talk | agent/talk.py, tests/test_talk.py, tests/test_firewall.py | C | M0, M3, M4a |
| 2 | M12 duels | agent/tactics/duels.py, tests/test_duels.py | C | M0 |
| 2 | M8 pages | agent/tactics/pages.py, config/plan.json, tests/test_pages.py | B | M0, M3, M2 |
| 2 | M10 dealers | agent/tactics/dealers.py, tests/test_dealers.py | B | M0, M2, M3 |
| 2 | M11 rastro | agent/tactics/rastro.py, tests/test_rastro.py | B | M0, M3 |
| 2 | L1 bench | agent/tactics/bench.py, tests/test_bench.py | L (banco 7,0) | M0, M1, M2 |
| 3 | M15 runner | agent/runner.py, tests/test_runner.py | A | todos los de A |
| 3 | M16 cli | bazaar.py, tests/test_cli.py | A | M15, M2, M13 |
| 3 | M17 integration | tests/test_architecture.py, tests/test_isolation.py, tests/test_e2e_fake.py, tests/test_chaos.py, tests/test_foreign_writer.py, tests/test_dry.py, tests/test_replay_friday.py, tests/fixtures/harvest/** (el replay no tiene carpeta propia) | A (+ casos por etapa) | M6a, M6b, M15, M16 |
| 3 | M18 cleanup | docs/history/legacy-code/**, .gitignore, .vercelignore, CLAUDE.md, README.md, docs/research-context.md, live_monitor.py, observe_performance.py, website/worker.mjs, los `.py` que se archivan | parte 1 antes de las 07:00; parte 2 el sábado 23:15 | M1 |

Notas: M9 hygiene crea `agent/tactics/__init__.py` porque es la primera táctica de la etapa A. `config/plan.json` (M8) lo usa también la higiene: en la etapa A, M9 lee solo `startup_cancels`, `baseline_bands`, `protect_sets`, `grant_lookahead_ticks` y `day_end_hours`, y M8 lo crea con esas claves a las 05:00 (lo demás después). Las plantillas de texto son solo de M4b; los perfiles numéricos de los dealers (`profiles`) viven en `config/plan.json`. L2 (días) es trabajo dentro de M12 y `days_sign` en `config/plan.json`. L3 (informe) es `Calibrator.report` (M13) y `bazaar.py report` (M16). L4 (venue `auto`) es un fichero nuevo `agent/venue.py` con su propio intent y guarda, solo si se cumplen las condiciones de J11. L5 (dealers de nivel 3+) es trabajo de M10 en modo PROBE.

**Pistas y horario (7 pistas, desde las 03:30):**
- **P1:** M0 (03:00–03:30) → M5 (03:30–05:45) → M15 (05:45–07:00, contra tácticas stub desde las 04:00).
- **P2:** M1 (03:30–05:00) → M7 (05:00–06:30) → M16 (06:30–07:15).
- **P3:** M3 (03:30–04:30) → M2 (04:30–05:30) → M13 (05:30–06:30) → M9 (06:30–07:15).
- **P4:** M4a (03:30–06:00) → M17 núcleo (06:00–07:30).
- **P5:** M6a (03:30–05:30) → M6b TeamBot (05:30–06:15) → M17 e2e/caos (06:15–07:30) → M6b DuelRival (08:00–09:30) → dealer-bots (09:30–10:15).
- **P6 (etapa C primero):** M4b (03:30–05:30) → M12 (05:30–09:30).
- **P7 (etapa B):** M8 (05:00–06:00) → M11 (06:00–08:30) → M10 (08:30–10:15).
- **M18 parte 1** (06:00–07:00, cualquier pista libre): `SystemExit` en los `.py` que se archivan (después de `from __future__` si lo hay: `agent/scorer.py:25`), `live_monitor.py` y `observe_performance.py` con `client("read")`, `.gitignore`.
- **07:30–07:50** revisión cruzada (cada guarda la revisa quien no la escribió). **08:00** congelación de la etapa A y `selftest`.

**Aceptación por módulo** (además de sus tests): M0 congelado a las 03:30; M1 los paneles siguen sirviendo; M2 cadena verificable tras el cambio de día; M3 sin E/S; M4a revisada antes de las 07:50; M5 0 envíos en dry; M6a contrato de forma en verde; M7 ninguna cadena ajena en el World; M9 {2463, 1652}; M13 sin STOP ni pausa al cambiar de ronda; M15 una táctica que lanza no frena a las demás; M16 `status` sin API; M17 todo en verde a las 07:45; M18 los tests de paneles y `worker.test.mjs` en verde, y ningún script antiguo puede escribir.

---

## 12. Limpieza del repositorio (M18)

> **Hecho** (M18 partes 1 y 2). Lo que aquí dice `santi/` está ahora en `docs/history/legacy-code/docs/santi/`, salvo el kickoff, que está en `docs/official/kickoff.pdf`.
>
> **Versión publicada:** se retiraron además `website/`, `panel.py`, `panel.html`, `live_monitor.py`, `observe_performance.py`, `inventory_panel.py`, `laboratorio.py`, `negotiation_policy.py` y sus tests, así que las filas «keep» de esos ficheros y sus menciones en §11 (M18, aceptación) y §13 son históricas. El `docs/README.md` actual es el índice nuevo; el archivado está en `docs/history/legacy-code/docs/README.md`.

**Reglas:** archivar = `git mv <ruta> docs/history/legacy-code/<ruta>` (parte 2, una persona, el sábado a las 23:15 y `selftest` después). El `SystemExit` de los `.py` se pone en la parte 1, después de cualquier `from __future__`. Las fusiones se hacen dentro de los módulos dueños y se archivan solo cuando sus tests están en verde: casos de `offer_safety` de `test_agent_core` → `test_guards` (M4a); los de `team_writer` → `test_gate` (M5); `haggle.curve` → M10; frases de `agent/dealers.py` y `negotiation-design` → `talk.TEMPLATES` (M4b); `agent/duels.py` → M12.

| Ruta | Acción | Motivo |
|---|---|---|
| bazaar_sdk.py, RULES.md, docs/openapi.json | keep | Oficiales |
| santi/The Bazaar - Kickoff.pdf | keep → git mv a docs/official/kickoff.pdf | Oficial |
| docs/knowledge.md, docs/strategy.md, docs/harness-spec.md | keep; **añadir a git** | Hechos, plan, contrato |
| docs/research-context.md | keep (nota en §4: "esperar cuesta" refutado, U-02) | Ideas para jueces |
| README.md | keep (sección del equipo de ~15 líneas) | Readme oficial |
| CLAUDE.md | keep (reescribir; quitar las refutadas 60, 63, 67) | Instrucciones |
| SHOWCASE.md | keep (reescribir el domingo) | Jueces |
| STRATEGY.md, santi/STRATEGY_v2.md, santi/estrategia_el_estrangulamiento_de_rastro.md | archive | Refutadas; Fase 4 prohibida |
| ANALISIS_RENDIMIENTO.md, RECHECK.md, INTEGRACION_JORGE.md, HANDOFF.md, PROPUESTA.md | archive | Históricos |
| docs/playbook.md, scoring.md, audit.md, experiments.md, decisions.md, broker-design.md, information.md | archive | Sustituidos |
| docs/api.md, docs/negotiation-design.md, docs/README.md | merge, luego archive | |
| run_loop.py, run_dealer.py, run_duels.py, run_broker.py, run_morning.py, market.py | archive (+SystemExit) | Escriben sin Gate; con M1 su `client()` ya es de solo lectura |
| starter_agent.py, collect_info.py | archive (+SystemExit) | Construyen su propio cliente con la clave |
| starter_broker.py | archive (+SystemExit); `bench_plan` se copia a L1 | Tiene un bucle `broker.match` (línea 60) |
| scout.py, probe.py, sim_bench.py, recheck.py, evaluacion.py, collector_mcp.py, bench_information.py, .mcp.json | archive | Ad hoc o colector |
| agent/haggle.py, agent/dealers.py, agent/duels.py | merge, luego archive | |
| agent/broker.py, agent/information.py | archive | Refutado / colector |
| agent/scorer.py | archive (+SystemExit tras la línea 25 `from __future__`) | Segundo valuador |
| agent/offer_safety.py, agent/execution.py, agent/client.py, agent/journal.py, agent/__init__.py, agent/dashboard.html, agent/dashboard.py | keep | Del arnés |
| api/index.py, vercel.json, run_dashboard.py, panel.py, panel.html, inventory_panel.py, laboratorio.py, negotiation_policy.py | keep | Paneles |
| live_monitor.py, observe_performance.py | keep (con `client("read")`) | Paneles |
| website/** | keep; `INTERVAL` a 15000 en `worker.mjs` solo si `worker.test.mjs` sigue en verde | Panel desplegado |
| .vercelignore | keep (añadir docs/history/legacy-code/, sim/, config/, state/) | |
| .gitignore | keep (añadir STOP*, stop*, state/, config/local*.json, .pytest_cache/) | |
| tests/test_agent_core.py | merge, luego archive | |
| tests/test_new_dealer.py, test_information.py, test_evaluation.py | archive | Prueban código archivado |
| tests/test_inventory_panel.py, test_live_monitor.py, test_performance_observer.py, test_negotiation.py | keep | Paneles |
| .env.night | delete (solo el operador, tras confirmar que no hace falta; no se ha abierto) | Probablemente lleva una clave |
| logs/harvest/harvest.py | archive local (fuera de git; +SystemExit) | Script con clave |
| `__pycache__/`, `.pytest_cache/`, runs/, logs/information.jsonl | delete | Generados |
| logs/ | keep (local) | Evidencia |

---

## 13. Runbook

**Custodia de la clave.** La usan para escribir solo la máquina A (`.env`). Los paneles alojados la guardan del lado del servidor y solo emiten GET (medido: `website/worker.mjs` usa `method: "GET"` y `redirect: "error"`; `api/index.py` pasa por `client("read")`). Ninguna otra máquina ejecuta código con la clave. La exclusión entre máquinas es custodia, no candado.

**Presupuesto de peticiones (5 req/s por clave, ráfagas de 20, C-07):** runner 3,5 req/s (domingo, ticks de 15 s; era 2,5); paneles ≤ 1 req/s en total (`client.PANEL_RATE`) = un solo visor (worker: 4 GET cada 5 s ≈ 0,8 req/s) **o** Vercel (`CACHE_S` 30 ≈ 0,25 req/s), no los dos; `live_monitor.py` y `panel.py` no se lanzan el sábado.

**Sábado:**
1. **08:00** `git pull`; `python3 bazaar.py selftest`. Núcleo + higiene en verde → live. **E0 (núcleo en rojo):** dos personas, en un REPL con el SDK, cancelan solo 2463 y 1652 y releen `/api/me/offers`; no se arranca nada más hasta tener el núcleo en verde.
2. **08:30** Custodia y presupuesto (arriba). En Vercel: `DASHBOARD_PASSWORD` puesto o `BAZAAR_KEY` retirado.
3. **08:50** `python3 bazaar.py clockcheck`.
4. **08:55** `python3 bazaar.py run --live --arm hygiene`.
5. **09:00:30 y 09:05** `clockcheck` (E1, E6); `status` confirma 2463 y 1652 `cancelled`.
6. **t173** Si la etapa B no está: `python3 bazaar.py do list_offer --args '{"side":"sell","ref":"LAV-03","asset_id":<id>,"price":9,"expires_ticks":60,"closer":false}' --why "J5" --live` (y MAL-04, MAL-05 a 9; LAV-04 a 12).
7. **Actualización en caliente** (para cada etapa nueva): `python3 bazaar.py stop "hot update"` → `status` sin pendientes ni unknowns → `git pull` → `selftest` → `python3 bazaar.py run --live --arm hygiene,<lo que esté en verde>`. Concilia antes de escribir.
8. **Etapa B en verde y RET publicado** (sobre de la subvención ya abierto con N): `arm dealers --why`, `arm rastro --why`.
9. **Etapa C en verde, antes de Duels I:** `arm duels --why "Duels I"`.
10. **RET en 9/10:** `arm closer --why "cierre RET"`.
11. **Cada hora:** `status`. Una táctica pausada sola: leer su `measure` y su `pause` antes de rearmarla.
12. **Kill:** `python3 bazaar.py stop "motivo"` (o `--flatten` para retirar antes pujas e hilos), o crear `STOP` en la raíz del repo (vale `STOP.txt`). Cualquiera de los tres.
13. **Caída:** relanzar el mismo `run`.
14. **22:55** la higiene cierra los hilos con dealer; **23:00** `stop "cierre sábado"`; **23:15** M18 parte 2 (`git mv`) y `selftest`.

**Domingo:** superado por [plan-domingo.md](history/plan-domingo.md) §3 y §4 (CHA ya está en `page_sets`; calendario en tres escenarios; despliegue de `night-build`; fin de dealers y endgame derivados en vivo, ≈ 13:55 / 14:25).

**Nunca:** lanzar scripts archivados; usar la clave para escribir fuera de la máquina A; tocar `/api/admin/*`; editar `bazaar_sdk.py`; correr `selftest` con un `.env` de producción sin `tests/__init__.py` intacto.

---

## 14. Decisiones tras el equipo rojo

Tres críticos: seguridad (S), escéptico de estrategia (E) y jefe de ingeniería (B). B = bloqueante, M = mayor. Todos los bloqueantes y mayores se han corregido salvo los marcados como "rebatido" (con su evidencia). Varios se solapan; se indica el duplicado.

### 14.1 Bloqueantes

| Id | Problema | Qué se hizo | Dónde |
|---|---|---|---|
| S-B1 | Precio en pie en un hilo con dealer + sobre de la subvención = pérdida que G14 no ve | Corregido: la higiene cierra todos los hilos de compra a ≤ 3 ticks de una subvención con sobre y en cuanto aparece un sobre; G40 no abre un sobre con hilos abiertos; G30 no abre hilos con la subvención cerca; hilo cuyo precio en pie supera `dv_add − 1` → cerrar. Nuevo INV-23. | §3, §4 (vigilancia, G30, G40); strategy J1, J3 |
| S-B2 / B-M (libro) | El libro no cambia dentro del tick: dobles compromisos | Corregido: `guards.apply(book, intent, outcome)` tras cada `sent/would/unknown`; test de 50 pares aleatorios | §0, §2.5, §2.6 paso 11, INV-07/08 |
| S-B3 / B-M (huella de duelo) | `duel_accept` no lleva id; la relectura no ata al servidor | Corregido: solo se acepta si `rival_offer.tick == tick actual` (el rival ya gastó su mensaje del tick, `messages_per_side_per_tick = 1` medido) y queda margen antes del cambio de tick; `duel_fingerprint`; ventana tardía del tick; el servidor falso aplica el accept a la oferta en pie al recibir el POST. Residual (POST que llega tras el cambio de tick) medido por E16. | INV-12, G51, §1 paso 10, §9 |
| S-B4 | `bad_response`, `IncompleteRead` y 302 → escrituras duplicadas o fantasma | Corregido: `_call` propio sin redirecciones; clasificación de fallo cerrado (todo lo no limpio es `unknown`); fallos `html_200`, `truncated_body`, `redirect_302`, `incomplete_read` en `sim/faults.py` | §0, §2.2, INV-14, §8 |
| S-B5 | El calibrador haría STOP cuando se cumpla 2504 (heredada) | Corregido: STOP por banda solo para ofertas creadas por el arnés; las heredadas usan su banda de `state/baseline.json` (2503/2504 → 0) y dan `alarm` | §7.5, INV-17 |
| E-B1 | Todo depende de un arnés que no existe; sin modo degradado | Corregido: etapas A/B/C con fecha; `selftest` por etapa (una etapa roja no bloquea otra); `bazaar.py do` para cualquier jugada a mano bajo el Gate; procedimiento E0 si cae el núcleo | §5, §11, §13 |
| B-B1 | `python3 -m unittest` no encuentra tests (medido: "NO TESTS RAN", `tests/` sin `__init__.py`) | Corregido: `discover -s tests -t .`, mínimo de tests por etapa, `tests/__init__.py` (M0) | §5, §10 |
| B-B2 / S-M (diario por día) | Diario por fecha: el domingo olvida el sábado | Corregido: un solo `logs/run/journal.jsonl` con `day` por fila | §6, INV-15 |
| B-B3 / S-M (.env en tests) | Los tests comparten diario, `state/` y `.env` con el live | Corregido: `Paths` único con raíz temporal en tests; `tests/__init__.py` limpia el entorno; el transporte rechaza producción con `BAZAAR_TEST=1` y claves reales contra 127.0.0.1; `selftest` comprueba que `logs/run` y `state/` no cambian; filas con `mode` | §2.1, §2.2, INV-21 |
| B-B4 | La línea base solo tenía ids de ofertas: STOP en el tick 160 por nuestros mensajes de duelo del viernes | Corregido: la línea base guarda ofertas, hilos, `msg_id` de hilos y `(did, tick, price, days)` de duelos (incluidos los 5 de práctica vivos); test desde el harvest sin cambios | §4 (escritor ajeno), INV-16 |
| B-B5 / S-M (ronda) | Un posible reinicio de puntos al cambiar de ronda dispararía pausas y STOP | Corregido: fila `round_reset`, nueva base y la ventana se excluye | §7.3, INV-17 |
| B-B6 | ~5.000 líneas y fuzz de 10⁵: no cabe en una noche | Corregido: etapas; reloj virtual; `LoopbackTransport` en proceso; fuzz a 2.000 casos de duelo y 1.000 mutaciones; caos 4 × 25 + 5 muertes reales; e2e 5 + 1 semillas | §10, §11 |

### 14.2 Mayores

| Id | Problema | Qué se hizo |
|---|---|---|
| S-M1 / B-M (maker) | El tablón muestra seudónimos (medido); G10 y la ida y vuelta no funcionaban | Corregido: el sensor aprende nuestro seudónimo; G10 exige `maker ∉ {t18, seudónimo}` y `id ∉ own_offer_ids`; sin `me/offers` no se acepta (G06); la ida y vuelta se mide con nuestras liquidaciones del diario, sea quien sea la contraparte; el servidor falso usa seudónimos |
| S-M2 / B-M (G13, G19) | `committed` ambiguo; desempate contradictorio | Corregido: `free(ref)` formal; vigilancia de una en una recalculando, primero la que caduca antes; test exacto {2463, 1652}; J0 por ids de configuración |
| S-M3 | `closes_page` ignoraba lo que está en camino | Corregido: `Book.projected` en G12/G21/G30/G32; carta de cierre congelada en 8/10 (`state/frozen.json`); test con los dos dealers aceptando a la vez |
| S-M4 | Aceptaciones `ok` sin liquidar fuera de `cash_free` | Corregido: estado `accepted_unsettled`, resuelto con `/api/cards/{id}` (`why = "trade #<id>"`, medido en cards_all) o liberado en T+2 |
| S-M5 | Puja de cierre abierta mientras llega la carta por otra vía | Corregido: `delivery_risk` retira la puja (INV-23); umbral de la vigilancia = banda por oferta, no 0. Residual escrito en strategy §6 riesgo 3 |
| S-M6 / B-M (G03) | Frescura medida desde el final de las lecturas | Corregido: `tick_deadline` desde la lectura del reloj; relectura de `/api/clock` antes de aceptar; cancel y close_thread exentos; con ticks < 10 s el sensor se reduce a clock, me, me/offers, duels |
| S-M7 | = B-B2 | Ver B-B2 |
| S-M8 / B-M (CLI) | CLI y runner escribían el mismo diario | Corregido: el CLI solo deja órdenes en `state/inbox/`; el runner es el único escritor; JSON roto = valor anterior; nada armado si `armed.json` falla al arrancar. INV-22 |
| S-M9 | `BAZAAR_KILL` no llega a un proceso vivo; STOP relativo al directorio; `STOP.txt` | Corregido: se retira `BAZAAR_KILL`; `Paths.root` fijo; vale `STOP`, `STOP.*`, `stop`, `stop.*`; test con `STOP.txt` |
| S-M10 / B-M (barrera) | Atajos: `broker()`, `_Http._call`, `Bazaar(...)`, urllib, permiso por regex | Corregido: permiso exacto de un uso (método, ruta, sha256 del cuerpo); audit hook; `broker()` desactivado; `mode` de solo lectura; AST ampliado; `starter_broker.py` archivado; `live_monitor` y `observe_performance` con `client("read")` |
| S-M11 | Candado con nombre a elección del llamante (5 ficheros medidos en %TEMP%) | Corregido: `state/writer.lock` fijo para todo `run` y `do`; PID en el fichero; la exclusión entre máquinas es custodia |
| S-M12 / B-M (paneles) | Paneles con la clave fuera del limitador; Vercel sin contraseña es público | Corregido: runner a 2,5 req/s con ficha reservada; un solo visor; `api/index.py` falla cerrado sin contraseña. **Rebatido en parte:** "ráfagas de 4 GET en paralelo" caben en la ráfaga oficial de 20 (C-07); se limita la tasa media, no la forma del worker |
| S-M13 | `.env` heredado en tests; `run(base_url=None)` a producción | = B-B3 |
| S-M14 | Un rival puede abrir un hilo o mandarnos ofertas y provocar STOP o agotar cuotas | Corregido: el escritor ajeno solo mira lo que crea t18; G04 solo cuenta lo nuestro; hilos ajenos → `untrusted` y cierre si cuentan (E17) |
| S-M15 | = B-B5 | Ver B-B5 |
| S-M16 | Sin mapa de qué depende de qué fuente | Corregido: tabla `SOURCES` y G06 |
| S-M17 | El servidor falso no es fiel | Corregido: lista de fidelidad obligatoria y `test_fake_contract.py` contra el harvest y la OpenAPI; `duel_say` envía `days` arriba y en `offer` (el SDK solo lo pone dentro; `PostMessage` admite los dos, medido). **Rebatido en parte:** un segundo oráculo "solo de hechos" sería un modelo inventado; el oráculo es el modelo medido y está anclado a los 11/12 puntos y a las 5 pérdidas (P-04, P-05) |
| S-M18 / E-m | Carrera de apertura sobre 2463 | Corregido: `cancel` exento de puertas y pausa; intento a las 08:55; vía rápida antes de la lectura completa |
| S-M19 | Fugas por redirección, formato de clave desconocido, inyección hacia operadores | Corregido: sin redirecciones; redacción por igualdad con el valor real; texto ajeno en base64 en un fichero aparte que `status` y `report` no leen |
| E-M1 | Escalar 30→40→49 no gana nada con tope y pierde tiempo | Corregido: puja inmediata a `min(floor(dv_add − 50), cash_free)`; competencia → hasta `floor(dv_add − 20)`; cierre elegido sin pujas rivales |
| E-M2 | Bajar la puja de cierre al final es al revés | Corregido: se sube en el final del domingo; nunca se baja (strategy §2.1 #8) |
| E-M3 | E5 no distingue nada con un cierre a 49 | Corregido: E5 solo cuenta con ganancia sin tope ≥ 55 (p. ej. LAT con 2503+2504: +60,6); el cálculo sin tope es 99,1 − p |
| E-M4 | El modo `page` del domingo nunca se activaba; J11 tampoco | Corregido: un solo modo (comprar por debajo del valor nunca resta y la caja sobrante vale 0); coste desde los Needs; J13 y la liquidación de LAT financian; J11 rehecho |
| E-M5 | Vender duplicados de RET a 9 alimenta cierres rivales | Corregido: RET/CHA nunca por debajo de 30; mejor pujas rivales |
| E-M6 | Una sola aceptación por tick con varios duelos y dealers | Corregido: reparto por deadline en `choose`; sin hilos nuevos de una táctica con más de 4 duelos vivos (el domingo van de 4 en 4, así que la escalera sigue abriendo hilos; una orden manual pasa; lo que `choose` deja fuera queda en el diario: fila `dropped` para órdenes manuales, recuento en la fila `tick`). **Rebatido en parte:** E9 con los duelos de práctica antes de Duels I no es viable (vencen en t168 ≈ 09:04 con N y el módulo de duelos no estará; además una segunda aceptación válida casi nunca existe, R-06); queda oportunista y se supone compartida |
| E-M7 | El orden de construcción era el inverso de la urgencia | Corregido: M4b y M12 en la pista P6 desde las 03:30 (etapa C antes que B); fallback v0 corregido detrás del Gate |
| E-M8 | El paso 1 del cierre quedaba bloqueado por G15 | Corregido: cancelar en T, verificar `cancelled` en T+1, aceptar en T+1 |
| E-M9 | El venue `auto` no se evaluaba | Corregido: E15 lo mide; J11 = `auto` a comisión 0 si hay flujo y caja, por el Gate (L4). **Rebatido en parte:** el viernes no hubo flujo en venues de equipo (M-10) y el `auto` bloquea 270 P del plan de páginas, así que no se abre a ciegas |
| E-M10 | LAT sigue protegida aunque esté muerta | Corregido: sale de `protect_sets` en t205 si no se cumplió ninguna puja; sus cartas se venden. Corregida también la errata de LAV-04 (copia única) |
| E-M11 | Falta la jugada de reabastecer pujas de cierre rivales (t12) | Corregido: J13 con excepción acotada en G13 (ganancia ≥ 15, común/infrecuente, no el cierre congelado, cuota de la Abuela, caducidad ≥ 2 ticks) |
| B-M1 / S-m | El replay aprobaba SAL-10 a 80 y G21 lo prohibía (tope fijo 49) | Corregido de raíz: G21 ya no usa un tope fijo sino `floor(dv_add − 20)`; SAL-10 a 80 pasa (≤ 129) y el replay lo espera aprobado. Así ni el test ni la guarda se aflojan |
| B-M2 | El test AST fallaba con ficheros que deben contener `/api/admin` | Corregido: alcance `*.py` de `agent/`, `sim/`, `bazaar.py`; `/api/admin` permitido como literal en `transport.py` y `fake_server.py`; `starter_broker.py` archivado |
| B-M3 | = S-M10 | Ver S-M10 |
| B-M4 | Dependencias de la ola 0 sin declarar | Corregido: `redact`, `Paths`, `PlanCfg`, `Book`, `Secrets` y las fixtures son de M0; olas como orden de integración con dependencias explícitas |
| B-M5 | Interfaces vagas (`needs`, bloqueos, SDK, predicción, dominios) | Corregido: `Book.needs`, `Book.dealer_block`, `REQUEST_FOR`, semántica de `Prediction` por kind, `domains_of → frozenset` |
| B-M6 | `Intent` no hashable; G01 contradictorio; G19 ambiguo | Corregido: `eq=False` e índice por id; `(int, NONE)`; STOP = `refused:G01.stop` en todos los sitios; G19 = S-M2 |
| B-M7 | = S-B2 | Ver S-B2 |
| B-M8 | = S-B3 | Ver S-B3 |
| B-M9 | El firewall rechazaba el precio igual al límite | Corregido: solo se permiten `{str(p), str(d)}` y nada más; test con `p == límite` |
| B-M10 | = S-M12 | Ver S-M12 |
| B-M11 | `vlib.py` con rutas y sets fijos | Corregido: `Valuer` sin E/S con `released_sets` del catálogo; 4.ª copia 0 al comprar y `MARG[-1]` al vender |
| B-M12 | = S-M1 | Ver S-M1 |
| B-M13 | `World.untrusted` llegaba a las tácticas | Corregido: fuera del World; test AST |
| B-M14 | `redact` borraba `starter_broker_key` antes de que L1 la usara | Corregido: objeto `Secrets` en memoria, solo para `bench.py` |
| B-M15 | = S-M6 | Ver S-M6 |
| B-M16 | = S-M8 | Ver S-M8 |
| B-M17 | Una forma rara en la relectura del Gate daba STOP de equipo | Corregido: `refused:G10.shape` y dominio bloqueado; STOP solo por transporte, diario o aserción |
| B-M18 | Criterio 56/56 imposible con ofertas ya cerradas | Corregido: criterio en tres partes (INV-05) |
| B-M19 | Ficheros con dos dueños | Corregido: fixtures del harvest → M0; replay → M17; `test_bots.py` → M6b; plantillas solo en M4b; perfiles numéricos y `days_sign` en `config/plan.json` (M8); formas torcidas en un fichero de M4a que usan test y bot |
| B-M20 | Sin procedimiento para meter código nuevo con el live en marcha | Corregido: actualización en caliente en el runbook; M18 parte 2 el sábado a las 23:15 |
| B-M21 | Ficheros sin tratar en la limpieza | Corregido: `.env.night`, `.pytest_cache`, `harvest.py`, los dos documentos nuevos a git, dueños de las fusiones, `SystemExit` tras `from __future__` |
| B-M22 | Criterios de test que dependían de bots aleatorios | Corregido: invariantes condicionales; comparaciones de rendimiento a `report`; nuevos `test_cli.py`, `test_bots.py` y la prueba de `api/index.py` |

### 14.3 Menores corregidos
STOP con `--flatten`; tipo de sobre desconocido sin excepción; cola rota del diario; `server_values` compartidos entre táctica y Gate; GET por lista blanca con `fullmatch`; lista blanca de campos en el sensor; una sola regla de caducidad (`≥ tick + 1`); RET-08 con el patrón de t03; escenario P del reloj; vía rápida en el primer tick; ascenso lento en duelos; `from __future__` y salida UTF-8; redacción de INV-06; mapa `LIMIT_KEYS` con test.

### 14.4 Lo que queda abierto (con su experimento)
- Si el rival puede mandar dos mensajes en un tick o si un POST llega tras el cambio de tick (E16).
- Si el servidor cuenta contra nuestros hilos los que abre un rival (E17).
- Si los regalos de la Abuela se repiten en la ronda 2 (se trata como riesgo de entrega mientras haya un hilo con ella).
- Si `duel_accept` comparte la aceptación del tick (E9; se supone que sí).

---

## 15. Cambios desde el sábado 03:30 (código publicado: rama `release`; incluye `night-build` `0daffe5` y los cambios del domingo en vivo)

- **Domingo (en vivo):** CHA-11 en `extra_needs` sube a 225, para que J6 pueda comprar la épica a un equipo; el hilo con los Pícaros sigue en el límite de su perfil, 170 (`8ba8399`). Don Ernesto (banco) es dealer de compra para CHA-12: `extra_needs` ≤ 470, perfil con ancla 380 y paso 5, plantilla `banco_buy` (`1ef5a66`). `DAILY_SURPRISE_STOP` pasa de −5 a −60 (`9a871e2`). LAV-07 como portadora del huevo de El Chato (`25fe09a`), retirada al llegar el huevo (`8de6c59`).
- **§2.1 (M0):** `contracts.py` recibió las entradas tardías D1–D3 con valores por defecto: `ARGS["accept"]["venue"]` (D2: aceptar en venues de otros equipos con `RIVAL_VENUE_MIN_GAIN` / `RIVAL_TOP_N`), `ARGS["list_offer"]["want_ref"]` y side `"swap"` (D1), `World.boards` / `venues` / `leaderboard`, `DOWN_SOURCES` ampliado y `expiry_units()` (D3). Publicamos solo en El Rastro: la frase «el venue siempre es rastro» de §2.1 vale solo para `list_offer`.

Las secciones 0–14 son el contrato congelado de la noche del viernes. Aquí se recoge en qué difiere el código; si algo choca, manda el código y esta lista. Las líneas de §3 (INV-03, INV-12) y §4 (G50, G51, día de la higiene) ya están reescritas con el código final.

- **§2.2:** `GET_ALLOWLIST` vive en `agent/contracts.py:136`, no en `transport.py`, y admite `venues/[a-z0-9_-]+/offers` (D2), no solo `venues/rastro/offers`. `/api/broker/*` no está: `bench_rec.py` lee el libro con su propio GET, fuera del arnés.
- **Presupuesto de peticiones:** runner 3,5 req/s, ráfaga 8, 2 fichas reservadas (`runner.RUNNER_RATE`); paneles 1 req/s (`client.PANEL_RATE`). La relectura de mitad de tick para aceptar duelos es la reducida (clock, me, me/offers, duels) y su duración va a la fila `tick` (`late_read_s`).
- **§2.5, `talk.TEMPLATES`:** 11 plantillas (`abuela_buy`, `abuela_sell`, `chato_buy`, `chato_sell`, `pilar_sell`, `picaros_buy`, `picaros_sell`, `banco_buy`, `banco_sell`, `duel`, `duel_days`). `EGG_LINES` = {chato_buy 2, chato_sell 1, abuela_buy 2, abuela_sell 3, pilar_sell 1, banco_sell 2, picaros_sell 1}: cuántas variantes del final de cada plantilla son huevos que solo se mandan a mano (`dealers._variant` no las rota; cada línea pasa G60).
- **§2.5, `guards.Cfg`:** además de lo listado, `RIVAL_TOP_N`, `RIVAL_VENUE_MIN_GAIN`, `GRANT_LOOKAHEAD_TICKS`, `DAYS_SIGN` (sin uso), `DAYS_WEIGHT_FALLBACK`, `ABUELA_DEALS_HOUR_MAX`, `TICKS_PER_GAME_HOUR`, `MIN_EXPIRES` y `MAX_EXPIRES`. Bloqueos de dealer (`_closed_thread_blocks`): `cooloff` hasta su `until_tick`; `persona_quota`, `persona_budget` y `sold_out` hasta el final de la hora de juego en curso (`2512ce4`).
- **§2.1, `PlanCfg` / `config/plan.json`:** añade `duels {anchor 0,62, slow_cap 0,85, acc_late 2, e8_ticks 0, days_weight_fallback 1,0}`, `closer.freeze_at` 8, `closer.endgame_min_before_close` 35, `closer.endgame_hours` (respaldo), `day_end_min_before_close` 5, `day_end_hours` (solo `sun`, respaldo), `grant_lookahead_ticks` 12, `dup_min_price` {RET 30, CHA 30, LAT 18}, `resupply_min` 999 (J13 apagada), `endgame_buy_any`, `hand_sales`, `extra_needs` con `min_round`, `profiles.*.fallback_dealer` y el perfil genérico `rare` (respaldo de El Chato). Solo valen como perfil los dealers `abuela`, `chato`, `picaros` y `banco` (banco solo para comprar CHA-12, `1ef5a66`). Las ventas a Pilar y al banco siguen siendo a mano. `days_sign` sigue en el fichero porque `PlanCfg` la declara, pero no se usa.
- **Días en duelos (G50/G51):** el sensor deriva `days_sign` de `days_meaning` y solo deja el signo en el World. El signo sale de `talk.days_sign_of`: `days_sign` del sensor, si no `days_meaning`, si no el papel (`ROLE_DAYS_SIGN`: comprador −1, vendedor +1). `talk.checked_sign`: un signo leído que contradice al papel da −1. El runner deja una alarma por duelo con el texto ilegible o en conflicto. Con días, devolver al rival su propio par (precio, días) en pie no cuenta como retroceso (G50).
- **Fin del día y endgame (`pages.effective_plan`, cada tick en el runner):** cierre = el antes de `clock.closes` (pared: t + (closes − ahora)/3600, solo con puertas abiertas y reloj en marcha), del `day_closes` de hoy y de un `end_round` del calendario vivo; las entradas cuyo propio `wall` ya pasó no cuentan. Cierre de puestos = primera hora con ≥ 3 entradas `persona enabled:false` (`STALLS_MIN_PERSONAS`), recordada en memoria y en `state/day_times.json` (válido < 6 h). Fin de dealers = mín(cierre, puestos) − `day_end_min_before_close`; endgame = cierre − `closer.endgame_min_before_close`. Fila `param day_times` al arrancar y en cada cambio de más de 1 min. `pages.today` ya no adivina el día por la hora. `bazaar.py clockcheck` imprime lo mismo y la pista de escenario A/B/C.
- **Runner (`choose`):** con más de 4 duelos vivos (`MAX_LIVE_DUELS_FOR_THREADS`), ningún `open_thread` de una táctica; los manuales pasan. Cada descarte lleva código (`R04.*`): fila `dropped` para órdenes manuales y recuento en la fila `tick`. Una aceptación de táctica que gastaría el último cupo se retiene un tick (`R04.duel_slot`) si un duelo cerca de su deadline tiene una oferta rival dentro del límite; nunca la de `manual` ni la del `closer`. Los duelos que se quedan sin cupo de aceptación reciben un mensaje con el par del rival. En `live`, las intenciones de tácticas en pausa o sin armar solo dejan `would`, después de la ventana tardía, y no gastan cupos ni caja.
- **Libro (`build_book`):** una fila `accepted_unsettled` deja de reservar caja en cuanto el World pasa de su tick (el servidor liquida en T+1). G19 no cancela ventas mientras falte el catálogo o el valorador.
- **Tácticas:** `pages.need_limit` (el tope de un Need también mira el límite del dealer de respaldo); `extra_needs` solo con su set publicado, detrás de las cartas de página y desde `min_round`, y con el hilo topado en `cash_free` menos lo que la puja del closer necesita a su precio de endgame (`dealers.closer_reserve`, `0daffe5`); el closer no puja mientras haya riesgo de entrega; J13 nunca en el endgame; `hand_sales` fuera de J5, de las ventas a pujas y de los intercambios hasta el fin de dealers; un intercambio D1 solo da lo que daría `_spares`; las épicas nunca son sobrantes.
- **Escrituras fuera de la Gate:** el contrato no tiene KIND para denuncias, venues ni broker. Las excepciones manuales con el OK de Jorge son regla de CLAUDE.md, no del arnés. Sábado: `PATCH /api/venues/v18`, `POST /api/broker/announce` y 9 `POST /api/flags`. Domingo: denuncias (`flag_one.py`), anuncios (`announce_stall.py` y un anunciador cada 10 min) y la apertura del venue board v28 con un broker del operador. Ninguno de esos scripts está en el repo, mira STOP ni escribe en el diario: se apuntan en `docs/history/handoffs/HANDOFF-domingo.md`, y la traza del venue está en `data/market-test/`. L4 (`open_venue` como KIND) no se construyó. INV-01 e INV-20 siguen valiendo para todo lo que sale por la Gate.
- **Scripts manuales de la raíz** (fuera de `agent/`; leen solo por GET y escriben solo con `bazaar.py do ... --live`, por la Gate): `ladder_sell.py` (escalera de precios con un dealer; manda el siguiente precio solo cuando el anterior está en el hilo y el dealer ha contestado; se rinde a los 40 ticks), `egg_carrier.py` (lo mismo, con las variantes de huevo primero). Solo lectura: `flag_candidates.py` (denuncias de nivel A) y `announce_candidates.py` (parejas para anuncios en v18, sin clave). Simulador: `python3 -m sim.sunday C|A|B`.
- **CLI:** `status` avisa `STALE?` si un runner tiene el candado y la última fila `tick` tiene más de 90 s, y lista las últimas filas `dropped` y `param`. Un `do` sin `--live` junto a un runner vivo se rechaza.
- **Sin conectar:** `pages.protect_sets` (solo existe la definición), `Calibrator.recheck`, `duels.e16_settled` y el grabador L1 dentro del runner (lo hace `bench_rec.py` aparte).
- **Fallos conocidos que quedan:** [plan-domingo.md](history/plan-domingo.md) §1.3.
