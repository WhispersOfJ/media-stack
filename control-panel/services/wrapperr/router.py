"""Wrapperr routes, ported from app.py (lines 5362-5422) - Phase 4 of
.claude/plans/evolved-control-panel-backend.plan.md.

All routes are read-only - current_user_or_service throughout, same
reasoning as services/tautulli.
"""
import json
import os

import httpx
from core.api_hit_counts import install as install_hit_counter
from core.api_hit_counts import register_host_label
from core.host_paths import HOST_CONFIG_DIR
from core.responses import ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends
from services.tautulli.router import _tautulli_key

router = APIRouter(tags=["wrapperr"])

SERVICE_META = {"label": "Wrapperr", "health_check": None}

WRAPPERR_URL = "http://wrapperr:8282"

register_host_label(WRAPPERR_URL, "Wrapperr")
install_hit_counter()


def _wrapperr_config() -> dict:
    path = os.path.join(HOST_CONFIG_DIR, "wrapperr", "config.json")
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        return json.load(f)


@router.get("/api/wrapperr/status")
def wrapperr_status(_=Depends(current_user_or_service)):
    """Reachability + whether Wrapperr has a Tautulli connection saved at
    all (config.json is only written once its setup wizard completes)."""
    try:
        r = httpx.get(f"{WRAPPERR_URL}/", timeout=10)
        reachable = r.status_code < 500
    except httpx.HTTPError:
        reachable = False
    cfg = _wrapperr_config()
    configured = bool(cfg.get("tautulli_url") or cfg.get("tautulliUrl"))
    msg = "Wrapperr reachable" + (", Tautulli connection saved." if configured else ", but no Tautulli connection saved yet.")
    return ok(msg, reachable=reachable, configured=configured)


@router.get("/api/wrapperr/reports")
def wrapperr_reports(_=Depends(current_user_or_service)):
    """Saved report definitions from Wrapperr's config.json - it has no
    real query API of its own, reports are pre-built and rendered on
    request through its UI."""
    cfg = _wrapperr_config()
    reports = cfg.get("reports", [])
    names = [r.get("name") or r.get("title") for r in reports] if isinstance(reports, list) else []
    return ok(f"{len(names)} saved report(s)." if names else "No saved reports configured yet.", items=names)


@router.get("/api/wrapperr/links")
def wrapperr_links(_=Depends(current_user_or_service)):
    """Public share links Wrapperr has generated for specific reports."""
    path = os.path.join(HOST_CONFIG_DIR, "wrapperr", "links")
    if not os.path.isdir(path):
        return ok("No share links generated yet.", items=[])
    items = os.listdir(path)
    return ok(f"{len(items)} share link(s).", items=items)


@router.get("/api/wrapperr/tautulli-link-check")
def wrapperr_tautulli_link_check(_=Depends(current_user_or_service)):
    """Misconfiguration guard: Wrapperr stores its OWN copy of Tautulli's
    URL/API key (entered by hand in its setup wizard) rather than reading
    Tautulli's config directly - if either drifts (e.g. Tautulli's API key
    is regenerated), Wrapperr silently starts failing every report."""
    cfg = _wrapperr_config()
    stored_key = cfg.get("tautulli_api_key") or cfg.get("tautulliApiKey")
    real_key = _tautulli_key()
    if not stored_key:
        return ok("Wrapperr has no Tautulli API key saved yet.", matches=False)
    if not real_key:
        return ok("Tautulli has no API key generated yet to compare against.", matches=False)
    matches = stored_key == real_key
    msg = "Wrapperr's saved Tautulli key matches the live one." if matches else \
          "MISMATCH: Wrapperr's saved Tautulli API key is stale - re-enter it in Wrapperr's settings."
    return ok(msg, matches=matches)
