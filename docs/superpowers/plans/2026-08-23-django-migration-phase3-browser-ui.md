# FastAPI→Django Migration — Phase 3: Django Template + htmx Browser UI — Implementation Plan

> **Status: COMPLETE** (2026-08-23) — see `docs/superpowers/plans/2026-08-23-django-migration-phase3-closeout.md`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static HTML/JS SPA (the ~2900-line `control-panel/static/` client) with a server-rendered Django template UI + htmx partial swaps, one template per page, per the confirmed mockup: dense card grid (4 cards/row), monospace stat lines per card, status dot, thin nav bar, log strip below the grid. Template views call the Phase 2 `services.py` functions **directly server-side** (never re-fetching `/api/v2/*` from the browser) — that is why the spec made `services.py` framework-agnostic. No fish CLI changes (Phase 4) and no deployment/cutover (Phase 5) in this phase; the old FastAPI SPA stays in place and live until cutover — **nothing under `control-panel/static/` is deleted in this phase**.

**Architecture:** A new `ui` app owns the page shell — `base.html` (thin nav bar, log strip, status-dot header), vendored htmx + `style.css` under `ui/static/`, the root `/` route, and the cross-app pages (Overview, Settings, Reference, Activity Log). Each existing service app that has a UI page (host, arr, plex, posters, letterboxd, mdblist, queue_app) gains a `views.py` with Django template views + htmx partial-fragment views, a `templates/<app>/` directory, and an app-level `urls.py` mounted under `/` — alongside its existing `api/urls.py` mounted under `/api/v2/<app>/`. Template views reuse the Phase 1/2 session auth: a tiny `login_required` decorator redirects to the existing `auth_app/login.html` when `request.session["user_id"]` is absent, and the two-tier session-only split for destructive actions (host settings PATCH, reboot, prune, manual-import, blocklist) is preserved exactly as in the API tier. The command palette (`commands.json` + `palette.js`, ~1/3 of the current UI) is **deferred to Phase 4**: the design spec's Browser UI section (thin nav + log strip + htmx actions, no palette) is the design of record, and the palette's registry of 280 fish operations only makes sense once Phase 4 redefines the CLI contract. A minimal "recent activity" log strip (from the SSE/activity stream) ships here instead.

**Tech Stack:** Django 5.2 + built-in template engine (`APP_DIRS=True` — no new templating dependency), htmx 2.x (single file **vendored into `ui/static/vendor/htmx.min.js` — no CDN**; this is a private LAN stack), existing pytest-django + pytest-cov + DRF `APIClient` for tests (template views tested via Django's `Client` with rendered-HTML assertions). No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-08-21-fastapi-to-django-migration-design.md` (Browser UI + Testing + Django project layout sections).

## Global Constraints

- **Template views call `services.py` directly, never the HTTP API.** The spec's `services.py` is framework-agnostic precisely so template views and DRF views share one code path. A template view is a thin function that calls e.g. `host.services.host_resources()` and renders a fragment — it does not `httpx.get("http://localhost:8420/api/v2/host/host-resources")`. This keeps auth, envelopes, and latency out of the browser path and is what makes the htmx partials cheap.
- **Keep the FastAPI-era SPA untouched and live.** `control-panel/static/` is served by the still-running FastAPI app until the Phase 5 cutover. Phase 3 only *builds the new UI beside it*; do not delete, rename, or edit the old JS/HTML except to add a one-line banner link if a page is ready to preview (optional, and revert before cutover).
- **Preserve the two-tier auth split** exactly as in the API tier: read-only + automation-invoked pages render for any session user; irreversible/admin actions (host `settings` PATCH, `disk-health/prune`, reboot/pacman, arr `manual-import`/`blocklist`, posters destructive ops) require the session tier — i.e. the template buttons for those call services guarded the same way the API views guard them, and the *view* re-checks session-only for those POSTs regardless of what the button looks like. Get this wrong and the UI silently grants what the API denies.
- **CSRF is mandatory on every htmx POST.** Django template views enforce `CsrfViewMiddleware`. Each page's `<head>` carries `<meta name="csrf-token" content="{{ csrf_token }}">` and htmx is configured once in `base.html` to send it as `X-CSRFToken` (standard htmx+HTMX headers pattern — verify the exact mechanism with the vendored version's docs during Task 0, and add a test that a POST without the token is rejected 403).
- **Session-only, no service-key on the UI.** The browser UI authenticates exclusively via the session (X-Api-Key is for the fish CLI). Template views must never accept `X-Api-Key`; the `login_required` decorator checks the session only.
- **No chart library.** `sparkline.js` (and the status-dot pulse) become server-rendered inline SVG generated by the template/view — no new JS dependency beyond htmx.
- **App-level `urls.py` naming:** the spec says two routers per app; existing apps already use `api/urls.py` (mounted at `/api/v2/<app>/`). Phase 3 adds a *second* app-level `urls.py` for template routes mounted at `/` — do **not** rename the existing `api/urls.py` files (avoid churn; the API mount stays as-is).
- **Verify the `/api/v2/host/` double-include before relying on it:** `config/urls.py` mounts both `host_actions.api.urls` and `host.api.urls` under `/api/v2/host/` (verified non-colliding at plan time — `reboot|pacman-*` vs `status|containers|...` are distinct leaf paths — but if any new host template view needs an API path, keep it distinct). Renaming `host_actions` to its own prefix is a cleanup for a later phase, not this one.
- **80%+ coverage per app via `pytest --cov`** (CLAUDE.md floor), now including template views: rendered-HTML assertions (page renders, auth-redirect, key stat present) + htmx partial-response assertions (fragment returns, action POST swaps the target). View tests mock `services.py` — they do not hit real Radarr/Plex/Docker/httpx.
- **TEMPLATES `DIRS` stays empty** — per-app `templates/<app>/` via `APP_DIRS=True`, matching Phase 1's `auth_app/templates/auth_app/login.html`. No project-level templates dir.
- **No task-queue infrastructure** (Celery/Redis) — htmx polling (`hx-trigger="every 15s"`) replaces the SPA's `setInterval`, and the existing `threading.Thread` background jobs in `posters.services` keep working unchanged.

## File Structure (new/changed, under `control-panel-django/`)

```
ui/
  __init__.py  apps.py
  views.py                 # shell + cross-app pages (overview, settings, reference, activity log)
  urls.py                  # mounted at "/" — includes per-app page routes
  templates/ui/base.html   # nav bar, log strip, status dot, htmx boot, csrf meta
  templates/ui/overview.html  settings.html  reference.html  activity_log.html  + partials/
  static/vendor/htmx.min.js
  static/css/style.css     # port of control-panel/static/style.css to the mockup
  tests/test_views.py  tests/test_partials.py
host/views.py  host/urls.py  host/templates/host/host.html  host/tests/test_views.py
arr/views.py   arr/urls.py   arr/templates/arr/fleet.html     arr/tests/test_views.py
plex/views.py  plex/urls.py  plex/templates/plex/plex.html    plex/tests/test_views.py
posters/views.py  posters/urls.py  posters/templates/posters/posters.html  posters/tests/test_views.py
letterboxd/views.py  letterboxd/urls.py  letterboxd/templates/letterboxd/letterboxd.html  letterboxd/tests/test_views.py
mdblist/views.py  mdblist/urls.py  mdblist/templates/mdblist/mdblist.html  mdblist/tests/test_views.py
queue_app/views.py  queue_app/urls.py  queue_app/templates/queue_app/queue.html  queue_app/tests/test_views.py
config/urls.py       # + path("", include("ui.urls"))
config/settings.py   # + "ui" in INSTALLED_APPS, + STATICFILES_DIRS (ui/static) if needed
core/decorators.py   # login_required template decorator + session-only-action decorator
core/templates/core/partials/status_dot.svg  sparkline.svg  (or inline in ui/)
```

Page inventory (page → current JS module → Phase 2 services it binds to):

| Page | Old JS module(s) | Binds to (services.py) |
|---|---|---|
| Overview | `overview.js`, `status.js`, `sparkline.js` | `host.services.status`, `plex.services.{updates,scan_health}`, `queue_app.services.aggregate_queue_status`, `core.api_hit_counts` equivalent |
| Arr Fleet | `fleet.js`, `arr-fleet.js`, `loop-remediation.js` | `arr.services.{queue,search_status,manual_import,queue_autofix,loop_candidates,backlog_status}`, `radarr/sonarr.services` |
| Host | `host.js` | `host.services.{containers,host_resources,top,mount_health,disk_health,log_levels,settings}`, `host_actions.services.{reboot,pacman_*}` |
| Plex Health | `plex-health.js`, `status.js` (plex parts) | `plex.services.{scan_health,updates,activities}` |
| Poster Sync | `poster-sync.js` | `posters.services.{libraries,gallery,quality,review,sync}` |
| Letterboxd | `letterboxd.js` | `letterboxd.services.{tracked_lists,sync_now,stats}` |
| MDBList | *(new page — spec lists it; no SPA module today)* | `mdblist.services.{tracked_lists,sync_now,quality_profiles}` |
| Settings | `settings.js` | `core.settings.get_settings/update_settings`, `host.services.log_levels` |
| Reference | `reference.js` | `host.services.docs_readme`, static registry (skills/doc links) |
| Activity Log (strip) | `activity-log.js` | SSE stream (posters SSE helper pattern) + `core.models.AuditLog` |

---

## Task 0 — UI shell: `ui` app, base.html, auth gate, static pipeline

**Interfaces:** `ui/urls.py` mounted at `/`; `ui/views.py` with `home` (Overview), `login_required` decorator in `core/decorators.py`; `ui/templates/ui/base.html`; vendored htmx + `style.css`.

- [ ] **Step 1:** Create `ui` app (`startapp ui`), register `"ui"` in `INSTALLED_APPS`, add `path("", include("ui.urls"))` to `config/urls.py` — this finally gives the orphaned `redirect("/")` in `auth_app.login_view` a real target (it 404s today).
- [ ] **Step 2:** `core/decorators.py` — `login_required(view)` decorator: redirects to `auth_app:login` when `request.session.get("user_id")` is falsy; `session_only_action(view)` decorator: raises 403 if the request carries `X-Api-Key` or has no session user (defense-in-depth for destructive POSTs).
- [ ] **Step 3:** Vendor htmx 2.x: download the single-file `htmx.min.js` release into `ui/static/vendor/htmx.min.js` (no CDN — commit the file). Verify the vendored version's CSRF/`hx-trigger="every 15s"` behavior against its bundled README/docs before wiring it (the version's docs are the reference, not memory).
- [ ] **Step 4:** `ui/templates/ui/base.html` — thin nav bar (Overview | Arr Fleet | Host | Plex | Poster Sync | Letterboxd | MDBList | Settings | Reference), status dot + clock in the header, log strip below the grid, `{% csrf_token %}` meta, htmx boot with the `X-CSRFToken` header. Port `control-panel/static/style.css` (read the actual file; keep the dense-card-grid/monospace/status-dot look per the mockup — rewrite, don't copy wholesale; the SPA's markup classes won't match).
- [ ] **Step 5:** `core/decorators.py` + `ui/views.py` — `home` view renders Overview (below); unauth'd request → redirect to login.
- [ ] **Step 6:** `ui/tests/test_views.py` — auth-redirect (no session → 302 to login), logged-in home renders (status dot present, nav has the 9 links), POST without CSRF token → 403. `ui/tests/test_partials.py` — each partial returns 200 and the expected fragment id.
- [ ] **Step 7:** Gate: `python -m pytest ui/ -v --cov=ui --cov-report=term-missing` — all pass, ≥80%.

## Task 1 — Overview page (dense card grid, status dot, sparklines)

**Interfaces:** `ui/views.py: overview`; partials `_status_cards.html` (4/row grid), `_sparkline.svg`.

- [ ] **Step 1:** Port the Overview card set: queue aggregate (from `queue_app.services.aggregate_queue_status()`), host status (from `host.services.status()`), plex health + update check (from `plex.services`), and the status-dot + clock header (from `status.js` — now server-rendered in `base.html`, refreshed by htmx).
- [ ] **Step 2:** Inline-SVG sparkline partial fed by whatever numeric series the old `sparkline.js` drew for each card (read `control-panel/static/js/sparkline.js` to see the series — e.g. queue sizeleft history — and render the same series server-side from services; no chart lib).
- [ ] **Step 3:** htmx polling: `hx-trigger="every 20s"` on the status cards + queue cards to swap `_status_cards.html`; the overview page body is the target.
- [ ] **Step 4:** `ui/tests/test_views.py` — overview renders all card groups (mock each services call), sparkline SVG present; `ui/tests/test_partials.py` — `_status_cards` fragment swaps.
- [ ] **Step 5:** Gate: `python -m pytest ui/ --cov=ui` — all pass, ≥80%.

## Task 2 — Host page (vitals, actions, resources, mount/disk health)

**Interfaces:** `host/views.py: host_page`, partials `_vitals`, `_resources`, `_mounts`, `_disk`; action POST routes.

- [ ] **Step 1:** `host/views.py` + `host/urls.py` (mounted at `/host/`) — page renders `host.services.{containers,host_resources,top,mount_health,disk_health}` into the card grid; the old `host.js` 5s `refreshHostResources` interval becomes `hx-trigger="every 5s"` on `_resources`.
- [ ] **Step 2:** Actions as htmx POSTs, session-only: container start/stop/restart (per-container card buttons), stack restart-all, settings save (PATCH semantics — session-only, same guard as the API `SettingsView`), disk prune (session-only, confirm dialog via `hx-confirm`), log-levels set/reset. Each POST returns the refreshed fragment to swap.
- [ ] **Step 3:** `host/templates/host/host.html` + partials; wire into `ui/base.html` nav.
- [ ] **Step 4:** `host/tests/test_views.py` — page renders containers/resources/mounts (mock services), each action POST calls the service and swaps, service-key header on a POST → 403, no-session → redirect.
- [ ] **Step 5:** Gate: `python -m pytest host/ --cov=host` — all pass, ≥80% (existing API tests still green).

## Task 3 — Arr Fleet page (fleet cards, queue table, loop remediation)

**Interfaces:** `arr/views.py: fleet_page`, partials `_fleet_cards`, `_queue_table`, `_loop`.

- [ ] **Step 1:** `arr/views.py` + `arr/urls.py` (mounted at `/fleet/` and `/arr/`) — page renders per-app fleet cards (radarr/sonarr, from `arr.services` queue + wanted/missing + backlog_status), the queue table (unstick/manual-import rows), and the loop-remediation panel (from `arr.services.loop_candidates` + `queue_autofix` + `core.import_starvation`).
- [ ] **Step 2:** Actions as htmx POSTs, session-only: unstick, blocklist-and-research, manual-import, search toggle, autofix, clear search backlog. `hx-confirm` on destructive ones. Polling: queue table `every 15s`, fleet cards `every 15s` (matches the old `refreshFleet` 15s interval).
- [ ] **Step 3:** `arr/templates/arr/fleet.html` + partials; nav entry.
- [ ] **Step 4:** `arr/tests/test_views.py` — page renders fleet cards + queue rows (mock services), each action POST calls the service and swaps, session-only enforced, service-key rejected.
- [ ] **Step 5:** Gate: `python -m pytest arr/ --cov=arr` — all pass, ≥80%.

## Task 4 — Plex Health page

**Interfaces:** `plex/views.py: plex_page`, partials `_plex_health`, `_plex_activities`.

- [ ] **Step 1:** `plex/views.py` + `plex/urls.py` (mounted at `/plex/`) — page renders `plex.services.scan_health`, update check (`updates`), and activity/progress (from `plex.services.get_activities` / `get_progress_snapshot` — the same functions `queue_app` uses). Poll `every 15s` like the old `refreshPlexHealth`.
- [ ] **Step 2:** Update-check button → htmx POST → `plex.services` update action; result swaps into the card.
- [ ] **Step 3:** `plex/templates/plex/plex.html` + partials; nav entry.
- [ ] **Step 4:** `plex/tests/test_views.py` — renders health/activities (mock services), POST actions, session-only.
- [ ] **Step 5:** Gate: `python -m pytest plex/ --cov=plex` — all pass, ≥80%.

## Task 5 — Poster Sync page (libraries, gallery, quality scan, review)

**Interfaces:** `posters/views.py: posters_page`, partials `_libraries`, `_gallery` (paginated), `_scan_results`.

- [ ] **Step 1:** `posters/views.py` + `posters/urls.py` (mounted at `/posters/`) — page renders libraries, the gallery grid (paginated via htmx `hx-get` next/prev — the old `poster-gallery-prev/next` buttons), quality scan + review states (from `posters.services` + `posters.candidates`/`posters.quality`). The old `poster-sync.js` Start form + `poster-gallery-scan` button become htmx POSTs; gallery pagination swaps `_gallery`.
- [ ] **Step 2:** Careful with the background jobs: the SSE stream from `posters` drives the log strip + gallery refresh (reuse the Phase 2 `posters/api/sse.py` helper for a template SSE view or an htmx-polled fragment — pick whichever the vendored htmx handles cleanly and note the choice).
- [ ] **Step 3:** `posters/templates/posters/posters.html` + partials; nav entry.
- [ ] **Step 4:** `posters/tests/test_views.py` — renders libraries/gallery/scan (mock services), pagination, POST actions (session-only).
- [ ] **Step 5:** Gate: `python -m pytest posters/ --cov=posters` — all pass, ≥80%.

## Task 6 — Letterboxd page

**Interfaces:** `letterboxd/views.py: letterboxd_page`, partial `_tracked_lists`.

- [ ] **Step 1:** `letterboxd/views.py` + `letterboxd/urls.py` (mounted at `/letterboxd/`) — page renders tracked lists + last-sync stats (from `letterboxd.services`), sync-now button → htmx POST → `letterboxd.services.sync_now` (the old `buildLetterboxdPanel` behavior).
- [ ] **Step 2:** `letterboxd/templates/letterboxd/letterboxd.html` + partials; nav entry.
- [ ] **Step 3:** `letterboxd/tests/test_views.py` — renders lists (mock services), sync-now POST (session-only).
- [ ] **Step 4:** Gate: `python -m pytest letterboxd/ --cov=letterboxd` — all pass, ≥80%.

## Task 7 — MDBList page (new)

**Interfaces:** `mdblist/views.py: mdblist_page`, partial `_tracked_lists`.

- [ ] **Step 1:** `mdblist/views.py` + `mdblist/urls.py` (mounted at `/mdblist/`) — new page (no SPA equivalent): tracked lists, sync-now, quality-profile/root-folder display from `mdblist.services`; sync-now POST swaps the list fragment.
- [ ] **Step 2:** `mdblist/templates/mdblist/mdblist.html` + partials; nav entry.
- [ ] **Step 3:** `mdblist/tests/test_views.py` — renders lists (mock services), sync-now POST (session-only), empty-state renders.
- [ ] **Step 4:** Gate: `python -m pytest mdblist/ --cov=mdblist` — all pass, ≥80%.

## Task 8 — Settings + Reference + Activity Log pages

**Interfaces:** `ui/views.py` additions; `queue_app/views.py` if the queue aggregate page is wanted beyond Overview.

- [ ] **Step 1:** Settings page — `core.settings.get_settings/update_settings` form (theme, thresholds) + host log-levels form, htmx POSTs, session-only for saves.
- [ ] **Step 2:** Reference page — `host.services.docs_readme` + the quick-links/doc-links/skills registry the old `reference.js` built from (read `reference.js` + `core.services`/FastAPI docs endpoints for the source of the list).
- [ ] **Step 3:** Activity Log — log strip in `base.html` fed by the SSE stream + `core.models.AuditLog`; the old `activity-log.js` drawer behavior (open on stream start, clear, source select) reimplemented as htmx-swapped fragments.
- [ ] **Step 4:** Tests for all three pages (render + POST + session-only) in `ui/tests/`.
- [ ] **Step 5:** Gate: `python -m pytest ui/ --cov=ui` — all pass, ≥80%.

## Task 9 — Cross-cutting wiring pass (every action is htmx, no JS left in the new UI)

- [ ] **Step 1:** Sweep every rendered page: every button that mutated state in the SPA maps to an htmx POST whose response is a partial swap; every live-refresh interval maps to `hx-trigger="every Ns"`. No `onclick`/inline JS in templates — the only JS in the new UI is the htmx boot line.
- [ ] **Step 2:** Confirm the log strip, status dot, and clock all update without a page reload.
- [ ] **Step 3:** Grep the new templates for `fetch(`, `<script`, `onclick` — expect zero hits.
- [ ] **Step 4:** Full suite green + per-app coverage gate (below).

## Task 10 — Retire the SPA (documentation only — no deletion until cutover)

- [ ] **Step 1:** Verify every page has a working Django equivalent (walk the page inventory table above; anything in the old SPA with no Django page is a gap — either build it or explicitly mark it deferred).
- [ ] **Step 2:** Add a note in `docs/` (or `ui/README`): the FastAPI SPA under `control-panel/static/` is superseded as of this commit but intentionally **not deleted** — Phase 5 cutover removes it. `palette.js`/`commands.json` retirement is explicitly deferred to Phase 4 (CLI contract) + Phase 5 (cutover).
- [ ] **Step 3:** Mark the spec's "current SPA" description as superseded in the plan tracker of record.

---

## Phase 3 Closeout Gate

- [ ] `source .venv/bin/activate && python -m pytest --cov=ui --cov=host --cov=arr --cov=plex --cov=posters --cov=letterboxd --cov=mdblist --cov=queue_app --cov=core --cov=config` — all pass, **every app ≥80%** (include template views in the measurement; the old API-only numbers must not regress).
- [ ] `python manage.py check` — no issues.
- [ ] Manual smoke (via the running stack, if available, or documented as a Phase 5 pre-cutover checklist item): each page renders, every action swaps without a reload, log strip streams, unauth'd browser gets the login page.
- [ ] No changes to `control-panel/static/` beyond the optional preview banner (verify with `git status` that no old-SPA file is modified).

## Out of Scope / Decisions Recorded

- **Command palette → Phase 4.** The 41KB `commands.json` + `palette.js` (list/args/confirm/run screens, ~1/3 of the SPA) is deferred: its registry is the fish-CLI command catalog, which Phase 4 redefines as part of repointing `fish-functions/`. The design spec's mockup (nav + grid + log strip, no palette) is the authority. If a palette is wanted sooner, that's a scope add — say so before starting Task 8.
- **MDBList page is new** (no SPA equivalent) — spec lists it explicitly, so it's in scope.
- **`ui` app name** is a convention choice; rename freely if a better name exists, but keep one shell app owning `base.html` + static.
- **No deletion, no cutover** — old SPA and FastAPI server keep running until Phase 5; Phase 3 is additive only.
- **Phases 4–5 still unplanned** (fish CLI repointing + gunicorn cutover). This plan's Task 10 only prepares the ground.
