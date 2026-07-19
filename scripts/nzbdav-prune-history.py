#!/usr/bin/env python3
"""Deletes every "Failed" entry from nzbdav's SABnzbd-compatible history.

nzbdav rejects re-grabbing an NZB whose release name matches a prior Failed
history row with "Duplicate nzb: the download folder for this nzb already
exists" - even when nothing exists on disk for it (confirmed live 2026-07-19:
9 Radarr titles stuck in a permanent retry-fails-with-duplicate loop, no
completed-symlinks folder present for any of them). A Failed row has no
surviving output (storage is null/never wrote real content), so it serves no
purpose once logged except this blocking side effect - safe to delete
unconditionally, regardless of age.

Run every few hours by systemd/stack-nzbdav-prune-history.{service,timer}.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

STACK_DIR = Path(__file__).resolve().parent.parent
NZBDAV_URL = "http://localhost:3001"


def env_get(key):
    env_path = STACK_DIR / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


NZBDAV_API_KEY = env_get("NZBDAV_API_KEY")

# nzbdav's history/delete endpoint takes exactly one GUID per call - no
# comma-separated batch form despite otherwise mirroring SABnzbd's API
# (confirmed live 2026-07-19: passing two ids errored "Guid should contain
# 32 digits..."). History can run in the tens of thousands of entries on
# this stack, so deletes are fanned out across threads rather than done
# serially - these are same-host HTTP calls, not a remote/rate-limited API.
WORKERS = 20


def api_get(params, timeout=30):
    url = f"{NZBDAV_URL}/api?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def delete_one(slot):
    nzo_id = slot["nzo_id"]
    try:
        result = api_get({
            "mode": "history",
            "name": "delete",
            "value": nzo_id,
            "apikey": NZBDAV_API_KEY,
            "output": "json",
        })
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return False, f"failed to delete {nzo_id} ({slot.get('name')}): {e}"
    if result.get("status"):
        return True, None
    return False, f"delete rejected for {nzo_id} ({slot.get('name')}): {result.get('error')}"


def main():
    if not NZBDAV_API_KEY or NZBDAV_API_KEY == "changeme":
        print("NZBDAV_API_KEY not configured in .env", file=sys.stderr)
        return 1

    # Full history on this stack runs 35k+ entries - serializing that on
    # nzbdav's side is slow, confirmed live to exceed a 30s timeout.
    history = api_get({
        "mode": "history",
        "limit": 0,
        "apikey": NZBDAV_API_KEY,
        "output": "json",
    }, timeout=180)
    slots = history.get("history", {}).get("slots", [])
    failed = [s for s in slots if s.get("status") == "Failed"]

    deleted = 0
    errors = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(delete_one, slot) for slot in failed]
        for future in as_completed(futures):
            ok, message = future.result()
            if ok:
                deleted += 1
            else:
                print(message, file=sys.stderr)
                errors += 1

    print(f"pruned {deleted}/{len(failed)} failed history entries ({errors} errors)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
