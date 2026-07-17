# Dedicated Anime Radarr + Sonarr Instance — Implementation Plan

Status: **the "Alternate lightweight path" (single-instance) is implemented and verified live —
the dual-instance path below it is still just a plan, not started.** Both Radarr and Sonarr now
carry a Recyclarr-managed "[Anime] Remux-1080p" profile (id 7 on both), synced via
`quality_profiles.trash_id` in `config/recyclarr/recyclarr.yml` (gitignored - see that file
directly for the live config, this document for the reasoning). Confirmed via direct API
inspection: correct custom-format scores (Anime BD/Web Tiers, Remux Tiers, Dual Audio,
Uncensored, 10bit, Raws, Dubs Only, v0-v4 all present and matching TRaSH's published defaults)
and correct quality-tier allow/deny groupings on both apps. See "Alternate lightweight path"
below for what was actually done and one real constraint discovered during implementation that
the original draft didn't anticipate (quality *definitions* being instance-wide, not
per-profile) — full detail in this repo's own `CLAUDE.md` landmines section and in
`config/recyclarr/recyclarr.yml`'s comments directly.

It was written alongside the much smaller `scripts/sort-anime-movies.py` sweep (already
implemented, running hourly via `systemd/stack-sort-anime-movies.timer`), which solved the
immediate "165 movies in the wrong library" problem cheaply. This document as a whole was
scoped around a different, bigger problem: **classifying anime correctly at request time**,
with real per-genre quality profiles, instead of inferring it after the fact from Plex's tag -
the lightweight path above achieves that goal without the dual-instance build below it.

## Research findings (added after the initial draft — read before Phase 0)

Three open questions from the first draft, now answered against TRaSH's actual published
guides and this stack's own live config files rather than assumption.

### 1. TRaSH's actual anime quality profiles — what they contain

Confirmed against `trash-guides.info`'s dedicated anime pages for both apps
([Sonarr](https://trash-guides.info/Sonarr/sonarr-setup-quality-profiles-anime/),
[Radarr](https://trash-guides.info/Radarr/radarr-setup-quality-profiles-anime/)) — these are
real, actively maintained guides, not a one-off community post.

**Custom formats (same shape on both apps):**
- **Anime BD Tiers 01–08** (1400→700 pts) and **Anime Web Tiers 01–06** (600→100 pts) — the
  actual quality-tiering backbone, playing the same role this stack's "Unlimited" profile's
  resolution scoring does today, just anime-release-naming-aware.
- **Remux Tiers** (Sonarr: 01–02, Radarr: 01–03), 975→950 pts.
- **Dual Audio, Uncensored, 10bit** — score 0 by default (informational/neutral), optionally
  boosted to +10 (prefer within same tier), +101 (prefer a tier above), or up to +2000
  (Radarr's guide: set as the profile's *minimum* CF score to hard-require Dual Audio).
- **Anime Raws, Dubs Only** (Radarr also lists **Anime LQ Groups**) — −10,000 pts by default
  (effectively excluded), invertible if raws/dub-only is actually preferred.
- **v0–v4** release-versioning markers, −51 to +4 pts.
- Radarr's guide additionally lists **VOSTFR** and **VRV** language/source markers not present
  on the Sonarr side.
- **Prerequisite**: Sonarr V4+ required for this setup. This stack's Sonarr is already on
  **4.0.19.2979** — no upgrade needed if this plan moves forward.

This is a real, meaningfully different rule set from this stack's current "Unlimited" profile
(which intentionally carries zero anime-aware scoring) — confirms the quality-profile benefit
claimed earlier in this document is real, not hypothetical.

### 2. Does this require two instances, or can one Sonarr do it forever?

**TRaSH's own guide explicitly endorses staying on one instance, for both apps** — this is the
single most consequential finding from this research pass, and changes the plan's default
recommendation (see below).

Direct quote, present on **both** the Sonarr and Radarr anime guides: *"It's recommended to run
two [Sonarr/Radarr] instances (one for Anime and one for regular [TV/movies])... However, if
you prefer a single instance, you can create separate quality profiles and assign
[series/movies] accordingly."*

Read that carefully: TRaSH frames the dual-instance setup as a **preference for cleaner
separation**, not a functional requirement. A single instance with a second, anime-specific
quality profile (and, on the Sonarr side, `Series Type: Anime` per-series — a feature this
stack's existing single Sonarr instance already uses today for its `/data/anime` root folder)
is described as a fully supported alternative, not a degraded workaround.

**Practical implication for this stack:** staying on one Sonarr permanently is a legitimate,
TRaSH-sanctioned long-term architecture, not just "acceptable until you get around to
migrating." If the only goal is the quality-profile benefit from finding #1 above, **the
entire Phase 1–3/3a–3c/5–9 compose-and-wiring effort in this plan can be skipped Sonarr-side
and replaced with**: add a second quality profile + matching Recyclarr block to the *existing*
Sonarr instance, assign anime series to it (manually, or via the existing `Series Type: Anime`
setting as a signal), done. Radarr has no per-item "type" flag to key a profile assignment off
today, so its equivalent single-instance path is: assign the new "[Anime] Remux-1080p"-style
profile manually per-movie at add time (via Seerr's profile selection, same mechanism as the
existing multi-connection pattern) rather than automatically. Either way, **this removes
essentially the entire integration surface in the "Full connection checklist" above** — no new
Unpackerr entries, no new NzbDAV Repairs connections, no new Maintainerr connections, no new
Decypharr categories, no new Prowlarr Applications, no new Cleanuparr instance rows, no new
control-panel wiring — because there's no second container to wire in anywhere. The only real
work left is the Recyclarr config + quality profile creation (Phase 4) and, optionally, Seerr
profile-selection wiring (a lighter version of Phase 8).

This doesn't make the dual-instance path wrong — the "What you get" section above (independent
settings not fighting over one instance, matching the existing `decypharr`/`decypharr-alldebrid`
precedent) is still real. But it reframes dual-instance as an *optional upgrade for cleaner
separation*, not a prerequisite for getting TRaSH's anime custom formats working at all. Revisit
Phase 0 decision #1 with this in mind — the honest default recommendation, given this finding,
is **start single-instance** (cheap, TRaSH-endorsed, reversible) and only move to a second
instance later if the single-profile setup genuinely proves limiting in practice.

### 3. Guarantee against ever needing a third Decypharr instance

Verified directly against this stack's own live config files (not just the general reasoning
in Phase 0/3 below), to make this an actual guarantee rather than an inference:

```
config/decypharr/config.json:            debrids: [{"provider": "realdebrid", ...}]  (1 entry)
                                          categories: ["sonarr", "lidarr", "radarr"]
config/decypharr-alldebrid/config.json:  debrids: [{"provider": "alldebrid", ...}]   (1 entry)
                                          categories: ["sonarr", "radarr"]
```

Structurally, `debrids` and `categories` are **separate, independent top-level arrays** in
Decypharr's config schema — there is no per-category field anywhere that scopes a category to
a specific debrid provider. Every category on an instance shares that instance's entire
`debrids` list, unconditionally. This is confirmed by Decypharr's own upstream documentation
(a single instance is explicitly designed to "handle multiple Arr applications simultaneously
using category scoping to keep downloads organized," with provider selection entirely separate
from category selection) and by direct inspection above, not assumed.

**The guarantee holds as long as one condition is true: anime content never needs a *different*
debrid provider* than its non-anime sibling app already uses.** Since Phase 0 decision #2
already commits to `radarr-anime` sharing the existing RD-only `decypharr` instance (new
category `radarr-anime`, same single `realdebrid` provider Radarr's existing `radarr` category
already uses) and `sonarr-anime` sharing the AD-only `decypharr-alldebrid` instance (new
category `sonarr-anime`, same `alldebrid` provider), that condition holds by construction — a
third instance would only ever become necessary if someone later wanted anime specifically
routed to a *different* debrid backend than its non-anime counterpart, which is not part of
this plan's design and not a requirement anywhere in TRaSH's own anime guides either.

**Side finding, worth a look outside this plan's scope**: `CLAUDE.md`'s architecture notes
describe `decypharr` as serving "both Real-Debrid+AllDebrid" — the live config above shows it
configured with only `realdebrid`, one provider. Whether this is stale documentation or a
provider that was intentionally dropped from that instance at some point isn't something this
research pass resolved; flagging it here since it's directly adjacent to the claim being
verified, but it doesn't change the guarantee above either way (one provider or two, the
category-sharing mechanism is identical).

---

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

1. **Scope: stay single-instance, or go dual?** Updated by research finding #2 above — TRaSH's
   own anime guides explicitly endorse a single instance with a second quality profile as a
   supported alternative, not a degraded workaround. **Revised default recommendation: start
   single-instance for both apps.** This gets the entire quality-profile benefit (finding #1)
   for roughly a quarter of the cost — no new containers, no new Full-connection-checklist
   wiring — and Sonarr's existing `/data/anime` root folder + `Series Type: Anime` setting
   already puts it most of the way there. Only fall through to Phases 1–3/3a–3c/5–9 (the full
   dual-instance build) if single-instance genuinely proves limiting later — e.g. profile
   settings that need to differ in ways two profiles on one instance can't express, or a real
   operational need for Radarr/Sonarr-level isolation (separate restart/upgrade cadence,
   separate resource limits) rather than just profile-level separation. If dual-instance is
   still the choice, doing Radarr first still derisks it (Sonarr already has a partial
   precedent to validate against; Radarr's before/after is a cleaner state change to verify).
2. **Debrid gateway sharing (dual-instance path only — moot if staying single-instance).**
   Does `radarr-anime` share the existing `decypharr` instance (new category, e.g.
   `radarr-anime`) or get a third Decypharr instance entirely? **Now a guarantee, not just a
   recommendation** — see research finding #3 above, confirmed directly against both live
   `config/decypharr*/config.json` files: `debrids` and `categories` are independent arrays,
   every category shares the instance's whole `debrids` list, and nothing about anime content
   needs a different provider than its non-anime sibling already uses. Share; a third instance
   would solve a problem that doesn't exist here.
3. **TRaSH anime profile choice — resolved, see research finding #1 above.** Both apps' full
   custom-format lists and default scores are now documented there directly from TRaSH's
   current published guides, Sonarr V4+ prerequisite confirmed already met
   (this stack: 4.0.19.2979). Phase 4 no longer needs its own research pass — go straight to
   import/scoring decisions.
4. **Backlog migration: do it, or don't?** See the dedicated section near the end. Recommend
   deferring this decision until whichever path (single- or dual-instance) is live and
   validated with a real new request — don't commit to a migration approach before you've seen
   the new setup work.

---

## Alternate lightweight path — single-instance (implemented, verified live)

Phase 0 decision #1 came out single-instance, and this path is now **done**, not just planned.
As anticipated, **Phases 1–3, 3a–3c, and 5–9 below did not apply at all** — no second
container, nothing to mount, nothing to wire into Prowlarr/NeutArr/Cleanuparr/Unpackerr/
NzbDAV/Maintainerr/control-panel, no root-folder collision risk. What actually happened,
against what was originally planned:

1. **Sonarr**: a new quality profile, `[Anime] Remux-1080p` (landed as id 7, alongside
   "Unlimited" at id 1), added to the *existing* instance via a new `quality_profiles:` block
   in `config/recyclarr/recyclarr.yml`'s existing `sonarr:` section. **Simpler than planned**:
   rather than hand-listing custom-format trash_ids and scores, Recyclarr's
   `quality_profiles: [{trash_id: ...}]` form pulls the entire profile - qualities tree,
   custom-format associations, and TRaSH-recommended scores - directly from TRaSH's guide by
   ID. Verified via direct API call against the live profile: all expected custom formats
   present with the exact published default scores (Anime BD Tiers 1400→700, Web Tiers
   600→100, Raws/Dubs Only -10000, v0 -51, Dual Audio/Uncensored/10bit at 0), and the correct
   quality-tier allow/deny groupings (2160p+/Raw-HD/576p disallowed, SDTV through
   Bluray-1080p allowed, cutoff at "Bluray 1080p"). Assignment to anime series is still a
   manual per-series choice in Sonarr's UI, as anticipated - TRaSH's guide doesn't describe
   automatic profile assignment by series type.
2. **Radarr**: identical shape, same verification, `[Anime] Remux-1080p` also landed at id 7.
   Profile assignment happens manually per-movie or via Seerr's request-time profile selector,
   as anticipated.
3. **Root folders**: unchanged from the plan - Sonarr's existing `/data/anime`, Radarr's
   `/data/anime-movies` (added earlier this session for `scripts/sort-anime-movies.py`), both
   reused as-is.
4. **Not done this pass**: Seerr profile-selection wiring (item 4 in the original plan) -
   deferred, not blocking; the profile exists and works standalone regardless of whether Seerr
   points at it yet.
5. **Verification performed**: direct API inspection of both apps' new profile (formatItems,
   scores, quality-tier items) rather than a live end-to-end Seerr request - a real anime
   request through Seerr is still worth doing before calling this fully proven in production
   use, but the profile itself is confirmed correctly configured.

**One real constraint surfaced during implementation that the original draft didn't
anticipate**: Radarr/Sonarr's quality *definitions* (min/max file size per resolution tier) are
confirmed instance-wide via `GET /api/v3/qualitydefinition` - one flat list per app, not scoped
per profile. TRaSH's anime guide pairs its custom-format profile with anime-specific quality
*definition* sizes too (`type: anime` in `recyclarr.yml` terms) - applying that here would have
silently overwritten the existing `type: series`/`type: movie` sizes every non-anime
series/movie on these same instances still depends on. **Deliberately not applied** - the new
anime profile gets correct custom-format scoring and quality-tier groupings, but anime content
is still filtered against general-TV/movie file-size expectations, not anime-tuned ones. This
is the one respect in which the lightweight path doesn't fully match what a genuinely separate
instance (dual-instance path below) would provide - documented as a load-bearing, accepted
tradeoff in `CLAUDE.md`'s landmines section and in `recyclarr.yml`'s own comments directly, not
left implicit.

**Two unrelated, pre-existing bugs were found and fixed to even get this far** (full detail in
README's `v10.14.0` History entry and `CLAUDE.md`'s historical-incidents section): Recyclarr's
entire sync had been silently broken since the day it was added (`RADARR_API_KEY`/
`SONARR_API_KEY` never reached its container), and both apps' sole quality profile had drifted
to being named "Any" while `recyclarr.yml` assumed "Unlimited" - Recyclarr couldn't score
anything into either profile until both were fixed. Neither is specific to anime; both would
have blocked *any* future Recyclarr config change, not just this one.

Actual cost: in the same ballpark as the ~1.5–2.5 hour estimate for the anime-profile work
itself, plus meaningful extra time on the two unrelated bugs above before the anime work could
even be tested. Confirms the original reasoning for defaulting to this path over dual-instance:
same TRaSH-endorsed quality-profile benefit, a fraction of the dual-instance cost, and fully
reversible - a later move to dual-instance doesn't have to unwind anything here, since these
custom formats and profile definitions carry over conceptually to a second instance if that
ever becomes the better call.

---

## Phase 1 — Compose: two new services (dual-instance path only)

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

## Phase 2 — First-boot configuration (per new instance) (dual-instance path only)

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

## Phase 3 — Decypharr wiring (dual-instance path only)

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

## Phase 3a — Unpackerr (dual-instance path only; missing from the first draft of this plan)

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

## Phase 3b — NzbDAV's Repairs tab (dual-instance path only; missing from the first draft of this plan)

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

## Phase 3c — Maintainerr (dual-instance path only; missing from the first draft of this plan)

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

## Phase 4 — Recyclarr (TRaSH anime profiles) (dual-instance path; single-instance path covered above)

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

## Phase 5 — Prowlarr (dual-instance path only)

Prowlarr syncs indexer lists to Radarr/Sonarr via its own "Applications" feature — confirmed
live this stack currently has exactly two Application entries (Radarr, Sonarr). Add two more,
same `implementation` type as the existing ones, pointed at the new instances' internal URLs
and API keys. Use `arr-config-sync`'s own pattern/tooling in this repo (`.claude/skills/
arr-config-sync/`) rather than hand-rolling the API calls, since that skill already exists
specifically for this class of change.

---

## Phase 6 — NeutArr (dual-instance path only)

Checked live: NeutArr's config is **one JSON file per Servarr type**
(`config/neutarr/radarr.json`, `sonarr.json`, etc.), but each file's `instances` field is
already an **array** — e.g. `radarr.json` currently has one entry named `"Default"`. Adding the
anime instance is appending a second object to that same array (name it something like
`"Anime"`), **not** creating a new file — a genuine simplification versus what the removed-app
history (Lidarr/Whisparr) might suggest, since those were whole *type* removals, not
multi-instance additions within a type NeutArr already knows about.

---

## Phase 7 — Cleanuparr (dual-instance path only)

Per this repo's own documented gotcha: Cleanuparr's `arr_configs` table is keyed by **Servarr
type** (Radarr/Sonarr/Lidarr/Readarr/Whisparr), not by instance, and already has the one row
each type needs — adding a second Radarr *instance* does not need a new `arr_configs` row,
only a new `arr_instances` row (added via Cleanuparr's own UI, same as any other instance
registration in this stack). Confirm this assumption by checking Cleanuparr's `arr_instances`
table structure once the UI is in front of you — the type-vs-instance distinction here is
important enough to re-verify, not just trust this document.

---

## Phase 8 — Seerr (dual-instance path; single-instance path has a lighter version above)

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

## Phase 9 — control-panel (dual-instance path only)

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

## Phase 10 — Backup coverage (dual-instance path only)

Explicitly check (don't assume) whether `scripts/arr-app-backup.py` and `backup-config.sh` pick
up new instances automatically or need explicit additions — this repo's own history notes that
"a new DB-backed service added later gets zero backup coverage by default" unless the backup
scripts are told about it directly. Two new SQLite-backed Servarr instances are exactly the
class of thing this warning is about.

---

## Phase 11 — End-to-end test (dual-instance path; single-instance path has its own lighter test above)

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
