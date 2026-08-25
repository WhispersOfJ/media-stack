# Historical Incidents

Chronological record of incidents, migrations, and breaking changes. Each entry is self-contained — read the one relevant to the subsystem you're touching.

> Dates are committer dates. "Removed" means fully deleted (compose block, config, env vars, references). "Reverted" means the change was undone and the prior state restored.

---

## 2026-07-22: Jellyfin Migration and Reversion (same day)

**Plex replaced by Jellyfin, then fully reverted back to Plex the same day** after repeated unresolved library-scan hangs tied to the NzbDAV connection-leak bug.

- Jellyfin (`lscr.io/linuxserver/jellyfin:latest`) deployed with two libraries (Movies, Shows) matching Plex's final state
- **Deployed without `/mnt/nzbdav` mount** — scan completed with no error, matched 418 shows, added zero episodes (every file was a symlink into a non-existent path inside the container)
- Plugins installed before revert: Playback Reporting, Chapter Segments, TMDb Box Sets, Intro Skipper
- **Kometa never supported Jellyfin** — blog sources claiming otherwise were wrong; it's an unimplemented feature request
- Jellyfin, Jellystat, jellystat-db all removed in the reversion
- Plex config (`config/plex/`, 34GB including all watch history) was deleted with no archive during the migration — current Plex is a fresh install
- Watch history was never migrated (neither to Jellyfin nor back)

---

## 2026-07-22: NzbDAV Connection Leak

**Root cause of the Jellyfin hangs and recurring library-scan failures.**

- `UsenetStreamingClient.CreateNewConnection` never disposed a connection on auth failure
- Circuit breaker didn't enforce its documented single-probe limit
- Drove real accounts into provider-side rejection
- Filed upstream: nzbdav-dev/nzbdav#477 (leak), PR #478 (fix from fork) — never merged
- **Resolution**: switched to AltMount (2026-07-23), then BearMount (2026-07-24), then nzbdav/nzbdav superfork (2026-07-28) which had both bugs fixed with dedicated test coverage

---

## 2026-07-23: AltMount Replaced by BearMount

AltMount (`ghcr.io/javi11/altmount`) replaced by its rebrand/fork BearMount (`ghcr.io/whispersofj/bearmount`). Same codebase lineage, different name.

- Two upstream AltMount security issues filed (#796 unauthenticated SSRF, #997 unenforced IsAdmin) — moot once neither codebase was in use
- BearMount owned its mount directly (no separate rclone sidecar), unlike nzbdav

---

## 2026-07-23: Local Media Eliminated

AltMount switched to `SYMLINK` import strategy. Every root folder enforced back to 100% symlinks with zero real media files on local disk.

---

## 2026-07-23: API Keys Rotated

All four rotatable API keys (Radarr, Sonarr, Prowlarr, NzbDAV) rotated after one was found hardcoded in `.claude/settings.local.json`.

Key finding: Radarr/Sonarr's `apiKey` field in config API silently ignores changes — the actual key lives in `config/<app>/config.xml` and only takes effect after container restart.

---

## 2026-07-24: NeutArr Removed

Removed after its missing-content hunting built up large grab backlogs causing:
1. Self-sustaining blocklist-then-research loop in BearMount's queue cleanup
2. Plex SQLite lock-contention stall from the resulting import burst

No automated missing-content/quality-upgrade hunting remains in the stack.

---

## 2026-07-24: Sportarr Removed

Added and removed within 24 hours. Plex metadata integration was structurally broken.

---

## 2026-07-25: BearMount FUSE Read Hangs

Recurring D-state hangs during import-time ffprobe, specific to BearMount's Go FUSE implementation. Not observed in nzbdav_rclone's stock rclone.

Recovery procedure (rehearsed multiple times):
1. Drain queue check
2. FUSE abort
3. Host mountpoint `transport endpoint is not connected` cleared with `sudo umount -l /mnt/bearmount`
4. BearMount recreated and content-verified
5. Five dependents restarted

---

## 2026-07-25: stop_grace_period Root Cause

**The answer to "why does this stack need restarting multiple times an hour."**

1. BearMount's graceful shutdown legitimately takes ~40s (10s subprocess-reap race + 30s HTTP server shutdown deadline), but Docker's default 10s SIGKILL fired mid-sequence on every restart
2. A real, actively-growing host-level mount-table leak from `rshared` propagation
3. `max_processor_workers` drifted back to 2 (previously pinned to 1 after OOM near-miss)

Fixed: `stop_grace_period: 90s`, narrow `/mnt/bearmount` bind instead of broad `/mnt:/mnt:rshared`.

---

## 2026-07-28: BearMount Replaced by nzbdav/nzbdav

Different codebase despite the name reuse — WebDAV-only, no native FUSE mount, hence separate `nzbdav_rclone` sidecar.

Verified the superfork actually fixed both root-cause bugs:
- `UsenetStreamingClient.CreateNewConnection` wraps connect+auth in try/catch with dispose
- `ProviderCircuitBreaker` has real `Interlocked.CompareExchange`-based single-probe gate
- Both fixes have dedicated test coverage (`ProviderCircuitBreakerHalfOpenTests`, `ConnectionPoolIdleTimeoutTests`)

---

## 2026-07-31: Quality Profile Consolidation

Both Radarr and Sonarr consolidated to a single profile named `Anything` (all qualities allowed, `upgradeAllowed: false`). Recyclarr removed entirely a second time.

Fourteen custom formats carry `-10000` reject scores (AV1, BR-DISK, Bad Dual Groups, LQ, Upscaled, x265 HD, etc.).

---

## 2026-08-01: NzbDAV Dedup Bug

The `(2)`-suffix importBlocked bug — real root cause of most `importBlocked` loops. Fixed by setting `api.duplicate-nzb-behavior` to `mark-failed`.

---

## 2026-08-02: Radarr Import Lists Re-monitor Bug

Import lists silently re-monitor manually-unmonitored movies. The loop remediation toolkit was added to the Control Panel to counteract this.

---

## 2026-08-03: Pi-hole Added and Removed Same Day

Network-wide DNS added as Pi-hole, removed same day.

---

## 2026-08-06: Anime Support Removed Entirely

122 Radarr movies + 159 Sonarr series removed by explicit request. Touched: both libraries (`deleteFiles=true`), both Plex libraries, both root folders, quality profiles, 33 custom formats, Zurg routing groups, rclone-alldebrid-anime, Kometa blocks, Prowlarr indexers.

---

## 2026-08-12: New Services Batch (Phases 1-7)

Added: ntfy, Speedtest Tracker, Organizr, Scrutiny, WatchState. GAPS-2 added then scope-cut to Movies/Shows only. PlexAniSync added then decommissioned.

---

## 2026-08-12: Restic Removed Entirely

Total removal — code, scripts, systemd units, control-panel wiring, and repo data (453GB local + offsite Dropbox). No automated backup mechanism remains. `scripts/arr-app-backup.py` (Radarr/Sonarr native Backup) untouched.

---

## 2026-08-20: Awesome-ARR Companions Decommissioned

Tautulli, Wrapperr, Maintainerr, Lingarr, Prefetcharr all removed. None remain.

---

## 2026-08-24: Django Migration Complete

Control panel backend migrated from FastAPI to Django REST Framework. All 5 phases complete. 822 tests passing. FastAPI-era `control-panel/` tree archived.

---

## 2026-08-25: Fish Function API Path Remediation

21 fish functions still called dead FastAPI `/api/*` paths after Django migration. 2 nzbdav functions expected bare array, API returns `{ok, message, items}`. All 23 fixed. Stale `HOST_IP` in `.env` corrected.