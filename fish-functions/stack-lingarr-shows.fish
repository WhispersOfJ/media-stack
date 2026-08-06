# Usage: stack-lingarr-shows [limit]
# Shows Lingarr knows about via its own Sonarr connection.
function stack-lingarr-shows --description 'List shows Lingarr tracks'
    set -l limit 20
    test (count $argv) -ge 1; and set limit $argv[1]
    set -l host_ip 192.168.4.105
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/lingarr/shows?limit=$limit" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  {i['title']}\")
"
end
