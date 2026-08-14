# Usage: stack-arr-toggle-search <radarr|sonarr|radarr_anime|sonarr_anime|all> <on|off>
# Toggles RSS sync + automatic search on every indexer for the given app(s),
# without touching interactive/manual search. Use to pause new grabs while
# an import queue drains, then turn back on when it's clear.
function stack-arr-toggle-search --description 'Turn RSS sync + automatic search on/off for Radarr/Sonarr indexers'
    if test (count $argv) -ne 2; or not contains -- $argv[2] on off
        echo "Usage: stack-arr-toggle-search <radarr|sonarr|radarr_anime|sonarr_anime|all> <on|off>" >&2
        return 1
    end
    set -l enabled true
    if test $argv[2] = off
        set enabled false
    end
    set -l apps
    if test $argv[1] = all
        # All four instances. Toggling only the general pair here is the
        # failure this command exists to prevent: the anime instances
        # keep grabbing while you believe grabbing is paused.
        set apps radarr sonarr radarr_anime sonarr_anime
    else
        set apps (__stack_arr_app $argv[1])
        or begin
            echo "Usage: stack-arr-toggle-search <radarr|sonarr|radarr_anime|sonarr_anime|all> <on|off>" >&2
            return 1
        end
    end
    set -l rc 0
    for app in $apps
        __stack_api POST "/api/arr/$app/search-toggle?enabled=$enabled"
        or set rc 1
    end
    return $rc
end
