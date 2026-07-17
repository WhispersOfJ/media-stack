# Dedicated Anime Radarr + Sonarr Instance — Implementation Plan

Status: **not started**. This is a planning document only — nothing in this file has been
applied to the stack. It was written alongside the much smaller `scripts/sort-anime-movies.py`
sweep (already implemented, running hourly via `systemd/stack-sort-anime-movies.timer`), which
solves the immediate "165 movies in the wrong library" problem cheaply. This plan solves a
different, bigger problem: **classifying anime correctly at request time**, with real
per-genre quality profiles, instead of inferring it after the fact from Plex's tag.

## Why this is a separate, bigger thing than the sweep script

Radarr and TMDB have no "Anime" genre at all — verified live during the sweep-script work:
Akira's own Radarr record reports `genres: ['Animation', 'Science Fiction', 'Action']`, nothing
anime-specific. Only Plex's own agent adds the "Anime" tag, and only *after* it has matched the
file. That means:

- The sweep script can only ever be a **cleanup pass**, run after Plex has already scanned and
  tagged something. It cannot prevent an anime movie from landing in the wrong Radarr instance
  or the wrong quality profile at request time — there's no signal to key off before that point.
- A **dedicated instance** fixes this differently: instead of detecting anime-ness after the
  fact, the *human requesting it* (or whoever approves the request in Seerr) decides which
  instance to send it to, before Radarr/Sonarr ever touches it. This is a request-time decision,
  not a content-inspection heuristic — it can never be fooled by a tagging quirk, but it also
  provides **no automatic guardrail**: something requested through the default (non-anime)
  connection still lands in the wrong place with zero warning. See "What this does NOT solve"
  below — the sweep script (or something like it) stays relevant even after this plan ships.

## What you get that the sweep script structurally cannot provide

1. **Independent quality profiles / custom formats.** TRaSH Guides publishes anime-specific
   custom formats (dual-audio scoring, fansub-group handling, etc.) that are meaningfully
   different from this stack's current single "Unlimited" profile. Recyclarr can only cleanly
   sync one profile's worth of custom formats per app instance without the two rule sets
   fighting each other on the same movies/series — a second instance is the actual fix, not a
   workaround.
2. **Root-folder separation from the moment of import**, not after. Sonarr already half-does
   this today (`./media/anime-shows` mounted as a second root folder, `Series Type: Anime` set
   per-series) — this plan extends that pattern to a full second app instance for both movies
   and shows, and gives Radarr an equivalent for the first time (it currently has none).
3. **Matches an existing precedent in this stack.** `decypharr` / `decypharr-alldebrid` already
   establishes "run two instances of the same tool to cleanly separate a concern" as a normal,
   supported pattern here — this isn't a novel shape for the compose file.

## What this does NOT solve (read before starting)

- **The current library.** A new instance starts with an empty database. Anything already
  organized (including everything `sort-anime-movies.py` just moved) stays owned by the
  *existing* Radarr/Sonarr instances unless separately migrated — see "Backlog migration" below.
  Migrating it needs the exact same Plex-genre detection this plan is meant to obsolete; it just
  needs it once, for the move, instead of forever, for ongoing sweeps.
- **Anything that bypasses Seerr.** NeutArr's hunt cycles, a manual "Add Movie" in Radarr's own
  UI, or any future request tool that isn't routed through a Seerr connection specifically
  pointed at the anime instance will still land on whichever instance it was manually pointed
  at — with no automatic correction. Practically: **keep `sort-anime-movies.py`'s timer running
  even after this ships**, pointed at both instances, as a safety net.
- **Seerr does not auto-detect genre.** Confirmed against this repo's own
  `.claude/skills/request-manager-integrator/SKILL.md`: `connect` just registers a second
  server connection (root folder + quality profile). Routing a specific request to it is a
  manual choice by whoever submits/approves that request in Seerr's UI, not an automatic rule.

## Cost estimate (recap, itemized in detail below)

| Phase | Estimate |
|---|---|
| Going-forward setup (new instances, wired into every subsystem, tested) | ~5.5–7 hours |
| Backlog migration (existing anime content into the new instances) | +2–3 hours, uncertain |
| **Total if doing both** | **~8–10 hours** |

(Revised up from the original ~4.5–6 / ~7–9 hour estimate after the connection-checklist
cross-check below turned up three missing integrations — Unpackerr, NzbDAV's Repairs tab, and
Maintainerr — each adding roughly 15–30 minutes of real wiring + verification.)

Compare: the sweep script that's already live took ~1.5 hours total and fully cleared the
165-movie backlog the same day. This plan is worth doing for the quality-profile and
classification-correctness benefits above — not as a faster or cheaper way to solve the same
165-movie problem.

---

## Full connection checklist — every app wired to Radarr/Sonarr today

Cross-checked against `docker-compose.yml` directly (grepped every `radarr`/`sonarr` string
in the file and traced each hit back to its owning service block) rather than relying on
memory of what's "obviously" connected — this caught three real gaps the first draft of this
plan missed entirely. Nothing below should be an unknown by the time Phase 11's end-to-end
test runs.

| App | How it's wired to Radarr/Sonarr today | Covered by |
|---|---|---|
| Prowlarr | "Applications" sync pushes indexers to each instance | Phase 5 |
| Recyclarr | Custom-format/profile sync, one block per instance in `recyclarr.yml` | Phase 4 |
| Decypharr / Decypharr-AllDebrid | Download client, category-scoped | Phase 3 |
| NeutArr | Per-type config file, `instances` array | Phase 6 |
| Cleanuparr | `arr_instances` DB row (type-keyed `arr_configs` already exists) | Phase 7 |
| Seerr | Server connection (root folder + quality profile) | Phase 8 |
| control-panel | `ARR_APPS`/`CONTAINER_LABELS`/`QUEUE_ARR_APPS` + frontend | Phase 9 |
| **Unpackerr** | RAR extraction, `UN_RADARR_0_URL`/`UN_SONARR_0_URL` env vars | **Phase 3a (new, was missing)** |
| **NzbDAV (Repairs tab)** | Read-only root-folder mounts + Radarr/Sonarr API, correlates symlinks back to library entries for delete+research repairs | **Phase 3b (new, was missing)** |
| **Maintainerr** | Plex-lifecycle cleanup (watched/stale removal rules), server connections configured in its own UI | **Phase 3c (new, was missing)** |
| Zilean | No direct connection — "Radarr/Sonarr" in its compose comment is prose about Prowlarr's search flow, not a real wire | N/A, false positive |
| Tautulli | No connection — Plex stats/history only | N/A |
| Byparr | No connection — Prowlarr's indexer proxy only | N/A |

The three bolded rows were absent from the first draft of this plan. They're added as Phase
3a/3b/3c below, alongside a real design conflict Phase 3's original wording glossed over (see
the callout at the start of Phase 3a).

## Phase 0 — Decisions to make before writing any config

These aren't technical prerequisites, they're judgment calls that change the shape of
everything after them. Answer these first:

1. **Scope: Radarr only, Sonarr only, or both?** Sonarr already has a second root folder
   (`./media/anime-shows`) and `Series Type: Anime` per-series — it's most of the way to "anime
   gets different handling" already, just not a separate instance. Radarr has *nothing*
   anime-specific today. If you want to derisk this, **do Sonarr second** (it has less distance
   to travel and an existing partial precedent to validate against), start with Radarr where
   the before/after is a clean, easy-to-verify state change.
2. **Debrid gateway sharing.** Does `radarr-anime` share the existing `decypharr` instance (new
   category, e.g. `radarr-anime`) or get a third Decypharr instance entirely? Recommendation:
   **share** — the reason `decypharr-alldebrid` exists as a *second* instance is Decypharr's
   lack of per-provider (RD vs AD) scoping within one instance, which has nothing to do with
   anime vs non-anime. A third instance would be solving a problem that doesn't exist here.
3. **TRaSH anime profile choice.** Which of TRaSH Guides' anime-specific quality profiles /
   custom-format sets to actually adopt. This needs real research against TRaSH's current
   anime guide (not assumed from this plan) before Recyclarr wiring — treat this as its own
   ~30–45 minute research task inside Phase 4, not a copy-paste.
4. **Backlog migration: do it, or don't?** See the dedicated section near the end. Recommend
   deferring this decision until the going-forward setup is live and validated with a real new
   request — don't commit to a migration approach before you've seen the new instances work.

---

## Phase 1 — Compose: two new services

Add `radarr-anime` and `sonarr-anime` service blocks to `docker-compose.yml`, modeled directly
on the existing `radarr`/`sonarr` blocks (same `<<: *common` anchor, same healthcheck shape).

**Concrete shape for `radarr-anime`** (mirrors `radarr:`, docker-compose.yml lines ~397–429):

```yaml
  radarr-anime:
    <<: *common
    image: ghcr.io/hotio/radarr:release
    container_name: radarr-anime
    networks: [stacknet]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:7878/ping || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    volumes:
      - ./config/radarr-anime:/config
      - /mnt/zurg:/mnt/zurg:rslave
      - /mnt/decypharr:/mnt/decypharr:rslave
      - /mnt/nzbdav:/mnt/nzbdav:rslave
      # New Decypharr category (see Phase 0 decision #2) - NOT the same
      # ./config/decypharr/downloads path the main radarr: service uses,
      # or the two instances' imports would collide on the same directory.
      - ./config/decypharr/downloads-anime:/app/downloads:rslave
      - ./media/anime-movies:/data/anime-movies
    ports:
      - "7879:7878"   # host port must differ from the existing radarr's 7878
    mem_limit: 1g       # start conservative - anime-only library is far smaller
    mem_reservation: 128m
    cpus: 1
```

**Concrete shape for `sonarr-anime`** (mirrors `sonarr:`, lines ~436–463):

```yaml
  sonarr-anime:
    <<: *common
    image: ghcr.io/hotio/sonarr:release
    container_name: sonarr-anime
    networks: [stacknet]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8989/ping || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    volumes:
      - ./config/sonarr-anime:/config
      - /mnt:/mnt:rslave
      - ./config/decypharr-alldebrid/downloads-anime:/app/downloads-ad:rslave
      - ./media/anime-shows:/data/anime
    ports:
      - "8990:8989"   # host port must differ from the existing sonarr's 8989
    mem_limit: 1g
    mem_reservation: 128m
    cpus: 1
```

**Verify before applying:**
- `docker compose config --quiet` — catches YAML/anchor errors before anything starts.
- Confirm `./config/radarr-anime`, `./config/sonarr-anime`,
  `./config/decypharr/downloads-anime`, `./config/decypharr-alldebrid/downloads-anime` don't
  already exist as something else (`ls` each path first) — these are brand-new directories,
  Docker will create them on first mount but only if nothing conflicting is there.
- Every new service needs the explicit `mem_limit`/`cpus` this repo's own audit history says
  is easy to silently skip (`<<: *common` does not set either) — don't ship without them.

Bring up with `docker compose up -d radarr-anime sonarr-anime` (a fresh service, not a
recreate — no need for `--force-recreate` the first time).

---

## Phase 2 — First-boot configuration (per new instance)

Both apps come up with a fresh, unconfigured SQLite DB and a randomly-generated API key in
their own `config/<app>-anime/config.xml`. For each:

1. Read the generated API key: `grep ApiKey config/radarr-anime/config.xml` (same for sonarr).
   Add both to `.env` as `RADARR_ANIME_API_KEY` / `SONARR_ANIME_API_KEY`, matching this repo's
   existing `RADARR_API_KEY`/`SONARR_API_KEY` naming convention exactly.
2. Add the root folder via each app's own API (same call shape verified for the sweep script's
   Radarr work): `POST /api/v3/rootfolder {"path": "/data/anime-movies"}` (Radarr-anime) /
   `POST /api/v3/rootfolder {"path": "/data/anime"}` (Sonarr-anime, mirrors the main Sonarr
   instance's own root-folder path for its existing anime split).
3. Set `Series Type: Anime` as the *default* for new series in Sonarr-anime's settings (not
   per-series like the main instance currently does — since every series added to this instance
   is anime by construction, defaulting it removes a manual step per add).
4. Create the quality profile(s) once Phase 4's TRaSH research is done — don't wire Recyclarr
   against a profile that doesn't exist yet.
5. Set the download client (Phase 3) before adding any content, or first imports will have
   nowhere to land.

---

## Phase 3 — Decypharr wiring

Per Phase 0 decision #2 (share, don't triple the Decypharr instance count):

1. In `config/decypharr/config.json` (gitignored, live config — read it, don't guess the
   shape), add a new category, e.g. `"radarr-anime"`, alongside the existing `"radarr"`
   category. Decypharr's whole `debrids[]` list stays visible to the new category exactly as it
   already is to every other category on that instance — this is expected, not a leak (the
   *actual* reason a second Decypharr instance exists at all is RD-vs-AD provider scoping, which
   doesn't apply here).
2. Point `radarr-anime`'s download client settings at this instance/category (same
   `http://decypharr:8282` URL the main Radarr uses, different category name).
3. Same pattern for `sonarr-anime` against `decypharr-alldebrid`, new category e.g.
   `"sonarr-anime"`.
4. **Verify, don't assume**: grab one small test title through each new instance and confirm it
   actually imports (checks the download-client wiring, the category-to-path mapping, and the
   root folder all at once) before moving on to Phase 4/5's wiring, which all assume imports
   already work.

**⚠ Root-folder collision risk, flagged here rather than left implicit:** Phase 1's
`sonarr-anime` block mounts `./media/anime-shows` as `/data/anime` — the exact same host
directory the *existing* `sonarr` service already owns as its own anime root folder. That's
fine as long as `sonarr-anime` starts with an empty library and only new anime-show requests
ever get routed to it (Phase 8) — two Sonarr instances can both have filesystem access to the
same directory without conflict as long as only one of them believes it *owns* any given
show's files in its database. It stops being fine the moment backlog migration (see the bottom
of this document) moves an existing show's database ownership to `sonarr-anime` while the main
`sonarr` instance still has a stale entry pointed at the same folder — verify the old entry is
actually removed (not just orphaned) before/during any migration, or both instances will fight
over the same files.

---

## Phase 3a — Unpackerr (missing from the first draft of this plan)

Unpackerr handles RAR extraction for Radarr/Sonarr's downloads and is wired directly via
environment variables in its compose block (`docker-compose.yml`, `unpackerr:` service) —
confirmed live: `UN_RADARR_0_URL`/`UN_RADARR_0_API_KEY` and `UN_SONARR_0_URL`/
`UN_SONARR_0_API_KEY`, pointed at the main instances only. Unpackerr's own documented
convention for additional instances is a second numbered set
(verified against Unpackerr's own docs, not assumed): `UN_RADARR_1_URL`/`UN_RADARR_1_API_KEY`,
`UN_SONARR_1_URL`/`UN_SONARR_1_API_KEY`.

Add to the `unpackerr:` service's `environment:` block:

```yaml
      UN_RADARR_1_URL: http://radarr-anime:7878
      UN_RADARR_1_API_KEY: ${RADARR_ANIME_API_KEY}
      UN_SONARR_1_URL: http://sonarr-anime:8989
      UN_SONARR_1_API_KEY: ${SONARR_ANIME_API_KEY}
```

Without this, RAR'd anime releases (real and not uncommon for older/obscure titles per this
stack's own library, per today's audit) would sit unextracted with no error anywhere — the
same silent-gap failure mode this stack's own compose comment already documents for the
original Radarr/Sonarr wiring ("ran with '0 servers' configured since the day it was added").
Recreate `unpackerr` (env-only change, no volume change — a plain `docker compose up -d
unpackerr` picks it up, `--force-recreate` isn't required for an environment-only diff the way
it is for a volume/bind-mount change).

---

## Phase 3b — NzbDAV's Repairs tab (missing from the first draft of this plan)

NzbDAV's Repairs feature (`docker-compose.yml`'s own comment on the `nzbdav:` service, lines
~528–541) needs read-only mounts of the *arr apps' root folders to correlate on-disk
symlinks/`.strm` files back to Radarr/Sonarr library entries, and repairs a broken/missing
Usenet article by calling back into the Radarr/Sonarr API (delete + re-search) — not by
touching the symlink directly. Today it only mounts `/data/movies`, `/data/shows`,
`/data/anime` (the main instances' folders) and is only configured (via NzbDAV's own UI,
backed by its `db.sqlite`, not a config file — same pattern as Cleanuparr's instance storage)
against the main Radarr/Sonarr.

If anime content's *database* ownership ever moves to `radarr-anime`/`sonarr-anime` (i.e. if
you do the backlog migration), NzbDAV's Repairs tab needs a **second pair of Radarr/Sonarr
connections added in its own UI**, pointed at the new instances — otherwise a broken Usenet
article under an anime title would silently stop being repairable (NzbDAV would still see the
file via its existing `/data/anime-movies`/`/data/anime` mounts if those are added to its
compose volumes too, but its repair-by-API-callback would keep hitting the *old* Radarr/Sonarr
instance, which no longer owns that title's database entry, and the repair would fail or
silently no-op depending on how NzbDAV handles an API 404 on an unrecognized title — verify
this behavior directly rather than assuming either outcome).

Add to `nzbdav:`'s volumes if going forward with new instances at all (needed regardless of
whether migration happens, since new anime requests through the new instances still need
Repairs coverage):

```yaml
      - ./media/anime-movies:/data/anime-movies:ro
```

(`./media/anime-shows:/data/anime:ro` is already mounted — no change needed there unless the
path itself changes.)

---

## Phase 3c — Maintainerr (missing from the first draft of this plan)

Maintainerr (Plex-lifecycle cleanup — watched/stale-content removal rules) has its own server
connections to Plex, Radarr, Sonarr, *and* Seerr, all configured post-boot through its own
Settings UI, not environment variables (`docker-compose.yml`'s own comment on the
`maintainerr:` service). This is the easiest of the three missing integrations to overlook
entirely, because nothing about it shows up in a `grep` for API keys or env vars — it's 100%
UI-side state, invisible to a diff of this repo.

If `radarr-anime`/`sonarr-anime` go live and start managing any real content, Maintainerr needs
new server connections added for both **in its own UI**, with their own cleanup rules
(disabled by default, matching this stack's existing convention of shipping Maintainerr rules
off until deliberately enabled) — otherwise anime content silently falls outside whatever
watched/stale cleanup policy the rest of the library has, with no error or warning anywhere,
since Maintainerr simply never looks at instances it was never told about.

---

## Phase 4 — Recyclarr (TRaSH anime profiles)

This is the phase that actually delivers the "independent quality profiles" benefit — don't
skip it or this plan reduces to "two empty apps with the same profile as before," which
provides none of the stated advantage over the sweep-script approach.

1. Research TRaSH Guides' current anime-specific guide (Phase 0 decision #3) — do not copy the
   main `recyclarr.yml`'s custom-format list and assume it's anime-appropriate; that list
   (Bad Dual Groups, No-RlsGroup, Obfuscated, Retags, Scene) was deliberately chosen as
   resolution-agnostic "hygiene" formats for the existing single "Unlimited" profile — TRaSH's
   anime guide will have additional/different picks worth evaluating on their own merits.
2. Add two new top-level blocks to `config/recyclarr/recyclarr.yml`
   (`radarr` already has a sibling `sonarr:` block in this file per the existing structure —
   follow the same `base_url` / `api_key: !env_var` / `custom_formats` shape, pointed at the new
   instances' `.env` vars from Phase 2).
3. Decide whether the new instances get their own named quality profile (e.g. "Anime") from
   scratch, rather than reusing "Unlimited" — since these are fresh instances with no existing
   library to disrupt, this is the one place in this stack where creating a new named profile
   from a TRaSH template is *not* the risky move the main `recyclarr.yml`'s own comments warn
   against for the existing instances.
4. Dry-run Recyclarr (`recyclarr sync --preview`, matching the invocation the existing
   `recyclarr` service already uses) before committing the config, then let its normal cron
   schedule pick it up — no need for an ad-hoc first sync.

---

## Phase 5 — Prowlarr

Prowlarr syncs indexer lists to Radarr/Sonarr via its own "Applications" feature — confirmed
live this stack currently has exactly two Application entries (Radarr, Sonarr). Add two more,
same `implementation` type as the existing ones, pointed at the new instances' internal URLs
and API keys. Use `arr-config-sync`'s own pattern/tooling in this repo (`.claude/skills/
arr-config-sync/`) rather than hand-rolling the API calls, since that skill already exists
specifically for this class of change.

---

## Phase 6 — NeutArr

Checked live: NeutArr's config is **one JSON file per Servarr type**
(`config/neutarr/radarr.json`, `sonarr.json`, etc.), but each file's `instances` field is
already an **array** — e.g. `radarr.json` currently has one entry named `"Default"`. Adding the
anime instance is appending a second object to that same array (name it something like
`"Anime"`), **not** creating a new file — a genuine simplification versus what the removed-app
history (Lidarr/Whisparr) might suggest, since those were whole *type* removals, not
multi-instance additions within a type NeutArr already knows about.

---

## Phase 7 — Cleanuparr

Per this repo's own documented gotcha: Cleanuparr's `arr_configs` table is keyed by **Servarr
type** (Radarr/Sonarr/Lidarr/Readarr/Whisparr), not by instance, and already has the one row
each type needs — adding a second Radarr *instance* does not need a new `arr_configs` row,
only a new `arr_instances` row (added via Cleanuparr's own UI, same as any other instance
registration in this stack). Confirm this assumption by checking Cleanuparr's `arr_instances`
table structure once the UI is in front of you — the type-vs-instance distinction here is
important enough to re-verify, not just trust this document.

---

## Phase 8 — Seerr

Use `.claude/skills/request-manager-integrator/` exactly as documented:

```bash
python3 integrator.py connect radarr --root /data/anime-movies --profile "<anime profile name>" --name "Radarr (Anime)"
python3 integrator.py connect sonarr --root /data/anime --profile "<anime profile name>" --name "Sonarr (Anime)"
python3 integrator.py verify
```

Remember: this only creates the connection. **It does not make Seerr choose it automatically**
for anime requests — whoever submits or approves a request has to pick "Radarr (Anime)" /
"Sonarr (Anime)" explicitly. If Seerr's version in use has any per-genre auto-routing feature,
that would need separate research to confirm — do not assume it exists based on this plan.

---

## Phase 9 — control-panel

Same shape of edit as today's Whisparr/Stash removal, in reverse, for two new apps:

- `ARR_APPS` (app.py): two new entries, `radarr-anime` / `sonarr-anime`, same shape as the
  existing `radarr`/`sonarr` entries (`url`, `api`, `key` from the new `.env` vars, `label`,
  `import_events`).
- `QUEUE_ARR_APPS`: add both if you want Unstick/manual-import parity with the main instances.
- `CONTAINER_LABELS`: display labels for the container grid.
- `static/app.js`: `ARR_APPS` and `QUICK_LINKS` arrays, new ports (7879/8990 per Phase 1).
- Rebuild + force-recreate control-panel (same as any `static/`/`app.py` change —
  `docker compose build control-panel && docker compose recreate control-panel`, per this
  stack's own documented "build:, not a pre-built image" gotcha).

---

## Phase 10 — Backup coverage

Explicitly check (don't assume) whether `scripts/arr-app-backup.py` and `backup-config.sh` pick
up new instances automatically or need explicit additions — this repo's own history notes that
"a new DB-backed service added later gets zero backup coverage by default" unless the backup
scripts are told about it directly. Two new SQLite-backed Servarr instances are exactly the
class of thing this warning is about.

---

## Phase 11 — End-to-end test

Before calling this done: submit one real anime movie and one real anime show request through
Seerr, explicitly picking the new connections, and confirm the whole chain — Seerr → correct
Radarr/Sonarr instance → correct quality profile applied → correct Decypharr category →
correct download → correct root folder → correct Plex library (Anime Movies / Anime Shows,
not Movies / TV Shows) — end to end, not just that the container is up.

---

## Backlog migration (optional, separate decision — see Phase 0 #4)

Migrating the movies `sort-anime-movies.py` already relocated (and the pre-existing Sonarr
anime-tagged shows still sitting in the main Sonarr instance) into these new dedicated
instances is **not** a file operation — the files are already in the right *folders*
(`./media/anime-movies`, `./media/anime-shows`). What's missing is Radarr/Sonarr *database*
ownership: the main instances still believe they manage these titles.

Realistic approach, if you decide to do this:
1. In the main Radarr/Sonarr instance, remove each anime-tagged title **without deleting
   files** (Radarr/Sonarr both support this as a distinct option from a full delete).
2. In the new dedicated instance, add the same title back (search disabled — the file already
   exists) pointed at its existing folder, and let Radarr/Sonarr's own import-existing-file
   flow pick it up and match it to the file already sitting there.
3. This still needs the same Plex-genre detection `sort-anime-movies.py` already implements to
   know *which* titles to migrate — reuse that script's Plex-query logic rather than writing a
   second one from scratch.

This is real, uncertain, per-item work (165 movies plus however many existing Sonarr anime
entries) — budget the full 2–3 hours from the cost table, and expect some titles to need manual
attention (a title Radarr/Sonarr can't cleanly re-match against the existing file on the second
add, the same class of problem the Zurg/Plex audit earlier this week ran into repeatedly).
