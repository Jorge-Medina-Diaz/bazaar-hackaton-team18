/* Pure public-data bridge. Never exports settings, cash inputs, holdings, text or credentials. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.T18Evidence = factory();
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';
  const pick = (value, fields) => Object.fromEntries(fields.filter(k => value && value[k] !== undefined).map(k => [k, value[k]]));
  const card = a => pick(a, ['id', 'kind', 'ref', 'rarity', 'set', 'frm', 'to']);
  const side = s => ({cash: s?.cash || 0, assets: (s?.assets || []).map(card), types: (s?.types || []).filter(t => typeof t === 'string' && /^card:(LAV|MAL|LAT|SAL|RET|CHA)-\d{2}$/.test(t))});
  function publicEvent(e) {
    const base = pick(e, ['id', 'tick', 'type']);
    if (!Number.isInteger(base.id) || !Number.isInteger(base.tick)) return null;
    const p = e.payload || {};
    if (e.type === 'settlement' && p.kind === 'trade') {
      return {...base, payload: {...pick(p, ['kind', 'price', 'persona', 'parties']), items: (p.items || []).map(card)}};
    }
    if (e.type === 'offer.listed' && p.offer && typeof p.offer === 'object') {
      const o = p.offer;
      return {...base, payload: {offer: {...pick(o, ['id', 'maker', 'venue', 'thread', 'status', 'expires_tick', 'created_tick']), give: side(o.give), want: side(o.want)}}};
    }
    return null;
  }
  function exportPublic(live, state, catalog, capturedAt) {
    if (!live.lb || !live.clock || !Array.isArray(catalog?.sets)) throw new Error('Falta clasificación, reloj o catálogo');
    const feed = Object.values(state.feed || {}).map(publicEvent).filter(Boolean).sort((a,b) => a.id-b.id);
    return {schema: 't18.analyst.public.v1', captured_at: capturedAt,
      leaderboard: {...pick(live.lb, ['snapshot_tick', 'tick', 'round']), teams: (live.lb.teams || []).map(t => pick(t, ['team','rank','score','negotiating','market','pages_complete','album_filled','album_slots']))},
      clock: pick(live.clock, ['tick','paused','doors']), feed: {events: feed},
      catalog: {sets: catalog.sets.map(s => ({id:s.id, cards:(s.cards||[]).map(c=>pick(c,['id','rarity']))}))},
      coverage: {selection: 'browser_retained_settlements_and_bids', complete: false, events: feed.length,
        tick_range: feed.length ? [Math.min(...feed.map(e=>e.tick)),Math.max(...feed.map(e=>e.tick))] : []}};
  }
  function cancelledId(e) {
    const p = e?.payload || {}, o = p.offer;
    return Number.isInteger(o) ? o : o?.id ?? p.offer_id ?? null;
  }
  function offerState(o, board, cancellations, tick) {
    if (cancellations.has(o.id)) return 'cancelada';
    if (Number.isInteger(tick) && Number.isInteger(o.expires_tick) && tick > o.expires_tick) return 'vencida';
    if (o.venue === 'rastro' && board.some(b=>b.id===o.id && b.status==='open')) return 'abierta';
    return 'sin confirmar'; // Absence in El Rastro cannot prove a fill or the state in another venue.
  }
  function dealerCap(payload, caps) {
    const items = payload.items || [];
    return payload.persona && payload.kind === 'trade' && items.length === 1 && items[0].kind === 'card'
      ? caps[items[0].ref] ?? null : null;
  }
  function hourBaseline(history, now, round) {
    return history.filter(h=>h.round===round && h.ts<=now-3600000).at(-1) || null;
  }
  return {exportPublic, publicEvent, cancelledId, offerState, dealerCap, hourBaseline};
});
