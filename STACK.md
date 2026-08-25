# STACK.md

Quick-reference index for this media-stack repo. The detailed content has been split into focused documents:

| Document | What it covers |
|----------|---------------|
| [docs/architecture.md](docs/architecture.md) | Service inventory, commands, architecture facts, design decisions |
| [docs/landmines.md](docs/landmines.md) | Active issues that affect operations today |
| [docs/incidents.md](docs/incidents.md) | Chronological record of incidents, migrations, and breaking changes |
| [docs/playbooks.md](docs/playbooks.md) | Workflow playbooks, operational gotchas, backup/DR notes |
| [README.md](README.md) | User-facing documentation, quick start, CLI reference |

---

## Current State (read this first)

- **Media server**: Plex (host networking, VAAPI transcode)
- **Usenet client**: nzbdav/nzbdav (WebDAV + rclone FUSE sidecar)
- **Root folders**: 100% symlinks, zero real media files on local disk
- **Control Panel**: Django + htmx (port 8420), bearer token auth for host actions
- **Monitoring**: Prometheus + Grafana + Loki + node-exporter + cadvisor
- **CI**: Validate Compose (shellcheck, ruff, 822 Django tests, Trivy CVE scan)
- **Repo**: Public on GitHub (`WhispersOfJ/media-stack`), branch protection with `validate` required

## Key Landmines (quick reference)

1. **FUSE mount cascade**: nzbdav_rclone → radarr, sonarr, plex, unpackerr, cleanuparr. Never restart owner alone without restarting dependents.
2. **Plex scheduled scan only**: `FSEventLibraryUpdatesEnabled` disabled. 6h interval. Use `stack-plex-scan` for immediate scan.
3. **NZBDAV queue not persistent**: Confirm queue empty before touching container.
4. **Config holds secrets**: `config/<app>/` is gitignored, not reproducible, no automated backup.
5. **App removal must be exhaustive**: Compose block, config, env vars, Prowlarr sync, Cleanuparr row, Control Panel refs, fish functions, content-routing groups.

## Agent Instructions

See `CLAUDE.md` for short-sentence/verification rules. This file is pure reference material — read on demand per-section rather than loaded whole every turn.

> When in doubt about current app inventory, `docker compose ps` / `docker-compose.yml` itself is ground truth — this file's prose narrative has drifted stale multiple times across this repo's history and will likely do so again.