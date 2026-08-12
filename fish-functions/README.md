# Fish functions

All fish functions used on this host, mirrored here from `~/.config/fish/functions/` for version control. Most target this project's Control Panel API at `192.168.4.105:8420`; a handful are general shell/host utilities unrelated to the stack.

Install by symlinking or copying the whole directory into `~/.config/fish/functions/`.

---

## Personal shell utilities

Not stack-specific — general-purpose fish helpers.

- **`alacritty-use-theme <theme>`** — switch the active Alacritty theme (aliases.toml aware).
- **`backup <file>`** — copy a file to `<file>.bak`.
- **`claudehome`** — `cd ~/Claude` and launch Claude Code with permissions skipped and that directory added.
- **`cleanup`** — remove orphaned pacman packages in a loop until none remain.
- **`copy <dir1> <dir2>`** — recursive copy, trimming a trailing slash from the source first.
- **`history [args...]`** — fish's builtin history with timestamps shown, forwarding all arguments so subcommands like `history clear`/`history search` still work.
- **`__history_previous_command`** / **`__history_previous_command_arguments`** — bang-bang (`!!`) / bang-dollar (`!$`) history expansion support.
- **`TMDB`** — `cd` into the repo and run `scripts/audit-tmdb-links.py` against the Movies library, writing a CSV report.

## Core helper

- **`__stack_api <METHOD> <PATH> [JSON_BODY]`** — private helper every `stack-*` function funnels through. Calls Control Panel's API and prints its `message` field, handling both response shapes (`{"ok","message",...}` on success, FastAPI's `{"detail": {...}}` wrapper on an error). Exit status mirrors the API's own `ok` field.

## Container control & stack status

- **`stack-status`** — live running/health state of every container.
- **`stack-container <restart|stop|start> <name>`** — control a single container.
- **`stack-restart-all [-y|--yes]`** — restart every container in the stack; confirms first unless `-y` is given.
- **`stack-resource-check`** — containers missing an explicit `mem_limit`/`cpus`.
- **`stack-oom-check`** — containers Docker has recorded an OOM-kill for.
- **`stack-image-check`** — checks every pinned image tag for a newer registry digest (no pull).
- **`stack-top [cpu|mem] [limit]`** — top containers by CPU or memory usage.
- **`stack-disk-usage`** — per-app `config/` directory size, largest first.
- **`stack-docker-disk-usage`** — Docker disk usage broken down by images/containers/volumes/build cache.
- **`stack-mount-health`** — checks every known FUSE mountpoint resolves cleanly.
- **`stack-perms-check`** — config files unreadable by group/other (won't get backed up).
- **`stack-version`** — README's declared version plus a live container count.
- **`stack-help`** — lists every `stack-*` command with a one-line description.

## Radarr / Sonarr (general)

- **`stack-arr <radarr|sonarr> <rss-sync|search-missing|unstick|unstick-importing>`** — trigger RSS sync, a missing search, or clear a wedged queue item. `unstick` only touches items the app itself flagged; `unstick-importing` targets a different failure mode — a download stuck in `trackedDownloadState "importing"` while `trackedDownloadStatus` stays `ok`, so it never trips the normal flag.
- **`stack-arr-search-toggle <radarr|sonarr|all> <on|off>`** — turn RSS sync + automatic search on/off for every indexer, without touching manual search. Useful for pausing new grabs while an import queue drains.
- **`stack-arr-logs <radarr|sonarr|prowlarr> [lines]`** — tail an app's container log directly.
- **`stack-arr-backlog <radarr|sonarr>`** — the app's internal command-queue backlog (searches, RSS sync, bulk moves).
- **`stack-arr-import-backlog`** — items sitting on "waiting on import" across both apps, grouped by release rather than printed per-episode.
- **`stack-arr-import-candidates <radarr|sonarr>`** — files stuck in the queue ready to manually import, numbered for `stack-arr-import`.
- **`stack-arr-import <radarr|sonarr> <index>`** — import one file by index from `stack-arr-import-candidates`.
- **`stack-arr-import-all <radarr|sonarr>`** — import every candidate in one call instead of one at a time.
- **`stack-arr-missing-aired <radarr|sonarr>`** — monitored items with no file that have already aired/released, filtering out upcoming ones.
- **`stack-arr-queue-errors`** — queue items across every app already flagged as a problem by the app itself.
- **`stack-arr-import-starvation`** — why nothing is importing when the queue looks empty and clean. `RefreshMonitoredDownloads` both polls the download client and triggers imports, so a bulk search backlog that starves it out of the command pool stops imports *and* empties the queue at once, making every other queue check read healthy on a fully broken app (2026-08-08 incident). Read-only; the auto-remediation runs inside `stack-queue-autofix`. See the `arr-import-starvation-diagnosis` skill.
- **`stack-queue-autofix`** — blocklists+re-searches `failedPending` items in Radarr/Sonarr and Radarr's `importBlocked` items (always remove+research, no manual-import attempt first), disables `autoRedownloadFailed` if a retry storm is detected (≥15 failedPending in one pass), clears any search backlog starving imports, and reports NzbDAV queue health. Distinct from `unstick` — `unstick` only catches `trackedDownloadStatus warning/error`, which `failedPending` items don't set. Powers the recurring 5-minute queue-monitoring loop.
- **`stack-arr-blocklist <radarr|sonarr> [limit]`** — recent blocklisted releases.
- **`stack-arr-blocklist-clear <radarr|sonarr> [-y|--yes]`** — clear every blocklisted release; confirms first unless `-y`.
- **`stack-arr-list-implementations <radarr|sonarr>`** — every import-list type the app's build supports, configured or not.
- **`stack-import-lists <radarr|sonarr>`** — configured import lists and their enabled state.
- **`stack-cutoff-unmet <radarr|sonarr> [limit]`** — items below their quality profile's cutoff (have a file, just not the target quality).
- **`stack-recently-added <radarr|sonarr> [limit]`** — recently added items with file/episode status.
- **`stack-customformat-diff <radarr|sonarr>`** — diffs current custom-format scores against the last check, then updates the cache.
- **`stack-command-queue-summary`** — command-queue backlog across radarr/sonarr/prowlarr at once.
- **`stack-queue-status`** — every app's download queue with live-measured speed/ETA (two samples, ~4s apart).
- **`stack-backlog-status`** — every app's wanted/missing backlog with a throughput-projected ETA.
- **`stack-sonarr-monitor-episodes-fix`** — fixes any episode left unmonitored under a monitored Sonarr series/season (season 0 left alone).

## List imports (Radarr/Sonarr)

Most take `[--no-search] [--no-monitor] [--dry-run]`; list-scraping ones also take `[--limit N]`.

- **`stack-letterboxd-radarr <film-url>`** — add one Letterboxd film to Radarr, scraping its TMDb id server-side.
- **`stack-letterboxd-radarr-list <list-url>`** — add every film in a Letterboxd list.
- **`stack-letterboxd-radarr-watchlist <user-url>`** — add every film in a user's watchlist.
- **`stack-letterboxd-radarr-watched <user-url>`** — add every film a user has watched.
- **`stack-letterboxd-radarr-collection <collection-url>`** — add every film in a Letterboxd film collection.
- **`stack-letterboxd-radarr-filmography <role> <slug>`** — add a person's whole filmography by crew role (actor, director, writer, producer, editor, cinematography, composer, etc).
- **`stack-letterboxd-radarr-popular`** — add Letterboxd's current popular films.
- **`stack-letterboxd-radarr-list-random`** — picks one random URL from a cached list of featured Letterboxd lists and imports it, removing it from the cache so a future run won't repeat it.
- **`stack-mdblist-import <mdblist-list-url>`** — import a public MDBList list, routing movies to Radarr and TV to Sonarr in one call.
- **`stack-trakt-list-import <radarr|sonarr> <trakt-username> <trakt-listname> <display-name> [--no-search]`** — add a public Trakt list as an import list.
- **`stack-radarr-list-import <list-url> <display-name> [--no-search]`** — add a hosted Radarr-list-format JSON URL as a Radarr import list.
- **`stack-sonarr-custom-list-import <base-url> <display-name> [--no-search]`** — add a generic JSON/RSS feed as a Sonarr import list.
- **`stack-tmdb-company-import <tmdb-company-id> <display-name> [--no-search]`** — add a studio's filmography as a Radarr import list.
- **`stack-tmdb-keyword-import <tmdb-keyword-id> <display-name> [--no-search]`** — add a TMDB keyword-filtered list as a Radarr import list.
- **`stack-plex-watchlist-import <radarr|sonarr> [--no-search]`** — add your own Plex watchlist as a native import list (uses Plex's own OAuth token already set up in that app).
- **`stack-plex-rss-import <radarr|sonarr> <plex-watchlist-rss-url> [--no-search]`** — add a Plex Watchlist RSS feed URL as an import list (polls the public feed instead of using an account token).

## Ratings

Standalone `OMDB_KEY`/`MDBLIST_KEY` secrets — no other app dependency.

- **`stack-rating-imdb <imdb-id>`** — a title's IMDb rating via OMDb.
- **`stack-rating-mdblist <imdb-id>`** — a title's MDBList score plus its IMDb sub-rating if MDBList has one.

## Prowlarr

- **`stack-prowlarr-indexers`** — every configured indexer's enabled state and priority.

## Plex

- **`stack-plex <scan|empty-trash|optimize-db|clean-bundles>`** — trigger a Plex maintenance action.
- **`stack-plex-libraries`** — list Plex library names.
- **`stack-plex-empty-trash [library ...]`** — empty trash on one library, or every library if none given.
- **`stack-plex-analyze [library ...]`** — queue deep media analysis (loudness, chapter thumbnails, intro/credits/ad markers, voice activity) for one library, or all of them.
- **`stack-plex-duplicates [min_gb]`** — flag movies carrying redundant duplicate files well beyond a normal multi-version upgrade.
- **`stack-plex-sessions`** — who's watching what right now, direct play vs transcode per session.
- **`stack-plex-recently-added [limit]`** — what's actually finished importing and become visible in Plex (distinct from `stack-recently-added`, which shows what was added to management, not necessarily downloaded).
- **`stack-plex-updates`** — checks whether Plex has a newer release on its current channel (check only, doesn't apply it — this stack pins Plex deliberately).
- **`stack-tmdb-missing`** — scans every movie/show library for items with no TMDb link, writes them to `~/missing.txt`.

### Plex Butler tasks

`stack-plex-butler <task>` fires one on demand (run with no args for the full list); each also has its own dedicated wrapper:

- **`stack-plex-automatic-updates`** — Plex's own app-update check.
- **`stack-plex-backup-database`** — back up Plex's database.
- **`stack-plex-clean-cache-files`** — delete old cache files.
- **`stack-plex-clean-log-files`** — delete old supplemental log files.
- **`stack-plex-deep-media-analysis`** — full deep analysis across every library.
- **`stack-plex-garbage-collect-blobs`** — garbage-collect unused metadata blobs.
- **`stack-plex-garbage-collect-media`** — garbage-collect unused library media records.
- **`stack-plex-generate-ad-markers`** — generate ad-break markers.
- **`stack-plex-generate-chapter-thumbs`** — generate chapter thumbnail (BIF) files.
- **`stack-plex-generate-credits-markers`** — generate end-credits markers.
- **`stack-plex-generate-intro-markers`** — generate intro markers.
- **`stack-plex-generate-media-index`** — generate media index files for fast seeking.
- **`stack-plex-generate-voice-activity`** — generate voice-activity data for dialogue boost.
- **`stack-plex-loudness-analysis`** — analyze audio loudness for volume leveling.
- **`stack-plex-music-analysis`** — analyze music library audio.
- **`stack-plex-process-assets`** — process pending local assets (posters, themes, etc).
- **`stack-plex-refresh-epg`** — refresh Live TV/DVR EPG guide data.
- **`stack-plex-refresh-libraries`** — refresh metadata for every library.
- **`stack-plex-refresh-local-media`** — refresh local media file changes.
- **`stack-plex-upgrade-media-analysis`** — re-run analysis for items whose analysis version is outdated.

## NzbDAV

- **`stack-nzbdav-queue`** — current Usenet download queue.
- **`stack-nzbdav-history [limit]`** — recent download history (completed/failed).
- **`stack-nzbdav-stats`** — aggregate queue/history counts.
- **`stack-nzbdav-delete-failures`** — delete every "Failed" entry from history (a Failed row can block re-grabbing a release with a matching name).

## Bazarr

- **`stack-bazarr-wanted`** — movies/episodes still missing a subtitle, across both libraries.
- **`stack-bazarr-history [limit]`** — recent subtitle download history, successes and failures.
- **`stack-bazarr-provider-status`** — per-provider throttle/error state.
- **`stack-bazarr-search-missing`** — trigger an on-demand missing-subtitle search instead of waiting for the scheduler.

## Cleanuparr

- **`stack-cleanuparr-instances`** — which *arr apps Cleanuparr actually has a connected instance for.
- **`stack-cleanuparr-strikes [limit]`** — recent stalled/slow/malware strikes.

## Seerr

- **`stack-seerr-requests [pending|approved|available|all]`** — media requests sitting in Seerr, by status.

## Backup

- **`stack-claude-full-backup`** — one-off full `~/Claude` tree tar.zst backup to Dropbox, dated and not overwritten in place.

## Notifications

- **`stack-notify-test`** — send a real test message to the stack's Discord webhook.

## Host / system diagnostics

- **`stack-disk-free [warn-pct] [crit-pct]`** — real-filesystem disk free space with pass/warn/fail marks.
- **`stack-disk-health`** — SMART health summary for every physical disk.
- **`stack-mem-pressure`** — kernel PSI (pressure stall info) for memory, CPU, and IO.
- **`stack-kernel-check`** — compares the running kernel against the installed one (a mismatch means a reboot is needed).
- **`stack-reboot-check`** — checks for a pending-reboot marker and cross-references `stack-kernel-check`.
- **`stack-uptime-report`** — uptime, load average, and whether the last shutdown was clean.
- **`stack-zombie-check`** — lists zombie/defunct processes and their parent.
- **`stack-service-failed`** — `systemctl --failed` across both system and user manager instances.
- **`stack-timer-status`** — enabled state + last-run result for every `stack-*.timer` unit.
- **`stack-cron-list`** — system timers, user timers, and crontab entries in one view.
- **`stack-journal-errors`** — error-or-worse journal entries since last boot, summarized by unit.
- **`stack-journal-size [--vacuum-size SIZE]`** — journald's on-disk usage; optionally vacuum it down.
- **`stack-firewall-status`** — active nftables rule summary plus every listening port.
- **`stack-ssh-doctor`** — checks `~/.ssh` exists, `known_hosts` has a GitHub entry, and a private key is present and loadable.
- **`stack-git-status-all`** — `git status --short` across every repo directly under `~/Claude`.
- **`stack-pkg-updates`** — pending pacman + AUR updates.
- **`stack-pkg-update [--yes]`** — run the actual system update (confirmation-gated).
- **`stack-pkg-history [N]`** — tail of pacman's transaction log.
- **`stack-pkg-orphans [--remove]`** — list (or remove) orphaned packages.
- **`stack-pkg-clean-cache [keep-N]`** — vacuum pacman's package cache to the last N versions per package.
- **`stack-aur-audit`** — cross-checks installed packages against Arch security advisories, or lists AUR/foreign packages if `arch-audit` isn't installed.
- **`stack-flatpak-updates [--apply]`** — list, or apply, pending Flatpak updates.
- **`stack-log-levels [reset]`** — check, or reset, every Servarr app's log level.

## 2026-07-30 additions — Tautulli, Wrapperr, Maintainerr, Checkrr, Prefetcharr, Lingarr, Kometa

### Tautulli

- **`stack-tautulli-activity`** — current Plex streams as Tautulli sees them, with per-session transcode detail.
- **`stack-tautulli-terminate-stream <session_key>`** — kill one active stream by session key.
- **`stack-tautulli-history [limit]`** — recent watch history across every user/library.
- **`stack-tautulli-stats`** — home-page stat cards (top movies/shows/users).
- **`stack-tautulli-users`** — every known Plex user with lifetime plays/duration.
- **`stack-tautulli-user-history <user_id> [limit]`** — watch history filtered to one user.
- **`stack-tautulli-libraries`** — per-library item counts as Tautulli last saw them.
- **`stack-tautulli-recently-added [limit]`** — Tautulli's own recently-added feed.
- **`stack-tautulli-server-info`** — which Plex server Tautulli is actually configured against.
- **`stack-tautulli-newsletters`** — configured newsletter definitions, if any.
- **`stack-tautulli-notifiers`** — notification agents configured inside Tautulli itself.
- **`stack-tautulli-plays-by-date [days]`** — daily play-count trend.
- **`stack-tautulli-sync-check`** — confirms Tautulli is tracking this stack's real Plex server.

### Wrapperr

- **`stack-wrapperr-status`** — reachability plus whether a Tautulli connection is saved.
- **`stack-wrapperr-reports`** — saved report definitions.
- **`stack-wrapperr-links`** — generated public share links.
- **`stack-wrapperr-tautulli-link-check`** — confirms Wrapperr's saved Tautulli API key still matches the live one.

### Maintainerr

- **`stack-maintainerr-rules`** — configured rules (expected empty by design).
- **`stack-maintainerr-rule-detail <rule_id>`** — full definition of one rule.
- **`stack-maintainerr-collections`** — Plex collections being tracked for cleanup evaluation.
- **`stack-maintainerr-collection-media <collection_id>`** — media items inside one tracked collection.
- **`stack-maintainerr-logs [lines]`** — tail Maintainerr's container logs.
- **`stack-maintainerr-safety-check`** — alerts if any rule is ever active.
- **`stack-maintainerr-plex-link-check`** — confirms Maintainerr's configured Plex host matches this stack's real Plex.

### Checkrr

- **`stack-checkrr-badfiles [limit]`** — corrupt/unreadable files flagged (scan/log only, no auto-delete/reacquire).
- **`stack-checkrr-badfiles-count`** — just the total bad-file count.
- **`stack-checkrr-scan-status [lines]`** — tail recent scan activity.
- **`stack-checkrr-config`** — effective checkpaths, cron schedule, and per-app process flags.
- **`stack-checkrr-reacquire-guard`** — alerts if the process flag is ever flipped to enable auto-delete/reacquire.
- **`stack-checkrr-recent-scans`** — scan-cycle start/finish markers only, for cadence/duration.

### Prefetcharr

- **`stack-prefetcharr-logs [lines]`** — tail Prefetcharr's log file.
- **`stack-prefetcharr-status`** — container state plus the most recent prefetch-trigger event.
- **`stack-prefetcharr-config`** — effective config (interval, prefetch count, etc) as deployed.
- **`stack-prefetcharr-plex-link-check`** — confirms Prefetcharr's baked-in Plex URL is still current.

### Lingarr

- **`stack-lingarr-stats`** — lifetime translation totals.
- **`stack-lingarr-movies [limit]`** — movies Lingarr tracks via its Radarr connection.
- **`stack-lingarr-shows [limit]`** — shows Lingarr tracks via its Sonarr connection.
- **`stack-lingarr-logs [lines]`** — tail Lingarr's container logs.
- **`stack-lingarr-recent-translations`** — recent individual translation-completed events.

### Kometa

- **`stack-kometa-status`** — time until the next scheduled run.
- **`stack-kometa-run-now`** — trigger an immediate run alongside the scheduler (detached — returns right away).
- **`stack-kometa-logs [lines]`** — tail Kometa's container logs.
- **`stack-kometa-last-run-result`** — outcome of the last completed run.
- **`stack-kometa-config`** — which libraries/collections `config.yml` is set to touch.

### Cross-app

- **`stack-newapps-status`** — health sweep of all new apps at once.

## 2026-08 additions — new-services batch (PLANS.md Phases 1–3)

Backfilled 2026-08-12: Phases 1 and 2 shipped without updating this file or
`stack-help.fish`, so ntfy and Speedtest Tracker are documented here for the
first time alongside Organizr.

### ntfy (Phase 1)

- **`stack-ntfy-publish <topic> <message>`** — push a message to an ntfy topic.
- **`stack-ntfy-topics`** — list the topics the server currently has configured.

### Speedtest Tracker (Phase 2)

- **`stack-speedtest-latest`** — most recent completed result (down/up/ping/jitter).
- **`stack-speedtest-history [days]`** — results over the last N days, newest first (default 7).
- **`stack-speedtest-run-now`** — trigger a test outside the hourly schedule.

### Organizr (Phase 3)

- **`stack-organizr-tabs`** — every tab Organizr has, plus which stack services are missing one. Includes Organizr's own built-in Settings/Homepage pages, which this stack does not manage.
- **`stack-organizr-sync`** — add a tab for any service in the canonical table (`control-panel/services/organizr/tabs.py`) that doesn't have one. Additive only: it never edits or deletes an existing tab, so anything hand-tweaked in Organizr's UI survives. Run it after adding a service to the stack.

### Scrutiny (Phase 4)

Complements `stack-disk-health` (raw `smartctl`, right now) with Scrutiny's trended view. This host has one physical disk, a 954GB NVMe, so these are really about wear tracking on the disk the whole stack runs on.

- **`stack-scrutiny-summary`** — all-disk status at a glance: model, temperature, power-on hours, healthy or failing.
- **`stack-scrutiny-disk [uuid|name|serial]`** — per-disk SMART detail, including the wear attributes that actually predict end-of-life (`percentage_used`, `available_spare`, `media_errors`, `critical_warning`) and anything Scrutiny has flagged. The argument is optional on a single-disk host.
- **`stack-scrutiny-collect`** — run the collector now rather than waiting for its midnight cron. Returns the collector's own output.
- **`stack-scrutiny-alert-test`** — fire Scrutiny's test notification through its configured sink, which here is ntfy topic `scrutiny-alerts`. Proves the disk-failure alert path works before a disk actually fails.
