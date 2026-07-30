# Usage: stack-checkrr-config
# Effective scan config - checkpaths, cron schedule, and per-app process flags.
function stack-checkrr-config --description 'Show effective Checkrr config'
    __stack_api GET /api/checkrr/config
end
