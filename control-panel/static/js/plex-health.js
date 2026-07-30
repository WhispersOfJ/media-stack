/* Plex Health - live scan status + tiered mitigations. Session-only
   ring buffers feed the two sparklines (no server-side time-series
   exists anywhere in this app - see the boot block for the poll
   interval this matches the Fleet rail's own 15s cadence). */
import { escapeHtml, setStatusLine } from "./core.js";
import { logLine } from "./activity-log.js";
import { armButton } from "./buttons.js";

const PLEX_HEALTH_HISTORY_MAX = 60; // ~15 min at 15s polling
const plexProgressHistory = [];
const plexBusyDbHistory = [];

function renderSparkline(svgEl, samples, { min = 0, max = 100 } = {}) {
  if (!samples.length) {
    svgEl.innerHTML = "";
    return;
  }
  const w = 200, h = 40;
  const range = Math.max(max - min, 1);
  const points = samples.map((v, i) => {
    const x = samples.length === 1 ? w : (i / (samples.length - 1)) * w;
    const y = h - ((Math.min(Math.max(v, min), max) - min) / range) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  svgEl.innerHTML = `<polyline points="${points}" fill="none" stroke="var(--accent)" stroke-width="1.5" />`;
}

function plexHealthStateBadgeClass(state) {
  if (state === "hung_confirmed") return "state-error";
  if (state === "stalled_suspected") return "state-pending";
  return "state-success";
}

export function buildPlexHealth() {
  const wrap = document.getElementById("plex-health-actions");

  // All three quick-action buttons that used to live here were removed 2026-07-28:
  // "Restart Mount Cascade" and "Force Unstick" called into the BearMount-specific
  // ffprobe/D-state hang subsystem (/api/plex/restart-cascade, /api/plex/unstick),
  // which was removed along with BearMount itself - NzbDAV's mount is a stock rclone
  // sidecar (nzbdav_rclone) with no confirmed equivalent hang class (see STACK.md's
  // History); re-add here if one is ever confirmed. "Restart Plex" (plain
  // /api/container/plex/restart) was removed from the UI the same day because the
  // server-side route now rejects that call unless activated=true is passed
  // explicitly - a button that can only ever fail isn't worth keeping; use the API
  // directly with activated=true when a Plex restart is genuinely intended.
  const rows = [];

  if (rows.length === 0) {
    wrap.innerHTML = `<p class="rule-desc">No mitigation buttons available here - Plex restart requires activated=true via the API directly (not exposed as a plain click), and the mount-cascade/unstick actions were removed with BearMount.</p>`;
    return;
  }

  for (const row of rows) {
    const el = document.createElement("div");
    el.className = "rule-row";
    el.innerHTML = `
      <div class="rule-main">
        <span class="rule-title">${escapeHtml(row.title)}</span>
        <span class="rule-desc">${escapeHtml(row.desc)}</span>
      </div>
      <div class="rule-actions"><button class="${row.danger ? "btn-danger" : "btn-primary"}" type="button"></button></div>
      <div class="rule-status" id="status-${row.id}">—</div>
    `;
    wrap.appendChild(el);
    const btn = el.querySelector("button");
    const status = el.querySelector(".rule-status");
    armButton(btn, row.idle, row.armed, async () => {
      btn.disabled = true;
      setStatusLine(status, "pending", "Running…");
      logLine("pending", `${row.title} — requested`);
      try {
        const data = await row.run();
        setStatusLine(status, "success", data.message);
        logLine("ok", `${row.title} — ${data.message}`);
      } catch (e) {
        setStatusLine(status, "error", e.message);
        logLine("err", `${row.title} — ${e.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  }
}

export async function refreshPlexHealth() {
  let data;
  try {
    const res = await fetch("/api/plex/scan-health");
    const parsed = await res.json();
    data = parsed?.detail ?? parsed;
    if (!res.ok) throw new Error(data.message || "scan-health check failed");
  } catch (e) {
    document.getElementById("plex-health-state").textContent = "unknown";
    document.getElementById("plex-health-state-sub").textContent = e.message;
    return;
  }

  const stateEl = document.getElementById("plex-health-state");
  stateEl.textContent = data.state.replace(/_/g, " ");
  stateEl.className = `vital-value ${plexHealthStateBadgeClass(data.state)}`;
  document.getElementById("plex-health-state-sub").textContent =
    data.dstate_threads.length ? `${data.dstate_threads.length} D-state thread(s)` :
    !data.mount_ok ? "mount unresponsive" :
    data.fuse_waiting > 3 ? `${data.fuse_waiting} FUSE requests waiting` : "";

  const scanActivity = data.activities.find(a => a.type === "library.update.section");
  const progress = scanActivity ? scanActivity.progress : null;
  document.getElementById("plex-health-progress").textContent = progress === null ? "idle" : `${progress}%`;
  document.getElementById("plex-health-progress-sub").textContent = scanActivity ? (scanActivity.subtitle || scanActivity.title) : "";

  const q = data.nzbdav_queue;
  document.getElementById("plex-health-queue").textContent = String(q.pending ?? 0);
  document.getElementById("plex-health-queue-sub").textContent = q.processing ? `${q.processing} processing` : "";

  document.getElementById("plex-health-restarts").textContent = String(data.container.restart_count ?? 0);
  document.getElementById("plex-health-restarts-sub").textContent = data.container.health || "";

  document.getElementById("plex-health-log").textContent = (data.log_tail || []).join("\n");

  plexProgressHistory.push(progress ?? 0);
  if (plexProgressHistory.length > PLEX_HEALTH_HISTORY_MAX) plexProgressHistory.shift();
  renderSparkline(document.getElementById("spark-progress"), plexProgressHistory, { min: 0, max: 100 });

  plexBusyDbHistory.push(data.recent_busy_db_errors ?? 0);
  if (plexBusyDbHistory.length > PLEX_HEALTH_HISTORY_MAX) plexBusyDbHistory.shift();
  const maxBusy = Math.max(...plexBusyDbHistory, 1);
  renderSparkline(document.getElementById("spark-busydb"), plexBusyDbHistory, { min: 0, max: maxBusy });
}
