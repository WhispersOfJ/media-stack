"""UI shell views — the browser-facing Django template + htmx pages.

Every view here calls services.py functions directly server-side
(never re-fetching /api/v2/* from the browser).  The spec made
services.py framework-agnostic precisely for this.

Phase 3 pages (built in later tasks):
  - Overview (home) — Task 1
  - Settings — Task 8
  - Reference — Task 8
  - Activity Log — Task 8

Cross-app page views live in their respective apps' views.py files:
  - Host page → host/views.py (Task 2)
  - Arr Fleet page → arr/views.py (Task 3)
  - Plex Health page → plex/views.py (Task 4)
  - Poster Sync page → posters/views.py (Task 5)
  - Letterboxd page → letterboxd/views.py (Task 6)
  - MDBList page → mdblist/views.py (Task 7)
"""

import logging

from django.shortcuts import render
from django.utils import timezone

from core.decorators import login_required

logger = logging.getLogger(__name__)


def _overview_context():
    """Gather all cross-app data for the overview cards + partial.

    Calls every relevant services.py function directly.  Each call is
    wrapped in a try/except so one unreachable service (e.g. Plex
    restarting) doesn't blank the whole page — the card shows "…"
    instead.
    """
    ctx: dict = {}

    # ── Queue aggregate ────────────────────────────────────────────
    try:
        from queue_app.services import aggregate_queue_status
        qstatus = aggregate_queue_status()
        downloading = 0
        queued = 0
        importing = 0
        for app_name, data in qstatus.items():
            if isinstance(data, dict) and "error" not in data:
                downloading += len(data.get("downloading", []))
                queued += len(data.get("queued", []))
                importing += len(data.get("importing", []))
        ctx["q_downloading"] = downloading
        ctx["q_queued"] = queued
        ctx["q_importing"] = importing
    except Exception:
        logger.warning("overview: queue aggregate failed", exc_info=True)

    # ── Host resources ─────────────────────────────────────────────
    try:
        from host.services import host_resources
        hr = host_resources()
        ctx["cpu_percent"] = hr.get("cpu_percent")
        ctx["mem_percent"] = hr.get("mem_percent")
        ctx["mem_used"] = hr.get("mem_used")
        ctx["mem_total"] = hr.get("mem_total")
    except Exception:
        logger.warning("overview: host resources failed", exc_info=True)

    # ── Plex health ────────────────────────────────────────────────
    try:
        from plex.services import scan_health
        sh = scan_health()
        state = sh.get("state", "unknown")
        ctx["plex_state"] = state
        ctx["plex_state_label"] = state.replace("_", " ").title()
        ctx["plex_activity_count"] = len(sh.get("activities", []))
        ctx["plex_state_pct"] = 50  # default; real would come from progress
    except Exception:
        logger.warning("overview: plex health failed", exc_info=True)

    # ── Arr Fleet backlog ──────────────────────────────────────────
    try:
        import arr.services as arr_services
        bs = arr_services.backlog_status()
        apps = bs.get("apps", {})
        ctx["arr_app_count"] = len(apps)
        ctx["arr_missing"] = sum(
            v.get("missing", 0) for v in apps.values()
            if isinstance(v, dict) and "error" not in v
        )
    except Exception:
        logger.warning("overview: arr backlog failed", exc_info=True)

    return ctx


@login_required
def overview_cards_partial(request):
    """Returns the overview card grid fragment for htmx polling."""
    return render(request, "ui/partials/overview_cards.html", _overview_context())


@login_required
def home(request):
    """Overview page — the root / route, finally giving auth_app.login_view's
    redirect('/') a real target (it 404s today without this)."""
    ctx = _overview_context()
    ctx["page"] = "overview"
    ctx["page_title"] = "Overview"
    return render(request, "ui/overview.html", ctx)


@login_required
def settings_page(request):
    """Placeholder — Task 8 builds the real settings page."""
    return render(request, "ui/settings.html", {"page": "settings", "page_title": "Settings"})


@login_required
def reference_page(request):
    """Placeholder — Task 8 builds the real reference page."""
    return render(request, "ui/reference.html", {"page": "reference", "page_title": "Reference"})


@login_required
def activity_log_page(request):
    """Placeholder — Task 8 builds the real activity log page."""
    return render(request, "ui/activity_log.html", {"page": "activity_log", "page_title": "Activity Log"})


# ─── htmx partial swap targets ───────────────────────────────────────


@login_required
def status_dot_partial(request):
    """Returns just the status-dot + clock fragment for htmx swap."""
    return render(request, "ui/partials/status_dot.html", {
        "now": timezone.now(),
    })


@login_required
def log_strip_partial(request):
    """Returns the log-strip fragment for htmx polling."""
    return render(request, "ui/partials/log_strip.html", {
        "recent_activity": [],
    })


