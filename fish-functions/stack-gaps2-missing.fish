# Usage: stack-gaps2-missing [plex-library] [limit]
# Titles a collection or franchise says should be there but the library does
# not have, from each library's most recent scan. Every entry is tagged with
# the Arr instance stack-gaps2-push would send it to, so the destination is
# visible in the list rather than only at push time.
#
# Named library restricts to one; limit caps the list (the total is always
# reported in full).
function stack-gaps2-missing --description 'Titles missing from collections/franchises, with their target Arr'
    # Built with urlencode rather than string-joined by hand: a Plex library
    # name may contain a space, and an unencoded space makes curl reject the
    # URL outright rather than failing usefully.
    set -l query (python3 -c "
import sys
from urllib.parse import urlencode
pairs = [(k, v) for k, v in zip(('library', 'limit'), sys.argv[1:]) if v.strip()]
print(('?' + urlencode(pairs)) if pairs else '')
" "$argv[1]" "$argv[2]")
    __stack_api GET "/api/gaps2/missing$query"
end
