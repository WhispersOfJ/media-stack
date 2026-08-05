"""Backup (restic) routes, ported from app.py (lines 4323-4402, 4764-4790,
5057-5074) - Phase 4 of .claude/plans/evolved-control-panel-backend.plan.md.

All read-only against restic repos mounted read-only into this container,
or a scratch-path restore test (backup-restore-test) that writes nothing
back to the repo - current_user_or_service throughout, same reasoning as
services/arr's automation-invoked routes.
"""
import json
import os
import subprocess

from core.host_paths import (
    HOST_BACKUP_LOCAL,
    HOST_BACKUP_OFFSITE,
    HOST_RESTIC_PASSWORD_FILE,
)
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends

router = APIRouter(tags=["backups"])

SERVICE_META = {"label": "Backups", "health_check": None}


def _restic(repo_path: str, args: list, text: bool = True, timeout: int = 60) -> subprocess.CompletedProcess:
    """Both repos are mounted read-only into this container - deliberately,
    there's no legitimate reason Control Panel needs write access to a
    backup repo. restic still tries to take a lock file for most commands,
    including read-only ones, which fails against a read-only mount and
    retries for a full minute before giving up (confirmed live: every call
    here failed with "read-only file system" on the lock, not an actual
    repo problem). --no-lock is correct for every use in this file - none
    of them write anything - so this fixes it without loosening the mount.
    text=False for `dump`: it streams a file's raw bytes to stdout, and
    forcing UTF-8 decoding on that (the default here otherwise) throws
    UnicodeDecodeError on the first binary file it happens to hit -
    confirmed live against a real MediaCover image."""
    env = dict(os.environ)
    env["RESTIC_REPOSITORY"] = repo_path
    env["RESTIC_PASSWORD_FILE"] = HOST_RESTIC_PASSWORD_FILE
    return subprocess.run(["restic", "--no-lock", *args], env=env, capture_output=True, text=text, timeout=timeout)


@router.get("/api/backup-verify")
def backup_verify(_=Depends(current_user_or_service)):
    """Latest snapshot age for both the local and off-site restic repos -
    the check that would have caught the off-site leg silently not existing
    before a real audit found it the hard way (a real overnight tar-backup
    failure, discovered only by chance)."""
    repos = {"local": HOST_BACKUP_LOCAL, "offsite": HOST_BACKUP_OFFSITE}
    out = {}
    for name, path in repos.items():
        if not os.path.isdir(path):
            out[name] = {"status": "missing", "path": path}
            continue
        try:
            r = _restic(path, ["snapshots", "--json", "--latest", "1"])
            if r.returncode != 0:
                out[name] = {"status": "error", "detail": r.stderr.strip()[:300]}
                continue
            snaps = json.loads(r.stdout or "[]")
            if not snaps:
                out[name] = {"status": "empty", "path": path}
                continue
            out[name] = {"status": "ok", "time": snaps[0].get("time"), "id": snaps[0].get("short_id")}
        except Exception as e:
            out[name] = {"status": "error", "detail": str(e)}
    problems = [n for n, v in out.items() if v.get("status") != "ok"]
    msg = "Both repos have a recent snapshot." if not problems else f"Problem with: {', '.join(problems)}"
    return ok(msg, repos=out)


@router.post("/api/backup-restore-test")
def backup_restore_test(_=Depends(current_user_or_service)):
    """Pulls one small file out of the latest local snapshot into a scratch
    path inside the container and confirms it's actually readable - a
    backup can complete successfully many times without a restore ever
    being confirmed to actually work, until this checks it directly."""
    if not os.path.isdir(HOST_BACKUP_LOCAL):
        fail(f"{HOST_BACKUP_LOCAL} not present.")
    try:
        r = _restic(HOST_BACKUP_LOCAL, ["ls", "latest", "--json"])
        if r.returncode != 0:
            fail(f"restic ls failed: {r.stderr.strip()[:300]}")
        candidate = None
        for line in r.stdout.splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("type") == "file" and 0 < entry.get("size", 0) < 1_000_000:
                candidate = entry.get("path")
                break
        if not candidate:
            fail("No small file found in the latest snapshot to test-restore.")
        dump = _restic(HOST_BACKUP_LOCAL, ["dump", "latest", candidate], text=False)
        if dump.returncode != 0:
            fail(f"restic dump failed for {candidate}: {dump.stderr.decode(errors='replace').strip()[:300]}")
        return ok(f"Restore test passed: '{candidate}' ({len(dump.stdout)} bytes) dumped and read successfully.")
    except subprocess.TimeoutExpired:
        fail("restic operation timed out.")


@router.get("/api/backup-status")
def backup_status(_=Depends(current_user_or_service)):
    """Full snapshot history (not just the latest, see backup_verify()
    above) for both restic repos - count and oldest/newest timestamps, to
    catch a repo that's accumulating snapshots but silently stopped
    pruning, or one that only ever had a single snapshot ever taken."""
    repos = {"local": HOST_BACKUP_LOCAL, "offsite": HOST_BACKUP_OFFSITE}
    out = {}
    for name, path in repos.items():
        if not os.path.isdir(path):
            out[name] = {"status": "missing", "path": path}
            continue
        try:
            r = _restic(path, ["snapshots", "--json"])
            if r.returncode != 0:
                out[name] = {"status": "error", "detail": r.stderr.strip()[:300]}
                continue
            snaps = json.loads(r.stdout or "[]")
            if not snaps:
                out[name] = {"status": "empty", "count": 0}
                continue
            times = sorted(s["time"] for s in snaps)
            out[name] = {"status": "ok", "count": len(snaps), "oldest": times[0], "newest": times[-1]}
        except Exception as e:
            out[name] = {"status": "error", "detail": str(e)[:300]}
    return ok("Backup repo snapshot history.", repos=out)


@router.post("/api/backup-integrity-check")
def backup_integrity_check(_=Depends(current_user_or_service)):
    """On-demand `restic check` (10% data subset, same sampling
    backup-config.sh's own monthly automatic check uses) against both
    repos - for verifying right now rather than waiting for the 1st of
    the month, e.g. right after a repo's been touched by hand."""
    repos = {"local": HOST_BACKUP_LOCAL, "offsite": HOST_BACKUP_OFFSITE}
    out = {}
    for name, path in repos.items():
        if not os.path.isdir(path):
            out[name] = {"status": "missing", "path": path}
            continue
        r = _restic(path, ["check", "--read-data-subset=10%"], timeout=600)
        out[name] = {"status": "ok" if r.returncode == 0 else "error",
                      "detail": None if r.returncode == 0 else (r.stderr or r.stdout).strip()[:500]}
    problems = [n for n, v in out.items() if v["status"] != "ok"]
    msg = "Both repos passed integrity check." if not problems else f"Problem with: {', '.join(problems)}"
    return ok(msg, repos=out)
