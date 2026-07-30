/* Host rail — two lanes. Vitals are read-only checks this container can
   genuinely answer from its own mounts (docker.sock, /host-config,
   /mnt, /host-backups). Package updates / reboot-needed / mem-pressure
   / zombie-check are deliberately NOT here: this container has no
   pacman, no pid:host, and no real host /proc — building those as live
   tiles would show container-scoped or fake data as if it were the
   host's. They stay terminal-only; see the Reference rail below. */
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
}
