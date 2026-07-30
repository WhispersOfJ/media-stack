# Usage: stack-wrapperr-tautulli-link-check
# Confirms Wrapperr's saved Tautulli API key still matches the live one.
function stack-wrapperr-tautulli-link-check --description 'Check Wrapperr-Tautulli key drift'
    __stack_api GET /api/wrapperr/tautulli-link-check
end
