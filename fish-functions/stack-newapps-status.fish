# Usage: stack-newapps-status
# One-shot health sweep across the remaining apps added 2026-07-30
# (prefetcharr). Tautulli, Wrapperr, Maintainerr, and Lingarr were
# decommissioned; see PLANS.md.
function stack-newapps-status --description 'Health sweep of the new apps'
    set -l host_ip 192.168.4.20
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/newapps/status" | python3 -c "
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
