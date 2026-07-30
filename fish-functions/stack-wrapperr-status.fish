# Usage: stack-wrapperr-status
# Reachability + whether Wrapperr has a Tautulli connection saved yet.
function stack-wrapperr-status --description 'Show Wrapperr reachability/config status'
    __stack_api GET /api/wrapperr/status
end
