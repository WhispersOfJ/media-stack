# Usage: stack-maintainerr-collections
# Plex collections Maintainerr is tracking for cleanup evaluation.
function stack-maintainerr-collections --description 'List Plex collections Maintainerr tracks'
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/maintainerr/collections" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  [{i['id']}] {i['title']:<40} {i['media_count']} item(s)\")
"
end
