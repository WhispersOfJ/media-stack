# Usage: stack-arr-blocklist <radarr|sonarr> [limit]
# Recent blocklisted releases - what got blocklisted, when, and which
# movie/series it belongs to.
function stack-arr-blocklist --description 'Show blocklisted releases in Radarr/Sonarr'
    if test (count $argv) -lt 1; or test (count $argv) -gt 2; or not contains -- $argv[1] radarr sonarr
        echo "Usage: stack-arr-blocklist <radarr|sonarr> [limit]" >&2
        return 1
    end
    set -l limit 50
    if test (count $argv) -eq 2
        set limit $argv[2]
    end
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/arr/$argv[1]/blocklist?limit=$limit" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for r in data.get('records', []):
    print(f\"  [{r['date']}] {r['title']}\")
"
end
