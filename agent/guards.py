"""M4a guards-core: Book (build/apply), guards G01-G07, G10-G16, G20-G23, G33, G40, the SOURCES table,
canonical offer shapes and fingerprints (docs/harness-spec.md §2.5, §3, §4; late inputs D1, D2).

PURE except build_book, which reads the journal object it is handed (no file or network I/O here).

NOTES (M4a, night build)
- G01 (STOP file) and the "result already exists for iid" half of G05 need I/O: the Gate does them (§2.6
  steps 1-2). check() does the unknown-domain half of G05 and everything else that is pure.
- G07 here is ONE-SIDED: a team intent may not claim more neg than the guard computes (+0.01). The exact
  recomputation (trip) is the Gate's step 5 with valuation.predict_*; doing it twice risks false trips.
- `fresh` for a team accept: {"tick": <tick of the re-read /api/clock>, "offer": <re-read offer>}
  ("clock_tick" is accepted as an alias of "tick"). A bare offer (no clock tick) fails closed: G03.stale.
  For dealer accepts / duel_accept `fresh` is passed through to agent.talk unchanged.
- Book.packs holds pack TYPES (e.g. "sobre_barrio"), not asset ids: every caller (talk, hygiene, dealers)
  passes book.packs straight to Valuer.delta_add/delta_remove, which takes types. Pack asset ids come
  from world.me (G40 checks args.asset_id there). Contract comment says tuple[int]: deviation reported.
- Book.needs is {} after build_book: needs are planned after begin_tick (pages.plan). The runner/Gate can
  set them with dataclasses.replace(book, needs=...).
- Fees: accept on venue V uses that venue's fee_bps/fee_per_card from World.venues; El Rastro falls back
  to R-01 (500 bps + 1 per card) when it is not listed. A swap counts 2 cards (conservative). apply()
  only knows the intent, so it books the El Rastro fee; the RESERVE covers the difference.
- apply() cannot know the ref of the asset handed over in an accepted swap (args carry only give_asset), so
  it books the asset in listed_assets; G13 uses free(book, ref, world), which also counts our assets of that
  ref already in listed_assets. Talk's own _free does not (it never hands over swap assets).
- Journal rows follow M2: intent rows are kind "intent" with the intent's kind in "intent_kind".
- Swaps (D1): accept side "swap" = maker gives exactly one card (asset or type), wants exactly one card
  (type/cards, or exactly our give_asset), no cash anywhere. list_offer side "swap" = we give asset_id
  (ref), want want_ref. Value: V(received) - V(given) - fee via Valuer.delta_swap semantics.
- Rival venues (D2): accept on a venue != "rastro" needs the venue open in World.venues, owner != t18
  (INV-20), a known leaderboard with the owner outside the top RIVAL_TOP_N, and neg_lo >= RIVAL_VENUE_MIN_GAIN.
- Not done tonight: dealer_block / thread_limit / recent_rastro are rebuilt from the journal best effort
  (the M2 row shapes were not final; dealer_block also comes from our threads' closed_reason / until_tick, see
  _closed_thread_blocks); delivery_risk does not yet look at "new dealer level announced";
  dup_min_price (RET/CHA >= 30) is a tactic rule, not a guard here.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Mapping, Optional

from agent.contracts import (ARGS, KINDS, RASTRO, TALK_KINDS, TEAM, Book, Intent, Outcome, Verdict,
                             domains_of, make_intent)
from agent.offer_safety import offer_ok
from agent.valuation import fee as _fee

REF_RE = re.compile(r"[A-Z]{3}-\d{2}")
MAX_PRICE = 1_000_000
OPEN_STATUSES = frozenset({"open", "queued"})
OK = Verdict(True, "ok")


# ------------------------------------------------------------------------------------------- config

@dataclass(frozen=True)
class Cfg:
    MIN_GAIN_TEAM: float = 3.0
    MIN_GAIN_MAKER: float = 2.0
    DEALER_MARGIN: float = 1.0
    VAL_TOL: float = 0.11
    RESERVE: int = 10
    NEG_CAP: float = 50.0
    CLOSER_ACCEPT_MIN: float = 20.0
    RESUPPLY_MIN: float = 15.0
    LISTINGS_PER_TICK: int = 6
    OPEN_OFFERS_MARGIN: int = 4
    THREADS_MARGIN: int = 1
    DUEL_ACCEPT_SHARED: bool = True
    TICK_MARGIN_S: float = 2.0
    ALLOW_DEALER_CLOSE: frozenset = frozenset({"LAT"})
    MAX_PRICE_X_BOOK: float = 4.0
    ROUND_TRIP_TICKS: int = 60
    EXPIRY_FACTOR: Optional[float] = None
    # late inputs (D2) and knobs agent.talk reads with getattr
    RIVAL_VENUE_MIN_GAIN: float = 10.0
    RIVAL_TOP_N: int = 5
    GRANT_LOOKAHEAD_TICKS: int = 3
    DAYS_SIGN: Optional[int] = None
    DAYS_WEIGHT_FALLBACK: Optional[float] = None   # plan duels.days_weight_fallback (null server weight)
    ABUELA_DEALS_HOUR_MAX: int = 6
    TICKS_PER_GAME_HOUR: int = 60          # fallback only (tick_seconds unknown): see ticks_per_hour()
    MIN_EXPIRES: int = 4
    MAX_EXPIRES: int = 240


@dataclass
class Counters:
    tick: int
    accepts: int = 0
    listings: int = 0
    threads_opened: int = 0
    offers_opened: int = 0
    msgs: set = field(default_factory=set)


_TEAM_SRC = frozenset({"clock", "me", "me/offers", "me/threads", "board"})
_DEALER_SRC = frozenset({"clock", "me", "me/offers", "me/threads", "threads"})
SOURCES: Mapping[str, frozenset] = MappingProxyType({
    "cancel": frozenset({"clock", "me/offers"}),
    "close_thread": frozenset({"clock", "me/threads"}),
    "list_offer": _TEAM_SRC,
    "accept": _TEAM_SRC,                                         # team accept on El Rastro
    "accept_venue": _TEAM_SRC | {"boards", "venues", "leaderboard"},   # D2: team accept on another venue
    "accept_dealer": _DEALER_SRC,
    "open_thread": _DEALER_SRC,
    "say": _DEALER_SRC,
    "open_pack": frozenset({"clock", "me", "me/threads"}),
    "duel_say": frozenset({"clock", "duels"}),
    "duel_accept": frozenset({"clock", "duels"}),
})
_NO_VALUE_KINDS = frozenset({"cancel", "close_thread", "open_pack", "duel_say", "duel_accept"})
_PACK_OK_KINDS = frozenset({"open_pack", "cancel", "close_thread", "duel_say", "duel_accept"})


def source_key(intent: Intent) -> str:
    a = intent.args
    if intent.kind == "accept":
        if a.get("source") == "dealer":
            return "accept_dealer"
        return "accept" if a.get("venue") == RASTRO else "accept_venue"
    return intent.kind


# ----------------------------------------------------------------------------------- small helpers

class _Refuse(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code, self.detail = code, detail


def _need(cond: Any, code: str, detail: str = "") -> None:
    if not cond:
        raise _Refuse(code, detail)


def _int(x: Any) -> bool:
    return type(x) is int


def _finite(x: Any) -> bool:
    return type(x) in (int, float) and math.isfinite(x)


def _set_of(ref: str) -> str:
    return ref.split("-", 1)[0]


def _empty(v: Any) -> bool:
    return v is None or (type(v) is int and v == 0) or v == "" or v == [] or v == {} or v == ()


def _assets(world) -> dict:
    out = {}
    me = world.me if isinstance(world.me, Mapping) else {}
    for a in me.get("assets") or ():
        if isinstance(a, Mapping) and _int(a.get("id")):
            out[a["id"]] = a
    return out


def _pack_types(world) -> tuple:
    """Types of the packs in hand: only kind "pack" (an unknown asset kind is not a pack: it made book.packs
    non-empty and G14 refused every trade)."""
    return tuple(a.get("ref") if isinstance(a.get("ref"), str) else ""
                 for a in _assets(world).values() if a.get("kind") == "pack")


def ticks_per_hour(world, cfg: Optional[Cfg] = None) -> int:
    """Ticks per game hour. A game hour is a wall hour, so 3600 / tick_seconds (60 at 60 s on Friday: t159 =
    2.65 h; 120 at 30 s; 240 on Sunday at 15 s). cfg.TICKS_PER_GAME_HOUR only when tick_seconds is unknown."""
    ts = getattr(world, "tick_seconds", None)
    if _finite(ts) and ts > 0:
        return max(1, int(round(3600.0 / ts)))
    return int(getattr(cfg, "TICKS_PER_GAME_HOUR", 60) or 60)


def free(book: Book, ref: str, world=None) -> int:
    """INV-06: free(ref) = held - listed - pending_out. With `world`, also never more than held minus our
    assets of `ref` already in listed_assets (an accepted swap books its asset, not its ref)."""
    used = int(book.listed.get(ref, 0)) + int(book.pending_out.get(ref, 0))
    if world is not None:
        used = max(used, sum(1 for aid, a in _assets(world).items()
                             if a.get("ref") == ref and aid in book.listed_assets))
    return int(book.held.get(ref, 0)) - used


def venue_row(world, vid: str) -> Optional[Mapping]:
    for v in world.venues or ():
        if isinstance(v, Mapping) and (v.get("id") == vid or v.get("venue") == vid):
            return v
    return None


def trade_fee(world, venue: str, price: int, cards: int = 1) -> int:
    """Fee paid by the accepter on `venue`: ceil(fee_bps/10000*price + fee_per_card*cards). ValueError if unknown."""
    row = venue_row(world, venue)
    if row is None:
        if venue != RASTRO:
            raise ValueError(f"venue {venue} unknown")
        return _fee(price, cards)                                # R-01 default for El Rastro
    bps, pc = row.get("fee_bps"), row.get("fee_per_card")
    if not (_int(bps) and _int(pc) and bps >= 0 and pc >= 0):
        raise ValueError("venue fee malformed")
    return _fee(price, cards, bps, pc)


def your_value(world, ref: str, asset_id: Optional[int] = None) -> float:
    best = 0.0
    for a in _assets(world).values():
        if a.get("ref") == ref and _finite(a.get("your_value")):
            if asset_id is not None and a.get("id") == asset_id:
                return float(a["your_value"])
            best = max(best, float(a["your_value"]))
    return best


def dv_add(world, book: Book, valuer, ref: str, counts: Optional[Mapping] = None) -> float:
    """min(Valuer.delta_add(projected, ref, packs), server value?card)."""
    c = book.projected if counts is None else counts
    x = float(valuer.delta_add(dict(c), ref, book.packs))
    sv = (world.server_values or {}).get(ref)
    if _finite(sv):
        x = min(x, float(sv))
    _need(_finite(x), "G12.valuation", f"dv_add {ref}")
    return x


def dv_rm(world, book: Book, valuer, ref: str, asset_id: Optional[int] = None) -> float:
    """max(Valuer.delta_remove(held, ref, packs), your_value)."""
    x = abs(float(valuer.delta_remove(dict(book.held), ref, book.packs)))
    x = max(x, your_value(world, ref, asset_id))
    _need(_finite(x), "G12.valuation", f"dv_rm {ref}")
    return x


# --------------------------------------------------------------------------- canonical shapes (G11)

_TOP_KEYS = frozenset({"id", "maker", "to", "venue", "thread", "status", "give", "want", "expires_tick",
                       "created_tick", "final"})
_SIDE_KEYS = frozenset({"cash", "assets", "types", "cards"})
_ASSET_KEYS_OK = frozenset({"id", "kind", "ref", "serial", "rarity", "set", "print_run", "name", "your_value"})


def _side_items(side: Any) -> Optional[tuple]:
    """(cash, [(ref, asset_id|None), ...]) of a give/want side, or None if it is not a clean side."""
    if not isinstance(side, Mapping):
        return None
    for k, v in side.items():
        if k not in _SIDE_KEYS and not _empty(v):
            return None
    cash = side.get("cash", 0)
    if cash is None:
        cash = 0
    if not _int(cash) or not 0 <= cash <= MAX_PRICE:
        return None
    items = []
    assets, types, cards = side.get("assets") or [], side.get("types") or [], side.get("cards") or []
    if not all(isinstance(x, list) for x in (assets, types, cards)):
        return None
    for a in assets:
        if not isinstance(a, Mapping):
            return None
        if any(k not in _ASSET_KEYS_OK and not _empty(v) for k, v in a.items()):
            return None
        aid, ref = a.get("id"), a.get("ref")
        if not (_int(aid) and aid > 0 and a.get("kind") == "card" and isinstance(ref, str)
                and REF_RE.fullmatch(ref)):
            return None
        if a.get("set") is not None and a.get("set") != _set_of(ref):
            return None
        items.append((ref, aid))
    for t in types:
        if not isinstance(t, str) or not t.startswith("card:") or not REF_RE.fullmatch(t[5:]):
            return None
        items.append((t[5:], None))
    for c in cards:
        if not isinstance(c, str) or not REF_RE.fullmatch(c):
            return None
        items.append((c, None))
    return cash, items


def canonical_offer(o: Mapping) -> Optional[dict]:
    """The canonical form of a TEAM offer, or None. Shapes: "sell" (one card for cash), "bid" (cash for one
    card type), "swap" (one card for one card, no cash; D1). Anything else -> None."""
    try:
        if not isinstance(o, Mapping):
            return None
        for k, v in o.items():
            if k not in _TOP_KEYS and not _empty(v):
                return None
        oid, maker, status = o.get("id"), o.get("maker"), o.get("status")
        if not (_int(oid) and oid > 0 and isinstance(maker, str) and maker and isinstance(status, str)):
            return None
        to, venue, exp = o.get("to"), o.get("venue"), o.get("expires_tick")
        if not (to is None or isinstance(to, str)) or not (venue is None or isinstance(venue, str)):
            return None
        if not (exp is None or _int(exp)) or o.get("thread") is not None:
            return None
        if o.get("final") not in (None, False, True):
            return None
        g, w = _side_items(o.get("give")), _side_items(o.get("want"))
        if g is None or w is None:
            return None
        (gc, gi), (wc, wi) = g, w
        base = {"id": oid, "maker": maker, "to": to, "venue": venue, "status": status, "expires_tick": exp}
        if gc == 0 and len(gi) == 1 and gi[0][1] is not None and not wi and 1 <= wc <= MAX_PRICE:
            return {**base, "shape": "sell", "ref": gi[0][0], "asset_id": gi[0][1], "price": wc}
        if 1 <= gc <= MAX_PRICE and not gi and wc == 0 and len(wi) == 1 and wi[0][1] is None:
            return {**base, "shape": "bid", "ref": wi[0][0], "price": gc}
        if gc == 0 and wc == 0 and len(gi) == 1 and len(wi) == 1 and gi[0][0] != wi[0][0]:
            return {**base, "shape": "swap", "ref_in": gi[0][0], "asset_in": gi[0][1],
                    "ref_out": wi[0][0], "want_asset": wi[0][1]}
        return None
    except Exception:  # noqa: BLE001 - shape errors are "not canonical"
        return None


def _norm_side(side: Mapping) -> dict:
    out = {"cash": side.get("cash", 0)}
    assets = side.get("assets") or []
    out["assets"] = sorted([[a.get("id"), a.get("kind"), a.get("ref")] if isinstance(a, Mapping) else [repr(a)]
                            for a in assets], key=repr)
    for k, v in side.items():
        if k in ("cash", "assets") or _empty(v):
            continue
        out[k] = sorted(v, key=repr) if isinstance(v, list) else v
    return out


def fingerprint(o: Mapping) -> str:
    """sha1 over (id, give, want, to, venue, expires_tick, status); assets reduced to (id, kind, ref).
    "" if the offer cannot be fingerprinted (an empty fingerprint never matches: G10)."""
    try:
        payload = [o["id"], _norm_side(o["give"]), _norm_side(o["want"]), o.get("to"), o.get("venue"),
                   o.get("expires_tick"), o.get("status")]
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()
    except Exception:  # noqa: BLE001
        return ""


def duel_fingerprint(d: Mapping) -> str:
    """sha1(duel_id, rival_offer.id, .price, .days, .tick, len(messages)); "" if malformed."""
    try:
        ro = d.get("rival_offer") or {}
        did = d.get("duel", d.get("id"))
        payload = [did, ro.get("id"), ro.get("price"), ro.get("days"), ro.get("tick"), len(d.get("messages") or [])]
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()
    except Exception:  # noqa: BLE001
        return ""


# ------------------------------------------------------------------------------------------- book

def _offer_price(o: Mapping, side: str) -> int:
    s = o.get(side) or {}
    c = s.get("cash", 0) if isinstance(s, Mapping) else 0
    return c if _int(c) else 0


def _want_ref(o: Mapping) -> Optional[str]:
    w = o.get("want") or {}
    if not isinstance(w, Mapping):
        return None
    for t in w.get("types") or []:
        if isinstance(t, str) and t.startswith("card:"):
            return t[5:]
    for c in w.get("cards") or []:
        if isinstance(c, str):
            return c
    return None


def _thread_buy_ref(t: Mapping) -> Optional[str]:
    topic = t.get("topic") or {}
    b = topic.get("buy") if isinstance(topic, Mapping) else None
    if isinstance(b, Mapping):
        return b.get("card") or (("pack:" + b["pack"]) if b.get("pack") else None)
    return None


def _thread_standing(t: Mapping) -> Optional[int]:
    """Price of the live offer in a buy thread (the price we could be charged), or None. A dealer offer that fails
    offer_safety.offer_ok (the Pícaros trick: another card at the asked price) can never be accepted: ignored."""
    dealer, topic = t.get("with"), t.get("topic")
    best = None
    offers = list(t.get("standing_offers") or [])
    for m in t.get("messages") or []:
        if isinstance(m, Mapping) and isinstance(m.get("offer"), Mapping):
            offers.append(m["offer"])
    for o in offers:
        if isinstance(o, Mapping) and o.get("status") == "open" and o.get("maker") in (dealer, TEAM):
            if o.get("maker") == dealer and not offer_ok(o, topic, buying=True):
                continue
            p = _offer_price(o, "want") if o.get("maker") == dealer else _offer_price(o, "give")
            best = p if best is None else max(best, p)
    return best


def _own_thread_prices(t: Mapping) -> tuple:
    """Our prices in a dealer thread, oldest first. Live messages have no top-level price (keys id, offer, sender,
    tick): the price is the cash of the offer the message carries (give.cash when we buy, want.cash when we sell),
    as gate._foreign_writer reads it. A top-level price (fake server, tests) is the fallback."""
    side = "give" if _thread_buy_ref(t) else "want"
    out = []
    for m in t.get("messages") or []:
        if not isinstance(m, Mapping) or m.get("sender") != TEAM:
            continue
        o = m.get("offer")
        p = _offer_price(o, side) if isinstance(o, Mapping) else 0
        if not p and _int(m.get("price")):
            p = m["price"]
        if p > 0:
            out.append(p)
    return tuple(out)


_HOUR_BLOCK_REASONS = ("persona_quota", "persona_budget", "sold_out")


def _closed_thread_blocks(world, tph: int) -> dict:
    """dealer -> until_tick from our threads the dealer closed in the current game hour (closed_reason; live Sat:
    status "walked", closed_reason "persona_budget"): cooloff until its until_tick (end of the hour without one),
    persona_quota / persona_budget / sold_out until the end of the current game hour, so the dealers tactic does
    not reopen them. The closing tick is the thread's last message (or created_tick)."""
    out: dict = {}
    t_h = world.t_hours if _finite(world.t_hours) else None
    frac = t_h - math.floor(t_h) if t_h is not None else 0.0
    hour_start = world.tick - int(math.floor(frac * tph + 1e-9)) if t_h is not None else world.tick - tph
    hour_end = world.tick + max(1, math.ceil((1.0 - frac) * tph))
    for t in (world.threads or {}).values():
        if not isinstance(t, Mapping) or t.get("status") == "open" or not isinstance(t.get("with"), str):
            continue
        reason = t.get("closed_reason")
        if not isinstance(reason, str) or not reason:
            continue
        until = t.get("until_tick") if "cooloff" in reason and _int(t.get("until_tick")) else None
        if until is None and ("cooloff" in reason or any(c in reason for c in _HOUR_BLOCK_REASONS)):
            ticks = [m.get("tick") for m in t.get("messages") or () if isinstance(m, Mapping) and _int(m.get("tick"))]
            last = max(ticks) if ticks else t.get("created_tick")
            if _int(last) and last >= hour_start:
                until = hour_end
        if until is not None and until >= world.tick:
            out[t["with"]] = max(until, out.get(t["with"], until))
    return out


def _rows(journal, kinds) -> list:
    if journal is None:
        return []
    return list(journal.rows(set(kinds)))


def build_book(world, journal, valuer, cfg: Cfg, plan_cfg, frozen, baseline) -> Book:
    """Book at the start of a tick from the World, the journal (pending / unknown / settlements) and config.
    Journal errors propagate (the Gate turns them into STOP)."""
    cfg = cfg or Cfg()
    plan_cfg = plan_cfg or {}
    me = world.me if isinstance(world.me, Mapping) else {}
    cash = me.get("cash")
    cash = cash if _int(cash) else 0
    assets = _assets(world)
    held = Counter(a["ref"] for a in assets.values() if a.get("kind") == "card" and isinstance(a.get("ref"), str))
    packs = _pack_types(world)

    listed, listed_assets, own_ids, own_bids, bid_price = Counter(), set(), set(), {}, {}
    paths, projected = Counter(), Counter(held)
    commit = 0
    for o in world.my_offers or ():
        if not isinstance(o, Mapping) or not _int(o.get("id")):
            continue
        if o.get("maker") not in (TEAM, None):
            continue
        own_ids.add(o["id"])
        if o.get("status") not in OPEN_STATUSES:
            continue
        if o.get("thread") is not None:
            continue                     # dealer-thread offer: counted once, in the thread loop below (live 3 Oct t191)
        give = o.get("give") or {}
        for a in (give.get("assets") or []) if isinstance(give, Mapping) else []:
            if isinstance(a, Mapping) and _int(a.get("id")):
                listed_assets.add(a["id"])
                if isinstance(a.get("ref"), str):
                    listed[a["ref"]] += 1
        wref = _want_ref(o)
        if wref:
            own_bids.setdefault(wref, o["id"])
            paths[wref] += 1
            projected[wref] += 1
            p = _offer_price(o, "give")
            bid_price[o["id"]] = p
            commit += p

    # dealer threads opened by us
    thread_limit, thread_prices, thread_ref, thread_by_dealer, thread_res = {}, {}, {}, {}, {}
    deals_hour: Counter = Counter()
    abuela_open = False
    tph = ticks_per_hour(world, cfg)
    hour_ago = world.tick - tph
    for tid, t in (world.threads or {}).items():
        if not isinstance(t, Mapping):
            continue
        dealer = t.get("with")
        if t.get("status") == "deal" and isinstance(dealer, str) and _int(t.get("created_tick")) \
                and t["created_tick"] >= hour_ago:
            deals_hour[dealer] += 1
        prices = _own_thread_prices(t)
        thread_prices[tid] = prices
        if t.get("status") != "open":
            continue
        if isinstance(dealer, str):
            thread_by_dealer[dealer] = tid
            abuela_open = abuela_open or dealer == "abuela"
        ref = _thread_buy_ref(t)
        if ref:
            thread_ref[tid] = ref
            paths[ref] += 1
            standing = _thread_standing(t)
            if standing is not None:
                projected[ref] += 1
            thread_res[tid] = max([standing or 0] + list(prices))    # capped at the thread's limit below
        else:
            topic = t.get("topic") or {}
            sell = topic.get("sell") if isinstance(topic, Mapping) else None
            for aid in (sell.get("assets") or []) if isinstance(sell, Mapping) else []:
                aid = aid.get("id") if isinstance(aid, Mapping) else aid
                if _int(aid) and aid in assets:
                    thread_ref[tid] = assets[aid].get("ref")
                    listed_assets.add(aid)
                    listed[assets[aid].get("ref")] += 1

    # journal: limits of our threads, blocks, unknown domains, pending intents, recent El Rastro settlements
    unknown = set(journal.unknown_domains()) if journal is not None else set()
    dealer_block: dict = {}
    recent: dict = {}
    pending_in, pending_out = Counter(), Counter()
    if journal is not None:
        intents = {}
        for r in _rows(journal, {"intent", "result", "settlement"}):
            k = r.get("kind")
            if k == "intent":
                intents[r.get("id")] = r
            elif k == "result":
                it = intents.get(r.get("id")) or {}
                args = it.get("args") or {}
                resp = r.get("response") or {}
                code = str(r.get("code") or "")
                if it.get("intent_kind") == "open_thread" and r.get("status") == "ok" and isinstance(resp, Mapping) \
                        and _int(resp.get("id")) and _int(args.get("limit")):
                    thread_limit[resp["id"]] = args["limit"]
                if any(c in code for c in ("cooloff", "persona_quota")):
                    dealer = args.get("dealer") or (world.threads.get(args.get("thread_id")) or {}).get("with")
                    until = r.get("until_tick") or (resp.get("until_tick") if isinstance(resp, Mapping) else None)
                    if isinstance(dealer, str):
                        dealer_block[dealer] = until if _int(until) else (r.get("tick") or world.tick) + tph
                if it.get("intent_kind") == "accept" and r.get("status") == "ok" and args.get("venue", RASTRO) == RASTRO:
                    _note_trade(recent, args, r.get("tick") or it.get("tick") or 0)
            elif k == "settlement":
                for iid in r.get("ids") or []:
                    it = intents.get(iid) or {}
                    if it.get("intent_kind") == "list_offer":
                        _note_trade(recent, it.get("args") or {}, r.get("tick") or 0)
        for p in journal.pending():
            # M2 rows: the row kind is "intent" and the intent's own kind is in "intent_kind"
            it = p if p.get("kind") == "intent" else (intents.get(p.get("id")) or {})
            kind, args = it.get("intent_kind"), it.get("args") or {}
            if kind == "accept" and args.get("source") in ("team", "dealer"):
                side, ref = args.get("side"), args.get("ref")
                if side in ("buy", "swap") and ref:
                    pending_in[ref] += 1
                    paths[ref] += 1
                    projected[ref] += 1
                    price = args.get("price") if _int(args.get("price")) else 0
                    commit += price + (_fee(price, 2 if side == "swap" else 1) if args.get("source") == "team" else 0)
                give = args.get("give_asset")
                if side in ("sell", "swap") and _int(give) and give in assets:
                    pending_out[assets[give].get("ref")] += 1
                    listed_assets.add(give)
            elif kind == "list_offer" and args.get("side") in ("bid", "swap"):
                wref = args.get("ref") if args.get("side") == "bid" else args.get("want_ref")
                if wref and wref not in own_bids:
                    paths[wref] += 1
                    projected[wref] += 1
                    commit += args.get("price") if _int(args.get("price")) else 0
            elif kind == "open_thread" and args.get("side") == "buy" and args.get("ref"):
                if args.get("dealer") not in thread_by_dealer:
                    paths[args["ref"]] += 1
                    commit += args.get("limit") if _int(args.get("limit")) else 0

    for dealer, until in _closed_thread_blocks(world, tph).items():
        dealer_block[dealer] = max(until, dealer_block.get(dealer, until))

    # open buy threads reserve max(dealer ask, our prices), never above the limit the thread was opened with (we
    # never pay more: a dealer asking 95 on a limit-90 thread held 95); unknown limit -> the full max (fail closed)
    for tid, res in thread_res.items():
        lim = thread_limit.get(tid)
        commit += min(lim, res) if _int(lim) else res

    protect = frozenset(plan_cfg.get("protect_sets") or ("SAL", "RET", "CHA", "LAT"))
    keep = {}
    for ref in set(held) | set(getattr(valuer, "cards", {}) or {}):
        try:
            page = bool(valuer.page_card(ref))
        except Exception:  # noqa: BLE001 - unknown card: protect it (fail closed)
            page = True
        if _set_of(ref) in protect and page:
            keep[ref] = 1

    bands_cfg = plan_cfg.get("baseline_bands") or {}
    base_bands = (baseline or {}).get("bands") or {} if isinstance(baseline, Mapping) else {}
    bid_band = {}
    for oid in bid_price:
        b = bands_cfg.get(str(oid), base_bands.get(str(oid)))
        bid_band[oid] = float(b) if _finite(b) else 2.0

    risk = bool(packs) or abuela_open or _grant_soon(world, plan_cfg.get("grant_lookahead_ticks", cfg.GRANT_LOOKAHEAD_TICKS), cfg)

    try:
        val_ok = bool(valuer.self_check(world.me, world.server_values, cfg.VAL_TOL)[0]) and "values" not in world.down
    except Exception:  # noqa: BLE001
        val_ok = False

    return Book(
        cash=cash, cash_free=cash - commit - cfg.RESERVE,
        held=MappingProxyType(dict(held)), listed=MappingProxyType(dict(listed)),
        pending_out=MappingProxyType(dict(pending_out)), pending_in=MappingProxyType(dict(pending_in)),
        projected=MappingProxyType(dict(projected)), keep=MappingProxyType(keep),
        listed_assets=frozenset(listed_assets), own_offer_ids=frozenset(own_ids),
        own_bids=MappingProxyType(own_bids), bid_price=MappingProxyType(bid_price),
        bid_band=MappingProxyType(bid_band), paths=MappingProxyType(dict(paths)),
        thread_limit=MappingProxyType(thread_limit), thread_prices=MappingProxyType(thread_prices),
        thread_ref=MappingProxyType(thread_ref), thread_by_dealer=MappingProxyType(thread_by_dealer),
        dealer_block=MappingProxyType(dealer_block), dealer_deals_hour=MappingProxyType(dict(deals_hour)),
        packs=packs, needs=MappingProxyType({}), frozen_closer=MappingProxyType(dict(frozen or {})),
        protect_sets=protect, delivery_risk=risk, recent_rastro=MappingProxyType(recent),
        unknown_domains=frozenset(unknown), valuation_ok=val_ok)


def _note_trade(recent: dict, args: Mapping, tick: int) -> None:
    """ref -> (side, tick) of our trades; swaps note both refs. Latest tick wins."""
    side = args.get("side")
    notes = []
    if side == "buy":
        notes.append((args.get("ref"), "buy"))
    elif side == "sell":
        notes.append((args.get("ref"), "sell"))
    elif side == "bid":
        notes.append((args.get("ref"), "buy"))
    elif side == "swap":
        if args.get("want_ref"):           # list_offer swap: we gave ref, got want_ref
            notes += [(args.get("ref"), "sell"), (args.get("want_ref"), "buy")]
        else:                              # accept swap: we got ref
            notes.append((args.get("ref"), "buy"))
    for ref, s in notes:
        if isinstance(ref, str) and _int(tick) and (ref not in recent or recent[ref][1] <= tick):
            recent[ref] = (s, tick)


def _grant_soon(world, ticks: Any, cfg: Cfg) -> bool:
    """True if a scheduled grant with packs is due within `ticks` game ticks; unknown schedule -> True."""
    try:
        up = (world.schedule or {}).get("upcoming")
        if not isinstance(up, (list, tuple)) or not _finite(world.t_hours):
            return True
        horizon = world.t_hours + float(ticks) / ticks_per_hour(world, cfg)
        for e in up:
            params = e.get("params") or {}
            if isinstance(params, Mapping) and params.get("packs"):
                at = e.get("at_hours")
                if not _finite(at):
                    return True
                if world.t_hours - 1e-9 <= at <= horizon:
                    return True
        return False
    except Exception:  # noqa: BLE001
        return True


def apply(book: Book, intent: Intent, outcome: Outcome) -> Book:
    """PURE. sent / would / unknown -> the intent's commitment is booked at once; refused / deferred -> same book.
    Releases (cancel, close_thread, open_pack) are NOT booked: they count only once the server shows them."""
    if outcome.status not in ("sent", "would", "unknown"):
        return book
    a, kind = intent.args, intent.kind
    listed = Counter(book.listed)
    p_in, p_out = Counter(book.pending_in), Counter(book.pending_out)
    paths, proj = Counter(book.paths), Counter(book.projected)
    la, own_bids = set(book.listed_assets), dict(book.own_bids)
    tprices, tby = dict(book.thread_prices), dict(book.thread_by_dealer)
    cash_free = book.cash_free
    if kind == "accept":
        side, ref, price = a["side"], a["ref"], a["price"]
        team = a["source"] == "team"
        if side in ("buy", "swap"):
            p_in[ref] += 1
            paths[ref] += 1
            proj[ref] += 1
            cash_free -= price + (_fee(price, 2 if side == "swap" else 1) if team else 0)
        give = a.get("give_asset")
        if side in ("sell", "swap") and give is not None:
            la.add(give)            # a swap's out-ref is unknown here: G13 counts committed assets per ref
            if side == "sell":
                p_out[ref] += 1
    elif kind == "list_offer":
        side = a["side"]
        if side in ("sell", "swap") and a["asset_id"] is not None:
            la.add(a["asset_id"])
            listed[a["ref"]] += 1
        if side in ("bid", "swap"):
            wref = a["ref"] if side == "bid" else a["want_ref"]
            paths[wref] += 1
            proj[wref] += 1
            own_bids.setdefault(wref, -1)
            cash_free -= a["price"]
    elif kind == "open_thread":
        tby.setdefault(a["dealer"], -1)
        if a["side"] == "buy":
            paths[a["ref"]] += 1
            cash_free -= a["limit"]
        else:
            for aid in a["asset_ids"]:
                la.add(aid)
                listed[a["ref"]] += 1
    elif kind == "say":
        tid = a["thread_id"]
        tprices[tid] = tuple(tprices.get(tid, ())) + (a["price"],)
    return replace(book, cash_free=cash_free, listed=MappingProxyType(dict(listed)),
                   pending_in=MappingProxyType(dict(p_in)), pending_out=MappingProxyType(dict(p_out)),
                   paths=MappingProxyType(dict(paths)), projected=MappingProxyType(dict(proj)),
                   listed_assets=frozenset(la), own_bids=MappingProxyType(own_bids),
                   thread_prices=MappingProxyType(tprices), thread_by_dealer=MappingProxyType(tby))


# ------------------------------------------------------------------------------------------- check

def check(intent, world, book, valuer, cfg, counters, *, fresh=None, now: float) -> Verdict:
    """PURE. Globals G02-G06 (+ one-sided G07), then the team / publication / pack / thread-close guards.
    TALK_KINDS and dealer accepts go to agent.talk.check. Any exception -> refuse (fail closed)."""
    try:
        cfg = cfg or Cfg()
        _globals(intent, world, book, cfg, counters, now)
        kind, a = intent.kind, intent.args
        if kind in TALK_KINDS or (kind == "accept" and a["source"] == "dealer"):
            try:
                talk = importlib.import_module("agent.talk")
            except Exception:  # noqa: BLE001
                return Verdict(False, "G02.not_built", "agent.talk unavailable")
            return talk.check(intent, world, book, valuer, cfg, counters, fresh=fresh, now=now)
        if kind == "accept":
            _accept_team(intent, world, book, valuer, cfg, fresh)
        elif kind == "list_offer":
            _list_offer(intent, world, book, valuer, cfg)
        elif kind == "cancel":
            _cancel(a, world, book)
        elif kind == "close_thread":
            _close_thread(a, world)
        elif kind == "open_pack":
            _open_pack(a, world, book)
        else:
            return Verdict(False, "G02.kind", kind)
        return OK
    except _Refuse as r:
        return Verdict(False, r.code, r.detail)
    except Exception as e:  # noqa: BLE001 - fail closed
        return Verdict(False, "G00.error", f"{type(e).__name__}: {e}"[:200])


def _globals(it, world, book, cfg, counters, now) -> None:
    # G02 type and exact args
    _need(type(it) is Intent and it.kind in KINDS, "G02.kind")
    try:
        make_intent(it.kind, it.tactic, it.args, it.reason, it.expected_effect, it.prediction,
                    it.priority, it.experiment)
    except ValueError as e:
        raise _Refuse("G02.args", str(e)[:200])
    kind, a = it.kind, it.args
    exempt = kind in ("cancel", "close_thread")
    # G03 clock
    clock = world.clock if isinstance(world.clock, Mapping) else {}
    if not exempt:
        _need(clock.get("paused") is False, "G03.paused")
        _need(clock.get("doors") == "open", "G03.doors")
        _need(_finite(now) and _finite(world.tick_deadline) and now <= world.tick_deadline, "G03.late")
    # G04 budgets (only our own offers / threads count)
    _need(counters is not None and counters.tick == world.tick, "G04.counters")
    lim = world.limits
    if kind in ("accept", "duel_accept"):
        _need(counters.accepts < lim.accepts, "G04.accepts")
    if kind in ("list_offer", "cancel"):
        _need(counters.listings < min(cfg.LISTINGS_PER_TICK, lim.listings - 2), "G04.listings")
    if kind == "list_offer":
        mine = sum(1 for o in world.my_offers or () if isinstance(o, Mapping)
                   and o.get("maker") in (TEAM, None) and o.get("status") in OPEN_STATUSES)
        _need(mine + counters.offers_opened < lim.open_offers - cfg.OPEN_OFFERS_MARGIN, "G04.open_offers")
    if kind == "open_thread":
        mine = sum(1 for t in (world.threads or {}).values() if isinstance(t, Mapping) and t.get("status") == "open")
        _need(mine + counters.threads_opened < lim.threads - cfg.THREADS_MARGIN, "G04.threads")
    if kind == "say":
        _need(f"thread:{a['thread_id']}" not in counters.msgs, "G04.msg")
    if kind == "duel_say":
        _need(f"duel:{a['duel_id']}" not in counters.msgs, "G04.msg")
    # G05 unknown domains
    hit = domains_of(it) & frozenset(book.unknown_domains)
    _need(not hit, "G05.unknown", ",".join(sorted(hit)))
    # G06 health
    down = SOURCES[source_key(it)] & frozenset(world.down)
    _need(not down, "G06.source", ",".join(sorted(down)))
    if kind not in _NO_VALUE_KINDS:
        _need(book.valuation_ok, "G06.valuation")
    # G14 unopened pack
    if book.packs:
        _need(kind in _PACK_OK_KINDS, "G14.pack")


def _g07(it: Intent, neg_lo: float) -> None:
    """One-sided: the intent may not claim more than the guard computed."""
    p = it.prediction
    _need(_finite(p.neg_lo) and p.neg_lo <= neg_lo + 0.01, "G07.trip", f"pred {p.neg_lo:.2f} > guard {neg_lo:.2f}")


def _round_trip(world, book, cfg, ref: str, side: str) -> None:
    prev = book.recent_rastro.get(ref)
    if prev and prev[0] != side and world.tick - prev[1] < cfg.ROUND_TRIP_TICKS:
        raise _Refuse("G12.round_trip", ref)


def _g13(world, book, ref: str, asset_id: int, *, resupply_ok: bool = False) -> None:
    """INV-06: asset is ours, a card of `ref`, not listed / committed, and free(ref) - 1 >= keep(ref)."""
    a = _assets(world).get(asset_id)
    _need(a is not None, "G13.not_ours", str(asset_id))
    _need(a.get("kind") == "card" and a.get("ref") == ref, "G13.asset_ref", str(asset_id))
    _need(asset_id not in book.listed_assets, "G13.listed", str(asset_id))
    fr = free(book, ref, world)
    _need(fr >= 1, "G13.no_free_copy", ref)
    if not resupply_ok:
        _need(fr - 1 >= int(book.keep.get(ref, 0)), "G13.protected", ref)


def _j13_ok(world, book, cfg, ref: str, asset_id: int, offer: Mapping) -> None:
    """Exception J13 (resupply a rival's closer bid): every condition of §4 G13."""
    s = _set_of(ref)
    _need(s in ("RET", "CHA"), "G13.j13_set", s)
    have = sum(1 for r, n in book.projected.items() if _set_of(r) == s and n > 0)
    _need(have < 9, "G13.j13_page", str(have))
    _need(book.frozen_closer.get(s) != ref, "G13.j13_closer", ref)
    rar = (_assets(world).get(asset_id) or {}).get("rarity")
    _need(rar in ("common", "uncommon"), "G13.j13_rarity", str(rar))
    until = book.dealer_block.get("abuela")
    _need(until is None or until <= world.tick, "G13.j13_abuela_blocked")
    _need(book.dealer_deals_hour.get("abuela", 0) <= cfg.ABUELA_DEALS_HOUR_MAX, "G13.j13_abuela_quota")
    exp = offer.get("expires_tick")
    _need(exp is None or exp >= world.tick + 2, "G13.j13_expiry")
    _need(not book.packs, "G13.j13_pack")


def _accept_team(it, world, book, valuer, cfg, fresh) -> None:
    a = it.args
    _need(a["source"] == "team" and a["thread_id"] is None, "G11.source")
    _need(not a["resupply"] or a["side"] == "sell", "G11.resupply_side")
    # G03(c) + G10 fresh identity
    _need(isinstance(fresh, Mapping), "G10.no_fresh")
    offer = fresh.get("offer") if "offer" in fresh else None
    ftick = fresh.get("tick", fresh.get("clock_tick"))
    _need(isinstance(offer, Mapping), "G10.shape", "fresh has no offer")
    _need(_int(ftick) and ftick == world.tick, "G03.stale", f"fresh tick {ftick!r} != {world.tick}")
    _need(offer.get("id") == a["offer_id"], "G10.id")
    _need(offer.get("status") == "open", "G10.status", str(offer.get("status")))
    exp = offer.get("expires_tick")
    _need(exp is None or (_int(exp) and exp >= world.tick + 1), "G10.expired")
    _need(offer["id"] not in book.own_offer_ids, "G10.own_offer")
    _need(offer.get("maker") not in (TEAM, world.own_pseudonym, None, ""), "G10.own_maker")
    _need(offer.get("to") in (None, TEAM), "G10.to")
    _need(offer.get("venue") == a["venue"], "G10.venue")
    fp = fingerprint(offer)
    _need(fp and fp == a["fingerprint"], "G10.fingerprint")
    # G11 exact shape
    c = canonical_offer(offer)
    _need(c is not None, "G11.shape")
    side, ref, price = a["side"], a["ref"], a["price"]
    venue = a["venue"]
    if side == "buy":
        _need(c["shape"] == "sell" and c["ref"] == ref and c["price"] == price, "G11.buy_shape")
        _need(a["give_asset"] is None, "G11.give_asset")
        cards = 1
    elif side == "sell":
        _need(c["shape"] == "bid" and c["ref"] == ref and c["price"] == price, "G11.sell_shape")
        _need(_int(a["give_asset"]), "G11.give_asset")
        cards = 1
    else:  # swap (D1)
        _need(c["shape"] == "swap" and c["ref_in"] == ref and price == 0, "G11.swap_shape")
        _need(_int(a["give_asset"]), "G11.give_asset")
        _need(c["want_asset"] in (None, a["give_asset"]), "G11.swap_want_asset")
        cards = 2
    # D2 venue rules (INV-20: never our own venue)
    if venue != RASTRO:
        row = venue_row(world, venue)
        _need(row is not None and row.get("status") == "open", "G12.venue_closed", venue)
        owner = row.get("owner")
        _need(isinstance(owner, str) and owner and owner != TEAM, "G12.own_venue", str(owner))
        top = tuple(world.leaderboard or ())
        _need(len(top) > 0, "G12.rank_unknown")
        _need(owner not in top[:cfg.RIVAL_TOP_N], "G12.rival_top", owner)
    try:
        f = trade_fee(world, venue, price, cards)
    except ValueError as e:
        raise _Refuse("G12.fee_unknown", str(e))
    min_gain = cfg.MIN_GAIN_TEAM if venue == RASTRO else max(cfg.MIN_GAIN_TEAM, cfg.RIVAL_VENUE_MIN_GAIN)
    # G12 value, G13 protected copies, G15 one path, G16 cash
    if side == "buy":
        _need(book.paths.get(ref, 0) == 0, "G15.path", ref)
        g = dv_add(world, book, valuer, ref) - price - f
        neg = min(g, cfg.NEG_CAP)
        _need(neg >= min_gain, "G12.gain", f"{neg:.2f}")
        if valuer.closes_page(book.projected, ref):
            _need(neg >= cfg.CLOSER_ACCEPT_MIN, "G12.closer_gain", f"{neg:.2f}")
        _round_trip(world, book, cfg, ref, "buy")
        _need(price + f <= book.cash_free, "G16.cash", f"{price + f} > {book.cash_free}")
    elif side == "sell":
        give = a["give_asset"]
        if a["resupply"]:
            _g13(world, book, ref, give, resupply_ok=True)
            _j13_ok(world, book, cfg, ref, give, offer)
            min_gain = max(min_gain, cfg.RESUPPLY_MIN)
        else:
            _g13(world, book, ref, give)
        g = price - f - dv_rm(world, book, valuer, ref, give)
        neg = min(g, cfg.NEG_CAP)
        _need(neg >= min_gain, "G12.gain", f"{neg:.2f}")
        _round_trip(world, book, cfg, ref, "sell")
        _need(f <= book.cash_free + price, "G16.cash")
    else:
        give = a["give_asset"]
        out_ref = (_assets(world).get(give) or {}).get("ref")
        _need(isinstance(out_ref, str) and out_ref == c["ref_out"], "G11.swap_give_ref", str(out_ref))
        _g13(world, book, out_ref, give)
        _need(book.paths.get(ref, 0) == 0, "G15.path", ref)
        lost = dv_rm(world, book, valuer, out_ref, give)
        counts = Counter(book.projected)
        counts[out_ref] -= 1
        g = dv_add(world, book, valuer, ref, counts) - lost - f
        neg = min(g, cfg.NEG_CAP)
        _need(neg >= min_gain, "G12.gain", f"{neg:.2f}")
        if valuer.closes_page(counts, ref):
            _need(neg >= cfg.CLOSER_ACCEPT_MIN, "G12.closer_gain", f"{neg:.2f}")
        _round_trip(world, book, cfg, ref, "buy")
        _round_trip(world, book, cfg, out_ref, "sell")
        _need(f <= book.cash_free, "G16.cash")
    _g07(it, neg)


def _catalog_book(world, ref: str) -> Optional[float]:
    for s in (world.catalog or {}).get("sets") or ():
        for c in s.get("cards") or ():
            if c.get("id") == ref and _finite(c.get("book")):
                return float(c["book"])
    return None


def _list_offer(it, world, book, valuer, cfg) -> None:
    a = it.args
    side, ref, price = a["side"], a["ref"], a["price"]
    # G22 expiry range (the tactic applies EXPIRY_FACTOR; the guard checks the clamp)
    _need(cfg.MIN_EXPIRES <= a["expires_ticks"] <= cfg.MAX_EXPIRES, "G22.expiry", str(a["expires_ticks"]))
    _need(REF_RE.fullmatch(ref), "G11.ref")
    if side == "sell":
        # G20 own sale
        _g13(world, book, ref, a["asset_id"])
        _need(1 <= price <= MAX_PRICE, "G20.price")
        lost = dv_rm(world, book, valuer, ref, a["asset_id"])
        _need(price >= math.ceil(lost + cfg.MIN_GAIN_MAKER - 1e-9), "G20.low", f"{price} < {lost:.2f}+{cfg.MIN_GAIN_MAKER}")
        bk = _catalog_book(world, ref)
        aff = ((world.me or {}).get("affinity") or {}).get(_set_of(ref))
        _need(bk is not None and _finite(aff), "G20.book_unknown", ref)
        _need(price <= cfg.MAX_PRICE_X_BOOK * bk * aff, "G20.high", f"{price} > {cfg.MAX_PRICE_X_BOOK}x{bk}x{aff}")
        _round_trip(world, book, cfg, ref, "sell")
        _g07(it, min(price - lost, cfg.NEG_CAP))
    elif side == "bid":
        # G21 own bid
        _need(ref not in book.own_bids, "G21.dup", ref)
        _need(book.paths.get(ref, 0) == 0, "G15.path", ref)
        _need(1 <= price <= MAX_PRICE, "G21.price")
        dv = dv_add(world, book, valuer, ref)
        if valuer.closes_page(book.projected, ref):
            _need(a["closer"], "G21.closer_flag", ref)
            _need(not book.delivery_risk, "G21.delivery_risk")
            _need(price <= math.floor(dv - cfg.CLOSER_ACCEPT_MIN + 1e-9), "G21.closer_high", f"{price} vs {dv:.2f}")
        else:
            _need(price <= math.floor(dv - cfg.MIN_GAIN_TEAM + 1e-9), "G21.high", f"{price} vs {dv:.2f}")
        _round_trip(world, book, cfg, ref, "buy")
        _need(price <= book.cash_free, "G16.cash", f"{price} > {book.cash_free}")
        _g07(it, min(dv - price, cfg.NEG_CAP))
    else:  # swap (D1): we give asset_id (ref) and want want_ref, no cash
        want = a["want_ref"]
        _need(isinstance(want, str) and REF_RE.fullmatch(want) and want != ref and price == 0, "G11.swap")
        _g13(world, book, ref, a["asset_id"])
        _need(want not in book.own_bids and book.paths.get(want, 0) == 0, "G15.path", want)
        lost = dv_rm(world, book, valuer, ref, a["asset_id"])
        counts = Counter(book.projected)
        counts[ref] -= 1
        gain = dv_add(world, book, valuer, want, counts)
        neg = min(gain - lost, cfg.NEG_CAP)
        _need(neg >= cfg.MIN_GAIN_MAKER, "G12.swap_gain", f"{neg:.2f}")
        if valuer.closes_page(counts, want):
            _need(a["closer"] and not book.delivery_risk and neg >= cfg.CLOSER_ACCEPT_MIN, "G21.closer_swap")
        _round_trip(world, book, cfg, want, "buy")
        _round_trip(world, book, cfg, ref, "sell")
        _g07(it, neg)


def _cancel(a, world, book) -> None:
    oid = a["offer_id"]
    _need(oid in book.own_offer_ids, "G23.not_ours", str(oid))
    rows = [o for o in world.my_offers or () if isinstance(o, Mapping) and o.get("id") == oid]
    _need(rows and rows[0].get("maker") in (TEAM, None) and rows[0].get("status") in OPEN_STATUSES,
          "G23.not_open", str(oid))


def _close_thread(a, world) -> None:
    t = (world.threads or {}).get(a["thread_id"])
    _need(isinstance(t, Mapping), "G33.not_ours", str(a["thread_id"]))
    _need(t.get("team") in (TEAM, None) and t.get("status") == "open", "G33.not_open", str(a["thread_id"]))


def _open_pack(a, world, book) -> None:
    asset = _assets(world).get(a["asset_id"])
    _need(asset is not None and asset.get("kind") == "pack", "G40.not_pack", str(a["asset_id"]))
    buy_open = [tid for tid, t in (world.threads or {}).items()
                if isinstance(t, Mapping) and t.get("status") == "open" and _thread_buy_ref(t)]
    _need(not buy_open and not any(v == -1 for v in book.thread_by_dealer.values()), "G40.threads_open",
          ",".join(map(str, buy_open)))
