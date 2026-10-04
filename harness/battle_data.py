"""Read-only, offline evidence for Mini campo de batalla.

Historical team fixtures contain disclosed own limits; the public feed does not.
No API, agent imports, raw conversation text or inferred hidden rival limits.
"""
from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
from statistics import mean, median
from harness.battle_history import market_history


FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/harvest/duels_done.json"


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _summary(values):
    values = [float(v) for v in values if _number(v)]
    if not values:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    return {"n": len(values), "mean": round(mean(values), 6),
            "median": round(median(values), 6), "min": min(values), "max": max(values)}


def _read(path, key):
    """Return rows, malformed-line count; JSONL and JSON envelopes accepted."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".jsonl":
        rows, malformed = [], 0
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except (ValueError, UnicodeError):
                    malformed += 1
                    continue
                if isinstance(row, dict):
                    rows.append(row)
                else:
                    malformed += 1
        return rows, malformed
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get(key, data.get("events", data.get("feed", [])))
    if not isinstance(data, list):
        raise ValueError(f"Expected list or {key!r} envelope")
    return [row for row in data if isinstance(row, dict)], sum(not isinstance(row, dict) for row in data)


def _role_profile(rows):
    own_counts, rival_counts, rounds, spans, lags, steps = [], [], [], [], [], []
    statuses = Counter()
    price_matches = Counter()
    silent = 0
    for row in rows:
        statuses[str(row.get("status", "unknown"))] += 1
        messages = [m for m in row.get("messages", []) if isinstance(m, dict)]
        own = [m for m in messages if m.get("from") == "you"]
        rival = [m for m in messages if m.get("from") not in (None, "you")]
        own_counts.append(len(own))
        rival_counts.append(len(rival))
        rounds.append(row.get("rounds"))
        silent += not rival
        ticks = [m["tick"] for m in messages if _number(m.get("tick"))]
        if ticks:
            spans.append(max(ticks) - min(ticks))
        prior_own_ticks = []
        for message in messages:
            tick = message.get("tick")
            if message.get("from") == "you" and _number(tick):
                prior_own_ticks.append(tick)
            elif message.get("from") not in (None, "you") and _number(tick):
                # A same-tick own message later in the log is not a precursor.
                previous = [t for t in prior_own_ticks if t <= tick]
                if previous:
                    lags.append(tick - max(previous))
        prices = [m["price"] for m in rival if _number(m.get("price"))]
        direction = -1 if row.get("role") == "buyer" else 1
        steps.extend(direction * (b - a) for a, b in zip(prices, prices[1:]))
        if row.get("status") == "deal" and _number(row.get("price")):
            matched = []
            for name in ("your_offer", "rival_offer"):
                offer = row.get(name)
                if isinstance(offer, dict) and offer.get("price") == row["price"]:
                    matched.append(name)
            price_matches["both" if len(matched) == 2 else matched[0] if matched else "neither"] += 1
    closed = statuses["deal"] + statuses["no_deal"]
    return {
        "duels": len(rows), "status_counts": dict(statuses),
        "agreement_rate_closed": round(statuses["deal"] / closed, 6) if closed else None,
        "silent_rival_count": silent,
        "own_messages": _summary(own_counts), "rival_messages": _summary(rival_counts),
        "rounds_recorded": _summary(rounds), "message_span_ticks": _summary(spans),
        "rival_lag_after_prior_own_message_ticks": _summary(lags),
        "rival_price_movement_toward_us": _summary(steps),
        "settled_price_matches_last_offer": dict(price_matches),
        "acceptance_actor": "unknown: a price match does not identify who accepted",
    }


def load_evidence(feed_path=None, duels_path=None):
    """Summarize supplied local data; None uses historical duel fixture only.

    Public statuses support agreement counts but cannot identify team roles,
    hidden limits, message rounds, acceptance actors or rival causal policies.
    Returned data is JSON serializable and omits raw text, prices and limits.
    """
    path = Path(duels_path) if duels_path is not None else FIXTURE
    duels, malformed_duels = _read(path, "duels")
    deduplicated = {}
    for index, duel in enumerate(duels):
        deduplicated[(duel.get("session"), duel.get("duel", f"row-{index}"))] = duel
    duels = list(deduplicated.values())
    feed, malformed_feed = _read(feed_path, "events") if feed_path is not None else ([], 0)
    unique_events, seen = [], set()
    for event in feed:
        identifier = event.get("id")
        if identifier is not None and identifier in seen:
            continue
        if identifier is not None:
            seen.add(identifier)
        unique_events.append(event)
    feed = unique_events
    public_closed = [e for e in feed if e.get("type") == "duel.closed"]
    public_sessions = {}
    for event in public_closed:
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            continue
        session = str(payload.get("session", "unknown"))
        public_sessions.setdefault(session, Counter())[str(payload.get("status", "unknown"))] += 1
    tested, passed, errors, failures, round_tested, round_matches = 0, 0, [], [], 0, 0
    decays = Counter()
    for duel in duels:
        decay = duel.get("decay_per_round")
        if _number(decay):
            decays[str(decay)] += 1
        messages = [m for m in duel.get("messages", []) if isinstance(m, dict)]
        if messages and _number(duel.get("rounds")):
            own = sum(m.get("from") == "you" for m in messages)
            rival = sum(m.get("from") not in (None, "you") for m in messages)
            round_tested += 1
            round_matches += duel["rounds"] == min(own, rival)
        if duel.get("status") != "deal" or duel.get("role") not in ("buyer", "seller"):
            continue
        # Days utility is not calibrated here; never silently score it as zero.
        if any(issue != "price" for issue in duel.get("issues", ["price"])):
            continue
        values = [duel.get(k) for k in ("your_limit", "price", "rounds", "result", "decay_per_round")]
        if not all(_number(v) for v in values):
            continue
        limit, price, rounds, result, decay = values
        if not (0 <= decay < 1 and rounds >= 0):
            continue
        surplus = limit - price if duel["role"] == "buyer" else price - limit
        predicted = surplus * (1 - decay) ** rounds
        error = abs(predicted - result)
        errors.append(error)
        tested += 1
        passed += error <= 0.051
        if error > 0.051:
            failures.append({"duel": duel.get("duel"), "session": duel.get("session"),
                             "absolute_error": round(error, 6)})
    ticks = [e["tick"] for e in feed if _number(e.get("tick"))]
    return {
        "sources": {"duels": str(path), "duels_kind": "historical_fixture" if duels_path is None else "supplied_local_file",
                    "feed": str(feed_path) if feed_path is not None else None,
                    "network_used": False, "malformed_duel_rows": malformed_duels,
                    "malformed_feed_rows": malformed_feed},
        "counts": {"duels": len(duels), "feed_events": len(feed), "public_duel_closed": len(public_closed)},
        "profiles": {role: _role_profile([d for d in duels if d.get("role") == role])
                     for role in ("buyer", "seller")},
        "public_duel_summary": {"by_session": {k: dict(v) for k, v in public_sessions.items()},
                                "tick_range": [min(ticks), max(ticks)] if ticks else None},
        "formula_verified": {"expression": "signed_surplus * (1 - decay) ** rounds",
                             "tested": tested, "passed": passed, "failed": tested - passed,
                             "max_abs_error": round(max(errors), 6) if errors else None,
                             "tolerance": 0.051, "failures": failures,
                             "rounds_min_messages_tested": round_tested,
                             "rounds_min_messages_matches": round_matches,
                             "scope": "price-only historical cases; does not prove days utility or final rival behavior"},
        "observed_facts": {"decay_counts": dict(decays),
                           "status_counts": dict(Counter(str(d.get("status", "unknown")) for d in duels)),
                           "fixture_prices_and_limits_omitted_from_report": True},
        "simulation_profile_weights": None,
        "market_history": market_history(feed),
        "simulation_weights_basis": "No hay datos suficientes para inferir mezcla; simulator usa su mezcla uniforme declarada",
        "uncertainty": ["Fixtures are historical; they do not describe the current live operator or final.",
                        "Public duel.closed events omit role, price, messages and hidden limits.",
                        "No causal inference of whether a rival reacts to a message or time alone.",
                        "Message span is not total duel duration; acceptance actors are unknown.",
                        "No conversion from raw duel surplus to leaderboard points is established.",
                        "Final clock/schedule must be confirmed by the operator's fresh snapshot."],
    }
