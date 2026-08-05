"""Phase 4 validation for .claude/plans/evolved-control-panel-backend.plan.md:
services/checkrr/router.py, ported from app.py. Covers auth gating,
badfiles CSV parsing, reacquire-guard's safe/flipped branches, and the
container-log routes' missing-container 502.
"""
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


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/checkrr/badfiles"),
    ("GET", "/api/checkrr/config"),
    ("GET", "/api/checkrr/reacquire-guard"),
    ("GET", "/api/checkrr/scan-status"),
    ("GET", "/api/checkrr/recent-scans"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path)
    assert resp.status_code == 401


def test_badfiles_reports_none_when_csv_missing(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.checkrr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/checkrr/badfiles", headers=headers)
    assert resp.json()["items"] == []


def test_badfiles_parses_csv_rows(cp_main_app, monkeypatch, tmp_path):
    checkrr_dir = tmp_path / "checkrr"
    checkrr_dir.mkdir(parents=True)
    (checkrr_dir / "badfiles.csv").write_text(
        "/media/movies/bad.mkv,corrupt moov atom\n/media/shows/bad2.mkv,truncated\n")
    monkeypatch.setattr("services.checkrr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/checkrr/badfiles", headers=headers)
    body = resp.json()
    assert body["total"] == 2
    assert body["items"][0]["reason"] == "corrupt moov atom"


def test_badfiles_respects_limit(cp_main_app, monkeypatch, tmp_path):
    checkrr_dir = tmp_path / "checkrr"
    checkrr_dir.mkdir(parents=True)
    rows = "\n".join(f"/media/f{i}.mkv,reason{i}" for i in range(5))
    (checkrr_dir / "badfiles.csv").write_text(rows + "\n")
    monkeypatch.setattr("services.checkrr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/checkrr/badfiles?limit=2", headers=headers)
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


def test_config_reports_checkpaths_and_process_flags(cp_main_app, monkeypatch, tmp_path):
    checkrr_dir = tmp_path / "checkrr"
    checkrr_dir.mkdir(parents=True)
    (checkrr_dir / "checkrr.yaml").write_text(
        "checkrr:\n  checkpath: ['/media/movies', '/media/shows']\n  cron: '0 3 * * *'\n"
        "arr:\n  radarr:\n    process: false\n  sonarr:\n    process: false\n")
    monkeypatch.setattr("services.checkrr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/checkrr/config", headers=headers)
    body = resp.json()
    assert body["checkpaths"] == ["/media/movies", "/media/shows"]
    assert body["process_flags"] == {"radarr": False, "sonarr": False}


def test_reacquire_guard_reports_safe(cp_main_app, monkeypatch, tmp_path):
    checkrr_dir = tmp_path / "checkrr"
    checkrr_dir.mkdir(parents=True)
    (checkrr_dir / "checkrr.yaml").write_text("arr:\n  radarr:\n    process: false\n")
    monkeypatch.setattr("services.checkrr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/checkrr/reacquire-guard", headers=headers)
    body = resp.json()
    assert body["flipped"] == []
    assert "Safe" in body["message"]


def test_reacquire_guard_warns_when_flipped(cp_main_app, monkeypatch, tmp_path):
    checkrr_dir = tmp_path / "checkrr"
    checkrr_dir.mkdir(parents=True)
    (checkrr_dir / "checkrr.yaml").write_text("arr:\n  radarr:\n    process: true\n  sonarr:\n    process: false\n")
    monkeypatch.setattr("services.checkrr.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/checkrr/reacquire-guard", headers=headers)
    body = resp.json()
    assert body["flipped"] == ["radarr"]
    assert "WARNING" in body["message"]


def test_scan_status_tails_container_logs(cp_main_app, monkeypatch):
    import sys
    dc = sys.modules["core.docker_client"]
    fake = MagicMock()
    fake.logs.return_value = b"line one\n\nline two"
    dc.docker_client.containers.get.return_value = fake
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/checkrr/scan-status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["lines"] == ["line one", "line two"]


def test_scan_status_502s_when_container_missing(cp_main_app, monkeypatch):
    import sys
    dc = sys.modules["core.docker_client"]
    dc.docker_client.containers.get.side_effect = docker.errors.NotFound("not found")
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/checkrr/scan-status", headers=headers)
    assert resp.status_code == 502


def test_recent_scans_filters_scan_cycle_markers(cp_main_app, monkeypatch):
    import sys
    dc = sys.modules["core.docker_client"]
    fake = MagicMock()
    fake.logs.return_value = (
        b"2026-08-05 checking file /media/movies/a.mkv\n"
        b"2026-08-05 Starting scan\n"
        b"2026-08-05 checking file /media/movies/b.mkv\n"
        b"2026-08-05 Finished scan\n"
    )
    dc.docker_client.containers.get.return_value = fake
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/checkrr/recent-scans", headers=headers)
    body = resp.json()
    assert len(body["lines"]) == 2
    assert "Starting scan" in body["lines"][0]
    assert "Finished scan" in body["lines"][1]
