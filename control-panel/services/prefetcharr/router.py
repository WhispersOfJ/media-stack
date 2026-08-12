"""Prefetcharr routes, ported from app.py (lines 5608-5673) - Phase 4 of
.claude/plans/evolved-control-panel-backend.plan.md.

All routes read-only - current_user_or_service throughout, same reasoning
as services/tautulli. Prefetcharr has no API/port of its own (log-file
and env-var driven only), unlike most other Phase 4 integrations.
"""
import os
import re

import docker
from core.docker_client import docker_client
from core.host_paths import HOST_CONFIG_DIR
from core.plex_client import PLEX_URL
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends

router = APIRouter(tags=["prefetcharr"])

SERVICE_META = {"label": "Prefetcharr", "health_check": None}


def _prefetcharr_log_lines() -> tuple[str | None, list[str]]:
    path = os.path.join(HOST_CONFIG_DIR, "prefetcharr")
    log_files = sorted((f for f in os.listdir(path) if f.endswith(".log")), reverse=True) if os.path.isdir(path) else []
    if not log_files:
        return None, []
    with open(os.path.join(path, log_files[0])) as f:
        return log_files[0], f.readlines()


@router.get("/api/prefetcharr/logs")
def prefetcharr_logs(lines: int = 60, _=Depends(current_user_or_service)):
    """Tails Prefetcharr's own log file directly (mounted at
    config/prefetcharr, unlike Kometa which is stdout-only)."""
    name, all_lines = _prefetcharr_log_lines()
    if not name:
        return ok("No log file found yet.", lines=[])
    return ok(f"Last {min(lines, len(all_lines))} line(s) from {name}.", lines=[line.rstrip() for line in all_lines[-lines:]])


@router.get("/api/prefetcharr/status")
def prefetcharr_status(_=Depends(current_user_or_service)):
    """Container up/down plus the most recent prefetch-trigger event
    found in its log - prefetcharr has no API/port of its own to poll."""
    try:
        c = docker_client.containers.get("prefetcharr")
    except docker.errors.NotFound:
        fail("Container 'prefetcharr' not found.")
    running = c.status == "running"
    _, all_lines = _prefetcharr_log_lines()
    last_prefetch = None
    for line in all_lines:
        if re.search(r"(?i)(prefetch|request.{0,10}season)", line):
            last_prefetch = line.strip()
    return ok(f"Container is {c.status}." + (f" Last prefetch event: {last_prefetch}" if last_prefetch else " No prefetch event logged yet."),
              running=running, last_event=last_prefetch)


@router.get("/api/prefetcharr/config")
def prefetcharr_config(_=Depends(current_user_or_service)):
    """Effective PREFETCHARR_CONFIG as deployed (interval/prefetch_num/
    request_seasons), read straight from the running container's own env -
    it's a single TOML blob (see docker-compose.yml), not a mounted file."""
    try:
        c = docker_client.containers.get("prefetcharr")
    except docker.errors.NotFound:
        fail("Container 'prefetcharr' not found.")
    env = {e.split("=", 1)[0]: e.split("=", 1)[1] for e in c.attrs["Config"]["Env"] if "=" in e}
    blob = env.get("PREFETCHARR_CONFIG", "")
    return ok("Effective prefetcharr config.", config=blob)


@router.get("/api/prefetcharr/plex-link-check")
def prefetcharr_plex_link_check(_=Depends(current_user_or_service)):
    """Misconfiguration guard: prefetcharr's [media_server] block hardcodes
    PLEX_URL/PLEX_TOKEN at deploy time (docker-compose.yml env
    substitution) - if this stack's PLEX_URL/PLEX_TOKEN ever rotates
    without recreating this container, prefetcharr keeps using the stale
    value silently (it only reads env at container start)."""
    try:
        c = docker_client.containers.get("prefetcharr")
    except docker.errors.NotFound:
        fail("Container 'prefetcharr' not found.")
    env = {e.split("=", 1)[0]: e.split("=", 1)[1] for e in c.attrs["Config"]["Env"] if "=" in e}
    blob = env.get("PREFETCHARR_CONFIG", "")
    m = re.search(r'url\s*=\s*"([^"]*)"', blob)
    baked_url = m.group(1) if m else None
    matches = baked_url == PLEX_URL
    msg = "Prefetcharr's baked-in Plex URL matches this stack's current PLEX_URL." if matches else \
          f"MISMATCH: prefetcharr was started with Plex URL '{baked_url}', current PLEX_URL is '{PLEX_URL}' - recreate the container."
    return ok(msg, matches=matches, baked_url=baked_url, real_url=PLEX_URL)
