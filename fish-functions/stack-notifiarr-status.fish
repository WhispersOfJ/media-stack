# Usage: stack-notifiarr-status
# Reachability of Notifiarr's local client API.
function stack-notifiarr-status --description 'Check Notifiarr client reachability'
    __stack_api GET /api/notifiarr/status
end
