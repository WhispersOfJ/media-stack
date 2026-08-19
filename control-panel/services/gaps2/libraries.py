"""The canonical Plex-library -> Arr-instance routing table for GAPS-2.

One definition, imported by both `services/gaps2/router.py` and
`scripts/gaps2-provision.py`, so the mapping can never drift between the
thing that provisions GAPS-2 and the thing that reads its results.

Scope: general libraries only
-----------------------------
GAPS-2 covers Movies and Shows. The anime libraries (Anime Movies, Anime
Shows) were removed from this table on 2026-08-12 at Bear's request (this
predates the 2026-08-18 anime-instance merge, so the exclusion still
applies now that both libraries route through base radarr/sonarr).
Collection/franchise gap detection is a poor
fit for anime: TMDB collections and TheTVDB franchises model anime seasons,
OVAs, specials and recap films inconsistently, so a "gap" there is far more
often a metadata artefact than a title actually worth grabbing.

Removing them also collapses the routing problem. With one movie library and
one show library there is exactly one Radarr and one Sonarr in scope, which
is precisely what GAPS-2 itself can hold, so GAPS-2's own Radarr/Sonarr
connections are now provisioned too (`scripts/gaps2-provision.py`) and its
web UI's Add button lands titles in the same place `/api/gaps2/push` does.

This table stays regardless. It is what makes /missing and /push name their
destination explicitly, and what rejects a library that is not covered
instead of silently defaulting to one.

Why scans run one library at a time
-----------------------------------
GAPS-2's scan accepts a `libraryNames` LIST and merges the owned titles from
all of them into a single deduplicated result. Its progress/result structure
records `libraries` at the scan level and the gap objects themselves carry no
library field (`services/scan_progress.py`, `services/scan_history.py`), so a
merged multi-library scan produces gaps that cannot be attributed back to a
library afterwards - and therefore cannot be routed.

Scanning one library per scan makes each completed scan a scan-history entry
whose `libraries` field is exactly one name, which is what lets `/missing`
and `/push` attribute every gap deterministically. Attribution comes from
GAPS-2's own persisted history rather than a cache maintained here.
"""

# `kind` selects which half of GAPS-2's API a library goes through: movie
# libraries scan via TMDB collections (/api/recommendations/scan) and push by
# tmdbId, show libraries scan via TheTVDB franchises (/api/tvdb/scan) and push
# by tvdbId. `arr` is a key into core.arr_client.ARR_APPS.
LIBRARIES = (
    {"plex_library": "Movies", "kind": "movie", "arr": "radarr"},
    {"plex_library": "Shows", "kind": "show", "arr": "sonarr"},
)

MOVIE_LIBRARIES = tuple(lib["plex_library"] for lib in LIBRARIES if lib["kind"] == "movie")
SHOW_LIBRARIES = tuple(lib["plex_library"] for lib in LIBRARIES if lib["kind"] == "show")
LIBRARY_NAMES = tuple(lib["plex_library"] for lib in LIBRARIES)

_BY_NAME = {lib["plex_library"]: lib for lib in LIBRARIES}


def library(name: str) -> dict | None:
    """The routing entry for a Plex library name, or None if unknown."""
    return _BY_NAME.get(name)


def arr_for_library(name: str) -> str | None:
    """The ARR_APPS key a gap found in `name` should be pushed to."""
    entry = _BY_NAME.get(name)
    return entry["arr"] if entry else None


def kind_for_library(name: str) -> str | None:
    """'movie' or 'show' for a Plex library name, or None if unknown."""
    entry = _BY_NAME.get(name)
    return entry["kind"] if entry else None


def libraries_for_kind(kind: str) -> tuple[str, ...]:
    """Every Plex library name of a given kind ('movie' or 'show')."""
    return tuple(lib["plex_library"] for lib in LIBRARIES if lib["kind"] == kind)
