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

    Runs all four service calls in parallel via threads to minimize
    latency. Each call is wrapped in a try/except so one unreachable
    service doesn't blank the whole page.
    """
    ctx: dict = {}

    def _fetch_queue():
        try:
            from queue_app.services import aggregate_queue_status
            qstatus = aggregate_queue_status()
            downloading = queued = importing = 0
            for data in qstatus.values():
                if isinstance(data, dict) and "error" not in data:
                    downloading += len(data.get("downloading", []))
                    queued += len(data.get("queued", []))
                    importing += len(data.get("importing", []))
            return {"q_downloading": downloading, "q_queued": queued, "q_importing": importing}
        except Exception:
            logger.warning("overview: queue aggregate failed", exc_info=True)
            return {}

    def _fetch_host():
        try:
            from host.services import host_resources
            hr = host_resources()
            return {
                "cpu_percent": hr.get("cpu_percent"),
                "mem_percent": hr.get("mem_percent"),
                "mem_used": hr.get("mem_used"),
                "mem_total": hr.get("mem_total"),
            }
        except Exception:
            logger.warning("overview: host resources failed", exc_info=True)
            return {}

    def _fetch_plex():
        try:
            from plex.services import scan_health
            sh = scan_health()
            state = sh.get("state", "unknown")
            return {
                "plex_state": state,
                "plex_state_label": state.replace("_", " ").title(),
                "plex_activity_count": len(sh.get("activities", [])),
                "plex_state_pct": 50,
            }
        except Exception:
            logger.warning("overview: plex health failed", exc_info=True)
            return {}

    def _fetch_arr():
        try:
            import arr.services as arr_services
            bs = arr_services.backlog_status()
            apps = bs.get("apps", {})
            return {
                "arr_app_count": len(apps),
                "arr_missing": sum(
                    v.get("missing", 0) for v in apps.values()
                    if isinstance(v, dict) and "error" not in v
                ),
            }
        except Exception:
            logger.warning("overview: arr backlog failed", exc_info=True)
            return {}

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_fetch_queue): "queue",
            pool.submit(_fetch_host): "host",
            pool.submit(_fetch_plex): "plex",
            pool.submit(_fetch_arr): "arr",
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                ctx.update(future.result())
            except Exception:
                logger.warning("overview: %s failed", futures[future], exc_info=True)

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
    """Settings page — connection config, auth, display, notifications."""
    ctx = {"page": "settings", "page_title": "Settings"}
    # Pull current env values for the form
    import os
    ctx["settings"] = {
        "plex_url": os.environ.get("PLEX_URL", ""),
        "plex_token": os.environ.get("PLEX_TOKEN", ""),
        "radarr_api_key": os.environ.get("RADARR_API_KEY", ""),
        "sonarr_api_key": os.environ.get("SONARR_API_KEY", ""),
    }
    ctx["theme"] = request.session.get("theme", "dark")
    return render(request, "ui/settings.html", ctx)


@login_required
def reference_page(request):
    """Reference page — links to all services and documentation."""
    import os
    host_ip = os.environ.get("HOST_IP", "localhost")
    ctx = {
        "page": "reference",
        "page_title": "Reference",
        "plex_host": host_ip,
        "radarr_host": host_ip,
        "sonarr_host": host_ip,
        "prowlarr_host": host_ip,
        "nzbdav_host": host_ip,
        "seerr_host": host_ip,
        "watchstate_host": host_ip,
        "grafana_host": host_ip,
    }
    return render(request, "ui/reference.html", ctx)


@login_required
def activity_log_page(request):
    """Activity Log — searchable audit trail."""
    from core.models import AuditLog
    activities = AuditLog.objects.order_by("-created_at")[:100]
    return render(request, "ui/activity.html", {
        "page": "activity",
        "page_title": "Activity Log",
        "activities": activities,
    })


@login_required
def logs_page(request):
    """Log Viewer — centralized container log streaming."""
    from host.services import list_containers
    containers = []
    try:
        containers = [c["name"] for c in list_containers()]
    except Exception:
        pass
    selected = request.GET.get("container", "")
    return render(request, "ui/logs.html", {
        "page": "logs",
        "page_title": "Log Viewer",
        "containers": containers,
        "selected_container": selected,
    })


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


@login_required
def activity_timeline_partial(request):
    """Returns the activity timeline fragment for htmx polling."""
    from core.models import AuditLog
    activities = AuditLog.objects.order_by("-created_at")[:20]
    return render(request, "ui/partials/activity_timeline.html", {
        "activities": activities,
    })


@login_required
def log_stream_partial(request):
    """Returns log lines from a container for htmx polling."""
    container = request.GET.get("container", "")
    log_lines = []
    if container:
        try:
            import docker
            client = docker.from_env()
            c = client.containers.get(container)
            raw = c.logs(tail=200, timestamps=True).decode(errors="replace")
            log_lines = [line.rstrip() for line in raw.splitlines() if line.strip()]
        except Exception:
            log_lines = [f"Error: could not read logs for {container}"]
    return render(request, "ui/partials/log_stream.html", {
        "log_lines": log_lines,
        "container": container,
    })


@login_required
def log_stream_sse(request):
    """SSE endpoint that streams live container logs."""
    from django.http import StreamingHttpResponse
    container = request.GET.get("container", "")
    if not container:
        return StreamingHttpResponse(
            iter(["data: {\"error\": \"No container specified\"}\n\n"]),
            content_type="text/event-stream",
        )

    def generate():
        try:
            import docker
            client = docker.from_env()
            c = client.containers.get(container)
            for line in c.logs(stream=True, follow=True, tail=50, timestamps=True):
                text = line.decode(errors="replace").rstrip()
                if text:
                    import json
                    yield f"data: {json.dumps({'line': text})}\n\n"
        except Exception as e:
            import json
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    response = StreamingHttpResponse(generate(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


