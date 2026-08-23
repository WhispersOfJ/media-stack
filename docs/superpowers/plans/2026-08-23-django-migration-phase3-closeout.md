# Phase 3 — Django Template + htmx Browser UI — Closeout

**Date:** 2026-08-23  
**Status:** Complete

## What was built

- **`ui` app:** `base.html` shell (thin nav bar, status dot + clock, log strip, htmx 2.x boot, CSRF meta), CRT Pip-Boy ported CSS, vendored htmx 2.0.4
- **`core/decorators.py`:** `login_required` (session check → redirect) and `session_only_action` (rejects X-Api-Key → 403)
- **7 app pages:** Host (`/host/`), Arr Fleet (`/fleet/`), Plex Health (`/plex/`), Poster Sync (`/posters/`), Letterboxd (`/letterboxd/`), MDBList (`/mdblist/`), Overview (`/`)
- **4 shell pages:** Settings, Reference, Activity Log (placeholder — real content deferred to Task 8)
- **htmx partials:** Overview cards (20s poll), container grid (10s poll), fleet cards + queue table (15s poll), plex health (15s poll), gallery pagination
- **All template views call `services.py` directly server-side** — never re-fetch `/api/v2/*` from the browser

## What was not built (deferred)

- **Command palette** → Phase 4 (CLI contract redesign)
- **Full Settings/Reference/Activity Log pages** → Task 8 (basic shells exist)
- **Real log strip content** → needs SSE/activity stream wiring (placeholder renders "no recent activity")
- **Theme switching** (amber/green toggle) — static "amber" in base.html; needs settings context processor

## What was not touched

- **`control-panel/static/`** — the FastAPI SPA remains untouched and live until Phase 5 cutover
- **`control-panel-django/api/` routes** — all Phase 2 APIs unchanged
- **`fish-functions/`** — no CLI changes in this phase (Phase 4)

## Coverage

- **575 tests passing**, 96% total coverage
- Every app's `services.py` stays at ≥80%
- Template views: `ui/views.py` 84%, `host/views.py` 60%, `arr/views.py` 71%, others 68-79% (uncovered: error-branch except clauses)
- Existing API tests: zero regressions

## Test run

```
cd control-panel-django
python -m pytest --cov=ui --cov=host --cov=arr --cov=plex \
    --cov=posters --cov=letterboxd --cov=mdblist --cov=core \
    --cov=config -q
# 575 passed, 96%
```