"""Scrutiny routes - Phase 4 of PLANS.md's 7-service integration batch.
S.M.A.R.T. health trending and failure prediction, layered on top of (not
replacing) the raw-smartctl `stack-disk-health` check.

Scope reality this stack, worth knowing before reading the code: there is
exactly ONE physical disk here, a 954GB NVMe. PLANS.md 4.1 assumed a
multi-disk SATA array (`/dev/sda`, `/dev/sdb`). Everything else the stack
serves lives on the Usenet-backed FUSE mount, which has no SMART data to
trend. So these routes are really about NVMe wear tracking on the single
disk the whole stack runs on.

No auth against Scrutiny itself - it ships with none, and it is not exposed
publicly. Auth is this panel's own `current_user_or_service`, same as every
other route here.
"""
import docker
import httpx
from core.docker_client import docker_client
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends

router = APIRouter(tags=["scrutiny"])

SERVICE_META = {"label": "Scrutiny", "health_check": None}

SCRUTINY_URL = "http://scrutiny:8080"

# Scrutiny's own device_status enum: 0 is passing, anything non-zero is a
# failure of at least one of its three checks (SMART self-assessment,
# per-attribute thresholds, its own failure-rate heuristic).
STATUS_PASSED = 0

# The NVMe attributes worth surfacing in a terminal summary. Scrutiny tracks
# 16 for an NVMe device; these are the ones that actually predict end-of-life
# or indicate damage, rather than raw counters (host_reads, data_units_read
# and friends) that only mean something as a trend line in the web UI.
WEAR_ATTRS = (
    "critical_warning",
    "available_spare",
    "percentage_used",
    "media_errors",
    "unsafe_shutdowns",
    "num_err_log_entries",
)


def _get(path: str) -> dict:
    try:
        r = httpx.get(f"{SCRUTINY_URL}{path}", timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Scrutiny request failed: {e}")
    return r.json()


def _summary_map() -> dict:
    body = _get("/api/summary")
    return ((body.get("data") or {}).get("summary")) or {}


def _resolve_uuid(disk_id: str, summary: dict) -> str | None:
    """Accepts a Scrutiny UUID, a device name (`nvme0`, `sda`) or a serial.

    Scrutiny's own API only takes its internal UUID, which nobody has
    memorised and which changes if a device is re-registered. Resolving a
    friendly identifier here keeps `stack-scrutiny-disk nvme0` usable.
    """
    if disk_id in summary:
        return disk_id
    needle = disk_id.lower()
    for uuid, entry in summary.items():
        device = entry.get("device") or {}
        candidates = {
            str(device.get("device_name") or "").lower(),
            str(device.get("serial_number") or "").lower(),
            str(device.get("device_label") or "").lower(),
        }
        if needle in candidates:
            return uuid
    return None


@router.get("/api/scrutiny/summary")
def scrutiny_summary(_=Depends(current_user_or_service)):
    """All-disk status at a glance: model, temperature, power-on hours, and
    whether Scrutiny considers each device healthy."""
    summary = _summary_map()
    disks, failing = [], []
    for uuid, entry in summary.items():
        device = entry.get("device") or {}
        smart = entry.get("smart") or {}
        device_status = device.get("device_status")
        healthy = device_status == STATUS_PASSED
        if not healthy:
            failing.append(device.get("device_name"))
        disks.append({
            "uuid": uuid,
            "name": device.get("device_name"),
            "model": device.get("model_name"),
            "serial": device.get("serial_number"),
            "protocol": device.get("device_protocol"),
            "capacity": device.get("capacity"),
            "healthy": healthy,
            "device_status": device_status,
            "temp_c": smart.get("temp"),
            "power_on_hours": smart.get("power_on_hours"),
            "last_collected": smart.get("collector_date"),
        })

    if not disks:
        # Registered-but-empty is the normal state between container start
        # and the first collector run, so say which it is rather than
        # implying the disk is gone.
        return ok("No disks registered yet - has the collector run? (stack-scrutiny-collect)", disks=[])
    if failing:
        return ok(f"{len(failing)} of {len(disks)} disk(s) FAILING: {', '.join(filter(None, failing))}.",
                  disks=disks, failing=failing)
    return ok(f"{len(disks)} disk(s), all healthy.", disks=disks, failing=[])


@router.get("/api/scrutiny/disk")
def scrutiny_disk(disk_id: str = "", _=Depends(current_user_or_service)):
    """Per-disk SMART detail. `disk_id` may be Scrutiny's UUID, a device
    name (`nvme0`) or a serial number.

    Optional: this host has one disk, so omitting it picks that disk rather
    than making the caller look up an identifier to describe the only
    possible answer. With more than one registered it becomes required.
    """
    summary = _summary_map()
    if not summary:
        fail("No disks registered yet - has the collector run? (stack-scrutiny-collect)", status_code=404)
    if not disk_id:
        if len(summary) > 1:
            names = ", ".join(sorted(
                str((e.get("device") or {}).get("device_name")) for e in summary.values()
            ))
            fail(f"{len(summary)} disks registered - name one of: {names}.", status_code=400)
        disk_id = next(iter(summary))

    uuid = _resolve_uuid(disk_id, summary)
    if not uuid:
        known = ", ".join(sorted(
            str((e.get("device") or {}).get("device_name")) for e in summary.values()
        )) or "none registered"
        fail(f"No disk matching '{disk_id}'. Known devices: {known}.", status_code=404)

    data = _get(f"/api/device/{uuid}/details").get("data") or {}
    device = data.get("device") or {}
    results = data.get("smart_results") or []
    if not results:
        return ok(f"{device.get('device_name')}: registered but no SMART results yet.",
                  uuid=uuid, name=device.get("device_name"), attrs={})

    latest = results[0]
    attrs = latest.get("attrs") or {}
    wear = {
        key: {"value": attrs[key].get("value"), "status": attrs[key].get("status")}
        for key in WEAR_ATTRS if key in attrs
    }
    # Any attribute Scrutiny itself flagged, even one outside WEAR_ATTRS.
    flagged = sorted(k for k, v in attrs.items() if v.get("status") != STATUS_PASSED)

    message = f"{device.get('device_name')} ({device.get('model_name')}): {latest.get('temp')}C, {latest.get('power_on_hours')}h powered on"
    if flagged:
        message += f" - {len(flagged)} attribute(s) flagged: {', '.join(flagged)}"
    return ok(
        message,
        uuid=uuid, name=device.get("device_name"), model=device.get("model_name"),
        serial=device.get("serial_number"), firmware=device.get("firmware"),
        temp_c=latest.get("temp"), power_on_hours=latest.get("power_on_hours"),
        power_cycle_count=latest.get("power_cycle_count"),
        collected=latest.get("date"), wear=wear, flagged=flagged,
        attr_count=len(attrs), history_points=len(results),
    )


@router.post("/api/scrutiny/collect")
def scrutiny_collect(_=Depends(current_user_or_service)):
    """Runs the metrics collector now instead of waiting for its daily cron.

    Not detached, unlike Kometa's run-now: a SMART sweep of this host's one
    disk takes about a second, and returning the collector's own output is
    far more useful than making the caller go and tail logs.
    """
    try:
        container = docker_client.containers.get("scrutiny")
    except docker.errors.NotFound:
        fail("Container 'scrutiny' not found.")
    result = container.exec_run(["/opt/scrutiny/bin/scrutiny-collector-metrics", "run"])
    output = (result.output or b"").decode(errors="replace")
    if result.exit_code != 0:
        fail(f"Collector exited {result.exit_code}: {output[-600:]}")
    published = output.count("Publishing smartctl results")
    return ok(f"Collector run complete, {published} device(s) published.",
              devices_published=published, output=output[-2000:])


@router.post("/api/scrutiny/alert-test")
def scrutiny_alert_test(_=Depends(current_user_or_service)):
    """Fires Scrutiny's own test notification through whatever `notify.urls`
    its config has - which in this stack is the ntfy sink from Phase 1.
    Proves the disk-failure alert path works without waiting for a disk to
    actually start failing."""
    try:
        r = httpx.post(f"{SCRUTINY_URL}/api/health/notify", timeout=30)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Scrutiny test notification failed: {e}")
    body = r.json()
    if not body.get("success", True):
        fail(f"Scrutiny reported the notification failed: {body}")
    # Key is `scrutiny_response`, NOT `detail`. __stack_api unwraps any
    # top-level dict `detail` key as FastAPI's HTTPException envelope
    # (fish-functions/__stack_api.fish), so a success payload carrying
    # `detail` gets mistaken for an error body and prints raw JSON instead
    # of the message. Caught live on 2026-08-12, not by the tests - the
    # router was correct in isolation and only wrong through the CLI.
    return ok("Test notification sent - check the 'scrutiny-alerts' ntfy topic.", scrutiny_response=body)
