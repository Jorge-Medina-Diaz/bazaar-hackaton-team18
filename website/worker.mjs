// Hosted read-only panel. Game credentials exist only in an encrypted session cookie.
const API = "https://bazaar.causaprima.ai";
const INTERVAL = 5000;
const encoder = new TextEncoder();
const decoder = new TextDecoder();
const COOKIE = "__Host-bazaar-session";
const fields = ["inventario y saldo", "reloj", "ofertas", "conversaciones"];

function json(value, status = 200, extra = {}) {
  return new Response(JSON.stringify(value), { status, headers: {
    "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff", ...extra,
  } });
}
function encode(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes))).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}
function decode(value) {
  return Uint8Array.from(atob(value.replaceAll("-", "+").replaceAll("_", "/")), c => c.charCodeAt(0));
}
async function secretKey(secret) {
  if (!secret || secret.length < 32) throw new Error("configuration_required");
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(secret));
  return crypto.subtle.importKey("raw", digest, "AES-GCM", false, ["encrypt", "decrypt"]);
}
export async function encryptSession(key, secret) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const data = encoder.encode(JSON.stringify({ key, expires: Date.now() + 8 * 3600_000 }));
  const encrypted = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await secretKey(secret), data);
  return encode(iv) + "." + encode(encrypted);
}
export async function decryptSession(token, secret) {
  try {
    if (!token || token.length > 1600) return null;
    const [iv, value] = token.split(".");
    const data = await crypto.subtle.decrypt({ name: "AES-GCM", iv: decode(iv) }, await secretKey(secret), decode(value));
    const session = JSON.parse(decoder.decode(data));
    return session.expires > Date.now() && typeof session.key === "string" ? session.key : null;
  } catch { return null; }
}
function cookie(value, age = 28800) {
  return `${COOKIE}=${value}; Path=/; Max-Age=${age}; Secure; HttpOnly; SameSite=Strict`;
}
function cookieValue(request) {
  return request.headers.get("Cookie")?.split(";").map(s => s.trim()).find(s => s.startsWith(COOKIE + "="))?.slice(COOKIE.length + 1);
}
async function boundedJSON(response, limit = 2_000_000) {
  const reader = response.body?.getReader();
  if (!reader) throw new Error("invalid_response");
  let size = 0;
  const parts = [];
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) { await reader.cancel(); throw new Error("response_too_large"); }
      parts.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const part of parts) { bytes.set(part, offset); offset += part.byteLength; }
  try { return JSON.parse(decoder.decode(bytes)); } catch { throw new Error("invalid_response"); }
}
async function readAPI(path, key) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 3500);
  try {
    const response = await fetch(API + path, { method: "GET", headers: { "X-Team-Key": key, Accept: "application/json" }, signal: controller.signal, redirect: "error" });
    if (!response.ok) throw new Error(response.status === 401 ? "bad_key" : response.status === 429 ? "rate_limited" : "upstream_error");
    return await boundedJSON(response);
  } catch (error) {
    if (["bad_key", "rate_limited", "upstream_error", "invalid_response", "response_too_large"].includes(error.message)) throw error;
    throw new Error("connection_error");
  } finally { clearTimeout(timer); }
}
function list(payload, field) {
  const data = Array.isArray(payload) ? payload : payload?.[field];
  if (!Array.isArray(data)) throw new Error("invalid_response");
  return data;
}
function normalize(name, payload) {
  if (name === "inventario y saldo") {
    if (!Number.isFinite(payload?.cash)) throw new Error("invalid_response");
    const assets = list(payload, "assets").map(a => {
      if (a.id == null || typeof a.ref !== "string") throw new Error("invalid_response");
      return { id: a.id, ref: a.ref, name: a.name || a.ref, kind: a.kind || "card", paid: null, value: a.your_value ?? null, serial: a.serial ?? null };
    });
    return { cash: payload.cash, assets, team_id: payload.id, team_name: payload.name };
  }
  if (name === "reloj") {
    if (!Number.isInteger(payload?.tick)) throw new Error("invalid_response");
    return { tick: payload.tick, paused: !!payload.paused };
  }
  const isOffers = name === "ofertas";
  return list(payload, isOffers ? "offers" : "threads").map(item => {
    if (item.id == null || typeof item.status !== "string") throw new Error("invalid_response");
    const allowed = isOffers ? ["id", "status", "maker", "to", "give", "want", "final", "venue", "thread_id"] : ["id", "status", "with", "closed_reason"];
    return Object.fromEntries(allowed.filter(k => item[k] != null).map(k => [k, item[k]]));
  });
}
async function cacheRequest(key, secret, origin) {
  const signingKey = await crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const digest = encode(await crypto.subtle.sign("HMAC", signingKey, encoder.encode(key)));
  return new Request(origin + "/__private-state/" + digest);
}
async function stateFor(key, secret, origin) {
  const cacheKey = await cacheRequest(key, secret, origin);
  const cache = globalThis.caches?.default;
  let previous = null;
  try { const cached = await cache?.match(cacheKey); if (cached) previous = await cached.json(); } catch { /* Refresh instead. */ }
  if (previous && Date.now() - previous.last_poll_ms < INTERVAL) return previous;
  const pollStarted = Date.now();
  const stamp = new Date().toISOString();
  const paths = ["/api/me", "/api/clock", "/api/me/offers", "/api/me/threads"];
  const results = await Promise.allSettled(paths.map((path, index) => readAPI(path, key).then(value => normalize(fields[index], value))));
  if (results[0].status === "rejected" && results[0].reason.message === "bad_key") throw new Error("bad_key");
  const state = previous || { mode: "live", scenario: "Bazaar real", cash: null, assets: [], offers: [], threads: [], events: [], movements: [], pending: null, tick: null, checks: {}, updated_at: null, finished: false };
  results.forEach((result, index) => {
    const name = fields[index];
    const oldCheck = state.checks[name];
    state.checks[name] = { ok: result.status === "fulfilled", attempted_at: stamp,
      verified_at: result.status === "fulfilled" ? stamp : oldCheck?.verified_at ?? null,
      error: result.status === "rejected" ? result.reason.message : null };
    if (result.status !== "fulfilled") return;
    if (index === 0) {
      if (previous?.updated_at) {
        const old = new Map(state.assets.map(a => [a.id, a]));
        const current = new Map(result.value.assets.map(a => [a.id, a]));
        for (const [direction, from, to] of [["in", current, old], ["out", old, current]]) {
          for (const [id, asset] of from) if (!to.has(id)) state.movements.push({ id: stamp + ":" + id + direction, side: direction, card: asset.ref, asset_id: id, observed_at: stamp, tick: null, price: null, paid: null, counterparty: "Cambio confirmado de inventario" });
        }
        state.movements = state.movements.slice(-100);
      }
      Object.assign(state, result.value, { updated_at: stamp });
    } else if (index === 1) Object.assign(state, result.value);
    else state[index === 2 ? "offers" : "threads"] = result.value;
  });
  state.last_poll_ms = pollStarted;
  state.poll_seconds = 5;
  if (cache) {
    const response = new Response(JSON.stringify(state), { headers: { "Content-Type": "application/json", "Cache-Control": "max-age=86400" } });
    try { await cache.put(cacheKey, response); } catch { /* A cache failure never exposes data. */ }
  }
  return state;
}

export function createWorker(panelHTML) {
  return {
    async fetch(request, env) {
      const url = new URL(request.url);
      if (url.pathname === "/" && request.method === "GET") return new Response(panelHTML, { headers: {
        "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'self' https://chatgpt.com https://*.chatgpt.com; form-action 'self'",
      } });
      if (request.method === "POST" && !["/api/login", "/api/logout"].includes(url.pathname)) return json({ error: "not_found" }, 404);
      if (request.method === "POST" && request.headers.get("Origin") !== url.origin) return json({ error: "forbidden" }, 403);
      if (url.pathname === "/api/logout" && request.method === "POST") return json({ ok: true }, 200, { "Set-Cookie": cookie("", 0) });
      if (url.pathname === "/api/login" && request.method === "POST") {
        try {
          const body = await boundedJSON(request, 2048);
          if (typeof body.key !== "string" || !/^[A-Za-z0-9_-]{5,200}$/.test(body.key)) return json({ error: "invalid_key", message: "Revisa la clave del equipo." }, 400);
          await secretKey(env.SESSION_SECRET);
          normalize("inventario y saldo", await readAPI("/api/me", body.key));
          const token = await encryptSession(body.key, env.SESSION_SECRET);
          return json({ ok: true }, 200, { "Set-Cookie": cookie(token) });
        } catch (error) {
          return json({ error: error.message, message: error.message === "bad_key" ? "La clave no es válida." : "No se pudo verificar el acceso. Inténtalo de nuevo." }, error.message === "bad_key" ? 401 : 503);
        }
      }
      if (url.pathname === "/api/state" && request.method === "GET") {
        const key = await decryptSession(cookieValue(request), env.SESSION_SECRET);
        if (!key) return json({ error: "auth_required", message: "Introduce la clave del equipo para ver sus cartas." }, 401);
        try { return json(await stateFor(key, env.SESSION_SECRET, url.origin)); }
        catch (error) { return json({ error: error.message, message: "No se pudo verificar el estado del equipo." }, error.message === "bad_key" ? 401 : 503); }
      }
      return json({ error: "not_found" }, 404);
    },
  };
}
