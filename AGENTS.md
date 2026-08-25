# AGENTS.md

Complete reference for AI coding agents working in this repo. Read `CLAUDE.md` first for
work style and non-negotiable rules — this file covers the system itself.

---

## What This Repo Is

A private, self-hosted media-acquisition-and-serving stack. 21 Docker Compose services,
55 fish CLI functions, a Django control panel, an arr-dashboard, Prometheus/Grafana monitoring,
and CI/CD via GitHub Actions. Hosted on Arch Linux at `192.168.4.20`.

**This repo has no public mirror.** Do not create one. `StackMaster`/`Stackalicious`/`StackScripts`
were deleted deliberately. The public profile README at `github.com/WhispersOfJ/WhispersOfJ`
is a summary page, not a code mirror.

---

## Architecture

```
Prowlarr (indexers) ──▶ Radarr + Sonarr ──▶ nzbdav (Usenet) ──▶ FUSE mount ──▶ Plex
                              │
                    ┌─────────┴─────────┐
                    │                   │
          Control Panel :8420    arr-dashboard :41789
          (Infrastructure)       (Media Operations)
                    │                   │
              Prometheus :9090    Grafana :3001
```

### Two Dashboard Surfaces

| Panel | Port | Technology | Responsibilities |
|-------|------|------------|-----------------|
| **Control Panel** | 8420 | Django + htmx | Container lifecycle, host operations, NzbDAV, Watchstate, FUSE mounts, queue aggregation |
| **arr-dashboard** | 41789 | Next.js (Node 22) | Multi-instance queue/calendar/history, TRaSH Guides, library cleanup, auto-hunting, Plex analytics, notifications, statistics |

They share no state. Both talk independently to Radarr/Sonarr/Prowlarr APIs.

- **Content flow:** Prowlarr indexes → Radarr/Sonarr queue → nzbdav downloads → rclone FUSE mount → Plex serves
- **Metadata:** Metacache (:8765) caches TMDB/TVDB lookups locally so Plex refreshes hit cache
- **Observability:** Prometheus scrapes node-exporter, cadvisor, nzbdav-exporter, metacache. Loki ingests syslog + Docker logs via Promtail. Grafana queries both.
- **Control:** Django dashboard at :8420 for infrastructure ops. arr-dashboard at :41789 for media ops.

---

## Services (21 containers)

| # | Service | Purpose | Port |
|---|---------|---------|------|
| 1 | `plex` | Media server | — |
| 2 | `radarr` | Movie management | 7878 |
| 3 | `sonarr` | TV show management | 8989 |
| 4 | `prowlarr` | Indexer manager | 9696 |
| 5 | `seerr` | Request manager (Jellyseerr) | 5055 |
| 6 | `nzbdav` | Usenet download client + WebDAV | 3000 |
| 7 | `nzbdav_rclone` | FUSE mount sidecar (streams on demand) | — |
| 8 | `unpackerr` | Auto-extracts downloads | — |
| 9 | `cleanuparr` | Cleans orphaned files + failed downloads | 11011 |
| 10 | `watchstate` | Tracks what you've watched | 8705 |
| 11 | `control-panel` | Django infrastructure dashboard | 8420 |
| 12 | `arr-dashboard` | Next.js media operations dashboard | 41789 |
| 13 | `metacache` | Metadata cache proxy for Plex | 8765 |
| 14 | `prometheus` | Metrics collection | 9090 |
| 15 | `grafana` | Dashboards + alerting | 3001 |
| 16 | `loki` | Log aggregation | 3100 |
| 17 | `promtail` | Log shipping to Loki | — |
| 18 | `cadvisor` | Container resource metrics | 8080 |
| 19 | `node-exporter` | Host CPU/RAM/disk metrics | 9100 |
| 20 | `nzbdav-exporter` | NzbDAV config/queue metrics | 1011 |
| 21 | `watchtower` | Auto-updates channel-tagged images | — |

---

## Port Map

```
3000  nzbdav (WebDAV)
3001  Grafana
3100  Loki
5055  Seerr (requests)
7878  Radarr
8080  cadvisor
8420  Control Panel (Django)
8705  Watchstate
8765  Metacache
8989  Sonarr
9090  Prometheus
9100  node-exporter
9696  Prowlarr
1011  nzbdav-exporter
11011 Cleanuparr
41789 arr-dashboard (Next.js)
```

---

## Fish Functions (55 `stack-*` commands)

All functions live in `fish-functions/` and are symlinked to `~/.config/fish/functions/` by
`scripts/fish-functions-install.py`. Naming convention: `stack-<domain>-<verb>`.

**Media operations (queue, library, calendar, Plex, Seerr, ratings, TRaSH Guides) are now
handled by arr-dashboard at :41789.** The remaining fish functions handle infrastructure only.

### NzbDAV (Usenet)

| Command | What it does |
|---------|-------------|
| `stack-nzbdav-dedup-check` | Check for duplicate downloads |
| `stack-nzbdav-delete-failures` | Delete failed downloads |
| `stack-nzbdav-history` | Show download history |
| `stack-nzbdav-queue` | Show download queue |
| `stack-nzbdav-stats` | Show download statistics |

### System / Host

| Command | What it does |
|---------|-------------|
| `stack-status` | Overall stack status |
| `stack-top` | Top containers by resource usage |
| `stack-version` | Show stack version |
| `stack-help` | Show help for all commands |
| `stack-container <name> <action>` | Container lifecycle (start, stop, restart, logs) |
| `stack-restart-all` | Restart all containers in correct order |
| `stack-reboot-check` | Check if reboot is needed |
| `stack-resource-check` | Check host resources |
| `stack-disk-free` | Show disk free space |
| `stack-disk-health` | Check disk SMART health |
| `stack-disk-config-sizes` | Show config directory sizes |
| `stack-docker-disk-usage` | Docker disk usage breakdown |
| `stack-mem-pressure` | Check memory pressure |
| `stack-oom-check` | Check for OOM kills |
| `stack-zombie-check` | Check for zombie processes |
| `stack-firewall-status` | Show firewall rules |
| `stack-ssh-doctor` | Check SSH setup health |
| `stack-kernel-check` | Check kernel version |
| `stack-mount-health` | Check FUSE mount health |
| `stack-perms-check` | Check file permissions |
| `stack-image-check` | Check Docker image versions |

### Package Management

| Command | What it does |
|---------|-------------|
| `stack-pkg-update` | Update packages |
| `stack-pkg-updates` | List pending updates |
| `stack-pkg-history` | Package install history |
| `stack-pkg-orphans` | List orphaned packages |
| `stack-pkg-cleanup` | Remove orphaned packages |
| `stack-pkg-clean-cache` | Clean package cache |
| `stack-aur-audit` | Audit AUR packages |
| `stack-flatpak-updates` | Check Flatpak updates |

### Queue / Import Management

| Command | What it does |
|---------|-------------|
| `stack-queue-status` | Show queue status |
| `stack-arr-import-backlog` | Show items waiting on import |
| `stack-command-queue-summary` | Show command queue summary |

### Cleanuparr

| Command | What it does |
|---------|-------------|
| `stack-cleanuparr-instances` | Manage Cleanuparr instances |
| `stack-cleanuparr-strikes` | Show cleanup strikes |

### Watchstate

| Command | What it does |
|---------|-------------|
| `stack-watchstate-status` | Show watch state |
| `stack-watchstate-history` | Show watch history |
| `stack-watchstate-import-now` | Import watch state now |

### Monitoring / Logging

| Command | What it does |
|---------|-------------|
| `stack-log-levels` | Show/set log levels |
| `stack-journal-errors` | Show journal errors |
| `stack-journal-size` | Show journal disk usage |
| `stack-notify-test` | Test notification delivery |
| `stack-service-failed` | Show failed systemd services |
| `stack-timer-status` | Show timer status |
| `stack-cron-list` | List cron jobs |

### Other

| Command | What it does |
|---------|-------------|
| `stack-file-backup` | Create .bak copy of a file |
| `stack-claude-home` | Launch Claude in ~/Claude workspace |
| `stack-claude-full-backup` | Full ~/Claude tar.zst backup to Dropbox |
| `stack-alacritty-theme` | Switch Alacritty theme |
| `stack-git-status-all` | Git status across all repos |
| `stack-uptime-report` | Show uptime report |
| `stack-tmdb-audit` | Audit TMDB links in Plex libraries |

### Private Helpers (not user-facing)

| File | Purpose |
|------|---------|
| `__stack_api.fish` | Call Control Panel HTTP API |
| `__stack_arr_app.fish` | Resolve app name to API path |
| `__stack_containers.fish` | Container name resolution |

---

## Control Panel API (`:8420/api/v2/`)

Django REST framework endpoints. Auth: session cookie or `Authorization: Bearer <key>` for
destructive endpoints (`/api/v2/host/*`). CSRF Origin validation on all POST/PUT/DELETE.

### Host Operations (`/api/v2/host/`)

```
GET  /api/v2/host/status                 — Container status
GET  /api/v2/host/containers             — List all containers
POST /api/v2/host/container/<name>/restart — Restart container
POST /api/v2/host/container/<name>/start   — Start container
POST /api/v2/host/container/<name>/stop    — Stop container
GET  /api/v2/host/container/<name>/logs/stream — Stream logs (SSE)
POST /api/v2/host/stack/restart-all      — Restart all in correct order
GET  /api/v2/host/settings               — Get settings
PATCH /api/v2/host/settings              — Update settings
GET  /api/v2/host/resource-check         — Host resources
GET  /api/v2/host/disk-health            — Disk SMART health
POST /api/v2/host/disk-health/prune      — Prune disk health data
GET  /api/v2/host/host-resources         — CPU/RAM usage
GET  /api/v2/host/log-levels             — Get log levels
POST /api/v2/host/log-levels/reset       — Reset log levels
GET  /api/v2/host/oom-check              — Check OOM kills
GET  /api/v2/host/disk-usage             — Disk usage
GET  /api/v2/host/mount-health           — FUSE mount health
GET  /api/v2/host/perms-check            — File permissions
GET  /api/v2/host/image-check            — Docker image versions
GET  /api/v2/host/version                — Stack version
GET  /api/v2/host/docs/readme            — README content
POST /api/v2/host/notify/test            — Test notifications
GET  /api/v2/host/top                    — Top containers
POST /api/v2/host/reboot                 — Reboot host (requires bearer auth)
POST /api/v2/host/pacman-sync            — Sync pacman databases
POST /api/v2/host/pacman-upgrade         — Upgrade packages
```

### NzbDAV (`/api/v2/nzbdav/`)

```
GET  /api/v2/nzbdav/queue               — Download queue
GET  /api/v2/nzbdav/history             — Download history
GET  /api/v2/nzbdav/dedup-config-check  — Dedup config check
GET  /api/v2/nzbdav/stats               — Download statistics
POST /api/v2/nzbdav/delete-failures     — Delete failed downloads
```

### Cleanuparr (`/api/v2/cleanuparr/`)

```
GET  /api/v2/cleanuparr/instances       — List instances
GET  /api/v2/cleanuparr/strikes         — Show strikes
```

### Watchstate (`/api/v2/watchstate/`)

```
GET  /api/v2/watchstate/status          — Watch state status
POST /api/v2/watchstate/import          — Import watch state
GET  /api/v2/watchstate/history         — Watch history
```

### Queue (`/api/v2/queue/`)

```
GET  /api/v2/queue/status               — Aggregate queue status (Arr + NzbDAV)
```

### Catalog (`/api/v2/catalog/`)

```
GET  /api/v2/catalog/                   — Software catalog
GET  /api/v2/catalog/<id>/status        — Catalog item status
POST /api/v2/catalog/<id>/install       — Install catalog item
POST /api/v2/catalog/<id>/remove        — Remove catalog item
```

### UI Routes (HTMX)

```
/                       — Dashboard overview (infrastructure only)
/host/                  — Container management
/logs/                  — Log viewer with SSE streaming
/settings/              — Settings page
/reference/             — Reference links
/activity/              — Activity log
```

---

## arr-dashboard (`:41789`)

Next.js 22 frontend that talks directly to Radarr/Sonarr/Prowlarr/Plex/Seerr APIs.
Handles all media operations that the control panel no longer provides.

### First-run setup

1. Visit `http://192.168.4.20:41789`
2. Create admin account
3. Add Radarr/Sonarr/Prowlarr instances in Settings
4. Optionally connect Plex via OAuth

### Features provided

- **Unified Dashboard:** Queue, calendar, history, statistics across all Arr instances
- **Library Management:** Browse, filter, manage movies, TV shows
- **Global Search:** Search across all indexers via Prowlarr
- **Plex Integration:** Now playing, on deck, recently added, watch history, statistics
- **Seerr Integration:** Requests, users, issues
- **TMDB Discovery:** Trending, popular, upcoming content
- **TRaSH Guides:** Quality profiles, custom formats, naming schemes, auto-sync
- **Library Cleanup:** Rule-based with 20+ condition types
- **Auto-Hunting:** Missing content search with per-instance config
- **Queue Cleaner:** Automated queue management with strike system
- **Auto-Tagger:** Criteria-based tagging with 50+ rule types
- **Notifications:** Discord, Telegram, Email, Pushover, Gotify, Ntfy, Pushbullet, Browser Push
- **Security:** OIDC, passkeys, AES-256-GCM encrypted storage
- **Backup/Restore:** Automated encrypted backups

---

## Technologies

### Backend
- **Python 3.14** — Control panel, scripts, tests
- **Django 5.2** + **Django REST Framework 3.16** — Control panel backend
- **httpx 0.28** — HTTP client for Arr/NzbDAV APIs
- **argon2-cffi** — Password hashing
- **Docker SDK for Python** — Container management
- **SQLite** — Control panel database

### Frontend
- **htmx** — Dynamic UI without JavaScript frameworks
- **Tailwind CSS** — Utility-first styling
- **SSE (Server-Sent Events)** — Live log streaming
- **Next.js 22** — arr-dashboard (separate container)

### Infrastructure
- **Docker Compose** — Service orchestration
- **rclone** — FUSE mount for streaming content
- **NzbDAV** — Usenet download client + WebDAV server
- **Plex** — Media server with hardware transcoding (VAAPI)
- **Metacache** — C#/.NET metadata cache proxy (TMDB/TVDB)

### Monitoring
- **Prometheus** — Metrics collection + alerting rules
- **Grafana** — Dashboards + visualization
- **Loki** — Log aggregation
- **Promtail** — Log shipping
- **cadvisor** — Container resource metrics
- **node-exporter** — Host metrics
- **nzbdav-exporter** — NzbDAV config/queue metrics

### Security
- **Trivy** — CVE scanning (nightly CI + pre-commit)
- **Dependabot** — NuGet + Docker base image updates
- **CodeQL** — Code scanning (v4)
- **ShellCheck** — Shell script linting
- **Ruff** — Python linting

### CI/CD
- **GitHub Actions** — 5 workflows
  - `validate.yml` — shellcheck, ruff, compose validation, 291 script/fish tests, 292 Django tests, installer build
  - `docker.yml` — Build + publish Metacacharr to GHCR
  - `trivy-scan.yml` — Nightly CVE scan of all images
  - `release-please` — Automated release management

### Languages
- **Fish shell** — 55 CLI functions
- **Python** — Control panel + 30+ scripts
- **Bash** — System scripts, CI steps
- **C# / .NET** — Metacache metadata cache proxy
- **TypeScript** — arr-dashboard (Next.js)

---

## Configuration

### Environment Variables

All secrets live in `.env` (never committed). Key groups:

| Variable | Purpose |
|----------|---------|
| `RADARR_API_KEY` | Radarr API authentication |
| `SONARR_API_KEY` | Sonarr API authentication |
| `PROWLARR_API_KEY` | Prowlarr API authentication |
| `PLEX_TOKEN` | Plex authentication |
| `PLEX_URL` | Plex server URL |
| `TMDB_KEY` | TMDB API key (read access token) |
| `TVDB_KEY` | TVDB API key |
| `FANART_KEY` | Fanart.tv API key |
| `MDBLIST_KEY` | MDBList API key |
| `OMDB_KEY` | OMDb API key |
| `NZBDAV_API_KEY` | NzbDAV API key |
| `WS_API_KEY` | Watchstate API key |
| `METACACHE_API_KEY` | Metacache API key |
| `CONTROL_PANEL_SECRET_KEY` | Django secret key |
| `CONTROL_PANEL_SERVICE_API_KEY` | Service-to-service auth key |
| `CONTROL_PANEL_ADMIN_USERNAME` | Admin username |
| `CONTROL_PANEL_ADMIN_PASSWORD` | Admin password |
| `DISCORD_WEBHOOK_URL` | Discord notification webhook |
| `GRAFANA_ADMIN_USER` | Grafana admin user |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin password |
| `HOST_IP` | Host IP address |
| `PLEX_UID` / `PLEX_GID` | Plex user/group ID |

---

## Historical Issues and Landmines

See `docs/landmines.md` for active issues and `docs/incidents.md` for dated incident history.

### Critical Landmines (affect operations today)

1. **FUSE mount fragility** — Mount-owner restart breaks all dependents. Never `sudo umount` a FUSE mountpoint. Restart the owner, then all dependents in order.

2. **Plex FSEventLibraryUpdatesEnabled disabled** — New content takes up to 6h to appear. Use arr-dashboard or Plex API for immediate scan.

3. **NzbDAV queue is not persistent** — Recreate wipes queued NZBs and silently blocklists affected items. Confirm pending is 0 before touching.

4. **Control Panel reads .env at create time only** — `restart` doesn't pick up .env changes. Use `--force-recreate`.

5. **Cleanuparr doesn't auto-register** — Discovers Arr apps but needs explicit instance registration in its `arr_instances` table.

6. **Watchtower doesn't auto-update all images** — Only channel-tagged images auto-update. Digest-pinned and manually-versioned are excluded by design.

7. **App removal checklists must be exhaustive** — Every removal touches: compose, config, env vars, Prowlarr sync, Cleanuparr, Control Panel, fish functions, content-routing groups.

---

## How to Work in This Repo

### Before Making Changes

1. Read `CLAUDE.md` for work style rules
2. Read `docs/landmines.md` for active issues
3. Read `docs/architecture.md` for service inventory
4. Check `docker compose ps` for current state

### After Making Changes

1. Run tests: `python3 -m pytest tests/ -x -q` (291 tests) and `cd control-panel-django && CONTROL_PANEL_SECRET_KEY=test pytest -x -q` (292 tests)
2. Run fish function linter: `python3 -m pytest tests/test_fish_naming.py`
3. If fish functions changed: `python3 scripts/fish-functions-install.py`
4. If completions changed: `python3 scripts/fish-completions-generate.py`
5. If Django templates changed: `docker compose build control-panel && docker compose up -d --force-recreate control-panel`

### Safety Rules

- Never commit `.env` or secrets
- Never run destructive operations without confirmation
- Never create a public mirror of this repo
- Always restart dependents after mount-owner changes
- Always confirm NzbDAV queue is empty before container operations
- Use `--force-recreate` when .env changes need to take effect
