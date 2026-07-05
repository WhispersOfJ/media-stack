# The Stack

Docker Compose media-acquisition stack on `192.168.4.105` — indexes, requests, and symlinks
already-cached content from Real-Debrid / AllDebrid into the existing native Plex library.
Nothing here downloads by default except the explicit NZBGet fallback.

## Contents

- [Architecture](#architecture)
- [Directory layout](#directory-layout)
- [What's already done](#whats-already-done)
- [One prerequisite: extend Zurg for new media types](#one-prerequisite-extend-zurg-for-new-media-types-done)
- [Bringing the stack up](#bringing-the-stack-up)
- [Configuration status](#configuration-status)
- [The Usenet caveat](#the-usenet-caveat)
- [Plex library locations to add](#plex-library-locations-to-add)
- [Zilean hardware tuning](#zilean-hardware-tuning)
- [Security note](#security-note)
- [Optional extras reference](#optional-extras-reference)

## Architecture

```
Prowlarr ──indexes──> (your trackers + Zilean's DMM cache-hash list)
   │
   ▼
Radarr / Sonarr / Lidarr / Readarr / Whisparr ──grab──> Decypharr (qBittorrent-compatible API)
   │                                                        │
   │                                                        ├─> Real-Debrid API  (add magnet)
   │                                                        └─> AllDebrid API    (add magnet)
   │
   └──(secondary/fallback)──> NZBGet ──real local download──> ./usenet/downloads

Zurg (native, already running)  → /mnt/zurg/{movies,shows,...}  → read by Plex directly
Decypharr DFS mount (new)       → /mnt/decypharr/{...}          → add as new Plex locations
rclone AllDebrid (native)       → /mnt/all/{magnets,links,...}  → already a Plex location
```

Seerr (formerly Overseerr/Jellyseerr — the projects merged) is the user-facing request page,
talking to Plex + Radarr/Sonarr.

Zilean specifically searches [DebridMediaManager](https://debridmediamanager.com)'s shared
hash-list of content already known to be cached on Real-Debrid/AllDebrid, so grabs from it
come back near-instantly instead of waiting on an uncached download.

## Directory layout

```
Stack/
├── docker-compose.yml
├── .env                          # PUID/PGID/TZ, Zilean DB password + API key
├── README.md, CHANGELOG.md
├── config/<app>/                 # each app's persistent config
├── config/decypharr/config.json  # debrid API keys filled in (chmod 600)
├── config/homepage/{services,bookmarks}.yaml
├── config/recyclarr/recyclarr.yml  # TRaSH profiles for Radarr/Sonarr (chmod 600)
├── usenet/{downloads,incomplete}  # NZBGet's real local downloads
└── media/{movies,shows,music,books}  # local root folders for NZBGet-acquired content
```

## What's already done

- `.env` has PUID/PGID (1000/1000), timezone (America/New_York), a generated Zilean Postgres
  password + API key.
- `config/decypharr/config.json` has your Real-Debrid and AllDebrid API keys filled in,
  `chmod 600`.
- `config/recyclarr/recyclarr.yml` has Radarr + Sonarr API keys and TRaSH template
  references, `chmod 600`.
- Homepage is configured with grouped service links and a Debrid Media Manager bookmark.
- `docker-compose.yml` validates clean (`docker compose config`), all image references
  verified against live registries rather than assumed.
- Full stack (core + extras) is live and healthy — see [CHANGELOG.md](CHANGELOG.md) for the
  issues hit and fixed along the way.
- **Prowlarr** has 70 indexers configured (69 public trackers + Zilean), FlareSolverr wired
  up as an Indexer Proxy for the Cloudflare-protected ones, and NZBGet added as its own
  global download client.
- **Decypharr** and **NZBGet** are both added as download clients (priority 1 and 2
  respectively) in Radarr, Sonarr, Lidarr, Readarr, and Whisparr — Decypharr auto-detected
  all 5 apps.
- **Root folders** are set in all 5 arr apps, pointed at their matching Zurg path.
- **Zilean** is tuned for this host's actual hardware (16-thread CPU, NVMe) rather than left
  on defaults sized for a machine with a few hundred MB of RAM — see
  [Zilean hardware tuning](#zilean-hardware-tuning) below.
- **Seerr** is initialized, signed in to Plex, and connected to Radarr + Sonarr as default
  servers.

## One prerequisite: extend Zurg for new media types (done)

Music/books/adult are routed through Zurg rather than a separate AllDebrid path, so
Lidarr/Readarr/Whisparr need Zurg to organize those into their own folders. This meant
editing the **live** `config.yml` for a service actively serving the Plex library — this has
already been applied and the service restarted cleanly, confirmed by the `music`/`books`/
`adult` folders appearing under `/mnt/zurg`.

For reference, the change made to `/home/bear/zurg/config.yml` (backup kept at
`config.yml.bak`):

```yaml
directories:
  shows:
    group: media
    group_order: 10
    filters:
      - has_episodes: true
  music:
    group: media
    group_order: 15
    filters:
      - regex: /(?i)\b(FLAC|MP3|320kbps|CDDA|Discography)\b/
  books:
    group: media
    group_order: 16
    filters:
      - regex: /(?i)\b(AUDIOBOOK|EPUB|MOBI|AZW3)\b/
  adult:
    group: media
    group_order: 17
    filters:
      - regex: /(?i)\bXXX\b/
  movies:
    filters:
      - regex: /.*/
    group: media
    group_order: 20
```

These regexes are a starting heuristic based on common release-naming conventions, not a
guarantee — anything that doesn't match just falls through to `movies` as it did before, so a
miscategorized item is a quick fix later, not data loss.

Restart command, if the config ever needs tuning again — `zurg.service` runs the `zurg`
binary directly, which spawns its own rclone mount as a child process, so one restart
handles both:

```bash
systemctl --user restart zurg.service
```

> This briefly interrupts `/mnt/zurg` for a few seconds. Do it when nothing's actively
> streaming from Plex. (`rclone-all.service` and `/mnt/all` are unrelated and untouched by
> this.)

## Bringing the stack up

Core services only:

```bash
cd /home/bear/Stack
docker compose up -d
```

Core + optional extras (Bazarr, FlareSolverr, Tautulli, Homepage, Recyclarr, Unpackerr,
Watchtower):

```bash
docker compose --profile extras up -d
```

| Service | URL | Notes |
|---|---|---|
| Prowlarr | http://192.168.4.105:9696 | indexer manager |
| Zilean | http://192.168.4.105:8181 | DMM cache-hash indexer + dashboard |
| Decypharr | http://192.168.4.105:8282 | debrid gateway UI |
| Radarr | http://192.168.4.105:7878 | movies |
| Sonarr | http://192.168.4.105:8989 | TV |
| Lidarr | http://192.168.4.105:8686 | music |
| Readarr | http://192.168.4.105:8787 | books — pinned to `0.4.19-nightly` (LinuxServer's generic `nightly` tag is dead upstream) |
| Whisparr | http://192.168.4.105:6969 | adult |
| NZBGet | http://192.168.4.105:6789 | usenet, real local downloads, fallback path |
| Seerr | http://192.168.4.105:5055 | request frontend |
| Bazarr *(extras)* | http://192.168.4.105:6767 | subtitles |
| FlareSolverr *(extras)* | http://192.168.4.105:8191 | Cloudflare-protected indexers |
| Tautulli *(extras)* | http://192.168.4.105:8182 | Plex stats |
| Homepage *(extras)* | http://192.168.4.105:3000 | dashboard linking every service + DMM library bookmark |

## Configuration status

Everything below was done via each app's API directly (scripted, not clicked through) —
noted as **done** where complete. What's left is a preference call, not a technical gap
(which quality profile to assign where).

1. **Prowlarr** (done): 69 public trackers + Zilean added (see
   [What's already done](#whats-already-done)), FlareSolverr proxy wired up, NZBGet added as
   Prowlarr's own download client. Private/semi-private trackers need your own account
   credentials per-site if you want to add any — those weren't and can't be automated.
2. **Each *arr app** (Radarr/Sonarr/Lidarr/Readarr/Whisparr) (done): Decypharr (priority 1)
   and NZBGet (priority 2, fallback) both added as download clients; root folders set to
   `/mnt/zurg/movies`, `/mnt/zurg/shows`, `/mnt/zurg/music`, `/mnt/zurg/books`,
   `/mnt/zurg/adult` respectively.
3. **Seerr** (done): initialized and signed in to Plex using the existing Plex token already
   on this host (from Zurg's config) rather than the interactive OAuth flow, so it turned out
   scriptable after all. Connected to Radarr (`HD Bluray + WEB` profile, `/mnt/zurg/movies`)
   and Sonarr (`WEB-1080p` profile, `/mnt/zurg/shows`) as default servers.
4. **Decypharr** (done): debrid API keys set, all 5 arr apps auto-detected. `download_action`
   defaults to `symlink` for every arr — no change needed.
5. **Recyclarr** (done): already synced once manually (`HD Bluray + WEB` profile in Radarr,
   `WEB-1080p` in Sonarr) and runs automatically once a day. Still manual: go to each app's
   **Settings → Profiles** and set the new profile as default for your root folders —
   Recyclarr creates the profile but doesn't assign it, since that's a preference call.

> Seerr only recognizes Radarr and Sonarr in its settings API
> (`/api/v1/settings/lidarr|readarr|whisparr` all 404) — it's a TMDB-based movie/TV frontend
> with no data model for music, books, or adult content. Lidarr, Readarr, and Whisparr have
> no Seerr request page and can't get one; they stay standalone, already fully wired up on
> their own via Prowlarr + Decypharr/NZBGet.

## The Usenet caveat

NZBGet is a **real, local download** — the one piece of this stack that isn't debrid/symlink
based, per the explicit ask to include it as a minimum component. Its completed files land
in `./usenet/downloads` on local disk, not in Real-Debrid/AllDebrid's cloud, so:

- It needs its own local root folders (`./media/movies`, `./media/shows`, etc.) since you
  can't write local files into the Zurg/Decypharr virtual filesystems.
- Plex needs additional library **locations** added for these paths if you want NZBGet-
  acquired content to show up (the same way `/mnt/all/magnets` is already an extra location
  on the TV Shows library today).
- It consumes real disk space, unlike everything else in this stack.

Already wired up this way — NZBGet is priority 2 behind Decypharr's priority 1 in all 5 arr
apps, so debrid is always tried first and NZBGet only fires for things neither debrid
service has cached.

## Plex library locations to add

Add these as new library locations in Plex (Settings → Libraries → Edit → Add folder),
matching how `/mnt/all/magnets` is already an extra TV Shows location:

- `/mnt/zurg/music`, `/mnt/zurg/books`, `/mnt/zurg/adult` — new libraries, folders already
  exist and are live.
- `/mnt/decypharr/...` — Decypharr's own organized mount, already mounted and populating.
- `./media/...` — only if you want NZBGet-acquired content visible too.

## Zilean hardware tuning

This host has 16 CPU threads (AMD Ryzen 7 PRO 6850H) but is a shared desktop — Plex, Steam,
and Discord also run here, and free memory sits around 8–9GB in normal use. Zilean and its
Postgres database were tuned deliberately rather than maxed out:

| Setting | Value | Why |
|---|---|---|
| `Zilean__Imdb__NumberOfCores` | 12 | Parallel IMDB title-matching, Zilean's one real CPU-parallel workload. Not `UseAllCores` — 4 threads deliberately left for everything else on the machine. |
| `Zilean__Imdb__UseLucene` | true | Per Zilean's own docs, "massively faster" matching at the cost of ~3GB extra RAM during resyncs. |
| `DOTNET_gcServer` | 1 | .NET Server GC — per-core heaps, parallel collection. The throughput-oriented choice for a backend service; the default Workstation GC is tuned for desktop app responsiveness instead. |
| `DOTNET_GCHeapHardLimit` | 3GB | Bounded inside the container's 4GB memory limit, leaving headroom for non-GC (native) memory. |
| zilean-postgres `shared_buffers` | 512MB | Postgres defaults to 128MB regardless of host — this DB holds the full DMM hash list. |
| zilean-postgres `effective_cache_size`, `work_mem`, `max_parallel_workers` | 1.5GB / 32MB / 4 | Sized for this host rather than left at Postgres's hardware-agnostic defaults. |
| zilean-postgres `random_page_cost`, `effective_io_concurrency` | 1.1 / 200 | Tuned for the NVMe SSD underneath (Postgres defaults assume spinning disks). |

Container limits: Zilean 4GB RAM / 12 CPUs (reservation 512MB / 1 CPU), zilean-postgres 2GB
RAM / 4 CPUs. Both confirmed applied via live `SHOW` queries and container env inspection
after restart.

## Security note

`config/decypharr/config.json` and `config/recyclarr/recyclarr.yml` contain API keys in
plaintext and are both `chmod 600`. This matches how Zurg's own `config.yml` already stores
its Real-Debrid token — consistent with the existing setup, but worth knowing if this host is
ever shared or backed up somewhere less trusted.

## Optional extras reference

| Service | Why you might want it |
|---|---|
| Bazarr | Automatic subtitle download/matching for Radarr/Sonarr libraries |
| FlareSolverr | Lets Prowlarr solve Cloudflare challenges some indexers put up — already registered as an Indexer Proxy and tagged onto the trackers that need it |
| Tautulli | Plex watch-history/stats dashboard |
| Homepage | Single landing page linking every service above, plus a Debrid Media Manager bookmark |
| Recyclarr | Syncs TRaSH-Guides quality profiles into Radarr/Sonarr automatically, once a day |
| Unpackerr | Auto-extracts RAR'd releases (some cached torrents are compressed) |
| Watchtower | Auto-updates all container images on a schedule (4am daily here) |

Not included but worth knowing about: Decypharr can stream Usenet directly via NNTP with no
separate download client (a built-in feature), which would make NZBGet unnecessary if a
fully "nothing touches local disk" setup is ever wanted. Left out here since NZBGet was
requested specifically.
