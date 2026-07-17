#!/usr/bin/env python3
"""Moves movies Plex tags with the "Anime" genre out of the Movies library
and into the Anime Movies library, via Radarr's own move-file mechanism
(PUT /api/v3/movie/editor with moveFiles=true) rather than touching files
directly.

Why Plex's genre and not Radarr's: Radarr/TMDB has no "Anime" genre at all
- confirmed live, e.g. Akira's Radarr genres are just ['Animation', 'Science
Fiction', 'Action']. Only Plex's own agent adds the "Anime" tag, and only
after it has already matched the file. So this can never run *before*
import (there is no reliable earlier signal to key off), only as a sweep
after the fact - see PLAN.md for the alternative (a dedicated Anime Radarr
instance, decided at request time instead of detected after the fact).

Matching Plex items back to Radarr movies: Plex's `Guid` list includes a
`tmdb://<id>` entry for every properly-matched item; Radarr's own movie
list carries the same id as `tmdbId`. That's the only join key used here -
titles are not compared, since re-matched/aliased titles (see today's Zurg
audit) can differ between the two systems for the exact same film.

Run by systemd/stack-sort-anime-movies.{service,timer} (hourly). Safe to
run repeatedly - a movie already on the anime root folder is simply not
returned by the Plex genre query's rootFolderPath filter below, so re-runs
are no-ops for anything already moved.

Usage: sort-anime-movies.py [--dry-run]
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

STACK_DIR = Path(__file__).resolve().parent.parent

MOVIES_SECTION_ID = "14"
ANIME_ROOT_FOLDER = "/data/anime-movies"


def env_get(key):
    env_path = STACK_DIR / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


PLEX_URL = (env_get("PLEX_URL") or "").rstrip("/")
PLEX_TOKEN = env_get("PLEX_TOKEN")
RADARR_URL = "http://localhost:7878"
RADARR_API_KEY = env_get("RADARR_API_KEY")


def plex_get(path):
    url = f"{PLEX_URL}{path}"
    req = urllib.request.Request(url, headers={"X-Plex-Token": PLEX_TOKEN, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def radarr_request(method, path, body=None):
    url = f"{RADARR_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"X-Api-Key": RADARR_API_KEY, "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def anime_tagged_movies():
    """Every Movies-section item currently carrying Plex's "Anime" genre,
    as (title, tmdb_id) pairs. Items without a tmdb:// guid (unmatched, or
    matched against a non-TMDB source) are skipped and reported separately
    - there is nothing to look up in Radarr for those."""
    # includeGuids=1 is required - confirmed live that the bulk /all listing
    # otherwise omits the Guid array entirely (only the single-item
    # /library/metadata/{key} endpoint includes it by default), which would
    # otherwise make every item look "unmatched" below.
    data = plex_get(f"/library/sections/{MOVIES_SECTION_ID}/all?genre=Anime&includeGuids=1")
    items = data.get("MediaContainer", {}).get("Metadata", [])
    matched, unmatched = [], []
    for item in items:
        tmdb_id = None
        for g in item.get("Guid", []):
            if g["id"].startswith("tmdb://"):
                tmdb_id = int(g["id"].removeprefix("tmdb://"))
                break
        if tmdb_id is None:
            unmatched.append(item.get("title"))
        else:
            matched.append((item.get("title"), tmdb_id))
    return matched, unmatched


def radarr_movies_by_tmdb_id():
    movies = radarr_request("GET", "/api/v3/movie")
    return {m["tmdbId"]: m for m in movies}


def main():
    dry_run = "--dry-run" in sys.argv

    if not PLEX_URL or not PLEX_TOKEN:
        print("PLEX_URL/PLEX_TOKEN not configured in .env", file=sys.stderr)
        return 1
    if not RADARR_API_KEY or RADARR_API_KEY == "changeme":
        print("RADARR_API_KEY not configured in .env", file=sys.stderr)
        return 1

    try:
        plex_matched, plex_unmatched = anime_tagged_movies()
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"Plex genre query failed: {e}", file=sys.stderr)
        return 1

    try:
        radarr_by_tmdb = radarr_movies_by_tmdb_id()
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"Radarr movie list fetch failed: {e}", file=sys.stderr)
        return 1

    to_move = []
    no_radarr_match = []
    already_on_anime_root = []
    for title, tmdb_id in plex_matched:
        movie = radarr_by_tmdb.get(tmdb_id)
        if movie is None:
            no_radarr_match.append(title)
            continue
        if movie.get("rootFolderPath") == ANIME_ROOT_FOLDER:
            already_on_anime_root.append(title)
            continue
        to_move.append(movie)

    print(f"Plex: {len(plex_matched)} Anime-tagged movies found, {len(plex_unmatched)} unmatched (no tmdb guid, skipped)")
    if plex_unmatched:
        for t in plex_unmatched:
            print(f"  unmatched (skipped): {t}")
    print(f"Radarr: {len(no_radarr_match)} have no corresponding Radarr movie (not Radarr-managed, skipped)")
    for t in no_radarr_match:
        print(f"  no Radarr match (skipped): {t}")
    print(f"Already on {ANIME_ROOT_FOLDER}: {len(already_on_anime_root)} (no-op)")
    print(f"To move: {len(to_move)}")
    for m in to_move:
        print(f"  {'[dry-run] would move' if dry_run else 'moving'}: {m['title']} ({m['rootFolderPath']} -> {ANIME_ROOT_FOLDER})")

    if dry_run or not to_move:
        return 0

    try:
        radarr_request(
            "PUT",
            "/api/v3/movie/editor",
            {"movieIds": [m["id"] for m in to_move], "rootFolderPath": ANIME_ROOT_FOLDER, "moveFiles": True},
        )
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"Radarr move request failed: {e}", file=sys.stderr)
        return 1

    print(f"Move request submitted for {len(to_move)} movie(s) - Radarr will relocate files in the background.")

    for section_id in (MOVIES_SECTION_ID, "13"):
        try:
            plex_get(f"/library/sections/{section_id}/refresh")
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            print(f"Plex refresh for section {section_id} failed (non-fatal): {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
