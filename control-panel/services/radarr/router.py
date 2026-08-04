"""Radarr-only routes (no Sonarr equivalent), ported from app.py
(lines ~1726-2126, ~2765-2792) - Phase 3 of
.claude/plans/evolved-control-panel-backend.plan.md.

All manual UI actions, no automation caller - every route requires
current_user.
"""
import re
import time

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.arr_client import ARR_APPS, get_movie_or_episode, radarr_add_movie, radarr_root_folder_and_profile
from core.responses import fail, ok
from core.security import current_user

router = APIRouter(tags=["radarr"])

SERVICE_META = {"label": "Radarr", "health_check": None}

# Letterboxd doesn't expose TMDb ids directly, but every matched film page
# links to its TMDb entry in the sidebar - regex is simpler and more stable
# than parsing Letterboxd's HTML structure.
LETTERBOXD_TMDB_RE = re.compile(r"themoviedb\.org/movie/(\d+)")
LETTERBOXD_ITEM_SLUG_RE = re.compile(r'data-item-slug="([^"]+)"')
LETTERBOXD_LIST_PAGE_RE = re.compile(r"/page/(\d+)/")

# robots.txt's "User-agent: *" section disallows these sort/filter path
# segments specifically.
LETTERBOXD_DISALLOWED_RE = re.compile(
    r"/(by|on|tag|genre|country|language|decade|friends)/"
    r"|/popular/this/"
    r"|/films/year/"
    r"|/films/[^/]+/year/"
    r"|/films/[^/]+/size/large/"
)
LETTERBOXD_GRID_RE = re.compile(
    r"^https://letterboxd\.com/(?:[^/]+/(?:list/[^/]+|watchlist|films)|[a-z-]+/[^/]+|films/in/[^/]+|films)/?$"
)

_LETTERBOXD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}


def _letterboxd_page(url: str) -> str:
    try:
        page = httpx.get(url, headers=_LETTERBOXD_HEADERS, timeout=15, follow_redirects=True)
        page.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Couldn't fetch {url}: {e}")
    return page.text


def _letterboxd_page_or_none(url: str) -> str | None:
    try:
        page = httpx.get(url, headers=_LETTERBOXD_HEADERS, timeout=15, follow_redirects=True)
        page.raise_for_status()
    except httpx.HTTPError:
        return None
    return page.text


class LetterboxdAddRequest(BaseModel):
    url: str
    monitored: bool = True
    search: bool = True
    root_folder: str | None = None
    quality_profile: str | None = None
    dry_run: bool = False


@router.post("/api/arr/radarr/add-from-letterboxd")
def radarr_add_from_letterboxd(payload: LetterboxdAddRequest, _=Depends(current_user)):
    cfg = ARR_APPS["radarr"]
    url = payload.url.strip()
    if "letterboxd.com/film/" not in url:
        fail("Not a Letterboxd film URL - expected something like https://letterboxd.com/film/<slug>/.", status_code=400)
    page_text = _letterboxd_page(url)
    match = LETTERBOXD_TMDB_RE.search(page_text)
    if not match:
        fail("No TMDb link found on that Letterboxd page - it may be unmatched to TMDb.", status_code=404)
    tmdb_id = int(match.group(1))

    try:
        existing = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie", params={"tmdbId": tmdb_id},
                              headers={"X-Api-Key": cfg["key"]}, timeout=20)
        existing.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Couldn't check whether Radarr already has this movie: {e}")
    existing_movies = existing.json()
    if existing_movies:
        m = existing_movies[0]
        return ok(f'"{m["title"]}" ({m.get("year")}) is already in Radarr.', tmdbId=tmdb_id, radarrId=m["id"], alreadyAdded=True)

    try:
        lookup = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie/lookup/tmdb", params={"tmdbId": tmdb_id},
                            headers={"X-Api-Key": cfg["key"]}, timeout=20)
        lookup.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Radarr's TMDb lookup failed: {e}")
    movie = lookup.json()
    if not movie or not movie.get("title"):
        fail(f"Radarr has no TMDb match for id {tmdb_id}.", status_code=404)

    root_folder_path, quality_profile_id = radarr_root_folder_and_profile(cfg, payload.root_folder, payload.quality_profile)
    movie["qualityProfileId"] = quality_profile_id
    movie["rootFolderPath"] = root_folder_path
    movie["monitored"] = payload.monitored
    movie["addOptions"] = {"searchForMovie": payload.search}

    if payload.dry_run:
        return ok(f'Would add "{movie["title"]}" ({movie.get("year")}) to Radarr - dry run, nothing written.',
                   tmdbId=tmdb_id, dryRun=True)

    try:
        add = httpx.post(f"{cfg['url']}/api/{cfg['api']}/movie", json=movie, headers={"X-Api-Key": cfg["key"]}, timeout=30)
        add.raise_for_status()
    except httpx.HTTPStatusError as e:
        fail(f"Radarr rejected the add: {e.response.text.strip() or e}")
    except httpx.HTTPError as e:
        fail(f"Radarr add failed: {e}")

    added = add.json()
    return ok(f'Added "{added.get("title", movie["title"])}" ({added.get("year", movie.get("year"))}) to Radarr.',
              tmdbId=tmdb_id, radarrId=added.get("id"))


class LetterboxdListAddRequest(BaseModel):
    url: str
    monitored: bool = True
    search: bool = True
    root_folder: str | None = None
    quality_profile: str | None = None
    limit: int | None = None
    dry_run: bool = False


@router.post("/api/arr/radarr/add-from-letterboxd-list")
def radarr_add_from_letterboxd_list(payload: LetterboxdListAddRequest, _=Depends(current_user)):
    cfg = ARR_APPS["radarr"]
    base_url = payload.url.strip().rstrip("/")
    if LETTERBOXD_DISALLOWED_RE.search(base_url + "/"):
        fail(
            "That URL includes a sort/filter option Letterboxd's robots.txt disallows scraping "
            "(by/, genre/, decade/, year/, this/week/, size/large/, etc). Use the plain, unsorted URL.",
            status_code=400,
        )
    if not LETTERBOXD_GRID_RE.match(base_url):
        fail(
            "Not a recognized Letterboxd list/watchlist/filmography/collection URL - expected something like "
            "https://letterboxd.com/<user>/list/<slug>/, https://letterboxd.com/<user>/watchlist/, "
            "https://letterboxd.com/<user>/films/, https://letterboxd.com/actor/<slug>/, "
            "https://letterboxd.com/films/in/<collection>/, or https://letterboxd.com/films/popular/.",
            status_code=400,
        )

    first_page = _letterboxd_page(base_url + "/")
    last_page = min(max((int(n) for n in LETTERBOXD_LIST_PAGE_RE.findall(first_page)), default=1), 10)

    slugs = list(dict.fromkeys(LETTERBOXD_ITEM_SLUG_RE.findall(first_page)))
    for page_num in range(2, last_page + 1):
        page_html = _letterboxd_page_or_none(f"{base_url}/page/{page_num}/")
        if page_html is None:
            break
        slugs.extend(LETTERBOXD_ITEM_SLUG_RE.findall(page_html))
        time.sleep(0.2)
    slugs = list(dict.fromkeys(slugs))
    if not slugs:
        fail(
            "No films found on that Letterboxd page. Some pages (e.g. /films/popular/) render their "
            "poster grid client-side in JS and have no scrapeable server-rendered film data.",
            status_code=404,
        )

    limit = min(payload.limit, 720) if payload.limit else 720
    slugs = slugs[:limit]

    tmdb_ids = []
    unmatched = []
    total_slugs = len(slugs)
    for i, slug in enumerate(slugs, 1):
        match = LETTERBOXD_TMDB_RE.search(_letterboxd_page(f"https://letterboxd.com/film/{slug}/"))
        if match:
            tmdb_ids.append(int(match.group(1)))
            print(f"letterboxd-list: [{i}/{total_slugs}] matched {slug} -> tmdb {match.group(1)}")
        else:
            unmatched.append(slug)
            print(f"letterboxd-list: [{i}/{total_slugs}] no TMDb match for {slug}")
        time.sleep(0.2)
    tmdb_ids = list(dict.fromkeys(tmdb_ids))

    try:
        library = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie", headers={"X-Api-Key": cfg["key"]}, timeout=30)
        library.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Couldn't read Radarr's library: {e}")
    existing_tmdb_ids = {m["tmdbId"] for m in library.json()}

    root_folder_path, quality_profile_id = radarr_root_folder_and_profile(cfg, payload.root_folder, payload.quality_profile)

    added, already, failed = [], [], []
    total_movies = len(tmdb_ids)
    for i, tmdb_id in enumerate(tmdb_ids, 1):
        result = radarr_add_movie(cfg, tmdb_id, payload.monitored, payload.search, root_folder_path, quality_profile_id,
                                   existing_tmdb_ids, dry_run=payload.dry_run)
        if result["status"] == "already":
            already.append(tmdb_id)
            print(f"letterboxd-list: [{i}/{total_movies}] tmdb {tmdb_id} already in Radarr")
        elif result["status"] == "added":
            added.append(result["title"])
            verb = "would add" if payload.dry_run else "added"
            print(f'letterboxd-list: [{i}/{total_movies}] {verb} "{result["title"]}"')
        else:
            failed.append(result["reason"])
            print(f"letterboxd-list: [{i}/{total_movies}] failed - {result['reason']}")

    verb = "would be added" if payload.dry_run else "added"
    summary = f"{len(added)} {verb}, {len(already)} already in Radarr, {len(failed)} failed"
    if unmatched:
        summary += f", {len(unmatched)} had no TMDb match"
    return ok(summary, added=added, alreadyCount=len(already), failed=failed, unmatched=unmatched, dryRun=payload.dry_run)


class ExcludeRequest(BaseModel):
    movieId: int


@router.post("/api/arr/radarr/exclude")
def arr_radarr_exclude(body: ExcludeRequest, _=Depends(current_user)):
    """The durable fix for movies that keep getting silently re-monitored by
    an import list's periodic sync - plain unmonitor only holds until the
    next sync. No Sonarr equivalent exists."""
    cfg = ARR_APPS["radarr"]
    movie = get_movie_or_episode("radarr", cfg, body.movieId)
    if movie is None:
        fail(f"Movie {body.movieId} not found in Radarr.", status_code=404)
    try:
        r = httpx.post(f"{cfg['url']}/api/{cfg['api']}/exclusions",
                        json={"tmdbId": movie.get("tmdbId"), "movieTitle": movie.get("title"), "movieYear": movie.get("year")},
                        headers={"X-Api-Key": cfg["key"]}, timeout=20)
        if r.status_code not in (200, 201, 400, 409):
            r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Exclusion failed: {e}")
    return ok(f"Excluded \"{movie.get('title')}\" from Radarr import lists.", movieId=body.movieId)
