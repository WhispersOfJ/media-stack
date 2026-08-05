"""Phase 4 validation for .claude/plans/evolved-control-panel-backend.plan.md:
services/tautulli/router.py, ported from app.py. Covers auth gating,
_tautulli_call()'s missing-key/error-result branches, response shaping for
every route, and sync-check's match/mismatch/unconfigured branches.
"""
from unittest.mock import MagicMock

import httpx
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


def _tautulli_key_file(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "tautulli"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.ini").write_text("[General]\napi_key = test-tautulli-key\n")
    monkeypatch.setattr("services.tautulli.router.HOST_CONFIG_DIR", str(tmp_path))


def _tautulli_response(data, result="success", message=None):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"response": {"result": result, "message": message, "data": data}}
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/tautulli/activity"),
    ("POST", "/api/tautulli/terminate-stream?session_key=abc"),
    ("GET", "/api/tautulli/history"),
    ("GET", "/api/tautulli/stats"),
    ("GET", "/api/tautulli/users"),
    ("GET", "/api/tautulli/user-history?user_id=1"),
    ("GET", "/api/tautulli/libraries"),
    ("GET", "/api/tautulli/recently-added"),
    ("GET", "/api/tautulli/server-info"),
    ("GET", "/api/tautulli/newsletters"),
    ("GET", "/api/tautulli/notifiers"),
    ("GET", "/api/tautulli/plays-by-date"),
    ("GET", "/api/tautulli/sync-check"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path)
    assert resp.status_code == 401


def test_tautulli_call_500s_when_no_key(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.tautulli.router.HOST_CONFIG_DIR", str(tmp_path))  # no config.ini
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/tautulli/activity", headers=headers)
    assert resp.status_code == 500


def test_tautulli_call_fails_on_error_result(cp_main_app, monkeypatch, tmp_path):
    _tautulli_key_file(tmp_path, monkeypatch)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _tautulli_response(None, result="error", message="bad apikey"))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/tautulli/activity", headers=headers)
    assert resp.status_code == 502
    assert "bad apikey" in resp.json()["detail"]["message"]


def test_activity_shapes_sessions(cp_main_app, monkeypatch, tmp_path):
    _tautulli_key_file(tmp_path, monkeypatch)
    data = {"stream_count": 1, "sessions": [{"session_key": "1", "user": "bear", "full_title": "Movie",
                                              "state": "playing", "transcode_decision": "direct play",
                                              "progress_percent": "42"}]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _tautulli_response(data))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/tautulli/activity", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["items"][0]["title"] == "Movie"


def test_terminate_stream_passes_session_key(cp_main_app, monkeypatch, tmp_path):
    _tautulli_key_file(tmp_path, monkeypatch)
    captured = {}

    def fake_get(url, params=None, **k):
        captured.update(params or {})
        return _tautulli_response(None)

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/tautulli/terminate-stream?session_key=42", headers=headers)
    assert resp.status_code == 200
    assert captured["session_key"] == "42"
    assert captured["cmd"] == "terminate_session"


def test_history_shapes_entries(cp_main_app, monkeypatch, tmp_path):
    _tautulli_key_file(tmp_path, monkeypatch)
    data = {"data": [{"full_title": "Show S01E01", "user": "bear", "date": 123, "percent_complete": 90}]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _tautulli_response(data))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/tautulli/history", headers=headers)
    assert resp.json()["items"][0]["title"] == "Show S01E01"


def test_stats_groups_by_category(cp_main_app, monkeypatch, tmp_path):
    _tautulli_key_file(tmp_path, monkeypatch)
    data = [{"stat_id": "top_movies", "rows": [{"title": "Movie A"}, {"title": "Movie B"}]}]
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _tautulli_response(data))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/tautulli/stats", headers=headers)
    assert resp.json()["stats"]["top_movies"] == ["Movie A", "Movie B"]


def test_users_shapes_lifetime_stats(cp_main_app, monkeypatch, tmp_path):
    _tautulli_key_file(tmp_path, monkeypatch)
    data = {"data": [{"friendly_name": "bear", "plays": 100, "duration": 5000, "last_seen": 999}]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _tautulli_response(data))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/tautulli/users", headers=headers)
    assert resp.json()["items"][0]["user"] == "bear"


def test_user_history_passes_user_id(cp_main_app, monkeypatch, tmp_path):
    _tautulli_key_file(tmp_path, monkeypatch)
    captured = {}

    def fake_get(url, params=None, **k):
        captured.update(params or {})
        return _tautulli_response({"data": []})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/tautulli/user-history?user_id=7", headers=headers)
    assert resp.status_code == 200
    assert captured["user_id"] == 7


def test_libraries_shapes_counts(cp_main_app, monkeypatch, tmp_path):
    _tautulli_key_file(tmp_path, monkeypatch)
    data = [{"section_name": "Movies", "count": 500, "section_type": "movie"}]
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _tautulli_response(data))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/tautulli/libraries", headers=headers)
    assert resp.json()["items"][0]["name"] == "Movies"


def test_recently_added_shapes_items(cp_main_app, monkeypatch, tmp_path):
    _tautulli_key_file(tmp_path, monkeypatch)
    data = {"recently_added": [{"full_title": "New Movie", "added_at": 123}]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _tautulli_response(data))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/tautulli/recently-added", headers=headers)
    assert resp.json()["items"][0]["title"] == "New Movie"


def test_server_info_returns_pms_fields(cp_main_app, monkeypatch, tmp_path):
    _tautulli_key_file(tmp_path, monkeypatch)
    data = {"pms_name": "Bear's Plex", "pms_ip": "1.2.3.4", "pms_port": "32400"}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _tautulli_response(data))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/tautulli/server-info", headers=headers)
    assert "Bear's Plex" in resp.json()["message"]


def test_newsletters_reports_none_configured(cp_main_app, monkeypatch, tmp_path):
    _tautulli_key_file(tmp_path, monkeypatch)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _tautulli_response([]))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/tautulli/newsletters", headers=headers)
    assert resp.json()["message"] == "No newsletters configured."


def test_notifiers_shapes_active_flag(cp_main_app, monkeypatch, tmp_path):
    _tautulli_key_file(tmp_path, monkeypatch)
    data = [{"id": 1, "agent_name": "Discord", "active": 1}]
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _tautulli_response(data))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/tautulli/notifiers", headers=headers)
    assert resp.json()["items"][0]["active"] is True


def test_plays_by_date_sums_series(cp_main_app, monkeypatch, tmp_path):
    _tautulli_key_file(tmp_path, monkeypatch)
    data = {"categories": ["Mon", "Tue"], "series": [{"data": [1, 2]}, {"data": [3, 4]}]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _tautulli_response(data))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/tautulli/plays-by-date", headers=headers)
    assert resp.json()["totals"] == [4, 6]


def test_sync_check_reports_match(cp_main_app, monkeypatch, tmp_path):
    _tautulli_key_file(tmp_path, monkeypatch)

    def fake_get(url, headers=None, params=None, timeout=None, **k):
        if "tautulli" in url:
            return _tautulli_response({"pms_identifier": "abc123", "pms_name": "Bear's Plex"})
        return MagicMock(json=lambda: {"MediaContainer": {"machineIdentifier": "abc123"}},
                          raise_for_status=MagicMock())

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/tautulli/sync-check", headers=headers)
    assert resp.json()["matches"] is True


def test_sync_check_reports_mismatch(cp_main_app, monkeypatch, tmp_path):
    _tautulli_key_file(tmp_path, monkeypatch)

    def fake_get(url, headers=None, params=None, timeout=None, **k):
        if "tautulli" in url:
            return _tautulli_response({"pms_identifier": "wrong-id", "pms_name": "Other Plex"})
        return MagicMock(json=lambda: {"MediaContainer": {"machineIdentifier": "abc123"}},
                          raise_for_status=MagicMock())

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/tautulli/sync-check", headers=headers)
    body = resp.json()
    assert body["matches"] is False
    assert "MISMATCH" in body["message"]


def test_sync_check_reports_unconfigured(cp_main_app, monkeypatch, tmp_path):
    _tautulli_key_file(tmp_path, monkeypatch)

    def fake_get(url, headers=None, params=None, timeout=None, **k):
        if "tautulli" in url:
            return _tautulli_response({})
        return MagicMock(json=lambda: {"MediaContainer": {"machineIdentifier": "abc123"}},
                          raise_for_status=MagicMock())

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/tautulli/sync-check", headers=headers)
    assert resp.json()["matches"] is False
