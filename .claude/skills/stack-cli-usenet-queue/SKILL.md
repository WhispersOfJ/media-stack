---
name: stack-cli-usenet-queue
description: Exact fish CLI command reference for BearMount, Cleanuparr, and Prowlarr status/queue operations against this stack's Control Panel. Use whenever the user asks about the Usenet download queue/history, Cleanuparr strikes, or Prowlarr indexer state from the terminal. Trigger phrases: "check the bearmount queue", "bearmount history", "cleanuparr strikes", "prowlarr indexers".
---

# Stack CLI: Usenet & Queue Automation

<skill_scope skill="stack-cli-usenet-queue">
This is a command reference, not an operational tool: it exists so the exact fish function name, argument order, and output shape for every BearMount/Cleanuparr/Prowlarr terminal command in this stack is already known, without reading the fish source fresh each time. Every command here is a thin fish wrapper around Control Panel's own HTTP API (`http://192.168.4.105:8420`); the actual behavior lives in `control-panel/app.py`. Recyclarr was reinstalled in a later session (see CLAUDE.md's History) - it currently has no dedicated CLI command here, only a `/api/recyclarr/status` route. Maintainerr (and its `stack-maintainerr-rules` command, `/api/maintainerr/rules` route) was removed entirely, by explicit request (never used) - there is no Plex library lifecycle management in this stack. NeutArr (missing-content hunting) was removed entirely 2026-07-24 - there is no `stack-neutarr-*` command anymore, and no automated hunting of any kind in this stack.

**Related skill:** `usenet-orchestrator` is a different mechanism entirely - a standalone Python script that talks to BearMount's own SABnzbd-compatible API directly (not through Control Panel) and can retry/clear-failed items. Reach for `usenet-orchestrator` for queue *mutation* (retry, clear-failed); reach for the commands here for quick read-only status checks.
</skill_scope>

## Calling convention

<calling_convention>
Some commands here (`stack-cleanuparr-instances`) go through the `__stack_api` helper and print a raw `message`. The rest `curl` their endpoint directly and pipe through an inline `python3 -c "..."` formatter that unwraps FastAPI's `{"detail": {...}}` shape if present, prints `data['message']`, then loops over the relevant list field with per-line formatting.

None of these read a `STACK_HOST_IP` environment variable - the Control Panel URL is a literal hardcoded string in every function.
</calling_convention>

## Command reference

<command_reference>
| Command | Args | What it does |
|---|---|---|
| `stack-bearmount-queue` | none | BearMount's current Usenet download queue - category, name, status, percentage, MB left while downloading. |
| `stack-bearmount-history` | `[limit]` (default 20) | Recent completed/failed downloads, with the failure message if one failed. |
| `stack-bearmount-stats` | none | Aggregate queue/history counts - a summary instead of the raw dumps `stack-bearmount-queue`/`stack-bearmount-history` give. |
| `stack-bearmount-delete-failures` | none | Deletes every "Failed" entry from BearMount's history right now. On-demand version of the `stack-bearmount-prune-history.timer` job that already runs this every 4h - useful because a Failed row blocks re-grabbing an NZB with a matching release name ("Duplicate nzb" error) even when nothing exists on disk for it. |
| `stack-cleanuparr-instances` | none | Which `*arr` apps Cleanuparr has an *actual connected instance* for, as opposed to just network-reachable - a real gap found live once (an app had network access and a config placeholder but no connected instance, so queue-cleaning silently wasn't covering it). |
| `stack-cleanuparr-strikes` | `[limit]` (default 15) | Recent stalled/slow/malware strikes Cleanuparr has issued. |
| `stack-prowlarr-indexers` | none | Every configured Prowlarr indexer's enabled state and sync priority. |
</command_reference>

## Common mistakes

<common_mistakes>
<general_anti_patterns>
- **Assuming a network-reachable Cleanuparr means it's covering an app.** Reachability and having an actual connected instance in Cleanuparr's own config are two different things - always check `stack-cleanuparr-instances`, not just that the container is up, before assuming strikes/cleanup are active for a given app.
- **There is no `stack-bearmount-unstick`/`set-connections` equivalent.** Both were NzbDAV-specific workarounds (a non-REST settings API; a history-query-hang that cascaded into Sonarr marking the client unavailable) that were deliberately not ported to AltMount or BearMount - neither bug applies to BearMount's actual API shape. Before restarting `bearmount` for any reason, check its `import_queue` table for pending/processing rows first (see CLAUDE.md's hard rule) - a recreate wipes anything queued.
</general_anti_patterns>
</common_mistakes>

## Resources

<resources>
**Local:**
- `~/.config/fish/functions/stack-bearmount*.fish` (including `stack-bearmount-delete-failures.fish`), `stack-cleanuparr*.fish`, `stack-prowlarr-indexers.fish` - the actual fish source these commands wrap
- `scripts/bearmount-prune-history.py` and its `stack-bearmount-prune-history.timer` unit - the recurring job `stack-bearmount-delete-failures` runs on demand
- `control-panel/app.py` in this repo - the real behavior behind every endpoint these commands call
</resources>
