# Usage: stack-tautulli-recently-added [limit]
# Tautulli's own recently-added feed (separate from stack-plex's recently-added).
function stack-tautulli-recently-added --description 'Show recently-added items via Tautulli'
    set -l limit 15
    test (count $argv) -ge 1; and set limit $argv[1]
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/tautulli/recently-added?limit=$limit" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  {i['title']}\")
"
end
