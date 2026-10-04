"""Offline duel evaluator: plays agent/tactics/duels.decide against simulated rivals and scores it with U-01/U-02.

Deterministic, stdlib only, no network, no key, never touches the Gate or the game. It only calls the pure
`D.view` / `D.decide` of the duel tactic, one duel at a time (no E8 hold, no accept budget: that is propose()'s job).

Score of one episode (docs/knowledge.md U-01, U-02, U-09):
    points = surplus * (1 - decay) ** rounds   if there is a deal and the price is inside our limit
    rounds = min(our messages, rival messages) at the moment of the deal; accepting adds no round
    no deal -> 0; silence is free. A deal outside our limit scores 0 here and is counted as a BUG.

Episodes
- Our limit L ~ uniform int 60..200. Rival limit RL: gap ~ uniform(-10 %, +45 %) of L, so the zone of agreement
  (ZOPA = gap when positive) exists in ~82 % of the episodes. Buyer: RL = L - gap (rival seller); seller: RL = L + gap.
- Roles alternate buyer/seller by episode index. Settings: primary 12 ticks / decay 0.10 (the Final), secondary
  12 ticks / 0.08 and 16 ticks / 0.06.
- Each tick: a coin decides whether the rival acts before our first pass; we then make two passes (early and
  late window, like the runner) and the rival acts once per tick at most, never at the deadline tick
  (same loop as tests/test_duels.py run_episode).
- Pairing: every config sees the same episodes (L, RL, start, per-tick order coins and the rival's random stream
  are seeded from (seed, setting, kind, index)), so differences between configs are paired.

Rival models (all ASSUMPTIONS, none is fitted to real rivals; U-09: reactivity is not identifiable from practice).
Rivals open at RL * 1.35 (seller) / RL * 0.65 (buyer) unless stated otherwise.
From tests/test_duels.py (DuelRival, reused as is, only RL and the opening are set here):
  mute            never speaks, never accepts (U-07: many teams have no bot). Always 0 for any policy.
  accept_only     never speaks; accepts our standing offer if inside its limit with p = 0.5 per tick.
  one_and_accept  one opening message, then like accept_only.
  reactive        answers only after we spoke: accepts with p = 0.3 if inside its limit, else concedes 1..8.
  time_driven     concedes 0..6 every tick and speaks every tick (never accepts).
  firm            repeats its opening with p = 0.7 per tick (never concedes, never accepts).
  worsening       retracts 5 per tick and speaks with p = 0.6.
  injector        random absurd prices (1, 2, 10**6, ...). A safety model, not a scoring one: it is reported but
                  left out of the overall mean (a 10**6 offer to a seller would dominate it). --include-injector.
Added here (book-inspired / behavioural):
  splitter        "split the difference": silent until we speak; after each of our messages, accepts our offer if
                  it is inside its limit and at least as good as its last offer or within 3 % of it; otherwise
                  proposes the midpoint between its last offer and ours, clamped to its limit.
  ackerman        Voss's Ackerman: target = 0.9 of the way from 0 to its limit (buyer: 0.9 * RL; seller mirror:
                  RL / 0.9). Opens at 65 % of the target (seller: target / 0.65) on its first turn, then after each
                  of our messages steps to 85 / 95 / 100 %, then holds (repeats the target). Accepts when our offer
                  is inside its limit and at least as good for it as its current step.
  patient         silent until deadline-4; from deadline-4 concedes linearly from its opening to its limit (reaching
                  it at deadline-1), one message per tick; from deadline-3 accepts any standing offer of ours that
                  is inside its limit.

Overall = mean over rival kinds of the per-kind mean (equal weight per kind). 95 % CIs by bootstrap over episodes,
stratified by kind; with --compare, CIs of the difference against the FIRST config are paired (same resampled
indices for both configs).

What this cannot measure: the effect of the words we send (talk.py templates, Voss labels, calibrated questions).
Rivals here read prices only; any text effect on real LLM rivals is outside the model.

Usage
  py run_duel_eval.py --params '{"anchor":0.6}' --n 400 --seed 18 [--json out.json]
  py run_duel_eval.py --compare '{"base":{},"a55":{"anchor":0.55}}' --n 400
  py run_duel_eval.py --primary-only --n 1000 --boot 2000
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401  (isolates the environment: BAZAAR_TEST=1, no .env, no key)
from tests.test_duels import RIVALS as TEST_RIVALS, DuelRival, duel, msg  # noqa: E402
from agent.tactics import duels as D  # noqa: E402

PRIMARY = (12, 0.10)
SETTINGS = ((12, 0.10), (12, 0.08), (16, 0.06))
NEW_RIVALS = ("splitter", "ackerman", "patient")
KINDS = tuple(TEST_RIVALS) + NEW_RIVALS
SCORING_EXCLUDED = ("injector",)


def _surplus(role, L, p):
    return (L - p) if role == "buyer" else (p - L)


# ------------------------------------------------------------------------------------------- rivals

class Rival(DuelRival):
    """DuelRival with the limit drawn here and three extra kinds. Speaks at most once per tick."""

    def __init__(self, kind, role, L, RL, T, deadline, rng):
        super().__init__(kind, role, L, T, rng)            # consumes one randint (its own gap): same for all configs
        self.RL = RL
        self.cur = round(RL * 1.35) if self.role == "seller" else max(1, round(RL * 0.65))
        self.open = self.cur
        self.deadline = deadline
        self.last = None                                      # splitter / ackerman: its last offer
        self.step = 0                                         # ackerman step index

    def _better_or_equal(self, a, b):
        """Is price a at least as good as price b for the rival?"""
        return a >= b if self.role == "seller" else a <= b

    def _clamp(self, p):
        return max(self.RL, p) if self.role == "seller" else max(1, min(self.RL, p))

    def act(self, d, t, we_spoke_last):
        k = self.kind
        if k not in NEW_RIVALS:
            return super().act(d, t, we_spoke_last)
        ours = [m for m in d["messages"] if m["from"] == "you"]
        mine = ours[-1]["price"] if ours else None
        if k == "splitter":
            if mine is None or not we_spoke_last:
                return None
            last = self.last if self.last is not None else self.cur
            if self._ok(mine) and (self._better_or_equal(mine, last) or abs(mine - last) <= 0.03 * last):
                return ("accept", None)
            mid = (last + mine) / 2
            mid = math.ceil(mid) if self.role == "seller" else math.floor(mid)
            self.last = self._clamp(mid)
            return ("say", self.last)
        if k == "ackerman":
            if self.role == "buyer":
                target = 0.9 * self.RL
                steps = [max(1, math.floor(target * f)) for f in (0.65, 0.85, 0.95, 1.0)]
            else:
                target = self.RL / 0.9
                steps = [math.ceil(target / f) for f in (0.65, 0.85, 0.95, 1.0)]
            if self.last is None:
                if mine is not None and self._ok(mine) and self._better_or_equal(mine, steps[0]):
                    return ("accept", None)
                self.last = steps[0]
                return ("say", self.last)
            if not we_spoke_last:
                return None
            if mine is not None and self._ok(mine) and self._better_or_equal(mine, steps[self.step]):
                return ("accept", None)
            self.step = min(self.step + 1, len(steps) - 1)
            self.last = steps[self.step]
            return ("say", self.last)
        if k == "patient":
            dl = self.deadline
            if t < dl - 4:
                return None
            if t >= dl - 3 and mine is not None and self._ok(mine):
                return ("accept", None)
            frac = min(1.0, (t - (dl - 4) + 1) / 4)
            p = self.open + (self.RL - self.open) * frac
            p = math.ceil(p) if self.role == "seller" else math.floor(p)
            return ("say", self._clamp(p))
        return None


# ------------------------------------------------------------------------------------------ episode

def draw(seed, T, decay, kind, i):
    """Everything about episode i that must be identical for every config (pairing)."""
    r = random.Random(f"duel-eval:{seed}:{T}:{decay}:{kind}:{i}")
    role = "buyer" if i % 2 == 0 else "seller"
    L = r.randint(60, 200)
    gap = round(r.uniform(-0.10, 0.45) * L)
    RL = max(1, L - gap) if role == "buyer" else L + gap
    zopa = max(0, _surplus(role, L, RL))
    start = r.randint(100, 200)
    return {"role": role, "L": L, "RL": RL, "zopa": zopa, "start": start, "deadline": start + T,
            "order_seed": r.getrandbits(64), "rival_seed": r.getrandbits(64), "did": r.randint(1, 10 ** 5)}


def run_episode(ep, kind, T, decay, params, phases=None):
    """Play one duel. -> dict(points, deal, rounds, price, bug, says_outside). Same loop as tests/test_duels.py."""
    role, L, deadline = ep["role"], ep["L"], ep["deadline"]
    order = random.Random(ep["order_seed"])
    rival = Rival(kind, role, L, ep["RL"], T, deadline, random.Random(ep["rival_seed"]))
    d = duel(did=ep["did"], role=role, L=L, deadline=deadline, decay=decay)
    decide_ex = getattr(D, "decide_ex", None)
    says_outside = 0
    result = None
    for t in range(ep["start"], deadline + 1):
        rival_first = order.random() < 0.5
        rival_done = False

        def rival_turn():
            ours = [i for i, m in enumerate(d["messages"]) if m["from"] == "you"]
            riv = [i for i, m in enumerate(d["messages"]) if m["from"] != "you"]
            we_last = bool(ours) and (not riv or ours[-1] > riv[-1])
            a = rival.act(d, t, we_last)
            if a is None:
                return None
            if a[0] == "accept":
                yo = d["your_offer"]
                return ("rival_accepted", yo["price"]) if yo else None
            d["messages"].append(msg("Rival X", t, a[1]))
            d["rival_offer"] = {"price": a[1], "days": None, "tick": t, "id": len(d["messages"])}
            rival.spoke += 1
            return None

        if rival_first and t < deadline:
            result = rival_turn()
            rival_done = True
            if result:
                break
        for _pass in (0, 1):                                  # early pass, then late-window pass (same tick)
            v = D.view(d, t)
            act = D.decide(v, params)
            if phases is not None and decide_ex is not None:  # logging only, never drives the action
                try:
                    ex = decide_ex(v, params)
                    ph = None                         # current shape: ((kind, price, days), phase)
                    if isinstance(ex, tuple) and len(ex) == 2 and isinstance(ex[0], tuple):
                        ph = ex[1] if ex[1] is not None else "wait"
                    elif isinstance(ex, dict):
                        ph = ex.get("phase")
                    if ph is not None:
                        phases[str(ph)] = phases.get(str(ph), 0) + 1
                except Exception:
                    pass
            if act[0] == "accept":
                if not rival_done or d["rival_offer"] is None or d["rival_offer"]["tick"] != t:
                    says_outside += 1000                       # accepting a stale offer: flag as a bug
                result = ("we_accepted", d["rival_offer"]["price"])
                break
            if act[0] == "say":
                if _surplus(role, L, act[1]) < 1:
                    says_outside += 1
                d["messages"].append(msg("you", t, act[1], act[2]))
                d["your_offer"] = {"price": act[1], "days": act[2], "tick": t, "id": 1}
            if not rival_done and t < deadline:
                result = rival_turn()
                rival_done = True
                if result:
                    break
        if result:
            break
    nY = sum(1 for m in d["messages"] if m["from"] == "you")
    nR = len(d["messages"]) - nY
    rounds = min(nY, nR)
    if not result:
        return {"points": 0.0, "deal": 0, "rounds": rounds, "price": None, "bug": 0, "say_bug": says_outside}
    price = result[1]
    s = _surplus(role, L, price)
    bug = 1 if s < 0 else 0
    pts = 0.0 if bug else round(s * (1 - decay) ** rounds, 1)
    return {"points": pts, "deal": 1, "rounds": rounds, "price": price, "bug": bug, "say_bug": says_outside}


# ------------------------------------------------------------------------------------------- stats

def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return 0.0
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def overall(points_by_kind, kinds):
    return _mean([_mean(points_by_kind[k]) for k in kinds])


def bootstrap(pa, pb, kinds, B, seed):
    """Stratified bootstrap. pb None -> CI of overall(pa); else CI of overall(pb) - overall(pa), paired."""
    rng = random.Random(f"boot:{seed}")
    vals = []
    for _ in range(B):
        means = []
        for k in kinds:
            xa = pa[k]
            n = len(xa)
            idx = [rng.randrange(n) for _ in range(n)]
            ma = sum(xa[j] for j in idx) / n
            if pb is None:
                means.append(ma)
            else:
                xb = pb[k]
                means.append(sum(xb[j] for j in idx) / n - ma)
        vals.append(_mean(means))
    return _pct(vals, 0.025), _pct(vals, 0.975)


def evaluate(configs, n, seed, settings, kinds, log_phases=False):
    """-> {setting_key: {config: {kind: [episode dicts]}}}, plus the drawn episodes."""
    out = {}
    for T, decay in settings:
        key = f"T{T}_d{decay:.2f}"
        eps = {k: [draw(seed, T, decay, k, i) for i in range(n)] for k in kinds}
        res = {}
        for name, params in configs.items():
            phases = {} if log_phases else None
            res[name] = {k: [run_episode(e, k, T, decay, params, phases) for e in eps[k]] for k in kinds}
            if phases:
                res[name]["_phases"] = phases
        out[key] = {"T": T, "decay": decay, "episodes": eps, "results": res}
    return out


def summarize(ev, configs, kinds, scoring, B, seed):
    names = list(configs)
    ref = names[0]
    report = {}
    for key, blob in ev.items():
        eps, res = blob["episodes"], blob["results"]
        rep = {"T": blob["T"], "decay": blob["decay"], "configs": {}}
        pts = {nm: {k: [r["points"] for r in res[nm][k]] for k in kinds} for nm in names}
        for nm in names:
            per = {}
            for k in kinds:
                rs = res[nm][k]
                deals = [r for r in rs if r["deal"]]
                pos = [(e, r) for e, r in zip(eps[k], rs) if e["zopa"] > 0]
                per[k] = {
                    "points": round(_mean([r["points"] for r in rs]), 2),
                    "deal_rate": round(len(deals) / len(rs), 3),
                    "rounds": round(_mean([r["rounds"] for r in deals]), 2),
                    "miss_rate": round(sum(1 for e, r in pos if not r["deal"]) / max(1, len(pos)), 3),
                    "zopa_share": round(_mean([r["points"] / e["zopa"] for e, r in pos]), 3),
                    "bugs": sum(r["bug"] for r in rs),
                    "say_bugs": sum(r["say_bug"] for r in rs),
                }
            ov = overall(pts[nm], scoring)
            entry = {"per_kind": per, "overall": round(ov, 2), "scoring_kinds": list(scoring),
                     "bugs": sum(p["bugs"] for p in per.values()),
                     "say_bugs": sum(p["say_bugs"] for p in per.values())}
            if nm == ref:
                lo, hi = bootstrap(pts[nm], None, scoring, B, f"{seed}:{key}")
                entry["ci95"] = [round(lo, 2), round(hi, 2)]
            else:
                lo, hi = bootstrap(pts[ref], pts[nm], scoring, B, f"{seed}:{key}:{nm}")
                entry["diff_vs_ref"] = round(ov - overall(pts[ref], scoring), 2)
                entry["diff_ci95"] = [round(lo, 2), round(hi, 2)]
            if "_phases" in res[nm]:
                entry["phases"] = res[nm]["_phases"]
            rep["configs"][nm] = entry
        report[key] = rep
    return report


def _share(x):
    return f"{100 * x:.1f}" if abs(x) < 9.995 else ">999"


def _pts(x):
    return f"{x:.2f}" if abs(x) < 99999 else f"{x:.2e}"


def print_report(report, configs, kinds, scoring, n):
    names = list(configs)
    for key, rep in report.items():
        tag = "primary" if (rep["T"], rep["decay"]) == PRIMARY else "secondary"
        print(f"\n=== {rep['T']} ticks, decay {rep['decay']:.2f} ({tag}) - n = {n} episodes per rival kind ===")
        for nm in names:
            e = rep["configs"][nm]
            print(f"\n[{nm}] params = {json.dumps(configs[nm], sort_keys=True)}")
            print(f"  {'rival':<15}{'points':>8}{'deal%':>8}{'rounds':>8}{'miss%':>8}{'zopa%':>8}{'bugs':>6}")
            for k in kinds:
                p = e["per_kind"][k]
                mark = "" if k in scoring else "  (not in overall)"
                print(f"  {k:<15}{_pts(p['points']):>8}{100 * p['deal_rate']:>8.1f}{p['rounds']:>8.2f}"
                      f"{100 * p['miss_rate']:>8.1f}{_share(p['zopa_share']):>8}{p['bugs'] + p['say_bugs']:>6}{mark}")
            line = f"  {'OVERALL':<15}{e['overall']:>8.2f}   ({len(scoring)} kinds, equal weight)"
            if "ci95" in e:
                line += f"  95% CI [{e['ci95'][0]:.2f}, {e['ci95'][1]:.2f}]"
            else:
                line += (f"  diff vs {names[0]}: {e['diff_vs_ref']:+.2f}"
                         f"  paired 95% CI [{e['diff_ci95'][0]:+.2f}, {e['diff_ci95'][1]:+.2f}]")
            print(line)
            if e["bugs"] or e["say_bugs"]:
                print(f"  !! BUG: {e['bugs']} deals outside our limit, say/accept bug score {e['say_bugs']}")
    print("\npoints: mean U-01 score per episode (no deal = 0); deal%: share of episodes with a deal; rounds: mean"
          " rounds of the deals;\nmiss%: no deal although the ZOPA was positive; zopa%: mean points / ZOPA on"
          " positive-ZOPA episodes; bugs: deals outside our limit + says outside / stale accepts.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Offline deterministic evaluator of agent/tactics/duels.py")
    ap.add_argument("--params", default="{}", help="JSON params for D.decide (ignored when --compare is given)")
    ap.add_argument("--compare", default=None, help='JSON {"name": params, ...}; the first one is the reference')
    ap.add_argument("--n", type=int, default=400, help="episodes per rival kind and setting (roles alternate)")
    ap.add_argument("--seed", type=int, default=18)
    ap.add_argument("--boot", type=int, default=1000, help="bootstrap resamples")
    ap.add_argument("--primary-only", action="store_true", help="only 12 ticks / decay 0.10")
    ap.add_argument("--include-injector", action="store_true", help="count the injector in the overall mean")
    ap.add_argument("--phases", action="store_true", help="log D.decide_ex phases if the module has it")
    ap.add_argument("--json", default=None, help="write the full report here")
    a = ap.parse_args(argv)
    if a.compare:
        configs = json.loads(a.compare)
        if not isinstance(configs, dict) or not configs or not all(isinstance(v, dict) for v in configs.values()):
            ap.error("--compare must be a non-empty JSON object of params objects")
    else:
        params = json.loads(a.params)
        if not isinstance(params, dict):
            ap.error("--params must be a JSON object")
        configs = {"params": params}
    settings = (PRIMARY,) if a.primary_only else SETTINGS
    kinds = KINDS
    scoring = tuple(k for k in kinds if a.include_injector or k not in SCORING_EXCLUDED)
    t0 = time.perf_counter()
    ev = evaluate(configs, a.n, a.seed, settings, kinds, log_phases=a.phases)
    report = summarize(ev, configs, kinds, scoring, a.boot, a.seed)
    print_report(report, configs, kinds, scoring, a.n)
    print(f"\n{len(configs)} config(s) x {len(settings)} setting(s) x {len(kinds)} kinds x {a.n} episodes"
          f" in {time.perf_counter() - t0:.1f} s (seed {a.seed}, bootstrap {a.boot})")
    if a.json:
        Path(a.json).write_text(json.dumps({"seed": a.seed, "n": a.n, "configs": configs, "report": report},
                                           indent=1, sort_keys=True), encoding="utf-8")
    bugs = sum(c["bugs"] + c["say_bugs"] for r in report.values() for c in r["configs"].values())
    return 1 if bugs else 0


if __name__ == "__main__":
    sys.exit(main())
