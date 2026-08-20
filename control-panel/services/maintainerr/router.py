"""Maintainerr routes, ported from app.py (lines 5425-5524) - Phase 4 of
.claude/plans/evolved-control-panel-backend.plan.md.

All routes are read-only - current_user_or_service throughout, same
reasoning as services/seerr. safety-check exists specifically because
this stack's Maintainerr is installed with ZERO rules on purpose (see
CLAUDE.md/STACK.md's 3+ documented mass-deletion incidents) - a non-empty
active-rule list is worth surfacing loudly, not silently trusting.
"""
from urllib.parse import urlparse

import docker
import httpx
from core.api_hit_counts import install as install_hit_counter
from core.api_hit_counts import register_host_label
from core.docker_client import docker_client
from core.plex_client import PLEX_URL
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends

router = APIRouter(tags=["maintainerr"])

SERVICE_META = {"label": "Maintainerr", "health_check": None}

MAINTAINERR_URL = "http://maintainerr:6246"

register_host_label(MAINTAINERR_URL, "Maintainerr")
install_hit_counter()


@router.get("/api/maintainerr/rules")
def maintainerr_rules(_=Depends(current_user_or_service)):
    """Configured maintenance rules. Installed deliberately with ZERO
    rules (this stack has 3+ documented mass-deletion incidents - see
    CLAUDE.md/STACK.md) - a non-empty list here is worth a second look,
    see maintainerr_safety_check() below."""
    try:
        r = httpx.get(f"{MAINTAINERR_URL}/api/rules", timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Maintainerr lookup failed: {e}")
    rules = r.json()
    items = [{"id": rl.get("id"), "name": rl.get("name"), "active": rl.get("isActive")} for rl in rules]
    return ok(f"{len(items)} rule(s) configured." if items else "No rules configured (expected - see CLAUDE.md).", items=items)


@router.get("/api/maintainerr/rule-detail")
def maintainerr_rule_detail(rule_id: int, _=Depends(current_user_or_service)):
    """Full definition of a single rule by id (from maintainerr_rules() above)."""
    try:
        r = httpx.get(f"{MAINTAINERR_URL}/api/rules/{rule_id}", timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Maintainerr lookup failed: {e}")
    return ok(f"Rule {rule_id} detail.", rule=r.json())


@router.get("/api/maintainerr/collections")
def maintainerr_collections(_=Depends(current_user_or_service)):
    """Plex collections Maintainerr is tracking for cleanup evaluation."""
    try:
        r = httpx.get(f"{MAINTAINERR_URL}/api/collections", timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Maintainerr lookup failed: {e}")
    collections = r.json()
    items = [{"id": c.get("id"), "title": c.get("title"), "media_count": len(c.get("media", []) or [])} for c in collections]
    return ok(f"{len(items)} collection(s) tracked.", items=items)


@router.get("/api/maintainerr/collection-media")
def maintainerr_collection_media(collection_id: int, _=Depends(current_user_or_service)):
    """Media items inside one tracked collection (from
    maintainerr_collections() above) and their current cleanup state."""
    try:
        r = httpx.get(f"{MAINTAINERR_URL}/api/collections/{collection_id}/media", timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Maintainerr lookup failed: {e}")
    items = r.json()
    return ok(f"{len(items)} media item(s) in collection {collection_id}.", items=items)


@router.get("/api/maintainerr/logs")
def maintainerr_logs(lines: int = 100, _=Depends(current_user_or_service)):
    """Tails Maintainerr's own container logs directly."""
    try:
        c = docker_client.containers.get("maintainerr")
    except docker.errors.NotFound:
        fail("Container 'maintainerr' not found.")
    raw = c.logs(tail=min(lines, 1000), timestamps=True).decode(errors="replace")
    return ok(f"Last {lines} line(s) from maintainerr.", log=raw)


@router.get("/api/maintainerr/safety-check")
def maintainerr_safety_check(_=Depends(current_user_or_service)):
    """Explicit guard tied directly to this stack's mass-deletion history:
    Maintainerr was installed with zero rules on purpose. This alerts
    loudly the moment that's no longer true, rather than a rule quietly
    appearing and running unnoticed."""
    try:
        r = httpx.get(f"{MAINTAINERR_URL}/api/rules", timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Maintainerr lookup failed: {e}")
    rules = r.json()
    active = [rl for rl in rules if rl.get("isActive")]
    if not active:
        return ok("Safe: no active rules configured.", active_count=0)
    names = ", ".join(rl.get("name", "?") for rl in active)
    return ok(f"WARNING: {len(active)} active rule(s) configured - review before trusting it not to delete "
              f"anything: {names}", active_count=len(active))


@router.get("/api/maintainerr/plex-link-check")
def maintainerr_plex_link_check(_=Depends(current_user_or_service)):
    """Misconfiguration guard: Maintainerr's Plex connection is entered
    via its own setup wizard, same drift risk as Prefetcharr above."""
    try:
        r = httpx.get(f"{MAINTAINERR_URL}/api/settings", timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Maintainerr lookup failed: {e}")
    settings = r.json()
    real_host = urlparse(PLEX_URL).hostname
    stored_host = settings.get("plex_hostname")
    matches = bool(stored_host) and stored_host == real_host
    msg = f"Maintainerr's Plex host ({stored_host}) matches this stack's ({real_host})." if matches else \
          f"MISMATCH: Maintainerr is pointed at '{stored_host}', this stack's Plex is at '{real_host}'."
    return ok(msg, matches=matches, stored_host=stored_host, real_host=real_host)
