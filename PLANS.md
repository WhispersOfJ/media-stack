# PLANS.md

Agent-oriented implementation spec for the current pending work: adding 7 new
services to the stack, fully wired in, plus a deferred phase-2 naming cleanup.

Source of truth for the human-readable version of this same plan (same content,
presentation-only): the published Artifact at
`https://claude.ai/code/artifact/6b115a3f-1972-44ff-968a-1d49a70fb281`. This file
is the canonical one an implementing agent should follow — if the two ever drift,
this file wins.

**Status: see each phase's own `Status:` line — that's the single source of
truth, not this paragraph.** As of last update (2026-08-11): Phases 1 (ntfy)
and 2 (Speedtest Tracker) DONE, Phases 3-7 not started. Phase 1 was built out
of this doc's stated risk order at Bear's explicit request (see its own
Phase 1 section for why that's a deliberate deviation, not an oversight).
See STACK.md's "ntfy added" and "Speedtest Tracker added" entries for the
full implementation records, including real bugs/assumption-mismatches
found and fixed during live verification of each.
Each phase below gets its own commit(s); update the `Status` line at the top
of a phase's section to `IN PROGRESS` / `DONE` as work lands, and update
`MEMORY.md` per the memory-reference note at the bottom.

---

## 0. How to use this doc

This is written so a fresh agent session, with no prior context, can pick up any
one phase and implement it correctly. Each service phase is self-contained:
it names exact files to create/edit, exact env vars, exact fish function names,
exact control-panel routes, and an acceptance checklist. Do not start a phase
until the previous one's acceptance checklist is fully green — phases are
ordered by risk, and skipping ahead defeats that.

**Global rules that apply to every phase (do not repeat per-phase unless a
phase deviates):**

- One commit per service. Commit message format: `feat: add <service> (<one-line
  what it does>)`. No `--no-verify`. Follow the repo's existing pre-commit hooks.
- Every phase ships with tests in the same commit: a pytest suite for the new
  control-panel router, and a live integration check run against the actual
  running container (documented per-phase as "Live verification").
- After a phase's commit, restart/redeploy per the `docker-compose-manager`
  skill and re-run `health-monitor` before starting the next phase.
- Secrets: prefer services that self-generate their own API key into their own
  `/config` volume, read off disk by the control-panel router (the existing
  `_tautulli_key()` pattern in `control-panel/services/tautulli/router.py` and
  the legacy copy in `control-panel/app.py:5193` — copy that pattern exactly,
  do not invent a new one). Only touch `secret-injector`
  (`.claude/skills/secret-injector`) if a service needs a key pushed *into* it
  rather than read back out.
- Naming: new fish functions and control-panel routes follow the *existing*
  `stack-<service>-<action>` / `/api/<service>/*` convention exactly as it
  stands today. Do **not** attempt to apply the phase-8 naming cleanup while
  building phases 1–7 — that would mix an unreviewed schema into services that
  haven't shipped yet. Match today's convention, nothing fancier.
- Every new docker-compose service block goes in a new `# new-services
  (2026-08)` section at the bottom of `docker-compose.yml`, mirroring the
  existing `# awesome-arr additions (2026-07-30)` section's structure (see
  `docker-compose.yml:780-784` for the comment-block style to match).
- Host ports for this batch are pre-allocated in the table below so there is
  no conflict-checking ambiguity mid-implementation.
- Before hardcoding any `<APP>_CONFIG__*`-style env var (or equivalent
  headless/env-driven config key) into a new service's compose block based on
  that project's own GitHub docs, verify the feature's "since vX.Y.Z" against
  the actually-deployed image tag, not just the docs on `main` — see the
  `verify-image-version-before-headless-config` skill. A mutable tag like
  `:latest` tracks the newest *stable* release only; docs on `main` can
  describe features not yet in any published image. Real incident this rule
  is from: hardcoding a documented nzbdav/InfiniDysk env var crashed that
  service's backend outright on recreate, and Docker's own healthcheck stayed
  green throughout because it was answered by a frontend/proxy layer
  independent of the crashed backend — don't trust `docker ps` health alone
  after a config-driven recreate; grep `docker logs <service>` for
  fatal/unknown-config errors too.
- For any live-verification step expected to take more than ~30s (a scan, a
  collector run, a library reconcile), use a background poll (Monitor-style:
  spawn it, poll on a longer interval, report progress rather than blocking)
  instead of a blocking wait. Frequent tight-interval polling against a
  service's own database while it's mid-write can itself add contention and
  slow the operation down — space polls out (tens of seconds, not sub-10s).

**Host port allocation (checked against every port currently in
`docker-compose.yml` as of 2026-08-08 — none of 8700–8706 are in use):**

| Service | Container port | Host port |
|---|---|---|
| ntfy | 80 | 8700 |
| Speedtest Tracker | 80 | 8701 |
| Organizr | 80 | 8702 |
| Scrutiny | 8080 | 8703 |
| GAPS-2 | 4277 | 8704 |
| WatchState | 8080 | 8705 |
| PlexAniSync | — (no web UI, scheduled job) | — |

---

## Phase 1 — ntfy

**Status:** DONE (2026-08-09)
**Risk:** low
**Role:** shared push-notification sink for the whole stack.

Built out of the plan's stated risk order at Bear's explicit request (asked for
"just step 1" when offered the choice between that and doing Phases 1-5 in
order). Implemented, live-verified, and committed - see STACK.md's "ntfy
added" entry for the full record. Two deviations from this section as
originally written, both discovered during live verification against the
real running Radarr/Sonarr/Prowlarr, not assumed from docs:
- 1.4's "Connect settings API call" needed every optional field present in
  the payload (empty string/list), not omitted - Radarr 400s with a
  misleading error otherwise.
- The plan didn't call out that Prowlarr's API is `/api/v1/`, not `/api/v3/`
  like Radarr/Sonarr - the setup-connections route reads each app's real
  version from `ARR_APPS`/`PROWLARR_CFG` rather than assuming v3 everywhere.

### 1.1 Compose

Add to `docker-compose.yml` in the new-services section:

```yaml
  ntfy:
    restart: unless-stopped
    image: binwiederhier/ntfy
    container_name: ntfy
    command: serve
    networks: [stacknet]
    healthcheck:
      test: ["CMD-SHELL", "wget -q --tries=1 http://localhost:80/v1/health -O - | grep -q true || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    volumes:
      - ./config/ntfy/cache:/var/cache/ntfy
      - ./config/ntfy/etc:/etc/ntfy
    ports:
      - "8700:80"
    mem_limit: 256m
    mem_reservation: 32m
    cpus: 1
```

Create `./config/ntfy/etc/server.yml` (mounted, not baked into the image) with
cache retention tuned down from the unbounded default:

```yaml
base-url: "http://<host>:8700"
cache-file: "/var/cache/ntfy/cache.db"
cache-duration: "72h"
behind-proxy: false
```

No auth-file needed initially — anonymous read/write is acceptable since the
stack is not exposed publicly. Note this explicitly in the STACK.md entry
(1.6) so it isn't mistaken for an oversight later.

### 1.2 Secrets

None. ntfy needs no API key for basic publish/subscribe use.

### 1.3 Health monitor

Add to `HTTP_SERVICES` in `.claude/skills/health-monitor/monitor.py`:

```python
"ntfy": (8700, "/v1/health"),
```

### 1.4 Radarr/Sonarr/Prowlarr wiring

For each of `radarr`, `radarr-anime`, `sonarr`, `sonarr-anime`, `prowlarr`:
Settings → Connect → add ntfy connection, pointing at
`http://ntfy:80/<app-name>-alerts` (e.g. topic `radarr-alerts`,
`sonarr-anime-alerts`). Trigger on at minimum: health issue, application
update, manual interaction required. This is done via each app's REST API
(`POST /api/v3/notification`) inside the control-panel router below, not by
hand in each UI — write a one-time setup script or router action, not a
manual click-through, since this repeats 5 times identically.

### 1.5 Fish functions

New file `fish-functions/stack-ntfy-*.fish`:

- `stack-ntfy-publish <topic> <message>` — thin wrapper calling
  `__stack_api POST /api/ntfy/publish` with `{topic, message}` body. Mirrors
  the existing `__stack_api` pattern used by every other `stack-<service>-*`
  function — see `fish-functions/stack-tautulli-stats.fish:3` for the exact
  shape to copy.
- `stack-ntfy-topics` — lists configured topics (reads server.yml via the
  router), calls `__stack_api GET /api/ntfy/topics`.
- `stack-notify-test` already exists (see the existing function list) —
  **update it**, don't duplicate it, to route through ntfy once ntfy exists.
  Check its current implementation before touching it; if it already posts to
  a different notification channel, add ntfy as an additional sink rather than
  replacing existing behavior, and confirm with a quick check of what it
  currently does before assuming.

### 1.6 Control panel

- New `control-panel/services/ntfy/router.py`: `SERVICE_META`, `APIRouter`,
  routes `POST /api/ntfy/publish`, `GET /api/ntfy/topics`, `GET
  /api/ntfy/health`. Mirror `control-panel/services/tautulli/router.py`'s
  structure exactly (imports, error handling, response shape).
- Register in the fleet: `control-panel/app.py` — add to the fleet
  label/description dict (same place as the existing entries near line 161),
  add to `NEW_APP_CONTAINERS` (~line 5818) and the port map (~line 5827).
- Frontend: `control-panel/static/js/fleet.js` — add ntfy to the
  notifications/utility category grouping. `control-panel/static/js/reference.js`
  — add `{id: "ntfy", label: "ntfy", port: 8700}` tile. `control-panel/static/commands.json`
  — add entries for the two new CLI commands mirroring the router routes.
- `STACK.md` — new entry: what ntfy is, why it was added (central alert sink
  instead of N per-app configs), the anonymous-access note from 1.1, host port.

### 1.7 Tests

- `tests/control_panel/services/test_ntfy_router.py` — pytest, mock the ntfy
  HTTP client, assert publish/topics/health routes behave (200 on success,
  meaningful error on ntfy unreachable). Match the test file structure of
  the existing tautulli router tests (find via `find tests -iname
  '*tautulli*'` and mirror it).
- **Live verification** (run once against the real deployed container, record
  result in the phase status note, not a permanent test): `curl -d "hello" \
  http://localhost:8700/media-stack-test`, confirm delivery via the ntfy web
  UI or app, then delete the test topic's cached messages.
- Confirm `health-monitor` reports ntfy green.
- Confirm at least one Arr app (e.g. Radarr) successfully delivers a real
  ntfy notification end-to-end (trigger a test notification from Radarr's
  Connect settings).

### 1.8 Acceptance

- [ ] Container healthy via `docker compose ps`
- [ ] health-monitor probe green
- [ ] pytest suite passing
- [ ] Live publish/subscribe verified
- [ ] All 5 Arr-family apps have a working ntfy connection
- [ ] Fish functions callable, `stack-notify-test` updated
- [ ] STACK.md entry added
- [ ] Committed as its own commit

---

## Phase 2 — Speedtest Tracker

**Status:** DONE (2026-08-11)
**Risk:** low
**Role:** scheduled ISP speed monitoring + history, so link degradation is
visible before it's the reason downloads/streaming feel slow.

Implemented, live-verified, and committed - see STACK.md's "Speedtest Tracker
added" entry for the full record, including two real bugs found and fixed
during live verification (not just discovered during planning): the Ookla
CLI's IPv6 socket failure that made every run fail 100% of the time until a
`sysctls` fix landed, and a naive-vs-aware datetime 500 in `/history` caused
by the live API's real timestamp format differing from its own docs. Also
two deviations from this section as originally written, both discovered
during implementation, not assumed from docs:
- 2.2's default-login note is moot - the image's `ADMIN_NAME`/`ADMIN_EMAIL`/
  `ADMIN_PASSWORD` env vars seed a real admin on first boot, so there was
  never a default `admin@example.com`/`password` login to change.
- 2.5's "sqlite query" assumption for reading the API token back out was
  wrong - Sanctum only stores a hash, and the image has no `tinker`. The
  token was minted by replicating Sanctum's own token-generation algorithm
  and inserting the row directly via Python's `sqlite3` against the
  bind-mounted DB file. Full detail in STACK.md.

### 2.1 Compose

```yaml
  speedtest-tracker:
    restart: unless-stopped
    image: lscr.io/linuxserver/speedtest-tracker:latest
    container_name: speedtest-tracker
    environment:
      PUID: "${PUID}"
      PGID: "${PGID}"
      TZ: "${TZ}"
      APP_KEY: "${SPEEDTEST_TRACKER_APP_KEY}"
      APP_URL: "http://localhost:8701"
      DB_CONNECTION: sqlite
      SPEEDTEST_SCHEDULE: "0 * * * *"
    networks: [stacknet]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:80/api/healthcheck || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    volumes:
      - ./config/speedtest-tracker:/config
    ports:
      - "8701:80"
    mem_limit: 512m
    mem_reservation: 64m
    cpus: 1
```

`SPEEDTEST_SCHEDULE: "0 * * * *"` is hourly — deliberately not upstream's
15-minute default, since a full speedtest saturates the link and running it
4x/hour is unnecessary noise for a monitoring signal, not a benchmark tool.

### 2.2 Secrets

`APP_KEY` must be generated once (Laravel app key, 32-byte base64) and stored
in `.env` as `SPEEDTEST_TRACKER_APP_KEY`. Generate with:
`docker run --rm lscr.io/linuxserver/speedtest-tracker:latest php artisan
key:generate --show` (or equivalent one-liner — verify the exact command
against the image's entrypoint at implementation time, since LinuxServer
images sometimes wrap this differently). Add `SPEEDTEST_TRACKER_APP_KEY` to
`.env.example` as a placeholder with a comment explaining how to generate it.

Default web login (`admin@example.com` / `password`) must be changed on
first login — note this as a manual one-time step in the STACK.md entry, it
cannot be automated via the API before the app has booted once.

### 2.3 Health monitor

```python
"speedtest-tracker": (8701, "/api/healthcheck"),
```

### 2.4 Fish functions

- `stack-speedtest-latest` — `GET /api/speedtest/latest`, returns most recent
  result (down/up/ping/jitter).
- `stack-speedtest-history [days]` — `GET /api/speedtest/history?days=<n>`,
  default 7.
- `stack-speedtest-run-now` — `POST /api/speedtest/run`, triggers an
  out-of-schedule test.

### 2.5 Control panel

- `control-panel/services/speedtest_tracker/router.py` — routes matching
  2.4's three fish functions, reading Speedtest Tracker's own REST API
  (`/api/*` on the container, authenticated via a Sanctum token generated
  in-app — same read-off-disk-or-DB pattern as other self-generated keys;
  confirm exact token location during implementation since LinuxServer's
  Speedtest Tracker stores it in its sqlite DB, not a flat config file like
  Tautulli — the read helper will need a sqlite query, not a file read).
- Fleet/tile/commands.json registration — same three-file pattern as 1.6.
- STACK.md entry: schedule choice, APP_KEY generation step, sqlite token
  quirk.

### 2.6 Tests

- pytest for the router (mock the Speedtest Tracker API/DB read).
- Live verification: trigger `stack-speedtest-run-now`, confirm a result
  appears in Speedtest Tracker's own UI and via `stack-speedtest-latest`.
- health-monitor green.

### 2.7 Acceptance

- [x] Container healthy
- [x] APP_KEY generated and in `.env` (not committed — verified `.gitignore`
      covers `.env` before this phase's commit)
- [x] Default login changed (moot - seeded correctly via ADMIN_* env vars,
      see the deviation note above)
- [x] health-monitor probe green
- [x] pytest suite passing
- [x] Live speedtest run + readback verified
- [x] Fish functions callable
- [x] STACK.md entry added
- [ ] Committed as its own commit

---

## Phase 3 — Organizr

**Status:** NOT STARTED
**Risk:** low
**Role:** single landing dashboard with tabs for every service in the stack
(existing + all new ones from this batch).

### 3.1 Compose

```yaml
  organizr:
    restart: unless-stopped
    image: organizr/organizr:latest
    container_name: organizr
    environment:
      PUID: "${PUID}"
      PGID: "${PGID}"
      TZ: "${TZ}"
      fpm: "false"
      branch: "v2-master"
    networks: [stacknet]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:80/ || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    volumes:
      - ./config/organizr:/config
    ports:
      - "8702:80"
    mem_limit: 256m
    mem_reservation: 32m
    cpus: 1
```

### 3.2 Secrets

None required for base operation (single-user setup, auth optional via
Organizr's own UI).

### 3.3 Health monitor

```python
"organizr": (8702, "/"),
```

### 3.4 Tab provisioning (manual by design — see design note)

Organizr has no tab-provisioning API; all tab state lives in its own SQLite
DB. Do not attempt to script this. Instead:

1. On first boot, log into Organizr's setup wizard (documented step, not
   automatable).
2. Add one tab per service currently in the stack, using the port table from
   this doc plus the existing `docker-compose.yml` port mappings. Build the
   full tab list from `docker-compose.yml`'s port bindings at implementation
   time — do not hand-copy a stale list into this doc, since ports here can
   drift.
3. For each tab, check whether the target service sets `X-Frame-Options` or
   a restrictive CSP before enabling iframe mode; if it blocks framing, set
   that tab to "open in new tab" mode instead of iframe. Record which
   services needed which mode in the STACK.md entry so a future service
   addition to Organizr doesn't have to re-discover this per-service.

### 3.5 Fish functions / control panel

- `stack-organizr-tabs` — `GET /api/organizr/tabs`, returns the tab list
  Organizr currently has configured (read via Organizr's own API if it
  exposes one for listing tabs; if it genuinely doesn't, this route reads the
  SQLite DB directly the same way STACK.md documents for other SQLite-backed
  companion apps — verify Organizr's DB schema at implementation time before
  writing the query).
- Fleet/tile/commands.json registration — same pattern as 1.6.

### 3.6 Tests

- pytest for the router's read-only tab-list endpoint.
- Live verification: manual click-through confirming every tab loads its
  target service correctly (this is the one phase where "test" includes a
  manual UI pass, since tab provisioning itself is manual — see 3.4).
- health-monitor green.

### 3.7 Acceptance

- [ ] Container healthy
- [ ] health-monitor probe green
- [ ] Every existing + new service has a working tab (iframe or direct-link,
      whichever the per-service framing check calls for)
- [ ] pytest suite passing for the read-only router
- [ ] STACK.md entry documents the iframe/direct-link decision per service
- [ ] Committed as its own commit

---

## Phase 4 — Scrutiny

**Status:** NOT STARTED
**Risk:** low
**Role:** disk S.M.A.R.T. health trending and failure prediction, layered on
top of (not replacing) the existing `stack-disk-health` raw-`smartctl` check.

### 4.1 Compose

```yaml
  scrutiny:
    restart: unless-stopped
    image: ghcr.io/analogj/scrutiny:latest-omnibus
    container_name: scrutiny
    cap_add:
      - SYS_RAWIO
    devices:
      # Enumerate every physical disk backing this host explicitly at
      # implementation time via `lsblk -d -o NAME,TYPE` — do not use a
      # blanket /dev:/dev or --privileged. Example shape:
      - "/dev/sda:/dev/sda"
      - "/dev/sdb:/dev/sdb"
    networks: [stacknet]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8080/api/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    volumes:
      - ./config/scrutiny/config:/opt/scrutiny/config
      - ./config/scrutiny/influxdb:/opt/scrutiny/influxdb
      - /run/udev:/run/udev:ro
    ports:
      - "8703:8080"
    mem_limit: 512m
    mem_reservation: 64m
    cpus: 1
```

If any host disk is NVMe, also add `cap_add: [SYS_ADMIN]`. Check
`lsblk -d -o NAME,ROTA,TRAN` at implementation time to decide.

### 4.2 Secrets

None.

### 4.3 Health monitor

```python
"scrutiny": (8703, "/api/health"),
```

### 4.4 Fish functions

- `stack-scrutiny-summary` — `GET /api/scrutiny/summary` (proxies Scrutiny's
  own `/api/summary`), all-disk status at a glance.
- `stack-scrutiny-disk <disk_id>` — `GET /api/scrutiny/disk/<disk_id>`
  (proxies `/api/device/{id}/details`), per-disk SMART attribute history.

### 4.5 Control panel

- `control-panel/services/scrutiny/router.py` — proxy routes for the two
  fish functions above, straightforward passthrough to Scrutiny's own REST
  API (no auth needed).
- Fleet/tile/commands.json registration — same pattern as 1.6.
- STACK.md entry: relationship to existing `stack-disk-health`, the explicit
  device list decision (why not `--privileged`), cron schedule (default
  daily, leave as-is — SMART trending doesn't need to run more often).

### 4.6 Tests

- pytest for the router (mock Scrutiny's API).
- Live verification: confirm every physical disk enumerated in the compose
  `devices` list actually shows up with populated SMART data in
  `stack-scrutiny-summary` within one collector cron cycle (default daily —
  trigger a manual collector run for verification instead of waiting a full
  day: `docker exec scrutiny /opt/scrutiny/bin/scrutiny-collector-metrics
  run`).
- health-monitor green.

### 4.7 Acceptance

- [ ] Container healthy
- [ ] Every physical disk has SMART data populated
- [ ] health-monitor probe green
- [ ] pytest suite passing
- [ ] Fish functions callable
- [ ] STACK.md entry added
- [ ] Committed as its own commit

---

## Phase 5 — GAPS-2

**Status:** NOT STARTED
**Risk:** medium — touches Radarr (can push adds) and reads the Plex library
directly; scan cost against the FUSE mount needs real tuning, not defaults.
Concrete numbers from this stack (2026-08-11): a single library-wide
filesystem walk over the FUSE mount can run tens of minutes on a library this
size, and Plex's own DB reconcile (`emptyTrash` over ~1,176 items) took ~45
min with real write contention (`Waited over 10 seconds for a busy database`
in Plex's log). GAPS-2 doing a full Plex+Radarr cross-reference at scan time
is the same shape of operation. **Read `fuse-hang-vs-slow-diagnosis` and
`plex-marked-deleted-db-contention` before picking a scan schedule** — don't
default to upstream's schedule or assume "check current movie count" alone
is enough tuning input; also avoid scheduling GAPS-2 scans to overlap a Plex
library refresh or trash-empty window (see `scoped-plex-library-refresh`).

**Anime-scope decision, locked in ahead of implementation (2026-08-09):** Bear
was asked "general Radarr only" (this section's stated default) vs "both
general and anime" while Phase 1 was being built, and chose **both** — GAPS-2
should scan and report gaps for `radarr` and `radarr_anime`. This overrides
5.2's default below; when 5.2 is implemented, wire GAPS-2 (or the
`stack-gaps2-*` router) against both Radarr instances, not just the general
one.

### 5.1 Compose

```yaml
  gaps2:
    restart: unless-stopped
    image: primetime43/gaps-2:latest
    container_name: gaps2
    networks: [stacknet]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:4277/ || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    volumes:
      - ./config/gaps2:/app/data
    ports:
      - "8704:4277"
    mem_limit: 1024m
    mem_reservation: 128m
    cpus: 2
```

`/app/data` holds `config.enc` and `.config.key` — losing either bricks the
saved configuration (Plex OAuth, Radarr key, TMDB key all re-entry required).
**This volume must be included in whatever backup mechanism replaces the
retired restic setup** — verify new top-level `./config/<service>`
directories get picked up automatically rather than taking it on faith,
since a silently-unbacked-up encryption key is the actual failure mode
this note exists to prevent.

### 5.2 Secrets

Entered via GAPS-2's own Settings UI post-boot, not pre-seeded:
- Plex: OAuth login flow (interactive, one-time).
- Radarr: API key + URL — use the existing Radarr instance; if GAPS-2 should
  also scan the radarr-anime library, this needs a decision Bear should make
  at implementation time (does GAPS-2 report anime gaps too, or only
  general-library gaps? default to general Radarr only unless told
  otherwise, since anime "missing from Plex" detection is noisier given
  the existing anime backfill history in this stack).
- TMDB API key: reuse the same TMDB key already used elsewhere in the stack
  (check `.env` for an existing `TMDB_API_KEY` before asking Bear for a new
  one).
- TheTVDB key: optional, skip unless TV franchise scanning is wanted later.

### 5.3 Health monitor

```python
"gaps2": (8704, "/"),
```

### 5.4 Fish functions

- `stack-gaps2-scan` — `POST /api/gaps2/scan`, triggers a scan.
- `stack-gaps2-missing` — `GET /api/gaps2/missing`, list of movies GAPS-2
  currently considers missing.
- `stack-gaps2-push <tmdb_id>` — `POST /api/gaps2/push` with `{tmdb_id}`,
  pushes one missing title into Radarr. Deliberately per-title, not a bulk
  "push all" function — bulk-adding without review is the kind of one-shot
  destructive-ish action this repo's CLAUDE.md asks to confirm before doing,
  and a missing-movie list can contain false positives (wrong-year matches,
  short films, etc).

### 5.5 Control panel

- `control-panel/services/gaps2/router.py` — routes for the three fish
  functions, proxying GAPS-2's own REST API.
- Fleet/tile/commands.json registration — same pattern as 1.6.
- STACK.md entry: the anime-scope decision from 5.2, the encryption-key
  backup note from 5.1, scan schedule chosen (tie to library size — check
  current movie count via Radarr's API at implementation time and pick
  something reasonable, e.g. weekly for a large library rather than
  upstream's more aggressive default).

### 5.6 Tests

- pytest for the router (mock GAPS-2's API).
- Live verification: run a real scan against the live library, confirm at
  least one known-missing title surfaces correctly, and do one controlled
  single-title push into Radarr, then verify it landed in Radarr's queue/
  wanted list correctly (respecting existing quality profile / root folder
  routing — do not verify against radarr-anime unless 5.2's scope decision
  included it).
- health-monitor green.

### 5.7 Acceptance

- [ ] Container healthy
- [ ] `/app/data` confirmed covered by existing backup mechanism
- [ ] Plex OAuth + Radarr + TMDB keys configured
- [ ] Anime-scope decision made and documented
- [ ] health-monitor probe green
- [ ] pytest suite passing
- [ ] Live scan + one controlled push verified
- [ ] Fish functions callable
- [ ] STACK.md entry added
- [ ] Committed as its own commit

---

## Phase 6 — WatchState

**Status:** NOT STARTED
**Risk:** medium — writes watch-state data continuously; needs both the
scheduled import task and Plex webhook configured correctly, or events get
silently dropped (per WatchState's own documented caveat).

### 6.1 Compose

```yaml
  watchstate:
    restart: unless-stopped
    image: ghcr.io/arabcoders/watchstate:latest
    container_name: watchstate
    networks: [stacknet]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8080/ || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    volumes:
      - ./config/watchstate:/config
    ports:
      - "8705:8080"
    mem_limit: 512m
    mem_reservation: 64m
    cpus: 1
```

### 6.2 Secrets

Plex token entered via WatchState's own setup CLI/UI (its `console`
sub-commands, run via `docker exec`, or its web onboarding — confirm which
path this image exposes at implementation time). No pre-seeding via
secret-injector.

### 6.3 Health monitor

```python
"watchstate": (8705, "/"),
```

### 6.4 Import task + webhook

1. Enable WatchState's own scheduled import task (its internal cron,
   confirm default interval and tune it to match Plex's existing library
   refresh cadence already configured elsewhere in this stack — check
   `stack-plex-refresh-libraries`'s schedule for the cadence to mirror).
   Do not schedule it to overlap a Plex library refresh, backfill, or
   trash-empty window — this stack has confirmed real SQLite write
   contention (`busy database` errors) when Plex's DB takes concurrent write
   pressure from multiple directions at once (see
   `plex-marked-deleted-db-contention` and `scoped-plex-library-refresh`);
   pick a clear offset, don't assume WatchState's reads are cheap enough to
   ignore this.
2. **Also** configure a Plex webhook pointing at WatchState
   (`http://watchstate:8080/v1/api/webhook/plex` or WatchState's documented
   webhook path — confirm exact path in its docs at implementation time)
   for near-real-time updates. Keep the scheduled import running regardless
   — WatchState's own docs warn webhooks alone can drop events, do not
   disable the import task as an "optimization."

### 6.5 Fish functions

- `stack-watchstate-status` — `GET /api/watchstate/status`, last import run
  time/result.
- `stack-watchstate-import-now` — `POST /api/watchstate/import`, triggers an
  out-of-schedule import.
- `stack-watchstate-history <item>` — `GET
  /api/watchstate/history?item=<title>`, watch-state history for a title.

### 6.6 Control panel

- `control-panel/services/watchstate/router.py` — routes for the three fish
  functions, proxying WatchState's own REST API.
- Fleet/tile/commands.json registration — same pattern as 1.6.
- STACK.md entry: import interval chosen, webhook path configured, the
  "keep import task on even with webhooks" caveat restated so a future pass
  doesn't accidentally "clean up" the redundancy.

### 6.7 Tests

- pytest for the router (mock WatchState's API).
- Live verification: mark one episode watched in Plex, confirm it appears in
  WatchState within one import cycle (via `stack-watchstate-history`), and
  separately confirm the webhook itself fires (check WatchState's logs for
  a webhook-triggered event, not just the scheduled import).
- health-monitor green.

### 6.8 Acceptance

- [ ] Container healthy
- [ ] Plex token configured
- [ ] Scheduled import enabled and interval tuned
- [ ] Plex webhook configured and confirmed firing
- [ ] health-monitor probe green
- [ ] pytest suite passing
- [ ] Live watch-state sync verified via both paths (import + webhook)
- [ ] Fish functions callable
- [ ] STACK.md entry added
- [ ] Committed as its own commit

---

## Phase 7 — PlexAniSync

**Status:** NOT STARTED
**Risk:** medium — the one service in this batch with an unautomatable
secret (AniList OAuth, yearly manual renewal) and no persistent web UI.

### 7.1 Compose

Not a long-running web service — runs as a scheduled job via a systemd timer
(mirroring the existing pattern for `kometa` — check
`.claude/skills/kometa-run-and-monitor` or the systemd unit backing Kometa's
own scheduled runs, and copy that structure exactly rather than inventing a
new scheduling mechanism):

```yaml
  plexanisync:
    image: rickdb/plexanisync:latest
    container_name: plexanisync
    networks: [stacknet]
    volumes:
      - ./config/plexanisync:/app/config
    profiles: ["scheduled"]   # not started by `docker compose up`; invoked by the timer
```

New systemd files (mirror whatever unit pattern backs Kometa's scheduled
run — check `systemd/` in this repo for the existing example to copy):
`systemd/plexanisync.service` (runs `docker compose run --rm plexanisync`),
`systemd/plexanisync.timer` (interval matched to WatchState's import
interval from 6.4, so anime and general watch-state sync don't race each
other — pick an offset, not the same exact minute, to avoid both hitting
Plex's API simultaneously). Same contention risk as 6.4's note applies here
too: don't let this offset land inside a Plex library refresh or trash-empty
window either — check `stack-plex-refresh-libraries`'s schedule and any
backup/maintenance windows before picking the final offset.

### 7.2 Secrets

- Plex token: reuse the same token pattern as WatchState (6.2) — do not
  create a second, separately-obtained token if one is already sitting in
  `.env` from Phase 6; check first.
- AniList OAuth token: **cannot be automated.** Interactive OAuth flow,
  1-year expiry. Store as `PLEXANISYNC_ANILIST_TOKEN` in `.env` (not
  committed), obtained by Bear visiting AniList's auth endpoint per
  PlexAniSync's own docs. Add a clearly-flagged comment in `.env.example`
  and a STACK.md entry under a section future sessions will actually read
  (a dated "known landmine" entry, matching this file's existing style for
  things like the AltMount/nzbdav lineage correction) noting the renewal
  date so a future session doesn't waste time re-diagnosing "why did anime
  sync silently stop" a year from now.

### 7.3 Health monitor

Not applicable in the usual HTTP sense (no persistent service). Instead, add
a **run-freshness check**: confirm the systemd timer's last run succeeded
within the expected interval. If `health-monitor`'s existing pattern already
has a mechanism for checking systemd timer freshness (check how it currently
handles Kometa, if at all), reuse that; otherwise this is the one new check
type this batch introduces — keep it minimal (parse `systemctl status
plexanisync.timer` / `journalctl -u plexanisync.service` for last-run
success/failure).

### 7.4 Fish functions

- `stack-plexanisync-run-now` — triggers `systemctl start
  plexanisync.service` (or the docker-compose-manager equivalent — confirm
  which mechanism this repo's other scheduled jobs use for a manual trigger
  and match it).
- `stack-plexanisync-last-run` — reports last run time/result/synced-title-
  count, parsed from the container's own log output (no REST API to query,
  since PlexAniSync is not a persistent service).

### 7.5 Control panel

- `control-panel/services/plexanisync/router.py` — routes for the two fish
  functions above. Since there's no long-running API to proxy, this router
  shells out to `systemctl`/`docker compose run` and parses logs — follow
  whatever existing pattern this repo uses for other systemd-timer-backed
  jobs (check if Kometa's control-panel router already does this, and copy
  its approach rather than inventing a new one).
- Fleet/tile/commands.json registration — same pattern as 1.6, noting in the
  tile that this is a scheduled job, not a persistent service (so its status
  display should show "last run" rather than a simple up/down health dot).
- STACK.md entry: AniList token renewal reminder (see 7.2), scheduling
  offset from WatchState, anime library scope (confirm it targets the
  correct Plex anime library given this stack's existing radarr-anime/
  sonarr-anime split).

### 7.6 Tests

- pytest for the router (mock the systemctl/log-parsing calls).
- Live verification: manually trigger `stack-plexanisync-run-now` against a
  known-watched anime title, confirm the title's watch state appears on the
  configured AniList account, and confirm the systemd timer is enabled
  (`systemctl is-enabled plexanisync.timer`).

### 7.7 Acceptance

- [ ] systemd service + timer installed and enabled
- [ ] Plex token configured (reused from Phase 6 if present)
- [ ] AniList OAuth token configured, renewal date documented in STACK.md
- [ ] Timer offset confirmed not to race WatchState's import
- [ ] pytest suite passing
- [ ] Live sync verified against a real watched title
- [ ] Fish functions callable
- [ ] STACK.md entry added, including the yearly-renewal landmine note
- [ ] Committed as its own commit

---

## Phase 8 — deferred: whole-stack fish-function / endpoint naming cleanup

**Status:** DEFERRED — do not start until Phases 1–7 are all DONE.
**Risk:** high blast radius, not high technical risk — this is a scope/
coordination risk, not a correctness risk.

### 8.1 Why deferred

Phases 1–7 add ~15-20 new fish functions and control-panel routes using
today's existing naming convention. Renaming everything (today's ~150
functions across ~20 services, plus whatever this batch adds) in the same
pass as building new services would mean designing a naming schema against a
moving target. This phase starts only once the new services' own names are
settled and stable.

### 8.2 Locked decisions (from design conversation, 2026-08-08)

- **Scope: whole stack.** Every existing service's fish functions and
  control-panel endpoints, not just the 7 new ones from Phases 1–7.
- **Keep the `stack-<service>-<action>` prefix structure.** The rename is
  about consistency of verb order, phrasing, and eliminating duplicates —
  not a structural redesign of the naming scheme itself.
- **Hard cutover, no deprecated aliases.** Every caller (fish functions
  themselves, `control-panel/static/commands.json`, every `stack-cli-*`
  skill doc, this repo's own docs) gets updated in the same commit set as
  the rename. No transition period, no dead aliases left behind.
- **Own spec.** This phase needs its own brainstorm → design doc → plan
  cycle before implementation — this section is a pointer to that future
  work, not the spec itself.

### 8.3 Known inconsistencies to start the audit from

(Captured 2026-08-08 via `grep -h "^function stack-" fish-functions/*.fish` —
re-verify this list is still current before starting Phase 8, since Phases
1-7 add more functions and any other work between now and then may add
more still.)

- Verb-order drift: `stack-plex-empty-trash` (verb-noun) vs
  `stack-plex-recently-added` (adjective-noun) vs `stack-arr-search-toggle`
  (noun-verb) vs `stack-checkrr-reacquire-guard` (verb-noun-noun).
- Duplicate/ambiguous pair: top-level `stack-recently-added` vs
  `stack-plex-recently-added` — same concept, unclear which is canonical or
  whether the top-level one is dead code. Resolve during the audit, not
  before.
- Inconsistent modifier placement: `stack-radarr-list-import` vs
  `stack-sonarr-custom-list-import` for conceptually similar actions.
- Source-first naming for a family of functions (`stack-letterboxd-radarr-*`,
  `stack-mdblist-radarr-*`, `stack-tmdb-*-import`, `stack-trakt-list-import`)
  that puts the data source before the target app rather than the usual
  `stack-<service>-<action>` order — determine during the audit whether this
  is a deliberate, worth-keeping exception (source-oriented commands read
  naturally as "stack-letterboxd-radarr-watchlist" = "import my Letterboxd
  watchlist into Radarr") or an inconsistency worth normalizing.

### 8.4 What Phase 8's eventual spec must cover

- A full audit output (every current function name, proposed new name,
  reasoning) — not just the illustrative examples in 8.3.
- Every file that references a function name by string: `commands.json`,
  every `stack-cli-*` skill's `SKILL.md`, any cross-reference in `STACK.md`
  or `README.md`.
- A migration checklist proving no reference was missed (e.g. grep for the
  old name across the whole repo post-rename, expect zero hits outside git
  history).
- Whether control-panel REST endpoint paths (`/api/<service>/*`) get renamed
  too, or only the fish function layer — these are currently 1:1 but don't
  have to stay that way; this needs an explicit decision in that spec, not
  an assumption carried over from this doc.

---

## Reference

- Design conversation and approved Artifact:
  `https://claude.ai/code/artifact/6b115a3f-1972-44ff-968a-1d49a70fb281`
- Existing wiring pattern this doc mirrors throughout: tautulli/maintainerr,
  see `docker-compose.yml:786-852`, `control-panel/services/tautulli/router.py`,
  `.claude/skills/health-monitor/monitor.py:32,34`,
  `control-panel/static/js/fleet.js:15,19`,
  `control-panel/static/js/reference.js:18,20`.
- This doc is referenced from Claude's cross-session memory — see
  `MEMORY.md` in the memory store for the pointer entry.
