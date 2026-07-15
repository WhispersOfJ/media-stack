# The Stack

Current version: **v10.10.0**

**A Docker Compose media-acquisition-and-serving stack** — indexes, requests, and symlinks
already-cached content from Real-Debrid / AllDebrid, falls back to Usenet (streamed, not
downloaded) when nothing's cached, and serves the result through a containerized Plex. 34
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
- [Bindery and Calibre-Web: retired](#bindery-and-calibre-web-retired)
- [Stash: adult library cataloging](#stash-adult-library-cataloging)
- [Custom formats and quality profiles](#custom-formats-and-quality-profiles)
- [DebridMediaManager (self-hosted)](#debridmediamanager-self-hosted)
- [Automation extras: Kometa, Cleanuparr, NeutArr, Unpackerr, Watchtower](#automation-extras-kometa-cleanuparr-neutarr-unpackerr-watchtower)
- [Monitoring extras: Tautulli](#monitoring-extras-tautulli)
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
(Prowlarr + Zilean's DMM cache-hash index), a request front-end (Seerr), three `*arr` apps that
turn a request into an organized library (Radarr, Sonarr, Whisparr — Lidarr was removed entirely
in v10.9.9, see [History](#history)), a debrid gateway
that symlinks already-cached content instead of downloading it (Decypharr + Zurg), a Usenet
fallback that streams rather than downloads (NzbDAV), a containerized Plex to watch/listen to
the result on, a self-hosted DebridMediaManager, and a pile of automation/monitoring extras
(Kometa, Cleanuparr, NeutArr, Unpackerr, Watchtower, Tautulli) — 30
containers total, one `docker-compose.yml`. (Ebooks briefly had a dedicated app, Bindery, plus
Calibre-Web as its reader; both were retired in v10.9.8 — see
[Bindery and Calibre-Web: retired](#bindery-and-calibre-web-retired) — with no replacement
currently in the stack.)

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
#    Watchtower, Cleanuparr, NeutArr, Control Panel, DMM)
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
Radarr/Sonarr/Whisparr ──grab──> Decypharr (qBittorrent-compatible API)
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

**Two Decypharr instances, not one.** `docker-compose.yml` runs `decypharr` (port 8282, both
debrid backends, Radarr's + Whisparr's download client) and
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
> directly (`/mnt/zurg:/mnt/zurg:rslave`) rather than the parent `/mnt` the way Sonarr/
> Whisparr/Plex do. A direct bind of a FUSE mountpoint doesn't reliably survive that FUSE
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
| 11 | `whisparr` | `ghcr.io/hotio/whisparr:v3` | 6969 | core |
| 12 | `nzbdav` | `nzbdav/nzbdav:latest` | 3001→3000 | core |
| 13 | `nzbdav-rclone` | `rclone/rclone:1.74.4` | — | core |
| 14 | `seerr` | `ghcr.io/seerr-team/seerr@sha256:c92d2d...` | 5055 | core |
| 15 | `plex` | `plexinc/pms-docker:1.43.2.10687-563d026ea` | 32400 (host net) | core |
| 16 | `stash` | `stashapp/stash:v0.31.1` | 9998→9999 | extras |
| 17 | `byparr` | `ghcr.io/thephaseless/byparr@sha256:01a46a...` | 8191 | extras |
| 18 | `tautulli` | `ghcr.io/hotio/tautulli:release` | 8182 | extras |
| 19 | `control-panel` | built from `./control-panel` | 8420 | extras |
| 20 | `kometa` | `kometateam/kometa@sha256:98a0df...` | — | extras |
| 21 | `unpackerr` | `golift/unpackerr@sha256:4ec141...` | — | extras |
| 22 | `watchtower` | `nickfedor/watchtower:1.19.0` | — | extras |
| 23 | `recyclarr` | `ghcr.io/recyclarr/recyclarr:latest` | — | extras |
| 24 | `dmm-mysql` | `mysql:9.7` | — | extras |
| 25 | `dmm-redis` | `redis:8-alpine` | — | extras |
| 26 | `dmm-migrate` | built from DMM git context, `target: build` | — | extras (one-shot) |
| 27 | `debridmediamanager` | built from DMM git context, `target: build` | 3000 | extras |
| 28 | `cleanuparr` | `ghcr.io/cleanuparr/cleanuparr:2.9.16` | 11011 | extras |
| 29 | `neutarr` | `iampuid0/neutarr:1.9.1` | 9705 | extras |
| 30 | `maintainerr` | `ghcr.io/maintainerr/maintainerr:latest` | 6246 | extras |

`docker compose up -d` brings up the 15 core services; `docker compose --profile extras up -d`
adds the other 15. Both commands are safe to run repeatedly — Compose only recreates what's
actually out of sync with `docker-compose.yml`. (`bindery`/`calibre-web` were retired in v10.9.8
and no longer appear here; `glances`/`dozzle` removed entirely in v10.9.9, no data preserved;
`recyclarr` was previously missing from this table despite being a live service since well
before this session — fixed 2026-07-14.)

## The *arr apps

All three follow an identical wiring pattern: Prowlarr pushes indexers down via
`fullSync`, Decypharr (or `decypharr-alldebrid` for Sonarr) is the priority-1 download client,
NzbDAV is priority-2 fallback, Unpackerr extracts anything RAR'd, root folder is `./media/<type>`
mounted at `/data/<type>`, and Control Panel wires up RSS sync / search-missing / unstick /
manual-import against each one identically.

| App | Port | Root folder | Content type |
|---|---|---|---|
| Radarr | 7878 | `/data/movies` | Movies |
| Sonarr | 8989 | `/data/shows` | TV |
| Whisparr | 6969 | `/data/adult` | Adult (v3/"eros", series-style) |

Radarr/Sonarr/Whisparr were reinstated (Whisparr in a later session) after having been fully
removed at various earlier points — see [History](#history) for why each was pulled and why each
came back. **Lidarr was reinstated alongside Whisparr in v10.2.0, then removed entirely again in
v10.9.9** — see [History](#history) for that later removal; the `*arr` app family in this stack
is Radarr/Sonarr/Whisparr only as of that version. Every one of these apps' queue works
identically for Control Panel's [Unstick and manual-import](#control-panel) actions.

### Readarr is gone

Upstream Readarr was **officially retired** — "lack of developers... decided to retire the
project," per linuxserver.io's own deprecation notice — and the final straw was its Goodreads
metadata lookup dying permanently when `bookinfo.club` (the scrape target linuxserver's fork
depended on) expired outright. hotio never published a Readarr image at all, and linuxserver's own
`develop`/`nightly` tags stopped resolving to a valid manifest. It was replaced in v10.7.0 by
**Bindery**, a Go-based ebook `*arr` — which itself never tracked a single book and was retired
outright in v10.9.8 along with its reader, Calibre-Web. There is currently no ebook app of any
kind in this stack. Full detail on Bindery's deployment, its real gotchas, and why it was removed
is in [Bindery and Calibre-Web: retired](#bindery-and-calibre-web-retired) and the v10.7.0/v10.9.7/
v10.9.8 [History](#history) entries.

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
used for Radarr/Sonarr's own `:release` tags (also rolling, not commit-pinned). Whisparr was
previously removed once (see [History](#history)) over a real bug in the specific build then
running (`DownloadedEpisodesScan` throwing on missing `path`) plus a root-folder regression — the
same regression class Radarr/Sonarr have both hit; watch for it here too.

### Real API examples

Every Servarr-shaped app in this stack exposes the same `/api/v3` REST API shape
(Radarr/Sonarr/Whisparr):

```bash
# Radarr's own health/liveness endpoint (what every healthcheck in this stack uses)
curl -sf http://192.168.4.105:7878/ping

# List Radarr's configured root folders
curl -s -H "X-Api-Key: $RADARR_API_KEY" http://192.168.4.105:7878/api/v3/rootfolder | jq .

# Trigger an immediate RSS sync on Sonarr
curl -X POST -H "X-Api-Key: $SONARR_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"RssSync"}' http://192.168.4.105:8989/api/v3/command

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
  "categories": ["sonarr", "radarr", "whisparr"],
  "refresh_interval": "30s",
  "max_downloads": 10
}
```

`allowed_file_types` in that same file was extended when Lidarr/Readarr/Whisparr were reinstated
to cover audio (`flac`, `mp3`, `m4a`, `ape`, ...) and remains inclusive of video/subtitle types
alongside the original movie/TV list — one shared allow-list across every category, not scoped
per-app. Audio extensions are now a harmless leftover the same way the ebook extensions below
are, since Lidarr's own removal in v10.9.9 (see [History](#history)). Ebook extensions (`epub`,
`mobi`, `azw`, `azw3`, `cbr`, `cbz`, `pdf`, ...) were added for Bindery and never removed after
its retirement in v10.9.8 — harmless leftovers now that nothing reads that category.

**Restricting a specific app to a specific debrid provider** is a per-arr field, distinct from the
overall `debrids[]` list:

```bash
# Radarr is pinned to Real-Debrid only (added to its arrs[] entry in
# config/decypharr/config.json) - Sonarr/Whisparr are left on
# source: "auto" with no selected_debrid, so they can still fall through to
# AllDebrid.
# config/decypharr/config.json is gitignored (real API keys), so
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
  # Restored (originally for Readarr, later Bindery) - both are gone now
  # (see Bindery and Calibre-Web: retired) and nothing currently reads
  # /mnt/zurg/books, but the group is left in place as a harmless leftover
  # rather than pulled, in case an ebook app returns to this stack.
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
(see [History](#history)), and were restored to feed the reinstated apps. **`music` is once again
an orphaned group as of v10.9.9** — Lidarr, its only consumer, was removed entirely (see
[History](#history)) — left in place as a harmless leftover the same way `books` was after
Bindery's retirement, rather than pulled, in case a music `*arr` returns to this stack.
`anime-shows`/
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
pushes them down to all three `*arr` apps via `Settings → Apps` `fullSync`. Zilean is registered as
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

### Books/XXX indexer coverage — verified live, not assumed

An earlier version of this document claimed Prowlarr had 0 indexers scoped to Lidarr/Readarr/
Whisparr's categories. That was checked directly against the live Prowlarr Applications API
(`GET /api/v1/applications`, which lists each `*arr` app's `syncCategories`) and found to be
wrong: Prowlarr synced **15 indexers to Lidarr** (category 3000-range) and syncs **21 to
Whisparr** (6000-range). A live end-to-end test confirmed Lidarr's chain actually worked, back
when Lidarr was still part of this stack — a real Prowlarr → Lidarr → grab → NzbDAV → import pass
completed in well under a minute with zero manual intervention.

Both music and books indexer coverage are moot now. **Lidarr was removed entirely in v10.9.9**
(see [History](#history)) — Prowlarr's Lidarr application-sync entry was deleted via its own API
along with it, so there's no music indexing path in this stack currently. Bindery (the ebook
`*arr` that used to pull indexers from Prowlarr via its own non-Servarr-shaped API) was retired in
v10.9.8 along with its reader, Calibre-Web — see
[Bindery and Calibre-Web: retired](#bindery-and-calibre-web-retired). There is no ebook indexing
path in this stack currently either.

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
Whisparr (nor was it ever connected to Lidarr, before its removal in v10.9.9) — Seerr's own
settings API only recognizes `radarr` and `sonarr`; there's no adult-content data model to
connect Whisparr to, confirmed directly against its settings schema, not an oversight.

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

### Plex "Audiobooks" library, and the retired "Adult" library

**Audiobooks** (library key 8) is a **Music-type** library using the **"Plex Personal Media"
agent** (`tv.plex.agents.none`, the modern identifier for the legacy `com.plexapp.agents.none`)
rather than a real music-metadata agent — this is the standard workaround for audiobooks in Plex,
since Plex has no dedicated audiobook library type or agent. It's pointed at
`/home/bear/Stack/media/audiobooks` — that directory exists on disk but is currently empty, since
nothing populates it automatically (no `*arr` app manages audiobooks specifically).

```bash
curl -s -H "X-Plex-Token: $PLEX_TOKEN" http://192.168.4.105:32400/library/sections | \
  grep -E 'title="Audiobooks"'
```

**Plex's "Adult" library was removed entirely in v10.9.9**, via the Plex API (`DELETE
/library/sections/{key}`) — not just emptied. It was originally a plain **Movie-type** library
pointed at `/mnt/zurg/adult` and (after a real bug fixed in v10.5.0) also
`/home/bear/Stack/media/adult`. Stash now fully covers this content type's cataloging
(performers/studios/tags/StashDB identification — see [Stash](#stash-adult-library-cataloging)),
so a second, metadata-poor Plex library browsing the exact same files stopped earning its keep.
**Files under `./media/adult` were not touched** — only the Plex library entry was dropped.
Whisparr still manages the underlying files and root folder exactly as before; Stash is now the
sole means of browsing/cataloging this content, Plex no longer has any view into it at all.

## Bindery and Calibre-Web: retired

**Both retired in v10.9.8; the stack currently has no ebook or comic app of any kind.**

Bindery (`ghcr.io/vavallee/bindery`) replaced Readarr in v10.7.0 as the ebook `*arr`, with
Calibre-Web reading its root folder (`./media/books`) directly as the actual reader/library UI.
Bindery tracked **zero authors/books the entire time it ran** (see [v10.7.0](#history)) — its
Decypharr download-client wiring was fixed live in v10.9.7, but no real content ever came in
through it before both services were removed. With nothing in the library and no working
acquisition path proven out, keeping an empty ebook manager and its reader running wasn't worth
the resource/maintenance cost, so both `docker-compose.yml` service blocks were deleted outright
rather than left idling.

`config/calibre-web/` is left on disk (not deleted) in case anything ever needs recovering from
it; `config/bindery/` likewise. `CALIBRE_WEB_ADMIN_USERNAME`/`_PASSWORD` were removed from
`.env`/`.env.example` since nothing reads them anymore. `control-panel/app.py`'s
`CONTAINER_LABELS` and `ARR_LOG_CONTAINERS` no longer list either service.

No ebook agent exists for Plex either way (confirmed live via `/system/agents`, no book/ebook
identifier present) — if ebooks come back to this stack, it'll need both a manager and a
dedicated reader again, same as before.

## Stash: adult library cataloging

**[Stash](https://github.com/stashapp/stash)** (`stashapp/stash:v0.31.1`) catalogs `./media/adult`
(Whisparr's own root folder) with real performer/studio/tag metadata and scene identification —
Plex's own "Adult" library was removed entirely in v10.9.9 (see [Plex](#plex)) once Stash's
coverage made a second, metadata-poor library redundant, so as of that version **Stash is the
sole means of browsing/cataloging this content**, not an enrichment layer alongside Plex the way
it started out as:

```yaml
# docker-compose.yml
stash:
  image: stashapp/stash:v0.31.1
  environment:
    TZ: ${TZ}
    STASH_STASH: /data/
    STASH_GENERATED: /generated/
    STASH_METADATA: /metadata/
    STASH_CACHE: /cache/
    STASH_PORT: 9999
  volumes:
    - ./config/stash/config:/root/.stash
    - ./config/stash/metadata:/metadata
    - ./config/stash/cache:/cache
    - ./config/stash/blobs:/blobs
    - ./config/stash/generated:/generated
    # See "the library is 100% symlinks" below - these three are not optional.
    - /mnt/zurg:/mnt/zurg:rslave
    - /mnt/decypharr:/mnt/decypharr:rslave
    - /mnt/nzbdav:/mnt/nzbdav:rslave
    - ./media/adult:/data:ro     # read-only - see below
  ports:
    - "9998:9999"                # 9999 is Zurg's port on this stack; remapped host-side only
```

**Mounted `:ro` deliberately.** Stash's scan/tag/scrape flow never needs write access to the
source library. Its own opt-in "Organize" task renames and moves files — not something to allow
by accident onto a library Whisparr independently manages the layout of. Drop the `:ro` only if
Organize is deliberately wanted.

**The library is 100% symlinks, and the first deploy missed that.** `./media/adult` is Whisparr's
root folder, and per this stack's own architecture (see [Architecture](#architecture)) a root
folder never holds real files — every entry is a symlink into `/mnt/zurg`, `/mnt/decypharr`, or
`/mnt/nzbdav`. The initial `docker-compose.yml` only mounted `./media/adult:/data:ro` and none of
those three FUSE mounts, so every symlink was dangling from inside the Stash container's own mount
namespace. Not an obvious failure: a real library scan **completed successfully in seconds** and
reported 0 scenes/images found, no error anywhere. Root-caused by `readlink` on a sample symlink
(`/data/scenes/.../*.mp4` → `/mnt/nzbdav/.ids/...`) resolving to a path that simply didn't exist
inside the container, confirmed with `stat -L` failing "No such file or directory". Fixed by adding
the same three mounts every other consumer of this library already has (Whisparr, Radarr, Plex,
etc. above) — `stat -L` on the same symlink then resolved to a real 2.5GB file, and a rescan
correctly found all 530 of 531 files.

**No PUID/PGID support.** Unlike the LSIO/hotio images elsewhere in this stack, the stock
`stashapp/stash` image doesn't document PUID/PGID env vars (confirmed against its own reference
`docker-compose.yml`) — it runs as root inside the container, so `./config/stash/*` ends up
root-owned on the host.

**No auth configured**, consistent with every other web UI in this stack (see
[Security](#security)) — Stash does support an optional built-in password if that's ever wanted.

**Healthcheck needs `wget`, not `curl`.** The stock image is Alpine-based but doesn't bundle
`curl` — a `curl`-based `CMD-SHELL` healthcheck (this stack's usual pattern for every other app)
fails immediately with `executable file not found in $PATH`, confirmed live via `docker exec`,
and the container sits reporting `unhealthy` forever despite the app itself working fine.
`wget -qO- --spider http://localhost:9999/` is the working equivalent, confirmed against the
same image.

**Resource limits are a starting estimate, not observed.** `mem_limit: 2g` / `cpus: 4` — scene
thumbnail/sprite/preview generation is real ffmpeg transcoding work, but this hasn't been run
against the actual library size yet. Revisit against real `docker stats` once a full scan has run,
same as every other limit in [Resource limits](#resource-limits).

### Configuration audit (v10.9.3)

Checked against a real 530-scene scan, not just the defaults:

- **`parallel_tasks` was `1`** despite the host having 16 cores and this container being allowed
  4 — every scan/generate task was fully serialized. Bumped to `4` via
  `mutation { configureGeneral(input: {parallelTasks: 4}) }`; confirmed live in the next generate
  job's own log line (`Generate started with 4 parallel tasks`).
- **Hardware transcoding attempted, found genuinely broken, left on anyway.** The bundled ffmpeg
  is VAAPI-capable (`-hwaccels` lists it, `h264_vaapi`/`hevc_vaapi` encoders present) and this
  host has a real iGPU (`/dev/dri/renderD128`), so `/dev/dri` was passed through and
  `transcode_hardware_acceleration` enabled. A direct decode test against that device failed
  outright (`Failed to initialise VAAPI connection: -1 (unknown libva error)`) — the stock
  Alpine-based image is missing the actual userspace VAAPI driver package (e.g.
  `mesa-va-drivers`), ffmpeg having the API compiled in isn't the same as a working runtime.
  **Confirmed harmless, not confirmed beneficial**: a real generate job (previews) completed
  successfully with valid output either way, no errors in Stash's own logs — software fallback,
  not a break. Left the device mount and setting in place as a foundation for a future custom
  image; fixing this for real needs building a custom Stash image layering the driver package on
  top, which no other third-party app in this stack currently does.
- **`config/stash/cache` and `config/stash/generated` added to the restic exclude list** (see
  [Backups](#backups)) — same fully-regenerable reasoning as Plex's own cache exclusions, closed
  before either directory had a chance to grow large enough to matter.
- **`config/stash/config/config.yml` was unreadable by the backup user** (`640`, root-only,
  running the real off-site backup verification caught it directly:
  `permission denied` in the restic run). Fixed with `sudo chmod 644` — worth re-checking if a
  future Stash settings change somehow reverts it. The actual data that matters,
  `stash-go.sqlite`, was already `644` and has always been covered; this only affected the
  settings file, which is regeneratable via the setup wizard in a few minutes if ever lost.
- **StashDB connected** (`stashBoxes` in `configureGeneral`, `endpoint:
  https://stashdb.org/graphql`) — the personal account/API key was the user's own step (same
  category as Bindery's admin-account creation in [v10.7.0](#history)), verified against the real
  endpoint (`{ me { name } }`) before wiring it in. A full `metadataIdentify` run against all
  scenes, with `fieldOptions` set to `MERGE`+`createMissing: true` on studio/performers/tags
  (the default options only fill fields that already have a local match — without
  `createMissing`, nothing new ever gets created), took the library from zero metadata to
  **317 performers, 225 studios, 791 tags** across 582 scenes.

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

Lidarr used to carry its own additional custom format, **"Blocked Uploader (88 tag)"** — a regex
(`(?<!\d)88(?:cube)?\s*$`) rejecting a specific low-trust uploader's release-title tag
(`vtwin88cube` and similar), added after a real corrupted-archive investigation traced a run of
`rardecode: bad file checksum` failures to that uploader's catalog specifically, not to anything
in this stack's own download/extraction chain. Moot as of v10.9.9 — Lidarr was removed entirely
(see [History](#history)), taking its own quality profile and custom formats with it.

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
don't redundantly hunt the same libraries against the same indexers. NeutArr is wired to the
three Servarr-shaped `*arr` apps (Sonarr, Radarr, Whisparr — configured as its "Whisparr V3"
app type, not V2, matching this stack's `:v3` "eros" pin), each instance's URL/API key set
directly in `config/neutarr/{sonarr,radarr,eros}.json` (a straight host bind
mount at `/config`, editable without going through NeutArr's own UI — its own "Apps" settings
page hits the same files). `readarr.json` is still present in that directory but
`"enabled": false` — a leftover from before Readarr was replaced by Bindery (itself since retired,
see [Bindery and Calibre-Web: retired](#bindery-and-calibre-web-retired)); `lidarr.json` was
deleted along with Lidarr's own state/config in v10.9.9 (see [History](#history)); there's no
ebook app of any kind, and no music app of any kind, to wire up here today.

> **NeutArr, not Huntarr.** NeutArr is a hardened fork tracing through `elfhosted/newtarr`'s fork
> of Huntarr v6.6.3 — the last clean release before Huntarr's own maintainer suppressed reports of
> an unauthenticated auth-bypass that leaked every connected `*arr` app's API keys in cleartext,
> then took the repo private and banned users raising the issue. Never add Huntarr proper to this
> stack; NeutArr's whole reason for existing is that vetted alternative.

`config/neutarr/whisparr.json` was a second, orphaned config file for the same app — NeutArr's
real slot for Whisparr is internally named `eros` (standard Huntarr-lineage terminology, matching
the `:v3` "eros" pin), confirmed live via its own `settings_manager` log line (`Configured apps:
['sonarr', 'radarr', 'lidarr', 'eros']` — no `whisparr` entry at all). The orphaned file had
`"enabled": true` with blank `api_url`/`api_key`, which reads as a live bug at a glance but was
never actually read by NeutArr. Deleted rather than left as confusing clutter.

**Cleanuparr had a real, live gap found this session**: its own `arr_instances` table only had
Sonarr and Radarr actually connected — Lidarr and Whisparr had config-type placeholders
(`arr_configs`) but no instance, so queue-cleaning, strike-tracking, and malware-blocking weren't
covering either app at all despite both being fully functional `*arr` apps in this stack. Found by
querying `config/cleanuparr/cleanuparr.db` directly (`SELECT * FROM arr_instances`) since
Cleanuparr's REST API isn't straightforwardly discoverable (same limitation noted in [Known
gaps](#known-gaps-and-limitations) re: its stale Readarr reference). Fixed by adding both through
Cleanuparr's own **Settings → Lidarr/Whisparr → Add Instance** UI — confirmed connection-tested and
persisted at the time. All four Servarr-shaped apps were covered by Sonarr/Radarr/Lidarr/Whisparr
across Cleanuparr, NeutArr, and Unpackerr consistently at that point; as of v10.9.9, Lidarr is
gone entirely (see [History](#history)) and the three remaining apps (Sonarr/Radarr/Whisparr) are
what's covered. **The stale Lidarr row this left in Cleanuparr's SQLite `arr_instances` table was
cleaned up 2026-07-14**: no REST endpoint exists for this table at all (confirmed against
Cleanuparr 2.9.16's actual API surface — `download_client`, `malware_blocker`, and every other
`/api/configuration/*` route are unrelated; `arr_instances` is genuinely DB-only), so the fix was
to stop the container (avoiding any live WAL-mode write), delete the `arr_instances` row and its
now-orphaned parent `arr_configs` row directly, confirm zero orphaned rows in the six other tables
that reference `arr_instance_id`, then restart — came back healthy with Sonarr/Radarr/Whisparr
only, zero errors. Stash remains correctly excluded from all three (see its own section above)
since it isn't Servarr-shaped.

**Unpackerr** (`golift/unpackerr@sha256:4ec141...`) auto-extracts RAR'd releases across the three
Servarr-shaped `*arr` apps:

```yaml
UN_RADARR_0_URL: http://radarr:7878
UN_RADARR_0_API_KEY: ${RADARR_API_KEY}
# ...same pattern for sonarr/whisparr. The UN_LIDARR_0_* pair was removed in v10.9.9
# along with Lidarr itself (see History).
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

Digest-pinned images (Seerr, Kometa, Unpackerr, Byparr) and exact-version-tag-pinned ones
(Zilean, Decypharr, Watchtower itself, Plex) are **not** meaningfully auto-updated by
this — a digest or exact version tag is immutable, so Watchtower never finds anything new to pull
for those. See [Image pinning policy](#image-pinning-policy).

## Monitoring extras: Tautulli

- **Tautulli** (`ghcr.io/hotio/tautulli:release`, port 8182) — Plex watch-history/stats dashboard.

**Glances and Dozzle were both removed entirely in v10.9.9** — full removal, no data was kept
(neither had a config volume to begin with, so there was nothing to preserve). Glances powered
Control Panel's Overview "Host CPU/memory/disk/uptime" tiles via `/api/system/stats`; that
endpoint and those tiles are gone too, not just left silently degraded. Dozzle was a standalone
container-log viewer with read-only `docker.sock` access; Control Panel's per-app log tailing
(`/api/arr/{app}/logs`) is unaffected, it never depended on Dozzle. A Prometheus + Grafana
monitoring stack was also researched and briefly proposed in this same version, then cancelled
before any of it was built — nothing was ever added to `docker-compose.yml`.

**Adminer was removed in v10.9.9, with no replacement.** It briefly became CloudBeaver
(`dbeaver/cloudbeaver:24.3.0`) the same day, but that was reverted immediately — not a fit for
this stack. There's currently no web GUI for `zilean-postgres`/`dmm-mysql`; inspecting either
means `docker exec -it <db> psql/mysql ...`, same as before Adminer ever existed.

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

**Whisparr isn't supported by Maintainerr at all** (neither was Lidarr, before its removal in
v10.9.9) — its own settings controller only exposes `/radarr` and `/sonarr` connection endpoints,
nothing for any other `*arr` app. Not a gap in this stack's setup; a real limitation of what
Maintainerr itself connects to.

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
# control-panel/app.py - the ARR_APPS dict this whole panel is built around.
# Lidarr's entry (and its v1-API special-casing) was deleted in v10.9.9 along
# with Lidarr itself - see History.
ARR_APPS = {
    "radarr":  {"url": "http://radarr:7878",   "api": "v3", "search_command": "MissingMoviesSearch"},
    "sonarr":  {"url": "http://sonarr:8989",   "api": "v3", "search_command": "MissingEpisodeSearch"},
    "whisparr":{"url": "http://whisparr:6969", "api": "v3", "search_command": "MissingMoviesSearch"},
}
QUEUE_ARR_APPS = ("radarr", "sonarr", "whisparr")
```

| Endpoint | Method | What it does |
|---|---|---|
| `/healthz` | GET | Liveness probe (what the container's own healthcheck uses) |
| `/api/status` | GET | Running/health state for every container in the compose project |
| `/api/containers` | GET | Full grid: state, health, image, live CPU/mem per container |
| `/api/api-hit-counts` | GET | Live per-app outbound API call counter - dashboard flourish, see below |
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

### Live API hit counter: a dashboard flourish, not a metrics system

Every container card for an app Control Panel actually talks to over HTTP (the three Servarr-shaped
`*arr` apps, Plex, Zilean, Decypharr, NzbDAV) shows a live "API" row - a small dot and a
running count of outbound calls this panel has made to that app since it last started, ticking up
and flashing green on real increments. Purely cosmetic (in-memory `Counter`, resets on restart,
no persistence, no per-endpoint breakdown) - explicitly "for visual effect," not a monitoring
feature.

```python
# control-panel/app.py - wraps httpx.request itself rather than touching
# every one of this file's ~25 call sites individually
API_HIT_COUNTS = Counter({label: 0 for label in _API_HOST_LABELS.values()})
_httpx_request = httpx.request

def _counted_request(method, url, *args, **kwargs):
    host = urlparse(str(url)).hostname
    API_HIT_COUNTS[_API_HOST_LABELS.get(host, host or "unknown")] += 1
    return _httpx_request(method, url, *args, **kwargs)

httpx.request = _counted_request
httpx._api.request = _counted_request
```

**Two real bugs found building this, neither obvious from the docs:**

- **Reassigning `httpx.request` alone is a silent no-op.** `httpx.get`/`post`/`put`/`delete`/
  `patch` all internally call a function named `request`, but that name resolves against
  `httpx._api`'s own module globals (where those functions are actually defined), not `httpx`'s
  top-level namespace - confirmed via `httpx.get.__globals__ is httpx.__dict__` returning `False`.
  Caught live: hit counts stayed at exactly `0` through real, confirmed-working traffic. The fix
  is patching `httpx._api.request` directly (`httpx.request` is reassigned too, for anything that
  calls it by that name directly).
- **`/api/containers` was taking 60-90+ seconds**, discovered by accident while checking whether
  the new hit-counter badges were rendering — the container grid simply never loaded. Root cause:
  `container_stats()`'s own docstring claims a single `stats(stream=False)` call needs "no extra
  polling delay," but empirically each call still blocks ~1-2s (the Docker Engine API takes an
  internal two-sample delta regardless of the `stream` flag), and the endpoint called it in a
  sequential loop across all 34 containers - `34 × ~2s ≈ 67s` measured directly with `time curl`.
  This silently broke the grid's 15s auto-refresh entirely (the next poll would already be piling
  up behind the previous one). Fixed with a `concurrent.futures.ThreadPoolExecutor` (`max_workers`
  capped at 16) so all containers' stats are fetched in parallel instead of one at a time - total
  latency dropped to ~6s, bound by the slowest single container rather than the sum of all of them.
- **Separately, the frontend's own `ARR_APPS`/`QUICK_LINKS` arrays in `app.js`** - a second,
  independent list from the backend's `ARR_APPS` dict, used only to render the *arr apps section
  and Quick Links - still had a hardcoded `readarr` entry left over from the Bindery swap
  ([v10.7.0](#history)), invisible until actually looking at the rendered page: Quick Links linked
  to a "Readarr" tile that happened to still resolve (Bindery kept the same port), and the *arr
  apps section rendered a fully interactive "Readarr" row whose buttons would have 404'd against
  `/api/arr/readarr/...`, which no longer exists server-side. Fixed alongside the hit-counter work
  since it was found while visually checking it, not left for a separate pass.

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
MOUNT_PREREQS = {"nzbdav"}
MOUNT_PROVIDERS = {"zurg", "decypharr", "decypharr-alldebrid", "rclone-alldebrid", "rclone-alldebrid-anime", "nzbdav-rclone"}
MOUNT_DEPENDENTS = {"radarr"}

def worker():
    for c in prereqs: c.restart(timeout=30)
    for c in prereqs: wait_for_healthy(c)
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

**`nzbdav-rclone` needs its own prereq wave, not just a spot in `MOUNT_PROVIDERS`.** It owns the
`/mnt/nzbdav` FUSE mount exactly like `zurg`/`decypharr`/`rclone-alldebrid*` own theirs, but unlike
them it has an upstream dependency of its own: its rclone remote talks to `nzbdav`'s own API
(`docker-compose.yml`'s `depends_on: nzbdav: condition: service_healthy`), which `docker compose
up` enforces but this hand-rolled restart loop doesn't know about on its own. Originally
`nzbdav-rclone` wasn't in `MOUNT_PROVIDERS` at all — found live during a full stack outage where
`/mnt/nzbdav` was left stale at the **host** level (`Transport endpoint is not connected`,
registered in the host's mount table with a dead backing process) after a `stack-restart-all` run;
recovering required `sudo umount -l /mnt/nzbdav` on the host before anything would mount cleanly
again, since a container restart alone can't clear a stale entry the host itself is holding onto.
`MOUNT_PREREQS` restarts `nzbdav` first and waits for it healthy before the `MOUNT_PROVIDERS` wave
(which now includes `nzbdav-rclone`) starts, so `nzbdav-rclone`'s mount always finds `nzbdav` ready
instead of racing it.

**Known gap, pre-existing:** `MOUNT_DEPENDENTS` only ever contains `radarr`, despite Whisparr
binding the same three FUSE subpaths directly (`/mnt/zurg`, `/mnt/decypharr`,
`/mnt/nzbdav` — not a blanket `/mnt` bind) and therefore needing the same restart-ordering
protection Radarr gets. Not introduced or verified safe by any pass so far — flagged here since
it keeps getting noticed, not fixed. (Lidarr was in the same boat before its removal in v10.9.9;
moot now.)

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
stack-arr whisparr rss-sync                     # radarr/sonarr/whisparr; or search-missing / unstick
stack-arr-import-candidates whisparr            # list files ready to manually import
stack-arr-import whisparr 0                     # import candidate #0 from the list above
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
`radarr`/`sonarr`/`whisparr` as their app argument, matching Control Panel's own
`/api/arr/{app}/...` endpoints and `QUEUE_ARR_APPS` set exactly (the `lidarr` case was removed
along with Lidarr itself in v10.9.9 — see [History](#history)):

```fish
# ~/.dotfiles/.config/fish/functions/stack-arr.fish
function stack-arr --description 'Trigger an *arr app maintenance action'
    if not contains -- $argv[1] radarr sonarr whisparr
        echo "Unknown app '$argv[1]' - use radarr, sonarr, or whisparr." >&2
        return 1
    end
    ...
```

`stack-bazarr-search` was removed entirely along with Bazarr itself — it called
`/api/bazarr/search-wanted`, an endpoint that no longer exists in `control-panel/app.py`.

**Twenty more commands, added after a live resource+wiring audit turned up real, previously
invisible gaps** (10 containers with no `mem_limit`, 5 apps stuck on debug logging, a Zurg
`group_order` bug, Cleanuparr missing two `arr_instances`) — each one turns a manual
diagnostic session into a real command instead of a one-off `curl`/`sqlite3`/`journalctl`
session:

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
stack-stash-scan                                # trigger a Stash library scan
stack-stash-identify                            # trigger a full-library StashDB identify run
stack-arr-logs radarr 200                       # tail a container's log directly
stack-plex-empty-trash "TV Shows"               # scoped to one library, or every library if none given
stack-image-check                               # digest/exact-version-pinned images vs their registry
stack-disk-usage                                # per-app config/ directory size, largest first
stack-version                                   # README's declared version + live container count
stack-whisparr-hunt                             # force NeutArr to run an immediate hunt pass
```

**Three more added in v10.9.8, filling gaps found while auditing this list against Control
Panel's actual endpoint set** — `/api/plex/updates`, `/api/arr/{app}/manual-import-all`, and
`/api/arr/{app}/missing-aired` had no CLI wrapper at all before this:

```fish
stack-plex-updates                              # check for a Plex update (check only, doesn't apply it)
stack-arr-import-all whisparr                    # import every stuck queue file in one go, not just one
stack-arr-missing-aired sonarr                   # monitored + missing + already aired/released
```

**Seven more added in v10.10.0 — Letterboxd-to-Radarr, no extra container needed** (unlike
screeny05/letterboxd-list-radarr's Redis-backed adapter service). Each film-page fetch scrapes
the TMDb id Letterboxd links in its sidebar; list/grid variants scrape every poster's
`data-item-slug` (max 10 pages / 720 films) and bulk-add whatever isn't already in Radarr:

```fish
stack-letterboxd-radarr https://letterboxd.com/film/inception/
stack-letterboxd-radarr-list https://letterboxd.com/<user>/list/<slug>/
stack-letterboxd-radarr-watchlist https://letterboxd.com/<user>/watchlist/
stack-letterboxd-radarr-watched https://letterboxd.com/<user>/films/
stack-letterboxd-radarr-filmography actor tom-hanks       # or director / writer / any crew role
stack-letterboxd-radarr-collection https://letterboxd.com/films/in/<collection>/
stack-letterboxd-radarr-popular                            # currently always empty, see History
```

All seven accept `--no-search` (skip triggering a download search), `--no-monitor`, and (list
variants) `--limit N` to cap how many films are processed.

**This whole CLI (all 40 commands now), plus a standalone, restyled Control Panel and a
credential-entry installer, has been spun off into its own repo:
[`StackScripts`](https://github.com/WhispersOfJ/StackScripts).** Unlike `Stackalicious` (the
sanitized *mirror* of this exact repo), `StackScripts` is a *generalized* redistribution —
no hardcoded IP or host paths, config collected through a browser-based setup wizard instead
of assumed from this repo's own `.env`. See `AGENTS.md` above: every new `stack-*` command
added here needs to be mirrored into both siblings in the same pass, not deferred.

## Backups

`./config` holds every app's settings, database, and plaintext API keys — none of it is in git,
and it's the one part of this stack that isn't reproducible by re-running `docker compose up` or
re-pulling images.

- **`scripts/backup-config.sh`** — dumps `zilean-postgres` (`pg_dump`) and `dmm-mysql`
  (`mysqldump`) first, then `restic backup ./config`, then `restic forget --prune` (`--keep-daily
  7 --keep-weekly 4 --keep-monthly 6`). Repo at `~/backups/stack-restic-repo`, restic-encrypted.
  Run daily at 03:30 by `systemd/stack-backup.timer`, before Watchtower's 4am updates. An off-site
  leg mirrors the same backup to any restic-supported remote (`BACKUP_REMOTE_REPOSITORY` in
  `.env`) with its own retention pass and Discord tag, and is now configured (see the Known
  limitation note below) with its own monthly `restic check --read-data-subset=10%` integrity
  check on the 1st of the month, same as the local repo.
- **Excluded from the restic backup**: `decypharr/cache` and `decypharr-alldebrid/cache` (fully
  regenerable FUSE caches), every app's `logs`/`log` directory, `zilean-postgres`'s and
  `dmm-mysql`'s raw datadirs (the `pg_dump`/`mysqldump` logical dumps above cover those instead —
  file-level copying a *running* database's data directory can produce an inconsistent restore),
  `stash/cache` and `stash/generated` (regenerable via Scan/Generate against the still-real source
  library, same reasoning as Plex's exclusions), and several regenerable Plex subdirectories
  (`Metadata` — 28GB of re-fetchable posters/art, `Cache`, `Codecs`, `Logs`, `Crash Reports`, plus
  the sibling `plex-transcode` directory).
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
  `zilean-postgres` data directories) a normal user can't read. **This is not reliable enough to
  be the stack's actual off-site protection** — confirmed live: one run failed outright (4h41m,
  exit 1, no output file produced at all) with no earlier successful run under the current
  `-latest` naming still present to fall back on. Kept as a coarse convenience snapshot of the
  whole `~/Claude` tree (not just this repo), not the disaster-recovery mechanism — see the real
  off-site leg above for that.
- **Known limitation, now closed**: this host has a single physical disk (one NVMe) — the local
  restic repo protects against config corruption and accidental deletion, not disk failure on its
  own. Found and fixed live: the local repo *and* the `backup-claude-dir.sh` Dropbox tar (the
  previous de facto off-site copy) both lived on that same single disk, and the tar leg had
  silently stopped producing valid output. The off-site leg is now a second restic repository
  inside this host's already-running, already-authenticated Dropbox sync folder
  (`~/Dropbox/stack-restic-repo-offsite`) — Dropbox's own client handles the actual off-site
  replication, no new cloud account or `rclone` install needed. Same password file as the primary
  repo (`BACKUP_REMOTE_PASSWORD_FILE` left unset, falls back to `~/backups/.restic-password`).

Verify anytime:

```bash
RESTIC_PASSWORD_FILE=~/backups/.restic-password restic -r ~/backups/stack-restic-repo snapshots
# off-site leg:
RESTIC_PASSWORD_FILE=~/backups/.restic-password restic -r ~/Dropbox/stack-restic-repo-offsite snapshots
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
- **Grab/import/upgrade/health events from the three Servarr-shaped `*arr` apps** — configured as
  each app's own native **Discord** notification connection (not a script), pointed at the same
  `DISCORD_WEBHOOK_URL`. Event selection is `onGrab`/`onDownload`/`onUpgrade` per app's own naming
  (Radarr/Sonarr/Whisparr all share this shape), and all three also fire on `onHealthIssue` and
  `onApplicationUpdate`. Verified live via each app's own `POST /api/v3/notification/test` — a
  real message reaches the channel. (Lidarr had a slightly different event set —
  `onGrab`/`onReleaseImport`/`onUpgrade` plus `onDownloadFailure`/`onImportFailure` — before its
  removal in v10.9.9; moot now.)

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
  Sonarr, Tautulli) — hotio's whole model is rolling channels identified by git-hash, not
  semver, so this is as close to "pin to the stable channel, explicitly" as that upstream
  supports. Whisparr is pinned to `:v3` specifically (a major-version channel, not just `:release`)
  for the reason described in [The *arr apps](#the-arr-apps).
- **Version tags** (`ipromknight/zilean:v3.5.0`, `cy01/blackhole:v2.3`,
  `nickfedor/watchtower:1.19.0`, `stashapp/stash:v0.31.1`)
  where the upstream project tags real releases and the current running image matches.
- **Digest pins** (`@sha256:...`) for Seerr, Kometa, Unpackerr, and Byparr — in every one
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

Everything else (Seerr, all three `*arr` apps, NzbDAV, Watchtower, etc.) carries a
smaller generous ceiling as defensive insurance rather than from observed pressure — see
`docker-compose.yml` directly for exact current values, which change more often than this document
is updated.

**That claim was wrong until v10.9.5.** A live audit (`docker stats` showing several containers
reporting the full host memory ceiling instead of a real number) found ten services with no
`mem_limit`/`cpus` at all: **Prowlarr, Radarr, Sonarr, Lidarr, Whisparr, Bindery, Recyclarr,
NzbDAV, Seerr, and `dmm-migrate`** — including the core acquisition pipeline apps, not edge
cases. Fixed with limits sized above each one's real observed baseline (Radarr/Sonarr at 2GB
given Sonarr's ~300,000 episode records, the rest at 1GB or lighter for genuinely lighter apps
like Bindery and Recyclarr). Verified live: recreated all ten, confirmed every one healthy, and
confirmed via `docker stats` that the new ceilings are real (e.g. Sonarr reporting `244.9MiB /
2GiB` instead of the host's full `22.74GiB`).

**Same audit found Radarr, Sonarr, Lidarr, Whisparr, and Prowlarr all running `logLevel: debug`**
in production, not the default `info` — confirmed via each app's own `/api/*/config/host`.
Log directories showed the real cost: 101MB (Radarr), 101MB (Sonarr), 101MB (Prowlarr), 65MB
(Whisparr), 52MB (Lidarr), all at or near Servarr's rolling-log cap. Almost certainly leftover
from past troubleshooting sessions (this document's own History is full of "confirmed via debug
log" investigations) and never reset. Set back to `info` on all five via one API call each.

## Security

Every web UI in this stack publishes its port directly on the host with **no login gate** — the
same model this stack has landed on twice now after trying and reverting a full auth layer once
(see [History](#history)):

- Everything is reached through plain `http://<ip>:<port>` — no certificate, no account.
- These addresses only work from devices on the home LAN, or a [Tailscale](https://tailscale.com)
  network if configured — nothing here is reachable from the public internet unless you
  specifically set that up.
- **Control Panel** is worth knowing about specifically — it holds read-write `docker.sock`
  access and can restart or inspect any container in this stack. Don't put this stack on a
  network you don't trust, and don't forward any of these ports publicly.
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
    "RADARR_API_KEY", "SONARR_API_KEY",
    "WHISPARR_API_KEY", "PLEX_TOKEN",
}
AUTO_GENERATE_KEYS = {"ZILEAN_POSTGRES_PASSWORD", "ZILEAN_API_KEY"}
```

`LIDARR_API_KEY` was dropped from `POST_BOOT_KEYS` (and from `.env`/`.env.example` entirely) in
v10.9.9 along with Lidarr itself — see [History](#history). `BINDERY_API_KEY` was already gone
from `AUTO_GENERATE_KEYS` by the time of this edit (2026-07-14) — it was a harmless leftover from
when Bindery *seeded* its key from the env var instead of generating its own, and had already been
cleaned up in the wizard's own source even though this doc hadn't caught up until now. Four fields
genuinely can't be collected before first boot — each Servarr-shaped `*arr` app generates its own
API key on first start, and `PLEX_TOKEN` needs a running Plex with at least one library item.
These render in a highlighted "⚠ Fill in after first boot" section and default to `changeme`;
re-running `--setup` loads the real `.env` as defaults, so a second pass only means retyping
what's actually new.

## Known gaps and limitations

Documented honestly rather than swept under the rug:

- **Sonarr's `missing-aired` endpoint has an unresolved pagination performance risk on large
  libraries.** The early-stop-on-first-future-episode optimization helps, but this Sonarr instance
  tracks close to 300,000 episode records, and the endpoint's real-world latency against that full
  scale hasn't been load-tested. It also has zero frontend wiring in Control Panel's UI — curl/API
  access only. See [The *arr apps](#the-arr-apps).
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
- **Cleanuparr still has a stale Readarr reference** in its own SQLite-backed config
  (`config/cleanuparr/cleanuparr.db`) left over from before the Bindery swap. Its API surface
  wasn't quickly discoverable (`/api/instances` returns an HTML shell, not JSON, unlike every other
  app's REST API in this stack) so this was flagged rather than reverse-engineered on the spot —
  a manual follow-up, not a blocker.
- ~~Cleanuparr logs a recurring `Error creating download service for Decypharr`~~ **Fixed in
  v10.9.2** — root cause was a plain stale/wrong password in Cleanuparr's own stored credential
  (`ai9_Y_5sOgmg_vbjoS-slg`), not a Bindery-style Bearer-vs-cookie protocol mismatch as first
  suspected. Confirmed directly with `curl` against Decypharr's login endpoint (`401` with the
  stored password, `200` with the real one from `.env`) before touching anything. See
  [History](#history).
- **NeutArr's own `python3` process gets OOM-killed inside its 512MB cgroup limit on a tight,
  regular ~30-minute cycle** — 15 kills confirmed in one overnight window
  (`journalctl | grep oom-killer`, `Memory cgroup out of memory: Killed process ... (python3)`,
  memcg-scoped to NeutArr's own container). Invisible from Control Panel's dashboard or a plain
  `docker ps` since `restart: unless-stopped` silently brings it back each time — looks healthy at
  any single glance, isn't actually stable. Not yet root-caused (leak vs. a task that just needs
  more headroom) or fixed; flagged from a live audit, not from a user report.
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

**v10.6.2 — NeutArr wired to all five `*arr` apps.**

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

**v10.6.3 — NeutArr's Whisparr hunt rate raised after ruling out three false leads.**

- **Whisparr's missing-backlog throughput stayed flat (~1.78/hr) even after being wired into
  NeutArr**, while Radarr and Sonarr's rates visibly jumped. Chased three explanations in turn
  before finding the real one:
  1. *Hourly cap exhaustion* — ruled out live via `config/tally/hourly_cap.json`: `eros` showed
     `1/20` API hits used, nowhere near its cap (Sonarr was actually the one maxed at `20/20`).
  2. *Stateful cooldown saturation* — ruled out via `config/stateful/eros/Default.json`: only 2
     `processed_ids` ever recorded (vs Radarr's 203), so there was no large already-tried pool
     blocking new hunts either.
  3. *A dead scheduler thread* — the wrong conclusion, reached by comparing `date -u`'s UTC
     output against NeutArr's own log timestamps (which are in its container's `TZ=America/
     New_York`, i.e. EDT, UTC-4) without converting between them - made a "next cycle" that was
     still ~19 minutes away look like it had been silently skipped for over 3 hours. Restarting
     NeutArr on this theory wasn't harmful (isolated container, no dependents) but wasn't
     necessary either - worth remembering that this stack mixes UTC (`date -u`, most API
     timestamps) and local EDT (NeutArr's own log lines) depending on the source, so a
     time-gap diagnosis needs both sides in the same zone before trusting it.
  - **Real cause**: nothing broken at all. `hunt_missing_items: 1` + `sleep_duration: 900`
    (15 min) caps NeutArr's own theoretical contribution at ~4 items/hour for Whisparr - Radarr
    and Sonarr only look faster because they have far more *other* throughput stacked on top
    (RSS sync, a much larger indexer pool, existing automation); for Whisparr, NeutArr's own
    modest pace was close to the whole story. Raised to `hunt_missing_items: 3` +
    `sleep_duration: 300` (5 min) in `config/neutarr/eros.json` - theoretical max goes from ~4/hr
    to ~36/hr, meaning the existing `hourly_cap: 20` (left unchanged) now actually binds instead
    of never being approached. Confirmed live: the very next cycle post-restart processed 3/3
    items instead of 1/1.

**v10.6.4 — Fixed a burst-artifact bug in `backlog-status`'s throughput calculation.**

- **`GET /api/backlog-status` could report absurd rates during a large import burst** — caught
  live checking the v10.6.3 fix's actual effect: Sonarr showed `13,800/hr` (ETA `15h56m`)
  immediately after clearing a chunk of its backlog. Root cause: the rate was `event_count /
  (newest_event_time - oldest_event_time)` over a fixed 50-event sample, and a busy app clears
  its queue in bursts, not a steady drip - all 23 of Sonarr's most recent import events had
  landed within the same 6-second window while it worked through a large `importPending`
  backlog. `23 / 6 seconds` extrapolated to a huge but technically-correct-arithmetic hourly
  rate on a denominator that was never meant to represent a sustained pace. Fixed two ways in
  `control-panel/app.py`: `RECENT_IMPORT_SAMPLE_SIZE` raised `50 → 200` (a bigger sample
  naturally spans more real elapsed time, diluting any single burst), plus a new
  `MIN_RATE_WINDOW_HOURS = 0.25` floor under the observed span as a hard backstop for whatever
  a bigger sample doesn't dilute away. Confirmed live: Sonarr's rate dropped from the `13,800/hr`
  artifact to a believable `304/hr`; Radarr's rate (which was never bursty) barely moved,
  confirming the fix targets the actual failure mode rather than just dampening every number.
  Bonus effect: with the noise gone, Whisparr's rate increase from the fix immediately above
  finally became visible (`1.78/hr → 2.85/hr`) - it had been real the whole time, just masked
  by how noisy the old calculation was.

**v10.7.0 — Readarr replaced outright by Bindery.**

- **Trigger: a real search failure, not a proactive swap.** `Search for 'author:3389' failed.
  Invalid response received from Goodreads` from Readarr turned out to be permanent, not
  transient — its Goodreads-replacement provider's API host, `api.bookinfo.club`, has no DNS
  record at all anymore (confirmed with `dig` against both the container's resolver and
  `8.8.8.8` directly), and upstream Readarr itself is officially retired ("lack of
  developers... decided to retire the project," per linuxserver.io's own deprecation notice).
  hotio never published a Readarr image at all, and linuxserver's own moving `develop`/`nightly`
  tags stopped resolving to a pullable manifest. No fix existed to find.
- **Replaced with [Bindery](https://github.com/vavallee/bindery)** (`ghcr.io/vavallee/bindery`,
  pinned `v1.25.0`) — a Go-based, distroless, single-binary Readarr replacement with its own
  OpenLibrary-primary (+ five fallback: Google Books, Hardcover, DNB, Audnex, Audible) metadata
  pipeline, zero scraping, built specifically to survive the class of failure that just killed
  Readarr.
- **Three real deployment gotchas, found live, not from the docs alone:**
  - Distroless means no shell and a non-root default UID (65532) — `BINDERY_PUID`/`BINDERY_PGID`
    env vars alone do nothing (Bindery's own docs: "sanity checks, not user switchers"); needed
    a Compose `user: "${PUID}:${PGID}"` override plus a host-side `chown` on `config/bindery/`
    before the container would even start.
  - A custom `CMD-SHELL` healthcheck failed with `/bin/sh: no such file or directory` — expected,
    given no shell — but the fix wasn't writing an exec-form workaround, it was deleting the
    custom healthcheck entirely: fetching Bindery's own `Dockerfile` from GitHub showed it already
    bakes in a correct `HEALTHCHECK CMD ["/bindery","healthcheck"]` that a compose-level
    `healthcheck:` block was silently overriding.
  - Every mutating API call (`POST`/`PUT`/`DELETE`) returned `{"error":"forbidden"}` despite a
    verified-correct `X-Api-Key` — root-caused by fetching `internal/auth/middleware.go` from
    Bindery's source, which gates mutations behind `RequireXRequestedWith` unless
    `AuthedViaAPIKey(ctx)` is true. Docs suggest API-key auth should be exempt; empirically, on
    the deployed `v1.25.0`, it wasn't. Fix: send `X-Requested-With: bindery-ui` on every
    provisioning call regardless.
- **Admin-account creation is a manual step, on principle.** Bindery gates its API behind a
  one-time `/setup` flow before any admin-level call succeeds. Creating that account means
  entering a username and password — outside what gets done on the user's behalf here — so this
  was the one step handed back: "complete `/setup` yourself," confirmed via `auth/status` showing
  `setupRequired: false` before continuing.
- **Provisioned live via Bindery's own API**, all real HTTP calls, no config files: registered
  Prowlarr as an indexer source and synced (`POST /api/v1/prowlarr` then
  `POST /api/v1/prowlarr/{id}/sync` — 23 indexers, including a Usenet one, DrunkenSlug) — note
  this is the *reverse* of how Prowlarr → Lidarr/Radarr/Sonarr/Whisparr sync works; Bindery pulls,
  it isn't pushed to. Added NzbDAV as a SABnzbd-type download client and confirmed the connection
  live (`POST /api/v1/downloadclient/{id}/test` → `Connection verified`). Added `/books` as the
  root folder.
- **NzbDAV needed a category it didn't have.** Its own test rejected Bindery with `SABnzbd has no
  category 'bindery' configured` — fixed by patching `api.categories` directly in NzbDAV's SQLite
  `ConfigItems` table (no API surface exposed this) and restarting the container.
- **One accepted, documented gap: Decypharr isn't wired in as a Bindery download client.**
  Bindery's generic qBittorrent client type expects real cookie-based username/password login;
  Decypharr's actual working auth is a Bearer API token (confirmed by direct curl — 401 on cookie
  login, 200 on Bearer). Decypharr's admin password is bcrypt-hashed and shared across five other
  already-working app connections, so it wasn't reset just to unblock this one client type. NzbDAV
  covers the download-client role in the meantime.
- **Every supporting service rewired to match**: `control-panel/app.py`'s `ARR_APPS` lost its
  `readarr` entry entirely (Bindery isn't Servarr-shaped, so the generic arr_queue/arr_command
  machinery that dict drives doesn't apply, and it has no presence in queue-status/backlog-status
  either) and `QUEUE_ARR_APPS` dropped to four apps; Unpackerr's `UN_READARR_0_*` env vars removed (Bindery
  isn't a supported Starr app for it); NeutArr's `config/neutarr/readarr.json` set to
  `"enabled": false` and kept as a scaffold rather than deleted; Decypharr's `categories` list
  renamed `readarr` → `bindery`; `scripts/setup_wizard.py`'s `POST_BOOT_KEYS` lost
  `READARR_API_KEY`, and `BINDERY_API_KEY` joined `AUTO_GENERATE_KEYS` instead — unlike every
  Servarr app, Bindery *seeds* its key from the env var on first launch rather than generating its
  own, so the value can be known before first boot.
- **Left as a flagged, un-actioned follow-up**: Cleanuparr's own SQLite-backed config
  (`config/cleanuparr/cleanuparr.db`) still has a stale Readarr reference. Its API surface wasn't
  quickly discoverable (`/api/instances` returns an HTML shell, not JSON), so this was documented
  rather than reverse-engineered on the spot.
- **Calibre-Web needed no changes at all** — it was already reading `./media/books:/books`
  directly off disk, the same path Bindery's own root folder now points at, so the ebook reader
  kept working straight through the swap underneath it.

**v10.8.0 — Live per-app API hit counter; `/api/containers` sped up 60x; a real
stack outage found and fixed.**

- **Added a live "API" badge to every container card** for each app Control Panel actually talks
  to over HTTP (the four Servarr-shaped `*arr` apps, Plex, Zilean, Decypharr, Glances, NzbDAV) — a
  small dot and running count of outbound calls this panel has made to that app since it last
  started, ticking up and flashing green on real increments. Explicitly a dashboard flourish, not
  a metrics system: in-memory `Counter`, resets on restart, no persistence. See
  [Live API hit counter](#live-api-hit-counter-a-dashboard-flourish-not-a-metrics-system) above.
- **Two real bugs found building it:** reassigning `httpx.request` alone was a silent no-op
  (`httpx.get`/`post`/etc. resolve `request` against `httpx._api`'s own module globals, not
  `httpx`'s top-level namespace — hit counts stayed at `0` through real traffic until
  `httpx._api.request` itself was patched); and `/api/containers` was quietly taking 60-90+
  seconds — each `container_stats()` call blocks the Docker Engine API for ~1-2s regardless of
  `stream=False`, and the endpoint called it in a sequential loop across all 34 containers. Fixed
  with a `ThreadPoolExecutor` (`max_workers` capped at 16); total latency dropped to ~6s, bound by
  the slowest single container instead of the sum of all of them.
- **Cleaned up a stale Readarr leftover from v10.7.0**: `app.js`'s own `ARR_APPS`/`QUICK_LINKS`
  arrays — a second, independent list from the backend's, used only to render the *arr apps
  section and Quick Links — still had a hardcoded `readarr` entry. Quick Links linked to a
  "Readarr" tile that happened to still resolve (Bindery kept the same port); the *arr apps
  section rendered a fully interactive "Readarr" row whose buttons would have 404'd against
  `/api/arr/readarr/...`, which no longer exists server-side.
- **A real full-stack outage, found and fixed live**: `/mnt/nzbdav` was left stale at the
  **host** level (`Transport endpoint is not connected`, registered in the host's mount table
  with a dead backing process) — the third confirmed instance of the mount-cascade failure class,
  this time taking down all 32 containers rather than just `nzbdav-rclone`'s dependents. Recovered
  with `sudo umount -l /mnt/nzbdav` on the host, then mount owners brought up and confirmed
  healthy before the rest of the stack. Root-caused a real gap in `stack-restart-all`'s own
  ordering logic while investigating: `nzbdav-rclone` owns a FUSE mount exactly like
  `zurg`/`decypharr`/`rclone-alldebrid*` do, but wasn't in `MOUNT_PROVIDERS` at all, and it also
  has its own upstream dependency (`nzbdav` itself) that the hand-rolled restart loop didn't know
  about the way `docker compose up`'s `depends_on` graph does. Fixed with a new `MOUNT_PREREQS`
  wave restarted and confirmed healthy before `MOUNT_PROVIDERS` (which now includes
  `nzbdav-rclone`) starts. See
  [Whole-stack restart: mount-order aware](#whole-stack-restart-mount-order-aware) above.

**v10.9.0 — Stash added: performer/studio/tag cataloging for the adult library.**

- **[Stash](https://github.com/stashapp/stash)** (`stashapp/stash:v0.31.1`) added to the `extras`
  profile, reading `./media/adult` (Whisparr's own root folder) read-only alongside Plex — an
  enrichment/cataloging layer, not a Plex replacement. See
  [Stash: adult library cataloging](#stash-adult-library-cataloging).
- **Wired into Control Panel's dashboard** the same way every other service is:
  `CONTAINER_LABELS` entry for the container grid, `QUICK_LINKS` entry (port 9998, host-side
  remapped since 9999 is Zurg's port on this stack) for the link launcher.
- **One real bug found bringing it up live**: the stock image has no `curl` (Alpine-based, but
  doesn't bundle it — confirmed via `docker exec`, `exec: "curl": executable file not found in
  $PATH`), so this stack's usual `curl`-based `CMD-SHELL` healthcheck pattern reported the
  container permanently `unhealthy` despite the app itself working fine (confirmed serving `HTTP
  200` throughout). Fixed with `wget -qO- --spider` instead, which the image does have.
- **First-run setup wizard completed** (library path `/data`, blobs path `/blobs`, database at
  the default `/root/.stash/stash-go.sqlite`) — its account/password step is optional and the
  wizard never actually presents one, so nothing credential-related was set on the user's behalf,
  consistent with every other app in this stack having no login. A full library scan afterward
  correctly indexed 530 of 531 files (see the mount-order bug below).

**v10.9.1 — Stash's missing `/mnt` mounts fixed; Cleanuparr's missing Lidarr/Whisparr
wiring found and fixed; an orphaned NeutArr config file removed.**

- **Stash's first real scan found 0 scenes** despite completing in seconds with no error — root
  cause and fix are documented in
  [Stash: adult library cataloging](#stash-adult-library-cataloging) above (missing `/mnt/zurg`,
  `/mnt/decypharr`, `/mnt/nzbdav` mounts left every symlink in `./media/adult` dangling). After the
  fix, a rescan correctly indexed 530 of 531 files.
- **Cleanuparr was only actually connected to Sonarr and Radarr** — Lidarr and Whisparr had
  config-type placeholders but no real instance, found by querying its SQLite config directly.
  Added both through its own UI, connection-tested. See
  [Automation extras](#automation-extras-kometa-cleanuparr-neutarr-unpackerr-watchtower) above.
- **A second, orphaned NeutArr config file for Whisparr removed** (`config/neutarr/whisparr.json`)
  — NeutArr's real slot for Whisparr is internally named `eros`; the orphaned file had blank
  credentials despite `"enabled": true`, which reads as a bug at a glance but was never actually
  read by NeutArr, confirmed via its own startup log.
- **A separate, pre-existing Cleanuparr↔Decypharr issue found, flagged, then actually fixed
  immediately after** — see v10.9.2 below.
- **Recyclarr and Unpackerr audited and confirmed already correctly scoped** — Recyclarr to
  Sonarr/Radarr only (no TRaSH Guides custom-format support for other apps), Unpackerr to all four
  Servarr-shaped apps. No changes needed to either.

**v10.9.2 — Cleanuparr's Decypharr download client fixed: a stale password, not a
protocol mismatch.**

- **Root cause was simpler than first suspected.** v10.9.1 flagged a recurring `Error creating
  download service for Decypharr` (`401 Unauthorized` on qBittorrent-compat login) and initially
  guessed it might be the same Bearer-vs-cookie-auth mismatch documented for Bindery's own
  Decypharr integration attempt. It wasn't — Radarr's own working Decypharr connection uses the
  same cookie-based username/password auth successfully, ruling out a protocol issue. The real
  cause: Cleanuparr's stored password (`ai9_Y_5sOgmg_vbjoS-slg`, likely a stale leftover from
  before a Decypharr admin-password rotation) simply didn't match the real one
  (`DECYPHARR_ADMIN_PASSWORD` in `.env`). Confirmed directly with two `curl` calls against
  Decypharr's own `/api/v2/auth/login` before touching Cleanuparr at all — `401` with the stored
  password, `200` with the real one.
- **Fixed through Cleanuparr's own Settings → Download Clients → Edit UI**, not a direct database
  write — verified the new password persisted in `cleanuparr.db` and confirmed healthy
  (`Client ... health changed: Healthy`) on the next restart.

**v10.9.3 — Off-site backup actually wired up; Stash configuration audited; NeutArr's
overnight OOM crash-loop found.**

- **A full-stack audit turned up the single biggest real risk in this whole system: this host's
  only true off-site backup mechanism had silently stopped working.** `~/backups/stack-restic-repo`
  (the real, versioned backup) and `backup-claude-dir.sh`'s Dropbox tar (the de facto off-site
  copy) both lived on the same single physical disk — and the tar leg had failed outright the
  night before this was found (4h41m run, exit 1, no output file). See
  [Backups](#backups) for what changed: a genuine off-site restic leg, riding on this host's
  already-running, already-authenticated Dropbox client, wired up through the
  `BACKUP_REMOTE_REPOSITORY` mechanism that already existed in `backup-config.sh` but had never
  been turned on. Verified end-to-end, not just configured: ran the real script for real, confirmed
  a genuine snapshot landed in the off-site repo (48GB backed up, 44.7GB stored after dedup).
- **That same verification run caught a second, smaller bug**: `config/stash/config/config.yml`
  was root-owned `640` and unreadable by the backup user, so Stash's settings file (not its scene
  data — `stash-go.sqlite` was already `644`) had never actually been covered by either backup
  leg. Fixed with `chmod 644`.
- **Stash's configuration audited against a real 530-scene scan** — `parallel_tasks` bumped from
  `1` to `4`, hardware transcoding attempted and found genuinely non-functional (missing VAAPI
  driver in the stock image, confirmed harmless via a live generate test, left in place as a
  foundation rather than reverted), `cache`/`generated` added to the backup exclude list, and the
  real remaining gap identified: zero scrapers or StashDB connection, meaning every scene so far
  has zero performer/studio/tag metadata. See
  [Stash: adult library cataloging](#stash-adult-library-cataloging) above.
- **A second live-audit finding, unrelated, not yet fixed**: NeutArr's own process getting
  OOM-killed every ~30 minutes overnight (15 times in one window), silently self-healing via
  `restart: unless-stopped` and therefore invisible on the dashboard. See
  [Known gaps](#known-gaps-and-limitations).

**v10.9.4 — A real content-leak report resolved live: adult content was landing in
both Movies and TV Shows, for two different reasons.**

- **User-reported, not audit-found**: "Drilling Mommy" showing up in the Movies library.
  Confirmed via Radarr's own API it was never `*arr`-tracked — untracked content Zurg classifies
  independently, same failure class as every prior leak in
  [Zurg content-routing](#the-debrid-pipeline-zurg--decypharr). Cross-checking the rest of
  `/mnt/zurg/movies` against Radarr's full tracked-title list turned up two more untracked series
  leaking the same way: `Family Swap` and `The Best of Forbidden Scenes`. Added `Drilling`,
  `Family[\s._-]?Swap`, and `Forbidden[\s._-]?Scenes` to Zurg's `adult` keyword filter (plus
  `Cory[\s._-]?Chase`, a performer name spotted in the same sweep) — verified against both the
  new leaks and existing legitimate titles with the same words (`Mommy Dead and Dearest`,
  `Goodnight Mommy`, `Double Mommy` all correctly still don't match) before applying.
- **A second, structural bug found investigating why `Family Swap` was *also* leaking into TV
  Shows**: `adult`'s `group_order: 17` ran *after* `shows`' generic `has_episodes: true`
  heuristic (`group_order: 10`), so anything numbered like a series (`Family.Swap.10.2023.720p`)
  got claimed by `shows` before the adult keyword filter ever ran — no keyword-list fix could
  have caught this, since it never reached that filter at all. Fixed by moving `adult` to
  `group_order: 5`, first in the whole sequence.
- **Applied and verified live, following this stack's own documented mount-restart procedure**:
  Zurg restarted (config change), Radarr restarted after (its own documented mount fragility),
  confirmed via direct `stat -L`/`ls` on both host and inside the Plex container that the files
  physically moved from `/mnt/zurg/{movies,shows}` to `/mnt/zurg/adult`. Plex's own library index
  took longer to catch up than the underlying fix — a plain library scan only adds new files, it
  doesn't prune entries whose file disappeared, and this host's ~300k-episode TV library scan is
  slow enough that `emptyTrash` had nothing to purge yet by the time this was checked. The fix
  itself is confirmed correct at the source regardless of how long Plex's own UI takes to
  reflect it.

**v10.9.5 — Resource-limit and log-level audit: ten containers found running with no
memory/CPU ceiling at all.**

- **Ten services had zero `mem_limit`/`cpus`** despite [Resource limits](#resource-limits)
  claiming full coverage: `prowlarr`, `radarr`, `sonarr`, `lidarr`, `whisparr`, `bindery`,
  `recyclarr`, `nzbdav`, `seerr`, `dmm-migrate` — found via `docker stats` reporting the full
  host memory ceiling instead of a real number. Fixed with limits sized above each one's real
  observed baseline; see [Resource limits](#resource-limits) above for the full table and
  verification.
- **Same audit found Radarr, Sonarr, Lidarr, Whisparr, and Prowlarr running `logLevel: debug`**
  in production — set back to `info` on all five.

**v10.9.6 — Twenty new `stack-*` commands; the whole CLI + a generalized Control
Panel spun off into a standalone `StackScripts` repo.**

- **Twenty new diagnostic/action endpoints added to `control-panel/app.py`**, each backing a
  new `stack-*` command — see [CLI](#cli-the-stack--fish-functions) above for the full list.
  Needed three new read-only mounts (`/mnt`, `./config`, both restic repos), `restic` added
  to the Control Panel image, and `PyYAML` added for parsing Zurg's config live. Also wired
  `PROWLARR_API_KEY` through so `stack-log-levels` covers all five Servarr-shaped apps, not
  just the four already integrated.
- **Three real bugs found verifying these live, before committing**: `disk-usage`/
  `perms-check` were resolving symlinks in `config/decypharr/downloads` out to the multi-TB
  debrid mount (fixed with `lstat` + `followlinks=False`); `disk-usage` was then using
  `st_size` instead of `st_blocks`, wildly overstating usage against Decypharr's sparse
  cache files (confirmed against real `du` output — decypharr reported 349GB against an
  actual 11GB); `backup-verify`/`backup-restore-test` failed outright against the read-only
  repo mounts until restic calls got `--no-lock`, and the restore test crashed on the first
  binary file it happened to pick until raw bytes stopped being force-decoded as UTF-8.
- **The entire CLI (all 36 commands now) plus a generalized, restyled Control Panel and a
  credential-entry installer spun off into a new, standalone repo,
  [`StackScripts`](https://github.com/WhispersOfJ/StackScripts)** — every script verified
  live against a real running control panel, not just syntax-checked, which caught two real
  shell bugs: an unset-positional-parameter crash under `set -u` in both shells' shared API
  helper, and zsh's `read -p` silently meaning "read from a coprocess" instead of "show a
  prompt" (never populating the confirmation variable in `stack-restart-all.zsh`). `AGENTS.md`
  added to this repo, `Stackalicious`, and `StackScripts` itself, codifying the sync
  obligation: a new `stack-*` command isn't done until it exists in all three.

**v10.9.7 — Bindery's Decypharr download client fixed: same root cause as
Cleanuparr's, not the Bearer-token protocol limitation it was assumed to be.**

- **The "accepted gap" from v10.7.0 was wrong, the same way Cleanuparr's was in v10.9.2.**
  A live `qBittorrent auth failed (HTTP 401)` report from Bindery's own poller prompted a
  fresh look instead of re-citing the old conclusion. Bindery's `download_clients` row for
  Decypharr had its API key stuffed into `username` with `password` empty — never real
  admin credentials. Fixed through Bindery's own Settings → Download Clients → Edit UI
  (`admin` / the real `DECYPHARR_ADMIN_PASSWORD`), confirmed live: the 401s stopped
  immediately and `/api/v1/downloadclient/1`'s health flipped from `error` to `ok`.
  Decypharr's cookie-based qBittorrent-compat auth works fine — it always did, for every
  other app already wired to it.
- **A second, unrelated gap surfaced once auth was fixed**: `config/decypharr/downloads/bindery`
  had never been created (Decypharr only creates a category's folder on that category's first
  real download, and Bindery had never gotten far enough to trigger one). Created manually
  (`1000:1000`, `755`, matching every sibling category folder) — confirmed via Bindery's Test
  button: `Connection successful!`.
- **Write endpoints on Bindery's own API (`PUT`/`DELETE`) return a blanket `403 forbidden`
  under API-key auth**, even with the right key — only reads work that way. Mutating anything
  needs a real browser session against the UI, same as this fix. Noted here since it cost a
  few failed `curl` attempts before landing on the UI approach that actually worked.
- **`scripts/enable-recycle-bin.py` extended to Lidarr and Whisparr** — a Servarr-docs review
  found both had `recycleBin: ""` (completely unset) while Radarr/Sonarr had it configured since
  the original mass-deletion incident (see `2026-07-09` note in [History](#history)). Lidarr
  needed its own `api_version` field added to the script (`/api/v1/config/mediamanagement`, not
  `/api/v3/` like the other three) — confirmed live, not assumed from Radarr/Sonarr's shape. Both
  now set to `.recyclebin` under their own root (`/data/music`, `/data/adult`), 7-day cleanup,
  confirmed via a fresh `GET` against each app's own API afterward, not just the script's own exit
  code.

**v10.9.8 — Bindery and Calibre-Web retired outright; Decypharr's admin-auth gap
generalized past Bindery's own fix; Kometa's silent auto-run-on-restart stopped; NzbDAV's
Repairs tab wired to see Radarr/Sonarr's root folders.**

- **Bindery and Calibre-Web both removed, `docker-compose.yml` service blocks deleted for
  good** — see [Bindery and Calibre-Web: retired](#bindery-and-calibre-web-retired). Bindery
  never tracked a single author/book across its entire run (v10.7.0 through this version, even
  after v10.9.7's real Decypharr-auth fix), so there was nothing in Calibre-Web's library either;
  keeping both running idle wasn't worth it. `config/bindery/` and `config/calibre-web/` left on
  disk, not deleted. `CALIBRE_WEB_ADMIN_USERNAME`/`_PASSWORD` dropped from `.env`/`.env.example`.
  `control-panel/app.py`'s `CONTAINER_LABELS` and `ARR_LOG_CONTAINERS` no longer list either
  service; `MOUNT_DEPENDENTS`/backup/Unpackerr/Maintainerr/Cleanuparr/NeutArr/Discord references
  to Bindery removed throughout this document accordingly.
- **Recycle Bin gap from v10.9.7's Servarr audit closed in the same pass** (see the
  `enable-recycle-bin.py` entry directly above) — bundled into this version rather than its own,
  since both landed in the same working session.
- **Control Panel's `/api/decypharr/grab` (manual-grab) endpoint hit the same 401 Bindery's own
  fix in v10.9.7 diagnosed** — Decypharr's `/api/v2/*` torrent API needs its own qBittorrent-style
  session (`POST /api/v2/auth/login` with `DECYPHARR_ADMIN_USERNAME`/`_PASSWORD`, a separate SID
  cookie from the web UI's own `/login`), not just a bare POST. `decypharr_grab()` now logs in
  first via a shared `httpx.Client` before `createCategory`/`add`; `DECYPHARR_ADMIN_USERNAME`/
  `_PASSWORD` added to `control-panel`'s environment in `docker-compose.yml`. Confirmed live: the
  endpoint 401'd unnoticed before this fix since it's arm/confirm-gated and rarely exercised.
- **Kometa was silently doing a full run on every container start/restart, not just on a
  schedule** — no `run_time` is set in `config/kometa/config.yml`, but the image's default
  entrypoint (`python3 kometa.py --`) runs a complete pass immediately regardless, confirmed live
  (a 19+ hour single run since the container's last start, no cron/systemd timer/webhook trigger
  anywhere). Overridden to `entrypoint: ["/tini", "-s", "--"]` / `command: ["sleep", "infinity"]`
  so restarts idle instead; Control Panel's `/api/kometa/run` already execs `python3 /kometa.py
  --run` on-demand regardless of what the container's PID 1 is doing, so this changes nothing
  about how real runs actually happen. Healthcheck updated to match (`grep -aq 'sleep infinity'`
  instead of `grep -aq kometa.py`).
- **NzbDAV's Repairs tab needs to see the `*arr` apps' own root folders to correlate symlinks
  back to Radarr/Sonarr entries** — `./media/movies`, `./media/shows`, `./media/anime-shows`
  mounted read-only into `nzbdav` at the same `/data/movies`/`/data/shows`/`/data/anime` paths
  those apps already report as their own root folders. Only Radarr and Sonarr are wired into the
  Repairs tab as of this version, so only their root folders are mounted; repairs happen via the
  Radarr/Sonarr API (delete+research), not by touching symlinks directly, so this is read-only.

**v10.10.0 (current) — Letterboxd-to-Radarr added: seven new `stack-letterboxd-radarr*`
commands scrape a Letterboxd film, list, watchlist, watched-films page, filmography, collection,
or the popular-films page and add whatever isn't already in Radarr, with no extra container
(unlike screeny05/letterboxd-list-radarr's Redis-backed adapter service).**

- **`POST /api/arr/radarr/add-from-letterboxd`** scrapes a single film page's TMDb id (every
  matched Letterboxd film links its TMDb entry in the sidebar) and adds it via Radarr's own
  `/movie/lookup/tmdb` + `POST /movie`, defaulting to this stack's real root folder/quality
  profile (`/data/movies`, `Unlimited`) when neither is passed. `/movie/lookup/tmdb` doesn't
  carry a usable `id` for a movie already in the library on the Radarr version this stack runs
  (confirmed live) — `GET /movie?tmdbId=` is the reliable already-added check instead.
- **`POST /api/arr/radarr/add-from-letterboxd-list`** does the same for any Letterboxd
  list/watchlist/watched-films/filmography/collection/popular grid: scrapes every poster's
  `data-item-slug` off the page (up to a hard 10-page / 720-film cap), resolves each film's TMDb
  id, and bulk-adds. URLs containing a robots.txt-disallowed sort/filter segment (`/by/`,
  `/genre/`, `/decade/`, `/films/year/`, `/size/large/`, etc — checked against the live
  `robots.txt`) are rejected before any request goes out. A page-2+ fetch failure stops
  pagination and uses what already loaded instead of failing the whole request.
- **Known limitation: `/films/in/<collection>/` is gated by a genuine Cloudflare JS challenge**
  on that specific path (confirmed live: a bare UA gets a real "Just a moment..." page, not a
  plain 403; a full browser-shaped header set passes intermittently, not reliably).
  `stack-letterboxd-radarr-collection` can fail transiently for reasons that aren't this
  feature's bug.
- **Known limitation: `/films/popular/`'s poster grid is pure client-side JS hydration** with
  zero server-rendered film data at any header combination tried — `stack-letterboxd-radarr-popular`
  currently always reports "no films found." Left pointed at the real URL (not silently swapped
  for a different page) so the failure is honest.
- Seven fish functions (`stack-letterboxd-radarr`, `-list`, `-watchlist`, `-watched`,
  `-filmography`, `-collection`, `-popular`), their bash equivalents, and the two Control Panel
  endpoints above were mirrored to Stackalicious and StackScripts the same session; stack-tui's
  command list was regenerated and its `dist/` binaries rebuilt.

**v10.9.9 — Lidarr, Glances, and Dozzle all removed entirely; Adminer removed with no
replacement; Plex's "Adult" library removed in favor of Stash; Plex bumped to 1.43.3; Control
Panel's UI restyled; a Prometheus + Grafana monitoring stack was researched, proposed, then
cancelled before anything was built; 20 new Control Panel endpoints + matching `stack-*` fish
commands added after a live "why haven't my shows been processed" session.**

- **Lidarr removed entirely** — `docker-compose.yml` service block gone, `config/lidarr`
  deleted, `control-panel/app.py`'s `ARR_APPS`/`QUEUE_ARR_APPS`/`CONTAINER_LABELS`/
  `LOG_LEVEL_APPS`/`ARR_LOG_CONTAINERS` all updated, `LIDARR_API_KEY` gone from
  `.env`/`.env.example`, Prowlarr's Lidarr application-sync entry deleted via its own API,
  NeutArr's Lidarr state/config files deleted. The stale Lidarr row this left in Cleanuparr's
  SQLite `arr_instances` table (no REST endpoint exists for that table) was cleaned up the same
  day — container stopped first to avoid a live WAL-mode write, row and its orphaned parent
  `arr_configs` row deleted directly, zero orphaned rows confirmed in six other referencing
  tables, restarted healthy. The `*arr` app family in
  this stack is now Radarr/Sonarr/Whisparr only. See [The *arr apps](#the-arr-apps) and the many
  places throughout this document that referenced Lidarr as a current app.
- **Adminer removed, no replacement** — `adminer:5.4.2-standalone` (port 8081→8080) service block
  deleted. Briefly replaced with CloudBeaver (`dbeaver/cloudbeaver:24.3.0`) the same day — deployed
  live, confirmed healthy and responding on :8081, but reverted immediately at the user's request
  (not a fit for this stack) before ever reaching real use; `config/cloudbeaver` was also deleted.
  There is currently no web DB GUI in this stack — `docker exec -it <db> psql/mysql ...` again.
  See [Monitoring extras](#monitoring-extras-tautulli).
- **Plex's "Adult" library removed** via the Plex API — files under `./media/adult` were not
  touched, only the Plex library entry. Justification: Stash now fully covers this content
  type's cataloging, so a second, metadata-poor Plex library browsing the same files stopped
  earning its keep. Whisparr still manages the underlying files/root folder; only the Plex-side
  library was dropped. **This changes an architectural statement that used to be true**: Stash
  used to be "an enrichment layer alongside Plex, not a replacement for it" — as of this version
  it's the sole means of browsing/cataloging this content, since Plex no longer has an Adult
  library at all. See [Plex](#plex) and [Stash](#stash-adult-library-cataloging).
- **Plex bumped to `plexinc/pms-docker:1.43.3.10828-00f62d37d`** (from `1.43.2.10687-563d026ea`)
  — pulled, verified the tag exists before repinning, `--force-recreate`d, confirmed healthy and
  running the new version via `/identity`, all six libraries still reachable afterward. Per this
  stack's policy this is a deliberate manual bump, not something Watchtower ever does on its own.
- **Control Panel's dashboard restyled** — replaced the black/phosphor-green "Matrix" theme
  (`matrix-rain.js` canvas layer, neon-green glows throughout `style.css`) with a modern
  slate/blue dark theme and materially tighter spacing (smaller card padding, gaps, and font
  sizes throughout) to fit more status at a glance. `matrix-rain.js` deleted outright, no longer
  referenced from `index.html`. Verified live in a browser after rebuild — quick links, overview
  tiles, primary action cards, the `*arr` app list, and the container grid all confirmed rendering
  correctly with the new theme and zero Lidarr/Bindery/Calibre-Web residue.
- **`dmm-mysql` upgraded 8.4→9.7, live and verified.** A real major-version DB upgrade, not a
  routine bump - took a full `mysqldump --all-databases` backup first, stopped
  `debridmediamanager` (the one dependent app) before touching MySQL to avoid it hitting a
  mid-restart connection failure, then `--force-recreate`d `dmm-mysql`. Server completed both its
  data-dictionary upgrade (`80300`→`90200`) and full server upgrade (`80410`→`90701`) cleanly on
  first boot, no manual `mysql_upgrade` needed. Verified no data loss via exact `COUNT(*)`
  against the three largest tables (`imdb_title_akas`/`imdb_title_basics`/`imdb_title_ratings`) -
  counts came back *higher* than the pre-upgrade baseline (expected, ongoing IMDB ingestion), not
  lower. Restarted `debridmediamanager`; its own `dmm-migrate` one-shot Prisma step reported "The
  database is already in sync with the Prisma schema" and the app came up healthy.
- **`control-panel`'s `uvicorn` bumped 0.34.0→0.51.0** (`requirements.txt`) - rebuilt (it's
  `build:`, a `--force-recreate` alone wouldn't pick up a requirements change), came up healthy,
  spot-checked the dashboard, `/api/version`, and a live `*arr` queue route afterward.
- **Glances and Dozzle removed entirely, no data preserved** — both `docker-compose.yml` service
  blocks deleted, containers stopped and removed live; neither had a config volume, so there was
  nothing on disk to clean up. `control-panel/app.py`'s `GLANCES_URL`, `system_stats()` endpoint,
  and `CONTAINER_LABELS`/`_API_HOST_LABELS` entries for both removed; `static/app.js`'s Quick
  Links entries and the Overview strip's Host CPU/memory/disk/uptime tiles (their only data
  source) removed from both `app.js` and `index.html`. Rebuilt and redeployed Control Panel,
  verified live in a browser afterward.
- **A Grafana + Prometheus monitoring stack was researched and a concrete phased plan drafted,
  then cancelled before any of it was built** — no exporters, no Prometheus, no Grafana were ever
  added to `docker-compose.yml`; the proposal section that briefly existed in this document has
  been removed along with it.
- **20 new Control Panel endpoints + matching `stack-*` fish commands added in one pass**,
  triggered by a real "why haven't my shows been processed" session that took manually querying
  Sonarr's command queue to answer. Highlights: `stack-command-queue-summary` (the aggregate
  version of that manual query), `stack-plex-duplicates` (found - and, in a separate live
  cleanup, removed - ~700GB of redundant movie copies this same session), `stack-recently-added`,
  `stack-cutoff-unmet`, `stack-cleanuparr-strikes`, `stack-dmm-status`, `stack-plex-sessions`,
  `stack-seerr-requests`, `stack-tautulli-history`. New dependencies: `pymysql`+`cryptography`
  (DMM's MySQL needs `caching_sha2_password` support). Two new env vars threaded through to
  Control Panel: `DMM_MYSQL_ROOT_PASSWORD`, `DISCORD_WEBHOOK_URL` (both already existed in
  `.env`, just never passed into this container before). Tautulli's and Seerr's own API keys are
  read live from their mounted config files, not stored anywhere new. All 20 endpoints verified
  live end-to-end; three real bugs found and fixed in the process - `plex_duplicates()` initially
  flagged 74 false positives from a single file appearing twice via this library's two configured
  root paths (fixed by de-duplicating on exact byte size before counting); `plex_sessions()` and
  `plex_recently-added()` both 500'd on their first deploy (assumed XML, `plex_headers()` actually
  requests JSON); and the fish-side `stack-seerr-requests` silently broke on `status`, a real
  fish special variable (same trap class as zsh's `path`) - renamed to `req_status`.

---

🤖 **This stack — architecture, every service, every fix, every line of this document — was built
by [Claude AI](https://www.anthropic.com/claude).**
