"""Pure, conservative quote radar. Quoted spread is not private surplus."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import re

TEAM = re.compile(r"t(?:0[1-9]|1[0-8])")
REF = re.compile(r"(?:CHA|RET|SAL|LAT|LAV|MAL)-\d{2}")


def integer(x, minimum=0):
    return type(x) is int and x >= minimum


def fee(price, venue, cards=1):
    """Ceiling, paid by the accepting side; never assume it is the ask author."""
    bps, per = venue.get("fee_bps"), venue.get("fee_per_card")
    if not integer(price) or not integer(cards, 1) or not integer(bps) or not integer(per):
        raise ValueError("unknown/invalid fee")
    return (price * bps + 9999) // 10000 + per * cards


def events_at(snapshot, tick):
    """Bounded public feed, deduplicated, with no future/private events."""
    result = {}
    for e in snapshot.get("feed", {}).get("events", []):
        if (isinstance(e, dict) and e.get("scope") == "public"
                and integer(e.get("id")) and integer(e.get("tick")) and e["tick"] <= tick
                and isinstance(e.get("payload"), dict)):
            result[e["id"]] = e
    return sorted(result.values(), key=lambda e: (e["tick"], e["id"]))


@dataclass(frozen=True)
class Quote:
    id: int
    venue: str
    maker: str
    side: str
    ref: str
    price: int
    created: int
    expires: int


def normalize(snapshot):
    tick = snapshot.get("clock", {}).get("tick")
    if not integer(tick):
        raise ValueError("snapshot requires final clock.tick")
    events = events_at(snapshot, tick)
    identities, aliases = {}, {}
    cancelled = set()
    for e in events:
        p = e["payload"]
        if e["type"] == "offer.listed":
            o = p.get("offer", {})
            if isinstance(o, dict) and integer(o.get("id")) and TEAM.fullmatch(str(o.get("maker", ""))):
                identities[(p.get("venue"), o["id"])] = o["maker"]
        elif e["type"] == "offer.cancelled" and integer(p.get("offer")):
            cancelled.add((p.get("venue"), p["offer"]))
    # Only link a venue pseudonym through the SAME offer id in its public feed.
    for vid, book in snapshot.get("books", {}).items():
        for o in book.get("offers", []):
            team = identities.get((vid, o.get("id")))
            if team and isinstance(o.get("maker"), str):
                aliases.setdefault((vid, o["maker"]), set()).add(team)
    quotes, rejected, seen = [], Counter(), set()
    venues = {v["venue"]: v for v in snapshot.get("venues", {}).get("venues", [])}
    for vid, book in snapshot.get("books", {}).items():
        if venues.get(vid, {}).get("status") != "open":
            rejected["closed_or_unknown_venue"] += len(book.get("offers", []))
            continue
        for o in book.get("offers", []):
            oid = o.get("id")
            if not integer(oid) or oid in seen:
                rejected["invalid_or_duplicate_id"] += 1
                continue
            seen.add(oid)
            if o.get("venue") != vid or o.get("status") != "open" or o.get("to") is not None:
                rejected["non_public_open_quote"] += 1
                continue
            if (vid, oid) in cancelled:
                rejected["cancelled"] += 1
                continue
            if (not integer(o.get("expires_tick")) or o["expires_tick"] <= tick
                    or not integer(o.get("created_tick")) or o["created_tick"] > tick):
                rejected["expired_or_unknown_time"] += 1
                continue
            maker = identities.get((vid, oid))
            if not maker:
                alias = aliases.get((vid, o.get("maker")), set())
                maker = next(iter(alias)) if len(alias) == 1 else o.get("maker")
            if not TEAM.fullmatch(str(maker)):
                rejected["unresolved_maker"] += 1
                continue
            g, w = o.get("give"), o.get("want")
            if not isinstance(g, dict) or not isinstance(w, dict):
                rejected["unsupported_bundle"] += 1
                continue
            ga, gt, wa, wt = (g.get("assets", []), g.get("types", []),
                              w.get("assets", []), w.get("types", []))
            gc, wc = g.get("cash", 0), w.get("cash", 0)
            if not all(isinstance(v, list) for v in (ga, gt, wa, wt)) or not integer(gc) or not integer(wc):
                rejected["unsupported_bundle"] += 1
                continue
            if (len(ga) == 1 and isinstance(ga[0], dict) and ga[0].get("kind") == "card"
                    and not gt and not wa and not wt and gc == 0 and integer(wc, 1)):
                side, ref, price = "ask", ga[0].get("ref"), wc
            elif (not ga and not gt and not wa and len(wt) == 1 and isinstance(wt[0], str)
                  and wt[0].startswith("card:") and wc == 0 and integer(gc, 1)):
                side, ref, price = "bid", wt[0][5:], gc
            else:
                rejected["unsupported_bundle"] += 1
                continue
            if not REF.fullmatch(str(ref)):
                rejected["invalid_ref"] += 1
                continue
            quotes.append(Quote(oid, vid, maker, side, ref, price, o["created_tick"], o["expires_tick"]))
    return tick, venues, events, quotes, dict(rejected)


def analyze(snapshot, target="v18", previous=None, max_scan_ticks=2):
    tick, venues, events, quotes, rejected = normalize(snapshot)
    target_info = venues.get(target, {})
    owner = target_info.get("owner")
    start = snapshot.get("clock_start", {}).get("tick", tick)
    blocks = []
    if not integer(start) or not 0 <= tick - start <= max_scan_ticks:
        blocks.append("scan_not_fresh")
    if snapshot.get("errors"):
        blocks.append("incomplete_scan")
    if target_info.get("status") != "open" or target not in snapshot.get("books", {}):
        blocks.append("target_unavailable")
    if not TEAM.fullmatch(str(owner)):
        blocks.append("target_owner_unknown")
    if target_info.get("pending_fee"):
        blocks.append("target_fee_pending")
    try:
        fee(1, target_info)
    except ValueError:
        blocks.append("target_fee_unknown")
    opportunities = []
    if not blocks:
        for ask in quotes:
            if ask.side != "ask" or ask.maker == owner:
                continue
            for bid in quotes:
                if (bid.side != "bid" or bid.ref != ask.ref or bid.maker in (owner, ask.maker)):
                    continue
                target_cost = ask.price + fee(ask.price, target_info)
                gap = target_cost - bid.price
                expiry = min(ask.expires, bid.expires)
                try:
                    saving = fee(ask.price, venues[ask.venue]) - fee(ask.price, target_info)
                except ValueError:
                    saving = None
                status = "compatible_quotes" if gap <= 0 else "renegotiation_required"
                # Structured facts only; no untrusted announcement/dealer text enters a draft.
                draft = None
                if gap <= 0 and expiry - tick >= 2 and not (ask.venue == bid.venue == target):
                    draft = (f"{ask.maker} y {bid.maker}: {ask.ref}, ask #{ask.id} {ask.price} P "
                             f"en {ask.venue}; bid #{bid.id} {bid.price} P en {bid.venue}. "
                             f"Si ambos mantienen sus límites, podéis publicar ofertas nuevas en {target}: "
                             f"a {ask.price} P, coste con comisión {target_cost} P para el comprador "
                             f"que acepta la venta. Fuentes vistas en tick {tick}, caducidad mínima "
                             f"{expiry}. Revalidar y comprobar caja/carta antes de actuar.")
                opportunities.append({
                    "id": f"{target}:{ask.id}:{bid.id}", "ref": ask.ref, "seller": ask.maker,
                    "buyer": bid.maker, "ask": asdict(ask), "bid": asdict(bid), "target": target,
                    "status": status, "quoted_spread": -gap, "required_price_change": max(0, gap),
                    "target_buyer_cost_at_ask": target_cost,
                    "buyer_fee_saving_if_accepting_same_ask": saving,
                    "expires": expiry, "remaining_ticks": expiry - tick, "draft": draft,
                    "closure_probability": None, "private_surplus": None,
                })
    opportunities.sort(key=lambda o: (-o["quoted_spread"], -o["remaining_ticks"], o["id"]))
    teams = []
    prior_teams = {t["team"]: t for t in (previous or {}).get("leaderboard", {}).get("teams", [])}
    prior_venues = {v["venue"]: v for v in (previous or {}).get("venues", {}).get("venues", [])}
    for t in sorted(snapshot.get("leaderboard", {}).get("teams", []), key=lambda t: t["rank"]):
        tid = t["team"]
        own = [v for v in venues.values() if v.get("owner") == tid and v.get("status") == "open"]
        settlements = [e for e in events if e["type"] == "settlement" and tid in e["payload"].get("parties", [])]
        counts = Counter(e["type"] for e in events if e.get("actor") == tid)
        venue_ids = {v["venue"] for v in own}
        teams.append({"team": tid, "rank": t["rank"], "score": t["score"], "market": t["market"],
                      "score_delta": t["score"] - prior_teams[tid]["score"] if tid in prior_teams else None,
                      "listed_in_feed": counts["offer.listed"], "dealer_messages_in_feed": sum(
                          1 for e in events if e["type"] == "thread.message" and e.get("actor") == tid
                          and e["payload"].get("kind") == "persona"),
                      "settlements_in_feed": len(settlements),
                      "team_trades_in_feed": sum(bool(e["payload"].get("venue")) for e in settlements),
                      "announcements_in_feed": sum(e["type"] == "venue.announcement"
                                                   and e["payload"].get("venue") in venue_ids for e in events),
                      "resolved_asks": sum(q.maker == tid and q.side == "ask" for q in quotes),
                      "resolved_bids": sum(q.maker == tid and q.side == "bid" for q in quotes),
                      "venues": [{"venue": v["venue"], "mechanism": v.get("rules", {}).get("mechanism"),
                                  "trades": v.get("trades"), "volume": v.get("volume"),
                                  "trades_delta": v["trades"] - prior_venues[v["venue"]]["trades"]
                                  if (v["venue"] in prior_venues and integer(v.get("trades"))
                                      and integer(prior_venues[v["venue"]].get("trades"))) else None,
                                  "book_offers": len(snapshot.get("books", {}).get(v["venue"], {}).get("offers", []))}
                                 for v in own]})
    return {"schema": 1, "captured_at": snapshot.get("captured_at"), "tick": tick,
            "scan_start_tick": start, "paused": snapshot.get("clock", {}).get("paused"),
            "target": target, "blocks": blocks, "rejected": rejected, "teams": teams,
            "books_scanned": len(snapshot.get("books", {})), "resolved_quotes": len(quotes),
            "feed_window": {"count": len(events), "first_tick": events[0]["tick"] if events else None,
                            "last_tick": events[-1]["tick"] if events else None, "bounded": True},
            "venue_trades": {v: d.get("trades", 0) for v, d in venues.items()},
            "compatible_count": sum(o["status"] == "compatible_quotes" for o in opportunities),
            "opportunities": opportunities,
            "limitations": ["Public quotes are not inventory, cash, private value or guaranteed execution.",
                            "Feed is bounded; absence is not inactivity or proof of no settlement.",
                            "Drafts are not sent. Revalidate on the executor; honor both teams' policies.",
                            "Observed conversions do not prove causality or extra market points."]}


def brief(report, limit=5):
    lines = [f"# Radar de mercado · tick {report['tick']}", "",
             f"Pausado: {report['paused']} · libros: {report['books_scanned']} · "
             f"cotizaciones identificadas y vigentes: {report['resolved_quotes']}.",
             f"Parejas compatibles en {report['target']}: {report['compatible_count']}. "
             f"Bloqueos: {', '.join(report['blocks']) or 'ninguno en esta foto'}.", "",
             "## Todos los equipos (ventana pública limitada)", "",
             "| Equipo | Puesto | Mercado | Listados | Tratos equipo | Anuncios | Mercados abiertos: tratos/libro |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for t in report["teams"]:
        venue = "; ".join(f"{v['venue']} {v['mechanism']}: {v['trades']}/{v['book_offers']}" for v in t["venues"])
        lines.append(f"| {t['team']} | {t['rank']} | {t['market']:.2f} | {t['listed_in_feed']} | "
                     f"{t['team_trades_in_feed']} | {t['announcements_in_feed']} | {venue} |")
    lines += ["", "## Próximas parejas a revisar", ""]
    for o in report["opportunities"][:limit]:
        lines.append(f"- {o['ref']}: {o['seller']} pide {o['ask']['price']} P / "
                     f"{o['buyer']} ofrece {o['bid']['price']} P. {o['status']}; "
                     f"cambio mínimo {o['required_price_change']} P; quedan {o['remaining_ticks']} ticks.")
        if o["draft"]:
            lines.append(f"  Borrador local: {o['draft']}")
    if not report["opportunities"]:
        lines.append("Sin parejas verificables con los datos disponibles.")
    lines += ["", "## Límites", ""] + [f"- {s}" for s in report["limitations"]]
    return "\n".join(lines) + "\n"
