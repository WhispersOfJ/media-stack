"""
Control Panel - one-click operational actions for The Stack.

Talks to the Docker socket (exec/restart) and to each app's own HTTP API
(Plex, Radarr, Sonarr, Lidarr, Readarr). No auth - LAN-only, matches every
other service in this stack (see README.md "Security note").
"""
import os
import re
import socket
import threading
from datetime import datetime, timezone
from urllib.parse import quote

import docker
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PLEX_URL = os.environ["PLEX_URL"].rstrip("/")
PLEX_TOKEN = os.environ["PLEX_TOKEN"]
ZILEAN_URL = "http://zilean:8181"
DECYPHARR_URL = "http://decypharr:8282"
DECYPHARR_MANUAL_CATEGORY = "manual"
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
    "lidarr": {
        "url": "http://lidarr:8686",
        "api": "v1",
        "key": os.environ["LIDARR_API_KEY"],
        "search_command": "MissingAlbumSearch",
        "label": "Lidarr",
    },
    "readarr": {
        "url": "http://readarr:8787",
        "api": "v1",
        "key": os.environ["READARR_API_KEY"],
        "search_command": "MissingBookSearch",
        "label": "Readarr",
    },
}

# Allow-listed restart targets only - never accept an arbitrary container
# name from the client, even though this is a trusted LAN tool.
RESTARTABLE_CONTAINERS = {
    "radarr": "Radarr — also clears the stale Zurg mount issue (v4.0.1)",
    "sonarr": "Sonarr",
    "lidarr": "Lidarr",
    "readarr": "Readarr",
    "bazarr": "Bazarr",
    "prowlarr": "Prowlarr",
    "plex": "Plex",
    "zurg": "Zurg (Real-Debrid mount)",
    "rclone-alldebrid": "rclone (AllDebrid mount)",
    "decypharr": "Decypharr",
    "nzbget": "NZBGet",
    "seerr": "Seerr",
    "tautulli": "Tautulli",
    "byparr": "Byparr",
    "kometa": "Kometa",
    "zilean": "Zilean",
}

app = FastAPI(title="Control Panel")
docker_client = docker.from_env()


class KometaRunRequest(BaseModel):
    libraries: list[str] | None = None


class ZileanSearchRequest(BaseModel):
    query: str


class GrabRequest(BaseModel):
    hash: str
    title: str | None = None


def own_container():
    # Docker sets the container's hostname to its own short ID by default -
    # lets this container find itself in the compose project without a
    # hardcoded name.
    return docker_client.containers.get(socket.gethostname())


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
    """Live running/health state for every restartable container, used to
    light up the status lamps on page load without a manual refresh."""
    out = {}
    for name in RESTARTABLE_CONTAINERS:
        try:
            c = docker_client.containers.get(name)
            health = c.attrs.get("State", {}).get("Health", {}).get("Status")
            out[name] = {"state": c.status, "health": health}
        except docker.errors.NotFound:
            out[name] = {"state": "missing", "health": None}
        except Exception as e:
            out[name] = {"state": "unknown", "health": None, "error": str(e)}
    return out


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
    return ok(f"Kometa run started ({scope}) - watch its container stats on Homepage for progress.")


# ---------------------------------------------------------------------
# Plex
# ---------------------------------------------------------------------
def plex_headers():
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
# Container restarts
# ---------------------------------------------------------------------
@app.post("/api/container/{name}/restart")
def container_restart(name: str):
    if name not in RESTARTABLE_CONTAINERS:
        fail(f"'{name}' is not a restartable service.", status_code=404)
    try:
        c = docker_client.containers.get(name)
        c.restart(timeout=30)
    except docker.errors.NotFound:
        fail(f"Container '{name}' not found.")
    except Exception as e:
        fail(f"Restart failed: {e}")
    return ok(f"{RESTARTABLE_CONTAINERS[name].split(' — ')[0]} restarted.")


# ---------------------------------------------------------------------
# Whole-stack restart
# ---------------------------------------------------------------------
@app.post("/api/stack/restart-all")
def stack_restart_all():
    try:
        me = own_container()
    except docker.errors.NotFound:
        fail("Could not find this container's own record - can't determine the compose project.")
    project = me.labels.get("com.docker.compose.project")
    if not project:
        fail("This container has no compose project label - can't tell what 'the stack' is.")
    containers = docker_client.containers.list(all=True, filters={"label": f"com.docker.compose.project={project}"})
    # Excludes itself - restarting the panel mid-request would just drop the
    # connection instead of confirming the sweep actually started.
    targets = [c for c in containers if c.id != me.id]
    if not targets:
        fail("No other containers found in this compose project.")
    names = sorted(c.name for c in targets)

    def worker():
        for c in targets:
            try:
                c.restart(timeout=30)
            except Exception as e:
                print(f"restart-all: failed to restart {c.name}: {e}")

    threading.Thread(target=worker, daemon=True).start()
    return ok(f"Restarting {len(names)} containers (everything except this panel): {', '.join(names)}")


app.mount("/", StaticFiles(directory="static", html=True), name="static")
