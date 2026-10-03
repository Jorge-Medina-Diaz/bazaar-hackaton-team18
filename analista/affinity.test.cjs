// node --test analista/affinity.test.cjs · el puerto JS reproduce agent/affinity.py sobre la semilla exportada.
"use strict";
const test = require("node:test"), assert = require("node:assert");
const A = require("./assets/affinity.js");
require("./assets/affinity-seed.js");
const S = globalThis.T18AffinitySeed;

test("720 permutaciones distintas", () => {
  assert.strictEqual(A.PERMS.length, 720);
  assert.strictEqual(new Set(A.PERMS.map(p => p.join())).size, 720);
});

test("misma posterior que Python en el último corte de la semilla", () => {
  const post = A.estimate([...S.rows, ...S.quotes], S.jumps);
  const last = S.history[S.history.length - 1];
  assert.strictEqual(last.tick, S.tick);
  for (const [t, ref] of Object.entries(last.teams)) {
    assert.ok(post[t], t);
    for (const s of A.SETS) {
      assert.ok(Math.abs(post[t].expected[s] - ref.e[s]) < 2e-3, `${t} ${s} E ${post[t].expected[s]} vs ${ref.e[s]}`);
      assert.ok(Math.abs(post[t].p16[s] - ref.p16[s]) < 2e-3, `${t} ${s} p16`);
    }
    assert.ok(Math.abs(post[t].bits - ref.bits) < 0.02, `${t} bits`);
    assert.strictEqual(post[t].total, ref.n, `${t} n`);
  }
});

test("un equipo conocido queda fijado", () => {
  const aff = {LAV: 0.7, MAL: 0.5, LAT: 0.9, SAL: 1.1, RET: 1.3, CHA: 1.6};
  const p = A.estimate([], [], {t18: aff}).t18;
  assert.deepStrictEqual(p.map, aff);
  assert.ok(p.bits < 1e-6);
});

test("evidencia y saltos desde eventos del feed", () => {
  const items = [{kind: "card", ref: "SAL-09", set: "SAL", rarity: "rare", frm: "t01", to: "t02"}];
  const ev = [
    {id: 1, tick: 10, type: "settlement", payload: {kind: "trade", price: 90, items, parties: ["t01", "t02"]}},
    {id: 2, tick: 11, type: "offer.listed", payload: {offer: {maker: "t03", give: {cash: 40}, want: {types: ["card:CHA-07"]}}}},
    {id: 3, tick: 12, type: "offer.listed", payload: {offer: {maker: "t03", give: {cash: 50}, want: {types: ["card:CHA-07"]}}}},
  ];
  const {rows, quotes} = A.evidence(ev);
  assert.deepStrictEqual(rows.map(r => r.team + ":" + r.kind), ["t02:trade_buy", "t01:trade_sell"]);
  const q = Object.values(quotes);
  assert.strictEqual(q.length, 1);
  assert.strictEqual(q[0].price, 50);
  assert.strictEqual(q[0].book, 25);
  const teams = n => ({t01: 10, t02: n, t04: 10, t05: 10, t06: 10});
  const jumps = A.scoreJumps([{tick: 5, round: 1, teams: teams(10)}, {tick: 15, round: 1, teams: teams(11)}], ev);
  assert.deepStrictEqual(jumps.map(j => j.team + ":" + j.sign), ["t02:1"]);  // t01 no se movió más que la deriva
});
