"""Poster-sync routes (auto sync + manual review/apply), ported from
app.py (lines 270-283, 1065-1379) - Phase 4 of
.claude/plans/evolved-control-panel-backend.plan.md.

Owns the sync/review job state and the two background workers; actual
candidate lookup lives in candidates.py, cooldown persistence in
state.py. Mutating routes (sync/review/apply) use current_user_or_service
- the auto-sync path is systemd-timer-invoked (3x/day movies, 1x/day
shows), same automation-invoked exception as services/tautulli's
terminate-stream and services/kometa's run-now.
"""
import json
import queue
import threading
import time
from typing import Literal

import httpx
from core.plex_client import PLEX_URL, plex_headers, plex_sections
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from services.posters.candidates import FANART_KEY, TMDB_KEY, TVDB_KEY, omdb_key, resolve_poster_candidates
from services.posters.state import POSTER_STATE_LOCK, load_poster_state, poster_cooldown_remaining, save_poster_state

router = APIRouter(tags=["posters"])

SERVICE_META = {"label": "Poster Sync", "health_check": None}


class PosterSyncRequest(BaseModel):
    library: str
    dry_run: bool = False
    source: Literal["tmdb", "fanart", "tvdb", "omdb", "tvmaze"] = "tmdb"


class PosterReviewRequest(BaseModel):
    library: str
    source: Literal["tmdb", "fanart", "tvdb", "omdb", "tvmaze"] = "fanart"


class PosterApplyRequest(BaseModel):
    rating_key: str
    url: str


def _require_source_configured(source: str) -> None:
    if source == "fanart":
        if not FANART_KEY:
            fail("Fanart isn't configured (FANART_KEY not set in .env).", status_code=503)
    elif source == "tvdb":
        if not TVDB_KEY:
            fail("TheTVDB isn't configured (TVDB_KEY not set in .env).", status_code=503)
    elif source == "omdb":
        if not omdb_key():
            fail("OMDb isn't configured (OMDB_KEY not set in .env).", status_code=503)
    elif source == "tvmaze":
        pass  # free, no key - a movie library will just get every item skipped
    elif not TMDB_KEY:
        fail("TMDb isn't configured (TMDB_KEY not set in .env).", status_code=503)


# ---------------------------------------------------------------------
# Auto sync - one job at a time, in-memory only (no persistence across a
# panel restart) - progress streams over SSE to whichever browser tab has
# the stream open, same technique as the container-logs stream.
# ---------------------------------------------------------------------
POSTER_SYNC_LOCK = threading.Lock()
POSTER_SYNC_STATE = {"running": False, "queue": None}


def run_poster_sync(library_title: str, dry_run: bool, q: queue.Queue, source: str = "tmdb"):
    try:
        sections = plex_sections()
    except httpx.HTTPError as e:
        q.put(f"ERROR Could not read Plex libraries: {e}")
        return
    section = next((s for s in sections if s["title"].lower() == library_title.lower()), None)
    if not section or section.get("type") not in ("movie", "show"):
        q.put(f"ERROR No movie/show library found matching '{library_title}'.")
        return
    media_type = section["type"]

    try:
        r = httpx.get(
            f"{PLEX_URL}/library/sections/{section['key']}/all?X-Plex-Container-Size=100000",
            headers=plex_headers(), timeout=60,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        q.put(f"ERROR Could not list '{library_title}': {e}")
        return

    items = r.json()["MediaContainer"].get("Metadata", [])
    total = len(items)
    q.put(f"INFO Scanning {total} items in '{library_title}' ({media_type}){' - dry run' if dry_run else ''}…")

    with POSTER_STATE_LOCK:
        poster_state = load_poster_state()

    updated = skipped = failed = 0
    for i, item in enumerate(items, 1):
        rating_key = item["ratingKey"]
        title = item.get("title", "Unknown")
        year = item.get("year", "")
        label = f"{title} ({year})" if year else title

        # Cooldown check first, before any Plex/TMDb/Fanart lookup calls -
        # no point spending those on an item we won't touch either way.
        # Checked even on a dry run, so a preview accurately shows what a
        # real run would skip - just never updates the timestamp itself.
        remaining = poster_cooldown_remaining(poster_state, rating_key)
        if remaining > 0:
            hours = remaining / 3600
            q.put(f"SKIP [{i}/{total}] {label}: cooldown ({hours:.1f}h left of 48h since last poster change)")
            skipped += 1
            continue

        # The section listing's Metadata entries don't carry Guid - only
        # the single-item metadata endpoint does (confirmed live).
        try:
            meta_r = httpx.get(f"{PLEX_URL}/library/metadata/{rating_key}", headers=plex_headers(), timeout=15)
            meta_r.raise_for_status()
            meta = meta_r.json()["MediaContainer"]["Metadata"][0]
        except httpx.HTTPError as e:
            q.put(f"FAIL [{i}/{total}] {label}: could not read metadata ({e})")
            failed += 1
            continue

        used_source, candidates = resolve_poster_candidates(meta, media_type, source, limit=1)
        if not candidates:
            q.put(f"SKIP [{i}/{total}] {label}: no poster in {source} or its fallback")
            skipped += 1
            continue
        poster_url = candidates[0]["url"]
        via = "" if used_source == source else f" via {used_source} fallback"

        if dry_run:
            q.put(f"OK [{i}/{total}] {label}: would set poster{via} ({poster_url})")
            updated += 1
            continue

        try:
            up_r = httpx.post(
                f"{PLEX_URL}/library/metadata/{rating_key}/posters",
                params={"url": poster_url}, headers=plex_headers(), timeout=30,
            )
            up_r.raise_for_status()
        except httpx.HTTPError as e:
            q.put(f"FAIL [{i}/{total}] {label}: poster upload failed ({e})")
            failed += 1
            continue

        q.put(f"OK [{i}/{total}] {label}: poster updated{via}")
        updated += 1
        with POSTER_STATE_LOCK:
            poster_state[rating_key] = time.time()
            save_poster_state(poster_state)
        # TMDb's rate limit is roughly 40 req/10s; this loop already makes
        # 2-3 calls per item (metadata, images, sometimes /find), so a
        # small pause keeps it well clear of that without slowing a
        # several-thousand-item library down to a crawl.
        time.sleep(0.25)

    q.put(f"DONE {updated} updated, {skipped} skipped, {failed} failed out of {total}.")


@router.get("/api/posters/libraries")
def posters_libraries(_=Depends(current_user_or_service)):
    """Movie/show libraries only - same live-from-Plex source as
    /api/plex/libraries, filtered to the section types this sync actually
    knows how to handle."""
    try:
        sections = plex_sections()
    except httpx.HTTPError as e:
        fail(f"Could not read Plex libraries: {e}")
    return [{"key": s["key"], "title": s["title"], "type": s["type"]} for s in sections if s.get("type") in ("movie", "show")]


@router.post("/api/posters/sync")
def posters_sync(payload: PosterSyncRequest, _=Depends(current_user_or_service)):
    _require_source_configured(payload.source)
    plex_headers()  # raises 503 if Plex isn't configured

    with POSTER_SYNC_LOCK:
        if POSTER_SYNC_STATE["running"]:
            fail("A poster sync is already running - wait for it to finish.", status_code=409)
        q = queue.Queue()
        POSTER_SYNC_STATE["running"] = True
        POSTER_SYNC_STATE["queue"] = q

    def worker():
        try:
            run_poster_sync(payload.library, payload.dry_run, q, payload.source)
        finally:
            with POSTER_SYNC_LOCK:
                POSTER_SYNC_STATE["running"] = False

    threading.Thread(target=worker, daemon=True).start()
    return ok(f"Poster sync started for '{payload.library}' via {payload.source}{' (dry run)' if payload.dry_run else ''}.")


@router.get("/api/posters/sync/stream")
def posters_sync_stream(_=Depends(current_user_or_service)):
    """SSE progress feed for the currently running (or just-finished)
    poster sync. A single shared queue - if more than one tab has this
    open at once they split the lines between them rather than each
    seeing everything, same tradeoff as this panel's other single-job
    background actions. Fine for a one-operator LAN dashboard."""
    q = POSTER_SYNC_STATE["queue"]
    if q is None:
        fail("No poster sync has been started yet.", status_code=404)

    def generate():
        while True:
            try:
                line = q.get(timeout=1)
            except queue.Empty:
                if not POSTER_SYNC_STATE["running"]:
                    break
                continue
            yield f"data: {line}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------
# Poster review - the manual-pick counterpart to run_poster_sync above.
# Same per-item candidate lookup (resolve_poster_candidates), but streams
# up to 3 ranked candidates per item instead of auto-applying the top
# one, so the panel can render a picker. Candidate #1 in this list is
# always identical to what auto mode (/api/posters/sync) would have
# picked - the frontend's "apply auto for the rest" action just calls
# /api/posters/apply with that first candidate per unreviewed item, no
# separate auto-fallback endpoint needed.
# ---------------------------------------------------------------------
POSTER_REVIEW_LOCK = threading.Lock()
POSTER_REVIEW_STATE = {"running": False, "queue": None}


def run_poster_review(library_title: str, source: str, q: queue.Queue):
    try:
        sections = plex_sections()
    except httpx.HTTPError as e:
        q.put(json.dumps({"type": "error", "message": f"Could not read Plex libraries: {e}"}))
        return
    section = next((s for s in sections if s["title"].lower() == library_title.lower()), None)
    if not section or section.get("type") not in ("movie", "show"):
        q.put(json.dumps({"type": "error", "message": f"No movie/show library found matching '{library_title}'."}))
        return
    media_type = section["type"]

    try:
        r = httpx.get(
            f"{PLEX_URL}/library/sections/{section['key']}/all?X-Plex-Container-Size=100000",
            headers=plex_headers(), timeout=60,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        q.put(json.dumps({"type": "error", "message": f"Could not list '{library_title}': {e}"}))
        return

    items = r.json()["MediaContainer"].get("Metadata", [])
    total = len(items)
    q.put(json.dumps({"type": "start", "total": total, "library": library_title, "source": source}))

    for i, item in enumerate(items, 1):
        rating_key = item["ratingKey"]
        title = item.get("title", "Unknown")
        year = item.get("year")

        try:
            meta_r = httpx.get(f"{PLEX_URL}/library/metadata/{rating_key}", headers=plex_headers(), timeout=15)
            meta_r.raise_for_status()
            meta = meta_r.json()["MediaContainer"]["Metadata"][0]
        except httpx.HTTPError:
            q.put(json.dumps({"type": "item", "i": i, "total": total, "ratingKey": rating_key,
                               "title": title, "year": year, "candidates": []}))
            continue

        used_source, candidates = resolve_poster_candidates(meta, media_type, source, limit=3)

        q.put(json.dumps({"type": "item", "i": i, "total": total, "ratingKey": rating_key,
                           "title": title, "year": year, "candidates": candidates,
                           "source": used_source}))
        # Same rate-limit courtesy as run_poster_sync - this makes the same
        # 1-2 calls per item (metadata, then one art lookup).
        time.sleep(0.25)

    q.put(json.dumps({"type": "done"}))


@router.post("/api/posters/review")
def posters_review(payload: PosterReviewRequest, _=Depends(current_user_or_service)):
    _require_source_configured(payload.source)
    plex_headers()  # raises 503 if Plex isn't configured

    with POSTER_REVIEW_LOCK:
        if POSTER_REVIEW_STATE["running"]:
            fail("A poster review is already running - wait for it to finish.", status_code=409)
        q = queue.Queue()
        POSTER_REVIEW_STATE["running"] = True
        POSTER_REVIEW_STATE["queue"] = q

    def worker():
        try:
            run_poster_review(payload.library, payload.source, q)
        finally:
            with POSTER_REVIEW_LOCK:
                POSTER_REVIEW_STATE["running"] = False

    threading.Thread(target=worker, daemon=True).start()
    return ok(f"Poster review started for '{payload.library}' via {payload.source}.")


@router.get("/api/posters/review/stream")
def posters_review_stream(_=Depends(current_user_or_service)):
    """SSE feed of per-item candidate JSON lines - same single-shared-queue
    tradeoff as /api/posters/sync/stream."""
    q = POSTER_REVIEW_STATE["queue"]
    if q is None:
        fail("No poster review has been started yet.", status_code=404)

    def generate():
        while True:
            try:
                line = q.get(timeout=1)
            except queue.Empty:
                if not POSTER_REVIEW_STATE["running"]:
                    break
                continue
            yield f"data: {line}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/api/posters/apply")
def posters_apply(payload: PosterApplyRequest, _=Depends(current_user_or_service)):
    """Set a single item's poster to an exact URL - what the review
    picker's click handler calls, whether the user picked candidate #2/#3
    or the frontend is auto-filling candidate #1 for an unreviewed item.
    Not gated by the 48h cooldown itself (a deliberate manual pick should
    always go through immediately) but does record the timestamp, same as
    an auto-mode apply - otherwise the next scheduled auto sync could
    immediately overwrite a poster someone just picked by hand."""
    plex_headers()
    try:
        r = httpx.post(
            f"{PLEX_URL}/library/metadata/{payload.rating_key}/posters",
            params={"url": payload.url}, headers=plex_headers(), timeout=30,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Poster upload failed: {e}")
    with POSTER_STATE_LOCK:
        state = load_poster_state()
        state[payload.rating_key] = time.time()
        save_poster_state(state)
    return ok("Poster updated.")
