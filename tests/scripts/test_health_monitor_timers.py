"""Phase 7 (PLANS.md 7.3): the run-freshness check added to
.claude/skills/health-monitor/monitor.py.

This is the one new check *type* the 7-service batch introduced. Everything
else the monitor does asks "is this port answering", which says nothing about
a service that is a container running four times a day and sitting in
Exited(0) in between.

Two independent failure modes have to fail the check, and they are easy to
conflate: the timer stopped firing (stale), and the timer fired but the job
exited non-zero. A check that only looked at one would call a silently-broken
sync healthy - which, with a yearly-expiring AniList token behind it, is the
exact way this service is expected to break.
"""
import importlib.util
import time
from pathlib import Path

import pytest

MONITOR_PATH = Path(__file__).resolve().parents[2] / ".claude/skills/health-monitor/monitor.py"


@pytest.fixture
def monitor():
    spec = importlib.util.spec_from_file_location("health_monitor", MONITOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_show(monitor, monkeypatch, responses: dict):
    """Stub `systemctl --user show` per unit name."""
    monkeypatch.setattr(monitor, "_systemctl_show", lambda unit, props: responses.get(unit, {}))


def _fired(minutes_ago: int) -> str:
    """systemd's LastTriggerUSec format: 'Thu 2026-08-13 12:45:00 EDT'."""
    return time.strftime("%a %Y-%m-%d %H:%M:%S %Z", time.localtime(time.time() - minutes_ago * 60))


def test_fresh_run_passes(monitor, monkeypatch):
    _fake_show(monitor, monkeypatch, {
        "plexanisync.timer": {"LoadState": "loaded", "ActiveState": "active",
                              "LastTriggerUSec": _fired(30)},
        "plexanisync.service": {"Result": "success", "ExecMainStatus": "0"},
    })
    ok, detail = monitor.check_timer("plexanisync", "plexanisync.timer", 8 * 3600)
    assert ok is True
    assert "30m ago" in detail


def test_stale_run_fails_even_though_last_result_was_success(monitor, monkeypatch):
    """The timer succeeded - three days ago. Success is not freshness."""
    _fake_show(monitor, monkeypatch, {
        "plexanisync.timer": {"LoadState": "loaded", "ActiveState": "active",
                              "LastTriggerUSec": _fired(3 * 24 * 60)},
        "plexanisync.service": {"Result": "success", "ExecMainStatus": "0"},
    })
    ok, detail = monitor.check_timer("plexanisync", "plexanisync.timer", 8 * 3600)
    assert ok is False
    assert "stale" in detail


def test_recent_run_that_failed_fails(monitor, monkeypatch):
    """Fired 10 minutes ago and exited 1 - the expired-token failure mode."""
    _fake_show(monitor, monkeypatch, {
        "plexanisync.timer": {"LoadState": "loaded", "ActiveState": "active",
                              "LastTriggerUSec": _fired(10)},
        "plexanisync.service": {"Result": "exit-code", "ExecMainStatus": "1"},
    })
    ok, detail = monitor.check_timer("plexanisync", "plexanisync.timer", 8 * 3600)
    assert ok is False
    assert "failed" in detail and "exit=1" in detail


def test_uninstalled_timer_fails(monitor, monkeypatch):
    _fake_show(monitor, monkeypatch, {})
    ok, detail = monitor.check_timer("plexanisync", "plexanisync.timer", 8 * 3600)
    assert ok is False
    assert "not installed" in detail


def test_installed_but_inactive_timer_fails(monitor, monkeypatch):
    """A disabled timer loads fine and reports a plausible last-trigger - the
    check has to look at ActiveState, not just presence."""
    _fake_show(monitor, monkeypatch, {
        "plexanisync.timer": {"LoadState": "loaded", "ActiveState": "inactive",
                              "LastTriggerUSec": _fired(5)},
    })
    ok, detail = monitor.check_timer("plexanisync", "plexanisync.timer", 8 * 3600)
    assert ok is False
    assert "not active" in detail


def test_enabled_but_never_fired_passes(monitor, monkeypatch):
    """Just installed: active, no run yet. Not a failure - there is nothing
    stale about a timer whose first firing hasn't come around."""
    _fake_show(monitor, monkeypatch, {
        "plexanisync.timer": {"LoadState": "loaded", "ActiveState": "active",
                              "LastTriggerUSec": "n/a"},
        "plexanisync.service": {"Result": "", "ExecMainStatus": ""},
    })
    ok, detail = monitor.check_timer("plexanisync", "plexanisync.timer", 8 * 3600)
    assert ok is True
    assert "has not fired yet" in detail


def test_unparseable_trigger_does_not_crash_the_sweep(monitor, monkeypatch):
    _fake_show(monitor, monkeypatch, {
        "plexanisync.timer": {"LoadState": "loaded", "ActiveState": "active",
                              "LastTriggerUSec": "some future systemd format"},
        "plexanisync.service": {"Result": "success", "ExecMainStatus": "0"},
    })
    ok, detail = monitor.check_timer("plexanisync", "plexanisync.timer", 8 * 3600)
    assert ok is True
    assert "unparsed" in detail


def test_systemctl_missing_returns_empty_rather_than_raising(monitor, monkeypatch):
    """No systemd on the box (a container, CI) must degrade to 'not
    installed', never take the whole sweep down."""
    def _boom(*args, **kwargs):
        raise FileNotFoundError("systemctl")
    monkeypatch.setattr(monitor.subprocess, "run", _boom)
    assert monitor._systemctl_show("plexanisync.timer", "LoadState") == {}


def test_plexanisync_is_registered_as_a_scheduled_job(monitor):
    unit, max_age = monitor.SCHEDULED_JOBS["plexanisync"]
    assert unit == "plexanisync.timer"
    # 4x/day = 6h apart; the threshold must allow one missed firing plus a
    # long run, but not a whole quiet day.
    assert 6 * 3600 < max_age <= 12 * 3600
