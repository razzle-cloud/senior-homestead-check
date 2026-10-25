// Outreach list and map for approved partners. Sign-in is Supabase Auth (email + password);
// the list and the map are served only to approved email addresses, and every view is logged.
import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";

const SUPABASE_URL = "https://kwmfcuwqplcfruolrjhz.supabase.co";
const SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt3bWZjdXdxcGxjZnJ1b2xyamh6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTEzMzQ5MzYsImV4cCI6MjEwNjkxMDkzNn0.J_9ZPp5Qd0EghylB0FRL-SVDFSdu_IqcQfRJ_d1i34c";
const sb = createClient(SUPABASE_URL, SUPABASE_KEY, { auth: { persistSession: true, storage: window.sessionStorage } });

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (n) => (n ? "$" + Math.round(n).toLocaleString("en-US") : "");
const PAGE = 50;
let rows = [], view = [], page = 0;
let byId = new Map();          // parcel_id -> list row

async function call(action) {
  const { data: s } = await sb.auth.getSession();
  if (!s.session) return { status: "signed_out" };
  const r = await fetch(`${SUPABASE_URL}/functions/v1/outreach`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${s.session.access_token}`, apikey: SUPABASE_KEY },
    body: JSON.stringify({ action }),
  });
  return r.json().catch(() => ({ status: "error" }));
}

function show(which) {
  for (const id of ["signin-view", "denied-view", "list-view", "loading-view"]) $(id).hidden = id !== which;
}

async function load() {
  show("loading-view");
  const d = await call("view");
  if (d.status === "signed_out") return show("signin-view");
  if (d.status === "not_allowed") return show("denied-view");
  if (d.status !== "ok") { show("signin-view"); $("signin-error").textContent = "The list couldn't be loaded. Try again in a minute."; return; }
  rows = d.rows || [];
  byId = new Map(rows.map((r) => [r.parcel_id, r]));
  const { data: u } = await sb.auth.getUser();
  $("who").textContent = u?.user?.email || "";
  show("list-view");
  filter();
}

function groupsOf(r) {
  const g = [];
  if (r.proven.length) g.push("proven");
  if (r.likely.length) g.push("likely");
  if (r.possible.length) g.push("possible");
  if (r.long_tenure) g.push("long_tenure");
  return g;
}

function filter() {
  const want = new Set([...document.querySelectorAll('#groups input:checked')].map((i) => i.value));
  const q = $("search").value.trim().toLowerCase();
  const sort = $("sort").value;
  view = rows.filter((r) => groupsOf(r).some((g) => want.has(g)) &&
    (!q || `${r.address} ${r.owner} ${r.co_owner} ${r.mail}`.toLowerCase().includes(q)));
  if (sort === "savings") view.sort((a, b) => (b.city_savings + b.county_savings) - (a.city_savings + a.county_savings));
  else if (sort === "since") view.sort((a, b) => (a.owner_since ?? 9999) - (b.owner_since ?? 9999));
  else view.sort((a, b) => String(a.address).localeCompare(String(b.address), undefined, { numeric: true }));
  page = 0;
  $("count").textContent = `${view.length.toLocaleString("en-US")} homes`;
  draw();
  Map_.refilter();
}

function tagsHtml(r) {
  return [
    ...r.proven.map((t) => `<span class="tag proven">${esc(t)}</span>`),
    ...r.likely.map((t) => `<span class="tag">Likely: ${esc(t)}</span>`),
    ...r.possible.map((t) => `<span class="tag">Possible: ${esc(t)}</span>`),
    r.long_tenure ? `<span class="tag">Owner since ${esc(r.owner_since ?? "before 1990")}, no senior exemption</span>` : "",
  ].join("");
}

function draw() {
  const slice = view.slice(page * PAGE, page * PAGE + PAGE);
  $("list").querySelector("tbody").innerHTML = slice.map((r) => `<tr><td><strong>${esc(r.address)}</strong></td>
      <td>${esc(r.owner)}${r.co_owner ? `<br>${esc(r.co_owner)}` : ""}</td>
      <td>${esc(r.mail)}</td><td>${tagsHtml(r)}</td>
      <td class="num">${money(r.city_savings)}</td><td class="num">${money(r.county_savings)}</td></tr>`).join("")
    || `<tr><td colspan="6" class="none">No homes match these filters.</td></tr>`;
  const pages = Math.max(1, Math.ceil(view.length / PAGE));
  $("pageinfo").textContent = `Page ${page + 1} of ${pages}`;
  $("prev").disabled = page === 0;
  $("next").disabled = page >= pages - 1;
}

async function exportCsv() {
  await call("export");                              // records the download in the access log
  const head = ["address", "owner", "co_owner", "mailing_address", "proven_gaps", "likely_gaps", "possible_gaps", "owner_since_before_1990_no_senior", "owner_since", "est_city_savings", "est_county_savings"];
  const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const lines = [head.join(",")].concat(view.map((r) => [r.address, r.owner, r.co_owner, r.mail, r.proven.join("; "), r.likely.join("; "), r.possible.join("; "), r.long_tenure ? "yes" : "", r.owner_since, Math.round(r.city_savings || 0), Math.round(r.county_savings || 0)].map(q).join(",")));
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `decatur-outreach-${new Date().toISOString().slice(0, 10)}.csv` });
  a.click();
  URL.revokeObjectURL(a.href);
}

// ------------------------------------------------------------------ map
// Shapes arrive in metres (Web Mercator) relative to an origin, delta-encoded:
// [x0, y0, dx1, dy1, ...]. Classes say which exemption is missing, because that decides which office
// the homeowner visits: 1 county homestead, 2 city homestead, 3 senior (age proven), 4 senior (likely),
// 5 long-time owner with no senior exemption, 6 possible county senior, 0 none.
const CLASSES = [
  { c: 1, label: "County homestead missing", desc: "City homestead on file, none with DeKalb County" },
  { c: 2, label: "City homestead missing", desc: "DeKalb homestead on file, no GH-1 with the City" },
  { c: 3, label: "Senior exemption missing, age proven", desc: "GH-2, GH-3 or the 70+ school exemption; age already on file" },
  { c: 4, label: "Senior exemption likely", desc: "Age on file; depends on income or turning 70" },
  { c: 5, label: "Long-time owner, no senior exemption", desc: "Owner since before 1990, so probably 65 or older" },
  { c: 6, label: "Possible county senior gap", desc: "DeKalb income limits can't be confirmed" },
];
const NCLS = CLASSES.length;

const Map_ = (() => {
  let loaded = false, loading = false, data = null;
  let parcels = [], streets = [], cityPath = null, labels = [];
  let grid = new Map();            // cell -> parcel indexes, for hit testing
  const CELL = 100;
  let s = 1, tx = 0, ty = 0, fit = null;
  let canvas, ctx, dpr = 1, W = 0, H = 0, selected = -1, hover = -1;
  let batches = null;              // per-colour Path2D, rebuilt when filters change

  function decode(arr) {
    const pts = [];
    let x = 0, y = 0;
    for (let i = 0; i < arr.length; i += 2) { x += arr[i]; y += arr[i + 1]; pts.push(x, -y); }
    return pts;
  }
  function toPath(rings, close) {
    const p = new Path2D();
    for (const pts of rings) {
      p.moveTo(pts[0], pts[1]);
      for (let i = 2; i < pts.length; i += 2) p.lineTo(pts[i], pts[i + 1]);
      if (close) p.closePath();
    }
    return p;
  }

  function build(d) {
    data = d;
    const city = (d.city || []).map(decode);
    cityPath = toPath(city, true);
    let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
    for (const pts of city) for (let i = 0; i < pts.length; i += 2) {
      minx = Math.min(minx, pts[i]); maxx = Math.max(maxx, pts[i]); miny = Math.min(miny, pts[i + 1]); maxy = Math.max(maxy, pts[i + 1]);
    }
    fit = { minx, miny, maxx, maxy };
    parcels = (d.parcels || []).map(([id, cls, rings], idx) => {
      const rs = rings.map(decode);
      let a = Infinity, b = Infinity, c = -Infinity, e = -Infinity;
      for (const pts of rs) for (let i = 0; i < pts.length; i += 2) {
        a = Math.min(a, pts[i]); c = Math.max(c, pts[i]); b = Math.min(b, pts[i + 1]); e = Math.max(e, pts[i + 1]);
      }
      for (let gx = Math.floor(a / CELL); gx <= Math.floor(c / CELL); gx++)
        for (let gy = Math.floor(b / CELL); gy <= Math.floor(e / CELL); gy++) {
          const k = gx + "," + gy; if (!grid.has(k)) grid.set(k, []); grid.get(k).push(idx);
        }
      return { id, cls, rings: rs, path: toPath(rs, true), box: [a, b, c, e] };
    });
    streets = (d.streets || []).map(([name, rc, line]) => ({ name, rc, pts: decode(line) }));
    const strPath = new Path2D(), majPath = new Path2D();
    for (const st of streets) {
      const p = st.rc > 0 ? majPath : strPath;
      p.moveTo(st.pts[0], st.pts[1]);
      for (let i = 2; i < st.pts.length; i += 2) p.lineTo(st.pts[i], st.pts[i + 1]);
    }
    streets.paths = [strPath, majPath];
    // one label candidate per street segment: midpoint of its longest piece
    labels = [];
    for (const st of streets) {
      if (!st.name) continue;
      let best = 0, bi = -1;
      for (let i = 0; i + 3 < st.pts.length; i += 2) {
        const l = Math.hypot(st.pts[i + 2] - st.pts[i], st.pts[i + 3] - st.pts[i + 1]);
        if (l > best) { best = l; bi = i; }
      }
      if (bi < 0 || best < 60) continue;
      const [x1, y1, x2, y2] = [st.pts[bi], st.pts[bi + 1], st.pts[bi + 2], st.pts[bi + 3]];
      let ang = Math.atan2(y2 - y1, x2 - x1);
      if (ang > Math.PI / 2) ang -= Math.PI; else if (ang < -Math.PI / 2) ang += Math.PI;
      labels.push({ name: st.name, x: (x1 + x2) / 2, y: (y1 + y2) / 2, ang, len: best, major: st.rc > 0 });
    }
    labels.sort((a, b) => (b.major - a.major) || (b.len - a.len));
    loaded = true;
  }

  function colors() {
    const cs = getComputedStyle(document.documentElement);
    const v = (n) => cs.getPropertyValue(n).trim();
    return { land: v("--map-land"), city: v("--map-city"), street: v("--map-street"), edge: v("--map-edge"), none: v("--map-none"),
             ink: v("--ink"), paper: v("--paper"), sel: v("--ink"),
             cls: [null, ...CLASSES.map((k) => v("--map-c" + k.c))] };
  }

  function visibleIds() { return new Set(view.map((r) => r.parcel_id)); }

  function rebatch() {
    if (!loaded) return;
    const vis = visibleIds();
    batches = Array.from({ length: NCLS + 1 }, () => new Path2D());
    const counts = new Array(NCLS + 1).fill(0);
    for (const p of parcels) {
      const on = p.cls > 0 && vis.has(p.id);
      batches[on ? p.cls : 0].addPath(p.path);
      if (on) counts[p.cls]++;
    }
    legend(counts);
  }

  function legend(counts) {
    const c = colors();
    $("pmap-legend").innerHTML = CLASSES.map((k) =>
      `<div class="plg"><i style="background:${c.cls[k.c]}"></i><span><b>${k.label}</b><br><span class="small muted">${k.desc}</span></span><b class="num">${counts[k.c].toLocaleString("en-US")}</b></div>`).join("") +
      `<div class="plg"><i style="background:${c.none}"></i><span class="small muted">Other homes, or hidden by the filters above</span><span></span></div>`;
  }

  function resize() {
    const r = canvas.getBoundingClientRect();
    dpr = window.devicePixelRatio || 1;
    W = r.width; H = r.height;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    render();
  }

  function fitCity() {
    if (!fit) return;
    const pad = 16;
    s = Math.min((W - pad * 2) / (fit.maxx - fit.minx), (H - pad * 2) / (fit.maxy - fit.miny));
    tx = (W - (fit.maxx - fit.minx) * s) / 2 - fit.minx * s;
    ty = (H - (fit.maxy - fit.miny) * s) / 2 - fit.miny * s;
    render();
  }

  function zoomAt(f, cx, cy) {
    const ns = Math.max(0.05, Math.min(12, s * f));
    f = ns / s;
    tx = cx - (cx - tx) * f; ty = cy - (cy - ty) * f; s = ns;
    render();
  }

  let raf = 0;
  function render() { if (!raf) raf = requestAnimationFrame(paint); }
  function paint() {
    raf = 0;
    if (!ctx) return;
    const c = colors();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = c.land; ctx.fillRect(0, 0, W, H);
    if (!loaded) return;
    ctx.setTransform(dpr * s, 0, 0, dpr * s, dpr * tx, dpr * ty);
    ctx.fillStyle = c.city; ctx.fill(cityPath);
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    ctx.strokeStyle = c.street;
    ctx.lineWidth = Math.max(5, 1.2 / s); ctx.stroke(streets.paths[0]);
    ctx.lineWidth = Math.max(9, 2 / s); ctx.stroke(streets.paths[1]);
    if (batches) for (let k = 0; k <= NCLS; k++) { ctx.fillStyle = k ? c.cls[k] : c.none; ctx.fill(batches[k]); }
    if (s > 0.35) { ctx.strokeStyle = c.edge; ctx.lineWidth = 0.6 / s; for (let k = 0; k <= NCLS; k++) if (batches) ctx.stroke(batches[k]); }
    ctx.strokeStyle = c.ink; ctx.lineWidth = 1.5 / s; ctx.stroke(cityPath);
    for (const [i, w] of [[hover, 2], [selected, 3]]) {
      if (i < 0) continue;
      ctx.lineWidth = w / s; ctx.strokeStyle = c.sel; ctx.stroke(parcels[i].path);
    }
    // street names when zoomed in, skipping ones that would overlap
    if ($("pmap-labels").checked && s > 0.55) {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.font = "600 12px " + getComputedStyle(document.body).fontFamily;
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      const taken = [];
      for (const l of labels) {
        const x = l.x * s + tx, y = l.y * s + ty;
        if (x < -50 || y < -20 || x > W + 50 || y > H + 20) continue;
        const w = ctx.measureText(l.name).width;
        if (w > l.len * s * 0.95) continue;
        const box = [x - w / 2 - 4, y - 9, x + w / 2 + 4, y + 9];
        if (taken.some((b) => !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]))) continue;
        taken.push(box);
        ctx.save(); ctx.translate(x, y); ctx.rotate(l.ang);
        ctx.lineWidth = 3; ctx.strokeStyle = c.paper; ctx.strokeText(l.name, 0, 0);
        ctx.fillStyle = c.ink; ctx.fillText(l.name, 0, 0);
        ctx.restore();
        if (taken.length > 90) break;
      }
    }
  }

  const rank = (c) => (c > 0 ? 100 - c : 0);   // where homes overlap (condos), the most actionable wins
  function inRing(pts, x, y) {
    let inside = false;
    for (let i = 0, j = pts.length - 2; i < pts.length; j = i, i += 2) {
      const xi = pts[i], yi = pts[i + 1], xj = pts[j], yj = pts[j + 1];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }
  function pick(px, py) {
    const x = (px - tx) / s, y = (py - ty) / s;
    const cand = grid.get(Math.floor(x / CELL) + "," + Math.floor(y / CELL)) || [];
    let best = -1;
    for (const i of cand) {
      const p = parcels[i];
      if (x < p.box[0] || x > p.box[2] || y < p.box[1] || y > p.box[3]) continue;
      if (p.rings.some((r) => inRing(r, x, y))) { if (best < 0 || rank(p.cls) > rank(parcels[best].cls)) best = i; }
    }
    return best;
  }

  function detail(i) {
    const el = $("pmap-detail");
    if (i < 0) { el.innerHTML = `<p class="small muted">Click a home on the map to see its details.</p>`; return; }
    const p = parcels[i];
    const r = p.id ? byId.get(p.id) : null;
    if (!r) { el.innerHTML = `<p class="small muted">No missing exemption was found for this home.</p>`; return; }
    const shown = view.includes(r);
    el.innerHTML = `<h3 class="pd-h">${esc(r.address)}</h3>
      <p class="small">${esc(r.owner)}${r.co_owner ? `<br>${esc(r.co_owner)}` : ""}</p>
      <p class="small muted">Mail: ${esc(r.mail) || "not on file"}</p>
      <div>${tagsHtml(r)}</div>
      <p class="small">${r.city_savings ? `City: about ${money(r.city_savings)}/yr` : ""}${r.city_savings && r.county_savings ? " · " : ""}${r.county_savings ? `County: about ${money(r.county_savings)}/yr` : ""}</p>
      ${shown ? "" : `<p class="small muted">Hidden in the list by the current filters.</p>`}
      <button type="button" class="quiet" id="pd-list" style="min-height:auto;padding:.3rem .8rem">Show in list</button>`;
    $("pd-list").addEventListener("click", () => { $("search").value = r.address; setTab("list"); filter(); });
  }

  function tip(i, px, py) {
    const t = $("pmap-tip");
    if (i < 0 || !parcels[i].id || !byId.get(parcels[i].id)) { t.hidden = true; return; }
    t.textContent = byId.get(parcels[i].id).address;
    t.hidden = false;
    t.style.left = Math.min(px + 12, W - t.offsetWidth - 4) + "px";
    t.style.top = Math.max(4, py - 32) + "px";
  }

  function wire() {
    canvas = $("pmap"); ctx = canvas.getContext("2d");
    new ResizeObserver(() => resize()).observe(canvas);
    const ptrs = new Map();
    let moved = 0, last = null, pinch = null;
    canvas.addEventListener("pointerdown", (e) => {
      canvas.setPointerCapture(e.pointerId); ptrs.set(e.pointerId, [e.offsetX, e.offsetY]); moved = 0; last = [e.offsetX, e.offsetY];
      if (ptrs.size === 2) { const [a, b] = [...ptrs.values()]; pinch = Math.hypot(a[0] - b[0], a[1] - b[1]); }
      canvas.classList.add("dragging");
    });
    canvas.addEventListener("pointermove", (e) => {
      if (!ptrs.has(e.pointerId)) {
        if (e.pointerType === "mouse" && loaded) { const i = pick(e.offsetX, e.offsetY); if (i !== hover) { hover = i; render(); } tip(i, e.offsetX, e.offsetY); }
        return;
      }
      ptrs.set(e.pointerId, [e.offsetX, e.offsetY]);
      if (ptrs.size === 2) {
        const [a, b] = [...ptrs.values()];
        const d = Math.hypot(a[0] - b[0], a[1] - b[1]);
        if (pinch) zoomAt(d / pinch, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
        pinch = d; moved += 10; return;
      }
      const dx = e.offsetX - last[0], dy = e.offsetY - last[1];
      moved += Math.abs(dx) + Math.abs(dy);
      tx += dx; ty += dy; last = [e.offsetX, e.offsetY]; render();
    });
    const up = (e) => {
      ptrs.delete(e.pointerId); if (ptrs.size < 2) pinch = null;
      if (!ptrs.size) canvas.classList.remove("dragging");
      if (e.type === "pointerup" && moved < 6 && loaded) { selected = pick(e.offsetX, e.offsetY); detail(selected); render(); }
      if (ptrs.size === 1) last = [...ptrs.values()][0];
    };
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);
    canvas.addEventListener("pointerleave", () => { if (hover >= 0) { hover = -1; render(); } $("pmap-tip").hidden = true; });
    canvas.addEventListener("wheel", (e) => { e.preventDefault(); zoomAt(Math.exp(-e.deltaY * 0.0015), e.offsetX, e.offsetY); }, { passive: false });
    canvas.addEventListener("keydown", (e) => {
      const k = { ArrowLeft: [40, 0], ArrowRight: [-40, 0], ArrowUp: [0, 40], ArrowDown: [0, -40] }[e.key];
      if (k) { tx += k[0]; ty += k[1]; render(); e.preventDefault(); }
      else if (e.key === "+" || e.key === "=") { zoomAt(1.4, W / 2, H / 2); e.preventDefault(); }
      else if (e.key === "-") { zoomAt(1 / 1.4, W / 2, H / 2); e.preventDefault(); }
    });
    $("pmap-in").addEventListener("click", () => zoomAt(1.5, W / 2, H / 2));
    $("pmap-out").addEventListener("click", () => zoomAt(1 / 1.5, W / 2, H / 2));
    $("pmap-fit").addEventListener("click", fitCity);
    $("pmap-labels").addEventListener("change", render);
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { rebatch(); render(); });
  }

  async function open() {
    if (!canvas) wire();
    resize();
    if (loaded || loading) { render(); return; }
    loading = true;
    $("pmap-status").hidden = false;
    $("pmap-status").textContent = "Loading the map (about half a megabyte)…";
    const d = await call("map");
    loading = false;
    if (d.status !== "ok") { $("pmap-status").textContent = "The map couldn't be loaded. Try again in a minute."; return; }
    build(d);
    $("pmap-status").hidden = true;
    rebatch(); fitCity(); detail(-1);
  }

  return { open, refilter: () => { if (loaded) { rebatch(); render(); if (selected >= 0) detail(selected); } } };
})();

function setTab(which) {
  const map = which === "map";
  $("tab-list").setAttribute("aria-selected", String(!map));
  $("tab-map").setAttribute("aria-selected", String(map));
  $("list-panel").hidden = map;
  $("map-panel").hidden = !map;
  if (map) Map_.open();
}

$("signin-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("signin-error").textContent = "";
  const btn = e.target.querySelector("button");
  btn.disabled = true;
  const { error } = await sb.auth.signInWithPassword({ email: $("email").value.trim(), password: $("password").value });
  btn.disabled = false;
  if (error) { $("signin-error").textContent = "That email and password didn't match an approved account."; return; }
  $("password").value = "";
  load();
});
for (const id of ["signout", "signout2"]) $(id).addEventListener("click", async () => { await sb.auth.signOut(); rows = []; show("signin-view"); location.reload(); });
$("groups").addEventListener("change", filter);
$("search").addEventListener("input", filter);
$("sort").addEventListener("change", filter);
$("prev").addEventListener("click", () => { page--; draw(); });
$("next").addEventListener("click", () => { page++; draw(); });
$("export").addEventListener("click", exportCsv);
$("tab-list").addEventListener("click", () => setTab("list"));
$("tab-map").addEventListener("click", () => setTab("map"));

load();
