---
name: stack-cli-plex-kometa
description: Exact fish CLI command reference for Plex, Kometa, and Tautulli operations against this stack's Control Panel (library scan/maintenance, Kometa runs, watch sessions/history, duplicates, TMDb-link audit). Use whenever the user asks to run Kometa, scan Plex, check who's watching, find duplicate files, or check for a Plex update from the terminal. Trigger phrases: "run kometa", "scan plex", "who's watching", "empty plex trash", "find duplicate movies", "check plex update", "what's missing a tmdb link".
---

# Stack CLI: Plex & Kometa

<skill_scope skill="stack-cli-plex-kometa">
This is a command reference, not an operational tool: it exists so the exact fish function name, argument order, and output shape for every Plex/Kometa/Tautulli terminal command in this stack is already known, without reading `~/.config/fish/functions/stack-plex*.fish` fresh each time. Every command here is a thin fish wrapper around Control Panel's own HTTP API (`http://192.168.4.105:8420`); the actual behavior lives in `control-panel/app.py`.
</skill_scope>

## Calling convention

<calling_convention>
Most commands here `curl` their endpoint directly and pipe through an inline `python3 -c "..."` formatter that unwraps FastAPI's `{"detail": {...}}` shape if present, then prints `data['message']` followed by any list items. A few bare ones (`stack-plex-libraries`) go through the `__stack_api` helper instead and just print the raw `message`.

None of these read a `STACK_HOST_IP` environment variable - the Control Panel URL is a literal hardcoded string in every function.
</calling_convention>

## Command reference

<command_reference>
| Command | Args | What it does |
|---|---|---|
| `stack-kometa-run` | `[library ...]` (none = every library) | Triggers an immediate Kometa collections/metadata/overlays pass, bypassing its 05:00 schedule. Library names come from `stack-plex-libraries`. Kometa's container runs `sleep infinity` as PID 1 (load-bearing - see this repo's CLAUDE.md) and only ever actually runs via this on-demand exec path. |
| `stack-plex` | `<scan\|empty-trash\|optimize-db\|clean-bundles>` | One Plex maintenance action: `scan` refreshes every library section for new files, `empty-trash` permanently removes already-deleted items, `optimize-db` runs Plex's own DB optimization, `clean-bundles` removes metadata bundles Plex no longer needs. |
| `stack-plex-libraries` | none | Lists Plex library names - the input `stack-kometa-run` and `stack-plex-empty-trash` take. |
| `stack-plex-updates` | none | Checks whether Plex has a newer release on its current channel. Check only - this stack pins Plex's image deliberately and never auto-applies an update. |
| `stack-plex-empty-trash` | `[library name ...]` (none = every library) | Empty trash scoped to one or more named libraries (case-insensitive match against the Plex title, e.g. `"TV Shows"`) instead of everything. |
| `stack-plex-duplicates` | `[min_gb]` (default 5.0) | Flags movies whose combined file size looks like more than one real release stacked up (well beyond a single legitimate multi-version upgrade). Real incident: found ~700GB of redundant duplicate releases in one session this way. |
| `stack-plex-sessions` | none | Who's watching what right now - user, title, direct-play vs. transcode decision, progress, per session. |
| `stack-plex-recently-added` | `[limit]` (default 15) | What actually finished importing and became visible in Plex. Distinct from `stack-recently-added` (see the `stack-cli-arr-fleet` skill), which shows what was added *to Radarr/Sonarr's management*, not necessarily downloaded or visible yet. |
| `stack-tmdb-missing` | none | Scans every movie/show library for items with no TMDb link (neither the new nor legacy Plex agent's Guid) and writes them to `~/missing.txt`. Overwrites on every run - a rescan tool, not an appending log. |
| `stack-tautulli-history` | `[limit]` (default 10) | Recent Plex watch history via Tautulli - what actually got watched, as opposed to what's currently playing (`stack-plex-sessions`). |
</command_reference>

## Common mistakes

<common_mistakes>
<general_anti_patterns>
- **Confusing the two "recently added" commands.** `stack-recently-added <app>` (arr-fleet skill) is about management state in Radarr/Sonarr; `stack-plex-recently-added` is about what Plex itself has actually indexed and made playable. A title can show in one and not the other - that gap is itself diagnostic (added to management but not yet imported, or imported but Plex hasn't scanned yet).
- **Expecting `stack-tmdb-missing` to print results inline.** It writes to `~/missing.txt` and only prints a count - read that file for the actual list, don't assume the terminal output is complete.
- **Suggesting `stack-plex-updates` will apply an update.** It's read-only by design; this stack manually bumps Plex's pinned image tag rather than trusting Watchtower with it (see this repo's CLAUDE.md on image pinning policy).
</general_anti_patterns>
</common_mistakes>

## Resources

<resources>
**Local:**
- `~/.config/fish/functions/stack-plex*.fish`, `stack-kometa-run.fish`, `stack-tmdb-missing.fish`, `stack-tautulli-history.fish` - the actual fish source these commands wrap
- `control-panel/app.py` in this repo - the real behavior behind every endpoint these commands call
</resources>
