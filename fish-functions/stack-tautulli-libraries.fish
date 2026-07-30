# Usage: stack-tautulli-libraries
# Per-library item counts as Tautulli last saw them (its own cached view).
function stack-tautulli-libraries --description 'Show Tautulli per-library item counts'
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/tautulli/libraries" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  {i['name']:<20} {i['type']:<8} {i['count']}\")
"
end
