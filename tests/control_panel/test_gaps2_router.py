"""Phase 5 (PLANS.md) validation for services/gaps2/router.py.

The load-bearing behaviour here is push routing: the router - not GAPS-2 -
decides where a found gap goes, based on the Plex library it was found in.
Coverage is Movies -> radarr and Shows -> sonarr; the anime libraries were
removed from the table on 2026-08-12, and a test below asserts they stay out,
because re-adding one silently sends anime gaps to the general instance's
root folder and quality profile - an add that succeeds and lands in the wrong
place, with no error anywhere.

The rest covers the guards that make that routing trustworthy: gaps must come
from a single-library scan (a merged scan cannot be attributed), a pushed id
must actually appear in that library's missing list, and "never scanned" must
stay distinguishable from "nothing missing".
"""
import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


def _service_key_header(main_module):
    from core.security import hash_api_key
    from models.api_key import ApiKey

    db = main_module.SessionLocal()
    try:
        db.add(ApiKey(name="test-key", key_hash=hash_api_key("raw-service-key")))
        db.commit()
    finally:
        db.close()
    return {"X-Api-Key": "raw-service-key"}


def _resp(json_body, status_code=200):
    r = MagicMock()
    r.status_code = status_code
    r.content = b"{}"
    r.json.return_value = json_body
    r.raise_for_status = MagicMock()
    return r


# Each library's newest scan-history entry, keyed the way GAPS-2 stores them:
# `libraries` is a list, and only a single-entry one is attributable.
HISTORY = {
    "Movies": {"id": "hist-movies", "mediaType": "movie", "libraries": ["Movies"],
               "timestamp": "2026-08-12T16:00:00+00:00", "missing": 2, "totalOwned": 1200},
    "Shows": {"id": "hist-shows", "mediaType": "tv", "libraries": ["Shows"],
              "timestamp": "2026-08-12T17:00:00+00:00", "missing": 1, "totalOwned": 300},
}

GAPS = {
    "hist-movies": [
        {"tmdbId": 111, "name": "Alien 3", "year": 1992, "collectionName": "Alien Collection", "owned": False},
        {"tmdbId": 112, "name": "Alien Resurrection", "year": 1997, "collectionName": "Alien Collection", "owned": False},
    ],
    "hist-shows": [
        {"tvdbId": 331, "name": "Better Call Saul", "year": 2015, "franchiseName": "Breaking Bad", "owned": False},
    ],
}


def _mock_gaps2(monkeypatch, history=None, gaps=None):
    """Stand in for GAPS-2's about / scan-history / per-scan gaps endpoints."""
    history = HISTORY if history is None else history
    gaps = GAPS if gaps is None else gaps

    def fake_get(url, params=None, **k):
        if url.endswith("/api/about"):
            return _resp({"version": "2.10.0", "commit": "abc123"})
        if "/api/scan-history/" in url:
            entry_id = url.rsplit("/", 2)[-2]
            return _resp({"gaps": gaps.get(entry_id, [])})
        if url.endswith("/api/scan-history"):
            media_type = (params or {}).get("mediaType")
            entries = [e for e in history.values() if not media_type or e["mediaType"] == media_type]
            return _resp({"history": entries})
        return _resp({})

    monkeypatch.setattr("services.gaps2.router.httpx.get", fake_get)


@pytest.fixture(autouse=True)
def _reset_sweep_state():
    """The sweep flag is module-level, so a test that leaves it set would make
    every later scan test collect a spurious 409.

    Resets through sys.modules rather than importing the router directly: the
    router imports core.arr_client, which indexes os.environ["RADARR_API_KEY"]
    at import time, and those stand-ins are set by the cp_main_app fixture. An
    import here would run before that and KeyError every test in the file.
    """
    def reset():
        module = sys.modules.get("services.gaps2.router")
        if module is not None:
            module.SWEEP_STATE.update(
                {"running": False, "library": None, "done": [], "errors": [], "started": None}
            )

    reset()
    yield
    reset()


# --- auth -------------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("GET", "/api/gaps2/status"),
    ("POST", "/api/gaps2/scan"),
    ("GET", "/api/gaps2/missing"),
    ("POST", "/api/gaps2/push"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    assert client.request(method, path).status_code == 401


# --- the routing table ------------------------------------------------

def test_routing_table_covers_every_library_exactly_once():
    from services.gaps2.libraries import LIBRARIES, LIBRARY_NAMES

    assert len(LIBRARY_NAMES) == len(set(LIBRARY_NAMES)) == 2
    assert {lib["kind"] for lib in LIBRARIES} == {"movie", "show"}


def test_anime_libraries_stay_out_of_the_routing_table():
    """Dropped on 2026-08-12. Re-adding one is not a no-op: every route here
    derives its target instance from this table, so an anime entry pointing at
    radarr/sonarr would file anime titles under the general root folder and
    quality profile without erroring."""
    from services.gaps2.libraries import LIBRARIES, LIBRARY_NAMES

    assert "Anime Movies" not in LIBRARY_NAMES
    assert "Anime Shows" not in LIBRARY_NAMES
    assert not [lib for lib in LIBRARIES if lib["arr"].endswith("_anime")]


@pytest.mark.parametrize("library,arr,kind", [
    ("Movies", "radarr", "movie"),
    ("Shows", "sonarr", "show"),
])
def test_every_library_maps_to_the_expected_arr_instance(library, arr, kind):
    from services.gaps2.libraries import arr_for_library, kind_for_library

    assert arr_for_library(library) == arr
    assert kind_for_library(library) == kind


def test_routing_table_names_real_arr_instances(cp_main_app):
    """A typo'd arr key would only surface as a KeyError at push time, on the
    one code path that is hardest to exercise by accident.

    Takes cp_main_app purely for its env stand-ins: core.arr_client indexes
    os.environ["RADARR_API_KEY"] at import time.
    """
    from core.arr_client import ARR_APPS
    from services.gaps2.libraries import LIBRARIES

    for lib in LIBRARIES:
        assert lib["arr"] in ARR_APPS


# --- status -----------------------------------------------------------

def test_status_reports_last_scan_per_library(cp_main_app, monkeypatch):
    _mock_gaps2(monkeypatch)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/gaps2/status", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == "2.10.0"
    by_name = {lib["library"]: lib for lib in body["libraries"]}
    assert by_name["Movies"]["missing"] == 2
    assert by_name["Movies"]["arr"] == "radarr"
    assert by_name["Shows"]["arr"] == "sonarr"
    assert all(lib["scanned"] for lib in body["libraries"])


def test_status_calls_out_never_scanned_libraries(cp_main_app, monkeypatch):
    """Never scanned and zero gaps both render as 0 in a bare count and mean
    opposite things, so they must not collapse together."""
    _mock_gaps2(monkeypatch, history={"Movies": HISTORY["Movies"]})
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/gaps2/status", headers=_service_key_header(cp_main_app))
    body = resp.json()
    assert "Never scanned" in body["message"]
    by_name = {lib["library"]: lib for lib in body["libraries"]}
    assert by_name["Movies"]["scanned"] is True
    assert by_name["Shows"]["scanned"] is False
    assert by_name["Shows"]["missing"] is None


# --- missing ----------------------------------------------------------

def test_missing_tags_every_gap_with_its_target_arr(cp_main_app, monkeypatch):
    _mock_gaps2(monkeypatch)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/gaps2/missing", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    by_arr = {g["title"]: g["arr"] for g in body["missing"]}
    assert by_arr["Alien 3"] == "radarr"
    assert by_arr["Alien Resurrection"] == "radarr"
    assert by_arr["Better Call Saul"] == "sonarr"


def test_missing_uses_the_right_id_field_per_media_type(cp_main_app, monkeypatch):
    """Movies are pushed by tmdbId and shows by tvdbId; crossing them would
    look up an unrelated title in the target Arr."""
    _mock_gaps2(monkeypatch)
    client = TestClient(cp_main_app.app)
    body = client.get("/api/gaps2/missing", headers=_service_key_header(cp_main_app)).json()
    by_title = {g["title"]: g for g in body["missing"]}
    assert by_title["Alien 3"]["id_field"] == "tmdbId"
    assert by_title["Alien 3"]["id"] == 111
    assert by_title["Better Call Saul"]["id_field"] == "tvdbId"
    assert by_title["Better Call Saul"]["id"] == 331


def test_missing_filters_to_one_library(cp_main_app, monkeypatch):
    _mock_gaps2(monkeypatch)
    client = TestClient(cp_main_app.app)
    body = client.get("/api/gaps2/missing?library=Shows",
                      headers=_service_key_header(cp_main_app)).json()
    assert body["total"] == 1
    assert body["missing"][0]["library"] == "Shows"


def test_missing_excludes_owned_entries(cp_main_app, monkeypatch):
    """A scan run with showExisting records owned titles alongside gaps; they
    are not missing and must never reach a push."""
    gaps = dict(GAPS)
    gaps["hist-movies"] = [
        {"tmdbId": 111, "name": "Alien 3", "year": 1992, "collectionName": "Alien Collection", "owned": False},
        {"tmdbId": 113, "name": "Alien", "year": 1979, "collectionName": "Alien Collection", "owned": True},
    ]
    _mock_gaps2(monkeypatch, gaps=gaps)
    client = TestClient(cp_main_app.app)
    body = client.get("/api/gaps2/missing?library=Movies",
                      headers=_service_key_header(cp_main_app)).json()
    assert [g["id"] for g in body["missing"]] == [111]


def test_missing_ignores_multi_library_scans(cp_main_app, monkeypatch):
    """A merged scan's gaps carry no library field, so they cannot be routed.
    Treating one as a library's result would credit every gap in it to
    whichever library happened to be asking."""
    merged = {"Merged": {"id": "hist-merged", "mediaType": "movie",
                         "libraries": ["Movies", "Documentaries"],
                         "timestamp": "2026-08-12T18:00:00+00:00", "missing": 9, "totalOwned": 1955}}
    _mock_gaps2(monkeypatch, history=merged, gaps={"hist-merged": GAPS["hist-movies"]})
    client = TestClient(cp_main_app.app)
    body = client.get("/api/gaps2/missing", headers=_service_key_header(cp_main_app)).json()
    assert body["total"] == 0
    assert sorted(body["unscanned"]) == ["Movies", "Shows"]


def test_missing_reports_unscanned_separately_from_empty(cp_main_app, monkeypatch):
    _mock_gaps2(monkeypatch, history={"Movies": HISTORY["Movies"]})
    client = TestClient(cp_main_app.app)
    body = client.get("/api/gaps2/missing", headers=_service_key_header(cp_main_app)).json()
    assert "Never scanned" in body["message"]
    assert body["unscanned"] == ["Shows"]


def test_missing_limit_caps_list_but_not_total(cp_main_app, monkeypatch):
    _mock_gaps2(monkeypatch)
    client = TestClient(cp_main_app.app)
    body = client.get("/api/gaps2/missing?limit=2", headers=_service_key_header(cp_main_app)).json()
    assert body["total"] == 3
    assert len(body["missing"]) == 2


def test_missing_rejects_unknown_library(cp_main_app, monkeypatch):
    _mock_gaps2(monkeypatch)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/gaps2/missing?library=Documentaries",
                      headers=_service_key_header(cp_main_app))
    assert resp.status_code == 400


# --- push: the routing that matters -----------------------------------

@pytest.mark.parametrize("library,gap_id,expected_arr,expected_url", [
    ("Movies", 111, "radarr", "http://radarr:7878"),
    ("Movies", 112, "radarr", "http://radarr:7878"),
])
def test_movie_push_targets_radarr(cp_main_app, monkeypatch, library, gap_id, expected_arr, expected_url):
    _mock_gaps2(monkeypatch)
    seen = {}

    def fake_add(cfg, tmdb_id, monitored, search, root, profile, existing_tmdb_ids, **k):
        seen.update({"url": cfg["url"], "tmdb_id": tmdb_id, "root": root})
        return {"status": "added", "title": "Pushed Title"}

    monkeypatch.setattr("services.gaps2.router.radarr_root_folder_and_profile",
                        lambda cfg, a, b: ("/data/movies", 7))
    monkeypatch.setattr("services.gaps2.router.radarr_add_movie", fake_add)

    client = TestClient(cp_main_app.app)
    resp = client.post("/api/gaps2/push", json={"id": gap_id, "library": library},
                       headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    body = resp.json()
    assert body["arr"] == expected_arr
    assert seen["url"] == expected_url
    assert seen["tmdb_id"] == gap_id


@pytest.mark.parametrize("library,gap_id,expected_arr,expected_url", [
    ("Shows", 331, "sonarr", "http://sonarr:8989"),
])
def test_show_push_targets_sonarr(cp_main_app, monkeypatch, library, gap_id, expected_arr, expected_url):
    _mock_gaps2(monkeypatch)
    seen = {}

    def fake_add(cfg, tvdb_id, monitored, search, root, profile, existing_tvdb_ids, **k):
        seen.update({"url": cfg["url"], "tvdb_id": tvdb_id})
        return {"status": "added", "title": "Pushed Show"}

    monkeypatch.setattr("services.gaps2.router.sonarr_root_folder_and_profile",
                        lambda cfg, a, b: ("/data/shows", 3))
    monkeypatch.setattr("services.gaps2.router.sonarr_add_series", fake_add)

    client = TestClient(cp_main_app.app)
    resp = client.post("/api/gaps2/push", json={"id": gap_id, "library": library},
                       headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    assert resp.json()["arr"] == expected_arr
    assert seen["url"] == expected_url
    assert seen["tvdb_id"] == gap_id


def test_push_never_calls_the_movie_path_for_a_show(cp_main_app, monkeypatch):
    """Crossing the media types would send a tvdbId to Radarr's tmdb lookup,
    which resolves to a different title rather than failing."""
    _mock_gaps2(monkeypatch)

    def explode(*a, **k):
        raise AssertionError("radarr_add_movie must not be called for a show library")

    monkeypatch.setattr("services.gaps2.router.radarr_add_movie", explode)
    monkeypatch.setattr("services.gaps2.router.sonarr_root_folder_and_profile",
                        lambda cfg, a, b: ("/data/shows", 3))
    monkeypatch.setattr("services.gaps2.router.sonarr_add_series",
                        lambda *a, **k: {"status": "added", "title": "Show"})

    client = TestClient(cp_main_app.app)
    resp = client.post("/api/gaps2/push", json={"id": 331, "library": "Shows"},
                       headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200


def test_push_rejects_id_not_in_that_librarys_missing_list(cp_main_app, monkeypatch):
    """331 is a real gap, but in Shows - pushing it as a Movies gap would send
    a tvdbId to Radarr's tmdb lookup and add an unrelated title."""
    _mock_gaps2(monkeypatch)
    monkeypatch.setattr("services.gaps2.router.radarr_add_movie",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not add")))
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/gaps2/push", json={"id": 331, "library": "Movies"},
                       headers=_service_key_header(cp_main_app))
    assert resp.status_code == 400


def test_push_rejects_unknown_library(cp_main_app, monkeypatch):
    _mock_gaps2(monkeypatch)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/gaps2/push", json={"id": 111, "library": "Documentaries"},
                       headers=_service_key_header(cp_main_app))
    assert resp.status_code == 400


def test_push_refuses_when_library_was_never_scanned(cp_main_app, monkeypatch):
    _mock_gaps2(monkeypatch, history={})
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/gaps2/push", json={"id": 111, "library": "Movies"},
                       headers=_service_key_header(cp_main_app))
    assert resp.status_code == 409


def test_push_surfaces_an_arr_rejection(cp_main_app, monkeypatch):
    _mock_gaps2(monkeypatch)
    monkeypatch.setattr("services.gaps2.router.radarr_root_folder_and_profile",
                        lambda cfg, a, b: ("/data/movies", 7))
    monkeypatch.setattr("services.gaps2.router.radarr_add_movie",
                        lambda *a, **k: {"status": "failed", "reason": "already exists"})
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/gaps2/push", json={"id": 111, "library": "Movies"},
                       headers=_service_key_header(cp_main_app))
    assert resp.status_code == 502
    assert "already exists" in resp.json()["detail"]["message"]


# --- scan -------------------------------------------------------------

def test_scan_defaults_to_every_library(cp_main_app, monkeypatch):
    _mock_gaps2(monkeypatch)
    monkeypatch.setattr("services.gaps2.router.threading.Thread", lambda **k: MagicMock())
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/gaps2/scan", json={}, headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    assert resp.json()["libraries"] == ["Movies", "Shows"]


def test_scan_treats_blank_library_as_all(cp_main_app, monkeypatch):
    """The CLI sends an omitted optional argument as [""] (commands.json
    BodyFields Array), which must mean every library, not one named ""."""
    _mock_gaps2(monkeypatch)
    monkeypatch.setattr("services.gaps2.router.threading.Thread", lambda **k: MagicMock())
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/gaps2/scan", json={"libraries": [""]},
                       headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    assert resp.json()["libraries"] == ["Movies", "Shows"]


def test_scan_rejects_unknown_library(cp_main_app, monkeypatch):
    _mock_gaps2(monkeypatch)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/gaps2/scan", json={"libraries": ["Documentaries"]},
                       headers=_service_key_header(cp_main_app))
    assert resp.status_code == 400


def test_scan_refuses_to_overlap_a_running_sweep(cp_main_app, monkeypatch):
    """GAPS-2 keeps one scan slot per media type and 409s a second start, so
    overlapping sweeps would fight rather than queue."""
    from services.gaps2 import router as gaps2_router

    _mock_gaps2(monkeypatch)
    gaps2_router.SWEEP_STATE.update({"running": True, "library": "Movies"})
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/gaps2/scan", json={}, headers=_service_key_header(cp_main_app))
    assert resp.status_code == 409
