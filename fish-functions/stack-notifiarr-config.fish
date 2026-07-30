# Usage: stack-notifiarr-config
# Whether NOTIFIARR_API_KEY is set (masked) - Notifiarr silently no-ops without it.
function stack-notifiarr-config --description 'Check whether NOTIFIARR_API_KEY is set'
    __stack_api GET /api/notifiarr/config
end
