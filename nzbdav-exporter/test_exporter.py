import importlib.util
from pathlib import Path


_spec = importlib.util.spec_from_file_location(
    "nzbdav_exporter", Path(__file__).with_name("exporter.py")
)
_exporter = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_exporter)


def setup_function():
    with _exporter._lock:
        _exporter._metrics.clear()
        _exporter._metric_help.clear()


def test_labeled_samples_are_kept_and_rendered_as_valid_families():
    _exporter._set(
        "queue_items", "2", "Items by category", labels={"category": "tv\\special\"s"}
    )
    _exporter._set(
        "queue_items", "1", labels={"category": "movies"}
    )

    output = _exporter.render_metrics().decode()

    assert '# HELP queue_items Items by category' in output
    assert '# TYPE queue_items gauge' in output
    assert 'queue_items{category="movies"} 1' in output
    assert 'queue_items{category="tv\\\\special\\\"s"} 2' in output


def test_remove_family_drops_old_label_values_without_dropping_help():
    _exporter._set("queue_status", "1", "Queue status", labels={"status": "Downloading"})
    _exporter._set("queue_status", "2", labels={"status": "Queued"})
    _exporter._remove_family("queue_status")
    _exporter._set("queue_status", "1", labels={"status": "Complete"})

    output = _exporter.render_metrics().decode()

    assert 'queue_status{status="Complete"} 1' in output
    assert 'status="Downloading"' not in output
    assert 'status="Queued"' not in output
    assert '# HELP queue_status Queue status' in output


def test_numeric_helpers_fall_back_to_prometheus_safe_values():
    assert _exporter._as_float("not-a-number") == 0.0
    assert _exporter._as_number("not-a-number") == "0"
    assert _exporter._as_number("2.5") == "2.5"
    assert _exporter._as_number("3.0") == "3"
