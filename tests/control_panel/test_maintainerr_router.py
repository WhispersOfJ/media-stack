"""Phase 4 validation for .claude/plans/evolved-control-panel-backend.plan.md:
services/maintainerr/router.py, ported from app.py. Covers auth gating,
safety-check's zero-rules-expected guard, plex-link-check's match/mismatch
branches, and the container-logs route's missing-container 404.
"""
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


def _json_response(payload, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
    return resp


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/maintainerr/rules"),
    ("GET", "/api/maintainerr/rule-detail?rule_id=1"),
    ("GET", "/api/maintainerr/collections"),
    ("GET", "/api/maintainerr/collection-media?collection_id=1"),
    ("GET", "/api/maintainerr/logs"),
    ("GET", "/api/maintainerr/safety-check"),
    ("GET", "/api/maintainerr/plex-link-check"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path)
    assert resp.status_code == 401


def test_rules_reports_none_configured(cp_main_app, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response([]))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/maintainerr/rules", headers=headers)
    assert "No rules configured" in resp.json()["message"]


def test_rules_shapes_items(cp_main_app, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response(
        [{"id": 1, "name": "Delete watched", "isActive": True}]))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/maintainerr/rules", headers=headers)
    assert resp.json()["items"][0]["name"] == "Delete watched"


def test_rule_detail_returns_full_rule(cp_main_app, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response({"id": 5, "name": "x"}))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/maintainerr/rule-detail?rule_id=5", headers=headers)
    assert resp.json()["rule"]["id"] == 5


def test_collections_shapes_media_count(cp_main_app, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response(
        [{"id": 1, "title": "Watched Movies", "media": [1, 2, 3]}]))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/maintainerr/collections", headers=headers)
    assert resp.json()["items"][0]["media_count"] == 3


def test_collection_media_returns_items(cp_main_app, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response([{"id": 1}, {"id": 2}]))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/maintainerr/collection-media?collection_id=1", headers=headers)
    assert resp.json()["message"] == "2 media item(s) in collection 1."


def test_logs_tails_container(cp_main_app, monkeypatch):
    import sys
    dc = sys.modules["core.docker_client"]
    fake = MagicMock()
    fake.logs.return_value = b"log line 1\nlog line 2"
    dc.docker_client.containers.get.return_value = fake
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/maintainerr/logs", headers=headers)
    assert resp.status_code == 200
    assert "log line 1" in resp.json()["log"]


def test_logs_404s_when_container_missing(cp_main_app, monkeypatch):
    import sys
    dc = sys.modules["core.docker_client"]
    dc.docker_client.containers.get.side_effect = docker.errors.NotFound("not found")
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/maintainerr/logs", headers=headers)
    assert resp.status_code == 502


def test_safety_check_reports_safe_with_no_active_rules(cp_main_app, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response(
        [{"id": 1, "name": "x", "isActive": False}]))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/maintainerr/safety-check", headers=headers)
    body = resp.json()
    assert body["active_count"] == 0
    assert "Safe" in body["message"]


def test_safety_check_warns_on_active_rules(cp_main_app, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response(
        [{"id": 1, "name": "Delete watched", "isActive": True}]))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/maintainerr/safety-check", headers=headers)
    body = resp.json()
    assert body["active_count"] == 1
    assert "WARNING" in body["message"]
    assert "Delete watched" in body["message"]


def test_plex_link_check_reports_match(cp_main_app, monkeypatch):
    monkeypatch.setenv("PLEX_URL", "http://real-plex:32400")
    monkeypatch.setattr("services.maintainerr.router.PLEX_URL", "http://real-plex:32400")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response({"plex_hostname": "real-plex"}))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/maintainerr/plex-link-check", headers=headers)
    assert resp.json()["matches"] is True


def test_plex_link_check_reports_mismatch(cp_main_app, monkeypatch):
    monkeypatch.setattr("services.maintainerr.router.PLEX_URL", "http://real-plex:32400")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _json_response({"plex_hostname": "wrong-host"}))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/maintainerr/plex-link-check", headers=headers)
    body = resp.json()
    assert body["matches"] is False
    assert "MISMATCH" in body["message"]
