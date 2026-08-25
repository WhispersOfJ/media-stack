import importlib.util
import json
from pathlib import Path


_spec = importlib.util.spec_from_file_location(
    "nzbdav_exporter", Path(__file__).with_name("exporter.py")
)
_exporter = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_exporter)


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self._payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode()


class FakeNzbDav:
    def __init__(self, queue=None, history=None, config=None, health_status=200):
        self.queue = queue if queue is not None else {"queue": {"slots": []}}
        self.history = history if history is not None else {"history": {"slots": []}}
        self.config = config if config is not None else {"configItems": []}
        self.config_response = None
        self.health_status = health_status
        self.calls = []
        self.fail_modes = set()

    def get(self, url, params=None, headers=None, method="GET", data=None, timeout=10):
        del headers, timeout
        query = dict(params or {})
        self.calls.append({"url": url, "query": query, "method": method, "data": data})
        if query.get("mode") == "queue":
            endpoint = "queue"
        elif query.get("mode") == "history":
            endpoint = "history"
        elif url.endswith("/api/get-config"):
            endpoint = "config"
        else:
            raise AssertionError(f"unexpected exporter request: {url} {query}")
        if endpoint in self.fail_modes:
            raise OSError(f"simulated {endpoint} failure")
        if endpoint == "config" and self.config_response is not None:
            return self.config_response
        return {
            "queue": self.queue,
            "history": self.history,
            "config": self.config,
        }[endpoint]

    def urlopen(self, request, timeout=5):
        del timeout
        self.calls.append({"url": request.full_url, "method": request.method})
        if "healthz" not in request.full_url:
            raise AssertionError(f"unexpected health request: {request.full_url}")
        return FakeResponse(status=self.health_status)


def setup_function():
    with _exporter._lock:
        _exporter._metrics.clear()
        _exporter._metric_help.clear()
        _exporter._last_config.clear()


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


def test_scrape_populates_queue_history_config_health_and_valid_exposition(monkeypatch):
    upstream = FakeNzbDav(
        queue={
            "queue": {
                "slots": [
                    {"status": "Downloading", "cat": "movies", "mbleft": "1.5"},
                    {"status": "Queued", "cat": "movies", "mbleft": 2},
                    {"status": "Queued", "cat": "tv", "mbleft": "bad"},
                ]
            }
        },
        history={
            "history": {
                "slots": [
                    {"status": "Completed"},
                    {"status": "Completed"},
                    {"status": "Failed"},
                    {"status": "Aborted"},
                ]
            }
        },
        config={
            "configItems": [
                {"configName": "usenet.segment-cache.enabled", "configValue": "true"},
                {"configName": "usenet.segment-cache.max-gb", "configValue": "12.5"},
                {"configName": "queue.worker-count", "configValue": "4"},
                {"configName": "usenet.queue-pipelining.depth", "configValue": "bad"},
                {"configName": "repair.enable", "configValue": "false"},
                {"configName": "play.watchdog-enabled", "configValue": "true"},
                {"configName": "preflight.mode", "configValue": "strict"},
                {
                    "configKey": "usenet.max-download-connections-per-stream",
                    "configValue": "true",
                },
            ]
        },
    )
    monkeypatch.setattr(_exporter, "NZBDAV_URL", "http://fake-nzbdav:3000")
    monkeypatch.setattr(_exporter, "NZBDAV_API_KEY", "secret")
    monkeypatch.setattr(_exporter, "_get", upstream.get)
    monkeypatch.setattr(_exporter.urllib.request, "urlopen", upstream.urlopen)

    _exporter._scrape()
    output = _exporter.render_metrics().decode()

    assert "nzbdav_up 1" in output
    assert "nzbdav_queue_active_downloads 1" in output
    assert "nzbdav_queue_items_total 3" in output
    assert "nzbdav_queue_depth_bytes 3670016" in output
    assert 'nzbdav_queue_per_category_bytes{cat="movies"} 3670016' in output
    assert 'nzbdav_queue_per_category_bytes{cat="tv"} 0' in output
    assert 'nzbdav_queue_per_status_count{status="Queued"} 2' in output
    assert "nzbdav_history_completed_total 2" in output
    assert "nzbdav_history_failed_total 1" in output
    assert "nzbdav_history_success_ratio 0.6667" in output
    assert "nzbdav_config_segment_cache_enabled 1" in output
    assert "nzbdav_config_segment_cache_max_gb 12.5" in output
    assert "nzbdav_config_queue_worker_count 4" in output
    assert "nzbdav_config_pipelining_depth 0" in output
    assert "nzbdav_config_repair_enabled 0" in output
    assert "nzbdav_config_watchdog_enabled 1" in output
    assert 'nzbdav_config_preflight_mode_info{mode="strict"} 1' in output
    assert "nzbdav_config_max_connections_per_stream 1" in output
    assert "nzbdav_config_scrape_success 1" in output
    assert "nzbdav_health_healthy 1" in output

    queue_call = next(call for call in upstream.calls if call.get("query", {}).get("mode") == "queue")
    assert queue_call["query"]["apikey"] == "secret"
    config_call = next(call for call in upstream.calls if call.get("url", "").endswith("/api/get-config"))
    assert config_call["method"] == "POST"
    requested_keys = [value for key, value in config_call["data"] if key == "config-keys"]
    assert "usenet.segment-cache.enabled" in requested_keys
    assert len(requested_keys) == 8


def test_scrape_failure_keeps_exporter_up_but_marks_queue_down_and_clears_failed_data(monkeypatch):
    upstream = FakeNzbDav(
        queue={"queue": {"slots": [{"status": "Downloading", "cat": "movies", "mbleft": 1}]}},
        history={"history": {"slots": [{"status": "Failed"}]}},
        config={"configItems": []},
    )
    monkeypatch.setattr(_exporter, "_get", upstream.get)
    monkeypatch.setattr(_exporter.urllib.request, "urlopen", upstream.urlopen)

    _exporter._scrape()
    assert 'nzbdav_queue_per_category_bytes{cat="movies"} 1048576' in _exporter.render_metrics().decode()

    upstream.fail_modes.update({"queue", "history", "config"})
    _exporter._scrape()
    output = _exporter.render_metrics().decode()

    assert "nzbdav_up 0" in output
    assert "nzbdav_queue_items_total 0" in output
    assert "nzbdav_queue_depth_bytes 0" in output
    assert 'cat="movies"' not in output
    assert "nzbdav_history_completed_total 0" in output
    assert "nzbdav_history_failed_total 0" in output
    assert "nzbdav_history_success_ratio 0.0000" in output
    assert "nzbdav_config_segment_cache_enabled 0" in output
    assert 'nzbdav_config_preflight_mode_info{mode="unknown"} 1' in output
    assert "nzbdav_config_scrape_success 0" in output
    assert "nzbdav_health_healthy 1" in output


def test_config_status_failure_retains_last_known_values_and_marks_scrape_failed(monkeypatch):
    upstream = FakeNzbDav(
        config={
            "status": True,
            "configItems": [
                {"configName": "queue.worker-count", "configValue": "6"},
                {"configName": "preflight.mode", "configValue": "standard"},
            ],
        }
    )
    monkeypatch.setattr(_exporter, "_get", upstream.get)
    monkeypatch.setattr(_exporter.urllib.request, "urlopen", upstream.urlopen)

    _exporter._scrape()
    upstream.config_response = {"status": False, "error": "temporarily unavailable", "configItems": []}
    _exporter._scrape()
    output = _exporter.render_metrics().decode()

    assert "nzbdav_config_queue_worker_count 6" in output
    assert 'nzbdav_config_preflight_mode_info{mode="standard"} 1' in output
    assert "nzbdav_config_scrape_success 0" in output
    assert "nzbdav_up 0" in output


def test_malformed_queue_payload_marks_scrape_failed_without_crashing(monkeypatch):
    upstream = FakeNzbDav(queue={"queue": {"slots": "not-an-array"}})
    monkeypatch.setattr(_exporter, "_get", upstream.get)
    monkeypatch.setattr(_exporter.urllib.request, "urlopen", upstream.urlopen)

    _exporter._scrape()
    output = _exporter.render_metrics().decode()

    assert "nzbdav_up 0" in output
    assert "nzbdav_queue_items_total 0" in output
    assert "nzbdav_config_scrape_success 1" in output


def test_failed_health_request_marks_health_unhealthy_without_aborting_scrape(monkeypatch):
    upstream = FakeNzbDav(
        queue={"queue": {"slots": []}},
        history={"history": {"slots": []}},
        config={"configItems": []},
    )
    upstream.health_status = 503
    monkeypatch.setattr(_exporter, "_get", upstream.get)
    monkeypatch.setattr(_exporter.urllib.request, "urlopen", upstream.urlopen)

    _exporter._scrape()
    output = _exporter.render_metrics().decode()

    assert "nzbdav_up 1" in output
    assert "nzbdav_health_healthy 0" in output
    assert "nzbdav_queue_items_total 0" in output
