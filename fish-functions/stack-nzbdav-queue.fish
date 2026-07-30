function stack-nzbdav-queue --description 'Show NzbDAV''s current Usenet download queue'
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/nzbdav/queue" | python3 -c "
import json, sys
items = json.load(sys.stdin)
if not items:
    print('Queue is empty.')
    sys.exit(0)
for it in items:
    left = f\" ({it['size_left_mb']}MB left)\" if it.get('status') == 'Downloading' else ''
    print(f\"[{it['category']}] {it['name']}  {it['status']} {it['percentage']}%{left}\")
"
end
