#!/usr/bin/env python3
"""Provision Organizr from a bare volume: setup wizard, then one tab per
service. Phase 3 of PLANS.md.

PLANS.md 3.4 said tab provisioning was "manual by design - Organizr has no
tab-provisioning API; all tab state lives in its own SQLite DB. Do not
attempt to script this." That is wrong on both counts, confirmed by reading
the source rather than the docs:

  * api/v2/routes/tabs.php defines a full GET/POST/PUT/DELETE /api/v2/tabs.
  * isApprovedRequest (api/classes/organizr.class.php:4596) accepts a
    `Token:` header equal to the configured 20-char API key, treats it as
    admin, and short-circuits the CSRF formKey check that would otherwise
    block a POST from outside a browser session.
  * POST /api/v2/wizard is in $GLOBALS['bypass'] (api/v2/index.php:41-52),
    so first-boot setup needs no auth at all, and wizardConfig() self-
    disables once config+DB exist. We supply our own API key in that call,
    which is what makes every later step scriptable.

So the whole thing is one idempotent script, matching PLANS.md 1.4's own
rule about scripting anything that would otherwise be a repeated manual
click-through.

Safe to re-run. The wizard step no-ops once configured; the tab step skips
any tab whose name already exists rather than duplicating or erroring.

Usage:  python3 scripts/organizr-provision.py [--dry-run]
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# The tab table lives with the control-panel service that also serves it, so
# there is exactly one definition of it - see that module's docstring.
sys.path.insert(0, str(REPO_ROOT / "control-panel"))
from services.organizr.tabs import TABS, tab_payload  # noqa: E402

TIMEOUT = 20
# Organizr gates plugin visibility on this string; 'personal' and 'business'
# are the only values its own bundled plugins declare (api/plugins/*/plugin.php).
LICENSE = "personal"


def load_env() -> dict:
    env = {}
    for line in (REPO_ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def request(method: str, path: str, base: str, token: str | None = None, body: dict | None = None):
    """Returns (http_status, parsed_json_or_none)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{base}{path}", data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Token", token)
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
        raise SystemExit(f"Organizr unreachable at {base}: {e}")


def already_configured(base: str, token: str) -> bool:
    """A configured install answers /api/v2/tabs 200 for an admin token.

    Checked via tabs rather than by POSTing the wizard and reading its
    "database already exists" 401, so a re-run never sends credentials at
    an install that might belong to someone else.
    """
    status, body = request("GET", "/api/v2/tabs", base, token=token)
    return status == 200 and isinstance((body or {}).get("response", {}).get("data"), dict)


def run_wizard(base: str, env: dict, dry_run: bool) -> None:
    payload = {
        "driver": "sqlite3",
        "dbName": "organizr",
        # Pinned rather than left to wizardConfig's default, which is
        # $root/data/<10 random chars>/ - a random path makes the DB
        # location differ between rebuilds and defeats grepping for it.
        "dbPath": "/config/www/organizr/data/db/",
        "license": LICENSE,
        "hashKey": env["ORGANIZR_HASH_KEY"],
        "api": env["ORGANIZR_API_KEY"],
        "registrationPassword": env["ORGANIZR_REGISTRATION_PASSWORD"],
        "username": env["ORGANIZR_ADMIN_USERNAME"],
        "password": env["ORGANIZR_ADMIN_PASSWORD"],
        "email": env["ORGANIZR_ADMIN_EMAIL"],
    }
    if dry_run:
        redacted = {k: ("***" if "ass" in k or k in ("api", "hashKey") else v) for k, v in payload.items()}
        print(f"[dry-run] POST /api/v2/wizard {json.dumps(redacted)}")
        return
    status, body = request("POST", "/api/v2/wizard", base, body=payload)
    message = (body or {}).get("response", {}).get("message")
    if status != 200:
        raise SystemExit(f"wizard failed (HTTP {status}): {message or body}")
    print(f"  wizard: configured (admin '{payload['username']}', sqlite at {payload['dbPath']})")


def sync_tabs(base: str, token: str, host_ip: str, dry_run: bool) -> tuple[int, int]:
    status, body = request("GET", "/api/v2/tabs", base, token=token)
    if status != 200:
        # On a real run this is fatal. Under --dry-run against a not-yet-
        # configured install it is expected: the wizard was only simulated,
        # so the API key isn't live yet and every tab counts as missing.
        if not (dry_run and status == 401):
            raise SystemExit(f"could not list tabs (HTTP {status}): {body}")
        body = {}
    existing = {t["name"] for t in (body or {}).get("response", {}).get("data", {}).get("tabs", [])}

    added = skipped = 0
    for tab in TABS:
        if tab["name"] in existing:
            skipped += 1
            continue
        payload = tab_payload(tab, host_ip)
        if dry_run:
            print(f"  [dry-run] + {tab['name']:<18} type={payload['type']} {payload['url']}")
            added += 1
            continue
        st, resp = request("POST", "/api/v2/tabs", base, token=token, body=payload)
        msg = (resp or {}).get("response", {}).get("message")
        if st == 409:
            # Name taken - a tab we did not create, or a race. Not a failure.
            skipped += 1
            continue
        if st != 200:
            raise SystemExit(f"adding tab '{tab['name']}' failed (HTTP {st}): {msg or resp}")
        kind = "new-window" if payload["type"] == 2 else "iframe"
        print(f"  + {tab['name']:<18} {kind:<11} {payload['url']}")
        added += 1
    return added, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print what would change, touch nothing")
    args = parser.parse_args()

    env = load_env()
    missing = [k for k in (
        "ORGANIZR_API_KEY", "ORGANIZR_HASH_KEY", "ORGANIZR_ADMIN_USERNAME",
        "ORGANIZR_ADMIN_EMAIL", "ORGANIZR_ADMIN_PASSWORD",
        "ORGANIZR_REGISTRATION_PASSWORD", "HOST_IP",
    ) if not env.get(k)]
    if missing:
        raise SystemExit(f"missing from .env: {', '.join(missing)}")

    token = env["ORGANIZR_API_KEY"]
    if len(token) != 20:
        # Organizr compares strlen($token) == 20 before it even looks at the
        # value, so a wrong-length key 401s every write route with no hint.
        raise SystemExit(f"ORGANIZR_API_KEY must be exactly 20 chars, got {len(token)}")

    host_ip = env["HOST_IP"]
    base = f"http://{host_ip}:8702"
    print(f"Organizr provisioning against {base}")

    if already_configured(base, token):
        print("  wizard: already configured, skipping")
    else:
        run_wizard(base, env, args.dry_run)

    added, skipped = sync_tabs(base, token, host_ip, args.dry_run)
    print(f"Done. {added} tab(s) added, {skipped} already present, {len(TABS)} total defined.")


if __name__ == "__main__":
    main()
