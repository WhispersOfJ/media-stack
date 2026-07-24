---
name: usenet-orchestrator
description: Inspect and manage BearMount's download queue and health — the only download client this stack runs (torrent/debrid support was removed entirely in v11.0.0; NzbDAV was replaced by AltMount, itself replaced by BearMount). `diagnose-stuck-file` is a documented no-op here — it was built around NzbDAV/nzbdav-rclone's specific log pattern and refuses to guess at a BearMount equivalent. Use when the user asks about stuck or failed downloads, wants to see what's queued, needs to clear a jammed queue item, or wants to confirm the download client is reachable by the Arr apps. Trigger phrases: "what's stuck in the download queue", "check bearmount status", "clear failed downloads", "why isn't radarr grabbing anything".
---

# Usenet Orchestrator

Queries BearMount's own SABnzbd-compatible API directly (bypassing the Arr apps) to
answer "is the download client itself the problem?" before assuming it's an indexer,
mount, or Arr config issue. Complements `health-monitor` (which checks container-level
health) by checking *queue-level* health: stuck items, failed items, and reachability.

## Scope

- `bearmount` — the only download client this stack runs (SABnzbd-compatible API,
  `WhispersOfJ/bearmount`, a rebranded fork of `javi11/altmount`, which itself replaced
  NzbDAV). Torrent/debrid support (Decypharr, Zurg, rclone-alldebrid, Zilean, Byparr) was
  removed entirely in v11.0.0 — nothing else to orchestrate here.
- `orchestrator.py::CLIENTS` is written generically (any SABnzbd/qBittorrent-API-
  compatible client can be added back) in case that ever changes, but as of now it only
  lists `bearmount`.

BearMount owns its FUSE mount directly (no separate `-rclone` sidecar container, unlike
NzbDAV's old two-container split) — mount-cascade restarts are still
`docker-compose-manager`'s job, this skill only talks to the download-client queue API.

## Auth / config

```
BEARMOUNT_URL / BEARMOUNT_API_KEY   (defaults to http://localhost:PORT if unset)
```

Never hardcode a real LAN IP or credential as a fallback — env vars only, `localhost`
default.

## Usage

```bash
python3 orchestrator.py queue bearmount                 # list current queue items + state
python3 orchestrator.py failed bearmount                 # list only failed/error items
python3 orchestrator.py retry bearmount <item-id>        # re-queue a failed item
python3 orchestrator.py clear-failed bearmount            # remove all failed items (asks first)
python3 orchestrator.py reachability                      # ping the configured client, report up/down
```

`diagnose-stuck-file` still exists as a subcommand but is a documented no-op: it was
built around NzbDAV/nzbdav-rclone's specific repeating `.ids/<uuid> 404 Not Found` log
pattern, and no equivalent pattern has been confirmed for AltMount or BearMount — running
it just prints that explanation rather than searching logs that likely don't match.

## Interpreting results

- A client that's unreachable (`reachability` fails) almost always means the container
  is down or mid-restart — hand off to `docker-compose-manager status bearmount` rather
  than digging further here.
- A client that's reachable but has a growing "failed" queue with the same error message
  repeated is usually an indexer/API-limit problem upstream in Prowlarr, not this skill's
  job to fix — report the pattern, don't guess at Prowlarr config.
- Stuck-but-not-failed items (state unchanged across repeated `queue` calls) often
  correlate with a stale FUSE mount — cross-check with `docker-compose-manager cascade-map`
  before assuming the download client itself is broken.
- Before recreating/restarting `bearmount` for any reason, check its own `import_queue`
  table for pending/processing rows first — see CLAUDE.md's hard rule on this; a recreate
  wipes anything still queued and can silently blocklist affected Radarr/Sonarr items.

## Safety rules

- `clear-failed` prompts for confirmation — it's a bulk destructive action on queue state.
- `retry` only touches the single item ID given; never retries an entire queue implicitly.
