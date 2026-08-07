/* Host rail — two lanes plus a live resource strip. Vitals are read-only
   checks this container can genuinely answer from its own mounts
   (docker.sock, /host-config, /mnt, /host-backups, and - since
   2026-07-26's Plex Health mount - /host-proc for real host-wide CPU/
   RAM). Package updates / reboot-needed are still NOT here: pid:host and
   /host-proc give real *readable* host state, but this container has no
   pacman and no privileged path to actually change the host (install
   packages, reboot) - that's a genuine open design question (a host-side
   helper this panel could trigger but never bypass), not built yet. See
   the design-treatment artifact's Phase 02/03 risk table. */
import { escapeHtml, postAction, setStatusLine } from "./core.js";
import { logLine } from "./activity-log.js";
import { fetchAndRender } from "./result-render.js";
import { armButton } from "./buttons.js";
import { refreshStatus } from "./status.js";

const HOST_VITALS = [
  { id: "mount-health", label: "Mount health", desc: "Every known FUSE mountpoint under /mnt, checked for a clean listing.", path: "/api/mount-health" },
  { id: "oom-check", label: "OOM kills", desc: "Containers Docker has ever recorded an OOM-kill flag for.", path: "/api/oom-check" },
  { id: "resource-check", label: "Resource limits", desc: "Containers missing an explicit mem_limit or cpus.", path: "/api/resource-check" },
  { id: "disk-usage", label: "Config disk usage", desc: "Per-app config/ directory size, largest first.", path: "/api/disk-usage" },
  { id: "backup-verify", label: "Backup verify", desc: "Latest restic snapshot age and repo integrity summary.", path: "/api/backup-verify" },
  { id: "backup-status", label: "Backup history", desc: "Full snapshot history for both repos - catches one that stopped pruning or only ever ran once.", path: "/api/backup-status" },
  { id: "backup-restore-test", label: "Backup restore test", desc: "Pulls one real file out of the latest snapshot - proves restore actually works, not just that a snapshot exists.", path: "/api/backup-restore-test", method: "POST" },
  { id: "disk-health", label: "Disk health", desc: "Host mount free space plus reclaimable space from unused Docker images/volumes/build cache.", path: "/api/disk-health" },
];

export function buildHostVitals() {
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
        await fetchAndRender(result, v.method || "GET", v.path);
        logLine("ok", `${v.label} — loaded`);
      } catch (e) {
        logLine("err", `${v.label} — ${e.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  }
}

export function buildHostActions() {
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

  const pruneRow = document.createElement("div");
  pruneRow.className = "rule-row";
  pruneRow.innerHTML = `
    <div class="rule-main">
      <span class="rule-title">Prune unused Docker space</span>
      <span class="rule-desc">Dangling images and zero-refcount volumes only - never a running or stopped-but-referenced container's own image/volume.</span>
    </div>
    <div class="rule-actions"><button class="btn-ghost" type="button">Prune</button></div>
    <div class="rule-status" id="status-disk-prune">—</div>
  `;
  wrap.appendChild(pruneRow);
  const pruneBtn = pruneRow.querySelector("button");
  const pruneStatus = pruneRow.querySelector(".rule-status");
  armButton(pruneBtn, "Prune", "Click again to confirm", async () => {
    pruneBtn.disabled = true;
    setStatusLine(pruneStatus, "pending", "Pruning…");
    logLine("pending", "Disk prune — requested");
    try {
      const data = await postAction("/api/disk-health/prune", { confirm: true });
      setStatusLine(pruneStatus, "success", data.message);
      logLine("ok", `Disk prune — ${data.message}`);
    } catch (e) {
      setStatusLine(pruneStatus, "error", e.message);
      logLine("err", `Disk prune — ${e.message}`);
    } finally {
      pruneBtn.disabled = false;
    }
  });
}

/* Live resource strip - polls /api/host-resources every 5s and keeps a
   short rolling buffer per metric to draw as an inline sparkline. Plain
   polling, not SSE: this is a point-in-time gauge refreshing on a fixed
   cadence, not a long-running background job streaming progress - SSE
   earns its keep for poster-sync's kind of job, not this one. */
const RESOURCE_HISTORY_LEN = 24;
const cpuHistory = [];
const memHistory = [];

function sparklinePath(values, height = 34) {
  if (values.length < 2) return { line: "", fill: "" };
  const max = Math.max(100, ...values);
  const stepX = 100 / (values.length - 1);
  const points = values.map((v, i) => [i * stepX, height - (v / max) * height]);
  const line = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const fill = `${line} L100,${height} L0,${height} Z`;
  return { line, fill };
}

function renderSparkline(svgEl, values) {
  const { line, fill } = sparklinePath(values);
  svgEl.querySelector(".sparkline-fill").setAttribute("d", fill);
  svgEl.querySelector(".sparkline-line").setAttribute("d", line);
}

export function buildHostResources() {
  const wrap = document.getElementById("host-resources");
  if (!wrap) return;
  wrap.innerHTML = `
    <div class="sparkline-row">
      <div class="sparkline-block">
        <span class="sparkline-label">CPU <b id="host-cpu-val">—</b></span>
        <svg class="sparkline" viewBox="0 0 100 34" preserveAspectRatio="none"><path class="sparkline-fill"></path><path class="sparkline-line"></path></svg>
      </div>
      <div class="sparkline-block sparkline-ram">
        <span class="sparkline-label">RAM <b id="host-ram-val">—</b></span>
        <svg class="sparkline" viewBox="0 0 100 34" preserveAspectRatio="none"><path class="sparkline-fill"></path><path class="sparkline-line"></path></svg>
      </div>
    </div>
    <p class="hint" id="host-resources-hint"></p>
  `;
}

export async function refreshHostResources() {
  const wrap = document.getElementById("host-resources");
  if (!wrap || wrap.innerHTML === "") return;
  try {
    const res = await fetch("/api/host-resources");
    if (res.status === 503) {
      document.getElementById("host-resources-hint").textContent = "Host /proc mount not available.";
      return;
    }
    if (!res.ok) throw new Error(`Request failed (${res.status})`);
    const data = await res.json();
    cpuHistory.push(data.cpu_percent);
    memHistory.push(data.mem_percent);
    if (cpuHistory.length > RESOURCE_HISTORY_LEN) cpuHistory.shift();
    if (memHistory.length > RESOURCE_HISTORY_LEN) memHistory.shift();
    document.getElementById("host-cpu-val").textContent = `${data.cpu_percent}%`;
    document.getElementById("host-ram-val").textContent = `${data.mem_percent}%`;
    document.getElementById("host-resources-hint").textContent = `${data.mem_used} / ${data.mem_total} RAM`;
    renderSparkline(wrap.querySelector(".sparkline-block:not(.sparkline-ram) svg"), cpuHistory);
    renderSparkline(wrap.querySelector(".sparkline-ram svg"), memHistory);
  } catch (e) {
    logLine("err", `Host resources — ${e.message}`);
  }
}
