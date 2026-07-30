# Usage: stack-cleanuparr-strikes [limit]
# Recent stalled/slow/malware strikes Cleanuparr has issued.
function stack-cleanuparr-strikes --description 'Show recent Cleanuparr strikes'
    set -l limit 15
    if test (count $argv) -eq 1
        set limit $argv[1]
    end
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/cleanuparr/strikes?limit=$limit" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  {i['created_at']}  {i['type']:<10} {i['title']}\")
"
end
