"""Letterboxd page — tracked lists, sync history."""

from django.shortcuts import render

from core.decorators import login_required
from letterboxd import services


@login_required
def letterboxd_page(request):
    """Letterboxd tracked lists + recent sync history."""
    try:
        tracked = services.list_tracked()
        lists = tracked.get("lists", [])
    except Exception:
        lists = []
    try:
        history = services.get_history()
        runs = history.get("runs", [])
    except Exception:
        runs = []
    return render(request, "letterboxd/letterboxd.html", {
        "page": "letterboxd",
        "lists": lists,
        "runs": runs,
    })