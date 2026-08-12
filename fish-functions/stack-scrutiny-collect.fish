# Usage: stack-scrutiny-collect
# Runs Scrutiny's SMART collector now instead of waiting for its daily
# midnight cron. Takes about a second for one disk; returns the collector's
# own output rather than making you tail logs.
function stack-scrutiny-collect --description 'Run the SMART collector now'
    __stack_api POST /api/scrutiny/collect
end
