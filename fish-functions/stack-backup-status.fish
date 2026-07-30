# Usage: stack-backup-status
# Full snapshot history (count + oldest/newest) for both restic repos -
# distinct from stack-backup-verify's latest-only check.
function stack-backup-status --description 'Show full restic snapshot history for both backup repos'
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/backup-status" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for name, info in data.get('repos', {}).items():
    if info.get('status') == 'ok':
        print(f\"  {name:<8} {info['count']} snapshot(s)  oldest={info['oldest']}  newest={info['newest']}\")
    else:
        print(f\"  {name:<8} {info.get('status')}  {info.get('detail', info.get('path', ''))}\")
"
end
