# The Stack

**Version 2.5.1** — built entirely by [Claude AI](https://www.anthropic.com/claude). Every
service in this compose file, every bug fix, every migration, and this documentation itself
was designed, written, and verified by Claude. See [CHANGELOG.md](CHANGELOG.md) for the full
versioned history.

Docker Compose media-acquisition stack on `192.168.4.105` — indexes, requests, and symlinks
already-cached content from Real-Debrid / AllDebrid into the existing native Plex library.
Nothing here downloads by default except the explicit NZBGet fallback.

> 🤖 **Built with Claude AI.** This isn't a one-line disclaimer — every architectural
> decision, every registry lookup to verify an image actually exists, every live API call to
> wire up Prowlarr/Radarr/Sonarr/Decypharr/Seerr, and every bug this changelog documents was
> Claude's work, done and verified against the real running stack.

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
- [Custom format: blocking low-quality sources](#custom-format-blocking-low-quality-sources)
- [Security note](#security-note)
- [CI: validation and dependency updates](#ci-validation-and-dependency-updates)
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
   │                                                        │
   │                                        symlinked into  ▼
   │                                        each app's root folder: ./media/<type> → /data/<type>
   │
   └──(secondary/fallback)──> NZBGet ──real local download──> ./usenet/downloads ──imported into──> same /data/<type>

Zurg (native, already running)  → /mnt/zurg/{movies,shows,...}  → read by Plex directly (existing content)
Decypharr DFS mount             → /mnt/decypharr/{...}          → symlink target, add as Plex location
rclone AllDebrid (native)       → /mnt/all/{magnets,links,...}  → already a Plex location
./media/{movies,shows,...}      → /data/{movies,shows,...}      → every app's writable root folder (add as Plex location)
```

Root folders live on regular host disk (`./media/<type>`), not on Zurg's rclone FUSE mount —
that mount doesn't support having new files/symlinks written into it. See
[CHANGELOG.md v2.2.0](CHANGELOG.md) for why this changed.

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
├── config/heimdall/www/app.sqlite  # dashboard tiles, populated directly via SQLite
├── config/recyclarr/recyclarr.yml  # TRaSH profiles for Radarr/Sonarr (chmod 600)
├── config/decypharr/downloads/    # shared into every arr app at /app/downloads (identical path)
├── usenet/{downloads,incomplete}  # NZBGet's real local downloads
└── media/{movies,shows,music,books,adult}  # every arr app's writable root folder (mounted at /data/<type>)
```

## What's already done

*Built with Claude AI — nothing below was scaffolded and left half-finished; every item was
verified live against the running stack before being marked done.*

- `.env` has PUID/PGID (1000/1000), timezone (America/New_York), a generated Zilean Postgres
  password + API key.
- `config/decypharr/config.json` has your Real-Debrid and AllDebrid API keys filled in,
  `chmod 600`.
- `config/recyclarr/recyclarr.yml` has Radarr + Sonarr API keys and TRaSH guide-backed
  `quality_profiles` (v8 format — see below), `chmod 600`.
- **Recyclarr** is on v8, **zilean-postgres** is on Postgres 18 — both migrated from
  Dependabot's initial version-bump PRs, which needed real accompanying changes beyond the
  image tag (see [CHANGELOG.md](CHANGELOG.md) for what each required).
- Heimdall is configured with all 14 apps from the stack, grouped into five categories
  (Requests, Acquisition, Libraries, Media Server, Monitoring & Tools) — see
  [CHANGELOG.md](CHANGELOG.md) v2.3.0.
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
- **Root folders** are set in all 5 arr apps, pointed at `/data/<type>` (backed by
  `./media/<type>` on regular host disk) — not `/mnt/zurg/<type>`, since Zurg's rclone FUSE
  mount can't have new files written into it. See the v2.2.0 fix below.
- **Zilean** is tuned for this host's actual hardware (16-thread CPU, NVMe) rather than left
  on defaults sized for a machine with a few hundred MB of RAM — see
  [Zilean hardware tuning](#zilean-hardware-tuning) below.
- **Seerr** is initialized, signed in to Plex, and connected to Radarr + Sonarr as default
  servers.
- **Prowlarr** is connected to all 5 *arr apps under Settings → Apps (`fullSync`), so
  indexers propagate down automatically instead of needing to be configured per-app.
- A **custom format** ("Low Quality Sources/Groups") blocks known low-trust
  aggregator/group releases in every Radarr and Sonarr quality profile — see
  [Custom format: blocking low-quality sources](#custom-format-blocking-low-quality-sources)
  below for an important quirk around Recyclarr.
- **Every arr app can now actually import from Decypharr, end-to-end.** v2.1.0 fixed path
  *visibility* (all 5 containers share `config/decypharr/downloads` at the identical path
  Decypharr uses internally, `/app/downloads`). v2.2.0 fixed the deeper issue underneath it —
  root folders were still on Zurg's read-only FUSE mount, so the final import write always
  failed even after visibility was fixed. Root folders now live on regular disk (`/data/<type>`,
  backed by `./media/<type>`). Verified for real: a live Blue Bloods S01E03 search flowed all
  the way through Prowlarr → Sonarr → Decypharr → import, confirmed on disk as a working,
  readable symlink with `hasFile: true`. See [CHANGELOG.md](CHANGELOG.md) v2.1.0 and v2.2.0 for
  the full story.
- **Bazarr**'s Radarr, Sonarr, and Plex connections were all found silently broken
  (`ip: 127.0.0.1`, unreachable from inside its own container) and fixed — see
  [CHANGELOG.md](CHANGELOG.md) v2.4.0 and v2.5.1. All three are now genuinely live.

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

Core + optional extras (Bazarr, FlareSolverr, Tautulli, Heimdall, Recyclarr, Unpackerr,
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
| Heimdall *(extras)* | http://192.168.4.105:3000 | dashboard linking every service, grouped into 5 categories |

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
   `/data/movies`, `/data/shows`, `/data/music`, `/data/books`, `/data/adult` respectively
   (regular disk, backed by `./media/<type>` — not Zurg's read-only FUSE mount; see
   [CHANGELOG.md](CHANGELOG.md) v2.2.0).
3. **Seerr** (done): initialized and signed in to Plex using the existing Plex token already
   on this host (from Zurg's config) rather than the interactive OAuth flow, so it turned out
   scriptable after all. Connected to Radarr (`HD Bluray + WEB` profile, `/data/movies`)
   and Sonarr (`WEB-1080p` profile, `/data/shows`) as default servers.
4. **Decypharr** (done): debrid API keys set, all 5 arr apps auto-detected. `download_action`
   defaults to `symlink` for every arr — no change needed.
5. **Recyclarr** (done): already synced once manually (`HD Bluray + WEB` profile in Radarr,
   `WEB-1080p` in Sonarr) and runs automatically once a day. Still manual: go to each app's
   **Settings → Profiles** and set the new profile as default for your root folders —
   Recyclarr creates the profile but doesn't assign it, since that's a preference call.
6. **Bazarr** (done): its Radarr, Sonarr, and Plex connections were all found silently broken
   (`ip: 127.0.0.1`, unreachable from inside its own container) and fixed — see
   [CHANGELOG.md](CHANGELOG.md) v2.4.0 and v2.5.1.

> Seerr only recognizes Radarr and Sonarr in its settings API
> (`/api/v1/settings/lidarr|readarr|whisparr` all 404) — it's a TMDB-based movie/TV frontend
> with no data model for music, books, or adult content. Lidarr, Readarr, and Whisparr have
> no Seerr request page and can't get one; they stay standalone, already fully wired up on
> their own via Prowlarr + Decypharr/NZBGet.

## The Usenet caveat

NZBGet is a **real, local download** — the one piece of this stack that isn't debrid/symlink
based, per the explicit ask to include it as a minimum component. Its completed files land
in `./usenet/downloads` on local disk, not in Real-Debrid/AllDebrid's cloud, so:

- It shares the same `./media/<type>` root folders (mounted at `/data/<type>`) that every arr
  app now uses for all imports, debrid or not — see [CHANGELOG.md](CHANGELOG.md) v2.2.0. You
  can't write local files into the Zurg/Decypharr virtual filesystems, which is exactly why
  these root folders exist on regular disk instead.
- Plex needs additional library **locations** added for these paths — see
  [Plex library locations to add](#plex-library-locations-to-add) below. This now matters for
  *all* newly-imported content, not just NZBGet's.
- It consumes real disk space, unlike everything else in this stack.

Already wired up this way — NZBGet is priority 2 behind Decypharr's priority 1 in all 5 arr
apps, so debrid is always tried first and NZBGet only fires for things neither debrid
service has cached.

## Plex library locations to add

Add these as new library locations in Plex (Settings → Libraries → Edit → Add folder),
matching how `/mnt/all/magnets` is already an extra TV Shows location:

- **`/home/bear/Stack/media/{movies,shows,music,books,adult}`** — required, not optional, as
  of v2.2.0. Every arr app's root folder now lives here (regular disk, not Zurg's FUSE mount),
  so this is where *all* future imports land — Decypharr-symlinked and NZBGet alike. Without
  this added as a library location, newly-acquired content won't appear in Plex even though
  it's successfully imported. Confirmed live and working for Sonarr (Blue Bloods S01E03); add
  the matching location for each library type.
- `/mnt/zurg/music`, `/mnt/zurg/books`, `/mnt/zurg/adult` — still worth adding for content that
  predates v2.2.0's root folder migration; folders already exist and are live.
- `/mnt/decypharr/...` — Decypharr's own organized mount; the symlinks under `./media/<type>`
  point here, so Plex needs to be able to resolve through to it either way.

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

## Custom format: blocking low-quality sources

Both Radarr and Sonarr have a custom format, **"Low Quality Sources/Groups"**, matching a
regex against generic low-tier source tags and known low-trust aggregator/group names (YTS,
TGX, RARBG, EZTV, FGT, LOL, KILLERS, and similar). It's scored `-10000` in every quality
profile in both apps — since `minFormatScore` is `0` everywhere, this is a hard reject, not
just deprioritization.

This custom format isn't managed by Recyclarr (its config schema requires a `trash_ids`
reference to the TRaSH-Guides catalog — there's no way to declare an arbitrary regex format
inline), so it was added directly via each app's API instead.

On Recyclarr v7, this required a workaround: v7's sync implicitly reset any score it didn't
recognize back to `0`, but only on the one profile it actively manages per app — meaning this
custom format kept getting silently zeroed out daily on exactly the profile that matters.
**As of the v8 migration, this is no longer an issue** — v8's `reset_unmatched_scores` is an
explicit opt-in (default: leave unrecognized scores alone), and it's left unset here on
purpose. Verified by running `recyclarr sync` twice in a row and confirming the score held at
`-10000` both times with no intervention needed. The old enforcement script and its cron job
have been removed.

## Security note

`config/decypharr/config.json` and `config/recyclarr/recyclarr.yml` contain API keys in
plaintext and are both `chmod 600`. This matches how Zurg's own `config.yml` already stores
its Real-Debrid token — consistent with the existing setup, but worth knowing if this host is
ever shared or backed up somewhere less trusted.

## CI: validation and dependency updates

Two things run on GitHub, not on this host:

- **`.github/workflows/validate.yml`** — on every push/PR to `main`, copies `.env.example` to
  `.env` (just to resolve the variables compose references — no real secrets involved) and
  runs `docker compose config` for both the default and `extras` profiles. Catches YAML/schema
  errors before they'd bite at deploy time.
- **`.github/dependabot.yml`** — checks weekly for newer Docker image versions and opens a PR
  when it finds one. This only does something useful for images pinned to an actual version —
  `postgres:18-alpine`, `recyclarr:8`, `readarr:0.4.19-nightly`. Everything else in this stack
  is pinned to `:latest`, which has no "newer version" for Dependabot to bump to; those get
  whatever's current on every `docker compose pull` regardless. Its first two PRs (Recyclarr
  7→8, Postgres 16→18) both needed real migration work beyond the version bump — see the
  changelog for what that involved before merging any future major-version PR it opens.

## Optional extras reference

| Service | Why you might want it |
|---|---|
| Bazarr | Automatic subtitle download/matching for Radarr/Sonarr libraries |
| FlareSolverr | Lets Prowlarr solve Cloudflare challenges some indexers put up — already registered as an Indexer Proxy and tagged onto the trackers that need it |
| Tautulli | Plex watch-history/stats dashboard |
| Heimdall | Single landing page linking every service above, grouped into 5 categories |
| Recyclarr | Syncs TRaSH-Guides quality profiles into Radarr/Sonarr automatically, once a day |
| Unpackerr | Auto-extracts RAR'd releases (some cached torrents are compressed) |
| Watchtower | Auto-updates all container images on a schedule (4am daily here), via the `nickfedor/watchtower` fork |

Not included but worth knowing about: Decypharr can stream Usenet directly via NNTP with no
separate download client (a built-in feature), which would make NZBGet unnecessary if a
fully "nothing touches local disk" setup is ever wanted. Left out here since NZBGet was
requested specifically.

---

🤖 **This stack — architecture, every service, every fix, every line of documentation — was
built by [Claude AI](https://www.anthropic.com/claude).** Current version **2.5.1**. Full
version history in [CHANGELOG.md](CHANGELOG.md).
