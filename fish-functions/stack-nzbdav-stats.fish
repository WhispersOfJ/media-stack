# Usage: stack-nzbdav-stats
# Aggregate NzbDAV counts instead of the raw queue/history dumps
# stack-nzbdav-queue/stack-nzbdav-history already give.
function stack-nzbdav-stats --description 'Show aggregate NzbDAV queue/history stats'
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/nzbdav/stats" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data.get('message', data))
"
end
