"""Mini campo de batalla: reproducible OFFLINE practice, never a live-game executor.

Price-only scoring uses the measured decay rule and signed surplus. Rival behaviour,
timing and delivery-day utility are hypothetical stress models, not server replicas.
Selection uses training episodes only; validation shares fresh scenarios across policies.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import math
import random
from statistics import mean

from agent.tactics.duels import DEFAULTS, decide, view
from harness.battle_reference import training_cases, training_results, robustness

PROFILES = ("reactive", "time", "firm", "accept_only", "silent", "worsening")
DAY_CASES = ("price_only", "same", "opposite", "unknown")


def signed_score(role, limit, price, decay, our_messages, rival_messages, days_loss=0.0):
    """Zero without a deal; losses remain negative, acceptance adds no message."""
    if role not in ("buyer", "seller"):
        raise ValueError("role must be buyer or seller")
    if not 0 <= decay < 1 or min(our_messages, rival_messages) < 0:
        raise ValueError("invalid decay or message count")
    if price is None:
        return 0.0
    surplus = (limit - price) if role == "buyer" else (price - limit)
    return (surplus - days_loss) * (1 - decay) ** min(our_messages, rival_messages)


def make_scenarios(count, seed, profiles=None):
    """Deterministic paired worlds; opponent limit is hidden from the real tactic."""
    profiles = tuple(PROFILES if profiles is None else profiles)
    if count < 1 or not profiles or any(p not in PROFILES for p in profiles):
        raise ValueError("positive count and supported opponent profiles required")
    rng = random.Random(seed)
    rows = []
    for i in range(count):
        limit = rng.randint(50, 200)
        rows.append({"id": i, "profile": profiles[i % len(profiles)], "limit": limit,
                     "gap": rng.choice((-30, -15, -5, 5, 15, 30, 50)),
                     "day_case": DAY_CASES[(i // len(profiles)) % len(DAY_CASES)],
                     "days_weight": rng.choice((1, 2, 3)),
                     "days_sign": rng.choice((-1, 1)),
                     "rival_first": bool(rng.getrandbits(1)),
                     "patience": rng.randint(1, 4), "demand": rng.randint(1, 15)})
    return rows


def simulate_episode(role, scenario, params=None, ticks=12, decay=.10, trace=False):
    """Feed authentic view/decide with a synthetic rival; no I/O or credentials.

    Day utility is W(d)-max W, a conservative linear regret model. Unknown sign
    is hidden from the tactic but available to the offline evaluator. The opponent
    may accept our offer without sending a message (zero decay rounds).
    """
    if role not in ("buyer", "seller") or ticks < 3 or not 0 <= decay < 1:
        raise ValueError("invalid role, ticks or decay")
    profile = scenario["profile"]
    if profile not in PROFILES:
        raise ValueError("unsupported opponent profile")
    limit = scenario["limit"]
    sign = 1 if role == "seller" else -1
    # A positive gap is a price agreement zone, negative gap no price agreement.
    rival_limit = max(1, limit + sign * scenario["gap"])
    two = scenario["day_case"] != "price_only"
    weight = scenario["days_weight"] if two else 0
    own_sign = scenario["days_sign"]
    rival_sign = own_sign if scenario["day_case"] == "same" else -own_sign
    own_best = 10 if own_sign > 0 else 0
    rival_best = 10 if rival_sign > 0 else 0
    p = dict(DEFAULTS, **(params or {}))
    p["T"] = ticks
    p["days_sign"] = None if scenario["day_case"] == "unknown" else own_sign
    d = {"duel": scenario["id"], "role": role, "status": "live", "your_limit": limit,
         "deadline_tick": ticks, "decay_per_round": decay,
         "issues": ["price", "days"] if two else ["price"], "messages": [],
         "your_days_weight": weight if two else None,
         "days_meaning": "offline linear regret hypothesis" if two else None}
    logs, failures = [], []
    accepted_price, accepted_days, accepted_by = None, None, None
    e8_until = None
    last_own_index_replied = None

    def day_loss(days, desired):
        return weight * abs(days - desired) if two and days is not None else 0.0

    def our_surplus(price, days):
        return sign * (price - limit) - day_loss(days, own_best)

    def rival_surplus(price, days):
        return -sign * (price - rival_limit) - day_loss(days, rival_best)

    def append(sender, tick, price, days):
        msg = {"from": sender, "tick": tick, "price": price, "days": days}
        d["messages"].append(msg)
        d["your_offer" if sender == "you" else "rival_offer"] = {
            "id": len(d["messages"]), "tick": tick, "price": price, "days": days}
        if trace:
            logs.append(dict(msg, action="say"))

    def rival_step(tick):
        nonlocal accepted_price, accepted_days, accepted_by, last_own_index_replied
        ours = d.get("your_offer")
        target = scenario["demand"] * (1 - tick / max(1, ticks - 1))
        if profile == "firm":
            target = scenario["demand"]
        if profile == "silent":
            return
        if ours is not None and rival_surplus(ours["price"], ours["days"]) >= max(1, target):
            accepted_price, accepted_days, accepted_by = ours["price"], ours["days"], "rival"
            if trace:
                logs.append({"tick": tick, "action": "accept", "from": "rival",
                             "price": accepted_price, "days": accepted_days})
            return
        if profile == "accept_only":
            return
        if profile == "reactive" and ours is None:
            return
        if profile == "reactive" and ours["id"] == last_own_index_replied:
            return
        if profile == "reactive" and (tick % scenario["patience"]):
            return
        if profile == "worsening" and tick == 0:
            return
        fraction = tick / max(1, ticks - 1)
        if profile == "reactive":
            fraction = min(1.0, sum(m["from"] == "you" for m in d["messages"]) / 6)
        if profile == "firm":
            fraction = .65
        if profile == "worsening":
            fraction = max(0, 1 - fraction)
        requested = max(1, math.ceil(scenario["demand"] + .6 * limit * (1 - fraction)))
        # Rival quotes its best days; concessions are prices, not free day utility.
        days = rival_best if two else None
        price = max(1, rival_limit - sign * requested)
        if rival_surplus(price, days) < 1:
            return
        append("rival", tick, price, days)
        if profile == "reactive":
            last_own_index_replied = ours["id"]

    def own_step(tick):
        nonlocal accepted_price, accepted_days, accepted_by, e8_until
        v = view(d, tick)
        if not v.ok:
            failures.append("invalid_view:" + v.why)
            return
        if e8_until is None and v.rivals:
            e8_until = v.rivals[0][0] + p["e8_ticks"]
        cfg = dict(p, e8_hold_until=e8_until)
        action, price, days = decide(v, cfg)
        if action == "wait":
            return
        if price is None or (two and (type(days) is not int or not 0 <= days <= 10)):
            failures.append("malformed_action")
            return
        if our_surplus(price, days) < 1 - 1e-9:
            failures.append("unsafe_action")
            return
        if action == "say":
            append("you", tick, price, days)
        elif action == "accept":
            offered = d.get("rival_offer")
            if not offered or offered["tick"] != tick or offered["price"] != price:
                failures.append("stale_accept")
                return
            accepted_price, accepted_days, accepted_by = price, days, "you"
            if trace:
                logs.append({"tick": tick, "action": "accept", "from": "you",
                             "price": price, "days": days})

    for tick in range(ticks):
        if scenario["rival_first"]:
            rival_step(tick)
            if accepted_price is None:
                own_step(tick)
        else:
            own_step(tick)
            if accepted_price is None:
                rival_step(tick)
            # Model the runner's same-tick second read, acceptance without a message.
            if accepted_price is None:
                own_step(tick)
        if accepted_price is not None:
            break
    ours = sum(m["from"] == "you" for m in d["messages"])
    rivals = len(d["messages"]) - ours
    price_score = signed_score(role, limit, accepted_price, decay, ours, rivals)
    days_regret = day_loss(accepted_days, own_best) if accepted_price is not None else 0
    result = {"scenario": scenario["id"], "role": role, "profile": profile,
              "day_case": scenario["day_case"], "price_agreement_zone": scenario["gap"] > 0,
              "deal": accepted_price is not None, "price": accepted_price, "days": accepted_days,
              "accepted_by": accepted_by, "our_messages": ours, "rival_messages": rivals,
              "rounds": min(ours, rivals), "price_score": price_score,
              "score": signed_score(role, limit, accepted_price, decay, ours, rivals, days_regret),
              "days_regret_hypothetical": days_regret, "failures": failures}
    if trace:
        result["trace"] = logs
        result["hidden_world_for_audit"] = dict(scenario, rival_limit=rival_limit)
    return result


def _summary(rows):
    return {"episodes": len(rows), "mean_score": round(mean(r["score"] for r in rows), 6),
            "mean_price_score": round(mean(r["price_score"] for r in rows), 6),
            "deals": sum(r["deal"] for r in rows),
            "deal_rate": round(mean(r["deal"] for r in rows), 6),
            "negative_scores": sum(r["score"] < 0 for r in rows),
            "failures": sum(len(r["failures"]) for r in rows),
            "safety_violations": sum(f == "unsafe_action" for r in rows for f in r["failures"])}


def _groups(rows, field):
    return {key: _summary([r for r in rows if r[field] == key])
            for key in sorted({r[field] for r in rows}, key=str)}


def _role_experiment(role, count, train_seed, test_seed, profiles, ticks, decay, base_params=None):
    train = make_scenarios(count, train_seed, profiles)
    test = make_scenarios(count, test_seed, profiles)
    common = dict(base_params or {})
    candidates = [dict(common, anchor=anchor, acc_late=late)
                  for anchor in (.55, .60, .65, .70, .75) for late in (1, 3, 5)]
    baseline = dict(common, anchor=common.get("anchor", DEFAULTS["anchor"]),
                    acc_late=common.get("acc_late", DEFAULTS["acc_late"]))
    if baseline not in candidates:
        candidates.append(baseline)
    base_train = [simulate_episode(role, s, baseline, ticks, decay) for s in train]
    extra_cases = training_cases(role, train_seed, ticks, decay, max(1, min(100, math.ceil(count/6))))
    base_extra = training_results(extra_cases, ticks, decay, baseline)
    ranking = []
    for cfg in candidates:
        rows = base_train if cfg == baseline else [simulate_episode(role, s, cfg, ticks, decay) for s in train]
        extra = base_extra if cfg == baseline else training_results(extra_cases, ticks, decay, cfg)
        gains = {profile: mean((r["score"]-b["score"])/s["limit"]
                              for s,r,b in zip(train, rows, base_train) if s["profile"] == profile)
                 for profile in {s["profile"] for s in train}}
        day_gains = {day: mean((r["score"]-b["score"])/s["limit"]
                              for s,r,b in zip(train, rows, base_train) if s["day_case"] == day)
                     for day in {s["day_case"] for s in train}}
        for kind, episodes in extra_cases.items():
            gains[kind] = mean((r["points"]-b["points"])/e["L"]
                               for e,r,b in zip(episodes, extra[kind], base_extra[kind]))
        stats = _summary(rows)
        extra_failures = sum(r["bug"]+r["say_bug"] for rr in extra.values() for r in rr)
        stats["failures"] += extra_failures
        metrics = robustness(dict(gains, **{f"days:{k}":v for k,v in day_gains.items()}))
        metrics["selection_score"] = mean(gains.values())
        ranking.append({"params": cfg, **stats, **metrics,
                        "training_group_gains": dict(gains, **{f"days:{k}":v for k,v in day_gains.items()}),
                        "additional_training_failures": extra_failures})
    # Stable ties favor baseline, then smaller parameter change; never inspect test.
    ranking.sort(key=lambda r: (r["safety_violations"], r["failures"], r["robust_rejections"], -r["selection_score"],
                               r["params"] != baseline,
                               abs(r["params"]["anchor"] - baseline["anchor"]),
                               abs(r["params"]["acc_late"] - baseline["acc_late"])))
    chosen = ranking[0]["params"]
    base_rows = [simulate_episode(role, s, baseline, ticks, decay) for s in test]
    chosen_rows = [simulate_episode(role, s, chosen, ticks, decay) for s in test]
    deltas = [b["score"] - a["score"] for a, b in zip(base_rows, chosen_rows)]
    delta = mean(deltas)
    se = math.sqrt(sum((d - delta) ** 2 for d in deltas) / (len(deltas) - 1) / len(deltas)) if len(deltas) > 1 else 0
    baseline_stats, chosen_stats = _summary(base_rows), _summary(chosen_rows)
    trace_indexes = sorted(set(range(min(6, len(test)))) | set(range(6, min(24, len(test)), 6)))
    return {"train_seed": train_seed, "test_seed": test_seed,
            "distinct_scenarios": count * 2 + sum(map(len, extra_cases.values())),
            "executed_episodes": count * (len(candidates) + 2) + len(candidates)*sum(map(len, extra_cases.values())),
            "audit_trace_replays": len(trace_indexes),
            "selection_rule": "training safety first, then fewest losing opponent/day groups, then equal-model mean normalized paired gain; validation cannot select",
            "additional_training_profiles": list(extra_cases),
            "train_ranking": ranking, "baseline_params": baseline, "chosen_params": chosen,
            "baseline": baseline, "selected_params": chosen,
            "common_settings": {key: value for key, value in common.items()
                                if key not in ("anchor", "acc_late")},
            "validation_baseline": baseline_stats, "validation_selected": chosen_stats,
            "validation": {"baseline": _summary(base_rows), "chosen": _summary(chosen_rows),
                           "paired_mean_gain": round(delta, 6),
                           "paired_gain_standard_error": round(se, 6),
                           "chosen_improved": delta > 0},
            "per_opponent": {"baseline": _groups(base_rows, "profile"), "chosen": _groups(chosen_rows, "profile")},
            "per_days": {"baseline": _groups(base_rows, "day_case"), "chosen": _groups(chosen_rows, "day_case")},
            "per_agreement_zone": {"baseline": _groups(base_rows, "price_agreement_zone"),
                                   "chosen": _groups(chosen_rows, "price_agreement_zone")},
            "failures": baseline_stats["failures"] + chosen_stats["failures"] + sum(r["failures"] for r in ranking),
            "recommendation": "review_only" if delta > 0 else "retain_baseline",
            "traces": [simulate_episode(role, test[i], chosen, ticks, decay, True)
                       for i in trace_indexes]}


def run_experiment(practices_per_role=200, seed=18, profiles=None, ticks=12, decay=.10, base_params=None):
    """Run buyer/seller workers in parallel; return JSON-serializable evidence."""
    if type(practices_per_role) is not int or not 1 <= practices_per_role <= 20000:
        raise ValueError("practices_per_role must be 1..20000")
    if type(seed) is not int or ticks < 3 or not 0 <= decay < 1:
        raise ValueError("invalid seed, ticks or decay")
    if base_params is not None and not isinstance(base_params, dict):
        raise ValueError("base_params must be a parameter dictionary")
    base_params = dict(base_params or {})
    profiles = tuple(PROFILES if profiles is None else profiles)
    if not profiles or any(p not in PROFILES for p in profiles):
        raise ValueError("unsupported or empty profiles")
    if "silent" not in profiles:
        caution = "No silent opponent coverage: incomplete stress test."
    else:
        caution = "Silent rivals intentionally produce no deal; do not count that as a software failure."
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs = {role: pool.submit(_role_experiment, role, practices_per_role,
                                 seed + i * 100000, seed + i * 100000 + 50000,
                                 profiles, ticks, decay, base_params) for i, role in enumerate(("buyer", "seller"))}
        roles = {role: job.result(timeout=120) for role, job in jobs.items()}
    return {"name": "mini campo de batalla", "version": 1, "offline": True,
            "ticks": ticks, "decay": decay, "practices_per_role_per_split": practices_per_role,
            "profiles": list(profiles), "day_cases": list(DAY_CASES), "roles": roles,
            "policy_parameters": dict(DEFAULTS, **base_params),
            "common_settings": {key: value for key, value in base_params.items()
                                if key not in ("anchor", "acc_late")},
            "scenario_overrides": {"T": ticks, "days_sign": "scenario preference, hidden if unknown"},
            "distinct_scenarios": sum(r["distinct_scenarios"] for r in roles.values()),
            "executed_episodes": sum(r["executed_episodes"] for r in roles.values()),
            "audit_trace_replays": sum(r["audit_trace_replays"] for r in roles.values()),
            "counting": "executed_episodes counts benchmark runs; audit_trace_replays repeat validation cases and add no training evidence",
            "failures": sum(r["failures"] for r in roles.values()),
            "model": {"price": "measured signed surplus * (1-decay)^min(messages)",
                      "days": "hypothetical linear regret W(d)-max(W), not official server scoring",
                      "rivals": "synthetic behavioural profiles, not learned opponent replicas",
                      "training": "offline parameter selection, no LLM fine-tuning",
                      "runner": "same-tick re-read and isolated E8 per episode, not full Gate/runner replay"},
            "recommendation_caution": [caution, "Validation never changes the selected parameters.",
                                       "No live configuration is changed. Operator review is required.",
                                       "Simulation improvements do not establish gains against real opponents.",
                                       "Delivery preferences must be confirmed from the real duel before action."]}
