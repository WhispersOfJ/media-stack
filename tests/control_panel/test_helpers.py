import pytest


def test_human_size_falsy_is_unknown(cp_app):
    assert cp_app.human_size(None) == "?"
    assert cp_app.human_size(0) == "?"


@pytest.mark.parametrize(
    "n,expected",
    [
        (500, "500.0 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1024 ** 3, "1.0 GB"),
        (1024 ** 4, "1.0 TB"),
        (1024 ** 5, "1.0 PB"),
    ],
)
def test_human_size_units(cp_app, n, expected):
    assert cp_app.human_size(n) == expected


def test_ok_shape(cp_app):
    result = cp_app.ok("did the thing", extra=1)
    assert result["ok"] is True
    assert result["message"] == "did the thing"
    assert result["extra"] == 1
    assert "time" in result


def test_fail_raises_http_exception(cp_app):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        cp_app.fail("nope", status_code=404)
    assert exc.value.status_code == 404
    assert exc.value.detail["ok"] is False
    assert exc.value.detail["message"] == "nope"


def test_fail_default_status_code(cp_app):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        cp_app.fail("upstream broke")
    assert exc.value.status_code == 502


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (float("inf"), "unknown"),
        (-1, "unknown"),
        (45, "45s"),
        (125, "2m05s"),
        (3661, "1h01m"),
        (90000, "1d01h"),
    ],
)
def test_format_eta(cp_app, seconds, expected):
    assert cp_app.format_eta(seconds) == expected


@pytest.mark.parametrize(
    "value",
    [None, "", "not-a-date"],
)
def test_parse_air_date_invalid_returns_none(cp_app, value):
    assert cp_app.parse_air_date(value) is None


def test_parse_air_date_parses_iso(cp_app):
    result = cp_app.parse_air_date("2024-01-15T20:00:00Z")
    assert result.year == 2024
    assert result.month == 1
    assert result.day == 15


def test_bucket_arr_item_importing_regardless_of_sizeleft(cp_app):
    q = {"id": 1, "title": "Foo", "size": 1000, "sizeleft": 500, "trackedDownloadState": "importPending"}
    bucket, item = cp_app._bucket_arr_item(q, {})
    assert bucket == "importing"
    assert item["note"] == "fully fetched, waiting on import"


def test_bucket_arr_item_queued(cp_app):
    q = {"id": 1, "title": "Foo", "size": 1000, "sizeleft": 0}
    bucket, item = cp_app._bucket_arr_item(q, {})
    assert bucket == "queued"
    assert item["note"] == "queued, not yet started"


def test_bucket_arr_item_downloading(cp_app):
    q = {"id": 1, "title": "Foo", "size": 3000, "sizeleft": 1000}
    bucket, item = cp_app._bucket_arr_item(q, {1: 2000})
    assert bucket == "downloading"
    assert item["eta"] == "4s"
    assert "speed" in item


def test_bucket_arr_item_stalled_no_prior_sample(cp_app):
    q = {"id": 1, "title": "Foo", "size": 3000, "sizeleft": 1000}
    bucket, item = cp_app._bucket_arr_item(q, {})
    assert bucket == "stalled"


def test_bucket_arr_item_stalled_no_progress(cp_app):
    q = {"id": 1, "title": "Foo", "size": 3000, "sizeleft": 1000}
    bucket, item = cp_app._bucket_arr_item(q, {1: 1000})
    assert bucket == "stalled"


def test_bucket_bearmount_item_importing(cp_app):
    s = {"nzo_id": "a", "filename": "Foo", "mb": 100, "mbleft": 0, "status": "Downloading"}
    bucket, item = cp_app._bucket_bearmount_item(s, {})
    assert bucket == "importing"


def test_bucket_bearmount_item_queued(cp_app):
    s = {"nzo_id": "a", "filename": "Foo", "mb": 100, "mbleft": 50, "status": "Queued"}
    bucket, item = cp_app._bucket_bearmount_item(s, {})
    assert bucket == "queued"


def test_bucket_bearmount_item_downloading(cp_app):
    s = {"nzo_id": "a", "filename": "Foo", "mb": 100, "mbleft": 40, "status": "Downloading"}
    bucket, item = cp_app._bucket_bearmount_item(s, {"a": 60.0})
    assert bucket == "downloading"
    assert "eta" in item


def test_bucket_plex_activity_downloading(cp_app):
    a = {"uuid": "t1", "title": "Scanning TV Shows", "progress": 60}
    bucket, item = cp_app._bucket_plex_activity(a, {"t1": 30})
    assert bucket == "downloading"
    assert item["progress"] == "60%"


def test_bucket_plex_activity_stalled(cp_app):
    a = {"uuid": "t1", "title": "Scanning TV Shows", "progress": 30}
    bucket, item = cp_app._bucket_plex_activity(a, {"t1": 30})
    assert bucket == "stalled"


def test_bucket_plex_activity_includes_subtitle(cp_app):
    a = {"uuid": "t1", "title": "Scanning TV Shows", "subtitle": "Some Series", "progress": 10}
    bucket, item = cp_app._bucket_plex_activity(a, {})
    assert item["title"] == "Scanning TV Shows: Some Series"
