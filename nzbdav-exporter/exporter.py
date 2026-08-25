#!/usr/bin/env python3
"""NzbDAV Prometheus exporter (stdlib only, zero pip dependencies).

Scrapes NzbDAV's SABnzbd-compatible queue/history API and admin health API,
then exposes Prometheus metrics on :9200/metrics.
"""

import json
import logging
import math
import os
import time
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Lock, Thread

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nzbdav-exporter")

NZBDAV_URL = os.environ.get("NZBDAV_URL", "http://nzbdav:3000").rstrip("/")
NZBDAV_API_KEY = os.environ.get("NZBDAV_API_KEY", "")
try:
    SCRAPE_INTERVAL = max(1, int(os.environ.get("SCRAPE_INTERVAL", "15")))
except ValueError:
    SCRAPE_INTERVAL = 15

# Each key is one complete Prometheus sample line. Keeping labels in the key
# prevents samples from different categories/statuses overwriting one another.
_metrics: dict[str, str] = {}
_metric_help: dict[str, tuple[str, str]] = {}
_last_config: dict[str, object] = {}
_lock = Lock()


def _labels(labels: dict[str, object] | None = None) -> str:
    if not labels:
        return ""
    encoded = []
    for key in sorted(labels):
        value = str(labels[key]).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
        encoded.append(f'{key}="{value}"')
    return "{" + ",".join(encoded) + "}"


def _set(name: str, value: str, help_text: str = "", typ: str = "gauge",
         labels: dict[str, object] | None = None):
    """Register or replace one Prometheus sample."""
    with _lock:
        if help_text and name not in _metric_help:
            _metric_help[name] = (help_text, typ)
        _metrics[f"{name}{_labels(labels)}"] = value


def _remove_family(name: str):
    """Remove stale labeled samples before the next scrape."""
    with _lock:
        prefix = name + "{"
        for key in list(_metrics):
            if key == name or key.startswith(prefix):
                del _metrics[key]


def _as_float(value: object) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _as_number(value: object, default: str = "0") -> str:
    """Return a finite, Prometheus-compatible scalar."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return str(int(number)) if number.is_integer() else str(number)


def _slots(payload: object, section: str) -> list[dict]:
    """Validate an SAB history/queue slots collection before processing it."""
    if not isinstance(payload, dict):
        raise ValueError(f"{section} response is not an object")
    slots = payload.get("slots", [])
    if not isinstance(slots, list):
        raise ValueError(f"{section}.slots is not an array")
    return [slot for slot in slots if isinstance(slot, dict)]


def _get(url: str, params: dict | None = None, headers: dict | None = None,
         method: str = "GET", data: dict | list[tuple[str, object]] | None = None,
         timeout: int = 10):
    """HTTP request using stdlib. Returns parsed JSON dict."""
    if params:
        separator = "&" if "?" in url else "?"
        url = url + separator + urllib.parse.urlencode(params)
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data, doseq=True).encode()
    req = urllib.request.Request(url, method=method, data=body)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _scraper():
    """Background scrape loop."""
    while True:
        t0 = time.monotonic()
        try:
            _scrape()
        except Exception as exc:
            log.error("scrape failed: %s", exc)
            _set("nzbdav_up", "0", help_text="1 if the exporter completed a scrape", typ="gauge")
        elapsed = time.monotonic() - t0
        _set("nzbdav_scrape_duration_seconds", f"{elapsed:.4f}",
             help_text="Time spent scraping NzbDAV APIs", typ="gauge")
        time.sleep(SCRAPE_INTERVAL)


def _scrape():
    global _last_config
    headers = {"X-Api-Key": NZBDAV_API_KEY}
    scrape_success = True

    # --- Queue ---
    t0 = time.monotonic()
    try:
        data = _get(f"{NZBDAV_URL}/api",
                    params={"mode": "queue", "output": "json", "apikey": NZBDAV_API_KEY})
        if not isinstance(data, dict):
            raise ValueError("queue response is not an object")
        slots = _slots(data.get("queue", {}), "queue")
    except Exception as exc:
        log.warning("queue scrape failed: %s", exc)
        scrape_success = False
        slots = []
    _set("nzbdav_api_latency_seconds", f"{time.monotonic() - t0:.4f}",
         help_text="Latency of queue API call", typ="gauge")

    active = sum(1 for s in slots if s.get("status") == "Downloading")
    total = len(slots)
    total_mbleft = sum(_as_float(s.get("mbleft")) for s in slots)

    _set("nzbdav_queue_active_downloads", str(active),
         help_text="Number of actively downloading items", typ="gauge")
    _set("nzbdav_queue_items_total", str(total),
         help_text="Total items in download queue", typ="gauge")
    _set("nzbdav_queue_depth_bytes", str(int(total_mbleft * 1024 * 1024)),
         help_text="Total bytes remaining across all queue items", typ="gauge")

    # Remove old label values so disappeared categories/statuses are not
    # reported forever.
    _remove_family("nzbdav_queue_per_category_bytes")
    cat_bytes: dict[str, float] = {}
    for slot in slots:
        category = slot.get("cat") or "unknown"
        cat_bytes[category] = cat_bytes.get(category, 0) + _as_float(slot.get("mbleft"))
    for category, megabytes in cat_bytes.items():
        _set("nzbdav_queue_per_category_bytes", str(int(megabytes * 1024 * 1024)),
             help_text="Bytes remaining per category", typ="gauge",
             labels={"cat": category})

    _remove_family("nzbdav_queue_per_status_count")
    status_counts: dict[str, int] = {}
    for slot in slots:
        status = slot.get("status") or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    for status, count in status_counts.items():
        _set("nzbdav_queue_per_status_count", str(count),
             help_text="Queue items per status", typ="gauge",
             labels={"status": status})

    # --- History ---
    t0 = time.monotonic()
    try:
        data = _get(f"{NZBDAV_URL}/api",
                    params={"mode": "history", "output": "json",
                            "apikey": NZBDAV_API_KEY, "limit": "100"})
        if not isinstance(data, dict):
            raise ValueError("history response is not an object")
        history_slots = _slots(data.get("history", {}), "history")
    except Exception as exc:
        log.warning("history scrape failed: %s", exc)
        scrape_success = False
        history_slots = []
    _set("nzbdav_api_latency_seconds_history", f"{time.monotonic() - t0:.4f}",
         help_text="Latency of history API call", typ="gauge")

    completed = sum(1 for slot in history_slots if slot.get("status") == "Completed")
    failed = sum(1 for slot in history_slots if slot.get("status") == "Failed")
    total_history = completed + failed
    ratio = completed / total_history if total_history > 0 else 0.0

    _set("nzbdav_history_completed_total", str(completed),
         help_text="Completed items in recent history", typ="gauge")
    _set("nzbdav_history_failed_total", str(failed),
         help_text="Failed items in recent history", typ="gauge")
    _set("nzbdav_history_success_ratio", f"{ratio:.4f}",
         help_text="Success ratio (completed / completed+failed)", typ="gauge")

    # --- Config (admin API, form-encoded POST) ---
    config_keys = [
        "usenet.segment-cache.enabled",
        "usenet.segment-cache.max-gb",
        "queue.worker-count",
        "usenet.queue-pipelining.depth",
        "repair.enable",
        "play.watchdog-enabled",
        "preflight.mode",
        "usenet.max-download-connections-per-stream",
    ]
    t0 = time.monotonic()
    config_success = False
    with _lock:
        config = dict(_last_config)
    try:
        data = _get(f"{NZBDAV_URL}/api/get-config",
                    method="POST",
                    data=[("config-keys", key) for key in config_keys],
                    headers=headers)
        if not isinstance(data, dict):
            raise ValueError("config response is not an object")
        if data.get("status") is False or str(data.get("status", "true")).lower() == "false":
            raise ValueError(data.get("error") or "config API returned status=false")
        items = data.get("configItems", [])
        if not isinstance(items, list):
            raise ValueError("configItems is not an array")
        config = {
            item.get("configName", item.get("configKey")): item.get("configValue")
            for item in items
            if isinstance(item, dict) and item.get("configName", item.get("configKey"))
        }
        with _lock:
            _last_config = dict(config)
        config_success = True
    except Exception as exc:
        log.warning("config scrape failed; retaining last known values: %s", exc)
        scrape_success = False
    _set("nzbdav_api_latency_seconds_config", f"{time.monotonic() - t0:.4f}",
         help_text="Latency of config API call", typ="gauge")
    _set("nzbdav_config_scrape_success", "1" if config_success else "0",
         help_text="1 if the latest NzbDAV config scrape succeeded", typ="gauge")

    def _bool_val(key: str) -> str:
        return "1" if str(config.get(key, "")).lower() == "true" else "0"

    _set("nzbdav_config_segment_cache_enabled", _bool_val("usenet.segment-cache.enabled"),
         help_text="1 if segment cache is enabled", typ="gauge")
    _set("nzbdav_config_segment_cache_max_gb",
         _as_number(config.get("usenet.segment-cache.max-gb")),
         help_text="Configured max segment cache in GB", typ="gauge")
    _set("nzbdav_config_queue_worker_count", _as_number(config.get("queue.worker-count")),
         help_text="Configured queue worker count", typ="gauge")
    _set("nzbdav_config_pipelining_depth", _as_number(config.get("usenet.queue-pipelining.depth")),
         help_text="Configured pipelining depth", typ="gauge")
    _set("nzbdav_config_repair_enabled", _bool_val("repair.enable"),
         help_text="1 if repair is enabled", typ="gauge")
    _set("nzbdav_config_watchdog_enabled", _bool_val("play.watchdog-enabled"),
         help_text="1 if watchdog is enabled", typ="gauge")
    _set("nzbdav_config_preflight_mode", "0",
         help_text="Preflight mode (see nzbdav_config_preflight_mode_info label)", typ="gauge")
    _remove_family("nzbdav_config_preflight_mode_info")
    _set("nzbdav_config_preflight_mode_info", "1",
         help_text="Configured preflight mode", typ="gauge",
         labels={"mode": config.get("preflight.mode") or "unknown"})
    _set("nzbdav_config_max_connections_per_stream",
         _bool_val("usenet.max-download-connections-per-stream"),
         help_text="1 if per-stream connection cap is enabled", typ="gauge")
    _set("nzbdav_up", "1" if scrape_success else "0",
         help_text="1 if the exporter completed a queue, history, and config scrape", typ="gauge")

    # --- Health ---
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(f"{NZBDAV_URL}/healthz")
        with urllib.request.urlopen(req, timeout=5) as resp:
            healthy = resp.status == 200
    except Exception:
        healthy = False
    _set("nzbdav_health_healthy", "1" if healthy else "0",
         help_text="1 if /healthz returned 200", typ="gauge")
    _set("nzbdav_api_latency_seconds_health", f"{time.monotonic() - t0:.4f}",
         help_text="Latency of healthz call", typ="gauge")

    log.info("scrape ok: queue=%d active=%d history=%d/%d config_keys=%d",
             total, active, completed, failed, len(config))


def render_metrics() -> bytes:
    with _lock:
        lines = []
        for name, (help_text, typ) in _metric_help.items():
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {typ}")
            for key, value in _metrics.items():
                if key == name or key.startswith(name + "{"):
                    lines.append(f"{key} {value}")
        return ("\n".join(lines) + "\n").encode()


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            body = render_metrics()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def main():
    if not NZBDAV_API_KEY:
        log.error("NZBDAV_API_KEY not set — cannot scrape")

    t = Thread(target=_scraper, daemon=True)
    t.start()
    log.info("exporter listening on :9200, scraping %s every %ds", NZBDAV_URL, SCRAPE_INTERVAL)

    server = HTTPServer(("0.0.0.0", 9200), MetricsHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
