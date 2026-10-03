const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const E = require('./evidence.js');

test('absence from El Rastro does not prove closing or settlement', () => {
  assert.equal(E.offerState({id:1,venue:'rastro'},[],new Set(),4),'sin confirmar');
  assert.equal(E.offerState({id:1,venue:'v02'},[{id:1,status:'open'}],new Set(),4),'sin confirmar');
});
test('only explicit cancellation, expiry or live Rastro listing changes status', () => {
  const o={id:1,venue:'rastro',expires_tick:9};
  assert.equal(E.offerState(o,[{id:1,status:'open'}],new Set(),4),'abierta');
  assert.equal(E.offerState(o,[],new Set([1]),4),'cancelada');
  assert.equal(E.offerState(o,[],new Set(),10),'vencida');
});
test('cancel events support numeric offer ids and objects', () => {
  assert.equal(E.cancelledId({payload:{offer:123}}),123);
  assert.equal(E.cancelledId({payload:{offer:{id:456}}}),456);
  assert.equal(E.cancelledId({payload:{offer_id:789}}),789);
});
test('dealer cap never applies a single card limit to a bundle or team trade', () => {
  const c={kind:'card',ref:'RET-01'};
  assert.equal(E.dealerCap({kind:'trade',persona:'abuela',items:[c]}, {'RET-01':11}),11);
  assert.equal(E.dealerCap({kind:'trade',persona:'abuela',items:[c,c]}, {'RET-01':11}),null);
  assert.equal(E.dealerCap({kind:'trade',items:[c]}, {'RET-01':11}),null);
});
test('hourly delta waits for a full hour and stays within round', () => {
  const now=7200000;
  assert.equal(E.hourBaseline([{ts:now-600000,round:2}],now,2),null);
  assert.equal(E.hourBaseline([{ts:0,round:1}],now,2),null);
  const h={ts:now-3600000,round:2};
  assert.equal(E.hourBaseline([h,{ts:now,round:2}],now,2),h);
});
test('browser export contains selected public data, not settings, messages or keys', () => {
  const data=E.exportPublic({lb:{snapshot_tick:4,teams:[{team:'t18',rank:1,private:'hidden'}]},clock:{tick:5,private:'hidden'}},
    {settings:{cash:116,have:'LAT-01',key:'hidden'},feed:{1:{id:1,tick:4,type:'settlement',payload:{kind:'trade',price:9,key:'hidden',items:[{kind:'card',ref:'RET-01',key:'hidden'}]}},2:{id:2,tick:5,type:'thread.message',payload:{text:'hidden'}}}},
    {sets:[{id:'RET',cards:[{id:'RET-01',rarity:'common',flavour:'hidden'}]}]},'2026-10-03T09:00:00Z');
  assert.equal(data.schema,'t18.analyst.public.v1');
  assert.equal(data.feed.events.length,1);
  assert.equal(data.coverage.complete,false);
  assert.equal(JSON.stringify(data).includes('hidden'),false);
  assert.equal('settings' in data,false);
});
test('export requires actual observed clock, classification and catalogue', () => {
  assert.throws(()=>E.exportPublic({}, {}, {sets:[]}, 'now'));
});
test('generated limits exactly match repository plan', () => {
  const plan=fs.readFileSync(path.join(__dirname,'../config/plan.json'),'utf8').replace(/\r\n/g,'\n'); // git autocrlf checkouts
  const text=fs.readFileSync(path.join(__dirname,'plan-public.js'),'utf8');
  const compiled=JSON.parse(text.match(/Object.freeze\((.*)\);/)[1]);
  assert.deepEqual(compiled.dealer_max,JSON.parse(plan).dealer_max);
  assert.equal(compiled.sha256,crypto.createHash('sha256').update(plan).digest('hex'));
});
test('static bundle includes both roles and companion scripts', () => {
  const page=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
  assert.match(page,/href="jurado.html"/);
  assert.match(page,/src="evidence.js"/);
  assert.match(fs.readFileSync(path.join(__dirname,'jurado.html'),'utf8'),/href="index.html"/);
});
