# Usage: stack-bazarr-wanted
# Movies/episodes Bazarr still has no subtitle for, across both libraries.
function stack-bazarr-wanted --description 'List movies/episodes still missing subtitles in Bazarr'
    set -l host_ip 192.168.4.105
    set -l service_key (string match -r '^CONTROL_PANEL_SERVICE_API_KEY=(.*)$' -- (cat /home/bear/Claude/media-stack/.env 2>/dev/null))[2]
    curl -sS -H "X-Api-Key: $service_key" "http://$host_ip:8420/api/bazarr/wanted" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data['message'])
for m in data.get('movies', []):
    print(f'  [movie]   {m}')
for e in data.get('episodes', []):
    print(f'  [episode] {e}')
"
end
