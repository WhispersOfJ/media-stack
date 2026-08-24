#!/usr/bin/env python3
"""Update commands.json to use Django API v2 paths.

This script updates the PathTemplate fields in commands.json
to use the new /api/v2/* paths instead of the old /api/* paths.
"""

import json
from pathlib import Path

# Path mappings for commands.json
PATH_MAPPINGS = [
    # arr endpoints
    ('/api/arr/{1}/', '/api/v2/arr/{1}/'),
    ('/api/arr/{1}', '/api/v2/arr/{1}'),
    ('/api/arr/queue-autofix', '/api/v2/arr/queue-autofix'),
    ('/api/arr/queue-errors', '/api/v2/arr/queue-errors'),
    ('/api/arr/command-queue-summary', '/api/v2/arr/command-queue-summary'),
    ('/api/arr/backlog-status', '/api/v2/arr/backlog-status'),
    
    # letterboxd endpoints
    ('/api/arr/letterboxd/', '/api/v2/letterboxd/'),
    ('/api/arr/radarr/add-from-letterboxd-list', '/api/v2/letterboxd/add-from-list'),
    ('/api/arr/radarr/add-from-letterboxd', '/api/v2/letterboxd/add'),
    
    # container endpoints
    ('/api/container/', '/api/v2/host/container/'),
    
    # mdblist endpoints
    ('/api/mdblist/', '/api/v2/mdblist/'),
    
    # plex endpoints
    ('/api/plex/', '/api/v2/plex/'),
    
    # ratings endpoints
    ('/api/ratings/', '/api/v2/ratings/'),
    
    # watchstate endpoints
    ('/api/watchstate/', '/api/v2/watchstate/'),
    
    # nzbdav endpoints
    ('/api/nzbdav/', '/api/v2/nzbdav/'),
    
    # host endpoints
    ('/api/host/', '/api/v2/host/'),
    
    # cleanuparr endpoints
    ('/api/cleanuparr/', '/api/v2/cleanuparr/'),
    
    # catalog endpoints
    ('/api/catalog/', '/api/v2/catalog/'),
    
    # prowlarr endpoints
    ('/api/prowlarr/', '/api/v2/prowlarr/'),
    
    # seerr endpoints
    ('/api/seerr/', '/api/v2/seerr/'),
    
    # posters endpoints
    ('/api/posters/', '/api/v2/posters/'),
    
    # queue endpoints
    ('/api/queue/', '/api/v2/queue/'),
]

def update_path_template(path_template: str) -> str:
    """Update a path template to use Django API v2 paths."""
    for old, new in PATH_MAPPINGS:
        if old in path_template:
            path_template = path_template.replace(old, new)
    return path_template

def main():
    import sys
    
    dry_run = '--dry-run' in sys.argv
    commands_file = Path('/home/bear/Claude/media-stack/control-panel/static/commands.json')
    
    with open(commands_file) as f:
        commands = json.load(f)
    
    updated = 0
    for cmd in commands:
        old_path = cmd.get('PathTemplate', '')
        new_path = update_path_template(old_path)
        if old_path != new_path:
            print(f"{'[DRY RUN] ' if dry_run else ''}Updated: {cmd['Name']}")
            print(f"  {old_path} → {new_path}")
            if not dry_run:
                cmd['PathTemplate'] = new_path
            updated += 1
    
    if not dry_run and updated > 0:
        with open(commands_file, 'w') as f:
            json.dump(commands, f, indent=2)
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Summary:")
    print(f"  Updated: {updated} commands")
    print(f"  Total: {len(commands)} commands")

if __name__ == '__main__':
    main()
