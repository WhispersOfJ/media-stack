#!/usr/bin/env python3
"""Deletes every "Failed" entry from AltMount's SABnzbd-compatible history.

Same rationale this stack's now-removed NzbDAV prune script had: a Failed
history row has no surviving output but can still block re-grabbing a
matching release name, so there's no reason to keep one once logged - safe
to delete unconditionally, regardless of age.

Run every few hours by systemd/stack-altmount-prune-history.{service,timer}.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

STACK_DIR = Path(__file__).resolve().parent.parent
# AltMount's SABnzbd-compatible API lives under /sabnzbd (Fiber's
# prefix-matching app.Use, not a literal /api/sabnzbd path).
ALTMOUNT_URL = "http://localhost:8081/sabnzbd"


def env_get(key):
    env_path = STACK_DIR / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


ALTMOUNT_API_KEY = env_get("ALTMOUNT_API_KEY")

# Deletes fan out across threads rather than running serially - these are
# same-host HTTP calls, not a remote/rate-limited API. History can run in
# the tens of thousands of entries on this stack.
WORKERS = 20


def api_get(params, timeout=30):
    url = f"{ALTMOUNT_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def delete_one(slot):
    nzo_id = slot["nzo_id"]
    try:
        result = api_get({
            "mode": "history",
            "name": "delete",
            "value": nzo_id,
            "apikey": ALTMOUNT_API_KEY,
            "output": "json",
        })
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return False, f"failed to delete {nzo_id} ({slot.get('name')}): {e}"
    if result.get("status"):
        return True, None
    return False, f"delete rejected for {nzo_id} ({slot.get('name')}): {result.get('error')}"


def main():
    if not ALTMOUNT_API_KEY or ALTMOUNT_API_KEY == "changeme":
        print("ALTMOUNT_API_KEY not configured in .env", file=sys.stderr)
        return 1

    history = api_get({
        "mode": "history",
        "limit": 0,
        "apikey": ALTMOUNT_API_KEY,
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
