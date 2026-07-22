---
name: stack-cli-usenet-queue
description: Exact fish CLI command reference for NzbDAV, Cleanuparr, NeutArr, and Prowlarr status/queue operations against this stack's Control Panel. Use whenever the user asks about the Usenet download queue/history, Cleanuparr strikes, NeutArr hunting state, or Prowlarr indexer state from the terminal. Trigger phrases: "check the nzbdav queue", "nzbdav history", "cleanuparr strikes", "is neutarr connected", "prowlarr indexers".
---

# Stack CLI: Usenet & Queue Automation

<skill_scope skill="stack-cli-usenet-queue">
This is a command reference, not an operational tool: it exists so the exact fish function name, argument order, and output shape for every NzbDAV/Cleanuparr/NeutArr/Prowlarr terminal command in this stack is already known, without reading the fish source fresh each time. Every command here is a thin fish wrapper around Control Panel's own HTTP API (`http://192.168.4.105:8420`); the actual behavior lives in `control-panel/app.py`. Recyclarr (and its `stack-recyclarr-status` command) was removed entirely in v11.2.0. Maintainerr (and its `stack-maintainerr-rules` command, `/api/maintainerr/rules` route) was removed entirely, by explicit request (never used) - there is no Plex library lifecycle management in this stack.

**Related skill:** `usenet-orchestrator` is a different mechanism entirely - a standalone Python script that talks to NzbDAV's own SABnzbd-compatible API directly (not through Control Panel) and can retry/clear-failed items and diagnose a specific stuck-file-that-won't-stop-retrying via container log analysis. Reach for `usenet-orchestrator` for queue *mutation* (retry, clear-failed) or the stuck-file diagnostic; reach for the commands here for quick read-only status checks and NzbDAV's own connection settings.
</skill_scope>

## Calling convention

<calling_convention>
Some commands here (`stack-cleanuparr-instances`, `stack-neutarr-status`) go through the `__stack_api` helper and print a raw `message`. The rest `curl` their endpoint directly and pipe through an inline `python3 -c "..."` formatter that unwraps FastAPI's `{"detail": {...}}` shape if present, prints `data['message']`, then loops over the relevant list field with per-line formatting.

None of these read a `STACK_HOST_IP` environment variable - the Control Panel URL is a literal hardcoded string in every function.
</calling_convention>

## Command reference

<command_reference>
| Command | Args | What it does |
|---|---|---|
| `stack-nzbdav-queue` | none | NzbDAV's current Usenet download queue - category, name, status, percentage, MB left while downloading. |
| `stack-nzbdav-history` | `[limit]` (default 20) | Recent completed/failed downloads, with the failure message if one failed. |
| `stack-nzbdav-set-connections` | `<max-connections>` (integer) | Sets `MaxConnections` on every configured Usenet provider in NzbDAV's own Settings → Usenet. NzbDAV has no static API key for this specific setting - Control Panel logs in with `NZBDAV_ADMIN_USER`/`PASSWORD` on each call. |
| `stack-nzbdav-stats` | none | Aggregate queue/history counts - a summary instead of the raw dumps `stack-nzbdav-queue`/`stack-nzbdav-history` give. |
| `stack-nzbdav-delete-failures` | none | Deletes every "Failed" entry from NzbDAV's history right now. On-demand version of the `stack-nzbdav-prune-history.timer` job that already runs this every 4h - useful because a Failed row blocks re-grabbing an NZB with a matching release name ("Duplicate nzb" error) even when nothing exists on disk for it. |
| `stack-nzbdav-unstick` | none | Restarts NzbDAV if its own `mode=history` query is hanging - probes first, only restarts if actually stuck. Fixes the chain where a hung history query makes Sonarr's client-status poll time out, Sonarr marks the download client unavailable, then re-grabs releases already active in the queue and those re-grabs 500. Safe to run anytime. |
| `stack-cleanuparr-instances` | none | Which `*arr` apps Cleanuparr has an *actual connected instance* for, as opposed to just network-reachable - a real gap found live once (an app had network access and a config placeholder but no connected instance, so queue-cleaning silently wasn't covering it). |
| `stack-cleanuparr-strikes` | `[limit]` (default 15) | Recent stalled/slow/malware strikes Cleanuparr has issued. |
| `stack-neutarr-status` | none | Per-app enabled/disabled state from NeutArr's own config - confirms which apps it's actually hunting missing content for. |
| `stack-prowlarr-indexers` | none | Every configured Prowlarr indexer's enabled state and sync priority. |
</command_reference>

## Common mistakes

<common_mistakes>
<general_anti_patterns>
- **Assuming a network-reachable Cleanuparr means it's covering an app.** Reachability and having an actual connected instance in Cleanuparr's own config are two different things - always check `stack-cleanuparr-instances`, not just that the container is up, before assuming strikes/cleanup are active for a given app.
- **Confusing `stack-nzbdav-delete-failures` with `stack-nzbdav-unstick`.** They fix different things: `delete-failures` removes "Failed" rows from history so a matching release name can be re-grabbed ("Duplicate nzb" errors); `unstick` restarts the NzbDAV container because its history query is hanging. A hanging query isn't fixed by deleting failures, and a duplicate-nzb block isn't fixed by a restart - pick based on the actual symptom.
</general_anti_patterns>
</common_mistakes>

## Resources

<resources>
**Local:**
- `~/.config/fish/functions/stack-nzbdav*.fish` (including `stack-nzbdav-delete-failures.fish`, `stack-nzbdav-unstick.fish`), `stack-cleanuparr*.fish`, `stack-neutarr-status.fish`, `stack-prowlarr-indexers.fish` - the actual fish source these commands wrap
- `scripts/nzbdav-prune-history.py` and its `stack-nzbdav-prune-history.timer` unit - the recurring job `stack-nzbdav-delete-failures` runs on demand
- `control-panel/app.py` in this repo - the real behavior behind every endpoint these commands call
</resources>
