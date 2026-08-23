"""letterboxd/views.py template view tests."""

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
    monkeypatch.setattr("letterboxd.services.list_tracked", lambda: {
        "lists": [{"id": 1, "url": "https://letterboxd.com/user/list/test/",
                    "label": "Test List", "lastSyncedAt": "2026-01-01"}],
        "message": "1 list",
    })
    monkeypatch.setattr("letterboxd.services.get_history", lambda: {
        "runs": [{"listUrl": "https://letterboxd.com/user/list/test/",
                   "added": 5, "already": 10, "tvCrossover": 0,
                   "runAt": "2026-01-01T00:00", "errorDetail": None}],
        "message": "1 run",
    })


class TestLetterboxdPage:
    def test_letterboxd_page_renders(self, authed_client):
        response = authed_client.get("/letterboxd/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Letterboxd" in content
        assert "Test List" in content

    def test_letterboxd_page_unauth_redirects(self, db):
        client = Client()
        response = client.get("/letterboxd/")
        assert response.status_code == 302