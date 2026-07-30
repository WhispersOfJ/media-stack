# Usage: stack-lingarr-movies [limit]
# Movies Lingarr knows about via its own Radarr connection.
function stack-lingarr-movies --description 'List movies Lingarr tracks'
    set -l limit 20
    test (count $argv) -ge 1; and set limit $argv[1]
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/lingarr/movies?limit=$limit" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  {i['title']}\")
"
end
