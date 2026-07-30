function stack-arr-backlog --description 'Show an arr app''s internal command queue backlog (searches, RSS sync, bulk moves, etc)'
    if test (count $argv) -ne 1
        echo 'Usage: stack-arr-backlog <radarr|sonarr>' >&2
        return 1
    end
    set -l host_ip 192.168.4.105
    curl -sS "http://$host_ip:8420/api/arr/$argv[1]/command-backlog" | python3 -c "
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except ValueError:
    print(raw)
    sys.exit(1)
if isinstance(data, dict) and isinstance(data.get('detail'), dict):
    data = data['detail']
if not data.get('ok', True):
    print(data.get('message', raw))
    sys.exit(1)

print(data['message'])

running = data.get('running') or []
if running:
    print()
    print('Currently running:')
    for c in running:
        print(f\"  {c['id']:>6}  {c['name']:<28} started {c['started']}\")

oldest = data.get('oldest_queued') or []
if oldest:
    print()
    print(f\"Oldest queued (of {data.get('queued_total', len(oldest))} total):\")
    for c in oldest:
        print(f\"  {c['id']:>6}  {c['name']:<28} queued  {c['queued']}\")
"
end
