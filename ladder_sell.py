"""Venta manual a un dealer con una escalera de precios (máquina A, con el OK de Jorge para cada venta).

Abre un hilo de VENTA con DEALER para una carta (o reutiliza THREAD), pide los precios de ASKS de mayor a menor (uno
cada vez, solo cuando nuestro precio anterior ya está en el hilo y el dealer ha contestado después) y acepta la puja del dealer cuando llega a nuestro siguiente precio, o
su oferta final cuando es >= FLOOR. Con EGGS manda primero esas variantes (líneas de huevo de pascua de
talk.EGG_LINES, solo a mano), una por tick, y luego regatea con las variantes normales.

Lecturas: solo GET por client("read") (lista blanca, 1 req/s). Escrituras: cada paso es un `bazaar.py do ... --live`,
así que la Gate lo comprueba (G30/G31/G32/G60) y lo apunta en el diario. Nunca imprime la clave.
FLOOR debe ser >= your_value + 1 de esa carta (lo comprueba al arrancar); se rinde a los 40 ticks.

    python3 ladder_sell.py pilar 1063 SAL-11 200 260,250,242,235,228,222,216,211,207,203,201,200
    python3 ladder_sell.py abuela 789 MAL-02 6 9,8,7,6
    python3 ladder_sell.py abuela 940 MAL-01 6 9,8,7,6 5,6          # con huevos (egg_carrier.py hace lo mismo)
    python3 ladder_sell.py pilar 788 LAV-03 8 16,14,12,11,10,9,8 - 2071   # '-' = sin huevos; 2071 = hilo abierto
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parent
DEALERS = ("abuela", "chato", "picaros", "pilar", "banco")
MAX_TICKS = 40                 # ~10 min a 15 s/tick
LAND_TICKS = 4                 # un `do` junto al runner tarda ~17 s; si nuestro precio no aparece en 4 ticks, parar
POLL_S = 4


# ------------------------------------------------------------------------------------- pure decisions

def parse_ints(s: str) -> list:
    return [] if s in ("", "-") else [int(x) for x in s.split(",")]


def normal_variants(dealer: str) -> int:
    """Ordinary variants of f"{dealer}_sell": 0 .. n-1 (the EGG_LINES tail is hand-only)."""
    from agent.talk import EGG_LINES, TEMPLATES
    tpl = f"{dealer}_sell"
    return len(TEMPLATES[tpl]) - int(EGG_LINES.get(tpl, 0))


def check_args(dealer: str, floor: int, asks: Sequence[int], eggs: Sequence[int], your_value: Optional[float]) -> list:
    """-> list of problems (empty = ok). Fail closed: unknown value, floor below value + 1, asks not descending
    or below the floor, egg variants outside the template's egg tail."""
    from agent.talk import TEMPLATES
    bad = []
    if dealer not in DEALERS:
        bad.append(f"dealer {dealer!r} not in {DEALERS}")
        return bad
    if type(your_value) not in (int, float) or not math.isfinite(your_value):
        bad.append("your_value of the asset unknown")
    elif floor < your_value + 1:
        bad.append(f"floor {floor} < your_value + 1 ({your_value + 1:.1f})")
    if not asks or any(b >= a for a, b in zip(asks, asks[1:])):
        bad.append("asks must be strictly descending")
    if asks and min(asks) < floor:
        bad.append("an ask below the floor")
    n, total = normal_variants(dealer), len(TEMPLATES[f"{dealer}_sell"])
    if any(not (n <= v < total) for v in eggs):
        bad.append(f"egg variants must be in {n}..{total - 1}")
    if len(eggs) > len(asks):
        bad.append("more eggs than asks")
    return bad


def dealer_bids(thread: Mapping, dealer: str, asset: int, tick: int) -> list:
    """Open cash-only offers of the dealer that want exactly our asset and live past this tick."""
    out = []
    for m in thread.get("messages") or ():
        o = m.get("offer") if isinstance(m, Mapping) else None
        if not isinstance(o, Mapping) or o.get("maker") != dealer or o.get("status") != "open":
            continue
        g, w = o.get("give") or {}, o.get("want") or {}
        if g.get("assets") or g.get("types") or type(g.get("cash")) is not int:
            continue
        if [a.get("id") for a in w.get("assets") or ()] != [asset] or w.get("types"):
            continue
        if type(o.get("expires_tick")) is not int or o["expires_tick"] < tick + 1:
            continue
        out.append(o)
    return out


def decide(bid: int, final: bool, sent: Sequence[int], asks: Sequence[int], floor: int) -> tuple:
    """-> ("accept", bid) | ("say", ask) | ("close", why). Code decides the numbers, never the dealer's text.
    A bid >= floor is taken when no ask is left above it or it is final (a say against a final is G31.final, and a
    say at or below the dealer's bid is G31.should_accept), even with egg lines still unsent."""
    nxt = next((a for a in asks if a not in sent and (not sent or a < sent[-1]) and a > bid), None)
    if bid >= floor and (nxt is None or final):
        return ("accept", bid)
    if nxt is None:
        return ("close", f"no ask left above the bid {bid} (floor {floor})")
    if final and bid < floor:
        return ("close", f"final {bid} < floor {floor}")             # G31.final refuses any say against a final
    return ("say", nxt)


def ours_in(thread: Mapping) -> int:
    return sum(1 for m in thread.get("messages") or () if isinstance(m, Mapping) and m.get("sender") == "t18")


def our_turn(thread: Mapping, base: int, n_sent: int) -> bool:
    """True when every ask we sent already shows in the thread (ours - base >= n_sent) and the dealer spoke after our
    last message. Night review S3: a `do` next to the live runner lands ~17 s later, and a 4-tick dealer offer is
    still there, so 'last sender is not t18' alone let us drop one ask per tick before the dealer saw the previous."""
    msgs = thread.get("messages") or ()
    last = msgs[-1] if msgs and isinstance(msgs[-1], Mapping) else {}
    return ours_in(thread) - base >= n_sent and last.get("sender") != "t18"


def variant_for(n_sent: int, eggs: Sequence[int], normal: int) -> int:
    return eggs[n_sent] if n_sent < len(eggs) else (n_sent - len(eggs)) % max(1, normal)


# ------------------------------------------------------------------------------------------- I/O

def _reader():
    from agent.client import client
    c = client("read")
    return lambda path: c._call("GET", path)


def _do(kind: str, args: Mapping, why: str) -> str:
    r = subprocess.run([sys.executable, "bazaar.py", "do", kind, "--args", json.dumps(args), "--why", why, "--live"],
                       cwd=ROOT, capture_output=True, text=True)
    out = (r.stdout or r.stderr).strip()[:160]
    print("   do", kind, args.get("price"), args.get("variant"), out, flush=True)
    return out


def _log(*a: Any) -> None:
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def _threads(get) -> list:
    th = get("/api/me/threads")
    return th.get("threads", th) if isinstance(th, dict) else th


def main(argv: Sequence[str]) -> int:
    if len(argv) < 5:
        print(__doc__)
        return 2
    dealer, asset, ref, floor = argv[0], int(argv[1]), argv[2], int(argv[3])
    asks = parse_ints(argv[4])
    eggs = parse_ints(argv[5]) if len(argv) > 5 else []
    tid = int(argv[6]) if len(argv) > 6 else None
    get = _reader()
    me = get("/api/me")
    yv = next((a.get("your_value") for a in me.get("assets") or () if a.get("id") == asset and a.get("ref") == ref), None)
    problems = check_args(dealer, floor, asks, eggs, yv)
    if problems:
        print("refused:", "; ".join(problems))
        return 1
    from agent.guards import fingerprint                     # pure: the same fingerprint the Gate checks
    normal = normal_variants(dealer)
    if tid is None:
        _do("open_thread", {"dealer": dealer, "side": "sell", "ref": ref, "asset_ids": [asset], "limit": floor},
            f"Jorge: venta manual {ref} a {dealer} (suelo {floor})")
        for _ in range(30):
            time.sleep(5)
            mine = [t for t in _threads(get) if t.get("with") == dealer and t.get("status") == "open"
                    and ((t.get("topic") or {}).get("sell") or {}).get("assets") == [asset]]
            if mine:
                tid = mine[0]["id"]
                break
        if tid is None:
            print("thread not opened: the Gate's refusal code is in logs/run/journal.jsonl (a 'refused' row, tactic "
                  "manual, kind open_thread); G30.thread_open = the bot already holds a thread with that dealer "
                  "(an Abuela CHA buy: pause dealers first, and a manual Abuela sale also pulls the CHA closer bid)")
            return 1
    _log("thread", tid)
    sent: list = []
    acted, start, base, said = None, None, None, None
    while True:
        clk = get("/api/clock")
        tick = clk["tick"]
        start = tick if start is None else start
        if tick - start > MAX_TICKS:
            _do("close_thread", {"thread_id": tid, "ref": ref}, "Jorge: venta manual, fin de ventana")
            _log("window over, closing")
            return 0
        t = get(f"/api/threads/{tid}")
        t = t.get("thread", t)
        if t.get("status") != "open":
            _log("thread", t.get("status"), t.get("closed_reason"), "-> done")
            return 0
        base = ours_in(t) if base is None else base
        hers = dealer_bids(t, dealer, asset, tick)
        if said is not None and ours_in(t) - base < len(sent) and tick - said > LAND_TICKS:
            _log(f"our ask {sent[-1]} is not in the thread after {LAND_TICKS} ticks (refused? see the journal) -> stop")
            return 1
        if acted == tick or not our_turn(t, base, len(sent)) or not hers:
            time.sleep(POLL_S)
            continue                                         # one step per dealer answer to our last ask
        o = max(hers, key=lambda x: (x.get("created_tick") or 0, x["id"]))
        bid, final = o["give"]["cash"], o.get("final") is True
        act = decide(bid, final, sent, asks, floor)
        _log(f"tick {tick} {dealer} bids {bid}{' FINAL' if final else ''}; our last {sent[-1] if sent else None} -> {act}")
        if act[0] == "accept":
            _do("accept", {"offer_id": o["id"], "source": "dealer", "ref": ref, "side": "sell", "price": bid,
                           "thread_id": tid, "give_asset": asset, "fingerprint": fingerprint(o), "resupply": False,
                           "venue": dealer}, f"Jorge: {ref} a {dealer} a {bid}")
            acted = tick
            time.sleep(30)
            continue
        if act[0] == "close":
            _do("close_thread", {"thread_id": tid, "ref": ref}, f"Jorge: {dealer} no llega ({act[1]})")
            return 0
        v = variant_for(len(sent), eggs, normal)
        _do("say", {"thread_id": tid, "ref": ref, "price": act[1], "template": f"{dealer}_sell", "variant": v},
            f"Jorge: {'huevo' if len(sent) < len(eggs) else 'regateo'} {dealer} v{v}, pedimos {act[1]}")
        sent.append(act[1])
        acted, said = tick, tick
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
