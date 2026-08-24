#!/usr/bin/env python3
"""Update fish functions to use Django API v2 paths.

This script updates all fish functions that call the control panel API
to use the new /api/v2/* paths instead of the old /api/* paths.

Path mapping:
- /api/arr/$app/... → /api/v2/arr/$app/...
- /api/arr/letterboxd/... → /api/v2/letterboxd/...
- /api/arr/radarr/add-from-letterboxd → /api/v2/letterboxd/add
- /api/arr/radarr/add-from-letterboxd-list → /api/v2/letterboxd/add-from-list
- /api/arr/radarr/import-list/add → /api/v2/letterboxd/add (or radarr-specific)
- /api/arr/sonarr/import-list/add → /api/v2/letterboxd/add (or sonarr-specific)
- /api/container/... → /api/v2/host/container/...
- /api/mdblist/... → /api/v2/mdblist/...
- /api/plex/... → /api/v2/plex/...
- /api/ratings/... → /api/v2/ratings/...
- /api/watchstate/... → /api/v2/watchstate/...
- /api/nzbdav/... → /api/v2/nzbdav/...
"""

import re
from pathlib import Path

# Path mappings: (old_pattern, new_pattern)
# Using regex for flexible matching
PATH_MAPPINGS = [
    # arr endpoints (keep $app variable)
    (r'/api/arr/(\$app)/', r'/api/v2/arr/\1/'),
    (r'/api/arr/(\$\{app\})/', r'/api/v2/arr/\1/'),
    
    # letterboxd endpoints (moved from /api/arr/letterboxd/ to /api/v2/letterboxd/)
    (r'/api/arr/letterboxd/', r'/api/v2/letterboxd/'),
    
    # radarr-specific letterboxd endpoints
    (r'/api/arr/radarr/add-from-letterboxd-list', r'/api/v2/letterboxd/add-from-list'),
    (r'/api/arr/radarr/add-from-letterboxd', r'/api/v2/letterboxd/add'),
    (r'/api/arr/radarr/import-list/add', r'/api/v2/radarr/exclude'),  # or keep as-is if different
    
    # sonarr-specific endpoints
    (r'/api/arr/sonarr/import-list/add', r'/api/v2/sonarr/monitor-episodes-fix'),  # or keep as-is
    (r'/api/arr/sonarr/monitor-episodes-fix', r'/api/v2/sonarr/monitor-episodes-fix'),
    
    # container endpoints
    (r'/api/container/', r'/api/v2/host/container/'),
    
    # mdblist endpoints
    (r'/api/mdblist/', r'/api/v2/mdblist/'),
    
    # plex endpoints
    (r'/api/plex/', r'/api/v2/plex/'),
    
    # ratings endpoints
    (r'/api/ratings/', r'/api/v2/ratings/'),
    
    # watchstate endpoints
    (r'/api/watchstate/', r'/api/v2/watchstate/'),
    
    # nzbdav endpoints
    (r'/api/nzbdav/', r'/api/v2/nzbdav/'),
    
    # queue endpoints
    (r'/api/arr/queue-autofix', r'/api/v2/arr/queue-autofix'),
    (r'/api/arr/queue-errors', r'/api/v2/arr/queue-errors'),
    
    # host endpoints (if any)
    (r'/api/host/', r'/api/v2/host/'),
]

def update_file(filepath: Path, dry_run: bool = False) -> list[str]:
    """Update API paths in a fish function file."""
    content = filepath.read_text()
    original = content
    changes = []
    
    for old_pattern, new_pattern in PATH_MAPPINGS:
        # Find all matches and track changes
        matches = re.findall(old_pattern, content)
        if matches:
            content = re.sub(old_pattern, new_pattern, content)
            changes.append(f"  {old_pattern} → {new_pattern} ({len(matches)} matches)")
    
    if content != original:
        if not dry_run:
            filepath.write_text(content)
        return changes
    return []

def main():
    import sys
    
    dry_run = '--dry-run' in sys.argv
    fish_dir = Path('/home/bear/Claude/media-stack/fish-functions')
    
    updated = 0
    skipped = 0
    
    for fish_file in sorted(fish_dir.glob('stack-*.fish')):
        changes = update_file(fish_file, dry_run=dry_run)
        if changes:
            print(f"{'[DRY RUN] ' if dry_run else ''}Updated: {fish_file.name}")
            for change in changes:
                print(change)
            updated += 1
        else:
            skipped += 1
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Summary:")
    print(f"  Updated: {updated} files")
    print(f"  Skipped: {skipped} files (no changes needed)")

if __name__ == '__main__':
    main()
