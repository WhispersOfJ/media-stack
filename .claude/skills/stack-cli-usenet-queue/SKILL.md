---
name: stack-cli-usenet-queue
description: Exact fish CLI command reference for NzbDAV, Cleanuparr, NeutArr, Recyclarr, Maintainerr, and Prowlarr status/queue operations against this stack's Control Panel. Use whenever the user asks about the Usenet download queue/history, Cleanuparr strikes, NeutArr hunting state, Recyclarr's last sync, Maintainerr rules, or Prowlarr indexer state from the terminal. Trigger phrases: "check the nzbdav queue", "nzbdav history", "cleanuparr strikes", "is neutarr connected", "recyclarr status", "maintainerr rules", "prowlarr indexers".
---

# Stack CLI: Usenet & Queue Automation

<skill_scope skill="stack-cli-usenet-queue">
This is a command reference, not an operational tool: it exists so the exact fish function name, argument order, and output shape for every NzbDAV/Cleanuparr/NeutArr/Recyclarr/Maintainerr/Prowlarr terminal command in this stack is already known, without reading the fish source fresh each time. Every command here is a thin fish wrapper around Control Panel's own HTTP API (`http://192.168.4.105:8420`); the actual behavior lives in `control-panel/app.py`.

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
| `stack-cleanuparr-instances` | none | Which `*arr` apps Cleanuparr has an *actual connected instance* for, as opposed to just network-reachable - a real gap found live once (an app had network access and a config placeholder but no connected instance, so queue-cleaning silently wasn't covering it). |
| `stack-cleanuparr-strikes` | `[limit]` (default 15) | Recent stalled/slow/malware strikes Cleanuparr has issued. |
| `stack-neutarr-status` | none | Per-app enabled/disabled state from NeutArr's own config - confirms which apps it's actually hunting missing content for. |
| `stack-recyclarr-status` | none | Recyclarr's last sync result. Recyclarr is cron-driven with no persistent API of its own, so this is literally its container's recent log lines, not a live query - a stale-looking result can mean it hasn't run recently, not that it's broken. |
| `stack-maintainerr-rules` | none | Configured Maintainerr rules and their active/inactive state. Rules ship disabled by default in this stack - a rule showing `off` may be intentional, not a misconfiguration. |
| `stack-prowlarr-indexers` | none | Every configured Prowlarr indexer's enabled state and sync priority. |
</command_reference>

## Common mistakes

<common_mistakes>
<general_anti_patterns>
- **Assuming a network-reachable Cleanuparr means it's covering an app.** Reachability and having an actual connected instance in Cleanuparr's own config are two different things - always check `stack-cleanuparr-instances`, not just that the container is up, before assuming strikes/cleanup are active for a given app.
- **Reading a stale `stack-recyclarr-status` result as a failure.** It reflects the container's last log output on a cron schedule, not a live health check - cross-check the timestamp in the output against Recyclarr's actual schedule before concluding it's broken.
- **Treating a Maintainerr rule showing `off` as broken.** Rules ship disabled by default in this stack on purpose (they can delete matching media on a real schedule) - `off` is the safe default, not necessarily neglect.
</general_anti_patterns>
</common_mistakes>

## Resources

<resources>
**Local:**
- `~/.config/fish/functions/stack-nzbdav*.fish`, `stack-cleanuparr*.fish`, `stack-neutarr-status.fish`, `stack-recyclarr-status.fish`, `stack-maintainerr-rules.fish`, `stack-prowlarr-indexers.fish` - the actual fish source these commands wrap
- `control-panel/app.py` in this repo - the real behavior behind every endpoint these commands call
</resources>
