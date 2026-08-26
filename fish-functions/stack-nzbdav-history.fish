# Usage: stack-nzbdav-history [limit]  (default 20)
function stack-nzbdav-history --description 'Show NzbDAV''s recent download history (completed/failed)'
    set -l limit 20
    if test (count $argv) -ge 1
        set limit $argv[1]
    end
    set -l host_ip 192.0.2.1
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/v2/nzbdav/history?limit=$limit" | python3 -c "
import json, sys
data = json.load(sys.stdin)
items = data['items'] if isinstance(data, dict) else data
if not items:
    print('No history yet.')
    sys.exit(0)
for it in items:
    line = f\"[{it['category']}] {it['name']}  {it['status']}  {it['size']}\"
    if it.get('fail_message'):
        line += f\"  - {it['fail_message']}\"
    print(line)
"
end
