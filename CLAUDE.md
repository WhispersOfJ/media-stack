Read existing files before writing. Don't re-read unless changed.
Thorough in reasoning, concise in output.
Skip files over 100KB unless required.
No sycophantic openers or closing fluff.
No emojis or em-dashes.
Do not guess APIs, versions, flags, commit SHAs, or package names. Verify by reading code or docs before asserting.
Any outbound `urllib` request in `scripts/*.py` needs an explicit `User-Agent` header — several
Cloudflare-fronted endpoints (Discord's webhook included) 403 the bare `Python-urllib/3.x` default.


# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Docker Compose media-acquisition-and-serving stack (indexing via Prowlarr, requests via
Seerr, Radarr/Sonarr for organizing, Usenet fetch via NzbDAV + its nzbdav_rclone FUSE-mount
sidecar, Plex for serving) plus
`control-panel/`, a custom FastAPI dashboard — the one in-repo application, everything else is
off-the-shelf images wired together in `docker-compose.yml`.

## Read STACK.md before touching this stack

**HARD RULE: all documentation about this stack — architecture facts, current-state
corrections, known landmines, incident history, control-panel gotchas, backup/DR details,
workflow playbooks, root-cause writeups, anything explaining *why* something is the way it is
or *what happened* — goes in `STACK.md`, never in this file.** CLAUDE.md holds only short
imperative rules and pointers; it does not narrate incidents or carry the reasoning behind a
fix, no matter how significant that fix was. If you're about to write more than one sentence
explaining *why*, that sentence belongs in `STACK.md`, with at most a one-line pointer left
here. This is deliberate, not an oversight — this file was cut from 157K to ~5K chars by moving
everything narrative into `STACK.md`; do not let it regrow.

`STACK.md` is large (this repo has a long, incident-dense history — Plex/Jellyfin migrations,
three Usenet-client cutovers, multiple app removals) and is meant to be searched/read in
relevant sections, not loaded in full every turn. Before making any change to this stack:

- `grep`/search `STACK.md` for the service or subsystem you're touching before assuming you
  know its current state — several services were added, removed, renamed, or replaced multiple
  times, and old assumptions are wrong more often than not.
- Check STACK.md's "Known current landmines" and "Architecture facts" sections for anything
  relevant to the change before running destructive or restart-type commands (especially around
  nzbdav_rclone's FUSE mount and NzbDAV's download queue — recreating a mount-owning container
  while items are queued is a repeat, documented incident class across every download-client
  this stack has run).
- Real API keys/secrets are never in `STACK.md` or any tracked file — they live in `.env`
  (gitignored) and each app's own `config/<app>/` directory. `STACK.md` documents *where* a
  given app's key lives and how to rotate it, not the key values themselves.
- Any container touching a FUSE mount or a busy DB during shutdown needs `stop_grace_period`
  set — mount owner and mount consumer both, including containers restarted by automated
  recovery logic. See STACK.md's 2026-07-25 root-cause landmines before assuming a service is
  exempt.
- A dependent container's own bind-mount view of `/mnt/remote/nzbdav` can go stale
  independently of the host and of nzbdav_rclone itself, even while Docker healthchecks pass.
  Verify mount health from *inside the specific dependent container*
  (`docker exec <container> ls /mnt/remote/nzbdav/...`), not just the host or nzbdav_rclone's
  own container. See STACK.md 2026-07-25 (documented against BearMount, same underlying class).
- Always use `--force-recreate` for nzbdav_rclone's dependent cascade, never `restart` —
  `restart` reuses the container's existing mount namespace and never picks up a fresh FUSE
  mount, leaving every dependent silently stale. After recreating nzbdav_rclone, verify the
  host mount is actually up (`ls /mnt/remote/nzbdav` succeeds) before touching any dependent —
  recreating them against a still-settling mount reproduces the same stale-handle problem. See
  STACK.md 2026-07-26.
- If nzbdav_rclone itself fails to (re)mount with `transport endpoint is not connected` or
  `directory already mounted`, clear it with `sudo umount -l /mnt/remote/nzbdav` then recreate
  again — see STACK.md 2026-07-26 (BearMount) and 2026-07-28 (nzbdav_rclone's own variant of
  this, where binding the exact mount target rather than its parent caused the same symptom).
- Plex's `autoEmptyTrash` setting has mass-deleted library items 3x on a stale-mount scan
  (confirmed history in STACK.md) and is now disabled — don't re-enable it without reading
  that history first.
- nzbdav itself also bind-mounts `/mnt` directly, so it holds a FUSE handle same as
  radarr/sonarr/plex/unpackerr/cleanuparr — it is not just an upstream prereq for nzbdav_rclone.
  Restart it via a plain `docker restart nzbdav`, not `docker compose restart nzbdav` — compose
  evaluates `depends_on: nzbdav_rclone` with `restart: true` and would re-stale every other
  dependent's mount as a side effect. See `.claude/skills/docker-compose-manager/handler.py`'s
  `CASCADE_MAP`/`cmd_restart` for the actual restart-order implementation.

## Commands

```bash
# Validate compose config (what CI runs) — needs a .env first, dummy values are fine.
# DANGER on a real deployment: this OVERWRITES an existing .env with template
# placeholders, no confirmation, no backup. Check `test -f .env` first — if it
# already exists, it holds real secrets; never blindly cp over it. (Confirmed
# live 2026-07-26: recovery required reconstructing every credential from
# `docker inspect`'s running container environments.)
test -f .env || cp .env.example .env
docker compose config --quiet
docker compose --profile extras config --quiet

# Lint (what CI runs, no repo-local ruff config — defaults)
ruff check control-panel/app.py scripts/*.py
shellcheck scripts/*.sh  # CI excludes config/, media/, usenet/

# Rebuild and pick up control-panel changes — app.py AND static/ are baked into the image at
# build time, not bind-mounted, so a plain `restart` serves the old files untouched.
docker compose build control-panel
docker compose up -d control-panel

# control-panel reads .env at container-*create* time only — needs force-recreate, not restart
docker compose up -d --force-recreate control-panel

# Bring up the stack: core services, or everything (extras profile)
docker compose up -d
docker compose --profile extras up -d

# MANDATORY before recreating/restarting/stopping nzbdav or nzbdav_rclone for ANY reason —
# see STACK.md. NzbDAV's own db.sqlite schema is unconfirmed, so this goes through its SAB
# API rather than a raw sqlite query (unlike BearMount's old direct-DB check).
source .env && curl -s "http://localhost:3000/api?mode=queue&apikey=$FRONTEND_BACKEND_API_KEY&output=json"

# FUSE mount-table leak check (should be 1, not growing across recreates) — see STACK.md
mount | grep -c "remote/nzbdav"

# Corruption check — test multiple offsets, retry failures before concluding real corruption
# (see STACK.md: a single failed read under heavy load is usually contention, not corruption)
docker exec nzbdav_rclone dd if='/mnt/remote/nzbdav/<path>' bs=1M skip=<N> count=1 2>/dev/null | wc -c

# Unit tests — pure logic only, everything mocked (docker.sock, httpx, urllib). This host's
# Python is externally-managed (PEP 668): python3 -m venv /tmp/venv &&
# /tmp/venv/bin/pip install -r control-panel/requirements.txt -r requirements-dev.txt &&
# /tmp/venv/bin/pytest
pip install -r control-panel/requirements.txt -r requirements-dev.txt
pytest
```

CI (`.github/workflows/validate.yml`) runs compose-config validation, ruff, shellcheck, the
`tests/` unit suite, and a build-only Dockerfile check — no torrent/live-stack verification.
The unit suite only covers pure logic reachable with everything mocked; it does not replace
exercising a change against the real running stack (curl an endpoint, check `docker logs`,
load the dashboard) for anything that actually talks to a live container.

Fish functions (`stack-*`) aren't available in Claude Code's own shell (zsh/bash, not fish) —
invoke via `fish -c "stack-foo ..."` or call the underlying control-panel API endpoint directly.
See `fish-functions/README.md` for the full list of what's available. `/api/arr/{app}/manual-import-all`
scans queue items one at a time, sequentially — a 50+ item queue can legitimately take several
minutes; that's not a hang.

**`README.md`** is the only end-user documentation in this repo (long, organized by subsystem
with a linked table of contents) — read the relevant section there for how a feature is meant
to work. **`STACK.md`** is the operational/incident memory for Claude Code specifically
— read it for how things have actually broken, what's currently true vs. historical, and the
gotchas that aren't visible from reading the code alone.

**`FIXES.md`** now only holds historical record of the BearMount FUSE read-hang investigation
(50GB+ REMUX files, `ffprobe` deadlocks in D-state) — closed as moot when BearMount itself was
removed 2026-07-28 (see STACK.md's History). Its automated mitigation endpoint
(`/api/bearmount/unstick-ffprobe-hang`) was removed along with it, not ported — NzbDAV's mount
is a stock rclone sidecar (`nzbdav_rclone`), a different codebase with no confirmed equivalent
bug. Don't assume this class of hang still applies before re-reading that history.

## Debugging gotchas

- `cmd 2>&1 > file` does NOT redirect stderr to file (order matters) — use `cmd > file 2>&1`.
- Raw socket tests: use `python3 -c "import socket..."`, not bash `/dev/tcp/...` — this fish shell doesn't support it.
- Detect stuck FUSE/ffprobe/Plex-scanner reads host-wide: `ps -eo pid,stat,cmd | awk '$2 ~ /D/'`.
- Plex `DELETE /library/metadata/{key}` needs `allowMediaDeletion=1` set via `/:/prefs` first — always restore it to `0` after, this stack has a history of mass-deletion incidents from it being left on.
- Avoid full `/library/sections/{id}/refresh` scans when a usenet provider is degraded — a scan hitting a slow/timed-out read can falsely mark unrelated shows `deletedAt` even though files are intact. Prefer narrow per-item `/library/metadata/{key}/refresh`.
- To fully stop Plex from scanning, check ALL independent triggers: `ScheduledLibraryUpdatesEnabled`, `FSEventLibraryUpdatesEnabled`, `ButlerTaskRefreshLibraries`, `ButlerTaskRefreshPeriodicMetadata` (via `/:/prefs`) — AND Bazarr's own `plex.update_series_library`/`update_movie_library`, which fires independently on every subtitle grab.
- Bazarr's `POST /api/system/settings` silently no-ops (returns 204 but doesn't persist) with a JSON body — use form-urlencoded (`--data-urlencode "settings-plex-update_series_library=false"`).
- Sonarr/Radarr `autoRedownloadFailed`/`autoRedownloadFailedFromInteractiveSearch` (`/api/v3/config/downloadclient`) causes retry storms when a provider has widespread missing segments — disable rather than trying to blocklist individual queue items (the queue is transient; items cycle out before you can act on them).
- nzbdav/ThunderNews quirk: `STAT` returns `430 No such article` fast for a missing article, but `BODY` on the same article can hang with no response until timeout — this is the actual cause of "mount stalls," not a bug in rclone/nzbdav/Plex.
- NzbDAV's `POST /api/get-config` must be called as a form-encoded POST (`--data-urlencode config-keys=...`, repeated) — despite the name, a GET with `?config-keys=...` query params 500s with a missing-Content-Type error.
