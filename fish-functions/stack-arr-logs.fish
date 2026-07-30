# Usage: stack-arr-logs <radarr|sonarr|prowlarr> [lines]
function stack-arr-logs --description 'Tail an *arr app''s container log directly'
    if test (count $argv) -lt 1
        echo "Usage: stack-arr-logs <radarr|sonarr|prowlarr> [lines]" >&2
        return 1
    end
    set -l host_ip 192.168.4.105
    set -l lines 100
    if test (count $argv) -ge 2
        set lines $argv[2]
    end
    curl -sS "http://$host_ip:8420/api/arr/$argv[1]/logs?lines=$lines" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if isinstance(d, dict) and isinstance(d.get('detail'), dict):
    d = d['detail']
if not d.get('ok', True):
    print(d.get('message', 'error'), file=sys.stderr)
    sys.exit(1)
print(d.get('log', ''))
"
end
