"""services/letterboxd/router.py - moved out of
test_radarr_sonarr_prowlarr_bazarr_router.py when Letterboxd became its own
package (2026-08-06), spanning Radarr and Sonarr.
"""
from unittest.mock import MagicMock

import httpx
from fastapi.testclient import TestClient


def _login(client, main_module, password="correct-horse-battery-staple"):
    from core.security import hash_password
    from models.user import User

    db = main_module.SessionLocal()
    try:
        db.add(User(username="admin", password_hash=hash_password(password)))
        db.commit()
    finally:
        db.close()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert resp.status_code == 200


def _service_key_header(main_module):
    from core.security import hash_api_key
    from models.api_key import ApiKey

    db = main_module.SessionLocal()
    try:
        db.add(ApiKey(name="healthcheck-cron", key_hash=hash_api_key("raw-service-key")))
        db.commit()
    finally:
        db.close()
    return {"X-Api-Key": "raw-service-key"}


def _json_response(payload, status_code=200, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
    return resp


def test_letterboxd_add_short_circuits_when_already_in_radarr(cp_main_app, monkeypatch):
    letterboxd_html = '<html>themoviedb.org/movie/603</html>'

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        if "letterboxd.com" in url:
            return MagicMock(text=letterboxd_html, raise_for_status=MagicMock())
        if "/movie" in url and params and params.get("tmdbId") == 603:
            return _json_response([{"id": 99, "title": "The Matrix", "year": 1999}])
        return _json_response({})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd", json={"url": "https://letterboxd.com/film/the-matrix/"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["alreadyAdded"] is True
    assert body["radarrId"] == 99


def test_letterboxd_add_rejects_non_letterboxd_url(cp_main_app):
    client = TestClient(cp_main_app.app)
    _login(client, cp_main_app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd", json={"url": "https://example.com/not-letterboxd"})
    assert resp.status_code == 400


def test_letterboxd_add_accepts_service_key(cp_main_app, monkeypatch):
    """stack-letterboxd-radarr.fish calls this unattended via the service
    key (2026-08-06's extend-service-key-auth commit) - was session-only
    before that."""
    letterboxd_html = '<html>themoviedb.org/movie/603</html>'

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        if "letterboxd.com" in url:
            return MagicMock(text=letterboxd_html, raise_for_status=MagicMock())
        if "/movie" in url and params and params.get("tmdbId") == 603:
            return _json_response([{"id": 99, "title": "The Matrix", "year": 1999}])
        return _json_response({})

    monkeypatch.setattr(httpx, "get", fake_get)
    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd", json={"url": "https://letterboxd.com/film/x/"}, headers=headers)
    assert resp.status_code == 200


def test_letterboxd_add_requires_some_auth(cp_main_app):
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/arr/radarr/add-from-letterboxd", json={"url": "https://letterboxd.com/film/x/"})
    assert resp.status_code == 401
