"""Kometa routes, ported from app.py (lines 5741-5815) - Phase 4 of
.claude/plans/evolved-control-panel-backend.plan.md.

All routes read-only except run-now (triggers an out-of-band run) -
current_user_or_service throughout, same reasoning as services/tautulli's
terminate-stream mutating route.
"""
import os
import re

import docker
import yaml
from core.docker_client import docker_client
from core.host_paths import HOST_CONFIG_DIR
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends

router = APIRouter(tags=["kometa"])

SERVICE_META = {"label": "Kometa", "health_check": None}


@router.get("/api/kometa/status")
def kometa_status(_=Depends(current_user_or_service)):
    """Kometa is a scheduled batch job (KOMETA_TIMES) with no API of its
    own - this parses its own periodic countdown log line for next-run
    time, the only signal it emits between runs."""
    try:
        c = docker_client.containers.get("kometa")
    except docker.errors.NotFound:
        fail("Container 'kometa' not found.")
    raw = c.logs(tail=5).decode(errors="replace")
    m = re.search(r"Current Time: (\S+).*?next run at (\S+)", raw)
    if not m:
        return ok("Could not parse a countdown line from recent logs.", raw=raw[-500:])
    return ok(f"Current time {m.group(1)}, next Kometa run at {m.group(2)}.", current_time=m.group(1), next_run=m.group(2))


@router.post("/api/kometa/run-now")
def kometa_run_now(_=Depends(current_user_or_service)):
    """Triggers an immediate Kometa run alongside its own scheduler loop
    (docker exec -d python3 kometa.py --run), rather than waiting for
    KOMETA_TIMES. Detached - returns immediately, doesn't wait for the run
    to finish (a full run can take minutes)."""
    try:
        c = docker_client.containers.get("kometa")
    except docker.errors.NotFound:
        fail("Container 'kometa' not found.")
    c.exec_run(["python3", "kometa.py", "--run"], detach=True)
    return ok("Kometa run triggered in the background - check kometa_logs() shortly for progress.")


@router.get("/api/kometa/logs")
def kometa_logs(lines: int = 100, _=Depends(current_user_or_service)):
    """Tails Kometa's own container logs directly (no log file - stdout
    only)."""
    try:
        c = docker_client.containers.get("kometa")
    except docker.errors.NotFound:
        fail("Container 'kometa' not found.")
    raw = c.logs(tail=min(lines, 2000)).decode(errors="replace")
    return ok(f"Last {lines} line(s) from kometa.", log=raw)


@router.get("/api/kometa/last-run-result")
def kometa_last_run_result(_=Depends(current_user_or_service)):
    """Distinct from kometa_status() (just the countdown): scans further
    back through the logs for the last actual run's outcome - a completed
    summary line, or a traceback if it errored out."""
    try:
        c = docker_client.containers.get("kometa")
    except docker.errors.NotFound:
        fail("Container 'kometa' not found.")
    raw_lines = c.logs(tail=5000).decode(errors="replace").splitlines()
    finished = [line for line in raw_lines if re.search(r"(?i)(finished|run complete)", line)]
    errors_found = [line for line in raw_lines if re.search(r"(?i)(traceback|error)", line)]
    if finished:
        return ok(f"Last completed run: {finished[-1].strip()}", errors=errors_found[-5:])
    if errors_found:
        return ok(f"No completed run found yet - {len(errors_found)} error line(s) in recent logs.", errors=errors_found[-5:])
    return ok("No run has completed yet (still waiting for the first KOMETA_TIMES run).", errors=[])


@router.get("/api/kometa/config")
def kometa_config(_=Depends(current_user_or_service)):
    """Effective config.yml as deployed - which libraries/collections it's
    set to touch, without opening the file by hand. From-scratch, Plex-
    only minimal build (TMDb/MDBList only, no Trakt) - see STACK.md."""
    path = os.path.join(HOST_CONFIG_DIR, "kometa", "config.yml")
    if not os.path.isfile(path):
        return ok("No config.yml found yet.", libraries=[])
    with open(path) as f:
        cfg = yaml.safe_load(f) or {}
    libraries = list((cfg.get("libraries") or {}).keys())
    return ok(f"{len(libraries)} librar{'y' if len(libraries) == 1 else 'ies'} configured: {', '.join(libraries)}.",
              libraries=libraries)
