# Architecture Reference

Architecture facts, service inventory, commands, and deliberate design decisions for the media-stack. Split from STACK.md for focused reading.

> **Ground truth**: `docker-compose.yml` + `README.md`'s service table are authoritative for current inventory. This file captures the *relationship* map and non-obvious design rationale.

---

## What This Is

A Docker Compose media-acquisition-and-serving stack: indexes via Prowlarr, requests via Seerr, organizes via Radarr/Sonarr, acquires via Usenet through **nzbdav/nzbdav** (WebDAV + FUSE sidecar), and serves through **Plex**. One compose file, every image pinned and healthchecked.

Two operator surfaces: a **Control Panel** (Django + htmx dashboard, port 8420) and a **CLI** (133 `stack-*` fish functions). Every web UI publishes directly to the LAN with no login gate.

---

## Full Service Inventory

### Indexing
- **prowlarr** — Usenet indexer manager, pushes to Radarr/Sonarr via `fullSync`

### FUSE Mount Owners
- **nzbdav_rclone** — mounts nzbdav's WebDAV at `/mnt/remote/nzbdav` via rclone FUSE

### *Arr Apps
- **radarr** (port 7878) — movies, `/data/movies`
- **sonarr** (port 8989) — TV, `/data/shows`
- **radarr-anime** (port 7879) — anime movies, `/data/anime-movies`
- **sonarr-anime** (port 8990) — anime shows, `/data/anime-shows`

### Usenet
- **nzbdav** (port 3000) — WebDAV + SABnzbd-compatible API, the only download client

### Requests
- **seerr** (port 5055) — user-facing request frontend

### Media Server
- **plex** (host networking) — media server, VAAPI hardware transcode

### Subtitles
- **bazarr** (port 6767) — subtitle downloader

### Dashboard
- **control-panel** (port 8420) — custom Django dashboard

### Post-Processing
- **unpackerr** — RAR extraction

### Auto-Updates
- **watchtower** — daily auto-update for channel-tag images

### Queue Cleanup
- **cleanuparr** (port 11011) — strike/malware/stalled-download cleanup

### Monitoring
- **loki** (port 3100) — log aggregation
- **promtail** — log shipper
- **grafana** (port 3001) — dashboards
- **prometheus** (port 9090) — metrics
- **node-exporter** — host metrics
- **cadvisor** (port 8080) — container metrics
- **nzbdav-exporter** — NzbDAV config/queue metrics

### Metadata Cache
- **metacache** (port 8765) — Plex metadata provider proxy

### Other
- **ntfy** (port 8700) — push notifications
- **speedtest-tracker** (port 8701) — ISP monitoring
- **organizr** (port 8702) — single-pane frontend
- **scrutiny** (port 8703) — SMART disk health
- **watchstate** (port 8705) — cross-server watch-state sync

---

## Commands

```bash
# Validate compose config (what CI runs)
cp .env.example .env
docker compose config --quiet

# Lint
ruff check scripts/ tests/
shellcheck scripts/*.sh

# Rebuild control-panel (baked into image at build time)
docker compose build control-panel
docker compose up -d --force-recreate control-panel

# Bring up the stack
docker compose up -d

# Check download queue before touching nzbdav
stack-nzbdav-queue

# Unit tests
pip install -r control-panel/requirements.txt -r requirements-dev.txt
pytest
```

---

## Architecture Facts

### Root folders are 100% symlinks

Every media file in `./media/<type>` is a symlink into the FUSE mount. New services that read a root folder need the same `/mnt/remote/nzbdav` mount — not just the root folder itself. Stash's first deploy proved this: mounted only `./media/adult:/data`, every symlink was dangling from inside that container, scan completed with no error, found 0 items.

### FUSE mount cascade

`nzbdav_rclone` owns the mount. Every container that bind-mounts that path (Radarr, Sonarr, Plex, Unpackerr, Cleanuparr) holds a stale reference after the owner restarts. This does not self-heal. The Control Panel's restart-all endpoint sequences this: prereq (nzbdav healthy) → mount provider (nzbdav_rclone) → wait for healthy → dependents last.

### Root folder drift

A library rescan can reset an item's root folder back to `/mnt/<mount>/...` in an app's database. This is invisible to git since it's app state, not config. If an import stalls, check the item's resolved root folder first.

### Container-level wiring ≠ app-level wiring

A service can be connected at the compose level and still not be wired into the app it talks to. Cleanuparr's `arr_instances` table once had Lidarr/Whisparr with config-type placeholders but no real instance. Always check the receiving app's own config/API for a real instance entry.

### Image pinning is deliberately inconsistent

Channel tags for hotio images, version tags where upstream cuts releases, digest pins where `:latest` is ahead of any tag, and manually-bumped version tags for specific apps. Watchtower only auto-updates channel-tag images.

### Config holds real secrets

`config/<app>/` contains plaintext API keys and passwords. It's gitignored and not reproducible by `docker compose up`. As of the restic removal, no automated backup mechanism protects this.

### Resource limits required

Every service should have `mem_limit`/`cpus`. The `x-common` anchor does not set either. Ten services silently had neither for an unknown stretch of the project's history.

---

## Deliberate Design Decisions

1. **Usenet-only** — Torrent/debrid removed entirely in v11.0.0 after the Usenet migration proved reliable.

2. **Zero local media files** — nzbdav streams via WebDAV, nzbdav_rclone FUSE-mounts, arr apps symlink-import. Nothing written to local disk.

3. **Headless config** — Every service configured via environment variables, not manual Settings-UI clicks.

4. **Mount-order aware restarts** — The FUSE cascade (nzbdav → nzbdav_rclone → dependents) is sequenced in the Control Panel.

5. **Plex on host networking** — GDM auto-discovery, DLNA, and remote-access NAT-PMP/UPnP are unreliable on bridge networking.

6. **No login gate** — Every web UI publishes directly to the LAN. POST/PUT/DELETE validate Origin/Host headers as CSRF guard, not auth.

7. **Scheduled over real-time** — Plex's `FSEventLibraryUpdatesEnabled` disabled; replaced with 6h scheduled scan to prevent SQLite contention during import bursts.

8. **Bearer token for host actions** — Destructive endpoints (reboot, pacman) accept `Authorization: Bearer <key>` instead of `X-Api-Key` to prevent accidental automation triggers.

9. **nzbdav_rclone over single-binary** — Deliberate tradeoff: two containers instead of one, but rclone's FUSE implementation is more stable than BearMount's embedded Go FUSE.

10. **Content-routing groups must be removed with their app** — Zurg's `music`/`adult` groups outlived their apps and silently misrated real movies. The lesson: when removing an app that owns a filter/group, removing the group must be part of that same checklist.