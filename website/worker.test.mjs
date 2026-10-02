import assert from "node:assert/strict";
import { test } from "node:test";
import { createWorker, decryptSession, encryptSession } from "./worker.mjs";

const env = { SESSION_SECRET: "fixture-secret-for-session-tests-only-123456789" };
const origin = "https://panel.example";
const worker = createWorker("<html lang=es><h1>Mesa de cartas</h1></html>");
function request(path, options = {}) { return new Request(origin + path, options); }
async function fixture(t) {
  const originalFetch = globalThis.fetch;
  const originalCaches = globalThis.caches;
  const stored = new Map();
  const reads = [];
  const api = { cash: 391, offersError: false };
  globalThis.caches = { default: { async match(req) { return stored.get(req.url)?.clone(); }, async put(req, response) { stored.set(req.url, response.clone()); } } };
  globalThis.fetch = async (url, options) => {
    assert.equal(options.method, "GET");
    assert.equal(options.headers["X-Team-Key"], "tk-fixture-key");
    reads.push(new URL(url).pathname);
    const route = new URL(url).pathname;
    if (route === "/api/me") return Response.json({ id: "t18", name: "Equipo 18", cash: api.cash, assets: [{ id: 100, ref: "SAL-02", kind: "card", your_value: 11 }], starter_broker_key: "NEVER_EXPOSE" });
    if (route === "/api/clock") return Response.json({ tick: 45 });
    if (route === "/api/me/offers") return api.offersError ? new Response("rate_limited", { status: 429 }) : Response.json({ offers: [{ id: 480, status: "queued", maker: "abuela", give: { assets: [100] }, want: { cash: 9 } }] });
    if (route === "/api/me/threads") return Response.json({ threads: [{ id: 68, status: "deal", with: "abuela" }] });
    assert.fail("Unexpected API route: " + route);
  };
  t.after(() => { globalThis.fetch = originalFetch; globalThis.caches = originalCaches; });
  const token = await encryptSession("tk-fixture-key", env.SESSION_SECRET);
  const cookie = "__Host-bazaar-session=" + token;
  return { reads, stored, cookie, api };
}

test("public page contains no private data; API requires authentication", async () => {
  const page = await worker.fetch(request("/"), env);
  assert.equal(page.status, 200);
  assert.match(page.headers.get("Content-Security-Policy"), /connect-src 'self'/);
  assert.equal((await worker.fetch(request("/api/state"), env)).status, 401);
  assert.equal((await worker.fetch(request("/__private-state/anything"), env)).status, 404);
});
test("session encrypts the key; tampering and expired sessions are refused", async t => {
  const token = await encryptSession("tk-fixture-key", env.SESSION_SECRET);
  assert.ok(!token.includes("tk-fixture-key"));
  assert.equal(await decryptSession(token, env.SESSION_SECRET), "tk-fixture-key");
  assert.equal(await decryptSession(token + "tamper", env.SESSION_SECRET), null);
  assert.equal(await decryptSession(token, env.SESSION_SECRET + "other"), null);
  const originalNow = Date.now;
  Date.now = () => originalNow() + 9 * 3600_000;
  t.after(() => { Date.now = originalNow; });
  assert.equal(await decryptSession(token, env.SESSION_SECRET), null);
});
test("login validates the key and returns only a protected encrypted cookie", async t => {
  await fixture(t);
  const response = await worker.fetch(request("/api/login", { method: "POST", headers: { Origin: origin, "Content-Type": "application/json" }, body: JSON.stringify({ key: "tk-fixture-key" }) }), env);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { ok: true });
  const cookie = response.headers.get("Set-Cookie");
  assert.ok(!cookie.includes("tk-fixture-key"));
  assert.match(cookie, /Secure; HttpOnly; SameSite=Strict/);
  const forbidden = await worker.fetch(request("/api/login", { method: "POST", headers: { Origin: "https://other.example" }, body: "{}" }), env);
  assert.equal(forbidden.status, 403);
});
test("authenticated reads verify four sources, exclude broker keys and reuse the five-second snapshot", async t => {
  const f = await fixture(t);
  let response = await worker.fetch(request("/api/state", { headers: { Cookie: f.cookie } }), env);
  const state = await response.json();
  assert.equal(state.cash, 391);
  assert.equal(state.assets[0].ref, "SAL-02");
  assert.equal(state.poll_seconds, 5);
  assert.ok(!JSON.stringify(state).includes("NEVER_EXPOSE"));
  assert.ok(Object.values(state.checks).every(c => c.ok));
  assert.equal(f.reads.length, 4);
  await worker.fetch(request("/api/state", { headers: { Cookie: f.cookie } }), env);
  assert.equal(f.reads.length, 4);
  const originalNow = Date.now;
  Date.now = () => originalNow() + 5100;
  t.after(() => { Date.now = originalNow; });
  f.api.cash = 382;
  f.api.offersError = true;
  response = await worker.fetch(request("/api/state", { headers: { Cookie: f.cookie } }), env);
  const updated = await response.json();
  assert.equal(f.reads.length, 8);
  assert.equal(updated.cash, 382);
  assert.equal(updated.checks.ofertas.ok, false);
  assert.equal(updated.checks.ofertas.error, "rate_limited");
  assert.equal(updated.offers[0].id, 480);
});
test("logout clears the cookie; no game mutation routes exist", async () => {
  const response = await worker.fetch(request("/api/logout", { method: "POST", headers: { Origin: origin } }), env);
  assert.match(response.headers.get("Set-Cookie"), /Max-Age=0/);
  assert.equal((await worker.fetch(request("/api/offers/480/accept", { method: "POST", headers: { Origin: origin } }), env)).status, 404);
});
