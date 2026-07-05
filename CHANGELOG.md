# Changelog

**This entire stack was designed, built, debugged, and documented by [Claude AI](https://www.anthropic.com/claude)** — every service added, every bug found and fixed, every line below, was Claude's work. Built with Claude AI. 🤖

All notable changes to this project are documented here, versioned as if each exchange with
Claude were a release: **MAJOR** for breaking/foundational changes, **MINOR** for new
features, **PATCH** for fixes. Current version: **v2.0.1**.

---

## [2.0.1] — Cleanup

### Fixed
- Removed the old Postgres 16 data directory (`config/zilean-postgres.pg16.bak`, 1.1GB) after
  confirming the v18 rebuild was healthy — verified no errors, API responding, Lucene matcher
  actively rebuilding the cache before deleting.

*Built with Claude AI.*

## [2.0.0] — Recyclarr v8 and Postgres 18 (breaking changes, migrated in full)

### Changed — BREAKING
- **Recyclarr 7 → 8.** Read the upgrade guide *before* merging anything: v8 removes the
  `include: template:` mechanism entirely, which our config relied on — merging the raw
  version bump would have broken the nightly sync outright. Rewrote `recyclarr.yml` to the
  new guide-backed `quality_profiles: trash_id` format, pulling the exact trash IDs from
  TRaSH-Guides' own source rather than guessing. Verified clean adoption with zero duplicate
  profiles (same 7 profiles, same IDs, before and after, in both apps).
- **Postgres 16 → 18.** A straight image swap would have refused to start regardless — major
  Postgres versions use incompatible on-disk formats. Did a wipe-and-rebuild instead (safe
  here since Zilean's DB is just an hourly-regenerated cache), moving the old data aside
  rather than deleting it. Hit a second, unrelated issue along the way: Postgres 18's image
  changed its expected volume mount path entirely, confirmed against the real upstream
  Dockerfile before fixing the compose mount.

### Fixed
- **The actual root cause** of the custom-format-score-reset problem from v1.15.1: v8's
  `reset_unmatched_scores` is an explicit opt-in (default: leave scores alone), replacing
  v7's implicit always-on reset. Verified by syncing twice and watching the score hold at
  -10000 both times with zero intervention. Removed the old workaround script and its cron
  job entirely — patched-around problem, now actually fixed.

*Two Dependabot PRs opened this version — both closed as superseded once verified that
merging either raw diff alone would have broken something. Built with Claude AI.*

## [1.17.2] — Dependabot PR review

### Investigated
- Reviewed both open Dependabot PRs before merging either. Confirmed via Recyclarr's own
  upgrade guide and Postgres's fundamental on-disk format incompatibility that neither was a
  safe drop-in — see v2.0.0 for the actual migration.

## [1.17.1] — Dependabot config fix

### Fixed
- `package-ecosystem: "docker"` only scans for Dockerfiles/Kubernetes YAML, not Compose
  files — confirmed via the actual failed run logs, not just re-reading the docs. Corrected
  to the separate `docker-compose` identifier.

## [1.17.0] — Continuous integration

### Added
- `.github/workflows/validate.yml` — validates `docker compose config` on every push/PR.
- `.github/dependabot.yml` — weekly checks for newer image versions on anything pinned to a
  real tag rather than `:latest`.

## [1.16.0] — Passwordless sudo

### Added
- `/etc/sudoers.d/bear-nopasswd`, validated with `visudo -c`. Resolves the manual `sudo`
  hand-off friction from v1.0.0's Decypharr mountpoint fix — future host-level fixes no
  longer need a manual pause.

## [1.15.1] — Custom format score persistence (patched, later root-caused in v2.0.0)

### Fixed
- Discovered Recyclarr v7 silently resets any score it doesn't recognize back to 0, but only
  on the one profile it manages per app — confirmed empirically by running a real sync, not
  just reading docs. Added a cron-scheduled script to re-assert the intended score after
  every Recyclarr sync. (Superseded and removed in v2.0.0 once the actual root cause was
  fixed instead.)

## [1.15.0] — Quality gate: low-quality sources blocked

### Added
- Custom format matching known low-trust aggregator/group release names, scored -10000 in
  every quality profile in both Radarr and Sonarr — a hard reject, not just
  deprioritization.

## [1.14.0] — Prowlarr ↔ *arr app sync

### Added
- Connected all 5 *arr apps to Prowlarr under Settings → Apps with `fullSync`, so indexers
  now propagate down automatically. Confirmed complete by polling until indexer counts held
  steady with zero further log activity — genuinely rate-limited by design (60 req/min caps
  on several trackers), not stuck.

## [1.13.0] — Homepage documentation links

### Added
- Bookmarks linking to the GitHub-hosted, rendered README and CHANGELOG.

## [1.12.0] — Published to GitHub

### Added
- Converted to a git repo, `.gitignore` keeping every secret and stateful config file out of
  history, `.env.example` as a sanitized template. Pushed to a private repo under
  `WhispersOfJ/media-stack`.

## [1.11.2] — Seerr/Whisparr compatibility check

### Investigated
- Confirmed Seerr's settings API only recognizes `radarr` and `sonarr` — no adult-content
  data model exists to connect Whisparr to. Left standalone by design, not oversight.

## [1.11.1] — Seerr/Sonarr fix

### Fixed
- Seerr's Sonarr endpoint required `enableSeasonFolders`, undocumented until the first
  attempt failed. Added it, succeeded on retry.

## [1.11.0] — Seerr connected to Plex and the *arr apps

### Added
- Signed in to Plex using the token already on this host rather than the interactive OAuth
  flow, so it turned out scriptable after all. Connected Radarr and Sonarr as default
  servers.

## [1.10.0] — Zilean hardware tuning

### Added
- Tuned Zilean and its Postgres database for this host's actual 16-thread CPU and NVMe
  rather than defaults sized for a machine with a few hundred MB of RAM — Server GC, Lucene
  matching across 12 threads, Postgres `shared_buffers`/`work_mem`/parallelism sized up.
  Deliberately not maxed out — this is a shared desktop, not a dedicated server.

## [1.9.1] — NZBGet category fix

### Fixed
- NZBGet rejects any download-client category that doesn't already exist server-side, unlike
  Decypharr's more permissive API. Created the missing categories directly in `nzbget.conf`.

## [1.9.0] — NZBGet fallback download client

### Added
- Wired up as a lower-priority (2, behind Decypharr's 1) fallback download client across all
  5 apps, and separately as Prowlarr's own global client.

## [1.8.0] — Root folders

### Added
- Set in all 5 arr apps, pointed at their matching Zurg path. Lidarr/Readarr's older API
  needed extra metadata/quality profile fields Radarr/Sonarr/Whisparr didn't.

## [1.7.0] — Decypharr download client everywhere

### Added
- Added as a qBittorrent-compatible download client in all 5 arr apps. Confirmed
  auto-detection via Decypharr's own API — no manual config editing needed.

## [1.6.0] — Prowlarr indexers populated

### Added
- Bulk-added all 88 public-privacy indexer definitions Prowlarr ships with, plus Zilean as a
  Torznab indexer. 70 live in the end; the rest were genuinely unreachable, not a config
  error.

## [1.5.0] — Documentation format changes

### Changed
- Converted docs to HTML, then back to Markdown per a later request. Content carried over in
  full either way.

## [1.4.1] — Recyclarr image tag fix

### Fixed
- `:latest` is explicitly called out in Recyclarr's own README as no longer published.
  Repinned to `:7`.

## [1.4.0] — Recyclarr and TRaSH Guides

### Added
- TRaSH-Guides quality profiles synced into Radarr and Sonarr automatically, once a day.

## [1.3.0] — Homepage dashboard

### Added
- Every service linked, grouped by category, plus a Debrid Media Manager bookmark.

## [1.2.0] — Full stack online

### Added
- All 11 core containers plus all 7 optional `extras` containers confirmed healthy.

## [1.1.1] — Bring-up fixes

### Fixed
- Three issues hit bringing the stack online for the first time: a dead upstream image tag,
  a wrong API key pulled from the wrong source, and a FUSE mountpoint that didn't exist yet.
  None were guessed at — each was root-caused from actual error output before being fixed.

## [1.1.0] — Zurg extended

### Added
- New `music`/`books`/`adult` directory groups added to the **live**, already-running Zurg
  config — backed up first, restarted cleanly, confirmed via the new folders actually
  appearing.

## [1.0.0] — Initial release

### Added
- The whole stack, from nothing: Prowlarr, Zilean, Decypharr, Radarr, Sonarr, Lidarr,
  Readarr, Whisparr, NZBGet, Seerr, plus 7 optional extras. Every image reference verified
  against its live registry rather than trusted from memory — caught real wrong assumptions
  this way (LinuxServer doesn't publish Whisparr; Overseerr and Jellyseerr merged into one
  project; Decypharr's image kept its old project name).

---

**Designed and built end-to-end by [Claude AI](https://www.anthropic.com/claude).** Every
version above — every service, every integration, every bug caught and fixed — is Claude's
work, verified live against the running stack rather than assumed correct.
