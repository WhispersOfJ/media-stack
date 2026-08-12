"""Phase 4 (PLANS.md) validation for services/scrutiny/router.py: auth
gating, summary shaping, healthy-vs-failing classification, the friendly
disk-id resolver, the single-disk default, collector exec, and the ntfy
alert-test path."""
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

UUID = "500c6e6d-9dcd-584c-81e9-32a13f8f55c1"


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


def _summary(device_status=0, name="nvme0"):
    return {"data": {"summary": {UUID: {
        "device": {
            "device_name": name, "model_name": "Bestoss GM988H 1TB",
            "serial_number": "UB988KH7Q261KN00098", "device_protocol": "NVMe",
            "capacity": 1024209543168, "device_status": device_status,
        },
        "smart": {"temp": 43, "power_on_hours": 2083, "collector_date": "2026-08-12T12:47:52Z"},
    }}}}


def _details(attrs=None):
    return {"data": {
        "device": {
            "device_name": "nvme0", "model_name": "Bestoss GM988H 1TB",
            "serial_number": "UB988KH7Q261KN00098", "firmware": "SN13683",
        },
        "smart_results": [{
            "date": "2026-08-12T12:47:52Z", "temp": 43,
            "power_on_hours": 2083, "power_cycle_count": 41,
            "attrs": attrs if attrs is not None else {
                "percentage_used": {"value": 3, "status": 0},
                "available_spare": {"value": 100, "status": 0},
                "media_errors": {"value": 0, "status": 0},
                "critical_warning": {"value": 0, "status": 0},
                "host_reads": {"value": 1029315588, "status": 0},
            },
        }],
    }}


def _mock_get(monkeypatch, summary_body, details_body=None):
    def fake_get(url, **k):
        if url.endswith("/api/summary"):
            return _resp(summary_body)
        return _resp(details_body if details_body is not None else _details())

    monkeypatch.setattr("services.scrutiny.router.httpx.get", fake_get)


# --- auth -------------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("GET", "/api/scrutiny/summary"),
    ("GET", "/api/scrutiny/disk"),
    ("POST", "/api/scrutiny/collect"),
    ("POST", "/api/scrutiny/alert-test"),
])
def test_routes_require_auth(cp_main_app, method, path):
    client = TestClient(cp_main_app.app)
    assert client.request(method, path).status_code == 401


# --- summary ----------------------------------------------------------

def test_summary_reports_healthy_disk(cp_main_app, monkeypatch):
    _mock_get(monkeypatch, _summary())
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/scrutiny/summary", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    body = resp.json()
    assert body["failing"] == []
    assert len(body["disks"]) == 1
    disk = body["disks"][0]
    assert disk["healthy"] is True
    assert disk["name"] == "nvme0"
    assert disk["temp_c"] == 43
    assert disk["power_on_hours"] == 2083


def test_summary_flags_failing_disk(cp_main_app, monkeypatch):
    """Scrutiny's device_status is 0 for passing; any non-zero means at
    least one of its three failure checks tripped."""
    _mock_get(monkeypatch, _summary(device_status=1))
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/scrutiny/summary", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    body = resp.json()
    assert body["failing"] == ["nvme0"]
    assert body["disks"][0]["healthy"] is False
    assert "FAILING" in body["message"]


def test_summary_distinguishes_no_disks_from_broken(cp_main_app, monkeypatch):
    """Empty is the normal state between container start and first collector
    run, so it must not read as a missing disk."""
    _mock_get(monkeypatch, {"data": {"summary": {}}})
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/scrutiny/summary", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    assert resp.json()["disks"] == []
    assert "collector" in resp.json()["message"]


def test_summary_fails_when_unreachable(cp_main_app, monkeypatch):
    def fake_get(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr("services.scrutiny.router.httpx.get", fake_get)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/scrutiny/summary", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 502


# --- disk detail ------------------------------------------------------

@pytest.mark.parametrize("identifier", [UUID, "nvme0", "UB988KH7Q261KN00098", "NVME0"])
def test_disk_resolves_uuid_name_and_serial(cp_main_app, monkeypatch, identifier):
    """Scrutiny's own API only accepts its internal UUID, which nobody has
    memorised; the router resolves a friendly identifier first."""
    _mock_get(monkeypatch, _summary())
    client = TestClient(cp_main_app.app)
    resp = client.get(f"/api/scrutiny/disk?disk_id={identifier}", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    assert resp.json()["uuid"] == UUID


def test_disk_defaults_to_sole_disk(cp_main_app, monkeypatch):
    _mock_get(monkeypatch, _summary())
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/scrutiny/disk", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    assert resp.json()["uuid"] == UUID


def test_disk_requires_id_when_multiple_registered(cp_main_app, monkeypatch):
    body = _summary()
    body["data"]["summary"]["second-uuid"] = {
        "device": {"device_name": "sda", "device_status": 0}, "smart": {},
    }
    _mock_get(monkeypatch, body)
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/scrutiny/disk", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 400
    assert "nvme0" in resp.json()["detail"]["message"]


def test_disk_404s_on_unknown_identifier(cp_main_app, monkeypatch):
    _mock_get(monkeypatch, _summary())
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/scrutiny/disk?disk_id=sdz", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 404
    assert "nvme0" in resp.json()["detail"]["message"]


def test_disk_surfaces_wear_attrs_and_ignores_raw_counters(cp_main_app, monkeypatch):
    _mock_get(monkeypatch, _summary())
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/scrutiny/disk", headers=_service_key_header(cp_main_app))
    wear = resp.json()["wear"]
    assert wear["percentage_used"]["value"] == 3
    assert wear["available_spare"]["value"] == 100
    # host_reads is a raw counter, only meaningful as a trend line in the UI.
    assert "host_reads" not in wear


def test_disk_reports_flagged_attributes(cp_main_app, monkeypatch):
    _mock_get(monkeypatch, _summary(), _details(attrs={
        "percentage_used": {"value": 96, "status": 2},
        "media_errors": {"value": 14, "status": 1},
        "available_spare": {"value": 100, "status": 0},
    }))
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/scrutiny/disk", headers=_service_key_header(cp_main_app))
    body = resp.json()
    assert body["flagged"] == ["media_errors", "percentage_used"]
    assert "flagged" in body["message"]


def test_disk_handles_registered_but_no_results(cp_main_app, monkeypatch):
    _mock_get(monkeypatch, _summary(), {"data": {"device": {"device_name": "nvme0"}, "smart_results": []}})
    client = TestClient(cp_main_app.app)
    resp = client.get("/api/scrutiny/disk", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    assert resp.json()["attrs"] == {}


# --- collector --------------------------------------------------------

def test_collect_reports_published_device_count(cp_main_app, monkeypatch):
    container = MagicMock()
    container.exec_run.return_value = MagicMock(
        exit_code=0,
        output=b"Collecting smartctl results for nvme0\nPublishing smartctl results for 500c6e6d\nMain: Completed\n",
    )
    monkeypatch.setattr("services.scrutiny.router.docker_client.containers.get", lambda _: container)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/scrutiny/collect", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    assert resp.json()["devices_published"] == 1


def test_collect_fails_on_nonzero_exit(cp_main_app, monkeypatch):
    container = MagicMock()
    container.exec_run.return_value = MagicMock(exit_code=1, output=b"smartctl: permission denied")
    monkeypatch.setattr("services.scrutiny.router.docker_client.containers.get", lambda _: container)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/scrutiny/collect", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 502
    assert "permission denied" in resp.json()["detail"]["message"]


# --- alert test -------------------------------------------------------

def test_alert_test_posts_to_scrutiny(cp_main_app, monkeypatch):
    captured = {}

    def fake_post(url, **k):
        captured["url"] = url
        return _resp({"success": True})

    monkeypatch.setattr("services.scrutiny.router.httpx.post", fake_post)
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/scrutiny/alert-test", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 200
    assert captured["url"] == "http://scrutiny:8080/api/health/notify"


def test_no_success_route_returns_a_top_level_detail_key(cp_main_app, monkeypatch):
    """Regression test for a bug caught live, not by the original tests.

    __stack_api (fish-functions/__stack_api.fish) unwraps any top-level
    `detail` dict as FastAPI's HTTPException envelope. A *success* payload
    that happens to carry `detail` is therefore mistaken for an error body,
    and every stack-scrutiny-* command prints raw JSON instead of its
    message. The router looked correct in isolation and was only wrong
    through the CLI, which is why this asserts the response shape rather
    than any single route's behaviour.
    """
    _mock_get(monkeypatch, _summary())
    monkeypatch.setattr("services.scrutiny.router.httpx.post", lambda *a, **k: _resp({"success": True}))
    container = MagicMock()
    container.exec_run.return_value = MagicMock(exit_code=0, output=b"Publishing smartctl results for x\n")
    monkeypatch.setattr("services.scrutiny.router.docker_client.containers.get", lambda _: container)

    client = TestClient(cp_main_app.app)
    headers = _service_key_header(cp_main_app)
    for method, path in [
        ("GET", "/api/scrutiny/summary"),
        ("GET", "/api/scrutiny/disk"),
        ("POST", "/api/scrutiny/collect"),
        ("POST", "/api/scrutiny/alert-test"),
    ]:
        body = client.request(method, path, headers=headers).json()
        assert "detail" not in body, f"{path} returns a top-level 'detail' key; __stack_api will misread it"


def test_alert_test_surfaces_failure(cp_main_app, monkeypatch):
    """Scrutiny answers 200 with success:false when a notify URL is broken,
    so a bare raise_for_status would report a working alert path that isn't."""
    monkeypatch.setattr(
        "services.scrutiny.router.httpx.post",
        lambda *a, **k: _resp({"success": False, "errors": ["ntfy unreachable"]}),
    )
    client = TestClient(cp_main_app.app)
    resp = client.post("/api/scrutiny/alert-test", headers=_service_key_header(cp_main_app))
    assert resp.status_code == 502
