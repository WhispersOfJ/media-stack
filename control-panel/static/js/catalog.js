/* Software Catalog — curated install/remove, Phase 02 of the v3 design
   treatment. Cards are grouped by category, each with an install/remove
   action that goes through armButton's click-twice confirm (same guard
   every other real side effect in this app uses) before calling the
   catalog API with confirm:true. */
import { escapeHtml, postAction, setStatusLine } from "./core.js";
import { logLine } from "./activity-log.js";
import { armButton } from "./buttons.js";

const STATUS_LABEL = {
  not_installed: null,
  running: "Installed",
  exited: "Stopped",
  created: "Created",
};

function monogram(name) {
  return name.replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase();
}

async function loadCatalog() {
  const res = await fetch("/api/catalog");
  if (!res.ok) throw new Error(`Catalog load failed (${res.status})`);
  return res.json();
}

function formatDetails(item) {
  const envLines = Object.keys(item.environment).length
    ? Object.entries(item.environment)
        .map(([k, v]) => `<div class="catalog-detail-row"><code>${escapeHtml(k)}</code>: ${escapeHtml(String(v))}</div>`)
        .join("")
    : `<div class="catalog-detail-row hint">No environment variables.</div>`;
  const volLines = Object.keys(item.volumes).length
    ? Object.entries(item.volumes)
        .map(([name, v]) => `<div class="catalog-detail-row"><code>${escapeHtml(name)}</code> → <code>${escapeHtml(v.bind)}</code> (${escapeHtml(v.mode)})</div>`)
        .join("")
    : `<div class="catalog-detail-row hint">No volume mounts.</div>`;
  return `
    <div class="catalog-detail-group">
      <span class="catalog-detail-label">Environment</span>
      ${envLines}
    </div>
    <div class="catalog-detail-group">
      <span class="catalog-detail-label">Volumes</span>
      ${volLines}
    </div>
  `;
}

function renderCard(item) {
  const card = document.createElement("div");
  card.className = "glass-card catalog-card";
  const installed = item.status !== "not_installed";
  const badge = STATUS_LABEL[item.status] || item.status;

  card.innerHTML = `
    <div class="catalog-card-top">
      <span class="catalog-badge">${escapeHtml(monogram(item.name))}</span>
      <div class="catalog-card-name">
        <span class="rule-title">${escapeHtml(item.name)}</span>
        <a class="doc-link-ext" href="${escapeHtml(item.doc_url)}" target="_blank" rel="noopener">docs ↗</a>
      </div>
      ${installed ? `<span class="lb-pill lb-pill-fresh">${escapeHtml(badge)}</span>` : ""}
    </div>
    <p class="rule-desc catalog-pitch">${escapeHtml(item.pitch)}</p>
    ${item.caveat ? `<p class="hint catalog-caveat">${escapeHtml(item.caveat)}</p>` : ""}
    <div class="catalog-card-foot">
      <span class="footprint">${escapeHtml(item.footprint)}${item.ports.length ? ` · port ${item.ports.join(", ")}` : ""}</span>
      <div class="catalog-card-actions"></div>
    </div>
    <button type="button" class="catalog-details-toggle" aria-expanded="false">Details ▾</button>
    <div class="catalog-details-panel" hidden>${formatDetails(item)}</div>
    <div class="rule-status catalog-status" hidden>—</div>
  `;

  const toggle = card.querySelector(".catalog-details-toggle");
  const panel = card.querySelector(".catalog-details-panel");
  toggle.addEventListener("click", () => {
    const isOpen = !panel.hidden;
    panel.hidden = isOpen;
    toggle.setAttribute("aria-expanded", String(!isOpen));
    toggle.textContent = isOpen ? "Details ▾" : "Details ▴";
  });

  const actions = card.querySelector(".catalog-card-actions");
  const status = card.querySelector(".catalog-status");

  if (!installed) {
    const btn = document.createElement("button");
    btn.className = "btn-primary";
    actions.appendChild(btn);
    armButton(btn, "Install", "Confirm install", async () => {
      btn.disabled = true;
      status.hidden = false;
      setStatusLine(status, "pending", "Pulling image and starting…");
      logLine("pending", `Catalog: install ${item.name} — requested`);
      try {
        const data = await postAction(`/api/catalog/${item.id}/install`, { confirm: true });
        setStatusLine(status, "success", data.message);
        logLine("ok", `Catalog: install ${item.name} — ${data.message}`);
        buildCatalog();
      } catch (e) {
        setStatusLine(status, "error", e.message);
        logLine("err", `Catalog: install ${item.name} — ${e.message}`);
        btn.disabled = false;
      }
    });
  } else {
    const btn = document.createElement("button");
    btn.className = "btn-danger";
    actions.appendChild(btn);
    armButton(btn, "Remove", "Confirm remove", async () => {
      btn.disabled = true;
      status.hidden = false;
      setStatusLine(status, "pending", "Stopping and removing…");
      logLine("pending", `Catalog: remove ${item.name} — requested`);
      try {
        const data = await postAction(`/api/catalog/${item.id}/remove`, { confirm: true, remove_volumes: false });
        setStatusLine(status, "success", data.message);
        logLine("ok", `Catalog: remove ${item.name} — ${data.message}`);
        buildCatalog();
      } catch (e) {
        setStatusLine(status, "error", e.message);
        logLine("err", `Catalog: remove ${item.name} — ${e.message}`);
        btn.disabled = false;
      }
    });
  }

  return card;
}

export async function buildCatalog() {
  const wrap = document.getElementById("catalog-grid");
  if (!wrap) return;
  try {
    const data = await loadCatalog();
    const byCategory = new Map();
    for (const item of data.items) {
      if (!byCategory.has(item.category)) byCategory.set(item.category, []);
      byCategory.get(item.category).push(item);
    }
    wrap.innerHTML = "";
    for (const [category, items] of byCategory) {
      const heading = document.createElement("h3");
      heading.className = "rail-sub";
      heading.textContent = category;
      wrap.appendChild(heading);
      const grid = document.createElement("div");
      grid.className = "catalog-grid";
      for (const item of items) grid.appendChild(renderCard(item));
      wrap.appendChild(grid);
    }
  } catch (e) {
    wrap.innerHTML = `<p class="hint error">${escapeHtml(e.message)}</p>`;
  }
}
