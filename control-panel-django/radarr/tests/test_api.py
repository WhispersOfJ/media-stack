from unittest.mock import patch

import pytest
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from core.api_base import ServiceError
from core.models import User
from radarr.api.views import ExcludeMovieView


@pytest.mark.django_db
def test_exclude_movie_view_happy_path():
    """POST /api/v2/radarr/exclude excludes a movie via session auth."""
    user = User.objects.create(username="testuser", password_hash="x")
    request = APIRequestFactory().post(
        "/api/v2/radarr/exclude", {"movieId": 123}, format="json"
    )
    force_authenticate(request, user=user)

    with patch("radarr.api.views.services.exclude_movie", return_value={"movieId": 123}):
        response = ExcludeMovieView.as_view()(request)

    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["movieId"] == 123
    assert response.data["message"] == "Movie excluded"


@pytest.mark.django_db
def test_exclude_movie_view_service_client_gets_403(service_client):
    """Service key clients are rejected (session-only endpoint)."""
    response = service_client.post("/api/v2/radarr/exclude", {"movieId": 123}, format="json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_exclude_movie_view_movie_not_found():
    """404 when movie not found in Radarr."""
    user = User.objects.create(username="testuser2", password_hash="x")
    request = APIRequestFactory().post(
        "/api/v2/radarr/exclude", {"movieId": 999}, format="json"
    )
    force_authenticate(request, user=user)

    with patch(
        "radarr.api.views.services.exclude_movie",
        side_effect=ServiceError("Movie 999 not found in Radarr", status=404),
    ):
        response = ExcludeMovieView.as_view()(request)

    assert response.status_code == 404
    assert response.data["ok"] is False
    assert "not found" in response.data["message"]


@pytest.mark.django_db
def test_exclude_movie_view_missing_movie_id():
    """400 when movieId missing from request."""
    user = User.objects.create(username="testuser3", password_hash="x")
    request = APIRequestFactory().post("/api/v2/radarr/exclude", {}, format="json")
    force_authenticate(request, user=user)

    response = ExcludeMovieView.as_view()(request)
    assert response.status_code == 400


def test_exclude_movie_view_rejects_unauthenticated():
    """Unauthenticated requests are rejected."""
    client = APIClient()
    response = client.post("/api/v2/radarr/exclude", {"movieId": 123}, format="json")
    assert response.status_code in (401, 403)
