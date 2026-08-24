"""host/views.py template view tests."""

import pytest
from django.test import Client

from core.models import User


@pytest.fixture
def authed_client(db):
    user = User.objects.create(username="test", password_hash="x")
    from django.conf import settings
    client = Client()
    session = client.session
    session["user_id"] = user.id
    session.save()
    client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
    return client


@pytest.fixture(autouse=True)
def _mock_services(monkeypatch):
    monkeypatch.setattr("host.services.list_containers", lambda: [{
        "name": "radarr", "label": "Radarr", "image": "test/radarr:latest",
        "state": "running", "health": "healthy",
        "cpu_percent": 1.0, "mem_used_mb": 100,
    }])
    monkeypatch.setattr("host.services.host_resources", lambda: {
        "cpu_percent": 10.0, "mem_percent": 45.0,
        "mem_used": "7.2GB", "mem_total": "16.0GB",
    })
    monkeypatch.setattr("host.services.disk_health", lambda: {
        "mount": {"percent": 60.0, "free": "100GB"},
        "reclaimable": {},
        "total_reclaimable": "0B",
    })
    monkeypatch.setattr("host.services.mount_health", lambda: {
        "mounts": [{"mount": "remote/nzbdav", "status": "healthy"}],
        "message": "ok",
    })
    monkeypatch.setattr("host.services.restart_container", lambda name, activated=False: "ok")
    monkeypatch.setattr("host.services.stop_container", lambda name: "ok")
    monkeypatch.setattr("host.services.start_container", lambda name: "ok")
    monkeypatch.setattr("host.services.restart_all", lambda: "ok")


class TestHostPage:
    def test_host_page_renders(self, authed_client):
        response = authed_client.get("/host/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Host" in content
        assert "radarr" in content
        assert "10.0%" in content
        assert "running" in content

    def test_host_page_unauth_redirects(self, db):
        client = Client()
        response = client.get("/host/")
        assert response.status_code == 302

    def test_host_vitals_partial_renders(self, authed_client):
        response = authed_client.get("/host/_vitals/")
        assert response.status_code == 200
        assert "radarr" in response.content.decode()

