# Usage: stack-sonarr-fix-episode-monitoring [--anime]
# Fixes any episode left unmonitored under a monitored Sonarr series/season -
# can happen after an import-list add, a partial re-add after a bulk delete,
# etc. Season 0 (specials/extras) is deliberately left alone.
# --anime targets sonarr-anime, where this drift is likelier: anime series
# are frequently re-added after a season/absolute-numbering correction, and
# that is exactly the operation that leaves episodes unmonitored.
function stack-sonarr-fix-episode-monitoring --description 'Fix unmonitored episodes under monitored Sonarr series'
    argparse anime -- $argv
    or return 1
    set -l app sonarr
    set -q _flag_anime; and set app sonarr_anime
    __stack_api POST "/api/arr/$app/monitor-episodes-fix"
end
