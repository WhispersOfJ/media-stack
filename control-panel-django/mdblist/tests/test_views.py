"""mdblist/views.py template view tests."""

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
    monkeypatch.setattr("mdblist.services.list_tracked", lambda: {
        "lists": [{"id": 1, "url": "https://mdblist.com/lists/user/list/",
                    "label": "Test List", "lastSyncedAt": "2026-01-01"}],
        "message": "1 list",
    })
    monkeypatch.setattr("mdblist.services.get_history", lambda: {
        "runs": [{"listUrl": "https://mdblist.com/lists/user/list/",
                   "radarrAdded": 3, "radarrAlready": 5,
                   "runAt": "2026-01-01T00:00", "errorDetail": None}],
        "message": "1 run",
    })


class TestMDBListPage:
    def test_mdblist_page_renders(self, authed_client):
        response = authed_client.get("/mdblist/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "MDBList" in content
        assert "Test List" in content

    def test_mdblist_page_unauth_redirects(self, db):
        client = Client()
        response = client.get("/mdblist/")
        assert response.status_code == 302