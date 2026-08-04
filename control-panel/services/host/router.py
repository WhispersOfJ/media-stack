"""Fleet status/control + settings, ported from app.py (lines 437-501,
3802-3970) - Phase 2 of .claude/plans/evolved-control-panel-backend.plan.md.

Auth split per the plan's Acceptance criteria: read-only routes accept
either a session or the health-check cron's service API key
(current_user_or_service); every mutating route (restart/stop/start,
restart-all, PATCH settings) requires a real logged-in session.
"""
import concurrent.futures
import threading

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Literal

from core.docker_client import (
    CONTAINER_LABELS,
    MOUNT_DEPENDENTS,
    MOUNT_PREREQS,
    MOUNT_PROVIDERS,
    container_label,
    container_stats,
    find_project_container,
    project_containers,
    wait_for_healthy,
)
from core.responses import fail, ok
from core.security import current_user, current_user_or_service
from core import settings as settings_core

router = APIRouter(tags=["host"])

SERVICE_META = {"label": "Host/Fleet", "health_check": None}


@router.get("/api/status")
def status(_=Depends(current_user_or_service)):
    _, containers = project_containers()
    out = {}
    for c in containers:
        health = c.attrs.get("State", {}).get("Health", {}).get("Status")
        out[c.name] = {"state": c.status, "health": health}
    return out


def _container_row(me, c) -> dict:
    label, note = CONTAINER_LABELS.get(c.name, (c.name, None))
    health = c.attrs.get("State", {}).get("Health", {}).get("Status")
    image_tags = c.image.tags
    image = image_tags[0] if image_tags else (c.image.short_id or "")
    service = c.labels.get("com.docker.compose.service", c.name)
    return {
        "name": c.name,
        "label": label,
        "note": note,
        "service": service,
        "image": image,
        "state": c.status,
        "health": health,
        "is_self": c.id == me.id,
        **container_stats(c),
    }


@router.get("/api/containers")
def containers_list(_=Depends(current_user_or_service)):
    me, containers = project_containers()
    ordered = sorted(containers, key=lambda c: c.name)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(ordered), 16) or 1) as pool:
        return list(pool.map(lambda c: _container_row(me, c), ordered))


@router.post("/api/container/{name}/restart")
def container_restart(name: str, activated: bool = False, _=Depends(current_user)):
    if name == "plex" and not activated:
        fail(
            "Plex restart requires activated=true - a plain restart click is no longer "
            "enough (by design). Pass activated=true explicitly to restart Plex.",
            status_code=400,
        )
    c = find_project_container(name, reject_self=True)
    try:
        c.restart(timeout=30)
    except Exception as e:
        fail(f"Restart failed: {e}")
    return ok(f"{container_label(name)} restarted.")


@router.post("/api/container/{name}/stop")
def container_stop(name: str, _=Depends(current_user)):
    c = find_project_container(name, reject_self=True)
    if c.status != "running":
        return ok(f"{container_label(name)} is already {c.status}.")
    try:
        c.stop(timeout=30)
    except Exception as e:
        fail(f"Stop failed: {e}")
    return ok(f"{container_label(name)} stopped.")


@router.post("/api/container/{name}/start")
def container_start(name: str, _=Depends(current_user)):
    c = find_project_container(name, reject_self=False)
    if c.status == "running":
        return ok(f"{container_label(name)} is already running.")
    try:
        c.start()
    except Exception as e:
        fail(f"Start failed: {e}")
    return ok(f"{container_label(name)} started.")


@router.get("/api/container/{name}/logs/stream")
def container_logs_stream(name: str, tail: int = 100, _=Depends(current_user_or_service)):
    c = find_project_container(name, reject_self=False)

    def generate():
        for line in c.logs(stream=True, follow=True, tail=tail, timestamps=True):
            text = line.decode(errors="replace").rstrip("\n")
            for part in text.splitlines() or [""]:
                yield f"data: {part}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/api/stack/restart-all")
def stack_restart_all(_=Depends(current_user)):
    me, containers = project_containers()
    targets = [c for c in containers if c.id != me.id]
    if not targets:
        fail("No other containers found in this compose project.")
    names = sorted(c.name for c in targets)

    prereqs = [c for c in targets if c.name in MOUNT_PREREQS]
    providers = [c for c in targets if c.name in MOUNT_PROVIDERS]
    dependents = [c for c in targets if c.name in MOUNT_DEPENDENTS]
    staged = MOUNT_PREREQS | MOUNT_PROVIDERS | MOUNT_DEPENDENTS
    rest = [c for c in targets if c.name not in staged]

    def worker():
        for c in prereqs:
            try:
                c.restart(timeout=30)
            except Exception as e:
                print(f"restart-all: failed to restart {c.name}: {e}")
        for c in prereqs:
            wait_for_healthy(c)
        for c in providers:
            try:
                c.restart(timeout=30)
            except Exception as e:
                print(f"restart-all: failed to restart {c.name}: {e}")
        for c in providers:
            wait_for_healthy(c)
        for c in rest:
            try:
                c.restart(timeout=30)
            except Exception as e:
                print(f"restart-all: failed to restart {c.name}: {e}")
        for c in dependents:
            try:
                c.restart(timeout=30)
            except Exception as e:
                print(f"restart-all: failed to restart {c.name}: {e}")
        # nzbdav bind-mounts /mnt directly too, not just as an upstream
        # prereq for nzbdav_rclone - re-restart it here, after every other
        # mount consumer has settled on the provider's final instance, to
        # rebind it. Same reasoning as app.py's stack_restart_all.
        for c in prereqs:
            try:
                c.restart(timeout=30)
            except Exception as e:
                print(f"restart-all: failed to restart {c.name}: {e}")

    threading.Thread(target=worker, daemon=True).start()
    return ok(f"Restarting {len(names)} containers (everything except this panel): {', '.join(names)}")


class SettingsPatch(BaseModel):
    theme: Literal["dark", "light"] | None = None
    failed_pending_storm_threshold: int | None = None
    loop_review_profile_threshold: int | None = None


@router.get("/api/settings")
def get_settings(_=Depends(current_user_or_service)):
    return settings_core.get_settings()


@router.patch("/api/settings")
def patch_settings(body: SettingsPatch, _=Depends(current_user)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return settings_core.update_settings(patch)
