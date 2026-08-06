# Usage: stack-tautulli-users
# Every known Plex user Tautulli has seen, with lifetime plays/duration.
function stack-tautulli-users --description 'List Plex users known to Tautulli'
    set -l host_ip 192.168.4.105
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/tautulli/users" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  {i['user']:<20} plays={i['plays']:<6} duration={i['duration']} last_seen={i.get('last_seen')}\")
"
end
