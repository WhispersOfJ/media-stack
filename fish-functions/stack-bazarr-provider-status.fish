# Usage: stack-bazarr-provider-status
# Per-provider throttle/error state for every enabled Bazarr subtitle
# source - catches a provider silently rate-limited or erroring on every
# request, invisible from a plain enabled/disabled list.
function stack-bazarr-provider-status --description 'Show per-provider throttle/error state in Bazarr'
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/bazarr/provider-status" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for i in data.get('items', []):
    mark = 'ok  ' if i['status'] == 'Good' else 'FAIL'
    print(f\"  [{mark}] {i['name']:<20} {i['status']:<10} retry={i['retry']}\")
"
end
