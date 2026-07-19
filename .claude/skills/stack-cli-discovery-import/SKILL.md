---
name: stack-cli-discovery-import
description: Exact fish CLI command reference for IMDb/MDBList rating lookups and bulk-adding films to Radarr from Letterboxd or MDBList URLs, against this stack's Control Panel. Use whenever the user asks to add a Letterboxd film/list/watchlist/collection/filmography to Radarr, import an MDBList list, or look up a title's rating from the terminal. Trigger phrases: "add this letterboxd list to radarr", "import my letterboxd watchlist", "add this mdblist to radarr and sonarr", "what's this movie's imdb rating", "add this director's filmography".
---

# Stack CLI: Discovery & List Import

<skill_scope skill="stack-cli-discovery-import">
This is a command reference, not an operational tool: it exists so the exact fish function name, argument order, flags, and known limitations for every rating-lookup and list-import terminal command in this stack are already known, without reading the fish source fresh each time. Every command here is a thin fish wrapper around Control Panel's own HTTP API (`http://192.168.4.105:8420`), which does the actual scraping/API calls server-side - no extra container is needed for any of this. The real behavior lives in `control-panel/app.py`.
</skill_scope>

## Calling convention

<calling_convention>
The rating lookups (`stack-rating-imdb`, `stack-rating-mdblist`) are one-line `__stack_api GET <path>` calls.

Every list-import command (`stack-mdblist-import` and all `stack-letterboxd-radarr-*` commands) shares the same flag set and body shape: they use fish's `argparse` to accept `--no-search`, `--no-monitor`, `--dry-run`, and (list-shaped ones only) `--limit N`, build a JSON body (`url`/`list_url`, `search`, `monitored`, `dry_run`, optionally `limit`), and POST it via `__stack_api`. All three flags default to the safe/complete behavior when omitted: search **on**, monitored **on**, dry-run **off**. Pass `--dry-run` first when trying an unfamiliar list to see what *would* be added without writing anything.

None of these read a `STACK_HOST_IP` environment variable - the Control Panel URL is a literal hardcoded string in every function. Both rating lookups use the OMDb/MDBList API keys already present in Kometa's own `config.yml` - no separate account or key is needed.
</calling_convention>

## Command reference

<command_reference>
| Command | Args | What it does |
|---|---|---|
| `stack-rating-imdb` | `<imdb-id>` | A title's IMDb rating via OMDb. |
| `stack-rating-mdblist` | `<imdb-id>` | A title's MDBList score, plus its IMDb sub-rating if MDBList has one. |
| `stack-mdblist-import` | `<mdblist-list-url> [--no-search] [--no-monitor] [--dry-run] [--limit N]` | Imports an MDBList list, routing movies to Radarr and TV shows to Sonarr in one call. Works on any public MDBList list, including their mirrors of common IMDb lists (search mdblist.com for e.g. "imdb top 250") - this is the workaround for the fact that IMDb's own list pages sit behind a Cloudflare-class bot challenge and can't be scraped directly. |
| `stack-letterboxd-radarr` | `<film-url> [--no-search] [--no-monitor] [--dry-run]` | Scrapes one film's TMDb id off its Letterboxd page and adds it to Radarr. |
| `stack-letterboxd-radarr-list` | `<list-url> [--no-search] [--no-monitor] [--limit N] [--dry-run]` | Same technique applied to a custom list (`letterboxd.com/<user>/list/<slug>/`) - scrapes every film's slug off the paginated grid (max 10 pages / 720 films), then each film's own page for its TMDb id. |
| `stack-letterboxd-radarr-watchlist` | `<user-watchlist-url> [--no-search] [--no-monitor] [--limit N] [--dry-run]` | Same technique applied to a user's watchlist. |
| `stack-letterboxd-radarr-watched` | `<user-films-url> [--no-search] [--no-monitor] [--limit N] [--dry-run]` | Same technique applied to a user's watched-films page. |
| `stack-letterboxd-radarr-collection` | `<collection-url> [--no-search] [--no-monitor] [--limit N] [--dry-run]` | Same technique applied to a film collection (`letterboxd.com/films/in/<slug>/`). **Known limitation:** this specific path is gated by an actual Cloudflare JS challenge, not just header sniffing - confirmed live, a bare user-agent gets a real "Just a moment..." page. A full browser-shaped header set passes most of the time but not reliably; an intermittent fetch failure here is this known issue, not a bug in the command - retry. |
| `stack-letterboxd-radarr-filmography` | `<role> <slug> [--no-search] [--no-monitor] [--limit N] [--dry-run]` | Adds a person's whole filmography by crew role (`actor`, `director`, `writer`, `producer`, `editor`, `cinematography`, `composer`, and others - roles aren't hardcoded, an unrecognized one just 404s with a clear error). Builds `letterboxd.com/<role>/<slug>/`. |
| `stack-letterboxd-radarr-popular` | `[--no-search] [--no-monitor] [--limit N] [--dry-run]` | **Confirmed broken, left in place deliberately.** `letterboxd.com/films/popular/`'s poster grid is pure client-side JS hydration - the server-rendered HTML has zero film data at any header combination tried, unlike every other Letterboxd grid this technique covers. This command will currently always report "no films found." It's kept rather than silently pointed at a different page, so the failure is honest instead of quietly returning the wrong list - don't suggest running it expecting real results, and don't treat a "no films found" report from it as a sign something else is broken. |
| `stack-letterboxd-radarr-list-random` | `[--no-search] [--no-monitor] [--limit N] [--dry-run]` | Picks one random URL from a locally cached pool of Letterboxd's own featured lists (`~/.cache/letterboxd_lists.txt`, built by `scripts/scrape_letterboxd.py` off `letterboxd.com/lists/featured/`), removes it from the cache so a future run won't repeat it, then runs `stack-letterboxd-radarr-list` against it to completion, tailing Control Panel's live per-film progress log while it runs. All flags pass straight through. Runs the scraper automatically first if the cache file doesn't exist yet. |
</command_reference>

## Common mistakes

<common_mistakes>
<general_anti_patterns>
- **Running `stack-letterboxd-radarr-popular` expecting real results.** It's a confirmed, permanent limitation of that specific Letterboxd page (client-side rendering), not an intermittent bug - don't retry it hoping for a different outcome, and don't burn time debugging Control Panel's scraper against it.
- **Reading an intermittent failure from `stack-letterboxd-radarr-collection` as a real bug.** That specific `/films/in/` path is Cloudflare-challenge-gated; a failure there is expected some fraction of the time and worth a simple retry before investigating further.
- **Forgetting `--dry-run` exists before running an unfamiliar list against Radarr for real.** Every list-import command supports it - use it first on any list whose size or content isn't already known, especially before a whole filmography or a large custom list.
- **Assuming these commands need a separate scraping container or credentials.** All scraping and TMDb-id resolution happens server-side in Control Panel using keys already present in Kometa's own config - there's nothing else to set up or authenticate.
</general_anti_patterns>
</common_mistakes>

## Resources

<resources>
**Local:**
- `~/.config/fish/functions/stack-rating-*.fish`, `stack-mdblist-import.fish`, `stack-letterboxd-radarr*.fish` - the actual fish source these commands wrap
- `scripts/scrape_letterboxd.py` in this repo - builds the featured-lists cache `stack-letterboxd-radarr-list-random` draws from
- `control-panel/app.py` in this repo - the real behavior behind every endpoint these commands call
</resources>
