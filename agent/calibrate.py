"""M13 calibrate: prediction vs measurement loop (docs/harness-spec.md §7, INV-17).

Calibrator(journal, paths).on_tick(prev, world) pairs settlements with their intents, measures the *_points
(never `score`, P-14), excludes round changes, writes `measure` / `round_reset` / `pause` / `alarm` rows,
keeps persistent pauses in state/pauses.json and collects STOP reasons for the runner.

Design notes
- verdict() comes from agent.valuation (M3). If M3 cannot be imported, a local conservative fallback with the
  same signature is used (pass | soft_fail | hard_fail | surprise_up); a `verdict_fn=` kwarg lets tests and the
  runner inject one. Swaps (D1) need nothing special here: their prediction is a Prediction like any other.
- "A harness offer that would fail G12/G20/G21/G32 today" cannot re-run the guards (M4a) from here. Without an
  injected `recheck(intent_row, world) -> bool`, the proxy is: a window made only of harness settlements whose
  measured Δneg <= -1 (every guard demands >= +1) -> STOP. With `recheck`, a False also gives STOP.
- Ambiguous windows (several settlements) give a verdict on the sum; they never count for soft pauses, but a
  hard_fail pauses every tactic involved (§7.4). Settlements never overlap two windows: a new one joins the
  open window (ambiguous).
- Settlement sources: own offer open/queued -> accepted/settled/filled/done (or vanished before expiry with a
  cash/asset change); our dealer thread -> "deal"; live duel -> deal/done/no_deal (duels: info only, U-13);
  our ok `accept` intents pending <= 3 ticks + a cash/asset change.
- The "all *_points drop at once" round rule needs >= 2 positive components dropping (a lone neg drop with
  everything else at 0 is treated as a real loss, fail closed). A window that crosses a round change -> no
  verdict, no pause (measure row with verdict "excluded").
- D1 swaps / D2 rival venues: a swap offer settles as an asset-only change (`moved` covers assets); an
  `accept` on another venue is measured like any accept (its prediction already nets that venue's fee).
- Known limitations: E4 ladder table is only reported (by dealer) from measure rows; learning rows other than
  NEG_CAP_CONFIRMED (E5); journal is re-scanned from the start every tick (fine for one event, O(rows)).
- Contract note: §6 says the `intent` row carries {id, tactic, kind, ...} but the journal
  envelope already uses `kind` = "intent". intent_kind() reads intent_kind / ikind / it_kind, else infers the
  kind from the args key set (distinct per ARGS schema). list_offer -> offer id is read from the `result`
  response (offer_id | id | offer.id) or `reconciled.evidence`; else matched by shape (ref, price, created_tick).
- pauses.json format: {tactic: {"why": str, "tick": int|None}}. Broken pauses.json at start -> buy tactics and
  duels paused + alarm (fail closed); broken later -> keep the in-memory value.
"""
from __future__ import annotations

import json
import math
import os
from collections import Counter, defaultdict, deque
from typing import Any, Callable, Iterable, Mapping, Optional

from agent.contracts import ARGS, BUY_TACTICS, TACTICS, TEAM, Paths, Prediction, World

POINT_KEYS = ("neg_points", "ladder_points", "duel_points", "mm_points", "bench_points")
OPEN_STATUSES = frozenset({"open", "queued"})
SETTLED_STATUSES = frozenset({"accepted", "settled", "filled", "done", "deal"})
DUEL_END = frozenset({"deal", "done", "no_deal", "closed", "expired"})
WINDOW_TICKS = 3
TOL = 0.11
LOSS_STOP = -1.0                 # harness settlement with measured Δneg <= this -> STOP (proxy for G12/20/21/32)
UNATTRIBUTED_LOSS = -1.0         # Δneg <= this with no settlement -> pause buys
DAILY_SURPRISE_STOP = -500.0     # Sun 09:32: a closer fill that GAINED +23 (predicted +50) hit -5 and stopped the bot; 13:12: a cancel + Taller read as a -28.7 fill;
                                 # real losses are LOSS_STOP's job, this only catches a badly wrong model
SOFT_WINDOW, SOFT_MAX = 5, 2
NEG_CAP_MIN_HI, NEG_CAP_VALUE = 55.0, 50.0


# ---------------------------------------------------------------------------------------- helpers

def _num(x: Any) -> Optional[float]:
    if type(x) in (int, float) and math.isfinite(x):
        return float(x)
    return None


def points_of(me: Any) -> Optional[dict]:
    """*_points from world.me (me["score"][k] or me[k]). None if neg_points is unreadable."""
    if not isinstance(me, Mapping):
        return None
    score = me.get("score")
    out = {}
    for k in POINT_KEYS:
        v = _num(score.get(k)) if isinstance(score, Mapping) else None
        if v is None:
            v = _num(me.get(k))
        if v is not None:
            out[k] = v
    return out if "neg_points" in out else None


def _holdings(me: Any) -> tuple:
    if not isinstance(me, Mapping):
        return (None, frozenset())
    ids = set()
    for a in me.get("assets") or ():
        if isinstance(a, Mapping) and a.get("id") is not None:
            ids.add(a.get("id"))
    return (me.get("cash"), frozenset(ids))


def _pred_dict(p: Any) -> dict:
    if isinstance(p, Prediction):
        return {"neg_lo": p.neg_lo, "neg_hi": p.neg_hi, "ladder": p.ladder, "cash": p.cash, "duel": p.duel,
                "model": p.model}
    if isinstance(p, Mapping):
        return {"neg_lo": _num(p.get("neg_lo")) or 0.0, "neg_hi": _num(p.get("neg_hi")) or 0.0,
                "ladder": p.get("ladder") if p.get("ladder") in ("0", ">=0") else ">=0",
                "cash": p.get("cash") if type(p.get("cash")) is int else 0, "duel": _num(p.get("duel")),
                "model": str(p.get("model") or "")}
    return {"neg_lo": 0.0, "neg_hi": 0.0, "ladder": ">=0", "cash": 0, "duel": None, "model": "missing"}


def fallback_verdict(pred: Prediction, measured_neg: float, ladder_delta: float) -> str:
    """Same contract as valuation.verdict (M3): pass | soft_fail | hard_fail | surprise_up. Conservative."""
    if ladder_delta < -1e-6:
        return "hard_fail"
    if measured_neg < pred.neg_lo - TOL:
        if measured_neg <= min(0.0, pred.neg_lo) - 1.0 or pred.neg_lo - measured_neg > 10.0:
            return "hard_fail"
        return "soft_fail"
    if measured_neg > pred.neg_hi + TOL:
        return "surprise_up"
    return "pass"


def _load_verdict() -> Callable:
    try:
        from agent.valuation import verdict  # M3
        return verdict
    except Exception:            # M3 not built yet: conservative local twin
        return fallback_verdict


def _offer_ref_price(o: Mapping) -> tuple:
    """(ref, price) as the list_offer intent states them: sell/swap -> given card; bid -> wanted card.
    A swap (D1) gives an asset and wants a card with no cash: price None/0 (callers compare `or 0`)."""
    give, want = o.get("give") or {}, o.get("want") or {}
    assets = [a for a in (give.get("assets") or []) if isinstance(a, Mapping) and a.get("ref")]
    if assets:
        return assets[0].get("ref"), want.get("cash")
    for t in (want.get("types") or []):
        if isinstance(t, str) and t.startswith("card:"):
            return t[5:], give.get("cash")
    return None, give.get("cash")


def intent_kind(row: Mapping) -> Optional[str]:
    """The intent's kind in a journal `intent` row. The row's own `kind` is "intent" (journal envelope), so
    M5 must store it elsewhere: intent_kind / ikind / it_kind; else it is inferred from the args keys
    (every ARGS schema has a distinct key set)."""
    for k in ("intent_kind", "ikind", "it_kind"):
        if row.get(k) in ARGS:
            return row[k]
    if row.get("kind") in ARGS:
        return row["kind"]
    keys = set((row.get("args") or {}).keys())
    for k, schema in ARGS.items():
        if keys == set(schema):
            return k
    return None


def _offer_id_from(resp: Any) -> Optional[int]:
    if not isinstance(resp, Mapping):
        return None
    for cand in (resp.get("offer_id"), resp.get("id"),
                 (resp.get("offer") or {}).get("id") if isinstance(resp.get("offer"), Mapping) else None):
        if type(cand) is int:
            return cand
    return None


# ------------------------------------------------------------------------------------- calibrator

class Calibrator:
    def __init__(self, journal, paths: Paths, *, verdict_fn: Optional[Callable] = None,
                 recheck: Optional[Callable] = None, baseline: Optional[Mapping] = None,
                 bands: Optional[Mapping] = None):
        self.journal = journal
        self.paths = paths
        self.verdict_fn = verdict_fn or _load_verdict()
        self.recheck = recheck
        self._stops: list = []
        self._base: Optional[dict] = None          # *_points at the last good reading
        self._round: Optional[int] = None
        self._window: Optional[dict] = None
        self._soft = defaultdict(lambda: deque(maxlen=SOFT_WINDOW))   # tactic -> recent verdicts
        self._daily_surprise = defaultdict(float)
        self._pauses: dict = {}
        self._measured_ids: set = set()
        self._vanished: dict = {}                  # M17: own offers gone from me/offers whose card is still ours
        self._load_pauses(initial=True)
        self._inherited = self._load_baseline(baseline, bands)
        self._baseline_given = baseline is not None
        self._rebuild_history()

    # ------------------------------------------------------------------ pauses (persistent)
    def _load_pauses(self, initial: bool = False) -> None:
        p = self.paths.pauses
        if not p.exists():
            return
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                raw = {str(t): {"why": "loaded", "tick": None} for t in raw}
            if not isinstance(raw, dict):
                raise ValueError("pauses.json is not an object")
            self._pauses = {str(t): (v if isinstance(v, dict) else {"why": str(v), "tick": None})
                            for t, v in raw.items()}
        except Exception as e:
            if initial:     # fail closed: nothing that buys or talks runs until a person resumes it
                for t in sorted(BUY_TACTICS | {"duels"}):
                    self._pauses[t] = {"why": "pauses.json unreadable", "tick": None}
                self._write("alarm", what="pauses_unreadable", detail=str(e)[:200])

    def _save_pauses(self) -> None:
        p = self.paths.pauses
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._pauses, f, sort_keys=True, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)

    def paused(self, tactic: str) -> bool:
        return tactic in self._pauses

    def pause(self, tactic: str, why: str, tick: Optional[int] = None) -> None:
        if tactic in self._pauses:
            return
        self._pauses[tactic] = {"why": why, "tick": tick}
        self._write("pause", tactic=tactic, why=why, tick=tick)
        self._save_pauses()

    def resume(self, tactic: str, why: str) -> None:
        if tactic not in self._pauses:
            return
        self._pauses.pop(tactic, None)
        self._write("resume", tactic=tactic, why=why)
        self._save_pauses()
        self._soft.pop(tactic, None)

    def stop_reasons(self) -> list:
        return list(self._stops)

    # ------------------------------------------------------------------ journal access
    def _write(self, kind: str, **fields) -> None:
        self.journal.write(kind, **fields)

    def _rows(self, kinds: Optional[set] = None) -> Iterable[dict]:
        try:
            return list(self.journal.rows(kinds))
        except Exception:
            return []

    def _load_baseline(self, baseline: Optional[Mapping], bands: Optional[Mapping]) -> dict:
        """offer_id -> band for inherited offers (state/baseline.json; 2503/2504 -> 0.0)."""
        data = baseline
        if data is None:
            try:
                data = json.loads(self.paths.baseline.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        out: dict = {}
        offers = data.get("offers") if isinstance(data, Mapping) else None
        if isinstance(offers, Mapping):
            for k, v in offers.items():
                b = _num(v.get("band") if isinstance(v, Mapping) else v)
                out[int(k)] = 0.0 if b is None else b
        elif isinstance(offers, (list, tuple)):
            for o in offers:
                if isinstance(o, Mapping) and o.get("id") is not None:
                    out[int(o["id"])] = _num(o.get("band")) or 0.0
                elif type(o) is int:
                    out[o] = 0.0
        src_bands = bands if bands is not None else (data.get("bands") if isinstance(data, Mapping) else None)
        for k, v in (src_bands or {}).items():
            b = _num(v)
            if b is not None:
                out[int(k)] = b
        return out

    def _rebuild_history(self) -> None:
        for r in self._rows({"measure"}):
            for i in r.get("ids") or ():
                self._measured_ids.add(i)
            if r.get("ambiguous") or r.get("verdict") in ("excluded", "info"):
                continue
            for t in r.get("tactics") or ():
                self._soft[t].append(r.get("verdict"))
            s = _num(r.get("surprise"))
            if s is not None and r.get("day"):
                self._daily_surprise[r["day"]] += s

    def _index(self) -> dict:
        """Intents, results and pairings from the journal (re-read every tick)."""
        intents, ok, landed = {}, set(), set()
        offer_iid, thread_iids, duel_iids, accepts = {}, defaultdict(list), defaultdict(list), {}
        for r in self._rows({"intent", "result", "reconciled", "accepted_unsettled"}):
            k, iid = r.get("kind"), r.get("id")
            if k == "intent":
                intents[iid] = dict(r, ikind=intent_kind(r))
            elif k == "result" and r.get("status") in ("ok", "sent"):
                ok.add(iid)
                oid = _offer_id_from(r.get("response"))
                it = intents.get(iid)
                if oid is not None and it and it.get("ikind") == "list_offer":
                    offer_iid[oid] = iid
            elif k == "reconciled" and r.get("landed"):
                landed.add(iid)
                oid = _offer_id_from(r.get("evidence"))
                it = intents.get(iid)
                if oid is not None and it and it.get("ikind") == "list_offer":
                    offer_iid[oid] = iid
            elif k == "accepted_unsettled":
                accepts[iid] = r.get("until_tick")
        done = ok | landed
        for iid, it in intents.items():
            if iid not in done:
                continue
            a = it.get("args") or {}
            if a.get("thread_id") is not None:
                thread_iids[a["thread_id"]].append(iid)
            if it.get("ikind") in ("duel_say", "duel_accept") and a.get("duel_id") is not None:
                duel_iids[a["duel_id"]].append(iid)
            if it.get("ikind") == "accept" and a.get("thread_id") is None:
                accepts.setdefault(iid, (it.get("tick") or 0) + WINDOW_TICKS)
        return {"intents": intents, "done": done, "offer_iid": offer_iid, "thread_iids": thread_iids,
                "duel_iids": duel_iids, "accepts": accepts}

    # ------------------------------------------------------------------ settlement detection
    def _settlements(self, prev: World, world: World, idx: dict) -> list:
        out = []
        cash0, assets0 = _holdings(prev.me)
        cash1, assets1 = _holdings(world.me)
        moved = (cash0 != cash1) or (assets0 != assets1)
        me1 = world.me if isinstance(world.me, Mapping) else {}
        assets_ids1 = {a.get("id") for a in (me1.get("assets") or ()) if isinstance(a, Mapping)}
        now = {o.get("id"): o for o in world.my_offers if isinstance(o, Mapping)}
        for o in prev.my_offers:
            if not isinstance(o, Mapping) or o.get("maker") != TEAM or o.get("status") not in OPEN_STATUSES:
                continue
            if o.get("thread") is not None:
                continue        # M17: our offer inside a dealer thread is measured as the thread's "deal"
            oid = o.get("id")
            n = now.get(oid)
            if n is not None:
                hit = n.get("status") in SETTLED_STATUSES
            else:
                exp = o.get("expires_tick")
                hit = moved and not (type(exp) is int and world.tick > exp)
                gave = [a.get("id") for a in ((o.get("give") or {}).get("assets") or ()) if isinstance(a, Mapping)]
                if gave and any(aid in assets_ids1 for aid in gave) and not (type(exp) is int and world.tick > exp):
                    hit = False          # M17: the card it gave is still ours: not settled (yet). Watch it.
                    self._vanished[oid] = (o, world.tick + WINDOW_TICKS)
            if hit:
                out.append(self._attribute_offer(o, idx))
        for oid, (o, until) in list(self._vanished.items()):
            gave = [a.get("id") for a in ((o.get("give") or {}).get("assets") or ()) if isinstance(a, Mapping)]
            if oid in now and now[oid].get("status") in OPEN_STATUSES:
                self._vanished.pop(oid, None)
            elif gave and not any(aid in assets_ids1 for aid in gave) and moved:
                self._vanished.pop(oid, None)
                if not any(oid == s.get("offer_id") for s in out):
                    out.append(self._attribute_offer(o, idx))
            elif world.tick > until:
                self._vanished.pop(oid, None)
        for tid, t in (prev.threads or {}).items():
            if not isinstance(t, Mapping) or t.get("status") == "deal":
                continue
            n = (world.threads or {}).get(tid)
            if (n is not None and n.get("status") == "deal") or (n is None and moved):
                iids = idx["thread_iids"].get(tid) or []
                out.append({"source": "harness" if iids else "unknown", "ids": iids[-1:] or [f"thread:{tid}"],
                            "kind": "dealer", "dealer": t.get("with") or t.get("dealer")})
        live1 = {d.get("duel"): d for d in world.duels if isinstance(d, Mapping)}
        for d in prev.duels:
            if not isinstance(d, Mapping) or d.get("status") in DUEL_END:
                continue
            n = live1.get(d.get("duel"))
            if n is None or n.get("status") in DUEL_END:
                iids = idx["duel_iids"].get(d.get("duel")) or []
                out.append({"source": "duel", "ids": iids[-1:] or [f"duel:{d.get('duel')}"], "kind": "duel"})
        if moved:
            taken = {i for s in out for i in s["ids"]}
            for iid, until in idx["accepts"].items():
                if iid in taken or iid in self._measured_ids or iid not in idx["intents"]:
                    continue
                if type(until) is int and world.tick > until:
                    continue
                if not self._accept_evidence(idx["intents"][iid].get("args") or {}, prev.me, world.me,
                                             cash_alone=not out):
                    continue        # M17: no card moved the way this accept would move it (failed / not yet)
                out.append({"source": "harness", "ids": [iid], "kind": "accept"})
        return out

    @staticmethod
    def _accept_evidence(a: Mapping, me0: Any, me1: Any, cash_alone: bool = True) -> bool:
        """An accept settled only if its card moved: buy -> one more `ref` held; sell -> the asset (or one copy
        of `ref`) left; swap -> both. Without this, any cash/asset change in the window (an inherited sale, a
        grant) was measured as the accept's, and a phantom offer that never settles produced a false hard_fail."""
        def refs(me):
            c: Counter = Counter()
            ids = set()
            for x in (me.get("assets") or ()) if isinstance(me, Mapping) else ():
                if isinstance(x, Mapping):
                    ids.add(x.get("id"))
                    if x.get("kind", "card") == "card" and x.get("ref"):
                        c[x["ref"]] += 1
            return c, ids
        c0, ids0 = refs(me0)
        c1, ids1 = refs(me1)
        ref, side, give = a.get("ref"), a.get("side"), a.get("give_asset")
        if side == "buy":       # the card arrived, or we paid at least the price (paid without the card: measure it)
            cash0 = me0.get("cash") if isinstance(me0, Mapping) else None
            cash1 = me1.get("cash") if isinstance(me1, Mapping) else None
            price = a.get("price")
            paid = (type(cash0) in (int, float) and type(cash1) in (int, float) and type(price) is int
                    and cash0 - cash1 >= price)
            # cash alone is evidence only when nothing else of ours settled in this window (a dealer deal or
            # another accept paying at the same time would otherwise be measured as this accept)
            return (bool(ref) and c1[ref] > c0[ref]) or (paid and cash_alone)
        if side == "sell":
            if give is not None:
                return give in ids0 and give not in ids1
            return bool(ref) and c1[ref] < c0[ref]
        if give is not None:                          # swap: our asset left and something arrived
            return give in ids0 and give not in ids1 and len(ids1 - ids0) > 0
        return False

    def _attribute_offer(self, o: Mapping, idx: dict) -> dict:
        oid = o.get("id")
        iid = idx["offer_iid"].get(oid)
        if iid is None and oid not in self._inherited:      # fallback: same shape, created after the intent
            ref, price = _offer_ref_price(o)
            for cand, it in idx["intents"].items():
                a = it.get("args") or {}
                if (it.get("ikind") == "list_offer" and cand in idx["done"] and a.get("ref") == ref
                        and (a.get("price") or 0) == (price or 0)
                        and (o.get("created_tick") or 0) >= (it.get("tick") or 0)
                        and cand not in self._measured_ids):
                    iid = cand
        if iid is not None:
            return {"source": "harness", "ids": [iid], "kind": "offer", "offer_id": oid}
        if oid in self._inherited:
            return {"source": "inherited", "ids": [f"baseline:{oid}"], "kind": "offer", "offer_id": oid,
                    "band": self._inherited[oid]}
        return {"source": "unknown", "ids": [f"offer:{oid}"], "kind": "offer", "offer_id": oid}

    # ------------------------------------------------------------------ main loop
    def on_tick(self, prev: Optional[World], world: World) -> list:
        ev: list = []
        pts = points_of(world.me) if "me" not in (world.down or ()) else None
        if pts is None:                      # unreadable: no verdict, no base change, windows wait
            return ev
        if prev is None or self._base is None:
            self._base, self._round = pts, world.round
            return ev
        if not self._inherited and not self._baseline_given:
            # M17: the Gate writes state/baseline.json on its first begin_tick, after this Calibrator was built;
            # without this reload every inherited offer was "unknown" and could be shape-matched to an intent.
            self._inherited = self._load_baseline(None, None)
        idx = self._index()
        setts = self._settlements(prev, world, idx) if "me/offers" not in (world.down or ()) else []
        before = self._base

        # §7.3 round change (explicit, or every positive component drops with no settlement of ours)
        round_changed = self._round is not None and world.round is not None and world.round != self._round
        positives = [k for k, v in before.items() if v > 1e-9]
        dropped = [k for k in positives if pts.get(k, before[k]) < before[k] - 1e-9]
        all_drop = (not setts and self._window is None and len(positives) >= 2
                    and set(dropped) == set(positives))
        if round_changed or all_drop:
            row = {"from_round": self._round, "to_round": world.round, "before": before, "after": pts,
                   "tick": world.tick, "cause": "round" if round_changed else "all_points_drop"}
            self._write("round_reset", **row)
            ev.append({"kind": "round_reset", **row})
            excluded = list(self._window["setts"]) if self._window else []
            excluded += setts
            if excluded:
                m = {"ids": [i for s in excluded for i in s["ids"]], "pred": None, "meas": None,
                     "verdict": "excluded", "tick": world.tick}
                self._measured_ids.update(m["ids"])
                self._write("measure", **m)
                ev.append({"kind": "measure", **m})
            self._window, self._base, self._round = None, pts, world.round
            return ev
        self._round = world.round if world.round is not None else self._round

        if setts:
            if self._window is None:
                self._window = {"opened": world.tick, "before": before, "setts": list(setts)}
            else:
                self._window["setts"].extend(setts)

        dneg = pts["neg_points"] - before["neg_points"]
        dlad = pts.get("ladder_points", 0.0) - before.get("ladder_points", 0.0)
        changed = any(abs(pts.get(k, 0.0) - before.get(k, 0.0)) > 1e-9 for k in set(pts) | set(before))

        if self._window is not None:
            w = self._window
            dneg = pts["neg_points"] - w["before"]["neg_points"]
            dlad = pts.get("ladder_points", 0.0) - w["before"].get("ladder_points", 0.0)
            if changed or world.tick - w["opened"] >= WINDOW_TICKS:
                ev += self._close_window(w, pts, dneg, dlad, world)
                self._window = None
                self._base = pts
        else:
            if dlad < -1e-6:
                ev += self._pause_many(["dealers"], f"ladder_down:{dlad:.3f}", world.tick)
            if dneg <= UNATTRIBUTED_LOSS:
                ev += self._alarm("unattributed_neg_drop", f"dneg={dneg:.2f}", world.tick)
                ev += self._pause_many(sorted(BUY_TACTICS), f"unattributed_neg:{dneg:.2f}", world.tick)
            self._base = pts
        return ev

    # ------------------------------------------------------------------ verdicts and actions
    def _close_window(self, w: dict, pts: dict, dneg: float, dlad: float, world: World) -> list:
        ev: list = []
        setts = w["setts"]
        idx_intents = {r.get("id"): r for r in self._rows({"intent"})}
        ids = [i for s in setts for i in s["ids"]]
        self._measured_ids.update(ids)
        tactics, kinds, dealers = set(), set(), set()
        lo = hi = inh_lo = 0.0
        cash, ladder_any = 0, False
        sources = Counter(s["source"] for s in setts)
        for s in setts:
            kinds.add(s["kind"])
            if s.get("dealer"):
                dealers.add(s["dealer"])
            if s["source"] == "harness":
                for iid in s["ids"]:
                    it = idx_intents.get(iid) or {}
                    if it.get("tactic") in TACTICS:
                        tactics.add(it["tactic"])
                    p = _pred_dict(it.get("prediction"))
                    lo, hi, cash = lo + p["neg_lo"], hi + p["neg_hi"], cash + p["cash"]
                    ladder_any = ladder_any or p["ladder"] == ">=0"
            elif s["source"] == "inherited":
                # M17: the baseline band is a cancel threshold set before the harness existed, not a prediction
                # of ours: in a window mixed with harness trades it claims nothing (min(band, 0)), so an
                # inherited sale below its band cannot hard_fail (and pause/STOP) the harness tactic beside it.
                inh_lo += s["band"]
                lo, hi = lo + min(s["band"], 0.0), hi + s["band"] + 200.0
                ladder_any = True
            elif s["source"] == "duel":
                ladder_any = True
            else:                                   # unknown origin: no prediction, cannot be judged
                ladder_any = True
        ambiguous = len(setts) > 1
        only_duels = all(s["source"] == "duel" for s in setts)
        pred = Prediction(lo, hi, ">=0" if ladder_any else "0", int(cash), None,
                          "sum" if ambiguous else "single")
        meas = {"neg": round(dneg, 4), "ladder": round(dlad, 4),
                "duel": round(pts.get("duel_points", 0.0) - w["before"].get("duel_points", 0.0), 4)}
        if only_duels:
            verdict = "info"
        elif sources.get("unknown") and not sources.get("harness") and not sources.get("inherited"):
            verdict = "unattributed"
        elif sources.get("inherited") and not sources.get("harness"):
            verdict = "pass" if dneg >= inh_lo - TOL else "out_of_band"
            lo = inh_lo
        else:
            try:
                verdict = str(self.verdict_fn(pred, dneg, dlad))
            except Exception as e:                  # cannot judge -> treat as hard (fail closed)
                verdict = "hard_fail"
                ev += self._alarm("verdict_error", str(e)[:200], world.tick)
        day = str((world.clock or {}).get("today") or int(world.t_hours // 24))
        surprise = min(0.0, dneg - lo) if sources.get("harness") and verdict not in ("info",) else 0.0
        row = {"ids": ids, "pred": _pred_dict(pred), "meas": meas, "verdict": verdict, "tick": world.tick,
               "opened": w["opened"], "tactics": sorted(tactics), "kinds": sorted(kinds),
               "sources": dict(sources), "ambiguous": ambiguous, "dealers": sorted(dealers),
               "day": day, "surprise": round(surprise, 4)}
        self._write("measure", **row)
        ev.append({"kind": "measure", **row})

        # §7.5 automatic actions
        if verdict == "hard_fail":
            ev += self._pause_many(sorted(tactics) or sorted(BUY_TACTICS), f"hard_fail:{','.join(ids)}",
                                   world.tick)
        elif not ambiguous:
            for t in tactics:
                self._soft[t].append(verdict)
                if sum(1 for v in self._soft[t] if v == "soft_fail") >= SOFT_MAX:
                    ev += self._pause_many([t], "soft_fail x2 in last 5", world.tick)
        if dlad < -1e-6 and not only_duels:
            ev += self._pause_many(["dealers"], f"ladder_down:{dlad:.3f}", world.tick)
        if verdict == "out_of_band":
            ev += self._alarm("inherited_out_of_band", f"{ids} dneg={dneg:.2f} band={lo:.2f}", world.tick)
        if verdict == "unattributed" and dneg <= UNATTRIBUTED_LOSS:
            ev += self._alarm("unattributed_neg_drop", f"{ids} dneg={dneg:.2f}", world.tick)
            ev += self._pause_many(sorted(BUY_TACTICS), f"unattributed_neg:{dneg:.2f}", world.tick)
        harness_only = sources.get("harness", 0) and set(sources) <= {"harness", "duel"}
        if harness_only and not only_duels:
            bad = dneg <= LOSS_STOP
            if self.recheck is not None:
                for s in setts:
                    for iid in s["ids"] if s["source"] == "harness" else ():
                        try:
                            if self.recheck(idx_intents.get(iid) or {}, world) is False:
                                bad = True
                        except Exception:
                            bad = True
            if bad:
                ev += self._stop(f"calib:harness_settlement_out_of_band:{','.join(ids)}:dneg={dneg:.2f}")
        if surprise < 0:
            self._daily_surprise[day] += surprise
            if self._daily_surprise[day] < DAILY_SURPRISE_STOP:
                ev += self._stop(f"calib:daily_negative_surprise:{day}:{self._daily_surprise[day]:.2f}")
        # §7.6 learning (E5): only an unambiguous trade with uncapped gain >= 55 that measures 50.0 +- 0.1
        if not ambiguous and sources.get("harness") and hi >= NEG_CAP_MIN_HI and abs(dneg - NEG_CAP_VALUE) <= 0.1:
            self._write("param", name="NEG_CAP_CONFIRMED", value=True, evidence=ids, tick=world.tick)
            ev.append({"kind": "param", "name": "NEG_CAP_CONFIRMED", "value": True})
        return ev

    def _pause_many(self, tactics: Iterable[str], why: str, tick: int) -> list:
        ev = []
        for t in tactics:
            if not self.paused(t):
                self.pause(t, why, tick)
                ev.append({"kind": "pause", "tactic": t, "why": why})
        return ev

    def _alarm(self, what: str, detail: str, tick: int) -> list:
        self._write("alarm", what=what, detail=detail, tick=tick)
        return [{"kind": "alarm", "what": what, "detail": detail}]

    def _stop(self, reason: str) -> list:
        if reason in self._stops:
            return []
        self._stops.append(reason)
        return [{"kind": "stop", "reason": reason}]

    # ------------------------------------------------------------------ report (L3)
    def report(self) -> str:
        measures = self._rows({"measure"})
        resets = self._rows({"round_reset"})
        by_t: dict = defaultdict(Counter)
        ladder_by_dealer: dict = defaultdict(list)
        surprise_day: dict = defaultdict(float)
        cap = any(r.get("name") == "NEG_CAP_CONFIRMED" for r in self._rows({"param"}))
        for r in measures:
            for t in (r.get("tactics") or ["-"]):
                by_t[t][r.get("verdict")] += 1
            meas = r.get("meas") or {}
            for d in r.get("dealers") or ():
                ladder_by_dealer[d].append(meas.get("ladder"))
            if r.get("day") and _num(r.get("surprise")):
                surprise_day[r["day"]] += r["surprise"]
        lines = ["# Calibration report", f"measures: {len(measures)}  round_resets: {len(resets)}  "
                 f"NEG_CAP_CONFIRMED: {cap}"]
        for t in sorted(by_t):
            lines.append(f"  {t}: " + ", ".join(f"{k}={v}" for k, v in sorted(by_t[t].items(), key=str)))
        for r in resets:
            lines.append(f"  round_reset t{r.get('tick')}: {r.get('from_round')}->{r.get('to_round')} "
                         f"neg {(r.get('before') or {}).get('neg_points')}->{(r.get('after') or {}).get('neg_points')}")
        for d, xs in sorted(ladder_by_dealer.items()):
            lines.append(f"  ladder Δ by dealer {d}: {xs}")
        for d, s in sorted(surprise_day.items()):
            lines.append(f"  negative surprise {d}: {s:.2f}")
        lines.append("pauses: " + (", ".join(f"{t} ({v.get('why')})" for t, v in sorted(self._pauses.items()))
                                   or "none"))
        lines.append("stop reasons: " + ("; ".join(self._stops) or "none"))
        return "\n".join(lines)
