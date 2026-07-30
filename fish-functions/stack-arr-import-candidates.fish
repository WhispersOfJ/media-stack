# Usage: stack-arr-import-candidates <radarr|sonarr>
# Lists files stuck in that app's queue that are ready to manually import,
# numbered for use with stack-arr-import.
function stack-arr-import-candidates --description 'List files ready to manually import in an *arr app'
    if test (count $argv) -ne 1; or not contains -- $argv[1] radarr sonarr
        echo "Usage: stack-arr-import-candidates <radarr|sonarr>" >&2
        return 1
    end
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/arr/$argv[1]/manual-import" | python3 -c "
import json, sys
items = json.load(sys.stdin)
if not items:
    print('No importable files right now - nothing stuck in the queue.')
    sys.exit(0)
for i, it in enumerate(items):
    label = it.get('episode') or it.get('match_title') or ''
    print(f\"[{i}] {it.get('name')}\")
    print(f\"     from: {it.get('queue_title')}  {label}  {it.get('quality')}  {it.get('size')}\")
    if it.get('rejections'):
        print(f\"     rejections: {', '.join(it['rejections'])}\")
print()
print('Run: stack-arr-import $argv[1] <index>')
"
end
