#!/usr/bin/env python3
"""NzbDAV Prometheus exporter (stdlib only, zero pip dependencies).

Scrapes NzbDAV's SABnzbd-compatible queue/history API and admin health API,
then exposes Prometheus metrics on :9200/metrics.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Lock, Thread

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nzbdav-exporter")

NZBDAV_URL = os.environ.get("NZBDAV_URL", "http://nzbdav:3000")
NZBDAV_API_KEY = os.environ.get("NZBDAV_API_KEY", "")
SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", "15"))

# ---------------------------------------------------------------------------
# Metric storage
# ---------------------------------------------------------------------------
_metrics: dict[str, str] = {}
_lock = Lock()


def _set(name: str, value: str, help_text: str = "", typ: str = "gauge"):
    """Register a metric line (help only on first write)."""
    with _lock:
        if name not in _metrics:
            if help_text:
                _metrics[f"# HELP {name}"] = help_text
                _metrics[f"# TYPE {name}"] = typ
        _metrics[name] = value


def _get(url: str, params: dict | None = None, headers: dict | None = None,
         method: str = "GET", data: dict | None = None, timeout: int = 10):
    """HTTP request using stdlib. Returns parsed JSON dict."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
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
            _set("nzbdav_up", "0")
        elapsed = time.monotonic() - t0
        _set("nzbdav_scrape_duration_seconds", f"{elapsed:.4f}",
             help_text="Time spent scraping NzbDAV APIs", typ="gauge")
        time.sleep(SCRAPE_INTERVAL)


def _scrape():
    headers = {"X-Api-Key": NZBDAV_API_KEY}

    # --- Queue ---
    t0 = time.monotonic()
    try:
        data = _get(f"{NZBDAV_URL}/api",
                    params={"mode": "queue", "output": "json", "apikey": NZBDAV_API_KEY})
        queue = data.get("queue", {})
        slots = queue.get("slots", [])
        _set("nzbdav_up", "1")
    except Exception as exc:
        log.warning("queue scrape failed: %s", exc)
        _set("nzbdav_up", "0")
        slots = []
    _set("nzbdav_api_latency_seconds",
         f"{time.monotonic() - t0:.4f}",
         help_text="Latency of queue API call", typ="gauge")

    # Queue metrics
    active = sum(1 for s in slots if s.get("status") == "Downloading")
    total = len(slots)
    total_mbleft = sum(float(s.get("mbleft", 0) or 0) for s in slots)

    _set("nzbdav_queue_active_downloads", str(active),
         help_text="Number of actively downloading items", typ="gauge")
    _set("nzbdav_queue_items_total", str(total),
         help_text="Total items in download queue", typ="gauge")
    _set("nzbdav_queue_depth_bytes", str(int(total_mbleft * 1024 * 1024)),
         help_text="Total bytes remaining across all queue items", typ="gauge")

    # Per-category breakdown
    cat_bytes: dict[str, float] = {}
    for s in slots:
        cat = s.get("cat", "unknown")
        cat_bytes[cat] = cat_bytes.get(cat, 0) + float(s.get("mbleft", 0) or 0)
    for cat, mb in cat_bytes.items():
        _set("nzbdav_queue_per_category_bytes", f'{int(mb * 1024 * 1024)} cat="{cat}"',
             help_text="Bytes remaining per category", typ="gauge")

    # Per-status breakdown
    status_counts: dict[str, int] = {}
    for s in slots:
        st = s.get("status", "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1
    for st, count in status_counts.items():
        _set("nzbdav_queue_per_status_count", f'{count} status="{st}"',
             help_text="Queue items per status", typ="gauge")

    # --- History ---
    t0 = time.monotonic()
    try:
        data = _get(f"{NZBDAV_URL}/api",
                    params={"mode": "history", "output": "json",
                            "apikey": NZBDAV_API_KEY, "limit": "100"})
        history = data.get("history", {})
        hslots = history.get("slots", [])
    except Exception as exc:
        log.warning("history scrape failed: %s", exc)
        hslots = []
    _set("nzbdav_api_latency_seconds_history",
         f"{time.monotonic() - t0:.4f}",
         help_text="Latency of history API call", typ="gauge")

    completed = sum(1 for s in hslots if s.get("status") == "Completed")
    failed = sum(1 for s in hslots if s.get("status") == "Failed")
    total_h = completed + failed
    ratio = completed / total_h if total_h > 0 else 0.0

    _set("nzbdav_history_completed_total", str(completed),
         help_text="Completed items in recent history", typ="gauge")
    _set("nzbdav_history_failed_total", str(failed),
         help_text="Failed items in recent history", typ="gauge")
    _set("nzbdav_history_success_ratio", f"{ratio:.4f}",
         help_text="Success ratio (completed / completed+failed)", typ="gauge")

    # --- Config (admin API, form-encoded POST) ---
    config_keys = [
        "usenet.segmentCache.enabled",
        "usenet.segmentCache.maxGb",
        "queue.workerCount",
        "usenet.pipelining.depth",
        "repair.enable",
        "play.watchdogEnabled",
        "preflight.mode",
        "useNet.maxDownloadConnectionsPerStream",
    ]
    t0 = time.monotonic()
    try:
        data = _get(f"{NZBDAV_URL}/api/get-config",
                    method="POST",
                    data={"config-keys": ",".join(config_keys)},
                    headers=headers)
        items = data.get("configItems", [])
        cfg = {it.get("configKey"): it.get("configValue") for it in items}
    except Exception as exc:
        log.warning("config scrape failed: %s", exc)
        cfg = {}
    _set("nzbdav_api_latency_seconds_config",
         f"{time.monotonic() - t0:.4f}",
         help_text="Latency of config API call", typ="gauge")

    def _bool_val(key: str) -> str:
        return "1" if str(cfg.get(key, "")).lower() == "true" else "0"

    _set("nzbdav_config_segment_cache_enabled", _bool_val("usenet.segmentCache.enabled"),
         help_text="1 if segment cache is enabled", typ="gauge")
    _set("nzbdav_config_segment_cache_max_gb", str(cfg.get("usenet.segmentCache.maxGb", "0")),
         help_text="Configured max segment cache in GB", typ="gauge")
    _set("nzbdav_config_queue_worker_count", str(cfg.get("queue.workerCount", "0")),
         help_text="Configured queue worker count", typ="gauge")
    _set("nzbdav_config_pipelining_depth", str(cfg.get("usenet.pipelining.depth", "0")),
         help_text="Configured pipelining depth", typ="gauge")
    _set("nzbdav_config_repair_enabled", _bool_val("repair.enable"),
         help_text="1 if repair is enabled", typ="gauge")
    _set("nzbdav_config_watchdog_enabled", _bool_val("play.watchdogEnabled"),
         help_text="1 if watchdog is enabled", typ="gauge")
    _set("nzbdav_config_preflight_mode", f'0 mode="{cfg.get("preflight.mode", "unknown")}"',
         help_text="Preflight mode (label)", typ="gauge")
    _set("nzbdav_config_max_connections_per_stream",
         _bool_val("useNet.maxDownloadConnectionsPerStream"),
         help_text="1 if per-stream connection cap is enabled", typ="gauge")

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
    _set("nzbdav_api_latency_seconds_health",
         f"{time.monotonic() - t0:.4f}",
         help_text="Latency of healthz call", typ="gauge")

    log.info("scrape ok: queue=%d active=%d history=%d/%d config_keys=%d",
             total, active, completed, failed, len(cfg))


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------
class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            with _lock:
                body = "\n".join(_metrics.values()) + "\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode())
        elif self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress per-request logging


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
