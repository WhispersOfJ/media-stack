"""
Control Panel - the single dashboard for The Stack: live container status
and start/stop/restart control, Zilean's own indexed-hash count, one-click
operational actions, and a direct Zilean search with grab-to-Decypharr.
Supersedes the old Homepage+Control Panel split - see README.md's Control
Panel section.

Talks to the Docker socket (start/stop/restart/exec/stats), each app's own
HTTP API (Plex, Radarr, Sonarr, Zilean), and zilean-postgres
directly (hash count - Zilean has no stats API of its own). No auth -
LAN-only, matches every other service in this stack (see README.md's
"Security" section).
"""
import concurrent.futures
import os
import re
import socket
import sqlite3
import subprocess
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import docker
import httpx
import psycopg2
import pymysql
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PLEX_URL = (os.environ.get("PLEX_URL") or "").rstrip("/")
PLEX_TOKEN = os.environ.get("PLEX_TOKEN")
ZILEAN_URL = "http://zilean:8181"
DECYPHARR_URL = "http://decypharr:8282"
DECYPHARR_ALLDEBRID_URL = "http://decypharr-alldebrid:8282"
DECYPHARR_MANUAL_CATEGORY = "manual"
DECYPHARR_ADMIN_USERNAME = os.environ.get("DECYPHARR_ADMIN_USERNAME")
DECYPHARR_ADMIN_PASSWORD = os.environ.get("DECYPHARR_ADMIN_PASSWORD")
NZBDAV_URL = "http://nzbdav:3000"
NZBDAV_API_KEY = os.environ.get("NZBDAV_API_KEY")
ZILEAN_POSTGRES_PASSWORD = os.environ.get("ZILEAN_POSTGRES_PASSWORD")
HOST_IP = os.environ.get("HOST_IP")
PROWLARR_API_KEY = os.environ.get("PROWLARR_API_KEY")
TAUTULLI_URL = "http://tautulli:8181"
SEERR_URL = "http://seerr:5055"
MAINTAINERR_URL = "http://maintainerr:6246"
DMM_MYSQL_ROOT_PASSWORD = os.environ.get("DMM_MYSQL_ROOT_PASSWORD")
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


def _kometa_config() -> dict:
    """Kometa's config.yml already holds user-supplied OMDb/MDBList API
    keys (both optional, entered once for Kometa's own metadata lookups) -
    reading them live off the mounted config here means the ratings
    endpoints below need zero new secrets/.env entries, same reasoning as
    _tautulli_key/_seerr_key above."""
    path = os.path.join(HOST_CONFIG_DIR, "kometa", "config.yml")
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _omdb_key() -> str | None:
    return _kometa_config().get("omdb", {}).get("apikey") or None


def _mdblist_key() -> str | None:
    return _kometa_config().get("mdblist", {}).get("apikey") or None
# Read-only host mounts added specifically for the stack-* diagnostic
# endpoints below (resource-check through neutarr-hunt) - see
# docker-compose.yml's control-panel volumes for what backs each of these.
HOST_CONFIG_DIR = "/host-config"
HOST_MNT_DIR = "/mnt"
HOST_BACKUP_LOCAL = "/host-backups/stack-restic-repo"
HOST_BACKUP_OFFSITE = "/host-backup-offsite"
HOST_RESTIC_PASSWORD_FILE = "/host-backups/.restic-password"
HOST_README = "/host-README.md"
# Matches Decypharr's own hexRegex (pkg/internal/utils/magnet.go) - its
# magnet parser (anacrolix/torrent's metainfo.ParseMagnetUri) 400s with no
# application-level log line for anything that doesn't match this, so this
# is checked up front for a clear error instead of a passthrough failure.
INFO_HASH_RE = re.compile(r"^[0-9a-fA-F]{40}$")

# Internal stacknet hostnames - not HOST_IP, since this container reaches
# every *arr app over the docker network directly (same pattern Kometa's
# own config.yml uses).
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

# These four have a real download queue (Decypharr + NzbDAV wired to each
# as of 10.2.0) - Unstick/manual-import work identically on all of them,
# same reasoning 7.0.0 used when this was just Radarr/Sonarr. Bindery
# (Readarr's v10.7.0 replacement) isn't listed - its API is a clean-room
# design, not Servarr-shaped, so this generic queue machinery doesn't apply.
QUEUE_ARR_APPS = ("radarr", "sonarr")

# Display-only labels/notes for the container grid - NOT an allow-list.
# Which containers actually exist, and which actions are valid on them, is
# always determined live from Docker (see project_containers() below), so
# this dict going stale (a service added to docker-compose.yml but not
# listed here) only means a slightly plainer name in the UI, never a broken
# or missing control - the exact staleness failure mode the old hardcoded
# RESTARTABLE_CONTAINERS allow-list had (it silently excluded any service
# added to compose after it was written, e.g. decypharr-alldebrid).
CONTAINER_LABELS = {
    "radarr": ("Radarr", "also clears the stale Zurg mount issue (v4.0.1)"),
    "sonarr": ("Sonarr", None),
    "prowlarr": ("Prowlarr", None),
    "plex": ("Plex", None),
    "zurg": ("Zurg", "Real-Debrid mount"),
    "rclone-alldebrid": ("rclone", "AllDebrid mount"),
    "rclone-alldebrid-anime": ("rclone", "AllDebrid mount, anime-filtered subset"),
    "decypharr": ("Decypharr", "Real-Debrid + AllDebrid"),
    "decypharr-alldebrid": ("Decypharr", "AllDebrid only, Sonarr-exclusive"),
    "nzbdav": ("NzbDAV", "Usenet, WebDAV + SABnzbd-compatible API"),
    "nzbdav-rclone": ("rclone", "NzbDAV mount"),
    "seerr": ("Seerr", None),
    "tautulli": ("Tautulli", None),
    "byparr": ("Byparr", None),
    "kometa": ("Kometa", None),
    "zilean": ("Zilean", None),
    "zilean-postgres": ("Zilean Postgres", None),
    "unpackerr": ("Unpackerr", None),
    "watchtower": ("Watchtower", None),
    "debridmediamanager": ("DebridMediaManager", None),
    "dmm-mysql": ("DMM MySQL", "app database"),
    "dmm-redis": ("DMM Redis", "rate limiting"),
    "dmm-migrate": ("DMM Migrate", "one-shot Prisma migration - exits after running, not a bug if shown stopped"),
    "cleanuparr": ("Cleanuparr", "queue cleanup: strikes, malware block, stalled/failed removal"),
    "neutarr": ("NeutArr", "hardened Huntarr-lineage fork - missing/upgrade hunting"),
    "maintainerr": ("Maintainerr", "Plex library lifecycle - rule-based cleanup, wired but rules start disabled"),
    "recyclarr": ("Recyclarr", "TRaSH Guides custom-format sync, Radarr/Sonarr only"),
    "beszel": ("Beszel", "host/container resource monitoring hub - replaced Glances in v10.9.9"),
    "beszel-agent": ("Beszel Agent", "reports this host's stats to the beszel hub"),
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
    urlparse(ZILEAN_URL).hostname: "Zilean",
    urlparse(DECYPHARR_URL).hostname: "Decypharr",
    urlparse(NZBDAV_URL).hostname: "NzbDAV",
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


class ZileanSearchRequest(BaseModel):
    query: str


class GrabRequest(BaseModel):
    hash: str
    title: str | None = None


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
# Overview strip: Zilean's own indexed-hash count (queried straight from
# zilean-postgres - Zilean has no stats API of its own; every endpoint
# guessed at (/health, /api/stats, /dmm/status) 404s, see README.md
# "Zilean hash sources"). Best-effort: an unreachable Postgres degrades
# this one stat tile, not the whole page.
# ---------------------------------------------------------------------
@app.get("/api/zilean/stats")
def zilean_stats():
    if not ZILEAN_POSTGRES_PASSWORD:
        return {"available": False}
    try:
        conn = psycopg2.connect(
            host="zilean-postgres",
            port=5432,
            dbname="zilean",
            user="postgres",
            password=ZILEAN_POSTGRES_PASSWORD,
            connect_timeout=5,
        )
        try:
            with conn.cursor() as cur:
                # The base count is the one thing this tile actually needs -
                # do it first and on its own, so a wrong guess at the second
                # query's column name (below) can't take out the whole tile.
                cur.execute('SELECT COUNT(*) FROM "Torrents"')
                total = cur.fetchone()[0]
                matched = None
                try:
                    # Column name guessed from EF Core's PascalCase
                    # convention (matches "Torrents" itself) - not verified
                    # against the live schema, so this is best-effort only.
                    cur.execute('SELECT COUNT(*) FROM "Torrents" WHERE "ImdbId" IS NOT NULL')
                    matched = cur.fetchone()[0]
                except Exception:
                    conn.rollback()
        finally:
            conn.close()
        return {"available": True, "total_hashes": total, "imdb_matched": matched}
    except Exception:
        return {"available": False}


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
        cmd += ["--run-libraries", ",".join(payload.libraries)]
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
# NzbDAV - Usenet streaming layer (WebDAV + rclone, no local disk - see
# README.md's Usenet Pipeline section). Talks to its own SABnzbd-compatible query API
# (mode=queue/mode=history) rather than a dedicated REST API - it doesn't
# have one beyond that.
# ---------------------------------------------------------------------
def nzbdav_api(mode: str, **params) -> dict:
    if not NZBDAV_API_KEY:
        fail("NzbDAV isn't configured (NZBDAV_API_KEY not set)", status_code=503)
    try:
        r = httpx.get(
            f"{NZBDAV_URL}/api",
            params={"mode": mode, "output": "json", "apikey": NZBDAV_API_KEY, **params},
            timeout=15,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"NzbDAV {mode} lookup failed: {e}")
    return r.json()


@app.get("/api/nzbdav/queue")
def nzbdav_queue():
    slots = nzbdav_api("queue").get("queue", {}).get("slots", [])
    return [{
        "name": s.get("filename"),
        "category": s.get("cat"),
        "status": s.get("status"),
        "percentage": s.get("percentage"),
        "size_mb": s.get("mb"),
        "size_left_mb": s.get("mbleft"),
    } for s in slots]


@app.get("/api/nzbdav/history")
def nzbdav_history(limit: int = 20):
    slots = nzbdav_api("history", limit=limit).get("history", {}).get("slots", [])
    return [{
        "name": s.get("name"),
        "category": s.get("category"),
        "status": s.get("status"),
        "size": human_size(s.get("bytes")),
        "fail_message": s.get("fail_message") or None,
        "path": s.get("storage"),
    } for s in slots]


# ---------------------------------------------------------------------
# Ratings lookups - OMDb (IMDb) and MDBList. Both keys already live in
# Kometa's own config.yml (entered once for Kometa's metadata lookups),
# read live via _omdb_key()/_mdblist_key() rather than duplicated into
# .env - same reasoning as Tautulli/Seerr's keys above.
# ---------------------------------------------------------------------
@app.get("/api/ratings/imdb")
def rating_imdb(imdb_id: str):
    key = _omdb_key()
    if not key:
        fail("No OMDb API key found in Kometa's config.yml (omdb.apikey).", status_code=500)
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
        fail("No MDBList API key found in Kometa's config.yml (mdblist.apikey).", status_code=500)
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
        fail("No MDBList API key found in Kometa's config.yml (mdblist.apikey).", status_code=500)

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


# ---------------------------------------------------------------------
# Zilean - direct search against its own index, bypassing Prowlarr/*arr
# entirely. Talks to Zilean's own /dmm/search endpoint (AllowAnonymous,
# no API key needed - only /dmm/on-demand-scrape requires one).
# ---------------------------------------------------------------------
def human_size(n: int | None) -> str:
    if not n:
        return "?"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


@app.post("/api/zilean/search")
def zilean_search(payload: ZileanSearchRequest):
    query = payload.query.strip()
    if not query:
        fail("Search query is empty.", status_code=400)
    try:
        r = httpx.post(f"{ZILEAN_URL}/dmm/search", json={"queryText": query}, timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Zilean search failed: {e}")
    results = r.json()
    return [
        {
            "title": item.get("parsed_title") or item.get("raw_title"),
            "raw_title": item.get("raw_title"),
            "year": item.get("year"),
            "resolution": item.get("resolution"),
            "quality": item.get("quality"),
            "size": human_size(item.get("size")),
            "size_bytes": item.get("size"),
            "hash": item.get("info_hash"),
            "imdb_id": item.get("imdb_id"),
            "seasons": item.get("seasons") or [],
            "episodes": item.get("episodes") or [],
        }
        for item in results
    ]


@app.post("/api/decypharr/grab")
def decypharr_grab(payload: GrabRequest):
    """Adds a magnet built from a chosen hash to Decypharr's own
    qBittorrent-compatible API - the same path Radarr/Sonarr already use to
    add everything else in this stack, under a dedicated 'manual' category
    so ad-hoc grabs land somewhere predictable (config/decypharr/downloads/
    manual) instead of mixed into an arr app's own category. This is a real
    action against the user's debrid account - it should only ever run in
    response to an explicit click on a specific result, never automatically."""
    info_hash = payload.hash.strip().lower()
    if not info_hash:
        fail("No hash provided.", status_code=400)
    if not INFO_HASH_RE.match(info_hash):
        # Zilean's index is scraped from a public hashlist and isn't
        # perfectly clean - an occasional entry has a malformed info_hash.
        # Decypharr's magnet parser rejects these with a 400 and no
        # application-level log line at all, which is indistinguishable
        # from a real bug without this check - caught live via a real user
        # click that produced exactly that opaque failure.
        fail(f"'{info_hash}' isn't a valid 40-character info hash - this result can't be added.", status_code=400)
    title = (payload.title or info_hash).strip()
    magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={quote(title)}"
    try:
        # Decypharr's v2 API needs its own qBittorrent-style session (a
        # separate SID cookie from the web UI's own /login) - a bare POST
        # with no prior login 401s once use_auth is on, confirmed live.
        with httpx.Client(timeout=15) as client:
            client.post(
                f"{DECYPHARR_URL}/api/v2/auth/login",
                data={"username": DECYPHARR_ADMIN_USERNAME, "password": DECYPHARR_ADMIN_PASSWORD},
            )
            # Idempotent - safe to call before every add rather than tracking
            # whether it already exists.
            client.post(
                f"{DECYPHARR_URL}/api/v2/torrents/createCategory",
                data={"category": DECYPHARR_MANUAL_CATEGORY, "savePath": f"/app/downloads/{DECYPHARR_MANUAL_CATEGORY}"},
            )
            r = client.post(
                f"{DECYPHARR_URL}/api/v2/torrents/add",
                data={"urls": magnet, "category": DECYPHARR_MANUAL_CATEGORY},
                timeout=30,
            )
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        # Surface Decypharr's own response body (its actual error message)
        # instead of just httpx's generic "400 Bad Request" summary - the
        # difference between a self-diagnosing error and a support request.
        detail = e.response.text.strip() or str(e)
        fail(f"Grab failed: {detail}")
    except httpx.HTTPError as e:
        fail(f"Grab failed: {e}")
    return ok(f'Added "{title}" to Decypharr - will appear once Real-Debrid/AllDebrid finishes caching.')


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
# usually caused by the Zurg/rclone debrid mount going stale mid-import
# (see CONTAINER_LABELS' Radarr note) or a release that doesn't
# actually match what was expected.
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
# in this stack, confirmed live. Decypharr's debrid-cached/symlinked
# downloads jump straight from full size to zero with no gradual
# byte-by-byte transfer to time (there's no real download happening at
# that layer to measure), and NzbDAV's SABnzbd-emulation layer doesn't
# compute a speed field at all even though its mb/mbleft are real.
# Usenet items pulled through NzbDAV are the one case with an actual
# gradually-draining transfer. Rather than special-case that, this takes
# two live size-remaining samples ~4s apart for everything and derives
# real observed speed from the delta - honest about "no progress
# observed" (still caching server-side, or genuinely stalled) instead of
# fabricating an ETA the data can't support.
# ---------------------------------------------------------------------
QUEUE_SAMPLE_SECONDS = 4


def _arr_sizeleft_snapshot(app_name: str) -> dict[int, int]:
    try:
        records = arr_queue(app_name)
    except HTTPException:
        return {}
    return {q["id"]: q.get("sizeleft") or 0 for q in records if q.get("sizeleft")}


def _nzbdav_mbleft_snapshot() -> dict[str, float]:
    try:
        slots = nzbdav_api("queue").get("queue", {}).get("slots", [])
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


def _bucket_nzbdav_item(s: dict, prev_mbleft: dict[str, float]) -> tuple[str, dict]:
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
    before_nzbdav = _nzbdav_mbleft_snapshot()
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
        slots = nzbdav_api("queue").get("queue", {}).get("slots", [])
        buckets = {"downloading": [], "stalled": [], "queued": [], "importing": []}
        for s in slots:
            bucket, item = _bucket_nzbdav_item(s, before_nzbdav)
            buckets[bucket].append(item)
        grand_total += len(slots)
        result["nzbdav"] = {"label": "NzbDAV", "total": len(slots), **buckets}
    except HTTPException:
        result["nzbdav"] = {"label": "NzbDAV", "error": "unreachable"}

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


# ---------------------------------------------------------------------
# Whole-stack restart
# ---------------------------------------------------------------------
# Radarr bind-mounts /mnt/zurg and /mnt/decypharr directly (rslave), unlike
# Sonarr's blanket /mnt bind - a direct subpath bind doesn't survive the FUSE
# process underneath it being recreated, so restarting a provider after
# Radarr in the same sweep reproduces the CHANGELOG v4.0.1 stale-mount bug
# (see README's "Radarr-specific mount fragility" note). Restart providers
# first, wait for them to report healthy, then restart the dependents last.
#
# nzbdav-rclone belongs in this set too - it owns the /mnt/nzbdav FUSE mount,
# same as zurg/decypharr/rclone-alldebrid* own theirs - but it also has its
# own upstream dependency: its rclone remote talks to nzbdav's own API
# (docker-compose.yml's `depends_on: nzbdav: condition: service_healthy`),
# which the plain compose graph enforces but this hand-rolled restart loop
# doesn't. Restarting nzbdav-rclone before nzbdav is back up healthy fails
# the mount the same way a stale host mount does (confirmed live: a full
# stack outage where /mnt/nzbdav was left stale at the host level - see
# README's mount-cascade note). MOUNT_PREREQS restarts first and is waited
# on before MOUNT_PROVIDERS, so nzbdav-rclone always finds nzbdav ready.
MOUNT_PREREQS = {"nzbdav"}
MOUNT_PROVIDERS = {"zurg", "decypharr", "decypharr-alldebrid", "rclone-alldebrid", "rclone-alldebrid-anime", "nzbdav-rclone"}
MOUNT_DEPENDENTS = {"radarr"}


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
        # Two real bugs found getting this right, live:
        # 1. followlinks=False keeps os.walk from descending into a
        #    symlinked subdirectory, but os.path.getsize() on a file
        #    that's *itself* a symlink still follows it - config/decypharr/
        #    downloads holds symlinks into /mnt/decypharr (the debrid FUSE
        #    mount, real size in the TBs), which getsize() resolved and
        #    summed, reporting a 349GB "config directory".
        # 2. Switching to os.lstat().st_size fixed that, but decypharr's
        #    own cache still reported 152GB against a real (`du`-confirmed)
        #    11GB - st_size is a file's *logical* size, not actual disk
        #    consumption; decypharr's FUSE cache uses sparse/preallocated
        #    files, so st_size vastly overstates real usage. st_blocks
        #    (512-byte units, matching `du`'s own accounting) is what
        #    actually answers "how much disk does this use."
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


def _normalize_release_name(name: str) -> str:
    name = re.sub(r"\(\d{4}\).*", "", name)
    name = re.sub(r"[._-]", " ", name)
    return re.sub(r"\s+", " ", name).strip().lower()


CONTENT_AUDIT_APPS = {"movies": ("radarr", "title"), "shows": ("sonarr", "title")}


@app.get("/api/content-audit/{library}")
def content_audit(library: str):
    """Cross-references Zurg's raw /mnt/zurg/<library> listing against the
    matching *arr app's tracked titles - the exact manual workflow that
    found "Drilling Mommy"/"Family Swap"/"Forbidden Scenes" leaking into
    the wrong Plex library. Untracked ~= raw content Zurg classified
    independently, not necessarily wrong, but worth a look."""
    if library not in CONTENT_AUDIT_APPS:
        fail(f"Unknown library '{library}' - use one of: {', '.join(CONTENT_AUDIT_APPS)}", status_code=400)
    app_name, _ = CONTENT_AUDIT_APPS[library]
    cfg = ARR_APPS[app_name]
    mount_path = os.path.join(HOST_MNT_DIR, "zurg", library)
    if not os.path.isdir(mount_path):
        fail(f"{mount_path} not present - mount may be down.")
    try:
        r = httpx.get(f"{cfg['url']}/api/{cfg['api']}/movie" if app_name == "radarr" else f"{cfg['url']}/api/{cfg['api']}/series",
                       headers={"X-Api-Key": cfg["key"]}, timeout=30)
        r.raise_for_status()
        tracked = {_normalize_release_name(item["title"]) for item in r.json()}
    except Exception as e:
        fail(f"Could not reach {cfg['label']}: {e}")
    untracked = []
    for entry in sorted(os.listdir(mount_path)):
        norm = _normalize_release_name(entry)
        if not any(norm.startswith(t[:20]) or t in norm for t in tracked if len(t) > 3):
            untracked.append(entry)
    if not untracked:
        return ok(f"Every entry in /mnt/zurg/{library} matches a {cfg['label']}-tracked title.", untracked=[])
    return ok(
        f"{len(untracked)} entr(ies) in /mnt/zurg/{library} don't match any {cfg['label']}-tracked "
        f"title - not necessarily wrong, but worth a look (fuzzy match, false positives possible).",
        untracked=untracked,
    )


@app.get("/api/zurg/classify")
def zurg_classify(filename: str):
    """Tests a filename against Zurg's *current* config.yml, in group_order
    sequence, without needing a real leak sitting on disk to test against -
    would have made verifying today's adult-filter/group_order fix much
    faster. Mirrors Zurg's own "first match wins" logic exactly."""
    config_path = os.path.join(HOST_CONFIG_DIR, "zurg", "config.yml")
    if not os.path.isfile(config_path):
        fail(f"{config_path} not present.")
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    directories = cfg.get("directories", {})
    ordered = sorted(directories.items(), key=lambda kv: kv[1].get("group_order", 999))
    for group_name, group_cfg in ordered:
        for filt in group_cfg.get("filters", []):
            if "regex" in filt:
                pattern = filt["regex"].strip("/")
                # Zurg's own (?i) inline flag works fine in Python's re too.
                if re.search(pattern, filename):
                    return ok(f"'{filename}' matches group '{group_name}' (group_order {group_cfg.get('group_order')}).",
                               group=group_name, group_order=group_cfg.get("group_order"))
            if filt.get("has_episodes"):
                # Zurg's own heuristic isn't reimplementable exactly here -
                # flag it as a possible match rather than silently skipping.
                if re.search(r"\b[Ss]\d{1,2}[Ee]\d{1,3}\b|\b\d{1,3}x\d{1,3}\b", filename):
                    return ok(f"'{filename}' likely matches group '{group_name}' via has_episodes heuristic "
                              f"(approximated here, not Zurg's exact logic).", group=group_name, approximate=True)
    return ok(f"'{filename}' matches no group with a regex/heuristic filter - would fall through to the catch-all.")


KNOWN_MOUNTS = ["zurg", "decypharr", "decypharr-alldebrid", "nzbdav", "all", "all-anime"]


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
    # config/decypharr/downloads holds symlinks into the multi-TB debrid
    # mount; stat() would follow them (slow, and checking the wrong
    # file's permissions entirely - what matters here is the symlink
    # itself, not whatever it happens to point at).
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


def _restic(repo_path: str, args: list, text: bool = True) -> subprocess.CompletedProcess:
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
    return subprocess.run(["restic", "--no-lock", *args], env=env, capture_output=True, text=text, timeout=60)


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


DECYPHARR_INSTANCES = {"decypharr": DECYPHARR_URL, "decypharr-alldebrid": DECYPHARR_ALLDEBRID_URL}


@app.get("/api/decypharr/health/{instance}")
def decypharr_health(instance: str):
    """Directly checks a Decypharr instance's own health endpoint - bypasses
    whatever's consuming it (Radarr/Sonarr/Cleanuparr/etc.), useful when one
    of those reports a Decypharr failure and the question is "is it
    actually Decypharr, or my client's own stored credentials." Root-caused
    the Cleanuparr↔Decypharr 401 this session - the real problem was a
    stale password in Cleanuparr's own config, not Decypharr itself."""
    if instance not in DECYPHARR_INSTANCES:
        fail(f"Unknown instance '{instance}' - use one of: {', '.join(DECYPHARR_INSTANCES)}", status_code=400)
    url = DECYPHARR_INSTANCES[instance]
    try:
        r = httpx.get(f"{url}/api/v2/app/version", timeout=10)
        if r.status_code == 200:
            return ok(f"{instance} is reachable and responding normally.")
        fail(f"{instance} responded with HTTP {r.status_code}.")
    except httpx.RequestError as e:
        fail(f"{instance} unreachable: {e}")


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
            # De-duped by exact byte size first - this library has two
            # configured root paths (/mnt/zurg/movies and the Radarr-
            # symlinked one), so a single real file routinely shows up as
            # two "Media" entries with identical sizes. Real duplicates
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


@app.get("/api/dmm/status")
def dmm_status():
    """Row counts for DMM's three largest IMDB tables plus a live
    connection check - the same query run by hand to verify no data loss
    after this session's mysql 8.4->9.7 major-version upgrade, now a
    standing command instead of a one-off."""
    if not DMM_MYSQL_ROOT_PASSWORD:
        fail("DMM_MYSQL_ROOT_PASSWORD not set.", status_code=503)
    try:
        conn = pymysql.connect(host="dmm-mysql", port=3306, user="root",
                                password=DMM_MYSQL_ROOT_PASSWORD, database="dmm", connect_timeout=5)
        try:
            with conn.cursor() as cur:
                counts = {}
                for table in ("imdb_title_akas", "imdb_title_basics", "imdb_title_ratings"):
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    counts[table] = cur.fetchone()[0]
        finally:
            conn.close()
    except Exception as e:
        fail(f"DMM MySQL connection failed: {e}")
    return ok(f"DMM database reachable - {counts['imdb_title_akas']:,} akas, "
              f"{counts['imdb_title_basics']:,} titles, {counts['imdb_title_ratings']:,} ratings.", **counts)


@app.get("/api/decypharr/{instance}/torrents")
def decypharr_torrents(instance: str):
    """Active items in a Decypharr instance's own qBittorrent-compatible
    queue - the actual add-a-torrent auth flow decypharr_grab() already
    uses, reused here read-only for torrents/info instead of torrents/add."""
    if instance not in DECYPHARR_INSTANCES:
        fail(f"Unknown instance '{instance}' - use one of: {', '.join(DECYPHARR_INSTANCES)}", status_code=400)
    url = DECYPHARR_INSTANCES[instance]
    try:
        with httpx.Client(timeout=15) as client:
            client.post(f"{url}/api/v2/auth/login",
                        data={"username": DECYPHARR_ADMIN_USERNAME, "password": DECYPHARR_ADMIN_PASSWORD})
            r = client.get(f"{url}/api/v2/torrents/info")
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"{instance} lookup failed: {e}")
    items = [{"name": t.get("name"), "state": t.get("state"), "progress": t.get("progress"),
              "size": human_size(t.get("size"))} for t in r.json()]
    return ok(f"{len(items)} item(s) in {instance}'s queue.", items=items)


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


@app.get("/api/recyclarr/status")
def recyclarr_status():
    """Recyclarr is cron-driven with no persistent API of its own (unlike
    every other app this file talks to), so this is the only way to see
    its last run: its own container's last log lines, straight from
    Docker, not a mounted log file."""
    try:
        c = docker_client.containers.get("recyclarr")
    except docker.errors.NotFound:
        fail("Container 'recyclarr' not found.")
    lines = c.logs(tail=30).decode("utf-8", errors="replace").splitlines()
    relevant = [line for line in lines if line.strip()][-15:]
    return ok(f"Last {len(relevant)} log line(s) from recyclarr.", lines=relevant)


@app.get("/api/maintainerr/rules")
def maintainerr_rules():
    """Configured Maintainerr rules and their enabled state - README notes
    rules ship disabled by default, so this is a quick check of whether
    that's still true without opening its UI."""
    try:
        r = httpx.get(f"{MAINTAINERR_URL}/api/rules", timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Maintainerr lookup failed: {e}")
    rules = r.json()
    items = [{"name": rule.get("name"), "active": rule.get("isActive"),
              "collection": (rule.get("collection") or {}).get("title")} for rule in rules]
    return ok(f"{len(items)} rule(s) configured.", items=items)


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


@app.get("/api/nzbdav/stats")
def nzbdav_stats():
    """Aggregate counts instead of the raw queue/history dumps
    nzbdav_queue()/nzbdav_history() above already provide - queued count
    and total size left, plus history success/fail counts, in one glance."""
    queue = nzbdav_api("queue").get("queue", {}).get("slots", [])
    history = nzbdav_api("history", limit=100).get("history", {}).get("slots", [])
    fail_count = sum(1 for h in history if (h.get("status") or "").lower() == "failed")
    mb_left = sum(s.get("mbleft") or 0 for s in queue)
    return ok(f"{len(queue)} queued ({mb_left:.0f}MB left), {len(history)} in recent history "
              f"({fail_count} failed).", queued=len(queue), mb_left=round(mb_left), history_count=len(history),
              history_failed=fail_count)


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
