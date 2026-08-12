# Usage: stack-speedtest-history [days]
# Speedtest history over the last N days (default 7), newest first.
function stack-speedtest-history --description 'Show speedtest history'
    set -l days 7
    if test (count $argv) -ge 1
        set days $argv[1]
    end
    __stack_api GET "/api/speedtest-tracker/history?days=$days"
end
