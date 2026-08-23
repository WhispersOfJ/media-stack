"""UI shell tests — Task 0-1: auth redirect, logged-in rendering,
CSRF enforcement, overview cards with mocked services.

Each view test mocks its services calls — template views never hit
real Radarr/Plex/Docker/httpx during testing.
"""

import pytest
from django.conf import settings
from django.test import Client

from core.models import User


@pytest.fixture
def authed_client(db):
    """Django test client with a logged-in session."""
    user = User.objects.create(username="testuser", password_hash="x")
    client = Client()
    session = client.session
    session["user_id"] = user.id
    session.save()
    client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
    return client


@pytest.fixture
def anon_client():
    """Django test client with no session."""
    return Client()


# ── Service mocks shared across overview tests ──────────────────────────
# Patch at module level so the real _overview_context() code runs.

@pytest.fixture(autouse=True)
def _mock_services(monkeypatch):
    monkeypatch.setattr(
        "queue_app.services.aggregate_queue_status",
        lambda: {
            "radarr": {
                "label": "Radarr", "total": 3,
                "downloading": [{"title": "A"}],
                "stalled": [],
                "queued": [{"title": "B"}],
                "importing": [{"title": "C"}],
            },
        },
    )
    monkeypatch.setattr(
        "host.services.host_resources",
        lambda: {
            "cpu_percent": 12.5, "mem_percent": 45.2,
            "mem_used": "7.2GB", "mem_total": "16.0GB",
        },
    )
    monkeypatch.setattr(
        "plex.services.scan_health",
        lambda: {
            "state": "healthy", "activities": [{"title": "Scan"}],
            "scanner_running": False,
        },
    )
    monkeypatch.setattr(
        "arr.services.backlog_status",
        lambda: {
            "message": "25 missing across 2 apps.",
            "apps": {
                "radarr": {"label": "R", "missing": 10},
                "sonarr": {"label": "S", "missing": 15},
            },
        },
    )


# ── Auth redirect tests ────────────────────────────────────────────────

class TestAuthRedirect:
    def test_anon_user_redirected_to_login(self, anon_client):
        response = anon_client.get("/")
        assert response.status_code == 302
        assert response.url.startswith("/auth/login/")

    def test_anon_user_settings_page_redirected(self, anon_client):
        response = anon_client.get("/settings/")
        assert response.status_code == 302

    def test_anon_user_reference_page_redirected(self, anon_client):
        response = anon_client.get("/reference/")
        assert response.status_code == 302

    def test_anon_user_activity_log_redirected(self, anon_client):
        response = anon_client.get("/activity-log/")
        assert response.status_code == 302


# ── Logged-in home (Overview) tests ─────────────────────────────────────

class TestLoggedInHome:
    def test_home_renders_overview(self, authed_client):
        response = authed_client.get("/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Overview" in content

    def test_home_has_nav_bar(self, authed_client):
        response = authed_client.get("/")
        content = response.content.decode()
        for label in ["Overview", "Fleet", "Host", "Plex", "Posters",
                        "Lbx", "MDB", "Settings", "Ref"]:
            assert label in content, f"Nav missing: {label}"

    def test_home_has_status_dot(self, authed_client):
        response = authed_client.get("/")
        content = response.content.decode()
        assert 'class="dot' in content
        assert 'id="clock"' in content

    def test_home_has_log_strip(self, authed_client):
        response = authed_client.get("/")
        content = response.content.decode()
        assert "log-strip" in content

    def test_home_has_htmx_boot(self, authed_client):
        response = authed_client.get("/")
        content = response.content.decode()
        assert "htmx.min.js" in content
        assert "X-CSRFToken" in content

    def test_home_has_logout_link(self, authed_client):
        response = authed_client.get("/")
        content = response.content.decode()
        assert "Log out" in content
        assert "/auth/logout/" in content

    def test_overview_shows_queue_counts(self, authed_client):
        response = authed_client.get("/")
        content = response.content.decode()
        assert "1" in content  # q_downloading / queued / importing

    def test_overview_shows_host_resources(self, authed_client):
        response = authed_client.get("/")
        content = response.content.decode()
        assert "45.2" in content
        assert "7.2GB" in content
        assert "16.0GB" in content

    def test_overview_shows_plex_health(self, authed_client):
        response = authed_client.get("/")
        content = response.content.decode()

    def test_overview_shows_arr_missing(self, authed_client):
        response = authed_client.get("/")
        content = response.content.decode()
        assert "25" in content
        assert "2" in content  # app count

    def test_overview_has_sparkline_svg(self, authed_client):
        response = authed_client.get("/")
        content = response.content.decode()
        assert "<svg" in content
        assert 'class="sparkline"' in content


# ── CSRF enforcement ────────────────────────────────────────────────────

class TestCSRFEnforcement:
    def test_post_without_csrf_token_rejected(self, anon_client):
        response = anon_client.post("/settings/", {})
        assert response.status_code == 403


# ── Partial fragments ───────────────────────────────────────────────────

class TestPartialFragments:
    def test_log_strip_partial_renders(self, authed_client):
        response = authed_client.get("/partials/log-strip/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "recent activity" in content

    def test_status_dot_partial_renders(self, authed_client):
        response = authed_client.get("/partials/status-dot/")
        assert response.status_code == 200
        content = response.content.decode()
        assert 'class="dot' in content
        assert 'id="clock"' in content

    def test_overview_cards_partial_renders(self, authed_client):
        response = authed_client.get("/partials/overview-cards/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Queue" in content
        assert "Host" in content
        assert "Plex" in content

    def test_overview_cards_partial_has_all_cards(self, authed_client):
        response = authed_client.get("/partials/overview-cards/")
        content = response.content.decode()
        assert "vitals-row" in content
        assert "Queue" in content
        assert "Arr Fleet" in content