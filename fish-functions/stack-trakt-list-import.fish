# Usage: stack-trakt-list-import <radarr|sonarr> <trakt-username> <trakt-listname> <display-name> [--no-search]
# Adds a public Trakt list as an import list (TraktListImport). Reuses
# whichever app already has a Trakt OAuth token from an existing list
# (this Radarr's DCAU/DCEU lists, this Sonarr's Top250TV/True Crime) -
# no fresh "Authenticate with Trakt" pass needed unless neither app has
# one yet, in which case add one list manually through the app's own UI
# first and every command here can piggyback on it after.
function stack-trakt-list-import --description 'Add a public Trakt list as a Radarr/Sonarr import list'
    argparse 'no-search' -- $argv
    or return 1
    if test (count $argv) -ne 4; or not contains -- $argv[1] radarr sonarr
        echo "Usage: stack-trakt-list-import <radarr|sonarr> <trakt-username> <trakt-listname> <display-name> [--no-search]" >&2
        return 1
    end
    set -l search true
    set -q _flag_no_search; and set search false
    set -l body (python3 -c "
import json, sys
username, listname, name, search = sys.argv[1:5]
print(json.dumps({'implementation':'TraktListImport','name':name,'fields':{'username':username,'listname':listname},'search_on_add':search=='true'}))
" "$argv[2]" "$argv[3]" "$argv[4]" "$search")
    __stack_api POST "/api/arr/$argv[1]/import-list/add" "$body"
end
