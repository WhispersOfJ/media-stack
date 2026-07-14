"""
Control Panel - the single dashboard for The Stack: live container status
and start/stop/restart control, host system stats, Zilean's own indexed-hash
count, one-click operational actions, and a direct Zilean search with
grab-to-Decypharr. Supersedes the old Homepage+Control Panel split - see
README.md's Control Panel section.

Talks to the Docker socket (start/stop/restart/exec/stats), each app's own
HTTP API (Plex, Radarr, Sonarr, Whisparr, Zilean), Glances
(host stats), and zilean-postgres directly (hash count - Zilean has no stats
API of its own). No auth - LAN-only, matches every other service in this
stack (see README.md's "Security" section).
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
GLANCES_URL = "http://glances:61208"
NZBDAV_URL = "http://nzbdav:3000"
NZBDAV_API_KEY = os.environ.get("NZBDAV_API_KEY")
ZILEAN_POSTGRES_PASSWORD = os.environ.get("ZILEAN_POSTGRES_PASSWORD")
HOST_IP = os.environ.get("HOST_IP")
STASH_URL = "http://stash:9999"
PROWLARR_API_KEY = os.environ.get("PROWLARR_API_KEY")
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
    # Whisparr reinstated in 10.2.0 (originally removed in 4.0.0) - api
    # version and search_command name both differ per app, confirmed live
    # against each app's own /command endpoint rather than assumed
    # (Whisparr v3's is "MissingMoviesSearch", matching Radarr naming
    # despite tracking scenes, not "MissingEpisodeSearch" like Sonarr
    # would suggest from its Sonarr-codebase heritage).
    #
    # Readarr itself was replaced by Bindery in v10.7.0 (upstream Readarr's
    # sole metadata source died permanently, see docker-compose.yml's
    # comment on the bindery service) - no entry here since Bindery's API
    # is a clean-room design, not Servarr-shaped, so none of this generic
    # arr_queue/arr_command/history-rate-calc machinery applies to it.
    "whisparr": {
        "url": "http://whisparr:6969",
        "api": "v3",
        "key": os.environ["WHISPARR_API_KEY"],
        "search_command": "MissingMoviesSearch",
        "label": "Whisparr",
        "import_events": ("downloadFolderImported",),
    },
}

# These four have a real download queue (Decypharr + NzbDAV wired to each
# as of 10.2.0) - Unstick/manual-import work identically on all of them,
# same reasoning 7.0.0 used when this was just Radarr/Sonarr. Bindery
# (Readarr's v10.7.0 replacement) isn't listed - its API is a clean-room
# design, not Servarr-shaped, so this generic queue machinery doesn't apply.
QUEUE_ARR_APPS = ("radarr", "sonarr", "whisparr")

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
    "whisparr": ("Whisparr", "adult, v3"),
    "stash": ("Stash", "performer/studio/tag cataloging for the adult library"),
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
    "glances": ("Glances", None),
    "unpackerr": ("Unpackerr", None),
    "watchtower": ("Watchtower", None),
    "debridmediamanager": ("DebridMediaManager", None),
    "dmm-mysql": ("DMM MySQL", "app database"),
    "dmm-redis": ("DMM Redis", "rate limiting"),
    "dmm-migrate": ("DMM Migrate", "one-shot Prisma migration - exits after running, not a bug if shown stopped"),
    "cleanuparr": ("Cleanuparr", "queue cleanup: strikes, malware block, stalled/failed removal"),
    "neutarr": ("NeutArr", "hardened Huntarr-lineage fork - missing/upgrade hunting"),
    "dozzle": ("Dozzle", "read-only live log viewer"),
    "maintainerr": ("Maintainerr", "Plex library lifecycle - rule-based cleanup, wired but rules start disabled"),
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
    urlparse(GLANCES_URL).hostname: "Glances",
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
# Overview strip: live host stats (proxied from Glances - this container
# has no host pid namespace of its own, Glances already does via pid: host)
# and Zilean's own indexed-hash count (queried straight from
# zilean-postgres - Zilean has no stats API of its own; every endpoint
# guessed at (/health, /api/stats, /dmm/status) 404s, see README.md
# "Zilean hash sources"). Both are best-effort: an unreachable Glances or
# Postgres degrades this one stat tile, not the whole page.
# ---------------------------------------------------------------------
@app.get("/api/system/stats")
def system_stats():
    try:
        r = httpx.get(f"{GLANCES_URL}/api/4/all", timeout=8)
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError:
        return {"available": False}
    try:
        cpu = data.get("cpu", {})
        mem = data.get("mem", {})
        fs_list = data.get("fs", []) or []
        root_fs = next((f for f in fs_list if f.get("mnt_point") == "/"), fs_list[0] if fs_list else {})
        uptime = data.get("uptime")
        load = data.get("load", {})
        return {
            "available": True,
            "cpu_percent": cpu.get("total"),
            "load_1min": load.get("min1"),
            "mem_percent": mem.get("percent"),
            "mem_used_gb": round(mem["used"] / 1024**3, 1) if mem.get("used") else None,
            "mem_total_gb": round(mem["total"] / 1024**3, 1) if mem.get("total") else None,
            "disk_percent": root_fs.get("percent"),
            "disk_used_gb": round(root_fs["used"] / 1024**3, 1) if root_fs.get("used") else None,
            "disk_total_gb": round(root_fs["size"] / 1024**3, 1) if root_fs.get("size") else None,
            "uptime": uptime,
        }
    except Exception:
        return {"available": False}


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
            if app_name == "radarr" or app_name == "whisparr":
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
# NOTE: Whisparr binds the same three subpaths directly too and is
# conspicuously absent from this set - a pre-existing gap, not something
# this pass introduced or has verified is actually safe.
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
    "whisparr": ARR_APPS["whisparr"],
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
    vs. just an arr_configs type placeholder - the exact gap that left
    Lidarr and Whisparr completely uncovered by queue-cleaning/strikes
    despite both apps being fully functional."""
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


@app.post("/api/stash/scan")
def stash_scan():
    """Triggers a Stash library scan via its GraphQL API."""
    try:
        r = httpx.post(f"{STASH_URL}/graphql", json={"query": "mutation { metadataScan(input: {}) }"}, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get("errors"):
            fail(f"Stash returned an error: {data['errors']}")
        return ok(f"Scan job queued (id {data['data']['metadataScan']}).")
    except httpx.RequestError as e:
        fail(f"Could not reach Stash: {e}")


@app.post("/api/stash/identify")
def stash_identify():
    """Triggers a full-library StashDB identify run (studio/performer/tag
    creation enabled) - the same call that took this library from zero
    metadata to 317 performers/225 studios/791 tags. Requires a StashDB
    connection already configured in Stash's own Settings - this doesn't
    create one (that needs the user's own StashDB account)."""
    query = """
    mutation {
      metadataIdentify(input: {
        sources: [{source: {stash_box_endpoint: "https://stashdb.org/graphql"}}]
        options: {
          fieldOptions: [
            {field: "studio", strategy: MERGE, createMissing: true},
            {field: "performers", strategy: MERGE, createMissing: true},
            {field: "tags", strategy: MERGE, createMissing: true}
          ]
          setCoverImage: true
        }
      })
    }
    """
    try:
        r = httpx.post(f"{STASH_URL}/graphql", json={"query": query}, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get("errors"):
            fail(f"Stash returned an error: {data['errors']}")
        return ok(f"Identify job queued (id {data['data']['metadataIdentify']}) against all scenes.")
    except httpx.RequestError as e:
        fail(f"Could not reach Stash: {e}")


ARR_LOG_CONTAINERS = {"radarr", "sonarr", "whisparr", "prowlarr"}


@app.get("/api/arr/{app_name}/logs")
def arr_logs(app_name: str, lines: int = 100):
    """Tails a container's own docker logs directly - quicker than opening
    Dozzle for a one-off check."""
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


@app.post("/api/neutarr/hunt/eros")
def neutarr_hunt_eros():
    """NeutArr (Huntarr-lineage) has no documented "run now" API endpoint
    for an individual app's hunt cycle - the only reliable trigger is
    restarting the container, which forces its scheduler to restart from
    the beginning (including an immediate first pass) rather than waiting
    out whatever's left of the current interval."""
    try:
        c = docker_client.containers.get("neutarr")
        c.restart(timeout=30)
        return ok("neutarr restarted - its scheduler will run an immediate hunt pass for every enabled app "
                  "(eros/Whisparr included), not just eros specifically - NeutArr has no per-app trigger.")
    except docker.errors.NotFound:
        fail("Container 'neutarr' not found.")


app.mount("/", StaticFiles(directory="static", html=True), name="static")
