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
  { id: "radarr", label: "Radarr" },
  { id: "sonarr", label: "Sonarr" },
  { id: "lidarr", label: "Lidarr" },
  { id: "readarr", label: "Readarr" },
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

async function postAction(url) {
  const res = await fetch(url, { method: "POST" });
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
    grid.appendChild(card);
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
      <div class="arr-status" id="arr-status-${app.id}">—</div>
      <div class="arr-actions">
        <button class="btn-ghost" data-action="rss-sync" type="button">RSS sync</button>
        <button class="btn-ghost" data-action="search-missing" type="button">Search missing</button>
      </div>
    `;
    const status = row.querySelector(".arr-status");
    row.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const action = btn.dataset.action;
        const label = action === "rss-sync" ? "RSS sync" : "Search missing";
        row.querySelectorAll("button").forEach((b) => (b.disabled = true));
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
          row.querySelectorAll("button").forEach((b) => (b.disabled = false));
        }
      });
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
buildChipGrid();
tickClock();
setInterval(tickClock, 1000);
refreshStatus();
logLine("ok", "Control panel ready.");
