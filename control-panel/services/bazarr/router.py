"""Bazarr routes, ported from app.py (lines ~4984-5049) - Phase 3 of
.claude/plans/evolved-control-panel-backend.plan.md.
"""
import httpx
from fastapi import APIRouter, Depends

from core.api_hit_counts import install as install_hit_counter, register_host_label
from core.arr_client import BAZARR_URL, bazarr_headers
from core.responses import fail, ok
from core.security import current_user_or_service

router = APIRouter(tags=["bazarr"])

SERVICE_META = {"label": "Bazarr", "health_check": None}

register_host_label(BAZARR_URL, "Bazarr")
install_hit_counter()


@router.get("/api/bazarr/wanted")
def bazarr_wanted(_=Depends(current_user_or_service)):
    """Movies/episodes Bazarr still has no subtitle for, across both
    libraries - the same list its own scheduled search works through,
    surfaced without opening its UI."""
    try:
        movies = httpx.get(f"{BAZARR_URL}/api/movies/wanted", headers=bazarr_headers(), timeout=20)
        movies.raise_for_status()
        episodes = httpx.get(f"{BAZARR_URL}/api/episodes/wanted", headers=bazarr_headers(), timeout=20)
        episodes.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Bazarr lookup failed: {e}")
    movie_items = [m.get("title") for m in movies.json().get("data", [])]
    episode_items = [f'{e.get("seriesTitle")} - {e.get("episode_number", "")}' for e in episodes.json().get("data", [])]
    return ok(f"{len(movie_items)} movie(s), {len(episode_items)} episode(s) still missing subtitles.",
              movies=movie_items, episodes=episode_items)


@router.post("/api/bazarr/search-missing")
def bazarr_search_missing(_=Depends(current_user_or_service)):
    # Automation-invoked: same class of unattended remediation action as
    # queue-autofix - triggers Bazarr's own scheduled job on demand.
    try:
        r = httpx.post(f"{BAZARR_URL}/api/system/tasks", headers=bazarr_headers(),
                        data={"taskid": "wanted_search_missing_subtitles_movies"}, timeout=20)
        r.raise_for_status()
        r2 = httpx.post(f"{BAZARR_URL}/api/system/tasks", headers=bazarr_headers(),
                         data={"taskid": "wanted_search_missing_subtitles_series"}, timeout=20)
        r2.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Couldn't trigger Bazarr's search: {e}")
    return ok("Missing-subtitle search triggered for both movies and series.")


@router.get("/api/bazarr/history")
def bazarr_history(limit: int = 20, _=Depends(current_user_or_service)):
    """Recent subtitle download history (both movies and episodes),
    newest first - successes and failures both, so a provider that's
    silently failing every download shows up without checking each item."""
    try:
        movies = httpx.get(f"{BAZARR_URL}/api/movies/history", headers=bazarr_headers(), params={"length": limit}, timeout=20)
        movies.raise_for_status()
        episodes = httpx.get(f"{BAZARR_URL}/api/episodes/history", headers=bazarr_headers(), params={"length": limit}, timeout=20)
        episodes.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Bazarr lookup failed: {e}")
    items = []
    for rec in movies.json().get("data", [])[:limit]:
        items.append({"title": rec.get("title"), "action": rec.get("description"), "provider": rec.get("provider")})
    for rec in episodes.json().get("data", [])[:limit]:
        items.append({"title": rec.get("seriesTitle"), "action": rec.get("description"), "provider": rec.get("provider")})
    return ok(f"{len(items)} recent history entr{'y' if len(items) == 1 else 'ies'}.", items=items)


@router.get("/api/bazarr/provider-status")
def bazarr_provider_status(_=Depends(current_user_or_service)):
    """Per-provider throttle/error state for every enabled subtitle
    source - catches a provider that's silently rate-limited or erroring
    on every request, invisible from a plain enabled/disabled list."""
    try:
        r = httpx.get(f"{BAZARR_URL}/api/providers", headers=bazarr_headers(), timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Bazarr lookup failed: {e}")
    items = [{"name": p.get("name"), "status": p.get("status"), "retry": p.get("retry")} for p in r.json().get("data", [])]
    problems = [i["name"] for i in items if i["status"] != "Good"]
    msg = "All providers healthy." if not problems else f"Problem with: {', '.join(problems)}"
    return ok(msg, items=items)
