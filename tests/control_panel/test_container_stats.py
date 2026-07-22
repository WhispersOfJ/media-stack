from unittest.mock import MagicMock


def _fake_container(status="running", stats=None, stats_raises=False):
    c = MagicMock()
    c.status = status
    if stats_raises:
        c.stats.side_effect = RuntimeError("daemon unreachable")
    else:
        c.stats.return_value = stats or {}
    return c


def test_container_stats_not_running_returns_all_none(cp_app):
    c = _fake_container(status="exited")
    result = cp_app.container_stats(c)
    assert result == {"cpu_percent": None, "mem_used_mb": None, "mem_limit_mb": None, "mem_percent": None}
    c.stats.assert_not_called()


def test_container_stats_daemon_error_degrades_gracefully(cp_app):
    c = _fake_container(status="running", stats_raises=True)
    result = cp_app.container_stats(c)
    assert result == {"cpu_percent": None, "mem_used_mb": None, "mem_limit_mb": None, "mem_percent": None}


def test_container_stats_computes_cpu_and_memory(cp_app):
    stats = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 2_000_000_000},
            "system_cpu_usage": 10_000_000_000,
            "online_cpus": 2,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 1_000_000_000},
            "system_cpu_usage": 9_000_000_000,
        },
        "memory_stats": {
            "usage": 200 * 1024 * 1024,
            "limit": 1024 * 1024 * 1024,
            "stats": {"inactive_file": 50 * 1024 * 1024},
        },
    }
    c = _fake_container(status="running", stats=stats)
    result = cp_app.container_stats(c)
    # cpu_delta=1e9, system_delta=1e9 -> (1e9/1e9)*2*100 = 200.0
    assert result["cpu_percent"] == 200.0
    assert result["mem_used_mb"] == 150.0
    assert result["mem_limit_mb"] == 1024.0
    assert result["mem_percent"] == round((150 * 1024 * 1024 / (1024 * 1024 * 1024)) * 100, 1)


def test_container_stats_zero_system_delta_is_no_cpu_reading(cp_app):
    stats = {
        "cpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 500, "online_cpus": 1},
        "precpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 500},
        "memory_stats": {"usage": 0, "limit": 0, "stats": {}},
    }
    c = _fake_container(status="running", stats=stats)
    result = cp_app.container_stats(c)
    assert result["cpu_percent"] is None
    # usage=0 is still a real (if unhelpful) reading, not a null one
    assert result["mem_used_mb"] == 0.0
    # limit=0 is falsy, so mem_limit_mb (and the ratio derived from it)
    # both fall back to None rather than dividing by zero.
    assert result["mem_limit_mb"] is None
    assert result["mem_percent"] is None
