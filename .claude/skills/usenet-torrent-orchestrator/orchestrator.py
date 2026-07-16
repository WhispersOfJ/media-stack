#!/usr/bin/env python3
"""Inspect and manage download-client queues (nzbdav, decypharr) for the media-stack.

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
import collections
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

CLIENTS = {
    "nzbdav": {"port": 8080, "kind": "sabnzbd"},
    "decypharr": {"port": 8282, "kind": "generic"},
}

# nzbdav-rclone's FUSE mount surfaces a permanently unrecoverable Usenet
# file (missing articles, no par2 recovery blocks available) as an
# endlessly repeating "vfs cache ... 404 Not Found" error against the same
# internal .ids/<uuid> path, every ~10-20s, forever - not a transient
# blip. Confirmed live 2026-07-16 diagnosing "The Escapees (1981)": the
# root cause sat in nzbdav's own container logs ("missing articles",
# "Error executing nntp BODY command"), not in nzbdav-rclone's. This
# command only diagnoses and reports - it never deletes anything. Fixing
# a confirmed-broken file means removing that specific *arr app's file
# record, a real destructive action against library state that needs its
# own explicit, per-instance confirmation - not something to fold into an
# automated flag here.
_ID_RE = re.compile(r"\.ids/[0-9a-f]/[0-9a-f]/[0-9a-f]/[0-9a-f]/[0-9a-f]/([0-9a-f-]{36})")


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
            data = self._get("/api", {"mode": "queue", "output": "json"})
            return (data or {}).get("queue", {}).get("slots", [])
        data = self._get("/api/v1/queue")
        return data if isinstance(data, list) else (data or {}).get("items", [])

    def failed(self) -> list[dict]:
        if self.kind == "sabnzbd":
            data = self._get("/api", {"mode": "history", "output": "json", "failed_only": 1})
            return (data or {}).get("history", {}).get("slots", [])
        items = self.queue()
        return [i for i in items if str(i.get("status", "")).lower() in ("failed", "error")]

    def retry(self, item_id: str) -> None:
        if self.kind == "sabnzbd":
            self._get("/api", {"mode": "retry", "value": item_id, "output": "json"})
        else:
            self._get(f"/api/v1/queue/{item_id}/retry")

    def delete_failed_items(self, failed_items: list[dict]) -> int:
        count = 0
        for item in failed_items:
            item_id = item.get("nzo_id") or item.get("id")
            if not item_id:
                continue
            if self.kind == "sabnzbd":
                self._get("/api", {"mode": "queue", "name": "delete", "value": item_id, "output": "json"})
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


def _docker_logs(container: str, since: str) -> str:
    try:
        result = subprocess.run(
            ["docker", "logs", "--since", since, container],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        raise RuntimeError(f"couldn't read logs for {container}: {e}") from e
    return result.stdout + result.stderr


def _resolve_symlink(media_root: str, stuck_id: str) -> str | None:
    try:
        result = subprocess.run(
            ["find", media_root, "-type", "l", "-lname", f"*{stuck_id}*"],
            capture_output=True, text=True, timeout=60,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    hit = result.stdout.strip().splitlines()
    return hit[0] if hit else None


def cmd_diagnose_stuck_file(since: str, media_root: str) -> None:
    """Read-only. Finds the *arr library entry behind a file
    nzbdav-rclone can't stop retrying, and prints what to check - never
    deletes anything itself."""
    rclone_log = _docker_logs("nzbdav-rclone", since)
    counts: dict[str, int] = collections.Counter(m.group(1) for m in _ID_RE.finditer(rclone_log))
    if not counts:
        print(f"No repeating .ids/<uuid> 404 errors found in nzbdav-rclone's logs (last {since}).")
        return

    print(f"Repeating stuck ids in nzbdav-rclone's logs (last {since}):")
    for stuck_id, count in counts.most_common():
        print(f"  {count:>5}x  {stuck_id}")

    top_id, top_count = counts.most_common(1)[0]
    print(f"\nMost frequent: {top_id} ({top_count} errors) - investigating.")

    nzbdav_log = _docker_logs("nzbdav", since)
    nntp_lines = [
        line for line in nzbdav_log.splitlines()
        if "missing articles" in line.lower() or "nntp" in line.lower()
    ]
    if nntp_lines:
        print("\nnzbdav's own logs show NNTP/article problems in this window (root cause is")
        print("usually here, not in nzbdav-rclone - the provider doesn't have the data):")
        for line in nntp_lines[-5:]:
            print(f"  {line}")

    symlink = _resolve_symlink(media_root, top_id)
    if not symlink:
        print(f"\nCouldn't resolve {top_id} to a symlink under {media_root} - it may already")
        print("have been removed, or media_root needs adjusting for this stack.")
        return
    print(f"\nResolves to: {symlink}")
    print("Check this against Radarr/Sonarr's own API (GET /api/v3/movie or /series, look for")
    print("a movieFile/episodeFile path matching the above) to find the exact entry, then")
    print("confirm with the user before deleting anything - this command only diagnoses.")


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
