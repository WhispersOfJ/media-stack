# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Docker Compose media-acquisition-and-serving stack (35 services, one `docker-compose.yml`):
indexes content via Prowlarr + Zilean, requests via Seerr, organizes via five `*arr`-family apps
(Radarr/Sonarr/Lidarr/Whisparr/Bindery), fetches via a debrid-first pipeline (Zurg + Decypharr
against Real-Debrid/AllDebrid) with a Usenet fallback (NzbDAV), and serves via a containerized
Plex. Stash catalogs the adult library (performers/studios/tags/StashDB identification) as an
enrichment layer alongside Plex, not a replacement for it. `control-panel/` is the one
custom-built component (a FastAPI dashboard); everything else is off-the-shelf images wired
together in `docker-compose.yml`.

**`README.md` is the only documentation in this repo besides raw config** — it merges what used
to be README/TECHNICAL/CHANGELOG into one document, organized by subsystem, ~2,300 lines with a
linked table of contents. Read the relevant section there before making changes; this file only
covers what you need to get oriented and the things that aren't obvious from reading one file in
isolation.

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

# Bring up the stack: 18 core services, or everything (+17 more behind the `extras` profile)
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
  backends) serves Radarr/Lidarr/Bindery/Whisparr; `decypharr-alldebrid` (AllDebrid only) is
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
  anything for that app — found live as a real gap: Lidarr and Whisparr had network access to
  Cleanuparr and config-type placeholders, but no connected instance, so queue-cleaning/strikes
  silently weren't covering either app. When auditing "is X wired to Y," check the receiving
  app's own config/API for a real instance entry, not just that the container can reach it.
- **Every service should have `mem_limit`/`cpus` — verify with `docker stats`, not by grepping for
  the string `mem_limit:` near a service block.** The `x-common` anchor (`<<: *common`) does not
  set either; ten services silently had neither for an unknown stretch of this project's history,
  confirmed live via `docker stats` reporting the full host memory ceiling as several containers'
  limit instead of a real number. A new service needs its own explicit `mem_limit`/`cpus` lines
  regardless of whether it uses `<<: *common`.
