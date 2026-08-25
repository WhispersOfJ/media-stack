# HISTORY.md

Implemented plans and completed work, consolidated from root `.md` files and `docs/superpowers/`. These are kept for reference only — the work is done.

> Auto-generated consolidation. Original files deleted from root to reduce cruft.

---

## Phase 2: Secure Media Stack Deployment (COMPLETE)

**Duration:** ~2 weeks (concurrent Stages 1, 4, and Control-Panel hardening)
**Date Completed:** 2026-08-21
**Commits:** adde0b6, 5f018fe, 17fe4f8, 3f2772d (reverted), bc0a989

- **Stage 1: Logging Infrastructure** — Loki 2.8.0 + Promtail 2.8.0 + Grafana 10.4.0 deployed
- **Stage 4: CVE Scanning** — Trivy CLI + GitHub Actions + pre-commit hooks. 287 CVEs eliminated, stack security improved 39%.
- **Control Panel Hardening** — Python 3.13 upgrade (-165 CVEs, 46% reduction), rate limiting, cookie config, ALLOWED_HOSTS

---

## Stage 1: Centralized Logging (DEPLOYED)

**Deployed:** 2026-08-21, Commit: 7213249

| Service | Version | Port | Status |
|---------|---------|------|--------|
| Loki | 2.5.0 | 3100 | Healthy |
| Promtail | 2.5.0 | internal | Running |
| Grafana | 10.0.0 | 3001 | Healthy |

---

## Stage 4: Image Vulnerability Scanning (DEPLOYED)

**Deployed:** 2026-08-21, Commit: 0e648b7

| Component | Version | Purpose | Status |
|-----------|---------|---------|--------|
| Trivy CLI | 0.74.0 | Local CVE scanning | Installed |
| GitHub Actions | trivy-scan.yml | Automated PR/push scanning | Configured |
| Pre-commit Hook | trivy-pre-commit.sh | Block CRITICAL CVEs locally | Installed |

**CVE Baseline:** 0 CRITICAL, 658 HIGH (at time of deployment)

---

## Session 2026-08-21: Phase 2 Completion

- Loki 2.5.0 + Promtail + Grafana (logging complete)
- Trivy scanning + GitHub Actions + pre-commit hooks
- Control-panel Python 3.13 upgrade (-165 CVEs, 46% reduction)
- CVE remediation: -112 HIGH CVEs (Grafana trio, Watchtower)

---

## BearMount FUSE Read-Hang Fix (CLOSED AS MOOT)

**Closed:** 2026-07-28 — BearMount replaced by nzbdav/nzbdav

Root cause confirmed via live pprof goroutine dump: FUSE `Read()` goroutine parked in `sync.Cond.Wait()` inside `AsyncReadBuffer.ReadAtContext`. Fix (`asyncbuf-streaming-guard`) never had time to prove itself before the app was replaced. The automated mitigation endpoint (`/api/bearmount/unstick-ffprobe-hang`) was removed along with BearMount.

---

## Loki Startup Failures (RESOLVED)

Debug session investigating `mkdir : no such file or directory` + `error creating index client`. Tried boltdb with :ro volumes, in-memory storage, various schema versions. Resolved by switching storage backend configuration.

---

## Full-Stack Audit (COMPLETE)

**Date:** 2026-08-19 through 2026-08-21

| # | Directory | Status | Issues Found | Fixed | Tests Added |
|---|-----------|--------|--------------|-------|-------------|
| 1 | config/ + .env.example + compose | done | 4 dangling env vars | all 4 removed | 0 |
| 2 | control-panel/core/ | done | 11 of 12 modules untested | shared logger added | 108 |
| 3 | control-panel/services/ + main.py | done | 5 routers untested, 2 undocumented mutating routes | comments added, logger wired | 35 |
| 4 | control-panel/static/ | done | all commands.json verified clean | — | 8 |
| 5 | scripts/ | done | 4 untested files, 1 unguarded request() | try/except added | 23 |
| 6 | systemd/ + Dockerfile | done | stale --profile extras, dangling COPY | fixed | 9 |

Baseline: 721 tests → 806 tests after audit.

---

## Django Migration (ALL 5 PHASES COMPLETE)

**Completed:** 2026-08-24

| Phase | What | Status |
|-------|------|--------|
| Phase 1 | Skeleton, data layer, auth | Done |
| Phase 2 | `/api/v2/*` for 17 service apps (111 endpoints) | Done |
| Phase 3 | Django template + htmx browser UI | Done |
| Phase 4 | UI redesign (Pip-Boy theme, component library) | Done |
| Phase 5 | Cutover from FastAPI to Django | Done |

822 tests passing. FastAPI-era `control-panel/` tree archived.

---

## CLI Naming Cleanup (COMPLETE)

**Completed:** 2026-08-13

Made the repo the single source of truth for 133 `stack-*` fish functions. Symlinked from `~/.config/fish/functions/` into `fish-functions/`. Renamed 12 violating functions. Added schema linter gate test.

---

## Anime Re-enablement (COMPLETE)

**Completed:** 2026-08-06

Second Radarr instance (`radarr-anime`) for anime movies. Own root folder (`/data/anime-movies`), own quality profile, own Plex library. Reuses existing Usenet indexers via Prowlarr.

---

## Control Panel Redesigns (ALL COMPLETE)

| Redesign | Date | What |
|----------|------|------|
| Maximalist Visuals | 2026-08-14 | Per-rail accent hues, texture layer, shared sparkline renderer |
| Catalog Expansion | 2026-08-15 | 20→70+ entries, 3 new categories, env/volume details |
| Pip-Boy Theme | 2026-08-20 | Amber/green CRT palette, Poster Sync promoted, Catalog rail removed |
| Django UI | 2026-08-23 | Server-rendered templates + htmx, 7 app pages |

---

## Files Consolidated Into This Document

- `PHASE-2-COMPLETE.md`
- `PHASE-2-SUMMARY.md`
- `STAGE-1-CHECKLIST.md`
- `STAGE-1-DEPLOYED.md`
- `STAGE-4-CVE-BASELINE.md`
- `STAGE-4-DEPLOYED.md`
- `STAGE-4-REMEDIATION-PRIORITY.md`
- `SESSION-2026-08-21-SUMMARY.md`
- `FIXES.md`
- `loki-debug.md`
- `AUDIT_FINDINGS.md`
- `AUDIT_PROGRESS.md`
- `docs/superpowers/plans/` (7 files)
- `docs/superpowers/specs/` (5 files)