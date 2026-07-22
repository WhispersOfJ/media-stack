from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def test_healthz(cp_app):
    client = TestClient(cp_app.app)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_api_status_reports_state_and_health_per_container(cp_app, monkeypatch):
    me = MagicMock()
    me.labels = {"com.docker.compose.project": "media-stack"}

    container = MagicMock()
    container.name = "radarr"
    container.status = "running"
    container.attrs = {"State": {"Health": {"Status": "healthy"}}}

    monkeypatch.setattr(cp_app, "own_container", lambda: me)
    cp_app.docker_client.containers.list.return_value = [container]

    client = TestClient(cp_app.app)
    r = client.get("/api/status")
    assert r.status_code == 200
    assert r.json() == {"radarr": {"state": "running", "health": "healthy"}}


def test_api_status_container_with_no_healthcheck(cp_app, monkeypatch):
    me = MagicMock()
    me.labels = {"com.docker.compose.project": "media-stack"}

    container = MagicMock()
    container.name = "plex"
    container.status = "running"
    container.attrs = {"State": {}}

    monkeypatch.setattr(cp_app, "own_container", lambda: me)
    cp_app.docker_client.containers.list.return_value = [container]

    client = TestClient(cp_app.app)
    r = client.get("/api/status")
    assert r.json() == {"plex": {"state": "running", "health": None}}


def test_project_containers_fails_without_compose_label(cp_app, monkeypatch):
    me = MagicMock()
    me.labels = {}
    monkeypatch.setattr(cp_app, "own_container", lambda: me)

    with pytest.raises(HTTPException):
        cp_app.project_containers()


def test_arr_command_rejects_unknown_app(cp_app):
    with pytest.raises(HTTPException) as exc:
        cp_app.arr_command("not-a-real-app", "RssSync")
    assert exc.value.status_code == 404


def test_api_hit_counts_endpoint_returns_seeded_counter(cp_app):
    client = TestClient(cp_app.app)
    r = client.get("/api/api-hit-counts")
    assert r.status_code == 200
    body = r.json()
    # Seeded at 0 for every known app at import time (app.py:205) so the
    # dashboard shows every badge from a cold start, not just ones hit once.
    assert "Radarr" in body["counts"]
    assert body["counts"]["Radarr"] == 0
    assert body["total"] == 0
