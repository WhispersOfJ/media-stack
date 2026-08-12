# Usage: stack-gaps2-scan [plex-library] [--full]
# Sweeps for collection/franchise gaps. With no library named it sweeps all
# four (Movies, Anime Movies, Shows, Anime Shows).
#
# Returns as soon as the sweep starts - a first full movie scan is minutes of
# TMDB round-trips, so it runs in the background. Poll stack-gaps2-status for
# progress, then stack-gaps2-missing for the results.
#
# Incremental by default: only titles added since the last scan get fresh
# TMDB collection lookups, which is the difference between minutes and tens
# of minutes. --full re-resolves everything.
function stack-gaps2-scan --description 'Sweep libraries for collection/franchise gaps'
    set -l libs
    set -l incremental true
    for arg in $argv
        if test "$arg" = --full
            set incremental false
        else
            set -a libs "$arg"
        end
    end
    set -l body (python3 -c "
import json, sys
libs = [a for a in sys.argv[2:] if a.strip()]
payload = {'incremental': sys.argv[1] == 'true'}
if libs:
    payload['libraries'] = libs
print(json.dumps(payload))
" "$incremental" $libs)
    __stack_api POST /api/gaps2/scan "$body"
end
