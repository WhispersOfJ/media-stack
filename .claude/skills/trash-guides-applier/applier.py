#!/usr/bin/env python3
"""Apply/diff TRaSH-Guides-style quality profiles & custom formats to Radarr/Sonarr.

Usage:
    applier.py apply <app> --profiles FILE
    applier.py diff <app> --profiles FILE
    applier.py list-current <app>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

APPS = {
    "radarr": {"port": 7878, "api": "v3"},
    "sonarr": {"port": 8989, "api": "v3"},
}


class AppConfig:
    def __init__(self, name: str):
        if name not in APPS:
            raise ValueError(f"unknown app '{name}', expected one of {list(APPS)}")
        meta = APPS[name]
        env_prefix = name.upper()
        self.base_url = os.environ.get(
            f"{env_prefix}_URL", f"http://localhost:{meta['port']}"
        ).rstrip("/")
        self.api_key = os.environ.get(f"{env_prefix}_API_KEY")
        self.api_version = meta["api"]
        if not self.api_key:
            raise RuntimeError(f"{env_prefix}_API_KEY is not set in the environment")

    def request(self, method: str, path: str, body: dict | None = None) -> object:
        url = f"{self.base_url}/api/{self.api_version}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("X-Api-Key", self.api_key)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {url} -> HTTP {e.code}: {e.read().decode(errors='replace')}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"{method} {url} -> unreachable: {e.reason}") from e


def load_profiles(path: Path) -> dict:
    return json.loads(path.read_text())


def cmd_list_current(app_name: str) -> None:
    app = AppConfig(app_name)
    profiles = app.request("GET", "/qualityprofile") or []
    formats = app.request("GET", "/customformat") or []
    print(f"quality profiles ({len(profiles)}):")
    for p in profiles:
        print(f"  - {p.get('name')}")
    print(f"custom formats ({len(formats)}):")
    for f in formats:
        print(f"  - {f.get('name')} (score default {f.get('score', 'n/a')})")


def _diff(app: AppConfig, local: dict) -> tuple[list, list, list, list]:
    live_formats = {f["name"]: f for f in (app.request("GET", "/customformat") or [])}
    live_profiles = {p["name"]: p for p in (app.request("GET", "/qualityprofile") or [])}

    new_formats = [f for f in local.get("custom_formats", []) if f["name"] not in live_formats]
    changed_formats = [
        f for f in local.get("custom_formats", [])
        if f["name"] in live_formats and live_formats[f["name"]].get("score") != f.get("score")
    ]
    new_profiles = [p for p in local.get("quality_profiles", []) if p["name"] not in live_profiles]
    changed_profiles = [
        p for p in local.get("quality_profiles", [])
        if p["name"] in live_profiles
    ]
    return new_formats, changed_formats, new_profiles, changed_profiles


def cmd_diff(app_name: str, profiles_file: Path) -> None:
    app = AppConfig(app_name)
    local = load_profiles(profiles_file)
    new_formats, changed_formats, new_profiles, _ = _diff(app, local)
    print(f"custom formats: {len(new_formats)} new, {len(changed_formats)} score-changed")
    for f in new_formats:
        print(f"  + {f['name']}")
    for f in changed_formats:
        print(f"  ~ {f['name']} (score change)")
    print(f"quality profiles: {len(new_profiles)} new")
    for p in new_profiles:
        print(f"  + {p['name']}")


def cmd_apply(app_name: str, profiles_file: Path) -> None:
    app = AppConfig(app_name)
    local = load_profiles(profiles_file)

    live_formats = {f["name"]: f for f in (app.request("GET", "/customformat") or [])}
    for cf in local.get("custom_formats", []):
        payload = {
            "name": cf["name"],
            "specifications": cf.get("specifications", []),
        }
        if cf["name"] in live_formats:
            payload["id"] = live_formats[cf["name"]]["id"]
            app.request("PUT", f"/customformat/{payload['id']}", payload)
            print(f"updated custom format: {cf['name']}")
        else:
            app.request("POST", "/customformat", payload)
            print(f"created custom format: {cf['name']}")

    live_profiles = {p["name"]: p for p in (app.request("GET", "/qualityprofile") or [])}
    for qp in local.get("quality_profiles", []):
        if qp["name"] in live_profiles:
            print(f"quality profile already exists, skipping structural update: {qp['name']} "
                  f"(edit items/cutoff manually in the Arr UI — profile item IDs are app-assigned "
                  f"and not safe to blind-overwrite)")
            continue
        # Minimal creation payload; Radarr/Sonarr assign real qualityId/item structure
        # server-side once items reference the app's actual quality definitions.
        payload = {
            "name": qp["name"],
            "upgradeAllowed": qp.get("upgrade_allowed", True),
            "items": [],
            "minFormatScore": qp.get("min_format_score", 0),
            "cutoffFormatScore": qp.get("cutoff_format_score", 0),
        }
        try:
            app.request("POST", "/qualityprofile", payload)
            print(f"created quality profile skeleton: {qp['name']} "
                  f"(finish item ordering in the Arr UI — TRaSH-Guides item ordering isn't "
                  f"derivable from this JSON alone)")
        except RuntimeError as e:
            print(f"could not create {qp['name']}: {e}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    p_apply = sub.add_parser("apply")
    p_apply.add_argument("app")
    p_apply.add_argument("--profiles", type=Path, required=True)

    p_diff = sub.add_parser("diff")
    p_diff.add_argument("app")
    p_diff.add_argument("--profiles", type=Path, required=True)

    p_list = sub.add_parser("list-current")
    p_list.add_argument("app")

    args = parser.parse_args()

    try:
        if args.action == "apply":
            cmd_apply(args.app, args.profiles)
        elif args.action == "diff":
            cmd_diff(args.app, args.profiles)
        elif args.action == "list-current":
            cmd_list_current(args.app)
    except (RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
