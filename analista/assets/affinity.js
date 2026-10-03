/* Radar de barrios · estimador bayesiano de los multiplicadores de cada equipo, en el navegador.
   Puerto fiel de agent/affinity.py (mismas verosimilitudes, pesos y suelo EPS): cada equipo tiene los seis
   multiplicadores {0,5 0,7 0,9 1,1 1,3 1,6}, uno por barrio, en un orden privado; se puntúan las 720 permutaciones
   con la evidencia pública (tratos, pujas y ventas publicadas, saltos de puntuación). Puro: sin red ni DOM. */
"use strict";
const T18Affinity = (() => {
  const MULTS = [0.5, 0.7, 0.9, 1.1, 1.3, 1.6];
  const SETS = ["LAV", "MAL", "LAT", "SAL", "RET", "CHA"];
  const BOOK = {common: 10, uncommon: 25, rare: 70, epic: 180, legendary: 450};
  const EPS = 0.05, P_REPEAT = 0.75, PAGE_BOOK = 5 * 10 + 3 * 25 + 2 * 70;
  const PAGE_SHARE = [[0.0, 0.35], [0.1, 0.5], [1.0, 0.15]];
  const WEIGHT = {trade_buy: 1.0, trade_sell: 0.7, dealer_buy: 0.15, dealer_sell: 0.1, bid: 0.5, ask: 0.25, score: 1.0};
  const DEALERS = new Set(["abuela", "chato"]);
  const BITS0 = Math.log2(720);

  const PERMS = [];                          // mismo orden que itertools.permutations(MULTS)
  (function perm(prefix, rest) {
    if (!rest.length) { PERMS.push(prefix); return; }
    rest.forEach((m, i) => perm([...prefix, m], [...rest.slice(0, i), ...rest.slice(i + 1)]));
  })([], MULTS);

  const sig = x => 1 / (1 + Math.exp(-Math.max(-30, Math.min(30, x))));
  const tau = p => Math.max(3, 0.25 * p);
  const likBuy = (b, p, a) => EPS + (1 - 2 * EPS) * PAGE_SHARE.reduce((s, [share, w]) => s + w * sig(((b + share * 0.25 * PAGE_BOOK) * a - p) / tau(p)), 0);
  const likSell = (b, p, a) => EPS + (1 - 2 * EPS) * ((1 - P_REPEAT) * sig((p - b * a) / tau(p)) + P_REPEAT * sig((p - 0.25 * b * a) / tau(p)));

  function rarityOfRef(ref) {                // página: 5 comunes, 3 infrecuentes, 2 raras; luego épica y legendaria
    const n = Number(String(ref || "").split("-")[1]);
    return !n ? null : n <= 5 ? "common" : n <= 8 ? "uncommon" : n <= 10 ? "rare" : n === 11 ? "epic" : "legendary";
  }
  function cardOf(o) {
    const g = o.give || {}, w = o.want || {};
    const [side, pool] = (g.assets && g.assets.length) || (g.types && g.types.length) ? ["ask", g] : ["bid", w];
    if (pool.assets && pool.assets.length) { const a = pool.assets[0]; return [side, a.set, a.rarity, a.ref]; }
    for (const t of pool.types || []) {
      const i = t.indexOf(":"), kind = i < 0 ? t : t.slice(0, i), ref = i < 0 ? "" : t.slice(i + 1);
      if (kind === "card") return [side, ref.split("-")[0], null, ref];
    }
    return [side, null, null, null];
  }

  // Evidencia: tratos (filas) y la mejor puja / venta publicada por (equipo, lado, carta) (quotes).
  function evidence(events) {
    const rows = [], quotes = {};
    [...events].sort((a, b) => a.id - b.id).forEach(e => {
      const p = e.payload || {};
      if (e.type === "settlement" && p.kind === "trade") {
        const cards = (p.items || []).filter(i => i.kind === "card" && BOOK[i.rarity]);
        const total = cards.reduce((s, i) => s + BOOK[i.rarity], 0);
        if (!cards.length || !p.price) return;
        cards.forEach(i => {
          const base = {set: i.set, book: BOOK[i.rarity], price: p.price * BOOK[i.rarity] / total, tick: e.tick, ref: i.ref};
          const dealer = DEALERS.has(p.persona) || DEALERS.has(i.frm) || DEALERS.has(i.to);
          if (!DEALERS.has(i.to)) rows.push({...base, team: i.to, kind: dealer ? "dealer_buy" : "trade_buy"});
          if (!DEALERS.has(i.frm)) rows.push({...base, team: i.frm, kind: dealer ? "dealer_sell" : "trade_sell"});
        });
      } else if (e.type === "offer.listed") {
        const o = p.offer || {};
        if (o.thread != null || DEALERS.has(o.maker)) return;
        const [side, st, rar0, ref] = cardOf(o), rar = rar0 || rarityOfRef(ref);
        const price = side === "bid" ? (o.give || {}).cash : (o.want || {}).cash;
        if (!st || !BOOK[rar] || !price) return;
        addQuote(quotes, {team: o.maker, kind: side, set: st, book: BOOK[rar], price, tick: e.tick, ref});
      }
    });
    return {rows, quotes};
  }
  const quoteKey = q => q.team + "|" + q.kind + "|" + q.ref;
  function addQuote(quotes, q) {
    const k = quoteKey(q), best = quotes[k];
    if (!best || (q.kind === "bid" ? q.price > best.price : q.price < best.price)) quotes[k] = q;
  }

  // Saltos de puntuación entre fotos de la clasificación: snaps = [{tick, round, teams: {equipo: negotiating}}].
  function scoreJumps(snaps, events, minJump = 0.05) {
    const sett = events.filter(e => e.type === "settlement" && (e.payload || {}).kind === "trade");
    const duelTicks = events.filter(e => e.type === "duel.closed").map(e => e.tick);
    const out = [];
    for (let k = 0; k + 1 < snaps.length; k++) {
      const s0 = snaps[k], s1 = snaps[k + 1];
      if (s0.round !== s1.round || duelTicks.some(t => s0.tick < t && t <= s1.tick)) continue;
      const acts = {};
      const act = t => acts[t] || (acts[t] = {team: [], dealer: 0});
      sett.forEach(e => {
        if (!(s0.tick < e.tick && e.tick <= s1.tick)) return;
        const p = e.payload, cards = (p.items || []).filter(i => i.kind === "card" && BOOK[i.rarity]);
        const dealer = DEALERS.has(p.persona);
        (p.parties || []).forEach(party => {
          if (dealer || !cards.length) { act(party).dealer += 1; return; }
          const total = cards.reduce((s, i) => s + BOOK[i.rarity], 0);
          cards.forEach(i => {
            const side = i.to === party ? "buy" : i.frm === party ? "sell" : null;
            if (side) act(party).team.push({set: i.set, book: BOOK[i.rarity], side, price: p.price * BOOK[i.rarity] / total, ref: i.ref});
          });
        });
      });
      const n0 = s0.teams, n1 = s1.teams;
      const idle = Object.keys(n0).filter(t => t in n1 && !(t in acts) && n0[t] > 0.5).map(t => n1[t] / n0[t]);
      if (idle.length < 3) continue;
      const drift = median(idle);
      Object.entries(acts).forEach(([t, a]) => {
        if (a.dealer || !a.team.length || !(t in n0) || !(t in n1)) return;
        const jump = n1[t] - drift * n0[t];
        if (Math.abs(jump) >= minJump) out.push({team: t, sign: jump > 0 ? 1 : -1, trades: a.team, t0: s0.tick, t1: s1.tick, jump: Math.round(jump * 1000) / 1000});
      });
    }
    return out;
  }
  function median(a) { const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; }

  // Posterior por equipo a partir de filas de evidencia y saltos. known = {equipo: {SET: mult}} fija un equipo.
  function estimate(rows, jumps, known = {}) {
    const ll = {}, n = {};
    const acc = t => ll[t] || (ll[t] = new Float64Array(PERMS.length));
    const cnt = (t, k) => { (n[t] || (n[t] = {}))[k] = ((n[t] || {})[k] || 0) + 1; };
    rows.forEach(r => {
      const j = SETS.indexOf(r.set); if (j < 0) return;
      const w = WEIGHT[r.kind], f = r.kind === "trade_buy" || r.kind === "dealer_buy" || r.kind === "bid" ? likBuy : likSell;
      const perM = {}; MULTS.forEach(m => perM[m] = w * Math.log(f(r.book, r.price, m)));
      const a = acc(r.team);
      for (let i = 0; i < PERMS.length; i++) a[i] += perM[PERMS[i][j]];
      cnt(r.team, r.kind);
    });
    jumps.forEach(jmp => {
      const a = acc(jmp.team), scale = tau(jmp.trades.reduce((s, t) => s + t.price, 0));
      for (let i = 0; i < PERMS.length; i++) {
        let gain = 0;
        jmp.trades.forEach(t => {
          const j = SETS.indexOf(t.set); if (j < 0) return;
          const v = t.book * PERMS[i][j];
          gain += t.side === "buy" ? v - t.price : t.price - v * (1 - 0.75 * P_REPEAT);
        });
        a[i] += WEIGHT.score * Math.log(EPS + (1 - 2 * EPS) * sig(jmp.sign * gain / scale));
      }
      cnt(jmp.team, "score");
    });
    const out = {};
    Object.keys(ll).forEach(t => out[t] = posterior(t, ll[t], n[t] || {}));
    Object.entries(known).forEach(([t, aff]) => {
      const exact = PERMS.map(perm => SETS.every((s, j) => Math.abs((aff[s] || 0) - perm[j]) < 1e-9) ? 0 : -1e9);
      out[t] = posterior(t, exact, {known: 1});
    });
    return out;
  }
  function posterior(team, logp, n) {
    const m = Math.max(...logp), w = Array.from(logp, x => Math.exp(x - m)), z = w.reduce((s, x) => s + x, 0);
    const p = w.map(x => x / z);
    const marg = {};
    SETS.forEach((s, j) => { const o = {}; MULTS.forEach(mm => o[mm] = 0); PERMS.forEach((perm, i) => o[perm[j]] += p[i]); marg[s] = o; });
    let best = 0; p.forEach((x, i) => { if (x > p[best]) best = i; });
    const expected = {}, p16 = {};
    SETS.forEach(s => { expected[s] = MULTS.reduce((acc, mm) => acc + mm * marg[s][mm], 0); p16[s] = marg[s][1.6]; });
    const bits = -p.reduce((s, x) => s + (x > 0 ? x * Math.log2(x) : 0), 0);
    const map = {}; SETS.forEach((s, j) => map[s] = PERMS[best][j]);
    return {team, marg, expected, p16, map, pMap: p[best], bits, n, total: Object.values(n).reduce((s, x) => s + x, 0),
      known: !!n.known, info: 1 - bits / BITS0};
  }

  return {MULTS, SETS, BOOK, PERMS, WEIGHT, BITS0, evidence, addQuote, quoteKey, scoreJumps, estimate, rarityOfRef};
})();
if (typeof module !== "undefined") module.exports = T18Affinity;
