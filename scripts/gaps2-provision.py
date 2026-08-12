#!/usr/bin/env python3
"""Provision GAPS-2 from a bare volume: Plex connection, TMDB key, TheTVDB
key. Phase 5 of PLANS.md.

PLANS.md 5.2 said the secrets are "entered via GAPS-2's own Settings UI
post-boot, not pre-seeded", with Plex specifically requiring an "OAuth login
flow (interactive, one-time)". Reading upstream source shows that is
avoidable: POST /api/plex/connect-manual takes a plain {serverUrl, token} and
never touches OAuth (blueprints/plex.py, services/plex_service.py:
connect_manual), and every other credential has a plain POST behind it. GAPS-2
also ships no auth of any kind, so none of these calls need a session.

So the whole service provisions headlessly from the PLEX_URL / PLEX_TOKEN /
TMDB_KEY / TVDB_KEY already in .env, with no browser step at all.

Radarr and Sonarr are deliberately NOT configured here
-----------------------------------------------------
GAPS-2 stores exactly one Radarr connection and one Sonarr connection. This
stack has four Arr instances, split general/anime. If a single Radarr were
configured, GAPS-2's own web UI would grow an Add button that pushes every
title - anime included - into that one instance, under its root folder and
quality profile. That is a silent mis-file, and the UI gives no hint it
happened.

Leaving them unset makes that mis-route structurally impossible rather than
merely discouraged, and keeps two more API keys out of config.enc. Pushes go
through the control panel instead (`stack-gaps2-push` ->
/api/gaps2/push), which picks the instance from the library the gap was found
in - see control-panel/services/gaps2/libraries.py.

Safe to re-run: every step is a plain overwrite of the same config keys, and
the script reports what each one already looked like beforehand.

Usage:  python3 scripts/gaps2-provision.py [--dry-run]
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# The library routing table lives with the control-panel service that also
# serves it, so there is exactly one definition - see that module's docstring.
sys.path.insert(0, str(REPO_ROOT / "control-panel"))
from services.gaps2.libraries import LIBRARY_NAMES  # noqa: E402

BASE = "http://localhost:8704"
TIMEOUT = 60


def load_env() -> dict:
    env = {}
    for line in (REPO_ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def request(method: str, path: str, body: dict | None = None):
    """Returns (http_status, parsed_json_or_none)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except ValueError:
            return e.code, None
    except (urllib.error.URLError, TimeoutError) as e:
        raise SystemExit(f"GAPS-2 unreachable at {BASE}: {e}")


def require(env: dict, key: str) -> str:
    value = env.get(key, "")
    if not value or value == "changeme":
        raise SystemExit(f"{key} is not set in .env - cannot provision.")
    return value


def provision_plex(env: dict, dry_run: bool) -> list[str]:
    url, token = require(env, "PLEX_URL"), require(env, "PLEX_TOKEN")

    status, body = request("GET", "/api/plex/active-server")
    if status == 200 and (body or {}).get("server"):
        print(f"  plex: already connected to '{body['server']}'")
    if dry_run:
        print(f"  plex: would connect to {url} and persist the active server")
        return []

    # connect-manual validates the credentials and returns the library list,
    # but does not persist anything - save-data is what writes config.enc.
    status, body = request("POST", "/api/plex/connect-manual", {"serverUrl": url, "token": token})
    if status != 200 or not (body or {}).get("connected"):
        raise SystemExit(f"  plex: connect failed ({status}): {(body or {}).get('error')}")
    server_name = body["serverName"]
    libraries = body.get("libraries") or []
    print(f"  plex: connected to '{server_name}', {len(libraries)} libraries")

    status, body = request("POST", "/api/plex/save-data", {
        "server": server_name,
        "token": token,
        "libraries": libraries,
        "serverUrl": url,
    })
    if status != 200 or (body or {}).get("result") != "Success":
        raise SystemExit(f"  plex: save-data failed ({status}): {body}")
    print(f"  plex: active server persisted")
    return [lib.get("title") for lib in libraries]


def provision_tmdb(env: dict, dry_run: bool) -> None:
    key = require(env, "TMDB_KEY")
    status, body = request("GET", "/api/tmdb/status")
    if (body or {}).get("hasKey"):
        print("  tmdb: key already present (overwriting)")
    if dry_run:
        print("  tmdb: would save TMDB_KEY")
        return
    # save-key validates against TMDB before storing, so a bad key fails here
    # rather than silently at first scan.
    status, body = request("POST", "/api/tmdb/save-key", {"key": key})
    if status != 200:
        raise SystemExit(f"  tmdb: save failed ({status}): {(body or {}).get('message')}")
    print(f"  tmdb: {(body or {}).get('message')}")


def provision_tvdb(env: dict, dry_run: bool) -> None:
    key = require(env, "TVDB_KEY")
    if dry_run:
        print("  tvdb: would save TVDB_KEY")
        return
    status, body = request("POST", "/api/tvdb/config", {"api_key": key, "pin": ""})
    if status != 200:
        raise SystemExit(f"  tvdb: save failed ({status}): {body}")
    # A saved key is not a working key - TheTVDB v4 issues a bearer token per
    # login, and a rejected key only surfaces at that point.
    status, body = request("POST", "/api/tvdb/test", {"api_key": key, "pin": ""})
    if status != 200:
        raise SystemExit(f"  tvdb: key rejected by TheTVDB ({status}): {(body or {}).get('error') or body}")
    print(f"  tvdb: key saved and verified against TheTVDB")


def check_libraries(found: list[str]) -> None:
    """Warn if the routing table names a library this Plex server lacks.

    A typo or a renamed Plex library would otherwise only surface as an empty
    scan much later, which reads like "nothing is missing" rather than "we
    never looked at anything".
    """
    if not found:
        return
    missing = [name for name in LIBRARY_NAMES if name not in found]
    if missing:
        print(f"  WARNING: routing table names libraries this Plex server does not have: {', '.join(missing)}")
        print(f"           Plex reports: {', '.join(sorted(found))}")
        print(f"           Fix control-panel/services/gaps2/libraries.py before scanning.")
    else:
        print(f"  libraries: all {len(LIBRARY_NAMES)} routed libraries present on Plex")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    args = parser.parse_args()

    env = load_env()

    status, about = request("GET", "/api/about")
    if status != 200:
        raise SystemExit(f"GAPS-2 is not answering /api/about ({status}) - is the container up?")
    print(f"GAPS-2 {(about or {}).get('version')} at {BASE}{' (dry run)' if args.dry_run else ''}")

    found = provision_plex(env, args.dry_run)
    provision_tmdb(env, args.dry_run)
    provision_tvdb(env, args.dry_run)
    check_libraries(found)

    print("  radarr/sonarr: deliberately not configured (see this script's docstring)")
    print("Done." if not args.dry_run else "Dry run complete, nothing written.")


if __name__ == "__main__":
    main()
