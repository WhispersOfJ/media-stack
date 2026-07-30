# Usage: stack-prowlarr-indexers
# Every configured Prowlarr indexer's enabled/priority state.
function stack-prowlarr-indexers --description 'List Prowlarr indexers with enabled state and priority'
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/prowlarr/indexers" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    mark = 'on ' if i['enabled'] else 'off'
    print(f\"  [{mark}] pri={i['priority']:<3} {i['name']}\")
"
end
