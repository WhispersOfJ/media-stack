"""Phase 7 (PLANS.md) validation for services/plexanisync/router.py.

PlexAniSync is the only service in the batch with no API and no persistent
process - a container that runs once and exits - so every route here reads
container state and logs. Four behaviours carry the weight, all of them places
where the obvious reading of the container is wrong:

- **Exited(0) is healthy**, not down. It is the normal state between the four
  daily timer runs, so /last-run reports success from it.
- **Exit 0 does not prove the sync worked** - the matched count is reported
  alongside it, and a count upstream's log wording didn't yield must read as
  unknown (None), never as 0, which is a real and alarming answer.
- **An expired AniList token is the expected failure** (1-year OAuth, no
  non-interactive renewal) and gets named explicitly instead of surfacing as a
  generic non-zero exit.
- **A second concurrent run is refused, not queued** - two runs would push
  conflicting updates to the same AniList list.
"""
import sys
from unittest.mock import MagicMock

import docker
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


def _fake_container(state: dict, logs: bytes = b""):
    fake = MagicMock()
    fake.attrs = {"State": state}
    fake.logs.return_value = logs
    return fake


def _install(cp_main_app, container):
    dc = sys.modules["core.docker_client"]
    dc.docker_client.containers.get.side_effect = None
    dc.docker_client.containers.get.return_value = container
    return _service_key_header(cp_main_app)


SUCCESS_STATE = {
    "Running": False,
    "ExitCode": 0,
    "StartedAt": "2026-08-13T12:45:00.123456789Z",
    "FinishedAt": "2026-08-13T12:52:00.123456789Z",
}


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/plexanisync/last-run"),
    ("POST", "/api/plexanisync/run-now"),
    ("GET", "/api/plexanisync/logs"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    assert client.request(method, path).status_code == 401


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/plexanisync/last-run"),
    ("POST", "/api/plexanisync/run-now"),
    ("GET", "/api/plexanisync/logs"),
])
def test_502s_when_container_missing(cp_main_app, method, path):
    dc = sys.modules["core.docker_client"]
    dc.docker_client.containers.get.side_effect = docker.errors.NotFound("nope")
    headers = _service_key_header(cp_main_app)
    client = TestClient(cp_main_app.app)
    resp = client.request(method, path, headers=headers)
    assert resp.status_code == 502
    # fail() raises HTTPException, so the envelope arrives under "detail".
    assert "does not exist yet" in resp.json()["detail"]["message"]


# Verbatim from the 2026-08-13 live run (docker logs plexanisync), trimmed -
# not invented wording. These exact strings are what the parser is pinned to.
REAL_LOG = b"""2026-08-13 12:06:27 [ANILIST] Found 0 anime series on list
2026-08-13 12:06:56 [PLEX] Retrieving anime series from section: Anime Shows
2026-08-13 12:06:58 [PLEX] Found 826 anime series in section: Anime Shows
2026-08-13 12:06:58 [PLEX] Retrieving anime series from section: Anime Movies
2026-08-13 12:06:59 [PLEX] Found 756 anime series in section: Anime Movies
2026-08-13 12:07:07 [PLEX] Found 3 watched series
2026-08-13 12:07:08 [ANILIST] Found AniList entry for Plex title: Cowboy Bebop
2026-08-13 12:07:17 [ANILIST] Found AniList entry for Plex title: Dragon Ball Z
2026-08-13 12:07:18 [ANILIST] Found AniList entry for Plex title: The Animatrix
2026-08-13 12:07:19 Plex to AniList sync finished
"""


def test_exited_zero_reads_as_success_not_down(cp_main_app):
    """The container sits in Exited(0) between runs - that is the healthy state."""
    headers = _install(cp_main_app, _fake_container(SUCCESS_STATE, REAL_LOG))
    body = TestClient(cp_main_app.app).get("/api/plexanisync/last-run", headers=headers).json()
    assert body["ok"] is True
    assert body["running"] is False
    assert body["exit_code"] == 0
    assert body["completed"] is True
    assert "succeeded" in body["message"]
    assert body["counts"] == {"watched": 3, "matched": 3, "unmatched": 0}
    assert body["token_expired"] is False


def test_unmatched_titles_are_counted(cp_main_app):
    headers = _install(cp_main_app, _fake_container(
        SUCCESS_STATE,
        REAL_LOG + b"2026-08-13 12:07:19 [ANILIST] No match found for title: Some Obscure OVA\n"))
    body = TestClient(cp_main_app.app).get("/api/plexanisync/last-run", headers=headers).json()
    assert body["counts"]["unmatched"] == 1


def test_watched_total_is_unknown_not_zero_when_unparsed(cp_main_app):
    """A stated total that didn't parse must be None. Reporting 0 watched
    series would be a real, and wrong, alarm - tallies can safely be 0 because
    they count lines that are either present or absent."""
    headers = _install(cp_main_app, _fake_container(
        SUCCESS_STATE, b"done\nPlex to AniList sync finished\n"))
    body = TestClient(cp_main_app.app).get("/api/plexanisync/last-run", headers=headers).json()
    assert body["counts"]["watched"] is None
    assert body["counts"]["matched"] == 0
    assert "unknown" in body["message"]


def test_exit_zero_without_finish_line_is_not_success(cp_main_app):
    """A container killed partway exits 0 with no 'sync finished' line. Exit
    code alone would call that a healthy run."""
    headers = _install(cp_main_app, _fake_container(
        SUCCESS_STATE, b"2026-08-13 12:06:58 [PLEX] Found 826 anime series in section: Anime Shows\n"))
    body = TestClient(cp_main_app.app).get("/api/plexanisync/last-run", headers=headers).json()
    assert body["completed"] is False
    assert "stopped partway" in body["message"]


def test_expired_anilist_token_is_named(cp_main_app):
    headers = _install(cp_main_app, _fake_container(
        {**SUCCESS_STATE, "ExitCode": 1},
        b"ERROR: AniList returned 401 Unauthorized: Invalid token\n"))
    body = TestClient(cp_main_app.app).get("/api/plexanisync/last-run", headers=headers).json()
    assert body["token_expired"] is True
    assert "AniList token" in body["message"]


def test_failed_run_without_token_signature_is_generic(cp_main_app):
    headers = _install(cp_main_app, _fake_container(
        {**SUCCESS_STATE, "ExitCode": 1}, b"Traceback: connection refused to Plex\n"))
    body = TestClient(cp_main_app.app).get("/api/plexanisync/last-run", headers=headers).json()
    assert body["token_expired"] is False
    assert "FAILED" in body["message"]
    assert body["exit_code"] == 1


def test_never_run_container_says_so(cp_main_app):
    headers = _install(cp_main_app, _fake_container({
        "Running": False, "ExitCode": 0,
        "StartedAt": "0001-01-01T00:00:00Z", "FinishedAt": "0001-01-01T00:00:00Z",
    }))
    body = TestClient(cp_main_app.app).get("/api/plexanisync/last-run", headers=headers).json()
    assert body["started_at"] is None
    assert "Never run" in body["message"]


def test_run_now_starts_the_container(cp_main_app):
    container = _fake_container(SUCCESS_STATE)
    headers = _install(cp_main_app, container)
    resp = TestClient(cp_main_app.app).post("/api/plexanisync/run-now", json={}, headers=headers)
    assert resp.status_code == 200
    container.start.assert_called_once()


def test_run_now_refuses_a_concurrent_run(cp_main_app):
    """Refused, not queued: two runs would push conflicting updates to the
    same AniList list, and Docker cannot start a running container anyway."""
    container = _fake_container({**SUCCESS_STATE, "Running": True})
    headers = _install(cp_main_app, container)
    resp = TestClient(cp_main_app.app).post("/api/plexanisync/run-now", json={}, headers=headers)
    assert resp.status_code == 409
    container.start.assert_not_called()


def test_run_now_reports_a_docker_failure(cp_main_app):
    container = _fake_container(SUCCESS_STATE)
    container.start.side_effect = docker.errors.APIError("no such image")
    headers = _install(cp_main_app, container)
    resp = TestClient(cp_main_app.app).post("/api/plexanisync/run-now", json={}, headers=headers)
    assert resp.status_code == 502


def test_logs_tails_and_rejects_bad_line_counts(cp_main_app):
    container = _fake_container(SUCCESS_STATE, b"line one\nline two\n")
    headers = _install(cp_main_app, container)
    client = TestClient(cp_main_app.app)
    assert client.get("/api/plexanisync/logs?lines=0", headers=headers).status_code == 400
    body = client.get("/api/plexanisync/logs?lines=50", headers=headers).json()
    assert body["log"] == "line one\nline two\n"
    container.logs.assert_called_with(tail=50)
