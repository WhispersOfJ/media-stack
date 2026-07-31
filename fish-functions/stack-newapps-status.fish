# Usage: stack-newapps-status
# One-shot health sweep across all apps added 2026-07-30 (tautulli,
# wrapperr, maintainerr, checkrr, prefetcharr, lingarr, kometa).
function stack-newapps-status --description 'Health sweep of the new apps'
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/newapps/status" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for name, s in data.get('apps', {}).items():
    reach = s.get('reachable')
    reach_s = 'n/a' if reach is None else ('up' if reach else 'DOWN')
    print(f\"  {name:<12} running={s.get('running')}  http={reach_s}\")
"
end
