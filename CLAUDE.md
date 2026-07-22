Read existing files before writing. Don't re-read unless changed.
Thorough in reasoning, concise in output.
Skip files over 100KB unless required.
No sycophantic openers or closing fluff.
No emojis or em-dashes.
Do not guess APIs, versions, flags, commit SHAs, or package names. Verify by reading code or docs before asserting.


# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Docker Compose media-acquisition-and-serving stack (16 services, one `docker-compose.yml`):
indexes content via Prowlarr, requests via Seerr, organizes via two `*arr`-family apps
(Radarr/Sonarr — Lidarr was removed entirely in v10.9.9 and Whisparr in v10.12.0, see below;
Bindery, the ebook `*arr`, was retired in v10.9.8 along with its reader Calibre-Web; no ebook app
currently in the stack), fetches via Usenet (NzbDAV) exclusively, and serves via a containerized
Plex. **Torrent and debrid support (Decypharr, Zurg, rclone-alldebrid, Zilean, zilean-postgres,
Byparr) was removed entirely in v11.0.0, by explicit request** — every future acquisition goes
through NzbDAV, no exceptions (see the landmines/History sections below for the full removal,
including a real consequence found mid-execution: those apps never downloaded real bytes, only
symlinked into a live FUSE mount streamed from the debrid provider, so removing them
immediately broke playback for the ~3.65% of the library that was debrid-sourced, not just
future acquisitions). Usenet had already been the preferred protocol since a v10.14.1 policy
change (a deliberate reversal of the stack's original debrid-first design) before this final
removal. There is no adult content library in this stack anymore: Plex's own Adult library was
removed in v10.9.9 (confirmed live via `/library/sections`), and Whisparr (which managed the
underlying files/root folder) plus Stash (which cataloged it) were both removed in v10.12.0,
along with the files themselves. There is no anime library in this stack either as of v10.19.0
(also removed by explicit request, not a dead-app cleanup — see the landmines section below),
and no self-hosted DebridMediaManager as of v10.20.0 (same reasoning, same section).
`control-panel/` is the one custom-built component (a FastAPI dashboard); everything else is
off-the-shelf images wired together in `docker-compose.yml`.

**`README.md` is the only documentation in this repo besides raw config** — it merges what used
to be README/TECHNICAL/CHANGELOG into one document, organized by subsystem, ~1,900 lines with a
linked table of contents. Read the relevant section there before making changes; this file only
covers what you need to get oriented and the things that aren't obvious from reading one file in
isolation.

**This stack has no public downstream mirror — see `AGENTS.md`.** `StackMaster` (and before it,
`Stackalicious`/`StackScripts`) were deleted outright from GitHub, most recently 2026-07-21,
for privatization. Every `stack-*` command lives only in this host's own fish functions plus
this repo's `control-panel/app.py` — nothing to mirror anywhere.

## Full service inventory (all 16, by subsystem)

Not a duplicate of README's service table (image/port/profile) — this is the *relationship*
map: what each service actually talks to, so a question about any one container can be
answered without re-reading `docker-compose.yml` end to end. `core` = no `profiles:` line,
comes up on a bare `docker compose up -d`; `extras` = needs `--profile extras`.

**Indexing** — `prowlarr` (core, indexer manager, pushes indexers to Radarr/Sonarr via
`fullSync`; Usenet indexers only as of v11.0.0 — every torrent indexer, plus the `Zilean`
Torznab entry, was disabled then deleted, see the landmines/History sections).

**FUSE mount owners** — `nzbdav-rclone` (core, mounts NzbDAV's own WebDAV filesystem at
`/mnt/nzbdav`, `depends_on: condition: service_healthy` on `nzbdav` itself, not just compose
start-order — the only FUSE mount left in this stack as of v11.0.0).

**`*arr` apps** — `radarr` (core, port 7878, movies, `/data/movies`) ·
`sonarr` (core, port 8989, TV, `/data/shows`) — both single-quality-profile ("ANY") as of
v11.2.0, see [History](README.md#history); Recyclarr (TRaSH Guides custom-format sync) was
removed entirely the same version, so there is no automated custom-format management on
either app anymore.

**Usenet** — `nzbdav` (core, port 3001→3000, WebDAV-streamed Usenet, SABnzbd-API compatible,
**the only download client on both Radarr and Sonarr as of v11.0.0** — was priority-1 behind
Decypharr's priority-2 fallback until debrid was removed entirely, see the top-of-file
description) · `nzbdav-rclone` (see FUSE mount owners above — same container, listed once).

**Requests** — `seerr` (core, port 5055, Radarr/Sonarr only — no adult-content or music/ebook
data model, moot now that those app families are gone anyway).

**Media server** — `plex` (core, `network_mode: host` — the one deliberate exception to this
stack's publish-to-0.0.0.0 pattern, per Plex's own Docker guidance on GDM/DLNA/NAT-PMP under
bridge networking).

**Monitoring** — `tautulli` (extras, port 8182, Plex stats/history). `beszel`/`beszel-agent`
(Glances' v10.9.9 replacement) removed entirely in v11.2.0, by explicit request — no
host/container resource-monitoring hub currently in this stack.

**Subtitles** — `bazarr` (extras, port 6767, watches Radarr/Sonarr for missing subtitles;
reinstalled from scratch in v11.3.0 after being removed entirely in v10.2.0, no prior config
survived; wired to both apps post-boot via its own `/api/system/settings` form-encoded
endpoint — see README's dedicated section for the gotchas in that endpoint before touching it
again; provider list narrowed in v11.4.0 to 9 English-capable, non-anime-exclusive sources).

**Dashboard** — `control-panel` (extras, port 8420, the one custom-built component —
`build:` from `./control-panel`, not a pulled image; talks to `docker.sock` plus every app's
own HTTP API; no auth, CSRF/Origin-Host validated only; see the dedicated gotchas section
below).

**Metadata/overlays** — `kometa` (extras, no port, `entrypoint: sleep infinity` override is
load-bearing — see landmines below; runs only via Control Panel's on-demand
`/api/kometa/run` exec, never as PID 1) · `quickstart` (extras, port 7171, image
`kometateam/quickstart:latest`, container name `kometa-quickstart` — the official Kometa-Team
wizard for building `config/kometa/config.yml` interactively; a config-editing tool, not an
alternative way to run Kometa. Its own volume, `./config/quickstart:/config`, is deliberately
separate from `config/kometa` — a config built there has to be copied by hand into
`config/kometa/config.yml`, the `kometa` service above is still what actually runs against
that file). `labelarr` (TMDb-keywords-as-Plex-labels) removed
entirely in v11.2.0, by explicit request — no item-level Plex label automation currently in
this stack; Kometa's own collections/overlays are unaffected.

**Post-processing** — `unpackerr` (extras, no port, RAR extraction for Radarr/Sonarr's
downloads).

**Auto-updates** — `watchtower` (extras, no port, digest/channel-tag images only — Plex is
deliberately excluded from its train, see Image pinning policy).

**Queue cleanup / missing-content hunting** — `cleanuparr` (extras, port 11011, strikes +
malware-block + stalled-download cleanup; its own built-in proactive search should stay
disabled so it doesn't redundantly hunt alongside NeutArr) · `neutarr` (extras, port 9705,
hardened Huntarr-lineage fork — missing/upgrade hunting exclusively; never add Huntarr proper,
see its own compose comment for the auth-bypass history).

## Commands

```bash
# Validate compose config (what CI runs) — needs a .env first, dummy values are fine
cp .env.example .env
docker compose config --quiet
docker compose --profile extras config --quiet

# Lint (what CI runs, no repo-local ruff config — defaults)
ruff check control-panel/app.py scripts/*.py
shellcheck scripts/*.sh  # CI excludes config/, media/, usenet/

# Rebuild and pick up control-panel changes — app.py AND static/ (CSS/JS/HTML) are both
# baked into the image at build time via the Dockerfile's COPY, not bind-mounted, so a plain
# `restart` serves the old files untouched even after editing them on disk.
docker compose build control-panel
docker compose up -d control-panel

# control-panel reads .env at container-*create* time only — a plain restart won't
# pick up a .env change here, it needs force-recreate
docker compose up -d --force-recreate control-panel

# Bring up the stack: 7 core services, or everything (+13 more behind the `extras` profile)
docker compose up -d
docker compose --profile extras up -d
```

There is no unit test suite anywhere in this repo — CI (`.github/workflows/validate.yml`) is
compose-config validation + ruff + shellcheck + a build-only Dockerfile check, not tests.
Verifying a change means exercising it against the real running stack (curl an endpoint, check
`docker logs`, load the dashboard) — that's the pattern this project's own README follows
throughout its history section, and there's no substitute for it here.

## Architecture facts that span multiple files

- **Root folders for every `*arr` app live on regular disk (`./media/<type>` → `/data/<type>`),
  never on `nzbdav-rclone`'s `/mnt/nzbdav` FUSE mount.** That mount is read-only in practice
  (symlink/hardlink/copy all fail there with `EIO`; used to be true of Zurg's `/mnt/zurg` mount
  too, before torrent/debrid was removed entirely in v11.0.0 — see the landmine below). This
  has regressed silently before — a library rescan can reset an item's root folder back to
  `/mnt/<mount>/...` in an app's own database, which is invisible to git since it's app state,
  not stack config. If an import mysteriously stalls, check the item's resolved root folder
  before assuming a container/mount problem.
- **A root folder is 100% symlinks, never real files — any new service that reads one needs the
  same `/mnt/nzbdav` mount every existing consumer has, not just the root folder itself.**
  Confirmed as a real bug, not a hypothetical: Stash's first deploy (before it was removed
  entirely) mounted only `./media/adult:/data`, and every symlink under it was dangling from
  inside that container's own mount namespace — a real library scan completed in seconds with
  no error and found 0 scenes, because every `readlink` resolved to a path
  (`/mnt/nzbdav/.ids/...`) that simply didn't exist in that container. Silent, not a crash —
  check this first if a new container reading an existing root folder reports an empty/tiny
  library despite the source clearly having content.
- **FUSE-mount-owning containers and their dependents restart independently, and that's a real
  failure class, not a hypothetical.** `nzbdav-rclone` (the only FUSE-mount-owning container
  left as of v11.0.0, since Zurg/Decypharr/rclone-alldebrid were removed entirely) owns
  `/mnt/nzbdav`; every other container that bind-mounts that path (Radarr, Sonarr, Plex,
  Unpackerr, Cleanuparr) keeps a stale reference after the owner restarts and needs its own
  restart to recover — this does not self-heal. Confirmed live again 2026-07-18 during the
  torrent/debrid removal itself: recreating `nzbdav-rclone` and all five dependents in the same
  batch left every dependent unable to start at all (`transport endpoint is not connected`)
  until `nzbdav-rclone` was restarted alone first and the stale host mount cleared with `sudo
  umount -l /mnt/nzbdav`. `control-panel/app.py`'s `/api/stack/restart-all` encodes the known
  ordering (`MOUNT_PREREQS` → `MOUNT_PROVIDERS` → everything else → `MOUNT_DEPENDENTS` last),
  but it's a hand-maintained set, not derived from `docker-compose.yml` — if you add a new
  service that owns or depends on a FUSE mount, that set needs a manual update or the ordering
  silently stops covering it. See README's "Whole-stack restart: mount-order aware" section.
- **Control Panel (`control-panel/app.py`) is the only in-repo application code.** FastAPI, talks
  to `docker.sock` (via `docker` SDK) plus every app's own HTTP API (via `httpx`), no database, no
  auth beyond CSRF/Origin-Host validation on mutating requests (this stack is LAN-only by design —
  see README's Security section for why an earlier Traefik+Authelia+CrowdSec layer was built,
  verified working, and then reverted). `static/` is vanilla JS/CSS served straight off disk, no
  build step.
- **The `stack-*` CLI is not in this repo.** It's a set of fish functions tracked in
  `~/.dotfiles`, all calling Control Panel's HTTP API — treat `control-panel/app.py`'s routes as
  the actual interface contract; the CLI is a thin client over them.
- **Image pinning is deliberately inconsistent by policy, not oversight**: channel tags for hotio
  images, version tags where upstream cuts real releases, digest pins where the running `:latest`
  build is ahead of any tagged release, and a manually-bumped version tag for Plex specifically
  (kept off Watchtower's auto-update train). Watchtower only auto-updates the channel-tag-pinned
  subset — check which category an image falls into before assuming a version bump is either safe
  or something Watchtower will ever pick up on its own.
- **`config/<app>/` holds real plaintext secrets** wherever an app stores its own config (e.g.
  `config/nzbdav/db.sqlite`'s `ConfigItems` table holds the Usenet provider's real
  username/password), is gitignored, and is not reproducible by `docker compose up` or
  re-pulling images — it's the one thing the backup scripts under `scripts/`/`systemd/` actually
  exist to protect. It has a real off-site leg now too (`BACKUP_REMOTE_REPOSITORY` in `.env`, a
  second restic repo riding on this host's own Dropbox sync) — don't treat
  `scripts/backup-claude-dir.sh`'s Dropbox tar as the off-site protection if you're touching
  backup tooling; it's a cruder, unretained whole-`~/Claude`-tree snapshot that has failed
  silently before, not the real disaster-recovery mechanism.
- **Zurg's content-routing config (`config/zurg/config.yml`) had a real, repeated failure
  mode, worth remembering even though Zurg itself is gone as of v11.0.0**: a group whose *app*
  was removed didn't stop misrouting content, it just started misrouting into a path nothing
  served anymore, silently — happened three separate times (the `music`/`adult` groups
  outliving Lidarr/Whisparr's removal with bare keywords like `FLAC`/`Wicked`/`XXX`
  false-positive-matching 43+ real movies; the anime groups outliving the anime library
  removal by one release). **The generalizable lesson: when removing an app that owns a
  content-routing group or filter of any kind, removing the group itself has to be part of
  that same removal checklist** — nothing else in this stack ever caught it on its own (no
  library, no queue, no alert reads a dead path). See README's
  [The debrid pipeline: removed](README.md#the-debrid-pipeline-removed) section for the full
  incident writeup.
- **A service can be fully connected at the `docker-compose.yml` level and still not actually be
  wired into the *app* it's talking to.** Cleanuparr and NeutArr both auto-discover which
  `*arr` apps exist, but each still needs its own internal instance registration (Cleanuparr's
  own `arr_instances` DB table; NeutArr's own per-app JSON config) before it actually does
  anything for that app — found live as a real gap: Lidarr and Whisparr (both since removed) had
  network access to Cleanuparr and config-type placeholders, but no connected instance, so
  queue-cleaning/strikes silently weren't covering either app. When auditing "is X wired to Y,"
  check the receiving app's own config/API for a real instance entry, not just that the container
  can reach it. NeutArr regenerates a blank-credential placeholder file for any app type it knows
  about (`eros.json`, `whisparr.json`) on every restart even after that config is deleted — inert
  (no URL/key means it can never connect), not a sign the removal didn't take.
- **Every service should have `mem_limit`/`cpus` — verify with `docker stats`, not by grepping for
  the string `mem_limit:` near a service block.** The `x-common` anchor (`<<: *common`) does not
  set either; ten services silently had neither for an unknown stretch of this project's history,
  confirmed live via `docker stats` reporting the full host memory ceiling as several containers'
  limit instead of a real number. A new service needs its own explicit `mem_limit`/`cpus` lines
  regardless of whether it uses `<<: *common`.
- **Lidarr was removed entirely in v10.9.9** — `docker-compose.yml` service block gone,
  `config/lidarr` deleted, `control-panel/app.py`'s `ARR_APPS`/`QUEUE_ARR_APPS`/
  `CONTAINER_LABELS`/`LOG_LEVEL_APPS`/`ARR_LOG_CONTAINERS` all updated, `LIDARR_API_KEY` gone from
  `.env`/`.env.example`, Prowlarr's Lidarr application-sync entry deleted via its own API,
  NeutArr's Lidarr state/config files deleted. The stale Lidarr row this left in Cleanuparr's
  SQLite `arr_instances` table was cleaned up the same day — no REST endpoint exists for that
  table, so the container was stopped first (avoiding a live WAL-mode write), the row and its
  orphaned parent `arr_configs` row deleted directly, then restarted healthy.
- **Whisparr (and Stash, its cataloging app) were removed entirely in v10.12.0** — same recipe as
  Lidarr above, plus a few things Lidarr's removal didn't need to touch: `./media/adult` (Whisparr's
  root folder, 100% symlinks, no real media) deleted; the live Cleanuparr SQLite row deleted in
  the same pass this time, not left as a residual gap (six referencing tables confirmed zero
  orphaned rows before deleting); `/api/neutarr/hunt/eros` (an endpoint whose only purpose was
  triggering Whisparr's hunt cycle) removed outright, not just left orphaned; Decypharr's
  `categories` list in `config/decypharr/config.json` (gitignored, live config) had `"whisparr"`
  dropped. The `*arr` app family in this stack is now Radarr/Sonarr only.
- **Anime support was removed entirely in v10.19.0, by explicit request** — unlike Lidarr/
  Whisparr this wasn't a dead-app cleanup, it was a live, populated content category (122
  Radarr movies, 159 Sonarr series) removed on purpose. Touched: both library entries
  (`deleteFiles=true`, including 15.7GB of real, non-debrid-backed local files under
  `anime-movies` — this stack's "root folders are 100% symlinks" assumption above does not hold
  universally, that was the exception), both Plex libraries, both root folders, the
  `[Anime] Remux-1080p` quality profile and its 33 dedicated custom formats on both apps,
  Zurg's `anime-shows`/`anime-movies` content-routing groups, the `rclone-alldebrid-anime`
  service and `/mnt/all-anime` mount, Kometa's `Anime Movies`/`Anime Shows` library blocks and
  MyAnimeList credentials, `scripts/sort-anime-movies.py` and its systemd units,
  `control-panel/app.py`'s anime references, `PLAN.md` (a never-implemented dual-instance
  proposal), and 8 live Prowlarr indexers that are anime-dedicated by content even though their
  names don't say so (`Nyaa.si`, `SubsPlease`, `Mikan`, `dmhy`, etc. — disabled, not deleted).
  A live Sonarr Trakt import list literally named "Anime" (`enableAutomaticAdd: true`, 12h
  refresh) was found only by checking `/api/v3/importlist` directly — it doesn't live in any
  tracked file, and left in place would have silently re-added anime series on its next
  refresh. See README's History `[10.19.0]` for the full incident, including two more
  supply-chain-style gaps a naive file/config grep wouldn't have caught.
- **DebridMediaManager (self-hosted) was removed entirely in v10.20.0, by explicit request.**
  Four services (`dmm-mysql` - 4GB real MySQL data, permanently deleted with no dump kept;
  `dmm-redis`; `dmm-migrate`; `debridmediamanager`), `scripts/import-imdb-data.py` and its
  daily systemd timer (existed solely to feed `dmm-mysql`'s search index), Control Panel's
  `/api/dmm/status` route plus `pymysql`/`cryptography` from `requirements.txt`, and five
  env vars (`MDBLIST_KEY`/`OMDB_KEY`/`TRAKT_CLIENT_ID`/`TRAKT_CLIENT_SECRET`/`GH_PAT`) that
  turned out to be DMM-exclusive despite this file's own prior wording implying they were
  shared with Kometa — Kometa's `config.yml` carries independent hardcoded copies, not env-var
  substitution, so those five had zero other consumers once DMM's compose block was gone.
  **Deliberately kept, not an oversight**: Zilean's own `Zilean__Dmm__EnableScraping` (scrapes
  DMM's public hashlist website, unrelated to the self-hosted app) and Control Panel's
  `/api/zilean/search` (calls Zilean's own `/dmm/search` endpoint) — same name, different
  feature, confirmed by reading source before touching either. A removal-script bug was caught
  mid-execution: the first attempt at renumbering README's service table matched `zurg`'s row
  too, because its sponsor image (`ghcr.io/debridmediamanager/zurg@...`) contains the literal
  substring "debridmediamanager" — same false-positive class as the anime purge's "URANiME"
  release group, caught by a row-count sanity check, not assumed clean.
- **Adminer removed in v10.9.9, no replacement (for now).** Briefly swapped for CloudBeaver
  (`dbeaver/cloudbeaver:24.3.0`) same version, but that was reverted immediately at the user's
  request — not a fan of the tool, no substitute picked yet. There is currently no web DB GUI
  in this stack; moot now anyway, since `zilean-postgres` (its one-time subject) was itself
  removed along with the rest of the debrid layer in v11.0.0 — no Postgres instance runs in
  this stack anymore.
- **Glances and Dozzle removed entirely in v10.9.9, no data preserved.** Neither had a config
  volume, so there was nothing on disk to clean up. Glances powered Control Panel's Overview
  "Host CPU/memory/disk/uptime" tiles via `/api/system/stats` — that endpoint and those tiles
  are gone too, not just left degraded (Control Panel itself was never re-wired to Beszel below).
  A Prometheus + Grafana monitoring stack was also researched and briefly proposed the same
  session, then cancelled before anything was built or added to `docker-compose.yml`.
  **Glances' replacement, `beszel`/`beszel-agent`, was itself removed entirely in v11.2.0** —
  see [History](README.md#history). This stack currently has no host/container
  resource-monitoring hub of any kind.

## Known current landmines (not historical — still true as of last audit)

- ~~Radarr's and Sonarr's "Quality Definitions" are one flat, instance-wide list each, not
  scoped per quality profile~~ **Moot as of v11.2.0**: both apps were consolidated down to a
  single "ANY" quality profile each (all other profiles deleted, everything reassigned - see
  [History](README.md#history)), so there's only one profile per instance to share the
  instance-wide size definitions with now. Recyclarr (which managed the now-deleted
  TRaSH-tier profiles) was removed entirely the same version.
- **Kometa's `sleep infinity` entrypoint override is load-bearing, not a placeholder.** Removing
  it makes every container restart trigger a full unwanted Kometa run against the whole library.
- **A direct subpath bind of `/mnt/nzbdav` (`rslave`) does not reliably survive the FUSE
  process underneath it being recreated** (an `nzbdav-rclone` image update, a resource-limit
  change, a plain restart). Confirmed live 2026-07-18 during the torrent/debrid removal:
  recreating `nzbdav-rclone` and its five dependents (Radarr, Sonarr, Plex, Unpackerr,
  Cleanuparr) in the same batch left every dependent unable to start (`transport endpoint is
  not connected`) until `nzbdav-rclone` was restarted alone first and the stale host mount was
  cleared with `sudo umount -l /mnt/nzbdav`. Control Panel's `restart-all` already sequences
  this correctly (`MOUNT_DEPENDENTS` now covers all five, grown from just `{"radarr"}`); the
  failure mode above is only reachable by restarting/recreating containers outside that
  endpoint.
- **Cleanuparr's `arr_configs` table needs a row for all five Servarr types (Sonarr, Radarr,
  Lidarr, Readarr, Whisparr) permanently, even for apps this stack doesn't run.** Confirmed by
  reading Cleanuparr 2.9.16's own source — `GenericHandler.ExecuteAsync` does
  `arr_configs.FirstAsync(x => x.Type == T)` per type, not `FirstOrDefaultAsync`, on every single
  QueueCleaner/MalwareBlocker run. One missing type crashes the whole job. **Never delete an
  `arr_configs` row when removing an app from this stack** — only its `arr_instances` row and
  API key. See README's Known Gaps (was: "stale Readarr reference") for the full incident.
- **Cleanuparr's Blacklist Sync feature was permanently disabled against Decypharr** (its
  qBittorrent-API emulation never implemented `POST /api/v2/app/setPreferences`, confirmed
  live: 404 even with valid login/cookie). Moot now that Decypharr is removed entirely
  (v11.0.0) — whether Blacklist Sync works against NzbDAV's SABnzbd-compatible API is
  untested, not confirmed either way. Cleanuparr's separate Content Blocker / Malware Blocker
  feature (applies the same blacklist directly to Sonarr/Radarr, no download-client
  involvement) is unaffected either way and stays enabled.
- **Cleanuparr's own filesystem mount tracks whatever path the download client's API reports
  for each queue item** — originally added to fix QueueCleaner/MalwareBlocker crashing with
  `System.InvalidOperationException: Sequence contains no elements` against Decypharr's
  `/app/downloads`/`/app/downloads-ad` paths; updated to `/mnt/nzbdav` when Decypharr was
  removed entirely (v11.0.0), matching the `storage` path NzbDAV's own history API reports
  (`/mnt/nzbdav/completed-symlinks/<category>/...`). If a future download client changes its
  reported path convention, this mount needs to move with it.
- **NzbDAV leaks NNTP connections past its own configured `MaxConnections`, unbounded, from
  at least three independent code paths (download queue workers, `HealthCheckService`'s
  repair job, and ordinary WebDAV file reads/playback) that don't appear to share one
  enforced cap.** Confirmed live 2026-07-22: reproduced identically across the stable
  `v0.6.4` release and the `pre-release` tag (which adds a circuit breaker for multi-provider
  failover — useless here since this stack runs a single Thundernews provider with no
  backup to fail over to), across `MaxConnections` set to 2/4/10/20, and with the repair job
  (`repair.enable`) both on and off. Connection count climbs unbounded in every combination
  (observed peaks of 86, then 40→66 again minutes later after a full `docker compose rm -f
  nzbdav` + recreate — ruling out stale in-memory state, since a brand-new container
  reproduces it within seconds). This exceeds the account's real, provider-confirmed
  50-connection limit and gets the account explicitly rejected by Thundernews
  (`CouldNotLoginToUsenetException: ... 502 Connection failure. Please contact technical
  support.`), not just timed out. **This also breaks playback of already-completed library
  files, not just new downloads** — this stack has no local media disk, so NzbDAV streams
  every byte live from Usenet even for "completed" items; a plain `dd` read of an existing
  movie through `/mnt/nzbdav/completed-symlinks/...` hung and failed with the same exception.
  Filed upstream as
  [nzbdav-dev/nzbdav#477](https://github.com/nzbdav-dev/nzbdav/issues/477). Until fixed,
  restarting the `nzbdav` container (`stack-nzbdav-restart` or `stack-nzbdav-unstick`) only
  buys a small window before the leak catches back up — not a durable fix. As of this
  writing, Radarr, Sonarr, and NeutArr are stopped and both apps' RSS Sync intervals are set
  to `0` (disabled) specifically because of this bug, so automation doesn't keep feeding a
  queue that can't complete; re-enable them (and restart Radarr/Sonarr, `docker compose up -d
  radarr sonarr`, `docker compose up -d neutarr`) once the upstream issue is resolved. The
  Thundernews provider password was also rotated during this investigation (ruled out as the
  cause — the old password authenticated instantly and successfully in every manual test);
  both `.env` and NzbDAV's own `config/nzbdav/db.sqlite` were updated to match.
  **Root cause found and fixed upstream 2026-07-22**, by reading NzbDAV's own source
  (`nzbdav-dev/nzbdav`, cloned to a scratch dir, not part of this repo): two bugs, both in
  `backend/Clients/Usenet/`. (1) `UsenetStreamingClient.CreateNewConnection` opens the real
  TCP/TLS socket via `ConnectAsync` before `AuthenticateAsync`, but never disposes the
  connection if `AuthenticateAsync` throws — the socket is a local variable only returned to
  the caller on success, so a failed login abandons an open connection forever (relying on
  GC finalization, which is neither immediate nor guaranteed under load). This is the actual
  leak. (2) `ProviderCircuitBreaker`'s own doc comment claims "a single probe attempt is
  allowed" once tripped, but nothing enforces that — `MultiProviderNntpClient.
  GetOrderedProviders()` falls back to the tripped provider anyway when it's the only one
  configured, so every concurrent caller (each queued item, each health-check segment check)
  independently probes it at once with zero coordination. Fixing bug (1) alone made bug (2)
  *worse*, not better: once permits stopped leaking, retries fired fast enough to escalate
  from ~90 consecutive failures over several minutes (pre-fix) to 778 consecutive failures
  logged within a single second (fix (1) alone, live against the real account) — confirmed
  live, this is why the connection leak was accidentally throttling the retry storm the whole
  time. Both fixes together (dispose-on-failure + a real single-probe gate in
  `ProviderCircuitBreaker` via `TryEnterProbe`) were verified locally: real connection count
  stayed within the configured `MaxConnections` instead of growing unbounded, and real
  connection attempts against a tripped provider dropped to roughly one every 1-2 seconds
  instead of hundreds per second — tested first against a deliberately unreachable fake
  endpoint (zero risk to the real account), then briefly against the real account once that
  was confirmed safe. Filed as
  [nzbdav-dev/nzbdav PR #478](https://github.com/nzbdav-dev/nzbdav/pull/478) (fork:
  `WhispersOfJ/nzbdav`, branch `fix/connection-leak-and-circuit-breaker-storm`). **Not merged
  upstream yet as of this writing** — `docker-compose.yml` still pins `nzbdav/nzbdav:latest`
  (the stock, unpatched image), not the local patched build, since redeploying an unmerged
  fork build permanently isn't appropriate for this repo's normal image-pinning policy.
  Auth still failed against the real account even with both fixes applied, live-tested
  2026-07-22 — most likely the account itself is genuinely rate-limited/degraded from this
  session's heavy testing (a separate, external, time-based condition), not a remaining code
  bug. Re-test once PR #478 is merged into a real release, or once enough time has passed for
  the account to recover on its own.

## Backup/DR details beyond "restic + a Dropbox tarball"

- **No Postgres-backed service runs in this stack anymore** (`zilean-postgres` was removed
  with the rest of the debrid layer in v11.0.0, and `scripts/backup-config.sh`'s
  logical-`pg_dump` step for it was removed with it). **Any new DB-backed service added later
  gets zero backup coverage by default** unless it gets its own logical-dump step added back —
  restic's raw-datadir exclusion alone silently drops it (file-level backup of a live datadir
  is unsafe, which is why the exclusion exists, but that means nothing else covers the gap it
  leaves).
- **restic exit code 3 (some files unreadable/locked) is treated as a soft warning that still
  lets pruning proceed**, not a hard failure. Discord alerting keyed only on "error"-level restic
  output will miss a *recurring* partial-backup problem that never escalates past exit code 3.
- **`scripts/backup-claude-dir.sh` overwrites a single Dropbox tarball in place every run — there
  is no retained history for that leg at all**, unlike the restic repo's normal snapshot
  retention. Already established this script isn't the real DR mechanism; this is the specific
  reason why (one bad run can silently replace the only copy).
- **A from-scratch host restore needs `/mnt/nzbdav` created manually before `docker compose up`,
  or `nzbdav-rclone` crash-loops.** Confirmed live during the 2026-07-20 full restore onto a
  fresh CachyOS install: the host bind-mount target for the FUSE mount (`/mnt/nzbdav:/mnt/nzbdav`
  in `docker-compose.yml`) doesn't exist on a truly fresh disk the way it silently persisted
  across the old install's reinstalls, so rclone fails with `mountpoint does not exist:
  /mnt/nzbdav` in a tight restart loop until `sudo mkdir -p /mnt/nzbdav` is run first. Not
  covered by any backup/restore script since it's host filesystem state outside `~/Claude`
  entirely — add this as a manual pre-step to any future from-scratch restore runbook.

## Historical incidents worth knowing before touching related code

- **All four rotatable API keys (Radarr, Sonarr, Prowlarr, NzbDAV) were rotated 2026-07-22**,
  triggered by a live Sonarr key found hardcoded in `.claude/settings.local.json` (an
  untracked, personal-override file — see its own `.gitignore` entry added the same day).
  Radarr's and Sonarr's `apiKey` field in `config/host` silently ignores changes via a plain
  API PUT — the actual key lives in `config/<app>/config.xml`'s `<ApiKey>` element and only
  takes effect after a container restart; there is no REST-only way to rotate it. Doing so
  also required setting `AuthenticationMethod` from `Forms` (with blank, already-unusable
  username/password — GET always returns empty for these fields even when populated, and PUT
  validation demands them non-empty for `Forms`) to `None`, since the real credentials were
  never known and re-supplying them wasn't an option — a deliberate, approved security
  tradeoff, not an oversight. Every consumer of the old Radarr/Sonarr keys was updated and
  live-tested afterward: Prowlarr's Applications sync entries (`/api/v1/applications/{id}`,
  needs the read-only `id` field stripped before a PUT to Seerr's equivalent endpoint, and
  before that field, before the PUT will validate), Seerr's `/api/v1/settings/radarr|sonarr`,
  Bazarr's own `/api/system/settings` form-encoded endpoint (see
  [Bazarr](README.md#bazarr-subtitle-management) for its gotchas), Cleanuparr's `arr_instances`
  SQLite table (edited with the container stopped first, same WAL-safety practice as the
  Lidarr/Whisparr removals), and NeutArr's `radarr.json`/`sonarr.json` (NeutArr itself stays
  stopped regardless, per the NzbDAV connection-leak landmine above). NzbDAV's own SABnzbd-
  compatible key lives at config key `api.key` (rotatable via the same login+update-config
  pattern as `usenet.providers`) and also needed updating in Radarr's and Sonarr's own NzbDAV
  download-client entries (`/api/v3/downloadclient/1`). Plex's token was deliberately left
  alone — it's a sign-in session token, not a simple regenerate-via-API key, and carries a
  real risk of disrupting connected clients.
- **NeutArr was getting OOM-killed roughly every 30 minutes inside its 512MB `mem_limit`, fixed
  2026-07-18 by raising it to 1g.** Invisible from any dashboard because `restart: unless-stopped`
  just quietly restarted it — `docker stats`/`docker inspect` (OOMKilled flag / restart count) was
  the only way it was ever caught, container "looked up" the whole time. Found during a
  stack-wide `mem_limit` audit prompted by the anime/DMM/adult-content removals — every other
  service's limit turned out to already be deliberately tuned with documented rationale in its
  own compose comment (Zilean's 4g tied to `DOTNET_GCHeapHardLimit`, Decypharr's 1.5g to an
  observed 540-580MB steady state, Byparr's 2g to concurrent Camoufox headroom, Kometa's 2g to a
  642MB observed real-run footprint); NeutArr's 512m was the one outlier with no such comment.
  If a service ever looks "up" on every dashboard but behaves erratically, check `OOMKilled`
  before assuming an app-level bug.
- **An unexplained mass Radarr/Sonarr library deletion happened once, with zero trail in either
  app's API or logs** — root cause was never found. The Recycle Bin setting was turned on
  afterward purely as forward-looking mitigation, not because the mechanism was identified. If a
  similar report ever comes in, don't assume Recycle Bin retroactively explains or prevents every
  case — it wasn't proven to be the actual cause the first time.
- **Sonarr has a pagination-safe `missing-aired` endpoint that exists but has zero UI wiring and
  has never been tested against this library's real scale (~300k episode records).** Don't assume
  it's a validated, ready-to-use path without treating that first real invocation as a genuine
  test, not a known-safe operation.
- **Recyclarr's custom-format/quality-profile sync was completely broken since the day it was
  added, not a regression** — its compose service block never passed `RADARR_API_KEY`/
  `SONARR_API_KEY` into the container despite `config/recyclarr/recyclarr.yml`'s `!env_var`
  directives requiring them; every scheduled run failed at the config-parse stage with an
  undefined-variable error, confirmed live via its own logs going back to at least 2026-07-14.
  Separately, both apps' sole quality profile had drifted to being named "Any" at some point
  while `recyclarr.yml` (and this file, until fixed alongside it) still assumed "Unlimited" -
  Recyclarr was silently unable to find a profile to score into even after the env-var fix,
  until the live profile was renamed back via API. Fixed together; if a similar "sync completes
  with a Config Diagnostics warning" symptom ever recurs, check both layers (env vars actually
  reaching the container, and the profile name Recyclarr expects actually existing) rather than
  assuming just one explains it.
- **Torrent and debrid support was removed entirely in v11.0.0, by explicit request** — six
  services gone (`decypharr`, `decypharr-alldebrid`, `zurg`, `rclone-alldebrid`, `zilean`,
  `zilean-postgres`), plus `byparr` once confirmed no remaining Usenet indexer referenced it.
  All 49 enabled torrent indexers plus the `Zilean` Torznab entry disabled then deleted from
  Prowlarr, in that order. **A real, live consequence found mid-execution, not anticipated in
  planning**: Zurg and Decypharr never downloaded real bytes, they symlinked into a FUSE mount
  streaming directly from Real-Debrid/AllDebrid, so stopping those containers immediately
  broke playback for the 616 files (3.65% of the library) sourced through them — surfaced and
  confirmed with the user mid-removal rather than assumed safe, then accepted as a known
  consequence. Recreating `nzbdav-rclone` and its now-five mount-dependent containers in the
  same batch reproduced the FUSE stale-mount bug this file already documents for a single
  dependent — confirmed live, not just theorized; `MOUNT_DEPENDENTS` grew from `{"radarr"}` to
  all five to match. See README's History `[11.0.0]` for the full removal, including every
  file/endpoint/CLI-command touched.

## Control-panel gotchas beyond restart ordering and CSRF

- **Cleanuparr's instance-check in `control-panel/app.py` bypasses Cleanuparr's own HTTP API
  entirely and reads its SQLite DB file directly** — `/api/instances` on Cleanuparr itself
  returns an HTML shell, not JSON, so there was no API-level way to get this data.
- **`/api/version` depends on an exact regex match against a specific line format in
  `README.md`.** This compounds the single-file bind-mount staleness issue already noted above —
  reformatting that line in README *or* editing README without a `--force-recreate` on
  `control-panel` can both silently break version reporting.

## Deliberate architecture decisions with non-obvious reasons

- **A full Traefik + Authelia + CrowdSec stack (real 2FA, real CrowdSec ban behavior) was built
  and verified working, then deliberately reverted** in favor of the current LAN-only,
  CSRF/Origin-validated model — the full recipe is preserved in README's History section if this
  is ever revisited, so don't rebuild it from scratch without checking there first.
- **Sonarr's Remote Path Mapping for the AllDebrid `decypharr-alldebrid` instance (the one
  deliberate exception to this stack's normal "no Remote Path Mappings" convention) was
  removed along with Decypharr itself in v11.0.0** — this stack has no Remote Path Mappings
  at all now, no exceptions.

## Workflow playbook: recurring task types

Add to this section as new recurring task shapes come up. Goal: the next session facing
the same *kind* of problem starts from the playbook, not from scratch.

**A bundled/off-the-shelf dependency has a bug** (first hit 2026-07-22, NzbDAV's connection
leak — see the landmine above):
1. Rule out our own config first with a raw, protocol-level test that bypasses the app
   entirely (e.g. a manual `openssl s_client` NNTP auth) before concluding upstream is
   broken — this is what actually distinguished "our MaxConnections setting" from "NzbDAV
   itself" here.
2. Clone the upstream repo to a scratch dir (never into this repo) and read the real source
   before guessing at a fix from logs alone.
3. **Test any patch against a fake/unreachable endpoint first, never straight to the real
   live third-party service** — a connection/retry-logic fix can turn into a rapid-fire
   storm against a real account the moment it works correctly. Confirmed live: fixing
   NzbDAV's socket leak let retries fire fast enough to escalate a real account's failure
   count from ~90 over several minutes to 778 within one second. Only test against the real
   service briefly, after the fake-endpoint test confirms the retry rate is sane.
4. Fork the upstream repo (`gh repo fork <owner>/<repo> --clone=false`), push a branch, open
   a real PR referencing the filed issue — don't just comment with a diff.
5. For a broader security/leak audit of the dependency's source, reach for the
   `fullstack-dev-skills:security-reviewer` plugin skill (SAST/dependency-audit/secrets-scan
   focus) rather than this repo's own `/security-review` (scoped to git-diff PR review,
   explicitly excludes whole-codebase resource-leak findings — confirmed by a subagent that
   tried it and bounced off) or an unstructured general-purpose-agent prompt.
   `fullstack-dev-skills:debugging-wizard` is worth trying for the initial stack-trace/log
   correlation phase too, ahead of manual log reading.
6. Don't pin this stack's `docker-compose.yml` to a local/fork build permanently — leave the
   stock image pinned until the fix actually merges upstream into a real release, and record
   the PR/issue link plus the revert-when-merged condition here instead.

**Rotating a credential that multiple apps consume** (first hit 2026-07-22, Radarr/Sonarr/
Prowlarr/NzbDAV keys, after one turned up hardcoded in `.claude/settings.local.json`):
1. Start with the `secret-injector` skill (`rotate the radarr api key` is a listed trigger
   phrase) instead of hand-rolling this with raw `curl`/`sed` — it writes `.env` safely
   (value via stdin only, never echoed to a log or shell history) and can leak-scan the
   working tree for the old value still hardcoded somewhere.
2. Every consumer needs updating separately — nothing here shares one source of truth:
   - The issuing app's own key: Radarr/Sonarr live in `config/<app>/config.xml`'s
     `<ApiKey>` — a plain API `PUT /api/v3/config/host` silently ignores changes to
     `apiKey`, it has to be edited in the XML directly and the container restarted.
     Prowlarr: same pattern, `config/prowlarr/config.xml`. NzbDAV: config key `api.key`,
     rotatable through its login+get-config/update-config pattern (see the provider-config
     gotcha above for that pattern's shape).
   - Prowlarr's Applications sync entries (`/api/v1/applications/{id}`) — strip the
     read-only `id` field before PUTting back, or it 400s.
   - Seerr's `/api/v1/settings/radarr|sonarr/{id}` — same read-only `id`-field gotcha.
   - Bazarr's `/api/system/settings` form-encoded endpoint (see
     [Bazarr](README.md#bazarr-subtitle-management) for its own gotchas).
   - Cleanuparr's `arr_instances` SQLite row — stop the container first (WAL-safety, same
     practice as the Lidarr/Whisparr removals), edit directly; no REST endpoint exists for
     this table.
   - NeutArr's `config/neutarr/<app>.json` `api_key` field — plain JSON edit, safe whenever
     NeutArr's own container is stopped.
   - Radarr/Sonarr's own NzbDAV download-client entry (`/api/v3/downloadclient/1`) needs
     NzbDAV's key too — separate from Radarr/Sonarr's own issuing-app key above.
   - `control-panel` needs `--force-recreate` afterward — it only reads `.env` at
     container-*create* time (see the Commands section above).
3. Test each consumer's connection afterward via its own `/test`-style endpoint rather than
   assuming the write took — most of the endpoints above have one.
