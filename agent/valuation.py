"""M3 valuation: the measured value model (V-01, V-02), fees (R-01) and predictions (P-03, P-04, P-08, U-01).

No file, network or clock I/O: everything comes in as arguments (catalog, affinity, released sets, counts).
Rewritten from logs/analysis/scoring/verify/vlib.py without its fixed paths and fixed RELEASED list.

NOTES (M3, night build)
- Copy marginals and page bonus come from catalog["values"]; a catalog without them -> ValueError (fail closed:
  no Valuer means valuation_ok = False upstream).
- 4th+ copy (never measured, V-10): worth 0 when we BUY it, MARG[-1] when we SELL it. collection_value() itself
  uses MARG[-1] (the vlib model), delta_add() uses the buy view, delta_remove() the sell view.
- master_bonus (V-10, V-13): master_bonus x sum(base) of the set's 10 page cards + epic + legendary once each is held
  (affinity sets). Measured Sat t950: server value?card SAL-12 593.5 = model with it (495 without) -> self_check needs it.
- Pack slots draw from the released sets only, weighted by print_run - minted (V-02); `minted` defaults to the
  catalog's per-card "minted". A pack type that is not in the catalog -> UnknownPack (INV-19: valuation_ok = False).
- An unknown card ref, or a set without affinity -> UnknownCard (a KeyError): callers refuse, never guess.
- Late inputs: fee() takes the venue fee parameters (D2) and venue_fee() reads them from a World.venues row
  (fail closed on a malformed row); predict_team() takes fee_bps / per_card / cards keywords (defaults = El Rastro).
  Swaps (D1): Valuer.delta_swap() (V received - V given, sequential so a same-set page is handled) and
  predict_swap(). The fee of a swap (price 0) is assumed to count BOTH cards (cards=2) until measured: the
  conservative choice (larger fee, smaller predicted gain).
- verdict() thresholds are ours (the spec names the four outcomes only): tolerance 0.1 (display rounding 0.05),
  shortfall <= 1.0 -> soft_fail, a larger shortfall, a predicted non-loss that measures a loss, a falling ladder
  or a non-finite input -> hard_fail.
- Duel results with a negative surplus are unmeasured (U-01 only positive): predict_duel returns the signed
  surplus so the guards refuse it.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Iterable, Mapping, Optional

from agent.contracts import Prediction

__all__ = ["UnknownPack", "UnknownCard", "Valuer", "fee", "venue_fee", "predict_team", "predict_swap",
           "predict_dealer", "predict_duel", "predict_none", "verdict"]


class UnknownPack(Exception):
    """A pack type that the catalog does not describe (or that cannot be valued)."""


class UnknownCard(KeyError):
    """A card ref that the catalog / affinity does not describe."""


def _finite(x: Any) -> bool:
    return type(x) in (int, float) and math.isfinite(x)


# ----------------------------------------------------------------------------------------------- Valuer

class Valuer:
    """Collection value model. Pure: holds only the catalog-derived tables."""

    def __init__(self, catalog: Mapping, affinity: Mapping[str, float], released_sets: frozenset):
        values = catalog.get("values") if isinstance(catalog, Mapping) else None
        if not isinstance(values, Mapping):
            raise ValueError("catalog without values")
        marg = values.get("copy_marginals")
        pb = values.get("page_bonus")
        mb = values.get("master_bonus", 0.0)
        if not (isinstance(marg, (list, tuple)) and marg and all(_finite(m) for m in marg) and _finite(pb)
                and _finite(mb)):
            raise ValueError("catalog values malformed")
        self.marg = tuple(float(m) for m in marg)
        self.page_bonus = float(pb)
        self.master_bonus = float(mb)
        self.affinity = {str(k): float(v) for k, v in dict(affinity).items() if _finite(v)}
        self.released_sets = frozenset(released_sets)
        self.cards: dict = {}          # ref -> {set, rarity, book, print_run, minted, page}
        self.pages: dict = {}          # set -> tuple of page refs
        self.masters: dict = {}        # set -> page refs + epic + legendary (from main 3a44692; server-matched Sat)
        for s in catalog.get("sets") or ():
            sid = s.get("id")
            page_refs = []
            top = {"epic": [], "legendary": []}
            for c in s.get("cards") or ():
                ref = c.get("id")
                if not isinstance(ref, str) or not _finite(c.get("book")):
                    continue
                # RULES: "the hidden card is prestige only: no dealer buys it" -> worth 0 (server value?card = 0,
                # live Sat LAT-13 La Chulapa Dorada; without this self_check failed and blocked every value write)
                self.cards[ref] = {"set": sid, "rarity": c.get("rarity"),
                                   "book": 0.0 if c.get("hidden") is True else float(c["book"]),
                                   "print_run": c.get("print_run"), "minted": c.get("minted"),
                                   "page": c.get("page") is True}
                if c.get("page") is True:
                    page_refs.append(ref)
                elif c.get("rarity") in top:
                    top[c["rarity"]].append(ref)
            self.pages[sid] = tuple(page_refs)
            if page_refs and top["epic"] and top["legendary"]:
                self.masters[sid] = tuple(page_refs) + tuple(top["epic"]) + tuple(top["legendary"])
        self.packs: dict = {}
        for p in catalog.get("packs") or ():
            if isinstance(p, Mapping) and isinstance(p.get("id"), str) and isinstance(p.get("slots"), list):
                self.packs[p["id"]] = p

    # --- helpers ---------------------------------------------------------------------------------
    @staticmethod
    def released_from_catalog(catalog: Mapping) -> frozenset:
        return frozenset(s.get("id") for s in (catalog.get("sets") or ()) if s.get("released") is True)

    def base(self, ref: str) -> float:
        c = self.cards.get(ref)
        if c is None or c["set"] not in self.affinity:
            raise UnknownCard(ref)
        return c["book"] * self.affinity[c["set"]]

    def _mg(self, k: int, side: str) -> float:      # k: 0-based copy index
        if k < len(self.marg):
            return self.marg[k]
        return 0.0 if side == "buy" else self.marg[-1]

    @staticmethod
    def holdings(me: Mapping) -> tuple:
        """(Counter of card refs, tuple of pack types) from a /api/me body."""
        counts: Counter = Counter()
        packs = []
        for a in (me.get("assets") or ()) if isinstance(me, Mapping) else ():
            if not isinstance(a, Mapping):
                continue
            ref = a.get("ref")
            if a.get("kind") == "card":
                if isinstance(ref, str):
                    counts[ref] += 1
            elif a.get("kind") == "pack":       # only a pack is a pack: an unknown asset kind is not valued here
                packs.append(ref if isinstance(ref, str) else "")
        return counts, tuple(packs)

    def copy_value(self, ref: str, k: int, *, side: str) -> float:
        """Value of the k-th copy (k = 1 for the first). 4th+: 0 when buying, MARG[-1] when selling."""
        if type(k) is not int or k < 1:
            raise ValueError("k must be an int >= 1")
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        return self.base(ref) * self._mg(k - 1, side)

    def page_card(self, ref: str) -> bool:
        c = self.cards.get(ref)
        return bool(c and c["page"])

    def _cards_total(self, counts: Mapping, side: str = "model") -> float:
        v = 0.0
        for ref, n in counts.items():
            if n and n > 0:
                b = self.base(ref)
                v += sum(b * self._mg(k, side) for k in range(int(n)))
        for sid, refs in self.pages.items():
            if refs and sid in self.affinity and all(counts.get(r, 0) > 0 for r in refs):
                v += self.page_bonus * sum(self.base(r) for r in refs)
        if self.master_bonus:
            for sid, refs in self.masters.items():
                if sid in self.affinity and all(counts.get(r, 0) > 0 for r in refs):
                    v += self.master_bonus * sum(self.base(r) for r in refs)
        return v

    def _slot_dist(self, rarity: str, minted: Optional[Mapping]) -> list:
        cands = [r for r, c in self.cards.items() if c["set"] in self.released_sets and c["rarity"] == rarity]
        w = []
        for r in cands:
            c = self.cards[r]
            m = minted.get(r, 0) if minted is not None else (c["minted"] or 0)
            pr = c["print_run"]
            if not _finite(pr) or not _finite(m):
                raise UnknownPack(f"no print run for {r}")
            w.append(max(pr - m, 0))
        s = sum(w)
        if s <= 0:
            raise UnknownPack(f"no candidates for rarity {rarity!r}")
        return [(r, wi / s) for r, wi in zip(cands, w) if wi > 0]

    def _pack_ev(self, pack_type: str, counts: Mapping, minted: Optional[Mapping], side: str) -> float:
        p = self.packs.get(pack_type)
        if p is None:
            raise UnknownPack(pack_type)
        t0 = self._cards_total(counts, side)
        ev = 0.0
        for slot in p["slots"]:
            if not isinstance(slot, Mapping):
                raise UnknownPack(f"{pack_type}: bad slot")
            for rar, pr in slot.items():
                if not _finite(pr):
                    raise UnknownPack(f"{pack_type}: bad probability")
                for r, q in self._slot_dist(rar, minted):
                    c2 = Counter(counts)
                    c2[r] += 1
                    ev += pr * q * (self._cards_total(c2, side) - t0)
        return ev

    def _total(self, counts: Mapping, packs: Iterable[str], minted: Optional[Mapping], side: str) -> float:
        v = self._cards_total(counts, side)
        for p in packs:
            v += self._pack_ev(p, counts, minted, side)
        return v

    # --- public API ----------------------------------------------------------------------------------
    def collection_value(self, counts: Mapping, packs: Iterable[str] = (), minted: Optional[Mapping] = None) -> float:
        """V-01 + V-02: cards with copy marginals, page bonus, unopened packs at their stock-weighted EV."""
        return self._total(counts, tuple(packs), minted, "model")

    def delta_add(self, counts: Mapping, ref: str, packs: Iterable[str] = (), minted: Optional[Mapping] = None) -> float:
        """Value gained by receiving one copy of ref (4th+ copy counts 0)."""
        packs = tuple(packs)
        self.base(ref)
        c2 = Counter(counts)
        c2[ref] += 1
        return self._total(c2, packs, minted, "buy") - self._total(counts, packs, minted, "buy")

    def delta_remove(self, counts: Mapping, ref: str, packs: Iterable[str] = (), minted: Optional[Mapping] = None) -> float:
        """Value lost by handing over one copy of ref (4th+ copy counts MARG[-1]). ValueError if not held."""
        packs = tuple(packs)
        self.base(ref)
        if counts.get(ref, 0) < 1:
            raise ValueError(f"{ref} not held")
        c2 = Counter(counts)
        c2[ref] -= 1
        return self._total(counts, packs, minted, "sell") - self._total(c2, packs, minted, "sell")

    def delta_swap(self, counts: Mapping, give_ref: str, want_ref: str, packs: Iterable[str] = (),
                   minted: Optional[Mapping] = None) -> float:
        """D1: V(received) - V(given) for handing one give_ref and receiving one want_ref (no fee)."""
        packs = tuple(packs)
        lost = self.delta_remove(counts, give_ref, packs, minted)
        c2 = Counter(counts)
        c2[give_ref] -= 1
        gained = self.delta_add(c2, want_ref, packs, minted)
        return gained - lost

    def pack_ev(self, pack_type: str, counts: Mapping, minted: Optional[Mapping] = None) -> float:
        return self._pack_ev(pack_type, counts, minted, "model")

    def closes_page(self, counts: Mapping, ref: str) -> bool:
        """True if receiving ref completes its page (call with Book.projected)."""
        c = self.cards.get(ref)
        if not c or not c["page"] or counts.get(ref, 0) > 0:
            return False
        return all(counts.get(r, 0) > 0 for r in self.pages.get(c["set"], ()) if r != ref)

    def self_check(self, me: Mapping, server_values: Optional[Mapping] = None, tol: float = 0.11) -> tuple:
        """(ok, max_abs_error, mismatches) against collection_value, your_value and value?card.

        Never raises: an unknown pack / card or a malformed body is a mismatch (ok = False).
        """
        mism: list = []
        err = 0.0
        try:
            counts, packs = self.holdings(me)
            meas = me.get("collection_value")
            model = self.collection_value(counts, packs)
            # 4th+ copies (V-10, never measured): anywhere between 0 (buy view) and MARG[-1] (model) is accepted,
            # so an unmeasured copy marginal cannot fail the check and block every write; equal bounds otherwise
            low = self._total(counts, packs, None, "buy")
            if not _finite(meas):
                mism.append(("collection_value", None, model, meas))
            else:
                e = max(0.0, low - meas, meas - model) if low <= model else abs(model - meas)
                err = max(err, e)
                if e > tol:
                    mism.append(("collection_value", None, model, meas))
            for a in me.get("assets") or ():
                if a.get("kind") != "card":
                    continue
                yv = a.get("your_value")
                if not _finite(yv):
                    continue
                if counts.get(a["ref"], 0) > len(self.marg):    # handing over a 4th+ copy: unmeasured, not compared
                    continue
                m = self.delta_remove(counts, a["ref"], packs)
                err = max(err, abs(m - yv))
                if abs(m - yv) > tol:
                    mism.append(("your_value", a["ref"], m, yv))
            for ref, sv in (server_values or {}).items():
                if not _finite(sv):
                    mism.append(("value?card", ref, None, sv))
                    continue
                if counts.get(ref, 0) >= len(self.marg):      # 4th copy: unmeasured regime, not compared
                    continue
                m = self.delta_add(counts, ref, packs)
                err = max(err, abs(m - sv))
                if abs(m - sv) > tol:
                    mism.append(("value?card", ref, m, sv))
        except (UnknownPack, UnknownCard, ValueError, TypeError, AttributeError, KeyError) as e:
            mism.append(("error", type(e).__name__, None, str(e)))
        return (not mism, err, mism)


# ------------------------------------------------------------------------------------------------ fees

def fee(price: int, cards: int = 1, fee_bps: int = 500, per_card: int = 1) -> int:
    """R-01: ceil(fee_bps/10000 * price + per_card * cards), paid by the accepter. Exact integer arithmetic."""
    for name, x in (("price", price), ("cards", cards), ("fee_bps", fee_bps), ("per_card", per_card)):
        if not _finite(x) or type(x) is bool or x < 0:
            raise ValueError(f"fee: bad {name}")
    if all(type(x) is int for x in (price, cards, fee_bps, per_card)):
        num = fee_bps * price + 10000 * per_card * cards
        return -(-num // 10000)
    return int(math.ceil(fee_bps / 10000 * price + per_card * cards - 1e-9))


def venue_fee(venue: Mapping, price: int, cards: int = 1) -> int:
    """Fee on a venue row of World.venues ({fee_bps, fee_per_card}). ValueError on a malformed row (fail closed)."""
    if not isinstance(venue, Mapping):
        raise ValueError("venue row not a mapping")
    bps, pc = venue.get("fee_bps"), venue.get("fee_per_card")
    if type(bps) is not int or type(pc) is not int:
        raise ValueError("venue fee fields missing or not int")
    return fee(price, cards, bps, pc)


# ----------------------------------------------------------------------------------------- predictions

def _num(name: str, x: Any) -> float:
    if not _finite(x) or type(x) is bool:
        raise ValueError(f"{name} must be a finite number")
    return float(x)


def predict_team(dv: float, price: int, side: str, we_accept: bool, cap: float = 50.0, *,
                 cards: int = 1, fee_bps: int = 500, per_card: int = 1) -> Prediction:
    """P-03. buy: g = dv - price - fee; sell: g = price - fee - dv (dv = value lost, >= 0). Fee only if we accept."""
    dv = _num("dv", dv)
    if type(price) is not int or price < 0:
        raise ValueError("price must be an int >= 0")
    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'")
    f = fee(price, cards, fee_bps, per_card) if we_accept else 0
    if side == "buy":
        g = dv - price - f
        cash = -price - f
    else:
        g = price - f - dv
        cash = price - f
    return Prediction(neg_lo=min(g, float(cap)), neg_hi=g, ladder="0", cash=cash, model="P-03")


def predict_swap(dv_in: float, dv_out: float, we_accept: bool, cap: float = 50.0, *,
                 cards: int = 2, fee_bps: int = 500, per_card: int = 1) -> Prediction:
    """D1: g = V(received) - V(given) - fee (fee only if we accept; price 0, cards=2 assumed)."""
    dv_in, dv_out = _num("dv_in", dv_in), _num("dv_out", dv_out)
    f = fee(0, cards, fee_bps, per_card) if we_accept else 0
    g = dv_in - dv_out - f
    return Prediction(neg_lo=min(g, float(cap)), neg_hi=g, ladder="0", cash=-f, model="D1")


def predict_dealer(dv: float, price: int, side: str) -> Prediction:
    """P-04 / P-08: only losses count, min(0, gain); a gain may raise the ladder."""
    dv = _num("dv", dv)
    if type(price) is not int or price < 0:
        raise ValueError("price must be an int >= 0")
    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'")
    g = dv - price if side == "buy" else price - dv
    n = min(0.0, g)
    return Prediction(neg_lo=n, neg_hi=n, ladder=">=0" if g > 0 else "0",
                      cash=-price if side == "buy" else price, model="P-04")


def predict_duel(limit: int, price: int, decay: float, rounds: int, side: str) -> Prediction:
    """U-01: surplus * (1 - decay)^rounds; buy surplus = limit - price, sell = price - limit (signed)."""
    limit, price, decay = _num("limit", limit), _num("price", price), _num("decay", decay)
    if type(rounds) is not int or rounds < 0:
        raise ValueError("rounds must be an int >= 0")
    if not 0.0 <= decay < 1.0:
        raise ValueError("decay must be in [0, 1)")
    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'")
    surplus = (limit - price) if side == "buy" else (price - limit)
    return Prediction(neg_lo=0.0, neg_hi=0.0, ladder="0", cash=0, duel=surplus * (1.0 - decay) ** rounds,
                      model="U-01")


def predict_none(model: str = "none") -> Prediction:
    return Prediction(neg_lo=0.0, neg_hi=0.0, ladder="0", cash=0, model=model)


# ---------------------------------------------------------------------------------------------- verdict

VERDICT_TOL = 0.1
SOFT_SHORTFALL = 1.0
LADDER_EPS = 1e-6


def verdict(pred: Prediction, measured_neg: float, ladder_delta: float) -> str:
    """pass | soft_fail | hard_fail | surprise_up for a settled prediction."""
    vals = (pred.neg_lo, pred.neg_hi, measured_neg, ladder_delta)
    if not all(_finite(x) for x in vals):
        return "hard_fail"
    if ladder_delta < -LADDER_EPS:
        return "hard_fail"
    lo, hi = min(pred.neg_lo, pred.neg_hi), max(pred.neg_lo, pred.neg_hi)
    if measured_neg < lo - VERDICT_TOL:
        if lo >= 0 and measured_neg < -VERDICT_TOL:      # predicted no loss, measured a loss
            return "hard_fail"
        return "soft_fail" if lo - measured_neg <= SOFT_SHORTFALL else "hard_fail"
    if measured_neg > hi + VERDICT_TOL:
        return "surprise_up"
    if pred.ladder == "0" and ladder_delta > LADDER_EPS:
        return "surprise_up"
    return "pass"
