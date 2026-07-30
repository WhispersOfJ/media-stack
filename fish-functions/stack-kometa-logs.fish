# Usage: stack-kometa-logs [lines]
# Tails Kometa's own container logs directly (stdout only, no log file).
function stack-kometa-logs --description 'Tail Kometa container logs'
    set -l lines 100
    test (count $argv) -ge 1; and set lines $argv[1]
    __stack_api GET "/api/kometa/logs?lines=$lines"
end
