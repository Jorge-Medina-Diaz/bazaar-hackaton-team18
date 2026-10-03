"""M4b talk: conversation guards G30-G32, G50, G51 and the text firewall G60 (docs/harness-spec.md §2.5, §4).

PURE: no I/O, no clock reads, no network. The Gate passes everything in. Foreign text never reaches this
module: the World carries no text, and the only text we ever look at is the one we render from TEMPLATES.

NOTES (M4b, night build)
- check() covers open_thread (G30), say (G31), accept with source "dealer" (G32), duel_say (G50) and
  duel_accept (G51). Any other kind -> Verdict(False, "G02.kind"). Every exception -> refuse (fail closed).
- plan_cfg is not part of the check() signature, so `grant_lookahead_ticks` and `days_sign` are read from
  cfg with getattr(cfg, "GRANT_LOOKAHEAD_TICKS", 3) / getattr(cfg, "DAYS_SIGN", None). Lead: either add them
  to guards.Cfg or have guards copy them from plan_cfg.
- Two-issue duels (price + days): W(d) is modelled as your_days_weight * d (unknown in reality, U-13). The
  conservative bound (surplus >= 1 + |w| * max(d, 10 - d)) is applied ALWAYS, also when days_sign is known.
  With your_days_weight null (as in the practice) every two-issue price is refused (G50.days_unknown).
- duel_accept needs guards.duel_fingerprint (M4a). If agent.guards cannot be imported, G51 refuses
  ("G51.no_fingerprint"). A dealer accept does not compare guards.fingerprint (G32 does not ask for it); it
  matches offer id, maker, recipient, status, expiry, exact shape (offer_safety) and price.
- "Distinct from the last text of the thread": the World has no text, so it is enforced structurally:
  every template carries {p} (duel_days also {d}) and G31/G50 forbid repeating our (price[, days]).
  firewall() also takes an optional last_text for callers that have it.
- Dealer templates exist only for abuela and chato; a new dealer has no template -> G60.template (refuse).
- `fresh` for duel_accept: the duel Mapping, or the /api/duels payload ({"duels": [...]}) or a list.
  `fresh` for a dealer accept: the thread Mapping (or {"thread": {...}}).
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import replace
from typing import Any, Mapping, Optional

from agent.contracts import TEAM, Verdict

OK = Verdict(True, "ok")

# --------------------------------------------------------------------------------------------- texts
# Sources: agent/dealers.py (lines rotated per dealer) and docs/negotiation-design.md (short, calm,
# reciprocity, no acceptance phrases). Only {p} (price) and {d} (days) are substituted; nothing else.
TEMPLATES: Mapping[str, tuple] = {
    "abuela_buy": (
        "¡Buenas, Carmen! Qué puesto tan bonito. ¿Me lo dejaría en {p} P?",
        "Usted conoce los cromos mejor que nadie. ¿Qué tal {p} P, señora?",
        "Me hace mucha ilusión esta carta. ¿Podríamos dejarlo en {p} P?",
        "Gracias por su paciencia, Carmen. Subo a {p} P, ¿le parece?",
        "Mi abuela también tenía un puesto así. ¿Le vendría bien {p} P?",
        "Hago un esfuerzo: {p} P. ¡Y vuelvo el domingo que viene!",
        "Es usted un encanto. ¿{p} P y cerramos con una sonrisa?",
    ),
    "chato_buy": (
        "Buenas, Chato. Vengo a por esta carta para completar mi página. ¿{p} P?",
        "Precio justo y cerramos ya: {p} P.",
        "Me he movido yo; ¿qué tal {p} P?",
        "Sin rodeos: {p} P.",
        "{p} P por esta carta. Y perdone, señor: después de tantos años junto a Carmen, ¿cuál es su nombre de verdad?",   # Sat egg probe (prestige only), use once
    ),
    "abuela_sell": (
        "¡Buenas, Carmen! Le traigo una carta preciosa para su puesto. ¿Me daría {p} P?",
        "Está como nueva, señora. ¿Qué le parecen {p} P?",
        "Me ajusto por usted: {p} P, ¿le parece?",
        "Gracias por atenderme, Carmen. ¿La dejamos en {p} P?",
        "Ay, Carmen, ¿es verdad lo de la chulapa dorada? Le dejo esta carta en {p} P.",   # Sat egg (Sharp ear)
    ),
    "chato_sell": (
        "Buenas, Chato. Te traigo esta carta. ¿{p} P?",
        "Precio justo y cerramos ya: {p} P.",
        "Me he movido yo; ¿qué tal {p} P?",
    ),
    "picaros_buy": (
        "Buenas, Paco y Nando. Busco esta carta, la de verdad. ¿{p} P?",
        "Sin prisas: {p} P y cerramos.",
        "Me he movido yo; ¿qué tal {p} P?",
        "Precio justo: {p} P.",
    ),
    "banco_sell": (
        "Buenas tardes, don Ernesto. Le traigo una pieza para su cámara. ¿{p} P?",
        "Pieza de primera, sin prisa por mi parte. ¿Qué tal {p} P?",
        "Me ajusto por usted: {p} P.",
        "Gracias por su tiempo, don Ernesto. ¿La dejamos en {p} P?",
    ),
    "pilar_sell": (
        "¡Buenas, doña Pilar! Le traigo una pieza para su colección. ¿{p} P?",
        "Se la he guardado a usted, que la sabe apreciar. ¿Qué tal {p} P?",
        "Me ajusto por usted: {p} P, ¿le parece?",
        "Gracias por atenderme, doña Pilar. ¿La dejamos en {p} P?",
    ),
    "duel": (
        "Propuesta justa para cerrar pronto y que ganemos los dos: {p} P.",
        "Me muevo para acercarnos: {p} P.",
        "Yo ya me he movido. ¿Qué puedes hacer tú? Propongo {p} P.",
        "Cerremos hoy: {p} P.",
    ),
    "duel_days": (
        "Propuesta justa para cerrar pronto: {p} P y {d} días.",
        "Me muevo para acercarnos: {p} P con {d} días.",
        "Yo ya me he movido. Propongo {p} P y {d} días.",
    ),
}

MAX_LEN = 280
FORBIDDEN = re.compile(
    r"(?i)l[íi]mite|limit|reserv|m[íi]nimo|m[áa]ximo|presupuesto|budget|valor|value|afinidad|affinity"
    r"|multiplic|clave|key|token|tk-|bk_|http|system|ignore|\{|\}")
_DIGITS = re.compile(r"\d+")


def render(template: str, variant: int, price: int, days: Optional[int] = None) -> str:
    """Text of TEMPLATES[template][variant] with {p} = price and {d} = days. ValueError on any misuse."""
    if template not in TEMPLATES:
        raise ValueError(f"unknown template {template!r}")
    lines = TEMPLATES[template]
    if type(variant) is not int or not 0 <= variant < len(lines):
        raise ValueError(f"variant out of range for {template!r}")
    if type(price) is not int or price < 0:
        raise ValueError("price must be a non-negative int")
    line = lines[variant]
    if "{d}" in line:
        if type(days) is not int or not 0 <= days <= 10:
            raise ValueError("template needs days as int 0..10")
        line = line.replace("{d}", str(days))
    elif days is not None:
        raise ValueError("template has no days")
    return line.replace("{p}", str(price))


def _bad_char(ch: str) -> bool:
    cat = unicodedata.category(ch)
    return cat in ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")


def firewall(text: str, price: int, days: Optional[int], *, template: Optional[str] = None,
             last_text: Optional[str] = None) -> Verdict:
    """G60. Digits only str(price)/str(days); no forbidden term; <= 280 chars; no control or format chars;
    different from last_text; and, when `template` is given, exactly one of its rendered variants."""
    try:
        if type(text) is not str or not text.strip():
            return Verdict(False, "G60.empty")
        if type(price) is not int or (days is not None and type(days) is not int):
            return Verdict(False, "G60.args")
        if len(text) > MAX_LEN:
            return Verdict(False, "G60.length", str(len(text)))
        if any(_bad_char(ch) for ch in text):
            return Verdict(False, "G60.control")
        allowed = {str(price)} | ({str(days)} if days is not None else set())
        found = set(_DIGITS.findall(text))
        if not found <= allowed:
            return Verdict(False, "G60.digits")
        if any(ch.isdigit() and not ch.isascii() for ch in text) or any(
                unicodedata.numeric(ch, None) is not None and not ch.isascii() for ch in text):
            return Verdict(False, "G60.digits")
        if FORBIDDEN.search(text) or FORBIDDEN.search(unicodedata.normalize("NFKC", text)):
            return Verdict(False, "G60.term")
        if last_text is not None and text == last_text:
            return Verdict(False, "G60.repeat")
        if template is not None:
            if template not in TEMPLATES:
                return Verdict(False, "G60.template")
            rendered = set()
            for i in range(len(TEMPLATES[template])):
                try:
                    rendered.add(render(template, i, price, days))
                except ValueError:
                    pass
            if text not in rendered:
                return Verdict(False, "G60.template")
        return OK
    except Exception as e:  # noqa: BLE001 - fail closed
        return Verdict(False, "G60.error", type(e).__name__)


def _validate_templates() -> None:
    """Templates are checked at import: each has {p}, duel_days has {d}, each renders through the firewall."""
    for name, lines in TEMPLATES.items():
        if not lines:
            raise AssertionError(f"template {name} is empty")
        for i, line in enumerate(lines):
            if "{p}" not in line or ("{d}" in line) != (name == "duel_days"):
                raise AssertionError(f"template {name}[{i}] placeholders")
            if re.search(r"\d", line):
                raise AssertionError(f"template {name}[{i}] has a literal digit")
            for p in (1, 37, 999999):
                d = 7 if name == "duel_days" else None
                v = firewall(render(name, i, p, d), p, d, template=name)
                if not v.ok:
                    raise AssertionError(f"template {name}[{i}] fails G60: {v.code}")


_validate_templates()

# ------------------------------------------------------------------------------------------ helpers


class _Refuse(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code, self.detail = code, detail


def _need(cond: bool, code: str, detail: str = "") -> None:
    if not cond:
        raise _Refuse(code, detail)


def _num(x: Any) -> bool:
    return type(x) in (int, float) and math.isfinite(x)


def _plain(x: Any) -> Any:
    """Frozen World data (MappingProxyType / tuple) and raw JSON (dict / list) compare equal after this."""
    if isinstance(x, Mapping):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    return x


def _get(m: Any, k: str, default: Any = None) -> Any:
    return m.get(k, default) if isinstance(m, Mapping) else default


def _set_of(ref: str) -> str:
    return ref.split("-", 1)[0]


def _cfg(cfg: Any, name: str, default: Any) -> Any:
    return getattr(cfg, name, default)


def _own_counts(book, ref: str) -> dict:
    """Book.projected without the copy of `ref` that our own open dealer buy thread for `ref` stands for
    (M17 integration fix). build_book counts a thread's standing price in projected; valuing or page-checking
    the thread's OWN ref against that made dv_add a 2nd-copy value (every dealer buy refused G31/G32.limit)
    and closes_page(projected, ref) always False (INV-10 hole: a dealer could close RET/CHA)."""
    c = dict(book.projected or {})
    if ref in set((book.thread_ref or {}).values()) and int(c.get(ref, 0)) > int((book.held or {}).get(ref, 0)):
        c[ref] = int(c[ref]) - 1
    return c


def _dv_add(world, book, valuer, ref: str) -> float:
    v = valuer.delta_add(_own_counts(book, ref), ref, book.packs)
    sv = (world.server_values or {}).get(ref)
    out = min(float(v), float(sv)) if _num(sv) else float(v)
    _need(_num(out), "G3x.valuation", f"dv_add {ref}")
    return out


def _dv_rm(world, book, valuer, ref: str) -> float:
    v = float(valuer.delta_remove(book.held, ref, book.packs))
    sv = (world.server_values or {}).get(ref)
    out = max(v, float(sv)) if _num(sv) else v
    _need(_num(out), "G3x.valuation", f"dv_rm {ref}")
    return out


def _free(book, ref: str) -> int:
    return (int(book.held.get(ref, 0)) - int(book.listed.get(ref, 0)) - int(book.pending_out.get(ref, 0)))


def _protected_ok(world, book, ref: str, asset_ids, code: str, own_thread: bool = False) -> None:
    """G13 without the J13 exception (dealers never get protected copies).
    own_thread: the assets are the topic of our own open sell thread, which build_book already counts as listed;
    they are not listed elsewhere, so they are not refused as listed and are counted back as free (live 3 Oct)."""
    ids = list(asset_ids)
    if own_thread:
        n = len(set(ids) & set(book.listed_assets))
        book = replace(book, listed_assets=frozenset(set(book.listed_assets) - set(ids)),
                       listed={**dict(book.listed), ref: max(0, int(book.listed.get(ref, 0)) - n)})
    _need(len(ids) >= 1 and len(ids) == len(set(ids)), code + ".assets")
    assets = {a.get("id"): a for a in (_get(world.me, "assets") or ()) if isinstance(a, Mapping)}
    for aid in ids:
        a = assets.get(aid)
        _need(a is not None, code + ".not_ours", str(aid))
        _need(a.get("kind") == "card" and a.get("ref") == ref, code + ".asset_ref", str(aid))
        _need(aid not in book.listed_assets, code + ".listed", str(aid))
    _need(_free(book, ref) - len(ids) >= int(book.keep.get(ref, 0)), "G13.protected", ref)


def _closes_forbidden(book, valuer, cfg, ref: str, code: str) -> None:
    """INV-10: a dealer never closes a page (RET/CHA; only sets in ALLOW_DEALER_CLOSE may), nor delivers the
    frozen closer card."""
    _need(ref not in set((book.frozen_closer or {}).values()), code + ".frozen_closer", ref)
    allow = _cfg(cfg, "ALLOW_DEALER_CLOSE", frozenset({"LAT"}))
    if valuer.closes_page(_own_counts(book, ref), ref):
        _need(_set_of(ref) in allow and _set_of(ref) not in ("RET", "CHA"), code + ".closes_page", ref)


def _thread_side(thread: Mapping) -> str:
    topic = _get(thread, "topic") or {}
    if "buy" in topic:
        return "buy"
    if "sell" in topic:
        return "sell"
    raise _Refuse("G31.topic")


def _offers_of(thread: Mapping) -> list:
    out = []
    for o in _get(thread, "standing_offers") or ():
        if isinstance(o, Mapping):
            out.append(o)
    for m in _get(thread, "messages") or ():
        o = _get(m, "offer")
        if isinstance(o, Mapping):
            out.append(o)
    return out


def _our_prices(thread: Mapping, side: str) -> list:
    """Our own prices in the thread, from the server (give.cash when buying, want.cash when selling)."""
    out = []
    for o in _offers_of(thread):
        if o.get("maker") == TEAM:
            c = _get(o.get("give" if side == "buy" else "want"), "cash")
            if type(c) is int:
                out.append(c)
    return out


def _dealer_standing(thread: Mapping, dealer: str) -> list:
    return [o for o in _offers_of(thread) if o.get("maker") == dealer and o.get("status") == "open"]


def _dealer_price(o: Mapping, side: str) -> Optional[int]:
    c = _get(o.get("want" if side == "buy" else "give"), "cash")
    return c if type(c) is int else None


def _grant_soon(world, cfg) -> bool:
    """True if a scheduled grant with packs is due within GRANT_LOOKAHEAD_TICKS (or already due)."""
    ticks = _cfg(cfg, "GRANT_LOOKAHEAD_TICKS", 3)
    up = _get(world.schedule, "upcoming")
    _need(isinstance(up, (list, tuple)) and _num(world.t_hours) and _num(world.tick_seconds),
          "G30.grant_unknown")
    horizon = world.t_hours + ticks * world.tick_seconds / 3600.0
    for e in up:
        _need(isinstance(e, Mapping), "G30.grant_unknown")
        packs = _get(_get(e, "params"), "packs")
        if packs or "pack" in str(e.get("action", "")):
            at = e.get("at_hours")
            _need(_num(at), "G30.grant_unknown")
            if at <= horizon:
                return True
    return False


def _msg_used(counters, kind: str, oid: int) -> bool:
    msgs = getattr(counters, "msgs", None)
    if msgs is None:
        return False
    return any(k in msgs for k in (f"{kind}:{oid}", (kind, oid), oid))


# ------------------------------------------------------------------------------------- dealer guards


def _g30_open(a, world, book, valuer, cfg) -> None:
    dealer, side, ref = a["dealer"], a["side"], a["ref"]
    _need(dealer in (_get(world.me, "unlocked") or ()), "G30.locked", dealer)
    _need(dealer not in book.thread_by_dealer, "G30.thread_open", dealer)
    for t in (world.threads or {}).values():
        _need(not (_get(t, "with") == dealer and _get(t, "status") == "open"), "G30.thread_open", dealer)
    until = book.dealer_block.get(dealer)
    _need(until is None or (type(until) is int and world.tick >= until), "G30.blocked", dealer)
    _need(not book.packs, "G14.pack")
    margin = _cfg(cfg, "DEALER_MARGIN", 1.0)
    if side == "buy":
        _need(a["asset_ids"] == (), "G30.assets")
        need = book.needs.get(ref) or next((n for n in book.needs.values() if getattr(n, "ref", None) == ref), None)
        _need(need is not None, "G30.no_need", ref)
        cap = min(math.floor(_dv_add(world, book, valuer, ref) - margin), int(need.max_price))
        _need(1 <= a["limit"] <= cap, "G30.limit", f"{a['limit']} > {cap}")
        _closes_forbidden(book, valuer, cfg, ref, "G30")
        _need(not _grant_soon(world, cfg), "G30.grant_soon")
        _need(int(book.paths.get(ref, 0)) == 0, "G15.path", ref)
        _need(a["limit"] <= book.cash_free, "G16.cash")
    else:
        _protected_ok(world, book, ref, a["asset_ids"], "G30")
        floor_ = math.ceil(_dv_rm(world, book, valuer, ref) + margin)
        _need(a["limit"] >= floor_, "G30.limit", f"{a['limit']} < {floor_}")


def _limit_t(a_ref, tid, side, world, book, valuer, cfg) -> int:
    margin = _cfg(cfg, "DEALER_MARGIN", 1.0)
    lim = book.thread_limit.get(tid)
    _need(type(lim) is int, "G31.no_limit", str(tid))
    if side == "buy":
        return min(lim, math.floor(_dv_add(world, book, valuer, a_ref) - margin))
    return max(lim, math.ceil(_dv_rm(world, book, valuer, a_ref) + margin))


def _our_thread(world, book, tid) -> Mapping:
    t = (world.threads or {}).get(tid)
    _need(isinstance(t, Mapping), "G31.no_thread", str(tid))
    _need(_get(t, "status") == "open", "G31.not_open", str(tid))
    _need(_get(t, "team", TEAM) == TEAM, "G31.not_ours", str(tid))
    return t


def _g31_say(a, world, book, valuer, cfg, counters) -> None:
    tid, ref, p = a["thread_id"], a["ref"], a["price"]
    t = _our_thread(world, book, tid)
    _need(book.thread_ref.get(tid) == ref, "G31.ref", str(tid))
    side = _thread_side(t)
    if side == "buy":
        _need(not book.packs, "G14.pack")
    _need(not _msg_used(counters, "thread", tid), "G04.msg", str(tid))
    dealer = _get(t, "with")
    lim = _limit_t(ref, tid, side, world, book, valuer, cfg)
    prices = list(book.thread_prices.get(tid, ())) + _our_prices(t, side)
    _need(p >= 1, "G31.price")
    _need(p not in prices, "G31.repeat", str(p))
    if side == "buy":
        last = max(prices) if prices else None
        _need((last is None or last < p) and p <= lim, "G31.limit", f"last={last} p={p} lim={lim}")
    else:
        last = min(prices) if prices else None
        _need((last is None or p < last) and p >= lim, "G31.limit", f"last={last} p={p} lim={lim}")
    from agent import offer_safety
    topic = _get(t, "topic")
    # only offers of the thread's own card bind us: a Pícaros "trick" (another card at the asked price) can never be
    # accepted (G32.shape), so its "final" or its price must not freeze the haggle
    standing = [o for o in _dealer_standing(t, dealer) if offer_safety.offer_ok(o, topic, buying=side == "buy")]
    _need(not any(o.get("final") is True for o in standing), "G31.final")
    for o in standing:
        dp = _dealer_price(o, side)
        _need(dp is not None, "G31.shape")
        _need(not (dp <= p if side == "buy" else dp >= p), "G31.should_accept", str(dp))
    _text_ok(f"{dealer}_{side}", a, p, None)


def _g32_accept(a, world, book, valuer, cfg, fresh) -> None:
    from agent import offer_safety
    tid, ref, p, side = a["thread_id"], a["ref"], a["price"], a["side"]
    _need(tid is not None, "G32.thread")
    _need(side in ("buy", "sell"), "G32.side")
    t = _our_thread(world, book, tid)
    _need(book.thread_ref.get(tid) == ref, "G32.ref", str(tid))
    _need(_thread_side(t) == side, "G32.side")
    ft = _get(fresh, "thread", fresh)
    _need(isinstance(ft, Mapping) and ft.get("id") == tid, "G10.shape", "fresh thread")
    _need(ft.get("status") == "open", "G32.not_open")
    dealer = _get(t, "with")
    _need(ft.get("with") == dealer, "G10.shape", "dealer")
    topic = ft.get("topic")
    _need(_plain(topic) == _plain(_get(t, "topic")), "G10.shape", "topic")   # World freezes lists to tuples
    match = [o for o in _offers_of(ft) if o.get("id") == a["offer_id"]]
    _need(len(match) >= 1, "G32.no_offer")
    o = match[-1]
    _need(offer_safety.executable_offer(o, topic, dealer=dealer, team=TEAM, tick=world.tick + 1,
                                        buying=side == "buy"), "G32.not_executable")
    _need(offer_safety.offer_ok(o, topic, buying=side == "buy"), "G32.shape")
    _need(_dealer_price(o, side) == p, "G32.price", "offer price != intent price")
    lim = _limit_t(ref, tid, side, world, book, valuer, cfg)
    margin = _cfg(cfg, "DEALER_MARGIN", 1.0)
    if side == "buy":
        _need(not book.packs, "G14.pack")
        _need(a["give_asset"] is None, "G32.give_asset")
        _need(p <= lim, "G32.limit", f"{p} > {lim}")
        _need(_dv_add(world, book, valuer, ref) - p >= margin, "G32.margin")
        _closes_forbidden(book, valuer, cfg, ref, "G32")
        # the Book already reserved this thread's own max(standing, our prices) (guards.build_book): add it back,
        # or every accept inside a thread needs twice its price (live Sat: SAL-11 at 159 refused, cash 303)
        try:
            from agent.guards import _thread_standing
            reserved = max([_thread_standing(t) or 0] + [int(x) for x in book.thread_prices.get(tid, ()) or ()])
        except Exception:  # noqa: BLE001 - unknown: no add-back (fail closed)
            reserved = 0
        _need(p <= book.cash_free + reserved, "G16.cash", f"{p} > {book.cash_free} + {reserved}")
    else:
        ids = tuple((topic.get("sell") or {}).get("assets") or ())
        _protected_ok(world, book, ref, ids, "G32", own_thread=True)
        _need(p >= lim, "G32.limit", f"{p} < {lim}")
        _need(p - _dv_rm(world, book, valuer, ref) >= margin, "G32.margin")


def _text_ok(template: str, a, price: int, days: Optional[int]) -> None:
    _need(template in TEMPLATES, "G60.template", template)
    _need(a["template"] == template, "G60.template", f"{a['template']} != {template}")
    try:
        text = render(template, a["variant"], price, days)
    except ValueError as e:
        raise _Refuse("G60.render", str(e)) from None
    v = firewall(text, price, days, template=template)
    _need(v.ok, v.code, v.detail)


# --------------------------------------------------------------------------------------- duel guards


def _find_duel(src: Any, did: int) -> Optional[Mapping]:
    if isinstance(src, Mapping) and isinstance(src.get("duels"), (list, tuple)):
        src = src["duels"]
    if isinstance(src, Mapping):
        return src if _get(src, "duel", _get(src, "id")) == did else None
    if isinstance(src, (list, tuple)):
        for d in src:
            if isinstance(d, Mapping) and d.get("duel", d.get("id")) == did:
                return d
    return None


def _duel_basics(d: Mapping) -> tuple:
    _need(d.get("status") == "live", "G50.not_live")
    role = d.get("role")
    _need(role in ("seller", "buyer"), "G50.role")
    lim = d.get("your_limit")
    _need(_num(lim), "G50.limit")
    issues = d.get("issues")
    _need(isinstance(issues, (list, tuple)) and "price" in issues, "G50.issues")
    return (1 if role == "seller" else -1), float(lim), ("days" in issues)


def _days_penalty(d: Mapping, days: int, cfg: Any = None) -> float:
    """Worst-case effect of the days issue: max_d |W(d) - W(days)| with W(d) = your_days_weight * d.
    A null weight uses cfg.DAYS_WEIGHT_FALLBACK (plan duels.days_weight_fallback); none -> refuse."""
    w = d.get("your_days_weight")
    if w is None:
        w = _cfg(cfg, "DAYS_WEIGHT_FALLBACK", None)
    _need(_num(w), "G50.days_unknown")
    return abs(float(w)) * max(days, 10 - days)


def _g50_say(a, world, cfg, counters) -> None:
    did, p, days = a["duel_id"], a["price"], a["days"]
    d = _find_duel(world.duels, did)
    _need(d is not None, "G50.no_duel", str(did))
    s, lim, two = _duel_basics(d)
    dl = d.get("deadline_tick")
    _need(type(dl) is int and world.tick <= dl, "G50.deadline")
    _need(not _msg_used(counters, "duel", did), "G04.msg", str(did))
    _need(p >= 1, "G50.price")
    if two:
        _need(type(days) is int and 0 <= days <= 10, "G50.missing_days")
        penalty = _days_penalty(d, days, cfg)
    else:
        _need(days is None, "G50.days_not_issue")
        penalty = 0.0
    _need(s * (p - lim) >= 1 + penalty, "G50.limit", f"p={p} L={lim} pen={penalty}")
    ours = []                                   # (price, days) of every offer of ours the server shows
    mine = d.get("your_offer")
    if isinstance(mine, Mapping) and mine.get("price") is not None:
        ours.append((mine.get("price"), mine.get("days")))
    for m in d.get("messages") or ():
        if isinstance(m, Mapping) and m.get("from") == "you" and m.get("price") is not None:
            ours.append((m.get("price"), m.get("days")))
    for lp, ld in ours:
        _need(_num(lp), "G50.shape")
        _need(s * (lp - p) >= 0, "G50.monotone", f"ours={lp} p={p}")
    if isinstance(mine, Mapping) and mine.get("price") is not None:
        same_days = (not two) or mine.get("days") == days
        _need(not (mine.get("price") == p and same_days), "G50.repeat")
    rival = d.get("rival_offer")
    if isinstance(rival, Mapping) and _num(rival.get("price")):
        _need(s * (p - rival["price"]) >= 0, "G50.worse_than_rival", str(rival["price"]))
    _text_ok("duel_days" if two else "duel", a, p, days if two else None)


def _duel_fp(d: Mapping) -> str:
    try:
        from agent.guards import duel_fingerprint
    except Exception:  # noqa: BLE001 - M4a not built: fail closed
        raise _Refuse("G51.no_fingerprint") from None
    return duel_fingerprint(d)


def _g51_accept(a, world, cfg, counters, fresh, now) -> None:
    did = a["duel_id"]
    _need(fresh is not None, "G51.no_fresh")
    d = _find_duel(fresh, did)
    _need(d is not None, "G10.shape", "duel missing in re-read")
    s, lim, two = _duel_basics(d)
    rival = d.get("rival_offer")
    _need(isinstance(rival, Mapping), "G51.no_rival")
    rp, rt = rival.get("price"), rival.get("tick")
    _need(_num(rp) and type(rt) is int, "G10.shape", "rival_offer")
    _need(rt == world.tick, "G51.rival_tick", f"{rt} != {world.tick}")
    _need(_duel_fp(d) == a["fingerprint"], "G51.fingerprint")
    if two:
        rd = rival.get("days")
        _need(type(rd) is int and 0 <= rd <= 10, "G51.days")
        penalty = _days_penalty(d, rd, cfg)
    else:
        penalty = 0.0
    _need(s * (rp - lim) >= 1 + penalty, "G51.limit", f"rival={rp} L={lim} pen={penalty}")
    dl = d.get("deadline_tick")
    _need(type(dl) is int and world.tick <= dl - 1, "G51.deadline")
    _need(_num(now) and world.tick_deadline - now >= _cfg(cfg, "TICK_MARGIN_S", 2.0), "G51.late")
    acc = getattr(counters, "accepts", 0)
    _need(acc < world.limits.accepts, "G04.accepts")


# ----------------------------------------------------------------------------------------- entry


def check(intent, world, book, valuer, cfg, counters, *, fresh=None, now: float) -> Verdict:
    """G30-G32, G50, G51 (+ G60 on every text). PURE. Any exception -> refuse (fail closed)."""
    try:
        a, kind = intent.args, intent.kind
        if kind in ("open_thread", "say") or (kind == "accept" and a.get("source") == "dealer"):
            _need(bool(book.valuation_ok), "G06.valuation")
        if kind == "open_thread":
            _g30_open(a, world, book, valuer, cfg)
        elif kind == "say":
            _g31_say(a, world, book, valuer, cfg, counters)
        elif kind == "accept" and a.get("source") == "dealer":
            _g32_accept(a, world, book, valuer, cfg, fresh)
        elif kind == "duel_say":
            _g50_say(a, world, cfg, counters)
        elif kind == "duel_accept":
            _g51_accept(a, world, cfg, counters, fresh, now)
        else:
            return Verdict(False, "G02.kind", f"talk does not judge {kind}")
        return OK
    except _Refuse as r:
        return Verdict(False, r.code, r.detail)
    except Exception as e:  # noqa: BLE001 - fail closed on anything unexpected
        return Verdict(False, "G3x.error", f"{type(e).__name__}: {e}"[:200])
