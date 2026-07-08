# Plex Containerization Plan

**Status: planned, not yet implemented.** Paused 2026-07-08 at the user's request — resuming in
a few hours. Nothing in this document has been executed against the live host yet; native Plex
is untouched and still running as `plexmediaserver.service`.

This is the plan for bringing Plex into `docker-compose.yml` alongside the rest of the stack,
the same way Zurg/rclone-AllDebrid were containerized in [3.2.0](CHANGELOG.md). Once this ships,
this file's content moves into [CHANGELOG.md](CHANGELOG.md) and this file goes away, same as any
[TODO.md](TODO.md) item.

## Current state (what's being migrated)

- Plex is native — Arch's `plexmediaserver` package, running as a system-level systemd unit
  under a dedicated `plex` user, **uid/gid 955** (not the `bear` 1000/1000 this stack's other
  services use). `plex` is already in the `bear` group, which is how it currently reads the arr
  apps' media.
- Data lives at `/var/lib/plex/Plex Media Server` — **33GB**, library DB alone is 569MB. Years
  of watch history, collections, Kometa-applied metadata/overlays, Plex Home users.
- GPU: AMD Radeon 680M iGPU (`amdgpu` driver). `/dev/dri/renderD128` is world-writable
  (`rw-rw-rw-`) — same device Jellyfin used for VAAPI transcoding with zero `group_add` needed
  back in [2.4.0](CHANGELOG.md), before that whole experiment was reverted in
  [2.5.0](CHANGELOG.md).
- **User confirmed an active Plex Pass** — hardware transcoding is a real, usable feature here,
  not theoretical.
- `/var/lib/plex` (root btrfs subvolume `@`) and `/home/bear/Stack` (subvolume `@home`) are on
  the same physical NVMe but **different btrfs subvolumes** — moving the data dir between them
  is a real copy, not an instant rename. 753GB free, so no space problem, just real I/O time.

## Decisions made

| Question | Decision | Why |
|---|---|---|
| Image | Official `plexinc/pms-docker` | LinuxServer discontinued their own Plex image. This repo already avoids LinuxServer forks when existing data has non-1000/1000 ownership (see the Kometa entry in [README.md](README.md)) — a LinuxServer-style image would force a chown of 33GB to `PUID`/`PGID` on first boot. The official image supports `PLEX_UID`/`PLEX_GID` env vars directly, doing the same job without the chown. |
| Run-as identity | `PLEX_UID=955`, `PLEX_GID=955` | Matches the existing native `plex` user exactly. Zero chown, zero permission drama on 33GB. |
| Networking | `network_mode: host` | The one deliberate exception to this stack's `stacknet` bridge + published-port pattern. Plex's GDM auto-discovery, DLNA, and remote-access NAT-PMP/UPnP are unreliable on bridge networking. Every other service already publishes directly to `0.0.0.0` anyway, so nothing else in the stack is affected. |
| GPU passthrough | `/dev/dri/renderD128`, `group_add` for `video`(983)/`render`(987) as a defensive fallback | Plex Pass confirmed active — VAAPI hardware transcoding is worth wiring up in full. |
| Transcode temp dir | Plain disk bind mount | User reported transcoding is rarely used (mostly direct play) — a RAM-backed tmpfs isn't worth the added RAM-budget complexity here. |
| Image pin | Version-pin to the currently-installed native build, manually bumped (like Seerr/Homepage/Kometa), **not** on Watchtower's daily auto-update train | An unattended PMS major-version bump on a live library is higher blast radius than any other container in this stack. |
| Native package after cutover | **Disable, keep installed as rollback fallback** — don't uninstall immediately | Matches this repo's own precedent from the Zurg/rclone-AllDebrid migration ([3.2.0](CHANGELOG.md)), which also disabled-not-removed the native units before anything was removed. |

## The one hard constraint: path parity

Plex's library DB stores **absolute filesystem paths** per library location (`/mnt/zurg/movies`,
`/mnt/decypharr/...`, `/home/bear/Stack/media/movies`, etc.). The container must bind-mount
every existing library location at the *identical* absolute path already stored in the DB, or
every item shows as missing and it's a multi-thousand-item manual relink. This is the same
failure category already hit twice in this repo with Radarr's root-folder path drift
([2.2.0](CHANGELOG.md), [3.2.2](CHANGELOG.md)) — get it right on the first boot.

Everything else about the database survives by construction: the entire `Plex Media Server`
directory (DB, `Preferences.xml` with the claimed server identity/auth token, all metadata, all
Kometa-applied art) moves wholesale into `./config/plex` and gets bind-mounted back in as-is.
Nothing gets regenerated or re-claimed.

## Sequencing (when resumed)

1. Fresh backup of `/var/lib/plex/Plex Media Server` before cutover — the existing
   `~/PlexBackup_2026-07-03.tar.gz` will be stale by the time this resumes.
2. Stop + disable native `plexmediaserver.service` (system-level unit, needs sudo — different
   from this stack's user-level `media-stack.service`). Must happen *before* copying the DB to
   avoid grabbing it mid-write.
3. Copy (real copy, not `mv` — different btrfs subvolumes) the data dir into `./config/plex`,
   matching this repo's `config/<app>/` convention so it's covered by the same backup/doc
   patterns as every other service.
4. Add the `plex` service block to `docker-compose.yml`: host networking, `PLEX_UID`/`PLEX_GID`,
   identical absolute-path mounts for every existing library location, GPU device, healthcheck
   (`GET /identity`, unauthenticated — same pattern every other service in this compose file
   uses), version pin. No `<<: *common` anchor — it injects `PUID`/`PGID`, which Plex doesn't
   use.
5. Bring it up, verify: libraries show zero "missing files," Continue Watching/watch history
   intact, one real hardware-transcoded playback test.
6. Only after that's confirmed stable for real use — leave the native package disabled as a
   fallback (per the decision above), don't remove it yet.
7. Update [README.md](README.md) (new architecture note, new service table row, note the
   `network_mode: host` exception), [CHANGELOG.md](CHANGELOG.md) (new version entry), remove
   this file, and add `config/plex` to `scripts/backup-config.sh` — with excludes for
   regenerable `Metadata/`/codec caches (large, re-fetchable) while keeping `Databases/` and
   `Preferences.xml` in scope (irreplaceable).
