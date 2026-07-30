# Usage: stack-tautulli-notifiers
# Configured notification agents inside Tautulli itself (separate from Notifiarr).
function stack-tautulli-notifiers --description 'List configured Tautulli notifiers'
    __stack_api GET /api/tautulli/notifiers
end
