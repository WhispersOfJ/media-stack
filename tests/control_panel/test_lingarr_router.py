"""Phase 4 validation for .claude/plans/evolved-control-panel-backend.plan.md:
services/lingarr/router.py, ported from app.py. Covers auth gating,
Lingarr HTTP-lookup failure handling, response shaping, and the
container-log routes.
"""
import sys
from unittest.mock import MagicMock

import docker
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


def _response(data):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/lingarr/stats"),
    ("GET", "/api/lingarr/movies"),
    ("GET", "/api/lingarr/shows"),
    ("GET", "/api/lingarr/logs"),
    ("GET", "/api/lingarr/recent-translations"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path)
    assert resp.status_code == 401


def test_stats_502s_on_http_error(cp_main_app, monkeypatch):
    def fake_get(*a, **k):
        raise httpx.HTTPError("boom")
    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/lingarr/stats", headers=headers)
    assert resp.status_code == 502


def test_stats_reports_totals(cp_main_app, monkeypatch):
    data = {"totalSubtitles": 10, "totalMovies": 3, "totalEpisodes": 5}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _response(data))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/lingarr/stats", headers=headers)
    body = resp.json()
    assert body["totalSubtitles"] == 10
    assert "10 subtitle" in body["message"]


def test_movies_shapes_and_limits_items(cp_main_app, monkeypatch):
    data = {"items": [{"title": f"Movie {i}", "id": i} for i in range(5)]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _response(data))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/lingarr/movies?limit=2", headers=headers)
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["items"][0] == {"title": "Movie 0", "id": 0}


def test_shows_shapes_items(cp_main_app, monkeypatch):
    data = {"items": [{"title": "Show A"}]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _response(data))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/lingarr/shows", headers=headers)
    assert resp.json()["items"] == [{"title": "Show A"}]


def test_logs_502s_when_container_missing(cp_main_app):
    dc = sys.modules["core.docker_client"]
    dc.docker_client.containers.get.side_effect = docker.errors.NotFound("not found")
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/lingarr/logs", headers=headers)
    assert resp.status_code == 502


def test_logs_returns_raw_log_text(cp_main_app):
    dc = sys.modules["core.docker_client"]
    fake = MagicMock()
    fake.logs.return_value = b"lingarr started\n"
    dc.docker_client.containers.get.side_effect = None
    dc.docker_client.containers.get.return_value = fake
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/lingarr/logs", headers=headers)
    assert resp.json()["log"] == "lingarr started\n"


def test_recent_translations_filters_events(cp_main_app):
    dc = sys.modules["core.docker_client"]
    fake = MagicMock()
    fake.logs.return_value = (
        b"2026-08-05 checking file\n"
        b"2026-08-05 subtitle translated\n"
        b"2026-08-05 translation complete for Show S01E01\n"
    )
    dc.docker_client.containers.get.side_effect = None
    dc.docker_client.containers.get.return_value = fake
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/lingarr/recent-translations", headers=headers)
    body = resp.json()
    assert len(body["lines"]) == 2
