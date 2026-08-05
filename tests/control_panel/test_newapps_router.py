"""Phase 4 validation for .claude/plans/evolved-control-panel-backend.plan.md:
services/newapps/router.py, ported from app.py. Covers auth gating, the
status sweep's healthy/down branches (including missing container and
unreachable HTTP), and the backup-check's missing-repo/error/missing-app
branches.
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


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/newapps/status"),
    ("GET", "/api/newapps/backup-check"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path)
    assert resp.status_code == 401


def test_status_reports_all_healthy(cp_main_app, monkeypatch):
    dc = sys.modules["core.docker_client"]

    def fake_get(name):
        fake = MagicMock()
        fake.status = "running"
        return fake

    dc.docker_client.containers.get.side_effect = fake_get

    def fake_http_get(url, timeout=None):
        resp = MagicMock()
        resp.status_code = 200
        return resp

    monkeypatch.setattr(httpx, "get", fake_http_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/newapps/status", headers=headers)
    body = resp.json()
    assert body["message"] == "All 8 new apps healthy."
    assert body["apps"]["tautulli"]["running"] is True
    assert body["apps"]["prefetcharr"]["reachable"] is None


def test_status_reports_missing_container(cp_main_app, monkeypatch):
    dc = sys.modules["core.docker_client"]

    def fake_get(name):
        if name == "checkrr":
            raise docker.errors.NotFound("not found")
        fake = MagicMock()
        fake.status = "running"
        return fake

    dc.docker_client.containers.get.side_effect = fake_get
    monkeypatch.setattr(httpx, "get", lambda *a, **k: MagicMock(status_code=200))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/newapps/status", headers=headers)
    body = resp.json()
    assert body["apps"]["checkrr"]["running"] is False
    assert "checkrr" in body["message"]


def test_status_reports_unreachable_http(cp_main_app, monkeypatch):
    dc = sys.modules["core.docker_client"]

    def fake_get(name):
        fake = MagicMock()
        fake.status = "running"
        return fake

    dc.docker_client.containers.get.side_effect = fake_get

    def fake_http_get(url, timeout=None):
        if "tautulli" in url:
            raise httpx.HTTPError("boom")
        return MagicMock(status_code=200)

    monkeypatch.setattr(httpx, "get", fake_http_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/newapps/status", headers=headers)
    body = resp.json()
    assert body["apps"]["tautulli"]["reachable"] is False
    assert "tautulli" in body["message"]


def test_backup_check_reports_missing_repo(cp_main_app, monkeypatch):
    monkeypatch.setattr("services.newapps.router.HOST_BACKUP_LOCAL", "/nonexistent-repo-path")
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/newapps/backup-check", headers=headers)
    body = resp.json()
    assert body["repo_status"] == "missing"


def test_backup_check_reports_all_present(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.newapps.router.HOST_BACKUP_LOCAL", str(tmp_path))
    listing = "\n".join(f"/config/{name}" for name in
                         ["tautulli", "wrapperr", "maintainerr", "checkrr", "prefetcharr", "lingarr", "kometa"])
    fake_result = MagicMock(returncode=0, stdout=listing, stderr="")
    monkeypatch.setattr("services.newapps.router._restic", lambda *a, **k: fake_result)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/newapps/backup-check", headers=headers)
    body = resp.json()
    assert body["missing"] == []


def test_backup_check_reports_missing_apps(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.newapps.router.HOST_BACKUP_LOCAL", str(tmp_path))
    fake_result = MagicMock(returncode=0, stdout="/config/tautulli\n/config/wrapperr", stderr="")
    monkeypatch.setattr("services.newapps.router._restic", lambda *a, **k: fake_result)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/newapps/backup-check", headers=headers)
    body = resp.json()
    assert "checkrr" in body["missing"]
    assert "NOT in the latest snapshot" in body["message"]


def test_backup_check_reports_restic_error(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.newapps.router.HOST_BACKUP_LOCAL", str(tmp_path))
    fake_result = MagicMock(returncode=1, stdout="", stderr="permission denied")
    monkeypatch.setattr("services.newapps.router._restic", lambda *a, **k: fake_result)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/newapps/backup-check", headers=headers)
    body = resp.json()
    assert body["repo_status"] == "error"
