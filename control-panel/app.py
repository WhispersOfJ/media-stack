"""
Control Panel - the single dashboard for The Stack: live container status
and start/stop/restart control, host system stats, Zilean's own indexed-hash
count, one-click operational actions, and a direct Zilean search with
grab-to-Decypharr. Supersedes the old Homepage+Control Panel split - see
TECHNICAL.md's Control Panel section.

Talks to the Docker socket (start/stop/restart/exec/stats), each app's own
HTTP API (Plex, Radarr, Sonarr, Bazarr, Zilean), Glances (host stats), and
zilean-postgres directly (hash count - Zilean has no stats API of its own).
No auth - LAN-only, matches every other service in this stack (see
TECHNICAL.md's "Security note").
"""
import os
import re
import socket
import threading
import time
from datetime import datetime, timezone
from urllib.parse import quote

import docker
import httpx
import psycopg2
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PLEX_URL = (os.environ.get("PLEX_URL") or "").rstrip("/")
PLEX_TOKEN = os.environ.get("PLEX_TOKEN")
ZILEAN_URL = "http://zilean:8181"
DECYPHARR_URL = "http://decypharr:8282"
DECYPHARR_MANUAL_CATEGORY = "manual"
GLANCES_URL = "http://glances:61208"
BAZARR_URL = "http://bazarr:6767"
BAZARR_API_KEY = os.environ.get("BAZARR_API_KEY")
NZBDAV_URL = "http://nzbdav:3000"
NZBDAV_API_KEY = os.environ.get("NZBDAV_API_KEY")
ZILEAN_POSTGRES_PASSWORD = os.environ.get("ZILEAN_POSTGRES_PASSWORD")
HOST_IP = os.environ.get("HOST_IP")
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
    },
    "sonarr": {
        "url": "http://sonarr:8989",
        "api": "v3",
        "key": os.environ["SONARR_API_KEY"],
        "search_command": "MissingEpisodeSearch",
        "label": "Sonarr",
    },
}

# Unstick/manual-import only make sense for apps with a download queue that
# actually gets stuck on import matching - just Radarr/Sonarr now that
# Lidarr/Readarr are gone.
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
    "bazarr": ("Bazarr", None),
    "prowlarr": ("Prowlarr", None),
    "plex": ("Plex", None),
    "zurg": ("Zurg", "Real-Debrid mount"),
    "rclone-alldebrid": ("rclone", "AllDebrid mount"),
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
    "control-panel": ("Control Panel", "this dashboard"),
}

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


@app.get("/api/containers")
def containers_list():
    """Full container grid data - state, health, image, and live CPU/memory
    for every container in this compose project, discovered live from
    Docker rather than a hardcoded list."""
    me, containers = project_containers()
    out = []
    for c in sorted(containers, key=lambda c: c.name):
        label, note = CONTAINER_LABELS.get(c.name, (c.name, None))
        health = c.attrs.get("State", {}).get("Health", {}).get("Status")
        image_tags = c.image.tags
        image = image_tags[0] if image_tags else (c.image.short_id or "")
        service = c.labels.get("com.docker.compose.service", c.name)
        out.append({
            "name": c.name,
            "label": label,
            "note": note,
            "service": service,
            "image": image,
            "state": c.status,
            "health": health,
            "is_self": c.id == me.id,
            **container_stats(c),
        })
    return out


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
def plex_empty_trash():
    try:
        sections = plex_sections()
        for s in sections:
            r = httpx.put(
                f"{PLEX_URL}/library/sections/{s['key']}/emptyTrash",
                headers=plex_headers(),
                timeout=30,
            )
            r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"Empty trash failed: {e}")
    return ok(f"Trash emptied on {len(sections)} librar{'y' if len(sections) == 1 else 'ies'}.")


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
# Bazarr - runs its own "Search for Missing Series/Movies Subtitles" tasks
# every 6 hours on a schedule; this bypasses that wait the same way Kometa's
# run button bypasses its own 05:00 schedule. Uses Bazarr's generic
# scheduler endpoint (POST /api/system/tasks, taskid=<job_id>) rather than a
# per-item subtitle-search call - one click searches the whole library's
# wanted list, matching the arr apps' own "Search missing" pattern below.
# ---------------------------------------------------------------------
def bazarr_headers():
    if not BAZARR_API_KEY:
        fail("Bazarr isn't configured (BAZARR_API_KEY not set)", status_code=503)
    return {"X-API-KEY": BAZARR_API_KEY}


@app.post("/api/bazarr/search-wanted")
def bazarr_search_wanted():
    for task_id in ("wanted_search_missing_subtitles_series", "wanted_search_missing_subtitles_movies"):
        try:
            r = httpx.post(
                f"{BAZARR_URL}/api/system/tasks",
                data={"taskid": task_id},
                headers=bazarr_headers(),
                timeout=15,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            fail(f"Bazarr search-wanted ({task_id}) failed: {e}")
    return ok("Bazarr is searching for every missing series and movie subtitle now.")


# ---------------------------------------------------------------------
# NzbDAV - Usenet streaming layer (WebDAV + rclone, no local disk - see
# CHANGELOG.md [10.1.0]). Talks to its own SABnzbd-compatible query API
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
        # Idempotent - safe to call before every add rather than tracking
        # whether it already exists.
        httpx.post(
            f"{DECYPHARR_URL}/api/v2/torrents/createCategory",
            data={"category": DECYPHARR_MANUAL_CATEGORY, "savePath": f"/app/downloads/{DECYPHARR_MANUAL_CATEGORY}"},
            timeout=15,
        )
        r = httpx.post(
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
            match = f.get("movie") or f.get("series")
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
            else:
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
MOUNT_PROVIDERS = {"zurg", "decypharr", "decypharr-alldebrid", "rclone-alldebrid"}
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

    providers = [c for c in targets if c.name in MOUNT_PROVIDERS]
    dependents = [c for c in targets if c.name in MOUNT_DEPENDENTS]
    rest = [c for c in targets if c.name not in MOUNT_PROVIDERS and c.name not in MOUNT_DEPENDENTS]

    def worker():
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


app.mount("/", StaticFiles(directory="static", html=True), name="static")
