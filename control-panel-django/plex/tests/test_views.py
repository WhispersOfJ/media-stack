"""plex/views.py template view tests."""

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
    monkeypatch.setattr("plex.services.scan_health", lambda: {
        "state": "healthy",
        "message": "Plex is healthy.",
        "activities": [],
        "scanner_running": False,
        "mount_ok": True,
        "container": {"health": "healthy", "restart_count": 0},
        "dstate_threads": [],
        "recent_busy_db_errors": 0,
    })
    monkeypatch.setattr("plex.services.sessions", lambda: {
        "sessions": [{"title": "Movie", "user": "user", "decision": "direct play", "progress_pct": 50.0}],
        "message": "1 session",
    })
    monkeypatch.setattr("plex.services.get_updates", lambda: {
        "update_available": False, "running_version": "1.40",
    })


class TestPlexPage:
    def test_plex_page_renders(self, authed_client):
        response = authed_client.get("/plex/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Plex" in content
        assert "healthy" in content

    def test_plex_page_unauth_redirects(self, db):
        client = Client()
        response = client.get("/plex/")
        assert response.status_code == 302

    def test_plex_health_partial(self, authed_client):
        response = authed_client.get("/plex/_health/")
        assert response.status_code == 200
        assert "healthy" in response.content.decode()