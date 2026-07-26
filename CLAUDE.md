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
Seerr, Radarr/Sonarr for organizing, Usenet fetch via BearMount, Plex for serving) plus
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
  BearMount's FUSE mount and its import queue — recreating it while items are queued is a
  repeat, documented incident).
- Real API keys/secrets are never in `STACK.md` or any tracked file — they live in `.env`
  (gitignored) and each app's own `config/<app>/` directory. `STACK.md` documents *where* a
  given app's key lives and how to rotate it, not the key values themselves.
- Any container touching a FUSE mount or a busy DB during shutdown needs `stop_grace_period`
  set — mount owner and mount consumer both, including containers restarted by automated
  recovery logic. See STACK.md's 2026-07-25 root-cause landmines before assuming a service is
  exempt.
- A dependent container's own bind-mount view of BearMount can go stale independently of the
  host and of BearMount itself, even while Docker healthchecks pass. Verify mount health from
  *inside the specific dependent container* (`docker exec <container> ls /mnt/bearmount/...`),
  not just the host or BearMount's own container. See STACK.md 2026-07-25.
- Always use `--force-recreate` for bearmount's dependent cascade, never `restart` — `restart`
  reuses the container's existing mount namespace and never picks up bearmount's fresh FUSE
  mount, leaving every dependent silently stale. After recreating bearmount, verify the host
  mount is actually up (`ls /mnt/bearmount` succeeds) before touching any dependent — recreating
  them against a still-settling mount reproduces the same stale-handle problem. See STACK.md
  2026-07-26.
- If bearmount itself fails to (re)mount with `transport endpoint is not connected` or
  `fusermount3: user has no write access to mountpoint`, clear it with
  `sudo umount -l /mnt/bearmount` then recreate again — see STACK.md 2026-07-26.
- Plex's `autoEmptyTrash` setting has mass-deleted library items 3x on a stale-mount scan
  (confirmed history in STACK.md) and is now disabled — don't re-enable it without reading
  that history first.

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

# MANDATORY before recreating/restarting/stopping bearmount for ANY reason — see STACK.md
sqlite3 config/bearmount/bearmount.db "SELECT status, COUNT(*) FROM import_queue GROUP BY status;"

# FUSE mount-table leak check (should be 0) — see STACK.md
mount | grep -c bearmount-import

# Corruption check — test multiple offsets, retry failures before concluding real corruption
# (see STACK.md: a single failed read under heavy load is usually contention, not corruption)
docker exec bearmount dd if='/mnt/bearmount/<path>' bs=1M skip=<N> count=1 2>/dev/null | wc -c

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
`/api/arr/{app}/manual-import-all` scans queue items one at a time, sequentially — a 50+ item
queue can legitimately take several minutes; that's not a hang.

**`README.md`** is the only end-user documentation in this repo (long, organized by subsystem
with a linked table of contents) — read the relevant section there for how a feature is meant
to work. **`STACK.md`** is the operational/incident memory for Claude Code specifically
— read it for how things have actually broken, what's currently true vs. historical, and the
gotchas that aren't visible from reading the code alone.

**`FIXES.md`** tracks the still-open BearMount FUSE read-hang investigation (50GB+ REMUX files,
`ffprobe` deadlocks in D-state) — condensed state of what's fixed vs. not, and where the trail
left off. `POST /api/bearmount/unstick-ffprobe-hang` automates the operational mitigation
(detect, blocklist, recreate+cascade) — reach for it instead of doing that dance by hand.
