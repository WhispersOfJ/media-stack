# Usage: stack-tautulli-history [limit]
# Recent Plex watch history across every user/library, newest first.
function stack-tautulli-history --description 'Show recent Tautulli watch history'
    set -l limit 20
    test (count $argv) -ge 1; and set limit $argv[1]
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/tautulli/history?limit=$limit" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  {i['date']}  {i['user']:<15} {i['title']:<40} {i.get('percent_complete') or 0}%\")
"
end
