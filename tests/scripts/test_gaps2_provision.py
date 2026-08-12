"""Coverage for scripts/gaps2-provision.py's Radarr/Sonarr wiring.

GAPS-2's save_config is a wholesale overwrite of the stored dict, not a merge
(app/services/radarr_service.py: save_config builds `cleaned` from scratch).
Provisioning needs two saves - credentials first, because /root-folders and
/profiles read the stored config, then the resolved values - so the second
save has to re-send the credentials or it wipes them. That is the regression
these tests exist for; the rest cover the fallbacks that decide where a title
added from GAPS-2's own UI actually lands.
"""
import pytest


def _fake_request(recorder, *, folders=None, profiles=None, test_status=200, existing=None):
    """Stand in for the module's `request()` against GAPS-2's HTTP API."""
    folders = [{"path": "/data/movies"}] if folders is None else folders
    profiles = [{"id": 7, "name": "Unlimited"}] if profiles is None else profiles

    def request(method, path, body=None):
        recorder.append((method, path, body))
        if method == "GET" and path.endswith("/config"):
            return 200, (existing or {"enabled": False})
        if method == "POST" and path.endswith("/test"):
            return test_status, ({"message": "Connected to Radarr 5.0"} if test_status == 200
                                 else {"error": "Invalid API key"})
        if method == "GET" and path.endswith("/root-folders"):
            return 200, folders
        if method == "GET" and path.endswith("/profiles"):
            return 200, profiles
        if method == "POST" and path.endswith("/config"):
            # Mirror GAPS-2: enabled is derived from url + api_key being set.
            return 200, {**body, "enabled": bool(body.get("url") and body.get("api_key"))}
        raise AssertionError(f"unexpected call: {method} {path}")

    return request


def _radarr(gaps2_provision):
    return next(t for t in gaps2_provision.ARR_TARGETS if t["service"] == "radarr")


ENV = {"RADARR_API_KEY": "radarr-key", "SONARR_API_KEY": "sonarr-key"}


def _saves(calls):
    return [body for method, path, body in calls if method == "POST" and path.endswith("/config")]


# --- the targets themselves -------------------------------------------

def test_targets_match_the_routing_table(gaps2_provision):
    """One GAPS-2 connection per Arr instance the routing table names. A
    library routed somewhere GAPS-2 was never wired to would leave its own UI
    adding titles to the wrong instance, or to none."""
    from services.gaps2.libraries import LIBRARIES

    assert {t["service"] for t in gaps2_provision.ARR_TARGETS} == {lib["arr"] for lib in LIBRARIES}


def test_targets_use_docker_network_urls(gaps2_provision):
    """GAPS-2 is the client here, so localhost would resolve to the gaps2
    container itself rather than to Radarr/Sonarr."""
    for target in gaps2_provision.ARR_TARGETS:
        assert "localhost" not in target["url"] and "127.0.0.1" not in target["url"]


def test_decade_routing_stays_off(gaps2_provision):
    """auto_route_by_decade picks a root folder whose path contains the
    title's decade. This stack has one flat root folder per instance, so
    leaving it on makes every add's destination depend on a path match that
    never succeeds."""
    assert _radarr(gaps2_provision)["extra"]["auto_route_by_decade"] is False


# --- provisioning ------------------------------------------------------

def test_credentials_survive_the_second_save(gaps2_provision, monkeypatch):
    calls = []
    monkeypatch.setattr(gaps2_provision, "request", _fake_request(calls))
    gaps2_provision.provision_arr(_radarr(gaps2_provision), ENV, dry_run=False)

    final = _saves(calls)[-1]
    assert final["url"] == "http://radarr:7878"
    assert final["api_key"] == "radarr-key"
    assert final["root_folder_path"] == "/data/movies"
    assert final["quality_profile_id"] == 7


def test_named_root_folder_and_profile_are_preferred(gaps2_provision, monkeypatch):
    calls = []
    monkeypatch.setattr(gaps2_provision, "request", _fake_request(
        calls,
        folders=[{"path": "/data/other"}, {"path": "/data/movies"}],
        profiles=[{"id": 1, "name": "HD-1080p"}, {"id": 7, "name": "Unlimited"}],
    ))
    gaps2_provision.provision_arr(_radarr(gaps2_provision), ENV, dry_run=False)

    final = _saves(calls)[-1]
    assert final["root_folder_path"] == "/data/movies"
    assert final["quality_profile_id"] == 7


def test_falls_back_to_the_first_entry_when_the_named_one_is_absent(gaps2_provision, monkeypatch):
    """A blank root folder or profile id 0 makes GAPS-2's add fail with
    'Quality profile and root folder must be configured first', so a rename
    on the Radarr side must degrade to a working value, not to nothing."""
    calls = []
    monkeypatch.setattr(gaps2_provision, "request", _fake_request(
        calls,
        folders=[{"path": "/data/films"}],
        profiles=[{"id": 3, "name": "Any"}],
    ))
    gaps2_provision.provision_arr(_radarr(gaps2_provision), ENV, dry_run=False)

    final = _saves(calls)[-1]
    assert final["root_folder_path"] == "/data/films"
    assert final["quality_profile_id"] == 3


def test_no_root_folders_is_fatal(gaps2_provision, monkeypatch):
    calls = []
    monkeypatch.setattr(gaps2_provision, "request", _fake_request(calls, folders=[]))
    with pytest.raises(SystemExit, match="root folders"):
        gaps2_provision.provision_arr(_radarr(gaps2_provision), ENV, dry_run=False)


def test_no_quality_profiles_is_fatal(gaps2_provision, monkeypatch):
    calls = []
    monkeypatch.setattr(gaps2_provision, "request", _fake_request(calls, profiles=[]))
    with pytest.raises(SystemExit, match="quality profiles"):
        gaps2_provision.provision_arr(_radarr(gaps2_provision), ENV, dry_run=False)


def test_a_rejected_key_fails_before_anything_is_written(gaps2_provision, monkeypatch):
    """Otherwise a bad key only surfaces at the first Add from GAPS-2's UI,
    which reports it as the title failing rather than the connection."""
    calls = []
    monkeypatch.setattr(gaps2_provision, "request", _fake_request(calls, test_status=400))
    with pytest.raises(SystemExit, match="connection failed"):
        gaps2_provision.provision_arr(_radarr(gaps2_provision), ENV, dry_run=False)
    assert _saves(calls) == []


def test_missing_api_key_is_fatal(gaps2_provision, monkeypatch):
    calls = []
    monkeypatch.setattr(gaps2_provision, "request", _fake_request(calls))
    with pytest.raises(SystemExit, match="RADARR_API_KEY"):
        gaps2_provision.provision_arr(_radarr(gaps2_provision), {}, dry_run=False)
    assert _saves(calls) == []


def test_dry_run_writes_nothing(gaps2_provision, monkeypatch):
    calls = []
    monkeypatch.setattr(gaps2_provision, "request", _fake_request(calls))
    gaps2_provision.provision_arr(_radarr(gaps2_provision), ENV, dry_run=True)
    assert [method for method, _, _ in calls] == ["GET"]


def test_rerun_over_an_existing_config_still_writes(gaps2_provision, monkeypatch, capsys):
    """Safe to re-run is the script's whole contract - an already-enabled
    connection is reported and overwritten, not skipped."""
    calls = []
    monkeypatch.setattr(gaps2_provision, "request", _fake_request(
        calls, existing={"enabled": True, "url": "http://radarr:7878"}))
    gaps2_provision.provision_arr(_radarr(gaps2_provision), ENV, dry_run=False)

    assert "overwriting" in capsys.readouterr().out
    assert _saves(calls)[-1]["quality_profile_id"] == 7
