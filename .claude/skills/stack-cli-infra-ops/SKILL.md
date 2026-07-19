---
name: stack-cli-infra-ops
description: Exact fish CLI command reference for container control, backups, and infrastructure diagnostics against this stack's Control Panel (status, restart, resource/mount/permission/image checks, backup verify/status, Seerr requests, top). Use whenever the user asks to check overall stack health, restart a container from the terminal, verify backups, or check for OOM kills, missing mem_limits, stale mounts, or unreadable config files. Trigger phrases: "check stack status", "restart this container", "verify the backup", "any oom kills", "check mount health", "top containers by cpu", "seerr requests".
---

# Stack CLI: Infra & Ops

<skill_scope skill="stack-cli-infra-ops">
This is a command reference, not an operational tool: it exists so the exact fish function name, argument order, and output shape for every container-control/backup/diagnostic terminal command in this stack is already known, without reading the fish source fresh each time. Every command here is a thin fish wrapper around Control Panel's own HTTP API (`http://192.168.4.105:8420`); the actual behavior lives in `control-panel/app.py`.

**Related skills:**
- `docker-compose-manager` operates one layer lower - it runs `docker compose` directly on the host with FUSE-mount cascade awareness (restarting `nzbdav-rclone`'s dependents in the right order). `stack-container`/`stack-restart-all` below go through Control Panel's own HTTP API instead, which has its own (separately maintained) mount-ordering logic for the whole-stack restart specifically, but no cascade awareness for a single-container restart. Prefer `docker-compose-manager` when a FUSE-mount-owning container needs restarting; either works for a plain application container.
- `health-monitor` is a broader Python sweep (Docker health + HTTP reachability across every service in one pass) meant for a general "is everything okay" triage. `stack-status` below is Control Panel's own live per-container view - similar purpose, different implementation, prefer whichever is already running or the user names.
</skill_scope>

## Calling convention

<calling_convention>
Many commands here (`stack-status`, `stack-resource-check`, `stack-mount-health`, `stack-oom-check`, `stack-perms-check`, `stack-image-check`, `stack-version`, `stack-backup-verify`, `stack-backup-restore-test`) are one-line `__stack_api GET/POST <path>` calls that just print the response's `message` field. The rest `curl` directly and pipe through an inline `python3 -c "..."` formatter for structured output.

None of these read a `STACK_HOST_IP` environment variable - the Control Panel URL is a literal hardcoded string in every function.
</calling_convention>

## Command reference

<command_reference>
| Command | Args | What it does |
|---|---|---|
| `stack-status` | none | Live state/health of every container in the stack. |
| `stack-container` | `<restart\|stop\|start> <container-name>` | Controls one container by name. No confirmation prompt - unlike `stack-restart-all`, a single-container action isn't gated. |
| `stack-restart-all` | `[-y\|--yes]` | Restarts every container in the stack (~20). Prompts for confirmation unless `-y`/`--yes` is given, mirroring the arm/confirm double-click the web UI uses for the same "danger zone" action. |
| `stack-resource-check` | none | Containers missing an explicit `mem_limit`/`cpus` in `docker-compose.yml` - these silently inherit the full host ceiling instead of a real number. |
| `stack-log-levels` | `[reset]` (no arg = check) | Checks, or resets to default, every Servarr app's log level. |
| `stack-mount-health` | none | Confirms every known FUSE mountpoint (currently just `nzbdav-rclone`'s) resolves cleanly. |
| `stack-oom-check` | none | Containers Docker has recorded an OOM-kill for - the only reliable way to catch one, since `restart: unless-stopped` silently restarts a killed container with no other visible symptom. |
| `stack-perms-check` | none | Config files unreadable by group/other - these silently fail to back up rather than erroring loudly. |
| `stack-image-check` | none | Checks digest- or exact-version-pinned images for a newer registry digest (channel-tag images are already covered by Watchtower and not what this checks). |
| `stack-disk-usage` | none | Per-app `config/` directory size, largest first. |
| `stack-version` | none | This repo's README-declared version plus a live core/extras container count - a doc-vs-reality drift check. |
| `stack-backup-verify` | none | Confirms both the local and off-site restic repos have a recent snapshot. |
| `stack-backup-restore-test` | none | Actually restores one file from the latest local snapshot to prove restores work, not just that a snapshot exists. |
| `stack-backup-status` | none | Full snapshot history (count, oldest, newest) for both restic repos - distinct from `stack-backup-verify`'s latest-only check. |
| `stack-notify-test` | none | Sends a real test message through the stack's Discord webhook - confirms it still works without waiting for a real failure to find out it doesn't. |
| `stack-top` | `[cpu\|mem] [limit]` (default cpu, 10) | Top containers by resource usage, compact - faster than scanning every card in the dashboard grid. |
| `stack-seerr-requests` | `[pending\|approved\|available\|all]` (default pending) | Media requests sitting in Seerr, by status - confirms a request actually landed there before chasing why it's not showing up in Radarr/Sonarr. |
</command_reference>

## Common mistakes

<common_mistakes>
<general_anti_patterns>
- **Using `stack-container restart` on `nzbdav-rclone` or any FUSE-mount owner.** This command has no cascade awareness - restarting a mount-owning container without also restarting everything that bind-mounts its output (radarr, sonarr, plex, unpackerr, cleanuparr) leaves those dependents serving a stale mount handle until *they're* separately restarted. Use `docker-compose-manager`'s cascade-aware restart for that container specifically, not this.
- **Reading "container looks up" as "container is fine."** `restart: unless-stopped` means an OOM-killed container just silently restarts with no other visible symptom - `stack-oom-check` is the only way this class of problem surfaces; a clean `stack-status` doesn't rule it out.
- **Assuming a snapshot existing means restores work.** `stack-backup-verify` only checks that a recent snapshot exists; `stack-backup-restore-test` is the one that actually proves a restore succeeds. Prefer the latter when the question is really "can I trust this backup," not just "did it run."
</general_anti_patterns>

<from_fish>
- **Naming a local variable `status` in a fish script, expecting it to shadow cleanly.** `status` is a fish builtin tied to the last command's exit code; `set -l status ...` is silently rejected, so every later `$status` read falls through to the builtin instead of the intended value. Confirmed live in `stack-seerr-requests.fish` itself, which names its own local variable `req_status` specifically to avoid this - a real, previously-hit bug (produced `filter=1` in the request URL instead of `filter=pending`), not a hypothetical. The same class of trap exists in zsh with the `path` array; check for a reserved-name collision before assuming a local variable in either shell behaves like an ordinary local.
</from_fish>
</common_mistakes>

## Resources

<resources>
**Local:**
- `~/.config/fish/functions/stack-status.fish`, `stack-container.fish`, `stack-restart-all.fish`, `stack-resource-check.fish`, `stack-log-levels.fish`, `stack-mount-health.fish`, `stack-oom-check.fish`, `stack-perms-check.fish`, `stack-image-check.fish`, `stack-disk-usage.fish`, `stack-version.fish`, `stack-backup-*.fish`, `stack-notify-test.fish`, `stack-top.fish`, `stack-seerr-requests.fish` - the actual fish source these commands wrap
- `control-panel/app.py` in this repo - the real behavior behind every endpoint these commands call
</resources>
