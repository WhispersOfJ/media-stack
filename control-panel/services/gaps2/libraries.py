"""The canonical Plex-library -> Arr-instance routing table for GAPS-2.

One definition, imported by both `services/gaps2/router.py` and
`scripts/gaps2-provision.py`, so the mapping can never drift between the
thing that provisions GAPS-2 and the thing that reads its results. Same
single-definition arrangement as `services/organizr/tabs.py` from Phase 3.

Why this table has to exist at all
----------------------------------
GAPS-2 stores exactly ONE Radarr connection and ONE Sonarr connection
(`CONFIG_KEY = 'radarr'` / `'sonarr'` in its own service modules), with no
notion of a second instance. This stack has four Arr instances, split
general/anime. So GAPS-2 cannot be the thing that decides where a found gap
gets pushed - it would send every gap to whichever single instance it was
configured with, landing anime titles in the general Radarr's root folder
under the general quality profile.

Instead GAPS-2 is used purely as the gap *detector*, and this table plus the
push route in `router.py` own the routing decision. Bear chose this over
running a second `gaps2-anime` container (2026-08-12), because one instance
can already scan every library and a second container would duplicate the
scan work for nothing.

Why scans run one library at a time
-----------------------------------
GAPS-2's scan accepts a `libraryNames` LIST and merges the owned titles from
all of them into a single deduplicated result. Its progress/result structure
records `libraries` at the scan level and the gap objects themselves carry no
library field (`services/scan_progress.py`, `services/scan_history.py`), so a
merged Movies + Anime Movies scan produces gaps that cannot be attributed
back to a library afterwards - and therefore cannot be routed.

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
    {"plex_library": "Anime Movies", "kind": "movie", "arr": "radarr_anime"},
    {"plex_library": "Shows", "kind": "show", "arr": "sonarr"},
    {"plex_library": "Anime Shows", "kind": "show", "arr": "sonarr_anime"},
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
