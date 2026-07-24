/* Control Panel front end — no build step, no dependencies.
   One continuous split-pane workspace: a scrollable left column of
   rule-divided rails (Overview, Fleet, Host, Reference) and a
   permanently pinned right-hand log console. There is no page-hiding
   navigation and no card/box layout — the only overlay is the command
   palette (Ctrl/Cmd+K), which is transient by design. */

const ICONS = {
  bolt: '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>',
  database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0018 0V5"/><path d="M3 12a9 3 0 0018 0"/>',
  broom: '<path d="M9.59 4.59A2 2 0 1111 8H2"/><path d="M12.59 11.59A2 2 0 1114 15H2"/><path d="M17.73 7.73A2.5 2.5 0 1119.5 12H2"/>',
  stop: '<rect x="6" y="6" width="12" height="12"/>',
  start: '<polygon points="6 3 20 12 6 21 6 3"/>',
  restart: '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>',
  tail: '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>',
};

function svg(name) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ""}</svg>`;
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s ?? "";
  return div.innerHTML;
}

/* Docker's own timestamps=True prefixes each log line with its real
   RFC3339Nano write time (server-side, not this browser's receipt
   time) - reformat it to a compact local clock instead of stripping it.
   Lines with no such prefix (anything not sourced from a docker.logs()
   call) pass through unchanged. */
const LOG_TS_RE = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s(.*)$/;

function formatLogLine(line) {
  const m = LOG_TS_RE.exec(line);
  if (!m) return line;
  const t = new Date(m[1]).toLocaleTimeString([], { hour12: false });
  return `[${t}] ${m[2]}`;
}

function formatLogText(raw) {
  return raw.split("\n").map(formatLogLine).join("\n");
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
  } catch (_) { /* no body */ }
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

/* =====================================================================
   Activity strip — compact recent-action log, pinned under the log
   console. Purely client-side, resets on reload.
   ===================================================================== */
const MAX_ACTIVITY_LINES = 80;

function logLine(kind, text) {
  const body = document.getElementById("log-body");
  const t = new Date().toLocaleTimeString([], { hour12: false });
  const glyph = kind === "ok" ? "✓" : kind === "err" ? "✕" : "›";
  const el = document.createElement("div");
  el.className = `activity-line ${kind}`;
  el.innerHTML = `<span class="t">${t}</span> <span class="g">${glyph}</span> ${escapeHtml(text)}`;
  body.appendChild(el);
  while (body.children.length > MAX_ACTIVITY_LINES) body.removeChild(body.firstChild);
  body.scrollTop = body.scrollHeight;
}

/* =====================================================================
   Pinned log console (right column) — the one place any container's
   logs stream to, whether picked manually from the source select or
   opened automatically because a palette command targets a container.
   ===================================================================== */
let activeLogSource = null;
let activeLogName = null;

function selectLogSource(name) {
  const lines = document.getElementById("log-lines");
  const select = document.getElementById("log-source");
  if (activeLogSource) {
    activeLogSource.close();
    activeLogSource = null;
  }
  activeLogName = name || null;
  if (select && select.value !== (name || "")) select.value = name || "";
  if (!name) {
    lines.innerHTML = '<span class="log-empty">Select a container above, or run a command from the palette — its log will stream here.</span>';
    return;
  }
  lines.textContent = "";
  activeLogSource = new EventSource(`/api/container/${encodeURIComponent(name)}/logs/stream`);
  activeLogSource.onmessage = (ev) => {
    lines.textContent += formatLogLine(ev.data) + "\n";
    lines.scrollTop = lines.scrollHeight;
  };
  activeLogSource.onerror = () => {
    lines.textContent += "\n[stream disconnected]\n";
  };
}

function wireLogConsole() {
  document.getElementById("log-source").addEventListener("change", (e) => selectLogSource(e.target.value || null));
  document.getElementById("log-clear").addEventListener("click", () => {
    document.getElementById("log-lines").textContent = "";
  });
}

/* =====================================================================
   Generic inline result rendering — turns whatever shape a GET/POST
   returns into real tables/definition-lists instead of a JSON dump.
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
    pre.textContent = formatLogText(value);
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
    try { parsed = JSON.parse(raw); } catch (_) { parsed = null; }
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

/* =====================================================================
   Overview rail: rapid actions
   ===================================================================== */
const PRIMARY_ACTIONS = [
  { id: "plex-scan", title: "Scan for new files", desc: "Refresh every Plex library section.", endpoint: "/api/plex/scan", icon: "search" },
  { id: "plex-empty-trash", title: "Empty trash", desc: "Permanently remove already-deleted items across every library.", endpoint: "/api/plex/empty-trash", icon: "trash" },
  { id: "plex-optimize-db", title: "Optimize database", desc: "Clears bloat after large library changes.", endpoint: "/api/plex/optimize-db", icon: "database" },
  { id: "plex-clean-bundles", title: "Clean old bundles", desc: "Remove metadata bundles Plex no longer needs.", endpoint: "/api/plex/clean-bundles", icon: "broom" },
];

function buildPrimaryActions() {
  const wrap = document.getElementById("primary-actions");
  for (const action of PRIMARY_ACTIONS) {
    const row = document.createElement("div");
    row.className = "rule-row";
    row.innerHTML = `
      <div class="rule-main">
        <span class="rule-title">${escapeHtml(action.title)}</span>
        <span class="rule-desc">${escapeHtml(action.desc)}</span>
      </div>
      <div class="rule-actions">
        <button class="btn-primary" type="button">Run</button>
      </div>
      <div class="rule-status" id="status-${action.id}">—</div>
    `;
    wrap.appendChild(row);
    const btn = row.querySelector("button");
    const status = row.querySelector(".rule-status");
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      setStatusLine(status, "pending", "Running…");
      logLine("pending", `${action.title} — requested`);
      try {
        const data = await postAction(action.endpoint);
        setStatusLine(status, "success", data.message);
        logLine("ok", `${action.title} — ${data.message}`);
      } catch (e) {
        setStatusLine(status, "error", e.message);
        logLine("err", `${action.title} — ${e.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  }
}

/* =====================================================================
   Fleet rail: every container, live from Docker, grouped by subsystem
   (Source selection — option B). Never a hardcoded allow-list: a
   service missing from FLEET_GROUPS just falls into "Other" rather
   than being hidden, matching app.py's own CONTAINER_LABELS staleness
   tolerance. Clicking a row (not its action buttons) makes it the
   active log-console source.
   ===================================================================== */
const FLEET_GROUPS = {
  prowlarr: "Indexing", radarr: "Arr apps", sonarr: "Arr apps",
  bearmount: "Usenet", seerr: "Requests", plex: "Media server",
  bazarr: "Subtitles",
  unpackerr: "Post-processing", watchtower: "Auto-updates",
  cleanuparr: "Queue cleanup", neutarr: "Queue cleanup",
  "control-panel": "Dashboard",
};
const GROUP_ORDER = ["Arr apps", "Indexing", "Usenet", "Requests", "Media server", "Subtitles", "Queue cleanup", "Post-processing", "Auto-updates", "Dashboard", "Other"];
const collapsedGroups = new Set(JSON.parse(localStorage.getItem("fleetCollapsed") || "[]"));

function fmtPercent(v) { return v === null || v === undefined ? "—" : `${v.toFixed(1)}%`; }
function fmtMb(v) {
  if (v === null || v === undefined) return "—";
  return v >= 1024 ? `${(v / 1024).toFixed(2)} GB` : `${v.toFixed(0)} MB`;
}

function fleetRowHtml(c) {
  const stateClass = c.state === "running" ? (c.health === "unhealthy" ? "down" : c.health === "starting" ? "unknown" : "up") : c.state === "exited" || c.state === "created" ? "down" : "unknown";
  const healthLabel = c.state !== "running" ? c.state : c.health ? c.health : "running";
  const cpuPct = c.cpu_percent === null || c.cpu_percent === undefined ? 0 : Math.min(c.cpu_percent, 100);
  const memPct = c.mem_percent === null || c.mem_percent === undefined ? 0 : Math.min(c.mem_percent, 100);
  const cpuCls = cpuPct >= 90 ? "bad" : cpuPct >= 70 ? "warn" : "";
  const memCls = memPct >= 90 ? "bad" : memPct >= 70 ? "warn" : "";
  return `
    <div class="rule-row fleet-row" data-name="${escapeHtml(c.name)}" data-state="${escapeHtml(c.state)}">
      <div class="rule-main">
        <span class="fleet-row-name"><span class="dot ${stateClass}"></span>${escapeHtml(c.label)}${c.note ? `<span class="fleet-row-sub">${escapeHtml(c.note)}</span>` : ""}</span>
        <span class="fleet-row-image" title="${escapeHtml(c.image)}">${escapeHtml(c.image)}</span>
      </div>
      <span class="fleet-row-health">${escapeHtml(healthLabel)}</span>
      <span class="fleet-metric">CPU <span class="fleet-bar"><span class="fleet-bar-fill ${cpuCls}" style="width:${cpuPct}%"></span></span> ${fmtPercent(c.cpu_percent)}</span>
      <span class="fleet-metric">MEM <span class="fleet-bar"><span class="fleet-bar-fill ${memCls}" style="width:${memPct}%"></span></span> ${fmtMb(c.mem_used_mb)}</span>
      <div class="rule-actions">
        <button class="btn-icon" type="button" data-act="tail" title="Tail logs" aria-label="Tail logs for ${escapeHtml(c.label)}">${svg("tail")}</button>
        <button class="btn-icon" type="button" data-act="start" title="Start" aria-label="Start ${escapeHtml(c.label)}" ${c.state === "running" ? "disabled" : ""}>${svg("start")}</button>
        <button class="btn-icon" type="button" data-act="stop" title="Stop" aria-label="Stop ${escapeHtml(c.label)}" ${c.is_self || c.state !== "running" ? "disabled" : ""}>${svg("stop")}</button>
        <button class="btn-icon" type="button" data-act="restart" title="Restart" aria-label="Restart ${escapeHtml(c.label)}" ${c.is_self ? "disabled" : ""}>${svg("restart")}</button>
      </div>
    </div>`;
}

function wireFleetRow(row, c) {
  const tailBtn = row.querySelector('[data-act="tail"]');
  const startBtn = row.querySelector('[data-act="start"]');
  const stopBtn = row.querySelector('[data-act="stop"]');
  const restartBtn = row.querySelector('[data-act="restart"]');

  tailBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    selectLogSource(c.name);
    document.querySelectorAll(".fleet-row.selected").forEach((r) => r.classList.remove("selected"));
    row.classList.add("selected");
  });

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
      refreshFleet();
    }
  };
  if (!startBtn.disabled) startBtn.addEventListener("click", (e) => { e.stopPropagation(); fire(startBtn, "start", "start"); });
  if (!restartBtn.disabled) restartBtn.addEventListener("click", (e) => { e.stopPropagation(); fire(restartBtn, "restart", "restart"); });
  if (!stopBtn.disabled) armIconButton(stopBtn, "stop", () => fire(stopBtn, "stop", "stop"), (e) => e.stopPropagation());
}

let fleetBuilt = false;
let previousHitCounts = {};

async function fetchHitCounts() {
  try {
    const res = await fetch("/api/api-hit-counts");
    if (!res.ok) return null;
    const { counts } = await res.json();
    previousHitCounts = counts;
    return counts;
  } catch (e) {
    return null;
  }
}

function populateLogSourceSelect(data) {
  const select = document.getElementById("log-source");
  const prevValue = select.value;
  const byGroup = {};
  for (const c of data) {
    const group = FLEET_GROUPS[c.name] || "Other";
    (byGroup[group] = byGroup[group] || []).push(c);
  }
  let html = '<option value="">Select a source…</option>';
  for (const group of GROUP_ORDER) {
    if (!byGroup[group]) continue;
    html += `<optgroup label="${escapeHtml(group)}">`;
    for (const c of byGroup[group].sort((a, b) => a.label.localeCompare(b.label))) {
      html += `<option value="${escapeHtml(c.name)}">${escapeHtml(c.label)}</option>`;
    }
    html += `</optgroup>`;
  }
  select.innerHTML = html;
  select.value = prevValue;
}

async function refreshFleet() {
  const wrap = document.getElementById("fleet-groups");
  let data;
  try {
    const res = await fetch("/api/containers");
    data = await res.json();
    if (!res.ok) throw new Error("Could not load containers");
  } catch (e) {
    if (!fleetBuilt) wrap.innerHTML = `<div class="hint error">Could not load containers.</div>`;
    return;
  }

  const up = data.filter((c) => c.state === "running" && (c.health === "healthy" || !c.health)).length;
  const containersValue = document.getElementById("stat-containers-value");
  const containersSub = document.getElementById("stat-containers-sub");
  if (containersValue) containersValue.textContent = `${up} / ${data.length}`;
  if (containersSub) containersSub.textContent = up === data.length ? "all healthy" : `${data.length - up} need attention`;

  const hits = await fetchHitCounts();
  const byGroup = {};
  for (const c of data) {
    const group = FLEET_GROUPS[c.name] || "Other";
    (byGroup[group] = byGroup[group] || []).push(c);
  }

  wrap.innerHTML = "";
  for (const group of GROUP_ORDER) {
    const items = byGroup[group];
    if (!items) continue;
    items.sort((a, b) => a.label.localeCompare(b.label));
    const groupEl = document.createElement("div");
    groupEl.className = "fleet-group" + (collapsedGroups.has(group) ? " collapsed" : "");
    const downCount = items.filter((c) => !(c.state === "running" && (c.health === "healthy" || !c.health))).length;
    groupEl.innerHTML = `
      <div class="fleet-group-head" data-group="${escapeHtml(group)}">
        <span class="chev">▾</span>${escapeHtml(group)}
        <span class="fleet-group-count">${items.length} container${items.length === 1 ? "" : "s"}${downCount ? ` · ${downCount} need attention` : ""}</span>
      </div>
      <div class="rule-list">${items.map(fleetRowHtml).join("")}</div>
    `;
    wrap.appendChild(groupEl);
    groupEl.querySelector(".fleet-group-head").addEventListener("click", () => {
      groupEl.classList.toggle("collapsed");
      if (groupEl.classList.contains("collapsed")) collapsedGroups.add(group);
      else collapsedGroups.delete(group);
      localStorage.setItem("fleetCollapsed", JSON.stringify([...collapsedGroups]));
    });
    groupEl.querySelectorAll(".fleet-row").forEach((row) => {
      const c = items.find((x) => x.name === row.dataset.name);
      if (c.name === activeLogName) row.classList.add("selected");
      wireFleetRow(row, c);
    });
  }
  fleetBuilt = true;
  populateLogSourceSelect(data);
  renderStatusDots(data);
}

/* =====================================================================
   Arr fleet detail — Radarr/Sonarr actions, unchanged behavior, just
   restyled without the card class.
   ===================================================================== */
const ARR_APPS = [
  { id: "radarr", label: "Radarr", port: 7878 },
  { id: "sonarr", label: "Sonarr", port: 8989 },
];
const ARR_FLEET_ACTIONS = [
  { id: "queue-status", label: "Queue status", path: "/api/queue-status" },
  { id: "queue-errors", label: "Queue errors", path: "/api/arr/queue-errors" },
  { id: "command-queue-summary", label: "Command queue summary", path: "/api/arr/command-queue-summary" },
  { id: "backlog-status", label: "Backlog ETA", path: "/api/backlog-status" },
  { id: "prowlarr-indexers", label: "Prowlarr indexers", path: "/api/prowlarr/indexers" },
];
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

  const toolbarRow = document.createElement("div");
  toolbarRow.className = "arr-actions-row";
  toolbarRow.innerHTML = `<span class="arr-actions-row-label">Fleet-wide</span>` + ARR_FLEET_ACTIONS.map((a) => `<button class="btn-ghost" data-fleet="${a.id}" type="button">${a.label}</button>`).join("");
  const toolbarPanel = document.createElement("div");
  toolbarPanel.className = "arr-panel";
  toolbarPanel.hidden = true;
  wrap.appendChild(toolbarRow);
  wrap.appendChild(toolbarPanel);
  toolbarRow.querySelectorAll("[data-fleet]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const wasOpen = btn.classList.contains("active") && !toolbarPanel.hidden;
      toolbarRow.querySelectorAll("[data-fleet]").forEach((b) => b.classList.remove("active"));
      if (wasOpen) { toolbarPanel.hidden = true; return; }
      btn.classList.add("active");
      const action = ARR_FLEET_ACTIONS.find((a) => a.id === btn.dataset.fleet);
      logLine("pending", `${action.label} — requested`);
      try {
        await fetchAndRender(toolbarPanel, "GET", action.path);
        logLine("ok", `${action.label} — loaded`);
      } catch (e) {
        logLine("err", `${action.label} — ${e.message}`);
      }
    });
  });

  for (const app of ARR_APPS) {
    const openUrl = `${location.protocol}//${location.hostname}:${app.port}`;
    const block = document.createElement("div");
    block.className = "arr-block";
    block.innerHTML = `
      <div class="arr-head">
        <div class="arr-name"><span class="dot unknown" id="arr-dot-${app.id}"></span>${app.label}</div>
        <a class="arr-link" href="${openUrl}" target="_blank" rel="noopener">open UI ↗</a>
        <div class="arr-status" id="arr-status-${app.id}">—</div>
      </div>
      <form class="arr-search" data-app="${app.id}">
        <input type="search" placeholder="Search ${app.label}…" aria-label="Search ${app.label}" required>
        <button class="btn-ghost" type="submit">Search</button>
      </form>
      <div class="arr-actions-row">
        <span class="arr-actions-row-label">Run</span>
        <button class="btn-primary" data-action="rss-sync" type="button">RSS sync</button>
        <button class="btn-primary" data-action="search-missing" type="button">Search missing</button>
        <button class="btn-ghost" data-unstick type="button">Unstick</button>
        <button class="btn-ghost" data-unstick-importing type="button">Unstick importing</button>
      </div>
      <div class="arr-actions-row">
        <span class="arr-actions-row-label">View</span>
        ${ARR_VIEWS.map((v) => `<button class="btn-ghost" data-view="${v.id}" type="button">${v.label}</button>`).join("")}
        <button class="btn-ghost" data-view="manual-import" type="button">Manual import</button>
      </div>
      <div class="arr-panel" id="arr-panel-${app.id}" hidden></div>
    `;
    wrap.appendChild(block);

    const status = block.querySelector(".arr-status");
    const panel = block.querySelector(`#arr-panel-${app.id}`);

    block.querySelectorAll("[data-action]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const action = btn.dataset.action;
        const label = action === "rss-sync" ? "RSS sync" : "Search missing";
        block.querySelectorAll("[data-action]").forEach((b) => (b.disabled = true));
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
          block.querySelectorAll("[data-action]").forEach((b) => (b.disabled = false));
        }
      });
    });

    setupUnstick(app, block, status);
    setupUnstickImporting(app, block, status);

    const searchForm = block.querySelector(".arr-search");
    searchForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const input = searchForm.querySelector("input");
      const term = input.value.trim();
      if (!term) return;
      window.open(`${openUrl}/add/new?term=${encodeURIComponent(term)}`, "_blank", "noopener");
      logLine("ok", `${app.label} search — opened "${term}" in a new tab`);
      input.value = "";
    });

    block.querySelectorAll("[data-view]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const wasOpen = btn.classList.contains("active") && !panel.hidden;
        block.querySelectorAll("[data-view]").forEach((b) => b.classList.remove("active"));
        if (wasOpen) { panel.hidden = true; return; }
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

function setupUnstick(app, block, status) {
  const btn = block.querySelector("[data-unstick]");
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

function setupUnstickImporting(app, block, status) {
  const btn = block.querySelector("[data-unstick-importing]");
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
        <div class="result-row-item">
          <div class="result-row-main">
            <span class="result-title">${escapeHtml(match || item.name || "Unknown")}</span>
            ${rejections}
            <span class="result-meta">${escapeHtml(meta)}</span>
          </div>
          <button class="btn-ghost import-run" type="button" data-idx="${i}">Import</button>
          <div class="rule-status" id="import-status-${app.id}-${i}">—</div>
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

/* ---------- Arm/confirm guard for real, one-shot side effects ---------- */
function armButton(btn, idleLabel, armedLabel, onConfirm) {
  let armed = false;
  let disarmTimer = null;
  const disarm = () => { armed = false; btn.textContent = idleLabel; btn.classList.remove("armed"); };
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

function armIconButton(btn, iconName, onConfirm, stopHandler) {
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
  btn.addEventListener("click", async (e) => {
    if (stopHandler) stopHandler(e);
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

/* =====================================================================
   Host rail — two lanes. Vitals are read-only checks this container can
   genuinely answer from its own mounts (docker.sock, /host-config,
   /mnt, /host-backups). Package updates / reboot-needed / mem-pressure
   / zombie-check are deliberately NOT here: this container has no
   pacman, no pid:host, and no real host /proc — building those as live
   tiles would show container-scoped or fake data as if it were the
   host's. They stay terminal-only; see the Reference rail below.
   ===================================================================== */
const HOST_VITALS = [
  { id: "mount-health", label: "Mount health", desc: "Every known FUSE mountpoint under /mnt, checked for a clean listing.", path: "/api/mount-health" },
  { id: "oom-check", label: "OOM kills", desc: "Containers Docker has ever recorded an OOM-kill flag for.", path: "/api/oom-check" },
  { id: "resource-check", label: "Resource limits", desc: "Containers missing an explicit mem_limit or cpus.", path: "/api/resource-check" },
  { id: "disk-usage", label: "Config disk usage", desc: "Per-app config/ directory size, largest first.", path: "/api/disk-usage" },
  { id: "backup-verify", label: "Backup verify", desc: "Latest restic snapshot age and repo integrity summary.", path: "/api/backup-verify" },
];

function buildHostVitals() {
  const wrap = document.getElementById("host-vitals");
  for (const v of HOST_VITALS) {
    const row = document.createElement("div");
    row.className = "rule-row";
    row.innerHTML = `
      <div class="rule-main">
        <span class="rule-title">${escapeHtml(v.label)}</span>
        <span class="rule-desc">${escapeHtml(v.desc)}</span>
      </div>
      <div class="rule-actions"><button class="btn-ghost" type="button">Check</button></div>
      <div class="rule-result" hidden></div>
    `;
    wrap.appendChild(row);
    const btn = row.querySelector("button");
    const result = row.querySelector(".rule-result");
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      logLine("pending", `${v.label} — requested`);
      try {
        await fetchAndRender(result, "GET", v.path);
        logLine("ok", `${v.label} — loaded`);
      } catch (e) {
        logLine("err", `${v.label} — ${e.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  }
}

function buildHostActions() {
  const wrap = document.getElementById("host-actions");

  const restartRow = document.createElement("div");
  restartRow.className = "rule-row";
  restartRow.innerHTML = `
    <div class="rule-main">
      <span class="rule-title">Restart entire stack</span>
      <span class="rule-desc">Restarts every container except this panel, mount-order aware. Brief outage stack-wide.</span>
    </div>
    <div class="rule-actions"><button class="btn-danger" type="button">Restart everything</button></div>
    <div class="rule-status" id="status-restart-all">—</div>
  `;
  wrap.appendChild(restartRow);
  const restartBtn = restartRow.querySelector("button");
  const restartStatus = restartRow.querySelector(".rule-status");
  armButton(restartBtn, "Restart everything", "Click again to confirm", async () => {
    restartBtn.disabled = true;
    setStatusLine(restartStatus, "pending", "Restarting…");
    logLine("pending", "Restart entire stack — requested");
    try {
      const data = await postAction("/api/stack/restart-all");
      setStatusLine(restartStatus, "success", data.message);
      logLine("ok", `Restart entire stack — ${data.message}`);
      refreshStatus();
    } catch (e) {
      setStatusLine(restartStatus, "error", e.message);
      logLine("err", `Restart entire stack — ${e.message}`);
    } finally {
      restartBtn.disabled = false;
    }
  });

  const posterRow = document.createElement("div");
  posterRow.className = "rule-row";
  posterRow.innerHTML = `
    <div class="rule-main">
      <span class="rule-title">Poster sync</span>
      <span class="rule-desc">Replace posters with the top-voted TMDb match, one library at a time.</span>
    </div>
    <div class="rule-actions"><button class="btn-ghost" type="button">Open</button></div>
  `;
  wrap.appendChild(posterRow);
  posterRow.querySelector("button").addEventListener("click", () => {
    document.getElementById("poster-dock").hidden = false;
  });

  const integrityRow = document.createElement("div");
  integrityRow.className = "rule-row";
  integrityRow.innerHTML = `
    <div class="rule-main">
      <span class="rule-title">Backup integrity check</span>
      <span class="rule-desc">Runs restic's own data-verification pass against the repo — can take a while on a large repo.</span>
    </div>
    <div class="rule-actions"><button class="btn-ghost" type="button">Run check</button></div>
    <div class="rule-status" id="status-backup-integrity">—</div>
  `;
  wrap.appendChild(integrityRow);
  const integrityBtn = integrityRow.querySelector("button");
  const integrityStatus = integrityRow.querySelector(".rule-status");
  armButton(integrityBtn, "Run check", "Click again to confirm", async () => {
    integrityBtn.disabled = true;
    setStatusLine(integrityStatus, "pending", "Running…");
    logLine("pending", "Backup integrity check — requested");
    try {
      const data = await postAction("/api/backup-integrity-check");
      setStatusLine(integrityStatus, "success", data.message);
      logLine("ok", `Backup integrity check — ${data.message}`);
    } catch (e) {
      setStatusLine(integrityStatus, "error", e.message);
      logLine("err", `Backup integrity check — ${e.message}`);
    } finally {
      integrityBtn.disabled = false;
    }
  });
}

function buildPosterDock() {
  document.getElementById("poster-dock-close").addEventListener("click", () => {
    document.getElementById("poster-dock").hidden = true;
    closePosterStream();
  });
  buildPosterSync();
}

/* =====================================================================
   Reference rail — open-a-service quicklinks, documentation (this
   stack's own README + each third-party app's real upstream docs, all
   verified against docker-compose.yml's actual images before being
   hardcoded here), and a read-only list of the Claude Code skills this
   project uses (dev-time only — this app has no mechanism to invoke
   them, so they're informational, not interactive).
   ===================================================================== */
const QUICK_LINKS = [
  { id: "plex", label: "Plex", port: 32400, path: "/web" },
  { id: "prowlarr", label: "Prowlarr", port: 9696 },
  { id: "radarr", label: "Radarr", port: 7878 },
  { id: "sonarr", label: "Sonarr", port: 8989 },
  { id: "bearmount", label: "BearMount", port: 8082 },
  { id: "seerr", label: "Seerr", port: 5055 },
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

/* Each URL below was verified to resolve (github.com/<org>/<repo> or the
   project's own docs domain) against docker-compose.yml's real pinned
   image before being hardcoded — not guessed from the app's common name.
   `installed: false` means the compose service block and image both
   still exist, but no container is currently created for it (confirmed
   via `docker compose ps -a` showing nothing for that service) — kept
   here as documentation, not presented as a live/running app. */
const DOC_LINKS = [
  { app: "Radarr", desc: "movie root-folder/quality-profile management", urls: [["Wiki", "https://wiki.servarr.com/radarr"], ["Source", "https://github.com/Radarr/Radarr"]] },
  { app: "Sonarr", desc: "TV root-folder/quality-profile management", urls: [["Wiki", "https://wiki.servarr.com/sonarr"], ["Source", "https://github.com/Sonarr/Sonarr"]] },
  { app: "Prowlarr", desc: "indexer manager, syncs to Radarr/Sonarr", urls: [["Wiki", "https://wiki.servarr.com/prowlarr"], ["Source", "https://github.com/Prowlarr/Prowlarr"]] },
  { app: "BearMount", desc: "Usenet WebDAV mount + SABnzbd-compatible API (WhispersOfJ/bearmount, a rebranded fork of javi11/altmount)", urls: [["Source", "https://github.com/WhispersOfJ/bearmount"]] },
  { app: "Seerr", desc: "media request/discovery front-end", urls: [["Source", "https://github.com/seerr-team/seerr"]] },
  { app: "Plex", desc: "media server", urls: [["Support", "https://support.plex.tv"]] },
  { app: "Bazarr", desc: "subtitle management for Radarr/Sonarr", urls: [["Source", "https://github.com/morpheus65535/bazarr"]] },
  { app: "Cleanuparr", desc: "queue strikes/malware-block/stalled cleanup", urls: [["Source", "https://github.com/Cleanuparr/Cleanuparr"]] },
  { app: "NeutArr", desc: "missing/upgrade hunting (Huntarr-lineage fork)", urls: [["Source", "https://github.com/I-am-PUID-0/NeutArr"]] },
  { app: "Unpackerr", desc: "RAR extraction for Radarr/Sonarr downloads", urls: [["Source", "https://github.com/Unpackerr/unpackerr"]] },
  { app: "Watchtower", desc: "container auto-update (maintained fork)", urls: [["Source", "https://github.com/nicholas-fedor/watchtower"]] },
];

function buildDocLinks() {
  const wrap = document.getElementById("doc-links");

  const readmeRow = document.createElement("div");
  readmeRow.className = "rule-row";
  readmeRow.innerHTML = `
    <div class="rule-main">
      <span class="rule-title">This stack's own README.md</span>
      <span class="rule-desc">No public downstream mirror exists for this repo — read directly off disk instead of linking out.</span>
    </div>
    <div class="rule-actions"><button class="btn-ghost" type="button" id="readme-open">Open</button></div>
  `;
  wrap.appendChild(readmeRow);
  document.getElementById("readme-open").addEventListener("click", async () => {
    const panel = document.getElementById("readme-panel");
    const body = document.getElementById("readme-body");
    panel.hidden = false;
    body.textContent = "Loading…";
    try {
      const res = await fetch("/api/docs/readme");
      const data = await res.json();
      body.textContent = res.ok ? data.text : (data?.detail?.message || "Could not load README.md");
    } catch (e) {
      body.textContent = e.message;
    }
  });
  document.getElementById("readme-close").addEventListener("click", () => {
    document.getElementById("readme-panel").hidden = true;
  });

  for (const doc of DOC_LINKS) {
    const row = document.createElement("div");
    row.className = "rule-row";
    const notInstalled = doc.installed === false
      ? `<span class="not-installed-tag" title="Compose service block and image both exist, but no container is currently created for it">not installed</span>`
      : "";
    row.innerHTML = `
      <div class="rule-main">
        <span class="rule-title">${escapeHtml(doc.app)}${notInstalled}</span>
        <span class="rule-desc">${escapeHtml(doc.desc)}</span>
      </div>
      <div class="rule-actions">${doc.urls.map(([label, url]) => `<a class="doc-link-ext" href="${url}" target="_blank" rel="noopener">${escapeHtml(label)} ↗</a>`).join("")}</div>
    `;
    wrap.appendChild(row);
  }
}

/* Dev-time Claude Code skills this project uses — run inside Claude
   Code sessions, not inside this FastAPI app. Kept as a separate,
   read-only reference list rather than merged into the operator
   console above, since this app has no mechanism to invoke them. */
const CLAUDE_SKILLS = [
  { name: "docker-compose-manager", desc: "Start/stop/restart/inspect containers, mount-order aware." },
  { name: "health-monitor", desc: "Container health + HTTP-endpoint reachability sweep across the stack." },
  { name: "media-path-validator", desc: "Validate library/download paths are mounted and hardlink-capable." },
  { name: "request-manager-integrator", desc: "Wire Seerr to Radarr/Sonarr and verify the connection is live." },
  { name: "secret-injector", desc: "Generate/validate .env, rotate API keys, scan for leaked secrets." },
  { name: "arr-config-sync", desc: "Backup/restore/diff config across Radarr, Sonarr, Prowlarr." },
  { name: "trash-guides-applier", desc: "Apply TRaSH Guides quality profiles and custom formats." },
  { name: "usenet-orchestrator", desc: "Inspect/manage the Usenet download queue and health." },
  { name: "stack-cli-arr-fleet", desc: "Radarr/Sonarr queue, import, missing/cutoff, Bazarr subtitle ops." },
  { name: "stack-cli-discovery-import", desc: "Letterboxd/MDBList/Trakt/TMDb list imports and rating lookups." },
  { name: "stack-cli-infra-ops", desc: "Container control, backup verify/integrity, disk usage checks." },
  { name: "stack-cli-plex-kometa", desc: "Plex library/Butler tasks, duplicates, TMDb-link audit." },
  { name: "stack-cli-system-maintenance", desc: "Host package updates, reboot/disk/SMART/journal checks (terminal-only — see the Host rail's note above)." },
  { name: "stack-cli-usenet-queue", desc: "BearMount/Cleanuparr/NeutArr/Prowlarr status and queue ops." },
];

function buildSkillsList() {
  const wrap = document.getElementById("skills-list");
  wrap.innerHTML = CLAUDE_SKILLS.map((s) => `
    <div class="rule-row">
      <div class="rule-main">
        <span class="skill-name">${escapeHtml(s.name)}</span>
        <span class="rule-desc">${escapeHtml(s.desc)}</span>
      </div>
    </div>`).join("");
}

/* ---------- Plex update check ---------- */
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

/* ---------- Status dots (topbar conn + arr dots + quicklink dots) ---------- */
function setHudConn(up) {
  const dot = document.getElementById("hud-conn-dot");
  const label = document.getElementById("hud-conn-label");
  if (!dot || !label) return;
  dot.classList.remove("up", "down");
  dot.classList.add(up ? "up" : "down");
  label.textContent = up ? "connected" : "disconnected";
}

function renderStatusDots(data) {
  for (const c of data) {
    const isUp = c.state === "running" && (c.health === "healthy" || !c.health);
    const isStarting = c.state === "running" && c.health === "starting";
    const stateClass = isUp ? "up" : isStarting ? "unknown" : "down";
    const dot = document.getElementById(`arr-dot-${c.name}`);
    if (dot) { dot.classList.remove("up", "down", "unknown"); dot.classList.add(stateClass); }
    const qdot = document.getElementById(`qdot-${c.name}`);
    if (qdot) { qdot.classList.remove("up", "down", "unknown"); qdot.classList.add(stateClass); }
  }
}

async function refreshStatus() {
  try {
    await fetch("/api/status");
    setHudConn(true);
  } catch (_) {
    setHudConn(false);
  }
}

/* ---------- Clock + session uptime ---------- */
const sessionStart = Date.now();
function tickClock() {
  const el = document.getElementById("clock");
  el.textContent = new Date().toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  const elapsed = Math.floor((Date.now() - sessionStart) / 1000);
  const h = String(Math.floor(elapsed / 3600)).padStart(2, "0");
  const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, "0");
  const s = String(elapsed % 60).padStart(2, "0");
  const up = document.getElementById("uptime");
  if (up) up.textContent = `up ${h}:${m}:${s}`;
}

/* =====================================================================
   Command palette — Interaction model option C: the "doing" half of
   the split (viewing state is the panels above; triggering an action
   goes through here, reachable by fuzzy search regardless of where you
   are). Same list -> args -> confirm -> run flow as before, same
   manifest (static/commands.json); a running command's log now streams
   into the persistent right-column console instead of its own pane.
   ===================================================================== */
const consoleScreens = {
  list: document.getElementById("screen-list"),
  args: document.getElementById("screen-args"),
  confirm: document.getElementById("screen-confirm"),
  run: document.getElementById("screen-run"),
};

let commandRegistry = [];

function openPalette() {
  document.getElementById("palette-overlay").hidden = false;
  showConsoleScreen("list");
  const input = document.getElementById("console-filter");
  input.value = "";
  renderCommandList("");
  setTimeout(() => input.focus(), 30);
}

function closePalette() {
  document.getElementById("palette-overlay").hidden = true;
}

function showConsoleScreen(name) {
  for (const [key, el] of Object.entries(consoleScreens)) {
    if (el) el.hidden = key !== name;
  }
}

function wirePalette() {
  document.getElementById("palette-open").addEventListener("click", openPalette);
  document.querySelectorAll("[data-close]").forEach((btn) => btn.addEventListener("click", closePalette));
  document.getElementById("palette-overlay").addEventListener("click", (e) => {
    if (e.target.id === "palette-overlay") closePalette();
  });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      const overlay = document.getElementById("palette-overlay");
      overlay.hidden ? openPalette() : closePalette();
    } else if (e.key === "Escape" && !document.getElementById("palette-overlay").hidden) {
      closePalette();
    }
  });
  document.querySelectorAll("[data-back]").forEach((btn) => {
    btn.addEventListener("click", () => showConsoleScreen(btn.dataset.back));
  });
}

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
    if (cmd.Confirm) showConsoleConfirm(cmd, values);
    else runRegistryCommand(cmd, values);
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
  input.oninput = () => { yes.disabled = input.value.trim() !== cmd.Name; };
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
  try { parsed = JSON.parse(raw); } catch (_) { return { ok: false, message: raw, data: null, rawList: null }; }
  if (Array.isArray(parsed)) return { ok: status === 200, message: "", data: null, rawList: parsed };
  let data = parsed;
  if (data && typeof data.detail === "object" && data.detail !== null) data = data.detail;
  if (data && typeof data.message === "string") {
    const ok = typeof data.ok === "boolean" ? data.ok : status === 200;
    return { ok, message: data.message, data, rawList: null };
  }
  return { ok: status === 200, message: "", data, rawList: null };
}

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

async function runImportListAdd(cmd, values) {
  const spec = cmd.BodyFields;
  const path = prepareCommand(cmd, values).path;
  const fields = {};
  for (const f of spec.Fields || []) fields[f.Key] = argValue(cmd, values, f.ArgName);
  const search = spec.SearchArg ? argValue(cmd, values, spec.SearchArg) !== "no-search" : true;
  const body = {
    implementation: spec.Implementation,
    name: spec.NameArg ? argValue(cmd, values, spec.NameArg) : spec.Name,
    fields,
    search_on_add: search,
  };
  return callApi(cmd.Method, path, JSON.stringify(body));
}

async function execCommand(cmd, values) {
  if (cmd.BodyMode === "manual-import-by-index") return runManualImportByIndex(cmd, values);
  if (cmd.BodyMode === "log-levels-reset") return runLogLevelsReset(values);
  if (cmd.BodyMode === "letterboxd-filmography") return runLetterboxdFilmography(cmd, values);
  if (cmd.BodyMode === "letterboxd-popular") return runLetterboxdPopular(cmd);
  if (cmd.BodyMode === "import-list-add") return runImportListAdd(cmd, values);
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

  const container = resolveLogContainer(cmd, values);
  if (container) selectLogSource(container);

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
      if (key in item) { parts.push(String(item[key])); used.add(key); }
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

// Items a human has clicked a candidate for during the current review
// pass - "apply auto for the rest" skips these and uses candidate #1
// for everything else, so a manual pick is never silently overwritten.
const posterReviewDecided = new Set();

function posterCandidateCard(itemMsg, requestedSource) {
  const card = document.createElement("div");
  card.className = "poster-review-card";
  card.dataset.ratingKey = itemMsg.ratingKey;
  const label = itemMsg.year ? `${itemMsg.title} (${itemMsg.year})` : itemMsg.title;

  if (!itemMsg.candidates || itemMsg.candidates.length === 0) {
    card.innerHTML = `<div class="poster-review-title">${escapeHtml(label)}</div>
      <div class="poster-review-skip">no match in ${escapeHtml(requestedSource)} or its fallback — skipped</div>`;
    return card;
  }

  const fallbackNote = itemMsg.source && itemMsg.source !== requestedSource
    ? ` <span class="poster-review-fallback">(via ${escapeHtml(itemMsg.source)} fallback)</span>` : "";

  const thumbs = itemMsg.candidates.map((c, idx) => `
    <button type="button" class="poster-review-thumb" data-url="${escapeHtml(c.url)}" title="${escapeHtml(c.label || "")}">
      <img src="${escapeHtml(c.url)}" loading="lazy" alt="candidate ${idx + 1}">
      <span class="poster-review-thumb-label">${escapeHtml(c.label || `#${idx + 1}`)}</span>
    </button>`).join("");

  card.innerHTML = `<div class="poster-review-title">${escapeHtml(label)}${fallbackNote}</div>
    <div class="poster-review-thumbs">${thumbs}</div>
    <div class="poster-review-status"></div>`;

  card.querySelectorAll(".poster-review-thumb").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const status = card.querySelector(".poster-review-status");
      card.querySelectorAll(".poster-review-thumb").forEach((b) => b.classList.remove("poster-review-picked"));
      btn.classList.add("poster-review-picked");
      status.textContent = "applying…";
      try {
        await postAction("/api/posters/apply", { rating_key: itemMsg.ratingKey, url: btn.dataset.url });
        posterReviewDecided.add(itemMsg.ratingKey);
        status.textContent = "applied";
      } catch (e) {
        status.textContent = `failed: ${e.message}`;
      }
    });
  });

  return card;
}

function buildPosterSync() {
  const form = document.getElementById("poster-sync-form");
  if (!form) return;
  const summary = document.getElementById("poster-sync-summary");
  const submitBtn = form.querySelector("button[type=submit]");
  const modeSelect = document.getElementById("poster-sync-mode");
  const dryRunWrap = document.getElementById("poster-sync-dry-run-wrap");
  const logPane = document.getElementById("poster-log");
  const grid = document.getElementById("poster-review-grid");

  modeSelect.addEventListener("change", () => {
    dryRunWrap.hidden = modeSelect.value === "review";
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const library = document.getElementById("poster-sync-library").value;
    if (!library) return;
    const source = document.getElementById("poster-sync-source").value;
    const mode = modeSelect.value;

    logPane.textContent = "";
    logPane.hidden = mode === "review";
    grid.innerHTML = "";
    grid.hidden = mode !== "review";
    summary.textContent = "";
    submitBtn.disabled = true;
    closePosterStream();
    posterReviewDecided.clear();

    if (mode === "auto") {
      const dryRun = document.getElementById("poster-sync-dry-run").checked;
      try {
        const data = await postAction("/api/posters/sync", { library, dry_run: dryRun, source });
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
      return;
    }

    // Review mode: stream per-item candidates, render a picker grid.
    // Items nobody clicks stay unapplied until "Apply auto for the rest".
    const pending = [];
    try {
      const data = await postAction("/api/posters/review", { library, source });
      logLine("pending", data.message);
      summary.innerHTML = 'streaming candidates… <button type="button" class="btn-ghost" id="poster-apply-auto-rest">Apply auto for the rest</button>';
      document.getElementById("poster-apply-auto-rest").addEventListener("click", async (e) => {
        e.target.disabled = true;
        e.target.textContent = "applying…";
        for (const item of pending) {
          if (posterReviewDecided.has(item.ratingKey) || !item.candidates.length) continue;
          const card = grid.querySelector(`[data-rating-key="${item.ratingKey}"]`);
          const status = card?.querySelector(".poster-review-status");
          try {
            await postAction("/api/posters/apply", { rating_key: item.ratingKey, url: item.candidates[0].url });
            posterReviewDecided.add(item.ratingKey);
            if (status) status.textContent = "applied (auto)";
            card?.querySelector(".poster-review-thumb")?.classList.add("poster-review-picked");
          } catch (err) {
            if (status) status.textContent = `failed: ${err.message}`;
          }
        }
        e.target.textContent = "Done";
      });

      activePosterSource = new EventSource("/api/posters/review/stream");
      activePosterSource.onmessage = (evt) => {
        const msg = JSON.parse(evt.data);
        if (msg.type === "item") {
          pending.push(msg);
          grid.appendChild(posterCandidateCard(msg, source));
        } else if (msg.type === "error") {
          logLine("err", `Poster review — ${msg.message}`);
          closePosterStream();
          submitBtn.disabled = false;
        } else if (msg.type === "done") {
          logLine("ok", `Poster review — ${pending.length} item(s) loaded, pick a poster or apply auto for the rest.`);
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
      logLine("err", `Poster review — ${e.message}`);
      submitBtn.disabled = false;
    }
  });

  loadPosterLibraries();
}

/* ---------- Boot ---------- */
wireLogConsole();
buildQuickLinks();
buildPrimaryActions();
buildArrFleet();
buildHostVitals();
buildHostActions();
buildPosterDock();
buildDocLinks();
buildSkillsList();
buildPlexUpdateCheck();
wirePalette();
loadCommandRegistry();
tickClock();
setInterval(tickClock, 1000);
refreshStatus();
setInterval(refreshStatus, 20000);
refreshFleet();
setInterval(refreshFleet, 15000);
logLine("ok", "Control panel ready.");
