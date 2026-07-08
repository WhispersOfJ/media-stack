"""
Control Panel - one-click operational actions for The Stack.

Talks to the Docker socket (exec/restart) and to each app's own HTTP API
(Plex, Radarr, Sonarr, Lidarr, Readarr). No auth - LAN-only, matches every
other service in this stack (see README.md "Security note").
"""
import os
import time
from datetime import datetime, timezone

import docker
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

PLEX_URL = os.environ["PLEX_URL"].rstrip("/")
PLEX_TOKEN = os.environ["PLEX_TOKEN"]

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
def kometa_run():
    try:
        c = docker_client.containers.get("kometa")
    except docker.errors.NotFound:
        fail("Kometa container not found.")
    if c.status != "running":
        fail(f"Kometa container is {c.status}, not running.")
    try:
        # detach=True: fire the run and return immediately rather than
        # blocking the request for however long a full Kometa pass takes.
        c.exec_run(cmd=["python3", "/kometa.py", "--run"], detach=True)
    except Exception as e:
        fail(f"Failed to start Kometa run: {e}")
    return ok("Kometa run started - watch its container stats on Homepage for progress.")


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


app.mount("/", StaticFiles(directory="static", html=True), name="static")
