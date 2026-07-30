# Usage: stack-notify-test
# Sends a real test message through the stack's Discord webhook - confirms
# it still works without waiting for a real failure to find out it doesn't.
function stack-notify-test --description 'Send a test notification to the stack Discord webhook'
    set -l host_ip 192.168.4.105
    curl -sS -X POST "http://$host_ip:8420/api/notify/test" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
print(data.get('message', data))
"
end
