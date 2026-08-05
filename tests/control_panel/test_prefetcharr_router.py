"""Phase 4 validation for .claude/plans/evolved-control-panel-backend.plan.md:
services/prefetcharr/router.py, ported from app.py. Covers auth gating,
log-file tailing (present/absent), env-parsed config, and the
plex-link-check match/mismatch branches.
"""
import sys
from unittest.mock import MagicMock

import docker
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


def _fake_container(env_lines):
    fake = MagicMock()
    fake.status = "running"
    fake.attrs = {"Config": {"Env": env_lines}}
    return fake


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/prefetcharr/logs"),
    ("GET", "/api/prefetcharr/status"),
    ("GET", "/api/prefetcharr/config"),
    ("GET", "/api/prefetcharr/plex-link-check"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path)
    assert resp.status_code == 401


def test_logs_reports_none_when_no_log_file(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.prefetcharr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/prefetcharr/logs", headers=headers)
    assert resp.json()["lines"] == []


def test_logs_tails_most_recent_log_file(cp_main_app, monkeypatch, tmp_path):
    pf_dir = tmp_path / "prefetcharr"
    pf_dir.mkdir(parents=True)
    (pf_dir / "prefetcharr.2026-08-04.log").write_text("old line\n")
    (pf_dir / "prefetcharr.2026-08-05.log").write_text("line one\nline two\n")
    monkeypatch.setattr("services.prefetcharr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/prefetcharr/logs?lines=1", headers=headers)
    body = resp.json()
    assert body["lines"] == ["line two"]


def test_status_502s_when_container_missing(cp_main_app):
    dc = sys.modules["core.docker_client"]
    dc.docker_client.containers.get.side_effect = docker.errors.NotFound("not found")
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/prefetcharr/status", headers=headers)
    assert resp.status_code == 502


def test_status_reports_running_and_last_event(cp_main_app, monkeypatch, tmp_path):
    pf_dir = tmp_path / "prefetcharr"
    pf_dir.mkdir(parents=True)
    (pf_dir / "prefetcharr.log").write_text("2026-08-05 requesting next season\n")
    monkeypatch.setattr("services.prefetcharr.router.HOST_CONFIG_DIR", str(tmp_path))
    dc = sys.modules["core.docker_client"]
    dc.docker_client.containers.get.side_effect = None
    dc.docker_client.containers.get.return_value = _fake_container([])
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/prefetcharr/status", headers=headers)
    body = resp.json()
    assert body["running"] is True
    assert "requesting next season" in body["last_event"]


def test_config_reads_env_blob(cp_main_app):
    dc = sys.modules["core.docker_client"]
    dc.docker_client.containers.get.side_effect = None
    dc.docker_client.containers.get.return_value = _fake_container(['PREFETCHARR_CONFIG=interval = 300'])
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/prefetcharr/config", headers=headers)
    assert resp.json()["config"] == "interval = 300"


def test_plex_link_check_reports_match(cp_main_app):
    dc = sys.modules["core.docker_client"]
    dc.docker_client.containers.get.side_effect = None
    dc.docker_client.containers.get.return_value = _fake_container(
        ['PREFETCHARR_CONFIG=url = "http://test-plex:32400"'])
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/prefetcharr/plex-link-check", headers=headers)
    body = resp.json()
    assert body["matches"] is True


def test_plex_link_check_reports_mismatch(cp_main_app):
    dc = sys.modules["core.docker_client"]
    dc.docker_client.containers.get.side_effect = None
    dc.docker_client.containers.get.return_value = _fake_container(
        ['PREFETCHARR_CONFIG=url = "http://stale-plex:32400"'])
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/prefetcharr/plex-link-check", headers=headers)
    body = resp.json()
    assert body["matches"] is False
    assert "MISMATCH" in body["message"]
