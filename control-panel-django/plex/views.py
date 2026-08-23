"""Plex Health page — scan health, activities, session info."""

from django.shortcuts import render

from core.decorators import login_required
from plex import services


@login_required
def plex_page(request):
    """Plex health overview: scan state, activities, sessions."""
    try:
        health = services.scan_health()
    except Exception:
        health = {}
    try:
        sessions = services.sessions()
    except Exception:
        sessions = {}
    try:
        updates = services.get_updates()
    except Exception:
        updates = {}

    return render(request, "plex/plex.html", {
        "page": "plex",
        "health": health,
        "sessions": sessions.get("sessions", []),
        "update_available": updates.get("update_available", False),
        "running_version": updates.get("running_version"),
    })


@login_required
def plex_health_partial(request):
    """htmx poll target: health fragment."""
    try:
        health = services.scan_health()
    except Exception:
        health = {}
    return render(request, "plex/partials/_health.html", {"health": health})