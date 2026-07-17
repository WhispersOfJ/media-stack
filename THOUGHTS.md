# THOUGHTS

Planning/brainstorm doc, not shipped documentation - same status as `PLAN.md`. Two things in
here: a proposal for a "hub" repo to make James's projects easier to find, and a sync-debt
finding surfaced while updating docs across all three repos in this ecosystem (2026-07-17).

## Idea: a hub repo for project discovery

The problem: three repos exist (`media-stack`, private; `Stackalicious`, public mirror;
`StackScripts`, public standalone redistribution) plus whatever comes next, and nothing
currently answers "what has this person built" in one place. Someone finding `StackScripts` on
GitHub has no obvious path to `Stackalicious` (the richer reference implementation it was
extracted from) unless they already know to look.

**Constraint that shapes every option below: `media-stack` is private by design and must stay
that way.** It carries the real LAN IP and host username; `Stackalicious` exists specifically
as the sanitized public version so those never need to leave this machine. A hub repo is
public by definition - it can point at `Stackalicious` and `StackScripts`, never at
`media-stack` itself, and never at anything that would let someone infer real host details from
the fact that a private third repo exists. Whatever gets built, treat this the same as the
sanitization rule already documented in `Stackalicious/AGENTS.md`.

### Option A: GitHub profile README repo

Create a repo literally named `WhispersOfJ` (matching the GitHub username exactly) - GitHub
auto-renders that repo's `README.md` on the profile page (`github.com/WhispersOfJ`) with zero
other infrastructure. Lowest effort, immediate visibility to anyone who clicks through from any
starred/forked repo or a commit author link. Content: a short intro, then a card per public
project (one-liner, tech stack, link), starting with `Stackalicious` and `StackScripts`.

### Option B: dedicated hub/portfolio repo

A separate repo (`hub`, `portfolio`, whatever name) with a single categorized `README.md` -
"awesome-list" style. More discoverable via GitHub search on its own terms than a profile
README is, and doesn't require the exact-username-match trick. Can carry badges
(shields.io: build status, last commit, license) per linked repo with no build step. Natural
place to also note relationships between repos explicitly - e.g. "Stackalicious is the
sanitized reference version of a private stack; StackScripts is the standalone toolkit
extracted from it" - context a visitor to just one of the three repos wouldn't otherwise get.

### Option C: GitHub Pages site off the hub repo

Same content as Option B, rendered as an actual small site (GitHub Pages, no server) instead of
a plain README - room for screenshots/architecture diagrams Control Panel could supply, nicer
first impression. More effort, no infra cost (Pages is free/static). Worth it only if the
portfolio is going to be shown around (resume, forum post) rather than mostly discovered
organically via GitHub itself.

### Option D: topics + cross-link footer, no new repo at all

Lowest-effort option: add GitHub "topics" tags (`self-hosted`, `media-server`,
`plex`, `docker-compose`) to `Stackalicious` and `StackScripts` so they're discoverable via
GitHub's own topic search, and add a small standard footer to each public repo's README
linking to its siblings ("Part of a small toolkit - see also: [Stackalicious] / [StackScripts]").
No hub repo to maintain at all, but also no single landing page - relies on someone landing on
one of the two repos first.

### Recommendation

Start with **A + D together**: a profile README (cheap, immediate) plus footer cross-links
between `Stackalicious` and `StackScripts` (cheap, fixes the "no path between them" gap right
now). Upgrade to B or C later only if there's a reason to point people at a portfolio
independent of GitHub's own profile page (a resume link, a personal domain). Don't build C
speculatively - it's the most effort for a payoff that only matters in a specific
context (actively job-hunting or promoting the project) that may not apply.

## Finding: Stackalicious and StackScripts are behind media-stack's latest work

While updating README/CHANGELOG across all three repos (2026-07-17, alongside the v10.15.0
poster-sync work), checked whether that work had actually been synced downstream per each
repo's own `AGENTS.md`. It hadn't - flagging here rather than writing changelog entries that
would falsely claim parity:

- **`Stackalicious/control-panel/app.py`** is 260 lines behind `media-stack`'s (3150 vs 3410);
  **`static/app.js`** is 529 lines behind (820 vs 1349); **`static/commands.json`** (1314 lines,
  the command-registry/atmosphere-theme feature) doesn't exist there at all. This is the poster
  sync feature, the `/api/container/{name}/logs/stream` SSE endpoint, and the UI/a11y pass from
  media-stack's `27d875e`, none of it pulled over yet.
- **`scripts/sort-anime-movies.py`, `scripts/scrape_letterboxd.py`, and the newly-added
  `scripts/audit-tmdb-links.py`** don't exist in `Stackalicious/scripts/` yet either.
- **`StackScripts`** inherits the same gap one level further removed (it syncs from
  Stackalicious, not media-stack directly, per its own `AGENTS.md`) - already carrying a known,
  self-documented lag from before this session too (its `CHANGELOG.md` v2.7.0 entry says outright
  that the Lidarr/Bindery/Readarr reinstatement "hasn't been synced to this repo yet").

This is a real, pre-existing pattern in this project, not a new problem - both repos already
track their own lag honestly (Stackalicious's `TODO.md`, StackScripts' own changelog caveats)
rather than pretending to be current. Didn't attempt the actual port in this pass: it's a
few-thousand-line, sanitization-sensitive change (control-panel especially) that deserves its
own dedicated session rather than being rushed inside a docs-update pass. Fixed the one
self-contained inaccuracy found along the way (StackScripts' README still said "70 commands"
after the Whisparr/Stash removal dropped it to 67 - its own changelog entry already said as
much). Worth noting: a hub repo (above) or even just a simple version-comparison note in each
repo's own docs would make this kind of drift visible without needing an incidental audit like
this one to surface it.
