# Known Landmines

Active issues that are still true as of the last audit. Not historical — these affect operations today.

> When in doubt about current state, `docker compose ps` / `docker-compose.yml` is ground truth.

---

## FUSE Mount Fragility

### Direct subpath bind of a FUSE mountpoint doesn't survive owner restart

A bind like `/mnt/remote/nzbdav:/mnt/remote/nzbdav:rslave` does not reliably survive the FUSE process being recreated underneath it (image update, resource-limit change, plain restart). Confirmed live across every Usenet client this stack has run.

**Never** `sudo umount` a FUSE mountpoint yourself to "clear" it — with `rshared` propagation this can tear down the real live mount instead of just a stale reference. Confirm the mount owner is healthy first, then restart dependents.

### Mount-owner restart breaks all dependents

Every container that bind-mounts the FUSE path holds a stale reference after the owner restarts. This does not self-heal — each dependent needs its own restart. The Control Panel's restart-all endpoint encodes the known ordering (`MOUNT_PREREQS` → `MOUNT_PROVIDERS` → everything else → `MOUNT_DEPENDENTS` last). If you add a new service that owns or depends on a FUSE mount, that set needs a manual update.

### rclone "already mounted" false-positive

Bind-mounting the exact FUSE target path (`/mnt/remote/nzbdav:/mnt/remote/nzbdav`) makes rclone's pre-mount safety check see that path as already a mount boundary and refuse to mount on every attempt. Fixed by binding the parent directory (`/mnt/remote:/mnt/remote:rshared`) instead and letting rclone create the `nzbdav` subdirectory fresh underneath.

---

## Plex

### FSEventLibraryUpdatesEnabled disabled — 6h scheduled scan only

Plex's real-time filesystem-triggered library updates were disabled to prevent SQLite contention during import bursts. New content takes up to 6h to appear automatically. Use `stack-plex-scan` for immediate scan.

### stop_grace_period: 90s required

Plex's shutdown legitimately takes ~40s under load. Without `stop_grace_period: 90s`, Docker's 10s default SIGKILL fires mid-sequence, producing a genuine unkillable D-state hang.

### Hardware transcode needs whole /dev/dri

Mapping only `renderD128` leaves every real transcode falling back to software encode. Plex's hardware-eligibility probe needs `card1` and the `by-path` entries too.

---

## NZBDAV

### Queue is not a persistent volume

Any recreate wipes queued NZBs and each resulting failure silently unmonitors + permanently blocklists the affected Radarr/Sonarr item. Confirm pending/processing is 0 before touching the container.

### Import strategy "symlinks" means no real files on disk

Completed items land as symlinks under the FUSE mount. Radarr's/Sonarr's `copyUsingHardlinks: true` produces another symlink, never a byte copy.

### Config holds provider credentials in plaintext

`config/nzbdav/db.sqlite`'s `ConfigItems` table holds Usenet provider username/password. Rotating these requires the nzbdav login+get-config/update-config pattern, not a direct file edit.

---

## Control Panel

### Reads .env at container-create time only

A plain `restart` does not pick up a `.env` change. Use `--force-recreate`.

### Static files baked into image at build time

`static/` (CSS/JS/HTML) is COPY'd in the Dockerfile, not bind-mounted. Edit on disk → `docker compose build control-panel` → `docker compose up -d --force-recreate control-panel`.

### CSRF Origin validation, not auth

POST/PUT/DELETE validate Origin/Host headers as a CSRF guard. This is not a login gate. Every web UI publishes directly to the LAN.

### Mount-order sets are hand-maintained

`MOUNT_PREREQS`, `MOUNT_PROVIDERS`, `MOUNT_DEPENDENTS` are hardcoded, not derived from `docker-compose.yml`. Adding a new mount-dependent service requires a manual update.

---

## Service Lifecycle

### New content-routing groups must be removed with their app

Zurg's content-routing groups (`music`/`adult`/anime) outlived their apps and silently misrated real movies. When removing an app that owns a filter/group of any kind, removing the group itself has to be part of that same removal checklist.

### App removal checklists must be exhaustive

Every removal touches: compose block, config directory, env vars, Prowlarr application-sync entry, Cleanuparr SQLite row, Control Panel references, fish functions, and any content-routing groups. Nothing auto-detects orphaned references.

### Cleanuparr auto-discovers but doesn't auto-register

Cleanuparr discovers which *arr apps exist, but needs its own internal instance registration (`arr_instances` table) before it does anything. Network access alone is not sufficient.

### Watchtower doesn't auto-update digest-pinned or version-tagged images

Only channel-tag images (hotio `:release`) auto-update. Digest-pinned (Seerr, Unpackerr) and manually-versioned (Plex) are excluded by design.