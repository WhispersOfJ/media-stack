# Usage: stack-tmdb-missing
# Scans every movie/show library for items with no TMDb link and writes
# them to ~/missing.txt for manual review - overwrites each run, this is
# a rescan tool, not an appending log.
function stack-tmdb-missing --description 'Find Plex items missing a TMDb link, write ~/missing.txt'
    set -l host_ip 192.168.4.105
    set -l out ~/missing.txt
    curl -sS "http://$host_ip:8420/api/plex/tmdb-missing" | python3 -c "
import json, sys

data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
if not data.get('ok', True):
    print(data.get('message', 'Request failed.'), file=sys.stderr)
    sys.exit(1)

items = data.get('items', [])
with open('$out', 'w') as f:
    for it in items:
        year = it.get('year') or '?'
        line = f\"{it['library']}: {it['title']} ({year}) ratingKey={it['ratingKey']}\"
        f.write(line + '\n')

print(f\"{len(items)} items missing a TMDb link, written to $out\")
"
end
