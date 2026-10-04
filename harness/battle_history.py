"""Read-only historical checks. Recorded outcomes never become counterfactual wins."""
from __future__ import annotations

from collections import Counter, defaultdict
import math
import re
from statistics import median


DEALERS = {"abuela", "chato", "pilar", "picaros", "banco"}


def number(v):
    return isinstance(v, (int,float)) and not isinstance(v,bool) and math.isfinite(v)


def historical_states(rows, params=None):
    from agent.tactics.duels import view, decide
    from agent.world import parse_duel, SchemaError
    actions, patterns = Counter(), Counter()
    tested = failures = skipped = 0
    for row in rows:
        if row.get("role") not in ("buyer","seller") or row.get("issues",["price"]) != ["price"]:
            skipped += 1
            continue
        messages = [m for m in row.get("messages",[]) if isinstance(m,dict)]
        rivals = [m for m in messages if m.get("from") not in (None,"you") and number(m.get("price"))]
        direction = -1 if row["role"] == "buyer" else 1
        changes = [direction*(b["price"]-a["price"]) for a,b in zip(rivals,rivals[1:])]
        pattern = ("no_observed_message" if not rivals else "one_observed_message" if len(rivals)==1 else
                   "fixed_quotes" if all(d==0 for d in changes) else
                   "concessions_only" if all(d>=0 for d in changes) else
                   "worsening_only" if all(d<=0 for d in changes) else "mixed")
        patterns[pattern] += 1
        if not number(row.get("your_limit")) or type(row.get("deadline_tick")) is not int:
            skipped += 1
            continue
        # Evaluate recorded prefixes, not an invented conversation responding to our new policy.
        for index,m in enumerate(messages):
            if type(m.get("tick")) is not int or not number(m.get("price")):
                continue
            prefix = messages[:index+1] if m.get("from") != "you" else messages[:index]
            d = {k:row[k] for k in ("duel","session","role","your_limit","deadline_tick","decay_per_round","issues") if k in row}
            d.update(status="live", rounds=0, messages=prefix, your_offer=None, rival_offer=None)
            for msg in prefix:
                if number(msg.get("price")):
                    key = "your_offer" if msg.get("from")=="you" else "rival_offer"
                    d[key] = {"id":1,"price":msg["price"],"tick":msg.get("tick"),"days":msg.get("days")}
            d["rounds"] = min(sum(x.get("from")=="you" for x in prefix),
                              sum(x.get("from") not in (None,"you") for x in prefix))
            try:
                v = view(parse_duel(d),m["tick"])
                if not v.ok:
                    failures += 1
                    continue
                kind,price,days = decide(v,params)
                actions[kind] += 1
                tested += 1
                if kind in ("say","accept"):
                    surplus = row["your_limit"]-price if row["role"]=="buyer" else price-row["your_limit"]
                    failures += surplus < 1-1e-9
                if kind=="accept":
                    offer = d.get("rival_offer")
                    failures += not offer or offer["tick"]!=m["tick"] or offer["price"]!=price
            except (ValueError,TypeError,KeyError,SchemaError):
                failures += 1
    return {"source_kind":"historical_fixture_or_supplied_local_file", "states_tested":tested,
            "failures":failures,"skipped_duels":skipped,"actions":dict(actions),
            "observed_quote_patterns":dict(patterns),"counterfactual_wins_computed":False,
            "scope":"Recorded prefixes through World and policy; no rival limits, Gate, or response to changed actions."}


def market_history(events, own_team="t18", min_references=5, window_ticks=240):
    rows, excluded, seen = [], Counter(), set()
    for e in events:
        if e.get("type")!="settlement":continue
        p=e.get("payload",{})
        if not isinstance(p,dict) or p.get("persona") not in DEALERS:
            excluded["not_dealer"]+=1;continue
        settlement=p.get("settlement")
        identity=("settlement",settlement) if type(settlement) is int else ("event",e.get("id"))
        if type(identity[1]) is not int:
            excluded["missing_identity"]+=1;continue
        if identity in seen:
            excluded["duplicate_settlement"]+=1;continue
        seen.add(identity)
        items=p.get("items",[])
        # Never allocate one lot's price to individual cards or include mixed asset trades.
        if not isinstance(items,list) or len(items)!=1 or not isinstance(items[0],dict) or items[0].get("kind")!="card":
            excluded["not_single_card"]+=1;continue
        item=items[0];dealer=p["persona"];frm,to=item.get("frm"),item.get("to")
        side,team=("buy",to) if frm==dealer else ("sell",frm) if to==dealer else (None,None)
        ref=item.get("ref");price=p.get("price");tick=e.get("tick")
        parties=p.get("parties",[])
        if (side is None or not isinstance(team,str) or re.fullmatch(r"t\d+",team) is None or
                not isinstance(ref,str) or re.fullmatch(r"[A-Z]{3}-\d{2}",ref) is None or
                not number(price) or price<0 or type(tick) is not int or
                not isinstance(parties,list) or len(parties)!=2 or not all(isinstance(x,str) for x in parties) or
                set(parties)!={team,dealer} or
                item.get("rarity") not in {"common","uncommon","rare","epic","legendary"}):
            excluded["invalid_or_ambiguous"]+=1;continue
        rows.append({"event":e.get("id"),"tick":tick,"team":team,"dealer":dealer,"side":side,
                     "group":(dealer,side,item["rarity"],ref[:3]),"price":price})
    rows.sort(key=lambda r:(r["tick"],str(r["event"])))
    groups=defaultdict(list);scores=defaultdict(list);comparisons=[];pending=[];current_tick=None
    for row in rows:
        if row["tick"]!=current_tick:
            for prior in pending:groups[prior["group"]].append(prior)
            pending=[];current_tick=row["tick"]
        refs=[r for r in groups[row["group"]] if r["team"]!=row["team"] and r["tick"]>=row["tick"]-window_ticks]
        pending.append(row)
        teams=defaultdict(list)
        for r in refs:teams[r["team"]].append(r["price"])
        if len(refs)<min_references or len(teams)<2:continue
        # Equal weight per other team, so one prolific bot does not dominate the reference.
        base=median(median(prices) for prices in teams.values())
        advantage=base-row["price"] if row["side"]=="buy" else row["price"]-base
        scores[row["team"]].append(advantage)
        if row["team"]==own_team:
            comparisons.append({"event":row["event"],"tick":row["tick"],"dealer":row["dealer"],
                                "side":row["side"],"rarity":row["group"][2],"set":row["group"][3],
                                "advantage_P":advantage,"prior_reference_deals":len(refs),
                                "prior_reference_teams":len(teams)})
    return {"eligible_single_card_settlements":len(rows),"excluded":dict(excluded),
            "reference":"same dealer/side/rarity/set, strictly earlier ticks, median of team medians",
            "window_ticks":window_ticks,"own_team":own_team,"own_comparisons":comparisons,
            "team_observations":{team:{"comparable_deals":len(values),"median_advantage_P":median(values)}
                                 for team,values in sorted(scores.items())},
            "cautions":["Observed prices, not enemy limits or causal strategies.",
                        "Different cards of same rarity/set remain a proxy; no economics or profitability inferred.",
                        "No later or same-tick deals enter any reference; source coverage may be partial."]}
