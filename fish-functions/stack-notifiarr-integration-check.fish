# Usage: stack-notifiarr-integration-check
# Combines client-reachable + API-key-set into one pass/fail.
function stack-notifiarr-integration-check --description 'Check whether Notifiarr integration is fully ready'
    __stack_api GET /api/notifiarr/integration-check
end
