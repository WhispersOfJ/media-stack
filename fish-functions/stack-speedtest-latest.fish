# Usage: stack-speedtest-latest
# Most recent Speedtest Tracker result (down/up/ping/jitter).
function stack-speedtest-latest --description 'Show latest speedtest result'
    __stack_api GET /api/speedtest-tracker/latest
end
