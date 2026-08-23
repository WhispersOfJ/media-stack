"""MDBList page — tracked lists, sync history. New page (no SPA equiv)."""

from django.shortcuts import render

from core.decorators import login_required
from mdblist import services


@login_required
def mdblist_page(request):
    """MDBList tracked lists + recent sync history."""
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
    return render(request, "mdblist/mdblist.html", {
        "page": "mdblist",
        "lists": lists,
        "runs": runs,
    })