---
name: usenet-orchestrator
description: Inspect and manage NzbDAV's download queue and health — the only download client this stack runs (torrent/debrid support was removed entirely in v11.0.0). Also diagnoses an already-imported file nzbdav-rclone can't stop retrying (permanently missing Usenet articles) and resolves it back to the real Radarr/Sonarr library entry. Use when the user asks about stuck or failed downloads, wants to see what's queued, needs to clear a jammed queue item, wants to confirm the download client is reachable by the Arr apps, or reports a movie/show that "won't play"/"errors out" despite Radarr/Sonarr showing it as already downloaded. Trigger phrases: "what's stuck in the download queue", "check nzbdav status", "clear failed downloads", "why isn't radarr grabbing anything", "this file won't play", "nzbdav keeps erroring on the same file".
---

# Usenet Orchestrator

Queries NzbDAV's own API directly (bypassing the Arr apps) to answer "is the download
client itself the problem?" before assuming it's an indexer, mount, or Arr config issue.
Complements `health-monitor` (which checks container-level health) by checking
*queue-level* health: stuck items, failed items, and reachability.

## Scope

- `nzbdav` — the only download client this stack runs (SABnzbd-compatible API).
  Torrent/debrid support (Decypharr, Zurg, rclone-alldebrid, Zilean, Byparr) was removed
  entirely in v11.0.0 — nothing else to orchestrate here.
- `orchestrator.py::CLIENTS` is written generically (any SABnzbd/qBittorrent-API-
  compatible client can be added back) in case that ever changes, but as of now it only
  lists `nzbdav`.

This skill does **not** manage the underlying FUSE mount (`nzbdav-rclone`) — that's
`docker-compose-manager`'s cascade-restart job. It only talks to the download-client
queue API.

## Auth / config

```
NZBDAV_URL / NZBDAV_API_KEY         (defaults to http://localhost:PORT if unset)
```

Never hardcode a real LAN IP or credential as a fallback — env vars only, `localhost`
default.

## Usage

```bash
python3 orchestrator.py queue nzbdav                 # list current queue items + state
python3 orchestrator.py failed nzbdav                 # list only failed/error items
python3 orchestrator.py retry nzbdav <item-id>        # re-queue a failed item
python3 orchestrator.py clear-failed nzbdav            # remove all failed items (asks first)
python3 orchestrator.py reachability                   # ping the configured client, report up/down
python3 orchestrator.py diagnose-stuck-file             # find the *arr entry behind a permanently-broken nzbdav file
python3 orchestrator.py diagnose-stuck-file --since 24h --media-root /path/to/media
```

`diagnose-stuck-file` is **read-only** - it identifies the problem and tells you what to
check, it never deletes anything. It greps `nzbdav-rclone`'s container logs for the last
`--since` window (default `6h`) for repeating `vfs cache ... 404 Not Found` errors against
the same internal `.ids/<uuid>` path - a file whose Usenet articles are gone permanently
produces this every ~10-20s, forever, not as a transient blip. It then cross-references
`nzbdav`'s own container logs for `missing articles`/NNTP errors in the same window (that's
usually where the real root cause shows up, not in nzbdav-rclone's logs), and resolves the
most-frequent stuck id to a real symlink under `--media-root` (default `/data` - override to
match this stack's actual host media path) via `readlink`/`find -lname`. Confirmed live
2026-07-16 against a real case (*The Escapees (1981)*, 2160p UHD remux, missing par2 recovery
blocks too) - the loop only stopped once that specific Radarr file record was deleted.

## Interpreting results

- A client that's unreachable (`reachability` fails) almost always means the container
  is down or mid-restart — hand off to `docker-compose-manager status nzbdav` rather
  than digging further here.
- A client that's reachable but has a growing "failed" queue with the same error message
  repeated is usually an indexer/API-limit problem upstream in Prowlarr, not this skill's
  job to fix — report the pattern, don't guess at Prowlarr config.
- Stuck-but-not-failed items (state unchanged across repeated `queue` calls) often
  correlate with a stale FUSE mount — cross-check with `docker-compose-manager cascade-map`
  before assuming the download client itself is broken.
- `diagnose-stuck-file` finding zero repeating ids doesn't mean nothing's wrong — it only
  covers files already imported into a library and being re-read (Plex scans, playback
  attempts). A download still sitting in the active queue is a different problem; check
  `queue`/`failed` first.
- A resolved symlink with no matching Radarr/Sonarr entry usually means the file was
  already cleaned up since the log window started — re-run with a shorter `--since`.

## Safety rules

- `clear-failed` prompts for confirmation — it's a bulk destructive action on queue state.
- `retry` only touches the single item ID given; never retries an entire queue implicitly.
- `diagnose-stuck-file` never deletes anything — confirm the resolved Radarr/Sonarr entry
  against the real API yourself, and get explicit user confirmation, before removing any
  file record it points to.
