# Private helper: validate an Arr instance name and normalize it to the
# spelling the caller needs. Every stack-* command that takes an app
# argument funnels through this, so the accepted spellings are defined
# once instead of drifting across 19 separate `contains` guards.
#
# Two spellings are load-bearing and neither can be dropped:
#   radarr_anime  - the core/arr_client.py ARR_APPS key, which is what
#                   /api/arr/{app_name}/... matches on.
#   radarr-anime  - the Docker container name, which is what the logs
#                   route and `docker` itself need.
# Underscores are hostile to type at a prompt, so both are accepted
# everywhere along with a short alias, and this normalizes.
#
# Usage: __stack_arr_app <name> [--container]
# Prints the normalized name and returns 0, or prints nothing and
# returns 1 if the name is not an Arr instance. Callers test the return
# value; the guard reads `not __stack_arr_app $argv[1] >/dev/null`.
function __stack_arr_app
    argparse container -- $argv
    or return 1
    if test (count $argv) -ne 1
        return 1
    end
    set -l key
    switch $argv[1]
        case radarr
            set key radarr
        case sonarr
            set key sonarr
        case radarr_anime radarr-anime ranime anime-movies
            set key radarr_anime
        case sonarr_anime sonarr-anime sanime anime-shows
            set key sonarr_anime
        case '*'
            return 1
    end
    if set -q _flag_container
        string replace '_' '-' -- $key
    else
        echo $key
    end
end
