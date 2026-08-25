# Stack Audit — 2026-08-23

Top-to-bottom security, optimization, and app-gap audit. Ignore documentation,
examine the live compose file and running state only.

---

## Security (1–20)

### 1. No reverse proxy / TLS termination
Every service ports directly to `0.0.0.0`. The entire stack — including Control
Panel with docker.sock exec access, Grafana with admin credentials, and all *arr
API keys — is served over plaintext HTTP on the LAN. A single compromised device
on the same subnet owns everything.
**Fix:** Caddy as a reverse proxy with automatic HTTPS (or WireGuard-only
exposure if LAN-only is acceptable but you still want encryption between client
and proxy).

### 2. No network segmentation
All containers share a single `stacknet` bridge. A compromised Watchtower (which
has docker.sock read) can reach every other container on its internal port.
**Fix:** Split into subnets: `stacknet-public` (Plex, Seerr, Grafana),
`stacknet-internal` (Radarr, Sonarr, Prowlarr, NzbDAV, control-panel),
`stacknet-management` (Watchtower, Loki, Promtail).

### 3. Docker socket mounted read-only to two containers
Control Panel has `:ro` on `/var/run/docker.sock`, but even read-only lets an
attacker enumerate every container, read every environment variable (all secrets),
and read every volume path. Watchtower also has it.
**Fix:** Use Docker socket proxy (e.g., `tecnativa/docker-socket-proxy`) with a
filtered API whitelist instead of raw socket access.

### 4. Control Panel has `pid: host`, `SYS_ADMIN`, `SYS_PTRACE`, `apparmor:unconfined`
Most privileged container in the stack. Combined with unauthenticated LAN access
and docker.sock, any XSS or CSRF in the Flask app becomes root-equivalent on the
host.
**Fix:** Move Force Unstick to a separate sidecar with its own minimal container
and remove these capabilities from the main control-panel.

### 5. No `read_only: true` on any container filesystem
Every container can write to its own filesystem at runtime — a compromised
container can install tools, backdoors, or modify its own binary.
**Fix:** Add `read_only: true` + `tmpfs` for `/tmp`, `/run`, and any other
writable paths each container needs.

### 6. No `cap_drop: ALL` anywhere
All containers run with Docker's default capability set (includes `NET_RAW`,
`MKNOD`, `AUDIT_WRITE`, etc.).
**Fix:** Add `cap_drop: [ALL]` to every service, then `cap_add` only what's
strictly needed.

### 7. No `no-new-privileges` on any container
A container can escalate privileges via setuid binaries.
**Fix:** Add `security_opt: [no-new-privileges:true]` to every service.

### 8. Prowlarr, Radarr, Sonarr ports exposed to the LAN
Ports 9696, 7878, 8989 bound to `0.0.0.0`. These have API key auth but no
login — anyone on the LAN can search/index/grab via the API.
**Fix:** Bind to `127.0.0.1` (only reachable via control-panel's proxy) or put
behind the reverse proxy with proper auth.

### 9. Grafana default admin password in `.env.example`
`GRAFANA_ADMIN_PASSWORD` held a real, guessable password committed to git
(redacted 2026-08-25 before the repo went public).
**Fix:** Generate a random password, remove from `.env.example`, replace with
`changeme`.

### 10. No fail2ban / CrowdSec / brute-force protection
Every login endpoint is vulnerable to password spraying. CrowdSec was previously
built and reverted, but nothing replaced it.
**Fix:** At minimum add fail2ban monitoring Docker logs; ideally bring back
CrowdSec as a container.

### 11. Docker logging driver is `json-file` with no compression
Logs with secrets (API keys in startup banners, healthcheck URLs) accumulate
unencrypted on disk.
**Fix:** Consider `local` driver with compression, or pipe to Loki and disable
`json-file` except as a fallback.

### 12. Grafana contradictory alerting config
`GF_ALERTING_ENABLED: false` but `GF_UNIFIED_ALERTING_ENABLED: true`. If nobody
manages Grafana alerts, this is a silent attack surface.
**Fix:** Disable unified alerting too if not actively used, or actually configure
alerting.

### 13. Session cookie missing explicit `SameSite` attribute
Control Panel uses `CONTROL_PANEL_SECURE_COOKIE` only for `Secure` flag;
`SameSite` defaults vary by browser.
**Fix:** Set `SameSite=Lax` explicitly in the session cookie creation.

### 14. Control Panel secret key is in `.env`
`CONTROL_PANEL_SECRET_KEY` signs session tokens. If `.env` is compromised
(backup leak, git history), all session tokens are forgeable.
**Fix:** Move to Docker secret or ensure `.env` is never backed up to untrusted
location.

### 15. No secret rotation schedule
All `changeme` values in `.env.example` are real credentials in the live `.env`.
No rotation schedule, no secret management.
**Fix:** Quarterly rotation reminder for all API keys. Consider vaultwarden for
team secret management.

### 16. No container image signature verification
All images pulled by tag or digest with no cosign/notary verification.
**Fix:** Pin to digests and/or enable Docker Content Trust.

### 17. FUSE mount container has `SYS_ADMIN` + `apparmor:unconfined`
Required for FUSE, but a FUSE exploit in rclone = host kernel access.
**Fix:** Use kernel-level cgroup isolation or run FUSE in a dedicated security
domain with seccomp.

### 18. No seccomp profiles on any container
Default Docker seccomp profile is permissive.
**Fix:** Profile each container's syscalls (especially Watchtower and
control-panel which have docker.sock).

### 19. `.env` file bind-mounted as plain file
Any container with a volume mount to the host can read it.
**Fix:** Use Docker secrets for sensitive values.

### 20. Watchtower updates all containers with no image allowlist
A malicious upstream image gets auto-deployed to production.
**Fix:** Add label-based filter (`com.centurylinklabs.watchtower.enable=true`)
so only explicitly opted-in images auto-update.

---

## Optimization (21–38)

### 21. Plex on `network_mode: host`
Plex can't be reached by other containers by hostname — only by IP. Its full
port range is exposed.
**Fix:** Add iptables rules limiting port 32400 access to known client IPs.

### 22. VFS cache has no space-pressure eviction
50GB cache with only `max-age=336h` eviction. Old files consume disk until they
age out.
**Fix:** Add `--vfs-disk-space-total-size` or monitor/alert on cache size.

### 23. `--no-checksum` on rclone mount
Corrupted files during download or cache write are served silently to
Plex/Radarr.
**Fix:** Enable checksum verification for at least import operations.

### 24. Segment cache is 20GB on a 122GB-free filesystem
16% of available disk. Under heavy concurrent streams + import, this could push
other services to disk pressure.
**Fix:** Move to a dedicated path with its own disk quota, or reduce to 10GB.

### 25. `buffer-size=0M` on rclone mount
Disables read-ahead buffering. Every chunk request is a separate round-trip to
NzbDAV's WebDAV.
**Fix:** Set `--buffer-size=128M` for better sequential read performance.

### 26. Log rotation is 10MB × 10 files per container
15+ containers × 100MB = 1.5GB+ of logs in Docker's rotation alone.
**Fix:** Reduce to 5MB × 5 for low-volume containers.

### 27. No Prometheus — metrics gap in Grafana
Loki + Promtail only does log aggregation. No CPU, memory, disk I/O, or
container health history metrics.
**Fix:** Add node-exporter + cAdvisor + Prometheus, then build Grafana dashboards.

### 28. Queue worker count competes for provider pool
6 workers + streaming both draw from 52 connections. Heavy import can starve
streaming.
**Fix:** Reduce to 4 workers or partition the connection pool.

### 29. Prowlarr healthcheck start_period may be too short
30s may not be enough for indexer sync. NzbDAV may try to use indexers that
aren't ready.
**Fix:** Increase `start_period` to 60s or verify indexer count > 0.

### 30. No consolidated backup strategy
Each app's config is in a separate directory. Backup is ad-hoc.
**Fix:** Add a dedicated backup container (restic/duplicati) with consolidated
mount and remote target.

### 31. Watchtower has no rollback on bad updates
A bad image at 04:00 could break the stack with no automatic rollback.
**Fix:** Add `WATCHTOWER_ROLLING_RESTART=true` and a post-update healthcheck
that rolls back if healthchecks fail.

### 32. No healthcheck-based dependency ordering beyond `depends_on`
Services can start before dependencies are ready, causing crash loops.
**Fix:** Use `depends_on.condition: service_healthy` consistently.

### 33. No swap limits on containers
Containers can use swap, masking memory leaks until host OOM.
**Fix:** Add `memswap_limit` equal to `mem_limit` to disable swap per container.

### 34. No CPU shares/weight differentiation
Under contention, Watchtower could steal cycles from Plex.
**Fix:** Add `cpu_shares` to establish priority.

### 35. VFS cache max-age is 14 days
Stale cache persists for two weeks. Wasteful for immutable Usenet segments.
**Fix:** Consider `72h` and let re-fetches happen (NzbDAV segment cache handles
repeat reads).

### 36. No disk space monitoring/alerting
No alert when disk usage exceeds a threshold.
**Fix:** Add disk-usage check to control-panel health or a cron alert job.

### 37. `--poll-interval=5m` is aggressive
Polling every 5 minutes generates unnecessary WebDAV LIST requests.
**Fix:** Increase to 15m or 30m (RC notifications handle file-add events).

### 38. Grafana is at 10.4.0 (March 2024)
Current version is 11.x with significant security fixes.
**Fix:** Upgrade to latest stable 11.x.

---

## Additional Apps (39–55)

### 39. Vaultwarden
No secrets management. Self-hosted Bitwarden-compatible password manager for
all API keys and credentials.

### 40. Caddy
Reverse proxy with automatic HTTPS via Let's Encrypt. Single entry point with
proper auth middleware.

### 41. Authelia
SSO / 2FA layer in front of every web service. Previously built and reverted.

### 42. CrowdSec
Banned-IP / behavioral blocking. Analyzes logs and auto-bans malicious IPs.

### 43. Navidrome
Music server. Lightweight Subsonic-compatible audio server. Can library-scan
from a DAV-mounted path.

### 44. Audiobookshelf
Audiobook/podcast server. Self-contained, lightweight, with auth and progress
tracking. Can use DAV mount.

### 45. Calibre-Web
Ebook server. Web UI for reading/managing ebooks from a DAV-mounted library.

### 46. Tautulli
Plex monitoring/analytics. Watch history, user stats, recently added, IP-based
streaming info. Was removed in v11.9.0.

### 47. Kometa
Plex metadata manager. Automated poster collections, genre lists, metadata
overlays. Was removed in v11.9.0.

### 48. Seerr notification webhooks
Seerr is deployed but no notification configuration. Requests go silent.
**Fix:** Wire Seerr's notification system to `DISCORD_WEBHOOK_URL`.

### 49. Uptime Kuma
Service monitoring dashboard. Visual healthcheck dashboard with downtime
history and Discord notifications.

### 50. Watchtower notifications
Watchtower is deployed but `WATCHTOWER_NOTIFICATION_URL` is not set.
**Fix:** Add Shoutrrr Discord URL.

### 51. Dozzle
Live container log viewer. Instant `docker logs --follow` for all containers
in a web UI. Lightweight, zero-config.

### 52. FileBrowser
Web file manager. Browse config directories and media mounts from a web UI
with authentication.

### 53. Duplicati / Restic
Encrypted backup. Back up all `./config/`, `./data/`, and `.env` to an
encrypted remote target.

### 54. Netdata
Real-time host metrics. Per-second CPU/memory/disk/network tracking with
anomaly detection.

### 55. Authentik
Full-featured identity provider. OAuth2/OIDC/LDAP/SAML with passkeys and
TOTP. Alternative to Authelia.

---

## Implementation Priority

| Priority | Items | Impact |
|----------|-------|--------|
| P0 — Now | #27 (Prometheus/metrics), #1 (Caddy), #6+#7 (cap_drop + no-new-privileges) | High value, moderate effort |
| P1 — This week | #20 (Watchtower allowlist), #39 (Vaultwarden), #50 (Watchtower notifications) | Low effort, high value |
| P2 — This month | #2 (Network segmentation), #4 (Control-panel isolation), #10 (CrowdSec) | High effort, high value |
| P3 — Next month | #41 (Authelia), #49 (Uptime Kuma), #53 (Backup container) | Medium effort |
| P4 — Backlog | #43-47 (Navidrome, Audiobookshelf, Calibre-Web, Tautulli, Kometa) | Feature additions |
