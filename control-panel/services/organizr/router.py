"""Organizr routes - Phase 3 of PLANS.md's 7-service integration batch.
Single landing dashboard with one tab per service in the stack.

Auth deviation from PLANS.md 3.2's "no secrets required for base
operation": there is no such thing as an unauthenticated Organizr. The
setup wizard mandates an admin account, and every API route past /ping
runs through qualifyRequest(). This stack authenticates as admin with the
20-char key it handed Organizr at wizard time, sent as a `Token:` header -
isApprovedRequest (api/classes/organizr.class.php:4596-4623) accepts that
key, treats the caller as admin, and skips the CSRF formKey check that
would otherwise reject any non-browser POST. Read as a plain env var, same
pattern as SPEEDTEST_TRACKER_API_TOKEN, not read back off disk like
Tautulli's config.ini - we chose the key rather than Organizr generating it.

Provisioning deviation from PLANS.md 3.4's "manual by design": Organizr
does expose a full tabs API, so /tabs/sync below and the host-side
scripts/organizr-provision.py share one tab table (services/organizr/
tabs.py) and neither needs a click-through. See that module for the
per-service iframe/new-window decision and how it was measured.
"""
import os

import httpx
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends

from .tabs import TABS, tab_payload

router = APIRouter(tags=["organizr"])

SERVICE_META = {"label": "Organizr", "health_check": None}

ORGANIZR_URL = "http://organizr:80"


def _headers() -> dict:
    token = os.environ.get("ORGANIZR_API_KEY")
    if not token:
        fail("No Organizr API key configured (ORGANIZR_API_KEY unset).", status_code=500)
    if len(token) != 20:
        # Organizr compares strlen($token) == 20 before it compares the
        # value, so a wrong-length key 401s every route with no useful
        # error. Fail loudly here instead of blaming Organizr later.
        fail(f"ORGANIZR_API_KEY must be exactly 20 characters, got {len(token)}.", status_code=500)
    return {"Token": token, "Accept": "application/json"}


def _fetch_tabs() -> dict:
    try:
        r = httpx.get(f"{ORGANIZR_URL}/api/v2/tabs", headers=_headers(), timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Organizr tab lookup failed: {e}")
    return (r.json().get("response") or {}).get("data") or {}


@router.get("/api/organizr/health")
def organizr_health(_=Depends(current_user_or_service)):
    """Unauthenticated upstream ping - answers 200 both before and after
    the setup wizard has run, which is why it also backs the container
    healthcheck and health-monitor's probe."""
    try:
        r = httpx.get(f"{ORGANIZR_URL}/api/v2/ping", timeout=10)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Organizr unreachable: {e}")
    pong = (r.json().get("response") or {}).get("data")
    return ok(f"Organizr responded: {pong}.", pong=pong)


@router.get("/api/organizr/tabs")
def organizr_tabs(_=Depends(current_user_or_service)):
    """Every tab Organizr currently has, including its own two built-in
    type-0 pages (Settings, Homepage) which this stack does not manage."""
    data = _fetch_tabs()
    items = []
    for tab in data.get("tabs", []):
        items.append({
            "name": tab.get("name"),
            "url": tab.get("url"),
            "type": tab.get("type"),
            "enabled": bool(tab.get("enabled")),
            "group_id": tab.get("group_id"),
        })
    managed = {t["name"] for t in TABS}
    missing = sorted(managed - {i["name"] for i in items})
    return ok(
        f"{len(items)} tab(s) configured, {len(missing)} of this stack's {len(TABS)} missing.",
        items=items, missing=missing,
    )


@router.post("/api/organizr/tabs/sync")
def organizr_tabs_sync(_=Depends(current_user_or_service)):
    """Adds any tab from the canonical table that Organizr doesn't have.

    Additive only, deliberately: it never edits or deletes a tab that is
    already there, so a tab hand-tweaked in Organizr's UI survives a sync
    and a stray tab someone added on purpose isn't silently reaped.
    """
    existing = {t.get("name") for t in _fetch_tabs().get("tabs", [])}
    host_ip = os.environ.get("HOST_IP", "")
    if not host_ip:
        fail("HOST_IP unset - tab URLs are loaded by the browser and cannot use container names.", status_code=500)

    added, skipped = [], []
    for tab in TABS:
        if tab["name"] in existing:
            skipped.append(tab["name"])
            continue
        try:
            r = httpx.post(
                f"{ORGANIZR_URL}/api/v2/tabs",
                headers={**_headers(), "Content-Type": "application/json"},
                json=tab_payload(tab, host_ip), timeout=15,
            )
        except httpx.HTTPError as e:
            fail(f"Adding tab '{tab['name']}' failed: {e}")
        if r.status_code == 409:
            # Name already taken by a tab we didn't create. Not an error.
            skipped.append(tab["name"])
            continue
        if r.status_code != 200:
            message = ((r.json().get("response") or {}).get("message")) if r.content else r.status_code
            fail(f"Adding tab '{tab['name']}' failed: {message}")
        added.append(tab["name"])

    return ok(f"{len(added)} tab(s) added, {len(skipped)} already present.", added=added, skipped=skipped)
