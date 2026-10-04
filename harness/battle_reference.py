"""Held-out cross-check using main's additional rival models; never selects parameters."""
from __future__ import annotations

import math
from statistics import mean


def training_cases(role, seed, ticks, decay, per_kind):
    from run_duel_eval import NEW_RIVALS, draw
    parity = 0 if role == "buyer" else 1
    return {kind: [draw(f"mini-train-plus:{seed}", ticks, decay, kind, 2*i+parity)
                   for i in range(per_kind)] for kind in NEW_RIVALS}


def training_results(cases, ticks, decay, params):
    from run_duel_eval import run_episode
    return {kind: [run_episode(e, kind, ticks, decay, params) for e in episodes]
            for kind, episodes in cases.items()}


def robustness(group_gains):
    """Training-only constraint: reject observed average losses in any covered group."""
    return {"robust_rejections": sum(gain < -1e-12 for gain in group_gains.values()),
            "selection_score": mean(group_gains.values()) if group_gains else 0.0}


def crosscheck(simulation, seed, per_kind_role=80):
    if type(per_kind_role) is not int or not 1 <= per_kind_role <= 500:
        raise ValueError("per_kind_role must be 1..500")
    # The upstream module's import explicitly isolates test mode from keys/.env.
    from run_duel_eval import NEW_RIVALS, draw, run_episode
    ticks, decay = simulation["ticks"], simulation["decay"]
    roles = {}
    for role, parity in (("buyer", 0), ("seller", 1)):
        policy = simulation["roles"][role]
        groups = {}
        all_deltas = []
        failures = 0
        for kind in NEW_RIVALS:
            episodes = [draw(f"mini-reference:{seed}", ticks, decay, kind, 2*i+parity)
                        for i in range(per_kind_role)]
            assert all(e["role"] == role for e in episodes)
            baseline = [run_episode(e, kind, ticks, decay, policy["baseline_params"]) for e in episodes]
            selected = [run_episode(e, kind, ticks, decay, policy["selected_params"]) for e in episodes]
            deltas = [b["points"] - a["points"] for a,b in zip(baseline, selected)]
            bugs = sum(r["bug"] + r["say_bug"] for r in baseline+selected)
            failures += bugs
            all_deltas.extend(deltas)
            groups[kind] = {"scenarios": per_kind_role, "baseline_mean": mean(r["points"] for r in baseline),
                            "selected_mean": mean(r["points"] for r in selected),
                            "baseline_deals": sum(r["deal"] for r in baseline),
                            "selected_deals": sum(r["deal"] for r in selected),
                            "paired_gain": mean(deltas), "failures": bugs}
        gain = mean(all_deltas)
        n = len(all_deltas)
        se = math.sqrt(sum((d-gain)**2 for d in all_deltas)/(n-1)/n) if n>1 else 0
        conflict = (gain > 0) != (policy["validation"]["paired_mean_gain"] > 0)
        roles[role] = {"per_opponent": groups, "paired_gain": gain,
                       "paired_standard_error": se, "failures": failures,
                       "conflicts_with_main_validation": conflict,
                       "recommendation": "review_only" if gain > 1.96*se and not conflict and not failures
                                         else "retain_baseline"}
    count = per_kind_role * len(NEW_RIVALS) * len(roles)
    return {"source": "run_duel_eval.py from main", "seed": seed, "roles": roles,
            "distinct_scenarios": count, "evaluations": count*2,
            "failures": sum(r["failures"] for r in roles.values()),
            "selection_changed": False,
            "cautions": ["Additional validation only; cannot select or tune parameters.",
                         "Synthetic opponents; none calibrated to real teams.",
                         "Price-only episodes; upstream score rounded to 0.1, no Gate or memory replay.",
                         "Reference counts are separate from training counts."]}
