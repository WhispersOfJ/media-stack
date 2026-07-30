# Private helper: call Control Panel's API (direct port, no Traefik/Authelia
# in front of it anymore) and print its `message` field. Works against both
# response shapes app.py returns: {"ok","message",...} on 2xx, and FastAPI's
# {"detail": {"ok","message",...}} wrapper on a raised HTTPException.
# Usage: __stack_api METHOD PATH [JSON_BODY]
# Exit status mirrors the API's own "ok" field (or the HTTP status if the
# body isn't JSON at all).
function __stack_api
    set -l method $argv[1]
    set -l path $argv[2]
    set -l body $argv[3]
    set -l host_ip 192.168.4.105
    set -l curl_opts -sS -X $method -w '\n%{http_code}'
    if test -n "$body"
        set curl_opts $curl_opts -H 'Content-Type: application/json' -d $body
    end
    curl $curl_opts "http://$host_ip:8420$path" | python3 -c "
import json, sys
raw = sys.stdin.read()
body, _, code = raw.rpartition('\n')
try:
    data = json.loads(body) if body else {}
except ValueError:
    print(body or f'(empty response, HTTP {code})')
    sys.exit(1)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
if isinstance(data, dict) and 'message' in data:
    print(data['message'])
    sys.exit(0 if data.get('ok') else 1)
print(json.dumps(data, indent=2))
sys.exit(0 if code.strip() == '200' else 1)
"
end
