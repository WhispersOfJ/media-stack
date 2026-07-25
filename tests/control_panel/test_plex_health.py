import sqlite3
import time
from unittest.mock import MagicMock

from fastapi.testclient import TestClient


def test_bounded_exec_returns_result_when_fast(cp_app):
    container = MagicMock()
    container.exec_run.return_value = "fast result"
    assert cp_app._bounded_exec(container, ["ls"], timeout=2) == "fast result"


def test_bounded_exec_returns_none_on_timeout(cp_app):
    container = MagicMock()

    def slow(cmd):
        time.sleep(2)
        return "too slow"

    container.exec_run.side_effect = slow
    assert cp_app._bounded_exec(container, ["ps", "aux"], timeout=0.2) is None


def test_plex_container_pid_returns_pid(cp_app):
    container = MagicMock()
    container.attrs = {"State": {"Pid": 12345}}
    cp_app.docker_client.containers.get.return_value = container
    assert cp_app._plex_container_pid() == 12345


def test_plex_container_pid_missing_container(cp_app):
    import docker

    cp_app.docker_client.containers.get.side_effect = docker.errors.NotFound("nope")
    assert cp_app._plex_container_pid() is None


def test_plex_scanner_processes_filters_scanner_lines(cp_app, monkeypatch):
    container = MagicMock()
    result = MagicMock()
    result.output = b"root 1 ps\nplex 2 Plex Media Scanner --scan\n"
    monkeypatch.setattr(cp_app, "_bounded_exec", lambda c, cmd, timeout=5: result)
    cp_app.docker_client.containers.get.return_value = container
    lines = cp_app._plex_scanner_processes()
    assert len(lines) == 1
    assert "Plex Media Scanner" in lines[0]


def test_plex_scanner_processes_empty_on_bounded_exec_timeout(cp_app, monkeypatch):
    container = MagicMock()
    monkeypatch.setattr(cp_app, "_bounded_exec", lambda c, cmd, timeout=5: None)
    cp_app.docker_client.containers.get.return_value = container
    assert cp_app._plex_scanner_processes() == []


def test_plex_dstate_threads_finds_d_state(cp_app, monkeypatch, tmp_path):
    proc_dir = tmp_path / "host-proc"
    task_dir = proc_dir / "999" / "task" / "999"
    task_dir.mkdir(parents=True)
    (task_dir / "status").write_text("Name:\tPlex Media Scanner\nState:\tD (disk sleep)\n")
    monkeypatch.setattr(cp_app, "HOST_PROC_DIR", str(proc_dir))

    found = cp_app._plex_dstate_threads(999)
    assert len(found) == 1
    assert found[0]["comm"] == "Plex Media Scanner"


def test_plex_dstate_threads_empty_without_pid(cp_app):
    assert cp_app._plex_dstate_threads(None) == []


def test_plex_dstate_threads_empty_when_host_proc_missing(cp_app, monkeypatch, tmp_path):
    monkeypatch.setattr(cp_app, "HOST_PROC_DIR", str(tmp_path / "does-not-exist"))
    assert cp_app._plex_dstate_threads(123) == []


def test_plex_dstate_threads_ignores_running_state(cp_app, monkeypatch, tmp_path):
    proc_dir = tmp_path / "host-proc"
    task_dir = proc_dir / "999" / "task" / "999"
    task_dir.mkdir(parents=True)
    (task_dir / "status").write_text("Name:\tPlex\nState:\tR (running)\n")
    monkeypatch.setattr(cp_app, "HOST_PROC_DIR", str(proc_dir))
    assert cp_app._plex_dstate_threads(999) == []


def test_fuse_waiting_total_sums_connections(cp_app, monkeypatch, tmp_path):
    fuse_dir = tmp_path / "host-sys-fuse"
    for conn_id, waiting in [("80", "0"), ("93", "3")]:
        conn_dir = fuse_dir / "connections" / conn_id
        conn_dir.mkdir(parents=True)
        (conn_dir / "waiting").write_text(waiting)
    monkeypatch.setattr(cp_app, "HOST_SYS_FUSE_DIR", str(fuse_dir))
    assert cp_app._fuse_waiting_total() == 3


def test_fuse_waiting_total_zero_when_not_mounted(cp_app, monkeypatch, tmp_path):
    monkeypatch.setattr(cp_app, "HOST_SYS_FUSE_DIR", str(tmp_path / "does-not-exist"))
    assert cp_app._fuse_waiting_total() == 0


def test_bearmount_queue_counts_reads_real_sqlite(cp_app, monkeypatch, tmp_path):
    config_dir = tmp_path / "host-config"
    bearmount_dir = config_dir / "bearmount"
    bearmount_dir.mkdir(parents=True)
    db_path = bearmount_dir / "bearmount.db"
    con = sqlite3.connect(str(db_path))
    con.execute("CREATE TABLE import_queue (status TEXT)")
    con.executemany(
        "INSERT INTO import_queue (status) VALUES (?)",
        [("pending",), ("pending",), ("processing",), ("completed",)],
    )
    con.commit()
    con.close()
    monkeypatch.setattr(cp_app, "HOST_CONFIG_DIR", str(config_dir))

    counts = cp_app._bearmount_queue_counts()
    assert counts["pending"] == 2
    assert counts["processing"] == 1


def test_bearmount_queue_counts_db_missing(cp_app, monkeypatch, tmp_path):
    monkeypatch.setattr(cp_app, "HOST_CONFIG_DIR", str(tmp_path / "does-not-exist"))
    counts = cp_app._bearmount_queue_counts()
    assert counts["pending"] == 0
    assert counts["processing"] == 0
    assert counts["db_missing"] is True


def test_mount_test_true_on_real_content(cp_app, monkeypatch):
    container = MagicMock()
    result = MagicMock()
    result.exit_code = 0
    monkeypatch.setattr(cp_app, "_bounded_exec", lambda c, cmd, timeout=5: result)
    cp_app.docker_client.containers.get.return_value = container
    assert cp_app._mount_test("plex") is True


def test_mount_test_false_on_bounded_exec_timeout(cp_app, monkeypatch):
    container = MagicMock()
    monkeypatch.setattr(cp_app, "_bounded_exec", lambda c, cmd, timeout=5: None)
    cp_app.docker_client.containers.get.return_value = container
    assert cp_app._mount_test("plex") is False


def test_mount_test_false_on_nonzero_exit(cp_app, monkeypatch):
    container = MagicMock()
    result = MagicMock()
    result.exit_code = 2
    monkeypatch.setattr(cp_app, "_bounded_exec", lambda c, cmd, timeout=5: result)
    cp_app.docker_client.containers.get.return_value = container
    assert cp_app._mount_test("plex") is False


def _patch_scan_health_deps(cp_app, monkeypatch, *, dstate=None, mount_ok=True,
                             scanner_lines=None, queue=None, activities=None):
    monkeypatch.setattr(cp_app, "_plex_container_pid", lambda: 1)
    monkeypatch.setattr(cp_app, "_plex_dstate_threads", lambda pid: dstate or [])
    monkeypatch.setattr(cp_app, "_fuse_waiting_total", lambda: 0)
    monkeypatch.setattr(cp_app, "_mount_test", lambda name="plex": mount_ok)
    monkeypatch.setattr(cp_app, "_plex_scanner_processes", lambda: scanner_lines or [])
    monkeypatch.setattr(cp_app, "_bearmount_queue_counts",
                         lambda: queue or {"pending": 0, "processing": 0})
    monkeypatch.setattr(cp_app, "_plex_log_tail",
                         lambda lines=50: {"lines": [], "busy_db_errors": 0,
                                           "recent_busy_db_timestamps": []})
    monkeypatch.setattr(cp_app, "_plex_activities", lambda: activities or [])
    container = MagicMock()
    container.attrs = {"State": {"Health": {"Status": "healthy"}}, "RestartCount": 0}
    cp_app.docker_client.containers.get.return_value = container


def test_scan_health_healthy(cp_app, monkeypatch):
    _patch_scan_health_deps(cp_app, monkeypatch)
    client = TestClient(cp_app.app, base_url="http://localhost")
    r = client.get("/api/plex/scan-health")
    assert r.status_code == 200
    assert r.json()["state"] == "healthy"


def test_scan_health_hung_confirmed_on_dstate(cp_app, monkeypatch):
    _patch_scan_health_deps(cp_app, monkeypatch, dstate=[{"tid": "1", "comm": "x", "state": "D"}])
    client = TestClient(cp_app.app, base_url="http://localhost")
    r = client.get("/api/plex/scan-health")
    assert r.json()["state"] == "hung_confirmed"


def test_scan_health_hung_confirmed_on_broken_mount(cp_app, monkeypatch):
    _patch_scan_health_deps(cp_app, monkeypatch, mount_ok=False)
    client = TestClient(cp_app.app, base_url="http://localhost")
    r = client.get("/api/plex/scan-health")
    assert r.json()["state"] == "hung_confirmed"


def test_scan_health_scanning_with_active_queue_and_scanner(cp_app, monkeypatch):
    _patch_scan_health_deps(
        cp_app, monkeypatch,
        queue={"pending": 5, "processing": 1},
        scanner_lines=["plex 1 Plex Media Scanner"],
        activities=[{"title": "Scanning Movies", "progress": 10}],
    )
    client = TestClient(cp_app.app, base_url="http://localhost")
    r = client.get("/api/plex/scan-health")
    assert r.json()["state"] == "scanning"


def test_scan_health_stalled_suspected_queue_active_no_scanner(cp_app, monkeypatch):
    _patch_scan_health_deps(
        cp_app, monkeypatch,
        queue={"pending": 5, "processing": 1},
        scanner_lines=[],
        activities=[{"title": "Scanning Movies", "progress": 10}],
    )
    client = TestClient(cp_app.app, base_url="http://localhost")
    r = client.get("/api/plex/scan-health")
    assert r.json()["state"] == "stalled_suspected"


def test_restart_cascade_blocked_when_queue_not_empty(cp_app, monkeypatch):
    monkeypatch.setattr(cp_app, "_bearmount_queue_counts",
                         lambda: {"pending": 3, "processing": 0})
    client = TestClient(cp_app.app, base_url="http://localhost")
    r = client.post("/api/plex/restart-cascade")
    assert r.status_code == 409


def test_restart_cascade_force_bypasses_queue_gate(cp_app, monkeypatch):
    monkeypatch.setattr(cp_app, "_bearmount_queue_counts",
                         lambda: {"pending": 3, "processing": 0})
    monkeypatch.setattr(cp_app, "_restart_bearmount_cascade", lambda: ["radarr", "sonarr"])
    client = TestClient(cp_app.app, base_url="http://localhost")
    r = client.post("/api/plex/restart-cascade?force=true")
    assert r.status_code == 200
    assert r.json()["restarted"] == ["radarr", "sonarr"]


def test_unstick_503_when_fuse_not_mounted(cp_app, monkeypatch, tmp_path):
    monkeypatch.setattr(cp_app, "HOST_SYS_FUSE_DIR", str(tmp_path / "does-not-exist"))
    client = TestClient(cp_app.app, base_url="http://localhost")
    r = client.post("/api/plex/unstick")
    assert r.status_code == 503


def test_unstick_blocked_when_queue_not_empty(cp_app, monkeypatch, tmp_path):
    fuse_dir = tmp_path / "host-sys-fuse"
    (fuse_dir / "connections").mkdir(parents=True)
    monkeypatch.setattr(cp_app, "HOST_SYS_FUSE_DIR", str(fuse_dir))
    monkeypatch.setattr(cp_app, "_bearmount_queue_counts",
                         lambda: {"pending": 1, "processing": 0})
    client = TestClient(cp_app.app, base_url="http://localhost")
    r = client.post("/api/plex/unstick")
    assert r.status_code == 409


def test_unstick_no_waiting_connections_is_a_noop(cp_app, monkeypatch, tmp_path):
    fuse_dir = tmp_path / "host-sys-fuse"
    conn_dir = fuse_dir / "connections" / "80"
    conn_dir.mkdir(parents=True)
    (conn_dir / "waiting").write_text("0")
    monkeypatch.setattr(cp_app, "HOST_SYS_FUSE_DIR", str(fuse_dir))
    monkeypatch.setattr(cp_app, "_bearmount_queue_counts",
                         lambda: {"pending": 0, "processing": 0})
    client = TestClient(cp_app.app, base_url="http://localhost")
    r = client.post("/api/plex/unstick")
    assert r.status_code == 200
    assert r.json()["aborted"] == []


def test_unstick_aborts_waiting_connection_and_cascades(cp_app, monkeypatch, tmp_path):
    fuse_dir = tmp_path / "host-sys-fuse"
    conn_dir = fuse_dir / "connections" / "93"
    conn_dir.mkdir(parents=True)
    (conn_dir / "waiting").write_text("3")
    monkeypatch.setattr(cp_app, "HOST_SYS_FUSE_DIR", str(fuse_dir))
    monkeypatch.setattr(cp_app, "_bearmount_queue_counts",
                         lambda: {"pending": 0, "processing": 0})
    monkeypatch.setattr(cp_app, "_restart_bearmount_cascade", lambda: ["plex"])
    monkeypatch.setattr(cp_app.time, "sleep", lambda s: None)

    client = TestClient(cp_app.app, base_url="http://localhost")
    r = client.post("/api/plex/unstick")
    assert r.status_code == 200
    body = r.json()
    assert body["aborted"] == ["93"]
    assert body["restarted"] == ["plex"]
    assert (conn_dir / "abort").read_text() == "1"


def test_restart_bearmount_cascade_fails_when_mount_still_empty(cp_app, monkeypatch):
    monkeypatch.setattr(cp_app.subprocess, "run",
                         lambda *a, **k: MagicMock(returncode=0))
    bearmount = MagicMock()
    cp_app.docker_client.containers.get.return_value = bearmount
    monkeypatch.setattr(cp_app, "wait_for_healthy", lambda c, timeout=60: None)
    monkeypatch.setattr(cp_app, "_bounded_exec", lambda c, cmd, timeout=5: MagicMock(exit_code=0, output=b""))
    monkeypatch.setattr(cp_app.time, "sleep", lambda s: None)

    from fastapi import HTTPException
    import pytest as _pytest
    with _pytest.raises(HTTPException) as exc:
        cp_app._restart_bearmount_cascade()
    assert exc.value.status_code == 502
    assert "empty" in exc.value.detail["message"]


def test_restart_bearmount_cascade_succeeds_with_real_content(cp_app, monkeypatch):
    monkeypatch.setattr(cp_app.subprocess, "run",
                         lambda *a, **k: MagicMock(returncode=0))
    bearmount = MagicMock()
    dependent = MagicMock()
    cp_app.docker_client.containers.get.side_effect = lambda name: bearmount if name == "bearmount" else dependent
    monkeypatch.setattr(cp_app, "wait_for_healthy", lambda c, timeout=60: None)
    monkeypatch.setattr(cp_app, "_bounded_exec",
                         lambda c, cmd, timeout=5: MagicMock(exit_code=0, output=b"movie1\nmovie2\n"))

    restarted = cp_app._restart_bearmount_cascade()
    assert set(restarted) == cp_app.MOUNT_DEPENDENTS
