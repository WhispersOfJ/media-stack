---
name: usenet-torrent-orchestrator
description: Inspect and manage download-client queues and health across the stack's Usenet/debrid/torrent backends — nzbdav (Usenet), decypharr and zurg (debrid mounts), and any qBittorrent-style clients. Use when the user asks about stuck or failed downloads, wants to see what's queued, needs to clear a jammed queue item, or wants to confirm a download client is actually reachable by the Arr apps before troubleshooting further upstream. Trigger phrases: "what's stuck in the download queue", "check nzbdav status", "clear failed downloads", "is decypharr healthy", "why isn't radarr grabbing anything".
---

# Usenet/Torrent Orchestrator

Queries the download-client APIs directly (bypassing the Arr apps) to answer "is the
download client itself the problem?" before assuming it's an indexer, mount, or Arr
config issue. Complements `health-monitor` (which checks container-level health) by
checking *queue-level* health: stuck items, failed items, and per-client reachability.

## Scope

- `nzbdav` — Usenet download client (SABnzbd-compatible API)
- `decypharr` / `decypharr-alldebrid` — debrid-backed download client
- Any additional qBittorrent-API-compatible client configured via `QBIT_URL`/`QBIT_*`

This skill does **not** manage the underlying FUSE mounts (`zurg`, `rclone-*`) — that's
`docker-compose-manager`'s cascade-restart job. It only talks to the download-client
queue APIs.

## Auth / config

```
NZBDAV_URL / NZBDAV_API_KEY         (defaults to http://localhost:PORT if unset)
DECYPHARR_URL / DECYPHARR_API_KEY
QBIT_URL / QBIT_USERNAME / QBIT_PASSWORD   (only if a qBittorrent-API client is present)
```

Never hardcode a real LAN IP or credential as a fallback — env vars only, `localhost`
default.

## Usage

```bash
python3 orchestrator.py queue nzbdav                 # list current queue items + state
python3 orchestrator.py queue decypharr
python3 orchestrator.py failed nzbdav                 # list only failed/error items
python3 orchestrator.py retry nzbdav <item-id>        # re-queue a failed item
python3 orchestrator.py clear-failed nzbdav            # remove all failed items (asks first)
python3 orchestrator.py reachability                   # ping every configured client, report up/down
```

## Interpreting results

- A client that's unreachable (`reachability` fails) almost always means the container
  is down or mid-restart — hand off to `docker-compose-manager status <service>` rather
  than digging further here.
- A client that's reachable but has a growing "failed" queue with the same error message
  repeated is usually an indexer/API-limit problem upstream in Prowlarr, not this skill's
  job to fix — report the pattern, don't guess at Prowlarr config.
- Stuck-but-not-failed items (state unchanged across repeated `queue` calls) often
  correlate with a stale FUSE mount — cross-check with `docker-compose-manager cascade-map`
  before assuming the download client itself is broken.

## Safety rules

- `clear-failed` prompts for confirmation — it's a bulk destructive action on queue state.
- `retry` only touches the single item ID given; never retries an entire queue implicitly.
