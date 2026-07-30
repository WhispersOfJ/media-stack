# Usage: stack-cutoff-unmet <radarr|sonarr> [limit]
# Items below their quality profile's cutoff - already have a file, just
# not the target quality yet, so the app keeps upgrade-searching.
function stack-cutoff-unmet --description 'List items below quality cutoff in Radarr/Sonarr'
    if test (count $argv) -lt 1; or test (count $argv) -gt 2; or not contains -- $argv[1] radarr sonarr
        echo "Usage: stack-cutoff-unmet <radarr|sonarr> [limit]" >&2
        return 1
    end
    set -l limit 20
    if test (count $argv) -eq 2
        set limit $argv[2]
    end
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/arr/$argv[1]/cutoff-unmet?limit=$limit" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  {i['title']}\")
"
end
