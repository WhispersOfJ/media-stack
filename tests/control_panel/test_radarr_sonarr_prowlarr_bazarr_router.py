"""Phase 3 validation for .claude/plans/evolved-control-panel-backend.plan.md:
the app-specific routers (services/radarr, services/sonarr, services/prowlarr,
services/bazarr), ported from app.py.
"""
from unittest.mock import MagicMock

import httpx
from fastapi.testclient import TestClient


def _login(client, main_module, password="correct-horse-battery-staple"):
    from core.security import hash_password
    from models.user import User

    db = main_module.SessionLocal()
    try:
        db.add(User(username="admin", password_hash=hash_password(password)))
        db.commit()
    finally:
        db.close()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert resp.status_code == 200


def _service_key_header(main_module):
    from core.security import hash_api_key
    from models.api_key import ApiKey

    db = main_module.SessionLocal()
    try:
        db.add(ApiKey(name="healthcheck-cron", key_hash=hash_api_key("raw-service-key")))
        db.commit()
    finally:
        db.close()
    return {"X-Api-Key": "raw-service-key"}


def _json_response(payload, status_code=200, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
    return resp


# ---------------------------------------------------------------------
# Radarr: Letterboxd add + exclude
# ---------------------------------------------------------------------

def test_letterboxd_add_short_circuits_when_already_in_radarr(cp_main_app, monkeypatch):
    letterboxd_html = '<html>themoviedb.org/movie/603</html>'

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        if "letterboxd.com" in url:
            return MagicMock(text=letterboxd_html, raise_for_status=MagicMock())
        if "/movie" in url and params and params.get("tmdbId") == 603:
            return _json_response([{"id": 99, "title": "The Matrix", "year": 1999}])
        return _json_response({})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd", json={"url": "https://letterboxd.com/film/the-matrix/"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["alreadyAdded"] is True
    assert body["radarrId"] == 99


def test_letterboxd_add_rejects_non_letterboxd_url(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd", json={"url": "https://example.com/not-letterboxd"})
    assert resp.status_code == 400


def test_letterboxd_add_requires_session_not_service_key(cp_main_app):
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd", json={"url": "https://letterboxd.com/film/x/"}, headers=headers)
    assert resp.status_code == 401


def test_radarr_exclude_not_found_404s(cp_main_app, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response({}, status_code=404))
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/exclude", json={"movieId": 999})
    assert resp.status_code == 404


def test_radarr_exclude_posts_exclusion(cp_main_app, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response({"id": 5, "tmdbId": 603, "title": "The Matrix", "year": 1999}))
    posted = {}

    def fake_post(url, json=None, **kwargs):
        posted["json"] = json
        return _json_response({}, status_code=201)

    monkeypatch.setattr(httpx, "post", fake_post)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/exclude", json={"movieId": 5})
    assert resp.status_code == 200
    assert posted["json"]["tmdbId"] == 603


# ---------------------------------------------------------------------
# Sonarr: monitor-episodes-fix
# ---------------------------------------------------------------------

def test_monitor_episodes_fix_skips_season_zero(cp_main_app, monkeypatch):
    series = [{"id": 1, "monitored": True}]
    episodes = [
        {"id": 100, "seasonNumber": 0, "monitored": False},  # special - must stay untouched
        {"id": 101, "seasonNumber": 1, "monitored": False},  # real gap - must be fixed
        {"id": 102, "seasonNumber": 1, "monitored": True},
    ]

    def fake_get(url, params=None, **kwargs):
        if "/series" in url and "episode" not in url:
            return _json_response(series)
        if "/episode" in url:
            return _json_response(episodes)
        return _json_response({})

    put_calls = []
    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "put", lambda url, json=None, **k: (put_calls.append(json), _json_response({}))[1])

    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/sonarr/monitor-episodes-fix")
    assert resp.status_code == 200
    assert resp.json()["fixed"] == 1
    assert put_calls[0]["episodeIds"] == [101]


def test_monitor_episodes_fix_requires_session(cp_main_app):
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/arr/sonarr/monitor-episodes-fix", headers=headers)
    assert resp.status_code == 401


# ---------------------------------------------------------------------
# Prowlarr: indexers
# ---------------------------------------------------------------------

def test_prowlarr_indexers_counts_enabled(cp_main_app, monkeypatch):
    items = [{"name": "B", "enable": False, "priority": 2}, {"name": "A", "enable": True, "priority": 1}]
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response(items))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/prowlarr/indexers", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["name"] == "A"  # sorted
    assert "1/2 indexers enabled" in body["message"]


def test_prowlarr_indexers_no_key_503s(cp_main_app, monkeypatch):
    monkeypatch.setattr("services.prowlarr.router.PROWLARR_CFG", {
        "url": "http://prowlarr:9696", "api": "v1", "key": None, "label": "Prowlarr",
    })
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/prowlarr/indexers", headers=headers)
    assert resp.status_code == 503


# ---------------------------------------------------------------------
# Bazarr: wanted / search-missing / history / provider-status
# ---------------------------------------------------------------------

def _bazarr_key_file(tmp_path, monkeypatch):
    bazarr_dir = tmp_path / "bazarr" / "config"
    bazarr_dir.mkdir(parents=True)
    (bazarr_dir / "config.yaml").write_text("auth:\n  apikey: test-bazarr-key\n")
    monkeypatch.setattr("core.arr_client.HOST_CONFIG_DIR", str(tmp_path))


def test_bazarr_wanted_combines_movies_and_episodes(cp_main_app, monkeypatch, tmp_path):
    _bazarr_key_file(tmp_path, monkeypatch)

    def fake_get(url, headers=None, **kwargs):
        if "movies/wanted" in url:
            return _json_response({"data": [{"title": "Movie A"}]})
        if "episodes/wanted" in url:
            return _json_response({"data": [{"seriesTitle": "Show A", "episode_number": "S01E01"}]})
        return _json_response({})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/bazarr/wanted", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["movies"] == ["Movie A"]
    assert body["episodes"] == ["Show A - S01E01"]


def test_bazarr_wanted_no_key_500s(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("core.arr_client.HOST_CONFIG_DIR", str(tmp_path))  # no config.yaml present
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/bazarr/wanted", headers=headers)
    assert resp.status_code == 500


def test_bazarr_search_missing_triggers_both_tasks(cp_main_app, monkeypatch, tmp_path):
    _bazarr_key_file(tmp_path, monkeypatch)
    posted = []
    monkeypatch.setattr(httpx, "post", lambda url, headers=None, data=None, **k: (posted.append(data), _json_response({}))[1])
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/bazarr/search-missing", headers=headers)
    assert resp.status_code == 200
    assert len(posted) == 2
    assert {p["taskid"] for p in posted} == {
        "wanted_search_missing_subtitles_movies", "wanted_search_missing_subtitles_series",
    }


def test_bazarr_provider_status_flags_problems(cp_main_app, monkeypatch, tmp_path):
    _bazarr_key_file(tmp_path, monkeypatch)
    providers = {"data": [{"name": "opensubtitles", "status": "Good"}, {"name": "subscene", "status": "Throttled"}]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response(providers))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/bazarr/provider-status", headers=headers)
    assert resp.status_code == 200
    assert "subscene" in resp.json()["message"]


def test_bazarr_history_merges_movies_and_episodes(cp_main_app, monkeypatch, tmp_path):
    _bazarr_key_file(tmp_path, monkeypatch)

    def fake_get(url, headers=None, params=None, **kwargs):
        if "movies/history" in url:
            return _json_response({"data": [{"title": "M", "description": "downloaded", "provider": "p1"}]})
        if "episodes/history" in url:
            return _json_response({"data": [{"seriesTitle": "S", "description": "failed", "provider": "p2"}]})
        return _json_response({})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/bazarr/history", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2
