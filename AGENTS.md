# AGENTS.md

Complete reference for AI coding agents working in this repo. Read `CLAUDE.md` first for
work style and non-negotiable rules — this file covers the system itself.

---

## What This Repo Is

A private, self-hosted media-acquisition-and-serving stack. 21 Docker Compose services,
138 fish CLI functions, a Django control panel, Prometheus/Grafana monitoring, and
CI/CD via GitHub Actions. Hosted on Arch Linux at `192.168.4.20`.

**This repo has no public mirror.** Do not create one. `StackMaster`/`Stackalicious`/`StackScripts`
were deleted deliberately. The public profile README at `github.com/WhispersOfJ/WhispersOfJ`
is a summary page, not a code mirror.

---

## Architecture

```
Prowlarr (indexers) ──▶ Radarr + Sonarr ──▶ nzbdav (Usenet) ──▶ FUSE mount ──▶ Plex
                              │
                    Control Panel (Django + htmx, port 8420)
                              │
              ┌───────────────┼───────────────┐
              │               │               │
        Prometheus :9090   Grafana :3001   Loki :3100
```

- **Content flow:** Prowlarr indexes → Radarr/Sonarr queue → nzbdav downloads → rclone FUSE mount → Plex serves
- **Metadata:** Metacache (:8765) caches TMDB/TVDB lookups locally so Plex refreshes hit cache
- **Observability:** Prometheus scrapes node-exporter, cadvisor, nzbdav-exporter, metacache. Loki ingests syslog + Docker logs via Promtail. Grafana queries both.
- **Control:** Django dashboard at :8420 with HTMX partials, SSE log streaming, poster sync

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
| 11 | `control-panel` | Custom Django dashboard | 8420 |
| 12 | `metacache` | Metadata cache proxy for Plex | 8765 |
| 13 | `prometheus` | Metrics collection | 9090 |
| 14 | `grafana` | Dashboards + alerting | 3001 |
| 15 | `loki` | Log aggregation | 3100 |
| 16 | `promtail` | Log shipping to Loki | — |
| 17 | `cadvisor` | Container resource metrics | 8080 |
| 18 | `node-exporter` | Host CPU/RAM/disk metrics | 9100 |
| 19 | `nzbdav-exporter` | NzbDAV config/queue metrics | 1011 |
| 20 | `watchtower` | Auto-updates channel-tagged images | — |
| 21 | `arr-dashboard` | Unified media dashboard (Next.js) | 41789 |

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

## Fish Functions (138 `stack-*` commands)

All functions live in `fish-functions/` and are symlinked to `~/.config/fish/functions/` by
`scripts/fish-functions-install.py`. Naming convention: `stack-<domain>-<verb>`.

### Arr Apps (Radarr/Sonarr)

| Command | What it does |
|---------|-------------|
| `stack-arr <radarr\|sonarr> <action>` | Dispatch maintenance action (rss-sync, search-missing, unstick, unstick-importing) |
| `stack-arr-backlog` | Show backlog status across both apps |
| `stack-arr-blocklist` | Show blocklisted items |
| `stack-arr-clear-blocklist` | Clear blocklisted items |
| `stack-arr-import` | Import a file into Radarr/Sonarr |
| `stack-arr-import-all` | Import all pending files |
| `stack-arr-import-backlog` | Import backlog items |
| `stack-arr-import-candidates` | Show import candidates |
| `stack-arr-import-starvation` | Diagnose import starvation (RefreshMonitoredDownloads blocked) |
| `stack-arr-list-implementations` | Show import list implementation types |
| `stack-arr-logs` | Tail Arr app logs |
| `stack-arr-missing-aired` | Show missing episodes that have aired |
| `stack-arr-queue-errors` | Show queue errors |
| `stack-arr-recently-added` | Show recently added items |
| `stack-arr-toggle-search` | Toggle automatic search on/off |

### Plex

| Command | What it does |
|---------|-------------|
| `stack-plex <action>` | Dispatch maintenance (scan, empty-trash, optimize-db, clean-bundles) |
| `stack-plex-analyze` | Analyze media files |
| `stack-plex-automatic-updates` | Check for Plex updates |
| `stack-plex-backup-database` | Backup Plex database |
| `stack-plex-butler` | Run a specific Butler task |
| `stack-plex-butler-all` | Run all Butler tasks |
| `stack-plex-clean-cache-files` | Clean Plex cache files |
| `stack-plex-clean-log-files` | Clean Plex log files |
| `stack-plex-deep-media-analysis` | Deep analysis of media files |
| `stack-plex-duplicates` | Find duplicate files |
| `stack-plex-empty-trash` | Empty Plex trash |
| `stack-plex-garbage-collect-blobs` | Garbage collect blobs |
| `stack-plex-garbage-collect-media` | Garbage collect media |
| `stack-plex-generate-ad-markers` | Generate ad markers |
| `stack-plex-generate-chapter-thumbs` | Generate chapter thumbnails |
| `stack-plex-generate-credits-markers` | Generate credits markers |
| `stack-plex-generate-intro-markers` | Generate intro markers |
| `stack-plex-generate-media-index` | Generate media index |
| `stack-plex-generate-voice-activity` | Generate voice activity markers |
| `stack-plex-import-rss` | Import RSS feeds |
| `stack-plex-import-watchlist` | Import Plex watchlist to Radarr/Sonarr |
| `stack-plex-libraries` | List Plex libraries |
| `stack-plex-loudness-analysis` | Analyze audio loudness |
| `stack-plex-music-analysis` | Analyze music files |
| `stack-plex-process-assets` | Process Plex assets |
| `stack-plex-recently-added` | Show recently added items |
| `stack-plex-refresh-epg` | Refresh EPG data |
| `stack-plex-refresh-libraries` | Refresh all libraries |
| `stack-plex-refresh-local-media` | Refresh local media |
| `stack-plex-sessions` | Show active sessions |
| `stack-plex-updates` | Check for updates |
| `stack-plex-upgrade-media-analysis` | Upgrade media analysis |

### Letterboxd / MDBList / TMDB / Trakt Integration

| Command | What it does |
|---------|-------------|
| `stack-letterboxd-radarr <action>` | Letterboxd → Radarr sync (watchlist, collection, filmography, popular, history, track/untrack) |
| `stack-mdblist-import` | Import MDBList to Radarr |
| `stack-mdblist-radarr-<action>` | MDBList → Radarr (track, tracked, untrack, history) |
| `stack-tmdb-audit` | Audit TMDB links in Plex libraries |
| `stack-tmdb-import-company` | Add TMDB studio filmography as Radarr import list |
| `stack-tmdb-import-keyword` | Add TMDB keyword-filtered list as Radarr import list |
| `stack-tmdb-missing` | Show TMDB items missing from library |
| `stack-trakt-import-list` | Import Trakt list |
| `stack-rating-imdb` | Look up IMDb rating |
| `stack-rating-mdblist` | Look up MDBList rating |

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
| `stack-queue-autofix` | Auto-fix stuck queue items |
| `stack-command-queue-summary` | Show command queue summary |
| `stack-loop-candidates` | Find items stuck in import loops |
| `stack-loop-exclude` | Add item to exclusions |
| `stack-loop-unmonitor` | Unmonitor looped items |
| `stack-cutoff-unmet` | Show items below cutoff quality |
| `stack-backlog-status` | Show backlog status |
| `stack-customformat-diff` | Show custom format score changes |
| `stack-import-lists` | List all import lists |
| `stack-radarr-import-list` | Radarr-specific import list management |
| `stack-sonarr-fix-episode-monitoring` | Fix episode monitoring issues |
| `stack-sonarr-import-custom-list` | Import custom list to Sonarr |

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

### Other

| Command | What it does |
|---------|-------------|
| `stack-file-backup` | Create .bak copy of a file |
| `stack-claude-home` | Launch Claude in ~/Claude workspace |
| `stack-claude-full-backup` | Full ~/Claude tar.zst backup to Dropbox |
| `stack-alacritty-theme` | Switch Alacritty theme |
| `stack-git-status-all` | Git status across all repos |
| `stack-uptime-report` | Show uptime report |
| `stack-seerr-requests` | Show Seerr requests |
| `stack-prowlarr-indexers` | Show Prowlarr indexers |

### Private Helpers (not user-facing)

| File | Purpose |
|------|---------|
| `__stack_api.fish` | Call Control Panel HTTP API |
| `__stack_arr_app.fish` | Resolve app name to API path |
| `__stack_containers.fish` | Container name resolution |
| `__stack_plex_butler_tasks.fish` | Butler task name resolution |

---

## Skills (`.claude/skills/`)

Domain-specific operational skills for Claude Code. Load with "Load gstack. Run /<skill>".

| Skill | Purpose |
|-------|---------|
| `arr-config-sync` | Backup/restore/diff Arr app configurations across Radarr/Sonarr/Prowlarr |
| `arr-import-starvation-diagnosis` | Diagnose RefreshMonitoredDownloads being starved by bulk search backlogs |
| `background-job-protocol` | Protocol for long-running background jobs (monitoring, snapshots, completion reports) |
| `caveman-learn` | Review token cost reports and apply cost-lowering fixes |
| `docker-compose-manager` | Safe container lifecycle management with FUSE dependency ordering |
| `health-monitor` | Full-stack health check (container status + HTTP reachability probes) |
| `media-path-validator` | Validate media paths for hardlink support and correct mounting |
| `plex-marked-deleted-db-contention` | Diagnose Plex SQLite "marked as deleted" state after concurrent scan bursts |
| `plex-red-trash-stale-fuse-handle` | Diagnose mass red-trash-can from stale FUSE handles after nzbdav_rclone recreate |
| `request-manager-integrator` | Configure Seerr ↔ Radarr/Sonarr connection |
| `secret-injector` | Generate and validate .env file, ensure all secrets present |
| `stack-cli-arr-fleet` | Fish CLI reference for Radarr/Sonarr operations |
| `stack-cli-discovery-import` | Fish CLI reference for Letterboxd/MDBList/Trakt/TMDB imports |
| `stack-cli-infra-ops` | Fish CLI reference for container control and infrastructure diagnostics |
| `stack-cli-plex-kometa` | Fish CLI reference for Plex operations |
| `stack-cli-system-maintenance` | Fish CLI reference for host/Arch Linux admin |
| `stack-cli-usenet-queue` | Fish CLI reference for NzbDAV/Cleanuparr/Prowlarr status |
| `trash-guides-applier` | Apply TRaSH-Guides quality profiles via REST API |
| `usenet-orchestrator` | Inspect and manage NzbDAV download queue and health |

---

## Scripts (`scripts/`)

| Script | Purpose |
|--------|---------|
| `arr-app-backup.py` | Backup Arr app configurations |
| `audit-tmdb-links.py` | Audit TMDB links in Plex libraries |
| `bearmount-prune-history.py` | Prune BearMount history |
| `check-container-health.sh` | Check container health status |
| `checkrr-badfiles-report.py` | Report bad files via Checkrr |
| `check-upstream-updates.sh` | Check for upstream release updates |
| `enable-recycle-bin.py` | Enable Plex recycle bin |
| `fish-completions-generate.py` | Generate fish completions from function metadata |
| `fish-functions-install.py` | Install fish functions via symlinks |
| `fish-rename.py` | Rename fish functions with search/replace |
| `generate-bug-graph.py` | Auto-generate BUG-SMASHED.md from git log |
| `import-grafana-dashboards.sh` | Import Grafana dashboards |
| `letterboxd-sync.py` | Sync Letterboxd data |
| `mdblist_toplists_import.py` | Import MDBList top lists |
| `notify-discord.sh` | Send Discord notifications |
| `plex-arr-reconcile.py` | Reconcile Plex ↔ Arr libraries |
| `plex-health-monitor.py` | Monitor Plex health |
| `plex-library-report.py` | Generate Plex library report |
| `plex-webhook-listener.py` | Listen for Plex webhooks |
| `poster-sync-fanart.py` | Sync posters from Fanart.tv |
| `provision-cleanuparr-instances.py` | Provision Cleanuparr instances |
| `radarr-orphan-empty-folders.py` | Clean orphaned empty folders |
| `scrape_letterboxd.py` | Scrape Letterboxd data |
| `setup_wizard.py` | Interactive setup wizard |
| `stage4-setup.sh` | Stage 4 Trivy setup |
| `trivy-pre-commit.sh` | Pre-commit Trivy scan |
| `trivy-scan.sh` | Full Trivy scan |
| `update-fish-api-paths.py` | Update API paths in fish functions |
| `watchstate-provision.py` | Provision Watchstate |
| `weekly-cve-scan.sh` | Weekly CVE scan |

---

## Control Panel API (`:8420/api/v2/`)

Django REST framework endpoints. Auth: session cookie or `Authorization: Bearer <key>` for
destructive endpoints (`/api/v2/host/*`). CSRF Origin validation on all POST/PUT/DELETE.

### Arr Operations (`/api/v2/arr/`)

```
POST /api/v2/arr/<app>/rss-sync          — Trigger RSS sync
POST /api/v2/arr/<app>/search-missing    — Search for missing items
GET  /api/v2/arr/<app>/search-status     — Check search status
POST /api/v2/arr/<app>/search-toggle     — Toggle automatic search
GET  /api/v2/arr/<app>/command-backlog   — Show command backlog
POST /api/v2/arr/<app>/unstick           — Unstick failed items
POST /api/v2/arr/<app>/unstick-importing — Unstick wedged imports
POST /api/v2/arr/import-starvation       — Diagnose import starvation
POST /api/v2/arr/queue-autofix           — Auto-fix queue issues
GET  /api/v2/arr/<app>/loop-candidates   — Find loop-stuck items
POST /api/v2/arr/<app>/unmonitor         — Unmonitor items
POST /api/v2/arr/<app>/manual-import     — Manual file import
POST /api/v2/arr/<app>/manual-import-all — Import all pending
GET  /api/v2/arr/<app>/missing-aired     — Missing aired episodes
GET  /api/v2/arr/<app>/blocklist         — Show blocklist
POST /api/v2/arr/<app>/blocklist/clear   — Clear blocklist
GET  /api/v2/arr/backlog-status          — Backlog status
GET  /api/v2/arr/<app>/logs              — App logs
GET  /api/v2/arr/command-queue-summary   — Command queue summary
GET  /api/v2/arr/<app>/recently-added    — Recently added
GET  /api/v2/arr/<app>/queue-errors      — Queue errors
GET  /api/v2/arr/<app>/cutoff-unmet      — Below cutoff quality
GET  /api/v2/arr/<app>/import-lists      — Import lists
GET  /api/v2/arr/<app>/import-list/implementations — List implementations
POST /api/v2/arr/<app>/import-list/add   — Add import list
GET  /api/v2/arr/<app>/customformat-snapshot — Custom format scores
```

### Plex (`/api/v2/plex/`)

```
POST /api/v2/plex/scan                   — Trigger library scan
POST /api/v2/plex/empty-trash            — Empty trash
POST /api/v2/plex/optimize-db            — Optimize database
POST /api/v2/plex/clean-bundles          — Clean bundles
GET  /api/v2/plex/libraries              — List libraries
GET  /api/v2/plex/sessions               — Active sessions
GET  /api/v2/plex/recently-added         — Recently added
POST /api/v2/plex/butler/<task>          — Run Butler task
GET  /api/v2/plex/duplicates             — Find duplicates
GET  /api/v2/plex/updates                — Check for updates
```

### Host (`/api/v2/host/`)

```
POST /api/v2/host/reboot                 — Reboot host (requires bearer auth)
POST /api/v2/host/pacman-sync            — Sync pacman databases
POST /api/v2/host/pacman-upgrade         — Upgrade packages
```

### Container Management

```
GET  /api/v2/host/status                 — Container status
GET  /api/v2/host/containers             — List all containers
POST /api/v2/host/container/<name>/restart — Restart container
POST /api/v2/host/container/<name>/start   — Start container
POST /api/v2/host/container/<name>/stop    — Stop container
GET  /api/v2/host/container/<name>/logs/stream — Stream logs (SSE)
POST /api/v2/host/restart-all            — Restart all in correct order
```

### Other API Modules

```
/api/v2/catalog/       — Software catalog (install/remove/status)
/api/v2/cleanuparr/    — Cleanuparr instances + strikes
/api/v2/nzbdav/        — NzbDAV queue/history/stats
/api/v2/seerr/         — Seerr requests
/api/v2/prowlarr/      — Prowlarr indexers
/api/v2/ratings/       — IMDb/MDBList ratings
/api/v2/letterboxd/    — Letterboxd sync
/api/v2/mdblist/       — MDBList import
/api/v2/watchstate/    — Watch state
/api/v2/posters/       — Poster sync
/api/v2/queue/         — Queue management
```

### UI Routes (HTMX)

```
/                       — Dashboard overview
/fleet/                 — Arr fleet view (queue, cards, autofix)
/host/                  — Container management
/plex/                  — Plex management
/posters/               — Poster sync
/letterboxd/            — Letterboxd sync
/mdblist/               — MDBList import
```

---

## Technologies

### Backend
- **Python 3.14** — Control panel, scripts, tests
- **Django 5.2** + **Django REST Framework 3.16** — Control panel backend
- **httpx 0.28** — HTTP client for Arr/Plex APIs
- **argon2-cffi** — Password hashing
- **Docker SDK for Python** — Container management
- **Pillow** — Image processing for poster sync
- **SQLite** — Control panel database

### Frontend
- **htmx** — Dynamic UI without JavaScript frameworks
- **Tailwind CSS** — Utility-first styling
- **ApexCharts** — Sparkline charts on overview cards
- **SSE (Server-Sent Events)** — Live log streaming

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
  - `validate.yml` — shellcheck, ruff, compose validation, 291 script/fish tests, 834 Django tests, installer build
  - `docker.yml` — Build + publish Metacacharr to GHCR
  - `trivy-scan.yml` — Nightly CVE scan of all images
  - `release-please` — Automated release management
  - `claude-code-review` — (disabled)

### Languages
- **Fish shell** — 138 CLI functions
- **Python** — Control panel + 30+ scripts
- **Bash** — System scripts, CI steps
- **C# / .NET** — Metacache metadata cache proxy
- **HTML/CSS** — Control panel templates

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

### NzbDAV Configuration

NzbDAV config is extensive — ~60 `NZBDAV_CONFIG__*` variables covering:
- Usenet providers, connections, pipelining
- Rclone mount settings
- Import strategy (symlinks)
- Repair/healthcheck settings
- Watchtower integration
- WebDAV credentials

### Metacache Configuration

```
Metacache__Arr__RadarrUrl       — Radarr API URL
Metacache__Arr__RadarrApiKey    — Radarr API key
Metacache__Arr__SonarrUrl       — Sonarr API URL
Metacache__Arr__SonarrApiKey    — Sonarr API key
Metacache__Tmdb__ApiKey         — TMDB API key
Metacache__ApiKey               — Metacache auth key
```

---

## Historical Issues and Landmines

See `docs/landmines.md` for active issues and `docs/incidents.md` for dated incident history.

### Critical Landmines (affect operations today)

1. **FUSE mount fragility** — Mount-owner restart breaks all dependents. Never `sudo umount` a FUSE mountpoint. Restart the owner, then all dependents in order.

2. **Plex FSEventLibraryUpdatesEnabled disabled** — New content takes up to 6h to appear. Use `stack-plex-scan` for immediate scan.

3. **NzbDAV queue is not persistent** — Recreate wipes queued NZBs and silently blocklists affected items. Confirm pending is 0 before touching.

4. **Control Panel reads .env at create time only** — `restart` doesn't pick up .env changes. Use `--force-recreate`.

5. **Control Panel static files baked into image** — Edit on disk → `docker compose build control-panel` → `docker compose up -d --force-recreate control-panel`.

6. **Cleanuparr doesn't auto-register** — Discovers Arr apps but needs explicit instance registration in its `arr_instances` table.

7. **Watchtower doesn't auto-update all images** — Only channel-tagged images auto-update. Digest-pinned and manually-versioned are excluded by design.

8. **App removal checklists must be exhaustive** — Every removal touches: compose, config, env vars, Prowlarr sync, Cleanuparr, Control Panel, fish functions, content-routing groups.

### Incident History

20 documented incidents from 2026-07-22 through 2026-08-25. See `docs/incidents.md` for full details. Key patterns:
- FUSE mount cascade failures (multiple incidents)
- Plex SQLite contention during import bursts
- NzbDAV queue corruption on container recreate
- Config drift between Arr apps
- Cleanuparr orphaned references after app removal

---

## How to Work in This Repo

### Before Making Changes

1. Read `CLAUDE.md` for work style rules
2. Read `docs/landmines.md` for active issues
3. Read `docs/architecture.md` for service inventory
4. Check `docker compose ps` for current state

### After Making Changes

1. Run tests: `python3 -m pytest tests/ -x -q` (291 tests) and `cd control-panel-django && CONTROL_PANEL_SECRET_KEY=x pytest -x -q` (834 tests)
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
