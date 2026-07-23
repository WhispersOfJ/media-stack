"""
Control Panel - the single dashboard for The Stack: live container status
and start/stop/restart control plus one-click operational actions.
Supersedes the old Homepage+Control Panel split - see README.md's Control
Panel section.

Talks to the Docker socket (start/stop/restart/exec/stats) and each app's
own HTTP API (Plex, Radarr, Sonarr, NzbDAV, etc.). No auth - LAN-only,
matches every other service in this stack (see README.md's "Security"
section).
"""
import concurrent.futures
import json
import os
import queue
import re
import socket
import sqlite3
import subprocess
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse

import docker
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PLEX_URL = (os.environ.get("PLEX_URL") or "").rstrip("/")
PLEX_TOKEN = os.environ.get("PLEX_TOKEN")
# NzbDAV removed entirely 2026-07-23 (unmerged connection-leak bug,
# nzbdav-dev/nzbdav#478 - see CLAUDE.md's History). AltMount's own
# SABnzbd-compatible API lives under /sabnzbd (Fiber's prefix-matching
# app.Use, not a literal /api/sabnzbd path).
ALTMOUNT_URL = "http://altmount:8080/sabnzbd"
ALTMOUNT_API_KEY = os.environ.get("ALTMOUNT_API_KEY")
HOST_IP = os.environ.get("HOST_IP")
PROWLARR_API_KEY = os.environ.get("PROWLARR_API_KEY")
TAUTULLI_URL = "http://tautulli:8181"
BAZARR_URL = "http://bazarr:6767"
SEERR_URL = "http://seerr:5055"
TMDB_KEY = os.environ.get("TMDB_KEY")
TMDB_URL = "https://api.themoviedb.org/3"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")


def _tautulli_key() -> str | None:
    """Tautulli generates its own API key on first boot and stores it in
    config.ini - never an env var in this stack (see .env.example), so
    this reads it live off the mounted config each call rather than
    caching one at import time that'd go stale after a key regeneration."""
    path = os.path.join(HOST_CONFIG_DIR, "tautulli", "config.ini")
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        for line in f:
            if line.strip().startswith("api_key"):
                return line.split("=", 1)[1].strip()
    return None


def _bazarr_key() -> str | None:
    """Bazarr generates its own API key on first boot into
    config/config.yaml's auth.apikey - never an env var, same story as
    Tautulli/Seerr above."""
    path = os.path.join(HOST_CONFIG_DIR, "bazarr", "config", "config.yaml")
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        for line in f:
            if line.strip().startswith("apikey"):
                return line.split(":", 1)[1].strip()
    return None


def _seerr_key() -> str | None:
    """Same story as Tautulli - Seerr generates its own key on first setup
    and only stores it in settings.json, never in .env."""
    import json as _json
    path = os.path.join(HOST_CONFIG_DIR, "seerr", "settings.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return _json.load(f).get("main", {}).get("apiKey")
    except (ValueError, OSError):
        return None


def _omdb_key() -> str | None:
    # Used to live-read off Kometa's config.yml (both keys were entered
    # once for Kometa's own metadata lookups) - Kometa was removed entirely
    # (no Jellyfin support, see CLAUDE.md's migration History), so these are
    # now real standalone .env secrets instead of an orphaned read off a
    # deleted file.
    return os.environ.get("OMDB_KEY") or None


def _mdblist_key() -> str | None:
    return os.environ.get("MDBLIST_KEY") or None
# Read-only host mounts added specifically for the stack-* diagnostic
# endpoints below (resource-check through neutarr-hunt) - see
# docker-compose.yml's control-panel volumes for what backs each of these.
HOST_CONFIG_DIR = "/host-config"
HOST_MNT_DIR = "/mnt"
HOST_BACKUP_LOCAL = "/host-backups/stack-restic-repo"
HOST_BACKUP_OFFSITE = "/host-backup-offsite"
HOST_RESTIC_PASSWORD_FILE = "/host-backups/.restic-password"
HOST_README = "/host-README.md"

# Internal stacknet hostnames - not HOST_IP, since this container reaches
# every *arr app over the docker network directly.
ARR_APPS = {
    "radarr": {
        "url": "http://radarr:7878",
        "api": "v3",
        "key": os.environ["RADARR_API_KEY"],
        "search_command": "MissingMoviesSearch",
        "label": "Radarr",
        "import_events": ("downloadFolderImported",),
    },
    "sonarr": {
        "url": "http://sonarr:8989",
        "api": "v3",
        "key": os.environ["SONARR_API_KEY"],
        "search_command": "MissingEpisodeSearch",
        "label": "Sonarr",
        "import_events": ("downloadFolderImported",),
    },
    # Readarr itself was replaced by Bindery in v10.7.0 (upstream Readarr's
    # sole metadata source died permanently, see docker-compose.yml's
    # comment on the bindery service) - no entry here since Bindery's API
    # is a clean-room design, not Servarr-shaped, so none of this generic
    # arr_queue/arr_command/history-rate-calc machinery applies to it.
}

# These four have a real download queue (NzbDAV wired to each as of the
# debrid/torrent removal) - Unstick/manual-import work identically on all
# of them, same reasoning 7.0.0 used when this was just Radarr/Sonarr.
# Bindery (Readarr's v10.7.0 replacement) isn't listed - its API is a
# clean-room design, not Servarr-shaped, so this generic queue machinery
# doesn't apply.
QUEUE_ARR_APPS = ("radarr", "sonarr")

# Display-only labels/notes for the container grid - NOT an allow-list.
# Which containers actually exist, and which actions are valid on them, is
# always determined live from Docker (see project_containers() below), so
# this dict going stale (a service added to docker-compose.yml but not
# listed here) only means a slightly plainer name in the UI, never a broken
# or missing control - the exact staleness failure mode the old hardcoded
# RESTARTABLE_CONTAINERS allow-list had (it silently excluded any service
# added to compose after it was written).
CONTAINER_LABELS = {
    "radarr": ("Radarr", None),
    "sonarr": ("Sonarr", None),
    "prowlarr": ("Prowlarr", None),
    "plex": ("Plex", None),
    "altmount": ("AltMount", "Usenet, WebDAV + SABnzbd-compatible API"),
    "seerr": ("Seerr", None),
    "tautulli": ("Tautulli", None),
    "bazarr": ("Bazarr", "subtitle management - watches Radarr/Sonarr for missing subs"),
    "kometa": ("Kometa", None),
    "kometa-quickstart": ("Kometa Quickstart", "config.yml wizard, port 7171 - not an alternate Kometa runtime"),
    "unpackerr": ("Unpackerr", None),
    "watchtower": ("Watchtower", None),
    "cleanuparr": ("Cleanuparr", "queue cleanup: strikes, malware block, stalled/failed removal"),
    "neutarr": ("NeutArr", "hardened Huntarr-lineage fork - missing/upgrade hunting"),
    "control-panel": ("Control Panel", "this dashboard"),
}

# Live per-app outbound API hit counter - dashboard flourish, not a metrics
# system (resets on container restart, in-memory only). Wraps httpx.request
# itself rather than touching every one of this file's ~25 call sites:
# httpx.get/post/put/delete/patch all funnel through a call to request()
# internally (confirmed against the pinned 0.28.1). That call resolves
# against httpx._api's own module globals, not httpx's top-level namespace -
# reassigning httpx.request alone is a no-op for get/post/etc, silently
# uncounted (caught live: hit counts stayed at 0 through real traffic).
# Patching httpx._api.request directly is what get/post/put/delete/patch
# actually call; httpx.request is reassigned too so anything calling it
# directly, or a fresh `from httpx import request`, stays consistent.
_API_HOST_LABELS = {urlparse(cfg["url"]).hostname: cfg["label"] for cfg in ARR_APPS.values()}
_API_HOST_LABELS.update({
    urlparse(PLEX_URL).hostname: "Plex",
    urlparse(ALTMOUNT_URL).hostname: "AltMount",
})
# Seeded at 0 for every known app, not left empty until each app's first
# real hit - otherwise most badges wouldn't appear at all on a fresh
# restart until something happened to call that specific app (some, like
# the arr apps, only get called on a manual RSS-sync/search/unstick click),
# which defeats a dashboard element whose whole point is being visible.
API_HIT_COUNTS = Counter({label: 0 for label in _API_HOST_LABELS.values()})
_httpx_request = httpx.request


def _counted_request(method, url, *args, **kwargs):
    host = urlparse(str(url)).hostname
    API_HIT_COUNTS[_API_HOST_LABELS.get(host, host or "unknown")] += 1
    return _httpx_request(method, url, *args, **kwargs)


httpx.request = _counted_request
httpx._api.request = _counted_request

app = FastAPI(title="Control Panel")
docker_client = docker.from_env()

# CSRF hardening, not auth: this panel is deliberately no-login/LAN-only (see
# README's Security note), but its POST endpoints hold full docker.sock
# restart/exec power with zero Origin check, so any external site a LAN
# browser visits could otherwise fire a same-origin-exempt POST at it. This
# blocks cross-origin/cross-host POSTs without adding any credential.
ALLOWED_HOSTS = {h for h in (HOST_IP, "localhost", "127.0.0.1") if h}


@app.middleware("http")
async def verify_same_origin(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        host = (request.headers.get("host") or "").split(":")[0]
        if host not in ALLOWED_HOSTS:
            return JSONResponse(
                status_code=403,
                content={"ok": False, "message": "Rejected: Host header did not match this panel's configured HOST_IP."},
            )
        origin = request.headers.get("origin")
        if origin:
            origin_host = origin.split("://", 1)[-1].split(":")[0].split("/")[0]
            if origin_host not in ALLOWED_HOSTS:
                return JSONResponse(
                    status_code=403,
                    content={"ok": False, "message": "Rejected: Origin did not match this panel's host."},
                )
    return await call_next(request)


class KometaRunRequest(BaseModel):
    libraries: list[str] | None = None


class PosterSyncRequest(BaseModel):
    library: str
    dry_run: bool = False


class LetterboxdAddRequest(BaseModel):
    url: str
    monitored: bool = True
    search: bool = True
    root_folder: str | None = None
    quality_profile: str | None = None
    dry_run: bool = False


class LetterboxdListAddRequest(BaseModel):
    url: str
    monitored: bool = True
    search: bool = True
    root_folder: str | None = None
    quality_profile: str | None = None
    limit: int | None = None
    dry_run: bool = False


class ImportListAddRequest(BaseModel):
    implementation: str
    name: str
    fields: dict = {}
    search_on_add: bool = True
    monitor: str | None = None
    minimum_availability: str = "released"


class MDBListImportRequest(BaseModel):
    list_url: str
    monitored: bool = True
    search: bool = True
    limit: int | None = None
    radarr_root_folder: str | None = None
    radarr_quality_profile: str | None = None
    sonarr_root_folder: str | None = None
    sonarr_quality_profile: str | None = None
    dry_run: bool = False


class ManualImportFile(BaseModel):
    # Mirrors the shape returned by GET .../manualimport - the client just
    # echoes back the candidate it was given, same as the arr apps' own web
    # UI does when you confirm a manual import.
    path: str
    folderName: str | None = None
    quality: dict
    languages: list[dict]
    releaseGroup: str | None = None
    downloadId: str | None = None
    movieId: int | None = None
    seriesId: int | None = None
    episodeIds: list[int] | None = None
    artistId: int | None = None
    albumId: int | None = None
    trackIds: list[int] | None = None
    authorId: int | None = None
    bookId: int | None = None


def own_container():
    # Docker sets the container's hostname to its own short ID by default -
    # lets this container find itself in the compose project without a
    # hardcoded name.
    return docker_client.containers.get(socket.gethostname())


def project_containers():
    """Every container in this compose project, live from Docker - the same
    label-based discovery stack_restart_all() already used, pulled out so
    the container grid, start/stop/restart validation, and the whole-stack
    restart all share one source of truth instead of three separate lists
    that can individually drift out of sync with docker-compose.yml (the
    exact failure mode CONTAINER_LABELS going stale is harmless for, but an
    allow-list going stale silently breaks)."""
    try:
        me = own_container()
    except docker.errors.NotFound:
        fail("Could not find this container's own record - can't determine the compose project.")
    project = me.labels.get("com.docker.compose.project")
    if not project:
        fail("This container has no compose project label - can't tell what 'the stack' is.")
    containers = docker_client.containers.list(all=True, filters={"label": f"com.docker.compose.project={project}"})
    return me, containers


def container_stats(c) -> dict:
    """CPU%/memory for a running container, computed the same way `docker
    stats` does - a single stats() call already contains both the current
    and previous sample (cpu_stats/precpu_stats), so no extra polling
    delay is needed for one data point."""
    if c.status != "running":
        return {"cpu_percent": None, "mem_used_mb": None, "mem_limit_mb": None, "mem_percent": None}
    try:
        s = c.stats(stream=False)
        cpu = s.get("cpu_stats", {})
        precpu = s.get("precpu_stats", {})
        cpu_total = cpu.get("cpu_usage", {}).get("total_usage")
        precpu_total = precpu.get("cpu_usage", {}).get("total_usage")
        system = cpu.get("system_cpu_usage")
        presystem = precpu.get("system_cpu_usage")
        online_cpus = cpu.get("online_cpus") or len(cpu.get("cpu_usage", {}).get("percpu_usage") or [1]) or 1
        cpu_percent = None
        if None not in (cpu_total, precpu_total, system, presystem):
            cpu_delta = cpu_total - precpu_total
            system_delta = system - presystem
            if system_delta > 0 and cpu_delta >= 0:
                cpu_percent = round((cpu_delta / system_delta) * online_cpus * 100, 1)
        mem = s.get("memory_stats", {})
        mem_used = mem.get("usage")
        # Docker's raw "usage" includes page cache; subtracting inactive_file
        # (cgroup v1/v2 key differs) is what `docker stats` itself does to
        # show the same number a user would recognize from that command.
        mem_stats = mem.get("stats", {})
        cache = mem_stats.get("inactive_file", mem_stats.get("total_inactive_file", 0)) or 0
        if mem_used is not None:
            mem_used = max(mem_used - cache, 0)
        mem_limit = mem.get("limit")
        mem_used_mb = round(mem_used / 1024 / 1024, 1) if mem_used is not None else None
        mem_limit_mb = round(mem_limit / 1024 / 1024, 1) if mem_limit else None
        mem_percent = round((mem_used / mem_limit) * 100, 1) if mem_used and mem_limit else None
        return {"cpu_percent": cpu_percent, "mem_used_mb": mem_used_mb, "mem_limit_mb": mem_limit_mb, "mem_percent": mem_percent}
    except Exception:
        # Stats are a nice-to-have on the grid, not something a transient
        # per-container failure should turn into a 502 for the whole grid.
        return {"cpu_percent": None, "mem_used_mb": None, "mem_limit_mb": None, "mem_percent": None}


def now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S")


def ok(message: str, **extra):
    return {"ok": True, "message": message, "time": now(), **extra}


def fail(message: str, status_code: int = 502):
    raise HTTPException(status_code=status_code, detail={"ok": False, "message": message, "time": now()})


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/status")
def status():
    """Live running/health state for every container in the compose
    project, used to light up the status lamps on page load without a
    manual refresh. Discovered live rather than from a fixed list, so a
    newly added service shows up with no code change."""
    _, containers = project_containers()
    out = {}
    for c in containers:
        health = c.attrs.get("State", {}).get("Health", {}).get("Status")
        out[c.name] = {"state": c.status, "health": health}
    return out


def _container_row(me, c) -> dict:
    label, note = CONTAINER_LABELS.get(c.name, (c.name, None))
    health = c.attrs.get("State", {}).get("Health", {}).get("Status")
    image_tags = c.image.tags
    image = image_tags[0] if image_tags else (c.image.short_id or "")
    service = c.labels.get("com.docker.compose.service", c.name)
    return {
        "name": c.name,
        "label": label,
        "note": note,
        "service": service,
        "image": image,
        "state": c.status,
        "health": health,
        "is_self": c.id == me.id,
        **container_stats(c),
    }


@app.get("/api/containers")
def containers_list():
    """Full container grid data - state, health, image, and live CPU/memory
    for every container in this compose project, discovered live from
    Docker rather than a hardcoded list.

    Fetched concurrently, not in a sequential loop: each container_stats()
    call blocks on a real `stats(stream=False)` round-trip to the Docker
    daemon, which - despite the single-call/no-extra-polling design - still
    takes the daemon roughly 1-2s per container to return (it internally
    waits between two samples before responding, regardless of the
    stream=False flag). Caught live: a sequential loop over 34 containers
    made this endpoint take 67s, effectively breaking the 15s auto-refresh
    entirely - the next poll would already be piling up before the previous
    one returned. A thread pool brings total latency down to roughly the
    slowest single container's stats() call instead of the sum of all of
    them, since docker-py's stats() is a blocking call with no async form."""
    me, containers = project_containers()
    ordered = sorted(containers, key=lambda c: c.name)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(ordered), 16) or 1) as pool:
        return list(pool.map(lambda c: _container_row(me, c), ordered))


@app.get("/api/api-hit-counts")
def api_hit_counts():
    """Live count of every outbound API call this panel has made per app
    since it started - see the API_HIT_COUNTS module comment above. Visual
    flourish for the dashboard, not a metrics system: in-memory only, resets
    on restart."""
    return {"counts": dict(API_HIT_COUNTS), "total": sum(API_HIT_COUNTS.values())}


# ---------------------------------------------------------------------
# Kometa
# ---------------------------------------------------------------------
@app.post("/api/kometa/run")
def kometa_run(payload: KometaRunRequest = KometaRunRequest()):
    try:
        c = docker_client.containers.get("kometa")
    except docker.errors.NotFound:
        fail("Kometa container not found.")
    if c.status != "running":
        fail(f"Kometa container is {c.status}, not running.")
    cmd = ["python3", "/kometa.py", "--run"]
    scope = "every library"
    if payload.libraries:
        # Kometa's own --run-libraries takes a pipe-separated list, not comma
        # (confirmed live: a comma-joined multi-library value fails the whole
        # run with "Config Error: No libraries were found in config" - a
        # single-library run never hit this since there's no delimiter to
        # get wrong). Was silently broken for any multi-library scoped run
        # since this endpoint was written.
        cmd += ["--run-libraries", "|".join(payload.libraries)]
        scope = ", ".join(payload.libraries)
    try:
        # detach=True: fire the run and return immediately rather than
        # blocking the request for however long a full Kometa pass takes.
        c.exec_run(cmd=cmd, detach=True)
    except Exception as e:
        fail(f"Failed to start Kometa run: {e}")
    return ok(f"Kometa run started ({scope}) - watch its live CPU on the Containers grid below for progress.")


# ---------------------------------------------------------------------
# Plex
# ---------------------------------------------------------------------
def plex_headers():
    if not PLEX_URL or not PLEX_TOKEN:
        fail("Plex isn't configured (PLEX_URL/PLEX_TOKEN not set)", status_code=503)
    return {"Accept": "application/json", "X-Plex-Token": PLEX_TOKEN}


@app.post("/api/plex/scan")
def plex_scan():
    try:
        r = httpx.get(f"{PLEX_URL}/library/sections/all/refresh", headers=plex_headers(), timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Plex scan failed: {e}")
    return ok("Scan for new files started across every library.")


def plex_sections() -> list[dict]:
    r = httpx.get(f"{PLEX_URL}/library/sections", headers=plex_headers(), timeout=15)
    r.raise_for_status()
    return r.json()["MediaContainer"].get("Directory", [])


@app.get("/api/plex/libraries")
def plex_libraries():
    """Library names as Plex itself knows them - Kometa's --run-libraries
    flag needs an exact, case-sensitive match, so this is read live from
    Plex rather than hardcoded against config/kometa/config.yml."""
    try:
        sections = plex_sections()
    except httpx.HTTPError as e:
        fail(f"Could not read Plex libraries: {e}")
    return [{"key": s["key"], "title": s["title"]} for s in sections]


@app.post("/api/plex/empty-trash")
def plex_empty_trash(library: str | None = None):
    """Empties trash on every library, or just one if `library` (matched
    case-insensitively against its title) is given - the scoped form is
    what actually cleared the stale Movies/TV Shows entries after this
    session's content-routing fix, without touching every other library
    along with them. A plain scan only adds new files; it never prunes
    entries whose file disappeared, which is what this actually does."""
    try:
        sections = plex_sections()
        targets = sections if library is None else [s for s in sections if s["title"].lower() == library.lower()]
        if not targets:
            fail(f"No library found matching '{library}'.")
        for s in targets:
            r = httpx.put(
                f"{PLEX_URL}/library/sections/{s['key']}/emptyTrash",
                headers=plex_headers(),
                timeout=30,
            )
            r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Empty trash failed: {e}")
    return ok(f"Trash emptied on: {', '.join(s['title'] for s in targets)}.")


@app.post("/api/plex/analyze")
def plex_analyze(library: str | None = None):
    """Queues Plex's per-item deep analysis (loudness, chapter thumbnails,
    intro/credits/ad markers, voice activity) for one library, or every
    library if none given - `PUT /library/sections/{key}/analyze`, confirmed
    live (200) against this server. Scoped to a section, unlike the
    whole-server `deep-media-analysis` Butler task below
    (`/api/plex/butler/deep-media-analysis`); use this one to target just
    the library whose per-library analysis settings you changed, without
    re-running analysis server-wide."""
    try:
        sections = plex_sections()
        targets = sections if library is None else [s for s in sections if s["title"].lower() == library.lower()]
        if not targets:
            fail(f"No library found matching '{library}'.")
        for s in targets:
            r = httpx.put(
                f"{PLEX_URL}/library/sections/{s['key']}/analyze",
                headers=plex_headers(),
                timeout=30,
            )
            r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Analyze failed: {e}")
    return ok(f"Deep analysis queued for: {', '.join(s['title'] for s in targets)}.")


@app.post("/api/plex/optimize-db")
def plex_optimize_db():
    try:
        r = httpx.post(f"{PLEX_URL}/butler/OptimizeDatabase", headers=plex_headers(), timeout=30)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Database optimize failed: {e}")
    return ok("Database optimization started.")


@app.post("/api/plex/clean-bundles")
def plex_clean_bundles():
    try:
        r = httpx.post(f"{PLEX_URL}/butler/CleanOldBundles", headers=plex_headers(), timeout=30)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Clean bundles failed: {e}")
    return ok("Cleanup of old bundles started.")


# Every other Butler task Plex's own /butler endpoint currently advertises
# (confirmed live, not guessed - GET /butler?X-Plex-Token=... on this
# server). OptimizeDatabase/CleanOldBundles already have dedicated routes
# above and are left out of this dict to avoid a duplicate path for the
# same task. AutomaticUpdates is Plex's app-update checker, unrelated to
# library media - included anyway since the user's own request was "all"
# of them, not a curated subset.
PLEX_BUTLER_TASKS = {
    "automatic-updates": "AutomaticUpdates",
    "backup-database": "BackupDatabase",
    "clean-log-files": "ButlerTaskCleanSupplementalLogFiles",
    "generate-ad-markers": "ButlerTaskGenerateAdMarkers",
    "generate-credits-markers": "ButlerTaskGenerateCreditsMarkers",
    "generate-intro-markers": "ButlerTaskGenerateIntroMarkers",
    "generate-voice-activity": "ButlerTaskGenerateVoiceActivity",
    "clean-cache-files": "CleanOldCacheFiles",
    "deep-media-analysis": "DeepMediaAnalysis",
    "garbage-collect-blobs": "GarbageCollectBlobs",
    "garbage-collect-media": "GarbageCollectLibraryMedia",
    "generate-chapter-thumbs": "GenerateChapterThumbs",
    "generate-media-index": "GenerateMediaIndexFiles",
    "loudness-analysis": "LoudnessAnalysis",
    "music-analysis": "MusicAnalysis",
    "process-assets": "ProcessAssets",
    "refresh-epg": "RefreshEpgGuides",
    "refresh-libraries": "RefreshLibraries",
    "refresh-local-media": "RefreshLocalMedia",
    "upgrade-media-analysis": "UpgradeMediaAnalysis",
}


@app.post("/api/plex/butler/{task}")
def plex_butler_task(task: str):
    """Fires one named Butler task on demand, the same mechanism behind
    the dedicated optimize-db/clean-bundles routes above - `task` is this
    stack's own kebab-case alias (see PLEX_BUTLER_TASKS), not Plex's raw
    CamelCase task name, so the CLI/URL stays consistent with every other
    /api/plex/* route. `deep-media-analysis` is the one that actually runs
    full deep analysis (loudness, chapter thumbs, intro/credits/ad markers,
    voice activity) across the whole server in one pass - the per-library
    `PUT /library/sections/{key}/analyze` call is a narrower, section-scoped
    alternative to this, not the same thing."""
    plex_task = PLEX_BUTLER_TASKS.get(task)
    if plex_task is None:
        fail(f"Unknown Butler task '{task}'. Known: {', '.join(sorted(PLEX_BUTLER_TASKS))}")
    try:
        r = httpx.post(f"{PLEX_URL}/butler/{plex_task}", headers=plex_headers(), timeout=30)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Butler task '{task}' failed: {e}")
    return ok(f"Butler task started: {task}.")


@app.get("/api/plex/updates")
def plex_updates():
    """Checks Plex's own update-checker rather than trying to compare
    version strings against anything external - `/identity` gives the
    running version, `/updater/status` is Plex's own undocumented-but-real
    endpoint for whether it's found something newer on its current channel.
    This container is pinned deliberately (see README's Image pinning
    policy / Plex section) - this is a check, never an auto-apply action."""
    try:
        r = httpx.get(f"{PLEX_URL}/identity", headers=plex_headers(), timeout=10)
        r.raise_for_status()
        running_version = r.json().get("MediaContainer", {}).get("version")
    except httpx.HTTPError as e:
        fail(f"Could not read Plex's running version: {e}")
    available = []
    try:
        r = httpx.get(f"{PLEX_URL}/updater/status", headers=plex_headers(), timeout=10)
        r.raise_for_status()
        for u in r.json().get("MediaContainer", {}).get("Release", []):
            available.append({"version": u.get("version"), "added_at": u.get("added")})
    except httpx.HTTPError:
        # Not fatal - the official image's updater channel can be
        # unreachable/disabled in a container without breaking anything
        # else; the running version above is still real and useful on its
        # own.
        pass
    return {"running_version": running_version, "update_available": bool(available), "releases": available}

# ---------------------------------------------------------------------
# Poster sync - replaces a movie/show's Plex poster with the top-voted
# TMDb poster, matched via the tmdb:// (or tvdb:///imdb:// as fallback)
# Guid Plex's new agent already carries per item. TMDb only, not
# ThePosterDB - TPDb's own Terms of Service (https://theposterdb.com/terms)
# explicitly forbids automated scraping and it has no public API, so there
# is no ToS-compliant way to pull posters from it programmatically. TMDb
# is a real, documented, keyed API (the same TMDB_KEY Kometa already uses).
#
# One job at a time, in-memory only (no persistence across a panel
# restart) - progress streams over SSE to whichever browser tab has the
# stream open, same technique as /api/container/{name}/logs/stream.
# ---------------------------------------------------------------------
POSTER_SYNC_LOCK = threading.Lock()
POSTER_SYNC_STATE = {"running": False, "queue": None}


def tmdb_get(path: str, **params) -> dict:
    if not TMDB_KEY:
        fail("TMDb isn't configured (TMDB_KEY not set)", status_code=503)
    r = httpx.get(f"{TMDB_URL}{path}", params={"api_key": TMDB_KEY, **params}, timeout=15)
    r.raise_for_status()
    return r.json()


def tmdb_id_for_item(meta: dict, media_type: str) -> int | None:
    """media_type is Plex's own section type ("movie"/"show") for the item
    this Guid list came from. Prefers a direct tmdb:// Guid (present on
    both movies and shows under Plex's new agent, confirmed live against
    this library) and only falls back to TMDb's /find endpoint (external
    ID lookup, not scraping) for items still on an older match."""
    guids = {}
    for g in meta.get("Guid", []):
        gid = g.get("id", "")
        if "://" in gid:
            source, value = gid.split("://", 1)
            guids[source] = value

    if "tmdb" in guids:
        try:
            return int(guids["tmdb"])
        except ValueError:
            pass

    kind = "movie" if media_type == "movie" else "tv"
    if "tvdb" in guids and media_type == "show":
        try:
            found = tmdb_get(f"/find/{guids['tvdb']}", external_source="tvdb_id")
            results = found.get("tv_results") or []
            if results:
                return results[0]["id"]
        except httpx.HTTPError:
            pass
    if "imdb" in guids:
        try:
            found = tmdb_get(f"/find/{guids['imdb']}", external_source="imdb_id")
            results = found.get(f"{kind}_results") or []
            if results:
                return results[0]["id"]
        except httpx.HTTPError:
            pass
    return None


def tmdb_best_poster_url(tmdb_id: int, media_type: str) -> str | None:
    kind = "movie" if media_type == "movie" else "tv"
    try:
        data = tmdb_get(f"/{kind}/{tmdb_id}/images", include_image_language="en,null")
    except httpx.HTTPError:
        return None
    posters = data.get("posters") or []
    if not posters:
        return None
    best = max(posters, key=lambda p: (p.get("vote_average") or 0, p.get("vote_count") or 0))
    return f"https://image.tmdb.org/t/p/original{best['file_path']}"


def run_poster_sync(library_title: str, dry_run: bool, q: queue.Queue):
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

    updated = skipped = failed = 0
    for i, item in enumerate(items, 1):
        rating_key = item["ratingKey"]
        title = item.get("title", "Unknown")
        year = item.get("year", "")
        label = f"{title} ({year})" if year else title

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

        tmdb_id = tmdb_id_for_item(meta, media_type)
        if tmdb_id is None:
            q.put(f"SKIP [{i}/{total}] {label}: no TMDb match")
            skipped += 1
            continue

        poster_url = tmdb_best_poster_url(tmdb_id, media_type)
        if not poster_url:
            q.put(f"SKIP [{i}/{total}] {label}: TMDb has no poster for it")
            skipped += 1
            continue

        if dry_run:
            q.put(f"OK [{i}/{total}] {label}: would set poster ({poster_url})")
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

        q.put(f"OK [{i}/{total}] {label}: poster updated")
        updated += 1
        # TMDb's rate limit is roughly 40 req/10s; this loop already makes
        # 2-3 calls per item (metadata, images, sometimes /find), so a
        # small pause keeps it well clear of that without slowing a
        # several-thousand-item library down to a crawl.
        time.sleep(0.25)

    q.put(f"DONE {updated} updated, {skipped} skipped, {failed} failed out of {total}.")


@app.get("/api/posters/libraries")
def posters_libraries():
    """Movie/show libraries only - same live-from-Plex source as
    /api/plex/libraries, filtered to the section types this sync actually
    knows how to handle."""
    try:
        sections = plex_sections()
    except httpx.HTTPError as e:
        fail(f"Could not read Plex libraries: {e}")
    return [{"key": s["key"], "title": s["title"], "type": s["type"]} for s in sections if s.get("type") in ("movie", "show")]


@app.post("/api/posters/sync")
def posters_sync(payload: PosterSyncRequest):
    if not TMDB_KEY:
        fail("TMDb isn't configured (TMDB_KEY not set in .env).", status_code=503)
    plex_headers()  # raises 503 if Plex isn't configured

    with POSTER_SYNC_LOCK:
        if POSTER_SYNC_STATE["running"]:
            fail("A poster sync is already running - wait for it to finish.", status_code=409)
        q = queue.Queue()
        POSTER_SYNC_STATE["running"] = True
        POSTER_SYNC_STATE["queue"] = q

    def worker():
        try:
            run_poster_sync(payload.library, payload.dry_run, q)
        finally:
            with POSTER_SYNC_LOCK:
                POSTER_SYNC_STATE["running"] = False

    threading.Thread(target=worker, daemon=True).start()
    return ok(f"Poster sync started for '{payload.library}'{' (dry run)' if payload.dry_run else ''}.")


@app.get("/api/posters/sync/stream")
def posters_sync_stream():
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
# AltMount - Usenet streaming layer (WebDAV + its own internal rclone/FUSE
# mount, no local disk). Replaced NzbDAV entirely 2026-07-23 (unmerged
# connection-leak bug, nzbdav-dev/nzbdav#478 - see CLAUDE.md's History).
# Queue/history go through its SABnzbd-compatible API (mode=queue/history,
# keyed by ALTMOUNT_API_KEY, issued at registration via /api/auth/register).
# NzbDAV's own set-connections/unstick routes were both workarounds for its
# specific connection-leak/history-hang bugs and don't apply here - dropped
# outright rather than ported.
# ---------------------------------------------------------------------
def altmount_api(mode: str, timeout: int = 15, **params) -> dict:
    if not ALTMOUNT_API_KEY:
        fail("AltMount isn't configured (ALTMOUNT_API_KEY not set)", status_code=503)
    try:
        r = httpx.get(
            ALTMOUNT_URL,
            params={"mode": mode, "output": "json", "apikey": ALTMOUNT_API_KEY, **params},
            timeout=timeout,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"AltMount {mode} lookup failed: {e}")
    return r.json()


@app.get("/api/altmount/queue")
def altmount_queue():
    slots = altmount_api("queue").get("queue", {}).get("slots", [])
    return [{
        "name": s.get("filename"),
        "category": s.get("cat"),
        "status": s.get("status"),
        "percentage": s.get("percentage"),
        "size_mb": s.get("mb"),
        "size_left_mb": s.get("mbleft"),
    } for s in slots]


@app.get("/api/altmount/history")
def altmount_history(limit: int = 20):
    slots = altmount_api("history", limit=limit).get("history", {}).get("slots", [])
    return [{
        "name": s.get("name"),
        "category": s.get("category"),
        "status": s.get("status"),
        "size": human_size(s.get("bytes")),
        "fail_message": s.get("fail_message") or None,
        "path": s.get("storage"),
    } for s in slots]


# ---------------------------------------------------------------------
# Ratings lookups - OMDb (IMDb) and MDBList. Both keys used to live in
# Kometa's own config.yml (entered once for Kometa's metadata lookups) and
# were read live off that file - Kometa was removed entirely (no Jellyfin
# support, see CLAUDE.md's migration History), so these are now real
# standalone OMDB_KEY/MDBLIST_KEY .env secrets instead.
# ---------------------------------------------------------------------
@app.get("/api/ratings/imdb")
def rating_imdb(imdb_id: str):
    key = _omdb_key()
    if not key:
        fail("No OMDb API key found (OMDB_KEY not set in .env).", status_code=500)
    try:
        r = httpx.get("https://www.omdbapi.com/", params={"i": imdb_id, "apikey": key}, timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"OMDb request failed: {e}")
    data = r.json()
    if data.get("Response") == "False":
        fail(f"OMDb: {data.get('Error', 'no match for that IMDb id')}", status_code=404)
    rating = data.get("imdbRating")
    if not rating or rating == "N/A":
        fail(f'"{data.get("Title")}" has no IMDb rating yet.', status_code=404)
    return ok(
        f'"{data.get("Title")}" ({data.get("Year")}): {rating}/10 ({data.get("imdbVotes")} votes)',
        imdbId=imdb_id,
        title=data.get("Title"),
        year=data.get("Year"),
        rating=rating,
        votes=data.get("imdbVotes"),
    )


@app.get("/api/ratings/mdblist")
def rating_mdblist(imdb_id: str):
    key = _mdblist_key()
    if not key:
        fail("No MDBList API key found (MDBLIST_KEY not set in .env).", status_code=500)
    try:
        r = httpx.get("https://mdblist.com/api/", params={"apikey": key, "i": imdb_id}, timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"MDBList request failed: {e}")
    data = r.json()
    if data.get("response") is False:
        fail(f"MDBList: {data.get('error', 'no match for that IMDb id')}", status_code=404)
    imdb_entry = next((x for x in data.get("ratings", []) if x.get("source") == "imdb"), None)
    # MDBList fuzzy-matches an unrecognized-but-well-formed id to an
    # unrelated title instead of erroring, and even echoes the requested
    # id back as "imdbid" on that garbage match (confirmed live: a bogus
    # tt0000000 request "matched" an unrelated show, with the response's
    # own "imdbid" field reading back tt0000000) - so imdbid can't be used
    # to detect this. A real rating always carries a vote count; a garbage
    # match's imdb entry has null votes even when it has a 0 "value" - that
    # combination is the actual tell.
    has_real_imdb_rating = bool(imdb_entry and imdb_entry.get("votes"))
    score = data.get("score")
    if (score is None or score < 0) and not has_real_imdb_rating:
        fail(f'"{data.get("title")}" has no rating on MDBList yet.', status_code=404)
    message = f'"{data.get("title")}" ({data.get("year")}): MDBList score {score}/100'
    if imdb_entry and imdb_entry.get("value") is not None:
        message += f', IMDb {imdb_entry["value"]}/10 ({imdb_entry.get("votes")} votes)'
    return ok(
        message,
        imdbId=imdb_id,
        title=data.get("title"),
        year=data.get("year"),
        score=score,
        imdbRating=imdb_entry.get("value") if imdb_entry else None,
        imdbVotes=imdb_entry.get("votes") if imdb_entry else None,
    )


# MDBList's own lists already return items pre-split into "movies"/"shows"
# arrays with imdb_id/tvdb_id/tmdb_id per item - no scraping, no media-type
# detection needed on this end, unlike the Letterboxd list endpoints (which
# have to infer everything from an HTML poster grid). Direct IMDb list
# import was evaluated and dropped: IMDb's list/export pages sit behind a
# genuine AWS WAF JS challenge (confirmed live via the
# x-amzn-waf-action: challenge response header - not a bug in this stack,
# not workable with plain HTTP requests), and MDBList's own "external
# list" API only serves lists a user has already linked to their MDBList
# account through the website - there's no API to import an arbitrary
# IMDb URL programmatically. MDBList's own list search already mirrors
# common IMDb lists (Top 250 etc) under multiple users, which is the
# practical path to that content instead.
MDBLIST_URL_RE = re.compile(r"^https://mdblist\.com/lists/([^/]+)/([^/]+)/?$")


@app.post("/api/mdblist/import-list")
def mdblist_import_list(payload: MDBListImportRequest):
    key = _mdblist_key()
    if not key:
        fail("No MDBList API key found (MDBLIST_KEY not set in .env).", status_code=500)

    match = MDBLIST_URL_RE.match(payload.list_url.strip())
    if not match:
        fail(
            "Not a recognized MDBList list URL - expected something like "
            "https://mdblist.com/lists/<username>/<listname>.",
            status_code=400,
        )
    username, listname = match.groups()

    # One MDBList request already returns up to 1000 items - this hard cap
    # bounds worst-case pagination regardless of `limit`, same reasoning as
    # the Letterboxd list endpoint's 10-page/720-film cap.
    limit = min(payload.limit, 2000) if payload.limit else 2000

    movies: list[dict] = []
    shows: list[dict] = []
    cursor = None
    while len(movies) + len(shows) < limit:
        params = {"apikey": key, "limit": min(1000, limit - len(movies) - len(shows))}
        if cursor:
            params["cursor"] = cursor
        try:
            r = httpx.get(f"https://api.mdblist.com/lists/{username}/{listname}/items", params=params, timeout=20)
            r.raise_for_status()
        except httpx.HTTPError as e:
            fail(f"MDBList request failed: {e}")
        data = r.json()
        if isinstance(data, dict) and data.get("error"):
            fail(f"MDBList: {data['error']}", status_code=404)
        movies.extend(data.get("movies", []))
        shows.extend(data.get("shows", []))
        pagination = data.get("pagination", {})
        cursor = pagination.get("next_cursor")
        if not pagination.get("has_more") or not cursor:
            break

    if not movies and not shows:
        fail(f'No items found in MDBList list "{username}/{listname}" (or it is private/doesn\'t exist).', status_code=404)

    result = {"radarr": None, "sonarr": None}

    if movies:
        radarr_cfg = ARR_APPS["radarr"]
        try:
            library = httpx.get(
                f"{radarr_cfg['url']}/api/{radarr_cfg['api']}/movie", headers={"X-Api-Key": radarr_cfg["key"]}, timeout=30
            )
            library.raise_for_status()
        except httpx.HTTPError as e:
            fail(f"Couldn't read Radarr's library: {e}")
        existing_tmdb_ids = {m["tmdbId"] for m in library.json()}
        radarr_root_folder_path, radarr_quality_profile_id = _radarr_root_folder_and_profile(
            radarr_cfg, payload.radarr_root_folder, payload.radarr_quality_profile
        )

        added, already, failed = [], [], []
        for m in movies:
            tmdb_id = m.get("ids", {}).get("tmdb")
            if not tmdb_id:
                failed.append(f'"{m.get("title")}": no TMDb id from MDBList')
                continue
            r = _radarr_add_movie(
                radarr_cfg, tmdb_id, payload.monitored, payload.search, radarr_root_folder_path, radarr_quality_profile_id,
                existing_tmdb_ids, dry_run=payload.dry_run,
            )
            (added if r["status"] == "added" else already if r["status"] == "already" else failed).append(
                r.get("title") or r.get("reason") or tmdb_id
            )
        result["radarr"] = {"added": added, "alreadyCount": len(already), "failed": failed}

    if shows:
        sonarr_cfg = ARR_APPS["sonarr"]
        try:
            library = httpx.get(
                f"{sonarr_cfg['url']}/api/{sonarr_cfg['api']}/series", headers={"X-Api-Key": sonarr_cfg["key"]}, timeout=30
            )
            library.raise_for_status()
        except httpx.HTTPError as e:
            fail(f"Couldn't read Sonarr's library: {e}")
        existing_tvdb_ids = {s["tvdbId"] for s in library.json()}
        sonarr_root_folder_path, sonarr_quality_profile_id = _sonarr_root_folder_and_profile(
            sonarr_cfg, payload.sonarr_root_folder, payload.sonarr_quality_profile
        )

        added, already, failed = [], [], []
        for s in shows:
            tvdb_id = s.get("ids", {}).get("tvdb")
            if not tvdb_id:
                failed.append(f'"{s.get("title")}": no TVDb id from MDBList')
                continue
            r = _sonarr_add_series(
                sonarr_cfg, tvdb_id, payload.monitored, payload.search, sonarr_root_folder_path, sonarr_quality_profile_id,
                existing_tvdb_ids, dry_run=payload.dry_run,
            )
            (added if r["status"] == "added" else already if r["status"] == "already" else failed).append(
                r.get("title") or r.get("reason") or tvdb_id
            )
        result["sonarr"] = {"added": added, "alreadyCount": len(already), "failed": failed}

    verb = "would be added" if payload.dry_run else "added"
    parts = []
    if result["radarr"] is not None:
        parts.append(
            f"Radarr: {len(result['radarr']['added'])} {verb}, {result['radarr']['alreadyCount']} already present, "
            f"{len(result['radarr']['failed'])} failed"
        )
    if result["sonarr"] is not None:
        parts.append(
            f"Sonarr: {len(result['sonarr']['added'])} {verb}, {result['sonarr']['alreadyCount']} already present, "
            f"{len(result['sonarr']['failed'])} failed"
        )
    return ok("; ".join(parts), radarr=result["radarr"], sonarr=result["sonarr"], dryRun=payload.dry_run)


def human_size(n: int | None) -> str:
    if not n:
        return "?"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


# ---------------------------------------------------------------------
# *arr apps
# ---------------------------------------------------------------------
def arr_command(app_name: str, command: str) -> dict:
    if app_name not in ARR_APPS:
        fail(f"Unknown app '{app_name}'.", status_code=404)
    cfg = ARR_APPS[app_name]
    url = f"{cfg['url']}/api/{cfg['api']}/command"
    try:
        r = httpx.post(url, json={"name": command}, headers={"X-Api-Key": cfg["key"]}, timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} {command} failed: {e}")
    return cfg


@app.post("/api/arr/{app_name}/rss-sync")
def arr_rss_sync(app_name: str):
    cfg = arr_command(app_name, "RssSync")
    return ok(f"{cfg['label']} RSS sync started.")


@app.post("/api/arr/{app_name}/search-missing")
def arr_search_missing(app_name: str):
    if app_name not in ARR_APPS:
        fail(f"Unknown app '{app_name}'.", status_code=404)
    cfg = ARR_APPS[app_name]
    arr_command(app_name, cfg["search_command"])
    return ok(f"{cfg['label']} search for missing items started.")


# Letterboxd doesn't expose TMDb ids directly, but every matched film page
# links to its TMDb entry in the sidebar - regex is simpler and more stable
# than parsing Letterboxd's HTML structure, which isn't a documented API and
# changes without notice. No extra container needed (unlike
# screeny05/letterboxd-list-radarr's Redis-backed adapter service) - this
# just scrapes the pages Radarr needs the tmdbId from, server-side.
LETTERBOXD_TMDB_RE = re.compile(r"themoviedb\.org/movie/(\d+)")
# List/watchlist grid pages lazy-load their posters via JS in a browser, but
# the server-rendered HTML still carries each poster's slug in this
# attribute - confirmed live against a real 250-film list. Pagination links
# (.../page/2/, .../page/3/, ...) are present in that same server-rendered
# HTML too, so no separate AJAX endpoint needs reverse-engineering.
LETTERBOXD_ITEM_SLUG_RE = re.compile(r'data-item-slug="([^"]+)"')
LETTERBOXD_LIST_PAGE_RE = re.compile(r"/page/(\d+)/")


# A bare "compatible; ..." UA gets a real Cloudflare JS challenge (not just
# a 403 - a full "Just a moment..." challenge page) on some Letterboxd paths
# (confirmed live against /films/in/<collection>/), while a full browser-shaped
# header set passes consistently. /films/popular/'s poster grid is pure
# client-side JS hydration with zero server-rendered data at any header
# combination tried - a real limitation, not something headers fix.
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


def _radarr_root_folder_and_profile(cfg, root_folder: str | None, quality_profile: str | None) -> tuple[str, int]:
    try:
        folders = httpx.get(f"{cfg['url']}/api/{cfg['api']}/rootfolder", headers={"X-Api-Key": cfg["key"]}, timeout=15).json()
        profiles = httpx.get(
            f"{cfg['url']}/api/{cfg['api']}/qualityprofile", headers={"X-Api-Key": cfg["key"]}, timeout=15
        ).json()
    except httpx.HTTPError as e:
        fail(f"Couldn't read Radarr's root folders/quality profiles: {e}")

    # /data/movies and "Unlimited" are this stack's real defaults (see
    # README's Requests: Seerr section) - preferred when present, but not
    # hardcoded as the only option, since Radarr's own config is the source
    # of truth and either could be renamed independently of this file.
    root_folder_path = (
        root_folder
        or next((f["path"] for f in folders if f["path"] == "/data/movies"), None)
        or (folders[0]["path"] if folders else None)
    )
    if not root_folder_path:
        fail("Radarr has no root folders configured.", status_code=500)

    wanted_profile = quality_profile or "Unlimited"
    quality_profile_id = next((p["id"] for p in profiles if p["name"] == wanted_profile), None)
    if quality_profile_id is None:
        quality_profile_id = profiles[0]["id"] if profiles else None
    if quality_profile_id is None:
        fail("Radarr has no quality profiles configured.", status_code=500)

    return root_folder_path, quality_profile_id


def _sonarr_root_folder_and_profile(cfg, root_folder: str | None, quality_profile: str | None) -> tuple[str, int]:
    try:
        folders = httpx.get(f"{cfg['url']}/api/{cfg['api']}/rootfolder", headers={"X-Api-Key": cfg["key"]}, timeout=15).json()
        profiles = httpx.get(
            f"{cfg['url']}/api/{cfg['api']}/qualityprofile", headers={"X-Api-Key": cfg["key"]}, timeout=15
        ).json()
    except httpx.HTTPError as e:
        fail(f"Couldn't read Sonarr's root folders/quality profiles: {e}")

    # /data/shows and "Any" are this stack's real defaults (confirmed live
    # against Seerr's own Sonarr connection settings, same source used for
    # Radarr's /data/movies + "Unlimited" defaults above) - preferred when
    # present, but not hardcoded as the only option.
    root_folder_path = (
        root_folder
        or next((f["path"] for f in folders if f["path"] == "/data/shows"), None)
        or (folders[0]["path"] if folders else None)
    )
    if not root_folder_path:
        fail("Sonarr has no root folders configured.", status_code=500)

    wanted_profile = quality_profile or "Any"
    quality_profile_id = next((p["id"] for p in profiles if p["name"] == wanted_profile), None)
    if quality_profile_id is None:
        quality_profile_id = profiles[0]["id"] if profiles else None
    if quality_profile_id is None:
        fail("Sonarr has no quality profiles configured.", status_code=500)

    return root_folder_path, quality_profile_id


def _radarr_add_movie(
    cfg, tmdb_id: int, monitored: bool, search: bool, root_folder_path: str, quality_profile_id: int,
    existing_tmdb_ids: set[int], dry_run: bool = False,
) -> dict:
    """Looks up a movie by tmdbId and adds it if not already present.
    existing_tmdb_ids is a pre-fetched set (one bulk GET /movie call
    covers a whole list-import, instead of one existence check per item).
    Returns {"status": "added"|"already"|"failed", "title": ..., ...}."""
    if tmdb_id in existing_tmdb_ids:
        return {"status": "already", "title": None, "tmdbId": tmdb_id}
    try:
        lookup = httpx.get(
            f"{cfg['url']}/api/{cfg['api']}/movie/lookup/tmdb",
            params={"tmdbId": tmdb_id},
            headers={"X-Api-Key": cfg["key"]},
            timeout=20,
        )
        lookup.raise_for_status()
        movie = lookup.json()
    except httpx.HTTPError as e:
        return {"status": "failed", "reason": f"tmdb {tmdb_id}: lookup failed ({e})"}
    if not movie or not movie.get("title"):
        return {"status": "failed", "reason": f"tmdb {tmdb_id}: no Radarr match"}

    movie["qualityProfileId"] = quality_profile_id
    movie["rootFolderPath"] = root_folder_path
    movie["monitored"] = monitored
    movie["addOptions"] = {"searchForMovie": search}

    if dry_run:
        return {"status": "added", "title": movie["title"]}

    try:
        add = httpx.post(f"{cfg['url']}/api/{cfg['api']}/movie", json=movie, headers={"X-Api-Key": cfg["key"]}, timeout=30)
        add.raise_for_status()
    except httpx.HTTPStatusError as e:
        return {"status": "failed", "reason": f'"{movie["title"]}": {e.response.text.strip() or e}'}
    except httpx.HTTPError as e:
        return {"status": "failed", "reason": f'"{movie["title"]}": {e}'}
    return {"status": "added", "title": add.json().get("title", movie["title"])}


def _sonarr_add_series(
    cfg, tvdb_id: int, monitored: bool, search: bool, root_folder_path: str, quality_profile_id: int,
    existing_tvdb_ids: set[int], dry_run: bool = False,
) -> dict:
    """Looks up a series by tvdbId and adds it if not already present.
    existing_tvdb_ids is a pre-fetched set, same reasoning as
    _radarr_add_movie above. Returns
    {"status": "added"|"already"|"failed", "title": ..., ...}."""
    if tvdb_id in existing_tvdb_ids:
        return {"status": "already", "title": None, "tvdbId": tvdb_id}
    try:
        lookup = httpx.get(
            f"{cfg['url']}/api/{cfg['api']}/series/lookup",
            params={"term": f"tvdb:{tvdb_id}"},
            headers={"X-Api-Key": cfg["key"]},
            timeout=20,
        )
        lookup.raise_for_status()
        results = lookup.json()
    except httpx.HTTPError as e:
        return {"status": "failed", "reason": f"tvdb {tvdb_id}: lookup failed ({e})"}
    if not results:
        return {"status": "failed", "reason": f"tvdb {tvdb_id}: no Sonarr match"}
    series = results[0]

    series["qualityProfileId"] = quality_profile_id
    series["rootFolderPath"] = root_folder_path
    series["monitored"] = monitored
    series["seasonFolder"] = True
    series["addOptions"] = {
        "monitor": "all" if monitored else "none",
        "searchForMissingEpisodes": search,
        "searchForCutoffUnmetEpisodes": False,
    }

    if dry_run:
        return {"status": "added", "title": series["title"]}

    try:
        add = httpx.post(f"{cfg['url']}/api/{cfg['api']}/series", json=series, headers={"X-Api-Key": cfg["key"]}, timeout=30)
        add.raise_for_status()
    except httpx.HTTPStatusError as e:
        return {"status": "failed", "reason": f'"{series["title"]}": {e.response.text.strip() or e}'}
    except httpx.HTTPError as e:
        return {"status": "failed", "reason": f'"{series["title"]}": {e}'}
    added = add.json()
    return {"status": "added", "title": added.get("title", series["title"])}


@app.post("/api/arr/radarr/add-from-letterboxd")
def radarr_add_from_letterboxd(payload: LetterboxdAddRequest):
    cfg = ARR_APPS["radarr"]
    url = payload.url.strip()
    if "letterboxd.com/film/" not in url:
        fail("Not a Letterboxd film URL - expected something like https://letterboxd.com/film/<slug>/.", status_code=400)
    page_text = _letterboxd_page(url)
    match = LETTERBOXD_TMDB_RE.search(page_text)
    if not match:
        fail("No TMDb link found on that Letterboxd page - it may be unmatched to TMDb.", status_code=404)
    tmdb_id = int(match.group(1))

    # /movie/lookup/tmdb never carries a usable "id" for an already-added
    # movie in the version this stack runs (confirmed live: Inception, id
    # 595 in this library, still came back with no top-level "id" field at
    # all) - /movie?tmdbId= is the reliable way to check, since it returns
    # the real library entry (with its real id) when one exists.
    try:
        existing = httpx.get(
            f"{cfg['url']}/api/{cfg['api']}/movie",
            params={"tmdbId": tmdb_id},
            headers={"X-Api-Key": cfg["key"]},
            timeout=20,
        )
        existing.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Couldn't check whether Radarr already has this movie: {e}")
    existing_movies = existing.json()
    if existing_movies:
        m = existing_movies[0]
        return ok(
            f'"{m["title"]}" ({m.get("year")}) is already in Radarr.',
            tmdbId=tmdb_id,
            radarrId=m["id"],
            alreadyAdded=True,
        )

    try:
        lookup = httpx.get(
            f"{cfg['url']}/api/{cfg['api']}/movie/lookup/tmdb",
            params={"tmdbId": tmdb_id},
            headers={"X-Api-Key": cfg["key"]},
            timeout=20,
        )
        lookup.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Radarr's TMDb lookup failed: {e}")
    movie = lookup.json()
    if not movie or not movie.get("title"):
        fail(f"Radarr has no TMDb match for id {tmdb_id}.", status_code=404)

    root_folder_path, quality_profile_id = _radarr_root_folder_and_profile(cfg, payload.root_folder, payload.quality_profile)
    movie["qualityProfileId"] = quality_profile_id
    movie["rootFolderPath"] = root_folder_path
    movie["monitored"] = payload.monitored
    movie["addOptions"] = {"searchForMovie": payload.search}

    if payload.dry_run:
        return ok(
            f'Would add "{movie["title"]}" ({movie.get("year")}) to Radarr - dry run, nothing written.',
            tmdbId=tmdb_id,
            dryRun=True,
        )

    try:
        add = httpx.post(f"{cfg['url']}/api/{cfg['api']}/movie", json=movie, headers={"X-Api-Key": cfg["key"]}, timeout=30)
        add.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = e.response.text.strip() or str(e)
        fail(f"Radarr rejected the add: {detail}")
    except httpx.HTTPError as e:
        fail(f"Radarr add failed: {e}")

    added = add.json()
    return ok(
        f'Added "{added.get("title", movie["title"])}" ({added.get("year", movie.get("year"))}) to Radarr.',
        tmdbId=tmdb_id,
        radarrId=added.get("id"),
    )


# robots.txt's "User-agent: *" section disallows these sort/filter path
# segments specifically (fetched and read live from letterboxd.com/robots.txt)
# - browsing a list/filmography/collection itself is allowed, sorting or
# filtering it is not. Checked against the full URL, since these can appear
# anywhere in the path (e.g. /films/popular/this/week/, /films/year/2020/).
LETTERBOXD_DISALLOWED_RE = re.compile(
    r"/(by|on|tag|genre|country|language|decade|friends)/"
    r"|/popular/this/"
    r"|/films/year/"
    r"|/films/[^/]+/year/"
    r"|/films/[^/]+/size/large/"
)
# Every content-grid shape this technique supports: a user's list/watchlist/
# watched-films page, a person's filmography (actor/director/writer/any
# other crew role Letterboxd tracks - not enumerated here, an unknown role
# just 404s with a clear error), a collection, or the base films page.
LETTERBOXD_GRID_RE = re.compile(
    r"^https://letterboxd\.com/(?:[^/]+/(?:list/[^/]+|watchlist|films)|[a-z-]+/[^/]+|films/in/[^/]+|films)/?$"
)


@app.post("/api/arr/radarr/add-from-letterboxd-list")
def radarr_add_from_letterboxd_list(payload: LetterboxdListAddRequest):
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
    # Hard cap, not a default - Letterboxd's own pagination for these grids
    # tops out functionally useful browsing around here, and it bounds how
    # many outbound requests one call can trigger regardless of `limit`.
    last_page = min(max((int(n) for n in LETTERBOXD_LIST_PAGE_RE.findall(first_page)), default=1), 10)

    slugs = list(dict.fromkeys(LETTERBOXD_ITEM_SLUG_RE.findall(first_page)))
    # Page 1 failing is a hard error (nothing to work with), but pagination
    # beyond it hits a real Cloudflare JS challenge on some URL shapes (e.g.
    # a user's /films/ watched-films page - confirmed live, page 1 serves
    # fine, page 2 gets a genuine "Just a moment..." challenge, not
    # something a header tweak fixes). Stopping at the last page that
    # actually loaded beats failing the whole request over a partial result.
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

    # 720 matches the 10-page cap above (Letterboxd's grids run ~72/page) -
    # `limit` can only narrow this further, not exceed it.
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

    root_folder_path, quality_profile_id = _radarr_root_folder_and_profile(cfg, payload.root_folder, payload.quality_profile)

    added, already, failed = [], [], []
    total_movies = len(tmdb_ids)
    for i, tmdb_id in enumerate(tmdb_ids, 1):
        result = _radarr_add_movie(
            cfg, tmdb_id, payload.monitored, payload.search, root_folder_path, quality_profile_id,
            existing_tmdb_ids, dry_run=payload.dry_run,
        )
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


# Snapshot of an arr app's own /command queue - not just the download
# queue (arr_queue above), but the internal task backlog (searches,
# RSS sync, bulk moves, etc). Surfaced after a real incident where a
# hung ProcessMonitoredDownloads command silently backed up everything
# behind it for over an hour with zero indication in the normal UI.
@app.get("/api/arr/{app_name}/command-backlog")
def arr_command_backlog(app_name: str):
    if app_name not in ARR_APPS:
        fail(f"Unknown app '{app_name}'.", status_code=404)
    cfg = ARR_APPS[app_name]
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/command", headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} command lookup failed: {e}")
    commands = r.json()
    counts = Counter(c.get("status") for c in commands)
    running = sorted(
        (
            {"id": c["id"], "name": c["name"], "started": c.get("started")}
            for c in commands
            if c.get("status") == "started"
        ),
        key=lambda c: c["started"] or "",
    )
    queued = sorted((c for c in commands if c.get("status") == "queued"), key=lambda c: c.get("queued") or "")
    oldest_queued = [{"id": c["id"], "name": c["name"], "queued": c.get("queued")} for c in queued[:5]]
    return ok(
        f"{cfg['label']}: {len(commands)} commands total "
        f"({counts.get('completed', 0)} completed, {counts.get('queued', 0)} queued, "
        f"{counts.get('started', 0)} running).",
        total=len(commands),
        counts=dict(counts),
        running=running,
        queued_total=len(queued),
        oldest_queued=oldest_queued,
    )


# ---------------------------------------------------------------------
# Unstick + manual import - for queue items the arr app flagged itself
# (trackedDownloadStatus warning/error, the same icon its own UI shows),
# usually caused by the NzbDAV mount going stale mid-import or a release
# that doesn't actually match what was expected.
# ---------------------------------------------------------------------
def require_queue_app(app_name: str) -> dict:
    if app_name not in QUEUE_ARR_APPS:
        fail(f"'{app_name}' isn't supported here - only radarr and sonarr have a queue.", status_code=404)
    return ARR_APPS[app_name]


def arr_queue(app_name: str) -> list[dict]:
    cfg = ARR_APPS[app_name]
    try:
        r = httpx.get(
            f"{cfg['url']}/api/{cfg['api']}/queue",
            params={"pageSize": 250, "includeUnknownMovieItems": "true"},
            headers={"X-Api-Key": cfg["key"]},
            timeout=20,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} queue lookup failed: {e}")
    return r.json().get("records", [])


def stuck_queue_items(app_name: str) -> list[dict]:
    # warning/error is exactly what lights up the warning icon in Radarr's
    # and Sonarr's own Activity/Queue tab - not "importPending", which is
    # just normal in-progress state. Used by Unstick only (which removes +
    # blocklists + re-searches) - deliberately narrower than
    # import_candidate_queue_items below, since blocklisting a fine
    # importPending download that just hasn't been processed yet would be
    # actively harmful.
    return [q for q in arr_queue(app_name) if q.get("trackedDownloadStatus") in ("warning", "error")]


def import_candidate_queue_items(app_name: str) -> list[dict]:
    # Broader than stuck_queue_items - also includes "importPending" (fully
    # downloaded, waiting on the arr app's own internal queue-processing
    # command to actually run the import). Found live: this is common, not
    # rare - a busy arr instance can sit on a completed download for
    # minutes at a time behind its own command queue, and the previous
    # warning/error-only filter meant Manual Import always reported "0
    # importable files" for exactly the downloads a user would most want to
    # nudge along.
    return [
        q for q in arr_queue(app_name)
        if q.get("trackedDownloadStatus") in ("warning", "error")
        or q.get("trackedDownloadState") == "importPending"
    ]


@app.post("/api/arr/{app_name}/unstick")
def arr_unstick(app_name: str):
    cfg = require_queue_app(app_name)
    items = stuck_queue_items(app_name)
    if not items:
        return ok(f"No stuck downloads in {cfg['label']}.")
    removed, errors = [], []
    for q in items:
        title = q.get("title") or str(q["id"])
        try:
            r = httpx.delete(
                f"{cfg['url']}/api/{cfg['api']}/queue/{q['id']}",
                params={"removeFromClient": "true", "blocklist": "true", "skipRedownload": "false"},
                headers={"X-Api-Key": cfg["key"]},
                timeout=20,
            )
            r.raise_for_status()
            removed.append(title)
        except httpx.HTTPError as e:
            errors.append(f"{title}: {e}")
    if errors and not removed:
        fail(f"Unstick failed for all {len(errors)} stuck item(s) in {cfg['label']}: {errors[0]}")
    message = f"Removed, blocklisted, and re-searching {len(removed)} stuck download(s) in {cfg['label']}."
    if errors:
        message += f" {len(errors)} failed."
    return ok(message, removed=removed, errors=errors)


# ---------------------------------------------------------------------
# Unstick (importing) - a distinct failure mode from the warning/error one
# above. A download wedged in trackedDownloadState "importing" keeps
# trackedDownloadStatus "ok" the whole time, so it never lights up the
# arr app's own warning icon and Unstick above never touches it - but
# since disk-access commands run through a single execution slot, one
# wedged import silently blocks every other item queued behind it.
# Confirmed live across four separate incidents in one afternoon
# (2026-07-18, under NzbDAV - see CLAUDE.md's History for its removal):
# three were nzbdav-rclone symlinks pointing at permanently-missing Usenet
# articles; one was a queue record whose outputPath had simply vanished
# from disk entirely (no symlink there at all, not just an unreadable
# one). A plain queue-status check can't tell any of these from a
# merely-wedged slot - all just show "importing" - so this checks whether
# outputPath exists at all, and if so reads the first few MB of a file
# under it straight through the arr app's own container mount. A dead
# article fails, sometimes only after ~30s (rclone/AltMount retries
# before giving up); a wedged-but-fine file reads instantly; a
# missing path fails the existence check immediately. Broken releases get
# blocklisted so they aren't regrabbed; merely-wedged or missing-path ones
# are removed without blocklisting, since neither is evidence the release
# itself is bad. Either way the
# affected series/movie gets a fresh search queued afterward.
# ---------------------------------------------------------------------
IMPORTING_TEST_TIMEOUT_S = 40
IMPORTING_TEST_MB = 5


def _dd_test_file(container, file_path: str) -> tuple[bool, str]:
    try:
        result = container.exec_run(
            cmd=[
                "timeout", str(IMPORTING_TEST_TIMEOUT_S),
                "dd", f"if={file_path}", "of=/dev/null", "bs=1M", f"count={IMPORTING_TEST_MB}",
            ],
            demux=True,
        )
    except Exception as e:
        return False, f"exec failed: {e}"
    if result.exit_code == 0:
        return True, "readable"
    stderr = b""
    if result.output and result.output[1]:
        stderr = result.output[1]
    return False, stderr.decode(errors="replace").strip() or f"dd exited {result.exit_code}"


def _find_candidate_files(container, output_path: str) -> tuple[str, list[str]]:
    """Locates a file under output_path to dd-test. Returns (status, files):
    'missing' if output_path doesn't exist on disk at all (a distinct wedge
    from a dead article - confirmed live 2026-07-18, a queue record can sit
    in "importing" pointing at a symlink that's simply gone, e.g. cleaned up
    or evicted before the import ran), 'empty' if the path exists but has no
    file under it worth testing, or 'ok' with the files found."""
    exists = container.exec_run(cmd=["test", "-e", output_path])
    if exists.exit_code != 0:
        return "missing", []
    # Symlinks first - AltMount's mount may route root folders through
    # symlinks depending on import strategy; not yet fully verified either
    # way for the current config (import_strategy: NONE).
    find_result = container.exec_run(cmd=["find", output_path, "-maxdepth", "2", "-type", "l"])
    files = [f for f in find_result.output.decode(errors="replace").splitlines() if f.strip()]
    if not files:
        find_result = container.exec_run(cmd=["find", output_path, "-maxdepth", "2", "-type", "f"])
        files = [f for f in find_result.output.decode(errors="replace").splitlines() if f.strip()]
    return ("ok", files) if files else ("empty", [])


def _importing_queue_targets(app_name: str) -> list[dict]:
    # Multiple queue records can share one underlying download (a season
    # pack fans out to one record per episode, all with the same
    # downloadId) - dedupe before testing, or a single dead article gets
    # diagnosed once but the caller would otherwise loop over it N times.
    items = [q for q in arr_queue(app_name) if q.get("trackedDownloadState") == "importing"]
    by_download: dict[str, dict] = {}
    for q in items:
        key = q.get("downloadId") or str(q["id"])
        target = by_download.setdefault(key, {
            "queueIds": [],
            "title": q.get("title"),
            "outputPath": q.get("outputPath"),
            "seriesId": q.get("seriesId"),
            "movieId": q.get("movieId"),
        })
        target["queueIds"].append(q["id"])
    return list(by_download.values())


@app.post("/api/arr/{app_name}/unstick-importing")
def arr_unstick_importing(app_name: str):
    cfg = require_queue_app(app_name)
    targets = _importing_queue_targets(app_name)
    if not targets:
        return ok(f"No downloads currently importing in {cfg['label']}.")
    try:
        container = docker_client.containers.get(app_name)
    except docker.errors.NotFound:
        fail(f"Container '{app_name}' not found.")

    results = []
    to_research: set[tuple[str, int]] = set()
    for t in targets:
        output_path = t.get("outputPath")
        title = t.get("title") or "(untitled)"
        if not output_path:
            results.append({"title": title, "verdict": "skipped", "detail": "no outputPath on queue item"})
            continue
        status, files = _find_candidate_files(container, output_path)
        if status == "empty":
            results.append({"title": title, "verdict": "skipped", "detail": "outputPath exists but has no candidate file"})
            continue
        if status == "missing":
            # The path is simply gone, not evidence the release itself is
            # dead (could be a symlink cleaned up/evicted before the import
            # ran) - clear without blocklisting so it can regrab/rediscover
            # rather than banning a release that might be perfectly fine.
            blocklist = False
            detail = "outputPath does not exist on disk"
        else:
            # One representative file per download, same as the manual
            # technique this mirrors - testing every file in a season pack
            # would multiply the up-to-40s-per-file cost for no real gain,
            # since a single grab's files share the same source post/health.
            readable, detail = _dd_test_file(container, files[0])
            blocklist = not readable
        delete_failed = False
        for qid in t["queueIds"]:
            try:
                r = httpx.delete(
                    f"{cfg['url']}/api/{cfg['api']}/queue/{qid}",
                    params={"removeFromClient": "true", "blocklist": str(blocklist).lower(), "skipRedownload": "false"},
                    headers={"X-Api-Key": cfg["key"]},
                    timeout=20,
                )
                # A shared downloadId means later ids 404 once the first
                # delete clears the whole download from the client - not an
                # error, same pattern as /unstick above.
                if r.status_code not in (200, 404):
                    r.raise_for_status()
            except httpx.HTTPError as e:
                results.append({"title": title, "verdict": "error", "detail": f"delete failed: {e}"})
                delete_failed = True
                break
        if delete_failed:
            continue
        if status == "missing":
            verdict = "path-missing-cleared"
        elif blocklist:
            verdict = "broken-blocklisted"
        else:
            verdict = "wedged-cleared"
        results.append({"title": title, "verdict": verdict, "detail": detail})
        if t.get("seriesId"):
            to_research.add(("series", t["seriesId"]))
        if t.get("movieId"):
            to_research.add(("movie", t["movieId"]))

    for kind, rid in to_research:
        body = {"name": "SeriesSearch", "seriesId": rid} if kind == "series" else {"name": "MoviesSearch", "movieIds": [rid]}
        try:
            httpx.post(f"{cfg['url']}/api/{cfg['api']}/command", json=body, headers={"X-Api-Key": cfg["key"]}, timeout=20)
        except httpx.HTTPError:
            pass

    broken_n = sum(1 for r in results if r["verdict"] == "broken-blocklisted")
    wedged_n = sum(1 for r in results if r["verdict"] == "wedged-cleared")
    missing_n = sum(1 for r in results if r["verdict"] == "path-missing-cleared")
    message = (
        f"{cfg['label']}: checked {len(targets)} importing item(s) - "
        f"{broken_n} broken/blocklisted, {wedged_n} wedged/cleared, {missing_n} missing-path/cleared."
    )
    return ok(message, results=results)


@app.get("/api/arr/{app_name}/manual-import")
def arr_manual_import_candidates(app_name: str):
    """Every importable file the arr app can see across all currently
    stuck-or-importPending queue items, in the same shape its own Manual
    Import screen would show - each candidate is echoed straight back on
    import so the quality/language/match info can't drift from what the
    arr app itself reported."""
    cfg = require_queue_app(app_name)
    candidates = []
    for q in import_candidate_queue_items(app_name):
        folder, download_id = q.get("outputPath"), q.get("downloadId")
        if not folder or not download_id:
            continue
        try:
            r = httpx.get(
                f"{cfg['url']}/api/{cfg['api']}/manualimport",
                params={"folder": folder, "downloadId": download_id, "filterExistingFiles": "true"},
                headers={"X-Api-Key": cfg["key"]},
                timeout=30,
            )
            r.raise_for_status()
        except httpx.HTTPError:
            # One queue item's folder failing to scan shouldn't blank the
            # whole list - the others are still worth showing.
            continue
        for f in r.json():
            match = f.get("movie") or f.get("series") or f.get("author")
            episodes = f.get("episodes") or []
            file_payload = {
                "path": f.get("path"),
                "folderName": f.get("folderName"),
                "quality": f.get("quality"),
                "languages": f.get("languages"),
                "releaseGroup": f.get("releaseGroup"),
                "downloadId": f.get("downloadId"),
            }
            if app_name == "radarr":
                file_payload["movieId"] = match.get("id") if match else None
            elif app_name == "sonarr":
                file_payload["seriesId"] = (match or {}).get("id") or (episodes[0]["seriesId"] if episodes else None)
                file_payload["episodeIds"] = [e["id"] for e in episodes]
            episode_label = None
            if episodes:
                e = episodes[0]
                episode_label = f"S{e['seasonNumber']:02d}E{e['episodeNumber']:02d} - {e.get('title', '')}"
            candidates.append({
                "queue_title": q.get("title"),
                "name": f.get("name"),
                "relative_path": f.get("relativePath"),
                "size": human_size(f.get("size")),
                "quality": (f.get("quality") or {}).get("quality", {}).get("name"),
                "release_group": f.get("releaseGroup"),
                "rejections": [x.get("reason") for x in f.get("rejections", [])],
                "match_title": match.get("title") if match else None,
                "episode": episode_label,
                "file": file_payload,
            })
    return candidates


@app.post("/api/arr/{app_name}/manual-import")
def arr_manual_import_execute(app_name: str, payload: ManualImportFile):
    cfg = require_queue_app(app_name)
    body = {"name": "ManualImport", "files": [payload.model_dump(exclude_none=True)]}
    try:
        r = httpx.post(f"{cfg['url']}/api/{cfg['api']}/command", json=body, headers={"X-Api-Key": cfg["key"]}, timeout=30)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = e.response.text.strip() or str(e)
        fail(f"{cfg['label']} manual import failed: {detail}")
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} manual import failed: {e}")
    name = payload.path.rsplit("/", 1)[-1]
    return ok(f'Import started for "{name}" in {cfg["label"]}.')


@app.post("/api/arr/{app_name}/manual-import-all")
def arr_manual_import_all(app_name: str):
    """Bulk version of manual-import above - imports every candidate
    arr_manual_import_candidates currently lists (across all stuck queue
    items) in a single ManualImport command, instead of one API call per
    file."""
    cfg = require_queue_app(app_name)
    files = [c["file"] for c in arr_manual_import_candidates(app_name)]
    if not files:
        return ok(f"No importable files in {cfg['label']}.")
    body = {"name": "ManualImport", "files": files}
    try:
        r = httpx.post(f"{cfg['url']}/api/{cfg['api']}/command", json=body, headers={"X-Api-Key": cfg["key"]}, timeout=30)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = e.response.text.strip() or str(e)
        fail(f"{cfg['label']} bulk import failed: {detail}")
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} bulk import failed: {e}")
    return ok(f"Import started for {len(files)} file(s) in {cfg['label']}.", count=len(files))


# ---------------------------------------------------------------------
# Queue status + ETA - deliberately doesn't trust each app's own
# timeleft/estimatedCompletionTime (Radarr/Sonarr/etc) or NzbDAV's own
# timeleft: both are stale "00:00:00" placeholders for nearly everything
# in this stack, confirmed live. NzbDAV's SABnzbd-emulation layer doesn't
# compute a speed field at all even though its mb/mbleft are real. This
# takes two live size-remaining samples ~4s apart and derives real
# observed speed from the delta - honest about "no progress observed"
# (still caching server-side, or genuinely stalled) instead of
# fabricating an ETA the data can't support.
# ---------------------------------------------------------------------
QUEUE_SAMPLE_SECONDS = 4


def _arr_sizeleft_snapshot(app_name: str) -> dict[int, int]:
    try:
        records = arr_queue(app_name)
    except HTTPException:
        return {}
    return {q["id"]: q.get("sizeleft") or 0 for q in records if q.get("sizeleft")}


def _altmount_mbleft_snapshot() -> dict[str, float]:
    try:
        slots = altmount_api("queue").get("queue", {}).get("slots", [])
    except HTTPException:
        return {}
    return {s["nzo_id"]: float(s.get("mbleft") or 0) for s in slots if s.get("status") == "Downloading"}


def format_eta(seconds: float) -> str:
    if seconds == float("inf") or seconds < 0:
        return "unknown"
    seconds = int(seconds)
    # Days case is for the wanted/missing backlog ETA below - a
    # multi-thousand-item backlog at a modest throughput rate can run into
    # weeks, unlike a single download's ETA which never needs it.
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d{hours:02d}h"
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def _bucket_arr_item(q: dict, prev_sizeleft: dict[int, int]) -> tuple[str, dict]:
    title = q.get("title") or "?"
    size = q.get("size") or 0
    sizeleft = q.get("sizeleft") or 0
    item = {"title": title, "size": human_size(size)}
    if sizeleft > 0:
        item["size_left"] = human_size(sizeleft)
    if q.get("trackedDownloadState") in ("importPending", "importBlocked"):
        item["note"] = "fully fetched, waiting on import"
        return "importing", item
    if sizeleft <= 0:
        item["note"] = "queued, not yet started"
        return "queued", item
    prev = prev_sizeleft.get(q["id"])
    if prev is not None and prev > sizeleft:
        speed = (prev - sizeleft) / QUEUE_SAMPLE_SECONDS
        eta = sizeleft / speed if speed > 0 else float("inf")
        item["speed"] = f"{human_size(speed)}/s"
        item["eta"] = format_eta(eta)
        return "downloading", item
    item["note"] = "no progress observed (still caching, or stalled)"
    return "stalled", item


def _bucket_altmount_item(s: dict, prev_mbleft: dict[str, float]) -> tuple[str, dict]:
    title = s.get("filename") or "?"
    mb = float(s.get("mb") or 0)
    mbleft = float(s.get("mbleft") or 0)
    item = {"title": title, "size": f"{mb:.0f} MB", "size_left": f"{mbleft:.0f} MB"}
    if s.get("status") != "Downloading" or mbleft <= 0:
        item["note"] = "queued, not yet started" if mbleft > 0 else "fully fetched, waiting on import"
        return ("queued" if mbleft > 0 else "importing"), item
    prev = prev_mbleft.get(s["nzo_id"])
    if prev is not None and prev > mbleft:
        speed_mb = (prev - mbleft) / QUEUE_SAMPLE_SECONDS
        eta = mbleft / speed_mb if speed_mb > 0 else float("inf")
        item["speed"] = f"{speed_mb:.1f} MB/s"
        item["eta"] = format_eta(eta)
        return "downloading", item
    item["note"] = "no progress observed (still caching, or stalled)"
    return "stalled", item


# Plex has no byte size to drain - its own /activities progress (0-100)
# for library scans, deep media analysis, thumbnail generation, etc. is
# the equivalent signal, measured the same way (live delta over the same
# sample window, not trusted as-is - unlike the download clients above
# Plex's own progress numbers are usually real and moving, but a scan can
# still sit at one percentage for a while on a large/slow library section).
def _plex_activities() -> list[dict]:
    try:
        r = httpx.get(f"{PLEX_URL}/activities", headers=plex_headers(), timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Plex activities lookup failed: {e}")
    return r.json().get("MediaContainer", {}).get("Activity", [])


def _plex_progress_snapshot() -> dict[str, int]:
    try:
        return {a["uuid"]: a.get("progress", 0) for a in _plex_activities()}
    except HTTPException:
        return {}


def _bucket_plex_activity(a: dict, prev_progress: dict[str, int]) -> tuple[str, dict]:
    title = a.get("title") or "?"
    if a.get("subtitle"):
        title = f"{title}: {a['subtitle']}"
    progress = a.get("progress", 0)
    item = {"title": title, "progress": f"{progress}%"}
    prev = prev_progress.get(a["uuid"])
    if prev is not None and progress > prev:
        rate = (progress - prev) / QUEUE_SAMPLE_SECONDS  # percent per second
        eta = (100 - progress) / rate if rate > 0 else float("inf")
        item["eta"] = format_eta(eta)
        return "downloading", item
    item["note"] = "no progress observed (large section, or genuinely stalled)"
    return "stalled", item


@app.get("/api/queue-status")
def queue_status():
    """Every *arr app's download queue plus NzbDAV's and Plex's own
    background activities (library scans, media analysis, etc), bucketed
    into downloading/stalled/queued/importing with a real speed/progress
    and ETA for anything actually observed to be draining - see the
    module comment above for why this measures live instead of trusting
    each app's own timeleft."""
    before_arr = {app_name: _arr_sizeleft_snapshot(app_name) for app_name in QUEUE_ARR_APPS}
    before_altmount = _altmount_mbleft_snapshot()
    before_plex = _plex_progress_snapshot()
    time.sleep(QUEUE_SAMPLE_SECONDS)

    result = {}
    grand_total = 0
    for app_name in QUEUE_ARR_APPS:
        cfg = ARR_APPS[app_name]
        try:
            records = arr_queue(app_name)
        except HTTPException:
            result[app_name] = {"label": cfg["label"], "error": "unreachable"}
            continue
        buckets = {"downloading": [], "stalled": [], "queued": [], "importing": []}
        for q in records:
            bucket, item = _bucket_arr_item(q, before_arr[app_name])
            buckets[bucket].append(item)
        grand_total += len(records)
        result[app_name] = {"label": cfg["label"], "total": len(records), **buckets}

    try:
        slots = altmount_api("queue").get("queue", {}).get("slots", [])
        buckets = {"downloading": [], "stalled": [], "queued": [], "importing": []}
        for s in slots:
            bucket, item = _bucket_altmount_item(s, before_altmount)
            buckets[bucket].append(item)
        grand_total += len(slots)
        result["altmount"] = {"label": "AltMount", "total": len(slots), **buckets}
    except HTTPException:
        result["altmount"] = {"label": "AltMount", "error": "unreachable"}

    try:
        activities = _plex_activities()
        buckets = {"downloading": [], "stalled": [], "queued": [], "importing": []}
        for a in activities:
            bucket, item = _bucket_plex_activity(a, before_plex)
            buckets[bucket].append(item)
        grand_total += len(activities)
        result["plex"] = {"label": "Plex", "total": len(activities), **buckets}
    except HTTPException:
        result["plex"] = {"label": "Plex", "error": "unreachable"}

    # Bazarr has no in-progress download to bucket as downloading/stalled - a
    # subtitle grab completes synchronously within one API call, there's no
    # multi-second transfer to sample twice like the arr/altmount/plex
    # sources above. Its "wanted" list is the honest analog of a queue here: items
    # still waiting to be searched, which is exactly the "queued" bucket
    # already means for every other source.
    try:
        headers = _bazarr_headers()
        movies_wanted = httpx.get(f"{BAZARR_URL}/api/movies/wanted", headers=headers, timeout=20)
        movies_wanted.raise_for_status()
        episodes_wanted = httpx.get(f"{BAZARR_URL}/api/episodes/wanted", headers=headers, timeout=20)
        episodes_wanted.raise_for_status()
        queued = [{"title": m.get("title"), "note": "missing subtitle"}
                  for m in movies_wanted.json().get("data", [])]
        queued += [{"title": f'{e.get("seriesTitle")} - {e.get("episode_number", "")}', "note": "missing subtitle"}
                   for e in episodes_wanted.json().get("data", [])]
        grand_total += len(queued)
        result["bazarr"] = {"label": "Bazarr", "total": len(queued),
                             "downloading": [], "stalled": [], "queued": queued, "importing": []}
    except (HTTPException, httpx.HTTPError) as e:
        result["bazarr"] = {"label": "Bazarr", "error": str(e) if isinstance(e, httpx.HTTPError) else "unreachable"}

    active = sum(len(v.get("downloading", [])) for v in result.values())
    return ok(
        f"{grand_total} item(s) across {len(result)} queues, {active} actively downloading.",
        queues=result,
    )


def parse_air_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@app.get("/api/arr/{app_name}/missing-aired")
def arr_missing_aired(app_name: str):
    """Monitored + no file + already aired/released, excluding upcoming
    items that can't have a file yet. Sonarr's own Wanted/Missing list has
    no way to do this itself - confirmed against its actual frontend
    bundle, customFilterType only covers series/calendar/queue/history/
    blocklist/releases, not the missing-episodes page - so without this,
    that list is buried under ~300k not-yet-aired episodes from daily/
    ongoing shows (soaps, game shows, etc.). Radarr already has a native
    equivalent (monitored + !hasFile + isAvailable, saved as a custom
    filter on the movie list); this mirrors that same logic for both apps
    in one place.
    """
    if app_name not in ARR_APPS:
        fail(f"Unknown app '{app_name}'.", status_code=404)
    cfg = ARR_APPS[app_name]

    if app_name == "radarr":
        try:
            r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie", headers={"X-Api-Key": cfg["key"]}, timeout=30)
            r.raise_for_status()
        except httpx.HTTPError as e:
            fail(f"{cfg['label']} movie lookup failed: {e}")
        results = []
        for m in r.json():
            if not m.get("monitored") or m.get("hasFile") or not m.get("isAvailable"):
                continue
            released = m.get("digitalRelease") or m.get("physicalRelease") or m.get("inCinemas")
            results.append({"title": m.get("title"), "year": m.get("year"), "aired": released})
        results.sort(key=lambda x: x["aired"] or "", reverse=True)
        return results

    # Sonarr: paginate ascending by air date and stop as soon as a future
    # (unaired) episode is hit, rather than scanning the whole ~300k list -
    # everything after that point in ascending order is also future.
    cutoff = datetime.now(timezone.utc)
    results = []
    page = 1
    page_size = 250
    while True:
        try:
            r = httpx.get(
                f"{cfg['url']}/api/{cfg['api']}/wanted/missing",
                params={
                    "page": page,
                    "pageSize": page_size,
                    "sortKey": "airDateUtc",
                    "sortDirection": "ascending",
                    "includeSeries": "true",
                },
                headers={"X-Api-Key": cfg["key"]},
                timeout=30,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            fail(f"{cfg['label']} missing lookup failed: {e}")
        data = r.json()
        records = data.get("records", [])
        if not records:
            break
        hit_future = False
        for ep in records:
            air = parse_air_date(ep.get("airDateUtc"))
            if air is None:
                continue  # TBA - can't tell if it's aired, skip rather than guess
            if air > cutoff:
                hit_future = True
                break
            series = ep.get("series") or {}
            results.append({
                "series": series.get("title"),
                "episode": f"S{ep['seasonNumber']:02d}E{ep['episodeNumber']:02d}",
                "title": ep.get("title"),
                "aired": ep.get("airDateUtc"),
            })
        if hit_future or page * page_size >= data.get("totalRecords", 0):
            break
        page += 1
    results.sort(key=lambda x: x["aired"] or "", reverse=True)
    return results


# ---------------------------------------------------------------------
# Wanted/missing backlog ETA - a fundamentally different estimate from
# queue_status above: nothing here is mid-transfer, so there's no size to
# drain. Instead this measures throughput - how many items each app has
# actually finished importing recently - from its own /history, and
# projects that rate forward across the current missing count. Capped to
# a recent time window (RECENT_IMPORT_LOOKBACK_HOURS) so a backlog that
# was being chewed through fast an hour ago but has since stalled (e.g.
# an indexer rate-limit, see the WWE-batch incident) doesn't get credited
# with a pace it isn't currently keeping.
#
# RECENT_IMPORT_SAMPLE_SIZE and MIN_RATE_WINDOW_HOURS both guard against
# the same failure mode, confirmed live: a busy app clears its queue in
# bursts, not a steady drip - Sonarr once landed 23 imports within the
# same 6 seconds while working through a large backlog. The original
# 50-event sample could land entirely inside one such burst, and
# count/span with a near-zero span extrapolated to 13,800/hr - technically
# correct arithmetic on a meaningless denominator. A bigger sample dilutes
# any single burst with more real elapsed time; the floor on span_hours is
# the hard backstop for whatever a bigger sample doesn't dilute away.
# ---------------------------------------------------------------------
RECENT_IMPORT_LOOKBACK_HOURS = 6
RECENT_IMPORT_SAMPLE_SIZE = 200
MIN_RATE_WINDOW_HOURS = 0.25


def _wanted_missing_total(app_name: str) -> int:
    cfg = ARR_APPS[app_name]
    try:
        r = httpx.get(
            f"{cfg['url']}/api/{cfg['api']}/wanted/missing",
            params={"pageSize": 1},
            headers={"X-Api-Key": cfg["key"]},
            timeout=20,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} wanted/missing lookup failed: {e}")
    return r.json().get("totalRecords", 0)


def _recent_import_rate_per_hour(app_name: str) -> tuple[float, int]:
    """Returns (rate_per_hour, sample_count). Rate is 0 if there aren't at
    least 2 qualifying events, or the newest one is older than
    RECENT_IMPORT_LOOKBACK_HOURS - both mean "no current pace to report",
    not "instant" (that would be dividing by a near-zero time span)."""
    cfg = ARR_APPS[app_name]
    try:
        r = httpx.get(
            f"{cfg['url']}/api/{cfg['api']}/history",
            params={"pageSize": RECENT_IMPORT_SAMPLE_SIZE, "sortKey": "date", "sortDirection": "descending"},
            headers={"X-Api-Key": cfg["key"]},
            timeout=20,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} history lookup failed: {e}")
    records = r.json().get("records", [])
    events = [rec for rec in records if rec.get("eventType") in cfg["import_events"]]
    if len(events) < 2:
        return 0.0, len(events)
    newest = datetime.fromisoformat(events[0]["date"].replace("Z", "+00:00"))
    oldest = datetime.fromisoformat(events[-1]["date"].replace("Z", "+00:00"))
    if (datetime.now(timezone.utc) - newest).total_seconds() > RECENT_IMPORT_LOOKBACK_HOURS * 3600:
        return 0.0, len(events)
    span_hours = max((newest - oldest).total_seconds() / 3600, MIN_RATE_WINDOW_HOURS)
    return len(events) / span_hours, len(events)


@app.get("/api/backlog-status")
def backlog_status():
    """Every *arr app's wanted/missing count plus a throughput-projected
    ETA - see the module comment above for why this is rate-based instead
    of the size/speed math queue_status uses."""
    result = {}
    for app_name in QUEUE_ARR_APPS:
        cfg = ARR_APPS[app_name]
        try:
            missing = _wanted_missing_total(app_name)
            rate_per_hour, sample_count = _recent_import_rate_per_hour(app_name)
        except HTTPException:
            result[app_name] = {"label": cfg["label"], "error": "unreachable"}
            continue
        item = {
            "label": cfg["label"],
            "missing": missing,
            "recent_imports_sampled": sample_count,
            "rate_per_hour": round(rate_per_hour, 2),
        }
        if missing == 0:
            item["eta"] = "none - nothing missing"
        elif rate_per_hour > 0:
            item["eta"] = format_eta((missing / rate_per_hour) * 3600)
        else:
            item["eta"] = f"unknown - no imports in the last {RECENT_IMPORT_LOOKBACK_HOURS}h to measure a rate from"
        result[app_name] = item

    # Bazarr's missing count is real (movies + episodes still lacking a
    # subtitle), but there's no rate/ETA to project it forward with - its
    # history API only exposes a pre-formatted relative string ("3 hours
    # ago") for the timestamp field, not a parseable date like the arr
    # apps' own /history, so faking a rate off that would be guessing, not
    # measuring. Missing count alone is still a real, useful number.
    try:
        headers = _bazarr_headers()
        movies_wanted = httpx.get(f"{BAZARR_URL}/api/movies/wanted", headers=headers, params={"length": 1}, timeout=20)
        movies_wanted.raise_for_status()
        episodes_wanted = httpx.get(f"{BAZARR_URL}/api/episodes/wanted", headers=headers, params={"length": 1}, timeout=20)
        episodes_wanted.raise_for_status()
        missing = movies_wanted.json().get("total", 0) + episodes_wanted.json().get("total", 0)
        result["bazarr"] = {
            "label": "Bazarr",
            "missing": missing,
            "recent_imports_sampled": 0,
            "rate_per_hour": 0.0,
            "eta": "none - nothing missing" if missing == 0
                   else "unknown - Bazarr's history API has no parseable timestamp to measure a rate from",
        }
    except (HTTPException, httpx.HTTPError) as e:
        result["bazarr"] = {"label": "Bazarr", "error": str(e) if isinstance(e, httpx.HTTPError) else "unreachable"}

    total_missing = sum(v.get("missing", 0) for v in result.values())
    return ok(f"{total_missing} item(s) missing across {len(result)} apps.", apps=result)


# ---------------------------------------------------------------------
# Individual container control - start/stop/restart. Validated against the
# live set of containers in this compose project (project_containers()),
# never a hardcoded name list - see CONTAINER_LABELS' comment above for why.
# Self (this panel) is rejected for stop/restart: stopping the container
# serving the request that stops it just drops the connection with no
# useful confirmation, and there's no one-click way to start it back up
# from a page it just took down.
# ---------------------------------------------------------------------
def find_project_container(name: str, *, reject_self: bool):
    me, containers = project_containers()
    match = next((c for c in containers if c.name == name), None)
    if match is None:
        fail(f"'{name}' is not a container in this compose project.", status_code=404)
    if reject_self and match.id == me.id:
        fail("This panel can't stop or restart itself - use the host/systemd to do that.", status_code=400)
    return match


def container_label(name: str) -> str:
    return CONTAINER_LABELS.get(name, (name, None))[0]


@app.post("/api/container/{name}/restart")
def container_restart(name: str):
    c = find_project_container(name, reject_self=True)
    try:
        c.restart(timeout=30)
    except Exception as e:
        fail(f"Restart failed: {e}")
    return ok(f"{container_label(name)} restarted.")


@app.post("/api/container/{name}/stop")
def container_stop(name: str):
    c = find_project_container(name, reject_self=True)
    if c.status != "running":
        return ok(f"{container_label(name)} is already {c.status}.")
    try:
        c.stop(timeout=30)
    except Exception as e:
        fail(f"Stop failed: {e}")
    return ok(f"{container_label(name)} stopped.")


@app.post("/api/container/{name}/start")
def container_start(name: str):
    c = find_project_container(name, reject_self=False)
    if c.status == "running":
        return ok(f"{container_label(name)} is already running.")
    try:
        c.start()
    except Exception as e:
        fail(f"Start failed: {e}")
    return ok(f"{container_label(name)} started.")


@app.get("/api/container/{name}/logs/stream")
def container_logs_stream(name: str, tail: int = 100):
    """Live-follows a container's own docker logs as Server-Sent Events -
    the streaming counterpart to /api/arr/{app}/logs' one-shot tail, used
    for live feedback while a mutating action (restart, search, etc)
    against that same container is in flight. Works for any container in
    this compose project, not just the arr apps the older route covers."""
    c = find_project_container(name, reject_self=False)

    def generate():
        for line in c.logs(stream=True, follow=True, tail=tail):
            text = line.decode(errors="replace").rstrip("\n")
            for part in text.splitlines() or [""]:
                yield f"data: {part}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------
# Whole-stack restart
# ---------------------------------------------------------------------
# Every direct-subpath bind of /mnt/altmount (rslave) - Radarr, Sonarr,
# Plex, Unpackerr, Cleanuparr - doesn't survive the FUSE process underneath
# it being recreated; restarting the mount owner without restarting these
# after reproduces the same stale-mount bug this stack hit repeatedly under
# NzbDAV/nzbdav-rclone (see CLAUDE.md's History - NzbDAV was removed
# entirely 2026-07-23, replaced by AltMount). AltMount owns its own
# internal rclone/FUSE mount directly (no separate sidecar container the
# way nzbdav-rclone was), so there's only one tier here now - MOUNT_PREREQS
# is empty rather than removed outright, so this stays a two-phase
# provider/dependent restart if a future mount-owning service ever needs a
# real upstream prereq again. Restart the provider first, wait for it to
# report healthy, then restart the dependents last.
MOUNT_PREREQS: set[str] = set()
MOUNT_PROVIDERS = {"altmount"}
MOUNT_DEPENDENTS = {"radarr", "sonarr", "plex", "unpackerr", "cleanuparr"}


def wait_for_healthy(container, timeout=60):
    """Polls a container's own healthcheck status, if it has one. Containers
    with no healthcheck report no Health block at all - falls back to a
    flat sleep for those so the caller doesn't wait needlessly for a signal
    that will never come."""
    deadline = time.monotonic() + timeout
    saw_health_block = False
    while time.monotonic() < deadline:
        try:
            container.reload()
            status = container.attrs.get("State", {}).get("Health", {}).get("Status")
        except Exception:
            status = None
        if status:
            saw_health_block = True
            if status == "healthy":
                return
        time.sleep(2)
    if not saw_health_block:
        time.sleep(10)


@app.post("/api/stack/restart-all")
def stack_restart_all():
    me, containers = project_containers()
    # Excludes itself - restarting the panel mid-request would just drop the
    # connection instead of confirming the sweep actually started.
    targets = [c for c in containers if c.id != me.id]
    if not targets:
        fail("No other containers found in this compose project.")
    names = sorted(c.name for c in targets)

    prereqs = [c for c in targets if c.name in MOUNT_PREREQS]
    providers = [c for c in targets if c.name in MOUNT_PROVIDERS]
    dependents = [c for c in targets if c.name in MOUNT_DEPENDENTS]
    staged = MOUNT_PREREQS | MOUNT_PROVIDERS | MOUNT_DEPENDENTS
    rest = [c for c in targets if c.name not in staged]

    def worker():
        for c in prereqs:
            try:
                c.restart(timeout=30)
            except Exception as e:
                print(f"restart-all: failed to restart {c.name}: {e}")
        for c in prereqs:
            wait_for_healthy(c)
        for c in providers:
            try:
                c.restart(timeout=30)
            except Exception as e:
                print(f"restart-all: failed to restart {c.name}: {e}")
        for c in providers:
            wait_for_healthy(c)
        for c in rest:
            try:
                c.restart(timeout=30)
            except Exception as e:
                print(f"restart-all: failed to restart {c.name}: {e}")
        # Dependents restart last, and only after their mount providers are
        # back - restarting them any earlier reproduces the stale-mount bug.
        for c in dependents:
            try:
                c.restart(timeout=30)
            except Exception as e:
                print(f"restart-all: failed to restart {c.name}: {e}")

    threading.Thread(target=worker, daemon=True).start()
    return ok(f"Restarting {len(names)} containers (everything except this panel): {', '.join(names)}")


# ---------------------------------------------------------------------
# Diagnostic/audit endpoints - added after a live resource+wiring audit
# found real, previously-invisible gaps (10 containers with no mem_limit,
# 5 apps stuck on debug logging, a Zurg group_order bug, Cleanuparr missing
# two arr_instances). Each of these turns one of those manual investigation
# steps into a real endpoint instead of a one-off curl/sqlite3 session.
# ---------------------------------------------------------------------

@app.get("/api/resource-check")
def resource_check():
    """Every container missing mem_limit or cpus - the exact gap a live
    audit found for 10 services (docker stats silently reporting the full
    host memory as their ceiling instead of a real number)."""
    me, containers = project_containers()
    missing = []
    for c in containers:
        if c.id == me.id:
            continue
        host_config = c.attrs.get("HostConfig", {})
        mem_limit = host_config.get("Memory") or 0
        nano_cpus = host_config.get("NanoCpus") or 0
        if mem_limit == 0 or nano_cpus == 0:
            missing.append({
                "name": c.name,
                "mem_limit_set": mem_limit != 0,
                "cpus_set": nano_cpus != 0,
                **container_stats(c),
            })
    if not missing:
        return ok("Every container has both mem_limit and cpus set.", containers=[])
    return ok(f"{len(missing)} container(s) missing mem_limit and/or cpus.", containers=missing)


LOG_LEVEL_APPS = {
    "radarr": ARR_APPS["radarr"],
    "sonarr": ARR_APPS["sonarr"],
    "prowlarr": {"url": "http://prowlarr:9696", "api": "v1", "key": PROWLARR_API_KEY, "label": "Prowlarr"},
}


@app.get("/api/log-levels")
def log_levels():
    """Current logLevel for every Servarr-shaped app - debug left on in
    production was a real, invisible-until-checked finding this session
    (100MB+ log directories on 5 apps, likely months old)."""
    out = {}
    for name, cfg in LOG_LEVEL_APPS.items():
        try:
            r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/config/host", headers={"X-Api-Key": cfg["key"]}, timeout=10)
            r.raise_for_status()
            out[name] = r.json().get("logLevel")
        except Exception as e:
            out[name] = f"error: {e}"
    debug_apps = [n for n, lvl in out.items() if lvl == "debug"]
    msg = f"{len(debug_apps)} app(s) at debug: {', '.join(debug_apps)}" if debug_apps else "All apps at info (or non-debug)."
    return ok(msg, levels=out)


@app.post("/api/log-levels/reset")
def log_levels_reset():
    """Sets logLevel back to 'info' on every app currently at 'debug'."""
    reset = []
    for name, cfg in LOG_LEVEL_APPS.items():
        try:
            r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/config/host", headers={"X-Api-Key": cfg["key"]}, timeout=10)
            r.raise_for_status()
            current = r.json()
            if current.get("logLevel") != "debug":
                continue
            current["logLevel"] = "info"
            httpx.put(
                f"{cfg['url']}/api/{cfg['api']}/config/host/{current['id']}",
                headers={"X-Api-Key": cfg["key"], "Content-Type": "application/json"},
                json=current,
                timeout=10,
            ).raise_for_status()
            reset.append(name)
        except Exception as e:
            print(f"log-levels-reset: failed for {name}: {e}")
    if not reset:
        return ok("Nothing to reset - no app was at debug.")
    return ok(f"Reset {len(reset)} app(s) to info: {', '.join(reset)}")


@app.get("/api/oom-check")
def oom_check():
    """Containers Docker itself has ever recorded an OOM kill for
    (State.OOMKilled) - the NeutArr finding (15 kills in one overnight
    window, invisible on the dashboard since restart:unless-stopped
    self-heals every time) came from journalctl, but Docker tracks this
    per-container without needing host journal access at all."""
    me, containers = project_containers()
    killed = [c.name for c in containers if c.id != me.id and c.attrs.get("State", {}).get("OOMKilled")]
    if not killed:
        return ok("No container currently shows an OOM-kill flag.", containers=[])
    return ok(
        f"{len(killed)} container(s) have been OOM-killed at least once (flag persists until next "
        f"recreate, not necessarily still happening): {', '.join(killed)}",
        containers=killed,
    )


@app.get("/api/disk-usage")
def disk_usage():
    """Per-app config/ directory size - would have caught Stash's
    cache/generated growth (or any future app's) before it became a
    backup-bloat problem, instead of after."""
    if not os.path.isdir(HOST_CONFIG_DIR):
        fail(f"{HOST_CONFIG_DIR} not mounted.")
    sizes = []
    for entry in sorted(os.listdir(HOST_CONFIG_DIR)):
        path = os.path.join(HOST_CONFIG_DIR, entry)
        if not os.path.isdir(path):
            continue
        total = 0
        # Two real bugs found getting this right, live (both against the
        # since-removed Decypharr's config dir, which held symlinks into a
        # multi-TB debrid FUSE mount - the exact scenario that exposed
        # them, kept here since the fix is still generically correct):
        # 1. followlinks=False keeps os.walk from descending into a
        #    symlinked subdirectory, but os.path.getsize() on a file
        #    that's *itself* a symlink still follows it - resolving and
        #    summing a debrid mount's real (TB-scale) size, reporting a
        #    349GB "config directory".
        # 2. Switching to os.lstat().st_size fixed that, but a FUSE cache
        #    using sparse/preallocated files still reported 152GB against a
        #    real (`du`-confirmed) 11GB - st_size is a file's *logical*
        #    size, not actual disk consumption. st_blocks (512-byte units,
        #    matching `du`'s own accounting) is what actually answers "how
        #    much disk does this use."
        for dirpath, _, filenames in os.walk(path, followlinks=False):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.lstat(fp).st_blocks * 512
                except OSError:
                    pass
        sizes.append({"app": entry, "mb": round(total / 1024 / 1024, 1)})
    sizes.sort(key=lambda x: x["mb"], reverse=True)
    return ok(f"{len(sizes)} app config directories.", sizes=sizes)


KNOWN_MOUNTS = ["altmount"]


@app.get("/api/mount-health")
def mount_health():
    """Every known FUSE mountpoint under /mnt, checked for a clean listing -
    catches a stale mount (registered but dead backing process) before it
    causes the cascade failure documented in README's mount-cascade section."""
    results = []
    for name in KNOWN_MOUNTS:
        path = os.path.join(HOST_MNT_DIR, name)
        entry = {"mount": name, "path": path}
        if not os.path.exists(path):
            entry["status"] = "missing"
        else:
            try:
                os.listdir(path)
                entry["status"] = "healthy"
            except OSError as e:
                entry["status"] = f"stale: {e}"
        results.append(entry)
    unhealthy = [r for r in results if r["status"] != "healthy"]
    if not unhealthy:
        return ok("All known mounts resolve cleanly.", mounts=results)
    return ok(f"{len(unhealthy)} mount(s) not healthy: {', '.join(r['mount'] for r in unhealthy)}", mounts=results)


@app.get("/api/perms-check")
def perms_check():
    """Config files that are root-owned and unreadable by group/other - the
    exact class of bug that left Stash's config.yml (mode 640) out of every
    backup run despite the backup script having no error handling that
    would have surfaced it. Doesn't need to actually run as that user to
    check this - just inspects the mode bits directly."""
    if not os.path.isdir(HOST_CONFIG_DIR):
        fail(f"{HOST_CONFIG_DIR} not mounted.")
    unreadable = []
    # followlinks=False + lstat, same reasoning as disk_usage() above -
    # a symlink into a FUSE mount; stat() would follow it (slow, and
    # checking the wrong file's permissions entirely - what matters here
    # is the symlink itself, not whatever it happens to point at).
    for dirpath, _, filenames in os.walk(HOST_CONFIG_DIR, followlinks=False):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                mode = os.lstat(fp).st_mode
            except OSError:
                continue
            # No group or other read bit at all.
            if not (mode & 0o044):
                unreadable.append(fp.replace(HOST_CONFIG_DIR, "config", 1))
    if not unreadable:
        return ok("No config files found unreadable by group/other.", files=[])
    return ok(f"{len(unreadable)} file(s) unreadable by group/other (won't be backed up):", files=unreadable[:200])


@app.get("/api/image-check")
def image_check():
    """For every running container's image, queries the registry directly
    (no pull) for whether a newer digest exists under the same tag - the
    digest/exact-version-pinned tier Watchtower never touches on its own.
    Registry queries can be slow/rate-limited, so this is opt-in, not part
    of the container grid's own 15s poll."""
    me, containers = project_containers()
    results = []
    for c in containers:
        if c.id == me.id:
            continue
        image_tags = c.image.tags
        if not image_tags:
            continue
        tag_ref = image_tags[0]
        current_digests = set(c.image.attrs.get("RepoDigests", []))
        try:
            registry_data = docker_client.images.get_registry_data(tag_ref)
            remote_digest = registry_data.attrs.get("Descriptor", {}).get("digest")
            has_update = bool(remote_digest) and not any(remote_digest in d for d in current_digests)
            results.append({"name": c.name, "image": tag_ref, "update_available": has_update})
        except Exception as e:
            results.append({"name": c.name, "image": tag_ref, "update_available": None, "error": str(e)})
    updates = [r["name"] for r in results if r.get("update_available")]
    msg = f"{len(updates)} image(s) with a newer digest available: {', '.join(updates)}" if updates else \
          "No newer digests found for any currently-pinned tag (or all checks failed - see errors)."
    return ok(msg, images=results)


def _restic(repo_path: str, args: list, text: bool = True, timeout: int = 60) -> subprocess.CompletedProcess:
    """Both repos are mounted read-only into this container - deliberately,
    there's no legitimate reason Control Panel needs write access to a
    backup repo. restic still tries to take a lock file for most commands,
    including read-only ones, which fails against a read-only mount and
    retries for a full minute before giving up (confirmed live: every call
    here failed with "read-only file system" on the lock, not an actual
    repo problem). --no-lock is correct for every use in this file - none
    of them write anything - so this fixes it without loosening the mount.
    text=False for `dump`: it streams a file's raw bytes to stdout, and
    forcing UTF-8 decoding on that (the default here otherwise) throws
    UnicodeDecodeError on the first binary file it happens to hit -
    confirmed live against a real MediaCover image."""
    env = dict(os.environ)
    env["RESTIC_REPOSITORY"] = repo_path
    env["RESTIC_PASSWORD_FILE"] = HOST_RESTIC_PASSWORD_FILE
    return subprocess.run(["restic", "--no-lock", *args], env=env, capture_output=True, text=text, timeout=timeout)


@app.get("/api/backup-verify")
def backup_verify():
    """Latest snapshot age for both the local and off-site restic repos -
    the check that would have caught the off-site leg silently not existing
    before this session's audit found it the hard way (a real overnight
    tar-backup failure, discovered only by chance)."""
    repos = {"local": HOST_BACKUP_LOCAL, "offsite": HOST_BACKUP_OFFSITE}
    out = {}
    for name, path in repos.items():
        if not os.path.isdir(path):
            out[name] = {"status": "missing", "path": path}
            continue
        try:
            r = _restic(path, ["snapshots", "--json", "--latest", "1"])
            if r.returncode != 0:
                out[name] = {"status": "error", "detail": r.stderr.strip()[:300]}
                continue
            import json as _json
            snaps = _json.loads(r.stdout or "[]")
            if not snaps:
                out[name] = {"status": "empty", "path": path}
                continue
            out[name] = {"status": "ok", "time": snaps[0].get("time"), "id": snaps[0].get("short_id")}
        except Exception as e:
            out[name] = {"status": "error", "detail": str(e)}
    problems = [n for n, v in out.items() if v.get("status") != "ok"]
    msg = "Both repos have a recent snapshot." if not problems else f"Problem with: {', '.join(problems)}"
    return ok(msg, repos=out)


@app.post("/api/backup-restore-test")
def backup_restore_test():
    """Pulls one small file out of the latest local snapshot into a scratch
    path inside the container and confirms it's actually readable - this
    stack has verified backups complete successfully many times, but never
    that a restore actually works, until now."""
    if not os.path.isdir(HOST_BACKUP_LOCAL):
        fail(f"{HOST_BACKUP_LOCAL} not present.")
    try:
        r = _restic(HOST_BACKUP_LOCAL, ["ls", "latest", "--json"])
        if r.returncode != 0:
            fail(f"restic ls failed: {r.stderr.strip()[:300]}")
        import json as _json
        candidate = None
        for line in r.stdout.splitlines():
            try:
                entry = _json.loads(line)
            except ValueError:
                continue
            if entry.get("type") == "file" and 0 < entry.get("size", 0) < 1_000_000:
                candidate = entry.get("path")
                break
        if not candidate:
            fail("No small file found in the latest snapshot to test-restore.")
        dump = _restic(HOST_BACKUP_LOCAL, ["dump", "latest", candidate], text=False)
        if dump.returncode != 0:
            fail(f"restic dump failed for {candidate}: {dump.stderr.decode(errors='replace').strip()[:300]}")
        return ok(f"Restore test passed: '{candidate}' ({len(dump.stdout)} bytes) dumped and read successfully.")
    except subprocess.TimeoutExpired:
        fail("restic operation timed out.")


@app.get("/api/cleanuparr/instances")
def cleanuparr_instances():
    """Which *arr apps Cleanuparr actually has a connected arr_instance for,
    vs. just an arr_configs type placeholder - the exact gap that historically
    left Lidarr and Whisparr (both since removed) completely uncovered by
    queue-cleaning/strikes despite both apps being fully functional at the time."""
    db_path = os.path.join(HOST_CONFIG_DIR, "cleanuparr", "cleanuparr.db")
    if not os.path.isfile(db_path):
        fail(f"{db_path} not present.")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT type FROM arr_configs")
    configured_types = {row["type"] for row in cur.fetchall()}
    cur.execute("SELECT name FROM arr_instances")
    connected = {row["name"].lower() for row in cur.fetchall()}
    con.close()
    gaps = sorted(t for t in configured_types if t not in connected and t != "readarr")
    if not gaps:
        return ok("Every configured app type has a connected instance.", connected=sorted(connected))
    return ok(f"{len(gaps)} app(s) have a config placeholder but no connected instance: {', '.join(gaps)}",
              connected=sorted(connected), gaps=gaps)


@app.get("/api/neutarr/status")
def neutarr_status():
    """Per-app enabled/disabled state straight from NeutArr's own JSON
    config files - the same place the orphaned whisparr.json (blank
    creds, enabled:true, never actually read) was found."""
    neutarr_dir = os.path.join(HOST_CONFIG_DIR, "neutarr")
    if not os.path.isdir(neutarr_dir):
        fail(f"{neutarr_dir} not present.")
    apps = {}
    for fname in os.listdir(neutarr_dir):
        if not fname.endswith(".json") or fname in ("general.json", "swaparr.json", "users.json"):
            continue
        try:
            with open(os.path.join(neutarr_dir, fname)) as f:
                import json as _json
                cfg = _json.load(f)
            instances = cfg.get("instances", [])
            apps[fname[:-5]] = {
                "enabled": any(i.get("enabled") for i in instances),
                "has_credentials": any(i.get("api_url") and i.get("api_key") for i in instances),
            }
        except Exception as e:
            apps[fname[:-5]] = {"error": str(e)}
    return ok(f"{len(apps)} app config file(s) found in config/neutarr.", apps=apps)


ARR_LOG_CONTAINERS = {"radarr", "sonarr", "prowlarr"}


@app.get("/api/arr/{app_name}/logs")
def arr_logs(app_name: str, lines: int = 100):
    """Tails a container's own docker logs directly for a one-off check."""
    if app_name not in ARR_LOG_CONTAINERS:
        fail(f"Unknown app '{app_name}' - use one of: {', '.join(sorted(ARR_LOG_CONTAINERS))}", status_code=400)
    try:
        c = docker_client.containers.get(app_name)
        raw = c.logs(tail=min(lines, 1000)).decode(errors="replace")
        return ok(f"Last {lines} line(s) from {app_name}.", log=raw)
    except docker.errors.NotFound:
        fail(f"Container '{app_name}' not found.")


@app.get("/api/version")
def version():
    """Current version from README's own declared line, plus a live
    core/extras container count - a quick doc-vs-reality drift check."""
    declared = "unknown"
    if os.path.isfile(HOST_README):
        with open(HOST_README) as f:
            for line in f:
                m = re.match(r"Current version: \*\*(v[\d.]+)\*\*", line)
                if m:
                    declared = m.group(1)
                    break
    me, containers = project_containers()
    running = sum(1 for c in containers if c.status == "running")
    total = len(containers)
    return ok(f"README declares {declared}. {running}/{total} containers currently running.",
              version=declared, running=running, total=total)


# ---------------------------------------------------------------------
# 20 new diagnostic/read endpoints, added in one pass to back a matching
# set of new stack-* fish commands. Each follows an existing pattern in
# this file rather than inventing a new one - see the comment on each for
# which.
# ---------------------------------------------------------------------


@app.get("/api/arr/command-queue-summary")
def arr_command_queue_summary():
    """Same idea as arr_command_backlog() above, but across every *arr app
    at once instead of one at a time - built after a real session where
    the answer to "why haven't my new shows been processed" turned out to
    be a 775-command backlog that took manually querying Sonarr alone to
    find; this is that query, generalized to all four apps in one call."""
    out = {}
    for name, cfg in {**ARR_APPS, "prowlarr": {
        "url": "http://prowlarr:9696", "api": "v1", "key": PROWLARR_API_KEY, "label": "Prowlarr",
    }}.items():
        try:
            r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/command", headers={"X-Api-Key": cfg["key"]}, timeout=20)
            r.raise_for_status()
            commands = r.json()
            counts = Counter(c.get("status") for c in commands)
            out[name] = {"total": len(commands), "queued": counts.get("queued", 0), "running": counts.get("started", 0)}
        except httpx.HTTPError as e:
            out[name] = {"error": str(e)}
    total_queued = sum(v.get("queued", 0) for v in out.values() if "error" not in v)
    return ok(f"{total_queued} commands queued across {len(out)} apps.", apps=out)


@app.get("/api/arr/{app_name}/recently-added")
def arr_recently_added(app_name: str, limit: int = 10):
    """Radarr/Sonarr's own "added" timestamp, sorted newest-first - the
    exact query that answered a real "why haven't my shows been processed"
    session by showing which shows were added seconds vs hours apart and
    still had null episode statistics (never even refreshed yet)."""
    if app_name not in ("radarr", "sonarr"):
        fail("Only radarr and sonarr have an 'added' concept here.", status_code=400)
    cfg = ARR_APPS[app_name]
    path = "/api/v3/movie" if app_name == "radarr" else "/api/v3/series"
    try:
        r = httpx.get(f"{cfg['url']}{path}", headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} lookup failed: {e}")
    items = sorted(r.json(), key=lambda i: i.get("added") or "", reverse=True)[:limit]
    out = []
    for i in items:
        stats = i.get("statistics") or {}
        out.append({
            "title": i.get("title"),
            "added": i.get("added"),
            "monitored": i.get("monitored"),
            "file_count": stats.get("movieFileCount") if app_name == "radarr" else stats.get("episodeFileCount"),
            "total_count": None if app_name == "radarr" else stats.get("episodeCount"),
        })
    return ok(f"{len(out)} most recently added to {cfg['label']}.", items=out)


@app.get("/api/plex/duplicates")
def plex_duplicates(min_gb: float = 5.0):
    """Scans every movie library for items whose combined file size looks
    like more than one real release stacked up - the exact shape of a real
    session where three movies turned out to be carrying 200-300GB each
    across 3-7 redundant UHD remuxes of the same film. Flags anything
    whose total size is more than 1.5x its single largest file - a movie
    with one real multi-version upgrade (2-3 files) rarely trips this;
    the genuine duplicate cases were 5-10x their largest file."""
    try:
        sections = plex_sections()
    except httpx.HTTPError as e:
        fail(f"Could not read Plex libraries: {e}")
    movie_sections = [s for s in sections if s.get("type") == "movie"]
    flagged = []
    for s in movie_sections:
        try:
            r = httpx.get(f"{PLEX_URL}/library/sections/{s['key']}/all", headers=plex_headers(), timeout=30)
            r.raise_for_status()
        except httpx.HTTPError:
            continue
        for v in r.json().get("MediaContainer", {}).get("Metadata", []):
            # De-duped by exact byte size first - a library with more than
            # one configured root path can have a single real file show up
            # as two "Media" entries with identical sizes. Real duplicates
            # are near-impossible to collide on exact byte size by
            # accident; that's the whole signal this endpoint relies on.
            sizes = list({int(p.get("size") or 0) for m in v.get("Media", []) for p in m.get("Part", [])})
            if len(sizes) < 2:
                continue
            total = sum(sizes)
            largest = max(sizes)
            if total < min_gb * 1e9 or total < largest * 1.5:
                continue
            flagged.append({
                "title": v.get("title"), "year": v.get("year"), "ratingKey": v.get("ratingKey"),
                "file_count": len(sizes), "total_gb": round(total / 1e9, 1), "largest_gb": round(largest / 1e9, 1),
            })
    flagged.sort(key=lambda f: f["total_gb"], reverse=True)
    return ok(f"{len(flagged)} movie(s) look like they're carrying redundant duplicate files.", items=flagged)


TMDB_LEGACY_GUID_RE = re.compile(r"com\.plexapp\.agents\.themoviedb://")


@app.get("/api/plex/tmdb-missing")
def plex_tmdb_missing():
    """Every movie/show (top-level, not episodes) across every library with
    no TMDb link - neither the new agent's tmdb:// Guid nor the legacy
    com.plexapp.agents.themoviedb:// agent id. Read-only, matches the
    checks in scripts/audit-tmdb-links.py but against all movie/show
    libraries at once instead of one named library.

    Uses includeGuids=1 on the section listing itself (confirmed live to
    carry the full Guid array) rather than a per-item metadata call -
    the poster-sync code above needs a per-item fetch because it wants
    write-time-fresh data, this only needs the Guid list, so one request
    per library covers a few thousand items instead of one request each."""
    try:
        sections = plex_sections()
    except httpx.HTTPError as e:
        fail(f"Could not read Plex libraries: {e}")
    targets = [s for s in sections if s.get("type") in ("movie", "show")]

    missing = []
    for s in targets:
        try:
            r = httpx.get(
                f"{PLEX_URL}/library/sections/{s['key']}/all?includeGuids=1&X-Plex-Container-Size=200000",
                headers=plex_headers(), timeout=60,
            )
            r.raise_for_status()
        except httpx.HTTPError:
            continue
        for item in r.json()["MediaContainer"].get("Metadata", []):
            has_tmdb = any(g.get("id", "").startswith("tmdb://") for g in item.get("Guid", []))
            if not has_tmdb and TMDB_LEGACY_GUID_RE.search(item.get("guid") or ""):
                has_tmdb = True
            if has_tmdb:
                continue
            missing.append({
                "library": s["title"], "title": item.get("title"), "year": item.get("year"),
                "ratingKey": item.get("ratingKey"),
            })
    return ok(f"{len(missing)} item(s) missing a TMDb link.", items=missing)


@app.get("/api/prowlarr/indexers")
def prowlarr_indexers():
    """Every configured indexer's enabled/priority state in one place -
    Prowlarr's own UI is the only other place to see this without
    hitting the API directly."""
    if not PROWLARR_API_KEY:
        fail("PROWLARR_API_KEY not set.", status_code=503)
    try:
        r = httpx.get("http://prowlarr:9696/api/v1/indexer", headers={"X-Api-Key": PROWLARR_API_KEY}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Prowlarr lookup failed: {e}")
    items = [{"name": i.get("name"), "enabled": i.get("enable"), "priority": i.get("priority")} for i in r.json()]
    items.sort(key=lambda i: i["name"] or "")
    enabled = sum(1 for i in items if i["enabled"])
    return ok(f"{enabled}/{len(items)} indexers enabled.", items=items)


@app.get("/api/plex/sessions")
def plex_sessions():
    """Who's watching what right now, direct play vs transcode - Plex's
    own /status/sessions, not proxied through Tautulli (which only sees
    what it's been running long enough to have logged)."""
    try:
        r = httpx.get(f"{PLEX_URL}/status/sessions", headers=plex_headers(), timeout=10)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Could not read Plex sessions: {e}")
    sessions = []
    for v in r.json().get("MediaContainer", {}).get("Metadata", []):
        user = v.get("User") or {}
        player = v.get("Player") or {}
        media = (v.get("Media") or [{}])[0]
        title = f"{v['grandparentTitle']} - {v['title']}" if v.get("grandparentTitle") else v.get("title")
        duration = int(v.get("duration") or 1)
        sessions.append({
            "title": title,
            "user": user.get("title"),
            "player": player.get("product"),
            "state": player.get("state"),
            "decision": media.get("videoDecision") or media.get("selected"),
            "progress_pct": round(int(v.get("viewOffset") or 0) / max(duration, 1) * 100, 1),
        })
    return ok(f"{len(sessions)} active session(s).", sessions=sessions)


@app.get("/api/seerr/requests")
def seerr_requests(status: str = "pending"):
    """Pending (or any-status) media requests sitting in Seerr - the queue
    a user expects Radarr/Sonarr to eventually pick up automatically, so
    this is mostly useful for confirming a request actually landed there
    before chasing why it's not showing up downstream."""
    key = _seerr_key()
    if not key:
        fail("Could not read Seerr's API key from config/seerr/settings.json.", status_code=503)
    try:
        r = httpx.get(f"{SEERR_URL}/api/v1/request", params={"filter": status, "take": 25},
                       headers={"X-Api-Key": key}, timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Seerr lookup failed: {e}")
    data = r.json()
    items = [{
        # Seerr's own /api/v1/request response has no title field on its
        # embedded media object at all (confirmed live) - externalServiceSlug
        # (Radarr/Sonarr's own URL-safe slug, e.g. "the-ambiguously-gay-duo")
        # is the only human-readable thing available without a second
        # per-item API call to /api/v1/media/{id} or TMDB directly.
        "title": (req.get("media") or {}).get("externalServiceSlug")
                 or f"tmdb:{(req.get('media') or {}).get('tmdbId')}",
        "type": (req.get("media") or {}).get("mediaType"),
        "requestedBy": (req.get("requestedBy") or {}).get("displayName"),
        "status": req.get("status"),
        "createdAt": req.get("createdAt"),
    } for req in data.get("results", [])]
    return ok(f"{len(items)} {status} request(s) in Seerr.", items=items)


@app.get("/api/cleanuparr/strikes")
def cleanuparr_strikes(limit: int = 15):
    """Recent strikes Cleanuparr has issued (stalled/slow/malware) - lives
    in events.db, a separate SQLite file from the arr_instances/arr_configs
    one cleanuparr_instances() above reads, discovered while wiring this up
    (Cleanuparr splits its own state across cleanuparr.db and events.db)."""
    db_path = os.path.join(HOST_CONFIG_DIR, "cleanuparr", "events.db")
    if not os.path.isfile(db_path):
        fail(f"{db_path} not present.")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        "SELECT s.created_at, s.type, d.title FROM strikes s "
        "JOIN download_items d ON d.id = s.download_item_id "
        "ORDER BY s.created_at DESC LIMIT ?", (limit,)
    )
    rows = [{"created_at": r["created_at"], "type": r["type"], "title": r["title"]} for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) FROM strikes")
    total = cur.fetchone()[0]
    con.close()
    return ok(f"{total} strike(s) total, showing {len(rows)} most recent.", items=rows, total=total)


@app.get("/api/tautulli/history")
def tautulli_history(limit: int = 10):
    """Recent Plex watch history via Tautulli - what actually got watched,
    not just what's in the library. Tautulli's own API key, read live from
    its config.ini (see _tautulli_key() above)."""
    key = _tautulli_key()
    if not key:
        fail("Could not read Tautulli's API key from config/tautulli/config.ini.", status_code=503)
    try:
        r = httpx.get(f"{TAUTULLI_URL}/api/v2", params={"apikey": key, "cmd": "get_history", "length": limit},
                       timeout=15)
        r.raise_for_status()
        data = r.json()["response"]["data"]
    except (httpx.HTTPError, KeyError) as e:
        fail(f"Tautulli lookup failed: {e}")
    items = [{"title": h.get("full_title"), "user": h.get("user"), "date": h.get("date"),
              "percent_complete": h.get("percent_complete")} for h in data.get("data", [])]
    return ok(f"{len(items)} recent watch(es).", items=items)


@app.get("/api/arr/queue-errors")
def arr_queue_errors():
    """Only the queue items an arr app has already flagged as a problem
    itself (trackedDownloadStatus warning/error) across every queue-having
    app at once - a quick triage view instead of scrolling the full queue
    grid in each app's own UI looking for the handful that are stuck."""
    out = {}
    for app_name in QUEUE_ARR_APPS:
        try:
            queue = arr_queue(app_name)
        except HTTPException:
            out[app_name] = {"error": "lookup failed"}
            continue
        errors = [{
            "title": q.get("title"),
            "status": q.get("trackedDownloadStatus"),
            "messages": [m.get("title") for m in (q.get("statusMessages") or [])],
        } for q in queue if (q.get("trackedDownloadStatus") or "ok").lower() != "ok"]
        out[app_name] = errors
    total = sum(len(v) for v in out.values() if isinstance(v, list))
    return ok(f"{total} queue item(s) flagged with an error/warning across {len(out)} apps.", apps=out)


@app.post("/api/notify/test")
def notify_test():
    """Sends a real test message through the same Discord webhook every
    backup/health-check alert in this stack already uses - confirms the
    webhook itself still works without waiting for a real failure to find
    out it doesn't."""
    if not DISCORD_WEBHOOK_URL:
        fail("DISCORD_WEBHOOK_URL not set.", status_code=503)
    try:
        r = httpx.post(DISCORD_WEBHOOK_URL, json={"content": f"Control Panel test notification - {now()}"}, timeout=10)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Discord webhook test failed: {e}")
    return ok("Test notification sent to Discord.")


@app.get("/api/backup-status")
def backup_status():
    """Full snapshot history (not just the latest, see backup_verify()
    above) for both restic repos - count and oldest/newest timestamps, to
    catch a repo that's accumulating snapshots but silently stopped
    pruning, or one that only ever had a single snapshot ever taken."""
    import json as _json
    repos = {"local": HOST_BACKUP_LOCAL, "offsite": HOST_BACKUP_OFFSITE}
    out = {}
    for name, path in repos.items():
        if not os.path.isdir(path):
            out[name] = {"status": "missing", "path": path}
            continue
        try:
            r = _restic(path, ["snapshots", "--json"])
            if r.returncode != 0:
                out[name] = {"status": "error", "detail": r.stderr.strip()[:300]}
                continue
            snaps = _json.loads(r.stdout or "[]")
            if not snaps:
                out[name] = {"status": "empty", "count": 0}
                continue
            times = sorted(s["time"] for s in snaps)
            out[name] = {"status": "ok", "count": len(snaps), "oldest": times[0], "newest": times[-1]}
        except Exception as e:
            out[name] = {"status": "error", "detail": str(e)[:300]}
    return ok("Backup repo snapshot history.", repos=out)


@app.get("/api/top")
def stack_top(by: str = "cpu", limit: int = 10):
    """Top containers by CPU or memory in one compact list - the same data
    the container grid already shows per-card, sorted and truncated so a
    quick "what's using resources right now" doesn't mean scanning 30
    cards by eye."""
    if by not in ("cpu", "mem"):
        fail("'by' must be 'cpu' or 'mem'.", status_code=400)
    me, containers = project_containers()
    rows = []
    for c in containers:
        if c.id == me.id or c.status != "running":
            continue
        stats = container_stats(c)
        rows.append({
            "name": c.name,
            "cpu_percent": stats["cpu_percent"],
            "mem_percent": stats["mem_percent"],
            "mem_used_mb": stats["mem_used_mb"],
        })
    key = "cpu_percent" if by == "cpu" else "mem_percent"
    rows = [r for r in rows if r[key] is not None]
    rows.sort(key=lambda r: r[key], reverse=True)
    return ok(f"Top {min(limit, len(rows))} containers by {by}.", items=rows[:limit])


@app.get("/api/arr/{app_name}/cutoff-unmet")
def arr_cutoff_unmet(app_name: str, limit: int = 20):
    """Items below their quality profile's cutoff - already have a file,
    just not yet the target quality, so Radarr/Sonarr will keep
    upgrade-searching for these. Distinct from missing-aired/wanted
    (which is about having zero file at all)."""
    if app_name not in ("radarr", "sonarr"):
        fail("Only radarr and sonarr have quality cutoffs.", status_code=400)
    cfg = ARR_APPS[app_name]
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/wanted/cutoff",
                       params={"pageSize": limit, "sortKey": "title"},
                       headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} lookup failed: {e}")
    data = r.json()
    items = [{"title": rec.get("title") or rec.get("series", {}).get("title")} for rec in data.get("records", [])]
    return ok(f"{data.get('totalRecords', len(items))} item(s) below quality cutoff in {cfg['label']}.",
              items=items, total=data.get("totalRecords"))


@app.get("/api/arr/{app_name}/import-lists")
def arr_import_lists(app_name: str):
    """Configured import lists (e.g. Trakt lists, other *arr instances)
    and whether each is currently enabled - a quick check for "is this
    list actually still syncing" without opening Settings -> Import Lists."""
    if app_name not in ("radarr", "sonarr"):
        fail("Only radarr and sonarr have import lists.", status_code=400)
    cfg = ARR_APPS[app_name]
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/importlist", headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} lookup failed: {e}")
    items = [{"name": lst.get("name"), "enabled": lst.get("enabled"), "enableAutomaticAdd": lst.get("enableAutomaticAdd")}
             for lst in r.json()]
    return ok(f"{len(items)} import list(s) configured for {cfg['label']}.", items=items)


@app.get("/api/arr/{app_name}/import-list/implementations")
def arr_import_list_implementations(app_name: str):
    """Every import-list type Radarr/Sonarr's own build supports, whether
    configured here or not - a discovery aid for `import-list/add` below,
    since the useful ones (Simkl, TMDb Company/Keyword/User, Plex, Custom)
    are easy to miss without reading each app's Settings -> Import Lists
    schema directly."""
    if app_name not in ("radarr", "sonarr"):
        fail("Only radarr and sonarr have import lists.", status_code=400)
    cfg = ARR_APPS[app_name]
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/importlist/schema", headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} lookup failed: {e}")
    items = sorted({s["implementation"]: s.get("implementationName", s["implementation"]) for s in r.json()}.items())
    return ok(f"{len(items)} import-list implementation(s) available on {cfg['label']}.",
              items=[{"implementation": k, "name": v} for k, v in items])


@app.post("/api/arr/{app_name}/import-list/add")
def arr_import_list_add(app_name: str, payload: ImportListAddRequest):
    """Generic import-list creator - wraps whichever native implementation
    the caller names (e.g. PlexImport, SimklUserImport, TMDbCompanyImport,
    TMDbKeywordImport, TMDbUserImport, TraktUserImport, CustomImport,
    RadarrListImport) by overlaying only the fields that implementation
    needs on top of its own live schema, rather than hand-maintaining a
    separate field template per type in this file."""
    if app_name not in ("radarr", "sonarr"):
        fail("Only radarr and sonarr have import lists.", status_code=400)
    cfg = ARR_APPS[app_name]
    try:
        schemas = httpx.get(f"{cfg['url']}/api/{cfg['api']}/importlist/schema", headers={"X-Api-Key": cfg["key"]}, timeout=20).json()
        folders = httpx.get(f"{cfg['url']}/api/{cfg['api']}/rootfolder", headers={"X-Api-Key": cfg["key"]}, timeout=20).json()
        profiles = httpx.get(f"{cfg['url']}/api/{cfg['api']}/qualityprofile", headers={"X-Api-Key": cfg["key"]}, timeout=20).json()
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} lookup failed: {e}")
    template = next((s for s in schemas if s["implementation"] == payload.implementation), None)
    if template is None:
        fail(f"Unknown import-list implementation '{payload.implementation}' for {cfg['label']}.", status_code=400)
    if not folders or not profiles:
        fail(f"{cfg['label']} has no root folder / quality profile configured.")

    body = dict(template)
    body["name"] = payload.name
    body["enabled"] = True
    body["enableAuto"] = payload.search_on_add
    body["searchOnAdd"] = payload.search_on_add
    body["rootFolderPath"] = folders[0]["path"]
    body["qualityProfileId"] = profiles[0]["id"]
    body["monitor"] = payload.monitor or ("movieOnly" if app_name == "radarr" else "all")
    if app_name == "radarr":
        body["minimumAvailability"] = payload.minimum_availability
    field_values = dict(payload.fields)
    if payload.implementation == "PlexImport" and "accessToken" not in field_values and PLEX_TOKEN:
        field_values["accessToken"] = PLEX_TOKEN

    # Trakt/Simkl/TMDb-user import types need an OAuth token Radarr/Sonarr
    # only ever obtain through their own UI's "Authenticate" button - not
    # something this endpoint can complete on its own. But that token is
    # tied to the underlying account, not the individual list: if another
    # list of the same OAuth family (matched by implementation prefix, e.g.
    # any "Trakt*Import") is already configured on this app, its token
    # works for a new one too. Confirmed live: this Radarr's existing
    # TraktListImport entries (DCAU/DCEU) already carry a valid
    # accessToken/refreshToken, reusable here without a fresh OAuth pass.
    oauth_families = ("Trakt", "Simkl", "TMDbUser")
    family = next((f for f in oauth_families if payload.implementation.startswith(f)), None)
    if family:
        oauth_field_names = {"accessToken", "refreshToken", "expires", "authUser"}
        donor = next(
            (lst for lst in httpx.get(f"{cfg['url']}/api/{cfg['api']}/importlist",
                                       headers={"X-Api-Key": cfg["key"]}, timeout=20).json()
             if lst["implementation"].startswith(family)
             and any(f["name"] == "accessToken" and f.get("value") for f in lst["fields"])),
            None,
        )
        if donor:
            for f in donor["fields"]:
                if f["name"] in oauth_field_names and f["name"] not in field_values:
                    field_values[f["name"]] = f.get("value")
        elif not any(k in field_values for k in oauth_field_names):
            fail(f"No existing {family}-authenticated import list found on {cfg['label']} to reuse a token from - "
                 f"authenticate one list of this type through {cfg['label']}'s own UI first (Settings -> Import Lists "
                 f"-> Add -> {payload.implementation}'s \"Authenticate\" button), then this endpoint can reuse it "
                 f"for every list after.", status_code=409)

    body["fields"] = [dict(f, value=field_values[f["name"]]) if f["name"] in field_values else f
                       for f in template["fields"]]

    try:
        r = httpx.post(f"{cfg['url']}/api/{cfg['api']}/importlist", json=body, headers={"X-Api-Key": cfg["key"]}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        fail(f"{cfg['label']} import-list creation failed: {e.response.text.strip() or e}")
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} import-list creation failed: {e}")
    return ok(f"Import list '{payload.name}' ({payload.implementation}) added to {cfg['label']}.", id=r.json().get("id"))


@app.get("/api/tautulli/stats")
def tautulli_stats():
    """Tautulli's own home-stats widget data (most watched, most active
    users/platforms over the last 30 days) - a server-wide view, distinct
    from stack-tautulli-history's per-session log."""
    key = _tautulli_key()
    if not key:
        fail("No Tautulli API key found (config.ini not present yet - has it completed setup?).", status_code=500)
    try:
        r = httpx.get(f"{TAUTULLI_URL}/api/v2", params={"apikey": key, "cmd": "get_home_stats", "time_range": 30}, timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Tautulli lookup failed: {e}")
    data = r.json().get("response", {}).get("data", [])
    items = [{"title": stat.get("stat_title"), "rows": [row.get("title") or row.get("user") or row.get("platform")
              for row in stat.get("rows", [])[:5]]} for stat in data if stat.get("rows")]
    return ok(f"{len(items)} stat categor{'y' if len(items) == 1 else 'ies'} from the last 30 days.", items=items)


def _bazarr_headers():
    key = _bazarr_key()
    if not key:
        fail("No Bazarr API key found (config.yaml not present yet - has it completed setup?).", status_code=500)
    return {"X-API-KEY": key}


@app.get("/api/bazarr/wanted")
def bazarr_wanted():
    """Movies/episodes Bazarr still has no subtitle for, across both
    libraries - the same list its own scheduled search works through,
    surfaced without opening its UI."""
    try:
        movies = httpx.get(f"{BAZARR_URL}/api/movies/wanted", headers=_bazarr_headers(), timeout=20)
        movies.raise_for_status()
        episodes = httpx.get(f"{BAZARR_URL}/api/episodes/wanted", headers=_bazarr_headers(), timeout=20)
        episodes.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Bazarr lookup failed: {e}")
    movie_items = [m.get("title") for m in movies.json().get("data", [])]
    episode_items = [f'{e.get("seriesTitle")} - {e.get("episode_number", "")}' for e in episodes.json().get("data", [])]
    return ok(f"{len(movie_items)} movie(s), {len(episode_items)} episode(s) still missing subtitles.",
              movies=movie_items, episodes=episode_items)


@app.post("/api/bazarr/search-missing")
def bazarr_search_missing():
    """Triggers Bazarr's missing-subtitle search job on demand instead of
    waiting for its scheduler (default every 6h) - the same job
    `wanted_search_missing_subtitles_movies`/`_series` runs automatically."""
    try:
        r = httpx.post(f"{BAZARR_URL}/api/system/tasks", headers=_bazarr_headers(),
                        data={"taskid": "wanted_search_missing_subtitles_movies"}, timeout=20)
        r.raise_for_status()
        r2 = httpx.post(f"{BAZARR_URL}/api/system/tasks", headers=_bazarr_headers(),
                         data={"taskid": "wanted_search_missing_subtitles_series"}, timeout=20)
        r2.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Couldn't trigger Bazarr's search: {e}")
    return ok("Missing-subtitle search triggered for both movies and series.")


@app.get("/api/bazarr/history")
def bazarr_history(limit: int = 20):
    """Recent subtitle download history (both movies and episodes),
    newest first - successes and failures both, so a provider that's
    silently failing every download shows up without checking each item."""
    try:
        movies = httpx.get(f"{BAZARR_URL}/api/movies/history", headers=_bazarr_headers(),
                            params={"length": limit}, timeout=20)
        movies.raise_for_status()
        episodes = httpx.get(f"{BAZARR_URL}/api/episodes/history", headers=_bazarr_headers(),
                              params={"length": limit}, timeout=20)
        episodes.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Bazarr lookup failed: {e}")
    items = []
    for rec in movies.json().get("data", [])[:limit]:
        items.append({"title": rec.get("title"), "action": rec.get("description"), "provider": rec.get("provider")})
    for rec in episodes.json().get("data", [])[:limit]:
        items.append({"title": rec.get("seriesTitle"), "action": rec.get("description"), "provider": rec.get("provider")})
    return ok(f"{len(items)} recent history entr{'y' if len(items) == 1 else 'ies'}.", items=items)


@app.get("/api/bazarr/provider-status")
def bazarr_provider_status():
    """Per-provider throttle/error state for every enabled subtitle
    source - catches a provider that's silently rate-limited or erroring
    on every request, invisible from a plain enabled/disabled list."""
    try:
        r = httpx.get(f"{BAZARR_URL}/api/providers", headers=_bazarr_headers(), timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Bazarr lookup failed: {e}")
    items = [{"name": p.get("name"), "status": p.get("status"), "retry": p.get("retry")} for p in r.json().get("data", [])]
    problems = [i["name"] for i in items if i["status"] != "Good"]
    msg = "All providers healthy." if not problems else f"Problem with: {', '.join(problems)}"
    return ok(msg, items=items)


@app.post("/api/backup-integrity-check")
def backup_integrity_check():
    """On-demand `restic check` (10% data subset, same sampling
    backup-config.sh's own monthly automatic check uses) against both
    repos - for verifying right now rather than waiting for the 1st of
    the month, e.g. right after a repo's been touched by hand."""
    repos = {"local": HOST_BACKUP_LOCAL, "offsite": HOST_BACKUP_OFFSITE}
    out = {}
    for name, path in repos.items():
        if not os.path.isdir(path):
            out[name] = {"status": "missing", "path": path}
            continue
        r = _restic(path, ["check", "--read-data-subset=10%"], timeout=600)
        out[name] = {"status": "ok" if r.returncode == 0 else "error",
                      "detail": None if r.returncode == 0 else (r.stderr or r.stdout).strip()[:500]}
    problems = [n for n, v in out.items() if v["status"] != "ok"]
    msg = "Both repos passed integrity check." if not problems else f"Problem with: {', '.join(problems)}"
    return ok(msg, repos=out)


@app.get("/api/arr/{app_name}/customformat-snapshot")
def arr_customformat_snapshot(app_name: str):
    """Current custom-format list and scores for the given app's quality
    profile(s) - stack-customformat-diff caches this response locally and
    diffs successive calls, since neither app has a native change log for
    format-score edits made through the API."""
    if app_name not in ("radarr", "sonarr"):
        fail("Only radarr and sonarr have custom formats.", status_code=400)
    cfg = ARR_APPS[app_name]
    try:
        cf = httpx.get(f"{cfg['url']}/api/{cfg['api']}/customformat", headers={"X-Api-Key": cfg["key"]}, timeout=20)
        cf.raise_for_status()
        profiles = httpx.get(f"{cfg['url']}/api/{cfg['api']}/qualityprofile", headers={"X-Api-Key": cfg["key"]}, timeout=20)
        profiles.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"{cfg['label']} lookup failed: {e}")
    cf_names = {c["id"]: c["name"] for c in cf.json()}
    snapshot = {}
    for profile in profiles.json():
        snapshot[profile["name"]] = {
            cf_names.get(item["format"], str(item["format"])): item["score"] for item in profile["formatItems"]
        }
    return ok(f"{len(cf_names)} custom format(s) across {len(snapshot)} profile(s) on {cfg['label']}.", profiles=snapshot)


@app.get("/api/altmount/stats")
def altmount_stats():
    """Aggregate counts instead of the raw queue/history dumps
    altmount_queue()/altmount_history() above already provide - queued count
    and total size left, plus history success/fail counts, in one glance."""
    queue = altmount_api("queue").get("queue", {}).get("slots", [])
    history = altmount_api("history", limit=100).get("history", {}).get("slots", [])
    fail_count = sum(1 for h in history if (h.get("status") or "").lower() == "failed")
    mb_left = sum(float(s.get("mbleft") or 0) for s in queue)
    return ok(f"{len(queue)} queued ({mb_left:.0f}MB left), {len(history)} in recent history "
              f"({fail_count} failed).", queued=len(queue), mb_left=round(mb_left), history_count=len(history),
              history_failed=fail_count)


@app.post("/api/altmount/delete-failures")
def altmount_delete_failures():
    """Deletes every "Failed" history entry via AltMount's SABnzbd-compatible
    delete endpoint (mode=history&name=delete&value=<nzo_id>, one id per
    call, mirroring the same shape NzbDAV's equivalent route had). Deletes
    fan out across threads rather than running serially - same-host calls,
    not rate-limited."""
    history = altmount_api("history", limit=0, timeout=180)
    slots = history.get("history", {}).get("slots", [])
    failed = [s for s in slots if (s.get("status") or "") == "Failed"]
    if not failed:
        return ok("No failed history entries to delete.", deleted=0, errors=0)

    def delete_one(slot):
        try:
            r = httpx.get(ALTMOUNT_URL, params={
                "mode": "history", "name": "delete", "value": slot["nzo_id"],
                "apikey": ALTMOUNT_API_KEY, "output": "json",
            }, timeout=30)
            r.raise_for_status()
            result = r.json()
        except httpx.HTTPError as e:
            return False, f'{slot.get("name")}: {e}'
        if result.get("status"):
            return True, None
        return False, f'{slot.get("name")}: {result.get("error")}'

    deleted, errors = 0, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        for ok_, message in pool.map(delete_one, failed):
            if ok_:
                deleted += 1
            else:
                errors.append(message)
    msg = f"Deleted {deleted}/{len(failed)} failed history entries."
    if errors:
        msg += f" {len(errors)} error(s)."
    return ok(msg, deleted=deleted, errors=errors[:20])


@app.get("/api/plex/recently-added")
def plex_recently_added(limit: int = 15):
    """What actually finished importing and became visible in Plex, across
    every library - complements arr_recently_added() above (which shows
    what was *added to management*, not necessarily downloaded yet)."""
    try:
        r = httpx.get(f"{PLEX_URL}/library/all", params={"sort": "addedAt:desc", "type": 1},
                       headers=plex_headers(), timeout=20)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Could not read Plex's recently-added list: {e}")
    movies = r.json().get("MediaContainer", {}).get("Metadata", [])
    try:
        r = httpx.get(f"{PLEX_URL}/library/all", params={"sort": "addedAt:desc", "type": 2},
                       headers=plex_headers(), timeout=20)
        r.raise_for_status()
        shows = r.json().get("MediaContainer", {}).get("Metadata", [])
    except httpx.HTTPError:
        shows = []
    combined = sorted(movies + shows, key=lambda el: el.get("addedAt") or 0, reverse=True)[:limit]
    items = [{"title": el.get("title"), "year": el.get("year"), "type": el.get("type"),
              "addedAt": el.get("addedAt"), "librarySectionTitle": el.get("librarySectionTitle")}
             for el in combined]
    return ok(f"{len(items)} most recently added item(s) across Plex movie/show libraries.", items=items)


app.mount("/", StaticFiles(directory="static", html=True), name="static")
