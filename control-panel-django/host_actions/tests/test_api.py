import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

ENDPOINTS = [
    ("/api/v2/host/reboot", "host_actions.api.views.services.reboot"),
    ("/api/v2/host/pacman-sync", "host_actions.api.views.services.pacman_sync"),
    ("/api/v2/host/pacman-upgrade", "host_actions.api.views.services.pacman_upgrade"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("url,service_path", ENDPOINTS)
def test_confirmed_action_happy_path(authed_client, url, service_path):
    """POST with confirm=true calls the action function and returns its output."""
    with patch(service_path, return_value={"ok": True, "message": "did the thing", "returncode": 0}) as mock_fn:
        response = authed_client.post(
            url,
            json.dumps({"confirm": True}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )

    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["ok"] is True
    assert data["output"] == "did the thing"
    mock_fn.assert_called_once()


@pytest.mark.django_db
@pytest.mark.parametrize("url,service_path", ENDPOINTS)
def test_confirmed_action_rejects_missing_confirm(authed_client, url, service_path):
    """confirm defaults to false and missing/false confirm is rejected with 400
    BEFORE the action function is ever called."""
    with patch(service_path) as mock_fn:
        response = authed_client.post(
            url,
            json.dumps({}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )

    assert response.status_code == 400
    data = json.loads(response.content)
    assert data["ok"] is False
    mock_fn.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("url,service_path", ENDPOINTS)
def test_confirmed_action_rejects_explicit_confirm_false(authed_client, url, service_path):
    """confirm=false explicitly is also rejected with 400 before the action runs."""
    with patch(service_path) as mock_fn:
        response = authed_client.post(
            url,
            json.dumps({"confirm": False}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )

    assert response.status_code == 400
    mock_fn.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("url,service_path", ENDPOINTS)
def test_confirmed_action_502_when_helper_reports_failure(authed_client, url, service_path):
    """If call_host_helper's dict has ok=False, the view surfaces a 502, matching
    router.py's _run_host_action behavior (fail() with status_code=502)."""
    with patch(service_path, return_value={"ok": False, "message": "boom", "returncode": 1}):
        response = authed_client.post(
            url,
            json.dumps({"confirm": True}),
            content_type="application/json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )

    assert response.status_code == 502
    data = json.loads(response.content)
    assert data["ok"] is False


@pytest.mark.django_db
@pytest.mark.parametrize("url,service_path", ENDPOINTS)
def test_confirmed_action_service_client_gets_403(service_client, url, service_path):
    """Critical regression test: a service (API-key) client must NEVER be able to
    trigger irreversible host actions, even with confirm=true. Session cookie only."""
    response = service_client.post(
        url,
        {"confirm": True},
        format="json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code == 403


def test_confirmed_action_rejects_unauthenticated():
    """Fully unauthenticated requests are rejected on all three endpoints."""
    client = APIClient()
    for url, _ in ENDPOINTS:
        response = client.post(
            url,
            {"confirm": True},
            format="json",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
        assert response.status_code in (401, 403)


@pytest.mark.django_db
@pytest.mark.parametrize("url,service_path", ENDPOINTS)
def test_confirmed_action_accepts_bearer_token(authed_client, url, service_path):
    """Bearer token (Authorization: Bearer <key>) authenticates and allows
    host actions — the new standard for CLI/automation access to destructive
    endpoints. The authed_client fixture has a session, but this test passes
    the bearer header to verify the BearerTokenAuthentication path works."""
    # Create an API key for bearer auth
    from core.models import ApiKey
    from core.security import hash_api_key

    ApiKey.objects.create(name="bearer-test", key_hash=hash_api_key("bearer-token-123"))

    with patch(service_path, return_value={"ok": True, "message": "done", "returncode": 0}):
        response = authed_client.post(
            url,
            json.dumps({"confirm": True}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer bearer-token-123",
            HTTP_HOST="localhost",
            REMOTE_ADDR="127.0.0.1",
        )
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["ok"] is True


@pytest.mark.django_db
@pytest.mark.parametrize("url,service_path", ENDPOINTS)
def test_confirmed_action_rejects_invalid_bearer_token(url, service_path):
    """An invalid bearer token is rejected with 401 or 403."""
    client = APIClient()
    response = client.post(
        url,
        {"confirm": True},
        format="json",
        HTTP_AUTHORIZATION="Bearer invalid-token",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
@pytest.mark.parametrize("url,service_path", ENDPOINTS)
def test_confirmed_action_rejects_x_api_key_not_bearer(service_client, url, service_path):
    """X-Api-Key alone still gets 403 on host endpoints — callers must use
    the Bearer header instead."""
    response = service_client.post(
        url,
        {"confirm": True},
        format="json",
        HTTP_HOST="localhost",
        REMOTE_ADDR="127.0.0.1",
    )
    assert response.status_code == 403
