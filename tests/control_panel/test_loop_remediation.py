
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def _resp(json_body, status_code=200):
    r = httpx.Response(status_code=status_code, json=json_body, request=httpx.Request("GET", "http://x"))
    return r


def test_loop_candidates_rejects_unknown_app(cp_app):
    with pytest.raises(HTTPException) as exc:
        cp_app.arr_loop_candidates("not-a-real-app")
    assert exc.value.status_code == 404


def test_loop_candidates_flags_dedup_suffix(cp_app, monkeypatch):
    now = cp_app.datetime.now(cp_app.timezone.utc).isoformat().replace("+00:00", "Z")

    def fake_get(url, params=None, headers=None, timeout=None):
        if url.endswith("/history"):
            return _resp({"records": [
                {"movieId": 200, "sourceTitle": "Movie.2020.x264-GRP", "date": now, "eventType": "downloadFailed"},
                {"movieId": 200, "sourceTitle": "Movie.2020.x264-GRP2", "date": now, "eventType": "downloadFailed"},
            ]})
        if url.endswith("/movie/200"):
            return _resp({"id": 200, "monitored": True, "hasFile": False, "title": "Movie", "tmdbId": 1, "year": 2020})
        if url.endswith("/queue"):
            return _resp({"records": [{"movieId": 200, "outputPath": "/data/Movie (2).mkv"}]})
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(cp_app.httpx, "get", fake_get)
    client = TestClient(cp_app.app)
    r = client.get("/api/arr/radarr/loop-candidates")
    assert r.status_code == 200
    candidates = r.json()["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["suggested_action"] == "suffix-bug"


def test_loop_candidates_flags_scene_mismatch(cp_app, monkeypatch):
    now = cp_app.datetime.now(cp_app.timezone.utc).isoformat().replace("+00:00", "Z")

    def fake_get(url, params=None, headers=None, timeout=None):
        if url.endswith("/history"):
            return _resp({"records": [
                {"episodeId": 100, "sourceTitle": "Show.S01E03.x264-GRP", "date": now, "eventType": "downloadFailed"},
                {"episodeId": 100, "sourceTitle": "Show.S01E03.x264-GRP2", "date": now, "eventType": "downloadFailed"},
            ]})
        if url.endswith("/episode/100"):
            return _resp({
                "id": 100, "monitored": True, "hasFile": False, "title": "Ep",
                "episodeNumber": 2, "seasonNumber": 1, "sceneEpisodeNumber": 3, "sceneSeasonNumber": 1,
                "seriesId": 5, "series": {"title": "Show"},
            })
        if url.endswith("/queue"):
            return _resp({"records": []})
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(cp_app.httpx, "get", fake_get)
    client = TestClient(cp_app.app)
    r = client.get("/api/arr/sonarr/loop-candidates")
    assert r.status_code == 200
    candidates = r.json()["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["suggested_action"] == "unmonitor"
    assert "scene" in candidates[0]["reason"]


def test_unmonitor_radarr_uses_movie_editor(cp_app, monkeypatch):
    calls = []

    def fake_put(url, json=None, headers=None, timeout=None):
        calls.append((url, json))
        return _resp({}, status_code=202)

    monkeypatch.setattr(cp_app.httpx, "put", fake_put)
    cp_app.ALLOWED_HOSTS.add("testserver")
    client = TestClient(cp_app.app)
    r = client.post("/api/arr/radarr/unmonitor", json={"ids": [1, 2]})
    assert r.status_code == 200
    assert calls[0][0].endswith("/movie/editor")
    assert calls[0][1] == {"movieIds": [1, 2], "monitored": False}
