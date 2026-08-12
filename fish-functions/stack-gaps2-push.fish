# Usage: stack-gaps2-push <tmdb-or-tvdb-id> <plex-library>
# Adds one missing title to the Arr instance its library maps to: Movies ->
# radarr, Anime Movies -> radarr-anime, Shows -> sonarr, Anime Shows ->
# sonarr-anime.
#
# The library argument is required rather than inferred. It is what decides
# the target instance, and the same TMDB id can legitimately appear under
# either a general or an anime library - guessing would mis-file the title
# under the wrong root folder and quality profile with no visible error.
#
# One title per call by design. A gap list contains wrong-year matches and
# short films, so a bulk push would add unreviewed titles in volume.
function stack-gaps2-push --description 'Add one missing title to the Arr instance its library maps to'
    if test (count $argv) -ne 2
        echo "Usage: stack-gaps2-push <tmdb-or-tvdb-id> <plex-library>" >&2
        echo "Example: stack-gaps2-push 12345 'Anime Movies'" >&2
        return 1
    end
    set -l body (python3 -c "import json, sys; print(json.dumps({'id': int(sys.argv[1]), 'library': sys.argv[2]}))" "$argv[1]" "$argv[2]")
    or begin
        echo "id must be an integer TMDB (movies) or TheTVDB (shows) id" >&2
        return 1
    end
    __stack_api POST /api/gaps2/push "$body"
end
