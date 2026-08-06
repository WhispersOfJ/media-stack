# Usage: stack-checkrr-badfiles-count
# Just the total count of files Checkrr has flagged - reuses the same data
# as stack-checkrr-badfiles without printing every path.
function stack-checkrr-badfiles-count --description 'Count corrupt files Checkrr has flagged'
    set -l host_ip 192.168.4.105
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/checkrr/badfiles?limit=0" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(f\"{data.get('total', 0)} bad file(s) logged.\")
"
end
