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

Radarr and Sonarr ARE configured here (changed 2026-08-12)
---------------------------------------------------------
GAPS-2 stores exactly one Radarr connection and one Sonarr connection. That
used to be a blocker: with the anime libraries in the routing table there
were four candidate instances, and configuring one of them would have given
GAPS-2's own web UI an Add button that files anime titles into the general
Radarr's root folder under the general quality profile - a silent mis-file
with no hint in the UI. So both were left unset.

The anime libraries were dropped from the routing table, leaving Movies ->
radarr and Shows -> sonarr, which is exactly one Radarr and one Sonarr. The
ambiguity is gone, so both are now provisioned with the same root folder and
quality profile the control panel's own push uses. GAPS-2's Add button and
`stack-gaps2-push` land a title in the same place.

The control panel push route stays the primary path anyway (it names the
instance in its response and rejects an uncovered library) - see
control-panel/services/gaps2/libraries.py.

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

# The two Arr instances GAPS-2 itself gets wired to, one per media type.
#
# `url` is the docker-network address, because GAPS-2 is the thing that has to
# reach it - localhost:7878 works from this script's host but resolves to the
# gaps2 container itself from inside the network.
#
# `root_folder` / `quality_profile` deliberately repeat the defaults in
# control-panel/core/arr_client.py (radarr_root_folder_and_profile and its
# Sonarr twin). Same destination whether a title is added from GAPS-2's own UI
# or via /api/gaps2/push; each falls back to the instance's first entry if the
# named one is absent, rather than leaving the field blank.
ARR_TARGETS = (
    {
        "service": "radarr",
        "label": "Radarr",
        "url": "http://radarr:7878",
        "env_key": "RADARR_API_KEY",
        "root_folder": "/data/movies",
        "quality_profile": "Unlimited",
        # auto_route_by_decade would send a title to a root folder whose path
        # contains its decade. This stack has one flat root folder per
        # instance, so it must stay off or adds would fall back unpredictably.
        "extra": {"minimum_availability": "released", "auto_route_by_decade": False},
    },
    {
        "service": "sonarr",
        "label": "Sonarr",
        "url": "http://sonarr:8989",
        "env_key": "SONARR_API_KEY",
        "root_folder": "/data/shows",
        "quality_profile": "Any",
        "extra": {"season_folder": True},
    },
)


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
    print("  plex: active server persisted")
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
    print("  tvdb: key saved and verified against TheTVDB")


def provision_arr(target: dict, env: dict, dry_run: bool) -> None:
    """Wire one Arr instance into GAPS-2, in two saves.

    The root-folder and quality-profile lookups run through GAPS-2's own
    /root-folders and /profiles endpoints, which read the stored config. So
    the credentials have to be saved before they can be resolved, and the
    resolved values saved after. Going through GAPS-2 rather than querying
    Radarr/Sonarr directly from here also proves GAPS-2 can reach the
    instance over the docker network, which is the connection that matters.
    """
    service, label = target["service"], target["label"]
    api_key = require(env, target["env_key"])

    status, body = request("GET", f"/api/{service}/config")
    if (body or {}).get("enabled"):
        print(f"  {service}: already configured ({(body or {}).get('url')}) - overwriting")
    if dry_run:
        print(f"  {service}: would connect to {target['url']} and set root folder + quality profile")
        return

    # test takes the credentials in the body, so a bad key fails here rather
    # than at the first Add from GAPS-2's UI.
    status, body = request("POST", f"/api/{service}/test", {"url": target["url"], "api_key": api_key})
    if status != 200:
        raise SystemExit(f"  {service}: {label} connection failed ({status}): {(body or {}).get('error') or body}")
    print(f"  {service}: {(body or {}).get('message')}")

    base_config = {"url": target["url"], "api_key": api_key, "monitored": True, "search_on_add": True, **target["extra"]}
    status, body = request("POST", f"/api/{service}/config", base_config)
    if status != 200:
        raise SystemExit(f"  {service}: saving credentials failed ({status}): {body}")

    status, folders = request("GET", f"/api/{service}/root-folders")
    if status != 200 or not folders:
        raise SystemExit(f"  {service}: {label} reports no root folders ({status}): {folders}")
    paths = [f.get("path") for f in folders]
    root_folder_path = target["root_folder"] if target["root_folder"] in paths else paths[0]

    status, profiles = request("GET", f"/api/{service}/profiles")
    if status != 200 or not profiles:
        raise SystemExit(f"  {service}: {label} reports no quality profiles ({status}): {profiles}")
    quality_profile = next((p for p in profiles if p.get("name") == target["quality_profile"]), profiles[0])

    status, body = request("POST", f"/api/{service}/config", {
        **base_config,
        "root_folder_path": root_folder_path,
        "quality_profile_id": quality_profile["id"],
    })
    if status != 200 or not (body or {}).get("enabled"):
        raise SystemExit(f"  {service}: saving root folder/profile failed ({status}): {body}")
    print(f"  {service}: root folder {root_folder_path}, quality profile '{quality_profile['name']}' (id {quality_profile['id']})")


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
        print("           Fix control-panel/services/gaps2/libraries.py before scanning.")
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
    for target in ARR_TARGETS:
        provision_arr(target, env, args.dry_run)
    check_libraries(found)

    print("Done." if not args.dry_run else "Dry run complete, nothing written.")


if __name__ == "__main__":
    main()
