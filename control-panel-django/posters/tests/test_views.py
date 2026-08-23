"""posters/views.py template view tests."""

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
    monkeypatch.setattr("posters.services.list_libraries", lambda: {
        "items": [{"key": "1", "title": "Movies", "type": "movie"}],
        "message": "1 library",
    })
    monkeypatch.setattr("posters.services.gallery", lambda library, offset=0, limit=60: {
        "items": [{"ratingKey": "k1", "title": "Film", "year": 2023,
                    "thumbUrl": "/api/v2/posters/thumb/k1"}],
        "total": 1, "offset": 0, "limit": 60, "library": library, "type": "movie",
        "message": "ok",
    })


class TestPostersPage:
    def test_posters_page_renders(self, authed_client):
        response = authed_client.get("/posters/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Poster" in content
        assert "Movies" in content

    def test_posters_page_unauth_redirects(self, db):
        client = Client()
        response = client.get("/posters/")
        assert response.status_code == 302

    def test_posters_gallery_partial(self, authed_client):
        response = authed_client.get("/posters/_gallery/Movies/")
        assert response.status_code == 200
        assert "Film" in response.content.decode()