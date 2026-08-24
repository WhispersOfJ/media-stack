"""Arr Fleet page — per-app fleet cards, queue table, loop remediation.

Template views call arr.services directly server-side.
"""

from django.shortcuts import render

from arr import services
from core.decorators import login_required, session_only_action


@login_required
def fleet_page(request):
    """Arr Fleet overview: per-app cards with queue + backlog status."""
    try:
        backlog = services.backlog_status()
        apps = backlog.get("apps", {})
    except Exception:
        apps = {}
    try:
        qstatus = services.queue_errors()
    except Exception:
        qstatus = {}

    return render(request, "arr/fleet.html", {
        "page": "fleet",
        "page_title": "Fleet",
        "apps": apps,
        "queue_errors": qstatus.get("apps", {}),
    })


@login_required
def fleet_cards_partial(request):
    """htmx poll target: fleet cards refresh."""
    try:
        backlog = services.backlog_status()
        apps = backlog.get("apps", {})
    except Exception:
        apps = {}
    return render(request, "arr/partials/_fleet_cards.html", {"apps": apps})


@login_required
def queue_table_partial(request):
    """htmx poll target: queue error rows."""
    try:
        qstatus = services.queue_errors()
        apps = qstatus.get("apps", {})
    except Exception:
        apps = {}
    return render(request, "arr/partials/_queue_table.html", {"queue_errors": apps})


@login_required
@session_only_action
def queue_autofix_action(request):
    services.queue_autofix()
    return queue_table_partial(request)


@login_required
@session_only_action
def unstick_action(request, app_name):
    services.unstick(app_name)
    return queue_table_partial(request)