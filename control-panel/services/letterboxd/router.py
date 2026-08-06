"""Letterboxd -> Radarr/Sonarr integration routes. Owns every
/api/arr/*letterboxd* and /api/arr/letterboxd/* route - the single-film
and list/watchlist/filmography/collection adds (originally in
services/radarr/router.py, moved here 2026-08-06 once this became a
first-class integration spanning both Radarr and Sonarr).
"""
import time

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.arr_client import (
    ARR_APPS,
    radarr_add_movie,
    radarr_ensure_tags,
    radarr_quality_profile_id_by_name,
    radarr_root_folder_and_profile,
)
from core.db import SessionLocal
from core.responses import fail, ok
from core.security import current_user_or_service
from models.letterboxd_cache import LetterboxdTmdbCache
from services.letterboxd.cache import resolve_tmdb_ids
from services.letterboxd.scraping import (
    LETTERBOXD_DISALLOWED_RE,
    LETTERBOXD_GRID_RE,
    LETTERBOXD_ITEM_SLUG_RE,
    LETTERBOXD_LIST_PAGE_RE,
    LETTERBOXD_TMDB_RE,
    fetch_page,
    fetch_page_or_none,
    scrape_slugs_with_ratings,
    scrape_tags,
)

router = APIRouter(tags=["letterboxd"])

SERVICE_META = {"label": "Letterboxd", "health_check": None}


class LetterboxdAddRequest(BaseModel):
    url: str
    monitored: bool = True
    search: bool = True
    root_folder: str | None = None
    quality_profile: str | None = None
    dry_run: bool = False


@router.post("/api/arr/radarr/add-from-letterboxd")
# current_user_or_service, not current_user: stack-letterboxd-radarr.fish
# calls this unattended via __stack_api's service key (2026-08-06, carried
# over unchanged from services/radarr/router.py).
def radarr_add_from_letterboxd(payload: LetterboxdAddRequest, _=Depends(current_user_or_service)):
    cfg = ARR_APPS["radarr"]
    url = payload.url.strip()
    if "letterboxd.com/film/" not in url:
        fail("Not a Letterboxd film URL - expected something like https://letterboxd.com/film/<slug>/.", status_code=400)
    page_text = fetch_page(url)
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
    rating_quality_map: dict[str, str] | None = None
    tags_as_radarr_tags: bool = False


@router.post("/api/arr/radarr/add-from-letterboxd-list")
# current_user_or_service, not current_user: stack-letterboxd-radarr-list.fish
# calls this unattended via __stack_api's service key (2026-08-06, carried
# over unchanged from services/radarr/router.py).
def radarr_add_from_letterboxd_list(payload: LetterboxdListAddRequest, _=Depends(current_user_or_service)):
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

    first_page = fetch_page(base_url + "/")
    last_page = min(max((int(n) for n in LETTERBOXD_LIST_PAGE_RE.findall(first_page)), default=1), 10)

    if payload.rating_quality_map:
        slug_ratings: dict[str, int | None] = dict(scrape_slugs_with_ratings(first_page))
        for page_num in range(2, last_page + 1):
            page_html = fetch_page_or_none(f"{base_url}/page/{page_num}/")
            if page_html is None:
                break
            slug_ratings.update(dict(scrape_slugs_with_ratings(page_html)))
            time.sleep(0.2)
        slugs = list(slug_ratings.keys())
    else:
        slug_ratings = {}
        slugs = list(dict.fromkeys(LETTERBOXD_ITEM_SLUG_RE.findall(first_page)))
        for page_num in range(2, last_page + 1):
            page_html = fetch_page_or_none(f"{base_url}/page/{page_num}/")
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

    db = SessionLocal()
    try:
        tmdb_ids, unmatched = resolve_tmdb_ids(db, slugs)
    finally:
        db.close()
    tmdb_ids = list(dict.fromkeys(tmdb_ids))
    print(f"letterboxd-list: resolved {len(tmdb_ids)} tmdb id(s), {len(unmatched)} unmatched, out of {len(slugs)} slug(s)")

    try:
        library = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie", headers={"X-Api-Key": cfg["key"]}, timeout=30)
        library.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Couldn't read Radarr's library: {e}")
    existing_tmdb_ids = {m["tmdbId"] for m in library.json()}

    root_folder_path, quality_profile_id = radarr_root_folder_and_profile(cfg, payload.root_folder, payload.quality_profile)

    rating_profile_ids: dict[str, int] = {}
    if payload.rating_quality_map:
        for rating_str, profile_name in payload.rating_quality_map.items():
            pid = radarr_quality_profile_id_by_name(cfg, profile_name)
            if pid is not None:
                rating_profile_ids[rating_str] = pid

    # slug -> resolved tmdb_id, needed to look back up a film's rating (for
    # quality-profile mapping) or its owner-page tags - resolve_tmdb_ids
    # only returns the ids, not which slug produced which id, so track
    # that mapping here too whenever either feature needs it.
    slug_to_tmdb: dict[str, int] = {}
    if payload.rating_quality_map or payload.tags_as_radarr_tags:
        db = SessionLocal()
        try:
            for slug in slugs:
                cached = db.query(LetterboxdTmdbCache).filter_by(slug=slug).first()
                if cached and cached.tmdb_id is not None:
                    slug_to_tmdb[slug] = cached.tmdb_id
        finally:
            db.close()

    slug_to_tag_ids: dict[int, list[int]] = {}
    if payload.tags_as_radarr_tags:
        # base_url is like https://letterboxd.com/<user>/list/<slug> or
        # https://letterboxd.com/<user>/watchlist - the owner segment is
        # always the first path component, valid for every URL shape
        # LETTERBOXD_GRID_RE allows except the bare films/popular/collection
        # ones (which have no single owner - tags_as_radarr_tags on those
        # scrapes zero tags, not an error, since a film with no scraped
        # tags is a normal outcome for this feature).
        owner = base_url.replace("https://letterboxd.com/", "").split("/")[0]
        for slug, tmdb_id in slug_to_tmdb.items():
            user_film_html = fetch_page_or_none(f"https://letterboxd.com/{owner}/film/{slug}/")
            if not user_film_html:
                continue
            tag_names = scrape_tags(user_film_html)
            if tag_names:
                slug_to_tag_ids[tmdb_id] = radarr_ensure_tags(cfg, tag_names)
            time.sleep(0.2)

    added, already, failed = [], [], []
    total_movies = len(tmdb_ids)
    for i, tmdb_id in enumerate(tmdb_ids, 1):
        film_quality_profile_id = quality_profile_id
        if payload.rating_quality_map:
            slug = next((s for s, t in slug_to_tmdb.items() if t == tmdb_id), None)
            rating = slug_ratings.get(slug) if slug else None
            if rating is not None and str(rating) in rating_profile_ids:
                film_quality_profile_id = rating_profile_ids[str(rating)]
        result = radarr_add_movie(cfg, tmdb_id, payload.monitored, payload.search, root_folder_path, film_quality_profile_id,
                                   existing_tmdb_ids, dry_run=payload.dry_run, tag_ids=slug_to_tag_ids.get(tmdb_id))
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
