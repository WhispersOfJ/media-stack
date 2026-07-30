# Usage: stack-prefetcharr-status
# Container up/down plus the most recent prefetch-trigger event logged.
function stack-prefetcharr-status --description 'Show Prefetcharr container/last-event status'
    __stack_api GET /api/prefetcharr/status
end
