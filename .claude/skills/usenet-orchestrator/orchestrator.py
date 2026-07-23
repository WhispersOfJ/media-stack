#!/usr/bin/env python3
"""Inspect and manage download-client queues (altmount, or any other
SABnzbd/qBittorrent-API-compatible client added to CLIENTS below) for the
media-stack.

Usage:
    orchestrator.py queue <client>
    orchestrator.py failed <client>
    orchestrator.py retry <client> <item_id>
    orchestrator.py clear-failed <client>
    orchestrator.py reachability
    orchestrator.py diagnose-stuck-file [--since 6h] [--media-root /data]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# AltMount is the only download client this stack runs as of 2026-07-23,
# replacing NzbDAV entirely (unmerged connection-leak bug, see CLAUDE.md's
# History) - other SABnzbd/qBittorrent-API clients can still be added here
# if a future stack change brings one back. "path" is the base path each
# client's SABnzbd-compatible API is actually mounted under - a real
# vanilla SABnzbd install expects /api directly; AltMount's Fiber router
# mounts it under /sabnzbd instead (app.Use("/sabnzbd", ...), prefix-
# matching, confirmed via its own source). Host port is AltMount's
# published one (8081, mapped from container 8080) - override via
# ALTMOUNT_URL for anything reached differently.
CLIENTS = {
    "altmount": {"port": 8081, "path": "/sabnzbd", "kind": "sabnzbd"},
}

# NzbDAV/nzbdav-rclone's stuck-file diagnostic (matched a repeating
# ".ids/<uuid> 404 Not Found" log pattern specific to that FUSE mount) had
# no confirmed AltMount equivalent as of the 2026-07-23 cutover - AltMount
# is a single container with its own internal mount/logging shape, not
# verified to log missing-article failures the same way. Removed rather
# than guessed; see cmd_diagnose_stuck_file below.


class Client:
    def __init__(self, name: str):
        if name not in CLIENTS:
            raise ValueError(f"unknown client '{name}', expected one of {list(CLIENTS)}")
        self.name = name
        meta = CLIENTS[name]
        env_prefix = name.upper()
        self.base_url = os.environ.get(
            f"{env_prefix}_URL", f"http://localhost:{meta['port']}"
        ).rstrip("/")
        self.api_key = os.environ.get(f"{env_prefix}_API_KEY", "")
        self.kind = meta["kind"]
        self.path = meta.get("path", "/api")

    def _get(self, path: str, params: dict | None = None) -> object:
        params = dict(params or {})
        if self.api_key:
            params["apikey"] = self.api_key
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"GET {url} -> HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"GET {url} -> unreachable: {e.reason}") from e

    def queue(self) -> list[dict]:
        if self.kind == "sabnzbd":
            data = self._get(self.path, {"mode": "queue", "output": "json"})
            return (data or {}).get("queue", {}).get("slots", [])
        data = self._get("/api/v1/queue")
        return data if isinstance(data, list) else (data or {}).get("items", [])

    def failed(self) -> list[dict]:
        if self.kind == "sabnzbd":
            data = self._get(self.path, {"mode": "history", "output": "json", "failed_only": 1})
            return (data or {}).get("history", {}).get("slots", [])
        items = self.queue()
        return [i for i in items if str(i.get("status", "")).lower() in ("failed", "error")]

    def retry(self, item_id: str) -> None:
        if self.kind == "sabnzbd":
            self._get(self.path, {"mode": "retry", "value": item_id, "output": "json"})
        else:
            self._get(f"/api/v1/queue/{item_id}/retry")

    def delete_failed_items(self, failed_items: list[dict]) -> int:
        count = 0
        for item in failed_items:
            item_id = item.get("nzo_id") or item.get("id")
            if not item_id:
                continue
            if self.kind == "sabnzbd":
                self._get(self.path, {"mode": "queue", "name": "delete", "value": item_id, "output": "json"})
            else:
                self._get(f"/api/v1/queue/{item_id}/delete")
            count += 1
        return count


def cmd_queue(client_name: str) -> None:
    client = Client(client_name)
    items = client.queue()
    if not items:
        print(f"{client_name}: queue is empty")
        return
    for item in items:
        name = item.get("filename") or item.get("name") or "?"
        status = item.get("status", "?")
        progress = item.get("percentage") or item.get("progress", "?")
        print(f"  {status:>10}  {progress!s:>6}  {name}")


def cmd_failed(client_name: str) -> None:
    client = Client(client_name)
    items = client.failed()
    if not items:
        print(f"{client_name}: no failed items")
        return
    for item in items:
        name = item.get("filename") or item.get("name") or "?"
        item_id = item.get("nzo_id") or item.get("id") or "?"
        reason = item.get("fail_message") or item.get("error") or "unknown"
        print(f"  id={item_id}  {name}  reason={reason}")


def cmd_retry(client_name: str, item_id: str) -> None:
    client = Client(client_name)
    client.retry(item_id)
    print(f"{client_name}: retried {item_id}")


def cmd_clear_failed(client_name: str) -> None:
    client = Client(client_name)
    failed_items = client.failed()
    if not failed_items:
        print(f"{client_name}: no failed items to clear")
        return
    print(f"About to remove {len(failed_items)} failed item(s) from {client_name}:")
    for item in failed_items:
        print(f"  - {item.get('filename') or item.get('name')}")
    confirm = input("Type 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        print("Aborted.")
        return
    count = client.delete_failed_items(failed_items)
    print(f"{client_name}: removed {count} failed item(s)")


def cmd_reachability() -> None:
    for name in CLIENTS:
        client = Client(name)
        try:
            client.queue()
            print(f"{name}: UP ({client.base_url})")
        except RuntimeError as e:
            print(f"{name}: DOWN ({e})")


def cmd_diagnose_stuck_file(since: str, media_root: str) -> None:
    """Read-only. Was built around NzbDAV/nzbdav-rclone's specific
    ".ids/<uuid> 404 Not Found" log pattern (see module comment) - NzbDAV
    was removed entirely 2026-07-23 and this diagnostic has no confirmed
    AltMount equivalent yet, so it refuses to run rather than silently
    search logs that likely don't match this pattern at all."""
    print("diagnose-stuck-file has no confirmed AltMount equivalent yet - it was built")
    print("around NzbDAV/nzbdav-rclone's specific log format, and NzbDAV was removed")
    print("entirely 2026-07-23 (see CLAUDE.md's History). Check AltMount's own logs")
    print("(docker logs altmount) directly for now, or port this diagnostic once")
    print("AltMount's actual missing-article/failed-mount log format is confirmed.")
    _ = (since, media_root)  # unused until a real AltMount log pattern is confirmed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    p_queue = sub.add_parser("queue")
    p_queue.add_argument("client")

    p_failed = sub.add_parser("failed")
    p_failed.add_argument("client")

    p_retry = sub.add_parser("retry")
    p_retry.add_argument("client")
    p_retry.add_argument("item_id")

    p_clear = sub.add_parser("clear-failed")
    p_clear.add_argument("client")

    sub.add_parser("reachability")

    p_diagnose = sub.add_parser("diagnose-stuck-file")
    p_diagnose.add_argument("--since", default="6h", help="docker logs --since window (default 6h)")
    p_diagnose.add_argument("--media-root", default="/data", help="host media root to search for the symlink (default /data)")

    args = parser.parse_args()

    try:
        if args.action == "queue":
            cmd_queue(args.client)
        elif args.action == "failed":
            cmd_failed(args.client)
        elif args.action == "retry":
            cmd_retry(args.client, args.item_id)
        elif args.action == "clear-failed":
            cmd_clear_failed(args.client)
        elif args.action == "reachability":
            cmd_reachability()
        elif args.action == "diagnose-stuck-file":
            cmd_diagnose_stuck_file(args.since, args.media_root)
    except (RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
