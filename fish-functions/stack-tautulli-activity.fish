# Usage: stack-tautulli-activity
# Live Plex streams as Tautulli sees them - per-session transcode detail.
function stack-tautulli-activity --description 'Show current Plex streams via Tautulli'
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/tautulli/activity" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  [{i['session_key']}] {i['user']:<15} {i['title']:<40} {i['state']:<10} {i.get('decision') or ''}\")
"
end
