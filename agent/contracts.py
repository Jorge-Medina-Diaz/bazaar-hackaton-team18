"""M0 contracts: frozen types, paths and argument schemas shared by every module of the harness.

FROZEN. Other modules code against this file exactly (docs/harness-spec.md §2.1 plus the late inputs D1-D4).
Do not edit it to suit one module: work around it and report it to the lead.

NOTES (M0, night build)
- Late inputs adopted here: World.boards / World.venues (D2), ARGS["accept"]["venue"] (D2),
  ARGS["list_offer"]["want_ref"] and side "swap" (D1), RIVAL_VENUE_MIN_GAIN / RIVAL_TOP_N defaults (D2; the
  live values belong in guards.Cfg, M4a), GET_ALLOWLIST with /api/venues/<vid>/offers (D2; transport M1 should
  import it from here), expiry_units() for D3. open_venue stays out of KINDS (D4).
- Additions beyond the letter of §2.1 (all backward compatible, all with defaults):
  World.leaderboard (team ids best first; () = unknown, so the D2 rival-venue rule must fail closed),
  make_intent also checks enumerations (kind, tactic, source, side, venue) and a few cross-field rules
  (swap => price 0 and an asset to hand over; buy => nothing handed over), Secrets hides its value in repr,
  and Paths.at() with no root under BAZAAR_TEST=1 returns a per-process temporary root (INV-21, fail closed).
- Not done tonight: no runtime validation of World / Book contents (they are built by M7 / M4a).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional, TypedDict

PROD_URL = "https://bazaar.causaprima.ai"
TEAM = "t18"
RASTRO = "rastro"                       # the only venue we publish on (D2)

# --------------------------------------------------------------------------------------------- paths

_TEST_ROOT: Optional[Path] = None


def _test_root() -> Path:
    global _TEST_ROOT
    if _TEST_ROOT is None:
        _TEST_ROOT = Path(tempfile.mkdtemp(prefix="t18-test-root-")).resolve()
    return _TEST_ROOT


@dataclass(frozen=True)
class Paths:
    root: Path

    @classmethod
    def at(cls, root: "str | Path | None" = None) -> "Paths":
        """Paths rooted at `root`; by default the repo root (parent of agent/).

        Fail closed for tests (INV-21): with BAZAAR_TEST=1 and no explicit root, a per-process temporary
        directory is used instead of the repo, so no test can touch the repo's logs/run or state/.
        """
        if root is None:
            if os.environ.get("BAZAAR_TEST") == "1":
                return cls(_test_root())
            return cls(Path(__file__).resolve().parents[1])
        return cls(Path(root).resolve())

    @property
    def run_dir(self) -> Path:
        return self.root / "logs" / "run"

    @property
    def journal(self) -> Path:
        return self.root / "logs" / "run" / "journal.jsonl"

    @property
    def untrusted(self) -> Path:
        return self.root / "logs" / "run" / "untrusted.jsonl"

    @property
    def snaps(self) -> Path:
        return self.root / "logs" / "run" / "snap"

    @property
    def state(self) -> Path:
        return self.root / "state"

    @property
    def inbox(self) -> Path:
        return self.root / "state" / "inbox"

    @property
    def lock(self) -> Path:
        return self.root / "state" / "writer.lock"

    @property
    def baseline(self) -> Path:
        return self.root / "state" / "baseline.json"

    @property
    def armed(self) -> Path:
        return self.root / "state" / "armed.json"

    @property
    def pauses(self) -> Path:
        return self.root / "state" / "pauses.json"

    @property
    def frozen(self) -> Path:
        return self.root / "state" / "frozen.json"

    @property
    def selftest(self) -> Path:
        return self.root / "state" / "selftest.json"

    @property
    def stop_names(self) -> tuple:
        # a file in root named STOP or stop, with or without any extension (STOP.txt, stop.md ...)
        return ("STOP", "stop")


# ------------------------------------------------------------------------------------- vocabularies

KINDS = ("accept", "list_offer", "cancel", "open_thread", "say", "close_thread",
         "open_pack", "duel_say", "duel_accept")                     # D4: no open_venue
TACTICS = ("hygiene", "dealers", "rastro", "closer", "duels", "manual")
BUY_TACTICS = frozenset({"dealers", "rastro", "closer"})
TALK_KINDS = frozenset({"open_thread", "say", "duel_say", "duel_accept"})   # + accept with source == "dealer"

# D2 defaults; the live knobs are guards.Cfg.RIVAL_VENUE_MIN_GAIN / RIVAL_TOP_N (M4a).
RIVAL_VENUE_MIN_GAIN = 10.0
RIVAL_TOP_N = 5

# Sources the sensor may mark as down (World.down).
DOWN_SOURCES = frozenset({"clock", "me", "me/offers", "me/threads", "threads", "board", "boards", "venues",
                          "leaderboard", "duels", "feed", "values", "catalog", "schedule"})

VENUE_RE = r"[a-z0-9_-]{1,32}"
# GET allowlist (re.fullmatch). D2 adds /api/venues/<vid>/offers. Transport (M1) should import this one.
GET_ALLOWLIST = (r"/api/(clock|schedule|catalog|me|me/value|me/offers|me/threads|threads/\d+|venues"
                 r"|venues/[a-z0-9_-]+/offers|duels|feed|dealers|levels|cards/\d+|leaderboard)")


# --------------------------------------------------------------------------------------- prediction

@dataclass(frozen=True)
class Prediction:            # effect IF this write ends in a settlement
    neg_lo: float            # Δneg with the cap of 50
    neg_hi: float            # Δneg without cap
    ladder: str              # "0" | ">=0"
    cash: int                # Δcash on settlement (signed)
    duel: Optional[float] = None
    model: str = ""          # "P-03" | "P-04" | "P-08" | "U-01" | "none" | ...
# Semantics per kind: accept/list_offer -> predict_team (list_offer with we_accept=False);
# say and dealer accept -> predict_dealer(dv, p); duel_say -> predict_duel with rounds+1;
# duel_accept -> predict_duel with current rounds; cancel/close_thread/open_thread/open_pack -> predict_none.
# Swaps (D1): V(received) - V(given) - fee, model "D1".

LADDERS = frozenset({"0", ">=0"})


# ------------------------------------------------------------------------------------------- intent

@dataclass(frozen=True, eq=False)       # compared and indexed by intent_id, never by value
class Intent:
    kind: str
    tactic: str
    args: Mapping[str, Any]             # MappingProxyType, schema ARGS[kind]
    reason: str
    expected_effect: str
    prediction: Prediction
    priority: int = 0
    experiment: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.args, MappingProxyType):
            object.__setattr__(self, "args", MappingProxyType(dict(self.args)))


NONE = type(None)
ARGS: Mapping[str, Mapping[str, Any]] = MappingProxyType({
    "accept":      MappingProxyType({"offer_id": int, "source": str, "ref": str, "side": str, "price": int,
                                     "thread_id": (int, NONE), "give_asset": (int, NONE), "fingerprint": str,
                                     "resupply": bool, "venue": str}),
    "list_offer":  MappingProxyType({"side": str, "ref": str, "asset_id": (int, NONE), "price": int,
                                     "expires_ticks": int, "closer": bool, "want_ref": (str, NONE)}),
    "cancel":      MappingProxyType({"offer_id": int, "ref": (str, NONE)}),
    "open_thread": MappingProxyType({"dealer": str, "side": str, "ref": str, "asset_ids": tuple, "limit": int}),
    "say":         MappingProxyType({"thread_id": int, "ref": str, "price": int, "template": str, "variant": int}),
    "close_thread": MappingProxyType({"thread_id": int, "ref": (str, NONE)}),
    "open_pack":   MappingProxyType({"asset_id": int}),
    "duel_say":    MappingProxyType({"duel_id": int, "price": int, "days": (int, NONE), "template": str,
                                     "variant": int}),
    "duel_accept": MappingProxyType({"duel_id": int, "fingerprint": str}),
})
# Enumerations checked by make_intent.
#  accept:     source in {"team","dealer"}; side in {"buy","sell","swap"}; venue = venue id ("rastro" or another
#              team's venue, D2); ref = the card we RECEIVE (buy/swap) or hand over (sell);
#              give_asset = our asset handed over (sell into a bid, or swap); swap => price 0 and give_asset set.
#  list_offer: side in {"sell","bid","swap"}; always published on "rastro" (the Gate sets the venue).
#              sell: asset_id = asset we give, ref its card, want cash `price`;
#              bid:  asset_id None, ref = card we want, give cash `price`;
#              swap (D1): asset_id = asset we give (ref its card), want_ref = card we want, price 0.
#              expires_ticks = desired lifetime in game ticks (the Gate converts with expiry_units, D3).
#  open_thread: side in {"buy","sell"}.
ENUMS: Mapping[str, Mapping[str, frozenset]] = MappingProxyType({
    "accept": MappingProxyType({"source": frozenset({"team", "dealer"}),
                                "side": frozenset({"buy", "sell", "swap"})}),
    "list_offer": MappingProxyType({"side": frozenset({"sell", "bid", "swap"})}),
    "open_thread": MappingProxyType({"side": frozenset({"buy", "sell"})}),
})

_INT_FIELDS_NON_NEGATIVE = frozenset({"price", "limit", "offer_id", "thread_id", "give_asset", "asset_id",
                                      "duel_id", "variant"})   # days may be signed (days_sign)


def _type_ok(value: Any, expected: Any) -> bool:
    allowed = expected if isinstance(expected, tuple) else (expected,)
    return type(value) in allowed      # exact type: bool is not int, int subclasses are not int


def _num_ok(x: Any) -> bool:
    return type(x) in (int, float) and math.isfinite(x)


def _check_prediction(p: Any) -> None:
    if type(p) is not Prediction:
        raise ValueError("prediction must be a Prediction")
    if not (_num_ok(p.neg_lo) and _num_ok(p.neg_hi)):
        raise ValueError("prediction.neg_lo/neg_hi must be finite numbers")
    if p.ladder not in LADDERS:
        raise ValueError(f"prediction.ladder must be one of {sorted(LADDERS)}")
    if type(p.cash) is not int:
        raise ValueError("prediction.cash must be int")
    if p.duel is not None and not _num_ok(p.duel):
        raise ValueError("prediction.duel must be a finite number or None")
    if type(p.model) is not str:
        raise ValueError("prediction.model must be str")


def _check_args(kind: str, args: Mapping[str, Any]) -> dict:
    schema = ARGS[kind]
    a = dict(args)
    if set(a) != set(schema):
        missing = sorted(set(schema) - set(a))
        extra = sorted(set(a) - set(schema))
        raise ValueError(f"{kind}: args keys mismatch (missing={missing}, extra={extra})")
    for k, t in schema.items():
        if not _type_ok(a[k], t):
            raise ValueError(f"{kind}.{k}: expected {t}, got {type(a[k]).__name__}")
        if k in _INT_FIELDS_NON_NEGATIVE and type(a[k]) is int and a[k] < 0:
            raise ValueError(f"{kind}.{k}: must be >= 0")
    for k, allowed in ENUMS.get(kind, {}).items():
        if a[k] not in allowed:
            raise ValueError(f"{kind}.{k}: {a[k]!r} not in {sorted(allowed)}")
    if kind == "open_thread":
        if not all(type(x) is int and x >= 0 for x in a["asset_ids"]):
            raise ValueError("open_thread.asset_ids must be a tuple of non-negative int")
    if kind == "accept":
        if not re.fullmatch(VENUE_RE, a["venue"]):
            raise ValueError("accept.venue: invalid venue id")
        if a["side"] == "swap" and (a["price"] != 0 or a["give_asset"] is None or a["source"] != "team"):
            raise ValueError("accept swap: price 0, give_asset set and source 'team'")
        if a["side"] == "buy" and a["give_asset"] is not None:
            raise ValueError("accept buy: give_asset must be None")
    if kind == "list_offer":
        if a["expires_ticks"] < 1:
            raise ValueError("list_offer.expires_ticks must be >= 1")
        side = a["side"]
        if side == "swap":
            if a["price"] != 0 or a["asset_id"] is None or a["want_ref"] is None or a["want_ref"] == a["ref"]:
                raise ValueError("list_offer swap: price 0, asset_id set, want_ref set and != ref")
        elif a["want_ref"] is not None:
            raise ValueError("list_offer: want_ref only for side 'swap'")
        if side == "sell" and a["asset_id"] is None:
            raise ValueError("list_offer sell: asset_id required")
        if side == "bid" and a["asset_id"] is not None:
            raise ValueError("list_offer bid: asset_id must be None")
    return a


def make_intent(kind: str, tactic: str, args: Mapping[str, Any], reason: str, expected_effect: str,
                prediction: Prediction, priority: int = 0, experiment: Optional[str] = None) -> Intent:
    """Validated Intent. ValueError if kind, tactic, the exact keys or the exact types do not fit."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    if tactic not in TACTICS:
        raise ValueError(f"unknown tactic {tactic!r}")
    if not isinstance(args, Mapping):
        raise ValueError("args must be a mapping")
    a = _check_args(kind, args)
    if type(reason) is not str or type(expected_effect) is not str:
        raise ValueError("reason and expected_effect must be str")
    _check_prediction(prediction)
    if type(priority) is not int:
        raise ValueError("priority must be int")
    if experiment is not None and type(experiment) is not str:
        raise ValueError("experiment must be str or None")
    return Intent(kind, tactic, MappingProxyType(a), reason, expected_effect, prediction, priority, experiment)


def intent_id(tick: int, it: Intent) -> str:
    raw = f"{tick}|{it.tactic}|{it.kind}|{json.dumps(dict(it.args), sort_keys=True)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


_DOMAIN_KEYS = (("offer_id", "offer"), ("thread_id", "thread"), ("dealer", "dealer"), ("duel_id", "duel"),
                ("asset_id", "asset"), ("give_asset", "asset"), ("ref", "ref"), ("want_ref", "ref"))


def domains_of(it: Intent) -> frozenset:
    """{"offer:<id>", "thread:<id>", "dealer:<id>", "duel:<id>", "asset:<id>", "ref:<REF>"} from the args."""
    out = set()
    a = it.args
    for key, prefix in _DOMAIN_KEYS:
        v = a.get(key)
        if v is not None:
            out.add(f"{prefix}:{v}")
    for aid in a.get("asset_ids") or ():
        out.add(f"asset:{aid}")
    return frozenset(out)


def expiry_units(desired_ticks: int, tick_seconds: float) -> int:
    """D3: the server counts expires_in_ticks in 15-second units (measured).

    requested = ceil(desired_ticks * tick_seconds / 15), at least 1. ValueError on nonsense input.
    """
    if type(desired_ticks) is not int or desired_ticks < 1:
        raise ValueError("desired_ticks must be an int >= 1")
    if not _num_ok(tick_seconds) or tick_seconds <= 0:
        raise ValueError("tick_seconds must be a positive number")
    return max(1, math.ceil(desired_ticks * float(tick_seconds) / 15.0 - 1e-9))


# ------------------------------------------------------------------------------------------- limits

LIMIT_KEYS = MappingProxyType({
    "accepts": "accepts_per_team_per_tick", "messages": "messages_per_side_per_tick",
    "threads": "max_open_threads_per_team", "open_offers": "max_open_offers_per_team",
    "listings": "offers_per_team_per_tick"})                                     # [measured] clock.json


@dataclass(frozen=True)
class Limits:
    accepts: int
    messages: int
    threads: int
    open_offers: int
    listings: int

    @staticmethod
    def from_clock(clock: Mapping, prev: "Limits | None") -> "Limits":
        """Read clock["limits"][LIMIT_KEYS[k]]; a missing / non-int / negative value -> min(prev, FRIDAY)."""
        raw = clock.get("limits") if isinstance(clock, Mapping) else None
        if not isinstance(raw, Mapping):
            raw = {}
        vals = {}
        for k, server_key in LIMIT_KEYS.items():
            v = raw.get(server_key)
            if type(v) is int and v >= 0:
                vals[k] = v
            else:
                fallback = getattr(FRIDAY, k)
                vals[k] = min(getattr(prev, k), fallback) if prev is not None else fallback
        return Limits(**vals)


FRIDAY = Limits(1, 1, 6, 30, 12)


# -------------------------------------------------------------------------------------------- world

@dataclass(frozen=True)
class World:
    tick: int
    t_hours: float
    round: Optional[int]
    tick_seconds: float
    tick_deadline: float              # monotonic of the clock read + next_tick_in - TICK_MARGIN_S
    clock: Mapping
    limits: Limits
    reading: str                      # "N" | "M" | "C" | "P" | "?"
    me: Mapping                       # allowlisted fields; no keys, no text
    my_offers: tuple                  # tuple[Mapping, ...]: maker == "t18" (includes "queued")
    offers_to_us: tuple               # tuple[Mapping, ...]: to == "t18", maker != "t18" (any venue)
    board: tuple                      # tuple[Mapping, ...]: El Rastro, open, structured fields
    own_pseudonym: Optional[str]      # board maker of any offer whose id is in my_offers
    threads: Mapping                  # Mapping[int, Mapping]: dealer threads opened by us; messages without text
    foreign_threads: tuple            # tuple[int, ...]: threads others opened with us
    duels: tuple                      # tuple[Mapping, ...]: live duels; messages without text
    catalog: Mapping
    schedule: Mapping
    released_sets: frozenset
    feed_new: tuple                   # tuple[Mapping, ...], no text
    server_values: Mapping            # Mapping[str, float]: value?card cached per inventory version
    down: frozenset                   # frozenset[str] subset of DOWN_SOURCES
    # --- late inputs (D2); defaults keep older constructions valid ---
    boards: Mapping = field(default_factory=lambda: MappingProxyType({}))
    #   venue id -> tuple of open offers (structured fields only), every open venue incl. "rastro"
    venues: tuple = ()
    #   tuple[Mapping, ...] with keys id, owner, fee_bps, fee_per_card, status
    leaderboard: tuple = ()
    #   tuple[str, ...] team ids, best first. () means unknown: the D2 rival-venue rule must then refuse.


@dataclass(frozen=True, repr=False)
class Secrets:                        # never in World, journal, snapshots or console
    starter_broker_key: Optional[str] = None

    def __repr__(self) -> str:
        return f"Secrets(starter_broker_key={'<redacted>' if self.starter_broker_key else None})"


@dataclass(frozen=True)
class Need:
    set: str
    ref: str
    source: str                       # "abuela" | "chato" | "team"
    max_price: int
    closer: bool


@dataclass(frozen=True)
class Book:                           # built by guards.build_book; updated by guards.apply
    cash: int
    cash_free: int
    held: Mapping                     # Mapping[str, int]
    listed: Mapping                   # Mapping[str, int]
    pending_out: Mapping              # Mapping[str, int]
    pending_in: Mapping               # Mapping[str, int]
    projected: Mapping                # held + pending_in + buy threads with a standing price + own bids
    keep: Mapping                     # Mapping[str, int]
    listed_assets: frozenset          # frozenset[int]
    own_offer_ids: frozenset          # frozenset[int]
    own_bids: Mapping                 # ref -> offer_id
    bid_price: Mapping                # Mapping[int, int]
    bid_band: Mapping                 # Mapping[int, float]: G19 band per offer (baseline or 2/20)
    paths: Mapping                    # Mapping[str, int]
    thread_limit: Mapping             # Mapping[int, int]
    thread_prices: Mapping            # Mapping[int, tuple[int, ...]]
    thread_ref: Mapping               # Mapping[int, str]
    thread_by_dealer: Mapping         # Mapping[str, int]
    dealer_block: Mapping             # dealer -> until_tick (cooloff, persona_quota)
    dealer_deals_hour: Mapping        # Mapping[str, int]
    packs: tuple                      # tuple[int, ...]
    needs: Mapping                    # Mapping[str, Need]
    frozen_closer: Mapping            # set -> ref
    protect_sets: frozenset           # frozenset[str]
    delivery_risk: bool               # INV-23
    recent_rastro: Mapping            # ref -> (side, tick) of our settlements on El Rastro
    unknown_domains: frozenset        # frozenset[str]
    valuation_ok: bool


@dataclass(frozen=True)
class Verdict:
    ok: bool
    code: str
    detail: str = ""


OUTCOME_STATUSES = frozenset({"sent", "would", "refused", "deferred", "unknown"})


@dataclass(frozen=True)
class Outcome:
    intent_id: str
    status: str                       # "sent" | "would" | "refused" | "deferred" | "unknown"
    code: Optional[str] = None
    response: Optional[Mapping] = None   # redacted, <= 2 KB


class PlanCfg(TypedDict):
    page_sets: list                   # ["RET"] on Saturday; ["RET","CHA"] on Sunday
    protect_sets: list                # ["SAL","RET","CHA","LAT"]; LAT leaves when given up (t205)
    startup_cancels: list             # [2463, 1652]
    baseline_bands: dict              # {"2503": 0.0, "2504": 0.0}
    dealer_max: dict                  # ref -> cap
    profiles: dict                    # ref/rarity -> {dealer, anchor, step, limit, fallback_after}
    closer: dict                      # {"accept_min": 20, "default_minus": 50, "compete_minus": 20, "endgame_hours": {...}}
    resupply_min: float               # 15
    dup_min_price: dict               # {"RET": 30, "CHA": 30}
    days_sign: Optional[int]
    day_end_hours: dict               # dealer-thread close (22:55 Saturday)
    grant_lookahead_ticks: int        # 3
