# Playbooks & Gotchas

Workflow playbooks for recurring task types, operational gotchas, and backup/DR notes.

---

## Workflow Playbooks

### Bundled dependency has a bug

1. Rule out your own config first with a raw, protocol-level test that bypasses the app (e.g. `openssl s_client` for NNTP auth)
2. Clone upstream repo to a scratch dir, read real source before guessing from logs
3. **Test patches against a fake/unreachable endpoint first** — a retry-logic fix can turn into a rapid-fire storm against a real account
4. Fork upstream, push branch, open real PR referencing the filed issue
5. For broader security audit, use `fullstack-dev-skills:security-reviewer` plugin
6. Don't pin compose to a local/fork build permanently — leave stock image pinned, record PR/issue link

### Rotating a credential consumed by multiple apps

1. Use `secret-injector` skill (writes `.env` safely, leak-scans working tree)
2. Every consumer needs updating separately — nothing shares one source of truth:
   - Issuing app: `config/<app>/config.xml` `<ApiKey>` (API PUT silently ignores changes)
   - Prowlarr Applications sync: strip read-only `id` before PUT
   - Seerr: same read-only `id` field gotcha
   - Bazarr: `/api/system/settings` form-encoded (see README Bazarr section)
   - Cleanuparr: stop container first, edit SQLite `arr_instances` directly
   - NZBDAV download-client entry: separate from Radarr/Sonarr's own key
   - Control Panel: needs `--force-recreate` (reads `.env` at create time only)
3. Test each consumer's connection via its own `/test` endpoint

### FUSE mount owner needs restart

1. Confirm download queue is empty (`stack-nzbdav-queue`)
2. Restart mount owner first (`docker compose restart nzbdav_rclone`)
3. Wait for healthy (`docker exec nzbdav_rclone mount | grep nzbdav`)
4. Restart all five dependents: radarr, sonarr, plex, unpackerr, cleanuparr
5. Verify symlinks resolve (`ls -la media/movies/`)

### Whole-stack restart

Use `stack-restart-all` or the Control Panel's `/api/v2/host/restart-all` — it encodes the mount-order cascade. Never restart mount providers outside this endpoint without manually restarting dependents afterward.

---

## Operational Gotchas

### Control Panel reads .env at container-create time only

A plain `restart` won't pick up a `.env` change. Use `--force-recreate`.

### Static files baked into image

`static/` (CSS/JS/HTML) is COPY'd in the Dockerfile. Edit on disk → build → recreate.

### Bazarr settings endpoint

`POST /api/system/settings` is form-encoded, undocumented (meant for Bazarr's own frontend). Boolean fields need lowercase `true`/`false` strings. Array fields need one repeated form key per value, not comma-joined.

### Plex section keys drift

Section keys shift whenever a library is deleted/recreated. Check `GET /library/sections` for live keys, not documentation.

### App removal must be exhaustive

Remove: compose block, config directory, env vars, Prowlarr application-sync, Cleanuparr SQLite row, Control Panel references, fish functions, content-routing groups. Nothing auto-detects orphans.

### Service can be connected but not wired

A service reachable at the compose level may not be registered inside the target app. Always check the receiving app's own config/API for a real instance entry.

---

## Backup / DR

### Current state: zero automated backup coverage

Restic was removed entirely on 2026-08-12. `scripts/arr-app-backup.py` (Radarr/Sonarr native Backup command) is the only remaining backup mechanism and is not restic-based.

### From-scratch restore pre-step

`/mnt/remote/nzbdav` must be created manually before `docker compose up`, or nzbdav_rclone crash-loops. Run `sudo mkdir -p /mnt/remote/nzbdav` first.

### What config holds that isn't reproducible

- `config/<app>/` — every app's persistent state, API keys, databases
- `config/nzbdav/db.sqlite` — Usenet provider credentials
- `.env` — all secrets (gitignored, not in compose)
- `media/` symlinks — recreated by re-running nzbdav imports, but metadata/watch history is not

### What IS reproducible

- `docker compose up -d` restores all container definitions
- Image pulls restore all application code
- Plex libraries can be re-created via API
- Radarr/Sonarr libraries repopulate from import lists

### Known gap: Plex config deletion

The original Plex config (34GB, all watch history/ratings) was deleted with no archive during the Jellyfin migration. Current Plex is a fresh install with no migrated history.