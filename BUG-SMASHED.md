# BUG-SMASHED.md

> **Every bug found and fixed in this repo, chronologically organized by subsystem.**
> 76 fixes in the last 300 commits. This document is the historical record — the graveyard of smashed bugs.

---

## Bug Timeline Graph

```
2026-08 (August 2026): ████████████████████████████████████████ 76 bugs
```

## Bug Details by Month

### August 2026 (76 bugs)

| Date | Hash | Subsystem | Severity | Description |
|------|------|-----------|----------|-------------|
| 2026-08-05 | `4b37554` | Usenet Pipeline, Control Panel — Backend, Control Panel — Frontend, Django Migration | Low | fix(control-panel): add login UI and static-file mount for evolved backend |
| 2026-08-06 | `b5bf585` | Control Panel — Backend | Low | wire cleanuparr and seerr routers into main.py |
| 2026-08-06 | `e8fae06` | Fish Functions | Low | send X-Api-Key from stack-* fish CLI commands |
| 2026-08-06 | `0eb7281` | Uncategorized | High | add missing RADARR_ANIME_API_KEY to cp_main_app test fixture |
| 2026-08-06 | `1437035` | Control Panel — Backend | Low | fix(control-panel): extend service-key auth to every fish-CLI-called route |
| 2026-08-06 | `d982fca` | Control Panel — Backend | Low | fix(control-panel): allow service-key auth on add-from-letterboxd-list |
| 2026-08-06 | `b13ce2d` | Uncategorized | Low | fix(request-manager-integrator): resolve real container hostname, not app_name |
| 2026-08-06 | `aa2f6a6` | Usenet Pipeline | Low | fix(docker-compose-manager): add radarr-anime to FUSE mount cascade dependents |
| 2026-08-06 | `de1405b` | Usenet Pipeline | Low | fix(nzbdav): add anime-movies to NZBDAV_CONFIG__API__CATEGORIES |
| 2026-08-06 | `c8aa4b5` | Control Panel — Frontend | Low | fix(trash-guides-applier): build real quality-profile items from schema, register radarr_anime |
| 2026-08-06 | `784a579` | Plex | Low | fix(kometa): switch to manual-only runs |
| 2026-08-07 | `de6133f` | Control Panel — Backend | High | repair drifted skill scripts and port 3 missing control-panel routes |
| 2026-08-07 | `1c8c853` | Uncategorized | High | fix(health-monitor): add 7 missing services to HTTP reachability check |
| 2026-08-07 | `7aa4e7e` | Monitoring Stack, CI/CD | Low | bump Pillow 11.3.0 -> 12.3.0, clears 18 open Dependabot alerts |
| 2026-08-07 | `d16b12b` | Control Panel — Backend | High | add missing Control Panel/radarr_anime vars to .env.example |
| 2026-08-07 | `eafa540` | Uncategorized | Low | treat radarr_anime as a Radarr-type app in queue/import/blocklist paths |
| 2026-08-09 | `7bd400b` | Usenet Pipeline | High | add missing tertiary nzbdav usenet vars to .env.example |
| 2026-08-09 | `172edfa` | Usenet Pipeline | Low | set all three nzbdav usenet providers to priority 0 |
| 2026-08-09 | `f2f433b` | Usenet Pipeline | Low | remove tertiary nzbdav usenet provider |
| 2026-08-09 | `553bde6` | Usenet Pipeline | Low | restore nzbdav usenet connections to 50 per provider |
| 2026-08-09 | `8feda56` | Usenet Pipeline | Low | lower nzbdav usenet connections to 25 per provider |
| 2026-08-11 | `d1b27b5` | Uncategorized | Low | remove thundernews, set newshosting primary and ninja as backup |
| 2026-08-13 | `d799609` | Plex, CI/CD | Low | reconcile against the Plex API, not deleted_at (corrects a false positive) |
| 2026-08-13 | `5d43a0f` | Usenet Pipeline | Low | self-heal stale FUSE mountpoint on nzbdav_rclone start |
| 2026-08-14 | `113d38c` | Control Panel — Frontend | Low | remove dead sparkline CSS rules, diverge rail-fleet/rail-catalog from status colors |
| 2026-08-14 | `d4e4ab0` | Plex, Control Panel — Frontend | Medium | diverge --rail-plex-health from --bad to avoid error-color collision |
| 2026-08-14 | `9c070b3` | Control Panel — Frontend | Low | restore RAM sparkline green color and fill styling |
| 2026-08-14 | `76a2f66` | Plex | Low | send the service API key from the Plex health watchdog |
| 2026-08-14 | `e070b54` | CI/CD | Low | green up Validate Compose and widen its lint/profile coverage |
| 2026-08-15 | `a02163a` | Usenet Pipeline | Low | declare FUSE-mount dependency chain, add rclone healthcheck |
| 2026-08-15 | `ff650a6` | Control Panel — Frontend | Low | catalog details panel display:flex overrode [hidden], never collapsed |
| 2026-08-19 | `dc27428` | CI/CD | Low | clear ruff lint errors blocking Validate Compose CI |
| 2026-08-19 | `10f545f` | Control Panel — Backend | Critical | isolate router-import failures instead of crashing all of boot |
| 2026-08-19 | `7eb9af6` | Uncategorized | Low | remove stale extras profile refs, fix dangling app.py COPY |
| 2026-08-19 | `10ce1d1` | Uncategorized | High | guard unhandled Cleanuparr seeker fetch, add 23 script tests |
| 2026-08-19 | `0df6ac1` | Control Panel — Backend | Low | log silent excepts, justify automation routes, add 35 router tests |
| 2026-08-19 | `922831c` | Uncategorized | Low | remove dangling env vars for services deleted in consolidation |
| 2026-08-19 | `c7fc6b8` | Uncategorized | Low | finalize Plan 3 consolidation — retire app.py, drop dead tests/fish for removed services |
| 2026-08-20 | `56840a0` | Control Panel — Backend, Control Panel — Frontend | Low | update control-panel unit tests for amber/green theme default |
| 2026-08-20 | `475c078` | Control Panel — Frontend | Low | address final-review findings (theme PATCH schema, dead CSS, fragile selector) |
| 2026-08-21 | `31db35a` | Uncategorized | Medium | correct MDBList response shape and IMDb N/A handling in ratings app |
| 2026-08-21 | `b7f2485` | Control Panel — Backend | Low | restore server-side error logging in ServiceError/envelope handler |
| 2026-08-21 | `76960b1` | Control Panel — Backend, Security | Critical | harden Phase 1 findings from final review — secret key, session fixation, DRF defaults, gitignore |
| 2026-08-21 | `40f5f6d` | Control Panel — Backend, Django Migration | Low | bump Django to 5.2.17 for Python 3.14 compatibility |
| 2026-08-21 | `3a1a7f6` | Uncategorized | Low | feat: add Task 2 & 3 automation (upstream monitoring + weekly CVE scans) |
| 2026-08-21 | `cb840a6` | Monitoring Stack | High | Discord webhook integration - remove broken alert-rules YAML |
| 2026-08-21 | `7f45a00` | CI/CD | Low | remove unused variables from trivy scripts (shellcheck SC2034) |
| 2026-08-21 | `538fed8` | Monitoring Stack | Medium | resolve port collision between Grafana (3001) and Uptime Kuma catalog entry |
| 2026-08-21 | `5db9724` | Monitoring Stack, Security | High | add missing Grafana admin credentials to .env.example |
| 2026-08-21 | `bc0a989` | Uncategorized | Low | revert distroless, keep Python 3.13-slim with shell-free healthcheck |
| 2026-08-21 | `0e648b7` | CI/CD | Low | feat: deploy Stage 4 (Trivy image CVE scanning + remediation plan) |
| 2026-08-22 | `4cc90d4` | Control Panel — Backend, CI/CD | Low | exercise real auth layer in watchstate import unauthenticated test |
| 2026-08-22 | `8124bbc` | Uncategorized | Low | add HTTP_HOST/REMOTE_ADDR to host_actions 403 tests |
| 2026-08-22 | `206b3b7` | Control Panel — Backend | High | cleanuparr missing-db raises 502 ServiceError, matching router.py |
| 2026-08-22 | `9020911` | Control Panel — Backend | Low | feat: add /api/v2/sonarr/monitor-episodes-fix |
| 2026-08-22 | `9195d73` | Control Panel — Backend | Low | VerifySameOriginMiddleware host check + pytest.ini testpaths |
| 2026-08-22 | `d559024` | Uncategorized | Low | Task 4 findings - idempotent exclusion + test fidelity |
| 2026-08-23 | `ba503b6` | Plex | Low | wrap Plex httpx errors in posters list_libraries/gallery |
| 2026-08-23 | `8340898` | CI/CD | Low | replace slack-github-action with plain curl in Trivy scan workflow |
| 2026-08-23 | `687b77b` | Control Panel — Backend, Security | Low | bump pytest for CVE-2025-71176, add rate-limit test, document secure cookie env var |
| 2026-08-23 | `67cb2f3` | Control Panel — Backend, Security | Low | add rate limiting to all destructive host-level endpoints |
| 2026-08-23 | `fcdd57c` | Control Panel — Backend, Security | Critical | harden security — rate limiting, cookie config, ALLOWED_HOSTS, Docker import fallback, privilege docs |
| 2026-08-24 | `61be38c` | Control Panel — Frontend, Security | Critical | adversarial review — XSS in toasts, SSE resource leak, reconnect race |
| 2026-08-24 | `1af83b1` | Control Panel — Frontend | Low | wire sparkline data binding so ApexCharts shows live CPU/RAM/queue history |
| 2026-08-24 | `60adf62` | Plex, Control Panel — Backend | Low | control panel can reach Plex via host.docker.internal |
| 2026-08-24 | `acced04` | Usenet Pipeline, Control Panel — Backend | Low | persist control-panel SQLite DB in mounted /data volume |
| 2026-08-24 | `0186e9d` | Control Panel — Backend, Django Migration | Low | Django control panel Dockerfile, healthcheck, and static file serving |
| 2026-08-24 | `0ec2800` | Control Panel — Frontend, Security | Critical | UI redesign bug fixes and security improvements |
| 2026-08-25 | `2795558` | Control Panel — Frontend, Django Migration, CI/CD | Low | add whitenoise to CI test requirements |
| 2026-08-25 | `2763d67` | Django Migration | Low | bump pytest-httpx for pytest 9 compatibility |
| 2026-08-25 | `7bdbeb9` | Uncategorized | Critical | contain stale-image crashes in list_containers and image_check |
| 2026-08-25 | `fa353b8` | Control Panel — Backend, Django Migration, Fish Functions | Low | repair fish function API paths after Django migration |
| 2026-08-25 | `953af74` | Monitoring Stack | Low | align Speedtest Tracker catalog port |
| 2026-08-25 | `a668252` | Uncategorized | Low | document Metacache compose variables |
| 2026-08-25 | `dfcbede` | Usenet Pipeline, Exporter | Low | adapt NzbDAV config metrics to current API |
| 2026-08-25 | `ba98cff` | Exporter | Low | harden exporter metrics and live log handling |

---

## By Subsystem

### CI/CD (9 bugs)

| Date | Hash | Severity | Description |
|------|------|----------|-------------|
| 2026-08-07 | `7aa4e7e` | Low | bump Pillow 11.3.0 -> 12.3.0, clears 18 open Dependabot alerts |
| 2026-08-13 | `d799609` | Low | reconcile against the Plex API, not deleted_at (corrects a false positive) |
| 2026-08-14 | `e070b54` | Low | green up Validate Compose and widen its lint/profile coverage |
| 2026-08-19 | `dc27428` | Low | clear ruff lint errors blocking Validate Compose CI |
| 2026-08-21 | `7f45a00` | Low | remove unused variables from trivy scripts (shellcheck SC2034) |
| 2026-08-21 | `0e648b7` | Low | feat: deploy Stage 4 (Trivy image CVE scanning + remediation plan) |
| 2026-08-22 | `4cc90d4` | Low | exercise real auth layer in watchstate import unauthenticated test |
| 2026-08-23 | `8340898` | Low | replace slack-github-action with plain curl in Trivy scan workflow |
| 2026-08-25 | `2795558` | Low | add whitenoise to CI test requirements |

### Control Panel — Backend (23 bugs)

| Date | Hash | Severity | Description |
|------|------|----------|-------------|
| 2026-08-05 | `4b37554` | Low | fix(control-panel): add login UI and static-file mount for evolved backend |
| 2026-08-06 | `b5bf585` | Low | wire cleanuparr and seerr routers into main.py |
| 2026-08-06 | `1437035` | Low | fix(control-panel): extend service-key auth to every fish-CLI-called route |
| 2026-08-06 | `d982fca` | Low | fix(control-panel): allow service-key auth on add-from-letterboxd-list |
| 2026-08-07 | `de6133f` | High | repair drifted skill scripts and port 3 missing control-panel routes |
| 2026-08-07 | `d16b12b` | High | add missing Control Panel/radarr_anime vars to .env.example |
| 2026-08-19 | `10f545f` | Critical | isolate router-import failures instead of crashing all of boot |
| 2026-08-19 | `0df6ac1` | Low | log silent excepts, justify automation routes, add 35 router tests |
| 2026-08-20 | `56840a0` | Low | update control-panel unit tests for amber/green theme default |
| 2026-08-21 | `b7f2485` | Low | restore server-side error logging in ServiceError/envelope handler |
| 2026-08-21 | `76960b1` | Critical | harden Phase 1 findings from final review — secret key, session fixation, DRF defaults, gitignore |
| 2026-08-21 | `40f5f6d` | Low | bump Django to 5.2.17 for Python 3.14 compatibility |
| 2026-08-22 | `4cc90d4` | Low | exercise real auth layer in watchstate import unauthenticated test |
| 2026-08-22 | `206b3b7` | High | cleanuparr missing-db raises 502 ServiceError, matching router.py |
| 2026-08-22 | `9020911` | Low | feat: add /api/v2/sonarr/monitor-episodes-fix |
| 2026-08-22 | `9195d73` | Low | VerifySameOriginMiddleware host check + pytest.ini testpaths |
| 2026-08-23 | `687b77b` | Low | bump pytest for CVE-2025-71176, add rate-limit test, document secure cookie env var |
| 2026-08-23 | `67cb2f3` | Low | add rate limiting to all destructive host-level endpoints |
| 2026-08-23 | `fcdd57c` | Critical | harden security — rate limiting, cookie config, ALLOWED_HOSTS, Docker import fallback, privilege docs |
| 2026-08-24 | `60adf62` | Low | control panel can reach Plex via host.docker.internal |
| 2026-08-24 | `acced04` | Low | persist control-panel SQLite DB in mounted /data volume |
| 2026-08-24 | `0186e9d` | Low | Django control panel Dockerfile, healthcheck, and static file serving |
| 2026-08-25 | `fa353b8` | Low | repair fish function API paths after Django migration |

### Control Panel — Frontend (12 bugs)

| Date | Hash | Severity | Description |
|------|------|----------|-------------|
| 2026-08-05 | `4b37554` | Low | fix(control-panel): add login UI and static-file mount for evolved backend |
| 2026-08-06 | `c8aa4b5` | Low | fix(trash-guides-applier): build real quality-profile items from schema, register radarr_anime |
| 2026-08-14 | `113d38c` | Low | remove dead sparkline CSS rules, diverge rail-fleet/rail-catalog from status colors |
| 2026-08-14 | `d4e4ab0` | Medium | diverge --rail-plex-health from --bad to avoid error-color collision |
| 2026-08-14 | `9c070b3` | Low | restore RAM sparkline green color and fill styling |
| 2026-08-15 | `ff650a6` | Low | catalog details panel display:flex overrode [hidden], never collapsed |
| 2026-08-20 | `56840a0` | Low | update control-panel unit tests for amber/green theme default |
| 2026-08-20 | `475c078` | Low | address final-review findings (theme PATCH schema, dead CSS, fragile selector) |
| 2026-08-24 | `61be38c` | Critical | adversarial review — XSS in toasts, SSE resource leak, reconnect race |
| 2026-08-24 | `1af83b1` | Low | wire sparkline data binding so ApexCharts shows live CPU/RAM/queue history |
| 2026-08-24 | `0ec2800` | Critical | UI redesign bug fixes and security improvements |
| 2026-08-25 | `2795558` | Low | add whitenoise to CI test requirements |

### Django Migration (6 bugs)

| Date | Hash | Severity | Description |
|------|------|----------|-------------|
| 2026-08-05 | `4b37554` | Low | fix(control-panel): add login UI and static-file mount for evolved backend |
| 2026-08-21 | `40f5f6d` | Low | bump Django to 5.2.17 for Python 3.14 compatibility |
| 2026-08-24 | `0186e9d` | Low | Django control panel Dockerfile, healthcheck, and static file serving |
| 2026-08-25 | `2795558` | Low | add whitenoise to CI test requirements |
| 2026-08-25 | `2763d67` | Low | bump pytest-httpx for pytest 9 compatibility |
| 2026-08-25 | `fa353b8` | Low | repair fish function API paths after Django migration |

### Exporter (2 bugs)

| Date | Hash | Severity | Description |
|------|------|----------|-------------|
| 2026-08-25 | `dfcbede` | Low | adapt NzbDAV config metrics to current API |
| 2026-08-25 | `ba98cff` | Low | harden exporter metrics and live log handling |

### Fish Functions (2 bugs)

| Date | Hash | Severity | Description |
|------|------|----------|-------------|
| 2026-08-06 | `e8fae06` | Low | send X-Api-Key from stack-* fish CLI commands |
| 2026-08-25 | `fa353b8` | Low | repair fish function API paths after Django migration |

### Monitoring Stack (5 bugs)

| Date | Hash | Severity | Description |
|------|------|----------|-------------|
| 2026-08-07 | `7aa4e7e` | Low | bump Pillow 11.3.0 -> 12.3.0, clears 18 open Dependabot alerts |
| 2026-08-21 | `cb840a6` | High | Discord webhook integration - remove broken alert-rules YAML |
| 2026-08-21 | `538fed8` | Medium | resolve port collision between Grafana (3001) and Uptime Kuma catalog entry |
| 2026-08-21 | `5db9724` | High | add missing Grafana admin credentials to .env.example |
| 2026-08-25 | `953af74` | Low | align Speedtest Tracker catalog port |

### Plex (6 bugs)

| Date | Hash | Severity | Description |
|------|------|----------|-------------|
| 2026-08-06 | `784a579` | Low | fix(kometa): switch to manual-only runs |
| 2026-08-13 | `d799609` | Low | reconcile against the Plex API, not deleted_at (corrects a false positive) |
| 2026-08-14 | `d4e4ab0` | Medium | diverge --rail-plex-health from --bad to avoid error-color collision |
| 2026-08-14 | `76a2f66` | Low | send the service API key from the Plex health watchdog |
| 2026-08-23 | `ba503b6` | Low | wrap Plex httpx errors in posters list_libraries/gallery |
| 2026-08-24 | `60adf62` | Low | control panel can reach Plex via host.docker.internal |

### Security (7 bugs)

| Date | Hash | Severity | Description |
|------|------|----------|-------------|
| 2026-08-21 | `76960b1` | Critical | harden Phase 1 findings from final review — secret key, session fixation, DRF defaults, gitignore |
| 2026-08-21 | `5db9724` | High | add missing Grafana admin credentials to .env.example |
| 2026-08-23 | `687b77b` | Low | bump pytest for CVE-2025-71176, add rate-limit test, document secure cookie env var |
| 2026-08-23 | `67cb2f3` | Low | add rate limiting to all destructive host-level endpoints |
| 2026-08-23 | `fcdd57c` | Critical | harden security — rate limiting, cookie config, ALLOWED_HOSTS, Docker import fallback, privilege docs |
| 2026-08-24 | `61be38c` | Critical | adversarial review — XSS in toasts, SSE resource leak, reconnect race |
| 2026-08-24 | `0ec2800` | Critical | UI redesign bug fixes and security improvements |

### Uncategorized (16 bugs)

| Date | Hash | Severity | Description |
|------|------|----------|-------------|
| 2026-08-06 | `0eb7281` | High | add missing RADARR_ANIME_API_KEY to cp_main_app test fixture |
| 2026-08-06 | `b13ce2d` | Low | fix(request-manager-integrator): resolve real container hostname, not app_name |
| 2026-08-07 | `1c8c853` | High | fix(health-monitor): add 7 missing services to HTTP reachability check |
| 2026-08-07 | `eafa540` | Low | treat radarr_anime as a Radarr-type app in queue/import/blocklist paths |
| 2026-08-11 | `d1b27b5` | Low | remove thundernews, set newshosting primary and ninja as backup |
| 2026-08-19 | `7eb9af6` | Low | remove stale extras profile refs, fix dangling app.py COPY |
| 2026-08-19 | `10ce1d1` | High | guard unhandled Cleanuparr seeker fetch, add 23 script tests |
| 2026-08-19 | `922831c` | Low | remove dangling env vars for services deleted in consolidation |
| 2026-08-19 | `c7fc6b8` | Low | finalize Plan 3 consolidation — retire app.py, drop dead tests/fish for removed services |
| 2026-08-21 | `31db35a` | Medium | correct MDBList response shape and IMDb N/A handling in ratings app |
| 2026-08-21 | `3a1a7f6` | Low | feat: add Task 2 & 3 automation (upstream monitoring + weekly CVE scans) |
| 2026-08-21 | `bc0a989` | Low | revert distroless, keep Python 3.13-slim with shell-free healthcheck |
| 2026-08-22 | `8124bbc` | Low | add HTTP_HOST/REMOTE_ADDR to host_actions 403 tests |
| 2026-08-22 | `d559024` | Low | Task 4 findings - idempotent exclusion + test fidelity |
| 2026-08-25 | `7bdbeb9` | Critical | contain stale-image crashes in list_containers and image_check |
| 2026-08-25 | `a668252` | Low | document Metacache compose variables |

### Usenet Pipeline (12 bugs)

| Date | Hash | Severity | Description |
|------|------|----------|-------------|
| 2026-08-05 | `4b37554` | Low | fix(control-panel): add login UI and static-file mount for evolved backend |
| 2026-08-06 | `aa2f6a6` | Low | fix(docker-compose-manager): add radarr-anime to FUSE mount cascade dependents |
| 2026-08-06 | `de1405b` | Low | fix(nzbdav): add anime-movies to NZBDAV_CONFIG__API__CATEGORIES |
| 2026-08-09 | `7bd400b` | High | add missing tertiary nzbdav usenet vars to .env.example |
| 2026-08-09 | `172edfa` | Low | set all three nzbdav usenet providers to priority 0 |
| 2026-08-09 | `f2f433b` | Low | remove tertiary nzbdav usenet provider |
| 2026-08-09 | `553bde6` | Low | restore nzbdav usenet connections to 50 per provider |
| 2026-08-09 | `8feda56` | Low | lower nzbdav usenet connections to 25 per provider |
| 2026-08-13 | `5d43a0f` | Low | self-heal stale FUSE mountpoint on nzbdav_rclone start |
| 2026-08-15 | `a02163a` | Low | declare FUSE-mount dependency chain, add rclone healthcheck |
| 2026-08-24 | `acced04` | Low | persist control-panel SQLite DB in mounted /data volume |
| 2026-08-25 | `dfcbede` | Low | adapt NzbDAV config metrics to current API |

---

## Severity Summary

| Level | Count | Meaning |
|-------|-------|---------|
| **Critical** | 6 | Data loss, security exposure, or complete service outage |
| **High** | 9 | Major feature broken, requires immediate fix |
| **Medium** | 3 | Degraded functionality, wrong behavior in edge cases |
| **Low** | 58 | Cosmetic, documentation, or minor inconvenience |

## Bug Density by Month

```
2026-08: ████████████████████████████████████████ 76 bugs
```

**Total: 76 bugs fixed across 300 commits.**

---

*Last updated: 2026-08-25. Auto-generated from `git log` by `scripts/generate-bug-graph.py`.*
