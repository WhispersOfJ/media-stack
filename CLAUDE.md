Read existing files before writing. Don't re-read unless changed.
Thorough in reasoning, concise in output.
Skip files over 100KB unless required.
No sycophantic openers or closing fluff.
No emojis or em-dashes.
Do not guess APIs, versions, flags, commit SHAs, or package names. Verify by reading code or docs before asserting.


# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Docker Compose media-acquisition-and-serving stack, one `docker-compose.yml`: indexes content
via Prowlarr, requests via Seerr, organizes via two `*arr`-family apps (Radarr/Sonarr — Lidarr
was removed entirely in v10.9.9 and Whisparr in v10.12.0, see below; Bindery, the ebook `*arr`,
was retired in v10.9.8 along with its reader Calibre-Web; no ebook app currently in the stack),
fetches via Usenet exclusively through **AltMount**, and serves via **Plex** (real, current
state as of 2026-07-23 — confirmed live via `docker compose ps`, `/library/sections`, and
`docker-compose.yml` itself, not assumed from older narrative in this file).

**CORRECTION, 2026-07-24: AltMount itself was fully removed and replaced by BearMount**
(`ghcr.io/whispersofj/bearmount`, container name `bearmount`, mount `/mnt/bearmount`, host
port 8082) — a full rebrand/fork of AltMount at `github.com/WhispersOfJ/bearmount`, same
codebase lineage. Every `altmount` reference below (container name, `/mnt/altmount`, routes,
`.env` vars, scripts) is historical narrative, not current state — read it for the reasoning,
substitute `bearmount` for the actual name. Same cutover pattern as NzbDAV→AltMount: every
pre-cutover symlink broke, and this time Radarr/Sonarr were also fully purged (0 movies/series
tracked) at the user's explicit request, keeping only Import Lists so libraries repopulate
from scratch. Don't assume the old movie/series counts or symlink targets are still valid.

Jellyfin briefly
replaced Plex on 2026-07-22 and was fully reverted back to Plex the same day after repeated
unresolved library-scan hangs; Jellyfin/Jellystat/jellystat-db were removed entirely in that
reversion (see the dedicated History entry below) — there is no Jellyfin anywhere in this stack.
NzbDAV (Usenet client) was removed entirely 2026-07-23 and replaced by AltMount, for the same
reason (an unfixed upstream connection-leak bug) — see the landmines section for the full
incident and PR references. **Tautulli, Kometa, and Kometa's Quickstart companion are fully
removed, corrected 2026-07-24** — `docker-compose.yml` has zero references to any of the
three (confirmed via `grep`), reversing a 2026-07-23 correction in this same file that claimed
they were "present-but-dormant" with live compose blocks/images; that "present-but-dormant"
claim was itself stale by the time it was checked again. Treat their removal (compose blocks,
`config/tautulli/`, `config/kometa/`, `config/quickstart/`) as complete and final.
**Torrent and debrid support (Decypharr, Zurg, rclone-alldebrid, Zilean, zilean-postgres,
Byparr) was removed entirely in v11.0.0, by explicit request** — every acquisition goes through
Usenet, no exceptions (see the landmines/History sections below for the full removal, including
a real consequence found mid-execution: those apps never downloaded real bytes, only symlinked
into a live FUSE mount streamed from the debrid provider, so removing them immediately broke
playback for the ~3.65% of the library that was debrid-sourced, not just future acquisitions).
Usenet had already been the preferred protocol since a v10.14.1 policy change (a deliberate
reversal of the stack's original debrid-first design) before this final removal. There is no
adult content library in this stack anymore: Plex's own Adult library was removed in v10.9.9,
and Whisparr (which managed the underlying files/root folder) plus Stash (which cataloged it)
were both removed in v10.12.0, along with the files themselves. There is no anime library in
this stack either as of v10.19.0 (also removed by explicit request, not a dead-app cleanup —
see the landmines section below), and no self-hosted DebridMediaManager as of v10.20.0 (same
reasoning, same section). **As of 2026-07-23, every root folder is enforced back to 100%
symlinks with zero real media files on local disk** — AltMount's `import.import_strategy` is
`SYMLINK` (not `NONE`) and both Radarr's and Sonarr's `copyUsingHardlinks` is `true`; see the
dedicated History entry below for why this had regressed and how it was fixed and verified live
(a real symlink into `/mnt/altmount` that actually streams, not just a config value).
`control-panel/` is the one custom-built component (a FastAPI dashboard, redesigned entirely
2026-07-23 — no boxes/tabs, a permanently pinned log console, see the dedicated entry below);
everything else is off-the-shelf images wired together in `docker-compose.yml`.

**This stack currently has zero backup coverage, deliberately, as of 2026-07-23** — both the
local and offsite restic repositories were deleted at the user's explicit request while a new
backup policy is being decided, and the three backup systemd timers were stopped and unlinked
(not deleted — their source units still exist under `systemd/` and can be relinked anytime).
Do not assume `scripts/backup-config.sh` or its timer are running; verify with
`systemctl --user list-timers` before relying on either.

**`README.md` is the only documentation in this repo besides raw config** — it merges what used
to be README/TECHNICAL/CHANGELOG into one document, organized by subsystem, ~1,900 lines with a
linked table of contents. Read the relevant section there before making changes; this file only
covers what you need to get oriented and the things that aren't obvious from reading one file in
isolation.

**This stack has no public downstream mirror — see `AGENTS.md`.** `StackMaster` (and before it,
`Stackalicious`/`StackScripts`) were deleted outright from GitHub, most recently 2026-07-21,
for privatization. Every `stack-*` command lives only in this host's own fish functions plus
this repo's `control-panel/app.py` — nothing to mirror anywhere.

## Full service inventory (all 17, by subsystem)

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
v11.2.0 until 2026-07-23, when Recyclarr was reinstalled (see History) — both apps now also
carry real TRaSH-tier profiles (Radarr: HD Bluray + WEB / Remux + WEB 2160p / Low Quality;
Sonarr: WEB-1080p / WEB-2160p / Low Quality) alongside "Any", synced daily 6am by Recyclarr.
Existing movies/series were deliberately left on "Any", not reassigned to a tier.

**Usenet** — `nzbdav` (core, port 3001→3000, WebDAV-streamed Usenet, SABnzbd-API compatible,
**the only download client on both Radarr and Sonarr as of v11.0.0** — was priority-1 behind
Decypharr's priority-2 fallback until debrid was removed entirely, see the top-of-file
description) · `nzbdav-rclone` (see FUSE mount owners above — same container, listed once).

**Requests** — `seerr` (core, port 5055, Radarr/Sonarr only — no adult-content or music/ebook
data model, moot now that those app families are gone anyway).

**Media server** — `jellyfin` (core, `lscr.io/linuxserver/jellyfin:latest`, port 8096, bridge
networking on `stacknet` — replaced `plex` entirely 2026-07-22, see the Historical incidents
section below for the full migration. Two libraries, matching Plex's final two exactly: Movies
(`/data/movies`), Shows (`/data/shows`). Same VAAPI hardware-transcode device
(`/dev/dri/renderD128`) carried over from Plex's config. **Its compose block has no
`/mnt/nzbdav` mount** (unlike every other root-folder consumer — Radarr, Sonarr, Unpackerr,
Cleanuparr all bind it) — every root folder is 100% symlinks into that FUSE mount (see
Architecture facts below), so this looks like the exact same class of bug Stash's first deploy
hit: a library scan that completes with no error and finds nothing playable, because every
`readlink` resolves to a path that doesn't exist inside this container's own mount namespace.
Not yet confirmed live either way — flagged here as an unverified, high-suspicion gap, not a
confirmed bug, since verifying it means actually watching something and this pass was
documentation-only.)

**Monitoring** — `tautulli` removed entirely 2026-07-22, same session as the rest of the
Plex-to-Jellyfin migration (Plex-only, nothing left to monitor once Plex was gone; initially
left orphaned pointed at a dead media server, then fully removed on explicit follow-up
request — compose block, `config/tautulli/`, and its `control-panel/app.py` routes' container
listing entry all gone; the two `/api/tautulli/*` history/stats routes themselves were left as
documented dead code, same treatment as `/api/plex/*`, since they already 503 gracefully once
`config/tautulli/config.ini` doesn't exist) · `jellystat` + `jellystat-db` (extras, port 8087,
Jellyfin stats/history, the Tautulli-equivalent — `jellystat-db` is `postgres:18.1`, this
stack's first Postgres dependency since `zilean-postgres` was removed in v11.0.0, still with no
backup-coverage plan, a known gap, see Backup/DR section below). Both containers are up,
healthy, and fully configured — confirmed live via `jellystat-db`'s own `app_config` table
(real `JF_HOST`/`JF_API_KEY`, admin user `bear` matching Jellyfin's real user ID) and a
populated `jf_library_items` table (7,799 rows synced). `beszel`/`beszel-agent` (Glances'
v10.9.9 replacement) removed entirely in v11.2.0, by explicit request — no host/container
resource-monitoring hub currently in this stack.

**Subtitles** — `bazarr` (extras, port 6767, watches Radarr/Sonarr for missing subtitles;
reinstalled from scratch in v11.3.0 after being removed entirely in v10.2.0, no prior config
survived; wired to both apps post-boot via its own `/api/system/settings` form-encoded
endpoint — see README's dedicated section for the gotchas in that endpoint before touching it
again; provider list narrowed in v11.4.0 to 9 English-capable, non-anime-exclusive sources).

**Sports PVR** — none. `sportarr` was added 2026-07-23 and **removed entirely 2026-07-24**,
by explicit request, after its Plex metadata integration turned out to be structurally
broken (see History `[Sportarr removed]` below) and the user chose full removal over
further debugging.

**Dashboard** — `control-panel` (extras, port 8420, the one custom-built component —
`build:` from `./control-panel`, not a pulled image; talks to `docker.sock` plus every app's
own HTTP API; no auth, CSRF/Origin-Host validated only; see the dedicated gotchas section
below).

**Metadata/overlays** — none currently in this stack. `kometa` and its `quickstart` companion
(the official Kometa-Team config-building wizard) were **removed entirely 2026-07-22** when
Plex was replaced by Jellyfin, after confirming directly against `kometa-team/kometa`'s own
`config-schema.json` that Kometa has no `jellyfin`/`emby` top-level connection property, only
`plex` — several blog-post sources (e.g. jellywatch.app) claiming Kometa supports Jellyfin are
wrong/outdated as of this check; real Jellyfin support is an open, unimplemented feature
request (features.jellyfin.org/posts/2899). Initially just stopped (`docker compose stop
kometa quickstart`, config/compose untouched) in case that changed upstream soon, then fully
removed at the user's explicit follow-up request: both compose service blocks deleted,
`config/kometa/` and `config/quickstart/` deleted (`config/kometa/config.yml`'s real
credentials — Trakt client ID/secret, GitHub PAT, OMDb/MDBList keys — backed up to
`~/backups/removed-configs/kometa-config.yml.bak-2026-07-22` first, unlike Plex's config which
was pure app-internal state; OMDb/MDBList keys promoted to real `OMDB_KEY`/`MDBLIST_KEY` `.env`
secrets and wired into `control-panel/app.py`'s `/api/ratings/*` routes, which used to read
them live off Kometa's file), `control-panel/app.py`'s `/api/kometa/run` route and
`KometaRunRequest` model deleted outright (not left dead like the Plex routes — no
missing-env-var fallback existed for it to degrade into), `CONTAINER_LABELS` entries for both
containers removed. `labelarr` (TMDb-keywords-as-Plex-labels) removed entirely in v11.2.0, by
explicit request — no item-level Plex label automation currently in this stack, and no
collections/overlays automation of any kind now either, following Kometa's removal.

**Post-processing** — `unpackerr` (extras, no port, RAR extraction for Radarr/Sonarr's
downloads).

**Auto-updates** — `watchtower` (extras, no port, digest/channel-tag images only — Plex used to
be deliberately excluded from its train via a manually-bumped version tag; Jellyfin is not
excluded the same way — `lscr.io/linuxserver/jellyfin:latest` is a mutable channel tag, so
Watchtower auto-updates it like any other channel-tag image unless this is deliberately
changed, see Image pinning policy).

**Queue cleanup / missing-content hunting** — `cleanuparr` (extras, port 11011, strikes +
malware-block + stalled-download cleanup). **`neutarr` was removed entirely 2026-07-24**,
after its hunting flood caused a real cascading incident (see the landmines section) —
there is no automated missing-content/quality-upgrade hunting of any kind in this stack now.

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

# MANDATORY before recreating/restarting/stopping bearmount for ANY reason (config change,
# mem_limit tweak, unrelated debugging - the reason does not matter, see CLAUDE.md's
# 2026-07-23 repeat-incident entry, which carried over unchanged to bearmount's rebrand).
# /tmp/.bearmount-queue is NOT a persistent volume, so any recreate wipes queued NZBs and
# each resulting failure silently unmonitors + permanently blocklists the affected
# Radarr/Sonarr item. Confirm pending/processing is 0 first, or drain the queue before
# touching the container.
sqlite3 config/bearmount/bearmount.db "SELECT status, COUNT(*) FROM import_queue GROUP BY status;"

# Unit tests (added 2026-07-22) — control-panel/app.py's pure logic (helpers, CSRF
# middleware, bucketing/ETA math) plus scripts/*.py's pure logic, all with docker.sock,
# httpx, and urllib network calls mocked out; no real stack/daemon needed. Now part of
# CI (validate.yml), alongside the compose/ruff/shellcheck checks below.
# This host's Python is externally-managed (PEP 668) - pip install below refuses with
# "externally-managed-environment" outside a venv: `python3 -m venv /tmp/venv &&
# /tmp/venv/bin/pip install -r control-panel/requirements.txt -r requirements-dev.txt &&
# /tmp/venv/bin/pytest`.
pip install -r control-panel/requirements.txt -r requirements-dev.txt
pytest
```

CI (`.github/workflows/validate.yml`) runs compose-config validation, ruff, shellcheck,
the `tests/` unit suite above, and a build-only Dockerfile check — no torrent/live-stack
verification. **The unit suite only covers pure logic reachable with everything mocked**
(docker.sock, each app's HTTP API, `urllib`/`httpx` calls) — it does not replace exercising
a change against the real running stack (curl an endpoint, check `docker logs`, load the
dashboard), which is still the only way to verify anything that actually talks to a live
container. That's the pattern this project's own README follows throughout its history
section, and there's no substitute for it for that class of change.

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
  **Still literally `{"radarr", "sonarr", "plex", "unpackerr", "cleanuparr"}` as of the
  2026-07-22 Plex-to-Jellyfin migration** — `control-panel/app.py` is unreworked (see the
  Historical incidents entry below), so `restart-all` still tries to restart a container named
  `plex` that no longer exists in `docker-compose.yml` (a harmless no-op against the Docker SDK,
  not a crash, but dead weight) and does not include `jellyfin` at all — worse, Jellyfin's own
  compose block doesn't even bind `/mnt/nzbdav` right now (see the Media server entry above),
  so whether it needs to be in this set at all is unresolved until that's confirmed.
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
  build is ahead of any tagged release, and (historically) a manually-bumped version tag for Plex
  specifically, kept off Watchtower's auto-update train. Plex is gone as of 2026-07-22 (replaced
  by Jellyfin, see the Historical incidents entry below); Jellyfin's `lscr.io/linuxserver/jellyfin:latest`
  is a mutable channel tag, not a version pin, so it does *not* carry forward Plex's old
  exception — Watchtower auto-updates it same as any other channel-tag image unless that's
  deliberately changed. Watchtower only auto-updates the channel-tag-pinned subset — check which
  category an image falls into before assuming a version bump is either safe or something
  Watchtower will ever pick up on its own.
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

- **BearMount's `config/bearmount/config.yaml` `queue_cleanup_rules` entries can have
  `action: blocklist_search`, which blocklists a failed release AND immediately fires a new
  search** — if an indexer keeps serving equally-bad releases for a given episode/series
  (fake/incomplete NZBs, wrong file types), this becomes a self-sustaining loop with no
  external trigger needed (confirmed live: RuPaul's Drag Race and Snapped looped for 4+
  hours, 500+ blocklist entries each, long after the original hunting tool that grabbed
  them was disabled). Symptom: Sonarr/Radarr's blocklist growing continuously with no
  RSS sync, no NeutArr-equivalent, and no active manual search running. Fix: unmonitor the
  affected series (stops Sonarr from acting on the retriggered search) rather than trying
  to catch it via `docker-compose-manager`/queue-clearing, which doesn't touch this loop at
  all since it's driven by BearMount's own queue-cleanup logic, not the download queue.
- **A Plex scan can freeze mid-scan for a second, distinct reason from the documented
  FUSE/D-state hang**: SQLite lock contention from an import burst. Symptom looks
  identical (progress % frozen, eventually no scanner subprocess running) but
  `Plex Media Server.log` shows `ERROR - Waited over 10 seconds for a busy database;
  giving up` repeating every ~10s, not a FUSE/mount error, and `docker logs bearmount`
  is silent for the whole window (mount itself stays fully responsive). Check for this
  log line before assuming a stuck scan needs the FUSE-abort fix — a plain
  `docker compose restart plex` clears it without any mount-cascade risk. Triggered by
  100+ near-simultaneous imports (e.g. a hunting tool's backlog draining all at once)
  flooding Plex's own SQLite writer via Radarr/Sonarr's per-import notify webhook.
- **`~/.dotfiles` fish functions and `control-panel/static/commands.json` both drift
  silently out of sync with `control-panel/app.py` after any rename or removal — neither
  is caught by testing `app.py` alone.** Found live: five fish functions for apps removed
  sessions ago (Kometa, all 6 Sportarr commands, both Tautulli commands) and five
  `commands.json` command-palette entries still pointing at `/api/nzbdav/*` (dead since
  the AltMount/BearMount rebrand) — all silently broken, none caught until specifically
  audited. After renaming or removing any app's routes, grep both
  `~/.dotfiles`'s `.config/fish/functions/*.fish` and this repo's `commands.json` for the
  old name, don't assume `app.py` being correct means the CLI/palette are too.
- **A new rclone-mount-owning container needs its `/mnt/<name>` host directory pre-created and
  `chown 1000:1000` before first start** - `/mnt` itself is root-owned, and the container can't
  `mkdir` under it (`permission denied`). Hit for both AltMount's and BearMount's first boot -
  not a one-off, expect this for any future rclone/FUSE-mounting service.
- **BearMount's config schema is stricter than AltMount's for `providers[*].last_speed_test_time`**
  - AltMount tolerated a plain RFC3339 string there; BearMount's decoder rejects anything but
    `null` or an omitted key ("expected a map or struct, got string"). Same underlying
    codebase/fork, a real behavior difference - don't assume a config.yaml copied from
    AltMount's loads as-is into BearMount.
- **Radarr/Sonarr have real bulk-delete endpoints**: `DELETE /api/v3/movie/editor` /
  `/api/v3/series/editor`, body `{movieIds|seriesIds: [...], deleteFiles: bool,
  addImportListExclusion: bool}`. Keep `addImportListExclusion: false` if the intent is "let
  Import Lists re-add these later" - `true` permanently blacklists them from list-based
  re-adding.
- **Once a compose service block is deleted, `docker compose stop/rm <service>` fails with
  "no such service"** even while the container itself is still running - use `docker stop
  <container_name>` / `docker rm <container_name>` directly for a container whose compose
  block is already gone.
- **Radarr's/Sonarr's `renameMovies`/`renameEpisodes` default to `false`** — a custom naming
  format string being set does nothing on its own; files keep their original scene-release
  names until this is explicitly turned on. Confirmed both were `false` on a freshly-wiped
  instance despite a full TRaSH naming format already configured.
- **Sonarr's real per-file TMDB-id naming token is bare `{TmdbId}`, not `{Series TmdbId}`** —
  the latter (TRaSH-Guides' own documented syntax) silently resolves to an empty string
  (`{tmdb-}` in the real folder name) rather than erroring. Confirmed live by testing several
  candidate tokens against a real series via `PUT /api/v3/series/editor` with `moveFiles:
  true`. Radarr's equivalent `{TmdbId}` (no `Movie ` prefix) is correct as documented.
- **Sonarr's/Radarr's `GET /api/v3/config/naming/examples` ignores its own query parameters**
  — it only ever reflects the currently-*saved* naming config, regardless of what format
  string is passed in. To test an unsaved format, save it for real and re-check, or trigger a
  real per-item recompute (`PUT /api/v3/series/editor` with `moveFiles: true`) against a
  series/movie that already has real IDs populated.
- **Sonarr's command queue can flood with hundreds of `RefreshSeries` entries during a heavy
  import burst** (peaked at 737 during the RuPaul's Drag Race backfill), starving every other
  queued command for minutes. `DELETE /api/v3/command/{id}` cannot cancel a running batch
  command (`409 Unable to cancel task`) — the only fix is `docker compose restart sonarr`,
  which clears the in-memory command queue (the DB-persisted download queue itself survives).
- **Prowlarr's Applications `GET` response always masks `apiKey` as `"********"`** — PUTting
  that response straight back (e.g. to force a sync) silently overwrites the real Radarr/Sonarr
  API key Prowlarr uses to connect with the literal mask string, breaking the connection.
  Always re-fetch the real key from the target app's own `config.xml` and overwrite the masked
  field before PUTting a round-tripped Applications entry back.
- **`config/bearmount/config.yaml`'s `import.max_processor_workers` is deliberately pinned at
  `1`, not the default `2`** — see the AltMount memory incident above (99.87% of a 2GiB limit
  hit when two large multi-part RAR archives were analyzed concurrently, since per-archive
  memory cost scales with part count and this library has several 50-70GB+ UHD remux releases).
  **If this is ever bumped back to 2+ for testing (a new processor, a throughput experiment,
  anything)**, treat it as reintroducing that exact risk, not a routine tuning change: watch
  `docker stats bearmount` live while a large multi-part archive is queued, and don't leave it
  at 2+ unattended unless `mem_limit` (currently 6g) has real headroom confirmed for two
  concurrent large-archive analyses, not just one. Revert to `1` if not actively testing.
- **A new poster-sync API key (`control-panel/app.py`) needs adding in two places, not one** —
  `.env` alone is not enough; it also needs an explicit line in `docker-compose.yml`'s
  `control-panel` `environment:` block (matching the existing `TMDB_KEY`/`FANART_KEY` lines),
  or the container never sees it even after `--force-recreate`. Confirmed missing `TVDB_KEY`
  from that passthrough list caused a working `.env` value to be invisible inside the container.

### Quick diagnosis: AltMount/Plex/Radarr/Sonarr symptoms from 2026-07-23

Fast symptom → cause → fix reference for the failure classes hit during the NzbDAV→AltMount
cutover, so a future session recognizes these immediately instead of re-deriving them from
scratch. Full incident narrative is in the History section below; this is the cheat-sheet.

- **Symptom: `ls`/any read on `/mnt/altmount` (or a bind-mounted subpath of it) returns
  `Input/output error`, `Socket not connected`, or `transport endpoint is not connected`,
  on the host or in ANY container that mounts it (Plex, Radarr, Sonarr, Unpackerr,
  Cleanuparr).**
  → Cause: the mount owner (`altmount`) was restarted/recreated and every dependent still
  holds a stale reference to the old mount instance — this is the exact same FUSE-mount-cascade
  class this file already documents for the old `nzbdav-rclone`, just with `altmount` as the
  sole owner now.
  → Fix: **never** `sudo umount` the mount yourself to "clear" it — if propagation is
  `rshared`, this tears down the real live mount too (confirmed live, made things worse this
  session). Instead: confirm `altmount` itself is healthy and its own `docker logs altmount`
  shows `"Successfully mounted WebDAV via RC"` recently, then `docker compose restart` (or
  `up -d --force-recreate`) the five dependents — `radarr sonarr plex unpackerr cleanuparr` —
  in one batch. Verify with `docker exec <name> sh -c "ls /mnt/altmount"` on each afterward,
  don't assume it worked.
- **Symptom: the above happens even right after `altmount` itself was *just* restarted, and
  `docker logs altmount` shows repeating `ERROR : IO error: couldn't list files: 401
  Unauthorized` in `/config/rclone.log` (or via `docker exec altmount cat /config/rclone.log`).**
  → Cause: this is the real upstream bug (javi11/altmount#691, fixed in our fork's PR #792,
  not yet merged) — `createConfig()` writes the WebDAV password into rclone's config
  unobscured, rclone then tries to de-obscure the plaintext into garbage credentials. Confirm
  by checking `docker-compose.yml`'s `altmount` service still says `image:
  altmount-local-fix:obscure-pass` — if it's back to `ghcr.io/javi11/altmount:latest`, someone
  (Watchtower?) reverted it, or this is a fresh deploy that skipped the local build.
  → Fix: rebuild the patched image (`docker build -f docker/Dockerfile -t
  altmount-local-fix:obscure-pass <cloned-fork-dir>` — the fork is `WhispersOfJ/altmount`,
  branch `fix/internal-mount-obscure-password`) and redeploy. Check whether PR #792 merged
  upstream first — if so, switch back to the stock tagged image instead of maintaining the
  fork build.
- **`~/Claude/altmount`** is a persistent local clone of the AltMount fork
  (`WhispersOfJ/altmount`). Its `main` is now the definitive, pushed baseline — consolidated
  from the original scoped PRs plus a deeper path-traversal pass, CI-gated
  (`altmount-fixes-ci.yml`: build/vet/lint/test) and kept in sync with upstream
  (`sync-upstream.yml`: daily merge from `javi11/altmount` main, `-X ours` so this fork's fixes
  win any conflicting hunk, validated before push). Treat `main` as current, not the old
  `fix/all-consolidated` branch name or the "kept deliberately local" framing from the first
  audit round — check `main` there before re-auditing AltMount from scratch.
- **Host now has a real Go toolchain** (`go` 1.26, `gopls`) installed directly on this machine
  (not just inside a container) — installed for the AltMount audit above, but usable for any
  Go work in this repo or elsewhere. The `LSP` tool needs `gopls` on the *host* PATH
  specifically; a Docker-container-only `gopls` install won't satisfy it.
- **Files created via `docker run ... golang:...` (or similar) can end up root-owned and/or
  read-only** (e.g. a mounted Go module cache) — a plain `chmod -R u+w` can fail with
  "Operation not permitted" on those files. Use `sudo rm -rf` to clean up scratch directories
  that mixed host and containerized work.
- **Symptom: a Radarr/Sonarr download sits at `status: completed` /
  `trackedDownloadState: importing` (or `importPending`/`importBlocked`) forever, no error, and
  `GET /api/v3/command` shows a `ProcessMonitoredDownloads` entry permanently stuck at
  `"status": "started"` (never reaches `completed`), blocking every other command from even
  starting (they sit at `"status": "queued"` indefinitely).**
  → Cause: a genuinely wedged background command inside Radarr/Sonarr itself — confirmed live
  this session, distinct from a single wedged download. Control-panel's own
  `/api/arr/{app}/unstick-importing` endpoint (see `arr_unstick_importing()` in `app.py`) only
  clears the *queue item*, not this stuck *command* — running it alone is not sufficient here,
  confirmed by it reporting a clean "wedged/cleared" result while the underlying command stayed
  stuck and the next grab hung identically.
  → Fix: restart the affected app's container outright (`docker compose restart radarr` or
  `sonarr`) — this was the only thing that actually cleared it. Check
  `GET /api/v3/command` again afterward to confirm no stuck entries remain before assuming the
  pipeline is healthy.
- **Symptom: a new download client that streams via a separate FUSE/WebDAV mount (a different
  filesystem than the real root folder) fails imports silently, or Radarr/Sonarr logs show
  nothing useful at all about why import never happens.**
  → Cause: `copyUsingHardlinks: true` (the default) — hardlinks cannot cross a filesystem
  boundary, and a FUSE-mounted download client's storage is never the same filesystem as
  `/data/movies`/`/data/shows` on regular disk. This doesn't surface as an obvious error in
  every version — check this setting first, don't wait for a clear failure message.
  → Fix: `PUT /api/v3/config/mediamanagement/1` with `copyUsingHardlinks: false` on both apps.
  **Superseded 2026-07-23**: this stack no longer imports from a cross-filesystem FUSE source
  at all — AltMount's `import.import_strategy` was switched to `SYMLINK` with `import_dir`
  bind-mounted from `./media/altmount-import`, on the *same* filesystem as `/data/movies`/
  `/data/shows` (confirmed via `df`), so `copyUsingHardlinks` was flipped back to `true` on
  both apps and verified live: a real import produces a genuine symlink into `/mnt/altmount`
  (`lrwxrwxrwx`, readable, streams real bytes) with zero bytes copied to local disk, not a
  real file. If this setting is ever `false` again without a new cross-filesystem source
  being introduced, something regressed — the reasoning above (hardlinks can't cross a
  filesystem boundary) is still correct, it just no longer applies to this stack's current
  download-client source.
- **Reserved-shell-variable gotcha, hit multiple times this session and worth remembering
  generally**: this environment's default shell treats `status` as a read-only variable
  (mirrors `$?`, zsh-style) — using it as an ordinary variable name in a Bash-tool script
  fails with `read-only variable: status` and can silently corrupt output if combined with
  `2>&1` redirection into a file (confirmed live: an entire bulk git-recovery loop overwrote
  33 files with error text this way before being caught by a `fish -n` syntax check). Avoid
  `status` as a variable name in ad-hoc scripts; use something like `task_status`/`dl_status`
  instead.
- **Multi-line bash `for...do...done` loops silently break when run via the Bash tool** — the
  default shell here is fish, which doesn't understand that syntax; the failure isn't always a
  clean error (confirmed live: a loop meant to iterate ~187 ids instead ran once against an
  unexpanded/mangled string, e.g. all ids concatenated into one bad request). Wrap any
  multi-line bash-style loop in `bash -c '...'` explicitly rather than trusting it to run as
  typed.
- **Building a JSON body for curl inside a nested `bash -c '...'` wrapper (needed to
  background a long-running loop) silently mangles quoting** — confirmed live twice:
  `python3 -c "...{'ids':[...]}..."` inside `bash -c '...'` inside this tool's own shell
  wrapping corrupted the embedded single/double quotes, so the loop never actually
  authenticated/deleted anything and ran harmlessly forever instead of erroring loudly.
  For any curl+JSON+loop combination, write a standalone `.py` file and run it with a
  plain `python3 script.py` instead of inlining it — avoids the nested-quoting class of
  bug entirely, and is easy to fix/rerun once, rather than debugging escaping live.
- **Radarr's `DELETE /api/v3/queue/bulk` works; Sonarr's real endpoint 404s** (confirmed live,
  same Sonarr version this stack runs) — don't assume a bulk-queue-delete endpoint is shared
  Servarr-family API just because Radarr has it. Fall back to looping individual
  `DELETE /api/v3/queue/{id}?removeFromClient=true&blocklist=false` calls for Sonarr.

- ~~Radarr's and Sonarr's "Quality Definitions" are one flat, instance-wide list each, not
  scoped per quality profile~~ **Moot as of v11.2.0**: both apps were consolidated down to a
  single "ANY" quality profile each (all other profiles deleted, everything reassigned - see
  [History](README.md#history)), so there's only one profile per instance to share the
  instance-wide size definitions with now. **Recyclarr was reinstalled 2026-07-23** (see
  History) — both apps have multiple profiles again, sharing that same instance-wide list.
- ~~Kometa's `sleep infinity` entrypoint override is load-bearing, not a placeholder~~ **Moot
  as of v11.7.0**: Kometa was removed entirely (no Jellyfin support - see the migration History
  entry), along with its Quickstart companion. No automated collections/overlays/metadata tool
  currently runs in this stack.
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
  untested, not confirmed either way.
- **Cleanuparr's Content Blocker / MalwareBlocker feature can never work in this stack — not a
  config gap, a structural limitation, confirmed 2026-07-23.** `grep -a` across the actual
  Cleanuparr 2.9.16 binary (`/app/Cleanuparr` inside the container) for download-client-type
  strings turns up only `qBittorrent`/`Deluge`/`rTorrent`/`Transmission`/`uTorrent` — no
  `SABnzbd`/`NZBGet` string exists anywhere in the build. MalwareBlocker requires a row in
  Cleanuparr's own `download_clients` table (a *direct* Cleanuparr-to-client connection,
  separate from the `arr_instances` table QueueCleaner uses) to do its blacklist deletion at
  the client level, and there is no client type it could ever register for a 100%-Usenet
  stack. `download_clients` had been empty since at least 2026-07-20 (confirmed via its own
  logs going back that far, i.e. this predates the AltMount cutover — it was already broken
  under NzbDAV too, just never noticed), and every hourly run logged `[MalwareBlocker] No
  download clients configured` the entire time with zero protective effect. **Disabled
  outright** (`content_blocker_configs.enabled` → `0` in `config/cleanuparr/cleanuparr.db`,
  container stopped/backed-up/edited/restarted, same WAL-safety practice as every other live-DB
  edit in this file; verified via the restart log no longer listing a ContentBlocker job
  trigger). **QueueCleaner is unaffected and confirmed still working correctly against
  AltMount** — it operates purely through the `arr_instances`/Sonarr-Radarr queue API (strikes,
  failed-import removal, stall detection), never touches the `download_clients` table, and its
  strike/removal logic was observed firing correctly live on AltMount-sourced downloads the same
  day. A stack-wide audit the same session found no other non-Usenet-friendly feature enabled
  anywhere else (Cleanuparr's own seeding-rule tables and Download Cleaner are empty/disabled;
  Prowlarr/Radarr/Sonarr indexers and download clients are 100% Usenet; Unpackerr has no
  torrent-client env vars) — this was the only live one.
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
  upstream yet as of this writing** — `docker-compose.yml` originally kept `nzbdav/nzbdav:latest`
  (the stock, unpatched image) pinned rather than the local patched build, since redeploying an
  unmerged fork build permanently isn't appropriate for this repo's normal image-pinning policy.
  Auth failed against the real account even with both fixes applied on an earlier test the same
  day — most likely the account itself was genuinely rate-limited/degraded from that session's
  heavy testing (a separate, external, time-based condition), not a remaining code bug.
  **Later the same day, the account recovered and the local patched build (`nzbdav-local-fix:pr478`)
  was deployed as a temporary, deliberate exception to the pinning policy** — see the entry below
  for why (recurring hangs during a Movies library scan) and the entry further below for AltMount,
  which superseded this fix entirely once evaluated. Re-check whether PR #478 has merged into a
  real release before assuming this local build is still the right call.
  **Confirmed recurring against Jellyfin directly, 2026-07-22** (separate from the Radarr/
  Sonarr/NeutArr mitigation above, which doesn't cover Jellyfin): a full Movies library scan
  (`RefreshLibrary` scheduled task) hung silently at a fixed progress percentage with zero new
  log lines and near-idle CPU — no exception thrown, since the .NET thread was just parked
  waiting on a blocked FUSE syscall, not faulted. Diagnosed by bypassing Jellyfin entirely: a
  plain `timeout 8 docker exec jellyfin find /mnt/nzbdav/completed-symlinks -maxdepth 3 -type f`
  hit the full 8s timeout with zero output — the mount itself was unresponsive, matching this
  section's own prior note that a raw `dd` read through the same mount had hung identically
  once before. **Recovery confirmed working**: cancel the stuck task first
  (`DELETE /ScheduledTasks/Running/{id}`), then restart strictly in mount-dependency order —
  `docker compose restart nzbdav` (clears leaked NNTP connections) → `docker compose restart
  nzbdav-rclone` (recreates the FUSE mount) → `docker compose restart jellyfin` (Jellyfin holds
  a stale mount reference after `nzbdav-rclone` restarts, same as every other dependent
  documented above) — verifying the same `find` test returns instantly after each restart
  before moving to the next, rather than assuming any single restart alone fixed it. A fresh
  `RefreshLibrary` trigger afterward proceeded normally. This is the same underlying bug as the
  NzbDAV connection leak above (PR #478, unmerged), just a second, previously-undocumented
  failure mode of it (a hung file read during a library scan, not just a rejected new
  connection) — no new root cause, just a new confirmed symptom.
  **The restart-chain fix above is not durable — confirmed live the same session**: the retried
  scan stalled again roughly 7 minutes after the restart, this time with the FUSE mount itself
  still responsive (`find` returned instantly) but `docker logs nzbdav` showing repeated
  `System.InvalidOperationException: Response Content-Length mismatch: too few bytes written`
  (e.g. 73830400 of 134217728 bytes) every 15-60 seconds — partial WebDAV reads dying mid-stream,
  consistent with the same NNTP-connection-leak root cause, not a new bug. This matches this
  section's own existing warning that restarting `nzbdav` "only buys a small window before the
  leak catches back up." **Deliberately left cancelled and unfinished, at the user's explicit
  choice**, rather than cycling the restart chain again expecting a different outcome — a full
  Movies library re-scan should be re-attempted only after PR #478 merges upstream into a real
  release. Don't reflexively re-run the restart-chain recovery above more than once per session
  without flagging this to the user first; it is a temporary reprieve, not a fix.
- **Jellyfin's own `Library/VirtualFolders` `RefreshProgress` field lags badly behind the real
  scan progress and cannot be trusted on its own.** During the hang above, `VirtualFolders`
  reported the Movies library frozen at `RefreshProgress: 5` the entire time, while the
  authoritative source — `GET /ScheduledTasks/{id}`'s own `CurrentProgressPercentage` — showed
  it actually climbing (24% → 35% before the hang). Use the `ScheduledTasks` endpoint, not
  `VirtualFolders`, to judge whether a scan is really moving. This also fully explains a report
  that looked like data loss but wasn't: the Jellyfin web UI's Movies library page showed a
  stale low total (2,739) while `/Items/Counts` and a `ParentId`-scoped query both independently
  confirmed the real count (9,867) twice — the UI page was reading a live, still-climbing
  in-progress count from an active (later found hung) scan, not a final total. No data was
  ever missing; ruled out first by checking `DisplayPreferences` (no stored filter) and the
  user's own `Policy` (`MaxParentalRating: None`, `EnableAllFolders: True`, no restrictions)
  before finding the real cause above.
- **Jellystat's own `Full Jellyfin Sync` task can get stuck in `Running` state in the
  `jf_logging` table forever, with no code path that ever marks it `Failed`.** Root cause,
  confirmed 2026-07-22: Jellystat holds a long-lived HTTP/WebSocket connection to Jellyfin for
  the duration of a sync; if Jellyfin's own container restarts mid-sync, that connection drops
  with `ECONNRESET` (confirmed via `docker logs jellystat`), and Jellystat's sync code has no
  handler for that disconnect that updates the task's own DB row — it just silently stops
  making progress while the row still reads `Running`, indistinguishable from a real stall
  without checking hard evidence (no new log lines for 5+ minutes, `jf_library_episodes` count
  frozen). **Fix applied**: directly `UPDATE jf_logging SET "Result"='Failed' WHERE "Id"=...`
  for the stuck row (container was not stopped first here since this is an `UPDATE` on a
  clearly-abandoned row, not a live-write conflict risk like the Cleanuparr/Lidarr-class edits
  elsewhere in this file), then `docker compose restart jellystat` — necessary because
  Jellystat's in-memory `TaskManager` singleton (confirmed via its own source,
  `backend/routes/sync.js`'s `addTask`) independently tracks whether a sync is "already
  running," so fixing only the DB row would still have blocked a fresh `/sync/beginSync` call
  after this container never crashed (`RestartCount: 0` at the time). **Don't re-run a fresh
  Full Sync in parallel with a Jellyfin library scan** — the two contending for the same
  Jellyfin API is the likely trigger for the original disconnect; wait for one to finish before
  starting the other.
- **`/sync/beginSync` and `/sync/beginPartialSync` (Jellystat's manual-trigger routes) require a
  JWT in `Authorization: Bearer <token>`, verified against `JWT_SECRET`** (the same
  `JELLYSTAT_JWT_SECRET` this stack generated into `.env` during the Plex-to-Jellyfin
  migration) — confirmed by reading `backend/server.js`'s `authenticate()` middleware directly.
  A valid token can be minted without knowing the real `APP_USER`/`APP_PASSWORD` hash (which
  this session didn't have) by signing `{user: {id: 1, username: "<any>"}}` with that same
  secret — easiest done from inside the container itself, where `JWT_SECRET` is already a live
  env var:
  `docker exec jellystat sh -c "cd backend && node -e \"const jwt=require('jsonwebtoken'); console.log(jwt.sign({user:{id:1,username:'bear'}}, process.env.JWT_SECRET))\""`.
  Confirmed working against a real `/sync/beginSync` call.

## Jellyfin reverted back to Plex, 2026-07-22 (same day as the migration)

**Jellyfin was removed entirely, same day it replaced Plex**, after repeated, unresolved
library-scan hangs (see the NzbDAV connection-leak entries above) made it unusable for a full
scan. The user explicitly chose full reversion over continuing to debug Jellyfin, accepting
that Jellyfin's own watch history/config was lost with no archive (same treatment Plex's
config got during the original migration).

- **Removed entirely**: `jellyfin`, `jellystat`, `jellystat-db` compose blocks; `config/jellyfin/`,
  `config/jellystat/`, `config/jellystat-db/`, `config/jellystat-db-dump/`, `config/jellystat-backup/`
  (jellystat-db's `18/docker` subdirectory needed `sudo rm` — Postgres-internal-owned files);
  `JELLYFIN_URL`/`JELLYFIN_API_KEY`/`JELLYSTAT_*` from `.env`/`.env.example`; the `jellystat-db`
  `pg_dump` step and its restic exclude from `scripts/backup-config.sh`; `scripts/setup_wizard.py`'s
  `JELLYFIN_API_KEY`/`JELLYFIN_URL` references reverted to `PLEX_TOKEN`/`PLEX_URL`.
- **Recovery method — read this before ever reverting a migration in this repo again**: git
  history in both `media-stack` (commit `7f9cd27`, the original Plex→Jellyfin migration) and
  the `~/.dotfiles` bare repo (commit `b406324`, the fish-function rework) still had the exact
  pre-migration `docker-compose.yml` Plex/Kometa/Quickstart/Tautulli blocks, `.env.example`
  scaffolding, and `control-panel/app.py`'s original 14 `/api/plex/*` route implementations —
  recovered via `git show <commit>~1:<path>` rather than hand-rewriting any of it. This is
  drastically faster and more accurate than reconstructing from memory, but **never a blind
  `git checkout`** — real improvements landed in these files after the original removal (the
  jellystat-db backup step, OMDb/MDBList promoted to real `.env` secrets) that had to be
  preserved, not reverted alongside the Plex-specific code.
  **One real mistake made during this recovery, worth remembering**: a loop restoring ~33 fish
  functions used `$DOTFILES show ... > file 2>&1` where `$DOTFILES` was a string variable used
  as a command — invalid in this environment's shell, and the `2>&1` silently wrote the
  resulting error text *into* every target file, overwriting all of them with garbage before
  the mistake was noticed via a `fish -n` syntax check. Recovered immediately by re-running the
  same git-show loop correctly (literal `git --git-dir=... --work-tree=...` command, stderr to
  a separate file). If a bulk multi-file git-recovery loop ever silently "succeeds" but every
  file looks identical/wrong afterward, suspect this exact class of redirect bug first.
  **`stack-nzbdav-restart.fish` specifically was never committed to the dotfiles repo at all**
  (confirmed via `git ls-files`) — its content had to be recovered from the one commit that
  last touched it on disk (`b406324`) directly, not a parent-commit diff, since git had no
  earlier version to fall back to.
- **Fresh Plex install, not a restore**: `config/plex/` (34GB) was deleted with no archive back
  during the original migration, so this is a brand-new server — claimed via a live
  `plex.tv/claim` token (valid ~4 minutes, `PLEX_CLAIM` env var added temporarily to the
  compose block and `.env`, then removed immediately after — confirmed via
  `PlexOnlineToken`/`PlexOnlineMail` appearing in `Preferences.xml`, readable only via `sudo`
  since Plex's own files are owned by `PLEX_UID=955`). Libraries created via
  `POST /library/sections` — **this endpoint expects every parameter in the URL query string,
  not the POST body**, confirmed by reading the real error in `Plex Media Server.log` ("Missing
  required query parameter name") after a body-encoded attempt 400'd with no useful message.
  Language codes are locale-specific (`en-US`, not `en` — confirmed via `/system/agents`'s own
  per-agent `<Language>` list, not guessed). VAAPI hardware transcode device path needs the
  exact raw enum string from `/:/prefs`'s `HardwareDevicePath` `enumValues` (URL-encoded colons
  included, e.g. `1002%3a1681%3a1002%3a0124@0000%3ae5%3a00.0`) — passing the human-decoded
  version silently no-ops. The recovered pre-migration compose block already had the
  `/mnt/nzbdav:/mnt/nzbdav:rslave` mount and correct `network_mode: host`/VAAPI setup baked in
  from the original migration's own fix — but its `volumes:` list only had a placeholder
  `./media:/home/bear/Stack/media` mount, predating this stack's current `./media/movies:/data/movies`
  /`./media/shows:/data/shows` convention; updated to match Jellyfin's exact mount shape rather
  than reusing the stale placeholder.
- **Bazarr repointed to Plex automatically** — it had already auto-detected the newly-claimed
  Plex server (`server_name: RAWRZ`, real machine ID) via the account's own stored OAuth grant,
  independent of the deleted `config/plex/` directory (Bazarr's OAuth token lives in its own
  DB). Only needed `settings-general-use_plex=true`/`use_jellyfin=false` plus real library
  name/id mapping via the usual form-encoded `/api/system/settings` endpoint.
- **Seerr could NOT be auto-repointed** — its admin user (`id=1`, from the earlier Jellyfin-era
  fix) had an empty `plexToken`/`plexId` (it was a Jellyfin-local login, `userType=3`), and
  Seerr's own `/api/v1/settings/plex` route requires the admin user's *own* live Plex OAuth
  token to test the connection — not fabricable, unlike an API-key-based integration. Left
  pending a real "Sign in with Plex" from the user in the browser; once that happens, the same
  reconciliation this stack already did once (promote to admin, reassign existing
  `media_request` rows via `requestedById`/`modifiedById`) will need repeating.
- **The NzbDAV connection-leak bug hit Plex within minutes of the fresh library scan starting**
  (confirmed live: a random file read through `/mnt/nzbdav` inside the `plex` container timed
  out identically to Jellyfin's earlier hangs) — this is the same account-wide bug, not
  something specific to either media server. Directly motivated evaluating AltMount below.

## AltMount evaluated as NzbDAV's replacement, 2026-07-22

**javi11/altmount** (`ghcr.io/javi11/altmount`) was researched as a candidate replacement for
NzbDAV's unfixed connection-leak bug (PR #478, see above) — chosen over
`AusAgentSmith-org/nzbdav-rs` (a from-scratch Rust rewrite of NzbDAV itself, architecturally
immune to the same bug class, but only 22 GitHub stars and stale since 2026-05-25) for being
actively developed (295 stars, a real release 3 days before this evaluation) with no reported
issues matching NzbDAV's connection-leak symptom.

- **Deployed standalone first, under its own `altmount-eval` compose profile** — not wired to
  Radarr/Sonarr or `/mnt/nzbdav` initially, so it never touches the working stack until proven.
  Own internal rclone/FUSE mount (unlike NzbDAV, no separate `-rclone` sidecar container needed)
  — same `/dev/fuse`/`SYS_ADMIN`/`apparmor:unconfined` requirements as `nzbdav-rclone`, but on
  one container. Deliberately did **not** mount `/var/run/docker.sock` (README's example
  compose includes it for an "auto-update" feature) — unnecessary privilege for an evaluation
  deployment.
- **Two real first-boot bugs found and fixed, neither obvious from the docs**:
  1. `rclone.path: ''` (the documented default, meant to fall back to the config directory) does
     **not** actually resolve to the config directory in this version — confirmed by reading
     `internal/rclone`'s actual error (`mkdir rclone: permission denied`, a *relative* path, not
     `/config/rclone`) rather than trusting the config-sample comment. Fixed by setting
     `rclone.path: '/config'` explicitly.
  2. A separate, undocumented-in-the-sample top-level `mount_type` field (`none`/`rclone`/`fuse`/
     `rclone_external`) **overrides** `rclone.mount_enabled` entirely — confirmed by reading
     `internal/config/manager.go`'s validation logic, which forcibly sets
     `RClone.MountEnabled = false` whenever `mount_type` is unset, regardless of the nested
     `rclone.mount_enabled: true` setting. `config.sample.yaml` (as cloned this session) doesn't
     mention this field at all. Fixed by adding `mount_type: 'rclone'` alongside `mount_path`.
  Also needed `sudo chown 1000:1000` on both `config/altmount` (host bind mount) and a
  pre-created `/mnt/altmount` (host `/mnt` itself is root-owned, same as `/mnt/nzbdav`'s parent).
- **Real end-to-end streaming confirmed, not just "container is healthy"**: registered a real
  admin user via `POST /api/auth/register` (first-run only; needs `password` ≥12 chars,
  `username` ≥3 chars), logged in via `POST /api/auth/login` to get a session (the `Set-Cookie`
  is domain-scoped to whatever host the request was made against — `COOKIE_DOMAIN` env var — a
  cookie obtained via `localhost` will not authenticate a request made via the real host IP, or
  vice versa). `POST /api/providers/test` gave a real, live auth handshake against the
  Thundernews account (28ms). To prove genuine article-body retrieval (not just auth), a
  minimal single-segment NZB was hand-built from a **real message-id already present in
  NzbDAV's own blob store** (`config/nzbdav/blobs/<id[:2]>/<id[2:4]>/<id>` — confirmed this
  store retains the full original NZB XML, including real message-ids, for every release ever
  imported) and submitted via AltMount's SABnzbd-compatible `/sabnzbd?mode=addfile` endpoint.
  Result: exactly 768,000 bytes retrieved, matching the segment's real declared size precisely
  — genuine proof of working article fetch. (A first attempt using a PAR2-only file correctly
  failed pre-network with "NZB file contains only PAR2 files"; a second attempt using one
  segment of a 341-segment RAR correctly failed post-fetch with "unexpected EOF" — both are
  correct validation behavior given the deliberately incomplete test input, not bugs.)
- **Radarr/Sonarr's download client repointed to AltMount for future grabs** (`host: altmount`,
  `port: 8080`, `urlBase: sabnzbd` — Fiber's `app.Use("/sabnzbd", ...)` is prefix-matching, so
  Radarr/Sonarr's hardcoded `.../{urlBase}/api` request path still lands on the right handler).
  **A real category-name mismatch found and fixed**: AltMount's own `sabnzbd.categories` config
  only had `movies`/`tv` (guessed, reasonable-looking names) but Radarr/Sonarr's own
  `movieCategory`/`tvCategory` fields are actually `radarr`/`sonarr` (their real configured
  values, confirmed via each app's own `/api/v3/downloadclient` response, not assumed) —
  AltMount rejected the connection test with "Category does not exist" until the config's
  category names were changed to match exactly.
- **NzbDAV's blob store represents the scale of what a full "replace NzbDAV" migration actually
  means**: 103,523 `DavItems` rows / ~42,885 unique `NzbNames` — i.e. the *existing* library was
  built from roughly that many already-imported releases, every one of them symlinked into
  NzbDAV's own `/mnt/nzbdav/.ids/...` path scheme, which AltMount does not reproduce. "Full
  cutover" (the user's explicit choice) requires bulk-extracting every real NZB from this blob
  store and re-submitting each to AltMount so it can build its own mount structure — a genuinely
  long-running (hours, not minutes) bulk operation, not a quick command.

## Bulk re-link run, memory incident, and full NzbDAV removal, 2026-07-22/23

The evaluation above led directly to a same-session full cutover, executed while the user was
away for 8+ hours with instructions to log non-critical issues and only interrupt for real ones.

- **Bulk re-link executed via `scripts/altmount-bulk-relink.sh`** (resumable — tracks attempted
  blob ids in `scripts/.altmount-relink-progress.log`, skips already-processed ones on a rerun).
  Extracted 38,972 unique NZBs (12,285 Radarr + 26,687 Sonarr, explicitly excluding 3,170
  Whisparr/adult-content blobs — that library was deleted by policy years earlier, re-importing
  it would have silently undone that removal) from NzbDAV's own blob store
  (`config/nzbdav/blobs/<id[:2]>/<id[2:4]>/<id>`, confirmed to retain the full original NZB XML
  including real message-ids for every release ever imported) and submitted each via AltMount's
  SABnzbd-compatible `/sabnzbd?mode=addfile` endpoint. Completed 38,972/38,972 with 38,929 real
  successes.
- **Real incident during the run, handled without waking the user**: AltMount's memory hit
  99.87% of a 2GiB limit, confirmed live via `docker logs` to coincide with two huge multi-part
  RAR archives (56GB/508 parts, 73GB/134 parts) being analyzed concurrently — per-archive memory
  cost scales with part count, and this library has several 50-70GB+ UHD remux releases. Fixed
  by raising `mem_limit` to 4g and reducing `import.max_processor_workers` 2→1 (serializes
  large-archive analysis so two can't compound again). Also fixed a broken healthcheck the same
  session (`/api/health` requires an authenticated session with no unauthenticated route in this
  version — switched to a plain port-liveness check).
- **A second, more serious bug found on the user's return, not caught by the bulk-relink
  script's own progress tracking**: AltMount stages an uploaded NZB in `/tmp/altmount-uploads`
  before moving it to the persistent `config/altmount/.nzbs/<category>/` store — and `/tmp`
  inside the container was never mounted to a volume. The mid-run `--force-recreate` restart
  (done to apply the memory/worker fix above) wiped every NZB still sitting in that ephemeral
  path, which was nearly the entire ~28,460-item backlog still queued behind a single worker at
  the time. Confirmed with second-precision certainty: the last successful import completed at
  01:54:55 UTC, ten seconds before the restart at 01:55:05. Real consequence: of the 1,748 items
  AltMount had actually finished processing (not just accepted via the submission script — a
  distinct metric this file's own earlier entry didn't separate clearly enough), only 748
  succeeded and 1,000 failed, all with the identical `"raw NZB file is missing and no store was
  found ... to regenerate it"` error. **Lesson for any future AltMount deployment: mount `/tmp`
  (or wherever `altmount-uploads`/`.altmount-queue` land) to a persistent volume, or never
  restart the container while anything is queued.** This wasn't fixed in place — see below for
  why it became moot.
- **This exact mistake happened again, 2026-07-23, for a reason that looked too minor to
  warrant checking first — that's the actual lesson, not the mem_limit change itself.**
  `docker compose up -d altmount` was run to apply a `mem_limit: 4g` → `6g` bump (a config-only
  change, seemingly unrelated to the queue) without checking `import_queue` for pending rows
  first. `/tmp/.altmount-queue` still isn't a persistent volume (confirmed again via `docker
  inspect altmount --format '{{range .Mounts}}...'` — no `/tmp` entry), so the recreate wiped
  237 queued NZBs the same way as the incident above. AltMount then burned through the dead
  rows for ~4 minutes before being caught and stopped, and each failure triggered Radarr/
  Sonarr's `unmonitor + blocklist without re-search` — 37 Sonarr episodes (mostly *Game
  Changer*, *Um Actually*, *Make Some Noise*) and 3 Radarr movies got silently unmonitored and
  permanently blocklisted for a release that would otherwise have just needed a normal retry.
  Recovered live: stopped `altmount` immediately on noticing, dropped the remaining 234 dead
  `import_queue` rows at the user's explicit call (container stopped, DB backed up first, same
  WAL-safety practice as every other live-DB edit in this file) rather than trying to repair
  them, restarted `altmount` + the five mount-dependent containers per the FUSE cascade rule,
  then cleared all 40 blocklist entries (`DELETE /api/v3/blocklist/bulk` on both apps) and
  re-monitored all 40 affected items (`PUT /api/v3/episode/monitor` bulk on Sonarr, per-movie
  `PUT /api/v3/movie/{id}` on Radarr) so a regrab would actually find something instead of
  silently skipping a blocklisted release. **Hard rule, no exceptions**: before running
  `docker compose up -d altmount`, `--force-recreate altmount`, `docker restart altmount`, or
  `docker stop`/`docker kill altmount` for *any* reason — a memory limit tweak, a config
  one-liner, an unrelated debugging step, anything — first run
  `sqlite3 config/altmount/altmount.db "SELECT status, COUNT(*) FROM import_queue GROUP BY
  status;"` (container can stay up for a read-only `SELECT`) and confirm `pending`/`processing`
  is 0, or drain/wait it out first. The reason for the recreate does not matter and is not a
  factor in whether this check is needed — "it's just a memory bump" is exactly the reasoning
  that caused this to happen twice.
- **The same hard rule caught a third real recurrence, 2026-07-23**: adding Sportarr's
  category to `config/altmount/config.yaml` needed a restart, which (as always) wiped ~778
  pending queue rows and caused a small blocklist fallout (2 Radarr movies, 4 Sonarr episodes)
  before being caught and cleaned up the same way as the incidents above. No new lesson here —
  just further confirmation this rule has zero exceptions, including "just adding a category."
- **User's response on return: abandon the old library entirely rather than repair the
  re-link.** Explicit instructions, executed in this order:
  1. AltMount's queue backlog (39,168 rows) killed directly via
     `DELETE FROM import_queue` in `config/altmount/altmount.db` (container stopped first,
     WAL-safety, same practice as every other live-DB edit in this file) rather than the
     one-nzo-id-per-call SABnzbd delete endpoint, which has no bulk form.
  2. **Radarr's and Sonarr's databases fully wiped** (confirmed scope via explicit
     clarification: "only API key/download client/indexer config survives" — everything else,
     including quality profiles and root folders, was expected gone). Full `config/radarr`/
     `config/sonarr` backed up first to `~/backups/pre-wipe-<timestamp>/`. `radarr.db`/
     `sonarr.db` (+ `-wal`/`-shm`) deleted outright and let the app recreate a fresh schema on
     restart, rather than hand-editing tables — safer given foreign-key relationships an
     unfamiliar schema could break. `config.xml` (real API key) was never touched. Download
     client re-added via API (**stripping the leftover `id` field before POST** — Radarr/Sonarr
     reject creating a new row with an explicit existing id, "Can't insert model with existing
     ID 1"). Indexers were **not** successfully hand-recreated via API (400s — these are
     Prowlarr-owned definitions, not meant to be manually reconstructed); instead, re-saving
     Prowlarr's own Application entry with `?forceSync=true` on `PUT /api/v1/applications/{id}`
     triggered a real, immediate sync that recreated all 3 indexers on both apps correctly.
     Quality profiles came back automatically (Radarr/Sonarr create defaults on any fresh DB
     init); root folders (`/data/movies`, `/data/shows`) had to be re-added manually via
     `POST /api/v3/rootfolder`.
  3. **NzbDAV removed entirely** — `nzbdav`/`nzbdav-rclone` compose blocks deleted; `/mnt/nzbdav`
     unmounted on the host (`sudo umount -l`) and every remaining `/mnt/nzbdav` bind mount
     (Plex, Radarr, Sonarr, Unpackerr, Cleanuparr) repointed to `/mnt/altmount`; `config/nzbdav`
     (51GB) and `config/nzbdav-rclone` deleted; `NZBDAV_*` `.env`/`.env.example` vars renamed to
     `ALTMOUNT_*` where the same real credentials still apply (the Thundernews provider
     host/user/password, now consumed by AltMount's `config.yaml` instead); `control-panel/app.py`
     reworked (`nzbdav_api()`→`altmount_api()`, `/api/nzbdav/*`→`/api/altmount/*`, `CONTAINER_LABELS`,
     `MOUNT_PREREQS`/`MOUNT_PROVIDERS` simplified to reflect AltMount owning its own mount
     directly with no separate rclone sidecar) — `set-connections`/`unstick` routes were **not**
     ported, both were workarounds for NzbDAV-specific bugs (its non-REST settings API; its
     history-query-hang-causing-Sonarr-unavailable chain) that don't apply to AltMount, dropped
     outright rather than guessed-and-carried-forward; `scripts/nzbdav-prune-history.py` →
     `scripts/altmount-prune-history.py` (same logic, real endpoint path difference:
     `/sabnzbd` not `/api`), its systemd timer/service swapped the same way (old symlinks in
     `~/.config/systemd/user/` were live and enabled — disabling/removing/relinking done in
     one pass, not left dangling); the `.claude/skills/` project skills
     (`secret-injector`, `usenet-orchestrator`, `docker-compose-manager`) also referenced NzbDAV
     and were updated — `usenet-orchestrator`'s `diagnose-stuck-file` command was **not** ported
     (built around NzbDAV/nzbdav-rclone's specific `.ids/<uuid>` log pattern, no confirmed
     AltMount equivalent exists yet) and now refuses to run rather than search logs that likely
     don't match; every `stack-nzbdav-*` fish function reworked to `stack-altmount-*` or deleted
     outright (`set-connections`/`unstick` had no port target, matching the backend routes).
  4. **Plex's own library was left holding ~9,867 movies/424 shows worth of now-permanently-broken
     symlinks** (Plex's own DB was never wiped, only Radarr/Sonarr's) — flagged to the user as a
     real, non-obvious consequence of steps 2-3 rather than silently left broken. The user chose
     to mass-delete Plex's library manually rather than have it done programmatically.
- **Resolved 2026-07-23, see the dedicated entry below**: this bullet used to say AltMount's
  `import_strategy: NONE` direct-import pipeline was unverified end-to-end. It was verified,
  found to be silently writing real files to local disk instead of symlinks (`import_strategy:
  NONE` + `copyUsingHardlinks: false` together mean every import is a real byte copy), and
  fixed by switching to `import_strategy: SYMLINK`. See "Local media eliminated, AltMount
  switched to SYMLINK import strategy, 2026-07-23" below for the full incident.

## Local media eliminated, AltMount switched to SYMLINK import strategy, 2026-07-23

A routine disk-usage question ("how full is my root disk") surfaced a real architecture
regression: **318.7GB across 150 real (non-symlink) files** were sitting under
`media/movies`/`media/shows`, contradicting this file's own long-standing "root folders are
100% symlinks" invariant. Root cause: AltMount's `import.import_strategy` was `NONE` (a direct
copy/hardlink import, unlike NzbDAV's old symlink-into-FUSE-mount model), combined with
Radarr's/Sonarr's `copyUsingHardlinks: false` (a deliberate earlier fix for when the download-
client source was the cross-filesystem `/mnt/altmount` FUSE mount, see the landmine above) —
together these guaranteed every import since the AltMount cutover wrote a real byte-for-byte
copy to local disk. The other ~34,809 items in the library turned out to be symlinks, but
**every single one sampled was broken**, pointing at `/mnt/nzbdav/.ids/...` — dead since NzbDAV
was removed entirely. The real, working library was 100% those 150 real files; the pre-cutover
library was 100% non-functional.

**Fix, at the user's explicit direction ("I want no media on the disk, make the config match
that")**:
1. Added a new host directory, `./media/altmount-import`, confirmed via `df` to be on the
   *same filesystem* as `./media/movies`/`./media/shows` (both under `/`, `nvme0n1p2`) — bind-
   mounted identically as `/mnt/altmount-import` into `altmount`, `radarr`, and `sonarr`
   (`docker-compose.yml`).
2. AltMount's `config.yaml`: `import.import_strategy` → `SYMLINK`, `import.import_dir` →
   `/mnt/altmount-import`. AltMount now creates a symlink there pointing into `/mnt/altmount`
   (the real FUSE-streamed content) instead of writing bytes.
3. Radarr's and Sonarr's `copyUsingHardlinks` flipped back to `true` via
   `PUT /api/v3/config/mediamanagement/1` on both — now safe because the symlink source and
   the root folder share a filesystem, so a "hardlink" of a symlink just creates another
   symlink, never a real copy. See the landmine above for the historical reasoning this
   supersedes.
4. Recreated `altmount` first (mount-cascade ordering, see the existing landmine on this),
   confirmed healthy, then `radarr`/`sonarr` — all three confirmed to see the new shared mount
   correctly before touching anything else.
5. **All 318.7GB of real files and all ~34,809 broken symlinks were deleted** (`find
   media/movies -mindepth 1 -delete`, same for `media/shows`) — root disk went from 92% to 20%
   used. Radarr/Sonarr's own `RescanMovie`/`RescanSeries` commands **refused to update anything**
   (`"Movie's root folder (/data/movies) is empty. Rescan will not update movies as a failsafe"`,
   HTTP 409 on `DELETE /api/v3/moviefile/{id}` too) — a deliberate app-level protection against
   mistaking a disconnected mount for real deletion, and neither app exposes an API override for
   it. Worked around the same way this file already documents for other app-level DB blocks:
   stopped each container, directly edited `radarr.db`/`sonarr.db` (`UPDATE Movies SET
   MovieFileId = 0`, `DELETE FROM MovieFiles`; same pattern for `Episodes`/`EpisodeFiles`),
   backed up both DBs first, restarted.
6. `MissingMoviesSearch`/`SeriesSearch` triggered for the 3 tracked movies and the 2 series that
   actually had files (WWE: Unreal, The West Wing) — **narrower scope was a deliberate user
   choice**, not a default: rebuilding the entire former ~35,000-item library was explicitly
   ruled out as a separate option (tens of thousands of real grabs over hours/days) versus just
   proving the new pipeline on what's currently tracked.
7. **Verified live, not just configured**: the first completed import (The Dark Knight) landed
   as a real `lrwxrwxrwx` symlink into `/mnt/altmount/movies/...` — confirmed via `stat` from
   both the host and inside the `radarr` container, and confirmed it actually streams (`head -c
   1024` returned real bytes through the symlink, not a dangling-link error).
- **A real, separate download-client-side incident surfaced during this same reimport**: Sonarr
  had **Law & Order: Special Victims Unit** (594 episodes across 28 seasons, monitored, 0 files)
  independently backfilling its entire catalog through AltMount's single-worker queue at the
  same time, ballooning it to 544GB / 100+ items and delaying the actual reimport target items
  behind it. Not a bug — a real, legitimate (if enormous) missing-episode search running
  concurrently with unrelated work. Fixed by unmonitoring the series in Sonarr (stops *future*
  searches only) and separately clearing its ~120 already-queued AltMount items. **Found a real
  AltMount API bug doing this**: `mode=queue&name=delete` only accepts one `value` (a single
  `nzo_id`) per call despite normal SABnzbd convention supporting a comma-separated list — passing
  a joined list silently deletes nothing beyond whatever the string coincidentally parses as, and
  the endpoint **always returns `{"status": true}` regardless of whether anything was actually
  deleted** (confirmed by reading `internal/api/sabnzbd_handlers.go`'s
  `handleSABnzbdQueueDelete` directly — the final fallback literally always returns success).
  Worked around by looping one DELETE call per `nzo_id`; verified against the real queue
  afterward rather than trusting the reported status.
- **A second real mount-cascade recurrence, same session**: recreating `altmount` for the
  `SYMLINK` config change (step 4 above) was done via a direct `docker compose up -d
  --force-recreate altmount` rather than Control Panel's own `restart-all` endpoint, which
  already encodes the correct `MOUNT_DEPENDENTS` ordering — `radarr`/`sonarr` were manually
  restarted afterward, but **`plex`, `unpackerr`, and `cleanuparr` were forgotten**, all three
  confirmed holding stale FUSE references (`Transport endpoint is not connected` / `Socket not
  connected`) when checked later. Fixed by restarting all three; confirmed Plex could stream a
  real symlinked file afterward. Lesson reinforced, not new: manually recreating a mount owner
  outside `restart-all` means manually remembering *every* entry in `MOUNT_DEPENDENTS`, not
  just the ones actively being worked on.
- **Plex's library section paths reconfirmed correct** during the same check: `Movies` → real
  path `/data/movies`, `Shows` → real path `/data/shows` (via `/library/sections`), matching
  Radarr's/Sonarr's root folders exactly, and Plex's own compose block does mount
  `/mnt/altmount:/mnt/altmount:rslave` — the Stash/Jellyfin-class "root folder consumer missing
  the FUSE mount" bug this file already documents does not apply to Plex's current config.

## Control Panel redesigned entirely: no boxes, no tabs, permanent log console, 2026-07-23

Full rebuild of `control-panel/static/{index.html,style.css,app.js}` plus one new backend route
(`GET /api/docs/readme`), at the user's explicit request to remove the box/card and sidebar-tab
paradigm entirely. A plan artifact with three labeled options per category (log console, source
selection, PC operations, navigation, visual system, interaction model) was produced and
approved before any code changed — see that artifact for the full option/tradeoff writeup this
summarizes.

- **Navigation**: the old sidebar-button + hidden-`<section>` pattern (functionally a tab strip
  despite not looking like one) is gone entirely, replaced by a fixed two-column split-pane
  workspace — a scrollable left column of rule-divided rails (Overview, Fleet, Host, Reference)
  and a permanently pinned right-hand log console. There is no "page" concept and no
  `showPage()`/`wireSidebarNav()` left in `app.js`.
- **Log console**: single-focus, always-visible in the right column, fed either by a
  grouped-by-subsystem source `<select>` or automatically when a palette command targets a
  container (`resolveLogContainer` → `selectLogSource`). `/api/container/{name}/logs/stream`
  now requests `timestamps=True` from the Docker SDK and the client reformats Docker's own
  RFC3339Nano prefix into a compact local clock (`formatLogLine`/`formatLogText` in `app.js`) —
  real per-line record time, not client receipt time. Applied to both the pinned console and
  the arr apps' one-shot log view (`/api/arr/{app}/logs`, also now `timestamps=True`).
- **Fleet**: every container from `/api/containers` grouped by subsystem (a static, display-only
  map mirroring `CONTAINER_LABELS`' own non-gating precedent — an unmapped service just falls
  into "Other", never hidden), collapsible per group (state persisted in `localStorage`).
  Clicking a row's tail-log icon sets it as the active log source.
- **Host**: two lanes, deliberately separated by risk class — a read-only "Vitals" lane wired
  to routes that are genuinely host-backed given this container's actual mounts
  (`mount-health`, `oom-check`, `resource-check`, `disk-usage`, `backup-verify`), and a
  "Fleet-wide actions" lane for destructive/long-running ops (`restart-all`, poster sync,
  backup-integrity-check). **Real host package-update/reboot-needed/mem-pressure/zombie-check
  checks were deliberately NOT built as live panels** — confirmed this container has no
  `pacman`, no `pid: host`, and no real host `/proc` (its own `/proc/pressure` reflects the
  container's own cgroup, not the host), so building those as live tiles would present fake or
  container-scoped data as if it were the host's. They're listed in Reference as terminal-only
  fish commands instead.
- **Reference**: quicklinks (Tautulli dropped — see the "still present but not installed" entry
  above), a "Documentation" group linking each of the 13 third-party apps' real upstream docs
  (every URL verified against `docker-compose.yml`'s actual pinned image via `gh repo view`/
  `gh search repos` before being hardcoded — not guessed from the app's common name; notably
  Seerr's real org is `seerr-team`, Watchtower's real maintained fork is `nicholas-fedor`,
  NeutArr's real repo is `I-am-PUID-0/NeutArr`, none of which match an obvious guess), plus
  this stack's own README.md served locally via the new `/api/docs/readme` route since **this
  repo has no public downstream mirror to link to** (see the `AGENTS.md` note elsewhere in this
  file). A separate, explicitly read-only list of the 14 Claude Code skills this project uses
  is shown too, clearly labeled as dev-time-only (this app has no mechanism to invoke them).
  **Correction, 2026-07-24**: this bullet used to claim Tautulli and Kometa's doc-link rows
  carried a "not installed" badge (`installed: false` in `DOC_LINKS`) — never true; `DOC_LINKS`
  never had entries for either app at any point. The `installed: false` UI branch, its
  `not-installed-tag` CSS class, and this now-incorrect comment were all removed outright as
  dead code with zero live callers (see the tautulli/kometa/quickstart removal correction near
  the top of this file).
- **Visual system**: cool slate + one steel-teal accent (`#1f6f6b` light / `#4fb3ad` dark), IBM
  Plex Sans/Mono, zero border-radius anywhere, hairline 1px borders instead of shadows/cards.
  Muted red kept for status semantics only (errors/destructive), per explicit user direction —
  not a decorative color.
- **Interaction model**: panels for passively viewing state, a command palette (`Ctrl/Cmd+K`,
  overlay not a page) for triggering any of the 146 `commands.json` operations — same
  fuzzy-match/confirm-arm engine as before, just rendered as a transient overlay instead of a
  dedicated "Console" page, and a running command's log now streams into the persistent
  right-column console instead of its own embedded pane.
- **Kometa's "Run Kometa now" rapid action was removed from Overview**, along with its now-
  unused library-picker helpers — it would always fail (`Kometa container not found`) given
  Kometa has no running container, matching the "present but dormant" correction above.
- **No headless browser was available to screenshot this in this environment** (no system
  Chrome; Playwright's installer refuses to install on CachyOS, only Ubuntu/Debian are
  supported) — verified instead via a full static cross-check (every `getElementById`/
  `querySelector` target in `app.js` confirmed to exist in `index.html`, no stale references to
  deleted classes), live endpoint checks, and the user's own live browser session confirming it
  visually (their own traffic was visible in `docker logs control-panel` polling the new
  endpoints throughout).

## Seerr and Bazarr reconnection fixes, 2026-07-23

Two separate real leftovers found from the Jellyfin-to-Plex reversion, neither caught at the
time:

- **Seerr's `mediaServerType` was still `2` (JELLYFIN)** even after Plex came back — confirmed
  via `seerr-team/seerr`'s own compiled `dist/constants/server.js` (`PLEX = 1, JELLYFIN = 2,
  EMBY = 3, NOT_CONFIGURED = 4`, not guessed). Its Plex library entries were present with the
  right real IDs but `enabled: false`. Fixed: `main.mediaServerType` → `1`, both Plex libraries
  re-enabled via `GET /api/v1/settings/plex/library?enable=1,2&sync=true` (the real endpoint,
  found by reading `internal`... rather, `dist/routes/settings/index.js` directly — the
  library-enable state isn't settable through the documented `POST /settings/plex` body, which
  rejects `libraries` as read-only), then a real full scan triggered and confirmed complete in
  logs (`Plex Scan: Full Scan Complete`).
- **The "bear" Seerr user account was still Jellyfin-linked** (`userType: 3`, real
  `jellyfinUsername`, no `plexId`/`plexToken`) despite `permissions: 2` (admin) already being
  correct. Fixed using the account's own real, already-valid Plex token (`.env`'s `PLEX_TOKEN`)
  against `plex.tv/api/v2/user` to get the genuine linked identity (`TheDaddyBear`, id
  `277265765`, real email) rather than fabricating one — `userType` → `1`, `plexId`/
  `plexUsername`/`plexToken` populated for real, Jellyfin fields cleared. DB stopped/backed-up/
  edited/restarted, same practice as every other live-DB edit in this file.
- **Seerr's request history (144 `media_request` rows, cascaded 1,208 `season_request` rows)
  and its entire local media cache (19,021 `media` rows, cascaded 2,871 `season` rows) were
  both cleared at explicit user request**, in two separate passes (`DELETE FROM media_request`
  then, later, `DELETE FROM media` — both with `PRAGMA foreign_keys = ON` so the cascades
  actually fired, container stopped/backed-up first each time). Verified the media cache
  rebuilds cleanly from a fresh `/settings/plex/sync` trigger afterward — landed at 4 real
  titles, not the stale 19,021, confirming the rebuild reflects only what's actually in Plex.
- **Bazarr's SignalR connections to Radarr and Sonarr were silently dead for 4+ hours** —
  Radarr/Sonarr had both been recreated (unrelated mount-fix work earlier the same day) but
  Bazarr's own container hadn't restarted since the previous day, so its long-lived SignalR
  feeds never noticed the peer restart and never logged a reconnect attempt (unlike earlier
  drop/reconnect cycles the same day, which *did* self-heal). Config (API keys, Plex OAuth
  link) was already entirely correct — this was purely a stale-connection issue. Fixed with a
  plain `docker compose restart bazarr`; confirmed both SignalR feeds reconnected cleanly with
  zero errors afterward, and `/api/system/status` reported live real versions from both apps.

## Recyclarr reinstalled, trash-guides-applier skill found broken, 2026-07-23

User asked to sync custom formats/quality profiles with TRaSH-Guides, explicitly ruling out
Recyclarr at first. `trash-guides-applier` skill was tried instead — its bundled JSON turned
out mostly unusable: 9 of 11 custom formats (`profiles/{radarr,sonarr}-profiles.json`) are
placeholder stubs (`{"type": ..., "value": ...}`, not real Radarr/Sonarr `implementation`/
`fields` shape — one 400'd immediately with "Condition name(s) cannot be empty"), and
`applier.py`'s `apply` command creates quality profiles with `"items": []` and no `cutoff`,
which both apps' real API rejects outright (500, `ArgumentNullException: source`) rather than
accepting as a fillable skeleton. Only the one custom format with a real API shape ("Blocklist:
Unwanted Groups/Sources, RU-CN Audio, Blu-ray") applied successfully via this skill — quality
profiles never got created through it at all. **Don't trust this skill's bundled profile JSON
or its `apply` quality-profile path without re-verifying against a live `/qualityprofile/schema`
first** — the custom-format diff/apply path for a real-shaped entry does work correctly.
User then explicitly reversed the "no Recyclarr" instruction and asked for it reinstalled.
Recovered verbatim from the v11.2.0 removal commit (`ead5f04~1` / `4f6f9f4~1`): compose
service block, `config/recyclarr/recyclarr.yml` (real TRaSH profile/CF trash_ids for both
apps), control-panel's `/api/recyclarr/status` route + `CONTAINER_LABELS` entry, and the
`stack-recyclarr-status` palette command in `commands.json` — not rebuilt from scratch.
A manual `docker exec recyclarr recyclarr sync` was run to verify immediately rather than
waiting for the 6am cron — confirmed live: 62 CFs/3 profiles on Radarr, 42 CFs/3 profiles on
Sonarr, matching `recyclarr.yml`'s own trash_ids. Existing "Any" profile assignments were
left untouched on both apps — this only recreated the tiered profiles, it didn't reassign
any movie/series to them.

## Sportarr removed entirely, 2026-07-24

Added 2026-07-23 (see the Sports PVR entry this file used to carry), removed less than 24
hours later after its Plex integration turned out to be structurally broken, and the user
chose full removal over continued debugging.

- **Root cause of the Plex problem**: the Wrestling library had two root locations,
  `/data/wrestling/WWE` and `/data/wrestling/WCW` — both one directory too deep. Since
  Sportarr's own naming convention is `{Series}/Season {year}/`, pointing the library root
  directly at the league folder made Plex treat each `Season 2021`/`Season 2023`/`Season
  2024`/`Season 2025` folder as its own top-level show (`guid="local://..."`, Plex's
  unmatched-item placeholder) instead of a season under one real "WWE" show. Confirmed via
  `section_locations` in Plex's own SQLite DB and Plex's scanner log (`"There were 1
  top-level paths for Season 2023"`, match requests for `'Season 2023'` etc. all returning
  "no metadata"). Consolidating to a single `/data/wrestling` root and forcing a rescan fixed
  it for WWE (73 real episodes, 5 real seasons, real TMDb-backed metadata) — but one WCW file
  (`Bash At The Beach 1999`) never got picked up by Plex's scanner even after empty-trash,
  repeated forced rescans, and touching the file plus both parent directories to force an
  mtime change; Plex kept reporting the `WCW` directory as unchanged and never created an
  item for it. This remained unresolved when the user decided to remove Sportarr rather than
  debug further — not a symlink/mount problem (AltMount/FUSE were confirmed healthy and
  streaming correctly throughout), a Plex scanner-cache quirk specific to that one file.
- **Everything removed, verified physically gone, not just stopped**: `sportarr` container
  stopped and `rm -f`'d; `sportarr/sportarr:latest` image `docker rmi`'d; `config/sportarr`
  (41MB) and `media/wrestling` (372KB, 100% symlinks per this stack's usual policy — no real
  bytes were ever stored) deleted with `rm -rf`; Plex's "Wrestling" library section deleted
  via `DELETE /library/sections/5` (not just emptied); Prowlarr's Sportarr Application entry
  (id 5, the second Sonarr-type sync target) deleted via `DELETE /api/v1/applications/5`.
  `docker-compose.yml`'s service block, its `SPORTARR_API_KEY` env line into control-panel,
  and Plex's now-dangling `./media/wrestling:/data/wrestling` volume mount all removed;
  `SPORTARR_API_KEY` dropped from `.env`/`.env.example`; `control-panel/app.py`'s
  `SPORTARR_URL`/`SPORTARR_API_KEY` vars, the `sportarr_api()` helper, all six
  `/api/sportarr/*` routes, and its `CONTAINER_LABELS`/`MOUNT_DEPENDENTS`/
  `ARR_LOG_CONTAINERS` entries all deleted outright (no dead-route/degrade-gracefully
  treatment — this wasn't a removed-but-still-reachable dependency like the old Plex routes,
  it never needs to respond again). No frontend (`static/*.js`/`*.html`) or `commands.json`
  entries existed for Sportarr at all — the redesigned Control Panel UI (see its own History
  entry above) never wired these routes into any panel, so there was nothing to unwire there.
  109 unit tests pass, ruff clean, `docker compose config` validates clean for both the core
  and `extras` profiles after the edits.
- **Queue cleanup done the documented-safe way, not a raw DB wipe**: AltMount's own SABnzbd
  bulk-delete (`mode=queue&name=delete` with a comma-joined value list) is the already-known-
  buggy endpoint that silently no-ops beyond the first id and always reports
  `{"status": true}` regardless (see the earlier AltMount API bug entry above) — so all 11
  `category='sportarr'` queue items were deleted with one API call per `nzo_id` instead, then
  verified against both the live SABnzbd-compatible queue (0 remaining `sportarr` slots) and
  `import_queue`'s own `category='sportarr'` row count, not just trusted from the response.
  **AltMount's `config.yaml` still needs a container restart to actually drop the `sportarr`
  SABnzbd category and stop advertising `sportarr_instances: []`** — both were removed from
  the file, but the queue had 246 pending / 1 processing items for *other* categories
  (Radarr/Sonarr) at the time, so per this file's own hard rule (see the repeat
  altmount-recreate-wipes-the-queue incidents above) the restart was deliberately deferred
  rather than risking another blocklist-fallout cascade. Restart `altmount` once
  `SELECT status, COUNT(*) FROM import_queue GROUP BY status;` shows 0 pending/processing, to
  make the category removal take effect.
- **Cleanuparr, NeutArr, and Bazarr needed no cleanup** — confirmed live: Cleanuparr's
  `arr_instances` table never had a Sportarr row (only Sonarr and Radarr), NeutArr has no
  `sportarr.json` placeholder file, and Bazarr was never wired to it at all (single-Sonarr-
  instance limitation, already a documented accepted gap before this removal). No `~/.dotfiles`
  fish functions referenced Sportarr either — Control Panel's dedicated `/api/sportarr/*`
  routes were apparently never given their own `stack-sportarr-*` CLI wrapper.
- **Full stack health swept after every change** — all remaining containers healthy, all HTTP
  endpoints reachable (Tautulli's expected failure aside — it has no container, see the
  "present but dormant" correction elsewhere in this file), confirming the removal didn't
  regress anything else.

## Backup/DR details beyond "restic + a Dropbox tarball"

- **Every backup this stack had was deleted 2026-07-23, at the user's explicit request, while a
  new backup policy is being decided — this stack currently has zero backup coverage of any
  kind.** Deleted: the local restic repo (`~/backups/stack-restic-repo`, 83GB), the offsite
  restic repo (`/home/bear/Dropbox/stack-restic-repo-offsite`, 83GB, riding on Dropbox sync),
  and every ad-hoc pre-change snapshot made during that session's own work (including a real
  Radarr/Sonarr config backup made hours earlier during a DB wipe — required `sudo` to delete,
  since it was captured root-owned). The three backup systemd timers (`stack-backup.timer`,
  `stack-arr-backup.timer`, `stack-claude-backup.timer`) were stopped and unlinked, not deleted —
  their `.service` unit definitions and the real source files under `systemd/` in this repo are
  untouched, so re-enabling later is just `systemctl --user link systemd/stack-*.timer &&
  systemctl --user enable --now stack-*.timer` once a new policy is chosen, not a rebuild.
  Everything below this bullet describes the backup system as it existed before this deletion -
  read it as design/history, not as "this is currently running."
- **No Postgres-backed service ran in this stack from v11.0.0 (when `zilean-postgres` was
  removed with the rest of the debrid layer, along with `scripts/backup-config.sh`'s
  logical-`pg_dump` step for it) until 2026-07-22, when `jellystat-db` (`postgres:18.1`)
  reintroduced one** as part of the Plex-to-Jellyfin migration (Jellystat, Tautulli's
  Jellyfin-equivalent, needs its own Postgres). **This is exactly the gap this section already
  warned about — `jellystat-db` currently has zero backup coverage**, since it has no logical
  `pg_dump` step of its own yet and restic's raw-datadir exclusion (see below) doesn't cover a
  live Postgres datadir safely. Not yet fixed as of this writing; treat this as a known,
  outstanding gap, not something already handled. Any other new DB-backed service added later
  gets the same zero-coverage default unless it gets its own logical-dump step added.
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
  case — it wasn't proven to be the actual cause the first time. **Partial follow-up found
  2026-07-22, during the Plex-to-Jellyfin migration (see below)**: while auditing Plex's Movies
  library before decommissioning it, it turned out to only have 59-63 items indexed against
  ~10,004 real files on disk. Plex's own `Plex Media Scanner.log` showed a single event on
  2026-07-13 (9 days earlier) where the scanner removed 661 of 794 tracked items in one pass
  ("Taking 661 items out of the map... for being unavailable"), with `autoEmptyTrash` confirmed
  `true` via Plex's own `/:/prefs`. This is very likely the missing Plex-side half of this same
  incident: real files vanished from disk (the Radarr/Sonarr side above), Plex's next scan found
  the symlinks broken, and `autoEmptyTrash` silently deleted the corresponding library items.
  Confirmed *not* caused by the NzbDAV connection-leak bug (also dated 2026-07-22, same day) —
  no Plex log activity from today shows any removal events, only normal scan/analysis noise.
  Since Plex is now removed entirely, this can never be root-caused further. **This closes the
  loop on what was learned, not the underlying uncertainty**: the original Radarr/Sonarr-side
  file loss still has no confirmed cause, only this newly-found Plex-side symptom of it.
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
- **Plex was removed entirely 2026-07-22, replaced by Jellyfin** (`lscr.io/linuxserver/jellyfin:latest`,
  new `jellyfin` service in `docker-compose.yml`). Two libraries carried over exactly: Movies
  (`/data/movies`), Shows (`/data/shows`); the same VAAPI hardware-transcode device
  (`/dev/dri/renderD128`) carried over from Plex's config. Metadata providers: TheMovieDb + OMDb
  on Movies, TheTVDB + TheMovieDb + OMDb on Shows — **OMDb ships bundled with Jellyfin core
  already active, not a separate catalog install**, a real correction made mid-session after an
  earlier draft plan wrongly assumed it needed installing. A second assumption corrected the
  same session: this bundled plugin's own configuration schema (`GET /Plugins/{id}/
  Configuration`) exposes only `{"CastAndCrew": true}`, no API key field at all, confirmed live
  rather than guessed — nothing was actually pending here either. Plugins installed: Playback Reporting,
  Chapter Segments Provider, TMDb Box Sets (all official catalog), plus two third-party plugins
  — Intro Skipper (`https://intro-skipper.org/manifest.json`) and a "Bazarr" plugin
  (`https://raw.githubusercontent.com/enoch85/bazarr-jellyfin/main/manifest.json`) — all five
  pending a Jellyfin container restart to actually load, not yet confirmed active.

  **Jellystat** (`cyfershepard/jellystat:latest`) plus its own **`jellystat-db`**
  (`postgres:18.1`) were added as Tautulli's Jellyfin-equivalent, since Tautulli is Plex-only —
  this reintroduces a Postgres dependency to the stack for the first time since
  `zilean-postgres` was removed in v11.0.0 (see the Backup/DR section above — it has zero
  backup coverage right now, a known gap, not yet fixed). **A real bug found and fixed on first
  start**: the compose block originally mounted `./config/jellystat-db:/var/lib/postgresql/data`
  (matching this stack's usual `postgres` volume convention), but `postgres:18+` crash-looped
  immediately with "PostgreSQL data in an old, unsupported location" — the 18+ image manages its
  own version-specific subdirectory under a single `/var/lib/postgresql` mount now, confirmed
  via the container's own log output, not guessed. Fixed by mounting `/var/lib/postgresql`
  directly (partial data dir cleared first). A second bug: `jellystat`'s own healthcheck
  (`curl -sf http://localhost:3000/`) failed every time with `curl: not found` — this image has
  no curl, only `wget` (confirmed via `docker exec`); fixed by switching the healthcheck to
  `wget -qO-`. Both containers are up and healthy, and Jellystat's own first-run setup is
  **complete** — confirmed directly via `jellystat-db`'s `app_config` table (real
  `JF_HOST`/`JF_API_KEY`, admin user `bear` matching Jellyfin's real user ID,
  `PartialJellyfinSync`/`JellyfinSync`/`Backup` tasks scheduled) and a populated
  `jf_library_items` table (7,799 rows), not just assumed from the containers being up.
  **Tautulli itself was removed entirely** the same follow-up session (compose block,
  `config/tautulli/`, its `CONTAINER_LABELS` entry) — initially left orphaned pointed at the
  now-gone Plex, then fully removed on explicit request; its two `/api/tautulli/*` routes were
  left as documented dead code (503 gracefully, same treatment as `/api/plex/*`) rather than
  reworked, since Jellystat already covers the same role.

  **Kometa cannot talk to Jellyfin at all** — confirmed directly against `kometa-team/kometa`'s
  own `config-schema.json`, which has no `jellyfin`/`emby` top-level property, only `plex`. This
  contradicts several blog-post sources (jellywatch.app etc.) claiming Kometa supports
  Jellyfin — those are wrong/outdated as of this check; the real state is an open, unimplemented
  Jellyfin feature request on Jellyfin's own tracker (features.jellyfin.org/posts/2899). Kometa
  and its Quickstart companion were initially just stopped (`docker compose stop kometa
  quickstart`, config/compose untouched), then **removed entirely at the user's explicit
  follow-up request, same session**: both compose service blocks deleted; `config/kometa/`
  (901MB) and `config/quickstart/` (469MB) deleted, but not before backing up
  `config/kometa/config.yml` specifically to `~/backups/removed-configs/
  kometa-config.yml.bak-2026-07-22` — unlike Plex's config (pure app-internal state), this file
  held real third-party credentials (Trakt client ID/secret, GitHub PAT) with no other copy
  anywhere; OMDb/MDBList keys were live inside that same file and got promoted to real
  `OMDB_KEY`/`MDBLIST_KEY` `.env` secrets rather than lost, since `control-panel/app.py`'s
  `/api/ratings/imdb` and `/api/ratings/mdblist` routes depended on reading them off it live.
  `control-panel/app.py`'s `/api/kometa/run` route and `KometaRunRequest` model were deleted
  outright (no missing-env-var 503 fallback existed for this one to degrade into, unlike the
  Plex routes), and its `CONTAINER_LABELS` dict entries for both containers removed.

  **Bazarr reconfigured** for Jellyfin via its usual undocumented `POST /api/system/settings`
  form-encoded endpoint (same gotchas as always — boolean fields need lowercase `true`/`false`
  strings, array fields need repeated keys): `general.use_jellyfin=true`,
  `jellyfin.url=http://jellyfin:8096`, movie/series libraries mapped by name and Jellyfin's real
  library IDs (`jellyfin.movie_library`, `jellyfin.movie_library_ids`,
  `jellyfin.series_library`, `jellyfin.series_library_ids`), `jellyfin.refresh_method`,
  `update_movie_library`/`update_series_library=true`. `general.use_plex` set to `false`. Real
  field names verified against Bazarr's own live `GET /api/system/settings` response first,
  rather than trusting the Bazarr wiki's paraphrased docs.

  Watch-history migration (`qdm12/plex-to-jellyfin`,
  `ghcr.io/qdm12/plex-to-jellyfin`) was attempted but **explicitly abandoned by the user's own
  decision** ("don't worry about the watch history") — Jellyfin's libraries have no migrated
  watch history/ratings from Plex, a clean start, deliberate, not an oversight.

  Systemd units and scripts removed entirely: `systemd/stack-plex-webhook.service`,
  `systemd/stack-plex-report.service`, `systemd/stack-plex-report.timer` (all three were live,
  active, enabled user-level units, removed from both `~/.config/systemd/user/` and this repo's
  `systemd/`), `scripts/plex-webhook-listener.py`, `scripts/plex-library-report.py`.
  `.env`/`.env.example`'s `PLEX_URL`/`PLEX_TOKEN`/`PLEX_WEBHOOK_PORT` removed, replaced by
  `JELLYFIN_URL`/`JELLYFIN_API_KEY`. **`config/plex/` (34GB, including the Plex Media Server
  SQLite database with all watch history/ratings/metadata) and `config/plex-transcode/` were
  permanently deleted at the user's explicit request, no archive kept** — a deliberate,
  confirmed-with-the-user choice, not accidental data loss.

  **Fixed same-day, not open anymore**: Jellyfin's compose block was initially deployed with no
  `/mnt/nzbdav` mount at all — reproduced the exact Stash-deploy bug class (root folders are
  100% symlinks; series/seasons matched fine since those are real directories, but every
  episode came back silently unadded since the episode *files* are symlinks into
  `/mnt/nzbdav` and resolved to nothing inside the container). Confirmed live (a sample
  episode file was a dangling symlink; `cat` on it inside the container failed with "No such
  file or directory"), fixed by adding `/mnt/nzbdav:/mnt/nzbdav:rslave` to Jellyfin's volumes,
  reverified as readable, and the library rescanned. `control-panel/app.py`'s
  `MOUNT_DEPENDENTS` set was updated to `{"radarr", "sonarr", "jellyfin", "unpackerr",
  "cleanuparr"}` (`plex` → `jellyfin`) as part of the same fix. **A separate, since-reverted
  attempt**: Jellyfin was briefly moved to `network_mode: host` (the same exception Plex used
  to be the sole holder of) so its UDP client-discovery broadcast (port 7359, what mobile
  apps' Bonjour-style LAN scan uses to auto-find the server) could actually reach the physical
  LAN — bridge-mode port-mapping doesn't work for broadcast discovery, confirmed against
  Jellyfin's own networking docs, same root-cause class as Plex's old GDM/DLNA host-networking
  requirement. **Deliberately reverted back to `stacknet` bridge + published port 8096 at the
  user's explicit request** the same session — mobile-app LAN auto-discovery does not work as
  a result, accepted tradeoff, not an oversight. This stack has zero services on
  `network_mode: host` again as of this reversion. Seerr's Jellyfin connection (below) is
  unaffected either way, since it was already configured to reach Jellyfin via `HOST_IP:8096`,
  not the Docker service name.

  **`control-panel/app.py`'s 14 Plex-specific routes fully reworked to Jellyfin's real API**
  (later same overall migration effort, not left dead): `plex_headers()` → `jellyfin_headers()`
  (`X-Emby-Token` header); `/api/plex/scan` → `/api/jellyfin/scan` (`POST /Library/Refresh`);
  `/api/plex/libraries` → `/api/jellyfin/libraries` (`GET /Library/VirtualFolders`);
  `/api/plex/analyze` + `/api/plex/butler/deep-media-analysis` **consolidated** into
  `/api/jellyfin/deep-analysis` (fires `RefreshChapterImages`, `RefreshTrickplayImages`,
  `IntroSkipperDetectSegmentsTask`, `AudioNormalization` together — Jellyfin's task API has no
  per-library scope the way Plex's dedicated analyze call did, so the library-scoped-vs-
  whole-server distinction Plex had doesn't carry over); `/api/plex/optimize-db` →
  `/api/jellyfin/optimize-db` (`OptimizeDatabaseTask`); `/api/plex/butler/{task}` →
  `/api/jellyfin/task/{task}` against a new `JELLYFIN_TASKS` dict built from Jellyfin's own
  live `GET /ScheduledTasks` (confirmed real Keys, not guessed) — a task is fired by looking up
  its real Id (a GUID) by Key and `POST`ing `/ScheduledTasks/Running/{id}`, since Jellyfin's
  running-task endpoint takes the Id, not the Key string; `/api/plex/updates` →
  `/api/jellyfin/updates` (simplified to a version report only — Jellyfin's linuxserver image
  is already on Watchtower's normal channel-tag train, unlike Plex which was deliberately kept
  off it, so there's no separate update-check concept to build); `/api/plex/duplicates` and
  `/api/plex/tmdb-missing` → `/api/jellyfin/duplicates`/`/api/jellyfin/tmdb-missing` (Plex's
  `Media`/`Part`/`Guid` shapes replaced by Jellyfin's `MediaSources`/`ProviderIds`, live-tested
  against the real library — `tmdb-missing` correctly found the still-unmatched "4 Months 3
  Weeks and 2 Days" item this session's own Seerr sync logs had already flagged, confirming the
  logic is right, not a fluke); `/api/plex/sessions` → `/api/jellyfin/sessions` (`GET
  /Sessions`, filtered to sessions carrying a `NowPlayingItem` — idle admin connections show up
  in the raw list too); `/api/plex/recently-added` → `/api/jellyfin/recently-added` (`GET
  /Items?SortBy=DateCreated`). Poster sync (`/api/posters/*`) reworked the same way: TMDb
  matching now keys off `ProviderIds.Tmdb`/`.Tvdb`/`.Imdb` instead of Plex's Guid array, and the
  actual upload is `POST /Items/{id}/Images/Primary` with raw image bytes instead of Plex's
  URL-fetch endpoint — verified live via a real dry-run against the Movies library. Two
  concepts dropped entirely, no Jellyfin equivalent exists: `/api/plex/empty-trash` (no
  per-library trash concept) and `/api/plex/clean-bundles` (no per-item "bundle" directory
  scheme). `queue-status`'s Plex-activity folding (`_plex_activities`/`_bucket_plex_activity`)
  replaced by `_jellyfin_running_tasks`/`_bucket_jellyfin_task` against the same
  `/ScheduledTasks` data, live-tested showing real progress/ETA for a genuine concurrent
  deep-analysis run. All 109 unit tests pass (3 needed updating for the renamed bucketing
  function), ruff clean. The 5 previously-installed plugins have since loaded successfully
  after the restart mentioned above. **A real, unrelated discovery made mid-migration is filed
  as its own bullet above** (the Plex Media Scanner mass-deletion finding) — see there for the
  tie-back to this file's existing "unexplained mass Radarr/Sonarr library deletion" entry.

  **Every `stack-plex-*`/`stack-kometa-*`/`stack-tautulli-*` fish function reworked or removed**
  (tracked in `~/.dotfiles`, not this repo — see this file's own note on that). Every Plex
  maintenance function got a `stack-jellyfin-*` equivalent against the routes above; functions
  backing a dropped Plex-only concept (empty-trash, Plex-watchlist/RSS import, and every
  individual Butler-task wrapper with no real Jellyfin task behind it — garbage-collect-
  blobs/-media, generate-ad-markers, generate-voice-activity, music-analysis, backup-database,
  refresh-libraries/-local-media, upgrade-media-analysis) were deleted outright, not left
  dead. `stack-kometa-run` and both `stack-tautulli-*` functions deleted (both apps removed
  entirely). Auditing every function's own body (not just filenames) for stray references
  caught real breakage beyond the obvious renames: `stack-nzbdav-restart` still listed `plex`
  in its five mount-dependent containers to health-check; `stack-tmdb-missing` and
  `stack-queue-status` still called/referenced the deleted `/api/plex/*` routes directly (would
  have 404'd or silently mis-ordered output); `stack-rating-imdb`/`-mdblist`'s comments still
  described reading Kometa's `config.yml` instead of the new standalone `OMDB_KEY`/
  `MDBLIST_KEY` secrets. `stack-help.fish` rewritten to match. Every touched function was
  fish-syntax-checked (`fish -n`) and the core ones live-tested against the real running stack.

  **`jellystat-db` now has real backup coverage**: `scripts/backup-config.sh` gained a logical
  `pg_dump` step (`docker exec jellystat-db pg_dump -U jellystat jfstat`) written to
  `config/jellystat-db-dump/jfstat.sql`, overwritten each run (restic's own snapshot retention
  is what gives this history across days, not a dated filename) — the raw `config/jellystat-db`
  datadir itself is now explicitly `--exclude`d from restic, since a naive file-level copy of a
  live Postgres datadir has no WAL-consistency guarantee (the same lesson this project already
  learned once with `zilean-postgres`). Verified live: a full `backup-config.sh` run produced
  an 11,163,545-byte `jfstat.sql` (45,540 lines) with an empty error log, not just assumed to
  work from reading the script.

  **Real hardware transcoding confirmed working**, not just configured: a manual `PlaybackInfo`
  request with a deliberately incompatible `DeviceProfile` (forcing `SupportsDirectPlay: false`)
  against a real library item, followed by actually fetching an HLS segment (not just the
  playlist — the transcode process only spawns once a segment is requested), produced a real
  `ffmpeg` process inside the container with `-hwaccel vaapi -hwaccel_output_format vaapi
  -codec:v:0 h264_vaapi` and a `scale_vaapi` filter - genuine VAAPI hardware encode/scale via
  `/dev/dri/renderD128`, not software fallback. A real 394KB `.ts` segment was produced and the
  test session closed afterward.

  **Seerr, since repointed at Jellyfin** (fixed same session, only supports one media server at
  a time per its own GitHub issue #511): `config/seerr/settings.json`'s `main.mediaServerType`
  set to `2` (`MediaServerType.JELLYFIN` — confirmed from `seerr-team/seerr`'s own
  `server/constants/server.ts`, not guessed) and the `jellyfin` settings block filled with
  `ip: <HOST_IP>` (not the Docker service name — Jellyfin was briefly on `network_mode: host`
  during this same session, and Seerr's connection was set up to survive that either way),
  `port: 8096`, the real `JELLYFIN_API_KEY`. A stale browser session cookie masked the first
  login attempt (Seerr's JWT auth is stateless/signed, not tied to the user record, so an old
  cookie shows the dashboard without ever hitting the new auth flow) — a fresh logout/login
  created a real new user row (`userType: 3` = JELLYFIN, confirmed via `server/constants/
  user.ts`) correctly linked. That new account got only `permissions: 32` (REQUEST) instead of
  admin, because Seerr only auto-grants admin (`permissions: 2`) to the very first user ever
  created, and this instance already had one (the old Plex admin) — with Plex gone there was no
  way to log in as that account to promote the new one through the UI, so `permissions` was set
  directly in `config/seerr/db/db.sqlite3`'s `user` table (container stopped first, DB backed up
  before editing, same WAL-safety practice as every other live-DB edit in this file). The old
  Plex-linked user row had 144 real `media_request` rows attached (`ON DELETE CASCADE` on
  `requestedById`) - reassigned to the new account before deleting the dead row, not dropped.

  **NzbDAV's STRM import mode, evaluated and deliberately rejected**: `api.import-strategy`
  (values `symlinks`/`strm`) is a real, working NzbDAV feature - confirmed by reading
  `backend/Queue/PostProcessors/CreateStrmFilesPostProcessor.cs` directly, which writes a plain
  `.strm` text file containing a direct HTTP URL back to NzbDAV's own `/view/...` endpoint,
  bypassing `/mnt/nzbdav` entirely (genuinely Emby/Jellyfin-only; Plex never supported `.strm`,
  confirmed against this file's own prior note on that). **Not adopted**: the setting is global
  to NzbDAV, not something Jellyfin could opt into alone - it changes what Radarr/Sonarr's own
  import pipeline receives too, and that side has real, documented risk: an open, unresolved
  `Radarr/Radarr#11435` describes a grab-import-delete loop specific to `.strm` files from a
  SABnzbd-compatible client (exactly NzbDAV's emulation), Radarr's own `VideoFileInfoReader`
  runs `ffprobe` directly against the `.strm` text file (always fails, breaking media-info
  extraction), and a live user of this exact NzbDAV+Radarr/Sonarr combination
  (`nzbdav-dev/nzbdav` Discussion #175) reports being forced back to rclone because "the arrs
  can't figure out how to import .strm files." Revisit only if that Radarr issue is confirmed
  fixed in a real release - don't re-attempt from a general "STRM should work" assumption.

## Control-panel gotchas beyond restart ordering and CSRF

- **Cleanuparr's instance-check in `control-panel/app.py` bypasses Cleanuparr's own HTTP API
  entirely and reads its SQLite DB file directly** — `/api/instances` on Cleanuparr itself
  returns an HTML shell, not JSON, so there was no API-level way to get this data.
- **`/api/version` depends on an exact regex match against a specific line format in
  `README.md`.** This compounds the single-file bind-mount staleness issue already noted above —
  reformatting that line in README *or* editing README without a `--force-recreate` on
  `control-panel` can both silently break version reporting.
- **`claude-review` CI (`.github/workflows/claude-code-review.yml`) failed on every real
  (non-Dependabot) PR from at least 2026-07-15 through 2026-07-23 — fixed same day.** Root
  cause: `401 Invalid bearer token` — the `CLAUDE_CODE_OAUTH_TOKEN` repo secret itself was
  expired/invalid (`gh secret list` showed it last set 2026-07-09), not a permissions or
  prompt problem. Confirmed by temporarily adding `show_full_output: true` to the workflow
  (past the SDK's default output redaction) and running it via a genuine trigger PR — a
  workflow-file change on the *same* PR gets skipped outright by GitHub's own "must match
  default branch" validation, so seeing the real error needed the flag merged to `main` first,
  then a separate PR to trigger a real run; flag reverted after use. **Fixed by running
  `/install-github-app` from a local `claude` session**, which re-authorized against the
  user's own Claude account and rewrote `CLAUDE_CODE_OAUTH_TOKEN` (`gh secret list` timestamp
  moved to the moment the command completed) — this step needs the account owner's own OAuth
  authorization, it isn't fixable by editing files in this repo. **Verified working, not just
  configured**: an empty-commit throwaway PR (#28, closed after use, no branch left behind)
  completed a real `claude-review` run post-refresh (~1 minute runtime, matching a genuine
  Claude Code SDK invocation, not the ~15s instant-skip pattern the validation-guard produces)
  with no `is_error`. One retry was needed — the very first post-refresh attempt still hit the
  same "must match default branch" skip, apparently a brief propagation lag right after the
  workflow file's own most recent change landed on `main`; a second empty-commit push a minute
  later ran for real. No branch protection is configured on this repo, so none of this ever
  blocked a merge — it was a broken CI signal, now a working one.
- **`/install-github-app` doesn't just refresh `CLAUDE_CODE_OAUTH_TOKEN` — it also silently
  overwrites both `.github/workflows/claude-code-review.yml` and `claude.yml` with its own
  current upstream template, auto-committing and auto-merging the diff (PR #27, same session
  as the token refresh above) without asking.** Confirmed real, not hypothetical: that sync
  deleted the Dependabot-skip guard (`if: github.actor != 'dependabot[bot]'` plus
  `allowed_bots: 'dependabot[bot]'`) from `claude-code-review.yml` — the exact fix already in
  place for a previously-documented, real bug (GitHub withholds repo secrets from
  Dependabot-triggered `pull_request` runs, so this job fails every time without the skip) —
  and downgraded `actions/checkout@v7` → `v4` in both files. Both restored by hand the same
  session. **Any future run of `/install-github-app` needs its resulting diff reviewed before
  trusting it**, not just the secret's refreshed timestamp — it will silently re-strip this
  guard again if the upstream template hasn't changed to include an equivalent by then.

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
