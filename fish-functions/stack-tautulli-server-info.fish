# Usage: stack-tautulli-server-info
# The Plex server Tautulli is actually configured against.
function stack-tautulli-server-info --description 'Show the Plex server Tautulli is tracking'
    __stack_api GET /api/tautulli/server-info
end
