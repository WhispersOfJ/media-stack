# Usage: stack-plex-sessions
# Who's watching what right now - direct play vs transcode, per session.
function stack-plex-sessions --description 'Show active Plex streaming sessions'
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/plex/sessions" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for s in data.get('sessions', []):
    print(f\"  {s['user']:<15} {s['title']:<40} {s['decision']:<12} {s['progress_pct']}%  ({s['player']}, {s['state']})\")
"
end
