"""Tautulli routes, ported from app.py (lines 5188-5359) - Phase 4 of
.claude/plans/evolved-control-panel-backend.plan.md.

All routes are read-only except terminate-stream (kills a single active
session on request) - current_user_or_service throughout, same reasoning
as services/nzbdav's diagnostic/automation-invoked routes.
"""
import os

import httpx
from core.api_hit_counts import install as install_hit_counter
from core.api_hit_counts import register_host_label
from core.host_paths import HOST_CONFIG_DIR
from core.plex_client import PLEX_URL, plex_headers
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends

router = APIRouter(tags=["tautulli"])

SERVICE_META = {"label": "Tautulli", "health_check": None}

TAUTULLI_URL = "http://tautulli:8181"

register_host_label(TAUTULLI_URL, "Tautulli")
install_hit_counter()


def _tautulli_key() -> str | None:
    """Tautulli generates its own API key on first boot into
    config/config.ini's [General] api_key - never an env var, same story
    as Bazarr/Seerr."""
    path = os.path.join(HOST_CONFIG_DIR, "tautulli", "config.ini")
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        for line in f:
            if line.strip().startswith("api_key"):
                return line.split("=", 1)[1].strip()
    return None


def _tautulli_call(cmd: str, **params):
    key = _tautulli_key()
    if not key:
        fail("No Tautulli API key found (config.ini not present yet - has it completed setup?).", status_code=500)
    try:
        r = httpx.get(f"{TAUTULLI_URL}/api/v2", params={"apikey": key, "cmd": cmd, **params}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Tautulli lookup failed: {e}")
    body = r.json().get("response", {})
    if body.get("result") != "success":
        fail(f"Tautulli returned an error: {body.get('message') or 'unknown'}")
    return body.get("data")


@router.get("/api/tautulli/activity")
def tautulli_activity(_=Depends(current_user_or_service)):
    """Live Plex streams as Tautulli sees them - same data Plex's own
    /status/sessions gives, but with Tautulli's per-session transcode
    detail already broken out."""
    data = _tautulli_call("get_activity") or {}
    sessions = data.get("sessions", [])
    items = [{"session_key": s.get("session_key"), "user": s.get("user"), "title": s.get("full_title"),
              "state": s.get("state"), "decision": s.get("transcode_decision"), "progress": s.get("progress_percent")}
             for s in sessions]
    return ok(f"{data.get('stream_count', 0)} active stream(s).", items=items)


@router.post("/api/tautulli/terminate-stream")
def tautulli_terminate_stream(session_key: str, _=Depends(current_user_or_service)):
    """Kills a single active stream by its session_key (from
    tautulli_activity() above) - for a runaway transcode or a session that
    needs cutting off, without touching Plex directly.
    Automation-invoked mutating route: same documented exception as
    services/arr's unstick actions."""
    _tautulli_call("terminate_session", session_key=session_key, message="Stopped from Control Panel.")
    return ok(f"Terminate requested for session {session_key}.")


@router.get("/api/tautulli/history")
def tautulli_history(limit: int = 20, _=Depends(current_user_or_service)):
    """Recent watch history across every user/library, newest first."""
    data = _tautulli_call("get_history", length=limit) or {}
    items = [{"title": r.get("full_title"), "user": r.get("user"), "date": r.get("date"),
              "percent_complete": r.get("percent_complete")} for r in data.get("data", [])]
    return ok(f"{len(items)} recent history entr{'y' if len(items) == 1 else 'ies'}.", items=items)


@router.get("/api/tautulli/stats")
def tautulli_stats(_=Depends(current_user_or_service)):
    """Home-page stat cards (most watched movies/shows, top users) -
    Tautulli's own dashboard summary, without opening its UI."""
    data = _tautulli_call("get_home_stats") or []
    sections = {row.get("stat_id"): [r.get("title") or r.get("friendly_name") for r in row.get("rows", [])[:5]]
                for row in data}
    return ok(f"{len(sections)} stat categor{'y' if len(sections) == 1 else 'ies'}.", stats=sections)


@router.get("/api/tautulli/users")
def tautulli_users(_=Depends(current_user_or_service)):
    """Every known Plex user Tautulli has seen, with lifetime plays/duration."""
    data = _tautulli_call("get_users_table", length=100) or {}
    items = [{"user": r.get("friendly_name"), "plays": r.get("plays"), "duration": r.get("duration"),
              "last_seen": r.get("last_seen")} for r in data.get("data", [])]
    return ok(f"{len(items)} user(s).", items=items)


@router.get("/api/tautulli/user-history")
def tautulli_user_history(user_id: int, limit: int = 20, _=Depends(current_user_or_service)):
    """Same as tautulli_history() but filtered to one user_id (from
    tautulli_users() above)."""
    data = _tautulli_call("get_history", user_id=user_id, length=limit) or {}
    items = [{"title": r.get("full_title"), "date": r.get("date"), "percent_complete": r.get("percent_complete")}
             for r in data.get("data", [])]
    return ok(f"{len(items)} entr{'y' if len(items) == 1 else 'ies'} for user {user_id}.", items=items)


@router.get("/api/tautulli/libraries")
def tautulli_libraries(_=Depends(current_user_or_service)):
    """Per-library item counts as Tautulli last saw them (its own cached
    view, refreshed on its schedule - not a live Plex call)."""
    data = _tautulli_call("get_libraries") or []
    items = [{"name": r.get("section_name"), "count": r.get("count"), "type": r.get("section_type")} for r in data]
    return ok(f"{len(items)} librar{'y' if len(items) == 1 else 'ies'}.", items=items)


@router.get("/api/tautulli/recently-added")
def tautulli_recently_added_via_tautulli(limit: int = 15, _=Depends(current_user_or_service)):
    """Tautulli's own recently-added feed - separate from Plex's own
    recently-added route, which queries Plex directly."""
    data = _tautulli_call("get_recently_added", count=limit) or {}
    items = [{"title": r.get("full_title"), "added_at": r.get("added_at")} for r in data.get("recently_added", [])]
    return ok(f"{len(items)} recently-added item(s).", items=items)


@router.get("/api/tautulli/server-info")
def tautulli_server_info(_=Depends(current_user_or_service)):
    """The Plex server Tautulli is actually configured against - hostname/
    version/machine_identifier, for tautulli_sync_check() below to compare
    against this stack's real Plex."""
    data = _tautulli_call("get_server_info") or {}
    return ok(f"Tautulli is tracking Plex server '{data.get('pms_name')}' at {data.get('pms_ip')}:{data.get('pms_port')}.",
              **data)


@router.get("/api/tautulli/newsletters")
def tautulli_newsletters(_=Depends(current_user_or_service)):
    """Configured newsletter definitions (if any) - Tautulli ships this
    feature but this stack has never set one up; surfaces that plainly
    instead of it being silent."""
    data = _tautulli_call("get_newsletters") or []
    items = [{"id": n.get("id"), "agent": n.get("agent_name"), "active": n.get("active")} for n in data]
    return ok(f"{len(items)} newsletter(s) configured." if items else "No newsletters configured.", items=items)


@router.get("/api/tautulli/notifiers")
def tautulli_notifiers(_=Depends(current_user_or_service)):
    """Configured notification agents (Discord, etc.) inside Tautulli
    itself - separate from this stack's own DISCORD_WEBHOOK_URL."""
    data = _tautulli_call("get_notifiers") or []
    items = [{"id": n.get("id"), "agent": n.get("agent_name"), "active": bool(n.get("active"))} for n in data]
    return ok(f"{len(items)} notifier(s) configured." if items else "No notifiers configured.", items=items)


@router.get("/api/tautulli/plays-by-date")
def tautulli_plays_by_date(days: int = 30, _=Depends(current_user_or_service)):
    """Daily play-count trend for the last N days - the same series
    behind Tautulli's own dashboard graph."""
    data = _tautulli_call("get_plays_by_date", time_range=days) or {}
    categories = data.get("categories", [])
    series = data.get("series", [])
    total_per_day = [sum(s["data"][i] for s in series) for i in range(len(categories))] if series else []
    return ok(f"Play counts for the last {days} day(s).", days=categories, totals=total_per_day)


@router.get("/api/tautulli/sync-check")
def tautulli_sync_check(_=Depends(current_user_or_service)):
    """Misconfiguration guard: Tautulli is wired to Plex via its own UI
    post-boot (same pattern as Seerr/Maintainerr/Wrapperr), so a typo'd
    hostname/port silently leaves it tracking nothing. Compares its
    configured Plex machine_identifier against this stack's real one."""
    tautulli_info = _tautulli_call("get_server_info") or {}
    try:
        real = httpx.get(f"{PLEX_URL}/", headers=plex_headers(), timeout=10)
        real.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Could not reach this stack's real Plex to compare: {e}")
    real_id = real.json().get("MediaContainer", {}).get("machineIdentifier")
    tautulli_id = tautulli_info.get("pms_identifier")
    if not tautulli_id:
        return ok("Tautulli has no Plex server configured yet.", matches=False)
    matches = tautulli_id == real_id
    msg = "Tautulli is tracking this stack's real Plex server." if matches else \
          f"MISMATCH: Tautulli is tracking a different Plex server ({tautulli_info.get('pms_name')})."
    return ok(msg, matches=matches, tautulli_pms=tautulli_info.get("pms_name"), real_machine_id=real_id)
