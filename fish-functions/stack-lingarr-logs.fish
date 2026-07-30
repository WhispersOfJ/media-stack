# Usage: stack-lingarr-logs [lines]
# Tails Lingarr's own container logs.
function stack-lingarr-logs --description 'Tail Lingarr container logs'
    set -l lines 60
    test (count $argv) -ge 1; and set lines $argv[1]
    __stack_api GET "/api/lingarr/logs?lines=$lines"
end
