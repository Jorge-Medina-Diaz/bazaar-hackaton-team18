/* Caja para CHA: cálculo puro (sin E/S ni DOM), en vivo desde datos públicos y el equipo.json del navegador.
   - Caja: equipo.json (pestaña Equipo) + tratos y regalos públicos de t18 después de su tick; si no, manual.
   - Subvención: grant_all pendientes del calendario. Precios: mediana de ventas de dealer a equipos en el feed,
     CHA si ya hay, si no RET, si no los costes medidos el sábado. Faltan: página CHA menos lo que tenemos.
   - Sobres (V-11): cada hueco saca de los sets publicados el domingo (CHA incluido), ponderado por tirada − acuñadas;
     una rareza agotada da la de abajo (como agent/valuation.py). Coste esperado = media sobre lo que pueden traer
     los sobres que abramos el domingo (independencia entre cartas; 2^n subconjuntos, n ≤ 10).
   El cierre (J12) compra a un equipo la última carta que falte; las demás, a dealer. Nada de esto decide cifras
   del bot: es una vista del analista. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.T18ChaCash = factory();
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';
  const US = 't18';
  const RAR = ['common', 'uncommon', 'rare', 'epic', 'legendary'];          // ascendente: un hueco cae a la izquierda
  const DEFAULT_PRICE = {common: 9.5, uncommon: 22, rare: 86};               // RET el sábado (docs/analista.md §2)
  const median = a => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
  const num = v => (v === '' || v == null || !isFinite(Number(v))) ? null : Number(v);
  const packId = k => typeof k === 'string' ? k.replace(/^pack:/, '') : (k && (k.ref || k.id)) ? packId(k.ref || k.id) : null;

  /** Sets que el domingo están publicados: los ya publicados más los que salen el domingo. */
  function sundaySets(catalog) {
    return new Set((catalog.sets || []).filter(s => s.released || /^sun/.test(String(s.release || ''))).map(s => s.id));
  }

  /** {rarity: [[ref, q]]} con la regla de la rareza agotada; q suma 1 por rareza pedida. */
  function slotDists(catalog, sets) {
    const cards = (catalog.sets || []).filter(s => sets.has(s.id)).flatMap(s => s.cards || []);
    const own = {};
    for (const r of RAR) {
      const cs = cards.filter(c => c.rarity === r).map(c => [c.id, Math.max(0, (c.print_run || 0) - (c.minted || 0))]).filter(x => x[1] > 0);
      const W = cs.reduce((a, x) => a + x[1], 0);
      own[r] = W > 0 ? cs.map(([id, w]) => [id, w / W]) : null;
    }
    const out = {};
    for (const r of RAR) { for (let i = RAR.indexOf(r); i >= 0; i--) if (own[RAR[i]]) { out[r] = own[RAR[i]]; break; } out[r] = out[r] || []; }
    return out;
  }

  /** Probabilidad de que un sobre traiga al menos una vez cada ref, y nº esperado de cartas de `set`. */
  function packOdds(pack, dists, set) {
    const miss = {}; let expSet = 0, noSet = 1;
    for (const slot of pack.slots || []) {
      const p = {};
      for (const [r, q] of Object.entries(slot)) for (const [ref, w] of dists[r] || []) p[ref] = (p[ref] || 0) + q * w;
      let inSet = 0;
      for (const [ref, pr] of Object.entries(p)) { miss[ref] = (miss[ref] ?? 1) * (1 - pr); if (ref.startsWith(set + '-')) inSet += pr; }
      expSet += inSet; noSet *= 1 - inSet;
    }
    const hit = Object.fromEntries(Object.entries(miss).map(([k, v]) => [k, 1 - v]));
    return {hit, expSet, anySet: 1 - noSet};
  }

  /** Cartas de t18 = equipo.json + tratos y regalos públicos posteriores a su tick. */
  function holdings(me, events) {
    const cnt = {}; let cash = me && num(me.cash) != null ? Number(me.cash) : null, adj = 0;
    const since = me ? me.tick : null;
    if (me) (me.assets || []).forEach(a => { if (a.ref) cnt[a.ref] = (cnt[a.ref] || 0) + 1; });
    const packs = me ? (me.packTypes || Array(me.packs || 0).fill(null)).map(packId) : [];
    for (const e of events || []) {
      if (since != null && !(e.tick > since)) continue;
      const p = e.payload || {};
      if (e.type === 'settlement' && (p.parties || []).includes(US)) {
        const cards = (p.items || []).filter(i => i.kind === 'card');
        const buy = cards.some(i => i.to === US), sell = cards.some(i => i.frm === US);
        cards.forEach(i => { const d = i.to === US ? 1 : i.frm === US ? -1 : 0; cnt[i.ref] = Math.max(0, (cnt[i.ref] || 0) + d); });
        if (cash != null) cash += buy && !sell ? -(p.price || 0) : sell && !buy ? (p.price || 0) - (p.fee || 0) : 0;
        adj++;
      } else if (e.type === 'gift.given' && p.team === US) {
        (p.cards || []).forEach(r => cnt[r] = (cnt[r] || 0) + 1);
        (p.packs || []).forEach(k => packs.push(packId(k)));
        if (cash != null) cash += p.cash || 0;
        adj++;
      } else if (e.type === 'pack.opened' && p.team === US) {
        const i = packs.findIndex(k => k === packId(p.pack) || k == null); if (i >= 0) packs.splice(i, 1);
      }
    }
    return {cnt, cash, adj, packs, known: !!me};
  }

  /** Precio por rareza: ventas de dealer a equipos (CHA → RET), con la tabla por dealer de todos los sets. */
  function prices(events, set = 'CHA', fallbackSet = 'RET') {
    const obs = [];
    for (const e of events || []) {
      if (e.type !== 'settlement') continue;
      const p = e.payload || {}; if (!p.persona) continue;
      const cards = (p.items || []).filter(i => i.kind === 'card');
      if (cards.length !== 1 || cards[0].frm !== p.persona || !num(p.price)) continue;
      const c = cards[0];
      obs.push({tick: e.tick, dealer: p.persona, set: c.set || String(c.ref).split('-')[0], rarity: c.rarity, price: Number(p.price), to: c.to});
    }
    const out = {};
    for (const r of ['common', 'uncommon', 'rare']) {
      const of = s => obs.filter(o => o.rarity === r && o.set === s).map(o => o.price);
      const a = of(set), b = of(fallbackSet);
      const byDealer = {};
      obs.filter(o => o.rarity === r).forEach(o => (byDealer[o.dealer] = byDealer[o.dealer] || []).push(o.price));
      out[r] = {
        value: a.length ? median(a) : b.length ? median(b) : DEFAULT_PRICE[r],
        src: a.length ? `${set} · ${a.length} ventas de dealer` : b.length ? `${fallbackSet} · ${b.length} ventas de dealer` : 'sábado (RET medido)',
        n: a.length || b.length,
        dealers: Object.entries(byDealer).map(([d, v]) => ({dealer: d, n: v.length, median: median(v), min: Math.min(...v)})).sort((x, y) => x.median - y.median),
      };
    }
    return out;
  }

  /** Coste de comprar lo que falta: dealer para todas menos la última (la de menor rareza), que va al cierre. */
  function costOf(missing, price, closer) {
    if (!missing.length) return 0;
    const order = [...missing].sort((a, b) => RAR.indexOf(b.rarity) - RAR.indexOf(a.rarity));
    return order.slice(0, -1).reduce((s, c) => s + (price[c.rarity] ?? 0), 0) + closer;
  }

  /** Coste esperado si cada carta llega de los sobres con prob. p (independientes). */
  function expectedCost(missing, hit, price, closer) {
    const n = missing.length; let ev = 0, pAll = 1;
    for (let m = 0; m < 1 << n; m++) {                         // bit 1 = la carta sale de un sobre
      let pr = 1; const rest = [];
      for (let i = 0; i < n; i++) { const p = hit[missing[i].ref] || 0; if (m >> i & 1) pr *= p; else { pr *= 1 - p; rest.push(missing[i]); } }
      if (pr) ev += pr * costOf(rest, price, closer);
    }
    missing.forEach(c => pAll *= 1 - (hit[c.ref] || 0));
    return {ev, pNone: pAll};
  }

  /**
   * in: {catalog, me, events, schedule, nowHours, caps, ov: {cash, grant, extra, pr, pu, pc, pk, res, packs}}
   * ov: valores manuales; null/'' = automático. ov.packs = sobres de barrio extra que se abrirán el domingo.
   */
  function compute(inp) {
    const {catalog, me, events = [], schedule, caps = {}} = inp, ov = inp.ov || {}, set = 'CHA';
    const H = holdings(me, events);
    const pick = (k, auto, src) => num(ov[k]) != null ? {value: num(ov[k]), src: 'manual', auto} : {value: auto, src, auto};
    const grants = ((schedule && schedule.upcoming) || []).filter(e => e.action === 'grant_all' && (inp.nowHours == null || e.at_hours > inp.nowHours));
    const grantAuto = grants.reduce((a, e) => a + ((e.params && e.params.cash) || 0), 0);
    const P = prices(events, set);
    const f = {
      cash: pick('cash', H.cash != null ? Math.round(H.cash) : 116, H.cash != null ? `equipo.json t${me.tick}${H.adj ? ` + ${H.adj} movimientos del feed` : ''}` : 'sin equipo.json: último dato (116)'),
      grant: pick('grant', grantAuto, grants.length ? 'calendario (grant_all)' : 'calendario: nada pendiente'),
      extra: pick('extra', 0, 'ventas previstas, a mano'),
      pr: pick('pr', P.rare.value, P.rare.src), pu: pick('pu', P.uncommon.value, P.uncommon.src), pc: pick('pc', P.common.value, P.common.src),
      pk: pick('pk', 72, 'plan J12'), res: pick('res', 10, 'Gate (cash_free)'),
    };
    const price = {common: f.pc.value, uncommon: f.pu.value, rare: f.pr.value};
    const cset = catalog && (catalog.sets || []).find(s => s.id === set);
    const page = cset ? cset.cards.filter(c => c.page) : [];
    const missing = page.filter(c => !(H.known && H.cnt[c.id] > 0)).map(c => ({ref: c.id, rarity: c.rarity}));
    const count = r => missing.filter(c => c.rarity === r).length;

    // sobres que abriremos el domingo: los del fichero/regalos + los indicados a mano (de barrio)
    const extraPacks = Math.max(0, Math.round(num(ov.packs) || 0));
    const packs = [...H.packs.map(k => k || 'sobre_barrio'), ...Array(extraPacks).fill('sobre_barrio')];
    let hit = {}, packRows = [], dists = null;
    if (catalog) {
      dists = slotDists(catalog, sundaySets(catalog));
      const odds = Object.fromEntries((catalog.packs || []).map(p => [p.id, packOdds(p, dists, set)]));
      const miss = {};
      packs.forEach(k => { const o = odds[k]; if (o) Object.entries(o.hit).forEach(([r, p]) => miss[r] = (miss[r] ?? 1) * (1 - p)); });
      hit = Object.fromEntries(Object.entries(miss).map(([r, v]) => [r, 1 - v]));
      packRows = (catalog.packs || []).map(p => {
        const o = odds[p.id], one = expectedCost(missing, o.hit, price, f.pk.value);
        return {id: p.id, name: p.name, expSet: o.expSet, anySet: o.anySet,
          pMissing: 1 - missing.reduce((a, c) => a * (1 - (o.hit[c.ref] || 0)), 1),
          saving: costOf(missing, price, f.pk.value) - one.ev};
      });
    }
    const base = costOf(missing, price, f.pk.value);
    const ex = expectedCost(missing, hit, price, f.pk.value);
    const cash = f.cash.value + f.grant.value + f.extra.value;
    const shareCHA = {};
    if (catalog) {
      const sun = sundaySets(catalog), cards = (catalog.sets || []).filter(s => sun.has(s.id)).flatMap(s => s.cards.map(c => ({...c, set: s.id})));
      for (const r of RAR) {
        const left = c => Math.max(0, c.print_run - c.minted), all = cards.filter(c => c.rarity === r), W = all.reduce((a, c) => a + left(c), 0);
        const w = all.filter(c => c.set === set).reduce((a, c) => a + left(c), 0);
        shareCHA[r] = {left: W, cha: w, share: W ? w / W : 0, perCard: W && all.some(c => c.set === set) ? w / all.filter(c => c.set === set).length / W : 0};
      }
    }
    const over = missing.filter(c => caps[c.ref] != null && price[c.rarity] > caps[c.ref]).map(c => c.ref);
    return {f, missing, count: {rare: count('rare'), uncommon: count('uncommon'), common: count('common')}, known: H.known,
      packs, hit, base, expected: ex.ev, pNone: ex.pNone, need: base + f.res.value, needExp: ex.ev + f.res.value, cash,
      gap: base + f.res.value - cash, gapExp: ex.ev + f.res.value - cash, prices: P, packRows, shareCHA, over, price};
  }

  return {compute, holdings, prices, slotDists, packOdds, costOf, expectedCost, sundaySets, DEFAULT_PRICE};
});
