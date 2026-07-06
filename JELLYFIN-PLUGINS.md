# Jellyfin plugins — preinstall reference

Research for the planned Jellyfin work in [TODO.md](TODO.md). Not installed yet — this is
the shortlist to pull from once that work starts.

## Yes, plugins can be preinstalled

Jellyfin loads a plugin by scanning its data directory's `plugins/` folder at startup for
subfolders containing a `meta.json` + the plugin's `.dll`(s). That's the same thing the web
UI's "Install" button does under the hood — it just downloads a release zip and extracts it
there. So a plugin can be **fully preinstalled with no UI click-through** by doing that
extraction ourselves before the container's first start:

1. Pre-seed `config/jellyfin/data/plugins/repositories.json` with the repo URLs below, so
   they show up in the catalog even if we ever do want the UI.
2. For each plugin we want live from boot: resolve its manifest.json, find the entry
   matching our Jellyfin version's `targetAbi`, download that version's zip, and extract it
   to `config/jellyfin/data/plugins/<Name>_<Version>/` (the zip already contains the right
   `meta.json`).
3. Start the container — Jellyfin lists them as already installed, no catalog step needed.

Versions/checksums in each manifest.json change on every release, so step 2 gets scripted
against whatever's current at install time rather than hardcoded now — this file only
records *which* plugins and *which repo* to pull from.

## Official catalog (built in, no repository URL needed)

| # | Plugin | Category | Why it's on the list for this stack |
|---|---|---|---|
| 1 | Open Subtitles | Subtitles | Native subtitle search inside Jellyfin's own UI; overlaps with Bazarr somewhat — evaluate whether we still want both once Bazarr is pointed at Jellyfin per the TODO |
| 2 | Fanart | MoviesAndShows | Extra backdrops/logos/clearart beyond default TMDb art |
| 3 | TMDb Box Sets | MoviesAndShows | Auto-creates movie collections, mirrors what Recyclarr/TRaSH already assumes on the Radarr side |
| 4 | TheTVDB | MoviesAndShows | Second TV metadata source alongside TMDb, useful for shows TMDb handles poorly |
| 5 | Trakt | General | Watch-history sync/backup, works across both Plex and Jellyfin so history isn't siloed |
| 6 | Playback Reporting | Administration | Per-user/device watch stats — closest official equivalent to Tautulli until Jellystat lands |
| 7 | Reports | Administration | Scheduled library/activity reports |
| 8 | Webhook | Administration | Push library/playback events out — can feed the same Discord channel as `jellyfin-rpc` |
| 9 | Session Cleaner | Administration | Clears stuck/ghost playback sessions, cheap to run |
| 10 | Local Intros | MoviesAndShows | Official pre-roll/intro-skip mechanism if fingerprinting (Intro Skipper) turns out to be overkill |
| 11 | Chapter Segments Provider | General | Chapter-based thumbnails in the seek bar |
| 12 | Subtitle Extract | Subtitles | Pulls embedded subs out to sidecar files, makes them visible to other tools in the stack |
| 13 | Cover Art Archive | Music | Album art for Lidarr's library |
| 14 | LrcLib Lyrics | Music | Synced lyrics for Lidarr's library |
| 15 | Bookshelf | Books | In-app ebook reading for Readarr's library |

## Community (add the repo, then install from catalog)

| # | Plugin | Why it's on the list for this stack | Repository (manifest.json) |
|---|---|---|---|
| 16 | Intro Skipper | Most-installed community plugin — audio-fingerprint intro/credits skip, works without chapter markers | `https://raw.githubusercontent.com/intro-skipper/intro-skipper/master/manifest.json` |
| 17 | Jellyscrub | Scrub-bar preview thumbnails; check whether our Jellyfin version's native trickplay (10.9+) already covers this before installing | `https://raw.githubusercontent.com/nicknsy/jellyscrub/main/manifest.json` |
| 18 | Merge Versions | Dedupes multiple quality copies of the same movie/episode into one entry — likely to matter here since Decypharr/NZBGet can both land a title | `https://raw.githubusercontent.com/danieladov/JellyfinPluginManifest/master/manifest.json` |
| 19 | Skin Manager | Theme installer (same repo as Merge Versions, no extra repo needed) | `https://raw.githubusercontent.com/danieladov/JellyfinPluginManifest/master/manifest.json` |
| 20 | Home Sections | "Netflix-style" dynamic home screen rows | `https://www.iamparadox.dev/jellyfin/plugins/manifest.json` |
| 21 | Media Bar | Featured-content hero bar on the home screen (same repo as Home Sections) | `https://www.iamparadox.dev/jellyfin/plugins/manifest.json` |
| 22 | Collection Sections | Home-screen row for curated collections/playlists (same repo) | `https://www.iamparadox.dev/jellyfin/plugins/manifest.json` |
| 23 | Jellyfin-Enhanced | QoL bundle: keyboard shortcuts, subtitle styling, TMDB reviews in the client | `https://raw.githubusercontent.com/n00bcodr/Jellyfin-Enhanced/main/manifest.json` (confirm path at install time) |
| 24 | jellyfin-rpc (Radiicall/JustRadical fork) | Discord Rich Presence — shows "watching X" | `https://github.com/JustRadical/jellyfin-rpc` (check repo for manifest.json path) |
| 25 | Plexyfin | Syncs artwork/collections from the existing native Plex library into Jellyfin — directly useful since Plex stays primary and Jellyfin runs alongside it per the TODO | `https://github.com/cleverdevil/plexyfin` (check repo for manifest.json path) |
| 26 | Jellyfin Security | TOTP/2FA, passkeys, OIDC/SSO, audit logging | `https://github.com/ZL154/JellyfinSecurity` (check repo for manifest.json path) |
| 27 | Media Cleaner | Auto-removes already-watched media after a set time — worth it given NZBGet's fallback path uses real local disk, unlike the debrid-symlink majority of the stack | `https://github.com/shemanaev/jellyfin-plugin-media-cleaner` (check repo for manifest.json path) |
| 28 | Jellyfin Ignore | Skips filename patterns during library scans — useful for ignoring in-progress Decypharr/NZBGet staging files | `https://github.com/fdett/jellyfin-ignore/` (check repo for manifest.json path) |
| 29 | ThePornDB | Metadata provider for adult content — this stack already runs Whisparr, and general "top Jellyfin plugins" lists never cover this library type | `https://github.com/ThePornDatabase/Jellyfin.Plugin.ThePornDB` (check repo for manifest.json path) |
| 30 | Auto Collections | Builds dynamic collections from rules (genre, studio, actor, etc.) — useful once the library has grown past what TMDb Box Sets covers | `https://github.com/KeksBombe/jellyfin-plugin-auto-collections` (check repo for manifest.json path) |

Entries marked "check repo for manifest.json path" had a confirmed GitHub repo but no
manifest URL surfaced during research — that's a two-minute look at the repo's README
when we actually script the install, not a blocker to this list.

## Sources

- [Official Jellyfin plugin manifest](https://repo.jellyfin.org/files/plugin/manifest.json) — the 34-entry catalog list #1-15 is drawn from
- [Jellyfin docs: Plugins](https://jellyfin.org/docs/general/server/plugins/)
- [awesome-jellyfin](https://github.com/awesome-jellyfin/awesome-jellyfin) — community plugin/theme index
- [JellyWatch: 7 Must-Have Jellyfin Plugins (2026)](https://jellywatch.app/blog/jellyfin-intro-skipper-chapters-plugins-quality-of-life-2026)
- [XDA: plugins I install first when setting up a new Jellyfin server](https://www.xda-developers.com/plugins-i-install-first-when-setting-up-a-new-jellyfin-server/)
- [ytechb: 10 Best Jellyfin Plugins 2026](https://www.ytechb.com/best-jellyfin-plugins/)
- [danieladov/JellyfinPluginManifest](https://github.com/danieladov/JellyfinPluginManifest)
