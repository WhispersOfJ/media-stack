# Usage: stack-letterboxd-radarr-track <letterboxd-list-url> [--label TEXT]
# Registers a Letterboxd list for the nightly diff-only sync
# (systemd/stack-letterboxd-sync.timer, 04:00 daily). Adding, then never
# untracking, is how a list stays synced indefinitely - untrack with
# stack-letterboxd-radarr-untrack when done.
function stack-letterboxd-radarr-track --description 'Register a Letterboxd list for nightly diff-only sync'
    argparse 'label=' -- $argv
    or return 1
    if test (count $argv) -ne 1
        echo "Usage: stack-letterboxd-radarr-track <letterboxd-list-url> [--label TEXT]" >&2
        return 1
    end
    set -l url $argv[1]
    set -l label ""
    set -q _flag_label; and set label $_flag_label
    set -l body (python3 -c "
import json, sys
url, label = sys.argv[1:3]
payload = {'url': url}
if label:
    payload['label'] = label
print(json.dumps(payload))
" "$url" "$label")
    __stack_api POST "/api/arr/letterboxd/track" "$body"
end
