# Changelog

Everything done to build and stabilize [The Stack](README.md), in order. All entries so far
are from a single build session.

## 2026-07-05 — initial build

### Added: Core stack scaffolded

- Created `/home/bear/Stack` with `docker-compose.yml`: 11 core services (Prowlarr, Zilean +
  Postgres, Decypharr, Radarr, Sonarr, Lidarr, Readarr, Whisparr, NZBGet, Seerr) plus 7
  optional services behind `--profile extras` (Bazarr, FlareSolverr, Tautulli, Homepage,
  Recyclarr, Unpackerr, Watchtower).
- Verified every image reference against its live registry rather than trusting memory —
  caught several wrong assumptions along the way: LinuxServer doesn't publish a Whisparr
  image (hotio does), Overseerr and Jellyseerr merged into a single `seerr-team/seerr`
  project, and Decypharr's image is still published as `cy01/blackhole`.
- Seeded `config/decypharr/config.json` with Real-Debrid and AllDebrid API keys, `chmod 600`.
- Generated `.env` with PUID/PGID, timezone, and a random Zilean Postgres password + API key.

### Added: Zurg extended for new media types

- Backed up the live `/home/bear/zurg/config.yml` before editing.
- Added `music`, `books`, and `adult` directory groups (regex-based heuristics) ahead of the
  existing `movies` catch-all, so Lidarr/Readarr/Whisparr have Zurg-organized folders to use
  as root folders.
- Restarted `zurg.service` — confirmed the rclone child mount respawned cleanly and the new
  folders appeared under `/mnt/zurg`.

### Fixed: Three issues hit bringing the core stack online

- **Dead Readarr tag** — `lscr.io/linuxserver/readarr:nightly` resolved but pulled an
  empty/inactive manifest (`tag_status: inactive`, `full_size: 0` upstream). Repinned to
  `0.4.19-nightly`, which has real content.
- **Wrong AllDebrid key** — the password field from `rclone.conf` (used for the
  `webdav.debrid.it` bridge) was not accepted by AllDebrid's native API (`"auth apikey is
  invalid"`). Replaced with the correct AllDebrid API key.
- **Decypharr's DFS mount failed to start** — `fusermount3: failed to access mountpoint
  /mnt/decypharr: No such file or directory`. FUSE requires the mountpoint directory to
  exist first, and the container (uid 1000) couldn't create it since host `/mnt` is owned by
  `plex:plex` mode 755. Created `/mnt/decypharr` manually via `sudo mkdir` + `chown`; mount
  succeeded immediately after.

### Added: Full stack online

- All 11 core containers confirmed healthy, no crash-loops, every web UI smoke-tested with a
  real HTTP request.
- Decypharr's initial full sync confirmed progressing (thousands of existing Real-Debrid
  torrents populating under `/mnt/decypharr/Real-Debrid`).
- Brought up all 7 `extras`-profile containers; confirmed healthy and responsive.

### Added: Homepage configured

- `config/homepage/services.yaml` — every service grouped (Requests, Acquisition, Libraries,
  Media Server, Monitoring & Tools).
- `config/homepage/bookmarks.yaml` — Debrid Media Manager library bookmark
  (`debridmediamanager.com/library`).
- Verified both loaded correctly via Homepage's internal `/api/services` and
  `/api/bookmarks` endpoints.

### Added: Recyclarr configured with TRaSH Guide profiles

- Pulled live Radarr/Sonarr API keys from their `config.xml` files.
- `config/recyclarr/recyclarr.yml` — Radarr set to the `HD Bluray + WEB` template, Sonarr set
  to `WEB-1080p` (TRaSH's standard recommended defaults; easy to swap for remux/2160p
  variants later), `chmod 600`.

### Fixed: Dead Recyclarr image tag

- `ghcr.io/recyclarr/recyclarr:latest` is explicitly called out in Recyclarr's own README as
  no longer published. Repinned to the current major version tag, `:7`.
- Verified end-to-end with a manual `recyclarr sync` run: 34 custom formats + 1 quality
  profile synced to Radarr, 31 custom formats + 1 quality profile synced to Sonarr.

### Added: Documentation converted to HTML, then back to Markdown

- `README.md` converted to `README.html`, then converted back to `README.md` per a later
  request. Same for the changelog. Content is equivalent either way — this file is now the
  canonical version.

### Added: Prowlarr populated with indexers

- Created a `flaresolverr` tag and registered the running FlareSolverr container as a
  Prowlarr Indexer Proxy, so Cloudflare-protected public trackers resolve instead of failing
  outright.
- Bulk-added all 88 `public`-privacy indexer definitions Prowlarr ships with via its API
  (private/semi-private trackers need per-user account credentials that aren't available to
  automate, so those were left out) — tagged the ones needing Cloudflare bypass with
  `flaresolverr`, used `forceSave` so temporarily-slow sites didn't block the batch.
- Result: **70 indexers live** (69 public trackers + Zilean, verified via a live API query,
  not just the script's own tally). The dozen that failed even with `forceSave` — `52BT`,
  `AniSource`, `btstate`, `EBookBay`, `ExtraTorrent.st`, `kickasstorrents.to`, `Magnet Cat`,
  `Postman`, `torrent.by`, `Torrent[CORE]`, `showRSS`, `Torrent RSS Feed` — are genuinely
  unreachable/blocked right now, not a config error.
- Added **Zilean** as a Generic Torznab indexer (`http://zilean:8181/torznab`). Hit and fixed
  a path error along the way — Zilean's real endpoint is `/torznab/api`, so `baseUrl` needed
  the `/torznab` segment with `apiPath` left at the default `/api`, not the full path crammed
  into `baseUrl` alone. Connection verified — Prowlarr parsed Zilean's full category list
  (Movies/TV/XXX) back successfully.

### Added: Decypharr wired up as the download client everywhere

- Added Decypharr as a qBittorrent-type download client in Radarr, Sonarr, Lidarr, Readarr,
  and Whisparr — host `decypharr:8282`, username/password set to each arr's own URL/API key
  per Decypharr's documented pattern. All 5 connected and passed their live connection test
  on the first try.
- Confirmed via Decypharr's own `/api/arrs` endpoint that it auto-detected all 5 apps
  (`"source": "auto"`) with correct hosts/tokens — no manual `config.json` editing needed.

### Added: Root folders configured

- Radarr → `/mnt/zurg/movies`, Sonarr → `/mnt/zurg/shows`, Whisparr → `/mnt/zurg/adult` —
  straightforward, v3 API only needs a path.
- Lidarr → `/mnt/zurg/music`, Readarr → `/mnt/zurg/books` — their v1 API additionally
  requires `name`, `defaultMetadataProfileId`, and `defaultQualityProfileId`; used each app's
  shipped "Standard" defaults (Readarr's quality profile set to `eBook` specifically).
- All 5 confirmed `accessible: true` from inside their respective containers before adding.

### Added: NZBGet wired up as a fallback download client

- Added NZBGet (priority 2, behind Decypharr's priority 1) to all 5 arr apps, and separately
  as Prowlarr's own global download client for interactive search.

### Fixed: NZBGet category requirement

- Unlike Decypharr's qBittorrent-style API, NZBGet rejects any category that doesn't already
  exist server-side (`"Category does not exist"`) — arbitrary category names can't just be
  passed through. Renamed NZBGet's 4 default categories and added 2 more directly in
  `nzbget.conf` (`radarr`, `sonarr`, `lidarr`, `readarr`, `whisparr`, `prowlarr`), restarted
  to apply, then all 6 download-client registrations succeeded.

> Note: NZBGet is still on its default credentials (`nzbget` / `tegbzn6789`), used here to
> wire things up. Worth changing since it's reachable on the LAN.

### Added: Zilean tuned for the actual host hardware

- **Zilean**: `Imdb.NumberOfCores=12` (of 16 threads — deliberately not `UseAllCores`,
  leaving 4 for Plex/desktop/other containers on this shared machine) for parallel IMDB
  title-matching; `Imdb.UseLucene=true` for much faster matching at the cost of ~3GB extra
  RAM during resyncs; `DOTNET_gcServer=1` for per-core heaps/parallel GC (the
  throughput-oriented choice vs the default desktop-tuned Workstation GC);
  `DOTNET_GCHeapHardLimit` capped at 3GB inside a 4GB container limit.
- **zilean-postgres**: Postgres ships with defaults sized for a machine with a few hundred MB
  of RAM regardless of host. Tuned `shared_buffers` (512MB), `effective_cache_size` (1.5GB),
  `work_mem` (32MB), `max_parallel_workers` (4), `random_page_cost=1.1` +
  `effective_io_concurrency=200` for the NVMe underneath. Container capped at 2GB / 4 CPUs.
- Verified via live `SHOW` queries and container env inspection after restart — both came up
  clean with no errors.

### Added: Seerr connected to Radarr and Sonarr

- Seerr hadn't completed initial setup (`"initialized": false`) — normally requires an
  interactive Plex OAuth login. Signed in instead via `POST /api/v1/auth/plex` using the
  Plex token already sitting in Zurg's `config.yml`, which authenticated cleanly as the
  account owner and auto-detected the Plex server + both libraries. Called the initialize
  endpoint directly afterward.
- Connected Radarr (`HD Bluray + WEB` profile, `/mnt/zurg/movies`) and Sonarr (`WEB-1080p`
  profile, `/mnt/zurg/shows`) as default servers — both using the quality profiles Recyclarr
  created earlier.

### Fixed: Sonarr required an extra field

- Seerr's Sonarr endpoint rejected the first attempt: `must have required property
  'enableSeasonFolders'`. Added it, succeeded on retry.

### Investigated, no change made: Seerr ↔ Whisparr

- Checked whether Whisparr (or Lidarr/Readarr) could be connected to Seerr the same way —
  Seerr's settings API only recognizes `radarr` and `sonarr` (confirmed via a live 404 on the
  other three). Seerr is a TMDB-based movie/TV frontend with no adult-content data model, so
  there's no coherent connection to make — misusing the Radarr slot for Whisparr would have
  broken real movie requests instead. Left standalone by design, not oversight.

### Added: Published to GitHub

- Converted `/home/bear/Stack` to a git repo. `.gitignore` excludes `.env`, all of `config/`
  (per-app runtime state, several files with plaintext API keys), `usenet/`, and `media/` —
  none of that belongs in git history. Added `.env.example` as a sanitized template.
- Created a private repo at `github.com/WhispersOfJ/media-stack` and pushed. Local git
  identity set to match the GitHub account (scoped to this repo only, not global config).
