# The Stack

Current version: **v10.14.0**

A Docker Compose media-acquisition-and-serving stack. Indexes, requests, and symlinks
already-cached content from Real-Debrid / AllDebrid, falls back to Usenet (streamed, not
downloaded) on cache misses, and serves the result through a containerized Plex. 30 services,
one compose file, every image pinned and healthchecked. Two operator surfaces: a custom
dashboard (Control Panel) and a custom CLI (`stack-*` fish functions).

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
- [The debrid pipeline: Zurg + Decypharr](#the-debrid-pipeline-zurg--decypharr)
- [The Usenet pipeline: NzbDAV](#the-usenet-pipeline-nzbdav)
- [Indexing: Prowlarr, Zilean, Byparr](#indexing-prowlarr-zilean-byparr)
- [Requests: Seerr](#requests-seerr)
- [Plex](#plex)
- [Bindery and Calibre-Web: retired](#bindery-and-calibre-web-retired)
- [Custom formats and quality profiles](#custom-formats-and-quality-profiles)
- [DebridMediaManager (self-hosted)](#debridmediamanager-self-hosted)
- [Automation extras: Kometa, Cleanuparr, NeutArr, Unpackerr, Watchtower](#automation-extras-kometa-cleanuparr-neutarr-unpackerr-watchtower)
- [Monitoring extras: Tautulli](#monitoring-extras-tautulli)
- [Maintainerr: Plex library lifecycle](#maintainerr-plex-library-lifecycle)
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

Point this at a Real-Debrid and/or AllDebrid account and it wires together: an indexer layer
(Prowlarr + Zilean's DMM cache-hash index), a request front-end (Seerr), two `*arr` apps
(Radarr, Sonarr; Lidarr was removed in v10.9.9 and Whisparr in v10.12.0, see
[History](#history)), a debrid gateway that symlinks already-cached content instead of
downloading it (Decypharr + Zurg), a Usenet fallback that streams rather than downloads
(NzbDAV), a containerized Plex, a self-hosted DebridMediaManager, and automation/monitoring
extras (Kometa, Cleanuparr, NeutArr, Unpackerr, Watchtower, Tautulli, Maintainerr). Ebooks
briefly had a dedicated app (Bindery) plus a reader (Calibre-Web); both were retired in v10.9.8
with no replacement (see
[Bindery and Calibre-Web: retired](#bindery-and-calibre-web-retired)). Adult content
cataloging (Stash) was also removed in v10.12.0, along with Whisparr, which had managed its
underlying library.

Anything already cached on Real-Debrid/AllDebrid shows up as a symlink and plays immediately,
with no download step. NzbDAV covers cache misses as a WebDAV virtual filesystem streamed on
demand, not a local download. NZBGet, which wrote real files to disk, was removed (see
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

# 4. Everything else (Byparr, Tautulli, Kometa, Unpackerr, Watchtower,
#    Cleanuparr, NeutArr, Control Panel, DMM, ...)
docker compose --profile extras up -d
```

Step 2 is optional: `cp .env.example .env && $EDITOR .env` works the same; the wizard is a
form over the same file. Mechanics of the installer image and wizard are in
[Installer image and setup wizard](#installer-image-and-setup-wizard).

Three values can only be collected after first boot, once the relevant app has generated
them: `RADARR_API_KEY`, `SONARR_API_KEY` (each app's **Settings > General > Security**), and
`PLEX_TOKEN` (any library item > **Get Info > View XML**, copy the `token=` value from the
URL). Enter them via a second `--setup` run (it reloads the existing `.env` as defaults),
then:

```bash
docker compose up -d --force-recreate control-panel
```

`control-panel` reads these at container-create time only; a plain `restart` does not pick up
a `.env` change. Use `--force-recreate`.

## Architecture

```
Prowlarr ──indexes──> (your trackers + Zilean's DMM cache-hash list)
   │
   ▼
Radarr/Sonarr ──grab──> Decypharr (qBittorrent-compatible API)
   │                                                        │
   │                                                        ├─> Real-Debrid API  (add magnet)
   │                                                        └─> AllDebrid API    (add magnet;
   │                                                            Radarr pinned to Real-Debrid only,
   │                                                            selected_debrid in
   │                                                            config/decypharr/config.json)
   │                                                        │
   │                                        symlinked into  ▼
   │                                        each app's root folder: ./media/<type> → /data/<type>
   │
   └──(fallback, cache miss only)──> NzbDAV (SABnzbd-compatible API) ──streams via WebDAV──> rclone
                                      mount at /mnt/nzbdav ──symlinked into──> same /data/<type>

Zurg (containerized)             → /mnt/zurg/{movies,shows,music,books,adult}  → read by Plex directly
Decypharr DFS mount              → /mnt/decypharr/{...}                        → symlink target
rclone AllDebrid (containerized) → /mnt/all/{magnets,links,...}                 → already a Plex location
./media/{movies,shows,music,books,adult}  → /data/{...}                        → every app's writable root folder

Plex (network_mode: host, /mnt mounted 1:1 with the host) → Movies: /mnt/zurg/movies
                                                             TV Shows: /mnt/zurg/shows + /mnt/all/magnets
                                                             Music: /mnt/zurg/music (+ intended Audiobooks,
                                                                    see the Plex section below)
```

**Two Decypharr instances.** `docker-compose.yml` runs `decypharr` (port 8282, both debrid
backends, Radarr's download client) and `decypharr-alldebrid` (port 8283,
AllDebrid only, Sonarr's download client). Decypharr has no per-provider category scoping; a
single instance's `debrids[]` list is available to every category on it, so a separate
instance with its own config and mount is what keeps AllDebrid exclusive to Sonarr. The
second instance reports the same-looking `/app/downloads/<category>/...` path to Sonarr as
the primary instance does, but it is a different host directory. Sonarr therefore carries a
second mount (`/app/downloads-ad`) plus a Remote Path Mapping:

```yaml
# docker-compose.yml, sonarr service
volumes:
  - ./config/sonarr:/config
  - /mnt:/mnt:rslave
  - ./config/decypharr/downloads:/app/downloads:rslave
  # decypharr-alldebrid reports outputPath as /app/downloads/<category>/...,
  # identical-looking to the primary decypharr's convention, but a different
  # host directory.
  - ./config/decypharr-alldebrid/downloads:/app/downloads-ad:rslave
  - ./media/shows:/data/shows
```

```bash
# Remote Path Mapping added via Sonarr's API for the Decypharr-AllDebrid
# download client:
curl -X POST http://192.168.4.105:8989/api/v3/remotepathmapping \
  -H "X-Api-Key: $SONARR_API_KEY" -H "Content-Type: application/json" \
  -d '{"host":"decypharr-alldebrid","remotePath":"/app/downloads/","localPath":"/app/downloads-ad/"}'
```

Root folders live on regular host disk (`./media/<type>`), never on Zurg's rclone FUSE mount.
That mount does not accept new files or symlinks (symlink, hardlink, and copy all fail with
`EIO`). This has regressed silently before: a library import/rescan that registers
pre-existing Zurg content can reset that item's root folder back to `/mnt/zurg/<type>` in the
app's own database, which is app state, not stack config, so it never shows in git. If
imports stall, check whether the affected item's root folder resolves to `/mnt/zurg/...`
instead of `/data/...` before assuming a mount or container problem.

> **Radarr-specific mount fragility.** Radarr bind-mounts `/mnt/zurg` and `/mnt/decypharr`
> directly (`/mnt/zurg:/mnt/zurg:rslave`) rather than the parent `/mnt` as Sonarr and Plex do.
> A direct bind of a FUSE mountpoint does not reliably survive the FUSE process
> being recreated underneath it (a Zurg image update, a resource-limit change). Only Radarr
> breaks, with `Socket not connected` inside the container and `accessible: false` from
> `/api/v3/rootfolder`. Fix: `docker restart radarr` after any Zurg recreation. Control
> Panel's whole-stack restart (see [Control Panel](#control-panel)) already sequences this:
> mount providers first, wait for healthy, Radarr last.

> **Disk usage.** Everyday use costs almost no local disk: Plex streams `/mnt/zurg/*` and
> `/mnt/all/*` directly, and the grab pipeline symlinks into `/data/<type>` without copying
> video bytes. The exception is manually importing content that already sits on one of those
> read-only mounts into an app's tracked library: `Hardlink` requires the same filesystem,
> which is impossible from a remote FUSE mount onto local disk, so `Copy` is the only option,
> and it writes a full permanent duplicate. One candidate bulk-import from `/mnt/all/magnets`
> measured 1,801 folders / 26,008 files / 29.8TB against 686GB of free local disk and was
> scrapped. Scope disk space before doing this in bulk.

Seerr (formerly Overseerr/Jellyseerr; the projects merged) is the user-facing request page,
talking to Plex plus Radarr and Sonarr. Zilean searches
[DebridMediaManager](https://debridmediamanager.com)'s shared hash-list of content already
cached on Real-Debrid/AllDebrid, so grabs from it complete near-instantly.

## Directory layout

```
Stack/
├── docker-compose.yml
├── .env                              # PUID/PGID/TZ, every secret referenced below
├── README.md
├── config/<app>/                     # each app's persistent config (gitignored)
├── config/decypharr/config.json      # debrid API keys filled in, chmod 600
├── config/decypharr/downloads/       # shared into every arr app at /app/downloads (identical path)
├── config/zurg/config.yml            # Real-Debrid token, content-routing groups
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
| 2 | `zilean-postgres` | `postgres:18-alpine` | none | core |
| 3 | `zilean` | `ipromknight/zilean:v3.5.0` | 8181 | core |
| 4 | `decypharr` | `cy01/blackhole:v2.3` | 8282 | core |
| 5 | `decypharr-alldebrid` | `cy01/blackhole:v2.3` | 8283 | core |
| 6 | `zurg` | `ghcr.io/debridmediamanager/zurg@sha256:924f17...` | 9999 | core |
| 7 | `rclone-alldebrid` | `rclone/rclone:1.74.4` | none | core |
| 8 | `rclone-alldebrid-anime` | `rclone/rclone:1.74.4` | none | core |
| 9 | `radarr` | `ghcr.io/hotio/radarr:release` | 7878 | core |
| 10 | `sonarr` | `ghcr.io/hotio/sonarr:release` | 8989 | core |
| 11 | `nzbdav` | `nzbdav/nzbdav:latest` | 3001→3000 | core |
| 12 | `nzbdav-rclone` | `rclone/rclone:1.74.4` | none | core |
| 13 | `seerr` | `ghcr.io/seerr-team/seerr@sha256:c92d2d...` | 5055 | core |
| 14 | `plex` | `plexinc/pms-docker:1.43.3.10828-00f62d37d` | 32400 (host net) | core |
| 15 | `byparr` | `ghcr.io/thephaseless/byparr@sha256:01a46a...` | 8191 | extras |
| 16 | `tautulli` | `ghcr.io/hotio/tautulli:release` | 8182 | extras |
| 17 | `control-panel` | built from `./control-panel` | 8420 | extras |
| 18 | `kometa` | `kometateam/kometa@sha256:98a0df...` | none | extras |
| 19 | `unpackerr` | `golift/unpackerr@sha256:4ec141...` | none | extras |
| 20 | `watchtower` | `nickfedor/watchtower:1.19.0` | none | extras |
| 21 | `recyclarr` | `ghcr.io/recyclarr/recyclarr:latest` | none | extras |
| 22 | `dmm-mysql` | `mysql:9.7` | none | extras |
| 23 | `dmm-redis` | `redis:8-alpine` | none | extras |
| 24 | `dmm-migrate` | built from DMM git context, `target: build` | none | extras (one-shot) |
| 25 | `debridmediamanager` | built from DMM git context, `target: build` | 3000 | extras |
| 26 | `cleanuparr` | `ghcr.io/cleanuparr/cleanuparr:2.9.16` | 11011 | extras |
| 27 | `neutarr` | `iampuid0/neutarr:1.9.1` | 9705 | extras |
| 28 | `maintainerr` | `ghcr.io/maintainerr/maintainerr:latest` | 6246 | extras |
| 29 | `beszel` | `henrygd/beszel:latest` | 8090 | extras |
| 30 | `beszel-agent` | `henrygd/beszel-agent:latest` | none | extras |

`docker compose up -d` brings up the 14 core services; `docker compose --profile extras up
-d` adds the other 16. Both are safe to re-run; Compose only recreates what is out of sync
with `docker-compose.yml`.

## The *arr apps

Both follow the same wiring: Prowlarr pushes indexers down via `fullSync`, Decypharr (or
`decypharr-alldebrid` for Sonarr) is the priority-1 download client, NzbDAV is priority-2
fallback, Unpackerr extracts RAR'd releases, the root folder is `./media/<type>` mounted at
`/data/<type>`, and Control Panel provides RSS sync / search-missing / unstick /
manual-import for each.

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

## The debrid pipeline: Zurg + Decypharr

**Zurg** (`ghcr.io/debridmediamanager/zurg@sha256:924f17...`, the sponsor-gated image, not
the public `zurg-testing` one) mounts existing Real-Debrid content at `/mnt/zurg` for Plex to
read. **Decypharr** (`cy01/blackhole:v2.3`, two isolated instances; see
[Architecture](#architecture)) is the qBittorrent-API-compatible gateway every `*arr` app
grabs through: it adds a magnet to Real-Debrid/AllDebrid, waits for caching, and symlinks the
result into each app's `/app/downloads/<category>`, shared at the identical path across every
container so no Remote Path Mappings are needed (Decypharr's documented best practice).

```json
// config/decypharr/config.json (sanitized) - one debrid backend on this
// instance (Real-Debrid), symlink-only, categories for all three *arr apps
{
  "debrids": [
    {
      "provider": "realdebrid",
      "torrents_refresh_interval": "10m",
      "download_links_refresh_interval": "5m",
      "workers": 800,
      "auto_expire_links_after": "3d"
    }
  ],
  "mount": {
    "type": "dfs",
    "mount_path": "/mnt/decypharr",
    "dfs": {
      "cache_expiry": "24h",
      "disk_cache_size": "500MB",
      "chunk_size": "8MB",
      "read_ahead_size": "32MB"
    }
  },
  "default_download_action": "symlink",
  "categories": ["sonarr", "radarr"],
  "refresh_interval": "30s",
  "max_downloads": 10
}
```

`allowed_file_types` in the same file is one shared allow-list across every category, not
scoped per-app. It still includes audio extensions (added for Lidarr, removed v10.9.9) and
ebook extensions (added for Bindery, retired v10.9.8); both are inert since nothing reads
those categories.

Restricting an app to a specific debrid provider is a per-arr field, distinct from the
overall `debrids[]` list:

```bash
# Radarr is pinned to Real-Debrid only (in its arrs[] entry in
# config/decypharr/config.json). Sonarr stays on source: "auto"
# with no selected_debrid, so it can fall through to AllDebrid.
# config/decypharr/config.json is gitignored (real API keys), so this is
# a live runtime edit, not visible in git log.
{
  "name": "radarr",
  "source": "auto",
  "selected_debrid": "realdebrid"
}
```

Restart command if Zurg's config changes (the container runs the binary directly and spawns
its own rclone mount as a child process, so one restart covers both):

```bash
docker compose restart zurg
```

This interrupts `/mnt/zurg` for a few seconds; do it when nothing is streaming.
`rclone-alldebrid` and `/mnt/all` are unaffected.

### Zurg's content-routing groups

`config/zurg/config.yml`'s `directories` block routes cached content into per-type folders
under `/mnt/zurg`. Groups are evaluated in ascending `group_order`, first match wins. The
`movies` entry is a catch-all regex (`/.*/`) that must sort last; every more specific group
needs a lower `group_order` or its content falls into `movies`:

```yaml
# config/zurg/config.yml (token/plex_token redacted)
directories:
  # Checked before the generic "shows" group (has_episodes: true would
  # otherwise claim these first). Matches known fansub/release-group tags
  # plus an episode-number marker, so it only catches episodic anime;
  # anime movies fall through to anime-movies below.
  anime-shows:
    group: media
    group_order: 8
    filters:
      - regex: /(?i)\[(SubsPlease|Erai-raws|Judas|EMBER|HorribleSubs|Commie|ASW|GJM|Yameii|Tsundere-Raws|ReinForce|DKB|Anime Time|Golumpa|Beatrice-Raws|Kawaiika-Raws|Chihiro|Doki|UTW|Underwater|DameDesuYo|ToonsHub|NC-Raws|PAS)\].*(-\s?\d{2,3}(\D|$)|\bE\d{2,3}\b|S\d{1,2}E\d{1,3})/
  shows:
    group: media
    group_order: 10
    filters:
      - has_episodes: true
  music:
    group: media
    group_order: 12
    filters:
      - regex: /(?i)\b(FLAC|MP3|CDDA|Vinyl|Discography|320kbps|Lossless|WEB-DL.*MP3)\b/
  # Nothing currently reads /mnt/zurg/books (see Bindery and Calibre-Web:
  # retired); the group is left in place in case an ebook app returns.
  books:
    group: media
    group_order: 14
    filters:
      - regex: /(?i)\b(EPUB|MOBI|AZW3?|EBOOK)\b/
  adult:
    group: media
    group_order: 17
    filters:
      - regex: /(?i)\bXXX\b/
  # Same fansub-tag list as anime-shows without the episode-marker
  # requirement - episodic anime is already claimed by anime-shows
  # (lower group_order), so what matches here is movie-style anime.
  anime-movies:
    group: media
    group_order: 19
    filters:
      - regex: /(?i)\[(SubsPlease|Erai-raws|Judas|EMBER|HorribleSubs|Commie|ASW|GJM|Yameii|Tsundere-Raws|ReinForce|DKB|Anime Time|Golumpa|Beatrice-Raws|Kawaiika-Raws|Chihiro|Doki|UTW|Underwater|DameDesuYo|ToonsHub|NC-Raws|PAS)\]/
  movies:
    filters:
      - regex: /.*/
    group: media
    group_order: 20
```

Ordering: `anime-shows` (8) < `shows` (10) < `music` (12) < `books` (14) < `adult` (17) <
`anime-movies` (19) < `movies` (20). `music` and `books` are orphaned groups (Lidarr removed
v10.9.9, Bindery retired v10.9.8), left in place in case those content types return.
`anime-shows`/`anime-movies` feed a dedicated Plex Anime library; see [Plex](#plex).

The fansub-tag list covers the release groups that have appeared in this account's cache, not
every group that exists. New groups not in the list fall through to `shows`/`movies`; extend
the regex's alternation list when that happens.

### Zurg's mount is a supervised rclone subprocess

The container has `/dev/fuse`, `cap_add: SYS_ADMIN`, and `apparmor:unconfined`, but the FUSE
mount is a separate rclone process that Zurg spawns and supervises, controlled by two config
keys:

```yaml
# config/zurg/config.yml
mount_path: /mnt/zurg
rclone_enabled: true
```

Without these keys in `config.yml`, Zurg's dashboard shows the mount as "Stopped ... Disabled
in config" and a `docker restart zurg` leaves `/mnt/zurg` empty, with no error surfaced in
Plex or any `*arr` app. This happened once: the setting had only ever been toggled through
Zurg's dashboard (an in-memory setting not written back to `config.yml`), so it worked until
the next restart discarded it. With the keys present, logs show `rclone started with mount
/mnt/zurg` and `Mount verification successful`, and every directory repopulates. Toggling
this through the dashboard instead of the config file will not survive a restart.

### Zilean ingestion from Zurg (a second hash source)

Zurg exposes a `/debug/torrents` endpoint that Zilean scrapes hourly to index every torrent
cached on this account, in addition to DebridMediaManager's public hashlist:

```yaml
# docker-compose.yml, zilean service environment
Zilean__Ingestion__EnableScraping: "true"
Zilean__Ingestion__ZurgInstances__0__Url: "http://zurg:9999"
Zilean__Ingestion__ZurgInstances__0__EndpointType: "1"
```

```bash
# Force an immediate ingestion pass instead of waiting for the hourly tick
# (the API service and a separate `scraper` CLI ship in the same image):
docker exec zilean /app/scraper generic-sync
```

No AllDebrid equivalent exists: `rclone-alldebrid` is a generic FUSE tool with no
"list my cached torrents as name/hash/size JSON" endpoint. See
[Known gaps and limitations](#known-gaps-and-limitations).

### Known transient issue: Real-Debrid rate limiting

Zurg polls Real-Debrid every 10 seconds and Decypharr refreshes its torrent/link caches every
10/5 minutes. Heavy simultaneous use (a large batch of grabs, a bulk manual-import scan,
several concurrent Plex streams through the same mount) can transiently hit Real-Debrid's API
rate limits. It self-recovers via Decypharr's `rate_limit: "250/minute"` setting and retry
logic, but a burst of grabs can visibly slow down. See
[Known gaps and limitations](#known-gaps-and-limitations).

## The Usenet pipeline: NzbDAV

**NzbDAV** (`nzbdav/nzbdav:latest` plus an `nzbdav-rclone` sidecar) is a virtual filesystem,
not a local downloader: it exposes Usenet content as a WebDAV server, `nzbdav-rclone` mounts
that WebDAV at `/mnt/nzbdav`, and completed downloads appear there as symlinks streamed on
demand.

```yaml
# docker-compose.yml
nzbdav:
  image: nzbdav/nzbdav:latest
  # Host port 3001 - DebridMediaManager owns 3000 on this host. Internally
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
    # buffer-size=0 avoids double-caching (the OS/Plex already buffer reads);
    # read-ahead sized for high-bitrate remux playback
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

**Import strategy** is "Symlinks - Plex" in NzbDAV's SABnzbd-compatible settings, with
`Rclone Mount Directory` pointed at `/mnt/nzbdav`. This is what makes Radarr/Sonarr treat
completed downloads as importable files (the STRM alternative is Emby/Jellyfin-only).

NzbDAV is priority-2 in every `*arr` app, behind Decypharr's priority-1: debrid is tried
first, NzbDAV fires on cache misses. API examples via Control Panel's proxy (NzbDAV has a
SABnzbd-style query API, not a dedicated REST API):

```bash
# Current Usenet download queue
curl -s http://192.168.4.105:8420/api/nzbdav/queue | jq .

# Recent history (completed/failed), last 20 by default
curl -s http://192.168.4.105:8420/api/nzbdav/history | jq .
```

**UI quirk**: NzbDAV's "Add Provider"/"Test Connection" form only submits once every field
has been focused/touched in the browser, including fields already holding a valid default.
Clicking the button while any field is untouched does nothing: no request fires, nothing is
written to `db.sqlite`, and no error appears. Click or tab through every field first.

This replaced NZBGet, a real local downloader (files land on `./usenet`, then import into the
library), which did not match the stack's no-local-disk model. Its old `config/nzbget/` and
`usenet/` directories were left on disk, unused.

## Indexing: Prowlarr, Zilean, Byparr

**Prowlarr** (`ghcr.io/hotio/prowlarr:release`, port 9696) holds every configured tracker and
pushes them to the three `*arr` apps via `Settings > Apps` `fullSync`. Zilean is registered
as a `Generic Torznab` indexer:

```bash
curl -X POST -H "X-Api-Key: $PROWLARR_API_KEY" -H "Content-Type: application/json" \
  http://192.168.4.105:9696/api/v1/indexer \
  -d '{"name":"Zilean","implementation":"Torznab","fields":[
        {"name":"baseUrl","value":"http://zilean:8181"},
        {"name":"apiPath","value":"/torznab/api"}]}'
```

**Zilean** (`ipromknight/zilean:v3.5.0`, port 8181, plus `zilean-postgres` on Postgres 18)
indexes DebridMediaManager's public cache-hash list (`Zilean__Dmm__EnableScraping`, hourly)
plus this account's own Zurg-cached torrents (see the ingestion section above). Postgres and
the app are tuned for this host's hardware:

```yaml
# docker-compose.yml, zilean-postgres command block
command:
  - "postgres"
  - "-c"
  - "shared_buffers=512MB"      # Postgres default is 128MB regardless of host
  - "-c"
  - "effective_cache_size=1536MB"
  - "-c"
  - "random_page_cost=1.1"      # NVMe, not spinning disk
  - "-c"
  - "effective_io_concurrency=200"
```

```yaml
# docker-compose.yml, zilean service environment
Zilean__Imdb__NumberOfCores: "12"     # 4 of 16 threads left for Plex/desktop
Zilean__Imdb__UseLucene: "true"       # faster per Zilean's docs, ~3GB extra RAM
DOTNET_gcServer: "1"                  # .NET Server GC
DOTNET_GCHeapHardLimit: "0xC0000000"  # 3GB hard limit inside the 4GB container ceiling
```

Zilean has no stats API (`/health`, `/api/stats`, `/dmm/status` all 404); Control Panel
queries its Postgres database directly:

```bash
curl -s http://192.168.4.105:8420/api/zilean/stats | jq .
# {"available": true, "total_hashes": 1510656, "imdb_matched": 128321}
```

Direct search, bypassing Prowlarr and the `*arr` apps, to check whether something is cached
before grabbing:

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"query": "Dune"}' http://192.168.4.105:8420/api/zilean/search | jq .
```

**Byparr** (`ghcr.io/thephaseless/byparr@sha256:01a46a...`, port 8191) solves
Cloudflare/anti-bot challenges for indexers that need it, registered as Prowlarr's
`FlareSolverr`-implementation Indexer Proxy (the internal protocol name did not change when
Byparr replaced FlareSolverr; only the `host` field and display name did):

```bash
curl -X PUT -H "X-Api-Key: $PROWLARR_API_KEY" -H "Content-Type: application/json" \
  http://192.168.4.105:9696/api/v1/indexerproxy/1 \
  -d '{"implementation":"FlareSolverr","name":"Byparr","fields":[{"name":"host","value":"http://byparr:8191/"}]}'
```

Byparr uses Camoufox (a Firefox-based anti-detect browser) instead of FlareSolverr's
Selenium + undetected-chromedriver.

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

## Plex

Containerized, official `plexinc/pms-docker` image. A PUID/PGID-forcing image (LinuxServer
style) would have recursively chowned the ~33GB library on first boot.

```yaml
# docker-compose.yml
plex:
  image: plexinc/pms-docker:1.43.2.10687-563d026ea
  network_mode: host
  environment:
    PLEX_UID: "955"     # matches the uid/gid the library was originally owned as
    PLEX_GID: "955"
    PLEX_MEDIA_SERVER_APPLICATION_SUPPORT_DIR: /config
  volumes:
    - ./config/plex:/config
    - ./config/plex-transcode:/transcode
    - /mnt:/mnt:rslave
    - ./media:/home/bear/Stack/media
  devices:
    - /dev/dri/renderD128:/dev/dri/renderD128   # AMD Radeon 680M iGPU, VAAPI hardware transcode
```

- `network_mode: host` is the one exception to the stack's `stacknet` bridge +
  published-port pattern: Plex's GDM auto-discovery, DLNA, and remote-access NAT-PMP/UPnP
  negotiation are unreliable on bridge networking.
- The image is version-pinned and off Watchtower's auto-update train; PMS version changes are
  applied manually (see [Image pinning policy](#image-pinning-policy)).
- Libraries (from `/library/sections`):

  | Key | Title | Type | Agent | Locations |
  |---|---|---|---|---|
  | 4 | Movies | movie | `tv.plex.agents.movie` | `/home/bear/Stack/media/movies`, `/mnt/zurg/movies` |
  | 1 | TV Shows | show | `tv.plex.agents.series` | `/mnt/zurg/shows`, `/home/bear/Stack/media/shows`, `/mnt/all/magnets` |
  | 3 | Music | artist | `tv.plex.agents.music` | `/mnt/zurg/music`, `/home/bear/Stack/media/music` |
  | 8 | Audiobooks | artist | `tv.plex.agents.none` | `/home/bear/Stack/media/audiobooks` |
  | 10 | Anime Movies | movie | `tv.plex.agents.movie` | `/mnt/zurg/anime-movies`, `/home/bear/Stack/media/anime-movies` |
  | 11 | Anime Shows | show | `tv.plex.agents.series` | `/mnt/all-anime`, `/mnt/zurg/anime-shows`, `/home/bear/Stack/media/anime-shows` |

  `./media` is mounted at its identical host absolute path (`/home/bear/Stack/media`) so
  every arr app's writable root folder can be added as a library location directly.

### Plex "Anime Movies" and "Anime Shows" libraries

Two libraries backed by Zurg's `anime-movies`/`anime-shows` content-routing groups (see
[The debrid pipeline](#the-debrid-pipeline-zurg--decypharr)), using stock Plex agents
(`tv.plex.agents.movie`, `tv.plex.agents.series`). Plex ships no anime metadata agent;
installing one (e.g. HAMA) has not been done here.

Created via the Plex API:

```bash
curl -X POST "http://192.168.4.105:32400/library/sections?X-Plex-Token=$PLEX_TOKEN" \
  --data-urlencode "name=Anime Shows" --data-urlencode "type=show" \
  --data-urlencode "agent=tv.plex.agents.series" --data-urlencode "scanner=Plex TV Series" \
  --data-urlencode "language=en-US" \
  --data-urlencode "location=/mnt/zurg/anime-shows" \
  --data-urlencode "location=/home/bear/Stack/media/anime-shows"
```

Multi-`location` gotcha: posting the params as a form body returns a bare `400 Bad Request`.
Plex expects repeated `location=` params in the query string (`POST` with an empty body).
Updating an existing section via `PUT /library/sections/{id}` has the same gotcha, and also
400s unless `name`/`agent`/`scanner`/`language` are repeated in the same request; a partial
payload is not treated as a partial update.

`Anime Shows` also includes `/mnt/all-anime`, a second rclone mount
(`rclone-alldebrid-anime`) exposing an `--include`-filtered view of the AllDebrid
`all:magnets` remote using the same fansub-tag list as Zurg's two groups. AllDebrid has no
content-routing feature, so a filtered anime-only view requires a second rclone process with
glob `--include` patterns (brackets escaped). The tag list must be kept in sync by hand
across the two filter syntaxes (Zurg regex vs. rclone glob).

`Anime Movies` does not include `/mnt/all-anime`. The AllDebrid-side filter is a single flat
mount with no episodic/movie split; rclone's glob syntax cannot express "has this tag AND
lacks an episode-number pattern." Adding the mount to both libraries was tried and produced
false positives: Plex's movie scanner matched raw episode files (`Honzuki No Gekokujou S4
13`, `Lord of Mysteries 02v3`, etc.) as standalone films. It was removed from Anime Movies in
the same session. Consequence: anime movies from AllDebrid currently have no path into this
library; see [Known gaps and limitations](#known-gaps-and-limitations).

First scan: 10 folders matched into `anime-shows` from Zurg's Real-Debrid cache, then 19 more
from `/mnt/all-anime`, all correctly anime-tagged, zero false positives once `/mnt/all-anime`
was scoped to Anime Shows only. 6 titles auto-resolved Plex metadata; the rest need a manual
**Match** in Plex's UI, which is normal agent behavior for raw fansub-style folder names.
`anime-movies` had zero matches on the first pass (nothing movie-style cached yet).

The fansub-tag list only covers release groups seen so far; re-run this spot-check
periodically against both sources:

```bash
ls /mnt/zurg/anime-shows/ /mnt/zurg/anime-movies/ /mnt/all-anime/
curl -s -H "X-Plex-Token: $PLEX_TOKEN" http://192.168.4.105:32400/library/sections/11/all | \
  grep -oP 'title="[^"]*"'
```

### Plex "Audiobooks" library, and the retired "Adult" library

**Audiobooks** (key 8) is a Music-type library using the "Plex Personal Media" agent
(`tv.plex.agents.none`), the standard workaround since Plex has no audiobook library type or
agent. It points at `/home/bear/Stack/media/audiobooks`, which exists but is empty; nothing
populates it automatically.

**Plex's "Adult" library was removed in v10.9.9** via the Plex API
(`DELETE /library/sections/{key}`). It was a Movie-type library pointed at `/mnt/zurg/adult`
and (after a fix in v10.5.0) `/home/bear/Stack/media/adult`. Stash covered this content type's
cataloging (performers/studios/tags/StashDB identification) until it, along with Whisparr (the
app that managed this library) and `./media/adult` itself, was removed entirely in v10.12.0.
See [History](#history). There is no adult content library in this stack anymore.

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

Plex has no ebook agent (`/system/agents` lists no book identifier), so bringing ebooks back
would require both a manager and a reader again.

## Custom formats and quality profiles

Radarr and Sonarr each carry one custom format, **"Block - Sample, Russian, Low-Quality
Sources"**, scored `-10000` in the one quality profile each app has (`Unlimited`;
`minFormatScore` is `0`, so this is a hard reject). Four `required: false` conditions OR'd
together; any one match rejects the release:

```bash
# 1. Sample releases (title-level; a bundled sample file inside an otherwise
#    clean release is caught by each app's own per-file detection)
(?i)\bsample\b

# 2. Russian language - Radarr/Sonarr's built-in LanguageSpecification (value 11)

# 3. Russian/Korean text or script - literal tags plus Cyrillic and Hangul
#    Unicode ranges, so a release matches even with wrong language metadata
(?i)\b(rus|russian|kor|korean)\b|[Ѐ-ӿ]|[가-힣ᄀ-ᇿ㄰-㆏]

# 4. Blocked low-trust sources/groups
(?i)\b(WEB-DL|WEBRip|BDRip|HDRip|DVDRip|HDTV|AMZN|NF|DSNP|CR|YTS|TGX|TorrentGalaxy|FGT|LOL|KILLERS|EPSiLON|Erai-raws)\b|rartv|rarbg|eztv
```

Check what a release title scores with each app's parse endpoint:

```bash
curl -s -H "X-Api-Key: $RADARR_API_KEY" \
  "http://192.168.4.105:7878/api/v3/parse?title=Movie.Name.2024.1080p.WEB-DL.RUS" | \
  jq '.customFormats, .customFormatScore'
```

This replaced an earlier Recyclarr + TRaSH-Guides sync (41/40 per-quality-tier custom
formats, synced daily), removed in v3.0.0. Recyclarr was reinstated in v10.5.0 with a
narrower scope: it targets the same `Unlimited` profile directly and syncs five
resolution-agnostic hygiene custom formats (Scene, Obfuscated, Retags, No-RlsGroup, Bad Dual
Groups). `reset_unmatched_scores` is off so the manual blocklist format stays untouched by
syncs. See [History](#history).

## DebridMediaManager (self-hosted)

Self-hosted instance of
[DebridMediaManager](https://github.com/debridmediamanager/debrid-media-manager) (the app
behind debridmediamanager.com): library browsing/organizing/casting plus an on-demand
per-title scraper. Four services, all `profiles: [extras]`:

```yaml
# docker-compose.yml (abridged)
dmm-mysql:            # required by DMM's Prisma schema, not swappable for Postgres
dmm-redis:            # rate limiting
dmm-migrate:           # one-shot `npx prisma db push --accept-data-loss`, exits after running
debridmediamanager:    # the web app, port 3000
  build:
    context: https://github.com/debridmediamanager/debrid-media-manager.git#c2ceef94477e49ddd5c55606bf57959ffdf29b9e
    target: build      # NOT the default deploy stage - see below
```

No pre-built image exists for this project (checked GHCR and Docker Hub), so it builds from a
git context pinned to a specific commit.

Real-Debrid/AllDebrid/TorBox credentials are entered in the browser (`localStorage`), never a
server-side secret. `TMDB_KEY`/`MDBLIST_KEY`/`OMDB_KEY`/`TRAKT_CLIENT_ID`/
`TRAKT_CLIENT_SECRET`/`GH_PAT` are reused from Kometa's configured keys.

Search requires a local IMDB title index, not a live API: `api/search/title.ts` queries
`imdb_title_basics`/`imdb_title_akas`/`imdb_title_ratings` directly.
`scripts/import-imdb-data.py` streams IMDB's public dataset dumps from
`datasets.imdbws.com`, filters to what the search query touches (`movie`/`tvSeries`/
`tvMiniSeries`, non-adult), and loads them via `LOAD DATA INFILE`.
`systemd/stack-imdb-sync.timer` runs it daily at 04:15, matching IMDB's publish cadence.

```bash
curl -s "http://192.168.4.105:3000/api/search/title?keyword=Yellowstone%202018" | jq .
```

Two upstream bugs are worked around without vendoring a modified Dockerfile:

1. The default `deploy` stage generates the Prisma Client without `openssl` installed, so
   Prisma generates the wrong query engine binary and the app crash-loops. Running from the
   `build` stage (full toolchain) with a fix-then-start command avoids it:
   ```yaml
   command: >
     sh -c "apt-get update && apt-get install -y -q openssl curl tzdata &&
     rm -rf /var/lib/apt/lists/* && npx prisma generate &&
     npx next start -H 0.0.0.0 -p 3000"
   ```
2. `npx prisma` in the deploy stage (which strips devDependencies including the Prisma CLI)
   downloads a newer major version from the registry at runtime instead of the pinned one.
   The same `target: build` fix covers this.

## Automation extras: Kometa, Cleanuparr, NeutArr, Unpackerr, Watchtower

**Kometa** (`kometateam/kometa@sha256:98a0df...`; official image, not the LinuxServer fork,
which resets `/config` ownership on every start) automates Plex collections, metadata, and
overlay art. No web UI; it is a scheduled batch job (05:00 daily by default). Connected to
Plex, TMDb, Radarr, Sonarr, Tautulli, Trakt, and MyAnimeList.

```bash
# Run now instead of waiting for 05:00, optionally scoped to libraries
curl -X POST -H "Content-Type: application/json" \
  -d '{"libraries": ["Movies"]}' http://192.168.4.105:8420/api/kometa/run
```

The container's entrypoint is overridden to `sleep infinity`: the image's default entrypoint
runs a complete Kometa pass immediately on every container start/restart, not just on a
schedule. With the override, restarts idle; Control Panel's `/api/kometa/run` execs
`python3 /kometa.py --run` on demand regardless of PID 1. Do not remove the override.

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

Digest-pinned images (Seerr, Kometa, Unpackerr, Byparr) and exact-version-tag-pinned ones
(Zilean, Decypharr, Watchtower itself, Plex) are not auto-updated: a digest or exact tag is
immutable, so Watchtower never finds anything new. See
[Image pinning policy](#image-pinning-policy).

## Monitoring extras: Tautulli

**Tautulli** (`ghcr.io/hotio/tautulli:release`, port 8182): Plex watch-history/stats
dashboard.

Glances and Dozzle were removed in v10.9.9 (neither had a config volume, so no data was
involved). Glances powered Control Panel's Overview "Host CPU/memory/disk/uptime" tiles via
`/api/system/stats`; that endpoint and those tiles were removed with it. Control Panel's
per-app log tailing (`/api/arr/{app}/logs`) never depended on Dozzle. A Prometheus + Grafana
stack was researched the same version and cancelled before anything was built.

Adminer was removed in v10.9.9 with no replacement (a same-day CloudBeaver swap was
reverted). There is no web DB GUI; inspect `zilean-postgres`/`dmm-mysql` with
`docker exec -it <db> psql/mysql ...`.

## Maintainerr: Plex library lifecycle

**Maintainerr** removes watched/stale content on rules you define, covering the other half of
the request lifecycle Seerr starts, so the Zurg/Decypharr mounts and local `./media`
footprint do not grow unbounded. It was the one adoptable idea from an evaluation of
[RandomNinjaAtk/arr-scripts](https://github.com/RandomNinjaAtk/arr-scripts) (most of which
requires LinuxServer.io init-hook directories the hotio images here lack, duplicates existing
functionality, or conflicts with the no-local-disk architecture).

```yaml
# docker-compose.yml
maintainerr:
  image: ghcr.io/maintainerr/maintainerr:latest
  user: "${PUID}:${PGID}"
  volumes:
    - ./config/maintainerr:/opt/data
  ports:
    - "6246:6246"
```

Server connections (Plex, Radarr, Sonarr, Seerr, Tautulli) are configured through its
settings API/UI, not environment variables:

```bash
# Plex requires the auth token saved first, separately
curl -X POST -H "Content-Type: application/json" http://localhost:6246/api/settings/plex/token \
  -d "{\"plex_auth_token\": \"$PLEX_TOKEN\"}"
curl -X PATCH -H "Content-Type: application/json" http://localhost:6246/api/settings \
  -d '{"plex_hostname":"192.168.4.105","plex_port":32400,"plex_ssl":0,
       "plex_machine_id":"72ecc884f6bcd5f8bc4e4562b6b81e03ea9209e5","plex_manual_mode":1}'

# Radarr/Sonarr/Seerr/Tautulli are one call each
curl -X POST -H "Content-Type: application/json" http://localhost:6246/api/settings/radarr \
  -d "{\"serverName\":\"Radarr\",\"url\":\"http://radarr:7878\",\"apiKey\":\"$RADARR_API_KEY\"}"
```

Two starter rules were imported from Maintainerr's community rule library (the highest-karma
entries for a Seerr-based setup), one each for Movies and TV Shows: "seen by the Seerr
requester & older than 30 days, OR unwatched & older than 90 days." Both were created with
`isActive: false`. The rule engine runs on a cron schedule (`rules_handler_job_cron`, every 8
hours by default) and deletes matching media, so review the rules in the UI (`Rules` tab) and
enable them yourself:

```bash
curl -s http://localhost:6246/api/rules | \
  python3 -c "import sys,json; [print(r['id'], r['name'], r['isActive']) for r in json.load(sys.stdin)]"
```

## Control Panel

`control-panel/`: a custom FastAPI app (`build: ./control-panel`, not a pulled image), the
single dashboard for this stack. Live container status/control, Zilean's hash count,
one-click ops actions, direct Zilean search with grab-to-Decypharr, and per-app queue tools.
Port **8420**. Its addition allowed Heimdall and Homepage to be removed; see
[History](#history).

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
| `/api/zilean/stats` | GET | Total indexed hashes + IMDB-matched count, from `zilean-postgres` directly |
| `/api/kometa/run` | POST | `docker exec`s a Kometa run, optionally scoped to `{"libraries": [...]}` |
| `/api/plex/scan` \| `/empty-trash` \| `/optimize-db` \| `/clean-bundles` | POST | Plex maintenance actions |
| `/api/plex/libraries` | GET | Library names/keys, read live from Plex |
| `/api/plex/updates` | GET | Running Plex version + any newer release on its channel (check only) |
| `/api/nzbdav/queue` \| `/history` | GET | NzbDAV's current queue / recent history |
| `/api/zilean/search` | POST | `{"query": "..."}` → title/year/resolution/quality/size/hash results |
| `/api/decypharr/grab` | POST | `{"hash": "...", "title": "..."}` → adds a magnet to Decypharr under a `manual` category |
| `/api/arr/{app}/rss-sync` \| `/search-missing` | POST | Per-app RSS sync / missing-search |
| `/api/arr/{app}/unstick` | POST | Removes + blocklists + re-searches every `warning`/`error` queue item |
| `/api/arr/{app}/manual-import` | GET/POST | Lists importable files across stuck queue items; POST executes one |
| `/api/arr/{app}/manual-import-all` | POST | Bulk-imports every candidate the GET lists |
| `/api/arr/{app}/missing-aired` | GET | Monitored + no file + already-aired (see [The *arr apps](#the-arr-apps)) |
| `/api/container/{name}/start` \| `/stop` \| `/restart` | POST | Individual container control, validated against the live compose project |
| `/api/stack/restart-all` | POST | Restarts everything except itself, mount providers first (see below) |

### Live API hit counter

Container cards for apps the panel talks to over HTTP (the three `*arr` apps, Plex, Zilean,
Decypharr, NzbDAV) show a running count of outbound calls since the panel last started.
Cosmetic only: in-memory `Counter`, resets on restart, no persistence, no per-endpoint
breakdown.

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

### Grab: a real, non-undoable action

```python
# control-panel/app.py
INFO_HASH_RE = re.compile(r"^[0-9a-fA-F]{40}$")

@app.post("/api/decypharr/grab")
def decypharr_grab(payload: GrabRequest):
    info_hash = payload.hash.strip().lower()
    if not INFO_HASH_RE.match(info_hash):
        # Zilean's index is scraped from a public hashlist and isn't perfectly
        # clean - Decypharr's magnet parser 400s with no application-level log
        # line for a malformed hash.
        fail(f"'{info_hash}' isn't a valid 40-character info hash...", status_code=400)
    ...
```

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"hash": "08ada5a7a6183aae1e09d831df6748d566095a10", "title": "Example.2024.1080p"}' \
  http://192.168.4.105:8420/api/decypharr/grab
```

This acts on the live debrid account. It and the whole-stack restart are the only endpoints
the frontend guards with an arm/confirm double-click.

This endpoint only targets the primary Real-Debrid `decypharr` instance; it has no path to
`decypharr-alldebrid`.

### Whole-stack restart: mount-order aware

```python
# control-panel/app.py
MOUNT_PREREQS = {"nzbdav"}
MOUNT_PROVIDERS = {"zurg", "decypharr", "decypharr-alldebrid", "rclone-alldebrid", "rclone-alldebrid-anime", "nzbdav-rclone"}
MOUNT_DEPENDENTS = {"radarr"}

def worker():
    for c in prereqs: c.restart(timeout=30)
    for c in prereqs: wait_for_healthy(c)
    for c in providers: c.restart(timeout=30)
    for c in providers: wait_for_healthy(c)
    for c in rest: c.restart(timeout=30)
    for c in dependents: c.restart(timeout=30)   # Radarr last, after mounts are healthy
```

```bash
curl -X POST http://192.168.4.105:8420/api/stack/restart-all
```

This exists because of the Radarr mount-fragility issue in [Architecture](#architecture):
restarting Radarr before its mount providers are healthy reproduces that bug.

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
stack-arr radarr rss-sync                       # radarr/sonarr; or search-missing / unstick
stack-arr-import-candidates sonarr              # list files ready to manually import
stack-arr-import sonarr 0                       # import candidate #0 from the list above
stack-kometa-run Movies "TV Shows"              # scoped run; no args = every library
stack-plex scan                                 # or empty-trash / optimize-db / clean-bundles
stack-plex-libraries                            # list Plex library names
stack-zilean-search dune                        # search Zilean's cached-hash index
stack-grab 08ada5a7a6183aae1e09d831df6748d566095a10 "Dune (2021)"
stack-nzbdav-queue                              # current Usenet download queue
stack-nzbdav-history 20                         # recent history, default limit 20
stack-container restart radarr                  # or stop / start
stack-restart-all -y                            # skip the interactive confirm prompt
```

Example: search Zilean, then grab the top hit:

```fish
> stack-zilean-search dune
Dune Part Two 2024  [2160p BluRay REMUX]  84.3 GB
  hash: 08ada5a7a6183aae1e09d831df6748d566095a10
...
> stack-grab 08ada5a7a6183aae1e09d831df6748d566095a10 "Dune Part Two"
Added "Dune Part Two" to Decypharr - will appear once Real-Debrid/AllDebrid finishes caching.
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
stack-content-audit movies                      # or shows - content untracked by the matching *arr app
stack-zurg-classify "Family.Swap.5.2022.720p"   # test a filename against the current routing config
stack-mount-health                              # every known FUSE mountpoint, checked for a stale one
stack-oom-check                                 # containers Docker has recorded an OOM-kill for
stack-perms-check                               # config files unreadable by group/other
stack-backup-verify                             # latest snapshot age, local + off-site repos
stack-backup-restore-test                       # actually restores one file, confirms restores work
stack-cleanuparr-instances                      # which *arr apps Cleanuparr actually has connected
stack-neutarr-status                            # per-app enabled state from NeutArr's own config
stack-decypharr-health decypharr                # or decypharr-alldebrid
stack-arr-logs radarr 200                       # tail a container's log directly
stack-plex-empty-trash "TV Shows"               # scoped to one library, or every library if none given
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

**Ratings and MDBList list import — added in v10.11.0.** Both OMDb and MDBList API keys are
read live from Kometa's own `config.yml` (already configured there for Kometa's own metadata
lookups) - nothing new to sign up for or add to `.env`.

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

The full CLI (40 commands), plus a standalone restyled Control Panel and a credential-entry
installer, is also distributed as its own repo:
[`StackScripts`](https://github.com/WhispersOfJ/StackScripts). Unlike `Stackalicious` (the
sanitized mirror of this repo), `StackScripts` is generalized: no hardcoded IP or host paths,
config collected through a browser-based setup wizard. Per `AGENTS.md`, every new `stack-*`
command added here must be mirrored to both siblings in the same pass.

## Backups

`./config` holds every app's settings, database, and plaintext API keys. None of it is in
git, and it is not reproducible by re-running `docker compose up` or re-pulling images.

- **`scripts/backup-config.sh`**: dumps `zilean-postgres` (`pg_dump`) and `dmm-mysql`
  (`mysqldump`) first, then `restic backup ./config`, then `restic forget --prune`
  (`--keep-daily 7 --keep-weekly 4 --keep-monthly 6`). Repo at `~/backups/stack-restic-repo`,
  restic-encrypted. Run daily at 03:30 by `systemd/stack-backup.timer`, before Watchtower's
  4am updates. An off-site leg mirrors the same backup to any restic-supported remote
  (`BACKUP_REMOTE_REPOSITORY` in `.env`) with its own retention pass, Discord tag, and a
  monthly `restic check --read-data-subset=10%` integrity check on the 1st, same as the local
  repo.
- **Excluded from restic**: `decypharr/cache` and `decypharr-alldebrid/cache` (regenerable
  FUSE caches), every app's `logs`/`log` directory, `zilean-postgres`'s and `dmm-mysql`'s raw
  datadirs (the logical dumps cover those; file-level copying a running database's datadir
  can produce an inconsistent restore), and several regenerable Plex subdirectories (`Metadata` - 28GB of re-fetchable posters/art,
  `Cache`, `Codecs`, `Logs`, `Crash Reports`, plus `plex-transcode`). Any new DB-backed
  service needs its own logical-dump step added to `backup-config.sh`; excluding the raw
  datadir alone drops it from coverage.
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
- **Plex additions**: `scripts/plex-webhook-listener.py`, a listener bound to
  `127.0.0.1:${PLEX_WEBHOOK_PORT}` (default 9880) reacting to Plex's native `library.new`
  webhook (Plex Pass feature), with poster boxart re-uploaded as a file attachment. One-time
  manual step: Plex web app > **Settings > Webhooks > Add Webhook** >
  `http://127.0.0.1:9880/plex-webhook`.
- **Plex removals**: `scripts/plex-library-report.py`, every 30 minutes (Plex has no "item
  removed" webhook event, so this is a poll-and-diff).
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
- **Version tags** (`ipromknight/zilean:v3.5.0`, `cy01/blackhole:v2.3`,
  `nickfedor/watchtower:1.19.0`) where the upstream tags real releases and the running image
  matches.
- **Digest pins** (`@sha256:...`) for Seerr, Kometa, Unpackerr, and Byparr. In each case the
  running `:latest` build is ahead of the newest tagged release, so any tag would be a
  downgrade. Byparr publishes no clean `vX.Y.Z` tags on GHCR at all (only `:latest`, `:main`,
  and commit-sha/arch tags), so a digest is the only way to freeze a build.
- **Version tag, manually bumped, off Watchtower's train** for Plex
  (`plexinc/pms-docker:1.43.2.10687-563d026ea`); PMS version changes on a live library are
  applied manually.
- **Pinned to a specific git commit** for the two DebridMediaManager services built from
  source (no pre-built image exists upstream).

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
| `plex` | 6GB | 12 | Library scans alone (zero playback) briefly hit 100% CPU; HW transcode covers decode, not scan/analysis |
| `zurg` | 1GB | 6 | Sustained ~20-25% CPU baseline (10s Real-Debrid poll + serving reads) |
| `decypharr` / `decypharr-alldebrid` | 1.5GB each | 4 each | Highest steady RAM baseline besides Postgres/Zilean (~540-580MB) |
| `zilean` | 4GB | 12 | Lucene IMDB matching, 12 of 16 host threads |
| `zilean-postgres` | 2GB | 4 | Tuned for NVMe and this host's hardware |
| `byparr` | 2GB | 4 | Each Cloudflare solve spins up a Camoufox browser instance |
| `kometa` | 2GB | 4 | 642MB observed resident while idle |
| `dmm-mysql` | 2GB | 2 | Millions-of-rows IMDB index with fulltext indexes |
| `debridmediamanager` | 1.5GB | 2 | Runs from the `build` stage (full devDependencies) |

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
- `config/decypharr/config.json` and `config/zurg/config.yml` contain API tokens in
  plaintext, `chmod 600`. Relevant if this host is shared or backed up somewhere less
  trusted.

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
AUTO_GENERATE_KEYS = {"ZILEAN_POSTGRES_PASSWORD", "ZILEAN_API_KEY"}
```

`LIDARR_API_KEY` was dropped from `POST_BOOT_KEYS` (and from `.env`/`.env.example`) in
v10.9.9 with Lidarr, and `WHISPARR_API_KEY` the same way in v10.12.0 with Whisparr. Three
fields cannot be collected before first boot: each `*arr` app generates its own API key on
first start, and `PLEX_TOKEN` needs a running Plex with at least one library item. These
render in a highlighted "Fill in after first boot" section and default to `changeme`;
re-running `--setup` loads the real `.env` as defaults, so a second pass only means entering
what is new.

## Known gaps and limitations

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
- **NeutArr's `python3` process gets OOM-killed inside its 512MB limit on a ~30-minute
  cycle** (15 kills in one overnight window, confirmed via `journalctl | grep oom-killer`,
  memcg-scoped to its container). Invisible on any dashboard because
  `restart: unless-stopped` brings it back each time. Not yet root-caused (leak vs. a task
  needing more headroom) or fixed.
- **Zurg/Real-Debrid can hit transient rate limiting under heavy simultaneous use.**
  Self-recovers via Decypharr's retry logic. See
  [The debrid pipeline](#the-debrid-pipeline-zurg--decypharr).
- **`media/youtube` is an inert leftover** from a removed Pinchflat integration; nothing
  reads or writes it.
- **`rclone-alldebrid` does not reliably survive a plain `docker restart`.** Its `/mnt/all`
  FUSE mount can come back `Transport endpoint is not connected`, and restart-policy retries
  never clear it. Recovery needs a lazy unmount from outside the container's mount namespace
  (`docker run --rm --privileged -v /mnt:/mnt:rshared alpine umount -l /mnt/all`) followed by
  a fresh restart. This is not covered by `restart-all`'s mount ordering.
- **A still-unexplained mass Radarr/Sonarr library-loss event** occurred once early on (1,605
  movies deleted in a 0.1-second burst with no matching API call logged; ~90 Sonarr series
  briefly added then removed with no deletion log line). Root cause was never identified.
  Both apps' native Recycle Bin is now enabled as a blast-radius mitigation, not a fix
  (`/data/movies/.recyclebin`, `/data/shows/.recyclebin`, 7-day cleanup).
- **Anime movies from AllDebrid have no path into the Anime Movies library** (see
  [Plex](#plex)): the AllDebrid filter mount is flat and cannot split episodic vs. movie
  content.
- **No AllDebrid equivalent of Zilean's Zurg ingestion**: `rclone-alldebrid` has no
  torrent-listing endpoint to scrape.

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

**v10.3.0**: Maintainerr added (see
[Maintainerr](#maintainerr-plex-library-lifecycle)); two community rules imported, left
`isActive: false`. Native Discord notification connections added to all five `*arr` apps.

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

**v10.14.0** (current): `PLAN.md` research resolved two of its three open questions in TRaSH
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
