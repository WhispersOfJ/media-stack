"""arr/views.py template view tests."""

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
    monkeypatch.setattr("arr.services.backlog_status", lambda: {
        "apps": {"radarr": {"label": "Radarr", "missing": 10, "rate_per_hour": 2.5, "eta": "4h"}},
    })
    monkeypatch.setattr("arr.services.queue_errors", lambda: {
        "apps": {"radarr": [{"title": "Bad File", "status": "downloadClientUnavailable", "messages": ["oops"]}]},
    })
    monkeypatch.setattr("arr.services.unstick", lambda app_name: {"removed": [], "errors": []})
    monkeypatch.setattr("arr.services.queue_autofix", lambda: {"message": "ok"})


class TestFleetPage:
    def test_fleet_page_renders(self, authed_client):
        response = authed_client.get("/fleet/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Fleet" in content
        assert "Radarr" in content

    def test_fleet_page_unauth_redirects(self, db):
        client = Client()
        response = client.get("/fleet/")
        assert response.status_code == 302

    def test_fleet_cards_partial(self, authed_client):
        response = authed_client.get("/fleet/_cards/")
        assert response.status_code == 200
        assert "Radarr" in response.content.decode()

    def test_queue_table_partial(self, authed_client):
        response = authed_client.get("/fleet/_queue/")
        assert response.status_code == 200
        assert "Bad File" in response.content.decode()

