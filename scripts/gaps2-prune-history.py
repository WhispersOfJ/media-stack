#!/usr/bin/env python3
"""Drop GAPS-2's stored scan results for libraries the routing table no longer
covers.

Written when the anime libraries were removed from
`control-panel/services/gaps2/libraries.py` (2026-08-12). Removing them from
the table stops the control panel scanning, listing or pushing them, but
GAPS-2 keeps everything it already found: the anime entries stay in
`scan_history.json`, and `last_tv_scan.json` was an "Anime Shows" scan, so
GAPS-2's own dashboard still rendered 35 anime gaps.

That matters now in a way it did not before. GAPS-2's Radarr/Sonarr are
configured as of the same change, so those leftover rows carry a working Add
button that files an anime title into the general Radarr/Sonarr under
/data/movies or /data/shows. Deleting the rows removes the button with them.

What it touches, all under GAPS-2's data dir:

  scan_history.json   entries naming any uncovered library are dropped
  last_scan.json      deleted if that scan covered an uncovered library
  last_tv_scan.json   same

Not touched: tmdb_cache.json / tvdb_cache.json (metadata, not results -
re-fetching them costs API round-trips and they hold nothing library-specific)
and config.enc.

Each modified file is copied to <name>.bak-<timestamp> first, and rewritten
via a temp file + os.replace so a crash mid-write cannot truncate it.

Run with the gaps2 container stopped - a scan completing mid-prune would
rewrite the file this has already read.

Usage:  python3 scripts/gaps2-prune-history.py [--dry-run] [--data-dir DIR]
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# The covered-library list has exactly one definition, shared with the router
# and the provisioning script - see that module's docstring.
sys.path.insert(0, str(REPO_ROOT / "control-panel"))
from services.gaps2.libraries import LIBRARY_NAMES  # noqa: E402

DEFAULT_DATA_DIR = REPO_ROOT / "config" / "gaps2"
HISTORY_FILE = "scan_history.json"
LAST_SCAN_FILES = ("last_scan.json", "last_tv_scan.json")


def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except ValueError as e:
        raise SystemExit(f"{path.name} is not valid JSON ({e}) - refusing to touch it.")


def backup(path: Path, dry_run: bool) -> Path:
    dest = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    if not dry_run:
        shutil.copy2(path, dest)
    return dest


def write_json(path: Path, value) -> None:
    """Same atomic write GAPS-2 itself uses for these sidecars."""
    tmp = path.with_name(path.name + ".prune-tmp")
    tmp.write_text(json.dumps(value))
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def uncovered(libraries) -> list[str]:
    """The libraries in a scan entry that the routing table no longer covers.

    An entry is judged by the libraries it names, so a merged scan covering
    one kept and one dropped library counts as uncovered - its gaps cannot be
    attributed back to either, which is the same reason the router ignores
    merged scans.
    """
    return [name for name in (libraries or []) if name not in LIBRARY_NAMES]


def prune_history(data_dir: Path, dry_run: bool) -> tuple[int, int]:
    """Returns (kept, dropped)."""
    path = data_dir / HISTORY_FILE
    entries = read_json(path)
    if entries is None:
        print(f"  {HISTORY_FILE}: not present, nothing to prune")
        return 0, 0
    if not isinstance(entries, list):
        raise SystemExit(f"  {HISTORY_FILE}: expected a list of entries, got {type(entries).__name__}")

    kept, dropped = [], []
    for entry in entries:
        (dropped if uncovered(entry.get("libraries")) else kept).append(entry)

    for entry in dropped:
        print(f"    drop {entry.get('id')} {entry.get('libraries')} "
              f"({entry.get('missing')} gaps, {entry.get('timestamp')})")
    if not dropped:
        print(f"  {HISTORY_FILE}: {len(kept)} entries, none reference an uncovered library")
        return len(kept), 0
    if dry_run:
        print(f"  {HISTORY_FILE}: would drop {len(dropped)}, keep {len(kept)}")
        return len(kept), len(dropped)

    print(f"  {HISTORY_FILE}: backed up to {backup(path, dry_run).name}")
    write_json(path, kept)
    print(f"  {HISTORY_FILE}: dropped {len(dropped)}, kept {len(kept)}")
    return len(kept), len(dropped)


def prune_last_scans(data_dir: Path, dry_run: bool) -> int:
    """Delete the cached most-recent scan when it belonged to a dropped library.

    Deleted rather than emptied: GAPS-2 treats a missing sidecar as "no scan
    yet" (config_store.remove does exactly this), while a file with an empty
    gap list would read as "scanned, nothing missing" - the same
    never-scanned-vs-zero-gaps confusion the status route works to avoid.
    """
    removed = 0
    for name in LAST_SCAN_FILES:
        path = data_dir / name
        scan = read_json(path)
        if scan is None:
            continue
        stale = uncovered(scan.get("libraries"))
        if not stale:
            print(f"  {name}: {scan.get('libraries')} still covered, left alone")
            continue
        if dry_run:
            print(f"  {name}: would delete (last scan was {scan.get('libraries')})")
            removed += 1
            continue
        print(f"  {name}: backed up to {backup(path, dry_run).name}")
        path.unlink()
        print(f"  {name}: deleted (last scan was {scan.get('libraries')})")
        removed += 1
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="GAPS-2 data dir")
    args = parser.parse_args()

    if not args.data_dir.is_dir():
        raise SystemExit(f"{args.data_dir} is not a directory.")

    print(f"Covered libraries: {', '.join(LIBRARY_NAMES)}"
          f"{' (dry run)' if args.dry_run else ''}")
    prune_history(args.data_dir, args.dry_run)
    prune_last_scans(args.data_dir, args.dry_run)
    print("Done." if not args.dry_run else "Dry run complete, nothing written.")


if __name__ == "__main__":
    main()
