"""Cross-app download-queue aggregation, ported from the FastAPI-era
control-panel/services/queue/router.py for the Django/DRF rewrite.

Named `queue_app` (not `queue`) because `queue` collides with Python's
stdlib `queue` module.

Samples every source's remaining-size/progress twice, QUEUE_SAMPLE_SECONDS
apart, and buckets each item into downloading/stalled/queued/importing using
the *observed* delta rather than trusting each app's own (frequently wrong)
timeleft/progress reporting.

Note: Plex activities are now displayed by arr-dashboard (:41789).
This module only aggregates Arr app + NzbDAV queues.
"""
import time

from core.api_base import ServiceError
from core.arr_client import ARR_APPS, QUEUE_ARR_APPS, arr_queue, format_eta, human_size
from core.nzbdav_client import nzbdav_api

QUEUE_SAMPLE_SECONDS = 4


def _arr_sizeleft_snapshot(app_name: str) -> dict[int, int]:
    try:
        records = arr_queue(app_name)
    except ServiceError:
        return {}
    return {q["id"]: q.get("sizeleft") or 0 for q in records if q.get("sizeleft")}


def _nzbdav_mbleft_snapshot() -> dict[str, float]:
    try:
        slots = nzbdav_api("queue").get("queue", {}).get("slots", [])
    except ServiceError:
        return {}
    return {s["nzo_id"]: float(s.get("mbleft") or 0) for s in slots if s.get("status") == "Downloading"}


def _bucket_arr_item(q: dict, prev_sizeleft: dict[int, int]) -> tuple[str, dict]:
    title = q.get("title") or "?"
    size = q.get("size") or 0
    sizeleft = q.get("sizeleft") or 0
    item = {"title": title, "size": human_size(size)}
    if sizeleft > 0:
        item["size_left"] = human_size(sizeleft)
    if q.get("trackedDownloadState") in ("importPending", "importBlocked"):
        item["note"] = "fully fetched, waiting on import"
        return "importing", item
    if sizeleft <= 0:
        item["note"] = "queued, not yet started"
        return "queued", item
    prev = prev_sizeleft.get(q["id"])
    if prev is not None and prev > sizeleft:
        speed = (prev - sizeleft) / QUEUE_SAMPLE_SECONDS
        eta = sizeleft / speed if speed > 0 else float("inf")
        item["speed"] = f"{human_size(speed)}/s"
        item["eta"] = format_eta(eta)
        return "downloading", item
    item["note"] = "no progress observed (still caching, or stalled)"
    return "stalled", item


def _bucket_nzbdav_item(s: dict, prev_mbleft: dict[str, float]) -> tuple[str, dict]:
    title = s.get("filename") or "?"
    mb = float(s.get("mb") or 0)
    mbleft = float(s.get("mbleft") or 0)
    item = {"title": title, "size": f"{mb:.0f} MB", "size_left": f"{mbleft:.0f} MB"}
    if s.get("status") != "Downloading" or mbleft <= 0:
        item["note"] = "queued, not yet started" if mbleft > 0 else "fully fetched, waiting on import"
        return ("queued" if mbleft > 0 else "importing"), item
    prev = prev_mbleft.get(s["nzo_id"])
    if prev is not None and prev > mbleft:
        speed_mb = (prev - mbleft) / QUEUE_SAMPLE_SECONDS
        eta = mbleft / speed_mb if speed_mb > 0 else float("inf")
        item["speed"] = f"{speed_mb:.1f} MB/s"
        item["eta"] = format_eta(eta)
        return "downloading", item
    item["note"] = "no progress observed (still caching, or stalled)"
    return "stalled", item


def aggregate_queue_status() -> dict:
    """Every *arr app's download queue plus NzbDAV's own queue, bucketed
    into downloading/stalled/queued/importing with a real speed/progress
    and ETA for anything actually observed to be draining.

    Note: Plex activities are now displayed by arr-dashboard (:41789)."""
    before_arr = {app_name: _arr_sizeleft_snapshot(app_name) for app_name in QUEUE_ARR_APPS}
    before_nzbdav = _nzbdav_mbleft_snapshot()
    time.sleep(QUEUE_SAMPLE_SECONDS)

    result = {}
    for app_name in QUEUE_ARR_APPS:
        cfg = ARR_APPS[app_name]
        try:
            records = arr_queue(app_name)
        except ServiceError:
            result[app_name] = {"label": cfg["label"], "error": "unreachable"}
            continue
        buckets = {"downloading": [], "stalled": [], "queued": [], "importing": []}
        for q in records:
            bucket, item = _bucket_arr_item(q, before_arr[app_name])
            buckets[bucket].append(item)
        result[app_name] = {"label": cfg["label"], "total": len(records), **buckets}

    try:
        slots = nzbdav_api("queue").get("queue", {}).get("slots", [])
        buckets = {"downloading": [], "stalled": [], "queued": [], "importing": []}
        for s in slots:
            bucket, item = _bucket_nzbdav_item(s, before_nzbdav)
            buckets[bucket].append(item)
        result["nzbdav"] = {"label": "NzbDAV", "total": len(slots), **buckets}
    except ServiceError:
        result["nzbdav"] = {"label": "NzbDAV", "error": "unreachable"}

    return result
