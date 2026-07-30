# Usage: stack-arr-list-implementations <radarr|sonarr>
# Every import-list type that app's own build supports (Simkl, TMDb
# Company/Keyword/User, Plex, Custom, etc), whether configured or not -
# discovery aid before using the *-import commands below.
function stack-arr-list-implementations --description 'List every import-list implementation Radarr/Sonarr supports'
    if test (count $argv) -ne 1; or not contains -- $argv[1] radarr sonarr
        echo "Usage: stack-arr-list-implementations <radarr|sonarr>" >&2
        return 1
    end
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/arr/$argv[1]/import-list/implementations" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  {i['implementation']:<22} {i['name']}\")
"
end
