/* Poster sync dock — auto mode (server picks + applies) and review mode
   (server streams per-item candidates, human picks or bulk-applies the
   top match for whatever's left undecided). */
import { escapeHtml, postAction } from "./core.js";
import { logLine } from "./activity-log.js";

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

export function buildPosterSync() {
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

export function buildPosterDock() {
  document.getElementById("poster-dock-close").addEventListener("click", () => {
    document.getElementById("poster-dock").hidden = true;
    closePosterStream();
  });
  buildPosterSync();
}
