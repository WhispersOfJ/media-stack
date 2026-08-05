"""Checkrr routes, ported from app.py (lines 5527-5605) - Phase 4 of
.claude/plans/evolved-control-panel-backend.plan.md.

All routes are read-only - current_user_or_service throughout, same
reasoning as services/tautulli. reacquire-guard exists specifically
because checkrr.yaml was deployed with process:false for every Arr app
(scan/log only, no auto-delete/reacquire - see CLAUDE.md's mass-deletion
history) - it alerts if that's ever flipped without a deliberate update.
"""
import csv
import os
import re

import docker
import yaml
from core.docker_client import docker_client
from core.host_paths import HOST_CONFIG_DIR
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends

router = APIRouter(tags=["checkrr"])

SERVICE_META = {"label": "Checkrr", "health_check": None}


def _checkrr_config() -> dict:
    path = os.path.join(HOST_CONFIG_DIR, "checkrr", "checkrr.yaml")
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


@router.get("/api/checkrr/badfiles")
def checkrr_badfiles(limit: int = 50, _=Depends(current_user_or_service)):
    """Corrupt/unreadable files Checkrr has flagged, from its own CSV log
    (process:false - see CLAUDE.md/STACK.md - so nothing gets deleted or
    reacquired automatically, this is scan/log only)."""
    path = os.path.join(HOST_CONFIG_DIR, "checkrr", "badfiles.csv")
    if not os.path.isfile(path):
        return ok("No bad files logged yet.", items=[])
    items = []
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if len(row) >= 2:
                items.append({"path": row[0], "reason": row[1]})
    return ok(f"{len(items)} bad file(s) logged (showing up to {limit}).", items=items[:limit], total=len(items))


@router.get("/api/checkrr/config")
def checkrr_config(_=Depends(current_user_or_service)):
    """Effective scan config - checkpaths and the process flags per Arr
    app. process:false everywhere is the expected/safe state (see
    CLAUDE.md's mass-deletion history) - checkrr_reacquire_guard() below
    alerts specifically if that ever changes."""
    cfg = _checkrr_config()
    arr = cfg.get("arr", {}) or {}
    process_flags = {name: (settings or {}).get("process", False) for name, settings in arr.items()}
    return ok(f"Scanning {', '.join(cfg.get('checkrr', {}).get('checkpath', []))}, cron {cfg.get('checkrr', {}).get('cron')}.",
              checkpaths=cfg.get("checkrr", {}).get("checkpath", []), process_flags=process_flags)


@router.get("/api/checkrr/reacquire-guard")
def checkrr_reacquire_guard(_=Depends(current_user_or_service)):
    """Explicit guard: checkrr.yaml was deployed with process:false for
    every Arr app (scan/log only, no auto-delete/reacquire - see
    CLAUDE.md). Alerts if that's ever flipped to true without a
    corresponding, deliberate CLAUDE.md update."""
    cfg = _checkrr_config()
    arr = cfg.get("arr", {}) or {}
    live = {name: (settings or {}).get("process", False) for name, settings in arr.items()}
    flipped = [name for name, val in live.items() if val]
    if not flipped:
        return ok("Safe: process:false for every configured Arr app.", flipped=[])
    return ok(f"WARNING: process:true for {', '.join(flipped)} - Checkrr will now auto-reacquire/delete for "
              f"{'this app' if len(flipped) == 1 else 'these apps'}.", flipped=flipped)


@router.get("/api/checkrr/scan-status")
def checkrr_scan_status(lines: int = 40, _=Depends(current_user_or_service)):
    """Tails Checkrr's own container logs (stdout-only, no log file - see
    its compose comment) for the most recent scan activity."""
    try:
        c = docker_client.containers.get("checkrr")
    except docker.errors.NotFound:
        fail("Container 'checkrr' not found.")
    raw_lines = c.logs(tail=min(lines, 1000)).decode(errors="replace").splitlines()
    relevant = [line for line in raw_lines if line.strip()]
    return ok(f"Last {len(relevant)} log line(s) from checkrr.", lines=relevant)


@router.get("/api/checkrr/recent-scans")
def checkrr_recent_scans(_=Depends(current_user_or_service)):
    """Distinct from scan_status() above: pulls out just the scan-cycle
    boundary lines (start/finish) from a much larger log tail, to see scan
    cadence/duration without reading the full per-file output."""
    try:
        c = docker_client.containers.get("checkrr")
    except docker.errors.NotFound:
        fail("Container 'checkrr' not found.")
    raw_lines = c.logs(tail=2000).decode(errors="replace").splitlines()
    markers = [line for line in raw_lines if re.search(r"(?i)(starting|finished|complete).{0,20}scan", line)]
    return ok(f"{len(markers)} scan-cycle marker(s) found in recent logs.", lines=markers[-20:])
