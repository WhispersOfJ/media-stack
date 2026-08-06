# Usage: stack-backup-integrity-check
# On-demand `restic check` (10% data subset, same sampling
# backup-config.sh's own monthly automatic check uses) against both the
# local and off-site repos - for verifying right now instead of waiting
# for the 1st of the month, e.g. right after a repo's been touched by
# hand. Can take a few minutes; this is not the fast freshness check
# stack-backup-verify already does.
function stack-backup-integrity-check --description 'Run an on-demand restic integrity check on both backup repos'
    set -l host_ip 192.168.4.105
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" --max-time 600 -X POST "http://$host_ip:8420/api/backup-integrity-check" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for name, info in data.get('repos', {}).items():
    print(f\"  {name:<8} {info['status']}\" + (f\"  {info['detail']}\" if info.get('detail') else ''))
"
end
