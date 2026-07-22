# The Stack

Current version: **v11.7.0**

A Docker Compose media-acquisition-and-serving stack. Indexes, requests, and acquires content
via Usenet - streamed, not downloaded - and serves the result through a containerized
**Jellyfin** (`lscr.io/linuxserver/jellyfin:latest`), which replaced Plex entirely in v11.7.0
(see [History](#history)). Torrent/debrid support was removed entirely in v11.0.0 (see
[History](#history)). 16 services, one compose file, every image pinned and healthchecked. Two
operator surfaces: a custom dashboard (Control Panel) and a custom CLI (`stack-*` fish
functions).

This is the only document in this repo besides raw config files. It merges the former
`README.md`, `TECHNICAL.md`, and `CHANGELOG.md`, organized by subsystem. A condensed
chronological [History](#history) section is at the end.

## Contents

- [What this actually is](#what-this-actually-is)
- [Quick start](#quick-start)
- [Architecture](#architecture)
- [Directory layout](#directory-layout)
- [The full service list](#the-full-service-list)
- [The *arr apps](#the-arr-apps)
- [The Usenet pipeline: NzbDAV](#the-usenet-pipeline-nzbdav)
- [Indexing: Prowlarr](#indexing-prowlarr)
- [Requests: Seerr](#requests-seerr)
- [Jellyfin](#jellyfin)
- [Bindery and Calibre-Web: retired](#bindery-and-calibre-web-retired)
- [Custom formats and quality profiles](#custom-formats-and-quality-profiles)
- [Automation extras: Cleanuparr, NeutArr, Unpackerr, Watchtower](#automation-extras-cleanuparr-neutarr-unpackerr-watchtower)
- [Monitoring extras: Jellystat](#monitoring-extras-jellystat)
- [Bazarr: subtitle management](#bazarr-subtitle-management)
- [Control Panel](#control-panel)
- [CLI: the `stack-*` fish functions](#cli-the-stack--fish-functions)
- [Backups](#backups)
- [Alerting (Discord)](#alerting-discord)
- [Image pinning policy](#image-pinning-policy)
- [Resource limits](#resource-limits)
- [Security](#security)
- [CI](#ci)
- [Installer image and setup wizard](#installer-image-and-setup-wizard)
- [Known gaps and limitations](#known-gaps-and-limitations)
- [History](#history)

## What this actually is

A Usenet-only media stack: an indexer layer (Prowlarr), a request front-end (Seerr), two
`*arr` apps (Radarr, Sonarr; Lidarr was removed in v10.9.9 and Whisparr in v10.12.0, see
[History](#history)), Usenet acquisition that streams rather than downloads (NzbDAV), a
containerized **Jellyfin**, and automation/monitoring extras (Cleanuparr, NeutArr, Unpackerr,
Watchtower, Bazarr, Jellystat). Ebooks briefly had a dedicated app (Bindery) plus a reader
(Calibre-Web); both were retired in v10.9.8 with no replacement (see
[Bindery and Calibre-Web: retired](#bindery-and-calibre-web-retired)). Adult content
cataloging (Stash) was also removed in v10.12.0, along with Whisparr, which had managed its
underlying library.

**Plex was removed entirely in v11.7.0, replaced by Jellyfin** (see [History](#history) for
the full migration). Jellyfin carries over Plex's final two libraries exactly - Movies
(`/data/movies`), Shows (`/data/shows`) - and the same VAAPI hardware-transcode device. Kometa
and Tautulli, both Plex-specific integrations, were affected: **Kometa cannot talk to Jellyfin
at all** (no `jellyfin`/`emby` property in its own config schema, only `plex` - confirmed by
reading `kometa-team/kometa`'s `config-schema.json` directly, contradicting several blog posts
that claim otherwise), so Kometa and its Quickstart companion were **removed entirely** (see
[Jellyfin](#jellyfin) and [History](#history) `[11.7.0]`) - **no automated Plex/Jellyfin
collections, overlays, or metadata-enrichment tool of any kind currently runs in this stack**;
**Tautulli was removed entirely** (Plex-only, nothing left to monitor) and replaced by
**Jellystat** (plus its own Postgres, `jellystat-db` - this stack's first Postgres dependency
since `zilean-postgres` was removed in v11.0.0) as the watch-history/stats dashboard. See
[Monitoring extras](#monitoring-extras-jellystat) and [History](#history) `[11.7.0]`.

**Torrent and debrid (Decypharr, Zurg, rclone-alldebrid, Zilean, Byparr) were removed
entirely** (see [History](#history)) - the stack ran debrid-first originally, flipped to
Usenet-preferred in v10.14.1, and finally went Usenet-only once that migration proved out.
NzbDAV covers acquisition as a WebDAV virtual filesystem streamed on demand, not a local
download. NZBGet, which wrote real files to disk, was removed earlier (see
[History](#history)).

This assumes familiarity with Docker Compose. Every web UI publishes directly to the LAN with
no login gate (see [Security](#security)). A Traefik + Authelia + CrowdSec auth layer was
built, verified, and reverted (see [History](#history)).

## Quick start

```bash
mkdir -p ~/Stack && cd ~/Stack

# 1. Scaffold this repo's tracked files onto a fresh host (docker-compose.yml,
#    .env.example, scripts/, systemd/, this README) - no git clone needed.
docker run --rm -v "$(pwd)":/out ghcr.io/whispersofj/media-stack:latest

# 2. Fill in .env via a browser form built from .env.example's own
#    sections/comments - open http://<this-host>:8090
docker run --rm -p 8090:8090 -v "$(pwd)":/out ghcr.io/whispersofj/media-stack:latest --setup

# 3. Bring the core stack up
docker compose up -d

# 4. Everything else (Jellystat, Unpackerr, Watchtower,
#    Cleanuparr, NeutArr, Control Panel, ...)
docker compose --profile extras up -d
```

Step 2 is optional: `cp .env.example .env && $EDITOR .env` works the same; the wizard is a
form over the same file. Mechanics of the installer image and wizard are in
[Installer image and setup wizard](#installer-image-and-setup-wizard).

Three values can only be collected after first boot, once the relevant app has generated
them: `RADARR_API_KEY`, `SONARR_API_KEY` (each app's **Settings > General > Security**), and
`JELLYFIN_API_KEY` (Jellyfin's own **Dashboard > Advanced > API Keys**, generated after its
own setup wizard completes). **`scripts/setup_wizard.py` was not updated for the v11.7.0
Plex-to-Jellyfin migration** - it still treats the now-removed `PLEX_TOKEN` as the third
post-boot-only field instead of `JELLYFIN_API_KEY`; see
[Installer image and setup wizard](#installer-image-and-setup-wizard) for the details. Enter
these via a second `--setup` run (it reloads the existing `.env` as defaults), then:

```bash
docker compose up -d --force-recreate control-panel
```

`control-panel` reads these at container-create time only; a plain `restart` does not pick up
a `.env` change. Use `--force-recreate`.

## Architecture

```
Prowlarr ──indexes──> your Usenet indexers
   │
   ▼
Radarr/Sonarr ──grab──> NzbDAV (SABnzbd-compatible API) ──streams via WebDAV──> rclone
                         mount at /mnt/nzbdav ──symlinked into──> each app's root folder:
                         ./media/<type> → /data/<type>

./media/{movies,shows}  → /data/{...}  → every app's writable root folder

Jellyfin (bridge networking on stacknet, port 8096 - no network_mode: host,
unlike Plex; ./media/{movies,shows} bind-mounted directly)
```

Root folders live on regular host disk (`./media/<type>`), matching every app's own tracked
root folder path. The only FUSE mount left in this stack is `nzbdav-rclone`'s, at
`/mnt/nzbdav` - every service that reads a root folder's symlinks needs that same mount
(Radarr, Sonarr, Unpackerr, Cleanuparr, and Jellyfin). **Jellyfin's compose block was
initially deployed with no `/mnt/nzbdav` mount at all**, reproducing exactly the class of bug
Stash's first deploy hit (see [Known gaps and limitations](#known-gaps-and-limitations)): the
library scan completed with no error and matched all 418 shows at the series/season level
(real directories), but silently added zero episodes, because every episode file is a symlink
into `/mnt/nzbdav` and every `readlink` resolved to a path that didn't exist in Jellyfin's own
mount namespace. **Confirmed live and fixed same-day**: a sample episode file
(`100 Foot Wave (2021) {tvdb-396600}/Season 3/...mkv`) was verified as a dangling symlink
inside the container (`cat` failed with "No such file or directory"), the mount
(`/mnt/nzbdav:/mnt/nzbdav:rslave`) was added to Jellyfin's compose block, and the same file
was reverified as readable (real Matroska bytes) before re-triggering the library scan.

> **FUSE mount fragility.** A direct subpath bind of a FUSE mountpoint
> (`/mnt/nzbdav:/mnt/nzbdav:rslave`) does not reliably survive the FUSE process being
> recreated underneath it (an nzbdav-rclone image update, a resource-limit change, a plain
> restart). Confirmed live 2026-07-18 during the torrent/debrid removal: recreating
> `nzbdav-rclone` and its five dependents (Radarr, Sonarr, Plex, Unpackerr, Cleanuparr) in the
> same batch left every dependent unable to start at all (`transport endpoint is not
> connected`) until `nzbdav-rclone` was restarted alone first and the stale host-level mount
> was cleared with a lazy unmount (`sudo umount -l /mnt/nzbdav`). Control Panel's whole-stack
> restart (see [Control Panel](#control-panel)) already sequences this: mount providers first,
> wait for healthy, dependents last.

`control-panel/app.py`'s `MOUNT_DEPENDENTS` set (see [Control Panel](#control-panel)) has been
updated for the Plex-to-Jellyfin migration: `{"radarr", "sonarr", "jellyfin", "unpackerr",
"cleanuparr"}` - `plex` replaced with `jellyfin`, now that Jellyfin is a confirmed
`/mnt/nzbdav` consumer like the rest of this set.

Seerr (formerly Overseerr/Jellyseerr; the projects merged) is the user-facing request page,
talking to Radarr and Sonarr, and - as of this writing - **still pointed at Plex, not yet
repointed at Jellyfin**: Seerr only supports one media server at a time (confirmed via its own
GitHub issue #511) and repointing it needs a human login step in its own settings UI, not an
API-only change. Treat "Seerr talks to Jellyfin" as not yet true until that step happens.

**Torrent and debrid support (Decypharr, Zurg, rclone-alldebrid, Zilean, Byparr) was removed
entirely** - see [History](#history) for the full removal and the architecture that preceded
this one.

## Directory layout

```
Stack/
├── docker-compose.yml
├── .env                              # PUID/PGID/TZ, every secret referenced below
├── README.md
├── config/<app>/                     # each app's persistent config (gitignored)
├── control-panel/                    # custom-built dashboard (own Dockerfile)
├── config/nzbdav/, config/nzbdav-rclone/rclone.conf   # NzbDAV + its rclone mount sidecar
├── scripts/                          # backup/alert/setup automation, stdlib-only Python or bash
├── systemd/                          # user-scope units for boot automation, backups, alerts
└── media/{movies,shows,music,books,adult,audiobooks,youtube}  # every arr app's writable root
                                       # folder, mounted at /data/<type>; youtube/ is an inert
                                       # leftover from a removed Pinchflat integration
```

## The full service list

Every service in `docker-compose.yml`, in the order they appear:

| # | Service | Image | Port(s) | Profile |
|---|---|---|---|---|
| 1 | `prowlarr` | `ghcr.io/hotio/prowlarr:release` | 9696 | core |
| 2 | `radarr` | `ghcr.io/hotio/radarr:release` | 7878 | core |
| 3 | `sonarr` | `ghcr.io/hotio/sonarr:release` | 8989 | core |
| 4 | `nzbdav` | `nzbdav/nzbdav:latest` | 3001→3000 | core |
| 5 | `nzbdav-rclone` | `rclone/rclone:1.74.4` | none | core |
| 6 | `seerr` | `ghcr.io/seerr-team/seerr@sha256:c92d2d...` | 5055 | core |
| 7 | `jellyfin` | `lscr.io/linuxserver/jellyfin:latest` | 8096 | core |
| 8 | `jellystat-db` | `postgres:18.1` | none | extras |
| 9 | `jellystat` | `cyfershepard/jellystat:latest` | 8087 | extras |
| 10 | `bazarr` | `ghcr.io/hotio/bazarr:release` | 6767 | extras |
| 11 | `control-panel` | built from `./control-panel` | 8420 | extras |
| 12 | `unpackerr` | `golift/unpackerr@sha256:4ec141...` | none | extras |
| 13 | `watchtower` | `nickfedor/watchtower:1.19.0` | none | extras |
| 14 | `cleanuparr` | `ghcr.io/cleanuparr/cleanuparr:2.9.16` | 11011 | extras |
| 15 | `neutarr` | `iampuid0/neutarr:1.9.1` | 9705 | extras |

`jellyfin` replaced `plex` entirely in v11.7.0 - same table position (#7), same core profile,
different image/port. `jellystat-db`/`jellystat` are new the same version, Tautulli's
Jellyfin-equivalent (Tautulli is Plex-only, and was itself removed entirely on the same
follow-up request as Kometa below - compose block and `config/tautulli/` both deleted). `kometa`
and `quickstart` were initially stopped the same version, then removed entirely (compose blocks
and `config/kometa`/`config/quickstart` both deleted from disk) at explicit follow-up
request - see [Jellyfin](#jellyfin). Service table: 18 → 15 rows.

`docker compose up -d` brings up the 7 core services; `docker compose --profile extras up
-d` adds the other 8. Both are safe to re-run; Compose only recreates what is out of sync
with `docker-compose.yml`. (Torrent/debrid - Decypharr, Zurg, rclone-alldebrid, Zilean,
zilean-postgres, Byparr - were removed entirely; see [History](#history).)

## The *arr apps

Both follow the same wiring: Prowlarr pushes Usenet indexers down via `fullSync`, NzbDAV is
the only download client, Unpackerr extracts RAR'd releases, the root folder is
`./media/<type>` mounted at `/data/<type>`, and Control Panel provides RSS sync /
search-missing / unstick / unstick-importing / manual-import for each.

| App | Port | Root folder | Content type |
|---|---|---|---|
| Radarr | 7878 | `/data/movies` | Movies |
| Sonarr | 8989 | `/data/shows` | TV |

Radarr and Sonarr were each removed and reinstated at earlier points; Lidarr was reinstated
in v10.2.0 and removed again in v10.9.9, and Whisparr was removed for the last time in
v10.12.0 (along with Stash, which cataloged its library). See [History](#history). The `*arr`
family is now Radarr/Sonarr only.

### Readarr is gone

Upstream Readarr was retired ("lack of developers... decided to retire the project," per
linuxserver.io's deprecation notice), and its Goodreads metadata lookup died permanently when
`bookinfo.club` expired. hotio never published a Readarr image; linuxserver's
`develop`/`nightly` tags stopped resolving to a valid manifest. It was replaced in v10.7.0 by
Bindery, which was itself retired in v10.9.8 along with Calibre-Web. There is currently no
ebook app in this stack. See
[Bindery and Calibre-Web: retired](#bindery-and-calibre-web-retired).

### Real API examples

Radarr and Sonarr expose the same `/api/v3` REST API shape:

```bash
# Radarr's health/liveness endpoint (used by every healthcheck in this stack)
curl -sf http://192.168.4.105:7878/ping

# List Radarr's configured root folders
curl -s -H "X-Api-Key: $RADARR_API_KEY" http://192.168.4.105:7878/api/v3/rootfolder | jq .

# Trigger an immediate RSS sync on Sonarr
curl -X POST -H "X-Api-Key: $SONARR_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"RssSync"}' http://192.168.4.105:8989/api/v3/command
```

### The Sonarr `missing-aired` pagination gap (known, unresolved)

Sonarr's Wanted/Missing UI cannot filter to "monitored, no file, already aired"
(`customFilterType` covers series/calendar/queue/history/blocklist/releases, not the
missing-episodes page). Without filtering, that list is buried under roughly 300,000
not-yet-aired episodes from daily/ongoing shows this instance tracks. Control Panel exposes a
purpose-built endpoint:

```bash
curl -s http://192.168.4.105:8420/api/arr/sonarr/missing-aired | jq .
curl -s http://192.168.4.105:8420/api/arr/radarr/missing-aired | jq .
```

For Sonarr it paginates `wanted/missing` ascending by air date and stops at the first future
episode instead of scanning the full list. Radarr's equivalent is a single unpaginated pass
(`monitored && !hasFile && isAvailable`); Radarr's movie list is much smaller than Sonarr's
episode table. This endpoint has no frontend wiring in Control Panel (curl/API only) and has
not been load-tested at the full ~300k-record scale. See
[Known gaps and limitations](#known-gaps-and-limitations).

## The debrid pipeline: removed

Zurg (Real-Debrid FUSE mount), Decypharr (two instances - qBittorrent-API gateway to
Real-Debrid + AllDebrid), rclone-alldebrid (AllDebrid FUSE mount), Zilean + zilean-postgres
(DMM cache-hash indexer), and Byparr (Cloudflare bypass, only needed by torrent trackers) were
**all removed entirely** - see [History](#history) for the full removal and rationale. This
stack is Usenet-only now (see [The Usenet pipeline: NzbDAV](#the-usenet-pipeline-nzbdav)).

Worth preserving from the old debrid era, in case anything like it comes back: Zurg's
content-routing config (`config/zurg/config.yml`, gitignored, deleted with the rest of that
config directory) had a real, repeated failure mode where a group's regex/keyword filter
would silently misroute real movies into an orphaned path once the app that group served was
removed but the group itself wasn't - happened three separate times (`music`'s bare `FLAC`
keyword matching remux audio tracks, `adult`'s bare `Wicked`/`XXX` keywords matching real film
titles, and the anime groups outliving the anime library removal by one release). **The
lesson, not tied to Zurg specifically: when removing an app that owns a content-routing
group/filter of any kind, removing the group itself has to be part of that same removal
checklist** - nothing else in this stack ever caught it on its own.

## The Usenet pipeline: NzbDAV

**NzbDAV** (`nzbdav/nzbdav:latest` plus an `nzbdav-rclone` sidecar) is a virtual filesystem,
not a local downloader: it exposes Usenet content as a WebDAV server, `nzbdav-rclone` mounts
that WebDAV at `/mnt/nzbdav`, and completed downloads appear there as symlinks streamed on
demand.

```yaml
# docker-compose.yml
nzbdav:
  image: nzbdav/nzbdav:latest
  # Host port 3001 - DebridMediaManager used to own 3000 on this host
  # (removed v10.20.0), left at 3001 rather than reclaiming 3000. Internally
  # still :3000 (other containers reach it as http://nzbdav:3000 over
  # stacknet, unaffected by the host mapping).
  ports: ["3001:3000"]
  volumes:
    - ./config/nzbdav:/config
    - /mnt:/mnt

nzbdav-rclone:
  image: rclone/rclone:1.74.4
  command:
    - "mount"
    - "nzbdav:"
    - "/mnt/nzbdav"
    - "--vfs-cache-mode=full"
    - "--vfs-cache-max-size=20G"
    - "--vfs-cache-max-age=24h"
    # buffer-size=0 avoids double-caching (the OS/media-server already buffer
    # reads - Jellyfin now, Plex before it); read-ahead sized for high-bitrate
    # remux playback
    - "--buffer-size=0M"
    - "--vfs-read-ahead=512M"
```

**Provider**: a block-account news server is configured in NzbDAV's own UI (**Settings >
Usenet**), stored in `config/nzbdav/db.sqlite`'s `ConfigItems` table, not in a config file or
`.env`. `.env.example` documents the credentials anyway (`NZBDAV_PROVIDER_*`,
`NZBDAV_WEBDAV_*`, `NZBDAV_ADMIN_*`, `NZBDAV_API_KEY`) per this stack's convention: if a
credential lives in an app's own database or config rather than being read from `.env`,
`.env.example` still documents it as the reference copy, with a comment saying where it
actually lives. NzbDAV itself never reads `.env`.

**Import strategy** is "Symlinks - Plex" in NzbDAV's SABnzbd-compatible settings (backed by
the `api.import-strategy` config key, values `symlinks`/`strm`), with `Rclone Mount Directory`
pointed at `/mnt/nzbdav`. This is what makes Radarr/Sonarr treat completed downloads as
importable files. **Evaluated and deliberately rejected as part of the v11.7.0
Plex-to-Jellyfin migration** - NzbDAV does have a genuine STRM mode (confirmed by reading its
own source, `backend/Queue/PostProcessors/CreateStrmFilesPostProcessor.cs`: it writes a plain
text `.strm` file containing a direct HTTP URL back to NzbDAV's own `/view/...` endpoint,
bypassing the `/mnt/nzbdav` FUSE mount entirely - genuinely Emby/Jellyfin-only, Plex never
supported `.strm`). The setting is **global to NzbDAV**, not something Jellyfin could opt into
on its own - switching it changes what every consumer receives, Radarr/Sonarr included. Kept
on `symlinks` because of real, documented risk on the Radarr/Sonarr side: an open, unresolved
Radarr bug (`Radarr/Radarr#11435`) describes a grab-import-delete loop specific to `.strm`
files delivered by a SABnzbd-compatible client (exactly NzbDAV's own emulation), Radarr's own
`VideoFileInfoReader` runs `ffprobe` directly against the `.strm` text file (which always
fails, breaking resolution/codec media-info extraction), and a live user of this exact
NzbDAV+Radarr/Sonarr combination (`nzbdav-dev/nzbdav` Discussion #175, Nov 2025) reports being
"forced to still use rclone because the arrs can't figure out how to import .strm files."
The symlink approach has known, already-documented failure modes in this stack (see
[Jellyfin](#jellyfin)'s missing-mount fix above) but they're understood and fixable; the STRM
path has an open bug report for this exact software combination. Revisit only if that Radarr
issue is confirmed fixed in a real release.

NzbDAV is every `*arr` app's only download client (torrent/debrid was removed entirely - see
[History](#history)). API examples via Control Panel's proxy - queue/history
go through NzbDAV's SABnzbd-style query API (keyed by `NZBDAV_API_KEY`); its settings
(Usenet provider config) go through a separate backend with no static key, only a session
cookie from its own `POST /login` - Control Panel logs in with `NZBDAV_ADMIN_USER`/
`NZBDAV_ADMIN_PASSWORD` on every call:

```bash
# Current Usenet download queue
curl -s http://192.168.4.105:8420/api/nzbdav/queue | jq .

# Recent history (completed/failed), last 20 by default
curl -s http://192.168.4.105:8420/api/nzbdav/history | jq .

# Set every configured Usenet provider's max connections
curl -s -X POST http://192.168.4.105:8420/api/nzbdav/set-connections \
  -H 'Content-Type: application/json' -d '{"max_connections": 50}' | jq .
```

**UI quirk**: NzbDAV's "Add Provider"/"Test Connection" form only submits once every field
has been focused/touched in the browser, including fields already holding a valid default.
Clicking the button while any field is untouched does nothing: no request fires, nothing is
written to `db.sqlite`, and no error appears. Click or tab through every field first.

This replaced NZBGet, a real local downloader (files land on `./usenet`, then import into the
library), which did not match the stack's no-local-disk model. Its old `config/nzbget/` and
`usenet/` directories were left on disk, unused.

## Indexing: Prowlarr

**Prowlarr** (`ghcr.io/hotio/prowlarr:release`, port 9696) holds every configured Usenet
indexer and pushes them to Radarr/Sonarr via `Settings > Apps` `fullSync`. As of the
torrent/debrid removal (see [History](#history)), Prowlarr carries **Usenet indexers only** -
every torrent indexer (49 enabled at removal time, including the `Zilean` Torznab entry) was
disabled then deleted via its own API, in that order, so the change was verifiable and
reversible at each step before committing to it:

```bash
# Disable first (reversible, in case something needed re-checking)
curl -X PUT -H "X-Api-Key: $PROWLARR_API_KEY" -H "Content-Type: application/json" \
  http://192.168.4.105:9696/api/v1/indexer/<id> -d '{...same body, "enable": false}'

# Then delete once confirmed nothing depended on it
curl -X DELETE -H "X-Api-Key: $PROWLARR_API_KEY" \
  http://192.168.4.105:9696/api/v1/indexer/<id>
```

Zilean (the DMM cache-hash indexer, previously registered as a `Generic Torznab` indexer),
zilean-postgres, Decypharr (both instances), Zurg, rclone-alldebrid, and Byparr (Cloudflare
bypass - registered as Prowlarr's Indexer Proxy, but nothing among the remaining Usenet
indexers referenced it, confirmed by checking every indexer's `tags`/`indexerProxy` fields
before removing it) were all removed entirely in the same pass.

There is no music, ebook, or adult-content indexing path: Prowlarr's Lidarr application-sync
entry was deleted with Lidarr in v10.9.9, Bindery was retired in v10.9.8, and Prowlarr's
Whisparr application-sync entry was deleted with Whisparr in v10.12.0.

## Requests: Seerr

**Seerr** (`ghcr.io/seerr-team/seerr@sha256:c92d2d...`, port 5055; formerly
Overseerr/Jellyseerr, the projects merged) is the request entry point: search for a movie or
show, click Request. Connected to Radarr and Sonarr as default servers (the `Unlimited`
quality profile on both, `/data/movies`/`/data/shows`).

```bash
# Seerr's settings API accepts its stored API key as X-Api-Key - no session
# login needed for scripted config changes
curl -s -H "X-Api-Key: $SEERR_API_KEY" http://192.168.4.105:5055/api/v1/settings/radarr | jq .
```

## Jellyfin

Containerized, LinuxServer image (`lscr.io/linuxserver/jellyfin:latest`) - **replaced Plex
entirely in v11.7.0**, see [History](#history) for the full migration. LinuxServer's
PUID/PGID-forcing convention was chosen deliberately here, matching every hotio-style service
in this stack, not a claim that the official `jellyfin/jellyfin` image is worse.

```yaml
# docker-compose.yml
jellyfin:
  image: lscr.io/linuxserver/jellyfin:latest
  networks: [stacknet]
  volumes:
    - ./config/jellyfin:/config
    - ./media/movies:/data/movies
    - ./media/shows:/data/shows
  devices:
    - /dev/dri/renderD128:/dev/dri/renderD128   # same AMD Radeon 680M iGPU Plex used, VAAPI hardware transcode
  group_add: ["983", "987"]
  ports: ["8096:8096"]
```

- Bridge networking on `stacknet`, port 8096 published directly - **no `network_mode: host`**,
  unlike Plex. Plex needed the host network for GDM auto-discovery, DLNA, and NAT-PMP/UPnP
  remote-access negotiation; Jellyfin has no equivalent requirement here, so this stack no
  longer has any service using `network_mode: host` at all.
- Two libraries, matching Plex's final two exactly: Movies (`/data/movies`), Shows
  (`/data/shows`). Metadata providers: TheMovieDb + OMDb on Movies; TheTVDB + TheMovieDb + OMDb
  on Shows. **OMDb ships bundled with Jellyfin core already active** - not a separate catalog
  plugin install, a correction made mid-migration after an earlier draft plan wrongly assumed
  it needed installing. **A second assumption corrected the same session**: this bundled
  OMDb plugin's own configuration schema (`GET /Plugins/{id}/Configuration`) exposes only
  `{"CastAndCrew": true}` - no API key field at all, confirmed live rather than guessed. There
  is nothing pending here; the "needs its API key entered" note in earlier drafts of this
  migration was itself wrong.
- **Initially deployed with no `/mnt/nzbdav` mount at all**, unlike every other consumer of a
  root folder's symlinks (Radarr, Sonarr, Unpackerr, Cleanuparr all bind it) - reproduced the
  exact class of bug Stash's first deploy hit (see [Known gaps and limitations](#known-gaps-and-limitations)):
  the scan completed with no error, matched all 418 shows at the series/season level, and
  silently added zero episodes, since every episode file is a symlink into `/mnt/nzbdav` and
  resolved to nothing inside the container. Confirmed live (a sample episode file was a
  dangling symlink, `cat` failed with "No such file or directory") and fixed same-day by adding
  `/mnt/nzbdav:/mnt/nzbdav:rslave` to the compose block, reverified readable, and the library
  rescanned.
- Same VAAPI hardware-transcode device (`/dev/dri/renderD128`) carried over from Plex's config
  - render nodes support concurrent processes, so this is just the sole remaining consumer now.
- `mem_limit: 3g`/`cpus: 6` - starting at parity with Plex's old ceiling (Plex ran `6GB`/`12`),
  not yet tuned down against real observed usage the way every other service's limit in this
  file is (see [Resource limits](#resource-limits)).
- Plugins installed: Playback Reporting, Chapter Segments Provider, TMDb Box Sets (official
  catalog), plus two third-party plugins - Intro Skipper
  (`https://intro-skipper.org/manifest.json`) and a "Bazarr" plugin
  (`https://raw.githubusercontent.com/enoch85/bazarr-jellyfin/main/manifest.json`). All five
  are pending a Jellyfin container restart to actually load - not yet confirmed active.
- The image is a mutable `:latest` channel tag, unlike Plex's old manually-bumped version pin -
  it is **not** excluded from Watchtower's auto-update train the way Plex was (see
  [Image pinning policy](#image-pinning-policy)).

**Kometa cannot talk to Jellyfin at all.** Confirmed directly against
`kometa-team/kometa`'s own `config-schema.json`: no `jellyfin`/`emby` top-level property
exists, only `plex`. Several blog-post sources (jellywatch.app etc.) claiming Kometa supports
Jellyfin are wrong/outdated as of this check; the real state is an open, unimplemented
Jellyfin feature request on Jellyfin's own tracker (features.jellyfin.org/posts/2899). Kometa
and its Quickstart companion were initially just **stopped** (`docker compose stop kometa
quickstart`, config/compose untouched), then, at explicit follow-up request the same session,
**removed entirely**: both compose service blocks deleted, `config/kometa` (901MB) and
`config/quickstart` (469MB) deleted from disk. `config/kometa/config.yml` specifically was
backed up first (`~/backups/removed-configs/kometa-config.yml.bak-2026-07-22`) since, unlike
Plex's own config, it held real third-party credentials with no other copy anywhere - a Trakt
client ID/secret and a GitHub personal access token, plus the OMDb and MDBList API keys, which
were promoted to standalone `.env` secrets (`OMDB_KEY`, `MDBLIST_KEY`) since Control Panel used
to read them live off this file (see [Control Panel](#control-panel) for the new env-var
wiring). **No automated Plex/Jellyfin
collections, overlays, or metadata-enrichment tool of any kind currently runs in this stack.**
See [Automation extras](#automation-extras-cleanuparr-neutarr-unpackerr-watchtower) and
[History](#history) `[11.7.0]`.

**Tautulli was removed entirely** (Plex-only, nothing left to monitor). **Jellystat** replaces
its role for Jellyfin - see [Monitoring extras](#monitoring-extras-jellystat).

**Seerr has been repointed at Jellyfin** - `mediaServerType` switched, admin account
re-linked after a stale-session-cookie false start, and an orphaned Plex user's 144 requests
reassigned before deleting that dead row rather than losing them. See
[Architecture](#architecture) for why this needed a human login step (one media server at a
time, no API-only path).

**Watch history was not migrated.** `qdm12/plex-to-jellyfin`
(`ghcr.io/qdm12/plex-to-jellyfin`) was attempted, then **explicitly abandoned by the user's own
decision** ("don't worry about the watch history") - Jellyfin's libraries start with no
migrated watch history/ratings from Plex. A deliberate, known gap, not an oversight.

### Historical: Plex, removed v11.7.0

Everything below this point describes Plex as it existed before removal - kept as historical
record, same convention as this file's other removed-app sections (Lidarr, Whisparr, the
debrid pipeline). Plex ran as the official `plexinc/pms-docker` image, `network_mode: host`,
with two live libraries at the time of removal:

| Key | Title | Type | Agent | Locations |
|---|---|---|---|---|
| 14 | Movies | movie | `tv.plex.agents.movie` | `/home/bear/Stack/media/movies` |
| 16 | TV Shows | show | `tv.plex.agents.series` | `/mnt/zurg/shows` (dead - see below), `/home/bear/Stack/media/shows` |

`./media` was mounted at its identical host absolute path (`/home/bear/Stack/media`) so every
arr app's writable root folder could be added as a library location directly. Section keys
shifted whenever a library was deleted/recreated - confirmed live 2026-07-17 that this table
had drifted (previously documented as keys 4/1/3/8/10/11, live keys were 14/16, and
`Music`/`Audiobooks` no longer existed as Plex libraries at all - see [History](#history)).

TV Shows carried a dead `/mnt/zurg/shows` Location from the torrent/debrid removal onward -
Zurg's own mount was gone, so it resolved to nothing; not cleaned up via the Plex API
deliberately, since removing a library Location risks Plex offering to delete the underlying
metadata/watch history for content only reachable through it. Moot now that Plex itself is
gone.

**A real, unrelated discovery made while auditing this library before decommissioning it**:
Plex's Movies library was found to only have 59-63 items indexed against ~10,004 real files on
disk. Plex's own `Plex Media Scanner.log` showed a single event on 2026-07-13 (9 days before
the migration) where the scanner removed 661 of 794 tracked items in one pass ("Taking 661
items out of the map... for being unavailable"), with `autoEmptyTrash` confirmed `true` via
`/:/prefs`. This is very likely the missing Plex-side half of this stack's own
"still-unexplained mass Radarr/Sonarr library-loss event" (see
[Known gaps and limitations](#known-gaps-and-limitations)): real files vanished from disk (the
Radarr/Sonarr side), Plex's next scan found the symlinks broken, and `autoEmptyTrash` silently
deleted the corresponding library items. Confirmed *not* caused by the same-day NzbDAV
connection-leak bug - no Plex log activity from 2026-07-22 shows any removal events, only
normal scan/analysis noise. Since Plex is now removed entirely, this can never be root-caused
further; it closes the loop on what was learned, not the underlying uncertainty (the original
Radarr/Sonarr-side file loss still has no confirmed cause, only this newly-found symptom).

### Plex "Anime Movies" and "Anime Shows" libraries (removed)

Added v10.4.0, removed entirely 2026-07-18 along with the rest of this stack's anime support
(Radarr/Sonarr library, Zurg's `anime-shows`/`anime-movies` routing groups,
`rclone-alldebrid-anime`) - see [History](#history) for the full removal and what it touched.

### The retired "Music", "Audiobooks", and "Adult" libraries

**None of these three existed in Plex by the time it was removed.** Only two libraries were
live at that point: Movies, TV Shows (see the table above) - both now carried over to
Jellyfin.

**Plex's "Adult" library was removed in v10.9.9** via the Plex API
(`DELETE /library/sections/{key}`) - a documented, deliberate removal. It was a Movie-type
library pointed at `/mnt/zurg/adult` and (after a fix in v10.5.0) `/home/bear/Stack/media/adult`.
Stash covered this content type's cataloging (performers/studios/tags/StashDB identification)
until it, along with Whisparr (the app that managed this library) and `./media/adult` itself,
was removed entirely in v10.12.0. See [History](#history).

**"Music" and "Audiobooks" are a different story: undocumented removals, root cause unknown.**
This section used to describe both as live libraries (Music, a `tv.plex.agents.music`-agent
library at `/mnt/zurg/music` + `./media/music`; Audiobooks, a Music-type library on the
Plex Personal Media agent at `./media/audiobooks`, always empty by design - Plex has no
audiobook library type). Confirmed live 2026-07-17 that **neither existed anymore** - only 4
Plex sections total, not 6 - with no History entry ever recording either removal. Both
`./media/music` and `./media/audiobooks` still exist on disk (empty) and were never mounted
into any container in `docker-compose.yml`. Most likely tied to Lidarr's final removal in
v10.9.9 (Music was Lidarr's library), but that entry doesn't mention removing the Plex library
itself, only the app - unconfirmed, not chased further. This is the same undocumented-removal
pattern as the Zurg `music`/`books`/`adult` routing groups found the same day (see
[The debrid pipeline: removed](#the-debrid-pipeline-removed) and [History](#history)
`[10.16.0]`) - an app's removal checklist has repeatedly missed cleaning up everything that
depended on it, not just the app itself.

## Bindery and Calibre-Web: retired

Both retired in v10.9.8. The stack currently has no ebook or comic app.

Bindery (`ghcr.io/vavallee/bindery`) replaced Readarr in v10.7.0 as the ebook `*arr`, with
Calibre-Web reading its root folder (`./media/books`) as the reader/library UI. Bindery
tracked zero authors/books the entire time it ran; its Decypharr download-client wiring was
fixed in v10.9.7, but no content ever came in before both services were removed.

`config/calibre-web/` and `config/bindery/` are left on disk.
`CALIBRE_WEB_ADMIN_USERNAME`/`_PASSWORD` were removed from `.env`/`.env.example`.
`control-panel/app.py`'s `CONTAINER_LABELS` and `ARR_LOG_CONTAINERS` no longer list either
service.

Plex had no ebook agent (`/system/agents` listed no book identifier) at the time this was
written; Plex itself was removed entirely in v11.7.0, replaced by Jellyfin (see
[Jellyfin](#jellyfin)) - whether Jellyfin's own library-type/plugin ecosystem changes this
calculus hasn't been checked. Bringing ebooks back would require both a manager and a reader
again regardless of media server.

## Custom formats and quality profiles

Radarr and Sonarr were consolidated to a single quality profile each in v11.2.0, named
**`ANY`** on both apps (not `Unlimited` - renamed as part of that consolidation; see
[History](#history)). Recyclarr (the daily TRaSH-Guides sync that had managed a narrower set
of hygiene custom formats since v10.5.0) was removed entirely in the same pass - there is no
scheduled custom-format sync of any kind on either app anymore; every custom format below is
hand-maintained via each app's API, not templated from an external guide.

Custom format highlights on both apps (not exhaustive - check `GET /api/v3/customformat`
against either app for the full current list):

- **"Block - Sample, Russian, Low-Quality Sources"** (`-10000`, hard reject): sample releases,
  Russian audio/text (including Cyrillic/Hangul Unicode ranges so wrong language metadata
  doesn't slip through), and a blocklist of low-trust sources/groups.
- **"Block: Foreign Audio w/o English Subs"** (`-10000`, added v11.3.0): matches when audio
  language is not English *and* the release title carries no subtitle-availability tag
  (`ENG SUB`, `MULTI...SUB`, `ENGDL`, etc). A release-title-regex approximation, not a
  substitute for Bazarr actually managing subtitles post-download - see
  [Bazarr](#bazarr-subtitle-management) for why neither app can do better than this
  pre-download.
- **"Prefer Season Packs"** (Sonarr only, `+25`, re-added v11.3.0 after being lost in v11.2.0's
  profile consolidation): `ReleaseTypeSpecification` = Season Pack, so Sonarr favors a season
  pack over single/multi-episode releases when both are available.
- All anime-specific custom formats (BD/Web tier ladders, fansub versioning, dual-audio,
  anime-exclusive streaming services) were removed from both apps in the same v11.3.0 session,
  following the anime library removal itself (v10.19.0) - the CF definitions had outlived the
  content they scored.

Check what a release title scores with each app's parse endpoint:

```bash
curl -s -H "X-Api-Key: $RADARR_API_KEY" \
  "http://192.168.4.105:7878/api/v3/parse?title=Movie.Name.2024.1080p.WEB-DL.RUS" | \
  jq '.customFormats, .customFormatScore'
```

## Automation extras: Cleanuparr, NeutArr, Unpackerr, Watchtower

**Kometa and its Quickstart companion were removed entirely in v11.7.0** (a follow-up to the
same version's Plex-to-Jellyfin migration - see [Jellyfin](#jellyfin) and
[History](#history) `[11.7.0]` for the full removal). Kometa (`kometateam/kometa@sha256:98a0df...`)
used to automate Plex collections, metadata, and overlay art as a scheduled batch job
(05:00 daily by default), connected to Plex, TMDb, Radarr, Sonarr, Tautulli, and Trakt;
Quickstart (`kometateam/quickstart:latest`, port 7171) was the official Kometa-Team wizard for
building its `config.yml` interactively. Both were evaluated for Jellyfin support and found
incompatible - `kometa-team/kometa`'s own `config-schema.json` has no `jellyfin`/`emby`
top-level connection property, only `plex` (several blog-post sources, e.g. jellywatch.app,
claiming otherwise are wrong/outdated; real Jellyfin support is an open, unimplemented feature
request at features.jellyfin.org/posts/2899) - so both were stopped first, then removed
entirely at explicit follow-up request the same session: compose service blocks deleted,
`config/kometa` (901MB) and `config/quickstart` (469MB) deleted from disk. **No automated
Plex/Jellyfin collections, overlays, or metadata-enrichment tool of any kind currently runs in
this stack.**

**Cleanuparr** (`ghcr.io/cleanuparr/cleanuparr:2.9.16`, port 11011) and **NeutArr**
(`iampuid0/neutarr:1.9.1`, port 9705) automate what Control Panel's "unstick" and
"search missing" actions do by hand. Roles are split: Cleanuparr owns strikes (3-strike
failed-import detection), an hourly-checked community malware blocklist, and
stalled-download cleanup; NeutArr owns missing-content/quality-upgrade hunting. Cleanuparr's
built-in proactive search stays disabled so the two do not hunt the same libraries
redundantly. NeutArr is wired to Sonarr and Radarr, each instance's URL/API key set in
`config/neutarr/{sonarr,radarr}.json` (a host bind mount at `/config`; NeutArr's own
"Apps" settings page writes the same files). `readarr.json` is present but
`"enabled": false`, a leftover from before the Bindery swap; `lidarr.json` was deleted with
Lidarr in v10.9.9. `eros.json` (Whisparr's real slot) had its real credentials deleted when
Whisparr was removed in v10.12.0, same as `lidarr.json` — but unlike `lidarr.json`, NeutArr
regenerates both `eros.json` and the pre-existing orphaned `whisparr.json` on every restart
with blank credentials, the same inert-placeholder pattern already documented below for the
original orphaned file. Deleting them again is cosmetic; they can never actually connect.

> **NeutArr, not Huntarr.** NeutArr is a fork tracing through `elfhosted/newtarr`'s fork of
> Huntarr v6.6.3, the last release before Huntarr's maintainer suppressed reports of an
> unauthenticated auth-bypass that leaked every connected `*arr` app's API keys in cleartext,
> then took the repo private and banned users raising the issue. Do not add Huntarr proper to
> this stack.

Notes on wiring found and fixed live: a service can be connected at the compose level and
still not registered inside the app it talks to. Cleanuparr's `arr_instances` table once had
only Sonarr and Radarr connected while Lidarr and Whisparr had config-type placeholders but
no instance, so queue-cleaning and strikes were not covering them; both were added via its
**Settings > Add Instance** UI. When each was removed (Lidarr in v10.9.9, Whisparr in
v10.12.0), its stale row was deleted directly in SQLite (no REST endpoint exists for that
table; the container was stopped first to avoid a live WAL-mode write, zero orphaned rows in
every referencing table confirmed before deleting). Prowlarr's application-sync entry for
each was deleted via its own API in the same pass. When auditing "is X wired to Y," check the
receiving app's own config or API for a real instance entry, not just network reachability.

**Unpackerr** (`golift/unpackerr@sha256:4ec141...`) auto-extracts RAR'd releases for the
two `*arr` apps:

```yaml
UN_RADARR_0_URL: http://radarr:7878
UN_RADARR_0_API_KEY: ${RADARR_API_KEY}
# ...same pattern for sonarr. UN_LIDARR_0_* was removed in v10.9.9,
# UN_WHISPARR_0_* in v10.12.0.
```

It needs each app's actual `/app/downloads/...` path mounted, not just `/mnt`: the archives
live at the path each app's queue reports as `outputPath`, not the resolved symlink target.

**Watchtower** (`nickfedor/watchtower:1.19.0`; the maintained fork; `containrrr/watchtower`
is archived and its bundled Docker client is too old for this host's Engine API version)
auto-updates the channel-tag-pinned images daily at 4am, posting every update or failure to
Discord via Shoutrrr:

```yaml
WATCHTOWER_SCHEDULE: "0 0 4 * * *"
WATCHTOWER_NOTIFICATIONS: "shoutrrr"
WATCHTOWER_NOTIFICATION_URL: ${DISCORD_WATCHTOWER_SHOUTRRR_URL}
```

Digest-pinned images (Seerr, Unpackerr) and exact-version-tag-pinned ones
(Watchtower itself) are not auto-updated: a digest or exact tag is
immutable, so Watchtower never finds anything new. Plex used to be in this excluded group too
(a manually-bumped version tag, deliberately kept off the train); Jellyfin, which replaced it
in v11.7.0, does **not** carry that exception forward - `lscr.io/linuxserver/jellyfin:latest`
is a mutable channel tag, so Watchtower auto-updates it same as any other channel-tag image
unless that's deliberately changed. See [Image pinning policy](#image-pinning-policy).

## Monitoring extras: Jellystat

**Tautulli was removed entirely** (`ghcr.io/hotio/tautulli:release`, formerly port 8182: Plex
watch-history/stats dashboard). **Plex was removed entirely in v11.7.0** (see
[Jellyfin](#jellyfin) and [History](#history)) - Tautulli is Plex-only, so it was initially
left orphaned pointed at a media server that no longer existed, then fully removed on
follow-up request the same session: compose block, `config/tautulli/` (263MB, no credentials
of note, deleted with no backup), and its `control-panel/app.py` container-listing entry all
gone. Its two `/api/tautulli/*` routes (history, stats) were left as documented dead code
(unlike the former `/api/plex/*` routes, which have since been fully reworked against
Jellyfin's API, see [History](#history) `[11.7.0]`) - they already 503 gracefully once
`config/tautulli/config.ini` no longer exists, and Jellystat already covers the same role.

**Jellystat** (`cyfershepard/jellystat:latest`, port 8087, plus its own Postgres,
`jellystat-db` on `postgres:18.1`) was added the same version as Tautulli's Jellyfin-
equivalent - Tautulli has no Jellyfin support at all. This reintroduces a Postgres dependency
to the stack for the first time since `zilean-postgres` was removed in v11.0.0 (see
[The debrid pipeline: removed](#the-debrid-pipeline-removed)); **`jellystat-db` currently has
zero backup coverage** - it has no logical `pg_dump` step of its own yet, and restic's
raw-datadir exclusion doesn't cover a live Postgres datadir safely. A known, outstanding gap,
not yet fixed - see [Backups](#backups). Both containers are now up and healthy, after fixing
two first-start bugs (see [History](#history) `[11.7.0]`): `postgres:18+` crash-looped against
the usual `./config/jellystat-db:/var/lib/postgresql/data` mount convention ("PostgreSQL data
in an old, unsupported location" - 18+ manages its own version-specific subdirectory under a
single `/var/lib/postgresql` mount), fixed by mounting `/var/lib/postgresql` directly instead;
`jellystat`'s own healthcheck (`curl -sf http://localhost:3000/`) failed every time because the
image has no `curl`, only `wget` - fixed by switching the test to
`wget -qO- http://localhost:3000/ >/dev/null 2>&1 || exit 1`. Jellystat's own first-run setup
is **complete** - confirmed directly via `jellystat-db`'s `app_config` table (real
`JF_HOST`/`JF_API_KEY`, admin user matching Jellyfin's real user ID, sync tasks scheduled) and
a populated `jf_library_items` table (7,799 rows synced), not just assumed from the containers
being up.

Glances and Dozzle were removed in v10.9.9 (neither had a config volume, so no data was
involved). Glances powered Control Panel's Overview "Host CPU/memory/disk/uptime" tiles via
`/api/system/stats`; that endpoint and those tiles were removed with it. Control Panel's
per-app log tailing (`/api/arr/{app}/logs`) never depended on Dozzle. A Prometheus + Grafana
stack was researched the same version and cancelled before anything was built.

Adminer was removed in v10.9.9 with no replacement (a same-day CloudBeaver swap was
reverted). There is no web DB GUI; `zilean-postgres`, its one-time subject, was itself removed
along with the rest of the debrid layer (see [History](#history)) - no Postgres instance runs
in this stack anymore.

## Bazarr: subtitle management

**Bazarr** watches Radarr/Sonarr for missing subtitles and downloads them from whichever
configured providers have them. Removed entirely in v10.2.0; reinstalled from scratch in
v11.3.0 (see [History](#history)) - no prior `config/bazarr` state to restore.

```yaml
# docker-compose.yml
bazarr:
  image: ghcr.io/hotio/bazarr:release
  volumes:
    - ./config/bazarr:/config
    - ./media/movies:/data/movies
    - ./media/shows:/data/shows
  ports:
    - "6767:6767"
```

Radarr/Sonarr connections and every other setting go through Bazarr's
own settings endpoint, not environment variables - and unlike most of this stack's other
apps, that endpoint isn't in Bazarr's own published Swagger spec (`/api/swagger.json`); it's
`POST /api/system/settings`, form-encoded, undocumented because it's meant for Bazarr's own
frontend rather than external API consumers. Two gotchas worth keeping in mind before touching
this again: boolean fields need lowercase `true`/`false` strings (`True`/`False` fails
dynaconf's type validator with a misleading `"must is_type_of bool but it is True"` error), and
array-valued fields (`enabled_providers` among them) need one repeated form key per value, not
a single comma/space-joined string - trivial with `curl --data-urlencode` called once per
value, but easy to get wrong from a shell that doesn't word-split unquoted variables the way
you expect (this host's interactive shell is zsh, not bash - `for p in $PROVIDERS` silently
does *not* split on whitespace there without `${=PROVIDERS}` or an actual array).

```bash
curl -X POST -H "X-API-KEY: $BAZARR_API_KEY" http://localhost:6767/api/system/settings \
  --data-urlencode "settings-general-use_sonarr=true" \
  --data-urlencode "settings-sonarr-ip=sonarr" \
  --data-urlencode "settings-sonarr-port=8989" \
  --data-urlencode "settings-sonarr-apikey=$SONARR_API_KEY" \
  --data-urlencode "settings-general-enabled_providers=gestdown" \
  --data-urlencode "settings-general-enabled_providers=yifysubtitles" \
  --data-urlencode "languages-enabled=en" \
  --data-urlencode 'languages-profiles=[{"profileId":1,"name":"English","cutoff":null,
    "items":[{"id":1,"language":"en","forced":"False","hi":"False","audio_exclude":"False"}],
    "mustContain":[],"mustNotContain":[],"originalFormat":null,"tag":null}]'
```

Bazarr's own API key lives in `config/bazarr/config/config.yaml` under `auth.apikey`,
auto-generated on first boot - there's no env var for it.

**Reconfigured for Jellyfin in v11.7.0**, through the same undocumented endpoint above: real
field names verified against Bazarr's own live `GET /api/system/settings` response first
(rather than trusting the Bazarr wiki's paraphrased docs) -
`general.use_jellyfin=true`, `jellyfin.url=http://jellyfin:8096`,
`jellyfin.apikey`, movie/series libraries mapped by name and Jellyfin's real library IDs
(`jellyfin.movie_library`, `jellyfin.movie_library_ids`, `jellyfin.series_library`,
`jellyfin.series_library_ids`), `jellyfin.refresh_method`,
`jellyfin.update_movie_library`/`update_series_library=true`. `general.use_plex` set to
`false` in the same pass - Plex is gone.

**Provider selection**: only providers that need zero account/API key/passkey are enabled (39
of Bazarr's ~65 bundled providers - the full list and exclusion reasoning is in the v11.3.0
[History](#history) entry). This is a deliberate ceiling, not an oversight - adding any
excluded provider means creating an account/API key with that service first, which is a
per-provider decision this repo doesn't make on your behalf.

**What this does and doesn't cover**: Bazarr downloads real subtitle files after a movie/
episode already exists on disk. It has no way to influence what Radarr/Sonarr grab in the
first place - that's what the "Block: Foreign Audio w/o English Subs" custom format (both
apps' quality profiles, see [The *arr apps](#the-arr-apps)) is for, and that CF is a
release-title-regex approximation for exactly the reason Bazarr exists: neither app can see
actual embedded subtitle tracks before a release is grabbed.

## Control Panel

`control-panel/`: a custom FastAPI app (`build: ./control-panel`, not a pulled image), the
single dashboard for this stack. Live container status/control, one-click ops actions, and
per-app queue tools. Port **8420**. Its addition allowed Heimdall and Homepage to be removed;
see [History](#history).

### API surface

```python
# control-panel/app.py - the ARR_APPS dict the panel is built around.
ARR_APPS = {
    "radarr":  {"url": "http://radarr:7878",   "api": "v3", "search_command": "MissingMoviesSearch"},
    "sonarr":  {"url": "http://sonarr:8989",   "api": "v3", "search_command": "MissingEpisodeSearch"},
}
QUEUE_ARR_APPS = ("radarr", "sonarr")
```

| Endpoint | Method | What it does |
|---|---|---|
| `/healthz` | GET | Liveness probe (used by the container's healthcheck) |
| `/api/status` | GET | Running/health state for every container in the compose project |
| `/api/containers` | GET | Full grid: state, health, image, live CPU/mem per container |
| `/api/api-hit-counts` | GET | Live per-app outbound API call counter (see below) |
| `/api/jellyfin/scan` \| `/optimize-db` | POST | Jellyfin maintenance actions - no `empty-trash`/`clean-bundles` equivalent exists, dropped entirely (see below) |
| `/api/jellyfin/libraries` | GET | Library names/keys, read live from Jellyfin |
| `/api/jellyfin/deep-analysis` | POST | Chapter images + trickplay + Intro Skipper detection + audio normalization, every library at once |
| `/api/jellyfin/task/{task}` | POST | Fires one named Jellyfin scheduled task (see below for the full mapping) |
| `/api/jellyfin/updates` | GET | Running Jellyfin version (update-checking itself is Watchtower's job for this image, see below) |
| `/api/jellyfin/duplicates` | GET | Movie libraries only; flags items whose combined file size looks like redundant duplicate releases |
| `/api/jellyfin/tmdb-missing` | GET | Every movie/show across every library with no TMDb link (see `scripts/audit-tmdb-links.py`) |
| `/api/jellyfin/sessions` | GET | Who's watching what right now, direct play vs transcode |
| `/api/jellyfin/recently-added` | GET | Most recently added items across Jellyfin's movie/show libraries |
| `/api/posters/libraries` | GET | Movie/show libraries only, for the poster sync picker (see below) |
| `/api/posters/sync` | POST | `{"library": "...", "dry_run": bool}` → starts a poster sync, one job at a time |
| `/api/posters/sync/stream` | GET | SSE progress feed for the running (or just-finished) poster sync |
| `/api/container/{name}/logs/stream` | GET | SSE live-follow of a container's own `docker logs`, any container in the project |
| `/api/nzbdav/queue` \| `/history` | GET | NzbDAV's current queue / recent history |
| `/api/nzbdav/set-connections` | POST | `{"max_connections": N}` → sets every configured Usenet provider's max connections |
| `/api/arr/{app}/rss-sync` \| `/search-missing` | POST | Per-app RSS sync / missing-search |
| `/api/arr/{app}/unstick` | POST | Removes + blocklists + re-searches every `warning`/`error` queue item |
| `/api/arr/{app}/unstick-importing` | POST | Diagnoses a download wedged in `importing` state (dead-article/missing-path check via `docker exec`), clears or blocklists, re-searches |
| `/api/arr/{app}/manual-import` | GET/POST | Lists importable files across stuck queue items; POST executes one |
| `/api/arr/{app}/manual-import-all` | POST | Bulk-imports every candidate the GET lists |
| `/api/arr/{app}/missing-aired` | GET | Monitored + no file + already-aired (see [The *arr apps](#the-arr-apps)) |
| `/api/container/{name}/start` \| `/stop` \| `/restart` | POST | Individual container control, validated against the live compose project |
| `/api/stack/restart-all` | POST | Restarts everything except itself, mount providers first (see below) |

**`/api/kometa/run` was deleted outright when Kometa was removed entirely in v11.7.0** (its
`KometaRunRequest` Pydantic model went with it) - unlike the old `/api/plex/*` routes, there
was no missing-env-var 503 fallback for it to degrade into, since none was ever built; calling
this endpoint now 404s, it simply no longer exists.

**All 14 former `/api/plex/*` routes were reworked against Jellyfin's real API, same overall
migration effort** (see [History](#history) `[11.7.0]` for the full route-by-route mapping and
what changed under the hood - `jellyfin_headers()`'s `X-Emby-Token` header, task-triggering by
looking up a task's real Id via its Key rather than guessing an endpoint shape, Jellyfin's lack
of a per-library analyze scope forcing `/api/plex/analyze` and the old
`/api/plex/butler/deep-media-analysis` to consolidate into one `/api/jellyfin/deep-analysis`
call, etc). Two Plex-only concepts had no Jellyfin equivalent at all and were dropped entirely
rather than approximated: `empty-trash` (no per-library trash concept in Jellyfin) and
`clean-bundles` (no per-item "bundle" directory scheme). The poster-sync routes
(`/api/posters/*`) were reworked the same way - TMDb matching now keys off Jellyfin's
`ProviderIds` instead of Plex's Guid array, and the actual image write is
`POST /Items/{id}/Images/Primary` with raw bytes instead of Plex's URL-fetch endpoint - both
verified live via a real dry-run against the Movies library, not just read for syntax.

### Live API hit counter

Container cards for apps the panel talks to over HTTP (Radarr, Sonarr, Jellyfin, NzbDAV) show a
running count of outbound calls since the panel last started. Cosmetic only: in-memory
`Counter`, resets on restart, no persistence, no per-endpoint breakdown. The old `Plex` label
was replaced with `Jellyfin` as part of the same route rework above (see [Jellyfin](#jellyfin))
- it counts real outbound Jellyfin API calls now, not stuck at zero.

```python
# control-panel/app.py - wraps httpx.request itself rather than touching
# every call site individually
API_HIT_COUNTS = Counter({label: 0 for label in _API_HOST_LABELS.values()})
_httpx_request = httpx.request

def _counted_request(method, url, *args, **kwargs):
    host = urlparse(str(url)).hostname
    API_HIT_COUNTS[_API_HOST_LABELS.get(host, host or "unknown")] += 1
    return _httpx_request(method, url, *args, **kwargs)

httpx.request = _counted_request
httpx._api.request = _counted_request
```

Two implementation notes:

- Reassigning `httpx.request` alone is a silent no-op. `httpx.get`/`post`/etc. resolve
  `request` against `httpx._api`'s module globals, not `httpx`'s top-level namespace
  (`httpx.get.__globals__ is httpx.__dict__` is `False`). Patch `httpx._api.request`.
- `/api/containers` originally took 60-90+ seconds: each `container_stats()` call blocks
  ~1-2s (the Docker Engine API takes an internal two-sample delta regardless of
  `stream=False`), and the endpoint called it sequentially across every container. Fixed
  with a `concurrent.futures.ThreadPoolExecutor` (`max_workers` capped at 16); latency
  dropped to ~6s, bound by the slowest single container.

### Poster sync: TMDb posters over Plex's own

**Currently non-functional as of v11.7.0** - this feature reads/writes Plex's own Guid and
poster-upload API directly, and `PLEX_URL`/`PLEX_TOKEN` no longer exist in `.env` since Plex
was replaced by Jellyfin (see [Jellyfin](#jellyfin)). Not yet reworked against Jellyfin's
equivalent API. Description below is of the Plex-era implementation, kept for reference.

Replaces a movie/show's Plex poster with TMDb's top-voted one, matched via the item's own
`tmdb://` Guid (falling back to TMDb's `/find` endpoint against a `tvdb://`/`imdb://` Guid for
items still on an older agent match). ThePosterDB was considered and ruled out - its
[Terms of Service](https://theposterdb.com/terms) explicitly forbid automated scraping and it
has no public API, so there is no ToS-compliant way to pull from it programmatically. TMDb is
a real, documented, keyed API (`TMDB_KEY`).

One job at a time, in-memory only (`POSTER_SYNC_STATE`, no persistence across a panel
restart); a second sync request while one is running gets a 409. Progress streams to
`/api/posters/sync/stream` over SSE, the same single-shared-queue tradeoff as the container
log stream below - fine for a one-operator LAN dashboard, not for multiple simultaneous
viewers expecting independent progress. A `dry_run` flag reports what would change without
uploading anything.

### Whole-stack restart: mount-order aware

**Reworked as of v11.7.0**: `MOUNT_DEPENDENTS` now reads `{"radarr", "sonarr", "jellyfin",
"unpackerr", "cleanuparr"}` - `plex` replaced with `jellyfin`, confirmed correct now that
Jellyfin's own missing `/mnt/nzbdav` mount (see [Jellyfin](#jellyfin)) has been found and
fixed, making it a real FUSE-mount dependent like the rest of this set.

```python
# control-panel/app.py
MOUNT_PREREQS = {"nzbdav"}
MOUNT_PROVIDERS = {"nzbdav-rclone"}
MOUNT_DEPENDENTS = {"radarr", "sonarr", "plex", "unpackerr", "cleanuparr"}

def worker():
    for c in prereqs: c.restart(timeout=30)
    for c in prereqs: wait_for_healthy(c)
    for c in providers: c.restart(timeout=30)
    for c in providers: wait_for_healthy(c)
    for c in rest: c.restart(timeout=30)
    for c in dependents: c.restart(timeout=30)   # mount dependents last, after the mount is healthy
```

```bash
curl -X POST http://192.168.4.105:8420/api/stack/restart-all
```

This exists because a direct subpath bind of `/mnt/nzbdav` (`rslave`) does not reliably
survive the FUSE process underneath it being recreated: restarting a dependent before its
mount provider is healthy reproduces that bug. Confirmed live 2026-07-18 during the
torrent/debrid removal - recreating `nzbdav-rclone` and its five dependents in the same batch
(rather than sequenced through this exact logic) left every dependent unable to start at all
(`transport endpoint is not connected`) until `nzbdav-rclone` was restarted alone first and
the stale host-level mount was cleared with `sudo umount -l /mnt/nzbdav`. `MOUNT_DEPENDENTS`
grew from just `{"radarr"}` to its current five-service set the same day, once Sonarr, Plex,
Unpackerr, and Cleanuparr all switched from a blanket `/mnt` bind to the same narrow
`/mnt/nzbdav` subpath bind Radarr already used (see [Architecture](#architecture)) - the same
fragility now applies to all five, not just Radarr.

`nzbdav-rclone` needs its own prereq wave, not just a spot in `MOUNT_PROVIDERS`. It owns the
`/mnt/nzbdav` FUSE mount, but its rclone remote talks to `nzbdav`'s API
(`depends_on: nzbdav: condition: service_healthy` in compose), and this hand-rolled restart
loop does not read the compose dependency graph. Originally `nzbdav-rclone` was not in
`MOUNT_PROVIDERS` at all; during a full stack outage, `/mnt/nzbdav` was left stale at the
host level (`Transport endpoint is not connected`, dead backing process in the host mount
table), and recovery required `sudo umount -l /mnt/nzbdav` on the host. `MOUNT_PREREQS`
restarts `nzbdav` first and waits for healthy before the `MOUNT_PROVIDERS` wave starts.

### Security: CSRF/Origin-Host validation, not auth

```python
# control-panel/app.py
ALLOWED_HOSTS = {h for h in (HOST_IP, "localhost", "127.0.0.1") if h}

@app.middleware("http")
async def verify_same_origin(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        host = (request.headers.get("host") or "").split(":")[0]
        if host not in ALLOWED_HOSTS:
            return JSONResponse(status_code=403, content={"ok": False, "message": "..."})
        # ...same check against the Origin header if present
```

Not a login gate (see [Security](#security)). It closes a gap where any website a LAN browser
visits could fire a same-origin-exempt POST at this panel's docker.sock-backed
start/stop/restart/exec endpoints.

## CLI: the `stack-*` fish functions

A terminal interface to Control Panel's API, tracked in `~/.dotfiles`
(`.config/fish/functions/`), built on one private helper:

**Every `stack-plex-*`/`stack-kometa-*`/`stack-tautulli-*` command has been reworked or removed
as of v11.7.0** (see [History](#history) `[11.7.0]`) - every Plex maintenance command has a
`stack-jellyfin-*` equivalent against the routes in [Control Panel](#control-panel) above;
commands backing a dropped Plex-only concept (empty-trash, Plex-watchlist/RSS import, and
every individual Butler-task wrapper with no real Jellyfin task behind it) were deleted
outright rather than left dead; `stack-kometa-run` and both `stack-tautulli-*` commands were
deleted (both apps removed entirely, no Jellyfin-side equivalent for either).

```fish
# ~/.dotfiles/.config/fish/functions/__stack_api.fish
# Usage: __stack_api METHOD PATH [JSON_BODY]
function __stack_api
    set -l host_ip 192.168.4.105
    curl -sS -X $method -w '\n%{http_code}' "http://$host_ip:8420$path" | python3 -c "..."
end
```

```fish
stack-status                                    # live health of every container
stack-arr radarr rss-sync                       # radarr/sonarr; or search-missing / unstick / unstick-importing
stack-arr-import-candidates sonarr              # list files ready to manually import
stack-arr-import sonarr 0                       # import candidate #0 from the list above
stack-jellyfin scan                             # or optimize-db
stack-jellyfin-libraries                        # list Jellyfin library names
stack-nzbdav-queue                              # current Usenet download queue
stack-nzbdav-history 20                         # recent history, default limit 20
stack-nzbdav-set-connections 50                 # set the Usenet provider's max connections
stack-container restart radarr                  # or stop / start
stack-restart-all -y                            # skip the interactive confirm prompt
```

`stack-arr`, `stack-arr-import-candidates`, and `stack-arr-import` accept
`radarr`/`sonarr`, matching Control Panel's `/api/arr/{app}/...` endpoints and
`QUEUE_ARR_APPS`:

```fish
# ~/.dotfiles/.config/fish/functions/stack-arr.fish
function stack-arr --description 'Trigger an *arr app maintenance action'
    if not contains -- $argv[1] radarr sonarr
        echo "Unknown app '$argv[1]' - use radarr or sonarr." >&2
        return 1
    end
    ...
```

Diagnostic/action commands added after a live resource+wiring audit (see [History](#history),
v10.9.6):

```fish
stack-resource-check                            # containers missing mem_limit/cpus
stack-log-levels                                # or `reset` to set every debug app back to info
stack-mount-health                              # every known FUSE mountpoint, checked for a stale one
stack-oom-check                                 # containers Docker has recorded an OOM-kill for
stack-perms-check                               # config files unreadable by group/other
stack-backup-verify                             # latest snapshot age, local + off-site repos
stack-backup-restore-test                       # actually restores one file, confirms restores work
stack-cleanuparr-instances                      # which *arr apps Cleanuparr actually has connected
stack-neutarr-status                            # per-app enabled state from NeutArr's own config
stack-arr-logs radarr 200                       # tail a container's log directly
stack-plex-empty-trash "TV Shows"               # scoped to one library, or every library if none given
stack-plex-analyze "TV Shows"                   # queue deep media analysis, scoped to one library or all
stack-plex-butler deep-media-analysis           # fire any one Plex Butler task on demand (see full list below)
stack-image-check                               # digest/exact-version-pinned images vs their registry
stack-disk-usage                                # per-app config/ directory size, largest first
stack-version                                   # README's declared version + live container count
```

Added in v10.9.8:

```fish
stack-plex-updates                              # check for a Plex update (check only, doesn't apply it)
stack-arr-import-all sonarr                     # import every stuck queue file in one go, not just one
stack-arr-missing-aired sonarr                   # monitored + missing + already aired/released
```

Added in v10.10.0 (Letterboxd-to-Radarr, no extra container; each film-page fetch scrapes the
TMDb id Letterboxd links in its sidebar; list/grid variants scrape every poster's
`data-item-slug`, max 10 pages / 720 films, and bulk-add whatever isn't already in Radarr):

```fish
stack-letterboxd-radarr https://letterboxd.com/film/inception/
stack-letterboxd-radarr-list https://letterboxd.com/<user>/list/<slug>/
stack-letterboxd-radarr-watchlist https://letterboxd.com/<user>/watchlist/
stack-letterboxd-radarr-watched https://letterboxd.com/<user>/films/
stack-letterboxd-radarr-filmography actor tom-hanks       # or director / writer / any crew role
stack-letterboxd-radarr-collection https://letterboxd.com/films/in/<collection>/
stack-letterboxd-radarr-popular                            # currently always empty, see History
```

All seven accept `--no-search` (skip triggering a download search), `--no-monitor`,
`--dry-run` (report what would be added, write nothing), and (list variants) `--limit N`.

**Ratings and MDBList list import — added in v10.11.0.** Both OMDb and MDBList API keys used to
be read live from Kometa's own `config.yml`; since Kometa's removal in v11.7.0 (see
[History](#history) `[11.7.0]`) they're real standalone `.env` secrets instead - `OMDB_KEY`,
`MDBLIST_KEY` - read directly via `os.environ.get(...)` in `control-panel/app.py`, replacing
the deleted `_kometa_config()` helper.

```fish
stack-rating-imdb tt1375666
# "Inception" (2010): 8.8/10 (2,811,614 votes)

stack-rating-mdblist tt1375666
# "Inception" (2010): MDBList score 86/100, IMDb 8.8/10 (2833257 votes)

stack-mdblist-import https://mdblist.com/lists/<user>/<list-name>
# Radarr: 3 added, 12 already present, 0 failed; Sonarr: 1 added, 4 already present, 0 failed
```

`stack-rating-imdb`/`stack-rating-mdblist` each take one IMDb id (`tt...`) and print that
title's rating - use `stack-rating-imdb` for the plain IMDb score/vote count, or
`stack-rating-mdblist` for MDBList's own aggregate score plus its IMDb sub-rating in one call.

`stack-mdblist-import` takes any public MDBList list URL
(`https://mdblist.com/lists/<user>/<list-name>`) and, in one call, adds every movie in it to
Radarr and every TV show to Sonarr - MDBList's own API already returns items split into
`movies`/`shows` arrays with `imdb_id`/`tvdb_id`/`tmdb_id` attached, so no scraping or
media-type guessing is needed on this end (unlike the Letterboxd commands, which have to infer
everything from an HTML poster grid). It accepts the same `--no-search`, `--no-monitor`,
`--dry-run`, and `--limit N` flags as the Letterboxd list commands above - always dry-run a new
list first to see what it would do:

```fish
stack-mdblist-import https://mdblist.com/lists/<user>/<list-name> --dry-run --limit 10
```

Direct IMDb list import (pasting an `imdb.com/list/ls.../` URL directly) isn't supported and
isn't planned - IMDb's list and CSV-export pages sit behind a real AWS WAF JS challenge
(confirmed live: the response carries an `x-amzn-waf-action: challenge` header), the same class
of problem as Letterboxd's Cloudflare-gated pages, just on Amazon's infrastructure instead. If
you specifically want IMDb-sourced content, search MDBList itself for a mirror - e.g.
`https://mdblist.com/lists/adamosborne01/imdb-top-250` is a community-maintained, fully working
copy of the IMDb Top 250 reachable through the exact same `stack-mdblist-import` command above.

The full CLI (~60 commands) lives entirely in this host's own `~/.config/fish/functions/`,
backed by `control-panel/app.py` in this repo - no public mirror. A standalone redistributable
version (`StackScripts`, later merged into `StackMaster`) existed at points in this project's
history but was deleted outright from GitHub as of 2026-07-21, for privatization - see
`AGENTS.md`. There is currently no downstream repo to keep in sync.

## Backups

`./config` holds every app's settings, database, and plaintext API keys. None of it is in
git, and it is not reproducible by re-running `docker compose up` or re-pulling images.

- **`scripts/backup-config.sh`**: `restic backup ./config`, then `restic forget --prune`
  (`--keep-daily 7 --keep-weekly 4 --keep-monthly 6`). Repo at `~/backups/stack-restic-repo`,
  restic-encrypted. Run daily at 03:30 by `systemd/stack-backup.timer`, before Watchtower's
  4am updates. An off-site leg mirrors the same backup to any restic-supported remote
  (`BACKUP_REMOTE_REPOSITORY` in `.env`) with its own retention pass, Discord tag, and a
  monthly `restic check --read-data-subset=10%` integrity check on the 1st, same as the local
  repo. Used to also do a logical `pg_dump` of `zilean-postgres` before the restic run - that
  step (and the whole database) was removed along with the rest of the debrid layer (see
  [History](#history)). Any future DB-backed service needs its own logical-dump step added
  back; excluding a raw datadir from restic alone drops it from coverage entirely.
- **Excluded from restic**: every app's `logs`/`log` directory. Several regenerable Plex
  subdirectory exclusions (`Metadata` - 28GB of re-fetchable posters/art, `Cache`, `Codecs`,
  `Logs`, `Crash Reports`, plus `plex-transcode`) are moot as of v11.7.0 - `config/plex/` and
  `config/plex-transcode/` were deleted outright along with Plex itself (see
  [History](#history)), at the user's explicit request, no archive kept. This restic exclusion
  list still references those now-nonexistent paths; harmless (excluding a path that doesn't
  exist is a no-op), but worth pruning next time `scripts/backup-config.sh` is touched.
- **`scripts/arr-app-backup.py`** + `systemd/stack-arr-backup.timer` (daily, 03:40): triggers
  each `*arr` app's native `Backup` command, producing the portable `.zip` each app's own
  restore flow expects:
  ```bash
  curl -X POST -H "X-Api-Key: $RADARR_API_KEY" -H "Content-Type: application/json" \
    -d '{"name":"Backup"}' http://192.168.4.105:7878/api/v3/command
  ```
- **`scripts/backup-claude-dir.sh`** + `systemd/stack-claude-backup.timer` (nightly,
  midnight): a full `tar --zstd` snapshot of the entire `~/Claude` directory to
  `~/Dropbox/Claude-backup-latest.tar.zst`, overwritten in place each run, no retained
  history. Needs passwordless `sudo` (the tree includes container-owned files). This is not
  the stack's off-site protection: one run has failed outright (4h41m, exit 1, no output
  file) with no earlier copy to fall back on. It is a coarse convenience snapshot; the
  restic off-site leg above is the disaster-recovery mechanism.
- This host has a single physical disk (one NVMe). The local restic repo protects against
  config corruption and accidental deletion, not disk failure. The off-site leg is a second
  restic repository inside the host's Dropbox sync folder
  (`~/Dropbox/stack-restic-repo-offsite`); Dropbox's client handles the replication, no new
  cloud account or `rclone` install needed. Same password file as the primary repo
  (`BACKUP_REMOTE_PASSWORD_FILE` unset falls back to `~/backups/.restic-password`).

Verify anytime:

```bash
RESTIC_PASSWORD_FILE=~/backups/.restic-password restic -r ~/backups/stack-restic-repo snapshots
# off-site leg:
RESTIC_PASSWORD_FILE=~/backups/.restic-password restic -r ~/Dropbox/stack-restic-repo-offsite snapshots
```

Note: restic exit code 3 (some files unreadable/locked) is treated as a soft warning that
still allows pruning, not a hard failure. Alerting keyed only on error-level restic output
will miss a recurring partial-backup problem that never escalates past exit code 3.

## Alerting (Discord)

One webhook (`DISCORD_WEBHOOK_URL` in `.env`) backs several independent alert paths, all
through `scripts/notify-discord.sh` (no-ops silently if unconfigured):

- **Backups**: success/warning/failure from `backup-config.sh`, plus an `OnFailure=` systemd
  hook as a second layer for failures the script cannot self-report.
- **Watchtower**: every image update (or failed update) posts before it happens, via Shoutrrr
  (`discord://<token>@<id>` format, a separate URL from the plain webhook the others use).
- **Container health**: `scripts/check-container-health.sh`, every 5 minutes, diffs the
  unhealthy/restarting container set against its last poll and only posts on a change.
- ~~**Plex additions**: `scripts/plex-webhook-listener.py`~~ **Removed entirely in v11.7.0**
  along with Plex itself: the listener script, its `stack-plex-webhook.service` systemd unit
  (was live/enabled), and `PLEX_WEBHOOK_PORT` from `.env`/`.env.example`. No Jellyfin-webhook
  equivalent has been built - this is a gap, not yet addressed.
- ~~**Plex removals**: `scripts/plex-library-report.py`~~ **Removed entirely in v11.7.0**
  along with Plex itself: the report script and its `stack-plex-report.service` +
  `stack-plex-report.timer` systemd units (both were live/enabled). Same gap as above - no
  Jellyfin equivalent exists yet.
- **`*arr` backups**: one embed per day covering the native-backup trigger above.
- **Grab/import/upgrade/health events from the three `*arr` apps**: each app's own native
  **Discord** notification connection, pointed at the same `DISCORD_WEBHOOK_URL`. Events:
  `onGrab`/`onDownload`/`onUpgrade` plus `onHealthIssue` and `onApplicationUpdate`. Verified
  via each app's `POST /api/v3/notification/test`.

  ```bash
  curl -H "X-Api-Key: $RADARR_API_KEY" http://localhost:7878/api/v3/notification/3 | \
    curl -X POST -H "X-Api-Key: $RADARR_API_KEY" -H "Content-Type: application/json" \
      -d @- http://localhost:7878/api/v3/notification/test
  ```

  Known tradeoff: this shares one channel with the Watchtower/backup/health alerts above.
  Grab/import noise lands in the same place as alerts that matter. A second webhook/channel
  would separate them; not done.

## Image pinning policy

Every image is pinned, using whichever approach does not change what is running:

- **Channel tags** (`ghcr.io/hotio/radarr:release`, etc.) for the hotio images (Prowlarr,
  Radarr, Sonarr, Tautulli). hotio's model is rolling channels identified by git-hash, not
  semver, so a channel tag is the closest available pin.
- **Version tags** (`nickfedor/watchtower:1.19.0`, `ghcr.io/nullable-eth/labelarr:v1.4.0`)
  where the upstream tags real releases and the running image matches.
- **Digest pins** (`@sha256:...`) for Seerr and Unpackerr. In each case the
  running `:latest` build is ahead of the newest tagged release, so any tag would be a
  downgrade.
- ~~**Version tag, manually bumped, off Watchtower's train** for Plex
  (`plexinc/pms-docker:1.43.2.10687-563d026ea`); PMS version changes on a live library are
  applied manually.~~ **Plex was removed entirely in v11.7.0**, replaced by Jellyfin
  (`lscr.io/linuxserver/jellyfin:latest`) - a mutable channel tag, not a version pin, so this
  exception does not carry forward. Jellyfin is auto-updated by Watchtower like any other
  channel-tag image unless that's deliberately changed later. This stack currently has no
  service using the "manually-bumped version tag, off Watchtower's train" pattern at all.
Watchtower auto-updates only the channel-tag-pinned images (posting to Discord first).
Digest-pinned and exact-version-tag-pinned images stay frozen until someone re-checks
upstream and bumps the pin in `docker-compose.yml`. Check which category an image is in
before assuming a version bump is something Watchtower will pick up.

## Resource limits

Every container has `mem_limit`/`mem_reservation`/`cpus`, sized from `docker stats`
observation where a container showed a baseline worth capping, or as defensive defaults
otherwise:

| Service | mem_limit | cpus | Basis |
|---|---|---|---|
| `jellyfin` | 3GB | 6 | Replaced `plex` in v11.7.0 (Plex ran `6GB`/`12`, sized from library-scan CPU spikes); Jellyfin starts at half that ceiling by deliberate choice, not yet tuned against real observed usage the way every other row here is |
| `nzbdav` | 2GB | - | WebDAV streaming has real per-connection buffering cost, bumped from 1g after a live repair/import batch sat at 62% mid-run |
| `neutarr` | 1GB | 2 | Raised from 512m 2026-07-18 - was getting OOM-killed roughly every 30 minutes at that ceiling despite a modest ~145MB steady state, invisible on any dashboard since `restart: unless-stopped` masked it |
| `jellystat-db` | 512MB | 1 | New in v11.7.0, no observed baseline yet - both containers are up and healthy but not yet under real playback load |
| `jellystat` | 512MB | 1 | Same as above |

Torrent/debrid's own six services (`decypharr`, `decypharr-alldebrid`, `zurg`,
`rclone-alldebrid`, `zilean`, `zilean-postgres`) plus `byparr` carried roughly 12.5GB of
combined `mem_limit` ceiling before removal - see [History](#history).

Everything else carries a smaller defensive ceiling; see `docker-compose.yml` for current
values, which change more often than this document.

Coverage was incomplete until v10.9.5: a `docker stats` audit found ten services with no
`mem_limit`/`cpus` at all (Prowlarr, Radarr, Sonarr, Lidarr, Whisparr, Bindery, Recyclarr,
NzbDAV, Seerr, `dmm-migrate`), visible as containers reporting the full host memory ceiling
as their limit. The `x-common` anchor does not set limits; every new service needs its own
explicit `mem_limit`/`cpus` lines. Verify with `docker stats`, not by grepping the compose
file. The same audit found Radarr, Sonarr, Lidarr, Whisparr, and Prowlarr running
`logLevel: debug` (leftover from old troubleshooting, log dirs at Servarr's rolling cap); all
were set back to `info`.

## Security

Every web UI publishes its port directly on the host with no login gate:

- Everything is plain `http://<ip>:<port>`; no certificate, no account.
- These addresses work only from the home LAN, or a [Tailscale](https://tailscale.com)
  network if configured. Nothing is reachable from the public internet unless you set that
  up.
- **Control Panel** holds read-write `docker.sock` access and can restart or inspect any
  container. Do not put this stack on an untrusted network or forward these ports publicly.
- Control Panel's CSRF/Origin-Host validation (see [Control Panel](#control-panel)) is not
  auth; it closes a specific cross-origin-POST gap. It is the one piece kept from the
  reverted network-security effort.
- `config/<app>/` generally holds plaintext credentials wherever an app stores its own config
  (e.g. `config/nzbdav/db.sqlite`'s `ConfigItems` table holds the Usenet provider's real
  username/password). Relevant if this host is shared or backed up somewhere less trusted.

A full Traefik + Authelia + CrowdSec stack (TOTP 2FA, CrowdSec bans) was built, verified
end-to-end, and reverted; the login+2FA prompt in front of every app, three extra services,
and a hairpin-NAT bug that took Plex down through the proxy did not pay for themselves on a
LAN-only deployment. The recipe is in [History](#history) if it is ever needed again (e.g.
before any public exposure).

## CI

- **`.github/workflows/validate.yml`**: on every push/PR, copies `.env.example` to `.env`,
  validates `docker compose config` for both the default and `extras` profiles, checks that
  every `${VAR}` in `docker-compose.yml` has a matching key in `.env.example`, runs
  `shellcheck` over every `.sh` file and `ruff` over `control-panel/app.py` + `scripts/*.py`,
  and builds the installer image (no push).
- **`.github/dependabot.yml`**: weekly checks across `docker-compose`, `docker`, `pip`, and
  `github-actions`. Dependabot cannot propose digest bumps, only track tags it already
  watches, so the digest-pinned images are outside its coverage.
- **`.github/workflows/publish-installer.yml`**: rebuilds and republishes the installer image
  to GHCR on every push to `main` that touches a bundled file, tagged `:latest` and
  `:vX.Y.Z` (parsed from this document's version line), for `linux/amd64` and `linux/arm64`.
- **`.github/workflows/claude.yml`** / **`claude-code-review.yml`**: `@claude`-triggered PR
  assistance and automatic review on every PR. Dependabot-authored PRs are skipped (GitHub
  withholds repo secrets from `pull_request`-triggered runs when the actor is
  `dependabot[bot]`); the workaround is commenting `@claude` on the PR, which triggers the
  other workflow.

## Installer image and setup wizard

`Dockerfile` + `entrypoint.sh` bundle this repo's tracked, portable files
(`docker-compose.yml`, `.env.example`, `scripts/`, `systemd/`, this README) into an image
that extracts (or updates) them onto a host in one command, without a git clone:

```dockerfile
FROM alpine:3.24
RUN apk add --no-cache python3   # stdlib only, for scripts/setup_wizard.py's --setup mode
WORKDIR /stack
COPY docker-compose.yml .env.example README.md ./
COPY scripts/ ./scripts/
COPY systemd/ ./systemd/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh ./scripts/*.sh
ENTRYPOINT ["/entrypoint.sh"]
```

The image never contains `.env`, `config/`, `media/`, or `usenet/`; they are excluded at the
`.dockerignore` level (a build-context exclusion), so no COPY instruction could reach them:

```
.git
config/
media/
usenet/
.env
*.log
```

**The setup wizard** (`scripts/setup_wizard.py`, stdlib-only Python) parses `.env.example`'s
`# ---- Section ----` headers and comment lines into a browser form, so the form and the
template cannot drift apart: add a new `KEY=default` line with a comment above it and it
appears in the wizard with no code changes.

```python
FIELD_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
SECTION_RE = re.compile(r"^# ---- (.+?) ----$")
POST_BOOT_KEYS = {
    "RADARR_API_KEY", "SONARR_API_KEY", "PLEX_TOKEN",
}
AUTO_GENERATE_KEYS: set[str] = set()  # empty since the torrent/debrid removal
```

`LIDARR_API_KEY` was dropped from `POST_BOOT_KEYS` (and from `.env`/`.env.example`) in
v10.9.9 with Lidarr, and `WHISPARR_API_KEY` the same way in v10.12.0 with Whisparr.
**`scripts/setup_wizard.py` was not updated for the v11.7.0 Plex-to-Jellyfin migration** -
`POST_BOOT_KEYS` still literally contains `PLEX_TOKEN`, a key that no longer exists anywhere
in `.env.example` (removed along with `PLEX_URL`/`PLEX_WEBHOOK_PORT`, replaced by
`JELLYFIN_URL`/`JELLYFIN_API_KEY`). Since the wizard builds its form by parsing
`.env.example`'s own `KEY=default` lines, a `POST_BOOT_KEYS` entry with no matching field is
inert, not broken - it just never renders. Conversely `JELLYFIN_API_KEY` (which really is a
post-boot-only field - Jellyfin's own Dashboard > Advanced > API Keys page needs the setup
wizard already completed, see `.env.example`'s own comment) is **not** in `POST_BOOT_KEYS` at
all, so it renders in the normal section instead of the highlighted one - a real, unaddressed
inconsistency, not yet fixed. Two fields currently do get collected as post-boot-only
correctly: each `*arr` app's own generated API key. These render in a highlighted "Fill in
after first boot" section and default to `changeme`; re-running `--setup` loads the real
`.env` as defaults, so a second pass only means entering what is new.

## Known gaps and limitations

- **An entire Saint Seiya film collection was repeatedly re-grabbed the same day, unexplained.**
  Found live 2026-07-17 while root-causing the Zurg routing-group incident (see
  [History](#history) `[10.16.0]`): 5 Saint Seiya titles beyond the one actually needed each had
  2-3 duplicate Real-Debrid torrents added within a single day, all normal (non-FLAC) filenames
  - a different bug from the FLAC-misroute issue that prompted this whole audit, not yet
  investigated. Whatever's driving the repeat grabs (a stuck Radarr search, a collection-import
  feature, something else) is still active and still wasting real grabs each time it fires.
- **Sonarr's `missing-aired` endpoint has an unresolved pagination performance risk.** The
  early-stop optimization helps, but this instance tracks close to 300,000 episode records
  and the endpoint has not been load-tested at that scale. It also has no frontend wiring in
  Control Panel (curl/API only). See [The *arr apps](#the-arr-apps).
- ~~Cleanuparr has a stale Readarr reference~~ **Not stale - required.** Confirmed by reading
  Cleanuparr 2.9.16's own source (`GenericHandler.ExecuteAsync`): every scheduled QueueCleaner/
  MalwareBlocker run unconditionally does `arr_configs.FirstAsync(x => x.Type == T)` for **all
  five** Servarr types (Sonarr, Radarr, Lidarr, Readarr, Whisparr), not `FirstOrDefaultAsync`.
  Missing even one type's placeholder row throws `System.InvalidOperationException: Sequence
  contains no elements` and kills the entire job - not per-app, the whole run. This was live and
  broken for real: QueueCleaner (every 5 min) and MalwareBlocker (hourly) both crashed on every
  single scheduled run from at least 2026-07-14 until fixed 2026-07-16, entirely silently (caught
  processing "no adult content library" - see [History](#history) `[10.12.2]`). Lidarr and
  Whisparr placeholder rows (`type` only, no connected instance - `ProcessArrConfigAsync` cleanly
  skips a type with zero enabled instances) added to restore all five. **If Lidarr or Whisparr
  are ever removed from `docker-compose.yml` again, do not delete their `arr_configs` row along
  with the instance/API-key cleanup** - that row has to stay forever, or reference this section
  before repeating the fix.
- ~~Cleanuparr logs a recurring `Error creating download service for Decypharr`~~ Fixed in
  v10.9.2: a stale password in Cleanuparr's stored credential, not a protocol mismatch.
  Confirmed with `curl` against Decypharr's login endpoint (`401` with the stored password,
  `200` with the real one) before changing anything. See [History](#history).
- ~~NeutArr's `python3` process gets OOM-killed inside its 512MB limit~~ **Fixed
  2026-07-18**: raised to 1g. Was happening on a ~30-minute cycle (15 kills in one overnight
  window, confirmed via `journalctl | grep oom-killer`, memcg-scoped to its container),
  invisible on any dashboard because `restart: unless-stopped` brought it back each time.
  Found during a stack-wide `mem_limit` audit earlier the same day, unrelated to and before
  the torrent/debrid removal below.
- ~~616 files (3.65% of the library) went offline in the torrent/debrid removal~~ **Re-acquired
  2026-07-20**: 611 files found still pointing at the dead `/mnt/decypharr-alldebrid`/
  `/mnt/zurg`/`/mnt/rclone-alldebrid` mounts (548 movies, 63 TV episodes across 8 series) during
  the same-day full disaster-recovery restore (see [History](#history)). Every one mapped
  cleanly to its Radarr/Sonarr `movieFile`/`episodeFile` record, bulk-deleted via each app's API
  (`DELETE .../moviefile/bulk`, `.../episodefile/bulk`), then the now-orphaned symlinks removed
  from disk by hand since the bulk endpoints don't touch the filesystem themselves. Both apps'
  existing missing-content search picked the resulting gaps up automatically with no manual
  search trigger needed. The TV library still carried a dead `/mnt/zurg/shows` Location in
  Plex's own DB (see [Jellyfin](#jellyfin) `### Historical: Plex, removed v11.7.0`),
  deliberately not cleaned up via the API since doing so risked Plex offering to delete the
  underlying metadata/watch history - moot now that Plex (and `config/plex/` along with it)
  was removed entirely in v11.7.0.
- **`media/youtube` is an inert leftover** from a removed Pinchflat integration; nothing
  reads or writes it.
- **The v11.7.0 Plex-to-Jellyfin migration's gap list is now fully closed** (each item
  documented in place, collected here for visibility). Fixed same-day: Jellyfin's missing
  `/mnt/nzbdav` mount; `control-panel/app.py`'s `MOUNT_DEPENDENTS` set (now `jellyfin`, not
  `plex`); `scripts/setup_wizard.py`'s `POST_BOOT_KEYS`/`REQUIRED_KEYS`; stale
  `config/plex/...` restic excludes. Fixed in the same overall effort, slightly later:
  `control-panel/app.py`'s all 14 former `/api/plex/*` routes reworked to real Jellyfin
  endpoints (see [Control Panel](#control-panel) and [History](#history) `[11.7.0]` for the
  full route-by-route mapping) - none are dead references anymore; every
  `stack-plex-*`/`stack-kometa-*`/`stack-tautulli-*` fish function (tracked in `~/.dotfiles`)
  reworked to a `stack-jellyfin-*` equivalent or removed outright if no Jellyfin equivalent
  exists; `jellystat-db` now has real logical-backup coverage via a `pg_dump` step in
  `scripts/backup-config.sh`, verified live; Seerr repointed at Jellyfin and poster sync
  reworked against Jellyfin's `ProviderIds`/image-upload API, both verified live; real
  hardware transcoding confirmed working via an actual VAAPI `ffmpeg` process, not just
  configured. **Genuinely still open, no Jellyfin-side equivalent built**: no webhook/report
  equivalent exists for the two Plex alerting scripts deleted with Plex (see
  [Alerting](#alerting-discord)) - this is the one piece of the original Plex tooling with no
  Jellyfin-side replacement at all yet.
- **A still-unexplained mass Radarr/Sonarr library-loss event** occurred once early on (1,605
  movies deleted in a 0.1-second burst with no matching API call logged; ~90 Sonarr series
  briefly added then removed with no deletion log line). Root cause was never identified.
  Both apps' native Recycle Bin is now enabled as a blast-radius mitigation, not a fix
  (`/data/movies/.recyclebin`, `/data/shows/.recyclebin`, 7-day cleanup). **A likely Plex-side
  symptom of this same event was found 2026-07-22**, while auditing Plex's library before
  decommissioning it for Jellyfin (see [Jellyfin](#jellyfin) `### Historical: Plex, removed
  v11.7.0`): Plex's Movies library had only 59-63 items indexed against ~10,004 real files on
  disk, traced to a single 2026-07-13 `Plex Media Scanner.log` event removing 661 of 794
  tracked items in one pass with `autoEmptyTrash` confirmed on. This closes the loop on what
  was learned - real files vanished from disk, Plex's next scan found the broken symlinks and
  silently trashed the library items - but not the underlying uncertainty: the original
  Radarr/Sonarr-side file loss still has no confirmed cause, only this newly-found symptom of
  it. Since Plex is now removed entirely, this can never be root-caused further.

## History

Condensed chronological record. Full detail lived in `CHANGELOG.md` before it was merged into
this document.

**v1.x**: initial build. Prowlarr, Zilean, Decypharr, Radarr, Sonarr, Lidarr, Readarr,
Whisparr, NZBGet, Seerr, Homepage, Recyclarr/TRaSH-Guides, passwordless-sudo/CI baseline.

**v2.x**: Decypharr's staged downloads were invisible to the `*arr` apps until their
containers shared its download path (v2.1.0). A deeper bug followed: root folders pointed at
Zurg's read-only FUSE mount, which cannot accept a written symlink, so no import had ever
completed (v2.2.0). Root folders moved to regular disk (`./media/<type>`) permanently.
Jellyfin + companion apps (Jellyseerr, Jellystat, jfa-go) were added and later removed;
Plex does not support `.strm`, and a Decypharr config-wipe bug (any partial `PATCH` to its
config API dropped the `debrids`/`mount` sections; filed upstream as
[sirrobot01/decypharr#343](https://github.com/sirrobot01/decypharr/issues/343)) ended the
experiment. Homepage was later replaced by Heimdall; both were eventually replaced by Control
Panel's Quick Links.

**v3.x**: Zurg/rclone-AllDebrid moved from native systemd units into Docker (v3.2.0); Plex
followed via a byte-identical migration from a native Arch install (v3.3.0; 3,826 movies /
774 shows verified against pre-migration counts). Recyclarr and its per-app TRaSH-Guides
custom formats were removed in favor of one hand-maintained blocklist format (v3.0.0).
FlareSolverr replaced by Byparr (v3.4.0). A Caddy reverse-proxy/Basic-Auth layer (added
v2.11.0) was removed (v3.1.0), the first of two reverted auth layers.

**v4.x**: Whisparr removed after a bug in the running build (`DownloadedEpisodesScan`
throwing on missing `path`) plus a root-folder regression (v4.0.0). The same regression class
hit Radarr a version later, traced to Radarr bind-mounting `/mnt/zurg` directly rather than
the parent `/mnt` (v4.0.1; still true, see [Architecture](#architecture)). Control Panel
built (v4.1.0), then grew a container grid, host stats, Zilean search-and-grab, whole-stack
restart, and Unstick/manual-import. Native Plex and its pre-migration backups removed
(v4.8.0). Setup wizard shipped (v4.9.0).

**v5.x-v6.x**: Control Panel absorbed Quick Links; Homepage and Heimdall removed (v5.0.0). A
check found several documented features not actually live (Prowlarr had 0 indexers, both
`*arr` apps had 0 custom formats, log rotation and the restic pipeline had never run);
everything in that gap was rebuilt and reverified. DebridMediaManager self-hosted
(v6.2.0-v6.3.0), including the local IMDB title index. Bazarr's language/provider setup
completed (v6.7.0); Bazarr was later removed entirely (v10.2.0).

**v7.x-v8.x**: Lidarr and Readarr removed as a user decision (v7.0.0). Radarr/Sonarr gained
native Plex notification hooks and a daily native-backup script. Cleanuparr, NeutArr, and
Dozzle added (v7.1.0), along with Pinchflat (YouTube archiving), which was removed a version
later when the storage it needed was not available (v8.0.0).

**v9.x-v10.0.0**: a complete Traefik + Authelia + CrowdSec stack was built and verified
end-to-end (TOTP 2FA, a CrowdSec-banned IP receiving 403) in v9.0.0, then fully reverted in
v10.0.0: a login+2FA prompt in front of every app, three extra services, and a hairpin-NAT
bug that took Plex down through the proxy, on a stack not reachable from outside the
LAN/tailnet. Control Panel's CSRF/Origin-Host check was kept. NZBGet was wired up, found to
conflict with the no-local-disk goal, and replaced by NzbDAV (v10.1.0).

**v10.2.0**: Bazarr removed entirely (container, config, Control Panel references, env keys,
`stack-bazarr-search`). Lidarr, Readarr, and Whisparr reinstated, each wired to Prowlarr,
both Decypharr instances, NzbDAV, Zurg routing groups, Unpackerr, and Control Panel's queue
tools. Readarr pinned to the last pullable `linuxserver/readarr` tag (upstream retired);
Whisparr pinned to hotio's `:v3`. Calibre-Web added as the ebook reader (default password
rotated into `.env`). Zurg's `music`/`books` groups restored. Decypharr categories and
`allowed_file_types` extended. Plex "Audiobooks" library added; movie-type "Adult" library
added at `/mnt/zurg/adult`. CLI and setup wizard extended to five `*arr` apps. Whisparr
"Unlimited" quality profile added to match Radarr/Sonarr.

**v10.3.0**: Maintainerr added (Plex library lifecycle management - removed entirely in
v11.4.0, see below); two community rules imported, left `isActive: false`. Native Discord
notification connections added to all five `*arr` apps.

**v10.4.0**: Zurg `anime-shows`/`anime-movies` routing groups and matching Plex libraries
added. Restarting Zurg for the new groups left `/mnt/zurg` empty: the mount's
`mount_path`/`rclone_enabled` keys had never been written to `config.yml` (only toggled in
Zurg's dashboard, an in-memory setting). Keys added to `config.yml`. Sonarr's `/data/anime`
migration for 1,505 `Anime`-genre series started via `PUT /api/v3/series/editor`; the async
`BulkMoveSeries` command sat queued behind a long `ProcessMonitoredDownloads` job.

**v10.5.0**: the stuck command completed after 1h15m; the anime migration finished (all
1,505 series under `/data/anime`, verified with files on disk). Fixed the Plex "Adult"
library missing its `/data/adult` location (added in v10.2.0 with only the empty
`/mnt/zurg/adult`), so Whisparr's imports had been invisible in Plex; fixed via a Plex API
`PUT` (which requires `type`/`agent`/`scanner`/`language` resent alongside `location`).
Recyclarr reinstated, targeting the existing "Unlimited" profile with five hygiene custom
formats; `reset_unmatched_scores` left off to protect the manual blocklist format. Control
Panel gained `GET /api/arr/{app}/command-backlog` (+ `stack-arr-backlog`) after the stall
showed the internal command queue had no visibility. Synced to `Stackalicious` (sanitized).

**v10.6.0**: Control Panel gained `GET /api/queue-status` (+ `stack-queue-status`): every
download queue bucketed into downloading/stalled/queued/importing with observed speed/ETA
from two size-remaining samples ~4s apart, because the apps' own `timeleft` fields are stale
placeholders for debrid/NzbDAV downloads. Also `GET /api/backlog-status`
(+ `stack-backlog-status`): wanted/missing counts with throughput-projected ETA measured from
each app's last 50 import-completion history events, capped to a 6-hour lookback. Lidarr
names its import event `trackFileImported`, not `downloadFolderImported` like the
Radarr-lineage apps; Readarr's was unverifiable, so both names are checked.

**v10.6.1**: `queue-status` extended to include Plex's own `/activities` (scans, analysis,
thumbnails) as a seventh queue, using progress percent as the measured signal.

**v10.6.2**: NeutArr was only hunting Sonarr and Radarr; `lidarr`/`readarr`/`eros` config
files existed but had empty credentials. Filled in all three. Whisparr belongs under
NeutArr's "Whisparr V3" type (`eros.json`); the "Whisparr V2" slot (`whisparr.json`) targets
an API shape this stack's `:v3` pin does not speak.

**v10.6.3**: Whisparr's flat hunt throughput was config, not a fault: `hunt_missing_items: 1`
+ `sleep_duration: 900` caps NeutArr's contribution at ~4 items/hour. Raised to `3`/`300`
(~36/hour theoretical, now bounded by the unchanged `hourly_cap: 20`). Two false leads ruled
out first (hourly cap, cooldown saturation); a third (dead scheduler) came from comparing
UTC output against NeutArr's local-TZ log timestamps without converting. This stack mixes
UTC and local timestamps depending on source; put both sides in the same zone before
trusting a time-gap diagnosis.

**v10.6.4**: `backlog-status` could report absurd rates during an import burst (Sonarr:
`13,800/hr` from 23 events landing in one 6-second window over a 50-event sample). Fixed:
sample size 50 → 200, plus a `MIN_RATE_WINDOW_HOURS = 0.25` floor. Sonarr dropped to
`304/hr`; Radarr (never bursty) barely moved.

**v10.7.0**: Readarr replaced by Bindery. Trigger: Readarr's Goodreads-replacement provider
host (`api.bookinfo.club`) lost its DNS record entirely, and upstream Readarr is retired.
Bindery (`ghcr.io/vavallee/bindery`, pinned `v1.25.0`): Go-based, distroless,
OpenLibrary-primary metadata. Deployment notes: distroless means no shell and default UID
65532, so it needed a Compose `user:` override plus a host-side `chown`; the compose-level
healthcheck had to be deleted (the image bakes in `HEALTHCHECK CMD ["/bindery","healthcheck"]`
and a `CMD-SHELL` check fails with no shell); mutating API calls returned
`{"error":"forbidden"}` under API-key auth until `X-Requested-With: bindery-ui` was sent
(gated by `RequireXRequestedWith` in `internal/auth/middleware.go` on the deployed version).
Admin-account creation was left to the user. Provisioned via its API: Prowlarr registered
and synced (23 indexers; Bindery pulls, it is not pushed to), NzbDAV added as a SABnzbd-type
client (NzbDAV needed a `bindery` category patched into its SQLite `ConfigItems`; no API
exposes it), `/books` root folder. Decypharr was not wired in at the time (diagnosed as a
Bearer-vs-cookie mismatch; later found wrong, see v10.9.7). Supporting services rewired:
`ARR_APPS` lost `readarr`; Unpackerr's `UN_READARR_0_*` removed; NeutArr's `readarr.json`
disabled; Decypharr category renamed `readarr` → `bindery`; wizard keys updated. Cleanuparr's
stale Readarr reference flagged (see Known gaps). Calibre-Web needed no changes.

**v10.8.0**: live per-app API hit counter added (see
[Control Panel](#control-panel)), which surfaced two bugs: `httpx.request` reassignment alone
is a no-op (patch `httpx._api.request`), and `/api/containers` took 60-90s from sequential
`container_stats()` calls (fixed with a thread pool, ~6s). A stale `readarr` entry in
`app.js`'s frontend `ARR_APPS`/`QUICK_LINKS` arrays removed. A full-stack outage: `/mnt/nzbdav`
stale at the host level (`Transport endpoint is not connected`), recovered with
`sudo umount -l /mnt/nzbdav`; root cause in `stack-restart-all`'s ordering, fixed with the
`MOUNT_PREREQS` wave and `nzbdav-rclone` added to `MOUNT_PROVIDERS` (see
[Whole-stack restart](#whole-stack-restart-mount-order-aware)).

**v10.9.0**: Stash added (extras profile), reading `./media/adult` read-only. Wired into
Control Panel (container grid, Quick Links at host port 9998). The stock image has no `curl`;
healthcheck switched to `wget -qO- --spider`. First-run wizard completed (no credentials
set). First scan indexed 530 of 531 files after the mount fix below.

**v10.9.1**: Stash's first scan had found 0 scenes: the container lacked the
`/mnt/zurg`/`/mnt/decypharr`/`/mnt/nzbdav` mounts, so every symlink in `./media/adult` was
dangling (see [Stash](#stash-adult-library-cataloging)). Cleanuparr found connected only to
Sonarr and Radarr; Lidarr and Whisparr added via its UI. Orphaned
`config/neutarr/whisparr.json` removed. Recyclarr and Unpackerr audited; both already
correctly scoped.

**v10.9.2**: Cleanuparr's recurring `Error creating download service for Decypharr` was a
stale stored password, not a protocol mismatch (confirmed via `curl` against Decypharr's
login endpoint before changing anything). Fixed through Cleanuparr's UI.

**v10.9.3**: off-site backup wired up. The local restic repo and the Dropbox tar (the de
facto off-site copy) both lived on the host's single disk, and the tar leg had failed the
night before (4h41m, exit 1, no output). Added a second restic repo inside the host's Dropbox
sync folder via the existing `BACKUP_REMOTE_REPOSITORY` mechanism; verified with a real run
(48GB backed up, 44.7GB stored after dedup). The verification run also caught
`config/stash/config/config.yml` unreadable by the backup user (fixed, `chmod 644`). Stash
configuration audited (see [Stash](#stash-adult-library-cataloging)). NeutArr's ~30-minute
OOM-kill cycle found (see Known gaps).

**v10.9.4**: user-reported content leak: "Drilling Mommy" in the Movies library, untracked
content classified by Zurg. Added `Drilling`, `Family[\s._-]?Swap`,
`Forbidden[\s._-]?Scenes`, and `Cory[\s._-]?Chase` to Zurg's `adult` filter, verified against
legitimate titles containing the same words (`Goodnight Mommy` etc. still do not match). A
structural bug found in the same investigation: `adult` (`group_order: 17`) ran after
`shows`' `has_episodes: true` heuristic (10), so series-numbered content
(`Family.Swap.10.2023`) was claimed by `shows` before the adult filter ever ran; no keyword
fix could catch it. `adult` moved to `group_order: 5`, first in the sequence. Applied with
the documented restart order (Zurg, then Radarr); verified files moved on disk. Check
`group_order` first, not just keywords, when a misroute report does not match a
missing-keyword pattern.

**v10.9.5**: resource-limit and log-level audit; see [Resource limits](#resource-limits).
Ten services had no `mem_limit`/`cpus`; five apps ran `logLevel: debug`. Both fixed and
verified via `docker stats` and each app's config API.

**v10.9.6**: twenty new diagnostic/action endpoints + `stack-*` commands (see
[CLI](#cli-the-stack--fish-functions)). Three bugs found verifying them:
`disk-usage`/`perms-check` resolved symlinks out to the multi-TB debrid mount (fixed with
`lstat` + `followlinks=False`); `disk-usage` used `st_size` instead of `st_blocks`,
overstating sparse-file usage (349GB reported vs. 11GB actual); restic calls against the
read-only repo mounts needed `--no-lock`, and the restore test crashed force-decoding binary
files as UTF-8. The CLI plus a generalized Control Panel spun off into
[`StackScripts`](https://github.com/WhispersOfJ/StackScripts); `AGENTS.md` added to all three
repos codifying the sync obligation.

**v10.9.7**: Bindery's Decypharr download client fixed; same root cause class as v10.9.2
(stored credentials wrong: the API key was in `username` with an empty password), not the
Bearer-token limitation assumed in v10.7.0. Fixed via Bindery's UI; Bindery's own write API
returns 403 under API-key auth. `config/decypharr/downloads/bindery` had never been created
(Decypharr creates a category folder on first real download); created manually.
`scripts/enable-recycle-bin.py` extended to Lidarr and Whisparr (both had `recycleBin: ""`;
Lidarr needed an `api_version` field, `/api/v1/`).

**v10.9.8**: Bindery and Calibre-Web retired (see
[Bindery and Calibre-Web: retired](#bindery-and-calibre-web-retired)); Bindery tracked zero
books across its entire run. Control Panel's `/api/decypharr/grab` fixed: Decypharr's
`/api/v2/*` torrent API needs its own qBittorrent-style session
(`POST /api/v2/auth/login`), not a bare POST; `DECYPHARR_ADMIN_USERNAME`/`_PASSWORD` threaded
into the container. Kometa was running a full pass on every container start (image default
entrypoint); overridden to `sleep infinity` so restarts idle, with `/api/kometa/run` execing
runs on demand; healthcheck updated to match. NzbDAV's Repairs tab given read-only mounts of
Radarr/Sonarr's root folders so it can correlate symlinks back to library entries. Three CLI
wrappers added (`stack-plex-updates`, `stack-arr-import-all`, `stack-arr-missing-aired`).

**v10.9.9**: Lidarr removed entirely (compose block, `config/lidarr`, Control Panel dicts,
`LIDARR_API_KEY`, Prowlarr sync entry, NeutArr files; Cleanuparr's stale SQLite row deleted
directly with the container stopped, since no REST endpoint covers that table). Adminer
removed, no replacement (a same-day CloudBeaver swap was reverted; no web DB GUI remains).
Plex's "Adult" library removed via the API; Stash is now the sole catalog surface for that
content (files untouched, Whisparr unchanged). Plex bumped to
`1.43.3.10828-00f62d37d` (manual pin bump; verified via `/identity`, all six libraries
reachable). Control Panel restyled from the Matrix theme to a slate/blue dark theme;
`matrix-rain.js` deleted. `dmm-mysql` upgraded 8.4 → 9.7 (full `mysqldump` first, dependent
app stopped, row counts verified after). `uvicorn` bumped 0.34.0 → 0.51.0 (image rebuilt).
Glances and Dozzle removed (Control Panel's host-stats endpoint and tiles removed with
Glances). A Prometheus + Grafana plan was drafted and cancelled before anything was built.
20 new Control Panel endpoints + `stack-*` commands added (`stack-command-queue-summary`,
`stack-plex-duplicates` (which found ~700GB of redundant movie copies, removed the same
session), `stack-recently-added`, `stack-cutoff-unmet`, `stack-cleanuparr-strikes`,
`stack-dmm-status`, `stack-plex-sessions`, `stack-seerr-requests`, `stack-tautulli-history`,
and others). New Control Panel dependencies: `pymysql` + `cryptography` (MySQL
`caching_sha2_password`). Bugs fixed while verifying: `plex_duplicates()` false positives
from one file visible via two root paths (de-duplicated on byte size); two Plex endpoints
assumed XML where `plex_headers()` requests JSON; a fish function used `status`, a fish
special variable (renamed `req_status`).

**v10.10.0**: Letterboxd-to-Radarr added: seven `stack-letterboxd-radarr*` commands and two
Control Panel endpoints (`/api/arr/radarr/add-from-letterboxd`, `.../add-from-letterboxd-list`)
scrape a film page, list, watchlist, watched-films page, filmography, collection, or the
popular page and add whatever is not already in Radarr. No extra container (unlike
screeny05/letterboxd-list-radarr's Redis-backed adapter). `/movie/lookup/tmdb` does not carry
a usable `id` for an already-added movie on this Radarr version; `GET /movie?tmdbId=` is the
reliable check. robots.txt-disallowed sort/filter URL segments are rejected before any
request; a page-2+ fetch failure stops pagination and uses what loaded. Limitations:
`/films/in/<collection>/` sits behind a Cloudflare JS challenge (intermittent);
`/films/popular/` is pure client-side hydration, so `stack-letterboxd-radarr-popular` always
reports "no films found." Mirrored to Stackalicious and StackScripts.

**v10.10.1**: `--dry-run` added to every `stack-letterboxd-radarr*` command: validates and
reports what would be added to Radarr without writing anything.

**v10.10.2**: `cryptography` bumped 43.0.3 → 49.0.0, clearing 4 open Dependabot
alerts (2 high: a subgroup-validation gap on SECT curves and a vulnerable bundled OpenSSL;
2 low: the same OpenSSL issue and incomplete DNS name-constraint enforcement). Verified live
post-rebuild: control-panel starts healthy, DMM's MySQL connection (`caching_sha2_password`,
the actual consumer of this dependency) still authenticates, and the Letterboxd-to-Radarr
endpoints still work end to end.

**v10.11.0**: Ratings lookups (`stack-rating-imdb`, `stack-rating-mdblist`) and
MDBList list import (`stack-mdblist-import`) added — three new Control Panel endpoints
(`/api/ratings/imdb`, `/api/ratings/mdblist`, `/api/mdblist/import-list`) plus a new Sonarr
add-series path alongside the existing Radarr one. Both OMDb and MDBList API keys are read
live from Kometa's own `config.yml` (already configured for Kometa's metadata lookups) - no
new secrets or `.env` entries. Direct IMDb list import was evaluated and dropped: IMDb's list/
export pages sit behind a genuine AWS WAF JS challenge (confirmed live via the
`x-amzn-waf-action: challenge` response header, not workable with plain HTTP requests), and
MDBList's own "external list" API only serves lists a user has already linked to their MDBList
account through the website - there's no API to import an arbitrary IMDb URL
programmatically. MDBList's own list search already mirrors common IMDb lists (Top 250 etc)
under multiple users, reachable through the same working endpoint, which is the practical path
to that content instead. `_radarr_add_movie`/`_sonarr_add_series` were factored out as shared
per-item add helpers (bulk existing-ID set passed in once, not one existence check per item) and
the existing Letterboxd-list loop was refactored onto `_radarr_add_movie` rather than
duplicating the add logic a third time. Two real bugs caught during this work: MDBList
fuzzy-matches a well-formed-but-unrecognized IMDb id to an unrelated title instead of erroring,
and echoes the *requested* id back as its own `imdbid` field on that garbage match - an
id-equality check doesn't catch it, a real vote-count check does, since a genuine rating always
carries votes and a garbage match's sub-rating doesn't. Mirrored to Stackalicious and
StackScripts (which had never received the ratings feature from the prior session at all -
backfilled in full, not just the new pieces); stack-tui's command list regenerated (69 commands)
and `dist/` rebuilt.

**v10.12.0**: Whisparr and Stash removed entirely, same recipe as Lidarr's removal in v10.9.9.
Containers stopped and removed; `config/whisparr`, `config/stash`, and `./media/adult`
(Whisparr's root folder - 100% symlinks, no real media files) deleted; `docker-compose.yml`
service blocks, the notify container's `UN_WHISPARR_0_*` vars, and the Recyclarr comment
referencing Whisparr all removed; `control-panel/app.py`'s `ARR_APPS`/`QUEUE_ARR_APPS`/
`CONTAINER_LABELS`/`LOG_LEVEL_APPS`/`ARR_LOG_CONTAINERS` updated, the two `/api/stash/*`
endpoints and `/api/neutarr/hunt/eros` (Whisparr's only hunt trigger) deleted outright;
`WHISPARR_API_KEY` gone from `.env`/`.env.example` and `scripts/setup_wizard.py`'s
`POST_BOOT_KEYS`; Prowlarr's Whisparr application-sync entry deleted via its own API; the
Cleanuparr SQLite row deleted in the same pass this time (six referencing tables confirmed
zero orphaned rows first, container stopped to avoid a live WAL-mode write); NeutArr's
`eros.json` (the real instance config) and the pre-existing orphaned `whisparr.json` deleted -
both regenerate with blank credentials on every restart, same inert-placeholder pattern
already documented for the original orphan, not a sign the removal didn't take. Decypharr's
live `config/decypharr/config.json` had `"whisparr"` dropped from its `categories` list.
`scripts/enable-recycle-bin.py`, `scripts/backup-config.sh`, and four `.claude/skills/*`
helper scripts (`arr-config-sync`, `docker-compose-manager`, `health-monitor`,
`secret-injector`) all had their own Whisparr/Stash references removed. The `*arr` app family
in this stack is now Radarr/Sonarr only; there is no adult content library.

**v10.12.1**: Docs-accuracy pass triggered by a full moving-parts audit for CLAUDE.md. Found
`beszel`/`beszel-agent` (added at some point after Glances' v10.9.9 removal, per the compose
file's own comment - "Replaces Glances... hub+agent resource/container monitor") completely
undocumented outside `docker-compose.yml` itself: absent from `control-panel/app.py`'s
`CONTAINER_LABELS`, this README's service table, and `CLAUDE.md`'s "Glances and Dozzle
removed... no replacement" landmine, which was simply wrong by the time this was caught -
Beszel is the replacement. Fixed in all three places. Also fixed: this README's service table
still showed Plex pinned to `1.43.2.10687-563d026ea`, a full version behind the
`1.43.3.10828-00f62d37d` this stack has actually run since the v10.9.9 bump. Service count
corrected 28 → 30 throughout (the tracked table had silently excluded Beszel's two containers
since they were added).

**v10.12.2**: Cleanuparr was fully configured, surfacing two real live bugs in the process.
**QueueCleaner and MalwareBlocker had been crashing on every single scheduled run** (every 5
min / hourly) since at least 2026-07-14, entirely silently - `System.InvalidOperationException:
Sequence contains no elements`. Root-caused by reading Cleanuparr 2.9.16's own source:
`GenericHandler.ExecuteAsync` requires an `arr_configs` row for all five Servarr types
unconditionally (`FirstAsync`, not `FirstOrDefaultAsync`); this stack was missing `lidarr` and
`whisparr` (the latter deleted during this same session's Whisparr removal, following what
turned out to be a wrong assumption - see below). Fixed by inserting placeholder rows for both
(type only, no connected instance needed). The pre-existing "stale Readarr reference" noted in
Known Gaps was never stale - it's required scaffolding for this exact check, and deleting it
during a future app removal would silently reintroduce this bug. Also found and fixed:
Cleanuparr had zero filesystem access to the download paths (compose only mounted its own
`/config`, missing the `/app/downloads`/`/app/downloads-ad` mounts every other file-touching
companion app has) - not the actual crash's cause, but a real gap fixed alongside it. Blacklist
Sync (pushes the blacklist into the download client's own preferences) was found permanently
broken against Decypharr - 404 on `setPreferences` even with valid credentials, confirmed via
direct API testing, not a credentials issue - and disabled for good; Content/Malware Blocker
(applies the same blacklist directly to Sonarr/Radarr) already covers the useful half of that
feature and stays on. A stall-rule and slow-rule (3-strike, 0-100% completion, both
private/public) were added directly via SQL after confirming live that Cleanuparr's queue_cleaner
config API silently no-ops writes to `stallRules`/`slowRules` (200 "success" response, zero
effect on the DB or a subsequent GET) while the actual job code queries those tables directly,
independent of that broken API - the DB writes take effect regardless of the API bug.

**v10.13.0**: A live audit found 165 movies in the Movies library tagged "Anime" by Plex's own
agent - Radarr/TMDB has no such genre at all (confirmed on Akira: just Animation/Science
Fiction/Action), so this can only be detected after the fact, not filtered at import. Fixed
with a new hourly sweep (`scripts/sort-anime-movies.py` + `systemd/stack-sort-anime-movies.
{service,timer}`): queries Plex for Anime-tagged movies, matches each back to its Radarr entry
by `tmdb://` guid, and relocates it via Radarr's own `PUT /movie/editor` (`moveFiles: true`) to
a new second root folder, `/data/anime-movies` (Radarr had zero anime-movie root folder before
this - Sonarr's equivalent `/data/anime` split already existed). Cleared the full backlog the
same day; idempotent on rerun. Separately, `control-panel/static/app.js` still listed Whisparr
and Stash in `ARR_APPS`/`QUICK_LINKS` despite both being fully removed in v10.12.0 - dead tiles
pointing at containers that no longer exist; the Python side (`ARR_APPS`, `CONTAINER_LABELS`)
had already been cleaned up correctly, only the frontend had drifted. `PLAN.md` added alongside
this work, laying out the larger, deferred alternative (dedicated Anime Radarr/Sonarr instances)
- cross-checked every app wired to the main Radarr/Sonarr before writing it, catching three
integrations a first pass missed (Unpackerr, NzbDAV's Repairs tab, Maintainerr) plus a
root-folder collision risk if that plan's backlog migration ever reuses Sonarr's existing anime
path.

**v10.14.0**: `PLAN.md` research resolved two of its three open questions in TRaSH
Guides' favor of *not* building the dedicated-instance version at all: TRaSH's own anime guides
for both apps explicitly endorse a single instance with a second quality profile as supported,
not a workaround, and the "third Decypharr instance" question turned out to be a non-issue by
construction (verified directly against `config/decypharr*/config.json` - `debrids` and
`categories` are independent arrays, nothing scopes a provider to one category). Implemented
that lightweight path: both apps now carry a Recyclarr-managed "[Anime] Remux-1080p" profile
(id 7 on both), synced entirely by `quality_profiles.trash_id` rather than hand-copied scores -
TRaSH's guide supplies the qualities tree, custom-format associations, and scores directly.
Two real, previously-undiscovered bugs surfaced and fixed along the way, unrelated to the anime
work itself but blocking it: **Recyclarr's sync had been completely broken since the day it was
added** - its compose service block never passed `RADARR_API_KEY`/`SONARR_API_KEY` into the
container despite `recyclarr.yml`'s `!env_var` directives requiring them, so every scheduled
run failed at the config-parse stage, confirmed via logs going back to at least 2026-07-14; and
both apps' sole quality profile had drifted to being named "Any" while `recyclarr.yml` (and
this repo's own `CLAUDE.md`) still assumed "Unlimited," so even after the env-var fix, Recyclarr
couldn't find anywhere to score custom formats into until the live profile was renamed back via
API. A third, more structural finding shaped the implementation itself: Radarr/Sonarr's quality
*definitions* (file-size ranges per resolution) are confirmed instance-wide via
`GET /api/v3/qualitydefinition`, not scoped per profile - so the new anime profile deliberately
does *not* get TRaSH's anime-specific sizes, only its custom-format scores and quality-tier
groupings, to avoid silently overwriting the general sizes every existing non-anime title still
depends on. Documented as an accepted, load-bearing limitation in both `CLAUDE.md` and
`recyclarr.yml` directly, not left implicit.

**v10.14.1**: Usenet made the preferred protocol on both Radarr and Sonarr, on user
request - **a deliberate reversal of this stack's original debrid-first design** (debrid
mounts serve already-cached content instantly with no real download; Usenet always downloads/
streams real data, the tradeoff being knowingly accepted here). Checked every lever both apps
expose for protocol preference rather than assuming one setting covers it: Delay Profile
`preferredProtocol` was already `"usenet"` on both apps with zero delay either way, and indexer
priority already favored the two Usenet indexers (DrunkenSlug, NZBgeek at priority 1-2) well
ahead of every torrent indexer (all at 25) - neither needed a change. The one setting that
was backwards: download-client priority had Decypharr (torrent/debrid) at priority 1 and
`nzbdav` (Usenet) at priority 2 on both apps, opposite of the new preference - swapped via API
on both. All three settings live in each app's own gitignored config, not tracked files - this
entry is the only record of what changed.

**v10.15.0** (current): Poster sync added - replaces a movie/show's Plex poster with TMDb's
top-voted one, matched via the item's `tmdb://` Guid (falling back to TMDb's `/find` endpoint
for older-agent matches still on `tvdb://`/`imdb://`). ThePosterDB was evaluated and rejected:
its Terms of Service ban automated scraping and it has no public API. One job at a time,
progress over SSE (`/api/posters/sync/stream`); see [Poster sync](#poster-sync-tmdb-posters-over-plexs-own).
Alongside it: a control-panel UI pass (root font-size bumped 25%, a real focus-ring regression
fixed - `input:focus`/`select:focus` was setting `outline:none` *after* the `:focus-visible`
rule, silently killing keyboard focus visibility on every text/search/number input - aria-labels
added to icon-only buttons, and the armed-pulse destructive-action animation added to the
`prefers-reduced-motion` override, which had been looping unchecked) and a new SSE endpoint,
`/api/container/{name}/logs/stream`, for live-following any container's logs during a mutating
action.

Separately, a new standalone tool, `scripts/audit-tmdb-links.py`, audits a Plex movie library
for items with no TMDb link at all (checked via the same Guid logic as poster sync, plus the
legacy `com.plexapp.agents.themoviedb` guid), searches TMDb by title/year, and scores
candidates by title similarity + year delta into `matched`/`fixable`/`unmatched`/`search_error`
buckets - read-only, CSV + console report, never writes to Plex itself. First real run against
this library (3,923 movies) found 18 with no TMDb link; applying those 18 surfaced a genuinely
useful technique for obscure titles Plex's own `tv.plex.agents.movie` (Discover) agent doesn't
index at all (confirmed live: a direct `matches()` call against the Discover agent for several
1970s-80s exploitation titles returned no relevant candidates in the top 8 results) - calling
`Video.matches(agent="themoviedb", title=..., year=...)` instead invokes the legacy
`com.plexapp.agents.themoviedb` agent, which searches TMDb's own database directly and found
exact hits (verified by requiring the returned `SearchResult.guid` contain the same TMDb id
already found) for 17 of the 18; Plex then transparently upgraded most of those onto the
modern `plex://movie/...` object with a full `imdb`/`tmdb`/`tvdb` Guid set once one existed,
falling back to the raw legacy-agent guid only where no Discover equivalent exists. The 18th
("Redux", no year set in Plex) had no verifiable candidate via this method and was left
unmatched for manual review rather than force-applied. 14 of the 17 apply calls returned a
transient `500` from Plex - misleading in 10 of those cases, since the guid change had already
committed server-side before the 500 (the error came from something downstream, most likely
Plex's own post-match metadata/image fetch); the remaining 4 had genuinely not applied and
succeeded cleanly on a retry with more spacing between calls. Traced to load from a Kometa run
that happened to be active at the same time, not a problem with the match logic itself -
every apply is now verified by re-reading the item's guid afterward rather than trusting the
HTTP response code.

**v10.16.0** (current): Started as a docs-accuracy check on the previous entry's downstream
sync and turned into a live-stack audit. Found this README's Plex library table (see
[Architecture](#architecture)) had drifted badly - documented section keys 4/1/3/8/10/11,
live keys are 13/14/15/16 - and that two of the six libraries it claimed existed, `Music` and
`Audiobooks`, don't exist on the live Plex server at all anymore, with no History entry ever
recording their removal. Chasing why led to Zurg's `music`/`books`/`adult` content-routing
groups (see [The debrid pipeline: removed](#the-debrid-pipeline-removed) for the surviving
writeup) - all three had kept running long after the apps that needed them (Lidarr, Bindery,
Whisparr) were gone, and `music`/`adult`'s keyword regexes were both silently misrouting real
movies into paths nothing serves. Root-caused, fixed, and recovered: removed all three groups
from `config/zurg/config.yml`; found 43 movies sitting in the orphaned `music` path (37 already
duplicated safely in Radarr via Decypharr's separate mount, 5 genuinely missing and added +
manually imported, 1 already covered under a differently-dated TMDb entry) and 4 in `adult`
(2 real movies recovered the same way, 2 genuinely adult
files confirmed still live on the Real-Debrid account and deleted via its API directly, since
Zurg's own dashboard has no per-item delete); also found and cleaned up 4 duplicate grabs of
*Wicked City* (2160p HDR) sitting under 4 separate Real-Debrid torrent IDs, almost certainly
from Radarr retrying a search that kept succeeding but never importing. `scripts/
sort-anime-movies.py` was updated to resolve its Plex library section by title instead of a
hardcoded key, since this incident is direct proof those keys aren't stable across this stack's
own history - it happened to still be right, this time.

Separately found, not yet acted on: an active, ongoing retry loop grabbing an entire *Saint
Seiya* film collection (5 titles beyond the one actually needed) 2-3 times each within a single
day, all with normal (non-FLAC) filenames - a different bug from the one just fixed, still
unexplained. Flagged for its own investigation; see [Known gaps](#known-gaps-and-limitations).

**v10.17.0** (current): `config/kometa/config.yml` gained `Anime Movies` and `Anime Shows`
library blocks (movie-type and show-type collection/overlay file sets respectively, mirroring
`Movies`/`TV Shows`), replacing a stale comment that said Anime "doesn't exist as a Plex
library here" - it has, since v10.4.0; the comment just never got updated once the anime
libraries actually existed. Gitignored config, not tracked in git - this entry is the record.
Found and fixed a real bug surfacing this: Control Panel's `/api/kometa/run` builds
`--run-libraries` by joining the requested library names with a comma
(`",".join(payload.libraries)`), but Kometa's own CLI takes a **pipe**-separated list - a
comma-joined multi-library value fails the entire run with `Config Error: No libraries were
found in config` (confirmed live testing the new libraries directly via `docker exec`), not a
partial failure. A single-library scoped run never hit this, since there's no delimiter to get
wrong with only one name - this bug has been live since the endpoint was written and would only
ever show up when scoping a run to more than one library at once.

**v10.18.0** (current): Added Labelarr (`ghcr.io/nullable-eth/labelarr:v1.4.0`, extras profile)
- pulls TMDb keywords onto Plex items as labels, complementing Kometa (collections/overlays)
rather than overlapping it. Wired to Plex (via `HOST_IP:32400`, the same pattern every other
container needs since Plex runs `network_mode: host`), TMDb (a new credential,
`TMDB_READ_ACCESS_TOKEN` - TMDb's v4 read-access token, distinct from the v3 `TMDB_KEY` Kometa
and DMM already share), and Radarr/Sonarr for TMDb-id lookups. Timer-only (1h default, runs on
start too); its optional webhook mode needs Plex Pass and wasn't configured. Verified live on
first run: connected to all four services cleanly and applied keyword labels to real library
items with zero errors. 31 services total now.

**v10.19.0** (current): Anime support removed entirely, by explicit request - Radarr/Sonarr
library (122 movies, 159 series, `deleteFiles=true`, including 15.7GB of real - not
debrid-symlinked - local files under `anime-movies`), both Plex libraries (`Anime Movies` key
13, `Anime Shows` key 15), both root folders, the `[Anime] Remux-1080p` quality profile and its
33 dedicated custom formats on both apps, Zurg's `anime-shows`/`anime-movies` content-routing
groups, the `rclone-alldebrid-anime` service and `/mnt/all-anime` mount, `config/kometa/
config.yml`'s `Anime Movies`/`Anime Shows` library blocks and MyAnimeList credentials,
`scripts/sort-anime-movies.py` and its systemd timer/service, `control-panel/app.py`'s three
anime references, and `PLAN.md` (the never-implemented dedicated-instance proposal). 8 live
Prowlarr indexers whose names don't say "anime" but are anime-dedicated trackers (`Nyaa.si`,
`sukebei.nyaa.si`, `SubsPlease`, `Mikan`, `dmhy`, `Bangumi Moe`, `Shana Project`, `Tokyo
Toshokan`) were disabled too, after a scope check turned up that the 5 indexer *definition*
files under `config/prowlarr/Definitions/` matching "anime" by name were never actually added
as live indexers - the real anime-capable indexer surface used different names entirely.

A live Sonarr Trakt import list literally named "Anime" (`enableAutomaticAdd: true`,
`monitorNewItems: all`, 12h refresh, root folder `/data/anime`, quality profile 7) was found
and deleted mid-removal - undiscovered by the original file/config grep sweep since import
lists live only in the app's own API, not in any tracked file. Left in place, it would have
silently re-added anime series on its next refresh and undone the whole removal.

Quality profile deletion surfaced a second gap: 15 ordinary movies (*The Untouchables*,
*Highlander*, *Midnight Run*, etc.) and 17 of their TMDb collections were parked on quality
profile id 7 for reasons unrelated to anime (likely an old profile-id reuse), which blocked
`DELETE /api/v3/qualityprofile/7` with "QualityProfile in use" until all 32 were reassigned to
the general-library default (profile 9, `Remux + WEB 2160p`) - confirming the original
discovery pass's `qualityProfileId==7` OR-clause was too loose and would have wrongly deleted
15 real, unrelated movies if used as the deletion filter instead of root-folder path.

3 Sonarr series (`JUJUTSU KAISEN`, `Frieren - Beyond Journey's End`, `Hunter x Hunter 2011`)
had their DB records deleted cleanly by `deleteFiles=true` but left symlink-only folders behind
on disk (a stale-mount edge case, not a real data-loss risk since Sonarr no longer referenced
them) - removed by hand after confirming zero real files.

**v10.20.0** (current): DebridMediaManager (self-hosted) removed entirely, by explicit
request. Four services gone (`dmm-mysql` - 4GB real MySQL data, not debrid-backed, permanently
deleted with no dump kept per explicit instruction; `dmm-redis`; `dmm-migrate`;
`debridmediamanager` itself), plus `scripts/import-imdb-data.py` and its daily
`stack-imdb-sync` systemd timer (existed solely to feed `dmm-mysql`'s search index - no other
consumer). Control Panel lost its `/api/dmm/status` route, `pymysql`/`cryptography` from
`requirements.txt` (no longer used by anything), its `CONTAINER_LABELS` entries, and the
`debridmediamanager` dashboard tile + `stack-dmm-status` CLI command. `.env`/`.env.example`
dropped `DMM_MYSQL_ROOT_PASSWORD`/`DMM_MYSQL_PASSWORD`/`DMMCAST_SALT`/`DMM_ORIGIN` outright,
plus `MDBLIST_KEY`/`OMDB_KEY`/`TRAKT_CLIENT_ID`/`TRAKT_CLIENT_SECRET`/`GH_PAT` - initially
assumed shared with Kometa per this file's own then-current wording ("Kometa and DMM already
share"), but verified false: Kometa's `config.yml` carries its own independent hardcoded
copies of those same key values, not `${VAR}` substitution, so these five were DMM-exclusive
plumbing with zero remaining consumers anywhere in the repo once DMM's `docker-compose.yml`
block was gone - a real correction made mid-execution, not assumed.

**Explicitly kept, by design, not an oversight**: Zilean's own `Zilean__Dmm__EnableScraping`
(scrapes DMM's public hashlist website as a second cache-hash source, unrelated to the
self-hosted app) and Control Panel's `/api/zilean/search` (calls *Zilean's* `/dmm/search`
endpoint, not the removed app) - same name, different feature, confirmed via source before
touching anything.

A removal-script bug caught mid-execution: the first attempt at renumbering the service table
matched `zurg`'s row too, because its sponsor image path
(`ghcr.io/debridmediamanager/zurg@...`) contains the literal substring "debridmediamanager" -
a pure naming collision, same class of false positive as the anime purge's "URANiME" release
group. Caught by a row-count sanity check against the diff, not assumed clean; zurg's row was
restored before committing. Service table: 31 → 27 rows (13 core / 14 extras).

**v10.21.0**: Control Panel's front end got a full aesthetic redesign, by explicit
request - functionally identical (every `id`/class `app.js` depends on was audited and kept
exactly, confirmed via a grep of every `getElementById`/`classList` call before touching
anything), only `static/{style.css,fx.js,index.html}` changed. Replaced the previous "LAST
LIGHT" theme (deep red/ash-black bunker palette, chromatic-aberration glitch title, animated
canvas embers, CRT scanlines, periodic klaxon flicker) with a master-control-room/broadcast-
rack identity: cool graphite-steel background, amber/green/red indicator-lamp palette (the
literal VU-meter/patch-bay LED colors, not a generic dark-mode default), Barlow Semi
Condensed for chrome/labels paired with IBM Plex Mono for data/log readouts, segmented LED
bargraphs in place of smooth progress bars, corner-rivet detailing on the Rapid Deploy cards
specifically (not applied everywhere, to avoid overdoing the motif). Atmosphere simplified to
a single static grain texture painted once (no per-frame canvas loop, unlike the old embers)
plus a one-time power-on flicker on the title at load, replacing the old infinite-loop
glitch/scanline/flicker layers - quieter and cheaper to render.

Two real things surfaced during verification, not assumed clean:

`control-panel`'s static assets are baked into the image at build time (`COPY` in its
Dockerfile), not bind-mounted - a plain `docker compose restart` served the old CSS/JS
untouched even after the files changed on disk; needed `docker compose build control-panel &&
docker compose up -d --force-recreate control-panel` to actually pick up the new files, the
same rebuild step this file's own Commands section already documents for `app.py` changes,
just not obviously extended to `static/` before this.

A `mix-blend-mode: overlay` on the fixed, full-viewport noise canvas was suspected of causing
a real compositor bug (screenshots came back solid black at some scroll depths) and was
provisionally blamed - but isolating each fixed-position atmosphere layer independently
(hiding the canvas alone, then the vignette alone, then both) showed the blank capture still
reproduced with both hidden entirely, purely as a function of scroll depth. Live DOM/computed-
style inspection at those same scroll positions confirmed real, correctly-styled, visible
content (opacity 1, correct colors, non-zero dimensions) was actually there - a screenshot-
tool capture limitation on a tall page, not a rendering bug in the page itself. `mix-blend-
mode: overlay` was kept rather than removed, since isolating it disproved it as the cause;
noted here so a future session doesn't re-diagnose the same red herring.

**v11.0.0**: Torrent and debrid support removed entirely, by explicit request -
every future acquisition goes through NzbDAV/Usenet, no exceptions. Six services gone
(`decypharr`, `decypharr-alldebrid`, `zurg`, `rclone-alldebrid`, `zilean`, `zilean-postgres`),
plus `byparr` once confirmed no remaining Usenet indexer referenced it via tags/`indexerProxy`
(none did). All 49 enabled torrent indexers plus the `Zilean` Torznab entry disabled then
deleted from Prowlarr, in that order, so the change stayed verifiable and reversible at each
step. Both `*arr` apps' Decypharr download-client entries and delay-profile `enableTorrent`
flags removed; Sonarr's decypharr-alldebrid Remote Path Mapping (the one deliberate exception
to this stack's "no remote path mappings" convention) deleted with it. `docker image prune`
reclaimed ~6GB after the six containers were removed.

**A real, live consequence found mid-execution, not anticipated in planning**: Zurg and
Decypharr never downloaded real bytes - they symlinked into a FUSE mount streaming directly
from Real-Debrid/AllDebrid, so stopping those containers immediately broke playback for the
616 files (3.65% of the library, mostly premium 2160p Remux titles) sourced through them, not
just future acquisitions. Surfaced and confirmed with the user mid-removal before continuing;
accepted as a known consequence rather than reversed. See
[Known gaps and limitations](#known-gaps-and-limitations) for the current state of those
files and Plex's own now-dead `/mnt/zurg/shows` library Location.

Recreating `nzbdav-rclone` and its now-five mount-dependent containers (Radarr, Sonarr, Plex,
Unpackerr, Cleanuparr all switched from a blanket `/mnt` bind or Decypharr-specific mounts to
the same narrow `/mnt/nzbdav` subpath bind) in the same batch reproduced the exact FUSE
stale-mount bug this file already documented for Radarr alone - confirmed live, not just
theorized: every dependent failed to start (`transport endpoint is not connected`) until
`nzbdav-rclone` was restarted alone first and the stale host mount cleared with `sudo umount
-l /mnt/nzbdav`. `MOUNT_DEPENDENTS` grew from `{"radarr"}` to all five to match. (NeutArr's
long-standing OOM-kill-every-30-minutes issue, raised 512m → 1g, was fixed in an earlier,
unrelated session the same day - not part of this removal - see
[Known gaps and limitations](#known-gaps-and-limitations).)

Control Panel lost six endpoints (`/api/zilean/stats`, `/api/zilean/search`,
`/api/decypharr/grab`, `/api/zurg/classify`, `/api/decypharr/health/{instance}`,
`/api/decypharr/{instance}/torrents`) plus the Zurg-specific `/api/content-audit/{library}`,
its `psycopg2` dependency (no other Postgres consumer left), and every `CONTAINER_LABELS`/
`MOUNT_*`/`KNOWN_MOUNTS` entry for the removed services. Six fish functions deleted
(`stack-decypharr-health`, `stack-decypharr-torrents`, `stack-grab`, `stack-zilean-search`,
`stack-zurg-classify`, `stack-content-audit`); `stack-dmm-status` also deleted as unrelated
cleanup, a dead leftover from the v10.20.0 DMM removal that had never been taken out of
`stack-help`. `scripts/backup-config.sh` lost its `zilean-postgres` logical-dump step (the
database it backed up no longer exists); `scripts/setup_wizard.py`'s `AUTO_GENERATE_KEYS` is
now empty (was `ZILEAN_POSTGRES_PASSWORD`/`ZILEAN_API_KEY`). `config/decypharr/`,
`config/decypharr-alldebrid/`, `config/zurg/`, and `config/zilean-postgres/` deleted after
backing up their real API keys/tokens outside the repo.

**v11.1.0**: Full disaster-recovery restore executed 2026-07-20 onto a fresh CachyOS
install (the deliberate destructive ext4 reinstall this stack's own disaster-recovery runbook
had been prepared for), plus the same-day cleanup it enabled. `Claude-FULL-backup-20260720.tar.zst`
(~108GB, the uncut `~/Claude` tree including `media-stack/config`) restored via Dropbox
sync rather than a single-shot download link (the link tool's 15-minute expiry isn't viable for
a file that size); all 15 `.db`/`.sqlite`/`.sqlite3` files then overwritten with their
SQLite-online-backup-API snapshots (guaranteed-consistent, unlike the live tar copies) and
verified via `PRAGMA integrity_check`. `nzbdav-rclone` crash-looped on first boot with
`mountpoint does not exist: /mnt/nzbdav` - a fresh host never has that directory, unlike the old
install where it silently persisted across reinstalls; see [Backup/DR details](CLAUDE.md) in
`CLAUDE.md` for the fix and why it isn't covered by any backup script. Sonarr's automatic
missing-episode search was briefly (and incorrectly) suspected of mass-re-grabbing due to a
restore regression - stopped as a precaution, then a full tar-vs-disk cross-check showed all
341 shows with real backed-up content matched disk exactly; the apparent regression was one
show (RuPaul's Drag Race) that had never had any downloaded episodes before the wipe either.
Sonarr restarted once confirmed safe. Separately, the 616-file dead-debrid-symlink gap open
since the v11.0.0 removal (see [Known gaps and limitations](#known-gaps-and-limitations)) was
finally re-acquired as part of this same session - 611 files found, matched to their Radarr/
Sonarr file records, and cleared for normal re-download.

**v11.2.0**: Radarr and Sonarr consolidated down to a single "ANY" quality profile
each, by explicit request - every other profile deleted on both apps (Sonarr:
`WEB-1080p`/`WEB-2160p`/`Low Quality`; Radarr: `HD Bluray + WEB`/`Remux + WEB 2160p`/
`Low Quality`). Neither app's API allows deleting an in-use profile, so everything referencing
the old profiles was reassigned to `ANY` first: all 708 Sonarr series and all 16,936 Radarr
movies via each app's bulk `series`/`movie` editor endpoint, plus - less obviously - both
apps' import lists (each carries its own default quality profile for newly-added items) and,
Radarr-only, all 1,299 Collections (no bulk editor exists for these; updated one at a time via
`PUT /api/v3/collection/{id}}`). Recyclarr - the daily-cron TRaSH-Guides sync that managed the
now-deleted profiles - was removed entirely in the same pass: `docker-compose.yml` service
block, `config/recyclarr/`, Control Panel's `CONTAINER_LABELS` entry and `/api/recyclarr/status`
route, the `stack-recyclarr-status` fish function (deleted from both this host and its
`dotfiles-cave` source repo), and every skill doc (`trash-guides-applier`, `arr-config-sync`,
`stack-cli-usenet-queue`) that assumed it was still running.

Beszel/`beszel-agent` (host/container resource monitoring) and Labelarr (TMDb-keywords-as-
Plex-labels) were also removed entirely, by the same explicit request, following the same
recipe: compose service blocks, `config/beszel`/`config/beszel-agent`/`config/labelarr`
(all three gitignored, not tracked in git to begin with), Control Panel's `CONTAINER_LABELS`
entries, the `BESZEL_*`/`TMDB_READ_ACCESS_TOKEN` `.env`/`.env.example` variables (the latter
confirmed unused by anything else before deletion), and the containers/images themselves. The
host firewall rule opened for Beszel's port 8090 earlier the same day was deleted along with
it; Labelarr's port 9090 was never LAN-exposed (bound to `127.0.0.1` only) so needed no
firewall change either way. Service count: 20 → 16.

**v11.3.0** (current): Bazarr reinstalled - a from-scratch install, not a restore, since no
`config/bazarr` state survived the v10.2.0 removal. `docker-compose.yml` service block added
(port 6767, extras profile, `./config/bazarr`/`./media/movies`/`./media/shows` mounts, no
prior baseline so `mem_limit` matched to Tautulli's 512m as the nearest comparable companion
app). Wired to both Radarr and Sonarr via their existing API keys (Bazarr has no env-var
config path for this - done post-boot through its `/api/system/settings`
form-encoded endpoint, undocumented in its own Swagger spec; note for future config-via-API
work here: that endpoint's boolean fields require lowercase `true`/`false` strings, not
Python-style `True`/`False` - the latter fails dynaconf's type validator with a misleading
"must is_type_of bool but it is True" error). A single "English" languages profile (id 1,
non-forced, non-HI) was created and set as the default profile for both new movies and new
series so every existing/future library item picks it up automatically. Every bundled
subtitle provider that needs zero account/API key/passkey was enabled (39 total, cross-checked
against each provider's own Python `__init__` signature inside the container rather than
assumed from memory) - excluded: HDBits, AvistaZ/AvistaZ Network/Cinemaz, Karagarga (all
private-tracker-gated), Addic7ed/OpenSubtitles.com/SubDL/SubSource/SubX/Assrt/Betaseries/
Napisy24/Titlovi/Titulky/Ktuvit/Legendasdivx/LegendasNet/XSubs (each needs a registered
account or API key), Jimaku (requires an API key), WhisperAI (a transcription fallback, not a
subtitle source, needs its own endpoint). Gestdown (Addic7ed's anonymous-access mirror) was
enabled in Addic7ed's place for English TV subs. Both libraries synced in immediately (5,548
movies, 79 series) and a full local-subtitle index kicked off for both; the actual
missing-subtitle download search was left to Bazarr's own scheduler (default every 6h) rather
than forced synchronously, since a first-run search across the full library against 39
providers is a multi-hour operation better left backgrounded than blocking on. Known
limitation, not a bug: Radarr/Sonarr custom formats can't see actual embedded subtitle tracks
pre-download (that data only exists post-grab), so the "Block: Foreign Audio w/o English Subs"
custom format added the same session to both apps' quality profiles is a release-title-regex
approximation, not a real substitute for Bazarr actually managing subtitles after the fact -
the two are complementary, not redundant. Same session, same both-apps scope: all anime-only
custom formats removed (35 from Sonarr, 27 from Radarr - BD/Web anime tiers, Raws, LQ Groups,
Uncensored, v0-v4 fansub versioning, 10bit, Dual Audio, Dubs Only, VOSTFR, and Sonarr's
anime-exclusive streaming-service formats CR/VRV/FUNi/ABEMA/ADN/B-Global/Bilibili/HIDIVE/WKN),
and a "Prefer Season Packs" custom format (`ReleaseTypeSpecification` = Season Pack, +25) was
re-added to Sonarr after being lost in v11.2.0's quality-profile consolidation.

**v11.4.0**: Bazarr's provider list narrowed from the 39 enabled in v11.3.0 down to
9, in two follow-up passes - first removing every single-region/single-language site that
doesn't carry English subtitles at all (Bulgarian, Romanian, Croatian, Greek, Turkish, Hebrew,
Chinese, Latvian, Hungarian, Indonesian, Polish, Spanish, French, Persian - 28 providers),
then removing the one remaining anime-exclusive source (`animetosho`, a torrent-based anime
indexer). Final list: `bsplayer`, `embeddedsubtitles`, `gestdown`, `subf2m`, `subs4free`,
`subs4series`, `subsarr`, `tvsubtitles`, `yifysubtitles` - all either English-first sites or
language-agnostic (`embeddedsubtitles`/`subsarr`).

Maintainerr removed entirely, by explicit request (never used) - `docker-compose.yml` service
block, `config/maintainerr` (never gitignored-only local state, no real secrets to preserve),
Control Panel's `MAINTAINERR_URL`, `CONTAINER_LABELS` entry, `/api/maintainerr/rules` route,
and its Quick Links entry, the `stack-maintainerr-rules` fish function and its `stack-help`
listing, and its `commands.json` CLI-command entry. The only port-6246 rule found on the host
was Docker's own auto-managed DNAT/nftables entry for the published port - confirmed it
cleans up automatically on container/network removal, not a separate manual firewall rule
needing its own cleanup (unlike Beszel's v11.2.0 removal, which did have one). Bazarr picked
up Maintainerr's Quick Links slot in Control Panel's dashboard, since it never had one of its
own from the v11.3.0 reinstall - a gap from that session, closed here rather than left for a
separate pass.

**v11.5.0** (current): ~40 new `stack-*` fish commands added - list-import wrappers around
native Radarr/Sonarr import-list implementations that were installed but never configured
(Plex watchlist/RSS, Simkl/TMDb-user/Trakt-user OAuth families via token reuse from an already-
authenticated list on the same app, TMDb company/keyword lists, generic Sonarr `CustomImport`
and `RadarrListImport` URL wrappers), four Bazarr operational commands (wanted, on-demand
missing-subtitle search, history, per-provider throttle status), a Tautulli 30-day stats
command, an on-demand restic integrity check, a custom-format score differ (caches the last
snapshot locally, since neither app has a native change log for API-driven score edits), and
`stack-nzbdav-delete-failures` (deletes every "Failed" NzbDAV history entry on demand - the
same job `stack-nzbdav-prune-history.timer` already runs every 4h; first live run cleared
6,631 stale entries). Plus 3 host-diagnostic commands (git status across every repo under
`~/Claude`, an SSH setup doctor, stack timer health) and 20 system-maintenance/package-
management commands (pacman/AUR updates and orphan/cache cleanup, kernel-mismatch and pending-
reboot checks, SMART disk health, disk-free thresholds, journal error summarization and
vacuuming, failed-systemd-unit listing, a consolidated cron/timer view, firewall/listening-port
status, zombie-process check, PSI pressure-stall snapshot, Docker disk usage, Flatpak updates,
uptime/last-boot report, and an arch-audit wrapper).

A planned Wikipedia-list-import command (scraping "List of highest-grossing films"-style
wikitables) was designed, then dropped after live testing: Wikimedia's edge blocks Python
`httpx` at the client-fingerprint level regardless of User-Agent or even a policy-compliant
bot identification string through their own documented API - confirmed via two separate tests
from inside the Control Panel container, both a raw page fetch and `action=parse` through
`api.php`, both 403 with an explicit "respect our robot policy" message. `curl` from the host
itself gets a clean 200 on the identical URL - this is a TLS/HTTP client fingerprint
distinction, not a UA or IP-based block, and not something worth working around.

A second real bug surfaced independently while building these: `docker-compose.yml`'s
`control-panel` service still bind-mounted `/home/daddybear/backups` and
`/home/daddybear/Dropbox/stack-restic-repo-offsite` - the same stale pre-reinstall username
already fixed once this session in `.env`'s `BACKUP_REMOTE_REPOSITORY`, missed here because it
was a separate file. This silently broke `stack-backup-verify`/`stack-backup-status` (both
reported "missing"/"error" against paths that no longer existed) until caught live and fixed.

**A genuine backup incident happened investigating that fix, not before it**: the offsite
restic repo (freshly initialized and backed up with a real 103GB/213,943-file snapshot
earlier the same session) was found completely empty - on local disk *and* confirmed via the
Dropbox API directly against the cloud side, both at the identical timestamp. Root cause:
`backup-config.sh`'s offsite leg runs `restic` under `sudo` (needed to read Plex's mode-600
config files), which left every object in the repo root-owned - inside `~/Dropbox`, a folder
Dropbox's own sync daemon manages running as the regular user, not root. A sync client unable
to read most of a folder's own content appears to have reset it rather than partially
syncing. Fixed by `chown`-ing the offsite repo back to the invoking user immediately after
every backup and prune call in `scripts/backup-config.sh` - a later `sudo restic` call against
it still works fine (root can always read a user-owned file; only the reverse was ever the
problem). Re-initialized and re-backed-up after the fix, confirmed actually reaching Dropbox's
cloud this time before moving on.

**This stack's CLI was privatized the same session**: `StackMaster` (github.com/WhispersOfJ/
StackMaster, the standalone redistributable CLI + control panel that superseded
`Stackalicious`/`StackScripts`) was deleted outright from GitHub at the user's explicit
request, and its local clone removed. Every `stack-*` command - all ~100 of them at this
point - now lives only in this host's own fish functions plus this repo's
`control-panel/app.py`; there is no downstream sibling to keep in sync anymore, and
`AGENTS.md` was rewritten accordingly. Pre-existing uncommitted work in that deleted clone
(an unrelated in-progress `stack-queue-status` "Totals" section, never pushed anywhere) was
confirmed with the user before being allowed to go with it rather than silently discarded.

**v11.5.1**: `stack-tui` (github.com/WhispersOfJ/stack-tui, a terminal UI front end over the
same Control Panel API the fish CLI drives) deleted outright from GitHub and its local clone
removed, following the same privatization request - its own README described it as the third
layer of a four-repo chain requiring `Stackalicious`/`StackScripts` to already be running,
both deleted earlier this session, so it had no working dependency chain left regardless.
Clean working tree beforehand, nothing lost. No other file in this repo referenced it outside
one already-historical [History](#history) entry (the 2026 sync noting its command list was
regenerated to 69 commands), left untouched rather than rewritten - past entries here record
what was true at the time, not what's true now.

**v11.6.0**: Plex deep-media-analysis support added, prompted by a live check confirming the
account carries an active Plex Pass subscription (`myPlexSubscription="1"` via `/` -
independent of the `plexinc/pms-docker` image's *update channel*, which stays on public per
the Image pinning policy below; the two are unrelated settings). A per-library audit
(`/library/sections/{key}/prefs`) found Movies already had every analysis setting on
(`enableBIFGeneration`, `enableCreditsMarkerGeneration`, `enableAdMarkerGeneration`,
`enableVoiceActivityGeneration`), while TV Shows had three of five off against the
library-type default - fixed via a `PUT` to the same endpoint, confirmed by reading the
settings back afterward rather than assuming the write took.

Two new Control Panel routes and 22 new `stack-*` commands followed, all confirmed live
against the running Plex container (not assumed from Plex's docs):

- **`/api/plex/analyze`** (`stack-plex-analyze [library ...]`) - `PUT
  /library/sections/{key}/analyze`, queues deep analysis (loudness, chapter thumbnails,
  intro/credits/ad markers, voice activity) for one named library (case-insensitive title
  match, same convention as `stack-plex-empty-trash`) or every library if none given. This is
  the *section-scoped* trigger - use it to re-analyze just the library whose settings above
  were just changed, without touching the rest of the server.
- **`/api/plex/butler/{task}`** (`stack-plex-butler <task>`, plus one dedicated
  `stack-plex-<task>` wrapper per task) - fires any single Plex Butler maintenance task on
  demand via `POST /butler/{PlexTaskName}`. The full task list was read live from this
  server's own `GET /butler` (not guessed or taken from Plex's docs, which don't fully
  enumerate internal task names) and mapped to kebab-case aliases in `PLEX_BUTLER_TASKS`:
  - `stack-plex-deep-media-analysis` - the whole-server counterpart to `stack-plex-analyze`
    above (`DeepMediaAnalysis`); runs full deep analysis across every library in one pass,
    not just one section.
  - `stack-plex-backup-database` (`BackupDatabase`) - backs up Plex's database to its
    configured backup directory on demand, rather than waiting for its own schedule.
  - `stack-plex-clean-log-files` (`ButlerTaskCleanSupplementalLogFiles`) - deletes old
    supplemental Plex log files.
  - `stack-plex-generate-ad-markers` (`ButlerTaskGenerateAdMarkers`) - generates ad-break
    markers for eligible media.
  - `stack-plex-generate-credits-markers` (`ButlerTaskGenerateCreditsMarkers`) - generates
    end-credits markers for eligible media.
  - `stack-plex-generate-intro-markers` (`ButlerTaskGenerateIntroMarkers`) - generates intro
    markers for eligible media.
  - `stack-plex-generate-voice-activity` (`ButlerTaskGenerateVoiceActivity`) - generates
    voice-activity data (used for Plex's dialogue-boost audio feature).
  - `stack-plex-clean-cache-files` (`CleanOldCacheFiles`) - deletes old Plex cache files.
  - `stack-plex-garbage-collect-blobs` (`GarbageCollectBlobs`) - garbage-collects unused
    metadata blobs.
  - `stack-plex-garbage-collect-media` (`GarbageCollectLibraryMedia`) - garbage-collects
    unused library media records.
  - `stack-plex-generate-chapter-thumbs` (`GenerateChapterThumbs`) - generates chapter
    thumbnail (BIF) preview-image files.
  - `stack-plex-generate-media-index` (`GenerateMediaIndexFiles`) - generates media index
    files Plex uses for fast seeking.
  - `stack-plex-loudness-analysis` (`LoudnessAnalysis`) - analyzes audio loudness for volume
    leveling.
  - `stack-plex-music-analysis` (`MusicAnalysis`) - analyzes music library audio (moot while
    this stack has no music library, kept since the task still exists on the server).
  - `stack-plex-process-assets` (`ProcessAssets`) - processes pending local assets (posters,
    themes, etc).
  - `stack-plex-refresh-epg` (`RefreshEpgGuides`) - refreshes Live TV/DVR EPG guide data (moot
    while this stack runs no tuner, same reasoning as music analysis above).
  - `stack-plex-refresh-libraries` (`RefreshLibraries`) - refreshes metadata for every
    library; distinct from `stack-plex scan`, which only looks for new files on disk.
  - `stack-plex-refresh-local-media` (`RefreshLocalMedia`) - refreshes local media file
    changes.
  - `stack-plex-upgrade-media-analysis` (`UpgradeMediaAnalysis`) - re-runs analysis only for
    items whose analysis version is outdated, rather than everything.
  - `stack-plex-automatic-updates` (`AutomaticUpdates`) - triggers Plex's own app-update
    checker; unrelated to library media, included for completeness since it's one of the
    tasks the live server advertises.

  `OptimizeDatabase` and `CleanOldBundles` already had dedicated routes/commands
  (`stack-plex optimize-db` / `stack-plex clean-bundles`, see above) before this version, so
  they were left out of `PLEX_BUTLER_TASKS` rather than given a second, duplicate path to the
  same task.

Plex's own version was checked as part of this work (`stack-plex-updates`): running
`1.43.3.10828-00f62d37d` with no update available on its current (public) channel - already
current, no action needed.

**v11.7.0** (current): Plex removed entirely, replaced by Jellyfin
(`lscr.io/linuxserver/jellyfin:latest`, new `jellyfin` service - same table position, same
core profile, no `network_mode: host`, bridge networking on `stacknet` instead). Two libraries
carried over exactly: Movies (`/data/movies`), Shows (`/data/shows`); same VAAPI
hardware-transcode device (`/dev/dri/renderD128`). Metadata providers: TheMovieDb + OMDb on
Movies, TheTVDB + TheMovieDb + OMDb on Shows - OMDb ships bundled with Jellyfin core already
active, not a separate catalog install, a correction made mid-session after an earlier draft
plan wrongly assumed it needed installing. Plugins installed: Playback Reporting, Chapter
Segments Provider, TMDb Box Sets (official catalog), plus two third-party plugins - Intro
Skipper (`https://intro-skipper.org/manifest.json`) and a "Bazarr" plugin
(`https://raw.githubusercontent.com/enoch85/bazarr-jellyfin/main/manifest.json`) - all five
pending a container restart to load.

Jellystat (`cyfershepard/jellystat:latest`) plus its own Postgres (`jellystat-db`,
`postgres:18.1`) added as Tautulli's Jellyfin-equivalent, since Tautulli is Plex-only - this
stack's first Postgres dependency since `zilean-postgres` was removed in v11.0.0. Not yet given
a logical-backup step - a known gap, see [Known gaps and limitations](#known-gaps-and-limitations).
Two real bugs found and fixed on first start: `postgres:18+` crash-looped against the usual
`./config/jellystat-db:/var/lib/postgresql/data` mount convention ("PostgreSQL data in an old,
unsupported location" - 18+ manages its own version-specific subdirectory under a single
`/var/lib/postgresql` mount, confirmed via the container's own log output), fixed by mounting
`/var/lib/postgresql` directly instead after clearing the partially-initialized data directory;
`jellystat`'s own healthcheck (`curl -sf http://localhost:3000/`) failed every time with
`curl: not found` - this image has no `curl`, only `wget` (confirmed via `docker exec`), fixed
by switching the test to `wget -qO- http://localhost:3000/ >/dev/null 2>&1 || exit 1`. Both
containers are up and healthy, and Jellystat's own first-run setup is **complete** - confirmed
directly via `jellystat-db`'s `app_config` table (real `JF_HOST`/`JF_API_KEY`, admin user
matching Jellyfin's real user ID, sync tasks scheduled) and a populated `jf_library_items`
table (7,799 rows), not just assumed from the containers being up. **Tautulli itself was
removed entirely** on the same follow-up request as Kometa below: compose block,
`config/tautulli/` (263MB, no credentials of note, deleted with no backup), and its
`control-panel/app.py` container-listing entry all gone; its two `/api/tautulli/*` routes
(history, stats) were left as documented dead code rather than reworked (unlike the former
`/api/plex/*` routes, later fully reworked against Jellyfin's API in this same entry below),
since they already 503 gracefully and Jellystat covers the same role now.
Seerr was also repointed at Jellyfin the same session (`main.mediaServerType` switched to
`2`/`JELLYFIN`, confirmed against `seerr-team/seerr`'s own `server/constants/server.ts`; a
stale browser session cookie masked the first login attempt since Seerr's JWT auth is
stateless, not tied to the user record; the new account only got `permissions: 32` instead of
admin since Seerr only auto-grants admin to the very first user ever created and this instance
already had one, fixed by setting `permissions: 2` directly in `config/seerr/db/db.sqlite3`'s
`user` table with the container stopped first; the old Plex-linked account's 144 real
`media_request` rows were reassigned to the new account before deleting the dead row, not
dropped).

**Kometa cannot talk to Jellyfin at all** - confirmed directly against
`kometa-team/kometa`'s own `config-schema.json`, which has no `jellyfin`/`emby` top-level
property, only `plex`, contradicting several blog-post sources (jellywatch.app etc.) claiming
otherwise; real Jellyfin support is an open, unimplemented feature request
(features.jellyfin.org/posts/2899). Kometa and Quickstart were initially just stopped
(`docker compose stop kometa quickstart`, config/compose untouched; Quickstart's
now-meaningless `./config/plex:/plex-config` mount removed from its compose block) - then, at
explicit follow-up request the same session, **removed entirely**: both compose service blocks
deleted (the `kometa:` and `quickstart:` blocks, plus referencing comments elsewhere in the
file); `config/kometa` (901MB) and `config/quickstart` (469MB) deleted from disk.
`config/kometa/config.yml` was backed up first to
`~/backups/removed-configs/kometa-config.yml.bak-2026-07-22` - unlike Plex's config (pure
app-internal state), this file held real third-party credentials with no other copy anywhere: a
Trakt client ID/secret and a GitHub personal access token, plus the OMDb and MDBList API keys.
The OMDb and MDBList keys were promoted to real standalone `.env`/`.env.example` secrets
(`OMDB_KEY`, `MDBLIST_KEY`) since `control-panel/app.py`'s
`/api/ratings/imdb` and `/api/ratings/mdblist` endpoints used to read them live off Kometa's
config file via a `_kometa_config()` helper - that helper is deleted, replaced by direct
`os.environ.get("OMDB_KEY")`/`os.environ.get("MDBLIST_KEY")` reads; both new env vars are also
wired into `control-panel`'s compose `environment` block. `control-panel/app.py`'s
`/api/kometa/run` route and its `KometaRunRequest` Pydantic model were deleted outright - no
missing-env-var 503 fallback existed for this one to degrade into, unlike the still-pending
Plex routes, so this endpoint simply no longer exists (404). `CONTAINER_LABELS` lost its
`"kometa"`/`"kometa-quickstart"` entries; a few now-dead comments elsewhere in `app.py` that
referenced "Kometa's own config.yml" were reworded to describe the OMDb/MDBList migration
instead of asserting Kometa still exists. Net result: **no automated Plex/Jellyfin collections,
overlays, or metadata-enrichment tool of any kind currently runs in this stack.** Service
table: 18 → 16 rows.

Bazarr reconfigured for Jellyfin via its usual undocumented `POST /api/system/settings`
endpoint: `general.use_jellyfin=true`, `jellyfin.url`/`apikey`, library IDs mapped by name,
`update_movie_library`/`update_series_library=true`; `general.use_plex` set `false`. Watch-
history migration (`qdm12/plex-to-jellyfin`) was attempted, then explicitly abandoned by the
user's own decision - Jellyfin starts with no migrated watch history/ratings, a clean start,
deliberate.

Systemd units and scripts removed entirely: `stack-plex-webhook.service`,
`stack-plex-report.service`, `stack-plex-report.timer` (all three live, active, enabled),
`scripts/plex-webhook-listener.py`, `scripts/plex-library-report.py`.
`.env`/`.env.example`'s `PLEX_URL`/`PLEX_TOKEN`/`PLEX_WEBHOOK_PORT` removed, replaced by
`JELLYFIN_URL`/`JELLYFIN_API_KEY`. `config/plex/` (34GB, including the Plex Media Server
SQLite database with all watch history/ratings/metadata) and `config/plex-transcode/` were
permanently deleted at the user's explicit request, no archive kept.

A real, unrelated discovery made mid-migration while auditing Plex's Movies library before
decommissioning it: only 59-63 items were indexed against ~10,004 real files on disk, traced to
a single 2026-07-13 `Plex Media Scanner.log` event that removed 661 of 794 tracked items in one
pass with `autoEmptyTrash` confirmed on. Very likely the missing Plex-side half of this
project's own long-unexplained mass Radarr/Sonarr library-loss event (see
[Known gaps and limitations](#known-gaps-and-limitations)) - confirmed not caused by the
same-day NzbDAV connection-leak bug. Since Plex is now gone, this can't be root-caused further.

**Closed out in the same overall migration effort, slightly later** (all verified live, not
just read for syntax): all 14 former `/api/plex/*` routes reworked against Jellyfin's real
API (see [Control Panel](#control-panel) above for the full route-by-route mapping);
`MOUNT_DEPENDENTS` fixed; Seerr repointed at Jellyfin (`mediaServerType` switched, admin
account re-linked after a stale-session-cookie false start, the old Plex-linked account's 144
requests reassigned before deleting the dead row); poster sync reworked against Jellyfin's
`ProviderIds`/image-upload API; `scripts/setup_wizard.py`'s `POST_BOOT_KEYS`/`REQUIRED_KEYS`
fixed; every `stack-plex-*`/`stack-kometa-*`/`stack-tautulli-*` fish function reworked or
removed; `jellystat-db` given real logical-backup coverage; real VAAPI hardware transcoding
confirmed working via an actual `ffmpeg` process, not just configured. See
[Known gaps and limitations](#known-gaps-and-limitations) for the one genuinely remaining
item (no Jellyfin-side equivalent for the two deleted Plex alerting scripts).
