"""Phase 4 validation for .claude/plans/evolved-control-panel-backend.plan.md:
services/wrapperr/router.py, ported from app.py. Covers auth gating,
config.json-missing defaults, and tautulli-link-check's match/mismatch/
unconfigured branches (cross-checks services/tautulli's own key file).
"""
import json
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


def _wrapperr_config_file(tmp_path, monkeypatch, config: dict):
    cfg_dir = tmp_path / "wrapperr"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.json").write_text(json.dumps(config))
    monkeypatch.setattr("services.wrapperr.router.HOST_CONFIG_DIR", str(tmp_path))


def _tautulli_key_file(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "tautulli"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.ini").write_text("[General]\napi_key = real-tautulli-key\n")
    monkeypatch.setattr("services.tautulli.router.HOST_CONFIG_DIR", str(tmp_path))


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/wrapperr/status"),
    ("GET", "/api/wrapperr/reports"),
    ("GET", "/api/wrapperr/links"),
    ("GET", "/api/wrapperr/tautulli-link-check"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path)
    assert resp.status_code == 401


def test_status_reports_unconfigured_with_no_config(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.wrapperr.router.HOST_CONFIG_DIR", str(tmp_path))  # no config.json
    monkeypatch.setattr(httpx, "get", lambda *a, **k: MagicMock(status_code=200))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/wrapperr/status", headers=headers)
    body = resp.json()
    assert body["reachable"] is True
    assert body["configured"] is False


def test_status_reports_configured(cp_main_app, monkeypatch, tmp_path):
    _wrapperr_config_file(tmp_path, monkeypatch, {"tautulli_url": "http://tautulli:8181"})
    monkeypatch.setattr(httpx, "get", lambda *a, **k: MagicMock(status_code=200))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/wrapperr/status", headers=headers)
    assert resp.json()["configured"] is True


def test_status_reports_unreachable_on_connect_error(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.wrapperr.router.HOST_CONFIG_DIR", str(tmp_path))

    def fake_get(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/wrapperr/status", headers=headers)
    assert resp.json()["reachable"] is False


def test_reports_lists_saved_report_names(cp_main_app, monkeypatch, tmp_path):
    _wrapperr_config_file(tmp_path, monkeypatch, {"reports": [{"name": "Top Movies"}, {"title": "Top Users"}]})
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/wrapperr/reports", headers=headers)
    assert resp.json()["items"] == ["Top Movies", "Top Users"]


def test_reports_reports_none_saved_with_no_config(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.wrapperr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/wrapperr/reports", headers=headers)
    assert resp.json()["message"] == "No saved reports configured yet."


def test_links_lists_generated_links(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.wrapperr.router.HOST_CONFIG_DIR", str(tmp_path))
    links_dir = tmp_path / "wrapperr" / "links"
    links_dir.mkdir(parents=True)
    (links_dir / "abc123.json").write_text("{}")
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/wrapperr/links", headers=headers)
    assert resp.json()["items"] == ["abc123.json"]


def test_links_reports_none_when_dir_missing(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.wrapperr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/wrapperr/links", headers=headers)
    assert resp.json()["items"] == []


def test_tautulli_link_check_reports_match(cp_main_app, monkeypatch, tmp_path):
    _wrapperr_config_file(tmp_path, monkeypatch, {"tautulli_api_key": "real-tautulli-key"})
    _tautulli_key_file(tmp_path, monkeypatch)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/wrapperr/tautulli-link-check", headers=headers)
    assert resp.json()["matches"] is True


def test_tautulli_link_check_reports_mismatch(cp_main_app, monkeypatch, tmp_path):
    _wrapperr_config_file(tmp_path, monkeypatch, {"tautulli_api_key": "stale-key"})
    _tautulli_key_file(tmp_path, monkeypatch)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/wrapperr/tautulli-link-check", headers=headers)
    body = resp.json()
    assert body["matches"] is False
    assert "MISMATCH" in body["message"]


def test_tautulli_link_check_reports_no_saved_key(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.wrapperr.router.HOST_CONFIG_DIR", str(tmp_path))  # no config.json
    _tautulli_key_file(tmp_path, monkeypatch)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/wrapperr/tautulli-link-check", headers=headers)
    assert resp.json()["matches"] is False
