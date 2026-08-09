"""Phase 1 (PLANS.md) validation for services/ntfy/router.py: auth gating,
publish/topics/health response shaping, and setup-connections' already-
configured / newly-connected / failed branches across the 5 wired apps."""
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


def _resp(json_body, status_code=200):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_body
    r.raise_for_status = MagicMock()
    return r


@pytest.mark.parametrize("method,path,kwargs", [
    ("POST", "/api/ntfy/publish", {"json": {"topic": "x", "message": "y"}}),
    ("GET", "/api/ntfy/topics", {}),
    ("GET", "/api/ntfy/health", {}),
    ("POST", "/api/ntfy/setup-connections", {}),
])
def test_routes_require_auth(cp_main_app, method, path, kwargs):
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path, **kwargs)
    assert resp.status_code == 401


def test_publish_posts_to_topic(cp_main_app, monkeypatch):
    captured = {}

    def fake_post(url, content=None, headers=None, **k):
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        return _resp({})

    monkeypatch.setattr("services.ntfy.router.httpx.post", fake_post)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/ntfy/publish", json={"topic": "radarr-alerts", "message": "hello", "title": "Test"}, headers=headers)
    assert resp.status_code == 200
    assert captured["url"] == "http://ntfy:80/radarr-alerts"
    assert captured["content"] == b"hello"
    assert captured["headers"]["Title"] == "Test"


def test_publish_fails_when_ntfy_unreachable(cp_main_app, monkeypatch):
    def fake_post(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr("services.ntfy.router.httpx.post", fake_post)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/ntfy/publish", json={"topic": "x", "message": "y"}, headers=headers)
    assert resp.status_code == 502


def test_topics_lists_known_apps(cp_main_app):
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/ntfy/topics", headers=headers)
    assert resp.status_code == 200
    apps = {i["app"] for i in resp.json()["items"]}
    assert apps == {"radarr", "sonarr", "radarr_anime", "sonarr_anime", "prowlarr"}


def test_health_reports_healthy(cp_main_app, monkeypatch):
    monkeypatch.setattr("services.ntfy.router.httpx.get", lambda *a, **k: _resp({"healthy": True}))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/ntfy/health", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["healthy"] is True


def test_setup_connections_skips_already_configured(cp_main_app, monkeypatch):
    monkeypatch.setattr(
        "services.ntfy.router.httpx.get",
        lambda *a, **k: _resp([{"implementation": "Ntfy"}]),
    )
    post_calls = []
    monkeypatch.setattr("services.ntfy.router.httpx.post", lambda *a, **k: post_calls.append(1) or _resp({}))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/ntfy/setup-connections", headers=headers)
    assert resp.status_code == 200
    results = {r["app"]: r["status"] for r in resp.json()["results"]}
    assert results["radarr"] == "already configured"
    assert not post_calls


def test_setup_connections_adds_missing_and_reports_failures(cp_main_app, monkeypatch):
    def fake_get(url, headers=None, **k):
        if "sonarr" in url and "anime" not in url:
            raise httpx.ConnectError("down")
        return _resp([])

    monkeypatch.setattr("services.ntfy.router.httpx.get", fake_get)
    monkeypatch.setattr("services.ntfy.router.httpx.post", lambda *a, **k: _resp({}))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/ntfy/setup-connections", headers=headers)
    assert resp.status_code == 200
    results = {r["app"]: r["status"] for r in resp.json()["results"]}
    assert results["radarr"].startswith("connected")
    assert results["sonarr"].startswith("failed")
