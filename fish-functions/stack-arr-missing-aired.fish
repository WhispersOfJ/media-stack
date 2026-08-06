# Usage: stack-arr-missing-aired <radarr|sonarr>
# Monitored + no file + already aired/released, excluding upcoming items -
# the gap in each app's own Wanted/Missing list (Sonarr's has no filter for
# this and gets buried under not-yet-aired episodes; Radarr's has a native
# equivalent this mirrors).
function stack-arr-missing-aired --description 'List monitored items missing a file that have already aired/released'
    if test (count $argv) -ne 1; or not contains -- $argv[1] radarr sonarr
        echo "Usage: stack-arr-missing-aired <radarr|sonarr>" >&2
        return 1
    end
    set -l host_ip 192.168.4.105
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/arr/$argv[1]/missing-aired" | python3 -c "
import json, sys
items = json.load(sys.stdin)
if isinstance(items, dict) and isinstance(items.get('detail'), dict):
    items = items['detail']
if not items:
    print('Nothing missing - all monitored, aired/released items have a file.')
    sys.exit(0)
for it in items:
    if 'series' in it:
        label = f\"{it.get('series')} {it.get('episode')} - {it.get('title')}\"
    else:
        label = f\"{it.get('title')} ({it.get('year')})\"
    print(f\"{label}  aired {it.get('aired')}\")
"
end
