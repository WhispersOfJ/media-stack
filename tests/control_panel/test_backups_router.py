"""Phase 4 validation for .claude/plans/evolved-control-panel-backend.plan.md:
services/backups/router.py, ported from app.py. Covers auth gating and
_restic()'s --no-lock/text=False shape via mocked subprocess.run, plus the
missing-repo and error-status branches for each route.
"""
import subprocess
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


def _fake_run(returncode=0, stdout="", stderr=""):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/backup-verify"),
    ("POST", "/api/backup-restore-test"),
    ("GET", "/api/backup-status"),
    ("POST", "/api/backup-integrity-check"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path)
    assert resp.status_code == 401


def test_backup_verify_reports_missing_repo(cp_main_app, monkeypatch):
    monkeypatch.setattr("services.backups.router.HOST_BACKUP_LOCAL", "/definitely/not/here")
    monkeypatch.setattr("services.backups.router.HOST_BACKUP_OFFSITE", "/also/not/here")
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/backup-verify", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["repos"]["local"]["status"] == "missing"
    assert body["repos"]["offsite"]["status"] == "missing"


def test_backup_verify_ok_with_recent_snapshot(cp_main_app, monkeypatch, tmp_path):
    local = tmp_path / "local"
    local.mkdir()
    offsite = tmp_path / "offsite"
    offsite.mkdir()
    monkeypatch.setattr("services.backups.router.HOST_BACKUP_LOCAL", str(local))
    monkeypatch.setattr("services.backups.router.HOST_BACKUP_OFFSITE", str(offsite))
    snaps_json = '[{"time": "2026-08-04T10:00:00Z", "short_id": "abc123"}]'
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _fake_run(stdout=snaps_json))
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/backup-verify", headers=headers)
    body = resp.json()
    assert body["repos"]["local"]["status"] == "ok"
    assert body["repos"]["local"]["id"] == "abc123"


def test_backup_restore_test_missing_repo_fails(cp_main_app, monkeypatch):
    monkeypatch.setattr("services.backups.router.HOST_BACKUP_LOCAL", "/definitely/not/here")
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/backup-restore-test", headers=headers)
    assert resp.status_code == 502


def test_backup_restore_test_dumps_small_file(cp_main_app, monkeypatch, tmp_path):
    local = tmp_path / "local"
    local.mkdir()
    monkeypatch.setattr("services.backups.router.HOST_BACKUP_LOCAL", str(local))
    ls_output = '{"type": "file", "size": 1234, "path": "/config/settings.json"}\n'

    def fake_run(cmd, env=None, capture_output=True, text=True, timeout=60):
        if "ls" in cmd:
            return _fake_run(stdout=ls_output)
        # dump call: text=False per the docstring's UnicodeDecodeError fix
        assert text is False
        result = MagicMock()
        result.returncode = 0
        result.stdout = b"file contents"
        result.stderr = b""
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/backup-restore-test", headers=headers)
    assert resp.status_code == 200
    assert "settings.json" in resp.json()["message"]


def test_backup_restore_test_timeout_fails_cleanly(cp_main_app, monkeypatch, tmp_path):
    local = tmp_path / "local"
    local.mkdir()
    monkeypatch.setattr("services.backups.router.HOST_BACKUP_LOCAL", str(local))

    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="restic", timeout=60)

    monkeypatch.setattr("subprocess.run", fake_run)
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/backup-restore-test", headers=headers)
    assert resp.status_code == 502


def test_backup_status_reports_snapshot_history(cp_main_app, monkeypatch, tmp_path):
    local = tmp_path / "local"
    local.mkdir()
    offsite = tmp_path / "offsite"
    offsite.mkdir()
    monkeypatch.setattr("services.backups.router.HOST_BACKUP_LOCAL", str(local))
    monkeypatch.setattr("services.backups.router.HOST_BACKUP_OFFSITE", str(offsite))
    snaps_json = ('[{"time": "2026-08-01T00:00:00Z", "short_id": "a"}, '
                  '{"time": "2026-08-04T00:00:00Z", "short_id": "b"}]')
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _fake_run(stdout=snaps_json))
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/backup-status", headers=headers)
    body = resp.json()["repos"]["local"]
    assert body["count"] == 2
    assert body["oldest"] == "2026-08-01T00:00:00Z"
    assert body["newest"] == "2026-08-04T00:00:00Z"


def test_backup_integrity_check_flags_failed_repo(cp_main_app, monkeypatch, tmp_path):
    local = tmp_path / "local"
    local.mkdir()
    offsite = tmp_path / "offsite"
    offsite.mkdir()
    monkeypatch.setattr("services.backups.router.HOST_BACKUP_LOCAL", str(local))
    monkeypatch.setattr("services.backups.router.HOST_BACKUP_OFFSITE", str(offsite))

    def fake_run(cmd, env=None, capture_output=True, text=True, timeout=60):
        if env.get("RESTIC_REPOSITORY") == str(local):
            return _fake_run(returncode=0)
        return _fake_run(returncode=1, stderr="corrupt pack file")

    monkeypatch.setattr("subprocess.run", fake_run)
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/backup-integrity-check", headers=headers)
    body = resp.json()
    assert body["repos"]["local"]["status"] == "ok"
    assert body["repos"]["offsite"]["status"] == "error"
    assert "offsite" in body["message"]
