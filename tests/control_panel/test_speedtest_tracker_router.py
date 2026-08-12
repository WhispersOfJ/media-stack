"""Phase 2 (PLANS.md) validation for services/speedtest_tracker/router.py:
auth gating, latest/history/run response shaping, and the missing-token
error path."""
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


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/speedtest-tracker/latest"),
    ("GET", "/api/speedtest-tracker/history"),
    ("POST", "/api/speedtest-tracker/run"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path)
    assert resp.status_code == 401


def test_latest_fails_when_token_unset(cp_main_app, monkeypatch):
    monkeypatch.delenv("SPEEDTEST_TRACKER_API_TOKEN", raising=False)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/speedtest-tracker/latest", headers=headers)
    assert resp.status_code == 500


def test_latest_returns_shaped_result(cp_main_app, monkeypatch):
    monkeypatch.setenv("SPEEDTEST_TRACKER_API_TOKEN", "test-token")
    monkeypatch.setattr(
        "services.speedtest_tracker.router.httpx.get",
        lambda *a, **k: _resp({"data": {
            "download": 450, "upload": 95, "download_bits_human": "450 Mbps",
            "upload_bits_human": "95 Mbps", "status": "completed", "healthy": True,
            "created_at": "2024-01-15T10:30:00Z",
            "data": {"ping": {"latency": 15.5, "jitter": 2.3}},
        }}),
    )
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/speedtest-tracker/latest", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["download"] == 450
    assert body["upload"] == 95
    assert body["ping"] == 15.5
    assert body["jitter"] == 2.3


def test_latest_fails_when_unreachable(cp_main_app, monkeypatch):
    monkeypatch.setenv("SPEEDTEST_TRACKER_API_TOKEN", "test-token")

    def fake_get(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr("services.speedtest_tracker.router.httpx.get", fake_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/speedtest-tracker/latest", headers=headers)
    assert resp.status_code == 502


def test_history_filters_by_days(cp_main_app, monkeypatch):
    """Also a regression test for the real live-verification bug: the
    actual API returns "2026-08-12 02:15:00" (space-separated, no offset,
    Laravel's default cast) rather than the docs' "...T...Z" example -
    naive-vs-aware comparison against `cutoff` raised a 500 in production
    until the router started assuming a naive timestamp is UTC."""
    monkeypatch.setenv("SPEEDTEST_TRACKER_API_TOKEN", "test-token")
    from datetime import datetime, timedelta, timezone
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    monkeypatch.setattr(
        "services.speedtest_tracker.router.httpx.get",
        lambda *a, **k: _resp({"data": [
            {"download": 100, "upload": 10, "status": "completed", "created_at": "2020-01-01T00:00:00Z", "data": {}},
            {"download": 200, "upload": 20, "status": "completed", "created_at": recent, "data": {}},
        ]}),
    )
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/speedtest-tracker/history?days=7", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["download"] == 200


def test_run_now_triggers_and_reports_message(cp_main_app, monkeypatch):
    monkeypatch.setenv("SPEEDTEST_TRACKER_API_TOKEN", "test-token")
    captured = {}

    def fake_post(url, headers=None, **k):
        captured["url"] = url
        captured["headers"] = headers
        return _resp({"data": {"id": 1, "status": "queued"}, "message": "Speedtest queued successfully"})

    monkeypatch.setattr("services.speedtest_tracker.router.httpx.post", fake_post)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/speedtest-tracker/run", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["message"] == "Speedtest queued successfully"
    assert captured["url"] == "http://speedtest-tracker:80/api/v1/speedtests/run"
    assert captured["headers"]["Authorization"] == "Bearer test-token"


def test_run_now_fails_when_unreachable(cp_main_app, monkeypatch):
    monkeypatch.setenv("SPEEDTEST_TRACKER_API_TOKEN", "test-token")

    def fake_post(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr("services.speedtest_tracker.router.httpx.post", fake_post)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/speedtest-tracker/run", headers=headers)
    assert resp.status_code == 502
