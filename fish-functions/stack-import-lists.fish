# Usage: stack-import-lists <radarr|sonarr>
# Configured import lists (Trakt, other *arr instances, etc.) and whether
# each is enabled - a quick check without opening Settings -> Import Lists.
function stack-import-lists --description 'List configured import lists for Radarr/Sonarr'
    if test (count $argv) -ne 1; or not contains -- $argv[1] radarr sonarr
        echo "Usage: stack-import-lists <radarr|sonarr>" >&2
        return 1
    end
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/arr/$argv[1]/import-lists" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    mark = 'on ' if i['enabled'] else 'off'
    auto = 'auto-add' if i['enableAutomaticAdd'] else 'manual'
    print(f\"  [{mark}] {i['name']:<30} {auto}\")
"
end
