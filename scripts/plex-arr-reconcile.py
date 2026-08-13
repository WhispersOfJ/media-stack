#!/usr/bin/env python3
"""Reconcile what Radarr/Sonarr think they have against what Plex actually shows.

Three distinct states, which a naive "count comparison" collapses into one and
gets wrong:

  MISSING_FROM_PLEX  - the Arr app has a file on disk, Plex has no row for that
                       path at all. Plex has not scanned it. Fix: scoped scan.
  TRASHED_IN_PLEX    - Plex has a row, but every row for that path is
                       deleted_at-flagged, so the item is invisible and shows
                       the red trash-can overlay, AND the file is still on
                       disk. Fix: restart plex, then rescan.
  STALE_TRASH        - same DB state, but the file really is gone. Correct
                       behaviour, not a fault. These accumulate because this
                       stack disables autoEmptyTrash on purpose, so soft
                       deletes are never purged. Counting these as damage is
                       the easiest way to badly overstate the problem: on
                       2026-08-13 they were 1194 of 1269.
  UNSUPPORTED        - Arr has the file, Plex cannot index that container at
                       all (.iso, .img, disc images). Absent from Plex by
                       design, not a scan failure.
  ORPHAN_IN_PLEX     - Plex shows it, no Arr app tracks the path. Usually a
                       manual import or a leftover after an Arr-side delete.

The on-disk check runs inside the plex container, because "does this file
exist" must be answered through the same mount and the same FUSE handle Plex
itself uses - checking from the host can pass while Plex's own view fails.

Matching is by absolute file path, not title. Both sides use the same
/data/<library>/... paths through the same mount, so path equality is exact
where title matching would produce false pairs across editions and releases.

Library routing is derived from each file's own path prefix rather than from
which Arr instance reported it - radarr-anime writing into /data/movies would
otherwise be silently misfiled.

Usage:
    plex-arr-reconcile.py [--json] [--limit N] [--db PATH]

Reads Arr credentials from .env. Takes its own read-only snapshot of Plex's
SQLite DB unless --db is given, so it never holds a lock on the live database.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"

PLEX_DB_IN_CONTAINER = (
    "/config/Plex Media Server/Plug-in Support/Databases/"
    "com.plexapp.plugins.library.db"
)

# path prefix -> (label, plex library_section_id)
LIBRARIES = {
    "/data/movies/": ("Movies", 1),
    "/data/anime-movies/": ("Anime Movies", 6),
    "/data/shows/": ("Shows", 2),
    "/data/anime-shows/": ("Anime Shows", 7),
}

ARR_INSTANCES = [
    # (label, port, env key for api key, kind)
    ("radarr", 7878, "RADARR_API_KEY", "movie"),
    ("radarr-anime", 7879, "RADARR_ANIME_API_KEY", "movie"),
    ("sonarr", 8989, "SONARR_API_KEY", "series"),
    ("sonarr-anime", 8990, "SONARR_ANIME_API_KEY", "series"),
]


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if not ENV_FILE.is_file():
        return env
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def api_get(port: int, path: str, key: str):
    url = f"http://localhost:{port}/api/v3/{path}"
    req = urllib.request.Request(url, headers={"X-Api-Key": key})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def arr_paths(env: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Every file path the Arr apps believe is on disk -> which app owns it."""
    owned: dict[str, str] = {}
    problems: list[str] = []
    for label, port, env_key, kind in ARR_INSTANCES:
        key = env.get(env_key, "")
        if not key:
            problems.append(f"{label}: no {env_key} in .env")
            continue
        try:
            if kind == "movie":
                for movie in api_get(port, "movie", key):
                    path = (movie.get("movieFile") or {}).get("path")
                    if movie.get("hasFile") and path:
                        owned[path] = label
            else:
                for series in api_get(port, "series", key):
                    files = api_get(port, f"episodefile?seriesId={series['id']}", key)
                    for ep in files:
                        if ep.get("path"):
                            owned[ep["path"]] = label
        except (urllib.error.URLError, OSError, KeyError) as exc:
            problems.append(f"{label}: {exc}")
    return owned, problems


def snapshot_plex_db(explicit: str | None) -> tuple[Path, bool]:
    if explicit:
        return Path(explicit), False
    tmp = Path(tempfile.mkdtemp(prefix="plex-reconcile-")) / "library.db"
    subprocess.run(
        ["docker", "cp", f"plex:{PLEX_DB_IN_CONTAINER}", str(tmp)],
        check=True, capture_output=True,
    )
    return tmp, True


def plex_paths(db: Path) -> tuple[set[str], set[str]]:
    """(paths with at least one live row, paths whose every row is deleted)."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute("""
        SELECT mp.file,
               SUM(CASE WHEN mi.deleted_at IS NULL THEN 1 ELSE 0 END) AS live
        FROM metadata_items mi
        JOIN media_items m  ON m.metadata_item_id = mi.id
        JOIN media_parts mp ON mp.media_item_id = m.id
        WHERE mp.file IS NOT NULL
        GROUP BY mp.file
    """).fetchall()
    con.close()
    live = {f for f, n in rows if n}
    trashed = {f for f, n in rows if not n}
    return live, trashed


# Plex has no demuxer for a disc image. Radarr happily tracks one as a movie
# file, so it shows up as "missing from Plex" forever and is not actionable.
UNSUPPORTED_SUFFIXES = (".iso", ".img", ".mk3d", ".bin", ".nrg")


def exists_in_plex_container(paths: list[str]) -> set[str]:
    """Which of these paths exist, checked from inside the plex container.

    One `docker exec` for the whole batch: 1200 separate execs would take
    minutes and hammer the mount. Paths go in over stdin, NUL-free but
    newline-delimited, because no path in this library contains a newline.
    """
    if not paths:
        return set()
    script = (
        'while IFS= read -r f; do [ -e "$f" ] && printf "%s\\n" "$f"; done'
    )
    result = subprocess.run(
        ["docker", "exec", "-i", "plex", "sh", "-c", script],
        input="\n".join(paths), capture_output=True, text=True, timeout=900,
    )
    return {line for line in result.stdout.splitlines() if line}


def library_of(path: str) -> str | None:
    for prefix, (label, _) in LIBRARIES.items():
        if path.startswith(prefix):
            return label
    return None


def classify(path: str, *, in_live: bool, in_trashed: bool, on_disk: bool) -> str:
    """Which bucket a single Arr-owned path falls into.

    Pure, so the interesting decision in this script is testable without a
    running Plex or a mounted library. The order matters: a trashed path is
    judged on whether the file survives, and only a path Plex has never seen
    at all can be an unsupported-container case.
    """
    if in_live:
        return "ok"
    if in_trashed:
        return "trashed_in_plex" if on_disk else "stale_trash"
    if path.lower().endswith(UNSUPPORTED_SUFFIXES):
        return "unsupported"
    return "missing_from_plex"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, default=15,
                        help="example paths to print per bucket (default 15)")
    parser.add_argument("--db", help="use an existing Plex DB snapshot")
    args = parser.parse_args()

    env = load_env()
    arr, problems = arr_paths(env)
    db, temporary = snapshot_plex_db(args.db)
    try:
        live, trashed = plex_paths(db)
    finally:
        if temporary:
            shutil.rmtree(db.parent, ignore_errors=True)

    buckets = ("missing_from_plex", "trashed_in_plex", "stale_trash",
               "unsupported", "orphan_in_plex")
    report: dict[str, dict] = {}
    for label, _ in LIBRARIES.values():
        report[label] = {"arr": 0, "plex_live": 0, **{b: [] for b in buckets}}

    absent_from_live = []
    for path in arr:
        label = library_of(path)
        if label is None:
            continue
        report[label]["arr"] += 1
        if path not in live:
            absent_from_live.append(path)

    for path in live:
        label = library_of(path)
        if label is None:
            continue
        report[label]["plex_live"] += 1
        if path not in arr:
            report[label]["orphan_in_plex"].append(path)

    # A trashed path Plex knows about but no Arr app tracks still shows the red
    # overlay, so it belongs in the sweep even though no Arr row named it.
    trashed_unowned = [p for p in trashed
                       if p not in arr and library_of(p) is not None]

    # One existence sweep for everything whose state depends on it.
    candidates = sorted(set(absent_from_live) | set(trashed_unowned))
    on_disk = exists_in_plex_container(candidates)

    for path in absent_from_live:
        bucket = classify(path, in_live=False, in_trashed=path in trashed,
                          on_disk=path in on_disk)
        report[library_of(path)][bucket].append(path)

    for path in trashed_unowned:
        label = library_of(path)
        report[label]["trashed_in_plex" if path in on_disk
                      else "stale_trash"].append(path)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    for problem in problems:
        print(f"  WARNING  {problem}")
    if problems:
        print()

    header = (f"{'Library':<14}{'Arr':>8}{'Plex':>8}{'Missing':>9}"
              f"{'Trashed':>9}{'Stale':>8}{'Unsup':>7}{'Orphan':>8}")
    print(header)
    print("─" * len(header))
    totals = [0] * 7
    for label in ("Movies", "Anime Movies", "Shows", "Anime Shows"):
        r = report[label]
        counts = [r["arr"], r["plex_live"], len(r["missing_from_plex"]),
                  len(r["trashed_in_plex"]), len(r["stale_trash"]),
                  len(r["unsupported"]), len(r["orphan_in_plex"])]
        totals = [t + c for t, c in zip(totals, counts)]
        print(f"{label:<14}{counts[0]:>8}{counts[1]:>8}{counts[2]:>9}"
              f"{counts[3]:>9}{counts[4]:>8}{counts[5]:>7}{counts[6]:>8}")
    print("─" * len(header))
    print(f"{'TOTAL':<14}{totals[0]:>8}{totals[1]:>8}{totals[2]:>9}"
          f"{totals[3]:>9}{totals[4]:>8}{totals[5]:>7}{totals[6]:>8}")

    for bucket, headline in (
        ("trashed_in_plex", "ACTIONABLE - on disk, deleted-flagged in Plex (red trash-can)"),
        ("missing_from_plex", "ACTIONABLE - in an Arr app, absent from Plex (needs a scan)"),
        ("unsupported", "Not actionable - container Plex cannot index"),
        ("orphan_in_plex", "In Plex, tracked by no Arr app"),
    ):
        paths = [p for label in report for p in report[label][bucket]]
        if not paths:
            continue
        print(f"\n=== {headline}: {len(paths)} ===")
        for path in sorted(paths)[:args.limit]:
            print(f"  {path}")
        if len(paths) > args.limit:
            print(f"  ... and {len(paths) - args.limit} more")

    if totals[4]:
        print(f"\n{totals[4]} stale-trash rows suppressed (file genuinely gone, "
              "autoEmptyTrash disabled on purpose - not damage).")

    return 1 if totals[2] + totals[3] else 0


if __name__ == "__main__":
    raise SystemExit(main())
