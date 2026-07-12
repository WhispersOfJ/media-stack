# The Stack

Current version: **v10.6.2**

**A Docker Compose media-acquisition-and-serving stack** — indexes, requests, and symlinks
already-cached content from Real-Debrid / AllDebrid, falls back to Usenet (streamed, not
downloaded) when nothing's cached, and serves the result through a containerized Plex. 35
services, one compose file, every image pinned and healthchecked, one custom-built dashboard
(Control Panel) and one custom CLI (`stack-*` fish functions) as the two operator surfaces.

🤖 **Built entirely by [Claude AI](https://www.anthropic.com/claude)** — every service, every
migration, every bug found and fixed, and this document itself were designed, written, and
verified by Claude against the real running stack.

This is the **only** document in this repo besides raw config files. It used to be split across
`README.md` (quickstart), `TECHNICAL.md` (deep reference), and `CHANGELOG.md` (version history);
all three are merged here, organized by subsystem rather than by date, because that's a more
useful shape for both "how do I use this" and "why is it built this way" questions. A condensed
chronological [History](#history) section is at the end for anyone who wants the version-by-
version story.

No screenshots. If you want to see what something looks like, it's a `curl` away — every
section below shows the actual request.

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
- [Calibre-Web: ebooks](#calibre-web-ebooks)
- [Custom formats and quality profiles](#custom-formats-and-quality-profiles)
- [DebridMediaManager (self-hosted)](#debridmediamanager-self-hosted)
- [Automation extras: Kometa, Cleanuparr, NeutArr, Unpackerr, Watchtower](#automation-extras-kometa-cleanuparr-neutarr-unpackerr-watchtower)
- [Monitoring extras: Tautulli, Glances, Dozzle, Adminer](#monitoring-extras-tautulli-glances-dozzle-adminer)
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
(Prowlarr + Zilean's DMM cache-hash index), a request front-end (Seerr), five `*arr` apps that
turn a request into an organized library (Radarr, Sonarr, Lidarr, Readarr, Whisparr), a debrid
gateway that symlinks already-cached content instead of downloading it (Decypharr + Zurg), a
Usenet fallback that streams rather than downloads (NzbDAV), a containerized Plex to watch/listen
to the result on, Calibre-Web to actually read the ebooks Readarr organizes, a self-hosted
DebridMediaManager, and a pile of automation/monitoring extras (Kometa, Cleanuparr, NeutArr,
Unpackerr, Watchtower, Tautulli, Glances, Dozzle, Adminer) — 32 containers total, one
`docker-compose.yml`.

The debrid-first design (Zurg + Decypharr) means anything already cached on Real-Debrid/AllDebrid
shows up as a symlink and plays instantly — no "downloading" step. Usenet (NzbDAV) is there for
genuine cache misses only, and even then it's a WebDAV virtual filesystem streamed on demand, not
a real local download — the one thing in this stack that ever wrote real files to disk (NZBGet)
was deliberately removed once that turned out not to be the actual goal (see
[History](#history)).

**What this isn't**: a beginner's first Docker project. It assumes you're comfortable with
Compose, and every web UI here publishes directly to the LAN with no login gate (see
[Security](#security)) — that's a deliberate choice for a home server, not an oversight, and a
network-security layer (Traefik + Authelia + CrowdSec) was tried once and reverted (see
[History](#history)) once the day-to-day friction outweighed what it bought.

## Quick start

```bash
mkdir -p ~/Stack && cd ~/Stack

# 1. Scaffold this repo's tracked files onto a fresh host (docker-compose.yml,
#    .env.example, scripts/, systemd/, this README) - no git clone needed.
docker run --rm -v "$(pwd)":/out ghcr.io/whispersofj/media-stack:latest

# 2. Fill in .env via a browser form built straight from .env.example's own
#    sections/comments - open http://<this-host>:8090
docker run --rm -p 8090:8090 -v "$(pwd)":/out ghcr.io/whispersofj/media-stack:latest --setup

# 3. Bring the core stack up
docker compose up -d

# 4. Everything else (recommended - Byparr, Tautulli, Kometa, Unpackerr,
#    Watchtower, Cleanuparr, NeutArr, Dozzle, Control Panel, DMM, Adminer)
docker compose --profile extras up -d
```

Skip step 2 entirely if you'd rather hand-edit: `cp .env.example .env && $EDITOR .env` works
exactly as well — the wizard is a convenience layer over the same file, not a required step. Full
mechanics of both the installer image and the wizard (including why this is necessarily a
two-pass process) are in [Installer image and setup wizard](#installer-image-and-setup-wizard).

After first boot, three values can only be collected *after* the relevant app has generated them
itself — `RADARR_API_KEY`, `SONARR_API_KEY` (each app's own **Settings → General → Security**),
and `PLEX_TOKEN` (any library item → **Get Info → View XML**, copy the `token=` value from the
URL). Paste them in via a second `--setup` run (it reloads your existing `.env` as defaults), then:

```bash
docker compose up -d --force-recreate control-panel
```

`control-panel` is the only container that reads these at container-*create* time, so a plain
`restart` won't pick up a `.env` change — it needs `--force-recreate`.

## Architecture

```
Prowlarr ──indexes──> (your trackers + Zilean's DMM cache-hash list)
   │
   ▼
Radarr/Sonarr/Lidarr/Readarr/Whisparr ──grab──> Decypharr (qBittorrent-compatible API)
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
Calibre-Web → reads ./media/books directly (Readarr's own root folder) - not through Zurg/Decypharr
```

**Two Decypharr instances, not one.** `docker-compose.yml` runs `decypharr` (port 8282, both
debrid backends, Radarr's + Lidarr's + Readarr's + Whisparr's download client) and
`decypharr-alldebrid` (port 8283, AllDebrid only, Sonarr's download client). Decypharr has no
per-provider category scoping — a single instance's `debrids[]` list is available to every
category on it — so a fully separate instance, with its own config and mount, is the only way to
keep AllDebrid exclusive to Sonarr instead of shared with Radarr. One consequence: the second
instance reports the same-looking `/app/downloads/<category>/...` path to Sonarr as the primary
instance does, but it's actually a different host directory — every AllDebrid-sourced Sonarr grab
was stuck at import until a second mount (`/app/downloads-ad`) plus a Remote Path Mapping in
Sonarr were added to translate between them:

```yaml
# docker-compose.yml, sonarr service
volumes:
  - ./config/sonarr:/config
  - /mnt:/mnt:rslave
  - ./config/decypharr/downloads:/app/downloads:rslave
  # Sonarr's exclusive AllDebrid path - decypharr-alldebrid reports outputPath as
  # /app/downloads/<category>/... to Sonarr's API, identical-looking to the primary
  # decypharr's own convention, but it's actually a different host directory.
  - ./config/decypharr-alldebrid/downloads:/app/downloads-ad:rslave
  - ./media/shows:/data/shows
```

```bash
# Remote Path Mapping added directly via Sonarr's API for the Decypharr-AllDebrid
# download client specifically - translates what that client reports into where
# Sonarr should actually look on its own filesystem:
curl -X POST http://192.168.4.105:8989/api/v3/remotepathmapping \
  -H "X-Api-Key: $SONARR_API_KEY" -H "Content-Type: application/json" \
  -d '{"host":"decypharr-alldebrid","remotePath":"/app/downloads/","localPath":"/app/downloads-ad/"}'
```

Root folders live on regular host disk (`./media/<type>`), never on Zurg's rclone FUSE mount —
that mount is read-oriented and does not support having new files or symlinks written into it
(confirmed directly: symlink, hardlink, and plain copy all fail there with `EIO`). This is the
single most important fact about how this stack is wired, and it regressed silently more than
once in this project's history (a library-import/rescan that registers pre-existing Zurg content
can reset that item's root folder back to `/mnt/zurg/<type>` in an app's own database — invisible
to git since it's app state, not stack config). If imports mysteriously stall, check whether the
affected item's root folder resolves to `/mnt/zurg/...` instead of `/data/...` before assuming a
mount or container problem.

> **Radarr-specific mount fragility.** Radarr bind-mounts `/mnt/zurg` and `/mnt/decypharr`
> directly (`/mnt/zurg:/mnt/zurg:rslave`) rather than the parent `/mnt` the way Sonarr/Lidarr/
> Readarr/Whisparr/Plex do. A direct bind of a FUSE mountpoint doesn't reliably survive that FUSE
> process being recreated underneath it (a Zurg image update, a resource-limit change, etc.) —
> only Radarr breaks, with `Socket not connected` inside the container and `accessible: false`
> from `/api/v3/rootfolder`, while every other app keeps working fine. Fix is `docker restart
> radarr` after any Zurg recreation — Control Panel's own whole-stack restart (see
> [Control Panel](#control-panel)) already sequences this correctly: mount providers first, wait
> for them to report healthy, Radarr last.

> **Disk usage, not just bandwidth.** Everyday use costs ~zero local disk — Plex streams
> `/mnt/zurg/*` and `/mnt/all/*` directly as read-only library locations, and the normal grab
> pipeline (Decypharr/NzbDAV → **symlink** into `/data/<type>`) never copies real video bytes. The
> exception is manually importing content that's already sitting on one of those read-only mounts
> into an app's own tracked library: `Hardlink` needs the same filesystem, which is impossible
> from a remote FUSE mount onto local disk, so `Copy` is the only option — and `Copy` writes a
> full permanent duplicate, not a temp file. A scoping pass once measured a candidate bulk-import
> from `/mnt/all/magnets` at 1,801 folders / 26,008 files / 29.8TB against 686GB of free local
> disk — scrapped for exactly that reason. Scope disk space, not just time, before doing this in
> bulk.

Seerr (formerly Overseerr/Jellyseerr — the projects merged) is the user-facing request page,
talking to Plex + all five `*arr` apps. Zilean specifically searches
[DebridMediaManager](https://debridmediamanager.com)'s shared hash-list of content already known
to be cached on Real-Debrid/AllDebrid, so grabs from it come back near-instantly.

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
├── scripts/                          # backup/alert/setup automation, all stdlib-only Python or bash
├── systemd/                          # user-scope units for boot automation, backups, alerts
└── media/{movies,shows,music,books,adult,audiobooks,youtube}  # every arr app's writable root
                                       # folder, mounted at /data/<type>; youtube/ is an inert
                                       # leftover from a removed Pinchflat integration
```

## The full service list

Every service currently defined in `docker-compose.yml`, in the order they appear:

| # | Service | Image | Port(s) | Profile |
|---|---|---|---|---|
| 1 | `prowlarr` | `ghcr.io/hotio/prowlarr:release` | 9696 | core |
| 2 | `zilean-postgres` | `postgres:18-alpine` | — | core |
| 3 | `zilean` | `ipromknight/zilean:v3.5.0` | 8181 | core |
| 4 | `decypharr` | `cy01/blackhole:v2.3` | 8282 | core |
| 5 | `decypharr-alldebrid` | `cy01/blackhole:v2.3` | 8283 | core |
| 6 | `zurg` | `ghcr.io/debridmediamanager/zurg@sha256:924f17...` | 9999 | core |
| 7 | `rclone-alldebrid` | `rclone/rclone:1.74.4` | — | core |
| 8 | `rclone-alldebrid-anime` | `rclone/rclone:1.74.4` | — | core |
| 9 | `radarr` | `ghcr.io/hotio/radarr:release` | 7878 | core |
| 10 | `sonarr` | `ghcr.io/hotio/sonarr:release` | 8989 | core |
| 11 | `lidarr` | `ghcr.io/hotio/lidarr:release` | 8686 | core |
| 12 | `readarr` | `lscr.io/linuxserver/readarr:0.4.19-nightly` | 8787 | core |
| 13 | `whisparr` | `ghcr.io/hotio/whisparr:v3` | 6969 | core |
| 14 | `calibre-web` | `lscr.io/linuxserver/calibre-web:latest` | 8083 | core |
| 15 | `nzbdav` | `nzbdav/nzbdav:latest` | 3001→3000 | core |
| 16 | `nzbdav-rclone` | `rclone/rclone:1.74.4` | — | core |
| 17 | `seerr` | `ghcr.io/seerr-team/seerr@sha256:c92d2d...` | 5055 | core |
| 18 | `plex` | `plexinc/pms-docker:1.43.2.10687-563d026ea` | 32400 (host net) | core |
| 19 | `byparr` | `ghcr.io/thephaseless/byparr@sha256:01a46a...` | 8191 | extras |
| 20 | `tautulli` | `ghcr.io/hotio/tautulli:release` | 8182 | extras |
| 21 | `control-panel` | built from `./control-panel` | 8420 | extras |
| 22 | `glances` | `nicolargo/glances@sha256:5bc5b6...` | 61208 | extras |
| 23 | `kometa` | `kometateam/kometa@sha256:98a0df...` | — | extras |
| 24 | `unpackerr` | `golift/unpackerr@sha256:4ec141...` | — | extras |
| 25 | `watchtower` | `nickfedor/watchtower:1.19.0` | — | extras |
| 26 | `dmm-mysql` | `mysql:8.4` | — | extras |
| 27 | `dmm-redis` | `redis:7-alpine` | — | extras |
| 28 | `adminer` | `adminer:5.4.2-standalone` | 8081 | extras |
| 29 | `dmm-migrate` | built from DMM git context, `target: build` | — | extras (one-shot) |
| 30 | `debridmediamanager` | built from DMM git context, `target: build` | 3000 | extras |
| 31 | `cleanuparr` | `ghcr.io/cleanuparr/cleanuparr:2.9.16` | 11011 | extras |
| 32 | `neutarr` | `iampuid0/neutarr:1.9.1` | 9705 | extras |
| 33 | `dozzle` | `amir20/dozzle:v10.6.8` | 8080 | extras |
| 34 | `maintainerr` | `ghcr.io/maintainerr/maintainerr:latest` | 6246 | extras |

`docker compose up -d` brings up the 18 core services; `docker compose --profile extras up -d`
adds the other 16. Both commands are safe to run repeatedly — Compose only recreates what's
actually out of sync with `docker-compose.yml`.

## The *arr apps

All five apps follow the identical wiring pattern: Prowlarr pushes indexers down via
`fullSync`, Decypharr (or `decypharr-alldebrid` for Sonarr) is the priority-1 download client,
NzbDAV is priority-2 fallback, Unpackerr extracts anything RAR'd, root folder is `./media/<type>`
mounted at `/data/<type>`, and Control Panel wires up RSS sync / search-missing / unstick /
manual-import against each one identically.

| App | Port | Root folder | Content type |
|---|---|---|---|
| Radarr | 7878 | `/data/movies` | Movies |
| Sonarr | 8989 | `/data/shows` | TV |
| Lidarr | 8686 | `/data/music` | Music |
| Readarr | 8787 | `/data/books` | Ebooks |
| Whisparr | 6969 | `/data/adult` | Adult (v3/"eros", series-style) |

All five were reinstated (Lidarr/Readarr in a prior session, Whisparr in this one) after having
been fully removed at various earlier points — see [History](#history) for why each was pulled
and why each came back. Every app's queue now works identically for Control Panel's
[Unstick and manual-import](#control-panel) actions.

### Why Readarr is pinned to a nightly linuxserver tag, not hotio

```yaml
# docker-compose.yml
readarr:
  <<: *common
  image: lscr.io/linuxserver/readarr:0.4.19-nightly
  container_name: readarr
```

Upstream Readarr is **officially retired** — "lack of developers... decided to retire the
project," per linuxserver.io's own deprecation notice. hotio, which publishes rolling
`:release`/`:testing`/`:nightly` channel tags for every other `*arr` app in this stack, doesn't
publish a Readarr image at all. linuxserver's own moving `develop`/`nightly` tags no longer
resolve to a valid manifest for this platform either. `0.4.19-nightly` is the **last version tag
that's actually pullable** — it will never receive another update, which is the accurate state of
the underlying project, not a mistake in how it's pinned here. If upstream Readarr is ever
un-retired or a fork picks up maintenance, this is the one image in the stack that should be
revisited on principle rather than left on autopilot.

### Why Whisparr is pinned to `:v3`, not `:latest`

```yaml
# docker-compose.yml
whisparr:
  <<: *common
  # v3 (aka "eros"), not the default "latest" tag - that maps to v2, the
  # older movie-style build. v3 is Sonarr-codebase-based (series/episode
  # tracking of scenes), the actively developed line.
  image: ghcr.io/hotio/whisparr:v3
```

hotio's Whisparr `:latest` resolves to v2 ("vorta", the movie-style build modeled on Radarr).
`:v3` ("eros") is the Sonarr-codebase-based, series/episode-tracking build and the actively
developed line — this stack deliberately tracks it, matching the rolling-channel-tag convention
used for Radarr/Sonarr/Lidarr's own `:release` tags (also rolling, not commit-pinned). Whisparr was
previously removed once (see [History](#history)) over a real bug in the specific build then
running (`DownloadedEpisodesScan` throwing on missing `path`) plus a root-folder regression — the
same regression class Radarr/Sonarr have both hit; watch for it here too.

### Real API examples

Every app exposes the same Servarr-family REST API shape (`/api/v3` for Radarr/Sonarr/Whisparr,
`/api/v1` for Lidarr/Readarr):

```bash
# Radarr's own health/liveness endpoint (what every healthcheck in this stack uses)
curl -sf http://192.168.4.105:7878/ping

# List Radarr's configured root folders
curl -s -H "X-Api-Key: $RADARR_API_KEY" http://192.168.4.105:7878/api/v3/rootfolder | jq .

# Trigger an immediate RSS sync on Sonarr
curl -X POST -H "X-Api-Key: $SONARR_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"RssSync"}' http://192.168.4.105:8989/api/v3/command

# Lidarr root folder (API v1, not v3)
curl -s -H "X-Api-Key: $LIDARR_API_KEY" http://192.168.4.105:8686/api/v1/rootfolder | jq .

# Whisparr v3's missing-search command name is MissingMoviesSearch, matching
# Radarr's naming despite tracking scenes as episodes - not MissingEpisodeSearch
# the way its Sonarr-codebase heritage would suggest. Confirmed against its own
# /api/v3/command endpoint, not assumed.
curl -X POST -H "X-Api-Key: $WHISPARR_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"MissingMoviesSearch"}' http://192.168.4.105:6969/api/v3/command
```

### The Sonarr `missing-aired` pagination gap (known, unresolved)

Sonarr's own Wanted/Missing UI has no way to filter to "monitored, no file, already aired" —
confirmed against its actual frontend bundle: `customFilterType` only covers
series/calendar/queue/history/blocklist/releases, not the missing-episodes page. Without
filtering, that list is buried under roughly 300,000 not-yet-aired episodes from daily/ongoing
shows (soaps, game shows, etc.) that this library's Sonarr instance tracks. Control Panel exposes
a purpose-built endpoint for this:

```python
# control-panel/app.py
@app.get("/api/arr/{app_name}/missing-aired")
def arr_missing_aired(app_name: str):
    ...
    # Sonarr: paginate ascending by air date and stop as soon as a future
    # (unaired) episode is hit, rather than scanning the whole ~300k list -
    # everything after that point in ascending order is also future.
    cutoff = datetime.now(timezone.utc)
    ...
    while True:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/wanted/missing",
                       params={"page": page, "pageSize": page_size,
                               "sortKey": "airDateUtc", "sortDirection": "ascending",
                               "includeSeries": "true"}, ...)
        ...
```

```bash
curl -s http://192.168.4.105:8420/api/arr/sonarr/missing-aired | jq .
curl -s http://192.168.4.105:8420/api/arr/radarr/missing-aired | jq .
```

Radarr's equivalent is a single unpaginated pass (`monitored && !hasFile && isAvailable`), since
Radarr's own movie list is orders of magnitude smaller than Sonarr's episode-level table. The
early-stop optimization above helps in the common case, but this endpoint has **no frontend
wiring in Control Panel's UI at all** (curl/API only, listed here for exactly that reason) and its
real-world latency against the full ~300k-record Sonarr instance hasn't been load-tested — treat
it as a genuine, unresolved performance risk on a library this size, not a solved problem, and see
[Known gaps and limitations](#known-gaps-and-limitations).

## The debrid pipeline: Zurg + Decypharr

**Zurg** (`ghcr.io/debridmediamanager/zurg@sha256:924f17...` — the sponsor-gated image, not the
public `zurg-testing` one) mounts pre-existing Real-Debrid content directly at `/mnt/zurg` for
Plex to read. **Decypharr** (`cy01/blackhole:v2.3`, run as two isolated instances — see
[Architecture](#architecture)) is the qBittorrent-API-compatible gateway every `*arr` app grabs
through; it adds a magnet to Real-Debrid/AllDebrid, waits for it to cache, and symlinks the result
into each app's `/app/downloads/<category>` (shared at the identical path across every container,
avoiding Remote Path Mappings entirely — Decypharr's own documented best practice).

```json
// config/decypharr/config.json (real, sanitized) - one debrid backend on this
// instance (Real-Debrid), symlink-only, categories for all five apps
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
  "categories": ["sonarr", "readarr", "lidarr", "radarr", "whisparr"],
  "refresh_interval": "30s",
  "max_downloads": 10
}
```

`allowed_file_types` in that same file was extended when Lidarr/Readarr/Whisparr were reinstated
to cover audio (`flac`, `mp3`, `m4a`, `ape`, ...), ebook (`epub`, `mobi`, `azw`, `azw3`, `cbr`,
`cbz`, `pdf`, ...), and remains inclusive of video/subtitle types alongside the original movie/TV
list — one shared allow-list across every category, not scoped per-app.

**Restricting a specific app to a specific debrid provider** is a per-arr field, distinct from the
overall `debrids[]` list:

```bash
# Radarr is pinned to Real-Debrid only (added to its arrs[] entry in
# config/decypharr/config.json) - Sonarr/Lidarr/Readarr/Whisparr are left on
# source: "auto" with no selected_debrid, so they can still fall through to
# AllDebrid. config/decypharr/config.json is gitignored (real API keys), so
# this is a live runtime edit, not something that shows up in git log.
{
  "name": "radarr",
  "source": "auto",
  "selected_debrid": "realdebrid"
}
```

**Restart command**, if Zurg's config ever needs tuning — the container runs the binary directly
and spawns its own rclone mount as a child process, so one restart handles both:

```bash
docker compose restart zurg
```

This briefly interrupts `/mnt/zurg` for a few seconds; do it when nothing's actively streaming.
`rclone-alldebrid` and `/mnt/all` are unrelated and untouched by this.

### Zurg's content-routing groups

`config/zurg/config.yml`'s `directories` block is what routes cached content into per-type
folders under `/mnt/zurg`. Groups are evaluated in ascending `group_order`, and **the movies entry
is a catch-all regex (`/.*/`) that must sort last** — every more specific group needs a lower
`group_order` or its content falls into `movies` instead:

```yaml
# config/zurg/config.yml (real, token/plex_token redacted)
directories:
  # Checked before the generic "shows" group below (has_episodes: true would
  # otherwise claim these first) - matches well-known fansub/release-group
  # tags plus an episode-number marker, so it only catches episodic anime.
  # Anime movies fall through to anime-movies below instead.
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
  # Restored - removed when Lidarr/Readarr were dropped, never re-added
  # until Lidarr's own reinstatement. Checked before the movies catch-all
  # below, or every audio release would land in movies instead.
  music:
    group: media
    group_order: 12
    filters:
      - regex: /(?i)\b(FLAC|MP3|CDDA|Vinyl|Discography|320kbps|Lossless|WEB-DL.*MP3)\b/
  # Restored - ebook releases for Readarr.
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
  # Same fansub-tag list as anime-shows, without the episode-marker
  # requirement - episodic anime is already claimed by anime-shows (lower
  # group_order, checked first), so whatever matches this tag list by the
  # time it's checked is movie-style anime.
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

`anime-shows` (8) < `shows` (10) < `music` (12) < `books` (14) < `adult` (17) < `anime-movies` (19)
< `movies` (20) — the exact ordering that keeps the catch-all from swallowing everything above it.
`music`/`books` existed once before, were removed as dead routing when Lidarr/Readarr were pulled
(see [History](#history)), and are now restored to feed the reinstated apps. `anime-shows`/
`anime-movies` are new, added for a dedicated Plex Anime library — see
[Plex](#plex) for the library setup and the fansub-tag regex's real-world accuracy so far.

**The fansub-tag list is deliberately not exhaustive** — it covers the release groups that
actually showed up in this account's cache (`SubsPlease`, `Erai-raws`, and others), not every
fansub group that exists. New groups that appear in future grabs and aren't in the list will fall
through to `shows`/`movies` instead of `anime-shows`/`anime-movies` — extend the regex's
alternation list when that happens rather than treating it as a bug.

### Zurg's mount is a supervised rclone subprocess, not built into the binary directly

Despite the container having `/dev/fuse`, `cap_add: SYS_ADMIN`, and `apparmor:unconfined` (which
look like Zurg mounts `/mnt/zurg` itself), the actual FUSE mount is a **separate rclone process
that Zurg spawns and supervises**, controlled by two config keys that were missing from
`config.yml` entirely until this was diagnosed:

```yaml
# config/zurg/config.yml
mount_path: /mnt/zurg
rclone_enabled: true
```

**Real incident, not a hypothetical**: without these two keys, Zurg's own dashboard shows the
mount as "Stopped ... Disabled in config," and a plain `docker restart zurg` leaves `/mnt/zurg`
completely empty afterward — silently, with no error surfaced anywhere in Plex or any `*arr` app,
just an empty directory. This apparently was only ever toggled on live through Zurg's own
dashboard UI (an in-memory setting that isn't written back to `config.yml`), so it looked like it
was "just working" until the next restart discarded it. Confirmed live: adding these two keys and
restarting produced `rclone started with mount /mnt/zurg` and `Mount verification successful` in
the logs, and every directory (`movies`, `shows`, `music`, `books`, `adult`, and the two new anime
groups) repopulated immediately. Same failure *class* as the `rclone-alldebrid` bug below, but a
different root cause and a real permanent fix rather than a recovery procedure — written into
`config.yml` now specifically so it can't silently regress to "in-memory only" again.

### Zilean ingestion from Zurg (a second hash source)

Beyond serving Plex, Zurg exposes a `/debug/torrents` endpoint that Zilean scrapes hourly to index
every torrent already cached on *this account* specifically — not just DebridMediaManager's public
hashlist:

```yaml
# docker-compose.yml, zilean service environment
Zilean__Ingestion__EnableScraping: "true"
Zilean__Ingestion__ZurgInstances__0__Url: "http://zurg:9999"
Zilean__Ingestion__ZurgInstances__0__EndpointType: "1"
```

```bash
# Force an immediate ingestion pass rather than waiting up to an hour for the
# next scheduled tick (the API service and a separate `scraper` CLI both ship
# in the same Zilean image):
docker exec zilean /app/scraper generic-sync
```

No AllDebrid equivalent exists — Zurg is a purpose-built app with this specific debug endpoint;
`rclone-alldebrid` is a generic FUSE tool with no matching "list my cached torrents as
name/hash/size JSON" endpoint. See [Known gaps and limitations](#known-gaps-and-limitations).

### Known transient issue: Real-Debrid rate limiting

Zurg polls Real-Debrid on a 10-second interval and Decypharr refreshes its own torrent/link cache
every 10/5 minutes respectively; under heavy simultaneous use (a large batch of grabs, a bulk
manual-import scan, several concurrent Plex streams all resolving through the same mount) this can
transiently hit Real-Debrid's own API rate limits. It self-recovers — Decypharr's
`rate_limit: "250/minute"` setting and its own retry logic handle backoff — but a burst of grabs
in a short window can visibly slow down as a result. Not a bug to fix, just a real characteristic
of a shared upstream API under load; see [Known gaps and limitations](#known-gaps-and-limitations).

## The Usenet pipeline: NzbDAV

**NzbDAV** (`nzbdav/nzbdav:latest` + an `nzbdav-rclone` sidecar) is Usenet's path into this stack —
like Zurg/Decypharr for debrid, it's a **virtual filesystem, not a real local download**: it
exposes Usenet content as a WebDAV server, `nzbdav-rclone` mounts that WebDAV at `/mnt/nzbdav`, and
completed downloads show up there as symlinks streamed on demand.

```yaml
# docker-compose.yml
nzbdav:
  image: nzbdav/nzbdav:latest
  # Host port 3001, not 3000 - DebridMediaManager already owns 3000 on this
  # host. Internally still :3000 (Radarr/Sonarr/etc. reach it as
  # http://nzbdav:3000 over stacknet, unaffected by the host mapping).
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
    # read-ahead sized for smooth playback of high-bitrate remuxes
    - "--buffer-size=0M"
    - "--vfs-read-ahead=512M"
```

**Provider**: a real block-account news server is configured inside NzbDAV's own UI
(**Settings → Usenet**), stored in `config/nzbdav/db.sqlite`'s `ConfigItems` table — not a config
file or `.env`. `.env.example` documents the credentials anyway (`NZBDAV_PROVIDER_*`,
`NZBDAV_WEBDAV_*`, `NZBDAV_ADMIN_*`, `NZBDAV_API_KEY`) purely as the source-of-truth convention
this stack uses everywhere: **if a credential lives in an app's own database or config rather than
being read from `.env` by Docker Compose, it's still documented in `.env.example` as the reference
copy**, with a comment explaining where it actually lives. NzbDAV itself never reads `.env`
directly.

**Import strategy** is set to "Symlinks — Plex" in NzbDAV's own SABnzbd-compatible settings, with
`Rclone Mount Directory` pointed at `/mnt/nzbdav` — this is what makes Radarr/Sonarr/etc. treat
completed downloads as importable files at all (the alternative, STRM files, is Emby/Jellyfin-only,
not Plex).

NzbDAV is wired as priority-2 in every `*arr` app, behind Decypharr's priority-1 — debrid is always
tried first, NzbDAV only fires for genuine cache misses. Real API examples via Control Panel's own
proxy (NzbDAV has a SABnzbd-style query API, not a dedicated REST API):

```bash
# Current Usenet download queue
curl -s http://192.168.4.105:8420/api/nzbdav/queue | jq .

# Recent history (completed/failed), last 20 by default
curl -s http://192.168.4.105:8420/api/nzbdav/history | jq .
```

```python
# control-panel/app.py - talks to NzbDAV's SABnzbd-compatible mode=queue/mode=history
def nzbdav_api(mode: str, **params) -> dict:
    r = httpx.get(f"{NZBDAV_URL}/api",
                  params={"mode": mode, "output": "json", "apikey": NZBDAV_API_KEY, **params})
    return r.json()
```

**A UI quirk worth knowing**: NzbDAV's own "Add Provider"/"Test Connection" form only submits once
every field has actually been focused/touched in the browser, even fields already holding a valid
default (e.g. the port/connection-type defaults). Clicking the button while any field is still in
its untouched default state does nothing — no request fires, nothing is written to `db.sqlite`,
and there's no error message explaining why. Click or tab through every field first.

This replaced **NZBGet**, which briefly ran in this exact role before being fully removed. NZBGet
is a real local downloader — files land on `./usenet`, then get imported into the library — which
wasn't actually the goal ("no disk storage" was the explicit ask, matching the debrid side's own
symlink-only model). Nothing NZBGet ever wrote is used by the current setup; its old
`config/nzbget/` and `usenet/` directories were left on disk untouched rather than wired into
anything.

## Indexing: Prowlarr, Zilean, Byparr

**Prowlarr** (`ghcr.io/hotio/prowlarr:release`, port 9696) holds every configured tracker and
pushes them down to all five `*arr` apps via `Settings → Apps` `fullSync`. Zilean is registered as
a `Generic Torznab` indexer:

```bash
curl -X POST -H "X-Api-Key: $PROWLARR_API_KEY" -H "Content-Type: application/json" \
  http://192.168.4.105:9696/api/v1/indexer \
  -d '{"name":"Zilean","implementation":"Torznab","fields":[
        {"name":"baseUrl","value":"http://zilean:8181"},
        {"name":"apiPath","value":"/torznab/api"}]}'
```

**Zilean** (`ipromknight/zilean:v3.5.0`, port 8181 + `zilean-postgres` on Postgres 18) indexes
DebridMediaManager's public cache-hash list (`Zilean__Dmm__EnableScraping`, hourly) plus, as of the
ingestion work described above, this account's own Zurg-cached torrents. It's tuned for this
host's real hardware rather than left on defaults sized for a machine with a few hundred MB of
RAM:

```yaml
# docker-compose.yml, zilean-postgres command block
command:
  - "postgres"
  - "-c"
  - "shared_buffers=512MB"      # Postgres default is 128MB regardless of host
  - "-c"
  - "effective_cache_size=1536MB"
  - "-c"
  - "random_page_cost=1.1"      # tuned for NVMe, not spinning disk
  - "-c"
  - "effective_io_concurrency=200"
```

```yaml
# docker-compose.yml, zilean service environment
Zilean__Imdb__NumberOfCores: "12"     # not UseAllCores - 4 of 16 threads left for Plex/desktop
Zilean__Imdb__UseLucene: "true"       # "massively faster" per Zilean's own docs, ~3GB extra RAM
DOTNET_gcServer: "1"                  # .NET Server GC - per-core heaps, throughput over latency
DOTNET_GCHeapHardLimit: "0xC0000000"  # 3GB hard limit inside the 4GB container ceiling
```

Zilean has no stats API of its own (`/health`, `/api/stats`, `/dmm/status` all 404) — Control
Panel queries its Postgres database directly:

```bash
curl -s http://192.168.4.105:8420/api/zilean/stats | jq .
# {"available": true, "total_hashes": 1510656, "imdb_matched": 128321}
```

Direct search, bypassing Prowlarr and every `*arr` app entirely — useful for checking whether
something's actually cached before grabbing it:

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"query": "Dune"}' http://192.168.4.105:8420/api/zilean/search | jq .
```

**Byparr** (`ghcr.io/thephaseless/byparr@sha256:01a46a...`, port 8191) solves Cloudflare/anti-bot
challenges for the indexers that need it, registered as Prowlarr's `FlareSolverr`-implementation
Indexer Proxy (Prowlarr's internal protocol name for this proxy type didn't change even though the
actual service behind it did — only the `host` field and display name changed when this replaced
FlareSolverr):

```bash
curl -X PUT -H "X-Api-Key: $PROWLARR_API_KEY" -H "Content-Type: application/json" \
  http://192.168.4.105:9696/api/v1/indexerproxy/1 \
  -d '{"implementation":"FlareSolverr","name":"Byparr","fields":[{"name":"host","value":"http://byparr:8191/"}]}'
```

Byparr uses Camoufox (a Firefox-based anti-detect browser that patches fingerprints in C++)
instead of FlareSolverr's Selenium + undetected-chromedriver, on the bet that its faster patch
cadence keeps up with Cloudflare's evolving detection signals better.

### Music/Books/XXX indexer coverage — verified live, not assumed

An earlier version of this document claimed Prowlarr had 0 indexers scoped to Lidarr/Readarr/
Whisparr's categories. That was checked directly against the live Prowlarr Applications API
(`GET /api/v1/applications`, which lists each `*arr` app's `syncCategories`) and found to be
wrong: Prowlarr currently syncs **15 indexers to Lidarr** (category 3000-range), **9 to Readarr**
(7000-range, plus 3030), and **21 to Whisparr** (6000-range). A live end-to-end test confirmed
Lidarr's chain actually works — see
[Lidarr's indexer + download-client chain is verified working end-to-end](#known-gaps-and-limitations).

Whisparr's 21 indexers do sync correctly, but two live search tests against them (`Test Subjects`,
then the far more mainstream `Brazzers House`) both returned "0 reports downloaded." The cause
isn't a wiring gap: Prowlarr's own raw search (`/api/v1/search?categories=6000`) finds hundreds of
matching torrents through an indexer called `0Magnet`, but that indexer's Torznab capability
declaration reports `movieSearchParams: []` — no movie-search support, only generic keyword
search — so Prowlarr correctly excludes it from Whisparr's sync (Whisparr's search flow requires
the movie-search contract). This is a structural limitation of the available public XXX-category
Torznab indexer definitions, not a bug in this stack's configuration. Details and the exact
`curl`/`dig` commands used to confirm all of this live in
[Known gaps and limitations](#known-gaps-and-limitations).

## Requests: Seerr

**Seerr** (`ghcr.io/seerr-team/seerr@sha256:c92d2d...`, port 5055 — formerly Overseerr/Jellyseerr,
the two projects merged) is the day-to-day entry point: search for a movie or show, click
Request, everything else happens automatically. Connected to Radarr and Sonarr as default servers
(the `Unlimited` quality profile on both, `/data/movies`/`/data/shows`). Not connected to
Lidarr/Readarr/Whisparr — Seerr's own settings API only recognizes `radarr` and `sonarr`; there's
no music/book/adult-content data model to connect the other three apps to, confirmed directly
against its settings schema, not an oversight.

```bash
# Seerr's own settings API accepts its stored API key as X-Api-Key - no session
# login needed for scripted config changes
curl -s -H "X-Api-Key: $SEERR_API_KEY" http://192.168.4.105:5055/api/v1/settings/radarr | jq .
```

## Plex

Containerized (official `plexinc/pms-docker` image, not a LinuxServer-style fork — a
PUID/PGID-forcing image would have recursively chowned the ~33GB library on first boot).

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

- **`network_mode: host`** is the one deliberate exception to this stack's `stacknet` bridge +
  published-port pattern — Plex's GDM auto-discovery, DLNA, and remote-access NAT-PMP/UPnP
  negotiation are unreliable on bridge networking.
- **Image pin, not `:latest`, not on Watchtower's train.** An unattended PMS version change on a
  live library is a higher blast-radius event than anywhere else in this stack (see
  [Image pinning policy](#image-pinning-policy)).
- **Existing libraries** (confirmed live via `/library/sections`):

  | Key | Title | Type | Agent | Locations |
  |---|---|---|---|---|
  | 4 | Movies | movie | `tv.plex.agents.movie` | `/home/bear/Stack/media/movies`, `/mnt/zurg/movies` |
  | 1 | TV Shows | show | `tv.plex.agents.series` | `/mnt/zurg/shows`, `/home/bear/Stack/media/shows`, `/mnt/all/magnets` |
  | 3 | Music | artist | `tv.plex.agents.music` | `/mnt/zurg/music`, `/home/bear/Stack/media/music` |
  | 8 | Audiobooks | artist | `tv.plex.agents.none` | `/home/bear/Stack/media/audiobooks` |
  | 9 | Adult | movie | `tv.plex.agents.movie` | `/mnt/zurg/adult` |
  | 10 | Anime Movies | movie | `tv.plex.agents.movie` | `/mnt/zurg/anime-movies`, `/home/bear/Stack/media/anime-movies` |
  | 11 | Anime Shows | show | `tv.plex.agents.series` | `/mnt/all-anime`, `/mnt/zurg/anime-shows`, `/home/bear/Stack/media/anime-shows` |

  `./media` is mounted at its identical host absolute path (`/home/bear/Stack/media`) so every arr
  app's writable root folder is reachable the moment it's added as a library location.

### Plex "Anime Movies" and "Anime Shows" libraries

Two libraries backed by Zurg's `anime-movies`/`anime-shows` content-routing groups (see
[The debrid pipeline](#the-debrid-pipeline-zurg--decypharr)) — stock Plex agents (`tv.plex.agents.movie`,
`tv.plex.agents.series`), not a dedicated anime metadata agent (Plex ships none by default; adding
one like HAMA would be a separate plugin-installation project, not done here).

Created directly via the Plex API rather than the web UI (faster, no coordinate-dependent
clicking):

```bash
curl -X POST "http://192.168.4.105:32400/library/sections?X-Plex-Token=$PLEX_TOKEN" \
  --data-urlencode "name=Anime Shows" --data-urlencode "type=show" \
  --data-urlencode "agent=tv.plex.agents.series" --data-urlencode "scanner=Plex TV Series" \
  --data-urlencode "language=en-US" \
  --data-urlencode "location=/mnt/zurg/anime-shows" \
  --data-urlencode "location=/home/bear/Stack/media/anime-shows"
```

Note the multi-`location` gotcha: `curl --data-urlencode` posting the params as a form body
returns a bare `400 Bad Request` with no explanation — Plex expects repeated `location=` params in
the **query string** itself (`POST` with an empty body), not the request body. Updating an
*existing* section's locations via `PUT /library/sections/{id}` has the same gotcha, plus it
silently 400s unless `name`/`agent`/`scanner`/`language` are also repeated in the same request —
a partial payload isn't treated as a partial update.

**`Anime Shows` also includes `/mnt/all-anime`** — a second, purpose-built rclone mount
(`rclone-alldebrid-anime`) exposing an `--include`-filtered view of the AllDebrid `all:magnets`
remote, using the same fansub-tag list as Zurg's two groups. AllDebrid has no content-routing-groups
feature of its own like Zurg does, so getting a filtered anime-only view out of it needed a whole
second rclone process (glob `--include` patterns, brackets escaped) rather than one more config
entry — this list has to be kept in sync by hand across two different filter syntaxes (Zurg's
regex vs. rclone's glob) since they can't share a single definition. See
[The debrid pipeline](#the-debrid-pipeline-zurg--decypharr) for the container definition.

**`Anime Movies` deliberately does *not* include `/mnt/all-anime`** — unlike Zurg (which splits
episodic vs. movie-style anime into two separate mount paths via the episode-marker regex), the
AllDebrid-side filter is a single flat mount with no equivalent split; rclone's glob syntax can't
express "has this tag AND lacks an episode-number pattern" as cleanly as Zurg's regex does. Adding
it to *both* libraries was tried first and immediately produced real false positives — Plex's
**movie** scanner matched raw episode files (`Honzuki No Gekokujou S4 13`, `Lord of Mysteries
02v3`, `Dr Stone New World 01/02`, etc.) as if each were its own standalone film, since nothing in
that flat directory tells a movie-type scanner "this is actually episodic." Caught and removed
within the same session — the corrected fix (this section's location list) plus the still-open
question this raises (real anime *movies* from AllDebrid currently have no path into this library
at all) are recorded in [Known gaps and limitations](#known-gaps-and-limitations).

**First-scan result, verified live**: 10 folders matched into `anime-shows` from Zurg's existing
Real-Debrid cache the moment the mount came back (see the mount-outage note above), then 19 more
distinct releases appeared from `/mnt/all-anime` once the AllDebrid-side filter mount was added —
all correctly anime-tagged (`SubsPlease`/`Erai-raws`/`Yameii`), zero false positives from either
source *once* `/mnt/all-anime` was scoped to `Anime Shows` only. 6 titles had auto-resolved Plex
metadata within the first couple of scan passes (*Classroom of the Elite*, *Dr. STONE*, *Mobile
Suit Gundam: The Witch from Mercury*, *One Piece*, *Star Blazers 2199*, plus one more) — the rest
sat unmatched, which is ordinary Plex-agent behavior for raw fansub-style folder names against
TheTVDB, not a filter problem; they need a manual **Match** in Plex's UI like any niche title
would. `anime-movies` had zero matches from Zurg on this first pass — no anime-movie-style release
happened to be cached on Real-Debrid yet, and (per above) AllDebrid isn't wired into this library
at all right now.

**This needs periodic re-checking as more content gets grabbed** — the fansub-tag list (see above)
only covers release groups seen so far in this account's cache, and there's only been one real
data point (Zurg's 10, then AllDebrid's 19) to validate against. Re-run the same spot-check
periodically, against both sources:

```bash
ls /mnt/zurg/anime-shows/ /mnt/zurg/anime-movies/ /mnt/all-anime/
curl -s -H "X-Plex-Token: $PLEX_TOKEN" http://192.168.4.105:32400/library/sections/11/all | \
  grep -oP 'title="[^"]*"'
```

### Plex "Audiobooks" and "Adult" libraries

**Audiobooks** (library key 8) is a **Music-type** library using the **"Plex Personal Media"
agent** (`tv.plex.agents.none`, the modern identifier for the legacy `com.plexapp.agents.none`)
rather than a real music-metadata agent — this is the standard workaround for audiobooks in Plex,
since Plex has no dedicated audiobook library type or agent. It's pointed at
`/home/bear/Stack/media/audiobooks` — that directory exists on disk but is currently empty, since
nothing populates it automatically (no `*arr` app manages audiobooks specifically).

**Adult** (library key 9) is a plain **Movie-type** library, originally pointed only at
`/mnt/zurg/adult` (matching Zurg's `adult` content-routing group). **Real bug, found and fixed
in v10.5.0**: that single location was always empty, and Whisparr's actual (and only) root
folder — the local writable mount `/mnt/zurg` never receives writes through — was never added
as a second `Location`, so every file Whisparr had grabbed and imported was invisible in Plex.
Now has both `/mnt/zurg/adult` and `/home/bear/Stack/media/adult`, matching every other content
type's dual-path pattern (see [Architecture](#architecture)).

Both were verified live, not just configured:

```bash
curl -s -H "X-Plex-Token: $PLEX_TOKEN" http://192.168.4.105:32400/library/sections | \
  grep -E 'title="(Audiobooks|Adult)"'
```

## Calibre-Web: ebooks

Plex has **no ebook/book agent at all** — confirmed live via `/system/agents`, no book/ebook
identifier present in the response — so Readarr's actual output needs a real reader app rather
than a fake Plex library pretending to be one. **Calibre-Web**
(`lscr.io/linuxserver/calibre-web:latest`) fills that role, reading Readarr's own root folder
directly:

```yaml
# docker-compose.yml
calibre-web:
  image: lscr.io/linuxserver/calibre-web:latest
  environment:
    PUID: ${PUID}
    PGID: ${PGID}
    TZ: ${TZ}
    DOCKER_MODS: linuxserver/mods:universal-calibre   # adds calibre-convert for format conversion
  volumes:
    - ./config/calibre-web:/config
    - ./media/books:/books     # same host directory as Readarr's own root folder
  ports:
    - "8083:8083"
```

The `universal-calibre` DOCKER_MOD adds the full Calibre conversion toolchain (needed for
converting between ebook formats, e.g. EPUB↔MOBI, inside the container) — Calibre-Web's base image
doesn't bundle it by default.

**Default credentials rotated.** Calibre-Web ships with a well-known default (`admin`/`admin123`)
that must be changed on first login. The new credential is documented in `.env` under
`CALIBRE_WEB_ADMIN_PASSWORD`, following this stack's established convention (see the NzbDAV
section above) of naming every real secret in `.env`/`.env.example` as its source of truth even
when the app itself stores it somewhere else (Calibre-Web's own `config/calibre-web/app.db`, in
this case):

```bash
# .env.example
# ---- Calibre-Web ----
# Own login DB (config/calibre-web/app.db), not read from .env - documented
# here as the source of truth only. Default admin/admin123 rotated on setup.
CALIBRE_WEB_ADMIN_USERNAME=admin
CALIBRE_WEB_ADMIN_PASSWORD=changeme
```

The real value lives only in `.env` (chmod-restricted, gitignored) — never in this document.

## Custom formats and quality profiles

Radarr and Sonarr each carry exactly one custom format, **"Block - Sample, Russian, Low-Quality
Sources"**, scored `-10000` in the one quality profile each app has (`Unlimited` — `minFormatScore`
is `0`, so this is a hard reject, not deprioritization). Four `required: false` conditions OR'd
together — any one matching rejects the release:

```bash
# 1. Sample releases (title-level; a bundled sample *file* inside an otherwise-
#    clean release is caught separately by each app's own per-file detection)
(?i)\bsample\b

# 2. Russian language - Radarr/Sonarr's own built-in LanguageSpecification (value 11)

# 3. Russian/Korean text or script, beyond just the declared-language field -
#    literal tags plus the actual Cyrillic and Hangul Unicode ranges, so a
#    release matches even if nothing tagged its language metadata correctly
(?i)\b(rus|russian|kor|korean)\b|[Ѐ-ӿ]|[가-힣ᄀ-ᇿ㄰-㆏]

# 4. Blocked low-trust sources/groups
(?i)\b(WEB-DL|WEBRip|BDRip|HDRip|DVDRip|HDTV|AMZN|NF|DSNP|CR|YTS|TGX|TorrentGalaxy|FGT|LOL|KILLERS|EPSiLON|Erai-raws)\b|rartv|rarbg|eztv
```

Verify what a given release title actually scores against these rules with each app's own parse
endpoint:

```bash
curl -s -H "X-Api-Key: $RADARR_API_KEY" \
  "http://192.168.4.105:7878/api/v3/parse?title=Movie.Name.2024.1080p.WEB-DL.RUS" | \
  jq '.customFormats, .customFormatScore'
```

This replaced an earlier Recyclarr + TRaSH-Guides sync (41/40 per-quality-tier custom formats,
synced daily) that was removed entirely for a long stretch — quality selection here was judged
simple enough (one profile, one blocklist format) that the daily sync and its dozens of moving
parts were more overhead than value. **Recyclarr was reinstated in v10.5.0**, but scoped much
narrower than before: it targets this same `Unlimited` profile directly rather than its own
competing profile, and only syncs five resolution-agnostic hygiene custom formats (Scene,
Obfuscated, Retags, No-RlsGroup, Bad Dual Groups) rather than the old 41/40-format full catalog
— `reset_unmatched_scores` is deliberately left off so the manual blocklist format above stays
untouched by every sync. See [History](#history) for the full Recyclarr story, including the two
real Postgres/Recyclarr major-version migrations the original sync took along the way, and the
v10.5.0 entry for why it came back scoped the way it did.

Lidarr carries its own additional custom format, **"Blocked Uploader (88 tag)"** — a regex
(`(?<!\d)88(?:cube)?\s*$`) rejecting a specific low-trust uploader's release-title tag
(`vtwin88cube` and similar), added after a real corrupted-archive investigation traced a run of
`rardecode: bad file checksum` failures to that uploader's catalog specifically, not to anything
in this stack's own download/extraction chain.

## DebridMediaManager (self-hosted)

Self-hosted instance of [DebridMediaManager](https://github.com/debridmediamanager/debrid-media-manager)
(the app behind debridmediamanager.com) — personal library browsing/organizing/casting, plus its
own on-demand per-title scraper. Four services, all `profiles: [extras]`:

```yaml
# docker-compose.yml (abridged)
dmm-mysql:            # mysql:8.4 - hard-required by DMM's own Prisma schema, not swappable
dmm-redis:            # redis:7-alpine - rate limiting
dmm-migrate:           # one-shot `npx prisma db push --accept-data-loss`, exits after running
debridmediamanager:    # the web app itself, port 3000
  build:
    context: https://github.com/debridmediamanager/debrid-media-manager.git#c2ceef94477e49ddd5c55606bf57959ffdf29b9e
    target: build      # NOT the default deploy stage - see below
```

No pre-built image exists anywhere for this project (checked both GHCR and Docker Hub) — it's
built from a **git-context build pinned to a specific commit**, not `main`, consistent with this
stack's pin-everything policy.

**Real-Debrid/AllDebrid/TorBox credentials are entered in the browser** (`localStorage`), never a
server-side secret. `TMDB_KEY`/`MDBLIST_KEY`/`OMDB_KEY`/`TRAKT_CLIENT_ID`/`TRAKT_CLIENT_SECRET`/
`GH_PAT` are reused directly from Kometa's already-configured keys rather than signed up fresh.

**Search needs a local IMDB title index, not a live API call** — `api/search/title.ts` queries
`imdb_title_basics`/`imdb_title_akas`/`imdb_title_ratings` directly (confirmed by reading the
actual query source). `scripts/import-imdb-data.py` streams IMDB's public dataset dumps directly
from `datasets.imdbws.com`, filters to exactly what the search query touches (`movie`/`tvSeries`/
`tvMiniSeries`, non-adult), and loads them via `LOAD DATA INFILE`:

```bash
curl -s "http://192.168.4.105:3000/api/search/title?keyword=Yellowstone%202018" | jq .
```

`systemd/stack-imdb-sync.timer` runs this daily at 04:15, matching IMDB's own publish cadence.

**Two real upstream bugs worked around without vendoring a modified Dockerfile** (both would have
lost the clean pin-by-commit build):
1. The default `deploy` stage generates the Prisma Client without `openssl` installed, so Prisma
   silently generates the wrong query engine binary and the app crash-loops on startup. Fixed by
   running from the `build` stage instead (full toolchain present) with a fix-then-start command:
   ```yaml
   command: >
     sh -c "apt-get update && apt-get install -y -q openssl curl tzdata &&
     rm -rf /var/lib/apt/lists/* && npx prisma generate &&
     npx next start -H 0.0.0.0 -p 3000"
   ```
2. `npx prisma` in the deploy stage (which strips devDependencies including the Prisma CLI itself)
   silently downloads a random newer major version off the registry at runtime instead of using
   the pinned one — same `target: build` fix covers this too.

## Automation extras: Kometa, Cleanuparr, NeutArr, Unpackerr, Watchtower

**Kometa** (`kometateam/kometa@sha256:98a0df...` — official image, not the LinuxServer fork, which
resets `/config` ownership on every start) automates Plex collections, metadata, and overlay art.
No web UI — a scheduled batch job (05:00 daily by default), so it has no port and no Quick Link;
its "is it doing anything" signal is just its own live CPU on Control Panel's container grid.
Connected to Plex, TMDb, Radarr, Sonarr, Tautulli, Trakt, and MyAnimeList.

```bash
# Run it now instead of waiting for 05:00, optionally scoped to specific libraries
curl -X POST -H "Content-Type: application/json" \
  -d '{"libraries": ["Movies"]}' http://192.168.4.105:8420/api/kometa/run
```

**Cleanuparr** (`ghcr.io/cleanuparr/cleanuparr:2.9.16`, port 11011) and **NeutArr**
(`iampuid0/neutarr:1.9.1`, port 9705) automate what Control Panel's own "unstick" and "search
missing" buttons already do by hand, on a schedule, for the whole library. Roles are deliberately
split: Cleanuparr owns strikes (3-strike failed-import detection), a community malware blocklist
checked hourly, and stalled-download cleanup; NeutArr owns missing-content/quality-upgrade
hunting exclusively — Cleanuparr's own built-in proactive search stays disabled so the two apps
don't redundantly hunt the same libraries against the same indexers. NeutArr is wired to all
five `*arr` apps (Sonarr, Radarr, Lidarr, Readarr, Whisparr — configured as its "Whisparr V3"
app type, not V2, matching this stack's `:v3` "eros" pin), each instance's URL/API key set
directly in `config/neutarr/{sonarr,radarr,lidarr,readarr,eros}.json` (a straight host bind
mount at `/config`, editable without going through NeutArr's own UI — its own "Apps" settings
page hits the same files).

> **NeutArr, not Huntarr.** NeutArr is a hardened fork tracing through `elfhosted/newtarr`'s fork
> of Huntarr v6.6.3 — the last clean release before Huntarr's own maintainer suppressed reports of
> an unauthenticated auth-bypass that leaked every connected `*arr` app's API keys in cleartext,
> then took the repo private and banned users raising the issue. Never add Huntarr proper to this
> stack; NeutArr's whole reason for existing is that vetted alternative.

**Unpackerr** (`golift/unpackerr@sha256:4ec141...`) auto-extracts RAR'd releases across all five
`*arr` apps:

```yaml
UN_RADARR_0_URL: http://radarr:7878
UN_RADARR_0_API_KEY: ${RADARR_API_KEY}
UN_LIDARR_0_URL: http://lidarr:8686
UN_LIDARR_0_API_KEY: ${LIDARR_API_KEY}
# ...same pattern for sonarr/readarr/whisparr
```

Needs each app's actual `/app/downloads/...` path mounted, not just `/mnt` — the archives it needs
to reach live at the path each app's queue reports as `outputPath`, not the resolved symlink
target.

**Watchtower** (`nickfedor/watchtower:1.19.0` — the maintained fork; `containrrr/watchtower` is
archived and its bundled Docker client is too old for this host's Engine API version)
auto-updates the channel/version-tag-pinned images daily at 4am, posting every update (or failed
update) to Discord first via Shoutrrr rather than updating silently:

```yaml
WATCHTOWER_SCHEDULE: "0 0 4 * * *"
WATCHTOWER_NOTIFICATIONS: "shoutrrr"
WATCHTOWER_NOTIFICATION_URL: ${DISCORD_WATCHTOWER_SHOUTRRR_URL}
```

Digest-pinned images (Seerr, Glances, Kometa, Unpackerr, Byparr) and exact-version-tag-pinned ones
(Zilean, Decypharr, Watchtower itself, Plex, Readarr) are **not** meaningfully auto-updated by
this — a digest or exact version tag is immutable, so Watchtower never finds anything new to pull
for those. See [Image pinning policy](#image-pinning-policy).

## Monitoring extras: Tautulli, Glances, Dozzle, Adminer

- **Tautulli** (`ghcr.io/hotio/tautulli:release`, port 8182) — Plex watch-history/stats dashboard.
- **Glances** (`nicolargo/glances@sha256:5bc5b6...`, port 61208) — real *host* CPU/memory/
  disk/uptime, not container-scoped (`pid: host` + a read-only `/:/rootfs` mount). Control Panel
  proxies this for its overview strip.
- **Dozzle** (`amir20/dozzle:v10.6.8`, port 8080) — real-time log viewer for every container, the
  one thing Control Panel's grid can't show (state/health/CPU/mem, not log content). Read-only
  `docker.sock` mount.
- **Adminer** (`adminer:5.4.2-standalone`, port 8081) — single-file PHP database browser in front
  of `dmm-mysql`. Chosen over phpMyAdmin for a smaller attack surface; previously the only way to
  inspect DMM's data was `docker exec -it dmm-mysql mysql ...`.

## Maintainerr: Plex library lifecycle

Added after evaluating [RandomNinjaAtk/arr-scripts](https://github.com/RandomNinjaAtk/arr-scripts)
for anything worth adopting — almost none of it fit (it requires LinuxServer.io's
`/custom-services.d`/`/custom-cont-init.d` init-hook directories, which the hotio-based
Radarr/Sonarr/Whisparr images here don't have; its headline features either reverse a past
decision — Recyclarr, removed in v3.0.0 — duplicate something already native and better here
(PlexNotify → this stack's own Plex webhook hooks; its Queue Cleaner → Control Panel's Unstick), or
introduce direct-scraping tools (`deemix`, `tidal-dl`, `yt-dlp` trailers) that conflict with this
stack's Usenet+debrid-only, zero-local-disk architecture). **Maintainerr** was the one idea from
that research that's genuinely a good fit: API-driven, its own container, no base-image
dependency.

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

It handles the other half of the request lifecycle Seerr starts — removing watched/stale content
on rules you define, so the Zurg/Decypharr mount and local `./media` footprint don't grow
unbounded without manual pruning. All server connections (Plex, Radarr, Sonarr, Seerr, Tautulli)
are configured through its own settings API/UI, not environment variables:

```bash
# Plex requires the auth token saved first, separately from the rest of the connection details
curl -X POST -H "Content-Type: application/json" http://localhost:6246/api/settings/plex/token \
  -d "{\"plex_auth_token\": \"$PLEX_TOKEN\"}"
curl -X PATCH -H "Content-Type: application/json" http://localhost:6246/api/settings \
  -d '{"plex_hostname":"192.168.4.105","plex_port":32400,"plex_ssl":0,
       "plex_machine_id":"72ecc884f6bcd5f8bc4e4562b6b81e03ea9209e5","plex_manual_mode":1}'

# Radarr/Sonarr/Seerr/Tautulli are simpler - one call each
curl -X POST -H "Content-Type: application/json" http://localhost:6246/api/settings/radarr \
  -d "{\"serverName\":\"Radarr\",\"url\":\"http://radarr:7878\",\"apiKey\":\"$RADARR_API_KEY\"}"
```

**Lidarr/Readarr/Whisparr aren't supported by Maintainerr at all** — its own settings controller
only exposes `/radarr` and `/sonarr` connection endpoints, nothing for the other three `*arr`
apps. Not a gap in this stack's setup; a real limitation of what Maintainerr itself connects to.

**Two starter rules were imported from Maintainerr's community rule library** (the highest-karma
entries for a Seerr-based setup, 980/980) — one per Movies (library 4) and TV Shows (library 1):
"seen by the Seerr requester & older than 30 days, OR unwatched & older than 90 days." **Both were
created with `isActive: false`** — Maintainerr's rule engine runs on a real cron schedule
(`rules_handler_job_cron`, every 8 hours by default) and actually deletes matching media, so
nothing was left enabled without a human reviewing the exact rule first. Review and flip them on
in the UI (`Rules` tab) once you're satisfied they match what you actually want kept/removed:

```bash
curl -s http://localhost:6246/api/rules | \
  python3 -c "import sys,json; [print(r['id'], r['name'], r['isActive']) for r in json.load(sys.stdin)]"
```

## Control Panel

`control-panel/` — a custom-built FastAPI app (`build: ./control-panel`, not a pulled image), the
single dashboard for this stack: live container status/control, host stats, Zilean's hash count,
one-click ops actions, a direct Zilean search with grab-to-Decypharr, and per-app queue tools.
Port **8420**. This is what let Heimdall and Homepage (two earlier link-launcher/widget-dashboard
pairs) be removed entirely — see [History](#history).

### API surface

```python
# control-panel/app.py - the ARR_APPS dict this whole panel is built around
ARR_APPS = {
    "radarr":  {"url": "http://radarr:7878",   "api": "v3", "search_command": "MissingMoviesSearch"},
    "sonarr":  {"url": "http://sonarr:8989",   "api": "v3", "search_command": "MissingEpisodeSearch"},
    "lidarr":  {"url": "http://lidarr:8686",   "api": "v1", "search_command": "MissingAlbumSearch"},
    "readarr": {"url": "http://readarr:8787",  "api": "v1", "search_command": "MissingBookSearch"},
    "whisparr":{"url": "http://whisparr:6969", "api": "v3", "search_command": "MissingMoviesSearch"},
}
QUEUE_ARR_APPS = ("radarr", "sonarr", "lidarr", "readarr", "whisparr")
```

| Endpoint | Method | What it does |
|---|---|---|
| `/healthz` | GET | Liveness probe (what the container's own healthcheck uses) |
| `/api/status` | GET | Running/health state for every container in the compose project |
| `/api/containers` | GET | Full grid: state, health, image, live CPU/mem per container |
| `/api/system/stats` | GET | Host CPU/mem/disk/uptime, proxied from Glances |
| `/api/zilean/stats` | GET | Total indexed hashes + IMDB-matched count, from `zilean-postgres` directly |
| `/api/kometa/run` | POST | `docker exec`s a Kometa run, optionally scoped to `{"libraries": [...]}` |
| `/api/plex/scan` \| `/empty-trash` \| `/optimize-db` \| `/clean-bundles` | POST | Plex maintenance actions |
| `/api/plex/libraries` | GET | Library names/keys, read live from Plex (not hardcoded) |
| `/api/plex/updates` | GET | Running Plex version + any newer release on its channel (check only, never auto-applies) |
| `/api/nzbdav/queue` \| `/history` | GET | NzbDAV's current queue / recent history |
| `/api/zilean/search` | POST | `{"query": "..."}` → title/year/resolution/quality/size/hash results |
| `/api/decypharr/grab` | POST | `{"hash": "...", "title": "..."}` → adds a magnet to Decypharr under a dedicated `manual` category |
| `/api/arr/{app}/rss-sync` \| `/search-missing` | POST | Per-app RSS sync / missing-search |
| `/api/arr/{app}/unstick` | POST | Removes + blocklists + re-searches every `warning`/`error` queue item |
| `/api/arr/{app}/manual-import` | GET/POST | Lists importable files across stuck queue items; POST executes one |
| `/api/arr/{app}/manual-import-all` | POST | Bulk-imports every candidate the GET above lists, in one command |
| `/api/arr/{app}/missing-aired` | GET | Monitored + no file + already-aired (see [The `*arr` apps](#the-arr-apps)) |
| `/api/container/{name}/start` \| `/stop` \| `/restart` | POST | Individual container control, validated against the live compose project |
| `/api/stack/restart-all` | POST | Restarts everything except itself, mount providers first (see below) |

### Grab: a real, non-undoable action

```python
# control-panel/app.py
INFO_HASH_RE = re.compile(r"^[0-9a-fA-F]{40}$")

@app.post("/api/decypharr/grab")
def decypharr_grab(payload: GrabRequest):
    info_hash = payload.hash.strip().lower()
    if not INFO_HASH_RE.match(info_hash):
        # Zilean's index is scraped from a public hashlist and isn't perfectly
        # clean - Decypharr's own magnet parser 400s with no application-level
        # log line at all for a malformed hash, which is indistinguishable from
        # a real bug without this check.
        fail(f"'{info_hash}' isn't a valid 40-character info hash...", status_code=400)
    ...
```

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"hash": "08ada5a7a6183aae1e09d831df6748d566095a10", "title": "Example.2024.1080p"}' \
  http://192.168.4.105:8420/api/decypharr/grab
```

This is a genuine action against the live debrid account — it's the only endpoint besides the
whole-stack restart that the frontend guards with an arm/confirm double-click rather than firing
on a single click.

### Whole-stack restart: mount-order aware

```python
# control-panel/app.py
MOUNT_PROVIDERS = {"zurg", "decypharr", "decypharr-alldebrid", "rclone-alldebrid"}
MOUNT_DEPENDENTS = {"radarr"}

def worker():
    for c in providers: c.restart(timeout=30)
    for c in providers: wait_for_healthy(c)
    for c in rest: c.restart(timeout=30)
    for c in dependents: c.restart(timeout=30)   # Radarr last, after mounts are confirmed healthy
```

```bash
curl -X POST http://192.168.4.105:8420/api/stack/restart-all
```

This exists specifically because of the Radarr mount-fragility issue described in
[Architecture](#architecture) — restarting Radarr before its mount providers have come back
healthy reproduces that exact bug.

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

This isn't a login gate (see [Security](#security)) — it closes a real gap where any website a
LAN browser visits, not another device on the LAN, could otherwise fire a same-origin-exempt POST
at this panel's docker.sock-backed start/stop/restart/exec endpoints.

## CLI: the `stack-*` fish functions

A parallel terminal interface to Control Panel's API, tracked in `~/.dotfiles`
(`.config/fish/functions/`), all built on one private helper:

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
stack-arr lidarr rss-sync                       # radarr/sonarr/lidarr/readarr/whisparr; or search-missing / unstick
stack-arr-import-candidates whisparr            # list files ready to manually import
stack-arr-import readarr 0                      # import candidate #0 from the list above
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

Real example — search Zilean, then grab the top hit:

```fish
> stack-zilean-search dune
Dune Part Two 2024  [2160p BluRay REMUX]  84.3 GB
  hash: 08ada5a7a6183aae1e09d831df6748d566095a10
...
> stack-grab 08ada5a7a6183aae1e09d831df6748d566095a10 "Dune Part Two"
Added "Dune Part Two" to Decypharr - will appear once Real-Debrid/AllDebrid finishes caching.
```

`stack-arr`, `stack-arr-import-candidates`, and `stack-arr-import` accept
`radarr`/`sonarr`/`lidarr`/`readarr`/`whisparr` as their app argument, matching Control Panel's own
`/api/arr/{app}/...` endpoints and `QUEUE_ARR_APPS` set exactly:

```fish
# ~/.dotfiles/.config/fish/functions/stack-arr.fish
function stack-arr --description 'Trigger an *arr app maintenance action'
    if not contains -- $argv[1] radarr sonarr lidarr readarr whisparr
        echo "Unknown app '$argv[1]' - use radarr, sonarr, lidarr, readarr, or whisparr." >&2
        return 1
    end
    ...
```

`stack-bazarr-search` was removed entirely along with Bazarr itself — it called
`/api/bazarr/search-wanted`, an endpoint that no longer exists in `control-panel/app.py`.

## Backups

`./config` holds every app's settings, database, and plaintext API keys — none of it is in git,
and it's the one part of this stack that isn't reproducible by re-running `docker compose up` or
re-pulling images.

- **`scripts/backup-config.sh`** — dumps `zilean-postgres` (`pg_dump`) and `dmm-mysql`
  (`mysqldump`) first, then `restic backup ./config`, then `restic forget --prune` (`--keep-daily
  7 --keep-weekly 4 --keep-monthly 6`). Repo at `~/backups/stack-restic-repo`, restic-encrypted.
  Run daily at 03:30 by `systemd/stack-backup.timer`, before Watchtower's 4am updates. An optional
  off-site leg mirrors the same backup to any restic-supported remote (`BACKUP_REMOTE_REPOSITORY`
  in `.env`) with its own retention pass and Discord tag, left unset by default. A monthly
  `restic check --read-data-subset=10%` integrity check runs on the 1st of the month against both
  the local repo and the remote one if configured.
- **Excluded from the restic backup**: `decypharr/cache` and `decypharr-alldebrid/cache` (fully
  regenerable FUSE caches), every app's `logs`/`log` directory, `zilean-postgres`'s and
  `dmm-mysql`'s raw datadirs (the `pg_dump`/`mysqldump` logical dumps above cover those instead —
  file-level copying a *running* database's data directory can produce an inconsistent restore),
  and several regenerable Plex subdirectories (`Metadata` — 28GB of re-fetchable posters/art,
  `Cache`, `Codecs`, `Logs`, `Crash Reports`, plus the sibling `plex-transcode` directory).
- **`scripts/arr-app-backup.py`** + `systemd/stack-arr-backup.timer` (daily, 03:40) — triggers
  each `*arr` app's own native `Backup` command (`POST /api/v3/command` or `/api/v1/command`),
  producing the same portable `.zip` each app's own Settings → Backup screen would, which is what
  each app's own restore flow actually expects as input:
  ```bash
  curl -X POST -H "X-Api-Key: $RADARR_API_KEY" -H "Content-Type: application/json" \
    -d '{"name":"Backup"}' http://192.168.4.105:7878/api/v3/command
  ```
- **`scripts/backup-claude-dir.sh`** + `systemd/stack-claude-backup.timer` (nightly, midnight) —
  a cruder, separate backup: a full `tar --zstd` snapshot of the entire `~/Claude` directory (this
  repo included, plus everything else under it) to `~/Dropbox/Claude-backup-latest.tar.zst`,
  overwritten in place each run rather than dated/retained. Deliberately distinct from
  `backup-config.sh`'s incremental, retained restic run — this is a coarse whole-tree copy, and
  needs passwordless `sudo` since the tree includes container-owned files (`dmm-mysql`/
  `zilean-postgres` data directories) a normal user can't read.
- **Known limitation**: this host has a single physical disk (btrfs, one NVMe) — the local restic
  repo protects against config corruption and accidental deletion, not disk failure. The off-site
  leg above closes that gap when configured; it isn't by default.

Verify anytime:

```bash
RESTIC_PASSWORD_FILE=~/backups/.restic-password restic -r ~/backups/stack-restic-repo snapshots
```

## Alerting (Discord)

One webhook (`DISCORD_WEBHOOK_URL` in `.env`) backs several independent alert paths, all through
`scripts/notify-discord.sh` (no-ops silently if unconfigured):

- **Backups** — success/warning/failure from `backup-config.sh`, plus an `OnFailure=` systemd hook
  as a second layer for failures the script itself can't self-report.
- **Watchtower** — every real image update (or failed one) posts before it happens, via Shoutrrr
  (`discord://<token>@<id>` format, a separate URL from the plain webhook the others use).
- **Container health** — `scripts/check-container-health.sh`, every 5 minutes, diffs the
  unhealthy/restarting container set against its last poll and only posts on an actual *change*.
- **Plex additions** — `scripts/plex-webhook-listener.py`, a long-running listener bound to
  `127.0.0.1:${PLEX_WEBHOOK_PORT}` (default 9880) reacting to Plex's own native `library.new`
  webhook (Plex Pass feature) instantly, with poster boxart re-uploaded as a file attachment.
  Requires a one-time manual step: Plex web app → **Settings → Webhooks → Add Webhook** →
  `http://127.0.0.1:9880/plex-webhook`.
- **Plex removals** — `scripts/plex-library-report.py`, every 30 minutes (Plex has no "item
  removed" webhook event, so this is still a poll-and-diff rather than instant).
- **`*arr` backups** — one embed per day covering both the native-backup trigger above.
- **Grab/import/upgrade/health events from all five `*arr` apps** — configured as each app's own
  native **Discord** notification connection (not a script), pointed at the same
  `DISCORD_WEBHOOK_URL`. Event selection differs slightly per app's own naming
  (Radarr/Sonarr/Whisparr: `onGrab`/`onDownload`/`onUpgrade`; Lidarr/Readarr:
  `onGrab`/`onReleaseImport`/`onUpgrade`, plus `onDownloadFailure`/`onImportFailure` since neither
  exposes a Sonarr/Radarr-style "manual interaction required" event), but all five also fire on
  `onHealthIssue` and `onApplicationUpdate`. Verified live via each app's own
  `POST /api/v{1,3}/notification/test` — a real message reaches the channel.

  ```bash
  curl -H "X-Api-Key: $RADARR_API_KEY" http://localhost:7878/api/v3/notification/3 | \
    curl -X POST -H "X-Api-Key: $RADARR_API_KEY" -H "Content-Type: application/json" \
      -d @- http://localhost:7878/api/v3/notification/test
  ```

  **Known tradeoff, not yet addressed**: this shares one channel with Watchtower/backup/health
  alerts above — five apps' worth of grab/import noise lands in the same place as the alerts you
  actually want to notice quickly. Worth a second webhook/channel if it gets noisy; not done here
  since the ask was specifically "the existing webhook," not a new one.

## Image pinning policy

Every image is pinned, using whichever approach doesn't change what's actually running:

- **Channel tags** (`ghcr.io/hotio/radarr:release`, etc.) for the hotio images (Prowlarr, Radarr,
  Sonarr, Lidarr, Tautulli) — hotio's whole model is rolling channels identified by git-hash, not
  semver, so this is as close to "pin to the stable channel, explicitly" as that upstream
  supports. Whisparr is pinned to `:v3` specifically (a major-version channel, not just `:release`)
  for the reason described in [The *arr apps](#the-arr-apps).
- **Version tags** (`ipromknight/zilean:v3.5.0`, `cy01/blackhole:v2.3`,
  `nickfedor/watchtower:1.19.0`, `lscr.io/linuxserver/readarr:0.4.19-nightly`) where the upstream
  project tags real releases and the current running image matches.
- **Digest pins** (`@sha256:...`) for Seerr, Glances, Kometa, Unpackerr, and Byparr — in every one
  of these cases the currently-running `:latest` build is *ahead* of the newest tagged release
  upstream has cut, so no tag exists that wouldn't be a downgrade. Byparr specifically doesn't
  publish clean `vX.Y.Z` tags on GHCR at all (only `:latest`, `:main`, and commit-sha/arch-specific
  tags), so a digest was the only way to freeze a specific build.
- **Version tag, manually bumped, not on Watchtower's train** for Plex
  (`plexinc/pms-docker:1.43.2.10687-563d026ea`) — an unattended PMS version change on a live
  library is worth avoiding.
- **Pinned to a specific git commit**, not `main`, for the two DebridMediaManager services built
  from source (no pre-built image exists upstream) — building an unpinned git ref would be the
  self-built equivalent of `:latest`.

Watchtower auto-updates only the channel-tag-pinned images (posting to Discord first). Digest-
pinned and exact-version-tag-pinned images are frozen until someone manually re-checks upstream
and bumps the pin in `docker-compose.yml` — a digest or exact tag is immutable, so Watchtower never
finds anything new to pull for those.

## Resource limits

Every container in this stack now has `mem_limit`/`mem_reservation`/`cpus`, sized from real
`docker stats` observation where a container showed a real baseline worth capping, or as cheap
defensive insurance otherwise:

| Service | mem_limit | cpus | Why |
|---|---|---|---|
| `plex` | 6GB | 12 | Library scans alone (zero playback) briefly hit 100% CPU; HW transcode covers decode, not scan/analysis |
| `zurg` | 1GB | 6 | Sustained ~20-25% CPU baseline (10s Real-Debrid poll + serving reads) |
| `decypharr` / `decypharr-alldebrid` | 1.5GB each | 4 each | Highest steady RAM baseline besides Postgres/Zilean (~540-580MB) |
| `zilean` | 4GB | 12 | Lucene IMDB matching, 12 of 16 host threads reserved (4 left for desktop use) |
| `zilean-postgres` | 2GB | 4 | Tuned for NVMe + this host's real hardware, not Postgres's hardware-agnostic defaults |
| `byparr` | 2GB | 4 | Each Cloudflare solve spins up a real Camoufox browser instance |
| `kometa` | 2GB | 4 | 642MB observed resident even while idle - largest non-DB idle footprint |
| `dmm-mysql` | 2GB | 2 | Holds low-millions-of-rows IMDB index with `@@fulltext` indexes to maintain |
| `debridmediamanager` | 1.5GB | 2 | Runs from the `build` stage (full devDependencies), not the leaner deploy stage |

Everything else (Seerr, all five `*arr` apps, NzbDAV, Adminer, Dozzle, Watchtower, etc.) carries a
smaller generous ceiling as defensive insurance rather than from observed pressure — see
`docker-compose.yml` directly for exact current values, which change more often than this document
is updated.

## Security

Every web UI in this stack publishes its port directly on the host with **no login gate** — the
same model this stack has landed on twice now after trying and reverting a full auth layer once
(see [History](#history)):

- Everything is reached through plain `http://<ip>:<port>` — no certificate, no account.
- These addresses only work from devices on the home LAN, or a [Tailscale](https://tailscale.com)
  network if configured — nothing here is reachable from the public internet unless you
  specifically set that up.
- **Control Panel** and **Dozzle** are worth knowing about specifically — both hold read-write (or
  read-only, for Dozzle) `docker.sock` access and can restart or inspect any container in this
  stack. Don't put this stack on a network you don't trust, and don't forward any of these ports
  publicly.
- Control Panel's own CSRF/Origin-Host validation (see [Control Panel](#control-panel)) is *not*
  auth — it closes a specific cross-origin-POST gap, not a login requirement. It's the one piece
  of the earlier network-security effort that was deliberately kept when the rest was reverted.
- `config/decypharr/config.json` and `config/zurg/config.yml` both contain real API tokens in
  plaintext, `chmod 600`. Worth knowing if this host is ever shared or backed up somewhere less
  trusted.

If a login/auth layer is ever wanted back — say, before any public exposure — a full
Traefik + Authelia + CrowdSec stack was already built, verified working end-to-end (real TOTP 2FA,
a real CrowdSec-banned IP getting a real 403), and then reverted once the day-to-day friction
outweighed the benefit for a LAN-only deployment. See [History](#history) for exactly what that
looked like if you want to rebuild it.

## CI

- **`.github/workflows/validate.yml`** — on every push/PR: copies `.env.example` to `.env`,
  validates `docker compose config` for both the default and `extras` profiles, a var-diff check
  (every `${VAR}` in `docker-compose.yml` must have a matching key in `.env.example`), `shellcheck`
  over every `.sh` file, `ruff` over `control-panel/app.py` + `scripts/*.py`, and builds the
  installer image (no push).
- **`.github/dependabot.yml`** — weekly checks across the `docker-compose`, `docker`, `pip`, and
  `github-actions` ecosystems. Every image is pinned (see [Image pinning policy](#image-pinning-policy)),
  so this has something real to bump everywhere except the digest-pinned images (Dependabot can't
  propose "this digest should be newer," only track a tag it's already watching).
- **`.github/workflows/publish-installer.yml`** — rebuilds and republishes the installer image to
  GHCR on every push to `main` that touches a bundled file, tagged `:latest` and `:vX.Y.Z` (parsed
  from this document's own version references), for both `linux/amd64` and `linux/arm64`.
- **`.github/workflows/claude.yml`** / **`claude-code-review.yml`** — `@claude`-triggered PR
  assistance and automatic code review on every PR (skips Dependabot-authored PRs cleanly, since
  GitHub withholds repo secrets from `pull_request`-triggered runs when the actor is
  `dependabot[bot]` — the documented manual workaround is commenting `@claude` on the PR, which
  triggers the other, unaffected workflow instead).

## Installer image and setup wizard

`Dockerfile` + `entrypoint.sh` bundle this repo's own tracked, portable files
(`docker-compose.yml`, `.env.example`, `scripts/`, `systemd/`, this README) into a small image that
extracts (or updates) them onto a host in one command, instead of a git clone:

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

**Never contains** `.env`, `config/`, `media/`, or `usenet/` — excluded at the `.dockerignore`
level (a build-context exclusion, not just a documented convention), so no COPY instruction could
reach them even by mistake:

```
.git
config/
media/
usenet/
.env
*.log
```

**The setup wizard** (`scripts/setup_wizard.py`, stdlib-only Python) parses `.env.example`'s own
`# ---- Section ----` headers and comment lines into a browser form, so the form and the template
file can never drift apart — add a new `KEY=default` line with a comment above it and it shows up
in the wizard with zero code changes anywhere else.

```python
FIELD_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
SECTION_RE = re.compile(r"^# ---- (.+?) ----$")
POST_BOOT_KEYS = {
    "RADARR_API_KEY", "SONARR_API_KEY", "LIDARR_API_KEY", "READARR_API_KEY",
    "WHISPARR_API_KEY", "PLEX_TOKEN",
}
AUTO_GENERATE_KEYS = {"ZILEAN_POSTGRES_PASSWORD", "ZILEAN_API_KEY"}
```

Six fields genuinely can't be collected before first boot — each `*arr` app generates its own API
key on first start, and `PLEX_TOKEN` needs a running Plex with at least one library item. These
render in a highlighted "⚠ Fill in after first boot" section and default to `changeme`; re-running
`--setup` loads the real `.env` as defaults, so a second pass only means retyping what's actually
new.

## Known gaps and limitations

Documented honestly rather than swept under the rug:

- **Sonarr's `missing-aired` endpoint has an unresolved pagination performance risk on large
  libraries.** The early-stop-on-first-future-episode optimization helps, but this Sonarr instance
  tracks close to 300,000 episode records, and the endpoint's real-world latency against that full
  scale hasn't been load-tested. It also has zero frontend wiring in Control Panel's UI — curl/API
  access only. See [The *arr apps](#the-arr-apps).
- **Lidarr's indexer + download-client chain is verified working end-to-end**, not just configured:
  a live test (add artist → `MissingAlbumSearch` → grab → NzbDAV → import) completed in well under
  a minute with zero manual intervention. Lidarr has 15 synced Prowlarr indexers, Readarr has 9,
  Whisparr has 21 — the earlier assumption that these apps had 0 indexers was wrong.
- **Whisparr's search chain runs correctly but finds nothing for most titles** — confirmed via two
  live tests (`Test Subjects` and the much more mainstream `Brazzers House`), both completing with
  "0 reports downloaded" across all 21 synced indexers. Root cause identified: Prowlarr's own raw
  search (`/api/v1/search?categories=6000`) *does* return hundreds of hits from an indexer called
  `0Magnet`, but that indexer's Torznab capability declaration has `movieSearchParams: []` — it only
  implements generic keyword search, not the movie-search contract Whisparr's sync requires — so
  Prowlarr correctly excludes it from Whisparr's indexer list. This is a structural limitation of
  the available public XXX-category Torznab indexer definitions, not a wiring defect; a real fix
  would mean sourcing indexers with proper movie-search support. See
  [Indexing](#indexing-prowlarr-zilean-byparr).
- **Readarr's author/book metadata lookup is currently blocked by an external outage**, not a
  wiring issue: its Goodreads-replacement provider's API host, `api.bookinfo.club`, has no DNS
  record at all right now — confirmed with `dig` against both the container's resolver and Google's
  public DNS (`8.8.8.8`) directly from the host, both return nothing, while the bare
  `bookinfo.club` domain resolves fine. Readarr can't identify any author without this lookup
  succeeding, so no live grab test could be completed. Root folder, quality/metadata profiles, and
  both download clients (Decypharr, NzbDAV) are all confirmed correctly configured independent of
  this — only the metadata step is affected, and only because the upstream service is down.
- **Zurg/Real-Debrid can hit transient rate-limiting under heavy simultaneous use** — a burst of
  grabs, manual-import scans, and concurrent Plex streams all resolving through the same mount at
  once can transiently slow down against Real-Debrid's own API limits. Self-recovers via
  Decypharr's own retry logic; not something to "fix" so much as a real characteristic of a shared
  upstream API. See [The debrid pipeline](#the-debrid-pipeline-zurg--decypharr).
- **`media/youtube` is an inert leftover** from a Pinchflat integration removed entirely in an
  earlier version — the directory still exists on disk but nothing in `docker-compose.yml` or
  Plex writes to or reads from it anymore.
- **`rclone-alldebrid` doesn't reliably survive a plain `docker restart`** — its `/mnt/all` FUSE
  mount can come back `Transport endpoint is not connected` and the container's own restart-policy
  retries never clear it on their own. Recovery needs a lazy unmount from outside the container's
  mount namespace (`docker run --rm --privileged -v /mnt:/mnt:rshared alpine umount -l /mnt/all`)
  followed by a fresh restart. Same failure class as Radarr's mount fragility, no known one-line
  fix yet.
- **A still-unexplained mass Radarr/Sonarr library-loss event** occurred once early in this
  project's life (1,605 movies deleted in a single 0.1-second burst with no matching API call
  logged; ~90 Sonarr series briefly added then removed with no deletion log line at all). Root
  cause was never identified. As a blast-radius mitigation (not a fix), both apps' native Recycle
  Bin is now enabled (`/data/movies/.recyclebin`, `/data/shows/.recyclebin`, 7-day cleanup), so a
  repeat lands recoverable content in a real folder instead of disappearing outright.

## History

The condensed, chronological version — full detail for any of these lived in `CHANGELOG.md`
before it was merged into this document; each numbered version below corresponds to real work,
not a rounded-up estimate.

**v1.x — initial build.** The whole stack stood up from nothing: Prowlarr, Zilean, Decypharr,
Radarr, Sonarr, Lidarr, Readarr, Whisparr, NZBGet, Seerr, plus Homepage, Recyclarr/TRaSH-Guides,
and a passwordless-sudo/CI baseline.

**v2.x — the debrid-mount lesson, twice.** Decypharr's staged downloads were invisible to every
`*arr` app until their containers shared its download path (v2.1.0); a deeper bug then surfaced —
root folders were still pointed at Zurg's *read-only* FUSE mount, which can never accept a written
symlink, so **no import had ever actually completed** regardless of the path fix (v2.2.0). Root
folders moved to regular disk (`./media/<type>`) permanently from here on. Jellyfin + companion
apps (Jellyseerr, Jellystat, jfa-go) were added, wired up, and fully removed again a few versions
later once `.strm`-mode Decypharr (Plex doesn't support `.strm` at all) and a serious Decypharr
config-wipe bug (any partial `PATCH` to its config API silently dropped the `debrids`/`mount`
sections — filed upstream as
[sirrobot01/decypharr#343](https://github.com/sirrobot01/decypharr/issues/343)) made the
experiment not worth keeping. Homepage was later replaced by Heimdall, then both were eventually
replaced entirely by Control Panel's own Quick Links.

**v3.x — Plex and Zurg containerized.** Zurg/rclone-AllDebrid moved from native systemd units into
Docker (v3.2.0), Plex followed via a byte-identical migration from a native Arch install (v3.3.0,
3,826 movies / 774 shows verified against pre-migration counts). Recyclarr and its 40+ TRaSH-Guides
custom formats per app were removed entirely in favor of one hand-maintained blocklist format
(v3.0.0). FlareSolverr was replaced by Byparr (v3.4.0). A first reverse-proxy/Basic-Auth attempt
(Caddy, v2.11.0) was added and then removed (v3.1.0) — the first of two times this stack tried and
reverted an auth layer.

**v4.x — Whisparr's first removal; Control Panel is born.** Whisparr was removed entirely after a
real bug in the running build (`DownloadedEpisodesScan` throwing on missing `path`) plus a
root-folder regression (v4.0.0) — the same regression class hit Radarr independently a version
later, traced to Radarr uniquely bind-mounting `/mnt/zurg` directly rather than the parent `/mnt`
(v4.0.1, still true today, see [Architecture](#architecture)). Control Panel was built from
scratch (v4.1.0) with one-click ops actions, then grew a full container grid, host stats, Zilean
search-and-grab, whole-stack restart, and Unstick/manual-import for stuck queue items over the
rest of this line. Native Plex and its pre-migration backups were removed for good (v4.8.0) once
the containerized instance was trusted. The setup wizard shipped (v4.9.0), turning `.env`
hand-editing into a browser form.

**v5.x-v6.x — Homepage/Heimdall retired; DebridMediaManager self-hosted; a real rebuild-from-zero
after a discovered drift.** Control Panel absorbed Quick Links and a Matrix visual theme, letting
both older dashboards be removed for good (v5.0.0). A routine check found that several
already-documented features simply weren't live — Prowlarr had 0 indexers, both `*arr` apps had 0
custom formats, log rotation and the restic backup pipeline had never actually run — and
everything in that gap was rebuilt from zero and reverified rather than assumed working (the
`2026-07-09` note this correlates with the still-open mass-deletion incident in
[Known gaps and limitations](#known-gaps-and-limitations), without proving the connection).
DebridMediaManager was self-hosted in full (v6.2.0-v6.3.0, including a from-scratch local IMDB
title index since its own search doesn't call TMDB/MDBList live). Bazarr's language/provider setup
was completed (v6.7.0) — later fully removed in this session, see below.

**v7.x-v8.x — Lidarr, Readarr, and Pinchflat removed; native Plex hooks added.** Lidarr and Readarr
were removed as a user call, not a bug (v7.0.0) — "decided they weren't worth the ongoing hassle
relative to how little they were actually used." Radarr/Sonarr gained native Plex Media Server
notification hooks (`onDownload`/`onUpgrade`) and their own daily native-backup script in the same
version. Cleanuparr, NeutArr, and Dozzle were added (v7.1.0), along with a YouTube-archiving app
(Pinchflat) that was removed again a version later once the storage setup it needed wasn't
actually available (v8.0.0) — the same "good app, just not doable right now" pattern Whisparr's
first removal followed.

**v9.x-v10.x — a full auth layer, tried and reverted; NzbDAV replaces NZBGet.** A complete
Traefik + Authelia + CrowdSec stack was built and verified working end-to-end — real TOTP 2FA,
a real CrowdSec-banned IP getting a real 403 (v9.0.0) — then fully reverted a version later once
the day-to-day friction (a login+2FA prompt in front of every app, three extra services to keep
healthy, a firewall hairpin-NAT bug that took Plex down through the proxy) wasn't judged worth it
for a stack that's genuinely never reachable from outside the LAN/tailnet (v10.0.0). One piece
was deliberately kept: Control Panel's CSRF/Origin-Host check, which closes a different gap
unrelated to whether a proxy sits in front of anything. NZBGet — a real local downloader — was
wired up with a real provider, found not to match the actual "no disk storage" goal, and replaced
within the same session by NzbDAV's WebDAV-streaming approach (v10.1.0).

**v10.2.0 — Bazarr removed; Lidarr, Readarr, and Whisparr reinstated; Calibre-Web
added.** The most recent batch of changes, not yet given its own dated CHANGELOG entry before this
document absorbed the changelog format entirely:

- **Bazarr removed entirely** — container, `config/bazarr/`, every Control Panel reference
  (`BAZARR_API_KEY`, the search-wanted endpoint and primary-action card, `CONTAINER_LABELS`
  entry), its `.env`/`.env.example` entries, the matching `stack-bazarr-search` fish function, and
  the stale doc-comment references to it in `control-panel/app.py` and `docker-compose.yml`.
- **Lidarr, Readarr, and Whisparr reinstated** — each wired identically to Prowlarr indexer sync,
  both Decypharr instances, NzbDAV, Zurg's content-routing groups, Unpackerr, and Control Panel's
  queue tools (RSS sync, search-missing, unstick, manual-import all now work on all five `*arr`
  apps). Readarr is pinned to the last pullable `linuxserver/readarr` tag since upstream Readarr
  is officially retired; Whisparr is pinned to hotio's `:v3` ("eros") channel, the
  Sonarr-codebase-based series-style build, not the movie-style v2 that `:latest` resolves to.
- **Calibre-Web added** (`lscr.io/linuxserver/calibre-web:latest`, the `universal-calibre`
  DOCKER_MOD) — an actual ebook reader for Readarr's output, since Plex has no ebook agent at all.
  Its default `admin`/`admin123` password was rotated; the new value lives in `.env` under
  `CALIBRE_WEB_ADMIN_PASSWORD`.
- **Zurg's `music`/`books` content-routing groups restored** in `config/zurg/config.yml`, both
  sorted with a lower `group_order` than the movies catch-all.
- **Decypharr's `categories`/`allowed_file_types`** extended to cover all five apps' download
  categories and file types (audio, ebook formats alongside the existing video/subtitle list).
- **A Plex "Audiobooks" library** (Music-type, "Plex Personal Media" agent, i.e.
  `com.plexapp.agents.none`) was added pointed at `/home/bear/Stack/media/audiobooks`, and a new
  movie-type "Adult" library was added pointed at `/mnt/zurg/adult` for Whisparr's output. The
  existing Music library already had both `/mnt/zurg/music` and `/home/bear/Stack/media/music`
  configured from an earlier version.
- **`stack-arr`, `stack-arr-import-candidates`, and `stack-arr-import`** now accept
  `lidarr`/`readarr`/`whisparr` alongside `radarr`/`sonarr`; the setup wizard's `POST_BOOT_KEYS`
  now covers all five apps' API keys, matching Control Panel's API surface which already supported
  them.
- A **Whisparr "Unlimited" quality profile** was added, mirroring Radarr/Sonarr's own
  (720p-and-up allowed, cutoff at Remux-2160p, upgrades enabled) — Whisparr previously only had its
  stock `Any`/`SD`/`HD-*` profiles, none matching the other two apps' actual policy.

**v10.3.0 — Maintainerr added; native Discord notifications on all five `*arr` apps.**
Evaluated [RandomNinjaAtk/arr-scripts](https://github.com/RandomNinjaAtk/arr-scripts) for anything
worth adopting (see [Maintainerr](#maintainerr-plex-library-lifecycle) for why almost none of it
fit) and built the two things that did:

- **Maintainerr** (`ghcr.io/maintainerr/maintainerr:latest`, port 6246) — Plex library lifecycle
  management, wired to Plex/Radarr/Sonarr/Seerr/Tautulli via its own settings API. Two
  highest-karma community rules (Seerr-requester-watched-30d-or-unwatched-90d, one per Movies/TV)
  were imported but left `isActive: false` deliberately — its rule engine really does delete
  matching media on a real cron schedule, so nothing runs until a human reviews and enables it.
- **Native Discord notification connections** added to Radarr/Sonarr/Lidarr/Readarr/Whisparr,
  reusing the existing `DISCORD_WEBHOOK_URL` — grab/import/upgrade/health-issue/app-update events,
  verified live via each app's own `/notification/test`. Shares one channel with the
  Watchtower/backup/health alerts from [Alerting](#alerting-discord); a known tradeoff, not a bug.

**v10.4.0 — Anime Movies/Shows added; a real Zurg mount outage found and fixed.**

- **Two new Zurg content-routing groups** (`anime-shows`, `anime-movies`) and matching Plex
  libraries — see [Zurg's content-routing groups](#zurgs-content-routing-groups) and
  [Plex "Anime Movies" and "Anime Shows" libraries](#plex-anime-movies-and-anime-shows-libraries)
  for the fansub-tag regex, the ordering rationale, and the first live scan's results (10 shows
  matched, zero false positives, only 2 auto-resolved Plex metadata).
- **Found and fixed a real incident while doing that work**: restarting Zurg to pick up the new
  groups left `/mnt/zurg` completely empty — not just the two new anime folders, *every* existing
  directory (`movies`, `shows`, `music`, `books`, `adult`). Root cause: Zurg's `/mnt/zurg` mount is
  a supervised rclone subprocess gated by `mount_path`/`rclone_enabled` config keys that were never
  actually written to `config.yml` — apparently only ever toggled live through Zurg's own
  dashboard, an in-memory setting that a plain `docker restart` silently discards with zero error
  surfaced anywhere. Fixed by adding both keys to `config.yml` directly, so it can't regress to
  "in-memory only" again. See
  [Zurg's mount is a supervised rclone subprocess](#zurgs-mount-is-a-supervised-rclone-subprocess-not-built-into-the-binary-directly).
- **Sonarr's `/data/anime` migration for all 1,505 existing `Anime`-genre series started** via
  `PUT /api/v3/series/editor`, but the async `BulkMoveSeries` command got stuck queued behind a
  long-running `ProcessMonitoredDownloads` job for the rest of that session — see v10.5.0 below
  for how it actually resolved.

**v10.5.0 — Sonarr anime migration completed; Plex "Adult" library path bug found and
fixed; Recyclarr added; arr command-queue backlog visibility.**

- **The v10.4.0 migration stall cleared on its own.** The stuck `ProcessMonitoredDownloads`
  command (id 13592) completed after 1h15m total (no restart needed); the queued
  `BulkMoveSeries` command (13591, the 5-series test batch) then ran in under a second once
  unblocked. Verified clean: all 5 test series had real files physically present at
  `/data/anime/...`, zero orphaned folders left in `/data/shows`. The remaining 1,500 series
  were then submitted in one more `PUT /api/v3/series/editor` call (command 14095), which
  completed in 8 seconds once its own queue position cleared. **Verified complete**: all 1,505
  `Anime`-genre series now have `path` under `/data/anime`, zero remaining under `/data/shows`,
  spot-checked several with real episode files physically present on disk.
- **Found and fixed a real, previously-undiscovered bug in the Plex "Adult" library.** Added in
  v10.2.0 pointed at `/mnt/zurg/adult` only (empty — 0 entries) — Whisparr's actual, only root
  folder is the local writable mount `./media/adult` → `/data/adult`, which already had real,
  organized content (3 studio folders under `movies/`, 51 under `scenes/`). That path was never
  added as a second library Location, so every file Whisparr had grabbed and imported was
  invisible in Plex — not a scan failure, a missing `Location` entirely. Every other content
  type (Movies, TV Shows, Anime Shows, Music) already had both the Zurg path and the local
  writable path wired in; Adult was the one outlier. Fixed via a direct Plex API `PUT` adding
  the second location (Plex's library-edit endpoint 400s if `type`/`agent`/`scanner`/`language`
  aren't resent alongside `location` — a bare location-only `PUT` is treated as an invalid full
  section redefinition, not a patch), then triggered a rescan.
- **Recyclarr reinstated** (`profiles: [extras]`), deliberately not via its stock
  resolution-tiered templates — those create a competing quality profile and hard-block SDR by
  default, which would fight this stack's actual "Unlimited" policy (no resolution/dynamic-range
  restriction) on the first sync. `config/recyclarr/recyclarr.yml` targets "Unlimited" directly
  and only syncs five resolution-agnostic hygiene custom formats (Scene, Obfuscated, Retags,
  No-RlsGroup, Bad Dual Groups) at TRaSH's own default scores. `reset_unmatched_scores` is left
  off on purpose — it would zero out the two pre-existing hand-made hard blocks (`-10000` each,
  sample/low-quality releases and raw Blu-ray discs) that Recyclarr doesn't manage. Validated
  with `recyclarr sync --preview` before the real sync ran; confirmed live afterward that both
  manual formats were untouched and the five new ones landed at matching severity. No Whisparr
  support — TRaSH Guides doesn't publish custom-format guides for it.
- **Control Panel: `GET /api/arr/{app}/command-backlog`** (plus a matching `stack-arr-backlog
  <app>` fish function) — surfaces an arr app's internal `/command` queue (status counts,
  what's currently running, oldest still-queued items). Built directly off the stall above: an
  arr app's command backlog silently growing for over an hour behind one stuck job had zero
  visibility anywhere in Control Panel's existing tooling, which only looks at the download
  queue, not the internal command queue bulk moves/RSS sync/searches all share.
- **Synced to the public `Stackalicious` repo**, sanitized (real host IP and the real host
  username in one Plex bind-mount path both genericized) and covering v10.1.0 through this
  version — see that repo's own `CHANGELOG.md`.

**v10.6.0 — Live queue speed/ETA and wanted/missing backlog throughput ETA.**

- **Control Panel: `GET /api/queue-status`** (plus `stack-queue-status`) — every download queue
  (Radarr/Sonarr/Lidarr/Readarr/Whisparr + NzbDAV) bucketed into downloading/stalled/queued/
  importing, with a real speed and ETA for anything actually observed to be draining. Doesn't
  trust each app's own `timeleft`/`estimatedCompletionTime` - confirmed live those are stale
  `00:00:00` placeholders for nearly everything in this stack: Decypharr's debrid-cached/
  symlinked downloads jump straight from full size to zero with no gradual byte-by-byte transfer
  to time (there's no real download happening at that layer to measure), and NzbDAV's
  SABnzbd-emulation layer doesn't compute a speed field even though its `mb`/`mbleft` are real.
  Takes two live size-remaining samples ~4s apart and derives real observed speed from the delta
  instead - honest about "no progress observed" (still caching server-side, or genuinely
  stalled) rather than fabricating an ETA the data can't support.
- **Control Panel: `GET /api/backlog-status`** (plus `stack-backlog-status`) — every arr app's
  wanted/missing count with a throughput-projected ETA, a fundamentally different estimate from
  the queue one above: nothing here is mid-transfer, so there's no size to drain. Rate is
  measured from the last 50 import-completion events in each app's own `/history`, capped to a
  6-hour lookback so a backlog that was moving fast an hour ago but has since stalled (indexer
  rate-limit, etc.) doesn't get credited with a pace it isn't currently keeping. Confirmed live
  that Lidarr names its per-file-import event `trackFileImported`, not `downloadFolderImported`
  like the Radarr-lineage apps (Radarr/Sonarr/Whisparr) - Readarr's was unverifiable (zero
  history at the time, unused), so it checks both candidate names instead of guessing wrong and
  silently reporting zero forever.

**v10.6.1 — Plex's own activities added to `queue-status`.**

- **`GET /api/queue-status` now includes Plex** as a 7th queue, covering its own `/activities`
  (library scans, deep media analysis, thumbnail generation, etc.) alongside the five arr apps
  and NzbDAV. Piggybacks on the same before/sleep/after sample window the rest of the endpoint
  already takes, so this adds no extra latency. Plex has no byte size to drain, so `progress`
  (0-100) is the measured signal instead - real speed/ETA when it's climbing between samples,
  "stalled" when it isn't (large library section, or genuinely stuck) rather than assuming a
  scan sitting at one percentage is broken.

**v10.6.2 (current) — NeutArr wired to all five `*arr` apps.**

- **NeutArr was only hunting for Sonarr and Radarr** despite `config/neutarr/{lidarr,readarr,
  eros}.json` already existing on disk with the correct schema, scaffolded but never
  populated (`api_url`/`api_key` both empty, so `settings_manager` never counted them as
  configured — confirmed live via `Configured apps: ['sonarr', 'radarr']` repeating in its own
  logs). Filled in all three directly (same host bind mount NeutArr's own "Apps" settings page
  writes to), matching Radarr's already-working instance shape exactly. Whisparr is configured
  under NeutArr's "Whisparr V3" app type (`eros.json`) — NeutArr also has a "Whisparr V2" slot
  (`whisparr.json`, left untouched/disabled), and picking the wrong one would silently hunt
  against an API shape this stack's Whisparr (`:v3` "eros" pin) doesn't speak. `docker restart
  neutarr` picked up all three immediately — confirmed live via its own logs
  (`Configured apps: [..., 'lidarr', 'readarr', 'eros']`) and a real triggered search against
  Whisparr in the very next hunt cycle.

---

🤖 **This stack — architecture, every service, every fix, every line of this document — was built
by [Claude AI](https://www.anthropic.com/claude).**
