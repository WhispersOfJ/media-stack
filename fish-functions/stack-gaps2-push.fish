# Usage: stack-gaps2-push <tmdb-or-tvdb-id> <plex-library>
# Adds one missing title to the Arr instance its library maps to: Movies ->
# radarr, Shows -> sonarr. The anime libraries were dropped from GAPS-2 on
# 2026-08-12.
#
# The library argument is required rather than inferred. It decides the
# target instance and also the id type - movies are pushed by TMDB id, shows
# by TheTVDB id, and the same integer is a valid id in both namespaces
# pointing at unrelated titles.
#
# One title per call by design. A gap list contains wrong-year matches and
# short films, so a bulk push would add unreviewed titles in volume.
function stack-gaps2-push --description 'Add one missing title to the Arr instance its library maps to'
    if test (count $argv) -ne 2
        echo "Usage: stack-gaps2-push <tmdb-or-tvdb-id> <plex-library>" >&2
        echo "Example: stack-gaps2-push 12345 Movies" >&2
        return 1
    end
    set -l body (python3 -c "import json, sys; print(json.dumps({'id': int(sys.argv[1]), 'library': sys.argv[2]}))" "$argv[1]" "$argv[2]")
    or begin
        echo "id must be an integer TMDB (movies) or TheTVDB (shows) id" >&2
        return 1
    end
    __stack_api POST /api/gaps2/push "$body"
end
