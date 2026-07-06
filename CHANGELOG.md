# Changelog

**This entire stack was designed, built, debugged, and documented by [Claude AI](https://www.anthropic.com/claude)** — every service added, every bug found and fixed, every line below, was Claude's work. Built with Claude AI. 🤖

All notable changes to this project are documented here, versioned as if each exchange with
Claude were a release: **MAJOR** for breaking/foundational changes, **MINOR** for new
features, **PATCH** for fixes. Current version: **v2.4.0**.

---

## [2.4.0] — Jellyfin + companion apps added, wired to every existing app, two live bugs found and fixed

### Added
- **Jellyfin** (`lscr.io/linuxserver/jellyfin`) as a second media server alongside the existing
  native Plex install. VAAPI hardware transcoding passed through from the host's AMD Radeon
  680M iGPU (`/dev/dri`, world-writable `renderD128`, no `group_add` needed) — confirmed via
  `System/Configuration/encoding` (`HardwareAccelerationType: vaapi`). Scripted through the
  entire startup wizard via its REST API (server name, admin account, remote access, a
  permanent API key for the other apps below) rather than the interactive UI. 5 libraries
  created against `/data/{movies,shows,music,books,adult}` — the same regular-disk root
  folders every arr app already writes into, not `/mnt/zurg`. Also enabled native
  hardware-accelerated trickplay generation (`TrickplayOptions.EnableHwAcceleration`).
- **Jellyseerr** — a second instance of the same `seerr` image, configured for a Jellyfin
  backend instead of Plex. Confirmed empirically (querying the existing Seerr's own
  `/api/v1/settings/public`) that **one Seerr instance is Plex or Jellyfin, never both at
  once** (`mediaServerType` is a single enum field) — this answers the question left open in
  the TODO about whether the existing `seerr` container could just grow a second backend; it
  can't, hence the second container. Signed in against Jellyfin
  (`POST /api/v1/auth/jellyfin` with `serverType: 2`), which both validated admin access and
  created Jellyseerr's own admin user in one step, then connected Radarr + Sonarr the same way
  the original Seerr was connected in [1.11.0].
- **Jellystat** (`cyfershepard/jellystat`) + its own Postgres database, following the same
  pattern as Zilean's dedicated DB. Connected to Jellyfin via its API key. Syncs on its own
  schedule (60 min partial / 24h full).
- **jfa-go** (`hrfee/jfa-go`) for Jellyfin user invites/account management, authenticated
  directly against the Jellyfin admin account. Password-reset watching pointed at the same
  `/config` volume Jellyfin itself uses (mounted read-only at `/jf`).
- Connected **Bazarr** to Jellyfin (it already supports multiple media servers natively — no
  new container). Selected the Movies + Adult libraries as Bazarr's movie scope and Shows as
  its series scope.
- Installed the 30-plugin curated shortlist from `JELLYFIN-PLUGINS.md` via Jellyfin's
  `/Repositories` and `/Packages/Installed` APIs (11 community repos registered, 31 packages
  installed in one pass). 30 came up `Active`; **Jellyscrub** came up `NotSupported` and was
  removed — this Jellyfin version's native trickplay (now hardware-accelerated, see above)
  covers the same job, exactly the caveat noted against that plugin in the shortlist.
  `jellyfin-rpc`, also on the shortlist, turned out not to be a Jellyfin plugin at all (it's a
  standalone client-side Discord Rich Presence daemon with nothing to install server-side) —
  left out of the install, noted here rather than silently dropped.

### Fixed
- **Bazarr's Radarr, Sonarr, and Plex connections were all completely non-functional** —
  discovered while wiring up its new Jellyfin connection, not something anyone had reported.
  All three were configured with `ip: 127.0.0.1`, which from inside Bazarr's own container
  resolves to Bazarr itself, never to another container or to the native-host Plex install.
  `use_radarr`/`use_sonarr`/`use_plex` were all `false` too. Net effect: Bazarr had never
  actually synced a movie or series list from anything since it was added, regardless of
  anything configured in its own subtitle settings. Fixed Radarr → `radarr:7878` and
  Sonarr → `sonarr:8989` (both now on `stacknet` like every other container) and enabled both
  — confirmed live via Bazarr's own logs, SignalR feeds connected to both, and `/api/series`
  now returning real data for the first time. Plex's `127.0.0.1` is left unfixed for now — it
  needs a Plex API token this session didn't have on hand; noted, not silently ignored.
- **Both Seerr instances' Radarr/Sonarr root folders were stale**, pointing at
  `/mnt/zurg/{movies,shows}` — the FUSE-mount paths [2.2.0] moved every root folder off of,
  months ago. Found while copying the existing Seerr's connection settings as a template for
  Jellyseerr's: `activeDirectory` in `config/seerr/settings.json` still said `/mnt/zurg/movies`
  / `/mnt/zurg/shows`, and Radarr/Sonarr's own `/api/v3/rootfolder` confirmed those paths were
  `"accessible": false`. This meant any request made through the Plex-backed Seerr since
  [2.2.0] would have been handed a dead root folder. Patched `settings.json` directly to
  `/data/movies`/`/data/shows`, restarted Seerr, confirmed the fix persisted, and deleted the
  now-dead root folder entries from both Radarr and Sonarr entirely.

*Built with Claude AI.*

## [2.3.0] — Homepage replaced with Heimdall; Watchtower's stale Docker client fixed

### Changed
- Swapped `homepage` (ghcr.io/gethomepage/homepage) for `lscr.io/linuxserver/heimdall` as the
  stack's dashboard. Populated Heimdall directly via its SQLite database (`app.sqlite`) with
  all 14 apps from the stack, grouped into the same five categories Homepage used: Requests
  (Seerr), Acquisition (Prowlarr, Zilean, Decypharr, NZBGet), Libraries (Radarr, Sonarr,
  Lidarr, Readarr, Whisparr, Bazarr), Media Server (Plex), and Monitoring & Tools (Tautulli,
  FlareSolverr). Fetched matching icons from the community dashboard-icons set for 12 of the
  14 apps; Zilean and Decypharr have no icon available there (Homepage worked around this the
  same way, falling back to generic MDI icons).
- Hit two real bugs while wiring this up, not just config: (1) the newly created `heimdall`
  container came up with a broken `/etc/resolv.conf` (raw `127.0.0.53` instead of Docker's
  embedded `127.0.0.11` DNS), breaking every outbound request from inside it — fixed by force-
  recreating the container, after which Docker rewrote resolv.conf correctly. (2) Populated
  each app's description into Heimdall's `description` column, which is actually reserved for
  enhanced-app JSON config and gets `json_decode`'d on every page load — plain text there
  caused `json_decode` to return `null`, and the next line's `$config->url = ...` threw
  "Attempt to assign property on null", 500ing every category page. Fixed by moving
  descriptions to the correct `appdescription` column and re-verified all five category pages
  and the root dashboard return 200 with the right apps listed.

### Fixed
- `watchtower` was crash-looping: `containrrr/watchtower:latest` (now an archived/deprecated
  repo) bundles a Docker client capped at API 1.25, but the host's Docker Engine (29.6.1) has
  dropped support for anything below API 1.40. Moved to the actively maintained
  `nickfedor/watchtower` fork — same env vars, drop-in replacement. Confirmed stable post-
  switch: `Watchtower 1.19.0 using Docker API v1.55`, no more restarts.

*Built with Claude AI.*

## [2.2.0] — Root folders moved off Zurg's read-only FUSE mount, verified end-to-end

### Fixed
- v2.1.0 fixed *visibility* of Decypharr's staged downloads but "verify fix in real time" (an
  explicit ask, not an assumption that the first fix was sufficient) surfaced a second, deeper
  bug: every arr app's root folder was still `/mnt/zurg/<type>` — Zurg's own rclone FUSE mount.
  Reproduced directly rather than inferred from logs: `docker exec sonarr sh -c "ln -s ...
  /mnt/zurg/shows/_symlink_test"` returned `System.IO.IOException: I/O error [EIO]`. Rclone/
  WebDAV-backed FUSE mounts like Zurg's are read-oriented and simply do not support having new
  files or symlinks written into them — confirmed with symlink, hardlink, and plain copy, all
  failing identically. This meant **no import had ever been able to complete** through any arr
  app since the stack went live, regardless of the v2.1.0 path-visibility fix: Decypharr could
  stage a file, the arr app could now see it, but writing the actual symlink into the root
  folder always failed at the last step.
- Considered two narrower options (remote-path-map Decypharr's own mount into each root
  folder; or point root folders at Decypharr's DFS mount directly) and asked whether doing
  both was overkill — it was, and neither actually solved the real problem: NZBGet's fallback
  path independently needs a genuinely writable root folder regardless of what's done for
  Decypharr specifically, so patching only the Decypharr side would've left a second write-
  incompatible path unaddressed.
- Fix: gave every arr app a new root folder backed by regular host disk instead of a FUSE
  mount — `./media/{movies,shows,music,books,adult}`, mounted into each container at
  `/data/<type>` (these directories existed since v2.0.0 but were unused placeholders until
  now). Migrated existing tracked content via each app's API: added the new root folder,
  updated every tracked series/movie's `rootFolderPath`/`path` to the new location, removed
  the old `/mnt/zurg/<type>` root folder. Sonarr had 2 series, Radarr 2 movies, Whisparr 1
  series to migrate; Lidarr and Readarr had none yet.
- Discovered along the way: this specific Whisparr build (v2.2.0.108) uses Sonarr's
  `series`/`episode` API shape, not Radarr's `movie` shape — the first migration attempt 404'd
  on `/api/v3/movie` against it, corrected to `/api/v3/series`.
- Verified genuinely end-to-end, not just "no error returned": triggered a live search for
  Blue Bloods S01E03, watched it flow Prowlarr → Sonarr → Decypharr (Real-Debrid caching +
  symlinking) → back into Sonarr's queue → import. Confirmed at the filesystem level —
  `/data/shows/Blue Bloods/Season 1/blue.bloods.s01e03.720p.web.h264-skyfire.mkv` exists as a
  symlink into `/mnt/decypharr/__all__/...`, `episode.hasFile` is `true`, and the symlink
  target was proven genuinely readable (pulled real bytes through the full chain from inside
  Sonarr's container, confirming it isn't a dangling link to a debrid file that never actually
  cached). Also confirmed write access on the other 4 new mounts (`/data/movies`, `/data/music`,
  `/data/books`, `/data/adult`) directly.
- Blocklist cleanup was needed mid-investigation: Sonarr auto-blocklists a release after a
  failed import, which kept blocking re-tests of the exact releases needed to prove the fix —
  cleared via `DELETE /api/v3/blocklist/bulk`, scoped only to entries from the bug's specific
  timestamp window (42 entries total across two passes), not a blanket wipe.

### Action needed
- **Plex** (native, not dockerized) needs new library locations added for
  `/home/bear/Stack/media/{movies,shows,music,books,adult}` — this is where all future arr-app
  imports land now, and Plex can't be reconfigured via this stack's tooling; it's a manual
  Settings → Libraries → Edit → Add folder step. See
  [Plex library locations to add](README.md#plex-library-locations-to-add).

*Built with Claude AI.*

## [2.1.0] — Decypharr download path visibility fixed across every arr app

### Fixed
- Radarr surfaced a health warning: "download client Decypharr places downloads in
  `/app/downloads/radarr` but this directory does not appear to exist inside the container."
  Investigated rather than dismissed — this was real and already actively breaking imports.
  Sonarr's history showed repeated `grabbed` → `downloadFailed` cycles for the same episodes
  across many different releases, timestamped exactly when Decypharr had real symlinked media
  files sitting in its own container that no arr app could see. Since v1.7.0 first wired up
  Decypharr as the download client, every app's container only shared `/mnt`, `/usenet`, and
  its own `/config` — none of which overlapped with where Decypharr stages completed
  downloads internally (`/app/downloads/<category>`, backed by `config/decypharr` on the
  host). This meant no debrid-grabbed content had ever actually been importable through
  Decypharr in any app, only appearing to work when Recyclarr/Prowlarr syncs succeeded
  upstream of the actual download step.
- Fix: bind-mounted `config/decypharr/downloads` into Radarr, Sonarr, Lidarr, Readarr, and
  Whisparr at the identical path Decypharr uses internally (`/app/downloads`) — avoids
  needing Remote Path Mappings entirely, per Decypharr's own documented best practice of
  matching paths exactly across containers.
- Verified with a controlled test rather than assuming: wrote a file from inside Decypharr's
  container, confirmed it was immediately readable from Sonarr's container at the identical
  path. Live-release testing was confounded by unrelated (and correctly-working) mechanisms —
  Sonarr's own blocklist protecting against re-grabbing releases that failed before the fix,
  the "Low Quality Sources/Groups" custom format correctly rejecting garbage EZTV releases,
  and one candidate correctly refused by Decypharr for not being cached on Real-Debrid
  (`download_uncached: false`) — none of which are bugs, all confirmed as intended behavior
  along the way.
- The 3 specific episodes that failed during the fix window are gone (cleaned up by the
  download client's normal failed-download handling) and will need a fresh search to re-grab;
  everything going forward uses the corrected path.

*Built with Claude AI.*

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
