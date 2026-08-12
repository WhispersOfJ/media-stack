"""Cross-cutting health sweep across the 2026-07-30 "new apps" batch,
ported from app.py (lines 5808-5866) - Phase 4 of
.claude/plans/evolved-control-panel-backend.plan.md.

Not one integration's concern - kept in its own directory rather than
bolted onto any single service/host router, same "one concern, one
directory" reasoning as every other services/<name> split.
"""
import docker
import httpx
from core.docker_client import docker_client
from core.responses import ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends

router = APIRouter(tags=["newapps"])

SERVICE_META = {"label": "New Apps", "health_check": None}

NEW_APP_CONTAINERS = ["tautulli", "wrapperr", "maintainerr", "checkrr", "prefetcharr", "lingarr", "kometa"]


@router.get("/api/newapps/status")
def newapps_status(_=Depends(current_user_or_service)):
    """One-shot health sweep across all 2026-07-30 additions - container
    running state plus an HTTP reachability probe for the ones with a
    port (prefetcharr and kometa have neither, so those are container-
    status-only)."""
    ports = {"tautulli": 8181, "wrapperr": 8282, "maintainerr": 6246, "checkrr": 8585, "lingarr": 8080}
    out = {}
    for name in NEW_APP_CONTAINERS:
        try:
            c = docker_client.containers.get(name)
            running = c.status == "running"
        except docker.errors.NotFound:
            out[name] = {"running": False, "reachable": None, "error": "container not found"}
            continue
        reachable = None
        if name in ports and running:
            try:
                r = httpx.get(f"http://{name}:{ports[name]}/", timeout=5)
                reachable = r.status_code < 500
            except httpx.HTTPError:
                reachable = False
        out[name] = {"running": running, "reachable": reachable}
    down = [n for n, s in out.items() if not s["running"] or s["reachable"] is False]
    msg = "All 8 new apps healthy." if not down else f"Problem with: {', '.join(down)}"
    return ok(msg, apps=out)
