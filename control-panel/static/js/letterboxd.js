/* Letterboxd tracked-list management + sync history — mirrors
   loop-remediation.js's toolbar-row/on-demand-panel pattern: nothing here
   polls, every view is a manual "Show" click, same as every other
   fleet-rail subsystem. */
import { escapeHtml, postAction } from "./core.js";
import { logLine } from "./activity-log.js";
import { fetchAndRender } from "./result-render.js";

export function buildLetterboxdPanel() {
  const wrap = document.getElementById("letterboxd-panel");
  if (!wrap) return;

  const form = document.createElement("form");
  form.className = "arr-actions-row";
  form.innerHTML = `
    <span class="arr-actions-row-label">Track a list</span>
    <input type="url" placeholder="https://letterboxd.com/<user>/watchlist/" required data-track-url style="flex: 1; min-width: 240px;">
    <input type="text" placeholder="Label (optional)" data-track-label style="max-width: 200px;">
    <button class="btn-ghost" type="submit">Track</button>
  `;
  wrap.appendChild(form);

  const toolbarRow = document.createElement("div");
  toolbarRow.className = "arr-actions-row";
  toolbarRow.innerHTML = `
    <span class="arr-actions-row-label">Letterboxd</span>
    <button class="btn-ghost" data-lb="tracked" type="button">Tracked lists</button>
    <button class="btn-ghost" data-lb="history" type="button">Sync history</button>
  `;
  const panel = document.createElement("div");
  panel.className = "arr-panel";
  panel.hidden = true;
  wrap.appendChild(toolbarRow);
  wrap.appendChild(panel);

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const url = form.querySelector("[data-track-url]").value.trim();
    const label = form.querySelector("[data-track-label]").value.trim();
    logLine("pending", `Letterboxd track — ${url}`);
    try {
      await postAction("/api/arr/letterboxd/track", label ? { url, label } : { url });
      logLine("ok", `Letterboxd track — now tracking ${url}`);
      form.reset();
      if (!panel.hidden && panel.dataset.lbView === "tracked") await showTracked(panel);
    } catch (e) {
      logLine("err", `Letterboxd track — ${e.message}`);
    }
  });

  toolbarRow.querySelectorAll("[data-lb]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const wasOpen = btn.classList.contains("active") && !panel.hidden;
      toolbarRow.querySelectorAll("[data-lb]").forEach((b) => b.classList.remove("active"));
      if (wasOpen) { panel.hidden = true; return; }
      btn.classList.add("active");
      const view = btn.dataset.lb;
      logLine("pending", `Letterboxd ${view} — requested`);
      try {
        if (view === "tracked") {
          panel.dataset.lbView = "tracked";
          await showTracked(panel);
        } else {
          panel.dataset.lbView = "history";
          await fetchAndRender(panel, "GET", "/api/arr/letterboxd/history");
        }
        logLine("ok", `Letterboxd ${view} — loaded`);
      } catch (e) {
        logLine("err", `Letterboxd ${view} — ${e.message}`);
      }
    });
  });
}

async function showTracked(panel) {
  panel.hidden = false;
  panel.innerHTML = `<div class="hint">Loading…</div>`;
  const res = await fetch("/api/arr/letterboxd/tracked");
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail?.message || data?.message || `Request failed (${res.status})`);
  renderTracked(panel, data.lists || []);
}

function renderTracked(panel, lists) {
  if (!lists.length) {
    panel.innerHTML = `<div class="hint">No tracked lists yet — track one above.</div>`;
    return;
  }
  const rows = lists.map((l) => `
    <tr>
      <td>${escapeHtml(l.label || l.url)}</td>
      <td>${escapeHtml(l.lastSyncedAt || "never")}</td>
      <td><button class="btn-ghost" data-untrack-url="${escapeHtml(l.url)}" type="button">Untrack</button></td>
    </tr>`).join("");
  panel.innerHTML = `
    <div class="result-table-wrap">
      <table class="result-table">
        <thead><tr><th>List</th><th>Last synced</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  panel.querySelectorAll("[data-untrack-url]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const url = btn.dataset.untrackUrl;
      logLine("pending", `Letterboxd untrack — ${url}`);
      try {
        await postAction("/api/arr/letterboxd/untrack", { url });
        logLine("ok", `Letterboxd untrack — stopped tracking ${url}`);
        await showTracked(panel);
      } catch (e) {
        logLine("err", `Letterboxd untrack — ${e.message}`);
      }
    });
  });
}
