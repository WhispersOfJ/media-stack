# Usage: stack-plexanisync-logs [lines]
# Tails PlexAniSync's container log (stdout only - it writes no log file).
# Defaults to 200 lines. Use this when stack-plexanisync-last-run reports a
# failure and the log tail it returns is not enough.
function stack-plexanisync-logs --description 'Tail PlexAniSync container logs'
    set -l lines 200
    test (count $argv) -ge 1; and set lines $argv[1]
    __stack_api GET "/api/plexanisync/logs?lines=$lines"
end
