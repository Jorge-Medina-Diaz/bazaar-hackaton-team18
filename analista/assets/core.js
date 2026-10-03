/* Mesa del Analista · núcleo común de las tres páginas.
   Solo GET públicos a la API del juego (CORS *): sin clave, sin escrituras, nunca /api/admin.
   Lee clock y feed cada 15 s, clasificación, mercados y El Rastro cada 30 s, calendario cada 5 min, y guarda en este
   navegador (localStorage) la historia de la clasificación, de los mercados y el feed acumulado (el feed público solo
   devuelve los últimos 500 eventos, ~10 min de juego). Las páginas pintan desde Core.state y Core.on(render). */
"use strict";
const Core = (() => {
  const API = "https://bazaar.causaprima.ai";
  const US = "t18";
  const KEY = "t18-core-v1";
  const OLD_KEY = "t18-analista-v1";
  const PAGES = [
    {href: "./", file: "index.html", name: "Mesa", sub: "resumen y decisiones"},
    {href: "duelos.html", file: "duelos.html", name: "Duelos", sub: "sesiones y rendimiento"},
    {href: "mercado.html", file: "mercado.html", name: "Mercado", sub: "libros, precios, venues"},
    {href: "scoring.html", file: "scoring.html", name: "Scoring", sub: "qué pesa cada punto"},
    {href: "jurado.html", file: "jurado.html", name: "Jurado", sub: "demo para jueces"},
  ];
  const KEEP = new Set(["settlement", "offer.listed", "offer.cancelled", "duel.closed", "duels.scheduled",
    "venue.announcement", "venue.opened", "venue.closed", "venue.fee_changed", "schedule.fired", "bench.started"]);
  // Topes de dealers: plan-public.js (generado desde config/plan.json del repo por jury.report), con copia de respaldo.
  // Son los límites del repo, no la configuración que el operador tenga cargada. Multiplicadores: docs/knowledge.md.
  const DEALER_MAX = (globalThis.T18PublicPlan && globalThis.T18PublicPlan.dealer_max) || {"RET-01":11,"RET-02":11,"RET-03":11,"RET-04":11,"RET-05":11,"RET-06":25,"RET-07":25,"RET-08":31,"RET-09":90,"RET-10":90,
    "CHA-01":12,"CHA-02":12,"CHA-03":12,"CHA-04":12,"CHA-05":12,"CHA-06":25,"CHA-07":25,"CHA-08":31,"CHA-09":100,"CHA-10":100};
  const MULT = {CHA: 1.6, RET: 1.3, SAL: 1.1, LAT: 0.9, LAV: 0.7, MAL: 0.5};
  const BASE = {common: 10, uncommon: 25, rare: 70};

  // ---------- utilidades ----------
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const fmt = (n, d = 2) => n == null || isNaN(n) ? "—" : Number(n).toLocaleString("es-ES", {minimumFractionDigits: d, maximumFractionDigits: d});
  const pct = (n, d = 0) => n == null || isNaN(n) ? "—" : fmt(n * 100, d) + " %";
  const hhmm = d => new Date(d).toLocaleTimeString("es-ES", {hour: "2-digit", minute: "2-digit"});
  const median = a => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
  const fixText = s => String(s || "").replace(/Â·/g, "·").replace(/Ã­/g, "í").replace(/Ã¡/g, "á").replace(/Ã©/g, "é").replace(/Ã³/g, "ó").replace(/Ãº/g, "ú").replace(/Ã±/g, "ñ");
  function cd(ms) {
    if (ms == null) return "—";
    if (ms < 0) return "ahora";
    const m = Math.floor(ms / 60000), h = Math.floor(m / 60);
    return h ? `${h} h ${String(m % 60).padStart(2, "0")} min` : `${m} min ${String(Math.floor(ms / 1000) % 60).padStart(2, "0")} s`;
  }
  const setOf = ref => String(ref || "").split("-")[0];
  const value = (ref, rarity) => MULT[setOf(ref)] && BASE[rarity] ? +(BASE[rarity] * MULT[setOf(ref)]).toFixed(1) : null;
  const bidCards = o => (((o || {}).want || {}).types || []).filter(t => t.startsWith("card:")).map(t => t.slice(5));
  const isCardBid = o => (((o || {}).give || {}).cash || 0) > 0 && bidCards(o).length > 0;
  const isAsk = o => (((o || {}).give || {}).assets || []).length > 0 && (((o || {}).want || {}).cash || 0) > 0;

  // ---------- almacenamiento (solo este navegador) ----------
  let D = {hist: [], vhist: [], feed: {}, settings: {}};
  function readStore() {
    try { const raw = localStorage.getItem(KEY); if (raw) return JSON.parse(raw); } catch (e) {}
    return null;
  }
  (function load() {
    const got = readStore();
    if (got) { D = Object.assign(D, got); return; }
    try {                                   // migración desde la primera versión de la Mesa
      const old = JSON.parse(localStorage.getItem(OLD_KEY) || "null");
      if (old) {
        D.hist = old.hist || []; D.vhist = old.venues || []; D.settings = old.settings || {};
        Object.values(old.feed || {}).forEach(e => { if (KEEP.has(e.type)) D.feed[e.id] = e; });
      }
    } catch (e) {}
  })();
  function save() {
    try {
      const other = readStore();            // otra pestaña puede haber guardado: se une, no se pisa
      if (other) {
        Object.assign(D.feed, Object.fromEntries(Object.entries(other.feed || {}).filter(([k]) => !(k in D.feed))));
        const seen = new Set(D.hist.map(h => h.tick));
        (other.hist || []).forEach(h => { if (!seen.has(h.tick)) D.hist.push(h); });
        D.hist.sort((a, b) => a.ts - b.ts);
        const vs = new Set(D.vhist.map(h => h.ts));
        (other.vhist || []).forEach(h => { if (!vs.has(h.ts)) D.vhist.push(h); });
        D.vhist.sort((a, b) => a.ts - b.ts);
      }
      D.hist = D.hist.slice(-600); D.vhist = D.vhist.slice(-600);
      const ids = Object.keys(D.feed).map(Number).sort((a, b) => b - a).slice(0, 6000);
      const keep = {}; ids.forEach(i => keep[i] = D.feed[i]); D.feed = keep;
      localStorage.setItem(KEY, JSON.stringify(D));
    } catch (e) {}
  }
  const setting = (k, d) => D.settings[k] ?? d;
  function set(k, v) { D.settings[k] = v; save(); emit(); }
  function bind(sel, k, ev = "input") {
    const el = $(sel); if (!el) return;
    const v = D.settings[k]; if (v != null) el.value = v;
    el.addEventListener(ev, () => set(k, el.value));
  }

  // ---------- red ----------
  const state = {clock: null, schedule: null, lb: null, venues: null, rastro: null, paused: false, lastOk: 0, lastErr: null};
  async function get(path) {
    const r = await fetch(API + path, {cache: "no-store", credentials: "omit", signal: AbortSignal.timeout(10000)});
    if (!r.ok) throw new Error(path + " → HTTP " + r.status);
    return r.json();
  }
  function slim(e) { return {id: e.id, tick: e.tick, t: e.t, type: e.type, actor: e.actor, payload: e.payload, seen: Date.now()}; }
  function recordLb() {
    const lb = state.lb; if (!lb || !lb.teams) return;
    const tick = lb.snapshot_tick ?? lb.tick;
    if (D.hist.length && D.hist[D.hist.length - 1].tick === tick) return;
    const teams = {};
    lb.teams.forEach(t => teams[t.team] = {score: t.score, neg: t.negotiating, market: t.market, deals: t.deals, rank: t.rank});
    D.hist.push({ts: Date.now(), tick, round: lb.round, teams});
  }
  function recordVenues() {
    const v = {}, vol = {};
    state.venues.forEach(x => { v[x.venue] = x.trades; vol[x.venue] = x.volume; });
    const last = D.vhist[D.vhist.length - 1];
    if (last && JSON.stringify(last.v) === JSON.stringify(v) && Date.now() - last.ts < 600000) return;
    D.vhist.push({ts: Date.now(), tick: state.clock && state.clock.tick, v, vol});
  }
  const inflight = new Set();               // una lectura de cada fuente a la vez
  async function poll(what) {
    if (state.paused) return;
    what = what.filter(w => !inflight.has(w));
    if (!what.length) return;
    what.forEach(w => inflight.add(w));
    try {
      const jobs = [];
      if (what.includes("clock")) jobs.push(get("/api/clock").then(x => state.clock = x));
      if (what.includes("schedule")) jobs.push(get("/api/schedule").then(x => state.schedule = x));
      if (what.includes("lb")) jobs.push(get("/api/leaderboard").then(x => { state.lb = x; recordLb(); }));
      if (what.includes("venues")) jobs.push(get("/api/venues").then(x => { state.venues = x.venues || []; recordVenues(); }));
      if (what.includes("rastro")) jobs.push(get("/api/venues/rastro/offers").then(x => state.rastro = x.offers || []));
      if (what.includes("feed")) jobs.push(get("/api/feed?limit=500").then(f => (f.events || []).forEach(e => { if (KEEP.has(e.type)) D.feed[e.id] = slim(e); })));
      await Promise.all(jobs);
      state.lastOk = Date.now(); state.lastErr = null; save();
    } catch (e) { state.lastErr = String(e.message || e); }
    finally { what.forEach(w => inflight.delete(w)); }
    emit();
  }
  const ALL = ["clock", "schedule", "lb", "venues", "rastro", "feed"];
  const refresh = () => { const p = state.paused; state.paused = false; return poll(ALL).then(() => state.paused = p); };

  // ---------- suscriptores ----------
  const subs = [], secs = [];
  const on = fn => subs.push(fn);
  const onSecond = fn => secs.push(fn);
  function emit() { renderHeader(); subs.forEach(f => { try { f(); } catch (e) { console.error(e); } }); }

  // ---------- derivados ----------
  const feed = () => Object.values(D.feed).sort((a, b) => a.id - b.id);
  const feedOf = type => feed().filter(e => e.type === type);
  function histAgo(ms) {
    const round = state.lb && state.lb.round;
    if (ms === 3600e3 && globalThis.T18Evidence) return T18Evidence.hourBaseline(D.hist, Date.now(), round);  // hora completa, misma ronda
    const H = D.hist.filter(h => round == null || h.round === round); if (H.length < 2) return null;
    const target = Date.now() - ms; let pick = null;
    for (const h of H) { if (h.ts <= target) pick = h; else break; }
    pick = pick || H[0];
    return pick === H[H.length - 1] ? null : pick;
  }
  function venueRate(vid, windowMs = 3600e3) {
    const V = D.vhist; if (V.length < 2) return null;
    const now = V[V.length - 1], target = now.ts - windowMs;
    let base = V[0]; for (const s of V) { if (s.ts <= target) base = s; }
    if (base === now || now.ts - base.ts < 120e3) return null;
    return ((now.v[vid] || 0) - (base.v[vid] || 0)) / ((now.ts - base.ts) / 3600e3);
  }
  function teamOfPseudo() {                 // el feed publica el equipo; el libro, un seudónimo: se cruzan por id de oferta
    const byId = {}; feedOf("offer.listed").forEach(e => { const o = (e.payload || {}).offer; if (o) byId[o.id] = o.maker; });
    const map = {}; (state.rastro || []).forEach(o => { if (byId[o.id] && byId[o.id] !== o.maker) map[o.maker] = byId[o.id]; });
    return map;
  }
  function wallOf(h) {
    const sc = state.schedule, c = state.clock; if (!sc || !c) return null;
    const anchors = [[c.t_hours, Date.now()]];
    (sc.upcoming || []).forEach(e => { if (e.wall && e.action === "day_opens") anchors.push([e.at_hours, Date.parse(e.wall)]); });
    let best = anchors[0];
    anchors.forEach(a => { if (a[0] <= h + 1e-9 && a[0] >= best[0]) best = a; });
    return new Date(best[1] + (h - best[0]) * 3600e3);
  }
  function upcoming(filter) {
    const sc = state.schedule, c = state.clock; if (!sc || !c) return [];
    return (sc.upcoming || []).filter(e => e.at_hours >= c.t_hours - 0.02 && (!filter || filter(e)));
  }

  // ---------- gráficos ----------
  const COLORS = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s6)"];
  function lineChart(series, o = {}) {
    const W = o.w || 560, H = o.h || 220, L = 44, R = 14, T = 10, B = 26;
    const pts = series.flatMap(s => s.pts);
    if (pts.length < 2) return `<div class="empty">${esc(o.empty || "aún no hay datos suficientes")}</div>`;
    let x0 = Math.min(...pts.map(p => p[0])), x1 = Math.max(...pts.map(p => p[0]));
    let lo = o.y0 != null ? o.y0 : Math.min(...pts.map(p => p[1])), hi = Math.max(...pts.map(p => p[1]));
    if (hi - lo < (o.minSpan || 1)) { hi = lo + (o.minSpan || 1); }
    if (x1 === x0) x1 = x0 + 1;
    const x = v => L + (v - x0) / (x1 - x0) * (W - L - R), y = v => T + (hi - v) / (hi - lo) * (H - T - B);
    const xf = o.xfmt || (v => fmt(v, 0)), yf = o.yfmt || (v => fmt(v, 1));
    let g = "";
    for (let i = 0; i <= 4; i++) { const v = lo + (hi - lo) * i / 4, yy = y(v);
      g += `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" stroke="var(--rule)"/><text x="${L - 6}" y="${yy + 4}" text-anchor="end">${esc(yf(v))}</text>`; }
    g += `<text x="${L}" y="${H - 6}">${esc(xf(x0))}</text><text x="${W - R}" y="${H - 6}" text-anchor="end">${esc(xf(x1))}</text>`;
    series.forEach((s, i) => {
      if (s.pts.length < 1) return;
      const c = s.color || COLORS[i % COLORS.length];
      const d = s.pts.map(p => `${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
      const lp = s.pts[s.pts.length - 1];
      g += `<polyline fill="none" stroke="${c}" stroke-width="${s.bold ? 3 : 1.8}" stroke-linejoin="round" points="${d}"${s.dash ? ' stroke-dasharray="5 4"' : ""}/>`;
      g += `<circle cx="${x(lp[0]).toFixed(1)}" cy="${y(lp[1]).toFixed(1)}" r="3.5" fill="${c}"/>`;
    });
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.label || "gráfico")}">${g}</svg>`;
  }
  const legend = series => series.map((s, i) => `<span><i style="background:${s.color || COLORS[i % COLORS.length]}"></i>${esc(s.name)}</span>`).join("");
  function hbars(rows, o = {}) {             // rows: [{label, v, cls}] con signo
    if (!rows.length) return `<div class="empty">${esc(o.empty || "sin datos")}</div>`;
    const m = Math.max(...rows.map(r => Math.abs(r.v)), 1e-9), neg = rows.some(r => r.v < 0);
    return `<div class="hbars">${rows.map(r => {
      const w = Math.abs(r.v) / m * (neg ? 50 : 100), left = neg ? (r.v < 0 ? 50 - w : 50) : 0;
      const col = r.color || (r.v < 0 ? "var(--bad)" : "var(--s1)");
      return `<div class="hbar ${r.cls || ""}"><span>${esc(r.label)}</span><span class="track"><span class="fill" style="left:${left}%;width:${w}%;background:${col}"></span>${neg ? '<span class="zero" style="left:50%"></span>' : ""}</span><span class="num" style="text-align:right">${esc(o.fmt ? o.fmt(r.v) : fmt(r.v))}</span></div>`;
    }).join("")}</div>`;
  }
  function sortable(table, rows, cols, render, defKey, defDir = -1) {   // tabla con cabeceras clicables
    const key = "sort:" + table.id;
    let [k, dir] = (setting(key, defKey + ":" + defDir)).split(":"); dir = Number(dir);
    table.querySelector("thead").innerHTML = "<tr>" + cols.map(c => `<th ${c.sort ? `data-sort="${c.key}"` : ""} class="${c.num ? "num" : ""}">${esc(c.label)}${k === c.key ? (dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("") + "</tr>";
    table.querySelectorAll("th[data-sort]").forEach(th => th.onclick = () => {
      const nk = th.dataset.sort; set(key, nk + ":" + (nk === k ? -dir : -1));
    });
    const sorted = [...rows].sort((a, b) => { const x = a[k], y = b[k]; return (x == null) - (y == null) || (x > y ? 1 : x < y ? -1 : 0) * dir; });
    table.querySelector("tbody").innerHTML = sorted.map(render).join("") || `<tr><td colspan="${cols.length}" class="empty">sin filas</td></tr>`;
  }

  // ---------- cabecera ----------
  function header(active) {
    let file = location.pathname.split("/").pop() || "index.html";
    if (!file.includes(".")) file += ".html";          // Vercel cleanUrls: /duelos -> duelos.html
    const cur = active || file;
    const nav = document.createElement("header");
    nav.className = "nav";
    nav.innerHTML = `<div class="nav-in">
      <a class="brand" href="./"><span class="mark">t18</span><span class="nm">Mesa del Analista<small>Bazaar · Cromos de Madrid</small></span></a>
      <nav class="tabs-nav" aria-label="Secciones">${PAGES.map(p => `<a href="${p.href}" ${p.file === cur ? 'aria-current="page"' : ""}><b>${p.name}</b><span>${p.sub}</span></a>`).join("")}</nav>
      <div class="nav-right">
        <span class="chip opt" id="nv-tick"><span class="k">tick</span><b>—</b></span>
        <span class="chip opt" id="nv-t"><span class="k">t</span><b>—</b></span>
        <span class="chip next" id="nv-next"><span class="k">próximo</span><b>—</b></span>
        <span class="live"><span class="dot" id="nv-dot"></span><span id="nv-fresh">—</span></span>
        <button type="button" id="nv-pause" aria-pressed="false">Pausar</button>
        <button type="button" id="nv-now">Actualizar</button>
        <select id="nv-theme" aria-label="Tema"><option value="">Sistema</option><option value="light">Claro</option><option value="dark">Oscuro</option></select>
      </div></div>`;
    document.body.prepend(nav);
    $("#nv-pause").onclick = () => {
      state.paused = !state.paused;
      $("#nv-pause").textContent = state.paused ? "Reanudar" : "Pausar";
      $("#nv-pause").setAttribute("aria-pressed", state.paused);
      if (!state.paused) poll(ALL); else emit();
    };
    $("#nv-now").onclick = refresh;
    const th = $("#nv-theme");                         // misma clave que scoring.html: un solo tema en todo el sitio
    let t = setting("theme", ""); try { t = localStorage.getItem("t18-theme") ?? t; } catch (e) {}
    th.value = t;
    const apply = () => th.value ? document.documentElement.setAttribute("data-theme", th.value) : document.documentElement.removeAttribute("data-theme");
    th.onchange = () => { D.settings.theme = th.value; try { localStorage.setItem("t18-theme", th.value); } catch (e) {} save(); apply(); }; apply();
  }
  const KEY_EVENTS = /^(duels|set_release|grant_all|round|day_opens|persona_opens)$/;
  function renderHeader() {
    const c = state.clock;
    if (c && $("#nv-tick")) {
      $("#nv-tick b").textContent = c.tick;
      $("#nv-t b").textContent = fmt(c.t_hours, 2);
      $("#nv-t").title = fixText(c.round_name) + (c.paused ? " · PAUSADO" : "");
    }
    const nx = upcoming(e => KEY_EVENTS.test(e.action))[0];
    if (nx && $("#nv-next")) {
      const w = wallOf(nx.at_hours);
      $("#nv-next .k").textContent = fixText((nx.params && nx.params.name) || nx.note || nx.action).slice(0, 26);
      $("#nv-next b").textContent = w ? cd(w - Date.now()) : "—";
    }
    if ($("#nv-dot")) {
      $("#nv-dot").className = "dot " + (state.lastErr ? "err" : state.lastOk && !state.paused ? "on" : "");
      $("#nv-fresh").textContent = state.paused ? "en pausa" : state.lastErr ? "error" : state.lastOk ? `hace ${Math.round((Date.now() - state.lastOk) / 1000)} s` : "conectando";
    }
  }
  function alerts(list) {                    // list: [[cls, msg]]; recuerda desde cuándo
    const box = $("#alerts"); if (!box) return;
    const fired = alerts.f || (alerts.f = new Map());
    list.forEach(([, m]) => { if (!fired.has(m)) fired.set(m, Date.now()); });
    if (state.lastErr) list = [["warn", `Error leyendo la API: ${state.lastErr}. Se reintenta solo.`], ...list];
    box.innerHTML = list.map(([k, m]) => `<div class="alert ${k}"><span>${esc(m)}</span><span class="when">${fired.has(m) ? "desde " + hhmm(fired.get(m)) : ""}</span></div>`).join("");
  }

  function start(active) {
    header(active);
    emit();
    poll(ALL);
    setInterval(() => poll(["clock", "feed"]), 15000);
    setInterval(() => poll(["lb", "venues", "rastro"]), 30000);
    setInterval(() => poll(["schedule"]), 300000);
    setInterval(() => { renderHeader(); secs.forEach(f => { try { f(); } catch (e) {} }); }, 1000);
  }

  return {API, US, get, DEALER_MAX, MULT, BASE, COLORS, $, $$, esc, fmt, pct, hhmm, cd, median, fixText, setOf, value,
    bidCards, isCardBid, isAsk, get state() { return state; }, get D() { return D; }, save, setting, set, bind,
    on, onSecond, emit, feed, feedOf, histAgo, venueRate, teamOfPseudo, wallOf, upcoming, lineChart, legend, hbars,
    sortable, alerts, start, refresh};
})();
