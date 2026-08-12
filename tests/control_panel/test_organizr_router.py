"""Phase 3 (PLANS.md) validation for services/organizr/router.py: auth
gating, the 20-char API-key constraint, tab listing/shaping, additive sync
semantics, and the framing decision encoded in services/organizr/tabs.py."""
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient


def _service_key_header(main_module):
    from core.security import hash_api_key
    from models.api_key import ApiKey

    db = main_module.SessionLocal()
    try:
        db.add(ApiKey(name="test-key", key_hash=hash_api_key("raw-service-key")))
        db.commit()
    finally:
        db.close()
    return {"X-Api-Key": "raw-service-key"}


def _resp(json_body, status_code=200):
    r = MagicMock()
    r.status_code = status_code
    r.content = b"{}"
    r.json.return_value = json_body
    r.raise_for_status = MagicMock()
    return r


def _tabs_body(tabs):
    return {"response": {"result": "success", "data": {"tabs": tabs, "categories": [], "groups": []}}}


VALID_KEY = "abcdefghij0123456789"  # exactly 20 chars, as Organizr requires


# --- the table itself -------------------------------------------------

def test_nzbdav_is_the_only_new_window_tab():
    """Regression test for the 2026-08-12 framing sweep, so its result is
    encoded rather than folklore. Every live service was checked for
    X-Frame-Options and CSP frame-ancestors; nzbdav was the only one that
    refuses framing (X-Frame-Options: SAMEORIGIN on both its 302 and its
    final 200). If a future service also blocks framing, this test should
    be updated deliberately, not deleted."""
    from services.organizr.tabs import TABS, TYPE_IFRAME, TYPE_NEW_WINDOW

    new_window = [t["name"] for t in TABS if t["tab_type"] == TYPE_NEW_WINDOW]
    assert new_window == ["NzbDAV"]
    assert all(t["tab_type"] == TYPE_IFRAME for t in TABS if t["name"] != "NzbDAV")


def test_tab_urls_use_host_ip_not_container_names():
    """Tab URLs are fetched by the browser, not by Organizr's PHP, so a
    stacknet service name would resolve nowhere."""
    from services.organizr.tabs import TABS, tab_payload

    for tab in TABS:
        payload = tab_payload(tab, "192.168.4.105")
        assert payload["url"].startswith("http://192.168.4.105:")
        assert payload["url_local"] == payload["url"]
        assert payload["image"]
        assert payload["enabled"] == 1


def test_tab_names_are_unique():
    """Organizr rejects a duplicate tab name with a 409, so a dupe in the
    table would make sync permanently report a phantom skip."""
    from services.organizr.tabs import TABS

    names = [t["name"] for t in TABS]
    assert len(names) == len(set(names))


# --- auth -------------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("GET", "/api/organizr/health"),
    ("GET", "/api/organizr/tabs"),
    ("POST", "/api/organizr/tabs/sync"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    assert client.request(method, path).status_code == 401


def test_tabs_fails_when_key_unset(cp_main_app, monkeypatch):
    monkeypatch.delenv("ORGANIZR_API_KEY", raising=False)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/organizr/tabs", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 500


def test_tabs_fails_on_wrong_length_key(cp_main_app, monkeypatch):
    """Organizr compares strlen($token) == 20 before it compares the value
    (api/classes/organizr.class.php:4609), so a wrong-length key 401s every
    route with no useful error. The router rejects it up front instead."""
    monkeypatch.setenv("ORGANIZR_API_KEY", "too-short")
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/organizr/tabs", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 500
    assert "exactly 20" in resp.json()["detail"]["message"]


# --- listing ----------------------------------------------------------

def test_tabs_shapes_response_and_reports_missing(cp_main_app, monkeypatch):
    monkeypatch.setenv("ORGANIZR_API_KEY", VALID_KEY)
    monkeypatch.setattr(
        "services.organizr.router.httpx.get",
        lambda *a, **k: _resp(_tabs_body([
            {"name": "Settings", "url": "api/v2/page/settings", "type": 0, "enabled": 1, "group_id": 1},
            {"name": "Radarr", "url": "http://192.168.4.105:7878/", "type": 1, "enabled": 1, "group_id": 0},
        ])),
    )
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/organizr/tabs", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["items"][1] == {
        "name": "Radarr", "url": "http://192.168.4.105:7878/",
        "type": 1, "enabled": True, "group_id": 0,
    }
    # Everything in the canonical table except Radarr is still missing.
    assert "Plex" in body["missing"]
    assert "Radarr" not in body["missing"]


def test_tabs_fails_when_unreachable(cp_main_app, monkeypatch):
    monkeypatch.setenv("ORGANIZR_API_KEY", VALID_KEY)

    def fake_get(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr("services.organizr.router.httpx.get", fake_get)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/organizr/tabs", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 502


# --- sync -------------------------------------------------------------

def test_sync_adds_only_missing_tabs(cp_main_app, monkeypatch):
    from services.organizr.tabs import TABS

    monkeypatch.setenv("ORGANIZR_API_KEY", VALID_KEY)
    monkeypatch.setenv("HOST_IP", "192.168.4.105")
    monkeypatch.setattr(
        "services.organizr.router.httpx.get",
        lambda *a, **k: _resp(_tabs_body([{"name": "Radarr", "url": "x", "type": 1, "enabled": 1, "group_id": 0}])),
    )
    posted = []

    def fake_post(url, headers=None, json=None, **k):
        posted.append(json)
        return _resp({"response": {"result": "success", "message": "Tab added"}})

    monkeypatch.setattr("services.organizr.router.httpx.post", fake_post)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/organizr/tabs/sync", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    body = resp.json()
    assert body["skipped"] == ["Radarr"]
    assert len(body["added"]) == len(TABS) - 1
    assert "Radarr" not in [p["name"] for p in posted]


def test_sync_treats_409_as_skip_not_failure(cp_main_app, monkeypatch):
    """A 409 means the name is already taken by a tab we didn't create.
    Sync is additive, so that is a skip, not an error."""
    monkeypatch.setenv("ORGANIZR_API_KEY", VALID_KEY)
    monkeypatch.setenv("HOST_IP", "192.168.4.105")
    monkeypatch.setattr("services.organizr.router.httpx.get", lambda *a, **k: _resp(_tabs_body([])))
    monkeypatch.setattr(
        "services.organizr.router.httpx.post",
        lambda *a, **k: _resp({"response": {"message": "Tab name is already taken"}}, status_code=409),
    )
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/organizr/tabs/sync", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    assert resp.json()["added"] == []


def test_sync_fails_when_host_ip_unset(cp_main_app, monkeypatch):
    monkeypatch.setenv("ORGANIZR_API_KEY", VALID_KEY)
    monkeypatch.setenv("HOST_IP", "")
    monkeypatch.setattr("services.organizr.router.httpx.get", lambda *a, **k: _resp(_tabs_body([])))
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/organizr/tabs/sync", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 500


# --- health -----------------------------------------------------------

def test_health_reports_pong(cp_main_app, monkeypatch):
    monkeypatch.setattr(
        "services.organizr.router.httpx.get",
        lambda *a, **k: _resp({"response": {"result": "success", "data": "pong"}}),
    )
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/organizr/health", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    assert resp.json()["pong"] == "pong"


def test_health_needs_no_api_key(cp_main_app, monkeypatch):
    """Organizr's /api/v2/ping is in its unauthenticated set, so this probe
    must keep working even before provisioning has minted anything."""
    monkeypatch.delenv("ORGANIZR_API_KEY", raising=False)
    monkeypatch.setattr(
        "services.organizr.router.httpx.get",
        lambda *a, **k: _resp({"response": {"data": "pong"}}),
    )
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/organizr/health", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
