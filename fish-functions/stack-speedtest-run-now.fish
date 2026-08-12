# Usage: stack-speedtest-run-now
# Triggers an out-of-schedule speedtest, outside the hourly cron.
function stack-speedtest-run-now --description 'Trigger an out-of-schedule speedtest'
    __stack_api POST /api/speedtest-tracker/run
end
