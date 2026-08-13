# Usage: stack-loop-exclude <movie-id> [-y|--yes]
# Adds a Radarr movie to Exclusions - the durable fix for a movie that gets
# re-monitored by import-list syncs after stack-loop-unmonitor.
# Radarr only; Sonarr has no equivalent exclusion list for episodes.
function stack-loop-exclude --description 'Add a Radarr movie to Exclusions'
    if test (count $argv) -lt 1
        echo "Usage: stack-loop-exclude <movie-id> [-y|--yes]" >&2
        return 1
    end
    set -l movie_id $argv[1]
    if not contains -- -y $argv; and not contains -- --yes $argv
        read -l -P "Exclude Radarr movie $movie_id from all import lists? [y/N] " confirm
        if test "$confirm" != y -a "$confirm" != Y
            echo "Cancelled."
            return 1
        end
    end
    __stack_api POST "/api/arr/radarr/exclude" "{\"movieId\": $movie_id}"
end
