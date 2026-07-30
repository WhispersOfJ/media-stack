# Usage: stack-checkrr-badfiles [limit]
# Corrupt/unreadable files Checkrr has flagged (process:false - scan/log only).
function stack-checkrr-badfiles --description 'List corrupt files Checkrr has flagged'
    set -l limit 50
    test (count $argv) -ge 1; and set limit $argv[1]
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/checkrr/badfiles?limit=$limit" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    print(f\"  {i['reason']:<10} {i['path']}\")
"
end
