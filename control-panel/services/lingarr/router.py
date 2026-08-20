"""Lingarr routes, ported from app.py (lines 5677-5739) - Phase 4 of
.claude/plans/evolved-control-panel-backend.plan.md.

All routes read-only - current_user_or_service throughout, same reasoning
as services/prefetcharr.
"""
import re

import docker
import httpx
from core.docker_client import docker_client
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends

router = APIRouter(tags=["lingarr"])

SERVICE_META = {"label": "Lingarr", "health_check": None}

LINGARR_URL = "http://lingarr:8080"


@router.get("/api/lingarr/stats")
def lingarr_stats(_=Depends(current_user_or_service)):
    """Lifetime translation totals - Lingarr's own dashboard summary."""
    try:
        r = httpx.get(f"{LINGARR_URL}/api/statistics", timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Lingarr lookup failed: {e}")
    data = r.json()
    return ok(f"{data.get('totalSubtitles', 0)} subtitle(s) translated across "
              f"{data.get('totalMovies', 0)} movie(s)/{data.get('totalEpisodes', 0)} episode(s) tracked.", **data)


@router.get("/api/lingarr/movies")
def lingarr_movies(limit: int = 20, _=Depends(current_user_or_service)):
    """Movies Lingarr knows about (from its own Radarr connection) and
    their translation state."""
    try:
        r = httpx.get(f"{LINGARR_URL}/api/media/movies", timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Lingarr lookup failed: {e}")
    items = r.json().get("items", [])[:limit]
    return ok(f"{len(items)} movie(s) (showing up to {limit}).", items=[{"title": i.get("title"), "id": i.get("id")} for i in items])


@router.get("/api/lingarr/shows")
def lingarr_shows(limit: int = 20, _=Depends(current_user_or_service)):
    """Shows Lingarr knows about (from its own Sonarr connection)."""
    try:
        r = httpx.get(f"{LINGARR_URL}/api/media/shows", timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Lingarr lookup failed: {e}")
    items = r.json().get("items", [])[:limit]
    return ok(f"{len(items)} show(s) (showing up to {limit}).", items=[{"title": i.get("title")} for i in items])


@router.get("/api/lingarr/logs")
def lingarr_logs(lines: int = 60, _=Depends(current_user_or_service)):
    """Tails Lingarr's own container logs."""
    try:
        c = docker_client.containers.get("lingarr")
    except docker.errors.NotFound:
        fail("Container 'lingarr' not found.")
    raw = c.logs(tail=min(lines, 1000), timestamps=True).decode(errors="replace")
    return ok(f"Last {lines} line(s) from lingarr.", log=raw)


@router.get("/api/lingarr/recent-translations")
def lingarr_recent_translations(_=Depends(current_user_or_service)):
    """Distinct from lingarr_stats() (lifetime totals): pulls the most
    recent individual translation-completed events straight out of the
    container logs, since Lingarr's REST API doesn't expose a job-history
    list."""
    try:
        c = docker_client.containers.get("lingarr")
    except docker.errors.NotFound:
        fail("Container 'lingarr' not found.")
    raw_lines = c.logs(tail=1000).decode(errors="replace").splitlines()
    events = [line for line in raw_lines if re.search(r"(?i)translat(ed|ion complete)", line)]
    return ok(f"{len(events)} recent translation event(s) found in logs.", lines=events[-20:])
