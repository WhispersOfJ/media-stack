# Usage: stack-checkrr-recent-scans
# Scan-cycle start/finish markers pulled from a larger log tail, for
# cadence/duration - distinct from stack-checkrr-scan-status's raw tail.
function stack-checkrr-recent-scans --description 'Show recent Checkrr scan-cycle markers'
    __stack_api GET /api/checkrr/recent-scans
end
