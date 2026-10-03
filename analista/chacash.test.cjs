const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('./assets/chacash.js');

const card = (id, rarity, minted = 0, page = true) => ({id, rarity, print_run: {common: 300, uncommon: 90, rare: 30, epic: 9, legendary: 3}[rarity], minted, page});
const setOf = (id, released, release, minted = 0) => ({id, released, release, cards: [
  ...[1, 2, 3, 4, 5].map(i => card(`${id}-0${i}`, 'common', minted)), ...[6, 7, 8].map(i => card(`${id}-0${i}`, 'uncommon', minted)),
  card(`${id}-09`, 'rare', minted), card(`${id}-10`, 'rare', minted), card(`${id}-11`, 'epic', 0, false), card(`${id}-12`, 'legendary', 0, false)]});
const CAT = {sets: [setOf('RET', true, 'sat+0h'), setOf('CHA', false, 'sun+0h')],
  packs: [{id: 'sobre_barrio', name: 'Barrio', slots: [{common: 1}, {common: 1}, {common: 0.75, uncommon: 0.25}]}]};
const SCHED = {upcoming: [{at_hours: 16.7, action: 'grant_all', params: {cash: 150}}]};
const sale = (tick, persona, ref, rarity, price, to = 't05') => ({tick, type: 'settlement', payload: {persona, price, parties: [persona, to], items: [{kind: 'card', ref, rarity, set: ref.split('-')[0], frm: persona, to}]}});

test('sin datos reproduce el plan del sábado: 348 P + reserva frente a 116 + 150', () => {
  const r = C.compute({catalog: CAT, schedule: SCHED, nowHours: 8});
  assert.equal(r.base, 2 * 86 + 3 * 22 + 4 * 9.5 + 72);
  assert.equal(r.cash, 266);
  assert.equal(r.gap, 348 + 10 - 266);
  assert.equal(r.expected, r.base);                      // sin sobres, el esperado es el coste
});

test('la subvención ya cobrada no se suma dos veces', () => {
  assert.equal(C.compute({catalog: CAT, schedule: SCHED, nowHours: 17}).f.grant.value, 0);
});

test('precios: CHA antes que RET, y los manuales mandan', () => {
  const ev = [sale(1, 'chato', 'RET-09', 'rare', 90), sale(2, 'chato', 'CHA-09', 'rare', 80), sale(3, 'picaros', 'SAL-10', 'rare', 55)];
  const r = C.compute({catalog: CAT, events: ev, schedule: SCHED});
  assert.equal(r.f.pr.value, 80);
  assert.match(r.f.pr.src, /^CHA/);
  assert.equal(r.prices.rare.dealers[0].dealer, 'picaros');
  assert.equal(C.compute({catalog: CAT, events: ev, ov: {pr: '70'}}).f.pr.value, 70);
});

test('caja y cartas: equipo.json + feed posterior; las que tenemos no se compran', () => {
  const me = {cash: 100, tick: 10, assets: [{ref: 'CHA-01'}, {ref: 'CHA-09'}], packTypes: []};
  const ev = [sale(5, 'abuela', 'CHA-02', 'common', 9, 't18'), sale(11, 'abuela', 'CHA-02', 'common', 9, 't18'),
    {tick: 12, type: 'gift.given', payload: {team: 't18', cash: 5, packs: ['sobre_barrio'], cards: []}}];
  const r = C.compute({catalog: CAT, me, events: ev, schedule: SCHED, nowHours: 8});
  assert.equal(r.f.cash.value, 100 - 9 + 5);               // el trato de t5 ya está en el fichero
  assert.deepEqual(r.count, {rare: 1, uncommon: 3, common: 3});
  assert.deepEqual(r.packs, ['sobre_barrio']);
  assert.ok(r.expected < r.base && r.pNone < 1);
});

test('sobres: CHA con 0 acuñadas pesa más en cada hueco, y una rareza agotada cae a la de abajo', () => {
  const cat = {...CAT, sets: [setOf('RET', true, 'sat+0h', 100), setOf('CHA', false, 'sun+0h')]};
  const d = C.slotDists(cat, C.sundaySets(cat));
  const cha = d.common.filter(([r]) => r.startsWith('CHA')).reduce((a, x) => a + x[1], 0);
  assert.ok(Math.abs(cha - 1500 / (1500 + 1000)) < 1e-9);
  const dry = {sets: [{id: 'X', released: true, cards: [card('X-01', 'common'), {...card('X-09', 'rare'), minted: 30}]}]};
  assert.deepEqual(C.slotDists(dry, new Set(['X'])).rare, [['X-01', 1]]);
});

test('coste esperado: una carta segura del sobre deja de comprarse; si es la última, se ahorra el cierre', () => {
  const miss = [{ref: 'A', rarity: 'rare'}, {ref: 'B', rarity: 'common'}], price = {rare: 86, common: 9.5};
  assert.equal(C.costOf(miss, price, 72), 86 + 72);
  assert.equal(C.expectedCost(miss, {B: 1}, price, 72).ev, 72);
  assert.equal(C.expectedCost(miss, {A: 1, B: 1}, price, 72).ev, 0);
  assert.ok(Math.abs(C.expectedCost(miss, {B: 0.5}, price, 72).ev - (0.5 * 158 + 0.5 * 72)) < 1e-9);
});
