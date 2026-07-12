/* Control Panel front end — no build step, no dependencies. */

const ICONS = {
  bolt: '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>',
  database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0018 0V5"/><path d="M3 12a9 3 0 0018 0"/>',
  broom: '<path d="M9.59 4.59A2 2 0 1111 8H2"/><path d="M12.59 11.59A2 2 0 1114 15H2"/><path d="M17.73 7.73A2.5 2.5 0 1119.5 12H2"/>',
  restart: '<path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.13-3.36L23 10"/><path d="M1 14l5.36 4.36A9 9 0 0020.49 15"/>',
};

function svg(name) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
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

// Bindery (replaced Readarr in v10.7.0) isn't listed here - its API isn't
// Servarr-shaped, so none of the RSS-sync/search-missing/unstick/manual-
// import machinery this section wires up against /api/arr/{app}/... applies
// to it. It's still reachable via Quick Links below.
const ARR_APPS = [
  { id: "radarr", label: "Radarr", port: 7878, queue: true },
  { id: "sonarr", label: "Sonarr", port: 8989, queue: true },
  { id: "lidarr", label: "Lidarr", port: 8686, queue: true },
  { id: "whisparr", label: "Whisparr", port: 6969, queue: true },
];

/* Every service's own web UI - replaces Heimdall/Homepage as the link
   launcher, so both were removed from docker-compose.yml. Port list
   mirrors the "Bringing the stack up" table in README.md; `id` matches
   the container name so status dots can reuse /api/status's data. */
const QUICK_LINKS = [
  { id: "plex", label: "Plex", port: 32400, path: "/web" },
  { id: "prowlarr", label: "Prowlarr", port: 9696 },
  { id: "zilean", label: "Zilean", port: 8181 },
  { id: "decypharr", label: "Decypharr", port: 8282 },
  { id: "decypharr-alldebrid", label: "Decypharr (AllDebrid)", port: 8283 },
  { id: "zurg", label: "Zurg", port: 9999 },
  { id: "radarr", label: "Radarr", port: 7878 },
  { id: "sonarr", label: "Sonarr", port: 8989 },
  { id: "lidarr", label: "Lidarr", port: 8686 },
  { id: "bindery", label: "Bindery", port: 8787 },
  { id: "whisparr", label: "Whisparr", port: 6969 },
  { id: "nzbdav", label: "NzbDAV", port: 3001 },
  { id: "calibre-web", label: "Calibre-Web", port: 8083 },
  { id: "seerr", label: "Seerr", port: 5055 },
  { id: "byparr", label: "Byparr", port: 8191 },
  { id: "tautulli", label: "Tautulli", port: 8182 },
  { id: "glances", label: "Glances", port: 61208 },
  { id: "debridmediamanager", label: "DebridMediaManager", port: 3000 },
  { id: "cleanuparr", label: "Cleanuparr", port: 11011 },
  { id: "neutarr", label: "NeutArr", port: 9705 },
  { id: "dozzle", label: "Dozzle", port: 8080 },
  { id: "maintainerr", label: "Maintainerr", port: 6246 },
];

function buildQuickLinks() {
  const container = document.getElementById("quicklinks");
  container.innerHTML = QUICK_LINKS.map((svc) => {
    const url = `${location.protocol}//${location.hostname}:${svc.port}${svc.path || ""}`;
    return `<a class="quicklink" href="${url}" target="_blank" rel="noopener"><span class="quicklink-dot unknown" id="qdot-${svc.id}"></span>${escapeHtml(svc.label)}</a>`;
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
  div.textContent = s;
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

/* ---------- *arr rows ---------- */
function buildArrList() {
  const list = document.getElementById("arr-list");
  for (const app of ARR_APPS) {
    const row = document.createElement("div");
    row.className = "arr-row";
    row.innerHTML = `
      <div class="arr-name"><span class="lamp unknown" id="lamp-${app.id}"></span>${app.label}</div>
      <form class="arr-search" data-app="${app.id}">
        <input type="search" placeholder="Search ${app.label}…" aria-label="Search ${app.label}" required>
        <button class="btn-ghost" type="submit">Search</button>
      </form>
      <div class="arr-status" id="arr-status-${app.id}">—</div>
      <div class="arr-actions">
        <button class="btn-ghost" data-action="rss-sync" type="button">RSS sync</button>
        <button class="btn-ghost" data-action="search-missing" type="button">Search missing</button>
        ${app.queue ? `<button class="btn-ghost" data-unstick type="button">Unstick</button>` : ""}
        ${app.queue ? `<button class="btn-ghost" data-import-toggle type="button">Manual import</button>` : ""}
      </div>
    `;
    const status = row.querySelector(".arr-status");
    row.querySelectorAll(".arr-actions button[data-action]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const action = btn.dataset.action;
        const label = action === "rss-sync" ? "RSS sync" : "Search missing";
        row.querySelectorAll(".arr-actions button[data-action]").forEach((b) => (b.disabled = true));
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
          row.querySelectorAll(".arr-actions button[data-action]").forEach((b) => (b.disabled = false));
        }
      });
    });
    const searchForm = row.querySelector(".arr-search");
    searchForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const input = searchForm.querySelector("input");
      const term = input.value.trim();
      if (!term) return;
      const url = `${location.protocol}//${location.hostname}:${app.port}/add/new?term=${encodeURIComponent(term)}`;
      window.open(url, "_blank", "noopener");
      logLine("ok", `${app.label} search — opened "${term}" in a new tab`);
      input.value = "";
    });
    list.appendChild(row);

    if (app.queue) {
      const panel = document.createElement("div");
      panel.className = "import-panel";
      panel.hidden = true;
      list.appendChild(panel);
      setupUnstick(app, row, status);
      setupManualImportToggle(app, row, panel);
    }
  }
}

/* ---------- Unstick: sweep every stuck (warning/error) queue item ---------- */
function setupUnstick(app, row, status) {
  const btn = row.querySelector("[data-unstick]");
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

/* ---------- Manual import panel ---------- */
function setupManualImportToggle(app, row, panel) {
  const toggleBtn = row.querySelector("[data-import-toggle]");
  toggleBtn.addEventListener("click", async () => {
    const opening = panel.hidden;
    panel.hidden = !opening;
    if (opening) await loadManualImportCandidates(app, panel);
  });
}

async function loadManualImportCandidates(app, panel) {
  panel.innerHTML = `<div class="zilean-hint">Scanning stuck downloads for importable files…</div>`;
  logLine("pending", `${app.label} manual import — scanning`);
  try {
    const res = await fetch(`/api/arr/${app.id}/manual-import`);
    const items = await res.json();
    if (!res.ok) throw new Error(items?.detail?.message || items?.message || `Scan failed (${res.status})`);
    renderManualImportCandidates(app, panel, items);
    logLine("ok", `${app.label} manual import — found ${items.length} importable file${items.length === 1 ? "" : "s"}`);
  } catch (e) {
    panel.innerHTML = `<div class="zilean-hint error">${escapeHtml(e.message)}</div>`;
    logLine("err", `${app.label} manual import — ${e.message}`);
  }
}

function renderManualImportCandidates(app, panel, items) {
  if (!items.length) {
    panel.innerHTML = `<div class="zilean-hint">No importable files found among currently stuck downloads.</div>`;
    return;
  }
  panel.innerHTML = items
    .map((item, i) => {
      const meta = [item.quality, item.release_group, item.size].filter(Boolean).join(" · ");
      const match = [item.match_title, item.episode].filter(Boolean).join(" — ");
      const rejections = item.rejections.length
        ? `<span class="import-rejections" title="${escapeHtml(item.rejections.join("; "))}">⚠ ${item.rejections.length} rejection${item.rejections.length === 1 ? "" : "s"}</span>`
        : "";
      return `
        <div class="zilean-row">
          <div class="zilean-row-main">
            <span class="zilean-title">${escapeHtml(match || item.name || "Unknown")}</span>
            ${rejections}
            <span class="zilean-meta">${escapeHtml(meta)}</span>
          </div>
          <div class="zilean-row-hash">
            <code title="${escapeHtml(item.relative_path || "")}">${escapeHtml(item.relative_path || "")}</code>
            <button class="btn-ghost import-run" type="button" data-idx="${i}">Import</button>
          </div>
          <div class="status-line zilean-row-status" id="import-status-${app.id}-${i}">—</div>
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
const STOP_ICON = '<rect x="6" y="6" width="12" height="12" rx="2"/>';
const START_ICON = '<polygon points="6 3 20 12 6 21 6 3"/>';
ICONS.stop = STOP_ICON;
ICONS.start = START_ICON;

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
  // hits is undefined for containers Control Panel never makes an outbound
  // API call to (e.g. rclone mounts, Watchtower) - no row for those, rather
  // than a permanent "0" that never means anything.
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
        <span class="lamp ${stateClass}"></span>
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
        <button class="btn-icon" type="button" data-act="start" title="Start" ${c.state === "running" ? "disabled" : ""}>${svg("start")}</button>
        <button class="btn-icon" type="button" data-act="stop" title="Stop" ${c.is_self || c.state !== "running" ? "disabled" : ""}>${svg("stop")}</button>
        <button class="btn-icon" type="button" data-act="restart" title="Restart" ${c.is_self ? "disabled" : ""}>${svg("restart")}</button>
      </div>
    </div>`;
}

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
  // Stop is armed/confirmed - unlike restart (self-healing) or start
  // (harmless), stopping something leaves it down until someone notices
  // and starts it back up, so it gets the same one-extra-click guard as
  // the whole-stack restart and Zilean grab. Uses armIconButton (not
  // armButton) so the SVG icon survives the armed/idle swap instead of
  // being replaced by armButton's plain-text label.
  if (!stopBtn.disabled) armIconButton(stopBtn, "stop", () => fire(stopBtn, "stop", "stop"));
}

let containerGridBuilt = false;
let previousHitCounts = {};

// Best-effort, separate from the containers fetch above: if this fails,
// every card just renders with no API-hits row rather than losing the
// whole grid over a cosmetic extra.
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
    if (!containerGridBuilt) grid.innerHTML = `<div class="zilean-hint error">Could not load containers.</div>`;
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
}

/* ---------- Zilean direct search ---------- */
function buildZileanSearch() {
  const form = document.getElementById("zilean-search-form");
  const input = document.getElementById("zilean-search-input");
  const results = document.getElementById("zilean-results");
  const btn = form.querySelector("button");
  const filters = document.getElementById("zilean-filters");
  const resolutionSelect = document.getElementById("zilean-filter-resolution");
  const qualitySelect = document.getElementById("zilean-filter-quality");
  const minSizeInput = document.getElementById("zilean-filter-min-size");
  const maxSizeInput = document.getElementById("zilean-filter-max-size");
  const sortSelect = document.getElementById("zilean-filter-sort");
  const countEl = document.getElementById("zilean-filter-count");

  let allResults = [];

  function populateOptions(select, values) {
    const current = select.value;
    select.innerHTML = `<option value="">All</option>` + values.map((v) => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join("");
    if (values.includes(current)) select.value = current;
  }

  function applyFilters() {
    const resolution = resolutionSelect.value;
    const quality = qualitySelect.value;
    const minGb = parseFloat(minSizeInput.value);
    const maxGb = parseFloat(maxSizeInput.value);
    const sort = sortSelect.value;

    let filtered = allResults.filter((item) => {
      if (resolution && item.resolution !== resolution) return false;
      if (quality && item.quality !== quality) return false;
      const gb = item.size_bytes ? item.size_bytes / 1024 ** 3 : null;
      if (!Number.isNaN(minGb) && (gb === null || gb < minGb)) return false;
      if (!Number.isNaN(maxGb) && (gb === null || gb > maxGb)) return false;
      return true;
    });

    if (sort === "size-desc") filtered.sort((a, b) => (b.size_bytes || 0) - (a.size_bytes || 0));
    else if (sort === "size-asc") filtered.sort((a, b) => (a.size_bytes || 0) - (b.size_bytes || 0));
    else if (sort === "year-desc") filtered.sort((a, b) => (b.year || 0) - (a.year || 0));
    else if (sort === "name-asc") filtered.sort((a, b) => (a.title || "").localeCompare(b.title || ""));

    countEl.textContent = `${filtered.length} of ${allResults.length} shown`;
    renderZileanResults(results, filtered);
  }

  [resolutionSelect, qualitySelect, sortSelect].forEach((el) => el.addEventListener("change", applyFilters));
  [minSizeInput, maxSizeInput].forEach((el) => el.addEventListener("input", applyFilters));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const query = input.value.trim();
    if (!query) return;
    btn.disabled = true;
    filters.hidden = true;
    results.innerHTML = `<div class="zilean-hint">Searching…</div>`;
    logLine("pending", `Zilean search — "${query}"`);
    try {
      const data = await postAction("/api/zilean/search", { query });
      allResults = data;
      populateOptions(resolutionSelect, [...new Set(data.map((r) => r.resolution).filter(Boolean))].sort());
      populateOptions(qualitySelect, [...new Set(data.map((r) => r.quality).filter(Boolean))].sort());
      minSizeInput.value = "";
      maxSizeInput.value = "";
      sortSelect.value = "default";
      filters.hidden = data.length === 0;
      applyFilters();
      logLine("ok", `Zilean search — "${query}" returned ${data.length} result${data.length === 1 ? "" : "s"}`);
    } catch (e2) {
      results.innerHTML = `<div class="zilean-hint error">${escapeHtml(e2.message)}</div>`;
      logLine("err", `Zilean search — ${e2.message}`);
    } finally {
      btn.disabled = false;
    }
  });
}

function renderZileanResults(container, items) {
  if (!items.length) {
    container.innerHTML = `<div class="zilean-hint">No results.</div>`;
    return;
  }
  container.innerHTML = items
    .map((item, i) => {
      const meta = [item.resolution, item.quality, item.size].filter(Boolean).join(" · ");
      const season = item.seasons?.length ? `S${String(item.seasons[0]).padStart(2, "0")}` : "";
      const episode = item.episodes?.length ? `E${String(item.episodes[0]).padStart(2, "0")}` : "";
      const badge = [season, episode].filter(Boolean).join("");
      return `
        <div class="zilean-row">
          <div class="zilean-row-main">
            <span class="zilean-title">${escapeHtml(item.title || "Untitled")}${item.year ? ` (${item.year})` : ""}</span>
            ${badge ? `<span class="zilean-badge">${badge}</span>` : ""}
            <span class="zilean-meta">${escapeHtml(meta)}</span>
          </div>
          <div class="zilean-row-hash">
            <code>${escapeHtml(item.hash || "")}</code>
            <button class="btn-icon" type="button" data-copy="${escapeHtml(item.hash || "")}" title="Copy hash">Copy</button>
            <button class="btn-ghost zilean-grab" type="button" data-idx="${i}" title="Add to Decypharr (manual category)">Grab</button>
          </div>
          <div class="status-line zilean-row-status" id="zilean-status-${i}">—</div>
        </div>`;
    })
    .join("");
  container.querySelectorAll("button[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(btn.dataset.copy);
        const original = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(() => (btn.textContent = original), 1200);
      } catch (_) {
        logLine("err", "Clipboard access denied by the browser.");
      }
    });
  });
  container.querySelectorAll("button.zilean-grab").forEach((btn) => {
    const item = items[Number(btn.dataset.idx)];
    const status = document.getElementById(`zilean-status-${btn.dataset.idx}`);
    armButton(btn, "Grab", "Confirm grab?", async () => {
      btn.disabled = true;
      setStatusLine(status, "pending", "Adding to Decypharr…");
      logLine("pending", `Grab — "${item.title}" requested`);
      try {
        const data = await postAction("/api/decypharr/grab", { hash: item.hash, title: item.title });
        setStatusLine(status, "success", data.message);
        logLine("ok", `Grab — ${data.message}`);
      } catch (e) {
        setStatusLine(status, "error", e.message);
        logLine("err", `Grab — ${e.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  });
}

/* ---------- Arm/confirm guard for real, one-shot side effects ----------
   Shared by the whole-stack restart and Zilean grab buttons: first click
   arms (label swaps, 5s window), only a second click within that window
   actually fires onConfirm. Avoids a native confirm() dialog while still
   requiring deliberate intent for actions with a real, non-undoable side
   effect (restarting 22 containers, adding a magnet to a live debrid
   account). */
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

/* ---------- Icon-button variant of armButton() - keeps the SVG icon
   intact through the armed/idle swap instead of replacing it with a text
   label, via a CSS class + title change only. ---------- */
function armIconButton(btn, iconName, onConfirm) {
  let armed = false;
  let disarmTimer = null;
  btn.innerHTML = svg(iconName);
  const disarm = () => {
    armed = false;
    btn.classList.remove("armed");
    btn.title = btn.dataset.idleTitle || btn.title;
  };
  btn.dataset.idleTitle = btn.title;
  btn.addEventListener("click", async () => {
    if (!armed) {
      armed = true;
      btn.classList.add("armed");
      btn.title = "Click again to confirm";
      disarmTimer = setTimeout(disarm, 5000);
      return;
    }
    clearTimeout(disarmTimer);
    disarm();
    await onConfirm();
  });
}

/* ---------- Overview strip: host stats, Zilean hash count, Plex version ---------- */
async function refreshSystemStats() {
  try {
    const res = await fetch("/api/system/stats");
    const d = await res.json();
    const cpuVal = document.getElementById("stat-cpu-value");
    const cpuBar = document.getElementById("stat-cpu-bar");
    const memVal = document.getElementById("stat-mem-value");
    const memBar = document.getElementById("stat-mem-bar");
    const diskVal = document.getElementById("stat-disk-value");
    const diskBar = document.getElementById("stat-disk-bar");
    const uptimeVal = document.getElementById("stat-uptime-value");
    if (!d.available) {
      [cpuVal, memVal, diskVal].forEach((el) => (el.textContent = "unavailable"));
      uptimeVal.textContent = "unavailable";
      return;
    }
    cpuVal.textContent = fmtPercent(d.cpu_percent);
    cpuBar.style.width = `${Math.min(d.cpu_percent ?? 0, 100)}%`;
    memVal.textContent = d.mem_total_gb ? `${fmtPercent(d.mem_percent)} (${d.mem_used_gb}/${d.mem_total_gb} GB)` : fmtPercent(d.mem_percent);
    memBar.style.width = `${Math.min(d.mem_percent ?? 0, 100)}%`;
    diskVal.textContent = d.disk_total_gb ? `${fmtPercent(d.disk_percent)} (${d.disk_used_gb}/${d.disk_total_gb} GB)` : fmtPercent(d.disk_percent);
    diskBar.style.width = `${Math.min(d.disk_percent ?? 0, 100)}%`;
    uptimeVal.textContent = d.uptime || "—";
  } catch (_) {
    /* leave last-known values on screen rather than blanking on one failed poll */
  }
}

async function refreshZileanStats() {
  const val = document.getElementById("stat-zilean-value");
  const sub = document.getElementById("stat-zilean-sub");
  try {
    const res = await fetch("/api/zilean/stats");
    const d = await res.json();
    if (!d.available) {
      val.textContent = "unavailable";
      sub.textContent = "";
      return;
    }
    val.textContent = d.total_hashes.toLocaleString();
    sub.textContent = d.imdb_matched != null ? `${d.imdb_matched.toLocaleString()} IMDB-matched` : "";
  } catch (_) {
    /* leave last-known value */
  }
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

/* ---------- Status lamps ---------- */
async function refreshStatus() {
  let data;
  try {
    const res = await fetch("/api/status");
    data = await res.json();
  } catch (_) {
    return;
  }
  for (const [name, info] of Object.entries(data)) {
    const isUp = info.state === "running" && (info.health === "healthy" || info.health == null);
    const isStarting = info.state === "running" && info.health === "starting";
    const stateClass = isUp ? "up" : isStarting ? "unknown" : "down";

    const lamp = document.getElementById(`lamp-${name}`);
    if (lamp) {
      lamp.classList.remove("up", "down", "unknown");
      lamp.classList.add(stateClass);
    }
    const dot = document.getElementById(`qdot-${name}`);
    if (dot) {
      dot.classList.remove("up", "down", "unknown");
      dot.classList.add(stateClass);
    }
  }
}

/* ---------- Clock ---------- */
function tickClock() {
  const el = document.getElementById("clock");
  el.textContent = new Date().toLocaleString([], {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

buildQuickLinks();
buildPrimaryGrid();
buildArrList();
buildZileanSearch();
buildDangerZone();
buildPlexUpdateCheck();
tickClock();
setInterval(tickClock, 1000);
refreshStatus();
setInterval(refreshStatus, 20000);
refreshContainerGrid();
setInterval(refreshContainerGrid, 15000);
refreshSystemStats();
setInterval(refreshSystemStats, 10000);
refreshZileanStats();
setInterval(refreshZileanStats, 60000);
logLine("ok", "Control panel ready.");
