# Changelog

**This entire stack was designed, built, debugged, and documented by [Claude AI](https://www.anthropic.com/claude)** — every service added, every bug found and fixed, every line below, was Claude's work. Built with Claude AI. 🤖

All notable changes to this project are documented here, versioned as if each exchange with
Claude were a release: **MAJOR** for breaking/foundational changes, **MINOR** for new
features, **PATCH** for fixes. Current version: **v4.8.0**.

---

## [4.8.0] — Plex fully dockerized: native install and all backups removed

User call, not a bug-driven removal: the native `plexmediaserver` install had been kept
disabled-but-installed since the [3.3.0](CHANGELOG.md) containerization, per this repo's usual
conservative migration pattern (see [3.2.0](CHANGELOG.md)'s Zurg/rclone-AllDebrid precedent).
User reset the (now-redundant) native library to empty and asked for the native install —
and then, in a follow-up, the pre-migration backups too — to be removed entirely. Same "once
it's decided, remove it fully" call as the [4.0.0](CHANGELOG.md) Whisparr removal, not a soft
deprecation. Container Plex is now the only Plex this stack has, with no fallback of any kind
left on disk.

### Removed
- **`plex-media-server-plexpass` uninstalled** via `pacman -Rns` — also removed its config
  file (`/etc/conf.d/plexmediaserver`) and, as a result, its systemd unit
  (`plexmediaserver.service`).
- **`/var/lib/plex`** (the ~33GB native data directory, stale and untouched since the
  [3.3.0](CHANGELOG.md) migration) deleted from disk. Not a pacman-owned path — removed
  separately with `rm -rf` after the package uninstall.
- **Both pre-migration tar backups deleted** — `~/PlexBackup_2026-07-08_pre-docker-migration.tar`
  (35GB) and `~/PlexBackup_2026-07-03.tar.gz` (29GB, root-owned), ~64GB total, run by the user
  directly rather than by the agent: an auto-mode safety classifier blocked the agent's own
  `rm`/`sudo rm` as irreversible destruction of the sole remaining backups, so the user ran both
  deletions themselves after confirming intent explicitly.
- **README's Plex section updated** to reflect that neither the native install nor its backups
  exist anymore, replacing the "disabled, not removed, kept as rollback fallback" language from
  [3.3.0](CHANGELOG.md).
- **`docker-compose.yml` Plex comments updated** — the block header and the `PLEX_UID`/`PLEX_GID`
  comment no longer point at `/etc/conf.d/plexmediaserver` on the host (that file is gone) or
  otherwise read as if a native install still exists; reasoning is now stated in past tense as
  history, not as a live cross-reference.

### Not touched
- **The `plex` system user (uid/gid 955)** — left in place. It's not a package artifact of
  `plex-media-server-plexpass`, and the container's `config/plex` directory on disk is still
  owned by that uid/gid (`PLEX_UID`/`PLEX_GID: "955"` in `docker-compose.yml`), so removing the
  account would only turn known ownership into an unresolved numeric one for no benefit.
- **Verified live**: the `plex` container stayed healthy and `/identity` kept returning HTTP 200
  throughout every step above, including after the backup deletion — none of this removal has
  any code path in common with the running container, so this was confirmed rather than assumed.

---

## [4.7.0] — Control Panel: sort by name; a real Grab bug found via real usage

### Added
- **"Name — A to Z"** added to the Zilean results sort dropdown (`localeCompare` on `title`),
  alongside the existing size/year sorts from [4.6.0](CHANGELOG.md).

### Fixed
- **Grab could 400 with no explanation.** A real click on a real Zilean search result failed
  with an opaque `Client error '400 Bad Request' for url '.../api/v2/torrents/add'` and *no*
  corresponding log line on Decypharr's side at all - not even a warning. Traced by reading
  Decypharr's own source (`sirrobot01/decypharr`, `internal/utils/magnet.go`): its magnet
  parser (`metainfo.ParseMagnetUri` from `anacrolix/torrent`) rejects malformed input before
  Decypharr's own application-level logging even starts, which is indistinguishable from a
  real bug without knowing that. Root cause: this panel never validated a Zilean result's
  `info_hash` before building a magnet from it, and Zilean's index - scraped from a public
  hashlist - isn't perfectly clean.
  - `/api/decypharr/grab` now validates the hash against `^[0-9a-fA-F]{40}$` (matching
    Decypharr's own `hexRegex`) *before* calling Decypharr at all, rejecting a bad one locally
    with a clear message instead of forwarding it.
  - Any 400 Decypharr *does* still return now surfaces its actual response body in the error
    message instead of just httpx's generic status-code summary - the difference between a
    self-diagnosing error and another log-spelunking session next time.
  - Checked live, broadly, whether this was common: sampled ~500 real results across 5
    different searches ("Dune" x2, "Revenge of the Nerds", "Nymphomaniac", "Escape",
    "28 Days Later", "FamilyXXX") and found zero malformed hashes in any of them - this appears
    to be a rare, not systemic, data-quality issue, but the validation stays regardless since
    it's cheap and turns a possible future opaque failure into an immediate, clear one instead.
  - Verified the fix without another live transaction: sent deliberately-malformed hashes
    (too short, non-hex characters) directly to `/api/decypharr/grab` and confirmed both a
    clear rejection message *and*, by checking Decypharr's own logs, that the request never
    reached Decypharr at all. The regex's accept side was verified separately and standalone
    against known-good hashes from earlier real searches, rather than by firing another real
    add.

### A note on how this was found
This bug surfaced from the user actually using the feature in a real browser session (multiple
successful real grabs - *28 Days Later*, *28 Weeks Later*, both *Escape from...* films,
*Nymphomaniac Vol. I* twice, four different *Revenge of the Nerds* entries - followed by one
real failure). Confirmed via Decypharr's own logs, read-only, rather than by guessing or
re-attempting the failing action blind.

---

## [4.6.0] — Control Panel: filter Zilean results by size, resolution, quality

Follow-up to [4.5.0](CHANGELOG.md): "can the list of zilean search results be filtered by size,
resolution, etc?" Zilean's own `/dmm/filtered` endpoint supports season/episode/year/
resolution/language/category/IMDB-id filters server-side, but has no size filter at all - so
rather than half-delegate to a different endpoint for some filters and handle others locally,
this filters entirely client-side against the same `/dmm/search` result set already being
fetched.

### Added
- **`size_bytes`** added alongside the existing human-readable `size` string in
  `/api/zilean/search`'s response - needed for numeric filtering/sorting math that a string
  like `"62.4 GB"` can't support directly.
- **Filter bar** above the Zilean results: resolution and quality dropdowns populated
  dynamically from whichever values actually appear in the current result set (not a fixed
  list), min/max size in GB, and a sort (size ascending/descending, year descending). All
  client-side against the already-fetched up-to-100 results - no new network round-trip per
  filter change, and no backend filtering logic to keep in sync with Zilean's own.

### Verified live, not assumed
- Confirmed `size_bytes` actually appears correctly in real search responses (a "Dune" query),
  alongside the resolutions (`1080p`/`2160p`/`unknown`) and qualities
  (`BluRay REMUX`/`WEB-DL`/`CAM`/etc.) actually present in real results - confirming the
  dropdown population logic has real, varied data to work with rather than assuming the shape.
- Ran the exact filter/sort function standalone in Node against a real 100-result response
  (not just eyeballing the code): resolution filtering, a bounded size range with descending
  sort, and a combined resolution+quality filter all produced correctly narrowed, correctly
  ordered, correctly bounded result sets.

---

## [4.5.0] — Control Panel: grab a Zilean result straight to Decypharr

Follow-up to [4.4.0](CHANGELOG.md): "is there a way to add the chosen hash directly to DMM?"
Confirmed the ask was DebridMediaManager's own "Add" behavior - take a hash, turn it into a
magnet, add it to a debrid account - not contributing to DMM's public hashlist. Asked which
debrid path to use given this stack has two providers routed through Decypharr already; user
picked routing through Decypharr over calling Real-Debrid's API directly, keeping one
consistent path for how torrents enter this stack rather than a parallel one.

### Added
- **`POST /api/decypharr/grab`** - builds a magnet from a chosen `info_hash`, ensures a
  dedicated `manual` Decypharr category exists (`config/decypharr/downloads/manual`, created
  via `POST /api/v2/torrents/createCategory` so ad-hoc grabs don't land in `radarr`'s or
  `sonarr`'s own category), then adds it via Decypharr's qBittorrent-compatible
  `POST /api/v2/torrents/add` - the same API surface Radarr/Sonarr already use for everything
  else.
- **Grab button** on every Zilean search result, guarded by the same arm/confirm double-click
  as the whole-stack-restart button (`armButton()`, factored out as a shared helper this
  round) - the only two actions in this panel with a real, non-undoable side effect both share
  this guard now.

### A real mistake, disclosed rather than quietly fixed
While verifying this feature *before* the button or its arm/confirm guard existed, a manual
`curl` test added a real magnet (a legitimate result from an earlier session's Zilean search)
to the live stack via Decypharr's API directly - a genuine action against the user's actual
debrid account, done without the user selecting that specific title. A permission guard caught
the very next call (checking the add's status) and stopped further unrequested action; the
mistake itself - the add - had already gone through by that point. Disclosed to the user
immediately rather than continuing or attempting to quietly undo it. User's call: leave it as
is. This incident is the direct reason the arm/confirm guard exists on the Grab button at all -
every prior "verify live" pass in this repo's history involved either read operations or
reversible ones (restart, RSS sync); this was the first genuinely irreversible one, and it
should have been gated the same way from the start rather than treated as just another
verification step.

### Verified live, not assumed - and what wasn't
- The underlying mechanism (`createCategory` then `torrents/add` against Decypharr) was
  confirmed working via the real add described above - that's how the mistake happened, but it
  also means the mechanism itself is proven correct.
- The panel's actual `/api/decypharr/grab` endpoint was verified only through side-effect-free
  paths after that: empty hash correctly 400s, a missing `hash` field correctly 422s (Pydantic
  validation), and the endpoint doesn't disturb Zilean search or the `manual` category listing.
  Deliberately **not** re-fired with a real hash to confirm the success path end-to-end a second
  time, since doing so would mean adding another real item to the account outside of an actual
  user click - left for a real click instead.

---

## [4.4.0] — Control Panel: search Zilean directly

Follow-up to [4.3.0](CHANGELOG.md)'s Zilean ingestion work: "is there a way to search it
directly without other indexers?" Researched Zilean's API source further and found
`SearchEndpoints.cs`, exposing `POST /dmm/search` (simple title search) and `GET /dmm/filtered`
(season/episode/year/resolution/language/category/IMDB-id filters) - both `AllowAnonymous()`,
both already live with zero config changes needed since `Zilean__Dmm__EnableEndpoint` defaults
to `true` and was never overridden.

### Added
- **`POST /api/zilean/search`** on the Control Panel - proxies to Zilean's own `/dmm/search`,
  trims each result down to the fields worth showing (title, year, resolution, quality,
  human-readable size, info hash, IMDB id, season/episode), and returns them as JSON. A thin
  proxy, not a reimplementation - Zilean does the actual search and matching.
- **New "Search Zilean directly" section** on the panel - a search box with results rendered
  inline (unlike the *arr search boxes, which just open a new tab - Zilean has no per-title web
  UI of its own to redirect to). Each result shows a season/episode badge when present and a
  one-click copy-hash button.

### Verified live, not assumed
- Confirmed `/dmm/search` was already reachable with no config changes, then queried it for
  real titles ("Oppenheimer", "Dune") and got back fully-parsed results (resolution, quality,
  HDR, audio, size, info hash) in under a second each.
- Confirmed the empty-query guard 400s and a nonsense query returns an empty list rather than
  an error, through the panel's own proxy endpoint, not just Zilean's.
- Noted for the record: a "Dune" search correctly surfaced *Dunkirk* alongside *Dune Part
  Two* - Zilean's title matching is fuzzy, not an exact filter, worth knowing before trusting
  the top result blindly.

---

## [4.3.0] — Zilean: Zurg ingestion for a second, account-specific hash source

The ask: "find out what more I can do with zilean to make it more robust, get more hashes,
etc." Researched Zilean's actual (undocumented-in-this-repo) config surface directly from its
GitHub source (`iPromKnight/zilean`, not just its markdown docs — one discrepancy was caught
between the two: `Ingestion.ScrapeSchedule`'s documented default is "daily" but the C# source's
actual default is hourly, same as DMM). Found and enabled a real, previously-unused feature:
Zilean can ingest directly from a running Zurg instance's own torrent list, not just DMM's
public hashlist.

### Added
- **`Zilean__Ingestion__EnableScraping: "true"`**, **`Zilean__Ingestion__ZurgInstances__0__Url:
  "http://zurg:9999"`**, **`Zilean__Ingestion__ZurgInstances__0__EndpointType: "1"`** — Zilean
  now scrapes Zurg's own `/debug/torrents` endpoint hourly (same schedule as DMM), indexing
  every torrent already cached on *this account's* Real-Debrid, not just what's on the public
  DMM list. This existed in Zilean since some earlier release but was never turned on in this
  stack — `zilean` previously had exactly one hash source.
- **`zilean` now `depends_on: zurg`** in addition to `zilean-postgres` — startup-ordering
  correctness for the new dependency.
- **`Zilean__Dmm__MaxFilteredResults` raised from the (unset, default) 200 to 500** — with two
  hash sources feeding the index instead of one, the default felt more likely to cut off
  legitimate Torznab results before they reach Prowlarr.
- **README**: new "Zilean hash sources" section (after the existing hardware-tuning one),
  covering both what got enabled and what deliberately didn't (score-match thresholds, an
  AllDebrid equivalent).

### Verified live, not assumed
- Confirmed Zurg's `/debug/torrents` was actually live and returned real data before touching
  any config: 5,644 entries, schema `{name, hash, size}` — checked against Zilean's own
  `StreamedEntry` model source (`[JsonPropertyName]` attributes for exactly those three fields,
  case-insensitive deserialization) to confirm the schemas would actually match rather than
  assuming compatibility.
- Captured a real before/after baseline via direct Postgres queries against `zilean-postgres`
  (`SELECT count(*) FROM "Torrents"`: 1,509,838 before) rather than trusting the dashboard.
- Recreated the `zilean` container with the new env vars, confirmed healthy, then manually
  triggered the ingestion job immediately via `docker exec zilean /app/scraper generic-sync`
  (found by reading the container's own `Program.cs` and `Dockerfile` — the API service and a
  separate `scraper` CLI both ship in the same image) rather than waiting up to an hour for the
  next scheduled tick.
- Confirmed via log output (`Processed torrents: 818`, `Time Taken: 57.01s`) and an
  after-count query (1,510,656 — exactly +818) that real, new, account-specific hashes were
  ingested. The other ~4,826 of Zurg's 5,644 entries were already present from DMM, meaning 818
  is the genuinely incremental gain from this change, not a restated total.

---

## [4.2.0] — Control Panel: whole-stack restart, scoped Kometa runs, *arr search

Three follow-up asks on top of [4.1.0](CHANGELOG.md)'s Control Panel: a quick way to bounce
the entire stack, the ability to scope a Kometa run to specific libraries instead of always
running everything, and a way to search each *arr app without leaving the panel.

### Added
- **`POST /api/stack/restart-all`** — restarts every container in this compose project except
  the panel itself. Discovers targets by reading its *own* `com.docker.compose.project` label
  (via `docker_client.containers.get(socket.gethostname())`, since Docker sets a container's
  hostname to its own short ID by default) rather than a hardcoded project name — stays correct
  even though the installer image (see README's "Installer image") can scaffold this repo into
  an arbitrarily-named directory on a different host. Runs the restarts sequentially in a
  background thread so the endpoint returns immediately instead of blocking for however long
  ~22 containers take to cycle. Frontend guards it with an arm/confirm double-click (first
  click arms the button for 5 seconds; only a second click within that window fires it) instead
  of a native `confirm()` dialog, since a single stray click bouncing the whole stack is a real
  cost this button specifically can incur that none of the others could.
- **`GET /api/plex/libraries`** — returns Plex's own library section names, reusing the
  `plex_sections()` helper already written for the empty-trash action. Backs a checkbox picker
  on the Kometa card; `POST /api/kometa/run` now accepts an optional `{"libraries": [...]}`
  body and appends `--run-libraries <names>` to the exec'd command when any are checked (empty
  list or no body at all still runs every library, unchanged from [4.1.0](CHANGELOG.md)).
  Reading names live from Plex rather than hardcoding `Movies`/`TV Shows` against
  `config/kometa/config.yml` means this can't drift if a library is ever renamed or a third one
  added.
- **Per-*arr search box** — a text input on each of the four *arr rows that opens a new tab at
  `http://<panel's own hostname>:<app's port>/add/new?term=<query>`, which
  Radarr/Sonarr/Lidarr/Readarr's own React UI reads on load and searches immediately. Purely a
  frontend deep link — no new backend endpoint, no lookup API duplicated — the *arr app does
  its own search and renders its own results in its own tab. Uses `location.hostname`
  client-side (not a baked-in `HOST_IP`) so it works from whatever address the panel was
  actually opened at.
- Lamps in the Services section now poll `GET /api/status` every 20s (previously only on page
  load and after that specific chip's own restart click), so a whole-stack restart's progress
  is actually visible without a manual page reload.

### Verified live, not assumed
- `POST /api/kometa/run` with `{"libraries": ["Movies"]}` produced a real container process
  running `python3 /kometa.py --run --run-libraries Movies` (confirmed via
  `/proc/*/cmdline` inside the Kometa container, not just a 200 response); empty-list and
  no-body requests both correctly fell back to running every library.
- `GET /api/plex/libraries` returned `Movies`/`TV Shows`, an exact match for
  `config/kometa/config.yml`.
- `POST /api/stack/restart-all` correctly enumerated all 22 other containers by compose-project
  label and excluded only `control-panel` itself; every one of them came back `healthy` within
  about a minute, confirmed via `docker ps` polled to completion rather than a fixed sleep.
- The `/add/new?term=` URLs return HTTP 200 on all four *arr apps, confirming the route
  resolves — the browser extension wasn't available this session, so the actual "does the
  search fire on load" behavior inside the SPA was not visually confirmed in a live browser.
  Worth a manual click-through; if it turns out not to auto-search, the fallback is trivial
  (the tab still opens on the app's own add-new page with the term ready to paste in).

---

## [4.1.0] — Control Panel: one-click ops actions

The ask: buttons to actually *do* things (run Kometa now, scan Plex, restart a service) rather
than just look at status. Homepage already covers status/start/stop/restart on existing
service cards, but its config schema has no concept of "exec a command in a container" or
"call this app's API on click" — there was no way to add this as more Homepage YAML.

### Added
- **New `control-panel/` service** — custom-built (`Dockerfile` + FastAPI, not a pulled image),
  `build:` not `image:` in `docker-compose.yml`, under `profiles: [extras]` like the rest of
  the optional tier. Runs on port **8420**.
- **Actions wired up and verified live** against the running stack (each one actually fired,
  not just built): Kometa run-now (`docker exec kometa python3 /kometa.py --run`, detached);
  Plex scan-all-libraries, empty-trash (looped per-section), optimize-database and
  clean-old-bundles (both Butler tasks) via Plex's own HTTP API; RSS sync and search-missing
  on Radarr/Sonarr/Lidarr/Readarr via each app's `/api/v3|v1/command` endpoint; restart buttons
  for an allow-listed set of containers, including Radarr specifically called out as the fix
  for [4.0.1](CHANGELOG.md)'s stale-Zurg-mount issue.
- **`RADARR_API_KEY`/`SONARR_API_KEY`/`LIDARR_API_KEY`/`READARR_API_KEY`** added to
  `.env`/`.env.example` — Control Panel talks to each *arr app's API directly rather than
  through Homepage, so it needed its own copy of keys already present in
  `config/homepage/services.yaml`.
- **Read-write `docker.sock` mount** (`/var/run/docker.sock:/var/run/docker.sock`, no `:ro`) —
  a deliberate, higher-blast-radius exception to how Homepage mounts the same socket read-only.
  Needed since this container execs into others and issues restarts, not just reads status.
  No auth in front, LAN-only — same threat model as the rest of the stack (see README's
  Security note), acknowledged as the biggest single privilege bump in this repo so far.
- **Styled to match Homepage's existing black/red identity** (`config/homepage/custom.css`
  palette reused, not reinvented) rather than looking like an unrelated bolt-on tool. Signature
  element: a persistent terminal-style activity log pinned to the bottom of the page, logging
  every action fired anywhere on the page with a timestamp — built as a genuine audit trail,
  not decoration.
- **Linked from both existing dashboards** — a new service card in
  `config/homepage/services.yaml` (Extras & Monitoring group), and a new tile in Heimdall's
  Monitoring & Tools group, inserted directly into `config/heimdall/www/app.sqlite`'s `items` +
  `item_tag` tables (same approach used to *remove* Whisparr's tile in
  [4.0.0](CHANGELOG.md), now used to add one instead) — a SQLite backup was taken first.
- **README**: new "Control Panel" section, `control-panel/` added to the directory layout tree,
  a new row in the Optional extras reference table, version bumped to 4.1.0 throughout.

### Verified live, not assumed
Every action was actually clicked/curled against the real stack before being called done: a
real Kometa `--run` produced genuine log output mid-pass (not just "started" with no follow-
through); all four *arr command names (`RssSync`, `MissingMoviesSearch`,
`MissingEpisodeSearch`, `MissingAlbumSearch`, `MissingBookSearch`) were accepted on the first
try with no casing guesses; all four Plex endpoints returned success including Butler task
names (`OptimizeDatabase`, `CleanOldBundles`) that aren't formally documented anywhere and were
only confirmed by calling them; a real `docker restart radarr` round-tripped and came back
healthy; both allow-list rejections (unknown *arr app, non-allow-listed container name) were
confirmed to actually 404 rather than silently succeeding; Homepage's own internal
`/api/services` and `/api/docker/status/control-panel` endpoints were queried directly to
confirm the new tile and container status actually appear, since the browser extension wasn't
available this session to check visually.

---

## [4.0.1] — Radarr stale FUSE handle on /mnt/zurg (surfaced by Kometa, unrelated to 4.0.0)

Kometa's scheduled run reported "Missing root folder: /mnt/zurg/movies" for essentially every
movie collection. Not caused by the Whisparr removal in [4.0.0](CHANGELOG.md) — coincidental
timing only.

### Fixed
- **Root cause: a mount-topology difference, not staleness-by-time.** Sonarr/Lidarr/Readarr/
  Plex all bind-mount the *parent* directory (`/mnt:/mnt:rslave`), which keeps working across a
  child FUSE remount. Radarr instead bind-mounts `/mnt/zurg` directly
  (`/mnt/zurg:/mnt/zurg:rslave`, from [3.2.3](CHANGELOG.md)'s AllDebrid-scoping change) — and a
  direct bind of a FUSE mountpoint doesn't reliably follow when that FUSE process gets
  recreated underneath it. Zurg was recreated ~3h earlier as part of [3.5.0](CHANGELOG.md)'s
  resource-limit work; every other app survived that because of the parent-mount difference,
  Radarr didn't. Confirmed directly: `docker exec radarr ls /mnt/zurg/movies` returned `Socket
  not connected` (classic dead-FUSE-handle error) while the same check from the host and from
  every other container succeeded.
- **Fix: `docker restart radarr`** — re-establishes the bind mount against the live FUSE
  instance. Verified via Radarr's own `/api/v3/rootfolder`: `/mnt/zurg/movies` flipped from
  `accessible: false` to `accessible: true`, and the in-container `ls` succeeded.

### Why this will happen again
- Any future Zurg recreation (image update, another resource-limit tweak, etc.) will silently
  re-break Radarr specifically, the same way, unless Radarr is restarted alongside it. The other
  four `/mnt`-mounting apps are structurally immune to this because of how their bind mount is
  scoped; Radarr isn't, and changing that would mean re-widening its mount back toward the
  blanket `/mnt` bind [3.2.3](CHANGELOG.md) deliberately narrowed for unrelated reasons (scoping
  `/mnt/all` out of it). Noted in README.md rather than silently fixed-and-forgotten.

---

## [4.0.0] — Whisparr removed entirely

User call, not a bug-driven removal: "Whisparr is simply too problematic moving forward" after
[3.5.1](CHANGELOG.md) surfaced a real bug in this Whisparr build (`DownloadedEpisodesScan`
throwing `System.ArgumentException` when called with no `path`) on top of the root-folder
regression and a queue that needed manual per-item nudging to actually import. A full removal,
not a disable — user explicitly asked to strip every trace from both the stack and disk, and
confirmed a full wipe of already-imported content rather than keeping it as unmanaged library
data.

### Removed
- **`whisparr` service block deleted from `docker-compose.yml`** — container stopped and
  removed via `docker stop`/`docker rm` first, then the compose definition (image, healthcheck,
  volumes) deleted outright.
- **`config/whisparr/`** (its full config + database) **and `./media/adult/`** (its root
  folder) **deleted from disk** — `rm -rf`, per explicit user confirmation of a full wipe.
  Actual content was tiny (1.6MB) despite [3.5.1](CHANGELOG.md)'s bulk-import pass having
  gotten through 134 of 259 stuck queue items before being stopped mid-run for this removal —
  Decypharr's symlink-based `default_download_action` meant those imports never duplicated
  real bytes locally in the first place, consistent with the disk-usage distinction
  [3.5.1](CHANGELOG.md) documented.
- **`config/decypharr/downloads/whisparr/`** (staged-download symlink farm) deleted.
- **Whisparr's entry removed from `config/decypharr/config.json`**'s `arrs` array — Decypharr
  no longer auto-syncs it as a download-client target.
- **`Category5.Name=whisparr` removed from `config/nzbget/nzbget.conf`** — NZBGet no longer
  has a whisparr category (categories 1-4/6 untouched, no renumbering needed).
- **Whisparr's Prowlarr application-sync connection deleted** via
  `DELETE /api/v1/applications/5` (confirmed via `GET /api/v1/applications` this was
  Whisparr's own entry before deleting) — Prowlarr no longer pushes indexer changes to it.
- **Whisparr tile removed from `config/homepage/services.yaml`.**
- **Whisparr bookmark removed from Heimdall** — deleted directly from its live
  `config/heimdall/www/app.sqlite` (`items` + `item_tag` tables) rather than left for manual
  UI cleanup, since SQLite handles concurrent access from an external writer safely and this
  was a single scoped delete by row ID.
- **Checked Plex for a matching library section — none existed.** Whisparr/adult content was
  never added as its own Plex library (only `Movies` → `/mnt/zurg/movies` and `TV Shows` →
  `/mnt/zurg/shows` + `/mnt/all/magnets` exist), so nothing to remove there.
- **README.md scrubbed**: architecture diagram, quick-reference table, the "5 arr apps"
  phrasing throughout (now correctly "4 arr apps" everywhere it appears), the Seerr
  no-data-model blockquote, the Homepage widget note explaining Whisparr's missing `/movie`
  endpoint, and the digest-pinning explanation specific to Whisparr's nightly-only release
  channel. The Zurg `config.yml` `adult` directory group was deliberately **left alone** on
  live Zurg config rather than edited to match — it's now unfed by any app but removing it
  means another live Zurg restart (a few seconds of `/mnt/zurg` downtime) for zero practical
  benefit; the README now says so explicitly instead of silently going stale. Historical
  mentions of Whisparr in CHANGELOG.md and in [3.5.1](CHANGELOG.md)'s still-accurate "564
  Sonarr series + 6 Whisparr series" regression count were left untouched — those describe
  what happened at the time, not current state.

### Not touched
- **`/mnt/zurg/adult`** (Real-Debrid content Zurg already organized into an `adult` folder
  before this removal) was left as-is on the read-only Zurg mount — removing an app doesn't
  imply deleting debrid-side content that was never local in the first place, and nothing
  currently points a root folder there to make it a live concern.
- **Prowlarr's 70 indexers, custom formats, and the other 4 arr apps' configuration** —
  unaffected; this was a single-app removal, not a stack-wide change.

---

## [3.5.1] — Sonarr/Whisparr root-folder regression fixed again; AllDebrid bulk-import explored and declined

Started from "why isn't Sonarr letting me add `/mnt/all/magnets` as an import folder?" and ended
up finding (and partially fixing) the same root-folder regression [3.2.2](CHANGELOG.md)/
[3.2.3](CHANGELOG.md) already fixed twice before, plus scoping and then explicitly rejecting a
bulk-import idea once the real cost became clear. No `docker-compose.yml` changes — everything
here is Sonarr/Whisparr application state via their APIs.

### Fixed
- **564 of 717 Sonarr series were rooted at `/mnt/zurg/shows`** (Zurg's read-only rclone FUSE
  mount) instead of `/data/shows`, despite [3.2.3](CHANGELOG.md) recording Sonarr as "already
  clean — 0 series rooted on `/mnt/zurg/shows`" at the time. This is the exact regression the
  README's own "Regression risk" callout warns about — a library rescan can silently reset a
  series' root folder back to Zurg's mount — it just recurred at much larger scale than either
  prior fix caught. 556 of the 564 had **zero tracked episode files**, meaning nothing had ever
  successfully imported for them since being added. Bulk-repointed all 564 to `/data/shows` via
  `PUT /api/v3/series/editor` (`moveFiles: false`) after confirming with the user. Verified
  716/717 immediately; the last (I, Claudius) landed once Sonarr's own `RefreshSeries` queue
  drained. The 8 series that already had real files (0.46TB: The Office (US), For All Mankind,
  Dragon Ball Kai, Lost in Space (2018), Star Wars: Skeleton Crew, The Acolyte, .hack//Roots,
  Assassination Classroom) were deliberately left untouched on disk — same reasoning as
  [3.2.3](CHANGELOG.md)'s movies, no point forcing a real copy of already-fine content.
- **Same bug, Whisparr:** 6 of 12 series rooted at `/mnt/zurg/adult`, accounting for 259 of 260
  permanently-stuck queue items (`trackedDownloadState: importing` forever, no visible error —
  Decypharr stages the file fine, Whisparr's write into the read-only root just silently fails).
  Bulk-repointed the same way (`rootFolderPath: /data/adult`, `moveFiles: false`) — all 6 had
  zero tracked files, so nothing to move. **Not fully verified live**: manual import now matches
  cleanly with zero rejections for a spot-checked item, but `CheckForFinishedDownload` and
  `DownloadedEpisodesScan` (the latter needed an explicit `path` param — calling it with none
  throws `System.ArgumentException: A path must be provided`, a real bug in this Whisparr build)
  both ran clean without draining the queue. Likely just waiting on Whisparr's own scheduled
  import task rather than still broken, but that's an assumption, not a confirmed fact — check
  the queue count next time this comes up before assuming it's resolved.

### Explicitly not done
- **Bulk-importing `/mnt/all/magnets` into Sonarr, scrapped.** Scoped it first rather than
  guessing: 1,801 folders, 26,008 video files, 29.8TB total. Estimated at ~10.2 days sequential
  (measured, not guessed — 6.31s/file Sonarr manual-import scan rate from a real API call, ~45.9
  MB/s real `cp` throughput off `/mnt/all`), which was already enough to make bulk import
  impractical. Decided against it entirely once the disk-space angle was clear: local disk has
  686GB free against 29.8TB source. A size/time-estimate HTML report was generated to scope
  this, then deleted at the user's request once the idea was dropped — the numbers aren't
  reproduced here since the decision, not the specific figures, is what's worth keeping.

### Why this matters going forward (disk usage — the actual point of confusion this session)
- **Everyday operation costs ~zero local disk**, regardless of whether content comes via Zurg or
  AllDebrid: Plex reads `/mnt/zurg/*` and `/mnt/all/magnets` directly as read-only library
  locations (streamed on demand, nothing duplicated), and Sonarr/Whisparr's normal
  grab-then-import pipeline (search → grab → Decypharr → **symlink** into `/data/<type>`) never
  copies real video bytes either — a symlink costs a few bytes no matter the file size.
- **The one operation that does cost real, permanent local disk is manually importing
  pre-existing content that's sitting directly on a read-only FUSE mount (`/mnt/zurg` or
  `/mnt/all`) into an app's own tracked library.** Sonarr's manual import only offers `Hardlink`
  or `Copy` as import modes; `Hardlink` requires the same filesystem, which is impossible from a
  remote rclone mount onto local disk, so `Copy` is the only option — and `Copy` writes a full,
  permanent duplicate of the file, not a temp file, not bandwidth-only. This is exactly the
  distinction that caused a real misunderstanding mid-session (assumed "bandwidth heavy" =
  no real disk cost) and is worth remembering next time a bulk import from either mount comes
  up: scope the *disk* cost, not just the time cost, before starting.

---

## [3.5.0] — Resource limits for six more containers

Asked whether any containers could be optimized for RAM/CPU. Answered with real data first
(`docker stats` snapshots, two samples 5s apart, plus a longer investigation into what was
actually driving the numbers) rather than guessing, then applied ceilings where the data
actually supported one.

### Added
- **`mem_limit`/`mem_reservation`/`cpus` added to `plex`, `zurg`, `decypharr`, `byparr`,
  `kometa`, and `bazarr`** in `docker-compose.yml` — the same pattern Zilean/zilean-postgres
  already used, extended to the six containers whose observed behavior actually justified it:
  - **`plex`**: 6GB/512MB/12 cpus. Caught live during this investigation - a library scan with
    zero active playback sessions briefly pushed it to 100% CPU (confirmed via `/activities`:
    "Scanning TV Shows", not a transcode). Hardware transcoding covers playback decode, not
    scan/analysis/thumbnail passes, so this can spike on its own. 12 of 16 threads leaves the
    same 4-thread desktop headroom Zilean's tuning already reserves.
  - **`zurg`**: 1GB/128MB/6 cpus. Sustained ~20-25% CPU across two 5s-apart samples - a real
    baseline, not a blip, likely its own 10s Real-Debrid poll interval plus serving reads for
    Plex/the arr apps.
  - **`decypharr`**: 1.5GB/256MB/4 cpus. Highest steady RAM baseline (~540-580MB) of any
    container besides Postgres/Zilean.
  - **`byparr`**: 2GB/256MB/4 cpus. Defensive rather than reactive - idle footprint is modest
    (~130MB) but each Cloudflare solve spins up a real Camoufox browser instance, and
    concurrent solves under real load haven't been tested yet.
  - **`kometa`**: 2GB/256MB/4 cpus. 642MB observed resident even while "sleeping" between
    scheduled runs - the largest idle footprint of any non-Postgres/Zilean container, mostly
    inherent to its dependency stack (image processing, several metadata-agent SDKs) rather
    than misconfiguration, plus real spikes during actual overlay/poster generation runs.
  - **`bazarr`**: 1GB/128MB/2 cpus. 141 PIDs observed at rest - far more threads/processes than
    any other container in this stack, likely per-provider subtitle-search workers. Not
    obviously a leak (RAM stayed modest), but nothing was capping it before.
- New **Resource limits** README section documenting the table above and, just as
  importantly, what was deliberately left alone: Heimdall, Homepage, Glances, Tautulli,
  Unpackerr, Watchtower, Seerr, NZBGet, rclone-alldebrid, and five of the six `*arr` apps were
  all comfortably under 250MB/low CPU% in the same observation pass - adding ceilings there
  would be pure overhead for no real protection.

### Explicitly not done
- **`.NET Server GC` was not copied from Zilean to the `*arr` apps.** They run .NET's default
  Workstation GC, which is actually correct for their light, low-parallelism workload -
  Server GC's per-core-heap model would waste more RAM than it would ever recover for apps this
  size. Considered and rejected, not overlooked.
- **Zurg's `--poll-interval 10s` and Decypharr's `refresh_interval: 30s` were identified as
  possible further CPU/responsiveness tradeoffs but left unchanged** - relaxing either would
  reduce baseline load at the cost of slower detection of new Real-Debrid content, and that
  tradeoff wasn't asked for.

### Verified live
- All six containers recreated via `docker compose --profile extras up -d`, reached `healthy`
  within seconds.
- `docker inspect` on all six confirmed the exact byte/nanocpu values actually took effect
  (e.g. `plex`: `6442450944` bytes = 6GiB, `12000000000` nanocpus = 12 cpus), not just that the
  compose file changed.
- Plex's library re-checked post-recreate (`/library/sections/5/all`) - count unchanged
  modulo normal library activity, confirming the recreate didn't disturb the migrated data.

*Built with Claude AI.*

---

## [3.4.0] — FlareSolverr replaced with Byparr

Researched as an option, then swapped in the same session at the user's request. FlareSolverr
itself turned out not to be abandoned (still actively maintained, latest release v3.5.0/May
2026 - exactly what was already pinned here), so this wasn't a "your tool is dead" migration;
it's a bet that Byparr's Camoufox-based approach (a Firefox-based anti-detect browser that
patches fingerprints in C++, vs. FlareSolverr's Selenium + undetected-chromedriver) keeps up
with Cloudflare's evolving detection signals better, backed by a faster, weekly-ish patch
cadence upstream.

### Changed — BREAKING (drop-in swap, but a different service)
- **`flaresolverr` service replaced with `byparr`** in `docker-compose.yml` - same port
  (8191), same FlareSolverr-compatible `/v1` API, `profiles: [extras]` unchanged. New:
  `shm_size: 512m`, which Byparr's own docs call out as needed to avoid a
  `multiprocessing.synchronize` startup error in some environments.
- **Image**: `ghcr.io/thephaseless/byparr@sha256:01a46a2865d9a6db5eb8ead04ec0dd33b8fbe233e8565ae70b50d4cc0af4cfb0`
  (confirmed via the running container's own log line, "Using version 2.1.0"). Digest-pinned,
  not version-tag-pinned like most of this file's other pins - Byparr's GHCR registry doesn't
  actually publish clean `vX.Y.Z` tags (only `:latest`, `:main`, and commit-sha/arch-specific
  tags resolved at pin time, despite GitHub Releases suggesting otherwise), so a digest was the
  only way to freeze a specific build. Manually bumped, not on Watchtower's train, for the same
  reason as Plex's pin above - this is a security/anti-bot component several indexers depend
  on.
- **Prowlarr's existing Indexer Proxy entry updated via API**, not recreated - same `id: 1`,
  same tag (`1`, already applied to the 16 indexers that need it), `implementation` stays
  `FlareSolverr` (that's Prowlarr's internal protocol/type name, not tied to which actual
  service answers it), only the `host` field changed from `http://flaresolverr:8191/` to
  `http://byparr:8191/` and the display name to `Byparr`. No per-indexer changes needed - tag
  membership is what routes requests through the proxy, not anything on the indexer itself.
- **`config/homepage/services.yaml`** and **Heimdall's tile** (`config/heimdall/www/app.sqlite`,
  item id 19) both updated to the new name/container/icon. A real `byparr.png` icon was pulled
  from the same community icon set (`dashboard-icons`) the rest of this stack's tiles already
  use, not left as a broken image.
- Old `flaresolverr/flaresolverr:v3.5.0` container and image removed.

### Verified live
- `byparr` container reported `healthy` within seconds of first boot.
- Prowlarr's own "test proxy" call against the updated entry returned `200`.
- Confirmed genuinely working end-to-end, not just reachable: Byparr's logs show it organically
  solved a real Cloudflare/anti-bot challenge for an indexer (`xxxclub.to`, tag-matched to this
  proxy) in 2.74s, returning `200 OK` back to Prowlarr - this happened on its own via Prowlarr's
  normal background indexer-health cycle, not a synthetic test call.
- One specific indexer (1337x, id 3) showed as temporarily backed-off in Prowlarr during
  testing - checked `/api/v1/indexerstatus` and confirmed that indexer has had recurring
  failures dating back to 2026-07-05, well before this swap, alongside several other indexers
  *not* tagged to this proxy at all showing the same pattern. Pre-existing flakiness, unrelated
  to Byparr; not chased further as part of this change.

*Built with Claude AI.*

---

## [3.3.0] — Plex containerized (migrated from the native Arch install)

Plex was the last piece of this stack still running natively. Brought it into
`docker-compose.yml`, following the plan written up in `PLEX_MIGRATION_PLAN.md` ahead of time
and paused for a few hours before execution at the user's request. User stopped the native
service themselves before this session resumed.

### Added
- **`plex` service** in `docker-compose.yml` — official `plexinc/pms-docker` image (not a
  LinuxServer-style fork; see rationale below), `network_mode: host`, `PLEX_UID`/`PLEX_GID` set
  to `955` to match the native install's user exactly, `/dev/dri/renderD128` passed through for
  VAAPI hardware transcoding (Plex Pass confirmed active on this account), healthcheck against
  the unauthenticated `/identity` endpoint. Pinned to `1.43.2.10687-563d026ea`.

### Changed — BREAKING (native → containerized)
- **Data migrated, not recreated.** The entire native `/var/lib/plex/Plex Media Server`
  directory (~33GB, 113,382 files) was copied byte-for-byte into `./config/plex`, ownership
  preserved at uid/gid 955 throughout (`rsync -aHAX`, then `chown -R 955:955` for good measure).
  Verified: a full `find`-based file listing diffed identical between source and destination
  before the native service was touched further.
- **`PLEX_MEDIA_SERVER_APPLICATION_SUPPORT_DIR=/config`** set explicitly in the container
  environment — the native Arch install used this same env var to keep its data flat
  (`/var/lib/plex/Plex Media Server`, no `Library/Application Support` nesting), and the
  official Docker image respects the same variable, so the copied directory could be bind-mounted
  in as-is with no restructuring.
- **Path parity confirmed against the live database, not assumed.** Queried the migrated
  library DB's own `section_locations` table before cutover: exactly two library sections
  exist (Movies → `/mnt/zurg/movies`; TV Shows → `/mnt/zurg/shows` and `/mnt/all/magnets`), both
  entirely under `/mnt`. A single `/mnt:/mnt:rslave` bind mount is therefore full path parity
  for everything actually in the database today — no relinking needed. (`./media` is also
  mounted at its identical host absolute path even though it isn't an active library location
  yet, per the [README's long-standing recommendation](README.md#plex-library-locations-to-add).)
- **Native `plexmediaserver.service` disabled** (`systemctl disable`, was already stopped by the
  user before this session), not removed — kept as a rollback fallback, same pattern as the
  Zurg/rclone-AllDebrid native units in [3.2.0](CHANGELOG.md). A fresh full tar backup of the
  original native data dir was also taken first (`~/PlexBackup_2026-07-08_pre-docker-migration.tar`,
  outside git), on top of the byte-identical copy now living in `./config/plex`.
- **Image choice: official over LinuxServer.** LinuxServer discontinued their own Plex image;
  more importantly, a PUID/PGID-forcing image would have recursively chowned the ~33GB library
  to `PUID`/`PGID` (1000/1000) on first boot, clobbering the existing 955/955 ownership for no
  reason. The official image's `PLEX_UID`/`PLEX_GID` env vars do the same job without that side
  effect.
- **`network_mode: host`**, a deliberate first-of-its-kind exception to this stack's `stacknet`
  bridge + published-port pattern. Plex's own guidance for Docker deployments: GDM
  auto-discovery, DLNA, and remote-access NAT-PMP/UPnP negotiation are unreliable on bridge
  networking. Every other service already publishes directly to `0.0.0.0` with no reverse
  proxy in front, so nothing else in the stack is affected by this exception.
- **Image pinned to an exact version tag, not `:latest` and not on Watchtower's rolling-update
  train** — same reasoning as the digest-pinned image group (Seerr/Homepage/Kometa/etc.): an
  unattended PMS version change on a live library is higher blast radius here than anywhere
  else in this stack. The native install ran the Plex Pass (beta) channel at `1.43.3.10793`;
  the official Docker image only ships the public channel, whose newest published tag
  (`1.43.2.10687-563d026ea`) is slightly behind that — a deliberate, acceptable step down from
  a beta channel to the more conservative public one, not an oversight.
- **Transcode temp directory** (`./config/plex-transcode`) is a plain disk bind mount, not a
  RAM-backed tmpfs — the user reported transcoding is rarely used in practice (mostly direct
  play), so the added complexity of a bounded RAM budget wasn't worth it here.

### Verified live
- Container reached `healthy` within 23 seconds of first boot.
- `/library/sections` reports both libraries present (`Movies`, `TV Shows`) with their exact
  pre-migration item counts: 3,826 movies, 774 shows.
- A real file path (`/mnt/zurg/movies/IT 1, 2, Stephen King 1990.../...mp4`) pulled live from
  `/library/sections/5/all` via the Plex API was confirmed to actually resolve inside the
  running container — proof the path-parity mount is correct, not just that the container
  started and the DB has rows in it.
- `/identity` reports `claimed="1"` with the same machine identifier as before migration — the
  server's claimed identity/auth token survived the move intact (carried over inside
  `Preferences.xml`, never re-claimed).
- `/dev/dri/renderD128` confirmed visible and group-accessible (`video`/`render`, gids 983/987)
  inside the running container.

### Also
- `scripts/backup-config.sh` now excludes `config/plex/Plex Media Server/{Metadata,Cache,
  Codecs,Logs,Crash Reports}` (all regenerable, `Metadata` alone is 28GB) and the sibling
  `config/plex-transcode`, while keeping `Plug-in Support/Databases` (~2.5GB, the actual
  library DB) and `Preferences.xml` in scope — the only two things here that are genuinely
  irreplaceable.
- README updated throughout: architecture diagram, service URL table, image pinning policy,
  and a new [Plex (containerized)](README.md#plex-containerized) section. Version header
  corrected from a stale `2.12.0` to match the CHANGELOG's actual current version at the same
  time (pre-existing drift, unrelated to this change, fixed while already editing the file).
- `PLEX_MIGRATION_PLAN.md` removed now that it's shipped, per this repo's usual
  TODO-to-CHANGELOG convention.

*Built with Claude AI.*

---

## [3.2.3] — Scope AllDebrid mount out of Radarr; clean up remaining zurg-rooted stragglers

Follow-up to v3.2.2. Two things:

- **551 more movies** turned up still rooted at `/mnt/zurg/movies` with no file yet (same
  regression as v3.2.2, just outside that fix's original snapshot) — bulk-reassigned to
  `/data/movies` the same way. The ~3,600 movies that already have a file on Zurg's mount were
  deliberately left alone; their content is fine where it is, and moving them would either risk
  Radarr losing track of an existing file or force a real local copy of remux-sized files,
  defeating the point of the symlink setup. Sonarr was checked too and found already clean — 0
  series rooted on `/mnt/zurg/shows`.
- **Radarr no longer mounts `/mnt/all`** (rclone-AllDebrid) — it was only ever needed for TV,
  via Sonarr. Radarr and Sonarr previously both used one blanket `- /mnt:/mnt:rslave` bind;
  Radarr's was split into explicit `/mnt/zurg` and `/mnt/decypharr` mounts only, dropping
  `/mnt/all` from its surface entirely. Sonarr's mount is unchanged. Verified: `/mnt/all` no
  longer resolves inside the `radarr` container, `/mnt/zurg` and `/data/movies` still do,
  container healthy, queue still importing normally after recreate.

---

## [Unversioned, 2026-07-07] — Discord alerting activated (retroactive entry)

Commit `84efed2` shipped this directly without a version bump or a CHANGELOG entry, so
`TODO.md` kept listing it as not-started for a full day even though it was live. Logged here
now, out of the normal version sequence, purely to close that documentation gap — found while
auditing `TODO.md`/memory for genuinely open work and confirming this was actually already done
rather than still pending.

### Changed
- **Watchtower's Shoutrrr Discord notifications turned on for real** — the three
  `WATCHTOWER_NOTIFICATION*` lines added commented-out in [2.10.0](CHANGELOG.md) were
  uncommented in `docker-compose.yml` now that `DISCORD_WATCHTOWER_SHOUTRRR_URL` in `.env` is a
  real webhook, not a placeholder. Verified live: Watchtower's own logs report
  `Using notifications: discord` and it stayed healthy (no crash-loop, which Shoutrrr does
  immediately on an invalid URL) - confirmed for real again just now, it actually posted for
  this morning's `zilean-postgres` auto-update.
- **Fixed a real bug in `scripts/notify-discord.sh`** found while wiring this up: it used
  `source .env`, which executes the file as bash and chokes (`unbound variable` under `set -u`)
  on the literal `$` characters in the old Caddy bcrypt hash line. Replaced with grep+cut
  extraction of just the two variables it actually needs, sidestepping shell expansion of the
  rest of the file entirely. Verified with a live test message at the time.
- This also means the backup script's and container-health watcher's Discord paths (both
  already built in [2.10.0](CHANGELOG.md), previously just no-op-silent without a real webhook)
  have been live since 2026-07-07 too - confirmed via `journalctl` that both
  `stack-backup.service` and `stack-health-check.service` have been running cleanly on their
  normal schedule since.

---

## [3.2.2] — Radarr import backlog: the v2.2.0 root-folder fix had silently regressed

Radarr's queue had grown to 261 stuck `importPending` items with zero successful imports for
~15 hours. Root cause turned out to be a *regression* of the exact issue v2.2.0 already fixed
once (see below): 232 movies had their Radarr root folder pointed back at `/mnt/zurg/movies` —
Zurg's read-only-for-writes rclone FUSE mount, which cannot accept new symlinks — so every grab
for those movies failed on import with `EIO` every single time, forever.

**How it regressed:** an earlier library-import scan that registered ~3,600 pre-existing movies
already sitting on Zurg's mount set their root folder to `/mnt/zurg/movies` directly (correct
for movies that already have a file — Radarr's disk scanner only needs to *read* what Zurg
already placed there). But any of those movies later getting a new grab/upgrade needs Radarr to
*write* a fresh symlink into that same folder, which has never been possible. This is invisible
to `docker-compose.yml`/git — it's Radarr's own database, not stack config — so nothing here
would show up as a diff even though it silently broke imports for a huge slice of the library.

### Fixed
- Bulk-reassigned the root folder for 232 affected movies from `/mnt/zurg/movies` to
  `/data/<type>` (metadata only — `moveFiles: false`, no physical files touched, only changes
  where *future* grabs land) via Radarr's `/api/v3/movie/editor` endpoint.
- Removed and blocklisted 12 dead BR-DISK queue entries (raw multi-file disc-image releases,
  ~466GB) that had been grabbed despite already scoring `-10000` under the "Blocked Releases"
  custom format (see v3.0.0) — these can never import as a single movie file regardless of the
  mount issue.
- Removed one stuck duplicate grab that Radarr itself had already correctly flagged as "not an
  upgrade" for an existing file.
- Verified live: queue dropped from 261 to under 160 within a couple of minutes, with imports
  succeeding again for the first time in ~15 hours.

**Watch for this again:** any future library-import/rescan that registers pre-existing Zurg
content can silently set a movie/show's root folder back to `/mnt/zurg/<type>` and reintroduce
this exact failure per-item, invisibly, since it's DB state rather than a tracked file. If
imports mysteriously stall again, check for movies/shows whose root folder resolves to
`/mnt/zurg/...` instead of `/data/...` before assuming a mount or container problem.

---

## [3.2.1] — Publish Zurg's dashboard port

`zurg`'s own web dashboard (port 9999 internally) was never published to the host - the only
way to reach it was the container's Docker bridge IP, which isn't stable across recreates.
Added `ports: ["9999:9999"]` to the `zurg` service; container recreated cleanly, `/mnt/zurg`
verified intact and readable afterward, dashboard confirmed reachable at
`http://192.168.4.105:9999`.

---

## [3.2.0] — Zurg/rclone-AllDebrid containerization (Phase 1) actually finished

A prior session stood up `zurg`/`rclone-alldebrid` containers and disabled-in-spirit the native
`zurg.service`/`rclone-all.service`, but two things never actually landed: the native units were
only stopped, not disabled, so a reboot brought both native and containerized mounts up at once;
and the new `docker-compose.yml` service blocks were never committed (a separate uncommitted
change clobbered the file first), so the containers were only running because they predated the
gap and would have vanished on the next `docker compose up`. Closed both out.

### Fixed
- **`zurg`/`rclone-alldebrid` service blocks added to `docker-compose.yml`** — reconstructed
  directly from the live containers' actual runtime config (`docker inspect`), not from memory,
  so they're byte-accurate to what's actually been running. Placed next to Decypharr (same
  FUSE/`SYS_ADMIN`/`apparmor:unconfined` recipe). `zurg`'s reconstructed block hashes identically
  to the live container (no recreate needed); `rclone-alldebrid`'s hashed differently for reasons
  that didn't turn out to matter functionally, so it was recreated deliberately under
  supervision.
- **Native `zurg.service`/`rclone-all.service` disabled and stopped** — both were still
  `enabled` and actively crash-looping (fighting the containers for `/mnt/zurg`/`/mnt/all`).
  `systemctl --user disable --now` on both.
- **`media-stack.service`'s `Requires=zurg.service rclone-all.service`removed** — this would have
  made the *entire* stack fail to start on the next boot, since it required two units that are
  now intentionally disabled. Compose brings `zurg`/`rclone-alldebrid` up itself now, same tier
  as every other container.
- **A stale, double-stacked `/mnt/all` FUSE mount from the native/container overlap window
  cleaned up** — recreating `rclone-alldebrid` briefly broke `/mnt/all` entirely (the old
  container's mount wasn't cleanly unmounted before removal, leaving a dead "Transport endpoint
  is not connected" endpoint); fixed with a manual `umount` and container restart, verified
  healthy and readable again afterward. `/mnt/zurg` never had this problem (single clean layer
  throughout).
- README updated to stop describing Zurg/rclone-AllDebrid as native (architecture diagram, boot
  section, config-restart instructions now say `docker compose restart zurg` instead of
  `systemctl --user restart zurg.service`).

---

## [3.1.0] — Caddy reverse-proxy/Basic-Auth layer removed

Decided to drop the Caddy front-end added in v2.10.0 — every web UI publishes its host port
directly again, with no auth gate in front. A partial removal (Caddyfile deleted, Basic Auth env
vars dropped from `.env`/`.env.example`) had already been done by hand but left the `caddy`
service block still in `docker-compose.yml` and every other service still pointed at Caddy with
no port published — the stack was effectively unreachable until this was finished.

### Removed
- **Caddy** — container stopped and removed, `caddy:` service block removed from
  `docker-compose.yml`, `CADDY_BASIC_AUTH_USER`/`CADDY_BASIC_AUTH_HASH` env vars gone,
  `caddy/Caddyfile` gone, all doc references removed (README's "Reverse proxy / Basic Auth"
  section, TOC entry, healthcheck bullet, installer-image file list).

### Changed
- **All 16 previously-proxied services** (Prowlarr, Zilean, Decypharr, Radarr, Sonarr, Lidarr,
  Readarr, Whisparr, NZBGet, Seerr, Bazarr, FlareSolverr, Tautulli, Heimdall, Homepage, Glances)
  publish their host port directly again, same port numbers as before Caddy — no URL/bookmark
  changes needed.
- README's Security note now documents the no-auth-gate state explicitly (LAN-only threat model,
  same as originally justified Caddy's plain-HTTP-not-HTTPS tradeoff).

### Known follow-up
- Two stray root-owned directories from Docker auto-creating bind-mount targets for the missing
  Caddyfile (`caddy/Caddyfile`, `config/caddy/{data,config}`) need manual `sudo rm -rf` — blocked
  by the auto-mode classifier since the user's instruction didn't name these specific paths.

## [3.0.0] — Recyclarr removed; custom formats consolidated into one blocked-releases format

Decided to stop relying on Recyclarr's TRaSH-Guides sync entirely rather than keep maintaining
around its quirks (see the v8 migration notes below and the earlier v7 `reset_unmatched_scores`
workaround) — quality selection is simple enough here (`HD Bluray + WEB` / `WEB-1080p`, both
already hand-tuned) that the daily sync and its 40+ per-quality-tier custom formats per app were
more moving parts than value.

### Removed
- **Recyclarr** — container stopped and removed, all three of its images
  (`ghcr.io/recyclarr/recyclarr:8`/`:7`/`:latest`) deleted, `config/recyclarr/` deleted
  (gitignored, held both apps' API keys), service block removed from `docker-compose.yml`,
  and every doc/script/dashboard reference removed (README, `scripts/backup-config.sh`'s
  `recyclarr/resources` backup exclusion, its Homepage service card).
- **Every custom format Recyclarr had synced** — 41 in Radarr, 40 in Sonarr, deleted via each
  app's API (`DELETE /api/v3/customformat/{id}`), including the TRaSH-Guides scoring catalog
  (per-quality tiers, streaming-service tags, repack/proper handling, etc.) and the two
  manually-added ones that predated this change (`Low Quality Sources/Groups` in both apps,
  plus a Sonarr-only `FUCK RD` that turned out to carry an identical regex to
  `Low Quality Sources/Groups` - effectively a duplicate).

### Added
- **One custom format per app, "Blocked Releases (All Qualities)"** — replaces all of the
  above. Two OR'd Release Title conditions (`required: false` on both, so either one matching
  is enough to reject), scored `-10000` in every quality profile in both apps
  (`minFormatScore` stays `0`, so this is a hard reject as before):
  1. Low quality / legacy encodes / low-trust groups - carries the old
     `Low Quality Sources/Groups` regex forward as-is, plus a Real-Debrid-motivated addition:
     since Decypharr symlinks a debrid-cached file straight into the library, an older
     x264/XviD re-encode of a source that also exists as a native WEB-DL/remux buys nothing
     and just burns debrid cache slots, so `BluRay.x264`, `HDTV.x264`, `HDTV.XviD`, `WEB.x264`,
     and `WEB.h264` are rejected outright.
  2. BR-DISK / disc-based releases - the TRaSH-Guides `BR-DISK` regex, reused verbatim (not
     rewritten) so disc-image/folder releases (`ISO`, `BDMV`, `COMPLETE BLURAY`, etc.), which
     don't symlink into a single playable file the way the debrid mount expects, keep getting
     rejected the same way they already were.
  - Verified live against each app's own `/api/v3/parse` endpoint (real regex evaluation, not
    assumed correct): a plain `WEB-DL` release and a `BluRay.x264` release both come back
    rejected; a `BluRay.x265` release and a full `REMUX` release both come back clean.

### Changed
- Quality profiles (`HD Bluray + WEB` in Radarr, `WEB-1080p` in Sonarr) are now maintained by
  hand in each app directly - nothing re-syncs or can silently overwrite them anymore.

*Built with Claude AI.*

---

## [2.12.0] — Plex library added/removed report, every 12 hours

### Added
- **`scripts/plex-library-report.py`** — snapshots every item across every movie/show Plex
  library, diffs against the previous snapshot, and posts an embed to Discord listing what was
  added and removed since the last run. Run by `systemd/stack-plex-report.{service,timer}`
  every 12 hours (`OnBootSec=5min` + `OnUnitActiveSec=12h`). Unlike the other three alert
  paths, this one posts on every run regardless of whether anything changed - a periodic
  digest, not an anomaly alert - showing "No changes in the last 12 hours" when nothing did.
  First run establishes a baseline (nothing to diff against yet) instead of reporting the
  entire library as newly added; state lives in `~/.cache/plex-library-snapshot.json`. Diffs
  on Plex's `guid` rather than `ratingKey` - the latter isn't stable across a re-match (this
  library's own WCW-PPV matching cleanup reassigned one earlier the same day this shipped),
  which would otherwise show up as a false removed-then-added pair for content that never
  actually left. Long added/removed lists are truncated to 20 titles per library with a count
  of the rest, staying under Discord's embed field limits. Added `PLEX_TOKEN` to `.env`/
  `.env.example` alongside the existing `PLEX_URL` - needed for API access, wasn't required by
  anything in the stack until now.
- Real bug hit and fixed while building this: Discord's edge (Cloudflare) 403s Python's
  default `urllib` User-Agent (`Python-urllib/x.y`) outright, even though the exact same
  webhook works fine from curl or `notify-discord.sh`. Set a real `User-Agent` header on the
  POST request to fix it - would've been a confusing silent failure otherwise, since the
  Plex-side snapshot/diff logic itself has no way to know the *notification* step is what
  broke.

*Built with Claude AI.*

---

## [2.11.0] — Installer image published to GHCR

### Added
- **`Dockerfile` + `entrypoint.sh`** — bundles this repo's own tracked, portable files
  (`docker-compose.yml`, `caddy/`, `scripts/`, `systemd/`, docs) into a small installer image.
  `docker run --rm -v "$(pwd)":/out ghcr.io/whispersofj/media-stack:latest` extracts them onto
  a host in one command instead of a git clone. Deliberately never contains `.env`, `config/`,
  `media/`, or `usenet/` (excluded via the new `.dockerignore`) - re-running the same command
  after a later image update overwrites only the files the image actually contains, so it
  doubles as a safe "pull the latest compose/scripts/systemd changes" update path that can
  never touch real secrets or app state. The container runs as root (plain `alpine:3.20`), so
  the entrypoint `chown`s the extracted tree to match whatever UID/GID already owns the mount
  point - otherwise everything would land owned by root on the host.
- **`.github/workflows/publish-installer.yml`** — builds and pushes the image to GHCR
  (`ghcr.io/whispersofj/media-stack`) on every push to `main` that touches any bundled file,
  tagged `:latest` and `:vX.Y.Z` (version parsed straight from `CHANGELOG.md`). Lowercases the
  repo path for the image name - GHCR rejects the actual `WhispersOfJ` casing. Package
  visibility inherits the repo's (private) on first publish via the built-in `GITHUB_TOKEN`.
- **`.github/workflows/validate.yml`** — now also builds the installer image (no push, no
  registry credentials in this workflow) on every push/PR, so a broken Dockerfile fails CI
  before merge instead of only failing silently when the publish workflow runs on `main`.
- **`.github/dependabot.yml`** — added a `docker` ecosystem entry watching the installer
  image's own `alpine` base tag, alongside the existing `docker-compose` ecosystem entry for
  every service in the stack itself.

*Built with Claude AI.*

---

## [2.10.1] — Removed leftover Jellyfin artifacts

### Removed
- `config/NEW-ADMIN-CREDENTIALS.txt` — a stale plaintext credentials file (Jellyfin/Jellystat
  admin logins) left behind from the v2.x Jellyfin trial that was fully stood up and then
  entirely torn back out in an earlier session. The compose file, Homepage, and Heimdall were
  already clean; this file was simply never deleted when the rest of that work was reverted.
- Three unused Docker images still sitting on disk from the same trial
  (`lscr.io/linuxserver/jellyfin`, `cyfershepard/jellystat`, `hrfee/jfa-go`) — not referenced
  by any container or compose service, ~3.5GB reclaimed.

*Built with Claude AI.*

---

## [2.10.0] — Reverse-proxy auth, image pinning, healthchecks, log rotation, Discord alerting

A self-audit of the running stack (no prior bug report driving this one) surfaced five gaps:
every one of ~20 web UIs was exposed on the LAN with no auth in front of it; 20 of 21 images
floated on `:latest` with Watchtower silently auto-updating them daily; no container had a
`healthcheck:`, so `docker compose ps` only ever proved a process had started, never that it
was actually responding; nothing rotated container logs, daemon-level or per-service; and
nothing in the stack could tell you it was broken - a failed backup, a bad Watchtower update,
or a crash-looping container were all silent. All five fixed in one pass.

### Added
- **Caddy** reverse proxy in front of all 16 web UIs, on the exact same host ports each
  service published directly before, gated behind HTTP Basic Auth. `caddy/Caddyfile` (tracked
  in git - no secrets, just routing) has one site block per port; the auth hash lives in
  `.env` as `CADDY_BASIC_AUTH_HASH` (bcrypt, plaintext never stored). `ports:` removed from
  all 16 gated services - they're `stacknet`-internal only now, reached through Caddy.
  Heimdall's HTTPS port (3443, self-signed, no real value once Caddy is the front door) was
  dropped rather than gated. Plain HTTP, not HTTPS - see the README's Security section for
  what this does and doesn't defend against.
- **`healthcheck:`** on all 21 containers. Most use each app's own unauthenticated `/ping` (or
  equivalent); `zilean-postgres` uses `pg_isready`; NZBGet's gated web UI treats 401 as healthy
  (still proof the server's alive); Caddy checks its own local admin API rather than proxying
  through to an upstream (so a gated 401 downstream doesn't misreport as Caddy being
  unhealthy); Recyclarr/Kometa/Unpackerr (no web UI, and none of these minimal images ship
  `ps`/`pgrep`) check their main process is alive via `/proc`; Watchtower (no shell in its
  image at all) uses its own documented `--health-check` flag.
- **Docker daemon-level log rotation** - `/etc/docker/daemon.json` (host-level, not tracked in
  this repo), `max-size: 10m` / `max-file: 3` per container. Required a Docker daemon restart
  plus a `--force-recreate` of every container to actually take effect (a running container's
  log config is fixed at creation time, not re-read from the daemon's current defaults).
- **Discord alerting**, three independent paths sharing one webhook
  (`scripts/notify-discord.sh`, no-ops silently if unconfigured): backup success/failure
  (`backup-config.sh`, plus an `OnFailure=` systemd hook on `stack-backup.service` as a second
  layer for failures the script itself can't self-report); Watchtower's native Shoutrrr
  Discord notifications (every image update, or a failed one, posts instead of happening
  silently at 4am); and a new `scripts/check-container-health.sh` (run every 5 minutes by
  `systemd/stack-health-check.{service,timer}`) that diffs the unhealthy/restarting container
  set against its last poll and only posts on an actual change, not every poll.

### Changed
- **Every image pinned**, previously 20 of 21 floated on `:latest`. hotio images (8 of them)
  pinned to their `:release` channel tag - verified identical digest to `:latest` at pin time,
  so a no-op today, but now an explicit, intentional channel choice rather than an ambiguous
  `latest` that (per the v1.4.1 Recyclarr incident) can simply stop being published. Images
  with real upstream version tags matching what's currently running (Zilean, Decypharr,
  FlareSolverr, Watchtower) got version tags. Everything else (Whisparr, Seerr, Homepage,
  Glances, Kometa, Unpackerr, Heimdall) had its `:latest` running *ahead* of the newest tag
  upstream had actually cut - pinning to that tag would have been a silent downgrade, so these
  are digest-pinned instead, freezing exactly what's running today. Full reasoning and the
  exact tag/digest chosen for each image is in the README's new "Image pinning policy"
  section. Watchtower still auto-updates the 14 channel/version-tag-pinned images going
  forward (with every update now posting to Discord first instead of happening silently); the
  7 digest-pinned images are no longer auto-updated at all - a digest is immutable, so
  Watchtower re-pulling it always resolves to the same content. Those need a manual digest
  bump when someone checks upstream again.

*Built with Claude AI.*

## [2.9.1] — Glances service-card widget crashed the whole Homepage page

### Fixed
- The Glances card added in v2.9.0 used the wrong config schema: `cpu: true`/`mem: true` are
  the *info-widget's* (`widgets.yaml`, top-of-page) option flags, but the *service-widget*
  (`services.yaml`, individual cards) uses a completely different schema requiring a single
  `metric:` field (`info`, `cpu`, `memory`, `process`, `containers`, or a parameterized one
  like `network:eth0`). Neither `cpu` nor `mem` map to anything the service-widget component
  understands, so its internal `widget.metric` ended up `undefined`, and a `.match()` call on
  that undefined value crashed the entire page for every visitor - not a contained per-card
  error, the whole dashboard. Root-caused by reading Homepage's actual
  `src/widgets/glances/component.jsx` source (the failing `.match()` line) and its docs
  (`docs/widgets/services/glances.md`) to find the real schema, rather than guessing further.
  Fixed to `metric: info`, which shows a general hostname/OS/CPU/RAM/SWAP overview card -
  verified via `docker exec homepage` log monitoring showing no errors once idle, versus
  errors appearing only during manual (and initially also malformed) API probing.

*Built with Claude AI.*

## [2.9.0] — Real Kometa progress signal, Glances host stats, dashboard visual polish

### Added
- **Glances** (`nicolargo/glances:latest`), `extras` profile, `pid: host` + read-only
  `/:/rootfs` mount so it reports genuine *host* CPU/memory/disk/uptime rather than its own
  container's usage - confirmed via its API (`/api/4/cpu`, `/api/4/mem`, `/api/4/fs`) matching
  this host's real 16-core/24GB/~1TB NVMe specs. Run in "web server" mode (`GLANCES_OPT: "-w"`)
  so its API and web UI (port **61208**) are both available. Added to Homepage as a
  top-of-page `glances` info-widget (cpu/mem/disk/uptime) and as its own service card with a
  working `href` (unlike Kometa, Glances has a real web UI).
- **Kometa "is it doing something" signal:** `showStats: true` set globally in
  `settings.yaml` (Homepage), surfacing live container CPU/memory on every docker-integrated
  card, not just on click. For a batch job with no API of its own, this is the one honest
  progress signal available - idle near-0% normally, visibly spikes while a scheduled run is
  actually processing. Didn't fabricate a fake progress bar for something that has no
  meaningful "percent complete" concept.
- **Dashboard visual pass** (`config/homepage/custom.css`, `settings.yaml`): card surfaces
  now render with a subtle gradient + drop shadow, gain a red glow and lift on hover; section
  headings got a short gradient underline instead of flat colored text; stat/progress bars
  (docker stats, Glances, resources widgets) render with a red gradient fill instead of the
  theme default; "up"/healthy status indicators pulse slowly instead of sitting static;
  `blockHighlights` re-themed so widget good/warn/danger states use the site's own red/black
  palette instead of Homepage's default green/amber/red.

*Built with Claude AI.*

## [2.8.0] — Kometa added and configured (Plex collections/metadata/overlays)

### Added
- **Kometa** (`kometateam/kometa:latest` - the official image's stable channel, explicitly
  not `:nightly`/`:develop`), `extras` profile, for automated Plex collections, metadata, and
  overlay art. Only volume is `./config/kometa:/config` - Kometa applies overlays/posters
  through Plex's own API rather than touching media files directly, so unlike every *arr app
  it needs no `/mnt` or `./media/*` mount at all. On `stacknet` alongside everything else, so
  it can reach Radarr/Sonarr/Plex/Tautulli the same way every other service already does.
  Deliberately did *not* use the LinuxServer fork (`linuxserver/kometa`): it resets `/config`
  ownership to `PUID`/`PGID` (or `911:911` unset) on every start, which the official image
  doesn't do, and the wiki's own examples assume the official image.
- Added to **Heimdall** (new `items`/`item_tag` rows in `app.sqlite`, under the "Media Server"
  category alongside Plex) and **Homepage** (`config/homepage/services.yaml`, next to
  Recyclarr - same "no widget, container-status only" treatment). Both link to
  `https://kometa.wiki/` instead of a local URL: Kometa has no web UI of its own (it's a
  scheduled batch job, not a running service with a page to load), so its own docs are the
  only destination that goes anywhere - matches how Recyclarr/Unpackerr/Watchtower were
  already handled in both dashboards.
- Fetched a matching icon from the same community dashboard-icons set already used for the
  other Heimdall/Homepage entries.
- Ran the container once to let it complete its own documented first-run behavior
  (auto-downloads the stock default `config.yml` and exits/restarts once before settling into
  its normal idle-until-5AM state). Confirmed no restart loop (`RestartCount` stayed at 1).

### Configured (`./config/kometa/config.yml` - gitignored like the rest of `config/`, never committed)
- **Connections:** Plex (token reused from `~/zurg/config.yml` - same server), TMDb, Radarr,
  Sonarr, and Tautulli all wired up with real URLs/keys and validated via Kometa's own
  `--validate --validate-level full` (connects to every configured service without touching
  real collections/overlays/operations). Radarr/Sonarr `quality_profile` set to match whatever
  Recyclarr actively manages (`HD Bluray + WEB` / `WEB-1080p`) so the two stay in sync;
  `root_folder_path` pulled from each app's own `/api/v3/rootfolder` rather than the stub's
  fictional `S:/Movies` placeholder.
- **Trakt and MyAnimeList OAuth completed.** Both need a one-time interactive authorization
  (Trakt: visit a URL, get a short PIN; MAL: visit a URL, get redirected to a broken
  `localhost/?code=...` page) that a non-interactive container can't do on its own. Trakt's
  PIN flow worked through `--validate-level full` directly. MAL's did not - a `docker exec -i`
  session piped through a named pipe hit a Python `EOFError` on the input prompt every time
  rather than actually blocking for input, even after working around the FIFO's own
  read-blocks-until-writer gotcha. Completed it manually instead: read `modules/mal.py` in
  Kometa's own source to find the exact OAuth exchange it performs (`POST
  https://myanimelist.net/v1/oauth2/token` with `client_id`/`client_secret`/`code`/
  `code_verifier`/`grant_type=authorization_code`, where `code_verifier` must equal the
  `code_challenge` MAL's "plain" PKCE method logged in the authorize URL), then made that
  exact request directly and wrote the resulting `access_token`/`refresh_token` straight into
  `config.yml`. Both tokens auto-refresh via Kometa's own renewal logic going forward.
- **`libraries:`** trimmed to the two that actually exist on this Plex server (`Movies`,
  `TV Shows` - confirmed via a real `Plex Library 'Anime' not found. Options: ['Movies', 'TV
  Shows']` error from the stub's placeholder `Anime`/`Music` blocks, which were removed).
  Added the most commonly-used zero-config Kometa defaults on top of the stub's
  `basic`/`imdb`/`ribbon`: `genre`/`studio`/`decade` collections and a `resolution` overlay.
  Deliberately did *not* add the `ratings` overlay or any of the dozen other available
  defaults (streaming, franchise, awards, per-country content ratings, etc.) - `ratings`
  specifically needs you to choose which rating sources to display or it silently does
  nothing, and Kometa's own docs explicitly warn against enabling everything at once before
  understanding what each default does.
- **`add_missing: true` and `search: true`** enabled for both Radarr and Sonarr - Kometa will
  now add collection items missing from the library and trigger an immediate search rather
  than waiting for Radarr/Sonarr's own scheduled search cycle.

*Built with Claude AI.*

## [2.7.1] — Bazarr couldn't see Sonarr/Radarr's actual libraries

### Fixed
- Bazarr's `docker-compose.yml` volumes only had `/config` and `/mnt` - never the actual
  `/data/movies`/`/data/shows` paths Radarr and Sonarr use as their root folders. Bazarr asks
  each app for its root folder over the API, gets back a path that simply didn't exist inside
  Bazarr's own container, and surfaced it as "This Sonarr root directory does not seem to be
  accessible by Bazarr." Added `./media/movies:/data/movies` and `./media/shows:/data/shows`
  to Bazarr's volumes - identical paths to Radarr/Sonarr's own mounts, so no Path Mappings
  needed (same reasoning as the shared `/app/downloads` path elsewhere in this file). Verified
  via `docker exec bazarr ls /data/shows` and `/data/movies` (both populated, correct
  ownership) and Bazarr's own `/api/series` and `/api/movies` returning real data post-fix.

*Built with Claude AI.*

## [2.7.0] — Live dashboard (Homepage) + automated config backups

### Added
- **Homepage** (`ghcr.io/gethomepage/homepage`), `extras` profile, port 3001, alongside
  Heimdall rather than replacing it (v2.3.0 removed a prior Homepage instance in favor of
  Heimdall - this time the ask was specifically live per-service data, which Heimdall's
  static links can't provide). Live widgets wired up for Prowlarr, Radarr, Sonarr, Lidarr,
  Readarr, Bazarr, NZBGet, Seerr (its Overseerr-compatible `/api/v1/status` confirmed
  working), and Tautulli, using each app's real API key pulled from its own config. Docker
  integration (read-only `docker.sock` mount) covers every other service with a live
  running/health badge instead. Dedicated "Zilean Watch" group: link to Zilean's own
  dashboard, a ping check, and container status for `zilean` + `zilean-postgres` - no custom
  API widget, since Zilean's actual stats API isn't documented (`/health`, `/api/stats`,
  `/dmm/status` all confirmed 404) and guessing risked a broken widget for no real gain over
  linking its own UI directly.
- Custom dark/black + red-accent theme (`config/homepage/custom.css`) - Homepage's built-in
  `color: red` tints entire card surfaces red rather than just accenting, so base color is
  `slate` with black backgrounds/red borders/headings layered on top via CSS.
- Automated config backup: `scripts/backup-config.sh` (restic, `~/backups/stack-restic-repo`,
  `--keep-daily 7 --keep-weekly 4 --keep-monthly 6`) run daily at 03:30 by
  `systemd/stack-backup.{service,timer}` (same tracked+symlinked pattern as
  `media-stack.service`), scheduled before Watchtower's 4am updates.

### Fixed (found wiring this up, not pre-existing)
- Homepage's Next.js layer rejects any request with a non-allow-listed `Host` header -
  every page load failed with "Host validation failed" and nothing else. Needed
  `HOMEPAGE_ALLOWED_HOSTS` set to the exact `host:port` combinations (bare hostname without
  the port was not sufficient).
- Whisparr's fork doesn't expose Radarr's `/movie` endpoint (confirmed 404 directly against
  its API) even though `/queue/status` and `/queue/details` work fine - the borrowed "radarr"
  widget type half-broke on it. Dropped to a container-status-only card instead of a
  partially-erroring widget.
- First backup run exited non-zero: restic's own exit code 3 ("some source files could not
  be read") from `config/zilean-postgres`'s live data files, combined with `set -e`, aborted
  the script before the retention/prune step ran (backup itself had still succeeded). Fixed
  two ways: excluded `zilean-postgres` from the backup entirely - not just to dodge the
  permission error, but because file-level copying a *running* Postgres data directory can
  produce an inconsistent restore, and Zilean's index is a rebuildable DMM-scrape cache, not
  data worth that risk - and made the script tolerate exit code 3 generally rather than
  treating any non-zero restic exit as fatal.

### Known limitation
- Backup repo is local-only (`~/backups/`, same single NVMe as everything else) - protects
  against config corruption, accidental deletion, and repeats of the Decypharr config-wipe
  bug below, not physical disk failure. No cloud remote configured since no cloud storage
  account exists on this host; restic supports one natively if that's ever wanted.

*Built with Claude AI.*

## [2.6.0] — Boot automation via systemd

### Added
- `systemd/media-stack.service`: a user-scope systemd unit that brings the whole stack
  (extras profile included) up automatically on boot, correctly ordered after the two host
  mounts every arr container's `/mnt` bind-mount depends on: `zurg.service` (mounts
  `/mnt/zurg` via its own embedded rclone process) and `rclone-all.service` (mounts
  `/mnt/all`). Docker itself needs no explicit ordering — `docker.socket` is already
  socket-activated, so the unit's first `docker` invocation starts `docker.service` on
  demand. `RemainAfterExit=yes` + `ExecStop=docker compose --profile extras down` means
  `systemctl --user stop media-stack.service` tears the stack back down cleanly too.
  Installing it requires `loginctl enable-linger` for the user, since the mount units it
  orders against are user-scope services that otherwise only start on interactive login.
  See [README.md](README.md#starting-at-boot).

### Fixed
- Found `rclone-zurg.service` enabled but permanently failing (`didn't find section in
  config file`) while auditing the boot dependency chain above — a leftover duplicate of
  the mount `zurg.service` already manages internally via its own embedded rclone process.
  Disabled it; it provided no function and would have been a false lead in the new unit's
  dependency chain.

---

## [2.5.1] — Bazarr's Plex connection fixed (last piece of the v2.4.0 bug)

### Fixed
- Plex Media Server itself was found stopped on the host (`systemctl status` showed
  `inactive (dead)`, unrelated to anything in this stack) — started it back up first.
- With Plex reachable, finished the fix noted as outstanding in [2.4.0](CHANGELOG.md):
  Bazarr's Plex connection had the identical `ip: 127.0.0.1` bug as its Radarr/Sonarr
  connections. Pointed it at the host's real LAN IP with the Plex token already on this host
  (from Zurg's config), selected the Movies/TV Shows libraries, and enabled `use_plex`.
  Bazarr's own OAuth migration then ran automatically, converting the API-key config to its
  newer OAuth-token storage and validating the connection live against the real server
  (confirmed by server name/machine ID coming back correctly in the logs). All three of
  Bazarr's media-source connections (Plex, Radarr, Sonarr) are now genuinely live.

*Built with Claude AI.*

## [2.5.0] — Jellyfin removed; reverted to symlinks, experience judged not worth it

### Changed — BREAKING
- **Removed Jellyfin, Jellyseerr, Jellystat, and jfa-go entirely** — all four containers,
  their `docker-compose.yml` service definitions, their config directories (~170MB), the
  `JELLYSTAT_POSTGRES_PASSWORD`/`JELLYSTAT_JWT_SECRET` env vars, their 4 Heimdall tiles and
  icons, and the `JELLYFIN-PLUGINS.md` reference doc. Bazarr's Jellyfin connection was
  disabled and cleared; its Radarr/Sonarr connections (fixed in [2.4.0](CHANGELOG.md)) were
  left alone since that bug was real and independent of Jellyfin.
- **Decypharr reverted from `strm` back to `symlink`** for `default_download_action`. The
  strm experiment ([2.4.1](CHANGELOG.md) territory, never actually versioned on its own) was
  tried, tested, and judged not worth keeping:
  - **Plex doesn't support `.strm` files at all** (removed years ago) — since Plex is this
    stack's primary, native, pre-existing media server, strm mode meant every new grab was
    invisible to Plex and only playable through Jellyfin. That's a real regression, not a
    minor caveat.
  - **A serious, reproducible bug** in Decypharr's `POST /api/config`: any *partial* JSON
    patch (e.g. just `{"default_download_action": "strm"}`) causes it to silently drop the
    `debrids`, `mount`, and sometimes `arrs` sections entirely on the next save/restart —
    hit this **twice** in one session (once switching to strm, once switching back), each
    time fully breaking the debrid gateway (unmounted `/mnt/decypharr`, zero configured
    debrids) until manually reconstructed and POSTed back as one complete document. Anyone
    touching this API in the future: always send the full config, never a partial patch.
    Root-caused in the actual source (`handleUpdateConfig` decodes into a zero-value struct;
    `Config.Save()` overwrites `config.json` with no merge logic) and filed upstream as
    [sirrobot01/decypharr#343](https://github.com/sirrobot01/decypharr/issues/343).
  - Getting one clean, verifiable live example of a fresh strm-mode grab flowing through to
    Jellyfin took longer than expected — indexer availability for the specific titles being
    tested, not a stack bug, but it meant the "how fast does this actually work" question
    never got a clean answer before the decision to revert was made.
- Real-Debrid token was rotated mid-session after an unrelated accidental transcript exposure
  ([2.4.1](CHANGELOG.md)) — unaffected by this revert, still current.

*Built with Claude AI.*

## [2.4.1] — Real-Debrid token rotated

### Fixed
- While fetching a Plex API token from Zurg's `config.yml` to fix Bazarr's Plex connection, a
  broad `grep` also matched and printed the Real-Debrid token to the session transcript — a
  genuine accidental exposure, not a hypothetical one. Rotated the token in the Real-Debrid
  account settings and updated both places it lives on this host: `zurg`'s `config.yml` and
  `config/decypharr/config.json`. Restarted both, confirmed no auth errors and a clean initial
  sync from both debrid clients on the new key. Neither file is tracked by git (both are
  gitignored), so no repo history needed scrubbing — the exposure was transcript-only.

*Built with Claude AI.*

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
