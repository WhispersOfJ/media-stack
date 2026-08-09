"""ntfy routes - Phase 1 of PLANS.md's 7-service integration batch.

ntfy is the shared push-notification sink for the whole stack (replaces
N per-app ad-hoc notification setups with one place to publish/subscribe).
Anonymous read/write is intentional (see PLANS.md 1.1 / STACK.md) - the
stack is not exposed publicly, so no auth-file was configured.

setup-connections is the one mutating route here: it registers an Ntfy
notification connection (native implementation, both Radarr and Sonarr
ship one - confirmed against the running Radarr's /api/v3/notification/schema)
on every Arr-family app plus Prowlarr, so this doesn't need doing by hand
five times. Automation-invoked, not session-only - same documented
exception as services/tautulli's terminate-stream and services/host's
notify/test.
"""
import httpx
from core.arr_client import ARR_APPS, PROWLARR_CFG
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(tags=["ntfy"])

SERVICE_META = {"label": "ntfy", "health_check": None}

NTFY_URL = "http://ntfy:80"

# One topic per app - keeps each app's alerts separable in an ntfy client
# without needing per-app auth. Prowlarr isn't in ARR_APPS (it's indexer
# management, not a queue-shaped app) so it's wired separately below.
NTFY_TOPICS = {
    "radarr": "radarr-alerts",
    "sonarr": "sonarr-alerts",
    "radarr_anime": "radarr-anime-alerts",
    "sonarr_anime": "sonarr-anime-alerts",
    "prowlarr": "prowlarr-alerts",
}


class PublishBody(BaseModel):
    topic: str
    message: str
    title: str | None = None
    priority: int | None = None


@router.post("/api/ntfy/publish")
def ntfy_publish(body: PublishBody, _=Depends(current_user_or_service)):
    """Publishes one message to one topic - the primitive every other
    notification path in the stack (Arr apps, stack-notify-test) builds on."""
    headers = {}
    if body.title:
        headers["Title"] = body.title
    if body.priority:
        headers["Priority"] = str(body.priority)
    try:
        r = httpx.post(f"{NTFY_URL}/{body.topic}", content=body.message.encode(), headers=headers, timeout=10)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"ntfy publish failed: {e}")
    return ok(f"Published to topic '{body.topic}'.")


@router.get("/api/ntfy/topics")
def ntfy_topics(_=Depends(current_user_or_service)):
    """ntfy has no server-side 'list all topics' API by design (topics
    aren't pre-registered, and listing them all would leak every topic to
    anyone with server access) - this returns the topics *this stack*
    knows it publishes to, not a live query against ntfy itself."""
    items = [{"app": app, "topic": topic} for app, topic in NTFY_TOPICS.items()]
    return ok(f"{len(items)} known topic(s) configured by this stack.", items=items)


@router.get("/api/ntfy/health")
def ntfy_health(_=Depends(current_user_or_service)):
    try:
        r = httpx.get(f"{NTFY_URL}/v1/health", timeout=10)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"ntfy unreachable: {e}")
    data = r.json()
    healthy = bool(data.get("healthy"))
    return ok("ntfy is healthy." if healthy else "ntfy reports unhealthy.", healthy=healthy)


def _arr_notification_payload(topic: str) -> dict:
    # Every field in the schema must be present, even the optional ones -
    # confirmed live against Radarr's /api/v3/notification: omitting
    # accessToken/userName/password/tags/clickUrl 400s with a misleading
    # "Value cannot be null. (Parameter 'source')" rather than naming the
    # actually-missing field.
    return {
        "onGrab": True,
        "onDownload": True,
        "onUpgrade": True,
        "onHealthIssue": True,
        "includeHealthWarnings": True,
        "onHealthRestored": True,
        "onApplicationUpdate": True,
        "onManualInteractionRequired": True,
        "name": "ntfy",
        "fields": [
            {"name": "serverUrl", "value": NTFY_URL},
            {"name": "accessToken", "value": ""},
            {"name": "userName", "value": ""},
            {"name": "password", "value": ""},
            {"name": "priority", "value": 3},
            {"name": "topics", "value": [topic]},
            {"name": "tags", "value": []},
            {"name": "clickUrl", "value": ""},
        ],
        "implementation": "Ntfy",
        "implementationName": "ntfy.sh",
        "configContract": "NtfySettings",
    }


def _has_ntfy_connection(base_url: str, api_version: str, key: str) -> bool:
    r = httpx.get(f"{base_url}/api/{api_version}/notification", headers={"X-Api-Key": key}, timeout=10)
    r.raise_for_status()
    return any(n.get("implementation") == "Ntfy" for n in r.json())


@router.post("/api/ntfy/setup-connections")
def ntfy_setup_connections(_=Depends(current_user_or_service)):
    """Adds an Ntfy notification connection to every Arr-family app plus
    Prowlarr, each pointed at its own topic (NTFY_TOPICS above). Skips any
    app that already has one, so this is safe to re-run."""
    results = []
    targets = {name: (cfg["url"], cfg["api"], cfg["key"]) for name, cfg in ARR_APPS.items()}
    targets["prowlarr"] = (PROWLARR_CFG["url"], PROWLARR_CFG["api"], PROWLARR_CFG["key"])
    for name, (base_url, api_version, key) in targets.items():
        topic = NTFY_TOPICS[name]
        try:
            if _has_ntfy_connection(base_url, api_version, key):
                results.append({"app": name, "status": "already configured"})
                continue
            r = httpx.post(
                f"{base_url}/api/{api_version}/notification",
                headers={"X-Api-Key": key},
                json=_arr_notification_payload(topic),
                timeout=10,
            )
            r.raise_for_status()
            results.append({"app": name, "status": f"connected, topic={topic}"})
        except httpx.HTTPError as e:
            results.append({"app": name, "status": f"failed: {e}"})
    failures = [r["app"] for r in results if r["status"].startswith("failed")]
    msg = f"{len(results) - len(failures)}/{len(results)} app(s) wired to ntfy." + \
          (f" Failed: {', '.join(failures)}." if failures else "")
    return ok(msg, results=results)
