"""Coverage for scripts/gaps2-prune-history.py.

The script deletes results out of GAPS-2's data dir, so the two things worth
proving are that it drops exactly the entries naming an uncovered library and
that a dry run writes nothing at all. The backup and the atomic replace are
what make a wrong answer recoverable rather than final.
"""
import json

import pytest


def _write(data_dir, name, value):
    (data_dir / name).write_text(json.dumps(value))


def _entry(entry_id, libraries, missing=1):
    return {"id": entry_id, "libraries": libraries, "missing": missing,
            "mediaType": "movie", "timestamp": "2026-08-12T16:00:00+00:00"}


@pytest.fixture
def data_dir(tmp_path):
    _write(tmp_path, "scan_history.json", [
        _entry("keep-movies", ["Movies"], 994),
        _entry("drop-anime-movies", ["Anime Movies"], 286),
        _entry("keep-shows", ["Shows"], 219),
        _entry("drop-anime-shows", ["Anime Shows"], 35),
    ])
    _write(tmp_path, "last_scan.json", {"libraries": ["Movies"], "gaps": [{"tmdbId": 1}]})
    _write(tmp_path, "last_tv_scan.json", {"libraries": ["Anime Shows"], "gaps": [{"tvdbId": 2}]})
    return tmp_path


def _history(data_dir):
    return json.loads((data_dir / "scan_history.json").read_text())


def test_drops_only_uncovered_libraries(gaps2_prune_history, data_dir):
    kept, dropped = gaps2_prune_history.prune_history(data_dir, dry_run=False)
    assert (kept, dropped) == (2, 2)
    assert [e["id"] for e in _history(data_dir)] == ["keep-movies", "keep-shows"]


def test_merged_scans_count_as_uncovered(gaps2_prune_history, data_dir):
    """A scan covering one kept and one dropped library cannot be attributed
    to either - same reason the router ignores merged scans - so it goes."""
    _write(data_dir, "scan_history.json", [_entry("merged", ["Movies", "Anime Movies"])])
    gaps2_prune_history.prune_history(data_dir, dry_run=False)
    assert _history(data_dir) == []


def test_a_clean_history_is_left_untouched(gaps2_prune_history, data_dir):
    _write(data_dir, "scan_history.json", [_entry("keep-movies", ["Movies"])])
    before = (data_dir / "scan_history.json").read_text()
    kept, dropped = gaps2_prune_history.prune_history(data_dir, dry_run=False)
    assert (kept, dropped) == (1, 0)
    assert (data_dir / "scan_history.json").read_text() == before
    assert not list(data_dir.glob("*.bak-*"))


def test_the_original_is_backed_up_before_a_rewrite(gaps2_prune_history, data_dir):
    gaps2_prune_history.prune_history(data_dir, dry_run=False)
    backups = list(data_dir.glob("scan_history.json.bak-*"))
    assert len(backups) == 1
    assert len(json.loads(backups[0].read_text())) == 4


def test_dry_run_writes_nothing(gaps2_prune_history, data_dir):
    before = (data_dir / "scan_history.json").read_text()
    kept, dropped = gaps2_prune_history.prune_history(data_dir, dry_run=True)
    assert (kept, dropped) == (2, 2)
    assert (data_dir / "scan_history.json").read_text() == before
    assert not list(data_dir.glob("*.bak-*"))

    assert gaps2_prune_history.prune_last_scans(data_dir, dry_run=True) == 1
    assert (data_dir / "last_tv_scan.json").exists()


def test_no_temp_file_is_left_behind(gaps2_prune_history, data_dir):
    """The rewrite goes through a temp file + os.replace; a leftover .prune-tmp
    would mean the replace never happened."""
    gaps2_prune_history.prune_history(data_dir, dry_run=False)
    assert not list(data_dir.glob("*.prune-tmp"))


def test_last_scan_of_a_dropped_library_is_deleted_not_emptied(gaps2_prune_history, data_dir):
    """An empty gap list reads as 'scanned, nothing missing'; a missing file
    reads as 'never scanned', which is the truth here."""
    assert gaps2_prune_history.prune_last_scans(data_dir, dry_run=False) == 1
    assert not (data_dir / "last_tv_scan.json").exists()
    assert (data_dir / "last_scan.json").exists()
    assert list(data_dir.glob("last_tv_scan.json.bak-*"))


def test_missing_files_are_not_an_error(gaps2_prune_history, tmp_path):
    assert gaps2_prune_history.prune_history(tmp_path, dry_run=False) == (0, 0)
    assert gaps2_prune_history.prune_last_scans(tmp_path, dry_run=False) == 0


def test_corrupt_history_is_refused_rather_than_rewritten(gaps2_prune_history, data_dir):
    (data_dir / "scan_history.json").write_text("{not json")
    with pytest.raises(SystemExit, match="not valid JSON"):
        gaps2_prune_history.prune_history(data_dir, dry_run=False)


def test_covered_set_comes_from_the_routing_table(gaps2_prune_history):
    from services.gaps2.libraries import LIBRARY_NAMES

    assert gaps2_prune_history.LIBRARY_NAMES == LIBRARY_NAMES
    assert gaps2_prune_history.uncovered(["Movies", "Anime Movies"]) == ["Anime Movies"]
    assert gaps2_prune_history.uncovered([]) == []
