"""Poster Sync page — libraries, gallery, quality scan, review."""

from django.shortcuts import render

from core.decorators import login_required
from posters import services


@login_required
def posters_page(request):
    """Poster sync overview: libraries, recent state."""
    try:
        libraries = services.list_libraries()
        libs = libraries.get("items", [])
    except Exception:
        libs = []
    return render(request, "posters/posters.html", {
        "page": "posters",
        "page_title": "Posters",
        "libraries": libs,
    })


@login_required
def posters_gallery_partial(request, library):
    """htmx swap: gallery grid for one library."""
    offset = int(request.GET.get("offset", 0))
    try:
        gallery = services.gallery(library, offset=offset)
    except Exception:
        gallery = {}
    return render(request, "posters/partials/_gallery.html", {
        "gallery": gallery,
        "library": library,
        "offset": offset,
    })