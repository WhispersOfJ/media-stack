# Usage: stack-checkrr-scan-status [lines]
# Tails Checkrr's own container logs for the most recent scan activity.
function stack-checkrr-scan-status --description 'Tail recent Checkrr scan activity'
    set -l lines 40
    test (count $argv) -ge 1; and set lines $argv[1]
    __stack_api GET "/api/checkrr/scan-status?lines=$lines"
end
