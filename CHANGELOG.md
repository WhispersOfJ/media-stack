# Changelog

**This entire stack was designed, built, debugged, and documented by [Claude AI](https://www.anthropic.com/claude)** — every service added, every bug found and fixed, every line below, was Claude's work. Built with Claude AI. 🤖

All notable changes to this project are documented here, versioned as if each exchange with
Claude were a release: **MAJOR** for breaking/foundational changes, **MINOR** for new
features, **PATCH** for everything else — fixes, but also docs-only additions, CI/tooling
changes, dependency bumps, and planning docs that used to ship with no version at all. Every
commit that adds new, real information to the record gets a version now, however small; a
commit that only re-syncs already-documented information into a second file (e.g. copying a
just-shipped version's summary from CHANGELOG.md into README.md) still doesn't need its own —
same exception this file's own origin commit ([17e9f47], which wrote v1.0.0–v2.0.1 in one
retroactive pass) was never versioned under. Current version: **v10.0.0**.

> **2026-07-09 — live state found well behind what was already documented.** Before any of the
> work in [5.1.0], [5.2.0], and [6.0.0] below started, a routine check found
> that several features this file and README.md already described as done simply weren't live:
> Prowlarr had **0** indexers and **0** indexer proxies configured (README claimed 70 indexers
> + Byparr wired up); Radarr and Sonarr both had **0** custom formats and only the 6 stock
> default quality profiles (README claimed a "Blocked Releases" format at `-10000` and
> `HD Bluray + WEB`/`WEB-1080p` profiles, see [4.12.0]); `docker-compose.yml` had no
> `logging:` block anywhere and `/etc/docker/daemon.json` didn't exist (README's "Docker log
> rotation" section claimed daemon-level `10m`/`3` rotation was already live — no corresponding
> CHANGELOG entry for it exists anywhere in this file, so it's unclear it was ever actually
> shipped rather than just documented); and `restic` wasn't
> installed, `~/backups/stack-restic-repo` didn't exist, and `stack-backup.service` had never
> once run successfully despite being enabled. Root cause unconfirmed — this may be the same
> incident as the still-open [TODO.md](TODO.md) mass Radarr/Sonarr library-loss item (0.1s,
> zero API calls logged), since a wholesale `./config` rollback would explain the Prowlarr/
> Radarr/Sonarr side of this; it does **not** obviously explain `restic` being missing from the
> host or `/etc/docker/daemon.json` never existing, since neither lives inside `./config` or any
> docker volume. Flagging the correlation, not claiming it's proven. Everything below was
> rebuilt from zero and reverified live rather than assumed still-working from the old
> documentation — see each entry for what changed in the rebuild (notably: log rotation moved
> from host-level `daemon.json` to a per-service `logging:` block in `docker-compose.yml`
> itself, so it's tracked in git this time instead of living only on the host).

> **2026-07-09 — versioning policy tightened, history backfilled.** Several past commits (a
> planning doc, two CI workflow additions, a Dependabot base-image bump, a doc-only bugfix
> link, a doc-only correction, and turning on an already-built feature) had shipped with no
> version or CHANGELOG entry at all. Backfilled all of them and renumbered everything after
> each insertion point so the sequence stays gapless — see [2.3.1], [2.5.1], [2.7.0],
> [2.11.1], [2.11.2] (previously logged out-of-sequence as "[Unversioned, 2026-07-07]"),
> [2.13.1], [2.13.2], and [3.2.4]. This only touched `CHANGELOG.md`/`README.md`; no git commits
> were rewritten. **Only some `2.x` minor/patch numbers between `2.3.0` and `2.13.0` shifted**
> — `v4.14.0` and everything in the `3.x`/`4.x` line is unaffected. One consequence worth
> knowing: this repo's installer image is tagged `:vX.Y.Z` in GHCR on every push, parsed
> straight from this file's "Current version" line — a tag actually published in the past
> under one of the old `2.x` numbers (e.g. a `:v2.9.0` pulled before this date) no longer
> lines up 1:1 with what that number refers to here now.

## [10.0.0] — Network security layer fully reverted: Traefik + Authelia + CrowdSec removed, direct ports restored

Owner call, not a bug fix: after living with [9.0.0](CHANGELOG.md)'s login+2FA-in-front-of-
everything for a day, the day-to-day friction (a password+TOTP prompt in front of Sonarr/Radarr/
etc. for a stack that's genuinely LAN-only anyway, three extra services to keep healthy, plus the
firewall bug in [9.1.1](CHANGELOG.md) that took Plex down through the proxy) wasn't worth what it
bought. Reverted the whole layer back to [8.2.0](CHANGELOG.md)'s model: every web UI publishes
its port directly on the host again, no login gate, LAN/Tailscale trust only - the same model
this stack ran under from [3.1.0](CHANGELOG.md) through [8.2.0](CHANGELOG.md).

This is a revert of the *network security layer specifically*, not a revert of everything that
shipped alongside it in [9.0.0](CHANGELOG.md)/[9.1.0](CHANGELOG.md)/[9.1.1](CHANGELOG.md): the
README/TECHNICAL.md documentation split, and every unrelated fix from the rest of that same day
(Discord webhook posting, Pinchflat/Lidarr/Readarr/Whisparr cleanup, CI gates, off-site backup,
Control Panel's CSRF/Origin-Host hardening, restart-all ordering) all stay exactly as they were -
see each entry below for those individually.

### Removed
- **Traefik, Authelia, CrowdSec** - all three services, their `docker-compose.yml` blocks, and
  the `authelia/`, `crowdsec/`, `traefik/` config directories deleted outright.
- **`docker-compose.yml` labels → `ports:`** - every `traefik.*` label removed; all 18 services
  [9.0.0](CHANGELOG.md) migrated behind Traefik got their direct host `ports:` mapping back,
  identical to what they ran before that migration. Adminer (added in [9.0.0](CHANGELOG.md)
  itself, so it never had a direct port before) got a new one - `8081:8080`, since `8080` is
  already Dozzle's.
- **`.env`/`.env.example`** - `AUTHELIA_SESSION_SECRET`, `AUTHELIA_STORAGE_ENCRYPTION_KEY`,
  `AUTHELIA_JWT_SECRET`, `CROWDSEC_BOUNCER_API_KEY` all removed. `HOST_IP` stays - Control
  Panel's CSRF check and Watchtower's notification hostname both still use it independently of
  Traefik.
- **`scripts/setup_wizard.py`** - the three `AUTHELIA_*` keys removed from `AUTO_GENERATE_KEYS`.
- **Host firewall** - `/etc/nftables.conf`'s default-deny `inet filter` table (host-level, not
  tracked in this repo) removed live via the rollback command documented in its own header
  comment (`sudo nft delete table inet filter`), and `nftables.service` disabled so it doesn't
  reapply on the next boot. Docker's own iptables-nft tables and Tailscale's `ts-input`/
  `ts-forward` chains were never touched by this table and remain exactly as they were.
- **README.md/TECHNICAL.md** - the `https://*.cave.internal` + hosts-file instructions and the
  2FA walkthrough replaced with the direct `http://<ip>:<port>` table; TECHNICAL.md's Security
  note, Control Panel section, and setup-wizard section rewritten to describe the reverted state
  instead of the removed one.

### Kept
- **[7.2.0](CHANGELOG.md)'s CSRF/Origin-Host validation** on Control Panel's POST endpoints.
  Deliberately not part of this revert - it isn't the network-security layer, it closes a
  same-origin-POST gap that exists regardless of whether Traefik/Authelia are in front of
  anything. See the updated [Security note](TECHNICAL.md#security-note) for the distinction.

### Verified live
- `docker compose config` validated clean after every `docker-compose.yml` edit.
- `traefik`, `authelia`, `crowdsec` containers stopped and removed; the 18 direct-port services
  plus Adminer recreated via `docker compose up -d` and confirmed healthy.
- `sudo nft list ruleset` confirmed the `inet filter` table is gone and Docker/Tailscale's own
  tables are untouched.

## [9.1.1] — Fixed: Plex unreachable from any stacknet container (Traefik 502s, silent Radarr/Sonarr notification failures) - firewall hairpin-NAT gap

Found live, reported as "Bad Gateway on plex" after [9.0.0](CHANGELOG.md)'s network-security
rollout - every request that reached Plex's backend through Traefik failed with a `502`, **100%
of the time**, while direct requests from the host itself to the exact same
`http://192.168.4.105:32400` address always succeeded (confirmed with 20 back-to-back direct
requests, all clean `200`/`401`s). That "always fails one way, never the other" pattern is what
actually pointed at the real cause - a first hypothesis (Plex's HTTP server silently closing
idle keep-alive connections that Traefik's pool then tried to reuse) would have predicted
*intermittent* failures, not a deterministic one, and was abandoned once the access log showed
every single proxied request failing rather than a fraction of them.

**Root cause:** the nftables firewall added in [9.0.0](CHANGELOG.md) only allowed this host's LAN
subnet (`192.168.4.0/22`) to reach Plex's `network_mode: host` port `32400`. Any container on
`stacknet` reaching Plex via the host's real IP hairpins through Docker's own NAT and arrives at
the firewall's `INPUT` chain from `stacknet`'s own subnet (`172.18.0.0/16`), not the LAN, so it
was being rejected outright (`meta pkttype host limit rate 5/second ... reject with icmpx
admin-prohibited` - the same rule already in place, just never exercised by a *containerized*
client reaching this particular port before). Verified directly: a throwaway container on
`stacknet` hitting `http://192.168.4.105:32400/` got connection-refused (`000`) before the fix, a
clean `401` after.

**Same root cause, wider blast radius than first thought.** Digging into a separate symptom - a
freshly-imported movie (Interstellar) not showing up in Plex despite Radarr reporting a clean
import - traced back to this exact bug. Radarr's own debug log (`radarr.debug.6.txt`, the file
covering the actual import window - its log rotation is fast enough under heavy API traffic that
the current `radarr.txt`/`radarr.debug.0.txt` no longer covered it) showed Radarr attempting its
native Plex Media Server notification at the moment of import and failing with the identical
signature:
```
PlexServerProxy|Url: http://192.168.4.105:32400/identity?...
Warn|PlexServerService|Failed to Update Plex host: 192.168.4.105
Warn|NotificationService|Unable to process notification queue for Plex Media Server
```
Reproduced a second, independent failure for a different movie (Grease) 10 minutes later in the
same log, both before this fix landed. Radarr runs on `stacknet` exactly like Traefik, using the
same `http://192.168.4.105:32400` address (`PLEX_URL` in `.env`) - so its automatic
"update library on import" notification was silently failing via the same hairpin-NAT gap the
whole time, with no user-visible error (Radarr logs the failure at `Warn`, not somewhere the UI
surfaces by default). Sonarr has the identical `PlexServer` notification configured and was never
observed failing, but shares the exact same exposure and would have hit it under the same
conditions. Confirmed fixed by replicating Radarr's exact failing request
(`curl` from a `stacknet` container to `http://192.168.4.105:32400/identity?X-Plex-Token=...`) -
`000` before the fix, `200` after. Going forward, both Radarr and Sonarr should notify Plex
successfully on import/upgrade without needing a manual library scan.

### Fixed
- **`/etc/nftables.conf`** (host-level, not tracked in this repo) - added an explicit allow for
  `172.18.0.0/16` (stacknet) to reach `tcp/32400`, alongside the existing LAN allowance. One
  line; every other rule untouched. Fixes Traefik's proxying *and* Radarr/Sonarr's own Plex
  notifications in one change, since all three hit the same gap.

### Known follow-up
- A first fix attempt (a custom Traefik `serversTransport` with a 1-second idle-connection
  timeout for the Plex backend, meant to address the keep-alive theory above) was added and then
  removed once the real cause was confirmed - it wasn't wrong to try given the evidence available
  at the time, but it also wasn't the actual fix, and `docker-compose.yml` ended up byte-identical
  to [9.1.0](CHANGELOG.md) once removed (nothing to commit there this round - only this file and
  the host's own `/etc/nftables.conf` changed).
- Any content imported between [9.0.0](CHANGELOG.md) landing and this fix (just Interstellar, in
  practice) needed a one-time manual Plex library refresh to show up - already done live for that
  title; nothing further to clean up.

## [9.1.0] — README rewritten for beginners; all prior technical depth moved to TECHNICAL.md

`README.md` had grown into the project's real technical reference (1,828 lines) as of
[9.0.0](CHANGELOG.md) — exact image-pinning rationale, resource-limit tuning tables, the full
setup-wizard internals, byte-for-byte migration verification notes. Excellent for understanding
*why* something is the way it is, genuinely hostile to someone who just wants to get a Plex
library running and doesn't yet know what a `docker-compose.yml` even is. Decided to split
these into two documents with two different jobs, rather than trim the technical one down and
lose the depth that's been this project's whole differentiator so far.

### Added
- **`TECHNICAL.md`** — an exact copy of the prior `README.md` in full, plus a short banner at
  the top pointing back to the new `README.md` for anyone who landed here first. Nothing was
  cut; every image-pinning reason, every resource-limit table, every migration writeup, the
  full setup-wizard code walkthrough - all still here, unchanged, still the deep reference for
  anyone changing something in this stack themselves.

### Changed
- **`README.md` rewritten from scratch** as a short, plain-language "get this running and use
  it" guide: what the project does in two sentences, the four things you need before starting
  (Docker, a debrid account, a Plex account, a machine to run it on), the same setup commands
  as before but explained in plain terms, a short table of what each app is *for* rather than
  its port number, and a "you only actually need Seerr and Plex day to day" framing that the
  old version never made explicit. Every cross-reference that used to point at a
  now-relocated README section (image pinning, resource limits, Control Panel's full feature
  list, etc.) now points at `TECHNICAL.md` instead.

### Known follow-up
- Historical CHANGELOG entries below this one that link to "README.md's `#some-section`" were
  written when that content genuinely lived in `README.md` - it's all in `TECHNICAL.md` now,
  same anchor names, so those links still resolve to the right *content*, just via the other
  file. Left as-is rather than retroactively rewritten, consistent with this file's own
  append-only/historical-record convention (see the top-of-file note on when past entries do
  vs. don't get corrected).

## [9.0.0] — Network security layer: Traefik + Authelia + CrowdSec replace the flat no-auth state

Every web UI has published its port directly on the host with no auth gate since v3.1.0 removed
the Caddy + Basic-Auth layer added in v2.11.0 (see that entry - the removal reasoning was
maintenance cost, "more moving parts than value", not a flaw in reverse-proxying itself).
Decided to revisit this with a different toolset, and to build it so that exposing one service
publicly later is a small additive step instead of a redesign. Live investigation before writing
any config surfaced two things that shaped the whole design: Tailscale was already installed and
connected on this host (private remote access already solved, independent of this work), and
there was no host firewall at all - only Docker's own iptables-nft-managed tables and
Tailscale's `ts-input`/`ts-forward` chains.

### Added
- **nftables host firewall** - default-deny on the host's own `INPUT` chain
  (`/etc/nftables.conf`, host-level, not tracked in this repo, same treatment as
  `/etc/docker/daemon.json`). Explicit allow for `tailscale0` (full trust) and this host's LAN
  subnet for a short allowlist: Plex (`network_mode: host` - its ports terminate on the host
  directly, unlike every other container here, so this was the one real risk in an otherwise
  container-port-transparent change), mDNS, SSDP, KDE Connect, Dropbox LanSync, and Traefik's
  own `443`. No `forward` chain touched at all - confirmed live that Docker-published container
  ports are DNAT'd and delivered via Docker's own `FORWARD` chain, never reaching this table, so
  container networking needed zero changes here.
- **Traefik** (`traefik:v3.7.7`) - single ingress point for every web UI, Docker-label
  auto-discovery (`exposedByDefault: false`), TLS via a local `mkcert` CA
  (`config/traefik/certs/`, installed into this host's system/browser trust stores). Static
  config at `traefik/traefik.yml` (git-tracked, no secrets - same "tracked in git, just routing"
  treatment the old Caddyfile used).
- **Authelia** (`authelia/authelia:4.39.20`) - per-user login with TOTP 2FA via a
  `forwardAuth` middleware (`authelia@docker`) applied to every router, replacing Caddy's old
  one-shared-Basic-Auth-hash approach. File-based user DB
  (`config/authelia/users_database.yml`, gitignored, `chmod 600`). Filesystem notifier (no SMTP
  in this stack) - identity-verification codes for 2FA enrollment/password reset land in
  `config/authelia/notification.txt` instead of an inbox.
- **CrowdSec** (`crowdsecurity/crowdsec:v1.7.8` + the `maxlerebourg/crowdsec-bouncer-traefik-
  plugin` v1.6.0) - reads Traefik's access log (`crowdsec/acquis.yaml`), 59 scenarios loaded
  from the `crowdsecurity/traefik`, `crowdsecurity/http-cve`, and `crowdsecurity/base-http-
  scenarios` collections. `crowdsec@docker` bouncer middleware applied ahead of Authelia on
  every router; LAN/Tailscale ranges are exempted from bouncer checks
  (`clientTrustedIPs`) - this layer is built for the day a service is made public, not for
  today's LAN/tailnet-only traffic. Verified live: a manually-added ban decision for an
  untrusted-range IP got a real `403` at the Traefik layer, before Authelia ever saw the
  request; removing the decision restored normal access immediately.
- **Adminer** (`adminer:5.4.2-standalone`) - single-file PHP database browser in front of
  `dmm-mysql`, gated the same as every other service. Chosen over phpMyAdmin deliberately
  (smaller attack surface / CVE history for a one-file PHP app). Previously the only way to
  inspect DMM's Prisma-backed MySQL data was `docker exec -it dmm-mysql mysql ...`.

### Changed
- **All 18 previously host-published services** (Prowlarr, Zilean, Decypharr,
  Decypharr-AllDebrid, Zurg, Radarr, Sonarr, NZBGet, Seerr, Bazarr, Byparr, Tautulli,
  Control Panel, DebridMediaManager, Cleanuparr, NeutArr, Dozzle, Glances) had their `ports:`
  mapping removed and a `traefik.enable`/router/service label block added instead, one at a
  time - Glances went first as the pilot (validated the label pattern, then Authelia's forward-
  auth flow, before repeating it 17 more times), and each service's old direct port was
  confirmed closed before moving to the next. **Control Panel and Dozzle** (the two containers
  holding a Docker socket mount) were the actual priority behind this whole effort - Control
  Panel's own docstring had explicitly flagged its no-auth, read-write docker.sock access as
  "a deliberately higher-blast-radius exception"; that gap is closed now with zero code changes
  to either service, entirely at the network layer.
- **Plex** (`network_mode: host`, can't be discovered by Traefik's Docker provider the normal
  way since it isn't attached to `stacknet` at all) gets an explicit
  `loadbalancer.server.url: http://${HOST_IP}:32400` label instead of the usual port label -
  the one service that needed a different labeling approach.
- README's Security note rewritten to describe the new layered architecture in place of the
  old LAN-only-with-no-auth state; the three other places that referenced the old model
  (top-of-file "what this isn't" bullet, Control Panel's docker-socket note, the setup wizard's
  own no-auth note - genuinely still true, since that tool is ephemeral and runs *before*
  Traefik/Authelia exist) were each updated rather than left stale.

### Fixed (found live during this rollout)
- **Authelia's healthcheck used a removed CLI subcommand** - `authelia healthcheck` doesn't
  exist in 4.39.20; switched to `wget -qO- http://localhost:9091/api/health` directly.
- **CrowdSec's Traefik middleware silently failed to register** - `service
  "crowdsec-media-stack" error: port is missing"` in Traefik's logs, caused by its Docker
  provider trying (and failing) to build an implicit default service for any
  `traefik.enable=true` container that doesn't declare a port, which poisoned that container's
  *entire* label set including the middleware definition - not just a missing service. Fixed by
  giving the crowdsec container an explicit (unused-by-any-router)
  `loadbalancer.server.port: "8080"` label.
- **Authelia's identity-verification flow isn't a clickable email link on this stack** (no SMTP
  configured, filesystem notifier only) - it's a one-time code written to
  `config/authelia/notification.txt` that must be typed into the browser prompt. Retrying the
  2FA-enrollment step without that code tripped Authelia's own endpoint rate limiter
  (`/api/user/session/elevation`, ~3-4 minute cooldown), which surfaces to the user as a generic
  "Failed to generate the One-Time Code" error with no obvious cause.

### Known follow-up
- Public exposure (Tailscale Funnel or Traefik's ACME resolver) deliberately not enabled by any
  of the above - see README's Security note for the recommended path when that's actually
  wanted.
- Other devices (phones, other LAN machines) need the mkcert CA root installed separately to
  see a trusted padlock for `*.cave.internal` - it's currently only in this host's own system/
  browser trust stores.

## [8.2.0] — Plex additions now post to Discord instantly instead of on a 30-minute timer

Follow-up user request: "change the discord to fire after every addition as opposed to on a
timer." The [8.1.0](CHANGELOG.md) poster-boxart work still only ran on
`stack-plex-report.timer`'s 30-minute schedule - a newly added movie could sit unannounced for
up to half an hour. Verified this account actually has Plex Pass
(`myPlexSubscription: true` on the server's own `/` endpoint) before committing to Plex's native
webhooks as the mechanism, since that's the feature gate.

### Added
- **`scripts/plex-webhook-listener.py`** - new long-running HTTP listener
  (`systemd/stack-plex-webhook.service`, `Type=simple`/`Restart=on-failure`, no timer) bound to
  `127.0.0.1:${PLEX_WEBHOOK_PORT}` (new `.env` var, default `9880`). Parses Plex's
  multipart/form-data `library.new` webhook POST (stdlib-only, via the `email` package's own
  MIME parser rather than the removed-in-3.13 `cgi` module) and posts a Discord embed the
  instant Plex fires the event - synopsis plus boxart, using the poster Plex already attaches to
  the webhook when available, falling back to fetching `Metadata.thumb` from Plex's API for the
  rarer case where an item hadn't been matched yet. Posts are queued through a single background
  worker paced at ~1/second with a 429-triggered retry, rather than fired directly from the
  request thread, since a season-pack import fires one `library.new` per episode within seconds
  and posting that fast would blow through Discord's per-webhook rate limit and silently drop
  most of them. Requires a one-time manual step outside this repo: Plex web app → Settings →
  Webhooks → Add Webhook → `http://127.0.0.1:9880/plex-webhook` (account-level Plex setting, not
  something `PLEX_TOKEN` can configure via API) - documented in README.

### Changed
- **`scripts/plex-library-report.py` scope narrowed to removals only.** Plex has no
  "item removed" webhook event, so the 30-minute poll is still needed for that half of the
  picture, but the poster-embed/added-tracking logic added in [8.1.0](CHANGELOG.md) is now dead
  weight - reverted, and the snapshot format reverted with it (`guid -> "Title (Year)"` strings,
  matching what's already on disk at `~/.cache/plex-library-snapshot.json` - that file never
  actually got rewritten in the new dict shape by a live run, so this is a clean revert, not a
  migration). `label_of()` still accepts the brief dict shape defensively in case any other
  environment's snapshot passed through [8.1.0] before this shipped.

### Verified
Full request/response path exercised end-to-end against a local stand-in for Discord (not the
real webhook, to avoid firing unreviewed posts at the live channel): a realistic Plex
`library.new` multipart POST with an attached poster round-tripped correctly into a Discord
embed with the image re-uploaded as a file attachment; the `Metadata.thumb` fallback path fires
correctly when no poster is attached; a burst of 5 rapid additions was delivered in full with
~1-second pacing between posts (4.5s elapsed for 5 items). The removals-only rewrite of
`plex-library-report.py` was re-tested against the actual on-disk snapshot format. Ruff-clean.
Not yet verified against a real Plex-fired webhook or the live Discord channel - first real
`library.new` event once the webhook is registered in Plex's UI will exercise that.

---

## [8.1.0] — Plex library report: added items now post with real poster boxart

User request: "greatly enhance the discord notifications from Plex to show boxart if possible."
`scripts/plex-library-report.py`'s added/removed digest ([7.1.0](CHANGELOG.md)) only ever
posted plain text title lists - no images, since a naive `image: {url: ...}` pointed at
`PLEX_URL` wouldn't have rendered anyway (`PLEX_URL` is a LAN address, `http://192.168.4.105:32400`
per `.env` - Discord's own servers fetch embed image URLs server-side and can't reach it) and
would have leaked `PLEX_TOKEN` in the message besides.

### Added
- Each newly-added item (movie or show) now gets its own Discord embed with Plex's poster
  attached as a real file upload (`attachment://posterN.jpg` referencing a multipart file part),
  plus its synopsis. The poster is downloaded from Plex over the LAN and re-uploaded to Discord
  as bytes rather than linked, sidestepping both the unreachable-URL problem and the token leak.
  Stdlib-only multipart encoder added (`build_multipart`) - no new dependency taken on for this.
- Capped at 9 poster embeds per run (Discord's hard 10-embeds-per-message limit, minus the
  header embed) - items beyond the cap, and everything removed, still fall back to the previous
  truncated text-list summary on the header embed.
- Snapshot shape (`~/.cache/plex-library-snapshot.json`) changed from `guid -> "Title (Year)"` to
  `guid -> {title, year, thumb, summary}` so poster paths and synopses are available at diff
  time without extra Plex API calls. `label_of()` accepts both the old string shape and the new
  dict shape, so upgrading doesn't force a re-baseline on the first post-upgrade run.

### Verified
Diff/embed-building logic and the multipart encoder were exercised against mocked Plex
responses (baseline run, added-with-thumb, added-without-thumb, removed, and a >9-item overflow
case all produced the expected embed/field/attachment shapes) - not yet verified against a real
post to the live webhook, to avoid firing an unreviewed notification at the actual configured
Discord channel. First real run under `systemd/stack-plex-report.timer` will exercise the live
path.

---

## [8.0.0] — Pinchflat removed entirely; Lidarr/Readarr/Whisparr connections swept clean

User call, not a bug-driven removal: the storage setup Pinchflat's YouTube archiving needed
isn't there right now - "good app, just not doable for me" - same shape as the
[4.0.0](CHANGELOG.md) Whisparr removal, not a soft disable. While removing it, also swept for
any remaining directories/files/connections still pointing at Lidarr, Readarr, and Whisparr,
all three of which were fully removed in earlier versions ([7.0.0](CHANGELOG.md),
[4.0.0](CHANGELOG.md)) but hadn't been re-verified clean until now.

### Removed
- **Pinchflat** - container stopped and removed, `pinchflat` service block deleted from
  `docker-compose.yml`, `config/pinchflat/` deleted from disk (root-owned files - this image
  runs with no PUID/PGID support, so a privileged throwaway container was needed to actually
  remove them). `control-panel/app.py`'s `CONTAINER_LABELS` and `control-panel/static/app.js`'s
  `QUICK_LINKS` entries removed. README swept for every reference (Quick start, Contents, the
  service URL table, Resource limits, the dedicated `## Pinchflat` section, Optional extras
  reference, Control Panel's Quick Links description) - the dedicated section removed entirely,
  the rest updated in place.
- **`./media/adult`** - confirmed empty (0 files) and unreferenced anywhere in
  `docker-compose.yml` or Zurg's live `config.yml`, so removing the plain host directory needed
  no service restart, unlike the Zurg `config.yml` routing group itself (see README's own note,
  left alone for the reason already documented there - a live restart for zero benefit).
- **`config/heimdall/`, `config/homepage/`** - both apps were fully replaced by Control Panel
  back in v5.0.0 (no service block, no code reference to either left anywhere), but their config
  directories were still sitting on disk - 296K and 32K respectively, dashboard settings/
  bookmarks/widget config, nothing resembling real content. Confirmed disposable and removed
  (root-owned `homepage/logs/` again needed the privileged-container trick).
- **`./media/music`, `./media/books`** - unlike everything else in this entry, this *was* real
  content, not disposable app state: `./media/music` held a substantial personal collection
  (studio tracks, live recordings, rare mixes/demos), kept untouched through the Lidarr removal
  itself ([7.0.0](CHANGELOG.md)) on the explicit reasoning that library content and app state are
  different things. Removed here only after an explicit user decision to permanently delete it
  ("I will never use those directories") given as its own follow-up, not folded into the
  original Pinchflat/Lidarr/Readarr/Whisparr cleanup - flagged before acting that `./media/` has
  zero backup coverage (`backup-config.sh` only ever covers `./config`), so this has no
  restic snapshot to fall back on. `./media/books` was already empty. Plex's "Music" library
  keeps working via its other location (`/mnt/zurg/music`, the Real-Debrid FUSE mount) - only the
  local-disk location is now gone, left as a dead (non-crashing) entry in Plex's own library
  config rather than touched again after the last library-edit surprised with an unplanned Plex
  restart. README's directory layout and Plex library locations sections swept for the
  resulting stale `music`/`books` references.

### Verified clean, left alone
- **Prowlarr's applications list** - confirmed via `GET /api/v1/applications` to contain only
  Radarr and Sonarr, no lingering Lidarr/Readarr/Whisparr entries.
- **`config/neutarr/{lidarr,readarr,whisparr,eros}.json`** - NeutArr's own per-app-type config
  stubs, `api_url`/`api_key` both blank on all four. These aren't a real "connection" (nothing to
  disconnect) and are scaffolding NeutArr manages itself for every app type it supports whether
  used or not - left in place rather than deleted and risk the app just recreating them, or
  erroring, on next restart.

### Found while verifying
- **Deleting the orphaned Plex "YouTube" library triggered an unexpected internal Plex Media
  Server restart** - `DELETE /library/sections/{id}` reached Plex (confirmed in its own logs:
  a real stop/start cycle, "Sqlite3: Sleeping for 200ms to retry busy DB" repeated, then a
  clean reboot sequence), and the immediate follow-up check still showed the section present,
  so it looked at first like the delete had failed outright. It hadn't - the removal completed
  asynchronously behind that restart, confirmed by a later check showing only Movies/TV
  Shows/Music remain. The Docker container itself never went down (continuous uptime, `healthy`
  throughout) and the other three libraries' paths were confirmed unaffected.

### Verified live
- `docker compose config --quiet` (default + extras profile) clean after the service block
  removal.
- Rebuilt and force-recreated `control-panel`; confirmed healthy and the Quick Links panel no
  longer references Pinchflat.
- `du`/`find` confirmed `./media/music` and `./media/books` (the still-live Lidarr/Readarr
  library content, kept since [7.0.0](CHANGELOG.md)) were untouched by any of the above - real,
  substantial content (a large personal music collection) that this pass was careful not to go
  anywhere near.

## [7.2.2] — Claude Code Review: skip Dependabot PRs cleanly instead of failing

PATCH, CI-only. `.github/workflows/claude-code-review.yml` was showing a red X on every
Dependabot PR (`fastapi`, `uvicorn`, `docker`, `psycopg2-binary`, `actions/checkout`, etc. -
[7.2.0](CHANGELOG.md)'s new `pip`/`github-actions` ecosystems immediately surfaced a wave of
these): `Environment variable validation failed: ... ANTHROPIC_API_KEY, CLAUDE_CODE_OAUTH_TOKEN,
or workload identity federation ... is required`. Root cause was already diagnosed and dead-ended
by an earlier session (see this file's own top-of-workflow comment): GitHub withholds repository
secrets from `pull_request` runs triggered by `dependabot[bot]`, and switching the trigger to
`pull_request_target` to route around that (tried previously) makes
`anthropics/claude-code-action`'s own OIDC-based GitHub App token exchange fail instead (`401
Unauthorized - Invalid OIDC token`) - a structural incompatibility between the action and that
trigger type, not something fixable by reconfiguring secrets.

### Fixed
- Added `if: github.actor != 'dependabot[bot]'` at the job level, so the job shows a clean
  `skipped` instead of attempting and failing on Dependabot PRs. `Validate Compose` already
  gives those PRs real CI signal; the documented manual `@claude` PR-comment workaround (which
  triggers `claude.yml` instead, unaffected by any of this) still works for a human-requested
  review. The proper fix - splitting this into a `pull_request` (no secrets, uploads context) +
  `workflow_run` (runs on the base branch, has secrets) pair, which is GitHub's own recommended
  pattern for this exact scenario - would need `anthropics/claude-code-action` to support being
  invoked that way; not attempted here.

## [7.2.1] — Installation docs rewritten: real terminal output, wizard internals, more depth

Docs-only (PATCH per this file's own versioning policy). Rewrote the Quick start, Bringing the
stack up, Installer image, and Setup wizard sections substantially longer and more technical,
built entirely from real, verified material rather than illustrative snippets:

### Changed
- **Quick start** — added a step-by-step "what actually happens" walkthrough with real captured
  terminal output for both the fresh-install and re-scaffold cases, and the `entrypoint.sh`
  `FIRST_RUN` detection logic that decides which message you get. Corrected the two-pass diagram,
  which had drifted stale after [7.0.0](CHANGELOG.md) removed Lidarr/Readarr and this session
  added `PLEX_TOKEN` to `POST_BOOT_KEYS` - it said "paste the 4 keys in" when the real count is
  now 3 (`RADARR_API_KEY`, `SONARR_API_KEY`, `PLEX_TOKEN`).
- **Installer image** — added the full `Dockerfile`/`.dockerignore` contents with an explanation
  of why the "never touches your secrets" claim is structural (build-context exclusion) rather
  than just documented, plus a local-build example.
- **Setup wizard** — added a "How it actually works" walkthrough of `setup_wizard.py`'s three
  functions (`parse_env_example`, `render_form`, `render_env_file`) with real code excerpts, a
  real (sanitized) example `.env` from an actual wizard submission, and the exact conditional
  logic behind the confirmation page's "next step" hint. Documented a genuinely non-obvious
  behavior found while writing this: `render_form` renders non-post-boot fields before post-boot
  fields *within each section*, so the rendered field order doesn't match `.env.example`'s source
  order - discovered the hard way when a first attempt at scripting the wizard via Tab-key
  navigation put values in the wrong fields.
- **Bringing the stack up** — added the full `media-stack.service` unit contents, real
  `systemctl --user status` output from this stack's own host, and a real `docker compose up -d`
  re-run against the live (already-healthy) stack showing an in-place image recreate.

### Found while verifying
- **`rclone-alldebrid` was one patch behind its own compose pin** (`1.74.3` running vs. `1.74.4`
  pinned) - surfaced by capturing real `docker compose up -d` output for the docs above, not a
  new bug. Recreated cleanly this time and came up healthy; a Dependabot bump had apparently
  never been manually applied.
- Re-verified `github.com/WhispersOfJ/Stackalicious` against this repo file-by-file rather than
  by commit-message similarity alone: `docker-compose.yml`, `Dockerfile`, `entrypoint.sh`,
  `.dockerignore`, `.gitignore`, `control-panel/`, `scripts/*`, `TODO.md`, and `CHANGELOG.md` are
  byte-identical (`CHANGELOG.md` differs in exactly one line, the same `HOST_IP` sanitization
  pattern as `.env.example`). **`README.md` is not a synced copy** - Stackalicious carries its
  own distinct, much shorter (466 vs. this file's 1,381 lines pre-rewrite) public-facing README
  plus a separate `HOWTO.md` that doesn't exist in this repo at all. Whatever process keeps
  Stackalicious in sync clearly rewrites docs for a public audience rather than copying them, so
  this rewrite (and this repo's README generally) won't propagate there the way the code commits
  above do.

## [7.2.0] — Control Panel hardening, restart-ordering fix, CI gates, off-site backup

Source this time was a review of `github.com/WhispersOfJ/Stackalicious`, the public GitHub repo
under this same account. First confirmed what that repo actually is before trusting anything
found in it: its commit log is a same-day, paraphrased mirror of this repo's own CHANGELOG
history (latest commit at the time, `b951e97c`, was titled identically to this repo's own
v7.1.0 HEAD commit), and diffing `.env.example` between the two showed the *only* difference
is `HOST_IP`/`PLEX_URL`/`DMM_ORIGIN` sanitized to a placeholder subnet — everything else,
`control-panel/app.py` included, is the same content. So every finding below was independently
re-verified against this live repo (exact line numbers, real API calls, real container state)
rather than trusted from the review at face value — see the planning file this was built from.

### Added
- **CI gates in `.github/workflows/validate.yml`**: a var-diff step (every `${VAR}` referenced
  in `docker-compose.yml` now must have a matching key in `.env.example` — previously
  `docker compose config` just silently substituted an empty string for anything missing,
  which is exactly the failure mode that would have caught a real gap if one still existed),
  `shellcheck` (`ludeeus/action-shellcheck`) over `scripts/*.sh` + `entrypoint.sh`, and `ruff`
  over `control-panel/app.py` + `scripts/*.py`.
- **`pip` and `github-actions` Dependabot ecosystems** in `.github/dependabot.yml` —
  `control-panel/requirements.txt`'s pinned FastAPI/docker/httpx/psycopg2 versions and the
  Actions themselves (`actions/checkout@v4`, etc.) had nothing bumping them until now.
- **CSRF/Origin-Host validation middleware** in `control-panel/app.py`
  (`verify_same_origin`) — not auth (the "no auth, LAN-only" design in the Security note stays
  exactly as-is; a prior Caddy + HTTP Basic Auth layer was already tried and removed once).
  The real gap: the panel holds full read-write `docker.sock` access with zero Origin/Host
  check on any of its 15 POST endpoints, meaning any external website a LAN device's browser
  visited — not another device on the LAN, any website at all — could fire a same-origin-exempt
  POST at container start/stop/restart/exec. Rejects any POST/PUT/PATCH/DELETE whose `Host` or
  `Origin` header doesn't match `HOST_IP` (now passed into the container's environment) or
  `localhost`/`127.0.0.1`, with a 403 and a plain JSON body.
- **Off-site backup leg**, opt-in via two new blank-by-default `.env.example` vars
  (`BACKUP_REMOTE_REPOSITORY`, `BACKUP_REMOTE_PASSWORD_FILE`) — closes the "Known limitation"
  this file's own backup section already flagged (single physical disk, no remote copy). Any
  restic-supported URL works (B2/S3/sftp/rclone/etc.); `scripts/backup-config.sh` mirrors the
  same backup there with its own retention pass, tagged `(remote)` in every Discord
  notification so a local-only failure is never confused with a remote-only one. No-ops
  entirely if unset, same pattern `notify-discord.sh` already uses for
  `DISCORD_WEBHOOK_URL`.
- **Monthly restic integrity check** (`restic check --read-data-subset=10%`), piggybacked on
  the existing daily `stack-backup.timer` with a `date +%d = 01` guard rather than a second
  timer — runs against both the local repo and the remote one, if configured.
- **`scripts/enable-recycle-bin.py`** — one-off script (not a recurring job) that turns on
  Radarr/Sonarr's own Recycle Bin via `PUT /api/v3/config/mediamanagement/1`, reusing
  `arr-app-backup.py`'s `env_get()`/`api_request()` pattern. A blast-radius mitigation for the
  still-unsolved mass-deletion mystery below, not a fix for its root cause.

### Fixed
- **`BAZARR_API_KEY`/`PLEX_TOKEN`/`PLEX_URL` no longer crash the whole panel on boot** if
  unset — all three were `os.environ[...]` at import time (would take down every Control Panel
  feature for one missing optional key); now `.get()`, with `plex_headers()`/`bazarr_headers()`
  returning a clean `503` instead. `PLEX_TOKEN` also added to `setup_wizard.py`'s
  `POST_BOOT_KEYS` — it genuinely can't be known before Plex has booted and has a library item
  to read it from (same shape as the arr apps' own post-boot keys), so it was falling through
  the wizard's two-pass flow with nothing ever prompting for it.
- **`stack_restart_all()` had no dependency ordering** — restarted every container in
  whatever order the Docker API happened to list them, which could (and, per the
  README's own "Radarr-specific mount fragility" note and [4.0.1](CHANGELOG.md), reliably did)
  restart Zurg/Decypharr after Radarr and leave Radarr's direct `/mnt/zurg`/`/mnt/decypharr`
  binds stale. Now restarts `zurg`/`decypharr`/`decypharr-alldebrid`/`rclone-alldebrid` first,
  polls their own healthchecks (bounded, 60s), then the rest of the stack, then Radarr last.
- **One real pre-existing lint finding each**, surfaced by adding the new CI gates rather than
  introduced by them: an unused `header` variable in `scripts/import-imdb-data.py`
  (`ruff` F841), and a missing `|| exit` after `cd "$(dirname "$0")/.."` in
  `backup-config.sh`, `check-container-health.sh`, and `notify-discord.sh` (`shellcheck` SC2164).

### Found while verifying (new, unresolved — added to [TODO.md](TODO.md))
- **`rclone-alldebrid` doesn't reliably survive `docker restart`** — found live while testing
  the restart-ordering fix above with a real full-stack Restart-All. Its own `/mnt/all` FUSE
  mount came back `Transport endpoint is not connected` / `Socket not connected` and the
  container's own `unless-stopped` restart policy retried with growing backoff for 4+ minutes
  without ever clearing it on its own. Recovered manually: `docker run --rm --privileged -v
  /mnt:/mnt:rshared alpine umount -l /mnt/all` (lazy unmount from outside the container's mount
  namespace) followed by one `docker restart rclone-alldebrid`. Same failure class as the
  documented Radarr/Zurg bug, different container, no known one-line fix yet — and unlike
  Radarr's version, this one doesn't even self-heal with a single restart, so it would also
  bite a routine Watchtower-triggered restart, not just Restart-All.

### Verified live
- Blanked `BAZARR_API_KEY` and `PLEX_TOKEN` in `.env`, rebuilt + force-recreated
  `control-panel`, confirmed it stayed `healthy` (not crash-looping) and
  `POST /api/bazarr/search-wanted` / `POST /api/plex/scan` both returned a clean `503` with a
  plain-English message. Restored the real values, rebuilt again, confirmed both endpoints
  returned their normal success response.
- `curl -H "Origin: http://evil.example"` and `curl -H "Host: evil.example"` against a real
  POST endpoint both returned `403`; the same request with a real matching `Origin` returned
  `200` and actually restarted Glances, confirmed via `docker compose ps glances`.
- Triggered a real `POST /api/stack/restart-all` against the live 27-container stack (with
  explicit go-ahead first, given the blast radius). Watched the sweep with `docker compose ps`
  every 5s: `zurg`/`decypharr`/`decypharr-alldebrid` went healthy within ~15s,
  `rclone-alldebrid` hit its 60s timeout mid-incident (see above) without blocking the rest of
  the sweep, and Radarr restarted last and came back with `GET /api/v3/rootfolder` reporting
  `"accessible": true` — no manual follow-up restart needed, which is the exact failure this
  fix targets. All 27 containers ended up healthy (`dmm-migrate` correctly `Exited (0)` — a
  one-shot migration container, not a failure).
- `PUT /api/v3/config/mediamanagement/1` confirmed via a follow-up `GET`:
  `recycleBin: "/data/movies/.recyclebin"` (Radarr) / `"/data/shows/.recyclebin"` (Sonarr),
  both `recycleBinCleanupDays: 7`. Deliberately did **not** verify via a real deletion — that
  would mean removing real library content just to test a config change.
- Ran `backup-config.sh` for real: local backup + retention succeeded as before; the new
  remote/monthly-check blocks correctly no-op'd (`BACKUP_REMOTE_REPOSITORY` unset, not the 1st
  of the month) without touching the rest of the script's behavior.
- `ruff check control-panel/app.py scripts/*.py` and `shellcheck` over every `.sh` file both
  clean after all of the above; `docker compose config --quiet` (default + `extras` profile)
  and the new var-diff check both pass.

---

## [7.1.0] — Cleanuparr, NeutArr, Dozzle, and Pinchflat added; Discord alerts get real embeds

A pasted recommendation (from another AI conversation) suggested 5 new services plus a Huntarr
warning. Every claim was independently verified rather than trusted at face value before
anything was added - see the planning file this was built from. Two of the five suggestions
were turned down after review: **Notifiarr** requires routing app/library data through a
third-party cloud relay and a hosted Discord bot (confirmed via its own docs) - a categorically
different trust model than this stack's single self-controlled webhook, so its own Discord
alerting was upgraded instead (see below) rather than taking on that dependency. **Wizarr**
doesn't apply - solo Plex user, nothing to invite.

### Added
- **Cleanuparr** (`ghcr.io/cleanuparr/cleanuparr:2.9.16`, port 11011) - automates what Control
  Panel's own "unstick" endpoint and "search missing" buttons already did by hand, for the whole
  library on a schedule, plus a strike system and community malware blocklist neither button
  covered. Connected to Radarr/Sonarr and, as its download client, **Decypharr** - verified live
  via a real qBittorrent-API login, not just a connection test, resolving the one real unknown
  in the original recommendation. Queue Cleaner enabled (3-strike failed-import detection in
  `Exclude` mode with no exclusions, so nothing is scoped out; a 0-100%/both-privacy-types
  stalled-download rule, closing a coverage gap Cleanuparr's own UI flagged by default). Malware
  Blocker enabled for both apps against the community blocklist
  (`raw.githubusercontent.com/Cleanuparr/Cleanuparr/.../blacklist`, verified reachable before
  use) on an hourly schedule (the UI's own 5-second default was absurdly aggressive, changed
  before saving). Its own proactive missing-content search stays off - NeutArr owns that role,
  to avoid both apps redundantly hunting the same libraries against the same indexers.
- **NeutArr** (`iampuid0/neutarr:1.9.1`, port 9705) - a hardened Huntarr-lineage fork
  (`elfhosted/newtarr`'s fork of Huntarr v6.6.3, the last release before Huntarr's security
  scandal - see below), rebuilt auth, Bandit/pip-audit clean, specific CVEs patched. Connected
  to Radarr and Sonarr; verified live via both `Test Connection` calls succeeding
  (`Successfully connected to Radarr API version: 6.2.1.10461` in its own logs) and, more
  importantly, a real hunt cycle that found and searched for an actually-missing episode
  (`Law & Order - S09E13 - Hunters`) within minutes of being configured - not just a clean
  config, a real result.
- **Dozzle** (`amir20/dozzle:v10.6.8`, port 8080) - real-time log viewer, the one thing Control
  Panel's container grid couldn't do (state/health/CPU/mem, but no log content - previously a
  manual `docker logs`). Direct `:ro` docker.sock mount, same pattern Control Panel/Watchtower
  already use; no socket-proxy exists in this stack to slot behind (the pasted recommendation
  assumed one did - it doesn't), left as a possible separate hardening project rather than
  bundled into this one. Verified live: its own log confirms `"Connected to Docker", "clients":1`.
- **Pinchflat** (`ghcr.io/kieraneglin/pinchflat@sha256:01b4f98a...`, digest-pinned - newest
  tagged release `v2025.6.6` is meaningfully behind `:latest`, same reasoning as
  Seerr/Glances/Kometa/Unpackerr's existing digest pins; port 8945) - a new content vertical,
  YouTube channel/playlist archiving, writing real local files the same way NZBGet does. New
  `./media/youtube:/downloads` mount. One Media Profile created (`YouTube`, the built-in "Media
  Center" preset - Plex-friendly season/episode-by-date naming) - actual channel/playlist
  Sources deliberately left unconfigured, since that's a content choice, not infrastructure.
- **New Plex library, "YouTube"** (TV Shows type, matching Pinchflat's own recommended
  structure for episodic content), pointed at `/home/bear/Stack/media/youtube` - the same
  `./media:/home/bear/Stack/media` mount that already existed in `docker-compose.yml` waiting
  for exactly this (added ahead of time in an earlier session, per its own comment, but never
  acted on until now).
- **`scripts/notify-discord.sh` now posts real embeds** (title/color-by-severity/timestamp/host
  footer) instead of flat `{"content": "..."}` text - the visual upgrade Notifiarr would have
  provided, without its cloud dependency. Matches the embed style `plex-library-report.py` and
  `arr-app-backup.py` already built directly for their own posts; every caller
  (`backup-config.sh`, `check-container-health.sh`, `notify-failure@.service`) needed no changes
  - same `message [level]` call signature. Verified live with a real post to the configured
  webhook.
- **Control Panel** - `cleanuparr`/`neutarr`/`dozzle`/`pinchflat` added to `CONTAINER_LABELS`
  (`control-panel/app.py`) and `QUICK_LINKS` (`static/app.js`), same pattern as every other
  extras service. Verified live: all 4 appear correctly labeled and healthy in
  `GET /api/containers` after a rebuild.

### Fixed while verifying
- **Decypharr's admin password was unrecoverable** (bcrypt-hashed in `auth.json`, no plaintext
  anywhere, no documented reset flow) when Cleanuparr needed real credentials for the
  qBittorrent-API connection - generated a new password + matching bcrypt hash (via a throwaway
  `python:3.12-alpine` container, matching cost factor/prefix of the original), wrote it
  directly into `auth.json`, restarted Decypharr. This broke Radarr's and Sonarr's own existing
  Decypharr download-client connections, which had the old password stored - caught immediately
  (both apps' own connection tests failed) and fixed by updating both apps' stored credential to
  match, verified via a clean `200` re-test on both before moving on. Net downtime: none observed.
- **NeutArr's Radarr/Sonarr instance forms don't auto-save on selector switch** - filled in
  Sonarr, switched the type selector to Radarr without clicking Save first; caught via
  `settings_manager` logs still showing only `['sonarr']` configured after the Radarr form was
  filled and tested. Went back and saved explicitly; confirmed via the same log line updating to
  `['sonarr', 'radarr']`.

### Verified: the Huntarr warning in the original recommendation
Independently confirmed via `rfsbraz/huntarr-security-review`'s reproducible writeup, not just
the pasted claim: Huntarr v9.4.2 had an unauthenticated auth-bypass exposing every connected
`*arr` app's API keys in cleartext (`POST /api/settings/general` with zero credentials), and the
maintainer took the repo private/deleted it and banned people raising the issue on their own
subreddit rather than patching it. `MGHazz/huntarr.io-archive` preserves the abandoned repo
with an explicit "not under active development, use at your own risk" notice. Huntarr itself is
not used anywhere in this stack; NeutArr (above) is the vetted alternative.

---

## [7.0.0] — Lidarr and Readarr removed; Radarr/Sonarr get native Plex hooks + their own backups

MAJOR: two entire services removed, not just reconfigured. User's call after living with both
for a while - decided they weren't worth the ongoing hassle relative to how little they were
actually used. Bundled with two smaller additions that came up in the same pass: native Plex
library-update hooks on Radarr/Sonarr (previously nothing told Plex an import had happened -
only the manual "Scan for new files" button in Control Panel ever refreshed it), and a daily
native-backup script for the arr apps that remain.

### Removed
- **Lidarr and Readarr** - containers stopped and removed, service blocks deleted from
  `docker-compose.yml`, `config/lidarr/`+`config/readarr/` deleted from disk (their own
  app config/database only - the actual synced music/book library files under `./media/music`
  and `./media/books` were left untouched, since those are real library content, not app state).
  `LIDARR_API_KEY`/`READARR_API_KEY` removed from `.env` and `.env.example`.
- **Prowlarr applications** - both removed via `DELETE /api/v1/applications/{id}`, so indexer
  sync no longer targets either.
- **Unpackerr** - `UN_LIDARR_0_*`/`UN_READARR_0_*` env vars removed; it was extracting for both
  apps' queues, now just Radarr/Sonarr.
- **Zurg's `music`/`books` directory groups** - existed in `config/zurg/config.yml` only to
  organize content for Lidarr/Readarr to consume; removed as dead routing now that nothing
  reads from those folders, rather than left silently pointless. Live-edited and restarted
  (`docker restart zurg`) the same way this file's config has been touched before.
- **Control Panel** - `lidarr`/`readarr` removed from `ARR_APPS`/`CONTAINER_LABELS`
  (`control-panel/app.py`) and `ARR_APPS`/`QUICK_LINKS` (`static/app.js`). The `UNSTICK_ARR_APPS`/
  `MANUAL_IMPORT_ARR_APPS` split added in [6.8.0](CHANGELOG.md) specifically to give Lidarr
  unstick-only support collapsed back into a single `QUEUE_ARR_APPS` set (and the frontend's
  matching `unstick`/`manualImport` flags back into one `queue` flag) now that both remaining
  apps support both actions identically - keeping the split would have been unnecessary
  complexity with nothing left to differentiate.
- **`scripts/setup_wizard.py`** - `LIDARR_API_KEY`/`READARR_API_KEY` removed from
  `POST_BOOT_KEYS`.
- **README.md** - swept for every Lidarr/Readarr reference (architecture diagram, service
  table, configuration status list, image pinning policy, resource limits, Control Panel
  section, setup wizard docs) - some updated in place (service/key counts), some sections
  removed entirely where they no longer had anything to describe (Lidarr's blocked-uploader
  custom format, the Zurg music/books prerequisite write-up).

### Added
- **Native Plex Media Server connections** in both Radarr and Sonarr (`Settings → Connect`,
  not a generic webhook) - refreshes just the affected library section on import (`onDownload`)
  and upgrade (`onUpgrade`), rather than relying on someone noticing and clicking Control
  Panel's full-library "Scan for new files" button. Both point at `PLEX_URL`/`PLEX_TOKEN`
  directly, skipping the OAuth flow since the token's already on hand.
- **`scripts/arr-app-backup.py`** + `systemd/stack-arr-backup.{service,timer}`, daily at 03:40
  (after `stack-backup`'s 03:30 config snapshot, before Watchtower's 04:00 updates). Triggers
  each app's own native `Backup` command (`POST /api/v3/command`) and polls until it completes,
  producing the same portable `.zip` each app's own Settings → Backup screen creates on demand -
  a meaningfully different artifact than `backup-config.sh`'s raw file-level `./config`
  snapshot, and what each app's own restore flow actually expects as input. Scoped to
  Radarr/Sonarr only, matching this repo's own established meaning of "the arr apps" (Prowlarr
  and Bazarr both have an equivalent native backup mechanism, but neither is "an arr app" by
  that name).
- **`BAZARR_API_KEY`** added to `.env.example` - a gap from [6.8.0](CHANGELOG.md) that added it
  to `.env` and `docker-compose.yml` but missed the template file.

### Fixed while verifying
- **Plex itself was wedged** while testing the new notification hooks - stuck mid-restart from
  an unrelated earlier stop/start cycle (`Plex Media Server is already running. Will not
  start...` followed by a failed internal `kill`), timing out every real request despite Docker
  showing it `Up`. `docker restart plex` cleared it. Notification tests against Radarr/Sonarr
  failed with a connection timeout until this was caught and fixed - not a bug in the new hook
  config itself.

### Verified live
- `DELETE /api/v3/notification/test` (re-tested against each saved connection by id, not just
  at create time) returned a clean `200` for both Radarr and Sonarr - confirms real
  connectivity and auth against Plex, not just that the connection saved without error.
- Both apps' native `Backup` command completed successfully and produced real, listable
  `.zip` files (`GET /api/v3/system/backup`).
- Prowlarr's application list confirmed down to just Radarr/Sonarr after the removal
  (`GET /api/v1/applications`).
- Control Panel rebuilt and confirmed healthy; `GET /api/containers` no longer lists
  `lidarr`/`readarr`; `/api/arr/lidarr/unstick` now correctly `404`s instead of running.
- Zurg restarted healthy after the config edit; Plex connectivity reconfirmed unaffected.

---

## [6.8.0] — Control Panel: DMM's 4 containers labeled, Bazarr search + Lidarr unstick added

`CONTAINER_LABELS` in `control-panel/app.py` is display-only, not an allow-list - unlisted
containers still show up in the grid, just under their raw container name (see the code's own
comment). [6.2.0]'s 4 DMM containers had gone unlabeled since they were added; fixed as part of
a broader pass over what else the panel could usefully cover given everything else added since
it was last touched (the DMM stack, and this session's Bazarr work).

### Added
- **Container labels for DMM's 4 services** - `debridmediamanager`, `dmm-mysql`, `dmm-redis`,
  `dmm-migrate` (the last one correctly noted as "exits after running, not a bug if shown
  stopped" - it's a one-shot Prisma migration, not a long-running service).
- **DebridMediaManager added to Quick Links** - was missing since [6.2.0], same gap as above.
- **Bazarr "Search all wanted subtitles" primary action** - one click triggers Bazarr's own
  `wanted_search_missing_subtitles_series` and `_movies` scheduled tasks immediately via
  `POST /api/system/tasks`, bypassing their normal 6-hour interval. Same pattern as the existing
  Kometa/Plex primary action cards. Needed its own API key wired through - Bazarr's key was
  never mirrored into `.env` the way Radarr/Sonarr/Lidarr/Readarr's are, unlike every other
  `*arr` app's key already available to this container; added `BAZARR_API_KEY` to `.env` and
  `docker-compose.yml`'s `control-panel` environment block, matching the existing pattern.
- **Unstick extended to Lidarr** - the "remove + blocklist + re-search a stuck queue item"
  action (previously Radarr/Sonarr-only) now also covers Lidarr, using the identical
  `DELETE .../queue/{id}?blocklist=true&skipRedownload=false` pattern verified live, repeatedly,
  during [6.5.0]'s Metallica corrupted-archive investigation - this isn't speculative, it's the
  exact manual process from that investigation turned into a button. Manual import stayed
  Radarr/Sonarr-only - its file-to-item field mapping is Radarr/Sonarr-specific (`movieId` vs.
  `seriesId`/`episodeIds`) and was never adapted or tested against Lidarr's artist/album-shaped
  manual-import response, so extending unstick's queue coverage doesn't also silently extend
  manual-import into an untested, likely-broken state. `QUEUE_ARR_APPS` split into
  `UNSTICK_ARR_APPS` (`radarr`, `sonarr`, `lidarr`) and `MANUAL_IMPORT_ARR_APPS` (`radarr`,
  `sonarr`) to keep the two capabilities independently scoped going forward. Readarr excluded
  from both - never exercised against its queue this session, no live evidence its shape
  matches.

### Verified live
- Rebuilt and recreated the `control-panel` container; confirmed healthy.
- `GET /api/containers` shows all 4 DMM services with their new labels.
- `POST /api/bazarr/search-wanted` returned `200`; Bazarr's own `GET /api/system/tasks` showed
  `job_running: true` for both series and movies tasks immediately after.
- `POST /api/arr/lidarr/unstick` returned `200` - and genuinely found and fixed a real stuck
  item left over from [6.5.0]'s investigation (`Metallica - Load (1996) [MP3 320] 88`, never
  manually cleaned up after its second extraction failure), not just an empty "nothing to do"
  response.
- `GET /api/arr/lidarr/manual-import` correctly `404`s (`"manual import works on radarr and
  sonarr"`) - confirms the split didn't accidentally widen manual-import's scope too.
- `POST /api/arr/readarr/unstick` correctly `404`s - confirms Readarr wasn't accidentally
  included.

---

## [6.7.0] — Bazarr: English language wired up, default profile applied, real providers enabled

Bazarr was already connected to Sonarr and Radarr (`sonarr.apikey`/`radarr.apikey` in its own
config matched `.env`, confirmed live via `GET /api/system/status` returning real
`sonarr_version`/`radarr_version` strings, and all 6 series + 3 movies were already synced into
its library) but otherwise completely inert for actual subtitle fetching: **zero** languages
enabled, **zero** language profiles, **zero** subtitle providers (`enabled_providers: []`), and
no default profile set for new series/movies. It could see everything and do nothing with it.

### Added
- **English enabled** (`POST /api/system/settings`, `languages-enabled=en`).
- **Language profile "English"** (profileId `1`) — one item, plain English, not forced/HI-only.
  Set as the default for both new series and new movies going forward
  (`serie_default_enabled`/`movie_default_enabled` + matching `_profile` fields).
- **Applied retroactively** to the 6 series and 3 movies already synced from Sonarr/Radarr
  (`POST /api/series` / `POST /api/movies` with `profileid=1`) — the default-profile settings
  only apply to items added *after* being set, so existing library items needed an explicit
  bulk update or they'd have sat with no profile indefinitely.
- **Two subtitle providers enabled, both genuinely no-auth**: `gestdown` (TV-only, addic7ed
  alternative, zero signup) and `subf2m` (Subscene mirror, covers movies and TV, only needs a
  user agent Bazarr sets itself). Every other bundled provider needs a real account/API key
  this stack doesn't have credentials for, so these two are the only ones that could actually
  be turned on unilaterally.

### Fixed
- **Real bug hit while applying the profile retroactively**: `POST /api/series` and
  `POST /api/movies` both 500'd with `KeyError: 'audio_only_include'` the first time - Bazarr
  1.6.0's `list_missing_subtitles`/`list_missing_subtitles_movies` read a 6th field
  (`audio_only_include`) from each language-profile item that isn't documented in the
  `languages-profiles` POST schema itself, only surfaces once something actually tries to
  compute missing subtitles against the profile. The initial profile write (missing that field)
  returned a clean `204` and looked fully saved - the break only showed up one step later. This
  wasn't just a one-off for the retroactive bulk-apply either: the exact same code path runs
  automatically the moment `serie_default_enabled`/`movie_default_enabled` assigns the profile
  to any newly-synced series or movie, so leaving the field out would have silently broken
  every future Sonarr/Radarr sync's subtitle handling, not just this manual step. Fixed by
  re-posting the profile with `audio_only_include: "False"` added to its one item.

### Verified live
- `GET /api/system/languages` — English now shows `enabled: true`.
- `GET /api/system/languages/profiles` — profile `1` exists with the full 6-field item shape.
- All 6 series and all 3 movies show `profileId: 1` via `GET /api/series` / `GET /api/movies`,
  with real (non-error) missing-subtitle counts computed per item.
- **Real end-to-end subtitle search**: `GET /api/providers/episodes?episodeid=695` (a genuinely
  missing-subtitle Rick and Morty episode) returned actual `gestdown` results with real match
  scores (93, 86) and working download URLs - not just a clean API response, an actual
  subtitle found.
- The 3 Godfather movies correctly report zero missing subtitles because they already have
  embedded English tracks (`embedded_track_id` present in their `subtitles` list) - confirms
  the missing-subtitle logic is working correctly on the movie side too, not just silently
  reporting empty due to a bug.

---

## [6.6.0] — Lidarr: custom format added to reject the `88`/`vtwin88cube` uploader tag

Follow-up to [6.5.0]'s corrupted-archive investigation. Lidarr had no custom format support
configured at all (`GET /api/v1/customformat` returned `[]`) despite the API supporting it
(confirmed on the running `3.1.0.4875`), so every re-grab of a blocklisted album was still
eligible to land on another release from the same bad uploader - which is exactly what kept
happening across the ~4 manual blocklist rounds in [6.5.0].

### Added
- **Lidarr custom format `"Blocked Uploader (88 tag)"`** — one `ReleaseTitleSpecification`
  regex: `(?<!\d)88(?:cube)?\s*$`. Matches a trailing `88` or `88cube` release-title tag not
  preceded by another digit (so it catches `[FLAC] 88`, `[MP3 320] 88`, and `vtwin88cube`) while
  leaving genuine years alone - `(?<!\d)` blocks a match on the last two digits of `1988`, since
  those are preceded by `9`, a digit. Scored `-10000` in all three of Lidarr's quality profiles
  (`Any`, `Lossless`, `Standard` - Metallica's own profile is `Any`, but applied everywhere for
  the same reason Radarr/Sonarr's blocked-releases format is universal).

### Verified live
- `GET /api/v1/parse?title=...` against real titles from [6.5.0]'s investigation:
  `Metallica - Reload (1997) [FLAC] 88` and the `vtwin88cube` Kill 'Em All release both come
  back with `customFormatScore: -10000`; `Metallica - 72 Seasons (2023) [24Bit-48kHz] FLAC
  [PMEDIA]` (the clean replacement release that actually imported) comes back `customFormats: []`,
  `customFormatScore: 0` - confirms the regex doesn't false-positive on the album's release year
  or unrelated bracketed tags.

---

## [6.5.0] — Unpackerr was silently doing nothing; now wired up and extracting

User reported Lidarr had downloads stuck waiting on extraction. Checked Unpackerr's own logs
first rather than assuming the compose config was right: `No Starr apps or folders configured`
— it had been running since the service was first added with **zero API keys** set for any of
the four Starr apps (`UN_*_API_KEY` env vars were entirely absent, not just blank) and was only
mounted `/mnt`, missing every app's actual `/app/downloads/...` path, so even with keys it
couldn't have reached the archives to extract them. Readarr had never been wired in either.
Confirmed this had been inert for its entire runtime — no prior extraction ever appears in its
history.

### Fixed
- **`docker-compose.yml`** — `unpackerr` now sets `UN_RADARR_0_API_KEY`, `UN_SONARR_0_API_KEY`,
  `UN_LIDARR_0_API_KEY`, and `UN_READARR_0_API_KEY` (all reused from the existing `.env` keys
  each app already had). Added the missing volume mounts: `./config/decypharr/downloads`,
  `./config/decypharr-alldebrid/downloads`, and `./usenet`, alongside the existing `/mnt`, so
  every app's reported `outputPath` actually resolves inside the container.
- Container recreated (`docker compose up -d unpackerr`); startup log now shows all 4 apps as
  `1 server` with `apikey:true`.

### Found while verifying: separate, unrelated data-integrity issue
Once Unpackerr could actually reach Lidarr's queue, all 9 queued Metallica albums failed
extraction with an identical `rardecode: bad file checksum` error — reproduced independently
with the CLI `unrar t` too, so not a decoder bug. Repeated `md5sum` reads through the mount
were byte-for-byte identical, and Decypharr's own local cache showed a complete, single-range
file matching the expected size (no truncation). Cross-referenced Real-Debrid's own status via
Decypharr's API: all 9 show `status: downloaded`, `bad: false` — Real-Debrid itself doesn't
consider them corrupt. Conclusion: the source RAR archives are bad at the release level, almost
all sharing the uploader tag `88` (one also carried `vtwin88cube`) across *both* FLAC and MP3
encodes of the same albums — not a bug anywhere in this stack's mount, cache, or extraction
chain, but a single bad uploader's catalog being close to the only source for this artist on
the user's current indexers.

Blocklisted all 9 in Lidarr (`DELETE /api/v1/queue/{id}?blocklist=true&skipRedownload=false`),
which triggers Lidarr's own automatic re-search. Several rounds of re-grabs landed on more `88`
-tagged releases and failed the same way, requiring repeated manual blocklisting across roughly
4 rounds; **72 Seasons** and **Ride the Lightning** are confirmed fully re-imported clean this
session, from unrelated `PMEDIA` and `pea_soup` releases respectively. The remaining 7 were
still cycling through Lidarr's own retry logic (`autoRedownloadFailed: true`, already enabled)
when this entry was written — Lidarr will keep trying on its own without further intervention,
it's just a matter of whether non-`88` sources exist on the configured indexers for each
remaining album. Given how frequently re-grabs kept landing on the same tag, a Custom Format
rejecting `88`/`vtwin88cube` release titles in Lidarr would stop this at the source instead of
relying on failure-triggered retries - not yet added, since that's a call for the user to make
rather than something to apply unilaterally.

### Verified live
- Unpackerr's log: `Radarr Config: 1 server: ..., apikey:true`, same for Sonarr/Lidarr/Readarr.
- Test extraction succeeded end-to-end on a real archive before the corrupted batch was found,
  confirming the fix itself works and the later failures were data, not config.
- `GET /api/v1/history?eventType=downloadImported` confirms 72 Seasons' replacement release
  imported cleanly, track-by-track, with no checksum errors.

---

## [6.4.0] — Installer image now publishes multi-arch (amd64 + arm64)

Scoped deliberately to the two images this repo builds itself (the installer image,
`control-panel`) — every other service in `docker-compose.yml` just pulls a pre-built upstream
image, which Docker already resolves to the right platform automatically from that image's own
multi-arch manifest. DebridMediaManager's git-context build was explicitly left out of scope -
its own Prisma schema already declares `linux-arm64-openssl-3.0.x` as a binary target upstream,
suggesting they've thought about this, and it's not this repo's Dockerfile to modify anyway.

### Verified locally before touching CI, not assumed
- Installed QEMU arm64 emulation (`docker run --privileged tonistiigi/binfmt --install arm64`)
  and cross-built both Dockerfiles for real: `docker buildx build --platform linux/arm64`.
  Neither needed a single line changed - `FROM alpine:3.24` and
  `FROM python:3.12.7-slim-bookworm` are both already-multi-arch official images, and none of
  `apk add python3` or `pip install`'s five packages (`fastapi`/`uvicorn`/`docker`/`httpx`/
  `psycopg2-binary`) pull anything architecture-specific - confirmed `psycopg2-binary`
  specifically has a real `manylinux2014_aarch64` wheel, the one dependency here most likely to
  need a source compile instead.
- Ran the resulting arm64 installer image under emulation end-to-end (not just built it):
  scaffolded files into a mounted target, exit 0, correct file set written.
- Ran the resulting arm64 `control-panel` image under emulation: process stayed up, `docker
  top` showed a real `qemu-aarch64`-wrapped `uvicorn` process consuming CPU (not crash-looping),
  and the only failure hit (`KeyError: 'PLEX_URL'`) was from testing the container standalone
  without the env vars `docker-compose.yml` normally supplies - the exact same failure would
  happen identically on amd64 run the same way, not an architecture-specific bug.

### Added
- **`.github/workflows/publish-installer.yml`** — added `docker/setup-qemu-action@v3` and
  `docker/setup-buildx-action@v3` steps before the build, and `platforms: linux/amd64,
  linux/arm64` on the `docker/build-push-action@v6` step. Without both actions, `platforms:`
  alone isn't enough - QEMU is what actually executes arm64 instructions during `RUN` steps on
  the (amd64) GitHub Actions runner, and the buildx `docker-container` driver (not the default
  `docker` driver) is required to produce a multi-platform manifest list at all.

### Fixed
- **Stale "Homepage" reference in `entrypoint.sh`'s own first-run output** - found incidentally
  while testing the arm64 cross-build, not related to it. Homepage was removed and later
  replaced by Control Panel's Quick Links ([5.0.0]) but the success message users see after
  their very first `docker run` still told them to expect it. Updated to name what's actually
  there (`Bazarr/Byparr/Tautulli/Kometa/DebridMediaManager/etc.`).

---

## [6.3.2] — Quality profile renamed to "Unlimited"

Follow-up to [6.3.1] - user felt `720p+ (All Sources)` was a counterproductive name for the
profile now that the 1080p WEB/HDTV size caps are lifted, and asked for one shared name across
both apps reflecting the new setting plus the custom format already attached to it.

### Changed
- **Quality profile renamed `720p+ (All Sources)` → `Unlimited`** in both Radarr and Sonarr
  (`PUT /api/v3/qualityprofile/7`, same profile id in both apps, name only - no other setting
  touched).
- **Seerr's cached `activeProfileName` updated to match** (`PUT /api/v1/settings/{radarr,
  sonarr}/0`) - Seerr stores both the profile id and a display-name copy of it; the id (`7`)
  was still valid and nothing was actually broken, but the cached name would have gone stale
  and misleading otherwise. Same class of fix as [6.0.0]'s original Seerr repoint, caught
  proactively this time instead of discovered later.
- README's living documentation updated to describe the profile as `Unlimited` going forward;
  historical CHANGELOG entries ([6.0.0], [6.3.1]) left as-is, describing what was true at the
  time they were written.

---

## [6.3.1] — Sonarr: 1080p WEB/HDTV size cap raised to unlimited

User hit a batch of Sonarr rejection reasons in one search and asked to stop seeing them. Most
were Sonarr working as intended, not misconfiguration - explained rather than "fixed": a
blocklisted release (auto-blocklisted after a prior failed grab/import, by design), "multi-season
releases are not supported" (a hard Sonarr limitation, not a setting), "existing file meets
custom format cutoff" (a file already on disk already satisfies the profile's upgrade
threshold), and "episode wasn't requested"/"wrong season" (the release genuinely didn't match
the search scope). Only the size-limit rejection was a real tunable.

### Changed
- **`HDTV-1080p`/`WEBDL-1080p`/`WEBRip-1080p` quality definitions' `maxSize` set to unlimited**
  (`PUT /api/v3/qualitydefinition/{9,14,15}`) in Sonarr. The specific release that triggered
  this was 91.1GB for a 270-minute pack (~337 MB/min) against a 125-130 MB/min cap that matches
  TRaSH-Guides' own standard values - not misconfigured, but the user explicitly wants releases
  that size to get through going forward rather than raising the cap to a still-finite ceiling.
  Bluray-1080p and every other tier's cap were left as-is - only the three tiers actually
  discussed were changed.
- Live Sonarr app config only (not a `docker-compose.yml`/tracked-file change) - same category
  as [6.0.0]'s quality profile/custom format work, documented here per this file's own policy
  of versioning every real change regardless of whether it touches a file in this repo.

---

## [6.3.0] — DMM search actually works now: local IMDB title index populated, daily sync added

Closes the "keyword search still returns nothing" finding from [6.2.1] - planned first (Plan
mode) since it involves real engineering decisions (which tables actually matter, filtering
strategy, bulk-load mechanism, sync cadence). Full research preserved at
`~/.claude/plans/jaunty-munching-aurora.md`.

### Found by reading the actual query code, not assumed
- `src/services/database/imdbSearch.ts` (read directly from the pinned commit) only queries 3
  tables: `imdb_title_basics`, `imdb_title_akas`, `imdb_title_ratings`. The Prisma schema also
  has `imdb_title_episode`/`imdb_name_basics`/`imdb_genres`/etc. - none of these are referenced
  by any of the three search code paths (fulltext-on-basics, fulltext-on-akas fallback, LIKE
  fallback), so they weren't imported - narrower scope, faster import, no wasted effort on
  tables nothing reads.
- The search query's own filters (`title_type IN ('movie','tvSeries','tvMiniSeries')`,
  `is_adult = 0`, plus an INNER JOIN against `imdb_title_ratings` in every code path) define
  exactly what's worth importing - filtering on import to match is strictly better than
  importing everything unfiltered, since anything outside that filter could never surface in a
  result regardless.
- Real dataset sizes checked live (`curl -sI`) before committing to an approach:
  `title.basics.tsv.gz` 224MB, `title.akas.tsv.gz` 506MB, `title.ratings.tsv.gz` 8.5MB
  (compressed). Host had 900GB free - no space concern, filtering still saves real import time.

### Added
- **`scripts/import-imdb-data.py`** (stdlib-only Python, matching `scripts/setup_wizard.py`'s
  existing convention) - streams each `.tsv.gz` directly from `datasets.imdbws.com`, filters
  in-flight (no unfiltered file ever touches disk), and pipes filtered TSVs into `dmm-mysql` via
  `docker exec` stdin rather than a direct host bind-mount write - caught live: MySQL's own
  entrypoint chowns its `secure_file_priv` directory to a container-internal uid on every
  startup, which blocked host-side writes to a `:ro`-mounted path entirely (also caught and
  fixed: the mount can't be `:ro` at all, for the same chown reason). `TRUNCATE` + `LOAD DATA
  INFILE` per table, full refresh each run (IMDB's dumps aren't diff-friendly).
- **`./config/dmm-mysql-import` bind mount** on `dmm-mysql`, landing at
  `/var/lib/mysql-files/import` - matches MySQL 8.4's secure default
  (`secure_file_priv=/var/lib/mysql-files/`, confirmed live) rather than loosening
  `local_infile` globally.
- **`systemd/stack-imdb-sync.{service,timer}`** - same tracked-in-repo-then-symlinked pattern
  and `notify-failure@%n.service` wiring as every other `stack-*` unit. **Daily**, 04:15 (after
  the 03:30 backup, matching IMDB's own daily publish cadence - a deliberate choice over a
  lighter weekly default, confirmed with the user given the recurring ~750MB/day cost).
- **`dmm-mysql`'s resource ceiling raised** (`mem_limit` 1g→2g, `mem_reservation` 128m→256m) -
  now holds low millions of rows with `@@fulltext` indexes to maintain, not just small
  app-state tables.
- **`TZ` added to all 4 DMM containers** (`dmm-mysql`, `dmm-redis`, `dmm-migrate`,
  `debridmediamanager`) - none of them used the `<<: *common` anchor that normally sets it, so
  all four were silently running on UTC. `debridmediamanager`'s startup command also gets
  `tzdata` installed alongside the `openssl`/`curl` fix from [6.2.0] - `TZ` alone doesn't
  resolve DST/offset correctly without the zoneinfo database present. Fixes DMM's "Added"
  column showing UTC instead of local time.

### Verified live
- First manual run (before scheduling it): `basics=1,112,130 ratings=479,905 akas=6,883,614` -
  cross-checked directly against `dmm-mysql` with `SELECT COUNT(*)`, not just the script's own
  exit code.
- **The real test**: `GET /api/search/title?keyword=Yellowstone%202018`, the same query that
  returned `{"results": []}` in [6.2.1] - now returns `tt4236770` (the real 2018 show) ranked
  first with the correct rating (8.6). Confirmed again in an actual browser at
  `/search?query=Yellowstone+2018` - real poster art, correct title/year, not just a JSON
  response.
- `docker exec debridmediamanager date` now reports `EDT` (America/New_York), confirming the
  TZ fix took effect, not just that the env var is set.
- Checked whether the now-much-larger `dmm-mysql` changed the nightly `mysqldump` backup step's
  cost profile ([6.2.0]'s addition): 16.5s, 124MB compressed - still perfectly reasonable, no
  change needed.

---

## [6.2.1] — DMM's TMDB/OMDb/MDBList/Trakt keys reused from Kometa instead of left as changeme

User asked to reuse whatever API credentials Kometa already has configured
(`config/kometa/config.yml`) rather than sign up fresh. Kometa had real keys for exactly the
services DMM needed: `tmdb.apikey`, `omdb.apikey`, `mdblist.apikey`, and `trakt.client_id`/
`client_secret` all matched DMM's env vars 1:1, so they were copied into `.env` directly -
closes the "still `changeme`" follow-up from [6.2.0].

### Added
- **`GH_PAT`** wired into `debridmediamanager`'s environment (wasn't included in 6.2.0's env
  var list at all) - reused from Kometa's `github.token`. Genuinely optional (GitHub API
  rate-limit relief only), not related to the OAuth-login/sponsor-tier providers deliberately
  skipped in [6.2.0] - a distinct category that got missed in that pass.
- `.env.example` updated to note Kometa reuse as the first option before a fresh signup.

### Verified live
- Recreated `debridmediamanager`; confirmed the real values landed inside the running
  container (`docker exec ... echo $TMDB_KEY` etc.), not just written to `.env`.
- **New finding, not yet actionable**: tested `GET /api/search/title?keyword=Yellowstone`
  post-fix - still returns `{"results": []}`. Read the actual route source
  (`api/search/title.ts`): it queries a *local* IMDB title index
  (`db.searchImdbTitles`, backed by the `imdb_title_basics`/`Titles` tables) rather than
  calling TMDB/MDBList live - confirmed both tables have `0` rows. `TMDB_KEY`/`MDBLIST_KEY`
  are used *after* a title is identified (feeding `generateScrapeJobs`), not for the keyword
  search itself. So real API keys alone don't make search return results - populating the
  local IMDB title index (IMDB's public non-commercial dataset dumps -
  `title.basics`/`title.akas`/`title.ratings`/`title.episode`/`name.basics`, a genuinely
  separate, sizeable ETL task) would be needed for that, and wasn't in scope for this pass.
  Flagging rather than silently leaving it a mystery why search still looks empty.

---

## [6.2.0] — DebridMediaManager self-hosted (4 new services)

User asked to self-host [DebridMediaManager](https://github.com/debridmediamanager/debrid-media-manager)
(the app behind debridmediamanager.com) locally, "with all of the optional settings it comes
with" - including its own scraper-driven search, not just personal library browsing. Planned
first (Plan mode) since the actual env vars, Docker setup, and database requirements weren't
fully documented upstream - researched directly against the repo (Dockerfile, docker-compose.yml,
Prisma schema, scraper source) rather than assumed. Full plan, including three explicit scoping
decisions made with the user beforehand (scraper pipeline vs. personal-library-only; OAuth
login providers; the Tor proxy container), is preserved at
`~/.claude/plans/jaunty-munching-aurora.md`.

### Added
- **`dmm-mysql`** (`mysql:8.4`) - dedicated database, own container (same "each app-specific DB
  gets its own instance" pattern as `zilean-postgres`). MySQL is hard-required here, not
  swappable for Postgres/MariaDB - DMM's own `prisma/schema.prisma` hardcodes
  `provider = "mysql"` and uses MySQL-specific column types plus `@@fulltext` indexes.
- **`dmm-redis`** (`redis:7-alpine`) - rate limiting, matches upstream's own reference
  `docker-compose.yml` exactly.
- **`dmm-migrate`** - one-shot init container (`npx prisma db push --accept-data-loss`,
  `restart: "no"`) for first-run schema setup, since DMM's `package.json` has no migration
  runner and no `prisma/migrations` history to run `migrate deploy` against. Verified live: all
  55 tables from the full Prisma schema landed correctly in a single run (confirmed via
  `SHOW TABLES` against the fresh database, not just a clean exit code).
- **`debridmediamanager`** - the web app, port `3000`. No pre-built image exists anywhere
  (checked GHCR and Docker Hub) - built from source via a **git-context build pinned to a
  specific commit** (`c2ceef94477e49ddd5c55606bf57959ffdf29b9e`), not `main`, consistent with
  this stack's pin-everything policy (see README's Image pinning policy) - an unpinned git ref
  would be the self-built equivalent of `:latest`.

### Two real upstream bugs found and worked around live (not vendored/forked)
- **BuildKit wasn't installed on the host at all** (`docker-buildx` package missing) - the
  Dockerfile's `RUN --mount=type=cache` syntax needs it. User installed it (`sudo pacman -S
  docker-buildx`); confirmed working via `docker buildx version` before retrying the build.
- **Prisma binary-target mismatch** - the Dockerfile's `deploy` stage generates the Prisma
  Client without `openssl` installed, so Prisma can't detect the real OpenSSL version and
  silently generates the wrong query engine (`debian-openssl-1.1.x` instead of the actual
  `debian-openssl-3.0.x` runtime) - the app then crash-loops on startup unable to find a
  matching engine. Not fixable via `docker-compose` alone without vendoring a modified
  Dockerfile (which would lose the clean pin-by-commit setup and create an ongoing
  upstream-sync burden). Worked around instead: both `dmm-migrate` and `debridmediamanager` run
  from the Dockerfile's `build` stage (`target: build`) rather than the default `deploy` stage -
  that stage has the full toolchain, so `debridmediamanager`'s `command:` installs `openssl`
  (plus `curl`, for the healthcheck - caught live in a second pass: the app was actually up and
  serving the whole time, but the healthcheck itself was failing with "curl: executable file
  not found") and regenerates the Prisma Client correctly before starting via plain `next start`
  (this stage's regular, non-pruned `.next` build output, not the standalone server binary
  which isn't produced here). Costs somewhat more RAM (full `node_modules` present) - `mem_limit`
  set to `1.5g` accordingly, above the usual "no observation yet" default.
- Backup coverage closed proactively this time (not discovered missing later, unlike
  `zilean-postgres`'s gap in [5.1.0]): `scripts/backup-config.sh` gets a `mysqldump` step for
  `dmm-mysql` alongside the existing `pg_dump` step, same reasoning and naming convention.

### Verified live
- All four containers `healthy`; `dmm-migrate` exits `0` after a clean schema push.
- `GET /api/healthz` returns `{"status":"ok"}`, `GET /` returns `200`.
- Loaded `http://localhost:3000` in a real browser: correctly redirects to `/start` and renders
  DMM's actual login screen (Real-Debrid/AllDebrid/Torbox options, "no data stored on our
  servers" messaging confirming client-side credential storage) - not just a health-check pass.
  No console errors on a clean page load.
- **Deliberately not done**: logging in with real debrid credentials, or testing an actual
  per-title scrape - both need the user's own account credentials entered client-side
  (`localStorage`, never a server secret by DMM's own design), which wasn't done on their
  behalf, consistent with how every other sensitive credential was handled this session.

### Known follow-up (not done this session)
- **`TMDB_KEY`/`MDBLIST_KEY` are still `changeme`** - these are required in practice (not just
  "optional" like upstream's own `.env.example` implies) for the on-demand per-title scraper to
  resolve anything; search/scrape won't produce results until the user signs up for free keys
  at themoviedb.org and mdblist.com and updates `.env`, then recreates `debridmediamanager`.
  `OMDB_KEY`/`TRAKT_CLIENT_ID`/`TRAKT_CLIENT_SECRET` are genuinely optional and can stay
  `changeme` indefinitely.

---

## [6.1.0] — Sonarr now prefers season packs; Zilean set to top indexer priority

### Added
- **Custom format "Prefer Season Packs"** (Sonarr id 2) — a single `ReleaseTypeSpecification`
  set to `Season Pack` (value `3`), scored `+25` in the `720p+ (All Sources)` profile
  (`formatItems`). Uses Sonarr's own release parser to distinguish season packs from single/
  multi-episode releases, rather than a title regex - more reliable, and Sonarr-only (Radarr has
  no such specification, no episodes/seasons to distinguish). This is a *preference*, not a
  requirement: a positive score only outranks other releases at the identical quality tier, it
  doesn't block single-episode grabs when no season pack exists yet.
- **Verified live** against Sonarr's own `/api/v3/parse` endpoint (real parser evaluation, not
  a guess): `Yellowstone.S05.2160p.WEB.H265-GGEZ` parses `fullSeason: true`, matches the format,
  scores `+25`. Both `Yellowstone.S05E03...` (single) and `Yellowstone.S05E03-E04...`
  (multi-episode) parse `fullSeason: false`, match nothing, score `0`.

### Changed
- **Zilean's indexer priority set to `1`** (highest - Prowlarr's priority scale is `1`-`50`,
  lower is more preferred, matching Sonarr/Radarr's own convention) via `PUT /api/v1/indexer/
  13`, up from the default `25` every bulk-added indexer in [5.2.0] got. Triggered
  `ApplicationIndexerSync` afterward so the new priority propagates down to the 4 connected
  *arr apps (`fullSync` on all of them) instead of only living in Prowlarr's own database.

---

## [6.0.3] — Fixed: every AllDebrid-sourced Sonarr grab was stuck at import forever

User reported Sonarr stuck on `Yellowstone.2018.S05E03.2160p.WEB.H265-GGEZ[rarbg]` with "No
files found are eligible for import in /app/downloads/sonarr-ad/...". Not a one-off - this
affected every single release grabbed through the `Decypharr-AllDebrid` download client, since
the second, isolated Decypharr instance added to keep AllDebrid exclusive to Sonarr (see
[Architecture](README.md#architecture)) never got its own downloads folder mounted into
Sonarr's container. `Decypharr-AllDebrid` reports `outputPath` as `/app/downloads/<category>/
...` to Sonarr's API - identical-looking to the primary `decypharr` instance's own path
convention - but it's actually a different host directory
(`config/decypharr-alldebrid/downloads`, not `config/decypharr/downloads`). Confirmed live:
`docker exec sonarr ls /app/downloads/sonarr-ad/...` → "No such file or directory", while the
same path existed fine on the host and inside the `decypharr-alldebrid` container itself.

### Fixed
- **`docker-compose.yml`** — added `./config/decypharr-alldebrid/downloads:/app/downloads-ad:
  rslave` to Sonarr's volumes. Can't bind both decypharr instances' downloads at the literal
  `/app/downloads` (one container path, one mount), so this one lands at a second path instead.
- **Remote Path Mapping added in Sonarr** (`POST /api/v3/remotepathmapping`) for the
  `Decypharr-AllDebrid` download client specifically: `host: decypharr-alldebrid`, `remotePath:
  /app/downloads/`, `localPath: /app/downloads-ad/` - translates what that download client's
  API reports into where Sonarr should actually look on its own filesystem. The
  `Decypharr-AllDebrid` client's one exception to the "identical paths, no Remote Path
  Mappings" rule the rest of this stack follows (see [Architecture](README.md#architecture)).
- Sonarr recreated (`docker compose up -d sonarr`) to pick up the new mount.

### Verified live
- `docker exec sonarr stat -L` on the symlinked file resolved to a real, readable 5.99GB file
  (not a stale FUSE handle) before touching Sonarr's own import logic.
- Triggered `RefreshMonitoredDownloads`; the stuck queue item cleared on its own within seconds
  - `GET /api/v3/episode/113` now shows `hasFile: true`, `episodeFileId: 13`, and
  `GET /api/v3/history?episodeId=113` shows a `downloadFolderImported` event. Confirmed the
  actual symlink exists in the library at `media/shows/Yellowstone (2018)/Season 5/
  Yellowstone.2018.S05E03.2160p.WEB.H265-GGEZ[rarbg].mkv`, resolving through
  `/mnt/decypharr-alldebrid`.

---

## [6.0.2] — CI: Dependabot's GHCR auth failure on the Zurg image actually fixed

The second of the two failures found in [6.0.1] - this one closed out for real.

### Fixed
- **`.github/dependabot.yml`** — added a `registries:` block (`ghcr-zurg`, `type:
  docker-registry`, `url: ghcr.io`) so Dependabot's `docker-compose` update job can
  authenticate against the sponsor-gated `debridmediamanager/zurg` image instead of failing
  outright with `private_source_authentication_failure` on every run. Credential is
  `DEPENDABOT_GHCR_TOKEN`, a classic PAT scoped to `read:packages` only, set in the
  **Dependabot** secrets store specifically (`gh secret set ... --app dependabot`) - a
  separate store from the Actions secrets used for [6.0.1], which Dependabot's own update
  jobs don't read from at all.

Checked GitHub Actions CI status after the [6.0.0] push and found two persistent failures on
Dependabot-authored PRs. Root-caused both; genuinely fixed neither.

### Investigated: `claude-code-review.yml` failing on every Dependabot-authored PR
- **Symptom**: `ANTHROPIC_API_KEY, CLAUDE_CODE_OAUTH_TOKEN... is required`, consistently, on PR
  #6's rclone bump — despite `CLAUDE_CODE_OAUTH_TOKEN` being set as a repo secret (`gh secret
  set`, confirmed present via `gh secret list`).
- **Root cause confirmed**: GitHub withholds repository secrets from `pull_request`-triggered
  workflow runs when the triggering actor is `dependabot[bot]`, a hardening measure against a
  malicious dependency bump exfiltrating them. Confirmed by testing the *other* Claude workflow
  (`claude.yml`, comment-triggered via `issue_comment`) on the same PR with the same secret — it
  succeeded, proving the secret itself was valid and the restriction was specific to the
  `pull_request` trigger + Dependabot actor combination.
- **Attempted fix, reverted**: switched the trigger to `pull_request_target`, which runs in the
  base branch's trust context regardless of actor - confirmed this genuinely solved the secrets
  problem (`CLAUDE_CODE_OAUTH_TOKEN` was read correctly on the next Dependabot-actor run). But
  `anthropics/claude-code-action`'s own OIDC-based GitHub App token exchange then failed on that
  same run (`401 Unauthorized - Invalid OIDC token`), specific to `pull_request_target`'s token
  claims - outside anything fixable from this repo's side, since it's Anthropic's backend
  rejecting the token. Reverted to `pull_request` rather than leave it in a differently-broken
  state.
- **Net effect, unchanged from before this session**: `claude-code-review.yml` still won't
  auto-fire on Dependabot-authored PRs. Working alternative, confirmed live: commenting
  `@claude` on the PR triggers `claude.yml` instead, which reviews/responds correctly even on a
  Dependabot PR - one manual comment per PR that needs it.

### Investigated, not attempted: Dependabot's own `docker_compose` update job failing
- **Symptom**: `private_source_authentication_failure` against `ghcr.io` when checking
  `debridmediamanager/zurg` for updates.
- **Root cause**: that image is the sponsor-gated Zurg build (see `docker-compose.yml`'s own
  comment on it, not the public `zurg-testing` image) - Dependabot needs a registry credential
  to check a gated image for updates at all, and none is configured.
- **Fix, not done this pass**: add a `registries:` entry to `.github/dependabot.yml` pointing at
  a GHCR token secret.

---

## [6.0.0] — Quality profiles and blocklist custom format rebuilt from zero

**Breaking/foundational**: every pre-existing quality profile in Radarr and Sonarr was deleted
and replaced with a single new one in each app, changing what releases either app will accept
at all. User asked for a blocklist custom format (samples, Russian in any way, a specific
low-quality-source/group regex) scored `-10000`, then to delete every existing quality profile
and replace it with one profile covering all qualities 720p and up with that format attached. A
follow-up message asked for Korean characters to be added to the same format alongside Russian.

Found 0 custom formats and only the 6 stock default profiles (Any/SD/HD-720p/HD-1080p/
Ultra-HD/HD-720p-1080p) in both apps before starting — see the 2026-07-09 note above. Confirmed
via each app's `/api/v3/movie` and `/api/v3/series` that 0 movies and 0 series exist in either
library before deleting anything, so no reassignment was needed and nothing could break from
the deletion itself.

### Added
- **Custom format "Block - Sample, Russian, Low-Quality Sources"** (id 1 in both apps,
  `POST /api/v3/customformat`), four `required: false` Release-Title/Language specifications
  OR'd together — any one matching rejects the release:
  1. `Sample` (`ReleaseTitleSpecification`) — `(?i)\bsample\b`.
  2. `Russian Language` (`LanguageSpecification`) — built-in language value `11` (Russian),
     matches on Radarr/Sonarr's own parsed-language metadata.
  3. `Russian/Korean Text or Script` (`ReleaseTitleSpecification`) — catches Russian/Korean
     "in any way" beyond just the declared-language field: literal `rus`/`russian`/`kor`/
     `korean` text tags, plus the actual Cyrillic (`[Ѐ-ӿ]`) and Hangul
     (`[가-힣ᄀ-ᇿ㄰-㆏]`) Unicode ranges, so a release with Cyrillic or
     Hangul characters in the title matches even if nothing tagged its language metadata
     correctly. Korean added in a same-day follow-up to the initial Russian-only version.
  4. `Blocked Sources or Groups` (`ReleaseTitleSpecification`) — user-supplied regex:
     `` (?i)\b(WEB-DL|WEBRip|BDRip|HDRip|DVDRip|HDTV|AMZN|NF|DSNP|CR|YTS|TGX|TorrentGalaxy|FGT|LOL|KILLERS|EPSiLON|Erai-raws)\b|rartv|rarbg|eztv ``.
     Narrower than the old [4.12.0]/README "Blocked Releases (All Qualities)" format's
     equivalent condition (that one also had `BluRay\.x264|HDTV\.x264|HDTV\.XviD|WEB\.x264|
     WEB\.h264` and a separate BR-DISK-disc-release regex folded in) — this session implemented
     exactly the regex given, not the fuller historical one. Worth revisiting if the narrower
     coverage turns out to matter in practice.
- **Quality profile "720p+ (All Sources)"** (id 7 in both apps, `POST /api/v3/qualityprofile`)
  — the one profile in each app now. Allows HDTV/WEBDL/WEBRip/Bluray at 720p, 1080p, and 2160p,
  plus Remux at 1080p and 2160p; `upgradeAllowed: true`, cutoff set to the top tier
  (`Remux-2160p` in Radarr, `Bluray-2160p Remux` in Sonarr) so it keeps upgrading toward the
  best available. `BR-DISK` and `Raw-HD` deliberately left disallowed despite nominally being
  "1080p" — full disc images and raw broadcast captures are specialty formats essentially
  nobody wants in a general-purpose profile; a judgment call, not something explicitly asked
  for, flagged to the user at the time. Custom format id 1 wired in at `formatItems: [{"format":
  1, "score": -10000}]`; `minFormatScore` left at its default `0`, so a `-10000` match is a hard
  reject, not just deprioritization.

### Removed
- All 6 pre-existing quality profiles in both Radarr and Sonarr (`DELETE
  /api/v3/qualityprofile/{1..6}`, all 200s) — Any, SD, HD-720p, HD-1080p, Ultra-HD, and
  HD-720p/1080p in each app.

### Fixed
- **Seerr's stored Radarr/Sonarr connections** — confirmed via `config/seerr/settings.json`
  (readable directly on disk) that both still pointed at `activeProfileId: 6`
  (`"HD - 720p/1080p"`, one of the deleted stock profiles). The earlier unauthenticated `GET`
  attempt (no header at all) is what hit the session-cookie requirement, not the endpoint
  itself — `main.apiKey` from that same `settings.json` file works fine as `X-Api-Key` on the
  same `/api/v1/settings/*` routes. Repointed both to `activeProfileId: 7` /
  `"720p+ (All Sources)"` via `PUT /api/v1/settings/{radarr,sonarr}/0` and confirmed the change
  persisted on a fresh `GET`.

---

## [5.2.0] — Prowlarr rebuilt from zero: 68 indexers, Byparr proxy, Zilean

Found Prowlarr with 0 indexers and 0 indexer proxies configured — see the 2026-07-09 note
above; README already documented 70 indexers (69 public + Zilean) and Byparr as an Indexer
Proxy as if this were already done. Rebuilt via `/api/v1/*` directly rather than clicking
through the UI, same approach the original setup used.

### Added
- **Byparr registered as a `FlareSolverr`-implementation Indexer Proxy** (`POST
  /api/v1/indexerproxy`, id 1) — `host: http://byparr:8191/`, `requestTimeout: 60`. A
  `flaresolverr` tag (id 1) was created and applied to both the proxy and every indexer added
  below, since Prowlarr routes an indexer through a proxy by shared tag, not a per-indexer
  proxy-id field.
- **68 indexers added** — every `privacy: public` definition in Prowlarr's own
  `/api/v1/indexer/schema` catalog (623 total definitions; 86 public) that didn't need
  credentials this stack doesn't have, plus Zilean:
  - 67 of the 86 public definitions were addable with zero extra input beyond defaults.
    3 were deliberately skipped rather than added broken: `nekoBT` (needs a personal API key),
    `showRSS` and `Torrent RSS Feed` (both need a personal cookie/feed URL) — none of those
    credentials exist on this host.
  - 16 of the remaining addable ones failed Prowlarr's live connectivity test and were **not**
    saved — `forceSave=true` on `POST /api/v1/indexer` does not skip Prowlarr's live test the
    way it does for some other Servarr-family endpoints, it only bypasses non-connectivity
    validation. Failures were a mix of actually-dead/moved domains (`connection refused`,
    `timed out`) and active Cloudflare blocks even through Byparr (`1337x`, `52BT`) — real
    attrition against a bundled definition catalog against 2026-era sites, not a bug in the
    approach. Full pass/fail list in the session, not reproduced here.
  - **Zilean** added as a `Generic Torznab` indexer (`baseUrl: http://zilean:8181`, `apiPath:
    /torznab/api`, using `ZILEAN_API_KEY`) — confirmed its Torznab `?t=caps` endpoint responds
    correctly first, then added and live-tested with a real query (`?query=matrix`) through
    Prowlarr's own `/api/v1/search`: 29 results including several 4K remuxes.

### Verified live
- `GET /api/v1/indexer` returns 68 entries, all `enable: true`.
- Zilean search through Prowlarr's own search API returns real, correctly-tagged results (not
  just a 200 on save).

---

## [5.1.0] — Backup pipeline actually bootstrapped; log rotation, resource ceilings, fstrim, prune timer added

User asked for optimization suggestions, picked all six, asked for them applied. The most
consequential of the six: `stack-backup.timer` had been enabled since the same day (created
09:27, this work happened that afternoon) but had never once fired successfully — `restic`
wasn't installed on the host at all, so every run would have failed at the first command. See
the 2026-07-09 note above for how this intersects with README already describing a working
backup pipeline, daemon-level log rotation, and 6 resource-capped containers that didn't
actually match live state.

### Added
- **`restic` installed** (`pacman -S restic`, run by the user directly since `sudo` needs an
  interactive password this session couldn't supply) — `~/backups` (`chmod 700`) and
  `~/backups/.restic-password` (32 bytes from `openssl rand -base64 32`, `chmod 600`) created,
  repo initialized with `restic init`. Verified end-to-end with a real
  `./scripts/backup-config.sh` run, not just `restic init` succeeding: 742 files, 113.944 MiB
  snapshotted, retention policy applied, exit code 0. Three Plex files (`.LocalAdminToken`,
  `Preferences.xml`, `Setup Plex.html`) came back owned `sddm:sddm` mode `0600` from a container
  recreate during this same pass and are unreadable by the backing-up user — restic's own exit-3
  handling already treats this as non-fatal (warn, not fail); left alone rather than chased,
  since `.LocalAdminToken` arguably shouldn't be backed up anyway and the other two regenerate
  trivially.
- **`pg_dump` step added to `scripts/backup-config.sh`**, run before the `restic backup` call —
  `docker exec zilean-postgres pg_dump -U postgres zilean | gzip >
  ./config/zilean-postgres-dump/zilean.sql.gz`. Closes a real gap: `zilean-postgres`'s raw
  datadir is excluded from the restic backup (correctly — a live raw-file copy of a running
  Postgres datadir can be inconsistent), but nothing filled that gap before, so the
  ~5,600-entry Real-Debrid-ingested hash index had zero backup coverage. Tested live against
  the running container: produced a real 34MB gzipped dump with valid SQL content. Failure
  path posts a Discord warning but doesn't block the rest of the backup run.
- **Resource ceilings added to 6 previously-uncapped containers** — `rclone-alldebrid` (512MB/
  64MB/4 cpus), `tautulli` (512MB/64MB/2), `control-panel` (512MB/64MB/2), `glances` (512MB/
  64MB/2), `unpackerr` (512MB/64MB/2), `watchtower` (256MB/32MB/1). All sized as defensive
  insurance (cheap, generous headroom) rather than from observed pressure, same reasoning
  pattern as the original 6-container pass this supplements. All 21 containers recreated
  (`docker compose --profile extras up -d`) and confirmed `healthy` afterward.
- **Docker log rotation** — a `logging: &common-logging` anchor (`max-size: 10m`, `max-file: 3`)
  added directly in `docker-compose.yml` and applied to every service (via the existing
  `x-common` anchor where already used, explicit `logging: *common-logging` added to every
  standalone service block otherwise). Deliberately **not** `/etc/docker/daemon.json` this
  time, even though that's what README described — a compose-level anchor is tracked in git
  with everything else this stack manages, instead of living only on the host with no record of
  when or why it was set. README's Docker log rotation section needs updating to match (see
  README.md changes below).
- **`stack-docker-prune.timer`/`.service`** (new, same tracked-in-repo-then-symlinked pattern as
  every other `stack-*` unit) — weekly, Sundays 04:30 EDT (after the 03:30 backup and 04:00
  Watchtower pull so it doesn't race an image pull that's about to become "in use" again).
  `docker container prune -f`, `docker image prune -f`, `docker builder prune -f` — deliberately
  not `docker system prune --volumes`, since this stack uses bind mounts everywhere, not named
  volumes, so there's nothing to gain there and it's one flag away from removing something live.
  Wired to the same `notify-failure@%n.service` defense-in-depth as every other `stack-*` unit.
- **`fstrim.timer` enabled** (`systemctl enable --now fstrim.timer`, run by the user directly)
  — the whole stack, including a write-heavy Postgres instance, lives on one NVMe drive with no
  periodic TRIM previously scheduled at all.

### Removed
- Stray `hello-world` container (`awesome_perlman`, created earlier the same day, exited) —
  `docker rm`.

### Verified live
- `restic version`, `systemctl is-enabled/is-active fstrim.timer`, and
  `systemctl --user is-enabled/is-active stack-backup.timer` all confirmed after the user ran
  the two `sudo`-gated commands themselves.
- Task-tracking checklist double-checked against live state after the fact (session asked to
  "double check your checklist") — found `fstrim.timer` and the `restic` install still marked
  pending despite being verified live already; corrected to `completed` rather than left stale.

---

## [5.0.0] — Homepage and Heimdall removed; Control Panel gets Quick Links + a Matrix theme

User asked for a quick-link list to every service at the top of Control Panel's page
specifically so Homepage and Heimdall could be removed entirely, plus a Matrix visual theme
"to match the pc." Both requested and done in the same pass.

### Removed
- **`heimdall` and `homepage` services removed from `docker-compose.yml` entirely** (22 total
  services now, down from 24) — both were link-launcher/widget-dashboard installs that were
  never actually themed or populated with live data beyond their stock defaults (see
  [4.15.0](CHANGELOG.md) below and the Dashboard section in README.md), so once Quick Links
  covered what either was for, keeping them running was pure overhead. The live containers
  were stopped and removed with `docker compose --profile extras up -d --force-recreate
  control-panel --remove-orphans` rather than left dangling after the compose file change —
  confirmed via `docker ps -a` that neither `heimdall` nor `homepage` exists in any state
  anymore, not just that they're missing from `docker compose ps`.
- Every remaining `heimdall`/`homepage` reference in README.md, TODO.md, `.env.example`, and
  `control-panel/app.py`'s `CONTAINER_LABELS` dict cleaned up in the same pass — including a
  now-moot TODO.md item investigating Heimdall's empty `app.sqlite`, which stopped being
  worth investigating once the service itself was removed.

### Added
- **Quick Links panel** (`control-panel/static/app.js`'s `QUICK_LINKS`) — one link per service
  with a web UI (16 total: Plex, Prowlarr, Zilean, both Decypharr instances, Zurg, all 4 arr
  apps, NZBGet, Seerr, Bazarr, Byparr, Tautulli, Glances), each with a live up/down status dot
  reusing the same `/api/status` polling the container grid already does — no new backend
  endpoint needed.
- **Matrix theme** (`control-panel/static/style.css`) — full palette swap from black/red to
  black/phosphor-green (`--accent: #00ff41`), monospace headings, and button text color
  switched from white to a dark green (`--accent-text-on`) since white-on-bright-green has
  poor contrast where red-on-dark didn't. `--bad` (real errors/danger) deliberately kept red
  rather than reworked into the green palette, so it still reads as a genuine anomaly against
  an otherwise all-green console instead of blending in.
- **Falling-code rain layer** (`control-panel/static/matrix-rain.js`) — a self-contained canvas
  animation behind everything (`z-index: -1`), kept in its own file rather than folded into
  `app.js` on purpose: a bug in a decorative effect should never be able to take the actual
  ops dashboard down with it. Respects `prefers-reduced-motion` by skipping the render loop
  entirely (not just hiding the canvas via CSS), and pauses via the Page Visibility API when
  the tab isn't active, since this dashboard is meant to be left open in a tab.

### Verified live
- Rebuilt (`docker compose build control-panel`) and redeployed
  (`--force-recreate --remove-orphans`) against the actual running stack, not just built.
  Confirmed `heimdall`/`homepage` are gone from `docker ps -a` entirely (stopped and removed,
  not just orphaned), confirmed the container came back `healthy`, confirmed `/api/containers`
  now returns exactly 22 entries, and confirmed `index.html`/`style.css`/`matrix-rain.js` all
  serve the new content (200s, quicklinks/matrix-rain markup and the new CSS palette present
  in the response bodies).

*Built with Claude AI.*

## [4.15.0] — Control Panel becomes the single dashboard

User asked for Homepage to gain container-graphical status/control, Plex updates, Radarr/Sonarr
manual import, an optimize-database button, Zilean hash counts, live system specs, and a
sortable Zilean search with grab-to-DMM. Investigating turned up that Control Panel (not
Homepage) already had real backend code for most of this — manual import, optimize-database,
and Zilean search+grab were already implemented and working, while Homepage's own config files
were unconfigured stock templates with none of what README had claimed for it (see the
Dashboard/Homepage audit earlier this session). Consolidated everything into Control Panel
rather than building out a second, mostly-redundant dashboard.

### Added
- **Full container grid** (`GET /api/containers`) — every container in this compose project,
  discovered live via the same `com.docker.compose.project` label lookup the whole-stack
  restart already used (`project_containers()`, factored out and shared), not the old
  hardcoded `RESTARTABLE_CONTAINERS` allow-list (which only covered 16 of the stack's services
  and had already silently missed `decypharr-alldebrid`). Reports state, health, image, and
  live CPU/memory computed the same way `docker stats` does (`cpu_stats`/`precpu_stats` delta,
  `inactive_file` cache subtraction on memory). Added real **start**
  (`POST /api/container/{name}/start`) and **stop** (`POST /api/container/{name}/stop`)
  endpoints alongside the existing restart - stop is arm/confirm-guarded in the UI since it
  leaves something down until someone notices; the panel rejects stopping/restarting itself.
- **Host system stats** (`GET /api/system/stats`) — proxied from Glances' own REST API
  (`http://glances:61208/api/4/all`), since this container has no host `pid` namespace of its
  own. Degrades to `{"available": false}` rather than a 502 if Glances is unreachable.
- **Zilean hash count** (`GET /api/zilean/stats`) — queried directly from `zilean-postgres`
  (`SELECT COUNT(*) FROM "Torrents"`), since Zilean has no stats API of its own (every endpoint
  guessed at previously — `/health`, `/api/stats`, `/dmm/status` — 404s, see README's "Zilean
  hash sources"). Also attempts an IMDB-matched breakdown (`WHERE "ImdbId" IS NOT NULL`) with
  its own nested try/except so a wrong guess at that column name can't take out the base count.
- **Plex update check** (`GET /api/plex/updates`) — reads the running version from `/identity`
  and checks for a newer one via `/updater/status`; a check only, never an auto-apply action
  (Plex stays deliberately pinned, see README's Image pinning policy).
- `ZILEAN_POSTGRES_PASSWORD` added to `control-panel`'s environment in `docker-compose.yml` and
  `psycopg2-binary==2.9.10` to `requirements.txt` for the above.

### Changed
- `GET /api/status` and `POST /api/container/{name}/restart` now validate against the same
  live container discovery instead of the old hardcoded list.

### Verified live
- Rebuilt and redeployed against the real running stack (not a sandbox). `/api/containers`
  correctly reported all containers with real CPU/mem figures; `/api/system/stats` returned
  real host numbers (22.7GB RAM, 928GB disk, live uptime); `/api/zilean/stats` returned
  149,474 total hashes / 128,321 IMDB-matched — confirming the guessed `"ImdbId"` column name
  was actually correct against the live schema; `/api/plex/updates` correctly read the running
  Plex version with no update available. Safety guards confirmed: stopping/restarting the panel
  itself → 400, an unknown container name → 404, starting an already-running container → clean
  no-op. Fired a real restart of `unpackerr` through the new endpoint and confirmed it actually
  cycled via a fresh `StartedAt` timestamp.

*Built with Claude AI.*

## [4.14.0] — Decypharr: restrict Radarr to Real-Debrid only

User asked to remove Radarr's ability to use AllDebrid — leaving Real-Debrid as its only
debrid backend, while Sonarr/Lidarr/Readarr keep access to both.

### Added
- **`selected_debrid: "realdebrid"`** added to Radarr's entry in `config/decypharr/config.json`'s
  `arrs` array. Confirmed via [Decypharr's configuration reference](https://docs.decypharr.com/guides/configuration/)
  that this field (distinct from the existing `source: "auto"` field already on every arr entry)
  is exactly what pins a specific arr app to one debrid provider from the `debrids` list —
  Sonarr, Lidarr, and Readarr are left on `source: "auto"` with no `selected_debrid`, so they
  can still fall through to AllDebrid same as before.
- `docker compose restart decypharr` to load the change; startup log confirmed a clean reload
  (`Loading config from /app/config.json` → normal manager/DFS startup, no config-parse error or
  rejected field).

### Not committed
- `config/decypharr/config.json` is entirely gitignored (`config/` — plaintext debrid API keys),
  so this is a live runtime change only, not something that shows up in `git log`. Consistent
  with existing policy (see [Security note](README.md#security-note)).

---

## [4.13.0] — Plex library cleanup: orphaned Movies/TV folders removed

User asked to delete Plex's movie library contents as "leftover and not existent." Investigating
turned up a more specific problem than the request assumed, plus something unrelated and
unresolved.

### Found
- `./media/movies` (Radarr's own root folder) held 496 folders / 499 symlinks into
  `/mnt/decypharr/__all__/...`, **462 of them dangling** — but Radarr itself tracked **zero**
  movies (`/api/v3/rootfolder` showed all 496 as `unmappedFolders`). Pure orphaned output, not
  referenced by anything.
- Plex's actual **Movies** library doesn't read `./media/movies` at all — its one configured
  location is `/mnt/zurg/movies` (confirmed in `docker-compose.yml`'s own comments on the Plex
  service's `/mnt` bind mount). All 234 folders there were **completely empty** (0 files in any
  of them) — Real-Debrid cache eviction, not a local problem.
- Same pattern on the TV side: `./media/shows` (Sonarr's root folder) had 2,406 symlinks,
  2,368 broken, Sonarr tracking zero series. Plex's **TV Shows** library reads from *two*
  locations — `/mnt/zurg/shows` (2 folders, both empty, same dead pattern as Movies) and
  `/mnt/all/magnets` (25 entries, **all live** — the active AllDebrid magnet cache, mixed
  movie/TV content, currently working).

### Changed
- Deleted every folder under `./media/movies` (496) and `./media/shows` (135) — confirmed zero
  real (non-symlink) files in the movies folder first. **The shows folder had 130 real,
  non-symlink files that were deleted without inspecting them first** — a process mistake (the
  verification `find` and the `rm -rf` were chained in one command instead of checked as two
  separate steps). Best guess, unconfirmed: Bazarr-downloaded `.srt` subtitles, given the
  roughly one-per-folder count and that Bazarr sits in this same pipeline — but this wasn't
  verified before deletion and isn't recoverable (no btrfs snapshot exists for the `/home`
  subvolume; `snapper list-configs` shows only `root`; disk is SSD with `discard=async`).
- Triggered a Plex library scan on both **Movies** and **TV Shows** sections. This server has
  "empty trash after every scan" on, so dead entries cleared automatically with no separate
  `emptyTrash` call needed. Movies went to 0 items (nothing behind any of the 234 zurg-mount
  folders was real). TV Shows went to 3 items, all sourced from the live `/mnt/all/magnets`
  location.
- **`/mnt/zurg/movies`, `/mnt/zurg/shows`, and `/mnt/all/magnets` themselves were left
  untouched** — deliberate. These are live `rclone`/zurg-backed mounts tied to the actual
  Real-Debrid/AllDebrid accounts, not plain local files; deleting through them is a different
  risk category than deleting local symlinks, and wasn't part of what was asked.

### Found, not resolved
- While checking Radarr's tracked-movie count, its log (`config/radarr/logs/radarr.txt`) showed
  **1,605 movies deleted in a single 0.1-second burst** (`21:47:49`, all via
  `MovieService|Deleted movie`) with **no corresponding API call logged** — every other action
  in this session against Radarr's REST API shows up as a `Debug|Api` log line; this one has
  none. Sonarr shows the mirror image: roughly 90 real series (Deadwood, Longmire, Wynonna Earp,
  etc.) briefly got added around `21:43` with no `Import List Sync` running at the time (it ran
  later and found nothing), then vanished with **no deletion log line of any kind**. Both apps'
  queue, history, and blocklist tables are all empty now despite logs showing completely normal
  grab/import activity right up to the moment it happened. Not triggered by this session — only
  read-only `GET` requests had been made against either app before this was noticed. Root cause
  unidentified; see [TODO.md](TODO.md).

---

## [4.12.0] — Custom format: block Cyrillic-titled and sample releases

User asked to never receive anything in Cyrillic or sample releases. Extended the existing
single-custom-format blocklist (see [Custom format: blocked releases](README.md#custom-format-blocked-releases))
rather than adding new formats, to stay consistent with how that blocklist is already organized —
one format per app, every rejection condition folded in as an OR'd Release Title spec.

### Added
- **`Cyrillic`** — `[Ѐ-ӿ]`, matches any release title containing a Cyrillic character.
- **`Sample`** — `(?i)\bsample\b`, matches release titles with "sample" as a whole word
  (release-title level — a bundled sample *file* inside an otherwise-clean release is caught
  separately, by each app's own built-in per-file sample detection during import).
- Both added to **"Blocked Releases (All Qualities)"** on Radarr (id 42) and Sonarr (id 41) via
  `PUT /api/v3/customformat/{id}`, `required: false` / `negate: false` like the two existing
  specs — any one of the now-four conditions matching rejects the release. Already wired at
  `-10000` in every quality profile on both apps (`minFormatScore: 0`), so no quality-profile
  changes were needed — extending the existing format was enough.

### Verified
- Saved regex values read back correctly from both apps' APIs. Radarr's `/api/v3/customformat/test`
  endpoint returned `405` on this version (not available), so exact `.NET`-engine matching
  wasn't confirmed live — instead checked the same patterns with Python's `re` module against
  four real-shaped titles (a Cyrillic-titled release, a `SAMPLE`-tagged release, a clean
  release, and a `Sample`-tagged TV episode): all four matched exactly as expected. Simple
  literal-range and `\b`-boundary patterns like these don't touch any regex feature that differs
  between engines, so this is a reasonable stand-in for the missing live test, not a full
  substitute for one.

---

## [4.11.0] — Control Panel: Unstick and Manual Import for Radarr/Sonarr

Follow-on to [4.7.0](CHANGELOG.md)'s Control Panel v2. User asked for a button to clear stuck
Radarr/Sonarr queue items and manually import files — a real gap given the
[Radarr-specific mount fragility](README.md#architecture) already documented, where a stale
Zurg mount leaves completed downloads stuck at `importBlocked` until someone intervenes by hand.

### Added
- **`Unstick`** — one armed button per app (Radarr/Sonarr only; Lidarr/Readarr excluded,
  untested against their queue shape) that sweeps every queue item the app itself flagged
  `trackedDownloadStatus: warning|error` — the same condition that lights up the warning icon in
  each app's own Queue tab — and removes it, blocklists the release, and triggers an immediate
  re-search in one `DELETE /api/v3/queue/{id}?removeFromClient=true&blocklist=true&skipRedownload=false`
  call per item.
- **`Manual import`** — a collapsible panel per app listing every importable file Radarr/Sonarr's
  own `GET .../manualimport` endpoint finds across all currently-stuck queue items (title match,
  episode, quality, release group, size, any rejection reasons like `Sample`), each with its own
  armed **Import** button. The candidate object returned by the scan is echoed back verbatim on
  import (`POST /api/v3/command` with `name: "ManualImport"`) — same pattern each app's own
  Manual Import screen uses, so quality/language/match data can't drift between the scan and the
  actual import call.
- New backend endpoints in `control-panel/app.py`: `POST /api/arr/{app}/unstick`,
  `GET`/`POST /api/arr/{app}/manual-import`, gated to `radarr`/`sonarr` only via a
  `QUEUE_ARR_APPS` allow-list, same pattern as `RESTARTABLE_CONTAINERS`.

### Verified
- Both new `GET` endpoints (queue scan, manual-import candidate list) run live against the real
  stack: 34 stuck Radarr items and 1 stuck Sonarr item found and correctly resolved to real
  movie/series/episode metadata, matching what each app's own `manualimport` API returns.
  `POST` to a non-queue app (`lidarr`) correctly 404s.
- **The actual mutating actions (`unstick`, `manual-import` execute) were deliberately never
  fired during development** — they blocklist real releases and move real files, so verification
  stopped at the read-only paths. First real click is on you.

---

## [4.10.0] — README: introduction, "why use this," and real screenshots

User asked for the README to actually sell the project, not just document it: an
introduction, a reason someone would want to run this, code examples, and graphics — on top
of what [4.9.0](CHANGELOG.md)'s setup wizard already made possible.

### Added
- **`## Introduction` and `## Why use this`**, placed right after the existing opening
  paragraph/disclaimer, before the table of contents — what the stack actually does (23
  services, one compose file, debrid-first so cached content plays instantly instead of
  downloading), and why you'd want it over stitching guides together yourself, with an
  explicit "what this isn't" callout (not a beginner Docker tutorial, LAN-only/no-auth by
  design).
- **`## Quick start`**, a single fenced code block covering the whole bring-up sequence
  (scaffold → `--setup` wizard → `docker compose up -d` → optional extras profile) plus a
  Mermaid flowchart of the same sequence, laid out as two explicit phases (`Pass 1 - before
  first boot` / `Pass 2 - after first boot`) to make the *arr-key two-pass constraint from
  [4.9.0](CHANGELOG.md) visually obvious rather than something you only find by reading. First
  Mermaid diagram in this README — validated by actually rendering it (`@mermaid-js/mermaid-cli`
  via `npx`, pointed at the locally-installed `brave` browser as its headless renderer) before
  committing it, not just trusted to be syntactically correct.
- **Setup wizard section fleshed out**: why hand-editing 12 keys across 6 sections is
  error-prone in the first place, what re-running the wizard actually does under the hood
  (loads the real `.env` as defaults, blank fields keep their existing value), and the 4-step
  two-pass flow spelled out as a numbered list rather than prose.
- **A real screenshot** (`docs/images/setup-wizard-form.png`) of the actual running wizard
  form — not a mockup. Captured by scaffolding a scratch install, running `--setup` for real,
  and driving `brave --headless --screenshot` against `localhost:8090` (Claude Code's own
  Chrome extension wasn't connected this session, so this was the fallback rather than the
  first choice). The scratch `.env` behind it has no real secrets in it — Zilean fields show
  the wizard's own auto-generated tokens, everything else is still `changeme`, so the masked
  password fields in the image are placeholders, not anything sensitive. Cropped to content
  (pixel-scanned for the actual bottom of the rendered page rather than guessed) so it doesn't
  carry a few hundred pixels of dead space.
- Version banner at the top of the README (was still reading "4.7.0") corrected to match
  `CHANGELOG.md`'s actual current version — stale since before [4.8.0](CHANGELOG.md).

### Fixed
- The Setup wizard section briefly had two versions of the same "two-pass constraint /
  `config/homepage/services.yaml` isn't touched" explanation back to back — the new prose was
  written as an addition without removing the equivalent paragraph [4.9.0](CHANGELOG.md)
  already committed. Caught on a full diff review before commit, not left in.

---

## [4.9.0] — Setup wizard: onboarding closer to turnkey

Natural next step after [4.8.0](CHANGELOG.md)'s full Plex dockerization: with no native
fallback left anywhere, the installer image (see [Installer image](README.md#installer-image))
is genuinely this stack's only bring-up path now, and its last manual step was hand-editing
`.env` — 12 keys across 6 sections, several of them opaque secrets a new user has to know how
to obtain or generate. User asked for an onboarding app instead: enter the API keys/logins,
get a working `.env` back.

Scope was deliberately kept narrow: this fills in `.env` only. It does not touch any running
container and does not auto-wire the connections between apps (Prowlarr indexers, Radarr/
Sonarr root folders, Seerr, etc.) — those stay exactly as manual as they've always been. Also
deliberately **not** part of `docker-compose.yml` and **not** folded into the existing Control
Panel — Control Panel's own `app.py` hard-requires real `.env` values just to start
(`os.environ["PLEX_TOKEN"]` etc. at import time), so it can't be the tool that produces them.

### Added
- **`scripts/setup_wizard.py`** — stdlib-only Python (no pip dependency; `http.server` for a
  single GET/POST HTML form), matching how lean the installer image already is and the
  precedent set by `scripts/plex-library-report.py` (also stdlib-only). Parses `.env.example`
  into the same sections/help-text the file already has via its `# ---- X ----` headers and
  comment lines, so the form's structure and wording stay in sync with `.env.example`
  automatically rather than needing separate hand-maintained copy.
- **`--setup` mode** added to the installer image's `entrypoint.sh` — same image, same GHCR
  tag, `docker run --rm -p 8090:8090 -v "$(pwd)":/out ghcr.io/whispersofj/media-stack:latest
  --setup` serves the wizard on port 8090 instead of scaffolding files. Single-shot: the
  process exits itself after a successful write, no lingering container.
- **Auto-generates the two Zilean secrets** (`ZILEAN_POSTGRES_PASSWORD`, `ZILEAN_API_KEY`) via
  `secrets.token_hex(16)` instead of asking the user to run that command themselves and paste
  the result in — they're self-issued with no external source anyway, so one fewer manual step
  for a value nobody needed to see beforehand.
- **Re-run support, doubling as an edit flow.** If a real `.env` already exists in the target
  directory, the wizard loads *its* values as the form's defaults instead of `.env.example`'s
  placeholders — re-running after changing your mind about a value, or after first boot (see
  below), only means retyping what actually changed.
- **A blank submitted field falls back to the existing value**, not an empty string — protects
  a re-run from silently clobbering an already-real value back to blank if a field is left
  untouched in the browser.

### A hard constraint this couldn't design around
`RADARR_API_KEY`/`SONARR_API_KEY`/`LIDARR_API_KEY`/`READARR_API_KEY` cannot be genuinely
collected before first boot — confirmed against `docker-compose.yml`: each arr app mounts an
empty `./config/<app>:/config` on a fresh install and generates its own random API key into
its own config the first time the process starts. There's no external source for these ahead
of time, and pre-seeding a plausible `config.xml` before the app ever runs was considered and
rejected — fragile across image/schema versions and touches container state, out of this
feature's scope (`.env` only). So this is necessarily **two-pass**: the wizard marks these 4
fields as "fill in after first boot," defaults them to `changeme`, and the same re-run support
above is what makes pass two painless — bring the stack up, grab each key from that app's
Settings, re-run `--setup`, paste them in, submit.

### Not touched
- **`config/homepage/services.yaml`** has its own separate copy of the same 4 arr keys (per
  the existing comment in `.env.example`: "mirrors config/homepage/services.yaml") and is
  **not** sourced from `.env` at all. The wizard doesn't write to it — keeping Homepage's
  widgets in sync with a rotated key is still exactly as manual as it was before this existed.
  Documented explicitly in the README rather than left as a silent gap.
- **Inter-service wiring** (Prowlarr → arr apps sync, root folders, download clients, Seerr
  connections, Bazarr languages) — a deliberate scope decision, not an oversight. This closes
  the "enter your secrets" gap, not the "configure every app for me" one.
- **`docker compose up -d` itself** — the wizard's job ends at a written `.env`; bringing the
  stack up (or back up after a `--force-recreate control-panel`) stays a command the user runs.

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
  corrected from a stale `2.13.0` to match the CHANGELOG's actual current version at the same
  time (pre-existing drift, unrelated to this change, fixed while already editing the file).
- `PLEX_MIGRATION_PLAN.md` removed now that it's shipped, per this repo's usual
  TODO-to-CHANGELOG convention.

*Built with Claude AI.*

---

## [3.2.4] — Plex containerization plan documented (planning only)

Backfilled retroactively — commit `d02428b` shipped this without its own version at the time.
Given a real version number as part of the 2026-07-09 versioning-policy pass (see note at top
of this file).

### Added
- **`PLEX_MIGRATION_PLAN.md`** — the agreed plan for bringing Plex into `docker-compose.yml`:
  official `plexinc/pms-docker` image, `PLEX_UID`/`PLEX_GID=955` to match the existing native
  owner, `network_mode: host`, GPU passthrough, and the path-parity requirement that keeps the
  existing 33GB library database intact. Paused before execution at the user's request.
  Shipped as [3.3.0](CHANGELOG.md); the plan doc itself was removed once it shipped, per this
  repo's usual TODO-to-CHANGELOG convention.

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

Decided to drop the Caddy front-end added in v2.11.0 — every web UI publishes its host port
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

## [2.13.2] — Claude Code Review workflow fixed for Dependabot PRs

Backfilled retroactively — commit `4d667bf` shipped this without its own version at the time.
Given a real version number as part of the 2026-07-09 versioning-policy pass (see note at top
of this file).

### Fixed
- `claude-code-review.yml` ([2.7.0](CHANGELOG.md)) triggers on every PR with no actor filter,
  so Dependabot's own version-bump PRs hit it too — and the underlying
  `anthropics/claude-code-action` refuses to run for non-human actors by default ("Workflow
  initiated by non-human actor: dependabot (type: Bot). Add bot to allowed_bots list or use '*'
  to allow all bots."). Scoped the allowlist to `dependabot[bot]` specifically rather than `*`,
  since that's the only bot that actually needs to trigger this.

---

## [2.13.1] — Installer image's Alpine base bumped 3.20 → 3.24

Backfilled retroactively — commits `f4c3f9c`/`40f4872` (a routine Dependabot PR) shipped this
without a version at the time. Given a real version number as part of the 2026-07-09
versioning-policy pass (see note at top of this file).

### Changed
- `Dockerfile`'s Alpine base image bumped from `3.20` to `3.24` — the installer image's own
  base only; no functional change to the stack itself.

---

## [2.13.0] — Plex library added/removed report, every 12 hours

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

## [2.12.0] — Installer image published to GHCR

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

## [2.11.3] — Removed leftover Jellyfin artifacts

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

## [2.11.2] — Discord alerting activated

Backfilled retroactively — commit `84efed2` shipped this directly without a version bump or a
CHANGELOG entry, so `TODO.md` kept listing it as not-started for a full day even though it was
live. Originally logged out-of-sequence as "[Unversioned, 2026-07-07]"; given a real version
number as part of the 2026-07-09 versioning-policy pass (see note at top of this file).

### Changed
- **Watchtower's Shoutrrr Discord notifications turned on for real** — the three
  `WATCHTOWER_NOTIFICATION*` lines added commented-out in [2.11.0](CHANGELOG.md) were
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
  already built in [2.11.0](CHANGELOG.md), previously just no-op-silent without a real webhook)
  have been live since 2026-07-07 too - confirmed via `journalctl` that both
  `stack-backup.service` and `stack-health-check.service` have been running cleanly on their
  normal schedule since.

---

## [2.11.1] — 2.11.0 correction: digest-pinned images aren't auto-updated by Watchtower

Backfilled retroactively — commit `297dc13` shipped this without its own version at the time.
Given a real version number as part of the 2026-07-09 versioning-policy pass (see note at top
of this file). Caught while re-verifying [2.11.0](CHANGELOG.md): a digest pin is immutable by
definition, so Watchtower re-pulling that exact reference never sees anything new. The README/
CHANGELOG had claimed Watchtower "still updates every" pinned image — true for the 14 channel/
version-tag pins, false for the 7 digest pins (Whisparr, Seerr, Homepage, Glances, Kometa,
Unpackerr, Heimdall).

### Fixed
- Corrected both docs to say the 7 digest-pinned images need a manual bump instead.

---

## [2.11.0] — Reverse-proxy auth, image pinning, healthchecks, log rotation, Discord alerting

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

## [2.10.1] — Glances service-card widget crashed the whole Homepage page

### Fixed
- The Glances card added in v2.10.0 used the wrong config schema: `cpu: true`/`mem: true` are
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

## [2.10.0] — Real Kometa progress signal, Glances host stats, dashboard visual polish

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

## [2.9.0] — Kometa added and configured (Plex collections/metadata/overlays)

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

## [2.8.1] — Bazarr couldn't see Sonarr/Radarr's actual libraries

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

## [2.8.0] — Live dashboard (Homepage) + automated config backups

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

---

## [2.7.0] — Claude Code GitHub Actions workflows added

Backfilled retroactively — commits `53d3f23`, `240b90f`, and their merge (`8c74a94`, PR #3)
shipped this without a version at the time. Given a real version number as part of the
2026-07-09 versioning-policy pass (see note at top of this file).

### Added
- **`.github/workflows/claude.yml`** — the Claude PR Assistant workflow; tags `@claude` in an
  issue or PR comment to trigger an agentic response.
- **`.github/workflows/claude-code-review.yml`** — an automatic Claude code review on every PR.

---

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

## [2.5.2] — Bazarr's Plex connection fixed (last piece of the v2.4.0 bug)

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

## [2.5.1] — Decypharr's config-wipe bug filed upstream

Backfilled retroactively — commit `a7158f7` shipped this without its own version at the time.
Given a real version number as part of the 2026-07-09 versioning-policy pass (see note at top
of this file).

### Changed
- Linked [sirrobot01/decypharr#343](https://github.com/sirrobot01/decypharr/issues/343) into
  [2.5.0](CHANGELOG.md)'s writeup of the partial-`PATCH`-drops-config bug, for anyone checking
  the issue's status later.

---

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

## [2.3.1] — TODO.md added, tracking planned Jellyfin work

Backfilled retroactively — commit `cc156b6` shipped this without its own version at the time.
Given a real version number as part of the 2026-07-09 versioning-policy pass (see note at top
of this file).

### Added
- **`TODO.md`** — a running list of planned-but-not-started work, seeded with the Jellyfin +
  companion-app build that shipped as [2.4.0](CHANGELOG.md).

---

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
