/* Control Panel front end — no build step, no dependencies.
   One page, several sidebar-switched sections: Overview, Arr fleet,
   Containers, Maintenance, Console (search-any-of-N-commands runner),
   and Access (quicklinks). All share this one file, the same log panel,
   and the same sidebar container-status list. */

const ICONS = {
  bolt: '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>',
  database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0018 0V5"/><path d="M3 12a9 3 0 0018 0"/>',
  broom: '<path d="M9.59 4.59A2 2 0 1111 8H2"/><path d="M12.59 11.59A2 2 0 1114 15H2"/><path d="M17.73 7.73A2.5 2.5 0 1119.5 12H2"/>',
  restart: '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>',
};

function svg(name) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ""}</svg>`;
}

const PRIMARY_ACTIONS = [
  {
    id: "kometa-run",
    title: "Run Kometa now",
    desc: "Trigger an immediate collections, metadata, and overlays pass, bypassing the 05:00 schedule.",
    endpoint: "/api/kometa/run",
    icon: "bolt",
    extraHtml: `
      <div class="lib-picker">
        <span class="lib-hint">Libraries — none checked runs all</span>
        <div class="lib-options" id="kometa-lib-options">Loading libraries…</div>
      </div>
    `,
  },
  {
    id: "plex-scan",
    title: "Scan for new files",
    desc: "Refresh every Plex library section to pick up files that landed since the last scan.",
    endpoint: "/api/plex/scan",
    icon: "search",
  },
  {
    id: "plex-empty-trash",
    title: "Empty trash",
    desc: "Permanently remove items already deleted from disk, across every Plex library.",
    endpoint: "/api/plex/empty-trash",
    icon: "trash",
  },
  {
    id: "plex-optimize-db",
    title: "Optimize database",
    desc: "Run Plex's own database optimization task — clears bloat after large library changes.",
    endpoint: "/api/plex/optimize-db",
    icon: "database",
  },
  {
    id: "plex-clean-bundles",
    title: "Clean old bundles",
    desc: "Remove metadata bundles Plex no longer needs, freeing disk space.",
    endpoint: "/api/plex/clean-bundles",
    icon: "broom",
  },
];

const ARR_APPS = [
  { id: "radarr", label: "Radarr", port: 7878, queue: true },
  { id: "sonarr", label: "Sonarr", port: 8989, queue: true },
];

/* Every service's own web UI. Port list mirrors the "Bringing the stack
   up" table in README.md; `id` matches the container name so status dots
   can reuse /api/status's data. Torrent/debrid-era entries (Zilean,
   Decypharr x2, Zurg, Byparr) were removed with those services in
   v11.0.0 — nothing left in this stack still listens on those ports. */
const QUICK_LINKS = [
  { id: "plex", label: "Plex", port: 32400, path: "/web" },
  { id: "prowlarr", label: "Prowlarr", port: 9696 },
  { id: "radarr", label: "Radarr", port: 7878 },
  { id: "sonarr", label: "Sonarr", port: 8989 },
  { id: "nzbdav", label: "NzbDAV", port: 3001 },
  { id: "seerr", label: "Seerr", port: 5055 },
  { id: "tautulli", label: "Tautulli", port: 8182 },
  { id: "bazarr", label: "Bazarr", port: 6767 },
  { id: "cleanuparr", label: "Cleanuparr", port: 11011 },
  { id: "neutarr", label: "NeutArr", port: 9705 },
];

function buildQuickLinks() {
  const container = document.getElementById("quicklinks");
  container.innerHTML = QUICK_LINKS.map((svc) => {
    const url = `${location.protocol}//${location.hostname}:${svc.port}${svc.path || ""}`;
    return `<a class="quicklink" href="${url}" target="_blank" rel="noopener"><span class="dot unknown" id="qdot-${svc.id}"></span>${escapeHtml(svc.label)}</a>`;
  }).join("");
}

const MAX_LOG_LINES = 100;

function logLine(kind, text) {
  const body = document.getElementById("log-body");
  const t = new Date().toLocaleTimeString([], { hour12: false });
  const glyph = kind === "ok" ? "✓" : kind === "err" ? "✕" : "›";
  const el = document.createElement("div");
  el.className = `log-line ${kind}`;
  el.innerHTML = `<span class="t">${t}</span> <span class="g">${glyph}</span> ${escapeHtml(text)}`;
  body.appendChild(el);
  while (body.children.length > MAX_LOG_LINES) body.removeChild(body.firstChild);
  body.scrollTop = body.scrollHeight;
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s ?? "";
  return div.innerHTML;
}

async function postAction(url, body) {
  const opts = { method: "POST" };
  if (body !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  let data = null;
  try {
    data = await res.json();
  } catch (_) {
    /* no body */
  }
  if (!res.ok) {
    const msg = data?.detail?.message || data?.message || `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

function setStatusLine(el, state, text) {
  el.textContent = text;
  el.className = el.className.replace(/state-\S+/g, "").trim();
  el.classList.add(`state-${state}`);
}

/* ---------- Sidebar navigation: swap page-sections, no routing lib ---------- */
const PAGE_META = {
  overview: { title: "Overview", sub: "System vitals and rapid actions" },
  arr: { title: "Arr fleet", sub: "Radarr and Sonarr — every command, one click away" },
  containers: { title: "Containers", sub: "Every container in this compose project, live from Docker" },
  maintenance: { title: "Maintenance", sub: "Poster sync and whole-stack restart" },
  console: { title: "Operator console", sub: "Search-any-command runner for the full stack-* manifest" },
  access: { title: "Access", sub: "Every service's own web UI" },
};

function showPage(name) {
  if (!PAGE_META[name]) name = "overview";
  document.querySelectorAll(".page-section").forEach((el) => {
    el.hidden = el.id !== `page-${name}`;
  });
  document.querySelectorAll(".sidebar-nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.page === name);
  });
  document.getElementById("page-title").textContent = PAGE_META[name].title;
  document.getElementById("page-subtitle").textContent = PAGE_META[name].sub;
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
}

function wireSidebarNav() {
  document.querySelectorAll(".sidebar-nav-item[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => showPage(btn.dataset.page));
  });
  window.addEventListener("hashchange", () => showPage((location.hash || "").slice(1)));
  showPage((location.hash || "").slice(1) || "overview");
}

/* ---------- Primary action cards ---------- */
function buildPrimaryGrid() {
  const grid = document.getElementById("primary-grid");
  for (const action of PRIMARY_ACTIONS) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card-icon">${svg(action.icon)}</div>
      <div class="card-title">${action.title}</div>
      <div class="card-desc">${action.desc}</div>
      ${action.extraHtml || ""}
      <button class="btn-primary" type="button">Run</button>
      <div class="status-line" id="status-${action.id}">—</div>
    `;
    const btn = card.querySelector("button");
    const status = card.querySelector(".status-line");
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      setStatusLine(status, "pending", "Running…");
      logLine("pending", `${action.title} — requested`);
      try {
        const body = action.id === "kometa-run" ? { libraries: selectedKometaLibraries() } : undefined;
        const data = await postAction(action.endpoint, body);
        setStatusLine(status, "success", data.message);
        logLine("ok", `${action.title} — ${data.message}`);
      } catch (e) {
        setStatusLine(status, "error", e.message);
        logLine("err", `${action.title} — ${e.message}`);
      } finally {
        btn.disabled = false;
      }
    });
    grid.appendChild(card);
  }
  loadKometaLibraries();
}

function selectedKometaLibraries() {
  const boxes = document.querySelectorAll("#kometa-lib-options input[type=checkbox]:checked");
  return Array.from(boxes).map((b) => b.value);
}

async function loadKometaLibraries() {
  const el = document.getElementById("kometa-lib-options");
  if (!el) return;
  try {
    const res = await fetch("/api/plex/libraries");
    const libs = await res.json();
    if (!Array.isArray(libs) || libs.length === 0) {
      el.textContent = "No libraries found.";
      return;
    }
    el.innerHTML = libs
      .map(
        (lib) => `
        <label class="lib-check">
          <input type="checkbox" value="${escapeHtml(lib.title)}">
          ${escapeHtml(lib.title)}
        </label>`
      )
      .join("");
  } catch (e) {
    el.textContent = "Couldn't load libraries — will run all.";
  }
}

/* =====================================================================
   Generic inline result rendering — used by every arr-card view button,
   the fleet-wide toolbar, and (indirectly) the manual-import panel.
   Turns whatever shape a stack-* GET returns (raw array, or the {ok,
   message, ...extra} shape ok() wraps everything else in) into real
   tables/definition-lists instead of a JSON dump, recursing one level
   into nested dicts (e.g. queue-status's {queues: {radarr: {...}}}) so
   the common two-deep API shapes in this file render as real tables
   too, not one big stringified blob.
   ===================================================================== */
const TABLE_COLUMN_PRIORITY = ["title", "name", "series", "episode", "label", "status", "message"];

function renderKv(el, obj) {
  const dl = document.createElement("dl");
  dl.className = "kv-grid";
  for (const key of Object.keys(obj)) {
    const v = obj[key];
    const dt = document.createElement("dt");
    dt.textContent = key;
    const dd = document.createElement("dd");
    dd.textContent = v && typeof v === "object" ? JSON.stringify(v) : String(v);
    dl.appendChild(dt);
    dl.appendChild(dd);
  }
  el.appendChild(dl);
}

function renderTable(el, rows) {
  if (!rows.length) {
    el.innerHTML += `<div class="hint">No results.</div>`;
    return;
  }
  if (typeof rows[0] !== "object" || rows[0] === null) {
    const ul = document.createElement("ul");
    ul.className = "result-list";
    for (const v of rows) {
      const li = document.createElement("li");
      li.textContent = String(v);
      ul.appendChild(li);
    }
    el.appendChild(ul);
    return;
  }
  const keySet = new Set();
  for (const row of rows) for (const k of Object.keys(row || {})) keySet.add(k);
  const keys = [
    ...TABLE_COLUMN_PRIORITY.filter((k) => keySet.has(k)),
    ...[...keySet].filter((k) => !TABLE_COLUMN_PRIORITY.includes(k)).sort(),
  ];
  const wrap = document.createElement("div");
  wrap.className = "result-table-wrap";
  const table = document.createElement("table");
  table.className = "result-table";
  const thead = document.createElement("thead");
  thead.innerHTML = `<tr>${keys.map((k) => `<th>${escapeHtml(k)}</th>`).join("")}</tr>`;
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = keys
      .map((k) => {
        const v = (row || {})[k];
        const text = v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);
        return `<td class="${typeof v === "number" ? "num" : ""}">${escapeHtml(text)}</td>`;
      })
      .join("");
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  el.appendChild(wrap);
}

function resultSubhead(el, key) {
  const h = document.createElement("div");
  h.className = "result-subhead";
  h.textContent = key;
  el.appendChild(h);
}

function renderValue(el, key, value, depth) {
  if (value === null || value === undefined || value === "") return false;
  if (Array.isArray(value)) {
    if (!value.length) return false;
    resultSubhead(el, key);
    renderTable(el, value);
    return true;
  }
  if (typeof value === "object") {
    if (!Object.keys(value).length) return false;
    resultSubhead(el, key);
    if (depth >= 2) {
      renderKv(el, value);
      return true;
    }
    let any = false;
    for (const k of Object.keys(value).sort()) {
      any = renderValue(el, k, value[k], depth + 1) || any;
    }
    if (!any) el.innerHTML += `<div class="hint">Empty.</div>`;
    return true;
  }
  if (typeof value === "string" && value.includes("\n")) {
    resultSubhead(el, key);
    const pre = document.createElement("pre");
    pre.className = "log-block";
    pre.textContent = value;
    el.appendChild(pre);
    return true;
  }
  renderKv(el, { [key]: value });
  return true;
}

function renderResultPanel(el, data) {
  el.innerHTML = "";
  if (Array.isArray(data)) {
    renderTable(el, data);
    return;
  }
  data = data || {};
  let any = false;
  if (data.message) {
    const p = document.createElement("p");
    p.className = "result-summary";
    p.textContent = data.message;
    el.appendChild(p);
    any = true;
  }
  for (const key of Object.keys(data).sort()) {
    if (key === "message" || key === "ok" || key === "time") continue;
    any = renderValue(el, key, data[key], 0) || any;
  }
  if (!any) el.innerHTML = `<div class="hint">No data.</div>`;
}

async function fetchAndRender(el, method, url, body) {
  el.hidden = false;
  el.innerHTML = `<div class="hint">Loading…</div>`;
  const opts = { method };
  if (body !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  const raw = await res.text();
  let parsed = null;
  if (raw) {
    try {
      parsed = JSON.parse(raw);
    } catch (_) {
      parsed = null;
    }
  }
  if (!res.ok) {
    const msg = (parsed && (parsed.detail?.message || parsed.message)) || raw || `Request failed (${res.status})`;
    el.innerHTML = `<div class="hint error">${escapeHtml(msg)}</div>`;
    throw new Error(msg);
  }
  const payload = parsed && parsed.detail && typeof parsed.detail === "object" ? parsed.detail : parsed;
  renderResultPanel(el, payload);
  return payload;
}

/* ---------- Arr fleet: fleet-wide toolbar ---------- */
const ARR_FLEET_ACTIONS = [
  { id: "queue-status", label: "Queue status", path: "/api/queue-status" },
  { id: "queue-errors", label: "Queue errors", path: "/api/arr/queue-errors" },
  { id: "command-queue-summary", label: "Command queue summary", path: "/api/arr/command-queue-summary" },
  { id: "backlog-status", label: "Backlog ETA", path: "/api/backlog-status" },
  { id: "prowlarr-indexers", label: "Prowlarr indexers", path: "/api/prowlarr/indexers" },
];

function buildArrFleetToolbar() {
  const bar = document.getElementById("arr-fleet-toolbar");
  const panel = document.getElementById("arr-fleet-panel");
  if (!bar || !panel) return;
  bar.innerHTML = ARR_FLEET_ACTIONS.map((a) => `<button class="btn-ghost" data-fleet="${a.id}" type="button">${a.label}</button>`).join("");
  bar.querySelectorAll("[data-fleet]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const wasOpen = btn.classList.contains("active") && !panel.hidden;
      bar.querySelectorAll("[data-fleet]").forEach((b) => b.classList.remove("active"));
      if (wasOpen) {
        panel.hidden = true;
        return;
      }
      btn.classList.add("active");
      const action = ARR_FLEET_ACTIONS.find((a) => a.id === btn.dataset.fleet);
      logLine("pending", `${action.label} — requested`);
      try {
        await fetchAndRender(panel, "GET", action.path);
        logLine("ok", `${action.label} — loaded`);
      } catch (e) {
        logLine("err", `${action.label} — ${e.message}`);
      }
    });
  });
}

/* ---------- Arr fleet: per-app cards ---------- */
const ARR_VIEWS = [
  { id: "backlog", label: "Backlog", path: (id) => `/api/arr/${id}/command-backlog` },
  { id: "missing-aired", label: "Missing aired", path: (id) => `/api/arr/${id}/missing-aired` },
  { id: "cutoff-unmet", label: "Cutoff unmet", path: (id) => `/api/arr/${id}/cutoff-unmet?limit=25` },
  { id: "recently-added", label: "Recently added", path: (id) => `/api/arr/${id}/recently-added?limit=15` },
  { id: "import-lists", label: "Import lists", path: (id) => `/api/arr/${id}/import-lists` },
  { id: "logs", label: "Logs", path: (id) => `/api/arr/${id}/logs?lines=150` },
];

function buildArrFleet() {
  const wrap = document.getElementById("arr-fleet");
  if (!wrap) return;
  for (const app of ARR_APPS) {
    const openUrl = `${location.protocol}//${location.hostname}:${app.port}`;
    const card = document.createElement("div");
    card.className = "arr-card";
    card.innerHTML = `
      <div class="arr-card-head">
        <div class="arr-card-name"><span class="dot unknown" id="arr-dot-${app.id}"></span>${app.label}</div>
        <a class="arr-card-link" href="${openUrl}" target="_blank" rel="noopener">open UI ↗</a>
        <div class="arr-card-status" id="arr-status-${app.id}">—</div>
      </div>
      <form class="arr-card-search" data-app="${app.id}">
        <input type="search" placeholder="Search ${app.label}…" aria-label="Search ${app.label}" required>
        <button class="btn-ghost" type="submit">Search</button>
      </form>
      <div class="arr-actions-row">
        <span class="arr-actions-row-label">Run</span>
        <button class="btn-primary" data-action="rss-sync" type="button">RSS sync</button>
        <button class="btn-primary" data-action="search-missing" type="button">Search missing</button>
        ${app.queue ? `<button class="btn-ghost" data-unstick type="button">Unstick</button>` : ""}
        ${app.queue ? `<button class="btn-ghost" data-unstick-importing type="button">Unstick importing</button>` : ""}
      </div>
      <div class="arr-actions-row">
        <span class="arr-actions-row-label">View</span>
        ${ARR_VIEWS.map((v) => `<button class="btn-ghost" data-view="${v.id}" type="button">${v.label}</button>`).join("")}
        ${app.queue ? `<button class="btn-ghost" data-view="manual-import" type="button">Manual import</button>` : ""}
      </div>
      <div class="arr-card-panel result-scroll" id="arr-panel-${app.id}" hidden></div>
    `;
    wrap.appendChild(card);

    const status = card.querySelector(".arr-card-status");
    const panel = card.querySelector(`#arr-panel-${app.id}`);

    card.querySelectorAll("[data-action]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const action = btn.dataset.action;
        const label = action === "rss-sync" ? "RSS sync" : "Search missing";
        card.querySelectorAll("[data-action]").forEach((b) => (b.disabled = true));
        setStatusLine(status, "pending", `${label}…`);
        logLine("pending", `${app.label} ${label} — requested`);
        try {
          const data = await postAction(`/api/arr/${app.id}/${action}`);
          setStatusLine(status, "success", data.message);
          logLine("ok", `${app.label} ${label} — ${data.message}`);
        } catch (e) {
          setStatusLine(status, "error", e.message);
          logLine("err", `${app.label} ${label} — ${e.message}`);
        } finally {
          card.querySelectorAll("[data-action]").forEach((b) => (b.disabled = false));
        }
      });
    });

    setupUnstick(app, card, status);
    if (app.queue) setupUnstickImporting(app, card, status);

    const searchForm = card.querySelector(".arr-card-search");
    searchForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const input = searchForm.querySelector("input");
      const term = input.value.trim();
      if (!term) return;
      window.open(`${openUrl}/add/new?term=${encodeURIComponent(term)}`, "_blank", "noopener");
      logLine("ok", `${app.label} search — opened "${term}" in a new tab`);
      input.value = "";
    });

    card.querySelectorAll("[data-view]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const wasOpen = btn.classList.contains("active") && !panel.hidden;
        card.querySelectorAll("[data-view]").forEach((b) => b.classList.remove("active"));
        if (wasOpen) {
          panel.hidden = true;
          return;
        }
        btn.classList.add("active");
        if (btn.dataset.view === "manual-import") {
          await loadManualImportCandidates(app, panel);
          return;
        }
        const view = ARR_VIEWS.find((v) => v.id === btn.dataset.view);
        logLine("pending", `${app.label} ${view.label} — requested`);
        try {
          await fetchAndRender(panel, "GET", view.path(app.id));
          logLine("ok", `${app.label} ${view.label} — loaded`);
        } catch (e) {
          logLine("err", `${app.label} ${view.label} — ${e.message}`);
        }
      });
    });
  }
}

/* ---------- Unstick: sweep every stuck (warning/error) queue item ---------- */
function setupUnstick(app, card, status) {
  const btn = card.querySelector("[data-unstick]");
  if (!btn) return;
  armButton(btn, "Unstick", "Confirm — removes + blocklists", async () => {
    btn.disabled = true;
    setStatusLine(status, "pending", "Unsticking…");
    logLine("pending", `${app.label} unstick — requested`);
    try {
      const data = await postAction(`/api/arr/${app.id}/unstick`);
      setStatusLine(status, "success", data.message);
      logLine("ok", `${app.label} unstick — ${data.message}`);
    } catch (e) {
      setStatusLine(status, "error", e.message);
      logLine("err", `${app.label} unstick — ${e.message}`);
    } finally {
      btn.disabled = false;
    }
  });
}

/* ---------- Unstick importing: force-verify + clear items stuck mid-import ---------- */
function setupUnstickImporting(app, card, status) {
  const btn = card.querySelector("[data-unstick-importing]");
  if (!btn) return;
  armButton(btn, "Unstick importing", "Confirm — verifies + clears", async () => {
    btn.disabled = true;
    setStatusLine(status, "pending", "Checking importing downloads…");
    logLine("pending", `${app.label} unstick importing — requested`);
    try {
      const data = await postAction(`/api/arr/${app.id}/unstick-importing`);
      setStatusLine(status, "success", data.message);
      logLine("ok", `${app.label} unstick importing — ${data.message}`);
    } catch (e) {
      setStatusLine(status, "error", e.message);
      logLine("err", `${app.label} unstick importing — ${e.message}`);
    } finally {
      btn.disabled = false;
    }
  });
}

/* ---------- Manual import panel ---------- */
async function loadManualImportCandidates(app, panel) {
  panel.hidden = false;
  panel.innerHTML = `<div class="hint">Scanning stuck downloads for importable files…</div>`;
  logLine("pending", `${app.label} manual import — scanning`);
  try {
    const res = await fetch(`/api/arr/${app.id}/manual-import`);
    const items = await res.json();
    if (!res.ok) throw new Error(items?.detail?.message || items?.message || `Scan failed (${res.status})`);
    renderManualImportCandidates(app, panel, items);
    logLine("ok", `${app.label} manual import — found ${items.length} importable file${items.length === 1 ? "" : "s"}`);
  } catch (e) {
    panel.innerHTML = `<div class="hint error">${escapeHtml(e.message)}</div>`;
    logLine("err", `${app.label} manual import — ${e.message}`);
  }
}

function renderManualImportCandidates(app, panel, items) {
  if (!items.length) {
    panel.innerHTML = `<div class="hint">No importable files found among currently stuck downloads.</div>`;
    return;
  }
  panel.innerHTML = items
    .map((item, i) => {
      const meta = [item.quality, item.release_group, item.size].filter(Boolean).join(" · ");
      const match = [item.match_title, item.episode].filter(Boolean).join(" — ");
      const rejections = item.rejections.length
        ? `<span class="result-rejections" title="${escapeHtml(item.rejections.join("; "))}">⚠ ${item.rejections.length} rejection${item.rejections.length === 1 ? "" : "s"}</span>`
        : "";
      return `
        <div class="result-row">
          <div class="result-row-main">
            <span class="result-title">${escapeHtml(match || item.name || "Unknown")}</span>
            ${rejections}
            <span class="result-meta">${escapeHtml(meta)}</span>
          </div>
          <div class="result-row-actions">
            <code title="${escapeHtml(item.relative_path || "")}">${escapeHtml(item.relative_path || "")}</code>
            <button class="btn-ghost import-run" type="button" data-idx="${i}">Import</button>
          </div>
          <div class="status-line result-row-status" id="import-status-${app.id}-${i}">—</div>
        </div>`;
    })
    .join("");
  panel.querySelectorAll("button.import-run").forEach((btn) => {
    const item = items[Number(btn.dataset.idx)];
    const status = panel.querySelector(`#import-status-${app.id}-${btn.dataset.idx}`);
    armButton(btn, "Import", "Confirm import?", async () => {
      btn.disabled = true;
      setStatusLine(status, "pending", "Importing…");
      logLine("pending", `${app.label} manual import — "${item.name}" requested`);
      try {
        const data = await postAction(`/api/arr/${app.id}/manual-import`, item.file);
        setStatusLine(status, "success", data.message);
        logLine("ok", `${app.label} manual import — ${data.message}`);
      } catch (e) {
        setStatusLine(status, "error", e.message);
        logLine("err", `${app.label} manual import — ${e.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  });
}

/* ---------- Container grid: full state/health/image/CPU/mem + controls,
   discovered live from Docker via /api/containers rather than a fixed
   list, so a service added to compose shows up here with no code change. */
function fmtPercent(v) {
  return v === null || v === undefined ? "—" : `${v.toFixed(1)}%`;
}

function fmtMb(v) {
  if (v === null || v === undefined) return "—";
  return v >= 1024 ? `${(v / 1024).toFixed(2)} GB` : `${v.toFixed(0)} MB`;
}

function containerCardHtml(c, hits) {
  const stateClass = c.state === "running" ? (c.health === "unhealthy" ? "down" : c.health === "starting" ? "unknown" : "up") : c.state === "exited" || c.state === "created" ? "down" : "unknown";
  const healthLabel = c.state !== "running" ? c.state : c.health ? c.health : "running";
  const cpuPct = c.cpu_percent === null || c.cpu_percent === undefined ? null : Math.min(c.cpu_percent, 100);
  const memPct = c.mem_percent === null || c.mem_percent === undefined ? null : Math.min(c.mem_percent, 100);
  const hit = hits && hits.counts[c.label];
  const hitRow = hit === undefined ? "" : `
        <div class="metric api-hits-metric${hits.justTicked.has(c.label) ? " api-hits-tick" : ""}" title="API calls made to ${escapeHtml(c.label)} since this panel started">
          <span class="metric-label">API</span>
          <span class="api-hits-dot"></span>
          <span class="metric-value api-hits-value">${hit.toLocaleString()}</span>
        </div>`;
  return `
    <div class="container-card" data-name="${escapeHtml(c.name)}" data-state="${escapeHtml(c.state)}">
      <div class="container-card-head">
        <span class="dot ${stateClass}"></span>
        <span class="container-name">${escapeHtml(c.label)}${c.note ? `<span class="chip-sub">${escapeHtml(c.note)}</span>` : ""}</span>
        <span class="container-health">${escapeHtml(healthLabel)}</span>
      </div>
      <div class="container-image" title="${escapeHtml(c.image)}">${escapeHtml(c.image)}</div>
      <div class="container-metrics">
        <div class="metric">
          <span class="metric-label">CPU</span>
          <div class="stat-bar small"><div class="stat-bar-fill" style="width:${cpuPct ?? 0}%"></div></div>
          <span class="metric-value">${fmtPercent(c.cpu_percent)}</span>
        </div>
        <div class="metric">
          <span class="metric-label">MEM</span>
          <div class="stat-bar small"><div class="stat-bar-fill" style="width:${memPct ?? 0}%"></div></div>
          <span class="metric-value">${fmtMb(c.mem_used_mb)}</span>
        </div>${hitRow}
      </div>
      <div class="container-actions">
        <button class="btn-icon" type="button" data-act="start" title="Start" aria-label="Start ${escapeHtml(c.label)}" ${c.state === "running" ? "disabled" : ""}>${svg("start")}</button>
        <button class="btn-icon" type="button" data-act="stop" title="Stop" aria-label="Stop ${escapeHtml(c.label)}" ${c.is_self || c.state !== "running" ? "disabled" : ""}>${svg("stop")}</button>
        <button class="btn-icon" type="button" data-act="restart" title="Restart" aria-label="Restart ${escapeHtml(c.label)}" ${c.is_self ? "disabled" : ""}>${svg("restart")}</button>
      </div>
    </div>`;
}

const STOP_ICON = '<rect x="6" y="6" width="12" height="12" rx="2"/>';
const START_ICON = '<polygon points="6 3 20 12 6 21 6 3"/>';
ICONS.stop = STOP_ICON;
ICONS.start = START_ICON;

function wireContainerCard(card, c) {
  const startBtn = card.querySelector('[data-act="start"]');
  const stopBtn = card.querySelector('[data-act="stop"]');
  const restartBtn = card.querySelector('[data-act="restart"]');

  const fire = async (btn, action, label) => {
    btn.disabled = true;
    btn.classList.add("spinning");
    logLine("pending", `${c.label} — ${label} requested`);
    try {
      const data = await postAction(`/api/container/${c.name}/${action}`);
      logLine("ok", `${c.label} — ${data.message}`);
    } catch (e) {
      logLine("err", `${c.label} — ${e.message}`);
    } finally {
      btn.classList.remove("spinning");
      refreshContainerGrid();
    }
  };

  if (!startBtn.disabled) startBtn.addEventListener("click", () => fire(startBtn, "start", "start"));
  if (!restartBtn.disabled) restartBtn.addEventListener("click", () => fire(restartBtn, "restart", "restart"));
  if (!stopBtn.disabled) armIconButton(stopBtn, "stop", () => fire(stopBtn, "stop", "stop"));
}

let containerGridBuilt = false;
let previousHitCounts = {};

async function fetchHitCounts() {
  try {
    const res = await fetch("/api/api-hit-counts");
    if (!res.ok) return null;
    const { counts } = await res.json();
    const justTicked = new Set(
      Object.keys(counts).filter((label) => counts[label] > (previousHitCounts[label] || 0))
    );
    previousHitCounts = counts;
    return { counts, justTicked };
  } catch (e) {
    return null;
  }
}

async function refreshContainerGrid() {
  const grid = document.getElementById("container-grid");
  let data;
  try {
    const res = await fetch("/api/containers");
    data = await res.json();
    if (!res.ok) throw new Error("Could not load containers");
  } catch (e) {
    if (!containerGridBuilt) grid.innerHTML = `<div class="hint error">Could not load containers.</div>`;
    return;
  }
  const hits = await fetchHitCounts();
  const up = data.filter((c) => c.state === "running" && (c.health === "healthy" || !c.health)).length;
  const containersValue = document.getElementById("stat-containers-value");
  const containersSub = document.getElementById("stat-containers-sub");
  if (containersValue) containersValue.textContent = `${up} / ${data.length}`;
  if (containersSub) containersSub.textContent = up === data.length ? "all healthy" : `${data.length - up} need attention`;

  grid.innerHTML = data.map((c) => containerCardHtml(c, hits)).join("");
  grid.querySelectorAll(".container-card").forEach((card) => {
    const c = data.find((x) => x.name === card.dataset.name);
    wireContainerCard(card, c);
  });
  containerGridBuilt = true;

  renderSidebarStatus(data);
}

/* ---------- Sidebar status list: every container, always visible,
   fed off the same /api/containers poll the grid already does. ---------- */
function renderSidebarStatus(data) {
  const list = document.getElementById("sidebar-status-list");
  if (!list) return;
  const sorted = [...data].sort((a, b) => a.label.localeCompare(b.label));
  list.innerHTML = sorted
    .map((c) => {
      const cls = c.state !== "running" ? "down" : c.health === "unhealthy" ? "down" : c.health === "starting" ? "unknown" : "up";
      return `<li><span class="dot ${cls}"></span><span class="name" title="${escapeHtml(c.label)}">${escapeHtml(c.label)}</span></li>`;
    })
    .join("");
}

/* ---------- Arm/confirm guard for real, one-shot side effects ---------- */
function armButton(btn, idleLabel, armedLabel, onConfirm) {
  let armed = false;
  let disarmTimer = null;

  const disarm = () => {
    armed = false;
    btn.textContent = idleLabel;
    btn.classList.remove("armed");
  };

  btn.textContent = idleLabel;
  btn.addEventListener("click", async () => {
    if (!armed) {
      armed = true;
      btn.textContent = armedLabel;
      btn.classList.add("armed");
      disarmTimer = setTimeout(disarm, 5000);
      return;
    }
    clearTimeout(disarmTimer);
    disarm();
    await onConfirm();
  });
}

function armIconButton(btn, iconName, onConfirm) {
  let armed = false;
  let disarmTimer = null;
  btn.innerHTML = svg(iconName);
  const disarm = () => {
    armed = false;
    btn.classList.remove("armed");
    btn.title = btn.dataset.idleTitle || btn.title;
    btn.setAttribute("aria-label", btn.dataset.idleLabel || btn.getAttribute("aria-label"));
  };
  btn.dataset.idleTitle = btn.title;
  btn.dataset.idleLabel = btn.getAttribute("aria-label") || btn.title;
  btn.addEventListener("click", async () => {
    if (!armed) {
      armed = true;
      btn.classList.add("armed");
      btn.title = "Click again to confirm";
      btn.setAttribute("aria-label", "Click again to confirm");
      disarmTimer = setTimeout(disarm, 5000);
      return;
    }
    clearTimeout(disarmTimer);
    disarm();
    await onConfirm();
  });
}

function buildPlexUpdateCheck() {
  const btn = document.getElementById("plex-check-updates");
  const val = document.getElementById("stat-plex-value");
  const sub = document.getElementById("stat-plex-sub");
  const check = async () => {
    btn.disabled = true;
    try {
      const res = await fetch("/api/plex/updates");
      const d = await res.json();
      if (!res.ok) throw new Error(d?.detail?.message || "Could not check Plex updates.");
      val.textContent = d.running_version || "—";
      sub.textContent = d.update_available ? `Update available: ${d.releases[0]?.version}` : "Up to date on its current channel.";
      sub.classList.toggle("stat-sub-warn", d.update_available);
      logLine(d.update_available ? "pending" : "ok", `Plex updates — ${sub.textContent}`);
    } catch (e) {
      sub.textContent = e.message;
      logLine("err", `Plex updates — ${e.message}`);
    } finally {
      btn.disabled = false;
    }
  };
  btn.addEventListener("click", check);
  check();
}

/* ---------- Danger zone: restart everything ---------- */
function buildDangerZone() {
  const btn = document.getElementById("restart-all-btn");
  const status = document.getElementById("status-restart-all");

  armButton(btn, "Restart everything", "Click again to confirm", async () => {
    btn.disabled = true;
    setStatusLine(status, "pending", "Restarting…");
    logLine("pending", "Restart entire stack — requested");
    try {
      const data = await postAction("/api/stack/restart-all");
      setStatusLine(status, "success", data.message);
      logLine("ok", `Restart entire stack — ${data.message}`);
      refreshStatus();
    } catch (e) {
      setStatusLine(status, "error", e.message);
      logLine("err", `Restart entire stack — ${e.message}`);
    } finally {
      btn.disabled = false;
    }
  });
}

/* ---------- Status dots + sidebar connection state ---------- */
function setHudConn(up) {
  const dot = document.getElementById("hud-conn-dot");
  const label = document.getElementById("hud-conn-label");
  if (!dot || !label) return;
  dot.classList.remove("up", "down");
  dot.classList.add(up ? "up" : "down");
  label.textContent = up ? "connected" : "disconnected";
}

async function refreshStatus() {
  let data;
  try {
    const res = await fetch("/api/status");
    data = await res.json();
    setHudConn(true);
  } catch (_) {
    setHudConn(false);
    return;
  }
  for (const [name, info] of Object.entries(data)) {
    const isUp = info.state === "running" && (info.health === "healthy" || info.health == null);
    const isStarting = info.state === "running" && info.health === "starting";
    const stateClass = isUp ? "up" : isStarting ? "unknown" : "down";

    const dot = document.getElementById(`arr-dot-${name}`);
    if (dot) {
      dot.classList.remove("up", "down", "unknown");
      dot.classList.add(stateClass);
    }
    const qdot = document.getElementById(`qdot-${name}`);
    if (qdot) {
      qdot.classList.remove("up", "down", "unknown");
      qdot.classList.add(stateClass);
    }
  }
}

/* ---------- Clock + session uptime ---------- */
const sessionStart = Date.now();

function tickClock() {
  const el = document.getElementById("clock");
  el.textContent = new Date().toLocaleString([], {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
  const elapsed = Math.floor((Date.now() - sessionStart) / 1000);
  const h = String(Math.floor(elapsed / 3600)).padStart(2, "0");
  const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, "0");
  const s = String(elapsed % 60).padStart(2, "0");
  const up = document.getElementById("uptime");
  if (up) up.textContent = `up ${h}:${m}:${s}`;
}

/* =====================================================================
   Operator console — same list -> args -> confirm -> run screen flow,
   same command manifest (static/commands.json), every request goes
   same-origin straight to this app's own API. The Arr fleet page above
   covers the day-to-day Radarr/Sonarr actions with one click each; this
   is the full stack-* manifest for everything else (backups, disk
   usage, image checks, and the long tail).
   ===================================================================== */

const consoleScreens = {
  list: document.getElementById("screen-list"),
  args: document.getElementById("screen-args"),
  confirm: document.getElementById("screen-confirm"),
  run: document.getElementById("screen-run"),
};

let commandRegistry = [];
let activeLogSource = null;

function showConsoleScreen(name) {
  for (const [key, el] of Object.entries(consoleScreens)) {
    if (el) el.hidden = key !== name;
  }
  if (name !== "run") closeLogStream();
}

function closeLogStream() {
  if (activeLogSource) {
    activeLogSource.close();
    activeLogSource = null;
  }
}

document.querySelectorAll("[data-back]").forEach((btn) => {
  btn.addEventListener("click", () => showConsoleScreen(btn.dataset.back));
});

async function loadCommandRegistry() {
  const statusLine = document.getElementById("console-status");
  try {
    const res = await fetch("/commands.json");
    commandRegistry = await res.json();
    statusLine.textContent = `${commandRegistry.length} operations loaded`;
    renderCommandList("");
  } catch (e) {
    statusLine.textContent = "Command manifest failed to load.";
  }
}

function fuzzyMatch(query, target) {
  if (!query) return true;
  let qi = 0;
  const q = query.toLowerCase();
  const t = target.toLowerCase();
  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] === q[qi]) qi++;
  }
  return qi === q.length;
}

function matchRank(query, cmd) {
  const q = query.toLowerCase();
  const name = cmd.Name.toLowerCase();
  if (name === q) return 0;
  if (name.startsWith(q)) return 1;
  if (name.includes(q)) return 2;
  if (fuzzyMatch(query, cmd.Name)) return 3;
  if (fuzzyMatch(query, cmd.Description)) return 4;
  return -1;
}

function renderCommandList(filterValue) {
  const list = document.getElementById("command-list");
  list.innerHTML = "";
  const matches = commandRegistry
    .map((c) => ({ c, rank: filterValue ? matchRank(filterValue, c) : 0 }))
    .filter((m) => m.rank !== -1)
    .sort((a, b) => a.rank - b.rank || a.c.Name.localeCompare(b.c.Name))
    .map((m) => m.c);
  for (const cmd of matches) {
    const li = document.createElement("li");
    const tag = cmd.Confirm ? '<span class="ctag">destructive</span>' : "";
    li.innerHTML = `<span class="cname">${escapeHtml(cmd.Name)}</span>${tag}<span class="cdesc">${escapeHtml(cmd.Description)}</span>`;
    li.addEventListener("click", () => openCommand(cmd));
    list.appendChild(li);
  }
}

const consoleFilterInput = document.getElementById("console-filter");
if (consoleFilterInput) {
  consoleFilterInput.addEventListener("input", (e) => renderCommandList(e.target.value));
}

function openCommand(cmd) {
  document.getElementById("args-title").textContent = cmd.Name;
  document.getElementById("args-desc").textContent = cmd.Description;

  const form = document.getElementById("args-form");
  form.innerHTML = "";

  for (const arg of cmd.Args || []) {
    const label = document.createElement("label");
    const optionalTag = arg.Optional ? " (optional)" : "";
    label.innerHTML = `<span class="label-text">${escapeHtml(arg.Name)}${optionalTag}</span>`;

    let input;
    if (arg.Choices && arg.Choices.length > 0) {
      input = document.createElement("select");
      if (arg.Optional) {
        const blank = document.createElement("option");
        blank.value = "";
        blank.textContent = arg.Default ? `(default: ${arg.Default})` : "(none)";
        input.appendChild(blank);
      }
      for (const choice of arg.Choices) {
        const opt = document.createElement("option");
        opt.value = choice;
        opt.textContent = choice;
        input.appendChild(opt);
      }
    } else {
      input = document.createElement("input");
      input.type = "text";
      if (arg.Default) input.value = arg.Default;
      if (arg.Rest) input.placeholder = "space or comma separated";
    }
    input.dataset.argName = arg.Name;
    label.appendChild(input);
    form.appendChild(label);
  }

  const submit = document.createElement("button");
  submit.type = "submit";
  submit.className = "btn-primary";
  submit.textContent = cmd.Confirm ? "Continue" : "Run";
  form.appendChild(submit);

  form.onsubmit = (e) => {
    e.preventDefault();
    const values = Array.from(form.querySelectorAll("[data-arg-name]")).map((el) => el.value);
    if (cmd.Confirm) {
      showConsoleConfirm(cmd, values);
    } else {
      runRegistryCommand(cmd, values);
    }
  };

  showConsoleScreen("args");
}

function showConsoleConfirm(cmd, values) {
  document.getElementById("confirm-text").textContent = `${cmd.Name} ${values.filter(Boolean).join(" ")}`.trim();
  const input = document.getElementById("confirm-input");
  const yes = document.getElementById("confirm-yes");
  input.value = "";
  input.placeholder = cmd.Name;
  yes.disabled = true;
  input.oninput = () => {
    yes.disabled = input.value.trim() !== cmd.Name;
  };
  yes.onclick = () => runRegistryCommand(cmd, values);
  document.getElementById("confirm-no").onclick = () => showConsoleScreen("args");
  showConsoleScreen("confirm");
  setTimeout(() => input.focus(), 50);
}

function resolveLogContainer(cmd, values) {
  if (!cmd.LogContainer) return null;
  const m = /^\{(\d+)\}$/.exec(cmd.LogContainer);
  if (!m) return null;
  const idx = parseInt(m[1], 10) - 1;
  const v = values[idx];
  return v ? v : null;
}

/* ---- request builder: JS port of stack-web's commands.rs Prepare() +
   exec.rs, targeting this app's own same-origin API directly ---- */
function pathEscape(s) {
  let out = "";
  for (const ch of unescape(encodeURIComponent(s))) {
    const code = ch.charCodeAt(0);
    if (/[A-Za-z0-9\-_.~]/.test(ch)) out += ch;
    else out += "%" + code.toString(16).toUpperCase().padStart(2, "0");
  }
  return out;
}

function queryEscape(s) {
  if (s === " ") return "+";
  let out = "";
  for (const ch of unescape(encodeURIComponent(s))) {
    if (ch === " ") out += "+";
    else if (/[A-Za-z0-9\-_.~]/.test(ch)) out += ch;
    else out += "%" + ch.charCodeAt(0).toString(16).toUpperCase().padStart(2, "0");
  }
  return out;
}

function argValue(cmd, values, name) {
  const i = (cmd.Args || []).findIndex((a) => a.Name === name);
  return i === -1 ? "" : values[i];
}

function splitList(v) {
  const sep = v.includes(",") ? "," : " ";
  return v.split(sep).map((s) => s.trim()).filter(Boolean);
}

function prepareCommand(cmd, values) {
  let path = cmd.PathTemplate;
  values.forEach((value, i) => {
    const placeholder = `{${i + 1}}`;
    if (path.includes(placeholder)) path = path.split(placeholder).join(pathEscape(value));
  });

  if (cmd.Query && cmd.Query.length) {
    const pairs = [];
    for (const qp of cmd.Query) {
      const v = qp.ArgName ? argValue(cmd, values, qp.ArgName) : qp.Literal || "";
      if (!v) continue;
      pairs.push(`${queryEscape(qp.Key)}=${queryEscape(v)}`);
    }
    if (pairs.length) path += "?" + pairs.join("&");
  }

  let body = null;
  if (cmd.BodyMode === "json") {
    const obj = {};
    for (const bf of cmd.BodyFields || []) {
      const v = argValue(cmd, values, bf.ArgName);
      if (bf.Array) {
        if (!v) continue;
        obj[bf.Key] = splitList(v);
      } else {
        obj[bf.Key] = v;
      }
    }
    body = JSON.stringify(obj);
  }

  return { method: cmd.Method, path, body };
}

async function callApi(method, path, body) {
  const opts = { method };
  if (body !== null && body !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = body;
  }
  const res = await fetch(path, opts);
  const status = res.status;
  const raw = await res.text();
  return parseApiResult(raw, status);
}

function parseApiResult(raw, status) {
  if (!raw) return { ok: status === 200, message: `(empty response, HTTP ${status})`, data: null, rawList: null };

  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (_) {
    return { ok: false, message: raw, data: null, rawList: null };
  }

  if (Array.isArray(parsed)) return { ok: status === 200, message: "", data: null, rawList: parsed };

  let data = parsed;
  if (data && typeof data.detail === "object" && data.detail !== null) data = data.detail;

  if (data && typeof data.message === "string") {
    const ok = typeof data.ok === "boolean" ? data.ok : status === 200;
    return { ok, message: data.message, data, rawList: null };
  }

  return { ok: status === 200, message: "", data, rawList: null };
}

/* manual-import-by-index mirrors stack-arr-import.fish: re-fetch the
   candidate list fresh, then POST the file object at the chosen index. */
async function runManualImportByIndex(cmd, values) {
  const app = values[0] || "";
  const idx = parseInt((values[1] || "").trim(), 10);
  if (Number.isNaN(idx)) throw new Error(`index must be a number, got ${JSON.stringify(values[1])}`);

  const listPath = cmd.PathTemplate.replace("{1}", pathEscape(app));
  const listRes = await callApi("GET", listPath, null);
  if (!listRes.rawList) throw new Error("expected a JSON array response");
  const item = listRes.rawList[idx];
  if (!item) throw new Error(`no candidate at index ${idx} (${listRes.rawList.length} available) — run stack-arr-import-candidates ${app} again`);
  if (!item.file) throw new Error(`candidate at index ${idx} has no 'file' field`);
  return callApi("POST", listPath, JSON.stringify(item.file));
}

async function runLogLevelsReset(values) {
  if ((values[0] || "").trim() === "reset") return callApi("POST", "/api/log-levels/reset", null);
  return callApi("GET", "/api/log-levels", null);
}

/* Letterboxd's grid-scrape endpoints all take one JSON field (`url`), but
   two of the manifest entries collect it differently: filmography splits
   it into role+slug that need joining into a URL, and popular takes no
   arg at all (always the same base films page) - neither fits the
   generic {ArgName -> BodyFields.Key} mapping every other command uses,
   so (like manual-import-by-index and log-levels-reset above) these get
   their own small BodyMode handler instead of stretching that mapping to
   cover a shape it wasn't built for. */
async function runLetterboxdFilmography(cmd, values) {
  const role = (values[0] || "").trim();
  const slug = (values[1] || "").trim();
  if (!role || !slug) throw new Error("both role and slug are required");
  const prepared = prepareCommand(cmd, []);
  return callApi(cmd.Method, prepared.path, JSON.stringify({ url: `https://letterboxd.com/${role}/${slug}/` }));
}

async function runLetterboxdPopular(cmd) {
  const prepared = prepareCommand(cmd, []);
  return callApi(cmd.Method, prepared.path, JSON.stringify({ url: "https://letterboxd.com/films/" }));
}

async function execCommand(cmd, values) {
  if (cmd.BodyMode === "manual-import-by-index") return runManualImportByIndex(cmd, values);
  if (cmd.BodyMode === "log-levels-reset") return runLogLevelsReset(values);
  if (cmd.BodyMode === "letterboxd-filmography") return runLetterboxdFilmography(cmd, values);
  if (cmd.BodyMode === "letterboxd-popular") return runLetterboxdPopular(cmd);
  const prepared = prepareCommand(cmd, values);
  return callApi(prepared.method, prepared.path, prepared.body);
}

async function runRegistryCommand(cmd, values) {
  showConsoleScreen("run");
  document.getElementById("run-title").textContent = cmd.Name;
  const statusEl = document.getElementById("run-status");
  statusEl.textContent = "EXECUTING";
  statusEl.className = "pending";
  document.getElementById("result-pane").textContent = "";
  logLine("pending", `${cmd.Name} — requested`);

  const logPane = document.getElementById("log-pane");
  const logLines = document.getElementById("log-lines");
  logLines.textContent = "";
  const container = resolveLogContainer(cmd, values);

  closeLogStream();
  if (container) {
    logPane.hidden = false;
    document.getElementById("log-container-name").textContent = `(${container})`;
    activeLogSource = new EventSource(`/api/container/${encodeURIComponent(container)}/logs/stream`);
    activeLogSource.onmessage = (ev) => {
      logLines.textContent += ev.data + "\n";
      logLines.scrollTop = logLines.scrollHeight;
    };
  } else {
    logPane.hidden = true;
  }

  try {
    const result = await execCommand(cmd, values);
    statusEl.textContent = result.ok ? "COMPLETE" : "FAILED";
    statusEl.className = result.ok ? "ok" : "err";
    document.getElementById("result-pane").textContent = renderConsoleResult(result);
    logLine(result.ok ? "ok" : "err", `${cmd.Name} — ${result.message || (result.ok ? "done" : "failed")}`);
  } catch (e) {
    statusEl.textContent = "REQUEST FAILED";
    statusEl.className = "err";
    document.getElementById("result-pane").textContent = String(e.message || e);
    logLine("err", `${cmd.Name} — ${e.message || e}`);
  }

  if (activeLogSource) setTimeout(closeLogStream, 2000);
}

function renderConsoleResult(result) {
  const lines = [];
  if (result.message) lines.push(result.message);

  if (result.rawList) {
    if (!result.message && result.rawList.length === 0) return "(empty list)";
    for (const item of result.rawList) lines.push("  " + summarizeConsoleItem(item));
    return lines.join("\n");
  }

  const data = result.data || {};
  for (const key of Object.keys(data).sort()) {
    if (key === "message" || key === "ok") continue;
    const v = data[key];
    if (Array.isArray(v)) {
      if (v.length === 0) continue;
      lines.push("", key + ":");
      for (const item of v) lines.push("  " + summarizeConsoleItem(item));
    } else if (v && typeof v === "object") {
      if (Object.keys(v).length === 0) continue;
      lines.push("", key + ":");
      lines.push(indentDict(v, "  "));
    } else {
      lines.push(`${key}: ${v}`);
    }
  }
  const out = lines.join("\n").trim();
  return out || "(no output)";
}

function indentDict(d, indent) {
  const lines = [];
  for (const key of Object.keys(d).sort()) {
    const v = d[key];
    if (v && typeof v === "object" && !Array.isArray(v)) {
      lines.push(indent + key + ":");
      lines.push(indentDict(v, indent + "  "));
    } else {
      lines.push(`${indent}${key}: ${JSON.stringify(v)}`);
    }
  }
  return lines.join("\n");
}

function summarizeConsoleItem(item) {
  if (item && typeof item === "object" && !Array.isArray(item)) {
    const priority = ["title", "name", "label", "message"];
    const parts = [];
    const used = new Set();
    for (const key of priority) {
      if (key in item) {
        parts.push(String(item[key]));
        used.add(key);
      }
    }
    for (const key of Object.keys(item).sort()) {
      if (used.has(key)) continue;
      const v = item[key];
      parts.push(typeof v === "object" ? `${key}=${JSON.stringify(v)}` : `${key}=${v}`);
    }
    return parts.join("  ");
  }
  return String(item);
}

/* ---------- Poster sync ---------- */
let activePosterSource = null;

async function loadPosterLibraries() {
  const select = document.getElementById("poster-sync-library");
  if (!select) return;
  try {
    const res = await fetch("/api/posters/libraries");
    const libs = await res.json();
    if (!Array.isArray(libs) || libs.length === 0) {
      select.innerHTML = '<option value="">No movie/show libraries found</option>';
      return;
    }
    select.innerHTML = libs.map((lib) => `<option value="${escapeHtml(lib.title)}">${escapeHtml(lib.title)} (${lib.type})</option>`).join("");
  } catch (e) {
    select.innerHTML = '<option value="">Couldn\'t load libraries</option>';
  }
}

function posterLogLine(text) {
  const pane = document.getElementById("poster-log");
  const cls = text.startsWith("OK ") ? "poster-line-ok"
    : text.startsWith("FAIL ") || text.startsWith("ERROR ") ? "poster-line-fail"
    : text.startsWith("SKIP ") ? "poster-line-skip"
    : "poster-line-info";
  const line = document.createElement("div");
  line.className = cls;
  line.textContent = text;
  pane.appendChild(line);
  pane.scrollTop = pane.scrollHeight;
}

function closePosterStream() {
  if (activePosterSource) {
    activePosterSource.close();
    activePosterSource = null;
  }
}

function buildPosterSync() {
  const form = document.getElementById("poster-sync-form");
  if (!form) return;
  const summary = document.getElementById("poster-sync-summary");
  const submitBtn = form.querySelector("button[type=submit]");

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const library = document.getElementById("poster-sync-library").value;
    if (!library) return;
    const dryRun = document.getElementById("poster-sync-dry-run").checked;

    document.getElementById("poster-log").textContent = "";
    summary.textContent = "";
    submitBtn.disabled = true;
    closePosterStream();

    try {
      const data = await postAction("/api/posters/sync", { library, dry_run: dryRun });
      logLine("pending", data.message);
      summary.textContent = "running…";

      activePosterSource = new EventSource("/api/posters/sync/stream");
      activePosterSource.onmessage = (evt) => {
        posterLogLine(evt.data);
        if (evt.data.startsWith("DONE ")) {
          summary.textContent = evt.data.slice(5);
          logLine("ok", `Poster sync — ${evt.data.slice(5)}`);
          closePosterStream();
          submitBtn.disabled = false;
        } else if (evt.data.startsWith("ERROR ")) {
          summary.textContent = evt.data.slice(6);
          logLine("err", `Poster sync — ${evt.data.slice(6)}`);
          closePosterStream();
          submitBtn.disabled = false;
        }
      };
      activePosterSource.onerror = () => {
        closePosterStream();
        submitBtn.disabled = false;
      };
    } catch (e) {
      summary.textContent = e.message;
      logLine("err", `Poster sync — ${e.message}`);
      submitBtn.disabled = false;
    }
  });

  loadPosterLibraries();
}

/* ---------- Boot ---------- */
wireSidebarNav();
buildQuickLinks();
buildPrimaryGrid();
buildArrFleetToolbar();
buildArrFleet();
buildPosterSync();
buildDangerZone();
buildPlexUpdateCheck();
loadCommandRegistry();
tickClock();
setInterval(tickClock, 1000);
refreshStatus();
setInterval(refreshStatus, 20000);
refreshContainerGrid();
setInterval(refreshContainerGrid, 15000);
logLine("ok", "Control panel ready.");
