# Usage: stack-loop-exclude <movie-id> [--anime] [-y|--yes]
# Adds a Radarr movie to Exclusions - the durable fix for a movie that gets
# re-monitored by import-list syncs after stack-loop-unmonitor.
# Radarr only; Sonarr has no equivalent exclusion list for episodes, so
# --anime selects radarr-anime rather than any Sonarr instance. The flag
# spelling matches the Letterboxd/MDBList family, which already routes to
# the anime instances the same way.
function stack-loop-exclude --description 'Add a Radarr movie to Exclusions'
    argparse anime yes y -- $argv
    or return 1
    if test (count $argv) -lt 1
        echo "Usage: stack-loop-exclude <movie-id> [--anime] [-y|--yes]" >&2
        return 1
    end
    set -l movie_id $argv[1]
    set -l app radarr
    set -q _flag_anime; and set app radarr_anime
    if not set -q _flag_yes; and not set -q _flag_y
        read -l -P "Exclude $app movie $movie_id from all import lists? [y/N] " confirm
        if test "$confirm" != y -a "$confirm" != Y
            echo "Cancelled."
            return 1
        end
    end
    __stack_api POST "/api/arr/$app/exclude" "{\"movieId\": $movie_id}"
end
