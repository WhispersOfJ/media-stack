"""Phase 4 validation for .claude/plans/evolved-control-panel-backend.plan.md:
services/kometa/router.py, ported from app.py. Covers auth gating,
countdown-log parsing, run-now's exec_run trigger, last-run-result's
finished/error/neither branches, and config.yml library listing.
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


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/kometa/status"),
    ("POST", "/api/kometa/run-now"),
    ("GET", "/api/kometa/logs"),
    ("GET", "/api/kometa/last-run-result"),
    ("GET", "/api/kometa/config"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path)
    assert resp.status_code == 401


def test_status_502s_when_container_missing(cp_main_app):
    dc = sys.modules["core.docker_client"]
    dc.docker_client.containers.get.side_effect = docker.errors.NotFound("not found")
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/kometa/status", headers=headers)
    assert resp.status_code == 502


def test_status_parses_countdown_line(cp_main_app):
    dc = sys.modules["core.docker_client"]
    fake = MagicMock()
    fake.logs.return_value = b"Current Time: 10:00:00 | 2h left | next run at 12:00:00"
    dc.docker_client.containers.get.side_effect = None
    dc.docker_client.containers.get.return_value = fake
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/kometa/status", headers=headers)
    body = resp.json()
    assert body["current_time"] == "10:00:00"
    assert body["next_run"] == "12:00:00"


def test_status_reports_unparseable_log(cp_main_app):
    dc = sys.modules["core.docker_client"]
    fake = MagicMock()
    fake.logs.return_value = b"nothing useful here"
    dc.docker_client.containers.get.side_effect = None
    dc.docker_client.containers.get.return_value = fake
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/kometa/status", headers=headers)
    assert "Could not parse" in resp.json()["message"]


def test_run_now_triggers_detached_exec(cp_main_app):
    dc = sys.modules["core.docker_client"]
    fake = MagicMock()
    dc.docker_client.containers.get.side_effect = None
    dc.docker_client.containers.get.return_value = fake
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/kometa/run-now", headers=headers)
    assert resp.status_code == 200
    fake.exec_run.assert_called_once_with(["python3", "kometa.py", "--run"], detach=True)


def test_last_run_result_reports_finished(cp_main_app):
    dc = sys.modules["core.docker_client"]
    fake = MagicMock()
    fake.logs.return_value = b"doing work\nRun complete: 500 items updated\n"
    dc.docker_client.containers.get.side_effect = None
    dc.docker_client.containers.get.return_value = fake
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/kometa/last-run-result", headers=headers)
    assert "Run complete" in resp.json()["message"]


def test_last_run_result_reports_errors_when_no_finish(cp_main_app):
    dc = sys.modules["core.docker_client"]
    fake = MagicMock()
    fake.logs.return_value = b"Traceback (most recent call last):\nValueError: bad config\n"
    dc.docker_client.containers.get.side_effect = None
    dc.docker_client.containers.get.return_value = fake
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/kometa/last-run-result", headers=headers)
    body = resp.json()
    assert "error line" in body["message"]
    assert len(body["errors"]) > 0


def test_last_run_result_reports_no_run_yet(cp_main_app):
    dc = sys.modules["core.docker_client"]
    fake = MagicMock()
    fake.logs.return_value = b"waiting for scheduled time"
    dc.docker_client.containers.get.side_effect = None
    dc.docker_client.containers.get.return_value = fake
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/kometa/last-run-result", headers=headers)
    assert "No run has completed yet" in resp.json()["message"]


def test_config_reports_none_when_missing(cp_main_app, monkeypatch, tmp_path):
    monkeypatch.setattr("services.kometa.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/kometa/config", headers=headers)
    assert resp.json()["libraries"] == []


def test_config_lists_libraries(cp_main_app, monkeypatch, tmp_path):
    kometa_dir = tmp_path / "kometa"
    kometa_dir.mkdir(parents=True)
    (kometa_dir / "config.yml").write_text("libraries:\n  Movies:\n    collection_files:\n      - default: basic\n  TV Shows:\n    collection_files:\n      - default: basic\n")
    monkeypatch.setattr("services.kometa.router.HOST_CONFIG_DIR", str(tmp_path))
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.get("/api/kometa/config", headers=headers)
    body = resp.json()
    assert body["libraries"] == ["Movies", "TV Shows"]
