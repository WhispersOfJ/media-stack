# Usage: stack-prefetcharr-logs [lines]
# Tails Prefetcharr's own log file (config/prefetcharr), not container stdout.
function stack-prefetcharr-logs --description 'Tail Prefetcharr log file'
    set -l lines 60
    test (count $argv) -ge 1; and set lines $argv[1]
    __stack_api GET "/api/prefetcharr/logs?lines=$lines"
end
