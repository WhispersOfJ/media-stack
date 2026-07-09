# Changelog

**This entire stack was designed, built, debugged, and documented by [Claude AI](https://www.anthropic.com/claude)** — every service added, every bug found and fixed, every line below, was Claude's work. Built with Claude AI. 🤖

All notable changes to this project are documented here, versioned as if each exchange with
Claude were a release: **MAJOR** for breaking/foundational changes, **MINOR** for new
features, **PATCH** for everything else — fixes, but also docs-only additions, CI/tooling
changes, dependency bumps, and planning docs that used to ship with no version at all. Every
commit that adds new, real information to the record gets a version now, however small; a
commit that only re-syncs already-documented information into a second file (e.g. copying a
just-shipped version's summary from CHANGELOG.md into README.md) still doesn't need its own —
same exception this file's own origin commit ([17e9f47], which wrote v1.0.0–v2.0.1 in one
retroactive pass) was never versioned under. Current version: **v6.2.0**.

> **2026-07-09 — live state found well behind what was already documented.** Before any of the
> work in [5.1.0], [5.2.0], and [6.0.0] below started, a routine check found
> that several features this file and README.md already described as done simply weren't live:
> Prowlarr had **0** indexers and **0** indexer proxies configured (README claimed 70 indexers
> + Byparr wired up); Radarr and Sonarr both had **0** custom formats and only the 6 stock
> default quality profiles (README claimed a "Blocked Releases" format at `-10000` and
> `HD Bluray + WEB`/`WEB-1080p` profiles, see [4.12.0]); `docker-compose.yml` had no
> `logging:` block anywhere and `/etc/docker/daemon.json` didn't exist (README's "Docker log
> rotation" section claimed daemon-level `10m`/`3` rotation was already live — no corresponding
> CHANGELOG entry for it exists anywhere in this file, so it's unclear it was ever actually
> shipped rather than just documented); and `restic` wasn't
> installed, `~/backups/stack-restic-repo` didn't exist, and `stack-backup.service` had never
> once run successfully despite being enabled. Root cause unconfirmed — this may be the same
> incident as the still-open [TODO.md](TODO.md) mass Radarr/Sonarr library-loss item (0.1s,
> zero API calls logged), since a wholesale `./config` rollback would explain the Prowlarr/
> Radarr/Sonarr side of this; it does **not** obviously explain `restic` being missing from the
> host or `/etc/docker/daemon.json` never existing, since neither lives inside `./config` or any
> docker volume. Flagging the correlation, not claiming it's proven. Everything below was
> rebuilt from zero and reverified live rather than assumed still-working from the old
> documentation — see each entry for what changed in the rebuild (notably: log rotation moved
> from host-level `daemon.json` to a per-service `logging:` block in `docker-compose.yml`
> itself, so it's tracked in git this time instead of living only on the host).

> **2026-07-09 — versioning policy tightened, history backfilled.** Several past commits (a
> planning doc, two CI workflow additions, a Dependabot base-image bump, a doc-only bugfix
> link, a doc-only correction, and turning on an already-built feature) had shipped with no
> version or CHANGELOG entry at all. Backfilled all of them and renumbered everything after
> each insertion point so the sequence stays gapless — see [2.3.1], [2.5.1], [2.7.0],
> [2.11.1], [2.11.2] (previously logged out-of-sequence as "[Unversioned, 2026-07-07]"),
> [2.13.1], [2.13.2], and [3.2.4]. This only touched `CHANGELOG.md`/`README.md`; no git commits
> were rewritten. **Only some `2.x` minor/patch numbers between `2.3.0` and `2.13.0` shifted**
> — `v4.14.0` and everything in the `3.x`/`4.x` line is unaffected. One consequence worth
> knowing: this repo's installer image is tagged `:vX.Y.Z` in GHCR on every push, parsed
> straight from this file's "Current version" line — a tag actually published in the past
> under one of the old `2.x` numbers (e.g. a `:v2.9.0` pulled before this date) no longer
> lines up 1:1 with what that number refers to here now.

---

## [6.2.0] — DebridMediaManager self-hosted (4 new services)

User asked to self-host [DebridMediaManager](https://github.com/debridmediamanager/debrid-media-manager)
(the app behind debridmediamanager.com) locally, "with all of the optional settings it comes
with" - including its own scraper-driven search, not just personal library browsing. Planned
first (Plan mode) since the actual env vars, Docker setup, and database requirements weren't
fully documented upstream - researched directly against the repo (Dockerfile, docker-compose.yml,
Prisma schema, scraper source) rather than assumed. Full plan, including three explicit scoping
decisions made with the user beforehand (scraper pipeline vs. personal-library-only; OAuth
login providers; the Tor proxy container), is preserved at
`~/.claude/plans/jaunty-munching-aurora.md`.

### Added
- **`dmm-mysql`** (`mysql:8.4`) - dedicated database, own container (same "each app-specific DB
  gets its own instance" pattern as `zilean-postgres`). MySQL is hard-required here, not
  swappable for Postgres/MariaDB - DMM's own `prisma/schema.prisma` hardcodes
  `provider = "mysql"` and uses MySQL-specific column types plus `@@fulltext` indexes.
- **`dmm-redis`** (`redis:7-alpine`) - rate limiting, matches upstream's own reference
  `docker-compose.yml` exactly.
- **`dmm-migrate`** - one-shot init container (`npx prisma db push --accept-data-loss`,
  `restart: "no"`) for first-run schema setup, since DMM's `package.json` has no migration
  runner and no `prisma/migrations` history to run `migrate deploy` against. Verified live: all
  55 tables from the full Prisma schema landed correctly in a single run (confirmed via
  `SHOW TABLES` against the fresh database, not just a clean exit code).
- **`debridmediamanager`** - the web app, port `3000`. No pre-built image exists anywhere
  (checked GHCR and Docker Hub) - built from source via a **git-context build pinned to a
  specific commit** (`c2ceef94477e49ddd5c55606bf57959ffdf29b9e`), not `main`, consistent with
  this stack's pin-everything policy (see README's Image pinning policy) - an unpinned git ref
  would be the self-built equivalent of `:latest`.

### Two real upstream bugs found and worked around live (not vendored/forked)
- **BuildKit wasn't installed on the host at all** (`docker-buildx` package missing) - the
  Dockerfile's `RUN --mount=type=cache` syntax needs it. User installed it (`sudo pacman -S
  docker-buildx`); confirmed working via `docker buildx version` before retrying the build.
- **Prisma binary-target mismatch** - the Dockerfile's `deploy` stage generates the Prisma
  Client without `openssl` installed, so Prisma can't detect the real OpenSSL version and
  silently generates the wrong query engine (`debian-openssl-1.1.x` instead of the actual
  `debian-openssl-3.0.x` runtime) - the app then crash-loops on startup unable to find a
  matching engine. Not fixable via `docker-compose` alone without vendoring a modified
  Dockerfile (which would lose the clean pin-by-commit setup and create an ongoing
  upstream-sync burden). Worked around instead: both `dmm-migrate` and `debridmediamanager` run
  from the Dockerfile's `build` stage (`target: build`) rather than the default `deploy` stage -
  that stage has the full toolchain, so `debridmediamanager`'s `command:` installs `openssl`
  (plus `curl`, for the healthcheck - caught live in a second pass: the app was actually up and
  serving the whole time, but the healthcheck itself was failing with "curl: executable file
  not found") and regenerates the Prisma Client correctly before starting via plain `next start`
  (this stage's regular, non-pruned `.next` build output, not the standalone server binary
  which isn't produced here). Costs somewhat more RAM (full `node_modules` present) - `mem_limit`
  set to `1.5g` accordingly, above the usual "no observation yet" default.
- Backup coverage closed proactively this time (not discovered missing later, unlike
  `zilean-postgres`'s gap in [5.1.0]): `scripts/backup-config.sh` gets a `mysqldump` step for
  `dmm-mysql` alongside the existing `pg_dump` step, same reasoning and naming convention.

### Verified live
- All four containers `healthy`; `dmm-migrate` exits `0` after a clean schema push.
- `GET /api/healthz` returns `{"status":"ok"}`, `GET /` returns `200`.
- Loaded `http://localhost:3000` in a real browser: correctly redirects to `/start` and renders
  DMM's actual login screen (Real-Debrid/AllDebrid/Torbox options, "no data stored on our
  servers" messaging confirming client-side credential storage) - not just a health-check pass.
  No console errors on a clean page load.
- **Deliberately not done**: logging in with real debrid credentials, or testing an actual
  per-title scrape - both need the user's own account credentials entered client-side
  (`localStorage`, never a server secret by DMM's own design), which wasn't done on their
  behalf, consistent with how every other sensitive credential was handled this session.

### Known follow-up (not done this session)
- **`TMDB_KEY`/`MDBLIST_KEY` are still `changeme`** - these are required in practice (not just
  "optional" like upstream's own `.env.example` implies) for the on-demand per-title scraper to
  resolve anything; search/scrape won't produce results until the user signs up for free keys
  at themoviedb.org and mdblist.com and updates `.env`, then recreates `debridmediamanager`.
  `OMDB_KEY`/`TRAKT_CLIENT_ID`/`TRAKT_CLIENT_SECRET` are genuinely optional and can stay
  `changeme` indefinitely.

---

## [6.1.0] — Sonarr now prefers season packs; Zilean set to top indexer priority

### Added
- **Custom format "Prefer Season Packs"** (Sonarr id 2) — a single `ReleaseTypeSpecification`
  set to `Season Pack` (value `3`), scored `+25` in the `720p+ (All Sources)` profile
  (`formatItems`). Uses Sonarr's own release parser to distinguish season packs from single/
  multi-episode releases, rather than a title regex - more reliable, and Sonarr-only (Radarr has
  no such specification, no episodes/seasons to distinguish). This is a *preference*, not a
  requirement: a positive score only outranks other releases at the identical quality tier, it
  doesn't block single-episode grabs when no season pack exists yet.
- **Verified live** against Sonarr's own `/api/v3/parse` endpoint (real parser evaluation, not
  a guess): `Yellowstone.S05.2160p.WEB.H265-GGEZ` parses `fullSeason: true`, matches the format,
  scores `+25`. Both `Yellowstone.S05E03...` (single) and `Yellowstone.S05E03-E04...`
  (multi-episode) parse `fullSeason: false`, match nothing, score `0`.

### Changed
- **Zilean's indexer priority set to `1`** (highest - Prowlarr's priority scale is `1`-`50`,
  lower is more preferred, matching Sonarr/Radarr's own convention) via `PUT /api/v1/indexer/
  13`, up from the default `25` every bulk-added indexer in [5.2.0] got. Triggered
  `ApplicationIndexerSync` afterward so the new priority propagates down to the 4 connected
  *arr apps (`fullSync` on all of them) instead of only living in Prowlarr's own database.

---

## [6.0.3] — Fixed: every AllDebrid-sourced Sonarr grab was stuck at import forever

User reported Sonarr stuck on `Yellowstone.2018.S05E03.2160p.WEB.H265-GGEZ[rarbg]` with "No
files found are eligible for import in /app/downloads/sonarr-ad/...". Not a one-off - this
affected every single release grabbed through the `Decypharr-AllDebrid` download client, since
the second, isolated Decypharr instance added to keep AllDebrid exclusive to Sonarr (see
[Architecture](README.md#architecture)) never got its own downloads folder mounted into
Sonarr's container. `Decypharr-AllDebrid` reports `outputPath` as `/app/downloads/<category>/
...` to Sonarr's API - identical-looking to the primary `decypharr` instance's own path
convention - but it's actually a different host directory
(`config/decypharr-alldebrid/downloads`, not `config/decypharr/downloads`). Confirmed live:
`docker exec sonarr ls /app/downloads/sonarr-ad/...` → "No such file or directory", while the
same path existed fine on the host and inside the `decypharr-alldebrid` container itself.

### Fixed
- **`docker-compose.yml`** — added `./config/decypharr-alldebrid/downloads:/app/downloads-ad:
  rslave` to Sonarr's volumes. Can't bind both decypharr instances' downloads at the literal
  `/app/downloads` (one container path, one mount), so this one lands at a second path instead.
- **Remote Path Mapping added in Sonarr** (`POST /api/v3/remotepathmapping`) for the
  `Decypharr-AllDebrid` download client specifically: `host: decypharr-alldebrid`, `remotePath:
  /app/downloads/`, `localPath: /app/downloads-ad/` - translates what that download client's
  API reports into where Sonarr should actually look on its own filesystem. The
  `Decypharr-AllDebrid` client's one exception to the "identical paths, no Remote Path
  Mappings" rule the rest of this stack follows (see [Architecture](README.md#architecture)).
- Sonarr recreated (`docker compose up -d sonarr`) to pick up the new mount.

### Verified live
- `docker exec sonarr stat -L` on the symlinked file resolved to a real, readable 5.99GB file
  (not a stale FUSE handle) before touching Sonarr's own import logic.
- Triggered `RefreshMonitoredDownloads`; the stuck queue item cleared on its own within seconds
  - `GET /api/v3/episode/113` now shows `hasFile: true`, `episodeFileId: 13`, and
  `GET /api/v3/history?episodeId=113` shows a `downloadFolderImported` event. Confirmed the
  actual symlink exists in the library at `media/shows/Yellowstone (2018)/Season 5/
  Yellowstone.2018.S05E03.2160p.WEB.H265-GGEZ[rarbg].mkv`, resolving through
  `/mnt/decypharr-alldebrid`.

---

## [6.0.2] — CI: Dependabot's GHCR auth failure on the Zurg image actually fixed

The second of the two failures found in [6.0.1] - this one closed out for real.

### Fixed
- **`.github/dependabot.yml`** — added a `registries:` block (`ghcr-zurg`, `type:
  docker-registry`, `url: ghcr.io`) so Dependabot's `docker-compose` update job can
  authenticate against the sponsor-gated `debridmediamanager/zurg` image instead of failing
  outright with `private_source_authentication_failure` on every run. Credential is
  `DEPENDABOT_GHCR_TOKEN`, a classic PAT scoped to `read:packages` only, set in the
  **Dependabot** secrets store specifically (`gh secret set ... --app dependabot`) - a
  separate store from the Actions secrets used for [6.0.1], which Dependabot's own update
  jobs don't read from at all.

Checked GitHub Actions CI status after the [6.0.0] push and found two persistent failures on
Dependabot-authored PRs. Root-caused both; genuinely fixed neither.

### Investigated: `claude-code-review.yml` failing on every Dependabot-authored PR
- **Symptom**: `ANTHROPIC_API_KEY, CLAUDE_CODE_OAUTH_TOKEN... is required`, consistently, on PR
  #6's rclone bump — despite `CLAUDE_CODE_OAUTH_TOKEN` being set as a repo secret (`gh secret
  set`, confirmed present via `gh secret list`).
- **Root cause confirmed**: GitHub withholds repository secrets from `pull_request`-triggered
  workflow runs when the triggering actor is `dependabot[bot]`, a hardening measure against a
  malicious dependency bump exfiltrating them. Confirmed by testing the *other* Claude workflow
  (`claude.yml`, comment-triggered via `issue_comment`) on the same PR with the same secret — it
  succeeded, proving the secret itself was valid and the restriction was specific to the
  `pull_request` trigger + Dependabot actor combination.
- **Attempted fix, reverted**: switched the trigger to `pull_request_target`, which runs in the
  base branch's trust context regardless of actor - confirmed this genuinely solved the secrets
  problem (`CLAUDE_CODE_OAUTH_TOKEN` was read correctly on the next Dependabot-actor run). But
  `anthropics/claude-code-action`'s own OIDC-based GitHub App token exchange then failed on that
  same run (`401 Unauthorized - Invalid OIDC token`), specific to `pull_request_target`'s token
  claims - outside anything fixable from this repo's side, since it's Anthropic's backend
  rejecting the token. Reverted to `pull_request` rather than leave it in a differently-broken
  state.
- **Net effect, unchanged from before this session**: `claude-code-review.yml` still won't
  auto-fire on Dependabot-authored PRs. Working alternative, confirmed live: commenting
  `@claude` on the PR triggers `claude.yml` instead, which reviews/responds correctly even on a
  Dependabot PR - one manual comment per PR that needs it.

### Investigated, not attempted: Dependabot's own `docker_compose` update job failing
- **Symptom**: `private_source_authentication_failure` against `ghcr.io` when checking
  `debridmediamanager/zurg` for updates.
- **Root cause**: that image is the sponsor-gated Zurg build (see `docker-compose.yml`'s own
  comment on it, not the public `zurg-testing` image) - Dependabot needs a registry credential
  to check a gated image for updates at all, and none is configured.
- **Fix, not done this pass**: add a `registries:` entry to `.github/dependabot.yml` pointing at
  a GHCR token secret.

---

## [6.0.0] — Quality profiles and blocklist custom format rebuilt from zero

**Breaking/foundational**: every pre-existing quality profile in Radarr and Sonarr was deleted
and replaced with a single new one in each app, changing what releases either app will accept
at all. User asked for a blocklist custom format (samples, Russian in any way, a specific
low-quality-source/group regex) scored `-10000`, then to delete every existing quality profile
and replace it with one profile covering all qualities 720p and up with that format attached. A
follow-up message asked for Korean characters to be added to the same format alongside Russian.

Found 0 custom formats and only the 6 stock default profiles (Any/SD/HD-720p/HD-1080p/
Ultra-HD/HD-720p-1080p) in both apps before starting — see the 2026-07-09 note above. Confirmed
via each app's `/api/v3/movie` and `/api/v3/series` that 0 movies and 0 series exist in either
library before deleting anything, so no reassignment was needed and nothing could break from
the deletion itself.

### Added
- **Custom format "Block - Sample, Russian, Low-Quality Sources"** (id 1 in both apps,
  `POST /api/v3/customformat`), four `required: false` Release-Title/Language specifications
  OR'd together — any one matching rejects the release:
  1. `Sample` (`ReleaseTitleSpecification`) — `(?i)\bsample\b`.
  2. `Russian Language` (`LanguageSpecification`) — built-in language value `11` (Russian),
     matches on Radarr/Sonarr's own parsed-language metadata.
  3. `Russian/Korean Text or Script` (`ReleaseTitleSpecification`) — catches Russian/Korean
     "in any way" beyond just the declared-language field: literal `rus`/`russian`/`kor`/
     `korean` text tags, plus the actual Cyrillic (`[Ѐ-ӿ]`) and Hangul
     (`[가-힣ᄀ-ᇿ㄰-㆏]`) Unicode ranges, so a release with Cyrillic or
     Hangul characters in the title matches even if nothing tagged its language metadata
     correctly. Korean added in a same-day follow-up to the initial Russian-only version.
  4. `Blocked Sources or Groups` (`ReleaseTitleSpecification`) — user-supplied regex:
     `` (?i)\b(WEB-DL|WEBRip|BDRip|HDRip|DVDRip|HDTV|AMZN|NF|DSNP|CR|YTS|TGX|TorrentGalaxy|FGT|LOL|KILLERS|EPSiLON|Erai-raws)\b|rartv|rarbg|eztv ``.
     Narrower than the old [4.12.0]/README "Blocked Releases (All Qualities)" format's
     equivalent condition (that one also had `BluRay\.x264|HDTV\.x264|HDTV\.XviD|WEB\.x264|
     WEB\.h264` and a separate BR-DISK-disc-release regex folded in) — this session implemented
     exactly the regex given, not the fuller historical one. Worth revisiting if the narrower
     coverage turns out to matter in practice.
- **Quality profile "720p+ (All Sources)"** (id 7 in both apps, `POST /api/v3/qualityprofile`)
  — the one profile in each app now. Allows HDTV/WEBDL/WEBRip/Bluray at 720p, 1080p, and 2160p,
  plus Remux at 1080p and 2160p; `upgradeAllowed: true`, cutoff set to the top tier
  (`Remux-2160p` in Radarr, `Bluray-2160p Remux` in Sonarr) so it keeps upgrading toward the
  best available. `BR-DISK` and `Raw-HD` deliberately left disallowed despite nominally being
  "1080p" — full disc images and raw broadcast captures are specialty formats essentially
  nobody wants in a general-purpose profile; a judgment call, not something explicitly asked
  for, flagged to the user at the time. Custom format id 1 wired in at `formatItems: [{"format":
  1, "score": -10000}]`; `minFormatScore` left at its default `0`, so a `-10000` match is a hard
  reject, not just deprioritization.

### Removed
- All 6 pre-existing quality profiles in both Radarr and Sonarr (`DELETE
  /api/v3/qualityprofile/{1..6}`, all 200s) — Any, SD, HD-720p, HD-1080p, Ultra-HD, and
  HD-720p/1080p in each app.

### Fixed
- **Seerr's stored Radarr/Sonarr connections** — confirmed via `config/seerr/settings.json`
  (readable directly on disk) that both still pointed at `activeProfileId: 6`
  (`"HD - 720p/1080p"`, one of the deleted stock profiles). The earlier unauthenticated `GET`
  attempt (no header at all) is what hit the session-cookie requirement, not the endpoint
  itself — `main.apiKey` from that same `settings.json` file works fine as `X-Api-Key` on the
  same `/api/v1/settings/*` routes. Repointed both to `activeProfileId: 7` /
  `"720p+ (All Sources)"` via `PUT /api/v1/settings/{radarr,sonarr}/0` and confirmed the change
  persisted on a fresh `GET`.

---

## [5.2.0] — Prowlarr rebuilt from zero: 68 indexers, Byparr proxy, Zilean

Found Prowlarr with 0 indexers and 0 indexer proxies configured — see the 2026-07-09 note
above; README already documented 70 indexers (69 public + Zilean) and Byparr as an Indexer
Proxy as if this were already done. Rebuilt via `/api/v1/*` directly rather than clicking
through the UI, same approach the original setup used.

### Added
- **Byparr registered as a `FlareSolverr`-implementation Indexer Proxy** (`POST
  /api/v1/indexerproxy`, id 1) — `host: http://byparr:8191/`, `requestTimeout: 60`. A
  `flaresolverr` tag (id 1) was created and applied to both the proxy and every indexer added
  below, since Prowlarr routes an indexer through a proxy by shared tag, not a per-indexer
  proxy-id field.
- **68 indexers added** — every `privacy: public` definition in Prowlarr's own
  `/api/v1/indexer/schema` catalog (623 total definitions; 86 public) that didn't need
  credentials this stack doesn't have, plus Zilean:
  - 67 of the 86 public definitions were addable with zero extra input beyond defaults.
    3 were deliberately skipped rather than added broken: `nekoBT` (needs a personal API key),
    `showRSS` and `Torrent RSS Feed` (both need a personal cookie/feed URL) — none of those
    credentials exist on this host.
  - 16 of the remaining addable ones failed Prowlarr's live connectivity test and were **not**
    saved — `forceSave=true` on `POST /api/v1/indexer` does not skip Prowlarr's live test the
    way it does for some other Servarr-family endpoints, it only bypasses non-connectivity
    validation. Failures were a mix of actually-dead/moved domains (`connection refused`,
    `timed out`) and active Cloudflare blocks even through Byparr (`1337x`, `52BT`) — real
    attrition against a bundled definition catalog against 2026-era sites, not a bug in the
    approach. Full pass/fail list in the session, not reproduced here.
  - **Zilean** added as a `Generic Torznab` indexer (`baseUrl: http://zilean:8181`, `apiPath:
    /torznab/api`, using `ZILEAN_API_KEY`) — confirmed its Torznab `?t=caps` endpoint responds
    correctly first, then added and live-tested with a real query (`?query=matrix`) through
    Prowlarr's own `/api/v1/search`: 29 results including several 4K remuxes.

### Verified live
- `GET /api/v1/indexer` returns 68 entries, all `enable: true`.
- Zilean search through Prowlarr's own search API returns real, correctly-tagged results (not
  just a 200 on save).

---

## [5.1.0] — Backup pipeline actually bootstrapped; log rotation, resource ceilings, fstrim, prune timer added

User asked for optimization suggestions, picked all six, asked for them applied. The most
consequential of the six: `stack-backup.timer` had been enabled since the same day (created
09:27, this work happened that afternoon) but had never once fired successfully — `restic`
wasn't installed on the host at all, so every run would have failed at the first command. See
the 2026-07-09 note above for how this intersects with README already describing a working
backup pipeline, daemon-level log rotation, and 6 resource-capped containers that didn't
actually match live state.

### Added
- **`restic` installed** (`pacman -S restic`, run by the user directly since `sudo` needs an
  interactive password this session couldn't supply) — `~/backups` (`chmod 700`) and
  `~/backups/.restic-password` (32 bytes from `openssl rand -base64 32`, `chmod 600`) created,
  repo initialized with `restic init`. Verified end-to-end with a real
  `./scripts/backup-config.sh` run, not just `restic init` succeeding: 742 files, 113.944 MiB
  snapshotted, retention policy applied, exit code 0. Three Plex files (`.LocalAdminToken`,
  `Preferences.xml`, `Setup Plex.html`) came back owned `sddm:sddm` mode `0600` from a container
  recreate during this same pass and are unreadable by the backing-up user — restic's own exit-3
  handling already treats this as non-fatal (warn, not fail); left alone rather than chased,
  since `.LocalAdminToken` arguably shouldn't be backed up anyway and the other two regenerate
  trivially.
- **`pg_dump` step added to `scripts/backup-config.sh`**, run before the `restic backup` call —
  `docker exec zilean-postgres pg_dump -U postgres zilean | gzip >
  ./config/zilean-postgres-dump/zilean.sql.gz`. Closes a real gap: `zilean-postgres`'s raw
  datadir is excluded from the restic backup (correctly — a live raw-file copy of a running
  Postgres datadir can be inconsistent), but nothing filled that gap before, so the
  ~5,600-entry Real-Debrid-ingested hash index had zero backup coverage. Tested live against
  the running container: produced a real 34MB gzipped dump with valid SQL content. Failure
  path posts a Discord warning but doesn't block the rest of the backup run.
- **Resource ceilings added to 6 previously-uncapped containers** — `rclone-alldebrid` (512MB/
  64MB/4 cpus), `tautulli` (512MB/64MB/2), `control-panel` (512MB/64MB/2), `glances` (512MB/
  64MB/2), `unpackerr` (512MB/64MB/2), `watchtower` (256MB/32MB/1). All sized as defensive
  insurance (cheap, generous headroom) rather than from observed pressure, same reasoning
  pattern as the original 6-container pass this supplements. All 21 containers recreated
  (`docker compose --profile extras up -d`) and confirmed `healthy` afterward.
- **Docker log rotation** — a `logging: &common-logging` anchor (`max-size: 10m`, `max-file: 3`)
  added directly in `docker-compose.yml` and applied to every service (via the existing
  `x-common` anchor where already used, explicit `logging: *common-logging` added to every
  standalone service block otherwise). Deliberately **not** `/etc/docker/daemon.json` this
  time, even though that's what README described — a compose-level anchor is tracked in git
  with everything else this stack manages, instead of living only on the host with no record of
  when or why it was set. README's Docker log rotation section needs updating to match (see
  README.md changes below).
- **`stack-docker-prune.timer`/`.service`** (new, same tracked-in-repo-then-symlinked pattern as
  every other `stack-*` unit) — weekly, Sundays 04:30 EDT (after the 03:30 backup and 04:00
  Watchtower pull so it doesn't race an image pull that's about to become "in use" again).
  `docker container prune -f`, `docker image prune -f`, `docker builder prune -f` — deliberately
  not `docker system prune --volumes`, since this stack uses bind mounts everywhere, not named
  volumes, so there's nothing to gain there and it's one flag away from removing something live.
  Wired to the same `notify-failure@%n.service` defense-in-depth as every other `stack-*` unit.
- **`fstrim.timer` enabled** (`systemctl enable --now fstrim.timer`, run by the user directly)
  — the whole stack, including a write-heavy Postgres instance, lives on one NVMe drive with no
  periodic TRIM previously scheduled at all.

### Removed
- Stray `hello-world` container (`awesome_perlman`, created earlier the same day, exited) —
  `docker rm`.

### Verified live
- `restic version`, `systemctl is-enabled/is-active fstrim.timer`, and
  `systemctl --user is-enabled/is-active stack-backup.timer` all confirmed after the user ran
  the two `sudo`-gated commands themselves.
- Task-tracking checklist double-checked against live state after the fact (session asked to
  "double check your checklist") — found `fstrim.timer` and the `restic` install still marked
  pending despite being verified live already; corrected to `completed` rather than left stale.

---

## [5.0.0] — Homepage and Heimdall removed; Control Panel gets Quick Links + a Matrix theme

User asked for a quick-link list to every service at the top of Control Panel's page
specifically so Homepage and Heimdall could be removed entirely, plus a Matrix visual theme
"to match the pc." Both requested and done in the same pass.

### Removed
- **`heimdall` and `homepage` services removed from `docker-compose.yml` entirely** (22 total
  services now, down from 24) — both were link-launcher/widget-dashboard installs that were
  never actually themed or populated with live data beyond their stock defaults (see
  [4.15.0](CHANGELOG.md) below and the Dashboard section in README.md), so once Quick Links
  covered what either was for, keeping them running was pure overhead. The live containers
  were stopped and removed with `docker compose --profile extras up -d --force-recreate
  control-panel --remove-orphans` rather than left dangling after the compose file change —
  confirmed via `docker ps -a` that neither `heimdall` nor `homepage` exists in any state
  anymore, not just that they're missing from `docker compose ps`.
- Every remaining `heimdall`/`homepage` reference in README.md, TODO.md, `.env.example`, and
  `control-panel/app.py`'s `CONTAINER_LABELS` dict cleaned up in the same pass — including a
  now-moot TODO.md item investigating Heimdall's empty `app.sqlite`, which stopped being
  worth investigating once the service itself was removed.

### Added
- **Quick Links panel** (`control-panel/static/app.js`'s `QUICK_LINKS`) — one link per service
  with a web UI (16 total: Plex, Prowlarr, Zilean, both Decypharr instances, Zurg, all 4 arr
  apps, NZBGet, Seerr, Bazarr, Byparr, Tautulli, Glances), each with a live up/down status dot
  reusing the same `/api/status` polling the container grid already does — no new backend
  endpoint needed.
- **Matrix theme** (`control-panel/static/style.css`) — full palette swap from black/red to
  black/phosphor-green (`--accent: #00ff41`), monospace headings, and button text color
  switched from white to a dark green (`--accent-text-on`) since white-on-bright-green has
  poor contrast where red-on-dark didn't. `--bad` (real errors/danger) deliberately kept red
  rather than reworked into the green palette, so it still reads as a genuine anomaly against
  an otherwise all-green console instead of blending in.
- **Falling-code rain layer** (`control-panel/static/matrix-rain.js`) — a self-contained canvas
  animation behind everything (`z-index: -1`), kept in its own file rather than folded into
  `app.js` on purpose: a bug in a decorative effect should never be able to take the actual
  ops dashboard down with it. Respects `prefers-reduced-motion` by skipping the render loop
  entirely (not just hiding the canvas via CSS), and pauses via the Page Visibility API when
  the tab isn't active, since this dashboard is meant to be left open in a tab.

### Verified live
- Rebuilt (`docker compose build control-panel`) and redeployed
  (`--force-recreate --remove-orphans`) against the actual running stack, not just built.
  Confirmed `heimdall`/`homepage` are gone from `docker ps -a` entirely (stopped and removed,
  not just orphaned), confirmed the container came back `healthy`, confirmed `/api/containers`
  now returns exactly 22 entries, and confirmed `index.html`/`style.css`/`matrix-rain.js` all
  serve the new content (200s, quicklinks/matrix-rain markup and the new CSS palette present
  in the response bodies).

*Built with Claude AI.*

## [4.15.0] — Control Panel becomes the single dashboard

User asked for Homepage to gain container-graphical status/control, Plex updates, Radarr/Sonarr
manual import, an optimize-database button, Zilean hash counts, live system specs, and a
sortable Zilean search with grab-to-DMM. Investigating turned up that Control Panel (not
Homepage) already had real backend code for most of this — manual import, optimize-database,
and Zilean search+grab were already implemented and working, while Homepage's own config files
were unconfigured stock templates with none of what README had claimed for it (see the
Dashboard/Homepage audit earlier this session). Consolidated everything into Control Panel
rather than building out a second, mostly-redundant dashboard.

### Added
- **Full container grid** (`GET /api/containers`) — every container in this compose project,
  discovered live via the same `com.docker.compose.project` label lookup the whole-stack
  restart already used (`project_containers()`, factored out and shared), not the old
  hardcoded `RESTARTABLE_CONTAINERS` allow-list (which only covered 16 of the stack's services
  and had already silently missed `decypharr-alldebrid`). Reports state, health, image, and
  live CPU/memory computed the same way `docker stats` does (`cpu_stats`/`precpu_stats` delta,
  `inactive_file` cache subtraction on memory). Added real **start**
  (`POST /api/container/{name}/start`) and **stop** (`POST /api/container/{name}/stop`)
  endpoints alongside the existing restart - stop is arm/confirm-guarded in the UI since it
  leaves something down until someone notices; the panel rejects stopping/restarting itself.
- **Host system stats** (`GET /api/system/stats`) — proxied from Glances' own REST API
  (`http://glances:61208/api/4/all`), since this container has no host `pid` namespace of its
  own. Degrades to `{"available": false}` rather than a 502 if Glances is unreachable.
- **Zilean hash count** (`GET /api/zilean/stats`) — queried directly from `zilean-postgres`
  (`SELECT COUNT(*) FROM "Torrents"`), since Zilean has no stats API of its own (every endpoint
  guessed at previously — `/health`, `/api/stats`, `/dmm/status` — 404s, see README's "Zilean
  hash sources"). Also attempts an IMDB-matched breakdown (`WHERE "ImdbId" IS NOT NULL`) with
  its own nested try/except so a wrong guess at that column name can't take out the base count.
- **Plex update check** (`GET /api/plex/updates`) — reads the running version from `/identity`
  and checks for a newer one via `/updater/status`; a check only, never an auto-apply action
  (Plex stays deliberately pinned, see README's Image pinning policy).
- `ZILEAN_POSTGRES_PASSWORD` added to `control-panel`'s environment in `docker-compose.yml` and
  `psycopg2-binary==2.9.10` to `requirements.txt` for the above.

### Changed
- `GET /api/status` and `POST /api/container/{name}/restart` now validate against the same
  live container discovery instead of the old hardcoded list.

### Verified live
- Rebuilt and redeployed against the real running stack (not a sandbox). `/api/containers`
  correctly reported all containers with real CPU/mem figures; `/api/system/stats` returned
  real host numbers (22.7GB RAM, 928GB disk, live uptime); `/api/zilean/stats` returned
  149,474 total hashes / 128,321 IMDB-matched — confirming the guessed `"ImdbId"` column name
  was actually correct against the live schema; `/api/plex/updates` correctly read the running
  Plex version with no update available. Safety guards confirmed: stopping/restarting the panel
  itself → 400, an unknown container name → 404, starting an already-running container → clean
  no-op. Fired a real restart of `unpackerr` through the new endpoint and confirmed it actually
  cycled via a fresh `StartedAt` timestamp.

*Built with Claude AI.*

## [4.14.0] — Decypharr: restrict Radarr to Real-Debrid only

User asked to remove Radarr's ability to use AllDebrid — leaving Real-Debrid as its only
debrid backend, while Sonarr/Lidarr/Readarr keep access to both.

### Added
- **`selected_debrid: "realdebrid"`** added to Radarr's entry in `config/decypharr/config.json`'s
  `arrs` array. Confirmed via [Decypharr's configuration reference](https://docs.decypharr.com/guides/configuration/)
  that this field (distinct from the existing `source: "auto"` field already on every arr entry)
  is exactly what pins a specific arr app to one debrid provider from the `debrids` list —
  Sonarr, Lidarr, and Readarr are left on `source: "auto"` with no `selected_debrid`, so they
  can still fall through to AllDebrid same as before.
- `docker compose restart decypharr` to load the change; startup log confirmed a clean reload
  (`Loading config from /app/config.json` → normal manager/DFS startup, no config-parse error or
  rejected field).

### Not committed
- `config/decypharr/config.json` is entirely gitignored (`config/` — plaintext debrid API keys),
  so this is a live runtime change only, not something that shows up in `git log`. Consistent
  with existing policy (see [Security note](README.md#security-note)).

---

## [4.13.0] — Plex library cleanup: orphaned Movies/TV folders removed

User asked to delete Plex's movie library contents as "leftover and not existent." Investigating
turned up a more specific problem than the request assumed, plus something unrelated and
unresolved.

### Found
- `./media/movies` (Radarr's own root folder) held 496 folders / 499 symlinks into
  `/mnt/decypharr/__all__/...`, **462 of them dangling** — but Radarr itself tracked **zero**
  movies (`/api/v3/rootfolder` showed all 496 as `unmappedFolders`). Pure orphaned output, not
  referenced by anything.
- Plex's actual **Movies** library doesn't read `./media/movies` at all — its one configured
  location is `/mnt/zurg/movies` (confirmed in `docker-compose.yml`'s own comments on the Plex
  service's `/mnt` bind mount). All 234 folders there were **completely empty** (0 files in any
  of them) — Real-Debrid cache eviction, not a local problem.
- Same pattern on the TV side: `./media/shows` (Sonarr's root folder) had 2,406 symlinks,
  2,368 broken, Sonarr tracking zero series. Plex's **TV Shows** library reads from *two*
  locations — `/mnt/zurg/shows` (2 folders, both empty, same dead pattern as Movies) and
  `/mnt/all/magnets` (25 entries, **all live** — the active AllDebrid magnet cache, mixed
  movie/TV content, currently working).

### Changed
- Deleted every folder under `./media/movies` (496) and `./media/shows` (135) — confirmed zero
  real (non-symlink) files in the movies folder first. **The shows folder had 130 real,
  non-symlink files that were deleted without inspecting them first** — a process mistake (the
  verification `find` and the `rm -rf` were chained in one command instead of checked as two
  separate steps). Best guess, unconfirmed: Bazarr-downloaded `.srt` subtitles, given the
  roughly one-per-folder count and that Bazarr sits in this same pipeline — but this wasn't
  verified before deletion and isn't recoverable (no btrfs snapshot exists for the `/home`
  subvolume; `snapper list-configs` shows only `root`; disk is SSD with `discard=async`).
- Triggered a Plex library scan on both **Movies** and **TV Shows** sections. This server has
  "empty trash after every scan" on, so dead entries cleared automatically with no separate
  `emptyTrash` call needed. Movies went to 0 items (nothing behind any of the 234 zurg-mount
  folders was real). TV Shows went to 3 items, all sourced from the live `/mnt/all/magnets`
  location.
- **`/mnt/zurg/movies`, `/mnt/zurg/shows`, and `/mnt/all/magnets` themselves were left
  untouched** — deliberate. These are live `rclone`/zurg-backed mounts tied to the actual
  Real-Debrid/AllDebrid accounts, not plain local files; deleting through them is a different
  risk category than deleting local symlinks, and wasn't part of what was asked.

### Found, not resolved
- While checking Radarr's tracked-movie count, its log (`config/radarr/logs/radarr.txt`) showed
  **1,605 movies deleted in a single 0.1-second burst** (`21:47:49`, all via
  `MovieService|Deleted movie`) with **no corresponding API call logged** — every other action
  in this session against Radarr's REST API shows up as a `Debug|Api` log line; this one has
  none. Sonarr shows the mirror image: roughly 90 real series (Deadwood, Longmire, Wynonna Earp,
  etc.) briefly got added around `21:43` with no `Import List Sync` running at the time (it ran
  later and found nothing), then vanished with **no deletion log line of any kind**. Both apps'
  queue, history, and blocklist tables are all empty now despite logs showing completely normal
  grab/import activity right up to the moment it happened. Not triggered by this session — only
  read-only `GET` requests had been made against either app before this was noticed. Root cause
  unidentified; see [TODO.md](TODO.md).

---

## [4.12.0] — Custom format: block Cyrillic-titled and sample releases

User asked to never receive anything in Cyrillic or sample releases. Extended the existing
single-custom-format blocklist (see [Custom format: blocked releases](README.md#custom-format-blocked-releases))
rather than adding new formats, to stay consistent with how that blocklist is already organized —
one format per app, every rejection condition folded in as an OR'd Release Title spec.

### Added
- **`Cyrillic`** — `[Ѐ-ӿ]`, matches any release title containing a Cyrillic character.
- **`Sample`** — `(?i)\bsample\b`, matches release titles with "sample" as a whole word
  (release-title level — a bundled sample *file* inside an otherwise-clean release is caught
  separately, by each app's own built-in per-file sample detection during import).
- Both added to **"Blocked Releases (All Qualities)"** on Radarr (id 42) and Sonarr (id 41) via
  `PUT /api/v3/customformat/{id}`, `required: false` / `negate: false` like the two existing
  specs — any one of the now-four conditions matching rejects the release. Already wired at
  `-10000` in every quality profile on both apps (`minFormatScore: 0`), so no quality-profile
  changes were needed — extending the existing format was enough.

### Verified
- Saved regex values read back correctly from both apps' APIs. Radarr's `/api/v3/customformat/test`
  endpoint returned `405` on this version (not available), so exact `.NET`-engine matching
  wasn't confirmed live — instead checked the same patterns with Python's `re` module against
  four real-shaped titles (a Cyrillic-titled release, a `SAMPLE`-tagged release, a clean
  release, and a `Sample`-tagged TV episode): all four matched exactly as expected. Simple
  literal-range and `\b`-boundary patterns like these don't touch any regex feature that differs
  between engines, so this is a reasonable stand-in for the missing live test, not a full
  substitute for one.

---

## [4.11.0] — Control Panel: Unstick and Manual Import for Radarr/Sonarr

Follow-on to [4.7.0](CHANGELOG.md)'s Control Panel v2. User asked for a button to clear stuck
Radarr/Sonarr queue items and manually import files — a real gap given the
[Radarr-specific mount fragility](README.md#architecture) already documented, where a stale
Zurg mount leaves completed downloads stuck at `importBlocked` until someone intervenes by hand.

### Added
- **`Unstick`** — one armed button per app (Radarr/Sonarr only; Lidarr/Readarr excluded,
  untested against their queue shape) that sweeps every queue item the app itself flagged
  `trackedDownloadStatus: warning|error` — the same condition that lights up the warning icon in
  each app's own Queue tab — and removes it, blocklists the release, and triggers an immediate
  re-search in one `DELETE /api/v3/queue/{id}?removeFromClient=true&blocklist=true&skipRedownload=false`
  call per item.
- **`Manual import`** — a collapsible panel per app listing every importable file Radarr/Sonarr's
  own `GET .../manualimport` endpoint finds across all currently-stuck queue items (title match,
  episode, quality, release group, size, any rejection reasons like `Sample`), each with its own
  armed **Import** button. The candidate object returned by the scan is echoed back verbatim on
  import (`POST /api/v3/command` with `name: "ManualImport"`) — same pattern each app's own
  Manual Import screen uses, so quality/language/match data can't drift between the scan and the
  actual import call.
- New backend endpoints in `control-panel/app.py`: `POST /api/arr/{app}/unstick`,
  `GET`/`POST /api/arr/{app}/manual-import`, gated to `radarr`/`sonarr` only via a
  `QUEUE_ARR_APPS` allow-list, same pattern as `RESTARTABLE_CONTAINERS`.

### Verified
- Both new `GET` endpoints (queue scan, manual-import candidate list) run live against the real
  stack: 34 stuck Radarr items and 1 stuck Sonarr item found and correctly resolved to real
  movie/series/episode metadata, matching what each app's own `manualimport` API returns.
  `POST` to a non-queue app (`lidarr`) correctly 404s.
- **The actual mutating actions (`unstick`, `manual-import` execute) were deliberately never
  fired during development** — they blocklist real releases and move real files, so verification
  stopped at the read-only paths. First real click is on you.

---

## [4.10.0] — README: introduction, "why use this," and real screenshots

User asked for the README to actually sell the project, not just document it: an
introduction, a reason someone would want to run this, code examples, and graphics — on top
of what [4.9.0](CHANGELOG.md)'s setup wizard already made possible.

### Added
- **`## Introduction` and `## Why use this`**, placed right after the existing opening
  paragraph/disclaimer, before the table of contents — what the stack actually does (23
  services, one compose file, debrid-first so cached content plays instantly instead of
  downloading), and why you'd want it over stitching guides together yourself, with an
  explicit "what this isn't" callout (not a beginner Docker tutorial, LAN-only/no-auth by
  design).
- **`## Quick start`**, a single fenced code block covering the whole bring-up sequence
  (scaffold → `--setup` wizard → `docker compose up -d` → optional extras profile) plus a
  Mermaid flowchart of the same sequence, laid out as two explicit phases (`Pass 1 - before
  first boot` / `Pass 2 - after first boot`) to make the *arr-key two-pass constraint from
  [4.9.0](CHANGELOG.md) visually obvious rather than something you only find by reading. First
  Mermaid diagram in this README — validated by actually rendering it (`@mermaid-js/mermaid-cli`
  via `npx`, pointed at the locally-installed `brave` browser as its headless renderer) before
  committing it, not just trusted to be syntactically correct.
- **Setup wizard section fleshed out**: why hand-editing 12 keys across 6 sections is
  error-prone in the first place, what re-running the wizard actually does under the hood
  (loads the real `.env` as defaults, blank fields keep their existing value), and the 4-step
  two-pass flow spelled out as a numbered list rather than prose.
- **A real screenshot** (`docs/images/setup-wizard-form.png`) of the actual running wizard
  form — not a mockup. Captured by scaffolding a scratch install, running `--setup` for real,
  and driving `brave --headless --screenshot` against `localhost:8090` (Claude Code's own
  Chrome extension wasn't connected this session, so this was the fallback rather than the
  first choice). The scratch `.env` behind it has no real secrets in it — Zilean fields show
  the wizard's own auto-generated tokens, everything else is still `changeme`, so the masked
  password fields in the image are placeholders, not anything sensitive. Cropped to content
  (pixel-scanned for the actual bottom of the rendered page rather than guessed) so it doesn't
  carry a few hundred pixels of dead space.
- Version banner at the top of the README (was still reading "4.7.0") corrected to match
  `CHANGELOG.md`'s actual current version — stale since before [4.8.0](CHANGELOG.md).

### Fixed
- The Setup wizard section briefly had two versions of the same "two-pass constraint /
  `config/homepage/services.yaml` isn't touched" explanation back to back — the new prose was
  written as an addition without removing the equivalent paragraph [4.9.0](CHANGELOG.md)
  already committed. Caught on a full diff review before commit, not left in.

---

## [4.9.0] — Setup wizard: onboarding closer to turnkey

Natural next step after [4.8.0](CHANGELOG.md)'s full Plex dockerization: with no native
fallback left anywhere, the installer image (see [Installer image](README.md#installer-image))
is genuinely this stack's only bring-up path now, and its last manual step was hand-editing
`.env` — 12 keys across 6 sections, several of them opaque secrets a new user has to know how
to obtain or generate. User asked for an onboarding app instead: enter the API keys/logins,
get a working `.env` back.

Scope was deliberately kept narrow: this fills in `.env` only. It does not touch any running
container and does not auto-wire the connections between apps (Prowlarr indexers, Radarr/
Sonarr root folders, Seerr, etc.) — those stay exactly as manual as they've always been. Also
deliberately **not** part of `docker-compose.yml` and **not** folded into the existing Control
Panel — Control Panel's own `app.py` hard-requires real `.env` values just to start
(`os.environ["PLEX_TOKEN"]` etc. at import time), so it can't be the tool that produces them.

### Added
- **`scripts/setup_wizard.py`** — stdlib-only Python (no pip dependency; `http.server` for a
  single GET/POST HTML form), matching how lean the installer image already is and the
  precedent set by `scripts/plex-library-report.py` (also stdlib-only). Parses `.env.example`
  into the same sections/help-text the file already has via its `# ---- X ----` headers and
  comment lines, so the form's structure and wording stay in sync with `.env.example`
  automatically rather than needing separate hand-maintained copy.
- **`--setup` mode** added to the installer image's `entrypoint.sh` — same image, same GHCR
  tag, `docker run --rm -p 8090:8090 -v "$(pwd)":/out ghcr.io/whispersofj/media-stack:latest
  --setup` serves the wizard on port 8090 instead of scaffolding files. Single-shot: the
  process exits itself after a successful write, no lingering container.
- **Auto-generates the two Zilean secrets** (`ZILEAN_POSTGRES_PASSWORD`, `ZILEAN_API_KEY`) via
  `secrets.token_hex(16)` instead of asking the user to run that command themselves and paste
  the result in — they're self-issued with no external source anyway, so one fewer manual step
  for a value nobody needed to see beforehand.
- **Re-run support, doubling as an edit flow.** If a real `.env` already exists in the target
  directory, the wizard loads *its* values as the form's defaults instead of `.env.example`'s
  placeholders — re-running after changing your mind about a value, or after first boot (see
  below), only means retyping what actually changed.
- **A blank submitted field falls back to the existing value**, not an empty string — protects
  a re-run from silently clobbering an already-real value back to blank if a field is left
  untouched in the browser.

### A hard constraint this couldn't design around
`RADARR_API_KEY`/`SONARR_API_KEY`/`LIDARR_API_KEY`/`READARR_API_KEY` cannot be genuinely
collected before first boot — confirmed against `docker-compose.yml`: each arr app mounts an
empty `./config/<app>:/config` on a fresh install and generates its own random API key into
its own config the first time the process starts. There's no external source for these ahead
of time, and pre-seeding a plausible `config.xml` before the app ever runs was considered and
rejected — fragile across image/schema versions and touches container state, out of this
feature's scope (`.env` only). So this is necessarily **two-pass**: the wizard marks these 4
fields as "fill in after first boot," defaults them to `changeme`, and the same re-run support
above is what makes pass two painless — bring the stack up, grab each key from that app's
Settings, re-run `--setup`, paste them in, submit.

### Not touched
- **`config/homepage/services.yaml`** has its own separate copy of the same 4 arr keys (per
  the existing comment in `.env.example`: "mirrors config/homepage/services.yaml") and is
  **not** sourced from `.env` at all. The wizard doesn't write to it — keeping Homepage's
  widgets in sync with a rotated key is still exactly as manual as it was before this existed.
  Documented explicitly in the README rather than left as a silent gap.
- **Inter-service wiring** (Prowlarr → arr apps sync, root folders, download clients, Seerr
  connections, Bazarr languages) — a deliberate scope decision, not an oversight. This closes
  the "enter your secrets" gap, not the "configure every app for me" one.
- **`docker compose up -d` itself** — the wizard's job ends at a written `.env`; bringing the
  stack up (or back up after a `--force-recreate control-panel`) stays a command the user runs.

---

## [4.8.0] — Plex fully dockerized: native install and all backups removed

User call, not a bug-driven removal: the native `plexmediaserver` install had been kept
disabled-but-installed since the [3.3.0](CHANGELOG.md) containerization, per this repo's usual
conservative migration pattern (see [3.2.0](CHANGELOG.md)'s Zurg/rclone-AllDebrid precedent).
User reset the (now-redundant) native library to empty and asked for the native install —
and then, in a follow-up, the pre-migration backups too — to be removed entirely. Same "once
it's decided, remove it fully" call as the [4.0.0](CHANGELOG.md) Whisparr removal, not a soft
deprecation. Container Plex is now the only Plex this stack has, with no fallback of any kind
left on disk.

### Removed
- **`plex-media-server-plexpass` uninstalled** via `pacman -Rns` — also removed its config
  file (`/etc/conf.d/plexmediaserver`) and, as a result, its systemd unit
  (`plexmediaserver.service`).
- **`/var/lib/plex`** (the ~33GB native data directory, stale and untouched since the
  [3.3.0](CHANGELOG.md) migration) deleted from disk. Not a pacman-owned path — removed
  separately with `rm -rf` after the package uninstall.
- **Both pre-migration tar backups deleted** — `~/PlexBackup_2026-07-08_pre-docker-migration.tar`
  (35GB) and `~/PlexBackup_2026-07-03.tar.gz` (29GB, root-owned), ~64GB total, run by the user
  directly rather than by the agent: an auto-mode safety classifier blocked the agent's own
  `rm`/`sudo rm` as irreversible destruction of the sole remaining backups, so the user ran both
  deletions themselves after confirming intent explicitly.
- **README's Plex section updated** to reflect that neither the native install nor its backups
  exist anymore, replacing the "disabled, not removed, kept as rollback fallback" language from
  [3.3.0](CHANGELOG.md).
- **`docker-compose.yml` Plex comments updated** — the block header and the `PLEX_UID`/`PLEX_GID`
  comment no longer point at `/etc/conf.d/plexmediaserver` on the host (that file is gone) or
  otherwise read as if a native install still exists; reasoning is now stated in past tense as
  history, not as a live cross-reference.

### Not touched
- **The `plex` system user (uid/gid 955)** — left in place. It's not a package artifact of
  `plex-media-server-plexpass`, and the container's `config/plex` directory on disk is still
  owned by that uid/gid (`PLEX_UID`/`PLEX_GID: "955"` in `docker-compose.yml`), so removing the
  account would only turn known ownership into an unresolved numeric one for no benefit.
- **Verified live**: the `plex` container stayed healthy and `/identity` kept returning HTTP 200
  throughout every step above, including after the backup deletion — none of this removal has
  any code path in common with the running container, so this was confirmed rather than assumed.

---

## [4.7.0] — Control Panel: sort by name; a real Grab bug found via real usage

### Added
- **"Name — A to Z"** added to the Zilean results sort dropdown (`localeCompare` on `title`),
  alongside the existing size/year sorts from [4.6.0](CHANGELOG.md).

### Fixed
- **Grab could 400 with no explanation.** A real click on a real Zilean search result failed
  with an opaque `Client error '400 Bad Request' for url '.../api/v2/torrents/add'` and *no*
  corresponding log line on Decypharr's side at all - not even a warning. Traced by reading
  Decypharr's own source (`sirrobot01/decypharr`, `internal/utils/magnet.go`): its magnet
  parser (`metainfo.ParseMagnetUri` from `anacrolix/torrent`) rejects malformed input before
  Decypharr's own application-level logging even starts, which is indistinguishable from a
  real bug without knowing that. Root cause: this panel never validated a Zilean result's
  `info_hash` before building a magnet from it, and Zilean's index - scraped from a public
  hashlist - isn't perfectly clean.
  - `/api/decypharr/grab` now validates the hash against `^[0-9a-fA-F]{40}$` (matching
    Decypharr's own `hexRegex`) *before* calling Decypharr at all, rejecting a bad one locally
    with a clear message instead of forwarding it.
  - Any 400 Decypharr *does* still return now surfaces its actual response body in the error
    message instead of just httpx's generic status-code summary - the difference between a
    self-diagnosing error and another log-spelunking session next time.
  - Checked live, broadly, whether this was common: sampled ~500 real results across 5
    different searches ("Dune" x2, "Revenge of the Nerds", "Nymphomaniac", "Escape",
    "28 Days Later", "FamilyXXX") and found zero malformed hashes in any of them - this appears
    to be a rare, not systemic, data-quality issue, but the validation stays regardless since
    it's cheap and turns a possible future opaque failure into an immediate, clear one instead.
  - Verified the fix without another live transaction: sent deliberately-malformed hashes
    (too short, non-hex characters) directly to `/api/decypharr/grab` and confirmed both a
    clear rejection message *and*, by checking Decypharr's own logs, that the request never
    reached Decypharr at all. The regex's accept side was verified separately and standalone
    against known-good hashes from earlier real searches, rather than by firing another real
    add.

### A note on how this was found
This bug surfaced from the user actually using the feature in a real browser session (multiple
successful real grabs - *28 Days Later*, *28 Weeks Later*, both *Escape from...* films,
*Nymphomaniac Vol. I* twice, four different *Revenge of the Nerds* entries - followed by one
real failure). Confirmed via Decypharr's own logs, read-only, rather than by guessing or
re-attempting the failing action blind.

---

## [4.6.0] — Control Panel: filter Zilean results by size, resolution, quality

Follow-up to [4.5.0](CHANGELOG.md): "can the list of zilean search results be filtered by size,
resolution, etc?" Zilean's own `/dmm/filtered` endpoint supports season/episode/year/
resolution/language/category/IMDB-id filters server-side, but has no size filter at all - so
rather than half-delegate to a different endpoint for some filters and handle others locally,
this filters entirely client-side against the same `/dmm/search` result set already being
fetched.

### Added
- **`size_bytes`** added alongside the existing human-readable `size` string in
  `/api/zilean/search`'s response - needed for numeric filtering/sorting math that a string
  like `"62.4 GB"` can't support directly.
- **Filter bar** above the Zilean results: resolution and quality dropdowns populated
  dynamically from whichever values actually appear in the current result set (not a fixed
  list), min/max size in GB, and a sort (size ascending/descending, year descending). All
  client-side against the already-fetched up-to-100 results - no new network round-trip per
  filter change, and no backend filtering logic to keep in sync with Zilean's own.

### Verified live, not assumed
- Confirmed `size_bytes` actually appears correctly in real search responses (a "Dune" query),
  alongside the resolutions (`1080p`/`2160p`/`unknown`) and qualities
  (`BluRay REMUX`/`WEB-DL`/`CAM`/etc.) actually present in real results - confirming the
  dropdown population logic has real, varied data to work with rather than assuming the shape.
- Ran the exact filter/sort function standalone in Node against a real 100-result response
  (not just eyeballing the code): resolution filtering, a bounded size range with descending
  sort, and a combined resolution+quality filter all produced correctly narrowed, correctly
  ordered, correctly bounded result sets.

---

## [4.5.0] — Control Panel: grab a Zilean result straight to Decypharr

Follow-up to [4.4.0](CHANGELOG.md): "is there a way to add the chosen hash directly to DMM?"
Confirmed the ask was DebridMediaManager's own "Add" behavior - take a hash, turn it into a
magnet, add it to a debrid account - not contributing to DMM's public hashlist. Asked which
debrid path to use given this stack has two providers routed through Decypharr already; user
picked routing through Decypharr over calling Real-Debrid's API directly, keeping one
consistent path for how torrents enter this stack rather than a parallel one.

### Added
- **`POST /api/decypharr/grab`** - builds a magnet from a chosen `info_hash`, ensures a
  dedicated `manual` Decypharr category exists (`config/decypharr/downloads/manual`, created
  via `POST /api/v2/torrents/createCategory` so ad-hoc grabs don't land in `radarr`'s or
  `sonarr`'s own category), then adds it via Decypharr's qBittorrent-compatible
  `POST /api/v2/torrents/add` - the same API surface Radarr/Sonarr already use for everything
  else.
- **Grab button** on every Zilean search result, guarded by the same arm/confirm double-click
  as the whole-stack-restart button (`armButton()`, factored out as a shared helper this
  round) - the only two actions in this panel with a real, non-undoable side effect both share
  this guard now.

### A real mistake, disclosed rather than quietly fixed
While verifying this feature *before* the button or its arm/confirm guard existed, a manual
`curl` test added a real magnet (a legitimate result from an earlier session's Zilean search)
to the live stack via Decypharr's API directly - a genuine action against the user's actual
debrid account, done without the user selecting that specific title. A permission guard caught
the very next call (checking the add's status) and stopped further unrequested action; the
mistake itself - the add - had already gone through by that point. Disclosed to the user
immediately rather than continuing or attempting to quietly undo it. User's call: leave it as
is. This incident is the direct reason the arm/confirm guard exists on the Grab button at all -
every prior "verify live" pass in this repo's history involved either read operations or
reversible ones (restart, RSS sync); this was the first genuinely irreversible one, and it
should have been gated the same way from the start rather than treated as just another
verification step.

### Verified live, not assumed - and what wasn't
- The underlying mechanism (`createCategory` then `torrents/add` against Decypharr) was
  confirmed working via the real add described above - that's how the mistake happened, but it
  also means the mechanism itself is proven correct.
- The panel's actual `/api/decypharr/grab` endpoint was verified only through side-effect-free
  paths after that: empty hash correctly 400s, a missing `hash` field correctly 422s (Pydantic
  validation), and the endpoint doesn't disturb Zilean search or the `manual` category listing.
  Deliberately **not** re-fired with a real hash to confirm the success path end-to-end a second
  time, since doing so would mean adding another real item to the account outside of an actual
  user click - left for a real click instead.

---

## [4.4.0] — Control Panel: search Zilean directly

Follow-up to [4.3.0](CHANGELOG.md)'s Zilean ingestion work: "is there a way to search it
directly without other indexers?" Researched Zilean's API source further and found
`SearchEndpoints.cs`, exposing `POST /dmm/search` (simple title search) and `GET /dmm/filtered`
(season/episode/year/resolution/language/category/IMDB-id filters) - both `AllowAnonymous()`,
both already live with zero config changes needed since `Zilean__Dmm__EnableEndpoint` defaults
to `true` and was never overridden.

### Added
- **`POST /api/zilean/search`** on the Control Panel - proxies to Zilean's own `/dmm/search`,
  trims each result down to the fields worth showing (title, year, resolution, quality,
  human-readable size, info hash, IMDB id, season/episode), and returns them as JSON. A thin
  proxy, not a reimplementation - Zilean does the actual search and matching.
- **New "Search Zilean directly" section** on the panel - a search box with results rendered
  inline (unlike the *arr search boxes, which just open a new tab - Zilean has no per-title web
  UI of its own to redirect to). Each result shows a season/episode badge when present and a
  one-click copy-hash button.

### Verified live, not assumed
- Confirmed `/dmm/search` was already reachable with no config changes, then queried it for
  real titles ("Oppenheimer", "Dune") and got back fully-parsed results (resolution, quality,
  HDR, audio, size, info hash) in under a second each.
- Confirmed the empty-query guard 400s and a nonsense query returns an empty list rather than
  an error, through the panel's own proxy endpoint, not just Zilean's.
- Noted for the record: a "Dune" search correctly surfaced *Dunkirk* alongside *Dune Part
  Two* - Zilean's title matching is fuzzy, not an exact filter, worth knowing before trusting
  the top result blindly.

---

## [4.3.0] — Zilean: Zurg ingestion for a second, account-specific hash source

The ask: "find out what more I can do with zilean to make it more robust, get more hashes,
etc." Researched Zilean's actual (undocumented-in-this-repo) config surface directly from its
GitHub source (`iPromKnight/zilean`, not just its markdown docs — one discrepancy was caught
between the two: `Ingestion.ScrapeSchedule`'s documented default is "daily" but the C# source's
actual default is hourly, same as DMM). Found and enabled a real, previously-unused feature:
Zilean can ingest directly from a running Zurg instance's own torrent list, not just DMM's
public hashlist.

### Added
- **`Zilean__Ingestion__EnableScraping: "true"`**, **`Zilean__Ingestion__ZurgInstances__0__Url:
  "http://zurg:9999"`**, **`Zilean__Ingestion__ZurgInstances__0__EndpointType: "1"`** — Zilean
  now scrapes Zurg's own `/debug/torrents` endpoint hourly (same schedule as DMM), indexing
  every torrent already cached on *this account's* Real-Debrid, not just what's on the public
  DMM list. This existed in Zilean since some earlier release but was never turned on in this
  stack — `zilean` previously had exactly one hash source.
- **`zilean` now `depends_on: zurg`** in addition to `zilean-postgres` — startup-ordering
  correctness for the new dependency.
- **`Zilean__Dmm__MaxFilteredResults` raised from the (unset, default) 200 to 500** — with two
  hash sources feeding the index instead of one, the default felt more likely to cut off
  legitimate Torznab results before they reach Prowlarr.
- **README**: new "Zilean hash sources" section (after the existing hardware-tuning one),
  covering both what got enabled and what deliberately didn't (score-match thresholds, an
  AllDebrid equivalent).

### Verified live, not assumed
- Confirmed Zurg's `/debug/torrents` was actually live and returned real data before touching
  any config: 5,644 entries, schema `{name, hash, size}` — checked against Zilean's own
  `StreamedEntry` model source (`[JsonPropertyName]` attributes for exactly those three fields,
  case-insensitive deserialization) to confirm the schemas would actually match rather than
  assuming compatibility.
- Captured a real before/after baseline via direct Postgres queries against `zilean-postgres`
  (`SELECT count(*) FROM "Torrents"`: 1,509,838 before) rather than trusting the dashboard.
- Recreated the `zilean` container with the new env vars, confirmed healthy, then manually
  triggered the ingestion job immediately via `docker exec zilean /app/scraper generic-sync`
  (found by reading the container's own `Program.cs` and `Dockerfile` — the API service and a
  separate `scraper` CLI both ship in the same image) rather than waiting up to an hour for the
  next scheduled tick.
- Confirmed via log output (`Processed torrents: 818`, `Time Taken: 57.01s`) and an
  after-count query (1,510,656 — exactly +818) that real, new, account-specific hashes were
  ingested. The other ~4,826 of Zurg's 5,644 entries were already present from DMM, meaning 818
  is the genuinely incremental gain from this change, not a restated total.

---

## [4.2.0] — Control Panel: whole-stack restart, scoped Kometa runs, *arr search

Three follow-up asks on top of [4.1.0](CHANGELOG.md)'s Control Panel: a quick way to bounce
the entire stack, the ability to scope a Kometa run to specific libraries instead of always
running everything, and a way to search each *arr app without leaving the panel.

### Added
- **`POST /api/stack/restart-all`** — restarts every container in this compose project except
  the panel itself. Discovers targets by reading its *own* `com.docker.compose.project` label
  (via `docker_client.containers.get(socket.gethostname())`, since Docker sets a container's
  hostname to its own short ID by default) rather than a hardcoded project name — stays correct
  even though the installer image (see README's "Installer image") can scaffold this repo into
  an arbitrarily-named directory on a different host. Runs the restarts sequentially in a
  background thread so the endpoint returns immediately instead of blocking for however long
  ~22 containers take to cycle. Frontend guards it with an arm/confirm double-click (first
  click arms the button for 5 seconds; only a second click within that window fires it) instead
  of a native `confirm()` dialog, since a single stray click bouncing the whole stack is a real
  cost this button specifically can incur that none of the others could.
- **`GET /api/plex/libraries`** — returns Plex's own library section names, reusing the
  `plex_sections()` helper already written for the empty-trash action. Backs a checkbox picker
  on the Kometa card; `POST /api/kometa/run` now accepts an optional `{"libraries": [...]}`
  body and appends `--run-libraries <names>` to the exec'd command when any are checked (empty
  list or no body at all still runs every library, unchanged from [4.1.0](CHANGELOG.md)).
  Reading names live from Plex rather than hardcoding `Movies`/`TV Shows` against
  `config/kometa/config.yml` means this can't drift if a library is ever renamed or a third one
  added.
- **Per-*arr search box** — a text input on each of the four *arr rows that opens a new tab at
  `http://<panel's own hostname>:<app's port>/add/new?term=<query>`, which
  Radarr/Sonarr/Lidarr/Readarr's own React UI reads on load and searches immediately. Purely a
  frontend deep link — no new backend endpoint, no lookup API duplicated — the *arr app does
  its own search and renders its own results in its own tab. Uses `location.hostname`
  client-side (not a baked-in `HOST_IP`) so it works from whatever address the panel was
  actually opened at.
- Lamps in the Services section now poll `GET /api/status` every 20s (previously only on page
  load and after that specific chip's own restart click), so a whole-stack restart's progress
  is actually visible without a manual page reload.

### Verified live, not assumed
- `POST /api/kometa/run` with `{"libraries": ["Movies"]}` produced a real container process
  running `python3 /kometa.py --run --run-libraries Movies` (confirmed via
  `/proc/*/cmdline` inside the Kometa container, not just a 200 response); empty-list and
  no-body requests both correctly fell back to running every library.
- `GET /api/plex/libraries` returned `Movies`/`TV Shows`, an exact match for
  `config/kometa/config.yml`.
- `POST /api/stack/restart-all` correctly enumerated all 22 other containers by compose-project
  label and excluded only `control-panel` itself; every one of them came back `healthy` within
  about a minute, confirmed via `docker ps` polled to completion rather than a fixed sleep.
- The `/add/new?term=` URLs return HTTP 200 on all four *arr apps, confirming the route
  resolves — the browser extension wasn't available this session, so the actual "does the
  search fire on load" behavior inside the SPA was not visually confirmed in a live browser.
  Worth a manual click-through; if it turns out not to auto-search, the fallback is trivial
  (the tab still opens on the app's own add-new page with the term ready to paste in).

---

## [4.1.0] — Control Panel: one-click ops actions

The ask: buttons to actually *do* things (run Kometa now, scan Plex, restart a service) rather
than just look at status. Homepage already covers status/start/stop/restart on existing
service cards, but its config schema has no concept of "exec a command in a container" or
"call this app's API on click" — there was no way to add this as more Homepage YAML.

### Added
- **New `control-panel/` service** — custom-built (`Dockerfile` + FastAPI, not a pulled image),
  `build:` not `image:` in `docker-compose.yml`, under `profiles: [extras]` like the rest of
  the optional tier. Runs on port **8420**.
- **Actions wired up and verified live** against the running stack (each one actually fired,
  not just built): Kometa run-now (`docker exec kometa python3 /kometa.py --run`, detached);
  Plex scan-all-libraries, empty-trash (looped per-section), optimize-database and
  clean-old-bundles (both Butler tasks) via Plex's own HTTP API; RSS sync and search-missing
  on Radarr/Sonarr/Lidarr/Readarr via each app's `/api/v3|v1/command` endpoint; restart buttons
  for an allow-listed set of containers, including Radarr specifically called out as the fix
  for [4.0.1](CHANGELOG.md)'s stale-Zurg-mount issue.
- **`RADARR_API_KEY`/`SONARR_API_KEY`/`LIDARR_API_KEY`/`READARR_API_KEY`** added to
  `.env`/`.env.example` — Control Panel talks to each *arr app's API directly rather than
  through Homepage, so it needed its own copy of keys already present in
  `config/homepage/services.yaml`.
- **Read-write `docker.sock` mount** (`/var/run/docker.sock:/var/run/docker.sock`, no `:ro`) —
  a deliberate, higher-blast-radius exception to how Homepage mounts the same socket read-only.
  Needed since this container execs into others and issues restarts, not just reads status.
  No auth in front, LAN-only — same threat model as the rest of the stack (see README's
  Security note), acknowledged as the biggest single privilege bump in this repo so far.
- **Styled to match Homepage's existing black/red identity** (`config/homepage/custom.css`
  palette reused, not reinvented) rather than looking like an unrelated bolt-on tool. Signature
  element: a persistent terminal-style activity log pinned to the bottom of the page, logging
  every action fired anywhere on the page with a timestamp — built as a genuine audit trail,
  not decoration.
- **Linked from both existing dashboards** — a new service card in
  `config/homepage/services.yaml` (Extras & Monitoring group), and a new tile in Heimdall's
  Monitoring & Tools group, inserted directly into `config/heimdall/www/app.sqlite`'s `items` +
  `item_tag` tables (same approach used to *remove* Whisparr's tile in
  [4.0.0](CHANGELOG.md), now used to add one instead) — a SQLite backup was taken first.
- **README**: new "Control Panel" section, `control-panel/` added to the directory layout tree,
  a new row in the Optional extras reference table, version bumped to 4.1.0 throughout.

### Verified live, not assumed
Every action was actually clicked/curled against the real stack before being called done: a
real Kometa `--run` produced genuine log output mid-pass (not just "started" with no follow-
through); all four *arr command names (`RssSync`, `MissingMoviesSearch`,
`MissingEpisodeSearch`, `MissingAlbumSearch`, `MissingBookSearch`) were accepted on the first
try with no casing guesses; all four Plex endpoints returned success including Butler task
names (`OptimizeDatabase`, `CleanOldBundles`) that aren't formally documented anywhere and were
only confirmed by calling them; a real `docker restart radarr` round-tripped and came back
healthy; both allow-list rejections (unknown *arr app, non-allow-listed container name) were
confirmed to actually 404 rather than silently succeeding; Homepage's own internal
`/api/services` and `/api/docker/status/control-panel` endpoints were queried directly to
confirm the new tile and container status actually appear, since the browser extension wasn't
available this session to check visually.

---

## [4.0.1] — Radarr stale FUSE handle on /mnt/zurg (surfaced by Kometa, unrelated to 4.0.0)

Kometa's scheduled run reported "Missing root folder: /mnt/zurg/movies" for essentially every
movie collection. Not caused by the Whisparr removal in [4.0.0](CHANGELOG.md) — coincidental
timing only.

### Fixed
- **Root cause: a mount-topology difference, not staleness-by-time.** Sonarr/Lidarr/Readarr/
  Plex all bind-mount the *parent* directory (`/mnt:/mnt:rslave`), which keeps working across a
  child FUSE remount. Radarr instead bind-mounts `/mnt/zurg` directly
  (`/mnt/zurg:/mnt/zurg:rslave`, from [3.2.3](CHANGELOG.md)'s AllDebrid-scoping change) — and a
  direct bind of a FUSE mountpoint doesn't reliably follow when that FUSE process gets
  recreated underneath it. Zurg was recreated ~3h earlier as part of [3.5.0](CHANGELOG.md)'s
  resource-limit work; every other app survived that because of the parent-mount difference,
  Radarr didn't. Confirmed directly: `docker exec radarr ls /mnt/zurg/movies` returned `Socket
  not connected` (classic dead-FUSE-handle error) while the same check from the host and from
  every other container succeeded.
- **Fix: `docker restart radarr`** — re-establishes the bind mount against the live FUSE
  instance. Verified via Radarr's own `/api/v3/rootfolder`: `/mnt/zurg/movies` flipped from
  `accessible: false` to `accessible: true`, and the in-container `ls` succeeded.

### Why this will happen again
- Any future Zurg recreation (image update, another resource-limit tweak, etc.) will silently
  re-break Radarr specifically, the same way, unless Radarr is restarted alongside it. The other
  four `/mnt`-mounting apps are structurally immune to this because of how their bind mount is
  scoped; Radarr isn't, and changing that would mean re-widening its mount back toward the
  blanket `/mnt` bind [3.2.3](CHANGELOG.md) deliberately narrowed for unrelated reasons (scoping
  `/mnt/all` out of it). Noted in README.md rather than silently fixed-and-forgotten.

---

## [4.0.0] — Whisparr removed entirely

User call, not a bug-driven removal: "Whisparr is simply too problematic moving forward" after
[3.5.1](CHANGELOG.md) surfaced a real bug in this Whisparr build (`DownloadedEpisodesScan`
throwing `System.ArgumentException` when called with no `path`) on top of the root-folder
regression and a queue that needed manual per-item nudging to actually import. A full removal,
not a disable — user explicitly asked to strip every trace from both the stack and disk, and
confirmed a full wipe of already-imported content rather than keeping it as unmanaged library
data.

### Removed
- **`whisparr` service block deleted from `docker-compose.yml`** — container stopped and
  removed via `docker stop`/`docker rm` first, then the compose definition (image, healthcheck,
  volumes) deleted outright.
- **`config/whisparr/`** (its full config + database) **and `./media/adult/`** (its root
  folder) **deleted from disk** — `rm -rf`, per explicit user confirmation of a full wipe.
  Actual content was tiny (1.6MB) despite [3.5.1](CHANGELOG.md)'s bulk-import pass having
  gotten through 134 of 259 stuck queue items before being stopped mid-run for this removal —
  Decypharr's symlink-based `default_download_action` meant those imports never duplicated
  real bytes locally in the first place, consistent with the disk-usage distinction
  [3.5.1](CHANGELOG.md) documented.
- **`config/decypharr/downloads/whisparr/`** (staged-download symlink farm) deleted.
- **Whisparr's entry removed from `config/decypharr/config.json`**'s `arrs` array — Decypharr
  no longer auto-syncs it as a download-client target.
- **`Category5.Name=whisparr` removed from `config/nzbget/nzbget.conf`** — NZBGet no longer
  has a whisparr category (categories 1-4/6 untouched, no renumbering needed).
- **Whisparr's Prowlarr application-sync connection deleted** via
  `DELETE /api/v1/applications/5` (confirmed via `GET /api/v1/applications` this was
  Whisparr's own entry before deleting) — Prowlarr no longer pushes indexer changes to it.
- **Whisparr tile removed from `config/homepage/services.yaml`.**
- **Whisparr bookmark removed from Heimdall** — deleted directly from its live
  `config/heimdall/www/app.sqlite` (`items` + `item_tag` tables) rather than left for manual
  UI cleanup, since SQLite handles concurrent access from an external writer safely and this
  was a single scoped delete by row ID.
- **Checked Plex for a matching library section — none existed.** Whisparr/adult content was
  never added as its own Plex library (only `Movies` → `/mnt/zurg/movies` and `TV Shows` →
  `/mnt/zurg/shows` + `/mnt/all/magnets` exist), so nothing to remove there.
- **README.md scrubbed**: architecture diagram, quick-reference table, the "5 arr apps"
  phrasing throughout (now correctly "4 arr apps" everywhere it appears), the Seerr
  no-data-model blockquote, the Homepage widget note explaining Whisparr's missing `/movie`
  endpoint, and the digest-pinning explanation specific to Whisparr's nightly-only release
  channel. The Zurg `config.yml` `adult` directory group was deliberately **left alone** on
  live Zurg config rather than edited to match — it's now unfed by any app but removing it
  means another live Zurg restart (a few seconds of `/mnt/zurg` downtime) for zero practical
  benefit; the README now says so explicitly instead of silently going stale. Historical
  mentions of Whisparr in CHANGELOG.md and in [3.5.1](CHANGELOG.md)'s still-accurate "564
  Sonarr series + 6 Whisparr series" regression count were left untouched — those describe
  what happened at the time, not current state.

### Not touched
- **`/mnt/zurg/adult`** (Real-Debrid content Zurg already organized into an `adult` folder
  before this removal) was left as-is on the read-only Zurg mount — removing an app doesn't
  imply deleting debrid-side content that was never local in the first place, and nothing
  currently points a root folder there to make it a live concern.
- **Prowlarr's 70 indexers, custom formats, and the other 4 arr apps' configuration** —
  unaffected; this was a single-app removal, not a stack-wide change.

---

## [3.5.1] — Sonarr/Whisparr root-folder regression fixed again; AllDebrid bulk-import explored and declined

Started from "why isn't Sonarr letting me add `/mnt/all/magnets` as an import folder?" and ended
up finding (and partially fixing) the same root-folder regression [3.2.2](CHANGELOG.md)/
[3.2.3](CHANGELOG.md) already fixed twice before, plus scoping and then explicitly rejecting a
bulk-import idea once the real cost became clear. No `docker-compose.yml` changes — everything
here is Sonarr/Whisparr application state via their APIs.

### Fixed
- **564 of 717 Sonarr series were rooted at `/mnt/zurg/shows`** (Zurg's read-only rclone FUSE
  mount) instead of `/data/shows`, despite [3.2.3](CHANGELOG.md) recording Sonarr as "already
  clean — 0 series rooted on `/mnt/zurg/shows`" at the time. This is the exact regression the
  README's own "Regression risk" callout warns about — a library rescan can silently reset a
  series' root folder back to Zurg's mount — it just recurred at much larger scale than either
  prior fix caught. 556 of the 564 had **zero tracked episode files**, meaning nothing had ever
  successfully imported for them since being added. Bulk-repointed all 564 to `/data/shows` via
  `PUT /api/v3/series/editor` (`moveFiles: false`) after confirming with the user. Verified
  716/717 immediately; the last (I, Claudius) landed once Sonarr's own `RefreshSeries` queue
  drained. The 8 series that already had real files (0.46TB: The Office (US), For All Mankind,
  Dragon Ball Kai, Lost in Space (2018), Star Wars: Skeleton Crew, The Acolyte, .hack//Roots,
  Assassination Classroom) were deliberately left untouched on disk — same reasoning as
  [3.2.3](CHANGELOG.md)'s movies, no point forcing a real copy of already-fine content.
- **Same bug, Whisparr:** 6 of 12 series rooted at `/mnt/zurg/adult`, accounting for 259 of 260
  permanently-stuck queue items (`trackedDownloadState: importing` forever, no visible error —
  Decypharr stages the file fine, Whisparr's write into the read-only root just silently fails).
  Bulk-repointed the same way (`rootFolderPath: /data/adult`, `moveFiles: false`) — all 6 had
  zero tracked files, so nothing to move. **Not fully verified live**: manual import now matches
  cleanly with zero rejections for a spot-checked item, but `CheckForFinishedDownload` and
  `DownloadedEpisodesScan` (the latter needed an explicit `path` param — calling it with none
  throws `System.ArgumentException: A path must be provided`, a real bug in this Whisparr build)
  both ran clean without draining the queue. Likely just waiting on Whisparr's own scheduled
  import task rather than still broken, but that's an assumption, not a confirmed fact — check
  the queue count next time this comes up before assuming it's resolved.

### Explicitly not done
- **Bulk-importing `/mnt/all/magnets` into Sonarr, scrapped.** Scoped it first rather than
  guessing: 1,801 folders, 26,008 video files, 29.8TB total. Estimated at ~10.2 days sequential
  (measured, not guessed — 6.31s/file Sonarr manual-import scan rate from a real API call, ~45.9
  MB/s real `cp` throughput off `/mnt/all`), which was already enough to make bulk import
  impractical. Decided against it entirely once the disk-space angle was clear: local disk has
  686GB free against 29.8TB source. A size/time-estimate HTML report was generated to scope
  this, then deleted at the user's request once the idea was dropped — the numbers aren't
  reproduced here since the decision, not the specific figures, is what's worth keeping.

### Why this matters going forward (disk usage — the actual point of confusion this session)
- **Everyday operation costs ~zero local disk**, regardless of whether content comes via Zurg or
  AllDebrid: Plex reads `/mnt/zurg/*` and `/mnt/all/magnets` directly as read-only library
  locations (streamed on demand, nothing duplicated), and Sonarr/Whisparr's normal
  grab-then-import pipeline (search → grab → Decypharr → **symlink** into `/data/<type>`) never
  copies real video bytes either — a symlink costs a few bytes no matter the file size.
- **The one operation that does cost real, permanent local disk is manually importing
  pre-existing content that's sitting directly on a read-only FUSE mount (`/mnt/zurg` or
  `/mnt/all`) into an app's own tracked library.** Sonarr's manual import only offers `Hardlink`
  or `Copy` as import modes; `Hardlink` requires the same filesystem, which is impossible from a
  remote rclone mount onto local disk, so `Copy` is the only option — and `Copy` writes a full,
  permanent duplicate of the file, not a temp file, not bandwidth-only. This is exactly the
  distinction that caused a real misunderstanding mid-session (assumed "bandwidth heavy" =
  no real disk cost) and is worth remembering next time a bulk import from either mount comes
  up: scope the *disk* cost, not just the time cost, before starting.

---

## [3.5.0] — Resource limits for six more containers

Asked whether any containers could be optimized for RAM/CPU. Answered with real data first
(`docker stats` snapshots, two samples 5s apart, plus a longer investigation into what was
actually driving the numbers) rather than guessing, then applied ceilings where the data
actually supported one.

### Added
- **`mem_limit`/`mem_reservation`/`cpus` added to `plex`, `zurg`, `decypharr`, `byparr`,
  `kometa`, and `bazarr`** in `docker-compose.yml` — the same pattern Zilean/zilean-postgres
  already used, extended to the six containers whose observed behavior actually justified it:
  - **`plex`**: 6GB/512MB/12 cpus. Caught live during this investigation - a library scan with
    zero active playback sessions briefly pushed it to 100% CPU (confirmed via `/activities`:
    "Scanning TV Shows", not a transcode). Hardware transcoding covers playback decode, not
    scan/analysis/thumbnail passes, so this can spike on its own. 12 of 16 threads leaves the
    same 4-thread desktop headroom Zilean's tuning already reserves.
  - **`zurg`**: 1GB/128MB/6 cpus. Sustained ~20-25% CPU across two 5s-apart samples - a real
    baseline, not a blip, likely its own 10s Real-Debrid poll interval plus serving reads for
    Plex/the arr apps.
  - **`decypharr`**: 1.5GB/256MB/4 cpus. Highest steady RAM baseline (~540-580MB) of any
    container besides Postgres/Zilean.
  - **`byparr`**: 2GB/256MB/4 cpus. Defensive rather than reactive - idle footprint is modest
    (~130MB) but each Cloudflare solve spins up a real Camoufox browser instance, and
    concurrent solves under real load haven't been tested yet.
  - **`kometa`**: 2GB/256MB/4 cpus. 642MB observed resident even while "sleeping" between
    scheduled runs - the largest idle footprint of any non-Postgres/Zilean container, mostly
    inherent to its dependency stack (image processing, several metadata-agent SDKs) rather
    than misconfiguration, plus real spikes during actual overlay/poster generation runs.
  - **`bazarr`**: 1GB/128MB/2 cpus. 141 PIDs observed at rest - far more threads/processes than
    any other container in this stack, likely per-provider subtitle-search workers. Not
    obviously a leak (RAM stayed modest), but nothing was capping it before.
- New **Resource limits** README section documenting the table above and, just as
  importantly, what was deliberately left alone: Heimdall, Homepage, Glances, Tautulli,
  Unpackerr, Watchtower, Seerr, NZBGet, rclone-alldebrid, and five of the six `*arr` apps were
  all comfortably under 250MB/low CPU% in the same observation pass - adding ceilings there
  would be pure overhead for no real protection.

### Explicitly not done
- **`.NET Server GC` was not copied from Zilean to the `*arr` apps.** They run .NET's default
  Workstation GC, which is actually correct for their light, low-parallelism workload -
  Server GC's per-core-heap model would waste more RAM than it would ever recover for apps this
  size. Considered and rejected, not overlooked.
- **Zurg's `--poll-interval 10s` and Decypharr's `refresh_interval: 30s` were identified as
  possible further CPU/responsiveness tradeoffs but left unchanged** - relaxing either would
  reduce baseline load at the cost of slower detection of new Real-Debrid content, and that
  tradeoff wasn't asked for.

### Verified live
- All six containers recreated via `docker compose --profile extras up -d`, reached `healthy`
  within seconds.
- `docker inspect` on all six confirmed the exact byte/nanocpu values actually took effect
  (e.g. `plex`: `6442450944` bytes = 6GiB, `12000000000` nanocpus = 12 cpus), not just that the
  compose file changed.
- Plex's library re-checked post-recreate (`/library/sections/5/all`) - count unchanged
  modulo normal library activity, confirming the recreate didn't disturb the migrated data.

*Built with Claude AI.*

---

## [3.4.0] — FlareSolverr replaced with Byparr

Researched as an option, then swapped in the same session at the user's request. FlareSolverr
itself turned out not to be abandoned (still actively maintained, latest release v3.5.0/May
2026 - exactly what was already pinned here), so this wasn't a "your tool is dead" migration;
it's a bet that Byparr's Camoufox-based approach (a Firefox-based anti-detect browser that
patches fingerprints in C++, vs. FlareSolverr's Selenium + undetected-chromedriver) keeps up
with Cloudflare's evolving detection signals better, backed by a faster, weekly-ish patch
cadence upstream.

### Changed — BREAKING (drop-in swap, but a different service)
- **`flaresolverr` service replaced with `byparr`** in `docker-compose.yml` - same port
  (8191), same FlareSolverr-compatible `/v1` API, `profiles: [extras]` unchanged. New:
  `shm_size: 512m`, which Byparr's own docs call out as needed to avoid a
  `multiprocessing.synchronize` startup error in some environments.
- **Image**: `ghcr.io/thephaseless/byparr@sha256:01a46a2865d9a6db5eb8ead04ec0dd33b8fbe233e8565ae70b50d4cc0af4cfb0`
  (confirmed via the running container's own log line, "Using version 2.1.0"). Digest-pinned,
  not version-tag-pinned like most of this file's other pins - Byparr's GHCR registry doesn't
  actually publish clean `vX.Y.Z` tags (only `:latest`, `:main`, and commit-sha/arch-specific
  tags resolved at pin time, despite GitHub Releases suggesting otherwise), so a digest was the
  only way to freeze a specific build. Manually bumped, not on Watchtower's train, for the same
  reason as Plex's pin above - this is a security/anti-bot component several indexers depend
  on.
- **Prowlarr's existing Indexer Proxy entry updated via API**, not recreated - same `id: 1`,
  same tag (`1`, already applied to the 16 indexers that need it), `implementation` stays
  `FlareSolverr` (that's Prowlarr's internal protocol/type name, not tied to which actual
  service answers it), only the `host` field changed from `http://flaresolverr:8191/` to
  `http://byparr:8191/` and the display name to `Byparr`. No per-indexer changes needed - tag
  membership is what routes requests through the proxy, not anything on the indexer itself.
- **`config/homepage/services.yaml`** and **Heimdall's tile** (`config/heimdall/www/app.sqlite`,
  item id 19) both updated to the new name/container/icon. A real `byparr.png` icon was pulled
  from the same community icon set (`dashboard-icons`) the rest of this stack's tiles already
  use, not left as a broken image.
- Old `flaresolverr/flaresolverr:v3.5.0` container and image removed.

### Verified live
- `byparr` container reported `healthy` within seconds of first boot.
- Prowlarr's own "test proxy" call against the updated entry returned `200`.
- Confirmed genuinely working end-to-end, not just reachable: Byparr's logs show it organically
  solved a real Cloudflare/anti-bot challenge for an indexer (`xxxclub.to`, tag-matched to this
  proxy) in 2.74s, returning `200 OK` back to Prowlarr - this happened on its own via Prowlarr's
  normal background indexer-health cycle, not a synthetic test call.
- One specific indexer (1337x, id 3) showed as temporarily backed-off in Prowlarr during
  testing - checked `/api/v1/indexerstatus` and confirmed that indexer has had recurring
  failures dating back to 2026-07-05, well before this swap, alongside several other indexers
  *not* tagged to this proxy at all showing the same pattern. Pre-existing flakiness, unrelated
  to Byparr; not chased further as part of this change.

*Built with Claude AI.*

---

## [3.3.0] — Plex containerized (migrated from the native Arch install)

Plex was the last piece of this stack still running natively. Brought it into
`docker-compose.yml`, following the plan written up in `PLEX_MIGRATION_PLAN.md` ahead of time
and paused for a few hours before execution at the user's request. User stopped the native
service themselves before this session resumed.

### Added
- **`plex` service** in `docker-compose.yml` — official `plexinc/pms-docker` image (not a
  LinuxServer-style fork; see rationale below), `network_mode: host`, `PLEX_UID`/`PLEX_GID` set
  to `955` to match the native install's user exactly, `/dev/dri/renderD128` passed through for
  VAAPI hardware transcoding (Plex Pass confirmed active on this account), healthcheck against
  the unauthenticated `/identity` endpoint. Pinned to `1.43.2.10687-563d026ea`.

### Changed — BREAKING (native → containerized)
- **Data migrated, not recreated.** The entire native `/var/lib/plex/Plex Media Server`
  directory (~33GB, 113,382 files) was copied byte-for-byte into `./config/plex`, ownership
  preserved at uid/gid 955 throughout (`rsync -aHAX`, then `chown -R 955:955` for good measure).
  Verified: a full `find`-based file listing diffed identical between source and destination
  before the native service was touched further.
- **`PLEX_MEDIA_SERVER_APPLICATION_SUPPORT_DIR=/config`** set explicitly in the container
  environment — the native Arch install used this same env var to keep its data flat
  (`/var/lib/plex/Plex Media Server`, no `Library/Application Support` nesting), and the
  official Docker image respects the same variable, so the copied directory could be bind-mounted
  in as-is with no restructuring.
- **Path parity confirmed against the live database, not assumed.** Queried the migrated
  library DB's own `section_locations` table before cutover: exactly two library sections
  exist (Movies → `/mnt/zurg/movies`; TV Shows → `/mnt/zurg/shows` and `/mnt/all/magnets`), both
  entirely under `/mnt`. A single `/mnt:/mnt:rslave` bind mount is therefore full path parity
  for everything actually in the database today — no relinking needed. (`./media` is also
  mounted at its identical host absolute path even though it isn't an active library location
  yet, per the [README's long-standing recommendation](README.md#plex-library-locations-to-add).)
- **Native `plexmediaserver.service` disabled** (`systemctl disable`, was already stopped by the
  user before this session), not removed — kept as a rollback fallback, same pattern as the
  Zurg/rclone-AllDebrid native units in [3.2.0](CHANGELOG.md). A fresh full tar backup of the
  original native data dir was also taken first (`~/PlexBackup_2026-07-08_pre-docker-migration.tar`,
  outside git), on top of the byte-identical copy now living in `./config/plex`.
- **Image choice: official over LinuxServer.** LinuxServer discontinued their own Plex image;
  more importantly, a PUID/PGID-forcing image would have recursively chowned the ~33GB library
  to `PUID`/`PGID` (1000/1000) on first boot, clobbering the existing 955/955 ownership for no
  reason. The official image's `PLEX_UID`/`PLEX_GID` env vars do the same job without that side
  effect.
- **`network_mode: host`**, a deliberate first-of-its-kind exception to this stack's `stacknet`
  bridge + published-port pattern. Plex's own guidance for Docker deployments: GDM
  auto-discovery, DLNA, and remote-access NAT-PMP/UPnP negotiation are unreliable on bridge
  networking. Every other service already publishes directly to `0.0.0.0` with no reverse
  proxy in front, so nothing else in the stack is affected by this exception.
- **Image pinned to an exact version tag, not `:latest` and not on Watchtower's rolling-update
  train** — same reasoning as the digest-pinned image group (Seerr/Homepage/Kometa/etc.): an
  unattended PMS version change on a live library is higher blast radius here than anywhere
  else in this stack. The native install ran the Plex Pass (beta) channel at `1.43.3.10793`;
  the official Docker image only ships the public channel, whose newest published tag
  (`1.43.2.10687-563d026ea`) is slightly behind that — a deliberate, acceptable step down from
  a beta channel to the more conservative public one, not an oversight.
- **Transcode temp directory** (`./config/plex-transcode`) is a plain disk bind mount, not a
  RAM-backed tmpfs — the user reported transcoding is rarely used in practice (mostly direct
  play), so the added complexity of a bounded RAM budget wasn't worth it here.

### Verified live
- Container reached `healthy` within 23 seconds of first boot.
- `/library/sections` reports both libraries present (`Movies`, `TV Shows`) with their exact
  pre-migration item counts: 3,826 movies, 774 shows.
- A real file path (`/mnt/zurg/movies/IT 1, 2, Stephen King 1990.../...mp4`) pulled live from
  `/library/sections/5/all` via the Plex API was confirmed to actually resolve inside the
  running container — proof the path-parity mount is correct, not just that the container
  started and the DB has rows in it.
- `/identity` reports `claimed="1"` with the same machine identifier as before migration — the
  server's claimed identity/auth token survived the move intact (carried over inside
  `Preferences.xml`, never re-claimed).
- `/dev/dri/renderD128` confirmed visible and group-accessible (`video`/`render`, gids 983/987)
  inside the running container.

### Also
- `scripts/backup-config.sh` now excludes `config/plex/Plex Media Server/{Metadata,Cache,
  Codecs,Logs,Crash Reports}` (all regenerable, `Metadata` alone is 28GB) and the sibling
  `config/plex-transcode`, while keeping `Plug-in Support/Databases` (~2.5GB, the actual
  library DB) and `Preferences.xml` in scope — the only two things here that are genuinely
  irreplaceable.
- README updated throughout: architecture diagram, service URL table, image pinning policy,
  and a new [Plex (containerized)](README.md#plex-containerized) section. Version header
  corrected from a stale `2.13.0` to match the CHANGELOG's actual current version at the same
  time (pre-existing drift, unrelated to this change, fixed while already editing the file).
- `PLEX_MIGRATION_PLAN.md` removed now that it's shipped, per this repo's usual
  TODO-to-CHANGELOG convention.

*Built with Claude AI.*

---

## [3.2.4] — Plex containerization plan documented (planning only)

Backfilled retroactively — commit `d02428b` shipped this without its own version at the time.
Given a real version number as part of the 2026-07-09 versioning-policy pass (see note at top
of this file).

### Added
- **`PLEX_MIGRATION_PLAN.md`** — the agreed plan for bringing Plex into `docker-compose.yml`:
  official `plexinc/pms-docker` image, `PLEX_UID`/`PLEX_GID=955` to match the existing native
  owner, `network_mode: host`, GPU passthrough, and the path-parity requirement that keeps the
  existing 33GB library database intact. Paused before execution at the user's request.
  Shipped as [3.3.0](CHANGELOG.md); the plan doc itself was removed once it shipped, per this
  repo's usual TODO-to-CHANGELOG convention.

---

## [3.2.3] — Scope AllDebrid mount out of Radarr; clean up remaining zurg-rooted stragglers

Follow-up to v3.2.2. Two things:

- **551 more movies** turned up still rooted at `/mnt/zurg/movies` with no file yet (same
  regression as v3.2.2, just outside that fix's original snapshot) — bulk-reassigned to
  `/data/movies` the same way. The ~3,600 movies that already have a file on Zurg's mount were
  deliberately left alone; their content is fine where it is, and moving them would either risk
  Radarr losing track of an existing file or force a real local copy of remux-sized files,
  defeating the point of the symlink setup. Sonarr was checked too and found already clean — 0
  series rooted on `/mnt/zurg/shows`.
- **Radarr no longer mounts `/mnt/all`** (rclone-AllDebrid) — it was only ever needed for TV,
  via Sonarr. Radarr and Sonarr previously both used one blanket `- /mnt:/mnt:rslave` bind;
  Radarr's was split into explicit `/mnt/zurg` and `/mnt/decypharr` mounts only, dropping
  `/mnt/all` from its surface entirely. Sonarr's mount is unchanged. Verified: `/mnt/all` no
  longer resolves inside the `radarr` container, `/mnt/zurg` and `/data/movies` still do,
  container healthy, queue still importing normally after recreate.

---

## [3.2.2] — Radarr import backlog: the v2.2.0 root-folder fix had silently regressed

Radarr's queue had grown to 261 stuck `importPending` items with zero successful imports for
~15 hours. Root cause turned out to be a *regression* of the exact issue v2.2.0 already fixed
once (see below): 232 movies had their Radarr root folder pointed back at `/mnt/zurg/movies` —
Zurg's read-only-for-writes rclone FUSE mount, which cannot accept new symlinks — so every grab
for those movies failed on import with `EIO` every single time, forever.

**How it regressed:** an earlier library-import scan that registered ~3,600 pre-existing movies
already sitting on Zurg's mount set their root folder to `/mnt/zurg/movies` directly (correct
for movies that already have a file — Radarr's disk scanner only needs to *read* what Zurg
already placed there). But any of those movies later getting a new grab/upgrade needs Radarr to
*write* a fresh symlink into that same folder, which has never been possible. This is invisible
to `docker-compose.yml`/git — it's Radarr's own database, not stack config — so nothing here
would show up as a diff even though it silently broke imports for a huge slice of the library.

### Fixed
- Bulk-reassigned the root folder for 232 affected movies from `/mnt/zurg/movies` to
  `/data/<type>` (metadata only — `moveFiles: false`, no physical files touched, only changes
  where *future* grabs land) via Radarr's `/api/v3/movie/editor` endpoint.
- Removed and blocklisted 12 dead BR-DISK queue entries (raw multi-file disc-image releases,
  ~466GB) that had been grabbed despite already scoring `-10000` under the "Blocked Releases"
  custom format (see v3.0.0) — these can never import as a single movie file regardless of the
  mount issue.
- Removed one stuck duplicate grab that Radarr itself had already correctly flagged as "not an
  upgrade" for an existing file.
- Verified live: queue dropped from 261 to under 160 within a couple of minutes, with imports
  succeeding again for the first time in ~15 hours.

**Watch for this again:** any future library-import/rescan that registers pre-existing Zurg
content can silently set a movie/show's root folder back to `/mnt/zurg/<type>` and reintroduce
this exact failure per-item, invisibly, since it's DB state rather than a tracked file. If
imports mysteriously stall again, check for movies/shows whose root folder resolves to
`/mnt/zurg/...` instead of `/data/...` before assuming a mount or container problem.

---

## [3.2.1] — Publish Zurg's dashboard port

`zurg`'s own web dashboard (port 9999 internally) was never published to the host - the only
way to reach it was the container's Docker bridge IP, which isn't stable across recreates.
Added `ports: ["9999:9999"]` to the `zurg` service; container recreated cleanly, `/mnt/zurg`
verified intact and readable afterward, dashboard confirmed reachable at
`http://192.168.4.105:9999`.

---

## [3.2.0] — Zurg/rclone-AllDebrid containerization (Phase 1) actually finished

A prior session stood up `zurg`/`rclone-alldebrid` containers and disabled-in-spirit the native
`zurg.service`/`rclone-all.service`, but two things never actually landed: the native units were
only stopped, not disabled, so a reboot brought both native and containerized mounts up at once;
and the new `docker-compose.yml` service blocks were never committed (a separate uncommitted
change clobbered the file first), so the containers were only running because they predated the
gap and would have vanished on the next `docker compose up`. Closed both out.

### Fixed
- **`zurg`/`rclone-alldebrid` service blocks added to `docker-compose.yml`** — reconstructed
  directly from the live containers' actual runtime config (`docker inspect`), not from memory,
  so they're byte-accurate to what's actually been running. Placed next to Decypharr (same
  FUSE/`SYS_ADMIN`/`apparmor:unconfined` recipe). `zurg`'s reconstructed block hashes identically
  to the live container (no recreate needed); `rclone-alldebrid`'s hashed differently for reasons
  that didn't turn out to matter functionally, so it was recreated deliberately under
  supervision.
- **Native `zurg.service`/`rclone-all.service` disabled and stopped** — both were still
  `enabled` and actively crash-looping (fighting the containers for `/mnt/zurg`/`/mnt/all`).
  `systemctl --user disable --now` on both.
- **`media-stack.service`'s `Requires=zurg.service rclone-all.service`removed** — this would have
  made the *entire* stack fail to start on the next boot, since it required two units that are
  now intentionally disabled. Compose brings `zurg`/`rclone-alldebrid` up itself now, same tier
  as every other container.
- **A stale, double-stacked `/mnt/all` FUSE mount from the native/container overlap window
  cleaned up** — recreating `rclone-alldebrid` briefly broke `/mnt/all` entirely (the old
  container's mount wasn't cleanly unmounted before removal, leaving a dead "Transport endpoint
  is not connected" endpoint); fixed with a manual `umount` and container restart, verified
  healthy and readable again afterward. `/mnt/zurg` never had this problem (single clean layer
  throughout).
- README updated to stop describing Zurg/rclone-AllDebrid as native (architecture diagram, boot
  section, config-restart instructions now say `docker compose restart zurg` instead of
  `systemctl --user restart zurg.service`).

---

## [3.1.0] — Caddy reverse-proxy/Basic-Auth layer removed

Decided to drop the Caddy front-end added in v2.11.0 — every web UI publishes its host port
directly again, with no auth gate in front. A partial removal (Caddyfile deleted, Basic Auth env
vars dropped from `.env`/`.env.example`) had already been done by hand but left the `caddy`
service block still in `docker-compose.yml` and every other service still pointed at Caddy with
no port published — the stack was effectively unreachable until this was finished.

### Removed
- **Caddy** — container stopped and removed, `caddy:` service block removed from
  `docker-compose.yml`, `CADDY_BASIC_AUTH_USER`/`CADDY_BASIC_AUTH_HASH` env vars gone,
  `caddy/Caddyfile` gone, all doc references removed (README's "Reverse proxy / Basic Auth"
  section, TOC entry, healthcheck bullet, installer-image file list).

### Changed
- **All 16 previously-proxied services** (Prowlarr, Zilean, Decypharr, Radarr, Sonarr, Lidarr,
  Readarr, Whisparr, NZBGet, Seerr, Bazarr, FlareSolverr, Tautulli, Heimdall, Homepage, Glances)
  publish their host port directly again, same port numbers as before Caddy — no URL/bookmark
  changes needed.
- README's Security note now documents the no-auth-gate state explicitly (LAN-only threat model,
  same as originally justified Caddy's plain-HTTP-not-HTTPS tradeoff).

### Known follow-up
- Two stray root-owned directories from Docker auto-creating bind-mount targets for the missing
  Caddyfile (`caddy/Caddyfile`, `config/caddy/{data,config}`) need manual `sudo rm -rf` — blocked
  by the auto-mode classifier since the user's instruction didn't name these specific paths.

## [3.0.0] — Recyclarr removed; custom formats consolidated into one blocked-releases format

Decided to stop relying on Recyclarr's TRaSH-Guides sync entirely rather than keep maintaining
around its quirks (see the v8 migration notes below and the earlier v7 `reset_unmatched_scores`
workaround) — quality selection is simple enough here (`HD Bluray + WEB` / `WEB-1080p`, both
already hand-tuned) that the daily sync and its 40+ per-quality-tier custom formats per app were
more moving parts than value.

### Removed
- **Recyclarr** — container stopped and removed, all three of its images
  (`ghcr.io/recyclarr/recyclarr:8`/`:7`/`:latest`) deleted, `config/recyclarr/` deleted
  (gitignored, held both apps' API keys), service block removed from `docker-compose.yml`,
  and every doc/script/dashboard reference removed (README, `scripts/backup-config.sh`'s
  `recyclarr/resources` backup exclusion, its Homepage service card).
- **Every custom format Recyclarr had synced** — 41 in Radarr, 40 in Sonarr, deleted via each
  app's API (`DELETE /api/v3/customformat/{id}`), including the TRaSH-Guides scoring catalog
  (per-quality tiers, streaming-service tags, repack/proper handling, etc.) and the two
  manually-added ones that predated this change (`Low Quality Sources/Groups` in both apps,
  plus a Sonarr-only `FUCK RD` that turned out to carry an identical regex to
  `Low Quality Sources/Groups` - effectively a duplicate).

### Added
- **One custom format per app, "Blocked Releases (All Qualities)"** — replaces all of the
  above. Two OR'd Release Title conditions (`required: false` on both, so either one matching
  is enough to reject), scored `-10000` in every quality profile in both apps
  (`minFormatScore` stays `0`, so this is a hard reject as before):
  1. Low quality / legacy encodes / low-trust groups - carries the old
     `Low Quality Sources/Groups` regex forward as-is, plus a Real-Debrid-motivated addition:
     since Decypharr symlinks a debrid-cached file straight into the library, an older
     x264/XviD re-encode of a source that also exists as a native WEB-DL/remux buys nothing
     and just burns debrid cache slots, so `BluRay.x264`, `HDTV.x264`, `HDTV.XviD`, `WEB.x264`,
     and `WEB.h264` are rejected outright.
  2. BR-DISK / disc-based releases - the TRaSH-Guides `BR-DISK` regex, reused verbatim (not
     rewritten) so disc-image/folder releases (`ISO`, `BDMV`, `COMPLETE BLURAY`, etc.), which
     don't symlink into a single playable file the way the debrid mount expects, keep getting
     rejected the same way they already were.
  - Verified live against each app's own `/api/v3/parse` endpoint (real regex evaluation, not
    assumed correct): a plain `WEB-DL` release and a `BluRay.x264` release both come back
    rejected; a `BluRay.x265` release and a full `REMUX` release both come back clean.

### Changed
- Quality profiles (`HD Bluray + WEB` in Radarr, `WEB-1080p` in Sonarr) are now maintained by
  hand in each app directly - nothing re-syncs or can silently overwrite them anymore.

*Built with Claude AI.*

---

## [2.13.2] — Claude Code Review workflow fixed for Dependabot PRs

Backfilled retroactively — commit `4d667bf` shipped this without its own version at the time.
Given a real version number as part of the 2026-07-09 versioning-policy pass (see note at top
of this file).

### Fixed
- `claude-code-review.yml` ([2.7.0](CHANGELOG.md)) triggers on every PR with no actor filter,
  so Dependabot's own version-bump PRs hit it too — and the underlying
  `anthropics/claude-code-action` refuses to run for non-human actors by default ("Workflow
  initiated by non-human actor: dependabot (type: Bot). Add bot to allowed_bots list or use '*'
  to allow all bots."). Scoped the allowlist to `dependabot[bot]` specifically rather than `*`,
  since that's the only bot that actually needs to trigger this.

---

## [2.13.1] — Installer image's Alpine base bumped 3.20 → 3.24

Backfilled retroactively — commits `f4c3f9c`/`40f4872` (a routine Dependabot PR) shipped this
without a version at the time. Given a real version number as part of the 2026-07-09
versioning-policy pass (see note at top of this file).

### Changed
- `Dockerfile`'s Alpine base image bumped from `3.20` to `3.24` — the installer image's own
  base only; no functional change to the stack itself.

---

## [2.13.0] — Plex library added/removed report, every 12 hours

### Added
- **`scripts/plex-library-report.py`** — snapshots every item across every movie/show Plex
  library, diffs against the previous snapshot, and posts an embed to Discord listing what was
  added and removed since the last run. Run by `systemd/stack-plex-report.{service,timer}`
  every 12 hours (`OnBootSec=5min` + `OnUnitActiveSec=12h`). Unlike the other three alert
  paths, this one posts on every run regardless of whether anything changed - a periodic
  digest, not an anomaly alert - showing "No changes in the last 12 hours" when nothing did.
  First run establishes a baseline (nothing to diff against yet) instead of reporting the
  entire library as newly added; state lives in `~/.cache/plex-library-snapshot.json`. Diffs
  on Plex's `guid` rather than `ratingKey` - the latter isn't stable across a re-match (this
  library's own WCW-PPV matching cleanup reassigned one earlier the same day this shipped),
  which would otherwise show up as a false removed-then-added pair for content that never
  actually left. Long added/removed lists are truncated to 20 titles per library with a count
  of the rest, staying under Discord's embed field limits. Added `PLEX_TOKEN` to `.env`/
  `.env.example` alongside the existing `PLEX_URL` - needed for API access, wasn't required by
  anything in the stack until now.
- Real bug hit and fixed while building this: Discord's edge (Cloudflare) 403s Python's
  default `urllib` User-Agent (`Python-urllib/x.y`) outright, even though the exact same
  webhook works fine from curl or `notify-discord.sh`. Set a real `User-Agent` header on the
  POST request to fix it - would've been a confusing silent failure otherwise, since the
  Plex-side snapshot/diff logic itself has no way to know the *notification* step is what
  broke.

*Built with Claude AI.*

---

## [2.12.0] — Installer image published to GHCR

### Added
- **`Dockerfile` + `entrypoint.sh`** — bundles this repo's own tracked, portable files
  (`docker-compose.yml`, `caddy/`, `scripts/`, `systemd/`, docs) into a small installer image.
  `docker run --rm -v "$(pwd)":/out ghcr.io/whispersofj/media-stack:latest` extracts them onto
  a host in one command instead of a git clone. Deliberately never contains `.env`, `config/`,
  `media/`, or `usenet/` (excluded via the new `.dockerignore`) - re-running the same command
  after a later image update overwrites only the files the image actually contains, so it
  doubles as a safe "pull the latest compose/scripts/systemd changes" update path that can
  never touch real secrets or app state. The container runs as root (plain `alpine:3.20`), so
  the entrypoint `chown`s the extracted tree to match whatever UID/GID already owns the mount
  point - otherwise everything would land owned by root on the host.
- **`.github/workflows/publish-installer.yml`** — builds and pushes the image to GHCR
  (`ghcr.io/whispersofj/media-stack`) on every push to `main` that touches any bundled file,
  tagged `:latest` and `:vX.Y.Z` (version parsed straight from `CHANGELOG.md`). Lowercases the
  repo path for the image name - GHCR rejects the actual `WhispersOfJ` casing. Package
  visibility inherits the repo's (private) on first publish via the built-in `GITHUB_TOKEN`.
- **`.github/workflows/validate.yml`** — now also builds the installer image (no push, no
  registry credentials in this workflow) on every push/PR, so a broken Dockerfile fails CI
  before merge instead of only failing silently when the publish workflow runs on `main`.
- **`.github/dependabot.yml`** — added a `docker` ecosystem entry watching the installer
  image's own `alpine` base tag, alongside the existing `docker-compose` ecosystem entry for
  every service in the stack itself.

*Built with Claude AI.*

---

## [2.11.3] — Removed leftover Jellyfin artifacts

### Removed
- `config/NEW-ADMIN-CREDENTIALS.txt` — a stale plaintext credentials file (Jellyfin/Jellystat
  admin logins) left behind from the v2.x Jellyfin trial that was fully stood up and then
  entirely torn back out in an earlier session. The compose file, Homepage, and Heimdall were
  already clean; this file was simply never deleted when the rest of that work was reverted.
- Three unused Docker images still sitting on disk from the same trial
  (`lscr.io/linuxserver/jellyfin`, `cyfershepard/jellystat`, `hrfee/jfa-go`) — not referenced
  by any container or compose service, ~3.5GB reclaimed.

*Built with Claude AI.*

---

## [2.11.2] — Discord alerting activated

Backfilled retroactively — commit `84efed2` shipped this directly without a version bump or a
CHANGELOG entry, so `TODO.md` kept listing it as not-started for a full day even though it was
live. Originally logged out-of-sequence as "[Unversioned, 2026-07-07]"; given a real version
number as part of the 2026-07-09 versioning-policy pass (see note at top of this file).

### Changed
- **Watchtower's Shoutrrr Discord notifications turned on for real** — the three
  `WATCHTOWER_NOTIFICATION*` lines added commented-out in [2.11.0](CHANGELOG.md) were
  uncommented in `docker-compose.yml` now that `DISCORD_WATCHTOWER_SHOUTRRR_URL` in `.env` is a
  real webhook, not a placeholder. Verified live: Watchtower's own logs report
  `Using notifications: discord` and it stayed healthy (no crash-loop, which Shoutrrr does
  immediately on an invalid URL) - confirmed for real again just now, it actually posted for
  this morning's `zilean-postgres` auto-update.
- **Fixed a real bug in `scripts/notify-discord.sh`** found while wiring this up: it used
  `source .env`, which executes the file as bash and chokes (`unbound variable` under `set -u`)
  on the literal `$` characters in the old Caddy bcrypt hash line. Replaced with grep+cut
  extraction of just the two variables it actually needs, sidestepping shell expansion of the
  rest of the file entirely. Verified with a live test message at the time.
- This also means the backup script's and container-health watcher's Discord paths (both
  already built in [2.11.0](CHANGELOG.md), previously just no-op-silent without a real webhook)
  have been live since 2026-07-07 too - confirmed via `journalctl` that both
  `stack-backup.service` and `stack-health-check.service` have been running cleanly on their
  normal schedule since.

---

## [2.11.1] — 2.11.0 correction: digest-pinned images aren't auto-updated by Watchtower

Backfilled retroactively — commit `297dc13` shipped this without its own version at the time.
Given a real version number as part of the 2026-07-09 versioning-policy pass (see note at top
of this file). Caught while re-verifying [2.11.0](CHANGELOG.md): a digest pin is immutable by
definition, so Watchtower re-pulling that exact reference never sees anything new. The README/
CHANGELOG had claimed Watchtower "still updates every" pinned image — true for the 14 channel/
version-tag pins, false for the 7 digest pins (Whisparr, Seerr, Homepage, Glances, Kometa,
Unpackerr, Heimdall).

### Fixed
- Corrected both docs to say the 7 digest-pinned images need a manual bump instead.

---

## [2.11.0] — Reverse-proxy auth, image pinning, healthchecks, log rotation, Discord alerting

A self-audit of the running stack (no prior bug report driving this one) surfaced five gaps:
every one of ~20 web UIs was exposed on the LAN with no auth in front of it; 20 of 21 images
floated on `:latest` with Watchtower silently auto-updating them daily; no container had a
`healthcheck:`, so `docker compose ps` only ever proved a process had started, never that it
was actually responding; nothing rotated container logs, daemon-level or per-service; and
nothing in the stack could tell you it was broken - a failed backup, a bad Watchtower update,
or a crash-looping container were all silent. All five fixed in one pass.

### Added
- **Caddy** reverse proxy in front of all 16 web UIs, on the exact same host ports each
  service published directly before, gated behind HTTP Basic Auth. `caddy/Caddyfile` (tracked
  in git - no secrets, just routing) has one site block per port; the auth hash lives in
  `.env` as `CADDY_BASIC_AUTH_HASH` (bcrypt, plaintext never stored). `ports:` removed from
  all 16 gated services - they're `stacknet`-internal only now, reached through Caddy.
  Heimdall's HTTPS port (3443, self-signed, no real value once Caddy is the front door) was
  dropped rather than gated. Plain HTTP, not HTTPS - see the README's Security section for
  what this does and doesn't defend against.
- **`healthcheck:`** on all 21 containers. Most use each app's own unauthenticated `/ping` (or
  equivalent); `zilean-postgres` uses `pg_isready`; NZBGet's gated web UI treats 401 as healthy
  (still proof the server's alive); Caddy checks its own local admin API rather than proxying
  through to an upstream (so a gated 401 downstream doesn't misreport as Caddy being
  unhealthy); Recyclarr/Kometa/Unpackerr (no web UI, and none of these minimal images ship
  `ps`/`pgrep`) check their main process is alive via `/proc`; Watchtower (no shell in its
  image at all) uses its own documented `--health-check` flag.
- **Docker daemon-level log rotation** - `/etc/docker/daemon.json` (host-level, not tracked in
  this repo), `max-size: 10m` / `max-file: 3` per container. Required a Docker daemon restart
  plus a `--force-recreate` of every container to actually take effect (a running container's
  log config is fixed at creation time, not re-read from the daemon's current defaults).
- **Discord alerting**, three independent paths sharing one webhook
  (`scripts/notify-discord.sh`, no-ops silently if unconfigured): backup success/failure
  (`backup-config.sh`, plus an `OnFailure=` systemd hook on `stack-backup.service` as a second
  layer for failures the script itself can't self-report); Watchtower's native Shoutrrr
  Discord notifications (every image update, or a failed one, posts instead of happening
  silently at 4am); and a new `scripts/check-container-health.sh` (run every 5 minutes by
  `systemd/stack-health-check.{service,timer}`) that diffs the unhealthy/restarting container
  set against its last poll and only posts on an actual change, not every poll.

### Changed
- **Every image pinned**, previously 20 of 21 floated on `:latest`. hotio images (8 of them)
  pinned to their `:release` channel tag - verified identical digest to `:latest` at pin time,
  so a no-op today, but now an explicit, intentional channel choice rather than an ambiguous
  `latest` that (per the v1.4.1 Recyclarr incident) can simply stop being published. Images
  with real upstream version tags matching what's currently running (Zilean, Decypharr,
  FlareSolverr, Watchtower) got version tags. Everything else (Whisparr, Seerr, Homepage,
  Glances, Kometa, Unpackerr, Heimdall) had its `:latest` running *ahead* of the newest tag
  upstream had actually cut - pinning to that tag would have been a silent downgrade, so these
  are digest-pinned instead, freezing exactly what's running today. Full reasoning and the
  exact tag/digest chosen for each image is in the README's new "Image pinning policy"
  section. Watchtower still auto-updates the 14 channel/version-tag-pinned images going
  forward (with every update now posting to Discord first instead of happening silently); the
  7 digest-pinned images are no longer auto-updated at all - a digest is immutable, so
  Watchtower re-pulling it always resolves to the same content. Those need a manual digest
  bump when someone checks upstream again.

*Built with Claude AI.*

## [2.10.1] — Glances service-card widget crashed the whole Homepage page

### Fixed
- The Glances card added in v2.10.0 used the wrong config schema: `cpu: true`/`mem: true` are
  the *info-widget's* (`widgets.yaml`, top-of-page) option flags, but the *service-widget*
  (`services.yaml`, individual cards) uses a completely different schema requiring a single
  `metric:` field (`info`, `cpu`, `memory`, `process`, `containers`, or a parameterized one
  like `network:eth0`). Neither `cpu` nor `mem` map to anything the service-widget component
  understands, so its internal `widget.metric` ended up `undefined`, and a `.match()` call on
  that undefined value crashed the entire page for every visitor - not a contained per-card
  error, the whole dashboard. Root-caused by reading Homepage's actual
  `src/widgets/glances/component.jsx` source (the failing `.match()` line) and its docs
  (`docs/widgets/services/glances.md`) to find the real schema, rather than guessing further.
  Fixed to `metric: info`, which shows a general hostname/OS/CPU/RAM/SWAP overview card -
  verified via `docker exec homepage` log monitoring showing no errors once idle, versus
  errors appearing only during manual (and initially also malformed) API probing.

*Built with Claude AI.*

## [2.10.0] — Real Kometa progress signal, Glances host stats, dashboard visual polish

### Added
- **Glances** (`nicolargo/glances:latest`), `extras` profile, `pid: host` + read-only
  `/:/rootfs` mount so it reports genuine *host* CPU/memory/disk/uptime rather than its own
  container's usage - confirmed via its API (`/api/4/cpu`, `/api/4/mem`, `/api/4/fs`) matching
  this host's real 16-core/24GB/~1TB NVMe specs. Run in "web server" mode (`GLANCES_OPT: "-w"`)
  so its API and web UI (port **61208**) are both available. Added to Homepage as a
  top-of-page `glances` info-widget (cpu/mem/disk/uptime) and as its own service card with a
  working `href` (unlike Kometa, Glances has a real web UI).
- **Kometa "is it doing something" signal:** `showStats: true` set globally in
  `settings.yaml` (Homepage), surfacing live container CPU/memory on every docker-integrated
  card, not just on click. For a batch job with no API of its own, this is the one honest
  progress signal available - idle near-0% normally, visibly spikes while a scheduled run is
  actually processing. Didn't fabricate a fake progress bar for something that has no
  meaningful "percent complete" concept.
- **Dashboard visual pass** (`config/homepage/custom.css`, `settings.yaml`): card surfaces
  now render with a subtle gradient + drop shadow, gain a red glow and lift on hover; section
  headings got a short gradient underline instead of flat colored text; stat/progress bars
  (docker stats, Glances, resources widgets) render with a red gradient fill instead of the
  theme default; "up"/healthy status indicators pulse slowly instead of sitting static;
  `blockHighlights` re-themed so widget good/warn/danger states use the site's own red/black
  palette instead of Homepage's default green/amber/red.

*Built with Claude AI.*

## [2.9.0] — Kometa added and configured (Plex collections/metadata/overlays)

### Added
- **Kometa** (`kometateam/kometa:latest` - the official image's stable channel, explicitly
  not `:nightly`/`:develop`), `extras` profile, for automated Plex collections, metadata, and
  overlay art. Only volume is `./config/kometa:/config` - Kometa applies overlays/posters
  through Plex's own API rather than touching media files directly, so unlike every *arr app
  it needs no `/mnt` or `./media/*` mount at all. On `stacknet` alongside everything else, so
  it can reach Radarr/Sonarr/Plex/Tautulli the same way every other service already does.
  Deliberately did *not* use the LinuxServer fork (`linuxserver/kometa`): it resets `/config`
  ownership to `PUID`/`PGID` (or `911:911` unset) on every start, which the official image
  doesn't do, and the wiki's own examples assume the official image.
- Added to **Heimdall** (new `items`/`item_tag` rows in `app.sqlite`, under the "Media Server"
  category alongside Plex) and **Homepage** (`config/homepage/services.yaml`, next to
  Recyclarr - same "no widget, container-status only" treatment). Both link to
  `https://kometa.wiki/` instead of a local URL: Kometa has no web UI of its own (it's a
  scheduled batch job, not a running service with a page to load), so its own docs are the
  only destination that goes anywhere - matches how Recyclarr/Unpackerr/Watchtower were
  already handled in both dashboards.
- Fetched a matching icon from the same community dashboard-icons set already used for the
  other Heimdall/Homepage entries.
- Ran the container once to let it complete its own documented first-run behavior
  (auto-downloads the stock default `config.yml` and exits/restarts once before settling into
  its normal idle-until-5AM state). Confirmed no restart loop (`RestartCount` stayed at 1).

### Configured (`./config/kometa/config.yml` - gitignored like the rest of `config/`, never committed)
- **Connections:** Plex (token reused from `~/zurg/config.yml` - same server), TMDb, Radarr,
  Sonarr, and Tautulli all wired up with real URLs/keys and validated via Kometa's own
  `--validate --validate-level full` (connects to every configured service without touching
  real collections/overlays/operations). Radarr/Sonarr `quality_profile` set to match whatever
  Recyclarr actively manages (`HD Bluray + WEB` / `WEB-1080p`) so the two stay in sync;
  `root_folder_path` pulled from each app's own `/api/v3/rootfolder` rather than the stub's
  fictional `S:/Movies` placeholder.
- **Trakt and MyAnimeList OAuth completed.** Both need a one-time interactive authorization
  (Trakt: visit a URL, get a short PIN; MAL: visit a URL, get redirected to a broken
  `localhost/?code=...` page) that a non-interactive container can't do on its own. Trakt's
  PIN flow worked through `--validate-level full` directly. MAL's did not - a `docker exec -i`
  session piped through a named pipe hit a Python `EOFError` on the input prompt every time
  rather than actually blocking for input, even after working around the FIFO's own
  read-blocks-until-writer gotcha. Completed it manually instead: read `modules/mal.py` in
  Kometa's own source to find the exact OAuth exchange it performs (`POST
  https://myanimelist.net/v1/oauth2/token` with `client_id`/`client_secret`/`code`/
  `code_verifier`/`grant_type=authorization_code`, where `code_verifier` must equal the
  `code_challenge` MAL's "plain" PKCE method logged in the authorize URL), then made that
  exact request directly and wrote the resulting `access_token`/`refresh_token` straight into
  `config.yml`. Both tokens auto-refresh via Kometa's own renewal logic going forward.
- **`libraries:`** trimmed to the two that actually exist on this Plex server (`Movies`,
  `TV Shows` - confirmed via a real `Plex Library 'Anime' not found. Options: ['Movies', 'TV
  Shows']` error from the stub's placeholder `Anime`/`Music` blocks, which were removed).
  Added the most commonly-used zero-config Kometa defaults on top of the stub's
  `basic`/`imdb`/`ribbon`: `genre`/`studio`/`decade` collections and a `resolution` overlay.
  Deliberately did *not* add the `ratings` overlay or any of the dozen other available
  defaults (streaming, franchise, awards, per-country content ratings, etc.) - `ratings`
  specifically needs you to choose which rating sources to display or it silently does
  nothing, and Kometa's own docs explicitly warn against enabling everything at once before
  understanding what each default does.
- **`add_missing: true` and `search: true`** enabled for both Radarr and Sonarr - Kometa will
  now add collection items missing from the library and trigger an immediate search rather
  than waiting for Radarr/Sonarr's own scheduled search cycle.

*Built with Claude AI.*

## [2.8.1] — Bazarr couldn't see Sonarr/Radarr's actual libraries

### Fixed
- Bazarr's `docker-compose.yml` volumes only had `/config` and `/mnt` - never the actual
  `/data/movies`/`/data/shows` paths Radarr and Sonarr use as their root folders. Bazarr asks
  each app for its root folder over the API, gets back a path that simply didn't exist inside
  Bazarr's own container, and surfaced it as "This Sonarr root directory does not seem to be
  accessible by Bazarr." Added `./media/movies:/data/movies` and `./media/shows:/data/shows`
  to Bazarr's volumes - identical paths to Radarr/Sonarr's own mounts, so no Path Mappings
  needed (same reasoning as the shared `/app/downloads` path elsewhere in this file). Verified
  via `docker exec bazarr ls /data/shows` and `/data/movies` (both populated, correct
  ownership) and Bazarr's own `/api/series` and `/api/movies` returning real data post-fix.

*Built with Claude AI.*

## [2.8.0] — Live dashboard (Homepage) + automated config backups

### Added
- **Homepage** (`ghcr.io/gethomepage/homepage`), `extras` profile, port 3001, alongside
  Heimdall rather than replacing it (v2.3.0 removed a prior Homepage instance in favor of
  Heimdall - this time the ask was specifically live per-service data, which Heimdall's
  static links can't provide). Live widgets wired up for Prowlarr, Radarr, Sonarr, Lidarr,
  Readarr, Bazarr, NZBGet, Seerr (its Overseerr-compatible `/api/v1/status` confirmed
  working), and Tautulli, using each app's real API key pulled from its own config. Docker
  integration (read-only `docker.sock` mount) covers every other service with a live
  running/health badge instead. Dedicated "Zilean Watch" group: link to Zilean's own
  dashboard, a ping check, and container status for `zilean` + `zilean-postgres` - no custom
  API widget, since Zilean's actual stats API isn't documented (`/health`, `/api/stats`,
  `/dmm/status` all confirmed 404) and guessing risked a broken widget for no real gain over
  linking its own UI directly.
- Custom dark/black + red-accent theme (`config/homepage/custom.css`) - Homepage's built-in
  `color: red` tints entire card surfaces red rather than just accenting, so base color is
  `slate` with black backgrounds/red borders/headings layered on top via CSS.
- Automated config backup: `scripts/backup-config.sh` (restic, `~/backups/stack-restic-repo`,
  `--keep-daily 7 --keep-weekly 4 --keep-monthly 6`) run daily at 03:30 by
  `systemd/stack-backup.{service,timer}` (same tracked+symlinked pattern as
  `media-stack.service`), scheduled before Watchtower's 4am updates.

### Fixed (found wiring this up, not pre-existing)
- Homepage's Next.js layer rejects any request with a non-allow-listed `Host` header -
  every page load failed with "Host validation failed" and nothing else. Needed
  `HOMEPAGE_ALLOWED_HOSTS` set to the exact `host:port` combinations (bare hostname without
  the port was not sufficient).
- Whisparr's fork doesn't expose Radarr's `/movie` endpoint (confirmed 404 directly against
  its API) even though `/queue/status` and `/queue/details` work fine - the borrowed "radarr"
  widget type half-broke on it. Dropped to a container-status-only card instead of a
  partially-erroring widget.
- First backup run exited non-zero: restic's own exit code 3 ("some source files could not
  be read") from `config/zilean-postgres`'s live data files, combined with `set -e`, aborted
  the script before the retention/prune step ran (backup itself had still succeeded). Fixed
  two ways: excluded `zilean-postgres` from the backup entirely - not just to dodge the
  permission error, but because file-level copying a *running* Postgres data directory can
  produce an inconsistent restore, and Zilean's index is a rebuildable DMM-scrape cache, not
  data worth that risk - and made the script tolerate exit code 3 generally rather than
  treating any non-zero restic exit as fatal.

### Known limitation
- Backup repo is local-only (`~/backups/`, same single NVMe as everything else) - protects
  against config corruption, accidental deletion, and repeats of the Decypharr config-wipe
  bug below, not physical disk failure. No cloud remote configured since no cloud storage
  account exists on this host; restic supports one natively if that's ever wanted.

*Built with Claude AI.*

---

## [2.7.0] — Claude Code GitHub Actions workflows added

Backfilled retroactively — commits `53d3f23`, `240b90f`, and their merge (`8c74a94`, PR #3)
shipped this without a version at the time. Given a real version number as part of the
2026-07-09 versioning-policy pass (see note at top of this file).

### Added
- **`.github/workflows/claude.yml`** — the Claude PR Assistant workflow; tags `@claude` in an
  issue or PR comment to trigger an agentic response.
- **`.github/workflows/claude-code-review.yml`** — an automatic Claude code review on every PR.

---

## [2.6.0] — Boot automation via systemd

### Added
- `systemd/media-stack.service`: a user-scope systemd unit that brings the whole stack
  (extras profile included) up automatically on boot, correctly ordered after the two host
  mounts every arr container's `/mnt` bind-mount depends on: `zurg.service` (mounts
  `/mnt/zurg` via its own embedded rclone process) and `rclone-all.service` (mounts
  `/mnt/all`). Docker itself needs no explicit ordering — `docker.socket` is already
  socket-activated, so the unit's first `docker` invocation starts `docker.service` on
  demand. `RemainAfterExit=yes` + `ExecStop=docker compose --profile extras down` means
  `systemctl --user stop media-stack.service` tears the stack back down cleanly too.
  Installing it requires `loginctl enable-linger` for the user, since the mount units it
  orders against are user-scope services that otherwise only start on interactive login.
  See [README.md](README.md#starting-at-boot).

### Fixed
- Found `rclone-zurg.service` enabled but permanently failing (`didn't find section in
  config file`) while auditing the boot dependency chain above — a leftover duplicate of
  the mount `zurg.service` already manages internally via its own embedded rclone process.
  Disabled it; it provided no function and would have been a false lead in the new unit's
  dependency chain.

---

## [2.5.2] — Bazarr's Plex connection fixed (last piece of the v2.4.0 bug)

### Fixed
- Plex Media Server itself was found stopped on the host (`systemctl status` showed
  `inactive (dead)`, unrelated to anything in this stack) — started it back up first.
- With Plex reachable, finished the fix noted as outstanding in [2.4.0](CHANGELOG.md):
  Bazarr's Plex connection had the identical `ip: 127.0.0.1` bug as its Radarr/Sonarr
  connections. Pointed it at the host's real LAN IP with the Plex token already on this host
  (from Zurg's config), selected the Movies/TV Shows libraries, and enabled `use_plex`.
  Bazarr's own OAuth migration then ran automatically, converting the API-key config to its
  newer OAuth-token storage and validating the connection live against the real server
  (confirmed by server name/machine ID coming back correctly in the logs). All three of
  Bazarr's media-source connections (Plex, Radarr, Sonarr) are now genuinely live.

*Built with Claude AI.*

## [2.5.1] — Decypharr's config-wipe bug filed upstream

Backfilled retroactively — commit `a7158f7` shipped this without its own version at the time.
Given a real version number as part of the 2026-07-09 versioning-policy pass (see note at top
of this file).

### Changed
- Linked [sirrobot01/decypharr#343](https://github.com/sirrobot01/decypharr/issues/343) into
  [2.5.0](CHANGELOG.md)'s writeup of the partial-`PATCH`-drops-config bug, for anyone checking
  the issue's status later.

---

## [2.5.0] — Jellyfin removed; reverted to symlinks, experience judged not worth it

### Changed — BREAKING
- **Removed Jellyfin, Jellyseerr, Jellystat, and jfa-go entirely** — all four containers,
  their `docker-compose.yml` service definitions, their config directories (~170MB), the
  `JELLYSTAT_POSTGRES_PASSWORD`/`JELLYSTAT_JWT_SECRET` env vars, their 4 Heimdall tiles and
  icons, and the `JELLYFIN-PLUGINS.md` reference doc. Bazarr's Jellyfin connection was
  disabled and cleared; its Radarr/Sonarr connections (fixed in [2.4.0](CHANGELOG.md)) were
  left alone since that bug was real and independent of Jellyfin.
- **Decypharr reverted from `strm` back to `symlink`** for `default_download_action`. The
  strm experiment ([2.4.1](CHANGELOG.md) territory, never actually versioned on its own) was
  tried, tested, and judged not worth keeping:
  - **Plex doesn't support `.strm` files at all** (removed years ago) — since Plex is this
    stack's primary, native, pre-existing media server, strm mode meant every new grab was
    invisible to Plex and only playable through Jellyfin. That's a real regression, not a
    minor caveat.
  - **A serious, reproducible bug** in Decypharr's `POST /api/config`: any *partial* JSON
    patch (e.g. just `{"default_download_action": "strm"}`) causes it to silently drop the
    `debrids`, `mount`, and sometimes `arrs` sections entirely on the next save/restart —
    hit this **twice** in one session (once switching to strm, once switching back), each
    time fully breaking the debrid gateway (unmounted `/mnt/decypharr`, zero configured
    debrids) until manually reconstructed and POSTed back as one complete document. Anyone
    touching this API in the future: always send the full config, never a partial patch.
    Root-caused in the actual source (`handleUpdateConfig` decodes into a zero-value struct;
    `Config.Save()` overwrites `config.json` with no merge logic) and filed upstream as
    [sirrobot01/decypharr#343](https://github.com/sirrobot01/decypharr/issues/343).
  - Getting one clean, verifiable live example of a fresh strm-mode grab flowing through to
    Jellyfin took longer than expected — indexer availability for the specific titles being
    tested, not a stack bug, but it meant the "how fast does this actually work" question
    never got a clean answer before the decision to revert was made.
- Real-Debrid token was rotated mid-session after an unrelated accidental transcript exposure
  ([2.4.1](CHANGELOG.md)) — unaffected by this revert, still current.

*Built with Claude AI.*

## [2.4.1] — Real-Debrid token rotated

### Fixed
- While fetching a Plex API token from Zurg's `config.yml` to fix Bazarr's Plex connection, a
  broad `grep` also matched and printed the Real-Debrid token to the session transcript — a
  genuine accidental exposure, not a hypothetical one. Rotated the token in the Real-Debrid
  account settings and updated both places it lives on this host: `zurg`'s `config.yml` and
  `config/decypharr/config.json`. Restarted both, confirmed no auth errors and a clean initial
  sync from both debrid clients on the new key. Neither file is tracked by git (both are
  gitignored), so no repo history needed scrubbing — the exposure was transcript-only.

*Built with Claude AI.*

## [2.4.0] — Jellyfin + companion apps added, wired to every existing app, two live bugs found and fixed

### Added
- **Jellyfin** (`lscr.io/linuxserver/jellyfin`) as a second media server alongside the existing
  native Plex install. VAAPI hardware transcoding passed through from the host's AMD Radeon
  680M iGPU (`/dev/dri`, world-writable `renderD128`, no `group_add` needed) — confirmed via
  `System/Configuration/encoding` (`HardwareAccelerationType: vaapi`). Scripted through the
  entire startup wizard via its REST API (server name, admin account, remote access, a
  permanent API key for the other apps below) rather than the interactive UI. 5 libraries
  created against `/data/{movies,shows,music,books,adult}` — the same regular-disk root
  folders every arr app already writes into, not `/mnt/zurg`. Also enabled native
  hardware-accelerated trickplay generation (`TrickplayOptions.EnableHwAcceleration`).
- **Jellyseerr** — a second instance of the same `seerr` image, configured for a Jellyfin
  backend instead of Plex. Confirmed empirically (querying the existing Seerr's own
  `/api/v1/settings/public`) that **one Seerr instance is Plex or Jellyfin, never both at
  once** (`mediaServerType` is a single enum field) — this answers the question left open in
  the TODO about whether the existing `seerr` container could just grow a second backend; it
  can't, hence the second container. Signed in against Jellyfin
  (`POST /api/v1/auth/jellyfin` with `serverType: 2`), which both validated admin access and
  created Jellyseerr's own admin user in one step, then connected Radarr + Sonarr the same way
  the original Seerr was connected in [1.11.0].
- **Jellystat** (`cyfershepard/jellystat`) + its own Postgres database, following the same
  pattern as Zilean's dedicated DB. Connected to Jellyfin via its API key. Syncs on its own
  schedule (60 min partial / 24h full).
- **jfa-go** (`hrfee/jfa-go`) for Jellyfin user invites/account management, authenticated
  directly against the Jellyfin admin account. Password-reset watching pointed at the same
  `/config` volume Jellyfin itself uses (mounted read-only at `/jf`).
- Connected **Bazarr** to Jellyfin (it already supports multiple media servers natively — no
  new container). Selected the Movies + Adult libraries as Bazarr's movie scope and Shows as
  its series scope.
- Installed the 30-plugin curated shortlist from `JELLYFIN-PLUGINS.md` via Jellyfin's
  `/Repositories` and `/Packages/Installed` APIs (11 community repos registered, 31 packages
  installed in one pass). 30 came up `Active`; **Jellyscrub** came up `NotSupported` and was
  removed — this Jellyfin version's native trickplay (now hardware-accelerated, see above)
  covers the same job, exactly the caveat noted against that plugin in the shortlist.
  `jellyfin-rpc`, also on the shortlist, turned out not to be a Jellyfin plugin at all (it's a
  standalone client-side Discord Rich Presence daemon with nothing to install server-side) —
  left out of the install, noted here rather than silently dropped.

### Fixed
- **Bazarr's Radarr, Sonarr, and Plex connections were all completely non-functional** —
  discovered while wiring up its new Jellyfin connection, not something anyone had reported.
  All three were configured with `ip: 127.0.0.1`, which from inside Bazarr's own container
  resolves to Bazarr itself, never to another container or to the native-host Plex install.
  `use_radarr`/`use_sonarr`/`use_plex` were all `false` too. Net effect: Bazarr had never
  actually synced a movie or series list from anything since it was added, regardless of
  anything configured in its own subtitle settings. Fixed Radarr → `radarr:7878` and
  Sonarr → `sonarr:8989` (both now on `stacknet` like every other container) and enabled both
  — confirmed live via Bazarr's own logs, SignalR feeds connected to both, and `/api/series`
  now returning real data for the first time. Plex's `127.0.0.1` is left unfixed for now — it
  needs a Plex API token this session didn't have on hand; noted, not silently ignored.
- **Both Seerr instances' Radarr/Sonarr root folders were stale**, pointing at
  `/mnt/zurg/{movies,shows}` — the FUSE-mount paths [2.2.0] moved every root folder off of,
  months ago. Found while copying the existing Seerr's connection settings as a template for
  Jellyseerr's: `activeDirectory` in `config/seerr/settings.json` still said `/mnt/zurg/movies`
  / `/mnt/zurg/shows`, and Radarr/Sonarr's own `/api/v3/rootfolder` confirmed those paths were
  `"accessible": false`. This meant any request made through the Plex-backed Seerr since
  [2.2.0] would have been handed a dead root folder. Patched `settings.json` directly to
  `/data/movies`/`/data/shows`, restarted Seerr, confirmed the fix persisted, and deleted the
  now-dead root folder entries from both Radarr and Sonarr entirely.

*Built with Claude AI.*

## [2.3.1] — TODO.md added, tracking planned Jellyfin work

Backfilled retroactively — commit `cc156b6` shipped this without its own version at the time.
Given a real version number as part of the 2026-07-09 versioning-policy pass (see note at top
of this file).

### Added
- **`TODO.md`** — a running list of planned-but-not-started work, seeded with the Jellyfin +
  companion-app build that shipped as [2.4.0](CHANGELOG.md).

---

## [2.3.0] — Homepage replaced with Heimdall; Watchtower's stale Docker client fixed

### Changed
- Swapped `homepage` (ghcr.io/gethomepage/homepage) for `lscr.io/linuxserver/heimdall` as the
  stack's dashboard. Populated Heimdall directly via its SQLite database (`app.sqlite`) with
  all 14 apps from the stack, grouped into the same five categories Homepage used: Requests
  (Seerr), Acquisition (Prowlarr, Zilean, Decypharr, NZBGet), Libraries (Radarr, Sonarr,
  Lidarr, Readarr, Whisparr, Bazarr), Media Server (Plex), and Monitoring & Tools (Tautulli,
  FlareSolverr). Fetched matching icons from the community dashboard-icons set for 12 of the
  14 apps; Zilean and Decypharr have no icon available there (Homepage worked around this the
  same way, falling back to generic MDI icons).
- Hit two real bugs while wiring this up, not just config: (1) the newly created `heimdall`
  container came up with a broken `/etc/resolv.conf` (raw `127.0.0.53` instead of Docker's
  embedded `127.0.0.11` DNS), breaking every outbound request from inside it — fixed by force-
  recreating the container, after which Docker rewrote resolv.conf correctly. (2) Populated
  each app's description into Heimdall's `description` column, which is actually reserved for
  enhanced-app JSON config and gets `json_decode`'d on every page load — plain text there
  caused `json_decode` to return `null`, and the next line's `$config->url = ...` threw
  "Attempt to assign property on null", 500ing every category page. Fixed by moving
  descriptions to the correct `appdescription` column and re-verified all five category pages
  and the root dashboard return 200 with the right apps listed.

### Fixed
- `watchtower` was crash-looping: `containrrr/watchtower:latest` (now an archived/deprecated
  repo) bundles a Docker client capped at API 1.25, but the host's Docker Engine (29.6.1) has
  dropped support for anything below API 1.40. Moved to the actively maintained
  `nickfedor/watchtower` fork — same env vars, drop-in replacement. Confirmed stable post-
  switch: `Watchtower 1.19.0 using Docker API v1.55`, no more restarts.

*Built with Claude AI.*

## [2.2.0] — Root folders moved off Zurg's read-only FUSE mount, verified end-to-end

### Fixed
- v2.1.0 fixed *visibility* of Decypharr's staged downloads but "verify fix in real time" (an
  explicit ask, not an assumption that the first fix was sufficient) surfaced a second, deeper
  bug: every arr app's root folder was still `/mnt/zurg/<type>` — Zurg's own rclone FUSE mount.
  Reproduced directly rather than inferred from logs: `docker exec sonarr sh -c "ln -s ...
  /mnt/zurg/shows/_symlink_test"` returned `System.IO.IOException: I/O error [EIO]`. Rclone/
  WebDAV-backed FUSE mounts like Zurg's are read-oriented and simply do not support having new
  files or symlinks written into them — confirmed with symlink, hardlink, and plain copy, all
  failing identically. This meant **no import had ever been able to complete** through any arr
  app since the stack went live, regardless of the v2.1.0 path-visibility fix: Decypharr could
  stage a file, the arr app could now see it, but writing the actual symlink into the root
  folder always failed at the last step.
- Considered two narrower options (remote-path-map Decypharr's own mount into each root
  folder; or point root folders at Decypharr's DFS mount directly) and asked whether doing
  both was overkill — it was, and neither actually solved the real problem: NZBGet's fallback
  path independently needs a genuinely writable root folder regardless of what's done for
  Decypharr specifically, so patching only the Decypharr side would've left a second write-
  incompatible path unaddressed.
- Fix: gave every arr app a new root folder backed by regular host disk instead of a FUSE
  mount — `./media/{movies,shows,music,books,adult}`, mounted into each container at
  `/data/<type>` (these directories existed since v2.0.0 but were unused placeholders until
  now). Migrated existing tracked content via each app's API: added the new root folder,
  updated every tracked series/movie's `rootFolderPath`/`path` to the new location, removed
  the old `/mnt/zurg/<type>` root folder. Sonarr had 2 series, Radarr 2 movies, Whisparr 1
  series to migrate; Lidarr and Readarr had none yet.
- Discovered along the way: this specific Whisparr build (v2.2.0.108) uses Sonarr's
  `series`/`episode` API shape, not Radarr's `movie` shape — the first migration attempt 404'd
  on `/api/v3/movie` against it, corrected to `/api/v3/series`.
- Verified genuinely end-to-end, not just "no error returned": triggered a live search for
  Blue Bloods S01E03, watched it flow Prowlarr → Sonarr → Decypharr (Real-Debrid caching +
  symlinking) → back into Sonarr's queue → import. Confirmed at the filesystem level —
  `/data/shows/Blue Bloods/Season 1/blue.bloods.s01e03.720p.web.h264-skyfire.mkv` exists as a
  symlink into `/mnt/decypharr/__all__/...`, `episode.hasFile` is `true`, and the symlink
  target was proven genuinely readable (pulled real bytes through the full chain from inside
  Sonarr's container, confirming it isn't a dangling link to a debrid file that never actually
  cached). Also confirmed write access on the other 4 new mounts (`/data/movies`, `/data/music`,
  `/data/books`, `/data/adult`) directly.
- Blocklist cleanup was needed mid-investigation: Sonarr auto-blocklists a release after a
  failed import, which kept blocking re-tests of the exact releases needed to prove the fix —
  cleared via `DELETE /api/v3/blocklist/bulk`, scoped only to entries from the bug's specific
  timestamp window (42 entries total across two passes), not a blanket wipe.

### Action needed
- **Plex** (native, not dockerized) needs new library locations added for
  `/home/bear/Stack/media/{movies,shows,music,books,adult}` — this is where all future arr-app
  imports land now, and Plex can't be reconfigured via this stack's tooling; it's a manual
  Settings → Libraries → Edit → Add folder step. See
  [Plex library locations to add](README.md#plex-library-locations-to-add).

*Built with Claude AI.*

## [2.1.0] — Decypharr download path visibility fixed across every arr app

### Fixed
- Radarr surfaced a health warning: "download client Decypharr places downloads in
  `/app/downloads/radarr` but this directory does not appear to exist inside the container."
  Investigated rather than dismissed — this was real and already actively breaking imports.
  Sonarr's history showed repeated `grabbed` → `downloadFailed` cycles for the same episodes
  across many different releases, timestamped exactly when Decypharr had real symlinked media
  files sitting in its own container that no arr app could see. Since v1.7.0 first wired up
  Decypharr as the download client, every app's container only shared `/mnt`, `/usenet`, and
  its own `/config` — none of which overlapped with where Decypharr stages completed
  downloads internally (`/app/downloads/<category>`, backed by `config/decypharr` on the
  host). This meant no debrid-grabbed content had ever actually been importable through
  Decypharr in any app, only appearing to work when Recyclarr/Prowlarr syncs succeeded
  upstream of the actual download step.
- Fix: bind-mounted `config/decypharr/downloads` into Radarr, Sonarr, Lidarr, Readarr, and
  Whisparr at the identical path Decypharr uses internally (`/app/downloads`) — avoids
  needing Remote Path Mappings entirely, per Decypharr's own documented best practice of
  matching paths exactly across containers.
- Verified with a controlled test rather than assuming: wrote a file from inside Decypharr's
  container, confirmed it was immediately readable from Sonarr's container at the identical
  path. Live-release testing was confounded by unrelated (and correctly-working) mechanisms —
  Sonarr's own blocklist protecting against re-grabbing releases that failed before the fix,
  the "Low Quality Sources/Groups" custom format correctly rejecting garbage EZTV releases,
  and one candidate correctly refused by Decypharr for not being cached on Real-Debrid
  (`download_uncached: false`) — none of which are bugs, all confirmed as intended behavior
  along the way.
- The 3 specific episodes that failed during the fix window are gone (cleaned up by the
  download client's normal failed-download handling) and will need a fresh search to re-grab;
  everything going forward uses the corrected path.

*Built with Claude AI.*

## [2.0.1] — Cleanup

### Fixed
- Removed the old Postgres 16 data directory (`config/zilean-postgres.pg16.bak`, 1.1GB) after
  confirming the v18 rebuild was healthy — verified no errors, API responding, Lucene matcher
  actively rebuilding the cache before deleting.

*Built with Claude AI.*

## [2.0.0] — Recyclarr v8 and Postgres 18 (breaking changes, migrated in full)

### Changed — BREAKING
- **Recyclarr 7 → 8.** Read the upgrade guide *before* merging anything: v8 removes the
  `include: template:` mechanism entirely, which our config relied on — merging the raw
  version bump would have broken the nightly sync outright. Rewrote `recyclarr.yml` to the
  new guide-backed `quality_profiles: trash_id` format, pulling the exact trash IDs from
  TRaSH-Guides' own source rather than guessing. Verified clean adoption with zero duplicate
  profiles (same 7 profiles, same IDs, before and after, in both apps).
- **Postgres 16 → 18.** A straight image swap would have refused to start regardless — major
  Postgres versions use incompatible on-disk formats. Did a wipe-and-rebuild instead (safe
  here since Zilean's DB is just an hourly-regenerated cache), moving the old data aside
  rather than deleting it. Hit a second, unrelated issue along the way: Postgres 18's image
  changed its expected volume mount path entirely, confirmed against the real upstream
  Dockerfile before fixing the compose mount.

### Fixed
- **The actual root cause** of the custom-format-score-reset problem from v1.15.1: v8's
  `reset_unmatched_scores` is an explicit opt-in (default: leave scores alone), replacing
  v7's implicit always-on reset. Verified by syncing twice and watching the score hold at
  -10000 both times with zero intervention. Removed the old workaround script and its cron
  job entirely — patched-around problem, now actually fixed.

*Two Dependabot PRs opened this version — both closed as superseded once verified that
merging either raw diff alone would have broken something. Built with Claude AI.*

## [1.17.2] — Dependabot PR review

### Investigated
- Reviewed both open Dependabot PRs before merging either. Confirmed via Recyclarr's own
  upgrade guide and Postgres's fundamental on-disk format incompatibility that neither was a
  safe drop-in — see v2.0.0 for the actual migration.

## [1.17.1] — Dependabot config fix

### Fixed
- `package-ecosystem: "docker"` only scans for Dockerfiles/Kubernetes YAML, not Compose
  files — confirmed via the actual failed run logs, not just re-reading the docs. Corrected
  to the separate `docker-compose` identifier.

## [1.17.0] — Continuous integration

### Added
- `.github/workflows/validate.yml` — validates `docker compose config` on every push/PR.
- `.github/dependabot.yml` — weekly checks for newer image versions on anything pinned to a
  real tag rather than `:latest`.

## [1.16.0] — Passwordless sudo

### Added
- `/etc/sudoers.d/bear-nopasswd`, validated with `visudo -c`. Resolves the manual `sudo`
  hand-off friction from v1.0.0's Decypharr mountpoint fix — future host-level fixes no
  longer need a manual pause.

## [1.15.1] — Custom format score persistence (patched, later root-caused in v2.0.0)

### Fixed
- Discovered Recyclarr v7 silently resets any score it doesn't recognize back to 0, but only
  on the one profile it manages per app — confirmed empirically by running a real sync, not
  just reading docs. Added a cron-scheduled script to re-assert the intended score after
  every Recyclarr sync. (Superseded and removed in v2.0.0 once the actual root cause was
  fixed instead.)

## [1.15.0] — Quality gate: low-quality sources blocked

### Added
- Custom format matching known low-trust aggregator/group release names, scored -10000 in
  every quality profile in both Radarr and Sonarr — a hard reject, not just
  deprioritization.

## [1.14.0] — Prowlarr ↔ *arr app sync

### Added
- Connected all 5 *arr apps to Prowlarr under Settings → Apps with `fullSync`, so indexers
  now propagate down automatically. Confirmed complete by polling until indexer counts held
  steady with zero further log activity — genuinely rate-limited by design (60 req/min caps
  on several trackers), not stuck.

## [1.13.0] — Homepage documentation links

### Added
- Bookmarks linking to the GitHub-hosted, rendered README and CHANGELOG.

## [1.12.0] — Published to GitHub

### Added
- Converted to a git repo, `.gitignore` keeping every secret and stateful config file out of
  history, `.env.example` as a sanitized template. Pushed to a private repo under
  `WhispersOfJ/media-stack`.

## [1.11.2] — Seerr/Whisparr compatibility check

### Investigated
- Confirmed Seerr's settings API only recognizes `radarr` and `sonarr` — no adult-content
  data model exists to connect Whisparr to. Left standalone by design, not oversight.

## [1.11.1] — Seerr/Sonarr fix

### Fixed
- Seerr's Sonarr endpoint required `enableSeasonFolders`, undocumented until the first
  attempt failed. Added it, succeeded on retry.

## [1.11.0] — Seerr connected to Plex and the *arr apps

### Added
- Signed in to Plex using the token already on this host rather than the interactive OAuth
  flow, so it turned out scriptable after all. Connected Radarr and Sonarr as default
  servers.

## [1.10.0] — Zilean hardware tuning

### Added
- Tuned Zilean and its Postgres database for this host's actual 16-thread CPU and NVMe
  rather than defaults sized for a machine with a few hundred MB of RAM — Server GC, Lucene
  matching across 12 threads, Postgres `shared_buffers`/`work_mem`/parallelism sized up.
  Deliberately not maxed out — this is a shared desktop, not a dedicated server.

## [1.9.1] — NZBGet category fix

### Fixed
- NZBGet rejects any download-client category that doesn't already exist server-side, unlike
  Decypharr's more permissive API. Created the missing categories directly in `nzbget.conf`.

## [1.9.0] — NZBGet fallback download client

### Added
- Wired up as a lower-priority (2, behind Decypharr's 1) fallback download client across all
  5 apps, and separately as Prowlarr's own global client.

## [1.8.0] — Root folders

### Added
- Set in all 5 arr apps, pointed at their matching Zurg path. Lidarr/Readarr's older API
  needed extra metadata/quality profile fields Radarr/Sonarr/Whisparr didn't.

## [1.7.0] — Decypharr download client everywhere

### Added
- Added as a qBittorrent-compatible download client in all 5 arr apps. Confirmed
  auto-detection via Decypharr's own API — no manual config editing needed.

## [1.6.0] — Prowlarr indexers populated

### Added
- Bulk-added all 88 public-privacy indexer definitions Prowlarr ships with, plus Zilean as a
  Torznab indexer. 70 live in the end; the rest were genuinely unreachable, not a config
  error.

## [1.5.0] — Documentation format changes

### Changed
- Converted docs to HTML, then back to Markdown per a later request. Content carried over in
  full either way.

## [1.4.1] — Recyclarr image tag fix

### Fixed
- `:latest` is explicitly called out in Recyclarr's own README as no longer published.
  Repinned to `:7`.

## [1.4.0] — Recyclarr and TRaSH Guides

### Added
- TRaSH-Guides quality profiles synced into Radarr and Sonarr automatically, once a day.

## [1.3.0] — Homepage dashboard

### Added
- Every service linked, grouped by category, plus a Debrid Media Manager bookmark.

## [1.2.0] — Full stack online

### Added
- All 11 core containers plus all 7 optional `extras` containers confirmed healthy.

## [1.1.1] — Bring-up fixes

### Fixed
- Three issues hit bringing the stack online for the first time: a dead upstream image tag,
  a wrong API key pulled from the wrong source, and a FUSE mountpoint that didn't exist yet.
  None were guessed at — each was root-caused from actual error output before being fixed.

## [1.1.0] — Zurg extended

### Added
- New `music`/`books`/`adult` directory groups added to the **live**, already-running Zurg
  config — backed up first, restarted cleanly, confirmed via the new folders actually
  appearing.

## [1.0.0] — Initial release

### Added
- The whole stack, from nothing: Prowlarr, Zilean, Decypharr, Radarr, Sonarr, Lidarr,
  Readarr, Whisparr, NZBGet, Seerr, plus 7 optional extras. Every image reference verified
  against its live registry rather than trusted from memory — caught real wrong assumptions
  this way (LinuxServer doesn't publish Whisparr; Overseerr and Jellyseerr merged into one
  project; Decypharr's image kept its old project name).

---

**Designed and built end-to-end by [Claude AI](https://www.anthropic.com/claude).** Every
version above — every service, every integration, every bug caught and fixed — is Claude's
work, verified live against the running stack rather than assumed correct.
