# Usage: stack-plex-watchlist-import <radarr|sonarr> [--no-search]
# Adds your own Plex watchlist as a native import list (PlexImport) - one
# call each for movies (Radarr) or TV (Sonarr). Requires Plex's own OAuth
# token to already be set up in that app (same as any other Plex-backed
# import list) - this only creates the list entry, not the Plex auth link.
function stack-plex-watchlist-import --description 'Add your Plex watchlist as a Radarr/Sonarr import list'
    argparse 'no-search' -- $argv
    or return 1
    if test (count $argv) -ne 1; or not contains -- $argv[1] radarr sonarr
        echo "Usage: stack-plex-watchlist-import <radarr|sonarr> [--no-search]" >&2
        return 1
    end
    set -l search true
    set -q _flag_no_search; and set search false
    set -l body '{"implementation":"PlexImport","name":"Plex Watchlist","fields":{},"search_on_add":'"$search"'}'
    __stack_api POST "/api/arr/$argv[1]/import-list/add" "$body"
end
