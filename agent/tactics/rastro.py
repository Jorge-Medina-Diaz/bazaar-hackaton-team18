"""M11 rastro: team-market tactics (J4 closer, J5 author sales, J6 buys, J9 LAT liquidation, J13 resupply,
D1 swaps, D2 every venue, D3 long bids).

propose(world, book, valuer, cfg, plan_cfg, needs, state) -> list[Intent]
Pure apart from `state` (a dict the runner keeps across ticks; None works, with less memory).
Every intent is re-checked by the Gate (G10-G23); this module only proposes what already passes its own
copy of those rules, and refuses (proposes nothing) whenever an input it needs is missing.

NOTES (M11, night build)
- J4 (tactic "closer"): accept a sale with neg_lo >= accept_min (20) on the spot; else bid
  min(floor(dv_add - default_minus), cash_free) (49 for RET); with a rival bid >= ours, or in the endgame, raise to
  floor(dv_add - compete_minus) (79). Never lower: the floor is max(state memory, our standing bid). A raise or a
  switch from our bid to a board sale is two-step: cancel in T, act in T+1 once the bid is gone (INV-08).
  No closer bid while book.delivery_risk (hygiene.watch cancels the standing one).
- J5 author sales of spares (free - 1 >= keep): price max(ceil(dv_rm + 2), dup_min_price[set], rarity median),
  -1 per relist (60 ticks), never below ceil(dv_rm + 2), capped at 4 x book x affinity (G20).
  J9 needs no code here: when LAT leaves protect_sets, keep goes to 0 and J5/J13-style bid sales pick LAT up.
- J6: buy only refs in `needs`, gain after the venue fee >= MIN_GAIN_TEAM (20 if it closes a page), p <= max_price.
  M9 (plan endgame_buy_any): after the dealer day end or in the endgame, also a first copy (held 0) of a card
  outside the page sets with gain after the fee >= MIN_GAIN_TEAM, paid from cash_free.
- Bids into rival bids (sell): gain >= MIN_GAIN_TEAM, protected copies never; J13 resupply exception with all its
  conditions (resupply=True, gain >= RESUPPLY_MIN).
- D1 swaps: accepted when V(received) - V(given) - fee >= threshold, the copy handed over is never protected;
  swap fee is computed with cards = 2 (one each way, conservative). Published (maker, fee 0) only for
  non-closer needs with source "team" that have no other route, giving our cheapest-to-lose spare.
- D2: all boards + offers_to_us are scanned; publishing only on rastro; another team's venue only with
  gain >= RIVAL_VENUE_MIN_GAIN and owner not in leaderboard[:RIVAL_TOP_N]; unknown leaderboard -> refuse.
- D3: list_offer carries desired game ticks; the Gate converts with contracts.expiry_units.
- Long bids are published only for non-closer needs with source "team" (dealer-sourced needs belong to M10;
  a bid would block its thread through INV-08).
- Predictions come from M3 (predict_team / predict_swap with the venue's fee_bps / fee_per_card); an unknown
  card value (UnknownCard etc.) turns into a prediction that never passes a gain check.
- Not done tonight: reverse-form swaps where the rival names a card type it GIVES (only give.assets is read);
  multi-card offers (always skipped); sale relist decay is per ref, not per asset; the fingerprint falls back to
  a local sha1 until agent.guards.fingerprint exists (a mismatch makes G10 refuse: fail closed).
- For the Gate (M4a/M5): G10 still says fresh.venue == "rastro"; D2 accepts carry args["venue"] of another
  team's venue and need G10/G12 to use that venue's fee and re-read /api/venues/<vid>/offers.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Optional

from agent.contracts import (RASTRO, TEAM, RIVAL_TOP_N, RIVAL_VENUE_MIN_GAIN, Intent, Prediction,
                             make_intent)

from agent.valuation import fee as _fee_m3, predict_swap, predict_team   # M3 (required: no M3 -> no tactic)

try:                                    # M4a; the Gate re-checks the fingerprint anyway (G10)
    from agent.guards import fingerprint as _fingerprint_m4   # type: ignore
except Exception:                       # pragma: no cover
    _fingerprint_m4 = None

INF = float("inf")
_NO = Prediction(neg_lo=-INF, neg_hi=-INF, ladder="0", cash=0, model="none")   # never passes a gain check
RARITY_MEDIAN = {"common": 9, "uncommon": 25, "rare": 70}     # R-02 medians: opening author price
SELL_TICKS = 60            # J5: relist after 60 ticks at -1
BID_TICKS = 120            # long bids (D3 converts to 15 s units in the Gate)
CLOSER_TICKS = 240
SWAP_TICKS = 60
MAX_LISTINGS = 4           # own cap per tick (Gate G04 is the hard one)
MAX_SWAPS = 2
ROUND_TRIP_TICKS = 60


# ----------------------------------------------------------------------------------------- helpers

def _c(cfg: Any, name: str, default: Any) -> Any:
    v = getattr(cfg, name, None)
    if v is None and isinstance(cfg, Mapping):
        v = cfg.get(name)
    return default if v is None else v


def _fee(price: int, cards: int, fee_bps: int, per_card: int) -> int:
    """D2 fee, paid by the accepter: ceil(fee_bps/10000 * price + fee_per_card * cards) (M3 fee)."""
    return int(_fee_m3(price, cards, fee_bps, per_card))


def _pred_team(dv: float, price: int, side: str, we_accept: bool, venue: Mapping) -> Prediction:
    """P-03 with the fee of the venue (rastro: 500 bps + 1 per card). Unknown value -> a refusing prediction."""
    if not math.isfinite(dv):
        return _NO
    return predict_team(dv, int(price), side, we_accept, fee_bps=venue["fee_bps"], per_card=venue["fee_per_card"])


def _pred_swap(dv_in: float, dv_out: float, we_accept: bool, venue: Mapping) -> Prediction:
    """D1: V(received) - V(given) - fee (fee only when we accept; cards = 2, M3's conservative choice)."""
    if not (math.isfinite(dv_in) and math.isfinite(dv_out)):
        return _NO
    return predict_swap(dv_in, dv_out, we_accept, fee_bps=venue["fee_bps"], per_card=venue["fee_per_card"])


def _fingerprint(o: Mapping) -> str:
    if _fingerprint_m4 is not None:
        return _fingerprint_m4(o)
    raw = json.dumps([o.get("id"), o.get("give"), o.get("want"), o.get("to"), o.get("venue"),
                      o.get("expires_tick"), o.get("status")], sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _card_index(world) -> dict:
    """ref -> {set, rarity, book} from the catalog, completed by our own assets."""
    idx: dict = {}
    cat = world.catalog if isinstance(world.catalog, Mapping) else {}
    for s in cat.get("sets") or ():
        if not isinstance(s, Mapping):
            continue
        for c in s.get("cards") or ():
            if isinstance(c, Mapping) and isinstance(c.get("id"), str):
                idx[c["id"]] = {"set": s.get("id"), "rarity": c.get("rarity"), "book": c.get("book")}
    for a in (world.me or {}).get("assets") or ():
        if isinstance(a, Mapping) and a.get("kind") == "card" and isinstance(a.get("ref"), str):
            idx.setdefault(a["ref"], {"set": a.get("set"), "rarity": a.get("rarity"), "book": None})
    return idx


def _plan_refs(plan: Mapping, keys: tuple) -> frozenset:
    """Refs named in plan lists ([{ref, ...}] or [ref]) such as extra_needs / resale."""
    out = set()
    for k in keys:
        for e in plan.get(k) or ():
            r = e.get("ref") if isinstance(e, Mapping) else e
            if isinstance(r, str):
                out.add(r)
    return frozenset(out)


def _set_of(ref: str) -> str:
    return ref.split("-", 1)[0]


def _int(x: Any) -> Optional[int]:
    return x if type(x) is int else None


def _parse(o: Mapping) -> Optional[dict]:
    """Canonical reading of a single-card team offer, or None (fail closed: anything else is skipped).

    kinds: "sale" (they give 1 card, want cash), "bid" (they give cash, want 1 card type),
           "swap" (they give 1 card, want 1 card type or one specific asset of ours).
    """
    if not isinstance(o, Mapping):
        return None
    give, want = o.get("give"), o.get("want")
    if not isinstance(give, Mapping) or not isinstance(want, Mapping):
        return None
    allowed = {"cash", "assets", "types", "cards"}
    if set(give) - allowed or set(want) - allowed:
        return None
    g_cash, w_cash = give.get("cash") or 0, want.get("cash") or 0
    if type(g_cash) is not int or type(w_cash) is not int or g_cash < 0 or w_cash < 0:
        return None
    g_assets, w_assets = list(give.get("assets") or ()), list(want.get("assets") or ())
    if give.get("types") or give.get("cards"):
        return None
    w_types = list(want.get("types") or ())
    w_cards = list(want.get("cards") or ())
    want_ref = None
    if w_types or w_cards:
        if len(w_types) + len(w_cards) != 1:
            return None
        if w_types:
            t = w_types[0]
            if not isinstance(t, str) or not t.startswith("card:"):
                return None
            want_ref = t[5:]
        else:
            want_ref = w_cards[0] if isinstance(w_cards[0], str) else None
            if want_ref is None:
                return None

    def one_card(lst):
        if len(lst) != 1 or not isinstance(lst[0], Mapping):
            return None
        a = lst[0]
        if a.get("kind") != "card" or not isinstance(a.get("ref"), str) or _int(a.get("id")) is None:
            return None
        return a

    if g_assets and not g_cash and w_cash > 0 and not w_assets and want_ref is None:
        a = one_card(g_assets)
        return None if a is None else {"kind": "sale", "ref": a["ref"], "price": w_cash}
    if g_cash > 0 and not g_assets and not w_cash and not w_assets and want_ref:
        return {"kind": "bid", "ref": want_ref, "price": g_cash}
    if g_assets and not g_cash and not w_cash:
        a = one_card(g_assets)
        if a is None:
            return None
        if want_ref and not w_assets:
            return {"kind": "swap", "ref": a["ref"], "want_ref": want_ref, "want_asset": None, "price": 0}
        if not want_ref and len(w_assets) == 1:
            wa = w_assets[0]
            wid = wa.get("id") if isinstance(wa, Mapping) else wa
            if _int(wid) is None:
                return None
            return {"kind": "swap", "ref": a["ref"], "want_ref": None, "want_asset": wid, "price": 0}
    return None


# ------------------------------------------------------------------------------------------ context

class _Ctx:
    def __init__(self, world, book, valuer, cfg, plan_cfg, needs, state):
        self.w, self.b, self.v, self.cfg, self.plan = world, book, valuer, cfg, plan_cfg or {}
        self.needs = {n.ref: n for n in (needs or ())}
        self.state = state if isinstance(state, dict) else {}
        self.idx = _card_index(world)
        self.out: list = []
        self.claimed: set = set()          # refs acquired by a route proposed this tick (INV-08)
        self.used_assets: set = set()      # assets handed over / listed this tick
        self.listings = 0
        self.cash_free = int(book.cash_free)
        self.accepts = 0
        self.max_accepts = max(0, int(getattr(world.limits, "accepts", 1)))
        cl = self.plan.get("closer") or {}
        self.accept_min = float(cl.get("accept_min", _c(cfg, "CLOSER_ACCEPT_MIN", 20.0)))
        self.default_minus = float(cl.get("default_minus", 50))
        self.compete_minus = float(cl.get("compete_minus", 20))
        self.endgame_hours = cl.get("endgame_hours") or {}
        self.min_team = float(_c(cfg, "MIN_GAIN_TEAM", 3.0))
        self.min_maker = float(_c(cfg, "MIN_GAIN_MAKER", 2.0))
        self.resupply_min = float(self.plan.get("resupply_min", _c(cfg, "RESUPPLY_MIN", 15.0)))
        self.rival_min = float(_c(cfg, "RIVAL_VENUE_MIN_GAIN", RIVAL_VENUE_MIN_GAIN))
        self.rival_top = int(_c(cfg, "RIVAL_TOP_N", RIVAL_TOP_N))
        self.dup_min = dict(self.plan.get("dup_min_price") or {})
        self.not_spare = _plan_refs(self.plan, ("extra_needs", "resale"))   # bought for dealers: never El Rastro
        self.page_sets = frozenset(self.plan.get("page_sets") or ())
        self.buy_any = self._buy_any_on()
        self.venues = self._venues()
        self.own_ids = set(book.own_offer_ids) | {o.get("id") for o in world.my_offers if isinstance(o, Mapping)}
        self.own_makers = {TEAM} | ({world.own_pseudonym} if world.own_pseudonym else set())
        open_cap = int(getattr(world.limits, "open_offers", 30)) - int(_c(cfg, "OPEN_OFFERS_MARGIN", 4))
        self.open_room = open_cap - sum(1 for o in world.my_offers
                                        if isinstance(o, Mapping) and o.get("status") in ("open", "queued"))
        self.own_bids, self.own_swaps = self._own_offers()
        self.proj = self._proj_without_own()

    # --- venues (D2)
    def _venues(self) -> dict:
        out = {}
        for vn in self.w.venues or ():
            if not isinstance(vn, Mapping):
                continue
            vid = vn.get("id") or vn.get("venue")
            fb, fpc = vn.get("fee_bps"), vn.get("fee_per_card")
            if not isinstance(vid, str) or type(fb) is not int or type(fpc) is not int or fb < 0 or fpc < 0:
                continue
            out[vid] = {"id": vid, "owner": vn.get("owner"), "fee_bps": fb, "fee_per_card": fpc,
                        "status": vn.get("status")}
        if RASTRO not in out:                                  # R-01: 5 % + 1 per card
            out[RASTRO] = {"id": RASTRO, "owner": None, "fee_bps": 500, "fee_per_card": 1, "status": "open"}
        return out

    def venue_ok(self, vid: Any) -> Optional[dict]:
        """Venue where we may ACCEPT, with its fee; None = refuse."""
        vn = self.venues.get(vid) if isinstance(vid, str) else None
        if vn is None or vn.get("status") not in ("open", None):
            return None
        if vid == RASTRO:
            return vn
        owner = vn.get("owner")
        if owner == TEAM or not isinstance(owner, str):       # INV-20: never our own venue
            return None
        lb = tuple(self.w.leaderboard or ())
        if not lb or "leaderboard" in self.w.down:            # unknown leaderboard -> fail closed
            return None
        if owner in lb[: self.rival_top]:
            return None
        return vn

    def min_gain(self, vid: str, base: float) -> float:
        return base if vid == RASTRO else max(base, self.rival_min)

    # --- own standing offers
    def _own_offers(self):
        bids, swaps = {}, {}
        for o in self.w.my_offers:
            if not isinstance(o, Mapping) or o.get("status") not in ("open", "queued"):
                continue
            p = _parse(o)
            if p is None:
                continue
            if p["kind"] == "bid":
                bids[p["ref"]] = (o.get("id"), p["price"])
            elif p["kind"] == "swap" and p["want_ref"]:
                swaps[p["want_ref"]] = o.get("id")
        for ref, oid in (self.b.own_bids or {}).items():
            if ref not in bids:
                bids[ref] = (oid, int((self.b.bid_price or {}).get(oid, 0)))
        return bids, swaps

    def _proj_without_own(self) -> dict:
        """Book.projected without the copy of our OWN standing bid / swap (guards.build_book adds +1 per want ref):
        the closer and a switch value the card as if our offer had not filled (never below held, as
        hygiene._counts_without). Without this, RET-05 with our closer bid up read as a 2nd copy (3.25, not 99.1)."""
        c = {k: int(v or 0) for k, v in (self.b.projected or {}).items()}
        for ref in set(self.own_bids) | set(self.own_swaps):
            if isinstance(ref, str):
                c[ref] = max(c.get(ref, 0) - 1, self.counts(self.b.held, ref))
        return c

    # --- values
    def counts(self, m: Mapping, ref: str) -> int:
        return int((m or {}).get(ref, 0))

    def your_value(self, ref: str) -> float:
        best = -INF
        for a in (self.w.me or {}).get("assets") or ():
            if isinstance(a, Mapping) and a.get("ref") == ref and type(a.get("your_value")) in (int, float):
                best = max(best, float(a["your_value"]))
        return best

    def dv_add(self, ref: str) -> float:
        """Value of one more copy; -inf when unknown (UnknownCard etc.): every buy then fails closed."""
        try:
            d = float(self.v.delta_add(self.proj, ref, self.b.packs))
        except Exception:
            return -INF
        if not math.isfinite(d):
            return -INF
        sv = (self.w.server_values or {}).get(ref)
        return min(d, float(sv)) if type(sv) in (int, float) else d

    def dv_rm(self, ref: str) -> float:
        """Value lost giving one copy; +inf when unknown: every sale then fails closed."""
        try:
            d = float(self.v.delta_remove(self.b.held, ref, self.b.packs))
        except Exception:
            return INF
        return max(d, self.your_value(ref)) if math.isfinite(d) else INF

    def free(self, ref: str) -> int:
        return (self.counts(self.b.held, ref) - self.counts(self.b.listed, ref)
                - self.counts(self.b.pending_out, ref)
                - sum(1 for a in self.used_assets if self.asset_ref(a) == ref))

    def keep(self, ref: str) -> int:
        return self.counts(self.b.keep, ref)

    def asset_ref(self, aid: int) -> Optional[str]:
        for a in (self.w.me or {}).get("assets") or ():
            if isinstance(a, Mapping) and a.get("id") == aid:
                return a.get("ref")
        return None

    def spare_asset(self, ref: str) -> Optional[int]:
        """A copy of `ref` we may hand over: never a protected copy (INV-06), never one already listed."""
        if self.free(ref) - 1 < self.keep(ref):
            return None
        for a in sorted(((self.w.me or {}).get("assets") or ()),
                        key=lambda a: -(a.get("id") or 0) if isinstance(a, Mapping) else 0):
            if (isinstance(a, Mapping) and a.get("kind") == "card" and a.get("ref") == ref
                    and type(a.get("id")) is int and a["id"] not in self.b.listed_assets
                    and a["id"] not in self.used_assets):
                return a["id"]
        return None

    def can_acquire(self, ref: str) -> bool:
        """INV-08: no other route to `ref` (own bid, own swap, thread, unsettled accept, this tick)."""
        if ref in self.claimed or ref in self.own_bids or ref in self.own_swaps:
            return False
        return self.counts(self.b.paths, ref) == 0

    def round_trip(self, ref: str, side: str) -> bool:
        rec = (self.b.recent_rastro or {}).get(ref)
        if not rec:
            return False
        rside, rtick = rec
        opposite = "sell" if side == "buy" else "buy"
        return rside == opposite and self.w.tick - int(rtick) < ROUND_TRIP_TICKS

    def offer_live(self, o: Mapping) -> bool:
        if not isinstance(o, Mapping) or o.get("status") != "open" or _int(o.get("id")) is None:
            return False
        exp = o.get("expires_tick")
        if exp is not None and (type(exp) is not int or exp < self.w.tick + 1):
            return False
        if o["id"] in self.own_ids or o.get("maker") in self.own_makers:
            return False
        return o.get("to") in (None, TEAM)

    def offer_live_any(self, o: Mapping) -> bool:
        """A live rival offer (for competition detection: `to` does not matter)."""
        if not isinstance(o, Mapping) or o.get("status") != "open":
            return False
        exp = o.get("expires_tick")
        if exp is not None and (type(exp) is not int or exp < self.w.tick + 1):
            return False
        return o.get("id") not in self.own_ids and o.get("maker") not in self.own_makers

    def _buy_any_on(self) -> bool:
        """M9 endgame buy-any: plan.endgame_buy_any and (dealer day ended or closer endgame). Error -> off."""
        if self.plan.get("endgame_buy_any") is not True:
            return False
        try:
            from agent.tactics.pages import past_day_end
            return bool(past_day_end(self.w, self.plan)) or self.endgame()
        except Exception:
            return False

    def endgame(self) -> bool:
        eh = self.endgame_hours
        if not isinstance(eh, Mapping):
            return False
        h = eh.get(self.w.reading, eh.get("*"))
        return type(h) in (int, float) and float(self.w.t_hours) >= float(h)

    def add(self, kind, tactic, args, reason, effect, pred, priority) -> Optional[Intent]:
        try:
            it = make_intent(kind, tactic, args, reason, effect, pred, priority)
        except ValueError:
            return None
        self.out.append(it)
        return it


def _offers(world) -> list:
    """(venue id, offer) for every open board (D2) and the offers addressed to us; each id once."""
    seen, out = set(), []
    boards = dict(world.boards or {})
    if RASTRO not in boards:
        boards[RASTRO] = world.board
    for vid, offers in boards.items():
        for o in offers or ():
            if isinstance(o, Mapping) and o.get("id") not in seen:
                seen.add(o.get("id"))
                out.append((o.get("venue") or vid, o))
    for o in world.offers_to_us or ():
        if isinstance(o, Mapping) and o.get("id") not in seen:
            seen.add(o.get("id"))
            out.append((o.get("venue"), o))
    return out


# ------------------------------------------------------------------------------------------ tactics

def _accept(cx: _Ctx, o, vn, side, ref, price, give_asset, resupply, tactic, reason, pred, prio) -> bool:
    if cx.accepts >= cx.max_accepts:
        return False
    args = {"offer_id": o["id"], "source": "team", "ref": ref, "side": side, "price": int(price),
            "thread_id": None, "give_asset": give_asset, "fingerprint": _fingerprint(o),
            "resupply": bool(resupply), "venue": vn["id"]}
    it = cx.add("accept", tactic, args, reason, f"{side} {ref} @{price} on {vn['id']}", pred, prio)
    if it is None:
        return False
    cx.accepts += 1
    if side in ("buy", "swap"):
        cx.claimed.add(ref)
    if give_asset is not None:
        cx.used_assets.add(give_asset)
    if side == "buy":
        cx.cash_free -= int(-pred.cash)
    return True


def _cancel(cx: _Ctx, offer_id: int, ref: str, tactic: str, why: str, prio: int) -> None:
    if cx.listings >= MAX_LISTINGS:
        return
    if cx.add("cancel", tactic, {"offer_id": int(offer_id), "ref": ref}, why, f"cancel {offer_id}",
              Prediction(0.0, 0.0, "0", 0, model="none"), prio):
        cx.listings += 1


def _list(cx: _Ctx, args: dict, tactic: str, why: str, pred: Prediction, prio: int) -> bool:
    if cx.listings >= MAX_LISTINGS or cx.open_room <= 0:
        return False
    if cx.add("list_offer", tactic, args, why, f"{args['side']} {args['ref']} @{args['price']}", pred, prio):
        cx.listings += 1
        cx.open_room -= 1
        return True
    return False


def _rastro_venue(cx: _Ctx) -> dict:
    return cx.venues[RASTRO]


def _buy_ok(cx: _Ctx, vid: str, ref: str, price: int, gain_lo: float) -> bool:
    need = cx.needs.get(ref)
    if need is None or price > need.max_price or cx.round_trip(ref, "buy"):
        return False
    closes = bool(cx.v.closes_page(cx.proj, ref))
    base = cx.accept_min if closes else cx.min_team
    return gain_lo >= cx.min_gain(vid, base)


def _any_ok(cx: _Ctx, vid: str, ref: str, gain_lo: float) -> bool:
    """M9: once the dealer day has ended (or in the endgame) a first copy of a card outside the page sets is worth
    buying from a team below our value: cash held at the freeze scores 0. Page-set refs keep their Needs only."""
    return (cx.buy_any and _set_of(ref) not in cx.page_sets and cx.counts(cx.proj, ref) == 0
            and cx.counts(cx.b.held, ref) == 0 and not cx.round_trip(ref, "buy")
            and gain_lo >= cx.min_gain(vid, cx.min_team))


def _j4_closer(cx: _Ctx, offers: list) -> None:
    """J4: the frozen closer card of each page set (a Need with closer=True that closes the page)."""
    st = cx.state.setdefault("closer", {})
    for ref, need in cx.needs.items():
        if not need.closer or not cx.v.closes_page(cx.proj, ref):
            continue
        rec = st.setdefault(ref, {"floor": 0, "pending": None})
        if not math.isfinite(cx.dv_add(ref)):
            continue
        if rec.get("pending"):                       # two-step switch in flight: wait for it
            cx.claimed.add(ref)
            continue
        dv = cx.dv_add(ref)
        own = cx.own_bids.get(ref)
        if own:
            rec["floor"] = max(int(rec.get("floor") or 0), int(own[1]))
        # 1) a sale with neg_lo >= accept_min: accept now, or cancel our bid first (accept in T+1)
        best = None
        for vid, o in offers:
            p = _parse(o)
            if p is None or p["kind"] != "sale" or p["ref"] != ref or not cx.offer_live(o):
                continue
            vn = cx.venue_ok(vid)
            if vn is None:
                continue
            pred = _pred_team(dv, p["price"], "buy", True, vn)
            if pred.neg_lo < cx.min_gain(vn["id"], cx.accept_min) or -pred.cash > cx.cash_free:
                continue
            if p["price"] > need.max_price and need.max_price > 0:
                continue
            if best is None or pred.neg_hi > best[2].neg_hi:
                best = (o, vn, pred, p)
        if best is not None and not cx.round_trip(ref, "buy"):
            o, vn, pred, p = best
            if own:
                _cancel(cx, own[0], ref, "closer", "J4: switch bid -> board sale (cancel, then accept T+1)", 95)
                rec["pending"] = {"what": "accept", "offer": o["id"], "tick": cx.w.tick}
                cx.claimed.add(ref)
                continue
            if cx.counts(cx.b.paths, ref) == 0 and ref not in cx.claimed and ref not in cx.own_swaps:
                _accept(cx, o, vn, "buy", ref, p["price"], None, False, "closer",
                        f"J4: closer sale neg_lo {pred.neg_lo:.1f}", pred, 100)
            continue
        # 2-3) bid; raise with competition or in the endgame; never lower
        if cx.b.delivery_risk or cx.b.packs or _hygiene_risk(cx):
            continue
        compete = cx.endgame()
        for vid, o in offers:
            p = _parse(o)
            if (p and p["kind"] == "bid" and p["ref"] == ref and cx.offer_live_any(o)
                    and p["price"] >= (own[1] if own else int(math.floor(dv - cx.default_minus)))):
                compete = True
        target = int(math.floor(dv - (cx.compete_minus if compete else cx.default_minus)))
        target = max(target, int(rec.get("floor") or 0))
        cap = int(math.floor(dv - cx.accept_min))                 # G21 ceiling for a closer bid
        target = min(target, cap)
        if own:
            if target > own[1] and cx.cash_free + own[1] >= target:
                _cancel(cx, own[0], ref, "closer", f"J4: raise {own[1]} -> {target} (competition)", 90)
                rec["pending"] = {"what": "raise", "price": target, "tick": cx.w.tick}
            cx.claimed.add(ref)
            continue
        if cx.counts(cx.b.paths, ref) or ref in cx.claimed or ref in cx.own_swaps:
            continue
        price = min(target, cx.cash_free)
        if price < int(rec.get("floor") or 0) or price < 1:        # never lower than what we already stood at
            continue
        args = {"side": "bid", "ref": ref, "asset_id": None, "price": int(price),
                "expires_ticks": CLOSER_TICKS, "closer": True, "want_ref": None}
        pred = _pred_team(dv, int(price), "buy", False, _rastro_venue(cx))
        if _list(cx, args, "closer", f"J4: closer bid {price} (dv_add {dv:.1f})", pred, 92):
            rec["floor"] = max(int(rec.get("floor") or 0), int(price))
            rec["pending"] = None
            cx.claimed.add(ref)
            cx.cash_free -= int(price)


def _j6_buys(cx: _Ctx, offers: list) -> None:
    """J6: accept sales of plan cards with gain after the venue fee; own bid -> cancel, accept next tick."""
    st = cx.state.setdefault("switch", {})
    cands = []
    for vid, o in offers:
        p = _parse(o)
        if p is None or p["kind"] != "sale" or not cx.offer_live(o):
            continue
        ref = p["ref"]
        need = cx.needs.get(ref)
        if need is not None and need.closer:
            continue
        if need is None and not cx.buy_any:
            continue
        vn = cx.venue_ok(vid)
        if vn is None:
            continue
        pred = _pred_team(cx.dv_add(ref), p["price"], "buy", True, vn)
        ok = (_buy_ok(cx, vn["id"], ref, p["price"], pred.neg_lo) if need is not None
              else _any_ok(cx, vn["id"], ref, pred.neg_lo))
        if not ok or -pred.cash > cx.cash_free:
            continue
        cands.append((pred.neg_hi, o, vn, pred, p))
    for _, o, vn, pred, p in sorted(cands, key=lambda c: -c[0]):
        ref = p["ref"]
        if ref in st:                                # switch in flight
            continue
        own = cx.own_bids.get(ref)
        if own and ref not in cx.claimed:
            _cancel(cx, own[0], ref, "rastro", "J6: switch own bid -> board sale", 70)
            st[ref] = {"offer": o["id"], "tick": cx.w.tick}
            cx.claimed.add(ref)
            continue
        if not cx.can_acquire(ref) or -pred.cash > cx.cash_free:
            continue
        _accept(cx, o, vn, "buy", ref, p["price"], None, False, "rastro",
                f"J6: buy gain {pred.neg_lo:.1f} after fee", pred, 60)


def _sell_into_bids(cx: _Ctx, offers: list) -> None:
    """Sell spares into rival bids (gain >= MIN_GAIN_TEAM); J13 resupply with all its conditions."""
    cands = []
    for vid, o in offers:
        p = _parse(o)
        if p is None or p["kind"] != "bid" or not cx.offer_live(o):
            continue
        ref = p["ref"]
        if cx.counts(cx.b.held, ref) < 1 or cx.round_trip(ref, "sell"):
            continue
        if p["price"] < int(cx.dup_min.get(_set_of(ref), 0)):      # J5: RET/CHA copies never below 30
            continue
        vn = cx.venue_ok(vid)
        if vn is None:
            continue
        pred = _pred_team(cx.dv_rm(ref), p["price"], "sell", True, vn)
        resupply = False
        if cx.spare_asset(ref) is None:
            if not _j13_ok(cx, o, ref):
                continue
            resupply = True
            if pred.neg_lo < cx.min_gain(vn["id"], cx.resupply_min):
                continue
        elif pred.neg_lo < cx.min_gain(vn["id"], cx.min_team):
            continue
        cands.append((pred.neg_hi, o, vn, pred, p, resupply))
    for _, o, vn, pred, p, resupply in sorted(cands, key=lambda c: -c[0]):
        ref = p["ref"]
        aid = cx.spare_asset(ref) if not resupply else _any_copy(cx, ref)
        if aid is None:
            continue
        _accept(cx, o, vn, "sell", ref, p["price"], aid, resupply, "rastro",
                ("J13 resupply" if resupply else "sell spare into bid") + f" gain {pred.neg_lo:.1f}", pred,
                65 if resupply else 55)


def _any_copy(cx: _Ctx, ref: str) -> Optional[int]:
    for a in (cx.w.me or {}).get("assets") or ():
        if (isinstance(a, Mapping) and a.get("kind") == "card" and a.get("ref") == ref
                and type(a.get("id")) is int and a["id"] not in cx.b.listed_assets
                and a["id"] not in cx.used_assets):
            return a["id"]
    return None


def _hygiene_risk(cx: _Ctx) -> bool:
    """hygiene.delivery_risk, the predicate that cancels a standing closer bid: never place a bid hygiene would
    cancel the next tick (Sat 19:08-19:44: four closer bids listed then cancelled). Missing module -> risk."""
    try:
        from agent.tactics import hygiene
        return bool(hygiene.delivery_risk(cx.w, cx.b, cx.plan))
    except Exception:  # noqa: BLE001 - fail closed
        return True


def _j13_ok(cx: _Ctx, o: Mapping, ref: str) -> bool:
    """G13 resupply exception: every condition, or no."""
    if cx.endgame():          # no time left to buy it back from the Abuela (dealer Needs stop at day end)
        return False
    s = _set_of(ref)
    info = cx.idx.get(ref) or {}
    if s not in ("RET", "CHA") or info.get("rarity") not in ("common", "uncommon"):
        return False
    if cx.free(ref) < 1 or cx.b.packs:
        return False
    if (cx.b.frozen_closer or {}).get(s) == ref:
        return False
    page = sum(1 for r, n in (cx.b.projected or {}).items() if n and _set_of(r) == s)
    if page >= 9:
        return False
    if "abuela" in (cx.b.dealer_block or {}) or int((cx.b.dealer_deals_hour or {}).get("abuela", 0)) > 6:
        return False
    exp = o.get("expires_tick")
    if type(exp) is not int or exp < cx.w.tick + 2:
        return False
    return True


def _swaps_accept(cx: _Ctx, offers: list) -> None:
    """D1: rival gives card X and wants a card type (or one of our assets). V(in) - V(out) - fee."""
    cands = []
    for vid, o in offers:
        p = _parse(o)
        if p is None or p["kind"] != "swap" or not cx.offer_live(o):
            continue
        vn = cx.venue_ok(vid)
        if vn is None:
            continue
        rin = p["ref"]
        if p["want_asset"] is not None:
            aid = p["want_asset"]
            rout = cx.asset_ref(aid)
            if rout is None or aid in cx.b.listed_assets or cx.free(rout) - 1 < cx.keep(rout):
                continue
        else:
            rout = p["want_ref"]
            aid = cx.spare_asset(rout)
            if aid is None:
                continue
        if rin == rout or cx.round_trip(rin, "buy") or cx.round_trip(rout, "sell"):
            continue
        pred = _pred_swap(cx.dv_add(rin), cx.dv_rm(rout), True, vn)
        if -pred.cash > cx.cash_free:
            continue
        base = cx.accept_min if cx.v.closes_page(cx.proj, rin) else cx.min_team
        if pred.neg_lo < cx.min_gain(vn["id"], base):
            continue
        cands.append((pred.neg_hi, o, vn, pred, rin, aid))
    for _, o, vn, pred, rin, aid in sorted(cands, key=lambda c: -c[0]):
        rout = cx.asset_ref(aid)
        if not cx.can_acquire(rin) or aid in cx.used_assets or rout is None or cx.free(rout) - 1 < cx.keep(rout):
            continue
        if _accept(cx, o, vn, "swap", rin, 0, aid, False, "rastro",
                   f"D1 swap {rout} -> {rin} gain {pred.neg_lo:.1f}", pred, 58):
            cx.cash_free += pred.cash


SPARE_RARITIES = ("common", "uncommon", "rare")   # epics / legendaries are never a spare (dealer resale, prestige)


def _spares(cx: _Ctx) -> list:
    """Refs with a copy we may hand over, cheapest to lose first. Never an epic / legendary / unknown rarity, never
    a ref the plan buys for resale to dealers (extra_needs, resale: SAL-11 was listed on El Rastro at V+2)."""
    refs = sorted({a.get("ref") for a in (cx.w.me or {}).get("assets") or ()
                   if isinstance(a, Mapping) and a.get("kind") == "card" and isinstance(a.get("ref"), str)})
    refs = [r for r in refs if (cx.idx.get(r) or {}).get("rarity") in SPARE_RARITIES and r not in cx.not_spare]
    out = [(cx.dv_rm(r), r) for r in refs if cx.spare_asset(r) is not None and r not in cx.needs]
    out = [x for x in out if math.isfinite(x[0])]
    return sorted(out)


def _long_bids_and_swaps(cx: _Ctx) -> None:
    """Team-sourced non-closer needs: one long bid (D3) or, without cash, one swap (D1). INV-08."""
    if cx.b.packs:
        return
    swaps = 0
    rv = _rastro_venue(cx)
    for ref, need in sorted(cx.needs.items()):
        if need.closer or need.source != "team" or not cx.can_acquire(ref) or cx.round_trip(ref, "buy"):
            continue
        dv = cx.dv_add(ref)
        if not math.isfinite(dv):
            continue
        price = min(int(need.max_price), int(math.floor(dv - cx.min_team)), cx.cash_free)
        if cx.v.closes_page(cx.proj, ref):
            price = min(price, int(math.floor(dv - cx.accept_min)))
        if price >= 1:
            args = {"side": "bid", "ref": ref, "asset_id": None, "price": int(price),
                    "expires_ticks": BID_TICKS, "closer": False, "want_ref": None}
            if _list(cx, args, "rastro", f"long bid for need {ref} (D3)",
                     _pred_team(dv, int(price), "buy", False, rv), 40):
                cx.claimed.add(ref)
                cx.cash_free -= int(price)
            continue
        if swaps >= MAX_SWAPS:
            continue
        for v_out, rout in _spares(cx):
            g = dv - v_out
            if g < cx.min_maker or rout == ref:
                continue
            aid = cx.spare_asset(rout)
            args = {"side": "swap", "ref": rout, "asset_id": aid, "price": 0, "expires_ticks": SWAP_TICKS,
                    "closer": False, "want_ref": ref}
            if _list(cx, args, "rastro", f"D1 swap offer {rout} for {ref}", _pred_swap(dv, v_out, False, rv), 30):
                cx.claimed.add(ref)
                cx.used_assets.add(aid)
                swaps += 1
            break


def _j5_sales(cx: _Ctx) -> None:
    """J5: list spares as author (no fee for the maker). Duplicates of RET/CHA never below dup_min_price."""
    mem = cx.state.setdefault("sell_price", {})
    aff = (cx.w.me or {}).get("affinity") or {}
    listed_refs = set()
    for o in cx.w.my_offers:
        p = _parse(o) if isinstance(o, Mapping) and o.get("status") in ("open", "queued") else None
        if p and p["kind"] == "sale":
            listed_refs.add(p["ref"])
    rv = _rastro_venue(cx)
    for v_out, ref in _spares(cx):
        if ref in listed_refs or cx.round_trip(ref, "sell"):
            continue
        aid = cx.spare_asset(ref)
        if aid is None:
            continue
        info = cx.idx.get(ref) or {}
        s = info.get("set") or _set_of(ref)
        floor_p = int(math.ceil(v_out + 2))
        floor_p = max(floor_p, int(cx.dup_min.get(s, 0)))
        prev = mem.get(ref)
        start = max(floor_p, RARITY_MEDIAN.get(info.get("rarity"), floor_p))
        price = max(floor_p, int(prev) - 1) if type(prev) is int else start
        book_v, a = info.get("book"), aff.get(s, 1.0)
        if type(book_v) in (int, float) and type(a) in (int, float):
            cap = int(math.floor(4 * book_v * a))
            if price > cap:
                price = cap
            if price < floor_p:
                continue
        pred = _pred_team(v_out, int(price), "sell", False, rv)
        if pred.neg_lo < cx.min_maker:
            continue
        args = {"side": "sell", "ref": ref, "asset_id": aid, "price": int(price), "expires_ticks": SELL_TICKS,
                "closer": False, "want_ref": None}
        if _list(cx, args, "rastro", f"J5 sell spare {ref} @{price}", pred, 20):
            mem[ref] = int(price)
            cx.used_assets.add(aid)


def _pending_steps(cx: _Ctx, offers: list) -> None:
    """Second half of the two-step switches: our bid is gone -> act (cancel -> verify -> act)."""
    by_id = {o.get("id"): (vid, o) for vid, o in offers}
    st = cx.state.get("closer") or {}
    for ref, rec in st.items():
        pend = rec.get("pending") if isinstance(rec, dict) else None
        if not pend or pend.get("tick") == cx.w.tick:
            continue
        if ref in cx.own_bids:                         # cancel not seen yet: wait (stale after 5 ticks)
            if cx.w.tick - int(pend.get("tick", 0)) > 5:
                rec["pending"] = None
            continue
        rec["pending"] = None
        if pend.get("what") == "accept" and pend.get("offer") in by_id:
            vid, o = by_id[pend["offer"]]
            p, vn = _parse(o), cx.venue_ok(vid)
            if p and p["kind"] == "sale" and p["ref"] == ref and vn and cx.offer_live(o) and cx.can_acquire(ref):
                pred = _pred_team(cx.dv_add(ref), p["price"], "buy", True, vn)
                if pred.neg_lo >= cx.min_gain(vn["id"], cx.accept_min) and -pred.cash <= cx.cash_free:
                    _accept(cx, o, vn, "buy", ref, p["price"], None, False, "closer",
                            f"J4: accept after cancel, neg_lo {pred.neg_lo:.1f}", pred, 100)
        elif pend.get("what") == "raise":
            price = int(pend.get("price", 0))
            if not math.isfinite(cx.dv_add(ref)):
                continue
            if (cx.can_acquire(ref) and not cx.b.delivery_risk and not cx.b.packs and 1 <= price <= cx.cash_free
                    and price >= int(rec.get("floor") or 0)):
                dv = cx.dv_add(ref)
                if price <= int(math.floor(dv - cx.accept_min)):
                    args = {"side": "bid", "ref": ref, "asset_id": None, "price": price,
                            "expires_ticks": CLOSER_TICKS, "closer": True, "want_ref": None}
                    if _list(cx, args, "closer", f"J4: raised closer bid {price}",
                             _pred_team(dv, price, "buy", False, _rastro_venue(cx)), 92):
                        rec["floor"] = max(int(rec.get("floor") or 0), price)
                        cx.claimed.add(ref)
                        cx.cash_free -= price
    sw = cx.state.get("switch") or {}
    for ref in list(sw):
        pend = sw[ref]
        if pend.get("tick") == cx.w.tick:
            continue
        if ref in cx.own_bids:
            if cx.w.tick - int(pend.get("tick", 0)) > 5:
                del sw[ref]
            continue
        del sw[ref]
        if pend.get("offer") in by_id:
            vid, o = by_id[pend["offer"]]
            p, vn = _parse(o), cx.venue_ok(vid)
            if p and p["kind"] == "sale" and vn and cx.offer_live(o) and cx.can_acquire(ref):
                pred = _pred_team(cx.dv_add(ref), p["price"], "buy", True, vn)
                if _buy_ok(cx, vn["id"], ref, p["price"], pred.neg_lo) and -pred.cash <= cx.cash_free:
                    _accept(cx, o, vn, "buy", ref, p["price"], None, False, "rastro",
                            f"J6: accept after cancel, gain {pred.neg_lo:.1f}", pred, 60)




# ------------------------------------------------------------------------------------------ entry

def propose(world, book, valuer, cfg, plan_cfg, needs, state) -> list:
    """J4 (tactic "closer"), J5, J6, J9, J13 and D1-D3 (tactic "rastro"). Fail closed: [] on bad inputs."""
    if world is None or book is None or valuer is None or not getattr(book, "valuation_ok", False):
        return []
    if world.down & {"me", "me/offers", "me/threads", "board", "clock"}:
        return []
    if book.packs:                                   # G14 / INV-09: unopened pack -> no trades at all
        return []
    cx = _Ctx(world, book, valuer, cfg, plan_cfg, needs, state)
    offers = _offers(world)
    steps = (_pending_steps, _j4_closer, _j6_buys, _swaps_accept, _sell_into_bids)
    for step in steps:
        step(cx, offers)
    _long_bids_and_swaps(cx)
    _j5_sales(cx)
    return cx.out
