# Usage: stack-bazarr-history [limit]
# Recent subtitle download history (movies and episodes), newest first -
# successes and failures both.
function stack-bazarr-history --description 'Show recent Bazarr subtitle download history'
    set -l limit 20
    test (count $argv) -ge 1; and set limit $argv[1]
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/bazarr/history?limit=$limit" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  {i['title']:<40} {i['action']:<20} {i.get('provider') or ''}\")
"
end
