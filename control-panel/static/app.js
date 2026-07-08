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

const ARR_APPS = [
  { id: "radarr", label: "Radarr", port: 7878 },
  { id: "sonarr", label: "Sonarr", port: 8989 },
  { id: "lidarr", label: "Lidarr", port: 8686 },
  { id: "readarr", label: "Readarr", port: 8787 },
];

const RESTARTABLE = [
  { id: "radarr", label: "Radarr", sub: "fixes stale Zurg mount (v4.0.1)" },
  { id: "sonarr", label: "Sonarr" },
  { id: "lidarr", label: "Lidarr" },
  { id: "readarr", label: "Readarr" },
  { id: "bazarr", label: "Bazarr" },
  { id: "prowlarr", label: "Prowlarr" },
  { id: "plex", label: "Plex" },
  { id: "zurg", label: "Zurg", sub: "Real-Debrid mount" },
  { id: "rclone-alldebrid", label: "rclone", sub: "AllDebrid mount" },
  { id: "decypharr", label: "Decypharr" },
  { id: "nzbget", label: "NZBGet" },
  { id: "seerr", label: "Seerr" },
  { id: "tautulli", label: "Tautulli" },
  { id: "byparr", label: "Byparr" },
  { id: "kometa", label: "Kometa" },
  { id: "zilean", label: "Zilean" },
];

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
      </div>
    `;
    const status = row.querySelector(".arr-status");
    row.querySelectorAll(".arr-actions button").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const action = btn.dataset.action;
        const label = action === "rss-sync" ? "RSS sync" : "Search missing";
        row.querySelectorAll(".arr-actions button").forEach((b) => (b.disabled = true));
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
          row.querySelectorAll(".arr-actions button").forEach((b) => (b.disabled = false));
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
  }
}

/* ---------- Service restart chips ---------- */
function buildChipGrid() {
  const grid = document.getElementById("chip-grid");
  for (const svc of RESTARTABLE) {
    const chip = document.createElement("div");
    chip.className = "chip";
    chip.innerHTML = `
      <span class="lamp unknown" id="lamp-${svc.id}"></span>
      <span class="chip-name">${svc.label}${svc.sub ? `<span class="chip-sub">${svc.sub}</span>` : ""}</span>
      <button class="btn-icon" type="button" title="Restart ${svc.label}">${svg("restart")}</button>
    `;
    const btn = chip.querySelector("button");
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.classList.add("spinning");
      logLine("pending", `${svc.label} — restart requested`);
      try {
        const data = await postAction(`/api/container/${svc.id}/restart`);
        logLine("ok", `${svc.label} — ${data.message}`);
        refreshStatus();
      } catch (e) {
        logLine("err", `${svc.label} — ${e.message}`);
      } finally {
        btn.disabled = false;
        btn.classList.remove("spinning");
      }
    });
    grid.appendChild(chip);
  }
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
    const lamp = document.getElementById(`lamp-${name}`);
    if (!lamp) continue;
    lamp.classList.remove("up", "down", "unknown");
    if (info.state === "running" && (info.health === "healthy" || info.health == null)) {
      lamp.classList.add("up");
    } else if (info.state === "running" && info.health === "starting") {
      lamp.classList.add("unknown");
    } else {
      lamp.classList.add("down");
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

buildPrimaryGrid();
buildArrList();
buildZileanSearch();
buildChipGrid();
buildDangerZone();
tickClock();
setInterval(tickClock, 1000);
refreshStatus();
setInterval(refreshStatus, 20000);
logLine("ok", "Control panel ready.");
