# Usage: stack-arr-blocklist-clear <radarr|sonarr> [-y|--yes]
# Clears every blocklisted release, not just what stack-arr-blocklist shows.
# Confirms first unless -y is given.
function stack-arr-blocklist-clear --description 'Clear every blocklisted release in Radarr/Sonarr'
    if test (count $argv) -lt 1; or not contains -- $argv[1] radarr sonarr
        echo "Usage: stack-arr-blocklist-clear <radarr|sonarr> [-y|--yes]" >&2
        return 1
    end
    set -l app $argv[1]
    if not contains -- -y $argv; and not contains -- --yes $argv
        read -l -P "This clears EVERY blocklisted release in $app. Continue? [y/N] " confirm
        if test "$confirm" != y -a "$confirm" != Y
            echo "Cancelled."
            return 1
        end
    end
    __stack_api POST "/api/arr/$app/blocklist/clear"
end
