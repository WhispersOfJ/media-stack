Read existing files before writing. Don't re-read unless changed.
Thorough in reasoning, concise in output.
Skip files over 100KB unless required.
No sycophantic openers or closing fluff.
No emojis or em-dashes.
Do not guess APIs, versions, flags, commit SHAs, or package names. Verify by reading code or docs before asserting.


# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Docker Compose media-acquisition-and-serving stack (30 services, one `docker-compose.yml`):
indexes content via Prowlarr + Zilean, requests via Seerr, organizes via two `*arr`-family apps
(Radarr/Sonarr — Lidarr was removed entirely in v10.9.9 and Whisparr in v10.12.0, see below;
Bindery, the ebook `*arr`, was retired in v10.9.8 along with its reader Calibre-Web; no ebook app
currently in the stack), fetches via a debrid-first pipeline (Zurg + Decypharr against
Real-Debrid/AllDebrid) with a Usenet fallback (NzbDAV), and serves via a containerized Plex. There
is no adult content library in this stack anymore: Plex's own Adult library was removed in
v10.9.9 (confirmed live via `/library/sections`), and Whisparr (which managed the underlying
files/root folder) plus Stash (which cataloged it) were both removed in v10.12.0, along with the
files themselves. `control-panel/` is the one custom-built component (a FastAPI dashboard);
everything else is off-the-shelf images wired together in `docker-compose.yml`.

**`README.md` is the only documentation in this repo besides raw config** — it merges what used
to be README/TECHNICAL/CHANGELOG into one document, organized by subsystem, ~1,900 lines with a
linked table of contents. Read the relevant section there before making changes; this file only
covers what you need to get oriented and the things that aren't obvious from reading one file in
isolation.

**See `AGENTS.md` for this repo's sync obligations to two siblings** (`../Stackalicious`, a
sanitized public mirror; `../StackScripts`, a standalone redistribution of the `stack-*` CLI +
Control Panel) — a new `stack-*` command added here isn't finished until it's mirrored to both.

## Full service inventory (all 30, by subsystem)

Not a duplicate of README's service table (image/port/profile) — this is the *relationship*
map: what each service actually talks to, so a question about any one container can be
answered without re-reading `docker-compose.yml` end to end. `core` = no `profiles:` line,
comes up on a bare `docker compose up -d`; `extras` = needs `--profile extras`.

**Indexing** — `prowlarr` (core, indexer manager, pushes indexers to Radarr/Sonarr via
`fullSync`) · `zilean-postgres` (core, Postgres 18, backs `zilean` only) · `zilean` (core,
DMM cache-hash index + Zurg-ingestion second hash source, `depends_on` both
`zilean-postgres` and `zurg`).

**Debrid gateway** — `decypharr` (core, port 8282, Radarr's qBittorrent-compatible download
client, both Real-Debrid+AllDebrid) · `decypharr-alldebrid` (core, port 8283, isolated
second instance, AllDebrid-only, Sonarr's exclusive download client — exists solely because
Decypharr has no per-provider category scoping within one instance).

**FUSE mount owners** — `zurg` (core, Real-Debrid mount at `/mnt/zurg`) · `rclone-alldebrid`
(core, AllDebrid mount at `/mnt/all`) · `rclone-alldebrid-anime` (core, second AllDebrid
mount at `/mnt/all-anime`, `--include`-filtered to a hardcoded fansub-group list — kept in
sync by hand with Zurg's own anime routing groups, no shared config) · `nzbdav-rclone`
(core, mounts NzbDAV's own WebDAV filesystem at `/mnt/nzbdav`, `depends_on:
condition: service_healthy` on `nzbdav` itself, not just compose start-order).

**`*arr` apps** — `radarr` (core, port 7878, movies, `/data/movies`) · `sonarr` (core, port
8989, TV, `/data/shows` + `/data/anime`, the *only* app wired to `decypharr-alldebrid`) ·
`recyclarr` (extras, no port, daily-cron TRaSH Guides custom-format sync for both, scoped to
avoid competing with the manual "Unlimited" quality profile — not a real-time daemon despite
running as one).

**Usenet fallback** — `nzbdav` (core, port 3001→3000, WebDAV-streamed Usenet, SABnzbd-API
compatible, priority-2 download client behind Decypharr) · `nzbdav-rclone` (see FUSE mount
owners above — same container, listed once).

**Requests** — `seerr` (core, port 5055, Radarr/Sonarr only — no adult-content or music/ebook
data model, moot now that those app families are gone anyway).

**Media server** — `plex` (core, `network_mode: host` — the one deliberate exception to this
stack's publish-to-0.0.0.0 pattern, per Plex's own Docker guidance on GDM/DLNA/NAT-PMP under
bridge networking).

**Cloudflare/anti-bot** — `byparr` (extras, port 8191, Prowlarr's Indexer Proxy, Camoufox-based,
replaced FlareSolverr in v3.4.0 — same `/v1` API shape, Prowlarr's proxy type is still
literally named "FlareSolverr").

**Monitoring** — `tautulli` (extras, port 8182, Plex stats/history) · `beszel` (extras, port
8090, host/container resource-monitoring hub, replaced Glances in v10.9.9 — see the Glances
bullet above, this was undocumented outside `docker-compose.yml` until 2026-07-16) ·
`beszel-agent` (extras, no port, reports this host to the `beszel` hub over stacknet
WebSocket, `depends_on: beszel: condition: service_started`).

**Plex lifecycle** — `maintainerr` (extras, port 6246, rule-based watched/stale-content
cleanup; all server connections configured post-boot via its own UI, not env vars; rules ship
disabled by default).

**Dashboard** — `control-panel` (extras, port 8420, the one custom-built component —
`build:` from `./control-panel`, not a pulled image; talks to `docker.sock` plus every app's
own HTTP API; no auth, CSRF/Origin-Host validated only; see the dedicated gotchas section
below).

**Metadata/overlays** — `kometa` (extras, no port, `entrypoint: sleep infinity` override is
load-bearing — see landmines below; runs only via Control Panel's on-demand
`/api/kometa/run` exec, never as PID 1).

**Post-processing** — `unpackerr` (extras, no port, RAR extraction for Radarr/Sonarr's
downloads).

**Auto-updates** — `watchtower` (extras, no port, digest/channel-tag images only — Plex and
Byparr are deliberately excluded from its train, see Image pinning policy).

**DebridMediaManager (self-hosted)** — `dmm-mysql` (extras, hard-required by DMM's Prisma
schema, cannot be consolidated onto `zilean-postgres`) · `dmm-redis` (extras, rate limiting)
· `dmm-migrate` (extras, one-shot Prisma schema push, `restart: "no"`, exits after running —
`docker ps` showing it stopped is correct, not a failure) · `debridmediamanager` (extras,
port 3000, built from the `build` Dockerfile stage specifically, not `deploy` — see the DMM
Dockerfile landmine below).

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

# Rebuild and pick up control-panel code changes (it's `build:`, not a pre-built image —
# a plain `restart` reuses the old image)
docker compose build control-panel
docker compose up -d control-panel

# control-panel reads .env at container-*create* time only — a plain restart won't
# pick up a .env change here, it needs force-recreate
docker compose up -d --force-recreate control-panel

# Bring up the stack: 14 core services, or everything (+16 more behind the `extras` profile)
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
  never on Zurg's `/mnt/zurg` FUSE mount.** That mount is read-only in practice (symlink/hardlink/
  copy all fail there with `EIO`). This has regressed silently before — a library rescan can reset
  an item's root folder back to `/mnt/zurg/...` in an app's own database, which is invisible to
  git since it's app state, not stack config. If an import mysteriously stalls, check the item's
  resolved root folder before assuming a container/mount problem.
- **A root folder is 100% symlinks, never real files — any new service that reads one needs the
  same `/mnt/zurg`, `/mnt/decypharr`, `/mnt/nzbdav` mounts every existing consumer has, not just
  the root folder itself.** Confirmed as a real bug, not a hypothetical: Stash's first deploy
  mounted only `./media/adult:/data`, and every symlink under it was dangling from inside that
  container's own mount namespace — a real library scan completed in seconds with no error and
  found 0 scenes, because every `readlink` resolved to a path (`/mnt/nzbdav/.ids/...`) that
  simply didn't exist in that container. Silent, not a crash — check this first if a new
  container reading an existing root folder reports an empty/tiny library despite the source
  clearly having content.
- **FUSE-mount-owning containers and their dependents restart independently, and that's a real
  failure class, not a hypothetical.** `zurg`, `decypharr`, `decypharr-alldebrid`,
  `rclone-alldebrid`, `rclone-alldebrid-anime`, and `nzbdav-rclone` each own a mount under `/mnt`;
  every other container that bind-mounts that path keeps a stale reference after the owner
  restarts and needs its own restart to recover — this does not self-heal. `control-panel/app.py`'s
  `/api/stack/restart-all` encodes the known ordering (`MOUNT_PREREQS` → `MOUNT_PROVIDERS` →
  everything else → `MOUNT_DEPENDENTS` last), but it's a hand-maintained set, not derived from
  `docker-compose.yml` — if you add a new service that owns or depends on a FUSE mount, that set
  needs a manual update or the ordering silently stops covering it. See README's "Whole-stack
  restart: mount-order aware" section.
- **Two Decypharr instances exist because Decypharr has no per-provider category scoping** — a
  single instance's whole `debrids[]` list is available to every category on it. `decypharr` (both
  backends) serves Radarr; `decypharr-alldebrid` (AllDebrid only) is
  Sonarr's exclusive download client, with its own second mount and a Remote Path Mapping in
  Sonarr to reconcile the two instances reporting identical-looking `/app/downloads/...` paths
  that are actually different host directories.
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
- **`config/<app>/` holds real plaintext secrets** (`config/decypharr/config.json`,
  `config/zurg/config.yml`), is gitignored, and is not reproducible by `docker compose up` or
  re-pulling images — it's the one thing the backup scripts under `scripts/`/`systemd/` actually
  exist to protect. It has a real off-site leg now too (`BACKUP_REMOTE_REPOSITORY` in `.env`, a
  second restic repo riding on this host's own Dropbox sync) — don't treat
  `scripts/backup-claude-dir.sh`'s Dropbox tar as the off-site protection if you're touching
  backup tooling; it's a cruder, unretained whole-`~/Claude`-tree snapshot that has failed
  silently before, not the real disaster-recovery mechanism.
- **Zurg's content-routing (`config/zurg/config.yml`, gitignored) checks groups in `group_order`
  sequence, first match wins — a misrouted-content report can be either a missing keyword *or* a
  wrong `group_order`, and they look identical from the user's side.** `shows` uses a generic
  `has_episodes: true` heuristic; content numbered like a series (e.g. `Family.Swap.10.2023`)
  can get claimed by `shows` before a more specific group like `adult` ever runs, if `adult`'s
  `group_order` is higher (checked later). No keyword-list fix can catch that case — the group
  never receives the file to test against its regex at all. Check `group_order` first, not just
  the keyword list, when a report doesn't match any obvious missing-keyword pattern.
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
- **Adminer removed in v10.9.9, no replacement (for now).** Briefly swapped for CloudBeaver
  (`dbeaver/cloudbeaver:24.3.0`) same version, but that was reverted immediately at the user's
  request — not a fan of the tool, no substitute picked yet. There is currently no web DB GUI
  in this stack; inspecting `zilean-postgres`/`dmm-mysql` means `docker exec -it <db> psql/mysql
  ...` again, same as before Adminer existed.
- **Glances and Dozzle removed entirely in v10.9.9, no data preserved.** Neither had a config
  volume, so there was nothing on disk to clean up. Glances powered Control Panel's Overview
  "Host CPU/memory/disk/uptime" tiles via `/api/system/stats` — that endpoint and those tiles
  are gone too, not just left degraded (Control Panel itself was never re-wired to Beszel below).
  A Prometheus + Grafana monitoring stack was also researched and briefly proposed the same
  session, then cancelled before anything was built or added to `docker-compose.yml`.
  **Glances' actual replacement is `beszel`/`beszel-agent`** (added later, exact version not
  dated in this file — check `git log -- docker-compose.yml` if the timing matters), a hub+agent
  resource/container monitor at `http://<HOST_IP>:8090`. It was undocumented outside
  `docker-compose.yml` itself until a 2026-07-16 audit found it missing from
  `control-panel/app.py`'s `CONTAINER_LABELS`, README's service table, and this very bullet —
  see README's History `[10.12.1]` entry. `beszel` has no healthcheck (scratch-based image, no
  shell to exec a probe into — confirmed live, `CMD-SHELL` fails with "no such file or
  directory" despite the endpoint answering fine on a manual curl); don't read "no healthcheck"
  on this one container as neglect, it's the same class of issue as NeutArr's missing `curl`
  below, just with no fallback binary at all.

## Known current landmines (not historical — still true as of last audit)

- **NeutArr gets OOM-killed roughly every 30 minutes inside its 512MB `mem_limit`.** Invisible
  from any dashboard because `restart: unless-stopped` just quietly restarts it — `docker stats`
  or `docker inspect` (OOMKilled flag / restart count) is the only way to see this is happening;
  container "looks up" the whole time.
- **`rclone-alldebrid` does not survive a plain `docker compose restart` cleanly.** It needs a
  manual privileged lazy-unmount recovery step, and this is *not* covered by
  `restart-all`'s mount-ordering logic — treat it as a separate, manual recovery path, not
  something the cascade-restart machinery already handles.
- **Zurg's FUSE mount is a supervised rclone subprocess gated by two keys in
  `config/zurg/config.yml`** that can silently flip the mount to in-memory-only if ever toggled
  through Zurg's own live dashboard rather than the config file — a change made in the dashboard
  won't show up in `git diff` and won't be obvious as the cause of a later mount problem.
- **Kometa's `sleep infinity` entrypoint override is load-bearing, not a placeholder.** Removing
  it makes every container restart trigger a full unwanted Kometa run against the whole library.
- **`/api/decypharr/grab` (control-panel) can only target the primary Real-Debrid `decypharr`
  instance — it has no path to `decypharr-alldebrid`.** A grab intended for Sonarr's dedicated
  AllDebrid instance needs a different route/manual approach; don't assume this endpoint is
  instance-agnostic.
- **DMM's Dockerfile needs its specific `build`-stage target plus an openssl workaround to avoid
  a real crash-loop** — this isn't cosmetic pinning, changing the build stage or dropping the
  workaround has previously broken the container outright.

## Backup/DR details beyond "restic + a Dropbox tarball"

- **`scripts/backup-config.sh` does a logical `pg_dump`/`mysqldump` of `zilean-postgres` and
  `dmm-mysql` before the restic run runs**, because the restic exclude list skips raw Postgres/
  MySQL datadirs (file-level backup of a live datadir is unsafe). **Any new DB-backed service
  added later gets zero backup coverage by default** unless it's added to this logical-dump step
  explicitly — following only the "exclude the raw datadir" pattern silently drops it.
- **restic exit code 3 (some files unreadable/locked) is treated as a soft warning that still
  lets pruning proceed**, not a hard failure. Discord alerting keyed only on "error"-level restic
  output will miss a *recurring* partial-backup problem that never escalates past exit code 3.
- **`scripts/backup-claude-dir.sh` overwrites a single Dropbox tarball in place every run — there
  is no retained history for that leg at all**, unlike the restic repo's normal snapshot
  retention. Already established this script isn't the real DR mechanism; this is the specific
  reason why (one bad run can silently replace the only copy).

## Historical incidents worth knowing before touching related code

- **An unexplained mass Radarr/Sonarr library deletion happened once, with zero trail in either
  app's API or logs** — root cause was never found. The Recycle Bin setting was turned on
  afterward purely as forward-looking mitigation, not because the mechanism was identified. If a
  similar report ever comes in, don't assume Recycle Bin retroactively explains or prevents every
  case — it wasn't proven to be the actual cause the first time.
- **Sonarr has a pagination-safe `missing-aired` endpoint that exists but has zero UI wiring and
  has never been tested against this library's real scale (~300k episode records).** Don't assume
  it's a validated, ready-to-use path without treating that first real invocation as a genuine
  test, not a known-safe operation.

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
- **DMM hard-requires MySQL because of its Prisma schema** — it cannot be consolidated onto the
  stack's existing Postgres instance (`zilean-postgres`) no matter how appealing running one less
  database engine sounds.
- **Sonarr's Remote Path Mapping for the AllDebrid `decypharr-alldebrid` instance is the one
  deliberate exception to this stack's normal "no Remote Path Mappings" convention** — don't
  "clean it up" by removing it; it's reconciling two Decypharr instances that legitimately report
  identical-looking paths pointing at different host directories.
