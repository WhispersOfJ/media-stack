#!/usr/bin/env python3
"""Re-assert custom format scores that Recyclarr resets on its managed profiles.

Recyclarr treats any quality profile listed in its own recyclarr.yml
(assign_scores_to / template targets) as fully authoritative: every sync, it
resets the score of any custom format it doesn't itself track back to 0 on
those specific profiles. Manually-added custom formats (like ad-hoc regex
blocklists) survive fine on every OTHER profile, but get silently zeroed on
the one Recyclarr actively manages - which is usually the profile actually
in use.

This script re-applies the intended score after each Recyclarr sync. Run on
a schedule shortly after Recyclarr's own daily sync (see crontab).

API keys are read from environment variables (RADARR_API_KEY, SONARR_API_KEY)
rather than hardcoded, so this script can live in the repo without leaking
secrets. Set them in the crontab entry or export before running.
"""
import json
import os
import sys
import urllib.request

# (api_base, api_key_env_var, custom_format_id, managed_profile_name, score)
TARGETS = [
    ("http://127.0.0.1:7878/api/v3", "RADARR_API_KEY", 35, "HD Bluray + WEB", -10000),
    ("http://127.0.0.1:8989/api/v3", "SONARR_API_KEY", 33, "WEB-1080p", -10000),
]


def api_get(base, key, path):
    req = urllib.request.Request(f"{base}{path}", headers={"X-Api-Key": key})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def api_put(base, key, path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{base}{path}", data=data, method="PUT",
                                  headers={"X-Api-Key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def main():
    for base, key_env, cf_id, profile_name, score in TARGETS:
        key = os.environ.get(key_env)
        if not key:
            print(f"{profile_name}: skipped, {key_env} not set in environment", file=sys.stderr)
            continue
        profiles = api_get(base, key, "/qualityprofile")
        profile = next(p for p in profiles if p["name"] == profile_name)
        fi = next(f for f in profile["formatItems"] if f["format"] == cf_id)
        if fi["score"] == score:
            print(f"{profile_name}: already {score}, nothing to do")
            continue
        previous = fi["score"]
        fi["score"] = score
        api_put(base, key, f"/qualityprofile/{profile['id']}", profile)
        print(f"{profile_name}: reset from {previous} back to {score}")


if __name__ == "__main__":
    main()
