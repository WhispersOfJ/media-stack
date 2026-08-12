"""Speedtest Tracker routes - Phase 2 of PLANS.md's 7-service integration
batch. Scheduled ISP speed monitoring + history, so link degradation is
visible before it's the reason downloads/streaming feel slow.

Auth deviation from PLANS.md 2.5's original assumption: Speedtest Tracker's
API tokens are Laravel Sanctum personal-access tokens, only ever creatable
via its own web UI (/admin/api-tokens) - confirmed the image ships without
`artisan tinker` (`php artisan tinker` errors "Command not defined"), and
Sanctum stores only a SHA-256 *hash* of the token in its sqlite DB, so
there is no "read the plaintext back out of the DB" path the way Tautulli's
flat-file config.ini allows either. This stack provisions the token once by
replicating Sanctum's own HasApiTokens::createToken() algorithm and
inserting the row directly into the bind-mounted database.sqlite via
Python's stdlib sqlite3 from the host (see STACK.md's Speedtest Tracker
entry for the exact algorithm), stores the raw token in .env as
SPEEDTEST_TRACKER_API_TOKEN, and reads it as a plain env var here - same
pattern as FRONTEND_BACKEND_API_KEY elsewhere in this stack, not a sqlite
query at request time.
"""
import os
from datetime import datetime, timedelta, timezone

import httpx
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends

router = APIRouter(tags=["speedtest_tracker"])

SERVICE_META = {"label": "Speedtest Tracker", "health_check": None}

SPEEDTEST_TRACKER_URL = "http://speedtest-tracker:80"


def _token() -> str | None:
    return os.environ.get("SPEEDTEST_TRACKER_API_TOKEN")


def _headers() -> dict:
    token = _token()
    if not token:
        fail("No Speedtest Tracker API token configured (SPEEDTEST_TRACKER_API_TOKEN unset - has provisioning run yet?).", status_code=500)
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


@router.get("/api/speedtest-tracker/latest")
def speedtest_tracker_latest(_=Depends(current_user_or_service)):
    """Most recent completed speedtest result (down/up/ping/jitter)."""
    try:
        r = httpx.get(f"{SPEEDTEST_TRACKER_URL}/api/v1/results/latest", headers=_headers(), timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Speedtest Tracker lookup failed: {e}")
    data = r.json().get("data", r.json())
    ping = (data.get("data") or {}).get("ping", {})
    return ok(
        f"Latest result: {data.get('download_bits_human') or data.get('download')} down / "
        f"{data.get('upload_bits_human') or data.get('upload')} up.",
        download=data.get("download"), upload=data.get("upload"),
        ping=ping.get("latency"), jitter=ping.get("jitter"),
        status=data.get("status"), healthy=data.get("healthy"),
        created_at=data.get("created_at"),
    )


@router.get("/api/speedtest-tracker/history")
def speedtest_tracker_history(days: int = 7, _=Depends(current_user_or_service)):
    """Results from the last N days, newest first. Speedtest Tracker's own
    /api/v1/results has no date-range query param, so this filters
    client-side against created_at instead."""
    try:
        r = httpx.get(f"{SPEEDTEST_TRACKER_URL}/api/v1/results", headers=_headers(), timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Speedtest Tracker lookup failed: {e}")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items = []
    for row in r.json().get("data", []):
        created_at = row.get("created_at")
        try:
            # Live responses come back as "2026-08-12 02:15:00" (space-
            # separated, no offset - Laravel's default cast, UTC) rather
            # than the docs' "2024-01-15T10:30:00Z" example - handle both,
            # and treat a naive result as UTC rather than erroring on the
            # naive-vs-aware comparison below.
            when = datetime.fromisoformat((created_at or "").replace("Z", "+00:00").replace(" ", "T"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if when < cutoff:
            continue
        items.append({"download": row.get("download"), "upload": row.get("upload"),
                       "ping": (row.get("data") or {}).get("ping", {}).get("latency"),
                       "status": row.get("status"), "created_at": created_at})
    return ok(f"{len(items)} result(s) in the last {days} day(s).", items=items)


@router.post("/api/speedtest-tracker/run")
def speedtest_tracker_run_now(_=Depends(current_user_or_service)):
    """Triggers an out-of-schedule speedtest run."""
    try:
        r = httpx.post(f"{SPEEDTEST_TRACKER_URL}/api/v1/speedtests/run", headers=_headers(), timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Speedtest Tracker run request failed: {e}")
    body = r.json()
    return ok(body.get("message") or "Speedtest queued.", **(body.get("data") or {}))
