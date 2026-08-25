# media-stack

**A Docker Compose media-acquisition-and-serving stack — Usenet-only, FUSE-streamed, Plex-served.**

[![CI](https://github.com/WhispersOfJ/media-stack/actions/workflows/validate.yml/badge.svg)](https://github.com/WhispersOfJ/media-stack/actions/workflows/validate.yml)
[![Release](https://img.shields.io/github/v/release/WhispersOfJ/media-stack?include_prereleases)](https://github.com/WhispersOfJ/media-stack/releases)
[![Docker](https://img.shields.io/badge/docker--compose-21%20services-blue)](https://github.com/WhispersOfJ/media-stack/blob/main/docker-compose.yml)

---

**21 containers, one `docker compose up -d`.** Indexes content via **Prowlarr**, accepts requests through **Seerr**, acquires via **nzbdav/nzbdav** (WebDAV + FUSE — streamed, never downloaded to local disk), and serves through **Plex**. Two operator surfaces: a **Control Panel** (Django + htmx dashboard on port 8420) and a **CLI** (133 `stack-*` fish functions). Fully headless-configured — no manual Settings-UI setup needed for any service.

---

## Architecture

```
                         ┌──────────────────────────────────────────┐
                         │              Control Panel                │
                         │        (Django, port 8420, LAN)          │
                         │    status · logs · restart · queue ops   │
                         └────────────┬─────────────────────────────┘
                                      │ talks to everything
                                      ▼
┌──────────┐   indexes   ┌──────────────────────────────┐   serves   ┌──────┐
│ Prowlarr │────────────▶│       Radarr  +  Sonarr      │───────────▶│ Plex │
│  :9696   │             │    :7878/:7879  :8989/:8990  │            │ host │
└──────────┘             └──────────┬───────────────────┘            └──┬───┘
                                    │ grab NZBs                        │
                                    ▼                                  │
                         ┌────────────────────┐                        │
                         │      nzbdav        │  WebDAV + SAB-API     │
                         │  InfiniDysk :3000  │◄──────────────────────┘
                         └────────┬───────────┘   symlink imports
                                  │
                                  ▼
                         ┌────────────────────┐
                         │   nzbdav_rclone    │  rclone FUSE mount
                         │  /mnt/remote/nzbdav│  streamed on demand
                         └────────┬───────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
              ./media/movies  ./media/shows  ./media/anime-*
              (100% symlinks, zero real files on local disk)
```

**Every media file is a symlink into the FUSE mount.** Radarr/Sonarr's `copyUsingHardlinks: true` produces another symlink, never a byte copy. The only thing on local disk is metadata databases and config.

---

## Quick Start

```bash
mkdir -p ~/Stack && cd ~/Stack

# 1. Scaffold files onto a fresh host (no git clone needed)
docker run --rm -v "$(pwd)":/out ghcr.io/whispersofj/media-stack:latest

# 2. (Optional) Fill in .env via a browser wizard
docker run --rm -p 8090:8090 -v "$(pwd)":/out ghcr.io/whispersofj/media-stack:latest --setup

# 3. Bring everything up
cp .env.example .env && $EDITOR .env   # fill in your keys
docker compose up -d
```

**Post-boot:** collect `RADARR_API_KEY`, `SONARR_API_KEY` (Settings → General → Security in each app), and `PLEX_TOKEN` (via `plex.tv/claim`). Enter them in `.env`, then `docker compose up -d --force-recreate control-panel`.

---

## Services

| # | Service | Purpose | Port |
|---|---------|---------|------|
| 1 | `prowlarr` | Usenet indexer management | 9696 |
| 2 | `radarr` | Movie library manager | 7878 |
| 3 | `sonarr` | TV library manager | 8989 |
| 4 | `radarr-anime` | Anime movie library (separate instance) | 7879 |
| 5 | `sonarr-anime` | Anime TV library (separate instance) | 8990 |
| 6 | `nzbdav` | Usenet downloader (WebDAV + SAB-API) | 3000 |
| 7 | `nzbdav_rclone` | FUSE mount sidecar — streams content on demand | — |
| 8 | `seerr` | User-facing request frontend | 5055 |
| 9 | `plex` | Media server (host networking) | 32400 |
| 10 | `bazarr` | Subtitle downloader | 6767 |
| 11 | `control-panel` | Custom Django dashboard | 8420 |
| 12 | `unpackerr` | Auto-extracts RAR'd releases | — |
| 13 | `watchtower` | Auto-updates channel-tag images (4am daily) | — |
| 14 | `cleanuparr` | Strike/malware/stalled-download cleanup | 11011 |
| 15 | `kometa` | Plex collections/overlays automation | — |
| 16 | `ntfy` | Push notification sink | 8700 |
| 17 | `speedtest-tracker` | Hourly ISP speed monitoring | 8701 |
| 18 | `organizr` | Single-pane frontend | 8702 |
| 19 | `scrutiny` | SMART disk health monitoring | 8703 |
| 20 | `watchstate` | Cross-server watch-state sync | 8705 |
| — | `loki` + `promtail` | Log aggregation (internal) | 3100 |
| — | `grafana` | Logs dashboard | 3001 |
| — | `prometheus` + `node-exporter` + `cadvisor` | Host/container metrics | 9090 |
| — | `nzbdav-exporter` | NzbDAV config/queue metrics | 1011 |
| — | `metacache` | Metadata cache proxy for Plex | 8765 |

---

## CLI Reference

133 fish functions, all prefixed `stack-`. Every read-only command was live-verified 2026-08-25.

### Status & Health

```fish
stack-status                      # live health of every container
stack-top                         # CPU/mem per container
stack-resource-check              # containers missing memory/CPU limits
stack-image-check                 # stale images, update-available tags
stack-mount-health                # FUSE mount status
stack-mem-pressure                # system memory pressure
stack-oom-check                   # recent OOM kills
stack-zombie-check                # zombie processes
stack-firewall-status             # iptables/nftables summary
stack-kernel-check                # kernel version + known CVEs
stack-reboot-check                # pending reboot after kernel update
```

### *Arr Apps

```fish
stack-arr radarr rss-sync         # trigger RSS sync (radarr or sonarr)
stack-arr sonarr search-missing   # trigger missing-episode search
stack-arr radarr unstick          # remove + blocklist + re-search stuck items
stack-arr-backlog                 # items queued across all *arr apps
stack-arr-blocklist               # blocklist entries per app
stack-arr-clear-blocklist radarr  # clear all blocklist entries
stack-arr-import radarr 0         # manual import candidate #0
stack-arr-import-candidates       # list files ready to import
stack-arr-import-all              # bulk-import everything
stack-arr-import-backlog          # size of each app's import queue
stack-arr-import-starvation       # downloads waiting with no import activity
stack-arr-logs radarr             # recent logs for an app
stack-arr-missing-aired           # monitored + already-aired, no file yet
stack-arr-queue-errors            # queue items in warning/error state
stack-arr-recently-added          # most recent imports
stack-arr-toggle-search radarr    # toggle full-library search on/off
```

### Plex

```fish
stack-plex-libraries              # library names + keys
stack-plex-sessions               # who's watching right now
stack-plex-recently-added         # newest items
stack-plex-duplicates             # suspected duplicate releases
stack-plex-scan                   # trigger library scan
stack-plex-empty-trash            # empty trash for all libraries
stack-plex-optimize-db            # optimize Plex database
stack-plex-refresh-libraries      # refresh all library metadata
stack-plex-analyze                # queue deep media analysis
stack-plex-backup-database        # backup Plex database
stack-plex-updates                # check for PMS updates
```

### NzbDAV (Usenet)

```fish
stack-nzbdav-queue                # current download queue
stack-nzbdav-history              # recent history (completed/failed)
stack-nzbdav-stats                # aggregate queue + history stats
stack-nzbdav-delete-failures      # bulk-clear failed history
stack-nzbdav-dedup-check          # verify dedup config is safe
```

### System & Maintenance

```fish
stack-restart-all -y              # whole-stack restart (mount-order aware)
stack-container restart radarr    # restart a single container
stack-disk-free                   # disk usage per mountpoint
stack-disk-health                 # SMART status for all drives
stack-disk-config-sizes           # config directory sizes
stack-docker-disk-usage           # Docker image/volume/container usage
stack-pkg-updates                 # pending ArchLinux package updates
stack-flatpak-updates             # pending Flatpak updates
stack-aur-audit                   # audit AUR packages
stack-journal-errors              # systemd journal errors
stack-journal-size                # journal disk usage
stack-cron-list                   # active cron jobs
stack-uptime-report               # system uptime
stack-version                     # media-stack version + git info
stack-help                        # full command list
```

### Import Lists & Metadata

```fish
stack-import-lists                # all import lists across all apps
stack-customformat-diff           # custom format diffs between apps
stack-cutoff-unmet                # items below quality cutoff
stack-loop-candidates radarr      # titles with repeated download failures
stack-loop-unmonitor radarr 123   # unmonitor a loop candidate
stack-loop-exclude radarr 456     # add to Radarr Exclusions list
stack-queue-autofix               # blocklist + re-search stuck queue items
stack-sonarr-fix-episode-monitoring  # fix unmonitored episodes
stack-radarr-import-list          # trigger import list sync
```

### External Integrations

```fish
stack-letterboxd-radarr-list      # list Letterboxd lists
stack-letterboxd-radarr-tracked   # tracked Letterboxd lists
stack-letterboxd-radarr-watchlist # watchlist status
stack-mdblist-radarr-tracked      # tracked MDBList lists
stack-rating-imdb tt1234567       # IMDb rating lookup
stack-rating-mdblist 12345        # MDBList rating lookup
stack-watchstate-status           # WatchState sync status
stack-watchstate-history          # recent WatchState sync history
stack-watchstate-import-now       # trigger WatchState import
stack-tmdb-import-company 420     # import a TMDb company
stack-tmdb-missing                # items missing TMDb links
```

---

## Control Panel

**Port 8420** — Django + htmx dashboard. Amber/green CRT theme. Live container status, one-click ops, per-app queue tools, poster sync, SSE log streaming.

### Key API Endpoints

```bash
# Container health grid
curl -s http://192.168.4.20:8420/api/v2/host/status | jq .

# Live container stats (CPU, RAM, state)
curl -s http://192.168.4.20:8420/api/v2/host/containers | jq .

# Per-app operations
curl -X POST http://192.168.4.20:8420/api/v2/arr/radarr/rss-sync
curl -X POST http://192.168.4.20:8420/api/v2/arr/sonarr/search-missing

# NzbDAV queue + history
curl -s http://192.168.4.20:8420/api/v2/nzbdav/queue | jq .
curl -s http://192.168.4.20:8420/api/v2/nzbdav/stats | jq .

# Whole-stack restart (mount-order aware)
curl -X POST http://192.168.4.20:8420/api/v2/host/restart-all
```

Full API reference: see the Control Panel section of the [detailed docs](STACK.md).

---

## Monitoring Stack

```
Prometheus :9090 ──scrapes──▶ node-exporter  (host CPU/RAM/disk)
                              cadvisor       (per-container metrics)
                              nzbdav-exporter (NzbDAV queue/config)
                              metacache      (cache hit rates)

Loki :3100 ◀──promtail── syslog + Docker logs
Grafana :3001 ──queries──▶ Prometheus + Loki
```

- **Grafana** at `http://192.168.4.20:3001` — logs overview + import pipeline dashboards
- **Prometheus** at `http://192.168.4.20:9090` — metrics scraping, alerting rules
- **Scrutiny** at `http://192.168.4.20:8703` — SMART disk health
- **Speedtest Tracker** at `http://192.168.4.20:8701` — hourly ISP speed/latency

---

## CI/CD

| Workflow | What it does |
|----------|-------------|
| **Validate Compose** | shellcheck, ruff, compose validation, variable consistency, 291 script/fish tests, 822 Django tests, installer build |
| **Release Please** | Automated releases via conventional commits |
| **Trivy Scan** | Nightly CVE scan of all images (Docker, Prometheus, Grafana) |
| **Publish Installer** | Builds and pushes the `ghcr.io/whispersofj/media-stack` installer image |

---

## Repo Stats

```
21 Docker Compose services         133 fish CLI functions
 5 CI workflows                    822 Django tests
53 bugs fixed (last 200 commits)    66 features shipped
```

### Recent Commits

<!-- recent commits inserted here by CI -->

---

## Directory Layout

```
Stack/
├── docker-compose.yml          # single compose file, every image pinned
├── .env                        # secrets (gitignored)
├── README.md                   # this file
├── STACK.md                    # detailed reference: gotchas, incidents, playbooks
├── PLANS.md                    # implementation plans and specs
├── BUG-SMASHED.md              # historical bug graph — every bug found and fixed
├── MEMORY.md                   # agent session memory
├── config/<app>/               # each app's persistent config (gitignored)
├── control-panel-django/       # custom Django dashboard, 30+ Django apps
├── fish-functions/             # 133 stack-* CLI commands
├── scripts/                    # backup/alert/setup automation
├── systemd/                    # user-scope units for boot automation
├── monitoring/                 # Prometheus alerting rules
└── media/                      # writable root folders, 100% symlinks
    ├── movies/                 # Radarr root
    ├── shows/                  # Sonarr root
    ├── anime-movies/           # radarr-anime root
    └── anime-shows/            # sonarr-anime root
```

---

## Key Design Decisions

- **Usenet-only.** Torrent/debrid (Zurg, Decypharr, rclone-alldebrid, Zilean, Byparr) was removed entirely in v11.0.0 after the Usenet migration proved reliable.
- **Zero local media files.** nzbdav streams downloads via WebDAV, `nzbdav_rclone` FUSE-mounts the result, and the `*arr` apps symlink-import. Nothing is ever written to local disk.
- **Headless config.** Every service is configured via environment variables, not manual Settings-UI clicks. NzbDAV's providers, arr instances, WebDAV creds, and import strategy are all `NZBDAV_CONFIG__*` env vars.
- **Mount-order aware restarts.** The FUSE mount cascade (nzbdav → nzbdav_rclone → dependents) is sequenced in the Control Panel's restart-all endpoint. Never restart `nzbdav_rclone` alone.
- **Plex on host networking.** GDM auto-discovery, DLNA, and remote-access NAT-PMP/UPnP are unreliable on bridge networking. Every other service uses `stacknet`.
- **No login gate.** Every web UI publishes directly to the LAN. A Traefik + Authelia + CrowdSec auth layer was built, verified, and reverted. POST/PUT/DELETE endpoints validate Origin/Host headers as a CSRF guard, not an auth layer.
- **Image pinning.** Channel-tag images (hotio `:release`) auto-update via Watchtower. Digest-pinned images (Seerr, Unpackerr) are immutable. Plex is manually version-pinned and excluded from auto-update.

---

## Screenshots

### Control Panel Dashboard

The Control Panel (`http://<host-ip>:8420`) is a Django + htmx dashboard with an amber/green CRT theme. Navigation rails on the left, quick-action buttons at the top, live container status, and a permanently pinned log console.

![Control Panel Dashboard](docs/images/dashboard-snapshot.html)

> **Live dashboard:** visit `http://192.168.4.20:8420` (login: admin/changeme) to see the real thing with live data, sparklines, and SSE log streaming.

### Setup Wizard

The installer wizard (`--setup` flag) renders a browser form from `.env.example`'s sections and comments:

![Setup Wizard](docs/images/setup-wizard-form.png)

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [STACK.md](STACK.md) | Quick-reference index with links to focused docs |
| [docs/architecture.md](docs/architecture.md) | Service inventory, commands, architecture facts, design decisions |
| [docs/landmines.md](docs/landmines.md) | Active issues that affect operations today |
| [docs/incidents.md](docs/incidents.md) | Chronological record of incidents, migrations, breaking changes |
| [docs/playbooks.md](docs/playbooks.md) | Workflow playbooks, operational gotchas, backup/DR notes |
| [BUG-SMASHED.md](BUG-SMASHED.md) | Historical bug graph — every bug found and fixed |
| [PLANS.md](PLANS.md) | Implementation plans for pending and completed feature phases |
| [MEMORY.md](MEMORY.md) | Agent session memory — cross-session state for AI coding agents |
| [CLAUDE.md](CLAUDE.md) | Rules and commands for Claude Code sessions |
| [AGENTS.md](AGENTS.md) | Agent workflow rules |

---

## License

MIT