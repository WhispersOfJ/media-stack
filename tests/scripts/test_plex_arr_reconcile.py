"""Gate tests for the Plex/Arr reconcile.

The bug these exist to prevent is the one the first run of this script actually
had on 2026-08-13: it reported 1,269 broken items when only 75 were broken.
Every deleted-flagged row was counted as damage, including the 1,194 whose file
is genuinely gone - which is correct behaviour on this stack, because
autoEmptyTrash is disabled on purpose so soft deletes are never purged.

The distinguishing signal is whether the file still exists. classify() is the
place that decision lives, so it is the place worth pinning down.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/plex-arr-reconcile.py"


@pytest.fixture(scope="module")
def rec():
    spec = importlib.util.spec_from_file_location("_script_plex_arr_reconcile", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_script_plex_arr_reconcile"] = module
    spec.loader.exec_module(module)
    return module


MKV = "/data/anime-shows/Fairy Tail/Season 1/Fairy.Tail.E19.mkv"
ISO = "/data/movies/Aswang (1994) {tmdb-133535}/Aswang (1994) - [DVD-R].iso"


def test_visible_in_plex_is_ok(rec):
    assert rec.classify(MKV, in_live=True, in_trashed=False, on_disk=True) == "ok"


def test_trashed_with_the_file_still_there_is_the_red_trash_can(rec):
    assert rec.classify(MKV, in_live=False, in_trashed=True,
                        on_disk=True) == "trashed_in_plex"


def test_trashed_with_the_file_gone_is_not_damage(rec):
    """The 1,194 case. Calling this broken overstates the problem 17x."""
    assert rec.classify(MKV, in_live=False, in_trashed=True,
                        on_disk=False) == "stale_trash"


def test_a_live_row_wins_even_if_a_deleted_row_also_exists(rec):
    """A re-import leaves the old row flagged and adds a new one. The item is
    visible, so it is not a finding."""
    assert rec.classify(MKV, in_live=True, in_trashed=True, on_disk=True) == "ok"


def test_disc_image_plex_cannot_index_is_not_a_scan_failure(rec):
    assert rec.classify(ISO, in_live=False, in_trashed=False,
                        on_disk=True) == "unsupported"


def test_unsupported_check_is_case_insensitive(rec):
    assert rec.classify(ISO.replace(".iso", ".ISO"), in_live=False,
                        in_trashed=False, on_disk=True) == "unsupported"


def test_a_trashed_disc_image_is_judged_on_the_file_not_the_suffix(rec):
    """Suffix must not short-circuit the trashed branch - a disc image Plex
    already has a deleted row for is stale trash, not 'unsupported'."""
    assert rec.classify(ISO, in_live=False, in_trashed=True,
                        on_disk=False) == "stale_trash"


def test_normal_file_plex_never_saw_needs_a_scan(rec):
    assert rec.classify(MKV, in_live=False, in_trashed=False,
                        on_disk=True) == "missing_from_plex"


@pytest.mark.parametrize("path,expected", [
    ("/data/movies/X (2020)/X.mkv", "Movies"),
    ("/data/anime-movies/Y (2021)/Y.mkv", "Anime Movies"),
    ("/data/shows/Z/Season 1/Z.mkv", "Shows"),
    ("/data/anime-shows/W/Season 1/W.mkv", "Anime Shows"),
    ("/mnt/somewhere/else.mkv", None),
])
def test_library_is_derived_from_the_path_not_the_arr_instance(rec, path, expected):
    """radarr-anime writing into /data/movies must be filed under Movies, or
    the per-library totals silently lie."""
    assert rec.library_of(path) == expected


def test_anime_movies_is_not_swallowed_by_the_movies_prefix(rec):
    """/data/movies/ and /data/anime-movies/ do not share a prefix, but dict
    ordering makes this easy to break with a future rename."""
    assert rec.library_of("/data/anime-movies/A/A.mkv") == "Anime Movies"


def test_every_library_maps_to_a_distinct_plex_section(rec):
    sections = [sid for _, sid in rec.LIBRARIES.values()]
    assert len(set(sections)) == len(sections)
