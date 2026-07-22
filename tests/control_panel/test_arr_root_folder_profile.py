from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

RADARR_CFG = {"url": "http://radarr:7878", "api": "v3", "key": "radarr-key"}
SONARR_CFG = {"url": "http://sonarr:8989", "api": "v3", "key": "sonarr-key"}


def _mock_httpx_get(monkeypatch, cp_app, folders, profiles):
    folders_resp = MagicMock()
    folders_resp.json.return_value = folders
    profiles_resp = MagicMock()
    profiles_resp.json.return_value = profiles
    mock_get = MagicMock(side_effect=[folders_resp, profiles_resp])
    monkeypatch.setattr(cp_app.httpx, "get", mock_get)
    return mock_get


def test_radarr_prefers_default_root_and_profile_when_present(cp_app, monkeypatch):
    _mock_httpx_get(
        monkeypatch, cp_app,
        folders=[{"path": "/data/other"}, {"path": "/data/movies"}],
        profiles=[{"id": 6, "name": "HD"}, {"id": 5, "name": "Unlimited"}],
    )
    path, profile_id = cp_app._radarr_root_folder_and_profile(RADARR_CFG, None, None)
    assert path == "/data/movies"
    assert profile_id == 5


def test_radarr_honors_explicit_overrides(cp_app, monkeypatch):
    _mock_httpx_get(
        monkeypatch, cp_app,
        folders=[{"path": "/data/movies"}, {"path": "/custom"}],
        profiles=[{"id": 5, "name": "Unlimited"}, {"id": 6, "name": "HD"}],
    )
    path, profile_id = cp_app._radarr_root_folder_and_profile(RADARR_CFG, "/custom", "HD")
    assert path == "/custom"
    assert profile_id == 6


def test_radarr_falls_back_to_first_entry_when_default_missing(cp_app, monkeypatch):
    _mock_httpx_get(
        monkeypatch, cp_app,
        folders=[{"path": "/data/only-option"}],
        profiles=[{"id": 9, "name": "Other"}],
    )
    path, profile_id = cp_app._radarr_root_folder_and_profile(RADARR_CFG, None, None)
    assert path == "/data/only-option"
    assert profile_id == 9


def test_radarr_no_root_folders_fails_500(cp_app, monkeypatch):
    _mock_httpx_get(monkeypatch, cp_app, folders=[], profiles=[{"id": 1, "name": "x"}])
    with pytest.raises(HTTPException) as exc:
        cp_app._radarr_root_folder_and_profile(RADARR_CFG, None, None)
    assert exc.value.status_code == 500


def test_radarr_no_quality_profiles_fails_500(cp_app, monkeypatch):
    _mock_httpx_get(monkeypatch, cp_app, folders=[{"path": "/data/movies"}], profiles=[])
    with pytest.raises(HTTPException) as exc:
        cp_app._radarr_root_folder_and_profile(RADARR_CFG, None, None)
    assert exc.value.status_code == 500


def test_sonarr_prefers_default_root_and_profile_when_present(cp_app, monkeypatch):
    _mock_httpx_get(
        monkeypatch, cp_app,
        folders=[{"path": "/data/other"}, {"path": "/data/shows"}],
        profiles=[{"id": 2, "name": "HD"}, {"id": 1, "name": "Any"}],
    )
    path, profile_id = cp_app._sonarr_root_folder_and_profile(SONARR_CFG, None, None)
    assert path == "/data/shows"
    assert profile_id == 1


def test_sonarr_honors_explicit_overrides(cp_app, monkeypatch):
    _mock_httpx_get(
        monkeypatch, cp_app,
        folders=[{"path": "/data/shows"}, {"path": "/custom-shows"}],
        profiles=[{"id": 1, "name": "Any"}, {"id": 2, "name": "HD"}],
    )
    path, profile_id = cp_app._sonarr_root_folder_and_profile(SONARR_CFG, "/custom-shows", "HD")
    assert path == "/custom-shows"
    assert profile_id == 2
