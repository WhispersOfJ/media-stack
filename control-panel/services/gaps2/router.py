"""GAPS-2 routes - Phase 5 of PLANS.md's 7-service integration batch.

Finds titles that belong to a collection (movies, via TMDB) or a franchise
(TV, via TheTVDB) where the library owns some entries but not others, and
pushes a chosen missing title into the right Arr instance.

Three things about this integration are not what PLANS.md 5 assumed, all
established by reading upstream source rather than its docs:

1. The scan never touches the FUSE mount. It pulls the owned-title list from
   Plex's own API and then does TMDB/TheTVDB metadata lookups. PLANS.md 5's
   headline risk - "a single library-wide filesystem walk over the FUSE mount
   can run tens of minutes" - is about a different shape of operation than
   the one this service actually performs. The real cost is third-party API
   round-trips, which is what the incremental movie scan exists to avoid.

2. GAPS-2 holds ONE Radarr and ONE Sonarr connection, with no second-instance
   support. Coverage is Movies and Shows only (the anime libraries were
   dropped on 2026-08-12, see `libraries.py`), so that single pair is now
   provisioned and points at radarr/sonarr. `/push` still routes through
   `core.arr_client` rather than GAPS-2's own `/api/radarr/add`: it is the
   same destination, but this way the panel names the instance in its
   response, reuses the stack's root-folder/quality-profile defaults, and
   rejects an uncovered library instead of adding it somewhere by default.

3. Because of (2), scans run one library at a time. GAPS-2's gap objects carry
   no library field, so a merged multi-library scan produces results that
   cannot be attributed back and therefore cannot be routed. One library per
   scan makes each completed scan a scan-history entry tagged with exactly
   one library name, and that is where `/missing` and `/push` get attribution
   from. Full reasoning in `libraries.py`.

No auth against GAPS-2 itself - it ships with none (no login blueprint, no
request guard, and `CORS_ORIGINS` is "*" under ProductionConfig). Auth is
this panel's own `current_user_or_service`, same as every other route here.
"""
import threading
import time

import httpx
from core.arr_client import (
    ARR_APPS,
    radarr_add_movie,
    radarr_root_folder_and_profile,
    sonarr_add_series,
    sonarr_root_folder_and_profile,
)
from core.responses import fail, ok
from core.security import current_user_or_service
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .libraries import (
    LIBRARY_NAMES,
    arr_for_library,
    kind_for_library,
)

router = APIRouter(tags=["gaps2"])

SERVICE_META = {"label": "GAPS-2", "health_check": None}

GAPS2_URL = "http://gaps2:4277"

# Per-media-type API halves. Movies go through TMDB collections, TV through
# TheTVDB franchises; the two have separate scan endpoints, separate progress
# trackers and separate id fields, but otherwise identical plumbing.
ENDPOINTS = {
    "movie": {
        "scan": "/api/recommendations/scan",
        "progress": "/api/recommendations/scan/progress",
        "cancel": "/api/recommendations/scan/cancel",
        "preload": "/api/libraries/movies",
        "id_field": "tmdbId",
        "group_field": "collectionName",
    },
    "show": {
        "scan": "/api/tvdb/scan",
        "progress": "/api/tvdb/scan/progress",
        "cancel": "/api/tvdb/scan/cancel",
        "preload": "/api/libraries/shows",
        "id_field": "tvdbId",
        "group_field": "franchiseName",
    },
}

# How long to wait between progress polls during a sweep, and the ceiling on
# any single library's scan. Spaced out per PLANS.md's global rule about not
# tight-polling a service mid-operation; a full first-run movie scan is
# dominated by TMDB round-trips and takes minutes, not seconds.
POLL_SECONDS = 10
SCAN_TIMEOUT_SECONDS = 60 * 45

# One sweep at a time. GAPS-2 has a single global scan slot per media type and
# answers 409 if a second scan starts while one is running, so overlapping
# sweeps would fight each other rather than queue.
SWEEP_LOCK = threading.Lock()
SWEEP_STATE: dict = {"running": False, "library": None, "done": [], "errors": [], "started": None}


def _get(path: str, params: dict | None = None) -> dict:
    try:
        r = httpx.get(f"{GAPS2_URL}{path}", params=params, timeout=120)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"GAPS-2 request failed: {e}")
    return r.json()


def _post(path: str, body: dict | None = None, timeout: int = 60) -> tuple[int, dict]:
    """Returns (status_code, parsed_body) without raising on 4xx.

    GAPS-2 uses 409 for "a scan is already in progress" and 400 for "no TMDB
    key" / "browse the libraries first", and those are conditions the caller
    needs to report rather than a transport failure to retry.
    """
    try:
        r = httpx.post(f"{GAPS2_URL}{path}", json=body or {}, timeout=timeout)
    except httpx.HTTPError as e:
        fail(f"GAPS-2 request failed: {e}")
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


def _history(media_type: str | None = None) -> list[dict]:
    params = {"mediaType": media_type} if media_type else None
    body = _get("/api/scan-history", params)
    return body.get("history") or []


def _latest_entry_for_library(name: str) -> dict | None:
    """The newest scan-history entry whose libraries are exactly [name].

    Exactly, not merely containing: an entry covering several libraries can't
    attribute its gaps to any one of them (gap objects carry no library
    field), so it is useless for routing and must not be mistaken for this
    library's result.
    """
    kind = kind_for_library(name)
    media_type = "tv" if kind == "show" else "movie"
    for entry in _history(media_type):
        if list(entry.get("libraries") or []) == [name]:
            return entry
    return None


def _gaps_for_library(name: str) -> list[dict]:
    """Actionable gaps from this library's most recent single-library scan."""
    entry = _latest_entry_for_library(name)
    if not entry:
        return []
    detail = _get(f"/api/scan-history/{entry['id']}/gaps")
    kind = kind_for_library(name)
    id_field = ENDPOINTS[kind]["id_field"]
    group_field = ENDPOINTS[kind]["group_field"]
    gaps = []
    for gap in detail.get("gaps") or []:
        # `owned` entries appear only when a scan ran with showExisting; they
        # are not missing and must never reach a push.
        if gap.get("owned"):
            continue
        gaps.append({
            "id": gap.get(id_field),
            "id_field": id_field,
            "title": gap.get("name"),
            "year": gap.get("year"),
            "group": gap.get(group_field) or "",
            "library": name,
            "kind": kind,
            "arr": arr_for_library(name),
        })
    return gaps


def _run_sweep(targets: list[str], incremental: bool) -> None:
    """Scan each target library in turn, waiting for each to finish.

    Sequential by necessity, not preference: GAPS-2 keeps one scan slot per
    media type, so starting the next library before the current one finishes
    would just collect a 409.
    """
    for name in targets:
        with SWEEP_LOCK:
            SWEEP_STATE["library"] = name
        kind = kind_for_library(name)
        api = ENDPOINTS[kind]
        try:
            # Movie scans refuse to start unless the owned-title list is
            # already cached ("No movies loaded for the selected libraries"),
            # whereas the TV scan loads it itself. Preloading both keeps this
            # path uniform and is a cache hit on the TV side.
            httpx.get(f"{GAPS2_URL}{api['preload']}", params={"library_name": name}, timeout=300).raise_for_status()

            body = {"libraryNames": [name]}
            if kind == "movie":
                # TheTVDB scan has no incremental mode; only movies do.
                body["incremental"] = incremental
            r = httpx.post(f"{GAPS2_URL}{api['scan']}", json=body, timeout=60)
            if r.status_code != 200:
                raise RuntimeError((r.json() or {}).get("error") or f"scan returned {r.status_code}")

            deadline = time.monotonic() + SCAN_TIMEOUT_SECONDS
            while True:
                time.sleep(POLL_SECONDS)
                progress = httpx.get(f"{GAPS2_URL}{api['progress']}", timeout=30).json()
                state = progress.get("status")
                if state in ("done", "error", "cancelled"):
                    if state == "error":
                        raise RuntimeError(progress.get("error") or "scan reported an error")
                    if state == "cancelled":
                        raise RuntimeError("scan was cancelled")
                    break
                if time.monotonic() > deadline:
                    httpx.post(f"{GAPS2_URL}{api['cancel']}", timeout=30)
                    raise RuntimeError(f"scan exceeded {SCAN_TIMEOUT_SECONDS // 60} minutes and was cancelled")
        except (httpx.HTTPError, RuntimeError, ValueError) as e:
            with SWEEP_LOCK:
                SWEEP_STATE["errors"].append({"library": name, "error": str(e)})
            continue
        with SWEEP_LOCK:
            SWEEP_STATE["done"].append(name)


class ScanRequest(BaseModel):
    libraries: list[str] | None = None
    # Incremental reuses the cached TMDB collection lookups and only resolves
    # newly-added titles, which is the difference between a scan measured in
    # minutes and one measured in tens of minutes. Full scans are opt-in.
    incremental: bool = True


class PushRequest(BaseModel):
    id: int
    library: str
    monitored: bool = True
    search: bool = True


@router.get("/api/gaps2/status")
def gaps2_status(_=Depends(current_user_or_service)):
    """Whether GAPS-2 is configured, what a running sweep is doing, and when
    each library was last scanned."""
    about = _get("/api/about")

    libraries = []
    for name in LIBRARY_NAMES:
        entry = _latest_entry_for_library(name)
        libraries.append({
            "library": name,
            "arr": arr_for_library(name),
            "last_scan": (entry or {}).get("timestamp"),
            "missing": (entry or {}).get("missing"),
            "owned": (entry or {}).get("totalOwned"),
            "scanned": entry is not None,
        })

    with SWEEP_LOCK:
        sweep = dict(SWEEP_STATE)

    never = [lib["library"] for lib in libraries if not lib["scanned"]]
    if sweep["running"]:
        message = f"Sweep running - currently scanning '{sweep['library']}' ({len(sweep['done'])}/{len(LIBRARY_NAMES)} done)."
    elif never:
        message = f"Idle. Never scanned: {', '.join(never)}."
    else:
        total = sum(lib["missing"] or 0 for lib in libraries)
        message = f"Idle. {total} missing title(s) across {len(libraries)} libraries."
    return ok(message, version=about.get("version"), libraries=libraries, sweep=sweep)


@router.post("/api/gaps2/scan")
def gaps2_scan(payload: ScanRequest, _=Depends(current_user_or_service)):
    """Start a background sweep over one or more libraries.

    Returns as soon as the sweep starts rather than blocking: a full movie
    scan is minutes of TMDB round-trips, well past the point PLANS.md's own
    global rule says to poll in the background instead of waiting. Progress
    comes from /api/gaps2/status.
    """
    # Blanks are stripped before the "all libraries" fallback: the CLI sends
    # an optional, omitted argument as [""] (commands.json BodyFields Array),
    # and that must mean "every library", not "a library named empty string".
    targets = [name for name in (payload.libraries or []) if name.strip()] or list(LIBRARY_NAMES)
    unknown = [name for name in targets if kind_for_library(name) is None]
    if unknown:
        fail(f"Unknown library/libraries: {', '.join(unknown)}. Known: {', '.join(LIBRARY_NAMES)}.", status_code=400)

    with SWEEP_LOCK:
        if SWEEP_STATE["running"]:
            fail(f"A sweep is already running (scanning '{SWEEP_STATE['library']}').", status_code=409)
        SWEEP_STATE.update({"running": True, "library": None, "done": [], "errors": [], "started": time.strftime("%H:%M:%S")})

    def worker():
        try:
            _run_sweep(targets, payload.incremental)
        finally:
            with SWEEP_LOCK:
                SWEEP_STATE["running"] = False
                SWEEP_STATE["library"] = None

    threading.Thread(target=worker, daemon=True).start()
    mode = "incremental" if payload.incremental else "full"
    return ok(f"Sweep started ({mode}) over {len(targets)} librar{'y' if len(targets) == 1 else 'ies'}: {', '.join(targets)}.",
              libraries=targets, incremental=payload.incremental)


@router.get("/api/gaps2/missing")
def gaps2_missing(library: str = "", limit: int = 0, _=Depends(current_user_or_service)):
    """Missing titles from the most recent per-library scans, each tagged with
    the Arr instance /push would send it to."""
    if library and kind_for_library(library) is None:
        fail(f"Unknown library '{library}'. Known: {', '.join(LIBRARY_NAMES)}.", status_code=400)
    targets = [library] if library else list(LIBRARY_NAMES)

    gaps, unscanned = [], []
    for name in targets:
        if _latest_entry_for_library(name) is None:
            unscanned.append(name)
            continue
        gaps.extend(_gaps_for_library(name))

    gaps.sort(key=lambda g: (g["library"], g["group"], str(g["year"]), str(g["title"])))
    total = len(gaps)
    if limit and limit > 0:
        gaps = gaps[:limit]

    by_library = {name: sum(1 for g in gaps if g["library"] == name) for name in targets}
    message = f"{total} missing title(s)" + (f" in '{library}'" if library else " across all libraries")
    if unscanned:
        # Never scanned reads identically to zero gaps in a bare count, and
        # the difference matters - one means "nothing missing", the other
        # means "we have not looked".
        message += f". Never scanned: {', '.join(unscanned)} (run stack-gaps2-scan)"
    if limit and total > limit:
        message += f". Showing first {limit}"
    return ok(message + ".", missing=gaps, total=total, by_library=by_library, unscanned=unscanned)


@router.post("/api/gaps2/push")
def gaps2_push(payload: PushRequest, _=Depends(current_user_or_service)):
    """Add one missing title to the Arr instance its library maps to.

    Deliberately one title per call, per PLANS.md 5.4: a gap list can contain
    wrong-year matches and short films, so a bulk push would be exactly the
    kind of unreviewed mass action this repo's CLAUDE.md asks to confirm first.

    This does NOT go through GAPS-2's own /api/radarr/add, even though that
    now points at the same Radarr/Sonarr. Deciding the destination here from
    the library the gap was found in is what lets this route name the
    instance back to the caller, reuse the stack-wide root folder and quality
    profile defaults from core.arr_client, and refuse a library the routing
    table does not cover instead of adding it somewhere by default.
    """
    arr_name = arr_for_library(payload.library)
    if not arr_name:
        fail(f"Unknown library '{payload.library}'. Known: {', '.join(LIBRARY_NAMES)}.", status_code=400)
    kind = kind_for_library(payload.library)
    cfg = ARR_APPS[arr_name]

    known = {g["id"] for g in _gaps_for_library(payload.library)}
    if not known:
        fail(f"'{payload.library}' has no recorded gaps - run a scan first (stack-gaps2-scan).", status_code=409)
    if payload.id not in known:
        # Guards against pushing an id that was never reported missing for
        # this library - a typo, or an id copied from a different library's
        # list, would otherwise silently add an unrelated title.
        fail(f"{ENDPOINTS[kind]['id_field']} {payload.id} is not in '{payload.library}'s missing list.", status_code=400)

    if kind == "movie":
        root_folder_path, quality_profile_id = radarr_root_folder_and_profile(cfg, None, None)
        result = radarr_add_movie(cfg, payload.id, payload.monitored, payload.search,
                                  root_folder_path, quality_profile_id, existing_tmdb_ids=set())
    else:
        root_folder_path, quality_profile_id = sonarr_root_folder_and_profile(cfg, None, None)
        result = sonarr_add_series(cfg, payload.id, payload.monitored, payload.search,
                                   root_folder_path, quality_profile_id, existing_tvdb_ids=set())

    if result["status"] == "failed":
        fail(f"{cfg['label']} rejected the add: {result.get('reason')}")
    title = result.get("title") or payload.id
    return ok(f"Added '{title}' to {cfg['label']} ({root_folder_path}).",
              arr=arr_name, arr_label=cfg["label"], library=payload.library,
              title=title, root_folder=root_folder_path,
              quality_profile_id=quality_profile_id, push_status=result["status"])
