# Usage: stack-maintainerr-logs [lines]
# Tails Maintainerr's own container logs directly.
function stack-maintainerr-logs --description 'Tail Maintainerr container logs'
    set -l lines 100
    test (count $argv) -ge 1; and set lines $argv[1]
    __stack_api GET "/api/maintainerr/logs?lines=$lines"
end
